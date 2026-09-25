#!/usr/bin/env python3
"""Builds the radio bot as an AI agent with tools.

Instead of a long if-then chain, an AI agent (Ollama on the 3090 Ti) decides
which tool it needs. Each tool is its own small workflow:

  Tool - Search title      searchtext       -> list of hits with file paths
  Tool - Search direction  direction        -> suggestions for mood/genre
  Tool - Play now          path, title      -> clears the queue and plays immediately
  Tool - Play later        path, title      -> queues behind the current track
  Tool - What is running   (none)           -> what plays, what is next, listeners

Credentials come from the environment (AZ_KEY, TG_TOKEN). Output:
  /tmp/radio-werkzeuge.json  (list of the tool workflows)
  /tmp/radio-agent.json      (the bot)
"""
import json
import os
import uuid

AZ = "http://192.168.178.33"
API = AZ + "/api/station/1"
API_ADMIN = AZ + "/api/admin"
KATALOG = os.environ.get("CATALOG_URL", "http://192.168.178.53:8881")
OLLAMA = os.environ.get("OLLAMA_URL", "http://192.168.178.187:11434")
MODELL = os.environ.get("OLLAMA_MODEL", "qwen3.6:27b")
WHISPER = os.environ.get("WHISPER_URL", "http://192.168.178.187:18790/transcribe")
TG = "https://api.telegram.org/bot" + os.environ["TG_TOKEN"]
AZ_KEY = os.environ["AZ_KEY"]
TG_TOKEN = os.environ["TG_TOKEN"]
# In this n8n version, the "Ollama Chat Model" node does not pass tool calls
# through (the model answers with empty text, the agent aborts). Ollama speaks
# the same interface as OpenAI under /v1 - hence the OpenAI node.
OLLAMA_OAI_URL = os.environ.get("OLLAMA_OAI_URL", OLLAMA + "/v1")
OAI_CRED = os.environ.get("OLLAMA_OAI_CRED_ID", "YOUR-OLLAMA-CREDENTIAL-ID")
OAI_CRED_NAME = os.environ.get("OLLAMA_OAI_CRED_NAME", "Ollama (OpenAI interface)")
OLLAMA_CRED = os.environ.get("OLLAMA_CRED_ID", "radioOllama01")
OLLAMA_CRED_NAME = os.environ.get("OLLAMA_CRED_NAME", "Ollama (Radio)")
TG_CRED_ID = os.environ.get("TG_CRED_ID", "YOUR-TELEGRAM-CREDENTIAL-ID")
TG_CRED_NAME = os.environ.get("TG_CRED_NAME", "Telegram account 2")

AZ_KOPF = [{"name": "X-API-Key", "value": AZ_KEY}]
JSON_KOPF = [{"name": "Content-Type", "value": "application/json"}]
# Ollama speaks the OpenAI interface under /v1; the key can be anything.
OLLAMA_KOPF = [{"name": "Content-Type", "value": "application/json"},
               {"name": "Authorization", "value": "Bearer " + os.environ.get("OLLAMA_KEY", "ollama")}]


def modell_koerper(system, nutzer_ausdruck, temperatur, tokens):
    """Request body for a direct model call (POST /v1/chat/completions).

    For the tool-less stages (analysis, check) the agent node is deliberately
    NOT used: n8n attaches its own instructions there, which made the model classify
    simple jobs as "no job" (reproducible on 2026-09-20: the same
    request asked directly produced the right plan, inside the agent an empty
    result). A plain call is also faster and cheaper.
    """
    return ("={{ JSON.stringify({ model: " + json.dumps(MODELL)
            + ", messages: [{ role: 'system', content: " + json.dumps(system)
            + " }, { role: 'user', content: " + nutzer_ausdruck + " }]"
            + ", temperature: " + repr(temperatur).rstrip("0").rstrip(".")
            + ", max_tokens: " + str(tokens) + " }) }}")


ANTWORT_AUSLESEN_JS = r"""
// Put the answer of a direct model call into the "output" field - the following
// nodes all read "output" (as before with the agent).
const j = $json || {};
const wahl = (j.choices && j.choices[0]) || {};
const text = (wahl.message && wahl.message.content) || j.output || j.text || '';
return [{ json: Object.assign({}, j, { output: String(text || '') }) }];
"""

# Search text for the two search services: remove filler words, otherwise the
# station's full-text search hits every title that contains "of" or "please".
SUCHTEXT = ("={{ String($('Entry').first().json.searchtext || '')"
            ".replace(/\\b(the|a|an|of|with|without|for|by|and|or|"
            "please|just|yet|once|now|soon|quickly|then|me|more|"
            "play|put|do|what|something|a|"
            "in|at|on|to|feat|ft|of|with|by|and)\\b/gi, ' ')"
            ".replace(/\\s+/g, ' ').trim() }}")

PROJEKT = "YOUR-N8N-PROJECT-ID"
ORDNER = "vEDODlq4jIKCUDmf"

# One single tool workflow for everything: search title, direction, status.
#
# The agent attaches three tool nodes to it (search_title, search_direction,
# whats_running); which branch runs is decided by the input. This keeps the
# overview small and lets only ONE sub-workflow be active.
#
# Searching and playing deliberately sit in the same flow: the file path must
# not travel through the language model (smaller models would invent it).
# The model only names the search term, number or direction.
W_WERKZEUG = "RadioWerkzeug"
W_WERKZEUG_NAME = "tool - Radio"

# Own tool flow for the station itself (AzuraCast): addresses
# look up, call any endpoint, fetch an overview. The agent
# attaches three tool nodes to it - this way the operator can operate the server via the
# chat without the radio tools becoming cluttered.
W_AZURA = "AzuraWerkzeug"
W_AZURA_NAME = "tool - AzuraCast"


def nid():
    return str(uuid.uuid4())


def n(name, typ, version, pos, params, **extra):
    d = {"parameters": params, "id": nid(), "name": name, "type": typ,
         "typeVersion": version, "position": pos}
    d.update(extra)
    return d


def code(name, pos, js, modus=None):
    p = {"jsCode": js}
    if modus:
        p["mode"] = modus
    return n(name, "n8n-nodes-base.code", 2, pos, p)


def notiz(name, x, y, breite, height, inhalt, farbe=4):
    """Sticky note (group frame) - sits behind the nodes in n8n.

    Fields of this n8n version: content, height, width, color (1..7).
    """
    return n(name, "n8n-nodes-base.stickyNote", 1, [x, y],
             {"content": inhalt, "height": height, "width": breite, "color": farbe})


def http(name, pos, method, url, body=None, kopf=None, hint=""):
    p = {"method": method, "url": url,
         "sendHeaders": True, "headerParameters": {"parameters": kopf or []},
         "options": {"timeout": 30000}}
    if body is not None:
        p["sendBody"] = True
        p["specifyBody"] = "json"
        p["jsonBody"] = body
    return n(name, "n8n-nodes-base.httpRequest", 4.2, pos, p,
             onError="continueRegularOutput", notes=hint)


def http_get(name, pos, url, parameter, hint=""):
    p = {"method": "GET", "url": url, "sendQuery": True,
         "queryParameters": {"parameters": parameter},
         "sendHeaders": True, "headerParameters": {"parameters": AZ_KOPF},
         "options": {"timeout": 30000}}
    return n(name, "n8n-nodes-base.httpRequest", 4.2, pos, p,
             onError="continueRegularOutput", notes=hint)


def trigger(pos, felder):
    """Trigger of a sub-workflow with named input fields."""
    return n("Entry", "n8n-nodes-base.executeWorkflowTrigger", 1.1, pos,
             {"workflowInputs": {"values": felder}, "inputSource": "workflowInputs"})


def when(name, pos, expression, hint=""):
    """If node: first output = true, second output = false."""
    return n(name, "n8n-nodes-base.if", 2.2, pos, {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                   "typeValidation": "loose", "version": 2},
                       "combinator": "and",
                       "conditions": [{"id": nid(), "leftValue": expression,
                                       "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true",
                                                    "singleValue": True}}]},
        "options": {}}, notes=hint)


def feld(name, description, type="string", standard=None):
    """Input field of a tool that the model fills.

    Without $fromAI the tool node has only a single text parameter: n8n
    builds the description for the model from the $fromAI calls of the
    node parameters (extractFromAIParameters). If `value` stays empty,
    nothing arrives at the sub-workflow - the field is then simply null.

    A default value makes the field optional: required fields must be
    filled by the model, otherwise the call aborts with "Received tool input did not
    match expected schema".
    """
    teile = [json.dumps(name), json.dumps(description), json.dumps(type)]
    if standard is not None:
        teile.append(json.dumps(standard))
    return "={{ $fromAI(%s) }}" % ", ".join(teile)


def werkzeug_arbeit(ident, name, nodes, verbindungen):
    return {
        "id": ident,
        "name": name,
        "nodes": nodes,
        "connections": verbindungen,
        "settings": {"executionOrder": "v1"},
        "staticData": None,
        "active": False,
        "versionId": str(uuid.uuid4()),
        "parentFolderId": ORDNER,
    }


# ------------------------------------------------------------------ tools

# --- 1) search title: first the fuzzy catalog service, then the full-text search
SUCHE_JS = r"""
// Turn the hits of both sources into a short list the language model can read.
// The search term is read at the trigger: the HTTP steps before it give their
// own answer and do not pass the input on.
const input = $('Entry').first().json || {};
const searchtext = String(input.searchtext || $json.searchtext || '').trim();
const enqueue = input.enqueue === true
  || String(input.enqueue || '').toLowerCase() === 'true';
if (!searchtext) {
  return [{ json: { result: 'ERROR: No search term. Name the artist and/or title, '
    + 'for example "Modern Talking Juliet". Never search without a term.', path: '',
    enqueue: enqueue } }];
}

const okText = (t) => 'OK: "' + t + '" ' + (enqueue
  ? 'plays next (after the current track).'
  : 'plays right now.');

// Store of the last selection list: "2" or "number 2" resolves from it. That way
// the model does not have to copy the file path - smaller models would invent it otherwise.
const d = $getWorkflowStaticData('global');
const before = Array.isArray(d.listen) ? d.listen : [];
const zahl = searchtext.match(/^[^\d]{0,12}(\d{1,2})[^\d]{0,6}$/);
if (zahl) {
  const t = before[Number(zahl[1]) - 1];
  if (!t) {
    return [{ json: { result: (before.length
      ? 'Number ' + zahl[1] + ' does not exist - there were ' + before.length + ' titles to choose from.'
      : 'No selection list is ready yet. Search for a title first.'), path: '',
      enqueue: enqueue } }];
  }
  d.listen = [];
  return [{ json: { result: okText(t.title), path: t.path, title: t.title,
    enqueue: enqueue } }];
}

function source(quelleName) {
 try {
    const j = $(quelleName).first().json;
    if (!j || j.error) return [];
    if (Array.isArray(j.hits)) return j.hits;              // catalog service
    return (j.rows || j.data || (Array.isArray(j) ? j : []));    // station
  } catch (e) { return []; }
}

const norm = (s) => String(s || '').toLowerCase()
  .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
  .replace(/[^a-z0-9]+/g, ' ').trim();

// Core of the title without version suffix: "Juliet (remastered)", "01. Juliet" and
// "Juliet" are the same song. Without this summary the model sees three
// options and asks back instead of simply playing (the operator's wish:
// a named title plays immediately).
const kernTitel = (t) => norm(t && t.title)
  .replace(/^\d{1,3}\s+/, ' ')
  .replace(/\s*[\(\[][^\)\]]*[\)\]]/g, ' ')
  .replace(/\b(remaster(ed)?|remix|live|edit|version|extended|single|album|radio)\b/g, ' ')
  .replace(/\s+/g, ' ').trim();

// A suffix word at the end is the same recording ("juliet jeo s"), another word
// is not ("juliet in love").
function istFassung(a, b) {
  if (!a.length || !b.length) return false;
  const short = a.length <= b.length ? a : b;
  const lang = a.length <= b.length ? b : a;
  for (let i = 0; i < short.length; i += 1) if (short[i] !== lang[i]) return false;
  return true;
}

const kernS = (t) => kernTitel(t).split(' ').filter(Boolean);
const hits = [];
const seen = new Set();
const kerne = [];
for (const t of source('Smart search').concat(source('Station search'))) {
  const path = t.path || '';
  if (!path) continue;
  const raw = (t.artist || '') + '|' + (t.title || '') + '|' + path;
  if (seen.has(raw)) continue;
  seen.add(raw);
  const artist = norm(t.artist);
  const core = kernS(t);
  if (kerne.some((k) => k.artist === artist && istFassung(k.core, core))) continue;
  kerne.push({ artist: artist, core: core });
  hits.push(t);
  if (hits.length >= 5) break;
}

if (!hits.length) {
  d.listen = [];
  return [{ json: { result: 'NO HITS for "' + searchtext + '". '
    + 'Try the artist alone or a direction (search_direction).', path: '',
    enqueue: enqueue } }];
}

// How many titles a selection list shows at most. Telegram allows significantly
// more buttons (callback_data is limited to 1-64 bytes, so only
// a number sits there), but eight suggestions are a good limit in chat.
const AUSWAHL_MAX = 8;

// Rating: "play Juliet by Modern Talking" should play immediately, not
// ask back. A single search term quickly returns a second
// title from the same album ("Down on My Knees") - that one is clearly weaker
// and must not trigger a follow-up question. Therefore show a list only when
// two hits are equally strong.
//
// Filler words are removed ("of", "the", "please"), otherwise no title ever matches
// completely. And: a title in which NOT all named words appear
// is never a clear hit - otherwise "Sweet Dreams by Eurythmics" would in the
// end play "Sweet Dreams My Love" by someone else (happened on 2026-09-19).
const STOPP = new Set(['from', 'of', 'the', 'and', 'or',
  'with', 'without', 'for', 'in', 'at', 'on', 'to', 'a', 'an',
  'please', 'just', 'play', 'put', 'what', 'la', 'le', 'los', 'les', 'feat', 'ft',
  'the', 'by']);
const words = norm(searchtext).split(' ').filter((w) => w && !STOPP.has(w));
const nenntAlle = (t) => {
  if (!words.length) return false;
  const teile = (norm(t.artist) + ' ' + norm(t.title) + ' ' + norm(t.path)).split(' ');
  return words.every((w) => teile.includes(w) || teile.some((x) => x.length > 3 && x.includes(w)));
};
function punkte(t) {
  const title = norm(t.title);
  const artist = norm(t.artist);
  const heu = [title, artist, norm(t.album), norm(t.path)].join(' ');
  let p = 0;
  for (const w of words) {
    if (artist.split(' ').includes(w)) p += 30;
    if (title.split(' ').includes(w)) p += 25;
    if (heu.includes(w)) p += 8;
  }
  // Everything the user named is contained in artist or title.
  if (nenntAlle(t)) p += 40;
  const duration = Number(t.length);
  if (duration > 0 && duration < 45) p -= 35;        // jingles, short intro files
  if (/^moderation\//i.test(String(t.path || ''))) p -= 60;
  return p;
}

const bewertet = hits.map((t) => ({ t: t, p: punkte(t) })).sort((a, b) => b.p - a.p);
const klar = nenntAlle(bewertet[0].t)
  && (bewertet.length === 1 || (bewertet[0].p - bewertet[1].p) >= 25);
const show = klar ? bewertet.slice(0, 1) : bewertet.slice(0, AUSWAHL_MAX);

const name = (t) => (t.artist ? t.artist + ' - ' : '') + (t.title || '?');
const lines = show.map((e, i) => (i + 1) + '. ' + name(e.t)
  + (e.t.length_text ? '  (' + e.t.length_text + ')' : ''));
const bester = show[0].t;

if (klar) {
  d.listen = [];
  // Clear hit: the tool plays itself (node "Submit now") - the
  // model only gets the finished message and cannot just announce the title.
  return [{ json: { result: okText(name(bester)), path: bester.path || '',
    title: name(bester), enqueue: enqueue } }];
}

// Remember the selection: on the next message ("2" or button press) the
// tool resolves from it. "selection" are only the titles - the bot builds the
// clickable buttons from them (callback_data "w" + number), the file path stays here.
d.listen = show.map((e) => ({ title: name(e.t), path: e.t.path }));
return [{ json: {
  result: 'Several titles match "' + searchtext + '":\n' + lines.join('\n')
    + '\n\nBriefly ask which one is meant. If the reply is a number, call search_title\n'
    + 'with exactly that number as searchtext.',
  selection: show.map((e) => name(e.t)),
  path: '', enqueue: enqueue } }];
"""

