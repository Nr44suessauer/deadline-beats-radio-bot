#!/usr/bin/env bash
# Fetches INPUT_JS and the switch (SERVICE_TYPE_JS) from the producer and checks the
# entire path from the Telegram update to the decision - without n8n.
#
# The switch routes to the modules in the radio-tts service: playlist.py
# (playlists) and news.py (mailbox of the search bot, announcements).
# Call:  bash 11-service-type-test.sh
set -euo pipefail
cd "$(dirname "$0")"
QUELLE=../agent-wf-build.py

hole() {   # fetch <name of the constant> <target file>
  python3 - "$QUELLE" "$1" > "$2" <<'PY'
import ast
import sys

source = open(sys.argv[1], encoding="utf-8").read()
gesucht = sys.argv[2]
for nodes in ast.parse(source).body:
    if isinstance(nodes, ast.Assign):
        if gesucht in [z.id for z in nodes.targets if isinstance(z, ast.Name)]:
            print(ast.literal_eval(nodes.value))
            break
else:
    raise SystemExit(f"{gesucht} not found")
PY
}

hole INPUT_JS /tmp/eingabe.js
hole SERVICE_TYPE_JS /tmp/service-type.js

node 11-service-type-test.js /tmp/eingabe.js /tmp/service-type.js
