// Checks the pre-stage SHORT_JS of the radio bot without n8n.
// Call:  node short-test.js /tmp/short.js
//
// The pre-stage recognizes simple commands without a language model (fast) and
// passes everything else to the AI chain (slow). Both matter: what should be
// fast must be fast - and what the language model needs must not
// faelschlich here haengen bleiben.
const fs = require('fs');
const CODE = fs.readFileSync(process.argv[2], 'utf8');

function run(text) {
  const speicher = {};
  const $json = { text: text, chatId: '1' };
  const $getWorkflowStaticData = () => speicher;
  const fn = new Function('$json', '$getWorkflowStaticData', CODE);
  try {
    const e = fn($json, $getWorkflowStaticData);
    const j = (e && e[0] && e[0].json) || {};
    if (!j.short) return 'AI';
    const b = j.command || {};
    const wert = b.searchtext || b.direction || b.control || b.question || b.type || '';
    return j.short + '/' + wert;
  } catch (error) {
    return 'ERROR:' + error.message;
  }
}

// [Text, erwarteter beginning]
const cases = [
  // --- inbox: without language model and without announcement
  ['what messages are there', 'inbox'],
  ['what is in the mailbox', 'inbox'],
  ['which messages are waiting', 'inbox'],
  ['show me the mailbox', 'inbox'],
  ['are there messages', 'inbox'],
  ['what notifications are there', 'inbox'],

  // --- must go into the AI chain (research, announcement, multiple commands)
  ['read the messages aloud', 'AI'],
  ['search for the weather for Marbach am Neckar', 'AI'],
  ['what’s new', 'AI'],
  ['get me the messages', 'AI'],
  ['play Hyper Hyper by Scooter and search for the weather for Marbach am Neckar', 'AI'],
  ['say: the show begins in five minutes', 'AI'],
  ['create a playlist', 'AI'],

  // --- stock: this must keep being fast
  ['play Gasoline', 'wish/benzin'],
  ['play me something by Scooter', 'wish/scooter'],
  ['what’s playing', 'status'],
  ['next track', 'control/skip'],
  ['pause', 'control/pause'],
  ['2', 'wish/2'],
];

let good = 0;
for (const [text, expected] of cases) {
  const result = run(text);
  const ok = result.startsWith(expected);
  if (ok) good += 1;
  console.log((ok ? 'ok   ' : 'ABW. ') + '"' + text + '"'.padEnd(4)
    + ' -> ' + result + (ok ? '' : ' should be:' + expected));
}
console.log('\n' + good + ' of ' + cases.length + ' as expected');
process.exit(good === cases.length ? 0 : 1);
