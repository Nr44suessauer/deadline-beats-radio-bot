#!/bin/bash
# Spielt das Listen-Modul in den Dienst radio-tts ein (LXC 103) und baut ihn neu.
# Aufruf:  bash 08-dienst-einspielen.sh
set -euo pipefail

CFG=~/.ssh/config
QUELLE=<dokuordner>/dienst/playlist.py
STAMP=$(date +%Y%m%d-%H%M%S)

cat "$QUELLE" | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/playlist.py'"

cat <<'REMOTE' | ssh -F "$CFG" ai-server "pct exec 103 -- bash -s"
set -e
STAMP=$(date +%Y%m%d-%H%M%S)
cd /opt/radio-tts/app
cp playlist.py "playlist.py.vor-$STAMP" 2>/dev/null || true
cp main.py "main.py.vor-$STAMP"
cp /tmp/playlist.py playlist.py
python3 - <<'PY'
from pathlib import Path
p = Path('/opt/radio-tts/app/main.py')
text = p.read_text(encoding='utf-8')
if 'playlist_router' in text:
    print('Router ist schon eingebunden')
else:
    text += '''

# --- Wiedergabelisten: bauen, verwalten, abspielen (siehe playlist.py) ---------
try:
    from playlist import router as playlist_router  # type: ignore

    app.include_router(playlist_router)
    print("Listen-Modul eingebunden", flush=True)
except Exception as fehler:  # noqa: BLE001
    print("Listen-Modul nicht eingebunden:", fehler, flush=True)
'''
    p.write_text(text, encoding='utf-8')
    print('Router eingebunden')
PY
cd /opt/radio-tts
docker compose build radio-tts 2>&1 | tail -2
docker compose up -d radio-tts 2>&1 | tail -2
for i in $(seq 1 40); do
  C=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8881/health || true)
  [ "$C" = "200" ] && break
  sleep 3
done
echo "Gesundheit: $C"
echo "--- Listen-Modul ---"
curl -s http://127.0.0.1:8881/playlist/status
echo
REMOTE
