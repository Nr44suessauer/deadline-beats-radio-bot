##!/bin/bash
# Cleans up the not anymore current, sender-related workflows from n8n (corrected version).
# 1) export each workflow individually and check the identifier in the file
# 2) remove lines from the n8n database (identifiers as simple arguments)
# 3) restart n8n and check the inventory
set -euo pipefail
CFG=~/.ssh/config
ZIEL=<dokuordner>/NACHBAU/workflows-aufgeraeumt
mkdir -p "$ZIEL"

PAARE=(
  "RadioTelegramBot|RadioTelegramBot-Wunschbot.json"
  "RadioTelegramBot-Archiv-2026-09-19|RadioTelegramBot-Archiv-2026-09-19.json"
  "iDfPikpAIqTO9XQ2|RadioTelegramBot-copy-v1.json"
  "bjFSfXGqpLg7AAXw|Radio-AI-Moderator.json"
  "da7f06de-0bcf-4fbe-8c8d-ad8927d3d509|RadioAgent-before-dem-Umbau.json"
  "7Vv3NSFsS7OZaBSd|RadioAgent-Zwischenstand-V2.json"
  "jt2IC4TVPTF1KDLp|RadioAgent-copy.json"
  "zxBICXCfUaMGhNmT|RadioAgent-copy2-V2.json"
  "RadioWerkzeugSuche|tool-Titel-suchen.json"
  "RadioWerkzeugSofort|tool-Sofort-play.json"
  "RadioWerkzeugDanach|tool-Danach-play.json"
  "RadioWerkzeugStatus|Tool-What-is-running.json"
  "RadioWerkzeugRichtung|Tool-Direction-search.json"
)

echo "--- secure and check"
IDS=""
for couple in "${PAARE[@]}"; do
  id="${couple%%|*}"; name="${couple##*|}"
  ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc 'docker exec -u node n8n n8n export:workflow --id=$id --output=/tmp/wf-$id.json >/dev/null 2>&1; docker exec n8n cat /tmp/wf-$id.json'" > "$ZIEL/$name"
  chmod 600 "$ZIEL/$name"
  python3 - "$ZIEL/$name" "$id" <<'PY'
import json, sys
path, erwartet = sys.argv[1], sys.argv[2]
d = json.load(open(path, encoding="utf-8"))
w = d[0] if isinstance(d, list) else d
found = w.get("id", "")
if found != erwartet:
    raise SystemExit(f"ERROR: {path} contains {found}, expected {erwartet}")
print(f" ok  {erwartet:45s} {w.get('name','?'):45s} {len(w.get('nodes',[]))} nodes")
PY
  IDS="$IDS$id"
done
echo "--- remove"
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  docker cp /tmp/n8n-weg.js n8n:/tmp/ >/dev/null
  docker exec -u node n8n node /tmp/n8n-weg.js $IDS
'"
echo "--- restart n8n"
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  docker restart n8n >/dev/null
  for i in \$(seq 1 40); do
    C=\$(curl -s -o /dev/null -w \"%{http_code}\" http://127.0.0.1:5678/healthz)
    [ \"\$C\" = \"200\" ] && break
    sleep 3
  done
  echo \"  Gesundheit: \$C\"
'"
echo "Fertig."
