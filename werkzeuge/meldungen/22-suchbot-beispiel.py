#!/usr/bin/env python3
"""Beispiel fuer einen Suchbot: Wetter und Feed-Meldungen abgeben.

Zeigt genau das, was ein fremder Bot tun muss: eine Meldung an
POST /meldungen/neu schicken (Kopfzeile X-Meldung-Schluessel) und die Vorschau
des Sprechtextes lesen. Der Radio-Bot holt sie danach selbst ab und legt sie dem
Betreiber im Telegram vor.

Zwei Wege sind moeglich:
  * selbst holen und die fertige Meldung abgeben (dieses Beispiel), oder
  * den Dienst holen lassen: POST /recherche {"art": "wetter", "wort": "Marbach am Neckar"}
    (Wetter, Nachrichten, RSS, Wikipedia - ohne eigenen Abruf).

Aufruf:
    python3 22-suchbot-beispiel.py                 # Wetter- und Feedmeldung ablegen
    python3 22-suchbot-beispiel.py --wetter        # nur Wetter
    python3 22-suchbot-beispiel.py --wichtig       # als wichtige Meldung
    python3 22-suchbot-beispiel.py --aufraeumen    # eigene Proben wieder entfernen

Der Schluessel steht in <dokuordner>/NACHBAU/zugangsdaten/meldung-schluessel.txt
(auf dem Server: /daten/meldung-schluessel.txt im Dienstcontainer).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

DIENST = os.environ.get("MELDUNG_DIENST", "http://192.168.178.53:8881")
SCHLUESSEL_DATEI = Path(os.environ.get(
    "MELDUNG_SCHLUESSEL_DATEI", "<dokuordner>/NACHBAU/zugangsdaten/meldung-schluessel.txt"))


def schluessel() -> str:
    aus_umgebung = os.environ.get("MELDUNG_SCHLUESSEL", "").strip()
    if aus_umgebung:
        return aus_umgebung
    if SCHLUESSEL_DATEI.exists():
        return SCHLUESSEL_DATEI.read_text(encoding="utf-8").strip()
    raise SystemExit(f"Kein Schluessel: {SCHLUESSEL_DATEI} fehlt "
                     "(oder MELDUNG_SCHLUESSEL setzen)")


def meldung(art: str, titel: str, text: str, wichtig: bool = False,
            quelle: str = "", url: str = "") -> str:
    """Legt eine Meldung ab und gibt ihre Kennung zurueck."""
    koerper = json.dumps({"art": art, "titel": titel, "text": text, "wichtig": wichtig,
                          "quelle": quelle, "url": url, "von": "22-suchbot-beispiel.py"})
    anfrage = urllib.request.Request(
        DIENST + "/meldungen/neu", data=koerper.encode(),
        headers={"Content-Type": "application/json", "X-Meldung-Schluessel": schluessel()},
        method="POST")
    try:
        with urllib.request.urlopen(anfrage, timeout=30) as antwort:
            daten = json.loads(antwort.read().decode())
    except urllib.error.HTTPError as fehler:
        raise SystemExit(f"Abgelehnt (HTTP {fehler.code}): {fehler.read().decode()[:200]}") from fehler
    eintrag = daten["aufgenommen"][0]
    print(f"  abgelegt: {eintrag['id']}  ({art}: {titel})")
    return eintrag["id"]


def vorschau(kennung: str) -> None:
    """Zeigt, was der Moderator sprechen wuerde."""
    anfrage = urllib.request.Request(
        DIENST + f"/meldungen/text/{kennung}",
        headers={"X-Meldung-Schluessel": schluessel()})
    with urllib.request.urlopen(anfrage, timeout=30) as antwort:
        daten = json.loads(antwort.read().decode())
    print(f"  sprechen wuerde ({daten['zeichen']} Zeichen):\n    {daten['sprechtext']}")


def aufraeumen() -> None:
    """Entfernt die eigenen Probmeldungen wieder."""
    anfrage = urllib.request.Request(
        DIENST + "/meldungen/alle?anzahl=100",
        headers={"X-Meldung-Schluessel": schluessel()})
    with urllib.request.urlopen(anfrage, timeout=30) as antwort:
        alle = json.loads(antwort.read().decode())["meldungen"]
    meine = [m["id"] for m in alle if m.get("von") == "22-suchbot-beispiel.py"]
    if not meine:
        print("  nichts zu entfernen")
        return
    koerper = json.dumps({"ids": meine, "grund": "verworfen"}).encode()
    anfrage = urllib.request.Request(
        DIENST + "/meldungen/erledigt", data=koerper,
        headers={"Content-Type": "application/json", "X-Meldung-Schluessel": schluessel()},
        method="POST")
    with urllib.request.urlopen(anfrage, timeout=30) as antwort:
        print(f"  entfernt: {json.loads(antwort.read().decode())['geaendert']}")


def main() -> int:
    wichtige = "--wichtig" in sys.argv
    nur_wetter = "--wetter" in sys.argv and "--feed" not in sys.argv

    if "--aufraeumen" in sys.argv:
        print("Proben entfernen")
        aufraeumen()
        return 0

    jetzt = datetime.now().strftime("%H:%M")
    print("Suchbot-Beispiel: Meldungen an das Radio-Postfach\n")

    # --- Wetter (hier fest eingesetzt; im echten Bot aus einer Wetterabfrage)
    kennung = meldung(
        art="wetter", titel="Wetter Berlin",
        text="Um " + jetzt + " sind es in Berlin 18 Grad. Am Nachmittag ziehen Wolken auf, "
             "später ist mit Regen bei 70 % Wahrscheinlichkeit zu rechnen. "
             "Der Wind weht schwach aus Suedwest.",
        wichtig=wichtige, quelle="beispiel")
    vorschau(kennung)

    if not nur_wetter:
        # --- Feed (hier fest eingesetzt; im echten Bot aus einem RSS-Feed)
        kennung = meldung(
            art="rss", titel="Aus dem Netz",
            text="**Neue Version erschienen**: Das Projekt hat heute Version 4 "
                 "veroeffentlicht. Mehr dazu auf example.org/details.",
            wichtig=wichtige, quelle="beispiel-feed", url="https://example.org/details")
        vorschau(kennung)

    stand = json.loads(urllib.request.urlopen(DIENST + "/meldungen/status", timeout=30).read())
    print(f"\nIm Postfach offen: {stand['offen']} (davon wichtig: {stand['davon_wichtig']})")
    print("Der Radio-Bot holt sie beim naechsten Zeitplan-Lauf (alle 5 Minuten) ab und\n"
          "legt sie dem Betreiber im Telegram mit den Knoepfen Vorlesen/Verwerfen vor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
