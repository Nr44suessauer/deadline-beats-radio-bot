# Infrastruktur (Umgebung)

So sieht die Umgebung des laufenden Bots aus. Für einen Nachbau sind die **Rollen**
wichtig, nicht die konkreten IPs.

---

## 0. Grundlage: Proxmox, Container, GPU

Die Zahlen oben gelten für die Umgebung des Originals. Wer sie nachbaut, braucht
drei Dinge, die hier in Kurzform stehen (die ausführlichen Fassungen stehen in der
Proxmox-Dokumentation):

### Container anlegen

Proxmox VE 8, Vorlage Debian 12 (`pveam available` / `pveam download local <vorlage>`).
Docker im Container braucht **`nesting=1`** und **`keyctl=1`**:

```bash
pct create 103 local:vztmpl/<debian-12-vorlage> \
  --hostname radio-bot --cores 4 --memory 4096 --rootfs local-lvm:20 \
  --features nesting=1,keyctl=1 --unprivileged 1 --onboot 1
pct set 103 --net0 name=eth0,bridge=vmbr0,ip=<eigene-ip>/24,gw=<gateway>
pct start 103
pct exec 103 -- apt-get update && pct exec 103 -- apt-get install -y docker.io docker-compose-v2
```

Dieselbe Bauart für die GPU-Maschine (mehr RAM/Platte, GPU), die Sender-Maschine
(Musikordner als `mp0`-Bind, z. B. `pct set 106 -mp0 /mnt/Content,mp=/mnt/Content`) und
die Suchmaschine. `nesting=1` ist auch für den AzuraCast-Container nötig.

### GPU in den Container durchreichen

Damit gilt: **auf dem Host** läuft der NVIDIA-Treiber, **im Container** sieht man die
Karte, und die **Userspace-Bibliotheken passen zur Treiberversion des Hosts**.

```bash
nvidia-smi                       # auf dem Host: Karte und Treiberversion
pct exec 105 -- nvidia-smi       # im Container: dieselbe Karte
```

