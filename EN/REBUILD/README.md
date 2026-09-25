# Replication — rebuild the bot completely

This guide rebuilds the bot on **new hardware** (or after a total loss)
so that it behaves like the running one. Everything necessary is copied into
this folder; what **cannot** be in a folder is listed in section 6.

**Short answer to "is everything there?"**

| Area | In the folder? |
| --- | --- |
| Flows (Bot + 3 tools) | **yes, as creator** — will be rebuilt during setup (`tools/agent-wf-build.py`) |
| Service `radio-tts` (Language, Announcements, Catalog, Lists, Mailbox, Research) | **yes** — `service/app/`, `service/Dockerfile`, `service/docker-compose.yml` |
| Operation and test tools (over 100 scripts) | **yes** — `tools/` |
| Voices and models | **Guide + download script** (`fetch-voices.sh`, `voices-and-models.md`) — the files themselves are 0.2–18 GB |
| Own voice (RVC "YOUR-VOICE") | **yes** — `own-voice/`: all scripts + guide (`README.md`); dataset and model are generated from own media collection |
| Access data | **yes** — `credentials/` with `OVERVIEW.md` (working copy: real values 700/600; published: placeholders); how they are created: `credentials.md` |
| Music archive | **no** — the content itself; the bot runs with any own archive |
| Station configuration | **Guide** — `station-setup.md` |
| Own search engine (SearXNG, LXC 108) | **Guide** — `searxng-setup.md` |
| Infrastructure (containers, IPs, proxy) | **Guide** — `environment.md` |

---

## 1. What is needed

* A machine with **Docker** and **Docker Compose** for the service (original: LXC 103)
* **n8n** (v2.34.6) as a container (also LXC 103, port 5678) — including an account and
  your own project ID, see step 3
* A machine with **GPU** for Ollama **and** speech recognition (original: LXC 105 on
  `ai-server`, RTX 3090 Ti with 24 GB). The default model `qwen3.6:27b` needs **17.7 GB**
  — that calls for **24 GB VRAM** (or a smaller model); "from 8 GB" is only enough with a
  small model (see `voices-and-models.md` §3)
* An **AzuraCast** station (original 0.23.4, LXC 106 on the data server). If none is
  running yet, that is the **first** step: `station-setup.md` §0 (installation,
  account, API key)
* **Proxmox VE** as the base if containers are used: `nesting=1` and `keyctl=1` per
  container (Docker inside), and the GPU machine with the card passed through — see
  `environment.md` §0 for the short version and the checks
* A small container (2 cores, 1 GB) for the **own search engine**
  (SearXNG, original LXC 108 on `http://192.168.178.26:8888`) — without it
  the service queries DuckDuckGo and Bing directly, which block computers without login
* A **Telegram bot** (token from @BotFather) and the own chat-ID
* Around 100 GB of disk space for models and voices (without music archive)
* For the Telegram triggers: the n8n machine must be reachable from the internet
  (port forwarding or Cloudflare Tunnel) — otherwise use **webhook** mode, see step 3

**Operating system:** Proxmox VE 8 with Debian 12 templates; Ubuntu 24.04 for the RVC
machine (`own-voice/README.md` §0). **Time:** with an existing station, Proxmox and GPU,
one long evening is enough (the original took five days of building, `DOCS/BUILD.md` §1) —
training your own voice costs one more evening.

Network in original: see `environment.md` (fixed IPs, ports 5678, 8881, 8005, 8000,
11434, 18790, 8888 for the search engine).

---

## 2. Order of setup

**The station first, then the service** — the service's credentials file contains
`AZ_URL` and `AZ_KEY`, the address and key of the station (see `service/README.md`,
section "Zugangsdatei secret.env"). Where the steps show example values
(`192.168.x.x`, `YOUR-…`), put in your own.

| # | Step | Result you must see |
| --- | --- | --- |
| 0 | Install the station (`station-setup.md` §0) | `GET /api/status` answers, stream runs |
| 1 | Set up service `radio-tts` | `/health` → `{"status":"ok","stimmen":4,…}` |
| 2 | Language models on the GPU machine | Whisper answers, `ollama list` shows the model |
| 3 | Start n8n (container, account, project) | UI reachable on `:5678` |
| 4 | Import the workflows | 5 workflows active, test entry answers |
| 5 | Load the music archive | `katalog/status` shows more than 0 tracks |
| 6 | Verify everything (`DOCS/OPERATIONS.md`) | expectation table 11 of 11 |
| 7 | Own voice (optional) | sample via `/tts` |

---

### Step 1 — Set up service `radio-tts`

