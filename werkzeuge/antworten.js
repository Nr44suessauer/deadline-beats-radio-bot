// Zeigt zu den letzten Bot-Ausfuehrungen die Frage, die Antwort und Fehler.
// Aufruf im Container: docker exec -u node n8n node /tmp/antworten.js 8
const sqlite3 = require("/usr/local/lib/node_modules/n8n/node_modules/sqlite3");
const { parse } = require("/usr/local/lib/node_modules/n8n/node_modules/flatted");
const db = new sqlite3.Database("/home/node/.n8n/database.sqlite");
const ANZAHL = parseInt(process.argv[2] || "8", 10);

db.all("select id, status from execution_entity where workflowId = ? order by id desc limit " + ANZAHL,
  ["RadioTelegramBot"], (e, rows) => {
    if (e) { console.error(e.message); process.exit(1); }
    let offen = rows.length;
    if (!offen) { console.log("keine Ausfuehrungen"); db.close(); return; }
    rows.reverse().forEach((r) => {
      db.get("select data from execution_data where executionId = ?", [r.id], (e2, z) => {
        console.log("\n=== Ausfuehrung " + r.id + " (" + r.status + ")");
        if (z) {
          const d = parse(z.data);
          const runData = (d.resultData && d.resultData.runData) || {};
          const hol = (name) => {
            for (const l of (runData[name] || [])) {
              for (const zweig of ((l.data && l.data.main) || [])) {
                for (const item of (zweig || [])) if (item && item.json) return item.json;
              }
            }
            return null;
          };
          const test = hol("Test-Eingang");
          const eingabe = hol("Eingabe") || {};
          const frage = (test && test.body && test.body.message && test.body.message.text)
            || eingabe.text || (hol("Befehl") || {}).argument || "?";
          console.log("  Frage  : " + frage);
          const g = hol("Genre waehlen");
          if (g) console.log("  Richtung: " + (g.richtung || "-") + " (" + (g.richtungHinweis || "-")
            + ") Treffer " + ((g.treffer || []).length));
          const k = hol("Kluge Suche");
          if (k) console.log("  Kluge Suche: " + ((k.treffer || []).length) + " Treffer, Stufe "
            + (k.stufe || "-"));
          const namen = ["Wunsch sammeln", "Wunsch Text", "Sofort Text", "Ende Text", "Hilfe", "Jetzt Text",
                         "Verlauf Text", "Rueckmeldung", "Kein Zugang"];
          namen.forEach((name) => {
            const j = hol(name);
            if (j && j.antwort) {
              console.log("  Antwort:");
              String(j.antwort).split("\n").forEach((zeile) => console.log("    " + zeile));
            }
          });
          const b = hol("Bewerten");
          if (b && b.trefferListe) console.log("  Treffer: " + b.trefferListe.slice(0, 3).join(" | "));
          Object.keys(runData).forEach((name) => {
            const laeufe = runData[name] || [];
            const letzter = laeufe[laeufe.length - 1];
            if (letzter && letzter.error) {
              console.log("  FEHLER in " + name + ": " + String(letzter.error.message || "").slice(0, 160));
            }
          });
        }
        if (--offen === 0) db.close();
      });
    });
  });
