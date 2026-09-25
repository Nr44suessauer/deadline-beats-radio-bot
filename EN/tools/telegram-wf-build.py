#!/usr/bin/env python3
"""Builds the n8n workflow 'Radio - Telegram request bot'.

Credentials come from the environment (AZ_KEY, TG_TOKEN) and end up only in the
Workflow-file.
"""
import json
import os
import uuid

AZ = "http://192.168.178.33"
API = AZ + "/api/station/1"
API_ADMIN = AZ + "/api/admin"
TG = "https://api.telegram.org/bot" + os.environ["TG_TOKEN"]
API_KEY = os.environ["AZ_KEY"]
TG_CRED_ID = os.environ.get("TG_CRED_ID", "YOUR-TELEGRAM-CREDENTIAL-ID")
TG_CRED_NAME = os.environ.get("TG_CRED_NAME", "Telegram account 2")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

PLAYLIST_WUNSCH = 8      # requestable, the AutoDJ never plays it
PLAYLIST_SOFORT = 9      # interrupting -> immediate
AZ_KOPF = [{"name": "X-API-Key", "value": API_KEY}]
TG_KOPF = [{"name": "Content-Type", "value": "application/json"}]
# Speech recognition: whisper-stt on the ai server (RTX 3090 Ti, large-v3 model, German).
# Fallback on failure: CPU service whisper-asr in CT 103 with the OpenAI interface
# (http://192.168.178.53:8000/v1/audio/transcriptions, Modell Systran/faster-whisper-small).
WHISPER = os.environ.get("WHISPER_URL", "http://192.168.178.187:18790/transcribe")
# Play now and enqueue run via the file interface of the station. It
# writes immediately into the queue and knows no lock — unlike the
# detour via the interrupting playlist ("Queue is not empty").
MEDIEN = API + "/files/batch"
# Catalog service (context search + genre suggestions) in the radio-tts container.
KATALOG = os.environ.get("CATALOG_URL", "http://192.168.178.53:8881")
# Language model on the ai server (Ollama, RTX 3090 Ti). The bot asks it for free
# text and for voice messages, so that several requests in one sentence and
# references to the current track ("one more of those") are understood.
OLLAMA = os.environ.get("OLLAMA_URL", "http://192.168.178.187:11434")
MODELL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")


def _katalog_worte():
    """Fetch genre words and helper words from the service when building.

    This gives one source of truth: if the service learns new
    genres, the bot recognizes them by itself after the next build.
    If the service is not reachable, a short fallback list applies.
    """
    notrichtungen = ["rock", "pop", "metal", "rap", "hiphop", "electronic", "disco",
                     "punk", "grunge", "folk", "blues", "jazz", "classical", "schlager",
                     "germanrap", "partymusic", "charts", "country", "dance", "ballads",
                     "calm", "hard"]
    nothilfe = ["music", "direction", "genre", "stil", "sound", "what", "something", "just",
                "from", "the", "the", "the", "the", "for", "with", "anything"]
    try:
        import urllib.request
        with urllib.request.urlopen(KATALOG + "/genre/list", timeout=20) as answer:
            data = json.load(answer)
        return (sorted(set(data["stichwoerter"])), sorted(set(data["helpers"])))
    except Exception as error:
        print(f"Note: {KATALOG}/genre/list not reachable ({error}) — fallback list is used")
        return sorted(set(notrichtungen)), sorted(set(nothilfe))


RICHTUNG_WOERTER, RICHTUNG_HILFE = _katalog_worte()


def _katalog_kuenstler(count: int = 45):
    """Most frequent artists of the archive — as a hint for speech recognition.

    faster-whisper recognizes proper names much better when they are in the hint text
    stand. Misheard names ("new Runner" instead of "Nirvana") become rarer.
    """
    denylist = ["Nirvana", "Rammstein", "Metallica", "Queen", "Die Ärzte", "Die Toten Hosen",
                "Modern Talking", "AC/DC", "Linkin Park", "Eminem"]
    try:
        import urllib.request
        with urllib.request.urlopen(
                KATALOG + f"/catalog/artists?count={count}", timeout=25) as answer:
            names = json.load(answer).get("names") or []
        return names or denylist
    except Exception as error:
        print(f"Note: artist list not reachable ({error}) — fallback list is used")
        return denylist


KUENSTLER = _katalog_kuenstler()
SPRACH_HINWEIS = ("Music request to a radio station. It is about music: title and artist."
                  "Known artists:" + ", ".join(KUENSTLER) + ".")

nr = [0]


def nid():
    return str(uuid.uuid4())


def n(name, typ, version, pos, params, **extra):
    d = {"parameters": params, "id": nid(), "name": name, "type": typ,
         "typeVersion": version, "position": pos}
    d.update(extra)
    return d


def notiz(text, pos, breite=420, height=180, farbe=7):
    return n(f"Note {nr[0]}", "n8n-nodes-base.stickyNote", 1, pos,
             {"content": text, "height": height, "width": breite, "color": farbe})


