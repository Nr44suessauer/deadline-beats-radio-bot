#!/usr/bin/env python3
"""Checks the list tasks from end to end via the bot's test input.

The test goes through the real workflow (n8n) and sends real messages
to the operator chat. The response of the last node is the response from
Telegram - from this it is checked what the bot responded.

Process: Show lists, build playlist (Menu, tap title, Done),
Cancel, view, delete. At the end only "List A" remains.

Call:  python3 15-bot-playlists-test.py [--play]
 --play  additionally performs "build and play immediately"
 (interrupts the broadcast operation briefly!)
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# The test input is reachable from the workstation; in LXC 103 it is
# 127.0.0.1:5678 - therefore configurable via environment.
WEBHOOK = os.environ.get("BOT_WEBHOOK", "http://192.168.178.53:5678/webhook/YOUR-WEBHOOK-PATH")
KEY = Path("<dokuordner>/bot-test-key.txt").read_text().strip()
CHAT = "YOUR-CHAT-ID"
PROBE = "test Copilot"
SPIELEN = "--play" in sys.argv

if not KEY:
    raise SystemExit("Test key missing (bot-test-key.txt)")

letzte_nachricht = {"id": None}


def rufen(body: dict, duration: int = 120) -> dict:
    target = f"{WEBHOOK}?key={KEY}"
    data = json.dumps(body).encode()
    request = urllib.request.Request(target, data=data, headers={"Content-Type": "application/json"},
                                     method="POST")
    with urllib.request.urlopen(request, timeout=duration) as answer:
        raw = answer.read().decode()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def text(body: dict, description: str) -> str:
    """Send message and show the bot's response."""
    start = time.time()
    result = rufen({"message": {"message_id": 1, "chat": {"id": int(CHAT), "type": "private"},
                                  "from": {"id": int(CHAT), "first_name": "Test"}, "text": body}})
    return show(result, description, start)


def button(data: str, description: str) -> str:
    """Simulate button press - with the real message identifier, so that the
 menu is edited instead of resent."""
    if not letzte_nachricht["id"]:
        raise SystemExit("No message identifier - first send a text message")
    start = time.time()
    result = rufen({"callback_query": {
        "id": "1", "from": {"id": int(CHAT), "first_name": "Test"},
        "data": data,
        "message": {"message_id": letzte_nachricht["id"],
                    "chat": {"id": int(CHAT), "type": "private"}}}})
    return show(result, description, start)


def show(result: dict, description: str, start: float) -> str:
    seconds = time.time() - start
    inhalt = result.get("result") if isinstance(result.get("result"), dict) else None
    if inhalt and inhalt.get("message_id"):
        letzte_nachricht["id"] = inhalt["message_id"]
    news = ""
    if inhalt:
        news = inhalt.get("text") or inhalt.get("caption") or ""
    elif result.get("message"):
        news = f"ERROR: {result.get('message')}"
    elif result.get("raw"):
        news = result["raw"][:400]
    print(f"── {description}   ({seconds:.1f}s)")
    for zeile in str(news).splitlines():
        print("     " + zeile[:120])
    knoepfe = ((inhalt or {}).get("reply_markup") or {}).get("inline_keyboard") or []
    if knoepfe:
        print(" Buttons:" + " | ".join(k["text"][:34] for zeile in knoepfe for k in zeile)[:300])
    print()
    return str(news)


print("=" * 78)
print("List tasks in bot (test input, real operator chat)")
print("=" * 78 + "\n")

text("which playlists exist", "1) Show lists")
text(f"build a playlist {PROBE} from Scooter", "2) Build playlist -> selection menu")
button("p1", "3) Tap title 1")
button("p2", "4) Tap title 2")
button("pf", "5) Done -> create list")
button("px", "6) Enough (do not play)")
text(f"what is in the playlist {PROBE}", "7) View content")
text(f"delete the playlist {PROBE}", "8) Delete lists (confirmation)")
button("j", "9) Yes, delete")
text("remove Hyper Hyper from the playlist List A", "10) single title (not yet possible)")
text("do something with the station", "11) unknown task (runs as before)")

if SPIELEN:
    text(f"build a playlist {PROBE} immediately from Scooter and play it",
         "12) build and play immediately -> selection menu")
    button("p1", "13) Tap title 1")
    button("pf", "14) Done -> create AND play (broadcast operation is interrupted briefly)")
    text(f"Delete the playlist {PROBE} immediately", "15) Delete probe again")
    button("j", "16) Yes, delete")

print("Fertig.")
