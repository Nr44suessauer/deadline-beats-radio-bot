# Voice — integrating your own desired voice

> **Note about this edition:** This publication contains **no third-party voice** and
> **no voice data** (no model, no training clips, no samples). Out of the box the
> service speaks with a **free standard voice**. This document explains, step by step,
> how to bring in **your own desired voice** — either a free Piper voice (Option A) or
> a self-produced speaker voice via your own voice service (Option B).
>
> Placeholders: `YOUR-VOICE` = the name of your voice, `<GPU machine>` = the
> machine/container with an NVIDIA GPU, `<your-model>` = your training result,
> `<your-dataset>` = your collected material.

---

## 1. How announcements are produced

The speech service **`radio-tts`** (`dienst/`, port **8881**) turns text into audio and
speaks it live into the station's DJ harbour (announcements run in real time — not as a
background job). The voice is chosen in two places:

| Path | Field | Meaning |
| --- | --- | --- |
| OpenAI-compatible | `voice` in `POST /v1/audio/speech` | short name of a Piper voice **or** the name of your own voice |
| Bot tools | `stimme` for "announce message" and "fetch research" | empty = standard voice; `deine-stimme` = your own voice |

* **Standard voice:** `TTS_DEFAULT_VOICE` (default `de_thorsten`, a free Piper voice —
  it works without any custom GPU service).
* **Piper voices:** live as `.onnx` (+ `.json`) in `VOICE_DIR` (default `/voices`).
  Short names like `de_kerstin` map to file names inside the service.
* **Own voice (optional):** a **voice service of your own** that `radio-tts` calls via
  `EIGENE_STIMME_URL` (section 3.8). If it is unreachable, the fallback voice
  `EIGENE_STIMME_ERSATZ` speaks — an announcement never fails.

After every generation the service writes a log line **`Stimme: <name>`** — this is how
you verify in `docker logs radio-tts` which voice actually spoke.

---

## 2. Option A — choose a free Piper voice (simplest path)

1. Get a voice (freely available from the Piper voice collections) and put
   `<name>.onnx` and `<name>.onnx.json` into the voices folder (the host path mounted
   onto `VOICE_DIR` in `docker-compose.yml`).
2. Register the short name: either in the `KURZNAMEN` table in `dienst/main.py` or just
   use it (the service also matches plain file names, case-insensitive).
3. Set the default: `TTS_DEFAULT_VOICE=<short-name>` in `geheim.env` (or the compose
   environment), then recreate the service
   (`docker compose up -d --force-recreate radio-tts`).
4. Test:

```bash
curl -s -X POST http://127.0.0.1:8881/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"input": "Hello, this is the new voice speaking.", "voice": "<short-name>"}' \
  -o /tmp/probe.mp3 -w 'HTTP %{http_code}\n'
```

---

## 3. Option B — integrating your own (cloned) speaker voice

### 3.1 Legal note — read first

* Only use material **you hold the rights to** (your own recordings, your own
  speakers, licensed sources). Voices of other people — especially from films, series
  or games — must **not** be copied, published or used on a station without explicit
  permission.
* Training material, model and samples are **personal working data**: do not share
  or publish them.
* This publication deliberately ships **no** example voice — no third-party voice and
  no voice data.

### 3.2 What you need

* A machine/container with an **NVIDIA GPU** (~8 GB VRAM is enough; shared GPUs work,
  see pitfalls in section 3.11), Ubuntu, ~60 GB disk
* `ffmpeg`, internet access (base models, optional online TTS as the base voice)
* **Your own** audio material of the desired voice (e.g. clean, dry microphone
  recordings — no music)
* Time: collection depends on the material, training ~1 hour

### 3.3 Prepare the raw material (speaker separation)

For material with several speakers (e.g. video/broadcast recordings) a small service is
included that separates the voices and writes **one folder per speaker**:

```bash
# set up (copies script + systemd unit, creates a key)
bash NACHBAU/eigene-stimme/einrichten-stimmen-dienst.sh

# start a job — first ONE episode/file as a test, then all
K=$(cat /opt/stimmen-dienst/schluessel.txt)
curl -s -X POST "http://<GPU machine>:8890/extrahieren?schluessel=$K" \
     -H 'Content-Type: application/json' \
     -d '{"serie":"/path/to/your/material","name":"run1","folgen":1,"trennen":true}'
```

Result: `/opt/Applio/assets/datasets/run1/cluster_0 … cluster_n` — one folder per
speaker. Remove music/outros — they survive vocal separation.

### 3.4 Confirm the reference (mandatory)

From the matching speaker folder, copy the **cleanest 5–10 short clips** into their own
reference folder (e.g. `<your-reference>`). This reference drives all later collection —
a wrong anchor costs a complete model. You can have samples sent to you:

```bash
bash NACHBAU/eigene-stimme/cluster-proben.sh run1 2   # 2 samples per cluster
```

### 3.5 Collect clean pieces

Three small tools collect training material against the confirmed reference (similarity
threshold, minimum duration and window are proven example values at the top of the
scripts — adjust to your material):

| Tool | Task |
| --- | --- |
| `stimme_pruefen.py` | window check: clean pieces of the target voice against the reference |
| `stimme_sammeln.py` | collection: only the longest connected run of hits per candidate |
| `stimme_erweitern.py` | self-expansion in rounds (more material from more sources) |

```bash
# example (adjust the paths):
/opt/Applio/.venv/bin/python /opt/Applio/stimmen-dienst/stimme_sammeln.py \
  --referenz <your-reference> --quellen "<more-sources>/cluster_*" \
  --ziel <your-dataset>
```

