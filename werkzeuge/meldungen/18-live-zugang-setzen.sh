#!/usr/bin/env bash
# Trägt den Ansage-Zugang (Live-Weg) in die Zugangsdatei des Dienstes ein.
#
# Der Dienst spricht Ansagen über den DJ-Hafen des Senders in den laufenden
# Betrieb (POST /live). Dafür braucht er Server, Port, Mountpoint, Benutzer und
# Passwort als Umgebungsvariablen LIVE_*.
#
# Wichtig: Die Ansagen laufen über ein EIGENES Streamer-Konto des Bots
# (Original: deine-stimme, Anzeigename "DEINE-STIMME") - so erscheint im Sender "DEINE-STIMME" und
# nicht der Betreibername. Der Betreiberzugang (betreiber) bleibt getrennt.
#
# Die Werte werden aus der Zugangsdatei des Senders gelesen und direkt in
# /opt/radio-tts/geheim.env geschrieben - sie erscheinen nie im Terminal.
#
# Aufruf:  bash 18-live-zugang-setzen.sh
set -euo pipefail

CFG=~/.ssh/config
DATENSERVER="ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 root@192.168.178.163"

echo "--- Verbindungsdaten (DJ-Block) und Ansage-Konto (Bot) lesen"
DJ=$(${DATENSERVER} "pct exec 106 -- docker exec azuracast sh -c \"sed -n '/LIVE SENDEN/,/^4)/p' /var/azuracast/radio-zugang.txt\"" 2>/dev/null || true)
BOT=$(${DATENSERVER} "pct exec 106 -- docker exec azuracast sh -c \"awk '/Ansagestimme/{f=1} f' /var/azuracast/radio-zugang.txt\"" 2>/dev/null || true)
PASSWORT=$(${DATENSERVER} "pct exec 106 -- docker exec azuracast sh -c 'cat /var/azuracast/bot_streamer_passwort.txt'" 2>/dev/null | tr -d '\r\n' || true)

if [ -z "$DJ" ] || [ -z "$BOT" ] || [ -z "$PASSWORT" ]; then
  echo "FEHLER: Ansage-Zugang nicht lesbar (/var/azuracast/radio-zugang.txt bzw. bot_streamer_passwort.txt)"
  exit 1
fi

# Die LIVE_*-Zeilen bauen und ohne Ausgabe weiterreichen.
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
benutzer = wert('Streamer-Benutzer', '', bot)
print(f'LIVE_HOST={server}')
print(f'LIVE_PORT={port}')
print(f'LIVE_MOUNT={mount}')
print(f'LIVE_USER={benutzer}')
"
  printf 'LIVE_PASSWORD=%s\n' "$PASSWORT"
  echo "LIVE_NAME=Deadline Beats Moderation"
} | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c '
  set -e
  DATEI=/opt/radio-tts/geheim.env
  cp \"\$DATEI\" \"\$DATEI.vor-live-$(date +%Y%m%d-%H%M%S)\"
  grep -v \"^LIVE_\" \"\$DATEI\" > /tmp/geheim.neu
  cat >> /tmp/geheim.neu
  mv /tmp/geheim.neu \"\$DATEI\"
  chmod 600 \"\$DATEI\"
  echo \"geheim.env aktualisiert: \$(grep -c \\\"^LIVE_\\\" \"\$DATEI\") LIVE-Zeilen\"'"

echo "--- Dienst neu starten (damit die Variablen greifen)"
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc 'cd /opt/radio-tts && docker compose up -d radio-tts 2>&1 | tail -2'"

for i in $(seq 1 30); do
  C=$(curl -s -o /dev/null -w "%{http_code}" http://192.168.178.53:8881/health || true)
  [ "$C" = "200" ] && break
  sleep 2
done
echo "Gesundheit: $C"
echo "--- Kontrolle (ohne Zugangswerte)"
curl -s http://192.168.178.53:8881/ansage/status | python3 -c "
import json, sys
d = json.load(sys.stdin)
live = d['live']
print('  Server  :', live['host'], '| Port:', live['port'], '| Mount:', live['mount'])
print('  Benutzer:', live['benutzer'] or '(fehlt)', '| Passwort gesetzt:', live['passwort_gesetzt'])
print('  Stimme  :', d['stimme'])
"
