// Prueft die drei Knoten rund um Ergebnis und Antwort (ohne n8n).
//   PRUEFUNG_LESEN_JS   - Urteil: Frage an den Nutzer ist kein Fehlschlag
//   NACHTRAG_SAMMELN_JS - leerer zweiter Versuch darf die Ausgabe nicht loeschen
//   ANTWORT_BAUEN_JS    - Auswahlliste sichtbar + Knoepfe, kein "Nicht erledigt"
//
// Hintergrund: die Sprachnachricht vom 2026-09-20 ("Spiele mir was von Michael
// Jackson und wie wird das Wetter in Ludwigsburg?") hat das Wetter angesagt, aber
// die Titelliste wurde zu "⚠️ (keine Ausgabe)" - der Nutzer konnte nicht waehlen.
const fs = require('fs');
const lies = (n) => fs.readFileSync('/tmp/js/' + n + '.js', 'utf8');

const PRUEFUNG_LESEN = lies('PRUEFUNG_LESEN_JS');
const NACHTRAG = lies('NACHTRAG_SAMMELN_JS');
const ANTWORT = lies('ANTWORT_BAUEN_JS');

let gut = 0;
let schlecht = 0;
function pruefe(name, ist, soll) {
  const ok = typeof soll === 'function' ? soll(ist) : ist === soll;
  if (ok) gut += 1; else schlecht += 1;
  const zeige = (w) => { try { return String(JSON.stringify(w)).slice(0, 400); } catch (e) { return String(w); } };
  console.log((ok ? 'ok   ' : 'ABW. ') + name + (ok ? '' : '\n        ist:  ' + zeige(ist)));
}

// ---------------------------------------------------------------- Attrappen
function merker(daten) { return () => daten; }

function laufen(code, { json = {}, knoten = {}, daten = {}, erste } = {}) {
  const $ = (name) => ({ first: () => ({ json: knoten[name] || {} }), all: () => [] });
  const $json = json;
  const $getWorkflowStaticData = merker(daten);
  const $input = { first: () => ({ json: json }), all: () => [{ json: json }] };
  const fn = new Function('$json', '$getWorkflowStaticData', '$', '$input', code);
  return fn($json, $getWorkflowStaticData, $, $input);
}

// Ein Befehl mit Rueckfrage (so sah die Ausgabe des Werkzeugs aus) und einer,
// der geklappt hat.
const LISTE = 'Mehrere Titel passen zu "Michael Jackson":\n'
  + '1. Michael Jackson - Thriller  (5:57)\n'
  + '2. Michael Jackson - Love Never Felt So Good  (3:26)\n'
  + '3. Fatboy Slim - Michael Jackson  (5:48)\n\n'
  + 'Frage kurz, welcher gemeint ist.';

// ------------------------------------------- 1) Urteil: Frage ist keine Niederlage
{
  const daten = { lauf: { befehle: [
    { nr: 1, art: 'spielen', befehl: { suchtext: 'Michael Jackson' }, ausgabe: LISTE, ok: null, versuche: 1 },
    { nr: 2, art: 'recherche', befehl: { art: 'recherche' }, ausgabe: 'Das Wetter fuer Ludwigsburg ist im Radio angesagt worden.', ok: null, versuche: 1 },
  ] } };
  const aus = laufen(PRUEFUNG_LESEN, {
    json: { chatId: '1', befehle: daten.lauf.befehle },
    knoten: { Schleife: { nr: 1 }, 'Lage holen': {}, 'Warteschlange holen': {} },
    daten,
  });
  const b1 = daten.lauf.befehle[0];
  const b2 = daten.lauf.befehle[1];
  pruefe('Frage wird als Rueckfrage erkannt', b1.frage, true);
  pruefe('Auswahlliste bleibt im Wortlaut erhalten', b1.ausgabe, LISTE);
  pruefe('Rueckfrage wird nicht nachgefasst', aus[0].json.nichts_zu_tun, true);
  pruefe('erfolgreicher Befehl bleibt ok', b2.ok, true);
}

// --------------------------------- 2) leerer zweiter Versuch loescht nichts
{
  const daten = { lauf: { befehle: [
    { nr: 1, art: 'spielen', befehl: { suchtext: 'Michael Jackson' }, ausgabe: LISTE, ok: false, versuche: 1 },
  ] } };
  laufen(NACHTRAG, {
    json: { output: '' },
    knoten: { 'Schleife 2': { nr: 1 } },
    daten,
  });
  const b = daten.lauf.befehle[0];
  pruefe('Auswahlliste ueberlebt den leeren zweiten Versuch', b.ausgabe, LISTE);
  pruefe('Grund nennt das fehlende Nachfassen', b.grund, 'Nachfassen brachte keine Antwort');
}

