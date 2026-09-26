#!/usr/bin/env bash
# Builds the release version and mirrors it into the
# Git branch `webseite`; pushes the branch to origin. The working directory remains
# untouched.
#
# At the end, the same state is mirrored as branch `main` into the public GitHub repo
# https://github.com/Nr44suessauer/deadline-beats-radio-bot.
# If this fails (Network/Access), the script still runs through and points to
# `webseite-nach-github.sh`.
#
# The version is created with `veroeffentlichung-webseite.py`:
# - placeholders instead of access values (via doc-official-build.py),
# - no third-party voice and no voice data; your own desired voice stands
# as a placeholder in DOCS/VOICE.md and the template REBUILD/own-voice/.
#
# The branch contains the content FLACH (README.md, DOKU/, EN/, ...) - this way it is
# directly readable and publishable as a standalone package.
#
# Call:  bash zweig-webseite-sichern.sh [“Comment for the commit”]
set -euo pipefail

HIER="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HIER/../../../.." && pwd)"
TMP="$(mktemp -d /tmp/webseite-zweig.XXXXXX)"

# Public GitHub Repo (mirror, branch main); overridable via environment.
GITHUB_REPO="${GITHUB_REPO:-https://github.com/Nr44suessauer/deadline-beats-radio-bot.git}"

cleanup() {
  cd "$REPO"
  git worktree remove --force "$TMP/zweig" >/dev/null 2>&1 || true
  rm -rf "$TMP"
}
trap cleanup EXIT

echo "Building version (placeholder, without external voice)"
python3 "$HIER/veroeffentlichung-webseite.py" --ziel "$TMP/version" | tail -12

cd "$REPO"
if git show-ref --verify --quiet refs/heads/webseite; then
  git worktree add -q "$TMP/zweig" webseite
else
  echo "Branch website is being created (first run)."
  git worktree add -q --detach "$TMP/zweig"
  cd "$TMP/zweig"
  git checkout -q --orphan webseite
  git rm -rf -q . >/dev/null 2>&1 || true
  cd "$REPO"
fi

# Clear branch and fill it with the fresh version.
find "$TMP/zweig" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -a "$TMP/version/." "$TMP/zweig/"

cd "$TMP/zweig"
git add -A
if git diff --cached --quiet; then
  echo "No changes — branch website is up to date."
else
  git commit -q -m "${1:-Release edition (DE+EN, placeholders, without a third-party voice)}"
  echo "Commit hash: $(git log --oneline -1)"
fi
git push -q -u origin webseite
echo "Branch website is up to date at origin."

# Mirroring to public GitHub repo (same state as branch `main`).
if git push -q "$GITHUB_REPO" HEAD:refs/heads/main 2>/dev/null; then
  echo "GitHub mirror (branch main) is up to date."
else
  echo "Note: GitHub mirror failed — catch up with ‘bash webseite-nach-github.sh’."
fi
