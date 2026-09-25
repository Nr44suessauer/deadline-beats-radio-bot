#!/usr/bin/env bash
# Vollstaendiger Test des Wunschbots ueber den Test-Eingang.
WEBHOOK=http://127.0.0.1:5678/webhook/DEIN-WEBHOOK-PFAD

sende() {   # sende <beschreibung> <json-rumpf>
  echo "════════ $1"
  curl -s -m 90 -o /dev/null -w "  HTTP %{http_code}  (%{time_total}s)\n" \
    -X POST "$WEBHOOK" -H 'Content-Type: application/json' -d "$2"
}

nachricht() {  # nachricht <text>
  sende "$1" "$(python3 -c "
import json,sys
print(json.dumps({'message': {'message_id': 1, 'chat': {'id': 1, 'type': 'private'},
                              'from': {'id': 1, 'first_name': 'Test'}, 'text': sys.argv[1]}}))" "$1")"
}

knopf() {   # knopf <callback_data>
  sende "Knopf $1" "$(python3 -c "
import json,sys
print(json.dumps({'callback_query': {'id': '1', 'from': {'id': 1, 'first_name': 'Test'},
                                     'data': sys.argv[1],
                                     'message': {'message_id': 2, 'chat': {'id': 1, 'type': 'private'}}}}))" "$1")"
}

nachricht "/hilfe"
nachricht "/jetzt"
nachricht "/letzte"
nachricht "/wunsch benzin"
nachricht "/suche rammstein"
knopf "w1"
knopf "w9"
nachricht "/wunsch zzqqxxyy"
