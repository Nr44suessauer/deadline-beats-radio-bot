// Zeigt eine einzelne Ausfuehrung vollstaendig (alle Knoten, gekuerzt).
// Aufruf: docker exec -u node n8n node /tmp/eine.js 1430
const sqlite3 = require("/usr/local/lib/node_modules/n8n/node_modules/sqlite3");
const { parse } = require("/usr/local/lib/node_modules/n8n/node_modules/flatted");
const db = new sqlite3.Database("/home/node/.n8n/database.sqlite");
const ID = process.argv[2];

db.get("select data from execution_data where executionId = ?", [ID], (e, z) => {
  if (e || !z) { console.error(e ? e.message : "nicht gefunden"); process.exit(1); }
  const d = parse(z.data);
  const runData = (d.resultData && d.resultData.runData) || {};
  const kurz = (j) => {
    const k = Object.assign({}, j);
    ["headers", "params", "query", "webhookUrl", "executionMode", "art", "path", "song_id",
     "unique_id", "length", "playlists", "custom_fields", "extra_metadata"].forEach((x) => delete k[x]);
    return JSON.stringify(k).slice(0, 600);
  };
  Object.keys(runData).forEach((name) => {
    runData[name].forEach((lauf, i) => {
      const zeilen = [];
      if (lauf.error) {
        console.log(`--- ${name} [${i}] FEHLER: ${String(lauf.error.message || "").slice(0, 200)}`);
      }
      const main = (lauf.data && lauf.data.main) || [];
      main.forEach((zweig, zi) => (zweig || []).forEach((item, ii) => {
        if (item && item.json) zeilen.push(`    [Zweig ${zi} Nr ${ii}] ${kurz(item.json)}`);
        if (item && item.binary) zeilen.push(`    [Zweig ${zi} Nr ${ii}] (Binaerdaten)`);
      }));
      if (zeilen.length) console.log(`--- ${name} [${i}]\n` + zeilen.join("\n"));
    });
  });
  console.log("\nzuletzt ausgefuehrt:", d.resultData && d.resultData.lastNodeExecuted);
  db.close();
});
