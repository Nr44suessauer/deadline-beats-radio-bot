"""Messages and announcements: the inbox for the search bot and the moderation.

Two tasks in one module:

1. **Inbox** — another bot (search bot: weather, RSS feeds, news)
   stores messages here. The radio bot fetches them, shows them in Telegram for
   approval and then has them spoken.

2. **Announcement** — a moderation text is built from a message and spoken live
   into the running broadcast via the DJ harbor (`POST /live` in
   `main.py`, Piper + lameenc + Liquidsoap harbor). Dry run (`dry: true`)
   only creates the text, without sending.

Storage: `/data/news.json` (volume `./data` of the service, next to the catalog).
Access: shared key in the header `X-News-key`. The value is in
`/data/news-key.txt` (created on first start, permissions 600) or
in the environment variable `NEWS_KEY`. Only `/news/status` and
`/announce/status` are readable without a key (for monitoring).

The addresses are deliberately simple and stable — a foreign bot only needs:

    POST /news/new        submit a message (single or as a list)
    GET  /news/pending      fetch open messages (radio bot)
    POST /news/done   said or discarded
    GET  /news/text/<id>  preview of the moderation text
    POST /announce/item       speak a message (live into the station)
    POST /announce/text          speak free text
"""
from __future__ import annotations

import io
import json
import os
import re
import secrets
import threading
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

DATA = Path(os.environ.get("KATALOG_DIR", "/data"))
FILE = DATA / "news.json"
SCHLUESSEL_DATEI = DATA / "news-key.txt"

# Maximum length of an announcement. Originally: about 45 seconds. Since the roundup
# (2026-09-20) longer pieces are wanted too — measured, Piper speaks
# about 1050 characters per minute, so 9000 characters are about 8.5 minutes.
# Liquidsoap handles that (sent in broadcast timing); the limit only protects
# against accidentally huge texts.
MAX_CHARACTERS = int(os.environ.get("ANSAGE_MAX_ZEICHEN", "9000"))
# How many messages and announcements are kept.
MAX_NEWS = int(os.environ.get("MELDUNGEN_MAX", "500"))
MAX_ANNOUNCEMENTS = int(os.environ.get("ANSAGEN_MAX", "100"))
# The same free text will not be spoken twice within these seconds.
# Protection against tool loops of the model (introduced after an incident on
# the same evening: a command
# first spoke the messages and then still a 1.4-minute overview).
ANSAGE_SPERRE_SEK = int(os.environ.get("ANSAGE_SPERRE_SEK", "90"))

SPERRE = threading.Lock()

ARTEN = ("weather", "news", "rss", "traffic", "hint", "music", "overview",
         "misc")

# Preface per type - YOUR-VOICE's voice: short, personal, with a wink.
# The character of the figure (charakter.md) colors in the bot the freely formulated
# announcements; these fixed lines belong as the voice of the house.
VORSPANN: dict[str, str] = {
    "weather": "And now the look to the sky - I have looked out for you.",
    "news": "Briefly the news - I have listened carefully.",
    "rss": "Fresh from the net - searched for you.",
    "traffic": "Pay a moment’s attention - a traffic report.",
    "hint": "An announcement in one’s own matter.",
    "music": "",
    # For the roundup the title carries the lead-in, otherwise it would come twice.
    "overview": "",
    "misc": "I have a message for you.",
}
NACHSPANN: dict[str, str] = {
    "weather": "That was the weather - and now music for you again.",
    "news": "",
    "rss": "",
    "traffic": "And we continue with music.",
    "hint": "",
    "music": "",
    "overview": "That was the overview - and now some music for you.",
    "misc": "",
}


# --------------------------------------------------------------- Key

def key() -> str:
    """The shared key. Created on first call."""
    aus_umgebung = os.environ.get("NEWS_KEY", "").strip()
    if aus_umgebung:
        return aus_umgebung
    if SCHLUESSEL_DATEI.exists():
        wert = SCHLUESSEL_DATEI.read_text(encoding="utf-8").strip()
        if wert:
            return wert
    wert = secrets.token_urlsafe(24)
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        SCHLUESSEL_DATEI.write_text(wert + "\n", encoding="utf-8")
        SCHLUESSEL_DATEI.chmod(0o600)
    except OSError as error:  # noqa: BLE001
        print("Message key could not be saved:", error, flush=True)
    return wert