Für Schritt zwei sind die Gerätedateien (`/dev/nvidia0`, `/dev/nvidiactl`,
`/dev/nvidia-uvm`, …) und die Bibliotheken des Hosts in den Container zu bringen —
Vorgehen und Fallstricke stehen in der Proxmox-Dokumentation („PCI(e) Passthrough")
und in `DOKU/BETRIEB.md` §7 (zu wenig Grafikspeicher, `CUDA out of memory`).

### Netz und Erreichbarkeit

Feste Adressen im eigenen Netz (im Original `192.168.178.x`). Für die
Telegram-**Auslöser** muss der n8n-Rechner aus dem Internet erreichbar sein
(Portfreigabe oder Umkehrschluss auf einen eigenen Namen) — Betreiber und Bot
sprechen sonst nur aus dem eigenen Netz mit dem Bot. Der Name des Originals ist durch
`DEIN-N8N-HOST` ersetzt.

---

## 1. Die vier Maschinen

| Rolle | Im Original | Aufgabe | Mindestausstattung |
| --- | --- | --- | --- |
| **Bot-Maschine** | LXC 103 auf `ai-server` (`192.168.178.53`) | n8n (Port 5678) **und** Dienst `radio-tts` (Port 8881) | 4 Kerne, 4 GB RAM, 20 GB Platte |
| **GPU-Maschine** | LXC 105 auf `ai-server` (`192.168.178.187`) | Ollama (11434) + faster-whisper (18790) | GPU ab 8 GB VRAM (Original: RTX 3090 Ti 24 GB), 32 GB RAM |
| **Sender-Maschine** | LXC 106 auf Datenserver (`192.168.178.163`), Web `http://192.168.178.33` | AzuraCast (Icecast 8000, Liquidsoap/AutoDJ, DJ-Hafen 8005, API) | 4 Kerne, 2 GB RAM, Musikspeicher |
| **Suchmaschine** | LXC 108 auf `ai-server` (`192.168.178.26`, Port 8888) | SearXNG für den Themen-Überblick (Einrichtung: `searxng-einrichten.md`) | 2 Kerne, 1 GB RAM, 10 GB Platte |
| **Arbeitsplatz/Verwaltung** | Debian-Desktop (dieser Rechner) | Werkzeuge, Sicherungen, Prüfläufe, Doku | – |

Alle Container sind **unprivileged** LXC-Container; die SSH- und `pct`-Befehle der
Werkzeuge gehen über `~/.ssh/config` (Alias
`ai-server`) und direkt per Schlüssel auf den Datenserver.

---

## 2. Ports und Dienste

| Dienst | Adresse | Zweck |
| --- | --- | --- |
| n8n | `192.168.178.53:5678` (Web: `https://DEIN-N8N-HOST`) | der Bot selbst |
| n8n-Testeingang | `…/webhook/DEIN-WEBHOOK-PFAD?schluessel=…` | Prüfläufe ohne Telegram |
| Dienst `radio-tts` | `192.168.178.53:8881` | Sprache, Ansage, Katalog, Listen, Postfach, Recherche |
| Eigene Suchmaschine | `192.168.178.26:8888` (SearXNG, JSON) | „normale Internetseiten" für den Themen-Überblick |
| Ollama | `192.168.178.187:11434` | Sprachmodell `qwen3.6:27b` |
| faster-whisper | `192.168.178.187:18790` | Spracherkennung |
| AzuraCast-Web | `192.168.178.33:80/443` | Senderoberfläche und API |
| Icecast (Hörer) | `192.168.178.33:8000` | Stream (`/radio.mp3`) |
| DJ-Hafen | `192.168.178.33:8005`, Mount `/` | hier spricht die Moderation hinein |
| ComfyUI (vorhanden, nicht nötig) | `192.168.178.187:8188` | Bildwerkzeuge der GPU-Maschine |

Der Sender veröffentlicht zusätzlich Sender-Mounts auf den Ports 8005–8496 (je Sender
und Mount). Der Bot nutzt nur 8005 (Sprechen) und 8000 (Hören).

---

## 3. Container und Verzeichnisse (Original)

**Bot-Maschine (LXC 103)**

```
/opt/radio-tts/            Dienst (docker compose)
├── app/                   main.py, katalog.py, playlist.py, meldungen.py, suche.py
├── Dockerfile
├── docker-compose.yml
├── geheim.env             (600) DJ-Hafen + Lautstärke-Regelwerte
├── voices/                Piper-Stimmen (201 MB, 4 Stimmen)
└── daten/                 katalog.json (44 MB) und meldungen.json (Postfach)
```

n8n läuft als eigener Container (`n8n`, `n8n-runners`, `n8n-redis`,
`n8n-pushgateway`) mit dem Datenvolumen `n8n_data`
(`/var/lib/docker/volumes/n8n_data/_data/database.sqlite`).

**GPU-Maschine (LXC 105)**

```
/root/whisper-stt/whisper_server.py + systemd-Unit whisper-stt.service
/root/.cache/huggingface/…       Whisper-Modell (large-v3, ~3 GB)
/mnt/Storage                     Ollama-Modelle (OLLAMA_MODELS)
```

**Sender-Maschine (LXC 106)**

```
/var/azuracast/                  AzuraCast-Installation (docker compose)
/var/azuracast/stations/deadline_beats/config/   Liquidsoap-Konfiguration und Protokolle
/var/azuracast/dj_passwort.txt   (600) Betreiber-DJ-Zugang (Notbehelf)
/var/azuracast/bot_streamer_passwort.txt  (600) Ansagekonto des Bots (DEINE-STIMME)
/mnt/Content/Music               Musikarchiv (Bind → /data im Container)
```

---

## 4. Beispielhafte Diensteinheiten

**whisper-stt.service** (GPU-Maschine):

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

**ollama.service.d/override.conf** (GPU-Maschine):

```ini
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_KEEP_ALIVE=30m"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_MODELS=/mnt/Storage"
```

`OLLAMA_KEEP_ALIVE=30m` ist wichtig: ein Neuladen des Modells kostet gemessen
**43,7 s** — im Bot ist das die erste Antwort nach einer Pause.

---

## 5. Zugriffswege der Werkzeuge

| Weg | Befehl (Original) |
| --- | --- |
| Bot-Maschine | `ssh -F ~/.ssh/config ai-server "pct exec 103 -- …"` |
| In den Dienst | `… pct exec 103 -- docker exec radio-tts …` |
| In n8n | `… pct exec 103 -- docker exec -u node n8n n8n …` |
| GPU-Maschine | `ssh -F … ai-server "pct exec 105 -- …"` |
| Sender | `ssh -i ~/.ssh/id_ed25519 root@192.168.178.163 "pct exec 106 -- docker exec azuracast …"` |

Bei einem Nachbau passen die Skripte auf die eigenen Adressen an — die Stellen stehen
als Kopfzeilen (`CFG=…`, `PROJEKT=…`) in den jeweiligen Skripten.

---

## 6. Netz und Sicherheit

* Der n8n-Testeingang ist **über das Internet** erreichbar (über
  `DEIN-N8N-HOST`) — deshalb verlangt er einen Schlüssel.
* Die Telegram-Anbindung läuft **ausgehend** von n8n (Polling ist nicht im Einsatz,
  der Ablauf nutzt einen Telegram-Auslöser mit Webhook).
* Der Dienst `radio-tts` und die GPU-Dienste liegen im lokalen Netz ohne
  Verschlüsselung; ein Nachbau sollte sie nicht öffentlich erreichbar machen.
* Der Sender (AzuraCast) ist über HTTP im lokalen Netz erreichbar (Port 80/443).