WERKZEUG_ERGEBNIS_JS = r"""
// The search run already played on a clear hit - here only the
// station's answer is checked and the text passed on. The text sits, depending on
// branch, in "Prepare hits" (title search) or "Prepare suggestions"
// (direction); the other node did not run.
let on = {};
try { on = $('Prepare hits').first().json || {}; } catch (e) { on = {}; }
if (!on.result) {
  try { on = $('Prepare suggestions').first().json || {}; } catch (e) { on = {}; }
}
let answer = null;
if (on.path) {
  const source = again.enqueue ? 'Submit later' : 'Submit now';
  try { answer = $(source).first().json; } catch (e) { answer = null; }
}
if (!on.path || !answer) return [{ json: { result: on.result || 'No hits.',
  selection: Array.isArray(again.selection) ? again.selection : [] } }];
const error = (answer.errors || []).length || answer.error;
return [{ json: { result: (error
  ? 'ERROR while submitting: ' + JSON.stringify(answer.errors || answer.error)
  : on.result),
  selection: Array.isArray(again.selection) ? again.selection : [] } }];
"""

# --- 2) search direction
DIRECTION_JS = r"""
// Input am Ausloeser read (siehe SUCHE_JS).
const input = $('Entry').first().json || {};
const word = String(input.direction || $json.direction || '').trim();
const enqueue = input.enqueue === true
  || String(input.enqueue || '').toLowerCase() === 'true';
if (!word) {
  return [{ json: { result: 'ERROR: No direction given.', path: '',
    enqueue: enqueue } }];
}
let j = {};
try { j = $('Search direction').first().json || {}; } catch (e) { j = {}; }
if (j.error || !j.hits || !j.hits.length) {
  return [{ json: { result: 'The catalog does not know the direction "' + word + '". '
    + 'Known directions: party, dance, rock, pop, metal, hiphop, electronic, disco, '
    + 'punk, grunge, folk, blues, jazz, classical, schlager, german rap, calm, hard, 90s, 80s. '
    + 'Take one of them and call search_direction again.' } }];
}
const lines = j.hits.slice(0, 4).map((t, i) => (i + 1) + '. '
  + ((t.artist ? t.artist + ' - ' : '') + (t.title || '?'))
  + (t.length_text ? '  (' + t.length_text + ')' : ''));
const first = j.hits[0];
const title = (first.artist ? first.artist + ' - ' : '') + (first.title || '?');
// A mood is a job, not a question: playing happens here in the tool,
// the model only reports the result (node "Submit now").
const wo = enqueue ? 'plays next (after the current track).' : 'plays right now.';
return [{ json: {
  result: 'OK: "' + title + '" ' + wo + ' (direction ' + (j.direction || word) + ').'
    + (lines.length > 1 ? '\nNext could be: ' + lines.slice(1, 4).join(', ') : ''),
  path: first.path || '',
  title: title,
  enqueue: enqueue } }];
"""

STATUS_JS = r"""
const j = $json || {};
if (j.error) {
  return [{ json: { result: 'The station is not responding right now.' } }];
}
const now = (j.now_playing && j.now_playing.song) || {};
const rest = Math.max(0, Math.round((now.duration || 0) - (now.elapsed || 0)));
const naechster = (j.playing_next && j.playing_next.song) || {};
return [{ json: { result: 'Now playing: ' + (now.text || 'unknown')
  + (rest ? ' (' + Math.floor(rest / 60) + ':' + String(rest % 60).padStart(2, '0') + ' min left)' : '')
  + '\nNext: ' + (naechster.text || 'unknown')
  + '\nListeners: ' + ((j.listeners && j.listeners.current) || 0) } }];
"""

werkzeuge = []

# One tool workflow for everything. The agent attaches three tool nodes
# to it; which branch runs is decided by the input (direction / question / searchtext).
werkzeuge.append(werkzeug_arbeit(W_WERKZEUG, W_WERKZEUG_NAME, [
    # All fields of the tool sit on the trigger. Per call only one of them is
    # filled - the flow then decides which branch runs.
    trigger([-900, 0], [{"name": "searchtext", "type": "string"},
                        {"name": "direction", "type": "string"},
                        {"name": "question", "type": "string"},
                        {"name": "enqueue", "type": "boolean"}]),
    when("Direction?", [-660, 0], "={{ !!String($json.direction || '').trim() }}",
         "Yes = mood/genre/decade -> fetch suggestions and play the first one."),

    # --- branch: direction
    http_get("Search direction", [-420, -220], KATALOG + "/genre", [
        {"name": "word", "value": "={{ $('Entry').first().json.direction }}"},
        {"name": "count", "value": "12"},
        {"name": "mischen", "value": "true"}],
        "Direction, mood or decade in the catalog service."),
    code("Prepare suggestions", [-180, -220], DIRECTION_JS),

    # --- branch: status only
    when("Status only?", [-420, 200], "={{ !!String($json.question || '').trim() }}",
         "Yes = question about the program, no search."),
    http("NowPlaying", [-180, 400], "GET", AZ + "/api/nowplaying/1", None, AZ_KOPF,
         "What is playing, what comes next, how many listeners."),
    code("Prepare status", [60, 400], STATUS_JS),

    # --- branch: search title (fuzzy catalog service + full-text search of the station)
    # The search text is cleaned of filler words first: the station's full-text search
    # joins the words with OR, otherwise "play Benzin by Rammstein" would return
    # every title that contains "by".
    http_get("Smart search", [-180, 120], KATALOG + "/search", [
        {"name": "q", "value": SUCHTEXT},
        {"name": "count", "value": "8"},
        {"name": "min_punkte", "value": "40"}],
        "Fuzzy search in the catalog service (typo-tolerant)."),
    http_get("Station search", [60, 120], API + "/files", [
        {"name": "searchPhrase", "value": SUCHTEXT},
        {"name": "rowCount", "value": "40"}],
        "The station’s full-text search as a second source."),
    code("Prepare hits", [300, 0], SUCHE_JS),

    # --- shared playback (both branches meet here)
    when("Hits available?", [540, 0], "={{ !!$json.path }}",
         "Yes = the title should play (clear hit or number from the selection)."),
    when("Enqueue?", [780, 0], "={{ $('Hits available?').first().json.enqueue }}",
         "Yes = only enqueue, do not interrupt."),
    http("Clear queue", [1020, -180], "PUT", API_ADMIN + "/debug/station/1/telnet",
         "={{ JSON.stringify({ command: 'interrupting_requests.flush_and_skip' }) }}",
         AZ_KOPF, "Clears the station’s interrupting queue."),
    http("Submit now", [1260, -180], "PUT", API + "/files/batch",
         "={{ JSON.stringify({ do: 'immediate', files: [$('Hits available?').first().json.path] }) }}",
         AZ_KOPF, "Submits the title into the interrupting queue right away."),
    http("Submit later", [1260, 60], "PUT", API + "/files/batch",
         "={{ JSON.stringify({ do: 'queue', files: [$('Hits available?').first().json.path] }) }}",
         AZ_KOPF, "Appends the title behind the current one."),
    code("result", [1500, 0], WERKZEUG_ERGEBNIS_JS),
], {
    "Entry": {"main": [[{"node": "Direction?", "type": "main", "index": 0}]]},
    "Direction?": {"main": [
        [{"node": "Search direction", "type": "main", "index": 0}],
        [{"node": "Status only?", "type": "main", "index": 0}]]},
    "Search direction": {"main": [[{"node": "Prepare suggestions", "type": "main", "index": 0}]]},
    "Prepare suggestions": {"main": [[{"node": "Hits available?", "type": "main", "index": 0}]]},
    "Status only?": {"main": [
        [{"node": "NowPlaying", "type": "main", "index": 0}],
        [{"node": "Smart search", "type": "main", "index": 0}]]},
    "NowPlaying": {"main": [[{"node": "Prepare status", "type": "main", "index": 0}]]},
    "Smart search": {"main": [[{"node": "Station search", "type": "main", "index": 0}]]},
    "Station search": {"main": [[{"node": "Prepare hits", "type": "main", "index": 0}]]},
    "Prepare hits": {"main": [[{"node": "Hits available?", "type": "main", "index": 0}]]},
    "Hits available?": {"main": [
        [{"node": "Enqueue?", "type": "main", "index": 0}],
        [{"node": "result", "type": "main", "index": 0}]]},
    "Enqueue?": {"main": [
        [{"node": "Submit later", "type": "main", "index": 0}],
        [{"node": "Clear queue", "type": "main", "index": 0}]]},
    "Clear queue": {"main": [[{"node": "Submit now", "type": "main", "index": 0}]]},
    "Submit now": {"main": [[{"node": "result", "type": "main", "index": 0}]]},
    "Submit later": {"main": [[{"node": "result", "type": "main", "index": 0}]]},
}))


# ------------------------------------------------------------------ station interface

# --- look up addresses: find the matching paths in the OpenAPI description
ENDPUNKTE_JS = r"""
// The model must not guess addresses: here it gets the real paths from the
// station's description (public interface, OpenAPI). The description is
// a YAML file with a very regular structure - a line scan suffices.
const raw = $json || {};
const text = String(typeof raw.data === 'string' ? raw.data : (raw.body || ''));
if (!text) {
  return [{ json: { result: 'ERROR: The station description did not arrive. '
    + 'Call the address again later.' } }];
}
const input = $('Entry').first().json || {};
const search = String(input.search || '').trim().toLowerCase();

const punkte = [];
let path = '';
let method = '';
for (const z of text.split('\n')) {
  const mp = z.match(/^    '(\/[^']*)':\s*$/);
  if (mp) { path = mp[1]; method = ''; continue; }
  const mm = z.match(/^        (get|post|put|delete|patch):\s*$/);
  if (mm && path) { method = mm[1].toUpperCase(); continue; }
  const ms = z.match(/^            summary: (.*)$/);
  if (ms && path && method) {
    punkte.push({ m: method, p: path, s: ms[1].replace(/^['"]|['"]$/g, '').trim() });
    method = '';
  }
}
if (!punkte.length) {
  return [{ json: { result: 'ERROR: The station description could not be read.' } }];
}

const hits = punkte.filter((x) => !search
  || (x.p + ' ' + x.s).toLowerCase().includes(search));
if (!hits.length) {
  return [{ json: { result: 'No address found for "' + search + '". '
    + 'Try another keyword (playlist, user, backup, report, mount, webhook, '
    + 'storage, settings, media).' } }];
}
const lines = hits.slice(0, 40).map((x, i) => (i + 1) + '. ' + x.m + ' /api' + x.p
  + '  - ' + x.s);
return [{ json: { result: 'Addresses for keyword "' + search + '" (' + hits.length
  + ' hits):\n' + lines.join('\n')
  + '\n\nAlways start paths with /api/ (replace {id} with the identifier). '
  + 'Read with azura_call and method=GET. Write only after asking the operator '
  + 'and then with confirmed=true.' } }];
"""

