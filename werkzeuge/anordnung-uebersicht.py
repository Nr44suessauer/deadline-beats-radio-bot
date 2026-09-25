#!/usr/bin/env python3
"""Schreibt eine Uebersicht der Zeichenflaeche eines n8n-Arbeitsablaufs.

Damit ist die Anordnung nicht nur auf der Flaeche, sondern auch schwarz auf weiss
dokumentiert: je Rahmen die Ueberschrift und Beschreibung, darunter die Knoten mit
ihrer Beschriftung und Position.

Aufruf:
    python3 anordnung-uebersicht.py <ablauf.json> [weitere.json ...] [-o datei.md]
Ohne -o geht die Uebersicht nach stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def als_ablauf(daten):
    return daten[0] if isinstance(daten, list) else daten


def bereiche(ablauf):
    """[(Rahmenknoten, [Knoten])] - Zuordnung ueber die Position im Rechteck."""
    rahmen = [k for k in ablauf["nodes"] if "stickyNote" in k["type"]]
    knoten = [k for k in ablauf["nodes"] if "stickyNote" not in k["type"]]
    ergebnis = []
    for r in rahmen:
        rx, ry = r["position"]
        rb, rh = r["parameters"].get("width", 0), r["parameters"].get("height", 0)
        drin = [k for k in knoten
                if rx <= k["position"][0] + 60 <= rx + rb
                and ry <= k["position"][1] + 50 <= ry + rh]
        ergebnis.append((r, drin))
    return ergebnis


def uebersicht(pfad: Path) -> str:
    ablauf = als_ablauf(json.loads(pfad.read_text(encoding="utf-8")))
    zeilen = [f"## {ablauf.get('name', pfad.stem)}", ""]
    knoten = [k for k in ablauf["nodes"] if "stickyNote" not in k["type"]]
    rahmen = [k for k in ablauf["nodes"] if "stickyNote" in k["type"]]
    zeilen.append(f"{len(knoten)} Knoten in {len(rahmen)} Rahmen. "
                  f"Jeder Knoten traegt seine Erklaerung als Notiz unter dem Namen.")
    zeilen.append("")
    for r, drin in bereiche(ablauf):
        inhalt = str(r["parameters"].get("content", "")).strip().splitlines()
        kopf = inhalt[0].lstrip("# ").strip() if inhalt else r["name"]
        text = " ".join(z.strip() for z in inhalt[1:] if z.strip())
        zeilen.append(f"### {kopf}  ·  `{r['name']}`")
        if text:
            zeilen.append("")
            zeilen.append(text.replace("**", "**"))
        zeilen.append("")
        if not drin:
            zeilen.append("*(Uebersichtskasten ohne Knoten)*")
            zeilen.append("")
            continue
        zeilen.append("| Knoten | Erklaerung (Notiz am Knoten) | Position |")
        zeilen.append("| --- | --- | --- |")
        for k in sorted(drin, key=lambda k: (k["position"][0], k["position"][1])):
            notiz = str(k.get("notes", "")).replace("|", "\\|").strip() or "—"
            sichtbar = "" if k.get("notesInFlow") else " (nur im Notizfeld)"
            zeilen.append(f"| `{k['name']}` | {notiz}{sichtbar} | "
                          f"{k['position'][0]}, {k['position'][1]} |")
        zeilen.append("")
    without = [k for k in knoten
               if not any(k in drin for _, drin in bereiche(ablauf))]
    if without:
        zeilen.append("### Ohne Rahmen")
        zeilen.append("")
        zeilen.append(", ".join(f"`{k['name']}`" for k in without))
        zeilen.append("")
    return "\n".join(zeilen)


def main() -> int:
    zerleger = argparse.ArgumentParser()
    zerleger.add_argument("dateien", nargs="+")
    zerleger.add_argument("-o", "--ausgabe", default="")
    args = zerleger.parse_args()

    teile = [uebersicht(Path(d)) for d in args.dateien]
    text = "\n".join(teile)
    if args.ausgabe:
        Path(args.ausgabe).write_text(text, encoding="utf-8")
        print(f"geschrieben: {args.ausgabe} ({len(text)} Zeichen)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
