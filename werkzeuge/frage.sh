#!/usr/bin/env bash
# Sendet eine Nachricht an den Testeingang des Bots (laeuft im n8n-Container).
# Aufruf: frage.sh "<text>" [chatId]
set -u
TEXT="$1"
CHAT="${2:-1}"
KENNUNG="$(date +%s)"
curl -s -m 180 -o /tmp/antwort-$KENNUNG.json -w "HTTP %{http_code} in %{time_total}s\n" \
  -X POST http://127.0.0.1:5678/webhook/DEIN-WEBHOOK-PFAD \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "
import json,sys
print(json.dumps({'schluessel': open('/tmp/.botschluessel').read().strip(),
  'message': {'message_id': 900, 'chat': {'id': int('$CHAT'), 'type': 'private'},
              'from': {'id': int('$CHAT'), 'first_name': 'Test'}, 'text': '''$TEXT'''}}))
")"
