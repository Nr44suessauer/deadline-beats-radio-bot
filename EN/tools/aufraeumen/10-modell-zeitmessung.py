#!/usr/bin/env python3
"""Measures how long a planning request takes to the agent model -
with and without the model thinking.

The request corresponds to the "Plan" level of the Radio Bot
(POST /v1/chat/completions, as the n8n node triggers it).
"""
import json
import time
import urllib.request
from pathlib import Path

OLLAMA = "http://192.168.178.187:11434"
MODELL = "qwen3.6:27b"

SYSTEM = Path("/tmp/PLANEN_SYSTEM.txt").read_text(encoding="utf-8")
AUFTRAG = "play Scooter Hyper Hyper"


def v1(body: dict) -> tuple[float, dict]:
    data = json.dumps(body).encode()
    request = urllib.request.Request(
        OLLAMA + "/v1/chat/completions", data=data,
        headers={"Content-Type": "application/json"},
    )
    start = time.time()
    with urllib.request.urlopen(request, timeout=300) as answer:
        result = json.loads(answer.read().decode())
    return time.time() - start, result


def zeige(name: str, duration: float, result: dict) -> None:
    nutzung = result.get("usage") or {}
    text = ((result.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    denkt = ((result.get("choices") or [{}])[0].get("message") or {}).get("reasoning_content") or ""
    print(f"{name:38s} {duration:6.1f}s   Output tokens: {nutzung.get('completion_tokens', '?'):>5}"
          f" Response: {len(text):>4} characters   Thinking text: {len(denkt):>5} characters")


basis = {
    "model": MODELL,
    "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": AUFTRAG + "\n/no_think"},
    ],
    "temperature": 0.2,
    "max_tokens": 3000,
}

for name, extra in [
    ("as in the bot (/no_think in the text)", {}),
    ("+ reasoning_effort: none", {"reasoning_effort": "none"}),
    ("+ think: false", {"think": False}),
    ("+ chat_template_kwargs", {"chat_template_kwargs": {"enable_thinking": False}}),
]:
    body = dict(basis)
    body.update(extra)
    try:
        duration, result = v1(body)
        zeige(name, duration, result)
    except Exception as error:  # noqa: BLE001
        print(f"{name:38s} ERROR: {error}")

# Second pass: is the second call faster (cache)?
duration, result = v1(basis)
zeige("as in the bot, second pass", duration, result)
