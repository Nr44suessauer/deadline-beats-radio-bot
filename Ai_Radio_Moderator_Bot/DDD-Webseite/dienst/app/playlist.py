"""Aufgaben rund um die Wiedergabelisten des Senders (AzuraCast).

Der Bot reicht Nachrichten und Knopfdruecke hierher weiter; dieser Dienst
klaert den Auftrag, merkt sich die Auswahl und legt/erweitert/spielt die Liste.
Damit bleibt der n8n-Ablauf schlank und die Logik hier testbar.

Endpunkte:
    POST /playlist/befehl   {chatId, text}
        -> {antwort, tastatur?, bereich?}
    POST /playlist/knopf    {chatId, daten, text?}
        -> {antwort, tastatur?, bearbeiten?}

Wichtige Schnittstellenwege des Senders (am 2026-09-20 geprueft):
    GET    /api/station/<id>/playlists                     Listen (id, name, num_songs)
    GET    /api/station/<id>/playlist/{id}/export/m3u      Titel als Pfade, in Reihenfolge
    PUT    /api/station/<id>/files/batch                   {do:playlist, files:[...],
                                                         playlists:["new"],
                                                         new_playlist_name:"..."} legt an
                                                         UND fuellt in einem Aufruf
    POST   /api/station/<id>/playlist/{id}/import          m3u hochladen -> ergaenzt
    DELETE /api/station/<id>/playlist/{id}/empty           leert die Liste
    DELETE /api/station/<id>/playlist/{id}                 loescht die Liste
    PUT    /api/station/<id>/playlist/{id}                 aendern (ohne "links"/"podcasts"!)
    PUT    /api/station/<id>/files/batch                   {do:"immediate"|"queue", files:[...]}

Achtung: "files/batch" mit do=playlist ERSETZT die Listen des Titels. Fuer
"entfernen" wird deshalb geleert und der Rest neu importiert.
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
AZ_STATION_ID = os.environ.get("AZ_STATION_ID", "1")  # Sendernummer in AzuraCast
API = AZ_URL + f"/api/station/{AZ_STATION_ID}"
KANDIDATEN_MAX = 8

router = APIRouter()

# chatId -> laufende Auswahl
ZUSTAND: dict[str, dict[str, Any]] = {}

TRENNER = re.compile(r"[|;/,]")


def _api(methode: str, pfad: str, koerper: Any = None, roh: bool = False,
         formdatei: tuple[str, bytes] | None = None) -> tuple[int, Any]:
    """Ruft die Senderschnittstelle auf. Gibt (HTTP-Code, Antwort) zurueck."""
    url = AZ_URL + pfad
    kopf = {"X-API-Key": AZ_KEY}
    daten = None
    if formdatei is not None:
        name, inhalt = formdatei
        rand = uuid.uuid4().hex
        daten = (
            f"--{rand}\r\n"
            f'Content-Disposition: form-data; name="playlist_file"; filename="{name}"\r\n'
            f"Content-Type: audio/x-mpegurl\r\n\r\n"
        ).encode() + inhalt + f"\r\n--{rand}--\r\n".encode()
        kopf["Content-Type"] = f"multipart/form-data; boundary={rand}"
    elif koerper is not None:
        daten = json.dumps(koerper).encode()
        kopf["Content-Type"] = "application/json"
    anfrage = urllib.request.Request(url, data=daten, headers=kopf, method=methode)
    try:
        with urllib.request.urlopen(anfrage, timeout=60) as antwort:
            text = antwort.read().decode("utf-8", "replace")
            return antwort.status, text if roh else (json.loads(text) if text.strip() else {})
    except urllib.error.HTTPError as fehler:
        text = fehler.read().decode("utf-8", "replace")
        return fehler.code, text if roh else {"fehler": text[:200]}


# ------------------------------------------------------------------ Listen

def listen() -> list[dict[str, Any]]:
    code, daten = _api("GET", f"/api/station/{AZ_STATION_ID}/playlists")
    if code != 200 or not isinstance(daten, list):
        raise HTTPException(status_code=502, detail=f"Listen nicht lesbar (HTTP {code})")
    return [p for p in daten if isinstance(p, dict)]


def liste_finden(name: str) -> dict[str, Any] | None:
    """Findet eine Liste ueber ihren Namen (auch ungenau)."""
    gesucht = _norm(name)
    alle = listen()
    for p in alle:
        if _norm(p.get("name")) == gesucht:
            return p
    for p in alle:
        if gesucht and gesucht in _norm(p.get("name")):
            return p
    # Wortweise: "sommer" findet "Sommer 2026"
    for p in alle:
        if gesucht and any(w in _norm(p.get("name")).split() for w in gesucht.split()):
            return p
    return None


def liste_inhalt(pid: int) -> tuple[list[str], list[str]]:
    """Pfade und Anzeigetitel einer Liste.

    Zwei Wege derselben Schnittstelle: `/export/m3u` gibt die reinen Pfade,
    `/export?format=m3u` zusaetzlich die Titel ("Interpret - Titel"). Beide
    Pfadlisten sind gleich (geprueft); der zweite Weg liefert die schoenere
    Anzeige. Fehlen die Titel, dienen die Dateinamen.
    """
    pfade: list[str] = []
    titel: list[str] = []
    code, text = _api("GET", f"/api/station/{AZ_STATION_ID}/playlist/{pid}/export?format=m3u", roh=True)
    if code == 200:
        for zeile in str(text).splitlines():
            treffer = re.match(r"^(File|Title)(\d+)=(.*)$", zeile.strip())
            if not treffer:
                continue
            (pfade if treffer.group(1) == "File" else titel).append(treffer.group(3).strip())
    if not pfade:  # Ersatzweg: reine Pfadliste
        code2, text2 = _api("GET", f"/api/station/{AZ_STATION_ID}/playlist/{pid}/export/m3u", roh=True)
        if code2 == 200:
            pfade = [z.strip() for z in str(text2).splitlines() if z.strip()]
    if len(titel) != len(pfade):
        titel = [p.rsplit("/", 1)[-1] for p in pfade]
    return pfade, titel


def liste_pfade(pid: int) -> list[str]:
    return liste_inhalt(pid)[0]


def liste_titel(pid: int) -> list[str]:
    return liste_inhalt(pid)[1]


def liste_anlegen(name: str, pfade: list[str]) -> dict[str, Any]:
    code, daten = _api("PUT", f"/api/station/{AZ_STATION_ID}/files/batch", {
        "do": "playlist", "files": pfade, "playlists": ["new"],
        "new_playlist_name": name,
    })
    if code != 200 or not isinstance(daten, dict) or not daten.get("success"):
        raise HTTPException(status_code=502, detail=f"Anlegen fehlgeschlagen (HTTP {code})")
    return daten.get("record") or {}


def liste_ergaenzen(pid: int, pfade: list[str]) -> tuple[bool, str]:
    if not pfade:
        return False, "keine Titel"
    inhalt = ("\n".join(pfade) + "\n").encode("utf-8")
    code, daten = _api("POST", f"/api/station/{AZ_STATION_ID}/playlist/{pid}/import",
                       formdatei=("liste.m3u", inhalt))
    if code != 200 or not isinstance(daten, dict) or not daten.get("success"):
        return False, f"HTTP {code}: {str(daten)[:150]}"
    return True, str(daten.get("formatted_message") or daten.get("message") or "ergaenzt")


def liste_leeren(pid: int) -> bool:
    code, _ = _api("DELETE", f"/api/station/{AZ_STATION_ID}/playlist/{pid}/empty")
    return code == 200


def liste_loeschen(pid: int) -> bool:
    code, _ = _api("DELETE", f"/api/station/{AZ_STATION_ID}/playlist/{pid}")
    return code == 200


def liste_umbenennen(pid: int, neu: str) -> tuple[bool, str]:
    code, daten = _api("GET", f"/api/station/{AZ_STATION_ID}/playlist/{pid}")
    if code != 200 or not isinstance(daten, dict):
        return False, f"Liste nicht lesbar (HTTP {code})"
    # "links" und "podcasts" duerfen nicht mitgeschickt werden: der Empfaenger
    # erwartet fuer podcasts eine Sammlung, nicht ein Feld (HTTP 500).
    koerper = {k: v for k, v in daten.items() if k not in ("links", "podcasts")}
    koerper["name"] = neu
    code, antwort = _api("PUT", f"/api/station/{AZ_STATION_ID}/playlist/{pid}", koerper)
    if code != 200:
        return False, f"HTTP {code}: {str(antwort)[:150]}"
    return True, neu


def liste_abspielen(pid: int, pfade: list[str] | None = None) -> tuple[bool, str]:
    """Spielt die Titel der Liste sofort, in Reihenfolge."""
    titel = pfade if pfade is not None else liste_pfade(pid)
    if not titel:
        return False, "Die Liste ist leer."
    # Laufende Unterbrecher wegwerfen, damit der erste Titel sofort startet.
    _api("PUT", f"/api/admin/debug/station/{AZ_STATION_ID}/telnet",
         {"command": "interrupting_requests.flush_and_skip"})
    code, _ = _api("PUT", f"/api/station/{AZ_STATION_ID}/files/batch", {"do": "immediate", "files": [titel[0]]})
    if code != 200:
        return False, f"Start fehlgeschlagen (HTTP {code})"
    if len(titel) > 1:
        _api("PUT", f"/api/station/{AZ_STATION_ID}/files/batch", {"do": "queue", "files": titel[1:]})
    return True, f"{len(titel)} Titel laufen jetzt in Reihenfolge."


# ------------------------------------------------------------------ Suche

def kandidaten(suchtext: str, anzahl: int = KANDIDATEN_MAX) -> list[dict[str, Any]]:
    """Sucht Titel im Katalog (unscharf) und gibt sie mit Pfad zurueck."""
    try:
        from katalog import suche as katalog_suche  # gleiche Anwendung
    except Exception:  # noqa: BLE001
        katalog_suche = None

    treffer: list[dict[str, Any]] = []
    if katalog_suche is not None:
        try:
            ergebnis = katalog_suche(q=suchtext, anzahl=anzahl * 2, min_punkte=15)
            for t in ergebnis.get("treffer", []):
                treffer.append({"titel": (t.get("artist") + " - " + t.get("title")).strip(" -"),
                                "pfad": t.get("path") or "", "quelle": "katalog"})
        except Exception:  # noqa: BLE001
            pass

    if len(treffer) < anzahl:
        # Zweite Quelle: Volltextsuche des Senders
        code, daten = _api("GET", f"/api/station/{AZ_STATION_ID}/files?rowCount=30&searchPhrase="
                                  + urllib.parse.quote(suchtext))
        if code == 200 and isinstance(daten, dict):
            for r in daten.get("rows", []):
                pfad = r.get("path") or ""
                if not pfad or any(t["pfad"] == pfad for t in treffer):
                    continue
                treffer.append({"titel": ((r.get("artist") or "") + " - " + (r.get("title") or "")).strip(" -"),
                                "pfad": pfad, "quelle": "sender"})

    # Doppelte Titel (gleiche Aufnahme) zusammenfassen
    gesehen: set[str] = set()
    sauber: list[dict[str, Any]] = []
    for t in treffer:
        kern = _norm(t["titel"])
        if not kern or kern in gesehen:
            continue
        gesehen.add(kern)
        sauber.append(t)
        if len(sauber) >= anzahl:
            break
    return sauber


def _norm(text: Any) -> str:
    s = str(text or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


# ------------------------------------------------- Auftrag aus der Nachricht

REGELN: list[tuple[str, re.Pattern[str]]] = [
    # Reihenfolge ist wichtig: "benenne ... um" darf nicht als Uebersicht gelten.
    ("umbenennen", re.compile(r"\b(benenn\w*|nenn\w*)\b.{0,40}\bum\b", re.I)),
    ("loeschen", re.compile(r"\b(loesch\w*|lösch\w*)\b.{0,25}(playlist|liste|wiedergabeliste)\b", re.I)),
    ("leeren", re.compile(r"\b(leer\w*|entleer\w*)\b.{0,25}(playlist|liste)\b", re.I)),
    ("titel_entfernen", re.compile(r"\b(nimm|entfern\w*|loesch\w*|schmeiss\w*|schmeiß\w*)\b.{0,40}"
                                    r"(aus|von)\s*(der|die|dem)?\s*(playlist|liste|wiedergabeliste)", re.I)),
    ("listen", re.compile(r"\b(welche|zeig|zeige|liste|zeige mir)\b.{0,20}(playlist|wiedergabelist|listen)\b"
                           r"|\b(playlists|wiedergabelisten)\b.{0,12}(gibt|sind|zeigen|auflisten)", re.I)),
    ("ansehen", re.compile(r"\b(was|welche titel|inhalt|zeig|zeige)\b.{0,25}\b(in|von|der|die|des)\b.{0,10}"
                            r"(playlist|liste)\b", re.I)),
    ("abspielen", re.compile(r"^\s*(spiele?|starte?|leg|lege)\b.{0,25}(playlist|liste|wiedergabeliste)\b"
                              r"|^\s*mach\b.{0,25}(playlist|liste)\b.{0,12}\b(an|los|laufen)\b", re.I)),
    ("bauen", re.compile(r"\b(bau\w*|erstelle\w*|erzeug\w*|anlegen|lege\w*|mach\w*)\b.{0,25}"
                          r"(playlist|liste|wiedergabeliste)\b", re.I)),
    ("ergaenzen", re.compile(r"\b(nimm|fueg\w*|füg\w*|pack\w*|setz\w*)\b.{0,30}"
                              r"(hinzu|dazu|rein|in die playlist|in die liste)", re.I)),
]

LISTE_WORT = r"(?:playlist|playlists|wiedergabeliste|wiedergabelisten|liste|listen)"
ARTIKEL = r"(?:der|die|das|dem|den|des|einer|einen|eine|ein)\s+"
# Kriterium steht nach "aus"/"mit"/"von"
KRITERIUM_MUSTER = re.compile(r"\b(?:aus|mit|von)\s+(.+)$", re.I)
# "nimm <Titel> in die Playlist <Name>" / "fuege <Titel> hinzu"
HINZU_MUSTER = re.compile(r"\b(?:nimm|fueg\w*|füg\w*|pack\w*|setz\w*)\s+(.+?)\s+"
                          r"(?:hinzu|dazu|rein|in die playlist|in die liste)", re.I)
# "benenne ... in <neu> um"
UM_MUSTER = re.compile(r"\bin\s+(.+?)\s*\bum\b", re.I)
# Absicht am Satzende ("... und spiele sie", "... sofort"): gehoert weder in den
# Namen der Liste noch in den Suchbegriff.
ABSICHT_ENDE = re.compile(r"\s+(?:und\s+)?(?:dann\s+)?(?:spiel\w*|start\w*|lass\w*|leg\w*|"
                          r"abspiel\w*|anhoeren|hoer\w*|hör\w*)\b.*$", re.I)
ABSICHT_WORT = re.compile(r"\s+(?:gleich|sofort|jetzt|danach|anschliessend|los|ab)\s*$", re.I)


def _ohne_absicht(text: str) -> str:
    """Entfernt die Absicht am Ende und raeumt Satzzeichen weg."""
    return ABSICHT_WORT.sub("", ABSICHT_ENDE.sub("", str(text or ""))).strip(" .!?\"'")


def _zerlegen(roh: str, art: str) -> tuple[str, str]:
    """Trennt den Namen der Liste vom Suchbegriff.

    Beispiele:
        "baue eine Playlist Sommer aus Scooter"      -> ("Sommer", "Scooter")
        "baue eine Playlist aus Scooter"             -> ("Scooter", "Scooter")
        "baue eine Playlist aus Scooter und spiele sie" -> ("Scooter", "Scooter")
        "erzeuge eine playlist namens Sommer"        -> ("Sommer", "")
        "spiele die Playlist Sommer"                 -> ("Sommer", "")
        "nimm Hyper Hyper in die Playlist Sommer"    -> ("Sommer", "Hyper Hyper")
        "entferne Hyper Hyper aus der Playlist X"    -> ("X", "")
        "benenne die Playlist Sommer in Neu um"      -> ("Sommer", "")
    """
    # Beim Umbenennen endet der alte Name an "in ... um"
    um = UM_MUSTER.search(roh)
    vor_um = roh[:um.start()].rstrip(" ,") if um else roh

    kriterium = ""
    if art == "bauen":
        treffer = KRITERIUM_MUSTER.search(vor_um)
        if treffer:
            kriterium = _ohne_absicht(treffer.group(1))
    elif art == "ergaenzen":
        treffer = HINZU_MUSTER.search(roh)
        if treffer:
            kriterium = _ohne_absicht(treffer.group(1))

    name = ""
    # ausdruecklicher Name: "namens X" / "mit dem namen X" / in Anfuehrungszeichen
    treffer = re.search(r"(?:namens|mit dem namen|mit namen)\s+[\"\u201c\u201e']?(.+?)[\"\u201c\u201d\u201e']?"
                        r"(?:\s+(?:aus|mit|von)\b|$|\s*,\s*)", vor_um, re.I)
    if treffer:
        name = treffer.group(1).strip(" .!?\"'")
    if not name:
        treffer = re.search(r"[\"\u201c\u201e]([^\"\u201c\u201d\u201e]{2,40})[\"\u201c\u201d\u201e]", roh)
        if treffer:
            name = treffer.group(1).strip()
    if not name:
        # Text nach dem Listenwort, abgeschnitten an "aus/mit/von"
        treffer = re.search(LISTE_WORT + r"\s+(?:namens\s+|mit dem namen\s+)?(.+)$", vor_um, re.I)
        rest = treffer.group(1).strip(" .!?\"'") if treffer else ""
        rest = re.sub(r"^(?:aus|mit|von)\s+", "", rest, flags=re.I)
        rest = re.split(r"\s+\b(?:aus|mit|von)\b\s+", rest, maxsplit=1)[0].strip(" .!?\"'")
        rest = re.sub(r"^" + ARTIKEL, "", rest, flags=re.I)
        rest = re.sub(r"^(playlist|liste|wiedergabeliste)\s+", "", rest, flags=re.I)
        if _norm(rest) in ("", "eine", "ein", "neue", "einer"):
            rest = ""
        name = rest

    name = _ohne_absicht(name)

    if not name and art in ("bauen", "ergaenzen"):
        name = kriterium
    if art in ("bauen", "ergaenzen") and not kriterium:
        kriterium = name
    return name, kriterium


def auftrag_lesen(text: str) -> dict[str, Any]:
    """Erkennt, was der Betreiber mit den Listen vorhat."""
    roh = str(text or "").strip()
    if not roh:
        return {"art": "hilfe"}
    for art, muster in REGELN:
        if muster.search(roh):
            break
    else:
        return {"art": "unklar"}

    name, kriterium = _zerlegen(roh, art)
    if art == "listen":  # reine Auflistung: kein Name, kein Suchbegriff
        name = kriterium = ""
    # "baue eine Playlist X und spiele sie gleich" -> nach dem Anlegen ohne Rueckfrage
    # starten. Nur fuer das Anlegen/Ergaenzen von Bedeutung.
    zusammen = art in ("bauen", "ergaenzen") and bool(
        re.search(r"\b(?:und\s+)?(?:spiel\w*|start\w*|lass\w*|leg\w*|abspiel\w*)\b"
                  r"(?:\s+\w+){0,3}?\s+(?:sie|die|los|laufen|gleich|ab)\b", roh, re.I))
    return {"art": art, "name": name, "kriterium": kriterium, "text": roh,
            "danach_spielen": zusammen}


# ------------------------------------------------------------------ Menue

def menue_lieder(z: dict[str, Any]) -> str:
    zeilen = [f"\U0001f4dd {z['name']}" if z.get("name") else "\U0001f4dd Neue Wiedergabeliste",
              f"Suchbegriff: {z.get('kriterium', '')}", ""]
    for i, k in enumerate(z["kandidaten"], start=1):
        zeilen.append(("\u2705 " if k["gewaehlt"] else "\u2b1c ") + f"{i}. {k['titel']}")
    gewaehlt = sum(1 for k in z["kandidaten"] if k["gewaehlt"])
    zeilen.append("")
    zeilen.append(f"{gewaehlt} von {len(z['kandidaten'])} ausgewaehlt. "
                  "Tippe die Titel an, dann \u201eFertig\u201c.")
    return "\n".join(zeilen)


def menue_tastatur_lieder(z: dict[str, Any]) -> dict[str, Any]:
    zeilen = []
    for i, k in enumerate(z["kandidaten"], start=1):
        zeichen = "\u2705" if k["gewaehlt"] else "\u2b1c"
        zeilen.append([{"text": f"{zeichen} {k['titel']}"[:60], "callback_data": f"p{i}"}])
    zeilen.append([{"text": "\u2705 Alle", "callback_data": "pa"},
                   {"text": "\u2b1c Keine", "callback_data": "pk"}])
    zeilen.append([{"text": "\u25b6\ufe0f Fertig", "callback_data": "pf"},
                   {"text": "\u274c Abbrechen", "callback_data": "px"}])
    return {"inline_keyboard": zeilen}


def menue_tastatur_listen(listen_: list[dict[str, Any]]) -> dict[str, Any]:
    zeilen = [[{"text": f"\U0001f4fb {p['name']} ({p.get('num_songs', 0)} Titel)"[:60],
                "callback_data": f"l{i}"}] for i, p in enumerate(listen_[:KANDIDATEN_MAX], start=1)]
    return {"inline_keyboard": zeilen}


def menue_tastatur_ja_nein(frage: str) -> dict[str, Any]:
    return {"inline_keyboard": [[
        {"text": "\u2705 Ja", "callback_data": "j"},
        {"text": "\u274c Nein", "callback_data": "n"}]]}


def liste_text(pid: int, name: str, titel: list[str], anzahl: int = 20) -> str:
    if not titel:
        return f"\U0001f4fb \u201e{name}\u201c ist leer."
    zeilen = [f"\U0001f4fb \u201e{name}\u201c \u2013 {len(titel)} Titel", ""]
    for i, t in enumerate(titel[:anzahl], start=1):
        zeilen.append(f"{i}. {t}"[:100])
    if len(titel) > anzahl:
        zeilen.append(f"\u2026 und {len(titel) - anzahl} weitere")
    return "\n".join(zeilen)


# ------------------------------------------------------------------ Befehle

class Befehl(BaseModel):
    chatId: str
    text: str = ""


class Knopf(BaseModel):
    chatId: str
    daten: str = Field("", description="callback_data des Knopfes")
    text: str = ""


def _frisch(chat_id: str) -> dict[str, Any]:
    return ZUSTAND.get(chat_id) or {}


@router.post("/playlist/befehl")
def playlist_befehl(befehl: Befehl) -> dict[str, Any]:
    auftrag = auftrag_lesen(befehl.text)
    art = auftrag["art"]
    chat = befehl.chatId

    if art == "unklar":
        return {"antwort": "Das habe ich bei den Wiedergabelisten nicht verstanden. "
                           "Beispiele:\n\u2022 \u201ewas fuer Listen gibt es\u201c\n"
                           "\u2022 \u201ebaue eine Playlist Sommer aus Scooter\u201c\n"
                           "\u2022 \u201espiele die Playlist Sommer\u201c",
                "bereich": "playlist"}

    if art == "titel_entfernen":
        return {"antwort": "Einzelne Titel aus einer Liste zu nehmen kann ich noch nicht. "
                           "Du kannst die Liste leeren (\u201eleere die Playlist X\u201c) und "
                           "neu zusammenstellen.", "bereich": "playlist"}

    if art == "listen":
        alle = listen()
        if not alle:
            return {"antwort": "Es gibt noch keine Wiedergabelisten.", "bereich": "playlist"}
        zeilen = ["\U0001f4fb Wiedergabelisten:"]
        for p in alle:
            zeichen = "\u25b6\ufe0f" if p.get("is_enabled") else "\u23f8\ufe0f"
            zeilen.append(f"{zeichen} {p['name']} \u2013 {p.get('num_songs', 0)} Titel")
        zeilen.append("\n\u201espiele die Playlist NAME\u201c startet eine Liste.")
        return {"antwort": "\n".join(zeilen), "bereich": "playlist"}

    if art == "abspielen" and not auftrag["name"]:
        alle = listen()
        if not alle:
            return {"antwort": "Es gibt noch keine Wiedergabelisten.", "bereich": "playlist"}
        ZUSTAND[chat] = {"art": "listenwahl", "listen": alle}
        return {"antwort": "Welche Wiedergabeliste soll laufen?", "bereich": "playlist",
                "tastatur": menue_tastatur_listen(alle)}

    if art in ("abspielen", "ansehen", "leeren", "loeschen", "umbenennen", "ergaenzen"):
        liste = liste_finden(auftrag["name"])
        if liste is None:
            alle = listen()
            ZUSTAND[chat] = {"art": "listenwahl", "listen": alle,
                             "danach": art, "name": auftrag["name"],
                             "kriterium": auftrag.get("kriterium", "")}
            return {"antwort": f"\u201e{auftrag['name']}\u201c kenne ich nicht. "
                               "Welche Liste meinst du?", "bereich": "playlist",
                    "tastatur": menue_tastatur_listen(alle)}
        return _weitere_aktion(chat, art, liste, auftrag)

    if art == "bauen":
        k = kandidaten(auftrag["kriterium"] or auftrag["name"])
        if not k:
            return {"antwort": f"Zu \u201e{auftrag['kriterium']}\u201c habe ich nichts gefunden.",
                    "bereich": "playlist"}
        ZUSTAND[chat] = {"art": "lieder", "name": auftrag["name"] or "Neue Liste",
                         "kriterium": auftrag["kriterium"],
                         "danach_spielen": bool(auftrag.get("danach_spielen")),
                         "kandidaten": [dict(t, gewaehlt=False) for t in k]}
        z = ZUSTAND[chat]
        return {"antwort": menue_lieder(z), "tastatur": menue_tastatur_lieder(z),
                "bereich": "playlist"}

    return {"antwort": "Diesen Auftrag kann ich noch nicht.", "bereich": "playlist"}


def _weitere_aktion(chat: str, art: str, liste: dict[str, Any], auftrag: dict[str, Any]) -> dict[str, Any]:
    pid, name = int(liste["id"]), str(liste.get("name"))
    if art == "abspielen":
        ok, meldung = liste_abspielen(pid)
        return {"antwort": ("\u25b6\ufe0f " if ok else "\u26a0\ufe0f ") + meldung, "bereich": "playlist"}
    if art == "ansehen":
        return {"antwort": liste_text(pid, name, liste_titel(pid)), "bereich": "playlist"}
    if art == "leeren":
        ZUSTAND[chat] = {"art": "bestaetigung", "was": "leeren", "pid": pid, "name": name}
        return {"antwort": f"Soll ich \u201e{name}\u201c wirklich leeren? "
                           f"({liste.get('num_songs', 0)} Titel werden entfernt)",
                "tastatur": menue_tastatur_ja_nein(name), "bereich": "playlist"}
    if art == "loeschen":
        ZUSTAND[chat] = {"art": "bestaetigung", "was": "loeschen", "pid": pid, "name": name}
        return {"antwort": f"Soll ich die Wiedergabeliste \u201e{name}\u201c wirklich loeschen?",
                "tastatur": menue_tastatur_ja_nein(name), "bereich": "playlist"}
    if art == "umbenennen":
        neu = _neuer_name(auftrag.get("text", ""))
        if not neu:
            return {"antwort": "Wie soll die Liste heissen? Sag zum Beispiel: "
                               f"\u201ebenenne die Playlist {name} in Sommer 2026 um\u201c",
                    "bereich": "playlist"}
        ok, meldung = liste_umbenennen(pid, neu)
        return {"antwort": (f"\u2705 \u201e{name}\u201c heisst jetzt \u201e{neu}\u201c."
                            if ok else f"\u26a0\ufe0f {meldung}"), "bereich": "playlist"}
    if art == "ergaenzen":
        k = kandidaten(auftrag.get("kriterium") or "")
        if not k:
            return {"antwort": "Was soll ich hinzufuegen?", "bereich": "playlist"}
        ZUSTAND[chat] = {"art": "lieder", "name": name, "pid": pid,
                         "kriterium": auftrag.get("kriterium", ""),
                         "danach_spielen": bool(auftrag.get("danach_spielen")),
                         "kandidaten": [dict(t, gewaehlt=False) for t in k]}
        z = ZUSTAND[chat]
        return {"antwort": menue_lieder(z), "tastatur": menue_tastatur_lieder(z),
                "bereich": "playlist"}
    return {"antwort": "Diesen Auftrag kann ich noch nicht.", "bereich": "playlist"}


def _neuer_name(text: str) -> str:
    treffer = re.search(r"\bin\s+(.+?)\s*um\b", text, re.I)
    if treffer:
        return treffer.group(1).strip(" .!?\"'")
    treffer = re.search(r"\bum\s*(?:in|auf)?\s*(.+)$", text, re.I)
    return treffer.group(1).strip(" .!?\"'") if treffer else ""


def _menue_zeigen(z: dict[str, Any]) -> dict[str, Any]:
    if z.get("art") == "lieder":
        return {"antwort": menue_lieder(z), "tastatur": menue_tastatur_lieder(z),
                "bereich": "playlist", "bearbeiten": True}
    if z.get("art") == "listenwahl":
        return {"antwort": "Welche Wiedergabeliste soll es sein?",
                "tastatur": menue_tastatur_listen(z["listen"]),
                "bereich": "playlist", "bearbeiten": True}
    return {"antwort": "Die Auswahl ist abgelaufen. Fang bitte neu an.", "bereich": "playlist"}


@router.post("/playlist/knopf")
def playlist_knopf(knopf: Knopf) -> dict[str, Any]:
    chat = knopf.chatId
    daten = str(knopf.daten or "")
    z = _frisch(chat)

    if daten == "px":
        ZUSTAND.pop(chat, None)
        # Nach dem Anlegen heisst der Knopf "Genug" - dann ist nichts abzubrechen.
        antwort = ("\U0001f44d Alles klar, \u201e" + str(z["name"]) + "\u201c bleibt gespeichert."
                   if z.get("art") == "fertig" and z.get("name") else "Abgebrochen.")
        return {"antwort": antwort, "bearbeiten": True, "tastatur": {"inline_keyboard": []},
                "bereich": "playlist"}

    if daten == "v":
        pid = z.get("pid")
        if not pid:
            return {"antwort": "Die Auswahl ist abgelaufen. Fang bitte neu an.",
                    "bereich": "playlist"}
        ZUSTAND.pop(chat, None)
        ok, meldung = liste_abspielen(int(pid))
        return {"antwort": ("\u25b6\ufe0f " if ok else "\u26a0\ufe0f ") + meldung,
                "bearbeiten": True, "tastatur": {"inline_keyboard": []}, "bereich": "playlist"}

    if z.get("art") == "bestaetigung" and daten in ("j", "n"):
        ZUSTAND.pop(chat, None)
        if daten == "n":
            return {"antwort": "Dann nicht.", "bearbeiten": True,
                    "tastatur": {"inline_keyboard": []}, "bereich": "playlist"}
        if z["was"] == "leeren":
            ok = liste_leeren(int(z["pid"]))
            return {"antwort": f"\U0001f9f9 \u201e{z['name']}\u201c ist geleert." if ok
                    else "\u26a0\ufe0f Leeren hat nicht geklappt.",
                    "bearbeiten": True, "tastatur": {"inline_keyboard": []}, "bereich": "playlist"}
        ok = liste_loeschen(int(z["pid"]))
        return {"antwort": f"\U0001f5d1\ufe0f \u201e{z['name']}\u201c ist geloescht." if ok
                else "\u26a0\ufe0f Loeschen hat nicht geklappt.",
                "bearbeiten": True, "tastatur": {"inline_keyboard": []}, "bereich": "playlist"}

    if z.get("art") == "listenwahl" and re.fullmatch(r"l\d{1,2}", daten):
        i = int(daten[1:]) - 1
        liste_gewaehlt = (z.get("listen") or [])[i] if i < len(z.get("listen") or []) else None
        if not liste_gewaehlt:
            return {"antwort": "Diese Nummer gibt es nicht mehr.", "bearbeiten": True,
                    "tastatur": {"inline_keyboard": []}, "bereich": "playlist"}
        danach = z.get("danach")
        ZUSTAND.pop(chat, None)
        if danach and danach != "abspielen":
            antwort = _weitere_aktion(chat, danach, liste_gewaehlt, {"text": ""})
            if z.get("kriterium"):
                antwort = _weitere_aktion(chat, danach, liste_gewaehlt, {"kriterium": z["kriterium"]})
            antwort["bearbeiten"] = True
            return antwort
        ok, meldung = liste_abspielen(int(liste_gewaehlt["id"]))
        return {"antwort": ("\u25b6\ufe0f " if ok else "\u26a0\ufe0f ") + meldung,
                "bearbeiten": True, "tastatur": {"inline_keyboard": []}, "bereich": "playlist"}

    if z.get("art") != "lieder":
        return {"antwort": "Die Auswahl ist abgelaufen. Fang bitte neu an.", "bereich": "playlist"}

    if daten == "pa":
        for k in z["kandidaten"]:
            k["gewaehlt"] = True
    elif daten == "pk":
        for k in z["kandidaten"]:
            k["gewaehlt"] = False
    elif re.fullmatch(r"p\d{1,2}", daten):
        i = int(daten[1:]) - 1
        if i < len(z["kandidaten"]):
            z["kandidaten"][i]["gewaehlt"] = not z["kandidaten"][i]["gewaehlt"]
    elif daten == "pf":
        gewaehlt = [k["pfad"] for k in z["kandidaten"] if k["gewaehlt"]]
        if not gewaehlt:
            return {"antwort": "Es ist kein Titel ausgewaehlt.", "bearbeiten": True,
                    "tastatur": menue_tastatur_lieder(z), "bereich": "playlist"}
        name = z.get("name") or "Neue Liste"
        pid = z.get("pid")
        if pid:                                   # bestehende Liste ergaenzen
            ok, meldung = liste_ergaenzen(int(pid), gewaehlt)
            antwort = (f"\u2705 {len(gewaehlt)} Titel zu \u201e{name}\u201c hinzugefuegt."
                       if ok else f"\u26a0\ufe0f {meldung}")
        else:                                     # neue Liste anlegen und fuellen
            try:
                datensatz = liste_anlegen(name, gewaehlt)
                pid = datensatz.get("id")
                antwort = (f"\u2705 Wiedergabeliste \u201e{name}\u201c mit "
                           f"{len(gewaehlt)} Titeln angelegt.")
            except HTTPException as fehler:
                return {"antwort": f"\u26a0\ufe0f {fehler.detail}", "bearbeiten": True,
                        "tastatur": menue_tastatur_lieder(z), "bereich": "playlist"}
        ZUSTAND[chat] = {"art": "fertig", "pid": pid, "name": name}
        if z.get("danach_spielen") and pid:
            ZUSTAND.pop(chat, None)
            ok, meldung = liste_abspielen(int(pid))
            return {"antwort": antwort + "\n" + ("\u25b6\ufe0f " if ok else "\u26a0\ufe0f ")
                    + meldung, "bearbeiten": True, "tastatur": {"inline_keyboard": []},
                    "bereich": "playlist"}
        return {"antwort": antwort + "\n\nSoll sie gleich laufen?", "bearbeiten": True,
                "tastatur": {"inline_keyboard": [[
                    {"text": "\u25b6\ufe0f Jetzt abspielen", "callback_data": "v"},
                    {"text": "\U0001f44d Genug", "callback_data": "px"}]]},
                "bereich": "playlist"}

    return _menue_zeigen(z)


@router.post("/playlist/vorschlag")
def playlist_vorschlag(daten: Befehl) -> dict[str, Any]:
    """Kandidaten zu einem Suchbegriff (fuer die Auswahl im Bot)."""
    return {"kandidaten": kandidaten(daten.text)}


@router.get("/playlist/status")
def playlist_status() -> dict[str, Any]:
    return {"offene_auswahlen": len(ZUSTAND), "liste": list(ZUSTAND.keys())[:5],
            "senderschnittstelle": AZ_URL, "app": "playlist"}
