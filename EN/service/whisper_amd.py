#!/usr/bin/env python3
"""
whisper_amd.py — Bridge for the STT service on the MI50 (Container 112 "whisper-amd").

Provides the same interface as whisper_server.py on CT 105, so that the Radiobot
only needs to exchange the address:

 POST /transcribe   (multipart/form-data or raw body)
 file      - Audio file (ogg/opus from Telegram, mp3, m4a, wav ...)
 language  - Language code, default "de"; "auto" enables detection
 prompt    - optional domain-specific hint (proper names)
 -> {"text": "...", "language": "de"}

 GET /health -> Status of the service and the whisper.cpp server

Process per request:
 1) ffmpeg converts the file to 16-kHz-Mono-WAV (whisper.cpp only reads WAV;
 Telegram provides OGG/Opus).
 2) The WAV file is sent to the whisper.cpp server (model large-v3, Vulkan on the
 Radeon Instinct MI50) at 127.0.0.1:8081/inference.

start:   python3 whisper_amd.py --port 8000
Systemd: whisper-bruecke.service (before whisper-cpp.service was running)
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
    """Retrieve audio and text fields from the Multipart body.

 Return: (audio_bytes|None, {feldname: wert}) — same logic as
 whisper_server.py on CT 105.
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


def _hole_text(data):
    """Extract text from the response of the whisper.cpp server (json or list)."""
    if isinstance(data, dict):
        return str(data.get("text") or "")
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return str(data[0].get("text") or "")
    return ""


def _an_cpp(wav_pfad: str, voice, hint):
    """Send WAV to whisper.cpp (Vulkan). Return: Text."""
    margin = "----whisperamd" + uuid.uuid4().hex
    teile = []

    def feld(name: str, wert: str):
        teile.append(
            (f'--{margin}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
             + wert + "\r\n").encode("utf-8"))

    def file(name: str, path: str):
        kopf = (f'--{margin}\r\nContent-Disposition: form-data; name="{name}";'
                f'filename="audio.wav"\r\nContent-Type: audio/wav\r\n\r\n').encode("utf-8")
        with open(path, "rb") as f:
            teile.append(kopf + f.read() + b"\r\n")

    file("file", wav_pfad)
    feld("response_format", "json")
    feld("temperature", "0.0")
    feld("beam_size", BEAM)
    if voice:
        feld("language", voice)
    if hint:
        feld("prompt", hint)
    body = b"".join(teile) + f"--{margin}--\r\n".encode("utf-8")

    request = urllib.request.Request(
        CPP_URL, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={margin}"},
        method="POST")
    with urllib.request.urlopen(request, timeout=600) as answer:
        rohdaten = answer.read()
    try:
        data = json.loads(rohdaten.decode("utf-8", "ignore"))
    except json.JSONDecodeError:
        raise RuntimeError(f"whisper.cpp responded unreadable: {rohdaten[:200]!r}")
    return _hole_text(data)


def _nach_wav(quelldatei: str, zieldatei: str):
    """ffmpeg: any format -> 16 kHz Mono WAV (as expected by whisper.cpp)."""
    command = [FFMPEG, "-y", "-loglevel", "error", "-i", quelldatei,
              "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", "-f", "wav", zieldatei]
    result = subprocess.run(command, capture_output=True, timeout=120)
    if result.returncode != 0:
        news = result.stderr.decode("utf-8", "ignore").strip()[:300]
        raise RuntimeError(f"ffmpeg: {news}")


class WhisperHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"[whisper-amd] {self.client_address[0]} → {fmt % args}", flush=True)

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
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
            state = {"status": "ok", "engine": "whisper.cpp", "backend": "Vulkan (MI50)"}
            try:
                with urllib.request.urlopen(CPP_URL.replace("/inference", "/health"),
                                            timeout=3) as answer:
                    state["cpp_server"] = json.loads(answer.read().decode("utf-8", "ignore"))
            except Exception as e:
                state["cpp_server"] = f"not reachable: {e}"
            self._send_json(200, state)
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

        voice = (felder.get("language") or "de").strip().lower()
        if voice in ("", "auto", "none", "null"):
            voice = None
        hint = (felder.get("prompt") or "").strip() or None

        quelldatei = zieldatei = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as f:
                f.write(audio_daten)
                quelldatei = f.name
            zieldatei = quelldatei + ".wav"
            _nach_wav(quelldatei, zieldatei)
            print(f"[whisper-amd] Transcribing {len(audio_daten)} bytes (lang={voice}) ...",
                  flush=True)
            text = _an_cpp(zieldatei, voice, hint)
            print(f"[whisper-amd] Done: {text[:100]!r}", flush=True)
            self._send_json(200, {"text": text, "language": voice or "auto"})
        except Exception as e:
            print(f"[whisper-amd] Error: {e}", file=sys.stderr)
            traceback.print_exc()
            self._send_json(500, {"error": str(e)})
        finally:
            for path in (quelldatei, zieldatei):
                if path:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass


def main():
    parser = argparse.ArgumentParser(description="Whisper Bridge (whisper.cpp + Vulkan, MI50)")
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
