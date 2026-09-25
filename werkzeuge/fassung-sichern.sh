#!/bin/bash
# Legt eine Fassungs-Sicherung der laufenden Radio-Ablaeufe an.
# Die Sicherungen liegen AUSSERHALB des Projekts (der Projektordner bleibt schlank):
#   <sicherungen>/<name>/ablaeufe/  - Exporte aus n8n
#   <sicherungen>/<name>/bau/       - Erzeuger-, Einspiel- und Pruefskripte
#   <sicherungen>/<name>/dienste/   - Quellen der Dienste (Katalog, Listen, Sprachausgabe)
#   <sicherungen>/<name>/README.md  - Beschreibung (aus <textdatei>) und Rueckweg
# Aufruf:  bash fassung-sichern.sh <name> [beschreibung.md]
#
# Ersetzt tempo/01-fassung-sichern.sh: dieselbe Wirkung, aber ohne fest
# eingebauten Beschreibungstext und mit den Quellen der Dienste inklusive
# Dockerfile (sonst fehlt beim Wiederaufbau die Zeile fuer playlist.py).
set -euo pipefail

NAME=${1:?Name fehlt, z. B. radio-v4-2026-09-20-mit-listen}
BESCHREIBUNG=${2:-}
CFG=~/.ssh/config
RADIO=<dokuordner>
SICHERUNGEN=<projektordner>/sicherungen/radio-fassungen
ZIEL=$SICHERUNGEN/$NAME
WERKZEUGE=$RADIO/werkzeuge

mkdir -p "$ZIEL/ablaeufe" "$ZIEL/bau" "$ZIEL/dienste"

# --- Exporte der laufenden Ablaeufe
for W in RadioAgentBot RadioWerkzeug AzuraWerkzeug MeldungenWerkzeug Konfiguration StimmenBot bjFSfXGqpLg7AAXw; do
  ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
    docker exec -u node n8n n8n export:workflow --id=$W --output=/tmp/$W.json >/dev/null 2>&1
    docker cp n8n:/tmp/$W.json /tmp/$W.json >/dev/null'"
  ssh -F "$CFG" ai-server "pct exec 103 -- cat /tmp/$W.json" > "$ZIEL/ablaeufe/$W.json"
  printf '  %-18s %s Bytes\n' "$W" "$(wc -c < "$ZIEL/ablaeufe/$W.json")"
done

# --- Sicherung im kompletten Datenbestand (n8n-Datenbank) fuer den Notfall
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  docker cp n8n:/home/node/.n8n/database.sqlite /tmp/n8n-daten.sqlite >/dev/null && echo ok'" >/dev/null
ssh -F "$CFG" ai-server "pct exec 103 -- cat /tmp/n8n-daten.sqlite" | gzip -9 > "$ZIEL/n8n-daten.sqlite.gz"
printf '  %-18s %s Bytes\n' "n8n-daten.sqlite.gz" "$(wc -c < "$ZIEL/n8n-daten.sqlite.gz")"

# --- Erzeuger-, Einspiel- und Pruefskripte (Radiotopf und Listenaufgaben)
for F in agent-wf-bauen.py agent-einspielen.sh agent-nachbereiten.py \
         import-agent-vorbereiten.py statische-daten-patchen.py erlaubte-setzen.py \
         code-pruefen.py archiv-anlegen.py schlagwort-anlegen.py \
         bot-test.sh antworten.js letzter.js eine.js feld.js auswertung.py \
         durchlauf.sh ausfuehrungen.sh fassung-sichern.sh \
         agent-patchen.py agent-patchen.sh agent-einspielen-nur.sh dienst-einspielen.sh; do
  [ -f "$WERKZEUGE/$F" ] && cp "$WERKZEUGE/$F" "$ZIEL/bau/"
done
mkdir -p "$ZIEL/bau/playlist" "$ZIEL/bau/meldungen" "$ZIEL/bau/tempo"
cp "$WERKZEUGE/playlist/"* "$ZIEL/bau/playlist/" 2>/dev/null || true
cp "$WERKZEUGE/meldungen/"* "$ZIEL/bau/meldungen/" 2>/dev/null || true
cp "$WERKZEUGE/tempo/"*.py "$WERKZEUGE/tempo/"*.sh "$WERKZEUGE/tempo/README.md" "$ZIEL/bau/tempo/" 2>/dev/null || true

# --- Quellen der Dienste samt Bauanleitung
cp "$RADIO/dienst/"*.py "$ZIEL/dienste/" 2>/dev/null || true
cp "$RADIO/dienst/Dockerfile" "$RADIO/dienst/docker-compose.yml" "$RADIO/dienst/README.md" "$ZIEL/dienste/" 2>/dev/null || true

