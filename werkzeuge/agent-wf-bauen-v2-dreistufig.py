#!/usr/bin/env python3
"""Erzeugt den Radio-Bot als AI-Agent mit Werkzeugen.

Statt einer langen Wenn-Dann-Kette entscheidet ein KI-Agent (Ollama auf der 3090 Ti),
welches Werkzeug er braucht. Jedes Werkzeug ist ein eigener kleiner Arbeitsablauf:

  Werkzeug - Titel suchen     suchtext        -> Trefferliste mit Dateipfaden
  Werkzeug - Richtung suchen  richtung        -> Vorschlaege fuer Stimmung/Genre
  Werkzeug - Sofort spielen   pfad, titel     -> leert die Warteschlange und spielt sofort
  Werkzeug - Danach spielen   pfad, titel     -> reiht hinter das Laufende ein
  Werkzeug - Was laeuft       (keine)         -> was laeuft, was kommt, Zuhoerer

Zugangsdaten kommen aus dem Umfeld (AZ_KEY, TG_TOKEN). Ausgabe:
  /tmp/radio-werkzeuge.json  (Liste der Werkzeug-Arbeitsablaeufe)
  /tmp/radio-agent.json      (der Bot)
"""
import json
import os
import uuid

AZ = "http://192.168.178.33"
API = AZ + "/api/station/1"
API_ADMIN = AZ + "/api/admin"
KATALOG = os.environ.get("KATALOG_URL", "http://192.168.178.53:8881")
OLLAMA = os.environ.get("OLLAMA_URL", "http://192.168.178.187:11434")
MODELL = os.environ.get("OLLAMA_MODELL", "qwen3.6:27b")
WHISPER = os.environ.get("WHISPER_URL", "http://192.168.178.188:8000/transcribe")
TG = "https://api.telegram.org/bot" + os.environ["TG_TOKEN"]
AZ_KEY = os.environ["AZ_KEY"]
TG_TOKEN = os.environ["TG_TOKEN"]
# Der Knoten "Ollama Chat Model" reicht in dieser n8n-Fassung keine Werkzeugaufrufe
# durch (das Modell antwortet mit leerem Text, der Agent bricht ab). Ollama spricht
# unter /v1 dieselbe Schnittstelle wie OpenAI - deshalb der OpenAI-Knoten.
OLLAMA_OAI_URL = os.environ.get("OLLAMA_OAI_URL", OLLAMA + "/v1")
OAI_CRED = os.environ.get("OLLAMA_OAI_CRED_ID", "DEINE-OLLAMA-ZUGANGSKENNUNG")
OAI_CRED_NAME = os.environ.get("OLLAMA_OAI_CRED_NAME", "Ollama (OpenAI-Schnittstelle)")
OLLAMA_CRED = os.environ.get("OLLAMA_CRED_ID", "radioOllama01")
OLLAMA_CRED_NAME = os.environ.get("OLLAMA_CRED_NAME", "Ollama (Radio)")
TG_CRED_ID = os.environ.get("TG_CRED_ID", "DEINE-TELEGRAM-ZUGANGSKENNUNG")
TG_CRED_NAME = os.environ.get("TG_CRED_NAME", "Telegram account 2")

AZ_KOPF = [{"name": "X-API-Key", "value": AZ_KEY}]
JSON_KOPF = [{"name": "Content-Type", "value": "application/json"}]
# Ollama spricht unter /v1 die OpenAI-Schnittstelle; der Schluessel ist beliebig.
OLLAMA_KOPF = [{"name": "Content-Type", "value": "application/json"},
               {"name": "Authorization", "value": "Bearer " + os.environ.get("OLLAMA_KEY", "ollama")}]


def modell_koerper(system, nutzer_ausdruck, temperatur, tokens):
    """Textkoerper fuer einen direkten Modellaufruf (POST /v1/chat/completions).

    Fuer die werkzeuglosen Stufen (Analyse, Pruefung) wird der Agentenknoten bewusst
    NICHT benutzt: n8n haengt dort eigene Anweisungen an, mit denen das Modell einfache
    Auftraege als "kein Auftrag" einordnete (am 2026-09-20 reproduzierbar: dieselbe
    Aufforderung direkt gestellt lieferte den richtigen Plan, im Agenten ein leeres
    Ergebnis). Ein blanker Aufruf ist ausserdem schneller und billiger.
    """
    return ("={{ JSON.stringify({ model: " + json.dumps(MODELL)
            + ", messages: [{ role: 'system', content: " + json.dumps(system)
            + " }, { role: 'user', content: " + nutzer_ausdruck + " }]"
            + ", temperature: " + repr(temperatur).rstrip("0").rstrip(".")
            + ", max_tokens: " + str(tokens) + " }) }}")


ANTWORT_AUSLESEN_JS = r"""
// Antwort eines direkten Modellaufrufs in das Feld "output" legen - die folgenden
// Knoten lesen alle "output" (so wie frueher beim Agenten).
const j = $json || {};
const wahl = (j.choices && j.choices[0]) || {};
const text = (wahl.message && wahl.message.content) || j.output || j.text || '';
return [{ json: Object.assign({}, j, { output: String(text || '') }) }];
"""

# Suchtext fuer die beiden Suchdienste: Fuellwoerter weg, sonst trifft die
# Volltextsuche des Senders jeden Titel, in dem "von" oder "bitte" steht.
SUCHTEXT = ("={{ String($('Eingang').first().json.suchtext || '')"
            ".replace(/\\b(von|vom|the|der|die|das|den|dem|des|und|oder|aus|mit|ohne|fuer|"
            "bitte|mal|doch|einmal|sofort|gleich|jetzt|schnell|eben|denn|mir|noch|"
            "spiele|spiel|leg|lege|mach|was|etwas|ein|eine|einen|"
            "im|in|am|an|auf|zu|zur|zum|feat|ft|of|with|by|and)\\b/gi, ' ')"
            ".replace(/\\s+/g, ' ').trim() }}")

PROJEKT = "DEINE-N8N-PROJEKT-KENNUNG"
ORDNER = "vEDODlq4jIKCUDmf"

# Ein einziger Werkzeug-Arbeitsablauf fuer alles: Titel suchen, Richtung, Status.
#
# Der Agent haengt drei Werkzeugknoten daran (titel_suchen, richtung_suchen,
# was_laeuft); welcher Zweig laeuft, entscheidet die Eingabe. Das haelt die
# Uebersicht klein und laesst nur EINEN Unter-Arbeitsablauf aktiv sein.
#
# Suchen und Abspielen stecken bewusst im selben Ablauf: der Dateipfad darf
# nicht durch das Sprachmodell wandern (kleinere Modelle erfinden ihn dann).
# Das Modell nennt nur Suchbegriff, Nummer oder Richtung.
W_WERKZEUG = "RadioWerkzeug"
W_WERKZEUG_NAME = "Werkzeug - Radio"

# Eigener Werkzeug-Ablauf fuer den Sender selbst (AzuraCast): Adressen
# nachschlagen, beliebige Schnittstelle aufrufen, Ueberblick holen. Der Agent
# haengt drei Werkzeugknoten daran - so kann der Betreiber den Server ueber den
# Chat bedienen, ohne dass die Radio-Werkzeuge unuebersichtlich werden.
W_AZURA = "AzuraWerkzeug"
W_AZURA_NAME = "Werkzeug - AzuraCast"


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


def notiz(name, x, y, breite, hoehe, inhalt, farbe=4):
    """Haftnotiz (Gruppenrahmen) - liegt in n8n hinter den Knoten.

    Felder dieser n8n-Fassung: content, height, width, color (1..7).
    """
    return n(name, "n8n-nodes-base.stickyNote", 1, [x, y],
             {"content": inhalt, "height": hoehe, "width": breite, "color": farbe})


def http(name, pos, methode, url, koerper=None, kopf=None, hinweis=""):
    p = {"method": methode, "url": url,
         "sendHeaders": True, "headerParameters": {"parameters": kopf or []},
         "options": {"timeout": 30000}}
    if koerper is not None:
        p["sendBody"] = True
        p["specifyBody"] = "json"
        p["jsonBody"] = koerper
    return n(name, "n8n-nodes-base.httpRequest", 4.2, pos, p,
             onError="continueRegularOutput", notes=hinweis)


def http_get(name, pos, url, parameter, hinweis=""):
    p = {"method": "GET", "url": url, "sendQuery": True,
         "queryParameters": {"parameters": parameter},
         "sendHeaders": True, "headerParameters": {"parameters": AZ_KOPF},
         "options": {"timeout": 30000}}
    return n(name, "n8n-nodes-base.httpRequest", 4.2, pos, p,
             onError="continueRegularOutput", notes=hinweis)


def trigger(pos, felder):
    """Ausloeser eines Unter-Arbeitsablaufs mit benannten Eingabefeldern."""
    return n("Eingang", "n8n-nodes-base.executeWorkflowTrigger", 1.1, pos,
             {"workflowInputs": {"values": felder}, "inputSource": "workflowInputs"})


def wenn(name, pos, ausdruck, hinweis=""):
    """Wenn-Knoten: erster Ausgang = wahr, zweiter Ausgang = falsch."""
    return n(name, "n8n-nodes-base.if", 2.2, pos, {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                   "typeValidation": "loose", "version": 2},
                       "combinator": "and",
                       "conditions": [{"id": nid(), "leftValue": ausdruck,
                                       "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true",
                                                    "singleValue": True}}]},
        "options": {}}, notes=hinweis)


def feld(name, beschreibung, art="string", standard=None):
    """Eingabefeld eines Werkzeugs, das das Modell fuellt.

    Ohne $fromAI hat der Werkzeug-Knoten nur einen einzigen Textparameter: n8n
    baut die Beschreibung fuer das Modell aus den $fromAI-Aufrufen der
    Knoten-Parameter (extractFromAIParameters). Bleibt `value` leer, kommt beim
    Unter-Arbeitsablauf nichts an - das Feld ist dann einfach null.

    Ein Vorgabewert macht das Feld freiwillig: Pflichtfelder muessen vom Modell
    gefuellt werden, sonst bricht der Aufruf mit "Received tool input did not
    match expected schema" ab.
    """
    teile = [json.dumps(name), json.dumps(beschreibung), json.dumps(art)]
    if standard is not None:
        teile.append(json.dumps(standard))
    return "={{ $fromAI(%s) }}" % ", ".join(teile)


def werkzeug_arbeit(ident, name, knoten, verbindungen):
    return {
        "id": ident,
        "name": name,
        "nodes": knoten,
        "connections": verbindungen,
        "settings": {"executionOrder": "v1"},
        "staticData": None,
        "active": False,
        "versionId": str(uuid.uuid4()),
        "parentFolderId": ORDNER,
    }


# ------------------------------------------------------------------ Werkzeuge

# --- 1) Titel suchen: erst der unscharfe Katalogdienst, dann die Volltextsuche
SUCHE_JS = r"""
// Treffer beider Quellen zu einer kurzen Liste machen, die das Sprachmodell lesen kann.
// Der Suchbegriff wird am Ausloeser gelesen: die HTTP-Schritte davor geben ihre
// eigene Antwort aus und tragen die Eingabe nicht weiter.
const eingang = $('Eingang').first().json || {};
const suchtext = String(eingang.suchtext || $json.suchtext || '').trim();
const einreihen = eingang.einreihen === true
  || String(eingang.einreihen || '').toLowerCase() === 'true';
if (!suchtext) {
  return [{ json: { ergebnis: 'FEHLER: Kein Suchbegriff. Nenne Interpret und/oder Titel, '
    + 'zum Beispiel "Modern Talking Juliet". Suche nie ohne Begriff.', pfad: '',
    einreihen: einreihen } }];
}

const okText = (t) => 'OK: "' + t + '" ' + (einreihen
  ? 'laeuft danach (nach dem laufenden Titel).'
  : 'laeuft jetzt sofort.');

// Merker der letzten Auswahlliste: "2" oder "nummer 2" loest daraus auf. So muss
// das Modell den Dateipfad nicht abschreiben - kleinere Modelle erfinden ihn sonst.
const d = $getWorkflowStaticData('global');
const vorher = Array.isArray(d.listen) ? d.listen : [];
const zahl = suchtext.match(/^[^\d]{0,12}(\d{1,2})[^\d]{0,6}$/);
if (zahl) {
  const t = vorher[Number(zahl[1]) - 1];
  if (!t) {
    return [{ json: { ergebnis: (vorher.length
      ? 'Die Nummer ' + zahl[1] + ' gibt es nicht - zur Auswahl standen ' + vorher.length + ' Titel.'
      : 'Es steht keine Auswahlliste bereit. Suche erst nach einem Titel.'), pfad: '',
      einreihen: einreihen } }];
  }
  d.listen = [];
  return [{ json: { ergebnis: okText(t.titel), pfad: t.pfad, titel: t.titel,
    einreihen: einreihen } }];
}

function quelle(quelleName) {
  try {
    const j = $(quelleName).first().json;
    if (!j || j.error) return [];
    if (Array.isArray(j.treffer)) return j.treffer;              // Katalogdienst
    return (j.rows || j.data || (Array.isArray(j) ? j : []));    // Sender
  } catch (e) { return []; }
}

const norm = (s) => String(s || '').toLowerCase()
  .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
  .replace(/[^a-z0-9]+/g, ' ').trim();

// Kern des Titels ohne Fassungszusatz: "Juliet (remastered)", "01. Juliet" und
// "Juliet" sind dasselbe Lied. Ohne diese Zusammenfassung sieht das Modell drei
// Moeglichkeiten und fragt nach, statt einfach zu spielen (Wunsch des Betreibers:
// ein genannter Titel laeuft sofort).
const kernTitel = (t) => norm(t && t.title)
  .replace(/^\d{1,3}\s+/, ' ')
  .replace(/\s*[\(\[][^\)\]]*[\)\]]/g, ' ')
  .replace(/\b(remaster(ed)?|remix|live|edit|version|extended|single|album|radio)\b/g, ' ')
  .replace(/\s+/g, ' ').trim();

// Ein Zusatzwort am Ende ist dieselbe Aufnahme ("juliet jeo s"), ein anderes Wort
// nicht ("juliet in love").
function istFassung(a, b) {
  if (!a.length || !b.length) return false;
  const kurz = a.length <= b.length ? a : b;
  const lang = a.length <= b.length ? b : a;
  for (let i = 0; i < kurz.length; i += 1) if (kurz[i] !== lang[i]) return false;
  return true;
}

const kernS = (t) => kernTitel(t).split(' ').filter(Boolean);
const treffer = [];
const gesehen = new Set();
const kerne = [];
for (const t of quelle('Suche klug').concat(quelle('Suche Sender'))) {
  const pfad = t.path || '';
  if (!pfad) continue;
  const roh = (t.artist || '') + '|' + (t.title || '') + '|' + pfad;
  if (gesehen.has(roh)) continue;
  gesehen.add(roh);
  const artist = norm(t.artist);
  const kern = kernS(t);
  if (kerne.some((k) => k.artist === artist && istFassung(k.kern, kern))) continue;
  kerne.push({ artist: artist, kern: kern });
  treffer.push(t);
  if (treffer.length >= 5) break;
}

if (!treffer.length) {
  d.listen = [];
  return [{ json: { ergebnis: 'KEINE TREFFER fuer "' + suchtext + '". '
    + 'Versuche den Interpreten allein oder eine Richtung (richtung_suchen).', pfad: '',
    einreihen: einreihen } }];
}

// Wie viele Titel eine Auswahlliste hoechstens zeigt. Telegram erlaubt deutlich
// mehr Knoepfe (callback_data ist auf 1-64 Bytes begrenzt, deshalb steht dort nur
// eine Nummer), aber acht Vorschlaege sind im Chat eine gute Grenze.
const AUSWAHL_MAX = 8;

// Bewertung: "spiele Juliet von Modern Talking" soll sofort spielen, nicht
// nachfragen. Ein einzelner Suchbegriff liefert im Archiv schnell einen zweiten
// Titel aus demselben Album ("Down on My Knees") - der ist deutlich schwaecher
// und darf keine Rueckfrage ausloesen. Deshalb nur dann eine Liste zeigen, wenn
// zwei Treffer gleich stark sind.
//
// Fuellwoerter fliegen raus ("von", "the", "bitte"), sonst passt nie ein Titel
// vollstaendig. Und: ein Titel, in dem NICHT alle genannten Woerter vorkommen,
// ist nie ein klarer Treffer - sonst spielt "Sweet Dreams von Eurythmics" am
// Ende "Sweet Dreams My Love" von jemand anderem (passiert am 2026-09-19).
const STOPP = new Set(['von', 'vom', 'der', 'die', 'das', 'den', 'dem', 'des', 'und', 'oder',
  'aus', 'mit', 'ohne', 'fuer', 'im', 'in', 'am', 'an', 'auf', 'zu', 'zur', 'zum', 'ein', 'eine',
  'einen', 'the', 'of', 'with', 'by', 'and', 'a', 'la', 'le', 'los', 'les', 'feat', 'ft',
  'bitte', 'mal', 'spiele', 'spiel', 'leg', 'was']);
const woerter = norm(suchtext).split(' ').filter((w) => w && !STOPP.has(w));
const nenntAlle = (t) => {
  if (!woerter.length) return false;
  const teile = (norm(t.artist) + ' ' + norm(t.title) + ' ' + norm(t.path)).split(' ');
  return woerter.every((w) => teile.includes(w) || teile.some((x) => x.length > 3 && x.includes(w)));
};
function punkte(t) {
  const titel = norm(t.title);
  const artist = norm(t.artist);
  const heu = [titel, artist, norm(t.album), norm(t.path)].join(' ');
  let p = 0;
  for (const w of woerter) {
    if (artist.split(' ').includes(w)) p += 30;
    if (titel.split(' ').includes(w)) p += 25;
    if (heu.includes(w)) p += 8;
  }
  // Alles, was der Nutzer genannt hat, steckt in Interpret oder Titel.
  if (nenntAlle(t)) p += 40;
  const dauer = Number(t.length);
  if (dauer > 0 && dauer < 45) p -= 35;        // Jingles, angespielte Dateien
  if (/^moderation\//i.test(String(t.path || ''))) p -= 60;
  return p;
}

const bewertet = treffer.map((t) => ({ t: t, p: punkte(t) })).sort((a, b) => b.p - a.p);
const klar = nenntAlle(bewertet[0].t)
  && (bewertet.length === 1 || (bewertet[0].p - bewertet[1].p) >= 25);
const zeigen = klar ? bewertet.slice(0, 1) : bewertet.slice(0, AUSWAHL_MAX);

const name = (t) => (t.artist ? t.artist + ' - ' : '') + (t.title || '?');
const zeilen = zeigen.map((e, i) => (i + 1) + '. ' + name(e.t)
  + (e.t.length_text ? '  (' + e.t.length_text + ')' : ''));
const bester = zeigen[0].t;

if (klar) {
  d.listen = [];
  // Klarer Treffer: das Werkzeug spielt selbst (Knoten "Sofort eintragen") - das
  // Modell bekommt nur die fertige Meldung und kann den Titel nicht bloss ankuendigen.
  return [{ json: { ergebnis: okText(name(bester)), pfad: bester.path || '',
    titel: name(bester), einreihen: einreihen } }];
}

// Auswahl merken: bei der naechsten Nachricht ("2" oder Knopfdruck) loest das
// Werkzeug daraus auf. "auswahl" sind nur die Titel - der Bot baut daraus die
// anklickbaren Knoepfe (callback_data "w" + Nummer), der Dateipfad bleibt hier.
d.listen = zeigen.map((e) => ({ titel: name(e.t), pfad: e.t.path }));
return [{ json: {
  ergebnis: 'Mehrere Titel passen zu "' + suchtext + '":\n' + zeilen.join('\n')
    + '\n\nFrage kurz, welcher gemeint ist. Antwortet er mit einer Nummer, rufe titel_suchen\n'
    + 'mit genau dieser Nummer als suchtext auf.',
  auswahl: zeigen.map((e) => name(e.t)),
  pfad: '', einreihen: einreihen } }];
"""

