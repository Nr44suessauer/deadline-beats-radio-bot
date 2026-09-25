// Prueft die Weiche DIENST_ART_JS des Radio-Bots ohne n8n.
// Aufruf:  node 11-dienst-art-test.js /tmp/eingabe.js /tmp/dienst-art.js
//
// Die Weiche entscheidet, ob eine Nachricht an ein Modul im Dienst radio-tts geht:
//   listen-knopf / listen-befehl  -> playlist.py (Wiedergabelisten)
//   meldung-ansagen / meldung-verwerfen -> meldungen.py (Postfach, Ansagen)
//
// Wichtig: der Prueflauf schickt echte Telegram-Updates zuerst durch EINGABE_JS
// und dann durch die Weiche. Nur so fallen vertauschte Feldnamen auf - ein
// Tippfehler ("istCallback" statt "isCallback") blieb sonst unbemerkt und liess
// jeden Knopfdruck am Listen-Modul vorbeilaufen.
const fs = require('fs');
const EINGABE = fs.readFileSync(process.argv[2], 'utf8');
const DIENST_ART = fs.readFileSync(process.argv[3], 'utf8');

function verlauf(update) {
  // Achtung: hier darf KEIN "const $input" im Umfeld stehen - Node bindet den
  // Parameter von new Function dann nicht (nachgestellt: nur in Funktionsumfang,
  // auf Modulebene klappt es). Darum die Attrappe direkt uebergeben.
  const eingabe = new Function('$input', EINGABE)({ first: () => ({ json: update }) });
  const felder = (eingabe && eingabe[0] && eingabe[0].json) || {};
  const weiche = new Function('$json', DIENST_ART)(felder);
  const aus = (weiche && weiche[0] && weiche[0].json) || {};
  return { art: aus.dienstArt || '', kennung: aus.meldungKennung || '', felder };
}

const CHAT = DEINE-CHAT-ID;
const nachricht = (text) => ({ message: { message_id: 1, chat: { id: CHAT, type: 'private' },
  from: { id: CHAT, first_name: 'Test' }, text } });
const knopf = (daten) => ({ callback_query: { id: '1', from: { id: CHAT, first_name: 'Test' },
  data: daten, message: { message_id: 690, chat: { id: CHAT, type: 'private' } } } });

// [Update, erwartet, Erlaeuterung]
const faelle = [
  // --- Texte rund um Wiedergabelisten -> Listen-Modul
  [nachricht('baue eine Playlist Sommer aus Scooter'), 'listen-befehl', 'bauen'],
  [nachricht('mach mir eine playlist 90er hits'), 'listen-befehl', 'bauen mit anderem Wort'],
  [nachricht('spiele die Playlist Sommer'), 'listen-befehl', 'abspielen'],
  [nachricht('starte die Liste Sommer 2026'), 'listen-befehl', 'abspielen (Liste)'],
  [nachricht('spiele eine playlist'), 'listen-befehl', 'Listenwahl'],
  [nachricht('was ist in der Playlist Sommer'), 'listen-befehl', 'ansehen'],
  [nachricht('zeige den Inhalt der Liste List A'), 'listen-befehl', 'ansehen (Liste)'],
  [nachricht('benenne die Playlist Sommer in Sommer 2026 um'), 'listen-befehl', 'umbenennen'],
  [nachricht('welche Wiedergabelisten gibt es'), 'listen-befehl', 'Uebersicht'],
  [nachricht('zeige mir die Listen'), 'listen-befehl', 'Uebersicht (Liste)'],
  [nachricht('leere die Playlist Sommer'), 'listen-befehl', 'leeren'],
  [nachricht('loesche die Playlist Sommer'), 'listen-befehl', 'loeschen'],
  [nachricht('nimm Hyper Hyper in die Playlist Sommer'), 'listen-befehl', 'ergaenzen'],
  [nachricht('entferne Hyper Hyper aus der Playlist Sommer'), 'listen-befehl', 'Titel entfernen'],
  [nachricht('lege eine Wiedergabeliste Testlauf an'), 'listen-befehl', 'anlegen (Ausdruck des Betreibers)'],
  [nachricht('baue eine playlist aus scooter und spiele sie'), 'listen-befehl', 'anlegen und gleich abspielen'],

  // --- Knoepfe des Menues -> Listen-Modul
  [knopf('p3'), 'listen-knopf', 'Titel 3 an/abwaehlen'],
  [knopf('pa'), 'listen-knopf', 'alle'],
  [knopf('pk'), 'listen-knopf', 'keine'],
  [knopf('pf'), 'listen-knopf', 'Fertig'],
  [knopf('px'), 'listen-knopf', 'Abbrechen/Genug'],
  [knopf('l2'), 'listen-knopf', 'Liste 2 waehlen'],
  [knopf('j'), 'listen-knopf', 'Ja'],
  [knopf('n'), 'listen-knopf', 'Nein'],
  [knopf('v'), 'listen-knopf', 'Jetzt abspielen'],

  // --- Knoepfe der Meldungs-Karte -> Meldungs-Modul
  [knopf('mm260920-0007'), 'meldung-ansagen', 'Meldung vorlesen lassen'],
  [knopf('xm260920-0007'), 'meldung-verwerfen', 'Meldung verwerfen'],
  [knopf('mM260920-0007'), '', 'Kennung mit Grossbuchstabe: kein Knopf von uns'],

  // --- alles andere laeuft wie bisher (Analyse und Sprachmodell)
  [nachricht('spiele Benzin'), '', 'Musikwunsch'],
  [nachricht('ich möchte was von Scooter'), '', 'Musikwunsch'],
  [nachricht('was läuft gerade'), '', 'Frage zum Programm'],
  [nachricht('naechster Titel'), '', 'Steuerung'],
  [nachricht('danke'), '', 'Smalltalk'],
  [nachricht('mach irgendwas mit dem Sender'), '', 'unbekannt'],
  [nachricht(''), '', 'leer'],
  [knopf('w2'), '', 'alte Auswahlliste (w2) bleibt beim Agenten'],
  [knopf('irgendwas'), '', 'fremder Knopf'],
];

let gut = 0;
for (const [update, erwartet, hinweis] of faelle) {
  const ergebnis = verlauf(update);
  const art = ergebnis.art;
  const felder = ergebnis.felder;
  const ok = art === erwartet;
  if (ok) gut += 1;
  const was = update.callback_query ? 'Knopf ' + update.callback_query.data
    : '"' + update.message.text + '"';
  const kennung = update.callback_query && ergebnis.kennung ? ' (kennung ' + ergebnis.kennung + ')' : '';
  console.log((ok ? 'ok   ' : 'ABW. ') + was.padEnd(52) + ' -> ' + (art || '(weiter wie bisher)')
    + kennung + (ok ? '   ' + hinweis : '   erwartet: ' + (erwartet || '(weiter wie bisher)')));
  if (!ok) {
    console.log('       Felder aus Eingabe: ' + JSON.stringify(felder).slice(0, 200));
  }
}
console.log('\n' + gut + ' von ' + faelle.length + ' wie erwartet');
process.exit(gut === faelle.length ? 0 : 1);
