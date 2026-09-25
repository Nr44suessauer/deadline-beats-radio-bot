#!/usr/bin/env python3
"""
whisper_server.py — Minimal HTTP server providing STT via faster-whisper on GPU.

Deployed on CT105 (RTX 3090 Ti, 192.168.178.187:18790).
Receives audio via POST /transcribe (multipart/form-data or raw body) and returns
{"text": "...", "language": "..."}.

Form fields (all optional):
  file      - the audio file (also accepts a raw body)
  language  - language code, default "de" (this house speaks German); "auto" detects
  prompt    - domain hint text: proper nouns (artist names) are recognised far
              better when they appear in the hint

Start:
  python3 whisper_server.py --port 18790 --model large-v3
Systemd service: /etc/systemd/system/whisper-stt.service

Requires: pip install faster-whisper
"""

import argparse
import json
import os
import sys
import tempfile
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler

# Lazy-load whisper to keep startup fast
_whisper_model = None
_whisper_device = "cuda"
_whisper_compute = "auto"


def _load_model(model_name: str):
    global _whisper_model, _whisper_device, _whisper_compute
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("[whisper] faster-whisper not installed. Install: pip install faster-whisper",
              file=sys.stderr)
        return False

    # Detect CUDA via ctranslate2 (faster-whisper's backend — no torch needed)
    try:
        import ctranslate2
        _whisper_device = "cuda"
        _whisper_compute = "int8_float16"
        print("[whisper] CUDA device available via ctranslate2", flush=True)
    except Exception:
        _whisper_device = "cpu"
        _whisper_compute = "int8"

    print(f"[whisper] Loading model '{model_name}' on {_whisper_device} "
          f"(compute={_whisper_compute}) ...", flush=True)
    try:
        _whisper_model = WhisperModel(
            model_name,
            device=_whisper_device,
            compute_type=_whisper_compute,
        )
        print("[whisper] Model loaded OK.", flush=True)
        return True
    except Exception as e:
        if _whisper_device == "cuda":
            print(f"[whisper] CUDA failed ({e}), falling back to CPU ...", flush=True)
            _whisper_device = "cpu"
            _whisper_compute = "int8"
            try:
                _whisper_model = WhisperModel(model_name, device="cpu", compute_type="int8")
                print("[whisper] Model loaded OK on CPU.", flush=True)
                return True
            except Exception as e2:
                print(f"[whisper] CPU fallback also failed: {e2}", file=sys.stderr)
                return False
        print(f"[whisper] Failed to load model: {e}", file=sys.stderr)
        traceback.print_exc()
        return False


def _zerlege_multipart(body: bytes, boundary: str):
    """Audio und Textfelder aus dem Multipart-Koerper holen.

    Rueckgabe: (audio_bytes|None, {feldname: wert})
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
        # Abschliessende Zeilenumbrueche und die Grenzmarkierung entfernen
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


class WhisperHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"[whisper] {self.client_address[0]} → {fmt % args}", flush=True)

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
            self._send_json(200, {
                "status": "ok",
                "model":  _whisper_model is not None,
                "device": _whisper_device,
            })
        else:
            self._send_json(404, {"error": "not found. Use POST /transcribe"})

    def do_POST(self):
        if self.path != "/transcribe":
            self._send_json(404, {"error": f"unknown endpoint: {self.path}"})
            return

        if _whisper_model is None:
            self._send_json(503, {"error": "model not loaded yet, retry in a few seconds"})
            return

        content_type = self.headers.get("Content-Type", "")
        felder = {}
        if "multipart/form-data" not in content_type:
            # Roher Koerper als Rueckfallweg
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                self._send_json(400, {"error": "empty body"})
                return
            audio_data = self.rfile.read(length)
        else:
            boundary = None
            for part in content_type.split(";"):
                part = part.strip()
                if part.startswith("boundary="):
                    boundary = part[len("boundary="):].strip('"')
            if not boundary:
                self._send_json(400, {"error": "no boundary in multipart"})
                return
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            audio_data, felder = _zerlege_multipart(body, boundary)
            if audio_data is None:
                self._send_json(400, {"error": "no audio file part found in multipart"})
                return

        if len(audio_data) < 100:
            self._send_json(400, {"error": "audio too short"})
            return

        # Sprache: Standard Deutsch - der Sender wird auf Deutsch bedient. "auto"
        # stellt die Erkennung wieder frei.
        sprache = (felder.get("language") or "de").strip().lower()
        if sprache in ("", "auto", "none", "null"):
            sprache = None
        hinweis = (felder.get("prompt") or "").strip() or None

        # faster-whisper liest die Datei selbst (Erkennung ueber ffmpeg/PyAV).
        try:
            with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as f:
                f.write(audio_data)
                tmp_path = f.name
        except OSError as e:
            self._send_json(500, {"error": f"temp file error: {e}"})
            return

        try:
            print(f"[whisper] Transcribing {len(audio_data)} bytes (lang={sprache}) ...",
                  flush=True)
            segments, info = _whisper_model.transcribe(
                tmp_path,
                language=sprache,
                task="transcribe",
                beam_size=5,
                temperature=0.0,
                initial_prompt=hinweis,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            full_text = " ".join(seg.text.strip() for seg in segments)
            lang = info.language if info else "unknown"
            print(f"[whisper] Done: lang={lang}, text={full_text[:100]!r}", flush=True)
            self._send_json(200, {
                "text":     full_text,
                "language": lang,
            })
        except Exception as e:
            print(f"[whisper] Error: {e}", file=sys.stderr)
            traceback.print_exc()
            self._send_json(500, {"error": str(e)})
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser(description="Whisper STT HTTP Server")
    parser.add_argument("--port",  type=int,   default=18790, help="Listen port")
    parser.add_argument("--model", type=str,   default="large-v3",
                        choices=["tiny", "tiny.en", "base", "base.en",
                                 "small", "small.en", "medium", "medium.en",
                                 "large-v3"],
                        help="Whisper model size")
    parser.add_argument("--host",  type=str,   default="0.0.0.0", help="Bind address")
    args = parser.parse_args()

    if not _load_model(args.model):
        print("[whisper] Model load failed — starting anyway (will 503 until loaded)",
              file=sys.stderr)
        # Retry once after a delay
        import time
        time.sleep(3)
        _load_model(args.model)

    server = HTTPServer((args.host, args.port), WhisperHandler)
    print(f"[whisper] Listening on http://{args.host}:{args.port}", flush=True)
    print(f"[whisper] Health check: http://{args.host}:{args.port}/health", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[whisper] Shutting down.", flush=True)
        server.shutdown()


if __name__ == "__main__":
    main()