WERKZEUG_ERGEBNIS_JS = r"""
// Der Suchlauf hat bei einem klaren Treffer schon gespielt - hier nur noch die
// Antwort des Senders pruefen und den Text weitergeben. Der Text steht je nach
// Zweig in "Treffer aufbereiten" (Titelsuche) oder "Vorschlaege aufbereiten"
// (Richtung); der jeweils andere Knoten ist nicht gelaufen.
let auf = {};
try { auf = $('Treffer aufbereiten').first().json || {}; } catch (e) { auf = {}; }
if (!auf.ergebnis) {
  try { auf = $('Vorschlaege aufbereiten').first().json || {}; } catch (e) { auf = {}; }
}
let antwort = null;
if (auf.pfad) {
  const quelle = auf.einreihen ? 'Danach eintragen' : 'Sofort eintragen';
  try { antwort = $(quelle).first().json; } catch (e) { antwort = null; }
}
if (!auf.pfad || !antwort) return [{ json: { ergebnis: auf.ergebnis || 'Kein Treffer.',
  auswahl: Array.isArray(auf.auswahl) ? auf.auswahl : [] } }];
const fehler = (antwort.errors || []).length || antwort.error;
return [{ json: { ergebnis: (fehler
  ? 'FEHLER beim Eintragen: ' + JSON.stringify(antwort.errors || antwort.error)
  : auf.ergebnis),
  auswahl: Array.isArray(auf.auswahl) ? auf.auswahl : [] } }];
"""

# --- 2) Richtung suchen
RICHTUNG_JS = r"""
// Eingabe am Ausloeser lesen (siehe SUCHE_JS).
const eingang = $('Eingang').first().json || {};
const wort = String(eingang.richtung || $json.richtung || '').trim();
const einreihen = eingang.einreihen === true
  || String(eingang.einreihen || '').toLowerCase() === 'true';
if (!wort) {
  return [{ json: { ergebnis: 'FEHLER: Keine Richtung genannt.', pfad: '',
    einreihen: einreihen } }];
}
let j = {};
try { j = $('Richtung suchen').first().json || {}; } catch (e) { j = {}; }
if (j.error || !j.treffer || !j.treffer.length) {
  return [{ json: { ergebnis: 'Die Richtung "' + wort + '" kennt der Katalog nicht. '
    + 'Bekannte Richtungen: party, dance, rock, pop, metal, hiphop, electronic, disco, '
    + 'punk, grunge, folk, blues, jazz, klassik, schlager, deutschrap, ruhig, hart, 90er, 80er. '
    + 'Nimm eine davon und rufe richtung_suchen erneut auf.' } }];
}
const zeilen = j.treffer.slice(0, 4).map((t, i) => (i + 1) + '. '
  + ((t.artist ? t.artist + ' - ' : '') + (t.title || '?'))
  + (t.length_text ? '  (' + t.length_text + ')' : ''));
const erster = j.treffer[0];
const titel = (erster.artist ? erster.artist + ' - ' : '') + (erster.title || '?');
// Eine Stimmung ist ein Auftrag, keine Frage: gespielt wird hier im Werkzeug,
// das Modell meldet nur noch das Ergebnis (Knoten "Sofort eintragen").
const wo = einreihen ? 'laeuft danach (nach dem laufenden Titel).' : 'laeuft jetzt sofort.';
return [{ json: {
  ergebnis: 'OK: "' + titel + '" ' + wo + ' (Richtung ' + (j.richtung || wort) + ').'
    + (zeilen.length > 1 ? '\nDanach koennen kommen: ' + zeilen.slice(1, 4).join(', ') : ''),
  pfad: erster.path || '',
  titel: titel,
  einreihen: einreihen } }];
"""

STATUS_JS = r"""
const j = $json || {};
if (j.error) {
  return [{ json: { ergebnis: 'Der Sender antwortet gerade nicht.' } }];
}
const jetzt = (j.now_playing && j.now_playing.song) || {};
const rest = Math.max(0, Math.round((jetzt.duration || 0) - (jetzt.elapsed || 0)));
const naechster = (j.playing_next && j.playing_next.song) || {};
return [{ json: { ergebnis: 'Jetzt laeuft: ' + (jetzt.text || 'unbekannt')
  + (rest ? ' (noch ' + Math.floor(rest / 60) + ':' + String(rest % 60).padStart(2, '0') + ' min)' : '')
  + '\nDanach: ' + (naechster.text || 'unbekannt')
  + '\nZuhoerer: ' + ((j.listeners && j.listeners.current) || 0) } }];
"""

werkzeuge = []

# Ein Werkzeug-Arbeitsablauf fuer alles. Der Agent haengt drei Werkzeugknoten
# daran; welcher Zweig laeuft, entscheidet die Eingabe (richtung / frage / suchtext).
werkzeuge.append(werkzeug_arbeit(W_WERKZEUG, W_WERKZEUG_NAME, [
    # Alle Felder des Werkzeugs stehen am Ausloeser. Je Aufruf ist nur eines
    # gefuellt - der Ablauf entscheidet danach, welcher Zweig laeuft.
    trigger([-900, 0], [{"name": "suchtext", "type": "string"},
                        {"name": "richtung", "type": "string"},
                        {"name": "frage", "type": "string"},
                        {"name": "einreihen", "type": "boolean"}]),
    wenn("Richtung?", [-660, 0], "={{ !!String($json.richtung || '').trim() }}",
         "Ja = Stimmung/Genre/Jahrzehnt -> Vorschlaege holen und den ersten spielen."),

    # --- Zweig: Richtung
    http_get("Richtung suchen", [-420, -220], KATALOG + "/genre", [
        {"name": "wort", "value": "={{ $('Eingang').first().json.richtung }}"},
        {"name": "anzahl", "value": "12"},
        {"name": "mischen", "value": "true"}],
        "Richtung, Stimmung oder Jahrzehnt im Katalogdienst."),
    code("Vorschlaege aufbereiten", [-180, -220], RICHTUNG_JS),

    # --- Zweig: nur Status
    wenn("Nur Status?", [-420, 200], "={{ !!String($json.frage || '').trim() }}",
         "Ja = Frage zum Programm, keine Suche."),
    http("NowPlaying", [-180, 400], "GET", AZ + "/api/nowplaying/1", None, AZ_KOPF,
         "Was laeuft, was kommt danach, wie viele Zuhoerer."),
    code("Status aufbereiten", [60, 400], STATUS_JS),

    # --- Zweig: Titel suchen (Katalogdienst unscharf + Volltextsuche des Senders)
    # Der Suchtext wird vorher von Fuellwoertern befreit: die Volltextsuche des Senders
    # verknuepft die Woerter mit ODER, sonst liefert "spiele Benzin von Rammstein"
    # jeden Titel, in dem "von" vorkommt.
    http_get("Suche klug", [-180, 120], KATALOG + "/suche", [
        {"name": "q", "value": SUCHTEXT},
        {"name": "anzahl", "value": "8"},
        {"name": "min_punkte", "value": "40"}],
        "Unscharfe Suche im Katalogdienst (Tippfehler-tolerant)."),
    http_get("Suche Sender", [60, 120], API + "/files", [
        {"name": "searchPhrase", "value": SUCHTEXT},
        {"name": "rowCount", "value": "40"}],
        "Volltextsuche des Senders als zweite Quelle."),
    code("Treffer aufbereiten", [300, 0], SUCHE_JS),

    # --- gemeinsames Abspielen (beide Zweige laufen hier zusammen)
    wenn("Treffer da?", [540, 0], "={{ !!$json.pfad }}",
         "Ja = der Titel soll laufen (klarer Treffer oder Nummer aus der Auswahl)."),
    wenn("Einreihen?", [780, 0], "={{ $('Treffer da?').first().json.einreihen }}",
         "Ja = nur einreihen, nicht unterbrechen."),
    http("Warteschlange leeren", [1020, -180], "PUT", API_ADMIN + "/debug/station/1/telnet",
         "={{ JSON.stringify({ command: 'interrupting_requests.flush_and_skip' }) }}",
         AZ_KOPF, "Leert die unterbrechende Warteschlange des Senders."),
    http("Sofort eintragen", [1260, -180], "PUT", API + "/files/batch",
         "={{ JSON.stringify({ do: 'immediate', files: [$('Treffer da?').first().json.pfad] }) }}",
         AZ_KOPF, "Traegt den Titel sofort in die unterbrechende Warteschlange ein."),
    http("Danach eintragen", [1260, 60], "PUT", API + "/files/batch",
         "={{ JSON.stringify({ do: 'queue', files: [$('Treffer da?').first().json.pfad] }) }}",
         AZ_KOPF, "Haengt den Titel hinter das Laufende."),
    code("Ergebnis", [1500, 0], WERKZEUG_ERGEBNIS_JS),
], {
    "Eingang": {"main": [[{"node": "Richtung?", "type": "main", "index": 0}]]},
    "Richtung?": {"main": [
        [{"node": "Richtung suchen", "type": "main", "index": 0}],
        [{"node": "Nur Status?", "type": "main", "index": 0}]]},
    "Richtung suchen": {"main": [[{"node": "Vorschlaege aufbereiten", "type": "main", "index": 0}]]},
    "Vorschlaege aufbereiten": {"main": [[{"node": "Treffer da?", "type": "main", "index": 0}]]},
    "Nur Status?": {"main": [
        [{"node": "NowPlaying", "type": "main", "index": 0}],
        [{"node": "Suche klug", "type": "main", "index": 0}]]},
    "NowPlaying": {"main": [[{"node": "Status aufbereiten", "type": "main", "index": 0}]]},
    "Suche klug": {"main": [[{"node": "Suche Sender", "type": "main", "index": 0}]]},
    "Suche Sender": {"main": [[{"node": "Treffer aufbereiten", "type": "main", "index": 0}]]},
    "Treffer aufbereiten": {"main": [[{"node": "Treffer da?", "type": "main", "index": 0}]]},
    "Treffer da?": {"main": [
        [{"node": "Einreihen?", "type": "main", "index": 0}],
        [{"node": "Ergebnis", "type": "main", "index": 0}]]},
    "Einreihen?": {"main": [
        [{"node": "Danach eintragen", "type": "main", "index": 0}],
        [{"node": "Warteschlange leeren", "type": "main", "index": 0}]]},
    "Warteschlange leeren": {"main": [[{"node": "Sofort eintragen", "type": "main", "index": 0}]]},
    "Sofort eintragen": {"main": [[{"node": "Ergebnis", "type": "main", "index": 0}]]},
    "Danach eintragen": {"main": [[{"node": "Ergebnis", "type": "main", "index": 0}]]},
}))


# ------------------------------------------------------------------ Sender-Schnittstelle

# --- Adressen nachschlagen: aus der OpenAPI-Beschreibung die passenden Pfade
ENDPUNKTE_JS = r"""
// Das Modell soll Adressen nicht raten: hier bekommt es die echten Pfade aus der
// Beschreibung des Senders (Offene Schnittstelle, OpenAPI). Die Beschreibung ist
// eine YAML-Datei mit sehr regelmaessigem Aufbau - ein Zeilenscan genuegt.
const roh = $json || {};
const text = String(typeof roh.data === 'string' ? roh.data : (roh.body || ''));
if (!text) {
  return [{ json: { ergebnis: 'FEHLER: Die Beschreibung des Senders kam nicht an. '
    + 'Rufe die Adresse spaeter erneut auf.' } }];
}
const eingang = $('Eingang').first().json || {};
const suche = String(eingang.suche || '').trim().toLowerCase();

const punkte = [];
let pfad = '';
let methode = '';
for (const z of text.split('\n')) {
  const mp = z.match(/^    '(\/[^']*)':\s*$/);
  if (mp) { pfad = mp[1]; methode = ''; continue; }
  const mm = z.match(/^        (get|post|put|delete|patch):\s*$/);
  if (mm && pfad) { methode = mm[1].toUpperCase(); continue; }
  const ms = z.match(/^            summary: (.*)$/);
  if (ms && pfad && methode) {
    punkte.push({ m: methode, p: pfad, s: ms[1].replace(/^['"]|['"]$/g, '').trim() });
    methode = '';
  }
}
if (!punkte.length) {
  return [{ json: { ergebnis: 'FEHLER: Die Beschreibung des Senders liess sich nicht lesen.' } }];
}

const treffer = punkte.filter((x) => !suche
  || (x.p + ' ' + x.s).toLowerCase().includes(suche));
if (!treffer.length) {
  return [{ json: { ergebnis: 'Keine Adresse gefunden fuer "' + suche + '". '
    + 'Versuche ein anderes Stichwort (playlist, user, backup, report, mount, webhook, '
    + 'storage, settings, media).' } }];
}
const zeilen = treffer.slice(0, 40).map((x, i) => (i + 1) + '. ' + x.m + ' /api' + x.p
  + '  - ' + x.s);
return [{ json: { ergebnis: 'Adressen zum Stichwort "' + suche + '" (' + treffer.length
  + ' Treffer):\n' + zeilen.join('\n')
  + '\n\nPfade immer mit /api/ beginnen lassen ({id} durch die Kennung ersetzen). '
  + 'Lesen mit azura_aufruf und methode=GET. Schreiben nur nach Rueckfrage des Betreibers '
  + 'und dann mit bestaetigt=true.' } }];
"""

