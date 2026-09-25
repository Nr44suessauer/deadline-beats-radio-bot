# Your own speaker voice — working instructions for the scripts

These instructions rebuild a **speaker voice of your own** on your own hardware: from
your own audio material to the speech service. They belong to **`DOCS/VOICE.md`** —
that document describes the full path in detail (legal note first, then both options).

> **This edition contains no third-party voice and no voice data.** All scripts are
> **templates**: the paths, addresses and names inside are **example values from the
> build** and must be adapted to your environment.
>
> **Legal note:** only use your own material that you hold the rights to. Never
> publish or use other people's voices. Do not share model, dataset or samples.

---

## What is in this folder

| File | Purpose |
| --- | --- |
| `voice-service.py`, `voice-service.service`, `setup-voice-service.sh` | raw material: video → Demucs → speech cuts → speaker clusters (service **8890**) |
| `cluster-samples.sh` | samples per speaker cluster (choosing the target voice) |
| `check-voice.py` | window check: clean pieces of the target voice against the confirmed reference |
| `collect-voice.py` | collection: only the longest connected run of hits per candidate |
| `extend-voice.py` | self-expansion in rounds (more material from more sources) |
| `rvc-train.sh` | training in the container (preprocess → extract → train → index) |
| `speech-service.py`, `speech-service.service` | speech service **10205**: base TTS → RVC → WAV (systemd) |
| `tg-voice-message.sh` | send a sample via Telegram (optional) |
| `discarded/` | a discarded approach — for reference only |

The comments inside the files name the **adjustment points** (paths, addresses,
thresholds). Method, measurements and pitfalls are in `DOCS/VOICE.md`.

---

## The path in brief

```bash
# 0) environment: NVIDIA GPU, ffmpeg, Applio/RVC  (see DOCS/VOICE.md, section 3.2)
# 1) set up and start speaker separation  (port 8890)
bash setup-voice-service.sh
K=$(cat /opt/stimmen-dienst/schluessel.txt)
curl -s -X POST "http://<GPU machine>:8890/extrahieren?schluessel=$K" \
     -H 'Content-Type: application/json' \
     -d '{"serie":"/path/to/your/material","name":"run1","folgen":1,"trennen":true}'

# 2) confirm the target voice (samples per cluster) and store 5-10 clean reference clips
bash cluster-samples.sh run1 2

# 3) collect clean pieces (adjust the example values in the scripts)
/opt/Applio/.venv/bin/python collect-voice.py \
  --referenz <your-reference> --quellen "<more-sources>/cluster_*" \
  --ziel <your-dataset>

# 4) train the model  (~1 h on an RTX 3090 Ti for ~10 minutes of material)
bash rvc-train.sh <your-model> <your-dataset> 400 8

# 5) set up the speech service  (port 10205; contract: POST /tts, GET /health)
#    copy speech-service.py + speech-service.service to the container, enter your values,
#    systemctl enable --now speech-service, check /health

# 6) wire it into radio-tts  (geheim.env):
#    EIGENE_STIMME_URL=http://<GPU machine>:10205/tts
#    EIGENE_STIMME_NAME=deine-stimme
#    EIGENE_STIMME_ERSATZ=de_thorsten
```

Afterwards simply say in chat: **"… with your own voice"** — or call
`POST /v1/audio/speech` directly with `"voice": "deine-stimme"`.
