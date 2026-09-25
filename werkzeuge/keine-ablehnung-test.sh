#!/usr/bin/env bash
# Prüft, dass Befehle nicht mehr abgelehnt werden.
set -u
S="$1"
WEBHOOK="http://127.0.0.1:5678/webhook/DEIN-WEBHOOK-PFAD?schluessel=$S"

schicke() {
  echo "════ $1"
  curl -s -m 90 -o /dev/null -w "   HTTP %{http_code}\n" -X POST "$WEBHOOK" \
    -H 'Content-Type: application/json' \
    -d "$(python3 -c "
import json,sys
print(json.dumps({'message': {'message_id': 1, 'chat': {'id': 1, 'type': 'private'},
                              'from': {'id': 1, 'first_name': 'Test'}, 'text': sys.argv[1]}}))" "$1")"
}

# Titel, der eben lief -> frueher abgelehnt
schicke "/wunsch American Idiot"
# Mehrdeutig -> soll trotzdem den besten Treffer spielen
schicke "/wunsch nirvana"
# Ausdrueckliche Suche -> Liste
schicke "/suche rammstein"
