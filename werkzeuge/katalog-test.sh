#!/usr/bin/env bash
# Prueft den Katalogdienst (Kontextsuche + Richtungsvorschlaege).
# Aufruf: bash katalog-test.sh [basisadresse]
DIENST=${1:-http://127.0.0.1:8881}

echo "=== Zustand"
curl -s "$DIENST/katalog/status"
echo

echo "=== Kontextsuche (Tippfehler, verhoerte Namen)"
for q in "bohemian rapsody" "rammstien benzene" "die artzte" "nivana smells like teen spirit" \
         "Ben Zim Rammstein" "hooray"; do
  echo "--- $q"
  curl -s -G --data-urlencode "q=$q" --data "anzahl=3" --data "min_punkte=45" "$DIENST/suche" \
    | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('    Stufe', d.get('stufe'), '| geprueft', d.get('geprueft'))
for t in d.get('treffer', []):
    print('    ', t['artist'], '-', t['title'], '(', t['length_text'], ')', t['punkteFuzzy'])
"
done

echo
echo "=== Richtungen"
for w in "was aus rock" "etwas ruhiges" "metal" "90er" "80er" "deutschrap" "was Hartes"; do
  echo "--- $w"
  curl -s -G --data-urlencode "wort=$w" --data "anzahl=3" "$DIENST/genre" \
    | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('    genutzt:', ', '.join(d.get('genutzt', []))[:80])
print('    Hinweise:', ' | '.join(d.get('hinweise', []))[:80])
print('    Gesamttreffer:', d.get('anzahl_gesamt'))
for t in d.get('treffer', []):
    print('    ', t['artist'], '-', t['title'], '(', t['length_text'], ')')
"
done

echo
echo "=== Wortlisten (Grundlage der Bot-Erkennung)"
curl -s "$DIENST/genre/liste" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('    Richtungen:', len(d['stichwoerter']), '| Hilfsworte:', len(d['hilfsworte']))
print('    Beispiele:', ', '.join(d['stichwoerter'][:12]))
"
curl -s "$DIENST/katalog/kuenstler?anzahl=10" | python3 -c "
import json, sys
print('    Kuenstler fuer die Spracherkennung:', ', '.join(json.load(sys.stdin)['namen']))
"
