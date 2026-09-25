#!/usr/bin/env bash
# Drueckt einen Knopf im Chat (callback_query). Aufruf: knopf.sh <daten> [chatId]
set -u
DATEN="$1"; CHAT="${2:-1}"
curl -s -m 120 -o /dev/null -w "HTTP %{http_code} in %{time_total}s\n" \
  -X POST http://127.0.0.1:5678/webhook/DEIN-WEBHOOK-PFAD -H "Content-Type: application/json" \
  -d "$(python3 -c "
import json
print(json.dumps({'schluessel': open('/tmp/.botschluessel').read().strip(),
  'callback_query': {'id': '12345', 'data': '''$DATEN''',
    'from': {'id': int('$CHAT'), 'first_name': 'Test'},
    'message': {'message_id': 901, 'chat': {'id': int('$CHAT'), 'type': 'private'}}}}))
")"