# --- Wache: Pfad und Methode pruefen, Schreiben nur mit Bestaetigung
WACHE_JS = r"""
const j = $('Eingang').first().json || {};
const methode = String(j.methode || 'GET').trim().toUpperCase();
let pfad = String(j.pfad || '').trim();
const koerper = String(j.koerper || '').trim();
const bestaetigt = j.bestaetigt === true || String(j.bestaetigt).toLowerCase() === 'true';
const erlaubt = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'];

if (!erlaubt.includes(methode)) {
  return [{ json: { bereit: false, ergebnis: 'FEHLER: "' + methode + '" ist keine bekannte '
    + 'Methode. Nimm GET (lesen) oder POST/PUT/DELETE (aendern).' } }];
}
if (pfad && !pfad.startsWith('/')) pfad = '/' + pfad;
if (!pfad.startsWith('/api/')) {
  return [{ json: { bereit: false, ergebnis: 'FEHLER: Der Pfad muss mit /api/ beginnen '
    + '(z. B. /api/station/1/playlists). Nutze azura_endpunkte zum Nachschlagen.' } }];
}
// Schreiben (anlegen, aendern, loeschen) nur nach Rueckfrage - ein Modell soll
// nicht von sich aus in den Server schreiben. Ohne Bestaetigung gibt es einen
// Trockenlauf, den der Agent dem Betreiber vorlegen kann.
if (methode !== 'GET' && !bestaetigt) {
  return [{ json: { bereit: false, ergebnis: 'Trockenlauf (nichts geaendert): ' + methode
    + ' ' + pfad + (koerper ? ' mit ' + koerper.slice(0, 400) : '')
    + '\nFrage den Betreiber, ob das ausgefuehrt werden soll, und rufe dann erneut mit '
    + 'bestaetigt=true auf.' } }];
}
return [{ json: { bereit: true, methode: methode, pfad: pfad, koerper: koerper } }];
"""

TROCKENLAUF_JS = r"""
// Nichts ausgefuehrt - nur die Meldung der Wache weitergeben.
return [{ json: { ergebnis: String($json.ergebnis || 'Nichts zu tun.') } }];
"""

AUFRUF_ERGEBNIS_JS = r"""
// Antwort des Senders in eine kurze Meldung packen. Grosse Antworten (z. B. das
// ganze Musikarchiv) werden gekuerzt - sonst laeuft der Gespraechsspeicher voll.
const wache = $('Wache').first().json || {};
// Listen-Antworten kommen als mehrere Elemente an - alle zusammenfassen.
const alle = $input.all().map((i) => i.json);
const j = alle.length === 1 ? alle[0] : alle;
let text;
if (j && j.error) {
  text = 'FEHLER: ' + JSON.stringify(j.error).slice(0, 600);
} else if (j && typeof j.data === 'string') {
  text = j.data;
} else {
  text = JSON.stringify(j);
}
const gekuerzt = text.length > 4000;
return [{ json: { ergebnis: 'Antwort auf ' + wache.methode + ' ' + wache.pfad
  + (gekuerzt ? ' (gekuerzt)' : '') + ':\n' + text.slice(0, 4000) } }];
"""

UEBERSICHT_JS = r"""
// Kurzer Zustandsbericht des Senders: Anlagen, Technik, Wiedergabelisten.
// Achtung: n8n verteilt Listen-Antworten (Anlagen, Wiedergabelisten) auf mehrere
// Elemente - deshalb .all() und nicht .first().
const hole = (name) => { try { return $(name).all().map((i) => i.json || {}); } catch (e) { return []; } };

const zeilen = [];
for (const anlage of hole('Anlagen').slice(0, 5)) {
  zeilen.push('- Anlage: ' + (anlage.name || '?')
    + ' (' + (anlage.short_name || anlage.shortcode || '') + ')'
    + (anlage.is_enabled === false ? ' [aus]' : ''));
}
const zustand = hole('Zustand')[0] || {};
zeilen.push('Technik: Sendeteil ' + (zustand.backendRunning ? 'laeuft' : 'steht')
  + ', Ausgabe ' + (zustand.frontendRunning ? 'laeuft' : 'steht'));
const listen = hole('Wiedergabelisten');
for (const liste of listen.slice(0, 10)) {
  zeilen.push('- Wiedergabeliste: ' + (liste.name || '?') + ' (' + (liste.type || '?') + ')'
    + (liste.is_enabled === false ? ' [aus]' : '') + ' | Titel: ' + (liste.num_songs ?? '?'));
}
if (listen.length > 10) zeilen.push('- ... und ' + (listen.length - 10) + ' weitere Wiedergabelisten');
return [{ json: { ergebnis: 'Ueberblick ueber den Sender:\n' + zeilen.join('\n') } }];
"""

# Ein Werkzeug-Ablauf fuer den Sender selbst. Drei Werkzeugknoten des Agenten
# zeigen darauf; welcher Zweig laeuft, entscheidet die Eingabe (suche / pfad / frage).
werkzeuge.append(werkzeug_arbeit(W_AZURA, W_AZURA_NAME, [
    trigger([-900, 0], [{"name": "suche", "type": "string"},
                        {"name": "methode", "type": "string"},
                        {"name": "pfad", "type": "string"},
                        {"name": "koerper", "type": "string"},
                        {"name": "bestaetigt", "type": "boolean"},
                        {"name": "frage", "type": "string"}]),
    wenn("Adressen suchen?", [-660, 0], "={{ !!String($json.suche || '').trim() }}",
         "Ja = Adressen der Senderschnittstelle nachschlagen."),
    http("Beschreibung holen", [-420, -200], "GET", AZ + "/api/openapi.yml", None, AZ_KOPF,
         "Offene Schnittstelle des Senders (OpenAPI, YAML)."),
    code("Adressen finden", [-180, -200], ENDPUNKTE_JS),

    wenn("Aufruf?", [-420, 150], "={{ !!String($json.pfad || '').trim() }}",
         "Ja = eine Adresse aufrufen (lesen oder schreiben)."),
    code("Wache", [-180, 100], WACHE_JS),
    wenn("Ausfuehren?", [60, 100], "={{ $json.bereit }}",
         "Nein = Trockenlauf (Schreiben ohne Bestaetigung) -> nur melden."),
    wenn("Nur lesen?", [300, 60], "={{ $('Wache').first().json.methode === 'GET' }}",
         "Ja = GET ohne Koerper, sonst mit Koerper."),
    http("Lesen", [540, -60], "GET", "={{ '" + AZ + "' + $('Wache').first().json.pfad }}",
         None, AZ_KOPF, "Liest eine Adresse des Senders."),
    http("Schreiben", [540, 220], "={{ $('Wache').first().json.methode }}",
         "={{ '" + AZ + "' + $('Wache').first().json.pfad }}",
         "={{ $('Wache').first().json.koerper || '{}' }}", AZ_KOPF,
         "Aendert etwas am Sender (nur mit Bestaetigung)."),
    code("Aufruf Ergebnis", [800, 60], AUFRUF_ERGEBNIS_JS),
    code("Trockenlauf", [300, 320], TROCKENLAUF_JS),

    # --- Ueberblick (wenn weder Adresssuche noch Aufruf)
    http("Anlagen", [-180, 420], "GET", API_ADMIN + "/stations", None, AZ_KOPF, "Alle Anlagen."),
    http("Zustand", [60, 420], "GET", API + "/status", None, AZ_KOPF, "Laeuft der Sendeteil?"),
    http("Wiedergabelisten", [300, 420], "GET", API + "/playlists", None, AZ_KOPF,
         "Wiedergabelisten der Anlage 1."),
    code("Ueberblick", [540, 420], UEBERSICHT_JS),
], {
    "Eingang": {"main": [[{"node": "Adressen suchen?", "type": "main", "index": 0}]]},
    "Adressen suchen?": {"main": [
        [{"node": "Beschreibung holen", "type": "main", "index": 0}],
        [{"node": "Aufruf?", "type": "main", "index": 0}]]},
    "Beschreibung holen": {"main": [[{"node": "Adressen finden", "type": "main", "index": 0}]]},
    "Aufruf?": {"main": [
        [{"node": "Wache", "type": "main", "index": 0}],
        [{"node": "Anlagen", "type": "main", "index": 0}]]},
    "Wache": {"main": [[{"node": "Ausfuehren?", "type": "main", "index": 0}]]},
    "Ausfuehren?": {"main": [
        [{"node": "Nur lesen?", "type": "main", "index": 0}],
        [{"node": "Trockenlauf", "type": "main", "index": 0}]]},
    "Nur lesen?": {"main": [
        [{"node": "Lesen", "type": "main", "index": 0}],
        [{"node": "Schreiben", "type": "main", "index": 0}]]},
    "Lesen": {"main": [[{"node": "Aufruf Ergebnis", "type": "main", "index": 0}]]},
    "Schreiben": {"main": [[{"node": "Aufruf Ergebnis", "type": "main", "index": 0}]]},
    "Anlagen": {"main": [[{"node": "Zustand", "type": "main", "index": 0}]]},
    "Zustand": {"main": [[{"node": "Wiedergabelisten", "type": "main", "index": 0}]]},
    "Wiedergabelisten": {"main": [[{"node": "Ueberblick", "type": "main", "index": 0}]]},
}))

# ------------------------------------------------------------------ der Bot

EINGABE_JS = r"""
// Telegram-Update vereinheitlichen (Nachricht, Sprachnachricht, Knopfdruck).
const roh = $input.first().json ?? {};
const b = (roh.body && typeof roh.body === 'object') ? roh.body : null;
const quelle = (b && (b.message || b.callback_query || b.edited_message)) ? b : roh;
const istTest = !!(roh.body || roh.webhookUrl);
const schluessel = String((roh.query && roh.query.schluessel) || quelle.schluessel || '');
const cq = quelle.callback_query || null;
const m = quelle.message || (cq && cq.message) || {};
const von = (cq && cq.from) || m.from || {};
const stimme = m.voice || m.audio || null;
// Knopfdruck aus der Auswahlliste: Die Kennung wird zur Nummer - der weitere
// Ablauf behandelt sie wie eine getippte "2" (das Werkzeug loest die Nummer aus
// seiner gemerkten Liste auf). Der Text der Bot-Nachricht ist hier NICHT gemeint.
// Alte Kennungen ("w:2") werden mitgelesen, damit alte Pruefskripte nicht stumm
// das Falsche testen.
const knopf = cq ? String(cq.data || '') : '';
const knopfNummer = (knopf.match(/^w:?(\d{1,2})$/) || [])[1] || '';
return [{ json: {
  chatId: String((m.chat && m.chat.id) !== undefined ? m.chat.id : ''),
  text: cq ? knopfNummer : String(m.text || '').trim(),
  istSprache: !!stimme,
  stimmeDateiId: stimme ? String(stimme.file_id || '') : '',
  stimmeTestUrl: (stimme && stimme.test_url) ? String(stimme.test_url) : '',
  messageId: (cq && cq.message ? cq.message.message_id : m.message_id) || null,
  userName: [von.first_name, von.last_name].filter(Boolean).join(' ') || von.username || '',
  isCallback: !!cq,
  istTest, schluessel,
  eingang: new Date().toISOString(),
} }];
"""

ZUGANG_JS = r"""
// Nur der Betreiber darf den Sender steuern.
const d = $getWorkflowStaticData('global');
if (!Array.isArray(d.erlaubte)) d.erlaubte = (d.erlaubte ? [d.erlaubte] : []);
const j = $json;
if (j.istTest && (!d.testSchluessel || j.schluessel !== d.testSchluessel)) {
  return [{ json: Object.assign({}, j, { erlaubt: false, neuerBetreiber: false }) }];
}
let erlaubt = false;
let neu = false;
if (d.erlaubte.length === 0 && j.chatId) {
  d.erlaubte.push(j.chatId);
  erlaubt = true;
  neu = true;
} else {
  erlaubt = d.erlaubte.includes(j.chatId);
}
return [{ json: Object.assign({}, j, { erlaubt, neuerBetreiber: neu }) }];
"""

TRANSKRIPT_JS = r"""
// Sprachnachricht: nur den Text weitergeben, deuten laesst der Agent deuten.
const felder = $('Eingabe').item.json;
const roh = $input.first().json || {};
if (roh.error) {
  return [{ json: Object.assign({}, felder, { text: '',
    antwort: '\u26a0\ufe0f Die Sprachnachricht konnte nicht verarbeitet werden.' }) }];
}
const sauber = String(roh.text || '').replace(/\s+/g, ' ').trim();
if (!sauber) {
  return [{ json: Object.assign({}, felder, { text: '',
    antwort: '\U0001f3a7 Ich habe nichts verstanden - bitte nochmal sprechen.' }) }];
}
return [{ json: Object.assign({}, felder, { text: sauber, gehoert: sauber }) }];
"""

GEHOERT_JS = r"""
const j = $json;
return [{ json: { chatId: j.chatId || $('Eingabe').item.json.chatId,
  antwort: '\U0001f3a7 Verstanden: \u00bb' + (j.gehoert || '') + '\u00ab' } }];
"""

KEIN_ZUGANG_JS = r"""
const j = $json;
return [{ json: Object.assign({}, j, { antwort: j.neuerBetreiber
  ? '\u2705 Diesen Chat als Betreiber eingetragen. Schreib einfach, was laufen soll.'
  : '\u26d4 Kein Zugang. Dieser Bot ist auf den Betreiber beschraenkt.' }) }];
"""

KEIN_TEXT_JS = r"""
// Nachricht ohne Text (Knopfdruck, Bild, Sticker) - nichts zu steuern.
const j = $('Eingabe').first().json;
return [{ json: { chatId: j.chatId,
  antwort: 'Das habe ich nicht verstanden. Schreib zum Beispiel: spiele Juliet von Modern Talking.',
  tastatur: null } }];
"""

ANTWORT_JS = r"""
// Antwort fuer Telegram aufbereiten (HTML, keine Sternchen).
let text = String($json.antwort || '').trim();
if (!text) text = 'Das habe ich nicht verstanden. Sag zum Beispiel: spiele Juliet von Modern Talking.';
text = text.replace(/\*\*/g, '').replace(/^#+\s*/gm, '').replace(/`/g, '');
return [{ json: { chatId: $json.chatId || $('Eingabe').first().json.chatId, antwort: text,
  tastatur: $json.tastatur || null } }];
"""

# ============================================================ Stufe 1: Analyse

PLANEN_SYSTEM = """Du zerlegst die Anweisung des Betreibers in einzelne Befehle. Antworte NUR mit
JSON - kein Text davor oder danach, keine Erklaerung, keine Code-Umrandung.

Format:
{"befehle": [
  {"art": "spielen", "suchtext": "Interpret und/oder Titel", "einreihen": false},
  {"art": "richtung", "richtung": "party"},
  {"art": "programm", "frage": "was laeuft gerade"},
  {"art": "verwalten", "auftrag": "Wiedergabeliste Test anlegen", "bestaetigt": false}
]}

REGELN
1. Ein Befehl pro Aufgabe, in der Reihenfolge, in der sie genannt wurden.
2. art=spielen: konkreter Titel oder Interpret. einreihen=true nur bei "danach", "spaeter",
   "anschliessend", "hinterher" - sonst false.
3. art=richtung: Stimmung, Genre oder Jahrzehnt. Uebersetze auf EINES dieser Worte: party, dance,
   rock, pop, metal, hiphop, electronic, disco, punk, grunge, folk, blues, jazz, klassik,
   schlager, deutschrap, ruhig, hart, 90er, 80er. "peppig"/"flott"/"Tempo" -> party,
   "entspannt"/"ruhig" -> ruhig, "hart"/"laut" -> metal. Ein Stimmungswunsch bleibt IMMER
   art=richtung, auch wenn er beilaeufig klingt ("mach mal was peppiges" -> party).
4. art=programm: Fragen zum Programm ("was laeuft", "was kommt danach", "wie viele Zuhoerer").
5. art=verwalten: alles am Sender selbst (Wiedergabelisten, Anlagen, Nutzer, Rollen, Sicherungen,
   Einstellungen, Berichte, Medien, Streamer). Schreibe den Auftrag vollstaendig in eigenen Worten
   in "auftrag".
6. bestaetigt=true NUR, wenn der Betreiber gerade ausdruecklich zugestimmt hat ("ja", "mach das",
   "ok, leg an") und sich das auf einen Auftrag bezieht, den der Bot vorher zur Bestaetigung
   vorgelegt hat. Sonst false. Nimm den Auftrag dann wortgleich aus deiner letzten Antwort
   (oben mitgeschickt) - schreibe nicht nur "bestaetigen".
7. Verhoerte Namen dem naechstliegenden Interpreten zuordnen. Nichts erfinden.
8. Mehrere Schritte einer zusammenhaengenden Aufgabe ("lege eine Wiedergabeliste an und fuelle sie
   mit Rock") bleiben EIN Befehl art=verwalten - nicht zerlegen.
9. Steht in der Nachricht keine Aufgabe, gib {"befehle": []} zurueck.

/no_think"""

