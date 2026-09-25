// Prueft die Vorschaltstufe KURZ_JS des Radio-Bots ohne n8n.
// Aufruf:  node kurz-test.js /tmp/kurz.js
//
// Die Vorschaltstufe erkennt einfache Auftraege ohne Sprachmodell (schnell) und
// laesst alles andere in die KI-Kette (langsam). Wichtig ist beides: was schnell
// sein soll, muss schnell sein - und was das Sprachmodell braucht, darf nicht
// faelschlich hier haengen bleiben.
const fs = require('fs');
const CODE = fs.readFileSync(process.argv[2], 'utf8');

function laufen(text) {
  const speicher = {};
  const $json = { text: text, chatId: '1' };
  const $getWorkflowStaticData = () => speicher;
  const fn = new Function('$json', '$getWorkflowStaticData', CODE);
  try {
    const e = fn($json, $getWorkflowStaticData);
    const j = (e && e[0] && e[0].json) || {};
    if (!j.kurz) return 'KI';
    const b = j.befehl || {};
    const wert = b.suchtext || b.richtung || b.steuerung || b.frage || b.art || '';
    return j.kurz + '/' + wert;
  } catch (fehler) {
    return 'FEHLER: ' + fehler.message;
  }
}

// [Text, erwarteter Anfang]
const faelle = [
  // --- Postfach: ohne Sprachmodell und ohne Ansage
  ['was gibt es fuer Meldungen', 'postfach'],
  ['was liegt im Postfach', 'postfach'],
  ['welche Meldungen warten', 'postfach'],
  ['zeig mir das Postfach', 'postfach'],
  ['gibt es Meldungen', 'postfach'],
  ['was gibt es fuer mitteilungen', 'postfach'],

  // --- muss in die KI-Kette (Recherche, Ansage, mehrere Auftraege)
  ['lies die nachrichten vor', 'KI'],
  ['suche nach dem wetter fuer Marbach am Neckar', 'KI'],
  ['was gibt es neues', 'KI'],
  ['hol mir die nachrichten', 'KI'],
  ['spiele Hyper Hyper von Scooter und suche nach dem wetter fuer Marbach am Neckar', 'KI'],
  ['sag durch: die sendung beginnt in fuenf minuten', 'KI'],
  ['lege eine Wiedergabeliste an', 'KI'],

  // --- Bestand: das muss weiter schnell gehen
  ['spiele Benzin', 'wunsch/benzin'],
  ['spiel mir mal was von Scooter', 'wunsch/scooter'],
  ['was laeuft', 'status'],
  ['naechster Titel', 'steuerung/skip'],
  ['pause', 'steuerung/pause'],
  ['2', 'wunsch/2'],
];

let gut = 0;
for (const [text, soll] of faelle) {
  const ist = laufen(text);
  const ok = ist.startsWith(soll);
  if (ok) gut += 1;
  console.log((ok ? 'ok   ' : 'ABW. ') + '"' + text + '"'.padEnd(4)
    + ' -> ' + ist + (ok ? '' : '   soll: ' + soll));
}
console.log('\n' + gut + ' von ' + faelle.length + ' wie erwartet');
process.exit(gut === faelle.length ? 0 : 1);
