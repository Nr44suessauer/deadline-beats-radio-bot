#!/usr/bin/env python3
"""Writes German texts correctly in the n8n interface (umlauts instead of ae/oe/ue).

The producer has written the labels in ASCII so far ("Pruefen",
"running", "for"). This tool only revises the **visible texts**:

 * Notes (frame): parameters.content
 * Node labels: name (references "node"/$('Name') are included)
 * Subtitles: notes

Parameters (code, prompts, addresses) and everything that looks like
a file or command name will remain untouched (protection list below) — "n8n-oberflaeche.html",
"--cleanup", "anordnung-check.py" and "HANDBUCH.md" therefore remain as
they are.

Call:
  python3 german-texts.py --listen  file.json [weitere ...]
  python3 german-texts.py --anwenden file.json [weitere ...] \
 [--rename-file /tmp/rename.txt]

--listen only shows which words are not yet in the table (for
completion). --anwenden writes the files back and places (for the agent)
the "Old=New" list of renamed nodes, which the patcher needs.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

# ---------------------------------------------------------------- Word table
W = {
    "Eingaenge": "Inputs", "eingaenge": "inputs",
    "Ablaeufe": "Processes", "workflows": "processes",
    "Vorschlaege": "Suggestions", "vorschlaege": "suggestions",
    "Vorschlaegen": "Suggestions", "vorschlaegen": "suggestions",
    "running": "runs", "Laeuft": "Runs",
    "change": "change", "Aendern": "Change", "aendert": "changes", "Aendert": "Changes",
    "aenderung": "change", "Aenderung": "Change", "Aenderungen": "Changes",
    "Prueflauf": "Test run", "prueflauf": "Test run",
    "later": "later", "Spaeter": "Later",
    "traegt": "carries", "Traegt": "Carries",
    "haengt": "hangs", "Haengt": "Hangs", "haengen": "hang", "Haengen": "Hang",
    "choose": "choose", "Waehlen": "Choose", "chooses": "chooses", "waehle": "choose",
    "Naechster": "Next", "naechster": "next", "next": "next", "next": "next",
    "taete": "would do",
    "ausdruecklicher": "explicit", "ausdruecklich": "explicitly", "Ausdruecklich": "Explicitly",
    "genuegt": "suffices", "Genuegt": "Suffices",
    "zurueck": "back", "Zurueck": "Back", "zurueckgeben": "return",
    "Rueckgabe": "Return", "Callback": "Feedback", "FollowUp": "Follow-up",
    "key": "Key", "key": "key",
    "buttons": "Buttons", "Knoepfen": "buttons", "Knopfdruecke": "Button presses",
    "Zuhoerer": "Listeners", "zuhoerer": "listeners",
    "Anlaeufe": "Attempts", "anlaeufe": "attempts",
    "Zaehlt": "Counts", "zaehlt": "counts", "zaehlen": "count", "Zaehler": "Counter",
    "Rundenzaehler": "Round counter",
    "confirmed": "confirmed", "Bestaetigt": "Confirmed", "bestaetigen": "confirm",
    "Bestaetigung": "Confirmation",
    "ausfuehren": "execute", "Ausfuehren": "Execute", "ausfuehrt": "executes",
    "run": "Execution", "runs": "Executions",
    "check": "check", "Pruefen": "Check", "checks": "checks", "Prueft": "Checks",
    "Check": "Check", "Pruefungen": "Checks",
    "Ueberblick": "Overview", "overview": "overview",
    "overview": "Overview", "uebersicht": "overview",
    "over": "about", "Ueber": "About",
    "for": "for", "Fuer": "For",
    "clean_up": "clean up", "Saeubern": "Clean up", "saeubert": "cleans",
    "wuerde": "would", "wuerden": "would",
    "Koerper": "Body", "body": "body",
    "possible": "possible", "Moeglich": "Possible", "if possible": "as much as possible",
    "UI": "interface", "oberflaeche": "interface",
    "zusaetzlich": "additional", "zusaetzliche": "additional",
    "waehrend": "during", "unabhaengig": "independent",
    "aussen": "outside", "Aussen": "Outside",
    "gross": "large", "Grosse": "Large", "groesser": "larger",
    "schliessen": "close", "Schliessen": "Close",
    "means": "means", "Laenge": "Length", "laenge": "length",
    "Auffaellig": "Noticeable",
    "Abkuerzungen": "Abbreviations",
    "Geaendert": "Changed", "changed": "changed",
    "Gehoert": "Belongs", "gehoert": "belongs",
    "erklaert": "explained", "Erklaert": "Explained",
}

# Correct German words that accidentally contain "ue" — do not touch
IGNORE = {
    "Manuell", "manuell", "source", "sources", "sources", "Steuern", "steuern",
    "Control", "Steuerbefehle", "Steuerungen", "build", "Bauen", "new", "new",
    "neues", "Neues", "new", "neuem", "neuere", "neueren", "duration", "duration",
    "first", "Zuerst", "true", "Bauer", "Feuer", "deuten", "heute", "Leute",
}

# What is never replaced (filenames, commands, identifiers)
SCHUTZ = [
    "n8n-oberflaeche", "FAEHIGKEITEN", "STOERUNGEN", "anordnung-check",
    "code-check", "--cleanup", "cleanup", "ausfuehrungen.sh",
    "import-agent-vorbereiten", "agent-wf-build", "pruefsumme",
]

MUSTER = re.compile(r"[A-Za-zÄÖÜäöüß]*(?:ae|oe|ue)[A-Za-zÄÖÜäöüß]*")


def schuetzen(text: str) -> tuple[str, dict[str, str]]:
    """Replace filenames/commands with placeholders (only for editing)."""
    karte: dict[str, str] = {}
    for i, word in enumerate(SCHUTZ):
        platz = f"@@{i}@@"
        if word in text:
            text = text.replace(word, platz)
            karte[platz] = word
    # everything that looks like a filename
    def filename(m):
        platz = f"@@d{len(karte)}@@"
        karte[platz] = m.group(0)
        return platz

    text = re.sub(r"\S+\.(?:py|sh|json|md|html|service|yml|yaml|txt)\b", filename, text)
    # Identifiers with underscore (what_runs, search_title ...)
    def identifier(m):
        platz = f"@@k{len(karte)}@@"
        karte[platz] = m.group(0)
        return platz

    text = re.sub(r"\b\w+_\w+\b", identifier, text)
    return text, karte


def entschuetzen(text: str, karte: dict[str, str]) -> str:
    # Placeholders can be nested (@@d1@@ -> "@@0@@.html"),
    # therefore iterate multiple times until nothing changes anymore.
    for _ in range(8):
        before = text
        for platz, word in karte.items():
            text = text.replace(platz, word)
        if text == before:
            break
    return text


def waende(text: str, list: list[str]) -> str:
    text, karte = schuetzen(text)
    for word, ersatz in W.items():
        text = re.sub(rf"\b{re.escape(word)}\b", ersatz, text)
    if list is not None:
        for m in MUSTER.finditer(text):
            word = m.group(0)
            if word not in W and word not in IGNORE:
                list.append(word)
    return entschuetzen(text, karte)


# small, explicit character area corrections
# Set nodes to clear column spacing (measured in the browser): the frames
# should cleanly frame the nodes including their labels. A node
# occupied 96x96, including the label (192 wide) - therefore 24 px margin.
UMSTELLEN = {
    "bjFSfXGqpLg7AAXw": {
        "Manuell": [-660, -140], "Formular": [-660, 40], "Webhook": [-660, 260],
        "Felder": [-408, 40], "Now running": [-208, 40], "Recherche": [-8, 40],
        "Moderationstext": [240, 40], "Clean text": [440, 40],
        "voice": [640, 40], "Filename": [840, 40],
        "Modus": [1088, 40], "Live speaking": [1308, -15], "Hochladen": [1308, 160],
        "Warten": [1556, 160], "Find title": [1748, 160], "Zuordnen": [1956, 160],
        "Place wish": [2148, 160], "Answer": [2356, 40],
        "Select hits": [780, 1056],
    },
}
# Redraw frame: Position and size absolute (all measured in browser;
# Label block = NodeX-48 .. NodeX+144, bottom edge = NodeY+143).
RAHMEN = {
    "bjFSfXGqpLg7AAXw": {
        "Note input": [-732, -300, 240, 743],
        "Note Context": [-480, -72, 640, 295],
        "Note Text and Voice": [168, -48, 840, 255],
        "Note Output": [1016, -151, 460, 478],
        "Note Tracking": [1484, -40, 1040, 367],
        "Note Old Tools": [708, 908, 240, 315],
        "Documentation Note": [-732, -496, 1150, 172],
    },
}
HOEHEN = {  # Identifier -> {Notizname: new height}
    "Configuration": {"Documentation Note": 172},
}


def bearbeite(workflow: dict, list: list[str]) -> set[str]:
    changed: set[str] = set()
    for k in workflow["nodes"]:
        if "stickyNote" in k["type"]:
            alt = k.get("parameters", {}).get("content", "")
            new = waende(alt, list)
            k["parameters"]["content"] = new
        if k.get("notes"):
            k["notes"] = waende(k["notes"], list)
        neuer_name = waende(k["name"], list)
        if neuer_name != k["name"]:
            changed.add(k["name"])
            k["name"] = neuer_name
    if changed:
        # Follow references (connections and expressions)
        text = json.dumps(workflow, ensure_ascii=False)
        for alt in changed:
            new = waende(alt, [])
            text = text.replace(f'"{alt}":', f'"{new}":')          # Source key (connections/pinData)
            text = text.replace(f'"node": "{alt}"', f'"node": "{new}"')  # Target in connections
            text = text.replace(f"$('{alt}')", f"$('{new}')")
            text = text.replace(f'$("{alt}")', f'$("{new}")')
        ersetzt = json.loads(text)
        workflow.clear()
        workflow.update(ersetzt)
    for name, pos in UMSTELLEN.get(workflow.get("id"), {}).items():
        for k in workflow["nodes"]:
            if k["name"] == name:
                k["position"] = list(pos)
    for name, kasten in RAHMEN.get(workflow.get("id"), {}).items():
        for k in workflow["nodes"]:
            if "stickyNote" in k["type"] and k["name"] == name:
                k["position"] = [kasten[0], kasten[1]]
                k["parameters"]["width"] = kasten[2]
                k["parameters"]["height"] = kasten[3]
    for name, height in HOEHEN.get(workflow.get("id"), {}).items():
        for k in workflow["nodes"]:
            if "stickyNote" in k["type"] and k["name"] == name:
                k["parameters"]["height"] = height
    return changed


def main() -> int:
    z = argparse.ArgumentParser()
    z.add_argument("--listen", action="store_true")
    z.add_argument("--anwenden", action="store_true")
    z.add_argument("--rename-file", default="")
    z.add_argument("dateien", nargs="+")
    a = z.parse_args()
    list: list[str] = []
    umbenannt: list[str] = []
    for path in a.dateien:
        data = json.loads(open(path, encoding="utf-8").read())
        flach = data if isinstance(data, list) else [data]
        for workflow in flach:
            changed = bearbeite(workflow, list)
            if a.anwenden and changed:
                print(f"  {workflow.get('name')}: {sorted(changed)}")
            if a.anwenden and workflow.get("id") == "RadioAgentBot":
                for alt in sorted(changed):
                    umbenannt.append(f"{alt}={waende(alt, [])}")
        if a.anwenden:
            open(path, "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False, indent=2))
    if a.umbenennen_datei:
        open(a.umbenennen_datei, "w", encoding="utf-8").write(",".join(umbenannt))
        print("Renamings:", len(umbenannt), "->", a.umbenennen_datei)
    if list:
        from_ = sorted(set(list))
        print(f"{len(from_)} word forms still without rule:")
        for w in from_:
            print("   ", w)
        return 1
    print("Done — all word forms are covered." if a.listen else "Fertig.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