# --- guard: check path and method, write only with confirmation
WACHE_JS = r"""
const j = $('Entry').first().json || {};
const method = String(j.method || 'GET').trim().toUpperCase();
let path = String(j.path || '').trim();
const body = String(j.body || '').trim();
const confirmed = j.confirmed === true || String(j.confirmed).toLowerCase() === 'true';
const erlaubt = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'];

if (!erlaubt.includes(method)) {
  return [{ json: { ready: false, result: 'ERROR: "' + method + '" is not a known '
    + 'method. Use GET (read) or POST/PUT/DELETE (change).' } }];
}
if (path && !path.startsWith('/')) path = '/' + path;
if (!path.startsWith('/api/')) {
  return [{ json: { ready: false, result: 'ERROR: The path must start with /api/ '
    + '(e.g. /api/station/1/playlists). Use azura_endpoints to look things up.' } }];
}
// Writing (create, change, delete) only after asking - a model must
// not write to the server on its own. Without confirmation there is a
// dry run that the agent can present to the operator.
if (method !== 'GET' && !confirmed) {
  return [{ json: { ready: false, result: 'Dry run (nothing changed): ' + method
    + ' ' + path + (body ? ' with ' + body.slice(0, 400) : '')
    + '\nAsk the operator whether this should be executed, then call again with '
    + 'confirmed=true.' } }];
}
return [{ json: { ready: true, method: method, path: path, body: body } }];
"""

TROCKENLAUF_JS = r"""
// Nothing executed - only pass on the guard's message.
return [{ json: { result: String($json.result || 'Nothing to do.') } }];
"""

AUFRUF_ERGEBNIS_JS = r"""
// Pack the station's answer into a short message. Large answers (e.g. the
// whole music archive) are shortened - otherwise the conversation memory fills up.
const wache = $('Guard').first().json || {};
// Listen-Antworten kommen als several Elemente an - all zusammenfassen.
const all = $input.all().map((i) => i.json);
const j = all.length === 1 ? all[0] : all;
let text;
if (j && j.error) {
  text = 'ERROR: ' + JSON.stringify(j.error).slice(0, 600);
} else if (j && typeof j.data === 'string') {
  text = j.data;
} else {
  text = JSON.stringify(j);
}
const shortened = text.length > 4000;
return [{ json: { result: 'Response to ' + wache.method + ' ' + wache.path
  + (shortened ? ' (shortened)' : '') + ':\n' + text.slice(0, 4000) } }];
"""

UEBERSICHT_JS = r"""
// Short status report of the station: stations, technical, playlists.
// Note: n8n spreads list answers (stations, playlists) over several
// items - hence .all() and not .first().
const hole = (name) => { try { return $(name).all().map((i) => i.json || {}); } catch (e) { return []; } };

const lines = [];
for (const anlage of hole('Stations').slice(0, 5)) {
  lines.push('- Station: ' + (anlage.name || '?')
    + ' (' + (anlage.short_name || anlage.shortcode || '') + ')'
    + (anlage.is_enabled === false ? ' [off]' : ''));
}
const state = hole('Status')[0] || {};
lines.push('Technical: backend ' + (state.backendRunning ? 'running' : 'stopped')
  + ', output ' + (state.frontendRunning ? 'running' : 'stopped'));
const listen = hole('Playlists');
for (const list of listen.slice(0, 10)) {
  lines.push('- Playlist: ' + (list.name || '?') + ' (' + (list.type || '?') + ')'
    + (list.is_enabled === false ? ' [off]' : '') + ' | titles: ' + (list.num_songs ?? '?'));
}
if (listen.length > 10) lines.push('- ... and ' + (listen.length - 10) + ' more playlists');
return [{ json: { result: 'Overview of the station:\n' + lines.join('\n') } }];
"""

# One tool flow for the station itself. Three tool nodes of the agent
# point at it; which branch runs is decided by the input (search / path / question).
werkzeuge.append(werkzeug_arbeit(W_AZURA, W_AZURA_NAME, [
    trigger([-900, 0], [{"name": "search", "type": "string"},
                        {"name": "method", "type": "string"},
                        {"name": "path", "type": "string"},
                        {"name": "body", "type": "string"},
                        {"name": "confirmed", "type": "boolean"},
                        {"name": "question", "type": "string"}]),
    when("Look up addresses?", [-660, 0], "={{ !!String($json.search || '').trim() }}",
         "Yes = look up addresses of the station interface."),
    http("Fetch description", [-420, -200], "GET", AZ + "/api/openapi.yml", None, AZ_KOPF,
         "The station’s public interface (OpenAPI, YAML)."),
    code("Find addresses", [-180, -200], ENDPUNKTE_JS),

    when("Call?", [-420, 150], "={{ !!String($json.path || '').trim() }}",
         "Yes = call an address (read or write)."),
    code("Guard", [-180, 100], WACHE_JS),
    when("Execute?", [60, 100], "={{ $json.ready }}",
         "No = dry run (write without confirmation) -> only report."),
    when("Read only?", [300, 60], "={{ $('Guard').first().json.method === 'GET' }}",
         "Yes = GET without body, otherwise with body."),
    http("Lesen", [540, -60], "GET", "={{ '" + AZ + "' + $('Guard').first().json.path }}",
         None, AZ_KOPF, "Reads an address of the station."),
    http("Schreiben", [540, 220], "={{ $('Guard').first().json.method }}",
         "={{ '" + AZ + "' + $('Guard').first().json.path }}",
         "={{ $('Guard').first().json.body || '{}' }}", AZ_KOPF,
         "Changes something on the station (only with confirmation)."),
    code("Call result", [800, 60], AUFRUF_ERGEBNIS_JS),
    code("Dry run", [300, 320], TROCKENLAUF_JS),

    # --- overview (when neither address lookup nor call)
    http("Stations", [-180, 420], "GET", API_ADMIN + "/stations", None, AZ_KOPF, "All stations."),
    http("Status", [60, 420], "GET", API + "/status", None, AZ_KOPF, "Is the broadcast part running?"),
    http("Playlists", [300, 420], "GET", API + "/playlists", None, AZ_KOPF,
         "Playlists of the station."),
    code("Ueberblick", [540, 420], UEBERSICHT_JS),
], {
    "Entry": {"main": [[{"node": "Look up addresses?", "type": "main", "index": 0}]]},
    "Look up addresses?": {"main": [
        [{"node": "Fetch description", "type": "main", "index": 0}],
        [{"node": "Call?", "type": "main", "index": 0}]]},
    "Fetch description": {"main": [[{"node": "Find addresses", "type": "main", "index": 0}]]},
    "Call?": {"main": [
        [{"node": "Guard", "type": "main", "index": 0}],
        [{"node": "Stations", "type": "main", "index": 0}]]},
    "Guard": {"main": [[{"node": "Execute?", "type": "main", "index": 0}]]},
    "Execute?": {"main": [
        [{"node": "Read only?", "type": "main", "index": 0}],
        [{"node": "Dry run", "type": "main", "index": 0}]]},
    "Read only?": {"main": [
        [{"node": "Lesen", "type": "main", "index": 0}],
        [{"node": "Schreiben", "type": "main", "index": 0}]]},
    "Lesen": {"main": [[{"node": "Call result", "type": "main", "index": 0}]]},
    "Schreiben": {"main": [[{"node": "Call result", "type": "main", "index": 0}]]},
    "Stations": {"main": [[{"node": "Status", "type": "main", "index": 0}]]},
    "Status": {"main": [[{"node": "Playlists", "type": "main", "index": 0}]]},
    "Playlists": {"main": [[{"node": "Ueberblick", "type": "main", "index": 0}]]},
}))

# ------------------------------------------------------------------ the bot

INPUT_JS = r"""
// Telegram-Update vereinheitlichen (message, voice message, Knopfdruck).
const raw = $input.first().json ?? {};
const b = (raw.body && typeof raw.body === 'object') ? raw.body : null;
const source = (b && (b.message || b.callback_query || b.edited_message)) ? b : raw;
const istTest = !!(raw.body || raw.webhookUrl);
const key = String((raw.query && raw.query.key) || source.key || '');
const cq = source.callback_query || null;
const m = source.message || (cq && cq.message) || {};
const from_ = (cq && cq.from) || m.from || {};
const voice = m.voice || m.audio || null;
// Button press from the selection list: the identifier becomes a number - the further
// flow treats it like a typed "2" (the tool resolves the number from
// its remembered list). The text of the bot message is NOT meant here.
// Old identifiers ("w:2") are still read so old test scripts do not silently
// test the wrong thing.
const button = cq ? String(cq.data || '') : '';
const knopfNummer = (button.match(/^w:?(\d{1,2})$/) || [])[1] || '';
return [{ json: {
  chatId: String((m.chat && m.chat.id) !== undefined ? m.chat.id : ''),
  text: cq ? knopfNummer : String(m.text || '').trim(),
  istSprache: !!voice,
  stimmeDateiId: voice ? String(voice.file_id || '') : '',
  stimmeTestUrl: (voice && voice.test_url) ? String(voice.test_url) : '',
  messageId: (cq && cq.message ? cq.message.message_id : m.message_id) || null,
  userName: [from_.first_name, from_.last_name].filter(Boolean).join(' ') || from_.username || '',
  isCallback: !!cq,
  istTest, key,
  input: new Date().toISOString(),
} }];
"""

ZUGANG_JS = r"""
// Only the operator may control the station.
const d = $getWorkflowStaticData('global');
if (!Array.isArray(d.allowed)) d.allowed = (d.allowed ? [d.allowed] : []);
const j = $json;
if (j.istTest && (!d.testSchluessel || j.key !== d.testSchluessel)) {
  return [{ json: Object.assign({}, j, { erlaubt: false, neuerBetreiber: false }) }];
}
let erlaubt = false;
let new = false;
if (d.allowed.length === 0 && j.chatId) {
  d.allowed.push(j.chatId);
  erlaubt = true;
  new = true;
} else {
  erlaubt = d.allowed.includes(j.chatId);
}
return [{ json: Object.assign({}, j, { erlaubt, neuerBetreiber: new }) }];
"""

TRANSKRIPT_JS = r"""
// Voice message: only pass the text on, interpreting is left to the agent.
const felder = $('Input').item.json;
const raw = $input.first().json || {};
if (raw.error) {
  return [{ json: Object.assign({}, felder, { text: '',
    answer: '\u26a0\ufe0f The voice message could not be processed.' }) }];
}
const sauber = String(raw.text || '').replace(/\s+/g, ' ').trim();
if (!sauber) {
  return [{ json: Object.assign({}, felder, { text: '',
    answer: '\U0001f3a7 I did not understand anything - please speak again.' }) }];
}
return [{ json: Object.assign({}, felder, { text: sauber, gehoert: sauber }) }];
"""

GEHOERT_JS = r"""
const j = $json;
return [{ json: { chatId: j.chatId || $('Input').item.json.chatId,
  answer: '\U0001f3a7 Understood: \u00bb' + (j.gehoert || '') + '\u00ab' } }];
"""

KEIN_ZUGANG_JS = r"""
const j = $json;
return [{ json: Object.assign({}, j, { answer: j.neuerBetreiber
  ? '\u2705 This chat has been registered as operator. Simply write what should play.'
  : '\u26d4 No access. This bot is limited to the operator.' }) }];
"""

KEIN_TEXT_JS = r"""
// Message without text (button press, image, sticker) - nothing to control.
const j = $('Input').first().json;
return [{ json: { chatId: j.chatId,
  answer: 'I did not understand that. For example write: play Juliet by Modern Talking.',
  keyboard: null } }];
"""

ANTWORT_JS = r"""
// Prepare the answer for Telegram (HTML, no asterisks).
let text = String($json.answer || '').trim();
if (!text) text = 'I did not understand that. For example say: play Juliet by Modern Talking.';
text = text.replace(/\*\*/g, '').replace(/^#+\s*/gm, '').replace(/`/g, '');
return [{ json: { chatId: $json.chatId || $('Input').first().json.chatId, answer: text,
  keyboard: $json.keyboard || null } }];
"""

# ============================================================ stage 1: analysis

PLANEN_SYSTEM = """You split the instruction of the operator into individual commands. Answer ONLY with
JSON - no text before or after, no explanation, no code fence.

Format:
{"commands": [
  {"type": "play", "searchtext": "artist and/or title", "enqueue": false},
  {"type": "direction", "direction": "party"},
  {"type": "program", "question": "what is playing now"},
  {"type": "manage", "job": "create playlist Test", "confirmed": false}
]}

REGELN
1. One command per task, in the order they were named.
2. type=play: a concrete title or artist. enqueue=true only for "afterwards", "later",
   "subsequently", "after that" - otherwise false.
3. type=direction: mood, genre or decade. Translate to ONE of these words: party, dance,
   rock, pop, metal, hiphop, electronic, disco, punk, grunge, folk, blues, jazz, classical,
   schlager, germanrap, calm, hard, 90s, 80s. "lively"/"brisk"/"tempo" -> party,
   "relaxed"/"calm" -> calm, "hard"/"loud" -> metal. A mood request ALWAYS stays
   type=direction, even if it sounds casual ("put on something lively" -> party).
4. type=program: questions about the program ("what is playing", "what comes next", "how many listeners").
5. type=manage: everything on the station itself (playlists, stations, users, roles, backups,
   settings, reports, media, streamers). Write the order completely in your own words
   into "job".
6. confirmed=true ONLY when the operator has just explicitly agreed ("yes", "do that",
   "ok, go ahead") and this refers to a job the bot previously submitted for
   confirmation. Otherwise false. Then take the order verbatim from your last answer
   (sent along above) - do not write only "bestaetigen".
7. Map misheard names to the closest artist. Do not invent anything.
8. Several steps of one connected task ("create a playlist and fill it
   with rock") stay ONE command type=manage - do not split.
9. If the message contains no task, return {"commands": []}.

/no_think"""

