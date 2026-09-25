#!/usr/bin/env bash
# Richtet den STT-Dienst im Container 112 "whisper-amd" ein (MI50, whisper.cpp/Vulkan).
# Wiederholbar: kopiert Bruecke + systemd-Einheiten hinueber und startet die Dienste neu.
#
# Voraussetzungen im Container (einmalig):
#   - whisper.cpp unter /opt/whisper.cpp gebaut (GGML_VULKAN=ON)
#   - Modell /opt/whisper-models/ggml-large-v3.bin
#   - Pakete: build-essential cmake git libvulkan-dev vulkan-tools glslc spirv-headers ffmpeg
set -euo pipefail
CFG=~/.ssh/config
HIER="$(cd "$(dirname "$0")" && pwd)"

echo "--- Bruecke und Einheiten kopieren"
cat "$HIER/../whisper_amd.py" | ssh -F "$CFG" ai-server \
  "pct exec 112 -- bash -c 'mkdir -p /opt/whisper-bruecke && cat > /opt/whisper-bruecke/whisper_amd.py'"
cat "$HIER/whisper-cpp.service" | ssh -F "$CFG" ai-server \
  "pct exec 112 -- bash -c 'cat > /etc/systemd/system/whisper-cpp.service'"
cat "$HIER/whisper-bruecke.service" | ssh -F "$CFG" ai-server \
  "pct exec 112 -- bash -c 'cat > /etc/systemd/system/whisper-bruecke.service'"

echo "--- Dienste einspielen und starten"
ssh -F "$CFG" ai-server "pct exec 112 -- bash -lc '
  systemctl daemon-reload
  systemctl enable whisper-cpp whisper-bruecke
  systemctl restart whisper-cpp whisper-bruecke
  sleep 3
  systemctl --no-pager --lines=2 status whisper-cpp whisper-bruecke | grep -E \"Active:|Loaded:\" || true
  echo ---
  curl -s -m 5 http://127.0.0.1:8000/health
  echo
'"
