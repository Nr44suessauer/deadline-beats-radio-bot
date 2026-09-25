#!/usr/bin/env python3
"""Takes over tempo changes into the running Radio schedule.

Instead of rebuilding the entire schedule (for which the Telegram identifier is missing),
only the nodes are replaced that have actually changed in the producer.

IMPORTANT: Access values (Telegram identifier, interface key) are **only
masked for comparison**. The unchanged running version is always written.
The previous version of this script (`03-tempo-patchen-fehlerhaft.py.bak`)
had applied the masked values and thus destroyed the Telegram addresses of the bot
(404 when sending and when retrieving files) - hence the checks at the end.

Call:
    python3 03-tempo-patch.py <running.json> <new-gebaut.json> <output.json> [erlaubteIds]
"""
import copy
import json
import re
import sys

# Nodes where a change is expected - anything else would be an error.
ERWARTET = {"Short?", "Commands and locations", "Plan", "Pruefen"}

# Deviations that only originate from the newer n8n version and are consciously NOT
# adopted: the producer sets the fields "name"
# (tool model name) and "source" in the tool nodes. They are missing
# in the running version, where the node names are treated as tool names. Adopting would
# rename the tools for the model - this does not belong to this change.
BEKANNT_HARMLOS = {
    "Search for tool titles", "Search for tool direction", "Tool What is running",
    "Tool Azura addresses", "Tool Azura call", "Tool Azura overview",
}

# Fields that are newly created with each build or that n8n adds when saving.
WEGFELDER = {
    "id", "color", "hasOutputParser", "method", "position", "webhookId",
    "batchSize", "source", "mode", "parameterType", "alwaysOutputData",
}


def kennung_aus(text: str):
    hits = re.search(r"https://api\.telegram\.org/bot([A-Za-z0-9:_-]+)/", text)
    return hits.group(1) if hits else None


def maskieren(obj, geheim):
    """Deep copy, in which access values are replaced by a marker."""
    obj = copy.deepcopy(obj)
    text = json.dumps(obj, ensure_ascii=False)
    for wert in geheim:
        if wert and wert in text:
            text = text.replace(wert, "<SECRET>")
    return json.loads(text)


def normalisieren(obj):
    if isinstance(obj, dict):
        return {k: normalisieren(v) for k, v in obj.items() if k not in WEGFELDER}
    if isinstance(obj, list):
        return [normalisieren(x) for x in obj]
    return obj


def vergleichsbild(nodes, geheim):
    erg = {}
    for n in nodes:
        p = normalisieren(maskieren(n.get("parameters") or {}, geheim))
        erg[n["name"]] = json.dumps(p, sort_keys=True, ensure_ascii=False)
    return erg


def main() -> int:
    laufend_datei, gebaut_datei, ziel_datei = sys.argv[1:4]
    allowed = sys.argv[4] if len(sys.argv) > 4 else None

    laufend_text = open(laufend_datei, encoding="utf-8").read()
    gebaut_text = open(gebaut_datei, encoding="utf-8").read()

    identifier = kennung_aus(laufend_text)
    if not identifier:
        print("ERROR: no Telegram identifier found in the running version")
        return 1
    key = re.search(r"[0-9a-f]{16}:[0-9a-f]{32}", laufend_text)
    schluessel_wert = key.group(0) if key else ""

    # The producer writes a single object, the export is a list.
    # For output, the running version is used UNCHANGED.
    laufend_daten = json.loads(laufend_text)
    running = laufend_daten[0] if isinstance(laufend_daten, list) else laufend_daten
    gebaut_daten = json.loads(gebaut_text)
    gebaut = gebaut_daten[0] if isinstance(gebaut_daten, list) else gebaut_daten

    alt = {n["name"]: n for n in running["nodes"]}
    new = {n["name"]: n for n in gebaut["nodes"]}

    missing = sorted(set(new) - set(alt))
    if missing:
        print(f"ERROR: new nodes in rebuild that do not exist running: {missing}")
        return 1

    alt_v = vergleichsbild(running["nodes"], [identifier, schluessel_wert])
    neu_v = vergleichsbild(gebaut["nodes"], ["dummy"])

    unterschiede, unknown = [], []
    for name in alt:
        if alt_v[name] != neu_v[name]:
            unterschiede.append(name)
            if name not in ERWARTET and name not in BEKANNT_HARMLOS:
                unknown.append(name)

    print("Nodes running/new:", len(alt), len(new))
    print("Connections unchanged:", running.get("connections") == gebaut.get("connections"))
    print("Differences:", ", ".join(unterschiede) if unterschiede else "(none)")
    if unknown:
        print(f"ERROR: unexpected changes in {unknown} - aborting")
        return 1
    fehlend_erwartet = ERWARTET - set(unterschiede)
    if fehlend_erwartet:
        print(f"ERROR: expected change missing in {sorted(fehlend_erwartet)} - aborting")
        return 1

    zu_tauschen = [n for n in unterschiede if n in ERWARTET]
    print("To be adopted:", ", ".join(zu_tauschen))
    rest = [n for n in unterschiede if n not in ERWARTET]
    if rest:
        print("Remains unchanged (only newer n8n defaults):", ", ".join(rest))

    for name in zu_tauschen:
        uebernahme = json.dumps(new[name]["parameters"], ensure_ascii=False)
        if "dummy" in uebernahme or "<SECRET>" in uebernahme:
            print(f"ERROR: node ’{name}’ contains placeholder instead of access values - aborting")
            return 1
        alt[name]["parameters"] = new[name]["parameters"]
        alt[name]["notes"] = new[name].get("notes", alt[name].get("notes"))

    if allowed:
        data = running.get("staticData")
        if isinstance(data, str):
            data = json.loads(data or "{}")
        glob = data.setdefault("global", {})
        before = list(glob.get("allowed") or [])
        glob["allowed"] = sorted({str(x) for x in before} | {str(x) for x in allowed.split(",")})
        running["staticData"] = data
        print("Allowed identifiers:", before, "->", glob["allowed"])

    ziel_text = json.dumps([running], ensure_ascii=False, indent=2)
    if "<SECRET>" in ziel_text:
        print("ERROR: the output contains the marker <GEHEIM> - aborting")
        return 1
    if identifier not in ziel_text:
        print("ERROR: Telegram identifier missing in output - aborting")
        return 1
    if schluessel_wert and schluessel_wert not in ziel_text:
        print("ERROR: interface key missing in output - aborting")
        return 1

    with open(ziel_datei, "w", encoding="utf-8") as f:
        f.write(ziel_text)
    print(f"written: {ziel_datei} (identifier and key verified and included)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
