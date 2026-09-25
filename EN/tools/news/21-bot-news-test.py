#!/usr/bin/env python3
"""Checks the message paths from end to end via the bot (real operator chat).

Procedure:
 1. The search bot places messages (here simulated: POST to the service).
 2. The buttons of the message card are simulated (Read out / Discard) -
 "Read out" actually speaks into the transmitter (short text!).
 3. Telegram approval is checked (response of the last node).
 4. The schedule (every 5 minutes) is checked: it marks the message as
 offered - here we wait for it.

Call:
    python3 21-bot-news-test.py            # without announcement (buttons only discard)
    python3 21-bot-news-test.py --live     # with a real announcement
    python3 21-bot-news-test.py --wait   # additionally wait for the schedule
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

SERVICE = os.environ.get("MELDUNG_DIENST", "http://192.168.178.53:8881")
BOT = os.environ.get("BOT_WEBHOOK", "http://192.168.178.53:5678/webhook/YOUR-WEBHOOK-PATH")
RADIO = Path("<dokuordner>")
KEY = (RADIO / "news-key.txt").read_text(encoding="utf-8").strip()
TESTSCHLUESSEL = (RADIO / "bot-test-key.txt").read_text(encoding="utf-8").strip()
CHAT = "YOUR-CHAT-ID"
LIVE = "--live" in sys.argv
WARTEN = "--wait" in sys.argv

good = bad = 0
letzte_nachricht = {"id": None}


def check(condition: bool, description: str, extra: str = "") -> None:
    global good, bad
    if condition:
        good += 1
        print(f"ok   {description}")
    else:
        bad += 1
        print(f"ABW. {description}" + (f"\n       {extra}" if extra else ""))


def service(path: str, body: dict | None = None, method: str = "GET") -> tuple[int, dict]:
    kopf = {"X-News-key": KEY, "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(SERVICE + path, data=data, headers=kopf, method=method)
    with urllib.request.urlopen(request, timeout=300) as answer:
        return answer.status, json.loads(answer.read().decode() or "{}")


def bot(body: dict, duration: int = 300) -> dict:
    target = f"{BOT}?key={TESTSCHLUESSEL}"
    request = urllib.request.Request(target, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=duration) as answer:
        return json.loads(answer.read().decode() or "{}")


def zeige(result: dict, description: str, start: float) -> str:
    inhalt = result.get("result") if isinstance(result.get("result"), dict) else None
    if inhalt and inhalt.get("message_id"):
        letzte_nachricht["id"] = inhalt["message_id"]
    news = (inhalt or {}).get("text") or result.get("message") or str(result)[:200]
    print(f"── {description}   ({time.time() - start:.1f}s)")
    for zeile in str(news).splitlines():
        print("     " + zeile[:120])
    return str(news)


def button(data: str, description: str) -> str:
    start = time.time()
    result = bot({"callback_query": {
        "id": "1", "from": {"id": int(CHAT), "first_name": "Test"}, "data": data,
        "message": {"message_id": letzte_nachricht["id"] or 1,
                    "chat": {"id": int(CHAT), "type": "private"}}}})
    return zeige(result, description, start)


def text(message: str, description: str) -> str:
    start = time.time()
    result = bot({"message": {"message_id": 1, "chat": {"id": int(CHAT), "type": "private"},
                                "from": {"id": int(CHAT), "first_name": "Test"}, "text": message}})
    return zeige(result, description, start)


def new(type: str, title: str, inhalt: str, important: bool = False) -> str:
    _, d = service("/news/new", {"source": "suchbot-probe", "type": type, "title": title,
                                    "text": inhalt, "important": important, "from": "21-bot-news-test.py"},
                  "POST")
    return d["recorded"][0]["id"]


print("=" * 78)
print("Messages in the bot" + (" (with real announcement)" if LIVE else "") + (", waiting for the schedule" if WARTEN else ""))
print("=" * 78 + "\n")

# ------------------------------------------------------------------ 1. Buttons
print("=== 1. Offer and discard a message")
kennung_weg = new("rss", "Feedprobe", "A short test message from an RSS feed to be discarded.")
answer = button(f"x{kennung_weg}", "Button: Discard")
check("Verworfen" in answer or "discarded" in answer, "The bot reports the discard")

_, stand = service("/news/status")
check(stand["discarded"] >= 1, f"Message is recorded in the service as discarded (discarded: {stand['discarded']})")

if LIVE:
    print("\n=== 2. Have a message read out (transmission operation is briefly interrupted)")
    kennung_live = new("weather", "Wetterprobe",
                       "In Berlin today 19 degrees and occasionally sunshine. It remains dry.",
                       important=True)
    answer = button(f"m{kennung_live}", "Button: Read out")
    check("Gesagt" in answer or "said" in answer, "The bot reports the announcement",
           f"Reply: {answer[:160]}")
    _, d = service(f"/news/text/{kennung_live}")
    check(d.get("status") == "said", f"Message is marked as said (status: {d.get('status')})")
else:
    print("\n=== 2. Reading out skipped (without --live)")
    kennung_live = None

# ------------------------------------------------------------------ 3. Tool
print("\n=== 3. The agent queries the mailbox (via the tool)")
kennung_frage = new("news", "Nachrichtenprobe",
                    "The municipal council has adopted the budget. More on this later.")
answer = text("what messages are there", "Question: what messages are there")
check("Nachrichtenprobe" in answer or "news" in answer.lower() or "1." in answer,
       "The response lists the open message", f"Reply: {answer[:200]}")

# ------------------------------------------------------------------ 4. Schedule
print("\n=== 4. Schedule places new messages")
kennung_karte = new("traffic", "Verkehrsprobe",
                    "On the A100 traffic is congested after an accident on the right lane.",
                    important=True)
_, d = service(f"/news/text/{kennung_karte}")
if not WARTEN:
    print(" (without --wait, it does not wait for the schedule)")
    print(f" open message: {kennung_karte}")
else:
    print(f" waiting for the schedule (every 5 minutes), message {kennung_karte} ...")
    offered = False
    for _ in range(40):
        time, list = service("/news/all?count=50")
        entry = [m for m in list["news"] if m["id"] == kennung_karte]
        if entry and entry[0].get("angeboten_am"):
            offered = True
            break
        time.sleep(20)
    check(offered, "The schedule has remembered the message as offered")
    if offered:
        print(" -> the card is in Telegram (two buttons: Read Aloud / Discard)")

# ------------------------------------------------------------------ 5. Cleanup
print("\n=== 5. Cleanup")
ids = [k for k in (kennung_weg, kennung_live, kennung_frage, kennung_karte) if k]
_, d = service("/news/done", {"ids": ids, "reason": "discarded"}, "POST")
check(set(ids) <= set(d.get("changed", [])), f"All test messages discarded: {d.get('changed')}")
_, d = service("/news/cleanup?tage=0", {}, "POST")
check(isinstance(d.get("remaining"), int), f"Cleaned up (remains: {d.get('remaining')})")
_, stand = service("/news/status")
check(stand["open"] == 0, f"Mailbox empty again (open: {stand['open']})")

print(f"\nResult: {good} ok, {bad} deviating")
sys.exit(0 if bad == 0 else 1)
