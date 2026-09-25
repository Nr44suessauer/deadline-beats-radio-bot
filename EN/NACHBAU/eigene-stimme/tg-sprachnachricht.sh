#!/usr/bin/env bash
# Sends an audio file from the RVC container as a Telegram voice message.
#
# Call:   tg-sprachnachricht.sh <path-in-container> “Caption”
# Example: tg-sprachnachricht.sh /opt/Applio/assets/datasets/deine-stimme/00000.wav “YOUR-VOICE-test”
set -euo pipefail
CFG=${CFG:-~/.ssh/config}
CT=${CT:-111}
FILE=${1:?container path missing}
TEXT=${2:-}
CHAT=${TG_CHAT:-YOUR-CHAT-ID}

TOKEN=$(ssh -F "$CFG" ai-server \
  "pct exec 103 -- bash -lc 'docker exec -u node n8n n8n export:workflow --id=Configuration --output=/tmp/konf.json >/dev/null 2>&1; docker cp n8n:/tmp/konf.json - 2>/dev/null'" \
  | python3 -c "import sys,re; t=re.findall(r'[0-9]{8,}:[A-Za-z0-9_-]{30,}', sys.stdin.read()); print(t[0] if t else '')")
[ -n "$TOKEN" ] || { echo "No Telegram access found."; exit 1; }

printf '%s' "$TOKEN" | ssh -F "$CFG" ai-server "pct exec $CT -- bash -c 'cat > /tmp/tgtok; chmod 600 /tmp/tgtok'"
printf '%s' "$TEXT" | ssh -F "$CFG" ai-server "pct exec $CT -- bash -c 'cat > /tmp/tgtext'"

ssh -F "$CFG" ai-server "pct exec $CT -- bash -s" <<REMOTE
TOK=\$(cat /tmp/tgtok); MSG=\$(cat /tmp/tgtext)
ffmpeg -nostdin -y -v error -i '$FILE' -t 30 -ac 1 -ar 48000 -c:a libopus -b:a 64k /tmp/tgstimme.ogg </dev/null
curl -s -o /tmp/tgaus.json -F chat_id=$CHAT -F voice=@/tmp/tgstimme.ogg -F caption="\$MSG" \
     "https://api.telegram.org/bot\$TOK/sendVoice"
grep -q '"ok":true' /tmp/tgaus.json && echo "sent: \$MSG" || { echo "Error:"; head -c 200 /tmp/tgaus.json; echo; }
rm -f /tmp/tgtok /tmp/tgtext /tmp/tgaus.json /tmp/tgstimme.ogg
REMOTE
