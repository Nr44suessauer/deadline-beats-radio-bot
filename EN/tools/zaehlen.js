// Counts for each node the elements of an execution.
// Call: docker exec -u node n8n node /tmp/zaehlen.js <execution>
const sqlite3 = require("/usr/local/lib/node_modules/n8n/node_modules/sqlite3");
const { parse } = require("/usr/local/lib/node_modules/n8n/node_modules/flatted");
const db = new sqlite3.Database("/home/node/.n8n/database.sqlite");

db.get("Select data from execution_data where executionId = ?", [process.argv[2]], (e, z) => {
  if (e || !z) { console.error(e ? e.message : "not found"); process.exit(1); }
  const d = parse(z.data);
  const runData = (d.resultData || {}).runData || {};
  for (const [name, laeufe] of Object.entries(runData)) {
    const teile = [];
    laeufe.forEach((run, i) => {
      const numbers = ((run.data || {}).main || []).map((zweig) => (zweig || []).length);
      const error = run.error ? " ERROR:" + String(run.error.message).slice(0, 60) : "";
      teile.push(`[Run ${i}: ${numbers.join("/") || "-"}]${error}`);
    });
    console.log(name.padEnd(22) + teile.join(" "));
  }
  db.close();
});
