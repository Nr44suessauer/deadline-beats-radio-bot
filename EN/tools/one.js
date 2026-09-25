// Shows a single run completely (all nodes, truncated).
// Call: docker exec -u node n8n node /tmp/one.js 1430
const sqlite3 = require("/usr/local/lib/node_modules/n8n/node_modules/sqlite3");
const { parse } = require("/usr/local/lib/node_modules/n8n/node_modules/flatted");
const db = new sqlite3.Database("/home/node/.n8n/database.sqlite");
const ID = process.argv[2];

db.get("Select data from execution_data where executionId = ?", [ID], (e, z) => {
  if (e || !z) { console.error(e ? e.message : "not found"); process.exit(1); }
  const d = parse(z.data);
  const runData = (d.resultData && d.resultData.runData) || {};
  const short = (j) => {
    const k = Object.assign({}, j);
    ["headers", "params", "query", "webhookUrl", "executionMode", "type", "path", "song_id",
     "unique_id", "length", "playlists", "custom_fields", "extra_metadata"].forEach((x) => delete k[x]);
    return JSON.stringify(k).slice(0, 600);
  };
  Object.keys(runData).forEach((name) => {
    runData[name].forEach((run, i) => {
      const lines = [];
      if (run.error) {
        console.log(`--- ${name} [${i}] ERROR: ${String(run.error.message || "").slice(0, 200)}`);
      }
      const main = (run.data && run.data.main) || [];
      main.forEach((zweig, zi) => (zweig || []).forEach((item, ii) => {
        if (item && item.json) lines.push(`    [Zweig ${zi} Nr ${ii}] ${short(item.json)}`);
        if (item && item.binary) lines.push(`    [Zweig ${zi} Nr ${ii}] (Binaerdaten)`);
      }));
      if (lines.length) console.log(`--- ${name} [${i}]\n` + lines.join("\n"));
    });
  });
  console.log("\nlast executed:", d.resultData && d.resultData.lastNodeExecuted);
  db.close();
});
