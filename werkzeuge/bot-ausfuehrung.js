// Zeigt eine einzelne Ausfuehrung des Radio-Agenten Knoten fuer Knoten:
// welcher Knoten lief, welche Felder kamen heraus.
//
// Aufruf im Container:
//   docker exec -u node n8n node /tmp/bot-ausfuehrung.js <ausfuehrungsnummer>
const sqlite3 = require("/usr/local/lib/node_modules/n8n/node_modules/sqlite3");
const { parse } = require("/usr/local/lib/node_modules/n8n/node_modules/flatted");

const NUMMER = parseInt(process.argv[2] || "0", 10);
if (!NUMMER) {
  console.error("Aufruf: bot-ausfuehrung.js <ausfuehrungsnummer>");
  process.exit(1);
}

const db = new sqlite3.Database("/home/node/.n8n/database.sqlite", sqlite3.OPEN_READONLY);

db.all("select executionId, workflowData, data from execution_data where executionId = ?",
  [NUMMER], (fehler, zeilen) => {
    if (fehler) {
      console.error("Fehler:", fehler.message);
      process.exit(1);
    }
    if (!zeilen.length) {
      console.error("Keine Ausfuehrung mit der Nummer", NUMMER);
      process.exit(1);
    }
    const daten = parse(zeilen[0].data);
    for (const [lauf, inhalt] of Object.entries(daten.resultData.runData || {})) {
      const ergebnisse = (inhalt || []).filter((s) => s.data);
      console.log("=== Knoten:", lauf, "(" + ergebnisse.length + " Durchlauf/Durchlaeufe)");
      for (const schritt of ergebnisse) {
        for (const eintrag of schritt.data.main || []) {
          for (const stueck of eintrag || []) {
            const j = stueck.json || {};
            const kurz = {};
            for (const [k, v] of Object.entries(j)) {
              const t = typeof v === "string" ? v : JSON.stringify(v);
              kurz[k] = t && t.length > 220 ? t.slice(0, 220) + "…" : t;
            }
            console.log("   ", JSON.stringify(kurz));
          }
        }
        if (schritt.error) console.log("    FEHLER:", JSON.stringify(schritt.error).slice(0, 300));
      }
    }
    db.close();
  });
