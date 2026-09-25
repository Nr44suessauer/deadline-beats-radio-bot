"""Radio-TTS - deutsche Sprachausgabe fuer den Radio-Moderator.

Bietet die OpenAI-kompatible Schnittstelle /v1/audio/speech, damit n8n (und
andere Werkzeuge) dieselbe Aufrufform wie gegen Kokoro/OpenAI verwenden koennen.

Eigene Stimmen: eine Piper-Stimme besteht aus zwei Dateien
    <name>.onnx  und  <name>.onnx.json
Beide nach /voices legen - sie steht sofort unter ihrem Dateinamen und (falls
unten als Kurzname eingetragen) unter dem Kurznamen zur Verfuegung. Damit lassen
sich spaeter auch selbst trainierte Stimmen einbinden.
"""

from __future__ import annotations

import array
import base64
import http.client
import io
import json
import math
import os
import threading
import time
import wave
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from piper.voice import PiperVoice
from pydantic import BaseModel, Field

VOICE_DIR = Path(os.environ.get("VOICE_DIR", "/voices"))
STANDARD_STIMME = os.environ.get("TTS_DEFAULT_VOICE", "de_thorsten")

# Eigene Moderationsstimme "deine-stimme": erzeugt der Stimmendienst auf der GPU-Maschine
# (edge-tts + RVC, CT 111 Port 10205 - Aufbau siehe Ai_Radio_Moderator_Bot/
# STIMME.md). Ist er nicht erreichbar, spricht der Dienst mit EIGENE_STIMME_ERSATZ
# weiter (Standard de_thorsten) - eine Ansage soll nicht ausfallen, weil die
# GPU-Maschine gerade beschaeftigt ist.
EIGENE_URL = os.environ.get("EIGENE_STIMME_URL", "http://192.168.178.116:10205/tts")
EIGENE_NAME = os.environ.get("EIGENE_STIMME_NAME", "deine-stimme")
# Grosszuegig: die Erzeugung laeuft etwa 1,6x schneller als Echtzeit (gemessen
# 2026-09-23: 77 s Audio in 48 s). Ein Ueberblick mit mehreren Minuten Sprechzeit
# braucht daher einige Minuten - erst danach greift der Ersatzweg.
EIGENE_ZEITABLAUF = float(os.environ.get("EIGENE_STIMME_ZEITABLAUF", "600"))
EIGENE_STIMME_ERSATZ = os.environ.get("EIGENE_STIMME_ERSATZ", "de_thorsten")

# --------------------------------------------------------------- Lautstaerke
# Piper liefert volle Spitzen (gemessen -0,3 dBFS), aber viel Abstand zwischen
# Spitze und Effektivwert (-16,2 dBFS, Sprechpausen und weiche Konsonanten).
# Das Musikprogramm ist dagegen hart begrenzt (-9,8 LUFS) - die Ansage klang
# dadurch rund 6 dB zu leise. Ausgleich: Tiefen weg, auf einen Zielpegel
# anheben, Spitzen mit einem Begrenzer halten (alles in 16-Bit-PCM, ohne ffmpeg).
ZIEL_RMS_DB = float(os.environ.get("TTS_ZIEL_RMS_DB", "-11.5"))
MAX_ANHEBUNG_DB = float(os.environ.get("TTS_MAX_ANHEBUNG_DB", "14"))
BEGRENZER_DB = float(os.environ.get("TTS_BEGRENZER_DB", "-1.0"))
# Freigabezeit des Begrenzers: kurz halten! Bei 120 ms senkte er nach jeder Spitze
# noch die folgenden Silben (die Ansage wurde dadurch nicht lauter).
BEGRENZER_FREIGABE_MS = float(os.environ.get("TTS_BEGRENZER_FREIGABE_MS", "40"))
HOCHPASS_HZ = float(os.environ.get("TTS_HOCHPASS_HZ", "80"))
# Vor dem Begrenzer verdichten: Sprache hat ~16 dB Abstand zwischen Spitze und
# Effektivwert, das Musikprogramm nur ~10 dB. Ohne Verdichtung muesste der
# Begrenzer staendig eingreifen (klang dumpf und wurde trotzdem nicht lauter).
KOMPRESSOR_SCHWELLE_DB = float(os.environ.get("TTS_KOMPRESSOR_SCHWELLE_DB", "-19"))
KOMPRESSOR_VERHAELTNIS = float(os.environ.get("TTS_KOMPRESSOR_VERHAELTNIS", "3.0"))

