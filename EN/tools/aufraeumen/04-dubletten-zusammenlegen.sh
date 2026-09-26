##!/bin/bash
# Merges duplicate artist folders without losing database assignments.
#
# Each “Discography” folder ends up as a subfolder under the artist:
# unsorted/Korn (KoЯn) - Diskografie - [1993 - 2025]  ->  Korn/Diskografie/
# Led.Zeppelin.1969-2018                              ->  Led Zeppelin/Diskografie/
# If “Discography” already exists, “Discography 2”, etc. is used.
#
# The moving process runs through the AzuraCast collection action “move”
# (Paths are recorded in the database, identifiers remain intact).
# Only the loose advertising/text files (no media) are directly moved on the disk
# because AzuraCast does not know them.
#
# Call:  bash 04-dubletten-zusammenlegen.sh            -> Dry run
#          bash 04-dubletten-zusammenlegen.sh echt       -> ausfuehren
set -uo pipefail

SSH="ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 root@192.168.178.163"
MODUS=${1:-dry}

$SSH "MODUS=$MODUS bash -s" <<'ENDE'
set -uo pipefail
BASE=http://192.168.178.33
MUSIK=/mnt/Content/Music

KEY=$(pct exec 106 -- docker exec azuracast cat /var/azuracast/api_key.txt 2>/dev/null \
      | grep -oE '[0-9a-f]{16}:[0-9a-f]{32}' | head -1)
[ -n "$KEY" ] || { echo "No valid API key found"; exit 1; }

SICHERUNG=$(ls -d /root/azuracast-cleanup-* 2>/dev/null | sort | tail -1)
LOG="$SICHERUNG/dubletten-zusammenlegen.tsv"

# Source<TAB>Target artist
PAARE=$(mktemp)
cat > "$PAARE" <<'LISTE'
unsorted/The Prodigy - Diskografie - [1990 - 2024]	The Prodigy
unsorted/Pink Floyd - Diskografie - [1967 - 2025]	Pink Floyd
unsorted/Modern Talking - Diskografie - [1984 - 2024]	Modern Talking
unsorted/Bon Jovi - Diskografie - [1984 - 2025]	Bon Jovi
unsorted/Guns N' Roses (Guns N Roses) - Diskografie - [1987 - 2025]	Guns N’ Roses
unsorted/Korn (KoЯn) - Diskografie - [1993 - 2025]	Korn
unsorted/50 Cent - Diskografie - [1999 - 2019]	50 Cent
unsorted/Motley Crue - Diskografie - [1981 - 2025]	Mötley Crüe
unsorted/Pearl Jam - Diskografie - [1990 - 2025]	Pearl Jam
unsorted/Maroon 5 - Diskografie - [1994 - 2025]	Maroon 5
unsorted/HammerFall - Diskografie - [1997 - 2024]	HammerFall
unsorted/Rick James - Diskografie - [1978 - 2010]	Rick James
unsorted/SDP - Diskografie - [2004 - 2025]	SDP
unsorted/Papa Roach - Diskografie - [1994 - 2025]	Papa Roach
unsorted/Nickelback - Diskografie - [1996 - 2025]	Nickelback
unsorted/Dio - Diskografie - [1983 - 2022]	Dio
unsorted/K.I.Z. - Diskografie - [2005 - 2025]	K.I.Z
unsorted/The Offspring - Diskografie - [1989 - 2025]	The Offspring
unsorted/The Bosshoss - Diskografie - [2005 - 2025]	The BossHoss
unsorted/The Outfield - Diskografie - [1985 - 2011]	The Outfield
unsorted/Alligatoah - Diskografie - [2006 - 2025]	Alligatoah
Led.Zeppelin.1969-2018	Led Zeppelin
HammerFall - Diskografie - [1997 - 2024]	HammerFall
Good Charlotte - Discography (2000-2025)	Good Charlotte
LISTE

while IFS=$'\t' read -r source artists; do
  [ -d "$MUSIK/$source" ] || { echo "skipped (missing): $source"; continue; }

  # finding free target name: Discography, Discography 2, ...
  zielname="Diskografie"; k=2
  while [ -d "$MUSIK/$artists/$zielname" ]; do zielname="Diskografie $k"; k=$((k+1)); done
  target="$artists/$zielname"

  if [ "$MODUS" != "echt" ]; then
    printf '%5d Subfolder  %s  ->  %s/\n' \
      "$(find"$MUSIK/$source" -mindepth 1 -maxdepth 1 -type d | wc -l)" "$source" "$target"
    continue
  fi

  DL=$(mktemp); FL=$(mktemp)
  find "$MUSIK/$source" -mindepth 1 -maxdepth 1 -type d -printf "$source/%f\n" > "$DL"
  find "$MUSIK/$source" -mindepth 1 -maxdepth 1 -type f -printf "$source/%f\n" > "$FL"

  answer=$(python3 -c 'import json,sys
print(json.dumps({"do":"move","currentDirectory":sys.argv[1],"directory":sys.argv[2],
 "dirs":[l.rstrip("\n") for l in open(sys.argv[3]) if l.strip()],
 "files":[l.rstrip("\n") for l in open(sys.argv[4]) if l.strip()]}))' \
    "$source" "$target" "$DL" "$FL" \
    | curl -s -X PUT -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
           --data-binary @- "$BASE/api/station/1/files/batch")

  # loose files (ad/text files) are not known to AzuraCast -> move directly
  mkdir -p "$MUSIK/$target"
  while IFS= read -r f; do
    [ -f "$MUSIK/$f" ] && mv "$MUSIK/$f" "$MUSIK/$target/"
  done < "$FL"
  rm -f "$DL" "$FL"

  rmdir "$MUSIK/$source" 2>/dev/null && rest="(Folder removed)" || rest="(not empty: $(ls"$MUSIK/$source" 2>/dev/null | wc -l) entries remain)"
  printf '%s\t%s\t%s\n' "$source" "$target" "$answer" >> "$LOG"
  echo "$source  ->  $target/  $rest"
done < "$PAARE"

if [ "$MODUS" = "echt" ]; then
  echo
  echo "Empty remainder folders:"
  find "$MUSIK" -mindepth 1 -maxdepth 2 -type d -empty -print 2>/dev/null | head -10
  echo "Log: $LOG"
fi
rm -f "$PAARE"
ENDE
