"""Katalog des Musikarchivs: unscharfe Suche, Genre- und Stimmungsvorschlaege.

Der Katalog wird einmal aus der AzuraCast-Schnittstelle geholt und als JSON
abgelegt. Damit findet der Bot auch Titel, die falsch oder undeutlich gesagt
wurden (Tippfehler, fehlende Buchstaben, vertauschte Reihenfolge), und er kann
Vorschlaege aus einer Richtung machen ("was aus Rock", "etwas Ruhiges", "90er").

Endpunkte:
    GET  /katalog/status          Anzahl und Stand
    POST /katalog/aktualisieren   Katalog neu holen (dauert ~45 s)
    GET  /suche?q=...             unscharfe Suche
    GET  /genre?wort=...          Vorschlaege aus einer Richtung
    GET  /genre/liste             bekannte Richtungen und Stichwoerter
"""

from __future__ import annotations

import difflib
import json
import os
import random
import re
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

AZ_URL = os.environ.get("AZ_URL", "http://192.168.178.33").rstrip("/")
AZ_KEY = os.environ.get("AZ_KEY", "")
AZ_STATION_ID = os.environ.get("AZ_STATION_ID", "1")  # Sendernummer in AzuraCast
KATALOG_DIR = Path(os.environ.get("KATALOG_DIR", "/daten"))
KATALOG_DATEI = KATALOG_DIR / "katalog.json"

router = APIRouter()

# ------------------------------------------------------------------ Normalisieren

UMLAUTE = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
NICHT_WORT = re.compile(r"[^a-z0-9]+")
JAHR = re.compile(r"(19[5-9][0-9]|20[0-3][0-9])")
GENRE_TRENNER = re.compile(r"[|;/,]")

# Pfade, die der Bot nie vorschlagen oder spielen darf:
#   moderation/ = Ansagen des Moderators
#   _Archiv/    = Live- und Bootleg-Mitschnitte (2026-09-20 dorthin verschoben)
GESPERRTE_PFADE = ("moderation/", "_archiv/")


def gesperrt(pfad: Any) -> bool:
    return str(pfad or "").lower().startswith(GESPERRTE_PFADE)


def normalisieren(text: str) -> str:
    s = str(text or "").lower()
    for a, b in UMLAUTE.items():
        s = s.replace(a, b)
    return NICHT_WORT.sub(" ", s).strip()


def maske(text: str) -> int:
    """Bitmaske der Buchstaben a-z - sehr schneller Vorfilter."""
    m = 0
    for c in text:
        if "a" <= c <= "z":
            m |= 1 << (ord(c) - 97)
    return m


def jahr_aus_album(album: str) -> int | None:
    treffer = JAHR.findall(str(album or ""))
    return int(treffer[0]) if len(treffer) == 1 else None


def eintrag_bauen(r: dict[str, Any]) -> dict[str, Any]:
    artist = (r.get("artist") or "").strip()
    titel = (r.get("title") or "").strip()
    album = (r.get("album") or "").strip()
    genre = (r.get("genre") or "").strip()
    pfad = (r.get("path") or "").strip()
    heu = normalisieren(" ".join([artist, titel, album, pfad]))
    return {
        "id": r.get("id"),
        "uid": r.get("unique_id"),
        "song": r.get("song_id"),
        # Namen wie im AzuraCast-Archiv, damit der Bot dieselben Felder findet
        # (Abspielplan rechnet mit unique_id/song_id).
        "unique_id": r.get("unique_id"),
        "song_id": r.get("song_id"),
        "artist": artist,
        "title": titel,
        "album": album,
        "genre": genre,
        "length": r.get("length") or 0,
        "length_text": r.get("length_text") or "",
        "path": pfad,
        "playlists": [p.get("id") if isinstance(p, dict) else p for p in (r.get("playlists") or [])],
        "jahr": jahr_aus_album(album),
        "heu": heu,
        "kurz": normalisieren(artist + " " + titel + " " + album),
        # Nur Interpret und Titel - Grundlage der Kernpruefung in der Suche.
        "kern": normalisieren(artist + " " + titel),
        "kern_woerter": sorted(set(normalisieren(artist + " " + titel).split())),
        "woerter": sorted(set(heu.split())),
        "maske": maske(normalisieren(artist + " " + titel + " " + album)),
        "maske_all": maske(heu),
    }


