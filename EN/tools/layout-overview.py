#!/usr/bin/env python3
"""Writes an overview of the character surface of an n8n workflow.

With this, the arrangement is documented not only on the surface, but also black on white
documented: for each frame the heading and description, below the nodes with
their label and position.

Call:
    python3 layout-overview.py <workflow.json> [weitere.json ...] [-o file.md]
Without -o the overview goes to stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def as_workflow(data):
    return data[0] if isinstance(data, list) else data


def areas(workflow):
    """[(Frame node, [Nodes])] - Assignment via the position in the rectangle."""
    frames = [k for k in workflow["nodes"] if "stickyNote" in k["type"]]
    nodes = [k for k in workflow["nodes"] if "stickyNote" not in k["type"]]
    result = []
    for r in frames:
        rx, ry = r["position"]
        rb, rh = r["parameters"].get("width", 0), r["parameters"].get("height", 0)
        inside = [k for k in nodes
                if rx <= k["position"][0] + 60 <= rx + rb
                and ry <= k["position"][1] + 50 <= ry + rh]
        result.append((r, inside))
    return result


def uebersicht(path: Path) -> str:
    workflow = as_workflow(json.loads(path.read_text(encoding="utf-8")))
    lines = [f"## {workflow.get('name', path.stem)}", ""]
    nodes = [k for k in workflow["nodes"] if "stickyNote" not in k["type"]]
    frames = [k for k in workflow["nodes"] if "stickyNote" in k["type"]]
    lines.append(f"{len(nodes)} nodes in {len(frames)} frames."
                  f"Each node carries its explanation as a note under the name.")
    lines.append("")
    for r, inside in areas(workflow):
        inhalt = str(r["parameters"].get("content", "")).strip().splitlines()
        kopf = inhalt[0].lstrip("# ").strip() if inhalt else r["name"]
        text = " ".join(z.strip() for z in inhalt[1:] if z.strip())
        lines.append(f"### {kopf}  ·  `{r['name']}`")
        if text:
            lines.append("")
            lines.append(text.replace("**", "**"))
        lines.append("")
        if not inside:
            lines.append("*(Overview box without nodes)*")
            lines.append("")
            continue
        lines.append("| Node | Explanation (note at the node) | Position |")
        lines.append("| --- | --- | --- |")
        for k in sorted(inside, key=lambda k: (k["position"][0], k["position"][1])):
            notiz = str(k.get("notes", "")).replace("|", "\\|").strip() or "—"
            sichtbar = "" if k.get("notesInFlow") else " (only in the note field)"
            lines.append(f"| `{k['name']}` | {notiz}{sichtbar} |"
                          f"{k['position'][0]}, {k['position'][1]} |")
        lines.append("")
    without = [k for k in nodes
               if not any(k in inside for _, inside in areas(workflow))]
    if without:
        lines.append("### Without frame")
        lines.append("")
        lines.append(", ".join(f"`{k['name']}`" for k in without))
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dateien", nargs="+")
    parser.add_argument("-o", "--output", default="")
    args = parser.parse_args()

    teile = [uebersicht(Path(d)) for d in args.dateien]
    text = "\n".join(teile)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"written: {args.output} ({len(text)} characters)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
