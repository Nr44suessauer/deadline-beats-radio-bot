"""Catalog of the music archive: fuzzy search, genre and mood suggestions.

The catalog is fetched once from the AzuraCast interface and stored as JSON
on disk. This lets the bot also find titles that were said wrong or unclearly
(typos, missing letters, swapped order), and it can make
suggestions from a genre ("something from rock", "something calm", "90s").

Endpoints:
    GET  /catalog/status          count and state
    POST /catalog/refresh   fetch the catalog again (takes ~45 s)
    GET  /search?q=...             fuzzy search
    GET  /genre?word=...          suggestions from a genre
    GET  /genre/list             known genres and keywords
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
KATALOG_DIR = Path(os.environ.get("KATALOG_DIR", "/data"))
KATALOG_DATEI = KATALOG_DIR / "catalog.json"

router = APIRouter()

# ------------------------------------------------------------------ Normalizing

UMLAUTE = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
NICHT_WORT = re.compile(r"[^a-z0-9]+")
JAHR = re.compile(r"(19[5-9][0-9]|20[0-3][0-9])")
GENRE_TRENNER = re.compile(r"[|;/,]")

# Paths that the bot must never suggest or play:
#   moderation/ = announcements of the moderator
#   _Archiv/    = live and bootleg recordings (moved there on 2026-09-20)
GESPERRTE_PFADE = ("moderation/", "_archiv/")


def gesperrt(path: Any) -> bool:
    return str(path or "").lower().startswith(GESPERRTE_PFADE)


def normalisieren(text: str) -> str:
    s = str(text or "").lower()
    for a, b in UMLAUTE.items():
        s = s.replace(a, b)
    return NICHT_WORT.sub(" ", s).strip()


def mask(text: str) -> int:
    """Bit mask of the letters a-z — very fast pre-filter."""
    m = 0
    for c in text:
        if "a" <= c <= "z":
            m |= 1 << (ord(c) - 97)
    return m


def jahr_aus_album(album: str) -> int | None:
    hits = JAHR.findall(str(album or ""))
    return int(hits[0]) if len(hits) == 1 else None


def eintrag_bauen(r: dict[str, Any]) -> dict[str, Any]:
    artist = (r.get("artist") or "").strip()
    title = (r.get("title") or "").strip()
    album = (r.get("album") or "").strip()
    genre = (r.get("genre") or "").strip()
    path = (r.get("path") or "").strip()
    heu = normalisieren(" ".join([artist, title, album, path]))
    return {
        "id": r.get("id"),
        "uid": r.get("unique_id"),
        "song": r.get("song_id"),
        # Names as in the AzuraCast archive, so the bot finds the same fields
        # (the play plan computes with unique_id/song_id).
        "unique_id": r.get("unique_id"),
        "song_id": r.get("song_id"),
        "artist": artist,
        "title": title,
        "album": album,
        "genre": genre,
        "length": r.get("length") or 0,
        "length_text": r.get("length_text") or "",
        "path": path,
        "playlists": [p.get("id") if isinstance(p, dict) else p for p in (r.get("playlists") or [])],
        "year": jahr_aus_album(album),
        "heu": heu,
        "short": normalisieren(artist + " " + title + " " + album),
        # Only artist and title — basis of the core check in the search.
        "core": normalisieren(artist + " " + title),
        "kern_woerter": sorted(set(normalisieren(artist + " " + title).split())),
        "words": sorted(set(heu.split())),
        "mask": mask(normalisieren(artist + " " + title + " " + album)),
        "maske_all": mask(heu),
    }


# ------------------------------------------------------------------ Loading the catalog

_sperre = threading.Lock()
_katalog: dict[str, Any] = {"stand": None, "count": 0, "entries": []}
_genre_index: dict[str, list[int]] = {}
_year_index: dict[int, list[int]] = {}
_dauer: dict[str, Any] = {"letzte_dauer_s": None}


def _indizes_bauen() -> None:
    global _genre_index, _year_index
    genre: dict[str, list[int]] = {}
    years: dict[int, list[int]] = {}
    for i, e in enumerate(_katalog.get("entries", [])):
        if "mask" not in e:  # older catalog file
            e["mask"] = mask(normalisieren(f'{e["artist"]} {e["title"]} {e["album"]}'))
            e["maske_all"] = mask(e["heu"])
            e.setdefault("words", sorted(set(e["heu"].split())))
        e.setdefault("short", normalisieren(f'{e["artist"]} {e["title"]} {e["album"]}'))
        for teil in GENRE_TRENNER.split(e.get("genre") or ""):
            t = normalisieren(teil)
            if t:
                genre.setdefault(t, []).append(i)
        j = e.get("year")
        if j:
            years.setdefault(j, []).append(i)
    _genre_index = genre
    _year_index = years


def katalog_laden() -> None:
    global _katalog
    if not KATALOG_DATEI.is_file():
        return
    data = json.loads(KATALOG_DATEI.read_text(encoding="utf-8"))
    with _sperre:
        _katalog = data
        _indizes_bauen()


def katalog_holen() -> dict[str, Any]:
    if not AZ_KEY:
        raise HTTPException(status_code=500, detail="AZ_KEY is missing")
    all: list[dict[str, Any]] = []
    seite = 1
    while True:
        url = f"{AZ_URL}/api/station/1/files?rowCount=1000&page={seite}"
        request = urllib.request.Request(url, headers={"X-API-Key": AZ_KEY})
        with urllib.request.urlopen(request, timeout=60) as answer:
            data = json.loads(answer.read().decode("utf-8"))
        lines = data.get("rows") or []
        if not lines:
            break
        all.extend(
            eintrag_bauen(r) for r in lines if not gesperrt(r.get("path"))
        )
        if seite >= int(data.get("total_pages") or 1):
            break
        seite += 1
    return {"stand": time.strftime("%Y-%m-%dT%H:%M:%S"), "count": len(all), "entries": all}


def katalog_aktualisieren() -> dict[str, Any]:
    global _katalog
    start = time.time()
    new = katalog_holen()
    KATALOG_DIR.mkdir(parents=True, exist_ok=True)
    KATALOG_DATEI.write_text(json.dumps(new, ensure_ascii=False), encoding="utf-8")
    with _sperre:
        _katalog = new
        _indizes_bauen()
    _dauer["letzte_dauer_s"] = round(time.time() - start, 1)
    return new


def _katalog_bereit() -> bool:
    return bool(_katalog.get("entries"))


@router.get("/catalog/status")
def katalog_status() -> dict[str, Any]:
    return {
        "count": _katalog.get("count", 0),
        "stand": _katalog.get("stand"),
        "genres": len(_genre_index),
        "years": len(_year_index),
        "letzte_dauer_s": _dauer["letzte_dauer_s"],
    }


@router.post("/catalog/refresh")
def katalog_neu() -> dict[str, Any]:
    new = katalog_aktualisieren()
    return {"ok": True, "count": new["count"], "stand": new["stand"],
            "dauer_s": _dauer["letzte_dauer_s"]}


# ------------------------------------------------------------------ Fuzzy search

def _aehnlichkeit(word: str, heu: str, heu_woerter: list[str]) -> float:
    # Check whole word: "tim" must not hit inside "everytim e".
    if f" {word} " in f" {heu} ":
        return 1.0
    best = 0.0
    beginning = word[0]
    for k in heu_woerter:
        # only check words with the same start or similar length
        if k[0] != beginning and abs(len(k) - len(word)) > 3:
            continue
        r = difflib.SequenceMatcher(None, word, k).ratio()
        if k.startswith(word[:2]) and r > best:
            r = min(1.0, r + 0.08)
        if r > best:
            best = r
    return best


def _kandidaten(words: list[str]) -> tuple[list[int], str]:
    """Pre-filter via letter bit masks."""
    all = _katalog.get("entries", [])
    masken = [mask(w) for w in words]
    short = [i for i, e in enumerate(all) if all((e["mask"] & m) == m for m in masken)]
    if len(short) >= 5:
        return short, "short"
    weit = [i for i, e in enumerate(all) if all((e["maske_all"] & m) == m for m in masken)]
    if len(weit) >= 5:
        return weit, "weit"
    laengste = max(masken, key=lambda m: bin(m).count("1"))
    single = [i for i, e in enumerate(all) if (e["maske_all"] & laengste) == laengste]
    return (single or weit or short), "single"


@router.get("/search")
def search(q: str = Query(..., min_length=1), count: int = 8,
          min_punkte: int = 20) -> dict[str, Any]:
    if not _katalog_bereit():
        raise HTTPException(status_code=503, detail="Catalog is not loaded yet")
    ganz = normalisieren(q)
    words = [w for w in ganz.split() if len(w) > 1] or [ganz]
    if not ganz:
        return {"searchtext": q, "hits": [], "checked": 0}

    candidates, stufe = _kandidaten(words)
    # Preselection by a favourable trait (contains the whole word or the word start)
    if len(candidates) > 4000:
        def guenstig(i: int) -> int:
            short = _katalog["entries"][i]["short"]
            woerter_kurz = short.split()
            return sum(1 for w in words
                       if w in short or any(k.startswith(w[:3]) for k in woerter_kurz))

        candidates = sorted(candidates, key=guenstig, reverse=True)[:4000]

    ergebnisse: list[dict[str, Any]] = []
    for i in candidates:
        e = _katalog["entries"][i]
        teil = [_aehnlichkeit(w, e["heu"], e["words"]) for w in words]
        # Length-weighted: a sure long word ("rammstein") should outweigh
        # a misheard short one ("Ben Tim").
        gewicht = sum(len(w) for w in words) or 1
        schnitt = sum(t * len(w) for t, w in zip(teil, words)) / gewicht
        total = difflib.SequenceMatcher(None, ganz, e["short"]).ratio()
        # Core check: some search word must sit in the artist or title.
        # Without it, random echoes from album and path names pull hits up
        # (the misheard voice message "Ben Tim Rammstein" landed at 50 Cent).
        core = e.get("core") or normalisieren(e["artist"] + " " + e["title"])
        kern_woerter = e.get("kern_woerter") or core.split()
        best_kern = 0.0
        for w in words:
            if f" {w} " in f" {core} ":
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
        punkt = schnitt * 70 + total * 30 + best_kern * 20
        artist = normalisieren(e["artist"])
        if artist and ganz in artist:
            punkt += 15
        path = e["path"].lower()
        if not re.search(r"\.(mp3|m4a|aac|ogg|opus|flac)$", path):
            punkt -= 10
        if path.startswith("moderation/"):
            punkt -= 60
        if 0 < (e.get("length") or 0) <= 900:
            punkt += 5
        # Do not flush played fragments (jingles, half files) to the top.
        if 0 < (e.get("length") or 0) < 45:
            punkt -= 35
        if punkt >= min_punkte:
            ergebnisse.append({
                **{k: e[k] for k in ("id", "uid", "song", "unique_id", "song_id", "artist", "title", "album",
                                     "genre", "length", "length_text", "path", "playlists")},
                "punkteFuzzy": round(punkt, 1),
                "similarity": round(schnitt, 3),
            })
    ergebnisse.sort(key=lambda t: t["punkteFuzzy"], reverse=True)
    return {
        "searchtext": q,
        "stufe": stufe,
        "checked": len(candidates),
        "hits": ergebnisse[:max(1, count)],
    }


# ------------------------------------------------------------------ Genres

SYNONYME: dict[str, list[str]] = {
    "rock": ["rock", "classic rock", "hard rock", "soft rock", "folk rock", "punk rock"],
    "rocky": ["rock", "classic rock", "hard rock"],
    "hardrock": ["hard rock", "heavy metal", "hard n heavy"],
    "metal": ["metal", "heavy metal", "thrash metal", "power metal", "death metal",
              "black metal", "gothic metal", "symphonic metal"],
    "metall": ["metal", "heavy metal", "hard rock"],
    "metallic": ["metal", "heavy metal"],
    "punk": ["punk", "punk rock", "proto punk", "ska punk"],
    "pop": ["pop", "pop rock", "synth pop", "dance pop", "europop"],
    "poppy": ["pop", "dance pop", "europop"],
    "charts": ["pop", "dance pop", "hip hop", "rnb"],
    "hiphop": ["hip hop", "hip-hop", "rap", "gangsta rap"],
    "germanrap": ["germanrap", "german rap", "hip hop", "rap"],
    "germanrap": ["germanrap", "german rap", "hip hop"],
    "rap": ["rap", "hip hop", "hip-hop"],
    "electronic": ["electronic", "electronica", "edm", "house", "techno", "trance", "dance"],
    "elektro": ["electronic", "electronica", "edm", "house", "techno", "trance", "dance"],
    "techno": ["techno", "house", "trance", "electronic", "dance"],
    "dance": ["dance", "eurodance", "hands up", "edm", "electronic"],
    "dancemusic": ["dance", "eurodance", "disco", "hands up"],
    "grunge": ["grunge", "alternative rock", "alternative"],
    "alternative": ["alternative", "alternative rock", "indie", "indie rock"],
    "indie": ["indie", "indie rock", "alternative"],
    "disco": ["disco", "eurodisco", "funk", "soul"],
    "eurodisco": ["eurodisco", "disco", "synth pop"],
    "funk": ["funk", "soul", "disco"],
    "soul": ["soul", "funk", "rnb"],
    "blues": ["blues", "blues rock", "rhythm and blues"],
    "jazz": ["jazz", "swing", "big band"],
    "classical": ["classical", "classical", "orchestra", "opera", "baroque"],
    "classical": ["classical", "classical", "orchestra"],
    "folk": ["folk", "folk rock", "folk metal", "medieval", "medieval"],
    "medieval": ["medieval", "medieval", "folk metal", "viking metal"],
    "country": ["country", "country rock", "americana"],
    "reggae": ["reggae", "ska", "dancehall"],
    "schlager": ["schlager", "volksmusik", "german music"],
    "gothic": ["gothic", "gothic rock", "dark wave", "industrial"],
    "dark": ["dark wave", "gothic", "industrial", "dark ambient"],
    "industrial": ["industrial", "industrial metal", "ebm"],
    "ndh": ["new german hardness", "industrial metal"],
    "hardness": ["new german hardness", "industrial metal"],
    "german": ["new german hardness", "german music", "germanrap", "medieval"],
    "german": ["new german hardness", "german music", "germanrap"],
    "oldies": ["oldies", "rock n roll", "schlager"],
    "rocknroll": ["rock n roll", "rockabilly"],
    "ska": ["ska", "ska punk", "reggae"],
    "trance": ["trance", "house", "techno"],
    "house": ["house", "techno", "electronic"],
    "rnb": ["rnb", "soul", "hip hop"],
    "classics": ["classic rock", "oldies"],
    # Moods -> typical genres
    # Moods -> typical genres. Include singular forms and related terms:
    # in the archive it often says "Ballad" (not "Ballads") or "Lullaby".
    "calm": ["ballads", "ballad", "soft rock", "acoustic", "folk", "unplugged", "lullaby"],
    "calm": ["ballads", "ballad", "soft rock", "acoustic", "folk", "unplugged", "lullaby"],
    "calm": ["ballads", "ballad", "soft rock", "acoustic", "folk", "unplugged", "lullaby"],
    "chill": ["ballads", "ballad", "soft rock", "acoustic", "downtempo", "ambient", "lullaby"],
    "relaxed": ["ballads", "ballad", "soft rock", "acoustic", "ambient", "lullaby"],
    "relaxed": ["ballads", "ballad", "soft rock", "acoustic", "ambient", "lullaby"],
    "ballad": ["ballads", "ballad", "soft rock", "acoustic"],
    "ballads": ["ballads", "ballad", "soft rock", "acoustic"],
    "slow": ["ballads", "ballad", "downtempo", "ambient"],
    "romantic": ["ballads", "ballad", "love songs", "soft rock"],
    "love": ["ballads", "ballad", "love songs"],
    "sad": ["ballads", "ballad", "dark wave", "ambient"],
    "hard": ["hard rock", "heavy metal", "metal"],
    "hard": ["hard rock", "heavy metal", "metal"],
    "loud": ["hard rock", "heavy metal", "metal", "punk"],
    "loud": ["hard rock", "heavy metal", "metal"],
    "aggressive": ["metal", "hard rock", "punk", "industrial metal"],
    "party": ["dance", "eurodance", "disco", "pop", "hands up"],
    "partymusic": ["dance", "eurodance", "disco", "hands up"],
    "danceable": ["dance", "eurodance", "house", "disco"],
    "cheerful": ["pop", "dance", "europop"],
    "goodmood": ["pop", "dance", "europop", "disco"],
}

# Moods: these genres do not fit
STIMMUNG_GEGEN: dict[str, list[str]] = {
    "calm": ["hard rock", "heavy metal", "metal", "thrash metal", "death metal", "punk",
              "industrial metal", "hardcore", "ebm", "grunge"],
    "calm": ["hard rock", "heavy metal", "metal", "thrash metal", "death metal", "punk",
                "industrial metal", "hardcore", "ebm", "grunge"],
    "calm": ["hard rock", "heavy metal", "metal", "thrash metal", "death metal", "punk",
               "industrial metal", "hardcore", "ebm", "grunge"],
    "chill": ["hard rock", "heavy metal", "metal", "punk", "thrash metal", "industrial metal"],
    "relaxed": ["hard rock", "heavy metal", "metal", "punk", "thrash metal", "industrial metal"],
    "relaxed": ["hard rock", "heavy metal", "metal", "punk", "thrash metal", "industrial metal"],
    "ballad": ["hard rock", "heavy metal", "metal", "punk"],
    "ballads": ["hard rock", "heavy metal", "metal", "punk"],
    "romantic": ["hard rock", "heavy metal", "metal", "punk"],
    "love": ["hard rock", "heavy metal", "metal", "punk"],
    "sad": ["hard rock", "heavy metal", "metal", "punk", "eurodisco", "hands up", "eurodance"],
    "slow": ["hard rock", "heavy metal", "metal", "punk", "hands up", "hardstyle"],
}

RICHTUNG_HILFE = ["music", "direction", "genre", "stil", "sound", "type", "stuff", "junk",
                  "what", "something", "anything", "just", "from", "the", "the", "the", "the",
                  "the", "for", "with", "in", "in", "from", "from", "ish", "except",
                  "kind", "topic"]

# Typical genres per decade, when the archive has no year
DECADE_GENRES: dict[int, list[str]] = {
    1960: ["rock n roll", "classic rock", "pop"],
    1970: ["rock", "disco", "classic rock", "funk"],
    1980: ["eurodisco", "synth pop", "new wave", "pop", "rock"],
    1990: ["grunge", "eurodance", "hip hop", "alternative", "pop"],
    2000: ["pop", "dance pop", "hip hop", "rnb", "rock"],
    2010: ["pop", "dance pop", "hip hop", "electronic"],
    2020: ["pop", "hip hop", "electronic"],
}


def richtung_finden(word: str) -> tuple[list[str], list[str], list[str]]:
    """Keyword -> (genre building blocks, moods, hints)."""
    teile = [t for t in normalisieren(word).split() if t]
    bausteine: list[str] = []
    stimmungen: list[str] = []
    hints: list[str] = []
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
                hints.append(f"{t} → {nah[0]}")
            else:
                if t not in RICHTUNG_HILFE:
                    bausteine.append(t)
    seen: set[str] = set()
    eindeutig = [b for b in bausteine if not (b in seen or seen.add(b))]
    return eindeutig, stimmungen, hints


def jahrzehnt(word: str) -> tuple[int, int] | None:
    """Recognizes "90s", "80s", "1990s", "2010s"."""
    t = normalisieren(word)
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
def genre_vorschlag(word: str = Query(..., min_length=2), count: int = 12,
                    mischen: bool = True, nur_mit_playlist: bool = False) -> dict[str, Any]:
    if not _katalog_bereit():
        raise HTTPException(status_code=503, detail="Catalog is not loaded yet")
    all = _katalog["entries"]
    bausteine, stimmungen, hints = richtung_finden(word)
    target = set(bausteine)
    candidates: set[int] = set()

    for b in bausteine:
        if b in _genre_index:
            candidates.update(_genre_index[b])
    if not candidates:
        nah = difflib.get_close_matches(normalisieren(word), list(_genre_index), n=3, cutoff=0.75)
        for n in nah:
            candidates.update(_genre_index[n])
            hints.append(f"{word} → {n}")
        if nah:
            target.update(nah)

    period = jahrzehnt(word)
    modus = "genre"
    if period:
        from_, to = period
        years = [i for j, idx in _year_index.items() if from_ <= j <= to for i in idx]
        if len(years) >= 10:
            candidates = set(years)
            modus = "year"
            hints.append(f"years {from_}-{to}")
        else:
            typical = DECADE_GENRES.get(from_, [])
            for t in typical:
                candidates.update(_genre_index.get(t, []))
            target.update(typical)
            hints.append(f"typical genres of the {from_}s")

    against = {g for s in stimmungen for g in STIMMUNG_GEGEN.get(s, [])}
    # For mood requests, additionally filter out collector genres: in the archive
    # thousands of titles carry the same long tag ("Rock | Hard Rock | Heavy Metal | … | Folk"),
    # which is everything at once and therefore says nothing.
    max_genre_worte = 4 if stimmungen else 99
    mindestdauer = 90 if stimmungen else 60

    bewertet: list[tuple[float, int]] = []
    for i in candidates:
        e = all[i]
        path = e["path"].lower()
        if path.startswith("moderation/") or not re.search(r"\.(mp3|m4a|aac|ogg|opus|flac)$", path):
            continue
        # Filter out fragments (sampled files, jingles) and long mixes.
        duration = e.get("length") or 0
        if not mindestdauer <= duration <= 600:
            continue
        if nur_mit_playlist and not e.get("playlists"):
            continue
        meine = [t for t in (normalisieren(x) for x in GENRE_TRENNER.split(e.get("genre") or "")) if t]
        if len(meine) > max_genre_worte:
            continue
        if against and any(t in against for t in meine):
            continue
        if modus == "year":          # Year selection needs no genre match
            # Still prefer what also fits the genre, and do not play
            # short interludes (intro, skit) from those years.
            if (e.get("length") or 0) < 120:
                continue
            bonus = 0.25 if any(t in target for t in meine) else 0.0
            bewertet.append((0.5 + bonus, i))
            continue
        if not meine:
            continue
        hits = sum(1 for t in meine if t in target)
        if hits == 0:
            continue
        reinheit = hits / len(meine)
        if reinheit < 0.34:
            continue
        bewertet.append((reinheit, i))

    if len(bewertet) < 10 and not stimmungen:  # Loosen thresholds if filtering was too strict
        for i in candidates:
            if any(i == j for _, j in bewertet):
                continue
            e = all[i]
            duration = e.get("length") or 0
            if not 60 <= duration <= 600:
                continue
            meine = [t for t in (normalisieren(x) for x in GENRE_TRENNER.split(e.get("genre") or "")) if t]
            if meine and any(t in target for t in meine) and not (against and any(t in against for t in meine)):
                bewertet.append((0.1, i))

    bewertet.sort(key=lambda p: p[0], reverse=True)
    kopf = bewertet[:max(count * 12, 240)]
    if mischen:
        random.shuffle(kopf)
    hits = []
    for _, i in kopf[:max(1, count)]:
        e = all[i]
        hits.append({k: e[k] for k in ("id", "uid", "song", "unique_id", "song_id", "artist", "title",
                                          "album", "genre", "length", "length_text", "path", "playlists")})
    return {
        "word": word,
        "used": sorted(target),
        "stimmungen": stimmungen,
        "hints": hints,
        "anzahl_gesamt": len(bewertet) or len(candidates),
        "hits": hits,
    }


@router.get("/genre/list")
def genre_liste(count: int = 40) -> dict[str, Any]:
    haeufig = sorted(_genre_index.items(), key=lambda kv: len(kv[1]), reverse=True)[:count]
    return {
        "stichwoerter": sorted(SYNONYME),
        "helpers": RICHTUNG_HILFE,
        "genres": [{"name": n, "count": len(v)} for n, v in haeufig],
    }


@router.get("/catalog/artists")
def katalog_kuenstler(count: int = 60) -> dict[str, Any]:
    """Most frequent artists — as a hint for speech recognition.

    faster-whisper recognizes proper names much better when they are in the hint text
    ("Nirvana" instead of "new Runner"). The bot fetches the list when building.
    """
    if not _katalog_bereit():
        raise HTTPException(status_code=503, detail="Catalog is not loaded yet")
    counter: dict[str, int] = {}
    for e in _katalog["entries"]:
        name = (e.get("artist") or "").strip()
        # Samplers, various-artists and too short entries do not help recognition.
        if len(name) < 3 or name.lower() in ("va", "various", "various artists", "unknown",
                                            "unknown", "diverse", "verschiedene"):
            continue
        # Only take the main name before a ";" or " feat.".
        haupt = re.split(r"\s*(?:;|/| feat\.?| & )", name, maxsplit=1)[0].strip()
        if len(haupt) < 3:
            continue
        counter[haupt] = counter.get(haupt, 0) + 1
    haeufig = sorted(counter.items(), key=lambda kv: kv[1], reverse=True)[:count]
    return {"count": len(haeufig), "names": [n for n, _ in haeufig]}
