#!/usr/bin/env python3
"""Erzeugt den n8n-Workflow 'Radio - Telegram-Wunschbot'.

Zugangsdaten kommen aus der Umgebung (AZ_KEY, TG_TOKEN) und landen nur in der
Workflow-Datei.
"""
import json
import os
import uuid

AZ = "http://192.168.178.33"
API = AZ + "/api/station/1"
API_ADMIN = AZ + "/api/admin"
TG = "https://api.telegram.org/bot" + os.environ["TG_TOKEN"]
API_KEY = os.environ["AZ_KEY"]
TG_CRED_ID = os.environ.get("TG_CRED_ID", "DEINE-TELEGRAM-ZUGANGSKENNUNG")
TG_CRED_NAME = os.environ.get("TG_CRED_NAME", "Telegram account 2")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

PLAYLIST_WUNSCH = 8      # wunschbar, spielt der AutoDJ nie
PLAYLIST_SOFORT = 9      # unterbrechend -> sofort
AZ_KOPF = [{"name": "X-API-Key", "value": API_KEY}]
TG_KOPF = [{"name": "Content-Type", "value": "application/json"}]
# Spracherkennung: whisper-stt auf dem ai-Server (RTX 3090 Ti, Modell large-v3, deutsch).
# Rueckfall bei Ausfall: CPU-Dienst whisper-asr im CT 103 mit der OpenAI-Schnittstelle
# (http://192.168.178.53:8000/v1/audio/transcriptions, Modell Systran/faster-whisper-small).
WHISPER = os.environ.get("WHISPER_URL", "http://192.168.178.187:18790/transcribe")
# Sofort spielen und Einreihen laufen ueber die Dateischnittstelle des Senders. Sie
# schreibt unmittelbar in die Warteschlange und kennt keine Sperre - anders als der
# Umweg ueber die unterbrechende Wiedergabeliste ("Queue is not empty").
MEDIEN = API + "/files/batch"
# Katalogdienst (Kontextsuche + Richtungsvorschlaege) im Container radio-tts.
KATALOG = os.environ.get("KATALOG_URL", "http://192.168.178.53:8881")
# Sprachmodell auf dem ai-Server (Ollama, RTX 3090 Ti). Der Bot fragt es bei freiem
# Text und bei Sprachnachrichten, damit auch mehrere Auftraege in einem Satz und
# Bezuege auf das Laufende ("davon noch einen") verstanden werden.
OLLAMA = os.environ.get("OLLAMA_URL", "http://192.168.178.187:11434")
MODELL = os.environ.get("OLLAMA_MODELL", "qwen2.5:14b")


def _katalog_worte():
    """Richtungsworte und Hilfsworte beim Bauen vom Dienst holen.

    Damit gibt es nur eine Quelle der Wahrheit: lernt der Dienst neue
    Richtungen, erkennt der Bot sie nach dem naechsten Bauen von selbst.
    Ist der Dienst nicht erreichbar, gilt eine kurze Notliste.
    """
    notrichtungen = ["rock", "pop", "metal", "rap", "hiphop", "electronic", "disco",
                     "punk", "grunge", "folk", "blues", "jazz", "klassik", "schlager",
                     "deutschrap", "partymusik", "charts", "country", "dance", "balladen",
                     "ruhiges", "hartes"]
    nothilfe = ["musik", "richtung", "genre", "stil", "sound", "was", "etwas", "mal",
                "aus", "dem", "der", "die", "das", "fuer", "mit", "irgendwas"]
    try:
        import urllib.request
        with urllib.request.urlopen(KATALOG + "/genre/liste", timeout=20) as antwort:
            daten = json.load(antwort)
        return (sorted(set(daten["stichwoerter"])), sorted(set(daten["hilfsworte"])))
    except Exception as fehler:
        print(f"Hinweis: {KATALOG}/genre/liste nicht erreichbar ({fehler}) - Notliste wird benutzt")
        return sorted(set(notrichtungen)), sorted(set(nothilfe))


RICHTUNG_WOERTER, RICHTUNG_HILFE = _katalog_worte()


def _katalog_kuenstler(anzahl: int = 45):
    """Haeufigste Interpreten des Archivs - als Fachhinweis fuer die Spracherkennung.

    faster-whisper erkennt Eigennamen deutlich besser, wenn sie im Hinweistext
    stehen. Verhoerte Namen ("neue Runner" statt "Nirvana") werden so seltener.
    """
    notliste = ["Nirvana", "Rammstein", "Metallica", "Queen", "Die Ärzte", "Die Toten Hosen",
                "Modern Talking", "AC/DC", "Linkin Park", "Eminem"]
    try:
        import urllib.request
        with urllib.request.urlopen(
                KATALOG + f"/katalog/kuenstler?anzahl={anzahl}", timeout=25) as antwort:
            namen = json.load(antwort).get("namen") or []
        return namen or notliste
    except Exception as fehler:
        print(f"Hinweis: Künstlerliste nicht erreichbar ({fehler}) - Notliste wird benutzt")
        return notliste


KUENSTLER = _katalog_kuenstler()
SPRACH_HINWEIS = ("Musikwunsch an einen Radiosender. Es geht um Musik: Titel und Interpret. "
                  "Bekannte Interpreten: " + ", ".join(KUENSTLER) + ".")

nr = [0]


def nid():
    return str(uuid.uuid4())


def n(name, typ, version, pos, params, **extra):
    d = {"parameters": params, "id": nid(), "name": name, "type": typ,
         "typeVersion": version, "position": pos}
    d.update(extra)
    return d


def notiz(text, pos, breite=420, hoehe=180, farbe=7):
    return n(f"Notiz {nr[0]}", "n8n-nodes-base.stickyNote", 1, pos,
             {"content": text, "height": hoehe, "width": breite, "color": farbe})


