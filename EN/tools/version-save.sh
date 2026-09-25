##!/bin/bash
# Creates a version backup of the running radio workflows.
# <sicherungen>/<name>/workflows/  - Exports from n8n
# <sicherungen>/<name>/bau/       - Producer, import and test scripts
# <sicherungen>/<name>/dienste/   - Sources of the services (catalog, lists, text-to-speech)
# <sicherungen>/<name>/README.md  - Description (from <textfile>) and rollback path
# Call:  bash version-sichern.sh <name> [description.md]
#
# Replaces tempo/01-version-sichern.sh: same effect, but without fixed
# description text and with the sources of the services including
# Dockerfile (otherwise the line for playlist.py is missing during rebuild).
set -euo pipefail

NAME=${1:?Name missing, e.g. radio-v4-2026-09-20-with-lists}
BESCHREIBUNG=${2:-}
CFG=~/.ssh/config
RADIO=<dokuordner>
SICHERUNGEN=<projektordner>/sicherungen/radio-fassungen
ZIEL=$SICHERUNGEN/$NAME
TOOLS=$RADIO/werkzeuge

mkdir -p "$ZIEL/workflows" "$ZIEL/bau" "$ZIEL/dienste"

# --- Exports of the running workflows
for W in RadioAgentBot RadioWerkzeug AzuraWerkzeug MeldungenWerkzeug bjFSfXGqpLg7AAXw; do
  ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
    docker exec -u node n8n n8n export:workflow --id=$W --output=/tmp/$W.json >/dev/null 2>&1
    docker cp n8n:/tmp/$W.json /tmp/$W.json >/dev/null'"
  ssh -F "$CFG" ai-server "pct exec 103 -- cat /tmp/$W.json" > "$ZIEL/workflows/$W.json"
  printf ' %-18s %s Bytes\n' "$W" "$(wc -c < "$ZIEL/workflows/$W.json")"
done

# --- Backup in the complete data set (n8n database) for emergency purposes
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  docker cp n8n:/home/node/.n8n/database.sqlite /tmp/n8n-data.sqlite >/dev/null && echo ok'" >/dev/null
ssh -F "$CFG" ai-server "pct exec 103 -- cat /tmp/n8n-data.sqlite" | gzip -9 > "$ZIEL/n8n-data.sqlite.gz"
printf ' %-18s %s Bytes\n' "n8n-data.sqlite.gz" "$(wc -c < "$ZIEL/n8n-data.sqlite.gz")"

# --- Producer, import and test scripts (Radiotopf and list tasks)
for F in agent-wf-build.py agent-deploy.sh agent-postprocess.py \
         import-agent-prepare.py statische-data-patchen.py allowed-setzen.py \
         code-check.py create-archive.py create-tag.py \
         bot-test.sh answers.js letzter.js one.js feld.js evaluation.py \
         full-run.sh ausfuehrungen.sh version-sichern.sh \
         agent-patch.py agent-patch.sh agent-deploy-only.sh service-deploy.sh; do
  [ -f "$TOOLS/$F" ] && cp "$TOOLS/$F" "$ZIEL/bau/"
done
mkdir -p "$ZIEL/bau/playlist" "$ZIEL/bau/news" "$ZIEL/bau/tempo"
cp "$TOOLS/playlist/"* "$ZIEL/bau/playlist/" 2>/dev/null || true
cp "$TOOLS/news/"* "$ZIEL/bau/news/" 2>/dev/null || true
cp "$TOOLS/tempo/"*.py "$TOOLS/tempo/"*.sh "$TOOLS/tempo/README.md" "$ZIEL/bau/tempo/" 2>/dev/null || true

# --- Service sources plus build instructions
cp "$RADIO/service/"*.py "$ZIEL/dienste/" 2>/dev/null || true
cp "$RADIO/service/Dockerfile" "$RADIO/service/docker-compose.yml" "$RADIO/service/README.md" "$ZIEL/dienste/" 2>/dev/null || true

