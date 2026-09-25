#!/usr/bin/env python3
"""Prueft die Zeichenflaeche eines n8n-Arbeitsablaufs.

Ein Ablauf ist erst dann lesbar, wenn die Rahmen wirklich um ihre Knoten liegen,
jeder Knoten in genau einem Rahmen steht und die Beschriftungen stimmen. Dieses
Werkzeug rechnet das nach, statt auf das Auge zu hoffen.

Aufruf:  python3 anordnung-pruefen.py <ablauf.json> [weitere.json ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Knotengroesse in n8n (Breite, Hoehe) je Typ - grob, reicht fuer die Pruefung.
GROESSE = {
    "n8n-nodes-base.if": (200, 110),
    "n8n-nodes-base.switch": (230, 110),
    "n8n-nodes-base.stickyNote": (0, 0),
}
STANDARD = (110, 110)


def groesse(knoten: dict) -> tuple[int, int]:
    return GROESSE.get(knoten["type"], STANDARD)


def kasten(knoten: dict) -> tuple[float, float, float, float]:
    x, y = knoten["position"]
    b, h = groesse(knoten)
    return x, y, x + b, y + h


def pruefe(pfad: Path) -> int:
    roh = json.loads(pfad.read_text(encoding="utf-8"))
    ablauf = roh[0] if isinstance(roh, list) else roh
    knoten = [k for k in ablauf["nodes"] if k["type"] != "n8n-nodes-base.stickyNote"]
    rahmen = [k for k in ablauf["nodes"] if k["type"] == "n8n-nodes-base.stickyNote"]

    print(f"\n=== {pfad.name}: {len(knoten)} Knoten, {len(rahmen)} Rahmen")
    fehler = 0

    # 1) Jeder Knoten in genau einem Rahmen?
    drin: dict[str, list[str]] = {k["name"]: [] for k in knoten}
    for r in rahmen:
        rx, ry, rb, rh = (r["position"][0], r["position"][1],
                          r["parameters"].get("width", 0), r["parameters"].get("height", 0))
        for k in knoten:
            kx, ky, kb, kh = kasten(k)
            mitten_x, mitten_y = (kx + kb) / 2, (ky + kh) / 2
            if rx <= mitten_x <= rx + rb and ry <= mitten_y <= ry + rh:
                drin[k["name"]].append(r["name"])
                # ragt der Knoten ueber den Rahmen hinaus?
                if kx < rx or ky < ry or kb > rx + rb or kh > ry + rh:
                    print(f"  WARNUNG {k['name']}: ragt aus {r['name']} heraus")
                    fehler += 1
    ohne = [name for name, liste in drin.items() if not liste]
    mehrfach = [name for name, liste in drin.items() if len(liste) > 1]
    if ohne:
        print(f"  FEHLER ohne Rahmen ({len(ohne)}): {', '.join(sorted(ohne))}")
        fehler += 1
    if mehrfach:
        print(f"  FEHLER in mehreren Rahmen ({len(mehrfach)}): {', '.join(sorted(mehrfach))}")
        fehler += 1

    # 2) Leere Rahmen und Rahmen, die sich ueberlagern
    for r in rahmen:
        if not any(r["name"] in liste for liste in drin.values()):
            print(f"  HINWEIS {r['name']}: enthaelt keinen Knoten")
    for i, a in enumerate(rahmen):
        for b in rahmen[i + 1:]:
            ax, ay = a["position"]
            bx, by = b["position"]
            ab, ah = a["parameters"].get("width", 0), a["parameters"].get("height", 0)
            bb, bh = b["parameters"].get("width", 0), b["parameters"].get("height", 0)
            if ax < bx + bb and bx < ax + ab and ay < by + bh and by < ay + ah:
                print(f"  WARNUNG Rahmen ueberlagern sich: {a['name']} / {b['name']}")
                fehler += 1

    # 3) Beschriftung: Kurznotiz (notesInFlow) und Notiz
    ohne_notiz = [k["name"] for k in knoten if not str(k.get("notes", "")).strip()]
    im_plan = [k["name"] for k in knoten if k.get("notesInFlow")]
    print(f"  Notizfeld: {len(knoten) - len(ohne_notiz)}/{len(knoten)} | sichtbar im Plan (notesInFlow): {len(im_plan)}")
    if ohne_notiz:
        print(f"  HINWEIS ohne Notiz: {', '.join(sorted(ohne_notiz))}")

    # 4) Farben der Rahmen
    farben: dict[int, int] = {}
    for r in rahmen:
        farbe = r["parameters"].get("color", 0)
        farben[farbe] = farben.get(farbe, 0) + 1
    print("  Rahmenfarben: " + ", ".join(f"{f}->{n}x" for f, n in sorted(farben.items())))

    # 5) Ausdehnung der Zeichenflaeche
    xs = [k["position"][0] for k in ablauf["nodes"]]
    ys = [k["position"][1] for k in ablauf["nodes"]]
    print(f"  Flaeche: x {min(xs)}..{max(xs)}, y {min(ys)}..{max(ys)}")
    return fehler


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    fehler = 0
    for name in sys.argv[1:]:
        fehler += pruefe(Path(name))
    print(f"\n{fehler} Befund(e)")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
