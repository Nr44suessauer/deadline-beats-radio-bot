// Checks the SERVICE_TYPE_JS switch of the radio bot without n8n.
// Call:  node 11-service-type-test.js /tmp/eingabe.js /tmp/service-type.js
//
// The switch decides whether a message goes to a module in the radio-tts service:
//   listen-button / listen-command  -> playlist.py (Playlists)
//   news-announce / news-discard -> news.py (Inbox, Announcements)
//
// Important: the test run sends real Telegram updates first through INPUT_JS
// and then through the switch. Only that way swapped field names show up - a
// typo ("istCallback" instead of "isCallback") would otherwise go unnoticed and let
// jeden Knopfdruck am playlist module vorbeilaufen.
const fs = require('fs');
const EINGABE = fs.readFileSync(process.argv[2], 'utf8');
const DIENST_ART = fs.readFileSync(process.argv[3], 'utf8');

function verlauf(update) {
  // Attention: there must be NO "const $input" in scope here - Node does not bind the
  // Parameter from_ new Function then not (nachgestellt: only in Funktionsumfang,
  // at module level it works). That is why the mock is passed directly.
  const eingabe = new Function('$input', EINGABE)({ first: () => ({ json: update }) });
  const felder = (eingabe && eingabe[0] && eingabe[0].json) || {};
  const weiche = new Function('$json', DIENST_ART)(felder);
  const out = (weiche && weiche[0] && weiche[0].json) || {};
  return { type: out.serviceType || '', identifier: out.meldungKennung || '', felder };
}

const CHAT = YOUR-CHAT-ID;
const message = (text) => ({ message: { message_id: 1, chat: { id: CHAT, type: 'private' },
  from: { id: CHAT, first_name: 'Test' }, text } });
const button = (data) => ({ callback_query: { id: '1', from: { id: CHAT, first_name: 'Test' },
  data: data, message: { message_id: 690, chat: { id: CHAT, type: 'private' } } } });

// [Update, erwartet, Erlaeuterung]
const cases = [
  // --- Texte around match Playlists -> playlist module
  [message('build a playlist called Summer from Scooter'), 'listen-command', 'build'],
  [message('make me a playlist 90s hits'), 'listen-command', 'build with different word'],
  [message('play the playlist Sommer'), 'listen-command', 'playback'],
  [message('start the list Summer 2026'), 'listen-command', 'play (list)'],
  [message('play a playlist'), 'listen-command', 'Listenwahl'],
  [message('what is in the playlist Sommer'), 'listen-command', 'view'],
  [message('show the content of the list List A'), 'listen-command', 'view (list)'],
  [message('rename the playlist Summer to Summer 2026'), 'listen-command', 'rename'],
  [message('which playlists exist'), 'listen-command', 'overview'],
  [message('show me the lists'), 'listen-command', 'Overview (list)'],
  [message('empty the playlist Summer'), 'listen-command', 'clear'],
  [message('delete the playlist Summer'), 'listen-command', 'delete'],
  [message('add Hyper Hyper to the playlist Summer'), 'listen-command', 'extend'],
  [message('remove Hyper Hyper from the playlist Summer'), 'listen-command', 'remove title'],
  [message('Create a test playlist run'), 'listen-command', 'create (expression of operator)'],
  [message('build a playlist from scooter and play it'), 'listen-command', 'create and play immediately'],

  // --- menu buttons -> playlist module
  [button('p3'), 'listen-button', 'select/deselect title 3'],
  [button('pa'), 'listen-button', 'all'],
  [button('pk'), 'listen-button', 'keine'],
  [button('pf'), 'listen-button', 'Fertig'],
  [button('px'), 'listen-button', 'Cancel/Enough'],
  [button('l2'), 'listen-button', 'select list 2'],
  [button('j'), 'listen-button', 'Ja'],
  [button('n'), 'listen-button', 'Nein'],
  [button('v'), 'listen-button', 'play now'],

  // --- buttons the Meldungs-card -> news module
  [button('mm260920-0007'), 'news-announce', 'read out message'],
  [button('xm260920-0007'), 'news-discard', 'discard message'],
  [button('mM260920-0007'), '', 'Identifier with uppercase letter: no button from us'],

  // --- everything else runs as before (analysis and language model)
  [message('play Gasoline'), '', 'Musikwunsch'],
  [message('I want something from Scooter'), '', 'Musikwunsch'],
  [message('what is currently running'), '', 'question about program'],
  [message('next track'), '', 'Control'],
  [message('danke'), '', 'Smalltalk'],
  [message('do something with the station'), '', 'unknown'],
  [message(''), '', 'empty'],
  [button('w2'), '', 'old selection list (w2) remains at agent'],
  [button('anything'), '', 'foreign button'],
];

let good = 0;
for (const [update, erwartet, hint] of cases) {
  const result = verlauf(update);
  const type = result.type;
  const felder = result.felder;
  const ok = type === erwartet;
  if (ok) good += 1;
  const was = update.callback_query ? 'button ' + update.callback_query.data
    : '"' + update.message.text + '"';
  const identifier = update.callback_query && result.identifier ? ' (identifier' + result.identifier + ')' : '';
  console.log((ok ? 'ok   ' : 'ABW. ') + was.padEnd(52) + ' -> ' + (type || '(continue as before)')
    + identifier + (ok ? '   ' + hint : ' expected:' + (erwartet || '(continue as before)')));
  if (!ok) {
    console.log(' fields from input:' + JSON.stringify(felder).slice(0, 200));
  }
}
console.log('\n' + good + ' of ' + cases.length + ' as expected');
process.exit(good === cases.length ? 0 : 1);
