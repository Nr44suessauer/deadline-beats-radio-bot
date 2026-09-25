#!/usr/bin/env bash
# Plays the bot workflow and waits until webhook and access are available.
# Call: deploy.sh
set -eu
CFG=~/.ssh/config
KEY=$(cat <dokuordner>/bot-test-key.txt)
# Operator list: YOUR-CHAT-ID is the real operator, 1 is the test identifier.
IDS="${*:-1 YOUR-CHAT-ID}"

cat /tmp/radio-telegram-import.json | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/x.json'"
cat /tmp/data-setzen.py | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/data-setzen.py'"

ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  docker cp /tmp/x.json n8n:/tmp/ >/dev/null
  docker exec -u node n8n n8n import:workflow --input=/tmp/x.json --projectId=YOUR-N8N-PROJECT-ID 2>&1 | tail -1
  docker exec -u node n8n n8n update:workflow --id=RadioTelegramBot --active=true >/dev/null
  docker stop n8n >/dev/null
  python3 /tmp/data-setzen.py \"'"$KEY"'\" $IDS
  docker start n8n >/dev/null
  for i in \$(seq 1 40); do
    C=\$(curl -s -o /dev/null -w \"%{http_code}\" http://127.0.0.1:5678/healthz); [ \"\$C\" = \"200\" ] && break; sleep 3
  done
  # The webhook appears only some seconds after the health check.
  for i in \$(seq 1 40); do
    W=\$(curl -s -o /dev/null -w \"%{http_code}\" -X POST http://127.0.0.1:5678/webhook/YOUR-WEBHOOK-PATH \
        -H \"Content-Type: application/json\" -d \"{}\")
    [ \"\$W\" != \"404\" ] && break; sleep 3
  done
  echo \"n8n: \$C | Webhook: \$W\"'"
