#!/usr/bin/env python3
"""Inserts the list tasks into the running bot process (surgically).

Why no complete rebuild: the producer sets at the six tool nodes
the field "name" (search_title, ...), the running version does not have it. A
rebuild would change the tool names compared to the model - that does not belong
to this extension. Therefore, here ONLY the new nodes, the changed
input, the connections and the positions are taken over; everything else remains
identical to the running version.

Call:
    python3 13-listen-patchen.py <running.json> <rebuild.json> <output.json>
"""
import copy
import json
import re
import sys

# The new nodes along with sticky note - exactly these are inserted.
NEU = ["List Type", "Lists?", "List Service", "List Response", "List Send",
       "Note Lists"]

# Existing nodes whose position shifts (space for the new row).
VERSCHOBEN = ["Access", "Released?", "Text there?", "Job", "No access",
              "No text", "Send (short message)"]

# Existing nodes with new content.
GEAENDERT = ["Input"]

# Connections that are set anew.
NEUE_KANTEN = ["Released?", "List Type", "Lists?", "List Service", "List Response"]


def as_workflow(data):
    return data[0] if isinstance(data, list) else data


def targets(workflow):
    """All node names that appear as connection targets."""
    names = set()
    for source in (workflow.get("connections") or {}).values():
        for zweig in source.values():
            for gruppe in zweig:
                for kante in gruppe or []:
                    names.add(kante["node"])
    return names


def main() -> int:
    laufend_datei, gebaut_datei, ziel_datei = sys.argv[1:4]
    laufend_text = open(laufend_datei, encoding="utf-8").read()
    gebaut = as_workflow(json.load(open(gebaut_datei, encoding="utf-8")))
    new = copy.deepcopy(as_workflow(json.loads(laufend_text)))

    identifier = (re.search(r"api\.telegram\.org/bot([A-Za-z0-9:_-]+)/", laufend_text) or [None, ""])[1]
    key = re.search(r"[0-9a-f]{16}:[0-9a-f]{32}", laufend_text)
    key = key.group(0) if key else ""
    if not identifier or not key:
        print("ERROR: Telegram identifier or interface key not found")
        return 1

    namen_laufend = [k["name"] for k in new["nodes"]]
    schon_da = [n for n in NEU if n in namen_laufend]

    gebaut_nach_name = {k["name"]: k for k in gebaut["nodes"]}
    missing = [n for n in NEU + GEAENDERT if n not in gebaut_nach_name]
    if missing:
        print(f"ERROR: in rebuild missing: {missing}")
        return 1

    # 1) insert new nodes - or, if already present, bring to the state of
    # the rebuild (the call is thus repeatable).
    if schon_da:
        for name in NEU:
            target = [k for k in new["nodes"] if k["name"] == name][0]
            target["parameters"] = copy.deepcopy(gebaut_nach_name[name]["parameters"])
            target["notes"] = gebaut_nach_name[name].get("notes", target.get("notes"))
            target["notesInFlow"] = gebaut_nach_name[name].get("notesInFlow", target.get("notesInFlow"))
        print(f"Nodes already present - content updated: {schon_da}")
    else:
        for name in NEU:
            new["nodes"].append(copy.deepcopy(gebaut_nach_name[name]))

    # 2) take over positions of moved nodes
    for nodes in new["nodes"]:
        if nodes["name"] in VERSCHOBEN:
            nodes["position"] = list(gebaut_nach_name[nodes["name"]]["position"])

    # 3) changed nodes: only the content, everything else remains
    for name in GEAENDERT:
        source = gebaut_nach_name[name]
        target = [k for k in new["nodes"] if k["name"] == name][0]
        for feld, wert in source["parameters"].items():
            target["parameters"][feld] = copy.deepcopy(wert)

    # 4) connections
    verbindungen = new["connections"]
    for name in NEUE_KANTEN:
        verbindungen[name] = copy.deepcopy(gebaut["connections"][name])

    # ---------------------------------------------------------------- Checks
    error = []
    ausgabe_text = json.dumps(new, ensure_ascii=False, indent=2)
    if "<SECRET>" in ausgabe_text:
        error.append("Masked marker <SECRET> in result")
    if identifier and identifier not in ausgabe_text:
        error.append("Telegram identifier missing in result")
    if key and key not in ausgabe_text:
        error.append("Interface key missing in result")

    namen_neu = {k["name"] for k in new["nodes"]}
    fehlende_ziele = sorted(targets(new) - namen_neu)
    if fehlende_ziele:
        error.append(f"Connection targets without node: {fehlende_ziele}")

    for name in NEU + GEAENDERT:
        if name not in namen_neu:
            error.append(f"Node missing: {name}")

    erwartete_zahl = len([k["name"] for k in as_workflow(json.loads(laufend_text))["nodes"]])
    zuwachs = len(NEU) if not schon_da else 0
    if len(namen_neu) != erwartete_zahl + zuwachs:
        error.append(f"Node count does not match: {len(namen_neu)} instead of"
                      f"{erwartete_zahl + zuwachs}")

    print(f"Nodes running: {erwartete_zahl}   after patching: {len(namen_neu)}")
    print(f"New: {NEU}")
    print("Moved:", VERSCHOBEN)
    print("Content new:", GEAENDERT)
    print("Connections set anew:", NEUE_KANTEN)
    if error:
        print("\nERROR - not written:")
        for f in error:
            print("  -", f)
        return 1

    with open(ziel_datei, "w", encoding="utf-8") as f:
        f.write(ausgabe_text)
    print(f"\nWritten: {ziel_datei}")
    print("Checked: no mask markers, identifier and key included,"
          "all connection targets present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
