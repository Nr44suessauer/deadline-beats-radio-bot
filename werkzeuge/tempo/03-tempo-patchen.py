#!/usr/bin/env python3
"""Übernimmt die Tempo-Änderungen in den laufenden Radio-Ablauf.

Statt den Ablauf komplett neu zu bauen (dafür fehlt die Telegram-Kennung),
werden nur die Knoten ersetzt, die sich im Erzeuger wirklich geändert haben.

WICHTIG: Zugangswerte (Telegram-Kennung, Schnittstellenschlüssel) werden **nur
für den Vergleich** maskiert. Geschrieben wird immer die unveränderte laufende
Fassung. Die Vorgängerfassung dieses Skripts (`03-tempo-patchen-fehlerhaft.py.bak`)
hatte die maskierten Werte eingespielt und damit die Telegram-Adressen des Bots
zerstört (404 beim Senden und beim Datei-Abholen) - daher die Prüfungen am Ende.

Aufruf:
    python3 03-tempo-patchen.py <laufend.json> <neu-gebaut.json> <ausgabe.json> [erlaubteIds]
"""
import copy
import json
import re
import sys

# Knoten, bei denen eine Änderung erwartet wird - alles andere wäre ein Fehler.
ERWARTET = {"Kurz?", "Befehle und Lage", "Planen", "Pruefen"}

# Abweichungen, die nur von der neueren n8n-Fassung stammen und bewusst NICHT
# übernommen werden: der Erzeuger setzt bei den Werkzeugknoten die Felder "name"
# (Modellname des Werkzeugs) und "source". In der laufenden Fassung fehlen sie,
# dort gelten die Knotennamen als Werkzeugnamen. Ein Übernehmen würde die
# Werkzeuge für das Modell umbenennen - das gehört nicht zu dieser Änderung.
BEKANNT_HARMLOS = {
    "Werkzeug Titel suchen", "Werkzeug Richtung suchen", "Werkzeug Was laeuft",
    "Werkzeug Azura Adressen", "Werkzeug Azura Aufruf", "Werkzeug Azura Ueberblick",
}

# Felder, die bei jedem Bau neu entstehen oder die n8n beim Speichern ergänzt.
WEGFELDER = {
    "id", "color", "hasOutputParser", "method", "position", "webhookId",
    "batchSize", "source", "mode", "parameterType", "alwaysOutputData",
}


def kennung_aus(text: str):
    treffer = re.search(r"https://api\.telegram\.org/bot([A-Za-z0-9:_-]+)/", text)
    return treffer.group(1) if treffer else None


def maskieren(obj, geheim):
    """Tiefe Kopie, in der Zugangswerte durch einen Merker ersetzt sind."""
    obj = copy.deepcopy(obj)
    text = json.dumps(obj, ensure_ascii=False)
    for wert in geheim:
        if wert and wert in text:
            text = text.replace(wert, "<GEHEIM>")
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
    erlaubte = sys.argv[4] if len(sys.argv) > 4 else None

    laufend_text = open(laufend_datei, encoding="utf-8").read()
    gebaut_text = open(gebaut_datei, encoding="utf-8").read()

    kennung = kennung_aus(laufend_text)
    if not kennung:
        print("FEHLER: keine Telegram-Kennung in der laufenden Fassung gefunden")
        return 1
    schluessel = re.search(r"[0-9a-f]{16}:[0-9a-f]{32}", laufend_text)
    schluessel_wert = schluessel.group(0) if schluessel else ""

    # Der Erzeuger schreibt ein einzelnes Objekt, der Export eine Liste.
    # Für die Ausgabe wird die laufende Fassung UNVERÄNDERT weiterverwendet.
    laufend_daten = json.loads(laufend_text)
    laufend = laufend_daten[0] if isinstance(laufend_daten, list) else laufend_daten
    gebaut_daten = json.loads(gebaut_text)
    gebaut = gebaut_daten[0] if isinstance(gebaut_daten, list) else gebaut_daten

    alt = {n["name"]: n for n in laufend["nodes"]}
    neu = {n["name"]: n for n in gebaut["nodes"]}

    fehlend = sorted(set(neu) - set(alt))
    if fehlend:
        print(f"FEHLER: neue Knoten im Neubau, die es laufend nicht gibt: {fehlend}")
        return 1

    alt_v = vergleichsbild(laufend["nodes"], [kennung, schluessel_wert])
    neu_v = vergleichsbild(gebaut["nodes"], ["dummy"])

    unterschiede, unbekannt = [], []
    for name in alt:
        if alt_v[name] != neu_v[name]:
            unterschiede.append(name)
            if name not in ERWARTET and name not in BEKANNT_HARMLOS:
                unbekannt.append(name)

    print("Knoten laufend/neu:", len(alt), len(neu))
    print("Verbindungen unverändert:", laufend.get("connections") == gebaut.get("connections"))
    print("Unterschiede:", ", ".join(unterschiede) if unterschiede else "(keine)")
    if unbekannt:
        print(f"FEHLER: unerwartete Änderungen in {unbekannt} - Abbruch")
        return 1
    fehlend_erwartet = ERWARTET - set(unterschiede)
    if fehlend_erwartet:
        print(f"FEHLER: erwartete Änderung fehlt in {sorted(fehlend_erwartet)} - Abbruch")
        return 1

    zu_tauschen = [n for n in unterschiede if n in ERWARTET]
    print("Wird übernommen:", ", ".join(zu_tauschen))
    rest = [n for n in unterschiede if n not in ERWARTET]
    if rest:
        print("Bleibt unverändert (nur neuere n8n-Vorgaben):", ", ".join(rest))

    for name in zu_tauschen:
        uebernahme = json.dumps(neu[name]["parameters"], ensure_ascii=False)
        if "dummy" in uebernahme or "<GEHEIM>" in uebernahme:
            print(f"FEHLER: Knoten '{name}' enthält Platzhalter statt Zugangswerten - Abbruch")
            return 1
        alt[name]["parameters"] = neu[name]["parameters"]
        alt[name]["notes"] = neu[name].get("notes", alt[name].get("notes"))

    if erlaubte:
        daten = laufend.get("staticData")
        if isinstance(daten, str):
            daten = json.loads(daten or "{}")
        glob = daten.setdefault("global", {})
        vorher = list(glob.get("erlaubte") or [])
        glob["erlaubte"] = sorted({str(x) for x in vorher} | {str(x) for x in erlaubte.split(",")})
        laufend["staticData"] = daten
        print("Erlaubte Kennungen:", vorher, "->", glob["erlaubte"])

    ziel_text = json.dumps([laufend], ensure_ascii=False, indent=2)
    if "<GEHEIM>" in ziel_text:
        print("FEHLER: die Ausgabe enthält den Merker <GEHEIM> - Abbruch")
        return 1
    if kennung not in ziel_text:
        print("FEHLER: Telegram-Kennung fehlt in der Ausgabe - Abbruch")
        return 1
    if schluessel_wert and schluessel_wert not in ziel_text:
        print("FEHLER: Schnittstellenschlüssel fehlt in der Ausgabe - Abbruch")
        return 1

    with open(ziel_datei, "w", encoding="utf-8") as f:
        f.write(ziel_text)
    print(f"geschrieben: {ziel_datei} (Kennung und Schlüssel geprüft und enthalten)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
