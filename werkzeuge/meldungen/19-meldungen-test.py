#!/usr/bin/env python3
"""Prueft das Meldungs- und Ansagemodul.

Zwei Teile:
  1. Textaufbereitung (ohne Netz): was der Moderator sprechen wuerde - URLs,
     Emojis, Abkuerzungen, Kuerzung.
  2. Wege ueber den Dienst: Meldung abgeben, abholen, Vorschau, Ansage trocken,
     erledigen. Mit --live wird zusaetzlich eine echte Ansage in den Sender
     gesprochen (kurz, unterbricht den laufenden Titel).

Aufruf:
    python3 19-meldungen-test.py            # ohne Sendebetrieb
    python3 19-meldungen-test.py --live     # mit einer echten Ansage
"""
from __future__ import annotations

import json
import os
import sys
import types
import urllib.error
import urllib.request
from pathlib import Path

DIENST = os.environ.get("MELDUNG_DIENST", "http://192.168.178.53:8881")
SCHLUESSEL_DATEI = Path("<dokuordner>/NACHBAU/zugangsdaten/meldung-schluessel.txt")
LIVE = "--live" in sys.argv
QUELLE = Path("<dokuordner>/dienst/meldungen.py")

gut = 0
schlecht = 0


def pruefe(bedingung: bool, beschreibung: str, zusatz: str = "") -> None:
    global gut, schlecht
    if bedingung:
        gut += 1
        print(f"ok   {beschreibung}")
    else:
        schlecht += 1
        print(f"ABW. {beschreibung}" + (f"\n       {zusatz}" if zusatz else ""))


# ------------------------------------------------- Teil 1: Textaufbereitung

