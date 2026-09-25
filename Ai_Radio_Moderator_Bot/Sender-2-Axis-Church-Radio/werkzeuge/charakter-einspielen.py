#!/usr/bin/env python3
"""Spielt den Charakter der Stimme in die laufende Zentrale ("Konfiguration") ein.

Die Charakterdatei (Vorgabe: charakter.md neben dieser Ausgabe) bestimmt, WIE die Figur
spricht - nicht, WAS der Bot tut. Sie landet beim Bauen in der Zentrale im Feld
"charakter" und wirkt zur Laufzeit: im Hauptbot formuliert der Knoten "Planen" damit die
GESPROCHENEN Ansagen (die Telegram-Antworten bleiben sachlich), in der DDD-Fassung haengen
die Agenten der Ausfuehrung den Text an ihren Systemtext an. Dieses Werkzeug aendert NUR
diesen einen Wert im laufenden Ablauf - ohne Neubau, ohne Neustart:

  1. Charakterdatei lesen (Zeilen mit # am Anfang sind Notizen und fallen weg)
  2. laufende Zentrale aus n8n holen (Export in den n8n-Container)
  3. im Knoten "Werte" genau das Feld "charakter" ersetzen
  4. zurueck importieren, einschalten und gegenpruefen

Welche Ausgabe gemeint ist, ergibt sich aus dem Ort dieses Werkzeugs:
  Sender-1-Deadline-Beats/werkzeuge/charakter-einspielen.py    -> "Konfiguration"             (Sender 1)
  Sender-2-Axis-Church-Radio/werkzeuge/charakter-einspielen.py -> "DDD-Webseite-Konfiguration" (Sender 2)

Aufruf:
  python3 werkzeuge/charakter-einspielen.py            (Datei + Einspielen)
  python3 werkzeuge/charakter-einspielen.py --trocken  (nur zeigen, nichts aendern)
  python3 werkzeuge/charakter-einspielen.py --datei PFAD

Hinweise:
* Leerer Charaktertext (nur #-Zeilen) schaltet die Rolle ab.
* Vor dem Aendern wird die laufende Fassung lokal gesichert (Pfad wird ausgegeben);
  schlaegt der Import fehl, wird die Sicherung automatisch zurueckgespielt.
* Ein kompletter Neubau (agent-patchen.sh bzw. bauen.sh) liest dieselbe Datei.
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
AUSGABE = HIER.parent                                   # Sender-1-… bzw. Sender-2-Axis-Church-Radio
WEBSEITE = AUSGABE.name in ("Sender-2-Axis-Church-Radio", "DDD-Webseite")
WORKFLOW = "DDD-Webseite-Konfiguration" if WEBSEITE else "Konfiguration"
AGENT = "DDD-Webseite-Bot" if WEBSEITE else "RadioAgentBot"
KNOTEN = "Werte"
PROJEKT = "rQ6DFC63JlNQbiar"                            # n8n-Projekt der beiden Bots
CFG = "/media/discData/docs/projects/proxmox-ssh/config"
RECHNER = "ai-server"
CONTAINER = "n8n"
DATEI_STANDARD = AUSGABE / "charakter.md"
MARKE = "const KONFIG = "
SCHLUSS = ";\n\n// Abgeleitete Adressen"


def ssh(befehl: str, eingabe: str | None = None) -> str:
    """Befehl ueber den Proxmox-Zugang ausfuehren (Arbeitsplatz -> ai-server -> LXC 103)."""
    lauf = subprocess.run(["ssh", "-F", CFG, RECHNER, befehl],
                          input=eingabe, capture_output=True, text=True)
    if lauf.returncode != 0:
        raise SystemExit("ABBRUCH: ssh fehlgeschlagen:\n" + (lauf.stderr or lauf.stdout).strip())
    return lauf.stdout


def exportieren(kennung: str, ziel: str) -> dict:
    """Einen Ablauf aus n8n holen; prueft, dass wirklich die erwartete Kennung kam."""
    text = ssh("pct exec 103 -- bash -lc '"
               "docker exec -u node %s n8n export:workflow --id=%s --output=%s >/dev/null 2>&1; "
               "docker exec %s cat %s'" % (CONTAINER, kennung, ziel, CONTAINER, ziel))
    try:
        daten = json.loads(text)
    except json.JSONDecodeError:
        raise SystemExit("ABBRUCH: Export von %s lieferte kein JSON (Ablauf vorhanden?)." % kennung)
    ablauf = daten[0] if isinstance(daten, list) else daten
    if ablauf.get("id") != kennung:
        raise SystemExit("ABBRUCH: Export lieferte %s statt %s." % (ablauf.get("id"), kennung))
    return ablauf


def importieren(daten: dict, name: str) -> None:
    """Ablauf in n8n einspielen und einschalten (nur die Zentrale, kein Neustart)."""
    text = json.dumps(daten, ensure_ascii=False, indent=2)
    ssh("pct exec 103 -- bash -c 'cat > /tmp/%s'" % name, eingabe=text)
    ausgabe = ssh("pct exec 103 -- bash -lc '"
                  "docker cp /tmp/%s %s:/tmp/ >/dev/null && "
                  "docker exec -u node %s n8n import:workflow --input=/tmp/%s --projectId=%s && "
                  "docker exec -u node %s n8n update:workflow --id=%s --active=true | tail -1'"
                  % (name, CONTAINER, CONTAINER, name, PROJEKT, CONTAINER, WORKFLOW))
    for zeile in (ausgabe or "").strip().splitlines()[-2:]:
        print("   n8n:", zeile.strip())


def lese_charakter(pfad: Path) -> str:
    """Charaktertext aus der Datei lesen; Zeilen mit # am Anfang sind Notizen."""
    if not pfad.exists():
        raise SystemExit("ABBRUCH: Charakterdatei fehlt: %s" % pfad)
    zeilen = [z for z in pfad.read_text(encoding="utf-8").splitlines()
              if not z.lstrip().startswith("#")]
    return "\n".join(zeilen).strip()


