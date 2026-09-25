#!/usr/bin/env python3
"""Render the images of the surface documentation: one image per MODULE.

Structure: the surface paints the full window area (at 1900x1200 this is
1858x1102 pixels). A module (frame) is therefore captured in a few large tiles
and then assembled into ONE image. Scale ~1.1-1.25: the
labels are then also readable after shrinking in the document, and whoever
wants more can zoom in the document (click on the image).

Output per flow:
 "total":   an overview of the entire flow (tiles, scale ~0.35)
 "module":   list of modules with world rectangle, scale and tile grid

Call:  python3 modulbilder-plan.py <plan.json> <workflow.json> [more ...]
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

# Capture area: measured on 2026-09-24 in the surface (not estimated!) -
# [data-test-id="canvas"] was at 1380x807.8 pixels offset (200,65), the window is
# therefore 1580x906 large. Whoever makes the capture with a different window,
# must measure KLIP (getBoundingClientRect of the drawing area) and enter it here
# otherwise the tiles will not be where the plan expects them.
FENSTER = (1580, 906)
KLIP = (200, 65, 1380, 807.8)   # left edge, top edge, width, height
MASSTAB_MODUL_MAX = 1.2         # Font ~15 px
MASSTAB_MODUL_MIN = 0.7
MASSTAB_GESAMT = 0.32           # Overview: everything on one image
MARGIN = 24                       # Margin around the frame


def kacheln(bbox: tuple[float, float, float, float], scale: float) -> list[list[float]]:
    """Tile grid (world coordinates) for a rectangle at given scale.

 The tiles are evenly distributed over the rectangle: the first sits
 top left, the last bottom right - so each spot is covered exactly once
 (no gaps, no border).
    """
    x0, y0, x1, y1 = bbox
    breite = KLIP[2] / scale
    height = KLIP[3] / scale
    nx = max(1, math.ceil((x1 - x0) / breite))
    ny = max(1, math.ceil((y1 - y0) / height))
    schritt_x = (x1 - x0 - breite) / (nx - 1) if nx > 1 else 0
    schritt_y = (y1 - y0 - height) / (ny - 1) if ny > 1 else 0
    list = []
    for j in range(ny):
        for i in range(nx):
            list.append([round(x0 + breite / 2 + i * schritt_x),
                          round(y0 + height / 2 + j * schritt_y)])
    return list


def modul_massstab(bbox: tuple[float, float, float, float], kachel_max: int = 6) -> float:
    """Choose scale so that a module fits in at most <kachel_max> tiles."""
    breite, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    s = MASSTAB_MODUL_MAX
    while s > MASSTAB_MODUL_MIN and \
            math.ceil(breite * s / KLIP[2]) * math.ceil(height * s / KLIP[3]) > kachel_max:
        s -= 0.05
    return round(max(s, MASSTAB_MODUL_MIN), 3)


def plan_fuer(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    workflow = raw[0] if isinstance(raw, list) else raw
    short = re.sub(r"[^a-z0-9]+", "-", workflow["name"].lower()).strip("-")
    nodes = [k for k in workflow["nodes"] if k["type"] != "n8n-nodes-base.stickyNote"]
    frames = [k for k in workflow["nodes"] if k["type"] == "n8n-nodes-base.stickyNote"]

    xs = [k["position"][0] for k in workflow["nodes"]]
    ys = [k["position"][1] for k in workflow["nodes"]]
    gesamt_bbox = (min(xs), min(ys), max(xs) + 260, max(ys) + 240)
    total = {
        "file": "total-" + short + ".png",
        "bbox": [round(v) for v in gesamt_bbox],
        "scale": MASSTAB_GESAMT,
        "kacheln": kacheln(gesamt_bbox, MASSTAB_GESAMT),
    }

    module = []
    for i, r in enumerate(frames, 1):
        p = r["position"]
        rw = r["parameters"].get("width", 0)
        rh = r["parameters"].get("height", 0)
        x0, y0 = p[0] - MARGIN, p[1] - MARGIN
        x1, y1 = p[0] + rw + MARGIN, p[1] + rh + MARGIN
        # Frame AND all nodes contained within it - otherwise the frame
        # cuts into nodes that extend beyond the frame with their note.
        for k in nodes:
            kx, ky = k["position"]
            if p[0] - MARGIN <= kx + 55 <= p[0] + rw + MARGIN \
                    and p[1] - MARGIN <= ky + 55 <= p[1] + rh + MARGIN:
                x0, y0 = min(x0, kx - MARGIN), min(y0, ky - MARGIN)
                x1, y1 = max(x1, kx + 260 + MARGIN), max(y1, ky + 150 + MARGIN)
        bbox = (x0, y0, x1, y1)
        s = modul_massstab(bbox)
        title = r["parameters"].get("content", "").split("\n")[0].lstrip("# ").strip()
        module.append({
            "file": f"modul-{short}-{i:02d}.png",
            "title": title or r["name"],
            "frames": r["name"],
            "bbox": [round(v) for v in bbox],
            "scale": s,
            "kacheln": kacheln(bbox, s),
            "nodes": [k["name"] for k in nodes
                       if bbox[0] <= k["position"][0] + 55 <= bbox[2]
                       and bbox[1] <= k["position"][1] + 55 <= bbox[3]],
        })
    print(f" {workflow['name']:26s} {len(module):2d} modules,"
          f"Overview {len(total['kacheln'])} tiles,"
          f"{sum(len(m['kacheln']) for m in module)} tiles for modules")
    return {"name": workflow["name"], "identifier": short, "total": total, "module": module}


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    target = Path(sys.argv[1])
    plan = {Path(p).stem: plan_fuer(Path(p)) for p in sys.argv[2:]}
    target.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    kacheln_gesamt = sum(len(v["total"]["kacheln"]) + sum(len(m["kacheln"]) for m in v["module"])
                         for v in plan.values())
    print(f"Plan: {len(plan)} flows, {sum(len(v['module']) for v in plan.values())} modules,"
          f"{kacheln_gesamt} tiles -> {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
