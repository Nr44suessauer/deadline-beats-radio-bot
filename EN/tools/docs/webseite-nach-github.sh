#!/usr/bin/env bash
# Fetches the state of the `webseite` branch from GitLab and mirrors it as a branch
# `main` to the public GitHub repo.
#
# Intended for the case where the branch was changed elsewhere (e.g., directly
# in GitLab) - the normal way `zweig-webseite-sichern.sh` mirrors automatically.
#
# Call:  bash webseite-nach-github.sh
set -euo pipefail

HIER="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HIER/../../../.." && pwd)"

# Public GitHub repo; overridable via environment.
GITHUB_REPO="${GITHUB_REPO:-https://github.com/Nr44suessauer/deadline-beats-radio-bot.git}"

cd "$REPO"
git fetch -q origin webseite
echo "GitLab state: $(git log origin/webseite --oneline -1)"
git push "$GITHUB_REPO" refs/remotes/origin/webseite:refs/heads/main
echo "GitHub mirror (branch main) is up to date."
