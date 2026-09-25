# Speech recognition (`whisper_server.py`)

This module does **not** run inside the `radio-tts` service — it runs as a separate
small service on the GPU machine, in the original in LXC 105 (`192.168.178.187`),
port **18790**.

It is the source for the bot's "voice message" branch: the bot downloads the voice
message from Telegram, sends it here and gets the text back.

---

## Starting

```bash
python3 whisper_server.py --port 18790 --model large-v3
```

* `--model`: anything `faster-whisper` knows (`large-v3` is configured; the model is
  downloaded from HuggingFace on the first call, ~3 GB)
* `--port`: default 18790
* Language: **fixed to `de`** via the `language` parameter (auto-detection
  misheard short German sentences as English)
* `prompt`: domain hint — the bot sends the most frequent artists from the catalog
  along so that names like "Nirvana" or "Die Ärzte" arrive correctly

## Interface

| Address | Input | Response |
| --- | --- | --- |
| `POST /transcribe` | multipart: `file`, `language` (default `de`), `prompt` | `{"text": "…", "language": "de"}` |
| `GET /health` | — | state |

## systemd unit (original)

```ini
[Unit]
Description=Whisper STT HTTP Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/whisper-stt
ExecStart=/usr/bin/python3 /root/whisper-stt/whisper_server.py --port 18790 --model large-v3
Restart=always
RestartSec=5
Environment=PATH=/usr/bin:/usr/local/bin
Environment=PYTHONUNBUFFERED=1
Environment=LD_LIBRARY_PATH=/usr/lib/ollama/cuda_v12
```

```bash
mkdir -p /root/whisper-stt
cp whisper_server.py /root/whisper-stt/
python3 -m pip install faster-whisper
systemctl enable --now whisper-stt
curl -s http://127.0.0.1:18790/health
```

## Checking

```bash
# Create an announcement and transcribe it back (self test)
curl -s -X POST http://<service>:8881/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input":"Die Sendung beginnt in fünf Minuten.","voice":"","response_format":"wav"}' \
  -o /tmp/probe.wav
curl -s -X POST http://<gpu-machine>:18790/transcribe \
  -F "file=@/tmp/probe.wav" -F "language=de"
# expect: roughly the same sentence as text
```

From the project there are `tools/speech-test.sh` and
`tools/voice-check.sh` for this (the latter searches for a speech sample
that is understood cleanly).