# --- Documentation extract
cp "$RADIO/README.md" "$ZIEL/README-the-Doku.md"
cp "$RADIO/MANUAL.md" "$ZIEL/ARCHITEKTUR-the-Doku.md" 2>/dev/null || true

# The exports contain access values (bot identification, interface key,
# DJ password) - therefore only readable by the owner.
chmod 700 "$ZIEL" "$ZIEL/workflows" "$ZIEL/bau" "$ZIEL/bau/playlist" "$ZIEL/bau/news" "$ZIEL/bau/tempo" "$ZIEL/dienste"
chmod 600 "$ZIEL"/workflows/* "$ZIEL"/bau/* "$ZIEL"/bau/playlist/* "$ZIEL"/bau/news/* "$ZIEL"/bau/tempo/* "$ZIEL"/*.sqlite.gz \
          "$ZIEL"/dienste/* "$ZIEL"/*.md 2>/dev/null || true

# --- Description
{
  if [ -n "$BESCHREIBUNG" ] && [ -f "$BESCHREIBUNG" ]; then
    cat "$BESCHREIBUNG"
  else
    echo "# version $NAME"
    echo
    echo "Backup of running radio operations (current state $(date ’+%d.%m.%Y %H:%M’))."
  fi
  cat <<TEXT

## Content

- \`workflows/\` – Exporte out n8n: RadioAgentBot, RadioWerkzeug, AzuraWerkzeug,
  AI-Moderator (\`bjFSfXGqpLg7AAXw\`)
- \`n8n-data.sqlite.gz\` – komplette n8n-Datenbank (Notfall)
- \`bau/\` – builder, deploy and check scripts; \`bau/playlist/\` the playlist jobs,
  \`bau/news/\` the news inbox (search bot, announcements), \`bau/tempo/\` the
  tempo changes with their checks
- \`dienste/\` – sources the Dienste (Katalog, Listen, Sprachausgabe) samt Dockerfile
- \`README-the-Doku.md\`, \`ARCHITEKTUR-the-Doku.md\` – Doku-Abzug

## Rollback path (restoring operations from this backup)

\`\`\`bash
cd ../..
CFG=~/.ssh/config
for W in RadioAgentBot RadioWerkzeug AzuraWerkzeug MeldungenWerkzeug bjFSfXGqpLg7AAXw; do
  cat $SICHERUNGEN/$NAME/workflows/\$W.json | ssh -F "\$CFG" ai-server \\
    "pct exec 103 -- bash -c 'cat > /tmp/\$W.json'"
  ssh -F "\$CFG" ai-server "pct exec 103 -- bash -lc '
    docker cp /tmp/\$W.json n8n:/tmp/ >/dev/null
    docker exec -u node n8n n8n import:workflow --input=/tmp/\$W.json \\
      --projectId=YOUR-N8N-PROJECT-ID'
done
ssh -F "\$CFG" ai-server "pct exec 103 -- docker restart n8n"
\`\`\`

That restores the workflows as saved (webhook paths and the allowed
identifiers are inside the workflows themselves).

**Reset only the bot workflow** (that is how it was done on 2026-09-20 after the typo
in the playlist switch):

\`\`\`bash
cd ../../werkzeuge
bash tempo/04-deploy.sh $SICHERUNGEN/$NAME/workflows/RadioAgentBot.json RadioAgentBot
\`\`\`

## Rebuild services

\`\`\`bash
# Catalog + Lists (LXC 103, /opt/radio-tts)
bash tools/playlist/08-service-deploy.sh
\`\`\`

The Dockerfile must also copy the file \`app/playlist.py\` – otherwise the
playlist module im Service (\`No module named 'playlist'\`).
TEXT
} > "$ZIEL/README.md"

echo
echo "Backup is located in $ZIEL"
ls -la "$ZIEL"