BEFEHLE_LESEN_JS = r"""
// Die Antwort der Analyse in einzelne Befehle zerlegen. Klappt das nicht, wird der
// Text als ein Befehl weitergereicht (dann uebernimmt der Ersatzweg) - ein Auftrag
// darf nicht daran scheitern, dass das Modell kein sauberes JSON liefert.
const eingang = $('Eingabe').first().json;
const roh = String(($json && ($json.output || $json.text)) || '').trim();

function zerlegen(text) {
  const start = text.indexOf('{');
  const ende = text.lastIndexOf('}');
  if (start === -1 || ende <= start) return null;
  try {
    const j = JSON.parse(text.slice(start, ende + 1));
    return Array.isArray(j.befehle) ? j.befehle : null;
  } catch (e) { return null; }
}

const d = $getWorkflowStaticData('global');
d.planVersuche = 0;
d.lauf = { befehle: [], fehler: '' };

let befehle = zerlegen(roh);
if (!befehle) {
  // Kein brauchbares JSON: den Text selbst als Befehl nehmen, ohne Sprachmodell
  // ausfuehrbar (art=direkt). Vorher die Befehlswoerter wegschneiden, sonst sucht
  // das Radio nach "spiele" und "von" und liefert irgendwelche Titel.
  d.lauf.fehler = roh ? 'Analyse unlesbar' : (roh === '' ? 'Analyse lieferte nichts' : 'Analyse fehlgeschlagen');
  const rohText = String(eingang.text || '').trim();
  const einreihen = /(danach|anschliessend|hinterher|spaeter|anschliessend)/i.test(rohText);
  const sauber = rohText
    .replace(/\b(bitte|mal|doch|sofort|gleich|jetzt|danach|anschliessend|hinterher|spaeter|einmal)\b/gi, ' ')
    .replace(/^\s*(spiele|spiel|leg|lege|mach|setz|setze|pack|starte|nimm|will|moechte|ich)\s+/i, '')
    .replace(/^\s*(mir|mal)\s+/i, '')
    .replace(/^\s*(was|etwas|was von|was fuer)\s+/i, '')
    .replace(/\s+/g, ' ')
    .trim();
  befehle = [{ art: 'direkt', suchtext: sauber || rohText, einreihen: einreihen }];
}
if (!befehle.length) {
  // Kein Auftrag: ohne Sprachmodell, ohne Schleife und ohne Zustandsabfrage antworten.
  d.lauf = { befehle: [], fehler: '', ohneKi: true, schlicht: true, leer: true };
  return [{ json: { chatId: eingang.chatId, leer: true, anzahl: 0 } }];
}

const ausgabe = [];
befehlSchleife:
for (let i = 0; i < befehle.length; i += 1) {
  const b = befehle[i] || {};
  const art = String(b.art || '').toLowerCase();
  if (!['spielen', 'richtung', 'programm', 'verwalten', 'direkt'].includes(art)) continue;
  d.lauf.befehle.push({ nr: i + 1, art: art, befehl: b, ausgabe: '', ok: null, grund: '', versuche: 0 });
  ausgabe.push({ json: {
    chatId: eingang.chatId,
    text: eingang.text,
    nr: i + 1,
    anzahl: befehle.length,
    art: art,
    befehl: b,
  } });
}
if (!ausgabe.length) {
  return [{ json: { chatId: eingang.chatId, anzahl: 0, nr: 0, befehl: {},
    antwort: 'Ich habe darin keinen Auftrag erkannt.' } }];
}
return ausgabe;
"""

PLAN_MERKEN_JS = r"""
// Die Analyse hat nichts Brauchbares geliefert (das Modell antwortet gelegentlich
// leer). Nochmal versuchen und dabei den urspruenglichen Auftrag erneut vorlegen.
const d = $getWorkflowStaticData('global');
d.planVersuche = (d.planVersuche || 0) + 1;
const j = $('Auftrag').first().json;
return [{ json: Object.assign({}, j, { versuche: d.planVersuche }) }];
"""

AUFTRAG_JS = r"""
// Die letzte Antwort des Bots nur bei einer kurzen Zustimmung voranstellen - daran
// haengt "ja, mach das". Bei allen anderen Nachrichten wuerde sie die Analyse
// verwirren (ein Stimmungswunsch landete damit einmal bei "kein Auftrag").
const d = $getWorkflowStaticData('global');
const j = $json || {};
const text = String(j.text || '').trim();
const n = text.toLowerCase();
const zustimmung = /^(ja|j|jap|ok|okay|gerne|genau|richtig|passt|gut|los|mach das|mach es|mach weiter|ja bitte|ja gerne|ja mach|einverstanden|bestaetigt|bestätigt|bitte mach)\b/.test(n)
  && n.split(/\s+/).length <= 6;
const vorher = zustimmung ? String(d.letzteAntwort || '').trim() : '';
const auftrag = (vorher ? 'Deine letzte Antwort: ' + vorher + '\n' : '') + text;
return [{ json: Object.assign({}, j, { auftrag: auftrag }) }];
"""

# --------------------------------------------------- Stufe 0: Kurzbefehl ohne KI

# Einfache Befehle (Liedwunsch, naechster Titel, Pause, Neustart, Status) laufen
# ohne Sprachmodell. Die Regeln sind an einer Beispielsammlung geprueft (2026-09-20);
# was nicht sicher erkannt wird, geht unveraendert an die Analyse.
KURZ_JS = r"""
// Vorschaltstufe ohne Sprachmodell. Erkannt werden:
//   wunsch      "spiele X", "wechsel song auf: X", "danach X", "X bitte"
//   steuerung   "wechsel song/naechster", "weiter", "pause", "lauter",
//               "sender neu starten/starten/stoppen"
//   status      "was laeuft", "status", "wie viele hoeren zu", Fehlermeldungen
// Alles andere (Verwaltung, Richtungen wie "was peppiges", mehrere Auftraege)
// geht unveraendert an die Analyse.
const eingang = $json || {};
const d = $getWorkflowStaticData('global');
const roh = String(eingang.text || '');

function norm(t) {
  return String(t || '').toLowerCase()
    .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
    .replace(/[^a-z0-9: ]+/g, ' ').replace(/\s+/g, ' ').trim();
}

const STEUER = [
  ['skip', /^(wechsel|wechsle|aendere|naechst\w*|next|skip|ueberspring\w*|spring|weiter zum naechsten|titel wechseln|song wechseln|mach den naechsten|zum naechsten)\b[\w\s:]{0,14}$/],
  ['skip', /^(song|titel|lied|track)\s*(wechseln|ueberspringen|vor|skip)$/],
  ['play', /^(weiter|weiter spielen|play|play weiter|abspielen|fortsetzen|weiterlaufen|mach weiter|spiel weiter)\b[\w\s]{0,12}$/],
  ['pause', /^(pause|pausieren|anhalten|halt|stopp|stop|unterbrechen|kurz pause|musik aus)\b[\w\s]{0,6}$/],
  ['lautstaerke', /^(lauter|leiser|laut|leise|volume|volumen|lautstaerke|ton lauter|ton leiser|mach lauter|mach leiser|leiser machen|lauter machen)\b[\w\s]{0,10}$/],
  ['restart', /^(neustart|restart|sender neu starten|radio neu starten|stream neu starten|starte den sender neu|starte den stream neu|sender neustarten|alles neu starten|neu starten)\b[\w\s]{0,12}$/],
  ['start', /^(sender starten|stream starten|radio starten|starte den sender|starte den stream|sender an|radio an|lauf wieder|start)\b[\w\s]{0,10}$/],
  ['stop', /^(sender stoppen|stream stoppen|radio stoppen|sender aus|radio aus|stream aus|alles stoppen|sender abschalten)\b[\w\s]{0,10}$/],
];
const STATUS = /^(was laeuft|was laeuft gerade|was spielt|welcher (song|titel|interpret) laeuft|was ist das fuer ein (song|titel)|status|zustand|sender status|wie ist der zustand|laeuft der (sender|stream|das radio)|laeuft das radio|laeuft der stream|wie viele (hoeren|hoerer|zuhoerer|leute|menschen)|wieviele (hoeren|hoerer|zuhoerer|leute)|wer hoert|wie ist die auslastung|programm|was kommt danach|welcher titel kommt)\b/;
const FEHLER = /\b(fehler|problem|stoerung|offline|ausgefallen|abgestuerzt|geht nicht|laeuft nicht|funktioniert nicht|klappt nicht|spinnt|haengt|kein ton|keine verbindung|down|tot)\b/;
const WUNSCH_VORN = /^(spiele|spiel|leg|lege|mach|setz|setze|pack|starte|wechsel|wechsle|aendere|nimm|hoere|hor|zeig|ich will|ich moechte)\b\s*(mal |mir |bitte |doch )*/;
const WUNSCH_HINTEN = /^(danach|danach mal|spaeter|anschliessend|hinterher|als naechstes)\b\s*(mal |bitte )*/;
const WUNSCH_SUFFIX = /^[\w\s:]{2,40}(bitte|mal)$/;
const VERWALTUNG = /\b(wiedergabeliste|playlist|anlage|anlegen|erstelle|erstellen|loesche|loeschen|entferne|nutzer|benutzer|konto|rolle|rollen|sicherung|backup|einstellung|einstellungen|bericht|report|berichte|medien|mount|streamer|webhook|speicher|zertifikat|passwort|api schluessel|zertifikate)\b/;
const MEHRFACH = /\bund\b.*\b(danach|dann|spaeter|anschliessend|hinterher)\b/;
// Stimmung, Genre, Jahrzehnt - ohne Sprachmodell auf eine Richtung des
// Katalogdienstes abgebildet (Wortliste aus /genre/liste).
const RICHTUNG = {
  peppig: 'party', peppiges: 'party', peppige: 'party', flott: 'party', flottes: 'party',
  tempo: 'party', abgehen: 'party', party: 'party', partymusik: 'party', tanzbar: 'party',
  tanzmusik: 'party', gutelaune: 'party', froehlich: 'party',
  ruhig: 'ruhig', ruhiges: 'ruhig', ruhige: 'ruhig', entspannt: 'ruhig',
  entspanntes: 'ruhig', chillig: 'chillig', chill: 'chillig', sanft: 'ruhig', locker: 'ruhig',
  langsam: 'langsam', romantisch: 'romantisch', liebe: 'liebe', liebeslieder: 'liebe',
  traurig: 'traurig', trauriges: 'traurig', balladen: 'balladen', ballade: 'ballade',
  hart: 'hart', hartes: 'hart', laut: 'hart', lautes: 'hart', heftig: 'hart',
  aggressiv: 'aggressiv', haerte: 'haerte',
  rock: 'rock', rockig: 'rock', rockiges: 'rock', rocknroll: 'rocknroll',
  pop: 'pop', poppig: 'pop', metal: 'metal', metallisch: 'metal', hardrock: 'hardrock',
  disco: 'disco', eurodisco: 'eurodisco', dance: 'dance', house: 'house', trance: 'trance',
  techno: 'techno', electronic: 'electronic', elektro: 'elektro',
  hiphop: 'hiphop', rap: 'rap', deutschrap: 'deutschrap', germanrap: 'germanrap',
  punk: 'punk', grunge: 'grunge', gothic: 'gothic', dark: 'dark', indie: 'indie',
  jazz: 'jazz', blues: 'blues', soul: 'soul', funk: 'funk', reggae: 'reggae', ska: 'ska',
  klassik: 'klassik', klassisch: 'klassisch', schlager: 'schlager', folk: 'folk',
  country: 'country', oldies: 'oldies', deutsch: 'deutsch', deutsche: 'deutsch',
  ndh: 'ndh', mittelalter: 'mittelalter', alternative: 'alternative', charts: 'charts',
  '80er': '80er', '90er': '90er', '70er': '70er', achtziger: '80er', neunziger: '90er',
};
// Fuellwoerter, die neben einem Stimmungswort stehen duerfen ("was Peppiges").
const FUELL = ['was', 'etwas', 'irgendwas', 'mal', 'mir', 'bitte', 'doch', 'musik', 'zeug',
  'sachen', 'kram', 'richtung', 'sorte', 'thema', 'aus', 'fuer', 'mit', 'ein', 'eine', 'einen',
  'der', 'die', 'das', 'den', 'dem', 'sommer', 'schnell'];
const ZU_VIEL = ['raus', 'rein', 'weg', 'runter', 'ab', 'aus', 'alles', 'es', 'das', 'die', 'den',
  'dem', 'der', 'sie', 'ihn', 'ihm', 'nochmal', 'genau', 'richtig', 'wieder', 'jetzt'];

// Fuellwoerter und Befehlsreste wegschneiden: "wechsel song auf: X" -> "X".
function saeubern(rest) {
  let r = norm(rest);
  for (let i = 0; i < 3; i += 1) {
    r = r.trim();
    r = r.replace(/^(den|die|das|dem|ein|einen|der)\s+(song|titel|lied|track|musik|stueck)\b/, ' ');
    r = r.replace(/^(song|titel|lied|track|musik|stueck)\b/, ' ');
    r = r.replace(/^(auf|zu|an|mit|in|bei)\b\s*:?\s*/, ' ');
    r = r.replace(/^(mir|mal|bitte|doch|eben|kurz|noch|sofort|gleich|jetzt|schnell|denn)\b\s*/, ' ');
    r = r.replace(/^(was|etwas|irgendwas)\b\s*(von|fuer|aus|mit)?\s*/, ' ');
    r = r.replace(/^(von|fuer|aus)\b\s*/, ' ');
    r = r.replace(/\s+(auf|an|bitte|mal|sofort|gleich|jetzt|zu|hoeren|hoere|spielen|laufen|anhoeren|raus|rein)\b\s*\.?$/, ' ');
  }
  return r.replace(/\s+/g, ' ').replace(/^[ :-]+|[ :-]+$/g, '');
}

// Erkannt: Merker schreiben (ohneKi/schlicht) und das Element fuer die Schleife bauen.
function erkannt(art, befehl) {
  d.lauf = { befehle: [{ nr: 1, art: befehl.art, befehl: befehl, ausgabe: '', ok: null,
    grund: '', versuche: 0 }], fehler: '', ohneKi: true, schlicht: true };
  return [{ json: { chatId: eingang.chatId, text: eingang.text, nr: 1, anzahl: 1,
    art: befehl.art, befehl: befehl, kurz: art } }];
}

const n = norm(roh);
if (!n) return [{ json: Object.assign({}, $json, { kurz: null }) }];
const kern = n.replace(/^((bitte|mal|eben|schnell|jetzt|denn|den|die|das|mir|noch)\s+)+/, '');

for (const paar of STEUER) {
  if (paar[1].test(n) || paar[1].test(kern)) {
    return erkannt('steuerung', { art: 'steuerung', steuerung: paar[0] });
  }
}
if (STATUS.test(n)) {
  return erkannt('status', { art: 'direkt', frage: 'was laeuft gerade' });
}

// Auswahlliste: getippte Nummer oder angetippter Knopf (beides wird zu "2").
if (/^\d{1,2}$/.test(n)) {
  return erkannt('wunsch', { art: 'direkt', suchtext: n, einreihen: false });
}

// Stimmung pur ("was Peppiges", "mal was Ruhiges") - ohne Sprachmodell auf eine
// Richtung abgebildet. Bleibt neben dem Stimmungswort nur Fuellstoff uebrig,
// ist es kein Titelwunsch ("rock von nickelback" bleibt dagegen bei der KI).
const ohneVerb = n.replace(WUNSCH_VORN, ' ').replace(WUNSCH_HINTEN, ' ');
const stimmungWorte = ohneVerb.split(' ').filter((w) => w && FUELL.indexOf(w) < 0
  && !/^(spiele|spiel|leg|lege|mach|setz|setze|pack|starte|wechsel|wechsle|aendere|nimm|hoere|hor|zeig|ich|will|moechte|mir|bitte)$/.test(w));
if (stimmungWorte.length === 1 && RICHTUNG[stimmungWorte[0]]) {
  return erkannt('richtung', { art: 'direkt', richtung: RICHTUNG[stimmungWorte[0]] });
}

// Wunsch: nur wenn kein Verwaltungsauftrag, kein Doppelauftrag und kein Stimmungswunsch.
if (!MEHRFACH.test(n) && !VERWALTUNG.test(n)) {
  const hinten = WUNSCH_HINTEN.test(n);
  let rest = null;
  const vorn = n.match(WUNSCH_VORN);
  if (vorn) rest = n.slice(vorn[0].length);
  else if (hinten) rest = n.slice(n.match(WUNSCH_HINTEN)[0].length);
  else if (WUNSCH_SUFFIX.test(n) && n.split(' ').length <= 5 && !FEHLER.test(n)) {
    rest = n.replace(/\s*(bitte|mal)$/, '');
  }
  if (rest !== null) {
    const s = saeubern(rest);
    const zahl = /^\d{1,2}$/.test(s);
    const worte = s.split(' ');
    // Stimmungswunsch ("was Peppiges") ohne Sprachmodell auf eine Richtung abbilden.
    // Nur wenn ausser dem Stimmungswort nichts uebrig bleibt - "rock von nickelback"
    // ist dagegen ein Titelwunsch.
    if (worte.length && worte.length <= 3) {
      const ohneFuell = worte.filter((w) => FUELL.indexOf(w) < 0);
      if (ohneFuell.length === 1 && RICHTUNG[ohneFuell[0]]) {
        return erkannt('richtung', { art: 'direkt', richtung: RICHTUNG[ohneFuell[0]] });
      }
    }
    if ((s.length >= 2 || zahl) && ZU_VIEL.indexOf(s) < 0 && s.indexOf(' und ') < 0) {
      return erkannt('wunsch', { art: 'direkt', suchtext: s, einreihen: hinten });
    }
  }
}

// Fehlermeldung: kurzer Bericht ohne Auftragswort -> Statusbericht statt Modell.
if (FEHLER.test(n) && n.split(' ').length <= 8) {
  return erkannt('status', { art: 'direkt', frage: 'was laeuft gerade' });
}
// Nicht erkannt: das Element UNVERAENDERT weitergeben - daran haengt der Auftragstext
// fuer die Analyse (fehlte er, bekam das Modell "undefined" und lieferte keinen Plan).
return [{ json: Object.assign({}, $json, { kurz: null }) }];
"""

