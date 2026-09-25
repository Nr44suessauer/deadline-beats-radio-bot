#!/usr/bin/env python3
"""Vergleicht den Neubau des Bot-Ablaufs mit der laufenden Fassung.

Zweck: Vor dem Einspielen sehen, was sich wirklich aendert. Ein vollstaendiger
Neubau (agent-einspielen.sh) ersetzt den Ablauf - alles, was im Erzeuger fehlt,
waere danach weg. Dieses Skript listet darum:

  * Knoten, die es nur laufend gibt (waeren verloren)
  * Knoten, die es nur im Neubau gibt (neu)
  * inhaltliche Unterschiede je Knoten (ohne Zugangswerte und Wechselfelder)

Es schreibt nichts und bricht nicht ab - die Bewertung bleibt beim Menschen.

Aufruf:
    python3 12-neubau-vergleich.py <laufend.json> <neubau.json>
"""
import importlib.util
import json
import sys
from pathlib import Path

WERKZEUGE = Path(__file__).resolve().parents[1]


def lade_hilfen():
    """Die Vergleichshilfen aus tempo/03-tempo-patchen.py wiederverwenden."""
    pfad = WERKZEUGE / "tempo" / "03-tempo-patchen.py"
    spec = importlib.util.spec_from_file_location("tempo_patchen", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def als_ablauf(daten):
    return daten[0] if isinstance(daten, list) else daten


def main() -> int:
    hilfen = lade_hilfen()
    laufend_text = Path(sys.argv[1]).read_text(encoding="utf-8")
    gebaut_text = Path(sys.argv[2]).read_text(encoding="utf-8")

    kennung = hilfen.kennung_aus(laufend_text) or ""
    schluessel = ""
    import re
    treffer = re.search(r"[0-9a-f]{16}:[0-9a-f]{32}", laufend_text)
    if treffer:
        schluessel = treffer.group(0)

    laufend = als_ablauf(json.loads(laufend_text))
    gebaut = als_ablauf(json.loads(gebaut_text))

    alt = {n["name"]: n for n in laufend["nodes"]}
    neu = {n["name"]: n for n in gebaut["nodes"]}

    nur_laufend = sorted(set(alt) - set(neu))
    nur_neu = sorted(set(neu) - set(alt))

    alt_v = hilfen.vergleichsbild(laufend["nodes"], [kennung, schluessel])
    neu_v = hilfen.vergleichsbild(gebaut["nodes"], ["dummy"])

    unterschiede = []
    for name in sorted(set(alt) & set(neu)):
        if alt_v[name] != neu_v[name]:
            unterschiede.append(name)

    print(f"Knoten laufend: {len(alt)}   Neubau: {len(neu)}")
    print(f"Nur laufend (waeren weg): {nur_laufend or '(keine)'}")
    print(f"Nur im Neubau (neu): {nur_neu or '(keine)'}")
    print(f"Inhaltlich anders ({len(unterschiede)}): {unterschiede or '(keine)'}")
    gleich = laufend.get("connections") == gebaut.get("connections")
    print(f"Verbindungen unveraendert: {gleich}")
    if not gleich:
        alt_c, neu_c = laufend.get("connections") or {}, gebaut.get("connections") or {}
        for name in sorted(set(alt_c) | set(neu_c)):
            if alt_c.get(name) != neu_c.get(name):
                print(f"  anders: {name} -> {json.dumps(neu_c.get(name), ensure_ascii=False)[:160]}")

    print()
    if not nur_laufend:
        print("Urteil: der Neubau enthaelt alles, was laufend vorhanden ist.")
    else:
        print("ACHTUNG: der Neubau wuerde Knoten verlieren - vorher klaeren.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
