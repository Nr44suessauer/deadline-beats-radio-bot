#!/usr/bin/env bash
# Plays the version with central configuration: first the new workflow
# “Configuration”, then the three tool workflows, finally the bot.
#
# Call:  bash configuration-deploy.sh
# Before:  python3 werkzeuge/agent-wf-build.py   (writes the three files)
# + the access values from the environment (TG_TOKEN, AZ_KEY, NEWS_KEY)
#
# Nothing is deleted: existing workflows with the same identifiers will
# be replaced, everything else remains. The old version is available as a backup.
set -euo pipefail
cd "$(dirname "$0")"

CFG=~/.ssh/config
PROJEKT=YOUR-N8N-PROJECT-ID
KONFIG=/tmp/radio-konfiguration.json
TOOLS=/tmp/radio-werkzeuge.json
BOT=/tmp/radio-agent.json
ABLAEUFE="Configuration RadioWerkzeug AzuraWerkzeug MeldungenWerkzeug RadioAgentBot"

for D in "$KONFIG" "$TOOLS" "$BOT"; do
  [ -f "$D" ] || { echo "File missing: $D (run the generator first)"; exit 1; }
  if grep -q "<SECRET>" "$D"; then
    echo "CANCEL: $D contains mask marker <SECRET>."
    exit 1
  fi
done

echo "--- Build check"
python3 - "$KONFIG" "$TOOLS" "$BOT" <<'PY'
import json, sys
for path in sys.argv[1:]:
    d = json.load(open(path, encoding="utf-8"))
    for w in (d if isinstance(d, list) else [d]):
        names = [k["name"] for k in w["nodes"]]
        has = " ja" if "Configuration" in names else "nein"
        print(f" {w['name']:32s} {len(names):3d} nodes   Configuration: {has}")
PY

echo "--- Files to the container"
for PAAR in "$KONFIG:/tmp/wf-konfig.json" "$TOOLS:/tmp/wf-werkzeuge.json" "$BOT:/tmp/wf-bot.json"; do
  QUELLE=${PAAR%%:*}
  ZIEL=${PAAR##*:}
  cat "$QUELLE" | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > $ZIEL'"
done

ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  set -e
  for F in wf-konfig.json wf-werkzeuge.json wf-bot.json; do docker cp /tmp/\$F n8n:/tmp/ >/dev/null; done
  echo \"--- Configuration importieren (first)\"
  if ! docker exec -u node n8n n8n import:workflow --input=/tmp/wf-konfig.json --projectId=$PROJEKT > /tmp/i1.log 2>&1; then
    echo \"ABORT while configuring:\"; cat /tmp/i1.log; exit 1
  fi
  tail -1 /tmp/i1.log
  echo \"--- tools importieren\"
  if ! docker exec -u node n8n n8n import:workflow --input=/tmp/wf-werkzeuge.json --projectId=$PROJEKT > /tmp/i2.log 2>&1; then
    echo \"ABORT with the tools:\"; cat /tmp/i2.log; exit 1
  fi
  tail -1 /tmp/i2.log
  echo \"--- Bot importieren\"
  if ! docker exec -u node n8n n8n import:workflow --input=/tmp/wf-bot.json --projectId=$PROJEKT > /tmp/i3.log 2>&1; then
    echo \"ABORT with Bot:\"; cat /tmp/i3.log; exit 1
  fi
  tail -1 /tmp/i3.log
  echo \"--- einschalten\"
  for W in $ABLAEUFE; do
    docker exec -u node n8n n8n update:workflow --id=\$W --active=true 2>&1 | tail -1
  done
  echo \"--- Status\"
  docker exec -u node n8n n8n list:workflow 2>/dev/null | grep -E \"Configuration|RadioAgentBot|tool\" || true
'"
