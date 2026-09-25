#!/usr/bin/env bash
# Prüft den Sofortweg des Bots über den Testeingang (Chat 1).
set -u
S="$1"
WEBHOOK="http://127.0.0.1:5678/webhook/DEIN-WEBHOOK-PFAD?schluessel=$S"
KEY=$(cat /tmp/.azkey)

jetzt() {
  curl -s http://192.168.178.33/api/nowplaying/1 | python3 -c "
import json,sys
n = json.load(sys.stdin)['now_playing']
print('   ', n['song']['text'][:52], '| Playlist:', n['playlist'] or '-', '| seit', round(n['elapsed']), 's')
"
}

echo "  vorher:"; jetzt
echo "  --> /sofort American Idiot"
curl -s -m 90 -o /dev/null -w "   HTTP %{http_code} (%{time_total}s)\n" -X POST "$WEBHOOK" \
  -H 'Content-Type: application/json' \
  -d '{"message":{"message_id":1,"chat":{"id":1,"type":"private"},"from":{"id":1,"first_name":"Test"},"text":"/sofort American Idiot"}}'
for i in 1 2 3 4 5; do
  sleep 6
  echo "  nach $((i * 6)) s:"; jetzt
done
echo "  Unterbrecherliste:"; curl -s -H "X-API-Key: $KEY" http://192.168.178.33/api/station/1/playlist/9
echo
