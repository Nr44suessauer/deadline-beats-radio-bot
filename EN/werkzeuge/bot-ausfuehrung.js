// Shows a single run of the radio agent node by node:
// welcher nodes lief, welche Felder kamen heraus.
//
// Call im Container:
//   docker exec -u node n8n node /tmp/bot-ausfuehrung.js <ausfuehrungsnummer>
const sqlite3 = require("/usr/local/lib/node_modules/n8n/node_modules/sqlite3");
const { parse } = require("/usr/local/lib/node_modules/n8n/node_modules/flatted");

const NUMMER = parseInt(process.argv[2] || "0", 10);
if (!NUMMER) {
  console.error("Call: bot-ausfuehrung.js <execution number>");
  process.exit(1);
}

const db = new sqlite3.Database("/home/node/.n8n/database.sqlite", sqlite3.OPEN_READONLY);

db.all("select executionId, workflowData, data from execution_data where executionId = ?",
  [NUMMER], (error, lines) => {
    if (error) {
      console.error("Error:", error.message);
      process.exit(1);
    }
    if (!lines.length) {
      console.error("No execution with the number", NUMMER);
      process.exit(1);
    }
    const data = parse(lines[0].data);
    for (const [run, inhalt] of Object.entries(data.resultData.runData || {})) {
      const ergebnisse = (inhalt || []).filter((s) => s.data);
      console.log("=== Node:", run, "(" + ergebnisse.length + " Run/Runs)");
      for (const schritt of ergebnisse) {
        for (const entry of schritt.data.main || []) {
          for (const stueck of entry || []) {
            const j = stueck.json || {};
            const short = {};
            for (const [k, v] of Object.entries(j)) {
              const t = typeof v === "string" ? v : JSON.stringify(v);
              short[k] = t && t.length > 220 ? t.slice(0, 220) + "…" : t;
            }
            console.log("   ", JSON.stringify(short));
          }
        }
        if (schritt.error) console.log(" ERROR:", JSON.stringify(schritt.error).slice(0, 300));
      }
    }
    db.close();
  });