def tg_senden(name, pos, mit_tasten=False):
    # reply_markup nur mitschicken, wenn eine Tastatur vorhanden ist
    # (JSON.stringify laesst undefined weg).
    koerper = ("={{ JSON.stringify({ chat_id: $json.chatId, text: $json.antwort,"
               " parse_mode: 'HTML', disable_web_page_preview: true,"
               " reply_markup: $json.tastatur || undefined }) }}")
    return n(name, "n8n-nodes-base.httpRequest", 4.2, pos, {
        "method": "POST",
        "url": TG + "/sendMessage",
        "sendHeaders": True,
        "headerParameters": {"parameters": TG_KOPF},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": koerper,
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput", notes="Fehler beim Senden (z.B. Testkennung) stoppt den Lauf nicht. ->")


def az_get(name, pfad, pos, parameter=None):
    p = {"method": "GET", "url": pfad if pfad.startswith("http") else API + pfad,
         "sendHeaders": True,
         "headerParameters": {"parameters": AZ_KOPF}, "options": {"timeout": 20000}}
    if parameter:
        p["sendQuery"] = True
        p["queryParameters"] = {"parameters": parameter}
    # Ein Senderfehler soll eine verstaendliche Antwort ergeben, nicht den Lauf beenden.
    return n(name, "n8n-nodes-base.httpRequest", 4.2, pos, p,
             onError="continueRegularOutput")


def az_schreiben(name, methode, pfad, pos, koerper, hinweis=""):
    return n(name, "n8n-nodes-base.httpRequest", 4.2, pos, {
        "method": methode,
        "url": pfad if pfad.startswith(("http", "=")) else AZ + pfad,
        "sendHeaders": True,
        "headerParameters": {"parameters": AZ_KOPF},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": koerper,
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput", notes=hinweis)


def if_knoten(name, pos, links, rechts=None, typ="string", op="equals", bool_true=False):
    if bool_true:
        bedingung = {"id": nid(), "leftValue": links, "rightValue": "",
                     "operator": {"type": "boolean", "operation": "true", "singleValue": True}}
    else:
        bedingung = {"id": nid(), "leftValue": links, "rightValue": rechts,
                     "operator": {"type": typ, "operation": op}}
    return n(name, "n8n-nodes-base.if", 2.2, pos, {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
            "combinator": "and",
            "conditions": [bedingung],
        },
        "options": {},
    })


# ----------------------------------------------------------------- Texte (JS)

EINGABE_JS = r"""
// Telegram-Update vereinheitlichen (Nachricht oder Knopfdruck).
// Der Test-Eingang (Webhook) verpackt den Inhalt unter "body".
const roh = $input.first().json ?? {};
const b = (roh.body && typeof roh.body === 'object') ? roh.body : null;
const quelle = (b && (b.message || b.callback_query || b.edited_message)) ? b : roh;
// Ueber den Test-Eingang (Webhook) muss ein Schluessel mitkommen, der nicht im
// Arbeitsablauf steht - sonst koennte sich jeder Fremde als Betreiber eintragen.
const istTest = !!(roh.body || roh.webhookUrl);
const schluessel = String((roh.query && roh.query.schluessel) || quelle.schluessel || '');
const cq = quelle.callback_query || null;
const m = quelle.message || (cq && cq.message) || {};
const von = (cq && cq.from) || m.from || {};
// Sprachnachricht (oder Tonaufnahme) erkennen.
const stimme = m.voice || m.audio || null;
return [{ json: {
  chatId: String((m.chat && m.chat.id) !== undefined ? m.chat.id : ''),
  text: (m.text || '').trim(),
  istSprache: !!stimme,
  stimmeDateiId: stimme ? String(stimme.file_id || '') : '',
  stimmeDauer: stimme ? Number(stimme.duration || 0) : 0,
  stimmeTestUrl: (stimme && stimme.test_url) ? String(stimme.test_url) : '',
  callbackData: cq ? String(cq.data || '') : '',
  callbackId: cq ? String(cq.id || '') : '',
  messageId: (cq && cq.message ? cq.message.message_id : m.message_id) || null,
  userName: [von.first_name, von.last_name].filter(Boolean).join(' ') || von.username || '',
  isCallback: !!cq,
  istTest, schluessel,
  eingang: new Date().toISOString(),
} }];
"""

ZUGANG_JS = r"""
// Nur freigegebene Chat-Kennungen duerfen den Sender steuern.
// Beim ersten Start wird der erste Chat automatisch zum Betreiber.
const FESTE = [];                    // hier weitere chat_ids eintragen (Komma-getrennt)
const d = $getWorkflowStaticData('global');
if (!Array.isArray(d.erlaubte)) d.erlaubte = (d.erlaubte ? [d.erlaubte] : []);
const j = $json;

// Aufrufe ueber den Test-Eingang brauchen den geheimen Schluessel aus den
// statischen Daten - sonst antwortet der Bot nur "Kein Zugang".
if (j.istTest && (!d.testSchluessel || j.schluessel !== d.testSchluessel)) {
  return [{ json: Object.assign({}, j, { erlaubt: false, neuerBetreiber: false,
                                         betreiber: d.erlaubte }) }];
}

let erlaubt = false, neu = false;
if (FESTE.includes(j.chatId)) {
  erlaubt = true;
} else if (d.erlaubte.length === 0 && j.chatId) {
  d.erlaubte.push(j.chatId);
  erlaubt = true;
  neu = true;
} else {
  erlaubt = d.erlaubte.includes(j.chatId);
}
return [{ json: Object.assign({}, j, { erlaubt, neuerBetreiber: neu, betreiber: d.erlaubte }) }];
"""

AUFTRAG_JS = r"""
// Nachricht in Auftraege verwandeln.
// Schraegstrich-Befehle werden hier genau zerlegt (schneller Weg ohne Modell).
// Freier Text und Sprachnachrichten gehen zum Modell (Knoten Verstehen), das auch
// mehrere Auftraege und Bezuege auf das Laufende erkennt.
const j = $json;
if (j.isCallback) {
  // Knopfdruck: die Kennung des Knopfes wertet der Knoten "Auswahl lesen" aus.
  // "ersatz" muss leer bleiben - sonst deutet der naechste Knoten daraus einen
  // leeren Auftrag und der Bot antwortet mit der Uebersicht, statt zu handeln.
  return [{ json: Object.assign({}, j, { befehl: 'auswahl', argument: '', argumentUrl: '',
                                         genreWort: '', modus: 'wunsch', nurSuche: false,
                                         aufgaben: null, ersatz: [],
                                         brauchtDeutung: false }) }];
}
const text = (j.text || '').trim();
const treffer = text.match(/^\/([a-zA-Z_]+)(@[A-Za-z0-9_]+)?\s*([\s\S]*)$/);
const karte = {
  start: 'hilfe', hilfe: 'hilfe', help: 'hilfe',
  suche: 'suche', search: 'suche', finde: 'suche',
  wunsch: 'wunsch', wish: 'wunsch', spiele: 'sofort',
  sofort: 'sofort', jetzt_spielen: 'sofort',
  jetzt: 'jetzt', now: 'jetzt', was: 'jetzt',
  letzte: 'letzte', history: 'letzte', verlauf: 'letzte',
};
let befehl = 'wunsch';
let argument = text;
let aufgaben = null;
let brauchtDeutung = true;

if (treffer) {
  befehl = karte[treffer[1].toLowerCase()] || 'hilfe';
  argument = (treffer[3] || '').trim();
  if (['suche', 'wunsch', 'sofort'].includes(befehl) && !argument) befehl = 'hilfe';
  aufgaben = [{ befehl: befehl, argument: argument, anzahl: 1 }];
  brauchtDeutung = false;
} else if (!text) {
  befehl = 'hilfe';
  argument = '';
  aufgaben = [{ befehl: 'hilfe', argument: '', anzahl: 1 }];
  brauchtDeutung = false;
}

// Richtungswunsch? ("was aus rock", "etwas ruhiges", "mal metal", "90er")
// Das ist der Rueckfallweg, falls das Modell nicht antwortet.
const RICHTUNG = new Set(RICHTUNG_WOERTER);
const HILFE_WORT = new Set(RICHTUNG_HILFE);
const istRichtung = (t) => RICHTUNG.has(t)
  || Array.from(RICHTUNG).some((r) => r.length > 3 && (r.startsWith(t) || t.startsWith(r)));
const kleinTeile = argument.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().split(' ').filter(Boolean);
let genreWort = '';
if (befehl === 'wunsch' && kleinTeile.length) {
  const istJahr = (t) => /^(19|20)?\d0(er|ern|s)?$/.test(t);
  const nurRichtung = kleinTeile.every((t) => istRichtung(t) || HILFE_WORT.has(t) || istJahr(t));
  if (nurRichtung && kleinTeile.some((t) => istRichtung(t) || istJahr(t))) {
    genreWort = kleinTeile.filter((t) => !HILFE_WORT.has(t)).join(' ') || argument;
  }
}
const ersatz = aufgaben ? [] : [{
  befehl: genreWort ? 'genre' : 'wunsch',
  argument: genreWort || argument,
  richtung: genreWort,
  anzahl: 1,
}];

// /wunsch etwas ruhiges, /wunsch was aus rock: auch ein Schraegstrich-Befehl kann
// eine Richtung meinen. Dann geht es ueber die Richtungssuche.
if (aufgaben && genreWort && aufgaben.length === 1 && aufgaben[0].befehl === 'wunsch') {
  aufgaben[0] = { befehl: 'genre', argument: genreWort, richtung: genreWort, anzahl: 1 };
}

return [{ json: Object.assign({}, j, {
  befehl, argument, argumentUrl: encodeURIComponent(argument), genreWort,
  modus: befehl === 'sofort' ? 'sofort' : 'wunsch',
  nurSuche: befehl === 'suche',
  aufgaben, brauchtDeutung, ersatz,
}) }];
"""

# Was das Sprachmodell ueber den Sender und seine Befehle wissen muss. Die Listen
# kommen beim Bauen aus dem Katalogdienst, damit es nur eine Quelle gibt.
VERSTEHEN_SYSTEM = (
    'Du bist der Steuerrechner des Internetradios "Deadline Beats". Der Betreiber - der einzige '
    'Nutzer - schickt dir Aufgaben, getippt oder als Sprachnachricht, oft mit Erkennungsfehlern. '
    'Du wandelst sie in eine Liste von Befehlen um. Antworte AUSSCHLIESSLICH mit JSON.\n\n'
    'Befehle:\n'
    '- "sofort": einen Titel SOFORT spielen (unterbricht das Laufende). Das ist der '
    'Normalfall: wer einen Titel nennt oder "spiele", "leg auf", "mach an", "dreh mal" '
    'sagt, will ihn jetzt hoeren.\n'
    '- "wunsch": nur, wenn ausdruecklich eine Reihenfolge gewuenscht ist ("danach", '
    '"anschliessend", "spaeter", "als naechstes", "in die Warteschlange")\n'
    '- "genre": nach einer Richtung oder Stimmung suchen lassen (Feld "richtung")\n'
    '- Unbekannte Stimmungsworte ordnest du der naechstliegenden bekannten Richtung zu: '
    '"peppig"/"flott"/"Tempo" -> "party", "ruhig"/"entspannt" -> "ruhig", "hart" -> "metal". '
    'Trage das Wort aus der Liste unten in "richtung" ein, nicht das gesagte.\n'
    '- "suche": nur die Trefferliste zeigen\n'
    '- "jetzt": was laeuft gerade (auch "was laeuft", "welcher Titel", "wie heisst das")\n'
    '- "letzte": was lief zuletzt\n'
    '- "hilfe": die Uebersicht\n\n'
    'Felder je Aufgabe: befehl, titel, interpret, richtung, anzahl.\n'
    '- Zerlege jeden Wunsch in "interpret" und "titel" ("juliet von modern talking" -> '
    'titel "Juliet", interpret "Modern Talking"). Der Bot sucht damit getrennt weiter, '
    'wenn ein Name falsch verstanden wurde.\n'
    '- "anzahl" ist die gewuenschte Zahl von Titeln: "ein paar"/"mehrere"/"einige" = 3, '
    '"viele" = 6, Zahlwoerter als Ziffer ("drei" = 3). Standard 1.\n'
    '- Mehrere Aufgaben in einem Satz ("spiele X und danach Y") ergeben mehrere Eintraege: '
    'der erste "sofort", die weiteren "wunsch".\n'
    '- Bezieht sich etwas auf das Laufende oder Zuletztgehoerte ("davon noch einen", "der gleiche '
    'Interpret", "nochmal", "mehr davon", "so etwas wie gerade"), setze interpret/titel aus dem '
    'Kontext ein.\n'
    'Bekannte Interpreten im Archiv: ' + ", ".join(KUENSTLER) + '\n'
    'Verhoerte Namen ordne diesen Interpreten zu.\n'
    'Richtungen und Stimmungen: ' + ", ".join(RICHTUNG_WOERTER) + '\n\n'
    'Antwortformat: {"aufgaben":[{"befehl":"sofort","titel":"","interpret":"","richtung":"","anzahl":1}]}\n'
    'Wenn du nichts verstehst: {"aufgaben":[{"befehl":"sofort","titel":"<gesagter Text>","anzahl":1}]}'
)

# Anfrage an das Modell: Systemhinweis, Kontext und Aufgabe; Antwort als JSON.
VERSTEHEN_KOERPER = ("={{ JSON.stringify({ model: " + json.dumps(MODELL, ensure_ascii=False)
                    + ", stream: false, format: 'json', keep_alive: '30m',"
                    + " options: { temperature: 0.1, num_ctx: 4096 }, messages: ["
                    + " { role: 'system', content: " + json.dumps(VERSTEHEN_SYSTEM, ensure_ascii=False) + " },"
                    + " { role: 'user', content: ($json.kontextText || '') + ' | Aufgabe: '"
                    + " + ($(\'Auftrag\').item.json.text || \'\') } ] }) }}")

# Winziger Aufruf alle 10 Minuten: haelt das Modell im Speicher der Grafikkarte.
MODELL_WECKEN_KOERPER = ("={{ JSON.stringify({ model: " + json.dumps(MODELL, ensure_ascii=False)
                         + ", stream: false, keep_alive: '30m', options: { num_predict: 1, num_ctx: 512 },"
                         + " messages: [ { role: 'user', content: 'ping' } ] }) }}")

KONTEXT_BAUEN_JS = r"""
// Was laeuft gerade, was lief zuletzt? Das braucht das Modell, um "davon noch einen"
// oder "der gleiche Interpret" aufloesen zu koennen.
const felder = $('Auftrag').item.json;
const jetzt = (() => { try { return $('Kontext holen').item.json || {}; } catch (e) { return {}; } })();
const eingang = $input.all().map((i) => i.json);
const verlauf = (eingang.length === 1 && Array.isArray(eingang[0])) ? eingang[0] : eingang;

const jetztSong = (jetzt.now_playing && jetzt.now_playing.song) || {};
const zeile = (s) => [s && s.artist, s && s.title].filter(Boolean).join(' \u2013 ');
const letzte = verlauf.map((e) => zeile(e && (e.song || e))).filter(Boolean).slice(0, 8);
const kontextText = 'Jetzt laeuft: ' + (zeile(jetztSong) || 'nichts')
  + (jetztSong.genre ? ' (Richtung: ' + jetztSong.genre + ')' : '')
  + (letzte.length ? '\nZuletzt gespielt: ' + letzte.join(' | ') : '');

return [{ json: Object.assign({}, felder, {
  jetztSong: { artist: jetztSong.artist || '', title: jetztSong.title || '',
               genre: jetztSong.genre || '', id: jetztSong.id || '' },
  letzteSongs: letzte,
  kontextText,
}) }];
"""

AUFTEILEN_JS = r"""
// Auftraege zu einzelnen Elementen machen. Jedes Element laeuft danach einmal durch
// Suche, Bewertung und Ausfuehrung - so werden mehrere Wuensche in einer Nachricht
// nacheinander abgearbeitet.
const felder = $('Auftrag').item.json;
const roh = $json;

// Knopfdruck im Chat: nichts zu deuten, die Kennung geht unveraendert weiter.
if (felder.isCallback) {
  return [Object.assign({}, felder, {
    befehl: 'auswahl', argument: '', genreWort: '', anzahl: 1, herkunft: 'knopf',
    modus: 'wunsch', nurSuche: false,
  })];
}

const erlaubt = new Set(['sofort', 'wunsch', 'suche', 'jetzt', 'letzte', 'hilfe', 'genre', 'auswahl']);

function ausModell(inhalt) {
  let text = String(inhalt || '').trim();
  text = text.replace(/^```(?:json)?/i, '').replace(/```$/, '').trim();
  let daten = null;
  try {
    daten = JSON.parse(text);
  } catch (e) {
    const m = text.match(/\{[\s\S]*\}/);           // falls doch Text drumherum steht
    if (m) { try { daten = JSON.parse(m[0]); } catch (e2) { daten = null; } }
  }
  return (daten && Array.isArray(daten.aufgaben)) ? daten.aufgaben : [];
}

const zahlen = { ein: 1, eine: 1, einen: 1, einem: 1, zwei: 2, drei: 3, vier: 4, fuenf: 5,
                 funf: 5, sechs: 6, sieben: 7, acht: 8, neun: 9, zehn: 10, mehrere: 3,
                 einpaar: 2, paar: 2, einige: 3, viele: 6, massenhaft: 8, alles: 10 };
const alsZahl = (w) => {
  const roh = String(w == null ? '' : w);
  if (/\d/.test(roh)) return Math.max(1, Math.min(10, Math.round(Number(roh.replace(/[^0-9]/g, '')) || 1)));
  return zahlen[roh.toLowerCase().trim()] || 1;
};

let aufgaben = null;
let herkunft = 'befehl';
if (Array.isArray(roh.aufgaben)) {
  aufgaben = roh.aufgaben;                                  // Weg ohne Modell
} else {
  herkunft = 'modell';
  aufgaben = ausModell(roh.message && roh.message.content);
  if (!aufgaben.length) {
    herkunft = 'ersatz';
    aufgaben = felder.ersatz || [];
  }
}
if (!aufgaben.length) {
  aufgaben = [{ befehl: 'hilfe', anzahl: 1 }];
  herkunft = 'leer';
}

const items = [];
for (const a of aufgaben) {
  let befehl = String(a.befehl || 'wunsch').toLowerCase().trim();
  if (!erlaubt.has(befehl)) befehl = 'wunsch';
  const teile = [a.interpret, a.titel].map((x) => String(x || '').trim()).filter(Boolean);
  let argument = String(a.argument || a.text || '').trim() || teile.join(' ');
  let richtung = String(a.richtung || '').trim();
  // Nur eine Richtung genannt? Dann ist es eine Richtungssuche, kein leerer Titel.
  if (befehl === 'wunsch' && !argument && richtung) befehl = 'genre';
  if (befehl === 'genre' && !richtung) richtung = argument;
  if (befehl === 'genre' && !argument) argument = richtung;
  if (['wunsch', 'suche', 'sofort'].includes(befehl) && !argument) befehl = 'hilfe';
  // Ohne Suchbegriff darf nie gesucht werden: der Sender liefert dann das ganze
  // Archiv (erste Seite) und der Bot spielte schon versehentlich beliebige Titel.
  const ohneBegriff = !String(argument || '').trim() && !String(richtung || '').trim();
  if (ohneBegriff) befehl = 'hilfe';
  // "spiele Juliet von Modern Talking" heisst beim Betreiber immer: sofort. Wer
  // einen Titel nennt, will ihn hoeren - nicht in eine Warteschlange legen. Nur
  // wenn ausdruecklich eine Reihenfolge genannt wird, wandert der Titel nach
  // hinten. Bei mehreren Auftraegen entscheidet das Modell je Auftrag.
  const gesagt = String(felder.text || '');
  const reihenfolge = /(danach|anschlie\u00dfend|anschliessend|sp\u00e4ter|spaeter|im anschluss|hinterher|warteschlange|einreihen|vormerken|als n\u00e4chstes|als naechstes|nacheinander|danach noch)/i
    .test(gesagt);
  if (aufgaben.length === 1 && herkunft === 'modell' && befehl === 'wunsch' && !reihenfolge) {
    befehl = 'sofort';
  }
  items.push(Object.assign({}, felder, {
    befehl, argument, argumentUrl: encodeURIComponent(argument),
    titel: String(a.titel || '').trim(), interpret: String(a.interpret || '').trim(),
    genreWort: richtung, anzahl: alsZahl(a.anzahl), herkunft,
    modus: befehl === 'sofort' ? 'sofort' : 'wunsch',
    nurSuche: befehl === 'suche',
  }));
}
return items;
"""

WUNSCH_SAMMELN_JS = r"""

// Alle eingereihten Titel in einer Antwort zusammenfassen - mehrere Wuensche in einer
// Nachricht sollen nicht mehrere Nachrichten erzeugen.
const alle = $input.all().map((i) => i.json);
const chatId = (alle[0] || {}).chatId;
if (alle.length <= 1) {
  const e = alle[0] || {};
  return [{ json: { chatId, antwort: e.antwort || '🎙 Erledigt.',
                    tastatur: e.tastatur || null } }];
}
const zeilen = alle.map((e, i) => (i + 1) + '. ' + (e.zeileKurz || e.titel || '?'));
const hinweise = Array.from(new Set(alle.map((e) => e.hinweisKurz).filter(Boolean)));
return [{ json: {
  chatId,
  antwort: '🎵 <b>' + alle.length + ' Titel</b>\n' + zeilen.join('\n')
    + (hinweise.length ? '\n\n\u2139\ufe0f ' + hinweise.join(' \u00b7 ') : ''),
  tastatur: null,
} }];
"""


TRACKS_BILDEN_JS = r"""
// Aus "mehrere Titel gewuenscht" einzelne Elemente machen. Jedes Element laeuft
// danach einmal durch Abspielplan, Wunschliste und Antwort; die Antworten werden
// am Ende zusammengefasst.
const FELDER = ['chatId', 'modus', 'argument', 'richtung', 'richtungHinweis', 'nurSuche',
                'aktion'];
const raus = [];
for (const item of $input.all()) {
  const d = item.json || {};
  const liste = Array.isArray(d.mehrere) ? d.mehrere : [];
  if (!liste.length) {
    raus.push({ json: d });
    continue;
  }
  // Die Angaben zum Auftrag gehoeren an jedes Element: die Weiche entscheidet
  // danach (aktion), Abspielplan braucht modus und chatId.
  const lage = { antwort: '', tastatur: null, mehrere: null };
  for (const f of FELDER) if (d[f] !== undefined) lage[f] = d[f];
  for (const t of liste) raus.push({ json: Object.assign({}, t, lage) });
}
return raus;
"""
VORSCHLAEGE = ["rock", "pop", "metal", "hiphop", "electronic", "disco", "grunge", "punk",
              "folk", "blues", "jazz", "klassik", "schlager", "deutschrap", "party",
              "etwas ruhiges", "was Hartes", "90er", "80er"]


def auftrag_js():
    """Befehlslogik mit den Wortlisten des Katalogdienstes."""
    return (AUFTRAG_JS
            .replace("RICHTUNG_WOERTER", json.dumps(RICHTUNG_WOERTER, ensure_ascii=False))
            .replace("RICHTUNG_HILFE", json.dumps(RICHTUNG_HILFE, ensure_ascii=False)))


GENRE_WAEHLEN_JS = r"""
// Vorschlag des Katalogdienstes uebernehmen (er hat schon geprueft,
// welche Titel wirklich zu der Richtung passen).
const felder = $('Auftrag aufteilen').item.json;
const roh = $json || {};
const treffer = Array.isArray(roh) ? roh : (roh.treffer || []);
// Sagt der Dienst, welche Richtungen er stattdessen benutzt hat? Das hilft,
// wenn die Wunschrichtung im Archiv nicht vorkommt (z.B. Deutschrap).
const genutzt = (roh.genutzt || []);
const wort = String(felder.genreWort || '').toLowerCase();
const genau = genutzt.some((g) => g.includes(wort) || wort.includes(g));
let hinweis = (roh.hinweise || []).join(' · ');
if (!genau && genutzt.length) {
  hinweis = (hinweis ? hinweis + ' · ' : '') + 'ähnliche Richtung: ' + genutzt.slice(0, 3).join(', ');
}
if (!treffer.length) {
  // Nichts Passendes -> die normale Suche bekommt eine zweite Chance.
  return { json: Object.assign({}, felder, { gefunden: false }) };
}
return { json: Object.assign({}, felder, {
  gefunden: true,
  richtung: felder.genreWort,
  richtungHinweis: hinweis,
  treffer,
}) };
"""

HILFE_TEXT = """🎙 <b>Radio-Bot – Deadline Beats</b>

<b>Musik spielen – einfach schreiben</b>
Sag, was laufen soll: „spiele Juliet von Modern Talking“.
Der Titel wird im ganzen Archiv gesucht und geht <b>sofort</b> an den Sender.
Passt nichts eindeutig, zeigt der Bot eine Liste zum Antippen.

Nur mit „danach“, „später“ oder „als Nächstes“ wandert ein Titel hinter das
Laufende statt sofort zu starten.

/suche <i>titel</i> – nur die Trefferliste zeigen
/sofort <i>titel</i> – sofort spielen (dasselbe wie eine freie Nachricht)
/wunsch <i>titel</i> – einreihen, ohne zu unterbrechen

<b>Sprachnachricht</b>
Statt zu tippen kannst du auch sprechen: „spiele sofort Benzin“,
„was läuft gerade“, „wie hieß der Titel eben“. Wird im ganzen
Archiv gesucht und wie ein Befehl behandelt.

<b>Status</b>
/jetzt – was läuft gerade, was kommt danach
/letzte – die letzten Titel
/hilfe – diese Übersicht

Jeder Titel geht unmittelbar an den Sender: er läuft sofort.
Nur wenn du eine Reihenfolge nennst („danach“, „später“), wartet er.

<b>Ohne Titel – nach Richtung</b>
„was aus Rock“, „etwas Ruhiges“, „mal Metal“, „was aus den 90ern“:
der Bot sucht selbst etwas Passendes aus.
Beispiele: %s""" % ", ".join(VORSCHLAEGE)

HILFE_JS = "return { json: { chatId: $json.chatId, antwort: " + json.dumps(HILFE_TEXT) + " } };"

TRANSKRIPT_JS = r"""
// Sprachnachricht in Text verwandeln (nur bereinigen).
// Was gemeint ist, deutet danach das Sprachmodell - es versteht auch mehrere
// Auftraege in einem Satz. Hier bleibt nur: Fehler melden oder Text weitergeben.
const felder = $('Eingabe').item.json;
const roh = $input.first().json || {};

if (roh.error) {
  return [{ json: Object.assign({}, felder, {
    text: '', gehoert: '', istSprache: true,
    antwort: '\u26a0\ufe0f Die Sprachnachricht konnte nicht verarbeitet werden.',
  }) }];
}

const ganz = String(roh.text || '').trim();
const sauber = ganz.replace(/\s+/g, ' ').trim();
if (!sauber) {
  return [{ json: Object.assign({}, felder, {
    text: '', gehoert: '', istSprache: true,
    antwort: '\U0001f3a7 Ich habe nichts verstanden - bitte nochmal sprechen.',
  }) }];
}

return [{ json: Object.assign({}, felder, {
  text: sauber, gehoert: ganz, istSprache: true, sprachDauer: felder.stimmeDauer || 0,
}) }];
"""

GEHOERT_TEXT_JS = r"""
// Rueckmeldung: was wurde gesprochen? Antwortet nichts, ist der Text schon die Antwort.
const felder = $('Eingabe').item.json;
const j = $json;
const zeile = j.antwort || ('🎧 Verstanden: »' + (j.gehoert || '') + '«');
return [{ json: { chatId: felder.chatId || j.chatId, antwort: zeile, tastatur: null } }];
"""


KEIN_ZUGANG_JS = r"""
const j = $json;
if (j.neuerBetreiber) {
  return [{ json: Object.assign({}, j, { antwort:
    '✅ Diesen Chat als Betreiber eingetragen. Ab jetzt darf nur dieser Chat den Sender steuern.\n' +
    'Schreibe /hilfe fuer die Befehle.' }) }];
}
return [{ json: Object.assign({}, j, { antwort:
  '⛔ Kein Zugang. Dieser Bot ist auf den Betreiber beschraenkt.' }) }];
"""

JETZT_JS = r"""
const j = $json;
if (j && j.error) {
  return { json: { chatId: $('Auftrag aufteilen').item.json.chatId,
    antwort: '⚠️ Der Sender antwortet gerade nicht. Bitte später nochmal versuchen.' } };
}
const n = j.now_playing || {};
const song = (n.song && n.song.text) || 'unbekannt';
const rest = Math.max(0, Math.round((n.remaining !== undefined ? n.remaining
  : (n.duration || 0) - (n.elapsed || 0))));
const zeit = rest > 0
  ? `▸ noch ${Math.floor(rest / 60)}:${String(Math.round(rest % 60)).padStart(2, '0')} min`
  : '▸ läuft gerade aus';
const next = (j.playing_next && j.playing_next.song && j.playing_next.song.text) || '–';
const hoerer = j.listeners ? j.listeners.current : 0;
const antwort = [
  '🎵 <b>Jetzt läuft</b>',
  '▸ ' + song,
  zeit,
  n.is_request ? '🎁 Musikwunsch' : '',
  '',
  '⏭ <b>Danach</b>',
  '▸ ' + next,
  '',
  `👥 Zuhörer: ${hoerer}`,
].filter((z) => z !== '').join('\n');
return { json: { chatId: $('Auftrag aufteilen').item.json.chatId, antwort } };
"""

VERLAUF_JS = r"""
// /history liefert eine blanke Liste -> n8n verteilt sie auf mehrere Elemente.
const alle = $input.all().map((i) => i.json);
if (alle.length && alle[0] && alle[0].error) {
  return { json: { chatId: $('Auftrag aufteilen').item.json.chatId,
    antwort: '⚠️ Der Sender antwortet gerade nicht. Bitte später nochmal versuchen.' } };
}
const liste = (alle.length === 1 && Array.isArray(alle[0])) ? alle[0] : alle;
const zeilen = liste.slice(0, 10).map((e, i) => {
  const t = (e.song && e.song.text) || '?';
  const zeit = e.played_at
    ? new Date(e.played_at * 1000).toLocaleTimeString('de-DE',
        { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin' })
    : '--:--';
  const wunsch = e.is_request ? ' 🎁' : '';
  return `${String(i + 1).padStart(2, ' ')}. ${zeit}  ${t}${wunsch}`;
});
return { json: {
  chatId: $('Auftrag aufteilen').item.json.chatId,
  antwort: '🕘 <b>Zuletzt gespielt</b>\n' + (zeilen.join('\n') || 'keine Daten')
    + '\n\n🎁 = Musikwunsch',
} };
"""

BEWERTEN_JS = r"""
// Treffer bewerten, Mehrdeutigkeit erkennen, Auswahl zwischenspeichern.
const felder = $('Auftrag aufteilen').item.json;
const alsListe = (d) => (Array.isArray(d) ? d : (d && (d.rows || d.data || d.treffer)) || []);
// Ergebnis der Klugen Suche (Kontextsuche), falls sie gelaufen ist.
const KLUG = (() => { try { return $('Kluge Suche').item.json.treffer || []; } catch (e) { return []; } })();
// Ergebnis eines Richtungswunsches, falls es einer war.
const GENRE = (() => { try { return $('Genre waehlen').item.json.treffer || []; } catch (e) { return []; } })();
const RICHTUNG = (() => { try { return $('Genre waehlen').item.json.richtung || ''; } catch (e) { return ''; } })();
const RICHTUNG_HINWEIS = (() => { try { return $('Genre waehlen').item.json.richtungHinweis || ''; } catch (e) { return ''; } })();

if (felder.trefferAnzahl === undefined) {
  // Laeuft ohne die erste Suche (Richtungswunsch)? Dann gibt es hier nichts zu pruefen.
  let f = null;
  try { f = $('Treffer 1').item.json; } catch (e) { f = null; }
  if (f && f.antwort) return { json: Object.assign({}, felder, { aktion: 'nichts', antwort: f.antwort, tastatur: null }) };
}

let roh = [];
try { roh = alsListe($('Treffer 1').item.json.ersteListe); } catch (e) { roh = []; }
// Treffer der Kontextsuche immer mitnehmen - Dubletten fallen weiter unten raus.
roh = roh.concat(KLUG.filter((t) => !roh.some((x) => x.id === t.id)));
if (!roh.length && GENRE.length) roh = GENRE.slice();
// Treffer der zweiten und dritten Suche dazunehmen, soweit sie gelaufen sind.
for (const name of ['Suche 2', 'Suche 3']) {
  try {
    const gesehen = new Set(roh.map((t) => t.id));
    alsListe($(name).first().json).forEach((t) => { if (!gesehen.has(t.id)) roh.push(t); });
  } catch (e) { /* Suche lief nicht */ }
}

const norm = (s) => String(s || '').toLowerCase()
  .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
  .replace(/[^a-z0-9]+/g, ' ').trim();

// Kern des Titels ohne Fassungszusatz: "Juliet (remastered)" und "Juliet" sind
// dasselbe Lied - das darf keine Rueckfrage ausloesen.
const kernTitel = (t) => norm(t && t.title)
  .replace(/^\d{1,3}\s+/, ' ')                     // fuehrende Titelnummer ("01. ")
  .replace(/\s*[\(\[][^\)\]]*[\)\]]/g, ' ')
  .replace(/\b(remaster(ed)?|remix|live|edit|version|extended|single|album|radio)\b/g, ' ')
  .replace(/\s+/g, ' ').trim();

const woerter = norm(felder.argument).split(' ').filter(Boolean);
// Sicherheitsnetz: ohne Suchwoerter gibt es keine sinnvolle Bewertung. Der Sender
// wuerde sein ganzes Archiv liefern - daraus darf nie ein Vorschlag werden.
if (!woerter.length) {
  return { json: Object.assign({}, felder, {
    aktion: 'nichts',
    antwort: '🤔 Ich habe keinen Titel und keine Richtung verstanden. '
      + 'Sag zum Beispiel „spiele Juliet von Modern Talking“ oder „was aus Rock“.',
    tastatur: null,
  }) };
}
const ganz = woerter.join(' ');
const dauerOk = (d) => Number(d) > 0 && Number(d) <= 900;

function punkte(t) {
  const titel = norm(t.title);
  const artist = norm(t.artist);
  const heu = [titel, artist, norm(t.album), norm(t.path)].join(' ');
  let p = 0;
  if (titel === ganz) p += 130;
  else if (titel.startsWith(ganz)) p += 95;
  else if (titel.includes(ganz)) p += 75;
  if (artist === ganz) p += 110;
  else if (artist.includes(ganz)) p += 65;
  const drin = woerter.filter((w) => heu.includes(w));
  // Gewichtete Abdeckung: laengere Suchwoerter zaehlen mehr. So ueberholt ein
  // Fuellwort wie "wenn" keinen echten Interpreten-Treffer.
  const gesamt = Math.max(1, woerter.reduce((s, w) => s + w.length, 0));
  const drinGewicht = drin.reduce((s, w) => s + w.length, 0);
  p += (drinGewicht / gesamt) * 55;
  woerter.forEach((w) => {
    if (titel.split(' ').includes(w)) p += 12;
    if (artist.split(' ').includes(w)) p += 8;
    // Lange Suchwoerter, die als ganzes Wort vorkommen, zusaetzlich belohnen.
    if (w.length >= 5 && (titel.split(' ').includes(w) || artist.split(' ').includes(w))) p += 14;
  });
  // Titel und Interpret des Auftrags einzeln pruefen: "Du Hast" von Rammstein
  // darf nicht gegen den ganzen Satz "Rammstein Du Hast" gemessen werden.
  const wunschTitel = norm(felder.titel);
  const wunschInterpret = norm(felder.interpret);
  if (wunschTitel) {
    if (titel === wunschTitel) p += 130;
    else if (titel.startsWith(wunschTitel)) p += 90;
    else if (titel.includes(wunschTitel)) p += 60;
  }
  if (wunschInterpret) {
    if (artist === wunschInterpret) p += 110;
    else if (artist.includes(wunschInterpret)) p += 60;
  }
  const pfad = String(t.path || '').toLowerCase();
  if (/\.(mp3|m4a|aac|ogg|opus|flac)$/.test(pfad)) p += 6;
  if (/\.(mp4|webm|mkv)$/.test(pfad)) p -= 14;
  if (pfad.startsWith('moderation/')) p -= 60;
  if (dauerOk(t.length)) p += 6; else p -= 25;
  // Bruchstuecke (Jingles, angespielte Dateien) nach unten ziehen.
  if (Number(t.length) > 0 && Number(t.length) < 45) p -= 35;
  // Fassungen (remastered, remix, live) sind nicht die erste Wahl.
  if (/\((?:\d{4}\s+)?(?:remaster|remix|live|version|edit|extended)/i.test(String(t.title || ''))) {
    p -= 8;
  }
  // Punkte der Kontextsuche uebernehmen (Aehnlichkeit, Tippfehler-tolerant).
  if (typeof t.punkteFuzzy === 'number') p += t.punkteFuzzy;
  return Math.round(p);
}

const bewertet = (RICHTUNG && GENRE.length)
  // Richtungswunsch: die Reihenfolge des Dienstes stehen lassen. Sie sagt, wie
  // gut ein Titel zur Richtung passt - Wortpunkte gibt es hier ja nicht.
  ? GENRE.map((t) => Object.assign({}, t, { punkte: 60 }))
  : roh.map((t) => Object.assign({}, t, { punkte: punkte(t) }))
      .sort((a, b) => b.punkte - a.punkte);

// Dubletten (gleicher Titel + Interpret) zusammenfassen
// Fassungen desselben Liedes zusammenfassen: "Juliet", "Juliet (remastered)" und
// "Juliet (Jeo's remix)" sind keine drei Moeglichkeiten, sondern eine. Verglichen
// wird der Titel-Kern als Wortfolge - ein Zusatzwort am Ende ("juliet jeo s") ist
// dieselbe Aufnahme, ein anderes Wort ("juliet in love") nicht.
const istFassung = (a, b) => {
  if (!a.length || !b.length) return false;
  const kurz = a.length <= b.length ? a : b;
  const lang = a.length <= b.length ? b : a;
  for (let i = 0; i < kurz.length; i += 1) if (kurz[i] !== lang[i]) return false;
  return true;
};
const treffer = [];
const kerne = [];
for (const t of bewertet) {
  const artist = norm(t.artist);
  const kern = kernTitel(t).split(' ').filter(Boolean);
  if (kerne.some((k) => k.artist === artist && istFassung(k.kern, kern))) continue;
  kerne.push({ artist, kern });
  treffer.push(t);
  if (treffer.length >= 5) break;
}

const d = $getWorkflowStaticData('global');
d.suchen = d.suchen || {};
Object.keys(d.suchen).forEach((k) => {
  if (!d.suchen[k] || Date.now() - (d.suchen[k].ts || 0) > 3600000) delete d.suchen[k];
});

const bester = treffer[0] || null;
const zweiter = treffer[1] || null;
// Klarer Sieger? Dann wird direkt gespielt. Sonst lieber fragen: ein falsch
// verstandener Titel ist schaedlicher als eine kurze Rueckfrage mit Knoepfen.
const sicher = !!bester && bester.punkte >= 90
  && (!zweiter || bester.punkte - zweiter.punkte >= 20);

// Nur ein Interpret genannt, kein Titel? Dann ist "spiel etwas von denen"
// gemeint - dann wird gespielt, nicht gefragt.
const nurInterpret = !String(felder.titel || '').trim() && !!String(felder.interpret || '').trim();

let aktion = 'nichts';
if (bester) {
  // Bei einem Richtungswunsch gibt es keine Worttreffer zu bewerten - der Dienst
  // hat schon ausgewaehlt, also direkt spielen.
  aktion = (!!RICHTUNG || ((sicher || nurInterpret) && !felder.nurSuche))
    ? 'abspielen' : 'auswahl';
}
if (bester) d.suchen[felder.chatId] = { ts: Date.now(), treffer, modus: felder.modus };

const beschriftung = (t) => ((t.artist ? t.artist + ' – ' : '') + (t.title || '?'))
  .slice(0, 55) + (t.length_text ? `  (${t.length_text})` : '');

// Mehrere Titel gewuenscht ("spiele drei Lieder von Nirvana")? Dann die besten
// unterschiedlichen nehmen und jeden einzeln weitergeben - so wird jeder Titel
// eingereiht bzw. gespielt und die Antworten werden danach zusammengefasst.
const gewuenscht = Math.max(1, Math.min(10, Number(felder.anzahl) || 1));
if (bester && gewuenscht > 1 && !felder.nurSuche) {
  // Mehrere Titel: die besten unterschiedlichen sammeln. Sie werden im naechsten
  // Knoten (Tracks bilden) zu einzelnen Elementen - im Einzelmodus darf ein Knoten
  // nur ein Element zurueckgeben.
  const auswahl = [];
  const schonTitel = new Set();
  for (const t of bewertet) {
    const schluessel = norm(t.artist) + '|' + kernTitel(t);
    if (schonTitel.has(schluessel)) continue;
    schonTitel.add(schluessel);
    auswahl.push(t);
    if (auswahl.length >= gewuenscht) break;
  }
  return { json: Object.assign({}, bester, {
    chatId: felder.chatId, aktion: 'abspielen', antwort: '', tastatur: null,
    argument: felder.argument, modus: felder.modus, nurSuche: false,
    richtung: RICHTUNG, richtungHinweis: RICHTUNG_HINWEIS, trefferListe: [],
    mehrere: auswahl,
  }) };
}

let tastatur = null;
let antwort = '';
if (aktion === 'nichts') {
  const kopf = felder.gehoert ? `🎧 Gehört: <i>${felder.gehoert}</i>\n\n` : '';
  antwort = kopf + `🔍 Nichts gefunden für <b>${felder.argument}</b>.\n\n`
    + 'Tipps:\n▸ nur den Interpreten schreiben\n▸ Titel kürzer fassen\n▸ Schreibweise prüfen'
    + (felder.gehoert ? '\n▸ bei Sprachnachrichten: ungewöhnliche Titel lieber tippen' : '');
} else if (aktion === 'auswahl') {
  antwort = `🔍 <b>${treffer.length} Treffer</b> für „${felder.argument}“ – bitte auswählen:`;
  tastatur = { inline_keyboard: treffer.map((t, i) => ([
    { text: `${i + 1}. ${beschriftung(t)}`, callback_data: 'w:' + i },
  ])) };
}

return { json: Object.assign({}, bester || { }, {
  chatId: felder.chatId, aktion, antwort, tastatur,
  argument: felder.argument, modus: felder.modus, nurSuche: felder.nurSuche,
  richtung: RICHTUNG, richtungHinweis: RICHTUNG_HINWEIS,
  trefferListe: treffer.map((t) => beschriftung(t) + ' [' + t.punkte + ']'),
}) };
"""

ABSPIELPLAN_JS = r"""
// Was soll gespielt werden? Nur noch der Dateipfad und die Art (sofort oder danach).
// Der Sender bekommt den Befehl unmittelbar - keine Wiedergabeliste, kein Umweg
// ueber die Wuensche-Schnittstelle des Senders.
const t = $json;
const felder = $json;
const sofort = ($json.sofort === true) || felder.modus === 'sofort';
const titel = ((t.artist ? t.artist + ' – ' : '') + (t.title || '')).trim();
const d = $getWorkflowStaticData('global');
// Fuer den Knopf "Lieber sofort spielen": der zuletzt genannte Titel samt Pfad.
d.letzter = d.letzter || {};
d.letzter[felder.chatId] = { id: t.id, path: t.path, title: t.title, artist: t.artist,
  length_text: t.length_text, sofort };
return { json: Object.assign({}, t, {
  chatId: felder.chatId, sofort, titel, pfad: t.path || '',
  modus: sofort ? 'sofort' : 'wunsch',
}) };
"""
# Merkt sich, welcher Titel in der unterbrechenden Playlist liegt - damit ein
# liegengebliebener Eintrag spaeter wieder entfernt werden kann.
# Zeitplan: raeumt liegengebliebene Eintraege aus der unterbrechenden Playlist.
SOFORT_TEXT_JS = r"""
const plan = $('Abspielplan').item.json;
return { json: {
  chatId: plan.chatId,
  antwort: `⚡️ <b>${plan.titel}</b>\n\nLäuft sofort – der laufende Titel `
    + 'wird ausgeblendet.',
  zeileKurz: plan.titel + ' (sofort)',
  hinweisKurz: '',
} };
"""

DANACH_TEXT_JS = r"""
const plan = $('Abspielplan').item.json;
return { json: {
  chatId: plan.chatId,
  antwort: `🎵 <b>${plan.titel}</b>\n\nLäuft als Nächstes, nach dem `
    + 'laufenden Titel.',
  zeileKurz: plan.titel + ' (danach)',
  hinweisKurz: '',
} };
"""

AUSWAHL_JS = r"""
// Knopfdruck auswerten: "w:<index>" -> gespeicherter Treffer.
const felder = $('Auftrag aufteilen').item.json;
const d = $getWorkflowStaticData('global');
const roh = (felder.callbackData || '').trim();

// Knopf "Trotzdem sofort spielen" (s:) -> letzten Plan nehmen und auf sofort schalten.
if (roh.startsWith('s:')) {
  const letzter = (d.letzter || {})[felder.chatId];
  if (!letzter) {
    return { json: Object.assign({}, felder, {
      abgebrochen: true,
      antwort: '⌛️ Der Titel ist nicht mehr gemerkt. Bitte neu wünschen.',
      tastatur: null,
    }) };
  }
  return { json: Object.assign({}, letzter, { chatId: felder.chatId, sofort: true }) };
}

const eintrag = (d.suchen || {})[felder.chatId];
const idx = roh.startsWith('w:') ? parseInt(roh.slice(2), 10) : -1;
if (!eintrag || isNaN(idx) || !eintrag.treffer[idx]) {
  return { json: Object.assign({}, felder, {
    abgebrochen: true,
    antwort: '⌛️ Die Auswahl ist abgelaufen. Bitte neu suchen.',
    tastatur: null,
  }) };
}
const t = eintrag.treffer[idx];
return { json: Object.assign({}, t, {
  chatId: felder.chatId, sofort: (eintrag.modus || 'wunsch') === 'sofort',
  modus: eintrag.modus || 'wunsch', auswahl: true,
}) };
"""

# --------------------------------------------------------------- Knoten

knoten = [
    # --- Eingang
    n("Telegram Trigger", "n8n-nodes-base.telegramTrigger", 1.2, [-1180, 0],
      {"updates": ["message", "callback_query"], "additionalFields": {}},
      webhookId=nid(), credentials={"telegramApi": {"id": TG_CRED_ID, "name": TG_CRED_NAME}}),
    n("Test-Eingang", "n8n-nodes-base.webhook", 2, [-1180, 240],
      {"httpMethod": "POST", "path": "DEIN-WEBHOOK-PFAD", "responseMode": "lastNode", "options": {}},
      webhookId=nid(), notes="Nur zum Prüfen: nimmt eine Telegram-Nachricht als JSON entgegen."),
    n("Eingabe", "n8n-nodes-base.code", 2, [-940, 100], {"jsCode": EINGABE_JS}),
    if_knoten("Sprachnachricht?", [-740, -140], "={{ $json.istSprache }}", bool_true=True),
    n("Datei holen", "n8n-nodes-base.httpRequest", 4.2, [-540, -320], {
        "method": "GET", "url": TG + "/getFile",
        "sendQuery": True,
        "queryParameters": {"parameters": [
            {"name": "file_id", "value": "={{ $json.stimmeDateiId }}"}]},
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput",
       notes="Holt den Pfad der Sprachnachricht bei Telegram."),
    n("Audio laden", "n8n-nodes-base.httpRequest", 4.2, [-320, -320], {
        "method": "GET",
        "url": "={{ $('Eingabe').item.json.stimmeTestUrl || ('https://api.telegram.org/file/bot'"
               " + " + json.dumps(os.environ["TG_TOKEN"]) + " + '/' + ($json.result ? $json.result.file_path : '')) }}",
        "options": {"timeout": 30000,
                    # Achtung: options.response.response.* - so verlangt es der Knoten.
                    "response": {"response": {"responseFormat": "file",
                                              "outputPropertyName": "audio"}}},
    }, onError="continueRegularOutput",
       notes="Laedt die Audiodatei (OGG/Opus). Ueber den Testeingang darf stimme.test_url gesetzt werden."),
    n("Umwandeln", "n8n-nodes-base.httpRequest", 4.2, [-100, -320], {
        "method": "POST", "url": WHISPER,
        "sendBody": True, "contentType": "multipart-form-data",
        "bodyParameters": {"parameters": [
            {"parameterType": "formBinaryData", "name": "file", "inputDataFieldName": "audio"},
            {"parameterType": "formData", "name": "language", "value": "de"},
            # Fachhinweis: Interpretennamen im Hinweistext erkennt das Modell deutlich besser.
            {"parameterType": "formData", "name": "prompt", "value": SPRACH_HINWEIS},
        ]},
        "options": {"timeout": 120000},
    }, onError="continueRegularOutput",
       notes="Spracherkennung (faster-whisper large-v3, deutsch) auf dem ai-Server, RTX 3090 Ti, 192.168.178.187:18790."),
    n("Transkript", "n8n-nodes-base.code", 2, [60, -320], {"jsCode": TRANSKRIPT_JS}),
    n("Gehoert Text", "n8n-nodes-base.code", 2, [280, -500], {"jsCode": GEHOERT_TEXT_JS}),
    n("Zugang", "n8n-nodes-base.code", 2, [-740, 100], {"jsCode": ZUGANG_JS}),
    if_knoten("Freigegeben?", [-540, 100], "={{ $json.erlaubt }}", bool_true=True),
    n("Kein Zugang", "n8n-nodes-base.code", 2, [-320, 300], {"jsCode": KEIN_ZUGANG_JS}),
    n("Auftrag", "n8n-nodes-base.code", 2, [-320, -100], {"jsCode": auftrag_js()}),

    # --- Deutung durch das Sprachmodell (freier Text und Sprachnachrichten)
    if_knoten("Deutung noetig?", [-100, 60], "={{ $json.brauchtDeutung }}", bool_true=True),
    az_get("Kontext holen", AZ + "/api/nowplaying/1", [120, -320]),
    az_get("Verlauf kurz", "/history", [340, -320],
           parameter=[{"name": "rows", "value": "8"}]),
    n("Kontext bauen", "n8n-nodes-base.code", 2, [560, -320], {"jsCode": KONTEXT_BAUEN_JS}),
    n("Verstehen", "n8n-nodes-base.httpRequest", 4.2, [780, -320], {
        "method": "POST",
        "url": OLLAMA + "/api/chat",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": VERSTEHEN_KOERPER,
        "options": {"timeout": 120000},
    }, onError="continueRegularOutput",
        notes="Deutet freien Text und Sprachnachrichten: mehrere Auftraege, Mengen und "
              "Bezuege auf das Laufende. Modell " + MODELL + " auf dem ai-Server (3090 Ti). ->"),
    n("Auftrag aufteilen", "n8n-nodes-base.code", 2, [1000, -320], {"jsCode": AUFTEILEN_JS}),


    n("Weiche", "n8n-nodes-base.switch", 3.2, [-100, -100], {
        "rules": {"values": [
            {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                            "combinator": "and",
                            "conditions": [{"id": nid(), "leftValue": "={{ $json.befehl }}",
                                            "rightValue": "hilfe",
                                            "operator": {"type": "string", "operation": "equals"}}]},
             "renameOutput": True, "outputKey": "hilfe"},
            {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                            "combinator": "and",
                            "conditions": [{"id": nid(), "leftValue": "={{ $json.befehl }}",
                                            "rightValue": "jetzt",
                                            "operator": {"type": "string", "operation": "equals"}}]},
             "renameOutput": True, "outputKey": "jetzt"},
            {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                            "combinator": "and",
                            "conditions": [{"id": nid(), "leftValue": "={{ $json.befehl }}",
                                            "rightValue": "letzte",
                                            "operator": {"type": "string", "operation": "equals"}}]},
             "renameOutput": True, "outputKey": "letzte"},
            {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                            "combinator": "or",
                            "conditions": [
                                {"id": nid(), "leftValue": "={{ $json.befehl }}",
                                 "rightValue": "wunsch",
                                 "operator": {"type": "string", "operation": "equals"}},
                                {"id": nid(), "leftValue": "={{ $json.befehl }}",
                                 "rightValue": "sofort",
                                 "operator": {"type": "string", "operation": "equals"}},
                                {"id": nid(), "leftValue": "={{ $json.befehl }}",
                                 "rightValue": "suche",
                                 "operator": {"type": "string", "operation": "equals"}}]},
             "renameOutput": True, "outputKey": "suchen"},
            {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                            "combinator": "and",
                            "conditions": [{"id": nid(), "leftValue": "={{ $json.befehl }}",
                                            "rightValue": "auswahl",
                                            "operator": {"type": "string", "operation": "equals"}}]},
             "renameOutput": True, "outputKey": "auswahl"},
            {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                            "combinator": "and",
                            "conditions": [{"id": nid(), "leftValue": "={{ $json.befehl }}",
                                            "rightValue": "genre",
                                            "operator": {"type": "string", "operation": "equals"}}]},
             "renameOutput": True, "outputKey": "genre"},
        ]},
        "options": {"fallbackOutput": "extra"},
    }),

    # --- Hilfe / Status
    n("Hilfe", "n8n-nodes-base.code", 2, [140, -320], {"jsCode": HILFE_JS, "mode": "runOnceForEachItem"}),
    az_get("NowPlaying", AZ + "/api/nowplaying/1", [140, -140]),
    n("Jetzt Text", "n8n-nodes-base.code", 2, [380, -140], {"jsCode": JETZT_JS.replace("$('Auftrag aufteilen')", "$('Auftrag aufteilen')"), "mode": "runOnceForEachItem"}),
    az_get("Verlauf", "/history", [140, 40]),
    n("Verlauf Text", "n8n-nodes-base.code", 2, [380, 40], {"jsCode": VERLAUF_JS}),

    # --- Suche
    az_get("Suche 1", "/files", [140, 240],
           parameter=[{"name": "rowCount", "value": "120"},
                      {"name": "searchPhrase", "value": "={{ $json.argument }}"}]),
    n("Treffer 1", "n8n-nodes-base.code", 2, [380, 240], {"jsCode": r"""
// Volltextsuche des Senders: Ergebnis nur weiterreichen. Welche Treffer zaehlen,
// entscheidet die Bewertung - hier wird nichts mehr verworfen.
const felder = $('Auftrag aufteilen').item.json;
const roh = $json;
if (roh && roh.error) {
  return { json: Object.assign({}, felder, {
    antwort: '⚠️ Der Sender antwortet gerade nicht. Bitte später nochmal versuchen.',
    tastatur: null,
  }) };
}
const liste = Array.isArray(roh) ? roh : (roh.rows || roh.data || []);
return { json: Object.assign({}, felder, {
  ersteListe: liste, trefferAnzahl: liste.length,
}) };
""", "mode": "runOnceForEachItem"}),

    # --- Kontextsuche: laeuft immer mit, liefert Tippfehler-tolerante Treffer
    n("Kluge Suche", "n8n-nodes-base.httpRequest", 4.2, [620, 400], {
        "method": "GET",
        "url": KATALOG + "/suche",
        "sendQuery": True,
        "queryParameters": {"parameters": [
            {"name": "q", "value": "={{ $('Auftrag aufteilen').item.json.argument }}"},
            {"name": "anzahl", "value": "10"},
            {"name": "min_punkte", "value": "40"},
        ]},
        "options": {"timeout": 25000},
    }, onError="continueRegularOutput",
        notes="Aehnlichkeitssuche im Katalogdienst (Tippfehler, undeutlich gesprochene Titel). Laeuft immer mit, die Bewertung entscheidet. ->"),

    # --- Zwei Nachschlagewege mit den Feldern des Sprachmodells: erst der
    # Interpret, dann der Titel. Das faengt falsch verstandene Namen ab
    # ("Julia von Modern Talking" -> Interpret passt, Titel nicht).
    # Ist ein Feld leer, greift der jeweils naechste Wert - eine leere Suchphrase
    # wuerde dem Sender sonst das ganze Archiv zurueckgeben.
    az_get("Suche 2", "/files", [860, 400],
           parameter=[{"name": "rowCount", "value": "60"},
                      {"name": "searchPhrase", "value": "={{ $('Auftrag aufteilen').item.json.interpret || $('Auftrag aufteilen').item.json.titel || $('Auftrag aufteilen').item.json.argument }}"}]),
    az_get("Suche 3", "/files", [1100, 400],
           parameter=[{"name": "rowCount", "value": "60"},
                      {"name": "searchPhrase", "value": "={{ $('Auftrag aufteilen').item.json.titel || $('Auftrag aufteilen').item.json.interpret || $('Auftrag aufteilen').item.json.argument }}"}]),

    n("Bewerten", "n8n-nodes-base.code", 2, [1340, 400],
      {"jsCode": BEWERTEN_JS, "mode": "runOnceForEachItem"}),

    n("Genre suchen", "n8n-nodes-base.httpRequest", 4.2, [140, 700], {
        "method": "GET",
        "url": KATALOG + "/genre",
        "sendQuery": True,
        "queryParameters": {"parameters": [
            {"name": "wort", "value": "={{ $json.genreWort }}"},
            {"name": "anzahl", "value": "25"},
            {"name": "mischen", "value": "true"},
        ]},
        "options": {"timeout": 30000},
    }, onError="continueRegularOutput",
        notes="Suchrichtung und Stimmung im Katalogdienst; liefert fertige Vorschlaege. ->"),
    n("Genre waehlen", "n8n-nodes-base.code", 2, [380, 700], {"jsCode": GENRE_WAEHLEN_JS, "mode": "runOnceForEachItem"}),
    if_knoten("Genre da?", [600, 700], "={{ $json.gefunden }}", bool_true=True),

    n("Tracks bilden", "n8n-nodes-base.code", 2, [1120, 240],
      {"jsCode": TRACKS_BILDEN_JS, "mode": "runOnceForAllItems"}),
    n("Entscheidung", "n8n-nodes-base.switch", 3.2, [1260, 240], {
        "rules": {"values": [
            {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                            "combinator": "and",
                            "conditions": [{"id": nid(), "leftValue": "={{ $json.aktion }}",
                                            "rightValue": "abspielen",
                                            "operator": {"type": "string", "operation": "equals"}}]},
             "renameOutput": True, "outputKey": "abspielen"},
            {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                            "combinator": "and",
                            "conditions": [{"id": nid(), "leftValue": "={{ $json.aktion }}",
                                            "rightValue": "auswahl",
                                            "operator": {"type": "string", "operation": "equals"}}]},
             "renameOutput": True, "outputKey": "auswahl"},
        ]},
        "options": {"fallbackOutput": "extra"},
    }),

    # --- Auswahl / Knopfdruck
    n("Rueckmeldung", "n8n-nodes-base.httpRequest", 4.2, [140, 620], {
        "method": "POST", "url": TG + "/answerCallbackQuery",
        "sendHeaders": True, "headerParameters": {"parameters": TG_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ callback_query_id: $json.callbackId }) }}",
        "options": {"timeout": 15000},
    }, onError="continueRegularOutput"),
    n("Auswahl lesen", "n8n-nodes-base.code", 2, [400, 620], {"jsCode": AUSWAHL_JS, "mode": "runOnceForEachItem"}),
    if_knoten("Auswahl gueltig?", [620, 620], "={{ $json.abgebrochen }}", bool_true=True),

    # --- Abspielen
    n("Abspielplan", "n8n-nodes-base.code", 2, [880, 480],
      {"jsCode": ABSPIELPLAN_JS, "mode": "runOnceForEachItem"}),
    # Der Sender bekommt den Befehl unmittelbar ueber die Dateischnittstelle:
    # "immediate" traegt in die unterbrechende Warteschlange ein, "queue" haengt
    # hinten an. Beides kennt keine Sperre - ein neuer Wunsch geht immer durch.
    if_knoten("Sofort?", [1280, 480], "={{ $('Abspielplan').item.json.sofort }}", bool_true=True),
    # Der Sender spielt Unterbrecher der Reihe nach ab: liegen Wuensche in der
    # Warteschlange, wartet der neue Minuten. Deshalb erst leeren ("flush_and_skip"
    # wirft die wartenden Eintraege weg und beendet den laufenden Unterbrecher),
    # dann erst den neuen Titel eintragen.
    az_schreiben("Warteschlange leeren", "PUT", "/api/admin/debug/station/1/telnet", [1500, 260],
                 "={{ JSON.stringify({ command: 'interrupting_requests.flush_and_skip' }) }}",
                 "Leert die unterbrechende Warteschlange des Senders (Liquidsoap-Befehl)."),
    az_schreiben("Sofort spielen", "PUT", MEDIEN, [1740, 380],
                 "={{ JSON.stringify({ do: 'immediate', files: [$('Abspielplan').item.json.pfad] }) }}",
                 "Spielt den Titel sofort und blendet das Laufende aus."),
    az_schreiben("Danach spielen", "PUT", MEDIEN, [1520, 600],
                 "={{ JSON.stringify({ do: 'queue', files: [$('Abspielplan').item.json.pfad] }) }}",
                 "Haengt den Titel hinter das Laufende."),
    n("Sofort Text", "n8n-nodes-base.code", 2, [1780, 380], {"jsCode": SOFORT_TEXT_JS, "mode": "runOnceForEachItem"}),
    n("Danach Text", "n8n-nodes-base.code", 2, [1780, 600], {"jsCode": DANACH_TEXT_JS, "mode": "runOnceForEachItem"}),
    n("Wunsch sammeln", "n8n-nodes-base.code", 2, [2040, 480],
      {"jsCode": WUNSCH_SAMMELN_JS, "mode": "runOnceForAllItems"}),

    # Alle 10 Minuten ein winziger Aufruf: haelt das Sprachmodell im Speicher der
    # Grafikkarte. Das Aufraeumen der unterbrechenden Wiedergabeliste entfaellt -
    # der Bot benutzt sie nicht mehr.
    n("Zeitplan", "n8n-nodes-base.scheduleTrigger", 1.2, [-1180, 520],
      {"rule": {"interval": [{"field": "minutes", "minutesInterval": 10}]}}, webhookId=nid()),
    n("Modell wecken", "n8n-nodes-base.httpRequest", 4.2, [-940, 700], {
        "method": "POST",
        "url": OLLAMA + "/api/chat",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": MODELL_WECKEN_KOERPER,
        "options": {"timeout": 60000},
    }, onError="continueRegularOutput",
        notes="Haelt das Sprachmodell geladen. ->"),

    tg_senden("Senden", [2600, 100]),
    tg_senden("Senden mit Tasten", [1500, 780], mit_tasten=True),
]