// --------------------------------- 3) Antwort: Liste sichtbar, kein "Nicht erledigt"
{
  const daten = { lauf: { befehle: [
    { nr: 1, art: 'spielen', befehl: { suchtext: 'Michael Jackson' }, ausgabe: LISTE, ok: false, frage: true, versuche: 1 },
    { nr: 2, art: 'recherche', befehl: { art: 'recherche' }, ausgabe: 'Das Wetter fuer Ludwigsburg ist im Radio angesagt worden.', ok: true, versuche: 1 },
  ] } };
  const aus = laufen(ANTWORT, {
    json: {},
    knoten: { Schleife: { nr: 2, fertig: true }, Eingabe: { chatId: '1' } },
    daten,
  })[0].json;
  pruefe('keine Ausgabe"-Meldung mehr', aus.antwort, (a) => !/keine Ausgabe/.test(a));
  pruefe('Liste steht in der Antwort', aus.antwort, (a) => /1\. Michael Jackson - Thriller/.test(a) && /3\. Fatboy Slim/.test(a));
  pruefe('Wetter bleibt als erledigt stehen', aus.antwort, (a) => /Das Wetter fuer Ludwigsburg/.test(a));
  pruefe('kein "Nicht erledigt" bei einer Rueckfrage', aus.antwort, (a) => !/Nicht erledigt/.test(a));
  pruefe('Hinweis auf Knopf oder Nummer', aus.antwort, (a) => /Knopf oder antworte mit der Nummer/.test(a));
  pruefe('Knoepfe aus der Liste gebaut', (aus.tastatur || {}).inline_keyboard, (k) =>
    Array.isArray(k) && k.length === 3 && k[0][0].callback_data === 'w1'
      && k[0][0].text === 'Michael Jackson - Thriller' && k[2][0].callback_data === 'w3');
}

// --------------------------------- 4) echter Fehlschlag bleibt Fehlschlag
{
  const daten = { lauf: { befehle: [
    { nr: 1, art: 'spielen', befehl: { suchtext: 'Billie Jean' }, ausgabe: 'KEINE TREFFER: nichts gefunden.', ok: false, versuche: 1 },
  ] } };
  const aus = laufen(ANTWORT, {
    json: {},
    knoten: { Schleife: { nr: 1, fertig: true }, Eingabe: { chatId: '1' } },
    daten,
  })[0].json;
  pruefe('Fehlschlag wird weiter gemeldet', aus.antwort, (a) => /Nicht erledigt: Nr\. 1/.test(a));
  pruefe('ohne Knoepfe', aus.tastatur, null);
}

// ------------------------------- 5) zusammengezogene Liste (so kam sie an)
{
  const FLACH = 'Es gibt mehrere passende Titel: 1. Thriller, 2. Love Never Felt So Good '
    + '(Fedde Le Grand Remix), 3. There Must Be More To Life Than This (mit Queen), '
    + '4. Fatboy Slim - Michael Jackson Welchen Titel soll ich spielen?';
  const daten = { lauf: { befehle: [
    { nr: 1, art: 'spielen', befehl: { suchtext: 'Michael Jackson' }, ausgabe: FLACH, ok: false, frage: true, versuche: 1 },
  ] } };
  const aus = laufen(ANTWORT, {
    json: {},
    knoten: { Schleife: { nr: 1, fertig: true }, Eingabe: { chatId: '1' } },
    daten,
  })[0].json;
  const tasten = ((aus.tastatur || {}).inline_keyboard || []).map((k) => k[0].text);
  pruefe('Knoepfe aus zusammengezogener Liste', tasten.length, 4);
  pruefe('erster Knopf ist der erste Titel', tasten[0], 'Thriller');
  pruefe('letzter Knopf ohne Nachsatz', tasten[3], 'Fatboy Slim - Michael Jackson');
}

// ------------------------- 6) Postfachliste bekommt keine Knoepfe
{
  const daten = { lauf: { befehle: [
    { nr: 1, art: 'postfach', befehl: { art: 'postfach' }, ok: true, versuche: 1,
      ausgabe: 'Im Postfach 2 offene Meldung(en): 1. Wetter Marbach? (wetter, Kennung m1) | 2. Nachrichtenprobe (nachrichten, Kennung m2).' },
  ] } };
  const aus = laufen(ANTWORT, {
    json: {},
    knoten: { Schleife: { nr: 1, fertig: true }, Eingabe: { chatId: '1' } },
    daten,
  })[0].json;
  pruefe('Postfachliste ohne Knoepfe', aus.tastatur, null);
  pruefe('Postfachtext unveraendert durchgereicht', aus.antwort, (a) => /Im Postfach 2 offene/.test(a));
}

// --------------------------------- 7) Kurzbefehl bleibt schlicht
{
  const daten = { lauf: { schlicht: true, befehle: [
    { nr: 1, art: 'status', ausgabe: 'Jetzt laeuft: X', ok: true, versuche: 1 },
  ] } };
  const aus = laufen(ANTWORT, {
    json: {},
    knoten: { Schleife: { nr: 1, fertig: true }, Eingabe: { chatId: '1' } },
    daten,
  })[0].json;
  pruefe('Kurzbefehl ohne Zeichen davor', aus.antwort, 'Jetzt laeuft: X');
}

console.log('\n' + gut + ' ok, ' + schlecht + ' abweichend');
process.exit(schlecht ? 1 : 0);
