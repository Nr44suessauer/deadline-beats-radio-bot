#!/usr/bin/env bash
# Spielt die gepatchte Agenten-Fassung UND die Werkzeug-Ablaeufe in n8n ein.
#
# Nimmt eine fertige Importdatei (aus agent-patchen.sh) fuer den Agenten und die
# Werkzeug-Importdatei aus dem Erzeuger. Vorher vergleichen:
#   python3 vergleich-agent.py <laufend> <neubau>
#
# Aufruf:  bash agent-einspielen.sh <agent.json>
set -euo pipefail

CFG=~/.ssh/config
AGENT=${1:-/tmp/radio-agent-neu.json}
WERKZEUGE=/tmp/radio-werkzeuge-import.json
KONFIG=/tmp/radio-konfiguration.json
PROJEKT=DEINE-N8N-PROJEKT-KENNUNG

[ -f "$AGENT" ] || { echo "Datei fehlt: $AGENT"; exit 1; }
[ -f "$WERKZEUGE" ] || { echo "Datei fehlt: $WERKZEUGE (erst agent-patchen.sh laufen lassen)"; exit 1; }
[ -f "$KONFIG" ] || { echo "Datei fehlt: $KONFIG (erst agent-patchen.sh laufen lassen)"; exit 1; }
for D in "$AGENT" "$WERKZEUGE" "$KONFIG"; do
  if grep -q "<GEHEIM>" "$D"; then
    echo "ABBRUCH: $D enthaelt Maskenmerker <GEHEIM>."
    exit 1
  fi
done

echo "--- Agent pruefen"
python3 - "$AGENT" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
w = d[0] if isinstance(d, list) else d
namen = [k["name"] for k in w["nodes"]]
print(f"  {len(namen)} Knoten, Kennung {w.get('id')}")
for pflicht in ("Dienst Art", "Meldung Dienst", "Meldung Karte", "Werkzeug Meldungen",
                "Zeitplan Meldungen"):
    print(("  ok   " if pflicht in namen else "  FEHLT ") + pflicht)
PY

cat "$AGENT" | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/wf-agent.json'"
cat "$WERKZEUGE" | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/wf-werkzeuge.json'"
cat "$KONFIG" | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/wf-konfig.json'"

ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  set -e
  docker cp /tmp/wf-agent.json n8n:/tmp/ >/dev/null
  docker cp /tmp/wf-werkzeuge.json n8n:/tmp/ >/dev/null
  docker cp /tmp/wf-konfig.json n8n:/tmp/ >/dev/null
  echo \"--- Werkzeuge importieren\"
  if ! docker exec -u node n8n n8n import:workflow --input=/tmp/wf-werkzeuge.json \
        --projectId=$PROJEKT > /tmp/import1.log 2>&1; then
    echo \"ABBRUCH: Werkzeuge fehlgeschlagen (alte Fassung bleibt aktiv):\"
    cat /tmp/import1.log; exit 1
  fi
  tail -2 /tmp/import1.log
  echo \"--- Agent importieren\"
  if ! docker exec -u node n8n n8n import:workflow --input=/tmp/wf-agent.json \
        --projectId=$PROJEKT > /tmp/import2.log 2>&1; then
    echo \"ABBRUCH: Agent fehlgeschlagen (alte Fassung bleibt aktiv):\"
    cat /tmp/import2.log; exit 1
  fi
  tail -2 /tmp/import2.log
  echo \"--- Konfiguration importieren\"
  if ! docker exec -u node n8n n8n import:workflow --input=/tmp/wf-konfig.json \
        --projectId=$PROJEKT > /tmp/import3.log 2>&1; then
    echo \"ABBRUCH: Konfiguration fehlgeschlagen (alte Fassung bleibt aktiv):\"
    cat /tmp/import3.log; exit 1
  fi
  tail -2 /tmp/import3.log
  echo \"--- schalten\"
  for W in RadioWerkzeug AzuraWerkzeug MeldungenWerkzeug RadioAgentBot Konfiguration; do
    docker exec -u node n8n n8n update:workflow --id=\$W --active=true 2>&1 | tail -1
  done
  docker restart n8n >/dev/null
  for i in \$(seq 1 40); do
    C=\$(curl -s -o /dev/null -w \"%{http_code}\" http://127.0.0.1:5678/healthz)
    [ \"\$C\" = \"200\" ] && break
    sleep 3
  done
  echo \"n8n Gesundheit: \$C\"
  for i in \$(seq 1 40); do
    W=\$(curl -s -o /dev/null -w \"%{http_code}\" -X POST http://127.0.0.1:5678/webhook/DEIN-WEBHOOK-PFAD \
        -H \"Content-Type: application/json\" -d \"{}\" 2>/dev/null || true)
    [ \"\$W\" != \"404\" ] && break
    sleep 3
  done
  echo \"Webhook: \$W\"
  docker logs --tail 60 n8n 2>&1 | grep -iE \"activated workflow|error\" | tail -8'"

echo "--- Ordner zuordnen"
bash "$(dirname "$0")/n8n-ordner-setzen.sh"
