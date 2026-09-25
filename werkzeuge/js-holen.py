#!/usr/bin/env python3
"""Holt einen JS-Baustein (z. B. ANTWORT_BAUEN_JS) aus einem Erzeuger.

Aufruf:  python3 js-holen.py agent-wf-bauen.py ANTWORT_BAUEN_JS > /tmp/x.js
Damit lassen sich einzelne Code-Knoten ohne n8n pruefen (siehe antwort-test.sh).
"""
import ast
import sys

if len(sys.argv) < 3:
    raise SystemExit(__doc__)

quelle = open(sys.argv[1], encoding="utf-8").read()
name = sys.argv[2]
for knoten in ast.parse(quelle).body:
    if isinstance(knoten, ast.Assign):
        if name in [z.id for z in knoten.targets if isinstance(z, ast.Name)]:
            sys.stdout.write(ast.literal_eval(knoten.value))
            break
else:
    raise SystemExit(f"{name} nicht gefunden in {sys.argv[1]}")
