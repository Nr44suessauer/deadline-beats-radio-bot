# Infrastructure (Environment)

This is what the environment of the running bot looks like. For a rebuild, the **roles**
are important, not the specific IPs.

---

## 0. The base: Proxmox, containers, GPU

The figures above describe the original setup. Anyone rebuilding it needs three things
that are summarised here (the full versions are in the Proxmox documentation):

### Create containers

Proxmox VE 8, Debian 12 template (`pveam available` / `pveam download local <template>`).
Docker inside a container needs **`nesting=1`** and **`keyctl=1`**:

```bash
pct create 103 local:vztmpl/<debian-12-template> \
  --hostname radio-bot --cores 4 --memory 4096 --rootfs local-lvm:20 \
  --features nesting=1,keyctl=1 --unprivileged 1 --onboot 1
pct set 103 --net0 name=eth0,bridge=vmbr0,ip=<your-ip>/24,gw=<gateway>
pct start 103
pct exec 103 -- apt-get update && pct exec 103 -- apt-get install -y docker.io docker-compose-v2
```

Build the GPU machine (more RAM/disk, GPU), the station machine (music folder as a bind
mount, e.g. `pct set 106 -mp0 /mnt/Content,mp=/mnt/Content`) and the search engine the
same way. `nesting=1` is also required for the AzuraCast container.

### Pass the GPU into the container

What must hold: the NVIDIA driver runs **on the host**, the container **sees the card**,
and the **user-space libraries match the host driver version**.

```bash
nvidia-smi                       # on the host: card and driver version
pct exec 105 -- nvidia-smi       # inside the container: the same card
```

For the second part the device files (`/dev/nvidia0`, `/dev/nvidiactl`, `/dev/nvidia-uvm`,
…) and the host libraries have to reach the container — the procedure and the pitfalls
are in the Proxmox documentation ("PCI(e) Passthrough") and in `DOCS/OPERATIONS.md` §7 (too
little VRAM, `CUDA out of memory`).

### Network and reachability

Fixed addresses on your own network (the original uses `192.168.178.x`). For the Telegram
**triggers** the n8n machine must be reachable from the internet (port forwarding or a
tunnel to an own hostname) — otherwise operator and bot can only talk to the bot from the
local network. The original's hostname is replaced by `YOUR-N8N-HOST`.

---

## 1. The Four Machines

| Role | Original | Purpose | Minimum Setup |

| --- | --- | --- | --- |

| **Bot Machine** | LXC 103 on `ai-server` (`192.168.178.53`) | n8n (Port 5678) **and** Service `radio-tts` (Port 8881) | 4 cores, 4 GB RAM, 20 GB disk |

| **GPU Machine** | LXC 105 on `ai-server` (`192.168.178.187`) | Ollama (11434) + faster-whisper (18790) | GPU with at least 8 GB VRAM (Original: RTX 3090 Ti 24 GB), 32 GB RAM |

| **Transmitter Machine** | LXC 106 on Data Server (`192.168.178.163`), Web `http://192.168.178.33` | AzuraCast (Icecast 8000, Liquidsoap/AutoDJ, DJ Port 8005, API) | 4 cores, 2 GB RAM, music storage |

| **Search Engine** | LXC 108 on `ai-server` (`192.168.178.26`, Port 8888) | SearXNG for topic overview (Setup: `searxng-setup.md`) | 2 cores, 1 GB RAM, 10 GB disk |

| **Arbeitsplatz/Verwaltung** | Debian Desktop (this machine) | Tools, backups, tests, documentation | – |

All containers are **unprivileged** LXC containers; the SSH and `pct` commands of the
tools go through `~/.ssh/config` (Alias
`ai-server`) and directly via key to the data server.

---

## 2. Ports and Services

| Service | Address | Purpose |

| --- | --- | --- |

| n8n | `192.168.178.53:5678` (Web: `https://YOUR-N8N-HOST`) | the bot itself |

| n8n Test Input | `…/webhook/YOUR-WEBHOOK-PATH?schluessel=…` | test runs without Telegram |

| Service `radio-tts` | `192.168.178.53:8881` | language, announcements, catalog, lists, mailbox, research |

