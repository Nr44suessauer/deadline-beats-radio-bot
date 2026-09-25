#!/usr/bin/env bash
# Finds a language sample that the recognizer understands cleanly.
set -u
SATZ="Please play immediately Benzene by Rammstein"
for voice in de_thorsten de_DE-eva_k-x_low de_DE-kerstin-low de_DE-ramona-low; do
  for tempo in 1.0 0.85; do
    curl -s -o /tmp/t.mp3 -X POST http://127.0.0.1:8881/v1/audio/speech \
      -H 'Content-Type: application/json' \
      -d "{\"input\":\"$SATZ\",\"voice\":\"$voice\",\"response_format\":\"mp3\",\"speed\":$tempo}"
    docker cp /tmp/t.mp3 whisper-asr:/tmp/t.mp3 >/dev/null
    docker exec whisper-asr ffmpeg -y -loglevel error -i /tmp/t.mp3 -c:a libopus -b:a 64k /tmp/t.ogg
    docker cp whisper-asr:/tmp/t.ogg /tmp/t.ogg >/dev/null
    echo -n "$voice @ $tempo -> "
    curl -s -m 90 -X POST http://127.0.0.1:8000/v1/audio/transcriptions \
      -F "file=@/tmp/t.ogg" -F "model=Systran/faster-whisper-small" -F "language=de" \
      -F "response_format=json" -F "temperature=0" \
      -F "prompt=Musical request to a radio station. Title, artist, track, song, play immediately." \
      | python3 -c "import json,sys; print(json.load(sys.stdin).get('text','?'))"
  done
done
