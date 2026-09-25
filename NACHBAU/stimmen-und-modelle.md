# Stimmen und Modelle

Alles, was der Bot „im Kopf" hat, mit Quelle, Größe und Einstellung. Die Dateien selbst
sind zu groß für einen Dokumentationsordner — die Piper-Stimmen holt `stimmen-holen.sh`,
die Modelle ziehen ihre Werkzeuge selbst. Die **eigene Sprecherstimme** (RVC) wird aus
eigenem Material trainiert — Entstehung: `../DOKU/STIMME.md`, Nachbau: `eigene-stimme/`.

---

## 1. Stimmen (Piper, im Dienst)

Der Dienst nutzt **Piper** (`piper-tts`), jede Stimme besteht aus zwei Dateien:
`<name>.onnx` (Modell) und `<name>.onnx.json` (Konfiguration). Ablage: `/opt/radio-tts/voices`
(im Container `/voices`).

**Installiert (Original, 201 MB):**

| Kurzname in `main.py` | Datei | Größe | Download (Piper-Stimmen, HuggingFace) |
| --- | --- | --- | --- |
| `de_thorsten` (Ersatzstimme) | `de_DE-thorsten-medium.onnx` | 63 MB | `…/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx(.json)` |
| `de_kerstin` | `de_DE-kerstin-low.onnx` | 63 MB | `…/de/de_DE/kerstin/low/…` |
| `de_ramona` | `de_DE-ramona-low.onnx` | 63 MB | `…/de/de_DE/ramona/low/…` |
| `de_eva` | `de_DE-eva_k-x_low.onnx` | 21 MB | `…/de/de_DE/eva_k/x_low/…` |

Basis-URL: `https://huggingface.co/rhasspy/piper-voices/resolve/main/` (die drei
Beispieladressen wurden am 2026-09-20 mit HTTP 200 geprüft).

**Vorgabe der Ansagen ist seit 2026-09-23 die eigene Stimme `deine-stimme`** (Abschnitt 2) —
Piper-Stimmen bleiben über `voice`/`stimme` wählbar und dienen als Ersatz (`EIGENE_STIMME_ERSATZ`).

```bash
# alle vier holen (legt sie in das Zielverzeichnis)
bash NACHBAU/stimmen-holen.sh /opt/radio-tts/voices
```

In `main.py` sind weitere Kurznamen vorbereitet (`de_karlsson`, `de_martin`,
`de_pavoque`, `en_lessac`) — sie funktionieren, sobald die Dateien im Stimmenordner
liegen. Jede beliebige Piper-Stimme lässt sich so ergänzen; der Standardname wird über
`TTS_DEFAULT_VOICE` gewählt.

**Stimme wechseln** (ohne Codeänderung): `TTS_DEFAULT_VOICE` in
`/opt/radio-tts/geheim.env`, danach `docker compose up -d`.

**Stimme je Ansage**: die Adressen `/live`, `/ansage/meldung`, `/ansage/text` und
`/v1/audio/speech` nehmen `voice` und `speed` (0,3–3,0) entgegen.

---

## 2. Eigene Sprecherstimme (RVC) — „DEINE-STIMME"

