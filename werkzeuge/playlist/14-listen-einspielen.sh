#!/usr/bin/env bash
# Spielt die gepatchte Fassung mit den Listen-Aufgaben in n8n ein.
# Voraussetzung: 13-listen-patchen.sh wurde gelaufen (/tmp/radio-agent-listen.json).
# Vorher sichern: bash 01-fassung-sichern.sh  (Archiv der laufenden Fassung)
# Aufruf:  bash 14-listen-einspielen.sh
set -euo pipefail

CFG=~/.ssh/config
DATEI=${1:-/tmp/radio-agent-listen.json}
ABLAUF=RadioAgentBot
PROJEKT=DEINE-N8N-PROJEKT-KENNUNG

[ -f "$DATEI" ] || { echo "Datei fehlt: $DATEI - erst 13-listen-patchen.sh laufen lassen"; exit 1; }
if grep -q "<GEHEIM>" "$DATEI"; then
  echo "ABBRUCH: die Datei enthaelt Maskenmerker <GEHEIM> - so nicht einspielen."
  exit 1
fi

echo "--- Datei pruefen"
python3 - "$DATEI" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
w = d[0] if isinstance(d, list) else d
namen = [k["name"] for k in w["nodes"]]
neu = [n for n in ("Listen Art", "Listen?", "Listen Dienst", "Listen Antwort", "Listen Senden") if n in namen]
print("  Knoten:", len(namen), "| Listen-Knoten:", len(neu), "| Kennung:", w.get("id"))
if len(neu) != 5:
    raise SystemExit("ABBRUCH: die Listen-Knoten fehlen")
PY

cat "$DATEI" | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/wf-neu.json'"

ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  docker cp /tmp/wf-neu.json n8n:/tmp/ >/dev/null
  if ! docker exec -u node n8n n8n import:workflow --input=/tmp/wf-neu.json \
        --projectId=$PROJEKT > /tmp/import.log 2>&1; then
    echo \"ABBRUCH: Import fehlgeschlagen, alte Fassung bleibt aktiv:\"
    cat /tmp/import.log
    exit 1
  fi
  tail -2 /tmp/import.log
  docker exec -u node n8n n8n update:workflow --id=$ABLAUF --active=true 2>&1 | tail -1
  docker restart n8n >/dev/null
  for i in \$(seq 1 40); do
    C=\$(curl -s -o /dev/null -w \"%{http_code}\" http://127.0.0.1:5678/healthz)
    [ \"\$C\" = \"200\" ] && break
    sleep 3
  done
  echo \"n8n Gesundheit: \$C\"
  for i in \$(seq 1 40); do
    W=\$(curl -s -o /dev/null -w \"%{http_code}\" -X POST http://127.0.0.1:5678/webhook/DEIN-WEBHOOK-PFAD \
        -H \"Content-Type: application/json\" -d \"{}\")
    [ \"\$W\" != \"404\" ] && break
    sleep 3
  done
  echo \"Webhook: \$W\"
  docker logs --tail 60 n8n 2>&1 | grep -iE \"activated workflow|error\" | tail -6'"
