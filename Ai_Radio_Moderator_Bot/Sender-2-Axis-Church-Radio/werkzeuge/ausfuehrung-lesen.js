// Liest die letzte Ausführung eines Ablaufs aus der n8n-Datenbank und zeigt die
// Ergebnisse einzelner Knoten (n8n speichert flach: Verweise sind Indizes).
//
// Aufruf: node ausfuehrung-lesen.js <workflowId> [Knotenmustter...]
// Beispiel: node ausfuehrung-lesen.js DDD-Webseite-Bot Antwort Senden
const sqlite3 = require('/usr/local/lib/node_modules/n8n/node_modules/.pnpm/sqlite3@5.1.7/node_modules/sqlite3');

const wf = process.argv[2] || 'DDD-Webseite-Bot';
const muster = process.argv.slice(3);
const db = new sqlite3.Database('/home/node/.n8n/database.sqlite', sqlite3.OPEN_READONLY);

function aufloesen(roh, zeiger, tiefe = 0) {
  if (tiefe > 12 || zeiger === undefined || zeiger === null) return zeiger;
  if (typeof zeiger === 'string' && /^\d+$/.test(zeiger)) return aufloesen(roh, roh[Number(zeiger)], tiefe + 1);
  if (Array.isArray(zeiger)) return zeiger.map((x) => aufloesen(roh, x, tiefe + 1));
  if (typeof zeiger === 'object') {
    const neu = {};
    for (const [k, v] of Object.entries(zeiger)) neu[k] = aufloesen(roh, v, tiefe + 1);
    return neu;
  }
  return zeiger;
}

db.all(`SELECT id, status, startedAt FROM execution_entity WHERE workflowId = ? ORDER BY id DESC LIMIT 1`,
  [wf], (fehler, zeilen) => {
    if (fehler || !zeilen.length) { console.log('Keine Ausführung für', wf); process.exit(1); }
    const e = zeilen[0];
    console.log(`Ausführung #${e.id}  status=${e.status}  start=${e.startedAt}`);
    db.get(`SELECT data FROM execution_data WHERE executionId = ?`, [e.id], (f2, daten) => {
      if (f2 || !daten) { console.log('Keine Ausführungsdaten.'); process.exit(1); }
      const roh = JSON.parse(daten.data);
      const kopf = aufloesen(roh, roh[0]);
      const lauf = kopf.resultData.runData;
      console.log('Letzter Knoten:', kopf.resultData.lastNodeExecuted);
      for (const [name, eintraege] of Object.entries(lauf)) {
        if (muster.length && !muster.some((m) => name.includes(m))) continue;
        const datenTeil = aufloesen(roh, eintraege[0].data);
        const haupt = (datenTeil && datenTeil.main && datenTeil.main[0]) || [];
        console.log(`\n--- ${name}`);
        for (const x of haupt.slice(0, 2)) {
          console.log(JSON.stringify(aufloesen(roh, x && x.json)).slice(0, 900));
        }
      }
      process.exit(0);
    });
  });
