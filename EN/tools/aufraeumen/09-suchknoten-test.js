// Checks the search node of the Radio Bot with real data - without n8n.
//
// The node “Process hits” from “Tool - Search title” is executed here in
// a small environment (only $, $json and $getWorkflowStaticData
// are mocked). This allows checking whether the live archive is really
// excluded and normal titles still work.
//
// Call:  node 09-suchknoten-test.js <code.js> [searchterm ...]
const fs = require('fs');

const KATALOG = 'http://192.168.178.53:8881';
const SENDER = 'http://192.168.178.33';

const [codeDatei, ...begriffe] = process.argv.slice(2);
const CODE = fs.readFileSync(codeDatei, 'utf8');
const AZ_KEY = process.env.AZ_KEY;
if (!AZ_KEY) {
  console.error('AZ_KEY missing (call via 09-suchknoten-test.sh)');
  process.exit(1);
}

async function holeQuellen(text) {
  const [klug, sender] = await Promise.all([
    fetch(`${KATALOG}/search?q=${encodeURIComponent(text)}&count=25`).then((r) => r.json()).catch(() => ({})),
    fetch(`${SENDER}/api/station/1/files?rowCount=100&searchPhrase=${encodeURIComponent(text)}`,
      { headers: { 'X-API-Key': AZ_KEY } }).then((r) => r.json()).catch(() => ({})),
  ]);
  return { klug, sender };
}

function run(text, data) {
  const static_ = { listen: [], suchen: {} };
  const nodes = {
    Entry: { json: { searchtext: text, enqueue: false } },
    'Smart search': data.klug,
    'Station search': data.sender,
  };
  const $ = (name) => {
    const j = nodes[name];
    return { first: () => ({ json: j }), item: { json: j } };
  };
  const $getWorkflowStaticData = () => static_;
  const fn = new Function('$', '$getWorkflowStaticData', '$json', CODE);
  return fn($, $getWorkflowStaticData, nodes.Entry.json);
}

(async () => {
  for (const text of begriffe) {
    const data = await holeQuellen(text);
    const rohKlug = (data.klug.hits || []).length;
    const rohSender = (data.sender.rows || []).length;
    const archivKlug = (data.klug.hits || []).filter((t) => String(t.path || '').startsWith('_Archiv/')).length;
    const archivSender = (data.sender.rows || []).filter((t) => String(t.path || '').startsWith('_Archiv/')).length;

    let result;
    try {
      result = run(text, data);
    } catch (e) {
      result = [{ json: { result: 'ERROR:' + e.message } }];
    }
    const j = (result && result[0] && result[0].json) || {};
    console.log(`\n=== "${text}" ===`);
    console.log(`  sources raw: Katalog ${rohKlug} (davon Archiv ${archivKlug}), `
      + `Sender ${rohSender} (davon Archiv ${archivSender})`);
    console.log(`  path: ${j.path || '-'}`);
    if (j.selection) console.log(`  Auswahl: ${j.selection.join(' | ')}`);
    console.log(`  result: ${String(j.result || '-').replace(/\n/g, ' / ').slice(0, 200)}`);
  }
})();
