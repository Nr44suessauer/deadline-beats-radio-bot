#!/usr/bin/env python3
"""Translates the large Markdown documents into English (documentation tool).

Works line by line outside of code blocks with the same local
language model as `code-translate-en.py` (which uses the same building blocks).
Before translation, the following are applied:

* the replacements from `ZWEITBOT_ERSETZEN` (`veroeffentlichung-webseite.py`),
 provided that an entry for the file exists,
* the filenames of the EN version (`EN_DATEIEN`),
* folder paths with forward slash (`DOKU/` -> `DOCS/` and so forth).

Call:
    python3 werkzeuge/doku/dokumente-uebersetzen-en.py <file> [file …]

Written to `EN/<path>` as with the other EN files. At the end,
it is reported if a translation has changed the line marker (#, -, |, …) or the
number of table columns — check such places manually.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
PROJEKT = HIER.parent.parent                                   # the project

# filenames (German -> English) as in the EN tree, longest first.
_DATEIEN_MODUL = importlib.util.spec_from_file_location("ueb", HIER / "code-uebersetzen-en.py")
ueb = importlib.util.module_from_spec(_DATEIEN_MODUL)
_DATEIEN_MODUL.loader.exec_module(ueb)

_VWEB_MODUL = importlib.util.spec_from_file_location("vweb", HIER / "veroeffentlichung-webseite.py")
vweb = importlib.util.module_from_spec(_VWEB_MODUL)
_VWEB_MODUL.loader.exec_module(vweb)

DATEIEN = sorted(ueb.EN_DATEIEN.items(), key=lambda p: -len(p[0]))
# Folders only with forward slash (path context), so that prose words like "Doku" remain intact.
ORDNER = [
    ("workflows-running/", "running-workflows/"),
    ("access-data/", "credentials/"),
    ("tools/", "tools/"),
    ("REBUILD/", "REBUILD/"),
    ("APPENDIX/", "APPENDIX/"),
    ("service/", "service/"),
    ("news/", "news/"),
    ("images/", "images/"),
    ("DOKU/", "DOCS/"),
    ("doku/", "docs/"),
]

STAPEL = 20


def vorbereiten(text: str, rel: str) -> str:
    if rel in vweb.ZWEITBOT_ERSETZEN:
        for alt, ers in vweb.ZWEITBOT_ERSETZEN[rel]:
            text = text.replace(alt, ers)
    for alt, ers in DATEIEN:
        text = text.replace(alt, ers)
    for alt, ers in ORDNER:
        text = text.replace(alt, ers)
    return text


def uebersetze_md(source: Path, target: Path) -> list[tuple[int, str, str, str]]:
    rel = str(source.relative_to(PROJEKT))
    text = vorbereiten(source.read_text(encoding="utf-8"), rel)
    lines = text.splitlines()

    open = False
    stellen: list[int] = []
    for i, z in enumerate(lines):
        s = z.strip()
        if s.startswith("```"):
            open = not open
            continue
        if open or not s:
            continue
        if ueb.DEUTSCH.search(z):
            stellen.append(i)

    print(f"{rel}: {len(lines)} lines, {len(stellen)} text places", flush=True)
    stuecke = [lines[i] for i in stellen]
    speicher_datei = ueb.speicher()
    new: list[str] = []
    for beginning in range(0, len(stuecke), STAPEL):
        portion = stuecke[beginning:beginning + STAPEL]
        missing = [s for s in portion
                   if ueb.cache_schluessel(s) not in speicher_datei
                   and ueb.cache_schluessel(s.strip()) not in speicher_datei]
        if missing:
            try:
                frische = ueb.uebersetze_stuecke(missing, rel)
            except Exception:                           # noqa: BLE001
                frische = ueb.uebersetze_einzeln(missing, rel)
            for alt, nue in zip(missing, frische):
                speicher_datei[ueb.cache_schluessel(alt)] = nue
            ueb.SPEICHER.write_text(json.dumps(speicher_datei, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
        new += [ueb.uebersetzung(s, speicher_datei) for s in portion]

    warnungen: list[tuple[int, str, str, str]] = []
    for i, neuzeile in zip(stellen, new):
        alt = lines[i]
        marker = re.match(r"^(\s*(?:[#>|*\-]|\d+\.)\s*)", alt)
        marker_neu = re.match(r"^(\s*(?:[#>|*\-]|\d+\.)\s*)", neuzeile)
        if marker and (not marker_neu or marker.group(1) != marker_neu.group(1)):
            warnungen.append((i + 1, "Markierung", alt[:60], neuzeile[:60]))
        if alt.count("|") != neuzeile.count("|"):
            warnungen.append((i + 1, "Tabellenspalten", alt[:60], neuzeile[:60]))
        lines[i] = neuzeile

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Written: {target.relative_to(PROJEKT)}", flush=True)
    return warnungen


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    alle_warnungen: list[tuple[int, str, str, str]] = []
    for name in sys.argv[1:]:
        source = (PROJEKT / name).resolve()
        target = PROJEKT / "EN" / ueb.en_pfad(source.relative_to(PROJEKT))
        alle_warnungen += uebersetze_md(source, target)
    if alle_warnungen:
        print(f"\n WARNINGS ({len(alle_warnungen)}) — check manually:")
        for nr, type, a, b in alle_warnungen[:40]:
            print(f" Line {nr} [{type}]: {a!r} -> {b!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
