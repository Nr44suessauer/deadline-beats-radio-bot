#!/usr/bin/env bash
# Language messages with multiple tasks and reference to the context.
# Call: bash speech2-test.sh <key>
set -u
S="$1"
IP=192.168.178.53
WEBHOOK="http://127.0.0.1:5678/webhook/YOUR-WEBHOOK-PATH?key=$S"
mkdir -p /tmp/audio-test2 && cd /tmp/audio-test2 || exit 1

create() {   # generate <name> <spoken text>
  curl -s -o "$1.mp3" -X POST http://127.0.0.1:8881/v1/audio/speech \
    -H 'Content-Type: application/json' \
    -d "$(python3 -c "import json,sys; print(json.dumps({'input': sys.argv[1], 'voice': 'de_DE-eva_k-x_low', 'response_format': 'mp3'}))" "$2")"
  docker cp "$PWD/$1.mp3" whisper-asr:/tmp/x.mp3 >/dev/null
  docker exec whisper-asr ffmpeg -y -loglevel error -i /tmp/x.mp3 -c:a libopus -b:a 32k /tmp/x.ogg
  docker cp whisper-asr:/tmp/x.ogg "$PWD/$1.ogg" >/dev/null
  echo "  $1.ogg: $(stat -c %s "$1.ogg") Bytes"
}

echo "--- Generate voice files"
create m1 "Play gasoline from Rammstein immediately and then some Nirvana"
create m2 "Play me three songs by The Doctors"
create m3 "Of those I’d like two more"
create m4 "What is currently playing and how many people are listening"
create m5 "Play something quiet"

echo "--- Make files available (Port 8899)"
pkill -f "http.server 8899" 2>/dev/null
sleep 1
nohup python3 -m http.server 8899 --bind 0.0.0.0 >/tmp/audio-test2/http.log 2>&1 &
sleep 2
curl -s -o /dev/null -w " Test: HTTP %{http_code}\n" "http://$IP:8899/m1.ogg"

voice() {   # adjust <file> <duration>
  echo "════ $1"
  curl -s -m 120 -o /dev/null -w " HTTP %{http_code}  (%{time_total}s)\n" -X POST "$WEBHOOK" \
    -H 'Content-Type: application/json' \
    -d "{\"message\":{\"message_id\":1,\"chat\":{\"id\":1,\"type\":\"private\"},\"from\":{\"id\":1,\"first_name\":\"Test\"},\"voice\":{\"file_id\":\"TESTDATEI\",\"duration\":$2,\"mime_type\":\"audio/ogg\",\"test_url\":\"http://$IP:8899/$1\"}}}"
}

voice m1.ogg 5
voice m2.ogg 4
voice m3.ogg 3
voice m4.ogg 4
voice m5.ogg 3

pkill -f "http.server 8899" 2>/dev/null
echo "--- Test server stopped"
