#!/usr/bin/env bash
# Imports the patched agent version AND the tool workflows in n8n.
#
# Takes a finished import file (from agent-patch.sh) for the agent and the
# tool import file from the generator. Compare first:
#   python3 vergleich-agent.py <running> <rebuild>
#
# Call:  bash agent-deploy.sh <agent.json>
set -euo pipefail

CFG=~/.ssh/config
AGENT=${1:-/tmp/radio-agent-new.json}
TOOLS=/tmp/radio-werkzeuge-import.json
KONFIG=/tmp/radio-konfiguration.json
PROJEKT=YOUR-N8N-PROJECT-ID

[ -f "$AGENT" ] || { echo "File missing: $AGENT"; exit 1; }
[ -f "$TOOLS" ] || { echo "File missing: $TOOLS (run agent-patch.sh first)"; exit 1; }
[ -f "$KONFIG" ] || { echo "File missing: $KONFIG (first run agent-patch.sh)"; exit 1; }
for D in "$AGENT" "$TOOLS" "$KONFIG"; do
  if grep -q "<SECRET>" "$D"; then
    echo "CANCEL: $D contains mask marker <SECRET>."
    exit 1
  fi
done

echo "--- Check agent"
python3 - "$AGENT" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
w = d[0] if isinstance(d, list) else d
names = [k["name"] for k in w["nodes"]]
print(f" {len(names)} nodes, identifier {w.get('id')}")
for pflicht in ("Service type", "Service message", "Map message", "Tool messages",
                "Schedule messages"):
    print(("  ok   " if pflicht in names else "  FEHLT ") + pflicht)
PY

cat "$AGENT" | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/wf-agent.json'"
cat "$TOOLS" | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/wf-werkzeuge.json'"
cat "$KONFIG" | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/wf-konfig.json'"

ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  set -e
  docker cp /tmp/wf-agent.json n8n:/tmp/ >/dev/null
  docker cp /tmp/wf-werkzeuge.json n8n:/tmp/ >/dev/null
  docker cp /tmp/wf-konfig.json n8n:/tmp/ >/dev/null
  echo \"--- tools importieren\"
  if ! docker exec -u node n8n n8n import:workflow --input=/tmp/wf-werkzeuge.json \
        --projectId=$PROJEKT > /tmp/import1.log 2>&1; then
    echo \"ABORT: tools fehlgeschlagen (old version bleibt aktiv):\"
    cat /tmp/import1.log; exit 1
  fi
  tail -2 /tmp/import1.log
  echo \"--- Agent importieren\"
  if ! docker exec -u node n8n n8n import:workflow --input=/tmp/wf-agent.json \
        --projectId=$PROJEKT > /tmp/import2.log 2>&1; then
    echo \"ABORT: Agent fehlgeschlagen (old version bleibt aktiv):\"
    cat /tmp/import2.log; exit 1
  fi
  tail -2 /tmp/import2.log
  echo \"--- Configuration importieren\"
  if ! docker exec -u node n8n n8n import:workflow --input=/tmp/wf-konfig.json \
        --projectId=$PROJEKT > /tmp/import3.log 2>&1; then
    echo \"ABORT: Configuration fehlgeschlagen (old version bleibt aktiv):\"
    cat /tmp/import3.log; exit 1
  fi
  tail -2 /tmp/import3.log
  echo \"--- schalten\"
  for W in RadioWerkzeug AzuraWerkzeug MeldungenWerkzeug RadioAgentBot Configuration; do
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
    W=\$(curl -s -o /dev/null -w \"%{http_code}\" -X POST http://127.0.0.1:5678/webhook/YOUR-WEBHOOK-PATH \
        -H \"Content-Type: application/json\" -d \"{}\")
    [ \"\$W\" != \"404\" ] && break
    sleep 3
  done
  echo \"Webhook: \$W\"
  docker logs --tail 60 n8n 2>&1 | grep -iE \"activated workflow|error\" | tail -8'"
