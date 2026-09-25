#!/usr/bin/env python3
"""Retrieves a JS component (e.g. ANSWER_BUILD_JS) from a producer.

Call:  python3 js-fetch.py agent-wf-build.py ANSWER_BUILD_JS > /tmp/x.js
This allows checking individual code nodes without n8n (see answer-test.sh).
"""
import ast
import sys

if len(sys.argv) < 3:
    raise SystemExit(__doc__)

source = open(sys.argv[1], encoding="utf-8").read()
name = sys.argv[2]
for nodes in ast.parse(source).body:
    if isinstance(nodes, ast.Assign):
        if name in [z.id for z in nodes.targets if isinstance(z, ast.Name)]:
            sys.stdout.write(ast.literal_eval(nodes.value))
            break
else:
    raise SystemExit(f"{name} not found in {sys.argv[1]}")