| Custom Search Engine | `192.168.178.26:8888` (SearXNG, JSON) | "normal web pages" for topic overview |

| Ollama | `192.168.178.187:11434` | language model `qwen3.6:27b` |

| faster-whisper | `192.168.178.187:18790` | speech recognition |

| AzuraCast Web | `192.168.178.33:80/443` | web interface and API |

| Icecast (Listeners) | `192.168.178.33:8000` | stream (`/radio.mp3`) |

| DJ Port | `192.168.178.33:8005`, Mount `/` | here moderation speaks in |

| ComfyUI (present, not necessary) | `192.168.178.187:8188` | image tools of the GPU machine |

The transmitter publishes additional transmitter mounts on ports 8005–8496 (per transmitter
and mount). The bot uses only 8005 (Speaking) and 8000 (Listening).

---

## 3. Containers and Directories (Original)

**Bot Machine (LXC 103)**

```
/opt/radio-tts/            Dienst (docker compose)
├── app/                   main.py, catalog.py, playlist.py, news.py, search.py
├── Dockerfile
├── docker-compose.yml
├── secret.env             (600) DJ port + volume control values
├── voices/                Piper-Stimmen (201 MB, 4 Stimmen)
└── daten/                 catalog.json (44 MB) and news.json (inbox)
```

n8n runs as its own container (`n8n`, `n8n-runners`, `n8n-redis`,
`n8n-pushgateway`) with the data volume `n8n_data`
(`/var/lib/docker/volumes/n8n_data/_data/database.sqlite`).

**GPU Machine (LXC 105)**

```
/root/whisper-stt/whisper_server.py + systemd-Unit whisper-stt.service
/root/.cache/huggingface/…       Whisper-Modell (large-v3, ~3 GB)
/mnt/Storage                     Ollama-Modelle (OLLAMA_MODELS)
```

**Transmitter Machine (LXC 106)**

```
/var/azuracast/                  AzuraCast-Installation (docker compose)
/var/azuracast/stations/deadline_beats/config/   Liquidsoap configuration and logs
/var/azuracast/dj_passwort.txt   (600) Betreiber-DJ-Zugang (Notbehelf)
/var/azuracast/bot_streamer_passwort.txt  (600) announcement account of the bot (YOUR-VOICE)
/mnt/Content/Music               Musikarchiv (Bind → /data im Container)
```

---

## 4. Example Service Units

**whisper-stt.service** (GPU Machine):

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
Environment=PYTHONUNBUFFERED=1
Environment=LD_LIBRARY_PATH=/usr/lib/ollama/cuda_v12
```

**ollama.service.d/override.conf** (GPU Machine):

```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_KEEP_ALIVE=30m"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_MODELS=/mnt/Storage"
```

`OLLAMA_KEEP_ALIVE=30m` is important: reloading the model takes **43.7 seconds** — in the bot, this is the first response after a pause.

---

## 5. Tool Access Paths

| Path | Command (Original) |

| --- | --- |

| Bot Machine | `ssh -F ~/.ssh/config ai-server "pct exec 103 -- …"` |

| Into the Service | `… pct exec 103 -- docker exec radio-tts …` |

| Into n8n | `… pct exec 103 -- docker exec -u node n8n n8n …` |

| GPU Machine | `ssh -F … ai-server "pct exec 105 -- …"` |

| Transmitter | `ssh -i ~/.ssh/id_ed25519 root@192.168.178.163 "pct exec 106 -- docker exec azuracast …"` |

For a rebuild, the scripts adapt to the own addresses — the places are noted as header lines (`CFG=…`, `PROJEKT=…`) in the respective scripts.

---

## 6. Network and Security

* The n8n test input is **reachable over the internet** (via
  `YOUR-N8N-HOST`) — that's why it requires a key.
* The Telegram connection runs **outgoing** from n8n (Polling is not in use,
  the workflow uses a Telegram trigger with webhook).
* The service `radio-tts` and the GPU services are in the local network without
  encryption; a rebuild should not make them publicly accessible.
* The transmitter (AzuraCast) is reachable over HTTP in the local network (Port 80/443).