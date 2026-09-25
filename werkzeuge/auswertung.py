#!/usr/bin/env python3
"""Liest eine mit eine.js erzeugte Ausgabe und zeigt ausgewaehlte Felder je Knoten."""
import re
import sys

pfad = sys.argv[1]
namen = sys.argv[2:] or ["Verstehen", "Auftrag aufteilen", "Kluge Suche", "Bewerten",
                         "Wunsch sammeln", "Suche 1", "Treffer 1"]
text = open(pfad, encoding="utf-8").read()

for name in namen:
    block = None
    for teil in text.split("--- "):
        if teil.startswith(name + " [0]"):
            block = teil
            break
    if block is None:
        print(f"{name}: nicht im Lauf")
        continue
    gezeigt = 0
    for m in re.finditer(r"\[Zweig (\d+) Nr (\d+)\] (.*)", block):
        zeile = m.group(3)
        if name == "Verstehen":
            inhalt = re.search(r'"content":"(.*?)","done"', zeile)
            print(f"{name}: {inhalt.group(1)[:300] if inhalt else zeile[:200]}")
        else:
            felder = {}
            for feld in ("befehl", "argument", "genreWort", "anzahl", "aktion", "titel",
                         "artist", "text", "herkunft", "modus", "richtung"):
                treffer = re.search(r'"' + feld + r'":("[^"]*"|[0-9]+|true|false)', zeile)
                if treffer:
                    wert = treffer.group(1).strip('"')
                    if wert not in ("", "0", "false"):
                        felder[feld] = wert
            print(f"{name} Nr {m.group(2)}: {felder}")
        gezeigt += 1
    if gezeigt == 0:
        print(f"{name}: keine Ausgabe")
