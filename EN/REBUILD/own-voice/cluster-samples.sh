#!/usr/bin/env bash
# Send voice samples of speaker clusters from a voice dataset via Telegram.
#
# Call:   cluster-samples.sh <dataset> [samples-per-cluster] [only-this-cluster]
# Example: cluster-samples.sh konosuba 2
# cluster-samples.sh konosuba 2 cluster_3
#
# Retrieves the Telegram access from the n8n workflow “Configuration” (CT 103),
# converts the longest segments of each cluster into voice messages (OGG/Opus)
# and sends them to the chat. At the end, the question is asked which cluster is the
# desired speaker.
set -euo pipefail
CFG=${CFG:-~/.ssh/config}
NAME=${1:?Bitte Dataset-names angeben (z.B. konosuba)}
JE=${2:-2}
ONLY=${3:-}
CHAT=${TG_CHAT:-YOUR-CHAT-ID}
CT=${CT:-111}
DS="/opt/Applio/assets/datasets/$NAME"

# --- Obtain Telegram access (found in n8n workflow “Configuration”)
TOKEN=$(ssh -F "$CFG" ai-server \
  "pct exec 103 -- bash -lc 'docker exec -u node n8n n8n export:workflow --id=Configuration --output=/tmp/konf.json >/dev/null 2>&1; docker cp n8n:/tmp/konf.json - 2>/dev/null'" \
  | python3 -c "import sys,re; t=re.findall(r'[0-9]{8,}:[A-Za-z0-9_-]{30,}', sys.stdin.read()); print(t[0] if t else '')")
[ -n "$TOKEN" ] || { echo "No Telegram access found."; exit 1; }

# --- Build and send samples in container
ssh -F "$CFG" ai-server "pct exec $CT -- bash -s" <<REMOTE
set -uo pipefail
TOKEN='$TOKEN'
CHAT='$CHAT'
DS='$DS'
NAME='$NAME'
JE=$JE
ONLY='$ONLY'
mkdir -p /tmp/proben
found=0
for d in \$(ls -d \$DS/cluster_* 2>/dev/null | sort -V); do
  [ -d "\$d" ] || continue
  short=\$(basename "\$d")
  [ -z "\$ONLY" ] || [ "\$short" = "\$ONLY" ] || continue
  n=\$(find "\$d" -name '*.wav' | wc -l)
  [ "\$n" -gt 0 ] || continue
  echo "--- \$short: \$n segments"
  t=0
  for f in \$(ls -S "\$d"/*.wav 2>/dev/null | head -n \$JE); do
    t=\$((t+1))
    out=/tmp/proben/probe.ogg
    if ! ffmpeg -nostdin -y -i "\$f" -t 9 -ac 1 -ar 48000 -c:a libopus -b:a 48k "\$out" >/dev/null 2>&1; then
      echo " ffmpeg failed: \$f"; continue
    fi
    curl -s -o /tmp/tg.json -m 60 \\
      -F chat_id="\$CHAT" -F voice=@"\$out" \\
      -F caption="\$NAME · \$short · Sample \$t · \$n segments" \\
      "https://api.telegram.org/bot\$TOKEN/sendVoice"
    if grep -q '"ok":true' /tmp/tg.json; then
      echo " Sample \$t sent"
    else
      echo " Sending failed:"; head -c 200 /tmp/tg.json; echo
    fi
    sleep 1
  done
  found=1
done
if [ "\$found" = "0" ]; then
  echo "No clusters found under \$DS"
  exit 1
fi
curl -s -o /tmp/tg2.json -m 60 -F chat_id="\$CHAT" \\
  -F text="These were the speaker clusters of \$NAME. Reply with the name (e.g., cluster_2) of the one you want as the desired speaker – then I will start the RVC training." \\
  "https://api.telegram.org/bot\$TOKEN/sendMessage" >/dev/null
echo "Fertig."
REMOTE
