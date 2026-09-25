"""Meldungen und Ansagen: das Postfach fuer den Suchbot und die Moderation.

Zwei Aufgaben in einem Modul:

1. **Postfach** — ein anderer Bot (Suchbot: Wetter, RSS-Feeds, Nachrichten)
   legt Meldungen hier ab. Der Radio-Bot holt sie ab, zeigt sie im Telegram zur
   Freigabe und laesst sie dann sprechen.

2. **Ansage** — aus einer Meldung wird ein Moderations-Text gebaut und ueber den
   DJ-Hafen live in den laufenden Sendebetrieb gesprochen (`POST /live` in
   `main.py`, Piper + lameenc + Liquidsoap-Hafen). Trockenlauf (`trocken: true`)
   erzeugt nur den Text, ohne zu senden.

Speicher: `/daten/meldungen.json` (Band `./daten` des Dienstes, neben dem Katalog).
Zugang: gemeinsamer Schluessel im Kopf `X-Meldung-Schluessel`. Der Wert steht in
`/daten/meldung-schluessel.txt` (wird beim ersten Start erzeugt, Rechte 600) oder
in der Umgebungsvariablen `MELDUNG_SCHLUESSEL`. Nur `/meldungen/status` und
`/ansage/status` sind ohne Schluessel lesbar (für die Kontrolle).

Die Adressen sind bewusst einfach und stabil — ein fremder Bot braucht nur:

    POST /meldungen/neu        Meldung abgeben (einzeln oder als Liste)
    GET  /meldungen/offen      offene Meldungen abholen (Radio-Bot)
    POST /meldungen/erledigt   gesagt oder verworfen
    GET  /meldungen/text/<id>  Vorschau des Moderations-Textes
    POST /ansage/meldung       Meldung sprechen (live in den Sender)
    POST /ansage/text          freien Text sprechen
"""
from __future__ import annotations

import io
import json
import os
import re
import secrets
import threading
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

DATEN = Path(os.environ.get("KATALOG_DIR", "/daten"))
DATEI = DATEN / "meldungen.json"
SCHLUESSEL_DATEI = DATEN / "meldung-schluessel.txt"

# Hoechstlaenge einer Ansage. Ursprung: rund 45 Sekunden. Seit dem Ueberblick
# (2026-09-20) sind auch laengere Beitraege gewuenscht - gemessen spricht Piper
# rund 1050 Zeichen je Minute, 9000 Zeichen sind also etwa 8,5 Minuten.
# Liquidsoap vertraegt das (im Sendetakt gesendet), die Grenze schuetzt nur vor
# versehentlich riesigen Texten.
MAX_ZEICHEN = int(os.environ.get("ANSAGE_MAX_ZEICHEN", "9000"))
# Wie viele Meldungen und Ansagen aufgehoben werden.
MAX_MELDUNGEN = int(os.environ.get("MELDUNGEN_MAX", "500"))
MAX_ANSAGEN = int(os.environ.get("ANSAGEN_MAX", "100"))
# Derselbe freie Text wird innerhalb dieser Sekunden nicht zweimal gesprochen.
# Schutz vor Werkzeug-Schleifen des Modells (nach einem Vorfall am Abend
# uebernommen: ein Befehl
# sprach erst die Nachrichten und danach noch einen 1,4-Minuten-Ueberblick).
ANSAGE_SPERRE_SEK = int(os.environ.get("ANSAGE_SPERRE_SEK", "90"))

SPERRE = threading.Lock()

ARTEN = ("wetter", "nachrichten", "rss", "verkehr", "hinweis", "musik", "ueberblick",
         "sonstiges")

# Vorspann je Art - deine Stimme: kurz, persoenlich, mit einem Zwinkern.
# Der Charakter der Figur (charakter.md) faerbt im Bot die frei formulierten
# Ansagen; diese festen Zeilen gehoeren als Stimme des Hauses dazu.
VORSPANN: dict[str, str] = {
    "wetter": "Und nun der Blick zum Himmel - ich habe für euch nachgesehen.",
    "nachrichten": "Kurz die Nachrichten - ich habe genau hingehört.",
    "rss": "Frisch aus dem Netz - für euch herausgesucht.",
    "verkehr": "Passt einen Moment auf - eine Verkehrsmeldung.",
    "hinweis": "Eine Durchsage in eigener Sache.",
    "musik": "",
    # Beim Ueberblick traegt der Titel den Einstieg, sonst kaeme er zweimal.
    "ueberblick": "",
    "sonstiges": "Ich habe eine Meldung für euch.",
}
NACHSPANN: dict[str, str] = {
    "wetter": "Das war das Wetter - und jetzt wieder Musik für euch.",
    "nachrichten": "",
    "rss": "",
    "verkehr": "Und weiter geht es mit Musik.",
    "hinweis": "",
    "musik": "",
    "ueberblick": "Das war der Überblick - und jetzt wieder Musik für euch.",
    "sonstiges": "",
}


