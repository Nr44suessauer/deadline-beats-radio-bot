// Prueft den Suchknoten des Radio-Bots mit echten Daten - ohne n8n.
//
// Der Knoten "Treffer aufbereiten" aus "Werkzeug - Titel suchen" wird hier in
// einer kleinen Umgebung ausgefuehrt (nur $, $json und $getWorkflowStaticData
// werden nachgebildet). So laesst sich pruefen, ob das Live-Archiv wirklich
// ausgeschlossen wird und normale Titel weiter funktionieren.
//
// Aufruf:  node 09-suchknoten-test.js <code.js> [suchbegriff ...]
const fs = require('fs');

const KATALOG = 'http://192.168.178.53:8881';
const SENDER = 'http://192.168.178.33';

const [codeDatei, ...begriffe] = process.argv.slice(2);
const CODE = fs.readFileSync(codeDatei, 'utf8');
const AZ_KEY = process.env.AZ_KEY;
if (!AZ_KEY) {
  console.error('AZ_KEY fehlt (über 09-suchknoten-test.sh aufrufen)');
  process.exit(1);
}

async function holeQuellen(text) {
  const [klug, sender] = await Promise.all([
    fetch(`${KATALOG}/suche?q=${encodeURIComponent(text)}&anzahl=25`).then((r) => r.json()).catch(() => ({})),
    fetch(`${SENDER}/api/station/1/files?rowCount=100&searchPhrase=${encodeURIComponent(text)}`,
      { headers: { 'X-API-Key': AZ_KEY } }).then((r) => r.json()).catch(() => ({})),
  ]);
  return { klug, sender };
}

function laufen(text, daten) {
  const static_ = { listen: [], suchen: {} };
  const knoten = {
    Eingang: { json: { suchtext: text, einreihen: false } },
    'Suche klug': daten.klug,
    'Suche Sender': daten.sender,
  };
  const $ = (name) => {
    const j = knoten[name];
    return { first: () => ({ json: j }), item: { json: j } };
  };
  const $getWorkflowStaticData = () => static_;
  const fn = new Function('$', '$getWorkflowStaticData', '$json', CODE);
  return fn($, $getWorkflowStaticData, knoten.Eingang.json);
}

(async () => {
  for (const text of begriffe) {
    const daten = await holeQuellen(text);
    const rohKlug = (daten.klug.treffer || []).length;
    const rohSender = (daten.sender.rows || []).length;
    const archivKlug = (daten.klug.treffer || []).filter((t) => String(t.path || '').startsWith('_Archiv/')).length;
    const archivSender = (daten.sender.rows || []).filter((t) => String(t.path || '').startsWith('_Archiv/')).length;

    let ergebnis;
    try {
      ergebnis = laufen(text, daten);
    } catch (e) {
      ergebnis = [{ json: { ergebnis: 'FEHLER: ' + e.message } }];
    }
    const j = (ergebnis && ergebnis[0] && ergebnis[0].json) || {};
    console.log(`\n=== "${text}" ===`);
    console.log(`  Quellen roh: Katalog ${rohKlug} (davon Archiv ${archivKlug}), `
      + `Sender ${rohSender} (davon Archiv ${archivSender})`);
    console.log(`  Pfad: ${j.pfad || '-'}`);
    if (j.auswahl) console.log(`  Auswahl: ${j.auswahl.join(' | ')}`);
    console.log(`  Ergebnis: ${String(j.ergebnis || '-').replace(/\n/g, ' / ').slice(0, 200)}`);
  }
})();
