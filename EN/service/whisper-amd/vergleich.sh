#!/usr/bin/env bash
# Comparison test for speech recognition on the MI50 (Container 112).
#
# Generates a German announcement via the radio-tts service (Piper), converts it
# like Telegram to OGG/Opus and sends it through three paths:
# 1) Bridge CT 112, Port 8000   -> whisper.cpp on the MI50, VAD enabled (this is how the bot runs)
# 2) whisper-cli without VAD        -> Check whether VAD cuts off the beginning
# 3) old service CT 105, 18790  -> Comparison with faster-whisper large-v3 (3090 Ti)
#
# Call:  bash vergleich.sh
set -euo pipefail
CFG=~/.ssh/config

ssh -F "$CFG" ai-server 'bash -s' <<'FERN'
pct exec 112 -- bash -lc '
  curl -s -X POST http://192.168.178.53:8881/v1/audio/speech -H "Content-Type: application/json" -d "{\"input\":\"Spiele sofort Benzin von Rammstein und danach etwas ruhiges von Nirvana\",\"response_format\":\"mp3\"}" -o /tmp/probe.mp3
  ffmpeg -y -loglevel error -i /tmp/probe.mp3 -c:a libopus -b:a 32k /tmp/probe.ogg
  ffmpeg -y -loglevel error -i /tmp/probe.ogg -ar 16000 -ac 1 /tmp/probe.wav
  ls -l /tmp/probe.ogg
  echo "--- 1) Bridge with VAD, MI50 ---"
  time curl -s -m 300 -X POST http://127.0.0.1:8000/transcribe -F file=@/tmp/probe.ogg -F language=de
  echo
  echo "--- 2) whisper-cli without VAD ---"
  time /opt/whisper.cpp/build/bin/whisper-cli -m /opt/whisper-models/ggml-large-v3.bin -f /tmp/probe.wav -l de -bs 5 -nt 2>/dev/null | tail -2
  echo "--- 3) old service, 3090 Ti ---"
  time curl -s -m 120 -X POST http://192.168.178.187:18790/transcribe -F file=@/tmp/probe.ogg -F language=de
  echo
'
FERN
