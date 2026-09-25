#!/bin/bash
# Prueft den Suchknoten des Bots mit echten Daten (ohne n8n, ohne Sendebetrieb).
# Aufruf:  bash 09-suchknoten-test.sh ["Suchbegriff" ...]
set -euo pipefail

HIER=$(dirname "$(readlink -f "$0")")
SSH="ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 root@192.168.178.163"

# Schnittstellenschluessel des Senders holen (bleibt in der Umgebung, nicht in der Ablage)
AZ_KEY=$($SSH 'pct exec 106 -- docker exec azuracast cat /var/azuracast/api_key.txt' | tr -d '[:space:]')
export AZ_KEY

# Code des Suchknotens aus dem ausgerollten Ablauf
python3 - "$HIER/wf-radio-neu.json" "$HIER/.treffer-code.js" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))[0]
for n in d["nodes"]:
    if n["name"] == "Treffer aufbereiten":
        open(sys.argv[2], "w", encoding="utf-8").write(n["parameters"]["jsCode"])
        break
else:
    raise SystemExit("Knoten 'Treffer aufbereiten' nicht gefunden")
PY

BEGRIFFE=("$@")
if [ ${#BEGRIFFE[@]} -eq 0 ]; then
  BEGRIFFE=("About A Girl Nirvana" "Roseland Ballroom" "Benzin Rammstein" "Juliet Modern Talking")
fi

node "$HIER/09-suchknoten-test.js" "$HIER/.treffer-code.js" "${BEGRIFFE[@]}"
rm -f "$HIER/.treffer-code.js"