# --- Doku-Abzug
cp "$RADIO/ANHANG/entwicklung/README.md" "$ZIEL/README-der-Doku.md"
cp "$RADIO/DOKU/HANDBUCH.md" "$ZIEL/ARCHITEKTUR-der-Doku.md" 2>/dev/null || true

# Die Exporte enthalten Zugangswerte (Bot-Kennung, Schnittstellenschluessel,
# DJ-Passwort) - deshalb nur fuer den Eigentuemer lesbar.
chmod 700 "$ZIEL" "$ZIEL/ablaeufe" "$ZIEL/bau" "$ZIEL/bau/playlist" "$ZIEL/bau/meldungen" "$ZIEL/bau/tempo" "$ZIEL/dienste"
chmod 600 "$ZIEL"/ablaeufe/* "$ZIEL"/bau/* "$ZIEL"/bau/playlist/* "$ZIEL"/bau/meldungen/* "$ZIEL"/bau/tempo/* "$ZIEL"/*.sqlite.gz \
          "$ZIEL"/dienste/* "$ZIEL"/*.md 2>/dev/null || true

# --- Beschreibung
{
  if [ -n "$BESCHREIBUNG" ] && [ -f "$BESCHREIBUNG" ]; then
    cat "$BESCHREIBUNG"
  else
    echo "# Fassung $NAME"
    echo
    echo "Sicherung der laufenden Radio-Ablaeufe (Stand $(date '+%d.%m.%Y %H:%M'))."
  fi
  cat <<TEXT

## Inhalt

- \`ablaeufe/\` – Exporte aus n8n: RadioAgentBot, RadioWerkzeug, AzuraWerkzeug,
  AI-Moderator (\`bjFSfXGqpLg7AAXw\`)
- \`n8n-daten.sqlite.gz\` – komplette n8n-Datenbank (Notfall)
- \`bau/\` – Erzeuger-, Einspiel- und Prüfskripte; \`bau/playlist/\` die Listenaufgaben,
  \`bau/meldungen/\` das Meldungspostfach (Suchbot, Ansagen), \`bau/tempo/\` die
  Tempo-Änderungen mit ihren Prüfungen
- \`dienste/\` – Quellen der Dienste (Katalog, Listen, Sprachausgabe) samt Dockerfile
- \`README-der-Doku.md\`, \`ARCHITEKTUR-der-Doku.md\` – Doku-Abzug

## Rückweg (Abläufe aus dieser Sicherung wieder herstellen)

\`\`\`bash
cd ../..
CFG=~/.ssh/config
for W in RadioAgentBot RadioWerkzeug AzuraWerkzeug MeldungenWerkzeug Konfiguration StimmenBot bjFSfXGqpLg7AAXw; do
  cat $SICHERUNGEN/$NAME/ablaeufe/\$W.json | ssh -F "\$CFG" ai-server \\
    "pct exec 103 -- bash -c 'cat > /tmp/\$W.json'"
  ssh -F "\$CFG" ai-server "pct exec 103 -- bash -lc '
    docker cp /tmp/\$W.json n8n:/tmp/ >/dev/null
    docker exec -u node n8n n8n import:workflow --input=/tmp/\$W.json \\
      --projectId=DEINE-N8N-PROJEKT-KENNUNG'
done
ssh -F "\$CFG" ai-server "pct exec 103 -- docker restart n8n"
\`\`\`

Damit stehen die Abläufe wieder wie gesichert (Webhook-Pfade und die erlaubten
Kennungen stecken in den Abläufen selbst).

**Nur den Bot-Ablauf** zurücksetzen (so wurde am 20.09.2026 nach dem Tippfehler
in der Listenweiche gearbeitet):

\`\`\`bash
cd ../../werkzeuge
bash tempo/04-einspielen.sh $SICHERUNGEN/$NAME/ablaeufe/RadioAgentBot.json RadioAgentBot
\`\`\`

## Dienste wieder aufbauen

\`\`\`bash
# Katalog + Listen (LXC 103, /opt/radio-tts)
bash werkzeuge/playlist/08-dienst-einspielen.sh
\`\`\`

Der Dockerfile muss die Datei \`app/playlist.py\` mitkopieren – sonst fehlt das
Listen-Modul im Dienst (\`No module named 'playlist'\`).
TEXT
} > "$ZIEL/README.md"

echo
echo "Sicherung liegt in $ZIEL"
ls -la "$ZIEL"
