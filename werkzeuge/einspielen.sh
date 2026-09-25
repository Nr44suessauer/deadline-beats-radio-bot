#!/usr/bin/env bash
# Spielt den Bot-Arbeitsablauf ein und wartet, bis Webhook und Zugang stehen.
# Aufruf: einspielen.sh
set -eu
CFG=~/.ssh/config
SCHLUESSEL=$(cat <dokuordner>/NACHBAU/zugangsdaten/bot-test-schluessel.txt)
# Betreiberliste: DEINE-CHAT-ID ist der echte Betreiber, 1 ist die Testkennung.
IDS="${*:-1 DEINE-CHAT-ID}"

cat /tmp/radio-telegram-import.json | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/x.json'"
cat /tmp/daten-setzen.py | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/daten-setzen.py'"

ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  docker cp /tmp/x.json n8n:/tmp/ >/dev/null
  docker exec -u node n8n n8n import:workflow --input=/tmp/x.json --projectId=DEINE-N8N-PROJEKT-KENNUNG 2>&1 | tail -1
  docker exec -u node n8n n8n update:workflow --id=RadioTelegramBot --active=true >/dev/null
  docker stop n8n >/dev/null
  python3 /tmp/daten-setzen.py \"'"$SCHLUESSEL"'\" $IDS
  docker start n8n >/dev/null
  for i in \$(seq 1 40); do
    C=\$(curl -s -o /dev/null -w \"%{http_code}\" http://127.0.0.1:5678/healthz); [ \"\$C\" = \"200\" ] && break; sleep 3
  done
  # Der Webhook erscheint erst einige Sekunden nach dem Gesundheitstest.
  for i in \$(seq 1 40); do
    W=\$(curl -s -o /dev/null -w \"%{http_code}\" -X POST http://127.0.0.1:5678/webhook/DEIN-WEBHOOK-PFAD \
        -H \"Content-Type: application/json\" -d \"{}\")
    [ \"\$W\" != \"404\" ] && break; sleep 3
  done
  echo \"n8n: \$C | Webhook: \$W\"'"
