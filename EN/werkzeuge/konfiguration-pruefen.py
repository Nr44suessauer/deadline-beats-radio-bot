#!/usr/bin/env python3
"""Checks the central configuration in the generated workflows.

Five checks without which an import into n8n can fail silently:

 1. Node names unique (n8n rejects duplicate names).
 2. Every reference "$('Node')" points to an existing node.
 3. No expression contains nested "{{ ... }}" (n8n cannot read that).
 4. Every node that needs values from the configuration is reachable from node
    "Configuration" (otherwise it finds nothing at runtime).
 5. No credentials remain in the bot and tools (only in the configuration).

Usage:  python3 konfiguration-check.py [folder-with-the-json]
"""
import json
import os
import re
import sys

ORDNER = sys.argv[1] if len(sys.argv) > 1 else "/tmp"
DATEIEN = ["radio-konfiguration.json", "radio-werkzeuge.json", "radio-agent.json"]
KNOTEN = "Configuration"


def lade(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return d if isinstance(d, list) else [d]


def text_von(obj):
    return json.dumps(obj, ensure_ascii=False)


def nachfolger(workflow, name):
    """All direct targets of a node — across ALL connection types.

    Important: the agent's tool nodes are not attached to "main", but to
    "ai_tool". Anyone following only "main" wrongly considers them unreachable.
    """
    targets = []
    for type, zweige in (workflow["connections"].get(name) or {}).items():
        for zweig in zweige or []:
            for z in zweig or []:
                targets.append(z.get("node"))
    return [z for z in targets if z]


def erreichbar(workflow, start):
    """All nodes reachable from 'start' via connections."""
    seen, stapel = set(), [start]
    while stapel:
        n = stapel.pop()
        if n in seen:
            continue
        seen.add(n)
        stapel.extend(nachfolger(workflow, n))
    return seen


def ist_unterknoten(workflow, name):
    """Model or tool nodes of the agent.

    Note: these nodes are the SOURCE of an ai_* connection and point to the
    agent — so they lie before it, not behind it. That is exactly why the
    reachability check cannot see them; whether n8n resolves their expressions
    must be shown by a test run.
    """
    return any(type.startswith("ai_") for type in (workflow["connections"].get(name) or {}))


def main():
    found, error = 0, []
    for file in DATEIEN:
        path = os.path.join(ORDNER, file)
        if not os.path.exists(path):
            print("   missing:", path)
            continue
        for workflow in lade(path):
            name = workflow.get("name")
            nodes = workflow["nodes"]
            names = [k["name"] for k in nodes]
            print(f"== {name} ({len(names)} nodes)")

            # 1) unique names
            doppelt = {n for n in names if names.count(n) > 1}
            if doppelt:
                error.append(f"{name}: duplicate node names {sorted(doppelt)}")

            # 2) references and 3) nested expressions
            ganze = text_von(workflow)
            for verweis in set(re.findall(r"\$\('([^']+)'\)", ganze)):
                if verweis not in names:
                    error.append(f"{name}: reference to missing node ’{verweis}’")
            for k in nodes:
                for feld, wert in durchsuchen(k.get("parameters", {})):
                    s = str(wert)
                    if s.startswith("="):
                        # Whole expression: the body must not contain "{{ ... }}",
                        # otherwise two expressions are nested (n8n cannot do that).
                        body = s[2:-2] if s.endswith("}}") else s[2:]
                        if "{{" in body:
                            error.append(f"{name}/{k['name']}: nested expression in {feld}: "
                                          f"{body[:90]}")

            # 4) reachability
            if workflow.get("id") == KNOTEN:
                print("   (this is the hub itself — no call needed)")
            elif KNOTEN in names:
                erreichbar_von_konfig = erreichbar(workflow, KNOTEN)
                braucher = [k["name"] for k in nodes
                            if f"$('{KNOTEN}')" in text_von(k.get("parameters", {}))]
                weit = [b for b in braucher if b not in erreichbar_von_konfig]
                unterknoten = [b for b in weit if ist_unterknoten(workflow, b)]
                echt_weit = [b for b in weit if b not in unterknoten]
                if echt_weit:
                    error.append(f"{name}: need the values but are not reachable: {echt_weit}")
                print(f"   Configuration: {len(braucher)} nodes fetch values, "
                      f"{len(braucher) - len(weit)} safely reachable, "
                      f"{len(unterknoten)} as model/tool nodes (check in a test run)")
                found += 1
            else:
                error.append(f"{name}: node ’{KNOTEN}’ is missing")

    # 5) no credentials outside the configuration
    konfig_pfad = os.path.join(ORDNER, "radio-konfiguration.json")
    if os.path.exists(konfig_pfad):
        js = json.dumps(lade(konfig_pfad), ensure_ascii=False)
        geheim = re.findall(r'"(?:key|token)":\s*"([^"]{8,})"', js)
        # Addresses too belong only in the hub — otherwise a changeover fails
        # silently (as happened on 2026-09-22: "Fetch news items" kept the
        # fixed address because it was set again further down in the builder).
        adressen = [a for a in re.findall(r'"adresse":\s*"(https?://[^"]+)"', js)
                    if len(a) > 12]
        for file in ["radio-werkzeuge.json", "radio-agent.json"]:
            path = os.path.join(ORDNER, file)
            if not os.path.exists(path):
                continue
            inhalt = open(path, encoding="utf-8").read()
            open = [g[:6] + "..." for g in geheim if g in inhalt]
            open += [a for a in adressen if a in inhalt]
            if open:
                error.append(f"{file}: values outside the configuration: {open}")
            else:
                print(f"   {file}: no credentials contained")

    print()
    if error:
        print("FINDINGS (%d):" % len(error))
        for f in error:
            print("  -", f)
        raise SystemExit(1)
    print("Everything is in order.")


def durchsuchen(obj, weg=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from durchsuchen(v, f"{weg}.{k}" if weg else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from durchsuchen(v, f"{weg}[{i}]")
    else:
        yield weg, obj


if __name__ == "__main__":
    main()
