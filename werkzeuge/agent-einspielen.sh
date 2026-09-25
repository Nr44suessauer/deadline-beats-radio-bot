#!/usr/bin/env bash
# Spielt den Agenten und seine Werkzeuge ein.
#   - legt die Ollama-Anmeldedaten an (einmalig)
#   - importiert die 5 Werkzeug-Arbeitsablaeufe und den Agenten
#   - ordnet alles dem Projekt und dem Ordner "Radio" zu
#   - aktiviert den Agenten, schaltet den alten Wunschbot ab (beide nutzen denselben Bot)
#   - setzt Testschluessel und Betreiberliste
# Aufruf: agent-einspielen.sh [chatIds...]      (Standard: nur DEINE-CHAT-ID)
set -eu
CFG=~/.ssh/config
SCHLUESSEL=$(cat <dokuordner>/NACHBAU/zugangsdaten/bot-test-schluessel.txt)
IDS="${*:-DEINE-CHAT-ID}"

# Erst die Arbeitsablaeufe erzeugen, dann die Importdateien daraus bauen -
# import-agent-vorbereiten.py liest nur /tmp/radio-*.json.
python3 agent-wf-bauen.py
python3 import-agent-vorbereiten.py

cat > /tmp/ollama-cred.json <<'JSON'
[{"id": "DEINE-OLLAMA-ZUGANGSKENNUNG", "name": "Ollama (OpenAI-Schnittstelle)", "type": "openAiApi",
  "data": {"apiKey": "ollama", "url": "http://192.168.178.187:11434/v1"}}]
JSON

# Der Ablauf im Container liegt bewusst als eigenes Skript vor - so bleiben die
# Anfuehrungszeichen beim Weiterreichen per ssh uebersichtlich.
cat > /tmp/agent-remote.sh <<'REMOTE'
#!/usr/bin/env bash
set -eu
SCHLUESSEL="$1"; shift
IDS="$*"
cd /tmp

docker cp /tmp/radio-werkzeuge-import.json n8n:/tmp/ >/dev/null
docker cp /tmp/radio-agent-import.json n8n:/tmp/ >/dev/null
docker cp /tmp/ollama-cred.json n8n:/tmp/ >/dev/null
docker cp /tmp/agent-nachbereiten.py n8n:/tmp/ >/dev/null

# Anmeldedaten zuerst - der CLI-Befehl braucht einen laufenden Container.
echo "--- Anmeldedaten ---"
docker exec -u node n8n n8n import:credentials --input=/tmp/ollama-cred.json 2>&1 | tail -2
# Achtung: n8n meldet Strukturfehler (z. B. eine Verbindung zu einem nicht
# vorhandenen Knoten) nur im Protokoll und bricht mit Exit 1 ab. Ohne diese
# Pruefung laeuft still die alte Fassung weiter.
importieren() {   # importieren <datei> <bezeichnung>
  if docker exec -u node n8n n8n import:workflow --input="$1" \
       --projectId=DEINE-N8N-PROJEKT-KENNUNG > /tmp/import.log 2>&1; then
    tail -2 /tmp/import.log
  else
    echo "ABBRUCH: Import von $2 fehlgeschlagen (alte Fassung bleibt aktiv):"
    cat /tmp/import.log
    exit 1
  fi
}
echo "--- Werkzeuge ---"
importieren /tmp/radio-werkzeuge-import.json "Werkzeug-Ablaeufe"
echo "--- Agent ---"
importieren /tmp/radio-agent-import.json "Agent"

# Aktivieren/Schalten laeuft ueber den offiziellen Befehl: n8n 2.x fuehrt neben
# `active` noch die veroeffentlichte Fassung (activeVersionId); ein Schreiben der
# Spalte active allein wird beim naechsten Start wieder ueberschrieben.
#
# Wichtig: der Werkzeug-Arbeitsablauf MUSS aktiv sein - n8n lehnt den Aufruf
# eines Unter-Arbeitsablaufs sonst mit "Workflow is not active and cannot be
# executed." ab (der Agent meldet dem Modell dann nur "Es gab einen Fehler").
echo "--- Schalten ---"
docker exec -u node n8n n8n update:workflow --id=RadioTelegramBot --active=false 2>&1 | tail -1
for W in RadioWerkzeug AzuraWerkzeug MeldungenWerkzeug RadioAgentBot; do
  docker exec -u node n8n n8n update:workflow --id=$W --active=true 2>&1 | tail -1
done

docker stop n8n >/dev/null
python3 /tmp/agent-nachbereiten.py "$SCHLUESSEL" $IDS
docker start n8n >/dev/null
for i in $(seq 1 40); do
  C=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5678/healthz); [ "$C" = "200" ] && break; sleep 3
done
for i in $(seq 1 40); do
  W=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:5678/webhook/DEIN-WEBHOOK-PFAD \
      -H "Content-Type: application/json" -d "{}")
  [ "$W" != "404" ] && break; sleep 3
done
echo "n8n: $C | Webhook: $W"
docker logs --tail 40 n8n 2>&1 | grep -iE "activated workflow|error" | tail -6
REMOTE

for datei in /tmp/radio-werkzeuge-import.json /tmp/radio-agent-import.json /tmp/ollama-cred.json \
             agent-nachbereiten.py /tmp/agent-remote.sh; do
  cat "$datei" | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/$(basename "$datei")'"
done

ssh -F "$CFG" ai-server "pct exec 103 -- bash /tmp/agent-remote.sh '$SCHLUESSEL' $IDS"