def _pruefen(gegeben: str | None) -> None:
    if not gegeben or not secrets.compare_digest(gegeben, key()):
        raise HTTPException(status_code=403, detail="X-News-key is missing or does not match.")


def _jetzt() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ------------------------------------------------------------------ Storage

def _leer() -> dict[str, Any]:
    return {"news": [], "announce": [], "counter": 0}


def _laden() -> dict[str, Any]:
    if not FILE.exists():
        return _leer()
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:  # noqa: BLE001
        print("news.json not readable:", error, flush=True)
        return _leer()
    if not isinstance(data, dict):
        return _leer()
    data.setdefault("news", [])
    data.setdefault("announce", [])
    data.setdefault("counter", 0)
    return data


def _save(data: dict[str, Any]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    data["news"] = data["news"][-MAX_NEWS:]
    data["announce"] = data["announce"][-MAX_ANNOUNCEMENTS:]
    temporary = FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(FILE)


def _news(data: dict[str, Any], identifier: str) -> dict[str, Any] | None:
    for m in data["news"]:
        if str(m.get("id")) == str(identifier):
            return m
    return None


def _order(m: dict[str, Any]) -> tuple[int, str]:
    """Important ones first, then the newest."""
    return (0 if m.get("important") else 1, str(m.get("input") or ""))


# ------------------------------------------------- Building the moderation text

# Prepare for speech: URLs, markup and abbreviations disturb Piper or
# sound wrong when read aloud ("z.B." becomes "zet-be").
#
# Attention: the abbreviation patterns must NOT end with \b. After a period
# before a space there is no word boundary — "\bz\.B\.\b" never matches
# (bug on 2026-09-20: "z.B." stayed and was spelled out).
NO_LETTER = r"(?![A-Za-z\u00c4\u00d6\u00dc\u00e4\u00f6\u00fc\u00df])"

REPLACEMENTS: list[tuple[str, str]] = [
    (r"https?://\S+", ""),
    (r"\bwww\.\S+", ""),
    (r"\b[\w.-]+\.(?:de|com|org|net|at|ch|io)\b", ""),
    (r"[*_`#>|]+", ""),
    # Do not read out the ticker characters of the news feeds ("+++ News +++").
    (r"\s*\+{2,}\s*", " "),
    # Do not read out source references from Wikipedia ("[1]", "[ 1.1 ]").
    (r"\[\s*\d+(?:[.,]\d+)*\s*\]", " "),
    (r"\[([^\]]*)\]", r"\1"),
    # Agency brackets are labels, not text ("(dpa)", "(dpa/afp)").
    (r"\(\s*(?:dpa|afp|rtr|reuters|epd|kna|sid|ots|apa|ap)(?:[\s/,-]*[a-z]+)*\s*\)", " "),
    (r"\(([^)]*)\)", r"\1"),
    (r"\s*[\u2013\u2014]\s*", ", "),
    (r"\u00b0\s*C\b", " Grad"),
    (r"\u00b0", " Grad"),
    (r"\bkm/h\b", "Kilometers per hour"),
    (r"\bm/s\b", "metres per second"),
    (r"\bmm\b", "Millimeter"),
    (r"\bl/m\u00b2\b", "litres per square metre"),
    (r"\bhPa\b", "Hektopascal"),
    (r"%", " Prozent"),
    # Abbreviations (see note above)
    (r"\bz\.\s?B\." + NO_LETTER, "for example"),
    (r"\bu\.\s?a\." + NO_LETTER, "among other things"),
    (r"\bbzw\." + NO_LETTER, "respectively"),
    (r"\bca\." + NO_LETTER, "approx"),
    (r"\bevtl\." + NO_LETTER, "possibly"),
    (r"\binkl\." + NO_LETTER, "inclusive"),
    (r"\bggf\." + NO_LETTER, "ifneeded"),
    (r"\bd\.\s?h\." + NO_LETTER, "that means"),
    (r"\bmax\." + NO_LETTER, "maximum"),
    (r"\bmin\." + NO_LETTER, "minimum"),
    (r"\bNr\." + NO_LETTER, "number"),
    (r"\bStr\." + NO_LETTER, "street"),
    (r"\bStd\." + NO_LETTER, "hours"),
    (r"\bMio\." + NO_LETTER, "Millionen"),
    (r"\bMrz\." + NO_LETTER, "March"),
    (r"\bOkt\." + NO_LETTER, "Oktober"),
    (r"\bDez\." + NO_LETTER, "Dezember"),
    (r"\bvs\." + NO_LETTER, "against"),
    (r"&", " and "),
    # Do not read out image credits and rights notes from feed texts.
    # Careful: "Bild" is also a newspaper name — so only remove "Bild:".
    (r"\bAlle Rechte vorbehalten\b[:\s]*", " "),
    (r"\b(?:IMAGO|Getty Images|picture alliance|Symbolbild|Archivbild)\b", " "),
    (r"\b(?:Foto|Bild)\s*:\s*", " "),
    # Otherwise "Details on." remains after removing a source.
    # Two subtleties (measured on 2026-09-21):
    #  * the word boundary at the end is mandatory — without it "Infos?" eats the "Info"
    #    from "Informatik" ("Anwendungsgebiet the rmatik").
    #  * the pattern only applies at the END of the text — otherwise every
    #    "Informationen" in the middle of a sentence disappears.
    (r"\s*\b(?:Details?|More|Info|Information|Read more|Source|Link)\b\s*"
     r"(?:on|under|at|in|here|about|:)?\s*\.?\s*$", ""),
]

# Emojis and other symbol type that Piper should not speak.
UNSPEAKABLE = re.compile(
    "[" "\U0001F000-\U0001FAFF" "\U00002600-\U000027BF" "\U0001F1E6-\U0001F1FF" "\u2b00-\u2bff" "\u2190-\u21ff" "]"
)

# Author lines of news feeds are not speech text ("... By Stephan
# Ueberbach." appeared on 2026-09-25 as a sentence in the daily news announcement). Only at the
# END and with capital initial letters - "the said from_ the Leyen" remains.
AUTOR_ZEILE = re.compile(
    r"\s+Von\s+(?:(?:[A-ZÄÖÜ][\w’'\-.]*|und)\s+){1,5}[A-ZÄÖÜ][\w’'\-.]*\.?\s*$")
AUTOR_KURZ = re.compile(r"\s+Von\s+(?:dpa|afp|rtr|reuters|epd|kna|sid|ots)\b[^.]*\.?\s*$", re.I)


def speakable(text: str) -> str:
    """Turns a message text into something that can be spoken cleanly."""
    s = str(text or "")
    s = s.replace("\u00a0", " ").replace("\u201e", " ").replace("\u201c", " ")
    s = UNSPEAKABLE.sub(" ", s)
    for muster, ersatz in REPLACEMENTS:
        s = re.sub(muster, ersatz, s, flags=re.I)
    s = AUTOR_ZEILE.sub(" ", s)
    s = AUTOR_KURZ.sub(" ", s)
    # Lists and line breaks into one flowing text
    s = re.sub(r"(?m)^\s*[-•·]\s*", " ", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    s = re.sub(r"([,.;:!?])(?=[A-Za-zÄÖÜäöü])", r"\1 ", s)
    s = re.sub(r"\.{2,}", ".", s)
    s = re.sub(r"\s*,\s*", ", ", s)
    return s.strip(" ,;:-")


def shorten(text: str, grenze: int = MAX_CHARACTERS) -> str:
    """Trim at the last sentence end — unfinished sentences sound bad."""
    if len(text) <= grenze:
        return text
    teil = text[:grenze]
    schnitt = max(teil.rfind(". "), teil.rfind("! "), teil.rfind("? "))
    if schnitt < grenze * 0.5:
        schnitt = teil.rfind(" ")
    if schnitt <= 0:
        return teil.strip()
    return teil[: schnitt + 1].strip()


def moderation_text(news: dict[str, Any]) -> str:
    """Builds the text that the moderator speaks."""
    type = str(news.get("type") or "misc").lower()
    if type not in VORSPANN:
        type = "misc"
    vorspann = VORSPANN.get(type, "")
    nachspann = NACHSPANN.get(type, "")
    title = speakable(news.get("title") or "")
    inhalt = speakable(news.get("text") or "")
    stuecke = [speakable(vorspann)]
    # The title often just repeats ("weather Berlin") — only
    # read it out if it is not already at the start of the text.
    if title and title.lower()[:18] not in inhalt.lower()[:40]:
        stuecke.append(title + ".")
    stuecke.append(inhalt)
    if nachspann:
        stuecke.append(speakable(nachspann))
    text = " ".join(s for s in stuecke if s).strip()
    text = re.sub(r"\s+", " ", text)
    return shorten(text)


# ------------------------------------------------------------------ Models

class News(BaseModel):
    source: str = ""
    type: str = "misc"
    title: str = ""
    text: str = ""
    url: str = ""
    important: bool = False
    from_: str = ""
    to: str = ""


class NewsList(BaseModel):
    news: list[News] = Field(default_factory=list)


class Done(BaseModel):
    ids: list[str] = Field(default_factory=list)
    reason: Literal["said", "discarded", "expired"] = "discarded"


class Offered(BaseModel):
    ids: list[str] = Field(default_factory=list)


class AnnounceItem(BaseModel):
    id: str
    dry: bool = False
    voice: str = ""
    speed: float = Field(default=1.0, ge=0.3, le=3.0)


class AnnounceText(BaseModel):
    text: str
    dry: bool = False
    voice: str = ""
    speed: float = Field(default=1.0, ge=0.3, le=3.0)


# ------------------------------------------------------------------ Recording

def _aufnehmen(new: News, data: dict[str, Any]) -> dict[str, Any]:
    data["counter"] = int(data.get("counter", 0)) + 1
    identifier = f"m{datetime.now(timezone.utc):%y%m%d}-{data['counter']:04d}"
    type = (new.type or "misc").strip().lower()
    if type not in ARTEN:
        type = "misc"
    entry = {
        "id": identifier,
        "input": _jetzt(),
        "source": (new.source or "").strip(),
        "type": type,
        "title": (new.title or "").strip(),
        "text": (new.text or "").strip(),
        "url": (new.url or "").strip(),
        "important": bool(new.important),
        "from": (new.from_ or "").strip(),
        "to": (new.to or "").strip(),
        "status": "open",
        "gesagt_am": None,
        "angeboten_am": None,
        "duration": None,
        "voice": None,
    }
    data["news"].append(entry)
    return entry


def record(source: str = "", type: str = "misc", title: str = "", text: str = "",
              important: bool = False, from_: str = "", url: str = "", to: str = "") -> dict[str, Any]:
    """Stores a message — without key check, for other modules in the service
    (e.g. the research in search.py). The endpoint checks the key itself."""
    entry = News(source=source, type=type, title=title, text=text, important=important,
                      from_=from_, url=url, to=to)
    if not entry.text.strip():
        raise HTTPException(status_code=400, detail="Message without text.")
    with SPERRE:
        data = _laden()
        recorded = _aufnehmen(entry, data)
        _save(data)
    return recorded


def offene_zahl() -> int:
    """How many messages are open."""
    with SPERRE:
        data = _laden()
    return sum(1 for m in data["news"] if m.get("status") == "open")


@router.post("/news/new")
def meldungen_neu(body: dict[str, Any],
                  x_news_key: str | None = Header(default=None)) -> dict[str, Any]:
    """Accepts a message — single or as a list under "news"."""
    _pruefen(x_news_key)
    raw = body.get("news") if isinstance(body, dict) else None
    if raw is None:
        list = [News(**{k: v for k, v in (body or {}).items() if k in News.model_fields})]
    else:
        if not isinstance(raw, list):
            raise HTTPException(status_code=400, detail='"news" must be a list.')
        list = [News(**{k: v for k, v in (e or {}).items() if k in News.model_fields})
                 for e in raw]
    if not list:
        raise HTTPException(status_code=400, detail="No message provided.")
    ohne_text = [i for i, m in enumerate(list) if not m.text.strip()]
    if ohne_text:
        raise HTTPException(status_code=400, detail=f"Message without text: {ohne_text}")

    with SPERRE:
        data = _laden()
        recorded = [_aufnehmen(m, data) for m in list]
        _save(data)
        open = sum(1 for m in data["news"] if m.get("status") == "open")
    return {
        "ok": True,
        "recorded": [{"id": m["id"], "type": m["type"], "title": m["title"],
                         "beginning": m["text"][:80]} for m in recorded],
        "open": open,
    }


@router.get("/news/pending")
def meldungen_offen(count: int = 5, type: str = "", only_new: int = 0,
                    x_news_key: str | None = Header(default=None)) -> dict[str, Any]:
    """Open messages — important ones first, then the newest.

    `only_new=1` skips those that were already offered to the operator (the
    schedule in the bot polls with it regularly and does not repeat itself).
    """
    _pruefen(x_news_key)
    with SPERRE:
        data = _laden()
    open = [m for m in data["news"] if m.get("status") == "open"]
    if only_new:
        open = [m for m in open if not m.get("angeboten_am")]
    if type:
        open = [m for m in open if m.get("type") == type]
    open.sort(key=_order)
    return {"ok": True, "open": len(open),
            "news": [{**m, "preview": moderation_text(m)[:200]} for m in
                          open[:max(1, min(count, 50))]]}


@router.get("/news/all")
def meldungen_alle(count: int = 20, status: str = "",
                   x_news_key: str | None = Header(default=None)) -> dict[str, Any]:
    """All messages (also said and discarded ones) — for monitoring."""
    _pruefen(x_news_key)
    with SPERRE:
        data = _laden()
    all = list(data["news"])
    if status:
        all = [m for m in all if m.get("status") == status]
    all.sort(key=lambda m: str(m.get("input") or ""), reverse=True)
    return {"total": len(data["news"]), "news": all[:max(1, min(count, 200))]}


@router.get("/news/text/{identifier}")
def meldungen_text(identifier: str,
                   x_news_key: str | None = Header(default=None)) -> dict[str, Any]:
    """Shows what the moderator would say — without sending."""
    _pruefen(x_news_key)
    with SPERRE:
        data = _laden()
        news = _news(data, identifier)
    if news is None:
        raise HTTPException(status_code=404, detail=f"Message {identifier} does not exist.")
    text = moderation_text(news)
    return {"id": news["id"], "type": news["type"], "title": news["title"],
            "status": news["status"], "spoken_text": text,
            "characters": len(text), "words": len(text.split())}


@router.post("/news/offered")
def meldungen_angeboten(body: Offered,
                        x_news_key: str | None = Header(default=None)) -> dict[str, Any]:
    """Notes that these messages were already shown to the operator."""
    _pruefen(x_news_key)
    gemerkt: list[str] = []
    with SPERRE:
        data = _laden()
        for identifier in body.ids:
            news = _news(data, identifier)
            if news is None or news.get("angeboten_am"):
                continue
            news["angeboten_am"] = _jetzt()
            gemerkt.append(str(news["id"]))
        _save(data)
    return {"ok": True, "offered": gemerkt}


@router.post("/news/done")
def meldungen_erledigt(body: Done,
                       x_news_key: str | None = Header(default=None)) -> dict[str, Any]:
    """Marks messages as said, discarded or expired."""
    _pruefen(x_news_key)
    changed: list[str] = []
    title: list[str] = []
    with SPERRE:
        data = _laden()
        for identifier in body.ids:
            news = _news(data, identifier)
            if news is None:
                continue
            news["status"] = body.reason
            if body.reason == "said" and not news.get("gesagt_am"):
                news["gesagt_am"] = _jetzt()
            changed.append(str(news["id"]))
            title.append(str(news.get("title") or news["id"]))
        _save(data)
        open = sum(1 for m in data["news"] if m.get("status") == "open")
    if not changed:
        return {"ok": False, "changed": [], "open": open,
                "answer": "I don’t know this message anymore.",
                "edit": True, "keyboard": {"inline_keyboard": []}}
    bild = {"said": "As said, noted", "discarded": "Verworfen",
            "expired": "Abgelaufen"}[body.reason]
    return {"ok": True, "changed": changed, "open": open,
            "answer": f"{bild}: {', '.join(title)}"[:300],
            "edit": True, "keyboard": {"inline_keyboard": []}}


@router.post("/news/cleanup")
def meldungen_aufraeumen(tage: int = 7,
                         x_news_key: str | None = Header(default=None)) -> dict[str, Any]:
    """Removes done messages older than <tage>."""
    _pruefen(x_news_key)
    grenze = time.time() - max(0, tage) * 86400
    with SPERRE:
        data = _laden()
        before = len(data["news"])
        behalten = []
        for m in data["news"]:
            if m.get("status") == "open":
                behalten.append(m)
                continue
            try:
                time = datetime.fromisoformat(str(m.get("input"))).timestamp()
            except ValueError:
                time = time.time()
            if time >= grenze:
                behalten.append(m)
        data["news"] = behalten
        _save(data)
    return {"ok": True, "removed": before - len(behalten), "remaining": len(behalten)}


# ------------------------------------------------------------------- Announcements

def _live_funktion():
    """The live function from main.py — imported late, otherwise there is a cycle."""
    try:
        from main import live as live_funktion  # type: ignore  # noqa: PLC0415

        return live_funktion
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"Live path not available (main.live): {error}",
        ) from error


def _ansage_bauen(text: str, voice: str, speed: float) -> dict[str, Any]:
    """Calls /live — without sending if dry. Returns the result."""
    live_funktion = _live_funktion()
    from main import LiveAnfrage  # type: ignore  # noqa: PLC0415

    host = os.environ.get("LIVE_HOST", "")
    if not host or not os.environ.get("LIVE_USER") or not os.environ.get("LIVE_PASSWORD"):
        raise HTTPException(
            status_code=503,
            detail="The DJ access is missing: set LIVE_HOST, LIVE_USER and LIVE_PASSWORD "
                   "(geheim.env of the service).",
        )
    request = LiveAnfrage(text=text, voice=voice, speed=speed, host=host)
    if os.environ.get("LIVE_TROCKEN", "0") == "1":
        request = LiveAnfrage(text=text, voice=voice, speed=speed, host="", user="", password="")
    return live_funktion(request)


def _trocken_text(text: str, voice: str, speed: float) -> dict[str, Any]:
    """Only creates the audio and reports length and size."""
    from main import erzeuge_audio_gewaehlt  # type: ignore  # noqa: PLC0415

    with SPERRE:
        wav, _, chosen = erzeuge_audio_gewaehlt(text, voice, speed, "wav")
    try:
        with wave.open(io.BytesIO(wav), "rb") as w:
            duration = round(w.getnframes() / float(w.getframerate() or 1), 1)
    except Exception:  # noqa: BLE001 - an estimate rather than an error
        duration = round(len(wav) / 44100.0, 1)
    return {"ok": True, "dry": True, "spoken": text, "voice": chosen,
            "duration_seconds": duration, "wav_bytes": len(wav)}


def _ansage_merken(data: dict[str, Any], entry: dict[str, Any]) -> None:
    data["announce"].append(entry)


def ansage_machen(identifier: str, dry: bool = False, voice: str = "",
                 speed: float = 1.0) -> dict[str, Any]:
    """Speaks a stored message (or creates it dry).

    Without key check — for other modules in the service (search.py). The
    endpoint /announce/item checks the key beforehand.
    """
    return _ansage_meldung_arbeit(AnnounceItem(id=identifier, dry=dry, voice=voice,
                                               speed=speed))


@router.post("/announce/item")
def ansage_meldung(request: AnnounceItem,
                   x_news_key: str | None = Header(default=None)) -> dict[str, Any]:
    """Speaks a stored message live into the station (or dry)."""
    _pruefen(x_news_key)
    return _ansage_meldung_arbeit(request)


def _ansage_meldung_arbeit(request: AnnounceItem) -> dict[str, Any]:
    with SPERRE:
        data = _laden()
        news = _news(data, request.id)
    if news is None:
        raise HTTPException(status_code=404, detail=f"Message {request.id} does not exist.")
    text = moderation_text(news)
    if not text:
        raise HTTPException(status_code=400, detail="The message has no text.")
    if news.get("status") == "said" and not request.dry:
        return {"ok": False, "reason": "already_said", "id": news["id"],
                "gesagt_am": news.get("gesagt_am"),
                "answer": f"\u201c{news['title'] or news['id']}\u201d was already said."}

    if request.dry:
        result = _trocken_text(text, request.voice, request.speed)
    else:
        result = _ansage_bauen(text, request.voice, request.speed)

    if not request.dry:
        with SPERRE:
            data = _laden()
            entry = _news(data, request.id)
            if entry is not None:
                entry["status"] = "said"
                entry["gesagt_am"] = _jetzt()
                entry["duration"] = result.get("duration_seconds")
                entry["voice"] = result.get("voice")
            _ansage_merken(data, {
                "time": _jetzt(), "away": "news", "id": request.id,
                "type": entry.get("type") if entry else "",
                "title": entry.get("title") if entry else "",
                "duration_seconds": result.get("duration_seconds"),
            })
            _save(data)
    duration = result.get("duration_seconds")
    title = news.get("title") or news["id"]
    if request.dry:
        answer = f"Dry run: {duration} s - spoken would be: {text[:200]}"
    else:
        answer = f"Said ({duration} s): {title}"
    return {"ok": True, "id": news["id"], "type": news.get("type"),
            "title": title, "spoken": text, "duration_seconds": duration,
            "dry": bool(request.dry), "answer": answer,
            "edit": True, "keyboard": {"inline_keyboard": []}}


def _vor_kurzem_gesprochen(text: str) -> bool:
    """Was exactly this text (beginning) just spoken?"""
    grenze = text[:60]
    with SPERRE:
        data = _laden()
    now = datetime.now(timezone.utc)
    for a in reversed(data.get("announce", [])):
        if a.get("away") != "text" or a.get("title") != grenze:
            continue
        try:
            then = datetime.fromisoformat(str(a.get("time")))
        except ValueError:
            continue
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        return (now - then).total_seconds() < ANSAGE_SPERRE_SEK
    return False


@router.post("/announce/text")
def ansage_text(request: AnnounceText,
                x_news_key: str | None = Header(default=None)) -> dict[str, Any]:
    """Speaks free text live into the station (or dry)."""
    _pruefen(x_news_key)
    text = speakable(request.text)
    if not text:
        raise HTTPException(status_code=400, detail="No text provided.")
    text = shorten(text)
    # Loop protection: do not speak the same text shortly one after another.
    if not request.dry and _vor_kurzem_gesprochen(text):
        return {"ok": True, "spoken": text, "wiederholt": False,
                "duration_seconds": 0,
                "answer": "This announcement was just played -"
                           "I did not repeat them."}
    if request.dry:
        result = _trocken_text(text, request.voice, request.speed)
    else:
        result = _ansage_bauen(text, request.voice, request.speed)
        with SPERRE:
            data = _laden()
            _ansage_merken(data, {"time": _jetzt(), "away": "text", "id": "",
                                   "type": "", "title": text[:60],
                                   "duration_seconds": result.get("duration_seconds")})
            _save(data)
    duration = result.get("duration_seconds")
    return {"ok": True, "spoken": text, "duration_seconds": duration,
            "dry": bool(request.dry),
            "answer": (f"Dry run: {duration} s" if request.dry
                        else f"Announcement spoken ({duration} s): {text[:120]}")}


# ------------------------------------------------------------------- Status

@router.get("/news/status")
def meldungen_status() -> dict[str, Any]:
    """Monitoring without key: counters and whether the live path is set up."""
    with SPERRE:
        data = _laden()
    open = [m for m in data["news"] if m.get("status") == "open"]
    return {
        "app": "news",
        "total": len(data["news"]),
        "open": len(open),
        "davon_wichtig": sum(1 for m in open if m.get("important")),
        "said": sum(1 for m in data["news"] if m.get("status") == "said"),
        "discarded": sum(1 for m in data["news"] if m.get("status") == "discarded"),
        "offene_liste": [{"id": m["id"], "type": m["type"], "title": m["title"],
                          "important": m["important"], "beginning": m["text"][:60]} for m in
                         sorted(open, key=_order)[:10]],
        "schluessel_gesetzt": bool(key()),
        "schluessel_datei": str(SCHLUESSEL_DATEI),
        "live": {
            "host": os.environ.get("LIVE_HOST", ""),
            "port": os.environ.get("LIVE_PORT", "8005"),
            "mount": os.environ.get("LIVE_MOUNT", "/"),
            "user": os.environ.get("LIVE_USER", ""),
            "password_set": bool(os.environ.get("LIVE_PASSWORD")),
        },
        "max_zeichen": MAX_CHARACTERS,
    }


@router.get("/announce/status")
def ansage_status(count: int = 10) -> dict[str, Any]:
    """The latest announcements and the settings of the live path."""
    with SPERRE:
        data = _laden()
    return {
        "app": "announce",
        "count": len(data["announce"]),
        "last": data["announce"][-max(1, min(count, 50)):][::-1],
        "voice": os.environ.get("TTS_DEFAULT_VOICE", ""),
        "live": {
            "host": os.environ.get("LIVE_HOST", ""),
            "port": os.environ.get("LIVE_PORT", "8005"),
            "mount": os.environ.get("LIVE_MOUNT", "/"),
            "user": os.environ.get("LIVE_USER", ""),
            "password_set": bool(os.environ.get("LIVE_PASSWORD")),
            "silence": os.environ.get("LIVE_SCHWEIGEN", "5.5"),
        },
    }
