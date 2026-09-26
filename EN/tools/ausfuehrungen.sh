#!/usr/bin/env bash
# shellcheck disable=SC2016
# Shows the last executions of the bot workflow (nodes + results).
docker exec -u node n8n node -e '
const sqlite3 = require("/usr/local/lib/node_modules/n8n/node_modules/sqlite3");
const { parse } = require("/usr/local/lib/node_modules/n8n/node_modules/flatted");
const db = new sqlite3.Database("/home/node/.n8n/database.sqlite");
db.all("select id, status, startedAt from execution_entity where workflowId = ? order by id desc limit " + (process.argv[1] || 3),
  ["RadioTelegramBot"], (e, rows) => {
    if (e) { console.error(e.message); process.exit(1); }
    let open = rows.length;
    rows.forEach(r => {
      db.get("Select data from execution_data where executionId = ?", [r.id], (e2, z) => {
        console.log("\n===== Execution " + r.id + " (" + r.status + ")");
        if (z) {
          const d = parse(z.data);
          const runData = d.resultData && d.resultData.runData ? d.resultData.runData : {};
          for (const [name, laeufe] of Object.entries(runData)) {
            const last = laeufe[laeufe.length - 1];
            if (last.error) { console.log("  " + name.padEnd(22) + " ERROR:" + String(last.error.message || "").slice(0, 120)); continue; }
            const main = last.data && last.data.main ? last.data.main : [];
            const zweige = [];
            main.forEach((zweig, i) => { if (zweig && zweig.length) zweige.push(i + ":" + zweig.length); });
            const item = main.flat().find(Boolean);
            let short = "";
            if (item) {
              const j = Object.assign({}, item.json);
              for (const k of Object.keys(j)) if (typeof j[k] === "string" && j[k].length > 500) j[k] = j[k].slice(0, 500) + "…";
              for (const k of ["headers", "params", "query", "webhookUrl", "executionMode", "type", "path", "song_id", "unique_id", "length", "text"]) delete j[k];
              short = JSON.stringify(j);
            } else short = "(no output)";
            console.log("  " + name.padEnd(22) + " [Branch " + (zweige.join(",") || "-") + "] " + short.slice(0, 700));
          }
          console.log(" last executed:" + (d.resultData ? d.resultData.lastNodeExecuted : "?"));
        }
        if (--open === 0) db.close();
      });
    });
  });
' "$1"