Zusätzlich zu den Piper-Stimmen entsteht im Projekt eine **eigene Moderationsstimme**
(Wandlungsstimme über RVC v2/Applio, Basis `de-DE-AmalaNeural`). Sie läuft als eigener
kleiner Dienst auf der GPU-Maschine und ist seit 2026-09-23 im Radiodienst `radio-tts`
eingebunden — seit 2026-09-25 **auf ausdrücklichen Wunsch** (`stimme=deine-stimme`,
„… mit eigener Stimme"; Standard ist `de_thorsten`).

| Punkt | Wert |
| --- | --- |
| Modell | **`<dein-modell>`** — 400 Epochen, Batch 8, Datensatz 10:44 Min (280 Stücke) |
| Dateien | `/opt/Applio/logs/<dein-modell>/<dein-modell>.pth` (**53 MB**) + `<dein-modell>.index` (**97 MB**) |
| Sprechkette | edge-tts (`de-DE-AmalaNeural`, **+40 %**) → RVC (rmvpe, Tonhöhe **+4**, `index_rate` **0,65**, `protect` 0,5) → WAV 22050 Hz |
| Dienst | `sprechdienst` auf CT 111, **Port 10205** (`POST /tts`, `GET /health`) |
| Einbindung | `radio-tts` nutzt sie **auf Wunsch** (`stimme=deine-stimme`; Standard `de_thorsten`); Piper-Stimmen bleiben über `voice`/`stimme` wählbar; bei Ausfall ersatzweise `EIGENE_STIMME_ERSATZ` (de_thorsten) |
| Entstehung, Werte, Prüfungen | `../DOKU/STIMME.md` |
| Nachbau (alle Skripte) | `eigene-stimme/README.md` |

---

## 3. Sprachmodell (Ollama, GPU-Maschine)

| Punkt | Wert |
| --- | --- |
| Modell | **`qwen3.6:27b`** (17,7 GB) — läuft auf der RTX 3090 Ti |
| Herkunft | Ollama (`ollama pull`), alternativ eigenes Modelfile |
| Adresse | `http://<GPU-Maschine>:11434` (Umgebungsvariable `OLLAMA_URL` beim Bauen) |
| Einstellung im Bot | `temperature 0.2/0.3`, `maxTokens 3000` (Planen/Ausführen) bzw. 4000 (Prüfen), `reasoning_effort: "none"` |
| Dienstkonfiguration | `OLLAMA_HOST=0.0.0.0:11434`, `OLLAMA_KEEP_ALIVE=30m`, `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MODELS=/mnt/Storage` |

**Warum diese Werte:**

* `maxTokens` begrenzt — ohne Grenze schreibt qwen3 endlos (im Betrieb über 18.000
  Token, 180 s Zeitablauf).
* `reasoning_effort: "none"` schaltet das Denken ab (9,8 s → 1,7 s bei gleichem
  Ergebnis). `/no_think` im Text wirkt **nicht**.
* `OLLAMA_KEEP_ALIVE=30m` — ein Neuladen kostet 43,7 s.

**Modell austauschen:** `OLLAMA_MODELL` beim Bauen der Abläufe setzen. Es muss
**Werkzeuge (Function Calling)** beherrschen. Getestet: `qwen3.6:27b` (Empfehlung),
`qwen2.5:14b` (schreibt Aufrufe manchmal als Text), `llama3.1:8b` (erfindet Pfade).

**Weitere Modelle im Container des Originals** (nicht nötig):
`qwen3-coder:30b`, `gemma4:26b`, `phi4:14b`, `llama3.1:8b`, `qwen3-embedding:8b`.

---

## 4. Spracherkennung (faster-whisper, GPU-Maschine)

| Punkt | Wert |
| --- | --- |
| Modell | **`large-v3`** (int8_float16 auf CUDA) |
| Herkunft | HuggingFace `Systran/faster-whisper-large-v3`, geladen von
`faster-whisper` beim ersten Aufruf (~3 GB) |
| Dienst | `dienst/whisper/whisper_server.py`, Port **18790**, systemd `whisper-stt` |
| Aufruf | `POST /transcribe` (multipart: `file`, `language=de`, `prompt`) |
| Adresse im Bot | `WHISPER_URL` beim Bauen (`http://<GPU>:18790/transcribe`) |

```bash
# Nachbau auf der GPU-Maschine
mkdir -p /root/whisper-stt
cp dienst/whisper/whisper_server.py /root/whisper-stt/
python3 -m pip install faster-whisper
# systemd-Unit siehe dienst/whisper/README.md, dann:
systemctl enable --now whisper-stt
curl -s http://127.0.0.1:18790/health
```

**Wichtig:** `language` steht fest auf `de` (Autokennung verhörte kurze deutsche Sätze)
und der Bot schickt einen **Fachhinweis** (`prompt`) mit den häufigsten Interpreten aus
dem Katalog — damit werden Namen wie „Nirvana" zuverlässig erkannt.

---

## 5. Katalogindex (kein Modell, aber nötig)

Der Suchindex des Archivs liegt als Datei im Dienst (`/daten/katalog.json`, 44 MB) und
wird aus der Sender-Schnittstelle gebaut:

```bash
curl -s -X POST -H "X-Meldung-Schluessel: <Schlüssel>" \
  http://<dienst>:8881/katalog/aktualisieren      # dauert ~47 s
curl -s http://<dienst>:8881/katalog/status
```

Er ist **kein** Modell und kann jederzeit neu gebaut werden (Original: 48.729 von
56.635 Titeln — ausgenommen sind `_Archiv/` und `moderation/`).

---

## 6. Übersicht der Größen

| Bestandteil | Größe | Wo |
| --- | --- | --- |
| Piper-Stimmen (4) | 201 MB | `/opt/radio-tts/voices` |
| Sprecherstimme (RVC): Modell + Index | 53 MB + 97 MB | `/opt/Applio/logs/<dein-modell>/` (CT 111) |
| Sprecher-Datensatz (280 Stücke) | 10:44 Min | `/opt/Applio/assets/datasets/<dein-datensatz>` |
| Ollama-Modell | 17,7 GB | `/mnt/Storage` (GPU-Maschine) |
| Whisper large-v3 | ~3 GB | HuggingFace-Cache der GPU-Maschine |
| Katalogindex | 44 MB | `/opt/radio-tts/daten/katalog.json` |
| Musikarchiv | ~15 TB | Medienspeicher des Senders |