# ------------------------------------------------------------------ Katalog laden

_sperre = threading.Lock()
_katalog: dict[str, Any] = {"stand": None, "anzahl": 0, "eintraege": []}
_genre_index: dict[str, list[int]] = {}
_jahr_index: dict[int, list[int]] = {}
_dauer: dict[str, Any] = {"letzte_dauer_s": None}


def _indizes_bauen() -> None:
    global _genre_index, _jahr_index
    genre: dict[str, list[int]] = {}
    jahre: dict[int, list[int]] = {}
    for i, e in enumerate(_katalog.get("eintraege", [])):
        if "maske" not in e:  # aeltere Katalogdatei
            e["maske"] = maske(normalisieren(f'{e["artist"]} {e["title"]} {e["album"]}'))
            e["maske_all"] = maske(e["heu"])
            e.setdefault("woerter", sorted(set(e["heu"].split())))
        e.setdefault("kurz", normalisieren(f'{e["artist"]} {e["title"]} {e["album"]}'))
        for teil in GENRE_TRENNER.split(e.get("genre") or ""):
            t = normalisieren(teil)
            if t:
                genre.setdefault(t, []).append(i)
        j = e.get("jahr")
        if j:
            jahre.setdefault(j, []).append(i)
    _genre_index = genre
    _jahr_index = jahre


def katalog_laden() -> None:
    global _katalog
    if not KATALOG_DATEI.is_file():
        return
    daten = json.loads(KATALOG_DATEI.read_text(encoding="utf-8"))
    with _sperre:
        _katalog = daten
        _indizes_bauen()


def katalog_holen() -> dict[str, Any]:
    if not AZ_KEY:
        raise HTTPException(status_code=500, detail="AZ_KEY fehlt")
    alle: list[dict[str, Any]] = []
    seite = 1
    while True:
        url = f"{AZ_URL}/api/station/{AZ_STATION_ID}/files?rowCount=1000&page={seite}"
        anfrage = urllib.request.Request(url, headers={"X-API-Key": AZ_KEY})
        with urllib.request.urlopen(anfrage, timeout=60) as antwort:
            daten = json.loads(antwort.read().decode("utf-8"))
        zeilen = daten.get("rows") or []
        if not zeilen:
            break
        alle.extend(
            eintrag_bauen(r) for r in zeilen if not gesperrt(r.get("path"))
        )
        if seite >= int(daten.get("total_pages") or 1):
            break
        seite += 1
    return {"stand": time.strftime("%Y-%m-%dT%H:%M:%S"), "anzahl": len(alle), "eintraege": alle}


def katalog_aktualisieren() -> dict[str, Any]:
    global _katalog
    start = time.time()
    neu = katalog_holen()
    KATALOG_DIR.mkdir(parents=True, exist_ok=True)
    KATALOG_DATEI.write_text(json.dumps(neu, ensure_ascii=False), encoding="utf-8")
    with _sperre:
        _katalog = neu
        _indizes_bauen()
    _dauer["letzte_dauer_s"] = round(time.time() - start, 1)
    return neu


def _katalog_bereit() -> bool:
    return bool(_katalog.get("eintraege"))


@router.get("/katalog/status")
def katalog_status() -> dict[str, Any]:
    return {
        "anzahl": _katalog.get("anzahl", 0),
        "stand": _katalog.get("stand"),
        "genres": len(_genre_index),
        "jahre": len(_jahr_index),
        "letzte_dauer_s": _dauer["letzte_dauer_s"],
    }


@router.post("/katalog/aktualisieren")
def katalog_neu() -> dict[str, Any]:
    neu = katalog_aktualisieren()
    return {"ok": True, "anzahl": neu["anzahl"], "stand": neu["stand"],
            "dauer_s": _dauer["letzte_dauer_s"]}


# ------------------------------------------------------------------ Unscharfe Suche

def _aehnlichkeit(wort: str, heu: str, heu_woerter: list[str]) -> float:
    # Ganzwort pruefen: "tim" darf nicht in "everytim e" anschlagen.
    if f" {wort} " in f" {heu} ":
        return 1.0
    best = 0.0
    anfang = wort[0]
    for k in heu_woerter:
        # nur Woerter mit gleichem Anfang oder aehnlicher Laenge pruefen
        if k[0] != anfang and abs(len(k) - len(wort)) > 3:
            continue
        r = difflib.SequenceMatcher(None, wort, k).ratio()
        if k.startswith(wort[:2]) and r > best:
            r = min(1.0, r + 0.08)
        if r > best:
            best = r
    return best


