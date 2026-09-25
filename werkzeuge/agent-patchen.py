#!/usr/bin/env python3
"""Uebernimmt Aenderungen aus dem Erzeuger in den **laufenden** Radio-Ablauf.

Warum nicht einfach neu bauen: der Erzeuger setzt an den sechs Werkzeugknoten das
Feld `name` (titel_suchen und so weiter), das die laufende Fassung nicht hat. Ein
vollstaendiger Neubau wuerde die Werkzeugnamen gegenueber dem Modell aendern.
Dieses Werkzeug uebernimmt darum nur, was ausdruecklich genannt wird:

  * neue Knoten (im Neubau, aber nicht laufend),
  * umbenannte Knoten samt Verbindungen und `$('Name')`-Verweisen,
  * die Inhalte (Parameter) der genannten Knoten,
  * alle Positionen und das ganze Verbindungsbild aus dem Plan,
  * neue Haftnotizen.

Zugangswerte, Kennungen, Anmeldedaten und die Parameter aller uebrigen Knoten
bleiben **zeichengleich** zur laufenden Fassung.

Aufruf:
    python3 agent-patchen.py <laufend.json> <neubau.json> <ausgabe.json> \
        [--neu Knoten1,Knoten2] [--inhalt Knoten3] [--umbenennen "Alt=Neu,Alt2=Neu2"]
        [--trocken]

Ohne --neu werden alle im Neubau zusaetzlichen Knoten uebernommen.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys


def als_ablauf(daten):
    return daten[0] if isinstance(daten, list) else daten


def ziele(ablauf) -> set[str]:
    namen: set[str] = set()
    for quelle in (ablauf.get("connections") or {}).values():
        for zweig in quelle.values():
            for gruppe in zweig:
                for kante in gruppe or []:
                    namen.add(kante["node"])
    return namen


def kern(pfad: str, zusatz: str = "") -> tuple[dict, str, str]:
    text = open(pfad, encoding="utf-8").read()
    # Die Zugangswerte koennen in einer zweiten Datei liegen (seit dem Umbau
    # vom 22.09.2026 im Ablauf "Konfiguration - alle Werte").
    gesamt = text + zusatz
    kennung = (re.search(r"([0-9]{6,12}:[A-Za-z0-9_-]{33,})", gesamt) or [None, ""])[1]
    schluessel = re.search(r"[0-9a-f]{16}:[0-9a-f]{32}", gesamt)
    return als_ablauf(json.loads(text)), kennung, (schluessel.group(0) if schluessel else "")


def main() -> int:
    zerleger = argparse.ArgumentParser()
    zerleger.add_argument("laufend")
    zerleger.add_argument("neubau")
    zerleger.add_argument("ausgabe")
    zerleger.add_argument("--neu", default="")
    zerleger.add_argument("--inhalt", default="")
    zerleger.add_argument("--umbenennen", default="")
    zerleger.add_argument("--trocken", action="store_true")
    zerleger.add_argument("--aufraeumen", action="store_true",
                          help="Positionen, Notizen und Rahmen vollstaendig aus dem Plan uebernehmen")
    args = zerleger.parse_args()

    zusatz = ""
    if os.environ.get("KONFIG_LAUFEND"):
        zusatz = open(os.environ["KONFIG_LAUFEND"], encoding="utf-8").read()
    laufend, kennung, schluessel = kern(args.laufend, zusatz)
    gebaut, _, _ = kern(args.neubau, zusatz)
    if not kennung or not schluessel:
        print("FEHLER: Telegram-Kennung oder Schnittstellenschluessel nicht gefunden "
              "(Agent und Konfiguration geprueft)")
        return 1

    neu_daten = copy.deepcopy(laufend)
    umbenennen = {}
    for paar in filter(None, (p.strip() for p in args.umbenennen.split(","))):
        alt, _, ziel = paar.partition("=")
        umbenennen[alt.strip()] = ziel.strip()

    # ------------------------------------------------------------ 1) Umbenennen
    if umbenennen:
        namen_jetzt = {k["name"] for k in neu_daten["nodes"]}
        # Wiederholbar: Paare, deren Ziel schon steht (Alt weg, Neu da), sind
        # bereits erledigt und werden uebersprungen.
        schon = sorted(a for a, z in umbenennen.items()
                       if a not in namen_jetzt and z in namen_jetzt)
        for a in schon:
            del umbenennen[a]
        if schon:
            print(f"  schon umbenannt (uebersprungen): {schon}")
        fehlend = [a for a in umbenennen if a not in namen_jetzt]
        if fehlend:
            print(f"FEHLER: nicht vorhanden, kann nicht umbenannt werden: {fehlend}")
            return 1
        for knoten in neu_daten["nodes"]:
            if knoten["name"] in umbenennen:
                knoten["name"] = umbenennen[knoten["name"]]
        # Verweise in Verbindungen und in Ausdruecken nachziehen (die Verbindungen
        # kommen spaeter ohnehin aus dem Plan, die Ausdruecke bleiben laufend).
        text = json.dumps(neu_daten, ensure_ascii=False)
        for alt, ziel in umbenennen.items():
            text = text.replace(f'"node": "{alt}"', f'"node": "{ziel}"')
            text = text.replace(f"$('{alt}')", f"$('{ziel}')")
            text = text.replace(f'$("{alt}")', f'$("{ziel}")')
        neu_daten = json.loads(text)
        print(f"Umbenannt: {umbenennen}")

    laufend_namen = {k["name"] for k in neu_daten["nodes"]}
    gebaut_nach = {k["name"]: k for k in gebaut["nodes"]}
    if args.aufraeumen:
        # Reine Zeichenflaeche: Rahmen kommen komplett aus dem Plan (alte weg),
        # Notiz und Sichtbarkeit an jedem Knoten ebenfalls. Inhalte, Kennungen
        # und Verbindungen bleiben unberuehrt.
        alte = [k["name"] for k in neu_daten["nodes"] if "stickyNote" in k["type"]]
        neu_daten["nodes"] = [k for k in neu_daten["nodes"] if "stickyNote" not in k["type"]]
        for name in alte:
            print(f"  - alter Rahmen: {name}")
        for eintrag in gebaut["nodes"]:
            if "stickyNote" in eintrag["type"]:
                neu_daten["nodes"].append(copy.deepcopy(eintrag))
                print(f"  + Rahmen: {eintrag['name']}")
        geaendert = 0
        for knoten in neu_daten["nodes"]:
            quelle = gebaut_nach.get(knoten["name"])
            if not quelle:
                continue
            for feld in ("notes", "notesInFlow"):
                if feld in quelle and knoten.get(feld) != quelle[feld]:
                    knoten[feld] = copy.deepcopy(quelle[feld])
                    geaendert += 1
                elif feld not in quelle and feld in knoten:
                    del knoten[feld]
                    geaendert += 1
        print(f"  ~ Beschriftung: {geaendert} Aenderung(en) an Notizen")

    # ------------------------------------------------------------ 2) neue Knoten
    nur_gebaut = [n for n in gebaut_nach if n not in laufend_namen]
    gewuenscht = [n.strip() for n in args.neu.split(",") if n.strip()]
    einzufuegen = gewuenscht or nur_gebaut
    if args.aufraeumen:   # Rahmen kommen schon oben aus dem Plan
        einzufuegen = [n for n in einzufuegen if "stickyNote" not in gebaut_nach[n]["type"]]
    unbekannt = [n for n in einzufuegen if n not in gebaut_nach]
    if unbekannt:
        print(f"FEHLER: im Neubau nicht vorhanden: {unbekannt}")
        return 1
    schon_da = [n for n in einzufuegen if n in laufend_namen]
    if schon_da:
        print(f"Schon vorhanden, nur Inhalt: {schon_da}")
    for name in einzufuegen:
        if name not in laufend_namen:
            neu_daten["nodes"].append(copy.deepcopy(gebaut_nach[name]))
            print(f"  + {name} ({gebaut_nach[name]['type']})")

    # ------------------------------------------------- 3) Inhalte uebernehmen
    inhalt = [n.strip() for n in args.inhalt.split(",") if n.strip()]
    for name in inhalt:
        if name not in gebaut_nach:
            print(f"FEHLER: Inhalt angefordert, aber im Neubau nicht vorhanden: {name}")
            return 1
        ziel = [k for k in neu_daten["nodes"] if k["name"] == name]
        if not ziel:
            print(f"FEHLER: Knoten fehlt laufend: {name}")
            return 1
        for feld, wert in gebaut_nach[name]["parameters"].items():
            ziel[0]["parameters"][feld] = copy.deepcopy(wert)
        for feld in ("notes", "notesInFlow"):
            if feld in gebaut_nach[name]:
                ziel[0][feld] = gebaut_nach[name][feld]
        print(f"  ~ Inhalt: {name}")

    # --------------------------------- 4) Positionen und Verbindungen aus dem Plan
    ohne_position = []
    for knoten in neu_daten["nodes"]:
        quelle = gebaut_nach.get(knoten["name"])
        if quelle and "position" in quelle:
            knoten["position"] = list(quelle["position"])
        elif "stickyNote" not in knoten["type"]:
            ohne_position.append(knoten["name"])
    if ohne_position:
        print(f"WARNUNG: ohne Position im Plan: {ohne_position}")
    neu_daten["connections"] = copy.deepcopy(gebaut["connections"])

    # --------------------------------------------------------------- 5) Pruefen
    fehler = []
    text = json.dumps(neu_daten, ensure_ascii=False)
    if "<GEHEIM>" in text:
        fehler.append("Maskenmerker <GEHEIM> im Ergebnis")
    # Seit dem Umbau auf "Konfiguration - alle Werte" stehen Kennung und
    # Schluessel NICHT mehr im Agenten - der Verweis darauf genuegt.
    zentral = "$('Konfiguration')" in text
    if not zentral and kennung not in text:
        fehler.append("Telegram-Kennung fehlt im Ergebnis")
    if not zentral and schluessel not in text:
        fehler.append("Schnittstellenschluessel fehlt im Ergebnis")
    # Altlasten: Feldnamen und Knotennamen aus frueheren Fassungen. Beim Umbau
    # von "Listen ..." auf "Dienst ..." war ein Knotenausdruck uebersehen worden
    # (Listen Dienst fragte weiter nach listenArt) - der Knopfweg lief ins Leere.
    altlasten = [wort for wort in ("listenArt", "$('Listen", 'Listen Art', 'Listen?',
                                   "Notiz Listen")
                 if wort in text]
    if altlasten:
        fehler.append(f"Altlasten aus einer frueheren Fassung: {altlasten}")

    eigene = {k["name"] for k in neu_daten["nodes"]}
    fehlende_ziele = sorted(ziele(neu_daten) - eigene)
    if fehlende_ziele:
        fehler.append(f"Verbindungsziele ohne Knoten: {fehlende_ziele}")

    verloren = sorted(laufend_namen - eigene)
    if args.aufraeumen:
        # Beim Aufraeumen werden Rahmen neu gelegt - alte Haftnotizen duerfen
        # verschwinden (Knoten mit Logik nie).
        alt_typ = {k["name"]: k["type"] for k in laufend["nodes"]}
        verloren = [n for n in verloren if "stickyNote" not in alt_typ.get(n, "")]
    if verloren:
        fehler.append(f"Knoten wuerden verloren gehen: {verloren}")

    print(f"\nKnoten laufend {len(laufend['nodes'])} -> nach dem Patchen {len(neu_daten['nodes'])}")
    if fehler:
        print("FEHLER - nicht geschrieben:")
        for f in fehler:
            print("  -", f)
        return 1
    if args.trocken:
        print("Trockenlauf: nichts geschrieben.")
        return 0
    with open(args.ausgabe, "w", encoding="utf-8") as f:
        json.dump([neu_daten], f, ensure_ascii=False, indent=2)
    print(f"Geschrieben: {args.ausgabe}")
    print("Geprueft: keine Maskenmerker, Kennung und Schluessel enthalten, "
          "keine Knoten verloren, alle Verbindungsziele vorhanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