# Kurzname -> Dateiname der Stimme (ohne .onnx)
KURZNAMEN: dict[str, str] = {
    "de_thorsten": "de_DE-thorsten-medium",
    "de_kerstin": "de_DE-kerstin-low",
    "de_eva": "de_DE-eva_k-x_low",
    "de_ramona": "de_DE-ramona-low",
    "de_karlsson": "de_DE-karlsson-low",
    "de_martin": "de_DE-martin-low",
    "de_pavoque": "de_DE-pavoque-low",
    "en_lessac": "en_US-lessac-medium",
}

app = FastAPI(title="Radio-TTS", version="1.0")

_stimmen: dict[str, PiperVoice] = {}
_lesesperre = threading.Lock()  # PiperVoice ist nicht thread-sicher


# ---------------------------------------------------------------- Stimmen finden


def stimmdateien() -> list[Path]:
    if not VOICE_DIR.is_dir():
        return []
    return sorted(VOICE_DIR.glob("*.onnx"))


def stimmpfad(name: str) -> Path:
    """Kurzname oder Dateiname -> Pfad zur .onnx-Datei."""
    if not name:
        name = STANDARD_STIMME
    name = KURZNAMEN.get(name, name)
    p = VOICE_DIR / f"{name}.onnx"
    if p.is_file():
        return p
    # Ohne Endung uebergebene Namen und Gross-/Kleinschreibung tolerieren
    for kandidat in stimmdateien():
        if kandidat.stem.lower() == name.lower():
            return kandidat
    raise HTTPException(
        status_code=400,
        detail=f"Stimme '{name}' nicht gefunden. Verfuegbar: "
        + ", ".join(sorted({EIGENE_NAME, *KURZNAMEN, *(p.stem for p in stimmdateien())})),
    )


def ist_eigene_stimme(name: str) -> bool:
    """Ist das der Kurzname der externen Moderationsstimme? (Gross/Klein egal)"""
    return (name or "").strip().lower() == EIGENE_NAME.strip().lower()


def lade_stimme(name: str) -> PiperVoice:
    p = stimmpfad(name)
    with _lesesperre:
        stimme = _stimmen.get(str(p))
        if stimme is None:
            konfig = Path(str(p) + ".json")
            stimme = PiperVoice.load(p, config_path=konfig if konfig.is_file() else None)
            _stimmen[str(p)] = stimme
        return stimme


def stimmenliste() -> list[dict[str, Any]]:
    vorhanden = {p.stem for p in stimmdateien()}
    ausgabe: list[dict[str, Any]] = [
        {
            "id": EIGENE_NAME,
            "datei": "sprechdienst (RVC, extern)",
            "vorhanden": True,
            "alias_fuer": None,
            "extern": EIGENE_URL,
        }
    ]
    for kurz, datei in sorted(KURZNAMEN.items()):
        ausgabe.append(
            {
                "id": kurz,
                "datei": datei,
                "vorhanden": datei in vorhanden,
                "alias_fuer": datei,
            }
        )
    for datei in sorted(vorhanden - set(KURZNAMEN.values())):
        ausgabe.append({"id": datei, "datei": datei, "vorhanden": True, "alias_fuer": None})
    return ausgabe


# ------------------------------------------------------------------- Ausgabe


class SprachAnfrage(BaseModel):
    input: str | None = None
    text: str | None = None
    voice: str = ""
    model: str | None = None
    response_format: str = "mp3"
    speed: float = Field(default=1.0, ge=0.3, le=3.0)


