#!/usr/bin/env bash
# Holt die Vorschaltstufe (KURZ_JS) aus dem Erzeuger und prueft sie ohne n8n.
# Aufruf:  bash kurz-test.sh
set -euo pipefail
cd "$(dirname "$0")"

python3 - agent-wf-bauen.py > /tmp/kurz.js <<'PY'
import ast
import sys

quelle = open(sys.argv[1], encoding="utf-8").read()
for knoten in ast.parse(quelle).body:
    if isinstance(knoten, ast.Assign):
        if "KURZ_JS" in [z.id for z in knoten.targets if isinstance(z, ast.Name)]:
            print(ast.literal_eval(knoten.value))
            break
else:
    raise SystemExit("KURZ_JS nicht gefunden")
PY

node kurz-test.js /tmp/kurz.js