def lokaler_test() -> None:
    """Importiert das Modul mit Attrappen fuer FastAPI/Pydantic."""
    fastapi = types.ModuleType("fastapi")

    class _Router:
        def post(self, *_a, **_k):
            return lambda f: f

        def get(self, *_a, **_k):
            return lambda f: f

    class HTTPException(Exception):
        def __init__(self, status_code=500, detail=""):
            self.status_code, self.detail = status_code, detail

    fastapi.APIRouter = _Router
    fastapi.HTTPException = HTTPException
    fastapi.Header = lambda default=None, **_k: default
    sys.modules["fastapi"] = fastapi

    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        model_fields: dict = {}

        def __init__(self, **felder):
            for k, v in felder.items():
                setattr(self, k, v)

    pydantic.BaseModel = BaseModel
    pydantic.Field = lambda default="", **_k: default
    sys.modules["pydantic"] = pydantic

    sys.path.insert(0, str(QUELLE.parent))
    import importlib

    modul = importlib.import_module("meldungen")

    print("=== 1. Textaufbereitung fuer das Sprechen")
    faelle = [
        ("Heute 18°C, später Regen bei 70 % Wahrscheinlichkeit. Mehr auf wetter.de",
         ["Grad", "Prozent"], ["°", "%", "wetter.de"]),
        ("**Wichtig**: Der Zug fällt aus (Grund: Streik) — siehe https://bahn.de/streik",
         ["Wichtig", "Streik"], ["**", "(", ")", "https://"]),
        ("Wind bis 40 km/h, z.B. an der Küste 🌧️",
         ["Kilometer pro Stunde", "zum Beispiel"], ["km/h", "z.B.", "🌧️"]),
    ]
    for text, muss, darf_nicht in faelle:
        ergebnis = modul.sprechbar(text)
        fehlend = [m for m in muss if m not in ergebnis]
        verboten = [d for d in darf_nicht if d in ergebnis]
        pruefe(not fehlend and not verboten, f'sprechbar: "{text[:48]}..."',
               f"fehlt: {fehlend} | darf nicht: {verboten} | ist: {ergebnis}")

    # Abkuerzungen: das Muster darf nicht mit \b enden - nach einem Punkt vor
    # einem Leerzeichen gibt es keine Wortgrenze (Fehler am 2026-09-20).
    print("\n=== 1b. Abkuerzungen")
    for abk, soll in [("z.B. regnet es", "zum Beispiel"), ("z. B. regnet es", "zum Beispiel"),
                      ("bzw. morgen", "beziehungsweise"), ("ca. 20 Grad", "circa"),
                      ("u.a. Musik", "unter anderem"), ("d.h. später", "das heißt"),
                      ("Nr. 5 fährt", "Nummer"), ("ggf. später", "gegebenenfalls"),
                      ("evtl. gewitter", "eventuell")]:
        ergebnis = modul.sprechbar(abk)
        pruefe(soll in ergebnis and abk.split()[0] not in ergebnis,
               f'"{abk}" -> "{ergebnis}"')

    print("\n=== 2. Moderations-Text")
    wetter = {"art": "wetter", "titel": "Wetter Berlin", "text": "Am Nachmittag sonnig, 21 Grad."}
    t = modul.moderationstext(wetter)
    pruefe(t.startswith("Und nun der Blick zum Himmel"), f"Wetter bekommt Vorspann: {t}")
    pruefe("sunnig" not in t and "sonnig" in t, "Inhalt bleibt erhalten")

    nachricht = {"art": "nachrichten", "titel": "", "text": "Der Bundestag hat entschieden."}
    pruefe(modul.moderationstext(nachricht).startswith("Kurz die Nachrichten"),
           "Nachrichten bekommen eigenen Vorspann")

    rss = {"art": "rss", "quelle": "heise", "titel": "Neue Version", "text": "Heute erschienen."}
    txt = modul.moderationstext(rss)
    pruefe("Neue Version" in txt and txt.startswith("Frisch aus dem Netz"),
           f"RSS nennt den Titel: {txt}")

    ohne_titel = {"art": "wetter", "titel": "Wetter Berlin", "text": "Wetter Berlin: sonnig."}
    pruefe(modul.moderationstext(ohne_titel).count("Wetter Berlin") == 1,
           "Titel wird nicht doppelt vorgelesen")

    lang = {"art": "nachrichten", "text": "Satz eins ist da. " * 80}
    gekuerzt = modul.moderationstext(lang)
    pruefe(len(gekuerzt) <= modul.MAX_ZEICHEN + 40 and gekuerzt.endswith("."),
           f"Zu langer Text wird an der Satzgrenze gekuerzt ({len(gekuerzt)} Zeichen)")

    leer = modul.moderationstext({"art": "sonstiges", "text": ""})
    pruefe(leer != "", f"Leere Meldung ergibt trotzdem einen Satz: {leer!r}")


# ------------------------------------------------------ Teil 2: ueber den Dienst

def rufen(pfad: str, koerper: dict | None = None, methode: str = "GET",
          schluessel: str | None = None) -> tuple[int, dict]:
    kopf = {"Content-Type": "application/json"}
    if schluessel:
        kopf["X-Meldung-Schluessel"] = schluessel
    daten = json.dumps(koerper).encode() if koerper is not None else None
    anfrage = urllib.request.Request(DIENST + pfad, data=daten, headers=kopf, method=methode)
    try:
        with urllib.request.urlopen(anfrage, timeout=300) as antwort:
            return antwort.status, json.loads(antwort.read().decode() or "{}")
    except urllib.error.HTTPError as fehler:
        roh = fehler.read().decode()
        try:
            return fehler.code, json.loads(roh)
        except json.JSONDecodeError:
            return fehler.code, {"roh": roh[:200]}