def _wav_als_pcm(wav_daten: bytes) -> tuple[array.array, int, int]:
    with wave.open(io.BytesIO(wav_daten), "rb") as w:
        rate = w.getframerate()
        kanaele = w.getnchannels()
        breite = w.getsampwidth()
        roh = w.readframes(w.getnframes())
    if breite != 2:
        raise ValueError("nur 16-Bit-WAV")
    pcm = array.array("h")
    pcm.frombytes(roh)
    return pcm, rate, kanaele


def _pcm_als_wav(pcm: array.array, rate: int, kanaele: int) -> bytes:
    puffer = io.BytesIO()
    with wave.open(puffer, "wb") as w:
        w.setnchannels(kanaele)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return puffer.getvalue()


def zusatz_verstaerkung_db() -> float:
    """Feinabstimmung aus der Umgebung (LIVE_LAUTSTAERKE_DB), Standard 0."""
    try:
        return float(os.environ.get("LIVE_LAUTSTAERKE_DB", "0") or 0)
    except ValueError:
        return 0.0


def _sprech_rms(pcm: array.array, rate: int, kanaele: int) -> float:
    """Effektivwert der sprechenden Abschnitte (50-ms-Fenster, Stille zaehlt nicht)."""
    fenster = max(int(rate * 0.05), 1) * kanaele
    if len(pcm) < fenster:
        return 0.0
    pegeln: list[float] = []
    for start in range(0, len(pcm) - fenster + 1, fenster):
        summe = 0.0
        for i in range(start, start + fenster):
            v = pcm[i] / 32768.0
            summe += v * v
        pegeln.append(math.sqrt(summe / fenster))
    if not pegeln:
        return 0.0
    schwelle = max(max(pegeln) * 10 ** (-40 / 20), 10 ** (-50 / 20))
    sprechend = [p for p in pegeln if p >= schwelle]
    if not sprechend:
        return 0.0
    return math.sqrt(sum(p * p for p in sprechend) / len(sprechend))


def _verdichten(pcm: array.array, rate: int) -> array.array:
    """Senkt laute Stellen ab (3:1 ab KOMPRESSOR_SCHWELLE_DB) und hebt danach an.

    Der Sinus der Huellkurve ist weich (10 ms), der Griff greift in 5 ms und
    gibt in 80 ms frei - das ist der uebliche Bereich fuer Sprache. Ergebnis ist
    ein kleinerer Abstand zwischen Spitze und Effektivwert, also mehr Lautheit
    bei gleicher Spitze.
    """
    n = len(pcm)
    aus = array.array("h", [0] * n)
    huell_tau = math.exp(-1.0 / max(rate * 0.010, 1.0))
    angriff = math.exp(-1.0 / max(rate * 0.005, 1.0))
    freigabe = math.exp(-1.0 / max(rate * 0.080, 1.0))
    verhaeltnis = max(KOMPRESSOR_VERHAELTNIS, 1.0)
    huelle = 0.0
    griff = 1.0
    for i in range(n):
        x = pcm[i] / 32768.0
        huelle = math.sqrt(huell_tau * huelle * huelle + (1.0 - huell_tau) * x * x)
        pegel_db = 20.0 * math.log10(huelle) if huelle > 1e-6 else -120.0
        ueber = pegel_db - KOMPRESSOR_SCHWELLE_DB
        ziel = 1.0 if ueber <= 0 else 10 ** (-ueber * (1.0 - 1.0 / verhaeltnis) / 20.0)
        griff = (angriff * griff + (1.0 - angriff) * ziel) if ziel < griff \
            else (freigabe * griff + (1.0 - freigabe) * ziel)
        y = x * griff
        aus[i] = int(max(-1.0, min(1.0, y)) * 32767)
    return aus


