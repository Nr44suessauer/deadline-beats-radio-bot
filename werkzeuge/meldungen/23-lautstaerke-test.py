#!/usr/bin/env python3
"""Prueft die Lautstaerke-Anpassung der Moderation (dienst/main.py).

Warum: Piper liefert volle Spitzen, aber weiten Abstand zum Effektivwert - die
Ansage klang neben dem hart begrenzten Musikprogramm rund 6 dB zu leise
(gemessen 2026-09-20: Musik -9,8 LUFS, Stimme -16,2 LUFS).

Der Prueflauf holt die echten Funktionen per AST aus `dienst/main.py` (der Dienst
selbst braucht fastapi/piper und laeuft nur im Container) und rechnet mit einer
rohen Piper-Probe. Zusaetzlich wird der laufende Dienst befragt, damit auch die
eingespielte Fassung geprueft ist.

Aufruf:  python3 23-lautstaerke-test.py [--ohne-dienst]
"""
from __future__ import annotations

import argparse
import ast
import array
import io
import json
import math
import sys
import urllib.request
import wave
from pathlib import Path

HIER = Path(__file__).resolve().parent
QUELLE = HIER.parent.parent / "dienst" / "main.py"
PROBE = HIER / "probe-stimme-roh.wav"
DIENST = "http://192.168.178.53:8881"

ok = 0
abweichend = 0


def pruefe(name: str, wert, bedingung) -> None:
    global ok, abweichend
    gut = bedingung(wert) if callable(bedingung) else wert == bedingung
    if gut:
        ok += 1
    else:
        abweichend += 1
    print(("ok   " if gut else "ABW. ") + name + ("" if gut else f"   ist: {wert!r}"))


def pegel(wav_daten: bytes) -> tuple[float, float, float]:
    """(Spitze dBFS, Effektivwert dBFS, Dauer s) uber alle Kanaele."""
    with wave.open(io.BytesIO(wav_daten), "rb") as w:
        rate, kanaele, breite, anzahl = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        roh = w.readframes(anzahl)
    a = array.array("h")
    a.frombytes(roh)
    if not len(a):
        return -99.0, -99.0, 0.0
    spitze = max(abs(x) for x in a) / 32768
    rms = math.sqrt(sum((x / 32768) ** 2 for x in a) / len(a))
    dB = lambda v: 20 * math.log10(v) if v > 0 else -99.0  # noqa: E731
    return dB(spitze), dB(rms), anzahl / rate


def sprech_rms(wav_daten: bytes, raum: dict) -> float:
    """Effektivwert der sprechenden Abschnitte - dieselbe Messung wie im Dienst.

    Wichtig: nicht ueber alle Samples messen. Die Pausen zwischen den Saetzen
    druecken den Wert um etwa 1 dB; das Ziel gilt fuer die Sprache selbst.
    """
    pcm, rate, kanaele = raum["_wav_als_pcm"](wav_daten)
    wert = raum["_sprech_rms"](pcm, rate, kanaele)
    return 20 * math.log10(wert) if wert > 0 else -99.0


