#!/usr/bin/env python3
"""Setzt die Listen-Aufgaben in den laufenden Bot-Ablauf ein (chirurgisch).

Warum kein vollstaendiger Neubau: der Erzeuger setzt an den sechs Werkzeugknoten
das Feld "name" (titel_suchen, ...), die laufende Fassung hat es nicht. Ein
Neubau wuerde die Werkzeugnamen gegenueber dem Modell aendern - das gehoert nicht
zu dieser Erweiterung. Darum werden hier NUR die neuen Knoten, die geaenderte
Eingabe, die Verbindungen und die Positionen uebernommen; alles andere bleibt
zeichengleich zur laufenden Fassung.

Aufruf:
    python3 13-listen-patchen.py <laufend.json> <neubau.json> <ausgabe.json>
"""
import copy
import json
import re
import sys

# Die neuen Knoten samt Haftnotiz - genau diese werden eingefuegt.
NEU = ["Listen Art", "Listen?", "Listen Dienst", "Listen Antwort", "Listen Senden",
       "Notiz Listen"]

# Vorhandene Knoten, deren Position sich verschiebt (Platz fuer die neue Reihe).
VERSCHOBEN = ["Zugang", "Freigegeben?", "Text da?", "Auftrag", "Kein Zugang",
              "Kein Text", "Senden (Kurzmeldung)"]

# Vorhandene Knoten mit neuem Inhalt.
GEAENDERT = ["Eingabe"]

# Verbindungen, die neu gesetzt werden.
NEUE_KANTEN = ["Freigegeben?", "Listen Art", "Listen?", "Listen Dienst", "Listen Antwort"]


def als_ablauf(daten):
    return daten[0] if isinstance(daten, list) else daten


def ziele(ablauf):
    """Alle Knotennamen, die als Verbindungsziel vorkommen."""
    namen = set()
    for quelle in (ablauf.get("connections") or {}).values():
        for zweig in quelle.values():
            for gruppe in zweig:
                for kante in gruppe or []:
                    namen.add(kante["node"])
    return namen


def main() -> int:
    laufend_datei, gebaut_datei, ziel_datei = sys.argv[1:4]
    laufend_text = open(laufend_datei, encoding="utf-8").read()
    gebaut = als_ablauf(json.load(open(gebaut_datei, encoding="utf-8")))
    neu = copy.deepcopy(als_ablauf(json.loads(laufend_text)))

    kennung = (re.search(r"api\.telegram\.org/bot([A-Za-z0-9:_-]+)/", laufend_text) or [None, ""])[1]
    schluessel = re.search(r"[0-9a-f]{16}:[0-9a-f]{32}", laufend_text)
    schluessel = schluessel.group(0) if schluessel else ""
    if not kennung or not schluessel:
        print("FEHLER: Telegram-Kennung oder Schnittstellenschluessel nicht gefunden")
        return 1

    namen_laufend = [k["name"] for k in neu["nodes"]]
    schon_da = [n for n in NEU if n in namen_laufend]

    gebaut_nach_name = {k["name"]: k for k in gebaut["nodes"]}
    fehlend = [n for n in NEU + GEAENDERT if n not in gebaut_nach_name]
    if fehlend:
        print(f"FEHLER: im Neubau fehlen: {fehlend}")
        return 1

    # 1) neue Knoten einfuegen - oder, wenn schon vorhanden, auf den Stand des
    #    Neubaus bringen (der Aufruf ist damit wiederholbar).
    if schon_da:
        for name in NEU:
            ziel = [k for k in neu["nodes"] if k["name"] == name][0]
            ziel["parameters"] = copy.deepcopy(gebaut_nach_name[name]["parameters"])
            ziel["notes"] = gebaut_nach_name[name].get("notes", ziel.get("notes"))
            ziel["notesInFlow"] = gebaut_nach_name[name].get("notesInFlow", ziel.get("notesInFlow"))
        print(f"Knoten schon vorhanden - Inhalte aktualisiert: {schon_da}")
    else:
        for name in NEU:
            neu["nodes"].append(copy.deepcopy(gebaut_nach_name[name]))

    # 2) Positionen der verschobenen Knoten uebernehmen
    for knoten in neu["nodes"]:
        if knoten["name"] in VERSCHOBEN:
            knoten["position"] = list(gebaut_nach_name[knoten["name"]]["position"])

    # 3) geaenderte Knoten: nur der Inhalt, alles andere bleibt
    for name in GEAENDERT:
        quelle = gebaut_nach_name[name]
        ziel = [k for k in neu["nodes"] if k["name"] == name][0]
        for feld, wert in quelle["parameters"].items():
            ziel["parameters"][feld] = copy.deepcopy(wert)

    # 4) Verbindungen
    verbindungen = neu["connections"]
    for name in NEUE_KANTEN:
        verbindungen[name] = copy.deepcopy(gebaut["connections"][name])

    # ---------------------------------------------------------------- Pruefungen
    fehler = []
    ausgabe_text = json.dumps(neu, ensure_ascii=False, indent=2)
    if "<GEHEIM>" in ausgabe_text:
        fehler.append("Maskenmerker <GEHEIM> im Ergebnis")
    if kennung and kennung not in ausgabe_text:
        fehler.append("Telegram-Kennung fehlt im Ergebnis")
    if schluessel and schluessel not in ausgabe_text:
        fehler.append("Schnittstellenschluessel fehlt im Ergebnis")

    namen_neu = {k["name"] for k in neu["nodes"]}
    fehlende_ziele = sorted(ziele(neu) - namen_neu)
    if fehlende_ziele:
        fehler.append(f"Verbindungsziele ohne Knoten: {fehlende_ziele}")

    for name in NEU + GEAENDERT:
        if name not in namen_neu:
            fehler.append(f"Knoten fehlt: {name}")

    erwartete_zahl = len([k["name"] for k in als_ablauf(json.loads(laufend_text))["nodes"]])
    zuwachs = len(NEU) if not schon_da else 0
    if len(namen_neu) != erwartete_zahl + zuwachs:
        fehler.append(f"Knotenzahl stimmt nicht: {len(namen_neu)} statt "
                      f"{erwartete_zahl + zuwachs}")

    print(f"Knoten laufend: {erwartete_zahl}   nach dem Patchen: {len(namen_neu)}")
    print(f"Neu: {NEU}")
    print("Verschoben:", VERSCHOBEN)
    print("Inhalt neu:", GEAENDERT)
    print("Verbindungen neu gesetzt:", NEUE_KANTEN)
    if fehler:
        print("\nFEHLER - nicht geschrieben:")
        for f in fehler:
            print("  -", f)
        return 1

    with open(ziel_datei, "w", encoding="utf-8") as f:
        f.write(ausgabe_text)
    print(f"\nGeschrieben: {ziel_datei}")
    print("Geprueft: keine Maskenmerker, Kennung und Schluessel enthalten, "
          "alle Verbindungsziele vorhanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
