#!/usr/bin/env bash
# Deploys all service modules (main.py, catalog.py, playlist.py, news.py) along with
# The Dockerfile into the radio-tts service and builds it anew.
#
# Replaces playlist/08-service-deploy.sh: same effect, but for all
# Modules. The Dockerfile must copy each module, otherwise it will be missing in the service.
#
# Invocation:  bash service-deploy.sh
set -euo pipefail

CFG=~/.ssh/config
QUELLE=$(cd "$(dirname "$0")/../service" && pwd)
# Automatically include all Python modules - otherwise a newly added
# Module will silently be missing in the service (on 2026-09-20 at search.py: /research responded with 404).
DATEIEN=()
while IFS= read -r F; do DATEIEN+=("$(basename "$F")"); done < <(ls "$(dirname "$0")/../service"/*.py | sort)
DATEIEN+=(Dockerfile)

echo "--- Transfer modules"
for F in "${DATEIEN[@]}"; do
  [ -f "$QUELLE/$F" ] || { echo " missing locally: $F"; exit 1; }
  if [ "$F" = "Dockerfile" ]; then
    ZIEL=/opt/radio-tts/Dockerfile
  else
    ZIEL=/opt/radio-tts/app/$F
  fi
  cat "$QUELLE/$F" | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/$F'"
  ssh -F "$CFG" ai-server "pct exec 103 -- bash -c '
    set -e
    STAMP=\$(date +%Y%m%d-%H%M%S)
    [ -f $ZIEL ] && cp $ZIEL $ZIEL.before-\$STAMP
    mkdir -p \$(dirname $ZIEL)
    cp /tmp/$F $ZIEL'"
  printf ' %-14s %6s Bytes\n' "$F" "$(wc -c < "$QUELLE/$F")"
done

echo "--- build and start"
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc 'cd /opt/radio-tts && docker compose build radio-tts 2>&1 | tail -2 && docker compose up -d radio-tts 2>&1 | tail -2'"

for i in $(seq 1 40); do
  C=$(curl -s -o /dev/null -w "%{http_code}" http://192.168.178.53:8881/health || true)
  [ "$C" = "200" ] && break
  sleep 3
done
echo "Health: $C"

echo "--- Modules in service"
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc 'docker logs --tail 30 radio-tts 2>&1 | grep -iE \"Modul|eingebunden|error\" | tail -6'"
for A in /playlist/status /news/status /announce/status; do
  printf ' %-20s' "$A"
  curl -s "http://192.168.178.53:8881$A" | head -c 160
  echo
done