BEFEHLE_LESEN_JS = r"""
// Split the analysis answer into individual commands. If that fails, the
// text is passed on as one command (then the fallback takes over) - a job
// must not fail because the model does not deliver clean JSON.
const input = $('Input').first().json;
const raw = String(($json && ($json.output || $json.text)) || '').trim();

function zerlegen(text) {
  const start = text.indexOf('{');
  const ende = text.lastIndexOf('}');
  if (start === -1 || ende <= start) return null;
 try {
    const j = JSON.parse(text.slice(start, ende + 1));
    return Array.isArray(j.commands) ? j.commands : null;
  } catch (e) { return null; }
}

const d = $getWorkflowStaticData('global');
d.planVersuche = 0;
d.run = { commands: [], error: '' };

let commands = zerlegen(raw);
if (!commands) {
  // No usable JSON: take the text itself as the command, executable without a language model
  // (type=direct). First cut away the command words, otherwise the
  // radio searches for "play" and "of" and returns random titles.
  d.lagain.error = raw ? 'analysis unreadable' : (raw === '' ? 'analysis returned nothing' : 'analysis failed');
  const rohText = String(input.text || '').trim();
  const enqueue = /(afterwards|later|then|subsequently|queued)/i.test(rohText);
  const sauber = rohText
    .replace(/\b(please|just|yet|now|soon|afterwards|subsequently|later|once)\b/gi, ' ')
    .replace(/^\s*(play|put|make|set|pack|start|take|want|i)\s+/i, '')
    .replace(/^\s*(me|just)\s+/i, '')
    .replace(/^\s*(what|something|what from|what kind)\s+/i, '')
    .replace(/\s+/g, ' ')
    .trim();
  commands = [{ type: 'direkt', searchtext: sauber || rohText, enqueue: enqueue }];
}
if (!commands.length) {
  // No job: answer without language model, without loop and without status query.
  d.run = { commands: [], error: '', withoutAi: true, schlicht: true, empty: true };
  return [{ json: { chatId: input.chatId, empty: true, count: 0 } }];
}

const output = [];
befehlSchleife:
for (let i = 0; i < commands.length; i += 1) {
  const b = commands[i] || {};
  const type = String(b.type || '').toLowerCase();
  if (!['play', 'direction', 'program', 'manage', 'direct'].includes(type)) continue;
  d.lagain.commands.push({ nr: i + 1, type: type, command: b, output: '', ok: null, reason: '', attempts: 0 });
  output.push({ json: {
    chatId: input.chatId,
    text: input.text,
    nr: i + 1,
    count: commands.length,
    type: type,
    command: b,
  } });
}
if (!output.length) {
  return [{ json: { chatId: input.chatId, count: 0, nr: 0, command: {},
    answer: 'I could not find a job in that.' } }];
}
return output;
"""

PLAN_MERKEN_JS = r"""
// The analysis delivered nothing usable (the model occasionally answers
// empty). Try again and present the original job once more.
const d = $getWorkflowStaticData('global');
d.planVersuche = (d.planVersuche || 0) + 1;
const j = $('Job').first().json;
return [{ json: Object.assign({}, j, { attempts: d.planVersuche }) }];
"""

AUFTRAG_JS = r"""
// Only prepend the bot's last answer for a short confirmation - "yes, do that"
// depends on it. For all other messages it would confuse the analysis
// (a mood request once ended up at "no job" because of it).
const d = $getWorkflowStaticData('global');
const j = $json || {};
const text = String(j.text || '').trim();
const n = text.toLowerCase();
const zustimmung = /^(yes|y|yep|ok|okay|sure|exactly|right|fits|good|go|do that|do it|go on|yes please|yes sure|yes do|agreed|confirmed|please do)\b/.test(n)
  && n.split(/\s+/).length <= 6;
const before = zustimmung ? String(d.letzteAntwort || '').trim() : '';
const job = (before ? 'Your last answer: ' + before + '\n' : '') + text;
return [{ json: Object.assign({}, j, { job: job }) }];
"""

# --------------------------------------------------- stage 0: quick command without AI

# Simple commands (song request, next title, pause, restart, status) run
# without a language model. The rules were checked against a sample collection (2026-09-20);
# what is not recognized reliably goes unchanged to the analysis.
SHORT_JS = r"""
// Pre-stage without language model. Recognized are:
//   wish        "play X", "change song to: X", "then X", "X please"
//   control     "change song/next", "continue", "pause", "louder",
//               "restart/start/stop station"
//   status      "what is playing", "status", "how many are listening", error messages
// Alles other (Verwaltung, Richtungen wie "was lively", several jobs)
// goes unchanged to the analysis.
const input = $json || {};
const d = $getWorkflowStaticData('global');
const raw = String(input.text || '');

function norm(t) {
  return String(t || '').toLowerCase()
    .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
    .replace(/[^a-z0-9: ]+/g, ' ').replace(/\s+/g, ' ').trim();
}

const CONTROL = [
  ['skip', /^(switch|change|next\w*|skip|skip ahead|go to the next|change title|change song|play the next|to the next)\b[\w\s:]{0,14}$/],
  ['skip', /^(song|title|tune|track)\s*(switch|skip|forward|next)$/],
  ['play', /^(continue|keep playing|play|play on|resume|carry on|go on|play further)\b[\w\s]{0,12}$/],
  ['pause', /^(pause|hold|stop|halt|interrupt|quick pause|music off)\b[\w\s]{0,6}$/],
  ['volume', /^(louder|quieter|loud|quiet|volume|turn up|turn down|make it louder|make it quieter)\b[\w\s]{0,10}$/],
  ['restart', /^(restart|restart station|restart radio|restart stream|start the station again|start the stream again|restart everything)\b[\w\s]{0,12}$/],
  ['start', /^(start station|start stream|start radio|start the station|start the stream|station on|radio on|run again|start)\b[\w\s]{0,10}$/],
  ['stop', /^(stop station|stop stream|stop radio|station off|radio off|stream off|stop everything|switch off the station)\b[\w\s]{0,10}$/],
];
const STATUS = /^(what is playing|what is playing now|what plays|which (song|title|artist) is playing|what is that (song|title)|status|state|station status|how is the state|is the (station|stream|radio) running|is the radio running|is the stream running|how many (are listening|listeners|people)|who is listening|how is the load|program|what comes next|which title comes)\b/;
const ERROR = /\b(error|problem|failure|offline|failed|crashed|not working|not running|does not work|does not go|acting up|stuck|no sound|no connection|down|dead)\b/;
const WISH_PREFIX = /^(play|put|make|set|pack|start|switch|change|take|hear|show|i want|i would like)\b\s*(just |me |please |then )*/;
const WISH_SUFFIX = /^(afterwards|after that|later|subsequently|next)\b\s*(just |please )*/;
const WUNSCH_SUFFIX = /^[\w\s:]{2,40}(please|just)$/;
const ADMIN = /\b(playlist|station|create|delete|remove|user|account|role|roles|backup|setting|settings|report|reports|media|mount|streamer|webhook|storage|certificate|password|api key|certificates)\b/;
const MULTIPLE = /\band\b.*\b(afterwards|then|later|subsequently|after that)\b/;
// Mood, genre, decade - mapped to a direction of the
// Katalogdienstes abgebildet (Wortliste out /genre/list).
const DIRECTION = {
  lively: 'party', snappy: 'party', upbeat: 'party', brisk: 'party', bouncy: 'party',
  tempo: 'party', dance: 'party', party: 'party', partymusic: 'party', danceable: 'party',
  dancemusic: 'party', goodmood: 'party', cheerful: 'party',
  calm: 'calm', quiet: 'calm', smooth: 'calm', relaxed: 'calm',
  easygoing: 'calm', chill: 'chill', chillout: 'chill', gentle: 'calm', loose: 'calm',
  slow: 'slow', romantic: 'romantic', love: 'love', lovesongs: 'love',
  sad: 'sad', sorrowful: 'sad', ballads: 'ballads', ballad: 'ballad',
  hard: 'hard', tough: 'hard', loud: 'hard', noisy: 'hard', heavy: 'hard',
  aggressive: 'aggressive', intensity: 'hard',
  rock: 'rock', rocky: 'rock', rocking: 'rock', rocknroll: 'rocknroll',
  pop: 'pop', poppy: 'pop', metal: 'metal', metallic: 'metal', hardrock: 'hardrock',
  disco: 'disco', eurodisco: 'eurodisco', dance: 'dance', house: 'house', trance: 'trance',
  techno: 'techno', electronic: 'electronic', electro: 'electro',
  hiphop: 'hiphop', rap: 'rap', germanrap: 'germanrap',
  punk: 'punk', grunge: 'grunge', gothic: 'gothic', dark: 'dark', indie: 'indie',
  jazz: 'jazz', blues: 'blues', soul: 'soul', funk: 'funk', reggae: 'reggae', ska: 'ska',
  classical: 'classical', classics: 'classical', schlager: 'schlager', folk: 'folk',
  country: 'country', oldies: 'oldies', german: 'german', german2: 'german',
  ndh: 'ndh', medieval: 'medieval', alternative: 'alternative', charts: 'charts',
  '80s': '80s', '90s': '90s', '70s': '70s', eighties: '80s', nineties: '90s',
};
// filler words that may stand next to a mood word ("something lively").
const FILLERS = ['what', 'something', 'anything', 'just', 'me', 'please', 'then', 'music', 'stuff',
  'things', 'junk', 'direction', 'kind', 'topic', 'from', 'for', 'with', 'a', 'an',
  'the', 'summer', 'quickly'];
const TOO_MUCH = ['out', 'in', 'away', 'down', 'off', 'from', 'everything', 'it', 'the',
  'them', 'him', 'again', 'exactly', 'right', 'now'];

// Cut away filler words and command remnants: "change song to: X" -> "X".
function clean_up(rest) {
  let r = norm(rest);
  for (let i = 0; i < 3; i += 1) {
    r = r.trim();
    r = r.replace(/^(the|a|an)\s+(song|title|tune|track|music|piece)\b/, ' ');
    r = r.replace(/^(song|title|tune|track|music|piece)\b/, ' ');
    r = r.replace(/^(on|to|with|in|at|for)\b\s*:?\s*/, ' ');
    r = r.replace(/^(me|just|please|yet|briefly|more|now|soon|quickly|then)\b\s*/, ' ');
    r = r.replace(/^(what|something|anything)\b\s*(from|for|with)?\s*/, ' ');
    r = r.replace(/^(from|for|of)\b\s*/, ' ');
    r = r.replace(/\s+(on|please|just|now|soon|to|listen|hear|play|playing|out|in)\b\s*\.?$/, ' ');
  }
  return r.replace(/\s+/g, ' ').replace(/^[ :-]+|[ :-]+$/g, '');
}

// Recognized: write the store (withoutAi/schlicht) and build the item for the loop.
function detected(type, command) {
  d.run = { commands: [{ nr: 1, type: command.type, command: command, output: '', ok: null,
    reason: '', attempts: 0 }], error: '', withoutAi: true, schlicht: true };
  return [{ json: { chatId: input.chatId, text: input.text, nr: 1, count: 1,
    type: command.type, command: command, short: type } }];
}

const n = norm(raw);
if (!n) return [{ json: Object.assign({}, $json, { short: null }) }];
const core = n.replace(/^((please|just|briefly|quickly|now|then|the|me|more)\s+)+/, '');

for (const couple of CONTROL) {
  if (couple[1].test(n) || couple[1].test(core)) {
    return detected('control', { type: 'control', control: couple[0] });
  }
}
if (STATUS.test(n)) {
  return detected('status', { type: 'direkt', question: 'what is playing now' });
}

// Selection list: typed number or tapped button (both become "2").
if (/^\d{1,2}$/.test(n)) {
  return detected('wish', { type: 'direkt', searchtext: n, enqueue: false });
}

// Pure mood ("something lively", "something calm for a change") - mapped to a
// direction without a language model. If only filler remains next to the mood word,
// it is no title request ("rock by nickelback" stays with the AI instead).
const ohneVerb = n.replace(WISH_PREFIX, ' ').replace(WISH_SUFFIX, ' ');
const stimmungWorte = ohneVerb.split(' ').filter((w) => w && FILLERS.indexOf(w) < 0
  && !/^(play|put|make|set|pack|start|switch|change|take|hear|show|i|want|would|me|please)$/.test(w));
if (stimmungWorte.length === 1 && DIRECTION[stimmungWorte[0]]) {
  return detected('direction', { type: 'direkt', direction: DIRECTION[stimmungWorte[0]] });
}

// Wish: only when no administrative job, no double job and no mood request.
if (!MULTIPLE.test(n) && !ADMIN.test(n)) {
  const hinten = WISH_SUFFIX.test(n);
  let rest = null;
  const vorn = n.match(WISH_PREFIX);
  if (vorn) rest = n.slice(vorn[0].length);
  else if (hinten) rest = n.slice(n.match(WISH_SUFFIX)[0].length);
  else if (WUNSCH_SUFFIX.test(n) && n.split(' ').length <= 5 && !ERROR.test(n)) {
    rest = n.replace(/\s*(please|just)$/, '');
  }
  if (rest !== null) {
    const s = clean_up(rest);
    const zahl = /^\d{1,2}$/.test(s);
    const words = s.split(' ');
    // Map a mood request ("something lively") to a direction without a language model.
    // Only when nothing but the mood word remains - "rock by nickelback"
    // is a title request instead.
    if (words.length && words.length <= 3) {
      const ohneFuell = words.filter((w) => FILLERS.indexOf(w) < 0);
      if (ohneFuell.length === 1 && DIRECTION[ohneFuell[0]]) {
        return detected('direction', { type: 'direkt', direction: DIRECTION[ohneFuell[0]] });
      }
    }
    if ((s.length >= 2 || zahl) && TOO_MUCH.indexOf(s) < 0 && s.indexOf(' and ') < 0) {
      return detected('wish', { type: 'direkt', searchtext: s, enqueue: hinten });
    }
  }
}

// Error report: short report without a job word -> status report instead of model.
if (ERROR.test(n) && n.split(' ').length <= 8) {
  return detected('status', { type: 'direkt', question: 'what is playing now' });
}
// Not recognized: pass the item on UNCHANGED - the job text
// for the analysis depends on it (if missing, the model got "undefined" and delivered no plan).
return [{ json: Object.assign({}, $json, { short: null }) }];
"""

