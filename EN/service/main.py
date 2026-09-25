"""Radio-TTS — German speech output for the radio moderator.

Provides the OpenAI-compatible interface /v1/audio/speech so n8n (and
other tools) can use the same call format as against Kokoro/OpenAI.

Custom voices: a Piper voice consists of two files
    <name>.onnx  and  <name>.onnx.json
Place both into /voices — it is immediately available under its file name and (if
entered below as a short name) under the short name. This also lets
self-trained voices be integrated later.
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

# Own moderation voice "deine-stimme": created by the voice service on the GPU machine
# (edge-tts + RVC, CT 111 port 10205 — setup see Ai_Radio_Moderator_Bot/
# VOICE.md). If it is not reachable, the service speaks with EIGENE_STIMME_ERSATZ
# (default de_thorsten) — an announcement should not fail because the
# GPU machine is busy right now.
EIGENE_URL = os.environ.get("EIGENE_STIMME_URL", "http://192.168.178.116:10205/tts")
EIGENE_NAME = os.environ.get("EIGENE_STIMME_NAME", "deine-stimme")
# Generous: generation runs about 1.6x faster than real time (measured
# 2026-09-23: 77 s audio in 48 s). A roundup with several minutes of speech time
# therefore needs a few minutes — only afterwards does the fallback kick in.
EIGENE_ZEITABLAUF = float(os.environ.get("EIGENE_STIMME_ZEITABLAUF", "600"))
EIGENE_STIMME_ERSATZ = os.environ.get("EIGENE_STIMME_ERSATZ", "de_thorsten")

# --------------------------------------------------------------- Loudness
# Piper delivers full peaks (measured -0.3 dBFS), but a large gap between
# peak and RMS (-16.2 dBFS, speech pauses and soft consonants).
# The music program is hard-limited in contrast (-9.8 LUFS) — the announcement sounded
# about 6 dB too quiet because of that. Remedy: remove lows, raise to a target level,
# hold peaks with a limiter (all in 16-bit PCM, without ffmpeg).
ZIEL_RMS_DB = float(os.environ.get("TTS_ZIEL_RMS_DB", "-11.5"))
MAX_ANHEBUNG_DB = float(os.environ.get("TTS_MAX_ANHEBUNG_DB", "14"))
BEGRENZER_DB = float(os.environ.get("TTS_BEGRENZER_DB", "-1.0"))
# Limiter release time: keep it short! At 120 ms it lowered the following syllables
# after every peak (the announcement did not get louder because of that).
BEGRENZER_FREIGABE_MS = float(os.environ.get("TTS_BEGRENZER_FREIGABE_MS", "40"))
HOCHPASS_HZ = float(os.environ.get("TTS_HOCHPASS_HZ", "80"))
# Compress before the limiter: speech has ~16 dB between peak and
# RMS, the music program only ~10 dB. Without compression the
# limiter would have to engage constantly (sounded dull and still did not get louder).
KOMPRESSOR_SCHWELLE_DB = float(os.environ.get("TTS_KOMPRESSOR_SCHWELLE_DB", "-19"))
KOMPRESSOR_VERHAELTNIS = float(os.environ.get("TTS_KOMPRESSOR_VERHAELTNIS", "3.0"))

# Short name -> file name of the voice (without .onnx)
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
_lesesperre = threading.Lock()  # PiperVoice is not thread-safe


# ---------------------------------------------------------------- Finding voices


def stimmdateien() -> list[Path]:
    if not VOICE_DIR.is_dir():
        return []
    return sorted(VOICE_DIR.glob("*.onnx"))


def stimmpfad(name: str) -> Path:
    """Short name or file name -> path to the .onnx file."""
    if not name:
        name = STANDARD_STIMME
    name = KURZNAMEN.get(name, name)
    p = VOICE_DIR / f"{name}.onnx"
    if p.is_file():
        return p
    # Tolerate names given without extension, and upper/lower case
    for kandidat in stimmdateien():
        if kandidat.stem.lower() == name.lower():
            return kandidat
    raise HTTPException(
        status_code=400,
        detail=f"Voice ’{name}’ not found. Available: "
        + ", ".join(sorted({EIGENE_NAME, *KURZNAMEN, *(p.stem for p in stimmdateien())})),
    )


def ist_eigene_stimme(name: str) -> bool:
    """Is this the short name of the external moderation voice? (case-insensitive)"""
    return (name or "").strip().lower() == EIGENE_NAME.strip().lower()


def lade_stimme(name: str) -> PiperVoice:
    p = stimmpfad(name)
    with _lesesperre:
        voice = _stimmen.get(str(p))
        if voice is None:
            konfig = Path(str(p) + ".json")
            voice = PiperVoice.load(p, config_path=konfig if konfig.is_file() else None)
            _stimmen[str(p)] = voice
        return voice


def stimmenliste() -> list[dict[str, Any]]:
    vorhanden = {p.stem for p in stimmdateien()}
    output: list[dict[str, Any]] = [
        {
            "id": EIGENE_NAME,
            "file": "sprechdienst (RVC, external)",
            "vorhanden": True,
            "alias_fuer": None,
            "extern": EIGENE_URL,
        }
    ]
    for short, file in sorted(KURZNAMEN.items()):
        output.append(
            {
                "id": short,
                "file": file,
                "vorhanden": file in vorhanden,
                "alias_fuer": file,
            }
        )
    for file in sorted(vorhanden - set(KURZNAMEN.values())):
        output.append({"id": file, "file": file, "vorhanden": True, "alias_fuer": None})
    return output


# ------------------------------------------------------------------- Output


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
        raw = w.readframes(w.getnframes())
    if breite != 2:
        raise ValueError("only 16-bit WAV")
    pcm = array.array("h")
    pcm.frombytes(raw)
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
    """Fine tuning from the environment (LIVE_LAUTSTAERKE_DB), default 0."""
    try:
        return float(os.environ.get("LIVE_LAUTSTAERKE_DB", "0") or 0)
    except ValueError:
        return 0.0


def _sprech_rms(pcm: array.array, rate: int, kanaele: int) -> float:
    """RMS of the speaking sections (50 ms window, silence does not count)."""
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
    threshold = max(max(pegeln) * 10 ** (-40 / 20), 10 ** (-50 / 20))
    sprechend = [p for p in pegeln if p >= threshold]
    if not sprechend:
        return 0.0
    return math.sqrt(sum(p * p for p in sprechend) / len(sprechend))


def _verdichten(pcm: array.array, rate: int) -> array.array:
    """Lowers loud parts (3:1 above KOMPRESSOR_SCHWELLE_DB) and then raises the level.

    The envelope sine is smooth (10 ms); the clamp grips in 5 ms and
    releases in 80 ms — the usual range for speech. Result is
    a smaller gap between peak and RMS, i.e. more loudness
    at the same peak.
    """
    n = len(pcm)
    out = array.array("h", [0] * n)
    huell_tau = math.exp(-1.0 / max(rate * 0.010, 1.0))
    angriff = math.exp(-1.0 / max(rate * 0.005, 1.0))
    freigabe = math.exp(-1.0 / max(rate * 0.080, 1.0))
    ratio = max(KOMPRESSOR_VERHAELTNIS, 1.0)
    huelle = 0.0
    griff = 1.0
    for i in range(n):
        x = pcm[i] / 32768.0
        huelle = math.sqrt(huell_tau * huelle * huelle + (1.0 - huell_tau) * x * x)
        pegel_db = 20.0 * math.log10(huelle) if huelle > 1e-6 else -120.0
        over = pegel_db - KOMPRESSOR_SCHWELLE_DB
        target = 1.0 if over <= 0 else 10 ** (-over * (1.0 - 1.0 / ratio) / 20.0)
        griff = (angriff * griff + (1.0 - angriff) * target) if target < griff \
            else (freigabe * griff + (1.0 - freigabe) * target)
        y = x * griff
        out[i] = int(max(-1.0, min(1.0, y)) * 32767)
    return out


def _begrenzen(basis: array.array, rate: int, verstaerkung: float) -> tuple[array.array, float]:
    """Amplifies and limits with look-ahead. Returns PCM and peak (linear).

    The gain already drops 3 ms BEFORE a peak (running minimum looking
    ahead) and is released over 120 ms afterwards. This keeps the peak safely
    below BEGRENZER_DB without hard clipping the speech.
    """
    from collections import deque

    decke = 10 ** (BEGRENZER_DB / 20)
    lead = max(int(rate * 0.003), 1)
    n = len(basis)
    raw = [1.0] * n
    for i in range(n):
        v = abs(basis[i]) / 32768.0 * verstaerkung
        raw[i] = 1.0 if v <= decke else decke / v

    # Running minimum over [i, i+lead] — computed from the back so the
    # gain drops BEFORE the peak. Important: always compare with
    # the raw values (raw), write into target — otherwise the queue computes
    # with already smoothed values and lowers the level far too much.
    target = [1.0] * n
    schlange: deque[int] = deque()
    for i in range(n - 1, -1, -1):
        while schlange and raw[schlange[-1]] >= raw[i]:
            schlange.pop()
        schlange.append(i)
        while schlange[0] > i + lead:
            schlange.popleft()
        target[i] = raw[schlange[0]]

    freigabe = math.exp(-1.0 / max(rate * BEGRENZER_FREIGABE_MS / 1000.0, 1.0))
    out = array.array("h", [0] * n)
    griff = 1.0
    spitze = 0.0
    for i in range(n):
        g = target[i]
        griff = g if g < griff else freigabe * griff + (1.0 - freigabe) * g
        y = basis[i] / 32768.0 * verstaerkung * griff
        if y > 1.0:
            y = 1.0
        elif y < -1.0:
            y = -1.0
        if abs(y) > spitze:
            spitze = abs(y)
        out[i] = int(y * 32767)
    return out, spitze


def lautstaerke_anpassen(wav_daten: bytes, zusatz_db: float = 0.0) -> bytes:
    """Raises the voice to broadcast level and limits the peaks.

    Measured on 2026-09-20: music -9.8 LUFS, voice -16.2 LUFS — at full peak
    (0 dBFS). Simple amplification was therefore not possible. Hence this
    order: remove lows (headroom), compress (peak distance), raise the level
    to the target, limit peaks with look-ahead. The level is re-adjusted
    because the limiter takes some back (up to four passes, stop at
    0.3 dB deviation).
    """
    try:
        pcm, rate, kanaele = _wav_als_pcm(wav_daten)
    except Exception:
        return wav_daten
    if len(pcm) < 100 or rate <= 0:
        return wav_daten

    # 1) Remove lows — only costs headroom and makes the speech clearer.
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

    # 2) Compress — shrink the peak distance (brings the actual loudness).
    pcm = _verdichten(pcm, rate)
    ziel_db = ZIEL_RMS_DB + zusatz_db
    ist_db = 20 * math.log10(_sprech_rms(pcm, rate, kanaele) or 1e-9)
    if ist_db < -60:
        return _pcm_als_wav(pcm, rate, kanaele)

    extra = max(0.0, min(ziel_db - ist_db, MAX_ANHEBUNG_DB))
    bester: tuple[float, array.array] | None = None
    for _ in range(4):
        kandidat, _ = _begrenzen(pcm, rate, 10 ** (extra / 20))
        erreicht = 20 * math.log10(_sprech_rms(kandidat, rate, kanaele) or 1e-9)
        if bester is None or abs(erreicht - ziel_db) < abs(bester[0] - ziel_db):
            bester = (erreicht, kandidat)
        if abs(erreicht - ziel_db) <= 0.3:
            break
        extra = max(0.0, min(extra + (ziel_db - erreicht), MAX_ANHEBUNG_DB + 6))
    return _pcm_als_wav((bester or (ist_db, pcm))[1], rate, kanaele)


def verpacke_audio(wav_daten: bytes, format_: str) -> tuple[bytes, str]:
    """Deliver the finished WAV: unchanged or encoded as MP3."""
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
    # lameenc returns bytearray — Starlette needs bytes
    mp3 = bytes(kodierer.encode(pcm)) + bytes(kodierer.flush())
    return mp3, "audio/mpeg"


def erzeuge_audio(text: str, voice: PiperVoice, speed: float, format_: str) -> tuple[bytes, str]:
    syn_konfig = None
    if abs(speed - 1.0) > 0.01:
        try:
            from piper.config import SynthesisConfig

            syn_konfig = SynthesisConfig(length_scale=1.0 / speed)
        except Exception:  # different Piper version -> ignore the speed
            syn_konfig = None

    puffer = io.BytesIO()
    with wave.open(puffer, "wb") as wav_datei:
        voice.synthesize_wav(text, wav_datei, syn_config=syn_konfig)
    wav_daten = lautstaerke_anpassen(puffer.getvalue(), zusatz_verstaerkung_db())
    return verpacke_audio(wav_daten, format_)


def erzeuge_audio_eigene(text: str, speed: float, format_: str) -> tuple[bytes, str]:
    """Speaks via the external voice service (edge-tts + RVC, CT 111:10205)."""
    body: dict[str, Any] = {"text": text}
    if abs(speed - 1.0) > 0.01:
        # Map Piper's 'speed' to the percentage of the voice service
        # (1.2 = +20 %). Without a value, the configured tempo applies there (+40 %).
        body["rate"] = f"{round((speed - 1.0) * 100):+d}%"
    body = json.dumps(body, ensure_ascii=False).encode("utf-8")
    zerlegt = urlsplit(EIGENE_URL)
    verbindung = http.client.HTTPConnection(
        zerlegt.hostname, zerlegt.port or 80, timeout=EIGENE_ZEITABLAUF
    )
    try:
        verbindung.request(
            "POST",
            zerlegt.path or "/tts",
            body=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        answer = verbindung.getresponse()
        data = answer.read()
        status = answer.status
    finally:
        verbindung.close()
    if status != 200 or not data:
        raise HTTPException(
            status_code=502,
            detail=f"Voice service {EIGENE_URL} responds with HTTP {status}.",
        )
    wav_daten = lautstaerke_anpassen(data, zusatz_verstaerkung_db())
    return verpacke_audio(wav_daten, format_)


def erzeuge_audio_gewaehlt(text: str, voice: str, speed: float,
                           format_: str) -> tuple[bytes, str, str]:
    """Chooses the voice and returns (audio, media type, voice used).

    'deine-stimme' runs externally (voice service); everything else are Piper voices.
    If the voice service is unreachable, EIGENE_STIMME_ERSATZ is used (default
    de_thorsten) — the announcement then does not fail; the log mentions it.
    """
    chosen = (voice or STANDARD_STIMME).strip()
    if "deine-stimme" in chosen.lower():  # spellings like "own voice" count as a request
        chosen = EIGENE_NAME
    # Make visible in the log which voice is speaking - this answers the
    # question "why is your own voice no longer coming?" (operator 2026-09-25).
    print(f"Voice: {chosen}", flush=True)
    if not ist_eigene_stimme(chosen):
        voice = lade_stimme(chosen)
        with _lesesperre:
            data, typ = erzeuge_audio(text, voice, speed, format_)
        return data, typ, chosen
    try:
        data, typ = erzeuge_audio_eigene(text, speed, format_)
        return data, typ, chosen
    except Exception as error:  # noqa: BLE001 - fallback instead of failure
        ersatz = (EIGENE_STIMME_ERSATZ or "").strip()
        if not ersatz or ist_eigene_stimme(ersatz):
            if isinstance(error, HTTPException):
                raise
            raise HTTPException(
                status_code=502,
                detail=f"Voice service {EIGENE_URL} unreachable: {error}",
            ) from error
        print(f"your voice unreachable ({error}) — substitute voice: {ersatz}", flush=True)
        voice = lade_stimme(ersatz)
        with _lesesperre:
            data, typ = erzeuge_audio(text, voice, speed, format_)
        return data, typ, ersatz


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "stimmen_verzeichnis": str(VOICE_DIR),
        "voices": len(stimmdateien()),
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
def speech(request: SprachAnfrage) -> Response:
    text = (request.input or request.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text provided (field ‘input’).")

    format_ = (request.response_format or "mp3").lower()
    if format_ not in {"mp3", "wav"}:
        raise HTTPException(status_code=400, detail="response_format must be ‘mp3’ or ‘wav’.")

    gewuenscht = (request.voice or STANDARD_STIMME).strip()
    data, typ, used = erzeuge_audio_gewaehlt(text, request.voice, request.speed, format_)

    kopfzeilen = {
        "Content-Disposition": f'inline; filename="announcement.{format_}"',
        "X-voice": used,
    }
    if used.lower() != gewuenscht.lower():
        kopfzeilen["X-voice-Ersatz"] = "1"
    return Response(content=data, media_type=typ, headers=kopfzeilen)


# ------------------------------------------------------- Live into the station


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
    # Lead-in silence: Liquidsoap only switches the harbor through after a few seconds
    # and discards the seconds sent first. Without this silence
    # the first sentence of the announcement is missing.
    silence: float = Field(default=5.5, ge=0.0, le=20.0)
    # Tail silence: catches the cut-off when switching back.
    schweigen_ende: float = Field(default=1.5, ge=0.0, le=20.0)


def schweigen_anhaengen(wav_daten: bytes, vorne: float, hinten: float) -> bytes:
    """Puts silence before and/or after a WAV file."""
    if vorne <= 0 and hinten <= 0:
        return wav_daten
    with wave.open(io.BytesIO(wav_daten), "rb") as w:
        parameter = w.getparams()
        frames = w.readframes(w.getnframes())
    je_sekunde = parameter.framerate * parameter.nchannels * parameter.sampwidth
    still_vorn = b"\x00" * int(je_sekunde * vorne)
    still_hinten = b"\x00" * int(je_sekunde * hinten)
    puffer = io.BytesIO()
    with wave.open(puffer, "wb") as w:
        w.setparams(parameter)
        w.writeframes(still_vorn + frames + still_hinten)
    return puffer.getvalue()


def mp3_stuecke(wav_daten: bytes, rate: float = 0.2) -> list[bytes]:
    """Converts WAV into MP3 chunks of 'rate' seconds each (for the broadcast timing)."""
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
    schritt = max(int(bytes_je_sekunde * rate), 4096)
    stuecke: list[bytes] = []
    for pos in range(0, len(pcm), schritt):
        stueck = bytes(kodierer.encode(pcm[pos : pos + schritt]))
        if stueck:
            stuecke.append(stueck)
    stuecke.append(bytes(kodierer.flush()))
    return [s for s in stuecke if s]


@app.post("/live")
def live(request: LiveAnfrage) -> dict[str, Any]:
    """Speaks the text live into the station right away (DJ channel), in broadcast timing.

    Broadcasting in time is important: Liquidsoap only buffers ~10 seconds at the harbor.
    If the file is uploaded in one go, Liquidsoap discards the rest
    ("Generator max buffered length exceeded").
    """
    text = (request.input or request.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text provided (field ‘input’).")
    if not request.host or not request.user or not request.password:
        raise HTTPException(
            status_code=400,
            detail="host, user and password must be set (or LIVE_* variables).",
        )

    wav_daten, _, used = erzeuge_audio_gewaehlt(text, request.voice, request.speed, "wav")
    wav_daten = schweigen_anhaengen(wav_daten, request.silence, request.schweigen_ende)
    stuecke = mp3_stuecke(wav_daten)
    total = sum(len(s) for s in stuecke)

    identifier = base64.b64encode(f"{request.user}:{request.password}".encode()).decode()
    verbindung = http.client.HTTPConnection(request.host, request.port, timeout=300)
    try:
        verbindung.putrequest("PUT", request.mount or "/", skip_accept_encoding=True)
        for name, wert in {
            "Authorization": f"Basic {identifier}",
            "Content-Type": "audio/mpeg",
            "Content-Length": str(total),
            "Ice-Name": request.name,
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
            # Liquidsoap only answers when closing — wait briefly,
            # so the call does not block for 30 seconds.
            if verbindung.sock is not None:
                verbindung.sock.settimeout(2.0)
            answer = verbindung.getresponse()
            status = answer.status
            answer.read()
        except Exception:  # Source finished — Liquidsoap does not always answer
            status = 0
    finally:
        verbindung.close()

    return {
        "ok": True,
        "spoken": text,
        "voice": used,
        "mp3_bytes": total,
        "duration_seconds": round(total / (128_000 / 8), 1),
        "hafen_antwort": status,
    }


# --- Catalog: fuzzy search and genre suggestions (see catalog.py) ---------
try:
    from katalog import (  # type: ignore
        katalog_aktualisieren,
        katalog_laden,
        katalog_status,
        router as katalog_router,
    )

    app.include_router(katalog_router)

    def _katalog_beim_start() -> None:
        """Load the catalog and refresh it if needed (missing or older than 7 days)."""
        try:
            katalog_laden()
            stand = katalog_status()
            if stand["count"] == 0 and os.environ.get("KATALOG_BEI_START", "1") != "0":
                print("Catalog is being built (takes about 30 s) ...", flush=True)
                katalog_aktualisieren()
                print("Catalog ready:", katalog_status(), flush=True)
        except Exception as error:  # noqa: BLE001
            print("Catalog build failed:", error, flush=True)

    threading.Thread(target=_katalog_beim_start, daemon=True).start()
except Exception as error:  # noqa: BLE001
    print("Catalog module not loaded:", error, flush=True)


# --- More modules with their own addresses -------------------------------
# Each module brings its own router: playlist.py (playlists),
# news.py (inbox for the search bot and the moderation). A new module
# only needs an entry in this list and a COPY line in the Dockerfile.
for _modul, _name in (("playlist", "playlist module"), ("news", "news module"),
                       ("search", "Recherche-Modul")):
    try:
        _importiert = __import__(_modul)
        app.include_router(_importiert.router)
        print(f"{_name} loaded", flush=True)
    except Exception as _fehler:  # noqa: BLE001
        print(f"{_name} not loaded:", _fehler, flush=True)
