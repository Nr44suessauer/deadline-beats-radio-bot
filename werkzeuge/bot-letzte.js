// Zeigt die letzten Ausfuehrungen des Radio-Agenten: Frage, Stufen, Antwort, Fehler.
//
// Aufruf im Container:
//   docker exec -u node n8n node /tmp/bot-letzte.js [anzahl] [workflowId]
// Ueber SSH (wie in den anderen Werkzeugen):
//   ssh -F .../proxmox-ssh/config ai-server "pct exec 103 -- bash -lc '
//     docker cp /tmp/bot-letzte.js n8n:/tmp/ >/dev/null
//     docker exec -u node n8n node /tmp/bot-letzte.js 3'"
const sqlite3 = require("/usr/local/lib/node_modules/n8n/node_modules/sqlite3");
const { parse } = require("/usr/local/lib/node_modules/n8n/node_modules/flatted");

const ANZAHL = parseInt(process.argv[2] || "3", 10);
const WORKFLOW = process.argv[3] || "RadioAgentBot";
const db = new sqlite3.Database("/home/node/.n8n/database.sqlite");

db.all("select id, status, startedAt from execution_entity where workflowId = ? order by id desc limit "
       + ANZAHL, [WORKFLOW], (e, rows) => {
  if (e) { console.error(e.message); process.exit(1); }
  if (!rows.length) { console.log("keine Ausfuehrungen fuer " + WORKFLOW); db.close(); return; }
  let offen = rows.length;
  rows.reverse().forEach((r) => {
    db.get("select data from execution_data where executionId = ?", [r.id], (e2, z) => {
      console.log("\n===== Ausfuehrung " + r.id + " (" + r.status + ")");
      if (z) {
        const d = parse(z.data);
        const runData = (d.resultData && d.resultData.runData) || {};
        const alle = (name) => {
          const raus = [];
          for (const l of (runData[name] || [])) {
            for (const zweig of ((l.data && l.data.main) || [])) {
              for (const item of (zweig || [])) if (item && item.json) raus.push(item.json);
            }
          }
          return raus;
        };
        const hol = (name) => alle(name)[0] || null;
        const test = hol("Test-Eingang") || {};
        const eingabe = hol("Eingabe") || {};
        const frage = ((test.body || {}).message || {}).text || eingabe.text || "?";
        console.log("  Frage   : " + frage);
        const kurz = hol("Kurz?");
        if (kurz) {
          const kb = hol("Kurzbefehl?");
          console.log("  Stufe 0 : " + (kurz.kurz || "nicht erkannt"));
        }
        const bl = alle("Befehle lesen");
        if (bl.length) {
          console.log("  Befehle : " + bl.map((b) => (b.art || "?") + "#" + b.nr
              + (b.befehl && b.befehl.einreihen ? "(einreihen)" : "")).join(", "));
        }
        const ueber = hol("Ueberblick holen");
        if (ueber) console.log("  Ueberblick: " + String(ueber.antwort || ueber.error || "")
          .slice(0, 160));
        const sammlung = alle("Ergebnis sammeln").length + alle("Ersatz Antwort").length
          + alle("Postfach Antwort").length + alle("Steuerung Antwort").length
          + alle("Ueberblick Antwort").length + alle("Nachtrag sammeln").length;
        if (sammlung) console.log("  Durchlaeufe: " + sammlung);
        const antwort = hol("Antwort bauen") || hol("Antwort") || {};
        if (antwort.antwort) {
          console.log("  Antwort :");
          String(antwort.antwort).split("\n").forEach((zeile) => console.log("    " + zeile));
        }
        if (antwort.tastatur) {
          const knoepfe = ((antwort.tastatur.inline_keyboard) || [])
            .map((z) => z.map((k) => k.text).join(" | ")).join(" // ");
          console.log("  Knoepfe : " + knoepfe);
        }
        const senden = hol("Senden") || hol("Senden (Kurzmeldung)");
        if (senden && senden.error) {
          console.log("  Senden  : FEHLER " + String(senden.error.message || senden.error).slice(0, 120));
        }
        Object.keys(runData).forEach((name) => {
          const laeufe = runData[name] || [];
          const letzter = laeufe[laeufe.length - 1];
          if (letzter && letzter.error) {
            console.log("  FEHLER in " + name + ": "
              + String(letzter.error.message || "").slice(0, 160));
          }
        });
      }
      if (--offen === 0) db.close();
    });
  });
});
