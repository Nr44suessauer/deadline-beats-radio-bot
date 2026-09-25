#!/bin/bash
# Verschiebt die Live-/Bootleg-Sammelordner nach "_Archiv/Live/<alte Struktur>".
#
# Wichtig: benutzt die AzuraCast-Sammelaktion "move" (PUT /station/1/files/batch).
# Die schreibt den Pfad in der Datenbank mit um -> Medien-Kennung, unique_id,
# Wiedergabelisten-Zuordnungen und Wunsch-Eintraege bleiben erhalten.
# (Ein Verschieben auf der Platte wuerde die Eintraege loeschen und neu anlegen.)
#
# Aufruf:  bash 03-live-verschieben.sh            -> Trockenlauf (zeigt nur)
#          bash 03-live-verschieben.sh echt       -> fuehrt aus
set -uo pipefail

SSH="ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 root@192.168.178.163"
MODUS=${1:-trocken}

$SSH "MODUS=$MODUS LIMIT=${LIMIT:-0} bash -s" <<'ENDE'
set -uo pipefail
BASE=http://192.168.178.33
ARCHIV="_Archiv/Live"
zaehler=0

KEY=$(pct exec 106 -- docker exec azuracast cat /var/azuracast/api_key.txt 2>/dev/null \
      | grep -oE '[0-9a-f]{16}:[0-9a-f]{32}' | head -1)
if [ -z "$KEY" ]; then
  # Ersatzweg: Schluessel aus der Zugangsdatei, aber nur einen, der auch in der DB steht
  KENNUNG=$(pct exec 106 -- docker exec azuracast gosu mysql azuracast_db -N -e "select id from api_keys limit 1" | tr -d '[:space:]')
  KEY=$(grep -oE "[0-9a-f]{16}:[0-9a-f]{32}" /root/azuracast-zugang.txt | grep "^$KENNUNG:" | head -1)
fi
[ -n "$KEY" ] || { echo "Kein gueltiger API-Schluessel gefunden"; exit 1; }

# Probe: geschuetzter Endpunkt muss 200 liefern
PROBE=$(curl -s -o /dev/null -w '%{http_code}' -H "X-API-Key: $KEY" \
        "$BASE/api/station/1/files?rowCount=1")
if [ "$PROBE" != "200" ]; then
  echo "API-Schluessel wird abgelehnt (HTTP $PROBE) - Abbruch"
  exit 1
fi

SICHERUNG=$(ls -d /root/azuracast-aufraeumen-* 2>/dev/null | sort | tail -1)
[ -n "$SICHERUNG" ] || { echo "Keine Sicherung gefunden - erst 01-sicherung.sh laufen lassen"; exit 1; }
LOG="$SICHERUNG/live-verschieben.tsv"

# nur die obersten Ordner (verschachtelte kommen mit dem Elternordner mit)
awk '{ ok=1; for (i=1;i<=n;i++) if (index($0, roots[i]"/")==1) { ok=0; break }
       if (ok) roots[++n]=$0 } END { for (i=1;i<=n;i++) print roots[i] }' \
  /tmp/live_sammelordner.txt > /tmp/live_oben.txt

echo "Oberste Ordner zum Verschieben: $(wc -l < /tmp/live_oben.txt)"
echo "Sicherung/Protokoll: $SICHERUNG"
echo

while IFS= read -r ordner; do
  # schon verschoben (oder nicht mehr vorhanden)? dann ueberspringen
  if [ ! -d "/mnt/Content/Music/$ordner" ]; then
    echo "uebersprungen (nicht mehr vorhanden): $ordner"
    continue
  fi

  vater=$(dirname "$ordner")
  ziel="$ARCHIV/$vater"

  if [ "$MODUS" != "echt" ]; then
    echo "[trocken]  $ordner"
    echo "           -> $ziel/$(basename "$ordner")"
    continue
  fi

  zaehler=$((zaehler+1))
  if [ "$LIMIT" -gt 0 ] && [ "$zaehler" -gt "$LIMIT" ]; then
    echo "(Limit $LIMIT erreicht - Rest uebersprungen)"
    break
  fi

  antwort=$(python3 -c 'import json,sys
print(json.dumps({"do":"move","currentDirectory":sys.argv[1],"directory":sys.argv[2],"dirs":[sys.argv[3]]}))' \
    "$vater" "$ziel" "$ordner" \
    | curl -s -X PUT -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
           --data-binary @- "$BASE/api/station/1/files/batch")

  printf '%s\t%s\t%s\n' "$ordner" "$ziel" "$antwort" >> "$LOG"
  if echo "$antwort" | grep -q '"errors":\[\]'; then
    echo "verschoben: $ordner"
  else
    echo "FEHLER bei $ordner -> $antwort"
  fi
done < /tmp/live_oben.txt

if [ "$MODUS" = "echt" ]; then
  echo
  echo "Protokoll: $LOG"
fi
ENDE
