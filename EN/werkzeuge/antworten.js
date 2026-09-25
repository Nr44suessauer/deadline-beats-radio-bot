// Shows the latest bot runs: the question, the answer and errors.
// Call im Container: docker exec -u node n8n node /tmp/antworten.js 8
const sqlite3 = require("/usr/local/lib/node_modules/n8n/node_modules/sqlite3");
const { parse } = require("/usr/local/lib/node_modules/n8n/node_modules/flatted");
const db = new sqlite3.Database("/home/node/.n8n/database.sqlite");
const ANZAHL = parseInt(process.argv[2] || "8", 10);

db.all("select id, status from execution_entity where workflowId = ? order by id desc limit" + ANZAHL,
  ["RadioTelegramBot"], (e, rows) => {
    if (e) { console.error(e.message); process.exit(1); }
    let open = rows.length;
    if (!open) { console.log("no executions"); db.close(); return; }
    rows.reverse().forEach((r) => {
      db.get("Select data from execution_data where executionId = ?", [r.id], (e2, z) => {
        console.log("\n=== Execution" + r.id + " (" + r.status + ")");
        if (z) {
          const d = parse(z.data);
          const runData = (d.resultData && d.resultData.runData) || {};
          const fetch = (name) => {
            for (const l of (runData[name] || [])) {
              for (const zweig of ((l.data && l.data.main) || [])) {
                for (const item of (zweig || [])) if (item && item.json) return item.json;
              }
            }
            return null;
          };
          const test = fetch("Test-Entry");
          const eingabe = fetch("Input") || {};
          const question = (test && test.body && test.body.message && test.body.message.text)
            || eingabe.text || (fetch("Command") || {}).argument || "?";
          console.log(" Question :" + question);
          const g = fetch("Choose genre");
          if (g) console.log(" Direction:" + (g.direction || "-") + " (" + (g.richtungHinweis || "-")
            + ") hits" + ((g.hits || []).length));
          const k = fetch("Smart Search");
          if (k) console.log(" Smart Search:" + ((k.hits || []).length) + " hits, level"
            + (k.stufe || "-"));
          const names = ["Collect wishes", "Wish Text", "Immediate Text", "End Text", "Help", "Now Text",
                         "History Text", "Callback", "No access"];
          names.forEach((name) => {
            const j = fetch(name);
            if (j && j.answer) {
              console.log(" Answer:");
              String(j.answer).split("\n").forEach((zeile) => console.log("    " + zeile));
            }
          });
          const b = fetch("Rate hits");
          if (b && b.trefferListe) console.log(" Hits:" + b.trefferListe.slice(0, 3).join(" | "));
          Object.keys(runData).forEach((name) => {
            const laeufe = runData[name] || [];
            const last = laeufe[laeufe.length - 1];
            if (last && last.error) {
              console.log(" ERROR in" + name + ": " + String(last.error.message || "").slice(0, 160));
            }
          });
        }
        if (--open === 0) db.close();
      });
    });
  });
