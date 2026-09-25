#!/usr/bin/env bash
# Baut die Veröffentlichungsfassung und spiegelt sie in den
# Git-Zweig `webseite`; schiebt den Zweig zu origin. Der Arbeitsordner bleibt
# unberuehrt.
#
# Zum Schluss wird derselbe Stand als Zweig `main` ins oeffentliche GitHub-Repo
# gespiegelt (https://github.com/Nr44suessauer/deadline-beats-radio-bot).
# Schlaegt das fehl (Netz/Zugang), laeuft das Skript trotzdem durch und weist
# auf `webseite-nach-github.sh` hin.
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

# Oeffentliches GitHub-Repo (Spiegel, Zweig main); per Umfeld uebersteuerbar.
GITHUB_REPO="${GITHUB_REPO:-https://github.com/Nr44suessauer/deadline-beats-radio-bot.git}"

aufraeumen() {
  cd "$REPO"
  git worktree remove --force "$TMP/zweig" >/dev/null 2>&1 || true
  rm -rf "$TMP"
}
trap aufraeumen EXIT

echo "--- Fassung bauen (Platzhalter, ohne fremde Stimme)"
python3 "$HIER/veroeffentlichung-webseite.py" --ziel "$TMP/fassung" | tail -12

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
  git commit -q -m "${1:-Veroeffentlichungsfassung (DE+EN, Platzhalter, ohne fremde Stimme)}"
  echo "Festschreibung: $(git log --oneline -1)"
fi
git push -q -u origin webseite
echo "Zweig webseite ist bei origin aktuell."

# Spiegelung ins oeffentliche GitHub-Repo (derselbe Stand als Zweig `main`).
if git push -q "$GITHUB_REPO" HEAD:refs/heads/main 2>/dev/null; then
  echo "GitHub-Spiegel (Zweig main) ist aktuell."
else
  echo "Hinweis: GitHub-Spiegel fehlgeschlagen - mit 'bash webseite-nach-github.sh' nachholen."
fi
