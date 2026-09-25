#!/usr/bin/env bash
# Zeigt die letzten Ausfuehrungen des Bot-Arbeitsablaufs (Knoten + Ergebnisse).
# Fuer die Listen-Aufgaben: so sieht man, welcher Zweig gelaufen ist.
# Aufruf:  bash 16-ausfuehrungen.sh [anzahl]
set -euo pipefail
ANZAHL=${1:-4}

cat <<'REMOTE' | ssh -F ~/.ssh/config ai-server "pct exec 103 -- bash -c 'cat > /tmp/ausf-listen.js'"
const sqlite3 = require("/usr/local/lib/node_modules/n8n/node_modules/sqlite3");
const { parse } = require("/usr/local/lib/node_modules/n8n/node_modules/flatted");
const db = new sqlite3.Database("/home/node/.n8n/database.sqlite");
const anzahl = Number(process.argv[2] || 4);
db.all("select id, status, startedAt from execution_entity where workflowId = ? order by id desc limit " + anzahl,
  ["RadioAgentBot"], (e, rows) => {
    if (e) { console.error(e.message); process.exit(1); }
    if (!rows.length) { console.log("keine Ausfuehrungen gefunden"); return db.close(); }
    let offen = rows.length;
    rows.forEach(r => {
      db.get("select data from execution_data where executionId = ?", [r.id], (e2, z) => {
        console.log("\n===== Ausfuehrung " + r.id + " (" + r.status + ") " + r.startedAt);
        if (z) {
          const d = parse(z.data);
          const runData = (d.resultData && d.resultData.runData) ? d.resultData.runData : {};
          for (const [name, laeufe] of Object.entries(runData)) {
            const letzter = laeufe[laeufe.length - 1];
            if (letzter.error) { console.log("  " + name.padEnd(20) + " FEHLER: " + String(letzter.error.message || "").slice(0, 140)); continue; }
            if (name === "Test-Eingang" || name === "Eingabe") {
              console.log("  " + name.padEnd(20) + " " + JSON.stringify(letzter.data && letzter.data.main ? letzter.data.main.flat().map(i => i && i.json)[0] : {}).slice(0, 300));
              continue;
            }
            const main = (letzter.data && letzter.data.main) ? letzter.data.main : [];
            const zweige = [];
            main.forEach((zweig, i) => { if (zweig && zweig.length) zweige.push(i + ":" + zweig.length); });
            const item = main.flat().find(Boolean);
            let kurz = "(keine Ausgabe)";
            if (item) {
              const j = Object.assign({}, item.json);
              delete j.headers; delete j.params; delete j.query; delete j.webhookUrl;
              for (const k of Object.keys(j)) if (typeof j[k] === "string" && j[k].length > 240) j[k] = j[k].slice(0, 240) + "…";
              kurz = JSON.stringify(j);
            }
            console.log("  " + name.padEnd(20) + " [Zweig " + (zweige.join(",") || "-") + "] " + kurz.slice(0, 420));
          }
          console.log("  zuletzt ausgefuehrt: " + (d.resultData ? d.resultData.lastNodeExecuted : "?"));
        }
        if (--offen === 0) db.close();
      });
    });
  });
REMOTE

ssh -F ~/.ssh/config ai-server \
  "pct exec 103 -- bash -lc 'docker cp /tmp/ausf-listen.js n8n:/tmp/ >/dev/null; docker exec -u node n8n node /tmp/ausf-listen.js $ANZAHL'"
