"""Recherche: Wetter, Nachrichten, Feeds und Kurzinfos auf Zuruf.

Der Betreiber sagt im Telegram zum Beispiel „suche nach dem Wetter fuer Marbach am
Neckar". Der Agent ruft damit `POST /recherche` auf; dieses Modul holt die Daten,
baut daraus einen Moderationstext, legt ihn als Meldung ins Postfach
(`meldungen.py`) und spricht ihn auf Wunsch sofort in den Sender.

Alles kostenlos und ohne Schluessel:

  * Wetter     — Open-Meteo (Ortssuche per Geocoding, Vorhersage fuer heute)
  * Nachrichten— die oberste Meldung aus einem deutschen Nachrichten-Feed (RSS)
  * Feeds      — ein beliebiger RSS-/Atom-Feed (Adresse oder Kurzname)
  * Kurzinfo   — die Einleitung des Wikipedia-Artikels zu einem Stichwort
  * Ueberblick — mehrere Quellen auf einmal, als laengerer Beitrag (Minuten).
    Zu einem Thema kommen Schlagzeilen der Presse, Seiten **bekannter
    Nachrichten-Anbieter** und die eigenen Feeds; Wikipedia-Definitionen und
    Werbeseiten sind absichtlich NICHT dabei (Betreiber-Wunsch 2026-09-25).

Der Text ist bewusst „moderationsfertig": `meldungen.sprechbar` macht daraus
anschliessend das, was gesprochen wird.
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

import meldungen  # gleiche Anwendung (Dienst radio-tts)

router = APIRouter()

KOPF = {"User-Agent": "Radio-Deadline-Beats/1.0 (Moderation; kontakt@deadlinedriven.dev)"}
ZEIT = float(os.environ.get("RECHERCHE_TIMEOUT", "12"))

# Bekannte Feeds fuer "Nachrichten" und als Kurznamen (der Agent darf sie nennen).
# Alle Adressen am 2026-09-21 mit HTTP 200 und lesbarem XML geprueft.
FEEDS: dict[str, str] = {
    # Nachrichten
    "tagesschau": "https://www.tagesschau.de/xml/rss2/",
    "tagesschau-wirtschaft": "https://www.tagesschau.de/wirtschaft/unternehmen/index~rss2.xml",
    "heise": "https://www.heise.de/rss/heise-atom.xml",
    "heise-security": "https://www.heise.de/security/rss/news-atom.xml",
    "spiegel": "https://www.spiegel.de/schlagzeilen/index.rss",
    "deutschlandfunk": "https://www.deutschlandfunk.de/nachrichten-100.rss",
    "ntv": "https://www.n-tv.de/rss",
    "faz": "https://www.faz.net/rss/aktuell/",
    "welt": "https://www.welt.de/feeds/latest.rss",
    "tagesspiegel": "https://www.tagesspiegel.de/contentexport/feed/home",
    "taz": "https://taz.de/!p4608;rss/",
    "mdr": "https://www.mdr.de/nachrichten/index-rss.xml",
    "swr": "https://www.swr.de/~rss/swraktuell/index.xml",
    # Technik, Netz und Wissenschaft
    "golem": "https://www.golem.de/rss.php?feed=RSS2.0",
    "netzpolitik": "https://netzpolitik.org/feed/",
    "t3n": "https://t3n.de/rss.xml",
    "computerbase": "https://www.computerbase.de/rss/news.xml",
    "scinexx": "https://www.scinexx.de/feed/",
    "ingenieur": "https://www.ingenieur.de/feed/",
    # Sport und Wetter
    "sport": "https://www.sportschau.de/index~rss2.xml",
    # Achtung: die oeffentlichen Wetter-Feeds von wetter.de/wetter.com/tagesschau
    # antworten inzwischen mit 404. Im Ueberblick wird "wetter" deshalb ueber
    # Open-Meteo geholt (siehe _ueberblick).
    "wetter": "https://www.wetter.de/rss/wetter-deutschland.xml",
}
NACHRICHTEN_FEED = os.environ.get("RECHERCHE_NEWS_FEED", FEEDS["tagesschau"])

# --- Ueberblick: mehrere Quellen und Themen in einem laengeren Beitrag -------
# Gemessen am laufenden Dienst (2026-09-20): Piper/de_thorsten spricht rund
# 1050 Zeichen je Minute (17,5 Zeichen/s). Der Wert dient nur noch der
# Rueckmeldung ("so und so lang wurde es") - eine Ziellaenge gibt der Betreiber
# nicht mehr vor: die Laenge ergibt sich aus dem, was zu den Themen gefunden wird.
ZEICHEN_JE_MINUTE = int(os.environ.get("RECHERCHE_ZEICHEN_JE_MINUTE", "1050"))
# Quellen, wenn der Betreiber keine nennt (Namen aus FEEDS).
# Ohne Themen: die neuesten Meldungen dieser Nachrichtenquellen.
UEBERBLICK_QUELLEN = os.environ.get("RECHERCHE_UEBERBLICK_QUELLEN",
                                    "tagesschau,heise,spiegel,deutschlandfunk,ntv")
# Mit Themen: alle Quellen durchsuchen (nur Treffer zum Thema werden verwendet) -
# eine groessere Liste kostet hier nichts, sie bringt nur mehr Fundstellen.
UEBERBLICK_QUELLEN_THEMEN = os.environ.get("RECHERCHE_UEBERBLICK_QUELLEN_THEMEN", "alle")
# Stehende Themen des Senders: "ueberblick" ohne eigene Themen nutzt diese Liste.
UEBERBLICK_THEMEN = os.environ.get("RECHERCHE_UEBERBLICK_THEMEN", "")
# Wie viele Meldungen je Thema in den Beitrag kommen (Web, Presse, Feeds).
# 6 gibt der Presse 3 Plaetze und laesst je einen fuer Wikipedia, Netz und Feeds
# uebrig; bei kleineren Werten sorgt die Reservierung unten fuer dasselbe.
THEMA_MELDUNGEN = int(os.environ.get("RECHERCHE_THEMA_MELDUNGEN", "6"))
# Aufteilung je Thema: so viele aus der Presse, aus dem Netz (inkl. gelesener Seite),
# aus Wikipedia (nicht mehr im Nachrichten-Ueberblick, siehe unten) und den Feeds.
THEMA_PRESSE = int(os.environ.get("RECHERCHE_THEMA_PRESSE", "3"))
THEMA_WEB = int(os.environ.get("RECHERCHE_THEMA_WEB", "1"))
# Wikipedia-Definitionen gehoerten frueher fest in jeden Themen-Ueberblick. Auf
# Wunsch des Betreibers (2026-09-25) NICHT mehr: wer Nachrichten zu einem Thema
# will, hoert Schlagzeilen und Berichte, keine Lexikon-Einleitungen. Fuer "was ist
# X" bleibt art=wikipedia; RECHERCHE_THEMA_WIKI=1 holt die Definition zurueck.
THEMA_WIKI = int(os.environ.get("RECHERCHE_THEMA_WIKI", "0"))
THEMA_FEED = int(os.environ.get("RECHERCHE_THEMA_FEED", "1"))
# Wie viele Themen hoechstens verarbeitet werden (Schutz vor Romanen).
THEMEN_MAX = int(os.environ.get("RECHERCHE_THEMEN_MAX", "8"))
# Sicherheitsgrenze des Beitrags in Zeichen (0 = nur die Ansagegrenze).
UEBERBLICK_MAX_ZEICHEN = int(os.environ.get("RECHERCHE_UEBERBLICK_MAX_ZEICHEN", "6000"))
# Websuche (DuckDuckGo lite) und Google-News-Suche je Thema benutzen?
WEBSUCHE = os.environ.get("RECHERCHE_WEBSUCHE", "1") != "0"
PRESSE_SUCHE = os.environ.get("RECHERCHE_PRESSE", "1") != "0"
# Von der ersten gefundenen Adresse den Anfangstext lesen (normale Internetseite)?
SEITE_LESEN = os.environ.get("RECHERCHE_SEITE_LESEN", "1") != "0"
# Adressen, die immer mitgelesen werden (kommagetrennt).
WEBSEITEN = [u.strip() for u in os.environ.get("RECHERCHE_WEBSEITEN", "").split(",") if u.strip()]
# Manche Seiten liefern nur mit Browser-Kennung brauchbaren Inhalt.
WEB_KOPF = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Radio-Deadline-Beats/1.0"}

# Aus der Websuche kommen nur Seiten bekannter Nachrichten-Anbieter in den
# Beitrag. Andere Treffer waren zu oft Werbe- oder Klickseiten ("Aktienbrief
# kostenlos + unverbindlich ...", Draht-Meldungen) - das klingt im Radio falsch.
# Erweitern per RECHERCHE_SEITEN_LISTE (kommagetrennt).
SEITEN_LISTE = [s.strip().lower() for s in os.environ.get(
    "RECHERCHE_SEITEN_LISTE",
    "spiegel.de,sz.de,sueddeutsche.de,faz.net,zeit.de,heise.de,golem.de,tagesschau.de,"
    "tagesspiegel.de,welt.de,ntv.de,n-tv.de,taz.de,handelsblatt.com,manager-magazin.de,"
    "wiwo.de,capital.de,t-online.de,focus.de,stern.de,businessinsider.de,mdr.de,br.de,"
    "swr.de,wdr.de,ndr.de,deutschlandfunk.de,zdf.de,ard.de,orf.at,netzpolitik.org,"
    "t3n.de,computerbase.de,scinexx.de,ingenieur.de,sportschau.de").split(",")
    if s.strip()]


def _seite_vertraut(url: str) -> bool:
    """Ist die Adresse eine bekannte Nachrichten-Seite?"""
    try:
        wirt = urllib.parse.urlparse(url).netloc.lower()
    except ValueError:
        return False
    wirt = re.sub(r"^www\.", "", wirt)
    return any(wirt == d or wirt.endswith("." + d) for d in SEITEN_LISTE)


# Fertige Seiten, die wie ein Kassenbon klingen (Kurse, Abos, Rechtliches)
# statt wie ein Bericht: sie fliegen aus dem Themen-Ueberblick.
SEITE_VERBOTEN = ("Keine Gewähr", "Datenschutzerklärung", "zeitverzögert",
                   "Cookie-Einstellungen", "Impressum", "Nutzungsbedingungen",
                   "Alle Rechte vorbehalten", "Infront")


def _seite_brauchbar(seite: dict) -> bool:
    """Steht in der gelesenen Seite ein Bericht (oder nur Beiwerk)?"""
    text = str(seite.get("text") or "")
    return len(text) >= 120 and not any(m in text for m in SEITE_VERBOTEN)
# Eigene Suchmaschine (SearXNG) fuer die Websuche: "http://192.168.178.26:8888".
# Leer = keine eigene Instanz; dann werden DuckDuckGo und Bing versucht.
SEARX_URL = os.environ.get("RECHERCHE_SEARX_URL", "").rstrip("/")
# Ort fuer den Wetterblock des Ueberblicks (Open-Meteo, ohne Schluessel).
UEBERBLICK_WETTER_ORT = os.environ.get("RECHERCHE_WETTER_ORT", "Marbach am Neckar")
# Wie der Moderator eine Quelle anspricht (sonst "Aus <Name>").
QUELLEN_ANSPRACHE: dict[str, str] = {
    "tagesschau": "Aus der Tagesschau.",
    "tagesschau-wirtschaft": "Aus der Tagesschau, Wirtschaft.",
    "heise": "Bei Heise.",
    "heise-security": "Bei Heise Security.",
    "spiegel": "Aus dem Spiegel.",
    "deutschlandfunk": "Aus dem Deutschlandfunk.",
    "ntv": "Bei n-tv.",
    "faz": "Aus der F.A.Z.",
    "welt": "Aus der Welt.",
    "tagesspiegel": "Aus dem Tagesspiegel.",
    "taz": "Aus der taz.",
    "mdr": "Vom MDR.",
    "swr": "Vom SWR.",
    "golem": "Bei Golem.",
    "netzpolitik": "Bei Netzpolitik.",
    "t3n": "Bei t3n.",
    "computerbase": "Bei ComputerBase.",
    "scinexx": "Bei Scinexx.",
    "ingenieur": "Beim Ingenieur.",
    "sport": "Aus dem Sport.",
    "wetter": "Und das Wetter.",
}

# Wie die Quelle im Sprechtext genannt wird ("Das meldet die Tagesschau.").
QUELLEN_KURZ: dict[str, str] = {
    "tagesschau": "die Tagesschau",
    "tagesschau-wirtschaft": "die Tagesschau",
    "heise": "Heise",
    "heise-security": "Heise Security",
    "spiegel": "der Spiegel",
    "deutschlandfunk": "der Deutschlandfunk",
    "ntv": "n-tv",
    "faz": "die F.A.Z.",
    "welt": "die Welt",
    "tagesspiegel": "der Tagesspiegel",
    "taz": "die taz",
    "mdr": "der MDR",
    "swr": "der SWR",
    "golem": "Golem",
    "netzpolitik": "Netzpolitik",
    "t3n": "t3n",
    "computerbase": "ComputerBase",
    "scinexx": "Scinexx",
    "ingenieur": "der Ingenieur",
    "sport": "die Sportschau",
    "wetter": "das Wetter",
}


def _kurzname(name: str) -> str:
    """Kurzform einer Quelle fuer den Sprechtext."""
    return QUELLEN_KURZ.get(name, str(name).capitalize())

# WMO-Wettercodes (Open-Meteo) auf Deutsch
WETTER_WORTE: dict[int, str] = {
    0: "klar", 1: "überwiegend klar", 2: "wechselnd bewölkt", 3: "bedeckt",
    45: "neblig", 48: "neblig mit Reif", 51: "leichter Nieselregen",
    53: "Nieselregen", 55: "starker Nieselregen", 56: "gefrierender Nieselregen",
    57: "starker gefrierender Nieselregen", 61: "leichter Regen", 63: "Regen",
    65: "starker Regen", 66: "gefrierender Regen", 67: "starker gefrierender Regen",
    71: "leichter Schneefall", 73: "Schneefall", 75: "starker Schneefall",
    77: "Schneegriesel", 80: "leichte Regenschauer", 81: "Regenschauer",
    82: "heftige Regenschauer", 85: "Schneeschauer", 86: "starke Schneeschauer",
    95: "Gewitter", 96: "Gewitter mit leichtem Hagel", 99: "Gewitter mit Hagel",
}


class Recherche(BaseModel):
    art: Literal["wetter", "nachrichten", "rss", "wikipedia", "ueberblick"] = "wetter"
    wort: str = ""
    # Nur fuer den Ueberblick: Themen ("ki, raumfahrt") und gewuenschte Quellen.
    themen: str = ""
    quellen: str = ""
    ansagen: bool = True
    wichtig: bool = False
    trocken: bool = False
    quelle: str = "recherche"
    # Stimme der Ansage: "aqua" = Moderationsstimme, leer = Standardstimme
    # (Betreiber-Wahl 2026-09-25).
    stimme: str = ""


# ------------------------------------------------------------------ Hilfsmittel

def _holen(url: str, kopf: dict[str, str] | None = None, zeit: float | None = None) -> str:
    anfrage = urllib.request.Request(url, headers={**KOPF, **(kopf or {})})
    try:
        with urllib.request.urlopen(anfrage, timeout=zeit or ZEIT) as antwort:
            return antwort.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as fehler:
        raise HTTPException(status_code=502,
                            detail=f"Quelle antwortet mit {fehler.code} ({url[:80]})") from fehler
    except (urllib.error.URLError, TimeoutError, OSError) as fehler:
        raise HTTPException(status_code=504,
                            detail=f"Quelle nicht erreichbar ({url[:80]}): {fehler}") from fehler


def _json_holen(url: str) -> Any:
    return json.loads(_holen(url))


# Etiketten statt Text: Agentur-Klammern ("(dpa/afp)"), Autorenzeilen der Feeds
# ("... Von Stephan Ueberbach."), Draht-Meldungszeichen ("EQS-News:") und
# Lesehinweise ("Mehr zum Thema ...") sind kein Sprechtext. Am 2026-09-25 stand
# die Autorenzeile mitten in der Tagesschau-Ansage.
AGENTUR_KLAMMER = re.compile(
    r"\(\s*(?:dpa|afp|rtr|reuters|epd|kna|sid|ots|apa|ap)(?:[\s/,-]*[a-z]+)*\s*\)", re.I)
AUTOR_ZEILE = re.compile(
    r"\s+Von\s+(?:(?:[A-ZÄÖÜ][\w’'\-.]*|und)\s+){1,5}[A-ZÄÖÜ][\w’'\-.]*\.?\s*$")
AUTOR_KURZ = re.compile(r"\s+Von\s+(?:dpa|afp|rtr|reuters|epd|kna|sid|ots)\b[^.]*\.?\s*$", re.I)
DRAHT_ANFANG = re.compile(
    r"^\s*(?:EQS-News|EQS|DGAP-News|DGAP|ots|PR ?Newswire|Business ?Wire|dpa-AFX|AFP)\s*:\s*", re.I)
LESE_HINWEIS = re.compile(
    r"\s+(?:Mehr zum Thema|Lesen Sie auch|Zum Artikel|Weitere Artikel)[^.!?]*[.!?]?\s*$", re.I)


def _saeubern(text: str) -> str:
    """Etiketten und Verweise aus einem Quelltext entfernen (kein Sprechtext)."""
    s = str(text or "")
    s = re.sub(r"[\u200b-\u200d\u2060\ufeff]", "", s)
    s = DRAHT_ANFANG.sub("", s)
    s = AGENTUR_KLAMMER.sub(" ", s)
    for muster in (AUTOR_ZEILE, AUTOR_KURZ, LESE_HINWEIS):
        s = muster.sub(" ", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    s = re.sub(r"\s*[-–—‐‑]\s*(?=[.:])", "", s)
    s = re.sub(r"([:.])\s*[:.]+", r"\1", s)
    return s.strip(" ,;:-")


def _text_von_html(roh: str, grenze: int = 400) -> str:
    """HTML zu Fliesstext: Tags weg, Entities aufloesen, Etiketten weg, kuerzen."""
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", str(roh or ""), flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = _saeubern(s)
    if len(s) > grenze:
        s = s[:grenze].rsplit(" ", 1)[0].rstrip(" ,;:") + "."
    return s


def _feed_adresse(wort: str) -> str:
    """Feed-Adresse aus Kurzname oder direkter Adresse."""
    kurz = (wort or "").strip()
    if not kurz:
        return NACHRICHTEN_FEED
    if kurz.lower() in FEEDS:
        return FEEDS[kurz.lower()]
    if kurz.lower().startswith(("http://", "https://")):
        return kurz
    # Stichwort statt Adresse: bekannten Feed danach durchsuchen
    return NACHRICHTEN_FEED


def _feed_lesen(feed_url: str, anzahl: int = 3, grenze: int = 400) -> list[dict[str, str]]:
    """Die neuesten Eintraege eines RSS- oder Atom-Feeds.

    `grenze` ist die Laenge der Zusammenfassung: 400 Zeichen genuegen fuer eine
    Einzelmeldung, fuer den Ueberblick werden mehr Zeilen gebraucht.
    """
    roh = _holen(feed_url)
    try:
        baum = ET.fromstring(roh)
    except ET.ParseError as fehler:
        raise HTTPException(status_code=502,
                            detail=f"Feed nicht lesbar ({feed_url[:60]}): {fehler}") from fehler

    def ohne_namensraum(tag: str) -> str:
        return tag.rsplit("}", 1)[-1].lower()

    eintraege: list[dict[str, str]] = []
    for knoten in baum.iter():
        if ohne_namensraum(knoten.tag) not in ("item", "entry"):
            continue
        titel = beschreibung = link = ""
        for kind in knoten:
            name = ohne_namensraum(kind.tag)
            if name == "title" and not titel:
                titel = _text_von_html(kind.text or "", 200)
            elif name in ("description", "summary", "content") and not beschreibung:
                beschreibung = _text_von_html(kind.text or "", grenze)
            elif name == "link" and not link:
                link = (kind.get("href") or kind.text or "").strip()
        if titel or beschreibung:
            eintraege.append({"titel": titel, "text": beschreibung, "url": link})
        if len(eintraege) >= anzahl:
            break
    return eintraege


# ------------------------------------------------------------------- Recherchen

def _wetter(ort: str) -> dict[str, str]:
    """Wetter fuer einen Ort (Open-Meteo, ohne Schluessel)."""
    suche = (ort or "").strip()
    if not suche:
        raise HTTPException(status_code=400, detail="Kein Ort angegeben (Feld 'wort').")
    geo = _json_holen("https://geocoding-api.open-meteo.com/v1/search?"
                      + urllib.parse.urlencode({"name": suche, "count": 1, "language": "de",
                                                "format": "json"}))
    treffer = (geo or {}).get("results") or []
    if not treffer:
        raise HTTPException(status_code=404, detail=f"Ort '{suche}' nicht gefunden.")
    o = treffer[0]
    name = str(o.get("name") or suche)
    verwaltung = str(o.get("admin1") or "").strip()
    land = str(o.get("country") or "").strip()
    if verwaltung and name.lower() not in verwaltung.lower():
        anzeige = f"{name} in {verwaltung}"
    else:
        anzeige = name

    daten = _json_holen("https://api.open-meteo.com/v1/forecast?"
                        + urllib.parse.urlencode({
                            "latitude": o["latitude"], "longitude": o["longitude"],
                            "current": "temperature_2m,weather_code,wind_speed_10m",
                            "daily": "temperature_2m_max,temperature_2m_min,"
                                     "precipitation_probability_max",
                            "timezone": "Europe/Berlin", "forecast_days": 2,
                        }))
    jetzt = (daten.get("current") or {})
    tag = (daten.get("daily") or {})
    code = int(jetzt.get("weather_code") or 0)
    lage = WETTER_WORTE.get(code, "wechselhaft")

    def zahl(feld: str, stelle: int = 0) -> str:
        werte = tag.get(feld) or []
        if not werte or werte[0] is None:
            return "?"
        return f"{float(werte[0]):.{stelle}f}"

    teile = [f"In {anzeige} sind es aktuell {float(jetzt.get('temperature_2m') or 0):.0f} Grad, "
             f"dazu {lage}."]
    if tag.get("temperature_2m_max"):
        teile.append(f"Heute werden bis {zahl('temperature_2m_max')} Grad erreicht, "
                     f"in der Nacht kühlt es auf {zahl('temperature_2m_min')} Grad ab.")
    if tag.get("precipitation_probability_max"):
        teile.append(f"Die Regenwahrscheinlichkeit liegt bei "
                     f"{zahl('precipitation_probability_max')} Prozent.")
    if jetzt.get("wind_speed_10m") is not None:
        teile.append(f"Der Wind weht mit "
                     f"{float(jetzt.get('wind_speed_10m') or 0):.0f} Kilometern pro Stunde.")
    text = " ".join(teile)
    return {"titel": f"Wetter {anzeige}", "text": text,
            "url": f"https://open-meteo.com/", "ort": anzeige}


def _nachrichten(wort: str) -> dict[str, str]:
    """Die oberste Meldung eines Nachrichten-Feeds; 'wort' filtert optional."""
    feed = _feed_adresse(wort)
    eintraege = _feed_lesen(feed, anzahl=8)
    stichwort = (wort or "").strip().lower()
    if stichwort and stichwort not in FEEDS and not stichwort.startswith("http"):
        passende = [e for e in eintraege
                    if stichwort in (e["titel"] + " " + e["text"]).lower()]
        eintraege = passende or eintraege
    if not eintraege:
        raise HTTPException(status_code=404, detail="Keine Meldung im Feed gefunden.")
    neueste = eintraege[0]
    titel = neueste["titel"] or "Meldung aus den Nachrichten"
    text = neueste["text"] or titel
    if neueste["titel"] and neueste["titel"].lower() not in text.lower():
        trenn = "" if neueste["titel"].endswith(("?", "!", ".")) else "."
        text = f"{neueste['titel']}{trenn} {text}"
    return {"titel": titel[:90], "text": text, "url": neueste["url"]}


def _rss(wort: str) -> dict[str, str]:
    """Ein beliebiger Feed (Adresse oder Kurzname), oberster Eintrag."""
    adresse = _feed_adresse(wort)
    if adresse == NACHRICHTEN_FEED and (wort or "").strip().lower() not in FEEDS:
        if not (wort or "").strip().startswith("http"):
            raise HTTPException(status_code=400,
                                detail="Fuer einen Feed bitte die Adresse angeben "
                                       f"(oder einen Kurznamen: {', '.join(sorted(FEEDS))}).")
    eintraege = _feed_lesen(adresse, anzahl=3)
    if not eintraege:
        raise HTTPException(status_code=404, detail="Keine Eintraege im Feed.")
    neueste = eintraege[0]
    titel = neueste["titel"] or "Neuer Eintrag im Feed"
    text = neueste["text"] or titel
    if neueste["titel"] and neueste["titel"].lower() not in text.lower():
        trenn = "" if neueste["titel"].endswith(("?", "!", ".")) else "."
        text = f"{neueste['titel']}{trenn} {text}"
    return {"titel": titel[:90], "text": text, "url": neueste["url"]}


def _wiki_titel(thema: str) -> str:
    """Ueber die Wikipedia-Suche den richtigen Artikeltitel finden.

    Noetig, weil die Einleitungs-Schnittstelle den Titel genau braucht:
    "kuenstliche intelligenz" liefert 404, "Kuenstliche Intelligenz" nicht.
    """
    adresse = ("https://de.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": thema, "srlimit": 1,
         "format": "json", "utf8": 1}))
    try:
        daten = _json_holen(adresse)
    except (HTTPException, ValueError, json.JSONDecodeError):
        return ""
    treffer = (((daten.get("query") or {}).get("search")) or [])
    return str(treffer[0].get("title") or "") if treffer else ""


def _wiki_kurzinfo(titel: str) -> dict[str, str]:
    """Einleitung eines Artikels holen (genauer Titel noetig)."""
    adresse = ("https://de.wikipedia.org/api/rest_v1/page/summary/"
               + urllib.parse.quote(titel.replace(" ", "_")))
    daten = _json_holen(adresse)
    # Begriffsklaerungen sind als Hintergrund wertlos ("KI steht fuer: sumerische
    # Gottheit, ..."). Wikipedia kennzeichnet sie mit type=disambiguation.
    if str(daten.get("type") or "").lower() != "standard":
        raise HTTPException(status_code=404,
                            detail=f"Kein Artikel zu '{titel}' (Art: {daten.get('type')}).")
    text = _text_von_html(daten.get("extract") or "", 500)
    if not text:
        raise HTTPException(status_code=404, detail=f"Keinen Artikel zu '{titel}' gefunden.")
    return {"titel": str(daten.get("title") or titel)[:90], "text": text,
            "url": ((daten.get("content_urls") or {}).get("desktop") or {}).get("page", "")}


def _wikipedia(wort: str) -> dict[str, str]:
    """Kurzinfo zu einem Stichwort (Wikipedia-Einleitung)."""
    thema = (wort or "").strip()
    if not thema:
        raise HTTPException(status_code=400, detail="Kein Stichwort angegeben (Feld 'wort').")
    # Mehrere Schreibweisen durchprobieren, dann ueber die Suche den Titel holen.
    kandidaten = [thema, thema[:1].upper() + thema[1:],
                  " ".join(w[:1].upper() + w[1:] for w in thema.split())]
    fehler: HTTPException | None = None
    for versuch in dict.fromkeys(kandidaten):
        try:
            return _wiki_kurzinfo(versuch)
        except HTTPException as grund:
            fehler = grund
    titel = _wiki_titel(thema)
    if titel:
        try:
            return _wiki_kurzinfo(titel)
        except HTTPException as grund:
            fehler = grund
    raise fehler or HTTPException(status_code=404,
                                  detail=f"Keinen Artikel zu '{thema}' gefunden.")


def _quellen_aufloesen(text: str) -> list[tuple[str, str]]:
    """Quellen aus einem Text lesen: "heise und spiegel", "tagesschau, heise" oder "alle".

    Erst wird genau gesucht, dann unscharf (Kurzformen). Das ist wichtig, seit es
    aehnliche Namen gibt: "heise" darf nicht auf "heise-security" fallen.
    """
    roh_text = str(text or "").strip().lower()
    if re.fullmatch(r"(alle|alles|all|komplett|gesamt|saemtliche|sämtliche)", roh_text):
        return list(FEEDS.items())
    roh = re.sub(r"\b(und|sowie|plus|aus|dem|der|die|das|den|vom|alle[nm]?|alles|standard|"
                 r"uebliche|ueblichen|quellen?)\b", " ", roh_text)
    namen = [w for w in re.split(r"[\s,;+/]+\s*", roh) if len(w) > 1]
    if not namen:
        namen = [n.strip() for n in UEBERBLICK_QUELLEN.split(",") if n.strip()]

    gewaehlt: list[tuple[str, str]] = []
    for name in namen:
        treffer = None
        if name in FEEDS:
            treffer = name
        else:
            for kurz in sorted(FEEDS, key=len):   # kurze Namen zuerst
                if len(name) >= 4 and len(kurz) >= 4 \
                        and (kurz.startswith(name[:5]) or name.startswith(kurz[:5])):
                    treffer = kurz
                    break
        if treffer and (treffer, FEEDS[treffer]) not in gewaehlt:
            gewaehlt.append((treffer, FEEDS[treffer]))
    if not gewaehlt:   # nichts erkannt: Standardquellen nehmen
        gewaehlt = [(n.strip(), FEEDS[n.strip()]) for n in UEBERBLICK_QUELLEN.split(",")
                    if n.strip() in FEEDS]
    return gewaehlt


def _themen_aufloesen(text: str) -> list[str]:
    """Themen aus einem Text lesen: "ki, raumfahrt" oder "ki und raumfahrt"."""
    roh = str(text or "").strip() or UEBERBLICK_THEMEN
    if not roh:
        return []
    teile = re.split(r"\s*(?:,|;|\+|\bund\b|\bsowie\b|\bthemen\b|\bthema\b)\s*", roh, flags=re.I)
    sauber: list[str] = []
    for teil in teile:
        t = teil.strip(" .:-–")
        t = re.sub(r"^(zum|zur|den|dem|der|die|das|ein|eine|einen|themen?|thema|ueber|über|zu|"
                   r"nachrichten|news)\s+", "", t, flags=re.I)
        # Alte Zeitangaben ("3 minuten") ignorieren - die Laenge ergibt sich aus
        # dem, was gefunden wird.
        t = re.sub(r"\b\d{1,2}\s*(min|minute|minuten|sek|sekunden)\b", " ", t, flags=re.I)
        t = re.sub(r"\s+", " ", t).strip()
        if len(t) >= 2 and t.lower() not in [s.lower() for s in sauber]:
            sauber.append(t)
    return sauber[:THEMEN_MAX]


def _thema_name(thema: str) -> str:
    """Ein Thema schoen schreiben: "börse" -> "Börse", "ki" -> "KI"."""
    kurz = {"ki": "KI", "ai": "KI", "dax": "DAX", "eu": "EU", "us": "US", "usa": "USA",
            "it": "IT", "gpu": "GPU", "npu": "NPU", "uk": "UK", "nvme": "NVMe",
            "cdu": "CDU", "spd": "SPD", "fdp": "FDP", "afd": "AfD", "bsw": "BSW"}
    teile: list[str] = []
    for w in str(thema or "").split():
        if w.lower() in kurz:
            teile.append(kurz[w.lower()])
        elif len(w) > 3 and w[:1].islower():
            teile.append(w[:1].upper() + w[1:])
        else:
            teile.append(w)
    return " ".join(teile).strip(" .:-")


class _SeitenLeser(HTMLParser):
    """Holt Titel, Beschreibung und Absaetze einer normalen Internetseite."""

    # Bedienhilfen fuer Vorleser stehen im Quelltext, sind aber nicht sichtbar -
    # ungefiltert landet sonst "Pfeil rechts" mitten im Sprechtext.
    VERSTECKT = ("sr-only", "screen-reader", "visually-hidden", "visuallyhidden",
                 "skip-link", "skip-to", "a11y-hidden", "hidden-label")

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.titel = ""
        self.beschreibung = ""
        self.absaetze: list[str] = []
        self._im_titel = False
        self._titel_fertig = False
        self._im_absatz = 0
        self._puffer: list[str] = []
        self._ueberspringen = 0
        self._versteckt_je_tag: dict[str, int] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        daten = {k.lower(): (v or "") for k, v in attrs}
        klasse = (daten.get("class") or "").lower()
        if daten.get("aria-hidden", "").lower() == "true" \
                or any(k in klasse for k in self.VERSTECKT):
            self._versteckt_je_tag[tag] = self._versteckt_je_tag.get(tag, 0) + 1
            self._ueberspringen += 1
        if tag == "title":
            # Nur der Seitentitel zaehlt - Titelelemente in Symbolen (<svg><title>)
            # tragen Beschriftungen wie "Pfeil rechts" und wuerden ihn verlaengern.
            if not self._titel_fertig and not self._ueberspringen:
                self._im_titel = True
        elif tag in ("script", "style", "noscript", "nav", "footer", "header", "form", "svg",
                     "aside", "figure"):
            self._ueberspringen += 1
        elif tag == "meta":
            name = (daten.get("name") or daten.get("property") or "").lower()
            if name in ("description", "og:description", "twitter:description") \
                    and not self.beschreibung:
                self.beschreibung = daten.get("content", "").strip()
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

    def handle_data(self, daten: str) -> None:
        if self._im_titel:
            self.titel += daten
        elif self._im_absatz and not self._ueberspringen:
            self._puffer.append(daten)


def _seite_lesen(url: str, grenze: int = 900) -> dict[str, str]:
    """Eine normale Internetseite lesen: Titel und Anfangstext.

    Kein fremdes Paket: der Text kommt aus den Absaetzen (<p>), ersatzweise aus
    der Beschreibung im Kopf der Seite. Reicht beides nicht, ist die Seite
    unbrauchbar (Consent-Wand, nur Bilder) und wird uebersprungen.
    """
    roh = _holen(url)
    leser = _SeitenLeser()
    try:
        leser.feed(roh)
    except Exception:  # noqa: BLE001 - kaputtes HTML ist kein Grund abzubrechen
        pass
    text = ""
    for absatz in leser.absaetze:
        # Abschnittsnummern wie "1.1" nicht vorlesen.
        absatz = re.sub(r"^\d+(?:\.\d+)*\s*[.):]?\s*", "", absatz).strip()
        if len(absatz) < 40:
            continue
        text = (text + " " + absatz).strip()
        if len(text) >= grenze:
            break
    if len(text) < 80:
        text = _text_von_html(leser.beschreibung or "", grenze)
    if len(text) < 80:
        text = _text_von_html(leser.titel or "", 200)
    # Der Seitentitel traegt oft die Marke ("... | tagesschau.de") - nicht vorlesen.
    titel = re.sub(r"\s+[-–|]\s*(Wikipedia|WIKIPEDIA)\s*$", "", leser.titel)
    titel = re.sub(r"\s*[-–|]\s*[\w.-]+\.(?:de|com|org|net|at|ch|eu|io)\s*$", "", titel)
    titel = re.sub(r"\s+", " ", titel).strip()[:120]
    if titel and titel.lower() not in text.lower()[:80]:
        text = (titel + ". " + text).strip()
    return {"titel": titel or url, "text": _text_von_html(text, grenze), "url": url}


def _bing_ziel(verweis: str) -> str:
    """Bing verpackt Treffer in einen Weiterleitungsverweis (u=a1<base64>)."""
    try:
        roh = urllib.parse.parse_qs(urllib.parse.urlparse(verweis).query).get("u", [""])[0]
        if roh.startswith("a1"):
            s = roh[2:]
            s += "=" * (-len(s) % 4)
            return base64.urlsafe_b64decode(s).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        pass
    return verweis


def _websuche(thema: str, anzahl: int = 4) -> list[dict[str, str]]:
    """Websuche - findet auch normale Internetseiten ohne Feed.

    Reihenfolge: eigene Suchmaschine (SearXNG, `RECHERCHE_SEARX_URL`), dann
    DuckDuckGo, dann Bing. Die oeffentlichen Dienste sperren Rechner ohne
    Anmeldung sehr unterschiedlich (gemessen am 2026-09-21: DuckDuckGo antwortet
    mit 202 ohne Treffer, Mojeek mit Captcha, Ecosia mit 403, Bing mit einer
    Ergebnisliste). Findet keiner etwas, wird die Websuche still uebersprungen -
    Presse, Wikipedia und die Feeds tragen den Beitrag.
    """
    if SEARX_URL:
        treffer = _searx(thema, anzahl)
        if treffer:
            return treffer

    treffer: list[dict[str, str]] = []
    try:
        roh = _holen("https://lite.duckduckgo.com/lite/?" + urllib.parse.urlencode({"q": thema}),
                     kopf=WEB_KOPF)
        verweise = re.findall(r'href="(//duckduckgo\.com/l/\?uddg=[^"]+)"[^>]*'
                              r"class='result-link'>(.*?)</a>", roh, re.S)
        schnipsel = re.findall(r"class='result-snippet'>(.*?)</td>", roh, re.S)
        for i, (verweis, titel) in enumerate(verweise[:anzahl]):
            ziel = ""
            try:
                ziel = urllib.parse.parse_qs(
                    urllib.parse.urlparse(verweis).query).get("uddg", [""])[0]
            except Exception:  # noqa: BLE001
                ziel = ""
            treffer.append({"titel": _text_von_html(titel, 120),
                            "text": _text_von_html(schnipsel[i], 300) if i < len(schnipsel) else "",
                            "url": ziel})
    except HTTPException as fehler:
        print(f"Websuche (DuckDuckGo) '{thema}': {fehler.detail}", flush=True)

    if not treffer:   # zweiter Weg: Bing
        try:
            roh = _holen("https://www.bing.com/search?" + urllib.parse.urlencode(
                {"q": thema, "setlang": "de", "cc": "DE"}), kopf=WEB_KOPF)
            for block in re.findall(r'<li class="b_algo".*?</li>', roh, re.S)[:anzahl]:
                m = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
                if not m:
                    continue
                p = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
                treffer.append({"titel": _text_von_html(m.group(2), 120),
                                "text": _text_von_html(p.group(1), 300) if p else "",
                                "url": _bing_ziel(html.unescape(m.group(1)))})
        except HTTPException as fehler:
            print(f"Websuche (Bing) '{thema}': {fehler.detail}", flush=True)
    return treffer


def _searx(thema: str, anzahl: int = 4) -> list[dict[str, str]]:
    """Websuche ueber eine eigene SearXNG-Instanz (JSON-Schnittstelle)."""
    try:
        adresse = SEARX_URL + "/search?" + urllib.parse.urlencode(
            {"q": thema, "format": "json", "language": "de-DE"})
        daten = _json_holen(adresse)
    except (HTTPException, ValueError, json.JSONDecodeError) as fehler:
        print(f"Websuche (SearXNG) '{thema}': {fehler}", flush=True)
        return []
    treffer: list[dict[str, str]] = []
    for e in (daten.get("results") or [])[:anzahl]:
        ziel = str(e.get("url") or "")
        if not ziel.startswith("http"):
            continue
        treffer.append({"titel": str(e.get("title") or "")[:120],
                        "text": _text_von_html(str(e.get("content") or ""), 300),
                        "url": ziel})
    return treffer


def _google_news(thema: str, anzahl: int = 4) -> list[dict[str, str]]:
    """Presse-Suche je Thema ueber Google News (RSS) - liefert die Quelle mit.

    Draht- und Werbe-Meldungen ("EQS-News: ...", Boersen-Portale) fliegen raus:
    sie klingen im Radio wie Reklame und tragen keinen Nachrichteninhalt.
    """
    adresse = ("https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": thema, "hl": "de", "gl": "DE", "ceid": "DE:de"}))
    try:
        roh = _holen(adresse)
        baum = ET.fromstring(roh)
    except (HTTPException, ET.ParseError) as fehler:
        print(f"Presse-Suche '{thema}' nicht moeglich: {fehler}", flush=True)
        return []
    treffer: list[dict[str, str]] = []
    for knoten in baum.iter():
        if knoten.tag.rsplit("}", 1)[-1] != "item":
            continue
        titel = text = quelle = ""
        for kind in knoten:
            name = kind.tag.rsplit("}", 1)[-1].lower()
            if name == "title" and not titel:
                titel = _text_von_html(kind.text or "", 160)
            elif name in ("description", "summary") and not text:
                text = _text_von_html(kind.text or "", 400)
            elif name == "source" and not quelle:
                quelle = _text_von_html(kind.text or "", 60)
        # Google haengt die Quelle an den Titel ("... - heise online")
        if quelle and titel.lower().endswith(quelle.lower()):
            titel = titel[: len(titel) - len(quelle)].rstrip(" -–")
        # Draht-/Werbe-Portale und Wire-Ueberschriften ueberspringen (2026-09-25:
        # "Warren Wise entschluesselt Qiagens DNA" von boerse-EQS landete als
        # erste Schlagzeile im Boersen-Ueberblick).
        if any(w in quelle.lower() for w in PRESSE_VERBOTEN):
            continue
        if titel.lower().startswith(PRESSE_VERBOTEN_TITEL):
            continue
        # Die Beschreibung wiederholt den Titel - der Rest ist der Anfangstext.
        for abschneiden in (titel, quelle):
            if abschneiden and text.lower().startswith(abschneiden.lower()):
                text = text[len(abschneiden):].strip(" .-–")
        if text.lower().startswith(titel.lower()):
            text = text[len(titel):].strip(" .-–")
        if titel or text:
            treffer.append({"titel": titel, "text": text, "quelle": quelle})
        if len(treffer) >= anzahl:
            break
    return treffer


def _feeds_holen(quellen: list[tuple[str, str]]) -> tuple[list[tuple[str, list[dict[str, str]]]],
                                                        list[str]]:
    """Einmal alle genannten Quellen lesen (Wetter ueber Open-Meteo).

    Gibt die gelesenen Bloecke und die Namen der Quellen zurueck, die NICHT
    erreichbar waren (das ist etwas anderes als "hatte nichts zum Thema").
    """
    bloecke: list[tuple[str, list[dict[str, str]]]] = []
    fehlend: list[str] = []
    for name, adresse in quellen:
        if name == "wetter":
            try:
                w = _wetter(UEBERBLICK_WETTER_ORT)
                bloecke.append((name, [{"titel": "Wetter", "text": w["text"],
                                        "url": w.get("url", "")}]))
            except HTTPException as fehler:
                print(f"Ueberblick: Wetter nicht lesbar: {fehler.detail}", flush=True)
                fehlend.append(name)
            continue
        try:
            eintraege = _feed_lesen(adresse, anzahl=10, grenze=700)
        except HTTPException as fehler:   # eine Quelle darf ausfallen
            print(f"Ueberblick: Quelle {name} nicht lesbar: {fehler.detail}", flush=True)
            fehlend.append(name)
            continue
        if eintraege:
            bloecke.append((name, eintraege))
        else:
            fehlend.append(name)
    return bloecke, fehlend


def _passt_zum_thema(eintrag: dict[str, str], thema: str) -> bool:
    """Steht das Thema in Titel oder Text der Meldung?"""
    woerter = [w for w in re.split(r"[^a-z0-9]+", thema.lower()) if len(w) > 2]
    if not woerter:
        return False
    heu = (eintrag.get("titel", "") + " " + eintrag.get("text", "")).lower()
    return sum(1 for w in woerter if w in heu) >= max(1, len(woerter) - 1)


def _stueck(titel: str, text: str, grenze: int = 300) -> str:
    """Ein Meldungsstueck fuer den Sprechtext: "Titel. Anfang" - ohne Etikett.

    Geschnitten wird am liebsten am Satzende: ein mitten im Satz abgebrochenes
    Stueck klang im Radio wie ein Fehler. Die Quellenangabe kommt als eigener
    Satz dahinter (`_meldet`), nicht als "Quelle:" davor.
    """
    titel = _saeubern(titel).strip(" .;:-")
    anfang = _saeubern(text).strip()
    if titel and titel.lower() not in anfang.lower():
        trenn = "" if titel.endswith(("?", "!", ".")) else "."
        anfang = (titel + trenn + " " + anfang).strip()
    if len(anfang) > grenze:
        teil = anfang[:grenze]
        schnitt = max(teil.rfind(". "), teil.rfind("! "), teil.rfind("? "))
        if schnitt < grenze * 0.4:
            schnitt = teil.rfind(" ")
        anfang = (teil[: schnitt + 1] if schnitt > 0 else teil).strip(" ,;:-")
    if anfang and not anfang.endswith((".", "!", "?")):
        anfang += "."
    return anfang


def _meldet(name: str) -> str:
    """Quellenangabe als Satz fuer den Sprechtext ("Das meldet die Tagesschau.")."""
    name = _saeubern(name).strip(" .,;:-")
    return f"Das meldet {name}." if name else ""


def _ueberblick(themen_text: str = "", quellen_text: str = "") -> dict[str, Any]:  # noqa: C901
    """Themen sammeln: Websuche, Presse-Suche und die Feeds der Quelle.

    Eine feste Laenge gibt es nicht mehr: der Beitrag waechst mit dem, was zu den
    Themen gefunden wird (Sicherheitsgrenze: RECHERCHE_UEBERBLICK_MAX_ZEICHEN bzw.
    die Laengengrenze einer Ansage). Ohne Themen kommen die neuesten Meldungen der
    genannten Quellen.
    """
    themen = _themen_aufloesen(themen_text)
    if not quellen_text.strip():
        quellen_text = UEBERBLICK_QUELLEN_THEMEN if themen else UEBERBLICK_QUELLEN
    quellen = _quellen_aufloesen(quellen_text)
    if not quellen and not themen:
        raise HTTPException(status_code=400,
                            detail="Keine Quelle. Bekannt: " + ", ".join(sorted(FEEDS)))
    bloecke, nicht_erreichbar = _feeds_holen(quellen)
    grenze = UEBERBLICK_MAX_ZEICHEN or meldungen.MAX_ZEICHEN
    grenze = min(grenze, meldungen.MAX_ZEICHEN)

    teile: list[str] = []
    laenge = 0
    genutzt: list[str] = []          # Quellen, die wirklich etwas beigetragen haben
    gelesen: list[str] = []          # Adressen, die der Bot geoeffnet hat
    presse_anzahl = 0                # Meldungen aus der Presse-Suche
    web_anzahl = 0                   # Meldungen aus der Websuche bzw. von Seiten
    wiki_anzahl = 0                  # Hintergrund aus Wikipedia

    def anhaengen(stueck: str) -> None:
        nonlocal laenge
        if stueck:
            teile.append(stueck)
            laenge += len(stueck)

    if themen:
        for thema in themen:
            if laenge >= grenze:
                break
            stuecke: list[tuple[str, str]] = []   # (Satzstueck, Quellenangabe)
            presse_hier = web_hier = wiki_hier = feed_hier = 0
            seite_gelesen = False        # je Thema hoechstens eine Seite oeffnen
            # Plaetze je Thema: die Presse darf nicht alles belegen - fuer Netz und
            # Feed bleibt je ein Platz reserviert. Sonst liefert ein Thema nur
            # Schlagzeilen (die Presse-Treffer tragen keinen Fliesstext).
            reserve = ((1 if THEMA_WIKI > 0 else 0) + (1 if THEMA_WEB > 0 else 0)
                       + (1 if THEMA_FEED > 0 else 0))
            presse_max = min(THEMA_PRESSE, max(1, THEMA_MELDUNGEN - reserve))

            # 1) Presse-Suche: was schreiben die Zeitungen dazu?
            if PRESSE_SUCHE:
                for t in _google_news(thema, 4):
                    if presse_hier >= presse_max or len(stuecke) >= THEMA_MELDUNGEN:
                        break
                    # Google liefert in der Beschreibung oft eine Mischung aus mehreren
                    # Schlagzeilen. Fuer den Sprechtext ist die Ueberschrift allein
                    # sauberer - Inhalt kommt aus Seite und Feeds.
                    stuecke.append((_stueck(t.get("titel", ""), "", 200),
                                    _quellenname(t.get("quelle"))))
                    presse_hier += 1

            # 2) Wikipedia: auf Wunsch nur noch, wenn RECHERCHE_THEMA_WIKI=1
            #    (Standard 0 - keine Lexikon-Einleitungen im Nachrichten-Ueberblick).
            if THEMA_WIKI and wiki_hier < 1 and len(stuecke) < THEMA_MELDUNGEN:
                wiki_daten = None
                for versuch in (thema, thema[:1].upper() + thema[1:]):
                    try:
                        wiki_daten = _wikipedia(versuch)
                        break
                    except HTTPException as fehler:
                        print(f"Wikipedia '{versuch}': {fehler.detail}", flush=True)
                if wiki_daten:
                    stuecke.append((_stueck(wiki_daten.get("titel", ""),
                                            wiki_daten.get("text", ""), 400), "Wikipedia"))
                    wiki_hier = 1

            # 3) Websuche: findet auch Seiten ohne Feed - und liest die erste.
            #    Nur Seiten bekannter Nachrichten-Anbieter (Werbeseiten aussen vor).
            if WEBSUCHE and web_hier < THEMA_WEB and len(stuecke) < THEMA_MELDUNGEN:
                for t in _websuche(thema, 4):
                    if web_hier >= THEMA_WEB or len(stuecke) >= THEMA_MELDUNGEN:
                        break
                    ziel = t.get("url") or ""
                    if not ziel or not _seite_vertraut(ziel):
                        continue
                    # Die erste gefundene Adresse wirklich lesen - "normale Internetseite".
                    if SEITE_LESEN and not seite_gelesen:
                        try:
                            seite = _seite_lesen(ziel)
                        except HTTPException as fehler:
                            print(f"Seite {ziel[:60]} nicht lesbar: {fehler.detail}", flush=True)
                            seite = {}
                        if seite.get("text") and not _seite_brauchbar(seite):
                            continue      # Werbeseite (Kurse, Abos) - naechsten Treffer nehmen
                        if _seite_brauchbar(seite):
                            gelesen.append(ziel)
                            seite_gelesen = True
                            stuecke.append((_stueck(seite.get("titel", ""),
                                                    seite.get("text", ""), 500),
                                            _seitenname(ziel)))
                            web_hier += 1
                            continue
                    stuecke.append((_stueck(t.get("titel", ""), t.get("text", "")),
                                    _seitenname(ziel)))
                    web_hier += 1

            # 4) Die eigenen Feeds: passende Meldungen zum Thema.
            for name, eintraege in bloecke:
                if feed_hier >= THEMA_FEED or len(stuecke) >= THEMA_MELDUNGEN:
                    break
                passend = [e for e in eintraege if _passt_zum_thema(e, thema)]
                if not passend:
                    continue
                e = passend[0]
                stuecke.append((_stueck(e["titel"], e["text"], 300), _kurzname(name)))
                feed_hier += 1
                if name not in genutzt:
                    genutzt.append(name)

            # Ein Thema ohne Fund wird nicht angekuendigt (sonst eine leere Ansage).
            if not stuecke:
                continue
            anhaengen(f"Zum Thema {_thema_name(thema)}.")
            gesagte_quelle = ""
            for stueck, quelle in stuecke:
                anhaengen(stueck)
                if quelle and quelle != gesagte_quelle:
                    anhaengen(_meldet(quelle))
                    gesagte_quelle = quelle
                if laenge >= grenze:
                    break
            presse_anzahl += presse_hier
            web_anzahl += web_hier
            wiki_anzahl += wiki_hier
    else:
        # Ohne Themen: je genannter Quelle die neueste Meldung (eine Runde).
        for name, eintraege in bloecke:
            if laenge >= grenze:
                break
            if not eintraege:
                continue
            anhaengen(QUELLEN_ANSPRACHE.get(name, f"Aus {name}."))
            e = eintraege[0]
            anhaengen(_stueck(e["titel"], e["text"], 400))
            if name not in genutzt:
                genutzt.append(name)

    if not teile:
        raise HTTPException(status_code=504, detail="Zu diesen Themen wurde nichts gefunden.")

    # Konfigurierte Seiten immer mitlesen (Ergaenzung, kein Ersatz).
    for adresse in WEBSEITEN:
        if laenge >= grenze:
            break
        try:
            seite = _seite_lesen(adresse)
        except HTTPException as fehler:
            print(f"Webseite {adresse[:60]} nicht lesbar: {fehler.detail}", flush=True)
            continue
        if len(seite.get("text", "")) < 120:
            continue
        gelesen.append(adresse)
        anhaengen(_stueck(seite.get("titel", ""), seite.get("text", ""), 500))
        anhaengen(_meldet(_seitenname(adresse)))

    fehlend = nicht_erreichbar
    text = re.sub(r"\s+", " ", " ".join(t for t in teile if t)).strip()
    text = meldungen.kuerzen(text, grenze)
    return {"titel": "Überblick über die Nachrichtenlage", "text": text, "url": "",
            "quellen": genutzt, "themen": themen,
            "minuten": round(len(text) / ZEICHEN_JE_MINUTE, 1),
            "presse": presse_anzahl, "web": web_anzahl, "wiki": wiki_anzahl,
            "gelesen": gelesen, "ausgefallen": fehlend}


# Presse-Namen aus der Google-Suche sprechbar machen ("Das meldet ...").
PRESSE_NAMEN: dict[str, str] = {
    "sz": "die Süddeutsche Zeitung", "süddeutsche": "die Süddeutsche Zeitung",
    "sueddeutsche": "die Süddeutsche Zeitung",
    "süddeutsche zeitung": "die Süddeutsche Zeitung",
    "sueddeutsche zeitung": "die Süddeutsche Zeitung",
    "faz": "die F.A.Z.", "frankfurter allgemeine": "die F.A.Z.",
    "frankfurter allgemeine zeitung": "die F.A.Z.",
    "zeit": "die Zeit", "die zeit": "die Zeit", "zeit online": "die Zeit",
    "spiegel": "der Spiegel", "der spiegel": "der Spiegel", "spiegel online": "der Spiegel",
    "manager magazin": "das Manager Magazin", "handelsblatt": "das Handelsblatt",
    "welt": "die Welt", "die welt": "die Welt", "welt online": "die Welt",
    "n-tv": "n-tv", "ntv": "n-tv", "t-online": "t-online",
    "tagesschau": "die Tagesschau", "tagesschau.de": "die Tagesschau",
    "business insider": "Business Insider", "capital": "Capital", "focus": "Focus",
    "stern": "der stern", "der stern": "der stern", "taz": "die taz",
    "wirtschaftswoche": "die WirtschaftsWoche", "wiwo": "die WirtschaftsWoche",
    "deutschlandfunk": "der Deutschlandfunk", "reuters": "Reuters", "dpa": "die dpa",
    "heise": "Heise", "heise online": "Heise", "heise.de": "Heise",
}

# Werbe- und Draht-Portale, die nicht in den Nachrichten-Ueberblick gehoeren.
PRESSE_VERBOTEN = ("eqs", "dgap", "boerse", "finanzen.net", "wallstreet", "ariva",
                   "aktiencheck", "tradegate", "godmode", "der aktionär", "ots")
PRESSE_VERBOTEN_TITEL = ("eqs-news", "eqs:", "dgap-news", "dgap:", "ots:",
                         "original-research", "research:", "ad-hoc", "adhoc",
                         "pressemitteilung", "unternehmensmitteilung")


def _quellenname(name: str) -> str:
    """Den Namen eines Presse-Erzeugers sprechbar machen.

    Google News liefert hier mal "DIE ZEIT", mal "SZ" oder "heise online".
    Bekannte Namen bekommen ihren Artikel ("Das meldet die Zeit."), kurze oder
    kryptische Angaben fallen weg - dann steht nur die Schlagzeile im Beitrag.
    """
    s = re.sub(r"\s+", " ", str(name or "")).strip(" .-–")
    if s.lower() in PRESSE_NAMEN:
        return PRESSE_NAMEN[s.lower()]
    for alt in (" online", ".de", ".com"):
        if s.lower().endswith(alt):
            s = s[: -len(alt)]
    if s.lower() in PRESSE_NAMEN:
        return PRESSE_NAMEN[s.lower()]
    if len(s) < 3 or re.fullmatch(r"[A-Za-z]{2,4}\.?", s):
        return ""          # ohne Namen lieber nur die Schlagzeile sprechen
    return s[:28]


def _seitenname(url: str) -> str:
    """Ein sprechbarer Name fuer eine Adresse: \"heise.de\" -> \"Heise\"."""
    try:
        wirt = urllib.parse.urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return ""
    wirt = re.sub(r"^www\.", "", wirt)
    wirt = wirt.split(":")[0]
    teile = [t for t in wirt.split(".") if t]
    # "de.wikipedia.org" -> "wikipedia", "heise.de" -> "heise"
    haupt = teile[-2] if len(teile) >= 3 else (teile[0] if teile else "")
    namen = {"sz": "die Süddeutsche Zeitung", "sueddeutsche": "die Süddeutsche Zeitung",
             "faz": "die F.A.Z.", "n-tv": "n-tv", "ntv": "n-tv", "t3n": "t3n",
             "mdr": "der MDR", "swr": "der SWR", "br": "der BR", "ard": "die ARD",
             "zdf": "das ZDF", "wdr": "der WDR", "ndr": "der NDR",
             "rnd": "das Redaktionsnetzwerk Deutschland", "taz": "die taz",
             "tagesschau": "die Tagesschau",
             "handelsblatt": "das Handelsblatt", "manager-magazin": "das Manager Magazin",
             "wiwo": "die WirtschaftsWoche", "capital": "Capital", "focus": "Focus",
             "stern": "der stern", "businessinsider": "Business Insider",
             "t-online": "t-online", "sportschau": "die Sportschau", "orf": "der ORF",
             "heise": "Heise", "golem": "Golem", "spiegel": "der Spiegel",
             "zeit": "die Zeit", "welt": "die Welt", "tagesspiegel": "der Tagesspiegel",
             "netzpolitik": "Netzpolitik", "computerbase": "ComputerBase",
             "scinexx": "Scinexx", "ingenieur": "der Ingenieur", "deutschlandfunk": "der Deutschlandfunk",
             "wikipedia": "Wikipedia", "github": "GitHub", "bund": "Der Bund",
             "bmftr": "das Bundesministerium", "europarl": "das Europäische Parlament"}
    return namen.get(haupt, haupt.capitalize() if haupt else "")


