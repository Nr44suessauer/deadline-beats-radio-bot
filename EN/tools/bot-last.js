// Shows the latest runs of the radio agent: question, stages, answer, errors.
//
// Call im Container:
//   docker exec -u node n8n node /tmp/bot-last.js [count] [workflowId]
// Via SSH (as in the other tools):
//   ssh -F .../proxmox-ssh/config ai-server "pct exec 103 -- bash -lc '
//     docker cp /tmp/bot-last.js n8n:/tmp/ >/dev/null
//     docker exec -u node n8n node /tmp/bot-last.js 3'"
const sqlite3 = require("/usr/local/lib/node_modules/n8n/node_modules/sqlite3");
const { parse } = require("/usr/local/lib/node_modules/n8n/node_modules/flatted");

const ANZAHL = parseInt(process.argv[2] || "3", 10);
const WORKFLOW = process.argv[3] || "RadioAgentBot";
const db = new sqlite3.Database("/home/node/.n8n/database.sqlite");

db.all("select id, status, startedAt from execution_entity where workflowId = ? order by id desc limit"
       + ANZAHL, [WORKFLOW], (e, rows) => {
  if (e) { console.error(e.message); process.exit(1); }
  if (!rows.length) { console.log("no executions for" + WORKFLOW); db.close(); return; }
  let open = rows.length;
  rows.reverse().forEach((r) => {
    db.get("Select data from execution_data where executionId = ?", [r.id], (e2, z) => {
      console.log("\n===== Execution" + r.id + " (" + r.status + ")");
      if (z) {
        const d = parse(z.data);
        const runData = (d.resultData && d.resultData.runData) || {};
        const all = (name) => {
          const raus = [];
          for (const l of (runData[name] || [])) {
            for (const zweig of ((l.data && l.data.main) || [])) {
              for (const item of (zweig || [])) if (item && item.json) raus.push(item.json);
            }
          }
          return raus;
        };
        const fetch = (name) => all(name)[0] || null;
        const test = fetch("Test-Entry") || {};
        const eingabe = fetch("Input") || {};
        const question = ((test.body || {}).message || {}).text || eingabe.text || "?";
        console.log(" Question   :" + question);
        const short = fetch("Short?");
        if (short) {
          const kb = fetch("Shortcut?");
          console.log(" Level 0 :" + (short.short || "not recognized"));
        }
        const bl = all("Read commands");
        if (bl.length) {
          console.log(" Commands :" + bl.map((b) => (b.type || "?") + "#" + b.nr
              + (b.command && b.command.enqueue ? "(queuing)" : "")).join(", "));
        }
        const over = fetch("Get overview");
        if (over) console.log(" Overview:" + String(over.answer || over.error || "")
          .slice(0, 160));
        const sammlung = all("Collect results").length + all("Replacement answer").length
          + all("Mailbox answer").length + all("Control answer").length
          + all("Overview answer").length + all("Collect addendum").length;
        if (sammlung) console.log(" Runs:" + sammlung);
        const answer = fetch("Build answer") || fetch("Answer") || {};
        if (answer.answer) {
          console.log(" Answer :");
          String(answer.answer).split("\n").forEach((zeile) => console.log("    " + zeile));
        }
        if (answer.keyboard) {
          const knoepfe = ((answer.keyboard.inline_keyboard) || [])
            .map((z) => z.map((k) => k.text).join(" | ")).join(" // ");
          console.log(" Buttons :" + knoepfe);
        }
        const send = fetch("Send") || fetch("Send (short message)");
        if (send && send.error) {
          console.log(" Send  : ERROR" + String(send.error.message || send.error).slice(0, 120));
        }
        Object.keys(runData).forEach((name) => {
          const laeufe = runData[name] || [];
          const last = laeufe[laeufe.length - 1];
          if (last && last.error) {
            console.log(" ERROR in" + name + ": "
              + String(last.error.message || "").slice(0, 160));
          }
        });
      }
      if (--open === 0) db.close();
    });
  });
});
