##!/bin/bash
# Moves the Live/Bootleg collection folders to “_Archiv/Live/<old structure>”.
#
# Important: uses the AzuraCast collection action “move” (PUT /station/1/files/batch).
# It writes the path in the database with -> Media identifier, unique_id,
# Playlist assignments and wish list entries remain intact.
# (A moving on the disk would delete the entries and recreate them.)
#
# Call:  bash 03-live-verschieben.sh            -> Dry run (shows only)
#          bash 03-live-verschieben.sh echt       -> fuehrt out
set -uo pipefail

SSH="ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 root@192.168.178.163"
MODUS=${1:-dry}

$SSH "MODUS=$MODUS LIMIT=${LIMIT:-0} bash -s" <<'ENDE'
set -uo pipefail
BASE=http://192.168.178.33
ARCHIV="_Archiv/Live"
counter=0

KEY=$(pct exec 106 -- docker exec azuracast cat /var/azuracast/api_key.txt 2>/dev/null \
      | grep -oE '[0-9a-f]{16}:[0-9a-f]{32}' | head -1)
if [ -z "$KEY" ]; then
  # Replacement path: key from the access file, but only one that also exists in the DB
  KENNUNG=$(pct exec 106 -- docker exec azuracast gosu mysql azuracast_db -N -e "select id from api_keys limit 1" | tr -d '[:space:]')
  KEY=$(grep -oE "[0-9a-f]{16}:[0-9a-f]{32}" /root/azuracast-zugang.txt | grep "^$KENNUNG:" | head -1)
fi
[ -n "$KEY" ] || { echo "No valid API key found"; exit 1; }

# Test: protected endpoint must return 200
PROBE=$(curl -s -o /dev/null -w '%{http_code}' -H "X-API-Key: $KEY" \
        "$BASE/api/station/1/files?rowCount=1")
if [ "$PROBE" != "200" ]; then
  echo "API key is rejected (HTTP $PROBE) - aborting"
  exit 1
fi

SICHERUNG=$(ls -d /root/azuracast-cleanup-* 2>/dev/null | sort | tail -1)
[ -n "$SICHERUNG" ] || { echo "No backup found - run 01-sicherung.sh first"; exit 1; }
LOG="$SICHERUNG/live-verschieben.tsv"

# only the top-level folders (nested ones come with their parent folder)
awk '{ ok=1; for (i=1;i<=n;i++) if (index($0, roots[i]"/")==1) { ok=0; break }
       if (ok) roots[++n]=$0 } END { for (i=1;i<=n;i++) print roots[i] }' \
  /tmp/live_sammelordner.txt > /tmp/live_oben.txt

echo "Top-level folders to move: $(wc -l < /tmp/live_oben.txt)"
echo "Backup/Log: $SICHERUNG"
echo

while IFS= read -r folder; do
  # already moved (or no longer present)? then skip
  if [ ! -d "/mnt/Content/Music/$folder" ]; then
    echo "skipped (no longer present): $folder"
    continue
  fi

  vater=$(dirname "$folder")
  target="$ARCHIV/$vater"

  if [ "$MODUS" != "echt" ]; then
    echo "[dry-run] $folder"
    echo " -> $target/$(basename"$folder")"
    continue
  fi

  counter=$((counter+1))
  if [ "$LIMIT" -gt 0 ] && [ "$counter" -gt "$LIMIT" ]; then
    echo "(Limit $LIMIT reached - rest skipped)"
    break
  fi

  answer=$(python3 -c 'import json,sys
print(json.dumps({"do":"move","currentDirectory":sys.argv[1],"directory":sys.argv[2],"dirs":[sys.argv[3]]}))' \
    "$vater" "$target" "$folder" \
    | curl -s -X PUT -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
           --data-binary @- "$BASE/api/station/1/files/batch")

  printf '%s\t%s\t%s\n' "$folder" "$target" "$answer" >> "$LOG"
  if echo "$answer" | grep -q '"errors":\[\]'; then
    echo "moved: $folder"
  else
    echo "ERROR at $folder -> $answer"
  fi
done < /tmp/live_oben.txt

if [ "$MODUS" = "echt" ]; then
  echo
  echo "Log: $LOG"
fi
ENDE
