#!/usr/bin/env python3
"""Setzt die Aufnahme-Massstaebe in den Plan und schreibt die Aufnahmezettel.

Die Oberflaeche zoomt in 1,2er-Schritten; erreichbar ist deshalb nur
`Startwert * 1,2^k` (Startwert = Einpasswert des Ablaufs nach dem Laden, siehe
`startmassstaebe.json`). Dieses Werkzeug

* waehlt je Ablauf den erreichbaren Modul-Massstab nahe 1,15 und den
  Uebersichts-Massstab nahe 0,33,
* traegt sie in `modulplan.json` ein und rechnet die Kachelraster neu,
* ergaenzt um Module UND Uebersicht einen Schutzrand (Notizen malen unten
  ueber ihren Rahmen hinaus; Standard 60 Punkte unten, 16 rechts),
* schreibt je Ablauf einen **Aufnahmezettel** `<ordner>/<kennung>.json` fuer die
  Kachelaufnahme im Browser (Felder: s0, kg, km, sg, sm, gesamt.basis/tiles,
  module[].basis/tiles).

Aufruf:
  python3 modulbilder-massstaebe.py <plan.json> <startmassstaebe.json> <zettel-ordner>
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

KLIP_W, KLIP_H = 1380, 807.8      # Aufnahmeflaeche (24.09.2026 gemessen)
SCHUTZ_UNTEN = 60                 # Punkte Schutzrand unter jedem Modul
SCHUTZ_RECHTS = 16
MASSTAB_MODUL_ZIEL = 1.15
MASSTAB_GESAMT_ZIEL = 0.33


def kacheln(bbox: list[float], s: float) -> list[list[int]]:
    x0, y0, x1, y1 = bbox
    breite, hoehe = KLIP_W / s, KLIP_H / s
    nx = max(1, math.ceil((x1 - x0) / breite))
    ny = max(1, math.ceil((y1 - y0) / hoehe))
    sx = (x1 - x0 - breite) / (nx - 1) if nx > 1 else 0
    sy = (y1 - y0 - hoehe) / (ny - 1) if ny > 1 else 0
    return [[round(x0 + breite / 2 + i * sx), round(y0 + hoehe / 2 + j * sy)]
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
        wf["gesamt"]["massstab"] = round(sg, 5)
        x0, y0, x1, y1 = wf["gesamt"]["bbox"]
        wf["gesamt"]["bbox"] = [x0 - 10, y0 - 10, x1 + 24, y1 + 44]
        wf["gesamt"]["kacheln"] = kacheln(wf["gesamt"]["bbox"], sg)
        for m in wf["module"]:
            x0, y0, x1, y1 = m["bbox"]
            m["bbox"] = [x0 - 8, y0 - 8, x1 + SCHUTZ_RECHTS, y1 + SCHUTZ_UNTEN]
            m["massstab"] = round(sm, 5)
            m["kacheln"] = kacheln(m["bbox"], sm)
        zettel = {"s0": s0, "kg": kg, "km": km, "sg": round(sg, 5), "sm": round(sm, 5),
                  "gesamt": {"basis": wf["gesamt"]["datei"][:-4], "tiles": wf["gesamt"]["kacheln"]},
                  "module": [{"basis": m["datei"][:-4], "tiles": m["kacheln"]} for m in wf["module"]]}
        (zettel_ordner / (key + ".json")).write_text(json.dumps(zettel), encoding="utf-8")
        anzahl = len(zettel["gesamt"]["tiles"]) + sum(len(x["tiles"]) for x in zettel["module"])
        print(f"  {key:20} gesamt s={sg:.5f} ({kg:+d})  Module s={sm:.5f} ({km:+d})  {anzahl} Kacheln")
    plan_pfad.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Plan und Aufnahmezettel geschrieben.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
