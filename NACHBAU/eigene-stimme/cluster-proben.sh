#!/usr/bin/env bash
# Hoerproben der Sprecher-Cluster eines Stimm-Datasets per Telegram senden.
#
# Aufruf:   cluster-proben.sh <dataset> [proben-je-cluster] [nur-dieser-cluster]
# Beispiel: cluster-proben.sh konosuba 2
#           cluster-proben.sh konosuba 2 cluster_3
#
# Holt den Telegram-Zugang aus dem n8n-Ablauf "Konfiguration" (CT 103),
# wandelt je Cluster die laengsten Segmente in Sprachnachrichten (OGG/Opus)
# und sendet sie an den Chat. Am Ende kommt die Frage, welcher Cluster der
# Wunschsprecher ist.
set -euo pipefail
CFG=${CFG:-~/.ssh/config}
NAME=${1:?Bitte Dataset-Namen angeben (z.B. konosuba)}
JE=${2:-2}
NUR=${3:-}
CHAT=${TG_CHAT:-DEINE-CHAT-ID}
CT=${CT:-111}
DS="/opt/Applio/assets/datasets/$NAME"

# --- Telegram-Zugang besorgen (steht im n8n-Ablauf "Konfiguration")
TOKEN=$(ssh -F "$CFG" ai-server \
  "pct exec 103 -- bash -lc 'docker exec -u node n8n n8n export:workflow --id=Konfiguration --output=/tmp/konf.json >/dev/null 2>&1; docker cp n8n:/tmp/konf.json - 2>/dev/null'" \
  | python3 -c "import sys,re; t=re.findall(r'[0-9]{8,}:[A-Za-z0-9_-]{30,}', sys.stdin.read()); print(t[0] if t else '')")
[ -n "$TOKEN" ] || { echo "Kein Telegram-Zugang gefunden."; exit 1; }

# --- Proben im Container bauen und senden
ssh -F "$CFG" ai-server "pct exec $CT -- bash -s" <<REMOTE
set -uo pipefail
TOKEN='$TOKEN'
CHAT='$CHAT'
DS='$DS'
NAME='$NAME'
JE=$JE
NUR='$NUR'
mkdir -p /tmp/proben
gefunden=0
for d in \$(ls -d \$DS/cluster_* 2>/dev/null | sort -V); do
  [ -d "\$d" ] || continue
  kurz=\$(basename "\$d")
  [ -z "\$NUR" ] || [ "\$kurz" = "\$NUR" ] || continue
  n=\$(find "\$d" -name '*.wav' | wc -l)
  [ "\$n" -gt 0 ] || continue
  echo "--- \$kurz: \$n Segmente"
  t=0
  for f in \$(ls -S "\$d"/*.wav 2>/dev/null | head -n \$JE); do
    t=\$((t+1))
    out=/tmp/proben/probe.ogg
    if ! ffmpeg -nostdin -y -i "\$f" -t 9 -ac 1 -ar 48000 -c:a libopus -b:a 48k "\$out" >/dev/null 2>&1; then
      echo "    ffmpeg fehlgeschlagen: \$f"; continue
    fi
    curl -s -o /tmp/tg.json -m 60 \\
      -F chat_id="\$CHAT" -F voice=@"\$out" \\
      -F caption="\$NAME · \$kurz · Probe \$t · \$n Segmente" \\
      "https://api.telegram.org/bot\$TOKEN/sendVoice"
    if grep -q '"ok":true' /tmp/tg.json; then
      echo "    Probe \$t gesendet"
    else
      echo "    Senden fehlgeschlagen:"; head -c 200 /tmp/tg.json; echo
    fi
    sleep 1
  done
  gefunden=1
done
if [ "\$gefunden" = "0" ]; then
  echo "Keine Cluster gefunden unter \$DS"
  exit 1
fi
curl -s -o /tmp/tg2.json -m 60 -F chat_id="\$CHAT" \\
  -F text="Das waren die Sprecher-Cluster von \$NAME. Antworte mit dem Namen (z. B. cluster_2), welcher davon der Wunschsprecher ist – dann starte ich das RVC-Training." \\
  "https://api.telegram.org/bot\$TOKEN/sendMessage" >/dev/null
echo "Fertig."
REMOTE
