#!/usr/bin/env python3
"""Prüft die Dokumentsammlung auf handfeste Fehler (ohne Netz).

Aufruf:  python3 werkzeuge/doku/doku-pruefen.py [--leise]

Geprüft wird (deutsch und englisch, alle .md-Dateien):
  1. Abschnittsnummern: doppelte oder aus der Reihe laufende `## N.`-Titel
  2. Codeblöcke: ungerade Anzahl von ``` -Zäunen
  3. Mermaid: Beschriftungen mit Klammern ohne Anführungszeichen
     (führt bei GitHub/VS Code zu leeren Diagrammen)
  4. Verweise: `](ziel.md)` / `](ziel/)` müssen als Datei existieren
  5. Doppelte Überschriften direkt hintereinander
  6. Dateien, die im Inhaltsverzeichnis des ANHANG fehlen (nur Hinweis)

Rückgabe: 0 = sauber, 1 = Befunde.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

QUELLE = Path(__file__).resolve().parent.parent.parent          # der Projektordner
QUELLEN = [QUELLE]
OHNE = {"DocOfficial", ".git", "__pycache__", "node_modules"}

NUMMER = re.compile(r"^(#{2,4})\s+(\d+(?:\.\d+)*)\.?\s+(.*)$")
VERWEIS = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)\s]*)?\)")
MERMAID_KLAMMER = re.compile(r"(\||\[|-->)\s*[A-Za-z0-9_]*\[?[^\"\'\]\n|]*\([^)\n]*\)")


def wurzel_von(p: Path) -> Path:
    """Wurzel, zu der eine Datei gehoert."""
    return next(w for w in QUELLEN if p.is_relative_to(w))


def dateien() -> list[Path]:
    alle = []
    for wurzel in QUELLEN:
        for p in wurzel.rglob("*.md"):
            if any(teil in OHNE for teil in p.relative_to(wurzel).parts):
                continue
            alle.append(p)
    return sorted(alle)


def bloecke(text: str, sprache: str) -> list[list[str]]:
    """Codeblöcke einer Sprache (```sprache … ```) samt Start-/Endzeile."""
    treffer: list[list[str]] = []
    offen: tuple[str, int, list[str] | None] | None = None
    for nr, zeile in enumerate(text.splitlines(), start=1):
        streifen = zeile.strip()
        if streifen.startswith("```"):
            kennung = streifen[3:].strip().split()[0].lower() if streifen[3:].strip() else ""
            if offen is None:
                eintrag = [f"{nr}:?", ""] if kennung == sprache else None
                offen = (kennung, nr, eintrag)
            else:
                if offen[2] is not None:
                    offen[2][0] = f"{offen[1]}:{nr}"
                    treffer.append(offen[2])
                offen = None
        elif offen is not None and offen[2] is not None:
            offen[2][1] += zeile + "\n"
    return treffer


def pruefe(pfad: Path) -> tuple[list[str], list[str]]:
    befunde: list[str] = []
    hinweise: list[str] = []
    text = pfad.read_text(encoding="utf-8", errors="replace")
    wurzel = wurzel_von(pfad)
    rel = pfad.relative_to(wurzel)

    # 1) Abschnittsnummern
    gesehen: dict[str, int] = {}
    for nr, zeile in enumerate(text.splitlines(), start=1):
        m = NUMMER.match(zeile.strip())
        if not m:
            continue
        nummer, titel = m.group(2), m.group(3).strip()
        if nummer in gesehen:
            befunde.append(f"{rel}:{nr}: Nummer {nummer} doppelt (schon in Zeile {gesehen[nummer]}) — „{titel}“")
        gesehen[nummer] = nr

    # 2) Codezäune
    zaeune = sum(1 for z in text.splitlines() if z.strip().startswith("```"))
    if zaeune % 2:
        befunde.append(f"{rel}: ungerade Anzahl Codezäune ({zaeune}) — ein ``` fehlt")

    # 3) Mermaid-Beschriftungen (nur Flussdiagramme: dort brechen Klammern
    #    ohne Anführungszeichen das Zeichnen ab; Zustands-/Ablaufdiagramme
    #    vertragen sie im Text nach dem Doppelpunkt problemlos).
    for bereich, inhalt in bloecke(text, "mermaid"):
        start = int(bereich.split(":")[0])
        kopf = next((z.strip() for z in inhalt.splitlines() if z.strip() and not z.strip().startswith("%%")), "")
        if not kopf.startswith(("graph", "flowchart")):
            continue
        for nr, zeile in enumerate(inhalt.splitlines(), start=start):
            if MERMAID_KLAMMER.search(zeile) and '"' not in zeile and ("|" in zeile or "[" in zeile):
                befunde.append(f"{rel}:{nr}: Mermaid-Beschriftung mit Klammern ohne \"…\" → {zeile.strip()[:70]}")

    # 4) Verweise auf Dateien
    for nr, zeile in enumerate(text.splitlines(), start=1):
        for ziel in VERWEIS.findall(zeile):
            if ziel.startswith(("http://", "https://", "mailto:")):
                continue
            zielpfad = (pfad.parent / ziel).resolve()
            if not zielpfad.exists():
                befunde.append(f"{rel}:{nr}: Verweis zeigt ins Leere → {ziel}")

    # 5) gleiche Überschrift zweimal hintereinander
    zeilen = [z.strip() for z in text.splitlines()]
    for i in range(1, len(zeilen)):
        if zeilen[i].startswith("#") and zeilen[i] == zeilen[i - 1]:
            befunde.append(f"{rel}:{i + 1}: Überschrift doppelt → {zeilen[i][:60]}")

    # 6) Hinweis: Datei nicht im ANHANG-Inhaltsverzeichnis
    anhang = wurzel / "ANHANG" / "README.md"
    if pfad.parent == wurzel and pfad.suffix == ".md" and pfad.name not in {"README.md"} and anhang.exists():
        if pfad.name not in anhang.read_text(encoding="utf-8"):
            hinweise.append(f"{rel}: steht nicht im ANHANG/README.md")

    return befunde, hinweise


def main() -> int:
    leise = "--leise" in sys.argv
    alle_befunde: list[str] = []
    alle_hinweise: list[str] = []
    liste = dateien()
    for p in liste:
        b, h = pruefe(p)
        alle_befunde += b
        alle_hinweise += h

    if alle_befunde:
        print(f"Befunde ({len(alle_befunde)}) in {len(liste)} Dateien:")
        for b in alle_befunde:
            print("  ✗", b)
    if alle_hinweise and not leise:
        print(f"\nHinweise ({len(alle_hinweise)}):")
        for h in alle_hinweise:
            print("  ·", h)
    if not alle_befunde:
        print(f"✓ sauber — {len(liste)} Dateien geprüft, keine Befunde.")
    return 1 if alle_befunde else 0


if __name__ == "__main__":
    sys.exit(main())
