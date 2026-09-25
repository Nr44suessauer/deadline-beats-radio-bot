"""Research: weather, news, feeds and short info on demand.

The operator says in Telegram for example "search for the weather for Marbach am
Neckar". The agent thus calls `POST /research`; this module fetches the data,
builds a moderation text from it, stores it as a message in the inbox
(`news.py`) and speaks it into the station right away on request.

Everything free of charge and without a key:

  * Weather    — Open-Meteo (place search via geocoding, forecast for today)
  * News       — the top item from a German news feed (RSS)
  * Feeds      — any RSS/Atom feed (address or short name)
  * Short info — the introduction of the Wikipedia article for a keyword
  * Roundup    — several sources at once, as a longer piece (minutes)

The text is deliberately "ready for moderation": `news.speakable` then turns it
into what is spoken.
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from html.parser import HTMLParser
from pydantic import BaseModel, Field

import meldungen as news  # same application (service radio-tts)

router = APIRouter()

KOPF = {"User-Agent": "Radio-Deadline-Beats/1.0 (Moderation; YOUR-EMAIL)"}
ZEIT = float(os.environ.get("RECHERCHE_TIMEOUT", "12"))

# Known feeds for "news" and as short names (the agent may mention them).
# All addresses verified on 2026-09-21 with HTTP 200 and readable XML.
FEEDS: dict[str, str] = {
    # news
    "tagesschau": "https://www.tagesschau.de/xml/rss2/",
    "tagesschau-wirtschaft": "https://www.tagesschau.de/wirtschaft/unternehmen/index~rss2.xml",
    "heise": "https://www.heise.de/rss/heise-atom.xml",
    "heise-security": "https://www.heise.de/security/rss/news-atom.xml",
    "spiegel": "https://www.spiegel.de/schlagzeilen/index.rss",
    "deutschlandfunk": "https://www.deutschlandfunk.de/news-100.rss",
    "ntv": "https://www.n-tv.de/rss",
    "faz": "https://www.faz.net/rss/aktuell/",
    "welt": "https://www.welt.de/feeds/latest.rss",
    "tagesspiegel": "https://www.tagesspiegel.de/contentexport/feed/home",
    "taz": "https://taz.de/!p4608;rss/",
    "mdr": "https://www.mdr.de/news/index-rss.xml",
    "swr": "https://www.swr.de/~rss/swraktuell/index.xml",
    # Technology, network and science
    "golem": "https://www.golem.de/rss.php?feed=RSS2.0",
    "netzpolitik": "https://netzpolitik.org/feed/",
    "t3n": "https://t3n.de/rss.xml",
    "computerbase": "https://www.computerbase.de/rss/news.xml",
    "scinexx": "https://www.scinexx.de/feed/",
    "ingenieur": "https://www.ingenieur.de/feed/",
    # Sports and weather
    "sport": "https://www.sportschau.de/index~rss2.xml",
    # Careful: the public weather feeds of weather.de/weather.com/tagesschau
    # now answer with 404. In the roundup, "weather" is therefore fetched via
    # Open-Meteo (see _overview).
    "weather": "https://www.weather.de/rss/weather-deutschland.xml",
}
NACHRICHTEN_FEED = os.environ.get("RECHERCHE_NEWS_FEED", FEEDS["tagesschau"])

# --- Roundup: several sources and topics in one longer piece -------
# Measured on the running service (2026-09-20): Piper/de_thorsten speaks about
# 1050 characters per minute (17.5 characters/s). The value now only serves the
# feedback ("this is how long it got") — the operator no longer prescribes a target length:
# the length results from what is found for the topics.
ZEICHEN_JE_MINUTE = int(os.environ.get("RECHERCHE_ZEICHEN_JE_MINUTE", "1050"))
# Sources when the operator names none (names from FEEDS).
# Without topics: the newest items of these news sources.
OVERVIEW_SOURCES = os.environ.get("RECHERCHE_UEBERBLICK_QUELLEN",
                                    "tagesschau,heise,spiegel,deutschlandfunk,ntv")
# With topics: search all sources (only hits on the topic are used) —
# a larger list costs nothing here, it only brings more places to find.
UEBERBLICK_QUELLEN_THEMEN = os.environ.get("RECHERCHE_UEBERBLICK_QUELLEN_THEMEN", "all")
# Standing topics of the station: "roundup" without own topics uses this list.
UEBERBLICK_THEMEN = os.environ.get("RECHERCHE_UEBERBLICK_THEMEN", "")
# How many items per topic go into the piece (web, press, feeds).
# 6 gives the press 3 slots and leaves one each for Wikipedia, web and feeds
# left over; for smaller values, the reservation below does the same.
THEMA_MELDUNGEN = int(os.environ.get("RECHERCHE_THEMA_MELDUNGEN", "6"))
# Distribution per topic: that many from the press, from the web (incl. the read page),
# from Wikipedia and from the own feeds.
THEMA_PRESSE = int(os.environ.get("RECHERCHE_THEMA_PRESSE", "3"))
THEMA_WEB = int(os.environ.get("RECHERCHE_THEMA_WEB", "1"))
THEMA_WIKI = int(os.environ.get("RECHERCHE_THEMA_WIKI", "1"))
THEMA_FEED = int(os.environ.get("RECHERCHE_THEMA_FEED", "1"))
# Maximum number of topics processed (protection against novels).
THEMEN_MAX = int(os.environ.get("RECHERCHE_THEMEN_MAX", "8"))
# Safety limit of the piece in characters (0 = only the announcement limit).
UEBERBLICK_MAX_ZEICHEN = int(os.environ.get("RECHERCHE_UEBERBLICK_MAX_ZEICHEN", "6000"))
# Use web search (DuckDuckGo lite) and Google News search per topic?
WEBSUCHE = os.environ.get("RECHERCHE_WEBSUCHE", "1") != "0"
PRESSE_SUCHE = os.environ.get("RECHERCHE_PRESSE", "1") != "0"
# Read the opening text from the first address found (normal web page)?
SEITE_LESEN = os.environ.get("RECHERCHE_SEITE_LESEN", "1") != "0"
# Addresses that are always read along (comma-separated).
WEBSEITEN = [u.strip() for u in os.environ.get("RECHERCHE_WEBSEITEN", "").split(",") if u.strip()]
# Some pages only deliver usable content with a browser identification.
WEB_KOPF = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Radio-Deadline-Beats/1.0"}
# Own search engine (SearXNG) for the web search: "http://192.168.178.26:8888".
# Empty = no own instance; then DuckDuckGo and Bing are tried.
SEARX_URL = os.environ.get("RECHERCHE_SEARX_URL", "").rstrip("/")
# Place for the weather block of the roundup (Open-Meteo, without key).
UEBERBLICK_WETTER_ORT = os.environ.get("RECHERCHE_WETTER_ORT", "Marbach am Neckar")
# How the moderator addresses a source (otherwise "From <name>").
QUELLEN_ANSPRACHE: dict[str, str] = {
    "tagesschau": "From the Tagesschau.",
    "tagesschau-wirtschaft": "From the Tagesschau, business.",
    "heise": "At Heise.",
    "heise-security": "At Heise Security.",
    "spiegel": "From the Spiegel.",
    "deutschlandfunk": "From Deutschlandfunk.",
    "ntv": "At n-tv.",
    "faz": "From the F.A.Z.",
    "welt": "From the Welt.",
    "tagesspiegel": "From the Tagesspiegel.",
    "taz": "From the taz.",
    "mdr": "From MDR.",
    "swr": "From SWR.",
    "golem": "At Golem.",
    "netzpolitik": "At Netzpolitik.",
    "t3n": "At t3n.",
    "computerbase": "At ComputerBase.",
    "scinexx": "At Scinexx.",
    "ingenieur": "At the Ingenieur.",
    "sport": "From the sports desk.",
    "weather": "And the weather.",
}

# Short form for "source: item" in the piece (spoken).
QUELLEN_KURZ: dict[str, str] = {
    "tagesschau": "Tagesschau",
    "tagesschau-wirtschaft": "Tagesschau business",
    "heise": "Heise",
    "heise-security": "Heise Security",
    "spiegel": "Spiegel",
    "deutschlandfunk": "Deutschlandfunk",
    "ntv": "n-tv",
    "faz": "F.A.Z.",
    "welt": "Welt",
    "tagesspiegel": "Tagesspiegel",
    "taz": "taz",
    "mdr": "MDR",
    "swr": "SWR",
    "golem": "Golem",
    "netzpolitik": "Netzpolitik",
    "t3n": "t3n",
    "computerbase": "ComputerBase",
    "scinexx": "Scinexx",
    "ingenieur": "Ingenieur",
    "sport": "Sportschau",
    "weather": "weather",
}


def _kurzname(name: str) -> str:
    """Short form of a source for the spoken text."""
    return QUELLEN_KURZ.get(name, str(name).capitalize())

# WMO weather codes (Open-Meteo) in plain words
WETTER_WORTE: dict[int, str] = {
    0: "klar", 1: "mostly clear", 2: "partly cloudy", 3: "bedeckt",
    45: "neblig", 48: "fog with frost", 51: "light drizzle",
    53: "Nieselregen", 55: "heavy drizzle", 56: "freezing drizzle",
    57: "heavy freezing drizzle", 61: "light rain", 63: "Regen",
    65: "heavy rain", 66: "freezing rain", 67: "heavy freezing rain",
    71: "light snowfall", 73: "Schneefall", 75: "heavy snowfall",
    77: "Schneegriesel", 80: "light rain showers", 81: "Regenschauer",
    82: "heavy rain showers", 85: "Schneeschauer", 86: "heavy snow showers",
    95: "Gewitter", 96: "thunderstorm with light hail", 99: "thunderstorm with hail",
}


class Recherche(BaseModel):
    type: Literal["weather", "news", "rss", "wikipedia", "overview"] = "weather"
    word: str = ""
    # Only for the roundup: topics ("ai, space") and requested sources.
    topics: str = ""
    sources: str = ""
    announce: bool = True
    important: bool = False
    dry: bool = False
    source: str = "research"


# ------------------------------------------------------------------ Helpers

def _holen(url: str, kopf: dict[str, str] | None = None, time: float | None = None) -> str:
    request = urllib.request.Request(url, headers={**KOPF, **(kopf or {})})
    try:
        with urllib.request.urlopen(request, timeout=time or ZEIT) as answer:
            return answer.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        raise HTTPException(status_code=502,
                            detail=f"Source answers with {error.code} ({url[:80]})") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise HTTPException(status_code=504,
                            detail=f"Source unreachable ({url[:80]}): {error}") from error


def _json_holen(url: str) -> Any:
    return json.loads(_holen(url))


def _text_von_html(raw: str, grenze: int = 400) -> str:
    """HTML to plain text: strip tags, resolve entities, shorten."""
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", str(raw or ""), flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > grenze:
        s = s[:grenze].rsplit(" ", 1)[0].rstrip(" ,;:") + "."
    return s


def _feed_adresse(word: str) -> str:
    """Feed address from short name or direct address."""
    short = (word or "").strip()
    if not short:
        return NACHRICHTEN_FEED
    if short.lower() in FEEDS:
        return FEEDS[short.lower()]
    if short.lower().startswith(("http://", "https://")):
        return short
    # Keyword instead of address: search the known feeds for it
    return NACHRICHTEN_FEED


def _feed_lesen(feed_url: str, count: int = 3, grenze: int = 400) -> list[dict[str, str]]:
    """The newest entries of an RSS or Atom feed.

    `grenze` is the length of the summary: 400 characters are enough for a
    single message; for the roundup more lines are needed.
    """
    raw = _holen(feed_url)
    try:
        baum = ET.fromstring(raw)
    except ET.ParseError as error:
        raise HTTPException(status_code=502,
                            detail=f"Feed not readable ({feed_url[:60]}): {error}") from error

    def ohne_namensraum(tag: str) -> str:
        return tag.rsplit("}", 1)[-1].lower()

    entries: list[dict[str, str]] = []
    for nodes in baum.iter():
        if ohne_namensraum(nodes.tag) not in ("item", "entry"):
            continue
        title = description = link = ""
        for kind in nodes:
            name = ohne_namensraum(kind.tag)
            if name == "title" and not title:
                title = _text_von_html(kind.text or "", 200)
            elif name in ("description", "summary", "content") and not description:
                description = _text_von_html(kind.text or "", grenze)
            elif name == "link" and not link:
                link = (kind.get("href") or kind.text or "").strip()
        if title or description:
            entries.append({"title": title, "text": description, "url": link})
        if len(entries) >= count:
            break
    return entries


# ------------------------------------------------------------------- Research

def _wetter(ort: str) -> dict[str, str]:
    """Weather for a place (Open-Meteo, without key)."""
    search = (ort or "").strip()
    if not search:
        raise HTTPException(status_code=400, detail="No place given (field ‘word’).")
    geo = _json_holen("https://geocoding-api.open-meteo.com/v1/search?"
                      + urllib.parse.urlencode({"name": search, "count": 1, "language": "de",
                                                "format": "json"}))
    hits = (geo or {}).get("results") or []
    if not hits:
        raise HTTPException(status_code=404, detail=f"Place ’{search}’ not found.")
    o = hits[0]
    name = str(o.get("name") or search)
    verwaltung = str(o.get("admin1") or "").strip()
    land = str(o.get("country") or "").strip()
    if verwaltung and name.lower() not in verwaltung.lower():
        anzeige = f"{name} in {verwaltung}"
    else:
        anzeige = name

    data = _json_holen("https://api.open-meteo.com/v1/forecast?"
                        + urllib.parse.urlencode({
                            "latitude": o["latitude"], "longitude": o["longitude"],
                            "current": "temperature_2m,weather_code,wind_speed_10m",
                            "daily": "temperature_2m_max,temperature_2m_min,"
                                     "precipitation_probability_max",
                            "timezone": "Europe/Berlin", "forecast_days": 2,
                        }))
    now = (data.get("current") or {})
    tag = (data.get("daily") or {})
    code = int(now.get("weather_code") or 0)
    status = WETTER_WORTE.get(code, "wechselhaft")

    def zahl(feld: str, stelle: int = 0) -> str:
        werte = tag.get(feld) or []
        if not werte or werte[0] is None:
            return "?"
        return f"{float(werte[0]):.{stelle}f}"

    teile = [f"In {anzeige} it is currently {float(now.get('temperature_2m') or 0):.0f} degrees,"
             f"plus {status}."]
    if tag.get("temperature_2m_max"):
        teile.append(f"Today up to {zahl('temperature_2m_max')} degrees are reached,"
                     f"at night it cools down to {zahl('temperature_2m_min')} degrees.")
    if tag.get("precipitation_probability_max"):
        teile.append(f"The rain probability is"
                     f"{zahl('precipitation_probability_max')} percent.")
    if now.get("wind_speed_10m") is not None:
        teile.append(f"The wind blows at"
                     f"{float(now.get('wind_speed_10m') or 0):.0f} kilometres per hour.")
    text = " ".join(teile)
    return {"title": f"Weather {anzeige}", "text": text,
            "url": f"https://open-meteo.com/", "ort": anzeige}


def _nachrichten(word: str) -> dict[str, str]:
    """The top item of a news feed; 'word' optionally filters."""
    feed = _feed_adresse(word)
    entries = _feed_lesen(feed, count=8)
    stichwort = (word or "").strip().lower()
    if stichwort and stichwort not in FEEDS and not stichwort.startswith("http"):
        passende = [e for e in entries
                    if stichwort in (e["title"] + " " + e["text"]).lower()]
        entries = passende or entries
    if not entries:
        raise HTTPException(status_code=404, detail="No item found in the feed.")
    neueste = entries[0]
    title = neueste["title"] or "News item"
    text = neueste["text"] or title
    if neueste["title"] and neueste["title"].lower() not in text.lower():
        text = f"{neueste['title']}. {text}"
    return {"title": title[:90], "text": text, "url": neueste["url"]}


def _rss(word: str) -> dict[str, str]:
    """Any feed (address or short name), top entry."""
    adresse = _feed_adresse(word)
    if adresse == NACHRICHTEN_FEED and (word or "").strip().lower() not in FEEDS:
        if not (word or "").strip().startswith("http"):
            raise HTTPException(status_code=400,
                                detail="For a feed please give the address"
                                       f"(or a short name: {', '.join(sorted(FEEDS))}).")
    entries = _feed_lesen(adresse, count=3)
    if not entries:
        raise HTTPException(status_code=404, detail="No entries in the feed.")
    neueste = entries[0]
    title = neueste["title"] or "New entry in the feed"
    text = neueste["text"] or title
    if neueste["title"] and neueste["title"].lower() not in text.lower():
        text = f"{neueste['title']}. {text}"
    return {"title": title[:90], "text": text, "url": neueste["url"]}


def _wiki_titel(thema: str) -> str:
    """Find the correct article title via the Wikipedia search.

    Necessary because the introduction interface needs the exact title:
    "kuenstliche intelligenz" returns 404, "Kuenstliche Intelligenz" does not.
    """
    adresse = ("https://de.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": thema, "srlimit": 1,
         "format": "json", "utf8": 1}))
    try:
        data = _json_holen(adresse)
    except (HTTPException, ValueError, json.JSONDecodeError):
        return ""
    hits = (((data.get("query") or {}).get("search")) or [])
    return str(hits[0].get("title") or "") if hits else ""


def _wiki_kurzinfo(title: str) -> dict[str, str]:
    """Fetch the introduction of an article (exact title needed)."""
    adresse = ("https://de.wikipedia.org/api/rest_v1/page/summary/"
               + urllib.parse.quote(title.replace(" ", "_")))
    data = _json_holen(adresse)
    # Disambiguation pages are worthless as background ("AI stands for: Sumerian
    # deity, ..."). Wikipedia marks them with type=disambiguation.
    if str(data.get("type") or "").lower() != "standard":
        raise HTTPException(status_code=404,
                            detail=f"No article for ’{title}’ (kind: {data.get('type')}).")
    text = _text_von_html(data.get("extract") or "", 500)
    if not text:
        raise HTTPException(status_code=404, detail=f"No article found for ’{title}’.")
    return {"title": str(data.get("title") or title)[:90], "text": text,
            "url": ((data.get("content_urls") or {}).get("desktop") or {}).get("page", "")}


def _wikipedia(word: str) -> dict[str, str]:
    """Short info for a keyword (Wikipedia introduction)."""
    thema = (word or "").strip()
    if not thema:
        raise HTTPException(status_code=400, detail="No keyword given (field ‘word’).")
    # Try several spellings, then fetch the title via the search.
    candidates = [thema, thema[:1].upper() + thema[1:],
                  " ".join(w[:1].upper() + w[1:] for w in thema.split())]
    error: HTTPException | None = None
    for versuch in dict.fromkeys(candidates):
        try:
            return _wiki_kurzinfo(versuch)
        except HTTPException as reason:
            error = reason
    title = _wiki_titel(thema)
    if title:
        try:
            return _wiki_kurzinfo(title)
        except HTTPException as reason:
            error = reason
    raise error or HTTPException(status_code=404,
                                  detail=f"No article found for ’{thema}’.")


def _sources_resolve(text: str) -> list[tuple[str, str]]:
    """Parse sources from a text: "heise and spiegel", "tagesschau, heise" or "all".

    First it searches exactly, then fuzzily (short forms). This matters since there are
    similar names: "heise" must not fall on "heise-security".
    """
    roh_text = str(text or "").strip().lower()
    if re.fullmatch(r"(all|everything|complete|entire|whole)", roh_text):
        return list(FEEDS.items())
    raw = re.sub(r"\b(and|plus|from|the|of|all|standard|"
                 r"usual|common|sources?)\b", " ", roh_text)
    names = [w for w in re.split(r"[\s,;+/]+\s*", raw) if len(w) > 1]
    if not names:
        names = [n.strip() for n in OVERVIEW_SOURCES.split(",") if n.strip()]

    chosen: list[tuple[str, str]] = []
    for name in names:
        hits = None
        if name in FEEDS:
            hits = name
        else:
            for short in sorted(FEEDS, key=len):   # short names first
                if len(name) >= 4 and len(short) >= 4 \
                        and (short.startswith(name[:5]) or name.startswith(short[:5])):
                    hits = short
                    break
        if hits and (hits, FEEDS[hits]) not in chosen:
            chosen.append((hits, FEEDS[hits]))
    if not chosen:   # nothing recognized: take the standard sources
        chosen = [(n.strip(), FEEDS[n.strip()]) for n in OVERVIEW_SOURCES.split(",")
                    if n.strip() in FEEDS]
    return chosen


def _themen_aufloesen(text: str) -> list[str]:
    """Parse topics from a text: "ai, space" or "ai and space"."""
    raw = str(text or "").strip() or UEBERBLICK_THEMEN
    if not raw:
        return []
    teile = re.split(r"\s*(?:,|;|\+|\band\b|\bplus\b|\btopics\b|\btopic\b)\s*", raw, flags=re.I)
    sauber: list[str] = []
    for teil in teile:
        t = teil.strip(" .:-–")
        t = re.sub(r"^(the|a|an|topics?|topic|about|to|"
                   r"news)\s+", "", t, flags=re.I)
        # Ignore old time specifications ("3 minutes") — the length results from
        # what is found.
        t = re.sub(r"\b\d{1,2}\s*(min|minute|minutes|sec|seconds)\b", " ", t, flags=re.I)
        t = re.sub(r"\s+", " ", t).strip()
        if len(t) >= 2 and t.lower() not in [s.lower() for s in sauber]:
            sauber.append(t)
    return sauber[:THEMEN_MAX]


class _SeitenLeser(HTMLParser):
    """Fetches title, description and paragraphs of a normal web page."""

    # Accessibility helpers for screen readers are in the source text but not visible —
    # unfiltered, "Pfeil right" would otherwise land in the middle of the spoken text.
    VERSTECKT = ("sr-only", "screen-reader", "visually-hidden", "visuallyhidden",
                 "skip-link", "skip-to", "a11y-hidden", "hidden-label")

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.absaetze: list[str] = []
        self._im_titel = False
        self._titel_fertig = False
        self._im_absatz = 0
        self._puffer: list[str] = []
        self._ueberspringen = 0
        self._versteckt_je_tag: dict[str, int] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {k.lower(): (v or "") for k, v in attrs}
        klasse = (data.get("class") or "").lower()
        if data.get("aria-hidden", "").lower() == "true" \
                or any(k in klasse for k in self.VERSTECKT):
            self._versteckt_je_tag[tag] = self._versteckt_je_tag.get(tag, 0) + 1
            self._ueberspringen += 1
        if tag == "title":
            # Only the page title counts — title elements inside symbols (<svg><title>)
            # carry labels like "Pfeil right" and would lengthen it.
            if not self._titel_fertig and not self._ueberspringen:
                self._im_titel = True
        elif tag in ("script", "style", "noscript", "nav", "footer", "header", "form", "svg",
                     "aside", "figure"):
            self._ueberspringen += 1
        elif tag == "meta":
            name = (data.get("name") or data.get("property") or "").lower()
            if name in ("description", "og:description", "twitter:description") \
                    and not self.description:
                self.description = data.get("content", "").strip()
        elif tag == "p" and not self._ueberspringen:
            self._im_absatz += 1
            self._puffer = []

    def handle_endtag(self, tag: str) -> None:
        if self._versteckt_je_tag.get(tag):
            self._versteckt_je_tag[tag] -= 1
            self._ueberspringen = max(0, self._ueberspringen - 1)
        if tag == "title":
            self._im_titel = False
            self._titel_fertig = True
        elif tag in ("script", "style", "noscript", "nav", "footer", "header", "form", "svg",
                     "aside", "figure"):
            self._ueberspringen = max(0, self._ueberspringen - 1)
        elif tag == "p" and self._im_absatz:
            self._im_absatz -= 1
            text = " ".join(" ".join(self._puffer).split())
            if len(text) > 40:
                self.absaetze.append(text)
            self._puffer = []

    def handle_data(self, data: str) -> None:
        if self._im_titel:
            self.title += data
        elif self._im_absatz and not self._ueberspringen:
            self._puffer.append(data)


def _seite_lesen(url: str, grenze: int = 900) -> dict[str, str]:
    """Read a normal web page: title and opening text.

    No third-party package: the text comes from the paragraphs (<p>), otherwise from
    the description in the head of the page. If neither suffices, the page is
    unusable (consent wall, only images) and is skipped.
    """
    raw = _holen(url)
    leser = _SeitenLeser()
    try:
        leser.feed(raw)
    except Exception:  # noqa: BLE001 - broken HTML is no reason to abort
        pass
    text = ""
    for absatz in leser.absaetze:
        # Do not read out section numbers like "1.1".
        absatz = re.sub(r"^\d+(?:\.\d+)*\s*[.):]?\s*", "", absatz).strip()
        if len(absatz) < 40:
            continue
        text = (text + " " + absatz).strip()
        if len(text) >= grenze:
            break
    if len(text) < 80:
        text = _text_von_html(leser.description or "", grenze)
    if len(text) < 80:
        text = _text_von_html(leser.title or "", 200)
    # The page title often carries the brand ("... | tagesschau.de") — do not read it out.
    title = re.sub(r"\s+[-–|]\s*(Wikipedia|WIKIPEDIA)\s*$", "", leser.title)
    title = re.sub(r"\s*[-–|]\s*[\w.-]+\.(?:de|com|org|net|at|ch|eu|io)\s*$", "", title)
    title = re.sub(r"\s+", " ", title).strip()[:120]
    if title and title.lower() not in text.lower()[:80]:
        text = (title + ". " + text).strip()
    return {"title": title or url, "text": _text_von_html(text, grenze), "url": url}


def _bing_ziel(verweis: str) -> str:
    """Bing wraps hits in a redirect link (u=a1<base64>)."""
    try:
        raw = urllib.parse.parse_qs(urllib.parse.urlparse(verweis).query).get("u", [""])[0]
        if raw.startswith("a1"):
            s = raw[2:]
            s += "=" * (-len(s) % 4)
            return base64.urlsafe_b64decode(s).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        pass
    return verweis


def _websuche(thema: str, count: int = 4) -> list[dict[str, str]]:
    """Web search — also finds normal web pages without a feed.

    Order: own search engine (SearXNG, `RECHERCHE_SEARX_URL`), then
    DuckDuckGo, then Bing. The public services block machines without
    login very differently (measured on 2026-09-21: DuckDuckGo answers
    with 202 without hits, Mojeek with captcha, Ecosia with 403, Bing with a
    result list). If none finds anything, the web search is silently skipped —
    press, Wikipedia and the feeds carry the piece.
    """
    if SEARX_URL:
        hits = _searx(thema, count)
        if hits:
            return hits

    hits: list[dict[str, str]] = []
    try:
        raw = _holen("https://lite.duckduckgo.com/lite/?" + urllib.parse.urlencode({"q": thema}),
                     kopf=WEB_KOPF)
        verweise = re.findall(r'href="(//duckduckgo\.com/l/\?uddg=[^"]+)"[^>]*'
                              r"class='result-link'>(.*?)</a>", raw, re.S)
        schnipsel = re.findall(r"class='result-snippet'>(.*?)</td>", raw, re.S)
        for i, (verweis, title) in enumerate(verweise[:count]):
            target = ""
            try:
                target = urllib.parse.parse_qs(
                    urllib.parse.urlparse(verweis).query).get("uddg", [""])[0]
            except Exception:  # noqa: BLE001
                target = ""
            hits.append({"title": _text_von_html(title, 120),
                            "text": _text_von_html(schnipsel[i], 300) if i < len(schnipsel) else "",
                            "url": target})
    except HTTPException as error:
        print(f"Web search (DuckDuckGo) ’{thema}’: {error.detail}", flush=True)

    if not hits:   # second way: Bing
        try:
            raw = _holen("https://www.bing.com/search?" + urllib.parse.urlencode(
                {"q": thema, "setlang": "de", "cc": "DE"}), kopf=WEB_KOPF)
            for block in re.findall(r'<li class="b_algo".*?</li>', raw, re.S)[:count]:
                m = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
                if not m:
                    continue
                p = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
                hits.append({"title": _text_von_html(m.group(2), 120),
                                "text": _text_von_html(p.group(1), 300) if p else "",
                                "url": _bing_ziel(html.unescape(m.group(1)))})
        except HTTPException as error:
            print(f"Web search (Bing) ’{thema}’: {error.detail}", flush=True)
    return hits


def _searx(thema: str, count: int = 4) -> list[dict[str, str]]:
    """Web search via an own SearXNG instance (JSON interface)."""
    try:
        adresse = SEARX_URL + "/search?" + urllib.parse.urlencode(
            {"q": thema, "format": "json", "language": "de-DE"})
        data = _json_holen(adresse)
    except (HTTPException, ValueError, json.JSONDecodeError) as error:
        print(f"Web search (SearXNG) ’{thema}’: {error}", flush=True)
        return []
    hits: list[dict[str, str]] = []
    for e in (data.get("results") or [])[:count]:
        target = str(e.get("url") or "")
        if not target.startswith("http"):
            continue
        hits.append({"title": str(e.get("title") or "")[:120],
                        "text": _text_von_html(str(e.get("content") or ""), 300),
                        "url": target})
    return hits


def _google_news(thema: str, count: int = 4) -> list[dict[str, str]]:
    """Press search per topic via Google News (RSS) — delivers the source along."""
    adresse = ("https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": thema, "hl": "de", "gl": "DE", "ceid": "DE:de"}))
    try:
        raw = _holen(adresse)
        baum = ET.fromstring(raw)
    except (HTTPException, ET.ParseError) as error:
        print(f"Press search ’{thema}’ not possible: {error}", flush=True)
        return []
    hits: list[dict[str, str]] = []
    for nodes in baum.iter():
        if nodes.tag.rsplit("}", 1)[-1] != "item":
            continue
        title = text = source = ""
        for kind in nodes:
            name = kind.tag.rsplit("}", 1)[-1].lower()
            if name == "title" and not title:
                title = _text_von_html(kind.text or "", 160)
            elif name in ("description", "summary") and not text:
                text = _text_von_html(kind.text or "", 400)
            elif name == "source" and not source:
                source = _text_von_html(kind.text or "", 60)
        # Google appends the source to the title ("... - heise online")
        if source and title.lower().endswith(source.lower()):
            title = title[: len(title) - len(source)].rstrip(" -–")
        # The description repeats the title — the rest is the opening text.
        for abschneiden in (title, source):
            if abschneiden and text.lower().startswith(abschneiden.lower()):
                text = text[len(abschneiden):].strip(" .-–")
        if text.lower().startswith(title.lower()):
            text = text[len(title):].strip(" .-–")
        if title or text:
            hits.append({"title": title, "text": text, "source": source})
        if len(hits) >= count:
            break
    return hits


def _feeds_holen(sources: list[tuple[str, str]]) -> tuple[list[tuple[str, list[dict[str, str]]]],
                                                        list[str]]:
    """Read all named sources once (weather via Open-Meteo).

    Returns the read blocks and the names of the sources that were NOT
    reachable (that is different from "had nothing on the topic").
    """
    blocks: list[tuple[str, list[dict[str, str]]]] = []
    missing: list[str] = []
    for name, adresse in sources:
        if name == "weather":
            try:
                w = _wetter(UEBERBLICK_WETTER_ORT)
                blocks.append((name, [{"title": "weather", "text": w["text"],
                                        "url": w.get("url", "")}]))
            except HTTPException as error:
                print(f"Roundup: weather not readable: {error.detail}", flush=True)
                missing.append(name)
            continue
        try:
            entries = _feed_lesen(adresse, count=10, grenze=700)
        except HTTPException as error:   # one source may fail
            print(f"Roundup: source {name} not readable: {error.detail}", flush=True)
            missing.append(name)
            continue
        if entries:
            blocks.append((name, entries))
        else:
            missing.append(name)
    return blocks, missing


def _passt_zum_thema(entry: dict[str, str], thema: str) -> bool:
    """Is the topic in the title or text of the item?"""
    words = [w for w in re.split(r"[^a-z0-9]+", thema.lower()) if len(w) > 2]
    if not words:
        return False
    heu = (entry.get("title", "") + " " + entry.get("text", "")).lower()
    return sum(1 for w in words if w in heu) >= max(1, len(words) - 1)


def _stueck(source: str, title: str, text: str, grenze: int = 300) -> str:
    """A message piece for the spoken text: \"source: title. opening\"."""
    title = re.sub(r"\s+", " ", str(title or "")).strip(" .")
    beginning = re.sub(r"\s+", " ", str(text or "")).strip()
    if title and title.lower() not in beginning.lower():
        beginning = (title + ". " + beginning).strip()
    beginning = beginning[:grenze].rsplit(" ", 1)[0].rstrip(" ,;:") if len(beginning) > grenze else beginning
    if beginning and not beginning.endswith((".", "!", "?")):
        beginning += "."
    return f"{source}: {beginning}" if source else beginning


