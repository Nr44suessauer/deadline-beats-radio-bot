#!/usr/bin/env bash
# Vollstaendiger Durchlauf des Bots (laeuft im Container 103).
# Aufruf: durchlauf.sh
set -u
frage() {  # frage <text>
  printf '%-52s ' "$1"
  bash /tmp/frage.sh "$1" 1 > /tmp/.letzte 2>&1
  cat /tmp/.letzte | tr -d '\n'
  echo
  sleep 4
}

echo "--- Textbefehle ohne Schraegstrich (sollen sofort spielen) ---"
frage "spiele nirvana lithium"
frage "spiele raamstein du hast"          # falsch geschrieben: muss trotzdem treffen
frage "spiele schnee"                      # mehrdeutig: soll eine Auswahl zeigen
frage "leg mal was von den toten hosen auf"

echo "--- Reihenfolge (soll einreihen, nicht sofort) ---"
frage "spiele benzin von rammstein und danach etwas von nirvana"

echo "--- Status und Hilfe ---"
frage "/hilfe"
frage "/jetzt"
frage "/letzte"
frage "/suche rammstein"

echo "--- Nichts gefunden ---"
frage "zzqqxxyy"

echo "--- Schraegstrich-Wunsch ---"
frage "/wunsch ace of spades"