def _begrenzen(basis: array.array, rate: int, verstaerkung: float) -> tuple[array.array, float]:
    """Verstaerkt und begrenzt mit Vorausschau. Gibt PCM und Spitze (linear) zurueck.

    Die Verstaerkung sinkt schon 3 ms VOR einer Spitze (gleitendes Minimum nach
    vorn) und wird danach in 120 ms freigegeben. Damit bleibt die Spitze sicher
    unter BEGRENZER_DB, ohne dass die Sprache hart abschneidet.
    """
    from collections import deque

    decke = 10 ** (BEGRENZER_DB / 20)
    vorlauf = max(int(rate * 0.003), 1)
    n = len(basis)
    roh = [1.0] * n
    for i in range(n):
        v = abs(basis[i]) / 32768.0 * verstaerkung
        roh[i] = 1.0 if v <= decke else decke / v

    # Gleitendes Minimum ueber [i, i+vorlauf] - von hinten gerechnet, damit die
    # Verstaerkung schon VOR der Spitze sinkt. Wichtig: verglichen wird immer mit
    # den rohen Werten (roh), geschrieben in ziel - sonst rechnet die Warteschlange
    # mit bereits geglaetteten Werten und senkt den Pegel viel zu stark.
    ziel = [1.0] * n
    schlange: deque[int] = deque()
    for i in range(n - 1, -1, -1):
        while schlange and roh[schlange[-1]] >= roh[i]:
            schlange.pop()
        schlange.append(i)
        while schlange[0] > i + vorlauf:
            schlange.popleft()
        ziel[i] = roh[schlange[0]]

    freigabe = math.exp(-1.0 / max(rate * BEGRENZER_FREIGABE_MS / 1000.0, 1.0))
    aus = array.array("h", [0] * n)
    griff = 1.0
    spitze = 0.0
    for i in range(n):
        g = ziel[i]
        griff = g if g < griff else freigabe * griff + (1.0 - freigabe) * g
        y = basis[i] / 32768.0 * verstaerkung * griff
        if y > 1.0:
            y = 1.0
        elif y < -1.0:
            y = -1.0
        if abs(y) > spitze:
            spitze = abs(y)
        aus[i] = int(y * 32767)
    return aus, spitze


def lautstaerke_anpassen(wav_daten: bytes, zusatz_db: float = 0.0) -> bytes:
    """Hebt die Stimme auf Sendeniveau und begrenzt die Spitzen.

    Gemessen am 2026-09-20: Musik -9,8 LUFS, Stimme -16,2 LUFS - bei voller Spitze
    (0 dBFS). Einfaches Verstaerken war also nicht moeglich. Deshalb in dieser
    Reihenfolge: Tiefen weg (Kopfraum), verdichten (Spitzenabstand), Pegel auf das
    Ziel heben, Spitzen mit Vorausschau begrenzen. Der Pegel wird nachgeregelt,
    weil der Begrenzer wieder etwas wegnimmt (bis zu vier Durchgaenge, Abbruch bei
    0,3 dB Abweichung).
    """
    try:
        pcm, rate, kanaele = _wav_als_pcm(wav_daten)
    except Exception:
        return wav_daten
    if len(pcm) < 100 or rate <= 0:
        return wav_daten

    # 1) Tiefen weg - kostet nur Kopfraum und macht die Sprache klarer.
    if HOCHPASS_HZ > 0:
        a = math.exp(-2.0 * math.pi * HOCHPASS_HZ / rate)
        for k in range(kanaele):
            x_vor = 0.0
            y_vor = 0.0
            for i in range(k, len(pcm), kanaele):
                x = pcm[i] / 32768.0
                y = a * (y_vor + x - x_vor)
                x_vor, y_vor = x, y
                pcm[i] = int(max(-1.0, min(1.0, y)) * 32767)

    # 2) Verdichten - Spitzenabstand verkleinern (bringt die eigentliche Lautheit).
    pcm = _verdichten(pcm, rate)
    ziel_db = ZIEL_RMS_DB + zusatz_db
    ist_db = 20 * math.log10(_sprech_rms(pcm, rate, kanaele) or 1e-9)
    if ist_db < -60:
        return _pcm_als_wav(pcm, rate, kanaele)

    zusatz = max(0.0, min(ziel_db - ist_db, MAX_ANHEBUNG_DB))
    bester: tuple[float, array.array] | None = None
    for _ in range(4):
        kandidat, _ = _begrenzen(pcm, rate, 10 ** (zusatz / 20))
        erreicht = 20 * math.log10(_sprech_rms(kandidat, rate, kanaele) or 1e-9)
        if bester is None or abs(erreicht - ziel_db) < abs(bester[0] - ziel_db):
            bester = (erreicht, kandidat)
        if abs(erreicht - ziel_db) <= 0.3:
            break
        zusatz = max(0.0, min(zusatz + (ziel_db - erreicht), MAX_ANHEBUNG_DB + 6))
    return _pcm_als_wav((bester or (ist_db, pcm))[1], rate, kanaele)


