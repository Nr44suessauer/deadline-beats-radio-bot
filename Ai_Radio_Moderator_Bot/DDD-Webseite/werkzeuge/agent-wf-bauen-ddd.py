#!/usr/bin/env python3
"""Erzeugt den DDD-Webseite-Bot als AI-Agent mit Werkzeugen.

ABLEGER von ../../werkzeuge/agent-wf-bauen.py fuer die Webseiten-Fassung.
Unterschiede: Sender 2 (AzuraCast "DDD-Webseite Demo"), Ablauf-Kennungen und
-Namen mit dem Praefix "DDD-Webseite", ein eigener Testeingang, eigene
Telegram-Anmeldedaten; Ausgaben nach /tmp/ddd-webseite-*.json.

ZWEISPRACHIG: Der Bot versteht deutsche UND englische Nachrichten in EINEM
Chat. Die Sprache wird beim Eingang erkannt (EINGABE_JS, sprache_raten) und
reist als Feld "sprache" mit: die Kurzbefehle der Stufe 0 kennen englische
Wortlaute, die Werkzeuge antworten in der Sprache des Betreibers, und die
Sprachanweisungen verlangen die Antwort in dieser Sprache. Inhalte (Nachrichten,
Wetter) und die Verwaltungswege des Dienstes bleiben deutsch.

Statt einer langen Wenn-Dann-Kette entscheidet ein KI-Agent (Ollama auf der 3090 Ti),
welches Werkzeug er braucht. Jedes Werkzeug ist ein eigener kleiner Arbeitsablauf:

  Werkzeug - Titel suchen     suchtext        -> Trefferliste mit Dateipfaden
  Werkzeug - Richtung suchen  richtung        -> Vorschlaege fuer Stimmung/Genre
  Werkzeug - Sofort spielen   pfad, titel     -> leert die Warteschlange und spielt sofort
  Werkzeug - Danach spielen   pfad, titel     -> reiht hinter das Laufende ein
  Werkzeug - Was laeuft       (keine)         -> was laeuft, was kommt, Zuhoerer

Zugangsdaten kommen aus dem Umfeld (AZ_KEY, TG_TOKEN). Ausgabe:
  /tmp/ddd-webseite-werkzeuge.json  (Liste der Werkzeug-Arbeitsablaeufe)
  /tmp/ddd-webseite-agent.json      (der Bot)
"""
import json
import os
import uuid

# ---------------------------------------------------------------- Zentrale
# Alle Adressen, Schluessel und Aufgabentexte liegen ab jetzt in EINEM Code-Knoten
# des Ablaufs "Konfiguration" (siehe KONFIG am Ende dieser Datei). Die Ablaufe
# holen sie zur LAUFZEIT von dort. Was hier steht, ist deshalb kein Wert mehr,
# sondern nur der Ausdruck, der den Wert holt ("{{ ... }}" mitten in einer
# Zeichenkette, "={{ ... }}" als ganzer Wert eines Feldes).
K = "$('Konfiguration').first().json.konfig"


def kwert(pfad):
    """Ein Wert aus der Konfiguration - als ganzer Feldinhalt (Ausdruck)."""
    return Ausdruck(K + "." + pfad)


class Ausdruck(str):
    """Ein Ausdruck, der beim Verketten ein GANZER Ausdruck bleibt.

    Wichtig (am 2026-09-22 im Testlauf gemessen): n8n loest eine Einfuegung
    "{{ ... }}" mitten in einer Zeichenkette NICHT auf - im Knoten landete die
    Adresse woertlich ("Invalid URL: {{ $('Konfiguration')... }}"). Richtig ist
    immer die Form "={{ ... }}". Diese Klasse sorgt dafuer, dass auch
    zusammengesetzte Adressen so aussehen:

        AZ + "/api/station/2"  ->  ={{ $('Konfiguration').first().json.konfig.sender.adresse
                                       + "/api/station/2" }}
    """

    def __new__(cls, rumpf):
        return str.__new__(cls, "={{ " + rumpf + " }}")

    @property
    def rumpf(self):
        return str.__str__(self)[4:-3]

    def __add__(self, mehr):
        return Ausdruck(self.rumpf + " + " + json.dumps(str(mehr)))

    def __radd__(self, weniger):
        return Ausdruck(json.dumps(str(weniger)) + " + " + self.rumpf)


AZ = Ausdruck(K + ".sender.adresse")
API = AZ + "/api/station/2"
API_ADMIN = AZ + "/api/admin"
# Adresse fuer "was laeuft gerade": Senderkennung aus der Konfiguration
# (Sender 1 bzw. 2). Vorher stand hier fest "/api/nowplaying/1" - der
# DDD-Bot fragte damit den falschen Sender ab (gefunden am 2026-09-25).
NOWPLAYING = Ausdruck(K + ".sender.adresse + '/api/nowplaying/' + " + K + ".sender.senderId")
KATALOG = Ausdruck(K + ".dienst.adresse")
MELDUNGEN = Ausdruck(K + ".dienst.adresse")
OLLAMA = Ausdruck(K + ".sprachmodell.adresse")
MODELL = Ausdruck(K + ".sprachmodell.modell")
WHISPER = Ausdruck(K + ".sprache.adresse")
TG = Ausdruck(K + ".telegram.bot")
TG_DATEI = Ausdruck(K + ".telegram.datei")
# Der Knoten "Ollama Chat Model" reicht in dieser n8n-Fassung keine Werkzeugaufrufe
# durch (das Modell antwortet mit leerem Text, der Agent bricht ab). Ollama spricht
# unter /v1 dieselbe Schnittstelle wie OpenAI - deshalb der OpenAI-Knoten.
OLLAMA_OAI_URL = Ausdruck(K + ".sprachmodell.v1")
OAI_CRED = os.environ.get("OLLAMA_OAI_CRED_ID", "radioOllamaOpenAi")
OAI_CRED_NAME = os.environ.get("OLLAMA_OAI_CRED_NAME", "Ollama (OpenAI-Schnittstelle)")
OLLAMA_CRED = os.environ.get("OLLAMA_CRED_ID", "radioOllama01")
OLLAMA_CRED_NAME = os.environ.get("OLLAMA_CRED_NAME", "Ollama (Radio)")
TG_CRED_ID = os.environ.get("TG_CRED_ID", "dddWebseiteTelegram")
TG_CRED_NAME = os.environ.get("TG_CRED_NAME", "DDD-Webseite Telegram")

AZ_KOPF = [{"name": "X-API-Key", "value": kwert("sender.schluessel")}]
JSON_KOPF = [{"name": "Content-Type", "value": "application/json"}]
# Ollama spricht unter /v1 die OpenAI-Schnittstelle; der Schluessel ist beliebig.
OLLAMA_KOPF = [{"name": "Content-Type", "value": "application/json"},
               {"name": "Authorization", "value": "={{ 'Bearer ' + " + K
                + ".sprachmodell.schluessel }}"}]


