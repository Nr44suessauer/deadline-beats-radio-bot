#!/usr/bin/env python3
"""Setzt die Kacheln zu je einem Bild pro Modul zusammen.

Die Kacheln wurden mit dem Namen
  <modul>__t<nr>__x<tx>__y<ty>__s<massstab>.png
abgelegt. Aus dem Massstab des Plans und den Transformationswerten (tx, ty) der
Aufnahme laesst sich der Punkt im Gesamtbild exakt berechnen:

  Bildpunkt = Kachelpunkt - (tx + X0 * s)

(X0 = linke Kante des Moduls in Weltkoordinaten). Damit sitzen die Kacheln
pixelgenau, obwohl sie einzeln aufgenommen wurden.

Aufruf:  python3 bilder-stitch.py <plan.json> <kachel-ordner> <ziel-ordner>
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageChops

MUSTER = re.compile(r"^(?P<basis>.+?)__t\d+__x(?P<tx>-?\d+)__y(?P<ty>-?\d+)__s(?P<s>[\d.]+)\.png$")

# Leere Raender wegschneiden: Zeilen/Spalten ohne "Tinte" kosten im Dokument nur
# Platz (das Bild wird auf Seitenbreite verkleinert).
# ACHTUNG: im hellen Bild sind Knoten weiss und der Grund fast weiss - weisse
# Karten duerfen NICHT als leer gelten. Als Inhalt zaehlt daher nur, was deutlich
# dunkler als der Grund ist oder farbig (Rahmen, Linien, Schrift).
ABSTAND = 25       # so viel dunkler als der Grund = Inhalt
FARBIG = 20        # so viel Farbabstand zwischen den Kanaelen = Inhalt
RESTRAND = 14      # dieser Rand bleibt stehen


def zuschneiden(bild: Image.Image) -> Image.Image:
    """Schneidet Raender ohne Inhalt ab (bei Zweifel: nichts).

    Als Inhalt zaehlt alles, was deutlich dunkler als der Grund ist (Schrift,
    Linien, Schatten) ODER farbig (Rahmen, farbige Knoten, Notizzettel). Damit
    bleiben auch weisse Knoten auf fast weissem Grund erhalten, weil ihre
    Umrandung und ihr Schatten Farbe bzw. Helligkeit zeigen.
    """
    breite, hoehe = bild.size
    if breite < 60 or hoehe < 60:
        return bild
    rand = [bild.getpixel((x, 1)) for x in range(0, breite, max(1, breite // 60))]
    rand += [bild.getpixel((x, hoehe - 2)) for x in range(0, breite, max(1, breite // 60))]
    rand += [bild.getpixel((1, y)) for y in range(0, hoehe, max(1, hoehe // 60))]
    rand += [bild.getpixel((breite - 2, y)) for y in range(0, hoehe, max(1, hoehe // 60))]
    grund = tuple(sorted(rand, key=rand.count)[len(rand) // 2])
    grund_hell = sum(grund) / 3

    grau = bild.convert("L")
    dunkel = grau.point(lambda v: 255 if v < grund_hell - ABSTAND else 0, mode="L")
    r, g, b = bild.split()
    hoechst = ImageChops.lighter(ImageChops.lighter(r, g), b)
    tiefst = ImageChops.darker(ImageChops.darker(r, g), b)
    bunt = ImageChops.subtract(hoechst, tiefst).point(
        lambda v: 255 if v > FARBIG else 0, mode="L")
    kasten = ImageChops.lighter(dunkel, bunt).getbbox()
    if not kasten:
        return bild
    links, oben, rechts, unten = kasten
    links = max(0, links - RESTRAND)
    oben = max(0, oben - RESTRAND)
    rechts = min(breite, rechts + RESTRAND)
    unten = min(hoehe, unten + RESTRAND)
    if breite - links < 60 or hoehe - oben < 60 or rechts < 60 or unten < 60:
        return bild
    # nie mehr als ein Drittel an einer Seite wegnehmen
    if links > breite // 3 or oben > hoehe // 3 \
            or breite - rechts > breite // 3 or hoehe - unten > hoehe // 3:
        return bild
    return bild.crop((links, oben, rechts, unten))


def main() -> int:
    plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    kachel_ordner = Path(sys.argv[2])
    ziel = Path(sys.argv[3])
    ziel.mkdir(parents=True, exist_ok=True)

    # Kacheln nach Modulnamen einsammeln
    nach_basis: dict[str, list[tuple[Path, int, int]]] = defaultdict(list)
    for pfad in sorted(kachel_ordner.glob("*.png")):
        treffer = MUSTER.match(pfad.name)
        if not treffer:
            continue
        nach_basis[treffer.group("basis")].append(
            (pfad, int(treffer.group("tx")), int(treffer.group("ty"))))

    for kennung, daten in plan.items():
        teile = [(daten["gesamt"]["datei"], daten["gesamt"])] \
            + [(m["datei"], m) for m in daten["module"]]
        for datei, angaben in teile:
            basis = datei.replace(".png", "")
            kacheln = nach_basis.get(basis, [])
            if not kacheln:
                print(f"  FEHLT: {datei} (keine Kacheln)")
                continue
            x0, y0, x1, y1 = angaben["bbox"]
            s = angaben["massstab"]
            breite = round((x1 - x0) * s)
            hoehe = round((y1 - y0) * s)
            bild = Image.new("RGB", (breite, hoehe), (22, 24, 29))
            for pfad, tx, ty in kacheln:
                kachel = Image.open(pfad).convert("RGB")
                links = round(-(tx + x0 * s))
                oben = round(-(ty + y0 * s))
                bild.paste(kachel, (links, oben))
            if "--ohne-zuschnitt" not in sys.argv:
                vorher = bild.size
                bild = zuschneiden(bild)
                if bild.size != vorher:
                    rand = f" (Rand entfernt: {vorher[0]}x{vorher[1]})"
                else:
                    rand = ""
            else:
                rand = ""
            ziel_pfad = ziel / datei
            bild.save(ziel_pfad, optimize=True)
            kb = ziel_pfad.stat().st_size // 1024
            b, h = bild.size
            print(f"  {datei:44s} {b}x{h}  {kb:5d} KB  ({len(kacheln)} Kacheln){rand}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
