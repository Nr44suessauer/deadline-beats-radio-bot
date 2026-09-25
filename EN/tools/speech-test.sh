#!/usr/bin/env bash
# Testing language messages: generates OGG files, makes them available, feeds them in.
set -u
S="$1"                       # Key of the test input
IP=192.168.178.53
WEBHOOK="http://127.0.0.1:5678/webhook/YOUR-WEBHOOK-PATH?key=$S"
cd /tmp || exit 1
mkdir -p /tmp/audio-test && cd /tmp/audio-test || exit 1

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
create p1 "Please play immediately Benzene by Rammstein"
create p2 "What’s currently playing for a title"
create p3 "Please play Nirvana"
create p4 "What‘s the title that’s currently playing"
create p5 "Find me something by Die Ärzte"

echo "--- Make files available (Port 8899)"
pkill -f "http.server 8899" 2>/dev/null
sleep 1
nohup python3 -m http.server 8899 --bind 0.0.0.0 >/tmp/audio-test/http.log 2>&1 &
sleep 2
curl -s -o /dev/null -w " Test: HTTP %{http_code}\n" "http://$IP:8899/p1.ogg"

voice() {   # adjust <file> <duration>
  echo "════ Voice message $1"
  curl -s -m 90 -o /dev/null -w " HTTP %{http_code}  (%{time_total}s)\n" -X POST "$WEBHOOK" \
    -H 'Content-Type: application/json' \
    -d "{\"message\":{\"message_id\":1,\"chat\":{\"id\":1,\"type\":\"private\"},\"from\":{\"id\":1,\"first_name\":\"Test\"},\"voice\":{\"file_id\":\"TESTDATEI\",\"duration\":$2,\"mime_type\":\"audio/ogg\",\"test_url\":\"http://$IP:8899/$1\"}}}"
}

voice p1.ogg 3
voice p2.ogg 3
voice p3.ogg 3
voice p4.ogg 3
voice p5.ogg 3
