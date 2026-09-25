// Zaehlt je Knoten die Elemente einer Ausfuehrung.
// Aufruf: docker exec -u node n8n node /tmp/zaehlen.js <ausfuehrung>
const sqlite3 = require("/usr/local/lib/node_modules/n8n/node_modules/sqlite3");
const { parse } = require("/usr/local/lib/node_modules/n8n/node_modules/flatted");
const db = new sqlite3.Database("/home/node/.n8n/database.sqlite");

db.get("select data from execution_data where executionId = ?", [process.argv[2]], (e, z) => {
  if (e || !z) { console.error(e ? e.message : "nicht gefunden"); process.exit(1); }
  const d = parse(z.data);
  const runData = (d.resultData || {}).runData || {};
  for (const [name, laeufe] of Object.entries(runData)) {
    const teile = [];
    laeufe.forEach((lauf, i) => {
      const zahlen = ((lauf.data || {}).main || []).map((zweig) => (zweig || []).length);
      const fehler = lauf.error ? " FEHLER:" + String(lauf.error.message).slice(0, 60) : "";
      teile.push(`[Lauf ${i}: ${zahlen.join("/") || "-"}]${fehler}`);
    });
    console.log(name.padEnd(22) + teile.join(" "));
  }
  db.close();
});
