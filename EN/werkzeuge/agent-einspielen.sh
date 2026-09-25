#!/usr/bin/env bash
# Installs the agent and its tools.
# - creates the Ollama credentials (once only)
# - imports the 5 tool workflows and the agent
# - assigns everything to the project and the folder “Radio”
# - activates the agent, switches off the old wishbot (both use the same bot)
# - sets test key and operator list
# Call: agent-deploy.sh [chatIds...]      (default: only YOUR-CHAT-ID)
set -eu
CFG=~/.ssh/config
KEY=$(cat <dokuordner>/bot-test-key.txt)
IDS="${*:-YOUR-CHAT-ID}"

# First create the workflows, then build the import files from them -
# import-agent-vorbereiten.py only reads /tmp/radio-*.json.
python3 agent-wf-build.py
python3 import-agent-vorbereiten.py

cat > /tmp/ollama-cred.json <<'JSON'
[{"id": "YOUR-OLLAMA-CREDENTIAL-ID", "name": "Ollama (OpenAI interface)", "type": "openAiApi",
  "data": {"apiKey": "ollama", "url": "http://192.168.178.187:11434/v1"}}]
JSON

# The process in the container is deliberately kept as a separate script - this keeps
# the quotation marks readable when forwarding via ssh.
cat > /tmp/agent-remote.sh <<'REMOTE'
#!/usr/bin/env bash
set -eu
KEY="$1"; shift
IDS="$*"
cd /tmp

docker cp /tmp/radio-werkzeuge-import.json n8n:/tmp/ >/dev/null
docker cp /tmp/radio-agent-import.json n8n:/tmp/ >/dev/null
docker cp /tmp/ollama-cred.json n8n:/tmp/ >/dev/null
docker cp /tmp/agent-nachbereiten.py n8n:/tmp/ >/dev/null

# Credentials first - the CLI command needs a running container.
echo "--- Credentials ---"
docker exec -u node n8n n8n import:credentials --input=/tmp/ollama-cred.json 2>&1 | tail -2
# Attention: n8n reports structural errors (e.g. a connection to a non-
# existing node) only in the log and exits with Exit 1. Without this
# check, the old version continues silently.
importieren() {   # importieren <file> <description>
  if docker exec -u node n8n n8n import:workflow --input="$1" \
       --projectId=YOUR-N8N-PROJECT-ID > /tmp/import.log 2>&1; then
    tail -2 /tmp/import.log
  else
    echo "ABORT: Import of $2 failed (old version remains active):"
    cat /tmp/import.log
    exit 1
  fi
}
echo "--- Tools ---"
importieren /tmp/radio-werkzeuge-import.json "tool-Ablaeufe"
echo "--- Agent ---"
importieren /tmp/radio-agent-import.json "Agent"

# Activation/switching is done via the official command: n8n 2.x handles
# `active` together with the published version (activeVersionId); writing to
# the active column alone will be overwritten again on the next start.
#
# Important: the tool workflow MUST be active - n8n rejects calling
# a sub-workflow otherwise with “Workflow is not active and cannot be
# executed.“ (the agent then only reports ”There was an error“).
echo "--- Switching ---"
docker exec -u node n8n n8n update:workflow --id=RadioTelegramBot --active=false 2>&1 | tail -1
for W in RadioWerkzeug AzuraWerkzeug MeldungenWerkzeug RadioAgentBot; do
  docker exec -u node n8n n8n update:workflow --id=$W --active=true 2>&1 | tail -1
done

docker stop n8n >/dev/null
python3 /tmp/agent-nachbereiten.py "$KEY" $IDS
docker start n8n >/dev/null
for i in $(seq 1 40); do
  C=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5678/healthz); [ "$C" = "200" ] && break; sleep 3
done
for i in $(seq 1 40); do
  W=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:5678/webhook/YOUR-WEBHOOK-PATH \
      -H "Content-Type: application/json" -d "{}")
  [ "$W" != "404" ] && break; sleep 3
done
echo "n8n: $C | Webhook: $W"
docker logs --tail 40 n8n 2>&1 | grep -iE "activated workflow|error" | tail -6
REMOTE

for file in /tmp/radio-werkzeuge-import.json /tmp/radio-agent-import.json /tmp/ollama-cred.json \
             agent-nachbereiten.py /tmp/agent-remote.sh; do
  cat "$file" | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/$(basename "$file")'"
done

ssh -F "$CFG" ai-server "pct exec 103 -- bash /tmp/agent-remote.sh '$KEY' $IDS"
