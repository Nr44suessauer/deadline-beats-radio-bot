#!/usr/bin/env python3
"""Checks the character surface of an n8n workflow.

A workflow is only readable once the frames really surround their nodes,
each node stands in exactly one frame and the labels match. This
tool calculates this, instead of hoping for the eye.

Call:  python3 anordnung-check.py <workflow.json> [more.json ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Node size in n8n (width, height) per type - rough, sufficient for the check.
GROESSE = {
    "n8n-nodes-base.if": (200, 110),
    "n8n-nodes-base.switch": (230, 110),
    "n8n-nodes-base.stickyNote": (0, 0),
}
STANDARD = (110, 110)


def groesse(nodes: dict) -> tuple[int, int]:
    return GROESSE.get(nodes["type"], STANDARD)


def kasten(nodes: dict) -> tuple[float, float, float, float]:
    x, y = nodes["position"]
    b, h = groesse(nodes)
    return x, y, x + b, y + h


def check(path: Path) -> int:
    raw = json.loads(path.read_text(encoding="utf-8"))
    workflow = raw[0] if isinstance(raw, list) else raw
    nodes = [k for k in workflow["nodes"] if k["type"] != "n8n-nodes-base.stickyNote"]
    frames = [k for k in workflow["nodes"] if k["type"] == "n8n-nodes-base.stickyNote"]

    print(f"\n=== {path.name}: {len(nodes)} nodes, {len(frames)} frames")
    error = 0

    # 1) Is each node in exactly one frame?
    inside: dict[str, list[str]] = {k["name"]: [] for k in nodes}
    for r in frames:
        rx, ry, rb, rh = (r["position"][0], r["position"][1],
                          r["parameters"].get("width", 0), r["parameters"].get("height", 0))
        for k in nodes:
            kx, ky, kb, kh = kasten(k)
            mitten_x, mitten_y = (kx + kb) / 2, (ky + kh) / 2
            if rx <= mitten_x <= rx + rb and ry <= mitten_y <= ry + rh:
                inside[k["name"]].append(r["name"])
                # does the node extend beyond the frame?
                if kx < rx or ky < ry or kb > rx + rb or kh > ry + rh:
                    print(f" WARNING {k['name']}: extends from {r['name']}")
                    error += 1
    without = [name for name, list in inside.items() if not list]
    mehrfach = [name for name, list in inside.items() if len(list) > 1]
    if without:
        print(f" ERROR without frame ({len(without)}): {', '.join(sorted(without))}")
        error += 1
    if mehrfach:
        print(f" ERROR in multiple frames ({len(mehrfach)}): {', '.join(sorted(mehrfach))}")
        error += 1

    # 2) Empty frames and overlapping frames
    for r in frames:
        if not any(r["name"] in list for list in inside.values()):
            print(f" NOTE {r['name']}: contains no nodes")
    for i, a in enumerate(frames):
        for b in frames[i + 1:]:
            ax, ay = a["position"]
            bx, by = b["position"]
            ab, ah = a["parameters"].get("width", 0), a["parameters"].get("height", 0)
            bb, bh = b["parameters"].get("width", 0), b["parameters"].get("height", 0)
            if ax < bx + bb and bx < ax + ab and ay < by + bh and by < ay + ah:
                print(f" WARNING Overlapping frames: {a['name']} / {b['name']}")
                error += 1

    # 3) Label: Short note (notesInFlow) and note
    ohne_notiz = [k["name"] for k in nodes if not str(k.get("notes", "")).strip()]
    im_plan = [k["name"] for k in nodes if k.get("notesInFlow")]
    print(f" Note field: {len(nodes) - len(ohne_notiz)}/{len(nodes)} | visible in plan (notesInFlow): {len(im_plan)}")
    if ohne_notiz:
        print(f" NOTE without note: {', '.join(sorted(ohne_notiz))}")

    # 4) Frame colors
    farben: dict[int, int] = {}
    for r in frames:
        farbe = r["parameters"].get("color", 0)
        farben[farbe] = farben.get(farbe, 0) + 1
    print(" Frame colors:" + ", ".join(f"{f}->{n}x" for f, n in sorted(farben.items())))

    # 5) Extent of the drawing area
    xs = [k["position"][0] for k in workflow["nodes"]]
    ys = [k["position"][1] for k in workflow["nodes"]]
    print(f" Area: x {min(xs)}..{max(xs)}, y {min(ys)}..{max(ys)}")
    return error


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    error = 0
    for name in sys.argv[1:]:
        error += check(Path(name))
    print(f"\n{error} Finding(s)")
    return 1 if error else 0


if __name__ == "__main__":
    sys.exit(main())
