// Prueft die Vorschaltstufe (KURZ_JS) des Radio-Bots ohne n8n.
// Aufruf:  node 02-kurz-test.js <kurz-code.js>
const fs = require('fs');
const CODE = fs.readFileSync(process.argv[2], 'utf8');

function laufen(text) {
  const speicher = {};
  const $json = { text: text, chatId: '1' };
  const $getWorkflowStaticData = () => speicher;
  const fn = new Function('$json', '$getWorkflowStaticData', CODE);
  try {
    const ergebnis = fn($json, $getWorkflowStaticData);
    const j = (ergebnis && ergebnis[0] && ergebnis[0].json) || {};
    if (!j.kurz) return 'KI-Kette (langsam)';
    const b = j.befehl || {};
    return 'SCHNELL ' + j.kurz + ': ' + (b.suchtext || b.richtung || b.steuerung || b.frage || '?');
  } catch (e) {
    return 'FEHLER: ' + e.message;
  }
}

const faelle = [
  ['Ich spiele mir etwas von Scooter.', 'SCHNELL wunsch: scooter'],
  ['ich möchte was von Rammstein', 'SCHNELL wunsch: rammstein'],
  ['Ich will mal etwas von Nirvana hören', 'SCHNELL wunsch: nirvana'],
  ['kannst du mal was von Nirvana spielen', 'SCHNELL wunsch: nirvana'],
  ['spiel mir mal was von Scooter', 'SCHNELL wunsch: scooter'],
  ['spiele Hyper Hyper von Scooter', 'SCHNELL wunsch: hyper hyper von scooter'],
  ['spiele Benzin', 'SCHNELL wunsch: benzin'],
  ['Mach mal was Peppiges an', 'SCHNELL richtung/…'],
  ['naechster Titel', 'SCHNELL steuerung: skip'],
  ['was läuft', 'SCHNELL status: was laeuft gerade'],
  ['2', 'SCHNELL wunsch: 2'],
  ['spiele 99 Luftballons', 'SCHNELL wunsch: 99 luftballons'],
  ['lege eine Wiedergabeliste Testlauf an', 'KI-Kette (langsam)'],
  ['ich möchte 3 Lieder von Scooter', 'KI-Kette (langsam)'],
  ['spiele drei Lieder von Rammstein', 'KI-Kette (langsam)'],
  ['spiele zwei Titel von Nirvana', 'KI-Kette (langsam)'],
  ['spiele was von Scooter und danach was von Nirvana', 'KI-Kette (langsam)'],
  ['danke', 'KI-Kette (langsam)'],
  ['Ich habe eine Frage zur Sendung', 'KI-Kette (langsam)'],
];

let gut = 0;
for (const [text, erwartet] of faelle) {
  const ist = laufen(text);
  const ok = erwartet.startsWith('SCHNELL richtung') ? ist.startsWith('SCHNELL richtung')
    : ist === erwartet;
  if (ok) gut += 1;
  console.log((ok ? 'ok   ' : 'ABW. ') + '"' + text + '"\n         ' + ist
    + (ok ? '' : '\n         erwartet: ' + erwartet));
}
console.log('\n' + gut + ' von ' + faelle.length + ' wie erwartet');
