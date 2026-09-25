#!/usr/bin/env bash
# Holt EINGABE_JS und die Weiche (DIENST_ART_JS) aus dem Erzeuger und prueft den
# ganzen Weg vom Telegram-Update bis zur Entscheidung - ohne n8n.
#
# Die Weiche leitet an die Module im Dienst radio-tts weiter: playlist.py
# (Wiedergabelisten) und meldungen.py (Postfach des Suchbots, Ansagen).
# Aufruf:  bash 11-dienst-art-test.sh
set -euo pipefail
cd "$(dirname "$0")"
QUELLE=../agent-wf-bauen.py

hole() {   # hole <Name der Konstanten> <Zieldatei>
  python3 - "$QUELLE" "$1" > "$2" <<'PY'
import ast
import sys

quelle = open(sys.argv[1], encoding="utf-8").read()
gesucht = sys.argv[2]
for knoten in ast.parse(quelle).body:
    if isinstance(knoten, ast.Assign):
        if gesucht in [z.id for z in knoten.targets if isinstance(z, ast.Name)]:
            print(ast.literal_eval(knoten.value))
            break
else:
    raise SystemExit(f"{gesucht} nicht gefunden")
PY
}

hole EINGABE_JS /tmp/eingabe.js
hole DIENST_ART_JS /tmp/dienst-art.js

node 11-dienst-art-test.js /tmp/eingabe.js /tmp/dienst-art.js
