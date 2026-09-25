#!/usr/bin/env python3
"""Rechnet den Bildplan fuer die Oberflaechen-Dokumentation.

Warum: In der Anleitung muss man die Beschriftungen LESEN koennen. Ein Bild vom
ganzen Ablauf zeigt bei 873 Bildpunkten Breite nur noch Briefmarken-Schrift
(Massstab 0,1). Deshalb wird hier in kleine Ausschnitte geteilt - je Ausschnitt
etwa drei Knoten, aufgenommen bei Massstab ~1,6 (Schrift dann ~21 px statt 6 px).

Der Plan enthaelt je Ablauf eine Liste von Aufnahmen:
  [datei, mitte_x, mitte_y, massstab, bereich, knoten]

Aufruf:  python3 bildplan.py <ausgabe.json> <ablauf.json> [weitere.json ...]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

FELD = (873, 486)          # sichtbare Malflaeche des eingebetteten Browsers
MASSTAB_MAX = 1.4          # Schrift dann ~18 px; hoeher schneidet die Knotennamen an
BREITE_MAX = 560           # Weltkoordinaten je Ausschnitt (Breite)
HOEHE_MAX = 320
KNOTEN_MAX = 4
RAND = 90                  # Rand um die Knoten (Name + Notiz unter dem Knoten)


def kasten(knoten: dict) -> tuple[float, float, float, float]:
    """Platzbedarf eines Knotens samt Beschriftung (grob, aber ausreichend).

    Die Knoten selbst sind ~110 breit, ihre Beschriftung darunter ist breiter -
    mit 170 bzw. 240 gerechnet passt der Name ins Bild.
    """
    x, y = knoten["position"]
    b = 240 if knoten["type"].endswith((".if", ".switch")) else 170
    return x, y, x + b, y + 130


def rahmen_um(rahmen: list[dict], x: float, y: float) -> str:
    for r in rahmen:
        p = r["position"]
        b = r["parameters"].get("width", 0)
        h = r["parameters"].get("height", 0)
        if p[0] <= x <= p[0] + b and p[1] <= y <= p[1] + h:
            return r["name"]
    return ""


def gruppieren(knoten: list[dict]) -> list[list[dict]]:
    """Knoten von oben links nach unten rechts durchgehen und Nachbarn buendeln."""
    rest = sorted(knoten, key=lambda k: (round(k["position"][1] / 150), k["position"][0]))
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


def plan_fuer(pfad: Path) -> list[list]:
    roh = json.loads(pfad.read_text(encoding="utf-8"))
    ablauf = roh[0] if isinstance(roh, list) else roh
    rahmen = [k for k in ablauf["nodes"] if k["type"] == "n8n-nodes-base.stickyNote"
              and k["name"] != "Notiz Doku"]
    knoten = [k for k in ablauf["nodes"] if k["type"] != "n8n-nodes-base.stickyNote"]
    kurz = re.sub(r"[^a-z0-9]+", "-", ablauf["name"].lower()).strip("-")

    aufnahmen = []
    for nummer, gruppe in enumerate(gruppieren(knoten), 1):
        x0 = min(kasten(k)[0] for k in gruppe) - RAND
        y0 = min(kasten(k)[1] for k in gruppe) - RAND
        x1 = max(kasten(k)[2] for k in gruppe) + RAND
        y1 = max(kasten(k)[3] for k in gruppe) + RAND + 30   # Platz fuer die Notiz
        breite, hoehe = x1 - x0, y1 - y0
        massstab = min(FELD[0] / breite, FELD[1] / hoehe, MASSTAB_MAX)
        if massstab < 0.45:      # Sicherheitsnetz: sehr grosse Gruppen kleiner machen
            massstab = 0.45
        mitte = ((x0 + x1) / 2, (y0 + y1) / 2)
        bereich = rahmen_um(rahmen, mitte[0], mitte[1])
        namen = [k["name"] for k in sorted(gruppe, key=lambda k: k["position"][0])]
        aufnahmen.append([f"{kurz}-{nummer:02d}.png", round(mitte[0]), round(mitte[1]),
                          round(massstab, 3), bereich, namen])

    # Die Doku-Notiz selbst (was der Ablauf ist) als erstes Bild
    doku = [k for k in ablauf["nodes"] if k["name"] == "Notiz Doku"]
    if doku:
        p = doku[0]["position"]
        b = doku[0]["parameters"].get("width", 1000)
        h = doku[0]["parameters"].get("height", 150)
        aufnahmen.insert(0, [f"{kurz}-00.png", round(p[0] + b / 2), round(p[1] + h / 2),
                             round(min(FELD[0] / (b + RAND), FELD[1] / (h + RAND), MASSTAB_MAX), 3),
                             "Notiz Doku", ["Notiz Doku"]])
    print(f"  {ablauf['name']:26s} {len(aufnahmen):3d} Aufnahmen")
    return aufnahmen


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    ziel = Path(sys.argv[1])
    plan: dict[str, list] = {}
    for name in sys.argv[2:]:
        pfad = Path(name)
        plan[pfad.stem] = plan_fuer(pfad)
    ziel.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    gesamt = sum(len(v) for v in plan.values())
    print(f"Bildplan: {gesamt} Aufnahmen aus {len(plan)} Abläufen -> {ziel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
