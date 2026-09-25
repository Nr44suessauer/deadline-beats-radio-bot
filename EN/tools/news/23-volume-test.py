#!/usr/bin/env python3
"""Checks the loudness adjustment of the moderation (service/main.py).

Why: Piper delivers full peaks, but wide distance to the RMS value - the
announcement sounded about 6 dB too quiet next to the hard limited music program
(measured 2026-09-20: Music -9.8 LUFS, Voice -16.2 LUFS).

The test run fetches the actual functions via AST from `service/main.py` (the service
itself requires fastapi/piper and only runs inside a container) and calculates with a
raw Piper sample. Additionally, the running service is queried so that also the
recorded version is checked.

Call:  python3 23-volume-test.py [--no-service]
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
QUELLE = HIER.parent.parent / "service" / "main.py"
PROBE = HIER / "probe-voice-raw.wav"
SERVICE = "http://192.168.178.53:8881"

ok = 0
abweichend = 0


def check(name: str, wert, condition) -> None:
    global ok, abweichend
    good = condition(wert) if callable(condition) else wert == condition
    if good:
        ok += 1
    else:
        abweichend += 1
    print(("ok   " if good else "ABW. ") + name + ("" if good else f" is: {wert!r}"))


def level(wav_daten: bytes) -> tuple[float, float, float]:
    """(Peak dBFS, RMS value dBFS, Duration s) across all channels."""
    with wave.open(io.BytesIO(wav_daten), "rb") as w:
        rate, kanaele, breite, count = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(count)
    a = array.array("h")
    a.frombytes(raw)
    if not len(a):
        return -99.0, -99.0, 0.0
    spitze = max(abs(x) for x in a) / 32768
    rms = math.sqrt(sum((x / 32768) ** 2 for x in a) / len(a))
    dB = lambda v: 20 * math.log10(v) if v > 0 else -99.0  # noqa: E731
    return dB(spitze), dB(rms), count / rate


def sprech_rms(wav_daten: bytes, raum: dict) -> float:
    """RMS value of the speaking sections - same measurement as in the service.

 Important: do not measure over all samples. The pauses between the sentences
 push the value down by about 1 dB; the target applies to the speech itself.
    """
    pcm, rate, kanaele = raum["_wav_als_pcm"](wav_daten)
    wert = raum["_sprech_rms"](pcm, rate, kanaele)
    return 20 * math.log10(wert) if wert > 0 else -99.0


def funktionen_laden() -> dict:
    """Extracts the functions from the service (the service itself requires fastapi/piper).

 Executing the `def` blocks is harmless: the body only runs upon call,
 and only the loudness chain is called.
    """
    baum = ast.parse(QUELLE.read_text(encoding="utf-8"))
    names = {"lautstaerke_anpassen", "zusatz_verstaerkung_db", "ZIEL_RMS_DB", "BEGRENZER_DB"}
    raum: dict = {"array": array, "io": io, "math": math, "os": __import__("os"), "wave": wave}
    for nodes in baum.body:
        if isinstance(nodes, ast.Assign):
            targets = [z.id for z in nodes.targets if isinstance(z, ast.Name)]
            # Rule values (UPPERCASE) simply execute - they only read the environment.
            if targets and targets[0].isupper():
                modul = ast.Module(body=[nodes], type_ignores=[])
                try:
                    exec(compile(ast.fix_missing_locations(modul), str(QUELLE), "exec"), raum)
                except Exception:
                    pass
        if isinstance(nodes, ast.FunctionDef):
            # Strip decorators (@app.get ...) - there is no app here.
            nodes.decorator_list = []
            modul = ast.Module(body=[nodes], type_ignores=[])
            try:
                exec(compile(ast.fix_missing_locations(modul), str(QUELLE), "exec"), raum)
            except Exception:
                pass
    missing = names - set(raum)
    if missing:
        raise SystemExit(f"not found in {QUELLE}: {sorted(missing)}")
    return raum


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-service", action="store_true", help="only calculate with the sample")
    args = parser.parse_args()

    if not PROBE.exists():
        raise SystemExit(f"Sample missing: {PROBE} (raw Piper recording, see README)")
    raum = funktionen_laden()
    raw = PROBE.read_bytes()
    target = raum["ZIEL_RMS_DB"]
    decke = raum["BEGRENZER_DB"]

    spitze_roh, rms_roh, duration = level(raw)
    print(f"Raw Piper sample: {duration:.1f} s | Peak {spitze_roh:6.1f} dBFS | RMS {rms_roh:6.1f} dBFS")
    check("raw sample is really quiet (under -14 dBFS RMS)", rms_roh, lambda v: v < -14)

    loud = raum["lautstaerke_anpassen"](raw)
    spitze_neu, rms_neu, _ = level(loud)
    sprache_neu = sprech_rms(loud, raum)
    print(f"After adjustment:  Peak {spitze_neu:6.1f} dBFS | Speech {sprache_neu:6.1f} dBFS"
          f"| over everything {rms_neu:6.1f} dBFS")
    check(f"Speech level hits the target ({target} dBFS +/- 1)", sprache_neu,
           lambda v: abs(v - target) <= 1.0)
    check(f"Peaks stay under the ceiling ({decke} dBFS)", spitze_neu, lambda v: v <= decke + 0.3)
    check("significantly louder than before (at least +3 dB)", rms_neu - rms_roh, lambda v: v >= 3.0)
    check("no clipping (peak < 0 dBFS)", spitze_neu, lambda v: v < 0.0)

    # Applying twice must not increase further (the service does it exactly once).
    again = raum["lautstaerke_anpassen"](loud)
    _, rms_doppelt, _ = level(again)
    check("second application changes nothing anymore (+/- 0.7 dB)", rms_doppelt - rms_neu,
           lambda v: abs(v) <= 0.7)

    if not args.ohne_dienst:
        body = json.dumps({"input": "And now the view on the weather.", "voice": "",
                            "response_format": "wav"}).encode()
        r = urllib.request.Request(f"{SERVICE}/v1/audio/speech", data=body,
                                   headers={"Content-Type": "application/json"}, method="POST")
        dienst_wav = urllib.request.urlopen(r, timeout=60).read()
        spitze_d, rms_d, dauer_d = level(dienst_wav)
        sprache_d = sprech_rms(dienst_wav, raum)
        print(f"Running service:    Peak {spitze_d:6.1f} dBFS | Speech {sprache_d:6.1f} dBFS"
              f"| over everything {rms_d:6.1f} dBFS | {dauer_d:.1f} s")
        check("the service provides the target level", sprache_d, lambda v: abs(v - target) <= 1.0)
        check("the service limits the peaks", spitze_d, lambda v: v <= decke + 0.3)

    print(f"\nResult: {ok} ok, {abweichend} deviating")
    return 1 if abweichend else 0


if __name__ == "__main__":
    sys.exit(main())
