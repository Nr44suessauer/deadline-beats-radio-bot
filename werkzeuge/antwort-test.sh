#!/usr/bin/env bash
# Prueft die Knoten, die das Ergebnis festhalten und die Antwort bauen:
#   - eine leere Nachfass-Antwort darf eine brauchbare Ausgabe nicht loeschen
#     (genau das hat am 2026-09-20 die Auswahlliste verschluckt)
#   - eine Rueckfrage wird gezeigt und mit Knoepfen versehen, nicht "nachgefasst"
# Aufruf:  bash antwort-test.sh
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p /tmp/js
for N in ERGEBNIS_SAMMELN_JS ERSATZ_ANTWORT_JS NACHTRAG_SAMMELN_JS PRUEFUNG_LESEN_JS ANTWORT_BAUEN_JS; do
  python3 js-holen.py agent-wf-bauen.py "$N" > "/tmp/js/$N.js"
done

node antwort-test.js
