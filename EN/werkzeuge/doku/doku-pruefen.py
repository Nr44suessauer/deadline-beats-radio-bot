#!/usr/bin/env python3
"""Checks the document collection for solid errors (without network).

Usage:  python3 EN/werkzeuge/doku/doku-pruefen.py [--leise]

Checked are (German and English, all .md files):
 1. Section numbers: duplicate or out-of-sequence `## N.`-titles
 2. Code blocks: odd number of ```-fences
 3. Mermaid: labels with parentheses without quotes
 (leads to empty diagrams on GitHub/VS Code)
 4. References: `](target.md)` / `](target/)` must exist as files
 5. Duplicate headings directly one after another
 6. Files missing in the appendix table of contents (only notice)

Return value: 0 = clean, 1 = findings.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

QUELLE = Path(__file__).resolve().parent.parent.parent          # the project folder
QUELLEN = [QUELLE]
OHNE = {"DocOfficial", ".git", "__pycache__", "node_modules"}

NUMMER = re.compile(r"^(#{2,4})\s+(\d+(?:\.\d+)*)\.?\s+(.*)$")
VERWEIS = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)\s]*)?\)")
MERMAID_KLAMMER = re.compile(r"(\||\[|-->)\s*[A-Za-z0-9_]*\[?[^\"\'\]\n|]*\([^)\n]*\)")


def wurzel_von(p: Path) -> Path:
    """Root a file belongs to."""
    return next(w for w in QUELLEN if p.is_relative_to(w))


def dateien() -> list[Path]:
    all = []
    for wurzel in QUELLEN:
        for p in wurzel.rglob("*.md"):
            if any(teil in OHNE for teil in p.relative_to(wurzel).parts):
                continue
            all.append(p)
    return sorted(all)


def blocks(text: str, voice: str) -> list[list[str]]:
    """Code blocks of a language (```language … ```) including start-/end line."""
    hits: list[list[str]] = []
    open: tuple[str, int, list[str] | None] | None = None
    for nr, zeile in enumerate(text.splitlines(), start=1):
        streifen = zeile.strip()
        if streifen.startswith("```"):
            identifier = streifen[3:].strip().split()[0].lower() if streifen[3:].strip() else ""
            if open is None:
                entry = [f"{nr}:?", ""] if identifier == voice else None
                open = (identifier, nr, entry)
            else:
                if open[2] is not None:
                    open[2][0] = f"{open[1]}:{nr}"
                    hits.append(open[2])
                open = None
        elif open is not None and open[2] is not None:
            open[2][1] += zeile + "\n"
    return hits


def check(path: Path) -> tuple[list[str], list[str]]:
    befunde: list[str] = []
    hints: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    wurzel = wurzel_von(path)
    rel = path.relative_to(wurzel)

    # 1) Section numbers
    seen: dict[str, int] = {}
    for nr, zeile in enumerate(text.splitlines(), start=1):
        m = NUMMER.match(zeile.strip())
        if not m:
            continue
        nummer, title = m.group(2), m.group(3).strip()
        if nummer in seen:
            befunde.append(f"{rel}:{nr}: Number {nummer} duplicated (already seen on line {seen[nummer]}) — „{title}“")
        seen[nummer] = nr

    # 2) Code fences
    zaeune = sum(1 for z in text.splitlines() if z.strip().startswith("```"))
    if zaeune % 2:
        befunde.append(f"{rel}: odd number of code fences ({zaeune}) — one ``` is missing")

    # 3) Mermaid labels (only flow diagrams: there parentheses without quotes
    # break the drawing; state/action diagrams
    # tolerate them in text after colon without problems).
    for area, inhalt in blocks(text, "mermaid"):
        start = int(area.split(":")[0])
        kopf = next((z.strip() for z in inhalt.splitlines() if z.strip() and not z.strip().startswith("%%")), "")
        if not kopf.startswith(("graph", "flowchart")):
            continue
        for nr, zeile in enumerate(inhalt.splitlines(), start=start):
            if MERMAID_KLAMMER.search(zeile) and '"' not in zeile and ("|" in zeile or "[" in zeile):
                befunde.append(f"{rel}:{nr}: Mermaid label with parentheses without \"…\" → {zeile.strip()[:70]}")

    # 4) References to files
    for nr, zeile in enumerate(text.splitlines(), start=1):
        for target in VERWEIS.findall(zeile):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            zielpfad = (path.parent / target).resolve()
            if not zielpfad.exists():
                befunde.append(f"{rel}:{nr}: Reference points into void → {target}")

    # 5) Same heading twice in a row
    lines = [z.strip() for z in text.splitlines()]
    for i in range(1, len(lines)):
        if lines[i].startswith("#") and lines[i] == lines[i - 1]:
            befunde.append(f"{rel}:{i + 1}: Heading duplicated → {lines[i][:60]}")

    # 6) Notice: File not in appendix table of contents
    anhang = wurzel / "ANHANG" / "README.md"
    if path.parent == wurzel and path.suffix == ".md" and path.name not in {"README.md"} and anhang.exists():
        if path.name not in anhang.read_text(encoding="utf-8"):
            hints.append(f"{rel}: not listed in ANHANG/README.md")

    return befunde, hints


def main() -> int:
    leise = "--leise" in sys.argv
    alle_befunde: list[str] = []
    alle_hinweise: list[str] = []
    list = dateien()
    for p in list:
        b, h = check(p)
        alle_befunde += b
        alle_hinweise += h

    if alle_befunde:
        print(f"Findings ({len(alle_befunde)}) in {len(list)} files:")
        for b in alle_befunde:
            print("  ✗", b)
    if alle_hinweise and not leise:
        print(f"\nNotes ({len(alle_hinweise)}):")
        for h in alle_hinweise:
            print("  ·", h)
    if not alle_befunde:
        print(f"✓ clean — {len(list)} files checked, no findings.")
    return 1 if alle_befunde else 0


if __name__ == "__main__":
    sys.exit(main())