def _kandidaten(woerter: list[str]) -> tuple[list[int], str]:
    """Vorfilter ueber Buchstaben-Bitmasken."""
    alle = _katalog.get("eintraege", [])
    masken = [maske(w) for w in woerter]
    kurz = [i for i, e in enumerate(alle) if all((e["maske"] & m) == m for m in masken)]
    if len(kurz) >= 5:
        return kurz, "kurz"
    weit = [i for i, e in enumerate(alle) if all((e["maske_all"] & m) == m for m in masken)]
    if len(weit) >= 5:
        return weit, "weit"
    laengste = max(masken, key=lambda m: bin(m).count("1"))
    einzeln = [i for i, e in enumerate(alle) if (e["maske_all"] & laengste) == laengste]
    return (einzeln or weit or kurz), "einzeln"


@router.get("/suche")
def suche(q: str = Query(..., min_length=1), anzahl: int = 8,
          min_punkte: int = 20) -> dict[str, Any]:
    if not _katalog_bereit():
        raise HTTPException(status_code=503, detail="Katalog ist noch nicht geladen")
    ganz = normalisieren(q)
    woerter = [w for w in ganz.split() if len(w) > 1] or [ganz]
    if not ganz:
        return {"suchtext": q, "treffer": [], "geprueft": 0}

    kandidaten, stufe = _kandidaten(woerter)
    # Vorauswahl nach guenstigem Merkmal (ganzes Wort oder Wortanfang enthalten)
    if len(kandidaten) > 4000:
        def guenstig(i: int) -> int:
            kurz = _katalog["eintraege"][i]["kurz"]
            woerter_kurz = kurz.split()
            return sum(1 for w in woerter
                       if w in kurz or any(k.startswith(w[:3]) for k in woerter_kurz))

        kandidaten = sorted(kandidaten, key=guenstig, reverse=True)[:4000]

    ergebnisse: list[dict[str, Any]] = []
    for i in kandidaten:
        e = _katalog["eintraege"][i]
        teil = [_aehnlichkeit(w, e["heu"], e["woerter"]) for w in woerter]
        # Laengengewichtet: ein sicheres langes Wort ("rammstein") soll ein
        # verhoertes kurzes ("Ben Tim") ueberstimmen.
        gewicht = sum(len(w) for w in woerter) or 1
        schnitt = sum(t * len(w) for t, w in zip(teil, woerter)) / gewicht
        gesamt = difflib.SequenceMatcher(None, ganz, e["kurz"]).ratio()
        # Kernpruefung: irgendein Suchwort muss in Interpret oder Titel sitzen.
        # Ohne sie ziehen zufaellige Anklænge aus Album- und Pfadnamen Treffer nach
        # oben (verhoerte Sprachnachricht "Ben Tim Rammstein" landete bei 50 Cent).
        kern = e.get("kern") or normalisieren(e["artist"] + " " + e["title"])
        kern_woerter = e.get("kern_woerter") or kern.split()
        best_kern = 0.0
        for w in woerter:
            if f" {w} " in f" {kern} ":
                best_kern = 1.0
                break
            for k in kern_woerter:
                if k[0] != w[0] and abs(len(k) - len(w)) > 3:
                    continue
                r = difflib.SequenceMatcher(None, w, k).ratio()
                if k.startswith(w[:2]):
                    r = min(1.0, r + 0.08)
                if r > best_kern:
                    best_kern = r
        if best_kern < 0.72:
            continue
        punkt = schnitt * 70 + gesamt * 30 + best_kern * 20
        artist = normalisieren(e["artist"])
        if artist and ganz in artist:
            punkt += 15
        pfad = e["path"].lower()
        if not re.search(r"\.(mp3|m4a|aac|ogg|opus|flac)$", pfad):
            punkt -= 10
        if pfad.startswith("moderation/"):
            punkt -= 60
        if 0 < (e.get("length") or 0) <= 900:
            punkt += 5
        # Angespielte Bruchstuecke (Jingles, halbe Dateien) nicht nach oben spuelen.
        if 0 < (e.get("length") or 0) < 45:
            punkt -= 35
        if punkt >= min_punkte:
            ergebnisse.append({
                **{k: e[k] for k in ("id", "uid", "song", "unique_id", "song_id", "artist", "title", "album",
                                     "genre", "length", "length_text", "path", "playlists")},
                "punkteFuzzy": round(punkt, 1),
                "aehnlichkeit": round(schnitt, 3),
            })
    ergebnisse.sort(key=lambda t: t["punkteFuzzy"], reverse=True)
    return {
        "suchtext": q,
        "stufe": stufe,
        "geprueft": len(kandidaten),
        "treffer": ergebnisse[:max(1, anzahl)],
    }


