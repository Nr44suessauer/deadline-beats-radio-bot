#!/bin/bash
# Testet die Listen-Aufgaben des Dienstes (ohne Telegram, ohne Sendebetrieb).
# Aufruf:  bash 09-dienst-test.sh
set -uo pipefail

CFG=~/.ssh/config
BOT="192.168.178.53:8881"

ruf() {   # ruf <pfad> <json>
  ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc 'curl -s -X POST http://$BOT$1 \
    -H \"Content-Type: application/json\" -d '\''$2'\'''"
}

zeig() {  # zeig <bezeichnung> <json>
  echo "--- $1"
  python3 -c "
import json,sys
d = json.loads(sys.stdin.read())
print('  ' + str(d.get('antwort',''))[:600].replace(chr(10), chr(10) + '  '))
t = d.get('tastatur') or {}
k = t.get('inline_keyboard') or []
if k:
    print('  Knoepfe: ' + ' | '.join(x['text'][:40] for zeile in k for x in zeile))
"
}

sag() { printf '\n=== %s ===\n' "$1"; }

CHAT="test-$$"

sag "1) Listen auflisten"
ruf /playlist/befehl "{\"chatId\":\"$CHAT\",\"text\":\"welche Wiedergabelisten gibt es\"}" | zeig "Antwort"

sag "2) Playlist bauen (Auswahlmenue)"
ruf /playlist/befehl "{\"chatId\":\"$CHAT\",\"text\":\"baue eine Playlist Sommer aus Scooter\"}" > /tmp/m1.json
zeig "Antwort" < /tmp/m1.json

sag "3) Zwei Titel anklicken"
ruf /playlist/knopf "{\"chatId\":\"$CHAT\",\"daten\":\"p1\"}" > /tmp/m2.json
zeig "nach p1" < /tmp/m2.json
ruf /playlist/knopf "{\"chatId\":\"$CHAT\",\"daten\":\"p3\"}" > /tmp/m3.json
zeig "nach p3" < /tmp/m3.json

sag "4) Fertig -> Liste anlegen"
ruf /playlist/knopf "{\"chatId\":\"$CHAT\",\"daten\":\"pf\"}" | zeig "Antwort"

sag "5) In der Senderschnittstelle pruefen"
ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 root@192.168.178.163 \
 "pct exec 106 -- docker exec azuracast gosu mysql azuracast_db -t -e \"select id,name,type,source from station_playlists order by id desc limit 3;\"" | tail -8

sag "6) Kein Abspielen (px = genug)"
ruf /playlist/knopf "{\"chatId\":\"$CHAT\",\"daten\":\"px\"}" | zeig "Antwort"

sag "7) Inhalt ansehen"
ruf /playlist/befehl "{\"chatId\":\"$CHAT\",\"text\":\"was ist in der Playlist Sommer\"}" | zeig "Antwort"

sag "8) Umbenennen"
ruf /playlist/befehl "{\"chatId\":\"$CHAT\",\"text\":\"benenne die Playlist Sommer in Sommer Test um\"}" | zeig "Antwort"

sag "9) Leeren (mit Rueckfrage)"
ruf /playlist/befehl "{\"chatId\":\"$CHAT\",\"text\":\"leere die Playlist Sommer Test\"}" | zeig "Rueckfrage"
ruf /playlist/knopf "{\"chatId\":\"$CHAT\",\"daten\":\"j\"}" | zeig "nach Ja"

sag "10) Loeschen (mit Rueckfrage)"
ruf /playlist/befehl "{\"chatId\":\"$CHAT\",\"text\":\"loesche die Playlist Sommer Test\"}" | zeig "Rueckfrage"
ruf /playlist/knopf "{\"chatId\":\"$CHAT\",\"daten\":\"j\"}" | zeig "nach Ja"

sag "11) Listenwahl ohne Namen"
ruf /playlist/befehl "{\"chatId\":\"$CHAT\",\"text\":\"spiele eine Playlist\"}" | zeig "Antwort"

sag "12) Unbekannter Auftrag"
ruf /playlist/befehl "{\"chatId\":\"$CHAT\",\"text\":\"mach irgendwas mit dem Sender\"}" | zeig "Antwort"

sag "13) Zustand am Ende"
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc 'curl -s http://$BOT/playlist/status'"
echo
