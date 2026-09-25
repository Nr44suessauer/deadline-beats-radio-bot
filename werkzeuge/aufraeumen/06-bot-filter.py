#!/usr/bin/env python3
"""Ergaenzt im Such-Werkzeug des Radio-Bots den Ausschluss des Live-Archivs.

Der Bot sucht ueber den Katalogdienst und die Sender-Schnittstelle. Beide liefern
Dateipfade; die Live-/Bootleg-Mitschnitte liegen seit dem Aufraeumen unter
"_Archiv/". Dieses Skript patcht den Knoten "Treffer aufbereiten" so, dass solche
Treffer gar nicht erst vorgeschlagen werden.

Aufruf:  python3 06-bot-filter.py <eingabe.json> <ausgabe.json>
"""
import json
import sys

# Anker: die Schleife, die die Treffer beider Quellen zusammenfuehrt.
ANKER = "for (const t of quelle('Suche klug').concat(quelle('Suche Sender'))) {"
ALT = "  const pfad = t.path || '';\n  if (!pfad) continue;"
NEU = (
    "  const pfad = t.path || '';\n"
    "  if (!pfad) continue;\n"
    "  // Live-/Bootleg-Mitschnitte liegen im Archiv und werden nie vorgeschlagen.\n"
    "  if (/^_Archiv\\//i.test(pfad)) continue;"
)


def main() -> int:
    quelle, ziel = sys.argv[1], sys.argv[2]
    daten = json.load(open(quelle, encoding="utf-8"))
    ablauf = daten[0] if isinstance(daten, list) else daten

    geaendert = 0
    for knoten in ablauf.get("nodes", []):
        code = knoten.get("parameters", {}).get("jsCode")
        if not code or ANKER not in code:
            continue
        if "_Archiv" in code:
            print(f"Knoten '{knoten['name']}': Filter ist schon vorhanden")
            geaendert += 1
            continue
        if code.count(ALT) != 1:
            print(f"FEHLER: Ankerstelle {code.count(ALT)}x gefunden - Abbruch")
            return 1
        knoten["parameters"]["jsCode"] = code.replace(ALT, NEU)
        print(f"Knoten '{knoten['name']}': Archiv-Filter eingefuegt")
        geaendert += 1

    if not geaendert:
        print("FEHLER: kein passender Knoten gefunden - Abbruch")
        return 1

    with open(ziel, "w", encoding="utf-8") as f:
        json.dump([ablauf], f, ensure_ascii=False, indent=2)
    print(f"geschrieben: {ziel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
