#!/usr/bin/env python3
"""Calculates the image plan for the surface documentation.

Why: In the instructions, the labels must be READABLE. A picture of
the entire process shows only postage stamp letters at 873 pixels width
(Magnification 0.1). Therefore, it is divided here into small excerpts - each excerpt
about three nodes, taken at magnification ~1.6 (text then ~21 px instead of 6 px).

The plan contains for each process a list of recordings:
 [file, center_x, center_y, magnification, area, nodes]

Call:  python3 bildplan.py <output.json> <process.json> [more.json ...]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

FELD = (873, 486)          # visible drawing area of the embedded browser
MASSTAB_MAX = 1.4          # Text then ~18 px; higher cuts off the node names
BREITE_MAX = 560           # World coordinates per excerpt (width)
HOEHE_MAX = 320
KNOTEN_MAX = 4
MARGIN = 90                  # Margin around the nodes (name + note under the node)


def kasten(nodes: dict) -> tuple[float, float, float, float]:
    """Space requirement of a node with label (roughly, but sufficient).

 The nodes themselves are ~110 wide, their labels underneath are wider -
 with 170 or 240 calculated, the name fits into the image.
    """
    x, y = nodes["position"]
    b = 240 if nodes["type"].endswith((".if", ".switch")) else 170
    return x, y, x + b, y + 130


def rahmen_um(frames: list[dict], x: float, y: float) -> str:
    for r in frames:
        p = r["position"]
        b = r["parameters"].get("width", 0)
        h = r["parameters"].get("height", 0)
        if p[0] <= x <= p[0] + b and p[1] <= y <= p[1] + h:
            return r["name"]
    return ""


def gruppieren(nodes: list[dict]) -> list[list[dict]]:
    """Go through nodes from top left to bottom right and bundle neighbors."""
    rest = sorted(nodes, key=lambda k: (round(k["position"][1] / 150), k["position"][0]))
    gruppen: list[list[dict]] = []
    while rest:
        keim = rest.pop(0)
        kx0, ky0, kx1, ky1 = kasten(keim)
        gruppe = [keim]
        nah = True
        while nah and rest:
            nah = False
            for i, k in enumerate(rest):
                a0, b0, a1, b1 = kasten(k)
                x0, y0 = min(kx0, a0), min(ky0, b0)
                x1, y1 = max(kx1, a1), max(ky1, b1)
                if (x1 - x0) <= BREITE_MAX and (y1 - y0) <= HOEHE_MAX \
                        and len(gruppe) < KNOTEN_MAX:
                    gruppe.append(k)
                    kx0, ky0, kx1, ky1 = x0, y0, x1, y1
                    rest.pop(i)
                    nah = True
                    break
        gruppen.append(gruppe)
    return gruppen


def plan_fuer(path: Path) -> list[list]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    workflow = raw[0] if isinstance(raw, list) else raw
    frames = [k for k in workflow["nodes"] if k["type"] == "n8n-nodes-base.stickyNote"
              and k["name"] != "Documentation Note"]
    nodes = [k for k in workflow["nodes"] if k["type"] != "n8n-nodes-base.stickyNote"]
    short = re.sub(r"[^a-z0-9]+", "-", workflow["name"].lower()).strip("-")

    aufnahmen = []
    for nummer, gruppe in enumerate(gruppieren(nodes), 1):
        x0 = min(kasten(k)[0] for k in gruppe) - MARGIN
        y0 = min(kasten(k)[1] for k in gruppe) - MARGIN
        x1 = max(kasten(k)[2] for k in gruppe) + MARGIN
        y1 = max(kasten(k)[3] for k in gruppe) + MARGIN + 30   # Space for the note
        breite, height = x1 - x0, y1 - y0
        scale = min(FELD[0] / breite, FELD[1] / height, MASSTAB_MAX)
        if scale < 0.45:      # Safety net: make very large groups smaller
            scale = 0.45
        mitte = ((x0 + x1) / 2, (y0 + y1) / 2)
        area = rahmen_um(frames, mitte[0], mitte[1])
        names = [k["name"] for k in sorted(gruppe, key=lambda k: k["position"][0])]
        aufnahmen.append([f"{short}-{nummer:02d}.png", round(mitte[0]), round(mitte[1]),
                          round(scale, 3), area, names])

    # The documentation note itself (what the process is) as the first image
    doku = [k for k in workflow["nodes"] if k["name"] == "Documentation Note"]
    if doku:
        p = doku[0]["position"]
        b = doku[0]["parameters"].get("width", 1000)
        h = doku[0]["parameters"].get("height", 150)
        aufnahmen.insert(0, [f"{short}-00.png", round(p[0] + b / 2), round(p[1] + h / 2),
                             round(min(FELD[0] / (b + MARGIN), FELD[1] / (h + MARGIN), MASSTAB_MAX), 3),
                             "Documentation Note", ["Documentation Note"]])
    print(f" {workflow['name']:26s} {len(aufnahmen):3d} Recordings")
    return aufnahmen


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    target = Path(sys.argv[1])
    plan: dict[str, list] = {}
    for name in sys.argv[2:]:
        path = Path(name)
        plan[path.stem] = plan_fuer(path)
    target.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(len(v) for v in plan.values())
    print(f"Image plan: {total} recordings from {len(plan)} runs -> {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
