#!/usr/bin/env bash
# Sprachnachrichten mit mehreren Auftraegen und Bezug auf den Kontext.
# Aufruf: bash sprache2-test.sh <schluessel>
set -u
S="$1"
IP=192.168.178.53
WEBHOOK="http://127.0.0.1:5678/webhook/DEIN-WEBHOOK-PFAD?schluessel=$S"
mkdir -p /tmp/audio-test2 && cd /tmp/audio-test2 || exit 1

erzeuge() {   # erzeuge <name> <gesprochener Text>
  curl -s -o "$1.mp3" -X POST http://127.0.0.1:8881/v1/audio/speech \
    -H 'Content-Type: application/json' \
    -d "$(python3 -c "import json,sys; print(json.dumps({'input': sys.argv[1], 'voice': 'de_DE-eva_k-x_low', 'response_format': 'mp3'}))" "$2")"
  docker cp "$PWD/$1.mp3" whisper-asr:/tmp/x.mp3 >/dev/null
  docker exec whisper-asr ffmpeg -y -loglevel error -i /tmp/x.mp3 -c:a libopus -b:a 32k /tmp/x.ogg
  docker cp whisper-asr:/tmp/x.ogg "$PWD/$1.ogg" >/dev/null
  echo "  $1.ogg: $(stat -c %s "$1.ogg") Bytes"
}

echo "--- Sprachdateien erzeugen"
erzeuge m1 "Spiele bitte sofort Benzin von Rammstein und danach etwas von Nirvana"
erzeuge m2 "Spiele mir drei Lieder von den Ärzten"
erzeuge m3 "Davon hätte ich gern noch zwei"
erzeuge m4 "Was läuft gerade und wie viele Leute hören zu"
erzeuge m5 "Spiele mal etwas Ruhiges"

echo "--- Dateien bereitstellen (Port 8899)"
pkill -f "http.server 8899" 2>/dev/null
sleep 1
nohup python3 -m http.server 8899 --bind 0.0.0.0 >/tmp/audio-test2/http.log 2>&1 &
sleep 2
curl -s -o /dev/null -w "  Probe: HTTP %{http_code}\n" "http://$IP:8899/m1.ogg"

stimme() {   # stimme <datei> <dauer>
  echo "════ $1"
  curl -s -m 120 -o /dev/null -w "  HTTP %{http_code}  (%{time_total}s)\n" -X POST "$WEBHOOK" \
    -H 'Content-Type: application/json' \
    -d "{\"message\":{\"message_id\":1,\"chat\":{\"id\":1,\"type\":\"private\"},\"from\":{\"id\":1,\"first_name\":\"Test\"},\"voice\":{\"file_id\":\"TESTDATEI\",\"duration\":$2,\"mime_type\":\"audio/ogg\",\"test_url\":\"http://$IP:8899/$1\"}}}"
}

stimme m1.ogg 5
stimme m2.ogg 4
stimme m3.ogg 3
stimme m4.ogg 4
stimme m5.ogg 3

pkill -f "http.server 8899" 2>/dev/null
echo "--- Testserver gestoppt"