# ------------------------------------------------------------------ Richtungen

SYNONYME: dict[str, list[str]] = {
    "rock": ["rock", "classic rock", "hard rock", "soft rock", "folk rock", "punk rock"],
    "rockig": ["rock", "classic rock", "hard rock"],
    "hardrock": ["hard rock", "heavy metal", "hard n heavy"],
    "metal": ["metal", "heavy metal", "thrash metal", "power metal", "death metal",
              "black metal", "gothic metal", "symphonic metal"],
    "metall": ["metal", "heavy metal", "hard rock"],
    "metallisch": ["metal", "heavy metal"],
    "punk": ["punk", "punk rock", "proto punk", "ska punk"],
    "pop": ["pop", "pop rock", "synth pop", "dance pop", "europop"],
    "poppig": ["pop", "dance pop", "europop"],
    "charts": ["pop", "dance pop", "hip hop", "rnb"],
    "hiphop": ["hip hop", "hip-hop", "rap", "gangsta rap"],
    "deutschrap": ["deutschrap", "german rap", "hip hop", "rap"],
    "germanrap": ["deutschrap", "german rap", "hip hop"],
    "rap": ["rap", "hip hop", "hip-hop"],
    "electronic": ["electronic", "electronica", "edm", "house", "techno", "trance", "dance"],
    "elektro": ["electronic", "electronica", "edm", "house", "techno", "trance", "dance"],
    "techno": ["techno", "house", "trance", "electronic", "dance"],
    "dance": ["dance", "eurodance", "hands up", "edm", "electronic"],
    "tanzmusik": ["dance", "eurodance", "disco", "hands up"],
    "grunge": ["grunge", "alternative rock", "alternative"],
    "alternative": ["alternative", "alternative rock", "indie", "indie rock"],
    "indie": ["indie", "indie rock", "alternative"],
    "disco": ["disco", "eurodisco", "funk", "soul"],
    "eurodisco": ["eurodisco", "disco", "synth pop"],
    "funk": ["funk", "soul", "disco"],
    "soul": ["soul", "funk", "rnb"],
    "blues": ["blues", "blues rock", "rhythm and blues"],
    "jazz": ["jazz", "swing", "big band"],
    "klassik": ["classical", "klassik", "orchestra", "opera", "baroque"],
    "klassisch": ["classical", "klassik", "orchestra"],
    "folk": ["folk", "folk rock", "folk metal", "mittelalter", "medieval"],
    "mittelalter": ["mittelalter", "medieval", "folk metal", "viking metal"],
    "country": ["country", "country rock", "americana"],
    "reggae": ["reggae", "ska", "dancehall"],
    "schlager": ["schlager", "volksmusik", "deutsche musik"],
    "gothic": ["gothic", "gothic rock", "dark wave", "industrial"],
    "dark": ["dark wave", "gothic", "industrial", "dark ambient"],
    "industrial": ["industrial", "industrial metal", "ebm"],
    "ndh": ["neue deutsche haerte", "industrial metal"],
    "haerte": ["neue deutsche haerte", "industrial metal"],
    "deutsch": ["neue deutsche haerte", "deutsche musik", "deutschrap", "mittelalter"],
    "deutsche": ["neue deutsche haerte", "deutsche musik", "deutschrap"],
    "oldies": ["oldies", "rock n roll", "schlager"],
    "rocknroll": ["rock n roll", "rockabilly"],
    "ska": ["ska", "ska punk", "reggae"],
    "trance": ["trance", "house", "techno"],
    "house": ["house", "techno", "electronic"],
    "rnb": ["rnb", "soul", "hip hop"],
    "klassiker": ["classic rock", "oldies"],
    # Stimmungen -> typische Richtungen
    # Stimmungen -> typische Richtungen. Einzahlformen und verwandte Begriffe
    # mitnehmen: im Archiv steht oft "Ballad" (nicht "Ballads") oder "Lullaby".
    "ruhig": ["ballads", "ballad", "soft rock", "acoustic", "folk", "unplugged", "lullaby"],
    "ruhiges": ["ballads", "ballad", "soft rock", "acoustic", "folk", "unplugged", "lullaby"],
    "ruhige": ["ballads", "ballad", "soft rock", "acoustic", "folk", "unplugged", "lullaby"],
    "chillig": ["ballads", "ballad", "soft rock", "acoustic", "downtempo", "ambient", "lullaby"],
    "entspannt": ["ballads", "ballad", "soft rock", "acoustic", "ambient", "lullaby"],
    "entspanntes": ["ballads", "ballad", "soft rock", "acoustic", "ambient", "lullaby"],
    "ballade": ["ballads", "ballad", "soft rock", "acoustic"],
    "balladen": ["ballads", "ballad", "soft rock", "acoustic"],
    "langsam": ["ballads", "ballad", "downtempo", "ambient"],
    "romantisch": ["ballads", "ballad", "love songs", "soft rock"],
    "liebe": ["ballads", "ballad", "love songs"],
    "traurig": ["ballads", "ballad", "dark wave", "ambient"],
    "hart": ["hard rock", "heavy metal", "metal"],
    "hartes": ["hard rock", "heavy metal", "metal"],
    "laut": ["hard rock", "heavy metal", "metal", "punk"],
    "lautes": ["hard rock", "heavy metal", "metal"],
    "aggressiv": ["metal", "hard rock", "punk", "industrial metal"],
    "party": ["dance", "eurodance", "disco", "pop", "hands up"],
    "partymusik": ["dance", "eurodance", "disco", "hands up"],
    "tanzbar": ["dance", "eurodance", "house", "disco"],
    "froehlich": ["pop", "dance", "europop"],
    "gutelaune": ["pop", "dance", "europop", "disco"],
}