def tg_senden(name, pos, mit_tasten=False):
    # send reply_markup only when a keyboard is present
    # (JSON.stringify drops undefined).
    body = ("={{ JSON.stringify({ chat_id: $json.chatId, text: $json.answer,"
               " parse_mode: 'HTML', disable_web_page_preview: true,"
               " reply_markup: $json.keyboard || undefined }) }}")
    return n(name, "n8n-nodes-base.httpRequest", 4.2, pos, {
        "method": "POST",
        "url": TG + "/sendMessage",
        "sendHeaders": True,
        "headerParameters": {"parameters": TG_KOPF},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": body,
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput", notes="Errors when sending (e.g. test key) do not stop the run. ->")


def az_get(name, path, pos, parameter=None):
    p = {"method": "GET", "url": path if path.startswith("http") else API + path,
         "sendHeaders": True,
         "headerParameters": {"parameters": AZ_KOPF}, "options": {"timeout": 20000}}
    if parameter:
        p["sendQuery"] = True
        p["queryParameters"] = {"parameters": parameter}
    # A send error should yield an understandable answer, not end the run.
    return n(name, "n8n-nodes-base.httpRequest", 4.2, pos, p,
             onError="continueRegularOutput")


def az_schreiben(name, method, path, pos, body, hint=""):
    return n(name, "n8n-nodes-base.httpRequest", 4.2, pos, {
        "method": method,
        "url": path if path.startswith(("http", "=")) else AZ + path,
        "sendHeaders": True,
        "headerParameters": {"parameters": AZ_KOPF},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": body,
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput", notes=hint)


def if_knoten(name, pos, left, right=None, typ="string", op="equals", bool_true=False):
    if bool_true:
        condition = {"id": nid(), "leftValue": left, "rightValue": "",
                     "operator": {"type": "boolean", "operation": "true", "singleValue": True}}
    else:
        condition = {"id": nid(), "leftValue": left, "rightValue": right,
                     "operator": {"type": typ, "operation": op}}
    return n(name, "n8n-nodes-base.if", 2.2, pos, {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
            "combinator": "and",
            "conditions": [condition],
        },
        "options": {},
    })


# ----------------------------------------------------------------- Texts (JS)

INPUT_JS = r"""
// Unify the Telegram update (message or button press).
// The test entry (webhook) packs the content under "body".
const raw = $input.first().json ?? {};
const b = (raw.body && typeof raw.body === 'object') ? raw.body : null;
const source = (b && (b.message || b.callback_query || b.edited_message)) ? b : raw;
// Via the test entry (webhook) a key must come along that is not in the
// workflow - otherwise any stranger could register as operator.
const istTest = !!(raw.body || raw.webhookUrl);
const key = String((raw.query && raw.query.key) || source.key || '');
const cq = source.callback_query || null;
const m = source.message || (cq && cq.message) || {};
const from_ = (cq && cq.from) || m.from || {};
// Recognize a voice message (or audio recording).
const voice = m.voice || m.audio || null;
return [{ json: {
  chatId: String((m.chat && m.chat.id) !== undefined ? m.chat.id : ''),
  text: (m.text || '').trim(),
  istSprache: !!voice,
  stimmeDateiId: voice ? String(voice.file_id || '') : '',
  stimmeDauer: voice ? Number(voice.duration || 0) : 0,
  stimmeTestUrl: (voice && voice.test_url) ? String(voice.test_url) : '',
  callbackData: cq ? String(cq.data || '') : '',
  callbackId: cq ? String(cq.id || '') : '',
  messageId: (cq && cq.message ? cq.message.message_id : m.message_id) || null,
  userName: [from_.first_name, from_.last_name].filter(Boolean).join(' ') || from_.username || '',
  isCallback: !!cq,
  istTest, key,
  input: new Date().toISOString(),
} }];
"""

ZUGANG_JS = r"""
// Only approved chat identifiers may control the station.
// On first start the first chat automatically becomes the operator.
const FESTE = [];                    // enter further chat_ids here (comma-separated)
const d = $getWorkflowStaticData('global');
if (!Array.isArray(d.allowed)) d.allowed = (d.allowed ? [d.allowed] : []);
const j = $json;

// Calls via the test entry need the secret key from the
// static data - otherwise the bot only answers "No access".
if (j.istTest && (!d.testSchluessel || j.key !== d.testSchluessel)) {
  return [{ json: Object.assign({}, j, { erlaubt: false, neuerBetreiber: false,
                                         betreiber: d.allowed }) }];
}

let erlaubt = false, new = false;
if (FESTE.includes(j.chatId)) {
  erlaubt = true;
} else if (d.allowed.length === 0 && j.chatId) {
  d.allowed.push(j.chatId);
  erlaubt = true;
  new = true;
} else {
  erlaubt = d.allowed.includes(j.chatId);
}
return [{ json: Object.assign({}, j, { erlaubt, neuerBetreiber: new, betreiber: d.allowed }) }];
"""

AUFTRAG_JS = r"""
// message in jobs verwandeln.
// Slash commands are split exactly here (fast path without model).
// Free text and voice messages go to the model (node "Understand"), which also
// recognizes several jobs and references to what is playing.
const j = $json;
if (j.isCallback) {
  // Button press: the button's identifier is evaluated by the node "Read selection".
  // "ersatz" must stay empty - otherwise the next node interprets an
  // empty job from it and the bot answers with the overview instead of acting.
  return [{ json: Object.assign({}, j, { command: 'selection', argument: '', argumentUrl: '',
                                         genreWort: '', modus: 'wish', nurSuche: false,
                                         tasks: null, ersatz: [],
                                         brauchtDeutung: false }) }];
}
const text = (j.text || '').trim();
const hits = text.match(/^\/([a-zA-Z_]+)(@[A-Za-z0-9_]+)?\s*([\s\S]*)$/);
const karte = {
  start: 'help', help: 'help', help: 'help',
  search: 'search', search: 'search', finde: 'search',
  wish: 'wish', wish: 'wish', play: 'now',
  now: 'now', jetzt_spielen: 'now',
  now: 'now', now: 'now', was: 'now',
  last: 'last', history: 'last', verlauf: 'last',
};
let command = 'wish';
let argument = text;
let tasks = null;
let brauchtDeutung = true;

if (hits) {
  command = karte[hits[1].toLowerCase()] || 'help';
  argument = (hits[3] || '').trim();
  if (['search', 'wish', 'now'].includes(command) && !argument) command = 'help';
  tasks = [{ command: command, argument: argument, count: 1 }];
  brauchtDeutung = false;
} else if (!text) {
  command = 'help';
  argument = '';
  tasks = [{ command: 'help', argument: '', count: 1 }];
  brauchtDeutung = false;
}

// Direction request? ("something from rock", "something calm", "some metal", "90s")
// This is the fallback path in case the model does not answer.
const DIRECTION = new Set(RICHTUNG_WOERTER);
const HILFE_WORT = new Set(RICHTUNG_HILFE);
const istRichtung = (t) => DIRECTION.has(t)
  || Array.from(DIRECTION).some((r) => r.length > 3 && (r.startsWith(t) || t.startsWith(r)));
const kleinTeile = argument.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().split(' ').filter(Boolean);
let genreWort = '';
if (command === 'wish' && kleinTeile.length) {
  const istJahr = (t) => /^(19|20)?\d0(er|ern|s)?$/.test(t);
  const nurRichtung = kleinTeile.every((t) => istRichtung(t) || HILFE_WORT.has(t) || istJahr(t));
  if (nurRichtung && kleinTeile.some((t) => istRichtung(t) || istJahr(t))) {
    genreWort = kleinTeile.filter((t) => !HILFE_WORT.has(t)).join(' ') || argument;
  }
}
const ersatz = tasks ? [] : [{
  command: genreWort ? 'genre' : 'wish',
  argument: genreWort || argument,
  direction: genreWort,
  count: 1,
}];

// /wish something calm, /wish something from rock: a slash command can also
// mean a direction. Then it goes via the direction search.
if (tasks && genreWort && tasks.length === 1 && tasks[0].command === 'wish') {
  tasks[0] = { command: 'genre', argument: genreWort, direction: genreWort, count: 1 };
}

return [{ json: Object.assign({}, j, {
  command, argument, argumentUrl: encodeURIComponent(argument), genreWort,
  modus: command === 'now' ? 'now' : 'wish',
  nurSuche: command === 'search',
  tasks, brauchtDeutung, ersatz,
}) }];
"""

# What the language model must know about the station and its commands. The lists
# come from the catalog service when building, so there is only one source.
VERSTEHEN_SYSTEM = (
    'You are the control computer of the internet radio "Deadline Beats". The operator — the only'
    'user — sends you tasks, typed or as a voice message, often with recognition errors.'
    'You convert them into a list of commands. Answer EXCLUSIVELY with JSON.\n\n'
    'Commands:\n'
    '- "now": play a title IMMEDIATELY (interrupts the current track). This is the'
    'normal case: whoever names a title or says "play", "put on", "turn on", "spin"'
    'wants to hear it now.\n'
    '- "wish": only when an order is explicitly requested ("afterwards",'
    '"subsequently", "later", "as next", "into the queue")\n'
    '- "genre": search by a genre or mood (field "direction")\n'
    '- You map unknown mood words to the nearest known genre:'
    '"lively"/"brisk"/"tempo" -> "party", "calm"/"relaxed" -> "calm", "hard" -> "metal".'
    'Enter the word from the list below into "direction", not the spoken one.\n'
    '- "search": only show the hit list\n'
    '- "now": what is playing now (also "what is playing", "which title", "what is it called")\n'
    '- "last": what played last\n'
    '- "help": the overview\n\n'
    'Fields per task: command, title, interpret, direction, count.\n'
    '- Split every request into "interpret" and "title" ("juliet by modern talking" ->'
    'title "Juliet", interpret "Modern Talking"). The bot thus searches separately'
    'when a name was misunderstood.\n'
    '- "count" is the requested number of titles: "a few"/"several"/"some" = 3,'
    '"many" = 6, number words as digits ("three" = 3). Default 1.\n'
    '- Several tasks in one sentence ("play X and afterwards Y") yield several entries:'
    'the first "now", the others "wish".\n'
    '- If something refers to the current or last-heard track ("one more of those", "the same'
    'artist", "again", "more of that", "something like just now"), set interpret/title from the'
    'context.\n'
    'Known artists in the archive:' + ", ".join(KUENSTLER) + '\n'
    'Map misheard names to these artists.\n'
    'Genres and moods:' + ", ".join(RICHTUNG_WOERTER) + '\n\n'
    'Answer format: {"tasks":[{"command":"now","title":"","interpret":"","direction":"","count":1}]}\n'
    'If you understand nothing: {"tasks":[{"command":"now","title":"<spoken text>","count":1}]}'
)

# Request to the model: system note, context and task; answer as JSON.
VERSTEHEN_KOERPER = ("={{ JSON.stringify({ model: " + json.dumps(MODELL, ensure_ascii=False)
                    + ", stream: false, format: 'json', keep_alive: '30m',"
                    + " options: { temperature: 0.1, num_ctx: 4096 }, messages: ["
                    + " { role: 'system', content: " + json.dumps(VERSTEHEN_SYSTEM, ensure_ascii=False) + " },"
                    + " { role: 'user', content: ($json.kontextText || '') + ' | task: '"
                    + " + ($(\'Job\').item.json.text || \'\') } ] }) }}")

# Tiny call every 10 minutes: keeps the model in the graphics card memory.
MODELL_WECKEN_KOERPER = ("={{ JSON.stringify({ model: " + json.dumps(MODELL, ensure_ascii=False)
                         + ", stream: false, keep_alive: '30m', options: { num_predict: 1, num_ctx: 512 },"
                         + " messages: [ { role: 'user', content: 'ping' } ] }) }}")

KONTEXT_BAUEN_JS = r"""
// What is playing now, what played last? The model needs this to resolve "one more of that"
// or "the same artist".
const felder = $('Job').item.json;
const now = (() => { try { return $('Fetch context').item.json || {}; } catch (e) { return {}; } })();
const input = $input.all().map((i) => i.json);
const verlauf = (input.length === 1 && Array.isArray(input[0])) ? input[0] : input;

const jetztSong = (now.now_playing && now.now_playing.song) || {};
const zeile = (s) => [s && s.artist, s && s.title].filter(Boolean).join(' \u2013 ');
const last = verlauf.map((e) => zeile(e && (e.song || e))).filter(Boolean).slice(0, 8);
const kontextText = 'Jetzt running: ' + (zeile(jetztSong) || 'nothing')
  + (jetztSong.genre ? ' (direction: ' + jetztSong.genre + ')' : '')
  + (last.length ? '\nZuletzt played: ' + last.join(' | ') : '');

return [{ json: Object.assign({}, felder, {
  jetztSong: { artist: jetztSong.artist || '', title: jetztSong.title || '',
               genre: jetztSong.genre || '', id: jetztSong.id || '' },
  letzteSongs: last,
  kontextText,
}) }];
"""

AUFTEILEN_JS = r"""
// Turn into jobs per individual item. Each item then runs once through
// search, rating and execution - that way several wishes in one message
// nacheinander abgearbeitet.
const felder = $('Job').item.json;
const raw = $json;

// Button press in the chat: nothing to interpret, the identifier passes on unchanged.
if (felder.isCallback) {
  return [Object.assign({}, felder, {
    command: 'selection', argument: '', genreWort: '', count: 1, origin: 'button',
    modus: 'wish', nurSuche: false,
  })];
}

const erlaubt = new Set(['now', 'wish', 'search', 'now', 'last', 'help', 'genre', 'selection']);

function ausModell(inhalt) {
  let text = String(inhalt || '').trim();
  text = text.replace(/^```(?:json)?/i, '').replace(/```$/, '').trim();
  let data = null;
 try {
    data = JSON.parse(text);
  } catch (e) {
    const m = text.match(/\{[\s\S]*\}/);           // in case there is text around it
    if (m) { try { data = JSON.parse(m[0]); } catch (e2) { data = null; } }
  }
  return (data && Array.isArray(data.tasks)) ? data.tasks : [];
}

const numbers = { one: 1, two: 2, three: 3, four: 4, five: 5,
                 six: 6, seven: 7, eight: 8, nine: 9, ten: 10, several: 3,
                 acouple: 2, couple: 2, some: 3, many: 6, loads: 8, everything: 10 };
const alsZahl = (w) => {
  const raw = String(w == null ? '' : w);
  if (/\d/.test(raw)) return Math.max(1, Math.min(10, Math.round(Number(raw.replace(/[^0-9]/g, '')) || 1)));
  return numbers[raw.toLowerCase().trim()] || 1;
};

let tasks = null;
let origin = 'command';
if (Array.isArray(raw.tasks)) {
  tasks = raw.tasks;                                  // path without the model
} else {
  origin = 'model';
  tasks = ausModell(raw.message && raw.message.content);
  if (!tasks.length) {
    origin = 'ersatz';
    tasks = felder.ersatz || [];
  }
}
if (!tasks.length) {
  tasks = [{ command: 'help', count: 1 }];
  origin = 'empty';
}

const items = [];
for (const a of tasks) {
  let command = String(a.command || 'wish').toLowerCase().trim();
  if (!erlaubt.has(command)) command = 'wish';
  const teile = [a.interpret, a.title].map((x) => String(x || '').trim()).filter(Boolean);
  let argument = String(a.argument || a.text || '').trim() || teile.join(' ');
  let direction = String(a.direction || '').trim();
  // Only a direction named? Then it is a direction search, not an empty title.
  if (command === 'wish' && !argument && direction) command = 'genre';
  if (command === 'genre' && !direction) direction = argument;
  if (command === 'genre' && !argument) argument = direction;
  if (['wish', 'search', 'now'].includes(command) && !argument) command = 'help';
  // Never search without a search term: the station then returns the whole
  // archive (first page) and the bot already played random titles by accident.
  const ohneBegriff = !String(argument || '').trim() && !String(direction || '').trim();
  if (ohneBegriff) command = 'help';
  // "play Juliet by Modern Talking" always means: now, for the operator. Whoever
  // names a title wants to hear it - not put it in a queue. Only
  // when an order is explicitly named does the title go to the
  // back. With several jobs the model decides per job.
  const said = String(felder.text || '');
  const order = /(later|anschlie\u00dfend|anschliessend|sp\u00e4ter|later|im anschluss|hinterher|warteschlange|enqueue|vormerken|als n\u00e4chstes|als naechstes|nacheinander|later still)/i
    .test(said);
  if (tasks.length === 1 && origin === 'model' && command === 'wish' && !order) {
    command = 'now';
  }
  items.push(Object.assign({}, felder, {
    command, argument, argumentUrl: encodeURIComponent(argument),
    title: String(a.title || '').trim(), interpret: String(a.interpret || '').trim(),
    genreWort: direction, count: alsZahl(a.count), origin,
    modus: command === 'now' ? 'now' : 'wish',
    nurSuche: command === 'search',
  }));
}
return items;
"""

WUNSCH_SAMMELN_JS = r"""

// Summarize all enqueued titles in one answer - several wishes in one
// A message must not create several messages.
const all = $input.all().map((i) => i.json);
const chatId = (all[0] || {}).chatId;
if (all.length <= 1) {
  const e = all[0] || {};
  return [{ json: { chatId, answer: e.answer || '🎙 Done.',
                    keyboard: e.keyboard || null } }];
}
const lines = all.map((e, i) => (i + 1) + '. ' + (e.zeileKurz || e.title || '?'));
const hints = Array.from(new Set(all.map((e) => e.hinweisKurz).filter(Boolean)));
return [{ json: {
  chatId,
  answer: '🎵 <b>' + all.length + ' Titel</b>\n' + lines.join('\n')
    + (hints.length ? '\n\n\u2139\ufe0f ' + hints.join(' \u00b7 ') : ''),
  keyboard: null,
} }];
"""


TRACKS_BILDEN_JS = r"""
// Turn "several titles wanted" into individual items. Each item runs
// then once through play plan, wish list and answer; the answers are
// am end zusammengefasst.
const FELDER = ['chatId', 'modus', 'argument', 'direction', 'richtungHinweis', 'nurSuche',
                'aktion'];
const raus = [];
for (const item of $input.all()) {
  const d = item.json || {};
  const list = Array.isArray(d.several) ? d.several : [];
  if (!list.length) {
    raus.push({ json: d });
    continue;
  }
  // The job details belong on every item: the switch decides
  // based on them (aktion), the play plan needs modus and chatId.
  const status = { answer: '', keyboard: null, several: null };
  for (const f of FELDER) if (d[f] !== undefined) status[f] = d[f];
  for (const t of list) raus.push({ json: Object.assign({}, t, status) });
}
return raus;
"""
VORSCHLAEGE = ["rock", "pop", "metal", "hiphop", "electronic", "disco", "grunge", "punk",
              "folk", "blues", "jazz", "classical", "schlager", "germanrap", "party",
              "something quiet", "what heavy", "90s", "80s"]


def auftrag_js():
    """Command logic with the word lists of the catalog service."""
    return (AUFTRAG_JS
            .replace("RICHTUNG_WOERTER", json.dumps(RICHTUNG_WOERTER, ensure_ascii=False))
            .replace("RICHTUNG_HILFE", json.dumps(RICHTUNG_HILFE, ensure_ascii=False)))


GENRE_WAEHLEN_JS = r"""
// Accept the catalog service's suggestion (it has already checked
// which titles really fit the direction).
const felder = $('Split job').item.json;
const raw = $json || {};
const hits = Array.isArray(raw) ? raw : (raw.hits || []);
// Does the service say which directions it used instead? That helps
// when the wanted direction does not occur in the archive (e.g. germanrap).
const used = (raw.used || []);
const word = String(felder.genreWort || '').toLowerCase();
const exactly = used.some((g) => g.includes(word) || word.includes(g));
let hint = (raw.hints || []).join(' · ');
if (!exactly && used.length) {
  hint = (hint ? hint + ' · ' : '') + 'similar direction: ' + used.slice(0, 3).join(', ');
}
if (!hits.length) {
  // Nothing suitable -> the normal search gets a second chance.
  return { json: Object.assign({}, felder, { found: false }) };
}
return { json: Object.assign({}, felder, {
  found: true,
  direction: felder.genreWort,
  richtungHinweis: hint,
  hits,
}) };
"""

HILFE_TEXT = """🎙 <b>Radio bot – Deadline Beats</b>

<b>Playing music – simply write</b>
Say what should play: "play Juliet from_ Modern Talking".
The title is searched in the whole archive and goes <b>immediately</b> to the station.
If nothing matches clearly, the bot shows a list to tap.

Only with "afterwards", "later" or "as next" does a title move behind the
current one instead of starting immediately.

/search <i>title</i> – only show the hit list
/play <i>title</i> – play right away (same as a free message)
/wish <i>title</i> – enqueue without interrupting

<b>Voice message</b>
Instead of typing you can also speak: "play Benzin immediately",
"what is playing now", "what was that title just now". Searched in the whole
archive and treated like a command.

<b>Status</b>
/now – what is playing now, what comes next
/last – the last titles
/help – this overview

Every title goes immediately to the station: it plays right away.
Only when you name an order ("afterwards", "later") does it wait.

<b>Without title – by genre</b>
"something from rock", "something calm", "some metal", "something from the 90s":
the bot picks something suitable itself.
Examples: %s""" % ", ".join(VORSCHLAEGE)

HILFE_JS = "return { json: { chatId: $json.chatId, answer: " + json.dumps(HILFE_TEXT) + " } };"

TRANSKRIPT_JS = r"""
// Turn a voice message into text (clean up only).
// What is meant is then interpreted by the language model - it also understands several
// jobs in one sentence. Here only remains: report errors or pass on the text.
const felder = $('Input').item.json;
const raw = $input.first().json || {};

if (raw.error) {
  return [{ json: Object.assign({}, felder, {
    text: '', gehoert: '', istSprache: true,
    answer: '\u26a0\ufe0f The voice message could not be processed.',
  }) }];
}

const ganz = String(raw.text || '').trim();
const sauber = ganz.replace(/\s+/g, ' ').trim();
if (!sauber) {
  return [{ json: Object.assign({}, felder, {
    text: '', gehoert: '', istSprache: true,
    answer: '\U0001f3a7 I did not understand anything - please speak again.',
  }) }];
}

return [{ json: Object.assign({}, felder, {
  text: sauber, gehoert: ganz, istSprache: true, sprachDauer: felder.stimmeDauer || 0,
}) }];
"""

GEHOERT_TEXT_JS = r"""
// Answer back: what was spoken? If nothing answers, the text is already the answer.
const felder = $('Input').item.json;
const j = $json;
const zeile = j.answer || ('🎧 Understood: »' + (j.gehoert || '') + '«');
return [{ json: { chatId: felder.chatId || j.chatId, answer: zeile, keyboard: null } }];
"""


KEIN_ZUGANG_JS = r"""
const j = $json;
if (j.neuerBetreiber) {
  return [{ json: Object.assign({}, j, { answer:
    '✅ This chat is registered as operator. From now on only this chat may control the station.\n' +
    'Write /help for the commands.' }) }];
}
return [{ json: Object.assign({}, j, { answer:
  '⛔ No access. This bot is restricted to the operator.' }) }];
"""

JETZT_JS = r"""
const j = $json;
if (j && j.error) {
  return { json: { chatId: $('Split job').item.json.chatId,
    answer: '⚠️ The station is not responding right now. Please try again later.' } };
}
const n = j.now_playing || {};
const song = (n.song && n.song.text) || 'unknown';
const rest = Math.max(0, Math.round((n.remaining !== undefined ? n.remaining
  : (n.duration || 0) - (n.elapsed || 0))));
const time = rest > 0
  ? `▸ ${Math.floor(rest / 60)}:${String(Math.round(rest % 60)).padStart(2, '0')} min left`
  : '▸ playing out right now';
const next = (j.playing_next && j.playing_next.song && j.playing_next.song.text) || '–';
const listeners = j.listeners ? j.listeners.current : 0;
const answer = [
  '🎵 <b>Now playing</b>',
  '▸ ' + song,
  time,
  n.is_request ? '🎁 Music request' : '',
  '',
  '⏭ <b>Up next</b>',
  '▸ ' + next,
  '',
  `👥 Listeners: ${listeners}`,
].filter((z) => z !== '').join('\n');
return { json: { chatId: $('Split job').item.json.chatId, answer } };
"""

VERLAUF_JS = r"""
// /history returns a bare list -> n8n spreads it over several items.
const all = $input.all().map((i) => i.json);
if (all.length && all[0] && all[0].error) {
  return { json: { chatId: $('Split job').item.json.chatId,
    answer: '⚠️ The station is not responding right now. Please try again later.' } };
}
const list = (all.length === 1 && Array.isArray(all[0])) ? all[0] : all;
const lines = list.slice(0, 10).map((e, i) => {
  const t = (e.song && e.song.text) || '?';
  const time = e.played_at
    ? new Date(e.played_at * 1000).toLocaleTimeString('de-DE',
        { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin' })
    : '--:--';
  const wish = e.is_request ? ' 🎁' : '';
  return `${String(i + 1).padStart(2, ' ')}. ${time}  ${t}${wish}`;
});
return { json: {
  chatId: $('Split job').item.json.chatId,
  answer: '🕘 <b>Recently played</b>\n' + (lines.join('\n') || 'no data')
    + '\n\n🎁 = music request',
} };
"""

BEWERTEN_JS = r"""
// hits bewerten, Mehrdeutigkeit erkennen, Auswahl zwischenspeichern.
const felder = $('Split job').item.json;
const alsListe = (d) => (Array.isArray(d) ? d : (d && (d.rows || d.data || d.hits)) || []);
// Result of the smart search (context search), in case it ran.
const KLUG = (() => { try { return $('Kluge Search').item.json.hits || []; } catch (e) { return []; } })();
// Result of a direction request, in case it was one.
const GENRE = (() => { try { return $('Choose genre').item.json.hits || []; } catch (e) { return []; } })();
const DIRECTION = (() => { try { return $('Choose genre').item.json.direction || ''; } catch (e) { return ''; } })();
const RICHTUNG_HINWEIS = (() => { try { return $('Choose genre').item.json.richtungHinweis || ''; } catch (e) { return ''; } })();

if (felder.trefferAnzahl === undefined) {
  // Did it run without the first search (direction request)? Then there is nothing to check here.
  let f = null;
  try { f = $('Hits 1').item.json; } catch (e) { f = null; }
  if (f && f.answer) return { json: Object.assign({}, felder, { aktion: 'nothing', answer: f.answer, keyboard: null }) };
}

let raw = [];
try { raw = alsListe($('Hits 1').item.json.ersteListe); } catch (e) { raw = []; }
// Always take the context search hits along - duplicates drop out further below.
raw = raw.concat(KLUG.filter((t) => !raw.some((x) => x.id === t.id)));
if (!raw.length && GENRE.length) raw = GENRE.slice();
// Add the hits of the second and third search, as far as they ran.
for (const name of ['Search 2', 'Search 3']) {
 try {
    const seen = new Set(raw.map((t) => t.id));
    alsListe($(name).first().json).forEach((t) => { if (!seen.has(t.id)) raw.push(t); });
  } catch (e) { /* search did not run */ }
}

const norm = (s) => String(s || '').toLowerCase()
  .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
  .replace(/[^a-z0-9]+/g, ' ').trim();

// Core of the title without version suffix: "Juliet (remastered)" and "Juliet" are
// the same song - that must not trigger a follow-up question.
const kernTitel = (t) => norm(t && t.title)
  .replace(/^\d{1,3}\s+/, ' ')                     // fuehrende Titelnummer ("01. ")
  .replace(/\s*[\(\[][^\)\]]*[\)\]]/g, ' ')
  .replace(/\b(remaster(ed)?|remix|live|edit|version|extended|single|album|radio)\b/g, ' ')
  .replace(/\s+/g, ' ').trim();

const words = norm(felder.argument).split(' ').filter(Boolean);
// Safety net: without search words there is no meaningful rating. The station
// would return its whole archive - that must never become a suggestion.
if (!words.length) {
  return { json: Object.assign({}, felder, {
    aktion: 'nothing',
    answer: '🤔 I did not understand a title or a genre. '
      + 'Say for example "play Juliet by Modern Talking" or "something from rock".',
    keyboard: null,
  }) };
}
const ganz = words.join(' ');
const dauerOk = (d) => Number(d) > 0 && Number(d) <= 900;

function punkte(t) {
  const title = norm(t.title);
  const artist = norm(t.artist);
  const heu = [title, artist, norm(t.album), norm(t.path)].join(' ');
  let p = 0;
  if (title === ganz) p += 130;
  else if (title.startsWith(ganz)) p += 95;
  else if (title.includes(ganz)) p += 75;
  if (artist === ganz) p += 110;
  else if (artist.includes(ganz)) p += 65;
  const inside = words.filter((w) => heu.includes(w));
  // Weighted coverage: longer search words count more. That way a
  // filler word like "if" does not overtake a real artist hit.
  const total = Math.max(1, words.reduce((s, w) => s + w.length, 0));
  const drinGewicht = inside.reduce((s, w) => s + w.length, 0);
  p += (drinGewicht / total) * 55;
  words.forEach((w) => {
    if (title.split(' ').includes(w)) p += 12;
    if (artist.split(' ').includes(w)) p += 8;
    // Additionally reward long search words that occur as a whole word.
    if (w.length >= 5 && (title.split(' ').includes(w) || artist.split(' ').includes(w))) p += 14;
  });
  // Check title and artist of the job separately: "Du Hast" by Rammstein
  // must not be measured against the whole sentence "Rammstein Du Hast".
  const wunschTitel = norm(felder.title);
  const wunschInterpret = norm(felder.interpret);
  if (wunschTitel) {
    if (title === wunschTitel) p += 130;
    else if (title.startsWith(wunschTitel)) p += 90;
    else if (title.includes(wunschTitel)) p += 60;
  }
  if (wunschInterpret) {
    if (artist === wunschInterpret) p += 110;
    else if (artist.includes(wunschInterpret)) p += 60;
  }
  const path = String(t.path || '').toLowerCase();
  if (/\.(mp3|m4a|aac|ogg|opus|flac)$/.test(path)) p += 6;
  if (/\.(mp4|webm|mkv)$/.test(path)) p -= 14;
  if (path.startsWith('moderation/')) p -= 60;
  if (dauerOk(t.length)) p += 6; else p -= 25;
  // Pull fragments (jingles, intro files) down.
  if (Number(t.length) > 0 && Number(t.length) < 45) p -= 35;
  // Versions (remastered, remix, live) are not the first choice.
  if (/\((?:\d{4}\s+)?(?:remaster|remix|live|version|edit|extended)/i.test(String(t.title || ''))) {
    p -= 8;
  }
  // Take over the context search's points (similarity, typo-tolerant).
  if (typeof t.punkteFuzzy === 'number') p += t.punkteFuzzy;
  return Math.round(p);
}

const bewertet = (DIRECTION && GENRE.length)
  // Direction request: keep the service's order. It says how
  // well a title fits the direction - there are no word points here anyway.
  ? GENRE.map((t) => Object.assign({}, t, { punkte: 60 }))
  : raw.map((t) => Object.assign({}, t, { punkte: punkte(t) }))
      .sort((a, b) => b.punkte - a.punkte);

// Dubletten (gleicher Titel + Interpret) zusammenfassen
// Merge versions of the same song: "Juliet", "Juliet (remastered)" and
// "Juliet (Jeo's remix)" are not three options but one. Compared
// is the title core as a word sequence - a suffix word at the end ("juliet jeo s") is
// the same recording, another word ("juliet in love") is not.
const istFassung = (a, b) => {
  if (!a.length || !b.length) return false;
  const short = a.length <= b.length ? a : b;
  const lang = a.length <= b.length ? b : a;
  for (let i = 0; i < short.length; i += 1) if (short[i] !== lang[i]) return false;
  return true;
};
const hits = [];
const kerne = [];
for (const t of bewertet) {
  const artist = norm(t.artist);
  const core = kernTitel(t).split(' ').filter(Boolean);
  if (kerne.some((k) => k.artist === artist && istFassung(k.core, core))) continue;
  kerne.push({ artist, core });
  hits.push(t);
  if (hits.length >= 5) break;
}

const d = $getWorkflowStaticData('global');
d.suchen = d.suchen || {};
Object.keys(d.suchen).forEach((k) => {
  if (!d.suchen[k] || Date.now() - (d.suchen[k].ts || 0) > 3600000) delete d.suchen[k];
});

const bester = hits[0] || null;
const zweiter = hits[1] || null;
// Clear winner? Then it plays directly. Otherwise rather ask: a wrongly
// understood title is more harmful than a short follow-up question with buttons.
const sicher = !!bester && bester.punkte >= 90
  && (!zweiter || bester.punkte - zweiter.punkte >= 20);

// Only an artist named, no title? Then "play something by them"
// is meant - then it plays, no question.
const nurInterpret = !String(felder.title || '').trim() && !!String(felder.interpret || '').trim();

let aktion = 'nothing';
if (bester) {
  // With a direction request there are no word hits to rate - the service
  // has already chosen, so play directly.
  aktion = (!!DIRECTION || ((sicher || nurInterpret) && !felder.nurSuche))
    ? 'playback' : 'selection';
}
if (bester) d.suchen[felder.chatId] = { ts: Date.now(), hits, modus: felder.modus };

const beschriftung = (t) => ((t.artist ? t.artist + ' – ' : '') + (t.title || '?'))
  .slice(0, 55) + (t.length_text ? `  (${t.length_text})` : '');

// Several titles wanted ("play three songs by Nirvana")? Then take the best
// different ones and pass each one on individually - that way each title
// is queued resp. played and the answers are summarized afterwards.
const gewuenscht = Math.max(1, Math.min(10, Number(felder.count) || 1));
if (bester && gewuenscht > 1 && !felder.nurSuche) {
  // Several titles: collect the best different ones. They are turned into
  // individual items in the next node (Build tracks) - in single mode a node
  // may return only one item.
  const selection = [];
  const schonTitel = new Set();
  for (const t of bewertet) {
    const key = norm(t.artist) + '|' + kernTitel(t);
    if (schonTitel.has(key)) continue;
    schonTitel.add(key);
    selection.push(t);
    if (selection.length >= gewuenscht) break;
  }
  return { json: Object.assign({}, bester, {
    chatId: felder.chatId, aktion: 'playback', answer: '', keyboard: null,
    argument: felder.argument, modus: felder.modus, nurSuche: false,
    direction: DIRECTION, richtungHinweis: RICHTUNG_HINWEIS, trefferListe: [],
    several: selection,
  }) };
}

let keyboard = null;
let answer = '';
if (aktion === 'nothing') {
  const kopf = felder.gehoert ? `🎧 Heard: <i>${felder.gehoert}</i>\n\n` : '';
  answer = kopf + `🔍 Nothing found for <b>${felder.argument}</b>.\n\n`
    + 'Tips:\n▸ write only the artist\n▸ shorten the title\n▸ check the spelling'
    + (felder.gehoert ? '\n▸ for voice messages: rather type unusual titles' : '');
} else if (aktion === 'selection') {
  answer = `🔍 <b>${hits.length} hits</b> for „${felder.argument}“ – please choose:`;
  keyboard = { inline_keyboard: hits.map((t, i) => ([
    { text: `${i + 1}. ${beschriftung(t)}`, callback_data: 'w:' + i },
  ])) };
}

return { json: Object.assign({}, bester || { }, {
  chatId: felder.chatId, aktion, answer, keyboard,
  argument: felder.argument, modus: felder.modus, nurSuche: felder.nurSuche,
  direction: DIRECTION, richtungHinweis: RICHTUNG_HINWEIS,
  trefferListe: hits.map((t) => beschriftung(t) + ' [' + t.punkte + ']'),
}) };
"""

ABSPIELPLAN_JS = r"""
// What should play? Only the file path and the mode (now or later).
// The station gets the command directly - no playlist, no detour
// via the station's request interface.
const t = $json;
const felder = $json;
const now = ($json.now === true) || felder.modus === 'now';
const title = ((t.artist ? t.artist + ' – ' : '') + (t.title || '')).trim();
const d = $getWorkflowStaticData('global');
// For the button "Rather play now": the last named title including path.
d.last = d.last || {};
d.last[felder.chatId] = { id: t.id, path: t.path, title: t.title, artist: t.artist,
  length_text: t.length_text, now };
return { json: Object.assign({}, t, {
  chatId: felder.chatId, now, title, path: t.path || '',
  modus: now ? 'now' : 'wish',
}) };
"""
# Remembers which title lies in the interrupting playlist — so a
# left-over entry can be removed later.
# Schedule: clears left-over entries from the interrupting playlist.
SOFORT_TEXT_JS = r"""
const plan = $('Play plan').item.json;
return { json: {
  chatId: plan.chatId,
  answer: `⚡️ <b>${plan.title}</b>\n\nPlays immediately – the current title `
    + 'is faded out.',
  zeileKurz: plan.title + ' (now)',
  hinweisKurz: '',
} };
"""

DANACH_TEXT_JS = r"""
const plan = $('Play plan').item.json;
return { json: {
  chatId: plan.chatId,
  answer: `🎵 <b>${plan.title}</b>\n\nPlays next, after the `
    + 'current title.',
  zeileKurz: plan.title + ' (later)',
  hinweisKurz: '',
} };
"""

AUSWAHL_JS = r"""
// Knopfdruck auswerten: "w:<index>" -> gespeicherter hits.
const felder = $('Split job').item.json;
const d = $getWorkflowStaticData('global');
const raw = (felder.callbackData || '').trim();

// Button "Play now anyway" (s:) -> take the last plan and switch to now.
if (raw.startsWith('s:')) {
  const last = (d.last || {})[felder.chatId];
  if (!last) {
    return { json: Object.assign({}, felder, {
      abgebrochen: true,
      answer: '⌛️ The title is no longer remembered. Please make a new request.',
      keyboard: null,
    }) };
  }
  return { json: Object.assign({}, last, { chatId: felder.chatId, now: true }) };
}

const entry = (d.suchen || {})[felder.chatId];
const idx = raw.startsWith('w:') ? parseInt(raw.slice(2), 10) : -1;
if (!entry || isNaN(idx) || !entry.hits[idx]) {
  return { json: Object.assign({}, felder, {
    abgebrochen: true,
    answer: '⌛️ The selection has expired. Please search again.',
    keyboard: null,
  }) };
}
const t = entry.hits[idx];
return { json: Object.assign({}, t, {
  chatId: felder.chatId, now: (entry.modus || 'wish') === 'now',
  modus: entry.modus || 'wish', selection: true,
}) };
"""

# --------------------------------------------------------------- Nodes

nodes = [
    # --- Input
    n("Telegram Trigger", "n8n-nodes-base.telegramTrigger", 1.2, [-1180, 0],
      {"updates": ["message", "callback_query"], "additionalFields": {}},
      webhookId=nid(), credentials={"telegramApi": {"id": TG_CRED_ID, "name": TG_CRED_NAME}}),
    n("Test-Entry", "n8n-nodes-base.webhook", 2, [-1180, 240],
      {"httpMethod": "POST", "path": "YOUR-WEBHOOK-PATH", "responseMode": "lastNode", "options": {}},
      webhookId=nid(), notes="For testing only: accepts a Telegram message as JSON."),
    n("Input", "n8n-nodes-base.code", 2, [-940, 100], {"jsCode": INPUT_JS}),
    if_knoten("Voice message?", [-740, -140], "={{ $json.istSprache }}", bool_true=True),
    n("Fetch file", "n8n-nodes-base.httpRequest", 4.2, [-540, -320], {
        "method": "GET", "url": TG + "/getFile",
        "sendQuery": True,
        "queryParameters": {"parameters": [
            {"name": "file_id", "value": "={{ $json.stimmeDateiId }}"}]},
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput",
       notes="Fetches the path of the voice message from Telegram."),
    n("Load audio", "n8n-nodes-base.httpRequest", 4.2, [-320, -320], {
        "method": "GET",
        "url": "={{ $('Input').item.json.stimmeTestUrl || ('https://api.telegram.org/file/bot'"
               " + " + json.dumps(os.environ["TG_TOKEN"]) + " + '/' + ($json.result ? $json.result.file_path : '')) }}",
        "options": {"timeout": 30000,
                    # Careful: options.response.response.* — that is how the node requires it.
                    "response": {"response": {"responseFormat": "file",
                                              "outputPropertyName": "audio"}}},
    }, onError="continueRegularOutput",
       notes="Loads the audio file (OGG/Opus). Via the test input, voice.test_url may be set."),
    n("Umwandeln", "n8n-nodes-base.httpRequest", 4.2, [-100, -320], {
        "method": "POST", "url": WHISPER,
        "sendBody": True, "contentType": "multipart-form-data",
        "bodyParameters": {"parameters": [
            {"parameterType": "formBinaryData", "name": "file", "inputDataFieldName": "audio"},
            {"parameterType": "formData", "name": "language", "value": "de"},
            # Expert hint: the model recognizes artist names in the hint text much better.
            {"parameterType": "formData", "name": "prompt", "value": SPRACH_HINWEIS},
        ]},
        "options": {"timeout": 120000},
    }, onError="continueRegularOutput",
       notes="Speech recognition (faster-whisper large-v3, German) on the ai server, RTX 3090 Ti, 192.168.178.187:18790."),
    n("Transkript", "n8n-nodes-base.code", 2, [60, -320], {"jsCode": TRANSKRIPT_JS}),
    n("Heard text", "n8n-nodes-base.code", 2, [280, -500], {"jsCode": GEHOERT_TEXT_JS}),
    n("Access", "n8n-nodes-base.code", 2, [-740, 100], {"jsCode": ZUGANG_JS}),
    if_knoten("Released?", [-540, 100], "={{ $json.erlaubt }}", bool_true=True),
    n("No access", "n8n-nodes-base.code", 2, [-320, 300], {"jsCode": KEIN_ZUGANG_JS}),
    n("Job", "n8n-nodes-base.code", 2, [-320, -100], {"jsCode": auftrag_js()}),

    # --- Interpretation by the language model (free text and voice messages)
    if_knoten("Interpretation needed?", [-100, 60], "={{ $json.brauchtDeutung }}", bool_true=True),
    az_get("Fetch context", AZ + "/api/nowplaying/1", [120, -320]),
    az_get("Short history", "/history", [340, -320],
           parameter=[{"name": "rows", "value": "8"}]),
    n("Build context", "n8n-nodes-base.code", 2, [560, -320], {"jsCode": KONTEXT_BAUEN_JS}),
    n("Understand", "n8n-nodes-base.httpRequest", 4.2, [780, -320], {
        "method": "POST",
        "url": OLLAMA + "/api/chat",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": VERSTEHEN_KOERPER,
        "options": {"timeout": 120000},
    }, onError="continueRegularOutput",
        notes="Interprets free text and voice messages: several requests, quantities and"
              "references to the current track. Model" + MODELL + " on the ai server (3090 Ti). ->"),
    n("Split job", "n8n-nodes-base.code", 2, [1000, -320], {"jsCode": AUFTEILEN_JS}),


    n("Weiche", "n8n-nodes-base.switch", 3.2, [-100, -100], {
        "rules": {"values": [
            {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                            "combinator": "and",
                            "conditions": [{"id": nid(), "leftValue": "={{ $json.command }}",
                                            "rightValue": "help",
                                            "operator": {"type": "string", "operation": "equals"}}]},
             "renameOutput": True, "outputKey": "help"},
            {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                            "combinator": "and",
                            "conditions": [{"id": nid(), "leftValue": "={{ $json.command }}",
                                            "rightValue": "now",
                                            "operator": {"type": "string", "operation": "equals"}}]},
             "renameOutput": True, "outputKey": "now"},
            {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                            "combinator": "and",
                            "conditions": [{"id": nid(), "leftValue": "={{ $json.command }}",
                                            "rightValue": "last",
                                            "operator": {"type": "string", "operation": "equals"}}]},
             "renameOutput": True, "outputKey": "last"},
            {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                            "combinator": "or",
                            "conditions": [
                                {"id": nid(), "leftValue": "={{ $json.command }}",
                                 "rightValue": "wish",
                                 "operator": {"type": "string", "operation": "equals"}},
                                {"id": nid(), "leftValue": "={{ $json.command }}",
                                 "rightValue": "now",
                                 "operator": {"type": "string", "operation": "equals"}},
                                {"id": nid(), "leftValue": "={{ $json.command }}",
                                 "rightValue": "search",
                                 "operator": {"type": "string", "operation": "equals"}}]},
             "renameOutput": True, "outputKey": "suchen"},
            {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                            "combinator": "and",
                            "conditions": [{"id": nid(), "leftValue": "={{ $json.command }}",
                                            "rightValue": "selection",
                                            "operator": {"type": "string", "operation": "equals"}}]},
             "renameOutput": True, "outputKey": "selection"},
            {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                            "combinator": "and",
                            "conditions": [{"id": nid(), "leftValue": "={{ $json.command }}",
                                            "rightValue": "genre",
                                            "operator": {"type": "string", "operation": "equals"}}]},
             "renameOutput": True, "outputKey": "genre"},
        ]},
        "options": {"fallbackOutput": "extra"},
    }),

    # --- Help / status
    n("Help", "n8n-nodes-base.code", 2, [140, -320], {"jsCode": HILFE_JS, "mode": "runOnceForEachItem"}),
    az_get("NowPlaying", AZ + "/api/nowplaying/1", [140, -140]),
    n("Now Text", "n8n-nodes-base.code", 2, [380, -140], {"jsCode": JETZT_JS.replace("$('Split job')", "$('Split job')"), "mode": "runOnceForEachItem"}),
    az_get("History", "/history", [140, 40]),
    n("History Text", "n8n-nodes-base.code", 2, [380, 40], {"jsCode": VERLAUF_JS}),

    # --- Search
    az_get("Search 1", "/files", [140, 240],
           parameter=[{"name": "rowCount", "value": "120"},
                      {"name": "searchPhrase", "value": "={{ $json.argument }}"}]),
    n("Hits 1", "n8n-nodes-base.code", 2, [380, 240], {"jsCode": r"""
// Full-text search of the station: only pass on the result. Which hits count
// is decided by the rating - nothing is discarded here anymore.
const felder = $('Split job').item.json;
const raw = $json;
if (raw && raw.error) {
  return { json: Object.assign({}, felder, {
    answer: '⚠️ The station is not responding right now. Please try again later.',
    keyboard: null,
  }) };
}
const list = Array.isArray(raw) ? raw : (raw.rows || raw.data || []);
return { json: Object.assign({}, felder, {
  ersteListe: list, trefferAnzahl: list.length,
}) };
""", "mode": "runOnceForEachItem"}),

    # --- Context search: always runs along, delivers typo-tolerant hits
    n("Smart Search", "n8n-nodes-base.httpRequest", 4.2, [620, 400], {
        "method": "GET",
        "url": KATALOG + "/search",
        "sendQuery": True,
        "queryParameters": {"parameters": [
            {"name": "q", "value": "={{ $('Split job').item.json.argument }}"},
            {"name": "count", "value": "10"},
            {"name": "min_punkte", "value": "40"},
        ]},
        "options": {"timeout": 25000},
    }, onError="continueRegularOutput",
        notes="Similarity search in the catalog service (typos, indistinctly spoken titles). Always runs along; the scoring decides. ->"),

    # --- Two lookup paths with the fields of the language model: first the
    # artist, then the title. This catches misunderstood names
    # ("Julia by Modern Talking" -> artist matches, title does not).
    # If a field is empty, the next value applies — an empty search phrase
    # would otherwise return the whole archive from the station.
    az_get("Search 2", "/files", [860, 400],
           parameter=[{"name": "rowCount", "value": "60"},
                      {"name": "searchPhrase", "value": "={{ $('Split job').item.json.interpret || $('Split job').item.json.title || $('Split job').item.json.argument }}"}]),
    az_get("Search 3", "/files", [1100, 400],
           parameter=[{"name": "rowCount", "value": "60"},
                      {"name": "searchPhrase", "value": "={{ $('Split job').item.json.title || $('Split job').item.json.interpret || $('Split job').item.json.argument }}"}]),

    n("Rate hits", "n8n-nodes-base.code", 2, [1340, 400],
      {"jsCode": BEWERTEN_JS, "mode": "runOnceForEachItem"}),

    n("Search genre", "n8n-nodes-base.httpRequest", 4.2, [140, 700], {
        "method": "GET",
        "url": KATALOG + "/genre",
        "sendQuery": True,
        "queryParameters": {"parameters": [
            {"name": "word", "value": "={{ $json.genreWort }}"},
            {"name": "count", "value": "25"},
            {"name": "mischen", "value": "true"},
        ]},
        "options": {"timeout": 30000},
    }, onError="continueRegularOutput",
        notes="Genre and mood in the catalog service; delivers ready-made suggestions. ->"),
    n("Choose genre", "n8n-nodes-base.code", 2, [380, 700], {"jsCode": GENRE_WAEHLEN_JS, "mode": "runOnceForEachItem"}),
    if_knoten("Genre found?", [600, 700], "={{ $json.found }}", bool_true=True),

    n("Build tracks", "n8n-nodes-base.code", 2, [1120, 240],
      {"jsCode": TRACKS_BILDEN_JS, "mode": "runOnceForAllItems"}),
    n("Decision", "n8n-nodes-base.switch", 3.2, [1260, 240], {
        "rules": {"values": [
            {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                            "combinator": "and",
                            "conditions": [{"id": nid(), "leftValue": "={{ $json.aktion }}",
                                            "rightValue": "playback",
                                            "operator": {"type": "string", "operation": "equals"}}]},
             "renameOutput": True, "outputKey": "playback"},
            {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                            "combinator": "and",
                            "conditions": [{"id": nid(), "leftValue": "={{ $json.aktion }}",
                                            "rightValue": "selection",
                                            "operator": {"type": "string", "operation": "equals"}}]},
             "renameOutput": True, "outputKey": "selection"},
        ]},
        "options": {"fallbackOutput": "extra"},
    }),

    # --- Selection / button press
    n("Callback", "n8n-nodes-base.httpRequest", 4.2, [140, 620], {
        "method": "POST", "url": TG + "/answerCallbackQuery",
        "sendHeaders": True, "headerParameters": {"parameters": TG_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ callback_query_id: $json.callbackId }) }}",
        "options": {"timeout": 15000},
    }, onError="continueRegularOutput"),
    n("Read selection", "n8n-nodes-base.code", 2, [400, 620], {"jsCode": AUSWAHL_JS, "mode": "runOnceForEachItem"}),
    if_knoten("Selection valid?", [620, 620], "={{ $json.abgebrochen }}", bool_true=True),

    # --- Playing
    n("Play plan", "n8n-nodes-base.code", 2, [880, 480],
      {"jsCode": ABSPIELPLAN_JS, "mode": "runOnceForEachItem"}),
    # The station receives the command directly via the file interface:
    # "immediate" enters into the interrupting queue, "queue" appends
    # at the back. Both know no lock — a new request always goes through.
    if_knoten("Now?", [1280, 480], "={{ $('Play plan').item.json.now }}", bool_true=True),
    # The station plays interrupters one after another: if requests lie in the
    # queue, the new one waits for minutes. Therefore empty first ("flush_and_skip"
    # discards the waiting entries and ends the running interrupter),
    # only then enter the new title.
    az_schreiben("Clear queue", "PUT", "/api/admin/debug/station/1/telnet", [1500, 260],
                 "={{ JSON.stringify({ command: 'interrupting_requests.flush_and_skip' }) }}",
                 "Empties the interrupting queue of the station (Liquidsoap command)."),
    az_schreiben("Sofort play", "PUT", MEDIEN, [1740, 380],
                 "={{ JSON.stringify({ do: 'immediate', files: [$('Play plan').item.json.path] }) }}",
                 "Plays the title immediately and fades out the current one."),
    az_schreiben("Danach play", "PUT", MEDIEN, [1520, 600],
                 "={{ JSON.stringify({ do: 'queue', files: [$('Play plan').item.json.path] }) }}",
                 "Appends the title behind the current one."),
    n("Immediate Text", "n8n-nodes-base.code", 2, [1780, 380], {"jsCode": SOFORT_TEXT_JS, "mode": "runOnceForEachItem"}),
    n("Later text", "n8n-nodes-base.code", 2, [1780, 600], {"jsCode": DANACH_TEXT_JS, "mode": "runOnceForEachItem"}),
    n("Collect wishes", "n8n-nodes-base.code", 2, [2040, 480],
      {"jsCode": WUNSCH_SAMMELN_JS, "mode": "runOnceForAllItems"}),

    # A tiny call every 10 minutes: keeps the language model in the memory of the
    # graphics card. The cleanup of the interrupting playlist is dropped —
    # the bot no longer uses it.
    n("Zeitplan", "n8n-nodes-base.scheduleTrigger", 1.2, [-1180, 520],
      {"rule": {"interval": [{"field": "minutes", "minutesInterval": 10}]}}, webhookId=nid()),
    n("Wake model", "n8n-nodes-base.httpRequest", 4.2, [-940, 700], {
        "method": "POST",
        "url": OLLAMA + "/api/chat",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": MODELL_WECKEN_KOERPER,
        "options": {"timeout": 60000},
    }, onError="continueRegularOutput",
        notes="Keeps the language model loaded. ->"),

    tg_senden("Send", [2600, 100]),
    tg_senden("Send with buttons", [1500, 780], mit_tasten=True),
]