def verpacke_audio(wav_daten: bytes, format_: str) -> tuple[bytes, str]:
    """Fertiges WAV ausliefern: unveraendert oder als MP3 kodieren."""
    if format_ == "wav":
        return wav_daten, "audio/wav"

    with wave.open(io.BytesIO(wav_daten), "rb") as w:
        pcm = w.readframes(w.getnframes())
        kanaele = w.getnchannels()
        rate = w.getframerate()

    import lameenc

    kodierer = lameenc.Encoder()
    kodierer.set_bit_rate(128)
    kodierer.set_in_sample_rate(rate)
    kodierer.set_channels(kanaele)
    kodierer.set_quality(2)
    # lameenc liefert bytearray - Starlette braucht bytes
    mp3 = bytes(kodierer.encode(pcm)) + bytes(kodierer.flush())
    return mp3, "audio/mpeg"


def erzeuge_audio(text: str, stimme: PiperVoice, speed: float, format_: str) -> tuple[bytes, str]:
    syn_konfig = None
    if abs(speed - 1.0) > 0.01:
        try:
            from piper.config import SynthesisConfig

            syn_konfig = SynthesisConfig(length_scale=1.0 / speed)
        except Exception:  # andere Piper-Fassung -> Geschwindigkeit ignorieren
            syn_konfig = None

    puffer = io.BytesIO()
    with wave.open(puffer, "wb") as wav_datei:
        stimme.synthesize_wav(text, wav_datei, syn_config=syn_konfig)
    wav_daten = lautstaerke_anpassen(puffer.getvalue(), zusatz_verstaerkung_db())
    return verpacke_audio(wav_daten, format_)