STEUERUNG_ANTWORT_JS = r"""
// Answer to a quick command (basic control) - without language model.
const d = $getWorkflowStaticData('global');
const item = $('Loop').first().json || {};
const aktion = String((item.command || {}).control || '');
const r = $json || {};
const error = !!r.error || r.success === false;

let text = '';
if (aktion === 'pause') {
  text = 'The station cannot pause - every device can stop on its own. '
    + 'Say "continue" if the broadcast part should keep playing, or "next title".';
} else if (aktion === 'volume') {
  text = 'Every device controls its own volume - it cannot be changed at the station.';
} else if (aktion === 'skip') {
  text = error ? 'ERROR: The station does not accept the skip.' : 'Next title is starting.';
} else if (aktion === 'play') {
  text = error ? 'ERROR: The broadcast part does not start.' : 'The broadcast part is running.';
} else if (aktion === 'start') {
  text = error ? 'ERROR: The broadcast part could not be started.' : 'The broadcast part has been started.';
} else if (aktion === 'stop') {
  text = error ? 'ERROR: The broadcast part could not be stopped.' : 'The broadcast part is stopped.';
} else if (aktion === 'restart') {
  text = error ? 'ERROR: The broadcast part could not be restarted.'
    : 'The broadcast part has been restarted.';
} else {
  text = error ? 'ERROR: The command did not go through.' : 'Done.';
}

const nr = Number(item.nr || 1);
const entry = (d.run && d.lagain.commands || []).find((x) => x.nr === nr);
if (entry) {
  entry.output = text;
  entry.ok = !error;
  entry.attempts = (entry.attempts || 0) + 1;
}
return [{ json: { nr: nr, done: true } }];
"""

# ======================================================== stage 2: execution

AUSFUEHREN_SYSTEM = """You execute exactly ONE command of the operator on the internet radio
"Deadline Beats". The operator is the only user.

TOOLS
- search_title, search_direction, whats_running: music and program. These tools play themselves.
- azura_endpoints, azura_call, azura_overview: the station itself (administration).

REGELN
1. Execute the command — do not explain it.
2. Administrative order: first azura_endpoints (look up the address), then azura_call.
   Change (POST/PUT/DELETE) only when the command says "confirmed": true — otherwise only read
   or report the dry run and in the answer ask for permission in simple words
   ("Should I create that?"). Do not mention technical terms like "confirmed" or field names.
3. Answer in ONE short sentence with the result. No file paths, no technical talk,
   no listing of the tools.
4. If something went wrong, say in one sentence what.

/no_think"""

AUSFUEHREN_TEXT = ("={{ 'Command: ' + JSON.stringify($json.command) + '\\n/no_think' }}")

ERGEBNIS_SAMMELN_JS = r"""
// Record the result of the command in the store.
const d = $getWorkflowStaticData('global');
const nr = Number($('Loop').first().json.nr || 0);
const text = String(($json && ($json.output || $json.text)) || '').trim();
const entry = (d.run && d.lagain.commands || []).find((x) => x.nr === nr);
if (entry) {
  entry.output = text || '(no output)';
  entry.attempts = (entry.attempts || 0) + 1;
  entry.selection = Array.isArray($json.selection) ? $json.selection : (entry.selection || []);
}
return [{ json: { nr: nr, done: true } }];
"""

ERSATZ_ANTWORT_JS = r"""
// Record the fallback's result. The radio tool answers with "result",
// a language model with "output" - consider both.
const d = $getWorkflowStaticData('global');
const nr = Number($('Loop').first().json.nr || 0);
const text = String(($json && ($json.result || $json.output || $json.text)) || '').trim();
const entry = (d.run && d.lagain.commands || []).find((x) => x.nr === nr);
if (entry) {
  entry.output = text || '(no output)';
  entry.attempts = (entry.attempts || 0) + 1;
  entry.selection = Array.isArray($json.selection) ? $json.selection : (entry.selection || []);
}
return [{ json: { nr: nr, done: true } }];
"""

# ========================================================= stage 3: check

PRUEFEN_SYSTEM = """You check whether the commands were really executed. Answer ONLY with JSON,
no text before or after.

Format:
{"pruefung": [{"nr": 1, "ok": true, "reason": ""}]}

REGELN
1. ok=true when the output proves the command was executed: the title is playing, the
   title was enqueued, the information was given or the change was confirmed.
2. A dry run is NO error when the command has type=manage and "confirmed" is false
   — that is exactly how the bot should ask for permission before changing. ok=true in this case.
3. ok=false on an error message or a question back (the bot must ask the user something because
   a detail is missing). That the reported state of the station contradicts the command only counts
   as an error if the output also does not name the wanted title or artist —
   the station reports the running title with a delay.
4. type=program is ok as soon as the information was given.
4. "reason" is a short sentence why it did not work (empty when ok).
5. Exactly one entry per command, with the same "nr".

/no_think"""

LAGE_JS = r"""
// Station state as evidence for the check.
const d = $getWorkflowStaticData('global');
const now = $('Fetch status').first().json || {};
const wartend = $('Fetch queue').all().map((i) => i.json || {});
const song = (now.now_playing && now.now_playing.song) || {};
const next = ((now.playing_next || {}).song || {}).text || '';
const inWarteschlange = wartend.map((x) => (x.song && x.song.text) || '').filter(Boolean);
const list = (d.run && d.lagain.commands) || [];
// Clear error: every output is an error message or empty - then no
// language model is needed for the verdict (rule verdict in "Read check").
const klarFehler = list.length > 0 && list.every((b) => {
  const a = String(b.output || '').trim();
  return !a || a === '(no output)' || /^(ERROR|NO HITS|No selection list|Number)/i.test(a);
});
return [{ json: {
  chatId: $('Input').first().json.chatId,
  commands: list,
  withoutAi: !!(d.run && d.lagain.withoutAi),
  clearError: klarFehler,
  status: {
    running: song.text || 'unknown',
    later: next,
    warteschlange: inWarteschlange.slice(0, 5),
  },
} }];
"""

CHECK_READ_JS = r"""
// Write the check's result into the store and pass the failed commands
// on for the follow-up run.
//
// The language model judges. If it delivers nothing (empty answer, no JSON),
// a rule verdict applies - otherwise a failed command would pass as done.
const d = $getWorkflowStaticData('global');
const raw = String(($json && ($json.output || $json.text)) || '').trim();
const list = (d.run && d.lagain.commands) || [];
const status = ($('Commands and status').first().json || {}).status || {};
const STOERUNG = /error|not possible|could not|not found|no hits|dry run|which|unknown/i;

function zerlegen(text) {
  const start = text.indexOf('{');
  const ende = text.lastIndexOf('}');
  if (start === -1 || ende <= start) return null;
 try {
    const j = JSON.parse(text.slice(start, ende + 1));
    return Array.isArray(j.pruefung) ? j.pruefung : null;
  } catch (e) { return null; }
}

function words(text) {
  return String(text || '').toLowerCase().split(/[^a-z0-9]+/).filter((w) => w.length > 2);
}

function urteil(b) {
  const a = String(b.output || '').trim();
  if (!a || a === '(no output)') return { ok: false, reason: 'no output' };
  const b2 = b.command || {};
  // A dry run for a not yet confirmed administrative job is the normal case.
  const dry = b.type === 'manage' && b2.confirmed !== true && /dry run/i.test(a);
  if (dry) return { ok: true, reason: '' };
  if (STOERUNG.test(a)) return { ok: false, reason: a.slice(0, 150) };
  if (b.type === 'play') {
    const w = words(b2.searchtext);
    const genannt = w.length && w.some((x) => String(a).toLowerCase().includes(x));
    // If the output names the wanted title, the command counts as done - the
    // station reports the running title with a delay.
    if (genannt) return { ok: true, reason: '' };
    if (b2.enqueue === true) {
      const wartend = (status.warteschlange || []).join(' ').toLowerCase();
      if (w.length && !w.some((x) => wartend.includes(x))) {
        return { ok: false, reason: 'not in the queue' };
      }
    } else {
      const running = String(status.running || '').toLowerCase();
      if (w.length && !w.some((x) => running.includes(x))) {
        return { ok: false, reason: 'the station is playing "' + (status.running || '?') + '"' };
      }
    }
  }
  return { ok: true, reason: '' };
}

const pruefung = zerlegen(raw);
const gelesen = {};
for (const e of pruefung || []) gelesen[Number(e.nr)] = e;

for (const b of list) {
  const e = gelesen[Number(b.nr)];
  if (e) {
    b.ok = e.ok === true;
    b.reason = String(e.reason || '');
  } else {
    const u = urteil(b);
    b.ok = u.ok;
    b.reason = u.reason;
  }
  const empty = !String(b.output || '').trim() || String(b.output || '').trim() === '(no output)';
  if (b.ok && empty) { b.ok = false; b.reason = b.reason || 'no output'; }
  if (b.ok) b.reason = '';
}

const open = (d.run && d.lagain.withoutAi)
  // Quick command (executed without language model): verdict by rules, no second attempt.
  ? []
  : list.filter((b) => b.ok === false && (b.attempts || 0) < 2);
const output = open.map((b) => ({ json: { chatId: $json.chatId, nr: b.nr, type: b.type,
  command: b.command, reason: b.reason, attempts: b.attempts || 0 } }));
return output.length ? output : [{ json: { chatId: $json.chatId, nr: 0, nothing_to_do: true } }];
"""

APPEND_COLLECT_JS = r"""
// Record the result of the follow-up run in the store.
const d = $getWorkflowStaticData('global');
const item = $('Loop 2').first().json;
const text = String(($json && ($json.output || $json.text)) || '').trim();
const entry = (d.run && d.lagain.commands || []).find((x) => x.nr === Number(item.nr));
if (entry) {
  entry.output = text || '(no output)';
  entry.attempts = (entry.attempts || 0) + 1;
  // The second attempt is the valid state - it replaces the first output.
  entry.ok = !!text.trim() && !/error|not possible|could not|not found|no hits|which/i.test(text);
  entry.reason = entry.ok ? '' : (text || entry.reason || '');
}
return [{ json: { nr: item.nr, done: true } }];
"""

ANSWER_BUILD_JS = r"""
// Summary of all commands - success and failure separated.
const d = $getWorkflowStaticData('global');
const list = (d.run && d.lagain.commands) || [];
// schlicht = executed without language model (quick command): answer without a symbol in front.
const schlicht = !!(d.run && d.lagain.schlicht);
const lines = [];
for (const b of list) {
  const t = (b.output || '(no output)').replace(/[ \t]+/g, ' ').slice(0, 300);
  lines.push(schlicht ? t : ((b.ok === false ? '\u26a0\ufe0f ' : '\u2705 ') + t));
}
if (!lines.length) lines.push('I could not find a job in that.');
const open = list.filter((b) => b.ok === false);
if (!schlicht && open.length) {
  lines.push('Not done: ' + open.map((b) => 'no. ' + b.nr).join(', ')
    + ' - say it again, then I will try a different way.');
}
const error = (d.run && d.lagain.error) || '';
if (error) lines.push('(' + error + ')');
const total = lines.join('\n');
// Selection list as clickable buttons: callback_data "w" + number (short enough,
// Telegram allows 1-64 bytes there). The button press comes back as a number.
const mitListe = list.find((b) => Array.isArray(b.selection) && b.selection.length);
const keyboard = mitListe
  ? { inline_keyboard: mitListe.selection.map((t, i) => ([{
      text: String(t).slice(0, 60), callback_data: 'w' + (i + 1) }])) }
  : null;
// Remember for the next message: "yes, do that" depends on it.
d.letzteAntwort = total;
return [{ json: { chatId: $('Input').first().json.chatId, answer: total,
  keyboard: keyboard } }];
"""

# ======================================================================= the bot

