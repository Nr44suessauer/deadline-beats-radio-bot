"""Tasks around the playlists of the station (AzuraCast).

The bot forwards messages and button presses to here; this service
clarifies the request, remembers the selection and creates/extends/plays the list.
This keeps the n8n workflow lean and the logic testable here.

Endpoints:
    POST /playlist/command   {chatId, text}
        -> {answer, keyboard?, area?}
    POST /playlist/button    {chatId, data, text?}
        -> {answer, keyboard?, edit?}

Important interface routes of the station (verified on 2026-09-20):
    GET    /api/station/1/playlists                     lists (id, name, num_songs)
    GET    /api/station/1/playlist/{id}/export/m3u      titles as paths, in order
    PUT    /api/station/1/files/batch                   {do:playlist, files:[...],
                                                         playlists:["new"],
                                                         new_playlist_name:"..."} creates
                                                         AND fills in one call
    POST   /api/station/1/playlist/{id}/import          upload m3u -> appends
    DELETE /api/station/1/playlist/{id}/empty           empties the list
    DELETE /api/station/1/playlist/{id}                 deletes the list
    PUT    /api/station/1/playlist/{id}                 change (without "left"/"podcasts"!)
    PUT    /api/station/1/files/batch                   {do:"immediate"|"queue", files:[...]}

Careful: "files/batch" with do=playlist REPLACES the lists of the track. For
"removing", the list is therefore emptied and the rest imported anew.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

AZ_URL = os.environ.get("AZ_URL", "http://192.168.178.33").rstrip("/")
AZ_KEY = os.environ.get("AZ_KEY", "")
API = AZ_URL + "/api/station/1"
KANDIDATEN_MAX = 8

router = APIRouter()

# chatId -> current selection
ZUSTAND: dict[str, dict[str, Any]] = {}

TRENNER = re.compile(r"[|;/,]")


def _api(method: str, path: str, body: Any = None, raw: bool = False,
         formdatei: tuple[str, bytes] | None = None) -> tuple[int, Any]:
    """Calls the station interface. Returns (HTTP code, response)."""
    url = AZ_URL + path
    kopf = {"X-API-Key": AZ_KEY}
    data = None
    if formdatei is not None:
        name, inhalt = formdatei
        margin = uuid.uuid4().hex
        data = (
            f"--{margin}\r\n"
            f'Content-Disposition: form-data; name="playlist_file"; filename="{name}"\r\n'
            f"Content-Type: audio/x-mpegurl\r\n\r\n"
        ).encode() + inhalt + f"\r\n--{margin}--\r\n".encode()
        kopf["Content-Type"] = f"multipart/form-data; boundary={margin}"
    elif body is not None:
        data = json.dumps(body).encode()
        kopf["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=kopf, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as answer:
            text = answer.read().decode("utf-8", "replace")
            return answer.status, text if raw else (json.loads(text) if text.strip() else {})
    except urllib.error.HTTPError as error:
        text = error.read().decode("utf-8", "replace")
        return error.code, text if raw else {"error": text[:200]}


# ------------------------------------------------------------------ Lists

def listen() -> list[dict[str, Any]]:
    code, data = _api("GET", "/api/station/1/playlists")
    if code != 200 or not isinstance(data, list):
        raise HTTPException(status_code=502, detail=f"Lists not readable (HTTP {code})")
    return [p for p in data if isinstance(p, dict)]


def liste_finden(name: str) -> dict[str, Any] | None:
    """Finds a list by its name (fuzzy too)."""
    gesucht = _norm(name)
    all = listen()
    for p in all:
        if _norm(p.get("name")) == gesucht:
            return p
    for p in all:
        if gesucht and gesucht in _norm(p.get("name")):
            return p
    # Word-wise: "summer" finds "Summer 2026"
    for p in all:
        if gesucht and any(w in _norm(p.get("name")).split() for w in gesucht.split()):
            return p
    return None


def liste_inhalt(pid: int) -> tuple[list[str], list[str]]:
    """Paths and display titles of a list.

    Two ways of the same interface: `/export/m3u` gives the plain paths,
    `/export?format=m3u` additionally the titles ("Artist - Title"). Both
    path lists are identical (verified); the second way delivers the nicer
    display. If the titles are missing, the file names serve.
    """
    paths: list[str] = []
    title: list[str] = []
    code, text = _api("GET", f"/api/station/1/playlist/{pid}/export?format=m3u", raw=True)
    if code == 200:
        for zeile in str(text).splitlines():
            hits = re.match(r"^(File|Title)(\d+)=(.*)$", zeile.strip())
            if not hits:
                continue
            (paths if hits.group(1) == "File" else title).append(hits.group(3).strip())
    if not paths:  # Fallback: plain path list
        code2, text2 = _api("GET", f"/api/station/1/playlist/{pid}/export/m3u", raw=True)
        if code2 == 200:
            paths = [z.strip() for z in str(text2).splitlines() if z.strip()]
    if len(title) != len(paths):
        title = [p.rsplit("/", 1)[-1] for p in paths]
    return paths, title


def liste_pfade(pid: int) -> list[str]:
    return liste_inhalt(pid)[0]


def liste_titel(pid: int) -> list[str]:
    return liste_inhalt(pid)[1]


def liste_anlegen(name: str, paths: list[str]) -> dict[str, Any]:
    code, data = _api("PUT", "/api/station/1/files/batch", {
        "do": "playlist", "files": paths, "playlists": ["new"],
        "new_playlist_name": name,
    })
    if code != 200 or not isinstance(data, dict) or not data.get("success"):
        raise HTTPException(status_code=502, detail=f"Creation failed (HTTP {code})")
    return data.get("record") or {}


def liste_ergaenzen(pid: int, paths: list[str]) -> tuple[bool, str]:
    if not paths:
        return False, "no titles"
    inhalt = ("\n".join(paths) + "\n").encode("utf-8")
    code, data = _api("POST", f"/api/station/1/playlist/{pid}/import",
                       formdatei=("list.m3u", inhalt))
    if code != 200 or not isinstance(data, dict) or not data.get("success"):
        return False, f"HTTP {code}: {str(data)[:150]}"
    return True, str(data.get("formatted_message") or data.get("message") or "extended")


def liste_leeren(pid: int) -> bool:
    code, _ = _api("DELETE", f"/api/station/1/playlist/{pid}/empty")
    return code == 200


def liste_loeschen(pid: int) -> bool:
    code, _ = _api("DELETE", f"/api/station/1/playlist/{pid}")
    return code == 200


def liste_umbenennen(pid: int, new: str) -> tuple[bool, str]:
    code, data = _api("GET", f"/api/station/1/playlist/{pid}")
    if code != 200 or not isinstance(data, dict):
        return False, f"List not readable (HTTP {code})"
    # "left" and "podcasts" must not be sent along: the receiver
    # expects a collection for podcasts, not a field (HTTP 500).
    body = {k: v for k, v in data.items() if k not in ("left", "podcasts")}
    body["name"] = new
    code, answer = _api("PUT", f"/api/station/1/playlist/{pid}", body)
    if code != 200:
        return False, f"HTTP {code}: {str(answer)[:150]}"
    return True, new


def liste_abspielen(pid: int, paths: list[str] | None = None) -> tuple[bool, str]:
    """Plays the titles of the list right away, in order."""
    title = paths if paths is not None else liste_pfade(pid)
    if not title:
        return False, "The list is empty."
    # Flush running interrupters so the first title starts immediately.
    _api("PUT", "/api/admin/debug/station/1/telnet",
         {"command": "interrupting_requests.flush_and_skip"})
    code, _ = _api("PUT", "/api/station/1/files/batch", {"do": "immediate", "files": [title[0]]})
    if code != 200:
        return False, f"start failed (HTTP {code})"
    if len(title) > 1:
        _api("PUT", "/api/station/1/files/batch", {"do": "queue", "files": title[1:]})
    return True, f"{len(title)} titles are now playing in order."


# ------------------------------------------------------------------ Search

def candidates(searchtext: str, count: int = KANDIDATEN_MAX) -> list[dict[str, Any]]:
    """Searches titles in the catalog (fuzzy) and returns them with path."""
    try:
        from katalog import search as katalog_suche  # same application
    except Exception:  # noqa: BLE001
        katalog_suche = None

    hits: list[dict[str, Any]] = []
    if katalog_suche is not None:
        try:
            result = katalog_suche(q=searchtext, count=count * 2, min_punkte=15)
            for t in result.get("hits", []):
                hits.append({"title": (t.get("artist") + " - " + t.get("title")).strip(" -"),
                                "path": t.get("path") or "", "source": "catalog"})
        except Exception:  # noqa: BLE001
            pass

    if len(hits) < count:
        # Second source: full-text search of the station
        code, data = _api("GET", "/api/station/1/files?rowCount=30&searchPhrase="
                                  + urllib.parse.quote(searchtext))
        if code == 200 and isinstance(data, dict):
            for r in data.get("rows", []):
                path = r.get("path") or ""
                if not path or any(t["path"] == path for t in hits):
                    continue
                hits.append({"title": ((r.get("artist") or "") + " - " + (r.get("title") or "")).strip(" -"),
                                "path": path, "source": "sender"})

    # Merge duplicate titles (same recording)
    seen: set[str] = set()
    sauber: list[dict[str, Any]] = []
    for t in hits:
        core = _norm(t["title"])
        if not core or core in seen:
            continue
        seen.add(core)
        sauber.append(t)
        if len(sauber) >= count:
            break
    return sauber


def _norm(text: Any) -> str:
    s = str(text or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


# ------------------------------------------------- Request from the message

REGELN: list[tuple[str, re.Pattern[str]]] = [
    # Order matters: "rename ... to" must not count as a listing.
    ("rename", re.compile(r"\b(renam\w*|call\w*)\b.{0,40}\bto\b", re.I)),
    ("delete", re.compile(r"\b(delet\w*|remov\w*)\b.{0,25}(playlist|list)\b", re.I)),
    ("clear", re.compile(r"\b(empt\w*|clear\w*)\b.{0,25}(playlist|list)\b", re.I)),
    ("titel_entfernen", re.compile(r"\b(add|tak\w*|remov\w*|delet\w*|thro\w*)\b.{0,40}"
                                    r"|(out of|from|off)\s*(the)?\s*(playlist|list)", re.I)),
    ("listen", re.compile(r"\b(which|show|list|show me)\b.{0,20}(playlist|list|lists)\b"
                           r"|\b(playlists|lists)\b.{0,12}(are|exist|show)", re.I)),
    ("view", re.compile(r"\b(what|which titles|content|show)\b.{0,25}\b(in|of|from|the)\b.{0,10}"
                            r"|(playlist|list)\b", re.I)),
    ("playback", re.compile(r"^\s*(play|start|put|set)\b.{0,25}(playlist|list)\b"
                              r"|^\s*(make|do)\b.{0,25}(playlist|list)\b.{0,12}\b(play|run|go)\b", re.I)),
    ("build", re.compile(r"\b(build\w*|creat\w*|mak\w*|new)\b.{0,25}"
                          r"|(playlist|list)\b", re.I)),
    ("extend", re.compile(r"\b(add|put|plac\w*|insert)\b.{0,30}"
                              r"|(in|into|to the playlist|to the list|onto)", re.I)),
]

LISTE_WORT = r"(?:playlist|playlists|list|lists)"
ARTIKEL = r"(?:the|a|an)\s+"
# Criterion comes after "from"/"with"/"by"
KRITERIUM_MUSTER = re.compile(r"\b(?:from|with|by)\s+(.+)$", re.I)
# "add <title> to the playlist <name>" / "add <title>"
HINZU_MUSTER = re.compile(r"\b(?:add|put|insert)\s+(.+?)\s+"
                          r"|(in|into|to the playlist|to the list|onto)", re.I)
# "rename ... to <new>"
UMLAUT_PATTERN = re.compile(r"\bto\s+(.+?)\s*(?:\band\b|$)", re.I)
# Intent at the end of the sentence ("... and play them", "... now"): belongs neither in the
# name of the list nor in the search term.
ABSICHT_ENDE = re.compile(r"\s+(?:and\s+)?(?:then\s+)?(?:play|start|run|go|"
                          r"|kick off|listen)\b.*$", re.I)
ABSICHT_WORT = re.compile(r"\s+(?:right away|now|then|afterwards|go)\s*$", re.I)


def _ohne_absicht(text: str) -> str:
    """Removes the intent at the end and cleans up punctuation."""
    return ABSICHT_WORT.sub("", ABSICHT_ENDE.sub("", str(text or ""))).strip(" .!?\"'")


def _zerlegen(raw: str, type: str) -> tuple[str, str]:
    """Separates the name of the list from the search term.

 Examples:
        "build a playlist Summer from Scooter"      -> ("Summer", "Scooter")
        "build a playlist from Scooter"             -> ("Scooter", "Scooter")
        "build a playlist from Scooter and play it" -> ("Scooter", "Scooter")
        "create a playlist named Summer"            -> ("Summer", "")
        "play the playlist Summer"                  -> ("Summer", "")
        "add Hyper Hyper to the playlist Summer"    -> ("Summer", "Hyper Hyper")
        "remove Hyper Hyper from the playlist X"    -> ("X", "")
        "rename the playlist Summer to New"         -> ("Summer", "")
    """
    # When renaming, the old name ends at "to ..."
    match = UMLAUT_PATTERN.search(raw)
    before_um = raw[:match.start()].rstrip(" ,") if match else raw

    criterion = ""
    if type == "build":
        hits = KRITERIUM_MUSTER.search(before_um)
        if hits:
            criterion = _ohne_absicht(hits.group(1))
    elif type == "extend":
        hits = HINZU_MUSTER.search(raw)
        if hits:
            criterion = _ohne_absicht(hits.group(1))

    name = ""
    # explicit name: "named X" / "with the name X" / in quotation marks
    hits = re.search(r"(?:named|with the name|with name)\s+[\"\u201c\u201e‘]?(.+?)[\"\u201c\u201d\u201e’]?"
                        r"(?:\s+(?:from|with|by)\b|$|\s*,\s*)", before_um, re.I)
    if hits:
        name = hits.group(1).strip(" .!?\"'")
    if not name:
        hits = re.search(r"[\"\u201c\u201e]([^\"\u201c\u201d\u201e]{2,40})[\"\u201c\u201d\u201e]", raw)
        if hits:
            name = hits.group(1).strip()
    if not name:
        # Text after the list word, cut off at "from/with/by"
        hits = re.search(LISTE_WORT + r"\s+(?:named\s+|with the name\s+)?(.+)$", before_um, re.I)
        rest = hits.group(1).strip(" .!?\"'") if hits else ""
        rest = re.sub(r"^(?:from|with|by)\s+", "", rest, flags=re.I)
        rest = re.split(r"\s+\b(?:from|with|by)\b\s+", rest, maxsplit=1)[0].strip(" .!?\"'")
        rest = re.sub(r"^" + ARTIKEL, "", rest, flags=re.I)
        rest = re.sub(r"^(playlist|list)\s+", "", rest, flags=re.I)
        if _norm(rest) in ("", "a", "an", "new", "one"):
            rest = ""
        name = rest

    name = _ohne_absicht(name)

    if not name and type in ("build", "extend"):
        name = criterion
    if type in ("build", "extend") and not criterion:
        criterion = name
    return name, criterion


def auftrag_lesen(text: str) -> dict[str, Any]:
    """Recognizes what the operator intends to do with the lists."""
    raw = str(text or "").strip()
    if not raw:
        return {"type": "help"}
    for type, muster in REGELN:
        if muster.search(raw):
            break
    else:
        return {"type": "unclear"}

    name, criterion = _zerlegen(raw, type)
    if type == "listen":  # pure listing: no name, no search term
        name = criterion = ""
    # "build a playlist X and play it right away" -> after creating, without asking
    # starting. Only relevant for creating/adding.
    together = type in ("build", "extend") and bool(
        re.search(r"\b(?:and\s+)?(?:play|start|run|go)\b"
                  r"(?:\s+\w+){0,3}?\s+(?:it|them|go|run|now)\b", raw, re.I))
    return {"type": type, "name": name, "criterion": criterion, "text": raw,
            "play_later": together}


# ------------------------------------------------------------------ Menu

def menue_lieder(z: dict[str, Any]) -> str:
    lines = [f"\U0001f4dd {z['name']}" if z.get("name") else "\U0001f4dd New playlist",
              f"Search term: {z.get('criterion', '')}", ""]
    for i, k in enumerate(z["candidates"], start=1):
        lines.append(("\u2705 " if k["chosen"] else "\u2b1c ") + f"{i}. {k['title']}")
    chosen = sum(1 for k in z["candidates"] if k["chosen"])
    lines.append("")
    lines.append(f"{chosen} of {len(z['candidates'])} selected. "
                  "Tap the titles, then \u201cDone\u201d.")
    return "\n".join(lines)


def menue_tastatur_lieder(z: dict[str, Any]) -> dict[str, Any]:
    lines = []
    for i, k in enumerate(z["candidates"], start=1):
        characters = "\u2705" if k["chosen"] else "\u2b1c"
        lines.append([{"text": f"{characters} {k['title']}"[:60], "callback_data": f"p{i}"}])
    lines.append([{"text": "\u2705 All", "callback_data": "pa"},
                   {"text": "\u2b1c None", "callback_data": "pk"}])
    lines.append([{"text": "\u25b6\ufe0f Done", "callback_data": "pf"},
                   {"text": "\u274c Cancel", "callback_data": "px"}])
    return {"inline_keyboard": lines}


def menue_tastatur_listen(listen_: list[dict[str, Any]]) -> dict[str, Any]:
    lines = [[{"text": f"\U0001f4fb {p['name']} ({p.get('num_songs', 0)} titles)"[:60],
                "callback_data": f"l{i}"}] for i, p in enumerate(listen_[:KANDIDATEN_MAX], start=1)]
    return {"inline_keyboard": lines}


def menue_tastatur_ja_nein(question: str) -> dict[str, Any]:
    return {"inline_keyboard": [[
        {"text": "\u2705 Yes", "callback_data": "j"},
        {"text": "\u274c No", "callback_data": "n"}]]}


def liste_text(pid: int, name: str, title: list[str], count: int = 20) -> str:
    if not title:
        return f"\U0001f4fb \u201c{name}\u201d is empty."
    lines = [f"\U0001f4fb \u201c{name}\u201d \u2013 {len(title)} titles", ""]
    for i, t in enumerate(title[:count], start=1):
        lines.append(f"{i}. {t}"[:100])
    if len(title) > count:
        lines.append(f"\u2026 and {len(title) - count} more")
    return "\n".join(lines)


# ------------------------------------------------------------------ Commands

class Command(BaseModel):
    chatId: str
    text: str = ""


class button(BaseModel):
    chatId: str
    data: str = Field("", description="callback_data of the button")
    text: str = ""


def _frisch(chat_id: str) -> dict[str, Any]:
    return ZUSTAND.get(chat_id) or {}


@router.post("/playlist/command")
def playlist_befehl(command: Command) -> dict[str, Any]:
    job = auftrag_lesen(command.text)
    type = job["type"]
    chat = command.chatId

    if type == "unclear":
        return {"answer": "I did not understand that about the playlists. "
                           "Examples:\n\u2022 \u201cwhat playlists are there\u201d\n"
                           "\u2022 \u201cbuild a playlist Summer from Scooter\u201d\n"
                           "\u2022 \u201cplay the playlist Summer\u201d",
                "area": "playlist"}

    if type == "titel_entfernen":
        return {"answer": "Removing single titles from a list is not possible yet. "
                           "You can empty the list (\u201cempty the playlist X\u201d) and "
                           "rebuild it.", "area": "playlist"}

    if type == "listen":
        all = listen()
        if not all:
            return {"answer": "There are no playlists yet.", "area": "playlist"}
        lines = ["\U0001f4fb Playlists:"]
        for p in all:
            characters = "\u25b6\ufe0f" if p.get("is_enabled") else "\u23f8\ufe0f"
            lines.append(f"{characters} {p['name']} \u2013 {p.get('num_songs', 0)} titles")
        lines.append("\n\u201cplay the playlist NAME\u201d starts a list.")
        return {"answer": "\n".join(lines), "area": "playlist"}

    if type == "playback" and not job["name"]:
        all = listen()
        if not all:
            return {"answer": "There are no playlists yet.", "area": "playlist"}
        ZUSTAND[chat] = {"type": "listenwahl", "listen": all}
        return {"answer": "Which playlist should play?", "area": "playlist",
                "keyboard": menue_tastatur_listen(all)}

    if type in ("playback", "view", "clear", "delete", "rename", "extend"):
        list = liste_finden(job["name"])
        if list is None:
            all = listen()
            ZUSTAND[chat] = {"type": "listenwahl", "listen": all,
                             "later": type, "name": job["name"],
                             "criterion": job.get("criterion", "")}
            return {"answer": f"\u201c{job['name']}\u201d I do not know. "
                               "Which list do you mean?", "area": "playlist",
                    "keyboard": menue_tastatur_listen(all)}
        return _weitere_aktion(chat, type, list, job)

    if type == "build":
        k = candidates(job["criterion"] or job["name"])
        if not k:
            return {"answer": f"For \u201c{job['criterion']}\u201d I found nothing.",
                    "area": "playlist"}
        ZUSTAND[chat] = {"type": "songs", "name": job["name"] or "New list",
                         "criterion": job["criterion"],
                         "play_later": bool(job.get("play_later")),
                         "candidates": [dict(t, chosen=False) for t in k]}
        z = ZUSTAND[chat]
        return {"answer": menue_lieder(z), "keyboard": menue_tastatur_lieder(z),
                "area": "playlist"}

    return {"answer": "I cannot do this request yet.", "area": "playlist"}


def _weitere_aktion(chat: str, type: str, list: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    pid, name = int(list["id"]), str(list.get("name"))
    if type == "playback":
        ok, news = liste_abspielen(pid)
        return {"answer": ("\u25b6\ufe0f " if ok else "\u26a0\ufe0f ") + news, "area": "playlist"}
    if type == "view":
        return {"answer": liste_text(pid, name, liste_titel(pid)), "area": "playlist"}
    if type == "clear":
        ZUSTAND[chat] = {"type": "confirmation", "what": "clear", "pid": pid, "name": name}
        return {"answer": f"Should I really empty \u201c{name}\u201d? "
                           f"({list.get('num_songs', 0)} titles will be removed)",
                "keyboard": menue_tastatur_ja_nein(name), "area": "playlist"}
    if type == "delete":
        ZUSTAND[chat] = {"type": "confirmation", "what": "delete", "pid": pid, "name": name}
        return {"answer": f"Should I really delete the playlist \u201c{name}\u201d?",
                "keyboard": menue_tastatur_ja_nein(name), "area": "playlist"}
    if type == "rename":
        new = _neuer_name(job.get("text", ""))
        if not new:
            return {"answer": "What should the list be called? For example say: "
                               f"\u201crename the playlist {name} to Summer 2026\u201d",
                    "area": "playlist"}
        ok, news = liste_umbenennen(pid, new)
        return {"answer": (f"\u2705 \u201c{name}\u201d is now called \u201c{new}\u201d."
                            if ok else f"\u26a0\ufe0f {news}"), "area": "playlist"}
    if type == "extend":
        k = candidates(job.get("criterion") or "")
        if not k:
            return {"answer": "What should I add?", "area": "playlist"}
        ZUSTAND[chat] = {"type": "songs", "name": name, "pid": pid,
                         "criterion": job.get("criterion", ""),
                         "play_later": bool(job.get("play_later")),
                         "candidates": [dict(t, chosen=False) for t in k]}
        z = ZUSTAND[chat]
        return {"answer": menue_lieder(z), "keyboard": menue_tastatur_lieder(z),
                "area": "playlist"}
    return {"answer": "I cannot do this request yet.", "area": "playlist"}


def _neuer_name(text: str) -> str:
    hits = re.search(r"\bto\s+(.+?)\s*$", text, re.I)
    if hits:
        return hits.group(1).strip(" .!?\"'")
    hits = re.search(r"\bto\s*(?:into)?\s*(.+)$", text, re.I)
    return hits.group(1).strip(" .!?\"'") if hits else ""


def _menue_zeigen(z: dict[str, Any]) -> dict[str, Any]:
    if z.get("type") == "songs":
        return {"answer": menue_lieder(z), "keyboard": menue_tastatur_lieder(z),
                "area": "playlist", "edit": True}
    if z.get("type") == "listenwahl":
        return {"answer": "Which playlist should it be?",
                "keyboard": menue_tastatur_listen(z["listen"]),
                "area": "playlist", "edit": True}
    return {"answer": "The selection has expired. Please start over.", "area": "playlist"}


@router.post("/playlist/button")
def playlist_knopf(button: button) -> dict[str, Any]:
    chat = button.chatId
    data = str(button.data or "")
    z = _frisch(chat)

    if data == "px":
        ZUSTAND.pop(chat, None)
        # After creating, the button says "Enough" — then there is nothing to cancel.
        answer = ("\U0001f44d All right, \u201c" + str(z["name"]) + "\u201d stays saved."
                   if z.get("type") == "done" and z.get("name") else "Abgebrochen.")
        return {"answer": answer, "edit": True, "keyboard": {"inline_keyboard": []},
                "area": "playlist"}

    if data == "v":
        pid = z.get("pid")
        if not pid:
            return {"answer": "The selection has expired. Please start over.",
                    "area": "playlist"}
        ZUSTAND.pop(chat, None)
        ok, news = liste_abspielen(int(pid))
        return {"answer": ("\u25b6\ufe0f " if ok else "\u26a0\ufe0f ") + news,
                "edit": True, "keyboard": {"inline_keyboard": []}, "area": "playlist"}

    if z.get("type") == "confirmation" and data in ("j", "n"):
        ZUSTAND.pop(chat, None)
        if data == "n":
            return {"answer": "Never mind, then.", "edit": True,
                    "keyboard": {"inline_keyboard": []}, "area": "playlist"}
        if z["what"] == "clear":
            ok = liste_leeren(int(z["pid"]))
            return {"answer": f"\U0001f9f9 \u201c{z['name']}\u201d is emptied." if ok
                    else "\u26a0\ufe0f Emptying did not work.",
                    "edit": True, "keyboard": {"inline_keyboard": []}, "area": "playlist"}
        ok = liste_loeschen(int(z["pid"]))
        return {"answer": f"\U0001f5d1\ufe0f \u201c{z['name']}\u201d is deleted." if ok
                else "\u26a0\ufe0f Deleting did not work.",
                "edit": True, "keyboard": {"inline_keyboard": []}, "area": "playlist"}

    if z.get("type") == "listenwahl" and re.fullmatch(r"l\d{1,2}", data):
        i = int(data[1:]) - 1
        liste_gewaehlt = (z.get("listen") or [])[i] if i < len(z.get("listen") or []) else None
        if not liste_gewaehlt:
            return {"answer": "This number no longer exists.", "edit": True,
                    "keyboard": {"inline_keyboard": []}, "area": "playlist"}
        later = z.get("later")
        ZUSTAND.pop(chat, None)
        if later and later != "playback":
            answer = _weitere_aktion(chat, later, liste_gewaehlt, {"text": ""})
            if z.get("criterion"):
                answer = _weitere_aktion(chat, later, liste_gewaehlt, {"criterion": z["criterion"]})
            answer["edit"] = True
            return answer
        ok, news = liste_abspielen(int(liste_gewaehlt["id"]))
        return {"answer": ("\u25b6\ufe0f " if ok else "\u26a0\ufe0f ") + news,
                "edit": True, "keyboard": {"inline_keyboard": []}, "area": "playlist"}

    if z.get("type") != "songs":
        return {"answer": "The selection has expired. Please start over.", "area": "playlist"}

    if data == "pa":
        for k in z["candidates"]:
            k["chosen"] = True
    elif data == "pk":
        for k in z["candidates"]:
            k["chosen"] = False
    elif re.fullmatch(r"p\d{1,2}", data):
        i = int(data[1:]) - 1
        if i < len(z["candidates"]):
            z["candidates"][i]["chosen"] = not z["candidates"][i]["chosen"]
    elif data == "pf":
        chosen = [k["path"] for k in z["candidates"] if k["chosen"]]
        if not chosen:
            return {"answer": "No title is selected.", "edit": True,
                    "keyboard": menue_tastatur_lieder(z), "area": "playlist"}
        name = z.get("name") or "New list"
        pid = z.get("pid")
        if pid:                                   # add to an existing list
            ok, news = liste_ergaenzen(int(pid), chosen)
            answer = (f"\u2705 {len(chosen)} titles added to \u201c{name}\u201d."
                       if ok else f"\u26a0\ufe0f {news}")
        else:                                     # create and fill a new list
            try:
                datensatz = liste_anlegen(name, chosen)
                pid = datensatz.get("id")
                answer = (f"\u2705 Playlist \u201c{name}\u201d with "
                           f"{len(chosen)} titles created.")
            except HTTPException as error:
                return {"answer": f"\u26a0\ufe0f {error.detail}", "edit": True,
                        "keyboard": menue_tastatur_lieder(z), "area": "playlist"}
        ZUSTAND[chat] = {"type": "done", "pid": pid, "name": name}
        if z.get("play_later") and pid:
            ZUSTAND.pop(chat, None)
            ok, news = liste_abspielen(int(pid))
            return {"answer": answer + "\n" + ("\u25b6\ufe0f " if ok else "\u26a0\ufe0f ")
                    + news, "edit": True, "keyboard": {"inline_keyboard": []},
                    "area": "playlist"}
        return {"answer": answer + "\n\nShould it play right away?", "edit": True,
                "keyboard": {"inline_keyboard": [[
                    {"text": "\u25b6\ufe0f Play now", "callback_data": "v"},
                    {"text": "\U0001f44d Enough", "callback_data": "px"}]]},
                "area": "playlist"}

    return _menue_zeigen(z)


@router.post("/playlist/suggestion")
def playlist_vorschlag(data: Command) -> dict[str, Any]:
    """Candidates for a search term (for the selection in the bot)."""
    return {"candidates": candidates(data.text)}


@router.get("/playlist/status")
def playlist_status() -> dict[str, Any]:
    return {"offene_auswahlen": len(ZUSTAND), "list": list(ZUSTAND.keys())[:5],
            "station_interface": AZ_URL, "app": "playlist"}
