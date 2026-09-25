#!/usr/bin/env bash
# Sets up the Telegram command menu of the bot.
TOKEN=$(cat /tmp/.tgtok)
curl -s -X POST "https://api.telegram.org/bot$TOKEN/setMyCommands" \
  -H 'Content-Type: application/json' \
  -d '{
    "commands": [
      {"command": "wish", "description": "Search for title in entire archive and enqueue"},
      {"command": "now", "description": "Play title immediately (interrupts current)"},
      {"command": "search", "description": "Only search, show hits for selection"},
      {"command": "now", "description": "What’s currently playing, what comes next"},
      {"command": "last", "description": "Recently played titles"},
      {"command": "help", "description": "Overview of commands"}
    ]
  }' | head -c 200
echo
echo "--- set commands:"
curl -s "https://api.telegram.org/bot$TOKEN/getMyCommands" | python3 -c "
import json,sys
for b in json.load(sys.stdin)['result']:
    print(' ', b['command'], '-', b['description'])
"
