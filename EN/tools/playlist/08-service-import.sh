##!/bin/bash
# Plays the playlist module into the radio-tts service (LXC 103) and rebuilds it.
# Call:  bash 08-service-deploy.sh
set -euo pipefail

CFG=~/.ssh/config
QUELLE=<dokuordner>/service/playlist.py
STAMP=$(date +%Y%m%d-%H%M%S)

cat "$QUELLE" | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/playlist.py'"

cat <<'REMOTE' | ssh -F "$CFG" ai-server "pct exec 103 -- bash -s"
set -e
STAMP=$(date +%Y%m%d-%H%M%S)
cd /opt/radio-tts/app
cp playlist.py "playlist.py.before-$STAMP" 2>/dev/null || true
cp main.py "main.py.before-$STAMP"
cp /tmp/playlist.py playlist.py
python3 - <<'PY'
from pathlib import Path
p = Path('/opt/radio-tts/app/main.py')
text = p.read_text(encoding='utf-8')
if 'playlist_router' in text:
    print('Router is already bound')
else:
    text += '''

# --- Playlist: build, manage, play (see playlist.py) ---------
try:
    from playlist import router as playlist_router  # type: ignore

    app.include_router(playlist_router)
    print("Playlist module bound", flush=True)
except Exception as error:  # noqa: BLE001
    print("Playlist module not bound:", error, flush=True)
'''
    p.write_text(text, encoding='utf-8')
    print('Router bound')
PY
cd /opt/radio-tts
docker compose build radio-tts 2>&1 | tail -2
docker compose up -d radio-tts 2>&1 | tail -2
for i in $(seq 1 40); do
  C=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8881/health || true)
  [ "$C" = "200" ] && break
  sleep 3
done
echo "Health: $C"
echo "--- Playlist module ---"
curl -s http://127.0.0.1:8881/playlist/status
echo
REMOTE
