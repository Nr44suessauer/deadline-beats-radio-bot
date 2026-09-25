#!/usr/bin/env bash
# Inserts the announcement access (live route) into the service’s access file.
#
# The service makes announcements via the sender’s DJ dock in the ongoing
# operation (POST /live). For this, it needs server, port, mountpoint, user and
# password as environment variables LIVE_*.
#
# Important: The announcements are routed through an OWN streamer account of the bot
# (Original: deine-stimme, display name “YOUR-VOICE”) - so “YOUR-VOICE” appears in the station and
# not the operator name. The operator access (operator) remains separate.
#
# The values are read from the sender’s access file and directly inserted into
# /opt/radio-tts/geheim.env geschrieben - sie erscheinen nie im Terminal.
#
# Call:  bash 18-live-zugang-setzen.sh
set -euo pipefail

CFG=~/.ssh/config
DATENSERVER="ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 root@192.168.178.163"

echo "--- Read connection data (DJ block) and announcement account (bot)"
DJ=$(${DATENSERVER} "pct exec 106 -- docker exec azuracast sh -c \"sed -n '/LIVE SENDEN/,/^4)/p' /var/azuracast/radio-zugang.txt\"" 2>/dev/null || true)
BOT=$(${DATENSERVER} "pct exec 106 -- docker exec azuracast sh -c \"awk '/Ansagestimme/{f=1} f' /var/azuracast/radio-zugang.txt\"" 2>/dev/null || true)
PASSWORT=$(${DATENSERVER} "pct exec 106 -- docker exec azuracast sh -c 'cat /var/azuracast/bot_streamer_passwort.txt'" 2>/dev/null | tr -d '\r\n' || true)

if [ -z "$DJ" ] || [ -z "$BOT" ] || [ -z "$PASSWORT" ]; then
  echo "ERROR: Announcement access not readable (/var/azuracast/radio-zugang.txt or bot_streamer_passwort.txt)"
  exit 1
fi

# Build the LIVE_* lines and pass them on without output.
{
  printf '%s\n###BOT###\n%s\n' "$DJ" "$BOT" | python3 -c "
import re, sys
dj, bot = sys.stdin.read().split('###BOT###')
def wert(schlussel, vorgabe, text):
    m = re.search(schlussel + r'\s*:\s*(\S+)', text)
    return m.group(1) if m else vorgabe
server = wert('Server', '192.168.178.33', dj)
port = wert('Port', '8005', dj)
mount = wert('Mountpoint', '/', dj)
user = wert('Streamer-user', '', bot)
print(f'LIVE_HOST={server}')
print(f'LIVE_PORT={port}')
print(f'LIVE_MOUNT={mount}')
print(f'LIVE_USER={user}')
"
  printf 'LIVE_PASSWORD=%s\n' "$PASSWORT"
  echo "LIVE_NAME=Deadline Beats Moderation"
} | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c '
  set -e
  FILE=/opt/radio-tts/geheim.env
  cp \"\$FILE\" \"\$FILE.before-live-$(date +%Y%m%d-%H%M%S)\"
  grep -v \"^LIVE_\" \"\$FILE\" > /tmp/geheim.new
  cat >> /tmp/geheim.new
  mv /tmp/geheim.new \"\$FILE\"
  chmod 600 \"\$FILE\"
  echo \"secret.env updated: \$(grep -c \\\"^LIVE_\\\" \"\$FILE\") LIVE lines\"’"

echo "--- Restart service (so the variables take effect)"
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc 'cd /opt/radio-tts && docker compose up -d radio-tts 2>&1 | tail -2'"

for i in $(seq 1 30); do
  C=$(curl -s -o /dev/null -w "%{http_code}" http://192.168.178.53:8881/health || true)
  [ "$C" = "200" ] && break
  sleep 2
done
echo "Health: $C"
echo "--- Check (without access values)"
curl -s http://192.168.178.53:8881/announce/status | python3 -c "
import json, sys
d = json.load(sys.stdin)
live = d['live']
print(' Server  :', live['host'], '| Port:', live['port'], '| Mount:', live['mount'])
print(' User:', live['user'] or '(failed)', '| Password set:', live['password_set'])
print(' Voice  :', d['voice'])
"
