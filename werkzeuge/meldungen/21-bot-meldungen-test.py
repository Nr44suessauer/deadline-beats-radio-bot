#!/usr/bin/env python3
"""Prueft die Meldungswege von Ende zu Ende ueber den Bot (echter Betreiberchat).

Ablauf:
  1. Der Suchbot legt Meldungen ab (hier nachgestellt: POST an den Dienst).
  2. Die Knoepfe der Meldungs-Karte werden nachgestellt (Vorlesen / Verwerfen) -
     "Vorlesen" spricht wirklich in den Sender (kurzer Text!).
  3. Die Freigabe im Telegram wird geprueft (Antwort des letzten Knotens).
  4. Der Zeitplan (alle 5 Minuten) wird geprueft: er merkt die Meldung als
     angeboten - hier wird darauf gewartet.

Aufruf:
    python3 21-bot-meldungen-test.py            # ohne Ansage (Knoepfe nur verwerfen)
    python3 21-bot-meldungen-test.py --live     # mit echter Ansage
    python3 21-bot-meldungen-test.py --warten   # zusaetzlich auf den Zeitplan warten
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

DIENST = os.environ.get("MELDUNG_DIENST", "http://192.168.178.53:8881")
BOT = os.environ.get("BOT_WEBHOOK", "http://192.168.178.53:5678/webhook/DEIN-WEBHOOK-PFAD")
RADIO = Path("<dokuordner>")
SCHLUESSEL = (RADIO / "NACHBAU/zugangsdaten/meldung-schluessel.txt").read_text(encoding="utf-8").strip()
TESTSCHLUESSEL = (RADIO / "NACHBAU/zugangsdaten/bot-test-schluessel.txt").read_text(encoding="utf-8").strip()
CHAT = "DEINE-CHAT-ID"
LIVE = "--live" in sys.argv
WARTEN = "--warten" in sys.argv

gut = schlecht = 0
letzte_nachricht = {"id": None}


def pruefe(bedingung: bool, beschreibung: str, zusatz: str = "") -> None:
    global gut, schlecht
    if bedingung:
        gut += 1
        print(f"ok   {beschreibung}")
    else:
        schlecht += 1
        print(f"ABW. {beschreibung}" + (f"\n       {zusatz}" if zusatz else ""))


def dienst(pfad: str, koerper: dict | None = None, methode: str = "GET") -> tuple[int, dict]:
    kopf = {"X-Meldung-Schluessel": SCHLUESSEL, "Content-Type": "application/json"}
    daten = json.dumps(koerper).encode() if koerper is not None else None
    anfrage = urllib.request.Request(DIENST + pfad, data=daten, headers=kopf, method=methode)
    with urllib.request.urlopen(anfrage, timeout=300) as antwort:
        return antwort.status, json.loads(antwort.read().decode() or "{}")


def bot(rumpf: dict, dauer: int = 300) -> dict:
    ziel = f"{BOT}?schluessel={TESTSCHLUESSEL}"
    anfrage = urllib.request.Request(ziel, data=json.dumps(rumpf).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(anfrage, timeout=dauer) as antwort:
        return json.loads(antwort.read().decode() or "{}")


def zeige(ergebnis: dict, beschreibung: str, start: float) -> str:
    inhalt = ergebnis.get("result") if isinstance(ergebnis.get("result"), dict) else None
    if inhalt and inhalt.get("message_id"):
        letzte_nachricht["id"] = inhalt["message_id"]
    meldung = (inhalt or {}).get("text") or ergebnis.get("message") or str(ergebnis)[:200]
    print(f"── {beschreibung}   ({time.time() - start:.1f}s)")
    for zeile in str(meldung).splitlines():
        print("     " + zeile[:120])
    return str(meldung)


def knopf(daten: str, beschreibung: str) -> str:
    start = time.time()
    ergebnis = bot({"callback_query": {
        "id": "1", "from": {"id": int(CHAT), "first_name": "Test"}, "data": daten,
        "message": {"message_id": letzte_nachricht["id"] or 1,
                    "chat": {"id": int(CHAT), "type": "private"}}}})
    return zeige(ergebnis, beschreibung, start)


def text(nachricht: str, beschreibung: str) -> str:
    start = time.time()
    ergebnis = bot({"message": {"message_id": 1, "chat": {"id": int(CHAT), "type": "private"},
                                "from": {"id": int(CHAT), "first_name": "Test"}, "text": nachricht}})
    return zeige(ergebnis, beschreibung, start)


def neu(art: str, titel: str, inhalt: str, wichtig: bool = False) -> str:
    _, d = dienst("/meldungen/neu", {"quelle": "suchbot-probe", "art": art, "titel": titel,
                                    "text": inhalt, "wichtig": wichtig, "von": "21-bot-meldungen-test.py"},
                  "POST")
    return d["aufgenommen"][0]["id"]


print("=" * 78)
print("Meldungen im Bot" + (" (mit echter Ansage)" if LIVE else "") + (", warte auf den Zeitplan" if WARTEN else ""))
print("=" * 78 + "\n")

# ------------------------------------------------------------------ 1. Knoepfe
print("=== 1. Meldung anbieten und verwerfen")
kennung_weg = neu("rss", "Feedprobe", "Eine kurze Probenachricht aus einem RSS-Feed zum Verwerfen.")
antwort = knopf(f"x{kennung_weg}", "Knopf: Verwerfen")
pruefe("Verworfen" in antwort or "verworfen" in antwort, "Der Bot meldet den Verwurf")

_, stand = dienst("/meldungen/status")
pruefe(stand["verworfen"] >= 1, f"Meldung ist im Dienst als verworfen vermerkt (verworfen: {stand['verworfen']})")

if LIVE:
    print("\n=== 2. Meldung vorlesen lassen (Sendebetrieb wird kurz unterbrochen)")
    kennung_live = neu("wetter", "Wetterprobe",
                       "In Berlin heute 19 Grad und zeitweise Sonne. Es bleibt trocken.",
                       wichtig=True)
    antwort = knopf(f"m{kennung_live}", "Knopf: Vorlesen")
    pruefe("Gesagt" in antwort or "gesagt" in antwort, "Der Bot meldet die Ansage",
           f"Antwort: {antwort[:160]}")
    _, d = dienst(f"/meldungen/text/{kennung_live}")
    pruefe(d.get("status") == "gesagt", f"Meldung steht auf gesagt (status: {d.get('status')})")
else:
    print("\n=== 2. Vorlesen uebersprungen (ohne --live)")
    kennung_live = None

# ------------------------------------------------------------------ 3. Werkzeug
print("\n=== 3. Der Agent fragt das Postfach ab (ueber das Werkzeug)")
kennung_frage = neu("nachrichten", "Nachrichtenprobe",
                    "Der Gemeinderat hat den Haushalt verabschiedet. Mehr dazu spaeter.")
antwort = text("was gibt es fuer Meldungen", "Frage: was gibt es fuer Meldungen")
pruefe("Nachrichtenprobe" in antwort or "nachrichten" in antwort.lower() or "1." in antwort,
       "Die Antwort nennt die offene Meldung", f"Antwort: {antwort[:200]}")

# ------------------------------------------------------------------ 4. Zeitplan
print("\n=== 4. Zeitplan legt neue Meldungen vor")
kennung_karte = neu("verkehr", "Verkehrsprobe",
                    "Auf der A100 stockt der Verkehr nach einem Unfall auf dem rechten Fahrstreifen.",
                    wichtig=True)
_, d = dienst(f"/meldungen/text/{kennung_karte}")
if not WARTEN:
    print("       (ohne --warten wird nicht auf den Zeitplan gewartet)")
    print(f"       offene Meldung: {kennung_karte}")
else:
    print(f"       warte auf den Zeitplan (alle 5 Minuten), Meldung {kennung_karte} ...")
    angeboten = False
    for _ in range(40):
        zeit, liste = dienst("/meldungen/alle?anzahl=50")
        eintrag = [m for m in liste["meldungen"] if m["id"] == kennung_karte]
        if eintrag and eintrag[0].get("angeboten_am"):
            angeboten = True
            break
        time.sleep(20)
    pruefe(angeboten, "Der Zeitplan hat die Meldung als angeboten gemerkt")
    if angeboten:
        print("       -> die Karte steht im Telegram (zwei Knoepfe: Vorlesen / Verwerfen)")

# ------------------------------------------------------------------ 5. Aufraeumen
print("\n=== 5. Aufraeumen")
ids = [k for k in (kennung_weg, kennung_live, kennung_frage, kennung_karte) if k]
_, d = dienst("/meldungen/erledigt", {"ids": ids, "grund": "verworfen"}, "POST")
pruefe(set(ids) <= set(d.get("geaendert", [])), f"Alle Probemeldungen verworfen: {d.get('geaendert')}")
_, d = dienst("/meldungen/aufraeumen?tage=0", {}, "POST")
pruefe(isinstance(d.get("verbleibend"), int), f"Aufgeraeumt (bleibt: {d.get('verbleibend')})")
_, stand = dienst("/meldungen/status")
pruefe(stand["offen"] == 0, f"Postfach wieder leer (offen: {stand['offen']})")

print(f"\nErgebnis: {gut} ok, {schlecht} abweichend")
sys.exit(0 if schlecht == 0 else 1)
