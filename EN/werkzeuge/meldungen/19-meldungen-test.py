#!/usr/bin/env python3
"""Checks the message and announcement module.

Two parts:
 1. Text preparation (without network): what the moderator would say - URLs,
 Emojis, abbreviations, truncation.
 2. Ways via the service: submit a message, retrieve, preview, dry announcement,
 complete. With --live an additional real announcement is spoken into the
 broadcaster (short, interrupts the current title).

Call:
    python3 19-news-test.py            # without broadcast
    python3 19-news-test.py --live     # with a real announcement
"""
from __future__ import annotations

import json
import os
import sys
import types
import urllib.error
import urllib.request
from pathlib import Path

SERVICE = os.environ.get("MELDUNG_DIENST", "http://192.168.178.53:8881")
SCHLUESSEL_DATEI = Path("<dokuordner>/news-key.txt")
LIVE = "--live" in sys.argv
QUELLE = Path("<dokuordner>/service/news.py")

good = 0
bad = 0


def check(condition: bool, description: str, extra: str = "") -> None:
    global good, bad
    if condition:
        good += 1
        print(f"ok   {description}")
    else:
        bad += 1
        print(f"ABW. {description}" + (f"\n       {extra}" if extra else ""))


# ------------------------------------------------- Part 1: Text preparation

def lokaler_test() -> None:
    """Imports the module with fixtures for FastAPI/Pydantic."""
    fastapi = types.ModuleType("fastapi")

    class _Router:
        def post(self, *_a, **_k):
            return lambda f: f

        def get(self, *_a, **_k):
            return lambda f: f

    class HTTPException(Exception):
        def __init__(self, status_code=500, detail=""):
            self.status_code, self.detail = status_code, detail

    fastapi.APIRouter = _Router
    fastapi.HTTPException = HTTPException
    fastapi.Header = lambda default=None, **_k: default
    sys.modules["fastapi"] = fastapi

    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        model_fields: dict = {}

        def __init__(self, **felder):
            for k, v in felder.items():
                setattr(self, k, v)

    pydantic.BaseModel = BaseModel
    pydantic.Field = lambda default="", **_k: default
    sys.modules["pydantic"] = pydantic

    sys.path.insert(0, str(QUELLE.parent))
    import importlib

    modul = importlib.import_module("news")

    print("=== 1. Text preparation for speaking")
    cases = [
        ("Today 18°C, later rain at 70 % probability. More at weather.de",
         ["Grad", "Prozent"], ["°", "%", "weather.de"]),
        ("**Important**: The train is cancelled (reason: strike) — see https://bahn.de/streik",
         ["Wichtig", "Streik"], ["**", "(", ")", "https://"]),
        ("Wind up to 40 km/h, e.g. along the coast 🌧️",
         ["Kilometers per hour", "for example"], ["km/h", "z.B.", "🌧️"]),
    ]
    for text, must, darf_nicht in cases:
        result = modul.speakable(text)
        missing = [m for m in must if m not in result]
        forbidden = [d for d in darf_nicht if d in result]
        check(not missing and not forbidden, f'speakable: "{text[:48]}..."',
               f"missing: {missing} | must not be: {forbidden} | is: {result}")

    # Abbreviations: the pattern must not end with \b - after a period before
    # a space there is no word boundary (error on 2026-09-20).
    print("\n=== 1b. Abbreviations")
    for abk, expected in [("e.g. it’s raining", "for example"), ("e.g. it’s raining", "for example"),
                      ("or tomorrow", "respectively"), ("about 20 degrees", "approx"),
                      ("etc. music", "among other things"), ("that is, later", "that means"),
                      ("No. 5 is running", "number"), ("possibly later", "ifneeded"),
                      ("perhaps thunderstorms", "possibly")]:
        result = modul.speakable(abk)
        check(expected in result and abk.split()[0] not in result,
               f'"{abk}" -> "{result}"')

    print("\n=== 2. Moderation text")
    weather = {"type": "weather", "title": "Weather Berlin", "text": "In the afternoon sunny, 21 degrees."}
    t = modul.moderation_text(weather)
    check(t.startswith("And now a look at the weather"), f"Weather gets prefix: {t}")
    check("sunnig" not in t and "sonnig" in t, "Content remains intact")

    message = {"type": "news", "title": "", "text": "The Bundestag has decided."}
    check(modul.moderation_text(message).startswith("Briefly from the news"),
           "News get their own prefix")

    rss = {"type": "rss", "source": "heise", "title": "New version", "text": "Today’s release."}
    txt = modul.moderation_text(rss)
    check("New version" in txt and txt.startswith("News from the web"),
           f"RSS names the title: {txt}")

    without_title = {"type": "weather", "title": "Weather Berlin", "text": "Weather Berlin: sunny."}
    check(modul.moderation_text(without_title).count("Weather Berlin") == 1,
           "Title is not read twice")

    lang = {"type": "news", "text": "First sentence is here." * 80}
    shortened = modul.moderation_text(lang)
    check(len(shortened) <= modul.MAX_CHARACTERS + 40 and shortened.endswith("."),
           f"Too long text gets truncated at sentence boundary ({len(shortened)} characters)")

    empty = modul.moderation_text({"type": "misc", "text": ""})
    check(empty != "", f"Empty message still results in a sentence: {empty!r}")


