#!/usr/bin/env bash
# Shows the last executions of the bot workflow (node + results).
# For list tasks: this is how you see which branch ran.
# Call:  bash 16-ausfuehrungen.sh [count]
set -euo pipefail
ANZAHL=${1:-4}

cat <<'REMOTE' | ssh -F ~/.ssh/config ai-server "pct exec 103 -- bash -c 'cat > /tmp/ausf-listen.js'"
const sqlite3 = require("/usr/local/lib/node_modules/n8n/node_modules/sqlite3");
const { parse } = require("/usr/local/lib/node_modules/n8n/node_modules/flatted");
const db = new sqlite3.Database("/home/node/.n8n/database.sqlite");
const count = Number(process.argv[2] || 4);
db.all("select id, status, startedAt from execution_entity where workflowId = ? order by id desc limit" + count,
  ["RadioAgentBot"], (e, rows) => {
    if (e) { console.error(e.message); process.exit(1); }
    if (!rows.length) { console.log("no executions found"); return db.close(); }
    let open = rows.length;
    rows.forEach(r => {
      db.get("Select data from execution_data where executionId = ?", [r.id], (e2, z) => {
        console.log("\n===== Execution" + r.id + " (" + r.status + ") " + r.startedAt);
        if (z) {
          const d = parse(z.data);
          const runData = (d.resultData && d.resultData.runData) ? d.resultData.runData : {};
          for (const [name, laeufe] of Object.entries(runData)) {
            const last = laeufe[laeufe.length - 1];
            if (last.error) { console.log("  " + name.padEnd(20) + " ERROR:" + String(last.error.message || "").slice(0, 140)); continue; }
            if (name === "Test-Entry" || name === "Input") {
              console.log("  " + name.padEnd(20) + " " + JSON.stringify(last.data && last.data.main ? last.data.main.flat().map(i => i && i.json)[0] : {}).slice(0, 300));
              continue;
            }
            const main = (last.data && last.data.main) ? last.data.main : [];
            const zweige = [];
            main.forEach((zweig, i) => { if (zweig && zweig.length) zweige.push(i + ":" + zweig.length); });
            const item = main.flat().find(Boolean);
            let short = "(no output)";
            if (item) {
              const j = Object.assign({}, item.json);
              delete j.headers; delete j.params; delete j.query; delete j.webhookUrl;
              for (const k of Object.keys(j)) if (typeof j[k] === "string" && j[k].length > 240) j[k] = j[k].slice(0, 240) + "…";
              short = JSON.stringify(j);
            }
            console.log("  " + name.padEnd(20) + " [Branch" + (zweige.join(",") || "-") + "] " + short.slice(0, 420));
          }
          console.log(" last executed:" + (d.resultData ? d.resultData.lastNodeExecuted : "?"));
        }
        if (--open === 0) db.close();
      });
    });
  });
REMOTE

ssh -F ~/.ssh/config ai-server \
  "pct exec 103 -- bash -lc 'docker cp /tmp/ausf-listen.js n8n:/tmp/ >/dev/null; docker exec -u node n8n node /tmp/ausf-listen.js $ANZAHL'"