def feld_setzen(ablauf: dict, text: str) -> tuple[dict, str]:
    """Im Knoten "Werte" das Feld "charakter" ersetzen; gibt (Ablauf, alter Text)."""
    knoten = [k for k in ablauf.get("nodes", []) if k.get("name") == KNOTEN]
    if not knoten:
        raise SystemExit("ABBRUCH: Knoten %r nicht gefunden." % KNOTEN)
    js = knoten[0].get("parameters", {}).get("jsCode", "")
    if MARKE not in js or SCHLUSS not in js:
        raise SystemExit("ABBRUCH: Der Knoten %r hat die erwartete Form nicht.\n"
                         "   Erst den Bot neu bauen und einspielen - die laufende Fassung "
                         "kennt das Feld noch nicht." % KNOTEN)
    anfang = js.index(MARKE) + len(MARKE)
    ende = js.index(SCHLUSS, anfang)
    werte = json.loads(js[anfang:ende])
    alt = str(werte.get("charakter", ""))
    werte["charakter"] = text
    knoten[0]["parameters"]["jsCode"] = (js[:anfang]
                                         + json.dumps(werte, ensure_ascii=False, indent=2)
                                         + js[ende:])
    return ablauf, alt


def kurz(text: str, laenge: int = 90) -> str:
    text = " | ".join(z.strip() for z in text.strip().splitlines())
    return text[:laenge] + ("..." if len(text) > laenge else "")


def main() -> int:
    zerleger = argparse.ArgumentParser(description="Charakter der Stimme einspielen")
    zerleger.add_argument("--datei", type=Path, default=DATEI_STANDARD,
                          help="Charakterdatei (Vorgabe: %s)" % DATEI_STANDARD)
    zerleger.add_argument("--trocken", action="store_true",
                          help="nur zeigen, was sich aendern wuerde (nichts schreiben)")
    args = zerleger.parse_args()

    text = lese_charakter(args.datei)
    print("Ausgabe  : %s" % AUSGABE)
    print("Ablauf   : %s (n8n)" % WORKFLOW)
    print("Datei    : %s" % args.datei)
    print("Charakter: %s" % ("AUS (leer)" if not text else "%d Zeichen" % len(text)))
    if text:
        print("           %s" % kurz(text))

    print("--- laufende Fassung holen")
    ablauf = exportieren(WORKFLOW, "/tmp/charakter-laufend.json")
    original = copy.deepcopy(ablauf)                     # fuer Sicherung und Rueckweg
    ablauf, alt = feld_setzen(ablauf, text)
    print("   bisher   : %s" % ("(leer)" if not alt.strip() else kurz(alt)))

    if args.trocken:
        print("Trockenlauf - nichts geaendert.")
        return 0

    sicherung = Path("/tmp/charakter-sicherung-%s-%s.json"
                     % (WORKFLOW, time.strftime("%Y%m%d-%H%M%S")))
    sicherung.write_text(json.dumps(original, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Sicherung: %s" % sicherung)

    if alt == text:
        print("Unveraendert - die Datei steht schon so in der Zentrale "
              "(kein Schreibzugriff noetig).")
    else:
        print("--- einspielen")
        try:
            importieren(ablauf, "charakter-neu.json")
        except SystemExit as fehler:
            print("   Import fehlgeschlagen - die Sicherung wird zurueckgespielt.")
            importieren(original, "charakter-sicherung.json")
            raise fehler

        print("--- gegenpruefen")
        frisch = exportieren(WORKFLOW, "/tmp/charakter-kontrolle.json")
        jetzt = _gegenprobe(frisch)
        if jetzt != text:
            print("   ACHTUNG: Der Wert in n8n weicht ab (Sicherung: %s)." % sicherung)
            return 1
        print("   Zentrale traegt den neuen Charakter (%d Zeichen)." % len(text))

    agent = exportieren(AGENT, "/tmp/charakter-agent.json")
    wirksam = "konfig.charakter" in json.dumps(agent, ensure_ascii=False)
    print("   Charakter ist im Ablauf verdrahtet: %s"
          % ("ja" if wirksam else "NEIN - Agent erst neu bauen und einspielen!"))
    print("\nFertig." + (" Der neue Charakter wirkt ab sofort (kein Neustart noetig)."
                        if alt != text else ""))
    return 0


def _gegenprobe(ablauf: dict) -> str:
    """Hilfsgriff: den Wert aus der frisch geholten Fassung lesen (ohne ihn zu setzen)."""
    knoten = [k for k in ablauf.get("nodes", []) if k.get("name") == KNOTEN][0]
    js = knoten["parameters"]["jsCode"]
    anfang = js.index(MARKE) + len(MARKE)
    ende = js.index(SCHLUSS, anfang)
    return str(json.loads(js[anfang:ende]).get("charakter", ""))


if __name__ == "__main__":
    sys.exit(main())