```bash
# Verzeichnis wie im Original anlegen
mkdir -p /opt/radio-tts/{app,voices,daten}
cp service/*.py              /opt/radio-tts/app/
cp service/Dockerfile        /opt/radio-tts/
cp service/docker-compose.yml /opt/radio-tts/
cp service/secret.env.template /opt/radio-tts/secret.env   # fill in!
bash REBUILD/fetch-voices.sh /opt/radio-tts/voices              # Stimmen laden
cd /opt/radio-tts && docker compose up -d --build
curl -s http://127.0.0.1:8881/health        # {"status":"ok","stimmen":4,...}
```

> **Careful, two traps in this order:**
> 1. `secret.env` needs **`AZ_URL`** (address of the station) and **`AZ_KEY`**
>    (API key) — the template `service/secret.env.template` contains **neither**, so add
>    them by hand. Without them the catalogue quietly falls back to an example address.
> 2. The `environment` block of `service/docker-compose.yml` sets
>    `TTS_DEFAULT_VOICE`, `EIGENE_STIMME_URL` and `RECHERCHE_SEARX_URL`. Values there
>    **override** `secret.env`. For a rebuild without an own RVC voice set the default to
>    a Piper voice (`TTS_DEFAULT_VOICE=de_thorsten`) and point both addresses at your
>    own hosts.

### Step 2 — Language models on the GPU machine

```bash
# Ollama (model for planning/executing/checking)
ollama pull qwen3.6:27b            # or another model that is good at tool use
ollama list                        # must show the model
# Configure the Ollama service (see voices-and-models.md):
#   OLLAMA_HOST=0.0.0.0:11434  OLLAMA_KEEP_ALIVE=30m  OLLAMA_NUM_PARALLEL=1
curl -s http://127.0.0.1:11434/api/tags    # lists the model

# Speech recognition — two ways, same interface (POST /transcribe)
#   Way 1 (easiest rebuild): whisper_server.py with faster-whisper, port 18790
#     -> guide: service/whisper/README.md  (CUDA or CPU, pulls a ~3 GB model)
#   Way 2 (used by the original since 2026-09-23): whisper.cpp large-v3 on an MI50,
#     LXC 112, port 8000  -> DOCS/MANUAL.md §4.4, DOCS/OPERATIONS.md §1
# Important: the same port must appear as WHISPER_URL in the `Konfiguration` workflow.
mkdir -p /opt/whisper-stt && cp service/whisper/whisper_server.py /opt/whisper-stt/
python3 -m pip install faster-whisper          # pulls the model on first use
# systemd unit: see service/whisper/README.md
systemctl enable --now whisper-stt
curl -s http://127.0.0.1:18790/health      # {"status":"ok","model":true,"device":"cuda"}
```

> **Do not mix them up:** the service on port **18790** (faster-whisper, LXC 105) is the
> convenient rebuild path; in the running original that work is done by **whisper.cpp on
> the MI50** (LXC 112, port **8000**, `whisper-amd`). Both answer `POST /transcribe` with
> `{"text": …}` — all that matters is that `WHISPER_URL` in the `Konfiguration` workflow
> points at your own service (`DOCS/MANUAL.md` §4.4, `DOCS/OPERATIONS.md` §1).

### Step 3 — Start n8n (two ways)

**Way A — exact copy** (fast, requires old access values):
`running-workflows/*.json` import (**seven** files: the hub `Konfiguration`, the agent,
three tools, the voices workflow and the former AI moderator), activate, restart n8n.
Order: **first** `Konfiguration.json` (it holds the values for all others), then the
tools, then the agent; the **five** workflows listed in `template.md` §4 are switched on.
Guide in `running-workflows/README.md`.

**Way B — rebuild** (own access values, traceable):

n8n as container, port 5678, project folder creation. Then build the flows:

```bash
# export the credentials into the environment (see credentials.md)
export TG_TOKEN="<Telegram-Bot-Token>"
export AZ_KEY="<AzuraCast API key>"
export NEWS_KEY="<inbox key>"
export OLLAMA_URL="http://<GPU-Host>:11434"
export WHISPER_URL="http://<GPU-Host>:18790/transcribe"

cd werkzeuge
python3 agent-wf-build.py            # writes /tmp/radio-konfiguration.json,
                                     # /tmp/radio-werkzeuge.json + /tmp/radio-agent.json
python3 layout-check.py /tmp/radio-agent.json     # must report "0 Befunde"
python3 import-agent-prepare.py  # writes /tmp/radio-agent-import.json
                                     # + /tmp/radio-werkzeuge-import.json
nano /tmp/radio-konfiguration.json   # put your own values in there (tokenizer, URLs)
```

