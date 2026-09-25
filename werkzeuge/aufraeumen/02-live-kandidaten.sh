#!/bin/bash
# Ermittelt Ordner, die reine Live-/Bootleg-SAMMELORDNER sind.
# Eng gefasst: der Ordnername besteht nur aus Live-/Bootleg-Woertern
# (z. B. "Live", "Lives", "Live Albums", "03 - Live & Bootleg", "Bootlegs",
# "Concerts", "! Live, Bootlegs", "Compilations, Bootlegs").
# Studioalben wie "Songs That Live Forever" fallen damit NICHT darunter.
set -uo pipefail

ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 root@192.168.178.163 bash -s <<'ENDE'
cd /mnt/Content/Music || exit 1

find . -type f \( -iname '*.mp3' -o -iname '*.flac' -o -iname '*.m4a' -o -iname '*.mp4' \
                -o -iname '*.wav' -o -iname '*.opus' -o -iname '*.wma' \) -printf '%P\n' \
  | LC_ALL=C sort > /tmp/alle_dateien.txt

find . -type d -printf '%P\n' | LC_ALL=C sort | awk '
  function kern(s,   t) {
    t = tolower(s)
    gsub(/^[0-9]+[ ._-]*/, "", t)     # Nummerierung "03 - " entfernen
    gsub(/^[^a-z]+/, "", t)           # fuehrende Sonderzeichen entfernen
    gsub(/[^a-z]+$/, "", t)           # End-Sonderzeichen entfernen
    gsub(/^[ ,&\/-]+|[ ,&\/-]+$/, "", t)
    return t
  }
  {
    n = split($0, teile, "/")
    t = kern(teile[n])                 # nur der Ordnername selbst
    if (t ~ /^(live|lives|bootleg|bootlegs|concert|concerts)([ ,&\/-]+(live|lives|bootleg|bootlegs|concert|concerts|rare|albums|album))*$/)
      print $0
  }' > /tmp/live_sammelordner.txt

echo "Reine Live-/Bootleg-Sammelordner: $(wc -l < /tmp/live_sammelordner.txt)"
echo
printf '%6s  %s\n' "Dateien" "Ordner"
while IFS= read -r w; do
  n=$(awk -v w="$w" 'index($0, w"/")==1 {c++} END{print c+0}' /tmp/alle_dateien.txt)
  if [ "$n" -gt 0 ]; then printf '%6d  %s\n' "$n" "$w"; fi
done < /tmp/live_sammelordner.txt | sort -rn
ENDE

