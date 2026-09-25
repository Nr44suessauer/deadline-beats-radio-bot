#!/usr/bin/env python3
"""Prueft die Listen-Aufgaben von Ende zu Ende ueber den Testeingang des Bots.

Der Test geht durch den echten Arbeitsablauf (n8n) und schickt echte Nachrichten
an den Betreiberchat. Die Antwort des letzten Knotens ist die Antwort von
Telegram - daraus wird geprueft, was der Bot geantwortet hat.

Ablauf: Listen anzeigen, Playlist bauen (Menue, Titel antippen, Fertig),
Abbrechen, ansehen, loeschen. Am Ende bleibt nur "List A" uebrig.

Aufruf:  python3 15-bot-listen-test.py [--spielen]
         --spielen  fuehrt zusaetzlich "bauen und gleich abspielen" aus
                    (unterbricht den Sendebetrieb kurz!)
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Der Testeingang ist von der Arbeitsstation erreichbar; im LXC 103 ist es
# 127.0.0.1:5678 - darum ueber die Umgebung einstellbar.
WEBHOOK = os.environ.get("BOT_WEBHOOK", "http://192.168.178.53:5678/webhook/DEIN-WEBHOOK-PFAD")
SCHLUESSEL = Path("<dokuordner>/NACHBAU/zugangsdaten/bot-test-schluessel.txt").read_text().strip()
CHAT = "DEINE-CHAT-ID"
PROBE = "Probe Copilot"
SPIELEN = "--spielen" in sys.argv

if not SCHLUESSEL:
    raise SystemExit("Testschluessel fehlt (bot-test-schluessel.txt)")

letzte_nachricht = {"id": None}


def rufen(rumpf: dict, dauer: int = 120) -> dict:
    ziel = f"{WEBHOOK}?schluessel={SCHLUESSEL}"
    daten = json.dumps(rumpf).encode()
    anfrage = urllib.request.Request(ziel, data=daten, headers={"Content-Type": "application/json"},
                                     method="POST")
    with urllib.request.urlopen(anfrage, timeout=dauer) as antwort:
        roh = antwort.read().decode()
    try:
        return json.loads(roh)
    except json.JSONDecodeError:
        return {"roh": roh}


def text(rumpf: dict, beschreibung: str) -> str:
    """Nachricht senden und die Antwort des Bots zeigen."""
    start = time.time()
    ergebnis = rufen({"message": {"message_id": 1, "chat": {"id": int(CHAT), "type": "private"},
                                  "from": {"id": int(CHAT), "first_name": "Test"}, "text": rumpf}})
    return zeigen(ergebnis, beschreibung, start)


def knopf(daten: str, beschreibung: str) -> str:
    """Knopfdruck nachstellen - mit der echten Nachrichtenkennung, damit das
    Menue bearbeitet statt neu gesendet wird."""
    if not letzte_nachricht["id"]:
        raise SystemExit("Keine Nachrichtenkennung - erst einen Text senden")
    start = time.time()
    ergebnis = rufen({"callback_query": {
        "id": "1", "from": {"id": int(CHAT), "first_name": "Test"},
        "data": daten,
        "message": {"message_id": letzte_nachricht["id"],
                    "chat": {"id": int(CHAT), "type": "private"}}}})
    return zeigen(ergebnis, beschreibung, start)


def zeigen(ergebnis: dict, beschreibung: str, start: float) -> str:
    sekunden = time.time() - start
    inhalt = ergebnis.get("result") if isinstance(ergebnis.get("result"), dict) else None
    if inhalt and inhalt.get("message_id"):
        letzte_nachricht["id"] = inhalt["message_id"]
    meldung = ""
    if inhalt:
        meldung = inhalt.get("text") or inhalt.get("caption") or ""
    elif ergebnis.get("message"):
        meldung = f"FEHLER: {ergebnis.get('message')}"
    elif ergebnis.get("roh"):
        meldung = ergebnis["roh"][:400]
    print(f"── {beschreibung}   ({sekunden:.1f}s)")
    for zeile in str(meldung).splitlines():
        print("     " + zeile[:120])
    knoepfe = ((inhalt or {}).get("reply_markup") or {}).get("inline_keyboard") or []
    if knoepfe:
        print("     Knoepfe: " + " | ".join(k["text"][:34] for zeile in knoepfe for k in zeile)[:300])
    print()
    return str(meldung)


print("=" * 78)
print("Listen-Aufgaben im Bot (Testeingang, echter Betreiberchat)")
print("=" * 78 + "\n")

text("welche Wiedergabelisten gibt es", "1) Listen anzeigen")
text(f"baue eine Playlist {PROBE} aus Scooter", "2) Playlist bauen -> Auswahlmenue")
knopf("p1", "3) Titel 1 antippen")
knopf("p2", "4) Titel 2 antippen")
knopf("pf", "5) Fertig -> Liste anlegen")
knopf("px", "6) Genug (nichts abspielen)")
text(f"was ist in der Playlist {PROBE}", "7) Inhalt ansehen")
text(f"loesche die Playlist {PROBE}", "8) Listen loeschen (Rueckfrage)")
knopf("j", "9) Ja, loeschen")
text("entferne Hyper Hyper aus der Playlist List A", "10) einzelner Titel (noch nicht moeglich)")
text("mach irgendwas mit dem Sender", "11) unbekannter Auftrag (laeuft wie bisher)")

if SPIELEN:
    text(f"baue eine playlist {PROBE} Sofort aus Scooter und spiele sie",
         "12) bauen und gleich abspielen -> Auswahlmenue")
    knopf("p1", "13) Titel 1 antippen")
    knopf("pf", "14) Fertig -> anlegen UND abspielen (Sendebetrieb wird kurz unterbrochen)")
    text(f"loesche die Playlist {PROBE} Sofort", "15) Probe wieder loeschen")
    knopf("j", "16) Ja, loeschen")

print("Fertig.")