> **Important for replication:** the creator builds the flows **identically** to
> the running bot — with one exception: a complete rebuild sets the field `name`
> (e.g., `titel_suchen`) at the tool node. In the running system, the field is not set; there,
> changes were always **surgically patched** (`tools/agent-patch.sh`). To exactly replicate the running bot,
> take the exports from `running-workflows/` (step 3, way A — they contain the
> access values, permissions 700/600); older version backups (`sicherungen/radio-fassungen/…`)
> are only in the operator's project folder.

### Step 4 — Integrate Workflows

```bash
cd werkzeuge
# adapt target host/project in agent-import-only.sh + import-agent-prepare.py
bash agent-import-only.sh /tmp/radio-agent-import.json
```

The script needs **all three** files from step 3
(`/tmp/radio-konfiguration.json`, `/tmp/radio-werkzeuge-import.json`,
`/tmp/radio-agent-import.json`) and aborts otherwise.

**Expected result:** n8n restarts (~20 s) and then lists **five active workflows** with
no error in its output:

```bash
ssh <your-n8n-host> "docker exec -u node n8n n8n list:workflow"   # 5 lines, all active
```

The test entry webhook answers `⛔ Kein Zugang.` with an **invalid** key and with a bot
reply when the key is right — the call and the expected output are in `DOCS/OPERATIONS.md` §3.

Afterwards:
* Check the test entry webhook — see `DOCS/OPERATIONS.md` §3 for the call and the expected output
* Enable the operator: `python3 erlaubte-setzen.py <chatId>`
* Set bot data: `python3 bot-data-set.py`
* Telegram menu: `bash telegram-menu.sh`

### Step 5 — Set Up the Station

Follow `station-setup.md`: Station, Mount, Streamer access, Playlist,
DJ port, settings (including `request_threshold = 0`, `enable_streamers = 1`).

### Step 6 — Load Music Archive

Place music in the station's media folder (in the original `/mnt/Content/Music`),
let AzuraCast import it, then fill the catalog service:

```bash
curl -s -X POST -H "X-News-Key: <key>" http://127.0.0.1:8881/catalog/refresh
curl -s http://127.0.0.1:8881/catalog/status      # number of titles in the search index
```

### Step 7 — Verify Everything

Order (details in `../DOCS/OPERATIONS.md`):

```bash
bash short-test.sh          # 19 of 19
bash answer-test.sh       # 20 ok
bash playlist/11-service-type-test.sh          # 37 of 37
python3 news/19-news-test.py       # 45 ok   (needs the service)
python3 news/21-bot-news-test.py   # 6 ok    (braucht n8n + Testeingang)
bash bot-test.sh "what is playing"                 # Antwort in ~1–2 s
python3 news/24-live-level.py "Test of the volume."   # speaks on air
```

### Step 8 — Personal Voice (optional)

Those who want to speak announcements with a transformed voice (RVC) build it according to
`own-voice/README.md`: separate raw material (voice service, port 8890), get confirmation from the operator,
collect pure pieces (`extend-voice.py`), train the model (`rvc-train.sh <your-model> … 400 8`), start the speech service `sprechdienst` (port 10205)
— short test:

```bash
curl -s -X POST http://127.0.0.1:10205/tts -H 'Content-Type: application/json' \
  -d '{"text":"Test"}' -o /tmp/probe.wav -w "%{http_code}\n"
```

The integration is **complete**: The service uses `deine-stimme` as a template
(`TTS_DEFAULT_VOICE`, step 1); without a voice service, a Piper template suffices (`TTS_DEFAULT_VOICE=de_thorsten`). Details: `own-voice/README.md`, section 8.
A **general** guide (each Serie/Stimme, all values and commands): `../DOCS/VOICE.md`.

---

## 3. What the Folder Contains

| Folder | Content |
| --- | --- |
| `service/` *(in the project folder, `../service/`)* | the modules of the speech service (`main.py`, `catalog.py`, `playlist.py`, `news.py`, `search.py`), `Dockerfile`, `docker-compose.yml`, `secret.env.template`, `whisper/` (fallback speech recognition), `whisper-amd/` (speech recognition on the MI50) |
| `tools/` *(in the project folder, `../tools/`)* | all operation, build, and test scripts (over 100 files) |
| `credentials.md` | which access credentials are needed and how they are created |
| `environment.md` | containers, IPs, ports, services, reverse proxy |
| `station-setup.md` | set up the station (AzuraCast) |
| `voices-and-models.md` | voices and models: sources, sizes, configuration |
| `fetch-voices.sh` | loads the four Piper voices into a target directory |
| `own-voice/` | **rebuild your own voice**: Extraction service (8890), collector (`deine-stimme_sammeln3/4/5.py`), training script, speech service (10205), test tools — guide in the folder |
| `running-workflows/` | **the exports of the running workflows** (exact restoration; include access values, 700/600) |
| `credentials/` | **the actual access values** (700/600; placeholders in the published copy) with `OVERVIEW.md`: Telegram token, chat IDs, mailbox and test keys, AzuraCast keys, DJ password, `secret.env`, n8n access, SSH keys |

