// Zeigt ein einzelnes Feld eines Knotens aus einer Ausfuehrung.
// Aufruf: docker exec -u node n8n node /tmp/feld.js <ausfuehrung> <knoten> <feld>
const sqlite3 = require("/usr/local/lib/node_modules/n8n/node_modules/sqlite3");
const { parse } = require("/usr/local/lib/node_modules/n8n/node_modules/flatted");
const db = new sqlite3.Database("/home/node/.n8n/database.sqlite");
const [id, knoten, feld] = process.argv.slice(2);

db.get("select data from execution_data where executionId = ?", [id], (e, z) => {
  if (e || !z) { console.error(e ? e.message : "nicht gefunden"); process.exit(1); }
  const d = parse(z.data);
  const laeufe = ((d.resultData || {}).runData || {})[knoten] || [];
  let i = 0;
  for (const lauf of laeufe) {
    for (const zweig of ((lauf.data || {}).main || [])) {
      for (const item of (zweig || [])) {
        const j = item.json || {};
        const wert = feld === "*" ? JSON.stringify(j).slice(0, 900) : j[feld];
        console.log(`Nr ${i}: ${feld} = ${JSON.stringify(wert)}`);
        i += 1;
      }
    }
  }
  if (!i) console.log("keine Elemente");
  db.close();
});
