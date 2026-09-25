#!/usr/bin/env bash
# Laedt die vier Piper-Stimmen des Bots in ein Zielverzeichnis.
#
# Die Stimmen bestehen aus zwei Dateien: <name>.onnx und <name>.onnx.json.
# Quelle ist die Piper-Stimmsammlung (rhasspy/piper-voices).
#
# Aufruf:  bash stimmen-holen.sh [Zielverzeichnis]     (Standard: ./voices)
set -euo pipefail

ZIEL="${1:-./voices}"
BASIS="https://huggingface.co/rhasspy/piper-voices/resolve/main"

# Kurzname:Datei:Unterpfad  - der Kurzname ist der, den main.py kennt
STIMMEN=(
  "de_thorsten:de_DE-thorsten-medium:de/de_DE/thorsten/medium"
  "de_kerstin:de_DE-kerstin-low:de/de_DE/kerstin/low"
  "de_ramona:de_DE-ramona-low:de/de_DE/ramona/low"
  "de_eva:de_DE-eva_k-x_low:de/de_DE/eva_k/x_low"
)

mkdir -p "$ZIEL"
echo "Ziel: $(cd "$ZIEL" && pwd)"

for eintrag in "${STIMMEN[@]}"; do
  kurz="${eintrag%%:*}"
  rest="${eintrag#*:}"
  datei="${rest%%:*}"
  pfad="${rest#*:}"
  for endung in ".onnx" ".onnx.json"; do
    ziel="$ZIEL/$datei$endung"
    if [ -s "$ziel" ]; then
      echo "  vorhanden: $datei$endung"
      continue
    fi
    echo "  hole:      $datei$endung"
    curl -fLsS --retry 3 -o "$ziel.part" "$BASIS/$pfad/$datei$endung"
    mv "$ziel.part" "$ziel"
  done
  echo "  -> $kurz bereit"
done

echo
echo "Stimmen im Zielverzeichnis:"
ls -1 "$ZIEL" | sed 's/^/  /'
echo
echo "Damit der Dienst sie nutzt:"
echo "  docker compose up -d --build     (im Verzeichnis des Dienstes, z. B. /opt/radio-tts)"
echo "  curl -s http://127.0.0.1:8881/health    # muss \"stimmen\": 4 melden"
