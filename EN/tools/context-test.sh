#!/usr/bin/env bash
# Checks context search and direction preferences via the test input.
# Call: cat context-test.sh | ssh ... “pct exec 103 -- bash -s -- <key>”
WEBHOOK=http://127.0.0.1:5678/webhook/YOUR-WEBHOOK-PATH
KEY=${1:?Please provide the test key as an argument}

send() {   # send <text> [chat]
  echo "════════ $1"
  curl -s -m 120 -X POST "$WEBHOOK" -H 'Content-Type: application/json' -d "$(python3 -c "
import json,sys
print(json.dumps({'key': sys.argv[1],
                  'message': {'message_id': 1, 'chat': {'id': int(sys.argv[3]), 'type': 'private'},
                              'from': {'id': int(sys.argv[3]), 'first_name': 'Test'},
                              'text': sys.argv[2]}}))" "$KEY" "$1" "${2:-1}")" \
    | python3 -c "
import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    print(' (no JSON response)'); raise SystemExit
if isinstance(d, dict) and 'answer' in d:
    for z in str(d['answer']).split('\n'):
        if z.strip(): print('  ', z)
else:
    print('  ', str(d)[:200])
"
}

echo "--- Context search (typing errors) ---"
send "/wish bohemian rapsody"
send "/wish rammstien benzene"
send "/wish nivana smells like teen spirit"
send "/wish die artzte"
echo
echo "--- Direction preferences ---"
send "/wish was out rock"
send "/wish something calm"
send "/wish metal"
send "/wish 90s"
send "/wish germanrap"
echo
echo "--- Both mixed: Title that sounds like a direction ---"
send "/wish rock me amadeus"
send "/wish hip hop hooray"
