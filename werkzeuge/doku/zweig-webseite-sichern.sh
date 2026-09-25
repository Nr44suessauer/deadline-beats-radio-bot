#!/usr/bin/env bash
# Baut die Veröffentlichungsfassung von Sender 1 und spiegelt sie in den
# Git-Zweig `webseite`; schiebt den Zweig zu origin. Der Arbeitsordner bleibt
# unberuehrt.
#
# Die Fassung entsteht mit `veroeffentlichung-webseite.py`:
#   - Platzhalter statt Zugangswerte (ueber doc-official-bauen.py),
#   - keine fremde Stimme und keine Stimmdaten; die eigene Wunschstimme steht
#     als Platzhalter in DOKU/STIMME.md und der Vorlage NACHBAU/eigene-stimme/.
#
# Der Zweig enthaelt den Inhalt FLACH (README.md, DOKU/, EN/, ...) - so ist er
# direkt als eigenstaendiges Paket lesbar und veroeffentlichbar.
#
# Aufruf:  bash zweig-webseite-sichern.sh ["Kommentar fuer die Festschreibung"]
set -euo pipefail

HIER="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HIER/../../../.." && pwd)"
TMP="$(mktemp -d /tmp/webseite-zweig.XXXXXX)"

aufraeumen() {
  cd "$REPO"
  git worktree remove --force "$TMP/zweig" >/dev/null 2>&1 || true
  rm -rf "$TMP"
}
trap aufraeumen EXIT

echo "--- Fassung bauen (Platzhalter, ohne fremde Stimme)"
python3 "$HIER/veroeffentlichung-webseite.py" --ziel "$TMP/fassung" | tail -4

cd "$REPO"
if git show-ref --verify --quiet refs/heads/webseite; then
  git worktree add -q "$TMP/zweig" webseite
else
  echo "Zweig webseite wird angelegt (erster Lauf)."
  git worktree add -q --detach "$TMP/zweig"
  cd "$TMP/zweig"
  git checkout -q --orphan webseite
  git rm -rf -q . >/dev/null 2>&1 || true
  cd "$REPO"
fi

# Zweig leeren und mit der frischen Fassung fuellen.
find "$TMP/zweig" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -a "$TMP/fassung/." "$TMP/zweig/"

cd "$TMP/zweig"
git add -A
if git diff --cached --quiet; then
  echo "Keine Aenderungen — Zweig webseite ist aktuell."
else
  git commit -q -m "${1:-Veroeffentlichungsfassung Sender 1 (DE+EN, Platzhalter, ohne fremde Stimme)}"
  echo "Festschreibung: $(git log --oneline -1)"
fi
git push -q -u origin webseite
echo "Zweig webseite ist bei origin aktuell."