def modell_koerper(aufgabe, nutzer_ausdruck, temperatur, tokens):
    """Textkoerper fuer einen direkten Modellaufruf (POST /v1/chat/completions).

    `aufgabe` ist der Name der Aufgabe in der Konfiguration ("planen", "pruefen").
    Der Aufgabentext selbst steht im Knoten "Konfiguration" - hier nur der Verweis
    darauf, damit er dort geaendert werden kann und nicht im Erzeuger.

    Fuer die werkzeuglosen Stufen (Analyse, Pruefung) wird der Agentenknoten bewusst
    NICHT benutzt: n8n haengt dort eigene Anweisungen an, mit denen das Modell einfache
    Auftraege als "kein Auftrag" einordnete (am 2026-09-20 reproduzierbar: dieselbe
    Aufforderung direkt gestellt lieferte den richtigen Plan, im Agenten ein leeres
    Ergebnis). Ein blanker Aufruf ist ausserdem schneller und billiger.
    """
    return ("={{ JSON.stringify({ model: " + K + ".sprachmodell.modell"
            + ", messages: [{ role: 'system', content: " + K + ".aufgaben." + aufgabe
            + " }, { role: 'user', content: " + nutzer_ausdruck + " }]"
            + ", temperature: " + repr(temperatur).rstrip("0").rstrip(".")
            # Ohne diese Angabe "denkt" das Modell bei jeder Anfrage mehrere hundert
            # Token mit: gemessen am 2026-09-20 9,8 s / 347 Token gegen 1,7 s / 34 Token
            # bei gleichem, gueltigem JSON. Der Textbaustein /no_think allein wirkt nicht.
            + ", reasoning_effort: 'none'"
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

PROJEKT = "rQ6DFC63JlNQbiar"
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
W_WERKZEUG = "DDD-Webseite-Radio"
W_WERKZEUG_NAME = "DDD-Webseite Werkzeug Radio"

# Eigener Werkzeug-Ablauf fuer den Sender selbst (AzuraCast): Adressen
# nachschlagen, beliebige Schnittstelle aufrufen, Ueberblick holen. Der Agent
# haengt drei Werkzeugknoten daran - so kann der Betreiber den Server ueber den
# Chat bedienen, ohne dass die Radio-Werkzeuge unuebersichtlich werden.
W_AZURA = "DDD-Webseite-AzuraCast"
W_AZURA_NAME = "DDD-Webseite Werkzeug AzuraCast"

# Dritter Werkzeug-Ablauf: das Postfach fuer den Suchbot (Wetter, RSS, Nachrichten)
# und die Ansagen des Moderators. Liegt bewusst getrennt, damit der neue Umfang
# den bestehenden Bot nicht beruehrt (Schnittstelle: dienst/meldungen.py).
W_MELDUNGEN = "DDD-Webseite-Meldungen"
W_MELDUNGEN_NAME = "DDD-Webseite Werkzeug Meldungen"
# Der Dienst, der das Postfach fuehrt (LXC 103, Container ddd-radio). Die Adresse steht in der
# Konfiguration (dienst.adresse) - hier nur der Verweis darauf.
MELDUNGEN = Ausdruck(K + ".dienst.adresse")
MELDUNG_KOPF = [{"name": "Content-Type", "value": "application/json"},
                {"name": "X-Meldung-Schluessel", "value": kwert("dienst.schluessel")}]


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


def dokunotiz(ablauf, titel: str, zeilen: list[str], breite: int = 1150) -> None:
    """Setzt oben eine Notiz mit dem Verweis auf die Dokumentation des Ablaufs.

    Sie liegt bewusst AUSSERHALB aller Bereiche (oberhalb der Flaeche), damit die
    Anordnungspruefung unberuehrt bleibt, und traegt in der Oberflaeche die Antwort
    auf die zwei Fragen, die man beim Oeffnen hat: Was ist das - und wo steht mehr?
    """
    knoten = [k for k in ablauf["nodes"] if "stickyNote" not in k["type"]]
    x0 = min(k["position"][0] for k in knoten)
    y0 = min(k["position"][1] for k in ablauf["nodes"])
    inhalt = "## " + titel + "\n" + "\n".join(zeilen)
    # Zeilenhoehe 32 statt 22: die Oberflaeche rendert die Zeilen hoeher, sonst
    # wird die letzte Zeile abgeschnitten (am 2026-09-24 bei "Konfiguration" bemerkt).
    hoehe = 44 + 32 * len(zeilen)
    ablauf["nodes"].append(notiz("Notiz Doku", x0, y0 - hoehe - 80, breite, hoehe,
                                 inhalt, 2))


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
//
// ZWEISPRACHIG: Das Feld "sprache" (de/en) kommt vom Agenten mit und bestimmt die
// Sprache der Antwort. Der Suchweg selbst ist sprachunabhaengig; nur die Texte
// wechseln. Vorgabe ist deutsch.
const eingang = $('Eingang').first().json || {};
const EN = String(eingang.sprache || '').toLowerCase() === 'en';
const T = (de, eng) => (EN ? eng : de);
const suchtext = String(eingang.suchtext || $json.suchtext || '').trim();
const einreihen = eingang.einreihen === true
  || String(eingang.einreihen || '').toLowerCase() === 'true';
if (!suchtext) {
  return [{ json: { ergebnis: T('FEHLER: Kein Suchbegriff. Nenne Interpret und/oder Titel, '
    + 'zum Beispiel "In Extremo Santa Maria". Suche nie ohne Begriff.',
    'ERROR: No search term. Name the artist and/or title, for example '
    + '"In Extremo Santa Maria". Never search without a term.'), pfad: '',
    einreihen: einreihen } }];
}

const okText = (t) => 'OK: "' + t + '" ' + (einreihen
  ? T('laeuft danach (nach dem laufenden Titel).',
      'will play afterwards (after the current track).')
  : T('laeuft jetzt sofort.', 'is playing now.'));

// Merker der letzten Auswahlliste: "2" oder "nummer 2" loest daraus auf. So muss
// das Modell den Dateipfad nicht abschreiben - kleinere Modelle erfinden ihn sonst.
const d = $getWorkflowStaticData('global');
const vorher = Array.isArray(d.listen) ? d.listen : [];
const zahl = suchtext.match(/^[^\d]{0,12}(\d{1,2})[^\d]{0,6}$/);
if (zahl) {
  const t = vorher[Number(zahl[1]) - 1];
  if (!t) {
    return [{ json: { ergebnis: (vorher.length
      ? T('Die Nummer ' + zahl[1] + ' gibt es nicht - zur Auswahl standen ' + vorher.length + ' Titel.',
          'There is no number ' + zahl[1] + ' - the list had ' + vorher.length + ' track(s).')
      : T('Es steht keine Auswahlliste bereit. Suche erst nach einem Titel.',
          'There is no selection list. Search for a track first.')), pfad: '',
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
  // Live-/Bootleg-Mitschnitte liegen im Archiv und werden nie vorgeschlagen.
  // Der Schraegstrich muss einfach maskiert sein (\/) - mit \\/ waere der
  // regulaere Ausdruck in JavaScript ungueltig.
  if (/^_Archiv\//i.test(pfad)) continue;
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
  return [{ json: { ergebnis: T('KEINE TREFFER fuer "' + suchtext + '". '
    + 'Versuche den Interpreten allein oder eine Richtung (richtung_suchen).',
    'NO MATCHES for "' + suchtext + '". Try the artist alone or a direction '
    + '(richtung_suchen).'), pfad: '',
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
  ergebnis: T('Mehrere Titel passen zu "' + suchtext + '":\n' + zeilen.join('\n')
    + '\n\nFrage kurz, welcher gemeint ist. Antwortet er mit einer Nummer, rufe titel_suchen\n'
    + 'mit genau dieser Nummer als suchtext auf.',
    'Several tracks match "' + suchtext + '":\n' + zeilen.join('\n')
    + '\n\nAsk briefly which one is meant. If the answer is a number, call titel_suchen\n'
    + 'with exactly that number as suchtext.'),
  auswahl: zeigen.map((e) => name(e.t)),
  pfad: '', einreihen: einreihen } }];
"""

WERKZEUG_ERGEBNIS_JS = r"""
// Der Suchlauf hat bei einem klaren Treffer schon gespielt - hier nur noch die
// Antwort des Senders pruefen und den Text weitergeben. Der Text steht je nach
// Zweig in "Treffer aufbereiten" (Titelsuche) oder "Vorschlaege aufbereiten"
// (Richtung); der jeweils andere Knoten ist nicht gelaufen.
const eingang = $('Eingang').first().json || {};
const EN = String(eingang.sprache || '').toLowerCase() === 'en';
const T = (de, eng) => (EN ? eng : de);
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
if (!auf.pfad || !antwort) return [{ json: { ergebnis: auf.ergebnis
  || T('Kein Treffer.', 'No match.'),
  auswahl: Array.isArray(auf.auswahl) ? auf.auswahl : [] } }];
const fehler = (antwort.errors || []).length || antwort.error;
return [{ json: { ergebnis: (fehler
  ? T('FEHLER beim Eintragen: ', 'ERROR while queueing: ')
    + JSON.stringify(antwort.errors || antwort.error)
  : auf.ergebnis),
  auswahl: Array.isArray(auf.auswahl) ? auf.auswahl : [] } }];
"""

# --- 2) Richtung suchen
RICHTUNG_JS = r"""
// Eingabe am Ausloeser lesen (siehe SUCHE_JS).
const eingang = $('Eingang').first().json || {};
const EN = String(eingang.sprache || '').toLowerCase() === 'en';
const T = (de, eng) => (EN ? eng : de);
const wort = String(eingang.richtung || $json.richtung || '').trim();
const einreihen = eingang.einreihen === true
  || String(eingang.einreihen || '').toLowerCase() === 'true';
if (!wort) {
  return [{ json: { ergebnis: T('FEHLER: Keine Richtung genannt.',
    'ERROR: No direction given.'), pfad: '',
    einreihen: einreihen } }];
}
let j = {};
try { j = $('Richtung suchen').first().json || {}; } catch (e) { j = {}; }
if (j.error || !j.treffer || !j.treffer.length) {
  return [{ json: { ergebnis: T('Die Richtung "' + wort + '" kennt der Katalog nicht. '
    + 'Bekannte Richtungen: party, dance, rock, pop, metal, hiphop, electronic, disco, '
    + 'punk, grunge, folk, blues, jazz, klassik, schlager, deutschrap, ruhig, hart, 90er, 80er. '
    + 'Nimm eine davon und rufe richtung_suchen erneut auf.',
    'The catalogue does not know the direction "' + wort + '". '
    + 'Known directions: party, dance, rock, pop, metal, hiphop, electronic, disco, '
    + 'punk, grunge, folk, blues, jazz, klassik, schlager, deutschrap, ruhig, hart, 90er, 80er. '
    + 'Pick one of them and call richtung_suchen again.') } }];
}
const zeilen = j.treffer.slice(0, 4).map((t, i) => (i + 1) + '. '
  + ((t.artist ? t.artist + ' - ' : '') + (t.title || '?'))
  + (t.length_text ? '  (' + t.length_text + ')' : ''));
const erster = j.treffer[0];
const titel = (erster.artist ? erster.artist + ' - ' : '') + (erster.title || '?');
// Eine Stimmung ist ein Auftrag, keine Frage: gespielt wird hier im Werkzeug,
// das Modell meldet nur noch das Ergebnis (Knoten "Sofort eintragen").
const wo = einreihen
  ? T('laeuft danach (nach dem laufenden Titel).',
      'will play afterwards (after the current track).')
  : T('laeuft jetzt sofort.', 'is playing now.');
return [{ json: {
  ergebnis: 'OK: "' + titel + '" ' + wo + T(' (Richtung ', ' (direction ')
    + (j.richtung || wort) + ').'
    + (zeilen.length > 1 ? T('\nDanach koennen kommen: ', '\nCan follow: ')
        + zeilen.slice(1, 4).join(', ') : ''),
  pfad: erster.path || '',
  titel: titel,
  einreihen: einreihen } }];
"""

STATUS_JS = r"""
const eingang = $('Eingang').first().json || {};
const EN = String(eingang.sprache || '').toLowerCase() === 'en';
const T = (de, eng) => (EN ? eng : de);
const j = $json || {};
if (j.error) {
  return [{ json: { ergebnis: T('Der Sender antwortet gerade nicht.',
    'The station is not responding right now.') } }];
}
const jetzt = (j.now_playing && j.now_playing.song) || {};
const rest = Math.max(0, Math.round((jetzt.duration || 0) - (jetzt.elapsed || 0)));
const naechster = (j.playing_next && j.playing_next.song) || {};
return [{ json: { ergebnis: T('Jetzt laeuft: ', 'Now playing: ')
  + (jetzt.text || T('unbekannt', 'unknown'))
  + (rest ? T(' (noch ', ' (') + Math.floor(rest / 60) + ':' + String(rest % 60).padStart(2, '0')
      + T(' min)', ' left)') : '')
  + T('\nDanach: ', '\nNext: ') + (naechster.text || T('unbekannt', 'unknown'))
  + T('\nZuhoerer: ', '\nListeners: ') + ((j.listeners && j.listeners.current) || 0) } }];
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
                        {"name": "einreihen", "type": "boolean"},
                        {"name": "sprache", "type": "string"}]),
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
    http("NowPlaying", [-180, 400], "GET", NOWPLAYING, None, AZ_KOPF,
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
    http("Warteschlange leeren", [1020, -180], "PUT", API_ADMIN + "/debug/station/2/telnet",
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
    + '(z. B. /api/station/2/playlists). Nutze azura_endpunkte zum Nachschlagen.' } }];
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
    http("Lesen", [540, -60], "GET", "={{ " + K + ".sender.adresse + $('Wache').first().json.pfad }}",
         None, AZ_KOPF, "Liest eine Adresse des Senders."),
    http("Schreiben", [540, 220], "={{ $('Wache').first().json.methode }}",
         "={{ " + K + ".sender.adresse + $('Wache').first().json.pfad }}",
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

# Spracherkennung fuer den zweisprachigen Chat. Sie steckt in EINGABE_JS und in
# TRANSKRIPT_JS (Sprachnachricht) und liefert 'de' oder 'en'. Bewusst einfach und
# ohne Sprachmodell: deutsche Merkmale (Umlaute, Funktionswoerter) wiegen schwer,
# englische Funktionswoerter zaehlen dagegen. Ein einzelner Titel ohne Beiwoerter
# bleibt deutsch (die Vorgabe) - die Analyse antwortet dann trotzdem in der
# Sprache der Nachricht, weil das Sprachmodell sie selbst erkennt.
SPRACHE_JS = r"""
function sprache_raten(text) {
  const t = ' ' + String(text || '').toLowerCase()
    .replace(/[^a-z0-9\u00e4\u00f6\u00fc\u00df ]+/g, ' ') + ' ';
  if (/[\u00e4\u00f6\u00fc\u00df]/.test(t)) return 'de';
  const DE = [' der ', ' die ', ' das ', ' und ', ' nicht ', ' bitte ', ' mal ', ' was ',
    ' wie ', ' wer ', ' wo ', ' ist ', ' sind ', ' laeuft ', ' spiele ', ' spiel ',
    ' mach ', ' leg ', ' will ', ' moechte ', ' m\u00f6chte ', ' gib ', ' zeig ', ' suche ',
    ' brauche ', ' kannst ', ' koennen ', ' k\u00f6nnen ', ' danach ', ' gleich ',
    ' jetzt ', ' dein ', ' deine ', ' mir ', ' dir ', ' ich ', ' du ', ' wir ', ' ein ',
    ' eine ', ' einen ', ' dem ', ' den ', ' mit ', ' fuer ', ' f\u00fcr ', ' von ', ' zu ',
    ' am ', ' auf ', ' an ', ' kann ', ' soll ', ' gern ', ' habe ', ' hat ', ' noch ',
    ' schon ', ' etwas ', ' nichts ', ' alles ', ' wieder ', ' heute ', ' morgen '];
  const EN = [' the ', ' and ', ' not ', ' please ', ' what ', ' how ', ' who ', ' where ',
    ' is ', ' are ', ' playing ', ' play ', ' put ', ' make ', ' want ', ' would ',
    ' like ', ' give ', ' show ', ' search ', ' find ', ' need ', ' can ', ' could ',
    ' then ', ' now ', ' next ', ' your ', ' you ', ' we ', ' my ', ' me ', ' of ',
    ' from ', ' to ', ' with ', ' for ', ' by ', ' do ', ' does ', ' will ', ' should ',
    ' have ', ' has ', ' been ', ' still ', ' already ', ' something ', ' nothing ',
    ' everything ', ' again ', ' today ', ' tomorrow ', ' song ', ' songs ', ' music ',
    ' track ', ' radio ', ' station ', ' announce ', ' say ', ' tell ', ' read ',
    ' weather ', ' news ', ' messages ', ' overview ', ' later ', ' afterwards ',
    ' just ', ' resume ', ' continue ', ' louder ', ' quieter ', ' silence ',
    ' queue ', ' mailbox ', ' inbox ', ' volume ', ' reboot ', ' no '];
  // Achtung: mehrdeutige Woerter (pause, stop, start, skip, play, one) stehen hier
  // NICHT - sie sind auch im Deutschen ueblich. Fuer Kurzbefehle entscheidet der
  // Sprachmerker der STEUER-Zeile (z. B. "next"/"skip" -> englische Antwort).
  let de = 0;
  let en = 0;
  for (const w of DE) if (t.includes(w)) de += 1;
  for (const w of EN) if (t.includes(w)) en += 1;
  return en > de ? 'en' : 'de';
}
"""

# Sprachleser fuer die Antwort-Knoten: liest die am Eingang (EINGABE_JS) bzw. an
# der Sprachnachricht (TRANSKRIPT_JS) bestimmte Sprache. "Zugang" liegt in jedem
# Chat-Weg vor; in den Zeitplan-Knoten fehlen diese Quellen - dann gilt deutsch.
SPRACHE_LESEN_JS = r"""
// Sprache des Chats (am Eingang bestimmt; Vorgabe deutsch).
const EN = String((function () {
  for (const q of ['Zugang', 'Transkript', 'Eingabe']) {
    try {
      const j = $(q).first().json;
      if (j && j.sprache) return j.sprache;
    } catch (e) { /* Knoten nicht gelaufen */ }
  }
  return '';
})() || '') === 'en';
"""

EINGABE_JS = SPRACHE_JS + r"""
// Telegram-Update vereinheitlichen (Nachricht, Sprachnachricht, Knopfdruck).
// Die Sprache der Nachricht wird hier bestimmt und reist als "sprache" mit; sie
// entscheidet ueber die Sprache der Antworten (deutsch oder englisch).
const roh = $input.first().json ?? {};
const b = (roh.body && typeof roh.body === 'object') ? roh.body : null;
// Der REST-Eingang schickt einfach {"text": "..."} (ohne Telegram-Umschlag).
// Erkannt wird er an der Webhook-Adresse - der Testeingang bleibt unveraendert.
const flach = !!(b && typeof b.text === 'string'
  && !b.message && !b.callback_query && !b.edited_message);
const istRest = flach && /ddd-webseite-rest/.test(
  String(roh.webhookUrl || '') + String(roh.webhookTestUrl || ''));
const quelle = (b && (b.message || b.callback_query || b.edited_message)) ? b : roh;
const istTest = !!(roh.body || roh.webhookUrl);
const schluessel = String((roh.query && roh.query.schluessel)
  || (b && b.schluessel) || quelle.schluessel || '');
const cq = quelle.callback_query || null;
const m = flach ? { text: b.text } : (quelle.message || (cq && cq.message) || {});
const von = (cq && cq.from) || m.from || {};
const stimme = m.voice || m.audio || null;
// Knopfdruck aus der Auswahlliste: Die Kennung wird zur Nummer - der weitere
// Ablauf behandelt sie wie eine getippte "2" (das Werkzeug loest die Nummer aus
// seiner gemerkten Liste auf). Der Text der Bot-Nachricht ist hier NICHT gemeint.
// Alte Kennungen ("w:2") werden mitgelesen, damit alte Pruefskripte nicht stumm
// das Falsche testen.
const knopf = cq ? String(cq.data || '') : '';
const knopfNummer = (knopf.match(/^w:?(\d{1,2})$/) || [])[1] || '';
const textRoh = cq ? knopfNummer : String(m.text || '').trim();
const d = $getWorkflowStaticData('global');
// Knopfdruecke und getippte Nummern tragen keine Sprache (nur "w2" bzw. "2") -
// dann gilt die zuletzt benutzte Sprache des Chats, sonst waere die Antwort auf
// einen englischen Wunsch deutsch.
const nurZahl = /^\d{1,2}$/.test(textRoh);
const spracheJetzt = (cq || nurZahl) ? '' : (textRoh ? sprache_raten(textRoh) : '');
if (spracheJetzt) d.letzteSprache = spracheJetzt;
return [{ json: {
  chatId: String((m.chat && m.chat.id) !== undefined ? m.chat.id : ''),
  text: textRoh,
  sprache: (cq || nurZahl) ? String(d.letzteSprache || 'de') : spracheJetzt,
  knopfRoh: knopf,
  istSprache: !!stimme,
  stimmeDateiId: stimme ? String(stimme.file_id || '') : '',
  stimmeTestUrl: (stimme && stimme.test_url) ? String(stimme.test_url) : '',
  messageId: (cq && cq.message ? cq.message.message_id : m.message_id) || null,
  userName: [von.first_name, von.last_name].filter(Boolean).join(' ') || von.username || '',
  isCallback: !!cq,
  istTest, istRest, schluessel,
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
if (j.istTest) {
  // Gueltiger Schluessel genuegt: der REST-Eingang hat keinen Chat (keine ID).
  return [{ json: Object.assign({}, j, { erlaubt: true, neuerBetreiber: false }) }];
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

# Die Antwort fuer den REST-Eingang: gleiche Felder wie eine Telegram-Antwort, nur
# als JSON an den Aufrufer zurueck. Steht als Objekt-Ausdruck in den drei
# Antwort-Knoten (respondToWebhook) - n8n serialisiert das Objekt selbst.
REST_ANTWORT_JSON = ("={{ { ok: true, antwort: $json.antwort || '',"
                     " tastatur: $json.tastatur || null,"
                     " sprache: $json.sprache || $('Eingabe').first().json.sprache || 'de' } }}")

TRANSKRIPT_JS = SPRACHE_JS + r"""
// Sprachnachricht: nur den Text weitergeben, deuten laesst der Agent deuten.
// Die Sprache wird am erkannten Text neu bestimmt - bei einer englischen
// Sprachnachricht antwortet der Bot danach englisch.
const felder = $('Eingabe').item.json;
const roh = $input.first().json || {};
if (roh.error) {
  return [{ json: Object.assign({}, felder, { text: '',
    antwort: '\u26a0\ufe0f Die Sprachnachricht konnte nicht verarbeitet werden.' }) }];
}
const sauber = String(roh.text || '').replace(/\s+/g, ' ').trim();
if (!sauber) {
  const letzte = String(($getWorkflowStaticData('global') || {}).letzteSprache || 'de');
  return [{ json: Object.assign({}, felder, { text: '',
    antwort: (String(felder.sprache || letzte) === 'en'
      ? '\U0001f3a7 I did not understand that - please say it again.'
      : '\U0001f3a7 Ich habe nichts verstanden - bitte nochmal sprechen.') }) }];
}
// Die Sprache kommt aus dem ERKANNTEN Text (bei Sprachnachrichten ist der
// Originaltext leer) - sie reist ab hier als "sprache" mit.
return [{ json: Object.assign({}, felder, { text: sauber, gehoert: sauber,
  sprache: sprache_raten(sauber) }) }];
"""

GEHOERT_JS = SPRACHE_LESEN_JS + r"""
const j = $json;
return [{ json: { chatId: j.chatId || $('Eingabe').item.json.chatId,
  antwort: (EN ? '\U0001f3a7 Understood: \u00bb' : '\U0001f3a7 Verstanden: \u00bb')
    + (j.gehoert || '') + '\u00ab' } }];
"""

KEIN_ZUGANG_JS = SPRACHE_LESEN_JS + r"""
const j = $json;
return [{ json: Object.assign({}, j, { antwort: j.neuerBetreiber
  ? (EN ? '\u2705 This chat is registered as operator now. Just write what should play.'
        : '\u2705 Diesen Chat als Betreiber eingetragen. Schreib einfach, was laufen soll.')
  : (EN ? '\u26d4 No access. This bot is limited to its operator.'
        : '\u26d4 Kein Zugang. Dieser Bot ist auf den Betreiber beschraenkt.') }) }];
"""

ENDE_JS = r"""
// Sammelpunkt am Ende des Dienst-Zweigs: die Antwort des Sendens weiterreichen,
// damit der Lauf mit einer klaren Ausgabe endet (auch beim Nachsehen).
return [{ json: ($json && typeof $json === 'object') ? $json : {} }];
"""

KEIN_TEXT_JS = SPRACHE_LESEN_JS + r"""
// Nachricht ohne Text (Knopfdruck, Bild, Sticker) - nichts zu steuern.
const j = $('Eingabe').first().json;
return [{ json: { chatId: j.chatId,
  antwort: EN
    ? 'I did not understand that. For example write: play In Extremo Santa Maria.'
    : 'Das habe ich nicht verstanden. Schreib zum Beispiel: spiele In Extremo Santa Maria.',
  tastatur: null } }];
"""

DIENST_ART_JS = r"""
// Gehoert die Nachricht zu einem Dienst? Dann uebernimmt das jeweilige Modul im
// Dienst ddd-radio (playlist.py fuer Wiedergabelisten, meldungen.py fuer das
// Postfach des Suchbots und die Ansagen). Nur eindeutige Faelle werden dorthin
// geleitet, alles andere laeuft wie bisher durch Analyse und Agent.
const j = $json || {};
const KNOPF = /^(?:p[0-9]{1,2}|pa|pk|pf|px|l[0-9]{1,2}|j|n|v)$/;
// Knoepfe der Meldungs-Karte: m<kennung> = vorlesen, x<kennung> = verwerfen
const MELDUNG_KNOPF = /^([mx])(m[0-9]{6}-[0-9]{4})$/;
const LISTENWORT = /(playlist|wiedergabeliste)/i;
const LISTE = /\b(liste|listen)\b/i;
const TUN = /\b(bau\w*|erstell\w*|erzeug\w*|anlegen|mach\w*|nimm\w*|fueg\w*|füg\w*|hinzu|spiel\w*|start\w*|lass\w*|leer\w*|entleer\w*|loesch\w*|lösch\w*|entfern\w*|benenn\w*|nenn\w*|umbenenn\w*|zeig\w*|inhalt|welche\w*|was ist|gibt es|sind|starten|abspielen|an hoeren|anhoeren)\b/i;
const text = String(j.text || '');
const roh = String(j.knopfRoh || '');
let art = '';
let kennung = '';
if (j.isCallback) {
  const meldung = MELDUNG_KNOPF.exec(roh);
  if (meldung) {
    art = meldung[1] === 'm' ? 'meldung-ansagen' : 'meldung-verwerfen';
    kennung = meldung[2];
  } else if (KNOPF.test(roh)) {
    art = 'listen-knopf';
  }
}
if (!art && text && (LISTENWORT.test(text) || (LISTE.test(text) && TUN.test(text)))) {
  art = 'listen-befehl';
}
return [{ json: Object.assign({}, j, { dienstArt: art, meldungKennung: kennung }) }];
"""

# Die Meldungs-Karte an den Betreiber: Text und zwei Knoepfe je Meldung.
MELDUNG_KARTE_JS = r"""
// Baut aus den neuen Meldungen eine Telegram-Karte mit Knoepfen. Der Text geht
// mit parse_mode HTML raus, deshalb werden spitze Klammern maskiert.
const d = $json || {};
const offen = Array.isArray(d.meldungen) ? d.meldungen : [];
if (!offen.length) return [{ json: { leer: true } }];

const zeichen = { wetter: '\u26c5', nachrichten: '\U0001f4f0', rss: '\U0001f4e1',
  verkehr: '\U0001f6a7', hinweis: '\U0001f4a1', musik: '\U0001f3b5', sonstiges: '\U0001f4dd' };
const kopfe = { wetter: 'Wetter', nachrichten: 'Nachrichten', rss: 'Feed',
  verkehr: 'Verkehr', hinweis: 'Hinweis', musik: 'Musik', sonstiges: 'Meldung' };
const entkommen = (s) => String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const m = offen[0];
const kopf = kopfe[m.art] || 'Meldung';
const zeilen = [
  (zeichen[m.art] || '\U0001f4dd') + ' <b>' + (m.wichtig ? 'Wichtig: ' : '') + entkommen(kopf) + '</b>',
];
if (m.titel) zeilen.push('<i>' + entkommen(m.titel) + '</i>');
zeilen.push('');
zeilen.push(entkommen(String(m.text || '').slice(0, 600)));
zeilen.push('');
zeilen.push('Sprechen lassen (' + String(m.vorschau || '').length + ' Zeichen Vorschau) oder verwerfen?');
if (offen.length > 1) zeilen.push('(' + (offen.length - 1) + ' weitere Meldung(en) im Postfach)');

const tastatur = { inline_keyboard: [[
  { text: '\u25b6\ufe0f Vorlesen', callback_data: 'm' + m.id },
  { text: '\U0001f5d1\ufe0f Verwerfen', callback_data: 'x' + m.id },
]] };
// Die Kennung wird spaeter als "angeboten" gemerkt (kein zweites Angebot).
const angeboten = offen.map((e) => e.id);

const merker = $getWorkflowStaticData('global');
const erlaubte = Array.isArray(merker.erlaubte) ? merker.erlaubte
  : (merker.erlaubte ? [merker.erlaubte] : []);
return [{ json: { chatId: String(erlaubte[0] || ''),
  antwort: zeilen.join('\n'), tastatur: tastatur, bearbeiten: false,
  nachrichtId: null, angeboten: angeboten,
  vorschau: String(m.vorschau || m.text || '').slice(0, 400) } }];
"""

LISTEN_ANTWORT_JS = r"""
// Antwort des Listen-Moduls fuer Telegram aufbereiten.
// bearbeiten=true (Menue) laesst die Nachricht stehen und aendert nur Text und
// Knoepfe - sonst kommt bei jedem Antippen eine neue Nachricht dazu.
// Der Text geht mit parse_mode HTML an Telegram: spitze Klammern muessen daher
// maskiert werden. Titel wie "AC/DC - <Song>" haben den Versand sonst mit
// "can't parse entities" abgebrochen (am 2026-09-20 passiert).
const roh = $json || {};
const e = $('Eingabe').first().json;
let text = String(roh.antwort || '').trim();
if (!text) text = '\u26a0\ufe0f Das Listen-Modul hat nicht geantwortet.';
text = text.replace(/\*\*/g, '').replace(/`/g, '')
           .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const bearbeiten = !!roh.bearbeiten && !!e.messageId;
return [{ json: { chatId: e.chatId, antwort: text, tastatur: roh.tastatur || null,
  bearbeiten, nachrichtId: e.messageId || null } }];
"""

ANTWORT_JS = SPRACHE_LESEN_JS + r"""
// Antwort fuer Telegram aufbereiten (HTML, keine Sternchen).
let text = String($json.antwort || '').trim();
if (!text) text = EN
  ? 'I did not understand that. For example say: play In Extremo Santa Maria.'
  : 'Das habe ich nicht verstanden. Sag zum Beispiel: spiele In Extremo Santa Maria.';
text = text.replace(/\*\*/g, '').replace(/^#+\s*/gm, '').replace(/`/g, '');
return [{ json: { chatId: $json.chatId || $('Eingabe').first().json.chatId, antwort: text,
  tastatur: $json.tastatur || null } }];
"""

# ============================================================ Stufe 1: Analyse

PLANEN_SYSTEM = """Du zerlegst die Anweisung des Betreibers in einzelne Befehle. Antworte NUR mit
JSON - kein Text davor oder danach, keine Erklaerung, keine Code-Umrandung.

Der Betreiber schreibt DEUTSCH ODER ENGLISCH (derselbe Bot, derselbe Chat). Verstehe
beides. Die Feldwerte deiner Antwort bleiben deutsch wie im Format unten (art, einreihen,
ansagen, bestaetigt ...); Suchbegriffe, Orte und Themen uebernimmst du woertlich, auch
englisch ("play In Extremo" -> {"art": "spielen", "suchtext": "In Extremo"}).

Format:
{"befehle": [
  {"art": "spielen", "suchtext": "Interpret und/oder Titel", "einreihen": false},
  {"art": "richtung", "richtung": "party"},
  {"art": "programm", "frage": "was laeuft gerade"},
  {"art": "ansage", "text": "frei gesprochener Text"},
  {"art": "recherche", "suche": "wetter", "wort": "Marbach am Neckar", "ansagen": true},
  {"art": "recherche", "suche": "ueberblick", "themen": "ki, raumfahrt", "quellen": "heise golem", "ansagen": true},
  {"art": "verwalten", "auftrag": "Wiedergabeliste Test anlegen", "bestaetigt": false}
]}

REGELN
1. Ein Befehl pro Aufgabe, in der Reihenfolge, in der sie genannt wurden. Auch viele
   Aufgaben bleiben viele Befehle - bis zu zehn sind in Ordnung. Fasse NIE zwei Aufgaben
   zu einem Befehl zusammen, und lasse keine Aufgabe weg.
2. art=spielen: konkreter Titel oder Interpret. einreihen=true nur bei "danach", "spaeter",
   "anschliessend", "hinterher" - englisch "then", "later", "after that" - sonst false.
   Bei mehreren Titeln in einer Nachricht bleibt einreihen false (die Reihenfolge macht der
   Bot selbst: der erste sofort, der Rest danach).
3. art=richtung: Stimmung, Genre oder Jahrzehnt. Uebersetze auf EINES dieser Worte: party, dance,
   rock, pop, metal, hiphop, electronic, disco, punk, grunge, folk, blues, jazz, klassik,
   schlager, deutschrap, ruhig, hart, 90er, 80er. "peppig"/"flott"/"Tempo" -> party,
   "entspannt"/"ruhig" -> ruhig, "hart"/"laut" -> metal. Ein Stimmungswunsch bleibt IMMER
   art=richtung, auch wenn er beilaeufig klingt ("mach mal was peppiges" -> party).
4. art=programm: Fragen zum Programm ("was laeuft", "was kommt danach", "wie viele Zuhoerer").
5. art=ansage: der Betreiber will einen FREI FORMULIERTEN Text im Radio hoeren - "sag durch: ...",
   "lies folgenden Text vor: ...", englisch "announce: ...", "say on air: ...", "read this out: ...".
   "text" ist der Text, der gesprochen werden soll, woertlich und in der Sprache des
   Betreibers. NICHT fuer Musikwuensche, Fragen oder Nachrichten aus dem Netz (dafuer recherche).
5. art=recherche: etwas nachschlagen und im Radio ansagen - Wetter, Nachrichten, ein Feed, ein
   Ueberblick oder eine Kurzinfo. "suche" ist wetter, nachrichten, rss, wikipedia oder
   ueberblick. "wort" ist der Ort ("wetter fuer Marbach am Neckar" -> suche=wetter, wort="Marbach
   am Neckar"), das Stichwort (wikipedia) oder die Feed-Adresse. "ansagen" ist true, wenn der
   Betreiber die Meldung im Radio hoeren will ("suche nach dem wetter fuer X", "lies die
   nachrichten vor") - false nur bei "nur suchen", "zeig mir", "nicht vorlesen".
   Sonderfall Ueberblick: Das Wort "ueberblick" (auch "gib mir einen ueberblick",
   "nachrichtenueberblick", "rundumblick", "rundschau", "themen: ...") heisst IMMER
   suche=ueberblick. Der Betreiber nennt dabei THEMEN, zu denen gesucht werden soll; jedes Thema
   kommt einzeln in "themen", Komma getrennt ("ueberblick ki, raumfahrt" -> themen="ki, raumfahrt").
   Ohne genannte Themen bleibt "themen" leer. "quellen" nennt optional die gewuenschten Quellen
   (tagesschau, heise, heise-security, spiegel, deutschlandfunk, ntv, faz, welt, tagesspiegel, taz,
   mdr, swr, golem, netzpolitik, t3n, computerbase, scinexx, ingenieur, sport, wetter) - leer
   lassen, wenn keine genannt sind. Eine Laenge wird NICHT vorgegeben: der Beitrag ist so lang,
   wie die gefundenen Meldungen sind.
6. art=verwalten: alles am Sender selbst (Wiedergabelisten, Anlagen, Nutzer, Rollen, Sicherungen,
   Einstellungen, Berichte, Medien, Streamer). Schreibe den Auftrag vollstaendig in eigenen Worten
   in "auftrag".
7. bestaetigt=true NUR, wenn der Betreiber gerade ausdruecklich zugestimmt hat ("ja", "mach das",
   "ok, leg an") und sich das auf einen Auftrag bezieht, den der Bot vorher zur Bestaetigung
   vorgelegt hat. Sonst false. Nimm den Auftrag dann wortgleich aus deiner letzten Antwort
   (oben mitgeschickt) - schreibe nicht nur "bestaetigen".
8. Verhoerte Namen dem naechstliegenden Interpreten zuordnen. Nichts erfinden.
9. Mehrere Schritte einer zusammenhaengenden Aufgabe ("lege eine Wiedergabeliste an und fuelle sie
   mit Rock") bleiben EIN Befehl art=verwalten - nicht zerlegen. Musik und Recherche in einer
   Nachricht sind aber ZWEI Befehle ("spiele X und suche nach dem wetter fuer Y").
10. Steht in der Nachricht keine Aufgabe, gib {"befehle": []} zurueck.

/no_think"""

BEFEHLE_LESEN_JS = SPRACHE_LESEN_JS + r"""
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
  d.lauf.fehler = roh ? (EN ? 'analysis unreadable' : 'Analyse unlesbar')
    : (roh === '' ? (EN ? 'analysis returned nothing' : 'Analyse lieferte nichts')
        : (EN ? 'analysis failed' : 'Analyse fehlgeschlagen'));
  const rohText = String(eingang.text || '').trim();
  const einreihen = /(danach|anschliessend|hinterher|spaeter|anschliessend|then|after that|later)/i.test(rohText);
  const sauber = rohText
    .replace(/\b(bitte|mal|doch|sofort|gleich|jetzt|danach|anschliessend|hinterher|spaeter|einmal|please|now|just|later|then)\b/gi, ' ')
    .replace(/^\s*(spiele|spiel|leg|lege|mach|setz|setze|pack|starte|nimm|will|moechte|ich|play|queue|spin|drop|put|add|give|want|id|like)\s+/i, '')
    .replace(/^\s*(mir|mal|me|us|the|a|an|some)\s+/i, '')
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
// Hoechstens zehn Aufgaben je Nachricht - mehr waere weder zu lesen noch schnell.
const AUFGABEN_MAX = 10;
let musik = 0;
let uebrig = 0;
befehlSchleife:
for (let i = 0; i < befehle.length; i += 1) {
  const b = befehle[i] || {};
  const art = String(b.art || '').toLowerCase();
  // "ansage" ist freier Sprechtext ("sag durch: ..." / "announce: ...") - die
  // Ausfuehrung spricht ihn ueber das Meldungs-Werkzeug.
  if (!['spielen', 'richtung', 'programm', 'recherche', 'verwalten', 'ansage', 'direkt'].includes(art)) continue;
  if (ausgabe.length >= AUFGABEN_MAX) { uebrig += 1; continue; }
  // Mehrere Musikwuensche in einer Nachricht: der ERSTE laeuft sofort, alle weiteren
  // werden eingereiht. Sonst schneidet jeder Wunsch den vorigen ab, und die Pruefung
  // meldet die ersten als nicht erledigt (am 2026-09-20 gemessen).
  if (art === 'spielen' || art === 'richtung') {
    if (musik > 0) b.einreihen = true;
    musik += 1;
  }
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
if (uebrig) {
  d.lauf.fehler = (d.lauf.fehler ? d.lauf.fehler + '; ' : '')
    + 'Nur die ersten ' + AUFGABEN_MAX + ' Aufgaben bearbeitet';
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
// Vorschaltstufe ohne Sprachmodell. Sie versteht DEUTSCH UND ENGLISCH -
// in einem Chat. Erkannt werden:
//   wunsch      "spiele X", "danach X", "X bitte", "play X", "queue X", "X please"
//   steuerung   "naechster", "weiter", "pause", "lauter",
//               "sender neu starten/starten/stoppen" - englisch "next",
//               "skip", "resume", "volume up", "restart the station" ...
//   status      "was laeuft", "status" - englisch "what is playing",
//               "how many listeners", "what comes next"
// Die Sprache der Antwort kommt aus dem Eingang (Feld "sprache") und wird hier
// nicht neu bestimmt. Alles andere (Verwaltung, Richtungen wie "was peppiges",
// mehrere Auftraege) geht unveraendert an die Analyse.
const eingang = $json || {};
const d = $getWorkflowStaticData('global');
const roh = String(eingang.text || '');

function norm(t) {
  return String(t || '').toLowerCase()
    .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
    .replace(/[^a-z0-9: ]+/g, ' ').replace(/\s+/g, ' ').trim();
}

// Dritter Eintrag je Zeile: die Sprache, in der der Wortlaut zu Hause ist. Sie
// entscheidet bei einem Treffer ueber die Sprache der Antwort ("restart" ->
// englische Antwort, "neustart" -> deutsche), auch wenn der Satz sonst keine
// Merkmale traegt.
const STEUER = [
  ['skip', /^(wechsel|wechsle|aendere|naechst\w*|ueberspring\w*|spring|weiter zum naechsten|titel wechseln|song wechseln|mach den naechsten|zum naechsten)\b[\w\s:]{0,14}$/, 'de'],
  ['skip', /^(song|titel|lied|track)\s*(wechseln|ueberspringen|vor|skip)$/, 'de'],
  ['skip', /^(next|skip|skip this|next one|next song|next track|jump to the next)\b[\w\s:]{0,14}$/, 'en'],
  ['play', /^(weiter|weiter spielen|play weiter|abspielen|fortsetzen|weiterlaufen|mach weiter|spiel weiter)\b[\w\s]{0,12}$/, 'de'],
  ['play', /^play$/, 'en'],
  ['play', /^(continue|resume|keep playing|play on|go on)\b[\w\s]{0,12}$/, 'en'],
  ['pause', /^(pause|pausieren|anhalten|halt|stopp|stop|unterbrechen|kurz pause|musik aus)\b[\w\s]{0,6}$/, 'de'],
  ['pause', /^(pause the music|silence|quiet please|stop the music)\b[\w\s]{0,6}$/, 'en'],
  ['lautstaerke', /^(lauter|leiser|laut|leise|lautstaerke|ton lauter|ton leiser|mach lauter|mach leiser|leiser machen|lauter machen)\b[\w\s]{0,10}$/, 'de'],
  ['lautstaerke', /^(volume|volume up|volume down|louder|quieter|turn it up|turn it down)\b[\w\s]{0,10}$/, 'en'],
  ['restart', /^(neustart|sender neu starten|radio neu starten|stream neu starten|starte den sender neu|starte den stream neu|sender neustarten|alles neu starten|neu starten)\b[\w\s]{0,12}$/, 'de'],
  ['restart', /^(restart|restart the (station|stream|radio)|reboot)\b[\w\s]{0,12}$/, 'en'],
  ['start', /^(sender starten|stream starten|radio starten|starte den sender|starte den stream|sender an|radio an|lauf wieder|start)\b[\w\s]{0,10}$/, 'de'],
  ['start', /^(start the (station|stream|radio)|turn on the (station|radio))\b[\w\s]{0,10}$/, 'en'],
  ['stop', /^(sender stoppen|stream stoppen|radio stoppen|sender aus|radio aus|stream aus|alles stoppen|sender abschalten)\b[\w\s]{0,10}$/, 'de'],
  ['stop', /^(stop the (station|stream|radio)|turn off the (station|radio|stream))\b[\w\s]{0,10}$/, 'en'],
];
const STATUS = /^(was laeuft|was laeuft gerade|was spielt|welcher (song|titel|interpret) laeuft|was ist das fuer ein (song|titel)|status|zustand|sender status|wie ist der zustand|laeuft der (sender|stream|das radio)|laeuft das radio|laeuft der stream|wie viele (hoeren|hoerer|zuhoerer|leute|menschen)|wieviele (hoeren|hoerer|zuhoerer|leute)|wer hoert|wie ist die auslastung|programm|was kommt danach|welcher titel kommt|whats playing|what is playing|what is playing right now|whats on|what is on|now playing|what comes next|whats next|what is next|what s playing|what s on|what s next|which song is playing|what song is playing|current (song|track|title)|how many listeners|who is listening)\b/;
const FEHLER = /\b(fehler|problem|stoerung|offline|ausgefallen|abgestuerzt|geht nicht|laeuft nicht|funktioniert nicht|klappt nicht|spinnt|haengt|kein ton|keine verbindung|down|tot|error|not working|is down|no sound|broken)\b/;
const WUNSCH_VORN = /^(spiele|spiel|leg|lege|mach|setz|setze|pack|starte|wechsel|wechsle|aendere|nimm|hoere|hor|zeig|ich will|ich moechte|play|spin|drop|give me|i want|id like|i would like|can you play|could you play|please play)\b\s*(mal |mir |bitte |doch |some |the |a |me |us |please |now |to |hear )*/;
const WUNSCH_HINTEN = /^(danach|danach mal|spaeter|anschliessend|hinterher|als naechstes|then|after that|afterwards|later|next|queue|add|put on|play it later)\b\s*(mal |bitte |please |play |it )*/;
const WUNSCH_SUFFIX = /^[\w\s:]{2,40}(bitte|mal|please|now)$/;
const VERWALTUNG = /\b(wiedergabeliste|playlist|playlists|anlage|anlegen|erstelle|erstellen|create|loesche|loeschen|entferne|nutzer|benutzer|user|users|konto|accounts?|rolle|rollen|roles?|sicherung|backup|backups|einstellung|einstellungen|settings?|bericht|report|berichte|reports?|medien|media|mount|mounts|streamer|streamers|webhook|webhooks|speicher|storage|zertifikat|certificates?|passwort|passwords?|api schluessel)\b/;
const MEHRFACH = /\bund\b.*\b(danach|dann|spaeter|anschliessend|hinterher)\b/;
// Postfach-Fragen ("was gibt es fuer Meldungen", "was liegt im Postfach") beantwortet
// der Schnellweg selbst - das Modell hielt "Meldungen" sonst fuer Nachrichten und
// liess ungefragt eine Nachricht im Radio sprechen (gemessen 45 s, am 2026-09-20).
const POSTFACH_WORT = /\b(postfach|meldungen|mitteilungen|messages?|mailbox|inbox)\b/;
const POSTFACH_FRAGE = /\b(was|welche|wieviele|wie viele|gibt es|liegen|warten|liste|zeig|alle|offen|da|what|which|how many|are there|open|any|list|show|all|waiting|pending)\b/;
const POSTFACH_VERBOT = /\b(suche|such|hol|hole|lies|vorlesen|ansagen|sag|spiele|wetter|feed|rss|nachrichten|search|find|fetch|read|announce|say|tell|play|weather|news)\b/;
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
  '80s': '80er', '90s': '90er', '70s': '70er', eighties: '80er', nineties: '90er',
  seventies: '70er',
  // Englische Wortlaute - dieselben Richtungen, nur anders benannt.
  upbeat: 'party', lively: 'party', feelgood: 'party', fun: 'party',
  calm: 'ruhig', quiet: 'ruhig', relaxed: 'ruhig', relaxing: 'ruhig', mellow: 'ruhig',
  peaceful: 'ruhig', easy: 'ruhig', soft: 'ruhig',
  slow: 'langsam', romantic: 'romantisch', love: 'liebe', lovesongs: 'liebe', sad: 'traurig',
  ballads: 'balladen', hard: 'hart', loud: 'hart', heavy: 'hart', aggressive: 'aggressiv',
  rocking: 'rock', classical: 'klassik', german: 'deutsch',
};
// Fuellwoerter, die neben einem Stimmungswort stehen duerfen ("was Peppiges", "play some rock").
const FUELL = ['was', 'etwas', 'irgendwas', 'mal', 'mir', 'bitte', 'doch', 'musik', 'zeug',
  'sachen', 'kram', 'richtung', 'sorte', 'thema', 'aus', 'fuer', 'mit', 'ein', 'eine', 'einen',
  'der', 'die', 'das', 'den', 'dem', 'sommer', 'schnell',
  'some', 'any', 'a', 'the', 'me', 'please', 'now', 'music', 'song', 'songs', 'track', 'tracks',
  'stuff', 'something', 'anything'];
const ZU_VIEL = ['raus', 'rein', 'weg', 'runter', 'ab', 'aus', 'alles', 'es', 'das', 'die', 'den',
  'dem', 'der', 'sie', 'ihn', 'ihm', 'nochmal', 'genau', 'richtig', 'wieder', 'jetzt',
  'it', 'that', 'this', 'them', 'these', 'those', 'more', 'again', 'everything', 'one'];
// Mengenangaben: "spiele drei Lieder von Rammstein" ist keine Titelsuche. Ohne diese
// Sperre schickte der Schnellweg den ganzen Satz als Suchtext ans Werkzeug und der
// Auftrag lief ins Leere (vorher schon so, am 2026-09-20 beim Testen aufgefallen).
const MENGE = /\b(lieder|lied|songs|song|titel|tracks|track|tunes|tune|stueck|stuecke|mehrere|einige|jeweils|ein paar|several|a few|couple|two|three|four|five|six|seven|eight|nine|ten|zwei|drei|vier|fuenf|sechs|sieben|acht|neun|zehn)\b|\d{1,2}\s*(lieder|songs|titel|tracks|stueck|tunes)/;

// Fuellwoerter und Befehlsreste wegschneiden: "wechsel song auf: X" -> "X".
// Englisch genauso: "play the song X please" -> "X".
function saeubern(rest) {
  let r = norm(rest);
  for (let i = 0; i < 3; i += 1) {
    r = r.trim();
    r = r.replace(/^(den|die|das|dem|ein|einen|der)\s+(song|titel|lied|track|musik|stueck)\b/, ' ');
    r = r.replace(/^(song|titel|lied|track|musik|stueck)\b/, ' ');
    r = r.replace(/^(the|a|an)\s+(song|track|tune|music|one|title)\b/, ' ');
    r = r.replace(/^(song|track|tune|music|title)\b/, ' ');
    r = r.replace(/^(auf|zu|an|mit|in|bei)\b\s*:?\s*/, ' ');
    r = r.replace(/^(mir|mal|bitte|doch|eben|kurz|noch|sofort|gleich|jetzt|schnell|denn|me|us|please|just|some|any)\b\s*/, ' ');
    r = r.replace(/^(was|etwas|irgendwas)\b\s*(von|fuer|aus|mit)?\s*/, ' ');
    r = r.replace(/^(von|fuer|aus)\b\s*/, ' ');
    r = r.replace(/^(to hear|to listen to|hear|listen to|to)\b\s*/, ' ');
    r = r.replace(/\s+(auf|an|bitte|mal|sofort|gleich|jetzt|zu|hoeren|hoere|spielen|laufen|anhoeren|raus|rein)\b\s*\.?$/, ' ');
    r = r.replace(/\s+(please|now|for me|on|it)\b\s*\.?$/, ' ');
  }
  return r.replace(/\s+/g, ' ').replace(/^[ :-]+|[ :-]+$/g, '');
}

// Erkannt: Merker schreiben (ohneKi/schlicht) und das Element fuer die Schleife bauen.
// spracheWahl ist der Sprachmerker des erkannten Wortlauts (siehe STEUER); fehlt er,
// gilt die am Eingang erkannte Sprache.
function erkannt(art, befehl, spracheWahl) {
  const sp = spracheWahl || spracheEingang;
  d.lauf = { befehle: [{ nr: 1, art: befehl.art, befehl: befehl, ausgabe: '', ok: null,
    grund: '', versuche: 0 }], fehler: '', ohneKi: true, schlicht: true, sprache: sp };
  return [{ json: { chatId: eingang.chatId, text: eingang.text, nr: 1, anzahl: 1,
    art: befehl.art, befehl: befehl, kurz: art, sprache: sp } }];
}

// Die Sprache aus dem Eingang (Feld "sprache" aus EINGABE_JS/TRANSKRIPT_JS).
const spracheEingang = String((eingang && eingang.sprache) || 'de') === 'en' ? 'en' : 'de';

const n = norm(roh);
if (!n) return [{ json: Object.assign({}, $json, { kurz: null }) }];
const kern = n.replace(/^((bitte|mal|eben|schnell|jetzt|denn|please|now|just|den|die|das|mir|noch)\s+)+/, '');

for (const paar of STEUER) {
  if (paar[1].test(n) || paar[1].test(kern)) {
    return erkannt('steuerung', { art: 'steuerung', steuerung: paar[0] }, paar[2]);
  }
}
if (POSTFACH_WORT.test(n) && (POSTFACH_FRAGE.test(n) || n.split(' ').length <= 3)
    && !POSTFACH_VERBOT.test(n)) {
  return erkannt('postfach', { art: 'postfach', frage: n });
}
// Ueberblick: Themen sammeln, zu denen der Bot Meldungen sucht ("ueberblick ki,
// raumfahrt", "themen: ki und raumfahrt", auch "ueberblick aus heise und golem").
// Eine Zeitangabe gibt es nicht mehr - der Beitrag waechst mit dem, was zu den
// Themen gefunden wird.
const UEBERBLICK_WORT = /\b(ueberblick|rundumblick|rundschau|nachrichten ?ueberblick|news ?ueberblick|themenueberblick)\b/;
const THEMEN_WORT = /^\s*(themen|thema)\s*[:\-]?\s+\S/;
// "aber lies es nicht vor" / "nur zeigen" darf NICHT sprechen - dann entscheidet die
// Analyse (art=recherche mit ansagen=false), und der Beitrag bleibt im Postfach.
const UEBERBLICK_OHNE_ANSAGE = /(nicht vorlesen|nicht ansagen|nicht sprechen|ohne ansage|nur (zeigen|suchen|ablegen)|nicht im radio)/;
if ((UEBERBLICK_WORT.test(n) || THEMEN_WORT.test(n)) && n.split(' ').length <= 20
    && !UEBERBLICK_OHNE_ANSAGE.test(n)) {
  // Themen aus dem ORIGINAL lesen: norm() entfernt Kommas, damit waeren aus
  // "ki, raumfahrt" zwei Woerter eines Themas geworden (am 2026-09-21 gemessen).
  const original = String(roh || '');
  // Kein \b vor dem Umlaut: \b ist in JavaScript ASCII-basiert und wuerde vor
  // "überblick" nicht greifen.
  const wort = /(überblick|ueberblick|rundumblick|rundschau|nachrichtenüberblick|nachrichtenueberblick|newsüberblick|themenüberblick)/i;
  let rest = original.replace(wort, ' ');
  if (rest === original) rest = original.replace(/^\s*(themen|thema)\s*[:\-]?\s*/i, ' ');
  let quellen = '';
  const aus = rest.match(/\baus\s+(.+)$/i);
  if (aus) {
    quellen = aus[1].replace(/\b(und|sowie|plus|dem|der|die|das|den|vom)\b/gi, ' ')
      .replace(/\s+/g, ' ').trim();
    rest = rest.slice(0, aus.index);
  }
  const themen = rest
    .replace(/\b(bitte|mal|mir|gib|einen|eine|den|dem|der|die|das|zum|zu|über|ueber|themen|thema|nachrichten|news|aktuelle[nrs]?|kurze[nrs]?|neue[nrs]?|gib mir|über das|ueber das)\b/gi, ' ')
    .replace(/[;\-–]+/g, ', ')
    .replace(/\s*,\s*/g, ', ')
    .replace(/\s+/g, ' ')
    .replace(/^[\s,]+|[\s,]+$/g, '')
    .trim();
  return erkannt('ueberblick', { art: 'ueberblick', themen: themen, quellen: quellen });
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
// Zuvor die gesprochenen Formen abfangen: "ich spiele mir etwas von X",
// "was von X", "... von X spielen". Ohne das landen Sprachnachrichten in der
// kompletten KI-Kette (gemessen 163 s fuer "Ich spiele mir etwas von Scooter.").
const SPRACH_VORN = /^(ich|kannst du|kannst du mir|koenntest du|koennte ich|kann ich|mach mir|mach mal|spiel mir|spiele mir|gib mir|moechte|will|wollte|haette gern|haett gern|haette|wuerde gern|wuerde|mag|can you|could you|please|id like|i would like|i want|give me)\s+/;
const SPRACH_HINTEN = /\s+(spielen|spiele|anmachen|anschmeissen|abspielen|hoeren|laufen|laufen lassen|an|rein|raus|for me|please|now)$/;
const STIMMUNG_VERBOT = MENGE;
let gesprochen = n.replace(SPRACH_VORN, '').replace(SPRACH_HINTEN, '').trim();
// Zweiter Durchgang fuer "ich moechte was von X" - nach "ich" folgt die Absicht.
if (gesprochen !== n && SPRACH_VORN.test(gesprochen)) {
  gesprochen = gesprochen.replace(SPRACH_VORN, '').replace(SPRACH_HINTEN, '').trim();
}
if (gesprochen !== n && !VERWALTUNG.test(gesprochen) && !MEHRFACH.test(gesprochen)) {
  const vorn2 = gesprochen.match(WUNSCH_VORN);
  const ohneVerb2 = gesprochen.replace(WUNSCH_VORN, ' ').replace(WUNSCH_HINTEN, ' ').trim();
  const m2 = ohneVerb2.match(/^(?:mal |mir )*(?:was|etwas|irgendwas)\s+(?:von|fuer|aus)\s+(.+)$/);
  const rest2 = vorn2 ? gesprochen.slice(vorn2[0].length) : (m2 ? m2[1] : null);
  if (rest2 !== null) {
    const s2 = saeubern(rest2);
    if (s2.length >= 2 && ZU_VIEL.indexOf(s2) < 0 && s2.indexOf(' und ') < 0
        && !STIMMUNG_VERBOT.test(s2)) {
      return erkannt('wunsch', { art: 'direkt', suchtext: s2, einreihen: false });
    }
  }
}

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
    if ((s.length >= 2 || zahl) && ZU_VIEL.indexOf(s) < 0 && s.indexOf(' und ') < 0
        && !MENGE.test(s)) {
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

STEUERUNG_ANTWORT_JS = SPRACHE_LESEN_JS + r"""
// Antwort auf einen Kurzbefehl (Basissteuerung) - ohne Sprachmodell.
// Zweisprachig: die Texte folgen der Sprache des Chats (Feld "sprache").
const d = $getWorkflowStaticData('global');
const item = $('Schleife').first().json || {};
const aktion = String((item.befehl || {}).steuerung || '');
const r = $json || {};
const fehler = !!r.error || r.success === false;

let text = '';
if (aktion === 'pause') {
  text = EN
    ? 'The station cannot pause - every device stops its own playback. Say "continue" '
      + 'when the stream should keep playing, or "next track".'
    : 'Am Sender gibt es kein Pausieren - anhalten kann jedes Geraet selbst. '
      + 'Sag "weiter", wenn der Sendeteil weiterspielen soll, oder "naechster Titel".';
} else if (aktion === 'lautstaerke') {
  text = EN
    ? 'The volume is set on your own device - the station cannot change it.'
    : 'Die Lautstaerke stellt jedes Geraet selbst ein - am Sender laesst sie sich nicht aendern.';
} else if (aktion === 'skip') {
  text = fehler
    ? (EN ? 'ERROR: The station did not accept the skip.' : 'FEHLER: Der Sender nimmt den Sprung nicht an.')
    : (EN ? 'The next track is starting.' : 'Naechster Titel laeuft an.');
} else if (aktion === 'play') {
  text = fehler
    ? (EN ? 'ERROR: The stream did not start.' : 'FEHLER: Der Sendeteil laeuft nicht an.')
    : (EN ? 'The stream is running.' : 'Der Sendeteil laeuft.');
} else if (aktion === 'start') {
  text = fehler
    ? (EN ? 'ERROR: The stream could not be started.' : 'FEHLER: Der Sendeteil liess sich nicht starten.')
    : (EN ? 'The stream is started.' : 'Der Sendeteil ist gestartet.');
} else if (aktion === 'stop') {
  text = fehler
    ? (EN ? 'ERROR: The stream could not be stopped.' : 'FEHLER: Der Sendeteil liess sich nicht stoppen.')
    : (EN ? 'The stream is stopped.' : 'Der Sendeteil ist gestoppt.');
} else if (aktion === 'restart') {
  text = fehler
    ? (EN ? 'ERROR: The stream could not be restarted.' : 'FEHLER: Der Sendeteil liess sich nicht neu starten.')
    : (EN ? 'The stream was restarted.' : 'Der Sendeteil wurde neu gestartet.');
} else {
  text = fehler
    ? (EN ? 'ERROR: The command did not get through.' : 'FEHLER: Der Befehl kam nicht durch.')
    : (EN ? 'Done.' : 'Erledigt.');
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

POSTFACH_ANTWORT_JS = SPRACHE_LESEN_JS + r"""
// Antwort auf eine Postfach-Frage - ohne Sprachmodell, ohne Ansage.
// Die Huelle ist zweisprachig; die Meldungen selbst kommen deutsch aus dem Dienst
// (Nachrichten, Wetter, Feeds des Senders).
const d = $getWorkflowStaticData('global');
const item = $('Schleife').first().json || {};
const r = $json || {};
const liste = Array.isArray(r.meldungen) ? r.meldungen : [];

let text = '';
if (r.error) {
  text = EN ? 'ERROR: The mailbox is not reachable.' : 'FEHLER: Das Postfach ist nicht erreichbar.';
} else if (!liste.length) {
  text = EN ? 'There is nothing open in the mailbox.' : 'Im Postfach liegt nichts Offenes.';
} else {
  const zeilen = liste.map((m, i) => (i + 1) + '. ' + (m.wichtig ? (EN ? 'IMPORTANT ' : 'WICHTIG ') : '')
    + (m.titel || String(m.text || '').slice(0, 60)) + ' (' + (m.art || (EN ? 'message' : 'Meldung'))
    + (EN ? ', id ' : ', Kennung ') + m.id + ')');
  text = EN
    ? ('The mailbox has ' + liste.length + ' open message(s): ' + zeilen.join(' | ')
       + '. To have one read out, just name its title.')
    : ('Im Postfach ' + liste.length + ' offene Meldung(en): ' + zeilen.join(' | ')
       + '. Zum Vorlesen nenne einfach den Titel.');
}

// Der Text geht mit parse_mode HTML nach Telegram - spitze Klammern aus
// Ueberschriften wuerden den Versand sonst abbrechen (siehe Postfach-Probe).
text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const nr = Number(item.nr || 1);
const eintrag = (d.lauf && d.lauf.befehle || []).find((x) => x.nr === nr);
if (eintrag) {
  eintrag.ausgabe = text;
  eintrag.ok = !r.error;
  eintrag.versuche = (eintrag.versuche || 0) + 1;
}
return [{ json: { nr: nr, fertig: true } }];
"""

UEBERBLICK_ANTWORT_JS = SPRACHE_LESEN_JS + r"""
// Antwort des Ueberblicks festhalten (Stufe 2, Kurzweg ohne Sprachmodell).
// Der Dienst hat den Beitrag zu diesem Zeitpunkt schon gesprochen - hier kommt nur
// noch die Meldung zurueck, die in den Merker und damit in die Antwort geht.
// Der Beitrag selbst ist deutsch (Quellen des Senders); nur die Huelle wechselt.
const d = $getWorkflowStaticData('global');
const item = $('Schleife').first().json || {};
const r = $json || {};
let text = '';
if (r.error) {
  text = EN ? 'ERROR: The overview could not be fetched.'
    : 'FEHLER: Der Ueberblick liess sich nicht holen.';
} else {
  const dauer = Number(r.dauer_sekunden || 0);
  const minuten = dauer ? (dauer / 60).toFixed(1).replace('.', EN ? '.' : ',') : '';
  const themen = Array.isArray(r.themen) ? r.themen : [];
  const quellen = Array.isArray(r.quellen) ? r.quellen.length : 0;
  text = String(r.antwort || '').trim()
    || (EN
        ? ('Overview ' + (r.gesagt ? 'spoken' : 'prepared')
           + (minuten ? ' (' + minuten + ' min' : '')
           + (themen.length ? (minuten ? ', topics ' : ' (topics ') + themen.join(', ') : '')
           + (quellen ? ', ' + quellen + ' sources' : '')
           + ((minuten || themen.length || quellen) ? ')' : ''))
        : ('Ueberblick ' + (r.gesagt ? 'gesagt' : 'vorbereitet')
           + (minuten ? ' (' + minuten + ' Min' : '')
           + (themen.length ? (minuten ? ', Themen ' : ' (Themen ') + themen.join(', ') : '')
           + (quellen ? ', ' + quellen + ' Quellen' : '')
           + ((minuten || themen.length || quellen) ? ')' : '')));
  if (Array.isArray(r.ausgefallen) && r.ausgefallen.length) {
    text += EN ? (' (' + r.ausgefallen.join(', ') + ' not reachable)')
               : (' (' + r.ausgefallen.join(', ') + ' nicht erreichbar)');
  }
}
// Der Text geht mit parse_mode HTML nach Telegram - spitze Klammern maskieren.
text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const nr = Number(item.nr || 1);
const eintrag = (d.lauf && d.lauf.befehle || []).find((x) => x.nr === nr);
if (eintrag) {
  eintrag.ausgabe = text;
  eintrag.ok = !r.error;
  eintrag.versuche = (eintrag.versuche || 0) + 1;
}
return [{ json: { nr: nr, fertig: true } }];
"""

# ======================================================== Stufe 2: Ausfuehrung

AUSFUEHREN_SYSTEM = """Du fuehrst genau EINEN Befehl des Betreibers am Internetradio
"DDD-Webseite Demo" aus. Der Betreiber ist der einzige Nutzer.

SPRACHE
Der Betreiber schreibt deutsch oder englisch. Verstehe beides. Antworte in der Sprache
des Befehls (deutsch auf deutsch, englisch auf englisch) - auch die Bestaetigung.
Antworte NIE deutsch, wenn der Betreiber englisch geschrieben hat, auch wenn ein
Werkzeug oder der Sender deutsch antwortet. Die internen Werte (art,
auftrag, ansagen, bestaetigt ...) bleiben deutsch - sie sind nur fuer den Bot, nicht
fuer den Betreiber. Werkzeugaufrufe der Musik (titel_suchen, richtung_suchen,
was_laeuft) bekommen immer das Feld sprache (de oder en) mit.

WERKZEUGE
- titel_suchen, richtung_suchen, was_laeuft: Musik und Programm. Diese Werkzeuge spielen selbst.
- azura_endpunkte, azura_aufruf, azura_ueberblick: der Sender selbst (Verwaltung).
- meldungen: das Postfach (Wetter, RSS-Feeds, Nachrichten) und die Ansagen des Moderators.
  auftrag=anzeigen listet offene Meldungen NUR AUF (keine Ansage) - das ist der richtige Auftrag
  bei Fragen wie "was gibt es fuer Meldungen", "was liegt im Postfach". auftrag=lesen zeigt den
  Sprechtext, auftrag=ansagen spricht eine Meldung live in den Sender, auftrag=verwerfen legt
  sie weg, auftrag=text spricht freien Text.
- recherche: holt etwas Neues und legt es als Meldung ab - art=wetter (dann wort=Ort),
  art=nachrichten, art=rss (dann wort=Feed-Adresse), art=wikipedia (dann wort=Stichwort) oder
  art=ueberblick (dann themen=die Themen, z. B. "ki, raumfahrt", und optional quellen=gewuenschte
  Quellen). Der Ueberblick sucht zu jedem Thema in Presse, im Netz und in den Feeds und dauert
  so lange, wie das Gefundene braucht (mehrere Minuten), danach laeuft die Musik weiter.
  ansagen=true spricht die Meldung sofort in den Sender: das ist bei "suche nach dem wetter fuer
  X" und "lies die nachrichten vor" gewollt, bei "nur suchen" oder "zeig mir" nicht.

WAS IST WAS
- Frage nach dem Postfach ("was gibt es fuer Meldungen", "was liegt an") -> meldungen mit
  auftrag=anzeigen. Das listet nur auf und spricht NICHTS.
- "was gibt es Neues", "lies die Nachrichten vor" -> recherche mit art=nachrichten. Das holt
  die aktuelle Nachricht und sagt sie an (ansagen=true).
- "suche nach dem wetter fuer X" -> recherche mit art=wetter, wort=X, ansagen=true.
- "sag durch: ...", "announce: ..." -> meldungen mit auftrag=text (freier Text).
- Steht im Befehl art=ansage (Feld "text"), sprich genau diesen Text: meldungen mit
  auftrag=text und text aus dem Befehl. Nichts umformulieren, nichts ergaenzen.

WANN WIRD GESPROCHEN
Eine Ansage in den laufenden Sendebetrieb ist die Ausnahme, nicht die Regel. Gesprochen wird
NUR, wenn der Betreiber es ausdruecklich verlangt ("lies vor", "sag das an", "suche nach dem
wetter fuer X", "lies die nachrichten"). Fragen nach dem Inhalt ("was gibt es fuer Meldungen",
"was liegt an") beantwortest du als Text, ohne etwas in den Sender zu sprechen.

REGELN
1. Fuehre den Befehl aus - erklaere ihn nicht.
2. Verwaltungsauftrag: erst azura_endpunkte (Adresse nachschlagen), dann azura_aufruf.
   Aendern (POST/PUT/DELETE) nur, wenn im Befehl "bestaetigt": true steht - sonst nur lesen
   bzw. den Trockenlauf melden und in der Antwort in einfachen Worten um Erlaubnis bitten
   ("Soll ich das anlegen?"). Keine Fachbegriffe wie "bestaetigt" oder Feldnamen nennen.
3. Antworte in EINEM kurzen Satz mit dem Ergebnis - in der Sprache des Betreibers
   (deutsch oder englisch), ohne Dateipfade, ohne Technik, ohne Aufzaehlung der Werkzeuge.
4. Ging etwas schief, sag in einem Satz was.
5. Gibt ein Werkzeug eine AUSWAHLLISTE aus ("Mehrere Titel passen ..."), dann gib sie WORTGETREU
   und ZEILE FUER ZEILE weiter - jede Nummer in einer eigenen Zeile, nichts umformulieren, nichts
   zusammenziehen und nichts ergaenzen. An die Liste haengst du genau die Frage, welcher gemeint
   ist. Der Bot baut aus diesen Zeilen die Antwortknoepfe.
6. Steht im Befehl "einreihen": true, rufe titel_suchen oder richtung_suchen mit
   einreihen=true auf - der Titel darf dann nicht unterbrechen, er laeuft danach.

/no_think"""

AUSFUEHREN_TEXT = ("={{ 'Befehl: ' + JSON.stringify($json.befehl)"
                  + " + '\\nSprache des Betreibers: '"
                  + " + String(($('Zugang').first().json.sprache || 'de'))"
                  + " + '\\nAntworte in dieser Sprache (en = englisch, de = deutsch)"
                  + " - auch die Bestaetigung.\\n/no_think' }}")

ERGEBNIS_SAMMELN_JS = r"""
// Ergebnis des Befehls am Merker festhalten.
const d = $getWorkflowStaticData('global');
const nr = Number($('Schleife').first().json.nr || 0);
const text = String(($json && ($json.output || $json.text)) || '').trim();
const eintrag = (d.lauf && d.lauf.befehle || []).find((x) => x.nr === nr);
if (eintrag) {
  // Eine leere Antwort darf eine brauchbare Ausgabe NICHT loeschen. Am 2026-09-20 hat
  // der zweite Versuch die Auswahlliste ("Welchen Titel soll ich spielen?") mit
  // "(keine Ausgabe)" ueberschrieben - der Nutzer sah die Liste nie.
  const alt = String(eintrag.ausgabe || '').trim();
  if (text) eintrag.ausgabe = text;
  else if (!alt || alt === '(keine Ausgabe)') eintrag.ausgabe = '(keine Ausgabe)';
  eintrag.versuche = (eintrag.versuche || 0) + 1;
  if (Array.isArray($json.auswahl) && $json.auswahl.length) eintrag.auswahl = $json.auswahl;
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
  // Eine leere Antwort darf eine brauchbare Ausgabe NICHT loeschen. Am 2026-09-20 hat
  // der zweite Versuch die Auswahlliste ("Welchen Titel soll ich spielen?") mit
  // "(keine Ausgabe)" ueberschrieben - der Nutzer sah die Liste nie.
  const alt = String(eintrag.ausgabe || '').trim();
  if (text) eintrag.ausgabe = text;
  else if (!alt || alt === '(keine Ausgabe)') eintrag.ausgabe = '(keine Ausgabe)';
  eintrag.versuche = (eintrag.versuche || 0) + 1;
  if (Array.isArray($json.auswahl) && $json.auswahl.length) eintrag.auswahl = $json.auswahl;
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
  return !a || a === '(keine Ausgabe)' || /^(FEHLER|ERROR|KEINE TREFFER|NO MATCHES|Es steht keine Auswahlliste|Die Nummer|There is no (number|selection list))/i.test(a);
});
// Klar erledigt: jedes Werkzeug meldet seinen Erfolg selbst mit "OK: ...". Dann
// braucht es kein Sprachmodell fuer das Urteil - es wuerde nur bestaetigen, was
// schon belegt ist (kostete am 2026-09-20 gemessen 99 s je Ansage, weil das
// Modell den erfolgreichen Befehl mehrfach als "nicht ok" einstufte).
const klarErledigt = liste.length > 0 && liste.every((b) => /^OK:/i.test(String(b.ausgabe || '').trim()));
return [{ json: {
  chatId: $('Eingabe').first().json.chatId,
  befehle: liste,
  ohneKi: !!(d.lauf && d.lauf.ohneKi) || klarErledigt,
  klarerFehler: klarFehler,
  lage: {
    laeuft: song.text || 'unbekannt',
    danach: naechste,
    warteschlange: inWarteschlange.slice(0, 5),
  },
} }];
"""

PRUEFUNG_LESEN_JS = SPRACHE_LESEN_JS + r"""
// Ergebnis der Pruefung in den Merker schreiben und die fehlgeschlagenen Befehle
// fuer den Nachfass-Durchgang weitergeben.
//
// Das Sprachmodell urteilt. Liefert es nichts (leere Antwort, kein JSON), greift
// ein Regelurteil - sonst ginge ein misslungener Befehl als gelungen durch.
const d = $getWorkflowStaticData('global');
const roh = String(($json && ($json.output || $json.text)) || '').trim();
const liste = (d.lauf && d.lauf.befehle) || [];
const lage = ($('Befehle und Lage').first().json || {}).lage || {};
const STOERUNG = /fehler|error|nicht moeglich|konnte nicht|could not|nicht gefunden|keine treffer|no matches|trockenlauf|dry run|rueckfrage|question|welchen|welche|which|unbekannt|unknown|keine ausgabe|no output/i;

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

// Eine Rueckfrage an den Nutzer ist kein Fehlschlag: sie wird angezeigt (mit Knoepfen),
// aber NICHT nachgefasst.
const FRAGE_WORT = /\?|welchen|welche|welches|soll ich|frage kurz|bitte waehlen|mehrere (titel|treffer|moeglichkeiten)/i;
const STOER_WORT = /fehler|nicht moeglich|konnte nicht|nicht gefunden|keine treffer|unbekannt|abgelehnt/i;
for (const b of liste) {
  const a = String(b.ausgabe || '').trim();
  // Eine Frage an den Nutzer ist kein Fehlschlag: sie wird gezeigt (mit Knoepfen),
  // aber nicht nachgefasst - der zweite Versuch hatte die Liste geloescht.
  b.frage = !!(a && b.art !== 'verwalten' && !STOER_WORT.test(a) && FRAGE_WORT.test(a));
  if (b.frage) b.grund = b.grund || 'Rueckfrage an den Nutzer';
}
const offen = (d.lauf && d.lauf.ohneKi)
  // Kurzbefehl (ohne Sprachmodell ausgefuehrt): Urteil nach Regeln, kein zweiter Versuch.
  ? []
  : liste.filter((b) => b.ok === false && !b.frage && (b.versuche || 0) < 2);
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
  const alt = String(eintrag.ausgabe || '').trim();
  if (text) eintrag.ausgabe = text;
  else if (!alt || alt === '(keine Ausgabe)') eintrag.ausgabe = '(keine Ausgabe)';
  eintrag.versuche = (eintrag.versuche || 0) + 1;
  if (Array.isArray($json.auswahl) && $json.auswahl.length) eintrag.auswahl = $json.auswahl;
  // Der zweite Versuch ist der gueltige Stand - aber nur, wenn er etwas gesagt hat.
  if (text) {
    eintrag.ok = !/fehler|nicht moeglich|konnte nicht|nicht gefunden|keine treffer|welchen|welche/i.test(text);
    eintrag.grund = eintrag.ok ? '' : text;
  } else {
    eintrag.ok = false;
    eintrag.grund = eintrag.grund
      || (EN ? 'the retry brought no answer' : 'Nachfassen brachte keine Antwort');
  }
}
return [{ json: { nr: item.nr, fertig: true } }];
"""

ANTWORT_BAUEN_JS = SPRACHE_LESEN_JS + r"""
// Zusammenfassung aller Befehle - Erfolg und Misserfolg getrennt.
const d = $getWorkflowStaticData('global');
const liste = (d.lauf && d.lauf.befehle) || [];
// schlicht = ohne Sprachmodell ausgefuehrt (Kurzbefehl): Antwort ohne Zeichen davor.
const schlicht = !!(d.lauf && d.lauf.schlicht);
const zeilen = [];
for (const b of liste) {
  // Eine Auswahlliste darf nicht abgeschnitten werden: bei 300 Zeichen fehlten die
  // letzten Kandidaten (am 2026-09-20 gesehen - die Liste endete bei "5"). Bei vielen
  // Aufgaben wird dagegen kuerzer gehalten, sonst wird die Nachricht zu lang.
  // Traegt der Befehl eine Auswahlliste (Knoepfe), gilt die hohe Grenze - sonst
  // kappte eine englische Liste ihren Hinweissatz ("...call" statt "...als suchtext").
  const grenze = (b.frage || (Array.isArray(b.auswahl) && b.auswahl.length)) ? 1200
    : (liste.length > 4 ? 160 : 300);
  const t = (b.ausgabe || '(keine Ausgabe)').replace(/[ \t]+/g, ' ').slice(0, grenze);
  const zeichen = b.ok === false ? (b.frage ? '\u2753 ' : '\u26a0\ufe0f ') : '\u2705 ';
  zeilen.push(schlicht ? t : (zeichen + t));
}
if (!zeilen.length) zeilen.push(EN ? 'I did not find a command in that.'
  : 'Ich habe darin keinen Auftrag erkannt.');
const offen = liste.filter((b) => b.ok === false && !b.frage);
if (!schlicht && offen.length) {
  zeilen.push((EN ? 'Not done: no. ' : 'Nicht erledigt: Nr. ') + offen.map((b) => b.nr).join(', ')
    + (EN ? ' - please say it again, I will try another way.'
          : ' - sag es noch einmal, dann versuche ich es anders.'));
}
if (!schlicht && liste.some((b) => b.frage)) {
  zeilen.push(EN ? 'Tap the matching button or answer with the number.'
    : 'Tippe den passenden Knopf oder antworte mit der Nummer.');
}
const fehler = (d.lauf && d.lauf.fehler) || '';
if (fehler) zeilen.push('(' + fehler + ')');
const gesamt = zeilen.join('\n');
// Auswahlliste als anklickbare Knoepfe: callback_data "w" + Nummer (kurz genug,
// Telegram erlaubt dort 1-64 Bytes). Der Knopfdruck kommt als Nummer zurueck.
// Auswahlliste fuer Knoepfe: entweder vom Werkzeug ("auswahl") oder aus der
// nummerierten Liste im Text. Das Werkzeug kann seine Liste nur im Text mitgeben,
// wenn ein Sprachmodell dazwischen sass - dann bauen wir die Knoepfe hier.
const ausListe = (t) => {
  // Erst zeilenweise (so soll es sein), sonst aus einer zusammengezogenen Zeile
  // ("1. A, 2. B") - kleine Modelle ziehen Listen gern in eine Zeile.
  const zeilenweise = String(t || '').split('\n')
    .map((z) => z.trim().match(/^(\d{1,2})[.)]\s+(\S.*)$/)).filter(Boolean).map((m) => m[2]);
  const roh = zeilenweise.length >= 2 ? zeilenweise
    : String(t || '').replace(/\s+/g, ' ').split(/(?:^|[\s,;])\(?(\d{1,2})[.)]\s+/).slice(2).filter((_, i) => i % 2 === 0);
  return roh.map((z) => String(z)
      .split(/\s*(?:welchen|welche|welches|frage kurz|tippe|bitte waehlen|sag mir|soll ich)\b/i)[0]
      .replace(/[,;]\s*$/, '').replace(/\s*\([^)]*\)\s*$/, '').trim())
    .filter(Boolean);
};
// Knoepfe aus dem Text nur fuer Titelwahlen: eine Postfachliste ("1. ... | 2. ...")
// darf keine Knoepfe bekommen - "w1" waere dort als Liedwunsch missverstanden.
const mitListe = liste.find((b) => Array.isArray(b.auswahl) && b.auswahl.length)
  || liste.find((b) => b.frage && b.art === 'spielen' && ausListe(b.ausgabe).length >= 2);
const eintraege = mitListe
  ? ((Array.isArray(mitListe.auswahl) && mitListe.auswahl.length)
      ? mitListe.auswahl : ausListe(mitListe.ausgabe))
  : [];
const tastatur = eintraege.length >= 2
  ? { inline_keyboard: eintraege.map((t, i) => ([{
      text: String(t).slice(0, 60), callback_data: 'w' + (i + 1) }])) }
  : null;
// Fuer die naechste Nachricht merken: daran haengt "ja, mach das".
d.letzteAntwort = gesamt;
return [{ json: { chatId: $('Eingabe').first().json.chatId, antwort: gesamt,
  tastatur: tastatur } }];
"""

# ------------------------------------------------- Werkzeug-Aufgaben
# Diese Texte liest das Sprachmodell, um zu entscheiden, welches Werkzeug es
# braucht. Sie stehen im Knoten "Konfiguration" und werden von dort geholt.
AUFGABEN_WERKZEUGE = {
    "titel_suchen": 'Spielt einen Titel oder Interpreten. Eingabe: suchtext (Interpret und/oder Titel) ODER eine Nummer aus der letzten Auswahlliste, plus sprache (de oder en - die Sprache des Betreibers, damit die Antwort darin zurueckkommt). Klarer Treffer: er laeuft sofort. Mehrere verschiedene Titel: Antwort ist eine Liste (dann nachfragen). einreihen=true reiht nur ein, ohne zu unterbrechen.',
    "richtung_suchen": 'Spielt zur Stimmung, zum Genre oder Jahrzehnt den ersten passenden Titel. Eingabe: richtung (party, dance, rock, metal, ruhig, hart, 90er, 80er ...) plus sprache (de oder en). einreihen=true reiht nur ein, ohne zu unterbrechen.',
    "was_laeuft": 'Sagt, was gerade laeuft, wie lange noch, was danach kommt und wie viele Zuhoerer da sind. Eingabe: frage und sprache (de oder en). Keine weitere Eingabe.',
    "azura_endpunkte": 'Schlaegt Adressen der Senderschnittstelle nach (Stichwort, z. B. playlist, user, backup, report, mount, webhook, storage, settings, media). Immer zuerst benutzen, wenn du eine Verwaltungsaufgabe am Sender hast - Adressen und Felder nie raten.',
    "azura_aufruf": 'Ruft eine Schnittstelle des Senders auf (AzuraCast). Eingaben: methode (GET liest, POST/PUT/DELETE aendern), pfad (voll, z. B. /api/station/2/playlists), koerper (JSON, nur beim Schreiben), bestaetigt (true, wenn der Betreiber das Aendern ausdruecklich erlaubt hat). Ohne bestaetigt=true passiert beim Schreiben nichts - dann kommt nur ein Trockenlauf zurueck.',
    "azura_ueberblick": 'Ueberblick ueber den Sender: Anlagen, ob Sendeteil und Ausgabe laufen, Wiedergabelisten mit Titelzahl. Fuer Verwaltungsfragen (Zustand, Listen), nicht fuer Musikwuensche.',
    "meldungen": 'Postfach (Wetter, RSS-Feeds, Nachrichten) und Ansagen des Moderators. auftrag=anzeigen listet offene Meldungen auf - das ist KEINE Ansage. auftrag=lesen zeigt den Sprechtext einer Meldung (dann kennung angeben). auftrag=ansagen spricht die Meldung live in den Sender (dann kennung angeben, nur auf ausdruecklichen Wunsch). auftrag=verwerfen legt sie weg (dann kennung angeben). auftrag=text spricht freien Text (dann text angeben).',
    "recherche": "Holt etwas NEUES aus dem Netz und legt es als Meldung ab - Wetter, Nachrichten, ein RSS-Feed, einen Ueberblick ueber Themen oder eine Kurzinfo. NICHT fuer Fragen nach dem Postfach benutzen (dafuer meldungen mit auftrag=anzeigen). art=wetter (dann wort=Ort, z. B. 'Marbach am Neckar'), art=nachrichten (aktuellste Nachricht), art=rss (dann wort=Feed-Adresse oder Kurzname wie tagesschau, heise, spiegel), art=wikipedia (dann wort=Stichwort), art=ueberblick (dann themen=die Themen, zu denen gesucht werden soll, z. B. 'ki, raumfahrt'; optional quellen=gewuenschte Quellen wie 'heise golem'). Der Ueberblick sucht zu jedem Thema in Presse, im Netz und in den Feeds und dauert so lange, wie das Gefundene braucht. ansagen=true spricht die Meldung sofort im Radio an - das ist gewuenscht, wenn der Betreiber sie hoeren will ('suche nach dem wetter fuer X'); bei 'nur suchen' oder 'zeig mir' ansagen=false setzen.",
}

# ======================================================================= der Bot

bot = [
    n("Telegram Trigger", "n8n-nodes-base.telegramTrigger", 1.2, [-2400, 0],
      {"updates": ["message", "callback_query"], "additionalFields": {}},
      webhookId=nid(), credentials={"telegramApi": {"id": TG_CRED_ID, "name": TG_CRED_NAME}},
      **({"disabled": True} if os.environ.get("TRIGGER_AUS") else {})),
    n("Test-Eingang", "n8n-nodes-base.webhook", 2, [-2400, 240],
      {"httpMethod": "POST", "path": "ddd-webseite-test", "responseMode": "responseNode",
       "options": {}},
      webhookId=nid(), notes="Nur zum Pruefen: nimmt eine Telegram-Nachricht als JSON an; "
                              "die Antwort kommt wie beim REST-Eingang als JSON zurueck."),
    n("REST-Eingang", "n8n-nodes-base.webhook", 2, [-2400, 480],
      {"httpMethod": "POST", "path": "ddd-webseite-rest", "responseMode": "responseNode",
       "options": {}},
      webhookId=nid(),
      notes="REST-Befehl statt Telegram: POST mit {\"text\": \"...\"} und Schluessel "
            "(?schluessel=... oder Feld schluessel). Antwort kommt als JSON zurueck."),
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
               + " + " + K + ".telegram.token + '/' + ($json.result ? $json.result.file_path : '')) }}",
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

    # ------------------------------------- Wiedergabelisten (eigenes Listen-Modul)
    # Knopfdruecke und Texte rund um Wiedergabelisten laufen nicht durch Analyse
    # und Sprachmodell, sondern direkt in den Dienst ddd-radio (playlist.py).
    # Dort liegen Auswahlmenue, gemerkter Zustand und die Senderaufrufe.
    code("Dienst Art", [-2760, -1220], DIENST_ART_JS),
    wenn("Dienst?", [-2540, -1220], "={{ !!$json.dienstArt }}",
         "Ja = Knopf oder Text fuer Listen bzw. Meldungen -> eigenes Modul."),
    wenn("Meldung?", [-2540, -960], "={{ String($json.dienstArt).indexOf('meldung') === 0 }}",
         "Ja = Meldung vorlesen oder verwerfen, sonst Wiedergabeliste."),
    n("Meldung Dienst", "n8n-nodes-base.httpRequest", 4.2, [-2320, -960], {
        "method": "POST",
        "url": "={{ $json.dienstArt === 'meldung-verwerfen' ? " + K + ".dienst.adresse + '/meldungen/erledigt' : " + K + ".dienst.adresse + '/ansage/meldung' }}",
        "sendHeaders": True, "headerParameters": {"parameters": MELDUNG_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": ("={{ JSON.stringify($json.dienstArt === 'meldung-verwerfen'"
                     " ? { ids: [$json.meldungKennung], grund: 'verworfen' }"
                     " : { id: $json.meldungKennung }) }}"),
        "options": {"timeout": 900000},
    }, onError="continueRegularOutput",
       notes="Meldungs-Modul im Dienst ddd-radio: legt das Postfach des Suchbots "
             "und spricht Ansagen ueber den DJ-Hafen in den Sender. Das Sprechen "
             "dauert so lange wie die Ansage (bei einem Ueberblick Minuten) - "
             "daher 15 Minuten Zeitablauf."),
    n("Listen Dienst", "n8n-nodes-base.httpRequest", 4.2, [-2320, -1220], {
        "method": "POST",
        "url": "={{ $json.dienstArt === 'listen-knopf' ? " + K + ".dienst.adresse + '/playlist/knopf' : " + K + ".dienst.adresse + '/playlist/befehl' }}",
        "sendHeaders": True, "headerParameters": {"parameters": JSON_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": ("={{ JSON.stringify({ chatId: $json.chatId, daten: $json.knopfRoh || '',"
                     " text: $json.text || '' }) }}"),
        "options": {"timeout": 90000},
    }, onError="continueRegularOutput",
       notes="Listen-Modul im Dienst ddd-radio: sucht, baut, verwaltet und spielt "
             "Wiedergabelisten. Knopfdruecke gehen an /playlist/knopf, Texte an "
             "/playlist/befehl."),
    code("Dienst Antwort", [-2100, -1220], LISTEN_ANTWORT_JS),
    n("Senden fehlgeschlagen?", "n8n-nodes-base.if", 2.2, [-1660, -1220], {
        "conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                   "typeValidation": "loose", "version": 2},
                       "combinator": "and",
                       "conditions": [{"id": nid(),
                                       "leftValue": "={{ !!$json.error }}",
                                       "rightValue": "",
                                       "operator": {"type": "boolean", "operation": "true",
                                                    "singleValue": True}}]},
        "options": {}}, notes="Ja = Bearbeiten ging nicht (z.B. Nachricht zu alt)."),
    n("Dienst Ersatz senden", "n8n-nodes-base.httpRequest", 4.2, [-1440, -1220], {
        "method": "POST", "url": TG + "/sendMessage",
        "sendHeaders": True, "headerParameters": {"parameters": JSON_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": ("={{ JSON.stringify(Object.assign({ chat_id: $('Dienst Antwort').first().json.chatId,"
                     " text: $('Dienst Antwort').first().json.antwort, parse_mode: 'HTML',"
                     " disable_web_page_preview: true },"
                     " ($('Dienst Antwort').first().json.tastatur"
                     " ? { reply_markup: $('Dienst Antwort').first().json.tastatur } : {}))) }}"),
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput",
       notes="Zweiter Versuch als neue Nachricht, wenn editMessageText scheitert."),

    code("Ende", [-1220, -1220], ENDE_JS),
    n("Dienst Senden", "n8n-nodes-base.httpRequest", 4.2, [-1880, -1220], {
        "method": "POST",
        "url": "={{ $json.bearbeiten ? " + K + ".telegram.bot + '/editMessageText' : " + K + ".telegram.bot + '/sendMessage' }}",
        "sendHeaders": True, "headerParameters": {"parameters": JSON_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": ("={{ JSON.stringify($json.bearbeiten ? { chat_id: $json.chatId,"
                     " message_id: $json.nachrichtId, text: $json.antwort, parse_mode: 'HTML',"
                     " disable_web_page_preview: true, reply_markup: $json.tastatur ||"
                     " { inline_keyboard: [] } } : Object.assign({ chat_id: $json.chatId,"
                     " text: $json.antwort, parse_mode: 'HTML', disable_web_page_preview: true },"
                     " ($json.tastatur ? { reply_markup: $json.tastatur } : {}))) }}"),
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput",
       notes="sendMessage; im Menue editMessageText, damit nicht bei jedem Antippen "
             "eine neue Nachricht entsteht."),

    # ---------------------------------------- Stufe 0: Kurzbefehl (ohne Sprachmodell)
    code("Kurz?", [-480, -340], KURZ_JS),
    wenn("Kurzbefehl?", [-260, -340], "={{ !!$json.kurz }}",
         "Ja = einfacher Befehl, laeuft ohne Analyse direkt in die Ausfuehrung."),

    # ---------------------------------------------------- Stufe 1: Analyse
    n("Planen", "n8n-nodes-base.httpRequest", 4.2, [-480, 0], {
        "method": "POST", "url": OLLAMA_OAI_URL + "/chat/completions",
        "sendHeaders": True, "headerParameters": {"parameters": OLLAMA_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": modell_koerper("planen", "$json.auftrag + '\\n/no_think'", 0.2, 3000),
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
        "options": {"systemMessage": kwert("aufgaben.ausfuehren")},
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
        "method": "GET", "url": NOWPLAYING,
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
        "jsonBody": modell_koerper("pruefen",
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
                 "anderen Weg. Antworte in einem kurzen Satz in der Sprache des Betreibers: '"
                 " + String(($('Zugang').first().json.sprache || 'de'))"
                 " + ' (en = englisch, de = deutsch) - auch die Bestaetigung.\\n/no_think' }}"),
        "options": {"systemMessage": kwert("aufgaben.ausfuehren")},
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

    # ------------------------------------- Postfach: neue Meldungen anbieten
    # Eigener Eingang mit Zeitplan. Der Suchbot legt Meldungen in den Dienst;
    # hier werden sie regelmaessig abgeholt und dem Betreiber mit Knoepfen
    # vorgelegt. Angebotene Meldungen kommen nicht noch einmal (nur_neue=1).
    n("Zeitplan Meldungen", "n8n-nodes-base.scheduleTrigger", 1.2, [-2760, -460],
      {"rule": {"interval": [{"field": "minutes", "minutesInterval": 5}]}}, webhookId=nid(),
      **({"disabled": True} if os.environ.get("TRIGGER_AUS") else {})),
    n("Meldungen holen", "n8n-nodes-base.httpRequest", 4.2, [-2540, -460], {
        "method": "GET", "url": MELDUNGEN + "/meldungen/offen",
        "sendQuery": True,
        "queryParameters": {"parameters": [{"name": "anzahl", "value": "3"},
                                           {"name": "nur_neue", "value": "1"}]},
        "sendHeaders": True, "headerParameters": {"parameters": MELDUNG_KOPF},
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput",
       notes="Holt neue Meldungen aus dem Postfach (nur_neue=1 = noch nicht angeboten)."),
    wenn("Meldung da?", [-2320, -460], "={{ Number($json.offen || 0) > 0 }}",
         "Nein = nichts Neues, der Lauf endet hier."),
    code("Meldung Karte", [-2100, -460], MELDUNG_KARTE_JS),
    wenn("Angebot?", [-1880, -460], "={{ $('Meldung Karte').isExecuted }}",
         "Nein = Knopfdruck, hier endet der Lauf (die Markierung folgt nur dem Zeitplan)."),
    n("Meldung anbieten", "n8n-nodes-base.httpRequest", 4.2, [-1660, -460], {
        "method": "POST", "url": MELDUNGEN + "/meldungen/angeboten",
        "sendHeaders": True, "headerParameters": {"parameters": MELDUNG_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": ("={{ JSON.stringify({ ids: ($('Meldung Karte').isExecuted"
                     " ? $('Meldung Karte').first().json.angeboten : []) }) }}"),
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput",
       notes="Merkt die Meldungen als angeboten - kein zweites Angebot."),

    # --- Werkzeuge (Unterschnittstellen des Agenten)
    n("Werkzeug Titel suchen", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, [380, 420], {
        "name": "titel_suchen",
        "description": kwert("aufgaben.werkzeuge.titel_suchen"),
        "source": "database",
        "workflowId": {"__rl": True, "value": W_WERKZEUG, "mode": "list",
                       "cachedResultName": W_WERKZEUG_NAME},
        "workflowInputs": {
            "mappingMode": "defineBelow",
            "value": {"suchtext": feld("suchtext", "Interpret und/oder Titel, z. B. In Extremo Santa Maria. Oder eine Nummer aus der letzten Auswahlliste, z. B. 2"),
                      "einreihen": feld("einreihen", "true, wenn der Titel nur eingereiht werden soll (nicht sofort laufen)", "boolean", False),
                      "sprache": feld("sprache", "Sprache des Betreibers: de oder en. Immer mitgeben - die Antwort des Werkzeugs kommt in dieser Sprache zurueck.", "string", "de")},
            "matchingColumns": [],
            "schema": [{"id": "suchtext", "displayName": "suchtext", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "einreihen", "displayName": "einreihen", "required": False,
                        "defaultMatch": False, "display": True, "type": "boolean",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "sprache", "displayName": "sprache", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False}],
            "attemptToConvertTypes": False, "convertFieldsToString": False},
    }),
    n("Werkzeug Richtung suchen", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, [580, 420], {
        "name": "richtung_suchen",
        "description": kwert("aufgaben.werkzeuge.richtung_suchen"),
        "source": "database",
        "workflowId": {"__rl": True, "value": W_WERKZEUG, "mode": "list",
                       "cachedResultName": W_WERKZEUG_NAME},
        "workflowInputs": {
            "mappingMode": "defineBelow",
            "value": {"richtung": feld("richtung", "Stimmung, Genre oder Jahrzehnt - eines von: party, dance, rock, pop, metal, hiphop, electronic, disco, punk, grunge, folk, blues, jazz, klassik, schlager, deutschrap, ruhig, hart, 90er, 80er"),
                      "einreihen": feld("einreihen", "true, wenn der Titel nur eingereiht werden soll (nicht sofort laufen)", "boolean", False),
                      "sprache": feld("sprache", "Sprache des Betreibers: de oder en. Immer mitgeben - die Antwort des Werkzeugs kommt in dieser Sprache zurueck.", "string", "de")},
            "matchingColumns": [],
            "schema": [{"id": "richtung", "displayName": "richtung", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "einreihen", "displayName": "einreihen", "required": False,
                        "defaultMatch": False, "display": True, "type": "boolean",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "sprache", "displayName": "sprache", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False}],
            "attemptToConvertTypes": False, "convertFieldsToString": False},
    }),
    n("Werkzeug Was laeuft", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, [780, 420], {
        "name": "was_laeuft",
        "description": kwert("aufgaben.werkzeuge.was_laeuft"),
        "source": "database",
        "workflowId": {"__rl": True, "value": W_WERKZEUG, "mode": "list",
                       "cachedResultName": W_WERKZEUG_NAME},
        "workflowInputs": {
            "mappingMode": "defineBelow",
            "value": {"frage": feld("frage", "Was der Nutzer wissen will, z. B. welcher Titel laeuft, was danach kommt, wie viele Zuhoerer", "string", "was laeuft gerade"),
                      "sprache": feld("sprache", "Sprache des Betreibers: de oder en. Immer mitgeben - die Antwort des Werkzeugs kommt in dieser Sprache zurueck.", "string", "de")},
            "matchingColumns": [], "schema": [{"id": "frage", "displayName": "frage", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "sprache", "displayName": "sprache", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False}],
            "attemptToConvertTypes": False, "convertFieldsToString": False},
    }),
    n("Werkzeug Azura Adressen", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, [980, 420], {
        "name": "azura_endpunkte",
        "description": kwert("aufgaben.werkzeuge.azura_endpunkte"),
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
        "description": kwert("aufgaben.werkzeuge.azura_aufruf"),
        "source": "database",
        "workflowId": {"__rl": True, "value": W_AZURA, "mode": "list",
                       "cachedResultName": W_AZURA_NAME},
        "workflowInputs": {
            "mappingMode": "defineBelow",
            "value": {"methode": feld("methode", "GET zum Lesen, POST/PUT/DELETE zum Aendern", "string", "GET"),
                      "pfad": feld("pfad", "Vollstaendiger Pfad mit /api/, z. B. /api/station/2/playlists"),
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
        "description": kwert("aufgaben.werkzeuge.azura_ueberblick"),
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
    n("Werkzeug Meldungen", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, [1780, 420], {
        "name": "meldungen",
        "description": kwert("aufgaben.werkzeuge.meldungen"),
        "source": "database",
        "workflowId": {"__rl": True, "value": W_MELDUNGEN, "mode": "list",
                       "cachedResultName": W_MELDUNGEN_NAME},
        "workflowInputs": {
            "mappingMode": "defineBelow",
            "value": {"auftrag": feld("auftrag", "anzeigen (offene Meldungen), lesen (Sprechtext), ansagen (live sprechen), verwerfen oder text (freier Text)", "string", "anzeigen"),
                      "kennung": feld("kennung", "Kennung der Meldung, z. B. m260920-0007 (bei lesen, ansagen, verwerfen)", "string", ""),
                      "text": feld("text", "Freier Ansagetext (nur bei auftrag=text)", "string", "")},
            "matchingColumns": [],
            "schema": [{"id": "auftrag", "displayName": "auftrag", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "kennung", "displayName": "kennung", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "text", "displayName": "text", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False}],
            "attemptToConvertTypes": False, "convertFieldsToString": False},
    }),
    n("Werkzeug Recherche", "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, [2000, 420], {
        "name": "recherche",
        "description": kwert("aufgaben.werkzeuge.recherche"),
        "source": "database",
        "workflowId": {"__rl": True, "value": W_MELDUNGEN, "mode": "list",
                       "cachedResultName": W_MELDUNGEN_NAME},
        "workflowInputs": {
            "mappingMode": "defineBelow",
            "value": {"art": feld("art", "wetter, nachrichten, rss, wikipedia oder ueberblick", "string", "wetter"),
                      "wort": feld("wort", "Ort beim Wetter, Stichwort bei wikipedia, Feed-Adresse oder Kurzname bei rss", "string", ""),
                      "themen": feld("themen", "Nur beim Ueberblick: Themen, zu denen Meldungen gesucht werden, z. B. 'ki, raumfahrt' (leer = stehende Themen des Senders bzw. die neuesten Meldungen)", "string", ""),
                      "quellen": feld("quellen", "Nur beim Ueberblick: gewuenschte Quellen, z. B. 'heise golem' oder 'alle' (leer = Standard)", "string", ""),
                      "ansagen": feld("ansagen", "true = sofort im Radio ansagen, false = nur ablegen und im Telegram zeigen", "boolean", True)},
            "matchingColumns": [],
            "schema": [{"id": "art", "displayName": "art", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "wort", "displayName": "wort", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "themen", "displayName": "themen", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "quellen", "displayName": "quellen", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "ansagen", "displayName": "ansagen", "required": False,
                        "defaultMatch": False, "display": True, "type": "boolean",
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
                      "einreihen": "={{ $json.befehl.einreihen === true }}",
                      "sprache": "={{ $('Zugang').first().json.sprache || 'de' }}"},
            "matchingColumns": [],
            "schema": [{"id": "suchtext", "displayName": "suchtext", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "richtung", "displayName": "richtung", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "einreihen", "displayName": "einreihen", "required": False,
                        "defaultMatch": False, "display": True, "type": "boolean",
                        "canBeUsedToMatch": True, "removed": False},
                       {"id": "sprache", "displayName": "sprache", "required": False,
                        "defaultMatch": False, "display": True, "type": "string",
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
    wenn("Postfach?", [160, -740], "={{ $json.art === 'postfach' }}",
         "Ja = Frage nach dem Postfach, ohne Sprachmodell und ohne Ansage."),
    n("Postfach holen", "n8n-nodes-base.httpRequest", 4.2, [380, -740], {
        "method": "GET", "url": MELDUNGEN + "/meldungen/offen",
        "sendQuery": True,
        "queryParameters": {"parameters": [{"name": "anzahl", "value": "5"}]},
        "sendHeaders": True, "headerParameters": {"parameters": MELDUNG_KOPF},
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput", notes="Offene Meldungen im Postfach."),
    code("Postfach Antwort", [600, -740], POSTFACH_ANTWORT_JS),

    # --- Ueberblick: mehrere Quellen, laengerer Beitrag (eigener Weg ohne Sprachmodell)
    # Das Wort "ueberblick" (Stufe 0) laeuft hier vorbei: der Dienst holt die Quellen
    # und spricht den Beitrag in den Sender. Das dauert so lange wie der Beitrag.
    wenn("Ueberblick?", [-140, -920], "={{ $json.art === 'ueberblick' }}",
         "Ja = Ueberblick zu den genannten Themen (Beitrag dauert Minuten)."),
    n("Ueberblick holen", "n8n-nodes-base.httpRequest", 4.2, [80, -1140], {
        "method": "POST", "url": MELDUNGEN + "/recherche",
        "sendHeaders": True, "headerParameters": {"parameters": MELDUNG_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": ("={{ JSON.stringify({ art: 'ueberblick',"
                     " quellen: String($json.befehl.quellen || ''),"
                     " themen: String($json.befehl.themen || ''), ansagen: true }) }}"),
        "options": {"timeout": 900000},
    }, onError="continueRegularOutput",
       notes="Holt zu den Themen Meldungen aus Presse, Netz und Feeds und spricht sie "
             "in den Sender. Dauert so lange wie der Beitrag (Minuten) - daher 15 Minuten "
             "Zeitablauf."),
    code("Ueberblick Antwort", [300, -1140], UEBERBLICK_ANTWORT_JS),

    n("Kurz Steuern", "n8n-nodes-base.httpRequest", 4.2, [380, -520], {
        "method": "={{ ['pause', 'lautstaerke'].includes($json.befehl.steuerung) ? 'GET' : 'POST' }}",
        "url": "={{ ['pause', 'lautstaerke'].includes($json.befehl.steuerung) ? " + K + ".sender.api + '/status' : " + K + ".sender.api + '/backend/' + $json.befehl.steuerung }}",
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

    # Webhook-Eingaenge (REST und Test): die Antwort geht als JSON an den Aufrufer
    # zurueck (statt Telegram). Drei kleine Abnehmer, je einer am Ende eines
    # Antwort-Wegs - so bleibt der Weg kurz und ein Telegram-Lauf beruehrt sie
    # nicht (Feld "istTest" aus "Eingabe").
    wenn("JSON? (kurz)", [-1880, -700], "={{ !!$('Eingabe').first().json.istTest }}",
         "Ja = Aufruf von aussen (REST- oder Testeingang): Antwort als JSON."),
    n("JSON antworten (kurz)", "n8n-nodes-base.respondToWebhook", 1.1, [-1660, -960], {
        "respondWith": "json", "responseBody": REST_ANTWORT_JSON, "options": {}},
       notes="Antwort des kurzen Wegs als JSON (ok, antwort, tastatur, sprache)."),
    wenn("JSON? (dienst)", [-1880, 1130], "={{ !!$('Eingabe').first().json.istTest }}",
         "Ja = Aufruf von aussen (REST- oder Testeingang): Antwort als JSON."),
    n("JSON antworten (dienst)", "n8n-nodes-base.respondToWebhook", 1.1, [-2100, 1390], {
        "respondWith": "json", "responseBody": REST_ANTWORT_JSON, "options": {}},
       notes="Antwort des Dienst-Zweigs als JSON (ok, antwort, tastatur, sprache)."),
    wenn("JSON? (lang)", [3340, 960], "={{ !!$('Eingabe').first().json.istTest }}",
         "Ja = Aufruf von aussen (REST- oder Testeingang): Antwort als JSON."),
    n("JSON antworten", "n8n-nodes-base.respondToWebhook", 1.1, [3560, 1220], {
        "respondWith": "json", "responseBody": REST_ANTWORT_JSON, "options": {}},
       notes="Antwort des Hauptwegs als JSON (ok, antwort, tastatur, sprache)."),
]

bot_verbindungen = {
    "Telegram Trigger": {"main": [[{"node": "Eingabe", "type": "main", "index": 0}]]},
    "Test-Eingang": {"main": [[{"node": "Eingabe", "type": "main", "index": 0}]]},
    "REST-Eingang": {"main": [[{"node": "Eingabe", "type": "main", "index": 0}]]},
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
        [{"node": "JSON? (kurz)", "type": "main", "index": 0}]]},
    "Gehoert Text": {"main": [[{"node": "JSON? (kurz)", "type": "main", "index": 0}]]},
    "Zugang": {"main": [[{"node": "Freigegeben?", "type": "main", "index": 0}]]},
    "Freigegeben?": {"main": [
        [{"node": "Dienst Art", "type": "main", "index": 0}],
        [{"node": "Kein Zugang", "type": "main", "index": 0}]]},
    "Dienst Art": {"main": [[{"node": "Dienst?", "type": "main", "index": 0}]]},
    "Dienst?": {"main": [
        [{"node": "Meldung?", "type": "main", "index": 0}],
        [{"node": "Text da?", "type": "main", "index": 0}]]},
    "Meldung?": {"main": [
        [{"node": "Meldung Dienst", "type": "main", "index": 0}],
        [{"node": "Listen Dienst", "type": "main", "index": 0}]]},
    "Listen Dienst": {"main": [[{"node": "Dienst Antwort", "type": "main", "index": 0}]]},
    "Meldung Dienst": {"main": [[{"node": "Dienst Antwort", "type": "main", "index": 0}]]},
    "Dienst Antwort": {"main": [[{"node": "JSON? (dienst)", "type": "main", "index": 0}]]},
    "JSON? (dienst)": {"main": [
        [{"node": "JSON antworten (dienst)", "type": "main", "index": 0}],
        [{"node": "Dienst Senden", "type": "main", "index": 0}]]},
    "Senden fehlgeschlagen?": {"main": [
        [{"node": "Dienst Ersatz senden", "type": "main", "index": 0}],
        [{"node": "Ende", "type": "main", "index": 0}]]},
    "Ende": {"main": [[], []]},

    # Postfach: neue Meldungen anbieten (eigener Eingang mit Zeitplan)
    "Zeitplan Meldungen": {"main": [[{"node": "Meldungen holen", "type": "main", "index": 0}]]},
    "Meldungen holen": {"main": [[{"node": "Meldung da?", "type": "main", "index": 0}]]},
    "Meldung da?": {"main": [
        [{"node": "Meldung Karte", "type": "main", "index": 0}],
        []]},
    "Meldung Karte": {"main": [[{"node": "Dienst Senden", "type": "main", "index": 0}]]},
    "Dienst Senden": {"main": [[{"node": "Senden fehlgeschlagen?", "type": "main", "index": 0}]]},
    "Dienst Ersatz senden": {"main": [[{"node": "Angebot?", "type": "main", "index": 0}]]},
    "Angebot?": {"main": [
        [{"node": "Meldung anbieten", "type": "main", "index": 0}],
        [{"node": "Ende", "type": "main", "index": 0}]]},
    "Kein Zugang": {"main": [[{"node": "JSON? (kurz)", "type": "main", "index": 0}]]},
    "Text da?": {"main": [
        [{"node": "Auftrag", "type": "main", "index": 0}],
        [{"node": "Kein Text", "type": "main", "index": 0}]]},
    "Auftrag": {"main": [[{"node": "Kurz?", "type": "main", "index": 0}]]},
    # Stufe 0: erkannte Kurzbefehle gehen direkt in die Ausfuehrung, alles andere in die Analyse.
    "Kurz?": {"main": [[{"node": "Kurzbefehl?", "type": "main", "index": 0}]]},
    "Kurzbefehl?": {"main": [
        [{"node": "Schleife", "type": "main", "index": 0}],
        [{"node": "Planen", "type": "main", "index": 0}]]},
    "Kein Text": {"main": [[{"node": "JSON? (kurz)", "type": "main", "index": 0}]]},
    # Der kurze Weg endet als Telegram-Nachricht - oder (REST/Test) als JSON zurueck.
    "JSON? (kurz)": {"main": [
        [{"node": "JSON antworten (kurz)", "type": "main", "index": 0}],
        [{"node": "Senden (Kurzmeldung)", "type": "main", "index": 0}]]},

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
        [{"node": "Postfach?", "type": "main", "index": 0}]]},
    "Postfach?": {"main": [
        [{"node": "Postfach holen", "type": "main", "index": 0}],
        [{"node": "Ueberblick?", "type": "main", "index": 0}]]},
    "Ueberblick?": {"main": [
        [{"node": "Ueberblick holen", "type": "main", "index": 0}],
        [{"node": "Ausfuehren", "type": "main", "index": 0}]]},
    "Ueberblick holen": {"main": [[{"node": "Ueberblick Antwort", "type": "main", "index": 0}]]},
    "Ueberblick Antwort": {"main": [[{"node": "Schleife", "type": "main", "index": 0}]]},
    "Postfach holen": {"main": [[{"node": "Postfach Antwort", "type": "main", "index": 0}]]},
    "Postfach Antwort": {"main": [[{"node": "Schleife", "type": "main", "index": 0}]]},
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
    "Antwort": {"main": [[{"node": "JSON? (lang)", "type": "main", "index": 0}]]},
    # Der Hauptweg endet als Telegram-Nachricht - oder (REST/Test) als JSON zurueck.
    "JSON? (lang)": {"main": [
        [{"node": "JSON antworten", "type": "main", "index": 0}],
        [{"node": "Senden", "type": "main", "index": 0}]]},

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
    "Werkzeug Meldungen": {"ai_tool": [[{"node": "Ausfuehren", "type": "ai_tool", "index": 0},
                                        {"node": "Nacharbeiten", "type": "ai_tool", "index": 0}]]},
    "Werkzeug Recherche": {"ai_tool": [[{"node": "Ausfuehren", "type": "ai_tool", "index": 0},
                                        {"node": "Nacharbeiten", "type": "ai_tool", "index": 0}]]},
}

# ================================================================== Anordnung
# Die Zahlen in den Knotendefinitionen oben sind nur grobe Platzhalter - gueltig
# ist diese Tabelle. Sie legt fest, wie der Ablauf in n8n aussieht: sieben
# Gruppen, jede liest sich von links nach rechts, die Gruppen liegen in der
# Reihenfolge des Ablaufs untereinander. Schrittweite 220, Zeilenabstand 260.
ANORDNUNG = {
    # -- 1 Sprachnachricht (eigener Zweig oben)
    "Datei holen": (-3800, -2060),
    "Audio laden": (-3580, -2060),
    "Umwandeln": (-3360, -2060),
    "Transkript": (-3140, -2060),
    "Verstanden?": (-2920, -2060),
    "Gehoert Text": (-2700, -2060),

    # -- 2 Eingang und Zugang
    "Konfiguration": (-4200, -460),
    "Weiche Plan?": (-4200, -280),
    "Telegram Trigger": (-4200, -1380),
    "Test-Eingang": (-4200, -1060),
    "REST-Eingang": (-4200, -740),
    "Eingabe": (-3980, -1220),
    "Sprachnachricht?": (-3760, -1220),
    "Zugang": (-3200, -1220),
    "Freigegeben?": (-2980, -1220),
    "Dienst Art": (-2760, 350),
    "Dienst?": (-2540, 350),
    "Meldung?": (-2320, 610),
    "Text da?": (-2100, 610),
    "Auftrag": (-1880, 610),
    "Listen Dienst": (-2320, 870),
    "Meldung Dienst": (-2320, 1130),
    "Dienst Antwort": (-2100, 1130),
    "JSON? (dienst)": (-1880, 1130),
    "Dienst Senden": (-1880, 1390),
    "JSON antworten (dienst)": (-2100, 1390),
    "Senden fehlgeschlagen?": (-1660, 1130),
    "Dienst Ersatz senden": (-1440, 1130),
    "Ende": (-1220, 1130),
    "Kein Zugang": (-2980, -1500),
    "Kein Text": (-2100, -700),
    "JSON? (kurz)": (-1880, -700),
    "Senden (Kurzmeldung)": (-1660, -700),
    "JSON antworten (kurz)": (-1660, -960),

    # -- Postfach: Meldungen des Suchbots anbieten
    "Zeitplan Meldungen": (-2760, 1620),
    "Meldungen holen": (-2540, 1620),
    "Meldung da?": (-2320, 1620),
    "Meldung Karte": (-2100, 1620),
    "Angebot?": (-1880, 1620),
    "Meldung anbieten": (-1660, 1620),

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
    "Postfach?": (-140, 1220),
    "Postfach holen": (80, 1220),
    "Postfach Antwort": (300, 1220),
    "Ueberblick?": (-140, 1480),
    "Ueberblick holen": (80, 1740),
    "Ueberblick Antwort": (300, 1740),
    "Kurz Steuern": (80, 960),
    "Steuerung Antwort": (300, 960),
    "Ausfuehren": (80, 1480),
    "Ergebnis sammeln": (300, 1480),
    "Sprachmodell Ausfuehren": (80, 2000),

    # -- 5 Werkzeuge (Unterschnittstellen des Agenten)
    "Werkzeug Titel suchen": (560, 2200),
    "Werkzeug Richtung suchen": (760, 2200),
    "Werkzeug Was laeuft": (960, 2200),
    "Werkzeug Azura Adressen": (1160, 2200),
    "Werkzeug Azura Aufruf": (1360, 2200),
    "Werkzeug Azura Ueberblick": (1560, 2200),
    "Werkzeug Meldungen": (1780, 2200),
    "Werkzeug Recherche": (2000, 2200),

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
    "JSON? (lang)": (3340, 960),
    "Senden": (3560, 960),
    "JSON antworten": (3560, 1220),
}

# Rahmen (Haftnotizen) je Gruppe: Name, x, y, Breite, Hoehe, Farbe, Inhalt.
# Rund 180 Rasterpunkte Luft unter dem Notiztext, damit die Knoten nicht auf der
# Schrift liegen - in n8n steht der Text oben im Rahmen. Deshalb nur drei Zeilen
# je Notiz; das Ausfuehrliche steht an den Knoten (Anmerkung) und in der Doku.
LEGENDE_BOT = """## DDD-Webseite Bot - zweisprachiger Telegram-Agent (DE/EN)
EIN Bot, EIN Chat: der Betreiber schreibt deutsch oder englisch. Die Sprache wird
am Eingang erkannt (Feld `sprache`) und reist mit - Kurzbefehle, Werkzeugantworten
und die Antworten des Modells folgen ihr. Inhalte (Nachrichten, Wetter) und die
Verwaltungswege des Dienstes bleiben deutsch.

Was der Bot kann: Liedwunsch, Richtungswunsch, skip/pause/Status, Wiedergabelisten,
Postfach, Recherche (Wetter, Nachrichten, RSS) und Ansagen im laufenden Programm.
Alles kommt aus Telegram und geht dorthin zurueck - oder per REST- oder Testeingang
als JSON ({"text": "..."} plus Schluessel; Antwort {ok, antwort, tastatur, sprache}).
Gespielt wird auf dem Sender "DDD-Webseite Demo" (Sender 2).

Der Weg einer Nachricht: Eingang -> Stufe 0/1 Analyse -> Stufe 2 Ausfuehrung ->
Stufe 3 Pruefung -> Antwort. Sprachnachrichten laufen oben durch Whisper,
Dienste und Postfach haengen seitlich dran. Jeder Knoten traegt seinen Zweck als
Notiz unter dem Namen, jeder Rahmen erklaert eine Stufe.

Rahmenfarben: 1 Sprachnachricht | 2 Eingang | 3 Dienste | 4 Postfach |
5 Stufe 0+1 | 6 Stufe 2 + Werkzeuge | 7 Stufe 3 + Antwort

Erzeugt von DDD-Webseite/werkzeuge/agent-wf-bauen-ddd.py - nie von Hand aendern.
Aendern: bauen.sh, pruefen.sh, einspielen.sh.
Doku: README.md (deutsch) und EN/README.md (englisch)."""

BEREICHE = [
    ("Notiz Sprachnachricht", 1, """## Sprachnachricht (eigener Zweig oben)
Datei holen, umwandeln, erkennen (Whisper auf dem ai-Server).
Erkannt: weiter an **Zugang** - sonst kurze Rueckmeldung.""",
     ["Datei holen", "Audio laden", "Umwandeln", "Transkript", "Verstanden?", "Gehoert Text"]),
    ("Notiz Eingang", 2, """## Eingang und Zugang
Drei Eingaenge (Telegram, Test, REST); Zugang ueber `erlaubte` oder Testscluessel.
Kurze Wege senden ueber **Senden (Kurzmeldung)** oder **JSON antworten (kurz)**.""",
     ["Konfiguration", "Weiche Plan?", "Telegram Trigger", "Test-Eingang", "REST-Eingang",
      "Eingabe", "Sprachnachricht?", "Zugang", "Freigegeben?", "Kein Zugang", "Kein Text",
      "JSON? (kurz)", "JSON antworten (kurz)", "Senden (Kurzmeldung)"]),
    ("Notiz Dienste", 3, """## Dienste: Wiedergabelisten und Meldungen
Knopf oder Text -> **Dienst Art** -> **Meldung?** -> Modul im Dienst ddd-radio.
Listen merken sich die Auswahl; Meldungen kommen als Karte mit Knoepfen.
REST- und Testaufrufe bekommen die Ausgabe als JSON statt per Telegram.
Textnachrichten laufen ueber **Text da?** weiter in die Analyse.""",
     ["Dienst Art", "Dienst?", "Meldung?", "Text da?", "Auftrag", "Listen Dienst",
      "Meldung Dienst", "Dienst Antwort", "JSON? (dienst)", "JSON antworten (dienst)",
      "Dienst Senden", "Senden fehlgeschlagen?", "Dienst Ersatz senden", "Ende"]),
    ("Notiz Postfach", 4, """## Postfach (Suchbot -> Moderator)
Alle 5 Minuten: neue Meldungen holen und als Karte mit Knoepfen vorlegen.
**Meldung anbieten** merkt sie als angeboten - kein zweites Angebot.""",
     ["Zeitplan Meldungen", "Meldungen holen", "Meldung da?", "Meldung Karte",
      "Angebot?", "Meldung anbieten"]),
    ("Notiz Analyse", 5, """## Stufe 0 und Stufe 1: verstehen und planen
**Kurz?** erkennt einfache Befehle ohne Modell, **Kurzbefehl?** schickt sie direkt
in die Ausfuehrung. Sonst zerlegt **Planen** die Anweisung in einzelne Befehle.""",
     ["Kurz?", "Kurzbefehl?", "Planen", "Plan Antwort", "Plan da?", "Plan merken",
      "Plan nochmal?", "Befehle lesen", "Befehl da?"]),
    ("Notiz Ausfuehrung", 6, """## Stufe 2: Ausfuehrung im Zyklus
Ein Befehl je Durchlauf - Ausgang 0 = fertig, Ausgang 1 = weiter.
Drei Wege: Ersatz ohne Modell, feste Steuerung, Agent mit Werkzeugen.""",
     ["Schleife", "Direkt oder KI?", "Ersatz Werkzeug", "Ersatz Antwort", "Steuerung?",
      "Postfach?", "Postfach holen", "Postfach Antwort", "Ueberblick?", "Ueberblick holen",
      "Ueberblick Antwort", "Kurz Steuern",
      "Steuerung Antwort", "Ausfuehren", "Ergebnis sammeln", "Sprachmodell Ausfuehren"]),
    ("Notiz Werkzeuge", 6, """## Werkzeuge (Unterschnittstellen des Agenten)
Je Werkzeug ein Knoten; er ruft den Werkzeug-Ablauf per `executeWorkflow` auf.
Dateipfade und Senderaufrufe bleiben dort - das Modell sieht sie nie.""",
     ["Werkzeug Titel suchen", "Werkzeug Richtung suchen", "Werkzeug Was laeuft",
      "Werkzeug Azura Adressen", "Werkzeug Azura Aufruf", "Werkzeug Azura Ueberblick",
      "Werkzeug Meldungen", "Werkzeug Recherche"]),
    ("Notiz Pruefung", 7, """## Stufe 3: Pruefung, Nachfassen und Antwort
**Lage holen** und **Warteschlange holen** belegen den Senderzustand, **Pruefen**
urteilt je Befehl. **Nachfassen?** startet genau einen zweiten Versuch je Befehl.
**Antwort bauen** fasst zusammen und baut die Knoepfe; **Senden** schickt per
HTML - oder **JSON antworten** gibt die Antwort als JSON zurueck.""",
     ["Lage holen", "Warteschlange holen", "Befehle und Lage", "Pruefen?", "Pruefen",
      "Pruefung Antwort", "Pruefung lesen", "Nachfassen?", "Schleife 2", "Nacharbeiten",
      "Nachtrag sammeln", "Sprachmodell Nacharbeiten", "Antwort bauen", "Antwort",
      "JSON? (lang)", "Senden", "JSON antworten"]),
]

# Anmerkungen an den Knoten. Kurz und sichtbar im Plan stehen die wichtigen
# Knoten (unter dem Knoten, hoechstens rund 34 Zeichen - sonst schieben sich die
# Texte im Plan ueber die Nachbarn). Alles andere steht nur beim Ueberfahren.
KURZNOTIZ = {
    "Konfiguration": "Alle Werte an einer Stelle",
    "Weiche Plan?": "Nachricht oder Zeitplan?",
    "Eingabe": "Nachricht, Sprache, Knopfdruck",
    "Zugang": "Nur der Betreiber",
    "Auftrag": "Kontext fuer die Analyse",
    "Dienst Art": "Knopf oder Text fuer einen Dienst?",
    "Dienst?": "Ja = eigener Dienst-Zweig",
    "Meldung?": "Meldung oder Wiedergabeliste?",
    "Listen Dienst": "Modul playlist.py im Dienst",
    "Meldung Dienst": "Modul meldungen.py im Dienst",
    "Dienst Antwort": "Text und Knoepfe aufbereiten",
    "Dienst Senden": "sendMessage / editMessageText",
    "Senden fehlgeschlagen?": "Ja = neue Nachricht senden",
    "Dienst Ersatz senden": "Zweiter Versuch per sendMessage",
    "Ende": "Ausgabe des Dienst-Zweigs",
    "Meldung Karte": "Karte mit Knoepfen bauen",
    "Angebot?": "Nur im Zeitplan-Weg",
    "Meldung anbieten": "Als angeboten merken",
    "Senden (Kurzmeldung)": "Kurzer Weg, gleicher Aufruf",
    "REST-Eingang": "Befehl ohne Telegram (JSON)",
    "JSON? (kurz)": "Ja = Antwort als JSON",
    "JSON? (dienst)": "Ja = Antwort als JSON",
    "JSON? (lang)": "Ja = Antwort als JSON",
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
    "Postfach?": "Ja = Frage nach dem Postfach",
    "Postfach holen": "Offene Meldungen holen",
    "Postfach Antwort": "Liste als Text",
    "Ueberblick?": "Ja = Quellen-Ueberblick",
    "Ueberblick holen": "Beitrag holen und sprechen",
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
    "Zeitplan Meldungen": "Alle 5 Minuten: Postfach abfragen.",
    "Plan Antwort": "Liest den Text des Modells aus.",
    "Plan nochmal?": "Ja = neuer Anlauf, Nein = Ersatzweg ueber die Ausfuehrung.",
    "Ersatz Antwort": "Schreibt die Ausgabe in den Merker, dann zurueck in die Schleife.",
    "Kurz Steuern": "Naechster Titel, Start/Stop/Neustart - feste Adressen, kein Modell.",
    "Steuerung Antwort": "Formuliert die Antwort des Senders.",
    "Ergebnis sammeln": "Schreibt die Ausgabe in den Merker, dann zurueck in die Schleife.",
    "Ueberblick Antwort": "Schreibt die Ausgabe in den Merker, dann zurueck in die Schleife.",
    "Sprachmodell Ausfuehren": "Sprachmodell fuer 'Ausfuehren' (Ollama ueber die OpenAI-Schnittstelle).",
    "Werkzeug Titel suchen": "Werkzeug `titel_suchen` fuer Ausfuehren und Nacharbeiten.",
    "Werkzeug Richtung suchen": "Werkzeug `richtung_suchen` fuer Ausfuehren und Nacharbeiten.",
    "Werkzeug Was laeuft": "Werkzeug `was_laeuft` fuer Ausfuehren und Nacharbeiten.",
    "Werkzeug Azura Adressen": "Werkzeug `azura_endpunkte` fuer Ausfuehren und Nacharbeiten.",
    "Werkzeug Azura Aufruf": "Werkzeug `azura_aufruf` fuer Ausfuehren und Nacharbeiten.",
    "Werkzeug Azura Ueberblick": "Werkzeug `azura_ueberblick` fuer Ausfuehren und Nacharbeiten.",
    "Werkzeug Meldungen": "Werkzeug `meldungen`: Postfach und Ansagen.",
    "Werkzeug Recherche": "Werkzeug `recherche`: Wetter, Nachrichten, Feed, Kurzinfo.",
    "Lage holen": "Was laeuft gerade - Beleg fuer die Pruefung.",
    "Warteschlange holen": "Was eingereiht ist - Beleg fuer die Pruefung.",
    "Pruefung Antwort": "Liest das Urteil des Modells aus.",
    "Nachtrag sammeln": "Schreibt die Ausgabe des zweiten Versuchs in den Merker.",
    "Sprachmodell Nacharbeiten": "Sprachmodell fuer 'Nacharbeiten'.",
    "Antwort": "Bereitet den Text fuer Telegram auf (HTML, ohne Sternchen).",
    "JSON antworten (kurz)": "Gibt die kurze Antwort als JSON an den Aufrufer (REST/Test) zurueck.",
    "JSON antworten (dienst)": "Gibt die Dienst-Antwort als JSON an den Aufrufer (REST/Test) zurueck.",
    "JSON antworten": "Gibt die Antwort als JSON an den Aufrufer (REST/Test) zurueck.",
}


# ------------------------------------------------------------------ Zeichenflaeche
#
# Damit die Flaeche lesbar ist, wird sie aus den Positionen *gerechnet* statt von
# Hand gesetzt: jeder Knoten gehoert zu genau einem Bereich (Tabelle BEREICHE),
# der Rahmen wird aus den Knotenkaesten des Bereichs gebildet. So kann kein Knoten
# mehr "aus dem Rahmen ragen" und kein Rahmen einen anderen ueberlagern - genau das
# war vorher der Fall (geprueft mit anordnung-pruefen.py).

NODE_BREITE = {"n8n-nodes-base.if": 200, "n8n-nodes-base.switch": 240}
NODE_BREITE_STANDARD = 130
NODE_HOEHE = 120
ZEILENHOEHE = 18


def knoten_kasten(knoten):
    """(x0, y0, x1, y1) eines Knotens samt beschriftung unter dem Knoten."""
    x, y = knoten["position"]
    breite = NODE_BREITE.get(knoten["type"], NODE_BREITE_STANDARD)
    hoehe = NODE_HOEHE
    notiz = str(knoten.get("notes", "")).strip()
    if notiz and knoten.get("notesInFlow"):
        zeichen_je_zeile = max(int(breite / 7), 10)
        hoehe += ZEILENHOEHE * (1 + len(notiz) // zeichen_je_zeile)
    return x, y, x + breite, y + hoehe


def bereich_kasten(knoten, text, rand_links=90, rand_rechts=150, rand_unten=50):
    """Rahmen um eine Gruppe von Knoten - mit Platz fuer Ueberschrift und Notizen.

    Erst die Breite aus den Knoten, dann der Kopf aus dem umbrochenen Text: der
    Text darf nicht unter der ersten Knotenzeile liegen.
    """
    kaesten = [knoten_kasten(k) for k in knoten]
    x0 = min(k[0] for k in kaesten) - rand_links
    x1 = max(k[2] for k in kaesten) + rand_rechts
    y0 = min(k[1] for k in kaesten) - kopf_hoehe(text, x1 - x0)
    y1 = max(k[3] for k in kaesten) + rand_unten
    return x0, y0, x1 - x0, y1 - y0


ZEICHEN_BREITE = 7.0        # grobe Schaetzung: Pixel je Zeichen im Haftnotiztext


def text_zeilen(text: str, breite: float) -> int:
    """Zahl der sichtbaren Zeilen, wenn der Text auf 'breite' umbrochen wird."""
    import math as _math

    je_zeile = max(int(breite / ZEICHEN_BREITE), 16)
    zeilen = 0
    for zeile in text.splitlines():
        zeilen += 1 if not zeile.strip() else max(1, _math.ceil(len(zeile) / je_zeile))
    return max(zeilen, 1)


def kopf_hoehe(text: str, breite: float = 2000.0) -> int:
    """Platz fuer '## Ueberschrift' plus den umbrochenen Beschreibungstext."""
    return 44 + ZEILENHOEHE * (2 + text_zeilen(text, breite))


def rahmen_setzen(ablauf, bereiche):
    """Haengt je Bereich eine Haftnotiz als Rahmen um die zugehoerigen Knoten."""
    nach_name = {k["name"]: k for k in ablauf["nodes"]}
    for eintrag in bereiche:
        name, farbe, text, namen = eintrag
        fehlend = [n for n in namen if n not in nach_name]
        if fehlend:
            raise SystemExit(f"Bereich {name}: unbekannte Knoten {fehlend}")
        knoten = [nach_name[n] for n in namen]
        x, y, b, h = bereich_kasten(knoten, text)
        ablauf["nodes"].append(notiz(name, x, y, b, h, text, farbe))


def bereiche_entzerren(ablauf, bereiche, abstand=70, runden=200):
    """Schiebt ganze Bereiche auseinander, bis sich keine Rahmen mehr ueberlagern.

    Ein Rahmen wird aus seinen Knoten gerechnet - wenn zwei Bereiche in der
    Flaeche ueberlappen, wandert der spaetere (in Leserichtung von oben nach
    unten, dann rechts) ein Stueck weiter. Ist der Streifen in x schmaler als in
    y, geht er nach rechts, sonst nach unten. Die Pfeile bleiben gueltig, weil
    sich nur Positionen aendern.
    """
    nach_name = {k["name"]: k for k in ablauf["nodes"]}

    def kaesten():
        liste = []
        for name, farbe, text, namen in bereiche:
            x, y, b, h = bereich_kasten([nach_name[n] for n in namen], text)
            liste.append((name, (x, y, x + b, y + h), namen))
        return liste

    bewegungen = 0
    for _ in range(runden):
        liste = sorted(kaesten(), key=lambda e: (e[1][1], e[1][0]))
        bewegt = False
        for i, (_, ka, _) in enumerate(liste):
            for _, kb, namen_b in liste[i + 1:]:
                ux = min(ka[2], kb[2]) - max(ka[0], kb[0])
                uy = min(ka[3], kb[3]) - max(ka[1], kb[1])
                if ux <= -abstand or uy <= -abstand:
                    continue
                if ux <= uy:                      # schmaler Streifen in x
                    versatz = ka[2] + abstand - kb[0]
                    for n in namen_b:
                        nach_name[n]["position"][0] += versatz
                else:                             # schmaler Streifen in y
                    versatz = ka[3] + abstand - kb[1]
                    for n in namen_b:
                        nach_name[n]["position"][1] += versatz
                bewegungen += 1
                bewegt = True
                break
            if bewegt:
                break
        if not bewegt:
            if bewegungen:
                print(f"  Zeichenflaeche entzerrt: {bewegungen} Verschiebung(en)")
            return
    print("WARNUNG: Bereiche liessen sich nicht ganz entzerren")


def anordnen(ablauf, plan, bereiche, kurz, lang):
    """Setzt Positionen, Beschriftungen und Rahmen.

    Bricht ab, wenn ein Knoten keine Position hat (sonst landet er im Nichts),
    wenn ein Bereich unbekannte Knoten nennt oder wenn ein Knoten in mehreren
    Bereichen steht.
    """
    knoten = [k for k in ablauf["nodes"] if "stickyNote" not in k["type"]]
    namen = [k["name"] for k in knoten]
    ohne = [n for n in namen if n not in plan]
    if ohne:
        raise SystemExit("Ohne Position in ANORDNUNG: " + ", ".join(ohne))
    ueberzaehlig = [n for n in plan if n not in namen]
    if ueberzaehlig:
        raise SystemExit("In ANORDNUNG, aber nicht im Ablauf (%s): %s" % (ablauf.get("name"), ", ".join(ueberzaehlig)))
    doppelt = [n for n in kurz if n in lang]
    if doppelt:
        raise SystemExit("Kurz- und Langnotiz am selben Knoten: " + ", ".join(doppelt))

    for k in knoten:
        if k["name"] in plan:
            k["position"] = list(plan[k["name"]])
        # Jeder Knoten traegt seinen Zweck als Notiz - sichtbar unter dem Knoten,
        # damit die Flaeche ohne Nachschlagen verstaendlich ist.
        text = kurz.get(k["name"]) or lang.get(k["name"]) or k.get("notes") or ""
        if not text.strip():
            raise SystemExit(f"Knoten ohne Notiz: {k['name']}")
        k["notes"] = text
        k["notesInFlow"] = True

    # Genau ein Bereich je Knoten - sonst ueberlagern sich die Rahmen.
    vergeben: dict[str, str] = {}
    for name, _, _, namen_im_bereich in bereiche:
        for n in namen_im_bereich:
            if n in vergeben:
                raise SystemExit(f"{n} steht in zwei Bereichen: {vergeben[n]} und {name}")
            vergeben[n] = name
    ohne_bereich = [n for n in namen if n not in vergeben]
    if ohne_bereich:
        raise SystemExit("Ohne Bereich (Rahmen): " + ", ".join(ohne_bereich))

    bereiche_entzerren(ablauf, bereiche)

    for k in ablauf["nodes"]:
        if "stickyNote" in k["type"]:
            ablauf["nodes"].remove(k)
    rahmen_setzen(ablauf, bereiche)


def legende_setzen(ablauf, text, name="Notiz Uebersicht"):
    """Setzt die Uebersicht oben links ueber die ganze Flaeche."""
    xs = [k["position"][0] for k in ablauf["nodes"]]
    ys = [k["position"][1] for k in ablauf["nodes"]]
    breite = min(max(int(len(z) * ZEICHEN_BREITE) for z in text.splitlines()) + 80, 1400)
    hoehe = 40 + ZEILENHOEHE * (2 + text_zeilen(text, breite))
    x, y = min(xs), min(ys) - hoehe - 80
    ablauf["nodes"] = [k for k in ablauf["nodes"]
                       if not (k.get("name") == name and "stickyNote" in k["type"])]
    ablauf["nodes"].append(notiz(name, x, y, breite, hoehe, text, 7))


# Statische Daten des Bot-Ablaufs: Betreiberliste, Schluessel des Testeingangs und
# der Merker des Betriebs. Sind sie in der Umgebung vorhanden (STATIC_DATEN als JSON),
# werden sie unveraendert uebernommen - so wischt ein Import den Betriebszustand nicht weg.
if os.environ.get("STATIC_DATEN"):
    STATIC_GLOBAL = json.loads(os.environ["STATIC_DATEN"])
else:
    STATIC_GLOBAL = {
        "erlaubte": [int(x) for x in os.environ.get("ERLAUBTE", "").replace(";", ",").split(",")
                     if x.strip().isdigit()],
        "testSchluessel": os.environ.get("TEST_SCHLUESSEL", ""),
        "lauf": {"befehle": []},
    }

agent = {
    "id": "DDD-Webseite-Bot",
    "name": "DDD-Webseite Bot - Telegram-Agent (DE/EN)",
    "nodes": bot,
    "connections": bot_verbindungen,
    "settings": {"executionOrder": "v1", "saveDataSuccessExecution": "all",
                 "saveManualExecutions": True},
    "staticData": {"global": STATIC_GLOBAL},
    "active": False,
    "versionId": str(uuid.uuid4()),
    "parentFolderId": ORDNER,
}

# ============================================================== die Zentrale
# Ein eigener, kleiner Ablauf mit EINEM Code-Knoten: dort stehen alle Adressen,
# Schluessel und die Aufgabentexte des Modells. Die vier Ablaufe holen die Werte
# beim Start von dort - wer den Bot nachbaut, aendert nur diesen einen Knoten.
W_KONFIG = "DDD-Webseite-Konfiguration"
W_KONFIG_NAME = "DDD-Webseite Konfiguration - alle Werte"
KONFIG_KNOTEN = "Konfiguration"          # Name des Aufrufs in jedem Ablauf

KONFIG = {
    "sender": {
        "adresse": os.environ.get("SENDER_URL", "http://192.168.178.33"),
        "schluessel": os.environ.get("AZ_KEY", ""),
        "senderId": 2,
    },
    "dienst": {
        "adresse": os.environ.get("DIENST_URL", os.environ.get("KATALOG_URL",
                                                              "http://192.168.178.53:8882")),
        "schluessel": os.environ.get("MELDUNG_SCHLUESSEL", ""),
    },
    "sprache": {
        "adresse": os.environ.get("WHISPER_URL", "http://192.168.178.188:8000/transcribe"),
    },
    "sprachmodell": {
        "adresse": os.environ.get("OLLAMA_URL", "http://192.168.178.187:11434"),
        "schluessel": os.environ.get("OLLAMA_KEY", "ollama"),
        "modell": os.environ.get("OLLAMA_MODELL", "qwen3.6:27b"),
    },
    "telegram": {
        "adresse": "https://api.telegram.org",
        "token": os.environ.get("TG_TOKEN", ""),
    },
    "aufgaben": {
        "planen": PLANEN_SYSTEM,
        "pruefen": PRUEFEN_SYSTEM,
        "ausfuehren": AUSFUEHREN_SYSTEM,
        "werkzeuge": AUFGABEN_WERKZEUGE,
    },
}

# Abgeleitete Adressen: einmal im Knoten rechnen, damit die Ablaufe kurz bleiben.
KONFIG_ERGAENZEN = """
// Abgeleitete Adressen - nicht von Hand pflegen.
KONFIG.sender.api = KONFIG.sender.adresse + '/api/station/2';
KONFIG.sender.admin = KONFIG.sender.adresse + '/api/admin';
KONFIG.sprachmodell.v1 = KONFIG.sprachmodell.adresse + '/v1';
KONFIG.telegram.bot = KONFIG.telegram.adresse + '/bot' + KONFIG.telegram.token;
KONFIG.telegram.datei = KONFIG.telegram.adresse + '/file/bot' + KONFIG.telegram.token;
"""

WERTE_JS_KOPF = """// ============================================================================
//  HIER WIRD ALLES EINGESTELLT
//  Adressen des Senders, der Dienste und der Sprachmodelle, alle Schluessel und
//  die Aufgabentexte, die das Sprachmodell liest. Die vier Ablaufe holen sich
//  diese Werte beim Start von hier - nichts ist sonst irgendwo fest eingetragen.
//  Nach dem Aendern: Ablauf speichern, fertig (kein Neustart noetig).
// ============================================================================
const KONFIG = """

WERTE_JS_SCHLUSS = """

// Die Nutzlast des Aufrufers wieder auspacken: so stehen hinter dem Aufruf
// "Konfiguration" alle Felder unveraendert zur Verfuegung - plus "konfig".
let eingang = {};
try { eingang = JSON.parse($json.eingang || '{}') || {}; } catch (e) { eingang = {}; }
return [{ json: Object.assign({}, eingang, { konfig: KONFIG }) }];
"""


def konfig_werte_js(werte: dict) -> str:
    """JS-Quelltext des Konfigurationsknotens."""
    return (WERTE_JS_KOPF + json.dumps(werte, ensure_ascii=False, indent=2) + ";\n"
            + KONFIG_ERGAENZEN + WERTE_JS_SCHLUSS)


def konfig_platzhalter(werte: dict) -> dict:
    """Fassung fuer eine Vorlage: Geheimnisse durch Platzhalter ersetzen.

    Die Aufgabentexte bleiben: sie sind der Inhalt der Vorlage, keine Zugangsdaten.
    """
    import copy
    v = copy.deepcopy(werte)
    v["sender"]["adresse"] = "http://DEIN-SENDER"
    v["sender"]["schluessel"] = "DEIN-AZURACAST-API-SCHLUESSEL"
    v["dienst"]["adresse"] = "http://DEIN-DIENST:8882"
    v["dienst"]["schluessel"] = "DEIN-POSTFACH-SCHLUESSEL"
    v["sprache"]["adresse"] = "http://DEIN-WhISPER:18790/transcribe".replace("WhISPER", "WHISPER")
    v["sprachmodell"]["adresse"] = "http://DEIN-OLLAMA:11434"
    v["sprachmodell"]["modell"] = "DEIN-MODELL"
    v["telegram"]["token"] = "DEIN-TELEGRAM-BOT-TOKEN"
    return v


def konfig_aufruf(pos):
    """Knoten, der die Werte aus dem Ablauf "Konfiguration" holt."""
    return n(KONFIG_KNOTEN, "n8n-nodes-base.executeWorkflow", 1.2, pos,
             {"source": "database",
              "workflowId": {"__rl": True, "value": W_KONFIG, "mode": "list",
                             "cachedResultName": W_KONFIG_NAME},
              "workflowInputs": {
                  "mappingMode": "defineBelow",
                  "value": {"eingang": "={{ JSON.stringify($json) }}"},
                  "matchingColumns": [],
                  "schema": [{"id": "eingang", "displayName": "eingang", "required": False,
                              "defaultMatch": False, "display": True, "type": "string",
                              "canBeUsedToMatch": True, "removed": False}],
                  "attemptToConvertTypes": False, "convertFieldsToString": False}},
             notes="Alle Adressen, Schluessel und Aufgabentexte (Ablauf " + W_KONFIG + ").")


def freie_stelle(ablauf, abstand=200):
    """Platz unterhalb aller Knoten und Rahmen - ausserhalb jeder Gruppe."""
    knoten = ablauf["nodes"]
    x0 = min(k["position"][0] for k in knoten)
    y1 = max(k["position"][1] + (k.get("parameters", {}).get("height") or 0) for k in knoten)
    return [x0, y1 + abstand]


def konfiguration_einsetzen(ablauf, quellen, ziele, weiche=False):
    """Konfigurations-Aufruf zwischen die Quellknoten und ihre Ziele haengen.

    Die Reihenfolge ist wichtig: der Aufruf steht VOR allen Knoten, die Werte
    brauchen - sonst findet "$('Konfiguration')" nichts. Im Bot haengen drei
    Ausloeser an demselben Aufruf; die Weiche dahinter trennt Telegram/Test vom
    Zeitplan, damit beide Wege nur EINEN Konfigurationsknoten haben.
    """
    stelle = freie_stelle(ablauf)
    aufruf = konfig_aufruf(stelle)
    ablauf["nodes"].append(aufruf)
    alte_ziele = {}
    for q in quellen:
        zweige = ablauf["connections"].get(q, {}).get("main", [[]])
        alte_ziele[q] = zweige[0] or []
        ablauf["connections"][q] = {"main": [[{"node": KONFIG_KNOTEN, "type": "main", "index": 0}]]}
    if not weiche:
        ablauf["connections"][KONFIG_KNOTEN] = {"main": [[{"node": ziele[0], "type": "main",
                                                          "index": 0}]]}
        return
    weiche_knoten = n("Weiche Plan?", "n8n-nodes-base.if", 2.2,
                      [stelle[0] + 240, stelle[1]],
                      {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                                  "typeValidation": "loose", "version": 2},
                                      "combinator": "and",
                                      "conditions": [{"id": nid(),
                                                      "leftValue": "={{ !!( $json.body || $json.message"
                                                                   " || $json.callback_query"
                                                                   " || $json.edited_message ) }}",
                                                      "rightValue": "",
                                                      "operator": {"type": "boolean",
                                                                   "operation": "true",
                                                                   "singleValue": True}}]},
                       "options": {}},
                      notes="Ja = Nachricht von Telegram (oder der Testeingang), Nein = Zeitplan.")
    ablauf["nodes"].append(weiche_knoten)
    ablauf["connections"][KONFIG_KNOTEN] = {"main": [[{"node": "Weiche Plan?", "type": "main",
                                                       "index": 0}]]}
    ablauf["connections"]["Weiche Plan?"] = {"main": [
        [{"node": ziele[0], "type": "main", "index": 0}],
        [{"node": ziele[1], "type": "main", "index": 0}],
    ]}


def ablauf_erstes_ziel(ablauf):
    """Erster Knoten hinter dem Ausloeser eines Werkzeug-Ablaufs."""
    return ablauf["connections"]["Eingang"]["main"][0][0]["node"]


konfiguration_einsetzen(agent, ["Telegram Trigger", "Test-Eingang", "REST-Eingang",
                                "Zeitplan Meldungen"],
                        ["Eingabe", "Meldungen holen"], weiche=True)
konfiguration = werkzeug_arbeit(W_KONFIG, W_KONFIG_NAME, [
    n("Eingang", "n8n-nodes-base.executeWorkflowTrigger", 1.1, [-1280, 0],
      {"workflowInputs": {"values": [{"name": "eingang", "type": "string"}],
                          "inputSource": "workflowInputs"}}),
    code("Werte", [-1000, 0], konfig_werte_js(KONFIG)),
], {"Eingang": {"main": [[{"node": "Werte", "type": "main", "index": 0}]]}})
konfiguration["active"] = True
konfiguration["name"] = W_KONFIG_NAME
# Rahmen um die zwei Knoten (dieser Ablauf laeuft nicht ueber anordnen()).
_knoten = list(konfiguration["nodes"])
_x, _y, _b, _h = bereich_kasten(_knoten, "## Zentrale Werte")
konfiguration["nodes"].append(notiz("Notiz Zentrale", _x, _y, _b, _h,
    "## Zentrale Werte\nHier stehen alle Adressen, Schluessel und Aufgabentexte.\n"
    "Geaendert wird nur der Knoten **Werte** - danach speichern, kein Neustart.", 5))
dokunotiz(konfiguration, W_KONFIG_NAME, [
    "EINE Stelle fuer den ganzen Bot: Adressen, Schluessel, Modell, Aufgabentexte.",
    "Bearbeitet wird nur der Knoten 'Werte' (Code). Speichern genuegt, kein Neustart.",
    "Alle vier Ablaeufe holen die Werte beim Start ueber den Knoten 'Konfiguration'.",
    "Aendern: DDD-Webseite/werkzeuge/agent-wf-bauen-ddd.py (KONFIG), dann bauen-de.sh + einspielen.sh",
])

anordnen(agent, ANORDNUNG, BEREICHE, KURZNOTIZ, LANGNOTIZ)
legende_setzen(agent, LEGENDE_BOT)
dokunotiz(agent, "DDD-Webseite Bot - Telegram-Agent (DE/EN) mit REST-Eingang", [
    "Der Bot: Telegram-Eingang -> Stufe 0/1 (verstehen und planen) -> Stufe 2 (ausfuehren) -> Stufe 3 (Antwort).",
    "REST-Eingang: POST .../webhook/ddd-webseite-rest mit {\"text\": \"...\"} + Schluessel - Antwort als JSON.",
    "Der Plan ist die Quelle der Anordnung: DDD-Webseite/werkzeuge/agent-wf-bauen-ddd.py (ANORDNUNG, BEREICHE, KURZNOTIZ).",
    "Aendern: bauen-de.sh (erzeugt /tmp/ddd-webseite-agent.json), dann einspielen.sh",
    "Pruefen: pruefen.sh (Anordnung + Code-Knoten), Betrieb: DDD-Webseite/README.md",
    "Beschreibung: README.md, HANDBUCH.md, HANDBUCH.md, BETRIEB.md, BETRIEB.md, BETRIEB.md, BAU.md",
    "Bild fuer Bild: ANHANG/n8n-oberflaeche.html  (Projektordner Ai_Radio_Moderator_Bot)",
])
# ------------------------------------------------- Anordnung der Werkzeuge
# Dieselbe Idee wie beim Bot: je Zweig eine Zeile, darum ein Rahmen mit
# Ueberschrift. Die Weichen liegen auf der Hauptzeile (y = 0).
W_ANORDNUNG = {
    "Eingang": (-900, 0),
    "Konfiguration": (-900, 260),
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

W_BEREICHE = [
    ("Notiz W Weichen", 5, """## Weichen
Richtung, Zustand oder Titelsuche - eines von drei.""",
     ["Konfiguration", "Eingang", "Richtung?", "Nur Status?"]),
    ("Notiz W Richtung", 4, """## Zweig: Richtung
Stimmung, Genre oder Jahrzehnt aus dem Katalogdienst.""",
     ["Richtung suchen", "Vorschlaege aufbereiten"]),
    ("Notiz W Suche", 1, """## Zweig: Titel suchen
Katalogdienst (unscharf) und Volltextsuche des Senders.""",
     ["Suche klug", "Suche Sender", "Treffer aufbereiten"]),
    ("Notiz W Status", 6, """## Zweig: Was laeuft
Nur der Zustand - die Rueckgabe ist der Text.""",
     ["NowPlaying", "Status aufbereiten"]),
    ("Notiz W Abspielen", 3, """## Abspielen
Ohne Pfad wird nichts eingetragen - dann bleibt es bei einer Auswahlliste.
Mit Pfad: erst die unterbrechende Warteschlange leeren, dann sofort oder hinten an.""",
     ["Treffer da?", "Einreihen?", "Warteschlange leeren", "Sofort eintragen",
      "Danach eintragen"]),
    ("Notiz W Ausgabe", 2, """## Ausgabe
Hier endet der Werkzeug-Ablauf - der Text geht an den Agenten zurueck.""",
     ["Ergebnis"]),
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
    "Konfiguration": (-900, 260),
    "Adressen suchen?": (-660, 0),
    "Aufruf?": (-420, 0),
    "Wache": (300, 0),
    "Ausfuehren?": (540, 0),
    "Nur lesen?": (780, 0),
    "Aufruf Ergebnis": (1260, 0),
    "Lesen": (1020, 220),
    "Schreiben": (1020, 460),
    "Trockenlauf": (780, 560),
    "Beschreibung holen": (-420, -480),
    "Adressen finden": (-180, -480),
    "Anlagen": (-420, 1020),
    "Zustand": (-180, 1020),
    "Wiedergabelisten": (60, 1020),
    "Ueberblick": (300, 1020),
}

W_AZ_BEREICHE = [
    ("Notiz AZ Weichen", 5, """## Weichen
Adressen nachschlagen, eine Schnittstelle aufrufen oder Ueberblick geben.""",
     ["Konfiguration", "Eingang", "Adressen suchen?", "Aufruf?"]),
    ("Notiz AZ Adressen", 4, """## Zweig: Adressen
Das Verzeichnis des Katalogdienstes nach Adressen durchsuchen.""",
     ["Beschreibung holen", "Adressen finden"]),
    ("Notiz AZ Aufruf", 6, """## Zweig: Aufruf
**Wache** prueft Methode und Pfad; Aendern nur mit `bestaetigt: true`.
Zwei Schritte: Trockenlauf zurueckgeben oder wirklich aufrufen.""",
     ["Wache", "Ausfuehren?", "Nur lesen?", "Lesen", "Schreiben", "Aufruf Ergebnis",
      "Trockenlauf"]),
    ("Notiz AZ Ueberblick", 3, """## Zweig: Ueberblick
Anlagen, Sendeteil, Ausgabe und Wiedergabelisten in einem Text.""",
     ["Anlagen", "Zustand", "Wiedergabelisten", "Ueberblick"]),
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

# --- 3) Meldungen: Postfach des Suchbots und Ansagen des Moderators
MELDUNG_ERGEBNIS_JS = r"""
// Je nach Auftrag hat einer der Knoten geantwortet - hier nur den Text weitergeben.
const namen = ['Recherche holen', 'Meldung ansagen', 'Freie Ansage', 'Meldung verwerfen',
               'Sprechtext holen', 'Offene holen'];
let j = {};
let quelle = '';
for (const name of namen) {
  try {
    const x = $(name).first().json;
    if (x && Object.keys(x).length) { j = x; quelle = name; break; }
  } catch (e) { /* Knoten ist nicht gelaufen */ }
}
if (j.error) return [{ json: { ergebnis: 'Der Meldungsdienst hat nicht geantwortet: '
  + String(j.error.message || j.error).slice(0, 160) } }];
if (!quelle) return [{ json: { ergebnis: 'Kein Auftrag erkannt. Moeglich sind: anzeigen, lesen, '
  + 'ansagen, verwerfen, text.' } }];

if (quelle === 'Offene holen') {
  const liste = Array.isArray(j.meldungen) ? j.meldungen : [];
  if (!liste.length) return [{ json: { ergebnis: 'Keine offenen Meldungen im Postfach.',
    auswahl: [] } }];
  const zeilen = liste.map((m, i) => (i + 1) + '. ' + (m.wichtig ? 'WICHTIG ' : '')
    + m.art + ': ' + (m.titel || String(m.text || '').slice(0, 60)) + ' (kennung ' + m.id + ')');
  return [{ json: { ergebnis: 'Offene Meldungen (' + j.offen + '): ' + zeilen.join(' | '),
    auswahl: liste.map((m) => m.id) } }];
}
if (quelle === 'Sprechtext holen') {
  return [{ json: { ergebnis: 'Sprechtext (' + j.zeichen + ' Zeichen): ' + j.sprechtext,
    auswahl: [j.id] } }];
}
return [{ json: { ergebnis: String(j.antwort || j.gesprochen || 'Erledigt.').slice(0, 400),
  auswahl: [String(j.id || '')].filter(Boolean) } }];
"""

werkzeuge.append(werkzeug_arbeit(W_MELDUNGEN, W_MELDUNGEN_NAME, [
    trigger([-900, 0], [{"name": "auftrag", "type": "string"},
                        {"name": "kennung", "type": "string"},
                        {"name": "text", "type": "string"},
                        {"name": "art", "type": "string"},
                        {"name": "wort", "type": "string"},
                        {"name": "themen", "type": "string"},
                        {"name": "quellen", "type": "string"},
                        {"name": "ansagen", "type": "boolean"}]),

    # --- Zweig: Recherche (Wetter, Nachrichten, Feed, Kurzinfo)
    wenn("Recherche?", [-660, 0], "={{ !!String($json.art || '').trim() }}",
         "Ja = etwas nachschlagen und als Meldung ansagen."),
    n("Recherche holen", "n8n-nodes-base.httpRequest", 4.2, [-420, -260], {
        "method": "POST", "url": MELDUNGEN + "/recherche",
        "sendHeaders": True, "headerParameters": {"parameters": MELDUNG_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": ("={{ JSON.stringify({ art: String($json.art || '').trim().toLowerCase(),"
                     " wort: String($json.wort || '').trim(),"
                     " quellen: String($json.quellen || '').trim(),"
                     " themen: String($json.themen || '').trim(),"
                     " ansagen: $json.ansagen === undefined ? true : $json.ansagen === true }) }}"),
        "options": {"timeout": 900000},
    }, onError="continueRegularOutput",
       notes="Holt Wetter, Nachrichten, einen Feed, einen Ueberblick ueber mehrere "
             "Quellen oder eine Kurzinfo, legt sie als Meldung ab und spricht sie bei "
             "ansagen=true sofort in den Sender. Ein Ueberblick dauert Minuten - daher "
             "15 Minuten Zeitablauf."),

    wenn("Sprechen?", [-660, 240],
         "={{ ['ansagen','text'].includes(String($json.auftrag || '').trim()) }}",
         "Ja = eine Ansage sprechen (freier Text oder Meldung)."),

    # --- Zweig: Ansage
    wenn("Freier Text?", [-420, -220], "={{ !!String($json.text || '').trim() }}",
         "Ja = freier Text, Nein = abgelegte Meldung."),
    n("Freie Ansage", "n8n-nodes-base.httpRequest", 4.2, [-180, -440], {
        "method": "POST", "url": MELDUNGEN + "/ansage/text",
        "sendHeaders": True, "headerParameters": {"parameters": MELDUNG_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ text: String($json.text || '').trim() }) }}",
        "options": {"timeout": 900000},
    }, onError="continueRegularOutput",
       notes="Spricht freien Text live in den Sender (Piper -> DJ-Hafen)."),
    n("Meldung ansagen", "n8n-nodes-base.httpRequest", 4.2, [-180, -220], {
        "method": "POST", "url": MELDUNGEN + "/ansage/meldung",
        "sendHeaders": True, "headerParameters": {"parameters": MELDUNG_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ id: String($json.kennung || '').trim() }) }}",
        "options": {"timeout": 900000},
    }, onError="continueRegularOutput",
       notes="Spricht die Meldung live in den Sender - dauert so lange wie die Ansage."),

    # --- Zweig: verwerfen
    wenn("Verwerfen?", [-420, 200], "={{ String($json.auftrag || '').trim() === 'verwerfen' }}",
         "Ja = Meldung als verworfen weglegen."),
    n("Meldung verwerfen", "n8n-nodes-base.httpRequest", 4.2, [-180, 200], {
        "method": "POST", "url": MELDUNGEN + "/meldungen/erledigt",
        "sendHeaders": True, "headerParameters": {"parameters": MELDUNG_KOPF},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": ("={{ JSON.stringify({ ids: [String($json.kennung || '').trim()],"
                     " grund: 'verworfen' }) }}"),
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput", notes="Legt die Meldung als verworfen weg."),

    # --- Zweig: lesen oder anzeigen
    wenn("Kennung?", [-420, 460], "={{ !!String($json.kennung || '').trim() }}",
         "Ja = Sprechtext einer Meldung zeigen, Nein = offene Meldungen auflisten."),
    n("Sprechtext holen", "n8n-nodes-base.httpRequest", 4.2, [-180, 460], {
        "method": "GET",
        "url": ("={{ " + K + ".dienst.adresse + '/meldungen/text/' + String($json.kennung || '').trim() }}"),
        "sendHeaders": True, "headerParameters": {"parameters": MELDUNG_KOPF},
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput", notes="Zeigt, was der Moderator sprechen wuerde."),
    n("Offene holen", "n8n-nodes-base.httpRequest", 4.2, [-180, 700], {
        "method": "GET", "url": MELDUNGEN + "/meldungen/offen",
        "sendQuery": True,
        "queryParameters": {"parameters": [{"name": "anzahl", "value": "5"}]},
        "sendHeaders": True, "headerParameters": {"parameters": MELDUNG_KOPF},
        "options": {"timeout": 20000},
    }, onError="continueRegularOutput", notes="Offene Meldungen im Postfach (wichtige zuerst)."),

    code("Ergebnis Meldungen", [120, 120], MELDUNG_ERGEBNIS_JS),
], {
    "Eingang": {"main": [[{"node": "Recherche?", "type": "main", "index": 0}]]},
    "Recherche?": {"main": [
        [{"node": "Recherche holen", "type": "main", "index": 0}],
        [{"node": "Sprechen?", "type": "main", "index": 0}]]},
    "Recherche holen": {"main": [[{"node": "Ergebnis Meldungen", "type": "main", "index": 0}]]},
    "Sprechen?": {"main": [
        [{"node": "Freier Text?", "type": "main", "index": 0}],
        [{"node": "Verwerfen?", "type": "main", "index": 0}]]},
    "Freier Text?": {"main": [
        [{"node": "Freie Ansage", "type": "main", "index": 0}],
        [{"node": "Meldung ansagen", "type": "main", "index": 0}]]},
    "Freie Ansage": {"main": [[{"node": "Ergebnis Meldungen", "type": "main", "index": 0}]]},
    "Meldung ansagen": {"main": [[{"node": "Ergebnis Meldungen", "type": "main", "index": 0}]]},
    "Verwerfen?": {"main": [
        [{"node": "Meldung verwerfen", "type": "main", "index": 0}],
        [{"node": "Kennung?", "type": "main", "index": 0}]]},
    "Meldung verwerfen": {"main": [[{"node": "Ergebnis Meldungen", "type": "main", "index": 0}]]},
    "Kennung?": {"main": [
        [{"node": "Sprechtext holen", "type": "main", "index": 0}],
        [{"node": "Offene holen", "type": "main", "index": 0}]]},
    "Sprechtext holen": {"main": [[{"node": "Ergebnis Meldungen", "type": "main", "index": 0}]]},
    "Offene holen": {"main": [[{"node": "Ergebnis Meldungen", "type": "main", "index": 0}]]},
}))

# Anordnung des Meldungs-Werkzeugs: je Zweig eine Zeile, Weichen auf der Hauptzeile.
W_MELD_ANORDNUNG = {
    "Eingang": (-900, 120),
    "Konfiguration": (-900, 380),
    "Recherche?": (-660, 120),
    "Recherche holen": (400, -140),
    "Sprechen?": (-660, 380),
    "Freier Text?": (-420, 160),
    "Freie Ansage": (400, 300),
    "Meldung ansagen": (400, 520),
    "Verwerfen?": (-420, 620),
    "Meldung verwerfen": (400, 950),
    "Kennung?": (-420, 880),
    "Sprechtext holen": (400, 1210),
    "Offene holen": (400, 1470),
    "Ergebnis Meldungen": (900, 620),
}

W_MELD_BEREICHE = [
    ("Notiz M Weichen", 5, """## Weichen
Recherche, Ansage, Verwerfen oder Sprechtext - der Auftrag entscheidet.
Jede Weiche prueft ein Feld des Werkzeugs.""",
     ["Konfiguration", "Eingang", "Recherche?", "Sprechen?", "Verwerfen?", "Kennung?",
      "Freier Text?"]),
    ("Notiz M Recherche", 4, """## Recherche
Wetter, Nachrichten, Feed oder Kurzinfo holen, als Meldung ablegen und ansagen.""",
     ["Recherche holen"]),
    ("Notiz M Ansage", 1, """## Ansagen
Freien Text oder eine abgelegte Meldung live in den Sender sprechen.""",
     ["Freie Ansage", "Meldung ansagen"]),
    ("Notiz M Postfach", 3, """## Postfach
Offene Meldungen auflisten, Sprechtext zeigen oder eine Meldung verwerfen.""",
     ["Meldung verwerfen", "Sprechtext holen", "Offene holen"]),
    ("Notiz M Ausgabe", 2, """## Ausgabe
Hier endet der Werkzeug-Ablauf - der Text geht an den Agenten zurueck.""",
     ["Ergebnis Meldungen"]),
]

W_MELD_LANGNOTIZ = {
    "Eingang": "Felder des Werkzeugs: auftrag, kennung, text, art, wort, ansagen.",
    "Recherche?": "Ja = recherchieren (art=wetter, nachrichten, rss oder wikipedia).",
    "Recherche holen": "Holt die Daten, legt sie als Meldung ab und sagt sie bei ansagen=true an.",
    "Sprechen?": "Ja = eine Ansage sprechen (auftrag ansagen oder text).",
    "Freier Text?": "Ja = freier Text, Nein = Meldung aus dem Postfach.",
    "Freie Ansage": "Spricht freien Text live in den Sender.",
    "Meldung ansagen": "Spricht eine abgelegte Meldung live in den Sender.",
    "Verwerfen?": "Ja = Meldung als verworfen weglegen.",
    "Meldung verwerfen": "Setzt die Meldung auf verworfen.",
    "Kennung?": "Ja = Sprechtext zeigen, Nein = offene Meldungen auflisten.",
    "Sprechtext holen": "Zeigt den Text, den der Moderator sprechen wuerde.",
    "Offene holen": "Offene Meldungen (wichtige zuerst).",
    "Ergebnis Meldungen": "Ausgabeknoten: hier endet der Werkzeug-Ablauf.",
}

for _w in werkzeuge:
    konfiguration_einsetzen(_w, ["Eingang"], [ablauf_erstes_ziel(_w)])
anordnen(werkzeuge[0], W_ANORDNUNG, W_BEREICHE, {}, W_LANGNOTIZ)
anordnen(werkzeuge[1], W_ANORDNUNG_AZ, W_AZ_BEREICHE, {}, W_AZ_LANGNOTIZ)
anordnen(werkzeuge[2], W_MELD_ANORDNUNG, W_MELD_BEREICHE, {}, W_MELD_LANGNOTIZ)
dokunotiz(werkzeuge[0], "DDD-Webseite Werkzeug Radio", [
    "Unterschnittstelle des Agenten fuer Musik: Weichen, Titel suchen, Richtung, Zustand, abspielen.",
    "Aufgerufen wird sie ueber die Werkzeugknoten des Agenten (Werkzeug Titel suchen usw.).",
    "Der Plan ist die Quelle: DDD-Webseite/werkzeuge/agent-wf-bauen-ddd.py (W_ANORDNUNG, W_BEREICHE).",
    "Aendern/Pruefen wie beim Agenten; Beschreibung: HANDBUCH.md, HANDBUCH.md, ANHANG/n8n-oberflaeche.html",
])
dokunotiz(werkzeuge[1], "DDD-Webseite Werkzeug AzuraCast", [
    "Unterschnittstelle fuer den Sender: Adressen nachschlagen, Schnittstelle aufrufen, Ueberblick.",
    "Die Adressen kommen aus der OpenAPI-Beschreibung des Senders (263 Endpunkte).",
    "Der Plan ist die Quelle: DDD-Webseite/werkzeuge/agent-wf-bauen-ddd.py (W_ANORDNUNG_AZ, W_AZ_BEREICHE).",
    "Aendern/Pruefen wie beim Agenten; Beschreibung: HANDBUCH.md, ANHANG/n8n-oberflaeche.html",
])
dokunotiz(werkzeuge[2], "DDD-Webseite Werkzeug Meldungen", [
    "Unterschnittstelle fuer Ansage und Postfach: Recherche, freie Ansage, Meldung sprechen/verwerfen.",
    "Spricht ueber den Dienst ddd-radio (Piper + DJ-Hafen), legt Meldungen im Postfach ab.",
    "Der Plan ist die Quelle: DDD-Webseite/werkzeuge/agent-wf-bauen-ddd.py (W_MELD_ANORDNUNG, W_MELD_BEREICHE).",
    "Aendern/Pruefen wie beim Agenten; Beschreibung: HANDBUCH.md §1.3, HANDBUCH.md",
])

with open("/tmp/ddd-webseite-konfiguration.json", "w", encoding="utf-8") as f:
    json.dump([konfiguration], f, ensure_ascii=False, indent=2)
with open("/tmp/ddd-webseite-werkzeuge.json", "w", encoding="utf-8") as f:
    json.dump(werkzeuge, f, ensure_ascii=False, indent=2)
with open("/tmp/ddd-webseite-agent.json", "w", encoding="utf-8") as f:
    json.dump(agent, f, ensure_ascii=False, indent=2)

# Vorlage fuer andere: dieselben Ablaufe mit Platzhaltern statt Zugangsdaten.
if os.environ.get("VORLAGE"):
    _ordner = os.environ.get("VORLAGE_ZIEL", "/tmp/radio-vorlage")
    os.makedirs(_ordner, exist_ok=True)
    _vorlage = json.loads(json.dumps(konfiguration))
    for _k in _vorlage["nodes"]:
        if _k["name"] == "Werte":
            _k["parameters"]["jsCode"] = konfig_werte_js(konfig_platzhalter(KONFIG))
    _vorlage["name"] = W_KONFIG_NAME + " (Vorlage)"
    with open(_ordner + "/01-konfiguration.json", "w", encoding="utf-8") as f:
        json.dump([_vorlage], f, ensure_ascii=False, indent=2)
    with open(_ordner + "/02-werkzeuge.json", "w", encoding="utf-8") as f:
        json.dump(werkzeuge, f, ensure_ascii=False, indent=2)
    with open(_ordner + "/03-bot.json", "w", encoding="utf-8") as f:
        json.dump([agent], f, ensure_ascii=False, indent=2)
    print("Vorlage geschrieben nach", _ordner)


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

print("geschrieben: /tmp/ddd-webseite-werkzeuge.json (%d Arbeitsablaeufe), /tmp/ddd-webseite-agent.json"
      % len(werkzeuge))
print("Verbindungen geprueft:", " + ".join(w["name"] for w in werkzeuge + [agent]))
print("Bot-Knoten:", len(bot))
for w in werkzeuge:
    print("  ", w["id"], "->", w["name"], "|", len(w["nodes"]), "Knoten")