def funktionen_laden() -> dict:
    """Zieht die Funktionen aus dem Dienst (der Dienst selbst braucht fastapi/piper).

    Das Ausfuehren der `def`-Bloecke ist harmlos: der Rumpf laeuft erst beim Aufruf,
    und aufgerufen wird nur die Lautstaerke-Kette.
    """
    baum = ast.parse(QUELLE.read_text(encoding="utf-8"))
    namen = {"lautstaerke_anpassen", "zusatz_verstaerkung_db", "ZIEL_RMS_DB", "BEGRENZER_DB"}
    raum: dict = {"array": array, "io": io, "math": math, "os": __import__("os"), "wave": wave}
    for knoten in baum.body:
        if isinstance(knoten, ast.Assign):
            ziele = [z.id for z in knoten.targets if isinstance(z, ast.Name)]
            # Regelwerte (GROSS) einfach ausfuehren - sie lesen nur die Umgebung.
            if ziele and ziele[0].isupper():
                modul = ast.Module(body=[knoten], type_ignores=[])
                try:
                    exec(compile(ast.fix_missing_locations(modul), str(QUELLE), "exec"), raum)
                except Exception:
                    pass
        if isinstance(knoten, ast.FunctionDef):
            # Dekoratoren (@app.get ...) wegwerfen - hier gibt es keine App.
            knoten.decorator_list = []
            modul = ast.Module(body=[knoten], type_ignores=[])
            try:
                exec(compile(ast.fix_missing_locations(modul), str(QUELLE), "exec"), raum)
            except Exception:
                pass
    fehlend = namen - set(raum)
    if fehlend:
        raise SystemExit(f"nicht gefunden in {QUELLE}: {sorted(fehlend)}")
    return raum


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ohne-dienst", action="store_true", help="nur mit der Probe rechnen")
    args = parser.parse_args()

    if not PROBE.exists():
        raise SystemExit(f"Probe fehlt: {PROBE} (rohe Piper-Aufnahme, siehe README)")
    raum = funktionen_laden()
    roh = PROBE.read_bytes()
    ziel = raum["ZIEL_RMS_DB"]
    decke = raum["BEGRENZER_DB"]

    spitze_roh, rms_roh, dauer = pegel(roh)
    print(f"Rohe Piper-Probe: {dauer:.1f} s | Spitze {spitze_roh:6.1f} dBFS | RMS {rms_roh:6.1f} dBFS")
    pruefe("rohe Probe ist wirklich leise (unter -14 dBFS RMS)", rms_roh, lambda v: v < -14)

    laut = raum["lautstaerke_anpassen"](roh)
    spitze_neu, rms_neu, _ = pegel(laut)
    sprache_neu = sprech_rms(laut, raum)
    print(f"Nach der Anpassung:  Spitze {spitze_neu:6.1f} dBFS | Sprache {sprache_neu:6.1f} dBFS "
          f"| ueber alles {rms_neu:6.1f} dBFS")
    pruefe(f"Pegel der Sprache trifft das Ziel ({ziel} dBFS +/- 1)", sprache_neu,
           lambda v: abs(v - ziel) <= 1.0)
    pruefe(f"Spitzen bleiben unter der Decke ({decke} dBFS)", spitze_neu, lambda v: v <= decke + 0.3)
    pruefe("deutlich lauter als vorher (mindestens +3 dB)", rms_neu - rms_roh, lambda v: v >= 3.0)
    pruefe("kein Uebersteuern (Spitze < 0 dBFS)", spitze_neu, lambda v: v < 0.0)

    # Zweimal anwenden darf nicht weiter hochziehen (der Dienst macht es genau einmal).
    nochmal = raum["lautstaerke_anpassen"](laut)
    _, rms_doppelt, _ = pegel(nochmal)
    pruefe("zweite Anwendung aendert nichts mehr (+/- 0,7 dB)", rms_doppelt - rms_neu,
           lambda v: abs(v) <= 0.7)

    if not args.ohne_dienst:
        rumpf = json.dumps({"input": "Und nun der Blick zum Himmel - ich habe für euch nachgesehen.", "voice": "",
                            "response_format": "wav"}).encode()
        r = urllib.request.Request(f"{DIENST}/v1/audio/speech", data=rumpf,
                                   headers={"Content-Type": "application/json"}, method="POST")
        dienst_wav = urllib.request.urlopen(r, timeout=60).read()
        spitze_d, rms_d, dauer_d = pegel(dienst_wav)
        sprache_d = sprech_rms(dienst_wav, raum)
        print(f"Laufender Dienst:    Spitze {spitze_d:6.1f} dBFS | Sprache {sprache_d:6.1f} dBFS "
              f"| ueber alles {rms_d:6.1f} dBFS | {dauer_d:.1f} s")
        pruefe("der Dienst liefert den Zielpegel", sprache_d, lambda v: abs(v - ziel) <= 1.0)
        pruefe("der Dienst begrenzt die Spitzen", spitze_d, lambda v: v <= decke + 0.3)

    print(f"\nErgebnis: {ok} ok, {abweichend} abweichend")
    return 1 if abweichend else 0


if __name__ == "__main__":
    sys.exit(main())
