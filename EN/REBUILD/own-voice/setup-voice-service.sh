#!/usr/bin/env bash
# Sets up the voice service in container 111 (Applio/RVC):
# Film/Series -> Demucs -> Voice snippets -> Dataset -> Speaker clusters.
# Repeatable: copies script + unit, creates key, restarts.
set -euo pipefail
CFG=~/.ssh/config
HIER="$(cd "$(dirname "$0")" && pwd)"

echo "--- Folder and key"
ssh -F "$CFG" ai-server "pct exec 111 -- bash -lc '
  mkdir -p /opt/Applio/voices-service /var/log/voices /var/lib/voices-service
  if [ ! -s /opt/Applio/voices-service/key.txt ]; then
    head -c 24 /dev/urandom | base64 | tr -d \"+/=\" | cut -c1-32 > /opt/Applio/voices-service/key.txt
  fi
  chmod 600 /opt/Applio/voices-service/key.txt
  echo \"key liegt in /opt/Applio/voices-service/key.txt (600)\"
'"

echo "--- Copy script and unit"
cat "$HIER/voice-service.py" | ssh -F "$CFG" ai-server \
  "pct exec 111 -- bash -c 'cat > /opt/Applio/voices-service/voice-service.py'"
cat "$HIER/prep_dataset.py" | ssh -F "$CFG" ai-server \
  "pct exec 111 -- bash -c 'cat > /opt/Applio/pipeline/prep_dataset.py'"
cat "$HIER/cluster_speakers.py" | ssh -F "$CFG" ai-server \
  "pct exec 111 -- bash -c 'cat > /opt/Applio/pipeline/cluster_speakers.py'"
cat "$HIER/voices-service.service" | ssh -F "$CFG" ai-server \
  "pct exec 111 -- bash -c 'cat > /etc/systemd/system/voices-service.service'"

echo "--- start service"
ssh -F "$CFG" ai-server "pct exec 111 -- bash -lc '
  systemctl daemon-reload
  systemctl enable voices-service
  systemctl restart voices-service
  sleep 3
  systemctl --no-pager --lines=2 status voices-service | grep -E \"Active:|Loaded:\" || true
  echo ---
  curl -s -m 5 http://127.0.0.1:8890/status
  echo
  ss -tln | grep 8890 || true
'"
