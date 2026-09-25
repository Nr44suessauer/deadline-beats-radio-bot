# Your own speaker voice — working instructions for the scripts

These instructions rebuild a **speaker voice of your own** on your own hardware: from
your own audio material to the speech service. They belong to **`DOKU/STIMME.md`** —
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
| `stimmen_dienst.py`, `stimmen-dienst.service`, `einrichten-stimmen-dienst.sh` | raw material: video → Demucs → speech cuts → speaker clusters (service **8890**) |
| `cluster-proben.sh` | samples per speaker cluster (choosing the target voice) |
| `stimme_pruefen.py` | window check: clean pieces of the target voice against the confirmed reference |
| `stimme_sammeln.py` | collection: only the longest connected run of hits per candidate |
| `stimme_erweitern.py` | self-expansion in rounds (more material from more sources) |
| `rvc-trainieren.sh` | training in the container (preprocess → extract → train → index) |
| `sprechdienst.py`, `sprechdienst.service` | speech service **10205**: base TTS → RVC → WAV (systemd) |
| `tg-sprachnachricht.sh` | send a sample via Telegram (optional) |
| `verworfen/` | a discarded approach — for reference only |

The comments inside the files name the **adjustment points** (paths, addresses,
thresholds). Method, measurements and pitfalls are in `DOKU/STIMME.md`.

---

## The path in brief

```bash
# 0) environment: NVIDIA GPU, ffmpeg, Applio/RVC  (see DOKU/STIMME.md, section 3.2)
# 1) set up and start speaker separation  (port 8890)
bash einrichten-stimmen-dienst.sh
K=$(cat /opt/stimmen-dienst/schluessel.txt)
curl -s -X POST "http://<GPU machine>:8890/extrahieren?schluessel=$K" \
     -H 'Content-Type: application/json' \
     -d '{"serie":"/path/to/your/material","name":"run1","folgen":1,"trennen":true}'

# 2) confirm the target voice (samples per cluster) and store 5-10 clean reference clips
bash cluster-proben.sh run1 2

# 3) collect clean pieces (adjust the example values in the scripts)
/opt/Applio/.venv/bin/python stimme_sammeln.py \
  --referenz <your-reference> --quellen "<more-sources>/cluster_*" \
  --ziel <your-dataset>

# 4) train the model  (~1 h on an RTX 3090 Ti for ~10 minutes of material)
bash rvc-trainieren.sh <your-model> <your-dataset> 400 8

# 5) set up the speech service  (port 10205; contract: POST /tts, GET /health)
#    copy sprechdienst.py + sprechdienst.service to the container, enter your values,
#    systemctl enable --now sprechdienst, check /health

# 6) wire it into radio-tts  (geheim.env):
#    EIGENE_STIMME_URL=http://<GPU machine>:10205/tts
#    EIGENE_STIMME_NAME=deine-stimme
#    EIGENE_STIMME_ERSATZ=de_thorsten
```

Afterwards simply say in chat: **"… with your own voice"** — or call
`POST /v1/audio/speech` directly with `"voice": "deine-stimme"`.