STEUERUNG_ANTWORT_JS = r"""
// Antwort auf einen Kurzbefehl (Basissteuerung) - ohne Sprachmodell.
const d = $getWorkflowStaticData('global');
const item = $('Schleife').first().json || {};
const aktion = String((item.befehl || {}).steuerung || '');
const r = $json || {};
const fehler = !!r.error || r.success === false;

let text = '';
if (aktion === 'pause') {
  text = 'Am Sender gibt es kein Pausieren - anhalten kann jedes Geraet selbst. '
    + 'Sag "weiter", wenn der Sendeteil weiterspielen soll, oder "naechster Titel".';
} else if (aktion === 'lautstaerke') {
  text = 'Die Lautstaerke stellt jedes Geraet selbst ein - am Sender laesst sie sich nicht aendern.';
} else if (aktion === 'skip') {
  text = fehler ? 'FEHLER: Der Sender nimmt den Sprung nicht an.' : 'Naechster Titel laeuft an.';
} else if (aktion === 'play') {
  text = fehler ? 'FEHLER: Der Sendeteil laeuft nicht an.' : 'Der Sendeteil laeuft.';
} else if (aktion === 'start') {
  text = fehler ? 'FEHLER: Der Sendeteil liess sich nicht starten.' : 'Der Sendeteil ist gestartet.';
} else if (aktion === 'stop') {
  text = fehler ? 'FEHLER: Der Sendeteil liess sich nicht stoppen.' : 'Der Sendeteil ist gestoppt.';
} else if (aktion === 'restart') {
  text = fehler ? 'FEHLER: Der Sendeteil liess sich nicht neu starten.'
    : 'Der Sendeteil wurde neu gestartet.';
} else {
  text = fehler ? 'FEHLER: Der Befehl kam nicht durch.' : 'Erledigt.';
}

const nr = Number(item.nr || 1);
const eintrag = (d.lauf && d.lauf.befehle || []).find((x) => x.nr === nr);
if (eintrag) {
  eintrag.ausgabe = text;
  eintrag.ok = !fehler;
  eintrag.versuche = (eintrag.versuche || 0) + 1;
}
return [{ json: { nr: nr, fertig: true } }];
"""

# ======================================================== Stufe 2: Ausfuehrung

AUSFUEHREN_SYSTEM = """Du fuehrst genau EINEN Befehl des Betreibers am Internetradio
"Deadline Beats" aus. Der Betreiber ist der einzige Nutzer.

WERKZEUGE
- titel_suchen, richtung_suchen, was_laeuft: Musik und Programm. Diese Werkzeuge spielen selbst.
- azura_endpunkte, azura_aufruf, azura_ueberblick: der Sender selbst (Verwaltung).

REGELN
1. Fuehre den Befehl aus - erklaere ihn nicht.
2. Verwaltungsauftrag: erst azura_endpunkte (Adresse nachschlagen), dann azura_aufruf.
   Aendern (POST/PUT/DELETE) nur, wenn im Befehl "bestaetigt": true steht - sonst nur lesen
   bzw. den Trockenlauf melden und in der Antwort in einfachen Worten um Erlaubnis bitten
   ("Soll ich das anlegen?"). Keine Fachbegriffe wie "bestaetigt" oder Feldnamen nennen.
3. Antworte in EINEM kurzen deutschen Satz mit dem Ergebnis. Keine Dateipfade, keine Technik,
   keine Aufzaehlung der Werkzeuge.
4. Ging etwas schief, sag in einem Satz was.

/no_think"""

AUSFUEHREN_TEXT = ("={{ 'Befehl: ' + JSON.stringify($json.befehl) + '\\n/no_think' }}")

ERGEBNIS_SAMMELN_JS = r"""
// Ergebnis des Befehls am Merker festhalten.
const d = $getWorkflowStaticData('global');
const nr = Number($('Schleife').first().json.nr || 0);
const text = String(($json && ($json.output || $json.text)) || '').trim();
const eintrag = (d.lauf && d.lauf.befehle || []).find((x) => x.nr === nr);
if (eintrag) {
  eintrag.ausgabe = text || '(keine Ausgabe)';
  eintrag.versuche = (eintrag.versuche || 0) + 1;
  eintrag.auswahl = Array.isArray($json.auswahl) ? $json.auswahl : (eintrag.auswahl || []);
}
return [{ json: { nr: nr, fertig: true } }];
"""

ERSATZ_ANTWORT_JS = r"""
// Ergebnis des Ersatzwegs festhalten. Das Radio-Werkzeug antwortet mit "ergebnis",
// ein Sprachmodell mit "output" - beides beruecksichtigen.
const d = $getWorkflowStaticData('global');
const nr = Number($('Schleife').first().json.nr || 0);
const text = String(($json && ($json.ergebnis || $json.output || $json.text)) || '').trim();
const eintrag = (d.lauf && d.lauf.befehle || []).find((x) => x.nr === nr);
if (eintrag) {
  eintrag.ausgabe = text || '(keine Ausgabe)';
  eintrag.versuche = (eintrag.versuche || 0) + 1;
  eintrag.auswahl = Array.isArray($json.auswahl) ? $json.auswahl : (eintrag.auswahl || []);
}
return [{ json: { nr: nr, fertig: true } }];
"""

# ========================================================= Stufe 3: Pruefung

PRUEFEN_SYSTEM = """Du pruefst, ob die Befehle wirklich ausgefuehrt wurden. Antworte NUR mit JSON,
kein Text davor oder danach.

Format:
{"pruefung": [{"nr": 1, "ok": true, "grund": ""}]}

REGELN
1. ok=true, wenn die Ausgabe belegt, dass der Befehl ausgefuehrt wurde: der Titel laeuft, der
   Titel wurde eingereiht, die Auskunft wurde erteilt oder die Aenderung wurde bestaetigt.
2. Ein Trockenlauf ist KEIN Fehler, wenn der Befehl art=verwalten hat und "bestaetigt" false
   ist - genau so soll der Bot vor dem Aendern um Erlaubnis bitten. ok=true in diesem Fall.
3. ok=false bei Fehlermeldung oder Rueckfrage (der Bot muss den Nutzer etwas fragen, weil ihm
   eine Angabe fehlt). Dass der gemeldete Zustand des Senders dem Befehl widerspricht, zaehlt nur
   dann als Fehler, wenn die Ausgabe den gewuenschten Titel oder Interpreten auch nicht nennt -
   der Sender meldet den laufenden Titel verzoegert.
4. art=programm ist ok, sobald die Auskunft erteilt wurde.
4. "grund" ist ein kurzer deutscher Satz, warum es nicht geklappt hat (leer bei ok).
5. Fuer jeden Befehl genau ein Eintrag, dieselbe "nr".

/no_think"""

LAGE_JS = r"""
// Zustand des Senders als Beleg fuer die Pruefung.
const d = $getWorkflowStaticData('global');
const jetzt = $('Lage holen').first().json || {};
const wartend = $('Warteschlange holen').all().map((i) => i.json || {});
const song = (jetzt.now_playing && jetzt.now_playing.song) || {};
const naechste = ((jetzt.playing_next || {}).song || {}).text || '';
const inWarteschlange = wartend.map((x) => (x.song && x.song.text) || '').filter(Boolean);
const liste = (d.lauf && d.lauf.befehle) || [];
// Klarer Fehler: jede Ausgabe ist eine Fehlermeldung oder leer - dann braucht es
// kein Sprachmodell fuer das Urteil (Regelurteil in "Pruefung lesen").
const klarFehler = liste.length > 0 && liste.every((b) => {
  const a = String(b.ausgabe || '').trim();
  return !a || a === '(keine Ausgabe)' || /^(FEHLER|KEINE TREFFER|Es steht keine Auswahlliste|Die Nummer)/i.test(a);
});
return [{ json: {
  chatId: $('Eingabe').first().json.chatId,
  befehle: liste,
  ohneKi: !!(d.lauf && d.lauf.ohneKi),
  klarerFehler: klarFehler,
  lage: {
    laeuft: song.text || 'unbekannt',
    danach: naechste,
    warteschlange: inWarteschlange.slice(0, 5),
  },
} }];
"""

PRUEFUNG_LESEN_JS = r"""
// Ergebnis der Pruefung in den Merker schreiben und die fehlgeschlagenen Befehle
// fuer den Nachfass-Durchgang weitergeben.
//
// Das Sprachmodell urteilt. Liefert es nichts (leere Antwort, kein JSON), greift
// ein Regelurteil - sonst ginge ein misslungener Befehl als gelungen durch.
const d = $getWorkflowStaticData('global');
const roh = String(($json && ($json.output || $json.text)) || '').trim();
const liste = (d.lauf && d.lauf.befehle) || [];
const lage = ($('Befehle und Lage').first().json || {}).lage || {};
const STOERUNG = /fehler|nicht moeglich|konnte nicht|nicht gefunden|keine treffer|trockenlauf|rueckfrage|welchen|welche|unbekannt/i;

function zerlegen(text) {
  const start = text.indexOf('{');
  const ende = text.lastIndexOf('}');
  if (start === -1 || ende <= start) return null;
  try {
    const j = JSON.parse(text.slice(start, ende + 1));
    return Array.isArray(j.pruefung) ? j.pruefung : null;
  } catch (e) { return null; }
}

function worte(text) {
  return String(text || '').toLowerCase().split(/[^a-z0-9]+/).filter((w) => w.length > 2);
}

function urteil(b) {
  const a = String(b.ausgabe || '').trim();
  if (!a || a === '(keine Ausgabe)') return { ok: false, grund: 'keine Ausgabe' };
  const b2 = b.befehl || {};
  // Trockenlauf bei noch nicht bestaetigtem Verwaltungsauftrag ist der Regelfall.
  const trocken = b.art === 'verwalten' && b2.bestaetigt !== true && /trockenlauf/i.test(a);
  if (trocken) return { ok: true, grund: '' };
  if (STOERUNG.test(a)) return { ok: false, grund: a.slice(0, 150) };
  if (b.art === 'spielen') {
    const w = worte(b2.suchtext);
    const genannt = w.length && w.some((x) => String(a).toLowerCase().includes(x));
    // Nennt die Ausgabe den gewuenschten Titel, gilt der Befehl als erledigt - der
    // Sender meldet den laufenden Titel mit Verzoegerung.
    if (genannt) return { ok: true, grund: '' };
    if (b2.einreihen === true) {
      const wartend = (lage.warteschlange || []).join(' ').toLowerCase();
      if (w.length && !w.some((x) => wartend.includes(x))) {
        return { ok: false, grund: 'nicht in der Warteschlange' };
      }
    } else {
      const laeuft = String(lage.laeuft || '').toLowerCase();
      if (w.length && !w.some((x) => laeuft.includes(x))) {
        return { ok: false, grund: 'der Sender spielt "' + (lage.laeuft || '?') + '"' };
      }
    }
  }
  return { ok: true, grund: '' };
}

const pruefung = zerlegen(roh);
const gelesen = {};
for (const e of pruefung || []) gelesen[Number(e.nr)] = e;

for (const b of liste) {
  const e = gelesen[Number(b.nr)];
  if (e) {
    b.ok = e.ok === true;
    b.grund = String(e.grund || '');
  } else {
    const u = urteil(b);
    b.ok = u.ok;
    b.grund = u.grund;
  }
  const leer = !String(b.ausgabe || '').trim() || String(b.ausgabe || '').trim() === '(keine Ausgabe)';
  if (b.ok && leer) { b.ok = false; b.grund = b.grund || 'keine Ausgabe'; }
  if (b.ok) b.grund = '';
}

const offen = (d.lauf && d.lauf.ohneKi)
  // Kurzbefehl (ohne Sprachmodell ausgefuehrt): Urteil nach Regeln, kein zweiter Versuch.
  ? []
  : liste.filter((b) => b.ok === false && (b.versuche || 0) < 2);
const ausgabe = offen.map((b) => ({ json: { chatId: $json.chatId, nr: b.nr, art: b.art,
  befehl: b.befehl, grund: b.grund, versuche: b.versuche || 0 } }));
return ausgabe.length ? ausgabe : [{ json: { chatId: $json.chatId, nr: 0, nichts_zu_tun: true } }];
"""

NACHTRAG_SAMMELN_JS = r"""
// Ergebnis des Nachfass-Durchgangs am Merker festhalten.
const d = $getWorkflowStaticData('global');
const item = $('Schleife 2').first().json;
const text = String(($json && ($json.output || $json.text)) || '').trim();
const eintrag = (d.lauf && d.lauf.befehle || []).find((x) => x.nr === Number(item.nr));
if (eintrag) {
  eintrag.ausgabe = text || '(keine Ausgabe)';
  eintrag.versuche = (eintrag.versuche || 0) + 1;
  // Der zweite Versuch ist der gueltige Stand - er ersetzt die erste Ausgabe.
  eintrag.ok = !!text.trim() && !/fehler|nicht moeglich|konnte nicht|nicht gefunden|keine treffer|welchen|welche/i.test(text);
  eintrag.grund = eintrag.ok ? '' : (text || eintrag.grund || '');
}
return [{ json: { nr: item.nr, fertig: true } }];
"""

ANTWORT_BAUEN_JS = r"""
// Zusammenfassung aller Befehle - Erfolg und Misserfolg getrennt.
const d = $getWorkflowStaticData('global');
const liste = (d.lauf && d.lauf.befehle) || [];
// schlicht = ohne Sprachmodell ausgefuehrt (Kurzbefehl): Antwort ohne Zeichen davor.
const schlicht = !!(d.lauf && d.lauf.schlicht);
const zeilen = [];
for (const b of liste) {
  const t = (b.ausgabe || '(keine Ausgabe)').replace(/[ \t]+/g, ' ').slice(0, 300);
  zeilen.push(schlicht ? t : ((b.ok === false ? '\u26a0\ufe0f ' : '\u2705 ') + t));
}
if (!zeilen.length) zeilen.push('Ich habe darin keinen Auftrag erkannt.');
const offen = liste.filter((b) => b.ok === false);
if (!schlicht && offen.length) {
  zeilen.push('Nicht erledigt: ' + offen.map((b) => 'Nr. ' + b.nr).join(', ')
    + ' - sag es noch einmal, dann versuche ich es anders.');
}
const fehler = (d.lauf && d.lauf.fehler) || '';
if (fehler) zeilen.push('(' + fehler + ')');
const gesamt = zeilen.join('\n');
// Auswahlliste als anklickbare Knoepfe: callback_data "w" + Nummer (kurz genug,
// Telegram erlaubt dort 1-64 Bytes). Der Knopfdruck kommt als Nummer zurueck.
const mitListe = liste.find((b) => Array.isArray(b.auswahl) && b.auswahl.length);
const tastatur = mitListe
  ? { inline_keyboard: mitListe.auswahl.map((t, i) => ([{
      text: String(t).slice(0, 60), callback_data: 'w' + (i + 1) }])) }
  : null;
// Fuer die naechste Nachricht merken: daran haengt "ja, mach das".
d.letzteAntwort = gesamt;
return [{ json: { chatId: $('Eingabe').first().json.chatId, antwort: gesamt,
  tastatur: tastatur } }];
"""

# ======================================================================= der Bot

