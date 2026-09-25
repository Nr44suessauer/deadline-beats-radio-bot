#!/usr/bin/env bash
# Downloads the four Piper voices of the bot into a target directory.
#
# The voices consist of two files: <name>.onnx and <name>.onnx.json.
# Source is the Piper voice collection (rhasspy/piper-voices).
#
# Call:  bash voices-fetch.sh [target directory]     (default: ./voices)
set -euo pipefail

ZIEL="${1:-./voices}"
BASIS="https://huggingface.co/rhasspy/piper-voices/resolve/main"

# Short name:File:Subpath  - the short name is the one that main.py knows
STIMMEN=(
  "de_thorsten:de_DE-thorsten-medium:de/de_DE/thorsten/medium"
  "de_kerstin:de_DE-kerstin-low:de/de_DE/kerstin/low"
  "de_ramona:de_DE-ramona-low:de/de_DE/ramona/low"
  "de_eva:de_DE-eva_k-x_low:de/de_DE/eva_k/x_low"
)

mkdir -p "$ZIEL"
echo "Target: $(cd"$ZIEL" && pwd)"

for entry in "${STIMMEN[@]}"; do
  short="${entry%%:*}"
  rest="${entry#*:}"
  file="${rest%%:*}"
  path="${rest#*:}"
  for endung in ".onnx" ".onnx.json"; do
    target="$ZIEL/$file$endung"
    if [ -s "$target" ]; then
      echo " available: $file$endung"
      continue
    fi
    echo " fetch:      $file$endung"
    curl -fLsS --retry 3 -o "$target.part" "$BASIS/$path/$file$endung"
    mv "$target.part" "$target"
  done
  echo " -> $short ready"
done

echo
echo "Voices in target directory:"
ls -1 "$ZIEL" | sed 's/^/  /'
echo
echo "So that the service can use them:"
echo "  docker compose up -d --build     (in the service directory, e.g. /opt/radio-tts)"
echo "  curl -s http://127.0.0.1:8881/health    # must \"voices\": 4 melden"
