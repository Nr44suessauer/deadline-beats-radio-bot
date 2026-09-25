// Holt den Testerschluessel des Agenten aus den Statikdaten und gibt NUR ihn aus
// (gedacht zum Umleiten in die Datei /tmp/.botschluessel des Arbeitsplatzes).
const s = require("/usr/local/lib/node_modules/n8n/node_modules/sqlite3");
const db = new s.Database("/home/node/.n8n/database.sqlite", s.OPEN_READONLY);

db.all("select name, staticData from workflow_entity", (fehler, zeilen) => {
  if (fehler) {
    console.error(fehler.message);
    process.exit(1);
  }
  let gefunden = 0;
  for (const z of zeilen) {
    if (typeof z.staticData !== "string" || z.staticData.indexOf("testSchluessel") < 0) continue;
    let daten = {};
    try {
      daten = JSON.parse(z.staticData);
    } catch (grund) {
      continue;
    }
    const ganz = daten.global || daten;
    if (ganz && ganz.testSchluessel) {
      // Nur den Agenten ausgeben - andere Abläufe tragen dieselben Statikdaten.
      if (String(z.name).indexOf("Agent") >= 0) {
        process.stdout.write(String(ganz.testSchluessel) + "\n");
        gefunden += 1;
      }
    }
  }
  if (gefunden === 0) console.error("Kein Testerschluessel in den Statikdaten gefunden.");
  db.close();
});
