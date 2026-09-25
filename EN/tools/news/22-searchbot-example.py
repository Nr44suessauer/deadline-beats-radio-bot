#!/usr/bin/env python3
"""Example for a search bot: Provide weather and feed messages.

Shows exactly what a foreign bot must do: send a message to
POST /messages/new (header X-Message-Key) and read the preview
of the speech text. The radio bot then retrieves them itself and presents them to
the operator in Telegram.

Two ways are possible:
 * retrieve and submit the completed message (this example), or
 * request the service: POST /research {"type": "weather", "word": "Marbach am Neckar"}
 (Weather, news, RSS, Wikipedia - without own retrieval).

Call:
    python3 22-searchbot-example.py                 # file a weather and feed message
    python3 22-searchbot-example.py --weather        # weather only
    python3 22-searchbot-example.py --important       # as an important message
    python3 22-searchbot-example.py --cleanup    # eigene Proben again remove

The key is located in <dokuordner>/news-key.txt
(on the server: /data/news-key.txt in the service container).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

SERVICE = os.environ.get("MELDUNG_DIENST", "http://192.168.178.53:8881")
SCHLUESSEL_DATEI = Path(os.environ.get(
    "MELDUNG_SCHLUESSEL_DATEI", "<dokuordner>/news-key.txt"))


def key() -> str:
    aus_umgebung = os.environ.get("NEWS_KEY", "").strip()
    if aus_umgebung:
        return aus_umgebung
    if SCHLUESSEL_DATEI.exists():
        return SCHLUESSEL_DATEI.read_text(encoding="utf-8").strip()
    raise SystemExit(f"No key: {SCHLUESSEL_DATEI} missing"
                     "(or set NEWS_KEY)")


def news(type: str, title: str, text: str, important: bool = False,
            source: str = "", url: str = "") -> str:
    """Places a message and returns its identifier."""
    body = json.dumps({"type": type, "title": title, "text": text, "important": important,
                          "source": source, "url": url, "from": "22-searchbot-example.py"})
    request = urllib.request.Request(
        SERVICE + "/news/new", data=body.encode(),
        headers={"Content-Type": "application/json", "X-News-key": key()},
        method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as answer:
            data = json.loads(answer.read().decode())
    except urllib.error.HTTPError as error:
        raise SystemExit(f"Rejected (HTTP {error.code}): {error.read().decode()[:200]}") from error
    entry = data["recorded"][0]
    print(f" placed: {entry['id']}  ({type}: {title})")
    return entry["id"]


def preview(identifier: str) -> None:
    """Shows what the moderator would say."""
    request = urllib.request.Request(
        SERVICE + f"/news/text/{identifier}",
        headers={"X-News-key": key()})
    with urllib.request.urlopen(request, timeout=30) as answer:
        data = json.loads(answer.read().decode())
    print(f" would say ({data['characters']} characters):\n    {data['spoken_text']}")


def cleanup() -> None:
    """Removes own test messages again."""
    request = urllib.request.Request(
        SERVICE + "/news/all?count=100",
        headers={"X-News-key": key()})
    with urllib.request.urlopen(request, timeout=30) as answer:
        all = json.loads(answer.read().decode())["news"]
    meine = [m["id"] for m in all if m.get("from") == "22-searchbot-example.py"]
    if not meine:
        print(" nothing to remove")
        return
    body = json.dumps({"ids": meine, "reason": "discarded"}).encode()
    request = urllib.request.Request(
        SERVICE + "/news/done", data=body,
        headers={"Content-Type": "application/json", "X-News-key": key()},
        method="POST")
    with urllib.request.urlopen(request, timeout=30) as answer:
        print(f" removed: {json.loads(answer.read().decode())['changed']}")


def main() -> int:
    wichtige = "--important" in sys.argv
    nur_wetter = "--weather" in sys.argv and "--feed" not in sys.argv

    if "--cleanup" in sys.argv:
        print("Remove tests")
        cleanup()
        return 0

    now = datetime.now().strftime("%H:%M")
    print("Search bot example: Messages to the radio mailbox\n")

    # --- Weather (here fixed; in real bot from a weather query)
    identifier = news(
        type="weather", title="Weather Berlin",
        text="Um " + now + " it is 18 degrees in Berlin. In the afternoon clouds gather,"
             "later there is a 70 % chance of rain."
             "The wind blows weakly from southwest.",
        important=wichtige, source="beispiel")
    preview(identifier)

    if not nur_wetter:
        # --- Feed (here fixed; in real bot from an RSS feed)
        identifier = news(
            type="rss", title="From the web",
            text="**New version released**: The project has today released version 4"
                 "for more details see example.org/details.",
            important=wichtige, source="beispiel-feed", url="https://example.org/details")
        preview(identifier)

    stand = json.loads(urllib.request.urlopen(SERVICE + "/news/status", timeout=30).read())
    print(f"\nMailbox open: {stand['open']} (of which important: {stand['davon_wichtig']})")
    print("The radio bot retrieves them at the next scheduled run (every 5 minutes) and\n"
          "presents them to the operator in Telegram with the buttons Read/Dismiss.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