# ------------------------------------------------------ Part 2: about the service

def rufen(path: str, body: dict | None = None, method: str = "GET",
          key: str | None = None) -> tuple[int, dict]:
    kopf = {"Content-Type": "application/json"}
    if key:
        kopf["X-News-key"] = key
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(SERVICE + path, data=data, headers=kopf, method=method)
    try:
        with urllib.request.urlopen(request, timeout=300) as answer:
            return answer.status, json.loads(answer.read().decode() or "{}")
    except urllib.error.HTTPError as error:
        raw = error.read().decode()
        try:
            return error.code, json.loads(raw)
        except json.JSONDecodeError:
            return error.code, {"raw": raw[:200]}


def dienst_test() -> None:
    if not SCHLUESSEL_DATEI.exists():
        print(f"\nNo key ({SCHLUESSEL_DATEI}) - service part skipped.")
        return
    key = SCHLUESSEL_DATEI.read_text(encoding="utf-8").strip()

    print("\n=== 3. Mailbox (Searchbot -> Service)")
    code, _ = rufen("/news/status")
    check(code == 200, f"/news/status readable without key (HTTP {code})")

    code, _ = rufen("/news/new", {"text": "Test without key"}, "POST")
    check(code == 403, f"Submitting without key is rejected (HTTP {code})")

    code, d = rufen("/news/new", {
        "source": "testskript", "type": "weather", "title": "Wetterprobe",
        "text": "In Berlin today 18°C and later rain with 70 % probability."
                "Details on weather.de", "important": False, "from": "19-news-test.py",
    }, "POST", key)
    check(code == 200 and d.get("recorded"), f"Message received (HTTP {code}): {d.get('recorded')}")
    identifier = d["recorded"][0]["id"]

    code, d = rufen("/news/pending?count=5", key=key)
    check(code == 200 and any(m["id"] == identifier for m in d.get("news", [])),
           f"Message in mailbox (open: {d.get('open')})")

    code, d = rufen("/news/offered", {"ids": [identifier]}, "POST", key)
    check(code == 200 and identifier in d.get("offered", []), f"Remembered as offered: {d.get('offered')}")
    code, d = rufen("/news/pending?only_new=1", key=key)
    check(all(m["id"] != identifier for m in d.get("news", [])),
           "only_new=1 skips offered (no second offer)")
    code, d = rufen("/news/offered", {"ids": [identifier]}, "POST", key)
    check(d.get("offered") == [], "Second remembering is ineffective")

    code, d = rufen(f"/news/text/{identifier}", key=key)
    text = d.get("spoken_text", "")
    check(code == 200 and "Grad" in text and "Prozent" in text and "weather.de" not in text,
           f"Preview of speech text: {text}")
    check(d.get("words", 0) > 5, f"Words counted: {d.get('words')}")

    print("\n=== 3b. Research (dry run)")
    code, d = rufen("/research/feeds")
    check(code == 200 and "weather" in d.get("types", []),
           f"The research names their types: {d.get('types')}")

    recherchiert: list[str] = []
    for job, must in [({"type": "weather", "word": "Marbach am Neckar"}, "Grad"),
                          ({"type": "news"}, ""),
                          ({"type": "wikipedia", "word": "Marbach am Neckar"}, "")]:
        code, d = rufen("/research", {**job, "announce": False}, "POST", key)
        ok = code == 200 and d.get("id") and len(str(d.get("text", ""))) > 40
        check(ok, f"Research {job['type']} {job.get('word', '')}:"
                   f"{str(d.get('title', ''))[:60]} ({len(str(d.get('text', '')))} characters, HTTP {code})")
        if d.get("id"):
            recherchiert.append(d["id"])
        if must:
            check(must in str(d.get("text", "")), f"Text mentions ’{must}’")

    code, d = rufen("/research", {"type": "weather", "word": "Marbach am Neckar"}, "POST", key)
    check(code == 200 and d.get("duration_seconds", 0) > 3,
           f"Weather with announcement (dry set): {d.get('duration_seconds')} s, said={d.get('said')}")
    if d.get("id"):
        recherchiert.append(d["id"])

    code, d = rufen("/research", {"type": "weather", "word": "Xyzzyxquatschort", "announce": False},
                    "POST", key)
    check(code == 404, f"Unknown location is rejected (HTTP {code})")
    code, d = rufen("/research", {"type": "quatsch", "announce": False}, "POST", key)
    check(code in (400, 422), f"Unknown type is rejected (HTTP {code})")

    if recherchiert:
        rufen("/news/done", {"ids": recherchiert, "reason": "discarded"}, "POST", key)
        print(f" (Problem messages discarded: {recherchiert})")

    print("\n=== 4. Announcement (dry run)")
    code, d = rufen("/announce/item", {"id": identifier, "dry": True}, "POST", key)
    check(code == 200 and d.get("duration_seconds", 0) > 2,
           f"Audio generated, Length {d.get('duration_seconds')} s (HTTP {code})")
    check("Grad" in d.get("spoken", ""), "Speech text is provided along with it")
    check("Dry run" in d.get("answer", ""), f"Response mentions the dry run: {d.get('answer', '')[:80]}")

    code, d = rufen("/announce/text", {"text": "Test of the free announcement.", "dry": True},
                    "POST", key)
    check(code == 200 and d.get("duration_seconds", 0) > 0,
           f"Free announcement dry run: {d.get('duration_seconds')} s")

    if LIVE:
        print("\n=== 5. Live announcement into the broadcaster (broadcasting operation is briefly interrupted)")
        short = {"type": "hint", "title": "Ansageprobe",
                "text": "This is a short test of the moderation announcement."
                        "If you hear this, the new interface is working."}
        code, d = rufen("/news/new", short, "POST", key)
        kennung_live = d["recorded"][0]["id"]
        code, d = rufen("/announce/item", {"id": kennung_live}, "POST", key)
        check(code == 200 and d.get("duration_seconds", 0) > 3,
               f"Announcement spoken: {d.get('duration_seconds')} s, Port {d.get('answer')}"
               if isinstance(d, dict) else f"Response: {d}")
        if code == 200:
            print(f" spoken: {d.get('spoken', '')[:160]}")
        code, d = rufen("/announce/item", {"id": kennung_live}, "POST", key)
        check(d.get("reason") == "already_said", "Second announcement of the same message is rejected")
        rufen("/news/done", {"ids": [kennung_live], "reason": "discarded"},
              "POST", key)
        print(" (Problem message discarded again)")
    else:
        print("\n=== 5. Real announcement skipped (without --live)")

    print("\n=== 6. Finalization")
    code, d = rufen("/news/done", {"ids": [identifier], "reason": "discarded"},
                    "POST", key)
    check(code == 200 and identifier in d.get("changed", []), f"Message discarded: {d.get('changed')}")
    check(d.get("answer") and d.get("edit") is True,
           f"Response for Telegram at that time: {d.get('answer', '')[:80]}")

    code, d = rufen("/news/cleanup?tage=0", key=key, method="POST")
    check(code == 200, f"Cleanup successful (removed: {d.get('removed')}, remains: {d.get('remaining')})")

    code, d = rufen("/news/pending", key=key)
    check(d.get("open") == 0, f"Mailbox is empty again (open: {d.get('open')})")

    code, d = rufen("/announce/status?count=3")
    check(code == 200 and d.get("live", {}).get("password_set"),
           f"Live access set up: {d.get('live')}")


if __name__ == "__main__":
    print("=" * 78)
    print("Messages and Announcements - Test run" + (" (with real announcement)" if LIVE else ""))
    print("=" * 78 + "\n")
    lokaler_test()
    dienst_test()
    print(f"\nResult: {good} ok, {bad} deviating")
    sys.exit(0 if bad == 0 else 1)
