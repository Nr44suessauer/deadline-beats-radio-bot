#!/usr/bin/env bash
# Presses a button in the chat (callback_query). Call: knopf.sh <daten> [chatId]
set -u
DATEN="$1"; CHAT="${2:-1}"
curl -s -m 120 -o /dev/null -w "HTTP %{http_code} in %{time_total}s\n" \
  -X POST http://127.0.0.1:5678/webhook/YOUR-WEBHOOK-PATH -H "Content-Type: application/json" \
  -d "$(python3 -c "
import json
print(json.dumps({'key': open('/tmp/.botkey').read().strip(),
  'callback_query': {'id': '12345', 'data': '''$DATEN''',
    'from': {'id': int('$CHAT'), 'first_name': 'Test'},
    'message': {'message_id': 901, 'chat': {'id': int('$CHAT'), 'type': 'private'}}}}))
")"