# Stimmungen: diese Richtungen passen nicht dazu
STIMMUNG_GEGEN: dict[str, list[str]] = {
    "ruhig": ["hard rock", "heavy metal", "metal", "thrash metal", "death metal", "punk",
              "industrial metal", "hardcore", "ebm", "grunge"],
    "ruhiges": ["hard rock", "heavy metal", "metal", "thrash metal", "death metal", "punk",
                "industrial metal", "hardcore", "ebm", "grunge"],
    "ruhige": ["hard rock", "heavy metal", "metal", "thrash metal", "death metal", "punk",
               "industrial metal", "hardcore", "ebm", "grunge"],
    "chillig": ["hard rock", "heavy metal", "metal", "punk", "thrash metal", "industrial metal"],
    "entspannt": ["hard rock", "heavy metal", "metal", "punk", "thrash metal", "industrial metal"],
    "entspanntes": ["hard rock", "heavy metal", "metal", "punk", "thrash metal", "industrial metal"],
    "ballade": ["hard rock", "heavy metal", "metal", "punk"],
    "balladen": ["hard rock", "heavy metal", "metal", "punk"],
    "romantisch": ["hard rock", "heavy metal", "metal", "punk"],
    "liebe": ["hard rock", "heavy metal", "metal", "punk"],
    "traurig": ["hard rock", "heavy metal", "metal", "punk", "eurodisco", "hands up", "eurodance"],
    "langsam": ["hard rock", "heavy metal", "metal", "punk", "hands up", "hardstyle"],
}

RICHTUNG_HILFE = ["musik", "richtung", "genre", "stil", "sound", "art", "zeug", "kram",
                  "was", "etwas", "irgendwas", "mal", "aus", "dem", "der", "den", "die",
                  "das", "fuer", "mit", "im", "in", "ausdem", "ausm", "maessig", "ausser",
                  "sorte", "thema"]

# Typische Richtungen je Jahrzehnt, wenn im Archiv kein Jahr steht
JAHRZEHNT_GENRES: dict[int, list[str]] = {
    1960: ["rock n roll", "classic rock", "pop"],
    1970: ["rock", "disco", "classic rock", "funk"],
    1980: ["eurodisco", "synth pop", "new wave", "pop", "rock"],
    1990: ["grunge", "eurodance", "hip hop", "alternative", "pop"],
    2000: ["pop", "dance pop", "hip hop", "rnb", "rock"],
    2010: ["pop", "dance pop", "hip hop", "electronic"],
    2020: ["pop", "hip hop", "electronic"],
}