**Included but handle with care:** `credentials/` and
`running-workflows/` — both contain the actual access values (permissions 700/600).

**Intentionally not included:** the music archive, the model binary files (too large) and
the backups of the n8n database (`n8n-daten.sqlite.gz`, see
`<projektordner>/sicherungen/radio-fassungen/` outside the project).

---

## 4. Replication Verification

A rebuild is successful if:

1. `layout-check.py` reports **0 findings** (identical surface),
2. `HTTP 200` from `/health` with `"stimmen": 4`,
3. `/katalog/status` names the number of titles from the own archive,
4. the test runs from step 7 are green,
5. a title request in Telegram runs in **1–2 s** and
6. an announcement on the radio is audible (volume: around −11.8 LUFS on broadcast, see
   `../DOCS/MANUAL.md`, section 2).

---

## 5. What Can Be Different

* **Voice**: The default is the **own speaker voice `deine-stimme`** (external, `own-voice/`);
  without voice service, set `TTS_DEFAULT_VOICE` to a Piper voice (short names in
  `service/app/main.py`). If the voice service fails, `radio-tts` continues with
  `EIGENE_STIMME_ERSATZ` (default `de_thorsten`).
* **Model**: `OLLAMA_MODELL` — it must only handle tools (Function Calling).
  Tested are `qwen3.6:27b` (recommended) and `qwen2.5:14b` (less reliable).
* **Station**: every AzuraCast installation with Liquidsoap/AutoDJ works; it must
  meet the requirements listed under `station-setup.md` (DJ Harbor,
  API key).
* **Music**: the bot adapts to the own archive (rebuild catalog index).
* **Addresses**: all IPs/Ports are available as environment variables or in the catalog data
  of the workflows; in the original: service `192.168.178.53:8881`, n8n `:5678`,
  Ollama `192.168.178.187:11434`, Whisper `192.168.178.188:8000`,
  station `192.168.178.33`.

---

## 6. What **cannot** be in a folder

> **The access data is now in the folder** — in `credentials/`
> (directory 700, files 600, with `OVERVIEW.md`). Anyone who shares the folder
> shares the bot: Telegram token, station key, DJ password,
  inbox-/Testschlüssel and the SSH keys. For a release without secrets,
  simply omit `credentials/`.

1. **The music archive**. The bot needs it content-wise; the
   structure is free. → own backup.
2. **The model and voice binary files** (Voice models 200 MB,
   Whisper large-v3 ~3 GB, Ollama model 17.7 GB). → Download instructions.
3. **The station database** (playlists, users, history). → AzuraCast backup
   (`azuracast_cli backup`) or rebuild according to `station-setup.md`.
4. **The runtime state** (mail queue `/daten/meldungen.json`, open selections,
   n8n-running jobs) — it is created automatically.
5. **The running n8n database** — in the original additionally as `n8n-daten.sqlite.gz`
   in each version backed up; without it, the workflows are re-imported (Step 4).
6. **Raw material, dataset, and model of the own speaker voice** — come from
   external productions (own copy needed) and remain (like the music archive) outside
   the folder; the rebuild from the own stock is described in `own-voice/README.md`.

---

## 7. Proof of rebuild (created 2026-09-20; workflows and syntax re-checked 2026-09-24)

| Test | Result |
| --- | --- |
| Building workflows (`python3 tools/agent-wf-build.py`) | Bot with 83 nodes + 3 tools, all connections verified |
| Canvas (`python3 tools/layout-check.py /tmp/radio-*.json`) | **0 findings** |
| Python syntax of all modules (`compileall`) | in order |
| `docker compose config` with the template | valid, all variables resolved |
| `docker build` from `service/` | Image built (base `python:3.12-slim` + piper-tts, fastapi, lameenc) |
| Test start of image (different port, voices included) | `/health` → `{"status":"ok","stimmen":4,"standard":"de_thorsten"}` *(since 2026-09-25: default `de_thorsten`, YOUR-VOICE on request — see Step 8)* |
| Speech output of test (`POST /v1/audio/speech`) | HTTP 200, 56 kB WAV |
| Loading voices (`fetch-voices.sh`) and **checksums** comparison | 4 voices, md5 **identical** with the running system |

This proves: the **build and runtime files are complete** and functional. Only the three things from Section 6 (access data, Modell-/Stimmendateien,
music archive) are missing — all three with instructions.
