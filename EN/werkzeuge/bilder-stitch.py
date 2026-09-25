#!/usr/bin/env python3
"""Assembles the tiles into one image per module.

The tiles were saved with the name
 <modul>__t<nr>__x<tx>__y<ty>__s<scale>.png
From the scale of the plan and the transformation values (tx, ty) of the
capture, the point in the overall image can be calculated exactly:

 Image point = Tile point - (tx + X0 * s)

(X0 = left edge of the module in world coordinates). Thus, the tiles
are placed pixel-accurately, even though they were captured individually.

Call:  python3 images-stitch.py <plan.json> <tile-folder> <target-folder>
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageChops

MUSTER = re.compile(r"^(?P<basis>.+?)__t\d+__x(?P<tx>-?\d+)__y(?P<ty>-?\d+)__s(?P<s>[\d.]+)\.png$")

# Trim empty borders: Rows/columns without "ink" only cost
# space in the document (the image is shrunk to page width).
# ATTENTION: in the bright image, nodes are white and the background is almost white - white
# maps MUST NOT be considered empty. Therefore, content counts only what is clearly
# darker than the background or colored (frame, lines, text).
ABSTAND = 25       # this much darker than the background = content
FARBIG = 20        # this much color difference between channels = content
RESTRAND = 14      # this border remains


def zuschneiden(bild: Image.Image) -> Image.Image:
    """Crops borders without content (when in doubt: nothing).

 Everything that is clearly darker than the background (text,
 lines, shadows) OR colored (frame, colored nodes, note sheets) counts as content. This
 also preserves white nodes on almost white backgrounds because their
 outline and shadow show color or brightness.
    """
    breite, height = bild.size
    if breite < 60 or height < 60:
        return bild
    margin = [bild.getpixel((x, 1)) for x in range(0, breite, max(1, breite // 60))]
    margin += [bild.getpixel((x, height - 2)) for x in range(0, breite, max(1, breite // 60))]
    margin += [bild.getpixel((1, y)) for y in range(0, height, max(1, height // 60))]
    margin += [bild.getpixel((breite - 2, y)) for y in range(0, height, max(1, height // 60))]
    reason = tuple(sorted(margin, key=margin.count)[len(margin) // 2])
    grund_hell = sum(reason) / 3

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
    left, above, right, below = kasten
    left = max(0, left - RESTRAND)
    above = max(0, above - RESTRAND)
    right = min(breite, right + RESTRAND)
    below = min(height, below + RESTRAND)
    if breite - left < 60 or height - above < 60 or right < 60 or below < 60:
        return bild
    # never remove more than one third of a side
    if left > breite // 3 or above > height // 3 \
            or breite - right > breite // 3 or height - below > height // 3:
        return bild
    return bild.crop((left, above, right, below))


def main() -> int:
    plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    kachel_ordner = Path(sys.argv[2])
    target = Path(sys.argv[3])
    target.mkdir(parents=True, exist_ok=True)

    # Collect tiles by module name
    nach_basis: dict[str, list[tuple[Path, int, int]]] = defaultdict(list)
    for path in sorted(kachel_ordner.glob("*.png")):
        hits = MUSTER.match(path.name)
        if not hits:
            continue
        nach_basis[hits.group("basis")].append(
            (path, int(hits.group("tx")), int(hits.group("ty"))))

    for identifier, data in plan.items():
        teile = [(data["total"]["file"], data["total"])] \
            + [(m["file"], m) for m in data["module"]]
        for file, angaben in teile:
            basis = file.replace(".png", "")
            kacheln = nach_basis.get(basis, [])
            if not kacheln:
                print(f" MISSING: {file} (no tiles)")
                continue
            x0, y0, x1, y1 = angaben["bbox"]
            s = angaben["scale"]
            breite = round((x1 - x0) * s)
            height = round((y1 - y0) * s)
            bild = Image.new("RGB", (breite, height), (22, 24, 29))
            for path, tx, ty in kacheln:
                kachel = Image.open(path).convert("RGB")
                left = round(-(tx + x0 * s))
                above = round(-(ty + y0 * s))
                bild.paste(kachel, (left, above))
            if "--no-crop" not in sys.argv:
                before = bild.size
                bild = zuschneiden(bild)
                if bild.size != before:
                    margin = f" (border removed: {before[0]}x{before[1]})"
                else:
                    margin = ""
            else:
                margin = ""
            ziel_pfad = target / file
            bild.save(ziel_pfad, optimize=True)
            kb = ziel_pfad.stat().st_size // 1024
            b, h = bild.size
            print(f" {file:44s} {b}x{h}  {kb:5d} KB  ({len(kacheln)} tiles){margin}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
