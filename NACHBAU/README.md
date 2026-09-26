# Replikation — den Bot vollständig nachbauen

Diese Anleitung baut den Bot auf **neuer Hardware** (oder nach einem Totalverlust)
so nach, dass er sich wie der laufende verhält. Alles dafür Nötige liegt als Kopie in
diesem Ordner; was **nicht** in einem Ordner liegen kann, steht in Abschnitt 6.

**Kurzantwort auf „ist alles da?"**

| Bereich | Im Ordner? |
| --- | --- |
| Abläufe (Bot + 3 Werkzeuge) | **ja, als Erzeuger** — werden beim Aufbau neu gebaut (`werkzeuge/agent-wf-bauen.py`) |
| Dienst `radio-tts` (Sprache, Ansage, Katalog, Listen, Postfach, Recherche) | **ja** — `dienst/` (Module, `Dockerfile`, `docker-compose.yml`) |
| Betriebs- und Prüfwerkzeuge (über 100 Skripte) | **ja** — `werkzeuge/` |
| Stimmen und Modelle | **Anleitung + Download-Skript** (`stimmen-holen.sh`, `stimmen-und-modelle.md`) — die Dateien selbst sind 0,2–18 GB groß |
| Eigene Sprecherstimme (RVC „DEINE-STIMME") | **ja** — `eigene-stimme/`: alle Skripte + Anleitung (`README.md`); Datensatz und Modell entstehen aus dem eigenen Medienbestand |
| Zugangsdaten | **Anleitung** — `zugangsdaten.md` (diese Fassung enthält keine Werte; eigene anlegen) |
| Musikarchiv | **nein** — der Inhalt selbst; der Bot läuft mit jedem eigenen Archiv |
| Senderkonfiguration | **Anleitung** — `sender-einrichten.md` |
| Eigene Suchmaschine (SearXNG, LXC 108) | **Anleitung** — `searxng-einrichten.md` |
| Infrastruktur (Container, IPs, Proxy) | **Anleitung** — `umgebung.md` |

---

## 1. Was man braucht

* Eine Maschine mit **Docker** und **Docker Compose** für den Dienst (im Original: LXC 103)
* **n8n** (v2.34.6) als Container (ebenfalls LXC 103, Port 5678) — samt Konto und
  eigener Projektkennung, siehe Schritt 3
* Eine Maschine mit **GPU** für Ollama **und** Spracherkennung (im Original: LXC 105
  auf `ai-server`, RTX 3090 Ti mit 24 GB). Das Standardmodell `qwen3.6:27b` belegt
  **17,7 GB** — dafür sind **24 GB VRAM** (oder ein kleineres Modell) nötig; „ab 8 GB"
  genügt nur, wenn ein kleines Modell gewählt wird (siehe `stimmen-und-modelle.md` §3)
* Einen **AzuraCast**-Sender (im Original 0.23.4, LXC 106 auf dem Datenserver). Läuft noch
  keiner, ist das der **erste** Schritt: `sender-einrichten.md` §0 (Installation, Konto,
  API-Schlüssel)
* **Proxmox VE** als Unterbau, falls Container genutzt werden: je Container `nesting=1`
  und `keyctl=1` (Docker darin), GPU-Maschine mit durchgereichter Karte — Anleitung und
  Prüfschritte in `umgebung.md` §0
* Einen kleinen Container (2 Kerne, 1 GB) für die **eigene Suchmaschine**
  (SearXNG, im Original LXC 108 auf `http://192.168.178.26:8888`) — ohne sie
  fragt der Dienst DuckDuckGo und Bing direkt, die aber Rechner ohne Anmeldung sperren
* Einen **Telegram-Bot** (Token von @BotFather) und die eigene Chat-ID
* Rund 100 GB Plattenplatz für Modelle und Stimmen (ohne Musikarchiv)
* Für die Telegram-Auslöser: der n8n-Rechner muss vom Internet aus erreichbar sein
  (Portfreigabe oder Umkehrschluss) — sonst **Webhook**-Betrieb statt Abfrage, siehe
  Schritt 3

**Betriebssystem:** Proxmox VE 8 mit Debian-12-Vorlagen; für die RVC-Maschine
Ubuntu 24.04 (`eigene-stimme/README.md` §0). **Zeitaufwand:** mit vorhandenem Sender,
Proxmox und GPU reicht ein langer Abend (Original: fünf Bautage, `DOKU/BAU.md` §1) — das
Trainieren einer eigenen Stimme kostet zusätzlich einen Abend.

Netzwerk im Original: siehe `umgebung.md` (feste IPs, Ports 5678, 8881, 8005, 8000,
11434, 8888 für die Suchmaschine).

---

## 2. Reihenfolge des Aufbaus

**Erst den Sender, dann den Dienst** — die Zugangsdatei des Dienstes enthält mit
`AZ_URL` und `AZ_KEY` die Adresse und den Schlüssel des Senders (siehe `dienst/README.md`,
Abschnitt „Zugangsdatei geheim.env"). Wo in den Schritten Beispielwerte stehen
(`192.168.x.x`, `DEIN-…`), sind die eigenen einzusetzen.

| # | Schritt | Ergebnis, das man sehen muss |
| --- | --- | --- |
| 0 | Sender installieren (`sender-einrichten.md` §0) | `GET /api/status` antwortet, Stream läuft |
| 1 | Dienst `radio-tts` aufsetzen | `/health` → `{"status":"ok","stimmen":4,…}` |
| 2 | Sprachmodelle auf der GPU-Maschine | Whisper antwortet, `ollama list` zeigt das Modell |
| 3 | n8n starten (Container, Konto, Projekt) | Oberfläche auf `:5678` erreichbar |
| 4 | Abläufe einspielen | 5 Abläufe aktiv, Testeingang antwortet |
| 5 | Musikarchiv einlesen | `katalog/status` zeigt Titel > 0 |
| 6 | Alles prüfen (`DOKU/BETRIEB.md`) | Erwartungstabelle 11 von 11 |
| 7 | Eigene Stimme (optional) | Hörprobe über `/tts` |

---

### Schritt 1 — Dienst `radio-tts` aufsetzen

```bash
# Verzeichnis wie im Original anlegen
mkdir -p /opt/radio-tts/{app,voices,daten}
cp dienst/*.py              /opt/radio-tts/app/
cp dienst/Dockerfile        /opt/radio-tts/
cp dienst/docker-compose.yml /opt/radio-tts/
cp dienst/geheim.env.vorlage /opt/radio-tts/geheim.env   # ausfüllen!
bash NACHBAU/stimmen-holen.sh /opt/radio-tts/voices              # Stimmen laden
cd /opt/radio-tts && docker compose up -d --build
curl -s http://127.0.0.1:8881/health        # {"status":"ok","stimmen":4,...}
```

> **Achtung, zwei Fallen in dieser Reihenfolge:**
> 1. In `geheim.env` gehören **`AZ_URL`** (Adresse des Senders) und **`AZ_KEY`**
>    (API-Schlüssel) — die Vorlage `dienst/geheim.env.vorlage` enthält beide
>    **nicht**, sie sind also von Hand zu ergänzen. Ohne sie fällt der Katalog
>    still auf eine Beispieladresse zurück.
> 2. Im `environment`-Block von `dienst/docker-compose.yml` stehen
>    `TTS_DEFAULT_VOICE`, `EIGENE_STIMME_URL` und `RECHERCHE_SEARX_URL`. Werte dort
>    **überschreiben** `geheim.env`. Für einen Nachbau ohne eigene RVC-Stimme die
>    Vorgabe auf eine Piper-Stimme setzen (`TTS_DEFAULT_VOICE=de_thorsten`) und die
>    beiden Adressen auf die eigenen Hosts zeigen lassen.

### Schritt 2 — Sprachmodelle auf der GPU-Maschine

```bash
# Ollama (Modell für Planen/Ausführen/Prüfen)
ollama pull qwen3.6:27b            # alternativ ein anderes Werkzeug-taugliches Modell
ollama list                        # muss das Modell zeigen
# Ollama-Dienst konfigurieren (siehe stimmen-und-modelle.md):
#   OLLAMA_HOST=0.0.0.0:11434  OLLAMA_KEEP_ALIVE=30m  OLLAMA_NUM_PARALLEL=1
curl -s http://127.0.0.1:11434/api/tags    # listet das Modell

# Spracherkennung — zwei Wege, gleiche Schnittstelle (POST /transcribe)
#   Weg 1 (einfachster Nachbau): whisper_server.py mit faster-whisper, Port 18790
#     -> Anleitung: dienst/whisper/README.md  (CUDA oder CPU, zieht ~3 GB Modell)
#   Weg 2 (im Original seit 2026-09-23): whisper.cpp large-v3 auf einer MI50,
#     LXC 112, Port 8000  -> DOKU/HANDBUCH.md §4.4, DOKU/BETRIEB.md §1
# Wichtig: derselbe Port muss als WHISPER_URL im Ablauf `Konfiguration` stehen.
mkdir -p /opt/whisper-stt && cp dienst/whisper/whisper_server.py /opt/whisper-stt/
python3 -m pip install faster-whisper          # zieht das Modell beim ersten Lauf
# systemd-Unit: siehe dienst/whisper/README.md
systemctl enable --now whisper-stt
curl -s http://127.0.0.1:18790/health      # {"status":"ok","model":true,"device":"cuda"}
```

> **Nicht verwechseln:** Der Dienst auf Port **18790** (faster-whisper, LXC 105) ist der
> bequeme Nachbau-Weg; im laufenden Original erledigt das inzwischen **whisper.cpp auf
> der MI50** (LXC 112, Port **8000**, `whisper-amd`). Beide antworten auf
> `POST /transcribe` mit `{"text": …}` — es zählt nur, dass `WHISPER_URL` in der
> Zentrale `Konfiguration` auf den eigenen Dienst zeigt (`DOKU/HANDBUCH.md` §4.4,
> `DOKU/BETRIEB.md` §1).

### Schritt 3 — n8n starten (zwei Wege)

**Weg A — exakt kopieren** (schnell, braucht ausgefüllte Zugangswerte (hier: Platzhalter `DEIN-…` — vorher ersetzen)):
`ablaeufe-laufend/*.json` einspielen (**sieben** Dateien: die Zentrale `Konfiguration`,
der Agent, drei Werkzeuge, der Stimmen-Ablauf und der frühere KI-Moderator), aktivieren,
n8n neu starten. Reihenfolge: **zuerst** `Konfiguration.json` (dort stehen die Werte für
alle anderen), dann die Werkzeuge, dann der Agent; eingeschaltet werden die **fünf**
Abläufe laut `vorlage.md` §4. Anleitung in `ablaeufe-laufend/README.md`. In einer
frischen n8n das **Telegram-Konto** anlegen und am Trigger auswählen — die
Konto-Kennung aus dem Export gehört zur Original-Installation.

**Weg B — neu bauen** (eigene Zugangswerte, nachvollziehbar):

n8n als Container, Port 5678, Projektordner anlegen. Danach die Abläufe bauen:

```bash
# Zugangswerte in die Umgebung geben (siehe zugangsdaten.md)
export TG_TOKEN="<Telegram-Bot-Token>"
export AZ_KEY="<AzuraCast-API-Schlüssel>"
export MELDUNG_SCHLUESSEL="<Schlüssel des Postfachs>"
export OLLAMA_URL="http://<GPU-Host>:11434"
export WHISPER_URL="http://<GPU-Host>:18790/transcribe"

cd werkzeuge
python3 agent-wf-bauen.py            # schreibt /tmp/radio-konfiguration.json,
                                     # /tmp/radio-werkzeuge.json + /tmp/radio-agent.json
python3 anordnung-pruefen.py /tmp/radio-agent.json     # muss "0 Befunde" melden
python3 import-agent-vorbereiten.py  # schreibt /tmp/radio-agent-import.json
                                     # + /tmp/radio-werkzeuge-import.json
nano /tmp/radio-konfiguration.json   # dort die eigenen Werte eintragen (Tokenizer, URLs)
```

> **Wichtig für die Replikation:** der Erzeuger baut die Abläufe **identisch** zum
> laufenden Bot — mit einer Ausnahme: ein vollständiger Neubau setzt an den
> Werkzeugknoten das Feld `name` (z. B. `titel_suchen`). Im laufenden System ist das
> Feld nicht gesetzt; dort wurden Änderungen immer **chirurgisch gepatcht**
> (`werkzeuge/agent-patchen.sh`). Wer den laufenden Bot exakt kopieren will, nimmt
> die Exporte aus `ablaeufe-laufend/` (Schritt 3, Weg A — hier mit Platzhaltern;
> im Arbeitsordner mit den echten Werten, 700/600); ältere Fassungs-Sicherungen (`sicherungen/radio-fassungen/…`)
> liegen nur im Projektordner des Betreibers.

### Schritt 4 — Abläufe einspielen

```bash
cd werkzeuge
# Zielhost/Projekt in agent-einspielen-nur.sh + import-agent-vorbereiten.py anpassen
bash agent-einspielen-nur.sh /tmp/radio-agent-import.json
```

Das Skript braucht **alle drei** Dateien aus Schritt 3
(`/tmp/radio-konfiguration.json`, `/tmp/radio-werkzeuge-import.json`,
`/tmp/radio-agent-import.json`) und bricht sonst ab.

**Erwartetes Ergebnis:** n8n startet neu (~20 s) und listet danach
**fünf aktive Abläufe**; die Ausgabe nennt keinen Fehler:

```bash
ssh <dein-n8n-host> "docker exec -u node n8n n8n list:workflow"   # 5 Zeilen, alle active
```

Der Webhook des Testeingangs antwortet mit **ungültigem** Schlüssel mit
`⛔ Kein Zugang.` und mit dem richtigen Schlüssel mit einer Bot-Antwort — Aufruf und
erwartete Ausgabe stehen in `DOKU/BETRIEB.md` §3.

Danach:
* Webhook des Testeingangs prüfen (`/webhook/DEIN-WEBHOOK-PFAD?schluessel=…`)
* Betreiber freischalten: `python3 erlaubte-setzen.py <chatId>`
* Bot-Daten setzen: `python3 bot-daten-setzen.py`
* Telegram-Menü: `bash telegram-menue.sh`

### Schritt 5 — Sender einrichten

`sender-einrichten.md` folgen: Station, Mount, Streamer-Zugänge, Wiedergabeliste,
DJ-Hafen, Einstellungen (u. a. `request_threshold = 0`, `enable_streamers = 1`).

### Schritt 6 — Musikarchiv einlesen

Musik in den Medienordner des Senders legen (im Original `/mnt/Content/Music`),
AzuraCast einlesen lassen, dann den Katalogdienst füllen:

```bash
curl -s -X POST -H "X-Meldung-Schluessel: <Schlüssel>" http://127.0.0.1:8881/katalog/aktualisieren
curl -s http://127.0.0.1:8881/katalog/status      # Anzahl der Titel im Suchindex
```

### Schritt 7 — Alles prüfen

Reihenfolge (Details in `../DOKU/BETRIEB.md`):

```bash
bash kurz-test.sh          # 19 von 19
bash antwort-test.sh       # 20 ok
bash playlist/11-dienst-art-test.sh          # 37 von 37
python3 meldungen/19-meldungen-test.py       # 45 ok   (braucht den Dienst)
python3 meldungen/21-bot-meldungen-test.py   # 6 ok    (braucht n8n + Testeingang)
bash bot-test.sh "was läuft"                 # Antwort in ~1–2 s
python3 meldungen/24-live-pegel.py "Test der Lautstärke."   # spricht im Sender
```

### Schritt 8 — Eigene Sprecherstimme (optional)

Wer die Ansagen mit einer eigenen Wandlungsstimme (RVC) sprechen will, baut sie nach
`eigene-stimme/README.md` nach: Rohmaterial trennen (Stimmen-Dienst, Port 8890), Referenz
vom Betreiber bestätigen lassen, reine Stücke sammeln (`stimme_erweitern.py`), Modell
trainieren (`rvc-trainieren.sh <dein-modell> … 400 8`), Sprechdienst `sprechdienst` (Port 10205)
starten — Kurzprobe:

```bash
curl -s -X POST http://127.0.0.1:10205/tts -H 'Content-Type: application/json' \
  -d '{"text":"Test"}' -o /tmp/probe.wav -w "%{http_code}\n"
```

Die Einbindung ist **gebaut**: Der Dienst nutzt `deine-stimme` als Vorgabe
(`TTS_DEFAULT_VOICE`, Schritt 1); ohne Stimmendienst genügt eine Piper-Vorgabe
(`TTS_DEFAULT_VOICE=de_thorsten`). Details: `eigene-stimme/README.md`, Abschnitt 8.
Eine **allgemeine** Anleitung (jede Serie/Stimme, alle Werte und Befehle):
`../DOKU/STIMME.md`.

---

## 3. Was der Ordner enthält

| Ordner | Inhalt |
| --- | --- |
| `dienst/` *(im Projektordner, `../dienst/`)* | die Module des Sprachdienstes (`main.py`, `katalog.py`, `playlist.py`, `meldungen.py`, `suche.py`), `Dockerfile`, `docker-compose.yml`, `geheim.env.vorlage`, `whisper/` (Rückfall-Spracherkennung), `whisper-amd/` (Spracherkennung auf der MI50) |
| `werkzeuge/` *(im Projektordner, `../werkzeuge/`)* | alle Betriebs-, Bau- und Prüfskripte (über 100 Dateien) |
| `zugangsdaten.md` | welche Zugangsdaten nötig sind und wie sie entstehen |
| `umgebung.md` | Container, IPs, Ports, Dienste, Reverse Proxy |
| `sender-einrichten.md` | der Sender (AzuraCast) einrichten |
| `stimmen-und-modelle.md` | Stimmen und Modelle: Quellen, Größen, Konfiguration |
| `stimmen-holen.sh` | lädt die vier Piper-Stimmen in ein Zielverzeichnis |
| `eigene-stimme/` | **die eigene Sprecherstimme nachbauen**: Extraktions-Dienst (8890), Sammler (`deine-stimme_sammeln3/4/5.py`), Trainingsskript, Sprechdienst (10205), Prüf-Werkzeuge — Anleitung im Ordner |
| `ablaeufe-laufend/` | die **Exporte der laufenden Abläufe** (exakte Wiederherstellung; in dieser Fassung mit Platzhaltern) |
| `zugangsdaten/` | in dieser Fassung **entfernt**; eigene Werte anlegen nach `zugangsdaten.md` (Arbeitsordner: echte Werte 700/600) |

**Enthalten, aber mit Vorsicht zu behandeln:** im Arbeitsordner `zugangsdaten/` und
`ablaeufe-laufend/` (echte Werte, 700/600). **Diese Fassung enthält keine Werte** —
`zugangsdaten/` wurde entfernt, die Exporte tragen Platzhalter.

**Bewusst nicht enthalten:** das Musikarchiv, die Modell-Binärdateien (zu groß) und
die Sicherungen der n8n-Datenbank (`n8n-daten.sqlite.gz`, siehe
`<projektordner>/sicherungen/radio-fassungen/` außerhalb des Projekts).

---

## 4. Prüfung der Replikation

Ein Nachbau ist gelungen, wenn:

1. `anordnung-pruefen.py` **0 Befunde** meldet (identische Fläche),
2. `HTTP 200` von `/health` mit `"stimmen": 4`,
3. `/katalog/status` die Anzahl der Titel aus dem eigenen Archiv nennt,
4. die Prüfläufe aus Schritt 7 grün sind,
5. ein Titelwunsch im Telegram in **1–2 s** läuft und
6. eine Ansage im Radio hörbar ist (Lautstärke: rund −11,8 LUFS auf Sendung, siehe
   `../DOKU/HANDBUCH.md`, Abschnitt 2).

---

## 5. Was anders sein darf

* **Stimme**: Vorgabe ist die **eigene Sprecherstimme `deine-stimme`** (extern, `eigene-stimme/`);
  ohne Stimmendienst setzt man `TTS_DEFAULT_VOICE` auf eine Piper-Stimme (Kurznamen in
  `dienst/main.py`). Fällt der Stimmendienst aus, spricht `radio-tts` mit
  `EIGENE_STIMME_ERSATZ` (Standard `de_thorsten`) weiter.
* **Modell**: `OLLAMA_MODELL` — es muss nur Werkzeuge (Function Calling) beherrschen.
  Getestet sind `qwen3.6:27b` (Empfehlung) und `qwen2.5:14b` (unzuverlässiger).
* **Sender**: jede AzuraCast-Installation mit Liquidsoap/AutoDJ funktioniert; es muss
  die unter `sender-einrichten.md` genannten Voraussetzungen erfüllen (DJ-Hafen,
  API-Schlüssel).
* **Musik**: der Bot passt sich dem eigenen Archiv an (Katalogindex neu bauen).
* **Adressen**: alle IPs/Ports stehen als Umgebungsvariablen bzw. in den Katalogdaten
  der Abläufe; im Original: Dienst `192.168.178.53:8881`, n8n `:5678`,
  Ollama `192.168.178.187:11434`, Whisper `192.168.178.188:8000`,
  Sender `192.168.178.33`.

---

## 6. Was **nicht** in einem Ordner liegen kann

> **Diese Fassung enthält keine Zugangswerte** — der Ordner `zugangsdaten/` wurde
> entfernt, die Ablauf-Exporte tragen Platzhalter. Eigene Werte anlegen nach
> `zugangsdaten.md`; im Arbeitsordner liegen die echten Werte (700/600).

1. **Das Musikarchiv**. Der Bot braucht es inhaltlich; die
   Struktur ist frei. → eigenes Backup.
2. **Die Modell- und Stimmen-Binärdateien** (Voice-Modelle 200 MB,
   Whisper large-v3 ~3 GB, Ollama-Modell 17,7 GB). → Download-Anleitung.
3. **Die Senderdatenbank** (Wiedergabelisten, Nutzer, Verlauf). → AzuraCast-Sicherung
   (`azuracast_cli backup`) oder Neuaufbau nach `sender-einrichten.md`.
4. **Der Zustand zur Laufzeit** (Postfach `/daten/meldungen.json`, offene Auswahlen,
   n8n-laufende Aufträge) — entsteht von selbst.
5. **Die laufende n8n-Datenbank** — im Original zusätzlich als `n8n-daten.sqlite.gz`
   in jeder Fassung gesichert; ohne sie werden die Abläufe neu eingespielt (Schritt 4).
6. **Rohmaterial, Datensatz und Modell der eigenen Sprecherstimme** — stammen aus
   fremden Produktionen (eigene Kopie nötig) und bleiben (wie das Musikarchiv) außerhalb
   des Ordners; der Nachbau aus dem eigenen Bestand ist in `eigene-stimme/README.md`
   beschrieben.

---

## 7. Nachbau in Stichproben (angelegt am 2026-09-20; Abläufe und Syntax erneut geprüft am 2026-09-24)

| Prüfung | Ergebnis |
| --- | --- |
| Abläufe bauen (`python3 werkzeuge/agent-wf-bauen.py`) | Bot 83 Knoten + 3 Werkzeuge, alle Verbindungen geprüft |
| Zeichenfläche (`python3 werkzeuge/anordnung-pruefen.py /tmp/radio-*.json`) | **0 Befunde** |
| Python-Syntax aller Module (`compileall`) | in Ordnung |
| `docker compose config` mit der Vorlage | gültig, alle Variablen aufgelöst |
| `docker build` aus `dienst/` | Abbild gebaut (Basis `python:3.12-slim` + piper-tts, fastapi, lameenc) |
| Probe-Start des Abbilds (anderer Port, Stimmen eingebunden) | `/health` → `{"status":"ok","stimmen":4,"standard":"de_thorsten"}` *(seit 2026-09-23 zeitweise `deine-stimme`; seit 2026-09-25 wieder Vorgabe `de_thorsten`, DEINE-STIMME auf Wunsch — siehe Schritt 8)* |
| Sprachausgabe der Probe (`POST /v1/audio/speech`) | HTTP 200, 56 kB WAV |
| Stimmen laden (`stimmen-holen.sh`) und **Prüfsummen** vergleichen | 4 Stimmen, md5 **identisch** mit dem laufenden System |

Damit ist belegt: die **Bau- und Laufzeitdateien sind vollständig** und lauffähig. Es
fehlen nur die Dinge aus Abschnitt 6 (Modell-/Stimmendateien, Musikarchiv) —
plus die eigenen Zugangswerte nach `zugangsdaten.md`: alles mit Anleitung.
