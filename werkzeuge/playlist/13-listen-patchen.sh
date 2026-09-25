#!/usr/bin/env bash
# Baut den Bot-Ablauf neu, patcht die Listen-Aufgaben hinein und legt die
# fertige Datei nach /tmp/radio-agent-listen.json. Es wird NICHTS eingespielt.
# Aufruf:  bash 13-listen-patchen.sh
set -euo pipefail
cd "$(dirname "$0")"

CFG=~/.ssh/config
LAUFEND=/tmp/radio-agent-laufend.json
ZIEL=/tmp/radio-agent-listen.json

echo "--- laufende Fassung aus n8n holen"
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  docker exec -u node n8n n8n export:workflow --id=RadioAgentBot --output=/tmp/laufend.json >/dev/null 2>&1
  docker exec n8n cat /tmp/laufend.json'" > "$LAUFEND"
python3 -c "
import json
d = json.load(open('$LAUFEND', encoding='utf-8'))
w = d[0] if isinstance(d, list) else d
print('  Knoten:', len(w['nodes']), '| Name:', w.get('name'))
"

# Kennung und Schluessel stehen in der laufenden Fassung - von dort holen, damit
# der Neubau dieselben Zugangswerte traegt.
export TG_TOKEN=$(python3 -c "
import re
t = open('$LAUFEND', encoding='utf-8').read()
m = re.search(r'api\.telegram\.org/bot([A-Za-z0-9:_-]+)/', t)
print(m.group(1) if m else '')
")
export AZ_KEY=$(python3 -c "
import re
t = open('$LAUFEND', encoding='utf-8').read()
m = re.search(r'[0-9a-f]{16}:[0-9a-f]{32}', t)
print(m.group(0) if m else '')
")
[ ${#TG_TOKEN} -gt 20 ] || { echo "FEHLER: Telegram-Kennung nicht in der laufenden Fassung"; exit 1; }
[ ${#AZ_KEY} -gt 20 ] || { echo "FEHLER: Schnittstellenschluessel nicht in der laufenden Fassung"; exit 1; }
echo "  Kennung ${#TG_TOKEN} Zeichen, Schluessel ${#AZ_KEY} Zeichen"

echo "--- Neubau erzeugen"
python3 ../agent-wf-bauen.py >/dev/null

echo "--- vergleichen (nur zur Ansicht)"
python3 12-neubau-vergleich.py "$LAUFEND" /tmp/radio-agent.json | sed 's/^/  /'

echo "--- patchen"
python3 13-listen-patchen.py "$LAUFEND" /tmp/radio-agent.json "$ZIEL"

echo
echo "Fertig. Einspielen mit:  bash 14-listen-einspielen.sh"
