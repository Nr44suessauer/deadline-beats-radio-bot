#!/usr/bin/env python3
"""Sets the recording scales in the plan and writes the recording slips.

The surface zooms in 1.2-step increments; therefore only
`Startwert * 1.2^k` (Startwert = insertion value of the process after loading, see
`startscales.json`). This tool

* selects for each process the reachable module scale near 1.15 and the
 overview scale near 0.33,
* enters them in `moduleplan.json` and recalculates the tile grid,
* adds a border (notes are painted below their frame;
 standard 60 points below, 16 to the right) for modules AND overview,
* writes for each process a **recording slip** `<folder>/<identifier>.json` for the
 tile recording in the browser (fields: s0, kg, km, sg, sm, total.basis/tiles,
 module[].basis/tiles).

Call:
  python3 module-images-scales.py <plan.json> <startscales.json> <zettel-folder>
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

KLIP_W, KLIP_H = 1380, 807.8      # Recording area (measured on 24.09.2026)
SCHUTZ_UNTEN = 60                 # Points of border area under each module
SCHUTZ_RECHTS = 16
MASSTAB_MODUL_ZIEL = 1.15
MASSTAB_GESAMT_ZIEL = 0.33


def kacheln(bbox: list[float], s: float) -> list[list[int]]:
    x0, y0, x1, y1 = bbox
    breite, height = KLIP_W / s, KLIP_H / s
    nx = max(1, math.ceil((x1 - x0) / breite))
    ny = max(1, math.ceil((y1 - y0) / height))
    sx = (x1 - x0 - breite) / (nx - 1) if nx > 1 else 0
    sy = (y1 - y0 - height) / (ny - 1) if ny > 1 else 0
    return [[round(x0 + breite / 2 + i * sx), round(y0 + height / 2 + j * sy)]
            for j in range(ny) for i in range(nx)]


def main() -> int:
    plan_pfad, s0_pfad, zettel_ordner = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    plan = json.loads(plan_pfad.read_text(encoding="utf-8"))
    s0s = json.loads(s0_pfad.read_text(encoding="utf-8"))
    zettel_ordner.mkdir(parents=True, exist_ok=True)
    for key, wf in plan.items():
        s0 = s0s[key]
        kg = round(math.log(MASSTAB_GESAMT_ZIEL / s0) / math.log(1.2))
        sg = s0 * 1.2 ** kg
        km = round(math.log(MASSTAB_MODUL_ZIEL / s0) / math.log(1.2))
        sm = s0 * 1.2 ** km
        wf["total"]["scale"] = round(sg, 5)
        x0, y0, x1, y1 = wf["total"]["bbox"]
        wf["total"]["bbox"] = [x0 - 10, y0 - 10, x1 + 24, y1 + 44]
        wf["total"]["kacheln"] = kacheln(wf["total"]["bbox"], sg)
        for m in wf["module"]:
            x0, y0, x1, y1 = m["bbox"]
            m["bbox"] = [x0 - 8, y0 - 8, x1 + SCHUTZ_RECHTS, y1 + SCHUTZ_UNTEN]
            m["scale"] = round(sm, 5)
            m["kacheln"] = kacheln(m["bbox"], sm)
        zettel = {"s0": s0, "kg": kg, "km": km, "sg": round(sg, 5), "sm": round(sm, 5),
                  "total": {"basis": wf["total"]["file"][:-4], "tiles": wf["total"]["kacheln"]},
                  "module": [{"basis": m["file"][:-4], "tiles": m["kacheln"]} for m in wf["module"]]}
        (zettel_ordner / (key + ".json")).write_text(json.dumps(zettel), encoding="utf-8")
        count = len(zettel["total"]["tiles"]) + sum(len(x["tiles"]) for x in zettel["module"])
        print(f" {key:20} total s={sg:.5f} ({kg:+d})  Modules s={sm:.5f} ({km:+d})  {count} tiles")
    plan_pfad.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Plan and recording slips written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
