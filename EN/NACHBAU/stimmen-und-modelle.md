# Voices and Models

Everything the bot has "in its head" with source, size, and settings. The files themselves
are too large for a documentation folder — the Piper voices are fetched from `stimmen-holen.sh`,
the models pull their tools themselves. The **own speaker voice** (RVC) is trained from
personal material — Creation: `../DOKU/STIMME.md`, Replication: `eigene-stimme/`.

---

## 1. Voices (Piper, in Service)

The service uses **Piper** (`piper-tts`), each voice consists of two files:
`<name>.onnx` (Model) and `<name>.onnx.json` (Configuration). Storage: `/opt/radio-tts/voices`
(in container `/voices`).

**Installed (Original, 201 MB):**

| Short name in `main.py` | File | Size | Download (Piper voices, HuggingFace) |

| --- | --- | --- | --- |

| `de_thorsten` (Replacement voice) | `de_DE-thorsten-medium.onnx` | 63 MB | `…/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx(.json)` |

| `de_kerstin` | `de_DE-kerstin-low.onnx` | 63 MB | `…/de/de_DE/kerstin/low/…` |

| `de_ramona` | `de_DE-ramona-low.onnx` | 63 MB | `…/de/de_DE/ramona/low/…` |

| `de_eva` | `de_DE-eva_k-x_low.onnx` | 21 MB | `…/de/de_DE/eva_k/x_low/…` |

Base URL: `https://huggingface.co/rhasspy/piper-voices/resolve/main/` (the three
example addresses were checked with HTTP 200 on 2026-09-20).

**Announcement voice is since 2026-09-23 the own voice `deine-stimme`** (Section 2) —
Piper voices remain selectable via `voice`/`stimme` and serve as a fallback (`EIGENE_STIMME_ERSATZ`).

```bash
# fetch all four (puts them into the target directory)
bash NACHBAU/stimmen-holen.sh /opt/radio-tts/voices
```

In `main.py` are additional short names prepared (`de_karlsson`, `de_martin`,
`de_pavoque`, `en_lessac`) — they work as soon as the files are in the voice folder.
Any Piper voice can be added this way; the default name is chosen via
`TTS_DEFAULT_VOICE`.

**Change voice** (without code change): `TTS_DEFAULT_VOICE` in
`/opt/radio-tts/geheim.env`, then `docker compose up -d`.

**Voice per announcement**: the addresses `/live`, `/ansage/meldung`, `/ansage/text`, and
`/v1/audio/speech` accept `voice` and `speed` (0.3–3.0).

---

## 2. Own Speaker Voice (RVC) — "YOUR-VOICE"

In addition to the Piper voices, a **modulation voice** (voice conversion via RVC v2/Applio, base `de-DE-AmalaNeural`) is created in the project. It runs as a separate
small service on the GPU machine and has been integrated into the radio service `radio-tts`
since 2026-09-23 — since 2026-09-25 **on explicit request** (`stimme=deine-stimme`,
"… with your own voice"; default is `de_thorsten`).

| Point | Value |

| --- | --- |

| Model | **`<your-model>`** — 400 epochs, Batch 8, Dataset 10:44 min (280 samples) |

| Files | `/opt/Applio/logs/<your-model>/<your-model>.pth` (**53 MB**) + `<your-model>.index` (**97 MB**) |

| Voice chain | edge-tts (`de-DE-AmalaNeural`, **+40%**) → RVC (rmvpe, pitch shift **+4**, `index_rate` **0.65**, `protect` 0.5) → WAV 22050 Hz |

| Service | `sprechdienst` on CT 111, **Port 10205** (`POST /tts`, `GET /health`) |

| Integration | `radio-tts` uses it **on request** (`stimme=deine-stimme`; default `de_thorsten`); Piper voices remain selectable via `voice`/`stimme`; in case of failure, fallback to `EIGENE_STIMME_ERSATZ` (de_thorsten) |

| Creation, Values, Checks | `../DOKU/STIMME.md` |

| Replication (all scripts) | `eigene-stimme/README.md` |

