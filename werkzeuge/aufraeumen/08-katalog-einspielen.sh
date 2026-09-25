#!/bin/bash
# Spielt die neue Fassung des Katalogdienstes ein (Live-Archiv und Ansagen
# kommen nicht mehr in den Index) und baut den Katalog neu auf.
# Aufruf:  bash 08-katalog-einspielen.sh
set -euo pipefail

CFG=~/.ssh/config
QUELLE=<dokuordner>/dienst/katalog.py
STAMP=$(date +%Y%m%d-%H%M%S)

cat "$QUELLE" | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/katalog-neu.py'"

ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  set -e
  test -f /opt/radio-tts/app/katalog.py
  cp /opt/radio-tts/app/katalog.py /opt/radio-tts/app/katalog.py.vor-aufraeumen-$STAMP
  cp /tmp/katalog-neu.py /opt/radio-tts/app/katalog.py
  cd /opt/radio-tts
  docker compose build radio-tts 2>&1 | tail -3
  docker compose up -d radio-tts 2>&1 | tail -2
  for i in \$(seq 1 40); do
    C=\$(curl -s -o /dev/null -w \"%{http_code}\" http://127.0.0.1:8881/health || true)
    [ \"\$C\" = \"200\" ] && break
    sleep 3
  done
  echo \"Katalogdienst Gesundheit: \$C\"
  echo \"--- Katalog neu aufbauen (dauert etwa eine Minute) ---\"
  curl -s -X POST http://127.0.0.1:8881/katalog/aktualisieren | head -c 300
  echo
  echo \"--- Zustand ---\"
  curl -s http://127.0.0.1:8881/katalog/status
  echo
'"