verbindungen = {
    "Telegram Trigger": {"main": [[{"node": "Eingabe", "type": "main", "index": 0}]]},
    "Zeitplan": {"main": [[{"node": "Modell wecken", "type": "main", "index": 0}]]},
    "Modell wecken": {"main": [[]]},
    "Test-Eingang": {"main": [[{"node": "Eingabe", "type": "main", "index": 0}]]},
    "Eingabe": {"main": [[{"node": "Sprachnachricht?", "type": "main", "index": 0}]]},
    "Sprachnachricht?": {"main": [
        [{"node": "Datei holen", "type": "main", "index": 0}],
        [{"node": "Zugang", "type": "main", "index": 0}],
    ]},
    "Datei holen": {"main": [[{"node": "Audio laden", "type": "main", "index": 0}]]},
    "Audio laden": {"main": [[{"node": "Umwandeln", "type": "main", "index": 0}]]},
    "Umwandeln": {"main": [[{"node": "Transkript", "type": "main", "index": 0}]]},
    "Transkript": {"main": [[
        {"node": "Zugang", "type": "main", "index": 0},
        {"node": "Gehoert Text", "type": "main", "index": 0},
    ]]},
    "Gehoert Text": {"main": [[{"node": "Senden", "type": "main", "index": 0}]]},
    "Zugang": {"main": [[{"node": "Freigegeben?", "type": "main", "index": 0}]]},
    "Freigegeben?": {"main": [
        [{"node": "Auftrag", "type": "main", "index": 0}],
        [{"node": "Kein Zugang", "type": "main", "index": 0}],
    ]},
    "Kein Zugang": {"main": [[{"node": "Senden", "type": "main", "index": 0}]]},
    "Auftrag": {"main": [[{"node": "Deutung noetig?", "type": "main", "index": 0}]]},
    "Deutung noetig?": {"main": [
        [{"node": "Kontext holen", "type": "main", "index": 0}],
        [{"node": "Auftrag aufteilen", "type": "main", "index": 0}],
    ]},
    "Kontext holen": {"main": [[{"node": "Verlauf kurz", "type": "main", "index": 0}]]},
    "Verlauf kurz": {"main": [[{"node": "Kontext bauen", "type": "main", "index": 0}]]},
    "Kontext bauen": {"main": [[{"node": "Verstehen", "type": "main", "index": 0}]]},
    "Verstehen": {"main": [[{"node": "Auftrag aufteilen", "type": "main", "index": 0}]]},
    "Auftrag aufteilen": {"main": [[{"node": "Weiche", "type": "main", "index": 0}]]},
    "Weiche": {"main": [
        [{"node": "Hilfe", "type": "main", "index": 0}],
        [{"node": "NowPlaying", "type": "main", "index": 0}],
        [{"node": "Verlauf", "type": "main", "index": 0}],
        [{"node": "Suche 1", "type": "main", "index": 0}],
        [{"node": "Rueckmeldung", "type": "main", "index": 0}],
        [{"node": "Genre suchen", "type": "main", "index": 0}],
        [{"node": "Hilfe", "type": "main", "index": 0}],
    ]},
    "Hilfe": {"main": [[{"node": "Senden", "type": "main", "index": 0}]]},
    "NowPlaying": {"main": [[{"node": "Jetzt Text", "type": "main", "index": 0}]]},
    "Jetzt Text": {"main": [[{"node": "Senden", "type": "main", "index": 0}]]},
    "Verlauf": {"main": [[{"node": "Verlauf Text", "type": "main", "index": 0}]]},
    "Verlauf Text": {"main": [[{"node": "Senden", "type": "main", "index": 0}]]},
    "Suche 1": {"main": [[{"node": "Treffer 1", "type": "main", "index": 0}]]},
    "Treffer 1": {"main": [[{"node": "Kluge Suche", "type": "main", "index": 0}]]},
    "Kluge Suche": {"main": [[{"node": "Suche 2", "type": "main", "index": 0}]]},
    "Suche 2": {"main": [[{"node": "Suche 3", "type": "main", "index": 0}]]},
    "Suche 3": {"main": [[{"node": "Bewerten", "type": "main", "index": 0}]]},
    "Genre suchen": {"main": [[{"node": "Genre waehlen", "type": "main", "index": 0}]]},
    "Genre waehlen": {"main": [[{"node": "Genre da?", "type": "main", "index": 0}]]},
    "Genre da?": {"main": [
        [{"node": "Bewerten", "type": "main", "index": 0}],
        [{"node": "Suche 1", "type": "main", "index": 0}],
    ]},
    "Bewerten": {"main": [[{"node": "Tracks bilden", "type": "main", "index": 0}]]},
    "Tracks bilden": {"main": [[{"node": "Entscheidung", "type": "main", "index": 0}]]},
    "Entscheidung": {"main": [
        [{"node": "Abspielplan", "type": "main", "index": 0}],
        [{"node": "Senden mit Tasten", "type": "main", "index": 0}],
        [{"node": "Senden", "type": "main", "index": 0}],
    ]},
    "Rueckmeldung": {"main": [[{"node": "Auswahl lesen", "type": "main", "index": 0}]]},
    "Auswahl lesen": {"main": [[{"node": "Auswahl gueltig?", "type": "main", "index": 0}]]},
    "Auswahl gueltig?": {"main": [
        [{"node": "Senden", "type": "main", "index": 0}],
        [{"node": "Abspielplan", "type": "main", "index": 0}],
    ]},
    "Abspielplan": {"main": [[{"node": "Sofort?", "type": "main", "index": 0}]]},
    "Sofort?": {"main": [
        [{"node": "Warteschlange leeren", "type": "main", "index": 0}],
        [{"node": "Danach spielen", "type": "main", "index": 0}],
    ]},
    "Warteschlange leeren": {"main": [[{"node": "Sofort spielen", "type": "main", "index": 0}]]},
    "Sofort spielen": {"main": [[{"node": "Sofort Text", "type": "main", "index": 0}]]},
    "Danach spielen": {"main": [[{"node": "Danach Text", "type": "main", "index": 0}]]},
    "Sofort Text": {"main": [[{"node": "Wunsch sammeln", "type": "main", "index": 0}]]},
    "Danach Text": {"main": [[{"node": "Wunsch sammeln", "type": "main", "index": 0}]]},
    "Wunsch sammeln": {"main": [[{"node": "Senden", "type": "main", "index": 0}]]},
}

workflow = {
    "id": "RadioTelegramBot",
    "name": "Radio - Telegram-Wunschbot",
    "nodes": knoten,
    "connections": verbindungen,
    "settings": {"executionOrder": "v1", "saveManualExecutions": True, "saveDataSuccessExecution": "all"},
    "staticData": {"global": {"erlaubte": [], "suchen": {}}},
    "active": False,
    "versionId": str(uuid.uuid4()),
}

with open("/tmp/radio-telegram.json", "w", encoding="utf-8") as f:
    json.dump(workflow, f, ensure_ascii=False, indent=2)
echte = [k for k in knoten if not k["type"].endswith("stickyNote")]
print("geschrieben: /tmp/radio-telegram.json")
print("Knoten:", len(echte), "| davon HTTP:", sum(1 for k in echte if k["type"].endswith("httpRequest")),
      "| Code:", sum(1 for k in echte if k["type"].endswith("code")))
print(", ".join(k["name"] for k in echte))
