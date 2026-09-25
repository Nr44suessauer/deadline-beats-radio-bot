// Checks the three nodes around result and answer (without n8n).
//   CHECK_READ_JS   - verdict: a question to the user is not a failure
//   APPEND_COLLECT_JS - an empty second attempt must not delete the output
//   ANSWER_BUILD_JS    - Auswahlliste sichtbar + buttons, kein "Not completed"
//
// Background: the voice message of 2026-09-20 ("Play me something by Michael
// Jackson and how is the weather in Ludwigsburg?") announced the weather, but
// the title list became "⚠️ (no output)" - the user could not choose.
const fs = require('fs');
const lies = (n) => fs.readFileSync('/tmp/js/' + n + '.js', 'utf8');

const PRUEFUNG_LESEN = read('CHECK_READ_JS');
const NACHTRAG = read('APPEND_COLLECT_JS');
const ANTWORT = read('ANSWER_BUILD_JS');

let good = 0;
let bad = 0;
function check(name, result, expected) {
  const ok = typeof expected === 'function' ? expected(result) : result === expected;
  if (ok) good += 1; else bad += 1;
  const zeige = (w) => { try { return String(JSON.stringify(w)).slice(0, 400); } catch (e) { return String(w); } };
  console.log((ok ? 'ok   ' : 'ABW. ') + name + (ok ? '' : '\n        is:' + zeige(result)));
}

// ---------------------------------------------------------------- Attrappen
function marker(data) { return () => data; }

function run(code, { json = {}, nodes = {}, data = {}, first } = {}) {
  const $ = (name) => ({ first: () => ({ json: nodes[name] || {} }), all: () => [] });
  const $json = json;
  const $getWorkflowStaticData = marker(data);
  const $input = { first: () => ({ json: json }), all: () => [{ json: json }] };
  const fn = new Function('$json', '$getWorkflowStaticData', '$', '$input', code);
  return fn($json, $getWorkflowStaticData, $, $input);
}

// One command with FollowUp (that is what the tool output looked like) and one
// that worked.
const LISTE = 'Multiple titles match "Michael Jackson":\n'
  + '1. Michael Jackson - Thriller  (5:57)\n'
  + '2. Michael Jackson - Love Never Felt So Good  (3:26)\n'
  + '3. Fatboy Slim - Michael Jackson  (5:48)\n\n'
  + 'Question briefly, which one is meant.';

// ------------------------------- 1) verdict: a question is not a defeat
{
  const data = { run: { commands: [
    { nr: 1, type: 'play', command: { searchtext: 'Michael Jackson' }, output: LISTE, ok: null, attempts: 1 },
    { nr: 2, type: 'research', command: { type: 'research' }, output: 'The weather for Ludwigsburg was announced on the radio.', ok: null, attempts: 1 },
  ] } };
  const out = run(PRUEFUNG_LESEN, {
    json: { chatId: '1', commands: data.run.commands },
    nodes: { Loop: { nr: 1 }, 'Get location': {}, 'Get queue': {} },
    data,
  });
  const b1 = data.run.commands[0];
  const b2 = data.run.commands[1];
  check('Question is recognized as a follow-up question', b1.question, true);
  check('Selection list remains in exact wording', b1.output, LISTE);
  check('Follow-up question is not retried', out[0].json.nothing_to_do, true);
  check('successful command stays ok', b2.ok, true);
}

// -------------------------- 2) empty second attempt deletes nothing
{
  const data = { run: { commands: [
    { nr: 1, type: 'play', command: { searchtext: 'Michael Jackson' }, output: LISTE, ok: false, attempts: 1 },
  ] } };
  run(NACHTRAG, {
    json: { output: '' },
    nodes: { 'Loop 2': { nr: 1 } },
    data,
  });
  const b = data.run.commands[0];
  check('Selection list survives the empty second attempt', b.output, LISTE);
  check('Reason states the missing follow-up', b.reason, 'Follow-up brought no answer');
}

