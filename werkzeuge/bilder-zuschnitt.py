#!/usr/bin/env python3
"""Schneidet den leeren Rand aus den Aufnahmen der Dokumentation.

Warum: die Bilder entstehen in der laufenden Oberflaeche (873 x 486 Punkte). Damit
in der Anleitung die Beschriftungen gross genug sind, wird der unbeschriebene Rand
weggeschnitten - der Ausschnitt wird dadurch relativ groesser, wenn ihn die Anleitung
auf Spaltenbreite zieht.

Aufruf:  python3 bilder-zuschnitt.py <quelle-verzeichnis> [<ziel-verzeichnis>]
Ohne Ziel wird an Ort und Stelle ersetzt (Originale bleiben als *.orig.png).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageChops

RAND = 10          # Punkte, die als Rand stehen bleiben
TOLERANZ = 12      # Farbabweichung, ab der ein Punkt als "Inhalt" gilt


def zuschneiden(pfad: Path, ziel: Path) -> tuple[int, int]:
    bild = Image.open(pfad).convert("RGB")
    # Die Flaeche ist gleichmaessig dunkel; als Vergleich dient die linke obere Ecke.
    hintergrund = Image.new("RGB", bild.size, bild.getpixel((2, 2)))
    unterschied = ImageChops.difference(bild, hintergrund).convert("L")
    kasten = unterschied.point(lambda p: 255 if p > TOLERANZ else 0).getbbox()
    if not kasten:
        return bild.size
    links, oben, rechts, unten = kasten
    links = max(0, links - RAND)
    oben = max(0, oben - RAND)
    rechts = min(bild.width, rechts + RAND)
    unten = min(bild.height, unten + RAND)
    if (rechts - links, unten - oben) == bild.size:
        return bild.size
    ausgeschnitten = bild.crop((links, oben, rechts, unten))
    ziel.write_bytes(b"")
    ausgeschnitten.save(ziel)
    return ausgeschnitten.size


def main() -> int:
    quelle = Path(sys.argv[1])
    ziel = Path(sys.argv[2]) if len(sys.argv) > 2 else quelle
    ziel.mkdir(parents=True, exist_ok=True)
    gespart = 0
    for pfad in sorted(quelle.glob("*.png")):
        if pfad.name.endswith(".orig.png"):
            continue
        if ziel != quelle:
            kopie = ziel / pfad.name
            kopie.write_bytes(pfad.read_bytes())
            vorher = Image.open(kopfg := kopie).size
            nachher = zuschneiden(kopfg, kopfg)
        else:
            sicherung = pfad.with_suffix(".orig.png")
            if not sicherung.exists():
                sicherung.write_bytes(pfad.read_bytes())
            vorher = Image.open(pfad).size
            nachher = zuschneiden(pfad, pfad)
        gespart += (vorher[0] - nachher[0])
        print(f"  {pfad.name:38s} {vorher[0]}x{vorher[1]} -> {nachher[0]}x{nachher[1]}")
    print(f"Fertig. Weniger Breite insgesamt: {gespart} Punkte")
    return 0


if __name__ == "__main__":
    sys.exit(main())