bot = [
    n("Telegram Trigger", "n8n-nodes-base.telegramTrigger", 1.2, [-2400, 0],
      {"updates": ["message", "callback_query"], "additionalFields": {}},
      webhookId=nid(), credentials={"telegramApi": {"id": TG_CRED_ID, "name": TG_CRED_NAME}}),
    n("Test-Entry", "n8n-nodes-base.webhook", 2, [-2400, 240],
      {"httpMethod": "POST", "path": "YOUR-WEBHOOK-PATH", "responseMode": "lastNode", "options": {}},
      webhookId=nid(), notes="For checking only: accepts a Telegram message as JSON."),
    code("Input", [-2160, 100], INPUT_JS),
    n("Voice message?", "n8n-nodes-base.if", 2.2, [-1960, -140], {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                   "typeValidation": "loose", "version": 2},
                       "combinator": "and",
                       "conditions": [{"id": nid(), "leftValue": "={{ $json.istSprache }}",
                                       "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true",
                                                    "singleValue": True}}]},
        "options": {}}),
    n("Fetch file", "n8n-nodes-base.httpRequest", 4.2, [-1760, -320], {
        "method": "GET", "url": TG + "/getFile", "sendQuery": True,
        "queryParameters": {"parameters": [{"name": "file_id", "value": "={{ $json.stimmeDateiId }}"}]},
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput", notes="Fetches the path of the voice message from Telegram."),
    n("Load audio", "n8n-nodes-base.httpRequest", 4.2, [-1560, -320], {
        "method": "GET",
        "url": "={{ $('Input').item.json.stimmeTestUrl || ('https://api.telegram.org/file/bot'"
               + " + " + json.dumps(TG_TOKEN) + " + '/' + ($json.result ? $json.result.file_path : '')) }}",
        "options": {"timeout": 30000,
                    "response": {"response": {"responseFormat": "file",
                                              "outputPropertyName": "audio"}}},
    }, onError="continueRegularOutput",
       notes="Loads the audio file. Via the test input, voice.test_url may be set."),
    n("Umwandeln", "n8n-nodes-base.httpRequest", 4.2, [-1360, -320], {
        "method": "POST", "url": WHISPER,
        "sendBody": True, "contentType": "multipart-form-data",
        "bodyParameters": {"parameters": [
            {"parameterType": "formBinaryData", "name": "file", "inputDataFieldName": "audio"},
            {"parameterType": "formData", "name": "language", "value": "de"},
        ]},
        "options": {"timeout": 120000},
    }, onError="continueRegularOutput",
       notes="Speech recognition on the AI server (faster-whisper large-v3, RTX 3090 Ti)."),
    code("Transkript", [-1160, -320], TRANSKRIPT_JS),
    when("Understood?", [-960, -320], "={{ !!$json.text }}",
         "Yes = there is a recognized text. No = voice message unusable."),
    code("Heard text", [-760, -520], GEHOERT_JS),
    code("Access", [-1560, 100], ZUGANG_JS),
    n("Released?", "n8n-nodes-base.if", 2.2, [-1360, 100], {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                   "typeValidation": "loose", "version": 2},
                       "combinator": "and",
                       "conditions": [{"id": nid(), "leftValue": "={{ $json.erlaubt }}",
                                       "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true",
                                                    "singleValue": True}}]},
        "options": {}}),
    code("No access", [-1160, 320], KEIN_ZUGANG_JS),
    when("Text there?", [-960, 100], "={{ !!($json.text || '').trim() }}",
         "No = button press/image/sticker without text -> nothing to control."),
    code("No text", [-760, 320], KEIN_TEXT_JS),
    code("Job", [-680, 0], AUFTRAG_JS),

    # ---------------------------------------- stage 0: quick command (without language model)
    code("Short?", [-480, -340], SHORT_JS),
    when("Shortcut?", [-260, -340], "={{ !!$json.short }}",
         "Yes = simple command, goes without analysis straight into execution."),

    # ---------------------------------------------------- stage 1: analysis
    n("Plan", "n8n-nodes-base.httpRequest", 4.2, [-480, 0], {
        "method": "POST", "url": OLLAMA_OAI_URL + "/chat/completions",
        "sendHeaders": True, "headerParameters": {"parameters": OLLAMA_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": modell_koerper(PLANEN_SYSTEM, "$json.job + '\\n/no_think'", 0.2, 3000),
        "options": {"timeout": 120000},
    }, retryOnFail=True, maxTries=2, waitBetweenTries=3000, onError="continueRegularOutput",
       notes="Stage 1: splits the instruction into individual commands. Does nothing to the station."),
    code("Plan response", [-280, -160], ANTWORT_AUSLESEN_JS),
    when("Plan available?", [-80, -300], "={{ String($json.output || '').trim().length > 10 }}",
         "No = the model delivered nothing -> plan again."),
    code("Remember plan", [140, -460], PLAN_MERKEN_JS),
    when("Plan again?", [340, -460], "={{ Number($json.attempts || 0) < 3 }}",
         "Yes = second/third attempt, afterwards the fallback takes over."),
    code("Read commands", [-280, 0], BEFEHLE_LESEN_JS),
    when("Command available?", [-80, 160], "={{ !$json.empty }}",
         "No = no job recognized -> answer directly, without loop and without model."),

    # ------------------------------------------------ stage 2: execution
    n("Loop", "n8n-nodes-base.splitInBatches", 3, [-60, 0], {
        "batchSize": 1, "options": {},
    }, notes="Command by command."),
    n("Ausfuehren", "@n8n/n8n-nodes-langchain.agent", 2.2, [160, -140], {
        "promptType": "define",
        "text": AUSFUEHREN_TEXT,
        "options": {"systemMessage": AUSFUEHREN_SYSTEM},
        "hasOutputParser": False,
    }, retryOnFail=True, maxTries=2, waitBetweenTries=3000, onError="continueRegularOutput",
       notes="Executes exactly one command."),
    n("Language model execution", "@n8n/n8n-nodes-langchain.lmChatOpenAi", 1.2, [-40, 340], {
        "model": {"__rl": True, "value": MODELL, "mode": "id"},
        "options": {"temperature": 0.2, "maxTokens": 3000},
    }, credentials={"openAiApi": {"id": OAI_CRED, "name": OAI_CRED_NAME}}),
    n("Collect results", "n8n-nodes-base.code", 2, [380, -140], {"jsCode": ERGEBNIS_SAMMELN_JS}),

    # --------------------------------------------------- stage 3: check
    n("Get location", "n8n-nodes-base.httpRequest", 4.2, [600, 100], {
        "method": "GET", "url": AZ + "/api/nowplaying/1",
        "sendHeaders": True, "headerParameters": {"parameters": AZ_KOPF},
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput", notes="What is playing now - evidence for the check."),
    n("Get queue", "n8n-nodes-base.httpRequest", 4.2, [800, 100], {
        "method": "GET", "url": API + "/queue",
        "sendHeaders": True, "headerParameters": {"parameters": AZ_KOPF},
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput", notes="What is queued - evidence for the check."),
    code("Commands and locations", [1000, 100], LAGE_JS),
    when("Check?", [1120, 260], "={{ !$json.withoutAi && !$json.clearError }}",
         "No = quick command or clear error message: rule verdict instead of language model."),
    n("Pruefen", "n8n-nodes-base.httpRequest", 4.2, [1220, 100], {
        "method": "POST", "url": OLLAMA_OAI_URL + "/chat/completions",
        "sendHeaders": True, "headerParameters": {"parameters": OLLAMA_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": modell_koerper(PRUEFEN_SYSTEM,
                                   "‘Commands and outputs: ’ + JSON.stringify($json.commands) "
                                   "+ ’\\nState of the station: ’ + JSON.stringify($json.status) "
                                   "+ '\\n/no_think'", 0.1, 4000),
        "options": {"timeout": 120000},
    }, retryOnFail=True, maxTries=2, waitBetweenTries=3000, onError="continueRegularOutput",
       notes="Stage 3: interprets the results and marks what failed."),
    code("Check response", [1340, 260], ANTWORT_AUSLESEN_JS),
    code("Read check", [1440, 100], CHECK_READ_JS),
    when("Follow up?", [1660, 100], "={{ !$json.nothing_to_do }}",
         "Yes = at least one command failed -> second attempt."),
    n("Loop 2", "n8n-nodes-base.splitInBatches", 3, [1880, 60], {
        "batchSize": 1, "options": {},
    }, notes="Follow-up run, at most one second attempt per command."),
    n("Nacharbeiten", "@n8n/n8n-nodes-langchain.agent", 2.2, [2100, -60], {
        "promptType": "define",
        "text": ("={{ ‘Command: ’ + JSON.stringify($json.command) + ’\\nThe first attempt did not "
                 "work: ’ + $json.reason + ’\\nTry again - if possible in a "
                 "different way. Answer in one short English sentence.\\n/no_think’ }}"),
        "options": {"systemMessage": AUSFUEHREN_SYSTEM},
        "hasOutputParser": False,
    }, retryOnFail=True, maxTries=2, waitBetweenTries=3000, onError="continueRegularOutput",
       notes="Second attempt for a failed command."),
    n("Language model follow-up", "@n8n/n8n-nodes-langchain.lmChatOpenAi", 1.2, [2100, 340], {
        "model": {"__rl": True, "value": MODELL, "mode": "id"},
        "options": {"temperature": 0.3, "maxTokens": 3000},
    }, credentials={"openAiApi": {"id": OAI_CRED, "name": OAI_CRED_NAME}}),
    n("Collect addendum", "n8n-nodes-base.code", 2, [2320, -60], {"jsCode": APPEND_COLLECT_JS}),
    code("Build answer", [2560, 100], ANSWER_BUILD_JS),
    code("Answer", [2780, 100], ANTWORT_JS),
    n("Send", "n8n-nodes-base.httpRequest", 4.2, [3000, 100], {
        "method": "POST", "url": TG + "/sendMessage",
        "sendHeaders": True, "headerParameters": {"parameters": JSON_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": ("={{ JSON.stringify(Object.assign({ chat_id: $json.chatId, text: $json.answer,"
                     " parse_mode: 'HTML', disable_web_page_preview: true },"
                     " ($json.keyboard ? { reply_markup: $json.keyboard } : {}))) }}"),
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput", notes="An error while sending does not stop the run."),

    # --- tools (sub-interfaces of the agent)
    n("Search for tool titles", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, [380, 420], {
        "name": "search_title",
        "description": "Plays a title or artist. Input: searchtext (artist and/or"
                       "title) OR a number from the last selection list. Clear hit: it"
                       "plays immediately. Several different titles: the answer is a list (then"
                       "ask back). enqueue=true only enqueues without interrupting.",
        "source": "database",
        "workflowId": {"__rl": True, "value": W_WERKZEUG, "mode": "list",
                       "cachedResultName": W_WERKZEUG_NAME},
        "workflowInputs": {
            "mappingMode": "defineBelow",
            "value": {"searchtext": feld("searchtext", "Artist and/or title, e.g. Modern Talking Juliet. Or a number from the last selection list, e.g. 2"),
                      "enqueue": feld("enqueue", "true if the title should only be queued (not play immediately)", "boolean", False)},
            "matchingColumns": [],
            "schema": [{"id": "searchtext", "displayName": "searchtext", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "enqueue", "displayName": "enqueue", "required": False,
                        "defaultMatch": False, "display": True, "type": "boolean",
                        "canBeUsedToMatch": True, "removed": False}],
            "attemptToConvertTypes": False, "convertFieldsToString": False},
    }),
    n("Search for tool direction", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, [580, 420], {
        "name": "search_direction",
        "description": "Plays the first matching title for the mood, genre or decade."
                       "Input: direction (party, dance, rock, metal, calm, hard, 90s, 80s ...)."
                       "enqueue=true only queues without interrupting.",
        "source": "database",
        "workflowId": {"__rl": True, "value": W_WERKZEUG, "mode": "list",
                       "cachedResultName": W_WERKZEUG_NAME},
        "workflowInputs": {
            "mappingMode": "defineBelow",
            "value": {"direction": feld("direction", "Mood, genre or decade - one of: party, dance, rock, pop, metal, hiphop, electronic, disco, punk, grunge, folk, blues, jazz, classical, schlager, germanrap, calm, hard, 90s, 80s"),
                      "enqueue": feld("enqueue", "true if the title should only be queued (not play immediately)", "boolean", False)},
            "matchingColumns": [],
            "schema": [{"id": "direction", "displayName": "direction", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "enqueue", "displayName": "enqueue", "required": False,
                        "defaultMatch": False, "display": True, "type": "boolean",
                        "canBeUsedToMatch": True, "removed": False}],
            "attemptToConvertTypes": False, "convertFieldsToString": False},
    }),
    n("Tool What is running", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, [780, 420], {
        "name": "whats_running",
        "description": "Says what is playing now, how much longer, what comes next and how many"
                       "listeners there are. No input.",
        "source": "database",
        "workflowId": {"__rl": True, "value": W_WERKZEUG, "mode": "list",
                       "cachedResultName": W_WERKZEUG_NAME},
        "workflowInputs": {
            "mappingMode": "defineBelow",
            "value": {"question": feld("question", "What the user wants to know, e.g. which title is playing, what comes next, how many listeners", "string", "what is playing now")},
            "matchingColumns": [], "schema": [{"id": "question", "displayName": "question", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False}],
            "attemptToConvertTypes": False, "convertFieldsToString": False},
    }),
    n("Tool Azura addresses", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, [980, 420], {
        "name": "azura_endpoints",
        "description": "Looks up addresses of the station interface (keyword, e.g. playlist,"
                       "user, backup, report, mount, webhook, storage, settings, media). Always"
                       "use it first when you have an administrative task at the station — never"
                       "guess addresses and fields.",
        "source": "database",
        "workflowId": {"__rl": True, "value": W_AZURA, "mode": "list",
                       "cachedResultName": W_AZURA_NAME},
        "workflowInputs": {
            "mappingMode": "defineBelow",
            "value": {"search": feld("search", "Keyword for the address to look up, e.g. playlist")},
            "matchingColumns": [],
            "schema": [{"id": "search", "displayName": "search", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False}],
            "attemptToConvertTypes": False, "convertFieldsToString": False},
    }),
    n("Tool Azura call", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, [1180, 420], {
        "name": "azura_call",
        "description": "Calls an interface of the station (AzuraCast). Inputs: method"
                       "(GET reads, POST/PUT/DELETE changes), path (full, e.g."
                       "/api/station/1/playlists), body (JSON, only when writing), confirmed "
                       "(true if the operator explicitly allowed the change). Without"
                       "confirmed=true nothing happens when writing — then only a"
                       "dry run comes back.",
        "source": "database",
        "workflowId": {"__rl": True, "value": W_AZURA, "mode": "list",
                       "cachedResultName": W_AZURA_NAME},
        "workflowInputs": {
            "mappingMode": "defineBelow",
            "value": {"method": feld("method", "GET for reading, POST/PUT/DELETE for changing", "string", "GET"),
                      "path": feld("path", "Full path with /api/, e.g. /api/station/1/playlists"),
                      "body": feld("body", "JSON body when writing, e.g. {\"name\":\"New\",\"type\":\"default\"}", "string", ""),
                      "confirmed": feld("confirmed", "true if the operator has explicitly allowed the change", "boolean", False)},
            "matchingColumns": [],
            "schema": [{"id": "method", "displayName": "method", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "path", "displayName": "path", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "body", "displayName": "body", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "confirmed", "displayName": "confirmed", "required": False,
                        "defaultMatch": False, "display": True, "type": "boolean",
                        "canBeUsedToMatch": True, "removed": False}],
            "attemptToConvertTypes": False, "convertFieldsToString": False},
    }),
    n("Tool Azura overview", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, [1380, 420], {
        "name": "azura_overview",
        "description": "Overview of the station: facilities, whether broadcast part and output run,"
                       "playlists with title count. For administrative questions (state, lists),"
                       "not for music requests.",
        "source": "database",
        "workflowId": {"__rl": True, "value": W_AZURA, "mode": "list",
                       "cachedResultName": W_AZURA_NAME},
        "workflowInputs": {
            "mappingMode": "defineBelow",
            "value": {"question": feld("question", "What the operator wants to know, e.g. status or playlists", "string", "Ueberblick")},
            "matchingColumns": [],
            "schema": [{"id": "question", "displayName": "question", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False}],
            "attemptToConvertTypes": False, "convertFieldsToString": False},
    }),
    n("Fallback tool", "n8n-nodes-base.executeWorkflow", 1.2, [380, -320], {
        "source": "database",
        "workflowId": {"__rl": True, "value": W_WERKZEUG, "mode": "list",
                       "cachedResultName": W_WERKZEUG_NAME},
        "workflowInputs": {
            "mappingMode": "defineBelow",
            "value": {"searchtext": "={{ $json.command.searchtext || '' }}",
                      "direction": "={{ $json.command.direction || '' }}",
                      "question": "={{ $json.command.question || '' }}",
                      "enqueue": "={{ $json.command.enqueue === true }}"},
            "matchingColumns": [],
            "schema": [{"id": "searchtext", "displayName": "searchtext", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "direction", "displayName": "direction", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "enqueue", "displayName": "enqueue", "required": False,
                        "defaultMatch": False, "display": True, "type": "boolean",
                        "canBeUsedToMatch": True, "removed": False}],
            "attemptToConvertTypes": False, "convertFieldsToString": False},
        "mode": "once", "options": {"waitForSubWorkflow": True},
    }, notes="Fallback without language model: only when the analysis delivered nothing usable."),
    n("Direct or AI?", "n8n-nodes-base.if", 2.2, [160, -320], {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                   "typeValidation": "loose", "version": 2},
                       "combinator": "and",
                       "conditions": [{"id": nid(),
                                       "leftValue": "={{ $json.type === 'direkt' }}",
                                       "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true",
                                                    "singleValue": True}}]},
        "options": {}}, notes="Yes = analysis unusable, the tool plays directly."),
    n("Control?", "n8n-nodes-base.if", 2.2, [160, -520], {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                   "typeValidation": "loose", "version": 2},
                       "combinator": "and",
                       "conditions": [{"id": nid(),
                                       "leftValue": "={{ $json.type === 'control' }}",
                                       "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true",
                                                    "singleValue": True}}]},
        "options": {}}, notes="Yes = basic station control (without language model)."),
    n("Quick control", "n8n-nodes-base.httpRequest", 4.2, [380, -520], {
        "method": "={{ ['pause', 'volume'].includes($json.command.control) ? 'GET' : 'POST' }}",
        "url": "={{ ['pause', 'volume'].includes($json.command.control) ? '"
               + API + "/status' : '" + API + "/backend/' + $json.command.control }}",
        "sendHeaders": True, "headerParameters": {"parameters": AZ_KOPF},
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput",
       notes="Next title, start/stop/restart - fixed addresses, no model."),
    n("Control answer", "n8n-nodes-base.code", 2, [600, -520], {"jsCode": STEUERUNG_ANTWORT_JS}),
    n("Replacement answer", "n8n-nodes-base.code", 2, [600, -320], {"jsCode": ERSATZ_ANTWORT_JS}),

    # Second send node only for the short paths (no access, no text,
    # voice message unintelligible, transcript only). In content the same call
    # as "Send" - but the edges do not run across the whole area.
    n("Send (short message)", "n8n-nodes-base.httpRequest", 4.2, [600, -520], {
        "method": "POST", "url": TG + "/sendMessage",
        "sendHeaders": True, "headerParameters": {"parameters": JSON_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": ("={{ JSON.stringify({ chat_id: $json.chatId, text: $json.answer,"
                     " parse_mode: 'HTML', disable_web_page_preview: true }) }}"),
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput",
       notes="Same call as ‘Send’, only for the short paths at the entry."),
]

bot_verbindungen = {
    "Telegram Trigger": {"main": [[{"node": "Input", "type": "main", "index": 0}]]},
    "Test-Entry": {"main": [[{"node": "Input", "type": "main", "index": 0}]]},
    "Input": {"main": [[{"node": "Voice message?", "type": "main", "index": 0}]]},
    "Voice message?": {"main": [
        [{"node": "Fetch file", "type": "main", "index": 0}],
        [{"node": "Access", "type": "main", "index": 0}],
    ]},
    "Fetch file": {"main": [[{"node": "Load audio", "type": "main", "index": 0}]]},
    "Load audio": {"main": [[{"node": "Umwandeln", "type": "main", "index": 0}]]},
    "Umwandeln": {"main": [[{"node": "Transkript", "type": "main", "index": 0}]]},
    "Transkript": {"main": [[{"node": "Understood?", "type": "main", "index": 0}]]},
    "Understood?": {"main": [
        [{"node": "Access", "type": "main", "index": 0},
         {"node": "Heard text", "type": "main", "index": 0}],
        [{"node": "Send (short message)", "type": "main", "index": 0}]]},
    "Heard text": {"main": [[{"node": "Send (short message)", "type": "main", "index": 0}]]},
    "Access": {"main": [[{"node": "Released?", "type": "main", "index": 0}]]},
    "Released?": {"main": [
        [{"node": "Text there?", "type": "main", "index": 0}],
        [{"node": "No access", "type": "main", "index": 0}]]},
    "No access": {"main": [[{"node": "Send (short message)", "type": "main", "index": 0}]]},
    "Text there?": {"main": [
        [{"node": "Job", "type": "main", "index": 0}],
        [{"node": "No text", "type": "main", "index": 0}]]},
    "Job": {"main": [[{"node": "Short?", "type": "main", "index": 0}]]},
    # Stage 0: recognized quick commands go straight into execution, everything else into the analysis.
    "Short?": {"main": [[{"node": "Shortcut?", "type": "main", "index": 0}]]},
    "Shortcut?": {"main": [
        [{"node": "Loop", "type": "main", "index": 0}],
        [{"node": "Plan", "type": "main", "index": 0}]]},
    "No text": {"main": [[{"node": "Send (short message)", "type": "main", "index": 0}]]},

    # Stage 1: analysis
    "Plan": {"main": [[{"node": "Plan response", "type": "main", "index": 0}]]},
    "Plan response": {"main": [[{"node": "Plan available?", "type": "main", "index": 0}]]},
    "Plan available?": {"main": [
        [{"node": "Read commands", "type": "main", "index": 0}],
        [{"node": "Remember plan", "type": "main", "index": 0}]]},
    "Remember plan": {"main": [[{"node": "Plan again?", "type": "main", "index": 0}]]},
    "Plan again?": {"main": [
        [{"node": "Plan", "type": "main", "index": 0}],
        [{"node": "Read commands", "type": "main", "index": 0}]]},
    "Read commands": {"main": [[{"node": "Command available?", "type": "main", "index": 0}]]},
    "Command available?": {"main": [
        [{"node": "Loop", "type": "main", "index": 0}],
        [{"node": "Build answer", "type": "main", "index": 0}]]},

    # Stage 2: execution per command
    # Note: with splitInBatches v3, output 0 is "done" and output 1 is "loop"
    # (source: return [[], returnItems]) - do not mix them up.
    "Loop": {"main": [
        [{"node": "Get location", "type": "main", "index": 0}],
        [{"node": "Direct or AI?", "type": "main", "index": 0}]]},
    "Direct or AI?": {"main": [
        [{"node": "Fallback tool", "type": "main", "index": 0}],
        [{"node": "Control?", "type": "main", "index": 0}]]},
    "Control?": {"main": [
        [{"node": "Quick control", "type": "main", "index": 0}],
        [{"node": "Ausfuehren", "type": "main", "index": 0}]]},
    "Quick control": {"main": [[{"node": "Control answer", "type": "main", "index": 0}]]},
    "Control answer": {"main": [[{"node": "Loop", "type": "main", "index": 0}]]},
    "Fallback tool": {"main": [[{"node": "Replacement answer", "type": "main", "index": 0}]]},
    "Replacement answer": {"main": [[{"node": "Loop", "type": "main", "index": 0}]]},
    "Ausfuehren": {"main": [[{"node": "Collect results", "type": "main", "index": 0}]]},
    "Collect results": {"main": [[{"node": "Loop", "type": "main", "index": 0}]]},

    # Stage 3: check and follow-up
    "Get location": {"main": [[{"node": "Get queue", "type": "main", "index": 0}]]},
    "Get queue": {"main": [[{"node": "Commands and locations", "type": "main", "index": 0}]]},
    "Commands and locations": {"main": [[{"node": "Check?", "type": "main", "index": 0}]]},
    "Check?": {"main": [
        [{"node": "Pruefen", "type": "main", "index": 0}],
        [{"node": "Read check", "type": "main", "index": 0}]]},
    "Pruefen": {"main": [[{"node": "Check response", "type": "main", "index": 0}]]},
    "Check response": {"main": [[{"node": "Read check", "type": "main", "index": 0}]]},
    "Read check": {"main": [[{"node": "Follow up?", "type": "main", "index": 0}]]},
    "Follow up?": {"main": [
        [{"node": "Loop 2", "type": "main", "index": 0}],
        [{"node": "Build answer", "type": "main", "index": 0}]]},
    "Loop 2": {"main": [
        [{"node": "Build answer", "type": "main", "index": 0}],
        [{"node": "Nacharbeiten", "type": "main", "index": 0}]]},
    "Nacharbeiten": {"main": [[{"node": "Collect addendum", "type": "main", "index": 0}]]},
    "Collect addendum": {"main": [[{"node": "Loop 2", "type": "main", "index": 0}]]},
    "Build answer": {"main": [[{"node": "Answer", "type": "main", "index": 0}]]},
    "Answer": {"main": [[{"node": "Send", "type": "main", "index": 0}]]},

    # Unterschnittstellen
    "Language model execution": {"ai_languageModel": [[{"node": "Ausfuehren", "type": "ai_languageModel", "index": 0}]]},
    "Language model follow-up": {"ai_languageModel": [[{"node": "Nacharbeiten", "type": "ai_languageModel", "index": 0}]]},
    "Search for tool titles": {"ai_tool": [[{"node": "Ausfuehren", "type": "ai_tool", "index": 0},
                                           {"node": "Nacharbeiten", "type": "ai_tool", "index": 0}]]},
    "Search for tool direction": {"ai_tool": [[{"node": "Ausfuehren", "type": "ai_tool", "index": 0},
                                              {"node": "Nacharbeiten", "type": "ai_tool", "index": 0}]]},
    "Tool What is running": {"ai_tool": [[{"node": "Ausfuehren", "type": "ai_tool", "index": 0},
                                         {"node": "Nacharbeiten", "type": "ai_tool", "index": 0}]]},
    "Tool Azura addresses": {"ai_tool": [[{"node": "Ausfuehren", "type": "ai_tool", "index": 0},
                                             {"node": "Nacharbeiten", "type": "ai_tool", "index": 0}]]},
    "Tool Azura call": {"ai_tool": [[{"node": "Ausfuehren", "type": "ai_tool", "index": 0},
                                           {"node": "Nacharbeiten", "type": "ai_tool", "index": 0}]]},
    "Tool Azura overview": {"ai_tool": [[{"node": "Ausfuehren", "type": "ai_tool", "index": 0},
                                               {"node": "Nacharbeiten", "type": "ai_tool", "index": 0}]]},
}

# ================================================================== layout
# The numbers in the node definitions above are only rough placeholders - the
# valid one is this table. It determines how the flow looks in n8n: seven
# groups, each reads from left to right, the groups lie below each other in the
# order of the flow. Step width 220, line spacing 260.
ANORDNUNG = {
    # -- 1 voice message (own branch on top)
    "Fetch file": (-3800, -1860),
    "Load audio": (-3580, -1860),
    "Umwandeln": (-3360, -1860),
    "Transkript": (-3140, -1860),
    "Understood?": (-2920, -1860),
    "Heard text": (-2700, -1860),

    # -- 2 entry and access
    "Telegram Trigger": (-4200, -1380),
    "Test-Entry": (-4200, -1060),
    "Input": (-3980, -1220),
    "Voice message?": (-3760, -1220),
    "Access": (-2980, -1220),
    "Released?": (-2760, -1220),
    "Text there?": (-2540, -1220),
    "Job": (-2320, -1220),
    "No access": (-2760, -1500),
    "No text": (-2540, -1500),
    "Send (short message)": (-2100, -1500),

    # -- 3 quick commands (stage 0) and analysis (stage 1)
    "Short?": (-1800, -400),
    "Shortcut?": (-1580, -400),
    "Plan": (-1360, -400),
    "Plan response": (-1140, -400),
    "Plan available?": (-920, -400),
    "Remember plan": (-1360, -140),
    "Plan again?": (-1140, -140),
    "Read commands": (-680, -400),
    "Command available?": (-460, -400),

    # -- 4 execution in the loop (stage 2)
    "Loop": (-700, 960),
    "Direct or AI?": (-420, 960),
    "Fallback tool": (-140, 700),
    "Replacement answer": (80, 700),
    "Control?": (-140, 960),
    "Quick control": (80, 960),
    "Control answer": (300, 960),
    "Ausfuehren": (80, 1220),
    "Collect results": (300, 1220),
    "Language model execution": (80, 1480),

    # -- 5 tools (sub-interfaces of the agent)
    "Search for tool titles": (560, 1980),
    "Search for tool direction": (760, 1980),
    "Tool What is running": (960, 1980),
    "Tool Azura addresses": (1160, 1980),
    "Tool Azura call": (1360, 1980),
    "Tool Azura overview": (1560, 1980),

    # -- 6 check and follow-up (stage 3)
    "Get location": (880, 960),
    "Get queue": (1100, 960),
    "Commands and locations": (1320, 960),
    "Check?": (1540, 960),
    "Pruefen": (1540, 1220),
    "Check response": (1760, 1220),
    "Read check": (1980, 960),
    "Follow up?": (2200, 960),
    "Loop 2": (2420, 960),
    "Nacharbeiten": (2420, 1220),
    "Collect addendum": (2640, 1220),
    "Language model follow-up": (2420, 1480),

    # -- 7 answer and send
    "Build answer": (2900, 960),
    "Answer": (3120, 960),
    "Send": (3340, 960),
}

# Frame (sticky notes) per group: name, x, y, width, height, color, content.
# About 180 grid points of space below the note text so that the nodes do not
# lie on the writing - in n8n the text sits at the top of the frame. Hence only three lines
# per note; the detailed part sits on the nodes (note) and in the documentation.
RAHMEN = [
    ("note voice message", -3900, -2060, 1500, 360, 6, """## Voice message
Fetch file, convert, recognize (Whisper).
Recognized: continue to **Access** - otherwise a short reply."""),
    ("note Entry", -4300, -1680, 2440, 780, 7, """## Entry and access
Two entries; only the operator gets through (list `allowed`).
The short paths send via **Send (short message)**."""),
    ("note Analyse", -1900, -580, 1620, 700, 5, """## Stage 0 and stage 1
**Quick?** recognizes simple commands without a model, **Quick command?** sends them straight into execution.
Otherwise **Plan** splits the instruction into individual commands."""),
    ("note run", -820, 520, 1420, 1220, 4, """## Stage 2: execution in the loop
One command per pass - output 0 = done, output 1 = continue.
Three paths: fallback without model, fixed control, agent with tools."""),
    ("note tools", 460, 1820, 1300, 360, 3, """## Tools (sub-interfaces)
Dashed = tool connection to **Execution** and **Follow-up**.
File paths stay within the tool flows."""),
    ("note Check", 780, 780, 2020, 1020, 1, """## Stage 3: check and follow-up
**Fetch status** and **Fetch queue** query the station state.
**Follow up?** starts exactly one second attempt per command."""),
    ("note Answer", 2840, 780, 740, 360, 2, """## Answer and send
**Build answer** summarizes everything and builds the buttons of the selection list.
**Send** sends via sendMessage (HTML)."""),
]

# Notes on the nodes. Short and visible in the plan are the important
# nodes (below the node, at most about 34 characters - otherwise the
# texts in the plan overlap the neighbours). Everything else appears only on hover.
KURZNOTIZ = {
    "Input": "Message, voice, button press",
    "Access": "Only the operator",
    "Job": "Context for the analysis",
    "Send (short message)": "Short path, same call",
    "Short?": "Stage 0: without language model",
    "Shortcut?": "Yes = execute directly",
    "Plan": "Stage 1: plan from the text",
    "Plan available?": "Empty = plan again",
    "Remember plan": "Counts the attempts (max. 3)",
    "Read commands": "One item per command",
    "Command available?": "Empty = straight to the answer",
    "Loop": "0 = done, 1 = continue",
    "Direct or AI?": "Yes = fallback without model",
    "Fallback tool": "Tool plays on its own",
    "Control?": "Yes = fixed addresses",
    "Ausfuehren": "One command per pass",
    "Commands and locations": "Outputs + station state",
    "Check?": "No = verdict by rules",
    "Pruefen": "Stage 3: verdict per command",
    "Read check": "ok and reason per command",
    "Follow up?": "Yes = second attempt",
    "Loop 2": "Nachfass-Durchgang",
    "Nacharbeiten": "Second attempt per command",
    "Build answer": "Summarize + buttons",
    "Send": "sendMessage (HTML)",
}

LANGNOTIZ = {
    "Fetch file": "Fetch the path of the voice message from Telegram.",
    "Load audio": "Download the file (in tests via voice.test_url).",
    "Umwandeln": "Speech recognition on the AI server (faster-whisper).",
    "Transkript": "Only pass the text on - it is interpreted later.",
    "Understood?": "No = nothing understood, short reply.",
    "Heard text": "Shows what was understood, for control.",
    "Telegram Trigger": "Entry in the operator chat: messages and button presses.",
    "Test-Entry": "For checking only: accepts a Telegram message as JSON.",
    "Voice message?": "Yes = voice message, own branch on top.",
    "Released?": "No = rejection, the run ends.",
    "Text there?": "No = button, image or sticker without text.",
    "No access": "Short rejection.",
    "No text": "Brief prompt for messages without text.",
    "Plan response": "Reads out the model’s text.",
    "Plan again?": "Yes = new attempt, No = fallback via the execution.",
    "Replacement answer": "Writes the output into the store, then back into the loop.",
    "Quick control": "Next title, start/stop/restart - fixed addresses, no model.",
    "Control answer": "Formulates the station’s answer.",
    "Collect results": "Writes the output into the store, then back into the loop.",
    "Language model execution": "Language model for ‘Execution’ (Ollama via the OpenAI interface).",
    "Search for tool titles": "Tool `search_title` for execution and follow-up.",
    "Search for tool direction": "Tool `search_direction` for execution and follow-up.",
    "Tool What is running": "Tool `whats_running` for execution and follow-up.",
    "Tool Azura addresses": "Tool `azura_endpoints` for execution and follow-up.",
    "Tool Azura call": "Tool `azura_call` for execution and follow-up.",
    "Tool Azura overview": "Tool `azura_overview` for execution and follow-up.",
    "Get location": "What is playing now - evidence for the check.",
    "Get queue": "What is queued - evidence for the check.",
    "Check response": "Reads out the model’s verdict.",
    "Collect addendum": "Writes the output of the second attempt into the store.",
    "Language model follow-up": "Language model for ‘Follow-up’.",
    "Answer": "Prepares the text for Telegram (HTML, without asterisks).",
}


def anordnen(workflow, plan, frames, short, lang):
    """Sets positions, sticky notes and annotations.

    Aborts if a node has no position - otherwise a new node only
    shows up in n8n (it lands somewhere in nowhere).
    """
    names = [k["name"] for k in workflow["nodes"] if "stickyNote" not in k["type"]]
    without = [n for n in names if n not in plan]
    if without:
        raise SystemExit("Without position in ANORDNUNG: " + ", ".join(without))
    ueberzaehlig = [n for n in plan if n not in names]
    if ueberzaehlig:
        raise SystemExit("In ANORDNUNG, but not in the flow: " + ", ".join(ueberzaehlig))
    doppelt = [n for n in short if n in lang]
    if doppelt:
        raise SystemExit("Short and long note on the same node: " + ", ".join(doppelt))
    for k in workflow["nodes"]:
        if k["name"] in plan:
            k["position"] = list(plan[k["name"]])
        if k["name"] in short:
            k["notes"] = short[k["name"]]
            k["notesInFlow"] = True
        elif k["name"] in lang:
            k["notes"] = lang[k["name"]]
    for name, x, y, breite, height, farbe, inhalt in frames:
        workflow["nodes"].append(notiz(name, x, y, breite, height, inhalt, farbe))


agent = {
    "id": "RadioAgentBot",
    "name": "Radio - Telegram-Agent",
    "nodes": bot,
    "connections": bot_verbindungen,
    "settings": {"executionOrder": "v1", "saveDataSuccessExecution": "all",
                 "saveManualExecutions": True},
    "staticData": {"global": {"allowed": [], "run": {"commands": []}}},
    "active": False,
    "versionId": str(uuid.uuid4()),
    "parentFolderId": ORDNER,
}

anordnen(agent, ANORDNUNG, RAHMEN, KURZNOTIZ, LANGNOTIZ)

# ------------------------------------------------- layout of the tools
# The same idea as with the bot: one line per branch, around it a frame with
# a heading. The switches sit on the main line (y = 0).
W_ANORDNUNG = {
    "Entry": (-900, 0),
    "Direction?": (-660, 0),
    "Status only?": (-420, 0),
    "Search direction": (-420, -480),
    "Prepare suggestions": (-180, -480),
    "Smart search": (-420, 380),
    "Station search": (-180, 380),
    "Prepare hits": (60, 380),
    "NowPlaying": (-420, 760),
    "Prepare status": (-180, 760),
    "Hits available?": (540, 0),
    "Enqueue?": (780, 0),
    "Clear queue": (1020, -260),
    "Submit now": (1260, -260),
    "Submit later": (1260, 180),
    "result": (1500, 0),
}

W_RAHMEN = [
    ("note W Weichen", -1000, -160, 460, 340, 5, """## Switches
Direction, status or title search - one of three."""),
    ("note W direction", -520, -640, 560, 360, 4, """## Branch: direction
Mood, genre or decade from the catalog service."""),
    ("note W Search", -520, 220, 900, 340, 1, """## Branch: search title
Catalog service (fuzzy) and full-text search of the station."""),
    ("note W Status", -520, 620, 560, 340, 6, """## Branch: what is running
Only the status - the return value is the text."""),
    ("note W Abspielen", 940, -440, 540, 880, 3, """## Playback
First clear the queue, then play now or queue at the end."""),
]

W_LANGNOTIZ = {
    "Entry": "Fields of the tool: searchtext, direction, question, enqueue.",
    "Search direction": "Catalog service by mood, genre or decade.",
    "Prepare suggestions": "Turns the suggestions into a first title or a list.",
    "Smart search": "Fuzzy search in the catalog service (typo-tolerant).",
    "Station search": "The station’s full-text search as a second source.",
    "Prepare hits": "Merge hits from both sources into a short list.",
    "NowPlaying": "What is playing, what comes next, how many listeners.",
    "Prepare status": "Formulates the status as text (return value of the tool).",
    "Hits available?": "Yes = there is a title that should play.",
    "Enqueue?": "Yes = only enqueue, do not interrupt.",
    "Clear queue": "Clears the station’s interrupting queue.",
    "Submit now": "Submits the title into the interrupting queue right away.",
    "Submit later": "Appends the title behind the current one.",
    "result": "Output node: the tool flow ends here.",
}

W_ANORDNUNG_AZ = {
    "Entry": (-900, 0),
    "Look up addresses?": (-660, 0),
    "Call?": (-420, 0),
    "Guard": (-180, 0),
    "Execute?": (60, 0),
    "Read only?": (300, 0),
    "Call result": (800, 0),
    "Lesen": (540, 220),
    "Schreiben": (540, 460),
    "Dry run": (300, 560),
    "Fetch description": (-420, -480),
    "Find addresses": (-180, -480),
    "Stations": (-420, 900),
    "Status": (-180, 900),
    "Playlists": (60, 900),
    "Ueberblick": (300, 900),
}

W_AZ_RAHMEN = [
    ("note AZ Weichen", -1000, -160, 460, 340, 5, """## Switches
Look up addresses, call or overview."""),
    ("note AZ Adressen", -520, -640, 560, 360, 4, """## Branch: addresses
Search keyword and describe fields."""),
    ("note AZ Call", -520, -260, 1400, 980, 3, """## Branch: call
The guard checks path and method; without confirmed nothing is written."""),
    ("note AZ Ueberblick", -520, 780, 900, 340, 6, """## Branch: overview
Stations, status and playlists."""),
]

W_AZ_LANGNOTIZ = {
    "Entry": "Fields of the tool: search, method, path, body, confirmed, question.",
    "Look up addresses?": "Yes = look up addresses of the station interface.",
    "Fetch description": "Fetch the address directory from the catalog service.",
    "Find addresses": "Short list of matching addresses with fields.",
    "Call?": "Yes = call an interface of the station.",
    "Guard": "Checks method and path - write only with confirmed=true.",
    "Execute?": "Yes = call, No = return dry run.",
    "Read only?": "Yes = GET (read), No = change (POST/PUT/DELETE).",
    "Lesen": "Reads from the station.",
    "Schreiben": "Changes something on the station - only after explicit confirmation.",
    "Dry run": "Shows what the call would do without changing anything.",
    "Call result": "The station’s response, briefly summarized.",
    "Stations": "Stations and whether backend and output are running.",
    "Status": "State of backend and output.",
    "Playlists": "Playlists with title count.",
    "Ueberblick": "Summarizes the overview as text.",
}

anordnen(werkzeuge[0], W_ANORDNUNG, W_RAHMEN, {}, W_LANGNOTIZ)
anordnen(werkzeuge[1], W_ANORDNUNG_AZ, W_AZ_RAHMEN, {}, W_AZ_LANGNOTIZ)

with open("/tmp/radio-werkzeuge.json", "w", encoding="utf-8") as f:
    json.dump(werkzeuge, f, ensure_ascii=False, indent=2)
with open("/tmp/radio-agent.json", "w", encoding="utf-8") as f:
    json.dump(agent, f, ensure_ascii=False, indent=2)


def verbindungen_pruefen(workflow):
    """n8n rejects an import with 'Workflow structure is invalid' when a
    connection points to a non-existent node - and silently keeps the
    old version running (this happened on 2026-09-20: a leftover
    line 'Memory Plan'). Therefore check in advance here."""
    names = {k["name"] for k in workflow["nodes"]}
    error = []
    for source, ausgaenge in workflow["connections"].items():
        if source not in names:
            error.append("Source without node: %s" % source)
        for type, zweige in ausgaenge.items():
            for zweig in zweige or []:
                for target in zweig or []:
                    if target.get("node") not in names:
                        error.append("%s -> %s (%s): target without node"
                                      % (source, target.get("node"), type))
    for k in workflow["nodes"]:
        for type, zweige in (k.get("connections") or {}).items():
            for zweig in zweige or []:
                for target in zweig or []:
                    if target.get("node") not in names:
                        error.append("%s -> %s (%s): target without node"
                                      % (k["name"], target.get("node"), type))
    if error:
        raise SystemExit("Connections invalid in %s:\n  %s"
                         % (workflow.get("name"), "\n  ".join(error)))


for _w in werkzeuge + [agent]:
    verbindungen_pruefen(_w)

print("written: /tmp/radio-werkzeuge.json (%d workflows), /tmp/radio-agent.json"
      % len(werkzeuge))
print("Connections checked:", " + ".join(w["name"] for w in werkzeuge + [agent]))
print("Bot nodes:", len(bot))
for w in werkzeuge:
    print("  ", w["id"], "->", w["name"], "|", len(w["nodes"]), "nodes")
