#!/usr/bin/env python3
"""Schreibt deutsche Texte in der n8n-Oberflaeche richtig (Umlaute statt ae/oe/ue).

Der Erzeuger hat die Beschriftungen bisher in ASCII geschrieben ("Pruefen",
"laeuft", "fuer"). Dieses Werkzeug ueberarbeitet nur die **sichtbaren Texte**:

  * Haftnotizen (Rahmen): parameters.content
  * Knoten-Beschriftungen: name (Verweise "node"/$('Name') werden mitgezogen)
  * Untertitel: notes

Nicht angefasst werden Parameter (Code, Prompts, Adressen) und alles, was wie
Datei- oder Befehlsname aussieht (Schutzliste unten) — "n8n-oberflaeche.html",
"--aufraeumen", "anordnung-pruefen.py" und "HANDBUCH.md" bleiben also, wie
sie sind.

Aufruf:
  python3 deutsch-texte.py --listen  datei.json [weitere ...]
  python3 deutsch-texte.py --anwenden datei.json [weitere ...] \
      [--umbenennen-datei /tmp/umbenennen.txt]

--listen zeigt nur, welche Woerter noch nicht in der Tabelle stehen (zum
Ergaenzen). --anwenden schreibt die Dateien zurueck und legt (fuer den Agenten)
die Liste "Alt=Neu" der umbenannten Knoten ab, die der Patcher braucht.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

# ---------------------------------------------------------------- Worttabelle
W = {
    "Eingaenge": "Eingänge", "eingaenge": "eingänge",
    "Ablaeufe": "Abläufe", "ablaeufe": "abläufe",
    "Vorschlaege": "Vorschläge", "vorschlaege": "vorschläge",
    "Vorschlaegen": "Vorschlägen", "vorschlaegen": "vorschlägen",
    "laeuft": "läuft", "Laeuft": "Läuft",
    "aendern": "ändern", "Aendern": "Ändern", "aendert": "ändert", "Aendert": "Ändert",
    "aenderung": "änderung", "Aenderung": "Änderung", "Aenderungen": "Änderungen",
    "Prueflauf": "Prüflauf", "prueflauf": "prüflauf",
    "spaeter": "später", "Spaeter": "Später",
    "traegt": "trägt", "Traegt": "Trägt",
    "haengt": "hängt", "Haengt": "Hängt", "haengen": "hängen", "Haengen": "Hängen",
    "waehlen": "wählen", "Waehlen": "Wählen", "waehlt": "wählt", "waehle": "wähle",
    "Naechster": "Nächster", "naechster": "nächster", "naechste": "nächste", "naechsten": "nächsten",
    "taete": "täte",
    "ausdruecklicher": "ausdrücklicher", "ausdruecklich": "ausdrücklich", "Ausdruecklich": "Ausdrücklich",
    "genuegt": "genügt", "Genuegt": "Genügt",
    "zurueck": "zurück", "Zurueck": "Zurück", "zurueckgeben": "zurückgeben",
    "Rueckgabe": "Rückgabe", "Rueckmeldung": "Rückmeldung", "Rueckfrage": "Rückfrage",
    "Schluessel": "Schlüssel", "schluessel": "schlüssel",
    "Knoepfe": "Knöpfe", "Knoepfen": "Knöpfen", "Knopfdruecke": "Knopfdrücke",
    "Zuhoerer": "Zuhörer", "zuhoerer": "zuhörer",
    "Anlaeufe": "Anläufe", "anlaeufe": "anläufe",
    "Zaehlt": "Zählt", "zaehlt": "zählt", "zaehlen": "zählen", "Zaehler": "Zähler",
    "Rundenzaehler": "Rundenzähler",
    "bestaetigt": "bestätigt", "Bestaetigt": "Bestätigt", "bestaetigen": "bestätigen",
    "Bestaetigung": "Bestätigung",
    "ausfuehren": "ausführen", "Ausfuehren": "Ausführen", "ausfuehrt": "ausführt",
    "Ausfuehrung": "Ausführung", "Ausfuehrungen": "Ausführungen",
    "pruefen": "prüfen", "Pruefen": "Prüfen", "prueft": "prüft", "Prueft": "Prüft",
    "Pruefung": "Prüfung", "Pruefungen": "Prüfungen",
    "Ueberblick": "Überblick", "ueberblick": "überblick",
    "Uebersicht": "Übersicht", "uebersicht": "übersicht",
    "ueber": "über", "Ueber": "Über",
    "fuer": "für", "Fuer": "Für",
    "saeubern": "säubern", "Saeubern": "Säubern", "saeubert": "säubert",
    "wuerde": "würde", "wuerden": "würden",
    "Koerper": "Körper", "koerper": "körper",
    "moeglich": "möglich", "Moeglich": "Möglich", "moeglichst": "möglichst",
    "Oberflaeche": "Oberfläche", "oberflaeche": "oberfläche",
    "zusaetzlich": "zusätzlich", "zusaetzliche": "zusätzliche",
    "waehrend": "während", "unabhaengig": "unabhängig",
    "aussen": "außen", "Aussen": "Außen",
    "gross": "groß", "Grosse": "Große", "groesser": "größer",
    "schliessen": "schließen", "Schliessen": "Schließen",
    "heisst": "heißt", "Laenge": "Länge", "laenge": "länge",
    "Auffaellig": "Auffällig",
    "Abkuerzungen": "Abkürzungen",
    "Geaendert": "Geändert", "geaendert": "geändert",
    "Gehoert": "Gehört", "gehoert": "gehört",
    "erklaert": "erklärt", "Erklaert": "Erklärt",
}

# Korrekte deutsche Wörter, die nur zufällig "ue" enthalten — nicht anfassen
IGNORE = {
    "Manuell", "manuell", "Quelle", "Quellen", "quellen", "Steuern", "steuern",
    "Steuerung", "Steuerbefehle", "Steuerungen", "bauen", "Bauen", "neue", "neuer",
    "neues", "Neues", "neuen", "neuem", "neuere", "neueren", "Dauer", "dauer",
    "zuerst", "Zuerst", "true", "Bauer", "Feuer", "deuten", "heute", "Leute",
}

# Was nie ersetzt wird (Dateinamen, Befehle, Kennungen)
SCHUTZ = [
    "n8n-oberflaeche", "FAEHIGKEITEN", "STOERUNGEN", "anordnung-pruefen",
    "code-pruefen", "--aufraeumen", "aufraeumen", "ausfuehrungen.sh",
    "import-agent-vorbereiten", "agent-wf-bauen", "pruefsumme",
]

MUSTER = re.compile(r"[A-Za-zÄÖÜäöüß]*(?:ae|oe|ue)[A-Za-zÄÖÜäöüß]*")


def schuetzen(text: str) -> tuple[str, dict[str, str]]:
    """Dateinamen/Befehle durch Platzhalter ersetzen (nur fuer die Bearbeitung)."""
    karte: dict[str, str] = {}
    for i, wort in enumerate(SCHUTZ):
        platz = f"@@{i}@@"
        if wort in text:
            text = text.replace(wort, platz)
            karte[platz] = wort
    # alles, was wie ein Dateiname aussieht
    def dateiname(m):
        platz = f"@@d{len(karte)}@@"
        karte[platz] = m.group(0)
        return platz

    text = re.sub(r"\S+\.(?:py|sh|json|md|html|service|yml|yaml|txt)\b", dateiname, text)
    # Kennungen mit Unterstrich (was_laeuft, titel_suchen ...)
    def kennung(m):
        platz = f"@@k{len(karte)}@@"
        karte[platz] = m.group(0)
        return platz

    text = re.sub(r"\b\w+_\w+\b", kennung, text)
    return text, karte


def entschuetzen(text: str, karte: dict[str, str]) -> str:
    # Platzhalter koennen sich verschachteln (@@d1@@ -> "@@0@@.html"),
    # deshalb mehrfach durchlaufen, bis sich nichts mehr aendert.
    for _ in range(8):
        vorher = text
        for platz, wort in karte.items():
            text = text.replace(platz, wort)
        if text == vorher:
            break
    return text


def waende(text: str, liste: list[str]) -> str:
    text, karte = schuetzen(text)
    for wort, ersatz in W.items():
        text = re.sub(rf"\b{re.escape(wort)}\b", ersatz, text)
    if liste is not None:
        for m in MUSTER.finditer(text):
            wort = m.group(0)
            if wort not in W and wort not in IGNORE:
                liste.append(wort)
    return entschuetzen(text, karte)


# kleine, ausdrueckliche Zeichenflaechen-Korrekturen
# Knoten auf klare Spaltenabstaende setzen (im Browser gemessen): die Rahmen
# sollen die Knoten samt Beschriftung wieder sauber einfassen.  Ein Knoten
# belegt 96x96, darunter die Beschriftung (192 breit) - deshalb 24 px Rand.
UMSTELLEN = {
    "bjFSfXGqpLg7AAXw": {
        "Manuell": [-660, -140], "Formular": [-660, 40], "Webhook": [-660, 260],
        "Felder": [-408, 40], "Jetzt läuft": [-208, 40], "Recherche": [-8, 40],
        "Moderationstext": [240, 40], "Text säubern": [440, 40],
        "Stimme": [640, 40], "Dateiname": [840, 40],
        "Modus": [1088, 40], "Live sprechen": [1308, -15], "Hochladen": [1308, 160],
        "Warten": [1556, 160], "Titel finden": [1748, 160], "Zuordnen": [1956, 160],
        "Wunsch abgeben": [2148, 160], "Antwort": [2356, 40],
        "Treffer wählen": [780, 1056],
    },
}
# Rahmen neu fassen: Position und Groesse absolut (alles im Browser gemessen;
# Beschriftungsblock = Knotenx-48 .. Knotenx+144, Unterkante = Knoteny+143).
RAHMEN = {
    "bjFSfXGqpLg7AAXw": {
        "Notiz Eingänge": [-732, -300, 240, 743],
        "Notiz Kontext": [-480, -72, 640, 295],
        "Notiz Text und Stimme": [168, -48, 840, 255],
        "Notiz Ausgabe": [1016, -151, 460, 478],
        "Notiz Nachverfolgung": [1484, -40, 1040, 367],
        "Notiz Alte Hilfsmittel": [708, 908, 240, 315],
        "Notiz Doku": [-732, -496, 1150, 172],
    },
}
HOEHEN = {  # Kennung -> {Notizname: neue Hoehe}
    "Konfiguration": {"Notiz Doku": 172},
}


def bearbeite(ablauf: dict, liste: list[str]) -> set[str]:
    geaendert: set[str] = set()
    for k in ablauf["nodes"]:
        if "stickyNote" in k["type"]:
            alt = k.get("parameters", {}).get("content", "")
            neu = waende(alt, liste)
            k["parameters"]["content"] = neu
        if k.get("notes"):
            k["notes"] = waende(k["notes"], liste)
        neuer_name = waende(k["name"], liste)
        if neuer_name != k["name"]:
            geaendert.add(k["name"])
            k["name"] = neuer_name
    if geaendert:
        # Verweise nachziehen (Verbindungen und Ausdruecke)
        text = json.dumps(ablauf, ensure_ascii=False)
        for alt in geaendert:
            neu = waende(alt, [])
            text = text.replace(f'"{alt}":', f'"{neu}":')          # Quellschluessel (connections/pinData)
            text = text.replace(f'"node": "{alt}"', f'"node": "{neu}"')  # Ziel in Verbindungen
            text = text.replace(f"$('{alt}')", f"$('{neu}')")
            text = text.replace(f'$("{alt}")', f'$("{neu}")')
        ersetzt = json.loads(text)
        ablauf.clear()
        ablauf.update(ersetzt)
    for name, pos in UMSTELLEN.get(ablauf.get("id"), {}).items():
        for k in ablauf["nodes"]:
            if k["name"] == name:
                k["position"] = list(pos)
    for name, kasten in RAHMEN.get(ablauf.get("id"), {}).items():
        for k in ablauf["nodes"]:
            if "stickyNote" in k["type"] and k["name"] == name:
                k["position"] = [kasten[0], kasten[1]]
                k["parameters"]["width"] = kasten[2]
                k["parameters"]["height"] = kasten[3]
    for name, hoehe in HOEHEN.get(ablauf.get("id"), {}).items():
        for k in ablauf["nodes"]:
            if "stickyNote" in k["type"] and k["name"] == name:
                k["parameters"]["height"] = hoehe
    return geaendert


def main() -> int:
    z = argparse.ArgumentParser()
    z.add_argument("--listen", action="store_true")
    z.add_argument("--anwenden", action="store_true")
    z.add_argument("--umbenennen-datei", default="")
    z.add_argument("dateien", nargs="+")
    a = z.parse_args()
    liste: list[str] = []
    umbenannt: list[str] = []
    for pfad in a.dateien:
        daten = json.loads(open(pfad, encoding="utf-8").read())
        flach = daten if isinstance(daten, list) else [daten]
        for ablauf in flach:
            geaendert = bearbeite(ablauf, liste)
            if a.anwenden and geaendert:
                print(f"  {ablauf.get('name')}: {sorted(geaendert)}")
            if a.anwenden and ablauf.get("id") == "RadioAgentBot":
                for alt in sorted(geaendert):
                    umbenannt.append(f"{alt}={waende(alt, [])}")
        if a.anwenden:
            open(pfad, "w", encoding="utf-8").write(json.dumps(daten, ensure_ascii=False, indent=2))
    if a.umbenennen_datei:
        open(a.umbenennen_datei, "w", encoding="utf-8").write(",".join(umbenannt))
        print("Umbenennungen:", len(umbenannt), "->", a.umbenennen_datei)
    if liste:
        von = sorted(set(liste))
        print(f"{len(von)} Wortformen noch ohne Regel:")
        for w in von:
            print("   ", w)
        return 1
    print("Fertig — alle Wortformen sind abgedeckt." if a.listen else "Fertig.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