def recherchieren(art: str, wort: str, quellen: str = "",
                  themen: str = "") -> dict[str, Any]:
    """Holt die Daten und gibt Titel, Text und Quelle zurueck."""
    gewaehlt = (art or "wetter").lower()
    if gewaehlt == "wetter":
        return _wetter(wort)
    if gewaehlt in ("nachrichten", "news"):
        return _nachrichten(wort)
    if gewaehlt in ("rss", "feed"):
        return _rss(wort)
    if gewaehlt in ("wikipedia", "info", "kurzinfo"):
        return _wikipedia(wort)
    if gewaehlt in ("ueberblick", "ueberblick!", "overview", "rundschau", "rundumblick",
                    "themen", "themenueberblick"):
        return _ueberblick(themen or wort, quellen)
    raise HTTPException(status_code=400,
                        detail="art muss wetter, nachrichten, rss, wikipedia oder ueberblick sein.")


# -------------------------------------------------------------------- Endpunkt

@router.post("/recherche")
def recherche(anfrage: Recherche,
              x_meldung_schluessel: str | None = Header(default=None)) -> dict[str, Any]:
    """Holt Wetter/Nachrichten/Feed/Kurzinfo, legt eine Meldung ab und sagt sie an.

    `ansagen: false` legt die Meldung nur ab (der Bot kann sie spaeter im Telegram
    vorlegen), `trocken: true` erzeugt nur das Audio der Ansage.
    """
    meldungen._pruefen(x_meldung_schluessel)  # noqa: SLF001 - gleicher Dienst
    ergebnis = recherchieren(anfrage.art, anfrage.wort, anfrage.quellen, anfrage.themen)

    art = {"feed": "rss", "news": "nachrichten", "info": "wikipedia",
           "kurzinfo": "wikipedia", "overview": "ueberblick",
           "rundschau": "ueberblick", "rundumblick": "ueberblick",
           "themen": "ueberblick", "themenueberblick": "ueberblick"}.get(
               anfrage.art.lower().strip("!"), anfrage.art.lower().strip("!"))
    eintrag = meldungen.aufnehmen(quelle=anfrage.quelle or anfrage.art, art=art,
                                  titel=ergebnis.get("titel", ""), text=ergebnis.get("text", ""),
                                  wichtig=bool(anfrage.wichtig), von="recherche",
                                  url=ergebnis.get("url", ""))

    antwort: dict[str, Any] = {
        "ok": True, "id": eintrag["id"], "art": eintrag["art"], "titel": eintrag["titel"],
        "text": eintrag["text"], "quelle": ergebnis.get("url", ""),
        "sprechtext": meldungen.moderationstext(eintrag), "gesagt": False,
        "offen": meldungen.offene_zahl(),
    }
    if ergebnis.get("quellen") or ergebnis.get("themen"):
        antwort["quellen"] = ergebnis.get("quellen") or []
        antwort["themen"] = ergebnis.get("themen") or []
        antwort["minuten"] = ergebnis.get("minuten")
        antwort["presse"] = ergebnis.get("presse", 0)
        antwort["web"] = ergebnis.get("web", 0)
        antwort["wiki"] = ergebnis.get("wiki", 0)
        antwort["gelesen"] = ergebnis.get("gelesen") or []
        antwort["ausgefallen"] = ergebnis.get("ausgefallen") or []
    if anfrage.ansagen:
        ansage = meldungen.ansage_machen(eintrag["id"], trocken=anfrage.trocken,
                                        stimme=anfrage.stimme, speed=1.0)
        antwort["gesagt"] = not anfrage.trocken
        antwort["dauer_sekunden"] = ansage.get("dauer_sekunden")
        antwort["gesprochen"] = ansage.get("gesprochen") or antwort["sprechtext"]
        if art == "ueberblick":
            dauer = ansage.get("dauer_sekunden") or 0
            themen = ergebnis.get("themen") or []
            quellen = ergebnis.get("quellen") or []
            wo = ("Themen " + ", ".join(themen)) if themen else ("Quellen " + ", ".join(quellen[:6]))
            extra = []
            if ergebnis.get("presse"):
                extra.append(f"{ergebnis['presse']} aus der Presse")
            if ergebnis.get("wiki"):
                extra.append("mit Hintergrund")
            if ergebnis.get("web"):
                extra.append(f"{ergebnis['web']} aus dem Netz")
            antwort["antwort"] = (f"\U0001f399\ufe0f Überblick "
                                  f"{'gesagt' if antwort['gesagt'] else 'vorbereitet'} "
                                  f"({dauer / 60:.1f} Min, {wo}"
                                  + ((", " + ", ".join(extra)) if extra else "") + ")")
        else:
            antwort["antwort"] = ansage.get("antwort") or (
                f"\U0001f399\ufe0f {eintrag['titel']}: {antwort['gesprochen'][:160]}")
    else:
        antwort["antwort"] = (f"\U0001f4dd Abgelegt: {eintrag['titel']} "
                              f"({len(eintrag['text'])} Zeichen)")
    return antwort


@router.get("/recherche/feeds")
def recherche_feeds() -> dict[str, Any]:
    """Die bekannten Quellen, Arten und Einstellungen des Ueberblicks."""
    return {"feeds": FEEDS, "nachrichten": NACHRICHTEN_FEED,
            "arten": ["wetter", "nachrichten", "rss", "wikipedia", "ueberblick"],
            "ueberblick": {"quellen": UEBERBLICK_QUELLEN,
                            "quellen_mit_themen": UEBERBLICK_QUELLEN_THEMEN,
                            "themen": UEBERBLICK_THEMEN,
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
