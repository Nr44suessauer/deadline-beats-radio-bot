##!/bin/bash
# Checks the bot’s search node with real data (without n8n, without sending operation).
# Call:  bash 09-suchknoten-test.sh [“Search term” ...]
set -euo pipefail

HIER=$(dirname "$(readlink -f"$0")")
SSH="ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 root@192.168.178.163"

# Retrieve the sender’s interface key (remains in the environment, not in the storage)
AZ_KEY=$($SSH 'pct exec 106 -- docker exec azuracast cat /var/azuracast/api_key.txt' | tr -d '[:space:]')
export AZ_KEY

# Code of the search node from the rolled-out process
python3 - "$HIER/wf-radio-new.json" "$HIER/.hits-code.js" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))[0]
for n in d["nodes"]:
    if n["name"] == "Prepare hits":
        open(sys.argv[2], "w", encoding="utf-8").write(n["parameters"]["jsCode"])
        break
else:
    raise SystemExit("Node ‘Prepare hits’ not found")
PY

BEGRIFFE=("$@")
if [ ${#BEGRIFFE[@]} -eq 0 ]; then
  BEGRIFFE=("About A Girl Nirvana" "Roseland Ballroom" "Benzin Rammstein" "Juliet Modern Talking")
fi

node "$HIER/09-suchknoten-test.js" "$HIER/.hits-code.js" "${BEGRIFFE[@]}"
rm -f "$HIER/.hits-code.js"