def _overview(themen_text: str = "", sources_text: str = "") -> dict[str, Any]:  # noqa: C901
    """Collect topics: web search, press search and the feeds of the source.

    There is no fixed length any more: the piece grows with what is found
    for the topics (safety limit: RECHERCHE_UEBERBLICK_MAX_ZEICHEN or
    the length limit of an announcement). Without topics, the newest items of the
    named sources come.
    """
    topics = _themen_aufloesen(themen_text)
    if not sources_text.strip():
        sources_text = UEBERBLICK_QUELLEN_THEMEN if topics else OVERVIEW_SOURCES
    sources = _sources_resolve(sources_text)
    if not sources and not topics:
        raise HTTPException(status_code=400,
                            detail="No source. Known:" + ", ".join(sorted(FEEDS)))
    blocks, not_reachable = _feeds_holen(sources)
    grenze = UEBERBLICK_MAX_ZEICHEN or news.MAX_CHARACTERS
    grenze = min(grenze, news.MAX_CHARACTERS)

    teile: list[str] = []
    laenge = 0
    used: list[str] = []          # sources that really contributed something
    gelesen: list[str] = []          # addresses that the bot opened
    presse_anzahl = 0                # items from the press search
    web_anzahl = 0                   # items from the web search or from pages
    wiki_anzahl = 0                  # background from Wikipedia

    def anhaengen(stueck: str) -> None:
        nonlocal laenge
        if stueck:
            teile.append(stueck)
            laenge += len(stueck)

    if topics:
        for thema in topics:
            if laenge >= grenze:
                break
            stuecke: list[str] = []      # collect first, then announce
            presse_hier = web_hier = wiki_hier = feed_hier = 0
            seite_gelesen = False        # open at most one page per topic
            # Slots per topic: the press must not take all — for Wikipedia,
            # web and feed one slot each stays reserved. Otherwise a topic delivers
            # only headlines (the press hits carry no running text).
            reserve = ((1 if THEMA_WIKI > 0 else 0) + (1 if THEMA_WEB > 0 else 0)
                       + (1 if THEMA_FEED > 0 else 0))
            presse_max = min(THEMA_PRESSE, max(1, THEMA_MELDUNGEN - reserve))

            # 1) Press search: what do the newspapers write about it?
            if PRESSE_SUCHE:
                for t in _google_news(thema, 4):
                    if presse_hier >= presse_max or len(stuecke) >= THEMA_MELDUNGEN:
                        break
                    # In the description, Google often delivers a mix of several
                    # headlines. For the spoken text the headline alone is
                    # cleaner — content comes from the page and the feeds.
                    stuecke.append(_stueck(_quellenname(t.get("source")), t.get("title", ""), "", 200))
                    presse_hier += 1

            # 2) Wikipedia: background on the topic (always readable, without key).
            if THEMA_WIKI and wiki_hier < 1 and len(stuecke) < THEMA_MELDUNGEN:
                wiki_daten = None
                for versuch in (thema, thema[:1].upper() + thema[1:]):
                    try:
                        wiki_daten = _wikipedia(versuch)
                        break
                    except HTTPException as error:
                        print(f"Wikipedia '{versuch}': {error.detail}", flush=True)
                if wiki_daten:
                    stuecke.append(_stueck("Wikipedia", wiki_daten.get("title", ""),
                                           wiki_daten.get("text", ""), 400))
                    wiki_hier = 1

            # 3) Web search: also finds pages without feed — and reads the first.
            if WEBSUCHE and web_hier < THEMA_WEB and len(stuecke) < THEMA_MELDUNGEN:
                for t in _websuche(thema, 4):
                    if web_hier >= THEMA_WEB or len(stuecke) >= THEMA_MELDUNGEN:
                        break
                    target = t.get("url") or ""
                    # Really read the first address found — "normal web page".
                    if target and SEITE_LESEN and not seite_gelesen:
                        try:
                            seite = _seite_lesen(target)
                        except HTTPException as error:
                            print(f"Page {target[:60]} not readable: {error.detail}", flush=True)
                            seite = {}
                        if len(seite.get("text", "")) >= 120:
                            gelesen.append(target)
                            seite_gelesen = True
                            stuecke.append(_stueck(_seitenname(target), seite.get("title", ""),
                                                   seite.get("text", ""), 500))
                            web_hier += 1
                            continue
                    stuecke.append(_stueck(_seitenname(target), t.get("title", ""),
                                           t.get("text", "")))
                    web_hier += 1

            # 4) The own feeds: matching items on the topic.
            for name, entries in blocks:
                if feed_hier >= THEMA_FEED or len(stuecke) >= THEMA_MELDUNGEN:
                    break
                passend = [e for e in entries if _passt_zum_thema(e, thema)]
                if not passend:
                    continue
                e = passend[0]
                stuecke.append(_stueck(_kurzname(name), e["title"], e["text"], 300))
                feed_hier += 1
                if name not in used:
                    used.append(name)

            # A topic without a find is not announced (otherwise an empty announcement).
            if not stuecke:
                continue
            anhaengen(f"On the topic {thema}.")
            for stueck in stuecke:
                anhaengen(stueck)
                if laenge >= grenze:
                    break
            presse_anzahl += presse_hier
            web_anzahl += web_hier
            wiki_anzahl += wiki_hier
    else:
        # Without topics: the newest item per named source (one round).
        for name, entries in blocks:
            if laenge >= grenze:
                break
            if not entries:
                continue
            anhaengen(QUELLEN_ANSPRACHE.get(name, f"From {name}."))
            e = entries[0]
            anhaengen(_stueck("", e["title"], e["text"], 400))
            if name not in used:
                used.append(name)

    if not teile:
        raise HTTPException(status_code=504, detail="Nothing was found on these topics.")

    # Always read the configured pages along (addition, not replacement).
    for adresse in WEBSEITEN:
        if laenge >= grenze:
            break
        try:
            seite = _seite_lesen(adresse)
        except HTTPException as error:
            print(f"Web page {adresse[:60]} not readable: {error.detail}", flush=True)
            continue
        if len(seite.get("text", "")) < 120:
            continue
        gelesen.append(adresse)
        anhaengen(_stueck(_seitenname(adresse), seite.get("title", ""),
                          seite.get("text", ""), 500))

    missing = not_reachable
    text = re.sub(r"\s+", " ", " ".join(t for t in teile if t)).strip()
    text = news.shorten(text, grenze)
    return {"title": "Roundup of the news", "text": text, "url": "",
            "sources": used, "topics": topics,
            "minutes": round(len(text) / ZEICHEN_JE_MINUTE, 1),
            "presse": presse_anzahl, "web": web_anzahl, "wiki": wiki_anzahl,
            "gelesen": gelesen, "ausgefallen": missing}


