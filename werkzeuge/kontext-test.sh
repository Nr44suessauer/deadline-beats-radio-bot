#!/usr/bin/env bash
# Prueft Kontextsuche und Richtungswuensche ueber den Test-Eingang.
# Aufruf: cat kontext-test.sh | ssh ... "pct exec 103 -- bash -s -- <schluessel>"
WEBHOOK=http://127.0.0.1:5678/webhook/DEIN-WEBHOOK-PFAD
SCHLUESSEL=${1:?Bitte den Testschluessel als Argument angeben}

sende() {   # sende <text> [chat]
  echo "════════ $1"
  curl -s -m 120 -X POST "$WEBHOOK" -H 'Content-Type: application/json' -d "$(python3 -c "
import json,sys
print(json.dumps({'schluessel': sys.argv[1],
                  'message': {'message_id': 1, 'chat': {'id': int(sys.argv[3]), 'type': 'private'},
                              'from': {'id': int(sys.argv[3]), 'first_name': 'Test'},
                              'text': sys.argv[2]}}))" "$SCHLUESSEL" "$1" "${2:-1}")" \
    | python3 -c "
import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    print('  (keine JSON-Antwort)'); raise SystemExit
if isinstance(d, dict) and 'antwort' in d:
    for z in str(d['antwort']).split('\n'):
        if z.strip(): print('  ', z)
else:
    print('  ', str(d)[:200])
"
}

echo "--- Kontextsuche (Tippfehler) ---"
sende "/wunsch bohemian rapsody"
sende "/wunsch rammstien benzene"
sende "/wunsch nivana smells like teen spirit"
sende "/wunsch die artzte"
echo
echo "--- Richtungswuensche ---"
sende "/wunsch was aus rock"
sende "/wunsch etwas ruhiges"
sende "/wunsch metal"
sende "/wunsch 90er"
sende "/wunsch deutschrap"
echo
echo "--- Beides gemischt: Titel, der wie eine Richtung klingt ---"
sende "/wunsch rock me amadeus"
sende "/wunsch hip hop hooray"
