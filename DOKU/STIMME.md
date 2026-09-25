# Stimme — die eigene Wunschstimme einbinden

> **Hinweis zu dieser Fassung:** Diese Veröffentlichung enthält **keine fremde Stimme**
> und **keine Stimmdaten** (kein Modell, keine Trainingsausschnitte, keine Hörproben).
> Der Dienst spricht ab Werk mit einer **freien Standardstimme**. Hier steht Schritt
> für Schritt, wie du **deine eigene Wunschstimme** einbindest — entweder eine freie
> Piper-Stimme (Weg A) oder eine selbst erzeugte, eigene Sprecherstimme über einen
> eigenen Stimmendienst (Weg B).
>
> Platzhalter in dieser Anleitung: `DEINE-STIMME` = Name deiner Stimme,
> `<GPU-Maschine>` = Rechner/Container mit NVIDIA-GPU, `<dein-modell>` = dein
> Trainingsergebnis, `<dein-datensatz>` = deine Materialsammlung.

---

## 1. Wie die Ansagen entstehen

Der Sprachdienst **`radio-tts`** (`dienst/`, Port **8881**) macht aus Text Audio und
spricht es im Sendetakt live in den DJ-Hafen des Senders (Ansagen laufen also nicht
„nebenher“, sondern in Echtzeit). Zwei Stellen wählen die Stimme:

| Weg | Feld | Bedeutung |
| --- | --- | --- |
| OpenAI-kompatibel | `voice` bei `POST /v1/audio/speech` | Kurzname einer Piper-Stimme **oder** der Name deiner eigenen Stimme |
| Bot-Werkzeuge | `stimme` bei „Meldung ansagen“ und „Recherche holen“ | leer = Standardstimme; `deine-stimme` = deine eigene Stimme |

* **Standardstimme:** `TTS_DEFAULT_VOICE` (Vorgabe `de_thorsten`, eine freie
  Piper-Stimme — sie funktioniert ohne eigene GPU-Dienste).
* **Piper-Stimmen:** liegen als `.onnx` (+ `.json`) im Ordner `VOICE_DIR`
  (Vorgabe `/voices`). Kurznamen wie `de_kerstin` bildet der Dienst auf Dateinamen ab.
* **Eigene Stimme (optional):** ein **eigener Stimmendienst**, den `radio-tts` über
  `EIGENE_STIMME_URL` anspricht (Abschnitt 3.8). Ist er nicht erreichbar, greift die
  Ersatzstimme `EIGENE_STIMME_ERSATZ` — eine Ansage fällt nie aus.

Nach jeder Erzeugung schreibt der Dienst eine Logzeile **`Stimme: <Name>`** — damit
prüfst du in `docker logs radio-tts`, welche Stimme wirklich gesprochen hat.

---

## 2. Weg A — eine freie Piper-Stimme wählen (einfachster Weg)

1. Stimme besorgen (frei verfügbar z. B. über die Piper-Stimmenlisten) und die Dateien
   `<name>.onnx` und `<name>.onnx.json` in den Stimmenordner legen (Host-Pfad, der in
   `docker-compose.yml` auf `VOICE_DIR` gemountet wird).
2. Kurzname eintragen: entweder in der Tabelle `KURZNAMEN` in `dienst/main.py` oder
   direkt als Kurzname verwenden (der Dienst findet auch Dateinamen ohne Endung,
   Groß-/Kleinschreibung egal).
3. Standard setzen: `TTS_DEFAULT_VOICE=<kurzname>` in der `geheim.env` (bzw. im
   Compose-Umfeld), Dienst neu erzeugen (`docker compose up -d --force-recreate radio-tts`).
4. Probe:

```bash
curl -s -X POST http://127.0.0.1:8881/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"input": "Hallo, hier spricht die neue Stimme.", "voice": "<kurzname>"}' \
  -o /tmp/probe.mp3 -w 'HTTP %{http_code}\n'
```

---

## 3. Weg B — eine eigene (geklonte) Sprecherstimme einbinden

### 3.1 Rechtliches — zuerst lesen

* Verwende **nur Material, an dem du die nötigen Rechte hast** (eigene Aufnahmen,
  eigene Sprecher, freigegebene Quellen). Stimmen anderer Personen — erst recht aus
  Filmen, Serien oder Spielen — dürfen **ohne ausdrückliche Erlaubnis nicht**
  vervielfältigt, veröffentlicht oder in einem Sender eingesetzt werden.
* Trainingsmaterial, Modell und Hörproben sind **persönliche Arbeitsdaten**: nicht
  weitergeben, nicht veröffentlichen.
* Ein Vorbild aus dieser Veröffentlichung gibt es absichtlich **nicht** — diese
  Fassung kommt ohne fremde Stimme und ohne Stimmdaten.

### 3.2 Was du brauchst

* Maschine/Container mit **NVIDIA-GPU** (ab ~8 GB VRAM genügt; geteilte GPUs
  funktionieren, siehe Fallstricke in Abschnitt 3.11), Ubuntu, ~60 GB Plattenplatz
