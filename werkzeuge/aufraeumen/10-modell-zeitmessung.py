#!/usr/bin/env python3
"""Misst, wie lange eine Planungs-Anfrage an das Agenten-Modell dauert -
mit und ohne Nachdenken des Modells.

Die Anfrage entspricht der Stufe "Planen" des Radio-Bots
(POST /v1/chat/completions, wie sie der n8n-Knoten absetzt).
"""
import json
import time
import urllib.request
from pathlib import Path

OLLAMA = "http://192.168.178.187:11434"
MODELL = "qwen3.6:27b"

SYSTEM = Path("/tmp/PLANEN_SYSTEM.txt").read_text(encoding="utf-8")
AUFTRAG = "spiele Scooter Hyper Hyper"


def v1(koerper: dict) -> tuple[float, dict]:
    daten = json.dumps(koerper).encode()
    anfrage = urllib.request.Request(
        OLLAMA + "/v1/chat/completions", data=daten,
        headers={"Content-Type": "application/json"},
    )
    start = time.time()
    with urllib.request.urlopen(anfrage, timeout=300) as antwort:
        ergebnis = json.loads(antwort.read().decode())
    return time.time() - start, ergebnis


def zeige(name: str, dauer: float, ergebnis: dict) -> None:
    nutzung = ergebnis.get("usage") or {}
    text = ((ergebnis.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    denkt = ((ergebnis.get("choices") or [{}])[0].get("message") or {}).get("reasoning_content") or ""
    print(f"{name:38s} {dauer:6.1f}s   Ausgabe-Token: {nutzung.get('completion_tokens', '?'):>5}"
          f"   Antwort: {len(text):>4} Zeichen   Denktext: {len(denkt):>5} Zeichen")


basis = {
    "model": MODELL,
    "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": AUFTRAG + "\n/no_think"},
    ],
    "temperature": 0.2,
    "max_tokens": 3000,
}

for name, zusatz in [
    ("wie im Bot (/no_think im Text)", {}),
    ("+ reasoning_effort: none", {"reasoning_effort": "none"}),
    ("+ think: false", {"think": False}),
    ("+ chat_template_kwargs", {"chat_template_kwargs": {"enable_thinking": False}}),
]:
    koerper = dict(basis)
    koerper.update(zusatz)
    try:
        dauer, ergebnis = v1(koerper)
        zeige(name, dauer, ergebnis)
    except Exception as fehler:  # noqa: BLE001
        print(f"{name:38s} FEHLER: {fehler}")

# Zweiter Durchlauf: ist der zweite Aufruf schneller (Zwischenspeicher)?
dauer, ergebnis = v1(basis)
zeige("wie im Bot, zweiter Durchlauf", dauer, ergebnis)
