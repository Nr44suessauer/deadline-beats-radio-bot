#!/usr/bin/env bash
# Rebuilds the bot process, patches the list tasks in and places the
# finished file in /tmp/radio-agent-listen.json. NOTHING is played back.
# Call:  bash 13-playlists-patch.sh
set -euo pipefail
cd "$(dirname "$0")"

CFG=~/.ssh/config
RUNNING=/tmp/radio-agent-running.json
ZIEL=/tmp/radio-agent-listen.json

echo "--- retrieve running version from n8n"
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  docker exec -u node n8n n8n export:workflow --id=RadioAgentBot --output=/tmp/running.json >/dev/null 2>&1
  docker exec n8n cat /tmp/running.json'" > "$RUNNING"
python3 -c "
import json
d = json.load(open('$RUNNING', encoding='utf-8'))
w = d[0] if isinstance(d, list) else d
print(' Nodes:', len(w['nodes']), '| Name:', w.get('name'))
"

# Identifier and key are in the current version - retrieve them from there so
# the rebuild carries the same access values.
export TG_TOKEN=$(python3 -c "
import re
t = open('$RUNNING', encoding='utf-8').read()
m = re.search(r'api\.telegram\.org/bot([A-Za-z0-9:_-]+)/', t)
print(m.group(1) if m else '')
")
export AZ_KEY=$(python3 -c "
import re
t = open('$RUNNING', encoding='utf-8').read()
m = re.search(r'[0-9a-f]{16}:[0-9a-f]{32}', t)
print(m.group(0) if m else '')
")
[ ${#TG_TOKEN} -gt 20 ] || { echo "ERROR: Telegram-Identifier not in the running version"; exit 1; }
[ ${#AZ_KEY} -gt 20 ] || { echo "ERROR: interface key not in the running version"; exit 1; }
echo " Identifier ${#TG_TOKEN} characters, key ${#AZ_KEY} characters"

echo "--- create rebuild"
python3 ../agent-wf-build.py >/dev/null

echo "--- compare (for viewing only)"
python3 12-rebuild-vergleich.py "$RUNNING" /tmp/radio-agent.json | sed 's/^/  /'

echo "--- patching"
python3 13-playlists-patch.py "$RUNNING" /tmp/radio-agent.json "$ZIEL"

echo
echo "Done. Play back with:  bash 14-listen-deploy.sh"
