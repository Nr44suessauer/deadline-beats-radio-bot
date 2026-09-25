#!/usr/bin/env bash
# Richtet das Telegram-Befehlsmenue des Bots ein.
TOKEN=$(cat /tmp/.tgtok)
curl -s -X POST "https://api.telegram.org/bot$TOKEN/setMyCommands" \
  -H 'Content-Type: application/json' \
  -d '{
    "commands": [
      {"command": "wunsch", "description": "Titel im ganzen Archiv suchen und einreihen"},
      {"command": "sofort", "description": "Titel sofort spielen (unterbricht das Laufende)"},
      {"command": "suche", "description": "Nur suchen, Treffer zum Auswaehlen"},
      {"command": "jetzt", "description": "Was laeuft gerade, was kommt danach"},
      {"command": "letzte", "description": "Zuletzt gespielte Titel"},
      {"command": "hilfe", "description": "Uebersicht der Befehle"}
    ]
  }' | head -c 200
echo
echo "--- gesetzte Befehle:"
curl -s "https://api.telegram.org/bot$TOKEN/getMyCommands" | python3 -c "
import json,sys
for b in json.load(sys.stdin)['result']:
    print(' ', b['command'], '-', b['description'])
"