def richtung_finden(wort: str) -> tuple[list[str], list[str], list[str]]:
    """Stichwort -> (Genre-Bausteine, Stimmungen, Hinweise)."""
    teile = [t for t in normalisieren(wort).split() if t]
    bausteine: list[str] = []
    stimmungen: list[str] = []
    hinweise: list[str] = []
    for t in teile:
        if t in SYNONYME:
            bausteine.extend(SYNONYME[t])
            if t in STIMMUNG_GEGEN:
                stimmungen.append(t)
        else:
            nah = difflib.get_close_matches(t, list(SYNONYME), n=1, cutoff=0.82)
            if nah:
                bausteine.extend(SYNONYME[nah[0]])
                if nah[0] in STIMMUNG_GEGEN:
                    stimmungen.append(nah[0])
                hinweise.append(f"{t} → {nah[0]}")
            else:
                if t not in RICHTUNG_HILFE:
                    bausteine.append(t)
    gesehen: set[str] = set()
    eindeutig = [b for b in bausteine if not (b in gesehen or gesehen.add(b))]
    return eindeutig, stimmungen, hinweise


def jahrzehnt(wort: str) -> tuple[int, int] | None:
    """Erkennt "90er", "80ern", "1990er", "2010er"."""
    t = normalisieren(wort)
    m = re.search(r"\b(19|20)?(\d)0(er|ern|s|iger|erjahre)\b", t)
    if not m:
        m = re.search(r"\b(19|20)(\d)0\b", t)
    if not m:
        return None
    jahrhundert = m.group(1) or ("20" if int(m.group(2)) < 3 else "19")
    start = int(jahrhundert + m.group(2) + "0")
    if not 1950 <= start <= 2030:
        return None
    return start, start + 9


