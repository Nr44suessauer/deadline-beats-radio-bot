#!/usr/bin/env python3
"""Measures how loud the moderation sounds in the live program.

The way: record the stream while making a short test announcement during the broadcast,
speak into the transmitter, then evaluate the loudness (EBU R128) seconds values in the recording.
During the announcement the music is paused, therefore the loudest
segment is the voice - this allows comparing the voice directly with the music.

Call:  python3 24-live-level.py ["own text"]
Prerequisite: ssh access to 192.168.178.163 (AzuraCast) for ffmpeg.
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
ANSAGE = "http://192.168.178.53:8881/announce/text"
KEY = Path(__file__).resolve().parent.parent.parent / "news-key.txt"
SSH = ["ssh", "-i", "~/.ssh/id_ed25519",
       "-o", "StrictHostKeyChecking=no", "root@192.168.178.163"]
MIT = Path("/tmp/stream-mitschnitt.mp3")
DAUER = 45


def record() -> None:
    with urllib.request.urlopen(STREAM, timeout=30) as source, open(MIT, "wb") as target:
        ende = time.time() + DAUER
        while time.time() < ende:
            stueck = source.read(4096)
            if not stueck:
                break
            target.write(stueck)


def announcement(text: str) -> dict:
    body = json.dumps({"text": text}).encode()
    r = urllib.request.Request(ANSAGE, data=body,
                              headers={"Content-Type": "application/json",
                                       "X-News-key": KEY.read_text().strip()},
                              method="POST")
    return json.loads(urllib.request.urlopen(r, timeout=300).read().decode())


def fern(command: str) -> str:
    done = subprocess.run(SSH + [command], capture_output=True, text=True)
    return done.stdout


def fern_datei(path: Path, target: str) -> None:
    with open(path, "rb") as source:
        done = subprocess.run(SSH + [f"pct exec 106 -- docker exec -i azuracast bash -lc 'cat > {target}'"],
                                stdin=source, capture_output=True, text=True)
    if done.returncode:
        raise SystemExit("Transfer failed:" + done.stderr[:300])


def sekundenwerte(file: str) -> list[tuple[float, float]]:
    """[(Second, M in LUFS)] from ffmpeg ebur128."""
    out = fern(f"pct exec 106 -- docker exec azuracast ffmpeg -hide_banner -i {file} "
               "-filter_complex ebur128=peak=true -f null - 2>&1")
    werte = []
    for zeile in out.splitlines():
        if "TARGET:-23 LUFS" not in zeile:
            continue
        time = re.search(r"t:\s*([0-9.]+)", zeile)
        moment = re.search(r"M:\s*(-?[0-9.]+)", zeile)
        if time and moment:
            werte.append((float(time.group(1)), float(moment.group(1))))
    return werte


def main() -> int:
    text = sys.argv[1] if len(sys.argv) > 1 else "Test of loudness. One, two, three."
    print(f"Recording {DAUER} s, then test announcement: {text!r}")
    faden = threading.Thread(target=record)
    faden.start()
    time.sleep(5)
    answer = announcement(text)
    print(f"Announcement: {answer.get('duration_seconds')} s, said={answer.get('ok')}")
    faden.join()

    fern_datei(MIT, "/tmp/mitschnitt.mp3")
    werte = sekundenwerte("/tmp/mitschnitt.mp3")
    if not werte:
        raise SystemExit("no measurement values - check the recording")
    duration = werte[-1][0]
    still = [w for _, w in werte if w < -70]
    loud = [w for _, w in werte if w >= -70]
    print(f"\nSecond values ({len(werte)}, {duration:.0f} s): Music on average"
          f"{statistics.median(loud):.1f} LUFS, loudest value {max(loud):.1f} LUFS")
    print("Trend (Second: LUFS):")
    for sekunde, wert in werte:
        balken = "" if wert < -70 else "#" * max(int((wert + 40) / 1.5), 1)
        print(f" {sekunde:5.1f}: {wert:7.1f}  {balken}")
    print(f"\nSilent seconds: {len(still)} (Music pause during the announcement)")
    print(f"Music: Median {statistics.median(loud):.1f} LUFS | Voice (loudest value): {max(loud):.1f} LUFS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
