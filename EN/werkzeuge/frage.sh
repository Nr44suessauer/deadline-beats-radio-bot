#!/usr/bin/env bash
# Sends a message to the test input of the bot (runs in the n8n-container).
# Call: question.sh “<text>” [chatId]
set -u
TEXT="$1"
CHAT="${2:-1}"
KENNUNG="$(date +%s)"
curl -s -m 180 -o /tmp/answer-$KENNUNG.json -w "HTTP %{http_code} in %{time_total}s\n" \
  -X POST http://127.0.0.1:5678/webhook/YOUR-WEBHOOK-PATH \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "
import json,sys
print(json.dumps({'key': open('/tmp/.botkey').read().strip(),
  'message': {'message_id': 900, 'chat': {'id': int('$CHAT'), 'type': 'private'},
              'from': {'id': int('$CHAT'), 'first_name': 'Test'}, 'text': '''$TEXT'''}}))
")"