# --------------------------------------------------------------- Schluessel

def schluessel() -> str:
    """Der gemeinsame Schluessel. Wird beim ersten Aufruf erzeugt."""
    aus_umgebung = os.environ.get("MELDUNG_SCHLUESSEL", "").strip()
    if aus_umgebung:
        return aus_umgebung
    if SCHLUESSEL_DATEI.exists():
        wert = SCHLUESSEL_DATEI.read_text(encoding="utf-8").strip()
        if wert:
            return wert
    wert = secrets.token_urlsafe(24)
    try:
        DATEN.mkdir(parents=True, exist_ok=True)
        SCHLUESSEL_DATEI.write_text(wert + "\n", encoding="utf-8")
        SCHLUESSEL_DATEI.chmod(0o600)
    except OSError as fehler:  # noqa: BLE001
        print("Meldungsschluessel konnte nicht gespeichert werden:", fehler, flush=True)
    return wert


def _pruefen(gegeben: str | None) -> None:
    if not gegeben or not secrets.compare_digest(gegeben, schluessel()):
        raise HTTPException(status_code=403, detail="X-Meldung-Schluessel fehlt oder passt nicht.")


def _jetzt() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ------------------------------------------------------------------ Speicher

def _leer() -> dict[str, Any]:
    return {"meldungen": [], "ansagen": [], "zaehler": 0}


