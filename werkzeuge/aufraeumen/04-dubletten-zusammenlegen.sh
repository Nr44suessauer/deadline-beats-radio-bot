#!/bin/bash
# Legt doppelte Kuenstler-Ordner zusammen, ohne Datenbank-Zuordnungen zu verlieren.
#
# Jeder "Diskografie"-Ordner landet als Unterordner beim Kuenstler:
#   unsorted/Korn (KoЯn) - Diskografie - [1993 - 2025]  ->  Korn/Diskografie/
#   Led.Zeppelin.1969-2018                              ->  Led Zeppelin/Diskografie/
# Gibt es "Diskografie" schon, wird "Diskografie 2" usw. genommen.
#
# Das Verschieben laeuft ueber die AzuraCast-Sammelaktion "move"
# (Pfade werden in der Datenbank mitgeschrieben, Kennungen bleiben erhalten).
# Nur die losen Werbe-/Textdateien (keine Medien) werden direkt auf der Platte
# verschoben, weil AzuraCast sie nicht kennt.
#
# Aufruf:  bash 04-dubletten-zusammenlegen.sh            -> Trockenlauf
#          bash 04-dubletten-zusammenlegen.sh echt       -> ausfuehren
set -uo pipefail

SSH="ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 root@192.168.178.163"
MODUS=${1:-trocken}

$SSH "MODUS=$MODUS bash -s" <<'ENDE'
set -uo pipefail
BASE=http://192.168.178.33
MUSIK=/mnt/Content/Music

KEY=$(pct exec 106 -- docker exec azuracast cat /var/azuracast/api_key.txt 2>/dev/null \
      | grep -oE '[0-9a-f]{16}:[0-9a-f]{32}' | head -1)
[ -n "$KEY" ] || { echo "Kein gueltiger API-Schluessel gefunden"; exit 1; }

SICHERUNG=$(ls -d /root/azuracast-aufraeumen-* 2>/dev/null | sort | tail -1)
LOG="$SICHERUNG/dubletten-zusammenlegen.tsv"

# Quelle<TAB>Zielkuenstler
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

while IFS=$'\t' read -r quelle kuenstler; do
  [ -d "$MUSIK/$quelle" ] || { echo "uebersprungen (fehlt): $quelle"; continue; }

  # freien Zielnamen finden: Diskografie, Diskografie 2, ...
  zielname="Diskografie"; k=2
  while [ -d "$MUSIK/$kuenstler/$zielname" ]; do zielname="Diskografie $k"; k=$((k+1)); done
  ziel="$kuenstler/$zielname"

  if [ "$MODUS" != "echt" ]; then
    printf '%5d Unterordner  %s  ->  %s/\n' \
      "$(find "$MUSIK/$quelle" -mindepth 1 -maxdepth 1 -type d | wc -l)" "$quelle" "$ziel"
    continue
  fi

  DL=$(mktemp); FL=$(mktemp)
  find "$MUSIK/$quelle" -mindepth 1 -maxdepth 1 -type d -printf "$quelle/%f\n" > "$DL"
  find "$MUSIK/$quelle" -mindepth 1 -maxdepth 1 -type f -printf "$quelle/%f\n" > "$FL"

  antwort=$(python3 -c 'import json,sys
print(json.dumps({"do":"move","currentDirectory":sys.argv[1],"directory":sys.argv[2],
 "dirs":[l.rstrip("\n") for l in open(sys.argv[3]) if l.strip()],
 "files":[l.rstrip("\n") for l in open(sys.argv[4]) if l.strip()]}))' \
    "$quelle" "$ziel" "$DL" "$FL" \
    | curl -s -X PUT -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
           --data-binary @- "$BASE/api/station/1/files/batch")

  # lose Dateien (Werbe-/Textdateien) kennt AzuraCast nicht -> direkt verschieben
  mkdir -p "$MUSIK/$ziel"
  while IFS= read -r f; do
    [ -f "$MUSIK/$f" ] && mv "$MUSIK/$f" "$MUSIK/$ziel/"
  done < "$FL"
  rm -f "$DL" "$FL"

  rmdir "$MUSIK/$quelle" 2>/dev/null && rest="(Ordner entfernt)" || rest="(nicht leer: $(ls "$MUSIK/$quelle" 2>/dev/null | wc -l) Eintraege bleiben)"
  printf '%s\t%s\t%s\n' "$quelle" "$ziel" "$antwort" >> "$LOG"
  echo "$quelle  ->  $ziel/  $rest"
done < "$PAARE"

if [ "$MODUS" = "echt" ]; then
  echo
  echo "Leere Restordner:"
  find "$MUSIK" -mindepth 1 -maxdepth 2 -type d -empty -print 2>/dev/null | head -10
  echo "Protokoll: $LOG"
fi
rm -f "$PAARE"
ENDE
