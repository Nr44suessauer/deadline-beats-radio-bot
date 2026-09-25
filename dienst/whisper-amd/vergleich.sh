#!/usr/bin/env bash
# Vergleichstest fuer die Spracherkennung auf der MI50 (Container 112).
#
# Erzeugt eine deutsche Ansage ueber den radio-tts-Dienst (Piper), wandelt sie
# wie Telegram nach OGG/Opus und schickt sie durch drei Wege:
#   1) Bruecke CT 112, Port 8000   -> whisper.cpp auf der MI50, VAD an (so laeuft der Bot)
#   2) whisper-cli ohne VAD        -> Kontrolle, ob die VAD den Anfang abschneidet
#   3) alter Dienst CT 105, 18790  -> Vergleich mit faster-whisper large-v3 (3090 Ti)
#
# Aufruf:  bash vergleich.sh
set -euo pipefail
CFG=~/.ssh/config

ssh -F "$CFG" ai-server 'bash -s' <<'FERN'
pct exec 112 -- bash -lc '
  curl -s -X POST http://192.168.178.53:8881/v1/audio/speech -H "Content-Type: application/json" -d "{\"input\":\"Spiele sofort Benzin von Rammstein und danach etwas ruhiges von Nirvana\",\"response_format\":\"mp3\"}" -o /tmp/probe.mp3
  ffmpeg -y -loglevel error -i /tmp/probe.mp3 -c:a libopus -b:a 32k /tmp/probe.ogg
  ffmpeg -y -loglevel error -i /tmp/probe.ogg -ar 16000 -ac 1 /tmp/probe.wav
  ls -l /tmp/probe.ogg
  echo "--- 1) Bruecke mit VAD, MI50 ---"
  time curl -s -m 300 -X POST http://127.0.0.1:8000/transcribe -F file=@/tmp/probe.ogg -F language=de
  echo
  echo "--- 2) whisper-cli ohne VAD ---"
  time /opt/whisper.cpp/build/bin/whisper-cli -m /opt/whisper-models/ggml-large-v3.bin -f /tmp/probe.wav -l de -bs 5 -nt 2>/dev/null | tail -2
  echo "--- 3) alter Dienst, 3090 Ti ---"
  time curl -s -m 120 -X POST http://192.168.178.187:18790/transcribe -F file=@/tmp/probe.ogg -F language=de
  echo
'
FERN
