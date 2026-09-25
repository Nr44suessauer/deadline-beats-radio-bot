#!/usr/bin/env bash
# Checks the catalog service (context search + direction suggestions).
# Call: bash catalog-test.sh [base address]
SERVICE=${1:-http://127.0.0.1:8881}

echo "=== State"
curl -s "$SERVICE/catalog/status"
echo

echo "=== Context search (typos, misheard names)"
for q in "bohemian rapsody" "rammstien benzene" "die artzte" "nivana smells like teen spirit" \
         "Ben Zim Rammstein" "hooray"; do
  echo "--- $q"
  curl -s -G --data-urlencode "q=$q" --data "count=3" --data "min_punkte=45" "$SERVICE/search" \
    | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('    Stage', d.get('stufe'), '| checked', d.get('checked'))
for t in d.get('hits', []):
    print('    ', t['artist'], '-', t['title'], '(', t['length_text'], ')', t['punkteFuzzy'])
"
done

echo
echo "=== Directions"
for w in "what about rock" "something quiet" "metal" "90s" "80s" "germanrap" "what heavy"; do
  echo "--- $w"
  curl -s -G --data-urlencode "word=$w" --data "count=3" "$SERVICE/genre" \
    | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(' used:', ', '.join(d.get('used', []))[:80])
print(' Notes:', ' | '.join(d.get('hints', []))[:80])
print(' Total hits:', d.get('anzahl_gesamt'))
for t in d.get('hits', []):
    print('    ', t['artist'], '-', t['title'], '(', t['length_text'], ')')
"
done

echo
echo "=== Word lists (basis for bot detection)"
curl -s "$SERVICE/genre/list" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(' Directions:', len(d['stichwoerter']), '| Helper words:', len(d['helpers']))
print(' Examples:', ', '.join(d['stichwoerter'][:12]))
"
curl -s "$SERVICE/catalog/artists?count=10" | python3 -c "
import json, sys
print(' Artists for speech recognition:', ', '.join(json.load(sys.stdin)['names']))
"
