#!/usr/bin/env bash
# Testet Sprachnachrichten: erzeugt OGG-Dateien, stellt sie bereit, speist sie ein.
set -u
S="$1"                       # Schluessel des Testeingangs
IP=192.168.178.53
WEBHOOK="http://127.0.0.1:5678/webhook/DEIN-WEBHOOK-PFAD?schluessel=$S"
cd /tmp || exit 1
mkdir -p /tmp/audio-test && cd /tmp/audio-test || exit 1

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
erzeuge p1 "Spiele bitte sofort Benzin von Rammstein"
erzeuge p2 "Was läuft gerade für ein Titel"
erzeuge p3 "Spiele bitte Nirvana"
erzeuge p4 "Wie heißt der Titel der gerade läuft"
erzeuge p5 "Suche mir etwas von Die Ärzte"

echo "--- Dateien bereitstellen (Port 8899)"
pkill -f "http.server 8899" 2>/dev/null
sleep 1
nohup python3 -m http.server 8899 --bind 0.0.0.0 >/tmp/audio-test/http.log 2>&1 &
sleep 2
curl -s -o /dev/null -w "  Probe: HTTP %{http_code}\n" "http://$IP:8899/p1.ogg"

stimme() {   # stimme <datei> <dauer>
  echo "════ Sprachnachricht $1"
  curl -s -m 90 -o /dev/null -w "  HTTP %{http_code}  (%{time_total}s)\n" -X POST "$WEBHOOK" \
    -H 'Content-Type: application/json' \
    -d "{\"message\":{\"message_id\":1,\"chat\":{\"id\":1,\"type\":\"private\"},\"from\":{\"id\":1,\"first_name\":\"Test\"},\"voice\":{\"file_id\":\"TESTDATEI\",\"duration\":$2,\"mime_type\":\"audio/ogg\",\"test_url\":\"http://$IP:8899/$1\"}}}"
}

stimme p1.ogg 3
stimme p2.ogg 3
stimme p3.ogg 3
stimme p4.ogg 3
stimme p5.ogg 3
