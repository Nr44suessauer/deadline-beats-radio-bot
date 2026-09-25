#!/usr/bin/env bash
# Legt die Ablaeufe des privaten Bots (Sender 1) in ihren n8n-Ordner
# "Sender 1: Deadline Beats". Der Ordner wird angelegt, falls er fehlt; die
# sechs zugehoerigen Ablaeufe werden zugeordnet. Wiederholbar.
#
# Warum das noetig ist: `n8n import:workflow` uebernimmt die Ordner-Zuordnung
# NICHT (weder aus der Datei noch beim Ersetzen) - ein frisch angelegter Ablauf
# landet ohne Ordner. Darum setzt dieses Werkzeug die Zuordnung nach dem
# Einspielen (aufgerufen von konfiguration-einspielen.sh und
# agent-einspielen-nur.sh).
#
# Der Webseiten-Bot (Sender 2) wird hier NICHT angefasst - dessen Ordner
# "Sender 2: Axis Church Radio" richtet Sender-2-Axis-Church-Radio/werkzeuge/einspielen.sh ein.
#
# Aufruf:  bash n8n-ordner-setzen.sh
set -euo pipefail

CFG=~/.ssh/config
HIER="$(cd "$(dirname "$0")" && pwd)"

cat > /tmp/radio-ordner.js <<'JS'
// Ordnet die Ablaeufe des privaten Bots (Sender 1) dem Ordner zu.
const sqlite3 = require("/usr/local/lib/node_modules/n8n/node_modules/.pnpm/sqlite3@5.1.7/node_modules/sqlite3");
const db = new sqlite3.Database("/home/node/.n8n/database.sqlite");
const ORDNER = "vEDODlq4jIKCUDmf";                 // bleibt gleich, auch wenn der Name wechselt
const NAME = "Sender 1: Deadline Beats";
const PROJEKT = "DEINE-N8N-PROJEKT-KENNUNG";
const IDS = ["RadioAgentBot", "RadioWerkzeug", "AzuraWerkzeug", "MeldungenWerkzeug",
             "Konfiguration", "StimmenBot"];
db.serialize(() => {
  db.run("insert or ignore into folder (id, name, parentFolderId, projectId, createdAt, updatedAt)"
       + " values (?, ?, null, ?, datetime('now'), datetime('now'))", [ORDNER, NAME, PROJEKT]);
  for (const id of IDS) {
    db.run("update workflow_entity set parentFolderId = ? where id = ?", [ORDNER, id]);
  }
});
db.all("select id from workflow_entity where parentFolderId = ? order by id", [ORDNER], (e, r) => {
  if (e) { console.log("FEHLER: " + e.message); } else {
    console.log("Ordner \"" + NAME + "\": " + (r || []).map((x) => x.id).join(", "));
  }
  db.close();
});
JS

echo "--- Ordner zuordnen (Sender 1)"
cat /tmp/radio-ordner.js | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/radio-ordner.js'"
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  docker cp /tmp/radio-ordner.js n8n:/tmp/ >/dev/null
  docker exec -u node n8n node /tmp/radio-ordner.js'"