def dienst_test() -> None:
    if not SCHLUESSEL_DATEI.exists():
        print(f"\nKein Schluessel ({SCHLUESSEL_DATEI}) - Dienst-Teil uebersprungen.")
        return
    schluessel = SCHLUESSEL_DATEI.read_text(encoding="utf-8").strip()

    print("\n=== 3. Postfach (Suchbot -> Dienst)")
    code, _ = rufen("/meldungen/status")
    pruefe(code == 200, f"/meldungen/status ohne Schluessel lesbar (HTTP {code})")

    code, _ = rufen("/meldungen/neu", {"text": "Test ohne Schluessel"}, "POST")
    pruefe(code == 403, f"Abgeben ohne Schluessel wird abgelehnt (HTTP {code})")

    code, d = rufen("/meldungen/neu", {
        "quelle": "testskript", "art": "wetter", "titel": "Wetterprobe",
        "text": "In Berlin heute 18°C und später Regen bei 70 % Wahrscheinlichkeit. "
                "Details auf wetter.de", "wichtig": False, "von": "19-meldungen-test.py",
    }, "POST", schluessel)
    pruefe(code == 200 and d.get("aufgenommen"), f"Meldung aufgenommen (HTTP {code}): {d.get('aufgenommen')}")
    kennung = d["aufgenommen"][0]["id"]

    code, d = rufen("/meldungen/offen?anzahl=5", schluessel=schluessel)
    pruefe(code == 200 and any(m["id"] == kennung for m in d.get("meldungen", [])),
           f"Meldung liegt im Postfach (offen: {d.get('offen')})")

    code, d = rufen("/meldungen/angeboten", {"ids": [kennung]}, "POST", schluessel)
    pruefe(code == 200 and kennung in d.get("angeboten", []), f"Als angeboten gemerkt: {d.get('angeboten')}")
    code, d = rufen("/meldungen/offen?nur_neue=1", schluessel=schluessel)
    pruefe(all(m["id"] != kennung for m in d.get("meldungen", [])),
           "nur_neue=1 laesst Angebotenes weg (kein zweites Angebot)")
    code, d = rufen("/meldungen/angeboten", {"ids": [kennung]}, "POST", schluessel)
    pruefe(d.get("angeboten") == [], "Zweites Merken ist wirkungslos")

    code, d = rufen(f"/meldungen/text/{kennung}", schluessel=schluessel)
    text = d.get("sprechtext", "")
    pruefe(code == 200 and "Grad" in text and "Prozent" in text and "wetter.de" not in text,
           f"Vorschau des Sprechtextes: {text}")
    pruefe(d.get("woerter", 0) > 5, f"Woerter gezaehlt: {d.get('woerter')}")

    print("\n=== 3b. Recherche (trocken)")
    code, d = rufen("/recherche/feeds")
    pruefe(code == 200 and "wetter" in d.get("arten", []),
           f"Die Recherche nennt ihre Arten: {d.get('arten')}")

    recherchiert: list[str] = []
    for auftrag, muss in [({"art": "wetter", "wort": "Marbach am Neckar"}, "Grad"),
                          ({"art": "nachrichten"}, ""),
                          ({"art": "wikipedia", "wort": "Marbach am Neckar"}, "")]:
        code, d = rufen("/recherche", {**auftrag, "ansagen": False}, "POST", schluessel)
        ok = code == 200 and d.get("id") and len(str(d.get("text", ""))) > 40
        pruefe(ok, f"Recherche {auftrag['art']} {auftrag.get('wort', '')}: "
                   f"{str(d.get('titel', ''))[:60]} ({len(str(d.get('text', '')))} Zeichen, HTTP {code})")
        if d.get("id"):
            recherchiert.append(d["id"])
        if muss:
            pruefe(muss in str(d.get("text", "")), f"Text nennt '{muss}'")

    code, d = rufen("/recherche", {"art": "wetter", "wort": "Marbach am Neckar"}, "POST", schluessel)
    pruefe(code == 200 and d.get("dauer_sekunden", 0) > 3,
           f"Wetter mit Ansage (trockengestellt): {d.get('dauer_sekunden')} s, gesagt={d.get('gesagt')}")
    if d.get("id"):
        recherchiert.append(d["id"])

    code, d = rufen("/recherche", {"art": "wetter", "wort": "Xyzzyxquatschort", "ansagen": False},
                    "POST", schluessel)
    pruefe(code == 404, f"Unbekannter Ort wird abgelehnt (HTTP {code})")
    code, d = rufen("/recherche", {"art": "quatsch", "ansagen": False}, "POST", schluessel)
    pruefe(code in (400, 422), f"Unbekannte Art wird abgelehnt (HTTP {code})")

    if recherchiert:
        rufen("/meldungen/erledigt", {"ids": recherchiert, "grund": "verworfen"}, "POST", schluessel)
        print(f"       (Probmeldungen verworfen: {recherchiert})")

    print("\n=== 4. Ansage (trocken)")
    code, d = rufen("/ansage/meldung", {"id": kennung, "trocken": True}, "POST", schluessel)
    pruefe(code == 200 and d.get("dauer_sekunden", 0) > 2,
           f"Audio erzeugt, Laenge {d.get('dauer_sekunden')} s (HTTP {code})")
    pruefe("Grad" in d.get("gesprochen", ""), "Sprechtext wird mitgeliefert")
    pruefe("Trockenlauf" in d.get("antwort", ""), f"Antwort nennt den Trockenlauf: {d.get('antwort', '')[:80]}")

    code, d = rufen("/ansage/text", {"text": "Probe der freien Ansage.", "trocken": True},
                    "POST", schluessel)
    pruefe(code == 200 and d.get("dauer_sekunden", 0) > 0,
           f"Freie Ansage trocken: {d.get('dauer_sekunden')} s")

    if LIVE:
        print("\n=== 5. Ansage live in den Sender (Sendebetrieb wird kurz unterbrochen)")
        kurz = {"art": "hinweis", "titel": "Ansageprobe",
                "text": "Dies ist eine kurze Probe der Moderationsansage. "
                        "Wenn du das hoerst, funktioniert die neue Schnittstelle."}
        code, d = rufen("/meldungen/neu", kurz, "POST", schluessel)
        kennung_live = d["aufgenommen"][0]["id"]
        code, d = rufen("/ansage/meldung", {"id": kennung_live}, "POST", schluessel)
        pruefe(code == 200 and d.get("dauer_sekunden", 0) > 3,
               f"Ansage gesprochen: {d.get('dauer_sekunden')} s, Hafen {d.get('antwort')}"
               if isinstance(d, dict) else f"Antwort: {d}")
        if code == 200:
            print(f"       gesprochen: {d.get('gesprochen', '')[:160]}")
        code, d = rufen("/ansage/meldung", {"id": kennung_live}, "POST", schluessel)
        pruefe(d.get("grund") == "schon_gesagt", "Zweite Ansage derselben Meldung wird abgelehnt")
        rufen("/meldungen/erledigt", {"ids": [kennung_live], "grund": "verworfen"},
              "POST", schluessel)
        print("       (Probemeldung wieder verworfen)")
    else:
        print("\n=== 5. Echte Ansage uebersprungen (ohne --live)")

    print("\n=== 6. Abschluss")
    code, d = rufen("/meldungen/erledigt", {"ids": [kennung], "grund": "verworfen"},
                    "POST", schluessel)
    pruefe(code == 200 and kennung in d.get("geaendert", []), f"Meldung verworfen: {d.get('geaendert')}")
    pruefe(d.get("antwort") and d.get("bearbeiten") is True,
           f"Antwort fuer Telegram dabei: {d.get('antwort', '')[:80]}")

    code, d = rufen("/meldungen/aufraeumen?tage=0", schluessel=schluessel, methode="POST")
    pruefe(code == 200, f"Aufraeumen ok (entfernt: {d.get('entfernt')}, bleibt: {d.get('verbleibend')})")

    code, d = rufen("/meldungen/offen", schluessel=schluessel)
    pruefe(d.get("offen") == 0, f"Postfach ist wieder leer (offen: {d.get('offen')})")

    code, d = rufen("/ansage/status?anzahl=3")
    pruefe(code == 200 and d.get("live", {}).get("passwort_gesetzt"),
           f"Live-Zugang eingerichtet: {d.get('live')}")


if __name__ == "__main__":
    print("=" * 78)
    print("Meldungen und Ansagen - Prueflauf" + (" (mit echter Ansage)" if LIVE else ""))
    print("=" * 78 + "\n")
    lokaler_test()
    dienst_test()
    print(f"\nErgebnis: {gut} ok, {schlecht} abweichend")
    sys.exit(0 if schlecht == 0 else 1)