* `ffmpeg`, Internetzugang (Basismodelle, ggf. Online-TTS als Basis)
* **Eigenes** Tonmaterial der gewünschten Stimme (z. B. Aufnahmen mit dem Mikrofon —
  sauber, trocken, keine Musik)
* Zeit: Sammlung je nach Material wenige Minuten, Training ~1 Stunde

### 3.3 Rohmaterial aufbereiten (Sprechertrennung)

Für Material mit mehreren Sprechern (z. B. Video-/Sendungsmitschnitte) liegt ein
kleiner Dienst bei, der Sprache trennt und **je Sprecher** einen Ordner ablegt:

```bash
# einrichten (kopiert Skript + systemd-Einheit, legt einen Schlüssel an)
bash NACHBAU/eigene-stimme/einrichten-stimmen-dienst.sh

# Auftrag starten — erst EINE Folge/Datei zum Test, dann alles
K=$(cat /opt/stimmen-dienst/schluessel.txt)
curl -s -X POST "http://<GPU-Maschine>:8890/extrahieren?schluessel=$K" \
     -H 'Content-Type: application/json' \
     -d '{"serie":"/pfad/zu/deinem/material","name":"lauf1","folgen":1,"trennen":true}'
```

Ergebnis: `/opt/Applio/assets/datasets/lauf1/cluster_0 … cluster_n` — ein Ordner je
Sprecher. **Musik/Abspanne aussortieren** — sie überleben die Vokaltrennung.

### 3.4 Referenz bestätigen (Pflicht)

Aus dem passenden Sprecher-Ordner die **saubersten 5–10 kurzen Stücke** als Referenz
in einen eigenen Ordner legen (z. B. `<deine-referenz>`). Diese Referenz steuert die
gesamte spätere Sammlung — ein falsch gewählter Anker kostet ein komplettes Modell.
Hörproben je Sprecher kannst du dir schicken lassen:

```bash
bash NACHBAU/eigene-stimme/cluster-proben.sh lauf1 2   # je Cluster 2 Proben
```

### 3.5 Reine Stücke sammeln

Drei kleine Werkzeuge sammeln Trainingsmaterial gegen die bestätigte Referenz
(Ähnlichkeitsschwelle, Mindestdauer und Fenster sind oben in den Skripten als
bewährte Beispielwerte eingetragen — an dein Material anpassen):

| Werkzeug | Aufgabe |
| --- | --- |
| `stimme_pruefen.py` | Fenster-Prüfung: reine Stücke der Zielstimme gegen die Referenz |
| `stimme_sammeln.py` | Sammlung: nur der längste zusammenhängende Trefferlauf je Kandidat |
| `stimme_erweitern.py` | Selbst-Erweiterung in Runden (mehr Material aus mehr Quellen) |

```bash
# Beispiel (Pfade anpassen):
/opt/Applio/.venv/bin/python /opt/Applio/stimmen-dienst/stimme_sammeln.py \
  --referenz <deine-referenz> --quellen "<weitere-quellen>/cluster_*" \
  --ziel <dein-datensatz>
```

### 3.6 Modell trainieren

```bash
bash NACHBAU/eigene-stimme/rvc-trainieren.sh <dein-modell> <dein-datensatz> 400 8
```

* Ablauf: Preprocess → Extract (`rmvpe`) → Train (**400 Epochen, Batch 8**, Speichern
  alle 50) → Index.
* Erwartung auf einer RTX 3090 Ti: **~1 h** für ~10 Minuten Material.
* Ergebnisse: `<dein-modell>_400e_*.pth` (Modell) + `<dein-modell>.index` (Index).

### 3.7 Sprechdienst bauen

Der beiliegende Dienst **`sprechdienst.py`** ist die Brücke „Text → deine Stimme“:
Basis-TTS (Standard: `edge-tts`) → RVC-Wandlung → WAV. Er bietet genau die zwei
Endpunkte, die `radio-tts` erwartet:

| Endpunkt | Antwort |
| --- | --- |
| `POST /tts` mit `{"text": "…"}` | WAV-Audio (22050 Hz mono) |
| `GET /health` | Zustand (JSON) |

```bash
# Dateien auf die GPU-Maschine legen (Beispiel-Container „rvc“):
docker cp NACHBAU/eigene-stimme/sprechdienst.py  <container>:/opt/Applio/sprechdienst/sprechdienst.py
docker cp NACHBAU/eigene-stimme/sprechdienst.service <container>:/etc/systemd/system/
# Modell/Index-Pfade, Basisstimme und Tempo OBEN IM DIENST eintragen, dann:
systemctl daemon-reload && systemctl enable --now sprechdienst && systemctl is-active sprechdienst
curl -s http://127.0.0.1:10205/health
```

### 3.8 In `radio-tts` einbinden

In der `geheim.env` des Sprachdienstes (bzw. im Compose-Umfeld):

```env
EIGENE_STIMME_URL=http://<GPU-Maschine>:10205/tts
EIGENE_STIMME_NAME=deine-stimme
EIGENE_STIMME_ERSATZ=de_thorsten
# EIGENE_STIMME_ZEITABLAUF=600
```

