#!/usr/bin/env python3
"""Takes changes from the producer into the **running** radio schedule.

Why not simply rebuild: the producer sets at the six tool nodes the
field `name` (title_search and so on), which the running version does not have. A
complete rebuild would change the tool names compared to the model.
This tool therefore only takes what is explicitly mentioned:

 * new nodes (in the rebuild, but not running),
 * renamed nodes with connections and `$('Name')` references,
 * the contents (parameters) of the named nodes,
 * all positions and the entire connection image from the plan,
 * new emergency notes.

Access values, identifiers, login data and the parameters of all other nodes
remain **character identical** to the running version.

Call:
    python3 agent-patch.py <running.json> <rebuild.json> <output.json> \
 [--new Node1,Node2] [--content Node3] [--rename "Old=New,Old2=New2"]
 [--dry-run]

Without --new all additional nodes in the rebuild will be taken over.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys


def as_workflow(data):
    return data[0] if isinstance(data, list) else data


def targets(workflow) -> set[str]:
    names: set[str] = set()
    for source in (workflow.get("connections") or {}).values():
        for zweig in source.values():
            for gruppe in zweig:
                for kante in gruppe or []:
                    names.add(kante["node"])
    return names


def core(path: str, extra: str = "") -> tuple[dict, str, str]:
    text = open(path, encoding="utf-8").read()
    # The access values can be in a second file (since the refactoring
    # on 22.09.2026 in the schedule "Configuration - all values").
    total = text + extra
    identifier = (re.search(r"([0-9]{6,12}:[A-Za-z0-9_-]{33,})", total) or [None, ""])[1]
    key = re.search(r"[0-9a-f]{16}:[0-9a-f]{32}", total)
    return as_workflow(json.loads(text)), identifier, (key.group(0) if key else "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("running")
    parser.add_argument("rebuild")
    parser.add_argument("output")
    parser.add_argument("--new", default="")
    parser.add_argument("--content", default="")
    parser.add_argument("--rename", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cleanup", action="store_true",
                          help="Positions, notes and frames completely taken from the plan")
    args = parser.parse_args()

    extra = ""
    if os.environ.get("CONFIG_RUNNING"):
        extra = open(os.environ["CONFIG_RUNNING"], encoding="utf-8").read()
    running, identifier, key = core(args.running, extra)
    gebaut, _, _ = core(args.rebuild, extra)
    if not identifier or not key:
        print("ERROR: Telegram identifier or interface key not found"
              "(Agent and configuration checked)")
        return 1

    new_data = copy.deepcopy(running)
    rename = {}
    for couple in filter(None, (p.strip() for p in args.rename.split(","))):
        alt, _, target = couple.partition("=")
        rename[alt.strip()] = target.strip()

    # ------------------------------------------------------------ 1) Rename
    if rename:
        namen_jetzt = {k["name"] for k in new_data["nodes"]}
        # Repeatable: pairs whose target already exists (Old gone, New there), are
        # already done and will be skipped.
        already = sorted(a for a, z in rename.items()
                       if a not in namen_jetzt and z in namen_jetzt)
        for a in already:
            del rename[a]
        if already:
            print(f" already renamed (skipped): {already}")
        missing = [a for a in rename if a not in namen_jetzt]
        if missing:
            print(f"ERROR: not present, cannot be renamed: {missing}")
            return 1
        for nodes in new_data["nodes"]:
            if nodes["name"] in rename:
                nodes["name"] = rename[nodes["name"]]
        # Trace references in connections and expressions (the connections
        # come later anyway from the plan, the expressions remain running).
        text = json.dumps(new_data, ensure_ascii=False)
        for alt, target in rename.items():
            text = text.replace(f'"node": "{alt}"', f'"node": "{target}"')
            text = text.replace(f"$('{alt}')", f"$('{target}')")
            text = text.replace(f'$("{alt}")', f'$("{target}")')
        new_data = json.loads(text)
        print(f"Renamed: {rename}")

    laufend_namen = {k["name"] for k in new_data["nodes"]}
    gebaut_nach = {k["name"]: k for k in gebaut["nodes"]}
    if args.cleanup:
        # Pure character surface: frames come completely from the plan (old gone),
        # note and visibility at each node as well. Contents, identifiers
        # and connections remain untouched.
        old = [k["name"] for k in new_data["nodes"] if "stickyNote" in k["type"]]
        new_data["nodes"] = [k for k in new_data["nodes"] if "stickyNote" not in k["type"]]
        for name in old:
            print(f" - old frame: {name}")
        for entry in gebaut["nodes"]:
            if "stickyNote" in entry["type"]:
                new_data["nodes"].append(copy.deepcopy(entry))
                print(f" + frame: {entry['name']}")
        changed = 0
        for nodes in new_data["nodes"]:
            source = gebaut_nach.get(nodes["name"])
            if not source:
                continue
            for feld in ("notes", "notesInFlow"):
                if feld in source and nodes.get(feld) != source[feld]:
                    nodes[feld] = copy.deepcopy(source[feld])
                    changed += 1
                elif feld not in source and feld in nodes:
                    del nodes[feld]
                    changed += 1
        print(f"  ~ label: {changed} Aenderung(en) an notes")

    # ------------------------------------------------------------ 2) new nodes
    nur_gebaut = [n for n in gebaut_nach if n not in laufend_namen]
    gewuenscht = [n.strip() for n in args.new.split(",") if n.strip()]
    einzufuegen = gewuenscht or nur_gebaut
    if args.cleanup:   # Frames already come above from the plan
        einzufuegen = [n for n in einzufuegen if "stickyNote" not in gebaut_nach[n]["type"]]
    unknown = [n for n in einzufuegen if n not in gebaut_nach]
    if unknown:
        print(f"ERROR: not present in rebuild: {unknown}")
        return 1
    schon_da = [n for n in einzufuegen if n in laufend_namen]
    if schon_da:
        print(f"Already present, only content: {schon_da}")
    for name in einzufuegen:
        if name not in laufend_namen:
            new_data["nodes"].append(copy.deepcopy(gebaut_nach[name]))
            print(f" {name} ({gebaut_nach[name]['type']})")

    # ------------------------------------------------- 3) Apply contents
    inhalt = [n.strip() for n in args.inhalt.split(",") if n.strip()]
    for name in inhalt:
        if name not in gebaut_nach:
            print(f"ERROR: Content requested, but not present in new build: {name}")
            return 1
        target = [k for k in new_data["nodes"] if k["name"] == name]
        if not target:
            print(f"ERROR: Missing node: {name}")
            return 1
        for feld, wert in gebaut_nach[name]["parameters"].items():
            target[0]["parameters"][feld] = copy.deepcopy(wert)
        for feld in ("notes", "notesInFlow"):
            if feld in gebaut_nach[name]:
                target[0][feld] = gebaut_nach[name][feld]
        print(f"  ~ Inhalt: {name}")

    # --------------------------------- 4) Positions and connections from the plan
    ohne_position = []
    for nodes in new_data["nodes"]:
        source = gebaut_nach.get(nodes["name"])
        if source and "position" in source:
            nodes["position"] = list(source["position"])
        elif "stickyNote" not in nodes["type"]:
            ohne_position.append(nodes["name"])
    if ohne_position:
        print(f"WARNING: No position in plan: {ohne_position}")
    new_data["connections"] = copy.deepcopy(gebaut["connections"])

    # --------------------------------------------------------------- 5) Check
    error = []
    text = json.dumps(new_data, ensure_ascii=False)
    if "<SECRET>" in text:
        error.append("Masked marker <SECRET> in result")
    # Since the rebuild to "Configuration - all values", identifier and
    # key are NO LONGER in the agent - a reference to them is sufficient.
    zentral = "$('Configuration')" in text
    if not zentral and identifier not in text:
        error.append("Telegram identifier missing in result")
    if not zentral and key not in text:
        error.append("Interface key missing in result")
    # Legacy: Field names and node names from earlier versions. During the rebuild
    # from "Lists ..." to "Service ..." a node expression was overlooked
    # (List Service continued to ask for listArt) - the button path led to nothing.
    altlasten = [word for word in ("listenArt", "$('Listen", 'List Type', 'Lists?',
                                   "Note Lists")
                 if word in text]
    if altlasten:
        error.append(f"Legacy from an earlier version: {altlasten}")

    eigene = {k["name"] for k in new_data["nodes"]}
    fehlende_ziele = sorted(targets(new_data) - eigene)
    if fehlende_ziele:
        error.append(f"Connection targets without node: {fehlende_ziele}")

    verloren = sorted(laufend_namen - eigene)
    if args.cleanup:
        # During cleanup, frames are repositioned - old sticky notes must
        # disappear (nodes with logic never).
        old_type = {k["name"]: k["type"] for k in running["nodes"]}
        verloren = [n for n in verloren if "stickyNote" not in old_type.get(n, "")]
    if verloren:
        error.append(f"Nodes would be lost: {verloren}")

    print(f"\n nodes active {len(running['nodes'])} -> after patching {len(new_data['nodes'])}")
    if error:
        print("ERROR - not written:")
        for f in error:
            print("  -", f)
        return 1
    if args.dry:
        print("Dry run: nothing written.")
        return 0
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump([new_data], f, ensure_ascii=False, indent=2)
    print(f"Written: {args.output}")
    print("Checked: no mask markers, identifier and key included,"
          "No nodes lost, all connection targets present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
