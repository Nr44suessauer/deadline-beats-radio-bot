#!/usr/bin/env python3
"""Plant die Bilder der Oberflaechen-Dokumentation: je MODUL ein Bild.

Aufbau: die Oberflaeche malt die volle Fensterflaeche (bei 1900x1200 also
1858x1102 Punkte). Ein Modul (Rahmen) wird deshalb in wenigen grossen Kacheln
aufgenommen und danach zu EINEM Bild zusammengesetzt. Massstab ~1,1-1,25: die
Beschriftungen sind dann auch nach dem Verkleinern im Dokument lesbar, und wer
mehr will, zoomt im Dokument (Klick aufs Bild).

Ausgabe je Ablauf:
  "gesamt":   eine Uebersicht des ganzen Ablaufs (Kacheln, Massstab ~0,35)
  "module":   Liste der Module mit Welt-Rechteck, Massstab und Kachelraster

Aufruf:  python3 modulbilder-plan.py <plan.json> <ablauf.json> [weitere ...]
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

# Aufnahmeflaeche: am 2026-09-24 in der Oberflaeche GEMESSEN (nicht geraten!) -
# [data-test-id="canvas"] lag bei 1380x807.8 Punkten ab (200,65), das Fenster ist
# damit 1580x906 gross. Wer die Aufnahme mit einem anderen Fenster macht,
# muss KLIP nachmessen (getBoundingClientRect der Zeichenflaeche) und hier
# eintragen - sonst liegen die Kacheln nicht dort, wo der Plan sie erwartet.
FENSTER = (1580, 906)
KLIP = (200, 65, 1380, 807.8)   # linke Kante, obere Kante, Breite, Hoehe
MASSTAB_MODUL_MAX = 1.2         # Schrift ~15 px
MASSTAB_MODUL_MIN = 0.7
MASSTAB_GESAMT = 0.32           # Uebersicht: alles auf einem Bild
RAND = 24                       # Rand um den Rahmen


def kacheln(bbox: tuple[float, float, float, float], massstab: float) -> list[list[float]]:
    """Kachelraster (Weltkoordinaten) fuer ein Rechteck bei gegebenem Massstab.

    Die Kacheln werden gleichmaessig ueber das Rechteck verteilt: die erste sitzt
    links oben, die letzte rechts unten - so ist jede Stelle genau einmal bedeckt
    (keine Luecken, kein Rand).
    """
    x0, y0, x1, y1 = bbox
    breite = KLIP[2] / massstab
    hoehe = KLIP[3] / massstab
    nx = max(1, math.ceil((x1 - x0) / breite))
    ny = max(1, math.ceil((y1 - y0) / hoehe))
    schritt_x = (x1 - x0 - breite) / (nx - 1) if nx > 1 else 0
    schritt_y = (y1 - y0 - hoehe) / (ny - 1) if ny > 1 else 0
    liste = []
    for j in range(ny):
        for i in range(nx):
            liste.append([round(x0 + breite / 2 + i * schritt_x),
                          round(y0 + hoehe / 2 + j * schritt_y)])
    return liste


def modul_massstab(bbox: tuple[float, float, float, float], kachel_max: int = 6) -> float:
    """Massstab so waehlen, dass ein Modul in hoechstens <kachel_max> Kacheln passt."""
    breite, hoehe = bbox[2] - bbox[0], bbox[3] - bbox[1]
    s = MASSTAB_MODUL_MAX
    while s > MASSTAB_MODUL_MIN and \
            math.ceil(breite * s / KLIP[2]) * math.ceil(hoehe * s / KLIP[3]) > kachel_max:
        s -= 0.05
    return round(max(s, MASSTAB_MODUL_MIN), 3)


def plan_fuer(pfad: Path) -> dict:
    roh = json.loads(pfad.read_text(encoding="utf-8"))
    ablauf = roh[0] if isinstance(roh, list) else roh
    kurz = re.sub(r"[^a-z0-9]+", "-", ablauf["name"].lower()).strip("-")
    knoten = [k for k in ablauf["nodes"] if k["type"] != "n8n-nodes-base.stickyNote"]
    rahmen = [k for k in ablauf["nodes"] if k["type"] == "n8n-nodes-base.stickyNote"]

    xs = [k["position"][0] for k in ablauf["nodes"]]
    ys = [k["position"][1] for k in ablauf["nodes"]]
    gesamt_bbox = (min(xs), min(ys), max(xs) + 260, max(ys) + 240)
    gesamt = {
        "datei": "gesamt-" + kurz + ".png",
        "bbox": [round(v) for v in gesamt_bbox],
        "massstab": MASSTAB_GESAMT,
        "kacheln": kacheln(gesamt_bbox, MASSTAB_GESAMT),
    }

    module = []
    for i, r in enumerate(rahmen, 1):
        p = r["position"]
        rw = r["parameters"].get("width", 0)
        rh = r["parameters"].get("height", 0)
        x0, y0 = p[0] - RAND, p[1] - RAND
        x1, y1 = p[0] + rw + RAND, p[1] + rh + RAND
        # Rahmen UND alle Knoten, die darin liegen - sonst schneidet der Rand
        # Knoten an, die mit ihrer Notiz über den Rahmen hinausstehen.
        for k in knoten:
            kx, ky = k["position"]
            if p[0] - RAND <= kx + 55 <= p[0] + rw + RAND \
                    and p[1] - RAND <= ky + 55 <= p[1] + rh + RAND:
                x0, y0 = min(x0, kx - RAND), min(y0, ky - RAND)
                x1, y1 = max(x1, kx + 260 + RAND), max(y1, ky + 150 + RAND)
        bbox = (x0, y0, x1, y1)
        s = modul_massstab(bbox)
        titel = r["parameters"].get("content", "").split("\n")[0].lstrip("# ").strip()
        module.append({
            "datei": f"modul-{kurz}-{i:02d}.png",
            "titel": titel or r["name"],
            "rahmen": r["name"],
            "bbox": [round(v) for v in bbox],
            "massstab": s,
            "kacheln": kacheln(bbox, s),
            "knoten": [k["name"] for k in knoten
                       if bbox[0] <= k["position"][0] + 55 <= bbox[2]
                       and bbox[1] <= k["position"][1] + 55 <= bbox[3]],
        })
    print(f"  {ablauf['name']:26s} {len(module):2d} Module, "
          f"Übersicht {len(gesamt['kacheln'])} Kacheln, "
          f"{sum(len(m['kacheln']) for m in module)} Kacheln für Module")
    return {"name": ablauf["name"], "kennung": kurz, "gesamt": gesamt, "module": module}


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    ziel = Path(sys.argv[1])
    plan = {Path(p).stem: plan_fuer(Path(p)) for p in sys.argv[2:]}
    ziel.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    kacheln_gesamt = sum(len(v["gesamt"]["kacheln"]) + sum(len(m["kacheln"]) for m in v["module"])
                         for v in plan.values())
    print(f"Plan: {len(plan)} Abläufe, {sum(len(v['module']) for v in plan.values())} Module, "
          f"{kacheln_gesamt} Kacheln -> {ziel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
