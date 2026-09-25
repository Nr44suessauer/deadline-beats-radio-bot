#!/usr/bin/env bash
# Generates ANORDNUNG.md: an overview of the character surface of all four processes.
# Fetches the running versions from n8n, checks them and writes the table.
#
# Call:  bash anordnung-doku.sh
set -euo pipefail
cd "$(dirname "$0")"

CFG=~/.ssh/config
TMP=/tmp/anordnung
mkdir -p "$TMP"

fetch() {   # fetch <Workflow-Id> <Target-file>
  ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
    docker exec -u node n8n n8n export:workflow --id=$1 --output=/tmp/w.json >/dev/null 2>&1
    docker exec n8n cat /tmp/w.json'" > "$2"
}

echo "--- fetch running processes"
fetch RadioAgentBot "$TMP/agent.json"
fetch RadioWerkzeug "$TMP/werkzeug-radio.json"
fetch AzuraWerkzeug "$TMP/werkzeug-azura.json"
fetch MeldungenWerkzeug "$TMP/werkzeug-news.json"
# Archive of the first version: not in the construction tool, but with frame (archiv-frames.py)
fetch bjFSfXGqpLg7AAXw "$TMP/archiv-moderator.json"

echo "--- check character surface"
python3 anordnung-check.py "$TMP/agent.json" "$TMP/werkzeug-radio.json" \
  "$TMP/werkzeug-azura.json" "$TMP/werkzeug-news.json" "$TMP/archiv-moderator.json"

echo "--- write overview"
{
  cat <<'KOPF'
# Character surface of the processes (generated)

This file is **generated**, not maintained by hand: `bash anordnung-doku.sh`
fetches the running workflows from n8n, checks the canvas and writes the
node lists. It shows what is on the canvas — which frame has which
and what note stands under each node.

Why this matters: the frame is **computed from the positions**
(`werkzeuge/agent-wf-build.py`, tables `AREAS`). If a node lies outside
its frame or two frames overlap, `anordnung-check.py` reports
a finding. The goal is **0 findings**.

| check | meaning |
| --- | --- |
| node without frame | it lands somewhere without explanation |
| node in two frames | the areas are cut wrong |
| sticks out of the frame | the canvas is neatly askew |
| frames overlap | the areas lie on top of each other |
| node without note | the label is missing (every node must have one) |

As of: 2026-09-24 (version 19). Regenerate: `bash anordnung-doku.sh`.

KOPF
  python3 anordnung-uebersicht.py "$TMP/agent.json" "$TMP/werkzeug-radio.json" \
    "$TMP/werkzeug-azura.json" "$TMP/werkzeug-news.json" \
    "$TMP/archiv-moderator.json"
} > ../ANHANG/ANORDNUNG.md

echo "written: ANHANG/ANORDNUNG.md"
wc -l ANORDNUNG.md
