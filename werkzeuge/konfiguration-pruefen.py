#!/usr/bin/env python3
"""Prueft die zentrale Konfiguration in den erzeugten Ablaufen.

Fuenf Pruefungen, ohne die ein Import in n8n still scheitern kann:

 1. Knotennamen eindeutig (n8n lehnt doppelte Namen ab).
 2. Jeder Verweis "$('Knoten')" zeigt auf einen vorhandenen Knoten.
 3. Kein Ausdruck enthaelt verschachtelte "{{ ... }}" (das kann n8n nicht lesen).
 4. Jeder Knoten, der Werte aus der Konfiguration braucht, ist vom Knoten
    "Konfiguration" aus erreichbar (sonst findet er zur Laufzeit nichts).
 5. In Bot und Werkzeugen stehen keine Zugangsdaten mehr (nur in der Konfiguration).

Aufruf:  python3 konfiguration-pruefen.py [ordner-mit-den-json]
"""
import json
import os
import re
import sys

ORDNER = sys.argv[1] if len(sys.argv) > 1 else "/tmp"
DATEIEN = ["radio-konfiguration.json", "radio-werkzeuge.json", "radio-agent.json"]
KNOTEN = "Konfiguration"


def lade(pfad):
    with open(pfad, encoding="utf-8") as f:
        d = json.load(f)
    return d if isinstance(d, list) else [d]


def text_von(obj):
    return json.dumps(obj, ensure_ascii=False)


def nachfolger(ablauf, name):
    """Alle direkten Ziele eines Knotens - ueber ALLE Verbindungsarten.

    Wichtig: die Werkzeugknoten des Agenten haengen nicht an "main", sondern an
    "ai_tool". Wer nur "main" verfolgt, haelt sie faelschlich fuer unerreichbar.
    """
    ziele = []
    for art, zweige in (ablauf["connections"].get(name) or {}).items():
        for zweig in zweige or []:
            for z in zweig or []:
                ziele.append(z.get("node"))
    return [z for z in ziele if z]


def erreichbar(ablauf, start):
    """Alle Knoten, die von 'start' aus ueber Verbindungen erreichbar sind."""
    gesehen, stapel = set(), [start]
    while stapel:
        n = stapel.pop()
        if n in gesehen:
            continue
        gesehen.add(n)
        stapel.extend(nachfolger(ablauf, n))
    return gesehen


def ist_unterknoten(ablauf, name):
    """Modell- oder Werkzeugknoten des Agenten.

    Achtung: diese Knoten sind die QUELLE einer ai_*-Verbindung und zeigen auf den
    Agenten - sie liegen also vor ihm, nicht dahinter. Genau deshalb kann die
    Erreichbarkeitspruefung sie nicht sehen; ob n8n ihre Ausdruecke aufloest, muss
    ein Testlauf zeigen.
    """
    return any(art.startswith("ai_") for art in (ablauf["connections"].get(name) or {}))


def main():
    gefunden, fehler = 0, []
    for datei in DATEIEN:
        pfad = os.path.join(ORDNER, datei)
        if not os.path.exists(pfad):
            print("   fehlt:", pfad)
            continue
        for ablauf in lade(pfad):
            name = ablauf.get("name")
            knoten = ablauf["nodes"]
            namen = [k["name"] for k in knoten]
            print(f"== {name} ({len(namen)} Knoten)")

            # 1) eindeutige Namen
            doppelt = {n for n in namen if namen.count(n) > 1}
            if doppelt:
                fehler.append(f"{name}: doppelte Knotennamen {sorted(doppelt)}")

            # 2) Verweise und 3) verschachtelte Ausdruecke
            ganze = text_von(ablauf)
            for verweis in set(re.findall(r"\$\('([^']+)'\)", ganze)):
                if verweis not in namen:
                    fehler.append(f"{name}: Verweis auf fehlenden Knoten '{verweis}'")
            for k in knoten:
                for feld, wert in durchsuchen(k.get("parameters", {})):
                    s = str(wert)
                    if s.startswith("="):
                        # Ganzer Ausdruck: im Rumpf darf kein "{{ ... }}" stecken,
                        # sonst sind zwei Ausdruecke verschachtelt (n8n kann das nicht).
                        rumpf = s[2:-2] if s.endswith("}}") else s[2:]
                        if "{{" in rumpf:
                            fehler.append(f"{name}/{k['name']}: verschachtelter Ausdruck in {feld}: "
                                          f"{rumpf[:90]}")

            # 4) Erreichbarkeit
            if ablauf.get("id") == KNOTEN:
                print("   (das ist die Zentrale selbst - kein Aufruf noetig)")
            elif KNOTEN in namen:
                erreichbar_von_konfig = erreichbar(ablauf, KNOTEN)
                braucher = [k["name"] for k in knoten
                            if f"$('{KNOTEN}')" in text_von(k.get("parameters", {}))]
                weit = [b for b in braucher if b not in erreichbar_von_konfig]
                unterknoten = [b for b in weit if ist_unterknoten(ablauf, b)]
                echt_weit = [b for b in weit if b not in unterknoten]
                if echt_weit:
                    fehler.append(f"{name}: brauchen die Werte, sind aber nicht erreichbar: {echt_weit}")
                print(f"   Konfiguration: {len(braucher)} Knoten holen Werte, "
                      f"{len(braucher) - len(weit)} sicher erreichbar, "
                      f"{len(unterknoten)} als Modell-/Werkzeugknoten (im Testlauf pruefen)")
                gefunden += 1
            else:
                fehler.append(f"{name}: Knoten '{KNOTEN}' fehlt")

    # 5) keine Zugangsdaten ausserhalb der Konfiguration
    konfig_pfad = os.path.join(ORDNER, "radio-konfiguration.json")
    if os.path.exists(konfig_pfad):
        js = json.dumps(lade(konfig_pfad), ensure_ascii=False)
        geheim = re.findall(r'"(?:schluessel|token)":\s*"([^"]{8,})"', js)
        # Auch Adressen gehoeren nur in die Zentrale - sonst schlaegt eine Umstellung
        # still fehl (so am 2026-09-22 passiert: "Meldungen holen" behielt die
        # feste Adresse, weil sie im Erzeuger weiter unten neu gesetzt wurde).
        adressen = [a for a in re.findall(r'"adresse":\s*"(https?://[^"]+)"', js)
                    if len(a) > 12]
        for datei in ["radio-werkzeuge.json", "radio-agent.json"]:
            pfad = os.path.join(ORDNER, datei)
            if not os.path.exists(pfad):
                continue
            inhalt = open(pfad, encoding="utf-8").read()
            offen = [g[:6] + "..." for g in geheim if g in inhalt]
            offen += [a for a in adressen if a in inhalt]
            if offen:
                fehler.append(f"{datei}: Werte ausserhalb der Konfiguration: {offen}")
            else:
                print(f"   {datei}: keine Zugangsdaten enthalten")

    print()
    if fehler:
        print("BEFUNDE (%d):" % len(fehler))
        for f in fehler:
            print("  -", f)
        raise SystemExit(1)
    print("Alles in Ordnung.")


def durchsuchen(obj, weg=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from durchsuchen(v, f"{weg}.{k}" if weg else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from durchsuchen(v, f"{weg}[{i}]")
    else:
        yield weg, obj


if __name__ == "__main__":
    main()