def erzeuge_audio_eigene(text: str, speed: float, format_: str) -> tuple[bytes, str]:
    """Spricht ueber den externen Stimmendienst (edge-tts + RVC, CT 111:10205)."""
    koerper: dict[str, Any] = {"text": text}
    if abs(speed - 1.0) > 0.01:
        # Piper-'speed' auf die Prozentangabe des Stimmendienstes abbilden
        # (1.2 = +20 %). Ohne Angabe gilt dort das eingestellte Tempo (+40 %).
        koerper["rate"] = f"{round((speed - 1.0) * 100):+d}%"
    rumpf = json.dumps(koerper, ensure_ascii=False).encode("utf-8")
    zerlegt = urlsplit(EIGENE_URL)
    verbindung = http.client.HTTPConnection(
        zerlegt.hostname, zerlegt.port or 80, timeout=EIGENE_ZEITABLAUF
    )
    try:
        verbindung.request(
            "POST",
            zerlegt.path or "/tts",
            body=rumpf,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        antwort = verbindung.getresponse()
        daten = antwort.read()
        status = antwort.status
    finally:
        verbindung.close()
    if status != 200 or not daten:
        raise HTTPException(
            status_code=502,
            detail=f"Stimmendienst {EIGENE_URL} antwortet mit HTTP {status}.",
        )
    wav_daten = lautstaerke_anpassen(daten, zusatz_verstaerkung_db())
    return verpacke_audio(wav_daten, format_)


def erzeuge_audio_gewaehlt(text: str, voice: str, speed: float,
                           format_: str) -> tuple[bytes, str, str]:
    """Waehlt die Stimme und liefert (Audio, Medientyp, genutzte Stimme).

    'deine-stimme' laeuft extern (Stimmendienst); alles andere sind Piper-Stimmen.
    Ist der Stimmendienst nicht erreichbar, wird EIGENE_STIMME_ERSATZ genommen (Standard
    de_thorsten) - die Ansage faellt dann nicht aus, im Protokoll steht es.
    """
    gewaehlt = (voice or STANDARD_STIMME).strip()
    if "deine-stimme" in gewaehlt.lower():  # auch "eigene Stimme" u. Ae. zaehlt als Wunsch
        gewaehlt = EIGENE_NAME
    # Im Protokoll sichtbar machen, welche Stimme spricht - daran haengt die
    # Frage "warum kommt nicht mehr die eigene Stimme?" (Betreiber 2026-09-25).
    print(f"Stimme: {gewaehlt}", flush=True)
    if not ist_eigene_stimme(gewaehlt):
        stimme = lade_stimme(gewaehlt)
        with _lesesperre:
            daten, typ = erzeuge_audio(text, stimme, speed, format_)
        return daten, typ, gewaehlt
    try:
        daten, typ = erzeuge_audio_eigene(text, speed, format_)
        return daten, typ, gewaehlt
    except Exception as fehler:  # noqa: BLE001 - Ersatzweg statt Ausfall
        ersatz = (EIGENE_STIMME_ERSATZ or "").strip()
        if not ersatz or ist_eigene_stimme(ersatz):
            if isinstance(fehler, HTTPException):
                raise
            raise HTTPException(
                status_code=502,
                detail=f"Stimmendienst {EIGENE_URL} nicht erreichbar: {fehler}",
            ) from fehler
        print(f"Eigene Stimme nicht erreichbar ({fehler}) - Ersatzstimme: {ersatz}", flush=True)
        stimme = lade_stimme(ersatz)
        with _lesesperre:
            daten, typ = erzeuge_audio(text, stimme, speed, format_)
        return daten, typ, ersatz


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "stimmen_verzeichnis": str(VOICE_DIR),
        "stimmen": len(stimmdateien()),
        "standard": STANDARD_STIMME,
        "deine-stimme": {"name": EIGENE_NAME, "url": EIGENE_URL, "ersatz": EIGENE_STIMME_ERSATZ},
    }


@app.get("/v1/audio/voices")
def voices() -> dict[str, Any]:
    return {"voices": stimmenliste()}


@app.get("/v1/models")
def models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [{"id": "piper", "object": "model", "owned_by": "radio-tts"}],
    }


