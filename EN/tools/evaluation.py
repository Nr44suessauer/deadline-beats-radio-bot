#!/usr/bin/env python3
"""Reads an output produced with one.js and shows selected fields per node."""
import re
import sys

path = sys.argv[1]
names = sys.argv[2:] or ["Understand", "Split job", "Smart Search", "Rate hits",
                         "Collect wishes", "Search 1", "Hits 1"]
text = open(path, encoding="utf-8").read()

for name in names:
    block = None
    for teil in text.split("--- "):
        if teil.startswith(name + " [0]"):
            block = teil
            break
    if block is None:
        print(f"{name}: not in the run")
        continue
    gezeigt = 0
    for m in re.finditer(r"\[Zweig (\d+) Nr (\d+)\] (.*)", block):
        zeile = m.group(3)
        if name == "Understand":
            inhalt = re.search(r'"content":"(.*?)","done"', zeile)
            print(f"{name}: {inhalt.group(1)[:300] if inhalt else zeile[:200]}")
        else:
            felder = {}
            for feld in ("command", "argument", "genreWort", "count", "aktion", "title",
                         "artist", "text", "origin", "modus", "direction"):
                hits = re.search(r'"' + feld + r'":("[^"]*"|[0-9]+|true|false)', zeile)
                if hits:
                    wert = hits.group(1).strip('"')
                    if wert not in ("", "0", "false"):
                        felder[feld] = wert
            print(f"{name} Nr {m.group(2)}: {felder}")
        gezeigt += 1
    if gezeigt == 0:
        print(f"{name}: no output")
