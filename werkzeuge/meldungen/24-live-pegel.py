#!/usr/bin/env python3
"""Misst, wie laut die Moderation im laufenden Programm ankommt.

Der Weg: den Stream mitschneiden, waehrend der Ansage eine kurze Testansage in
den Sender sprechen, dann im Mitschnitt die Sekundenwerte der Lautheit (EBU R128)
auswerten. Waehrend der Ansage pausiert die Musik, deshalb ist der lauteste
Abschnitt die Stimme - so laesst sich die Stimme direkt mit der Musik vergleichen.

Aufruf:  python3 24-live-pegel.py ["eigener Text"]
Voraussetzung: ssh-Zugang zu 192.168.178.163 (AzuraCast) fuer ffmpeg.
"""
from __future__ import annotations

import json
import re
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

STREAM = "http://192.168.178.33/listen/deadline_beats/radio.mp3"
ANSAGE = "http://192.168.178.53:8881/ansage/text"
SCHLUESSEL = Path(__file__).resolve().parent.parent.parent / "NACHBAU/zugangsdaten/meldung-schluessel.txt"
SSH = ["ssh", "-i", "~/.ssh/id_ed25519",
       "-o", "StrictHostKeyChecking=no", "root@192.168.178.163"]
MIT = Path("/tmp/stream-mitschnitt.mp3")
DAUER = 45


def aufnehmen() -> None:
    with urllib.request.urlopen(STREAM, timeout=30) as quelle, open(MIT, "wb") as ziel:
        ende = time.time() + DAUER
        while time.time() < ende:
            stueck = quelle.read(4096)
            if not stueck:
                break
            ziel.write(stueck)


def ansage(text: str) -> dict:
    rumpf = json.dumps({"text": text}).encode()
    r = urllib.request.Request(ANSAGE, data=rumpf,
                              headers={"Content-Type": "application/json",
                                       "X-Meldung-Schluessel": SCHLUESSEL.read_text().strip()},
                              method="POST")
    return json.loads(urllib.request.urlopen(r, timeout=300).read().decode())


def fern(befehl: str) -> str:
    fertig = subprocess.run(SSH + [befehl], capture_output=True, text=True)
    return fertig.stdout


def fern_datei(pfad: Path, ziel: str) -> None:
    with open(pfad, "rb") as quelle:
        fertig = subprocess.run(SSH + [f"pct exec 106 -- docker exec -i azuracast bash -lc 'cat > {ziel}'"],
                                stdin=quelle, capture_output=True, text=True)
    if fertig.returncode:
        raise SystemExit("Uebertragen fehlgeschlagen: " + fertig.stderr[:300])


def sekundenwerte(datei: str) -> list[tuple[float, float]]:
    """[(Sekunde, M in LUFS)] aus ffmpeg ebur128."""
    aus = fern(f"pct exec 106 -- docker exec azuracast ffmpeg -hide_banner -i {datei} "
               "-filter_complex ebur128=peak=true -f null - 2>&1")
    werte = []
    for zeile in aus.splitlines():
        if "TARGET:-23 LUFS" not in zeile:
            continue
        zeit = re.search(r"t:\s*([0-9.]+)", zeile)
        moment = re.search(r"M:\s*(-?[0-9.]+)", zeile)
        if zeit and moment:
            werte.append((float(zeit.group(1)), float(moment.group(1))))
    return werte


def main() -> int:
    text = sys.argv[1] if len(sys.argv) > 1 else "Test der Lautstaerke. Eins, zwei, drei."
    print(f"Mitschnitt {DAUER} s, danach Testansage: {text!r}")
    faden = threading.Thread(target=aufnehmen)
    faden.start()
    time.sleep(5)
    antwort = ansage(text)
    print(f"Ansage: {antwort.get('dauer_sekunden')} s, gesagt={antwort.get('ok')}")
    faden.join()

    fern_datei(MIT, "/tmp/mitschnitt.mp3")
    werte = sekundenwerte("/tmp/mitschnitt.mp3")
    if not werte:
        raise SystemExit("keine Messwerte - Mitschnitt pruefen")
    dauer = werte[-1][0]
    still = [w for _, w in werte if w < -70]
    laut = [w for _, w in werte if w >= -70]
    print(f"\nSekundenwerte ({len(werte)}, {dauer:.0f} s): Musik im Mittel "
          f"{statistics.median(laut):.1f} LUFS, lautester Wert {max(laut):.1f} LUFS")
    print("Verlauf (Sekunde: LUFS):")
    for sekunde, wert in werte:
        balken = "" if wert < -70 else "#" * max(int((wert + 40) / 1.5), 1)
        print(f"  {sekunde:5.1f}: {wert:7.1f}  {balken}")
    print(f"\nStille Sekunden: {len(still)} (Musikpause waehrend der Ansage)")
    print(f"Musik: Median {statistics.median(laut):.1f} LUFS | Stimme (lautester Wert): {max(laut):.1f} LUFS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
