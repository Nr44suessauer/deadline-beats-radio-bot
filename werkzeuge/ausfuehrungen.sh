#!/usr/bin/env bash
# shellcheck disable=SC2016
# Zeigt die letzten Ausfuehrungen des Bot-Workflows (Knoten + Ergebnisse).
docker exec -u node n8n node -e '
const sqlite3 = require("/usr/local/lib/node_modules/n8n/node_modules/sqlite3");
const { parse } = require("/usr/local/lib/node_modules/n8n/node_modules/flatted");
const db = new sqlite3.Database("/home/node/.n8n/database.sqlite");
db.all("select id, status, startedAt from execution_entity where workflowId = ? order by id desc limit " + (process.argv[1] || 3),
  ["RadioTelegramBot"], (e, rows) => {
    if (e) { console.error(e.message); process.exit(1); }
    let offen = rows.length;
    rows.forEach(r => {
      db.get("select data from execution_data where executionId = ?", [r.id], (e2, z) => {
        console.log("\n===== Ausfuehrung " + r.id + " (" + r.status + ")");
        if (z) {
          const d = parse(z.data);
          const runData = d.resultData && d.resultData.runData ? d.resultData.runData : {};
          for (const [name, laeufe] of Object.entries(runData)) {
            const letzter = laeufe[laeufe.length - 1];
            if (letzter.error) { console.log("  " + name.padEnd(22) + " FEHLER: " + String(letzter.error.message || "").slice(0, 120)); continue; }
            const main = letzter.data && letzter.data.main ? letzter.data.main : [];
            const zweige = [];
            main.forEach((zweig, i) => { if (zweig && zweig.length) zweige.push(i + ":" + zweig.length); });
            const item = main.flat().find(Boolean);
            let kurz = "";
            if (item) {
              const j = Object.assign({}, item.json);
              for (const k of Object.keys(j)) if (typeof j[k] === "string" && j[k].length > 500) j[k] = j[k].slice(0, 500) + "…";
              for (const k of ["headers", "params", "query", "webhookUrl", "executionMode", "art", "path", "song_id", "unique_id", "length", "text"]) delete j[k];
              kurz = JSON.stringify(j);
            } else kurz = "(keine Ausgabe)";
            console.log("  " + name.padEnd(22) + " [Zweig " + (zweige.join(",") || "-") + "] " + kurz.slice(0, 700));
          }
          console.log("  zuletzt ausgefuehrt: " + (d.resultData ? d.resultData.lastNodeExecuted : "?"));
        }
        if (--offen === 0) db.close();
      });
    });
  });
' "$1"
