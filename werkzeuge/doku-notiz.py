#!/usr/bin/env python3
"""Setzt eine Dokumentations-Notiz in einen beliebigen n8n-Ablauf.

Gedacht fuer Ablaeufe, die NICHT vom Bauwerkzeug erzeugt werden (alte Fassungen,
Sicherungen, Archiv). Die Notiz liegt oberhalb der ganzen Flaeche, beruehrt also
keinen Rahmen; Knoten, Verbindungen und Texte bleiben unangetastet.

Aufruf:
  python3 doku-notiz.py <eingabe.json> <ziel.json> <titel> <zeile1> [zeile2 ...]

Danach einspielen:
  docker cp <ziel.json> n8n:/tmp/w.json
  docker exec -u node n8n n8n import:workflow --input=/tmp/w.json
"""
from __future__ import annotations

import json
import sys
from uuid import uuid4
from pathlib import Path

NAME = "Notiz Doku"
BREITE = 1150
RAND = 80


def main() -> int:
    if len(sys.argv) < 5:
        raise SystemExit(__doc__)
    quelle, ziel, titel = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    zeilen = sys.argv[4:]

    roh = json.loads(quelle.read_text(encoding="utf-8"))
    ablauf = roh[0] if isinstance(roh, list) else roh

    # Ein zweites Mal anlegen waere unnoetig - alte Fassung der Notiz ersetzen.
    ablauf["nodes"] = [k for k in ablauf["nodes"]
                       if not (k["type"] == "n8n-nodes-base.stickyNote" and k["name"] == NAME)]

    knoten = [k for k in ablauf["nodes"] if k["type"] != "n8n-nodes-base.stickyNote"]
    if not knoten:
        raise SystemExit("Der Ablauf hat keine Knoten.")
    x0 = min(k["position"][0] for k in knoten)
    y0 = min(k["position"][1] for k in ablauf["nodes"])
    hoehe = 40 + 22 * len(zeilen)
    ablauf["nodes"].append({
        "parameters": {
            "content": "## " + titel + "\n" + "\n".join(zeilen),
            "height": hoehe,
            "width": BREITE,
            "color": 2,
        },
        "id": str(uuid4()),
        "name": NAME,
        "type": "n8n-nodes-base.stickyNote",
        "typeVersion": 1,
        "position": [x0, y0 - hoehe - RAND],
    })
    ziel.write_text(json.dumps(roh if isinstance(roh, list) else ablauf,
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  {ablauf.get('name')}: Notiz gesetzt bei [{x0}, {y0 - hoehe - RAND}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
