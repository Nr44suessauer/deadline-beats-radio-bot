#!/usr/bin/env python3
"""Legt Rahmen und Beschriftungen im Archiv-Ablauf "Radio - AI-Moderator" an.

Der Archiv-Ablauf stammt aus der ersten Fassung und wird vom Bauwerkzeug nicht
erzeugt - er hat deshalb weder Rahmen noch Notizen. Dieses Werkzeug ergaenzt sie
(additiv: kein Knoten, keine Verbindung, kein Text der Logik wird geaendert).

Aufruf:  python3 archiv-rahmen.py <ablauf.json> <ziel.json>
Danach:  docker exec -u node n8n n8n import:workflow --input=<ziel.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Bereiche: (Rahmenname, Titel+Beschreibung, Farbe, Knoten)
BEREICHE = [
    ("Notiz Eingaenge",
     "## Eingaenge\nVon Hand, per Formular oder von aussen starten - alles laeuft in "
     "dieselbe Kette.",
     4, ["Manuell", "Formular", "Webhook"]),
    ("Notiz Kontext",
     "## Kontext\nWas laeuft gerade, und was ist zuletzt passiert? Das ist die Grundlage "
     "fuer den Moderationstext.",
     5, ["Felder", "Jetzt laeuft", "Recherche"]),
    ("Notiz Text und Stimme",
     "## Text und Stimme\nAus dem Kontext wird ein Sprechtext, daraus eine fertige Datei.",
     6, ["Moderationstext", "Text saeubern", "Stimme", "Dateiname"]),
    ("Notiz Ausgabe",
     "## Ausgabe\nEntweder live sprechen (unterbricht das Programm kurz) oder hochladen "
     "(laeuft danach als eigener Titel).",
     7, ["Modus", "Live sprechen", "Hochladen"]),
    ("Notiz Nachverfolgung",
     "## Nachverfolgung\nNach dem Hochladen: warten, den Titel im Archiv finden, den "
     "Wunsch zuordnen und abgeben.",
     3, ["Warten", "Titel finden", "Zuordnen", "Wunsch abgeben", "Antwort"]),
    ("Notiz Alte Hilfsmittel",
     "## Alte Hilfsmittel\nReste der ersten Fassung - nicht angeschlossen, nur zur "
     "Erinnerung.",
     2, ["Treffer waehlen"]),
]

NOTIZEN = {
    "Manuell": "Von Hand starten (Prueflauf).",
    "Formular": "Start ueber das n8n-Formular: Titel, Wunschtext, Stimme.",
    "Webhook": "Start von aussen (Zeitplan oder fremdes Werkzeug).",
    "Felder": "Eingaben sammeln: Titel, Wunschtext, Stimme, Ansage ja/nein.",
    "Jetzt laeuft": "Was laeuft gerade am Sender? (AzuraCast)",
    "Recherche": "Meldungen und Kontext fuer die Moderation sammeln.",
    "Moderationstext": "Den Sprechtext vom Sprachmodell (Ollama) erzeugen lassen.",
    "Text saeubern": "Sprechtext aufbereiten: Links, Emoji, Abkuerzungen, Satzgrenze.",
    "Stimme": "Sprache erzeugen (Piper im Dienst radio-tts).",
    "Dateiname": "Dateinamen der Ansage bauen.",
    "Modus": "Ja = live sprechen, nein = hochladen.",
    "Live sprechen": "Die Ansage live in den DJ-Hafen sprechen.",
    "Hochladen": "Die Ansage als Titel hochladen (Weg ohne Unterbrechung).",
    "Warten": "Warten, bis der Sender den Titel verarbeitet hat.",
    "Titel finden": "Den frisch hochgeladenen Titel im Archiv suchen.",
    "Zuordnen": "Wunsch und gefundenen Titel einander zuordnen.",
    "Wunsch abgeben": "Den Wunsch beim Sender abgeben.",
    "Antwort": "Antwort fuer den Aufrufer bauen.",
    "Treffer waehlen": "Alter Helfer: ersten Treffer der Suche waehlen (nicht mehr verbunden).",
}

# Knotengroesse wie in anordnung-pruefen.py
GROESSE = {"n8n-nodes-base.if": (200, 110), "n8n-nodes-base.switch": (230, 110)}
RAND_X, RAND_OBEN, RAND_UNTEN = 70, 80, 60


def groesse(knoten: dict) -> tuple[int, int]:
    return GROESSE.get(knoten["type"], (110, 110))


def main() -> int:
    quelle, ziel = Path(sys.argv[1]), Path(sys.argv[2])
    rohdaten = json.loads(quelle.read_text(encoding="utf-8"))
    ablauf = rohdaten[0] if isinstance(rohdaten, list) else rohdaten
    nach_name = {k["name"]: k for k in ablauf["nodes"]}
    fehlend = [n for _, _, _, namen in BEREICHE for n in namen if n not in nach_name]
    if fehlend:
        raise SystemExit(f"Knoten fehlen im Ablauf: {fehlend}")

    # Alte Rahmen entfernen (nur Klebezettel - Logik bleibt unberuehrt)
    ablauf["nodes"] = [k for k in ablauf["nodes"]
                       if k["type"] != "n8n-nodes-base.stickyNote"]

    # 1) Rohe Kaesten je Bereich rechnen
    kaesten = []
    for name, text, farbe, namen in BEREICHE:
        xs0 = min(nach_name[n]["position"][0] for n in namen)
        ys0 = min(nach_name[n]["position"][1] for n in namen)
        xs1 = max(nach_name[n]["position"][0] + groesse(nach_name[n])[0] for n in namen)
        ys1 = max(nach_name[n]["position"][1] + groesse(nach_name[n])[1] for n in namen)
        kaesten.append({"name": name, "text": text, "farbe": farbe,
                        "kx0": xs0, "kx1": xs1, "ky0": ys0, "ky1": ys1,
                        "x0": xs0 - RAND_X, "x1": xs1 + RAND_X,
                        "y0": ys0 - RAND_OBEN, "y1": ys1 + RAND_UNTEN})

    # 2) Waagerecht beschneiden, wo sich Bereiche in der Hoehe treffen - sonst
    #    ueberlappen die Rahmen (die Knoten stehen nur 200 Einheiten auseinander).
    for a in kaesten:
        for b in kaesten:
            if a is b:
                continue
            trifft_hoehe = a["y0"] < b["y1"] and b["y0"] < a["y1"]
            if not trifft_hoehe:
                continue
            if a["kx1"] <= b["kx0"]:                      # a liegt links von b
                a["x1"] = min(a["x1"], b["x0"] - 8)
            elif b["kx1"] <= a["kx0"]:                    # b liegt links von a
                a["x0"] = max(a["x0"], b["x1"] + 8)

    for k in kaesten:
        if k["x0"] > k["kx0"] or k["x1"] < k["kx1"] or k["y0"] > k["ky0"] or k["y1"] < k["ky1"]:
            raise SystemExit(f"Rahmen zu klein gerechnet: {k['name']}")
        ablauf["nodes"].append({
            "parameters": {
                "content": k["text"],
                "height": k["y1"] - k["y0"],
                "width": k["x1"] - k["x0"],
                "color": k["farbe"],
            },
            "id": "notiz-" + k["name"].split()[-1].lower(),
            "name": k["name"],
            "type": "n8n-nodes-base.stickyNote",
            "typeVersion": 1,
            "position": [k["x0"], k["y0"]],
        })
        print(f"  Rahmen {k['name']:26s} x {k['x0']}..{k['x1']}  y {k['y0']}..{k['y1']}")

    for name, notiz in NOTIZEN.items():
        nach_name[name]["notes"] = notiz
        nach_name[name]["notesInFlow"] = True
    print(f"  Beschriftungen: {len(NOTIZEN)} Knoten")

    ziel.write_text(json.dumps(rohdaten if isinstance(rohdaten, list) else ablauf,
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Geschrieben: {ziel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
