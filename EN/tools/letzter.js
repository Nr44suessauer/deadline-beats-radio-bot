// Shows the nodes of the last execution of the radiobot.
// Call: docker exec -u node n8n node /tmp/letzter.js [count]
const sqlite3 = require("/usr/local/lib/node_modules/n8n/node_modules/sqlite3");
const { parse } = require("/usr/local/lib/node_modules/n8n/node_modules/flatted");
const count = Number(process.argv[2] || 1);

const db = new sqlite3.Database("/home/node/.n8n/database.sqlite");
db.all(
  "select executionId, data from execution_data order by executionId desc limit ?",
  [count],
  (e, rows) => {
    if (e) {
      console.error(e.message);
      process.exit(1);
    }
    for (const r of rows.reverse()) {
      const d = parse(r.data);
      const rd = (d.resultData || {}).runData || {};
      console.log("=== Run " + r.executionId + " ===");
      for (const [name, laeufe] of Object.entries(rd)) {
        const j = (((laeufe[0] || {}).data || {}).main || [[]])[0][0];
        if (!j) continue;
        const x = j.json || {};
        const short = x.answer !== undefined ? x.answer
          : (x.path !== undefined ? "path=" + x.path
            : (x.title !== undefined ? "title=" + x.title
              : (x.text !== undefined ? "text=" + x.text : JSON.stringify(x).slice(0, 80))));
        console.log("  " + name + " -> " + String(short).replace(/\n/g, " ").slice(0, 110));
      }
    }
    db.close();
  },
);