@router.get("/genre")
def genre_vorschlag(wort: str = Query(..., min_length=2), anzahl: int = 12,
                    mischen: bool = True, nur_mit_playlist: bool = False) -> dict[str, Any]:
    if not _katalog_bereit():
        raise HTTPException(status_code=503, detail="Katalog ist noch nicht geladen")
    alle = _katalog["eintraege"]
    bausteine, stimmungen, hinweise = richtung_finden(wort)
    ziel = set(bausteine)
    kandidaten: set[int] = set()

    for b in bausteine:
        if b in _genre_index:
            kandidaten.update(_genre_index[b])
    if not kandidaten:
        nah = difflib.get_close_matches(normalisieren(wort), list(_genre_index), n=3, cutoff=0.75)
        for n in nah:
            kandidaten.update(_genre_index[n])
            hinweise.append(f"{wort} → {n}")
        if nah:
            ziel.update(nah)

    zeitraum = jahrzehnt(wort)
    modus = "genre"
    if zeitraum:
        von, bis = zeitraum
        jahre = [i for j, idx in _jahr_index.items() if von <= j <= bis for i in idx]
        if len(jahre) >= 10:
            kandidaten = set(jahre)
            modus = "jahr"
            hinweise.append(f"Jahre {von}-{bis}")
        else:
            typisch = JAHRZEHNT_GENRES.get(von, [])
            for t in typisch:
                kandidaten.update(_genre_index.get(t, []))
            ziel.update(typisch)
            hinweise.append(f"typische Richtungen der {von}er")

    gegen = {g for s in stimmungen for g in STIMMUNG_GEGEN.get(s, [])}
    # Bei Stimmungswuenschen zusaetzlich Sammler-Genres aussortieren: im Archiv tragen
    # tausende Titel denselben langen Tag ("Rock | Hard Rock | Heavy Metal | … | Folk"),
    # der alles gleichzeitig ist und damit nichts aussagt.
    max_genre_worte = 4 if stimmungen else 99
    mindestdauer = 90 if stimmungen else 60

    bewertet: list[tuple[float, int]] = []
    for i in kandidaten:
        e = alle[i]
        pfad = e["path"].lower()
        if pfad.startswith("moderation/") or not re.search(r"\.(mp3|m4a|aac|ogg|opus|flac)$", pfad):
            continue
        # Bruchstuecke (angespielte Dateien, Jingles) und lange Mixe aussortieren.
        dauer = e.get("length") or 0
        if not mindestdauer <= dauer <= 600:
            continue
        if nur_mit_playlist and not e.get("playlists"):
            continue
        meine = [t for t in (normalisieren(x) for x in GENRE_TRENNER.split(e.get("genre") or "")) if t]
        if len(meine) > max_genre_worte:
            continue
        if gegen and any(t in gegen for t in meine):
            continue
        if modus == "jahr":          # Jahresauswahl braucht keine Genrepassung
            # Trotzdem bevorzugen, was auch zur Richtung passt, und keine
            # kurzen Zwischenstuecke (Intro, Skit) aus den Jahren spielen.
            if (e.get("length") or 0) < 120:
                continue
            bonus = 0.25 if any(t in ziel for t in meine) else 0.0
            bewertet.append((0.5 + bonus, i))
            continue
        if not meine:
            continue
        treffer = sum(1 for t in meine if t in ziel)
        if treffer == 0:
            continue
        reinheit = treffer / len(meine)
        if reinheit < 0.34:
            continue
        bewertet.append((reinheit, i))

    if len(bewertet) < 10 and not stimmungen:  # Schwellen lockern, wenn zu streng gefiltert wurde
        for i in kandidaten:
            if any(i == j for _, j in bewertet):
                continue
            e = alle[i]
            dauer = e.get("length") or 0
            if not 60 <= dauer <= 600:
                continue
            meine = [t for t in (normalisieren(x) for x in GENRE_TRENNER.split(e.get("genre") or "")) if t]
            if meine and any(t in ziel for t in meine) and not (gegen and any(t in gegen for t in meine)):
                bewertet.append((0.1, i))

    bewertet.sort(key=lambda p: p[0], reverse=True)
    kopf = bewertet[:max(anzahl * 12, 240)]
    if mischen:
        random.shuffle(kopf)
    treffer = []
    for _, i in kopf[:max(1, anzahl)]:
        e = alle[i]
        treffer.append({k: e[k] for k in ("id", "uid", "song", "unique_id", "song_id", "artist", "title",
                                          "album", "genre", "length", "length_text", "path", "playlists")})
    return {
        "wort": wort,
        "genutzt": sorted(ziel),
        "stimmungen": stimmungen,
        "hinweise": hinweise,
        "anzahl_gesamt": len(bewertet) or len(kandidaten),
        "treffer": treffer,
    }


@router.get("/genre/liste")
def genre_liste(anzahl: int = 40) -> dict[str, Any]:
    haeufig = sorted(_genre_index.items(), key=lambda kv: len(kv[1]), reverse=True)[:anzahl]
    return {
        "stichwoerter": sorted(SYNONYME),
        "hilfsworte": RICHTUNG_HILFE,
        "genres": [{"name": n, "anzahl": len(v)} for n, v in haeufig],
    }


@router.get("/katalog/kuenstler")
def katalog_kuenstler(anzahl: int = 60) -> dict[str, Any]:
    """Haeufigste Interpreten - als Fachhinweis fuer die Spracherkennung.

    faster-whisper erkennt Eigennamen deutlich besser, wenn sie im Hinweistext
    stehen ("Nirvana" statt "neue Runner"). Der Bot holt die Liste beim Bauen.
    """
    if not _katalog_bereit():
        raise HTTPException(status_code=503, detail="Katalog ist noch nicht geladen")
    zaehler: dict[str, int] = {}
    for e in _katalog["eintraege"]:
        name = (e.get("artist") or "").strip()
        # Sampler, Diverse und zu kurze Eintraege helfen der Erkennung nicht.
        if len(name) < 3 or name.lower() in ("va", "various", "various artists", "unknown",
                                            "unbekannt", "diverse", "verschiedene"):
            continue
        # Nur den Hauptnamen vor einem ";" oder " feat." nehmen.
        haupt = re.split(r"\s*(?:;|/| feat\.?| & )", name, maxsplit=1)[0].strip()
        if len(haupt) < 3:
            continue
        zaehler[haupt] = zaehler.get(haupt, 0) + 1
    haeufig = sorted(zaehler.items(), key=lambda kv: kv[1], reverse=True)[:anzahl]
    return {"anzahl": len(haeufig), "namen": [n for n, _ in haeufig]}
