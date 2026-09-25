#!/usr/bin/env bash
# Retrieves the pre-stage (SHORT_JS) from the producer and checks it without n8n.
# Call:  bash short-test.sh
set -euo pipefail
cd "$(dirname "$0")"

python3 - agent-wf-build.py > /tmp/short.js <<'PY'
import ast
import sys

source = open(sys.argv[1], encoding="utf-8").read()
for nodes in ast.parse(source).body:
    if isinstance(nodes, ast.Assign):
        if "SHORT_JS" in [z.id for z in nodes.targets if isinstance(z, ast.Name)]:
            print(ast.literal_eval(nodes.value))
            break
else:
    raise SystemExit("SHORT_JS not found")
PY

node short-test.js /tmp/short.js
