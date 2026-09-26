# whisper-amd — speech recognition on the MI50 (container 112)

Whisper **large-v3** via **whisper.cpp with Vulkan** on the Radeon Instinct MI50 (32 GB).
Replaces the service on CT 105 (faster-whisper on the RTX 3090 Ti) for the radio bot — the
3090 Ti is thereby free for the language model, ComfyUI and RVC.

| | |
| --- | --- |
| Location | LXC **112** "whisper-amd" on the ai-server (**192.168.178.188**), Ubuntu 24.04 |
| Graphics | Radeon Instinct MI50 (Vulkan/RADV), passed through via `/dev/dri` |
| Setup | `whisper-server` (127.0.0.1:8081, model large-v3, Vulkan) + bridge `whisper_amd.py` (port **8000**) |
| Interface | `POST /transcribe` (multipart: `file`, `language`, `prompt`) → `{text, language}`; `GET /health` |
| Sources | `service/whisper_amd.py` (bridge), `service/whisper-amd/` (units, deployment, this document) |

The bridge has **the same interface** as `whisper_server.py` (CT 105). The bot only swaps the
address: in the n8n workflow **"Configuration"** under `sprache.adresse`
(`http://192.168.178.188:8000/transcribe`).

## One-off setup in the container (traceable)

```bash
CFG=~/.ssh/config
SSH='ssh -F $CFG ai-server pct exec 112 -- bash -lc'

# 1) packages
$SSH 'export DEBIAN_FRONTEND=noninteractive
      apt-get update -qq
      apt-get install -y -qq build-essential cmake git libvulkan-dev vulkan-tools \
                            glslc spirv-headers ffmpeg curl ca-certificates'

# 2) build whisper.cpp with Vulkan (Mesa/RADV comes from mesa-vulkan-drivers)
$SSH 'git clone --depth 1 https://github.com/ggml-org/whisper.cpp /opt/whisper.cpp
      cd /opt/whisper.cpp
      cmake -B build -DGGML_VULKAN=ON -DCMAKE_BUILD_TYPE=Release
      cmake --build build -j4 --config Release'

# 3) model (3.1 GB)
$SSH 'mkdir -p /opt/whisper-models
      curl -L -o /opt/whisper-models/ggml-large-v3.bin \
        https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin'
```

On the **host** the render nodes had to be made accessible (unprivileged container,
`/dev/dri/renderD129` = MI50 was only `root:render` 660):

```
/etc/udev/rules.d/99-dri-render-666.rules:
  SUBSYSTEM=="drm", KERNEL=="renderD*", MODE="0666"
```

Passing through in container 112 (`/etc/pve/lxc/112.conf`):

```
lxc.cgroup2.devices.allow: c 226:* rwm
lxc.mount.entry: /dev/dri dev/dri none bind,optional,create=dir
```

## Deploying / changing

`bash service/whisper-amd/einrichten.sh` — copies `whisper_amd.py` and the systemd units into
the container and restarts `whisper-cpp` + `whisper-bruecke`.

## Checking

```bash
CFG=~/.ssh/config

# status
ssh -F $CFG ai-server "pct exec 112 -- curl -s http://127.0.0.1:8000/health"
ssh -F $CFG ai-server "pct exec 112 -- systemctl --no-pager status whisper-cpp whisper-bruecke | grep -E 'Active|Loaded'"
ssh -F $CFG ai-server "pct exec 112 -- journalctl -u whisper-cpp -n 20 --no-pager"   # Vulkan device?

# test (generate a German announcement and push it through the chain)
curl -s -X POST http://192.168.178.53:8881/v1/audio/speech -H 'Content-Type: application/json' \
  -d '{"input":"Spiele bitte Benzin von Rammstein und danach etwas ruhiges von Nirvana","response_format":"wav"}' \
  -o /tmp/probe.wav
cat /tmp/probe.wav | ssh -F $CFG ai-server \
  "pct exec 112 -- curl -s -X POST http://127.0.0.1:8000/transcribe \
     -F file=@- -F language=de"
```
