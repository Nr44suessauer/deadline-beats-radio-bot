#!/usr/bin/env bash
# Holt den Stand des Zweigs `webseite` aus GitLab und spiegelt ihn als Zweig
# `main` ins oeffentliche GitHub-Repo.
#
# Gedacht fuer den Fall, dass der Zweig woanders geaendert wurde (z. B. direkt
# in GitLab) - der normale Weg `zweig-webseite-sichern.sh` spiegelt von selbst.
#
# Aufruf:  bash webseite-nach-github.sh
set -euo pipefail

HIER="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HIER/../../../.." && pwd)"

# Oeffentliches GitHub-Repo; per Umfeld uebersteuerbar.
GITHUB_REPO="${GITHUB_REPO:-https://github.com/Nr44suessauer/deadline-beats-radio-bot.git}"

cd "$REPO"
git fetch -q origin webseite
echo "GitLab-Stand: $(git log origin/webseite --oneline -1)"
git push "$GITHUB_REPO" refs/remotes/origin/webseite:refs/heads/main
echo "GitHub-Spiegel (Zweig main) ist aktuell."
