#!/usr/bin/env bash
# Checks the new interpretation: multiple orders, quantities, reference to the context.
# Call: bash kontext2-test.sh <key>
WEBHOOK=http://127.0.0.1:5678/webhook/YOUR-WEBHOOK-PATH
KEY=${1:?Please provide the test key as an argument}

send() {
  echo "════════ $1"
  curl -s -m 120 -o /dev/null -w " HTTP %{http_code}  (%{time_total}s)\n" \
    -X POST "$WEBHOOK" -H 'Content-Type: application/json' -d "$(python3 -c "
import json,sys
print(json.dumps({'key': sys.argv[1],
                  'message': {'message_id': 1, 'chat': {'id': 1, 'type': 'private'},
                              'from': {'id': 1, 'first_name': 'Test'},
                              'text': sys.argv[2]}}))" "$KEY" "$1")"
}

echo "--- Backslash commands (without model)"
send "/now"
send "/wish benzin"
echo
echo "--- Free text: multiple orders in one message"
send "play please immediately gasoline by Rammstein and then play Nirvana"
send "play three songs by Nirvana"
send "play multiple titles by the doctors"
echo
echo "--- Reference to the current"
send "of those I would like two more"
send "what is currently running for a title"
send "play something quiet"