* `EIGENE_STIMME_URL` — Adresse deines Sprechdienstes. **Leer = Funktion aus**
  (dann spricht immer die Piper-Standardstimme).
* `EIGENE_STIMME_NAME` — der Name, unter dem die Stimme angesprochen wird
  (Vorgabe `deine-stimme`).
* `EIGENE_STIMME_ERSATZ` — Piper-Stimme, die spricht, falls dein Dienst nicht
  erreichbar ist.
* Danach `docker compose up -d --force-recreate radio-tts` und `/health` prüfen:
  Die Stimmenliste zeigt deinen Namen; die Logzeile `Stimme: <Name>` beweist den Weg.

### 3.9 Im Chat verlangen

Die Ansagen nutzen **auf ausdrücklichen Wunsch** deine eigenen Stimme — einfache
Wendungen wie:

* „sag durch: … **mit eigener Stimme**“
* „lies die Nachrichten mit deiner Stimme vor“
* „… in der eigenen Stimme“

Der Wunsch wird fest erkannt und als `stimme=deine-stimme` an die Werkzeuge
übergeben; die Wendung selbst wird **nie vorgelesen**. Ohne Wunsch bleibt es bei der
Standardstimme (oder dem, was `TTS_DEFAULT_VOICE` sagt).

### 3.10 Prüfen

```bash
# 1) Dienst direkt:
curl -s -X POST http://<GPU-Maschine>:10205/tts -H 'Content-Type: application/json' \
  -d '{"text": "Willkommen. Hier spricht deine eigene Stimme."}' -o /tmp/probe.wav \
  -w 'HTTP %{http_code} in %{time_total}s\n'

# 2) Über radio-tts:
curl -s -X POST http://127.0.0.1:8881/v1/audio/speech -H 'Content-Type: application/json' \
  -d '{"input": "Probe über den Sprachdienst.", "voice": "deine-stimme"}' \
  -o /tmp/probe2.mp3 -D - | grep -i x-stimme

# 3) Im laufenden Betrieb: Logzeile prüfen
docker logs --tail 20 radio-tts | grep "Stimme:"
```

### 3.11 Fallstricke (aus dem Bau gelernt)

* **GPU teilen:** Läuft auf derselben Karte ein Sprachmodell (Ollama o. Ä.), kann
  dem Sprechdienst der Speicher ausgehen (`CUDA out of memory`, HTTP 500). Dann
  spricht die Ersatzstimme. Gegenmittel: Zwischenspeicher nach jeder Ansage
  freigeben (macht `sprechdienst.py`), `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`
  setzen, notfalls andere GPU-Dienste stoppen.
* **Zeitablauf großzügig:** Die Erzeugung ist etwas schneller als Echtzeit — eine
  mehrminütige Ansage braucht trotzdem Minuten. `EIGENE_STIMME_ZEITABLAUF` (Sekunden)
  entsprechend setzen, sonst fällt der Dienst vorzeitig auf die Ersatzstimme zurück.
* **Erste Ansage nach Dienststart** dauert länger (Modell laden), danach
  ~1,5–4 s je Satz.
* **Nur ein Modell je Dienst:** Wechselst du das Modell, Dienst neu starten.

---

## 4. Wo die Skripte liegen

Alles in **`NACHBAU/eigene-stimme/`** (Beispielwerte darin anpassen):

| Datei | Zweck |
| --- | --- |
| `README.md` | Arbeitsanleitung zu den Skripten |
| `stimmen_dienst.py`, `stimmen-dienst.service`, `einrichten-stimmen-dienst.sh` | Rohmaterial: Video → Vokaltrennung → Sprecher-Cluster (Port 8890) |
| `cluster-proben.sh` | Hörproben je Sprecher (Auswahl der Zielstimme) |
| `stimme_pruefen.py`, `stimme_sammeln.py`, `stimme_erweitern.py` | reine Stücke finden, sammeln, erweitern |
| `rvc-trainieren.sh` | Training im Container (Preprocess → Extract → Train → Index) |
| `sprechdienst.py`, `sprechdienst.service` | Sprechdienst (Port 10205): Basis-TTS → RVC → WAV |
| `tg-sprachnachricht.sh` | Hörprobe per Telegram schicken (optional) |
| `verworfen/` | ein verworfener Weg, nur als Referenz |

---

## 5. Wenn etwas nicht klappt

| Symptom | Ursache / Abhilfe |
| --- | --- |
| Ansage spricht „falsch“ (Ersatzstimme) | eigener Dienst nicht erreichbar/zu langsam — `/health` prüfen, Logzeile `Stimme:` ansehen, Zeitablauf erhöhen |
| `HTTP 500` beim Sprechdienst | meist GPU-Speicher (Abschnitt 3.11) |
| Stimme klingt anders als erwartet | Basisstimme/Tempo/RVC-Mischung (`index_rate`) im Dienst justieren — in kleinen Schritten und immer per Ohr |
| Bot spricht trotz Wunsch die Standardstimme | Befehl enthielt keine der Wendungen aus 3.9, oder `EIGENE_STIMME_URL` ist leer |