def _laden() -> dict[str, Any]:
    if not DATEI.exists():
        return _leer()
    try:
        daten = json.loads(DATEI.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as fehler:  # noqa: BLE001
        print("meldungen.json nicht lesbar:", fehler, flush=True)
        return _leer()
    if not isinstance(daten, dict):
        return _leer()
    daten.setdefault("meldungen", [])
    daten.setdefault("ansagen", [])
    daten.setdefault("zaehler", 0)
    return daten


def _speichern(daten: dict[str, Any]) -> None:
    DATEN.mkdir(parents=True, exist_ok=True)
    daten["meldungen"] = daten["meldungen"][-MAX_MELDUNGEN:]
    daten["ansagen"] = daten["ansagen"][-MAX_ANSAGEN:]
    vorlaeufig = DATEI.with_suffix(".json.tmp")
    vorlaeufig.write_text(json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8")
    vorlaeufig.replace(DATEI)


def _meldung(daten: dict[str, Any], kennung: str) -> dict[str, Any] | None:
    for m in daten["meldungen"]:
        if str(m.get("id")) == str(kennung):
            return m
    return None


def _reihenfolge(m: dict[str, Any]) -> tuple[int, str]:
    """Wichtiges zuerst, dann die neuesten."""
    return (0 if m.get("wichtig") else 1, str(m.get("eingang") or ""))


# ------------------------------------------------- Moderations-Text bauen

# Fuers Sprechen aufbereiten: URLs, Markup und Abkuerzungen stoeren Piper oder
# klingen vorgelesen falsch ("z.B." wird zu "zet-be").
#
# Achtung: die Abkuerzungsmuster duerfen NICHT mit \b enden. Nach einem Punkt
# vor einem Leerzeichen gibt es keine Wortgrenze - "\bz\.B\.\b" passt nie
# (Fehler am 2026-09-20: "z.B." blieb stehen und wurde buchstabiert).
KEIN_BUCHSTABE = r"(?![A-Za-z\u00c4\u00d6\u00dc\u00e4\u00f6\u00fc\u00df])"

ERSETZEN: list[tuple[str, str]] = [
    (r"https?://\S+", ""),
    (r"\bwww\.\S+", ""),
    (r"\b[\w.-]+\.(?:de|com|org|net|at|ch|io)\b", ""),
    (r"[*_`#>|]+", ""),
    # Ticker-Zeichen der Nachrichtenfeeds ("+++ Meldung +++") nicht vorlesen.
    (r"\s*\+{2,}\s*", " "),
    # Quellenverweise aus Wikipedia ("[1]", "[ 1.1 ]") nicht vorlesen.
    (r"\[\s*\d+(?:[.,]\d+)*\s*\]", " "),
    (r"\[([^\]]*)\]", r"\1"),
    # Agentur-Klammern sind Etiketten, kein Text ("(dpa)", "(dpa/afp)").
    (r"\(\s*(?:dpa|afp|rtr|reuters|epd|kna|sid|ots|apa|ap)(?:[\s/,-]*[a-z]+)*\s*\)", " "),
    (r"\(([^)]*)\)", r"\1"),
    (r"\s*[\u2013\u2014]\s*", ", "),
    (r"\u00b0\s*C\b", " Grad"),
    (r"\u00b0", " Grad"),
    (r"\bkm/h\b", "Kilometer pro Stunde"),
    (r"\bm/s\b", "Meter pro Sekunde"),
    (r"\bmm\b", "Millimeter"),
    (r"\bl/m\u00b2\b", "Liter pro Quadratmeter"),
    (r"\bhPa\b", "Hektopascal"),
    (r"%", " Prozent"),
    # Abkuerzungen (siehe Hinweis oben)
    (r"\bz\.\s?B\." + KEIN_BUCHSTABE, "zum Beispiel"),
    (r"\bu\.\s?a\." + KEIN_BUCHSTABE, "unter anderem"),
    (r"\bbzw\." + KEIN_BUCHSTABE, "beziehungsweise"),
    (r"\bca\." + KEIN_BUCHSTABE, "circa"),
    (r"\bevtl\." + KEIN_BUCHSTABE, "eventuell"),
    (r"\binkl\." + KEIN_BUCHSTABE, "inklusive"),
    (r"\bggf\." + KEIN_BUCHSTABE, "gegebenenfalls"),
    (r"\bd\.\s?h\." + KEIN_BUCHSTABE, "das heißt"),
    (r"\bmax\." + KEIN_BUCHSTABE, "maximal"),
    (r"\bmin\." + KEIN_BUCHSTABE, "minimal"),
    (r"\bNr\." + KEIN_BUCHSTABE, "Nummer"),
    (r"\bStr\." + KEIN_BUCHSTABE, "Straße"),
    (r"\bStd\." + KEIN_BUCHSTABE, "Stunden"),
    (r"\bMio\." + KEIN_BUCHSTABE, "Millionen"),
    (r"\bMrz\." + KEIN_BUCHSTABE, "März"),
    (r"\bOkt\." + KEIN_BUCHSTABE, "Oktober"),
    (r"\bDez\." + KEIN_BUCHSTABE, "Dezember"),
    (r"\bvs\." + KEIN_BUCHSTABE, "gegen"),
    (r"&", " und "),
    # Bildnachweise und Rechte-Hinweise aus Feed-Texten nicht vorlesen.
    # Vorsicht: "Bild" ist auch ein Zeitungsname - deshalb nur "Bild:" entfernen.
    (r"\bAlle Rechte vorbehalten\b[:\s]*", " "),
    (r"\b(?:IMAGO|Getty Images|picture alliance|Symbolbild|Archivbild)\b", " "),
    (r"\b(?:Foto|Bild)\s*:\s*", " "),
    # Nach dem Entfernen einer Quelle bleibt sonst "Details auf." stehen.
    # Zwei Feinheiten (am 2026-09-21 gemessen):
    #  * die Wortgrenze am Ende ist Pflicht - ohne sie frisst "Infos?" das "Info"
    #    aus "Informatik" ("Anwendungsgebiet der rmatik").
    #  * das Muster gilt nur am ENDE des Textes - sonst verschwindet jedes
    #    "Informationen" mitten im Satz.
    (r"\s*\b(?:Details?|Mehr|Infos?|Informationen|Nachzulesen|Quelle|Link)\b\s*"
     r"(?:auf|unter|bei|im|in|hier|dazu|:)?\s*\.?\s*$", ""),
]

# Emojis und sonstiges Zeichenwerk, das Piper nicht sprechen soll.
UNSPRECHBAR = re.compile(
    "[" "\U0001F000-\U0001FAFF" "\U00002600-\U000027BF" "\U0001F1E6-\U0001F1FF" "\u2b00-\u2bff" "\u2190-\u21ff" "]"
)

# Autorenzeilen der Nachrichtenfeeds sind kein Sprechtext ("... Von Stephan
# Ueberbach." stand am 2026-09-25 als Satz in der Tagesschau-Ansage). Nur am
# ENDE und mit großen Anfangsbuchstaben - "das sagte von der Leyen" bleibt.
AUTOR_ZEILE = re.compile(
    r"\s+Von\s+(?:(?:[A-ZÄÖÜ][\w’'\-.]*|und)\s+){1,5}[A-ZÄÖÜ][\w’'\-.]*\.?\s*$")
AUTOR_KURZ = re.compile(r"\s+Von\s+(?:dpa|afp|rtr|reuters|epd|kna|sid|ots)\b[^.]*\.?\s*$", re.I)


def sprechbar(text: str) -> str:
    """Macht aus einem Meldungstext etwas, das sich sauber sprechen laesst."""
    s = str(text or "")
    s = s.replace("\u00a0", " ").replace("\u201e", " ").replace("\u201c", " ")
    s = UNSPRECHBAR.sub(" ", s)
    for muster, ersatz in ERSETZEN:
        s = re.sub(muster, ersatz, s, flags=re.I)
    s = AUTOR_ZEILE.sub(" ", s)
    s = AUTOR_KURZ.sub(" ", s)
    # Aufzaehlungen und Zeilenumbrueche zu einem Fliesstext
    s = re.sub(r"(?m)^\s*[-•·]\s*", " ", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    s = re.sub(r"([,.;:!?])(?=[A-Za-zÄÖÜäöü])", r"\1 ", s)
    s = re.sub(r"\.{2,}", ".", s)
    s = re.sub(r"\s*,\s*", ", ", s)
    return s.strip(" ,;:-")


def kuerzen(text: str, grenze: int = MAX_ZEICHEN) -> str:
    """Am letzten Satzende kuerzen - angefangene Saetze klingen schlecht."""
    if len(text) <= grenze:
        return text
    teil = text[:grenze]
    schnitt = max(teil.rfind(". "), teil.rfind("! "), teil.rfind("? "))
    if schnitt < grenze * 0.5:
        schnitt = teil.rfind(" ")
    if schnitt <= 0:
        return teil.strip()
    return teil[: schnitt + 1].strip()


def moderationstext(meldung: dict[str, Any]) -> str:
    """Baut den Text, den der Moderator spricht."""
    art = str(meldung.get("art") or "sonstiges").lower()
    if art not in VORSPANN:
        art = "sonstiges"
    vorspann = VORSPANN.get(art, "")
    nachspann = NACHSPANN.get(art, "")
    titel = sprechbar(meldung.get("titel") or "")
    inhalt = sprechbar(meldung.get("text") or "")
    stuecke = [sprechbar(vorspann)]
    # Der Titel enthaelt oft nur eine Wiederholung ("Wetter Berlin") - nur
    # vorlesen, wenn er nicht schon am Anfang des Textes steht.
    if titel and titel.lower()[:18] not in inhalt.lower()[:40]:
        stuecke.append(titel + ".")
    stuecke.append(inhalt)
    if nachspann:
        stuecke.append(sprechbar(nachspann))
    text = " ".join(s for s in stuecke if s).strip()
    text = re.sub(r"\s+", " ", text)
    return kuerzen(text)


# ------------------------------------------------------------------ Modelle

class Meldung(BaseModel):
    quelle: str = ""
    art: str = "sonstiges"
    titel: str = ""
    text: str = ""
    url: str = ""
    wichtig: bool = False
    von: str = ""
    bis: str = ""


class Meldungsliste(BaseModel):
    meldungen: list[Meldung] = Field(default_factory=list)


class Erledigt(BaseModel):
    ids: list[str] = Field(default_factory=list)
    grund: Literal["gesagt", "verworfen", "abgelaufen"] = "verworfen"


class Angeboten(BaseModel):
    ids: list[str] = Field(default_factory=list)


class AnsageMeldung(BaseModel):
    id: str
    trocken: bool = False
    stimme: str = ""
    speed: float = Field(default=1.0, ge=0.3, le=3.0)


class AnsageText(BaseModel):
    text: str
    trocken: bool = False
    stimme: str = ""
    speed: float = Field(default=1.0, ge=0.3, le=3.0)


# ------------------------------------------------------------------ Aufnahme

def _aufnehmen(neu: Meldung, daten: dict[str, Any]) -> dict[str, Any]:
    daten["zaehler"] = int(daten.get("zaehler", 0)) + 1
    kennung = f"m{datetime.now(timezone.utc):%y%m%d}-{daten['zaehler']:04d}"
    art = (neu.art or "sonstiges").strip().lower()
    if art not in ARTEN:
        art = "sonstiges"
    eintrag = {
        "id": kennung,
        "eingang": _jetzt(),
        "quelle": (neu.quelle or "").strip(),
        "art": art,
        "titel": (neu.titel or "").strip(),
        "text": (neu.text or "").strip(),
        "url": (neu.url or "").strip(),
        "wichtig": bool(neu.wichtig),
        "von": (neu.von or "").strip(),
        "bis": (neu.bis or "").strip(),
        "status": "offen",
        "gesagt_am": None,
        "angeboten_am": None,
        "dauer": None,
        "stimme": None,
    }
    daten["meldungen"].append(eintrag)
    return eintrag


def aufnehmen(quelle: str = "", art: str = "sonstiges", titel: str = "", text: str = "",
              wichtig: bool = False, von: str = "", url: str = "", bis: str = "") -> dict[str, Any]:
    """Legt eine Meldung ab - ohne Schluesselpruefung, fuer andere Module im Dienst
    (z. B. die Recherche in suche.py). Der Endpunkt prueft den Schluessel selbst."""
    eintrag = Meldung(quelle=quelle, art=art, titel=titel, text=text, wichtig=wichtig,
                      von=von, url=url, bis=bis)
    if not eintrag.text.strip():
        raise HTTPException(status_code=400, detail="Meldung ohne Text.")
    with SPERRE:
        daten = _laden()
        aufgenommen = _aufnehmen(eintrag, daten)
        _speichern(daten)
    return aufgenommen


def offene_zahl() -> int:
    """Wie viele Meldungen offen sind."""
    with SPERRE:
        daten = _laden()
    return sum(1 for m in daten["meldungen"] if m.get("status") == "offen")


@router.post("/meldungen/neu")
def meldungen_neu(koerper: dict[str, Any],
                  x_meldung_schluessel: str | None = Header(default=None)) -> dict[str, Any]:
    """Nimmt eine Meldung auf - einzeln oder als Liste unter "meldungen"."""
    _pruefen(x_meldung_schluessel)
    roh = koerper.get("meldungen") if isinstance(koerper, dict) else None
    if roh is None:
        liste = [Meldung(**{k: v for k, v in (koerper or {}).items() if k in Meldung.model_fields})]
    else:
        if not isinstance(roh, list):
            raise HTTPException(status_code=400, detail='"meldungen" muss eine Liste sein.')
        liste = [Meldung(**{k: v for k, v in (e or {}).items() if k in Meldung.model_fields})
                 for e in roh]
    if not liste:
        raise HTTPException(status_code=400, detail="Keine Meldung uebergeben.")
    ohne_text = [i for i, m in enumerate(liste) if not m.text.strip()]
    if ohne_text:
        raise HTTPException(status_code=400, detail=f"Meldung ohne Text: {ohne_text}")

    with SPERRE:
        daten = _laden()
        aufgenommen = [_aufnehmen(m, daten) for m in liste]
        _speichern(daten)
        offen = sum(1 for m in daten["meldungen"] if m.get("status") == "offen")
    return {
        "ok": True,
        "aufgenommen": [{"id": m["id"], "art": m["art"], "titel": m["titel"],
                         "anfang": m["text"][:80]} for m in aufgenommen],
        "offen": offen,
    }


@router.get("/meldungen/offen")
def meldungen_offen(anzahl: int = 5, art: str = "", nur_neue: int = 0,
                    x_meldung_schluessel: str | None = Header(default=None)) -> dict[str, Any]:
    """Offene Meldungen - wichtige zuerst, dann die neuesten.

    `nur_neue=1` laesst die weg, die dem Betreiber schon angeboten wurden (der
    Zeitplan im Bot fragt damit regelmaessig und wiederholt sich nicht).
    """
    _pruefen(x_meldung_schluessel)
    with SPERRE:
        daten = _laden()
    offen = [m for m in daten["meldungen"] if m.get("status") == "offen"]
    if nur_neue:
        offen = [m for m in offen if not m.get("angeboten_am")]
    if art:
        offen = [m for m in offen if m.get("art") == art]
    offen.sort(key=_reihenfolge)
    return {"ok": True, "offen": len(offen),
            "meldungen": [{**m, "vorschau": moderationstext(m)[:200]} for m in
                          offen[:max(1, min(anzahl, 50))]]}


@router.get("/meldungen/alle")
def meldungen_alle(anzahl: int = 20, status: str = "",
                   x_meldung_schluessel: str | None = Header(default=None)) -> dict[str, Any]:
    """Alle Meldungen (auch gesagte und verworfene) - fuer die Kontrolle."""
    _pruefen(x_meldung_schluessel)
    with SPERRE:
        daten = _laden()
    alle = list(daten["meldungen"])
    if status:
        alle = [m for m in alle if m.get("status") == status]
    alle.sort(key=lambda m: str(m.get("eingang") or ""), reverse=True)
    return {"gesamt": len(daten["meldungen"]), "meldungen": alle[:max(1, min(anzahl, 200))]}


@router.get("/meldungen/text/{kennung}")
def meldungen_text(kennung: str,
                   x_meldung_schluessel: str | None = Header(default=None)) -> dict[str, Any]:
    """Zeigt, was der Moderator sprechen wuerde - ohne zu senden."""
    _pruefen(x_meldung_schluessel)
    with SPERRE:
        daten = _laden()
        meldung = _meldung(daten, kennung)
    if meldung is None:
        raise HTTPException(status_code=404, detail=f"Meldung {kennung} gibt es nicht.")
    text = moderationstext(meldung)
    return {"id": meldung["id"], "art": meldung["art"], "titel": meldung["titel"],
            "status": meldung["status"], "sprechtext": text,
            "zeichen": len(text), "woerter": len(text.split())}


@router.post("/meldungen/angeboten")
def meldungen_angeboten(koerper: Angeboten,
                        x_meldung_schluessel: str | None = Header(default=None)) -> dict[str, Any]:
    """Merkt, dass diese Meldungen dem Betreiber schon gezeigt wurden."""
    _pruefen(x_meldung_schluessel)
    gemerkt: list[str] = []
    with SPERRE:
        daten = _laden()
        for kennung in koerper.ids:
            meldung = _meldung(daten, kennung)
            if meldung is None or meldung.get("angeboten_am"):
                continue
            meldung["angeboten_am"] = _jetzt()
            gemerkt.append(str(meldung["id"]))
        _speichern(daten)
    return {"ok": True, "angeboten": gemerkt}


@router.post("/meldungen/erledigt")
def meldungen_erledigt(koerper: Erledigt,
                       x_meldung_schluessel: str | None = Header(default=None)) -> dict[str, Any]:
    """Markiert Meldungen als gesagt, verworfen oder abgelaufen."""
    _pruefen(x_meldung_schluessel)
    geaendert: list[str] = []
    titel: list[str] = []
    with SPERRE:
        daten = _laden()
        for kennung in koerper.ids:
            meldung = _meldung(daten, kennung)
            if meldung is None:
                continue
            meldung["status"] = koerper.grund
            if koerper.grund == "gesagt" and not meldung.get("gesagt_am"):
                meldung["gesagt_am"] = _jetzt()
            geaendert.append(str(meldung["id"]))
            titel.append(str(meldung.get("titel") or meldung["id"]))
        _speichern(daten)
        offen = sum(1 for m in daten["meldungen"] if m.get("status") == "offen")
    if not geaendert:
        return {"ok": False, "geaendert": [], "offen": offen,
                "antwort": "Diese Meldung kenne ich nicht mehr.",
                "bearbeiten": True, "tastatur": {"inline_keyboard": []}}
    bild = {"gesagt": "Als gesagt vermerkt", "verworfen": "Verworfen",
            "abgelaufen": "Abgelaufen"}[koerper.grund]
    return {"ok": True, "geaendert": geaendert, "offen": offen,
            "antwort": f"{bild}: {', '.join(titel)}"[:300],
            "bearbeiten": True, "tastatur": {"inline_keyboard": []}}


@router.post("/meldungen/aufraeumen")
def meldungen_aufraeumen(tage: int = 7,
                         x_meldung_schluessel: str | None = Header(default=None)) -> dict[str, Any]:
    """Entfernt erledigte Meldungen, die aelter als <tage> sind."""
    _pruefen(x_meldung_schluessel)
    grenze = time.time() - max(0, tage) * 86400
    with SPERRE:
        daten = _laden()
        vorher = len(daten["meldungen"])
        behalten = []
        for m in daten["meldungen"]:
            if m.get("status") == "offen":
                behalten.append(m)
                continue
            try:
                zeit = datetime.fromisoformat(str(m.get("eingang"))).timestamp()
            except ValueError:
                zeit = time.time()
            if zeit >= grenze:
                behalten.append(m)
        daten["meldungen"] = behalten
        _speichern(daten)
    return {"ok": True, "entfernt": vorher - len(behalten), "verbleibend": len(behalten)}


# ------------------------------------------------------------------- Ansagen

def _live_funktion():
    """Die Live-Funktion aus main.py - spaet geholt, sonst gibt es einen Kreis."""
    try:
        from main import live as live_funktion  # type: ignore  # noqa: PLC0415

        return live_funktion
    except Exception as fehler:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"Live-Weg nicht verfuegbar (main.live): {fehler}",
        ) from fehler


def _ansage_bauen(text: str, stimme: str, speed: float) -> dict[str, Any]:
    """Ruft /live auf - ohne zu senden, wenn trocken. Gibt das Ergebnis zurueck."""
    live_funktion = _live_funktion()
    from main import LiveAnfrage  # type: ignore  # noqa: PLC0415

    host = os.environ.get("LIVE_HOST", "")
    if not host or not os.environ.get("LIVE_USER") or not os.environ.get("LIVE_PASSWORD"):
        raise HTTPException(
            status_code=503,
            detail="Der DJ-Zugang fehlt: LIVE_HOST, LIVE_USER und LIVE_PASSWORD setzen "
                   "(geheim.env des Dienstes).",
        )
    anfrage = LiveAnfrage(text=text, voice=stimme, speed=speed, host=host)
    if os.environ.get("LIVE_TROCKEN", "0") == "1":
        anfrage = LiveAnfrage(text=text, voice=stimme, speed=speed, host="", user="", password="")
    return live_funktion(anfrage)


def _trocken_text(text: str, stimme: str, speed: float) -> dict[str, Any]:
    """Erzeugt nur das Audio und nennt Laenge und Groesse."""
    from main import erzeuge_audio_gewaehlt  # type: ignore  # noqa: PLC0415

    with SPERRE:
        wav, _, gewaehlt = erzeuge_audio_gewaehlt(text, stimme, speed, "wav")
    try:
        with wave.open(io.BytesIO(wav), "rb") as w:
            dauer = round(w.getnframes() / float(w.getframerate() or 1), 1)
    except Exception:  # noqa: BLE001 - lieber eine Schaetzung als ein Fehler
        dauer = round(len(wav) / 44100.0, 1)
    return {"ok": True, "trocken": True, "gesprochen": text, "stimme": gewaehlt,
            "dauer_sekunden": dauer, "wav_bytes": len(wav)}


def _ansage_merken(daten: dict[str, Any], eintrag: dict[str, Any]) -> None:
    daten["ansagen"].append(eintrag)


def ansage_machen(kennung: str, trocken: bool = False, stimme: str = "",
                 speed: float = 1.0) -> dict[str, Any]:
    """Spricht eine abgelegte Meldung (oder erzeugt sie trocken).

    Ohne Schluesselpruefung - fuer andere Module im Dienst (suche.py). Der
    Endpunkt /ansage/meldung prueft den Schluessel davor.
    """
    return _ansage_meldung_arbeit(AnsageMeldung(id=kennung, trocken=trocken, stimme=stimme,
                                               speed=speed))


@router.post("/ansage/meldung")
def ansage_meldung(anfrage: AnsageMeldung,
                   x_meldung_schluessel: str | None = Header(default=None)) -> dict[str, Any]:
    """Spricht eine abgelegte Meldung live in den Sender (oder trocken)."""
    _pruefen(x_meldung_schluessel)
    return _ansage_meldung_arbeit(anfrage)


def _ansage_meldung_arbeit(anfrage: AnsageMeldung) -> dict[str, Any]:
    with SPERRE:
        daten = _laden()
        meldung = _meldung(daten, anfrage.id)
    if meldung is None:
        raise HTTPException(status_code=404, detail=f"Meldung {anfrage.id} gibt es nicht.")
    text = moderationstext(meldung)
    if not text:
        raise HTTPException(status_code=400, detail="Die Meldung hat keinen Text.")
    if meldung.get("status") == "gesagt" and not anfrage.trocken:
        return {"ok": False, "grund": "schon_gesagt", "id": meldung["id"],
                "gesagt_am": meldung.get("gesagt_am"),
                "antwort": f"\u201e{meldung['titel'] or meldung['id']}\u201c wurde schon gesagt."}

    if anfrage.trocken:
        ergebnis = _trocken_text(text, anfrage.stimme, anfrage.speed)
    else:
        ergebnis = _ansage_bauen(text, anfrage.stimme, anfrage.speed)

    if not anfrage.trocken:
        with SPERRE:
            daten = _laden()
            eintrag = _meldung(daten, anfrage.id)
            if eintrag is not None:
                eintrag["status"] = "gesagt"
                eintrag["gesagt_am"] = _jetzt()
                eintrag["dauer"] = ergebnis.get("dauer_sekunden")
                eintrag["stimme"] = ergebnis.get("stimme")
            _ansage_merken(daten, {
                "zeit": _jetzt(), "weg": "meldung", "id": anfrage.id,
                "art": eintrag.get("art") if eintrag else "",
                "titel": eintrag.get("titel") if eintrag else "",
                "dauer_sekunden": ergebnis.get("dauer_sekunden"),
            })
            _speichern(daten)
    dauer = ergebnis.get("dauer_sekunden")
    titel = meldung.get("titel") or meldung["id"]
    if anfrage.trocken:
        antwort = f"Trockenlauf: {dauer} s - gesprochen wuerde: {text[:200]}"
    else:
        antwort = f"Gesagt ({dauer} s): {titel}"
    return {"ok": True, "id": meldung["id"], "art": meldung.get("art"),
            "titel": titel, "gesprochen": text, "dauer_sekunden": dauer,
            "trocken": bool(anfrage.trocken), "antwort": antwort,
            "bearbeiten": True, "tastatur": {"inline_keyboard": []}}


def _vor_kurzem_gesprochen(text: str) -> bool:
    """Wurde genau dieser Text (Anfang) gerade eben schon gesprochen?"""
    grenze = text[:60]
    with SPERRE:
        daten = _laden()
    jetzt = datetime.now(timezone.utc)
    for a in reversed(daten.get("ansagen", [])):
        if a.get("weg") != "text" or a.get("titel") != grenze:
            continue
        try:
            dann = datetime.fromisoformat(str(a.get("zeit")))
        except ValueError:
            continue
        if dann.tzinfo is None:
            dann = dann.replace(tzinfo=timezone.utc)
        return (jetzt - dann).total_seconds() < ANSAGE_SPERRE_SEK
    return False


@router.post("/ansage/text")
def ansage_text(anfrage: AnsageText,
                x_meldung_schluessel: str | None = Header(default=None)) -> dict[str, Any]:
    """Spricht freien Text live in den Sender (oder trocken)."""
    _pruefen(x_meldung_schluessel)
    text = sprechbar(anfrage.text)
    if not text:
        raise HTTPException(status_code=400, detail="Kein Text uebergeben.")
    text = kuerzen(text)
    # Schleifenschutz: denselben Text nicht kurz hintereinander sprechen.
    if not anfrage.trocken and _vor_kurzem_gesprochen(text):
        return {"ok": True, "gesprochen": text, "wiederholt": False,
                "dauer_sekunden": 0,
                "antwort": "Diese Ansage lief gerade eben schon - "
                           "ich habe sie nicht wiederholt."}
    if anfrage.trocken:
        ergebnis = _trocken_text(text, anfrage.stimme, anfrage.speed)
    else:
        ergebnis = _ansage_bauen(text, anfrage.stimme, anfrage.speed)
        with SPERRE:
            daten = _laden()
            _ansage_merken(daten, {"zeit": _jetzt(), "weg": "text", "id": "",
                                   "art": "", "titel": text[:60],
                                   "dauer_sekunden": ergebnis.get("dauer_sekunden")})
            _speichern(daten)
    dauer = ergebnis.get("dauer_sekunden")
    return {"ok": True, "gesprochen": text, "dauer_sekunden": dauer,
            "trocken": bool(anfrage.trocken),
            "antwort": (f"Trockenlauf: {dauer} s" if anfrage.trocken
                        else f"Ansage gesprochen ({dauer} s): {text[:120]}")}


# ------------------------------------------------------------------- Status

@router.get("/meldungen/status")
def meldungen_status() -> dict[str, Any]:
    """Kontrolle ohne Schluessel: Zaehler und ob der Live-Weg eingerichtet ist."""
    with SPERRE:
        daten = _laden()
    offen = [m for m in daten["meldungen"] if m.get("status") == "offen"]
    return {
        "app": "meldungen",
        "gesamt": len(daten["meldungen"]),
        "offen": len(offen),
        "davon_wichtig": sum(1 for m in offen if m.get("wichtig")),
        "gesagt": sum(1 for m in daten["meldungen"] if m.get("status") == "gesagt"),
        "verworfen": sum(1 for m in daten["meldungen"] if m.get("status") == "verworfen"),
        "offene_liste": [{"id": m["id"], "art": m["art"], "titel": m["titel"],
                          "wichtig": m["wichtig"], "anfang": m["text"][:60]} for m in
                         sorted(offen, key=_reihenfolge)[:10]],
        "schluessel_gesetzt": bool(schluessel()),
        "schluessel_datei": str(SCHLUESSEL_DATEI),
        "live": {
            "host": os.environ.get("LIVE_HOST", ""),
            "port": os.environ.get("LIVE_PORT", "8005"),
            "mount": os.environ.get("LIVE_MOUNT", "/"),
            "benutzer": os.environ.get("LIVE_USER", ""),
            "passwort_gesetzt": bool(os.environ.get("LIVE_PASSWORD")),
        },
        "max_zeichen": MAX_ZEICHEN,
    }


@router.get("/ansage/status")
def ansage_status(anzahl: int = 10) -> dict[str, Any]:
    """Die letzten Ansagen und die Einstellungen des Live-Wegs."""
    with SPERRE:
        daten = _laden()
    return {
        "app": "ansagen",
        "anzahl": len(daten["ansagen"]),
        "letzte": daten["ansagen"][-max(1, min(anzahl, 50)):][::-1],
        "stimme": os.environ.get("TTS_DEFAULT_VOICE", ""),
        "live": {
            "host": os.environ.get("LIVE_HOST", ""),
            "port": os.environ.get("LIVE_PORT", "8005"),
            "mount": os.environ.get("LIVE_MOUNT", "/"),
            "benutzer": os.environ.get("LIVE_USER", ""),
            "passwort_gesetzt": bool(os.environ.get("LIVE_PASSWORD")),
            "schweigen": os.environ.get("LIVE_SCHWEIGEN", "5.5"),
        },
    }
