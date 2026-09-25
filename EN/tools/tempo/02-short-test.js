// Checks the pre-stage (SHORT_JS) of the radio bot without n8n.
// Call:  node 02-short-test.js <short-code.js>
const fs = require('fs');
const CODE = fs.readFileSync(process.argv[2], 'utf8');

function run(text) {
  const speicher = {};
  const $json = { text: text, chatId: '1' };
  const $getWorkflowStaticData = () => speicher;
  const fn = new Function('$json', '$getWorkflowStaticData', CODE);
  try {
    const result = fn($json, $getWorkflowStaticData);
    const j = (result && result[0] && result[0].json) || {};
    if (!j.short) return 'AI chain (slow)';
    const b = j.command || {};
    return 'SCHNELL ' + j.short + ': ' + (b.searchtext || b.direction || b.control || b.question || '?');
  } catch (e) {
    return 'ERROR:' + e.message;
  }
}

const cases = [
  ['I’ll play something by Scooter.', 'SCHNELL wish: scooter'],
  ['I would like something by Rammstein', 'SCHNELL wish: rammstein'],
  ['I want to hear something by Nirvana', 'SCHNELL wish: nirvana'],
  ['can you play something by Nirvana', 'SCHNELL wish: nirvana'],
  ['play me something by Scooter', 'SCHNELL wish: scooter'],
  ['play Hyper Hyper by Scooter', 'SCHNELL wish: hyper hyper from_ scooter'],
  ['play Gasoline', 'SCHNELL wish: benzin'],
  ['Put on something lively', 'SCHNELL direction/…'],
  ['next track', 'SCHNELL control: skip'],
  ['what’s playing', 'SCHNELL status: was running gerade'],
  ['2', 'SCHNELL wish: 2'],
  ['play 99 Luftballons', 'SCHNELL wish: 99 luftballons'],
  ['Create a test playlist run', 'AI chain (slow)'],
  ['I would like 3 songs by Scooter', 'AI chain (slow)'],
  ['play three songs by Rammstein', 'AI chain (slow)'],
  ['play two tracks by Nirvana', 'AI chain (slow)'],
  ['play something by Scooter and then something by Nirvana', 'AI chain (slow)'],
  ['danke', 'AI chain (slow)'],
  ['I have a question about the show', 'AI chain (slow)'],
];

let good = 0;
for (const [text, erwartet] of cases) {
  const result = run(text);
  const ok = erwartet.startsWith('SCHNELL direction') ? result.startsWith('SCHNELL direction')
    : result === erwartet;
  if (ok) good += 1;
  console.log((ok ? 'ok   ' : 'ABW. ') + '"' + text + '"\n         ' + result
    + (ok ? '' : '\n         expected: ' + erwartet));
}
console.log('\n' + good + ' of ' + cases.length + ' as expected');