// ------------------- 3) answer: list visible, no "Not completed"
{
  const data = { run: { commands: [
    { nr: 1, type: 'play', command: { searchtext: 'Michael Jackson' }, output: LISTE, ok: false, question: true, attempts: 1 },
    { nr: 2, type: 'research', command: { type: 'research' }, output: 'The weather for Ludwigsburg was announced on the radio.', ok: true, attempts: 1 },
  ] } };
  const out = run(ANTWORT, {
    json: {},
    nodes: { Loop: { nr: 2, done: true }, Input: { chatId: '1' } },
    data,
  })[0].json;
  check('no "no output" message anymore', out.answer, (a) => !/no output/.test(a));
  check('List is in the response', out.answer, (a) => /1\. Michael Jackson - Thriller/.test(a) && /3\. Fatboy Slim/.test(a));
  check('Weather stays as completed', out.answer, (a) => /Das weather for Ludwigsburg/.test(a));
  check('no "not completed" for a follow-up question', out.answer, (a) => !/Not completed/.test(a));
  check('Hint on button or number', out.answer, (a) => /button or reply with the number/.test(a));
  check('Buttons built from list', (out.keyboard || {}).inline_keyboard, (k) =>
    Array.isArray(k) && k.length === 3 && k[0][0].callback_data === 'w1'
      && k[0][0].text === 'Michael Jackson - Thriller' && k[2][0].callback_data === 'w3');
}

// ------------------------- 4) a real failure stays a failure
{
  const data = { run: { commands: [
    { nr: 1, type: 'play', command: { searchtext: 'Billie Jean' }, output: 'NO MATCHES: nothing found.', ok: false, attempts: 1 },
  ] } };
  const out = run(ANTWORT, {
    json: {},
    nodes: { Loop: { nr: 1, done: true }, Input: { chatId: '1' } },
    data,
  })[0].json;
  check('Failure is reported further', out.answer, (a) => /Not completed: no. 1/.test(a));
  check('without buttons', out.keyboard, null);
}

// --------------------- 5) collapsed list (that is how it arrived)
{
  const FLACH = 'There are several matching titles: 1. Thriller, 2. Love Never Felt So Good'
    + '(Fedde Le Grand Remix), 3. There Must Be More To Life Than This (with Queen),'
    + '4. Fatboy Slim - Michael Jackson Which title should I play?';
  const data = { run: { commands: [
    { nr: 1, type: 'play', command: { searchtext: 'Michael Jackson' }, output: FLACH, ok: false, question: true, attempts: 1 },
  ] } };
  const out = run(ANTWORT, {
    json: {},
    nodes: { Loop: { nr: 1, done: true }, Input: { chatId: '1' } },
    data,
  })[0].json;
  const tasten = ((out.keyboard || {}).inline_keyboard || []).map((k) => k[0].text);
  check('Buttons from collapsed list', tasten.length, 4);
  check('first button is the first title', tasten[0], 'Thriller');
  check('last button without suffix', tasten[3], 'Fatboy Slim - Michael Jackson');
}

// ------------------------- 6) inbox list gets no buttons
{
  const data = { run: { commands: [
    { nr: 1, type: 'inbox', command: { type: 'inbox' }, ok: true, attempts: 1,
      output: 'In mailbox 2 open message(s): 1. Weather Marbach? (weather, identifier m1) | 2. News test (news, identifier m2).' },
  ] } };
  const out = run(ANTWORT, {
    json: {},
    nodes: { Loop: { nr: 1, done: true }, Input: { chatId: '1' } },
    data,
  })[0].json;
  check('Mailbox list without buttons', out.keyboard, null);
  check('Mailbox text unchanged passed through', out.answer, (a) => /In mailbox 2 open/.test(a));
}

// ------------------------------- 7) shortcut stays plain
{
  const data = { run: { schlicht: true, commands: [
    { nr: 1, type: 'status', output: 'Now playing: X', ok: true, attempts: 1 },
  ] } };
  const out = run(ANTWORT, {
    json: {},
    nodes: { Loop: { nr: 1, done: true }, Input: { chatId: '1' } },
    data,
  })[0].json;
  check('Shortcut command without character before', out.answer, 'Now playing: X');
}

console.log('\n' + good + ' ok,' + bad + ' abweichend');
process.exit(bad ? 1 : 0);
