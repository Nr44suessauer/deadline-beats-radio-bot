#!/usr/bin/env python3
"""speech-service.py — Text -> YOUR-VOICE-voice (edge-tts-Basis + RVC-Modell, Tonhoehe einstellbar).

HTTP:
 POST /tts     {"text": "...", "pitch": 4}   -> WAV (22050 Hz, mono, 16 Bit)
 GET  /health

The RVC model is loaded ONCE and reused (~1-3 s per announcement).
start: see speech-service.service (in CT 111).
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if "/opt/Applio" not in sys.path:
    sys.path.insert(0, "/opt/Applio")
os.chdir("/opt/Applio")

RVC_PTH = os.environ.get("RVC_PTH", "/opt/Applio/logs/deine-stimme2/deine-stimme2_300e_3300s.pth")
RVC_INDEX = os.environ.get("RVC_INDEX", "/opt/Applio/logs/deine-stimme2/deine-stimme2.index")
RVC_PITCH = int(os.environ.get("RVC_PITCH", "4"))
RVC_F0 = os.environ.get("RVC_F0", "rmvpe")
RVC_INDEX_RATE = float(os.environ.get("RVC_INDEX_RATE", "0.5"))
RVC_PROTECT = float(os.environ.get("RVC_PROTECT", "0.5"))
RVC_EMBEDDER = os.environ.get("RVC_EMBEDDER", "contentvec")
BASIS_STIMME = os.environ.get("BASIS_STIMME", "de-DE-AmalaNeural")
BASIS_RATE = os.environ.get("BASIS_RATE", "+20%")          # Speech rate of the base (e.g. +20%)
HTTP_PORT = int(os.environ.get("HTTP_PORT", "10205"))
OUTPUT_RATE = int(os.environ.get("OUTPUT_RATE", "22050"))

_sperre = threading.Lock()
_conv = None


def hole_conv():
    global _conv
    if _conv is None:
        from rvc.infer.infer import VoiceConverter
        _conv = VoiceConverter()
    return _conv


def edge_sprechen(text, voice, rate=None):
    """Text -> MP3 via edge-tts (as in Applio-TTS)."""
    import edge_tts
    tempo = rate or BASIS_RATE

    async def _lauf():
        data = b""
        async for st in edge_tts.Communicate(text, voice, rate=tempo).stream():
            if st["type"] == "audio":
                data += st["data"]
        return data

    return asyncio.run(_lauf())


def synthese(text, pitch=None, index_rate=None, rate=None, protect=None, basis=None):
    mp3 = edge_sprechen(text, basis or BASIS_STIMME, rate)
    tmp = tempfile.mkdtemp(prefix="sprechdienst-")
    input, out, target = (os.path.join(tmp, n) for n in ("input.wav", "out.wav", "target.wav"))
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", "pipe:0",
                        "-ar", "40000", "-ac", "1", "-c:a", "pcm_s16le", input],
                       input=mp3, check=True, timeout=120)
        with _sperre:
            hole_conv().convert_audio(
                audio_input_path=input, audio_output_path=out,
                model_path=RVC_PTH, index_path=RVC_INDEX,
                pitch=RVC_PITCH if pitch is None else int(pitch),
                f0_method=RVC_F0,
                index_rate=RVC_INDEX_RATE if index_rate is None else float(index_rate),
                protect=RVC_PROTECT if protect is None else float(protect),
                embedder_model=RVC_EMBEDDER, export_format="WAV")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", out,
                        "-ar", str(OUTPUT_RATE), "-ac", "1", "-c:a", "pcm_s16le", target],
                       check=True, timeout=120)
        with open(target, "rb") as f:
            return f.read()
    finally:
        # After each announcement return the CUDA intermediate memory: the card is
        # shared with Ollama, so the next service gets the reserve (OOM protection).
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001 - Cleanup must never interfere
            pass
        for p in (input, out, target):
            try:
                os.unlink(p)
            except OSError:
                pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, status, obj):
        d = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(d)))
        self.end_headers()
        self.wfile.write(d)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"ok": True, "model": RVC_PTH, "pitch": RVC_PITCH,
                             "basis": BASIS_STIMME, "tempo": BASIS_RATE,
                             "index_rate": RVC_INDEX_RATE, "protect": RVC_PROTECT})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/tts":
            return self._json(404, {"error": "not found. POST /tts"})
        n = int(self.headers.get("Content-Length", "0") or 0)
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._json(400, {"error": "JSON not readable"})
        text = (data.get("text") or "").strip()
        if not text:
            return self._json(400, {"error": "text missing"})
        try:
            wav = synthese(text, data.get("pitch"), data.get("index_rate"), data.get("rate"),
                           data.get("protect"), data.get("basis"))
        except Exception as e:
            traceback.print_exc()
            return self._json(500, {"error": str(e)[:300]})
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(wav)))
        self.end_headers()
        self.wfile.write(wav)


if __name__ == "__main__":
    print(f"sprechdienst Port {HTTP_PORT} | {RVC_PTH} | pitch {RVC_PITCH} | Basis {BASIS_STIMME}",
          flush=True)
    ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), Handler).serve_forever()
