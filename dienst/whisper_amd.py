#!/usr/bin/env python3
"""
whisper_amd.py — Bruecke fuer den STT-Dienst auf der MI50 (Container 112 "whisper-amd").

Bietet dieselbe Schnittstelle wie whisper_server.py auf CT 105, damit der Radiobot
nur die Adresse tauschen muss:

  POST /transcribe   (multipart/form-data oder roher Koerper)
    file      - Audiodatei (ogg/opus von Telegram, mp3, m4a, wav ...)
    language  - Sprachkuerzel, Vorgabe "de"; "auto" schaltet die Erkennung frei
    prompt    - optionaler Fachhinweis (Eigennamen)
  -> {"text": "...", "language": "de"}

  GET /health -> Zustand des Dienstes und des whisper.cpp-Servers

Ablauf je Anfrage:
  1) ffmpeg wandelt die Datei in 16-kHz-Mono-WAV (whisper.cpp liest nur WAV;
     Telegram liefert OGG/Opus).
  2) Die WAV-Datei geht an den whisper.cpp-Server (Modell large-v3, Vulkan auf der
     Radeon Instinct MI50) auf 127.0.0.1:8081/inference.

Start:   python3 whisper_amd.py --port 8000
Systemd: whisper-bruecke.service (davor laeuft whisper-cpp.service)
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import traceback
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CPP_URL = os.environ.get("WHISPER_CPP_URL", "http://127.0.0.1:8081/inference")
FFMPEG = os.environ.get("WHISPER_FFMPEG", "ffmpeg")
BEAM = os.environ.get("WHISPER_BEAM", "5")


def _zerlege_multipart(body: bytes, boundary: str):
    """Audio und Textfelder aus dem Multipart-Koerper holen.

    Rueckgabe: (audio_bytes|None, {feldname: wert}) — gleiche Logik wie
    whisper_server.py auf CT 105.
    """
    audio = None
    felder = {}
    for teil in body.split(boundary.encode()):
        idx = teil.find(b"\r\n\r\n")
        trenner = b"\r\n\r\n"
        if idx < 0:
            idx = teil.find(b"\n\n")
            trenner = b"\n\n"
        if idx < 0:
            continue
        kopf = teil[:idx]
        inhalt = teil[idx + len(trenner):]
        while inhalt.endswith((b"\r\n", b"\n")):
            inhalt = inhalt[:-2] if inhalt.endswith(b"\r\n") else inhalt[:-1]
        if inhalt.endswith(b"--"):
            inhalt = inhalt[:-2]

        if b"filename=" in kopf and audio is None:
            audio = inhalt
            continue
        name = None
        for zeile in kopf.split(b"\r\n"):
            if zeile.lower().startswith(b"content-disposition") and b'name="' in zeile:
                name = zeile.split(b'name="', 1)[1].split(b'"', 1)[0].decode("utf-8", "ignore")
        if name:
            felder[name] = inhalt.decode("utf-8", "ignore")
    return audio, felder


def _hole_text(daten):
    """Text aus der Antwort des whisper.cpp-Servers ziehen (json oder Liste)."""
    if isinstance(daten, dict):
        return str(daten.get("text") or "")
    if isinstance(daten, list) and daten and isinstance(daten[0], dict):
        return str(daten[0].get("text") or "")
    return ""


def _an_cpp(wav_pfad: str, sprache, hinweis):
    """WAV an whisper.cpp (Vulkan) schicken. Rueckgabe: Text."""
    rand = "----whisperamd" + uuid.uuid4().hex
    teile = []

    def feld(name: str, wert: str):
        teile.append(
            (f'--{rand}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
             + wert + "\r\n").encode("utf-8"))

    def datei(name: str, pfad: str):
        kopf = (f'--{rand}\r\nContent-Disposition: form-data; name="{name}"; '
                f'filename="audio.wav"\r\nContent-Type: audio/wav\r\n\r\n').encode("utf-8")
        with open(pfad, "rb") as f:
            teile.append(kopf + f.read() + b"\r\n")

    datei("file", wav_pfad)
    feld("response_format", "json")
    feld("temperature", "0.0")
    feld("beam_size", BEAM)
    if sprache:
        feld("language", sprache)
    if hinweis:
        feld("prompt", hinweis)
    koerper = b"".join(teile) + f"--{rand}--\r\n".encode("utf-8")

    anfrage = urllib.request.Request(
        CPP_URL, data=koerper,
        headers={"Content-Type": f"multipart/form-data; boundary={rand}"},
        method="POST")
    with urllib.request.urlopen(anfrage, timeout=600) as antwort:
        rohdaten = antwort.read()
    try:
        daten = json.loads(rohdaten.decode("utf-8", "ignore"))
    except json.JSONDecodeError:
        raise RuntimeError(f"whisper.cpp antwortete unlesbar: {rohdaten[:200]!r}")
    return _hole_text(daten)


def _nach_wav(quelldatei: str, zieldatei: str):
    """ffmpeg: beliebiges Format -> 16 kHz Mono WAV (wie es whisper.cpp erwartet)."""
    befehl = [FFMPEG, "-y", "-loglevel", "error", "-i", quelldatei,
              "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", "-f", "wav", zieldatei]
    ergebnis = subprocess.run(befehl, capture_output=True, timeout=120)
    if ergebnis.returncode != 0:
        meldung = ergebnis.stderr.decode("utf-8", "ignore").strip()[:300]
        raise RuntimeError(f"ffmpeg: {meldung}")


class WhisperHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"[whisper-amd] {self.client_address[0]} → {fmt % args}", flush=True)

    def _send_json(self, status: int, daten: dict):
        body = json.dumps(daten, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            zustand = {"status": "ok", "engine": "whisper.cpp", "backend": "Vulkan (MI50)"}
            try:
                with urllib.request.urlopen(CPP_URL.replace("/inference", "/health"),
                                            timeout=3) as antwort:
                    zustand["cpp_server"] = json.loads(antwort.read().decode("utf-8", "ignore"))
            except Exception as e:
                zustand["cpp_server"] = f"nicht erreichbar: {e}"
            self._send_json(200, zustand)
        else:
            self._send_json(404, {"error": "not found. Use POST /transcribe"})

    def do_POST(self):
        if self.path != "/transcribe":
            self._send_json(404, {"error": f"unknown endpoint: {self.path}"})
            return

        content_type = self.headers.get("Content-Type", "")
        felder = {}
        if "multipart/form-data" not in content_type:
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                self._send_json(400, {"error": "empty body"})
                return
            audio_daten = self.rfile.read(length)
        else:
            boundary = None
            for teil in content_type.split(";"):
                teil = teil.strip()
                if teil.startswith("boundary="):
                    boundary = teil[len("boundary="):].strip('"')
            if not boundary:
                self._send_json(400, {"error": "no boundary in multipart"})
                return
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            audio_daten, felder = _zerlege_multipart(body, boundary)
            if audio_daten is None:
                self._send_json(400, {"error": "no audio file part found in multipart"})
                return

        if len(audio_daten) < 100:
            self._send_json(400, {"error": "audio too short"})
            return

        sprache = (felder.get("language") or "de").strip().lower()
        if sprache in ("", "auto", "none", "null"):
            sprache = None
        hinweis = (felder.get("prompt") or "").strip() or None

        quelldatei = zieldatei = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as f:
                f.write(audio_daten)
                quelldatei = f.name
            zieldatei = quelldatei + ".wav"
            _nach_wav(quelldatei, zieldatei)
            print(f"[whisper-amd] Transcribing {len(audio_daten)} bytes (lang={sprache}) ...",
                  flush=True)
            text = _an_cpp(zieldatei, sprache, hinweis)
            print(f"[whisper-amd] Done: {text[:100]!r}", flush=True)
            self._send_json(200, {"text": text, "language": sprache or "auto"})
        except Exception as e:
            print(f"[whisper-amd] Error: {e}", file=sys.stderr)
            traceback.print_exc()
            self._send_json(500, {"error": str(e)})
        finally:
            for pfad in (quelldatei, zieldatei):
                if pfad:
                    try:
                        os.unlink(pfad)
                    except OSError:
                        pass


def main():
    parser = argparse.ArgumentParser(description="Whisper-Bruecke (whisper.cpp + Vulkan, MI50)")
    parser.add_argument("--port", type=int, default=8000, help="Listen port")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Bind address")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), WhisperHandler)
    print(f"[whisper-amd] Listening on http://{args.host}:{args.port}", flush=True)
    print(f"[whisper-amd] whisper.cpp: {CPP_URL}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[whisper-amd] Shutting down.", flush=True)
        server.shutdown()


if __name__ == "__main__":
    main()