@app.post("/v1/audio/speech")
def speech(anfrage: SprachAnfrage) -> Response:
    text = (anfrage.input or anfrage.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Kein Text uebergeben (Feld 'input').")

    format_ = (anfrage.response_format or "mp3").lower()
    if format_ not in {"mp3", "wav"}:
        raise HTTPException(status_code=400, detail="response_format muss 'mp3' oder 'wav' sein.")

    gewuenscht = (anfrage.voice or STANDARD_STIMME).strip()
    daten, typ, genutzt = erzeuge_audio_gewaehlt(text, anfrage.voice, anfrage.speed, format_)

    kopfzeilen = {
        "Content-Disposition": f'inline; filename="ansage.{format_}"',
        "X-Stimme": genutzt,
    }
    if genutzt.lower() != gewuenscht.lower():
        kopfzeilen["X-Stimme-Ersatz"] = "1"
    return Response(content=daten, media_type=typ, headers=kopfzeilen)


# ------------------------------------------------------- Live in den Sender


class LiveAnfrage(BaseModel):
    input: str | None = None
    text: str | None = None
    voice: str = ""
    speed: float = Field(default=1.0, ge=0.3, le=3.0)
    host: str = os.environ.get("LIVE_HOST", "")
    port: int = int(os.environ.get("LIVE_PORT", "8005"))
    mount: str = os.environ.get("LIVE_MOUNT", "/")
    user: str = os.environ.get("LIVE_USER", "")
    password: str = os.environ.get("LIVE_PASSWORD", "")
    name: str = "Deadline Beats Moderation"
    # Vorlauf-Stille: Liquidsoap schaltet den Hafen erst nach ein paar Sekunden
    # durch und verwirft dabei die zuerst gesendeten Sekunden. Ohne diese Stille
    # fehlt der erste Satz der Ansage.
    schweigen: float = Field(default=5.5, ge=0.0, le=20.0)
    # Nachlauf-Stille: faengt das Abschneiden beim Zurueckschalten ab.
    schweigen_ende: float = Field(default=1.5, ge=0.0, le=20.0)


def schweigen_anhaengen(wav_daten: bytes, vorne: float, hinten: float) -> bytes:
    """Legt Stille vor und/oder hinter eine WAV-Datei."""
    if vorne <= 0 and hinten <= 0:
        return wav_daten
    with wave.open(io.BytesIO(wav_daten), "rb") as w:
        parameter = w.getparams()
        rahmen = w.readframes(w.getnframes())
    je_sekunde = parameter.framerate * parameter.nchannels * parameter.sampwidth
    still_vorn = b"\x00" * int(je_sekunde * vorne)
    still_hinten = b"\x00" * int(je_sekunde * hinten)
    puffer = io.BytesIO()
    with wave.open(puffer, "wb") as w:
        w.setparams(parameter)
        w.writeframes(still_vorn + rahmen + still_hinten)
    return puffer.getvalue()


def mp3_stuecke(wav_daten: bytes, takt: float = 0.2) -> list[bytes]:
    """Wandelt WAV in MP3-Stuecke von je 'takt' Sekunden (fuer den Sendetakt)."""
    import lameenc

    with wave.open(io.BytesIO(wav_daten), "rb") as w:
        pcm = w.readframes(w.getnframes())
        kanaele = w.getnchannels()
        rate = w.getframerate()

    kodierer = lameenc.Encoder()
    kodierer.set_bit_rate(128)
    kodierer.set_in_sample_rate(rate)
    kodierer.set_channels(kanaele)
    kodierer.set_quality(2)

    bytes_je_sekunde = rate * kanaele * 2  # 16 Bit
    schritt = max(int(bytes_je_sekunde * takt), 4096)
    stuecke: list[bytes] = []
    for pos in range(0, len(pcm), schritt):
        stueck = bytes(kodierer.encode(pcm[pos : pos + schritt]))
        if stueck:
            stuecke.append(stueck)
    stuecke.append(bytes(kodierer.flush()))
    return [s for s in stuecke if s]


@app.post("/live")
def live(anfrage: LiveAnfrage) -> dict[str, Any]:
    """Spricht den Text sofort live in den Sender (DJ-Kanal) und zwar im Sendetakt.

    Das Senden im Takt ist wichtig: Liquidsoap puffert am Hafen nur ~10 Sekunden.
    Wird die Datei in einem Rutsch hochgeladen, verwirft Liquidsoap den Rest
    ("Generator max buffered length exceeded").
    """
    text = (anfrage.input or anfrage.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Kein Text uebergeben (Feld 'input').")
    if not anfrage.host or not anfrage.user or not anfrage.password:
        raise HTTPException(
            status_code=400,
            detail="host, user und password muessen gesetzt sein (oder LIVE_* Variablen).",
        )

    wav_daten, _, genutzt = erzeuge_audio_gewaehlt(text, anfrage.voice, anfrage.speed, "wav")
    wav_daten = schweigen_anhaengen(wav_daten, anfrage.schweigen, anfrage.schweigen_ende)
    stuecke = mp3_stuecke(wav_daten)
    gesamt = sum(len(s) for s in stuecke)

    kennung = base64.b64encode(f"{anfrage.user}:{anfrage.password}".encode()).decode()
    verbindung = http.client.HTTPConnection(anfrage.host, anfrage.port, timeout=300)
    try:
        verbindung.putrequest("PUT", anfrage.mount or "/", skip_accept_encoding=True)
        for name, wert in {
            "Authorization": f"Basic {kennung}",
            "Content-Type": "audio/mpeg",
            "Content-Length": str(gesamt),
            "Ice-Name": anfrage.name,
            "Ice-Public": "0",
            "User-Agent": "Radio-TTS/1.0",
        }.items():
            verbindung.putheader(name, wert)
        verbindung.endheaders()

        start = time.monotonic()
        gesendet = 0
        bytes_je_sekunde = 128_000 / 8  # 128 kbit/s
        for stueck in stuecke:
            verbindung.send(stueck)
            gesendet += len(stueck)
            wartezeit = (gesendet / bytes_je_sekunde) - (time.monotonic() - start)
            if wartezeit > 0:
                time.sleep(wartezeit)

        try:
            # Liquidsoap antwortet erst beim Schliessen - kurz darauf warten,
            # damit der Aufruf nicht 30 Sekunden blockiert.
            if verbindung.sock is not None:
                verbindung.sock.settimeout(2.0)
            antwort = verbindung.getresponse()
            status = antwort.status
            antwort.read()
        except Exception:  # Quelle beendet - Liquidsoap antwortet nicht immer
            status = 0
    finally:
        verbindung.close()

    return {
        "ok": True,
        "gesprochen": text,
        "stimme": genutzt,
        "mp3_bytes": gesamt,
        "dauer_sekunden": round(gesamt / (128_000 / 8), 1),
        "hafen_antwort": status,
    }


# --- Katalog: unscharfe Suche und Genre-Vorschlaege (siehe katalog.py) ---------
try:
    from katalog import (  # type: ignore
        katalog_aktualisieren,
        katalog_laden,
        katalog_status,
        router as katalog_router,
    )

    app.include_router(katalog_router)

    def _katalog_beim_start() -> None:
        """Katalog laden und bei Bedarf (fehlend oder aelter als 7 Tage) neu holen."""
        try:
            katalog_laden()
            stand = katalog_status()
            if stand["anzahl"] == 0 and os.environ.get("KATALOG_BEI_START", "1") != "0":
                print("Katalog wird aufgebaut (das dauert etwa 30 s) ...", flush=True)
                katalog_aktualisieren()
                print("Katalog fertig:", katalog_status(), flush=True)
        except Exception as fehler:  # noqa: BLE001
            print("Katalog-Aufbau fehlgeschlagen:", fehler, flush=True)

    threading.Thread(target=_katalog_beim_start, daemon=True).start()
except Exception as fehler:  # noqa: BLE001
    print("Katalog-Modul nicht eingebunden:", fehler, flush=True)


# --- Weitere Module mit eigenen Adressen -------------------------------------
# Jedes Modul bringt einen eigenen Router mit: playlist.py (Wiedergabelisten),
# meldungen.py (Postfach fuer den Suchbot und die Moderation). Ein neues Modul
# braucht nur einen Eintrag in dieser Liste und eine COPY-Zeile im Dockerfile.
for _modul, _name in (("playlist", "Listen-Modul"), ("meldungen", "Meldungs-Modul"),
                       ("suche", "Recherche-Modul")):
    try:
        _importiert = __import__(_modul)
        app.include_router(_importiert.router)
        print(f"{_name} eingebunden", flush=True)
    except Exception as _fehler:  # noqa: BLE001
        print(f"{_name} nicht eingebunden:", _fehler, flush=True)