def _quellenname(name: str) -> str:
    """Make the name of a press generator speakable.

    Google News here delivers sometimes "DIE ZEIT", sometimes "De" or "heise online" —
    short or cryptic entries are replaced by "From the web".
    """
    s = re.sub(r"\s+", " ", str(name or "")).strip(" .-–")
    if len(s) < 3 or re.fullmatch(r"[A-Za-z]{2,4}\.?", s):
        return ""          # without a name, rather speak only the headline
    for alt, new in ((" online", ""), (".de", ""), (".com", "")):
        if s.lower().endswith(alt):
            s = s[: -len(alt)]
    return s[:28]


def _seitenname(url: str) -> str:
    """A speakable name for an address: \"heise.de\" -> \"Heise\"."""
    try:
        wirt = urllib.parse.urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return ""
    wirt = re.sub(r"^www\.", "", wirt)
    wirt = wirt.split(":")[0]
    teile = [t for t in wirt.split(".") if t]
    # "de.wikipedia.org" -> "wikipedia", "heise.de" -> "heise"
    haupt = teile[-2] if len(teile) >= 3 else (teile[0] if teile else "")
    names = {"sz": "SZ", "faz": "F.A.Z.", "n-tv": "n-tv", "t3n": "t3n", "mdr": "MDR",
             "swr": "SWR", "br": "BR", "ard": "ARD", "zdf": "ZDF", "rnd": "RND",
             "taz": "taz", "sueddeutsche": "Süddeutsche", "handelsblatt": "Handelsblatt",
             "heise": "Heise", "golem": "Golem", "spiegel": "Spiegel", "time": "Zeit",
             "welt": "Welt", "tagesspiegel": "Tagesspiegel", "netzpolitik": "Netzpolitik",
             "computerbase": "ComputerBase", "scinexx": "Scinexx", "ingenieur": "Ingenieur",
             "wikipedia": "Wikipedia", "github": "GitHub", "bund": "Der Bund",
             "bmftr": "Bundesministerium", "europarl": "European Parliament"}
    return names.get(haupt, haupt.capitalize() if haupt else "")


