#!/usr/bin/env bash
# Richtet den Stimmen-Dienst im Container 111 (Applio/RVC) ein:
# Film/Serie -> Demucs -> Sprach-Schnipsel -> Dataset -> Sprecher-Cluster.
# Wiederholbar: kopiert Skript + Einheit, legt Schluessel an, startet neu.
set -euo pipefail
CFG=~/.ssh/config
HIER="$(cd "$(dirname "$0")" && pwd)"

echo "--- Ordner und Schluessel"
ssh -F "$CFG" ai-server "pct exec 111 -- bash -lc '
  mkdir -p /opt/Applio/stimmen-dienst /var/log/stimmen /var/lib/stimmen-dienst
  if [ ! -s /opt/Applio/stimmen-dienst/schluessel.txt ]; then
    head -c 24 /dev/urandom | base64 | tr -d \"+/=\" | cut -c1-32 > /opt/Applio/stimmen-dienst/schluessel.txt
  fi
  chmod 600 /opt/Applio/stimmen-dienst/schluessel.txt
  echo \"Schluessel liegt in /opt/Applio/stimmen-dienst/schluessel.txt (600)\"
'"

echo "--- Skript und Einheit kopieren"
cat "$HIER/stimmen_dienst.py" | ssh -F "$CFG" ai-server \
  "pct exec 111 -- bash -c 'cat > /opt/Applio/stimmen-dienst/stimmen_dienst.py'"
cat "$HIER/prep_dataset.py" | ssh -F "$CFG" ai-server \
  "pct exec 111 -- bash -c 'cat > /opt/Applio/pipeline/prep_dataset.py'"
cat "$HIER/cluster_speakers.py" | ssh -F "$CFG" ai-server \
  "pct exec 111 -- bash -c 'cat > /opt/Applio/pipeline/cluster_speakers.py'"
cat "$HIER/stimmen-dienst.service" | ssh -F "$CFG" ai-server \
  "pct exec 111 -- bash -c 'cat > /etc/systemd/system/stimmen-dienst.service'"

echo "--- Dienst starten"
ssh -F "$CFG" ai-server "pct exec 111 -- bash -lc '
  systemctl daemon-reload
  systemctl enable stimmen-dienst
  systemctl restart stimmen-dienst
  sleep 3
  systemctl --no-pager --lines=2 status stimmen-dienst | grep -E \"Active:|Loaded:\" || true
  echo ---
  curl -s -m 5 http://127.0.0.1:8890/status
  echo
  ss -tln | grep 8890 || true
'"