verbindungen = {
    "Telegram Trigger": {"main": [[{"node": "Input", "type": "main", "index": 0}]]},
    "Zeitplan": {"main": [[{"node": "Wake model", "type": "main", "index": 0}]]},
    "Wake model": {"main": [[]]},
    "Test-Entry": {"main": [[{"node": "Input", "type": "main", "index": 0}]]},
    "Input": {"main": [[{"node": "Voice message?", "type": "main", "index": 0}]]},
    "Voice message?": {"main": [
        [{"node": "Fetch file", "type": "main", "index": 0}],
        [{"node": "Access", "type": "main", "index": 0}],
    ]},
    "Fetch file": {"main": [[{"node": "Load audio", "type": "main", "index": 0}]]},
    "Load audio": {"main": [[{"node": "Umwandeln", "type": "main", "index": 0}]]},
    "Umwandeln": {"main": [[{"node": "Transkript", "type": "main", "index": 0}]]},
    "Transkript": {"main": [[
        {"node": "Access", "type": "main", "index": 0},
        {"node": "Heard text", "type": "main", "index": 0},
    ]]},
    "Heard text": {"main": [[{"node": "Send", "type": "main", "index": 0}]]},
    "Access": {"main": [[{"node": "Released?", "type": "main", "index": 0}]]},
    "Released?": {"main": [
        [{"node": "Job", "type": "main", "index": 0}],
        [{"node": "No access", "type": "main", "index": 0}],
    ]},
    "No access": {"main": [[{"node": "Send", "type": "main", "index": 0}]]},
    "Job": {"main": [[{"node": "Interpretation needed?", "type": "main", "index": 0}]]},
    "Interpretation needed?": {"main": [
        [{"node": "Fetch context", "type": "main", "index": 0}],
        [{"node": "Split job", "type": "main", "index": 0}],
    ]},
    "Fetch context": {"main": [[{"node": "Short history", "type": "main", "index": 0}]]},
    "Short history": {"main": [[{"node": "Build context", "type": "main", "index": 0}]]},
    "Build context": {"main": [[{"node": "Understand", "type": "main", "index": 0}]]},
    "Understand": {"main": [[{"node": "Split job", "type": "main", "index": 0}]]},
    "Split job": {"main": [[{"node": "Weiche", "type": "main", "index": 0}]]},
    "Weiche": {"main": [
        [{"node": "Help", "type": "main", "index": 0}],
        [{"node": "NowPlaying", "type": "main", "index": 0}],
        [{"node": "History", "type": "main", "index": 0}],
        [{"node": "Search 1", "type": "main", "index": 0}],
        [{"node": "Callback", "type": "main", "index": 0}],
        [{"node": "Search genre", "type": "main", "index": 0}],
        [{"node": "Help", "type": "main", "index": 0}],
    ]},
    "Help": {"main": [[{"node": "Send", "type": "main", "index": 0}]]},
    "NowPlaying": {"main": [[{"node": "Now Text", "type": "main", "index": 0}]]},
    "Now Text": {"main": [[{"node": "Send", "type": "main", "index": 0}]]},
    "History": {"main": [[{"node": "History Text", "type": "main", "index": 0}]]},
    "History Text": {"main": [[{"node": "Send", "type": "main", "index": 0}]]},
    "Search 1": {"main": [[{"node": "Hits 1", "type": "main", "index": 0}]]},
    "Hits 1": {"main": [[{"node": "Smart Search", "type": "main", "index": 0}]]},
    "Smart Search": {"main": [[{"node": "Search 2", "type": "main", "index": 0}]]},
    "Search 2": {"main": [[{"node": "Search 3", "type": "main", "index": 0}]]},
    "Search 3": {"main": [[{"node": "Rate hits", "type": "main", "index": 0}]]},
    "Search genre": {"main": [[{"node": "Choose genre", "type": "main", "index": 0}]]},
    "Choose genre": {"main": [[{"node": "Genre found?", "type": "main", "index": 0}]]},
    "Genre found?": {"main": [
        [{"node": "Rate hits", "type": "main", "index": 0}],
        [{"node": "Search 1", "type": "main", "index": 0}],
    ]},
    "Rate hits": {"main": [[{"node": "Build tracks", "type": "main", "index": 0}]]},
    "Build tracks": {"main": [[{"node": "Decision", "type": "main", "index": 0}]]},
    "Decision": {"main": [
        [{"node": "Play plan", "type": "main", "index": 0}],
        [{"node": "Send with buttons", "type": "main", "index": 0}],
        [{"node": "Send", "type": "main", "index": 0}],
    ]},
    "Callback": {"main": [[{"node": "Read selection", "type": "main", "index": 0}]]},
    "Read selection": {"main": [[{"node": "Selection valid?", "type": "main", "index": 0}]]},
    "Selection valid?": {"main": [
        [{"node": "Send", "type": "main", "index": 0}],
        [{"node": "Play plan", "type": "main", "index": 0}],
    ]},
    "Play plan": {"main": [[{"node": "Now?", "type": "main", "index": 0}]]},
    "Now?": {"main": [
        [{"node": "Clear queue", "type": "main", "index": 0}],
        [{"node": "Danach play", "type": "main", "index": 0}],
    ]},
    "Clear queue": {"main": [[{"node": "Sofort play", "type": "main", "index": 0}]]},
    "Sofort play": {"main": [[{"node": "Immediate Text", "type": "main", "index": 0}]]},
    "Danach play": {"main": [[{"node": "Later text", "type": "main", "index": 0}]]},
    "Immediate Text": {"main": [[{"node": "Collect wishes", "type": "main", "index": 0}]]},
    "Later text": {"main": [[{"node": "Collect wishes", "type": "main", "index": 0}]]},
    "Collect wishes": {"main": [[{"node": "Send", "type": "main", "index": 0}]]},
}

workflow = {
    "id": "RadioTelegramBot",
    "name": "Radio - Telegram request bot",
    "nodes": nodes,
    "connections": verbindungen,
    "settings": {"executionOrder": "v1", "saveManualExecutions": True, "saveDataSuccessExecution": "all"},
    "staticData": {"global": {"allowed": [], "suchen": {}}},
    "active": False,
    "versionId": str(uuid.uuid4()),
}

with open("/tmp/radio-telegram.json", "w", encoding="utf-8") as f:
    json.dump(workflow, f, ensure_ascii=False, indent=2)
echte = [k for k in nodes if not k["type"].endswith("stickyNote")]
print("written: /tmp/radio-telegram.json")
print("Nodes:", len(echte), "| of which HTTP:", sum(1 for k in echte if k["type"].endswith("httpRequest")),
      "| Code:", sum(1 for k in echte if k["type"].endswith("code")))
print(", ".join(k["name"] for k in echte))