def research(type: str, word: str, sources: str = "",
                  topics: str = "") -> dict[str, Any]:
    """Fetches the data and returns title, text and source."""
    chosen = (type or "weather").lower()
    if chosen == "weather":
        return _wetter(word)
    if chosen in ("news", "news"):
        return _nachrichten(word)
    if chosen in ("rss", "feed"):
        return _rss(word)
    if chosen in ("wikipedia", "info", "kurzinfo"):
        return _wikipedia(word)
    if chosen in ("overview", "roundup!", "overview", "rundschau", "rundumblick",
                    "topics", "themenueberblick"):
        return _overview(topics or word, sources)
    raise HTTPException(status_code=400,
                        detail="type must be weather, news, rss, wikipedia or overview.")


# -------------------------------------------------------------------- Endpoint

@router.post("/research")
def research(request: Recherche,
              x_news_key: str | None = Header(default=None)) -> dict[str, Any]:
    """Fetches weather/news/feed/short info, stores a message and announces it.

    `announce: false` only stores the message (the bot can present it later in Telegram
    ), `dry: true` only creates the audio of the announcement.
    """
    news._pruefen(x_news_key)  # noqa: SLF001 - same service
    result = research(request.type, request.word, request.sources, request.topics)

    type = {"feed": "rss", "news": "news", "info": "wikipedia",
           "kurzinfo": "wikipedia", "overview": "overview",
           "rundschau": "overview", "rundumblick": "overview",
           "topics": "overview", "themenueberblick": "overview"}.get(
               request.type.lower().strip("!"), request.type.lower().strip("!"))
    entry = news.record(source=request.source or request.type, type=type,
                                  title=result.get("title", ""), text=result.get("text", ""),
                                  important=bool(request.important), from_="research",
                                  url=result.get("url", ""))

    answer: dict[str, Any] = {
        "ok": True, "id": entry["id"], "type": entry["type"], "title": entry["title"],
        "text": entry["text"], "source": result.get("url", ""),
        "spoken_text": news.moderation_text(entry), "said": False,
        "open": news.offene_zahl(),
    }
    if result.get("sources") or result.get("topics"):
        answer["sources"] = result.get("sources") or []
        answer["topics"] = result.get("topics") or []
        answer["minutes"] = result.get("minutes")
        answer["presse"] = result.get("presse", 0)
        answer["web"] = result.get("web", 0)
        answer["wiki"] = result.get("wiki", 0)
        answer["gelesen"] = result.get("gelesen") or []
        answer["ausgefallen"] = result.get("ausgefallen") or []
    if request.announce:
        announcement = news.ansage_machen(entry["id"], dry=request.dry,
                                        voice="", speed=1.0)
        answer["said"] = not request.dry
        answer["duration_seconds"] = announcement.get("duration_seconds")
        answer["spoken"] = announcement.get("spoken") or answer["spoken_text"]
        if type == "overview":
            duration = announcement.get("duration_seconds") or 0
            topics = result.get("topics") or []
            sources = result.get("sources") or []
            wo = ("Topics " + ", ".join(topics)) if topics else ("sources " + ", ".join(sources[:6]))
            extra = []
            if result.get("presse"):
                extra.append(f"{result['presse']} from the press")
            if result.get("wiki"):
                extra.append("with background")
            if result.get("web"):
                extra.append(f"{result['web']} from the web")
            answer["answer"] = (f"\U0001f399\ufe0f Roundup"
                                  f"{'said' if answer['said'] else 'prepared'} "
                                  f"({duration / 60:.1f} min, {wo}"
                                  + ((", " + ", ".join(extra)) if extra else "") + ")")
        else:
            answer["answer"] = announcement.get("answer") or (
                f"\U0001f399\ufe0f {entry['title']}: {answer['spoken'][:160]}")
    else:
        answer["answer"] = (f"\U0001f4dd Stored: {entry['title']}"
                              f"({len(entry['text'])} characters)")
    return answer


@router.get("/research/feeds")
def recherche_feeds() -> dict[str, Any]:
    """The known sources, kinds and settings of the roundup."""
    return {"feeds": FEEDS, "news": NACHRICHTEN_FEED,
            "types": ["weather", "news", "rss", "wikipedia", "overview"],
            "overview": {"sources": OVERVIEW_SOURCES,
                            "quellen_mit_themen": UEBERBLICK_QUELLEN_THEMEN,
                            "topics": UEBERBLICK_THEMEN,
                            "thema_meldungen": THEMA_MELDUNGEN,
                            "thema_presse": THEMA_PRESSE,
                            "thema_web": THEMA_WEB,
                            "thema_feed": THEMA_FEED,
                            "themen_max": THEMEN_MAX,
                            "max_zeichen": UEBERBLICK_MAX_ZEICHEN,
                            "websuche": WEBSUCHE,
                            "searx_url": SEARX_URL,
                            "presse_suche": PRESSE_SUCHE,
                            "seite_lesen": SEITE_LESEN,
                            "webseiten": WEBSEITEN,
                            "wetter_ort": UEBERBLICK_WETTER_ORT,
                            "zeichen_je_minute": ZEICHEN_JE_MINUTE}}
