# whisper-amd — Spracherkennung auf der MI50 (Container 112)

Whisper **large-v3** über **whisper.cpp mit Vulkan** auf der Radeon Instinct MI50 (32 GB).
Ersetzt für den Radiobot den Dienst auf CT 105 (faster-whisper auf der RTX 3090 Ti) — die
3090 Ti bleibt damit für Sprachmodell, ComfyUI und RVC frei.

| | |
| --- | --- |
| Ort | LXC **112** „whisper-amd“ auf dem ai-server (**192.168.178.188**), Ubuntu 24.04 |
| Grafik | Radeon Instinct MI50 (Vulkan/RADV), durchgereicht über `/dev/dri` |
| Aufbau | `whisper-server` (127.0.0.1:8081, Modell large-v3, Vulkan) + Brücke `whisper_amd.py` (Port **8000**) |
| Schnittstelle | `POST /transcribe` (multipart: `file`, `language`, `prompt`) → `{text, language}`; `GET /health` |
| Quellen | `dienst/whisper_amd.py` (Brücke), `dienst/whisper-amd/` (Einheiten, Einspielen, diese Doku) |

Die Brücke hat **dieselbe Schnittstelle** wie `whisper_server.py` (CT 105). Der Bot tauscht nur
die Adresse: im n8n-Ablauf **„Konfiguration“** unter `sprache.adresse`
(`http://192.168.178.188:8000/transcribe`).

## Einmalige Einrichtung im Container (nachvollziehbar)

```bash
CFG=~/.ssh/config
SSH='ssh -F $CFG ai-server pct exec 112 -- bash -lc'

# 1) Pakete
$SSH 'export DEBIAN_FRONTEND=noninteractive
      apt-get update -qq
      apt-get install -y -qq build-essential cmake git libvulkan-dev vulkan-tools \
                            glslc spirv-headers ffmpeg curl ca-certificates'

# 2) whisper.cpp mit Vulkan bauen (Mesa/RADV kommt aus mesa-vulkan-drivers)
$SSH 'git clone --depth 1 https://github.com/ggml-org/whisper.cpp /opt/whisper.cpp
      cd /opt/whisper.cpp
      cmake -B build -DGGML_VULKAN=ON -DCMAKE_BUILD_TYPE=Release
      cmake --build build -j4 --config Release'

# 3) Modell (3,1 GB)
$SSH 'mkdir -p /opt/whisper-models
      curl -L -o /opt/whisper-models/ggml-large-v3.bin \
        https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin'
```

Auf dem **Host** mussten die Render-Knoten zugaenglich gemacht werden (unprivilegierter Container,
`/dev/dri/renderD129` = MI50 war nur `root:render` 660):

```
/etc/udev/rules.d/99-dri-render-666.rules:
  SUBSYSTEM=="drm", KERNEL=="renderD*", MODE="0666"
```

Durchreichung im Container 112 (`/etc/pve/lxc/112.conf`):

```
lxc.cgroup2.devices.allow: c 226:* rwm
lxc.mount.entry: /dev/dri dev/dri none bind,optional,create=dir
```

## Einspielen / Ändern

`bash dienst/whisper-amd/einrichten.sh` — kopiert `whisper_amd.py` und die systemd-Einheiten in
den Container und startet `whisper-cpp` + `whisper-bruecke` neu.

## Prüfen

```bash
CFG=~/.ssh/config

# Zustand
ssh -F $CFG ai-server "pct exec 112 -- curl -s http://127.0.0.1:8000/health"
ssh -F $CFG ai-server "pct exec 112 -- systemctl --no-pager status whisper-cpp whisper-bruecke | grep -E 'Active|Loaded'"
ssh -F $CFG ai-server "pct exec 112 -- journalctl -u whisper-cpp -n 20 --no-pager"   # Vulkan-Geraet?

# Probe (deutsche Ansage erzeugen und durch die Kette schicken)
curl -s -X POST http://192.168.178.53:8881/v1/audio/speech -H 'Content-Type: application/json' \
  -d '{"input":"Spiele bitte Benzin von Rammstein und danach etwas ruhiges von Nirvana","response_format":"wav"}' \
  -o /tmp/probe.wav
cat /tmp/probe.wav | ssh -F $CFG ai-server \
  "pct exec 112 -- curl -s -X POST http://127.0.0.1:8000/transcribe \
     -F file=@- -F language=de"
```