### 3.6 Train the model

```bash
bash NACHBAU/eigene-stimme/rvc-trainieren.sh <your-model> <your-dataset> 400 8
```

* Pipeline: preprocess → extract (`rmvpe`) → train (**400 epochs, batch 8**, save
  every 50) → index.
* Expectation on an RTX 3090 Ti: **~1 h** for ~10 minutes of material.
* Results: `<your-model>_400e_*.pth` (model) + `<your-model>.index` (index).

### 3.7 Build the speech service

The included **`sprechdienst.py`** is the bridge "text → your voice": base TTS
(default: `edge-tts`) → RVC conversion → WAV. It offers exactly the two endpoints
`radio-tts` expects:

| Endpoint | Response |
| --- | --- |
| `POST /tts` with `{"text": "…"}` | WAV audio (22050 Hz mono) |
| `GET /health` | status (JSON) |

```bash
# copy the files onto the GPU machine (example container "rvc"):
docker cp NACHBAU/eigene-stimme/sprechdienst.py  <container>:/opt/Applio/sprechdienst/sprechdienst.py
docker cp NACHBAU/eigene-stimme/sprechdienst.service <container>:/etc/systemd/system/
# enter model/index paths, base voice and speed AT THE TOP of the service, then:
systemctl daemon-reload && systemctl enable --now sprechdienst && systemctl is-active sprechdienst
curl -s http://127.0.0.1:10205/health
```

### 3.8 Wiring it into `radio-tts`

In the speech service's `geheim.env` (or the compose environment):

```env
EIGENE_STIMME_URL=http://<GPU machine>:10205/tts
EIGENE_STIMME_NAME=deine-stimme
EIGENE_STIMME_ERSATZ=de_thorsten
# EIGENE_STIMME_ZEITABLAUF=600
```

* `EIGENE_STIMME_URL` — address of your speech service. **Empty = feature off**
  (the Piper standard voice always speaks then).
* `EIGENE_STIMME_NAME` — the name the voice is addressed by (default `deine-stimme`).
* `EIGENE_STIMME_ERSATZ` — Piper voice used if your service is unreachable.
* Then `docker compose up -d --force-recreate radio-tts` and check `/health`: the voice
  list shows your name; the log line `Stimme: <name>` proves the path.

### 3.9 Asking for it in chat

Announcements use your own voice **on explicit request** — simple phrases such as:

* "announce: … **with your own voice**"
* "read the news with your voice"
* "in your own voice"

The request is detected reliably and passed on as `stimme=deine-stimme` to the tools;
the phrase itself is **never read out**. Without a request the standard voice is used
(or whatever `TTS_DEFAULT_VOICE` says).

### 3.10 Checks

```bash
# 1) service directly:
curl -s -X POST http://<GPU machine>:10205/tts -H 'Content-Type: application/json' \
  -d '{"text": "Welcome. This is your own voice speaking."}' -o /tmp/probe.wav \
  -w 'HTTP %{http_code} in %{time_total}s\n'

# 2) via radio-tts:
curl -s -X POST http://127.0.0.1:8881/v1/audio/speech -H 'Content-Type: application/json' \
  -d '{"input": "Test via the speech service.", "voice": "deine-stimme"}' \
  -o /tmp/probe2.mp3 -D - | grep -i x-stimme

# 3) in operation: check the log line
docker logs --tail 20 radio-tts | grep "Stimme:"
```

### 3.11 Pitfalls (learned while building)

* **Sharing the GPU:** if a language model (Ollama etc.) runs on the same card, your
  speech service can run out of memory (`CUDA out of memory`, HTTP 500). Then the
  fallback voice speaks. Countermeasures: free the cache after every announcement
  (`sprechdienst.py` does), set `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`,
  stop other GPU services if needed.
* **Generous timeout:** generation is a bit faster than real time — but a multi-minute
  announcement still takes minutes. Set `EIGENE_STIMME_ZEITABLAUF` (seconds)
  accordingly, otherwise the service falls back early.
* **First announcement after a service start** takes longer (model load), afterwards
  ~1.5–4 s per sentence.
* **One model per service:** after switching the model, restart the service.

---

## 4. Where the scripts live

All in **`NACHBAU/eigene-stimme/`** (adjust the example values inside):

| File | Purpose |
| --- | --- |
| `README.md` | working instructions for the scripts |
| `stimmen_dienst.py`, `stimmen-dienst.service`, `einrichten-stimmen-dienst.sh` | raw material: video → vocal separation → speaker clusters (port 8890) |
| `cluster-proben.sh` | samples per speaker (choosing the target voice) |
| `stimme_pruefen.py`, `stimme_sammeln.py`, `stimme_erweitern.py` | find, collect and expand clean pieces |
| `rvc-trainieren.sh` | training in the container (preprocess → extract → train → index) |
| `sprechdienst.py`, `sprechdienst.service` | speech service (port 10205): base TTS → RVC → WAV |
| `tg-sprachnachricht.sh` | send a sample via Telegram (optional) |
| `verworfen/` | a discarded approach, for reference only |

---

## 5. When something does not work

| Symptom | Cause / remedy |
| --- | --- |
| announcement speaks the "wrong" (fallback) voice | your service is unreachable/too slow — check `/health`, look at the `Stimme:` log line, raise the timeout |
| `HTTP 500` from the speech service | usually GPU memory (section 3.11) |
| voice sounds different than expected | tune base voice/speed/RVC mix (`index_rate`) in the service — in small steps and always by ear |
| bot still uses the standard voice | the request contained none of the phrases from 3.9, or `EIGENE_STIMME_URL` is empty |
