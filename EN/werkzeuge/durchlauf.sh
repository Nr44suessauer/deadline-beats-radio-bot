#!/usr/bin/env bash
# Complete run of the bot (runs in container 103).
# Call: durchlauf.sh
set -u
question() {  # ask <text>
  printf '%-52s' "$1"
  bash /tmp/question.sh "$1" 1 > /tmp/.last 2>&1
  cat /tmp/.last | tr -d '\n'
  echo
  sleep 4
}

echo "--- Text commands without slash (should play immediately) ---"
question "play nirvana lithium"
question "play rammstein du hast"          # wrongly spelled: must still hit
question "play snow"                      # ambiguous: should show a selection
question "put on something from the dead pants"

echo "--- Order (should queue, not play immediately) ---"
question "play gasoline by rammstein and then something from nirvana"

echo "--- Status and Help ---"
question "/help"
question "/now"
question "/last"
question "/search rammstein"

echo "--- Nothing found ---"
question "zzqqxxyy"

echo "--- Slash wish ---"
question "/wish ace of spades"
