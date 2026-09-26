#!/usr/bin/env python3
"""Adds to the Radio Bot's search tool the exclusion of the Live Archive.

The bot searches via the catalog service and the station interface. Both provide
file paths; the Live-/Bootleg recordings have been placed under
"_Archiv/" since the cleanup. This script patches the "Prepare hits" node so that such
hits are not even suggested.

Call:  python3 06-bot-filter.py <input.json> <output.json>
"""
import json
import sys

# Anchor: the loop that combines the hits from both sources.
ANKER = "for (const t of source('Smart search').concat(source('Station search'))) {"
ALT = " const path = t.path || '';\n  if (!path) continue;"
NEU = (
    " const path = t.path || '';\n"
    " if (!path) continue;\n"
    " // Live-/Bootleg recordings are in the archive and are never suggested.\n"
    " if (/^_Archiv\\//i.test(path)) continue;"
)


def main() -> int:
    source, target = sys.argv[1], sys.argv[2]
    data = json.load(open(source, encoding="utf-8"))
    workflow = data[0] if isinstance(data, list) else data

    changed = 0
    for nodes in workflow.get("nodes", []):
        code = nodes.get("parameters", {}).get("jsCode")
        if not code or ANKER not in code:
            continue
        if "_Archiv" in code:
            print(f"Node ’{nodes['name']}’: Filter already exists")
            changed += 1
            continue
        if code.count(ALT) != 1:
            print(f"ERROR: Anchor {code.count(ALT)}x found - aborting")
            return 1
        nodes["parameters"]["jsCode"] = code.replace(ALT, NEU)
        print(f"Node ’{nodes['name']}’: Archive filter inserted")
        changed += 1

    if not changed:
        print("ERROR: no matching node found - aborting")
        return 1

    with open(target, "w", encoding="utf-8") as f:
        json.dump([workflow], f, ensure_ascii=False, indent=2)
    print(f"written: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
