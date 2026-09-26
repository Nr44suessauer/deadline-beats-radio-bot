#!/usr/bin/env python3
"""Übersetzt die großen Markdown-Dokumente ins Englische (Doku-Werkzeug).

Arbeitet Zeile für Zeile außerhalb der Codeblöcke mit demselben lokalen
Sprachmodell wie `code-uebersetzen-en.py` (dessen Bausteine es mitbenutzt).
Vor der Übersetzung werden angewandt:

* die Ersetzungen aus `ZWEITBOT_ERSETZEN` (`veroeffentlichung-webseite.py`),
  soweit ein Eintrag zur Datei existiert,
* die Dateinamen der EN-Fassung (`EN_DATEIEN`),
* Ordnerpfade mit Schrägstrich (`DOKU/` -> `DOCS/` und so weiter).

Aufruf:
    python3 werkzeuge/doku/dokumente-uebersetzen-en.py <datei> [datei …]

Geschrieben wird nach `EN/<pfad>` wie bei den übrigen EN-Dateien. Am Ende wird
gemeldet, wenn eine Übersetzung die Zeilenmarkierung (#, -, |, …) oder die
Zahl der Tabellenspalten verändert hat — solche Stellen von Hand nachsehen.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
PROJEKT = HIER.parent.parent                                   # das Projekt

# Dateinamen (deutsch -> englisch) wie im EN-Baum, laengste zuerst.
_DATEIEN_MODUL = importlib.util.spec_from_file_location("ueb", HIER / "code-uebersetzen-en.py")
ueb = importlib.util.module_from_spec(_DATEIEN_MODUL)
_DATEIEN_MODUL.loader.exec_module(ueb)

_VWEB_MODUL = importlib.util.spec_from_file_location("vweb", HIER / "veroeffentlichung-webseite.py")
vweb = importlib.util.module_from_spec(_VWEB_MODUL)
_VWEB_MODUL.loader.exec_module(vweb)

DATEIEN = sorted(ueb.EN_DATEIEN.items(), key=lambda p: -len(p[0]))
# Ordner nur mit Schraegstrich (Pfadkontext), damit Prosa-Woerter wie „Doku“ heil bleiben.
ORDNER = [
    ("ablaeufe-laufend/", "running-workflows/"),
    ("zugangsdaten/", "credentials/"),
    ("werkzeuge/", "tools/"),
    ("NACHBAU/", "REBUILD/"),
    ("ANHANG/", "APPENDIX/"),
    ("dienst/", "service/"),
    ("meldungen/", "news/"),
    ("bilder/", "images/"),
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


def uebersetze_md(quelle: Path, ziel: Path) -> list[tuple[int, str, str, str]]:
    rel = str(quelle.relative_to(PROJEKT))
    text = vorbereiten(quelle.read_text(encoding="utf-8"), rel)
    zeilen = text.splitlines()

    offen = False
    stellen: list[int] = []
    for i, z in enumerate(zeilen):
        s = z.strip()
        if s.startswith("```"):
            offen = not offen
            continue
        if offen or not s:
            continue
        if ueb.DEUTSCH.search(z):
            stellen.append(i)

    print(f"{rel}: {len(zeilen)} Zeilen, {len(stellen)} Textstellen", flush=True)
    stuecke = [zeilen[i] for i in stellen]
    speicher_datei = ueb.speicher()
    neu: list[str] = []
    for anfang in range(0, len(stuecke), STAPEL):
        portion = stuecke[anfang:anfang + STAPEL]
        fehlend = [s for s in portion
                   if ueb.cache_schluessel(s) not in speicher_datei
                   and ueb.cache_schluessel(s.strip()) not in speicher_datei]
        if fehlend:
            try:
                frische = ueb.uebersetze_stuecke(fehlend, rel)
            except Exception:                           # noqa: BLE001
                frische = ueb.uebersetze_einzeln(fehlend, rel)
            for alt, nue in zip(fehlend, frische):
                speicher_datei[ueb.cache_schluessel(alt)] = nue
            ueb.SPEICHER.write_text(json.dumps(speicher_datei, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
        neu += [ueb.uebersetzung(s, speicher_datei) for s in portion]

    warnungen: list[tuple[int, str, str, str]] = []
    for i, neuzeile in zip(stellen, neu):
        alt = zeilen[i]
        marker = re.match(r"^(\s*(?:[#>|*\-]|\d+\.)\s*)", alt)
        marker_neu = re.match(r"^(\s*(?:[#>|*\-]|\d+\.)\s*)", neuzeile)
        if marker and (not marker_neu or marker.group(1) != marker_neu.group(1)):
            warnungen.append((i + 1, "Markierung", alt[:60], neuzeile[:60]))
        if alt.count("|") != neuzeile.count("|"):
            warnungen.append((i + 1, "Tabellenspalten", alt[:60], neuzeile[:60]))
        zeilen[i] = neuzeile

    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    print(f"Geschrieben: {ziel.relative_to(PROJEKT)}", flush=True)
    return warnungen


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    alle_warnungen: list[tuple[int, str, str, str]] = []
    for name in sys.argv[1:]:
        quelle = (PROJEKT / name).resolve()
        ziel = PROJEKT / "EN" / ueb.en_pfad(quelle.relative_to(PROJEKT))
        alle_warnungen += uebersetze_md(quelle, ziel)
    if alle_warnungen:
        print(f"\nWARNUNGEN ({len(alle_warnungen)}) — von Hand nachsehen:")
        for nr, art, a, b in alle_warnungen[:40]:
            print(f"   Zeile {nr} [{art}]: {a!r} -> {b!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
