##!/bin/bash
# Imports the patched radio workflow into n8n and restarts n8n.
# Call:  bash 04-deploy.sh <file.json> <workflow-id>
set -euo pipefail

CFG=~/.ssh/config
FILE=${1:-/tmp/radio-agent-new.json}
ABLAUF=${2:-RadioAgentBot}
PROJEKT=YOUR-N8N-PROJECT-ID

[ -f "$FILE" ] || { echo "File missing: $FILE"; exit 1; }

cat "$FILE" | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/wf-new.json'"

ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  docker cp /tmp/wf-new.json n8n:/tmp/ >/dev/null
  if ! docker exec -u node n8n n8n import:workflow --input=/tmp/wf-new.json \
        --projectId=$PROJEKT > /tmp/import.log 2>&1; then
    echo \"ABORT: Import fehlgeschlagen, old version bleibt aktiv:\"
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
  echo \"n8n Health: \$C\"’"
