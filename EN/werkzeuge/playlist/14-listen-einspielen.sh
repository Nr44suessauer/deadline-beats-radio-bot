#!/usr/bin/env bash
# Plays the patched version with the list tasks in n8n.
# Prerequisite: 13-listen-patchen.sh has been run (/tmp/radio-agent-listen.json).
# Backup first: bash 01-version-sichern.sh (Archive of the running version)
# Call: bash 14-listen-deploy.sh
set -euo pipefail

CFG=~/.ssh/config
FILE=${1:-/tmp/radio-agent-listen.json}
ABLAUF=RadioAgentBot
PROJEKT=YOUR-N8N-PROJECT-ID

[ -f "$FILE" ] || { echo "File missing: $FILE - run 13-listen-patchen.sh first"; exit 1; }
if grep -q "<SECRET>" "$FILE"; then
  echo "ABORT: the file contains mask markers <GEHEIM> - do not deploy like this."
  exit 1
fi

echo "--- Check file"
python3 - "$FILE" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
w = d[0] if isinstance(d, list) else d
names = [k["name"] for k in w["nodes"]]
new = [n for n in ("List Type", "Lists?", "List Service", "List Response", "List Send") if n in names]
print(" Nodes:", len(names), "| List Node:", len(new), "| Identifier:", w.get("id"))
if len(new) != 5:
    raise SystemExit("ABORT: the list nodes are missing")
PY

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
  echo \"n8n Gesundheit: \$C\"
  for i in \$(seq 1 40); do
    W=\$(curl -s -o /dev/null -w \"%{http_code}\" -X POST http://127.0.0.1:5678/webhook/YOUR-WEBHOOK-PATH \
        -H \"Content-Type: application/json\" -d \"{}\")
    [ \"\$W\" != \"404\" ] && break
    sleep 3
  done
  echo \"Webhook: \$W\"
  docker logs --tail 60 n8n 2>&1 | grep -iE \"activated workflow|error\" | tail -6'"
