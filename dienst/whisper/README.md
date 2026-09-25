# Spracherkennung (`whisper_server.py`)

Dieses Modul läuft **nicht** im Dienst `radio-tts`, sondern als eigener kleiner Dienst
auf der GPU-Maschine — im Original in LXC 105 (`192.168.178.187`), Port **18790**.

Es ist die Quelle für den Zweig „Sprachnachricht" des Bots: der Bot lädt die
Sprachnachricht von Telegram, schickt sie hierher und bekommt den Text zurück.

---

## Aufruf

```bash
python3 whisper_server.py --port 18790 --model large-v3
```

* `--model`: alles, was `faster-whisper` kennt (`large-v3` ist eingestellt; das Modell
  wird beim ersten Aufruf von HuggingFace geladen, ~3 GB)
* `--port`: Standard 18790
* Sprache: **fest `de`** über den Parameter `language` (Autokennung verhörte kurze
  deutsche Sätze als Englisch)
* `prompt`: Fachhinweis — der Bot schickt die häufigsten Interpreten aus dem Katalog
  mit, damit Namen wie „Nirvana" oder „die Ärzte" korrekt ankommen

## Schnittstelle

| Adresse | Eingabe | Antwort |
| --- | --- | --- |
| `POST /transcribe` | multipart: `file`, `language` (Standard `de`), `prompt` | `{"text": "…", "language": "de"}` |
| `GET /health` | — | Zustand |

## systemd-Unit (Original)

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
Environment=PATH=/usr/bin:/usr/local/bin
Environment=PYTHONUNBUFFERED=1
Environment=LD_LIBRARY_PATH=/usr/lib/ollama/cuda_v12
```

```bash
mkdir -p /root/whisper-stt
cp whisper_server.py /root/whisper-stt/
python3 -m pip install faster-whisper
systemctl enable --now whisper-stt
curl -s http://127.0.0.1:18790/health
```

## Prüfen

```bash
# Eine Ansage erzeugen und zurück transkribieren (Selbsttest)
curl -s -X POST http://<dienst>:8881/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input":"Die Sendung beginnt in fünf Minuten.","voice":"","response_format":"wav"}' \
  -o /tmp/probe.wav
curl -s -X POST http://<gpu-maschine>:18790/transcribe \
  -F "file=@/tmp/probe.wav" -F "language=de"
# erwartet: ungefähr derselbe Satz als Text
```

Aus dem Projekt gibt es dafür `werkzeuge/sprache-test.sh` und
`werkzeuge/stimme-pruefen.sh` (letzteres sucht eine Sprachprobe, die sauber verstanden
wird).
