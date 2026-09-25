#!/usr/bin/env bash
# Retrieves the running version, rebuilds it, patches the changes in and places the
# result in /tmp/radio-agent-new.json. NOTHING is deployed.
#
# Call:  bash agent-patchen.sh [“--new A,B --content C --rename ‘X=Y’”]
# Without specifications all additional nodes in the rebuild are taken over.
#
# Backup first:  bash version-sichern.sh radio-vX-<datum>-<kurzname>
# Then deploy: bash agent-deploy-only.sh /tmp/radio-agent-new.json
set -euo pipefail
cd "$(dirname "$0")"

CFG=~/.ssh/config
RUNNING=/tmp/radio-agent-running.json
ZIEL=/tmp/radio-agent-new.json
RADIO=<dokuordner>

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

# Access values from the running version, so that the rebuild carries the same.
# Since the refactoring to “Configuration - all values” (22.09.2026) tokens and
# interface keys are NO LONGER in the agent, but in the configuration process
# -> search both files.
CONFIG_RUNNING=/tmp/radio-konfig-running.json
export CONFIG_RUNNING
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  docker exec -u node n8n n8n export:workflow --id=Configuration --output=/tmp/konfig-running.json >/dev/null 2>&1
  docker exec n8n cat /tmp/konfig-running.json'" > "$CONFIG_RUNNING"
export TG_TOKEN=$(python3 -c "
import re
t = open('$RUNNING', encoding='utf-8').read() + open('$CONFIG_RUNNING', encoding='utf-8').read()
m = re.search(r'[0-9]{6,12}:[A-Za-z0-9_-]{33,}', t)
print(m.group(0) if m else '')")
export AZ_KEY=$(python3 -c "
import re
t = open('$RUNNING', encoding='utf-8').read() + open('$CONFIG_RUNNING', encoding='utf-8').read()
m = re.search(r'[0-9a-f]{16}:[0-9a-f]{32}', t)
print(m.group(0) if m else '')")
export NEWS_KEY=$(cat "$RADIO/news-key.txt" 2>/dev/null || echo "")
[ ${#NEWS_KEY} -gt 10 ] || { echo "ERROR: news-key.txt missing"; exit 1; }
[ ${#TG_TOKEN} -gt 30 ] || { echo "ERROR: Telegram-Identifier not found (Agent + Configuration checked)"; exit 1; }
[ ${#AZ_KEY} -gt 40 ] || { echo "ERROR: interface key not found (Agent + Configuration checked)"; exit 1; }
echo " Identifiers loaded (Telegram ${#TG_TOKEN}, Interface ${#AZ_KEY}, Messages ${#NEWS_KEY} characters)"

echo "--- create rebuild"
python3 agent-wf-build.py

echo "--- German labeling (umlauts instead of ae/oe/ue)"
python3 german-texts.py --anwenden --rename-file /tmp/rename.txt \
  /tmp/radio-agent.json /tmp/radio-werkzeuge.json /tmp/radio-konfiguration.json

# Attention: the import files AFTER the text revision are built - otherwise the
# tool processes won’t get the umlauts (on 2026-09-24: Agent yes,
# but the three tools continued with “Execute?” on the server).
python3 import-agent-vorbereiten.py >/dev/null

echo "--- patching"
UMB=$(cat /tmp/rename.txt 2>/dev/null || true)
python3 agent-patchen.py "$RUNNING" /tmp/radio-agent.json "$ZIEL" --rename "$UMB" "$@"

echo
echo "Done. Deploy with:  bash agent-deploy-only.sh $ZIEL"
