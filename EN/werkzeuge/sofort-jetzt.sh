#!/usr/bin/env bash
# Plays a title immediately (way of the bot, without building Telegram).
set -u
ID="$1"
KEY=$(cat /tmp/.azkey)

now() {
  curl -s http://192.168.178.33/api/nowplaying/1 | python3 -c "
import json,sys
n = json.load(sys.stdin)['now_playing']
print('   ', n['song']['text'][:52], '| Playlist:', n['playlist'] or '-', '| since', round(n['elapsed']), 's of', round(n['duration']), 's')
"
}

echo " before:"; now
echo " --> Title $ID to the interrupter list"
curl -s -o /dev/null -X PUT -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"playlists":[8,9]}' "http://192.168.178.33/api/station/1/file/$ID"
echo " --> Synchronization run"
curl -s -X PUT -H "X-API-Key: $KEY" http://192.168.178.33/api/admin/debug/sync/QueueInterruptingTracks \
  | python3 -c "
import json,sys
for l in json.load(sys.stdin).get('logs', []):
    m = l.get('message','')
    if any(w in m for w in ('Submitting', 'No interrupting', 'not empty')):
        print('   ', l.get('level'), m[:90])
"
sleep 10
echo " afterwards:"; now
echo " --> Title $ID again from the interrupter list"
curl -s -o /dev/null -X PUT -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"playlists":[8]}' "http://192.168.178.33/api/station/1/file/$ID"
