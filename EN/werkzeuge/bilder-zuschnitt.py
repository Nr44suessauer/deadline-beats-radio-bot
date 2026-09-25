#!/usr/bin/env python3
"""Cuts the empty margin from the documentation recordings.

Why: the images are generated in the running interface (873 x 486 points). Therefore
in the manual, the labels are large enough, the unmarked margin
is cut off - the crop thus becomes relatively larger when the manual
stretches it to column width.

Call:  python3 images-crop.py <source-directory> [<target-directory>]
Without target, replacement is done in place (originals remain as *.orig.png).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageChops

MARGIN = 10          # Points that remain as margin
TOLERANZ = 12      # Color deviation, from which a point is considered "content"


def zuschneiden(path: Path, target: Path) -> tuple[int, int]:
    bild = Image.open(path).convert("RGB")
    # The area is evenly dark; the upper left corner serves as reference.
    hintergrund = Image.new("RGB", bild.size, bild.getpixel((2, 2)))
    unterschied = ImageChops.difference(bild, hintergrund).convert("L")
    kasten = unterschied.point(lambda p: 255 if p > TOLERANZ else 0).getbbox()
    if not kasten:
        return bild.size
    left, above, right, below = kasten
    left = max(0, left - MARGIN)
    above = max(0, above - MARGIN)
    right = min(bild.width, right + MARGIN)
    below = min(bild.height, below + MARGIN)
    if (right - left, below - above) == bild.size:
        return bild.size
    ausgeschnitten = bild.crop((left, above, right, below))
    target.write_bytes(b"")
    ausgeschnitten.save(target)
    return ausgeschnitten.size


def main() -> int:
    source = Path(sys.argv[1])
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else source
    target.mkdir(parents=True, exist_ok=True)
    gespart = 0
    for path in sorted(source.glob("*.png")):
        if path.name.endswith(".orig.png"):
            continue
        if target != source:
            kopie = target / path.name
            kopie.write_bytes(path.read_bytes())
            before = Image.open(kopfg := kopie).size
            nachher = zuschneiden(kopfg, kopfg)
        else:
            sicherung = path.with_suffix(".orig.png")
            if not sicherung.exists():
                sicherung.write_bytes(path.read_bytes())
            before = Image.open(path).size
            nachher = zuschneiden(path, path)
        gespart += (before[0] - nachher[0])
        print(f" {path.name:38s} {before[0]}x{before[1]} -> {nachher[0]}x{nachher[1]}")
    print(f"Done. Less width in total: {gespart} points")
    return 0


if __name__ == "__main__":
    sys.exit(main())
