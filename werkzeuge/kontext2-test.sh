#!/usr/bin/env bash
# Prueft die neue Deutung: mehrere Auftraege, Mengen, Bezug auf den Kontext.
# Aufruf: bash kontext2-test.sh <schluessel>
WEBHOOK=http://127.0.0.1:5678/webhook/DEIN-WEBHOOK-PFAD
SCHLUESSEL=${1:?Bitte den Testschluessel als Argument angeben}

sende() {
  echo "════════ $1"
  curl -s -m 120 -o /dev/null -w "  HTTP %{http_code}  (%{time_total}s)\n" \
    -X POST "$WEBHOOK" -H 'Content-Type: application/json' -d "$(python3 -c "
import json,sys
print(json.dumps({'schluessel': sys.argv[1],
                  'message': {'message_id': 1, 'chat': {'id': 1, 'type': 'private'},
                              'from': {'id': 1, 'first_name': 'Test'},
                              'text': sys.argv[2]}}))" "$SCHLUESSEL" "$1")"
}

echo "--- Schraegstrich-Befehle (ohne Modell)"
sende "/jetzt"
sende "/wunsch benzin"
echo
echo "--- Freier Text: mehrere Auftraege in einer Nachricht"
sende "spiele bitte sofort Benzin von Rammstein und danach mach Nirvana an"
sende "mach drei Lieder von Nirvana an"
sende "spiele mir mehrere Titel von den Ärzten"
echo
echo "--- Bezug auf das Laufende"
sende "davon haette ich gern noch zwei"
sende "was läuft gerade für ein Titel"
sende "spiele mal was ruhiges"
