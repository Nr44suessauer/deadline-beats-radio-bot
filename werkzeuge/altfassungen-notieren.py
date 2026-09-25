#!/usr/bin/env python3
"""Setzt in die alten Radio-Ablaeufe eine "Altfassung"-Notiz (und ins Archiv eine
Dokumentations-Notiz).

Diese Ablaeufe werden nicht vom Bauwerkzeug erzeugt (Kopien, Sicherungen, das
Archiv der ersten Fassung). Sie sollen in der Oberflaeche trotzdem erklaeren,
was sie sind - sonst raetselt man beim Oeffnen. Geaendert wird nur EINE zusaetzliche
Haftnotiz oberhalb der Flaeche; Knoten, Verbindungen und Texte bleiben unangetastet.

Aufruf:  python3 altfassungen-notieren.py [--trocken]
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

CFG = "~/.ssh/config"
CT = "103"
NAME = "Notiz Doku"

# (Kennung, Titel der Notiz, Zeilen)
LISTE = [
    ("7Vv3NSFsS7OZaBSd", "Altfassung: Zwischenstand V2.0", [
        "Zwischenstand aus der Umbauphase (20.09.2026) - NICHT in Betrieb.",
        "In Betrieb ist der Ablauf \"Radio - Telegram-Agent\" (RadioAgentBot).",
        "Aufbewahrt als Anschauung; Beschreibung der Fassungen: BAU.md.",
        "Sicherungen liegen unter sicherungen/radio-fassungen/ (ausserhalb des Projekts).",
    ]),
    ("zxBICXCfUaMGhNmT", "Altfassung: Kopie eines Zwischenstands", [
        "Kopie aus der Umbauphase - NICHT in Betrieb.",
        "In Betrieb ist der Ablauf \"Radio - Telegram-Agent\" (RadioAgentBot).",
        "Kann geloescht werden, wenn die Sicherungen unter sicherungen/radio-fassungen/ genuegen.",
    ]),
    ("jt2IC4TVPTF1KDLp", "Altfassung: Kopie des Wunschbots", [
        "Alte Kopie des Wunschbots (erste Fassung) - NICHT in Betrieb.",
        "In Betrieb ist der Ablauf \"Radio - Telegram-Agent\" (RadioAgentBot).",
        "Beschreibung: BAU.md (v1-v9); Sicherungen: sicherungen/radio-fassungen/.",
    ]),
    ("da7f06de-0bcf-4fbe-8c8d-ad8927d3d509", "Altfassung: Stand vor dem Umbau", [
        "Sicherung der Fassung VOR dem Umbau (19.09.2026) - NICHT in Betrieb.",
        "Damit laesst sich der Stand von damals ansehen; in Betrieb ist RadioAgentBot.",
        "Beschreibung: BAU.md; Sicherungen: sicherungen/radio-fassungen/.",
    ]),
    ("RadioTelegramBot", "Altfassung: Radio - Telegram-Wunschbot", [
        "Der Wunschbot der ersten Fassung (bis 19.09.2026) - NICHT in Betrieb.",
        "Abgeloest vom \"Radio - Telegram-Agent\" (Stufen 0-3, Werkzeuge, Postfach).",
        "Seine Werkzeuge stecken heute in \"Werkzeug - Radio\" und \"Werkzeug - Meldungen\".",
        "Beschreibung: BAU.md (v1-v9), HANDBUCH.md.",
    ]),
    ("iDfPikpAIqTO9XQ2", "Altfassung: Kopie des Wunschbots", [
        "Kopie des Wunschbots der ersten Fassung - NICHT in Betrieb.",
        "In Betrieb ist der Ablauf \"Radio - Telegram-Agent\" (RadioAgentBot).",
        "Beschreibung: BAU.md (v1-v9).",
    ]),
    ("RadioTelegramBot-Archiv-2026-09-19", "Altfassung: Sicherung 19.09.2026", [
        "Sicherung des Wunschbots vom 19.09.2026 - NICHT in Betrieb.",
        "Aufbewahrt, falls der Stand von damals gebraucht wird.",
        "Beschreibung: BAU.md; Sicherungen: sicherungen/radio-fassungen/.",
    ]),
    ("RadioWerkzeugSuche", "Altfassung: Werkzeug - Titel suchen", [
        "Einzelner Werkzeug-Ablauf der ersten Fassung - NICHT in Betrieb.",
        "Diese Aufgabe steckt heute im Ablauf \"Werkzeug - Radio\" (drei Zweige in einem Ablauf).",
        "Beschreibung: HANDBUCH.md, HANDBUCH.md.",
    ]),
    ("RadioWerkzeugRichtung", "Altfassung: Werkzeug - Richtung suchen", [
        "Einzelner Werkzeug-Ablauf der ersten Fassung - NICHT in Betrieb.",
        "Diese Aufgabe steckt heute im Ablauf \"Werkzeug - Radio\".",
        "Beschreibung: HANDBUCH.md, HANDBUCH.md.",
    ]),
    ("RadioWerkzeugSofort", "Altfassung: Werkzeug - Sofort spielen", [
        "Einzelner Werkzeug-Ablauf der ersten Fassung - NICHT in Betrieb.",
        "Diese Aufgabe steckt heute im Ablauf \"Werkzeug - Radio\".",
        "Beschreibung: HANDBUCH.md, HANDBUCH.md.",
    ]),
    ("RadioWerkzeugDanach", "Altfassung: Werkzeug - Danach spielen", [
        "Einzelner Werkzeug-Ablauf der ersten Fassung - NICHT in Betrieb.",
        "Diese Aufgabe steckt heute im Ablauf \"Werkzeug - Radio\".",
        "Beschreibung: HANDBUCH.md, HANDBUCH.md.",
    ]),
    ("RadioWerkzeugStatus", "Altfassung: Werkzeug - Was laeuft", [
        "Einzelner Werkzeug-Ablauf der ersten Fassung - NICHT in Betrieb.",
        "Diese Aufgabe steckt heute im Ablauf \"Werkzeug - Radio\".",
        "Beschreibung: HANDBUCH.md, HANDBUCH.md.",
    ]),
    ("bjFSfXGqpLg7AAXw", "Radio - AI-Moderator (Archiv)", [
        "Erste Fassung der Moderation: Text erzeugen, sprechen, in den Sender stellen.",
        "NICHT in Betrieb - im Betrieb moderiert der Agent (RadioAgentBot) ueber den Dienst radio-tts.",
        "Rahmen und Beschriftungen: werkzeuge/archiv-rahmen.py (nicht im Bauwerkzeug).",
        "Beschreibung: BAU.md, HANDBUCH.md, ANHANG/n8n-oberflaeche.html (Abschnitt 16).",
    ]),
]


def ssh(befehl: str) -> str:
    fertig = subprocess.run(["ssh", "-F", CFG, "-o", "BatchMode=yes", "ai-server", befehl],
                            capture_output=True, text=True, check=False)
    if fertig.returncode:
        raise RuntimeError(fertig.stderr.strip()[:300])
    return fertig.stdout


def holen(kennung: str) -> dict:
    roh = ssh("pct exec %s -- bash -lc 'docker exec -u node n8n n8n export:workflow "
              "--id=%s --output=/tmp/w.json >/dev/null 2>&1; docker exec n8n cat /tmp/w.json'"
              % (CT, kennung))
    daten = json.loads(roh)
    return daten


def notieren(daten: dict, titel: str, zeilen: list[str]) -> dict:
    ablauf = daten[0] if isinstance(daten, list) else daten
    ablauf["nodes"] = [k for k in ablauf["nodes"]
                       if not (k["type"] == "n8n-nodes-base.stickyNote" and k["name"] == NAME)]
    knoten = [k for k in ablauf["nodes"] if k["type"] != "n8n-nodes-base.stickyNote"]
    x0 = min(k["position"][0] for k in knoten)
    y0 = min(k["position"][1] for k in ablauf["nodes"])
    hoehe = 40 + 22 * len(zeilen)
    ablauf["nodes"].append({
        "parameters": {"content": "## " + titel + "\n" + "\n".join(zeilen),
                       "height": hoehe, "width": 1150, "color": 2},
        "id": str(uuid4()), "name": NAME,
        "type": "n8n-nodes-base.stickyNote", "typeVersion": 1,
        "position": [x0, y0 - hoehe - 80],
    })
    return ablauf


def einspielen(ablauf: dict) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(ablauf, f, ensure_ascii=False, indent=2)
        pfad = f.name
    text = Path(pfad).read_text(encoding="utf-8")
    subprocess.run(["ssh", "-F", CFG, "-o", "BatchMode=yes", "ai-server",
                    "pct exec %s -- bash -c 'cat > /tmp/w-neu.json'" % CT],
                   input=text, text=True, check=True)
    ssh("pct exec %s -- bash -lc 'docker cp /tmp/w-neu.json n8n:/tmp/ >/dev/null && "
        "docker exec -u node n8n n8n import:workflow --input=/tmp/w-neu.json'" % CT)


def main() -> int:
    trocken = "--trocken" in sys.argv
    for kennung, titel, zeilen in LISTE:
        try:
            ablauf = notieren(holen(kennung), titel, zeilen)
        except Exception as grund:  # noqa: BLE001
            print(f"  FEHLER {kennung}: {grund}")
            continue
        zustand = f"aktiv={ablauf.get('active')} archiviert={ablauf.get('isArchived')}"
        print(f"  {kennung:38s} {ablauf.get('name')[:36]:38s} {zustand}")
        if not trocken:
            einspielen(ablauf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