---

## 3. Language Model (Ollama, GPU Machine)

| Point | Value |

| --- | --- |

| Model | **`qwen3.6:27b`** (17.7 GB) — runs on the RTX 3090 Ti |

| Origin | Ollama (`ollama pull`), alternatively own model file |

| Address | `http://<GPU-Maschine>:11434` (Environment variable `OLLAMA_URL` during build) |

| Settings in the bot | `temperature 0.2/0.3`, `maxTokens 3000` (plan/execute) or 4000 (check), `reasoning_effort: "none"` |

| Service configuration | `OLLAMA_HOST=0.0.0.0:11434`, `OLLAMA_KEEP_ALIVE=30m`, `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MODELS=/mnt/Storage` |

**Why these values:**

* `maxTokens` limits — without limit, qwen3 writes endlessly (in operation over 18,000
  tokens, 180 s time limit).
* `reasoning_effort: "none"` switches off thinking (9.8 s → 1.7 s with the same
  result). `/no_think` in the text does **not** affect it.
* `OLLAMA_KEEP_ALIVE=30m` — reloading costs 43.7 s.

**Change model:** `OLLAMA_MODELL` during build processes. It must
**handle tools (Function Calling)**. Tested: `qwen3.6:27b` (recommended),
`qwen2.5:14b` (writes calls sometimes as text), `llama3.1:8b` (invents paths).

**Additional Models in the Original Container** (not required):
`qwen3-coder:30b`, `gemma4:26b`, `phi4:14b`, `llama3.1:8b`, `qwen3-embedding:8b`.

---

## 4. Speech Recognition (faster-whisper, GPU Machine)

| Point | Value |
| --- | --- |
| Model | **`large-v3`** (int8_float16 on CUDA) |
| Origin | HuggingFace `Systran/faster-whisper-large-v3`, loaded from
`faster-whisper` on first call (~3 GB) |
| Service | `dienst/whisper/whisper_server.py`, Port **18790**, systemd `whisper-stt` |
| Call | `POST /transcribe` (multipart: `file`, `language=de`, `prompt`) |
| Address in Bot | `WHISPER_URL` during build (`http://<GPU>:18790/transcribe`) |

```bash
# rebuild on the GPU machine
mkdir -p /root/whisper-stt
cp dienst/whisper/whisper_server.py /root/whisper-stt/
python3 -m pip install faster-whisper
# systemd unit see dienst/whisper/README.md, then:
systemctl enable --now whisper-stt
curl -s http://127.0.0.1:18790/health
```

**Important:** `language` is fixed on `de` (autodetected short German sentences)
and the bot sends a **Technical Note** (`prompt`) with the most common interpreters
from the catalog — this ensures reliable recognition of names like "Nirvana".

---

## 5. Catalog Index (no model, but required)

The search index of the archive is a file in the service (`/daten/katalog.json`, 44 MB) and
is built from the sender interface:

```bash
curl -s -X POST -H "X-News-Key: <key>" \
  http://<dienst>:8881/katalog/aktualisieren      # dauert ~47 s
curl -s http://<dienst>:8881/katalog/status
```

It is **not** a model and can be rebuilt at any time (Original: 48,729 of
56,635 titles — excluded are `_Archiv/` and `moderation/`).

---

## 6. Overview of Sizes

| Component | Size | Where |

| --- | --- | --- |

| Piper Voices (4) | 201 MB | `/opt/radio-tts/voices` |

| Speaker Voice (RVC): Model + Index | 53 MB + 97 MB | `/opt/Applio/logs/<your-model>/` (CT 111) |

| Speaker Dataset (280 items) | 10:44 min | `/opt/Applio/assets/datasets/<your-dataset>` |

| Ollama Model | 17.7 GB | `/mnt/Storage` (GPU Machine) |

| Whisper large-v3 | ~3 GB | HuggingFace cache of the GPU machine |

| Catalog Index | 44 MB | `/opt/radio-tts/daten/katalog.json` |

| Music Archive | ~15 TB | Media storage of the sender |