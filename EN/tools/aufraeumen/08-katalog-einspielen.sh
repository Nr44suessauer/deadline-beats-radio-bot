##!/bin/bash
# Imports the new version of the catalog service (live archive and announcements
# are no longer indexed) and rebuilds the catalog.
# Call:  bash 08-catalog-deploy.sh
set -euo pipefail

CFG=~/.ssh/config
QUELLE=<dokuordner>/service/catalog.py
STAMP=$(date +%Y%m%d-%H%M%S)

cat "$QUELLE" | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/catalog-new.py'"

ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  set -e
  test -f /opt/radio-tts/app/catalog.py
  cp /opt/radio-tts/app/catalog.py /opt/radio-tts/app/catalog.py.before-cleanup-$STAMP
  cp /tmp/catalog-new.py /opt/radio-tts/app/catalog.py
  cd /opt/radio-tts
  docker compose build radio-tts 2>&1 | tail -3
  docker compose up -d radio-tts 2>&1 | tail -2
  for i in \$(seq 1 40); do
    C=\$(curl -s -o /dev/null -w \"%{http_code}\" http://127.0.0.1:8881/health || true)
    [ \"\$C\" = \"200\" ] && break
    sleep 3
  done
  echo \"Katalogdienst Gesundheit: \$C\"
  echo \"--- Rebuild the catalog (takes about a minute) ---\"
  curl -s -X POST http://127.0.0.1:8881/catalog/refresh | head -c 300
  echo
  echo \"--- Status ---\"
  curl -s http://127.0.0.1:8881/catalog/status
  echo
'"
