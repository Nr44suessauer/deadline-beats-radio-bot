#!/usr/bin/env bash
# Checks that commands are no longer rejected.
set -u
S="$1"
WEBHOOK="http://127.0.0.1:5678/webhook/YOUR-WEBHOOK-PATH?key=$S"

schicke() {
  echo "════ $1"
  curl -s -m 90 -o /dev/null -w " HTTP %{http_code}\n" -X POST "$WEBHOOK" \
    -H 'Content-Type: application/json' \
    -d "$(python3 -c "
import json,sys
print(json.dumps({'message': {'message_id': 1, 'chat': {'id': 1, 'type': 'private'},
                              'from': {'id': 1, 'first_name': 'Test'}, 'text': sys.argv[1]}}))" "$1")"
}

# Title that just played -> previously rejected
schicke "/wish American Idiot"
# Ambiguous -> should still play the best match
schicke "/wish nirvana"
# Explicit search -> List
schicke "/search rammstein"
