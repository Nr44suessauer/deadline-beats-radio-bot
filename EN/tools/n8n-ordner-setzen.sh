#!/usr/bin/env bash
# Sets the workflows of the bot into their n8n folder
# “Deadline Beats”. The folder is created if it is missing; the
# six associated workflows are assigned. Repeatable.
#
# Why this is necessary: `n8n import:workflow` does NOT carry the folder
# assignment (neither from the file nor when replacing) - a newly created
# workflow ends up without a folder. That is why this tool sets the assignment
# after the import (called from config-import.sh and agent-import-only.sh).
#
# Call: bash n8n-ordner-setzen.sh
set -euo pipefail

CFG=~/.ssh/config
HIER="$(cd "$(dirname "$0")" && pwd)"

cat > /tmp/radio-folder.js <<'JS'
// Assigns the workflows of the bot to their folder.
const sqlite3 = require("/usr/local/lib/node_modules/n8n/node_modules/.pnpm/sqlite3@5.1.7/node_modules/sqlite3");
const db = new sqlite3.Database("/home/node/.n8n/database.sqlite");
const ORDNER = "vEDODlq4jIKCUDmf";                 // stays the same, even if the name changes
const NAME = "Deadline Beats";
const PROJEKT = "YOUR-N8N-PROJECT-ID";
const IDS = ["RadioAgentBot", "RadioWerkzeug", "AzuraWerkzeug", "MeldungenWerkzeug",
             "Configuration", "StimmenBot"];
db.serialize(() => {
  db.run("insert or ignore into folder (id, name, parentFolderId, projectId, createdAt, updatedAt)"
       + " values (?, ?, null, ?, datetime('now'), datetime('now'))", [ORDNER, NAME, PROJEKT]);
  for (const id of IDS) {
    db.run("update workflow_entity set parentFolderId = ? where id = ?", [ORDNER, id]);
  }
});
db.all("select id from workflow_entity where parentFolderId = ? order by id", [ORDNER], (e, r) => {
  if (e) { console.log("ERROR:" + e.message); } else {
    console.log("Folder \"" + NAME + "\": " + (r || []).map((x) => x.id).join(", "));
  }
  db.close();
});
JS

echo "--- Assign folder"
cat /tmp/radio-folder.js | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/radio-folder.js'"
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  docker cp /tmp/radio-folder.js n8n:/tmp/ >/dev/null
  docker exec -u node n8n node /tmp/radio-folder.js'"
