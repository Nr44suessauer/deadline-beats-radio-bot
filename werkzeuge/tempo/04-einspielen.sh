#!/bin/bash
# Spielt den gepatchten Radio-Ablauf in n8n ein und startet n8n neu.
# Aufruf:  bash 04-einspielen.sh <datei.json> <Ablauf-Kennung>
set -euo pipefail

CFG=~/.ssh/config
DATEI=${1:-/tmp/radio-agent-neu.json}
ABLAUF=${2:-RadioAgentBot}
PROJEKT=DEINE-N8N-PROJEKT-KENNUNG

[ -f "$DATEI" ] || { echo "Datei fehlt: $DATEI"; exit 1; }

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
  echo \"n8n Gesundheit: \$C\"'"
