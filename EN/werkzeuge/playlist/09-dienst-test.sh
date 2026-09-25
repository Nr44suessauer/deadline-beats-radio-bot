##!/bin/bash
# Tests the list tasks of the service (without Telegram, without transmission operation).
# Call:  bash 09-service-test.sh
set -uo pipefail

CFG=~/.ssh/config
BOT="192.168.178.53:8881"

call() {   # call <path> <json>
  ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc 'curl -s -X POST http://$BOT$1 \
    -H \"Content-Type: application/json\" -d '\''$2'\'''"
}

show() {  # show <designation> <json>
  echo "--- $1"
  python3 -c "
import json,sys
d = json.loads(sys.stdin.read())
print('  ' + str(d.get('answer',''))[:600].replace(chr(10), chr(10) + '  '))
t = d.get('keyboard') or {}
k = t.get('inline_keyboard') or []
if k:
    print(' Buttons:' + ' | '.join(x['text'][:40] for zeile in k for x in zeile))
"
}

sag() { printf '\n=== %s ===\n' "$1"; }

CHAT="test-$$"

sag "1) List lists"
call /playlist/command "{\"chatId\":\"$CHAT\",\"text\":\"welche Playlists gives es\"}" | show "Answer"

sag "2) Build playlist (selection menu)"
call /playlist/command "{\"chatId\":\"$CHAT\",\"text\":\"build a playlist Summer from Scooter\"}" > /tmp/m1.json
show "Answer" < /tmp/m1.json

sag "3) Click two titles"
call /playlist/button "{\"chatId\":\"$CHAT\",\"data\":\"p1\"}" > /tmp/m2.json
show "after p1" < /tmp/m2.json
call /playlist/button "{\"chatId\":\"$CHAT\",\"data\":\"p3\"}" > /tmp/m3.json
show "after p3" < /tmp/m3.json

sag "4) Done -> Create list"
call /playlist/button "{\"chatId\":\"$CHAT\",\"data\":\"pf\"}" | show "Answer"

sag "5) Check in the transmitter interface"
ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 root@192.168.178.163 \
 "pct exec 106 -- docker exec azuracast gosu mysql azuracast_db -t -e \"select id,name,type,source from station_playlists order by id desc limit 3;\"" | tail -8

sag "6) No playback (px = enough)"
call /playlist/button "{\"chatId\":\"$CHAT\",\"data\":\"px\"}" | show "Answer"

sag "7) View content"
call /playlist/command "{\"chatId\":\"$CHAT\",\"text\":\"was result in the Playlist Sommer\"}" | show "Answer"

sag "8) Rename"
call /playlist/command "{\"chatId\":\"$CHAT\",\"text\":\"rename the playlist Summer to Summer Test\"}" | show "Answer"

sag "9) Empty (with confirmation)"
call /playlist/command "{\"chatId\":\"$CHAT\",\"text\":\"clear the playlist Summer Test\"}" | show "FollowUp"
call /playlist/button "{\"chatId\":\"$CHAT\",\"data\":\"j\"}" | show "after Yes"

sag "10) Delete (with confirmation)"
call /playlist/command "{\"chatId\":\"$CHAT\",\"text\":\"delete the playlist Summer Test\"}" | show "FollowUp"
call /playlist/button "{\"chatId\":\"$CHAT\",\"data\":\"j\"}" | show "after Yes"

sag "11) List selection without name"
call /playlist/command "{\"chatId\":\"$CHAT\",\"text\":\"play a playlist\"}" | show "Answer"

sag "Unknown command"
call /playlist/command "{\"chatId\":\"$CHAT\",\"text\":\"do something with the station\"}" | show "Answer"

sag "State at the end"
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc 'curl -s http://$BOT/playlist/status'"
echo
