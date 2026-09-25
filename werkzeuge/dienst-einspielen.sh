#!/usr/bin/env bash
# Spielt alle Dienstmodule (main.py, katalog.py, playlist.py, meldungen.py) samt
# Dockerfile in den Dienst radio-tts ein und baut ihn neu.
#
# Ersetzt playlist/08-dienst-einspielen.sh: gleiche Wirkung, aber für alle
# Module. Der Dockerfile muss jedes Modul mitkopieren, sonst fehlt es im Dienst.
#
# Aufruf:  bash dienst-einspielen.sh
set -euo pipefail

CFG=~/.ssh/config
QUELLE=$(cd "$(dirname "$0")/../dienst" && pwd)
# Alle Python-Module automatisch mitnehmen - sonst fehlt ein neu hinzugefuegtes
# Modul still im Dienst (am 2026-09-20 bei suche.py passiert: /recherche antwortete 404).
DATEIEN=()
while IFS= read -r F; do DATEIEN+=("$(basename "$F")"); done < <(ls "$(dirname "$0")/../dienst"/*.py | sort)
DATEIEN+=(Dockerfile)

echo "--- Module hinueberbringen"
for F in "${DATEIEN[@]}"; do
  [ -f "$QUELLE/$F" ] || { echo "  fehlt lokal: $F"; exit 1; }
  if [ "$F" = "Dockerfile" ]; then
    ZIEL=/opt/radio-tts/Dockerfile
  else
    ZIEL=/opt/radio-tts/app/$F
  fi
  cat "$QUELLE/$F" | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/$F'"
  ssh -F "$CFG" ai-server "pct exec 103 -- bash -c '
    set -e
    STAMP=\$(date +%Y%m%d-%H%M%S)
    [ -f $ZIEL ] && cp $ZIEL $ZIEL.vor-\$STAMP
    mkdir -p \$(dirname $ZIEL)
    cp /tmp/$F $ZIEL'"
  printf '  %-14s %6s Bytes\n' "$F" "$(wc -c < "$QUELLE/$F")"
done

echo "--- bauen und starten"
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc 'cd /opt/radio-tts && docker compose build radio-tts 2>&1 | tail -2 && docker compose up -d radio-tts 2>&1 | tail -2'"

for i in $(seq 1 40); do
  C=$(curl -s -o /dev/null -w "%{http_code}" http://192.168.178.53:8881/health || true)
  [ "$C" = "200" ] && break
  sleep 3
done
echo "Gesundheit: $C"

echo "--- Module im Dienst"
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc 'docker logs --tail 30 radio-tts 2>&1 | grep -iE \"Modul|eingebunden|error\" | tail -6'"
for A in /playlist/status /meldungen/status /ansage/status; do
  printf '  %-20s ' "$A"
  curl -s "http://192.168.178.53:8881$A" | head -c 160
  echo
done