bot = [
    n("Telegram Trigger", "n8n-nodes-base.telegramTrigger", 1.2, [-2400, 0],
      {"updates": ["message", "callback_query"], "additionalFields": {}},
      webhookId=nid(), credentials={"telegramApi": {"id": TG_CRED_ID, "name": TG_CRED_NAME}}),
    n("Test-Eingang", "n8n-nodes-base.webhook", 2, [-2400, 240],
      {"httpMethod": "POST", "path": "DEIN-WEBHOOK-PFAD", "responseMode": "lastNode", "options": {}},
      webhookId=nid(), notes="Nur zum Pruefen: nimmt eine Telegram-Nachricht als JSON entgegen."),
    code("Eingabe", [-2160, 100], EINGABE_JS),
    n("Sprachnachricht?", "n8n-nodes-base.if", 2.2, [-1960, -140], {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                   "typeValidation": "loose", "version": 2},
                       "combinator": "and",
                       "conditions": [{"id": nid(), "leftValue": "={{ $json.istSprache }}",
                                       "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true",
                                                    "singleValue": True}}]},
        "options": {}}),
    n("Datei holen", "n8n-nodes-base.httpRequest", 4.2, [-1760, -320], {
        "method": "GET", "url": TG + "/getFile", "sendQuery": True,
        "queryParameters": {"parameters": [{"name": "file_id", "value": "={{ $json.stimmeDateiId }}"}]},
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput", notes="Holt den Pfad der Sprachnachricht bei Telegram."),
    n("Audio laden", "n8n-nodes-base.httpRequest", 4.2, [-1560, -320], {
        "method": "GET",
        "url": "={{ $('Eingabe').item.json.stimmeTestUrl || ('https://api.telegram.org/file/bot'"
               + " + " + json.dumps(TG_TOKEN) + " + '/' + ($json.result ? $json.result.file_path : '')) }}",
        "options": {"timeout": 30000,
                    "response": {"response": {"responseFormat": "file",
                                              "outputPropertyName": "audio"}}},
    }, onError="continueRegularOutput",
       notes="Laedt die Audiodatei. Ueber den Testeingang darf stimme.test_url gesetzt werden."),
    n("Umwandeln", "n8n-nodes-base.httpRequest", 4.2, [-1360, -320], {
        "method": "POST", "url": WHISPER,
        "sendBody": True, "contentType": "multipart-form-data",
        "bodyParameters": {"parameters": [
            {"parameterType": "formBinaryData", "name": "file", "inputDataFieldName": "audio"},
            {"parameterType": "formData", "name": "language", "value": "de"},
        ]},
        "options": {"timeout": 120000},
    }, onError="continueRegularOutput",
       notes="Spracherkennung auf dem ai-Server (whisper.cpp large-v3 auf der MI50, CT 112)."),
    code("Transkript", [-1160, -320], TRANSKRIPT_JS),
    wenn("Verstanden?", [-960, -320], "={{ !!$json.text }}",
         "Ja = es gibt einen erkannten Text. Nein = Sprachnachricht nicht verwertbar."),
    code("Gehoert Text", [-760, -520], GEHOERT_JS),
    code("Zugang", [-1560, 100], ZUGANG_JS),
    n("Freigegeben?", "n8n-nodes-base.if", 2.2, [-1360, 100], {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                   "typeValidation": "loose", "version": 2},
                       "combinator": "and",
                       "conditions": [{"id": nid(), "leftValue": "={{ $json.erlaubt }}",
                                       "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true",
                                                    "singleValue": True}}]},
        "options": {}}),
    code("Kein Zugang", [-1160, 320], KEIN_ZUGANG_JS),
    wenn("Text da?", [-960, 100], "={{ !!($json.text || '').trim() }}",
         "Nein = Knopfdruck/Bild/Sticker ohne Text -> nichts zu steuern."),
    code("Kein Text", [-760, 320], KEIN_TEXT_JS),
    code("Auftrag", [-680, 0], AUFTRAG_JS),

    # ---------------------------------------- Stufe 0: Kurzbefehl (ohne Sprachmodell)
    code("Kurz?", [-480, -340], KURZ_JS),
    wenn("Kurzbefehl?", [-260, -340], "={{ !!$json.kurz }}",
         "Ja = einfacher Befehl, laeuft ohne Analyse direkt in die Ausfuehrung."),

    # ---------------------------------------------------- Stufe 1: Analyse
    n("Planen", "n8n-nodes-base.httpRequest", 4.2, [-480, 0], {
        "method": "POST", "url": OLLAMA_OAI_URL + "/chat/completions",
        "sendHeaders": True, "headerParameters": {"parameters": OLLAMA_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": modell_koerper(PLANEN_SYSTEM, "$json.auftrag + '\\n/no_think'", 0.2, 3000),
        "options": {"timeout": 120000},
    }, retryOnFail=True, maxTries=2, waitBetweenTries=3000, onError="continueRegularOutput",
       notes="Stufe 1: zerlegt die Anweisung in einzelne Befehle. Tut nichts am Sender."),
    code("Plan Antwort", [-280, -160], ANTWORT_AUSLESEN_JS),
    wenn("Plan da?", [-80, -300], "={{ String($json.output || '').trim().length > 10 }}",
         "Nein = das Modell hat nichts geliefert -> noch einmal planen."),
    code("Plan merken", [140, -460], PLAN_MERKEN_JS),
    wenn("Plan nochmal?", [340, -460], "={{ Number($json.versuche || 0) < 3 }}",
         "Ja = zweiter/dritter Anlauf, danach uebernimmt der Ersatzweg."),
    code("Befehle lesen", [-280, 0], BEFEHLE_LESEN_JS),
    wenn("Befehl da?", [-80, 160], "={{ !$json.leer }}",
         "Nein = kein Auftrag erkannt -> direkt antworten, ohne Schleife und ohne Modell."),

    # ------------------------------------------------ Stufe 2: Ausfuehrung
    n("Schleife", "n8n-nodes-base.splitInBatches", 3, [-60, 0], {
        "batchSize": 1, "options": {},
    }, notes="Befehl fuer Befehl."),
    n("Ausfuehren", "@n8n/n8n-nodes-langchain.agent", 2.2, [160, -140], {
        "promptType": "define",
        "text": AUSFUEHREN_TEXT,
        "options": {"systemMessage": AUSFUEHREN_SYSTEM},
        "hasOutputParser": False,
    }, retryOnFail=True, maxTries=2, waitBetweenTries=3000, onError="continueRegularOutput",
       notes="Fuehrt genau einen Befehl aus."),
    n("Sprachmodell Ausfuehren", "@n8n/n8n-nodes-langchain.lmChatOpenAi", 1.2, [-40, 340], {
        "model": {"__rl": True, "value": MODELL, "mode": "id"},
        "options": {"temperature": 0.2, "maxTokens": 3000},
    }, credentials={"openAiApi": {"id": OAI_CRED, "name": OAI_CRED_NAME}}),
    n("Ergebnis sammeln", "n8n-nodes-base.code", 2, [380, -140], {"jsCode": ERGEBNIS_SAMMELN_JS}),

    # --------------------------------------------------- Stufe 3: Pruefung
    n("Lage holen", "n8n-nodes-base.httpRequest", 4.2, [600, 100], {
        "method": "GET", "url": AZ + "/api/nowplaying/1",
        "sendHeaders": True, "headerParameters": {"parameters": AZ_KOPF},
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput", notes="Was laeuft gerade - Beleg fuer die Pruefung."),
    n("Warteschlange holen", "n8n-nodes-base.httpRequest", 4.2, [800, 100], {
        "method": "GET", "url": API + "/queue",
        "sendHeaders": True, "headerParameters": {"parameters": AZ_KOPF},
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput", notes="Was eingereiht ist - Beleg fuer die Pruefung."),
    code("Befehle und Lage", [1000, 100], LAGE_JS),
    wenn("Pruefen?", [1120, 260], "={{ !$json.ohneKi && !$json.klarerFehler }}",
         "Nein = Kurzbefehl oder klare Fehlermeldung: Regelurteil statt Sprachmodell."),
    n("Pruefen", "n8n-nodes-base.httpRequest", 4.2, [1220, 100], {
        "method": "POST", "url": OLLAMA_OAI_URL + "/chat/completions",
        "sendHeaders": True, "headerParameters": {"parameters": OLLAMA_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": modell_koerper(PRUEFEN_SYSTEM,
                                   "'Befehle und Ausgaben: ' + JSON.stringify($json.befehle) "
                                   "+ '\\nZustand des Senders: ' + JSON.stringify($json.lage) "
                                   "+ '\\n/no_think'", 0.1, 4000),
        "options": {"timeout": 120000},
    }, retryOnFail=True, maxTries=2, waitBetweenTries=3000, onError="continueRegularOutput",
       notes="Stufe 3: interpretiert die Ergebnisse und markiert Fehlgeschlagenes."),
    code("Pruefung Antwort", [1340, 260], ANTWORT_AUSLESEN_JS),
    code("Pruefung lesen", [1440, 100], PRUEFUNG_LESEN_JS),
    wenn("Nachfassen?", [1660, 100], "={{ !$json.nichts_zu_tun }}",
         "Ja = mindestens ein Befehl ist fehlgeschlagen -> zweiter Versuch."),
    n("Schleife 2", "n8n-nodes-base.splitInBatches", 3, [1880, 60], {
        "batchSize": 1, "options": {},
    }, notes="Nachfass-Durchgang, hoechstens ein zweiter Versuch je Befehl."),
    n("Nacharbeiten", "@n8n/n8n-nodes-langchain.agent", 2.2, [2100, -60], {
        "promptType": "define",
        "text": ("={{ 'Befehl: ' + JSON.stringify($json.befehl) + '\\nDer erste Versuch hat nicht "
                 "geklappt: ' + $json.grund + '\\nVersuche es erneut - wenn moeglich auf einem "
                 "anderen Weg. Antworte in einem kurzen deutschen Satz.\\n/no_think' }}"),
        "options": {"systemMessage": AUSFUEHREN_SYSTEM},
        "hasOutputParser": False,
    }, retryOnFail=True, maxTries=2, waitBetweenTries=3000, onError="continueRegularOutput",
       notes="Zweiter Versuch fuer einen fehlgeschlagenen Befehl."),
    n("Sprachmodell Nacharbeiten", "@n8n/n8n-nodes-langchain.lmChatOpenAi", 1.2, [2100, 340], {
        "model": {"__rl": True, "value": MODELL, "mode": "id"},
        "options": {"temperature": 0.3, "maxTokens": 3000},
    }, credentials={"openAiApi": {"id": OAI_CRED, "name": OAI_CRED_NAME}}),
    n("Nachtrag sammeln", "n8n-nodes-base.code", 2, [2320, -60], {"jsCode": NACHTRAG_SAMMELN_JS}),
    code("Antwort bauen", [2560, 100], ANTWORT_BAUEN_JS),
    code("Antwort", [2780, 100], ANTWORT_JS),
    n("Senden", "n8n-nodes-base.httpRequest", 4.2, [3000, 100], {
        "method": "POST", "url": TG + "/sendMessage",
        "sendHeaders": True, "headerParameters": {"parameters": JSON_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": ("={{ JSON.stringify(Object.assign({ chat_id: $json.chatId, text: $json.antwort,"
                     " parse_mode: 'HTML', disable_web_page_preview: true },"
                     " ($json.tastatur ? { reply_markup: $json.tastatur } : {}))) }}"),
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput", notes="Fehler beim Senden stoppt den Lauf nicht."),

    # --- Werkzeuge (Unterschnittstellen des Agenten)
    n("Werkzeug Titel suchen", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, [380, 420], {
        "name": "titel_suchen",
        "description": "Spielt einen Titel oder Interpreten. Eingabe: suchtext (Interpret und/oder "
                       "Titel) ODER eine Nummer aus der letzten Auswahlliste. Klarer Treffer: er "
                       "laeuft sofort. Mehrere verschiedene Titel: Antwort ist eine Liste (dann "
                       "nachfragen). einreihen=true reiht nur ein, ohne zu unterbrechen.",
        "source": "database",
        "workflowId": {"__rl": True, "value": W_WERKZEUG, "mode": "list",
                       "cachedResultName": W_WERKZEUG_NAME},
        "workflowInputs": {
            "mappingMode": "defineBelow",
            "value": {"suchtext": feld("suchtext", "Interpret und/oder Titel, z. B. Modern Talking Juliet. Oder eine Nummer aus der letzten Auswahlliste, z. B. 2"),
                      "einreihen": feld("einreihen", "true, wenn der Titel nur eingereiht werden soll (nicht sofort laufen)", "boolean", False)},
            "matchingColumns": [],
            "schema": [{"id": "suchtext", "displayName": "suchtext", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "einreihen", "displayName": "einreihen", "required": False,
                        "defaultMatch": False, "display": True, "type": "boolean",
                        "canBeUsedToMatch": True, "removed": False}],
            "attemptToConvertTypes": False, "convertFieldsToString": False},
    }),
    n("Werkzeug Richtung suchen", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, [580, 420], {
        "name": "richtung_suchen",
        "description": "Spielt zur Stimmung, zum Genre oder Jahrzehnt den ersten passenden Titel. "
                       "Eingabe: richtung (party, dance, rock, metal, ruhig, hart, 90er, 80er ...). "
                       "einreihen=true reiht nur ein, ohne zu unterbrechen.",
        "source": "database",
        "workflowId": {"__rl": True, "value": W_WERKZEUG, "mode": "list",
                       "cachedResultName": W_WERKZEUG_NAME},
        "workflowInputs": {
            "mappingMode": "defineBelow",
            "value": {"richtung": feld("richtung", "Stimmung, Genre oder Jahrzehnt - eines von: party, dance, rock, pop, metal, hiphop, electronic, disco, punk, grunge, folk, blues, jazz, klassik, schlager, deutschrap, ruhig, hart, 90er, 80er"),
                      "einreihen": feld("einreihen", "true, wenn der Titel nur eingereiht werden soll (nicht sofort laufen)", "boolean", False)},
            "matchingColumns": [],
            "schema": [{"id": "richtung", "displayName": "richtung", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "einreihen", "displayName": "einreihen", "required": False,
                        "defaultMatch": False, "display": True, "type": "boolean",
                        "canBeUsedToMatch": True, "removed": False}],
            "attemptToConvertTypes": False, "convertFieldsToString": False},
    }),
    n("Werkzeug Was laeuft", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, [780, 420], {
        "name": "was_laeuft",
        "description": "Sagt, was gerade laeuft, wie lange noch, was danach kommt und wie viele "
                       "Zuhoerer da sind. Keine Eingabe.",
        "source": "database",
        "workflowId": {"__rl": True, "value": W_WERKZEUG, "mode": "list",
                       "cachedResultName": W_WERKZEUG_NAME},
        "workflowInputs": {
            "mappingMode": "defineBelow",
            "value": {"frage": feld("frage", "Was der Nutzer wissen will, z. B. welcher Titel laeuft, was danach kommt, wie viele Zuhoerer", "string", "was laeuft gerade")},
            "matchingColumns": [], "schema": [{"id": "frage", "displayName": "frage", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False}],
            "attemptToConvertTypes": False, "convertFieldsToString": False},
    }),
    n("Werkzeug Azura Adressen", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, [980, 420], {
        "name": "azura_endpunkte",
        "description": "Schlaegt Adressen der Senderschnittstelle nach (Stichwort, z. B. playlist, "
                       "user, backup, report, mount, webhook, storage, settings, media). Immer "
                       "zuerst benutzen, wenn du eine Verwaltungsaufgabe am Sender hast - Adressen "
                       "und Felder nie raten.",
        "source": "database",
        "workflowId": {"__rl": True, "value": W_AZURA, "mode": "list",
                       "cachedResultName": W_AZURA_NAME},
        "workflowInputs": {
            "mappingMode": "defineBelow",
            "value": {"suche": feld("suche", "Stichwort zur gesuchten Adresse, z. B. playlist")},
            "matchingColumns": [],
            "schema": [{"id": "suche", "displayName": "suche", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False}],
            "attemptToConvertTypes": False, "convertFieldsToString": False},
    }),
    n("Werkzeug Azura Aufruf", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, [1180, 420], {
        "name": "azura_aufruf",
        "description": "Ruft eine Schnittstelle des Senders auf (AzuraCast). Eingaben: methode "
                       "(GET liest, POST/PUT/DELETE aendern), pfad (voll, z. B. "
                       "/api/station/1/playlists), koerper (JSON, nur beim Schreiben), bestaetigt "
                       "(true, wenn der Betreiber das Aendern ausdruecklich erlaubt hat). Ohne "
                       "bestaetigt=true passiert beim Schreiben nichts - dann kommt nur ein "
                       "Trockenlauf zurueck.",
        "source": "database",
        "workflowId": {"__rl": True, "value": W_AZURA, "mode": "list",
                       "cachedResultName": W_AZURA_NAME},
        "workflowInputs": {
            "mappingMode": "defineBelow",
            "value": {"methode": feld("methode", "GET zum Lesen, POST/PUT/DELETE zum Aendern", "string", "GET"),
                      "pfad": feld("pfad", "Vollstaendiger Pfad mit /api/, z. B. /api/station/1/playlists"),
                      "koerper": feld("koerper", "JSON-Koerper beim Schreiben, z. B. {\"name\":\"Neu\",\"type\":\"default\"}", "string", ""),
                      "bestaetigt": feld("bestaetigt", "true, wenn der Betreiber das Aendern ausdruecklich erlaubt hat", "boolean", False)},
            "matchingColumns": [],
            "schema": [{"id": "methode", "displayName": "methode", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "pfad", "displayName": "pfad", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "koerper", "displayName": "koerper", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "bestaetigt", "displayName": "bestaetigt", "required": False,
                        "defaultMatch": False, "display": True, "type": "boolean",
                        "canBeUsedToMatch": True, "removed": False}],
            "attemptToConvertTypes": False, "convertFieldsToString": False},
    }),
    n("Werkzeug Azura Ueberblick", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, [1380, 420], {
        "name": "azura_ueberblick",
        "description": "Ueberblick ueber den Sender: Anlagen, ob Sendeteil und Ausgabe laufen, "
                       "Wiedergabelisten mit Titelzahl. Fuer Verwaltungsfragen (Zustand, Listen), "
                       "nicht fuer Musikwuensche.",
        "source": "database",
        "workflowId": {"__rl": True, "value": W_AZURA, "mode": "list",
                       "cachedResultName": W_AZURA_NAME},
        "workflowInputs": {
            "mappingMode": "defineBelow",
            "value": {"frage": feld("frage", "Was der Betreiber wissen will, z. B. Zustand oder Wiedergabelisten", "string", "Ueberblick")},
            "matchingColumns": [],
            "schema": [{"id": "frage", "displayName": "frage", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False}],
            "attemptToConvertTypes": False, "convertFieldsToString": False},
    }),
    n("Ersatz Werkzeug", "n8n-nodes-base.executeWorkflow", 1.2, [380, -320], {
        "source": "database",
        "workflowId": {"__rl": True, "value": W_WERKZEUG, "mode": "list",
                       "cachedResultName": W_WERKZEUG_NAME},
        "workflowInputs": {
            "mappingMode": "defineBelow",
            "value": {"suchtext": "={{ $json.befehl.suchtext || '' }}",
                      "richtung": "={{ $json.befehl.richtung || '' }}",
                      "frage": "={{ $json.befehl.frage || '' }}",
                      "einreihen": "={{ $json.befehl.einreihen === true }}"},
            "matchingColumns": [],
            "schema": [{"id": "suchtext", "displayName": "suchtext", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "richtung", "displayName": "richtung", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "einreihen", "displayName": "einreihen", "required": False,
                        "defaultMatch": False, "display": True, "type": "boolean",
                        "canBeUsedToMatch": True, "removed": False}],
            "attemptToConvertTypes": False, "convertFieldsToString": False},
        "mode": "once", "options": {"waitForSubWorkflow": True},
    }, notes="Ersatzweg ohne Sprachmodell: nur wenn die Analyse nichts Brauchbares lieferte."),
    n("Direkt oder KI?", "n8n-nodes-base.if", 2.2, [160, -320], {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                   "typeValidation": "loose", "version": 2},
                       "combinator": "and",
                       "conditions": [{"id": nid(),
                                       "leftValue": "={{ $json.art === 'direkt' }}",
                                       "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true",
                                                    "singleValue": True}}]},
        "options": {}}, notes="Ja = Analyse unbrauchbar, das Werkzeug spielt direkt."),
    n("Steuerung?", "n8n-nodes-base.if", 2.2, [160, -520], {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                   "typeValidation": "loose", "version": 2},
                       "combinator": "and",
                       "conditions": [{"id": nid(),
                                       "leftValue": "={{ $json.art === 'steuerung' }}",
                                       "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true",
                                                    "singleValue": True}}]},
        "options": {}}, notes="Ja = Basissteuerung des Senders (ohne Sprachmodell)."),
    n("Kurz Steuern", "n8n-nodes-base.httpRequest", 4.2, [380, -520], {
        "method": "={{ ['pause', 'lautstaerke'].includes($json.befehl.steuerung) ? 'GET' : 'POST' }}",
        "url": "={{ ['pause', 'lautstaerke'].includes($json.befehl.steuerung) ? '"
               + API + "/status' : '" + API + "/backend/' + $json.befehl.steuerung }}",
        "sendHeaders": True, "headerParameters": {"parameters": AZ_KOPF},
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput",
       notes="Naechster Titel, Start/Stop/Neustart - feste Adressen, kein Modell."),
    n("Steuerung Antwort", "n8n-nodes-base.code", 2, [600, -520], {"jsCode": STEUERUNG_ANTWORT_JS}),
    n("Ersatz Antwort", "n8n-nodes-base.code", 2, [600, -320], {"jsCode": ERSATZ_ANTWORT_JS}),

    # Zweiter Sende-Knoten nur fuer die kurzen Wege (kein Zugang, kein Text,
    # Sprachnachricht unverstaendlich, nur Transkript). Inhaltlich derselbe Aufruf
    # wie "Senden" - aber die Kanten laufen nicht quer ueber die ganze Flaeche.
    n("Senden (Kurzmeldung)", "n8n-nodes-base.httpRequest", 4.2, [600, -520], {
        "method": "POST", "url": TG + "/sendMessage",
        "sendHeaders": True, "headerParameters": {"parameters": JSON_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": ("={{ JSON.stringify({ chat_id: $json.chatId, text: $json.antwort,"
                     " parse_mode: 'HTML', disable_web_page_preview: true }) }}"),
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput",
       notes="Gleicher Aufruf wie 'Senden', nur fuer die kurzen Wege im Eingang."),
]

bot_verbindungen = {
    "Telegram Trigger": {"main": [[{"node": "Eingabe", "type": "main", "index": 0}]]},
    "Test-Eingang": {"main": [[{"node": "Eingabe", "type": "main", "index": 0}]]},
    "Eingabe": {"main": [[{"node": "Sprachnachricht?", "type": "main", "index": 0}]]},
    "Sprachnachricht?": {"main": [
        [{"node": "Datei holen", "type": "main", "index": 0}],
        [{"node": "Zugang", "type": "main", "index": 0}],
    ]},
    "Datei holen": {"main": [[{"node": "Audio laden", "type": "main", "index": 0}]]},
    "Audio laden": {"main": [[{"node": "Umwandeln", "type": "main", "index": 0}]]},
    "Umwandeln": {"main": [[{"node": "Transkript", "type": "main", "index": 0}]]},
    "Transkript": {"main": [[{"node": "Verstanden?", "type": "main", "index": 0}]]},
    "Verstanden?": {"main": [
        [{"node": "Zugang", "type": "main", "index": 0},
         {"node": "Gehoert Text", "type": "main", "index": 0}],
        [{"node": "Senden (Kurzmeldung)", "type": "main", "index": 0}]]},
    "Gehoert Text": {"main": [[{"node": "Senden (Kurzmeldung)", "type": "main", "index": 0}]]},
    "Zugang": {"main": [[{"node": "Freigegeben?", "type": "main", "index": 0}]]},
    "Freigegeben?": {"main": [
        [{"node": "Text da?", "type": "main", "index": 0}],
        [{"node": "Kein Zugang", "type": "main", "index": 0}]]},
    "Kein Zugang": {"main": [[{"node": "Senden (Kurzmeldung)", "type": "main", "index": 0}]]},
    "Text da?": {"main": [
        [{"node": "Auftrag", "type": "main", "index": 0}],
        [{"node": "Kein Text", "type": "main", "index": 0}]]},
    "Auftrag": {"main": [[{"node": "Kurz?", "type": "main", "index": 0}]]},
    # Stufe 0: erkannte Kurzbefehle gehen direkt in die Ausfuehrung, alles andere in die Analyse.
    "Kurz?": {"main": [[{"node": "Kurzbefehl?", "type": "main", "index": 0}]]},
    "Kurzbefehl?": {"main": [
        [{"node": "Schleife", "type": "main", "index": 0}],
        [{"node": "Planen", "type": "main", "index": 0}]]},
    "Kein Text": {"main": [[{"node": "Senden (Kurzmeldung)", "type": "main", "index": 0}]]},

    # Stufe 1: Analyse
    "Planen": {"main": [[{"node": "Plan Antwort", "type": "main", "index": 0}]]},
    "Plan Antwort": {"main": [[{"node": "Plan da?", "type": "main", "index": 0}]]},
    "Plan da?": {"main": [
        [{"node": "Befehle lesen", "type": "main", "index": 0}],
        [{"node": "Plan merken", "type": "main", "index": 0}]]},
    "Plan merken": {"main": [[{"node": "Plan nochmal?", "type": "main", "index": 0}]]},
    "Plan nochmal?": {"main": [
        [{"node": "Planen", "type": "main", "index": 0}],
        [{"node": "Befehle lesen", "type": "main", "index": 0}]]},
    "Befehle lesen": {"main": [[{"node": "Befehl da?", "type": "main", "index": 0}]]},
    "Befehl da?": {"main": [
        [{"node": "Schleife", "type": "main", "index": 0}],
        [{"node": "Antwort bauen", "type": "main", "index": 0}]]},

    # Stufe 2: Ausfuehrung je Befehl
    # Achtung: bei splitInBatches v3 ist Ausgang 0 "done" und Ausgang 1 "loop"
    # (Quelltext: return [[], returnItems]) - nicht vertauschen.
    "Schleife": {"main": [
        [{"node": "Lage holen", "type": "main", "index": 0}],
        [{"node": "Direkt oder KI?", "type": "main", "index": 0}]]},
    "Direkt oder KI?": {"main": [
        [{"node": "Ersatz Werkzeug", "type": "main", "index": 0}],
        [{"node": "Steuerung?", "type": "main", "index": 0}]]},
    "Steuerung?": {"main": [
        [{"node": "Kurz Steuern", "type": "main", "index": 0}],
        [{"node": "Ausfuehren", "type": "main", "index": 0}]]},
    "Kurz Steuern": {"main": [[{"node": "Steuerung Antwort", "type": "main", "index": 0}]]},
    "Steuerung Antwort": {"main": [[{"node": "Schleife", "type": "main", "index": 0}]]},
    "Ersatz Werkzeug": {"main": [[{"node": "Ersatz Antwort", "type": "main", "index": 0}]]},
    "Ersatz Antwort": {"main": [[{"node": "Schleife", "type": "main", "index": 0}]]},
    "Ausfuehren": {"main": [[{"node": "Ergebnis sammeln", "type": "main", "index": 0}]]},
    "Ergebnis sammeln": {"main": [[{"node": "Schleife", "type": "main", "index": 0}]]},

    # Stufe 3: Pruefung und Nachfassen
    "Lage holen": {"main": [[{"node": "Warteschlange holen", "type": "main", "index": 0}]]},
    "Warteschlange holen": {"main": [[{"node": "Befehle und Lage", "type": "main", "index": 0}]]},
    "Befehle und Lage": {"main": [[{"node": "Pruefen?", "type": "main", "index": 0}]]},
    "Pruefen?": {"main": [
        [{"node": "Pruefen", "type": "main", "index": 0}],
        [{"node": "Pruefung lesen", "type": "main", "index": 0}]]},
    "Pruefen": {"main": [[{"node": "Pruefung Antwort", "type": "main", "index": 0}]]},
    "Pruefung Antwort": {"main": [[{"node": "Pruefung lesen", "type": "main", "index": 0}]]},
    "Pruefung lesen": {"main": [[{"node": "Nachfassen?", "type": "main", "index": 0}]]},
    "Nachfassen?": {"main": [
        [{"node": "Schleife 2", "type": "main", "index": 0}],
        [{"node": "Antwort bauen", "type": "main", "index": 0}]]},
    "Schleife 2": {"main": [
        [{"node": "Antwort bauen", "type": "main", "index": 0}],
        [{"node": "Nacharbeiten", "type": "main", "index": 0}]]},
    "Nacharbeiten": {"main": [[{"node": "Nachtrag sammeln", "type": "main", "index": 0}]]},
    "Nachtrag sammeln": {"main": [[{"node": "Schleife 2", "type": "main", "index": 0}]]},
    "Antwort bauen": {"main": [[{"node": "Antwort", "type": "main", "index": 0}]]},
    "Antwort": {"main": [[{"node": "Senden", "type": "main", "index": 0}]]},

    # Unterschnittstellen
    "Sprachmodell Ausfuehren": {"ai_languageModel": [[{"node": "Ausfuehren", "type": "ai_languageModel", "index": 0}]]},
    "Sprachmodell Nacharbeiten": {"ai_languageModel": [[{"node": "Nacharbeiten", "type": "ai_languageModel", "index": 0}]]},
    "Werkzeug Titel suchen": {"ai_tool": [[{"node": "Ausfuehren", "type": "ai_tool", "index": 0},
                                           {"node": "Nacharbeiten", "type": "ai_tool", "index": 0}]]},
    "Werkzeug Richtung suchen": {"ai_tool": [[{"node": "Ausfuehren", "type": "ai_tool", "index": 0},
                                              {"node": "Nacharbeiten", "type": "ai_tool", "index": 0}]]},
    "Werkzeug Was laeuft": {"ai_tool": [[{"node": "Ausfuehren", "type": "ai_tool", "index": 0},
                                         {"node": "Nacharbeiten", "type": "ai_tool", "index": 0}]]},
    "Werkzeug Azura Adressen": {"ai_tool": [[{"node": "Ausfuehren", "type": "ai_tool", "index": 0},
                                             {"node": "Nacharbeiten", "type": "ai_tool", "index": 0}]]},
    "Werkzeug Azura Aufruf": {"ai_tool": [[{"node": "Ausfuehren", "type": "ai_tool", "index": 0},
                                           {"node": "Nacharbeiten", "type": "ai_tool", "index": 0}]]},
    "Werkzeug Azura Ueberblick": {"ai_tool": [[{"node": "Ausfuehren", "type": "ai_tool", "index": 0},
                                               {"node": "Nacharbeiten", "type": "ai_tool", "index": 0}]]},
}

# ================================================================== Anordnung
# Die Zahlen in den Knotendefinitionen oben sind nur grobe Platzhalter - gueltig
# ist diese Tabelle. Sie legt fest, wie der Ablauf in n8n aussieht: sieben
# Gruppen, jede liest sich von links nach rechts, die Gruppen liegen in der
# Reihenfolge des Ablaufs untereinander. Schrittweite 220, Zeilenabstand 260.
ANORDNUNG = {
    # -- 1 Sprachnachricht (eigener Zweig oben)
    "Datei holen": (-3800, -1860),
    "Audio laden": (-3580, -1860),
    "Umwandeln": (-3360, -1860),
    "Transkript": (-3140, -1860),
    "Verstanden?": (-2920, -1860),
    "Gehoert Text": (-2700, -1860),

    # -- 2 Eingang und Zugang
    "Telegram Trigger": (-4200, -1380),
    "Test-Eingang": (-4200, -1060),
    "Eingabe": (-3980, -1220),
    "Sprachnachricht?": (-3760, -1220),
    "Zugang": (-2980, -1220),
    "Freigegeben?": (-2760, -1220),
    "Text da?": (-2540, -1220),
    "Auftrag": (-2320, -1220),
    "Kein Zugang": (-2760, -1500),
    "Kein Text": (-2540, -1500),
    "Senden (Kurzmeldung)": (-2100, -1500),

    # -- 3 Kurzbefehle (Stufe 0) und Analyse (Stufe 1)
    "Kurz?": (-1800, -400),
    "Kurzbefehl?": (-1580, -400),
    "Planen": (-1360, -400),
    "Plan Antwort": (-1140, -400),
    "Plan da?": (-920, -400),
    "Plan merken": (-1360, -140),
    "Plan nochmal?": (-1140, -140),
    "Befehle lesen": (-680, -400),
    "Befehl da?": (-460, -400),

    # -- 4 Ausfuehrung im Zyklus (Stufe 2)
    "Schleife": (-700, 960),
    "Direkt oder KI?": (-420, 960),
    "Ersatz Werkzeug": (-140, 700),
    "Ersatz Antwort": (80, 700),
    "Steuerung?": (-140, 960),
    "Kurz Steuern": (80, 960),
    "Steuerung Antwort": (300, 960),
    "Ausfuehren": (80, 1220),
    "Ergebnis sammeln": (300, 1220),
    "Sprachmodell Ausfuehren": (80, 1480),

    # -- 5 Werkzeuge (Unterschnittstellen des Agenten)
    "Werkzeug Titel suchen": (560, 1980),
    "Werkzeug Richtung suchen": (760, 1980),
    "Werkzeug Was laeuft": (960, 1980),
    "Werkzeug Azura Adressen": (1160, 1980),
    "Werkzeug Azura Aufruf": (1360, 1980),
    "Werkzeug Azura Ueberblick": (1560, 1980),

    # -- 6 Pruefung und Nachfassen (Stufe 3)
    "Lage holen": (880, 960),
    "Warteschlange holen": (1100, 960),
    "Befehle und Lage": (1320, 960),
    "Pruefen?": (1540, 960),
    "Pruefen": (1540, 1220),
    "Pruefung Antwort": (1760, 1220),
    "Pruefung lesen": (1980, 960),
    "Nachfassen?": (2200, 960),
    "Schleife 2": (2420, 960),
    "Nacharbeiten": (2420, 1220),
    "Nachtrag sammeln": (2640, 1220),
    "Sprachmodell Nacharbeiten": (2420, 1480),

    # -- 7 Antwort und Senden
    "Antwort bauen": (2900, 960),
    "Antwort": (3120, 960),
    "Senden": (3340, 960),
}

# Rahmen (Haftnotizen) je Gruppe: Name, x, y, Breite, Hoehe, Farbe, Inhalt.
# Rund 180 Rasterpunkte Luft unter dem Notiztext, damit die Knoten nicht auf der
# Schrift liegen - in n8n steht der Text oben im Rahmen. Deshalb nur drei Zeilen
# je Notiz; das Ausfuehrliche steht an den Knoten (Anmerkung) und in der Doku.
RAHMEN = [
    ("Notiz Sprachnachricht", -3900, -2060, 1500, 360, 6, """## Sprachnachricht
Datei holen, umwandeln, erkennen (Whisper).
Erkannt: weiter an **Zugang** - sonst kurze Rueckmeldung."""),
    ("Notiz Eingang", -4300, -1680, 2440, 780, 7, """## Eingang und Zugang
Zwei Eingaenge; nur der Betreiber kommt durch (Liste `erlaubte`).
Die kurzen Wege senden ueber **Senden (Kurzmeldung)**."""),
    ("Notiz Analyse", -1900, -580, 1620, 700, 5, """## Stufe 0 und Stufe 1
**Kurz?** erkennt einfache Befehle ohne Modell, **Kurzbefehl?** schickt sie direkt in die Ausfuehrung.
Sonst zerlegt **Planen** die Anweisung in einzelne Befehle."""),
    ("Notiz Ausfuehrung", -820, 520, 1420, 1220, 4, """## Stufe 2: Ausfuehrung im Zyklus
Ein Befehl je Durchlauf - Ausgang 0 = fertig, Ausgang 1 = weiter.
Drei Wege: Ersatz ohne Modell, feste Steuerung, Agent mit Werkzeugen."""),
    ("Notiz Werkzeuge", 460, 1820, 1300, 360, 3, """## Werkzeuge (Unterschnittstellen)
Gestrichelt = Werkzeug-Anbindung an **Ausfuehren** und **Nacharbeiten**.
Dateipfade bleiben in den Werkzeug-Ablaeufen."""),
    ("Notiz Pruefung", 780, 780, 2020, 1020, 1, """## Stufe 3: Pruefung und Nachfassen
**Lage holen** und **Warteschlange holen** belegen den Senderzustand.
**Nachfassen?** startet genau einen zweiten Versuch je Befehl."""),
    ("Notiz Antwort", 2840, 780, 740, 360, 2, """## Antwort und Senden
**Antwort bauen** fasst alles zusammen und baut die Knoepfe der Auswahlliste.
**Senden** schickt per sendMessage (HTML)."""),
]

# Anmerkungen an den Knoten. Kurz und sichtbar im Plan stehen die wichtigen
# Knoten (unter dem Knoten, hoechstens rund 34 Zeichen - sonst schieben sich die
# Texte im Plan ueber die Nachbarn). Alles andere steht nur beim Ueberfahren.
KURZNOTIZ = {
    "Eingabe": "Nachricht, Sprache, Knopfdruck",
    "Zugang": "Nur der Betreiber",
    "Auftrag": "Kontext fuer die Analyse",
    "Senden (Kurzmeldung)": "Kurzer Weg, gleicher Aufruf",
    "Kurz?": "Stufe 0: ohne Sprachmodell",
    "Kurzbefehl?": "Ja = direkt ausfuehren",
    "Planen": "Stufe 1: Plan aus dem Text",
    "Plan da?": "Leer = noch einmal planen",
    "Plan merken": "Zaehlt die Anlaeufe (max. 3)",
    "Befehle lesen": "Ein Element je Befehl",
    "Befehl da?": "Leer = direkt zur Antwort",
    "Schleife": "0 = fertig, 1 = weiter",
    "Direkt oder KI?": "Ja = Ersatzweg ohne Modell",
    "Ersatz Werkzeug": "Werkzeug spielt selbst",
    "Steuerung?": "Ja = feste Adressen",
    "Ausfuehren": "Ein Befehl je Durchlauf",
    "Befehle und Lage": "Ausgaben + Senderzustand",
    "Pruefen?": "Nein = Urteil nach Regeln",
    "Pruefen": "Stufe 3: Urteil je Befehl",
    "Pruefung lesen": "ok und grund je Befehl",
    "Nachfassen?": "Ja = zweiter Versuch",
    "Schleife 2": "Nachfass-Durchgang",
    "Nacharbeiten": "Zweiter Versuch je Befehl",
    "Antwort bauen": "Zusammenfassen + Knoepfe",
    "Senden": "sendMessage (HTML)",
}

LANGNOTIZ = {
    "Datei holen": "Pfad der Sprachnachricht bei Telegram holen.",
    "Audio laden": "Datei herunterladen (im Test ueber stimme.test_url).",
    "Umwandeln": "Spracherkennung auf dem ai-Server (whisper.cpp, MI50).",
    "Transkript": "Nur den Text weitergeben - gedeutet wird spaeter.",
    "Verstanden?": "Nein = nichts verstanden, kurze Rueckmeldung.",
    "Gehoert Text": "Zeigt zur Kontrolle, was verstanden wurde.",
    "Telegram Trigger": "Eingang im Betreiberchat: Nachrichten und Knopfdruecke.",
    "Test-Eingang": "Nur zum Pruefen: nimmt eine Telegram-Nachricht als JSON an.",
    "Sprachnachricht?": "Ja = Sprachnachricht, eigener Zweig oben.",
    "Freigegeben?": "Nein = Absage, der Lauf endet.",
    "Text da?": "Nein = Knopf, Bild oder Sticker ohne Text.",
    "Kein Zugang": "Kurze Absage.",
    "Kein Text": "Kurze Rueckfrage bei Nachrichten ohne Text.",
    "Plan Antwort": "Liest den Text des Modells aus.",
    "Plan nochmal?": "Ja = neuer Anlauf, Nein = Ersatzweg ueber die Ausfuehrung.",
    "Ersatz Antwort": "Schreibt die Ausgabe in den Merker, dann zurueck in die Schleife.",
    "Kurz Steuern": "Naechster Titel, Start/Stop/Neustart - feste Adressen, kein Modell.",
    "Steuerung Antwort": "Formuliert die Antwort des Senders.",
    "Ergebnis sammeln": "Schreibt die Ausgabe in den Merker, dann zurueck in die Schleife.",
    "Sprachmodell Ausfuehren": "Sprachmodell fuer 'Ausfuehren' (Ollama ueber die OpenAI-Schnittstelle).",
    "Werkzeug Titel suchen": "Werkzeug `titel_suchen` fuer Ausfuehren und Nacharbeiten.",
    "Werkzeug Richtung suchen": "Werkzeug `richtung_suchen` fuer Ausfuehren und Nacharbeiten.",
    "Werkzeug Was laeuft": "Werkzeug `was_laeuft` fuer Ausfuehren und Nacharbeiten.",
    "Werkzeug Azura Adressen": "Werkzeug `azura_endpunkte` fuer Ausfuehren und Nacharbeiten.",
    "Werkzeug Azura Aufruf": "Werkzeug `azura_aufruf` fuer Ausfuehren und Nacharbeiten.",
    "Werkzeug Azura Ueberblick": "Werkzeug `azura_ueberblick` fuer Ausfuehren und Nacharbeiten.",
    "Lage holen": "Was laeuft gerade - Beleg fuer die Pruefung.",
    "Warteschlange holen": "Was eingereiht ist - Beleg fuer die Pruefung.",
    "Pruefung Antwort": "Liest das Urteil des Modells aus.",
    "Nachtrag sammeln": "Schreibt die Ausgabe des zweiten Versuchs in den Merker.",
    "Sprachmodell Nacharbeiten": "Sprachmodell fuer 'Nacharbeiten'.",
    "Antwort": "Bereitet den Text fuer Telegram auf (HTML, ohne Sternchen).",
}


def anordnen(ablauf, plan, rahmen, kurz, lang):
    """Setzt Positionen, Haftnotizen und Anmerkungen.

    Bricht ab, wenn ein Knoten keine Position hat - sonst faellt ein neuer Knoten
    erst in n8n auf (er landet irgendwo im Nichts).
    """
    namen = [k["name"] for k in ablauf["nodes"] if "stickyNote" not in k["type"]]
    ohne = [n for n in namen if n not in plan]
    if ohne:
        raise SystemExit("Ohne Position in ANORDNUNG: " + ", ".join(ohne))
    ueberzaehlig = [n for n in plan if n not in namen]
    if ueberzaehlig:
        raise SystemExit("In ANORDNUNG, aber nicht im Ablauf: " + ", ".join(ueberzaehlig))
    doppelt = [n for n in kurz if n in lang]
    if doppelt:
        raise SystemExit("Kurz- und Langnotiz am selben Knoten: " + ", ".join(doppelt))
    for k in ablauf["nodes"]:
        if k["name"] in plan:
            k["position"] = list(plan[k["name"]])
        if k["name"] in kurz:
            k["notes"] = kurz[k["name"]]
            k["notesInFlow"] = True
        elif k["name"] in lang:
            k["notes"] = lang[k["name"]]
    for name, x, y, breite, hoehe, farbe, inhalt in rahmen:
        ablauf["nodes"].append(notiz(name, x, y, breite, hoehe, inhalt, farbe))


agent = {
    "id": "RadioAgentBot",
    "name": "Radio - Telegram-Agent",
    "nodes": bot,
    "connections": bot_verbindungen,
    "settings": {"executionOrder": "v1", "saveDataSuccessExecution": "all",
                 "saveManualExecutions": True},
    "staticData": {"global": {"erlaubte": [], "lauf": {"befehle": []}}},
    "active": False,
    "versionId": str(uuid.uuid4()),
    "parentFolderId": ORDNER,
}

anordnen(agent, ANORDNUNG, RAHMEN, KURZNOTIZ, LANGNOTIZ)

# ------------------------------------------------- Anordnung der Werkzeuge
# Dieselbe Idee wie beim Bot: je Zweig eine Zeile, darum ein Rahmen mit
# Ueberschrift. Die Weichen liegen auf der Hauptzeile (y = 0).
W_ANORDNUNG = {
    "Eingang": (-900, 0),
    "Richtung?": (-660, 0),
    "Nur Status?": (-420, 0),
    "Richtung suchen": (-420, -480),
    "Vorschlaege aufbereiten": (-180, -480),
    "Suche klug": (-420, 380),
    "Suche Sender": (-180, 380),
    "Treffer aufbereiten": (60, 380),
    "NowPlaying": (-420, 760),
    "Status aufbereiten": (-180, 760),
    "Treffer da?": (540, 0),
    "Einreihen?": (780, 0),
    "Warteschlange leeren": (1020, -260),
    "Sofort eintragen": (1260, -260),
    "Danach eintragen": (1260, 180),
    "Ergebnis": (1500, 0),
}

W_RAHMEN = [
    ("Notiz W Weichen", -1000, -160, 460, 340, 5, """## Weichen
Richtung, Zustand oder Titelsuche - eines von drei."""),
    ("Notiz W Richtung", -520, -640, 560, 360, 4, """## Zweig: Richtung
Stimmung, Genre oder Jahrzehnt aus dem Katalogdienst."""),
    ("Notiz W Suche", -520, 220, 900, 340, 1, """## Zweig: Titel suchen
Katalogdienst (unscharf) und Volltextsuche des Senders."""),
    ("Notiz W Status", -520, 620, 560, 340, 6, """## Zweig: Was laeuft
Nur der Zustand - die Rueckgabe ist der Text."""),
    ("Notiz W Abspielen", 940, -440, 540, 880, 3, """## Abspielen
Erst die Warteschlange leeren, dann sofort oder hinten anstellen."""),
]

W_LANGNOTIZ = {
    "Eingang": "Felder des Werkzeugs: suchtext, richtung, frage, einreihen.",
    "Richtung suchen": "Katalogdienst nach Stimmung, Genre oder Jahrzehnt.",
    "Vorschlaege aufbereiten": "Macht aus den Vorschlaegen einen ersten Titel oder eine Liste.",
    "Suche klug": "Unscharfe Suche im Katalogdienst (tippfehlertolerant).",
    "Suche Sender": "Volltextsuche des Senders als zweite Quelle.",
    "Treffer aufbereiten": "Treffer beider Quellen zu einer kurzen Liste machen.",
    "NowPlaying": "Was laeuft, was kommt danach, wie viele Zuhoerer.",
    "Status aufbereiten": "Formuliert den Zustand als Text (Rueckgabe des Werkzeugs).",
    "Treffer da?": "Ja = es gibt einen Titel, der laufen soll.",
    "Einreihen?": "Ja = nur einreihen, nicht unterbrechen.",
    "Warteschlange leeren": "Leert die unterbrechende Warteschlange des Senders.",
    "Sofort eintragen": "Traegt den Titel sofort in die unterbrechende Warteschlange ein.",
    "Danach eintragen": "Haengt den Titel hinter das Laufende.",
    "Ergebnis": "Ausgabeknoten: hier endet der Werkzeug-Ablauf.",
}

W_ANORDNUNG_AZ = {
    "Eingang": (-900, 0),
    "Adressen suchen?": (-660, 0),
    "Aufruf?": (-420, 0),
    "Wache": (-180, 0),
    "Ausfuehren?": (60, 0),
    "Nur lesen?": (300, 0),
    "Aufruf Ergebnis": (800, 0),
    "Lesen": (540, 220),
    "Schreiben": (540, 460),
    "Trockenlauf": (300, 560),
    "Beschreibung holen": (-420, -480),
    "Adressen finden": (-180, -480),
    "Anlagen": (-420, 900),
    "Zustand": (-180, 900),
    "Wiedergabelisten": (60, 900),
    "Ueberblick": (300, 900),
}

W_AZ_RAHMEN = [
    ("Notiz AZ Weichen", -1000, -160, 460, 340, 5, """## Weichen
Adressen nachschlagen, Aufruf oder Ueberblick."""),
    ("Notiz AZ Adressen", -520, -640, 560, 360, 4, """## Zweig: Adressen
Stichwort suchen und Felder beschreiben."""),
    ("Notiz AZ Aufruf", -520, -260, 1400, 980, 3, """## Zweig: Aufruf
Die Wache prueft Pfad und Methode; ohne bestaetigt wird nichts geschrieben."""),
    ("Notiz AZ Ueberblick", -520, 780, 900, 340, 6, """## Zweig: Ueberblick
Anlagen, Zustand und Wiedergabelisten."""),
]

W_AZ_LANGNOTIZ = {
    "Eingang": "Felder des Werkzeugs: suche, methode, pfad, koerper, bestaetigt, frage.",
    "Adressen suchen?": "Ja = Adressen der Senderschnittstelle nachschlagen.",
    "Beschreibung holen": "Adressverzeichnis vom Katalogdienst holen.",
    "Adressen finden": "Kurze Liste der passenden Adressen mit Feldern.",
    "Aufruf?": "Ja = eine Schnittstelle des Senders aufrufen.",
    "Wache": "Prueft Methode und Pfad - Schreiben nur mit bestaetigt=true.",
    "Ausfuehren?": "Ja = aufrufen, Nein = Trockenlauf zurueckgeben.",
    "Nur lesen?": "Ja = GET (lesen), Nein = aendern (POST/PUT/DELETE).",
    "Lesen": "Liest vom Sender.",
    "Schreiben": "Aendert am Sender - nur nach ausdruecklicher Bestaetigung.",
    "Trockenlauf": "Zeigt, was der Aufruf taete, ohne etwas zu aendern.",
    "Aufruf Ergebnis": "Antwort des Senders kurz zusammengefasst.",
    "Anlagen": "Anlagen und ob Sendeteil und Ausgabe laufen.",
    "Zustand": "Zustand von Sendeteil und Ausgabe.",
    "Wiedergabelisten": "Wiedergabelisten mit Titelzahl.",
    "Ueberblick": "Fasst den Ueberblick als Text zusammen.",
}

anordnen(werkzeuge[0], W_ANORDNUNG, W_RAHMEN, {}, W_LANGNOTIZ)
anordnen(werkzeuge[1], W_ANORDNUNG_AZ, W_AZ_RAHMEN, {}, W_AZ_LANGNOTIZ)

with open("/tmp/radio-werkzeuge.json", "w", encoding="utf-8") as f:
    json.dump(werkzeuge, f, ensure_ascii=False, indent=2)
with open("/tmp/radio-agent.json", "w", encoding="utf-8") as f:
    json.dump(agent, f, ensure_ascii=False, indent=2)


def verbindungen_pruefen(ablauf):
    """n8n lehnt einen Import mit 'Workflow structure is invalid' ab, wenn eine
    Verbindung auf einen nicht vorhandenen Knoten zeigt - und laesst dabei still
    die alte Fassung laufen (so am 2026-09-20 passiert: eine liegengebliebene
    Zeile 'Gedaechtnis Planen'). Deshalb hier vorab pruefen."""
    namen = {k["name"] for k in ablauf["nodes"]}
    fehler = []
    for quelle, ausgaenge in ablauf["connections"].items():
        if quelle not in namen:
            fehler.append("Quelle ohne Knoten: %s" % quelle)
        for art, zweige in ausgaenge.items():
            for zweig in zweige or []:
                for ziel in zweig or []:
                    if ziel.get("node") not in namen:
                        fehler.append("%s -> %s (%s): Ziel ohne Knoten"
                                      % (quelle, ziel.get("node"), art))
    for k in ablauf["nodes"]:
        for art, zweige in (k.get("connections") or {}).items():
            for zweig in zweige or []:
                for ziel in zweig or []:
                    if ziel.get("node") not in namen:
                        fehler.append("%s -> %s (%s): Ziel ohne Knoten"
                                      % (k["name"], ziel.get("node"), art))
    if fehler:
        raise SystemExit("Verbindungen fehlerhaft in %s:\n  %s"
                         % (ablauf.get("name"), "\n  ".join(fehler)))


for _w in werkzeuge + [agent]:
    verbindungen_pruefen(_w)

print("geschrieben: /tmp/radio-werkzeuge.json (%d Arbeitsablaeufe), /tmp/radio-agent.json"
      % len(werkzeuge))
print("Verbindungen geprueft:", " + ".join(w["name"] for w in werkzeuge + [agent]))
print("Bot-Knoten:", len(bot))
for w in werkzeuge:
    print("  ", w["id"], "->", w["name"], "|", len(w["nodes"]), "Knoten")
