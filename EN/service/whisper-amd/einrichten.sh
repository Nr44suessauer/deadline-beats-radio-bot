#!/usr/bin/env bash
# Sets up the STT service in container 112 “whisper-amd” (MI50, whisper.cpp/Vulkan).
# Repeatable: copies bridge + systemd units over and restarts the services.
#
# Prerequisites in the container (once only):
# - whisper.cpp built under /opt/whisper.cpp (GGML_VULKAN=ON)
# - Model /opt/whisper-models/ggml-large-v3.bin
# - Packages: build-essential cmake git libvulkan-dev vulkan-tools glslc spirv-headers ffmpeg
set -euo pipefail
CFG=~/.ssh/config
HIER="$(cd "$(dirname "$0")" && pwd)"

echo "--- Copy bridge and units"
cat "$HIER/../whisper_amd.py" | ssh -F "$CFG" ai-server \
  "pct exec 112 -- bash -c 'mkdir -p /opt/whisper-bruecke && cat > /opt/whisper-bruecke/whisper_amd.py'"
cat "$HIER/whisper-cpp.service" | ssh -F "$CFG" ai-server \
  "pct exec 112 -- bash -c 'cat > /etc/systemd/system/whisper-cpp.service'"
cat "$HIER/whisper-bruecke.service" | ssh -F "$CFG" ai-server \
  "pct exec 112 -- bash -c 'cat > /etc/systemd/system/whisper-bruecke.service'"

echo "--- Deploy services and start"
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
