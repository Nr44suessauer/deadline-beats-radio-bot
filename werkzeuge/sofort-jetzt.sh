#!/usr/bin/env bash
# Spielt einen Titel sofort aus (Weg des Bots, ohne Telegram nachzubauen).
set -u
ID="$1"
KEY=$(cat /tmp/.azkey)

jetzt() {
  curl -s http://192.168.178.33/api/nowplaying/1 | python3 -c "
import json,sys
n = json.load(sys.stdin)['now_playing']
print('   ', n['song']['text'][:52], '| Playlist:', n['playlist'] or '-', '| seit', round(n['elapsed']), 's von', round(n['duration']), 's')
"
}

echo "  vorher:"; jetzt
echo "  --> Titel $ID in die Unterbrecherliste"
curl -s -o /dev/null -X PUT -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"playlists":[8,9]}' "http://192.168.178.33/api/station/1/file/$ID"
echo "  --> Synchlauf"
curl -s -X PUT -H "X-API-Key: $KEY" http://192.168.178.33/api/admin/debug/sync/QueueInterruptingTracks \
  | python3 -c "
import json,sys
for l in json.load(sys.stdin).get('logs', []):
    m = l.get('message','')
    if any(w in m for w in ('Submitting', 'No interrupting', 'not empty')):
        print('   ', l.get('level'), m[:90])
"
sleep 10
echo "  nachher:"; jetzt
echo "  --> Titel $ID wieder aus der Unterbrecherliste"
curl -s -o /dev/null -X PUT -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"playlists":[8]}' "http://192.168.178.33/api/station/1/file/$ID"
