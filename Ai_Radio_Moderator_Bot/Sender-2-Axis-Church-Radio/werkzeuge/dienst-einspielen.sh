#!/bin/bash
# Spielt den Dienst der DDD-Webseite-Fassung auf die Bot-Maschine (LXC 103 auf
# ai-server) und startet ihn.
#
#   ddd-radio -> /opt/ddd-radio, Port 8882 (deutsche Schnittstelle)
#
# EIN Dienst fuer EINEN zweisprachigen Bot: die Ansagen sprechen den Text, den
# sie bekommen (deutsch oder englisch) - eine zweite Instanz braucht es nicht.
# Die alten Instanzen dieser Fassung (ddd-radio-de, ddd-radio-en) werden dabei
# entfernt. Der Dienst des Hauptbots radio-tts (Port 8881) bleibt unberuehrt;
# die Stimmen werden aus /opt/radio-tts/voices KOPIERT.
#
# Aufruf:  bash dienst-einspielen.sh
set -euo pipefail

HIER="$(cd "$(dirname "$0")" && pwd)"
BASIS="$(cd "$HIER/.." && pwd)"
SSH="ssh -F /media/discData/docs/projects/proxmox-ssh/config ai-server"

echo "== 1) Quellordner uebertragen =="
tar czf - -C "$BASIS" dienst | $SSH "pct exec 103 -- bash -c 'mkdir -p /opt/ddd-radio && tar xzf - --strip-components=1 -C /opt/ddd-radio && chmod 600 /opt/ddd-radio/geheim.env'"
echo "  dienst -> /opt/ddd-radio uebertragen"

echo "== 2) Alte Instanzen dieser Fassung entfernen =="
$SSH "pct exec 103 -- bash -c '
docker rm -f ddd-radio-de ddd-radio-en >/dev/null 2>&1 || true
rm -rf /opt/ddd-radio-de /opt/ddd-radio-en
echo \"  aufgeraeumt: ddd-radio-de, ddd-radio-en\"'"

echo "== 3) Stimmen =="
$SSH "pct exec 103 -- bash -c '
set -e
mkdir -p /opt/ddd-radio/voices /opt/ddd-radio/daten
for f in /opt/radio-tts/voices/*; do
  cp -n \"\$f\" /opt/ddd-radio/voices/ 2>/dev/null || true
done
ls /opt/ddd-radio/voices | head -6
'"

echo "== 4) Container bauen und starten =="
$SSH "pct exec 103 -- bash -c 'cd /opt/ddd-radio && docker compose up -d --build 2>&1 | tail -2'"

echo "== 5) Warten und pruefen =="
sleep 12
echo -n "  /health:        "; curl -s -m 8 http://192.168.178.53:8882/health | head -c 220; echo
echo -n "  /meldungen/status:  "; curl -s -m 8 http://192.168.178.53:8882/meldungen/status | head -c 160; echo
echo -n "  Katalogtitel:   "; curl -s -m 8 "http://192.168.178.53:8882/katalog/status" | head -c 160; echo
