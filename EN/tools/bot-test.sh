#!/usr/bin/env bash
# Full test of the request bot via the test entry.
WEBHOOK=http://127.0.0.1:5678/webhook/YOUR-WEBHOOK-PATH

send() {   # send <description> <json body>
  echo "════════ $1"
  curl -s -m 90 -o /dev/null -w "  HTTP %{http_code}  (%{time_total}s)\n" \
    -X POST "$WEBHOOK" -H 'Content-Type: application/json' -d "$2"
}

message() {  # message <text>
  send "$1" "$(python3 -c "
import json,sys
print(json.dumps({'message': {'message_id': 1, 'chat': {'id': 1, 'type': 'private'},
                              'from': {'id': 1, 'first_name': 'Test'}, 'text': sys.argv[1]}}))" "$1")"
}

button() {   # button <callback_data>
  send "Button $1" "$(python3 -c "
import json,sys
print(json.dumps({'callback_query': {'id': '1', 'from': {'id': 1, 'first_name': 'Test'},
                                     'data': sys.argv[1],
                                     'message': {'message_id': 2, 'chat': {'id': 1, 'type': 'private'}}}}))" "$1")"
}

message "/help"
message "/now"
message "/last"
message "/wish benzin"
message "/search rammstein"
button "w1"
button "w9"
message "/wish zzqqxxyy"
