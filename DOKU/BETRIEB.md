# Betrieb — Einspielen, Störungen, Testen

## Betrieb

**Stand:** 2026-09-24.

Alle Befehle laufen auf dem eigenen Rechner; die Werkzeuge liegen in
`werkzeuge/`, die Module des Dienstes in `dienst/`.

---

### 1. Wo was läuft

| Baustein | Ort | Zugriff |
| --- | --- | --- |
| n8n (Bot) | LXC 103 auf `ai-server` (192.168.178.32), IP `192.168.178.53`, Port 5678 | `ssh -F ~/.ssh/config ai-server "pct exec 103 -- …"` |
| Dienst `radio-tts` | Docker-Container `radio-tts` **in LXC 103** (Port 8881) | `… pct exec 103 -- docker exec radio-tts …` |
| Stimmendienst `sprechdienst` | systemd-Dienst in **CT 111** auf `ai-server` (`192.168.178.116`), Port 10205 — eigene Moderationsstimme | `ssh -F …/proxmox-ssh/config ai-server "pct exec 111 -- …"`; prüfen: `curl -s http://192.168.178.116:10205/health` |
| AzuraCast | LXC 106 auf dem **Datenserver** (192.168.178.163), Web `http://192.168.178.33` | `ssh -i ~/.ssh/id_ed25519 root@192.168.178.163 "pct exec 106 -- docker exec azuracast …"` |
| Ollama + HA-Whisper | LXC 105 auf `ai-server` (`192.168.178.187`) | Port 11434 (Sprachmodell), Port 10300 (Home-Assistant-Whisper); der frühere `whisper-stt` (**18790**) ist abgeschaltet — Start bei Bedarf: `pct exec 105 -- systemctl start whisper-stt` |
| Spracherkennung (Radio) | **whisper-amd** in LXC 112 auf `ai-server` (`192.168.178.188:8000`) | whisper.cpp large-v3 auf der **MI50** (seit 2026-09-23) |
| Eigene Suchmaschine (SearXNG) | LXC 108 auf `ai-server` (`192.168.178.26`), Port 8888 | `pct exec 108 -- …`; Dienste `uwsgi` + `redis-server`, Einrichtung: `NACHBAU/searxng-einrichten.md` |
| Projektordner | `<dokuordner>/` | Werkzeuge, Prüfläufe, Sicherungen |

Nützliche Adressen: Dienst `http://192.168.178.53:8881/health`,
Stimmendienst `http://192.168.178.116:10205/health`,
Sender `http://192.168.178.33/api/nowplaying/1`,
Suchmaschine `http://192.168.178.26:8888/search?q=test&format=json`,
n8n-Oberfläche `https://DEIN-N8N-HOST`.

---

### 2. Änderungen einspielen

#### 2.1 Etwas am Verhalten (Ablauf) ändern

```bash
cd ../../werkzeuge

## 3. Fassung sichern (immer vorher!)
bash fassung-sichern.sh radio-vN-<datum>-<kurzname> /tmp/beschreibung.md

## 4. Ablauf ändern: Erzeuger anpassen (agent-wf-bauen.py) und/oder patchen
bash agent-patchen.sh --inhalt "Knoten A,Knoten B"     # Inhalte übernehmen
bash agent-patchen.sh --aufraeumen                     # Zeichenfläche (Positionen, Notizen, Rahmen)
bash agent-patchen.sh --neu "Neuer Knoten" --umbenennen "Alt=Neu"

## 5. Prüfen und einspielen
python3 anordnung-pruefen.py /tmp/radio-agent-neu.json   # Ziel: 0 Befunde
bash agent-einspielen-nur.sh /tmp/radio-agent-neu.json
```

Der Patcher übernimmt nur das Genannte und prüft am Ende: keine Maskenmerker,
Kennung und Schlüssel enthalten, keine Logik-Knoten verloren, alle Verbindungsziele
vorhanden. Nach dem Einspielen startet n8n neu (~20 s), dann ist der Bot wieder
erreichbar.

#### 2.2 Etwas am Dienst ändern (Sprache, Ansage, Recherche, Listen, Postfach)

```bash
cd ../../werkzeuge
## Module liegen in ../dienst/*.py
bash dienst-einspielen.sh        # kopiert alle dienst/*.py + Dockerfile, baut und startet neu
```

Der Aufruf endet mit einer Selbstauskunft des Dienstes (`/katalog/status`,
`/meldungen/status`, `/ansage/status`) — daran sieht man, dass er läuft.

#### 2.3 Nur eine Einstellung ändern (ohne Neu-Bauen)

In `/opt/radio-tts/geheim.env` (im LXC 103 auf dem ai-server), danach
`docker compose up -d` im Verzeichnis `/opt/radio-tts`:

| Wert | Wirkung | Standard |
| --- | --- | --- |
| `LIVE_LAUTSTAERKE_DB` | Ansage um so viele dB lauter | 0 |
| `TTS_ZIEL_RMS_DB` | Zielpegel der Sprache | −11,5 |
| `TTS_KOMPRESSOR_SCHWELLE_DB` / `TTS_KOMPRESSOR_VERHAELTNIS` | Verdichtung | −19 / 3.0 |
| `TTS_BEGRENZER_DB` / `TTS_BEGRENZER_FREIGABE_MS` | Spitzendecke / Freigabe | −1.0 / 40 |
| `TTS_HOCHPASS_HZ`, `TTS_DEFAULT_VOICE` | Tiefenfilter, Stimme | 80, `de_thorsten` (Standard; DEINE-STIMME auf Wunsch: „… mit eigener Stimme“) |
| `EIGENE_STIMME_URL` | Stimmendienst (CT 111) | `http://192.168.178.116:10205/tts` |
| `EIGENE_STIMME_ERSATZ` | Ersatzstimme, wenn der Stimmendienst nicht erreichbar ist (leer = dann keine Ersatzstimme) | `de_thorsten` |
| `EIGENE_STIMME_ZEITABLAUF` | Zeitgrenze der Stimmerzeugung (Sekunden) | 600 |
| `ANSAGE_SPERRE_SEK` | derselbe frei formulierte Text wird so viele Sekunden nicht wiederholt (Schutz vor Werkzeug-Schleifen) | 90 |
| `LIVE_HOST/PORT/MOUNT/USER/PASSWORD` | DJ-Hafen; `LIVE_USER` ist das **eigene Bot-Konto `deine-stimme`** — im Sender erscheint beim Sprechen **„DEINE-STIMME“** (mein Zugang `betreiber` bleibt getrennt) | aus der Zugangsdatei |

> **Im Betrieb abweichend (nach Gehör gewählt, 2026-09-23):** In
> `/opt/radio-tts/geheim.env` stehen `TTS_HOCHPASS_HZ=50`,
> `TTS_KOMPRESSOR_SCHWELLE_DB=-18`, `TTS_KOMPRESSOR_VERHAELTNIS=2.0` und
> `TTS_ZIEL_RMS_DB=-12.5` — die sanftere Einstellung („Variante 3“) macht die Ansage
> weniger hell. Wirkung prüfen: `docker exec radio-tts env | grep TTS_`.

#### 2.4 Charakter der Stimme ändern (Datei `charakter.md`)

Der Charakter (Figur, Wesen, Ton) steht als **Klartextdatei** `charakter.md` neben dem
Projektordner. Zeilen mit `#` am Anfang sind Notizen; alles andere wird dem Sprachmodell
als Rolle mitgegeben. Er wirkt in den **gesprochenen Ansagen**: Verlangt der Betreiber
eine Ansage, deren Wortlaut der Bot selbst formulieren soll („sag eine Begrüßung an"),
formuliert der Planer sie in dieser Rolle; die Telegram-Antworten bleiben sachlich, und
die festen Zeilen des Dienstes (Vorspann/Nachspann) stehen unabhängig davon in
`dienst/meldungen.py`. Leerer Text (nur `#`-Zeilen) schaltet die Rolle ab.

```bash
cd ../..
python3 werkzeuge/charakter-einspielen.py            # Datei -> laufender Bot (ohne Neustart)
python3 werkzeuge/charakter-einspielen.py --trocken  # nur zeigen, was sich ändert
```

Das Werkzeug holt die laufende Zentrale (`Konfiguration`) aus n8n, ersetzt **nur** das Feld
`charakter` im Knoten `Werte`, spielt sie zurück und prüft am Ende, dass der Charakter im
Ablauf verdrahtet ist (Hauptbot: Knoten `Planen`; DDD: die Agenten). Vorher wird die
laufende Fassung nach `/tmp/charakter-sicherung-…json` gesichert; schlägt der Import fehl,
spielt das Werkzeug die Sicherung automatisch zurück. Ein kompletter Neubau
(`agent-patchen.sh` und `agent-einspielen-nur.sh`) liest dieselbe Datei — sie bleibt die
Quelle der Wahrheit.

---

### 6. Sichern und zurückrollen

**Fassungen** liegen außerhalb des Projektordners unter `<projektordner>/sicherungen/radio-fassungen/<name>/`:
die vier Abläufe als JSON, die Dienstmodule, der Dockerfile, die n8n-Datenbank und
eine Beschreibung (`README.md`). Anlegen und prüfen:

```bash
cd ../../werkzeuge
bash fassung-sichern.sh radio-vN-<datum>-<kurzname> /tmp/beschreibung.md
ls -l <projektordner>/sicherungen/radio-fassungen/radio-vN-.../          # Inhalt ansehen
```

Zurückrollen: die Abläufe aus der Sicherung einspielen
(`agent-einspielen-nur.sh <datei>`) und die Dienstmodule aus `<fassung>/dienste/`
mit `dienst-einspielen.sh` neu ausrollen. Die mitgesicherte `n8n-daten.sqlite.gz` ist
die vollständige n8n-Datenbank (letzter Ausweg).

**Senderdatenbank**: Sicherungen des Senders liegen auf `192.168.178.163` unter
`/root/azuracast-*` (u. a. Zustand vor und nach dem Aufräumen des Archivs).

---

### 7. Überwachen

```bash
## Läuft der Dienst?
curl -s http://192.168.178.53:8881/health
curl -s http://192.168.178.53:8881/meldungen/status
curl -s http://192.168.178.53:8881/ansage/status
curl -s http://192.168.178.116:10205/health   # Stimmendienst (eigene Stimme "deine-stimme")

## Grafikspeicher (Reserve fuer die Ansagestimme, Ollama ist geladen)
ssh -F ~/.ssh/config ai-server \
  "nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader"

## Ist eine gewünschte DEINE-STIMME-Ansage auf die Ersatzstimme ausgewichen? (leer = alles in Ordnung;
## die Meldung erscheint nur, wenn DEINE-STIMME gewünscht war)
ssh -F ~/.ssh/config ai-server \
  "pct exec 103 -- docker logs --since 1h radio-tts 2>&1 | grep -i 'eigene Stimme' || echo 'ok - keine Ausweichung'"

## Läuft der Sender? (is_live = spricht gerade der Moderator?)
curl -s http://192.168.178.33/api/nowplaying/1 | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['live']['is_live'], d['now_playing']['song']['text'], d['listeners']['current'])"

## Was hat der Bot zuletzt getan?
cd ../../werkzeuge
bash playlist/16-ausfuehrungen.sh 4      # letzte Läufe mit Knoten und Ergebnissen
bash ausfuehrungen.sh 3                  # dito für den Hauptablauf
cat bot-letzte.js | ssh -F ~/.ssh/config ai-server \
  "pct exec 103 -- bash -c 'cat > /tmp/bot-letzte.js'"
ssh -F ~/.ssh/config ai-server \
  "pct exec 103 -- bash -lc 'docker cp /tmp/bot-letzte.js n8n:/tmp/ >/dev/null && docker exec -u node n8n node /tmp/bot-letzte.js 3'"
## bot-letzte.js zeigt: Frage, Stufe 0, Befehle (mit "(einreihen)"), Überblick-Antwort,
## Antworttext, Knöpfe und Fehler je Knoten.
```

**Logs:** Liquidsoap-Protokoll `…/stations/deadline_beats/config/liquidsoap.log` im
AzuraCast-Container (zeigt Ansagen als `interrupting_requests: Prepared …`),
n8n im Container `n8n` (LXC 103), Dienst `radio-tts` per `docker logs radio-tts`,
Stimmendienst `sprechdienst` per `pct exec 111 -- journalctl -u sprechdienst -n 50`.

---

### 8. Nach einem Neustart

| Was | Verhalten |
| --- | --- |
| Dienst `radio-tts` | Postfach und Katalog liegen als Datei → bleiben erhalten; **offene Wiedergabelisten-Auswahl** geht verloren (der Bot sagt „Die Auswahl ist abgelaufen") |
| Stimmendienst `sprechdienst` (CT 111) | startet mit systemd mit; das RVC-Modell lädt beim **ersten** Aufruf (~9 s). Fällt er aus, sprechen die Ansagen ersatzweise mit `de_thorsten` (Kopfzeile `X-Stimme-Ersatz: 1`) |
| n8n | Import überschreibt `staticData` — Betreiberliste und Schlüssel werden über `erlaubte-setzen.py` / `bot-daten-setzen.py` gesetzt |
| Ollama | Modell wird nach 30 min entladen; der nächste Aufruf kostet 43,7 s (der Zeitplan hält es mit einem Mini-Aufruf warm) |
| Sender | AutoDJ läuft weiter; eine laufende Ansage ist nach spätestens 30 s beendet |

---

### 9. Häufige Handgriffe

```bash
## Sender: Sendeteil neu starten (nur wenn nötig)
curl -s -X POST -H "X-API-Key: <Schlüssel>" http://192.168.178.33/api/station/1/backend/restart

## Katalog neu aufbauen (nach dem Verschieben vieler Dateien, ~47 s)
curl -s -X POST -H "X-Meldung-Schluessel: <Schlüssel>" http://192.168.178.53:8881/katalog/aktualisieren

## Betreiber freischalten
python3 erlaubte-setzen.py <chatId>

## Bot von Hand testen (ohne Telegram)
bash bot-test.sh "was läuft"
```

---

### 10. Betriebsregeln (aus Schäden gelernt)

1. **Maskierte Fassungen nie einspielen.** Beim Vergleichen von Abläufen werden
   Kennungen durch `<GEHEIM>` ersetzt — wer die maskierte Datei einspielt, killt den
   Bot (Telegram antwortet dann 404). Der Patcher prüft das inzwischen selbst.
2. **Nach jeder Änderung am Erzeuger die Importdateien neu bauen** (macht
   `agent-patchen.sh` automatisch) — sonst wird eine alte Fassung eingespielt.
3. **Nie komplett neu bauen**, sondern patchen: ein Neubau setzt an den Werkzeugknoten
   das Feld `name` und ändert damit die Werkzeugnamen gegenüber dem Modell.
4. **Vor jeder Änderung sichern** (`fassung-sichern.sh`).
5. **Nach dem Einspielen prüfen**: `anordnung-pruefen.py` (0 Befunde) und einen
   Kurzbefehl über den Testeingang.

## Störungen

Alles hier ist **selbst passiert** und behoben — mit dem jeweiligen Symptom, der
Ursache und der Regel, die daraus wurde.

---

### 11. Der Bot antwortet gar nicht mehr (Telegram 404)

**Symptom:** Jede Nachricht läuft ins Leere; Sprachnachrichten melden „Die
Sprachnachricht konnte nicht verarbeitet werden".
**Ursache:** Beim Vergleichen zweier Abläufe wurde die **maskierte** Fassung
(eingesetztes `<GEHEIM>` statt Telegram-Kennung und Schnittstellenschlüssel)
eingespielt.
**Behebung/Regel:** Maskierte Fassungen **nie** einspielen.
**Diagnose ohne Geheimnisse:** `getFile` mit einer alten `file_id` muss 200 liefern;
`sendMessage` an einen unbekannten Chat muss 400 „chat not found" liefern (nicht 404).

---

### 12. Werkzeuge brechen ab: „i is not defined"

**Symptom:** Der Radio-Werkzeugablauf antwortet mit einem JS-Fehler.
**Ursache:** Eine **alte** Importdatei (`/tmp/radio-werkzeuge-import.json`) wurde
eingespielt — sie enthielt noch ein kaputtes Suchmuster.
**Regel:** Nach jeder Änderung am Erzeuger die Importdateien neu bauen;
`agent-patchen.sh` macht das inzwischen selbst.

---

### 13. Jeder Listenknopf sagt „Diesen Auftrag kann ich noch nicht"

**Symptom:** Wiedergabelisten-Knöpfe laufen ins Leere.
**Ursache:** Nach dem Umbenennen eines Knotens las der Code noch das **alte**
Feld (`listenArt`).
**Regel:** Nach Umbauten nach Altlasten suchen — der Patcher prüft das automatisch.

---

### 14. Ansage wird nicht gesprochen / bricht ab

| Symptom | Ursache | Lösung |
| --- | --- | --- |
| „Generator max buffered length exceeded" | Ansage in einem Rutsch hochgeladen; Liquidsoap puffert am Hafen nur ~10 s | der Dienst sendet **im Sendetakt** (0,2-s-Stücke) |
| Erster Satz fehlt | Liquidsoap schaltet den Hafen erst nach ein paar Sekunden durch | Vorlaufstille 5,5 s (`schweigen`), Nachlauf 1,5 s |
| Zwei Wünsche gleichzeitig: der zweite kommt nicht | der Sender hat nur **einen** Hafen; der zweite wartet | nacheinander sprechen |
| Zweiter Wunsch wird nicht gespielt | `request.queue` spielt der Reihe nach | vor dem Sofortspielen die unterbrechende Warteschlange leeren (`interrupting_requests.flush_and_skip`) |

---

### 15. Wunsch wird nicht angenommen

| Meldung | Bedeutung |
| --- | --- |
| „This song was already requested and will play soon." | der Wunsch steht schon in der Warteschlange — kein Fehler |
| „This song or artist was played too recently" | Sperrfrist; im Betrieb auf **0** gesetzt (`request_threshold`), damit Wünsche immer gehen |
| „No interrupting tracks to play" | die Liste zum Unterbrechen war selbst noch „kürzlich gespielt" (Listenart war `once_per_x_minutes`) — richtig ist Typ `default` + `interrupt` |
| Aufforderung zur Wahl | mehrere Titel passen — der Bot fragt absichtlich nach |

---

### 16. Antworten sahen falsch aus (behobene Anzeigefehler)

| Symptom | Ursache | Lösung |
| --- | --- | --- |
| „⚠️ (keine Ausgabe)" statt der Titelliste | der zweite Versuch antwortete leer und **überschrieb** die brauchbare Liste | leere Antworten ersetzen nichts mehr; Rückfrage gilt nicht mehr als Fehlschlag |
| Keine Knöpfe bei mehreren Titeln | das Modell zog die Liste in **eine** Zeile, `auswahl` kam nicht durch | der Bot baut die Knöpfe aus der nummerierten Liste, auch aus einer Zeile |
| Liste endet bei „5" | Text bei 300 Zeichen abgeschnitten | Auswahllisten dürfen bis 1200 Zeichen |
| Antwort kommt nicht an (Telegram-Fehler „can't parse entities") | spitze Klammern im Text (z. B. `<Titel>`) bei `parse_mode: HTML` | Texte werden maskiert (`&`, `<`, `>`) |
| Bearbeiten der Nachricht scheitert | Nachricht zu alt/gelöscht | zweiter Sendeversuch als neue Nachricht |
| „was gibt es für Meldungen" liest ungefragt eine Nachricht vor | das Modell hielt „Meldungen" für Nachrichten | Stufe 0 erkennt Postfachfragen selbst (0,4 s statt 45 s, **ohne** Ansage) |

---

### 17. Sprache und Spracherkennung

| Symptom | Ursache | Lösung |
| --- | --- | --- |
| Kurze deutsche Sätze werden als Englisch erkannt | `language` war „automatisch" | fest `de` |
| Namen werden verhört („neue Runner" statt „Nirvana") | fehlender Kontext | Fachhinweis mit den 45 häufigsten Interpreten als `prompt` |
| Stimme zu leise im Programm | Piper liefert −16,6 LUFS, das Musikprogramm −9,8 LUFS (die eigene Stimme `deine-stimme` läuft durch dieselbe Kette) | Lautstärke-Kette (siehe `HANDBUCH.md`, Abschnitt 2) |
| Ansage wird trotz Verstärkung nicht lauter | ohne Verdichtung muss der Begrenzer ständig eingreifen | Verdichtung **vor** dem Begrenzer; Freigabe 40 ms statt 120 ms |
| Die Ansage wurde leiser statt lauter | die Vorausschau des Begrenzers verglich schon geglättete Werte | immer mit den **rohen** Werten vergleichen |
| Ansage klingt nach der **männlichen Stimme** (`de_thorsten`) statt nach `deine-stimme` | der Stimmendienst konnte nicht sprechen — meist war die GPU voll und RVC antwortete mit `CUDA out of memory` (HTTP 500); `radio-tts` spricht dann **absichtlich** mit der Ersatzstimme weiter | Ursache prüfen: `nvidia-smi` (Reserve frei?) und das Dienstprotokoll (`docker logs radio-tts`, Zeile „Eigene Stimme nicht erreichbar …“); Platz schaffen (siehe unten), dann erneut sprechen lassen |
| Erste Ansage nach langer Pause dauert ~9 s länger | `sprechdienst` lädt das RVC-Modell beim ersten Aufruf | kein Fehler — nur die erste Erzeugung braucht länger |
| Ansage klingt im Sender **höher/heller** als in den Telegram-Proben | **Kein Tonhöhenfehler** (gemessen 2026-09-23: Grundton 242,3 Hz roh = 242,3 Hz im Stream). Die Lautstärkekette im Radiodienst macht die Stimme aber **heller** (spektraler Schwerpunkt 2688 → 2929 Hz) und **lauter** (−20,8 → −12,2 LUFS) — heller + lauter wird als „höher" gehört | nichts umbauen; zum Prüfen: Stream mitschneiden, Ansage mit `silencedetect` finden und schneiden, roh vs. Sendung per Gehör und Messung vergleichen (Weg unten) |

**„Im Sender klingt sie höher" — nachgemessen am 2026-09-23:** Der Weg wurde Stufe
für Stufe verglichen (rohe DEINE-STIMME-Datei → Lautstärkekette im Dienst → MP3/Sendetakt →
Stream): Der **Grundton ist identisch** (242,3 Hz roh und im Stream-Mitschnitt,
Autokorrelation); der **spektrale Schwerpunkt** steigt dagegen von 2688 Hz auf
2929 Hz, die **Lautheit** von −20,8 auf −12,2 LUFS. Ursache ist die gewollte
Lautstärkekette (Hochpass 80 Hz, Verdichtung 3:1, Begrenzer) — Telegram-Hörproben
ohne Kette klingen deshalb wärmer. Messweg: Stream mit `ffmpeg` mitschneiden
(`-c copy`), die Ansage per `silencedetect=noise=-40dB:d=2.5` finden, den Abschnitt
schneiden (`ffmpeg -ss … -t … -ac 1 -ar 22050`), Grundton mit einem kleinen
Autokorrelations-Skript vergleichen.

**Behoben am 2026-09-23 (meine Wahl „Variante 3"):** Die Lautstärkekette ist
entschärft — `TTS_HOCHPASS_HZ=50`, `TTS_KOMPRESSOR_SCHWELLE_DB=-18`,
`TTS_KOMPRESSOR_VERHAELTNIS=2.0`, `TTS_ZIEL_RMS_DB=-12.5` (statt 80 / −19 / 3,0 /
−11,5; in `/opt/radio-tts/geheim.env`, Sicherung daneben). Weniger Verdichtung = die
Stimme klingt weniger hell; der Pegel liegt bei −12,8 statt −12,2 dBFS Sprech-RMS.
Prüfen: `docker exec radio-tts env | grep TTS_`.

**Grafikspeicher (das war am 2026-09-23 die Ursache):** Die 3090 Ti (24 GB) trug
gleichzeitig Ollama (18,7 GB — direkt vor jeder Bot-Ansage geladen), den alten
`whisper-stt` (1,8 GB), den Home-Assistant-Whisper (1,8 GB), ComfyUI (0,3 GB) und den
DEINE-STIMME-Dienst — zusammen mehr, als hineinpasst. **Behoben:** `whisper-stt` (LXC 105) ist
gestoppt und auf Handbetrieb gestellt (seit dem Umzug der Spracherkennung auf die MI50
nicht mehr verdrahtet; Start bei Bedarf `systemctl start whisper-stt`), `sprechdienst` gibt
nach jeder Ansage seinen CUDA-Zwischenspeicher frei und läuft mit
`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`. Reserve im Betrieb: rund 2,6 GB.

---

### 18. Bedienung und Deutung

| Symptom | Erklärung |
| --- | --- |
| „Es steht keine Auswahlliste bereit" | die gemerkte Liste ist verbraucht oder der Dienst wurde neu gestartet → neu suchen |
| „Die Auswahl ist abgelaufen" | offene Wiedergabelisten-Auswahl überlebt keinen Dienstneustart |
| Der Bot fragt nach, obwohl der Titel klar war | zwei Treffer lagen zu dicht beieinander — lieber fragen als den falschen Titel spielen |
| „Nicht erledigt: Nr. 1" nach einer Rückfrage | kam früher vor, ist behoben (Fassung 7) |
| `/api/nowplaying` zeigt noch den alten Titel | die Adresse ist **15 s** gecacht |

---

### 19. Sender-Archiv

| Symptom | Ursache | Regel |
| --- | --- | --- |
| Nach dem Verschieben von Dateien fehlen Titel, Wiedergabelisten sind leer | AzuraCast gleicht per `md5(Pfad)` ab — Plattenverschieben löscht den Eintrag | Ordner **nur über die API** verschieben (`files/batch` mit `do=move`) |
| Suche findet nichts, obwohl das Wort vorkommt | mehrere Wörter werden mit **UND** verknüpft | Füllwörter weglassen oder im Katalogdienst unscharf suchen lassen |
| Ein Suchlauf liefert plötzlich russische Titel | eine leere Suche liefert das **ganze** Archiv (alphabetisch vorne) | nie ohne Suchbegriff suchen (die Werkzeuge verhindern das) |
| Der Bot schlägt Live-Aufnahmen vor | `_Archiv/` (7.906 Titel) und `moderation/` | werden vom Suchindex und vom Werkzeug ausgeschlossen |

---

### 20. Mehrere Titel in einer Nachricht — nur der letzte lief

**Symptom:** „spiele X und danach Y" (und jede Nachricht mit mehreren Musikwünschen):
Am Ende lief nur der letzte Titel, die ersten meldeten „nicht erledigt".
**Ursache:** Jeder Wunsch wurde als **Sofortspielen** (`do=immediate`) eingetragen und
schnitt damit den vorigen ab; Stufe 3 sah den ersten Titel nicht mehr als laufend an.
**Behebung/Regel (Fassung 10):** Bei mehreren Musikbefehlen einer Nachricht läuft der
**erste sofort**, alle weiteren werden **automatisch eingereiht** (`einreihen=true`).
Gemessen: „spiele Benzin von Rammstein und danach Hyper Hyper von Scooter" →
„läuft jetzt sofort" + „wurde eingereiht". Bis zu **zehn** Aufgaben je Nachricht.

---

### 21. „weiter" startete den Sendeteil neu

**Symptom:** Nach „weiter" war der Stream kurz weg (Neustart des Sendeteils).
**Ursache:** `/api/station/1/backend/{action}` kennt nur `skip, disconnect, start, stop,
reload, restart`. Eine **unbekannte** Aktion — hier `play` — antwortet trotzdem mit
**200 „Dienst neu gestartet"** und startet den Sendeteil wirklich neu (am 2026-09-20
am laufenden Sender nachgemessen).
**Behebung/Regel (Fassung 10):** „weiter" wird auf `start` abgebildet. Überhaupt nur
diese sechs Aktionen verwenden.

---

### 22. Überblick: Wetter fehlte, 8 Minuten wurden nur 4,7

*(Gilt für Fassung 10; seit Fassung 11 gibt es keine Minutenangabe mehr.)*

**Symptom:** Im Überblick stand „wetter nicht erreichbar", und „überblick 8 minuten"
endete nach 4,7 Minuten.
**Ursache:** Die öffentlichen Wetter-Feeds (wetter.de, wetter.com, tagesschau) liefern
**404**; je Quelle wurden nur 4 Meldungen gelesen, damit war der Vorrat zu klein.
**Behebung/Regel:** Wetter kommt im Überblick über **Open-Meteo** (Ort aus
`RECHERCHE_WETTER_ORT`), je Quelle werden **10** Meldungen gelesen, und der Text wird am
Satzende auf rund die Ziellänge gekürzt (1050 Zeichen je Minute gemessen). Ergebnis:
1 Min → 72 s, 3 Min → 194 s, 8 Min → 491 s.

---

### 23. Lange Ansage bricht ab (n8n-Zeitablauf)

**Symptom:** Ein mehrminütiger Beitrag kam nur teilweise oder die Ausführung meldete
einen Zeitablauf.
**Ursache:** Die Ansageknoten hatten **5 Minuten** Zeitablauf; der Dienst sendet im
Sendetakt, ein 8-Minuten-Beitrag braucht also rund 10 Minuten (Erzeugung + Sprechen).
**Regel:** Für Ansage- und Überblickknoten **15 Minuten** (900000 ms) Zeitablauf
einstellen; vor einem langen Beitrag prüfen, dass gerade keine zweite Ansage läuft
(der DJ-Hafen verträgt nur eine).

---

### 24. Suchmaschinen sperren den Bot — „normale Internetseiten" blieben aus

**Symptom:** Der Themen-Überblick brachte Presse-Schlagzeilen und Wikipedia, aber keine
Seite aus dem offenen Netz („Web 0").
**Ursache:** Öffentliche Suchmaschinen sperren Rechner ohne Anmeldung sehr
unterschiedlich (gemessen am 2026-09-21 aus dem Dienst-Container): DuckDuckGo antwortet
mit **202** ohne Treffer, Mojeek mit **Captcha**, Ecosia mit **403**, kicker.de mit 403 —
nur **Bing** liefert eine Ergebnisliste. Die Links dort sind außerdem verpackt
(`bing.com/ck/a?…&u=a1<base64>`); ohne Auspacken ist keine Seite lesbar.
Die SearXNG-Instanz in **LXC 108** ist nur ein **Quelltext-Klon** (/opt/searxng, kein
Dienst, kein Port) — sie läuft nicht.
**Behebung/Regel:** Der Dienst versucht **eigene SearXNG** (`RECHERCHE_SEARX_URL`), dann
DuckDuckGo, dann Bing (mit Auspacken der Links). Fällt alles aus, tragen Presse
und die 21 Feeds den Beitrag — die Websuche wird still übersprungen.
Eigene Seiten ohne Feed gehören in `RECHERCHE_WEBSEITEN` (kommagetrennt).
**Erledigt am 2026-09-21:** Die eigene Instanz läuft in **LXC 108** auf
`http://192.168.178.26:8888` (Einrichtung: `NACHBAU/searxng-einrichten.md`), der
Dienst hat `RECHERCHE_SEARX_URL` gesetzt. Gemessen: 20 deutsche Treffer je Suchbegriff,
und jeder Themen-Überblick liest jetzt mindestens eine Netzseite je Thema.

---

### 25. „nicht erreichbar" für Quellen, die nur nichts zum Thema hatten

**Symptom:** Die Antwort nannte 20 Quellen als „nicht erreichbar".
**Ursache:** Im Themen-Betrieb wurde jede Quelle ohne passende Meldung als Ausfall
gezählt.
**Regel:** `ausgefallen` enthält nur echte Ausfälle (nicht ladbar/leer). „Kein Treffer
zum Thema" ist kein Ausfall und wird nicht gemeldet.

---

### 26. Sprechfilter verschluckte „Info" aus „Informatik"

**Symptom:** Im Radio war „Anwendungsgebiet der rmatik" zu hören.
**Ursache:** Die Regel, die Quellenhinweise wie „Details auf." entfernt, enthielt
`Infos?` **ohne Wortgrenze** und löschte damit das „Info" in „Informatik".
**Behebung/Regel:** Wortgrenze am Ende ergänzen — und solche Muster nur am **Textende**
anwenden, sonst verschwindet jedes „Informationen" mitten im Satz. Ebenfalls ergänzt:
Bildnachweise („Alle Rechte vorbehalten", IMAGO, picture alliance) und
Wikipedia-Quellenverweise (`[1]`, `[ 1.1 ]`) werden nicht mehr vorgelesen. Bei
Adressen als Quellenname wird die Hauptdomain genommen (`de.wikipedia.org` → „Wikipedia").

---

### 27. Eigene Suchmaschine antwortete mit „Too Many Requests"

**Symptom:** Die frische SearXNG-Instanz lieferte auf `…/search?q=…&format=json` nur
`429 Too Many Requests`, im Browser (HTML) funktionierte sie.
**Ursache:** `server.limiter: true` in `/etc/searxng/settings.yml`. Der Limiter ist für
öffentliche Instanzen gedacht und verlangt von Abrufern ein Link-Token — ein Bot ohne
Browser-Kennung fällt durch.
**Regel:** Für die hausinterne Instanz `limiter: false` setzen (danach
`systemctl restart uwsgi`). Zusätzlich muss `search.formats` **`json`** enthalten —
sonst verweigert SearXNG die JSON-Schnittstelle ganz.

---

### 28. Wikipedia fand „künstliche intelligenz" nicht

**Symptom:** Zu einem mehrwortigen Thema kam kein Hintergrund („Wiki 0"), obwohl der
Artikel existiert.
**Ursache:** Die Einleitungs-Schnittstelle braucht den **genauen** Titel:
`…/page/summary/künstliche_intelligenz` antwortet **404**, `Künstliche_Intelligenz`
nicht. Auch die Schreibweise mit nur großem Anfangsbuchstaben („Künstliche intelligenz")
ist falsch. Außerdem liefert Wikipedia für Kürzel wie „KI" eine **Begriffsklärung**
(`type: disambiguation`), deren Text als Hintergrund wertlos ist
(„KI steht für: sumerische Gottheit, …").
**Behebung/Regel:** Erst mehrere Schreibweisen probieren, dann über die Such-Schnittstelle
(`action=query&list=search`) den richtigen Titel holen; Artikel mit
`type != "standard"` verwerfen. Gemessen danach: „künstliche intelligenz" →
„Künstliche Intelligenz ist ein Forschungs- und Anwendungsgebiet der Informatik…".

---

### 29. Presse verdrängte Netz und Feed im Themen-Überblick

**Symptom:** Der Beitrag bestand je Thema fast nur aus Schlagzeilen, „Web 0", obwohl
die eigene Suchmaschine lief.
**Ursache:** Die Kontingente waren kleiner als ihr Bedarf: je Thema 4 Plätze
(`RECHERCHE_THEMA_MELDUNGEN`), davon bis zu 3 aus der Presse und 1 aus Wikipedia —
für Netz und Feeds blieb nichts übrig. Presse-Treffer tragen außerdem **keinen**
Fliesstext, sodass der Beitrag inhaltlich dünn blieb.
**Behebung/Regel:** Vorgabe jetzt **6** Plätze je Thema, und die Presse bekommt nur so
viele, dass für Netz und Feeds je **ein** Platz reserviert bleibt. Damit kommen zu jedem
Thema Schlagzeilen **und** Inhalt (gelesene Seite). Der Wikipedia-Platz ist seit dem
2026-09-25 frei — der Nachrichten-Überblick bringt bewusst keine Lexikon-Einleitungen
mehr (siehe §32).

---

### 30. „Pfeil rechts" und Marken im Sprechtext

**Symptom:** Mitten im Beitrag war „… an | tagesschau.de Suche Pfeil rechts Pfeil rechts"
zu hören.
**Ursache:** Zwei Eigenheiten moderner Seiten: Beschriftungen von Symbolen stehen in
`<svg><title>`-Elementen (mehrere `title`-Elemente je Seite — der Leser hängte sie alle
an den Seitentitel), und Bedienhilfen für Vorleser (`class="visually-hidden"`,
`aria-hidden="true"`) standen mitten in den Absätzen.
**Behebung/Regel:** Nur das **erste** `title` außerhalb übersprungener Bereiche als
Seitentitel nehmen (`aria-hidden`/`visually-hidden` aussortieren) und den Marken-Zusatz
hinter dem Titel (`… | tagesschau.de`) entfernen.

---

### 31. Nach einem Neustart von LXC 108 keine Suche mehr

**Symptom:** Nach `pct reboot 108` antwortete die Suchmaschine minutenlang nicht
(„Web 0" im Themen-Überblick), obwohl beide Dienste als `enabled` eingetragen waren.
**Ursache:** Zwei Dinge zusammen:
1. Der Container hing in der Netzwerkeinrichtung — `ip6=dhcp` löste
   dhclient-Solicits mit Wartezeiten bis **68 s** aus, `networking.service` blieb auf
   „activating".
2. Die Anwendung lief über den **SysV-Emperor** (`/etc/init.d/uwsgi`), dessen Einheit
   `After=network-online.target` ist — sie startete deshalb erst nach dem Netz.
**Behebung/Regel:** Im Container `ip6=manual` setzen (`pct set 108 -net0 … ,ip6=manual`)
und die Anwendung über eine **eigene systemd-Einheit** `searxng.service` starten
(`ExecStart=/usr/bin/uwsgi --ini /etc/uwsgi/apps-available/searxng.ini`,
`After=network.target`); SysV-`uwsgi` abschalten und den Vassal-Eintrag entfernen,
sonst streiten zwei uWSGI-Instanzen um Port 8888. Neustartprobe gehört zur Abnahme:
`pct reboot 108` → `systemctl is-system-running` = `running`, `searxng` = `active`,
Suche liefert Treffer.

---

### 32. Etiketten, Werbeseiten und Wiki-Definitionen im Nachrichten-Überblick

**Symptom:** Ansagen klangen „merkwürdig": Autorenzeilen wurden vorgelesen
(„… Von Stephan Ueberbach."), Quelle und Schlagzeile standen als Etiketten getrennt
(„boerse: EQS-News: …"), eine Kursseite lieferte Beiwerk („Keine Gewähr …"), Sätze
brachen mitten ab, und zu Themen kamen Wikipedia-Definitionen statt Nachrichten.
**Ursache:** Feed-Texte enden mit Autorenzeilen; die Presse-Suche liefert auch
Draht-Meldungen (EQS/DGAP); die gelesene Web-Seite war eine Kursseite; der Überblick
hatte Wikipedia fest eingeplant (`RECHERCHE_THEMA_WIKI` = 1) und kannte keine
Seiten-Auswahl.
**Behebung/Regel:** `dienst/suche.py` säubert Texte (`_saeubern`), baut Stücke als
„Titel. Anfang" mit Quellen-Satz dahinter (`_meldet`), überspringt Draht-/Werbequellen
(`PRESSE_VERBOTEN`), liest nur Seiten **bekannter Nachrichten-Anbieter**
(`SEITEN_LISTE`) und verwirft Kassenbon-Seiten (`SEITE_VERBOTEN`). Wikipedia ist aus
dem Nachrichten-Überblick **aus** (`RECHERCHE_THEMA_WIKI` = 0; Kurzinfo
`art=wikipedia` bleibt). Prüfen: `POST /recherche {"art":"ueberblick",
"themen":"börse","trocken":true}` → keine „Von …"-Zeile, kein „(dpa)", `"wiki": 0`,
keine „kostenlos"-Reste.

---

### 33. Anordnung verrutscht — Knoten außerhalb der Rahmen

**Symptom:** `anordnung-pruefen.py` meldete im Agenten **7 Knoten ohne Rahmen**
(`Kurzbefehl?`, `Planen`, `Plan Antwort`, `Plan da?`, `Befehle lesen`, `Befehl da?`,
`Kurz?`), einen Rahmen **ohne Knoten** und **zwei sich überlappende Rahmen**
(`Notiz Analyse` / `Notiz Dienste`). In der Oberfläche hing der blaue Rahmen
„Stufe 0 und Stufe 1“ unterhalb der Knoten, die er erklären soll.
**Ursache:** Die Rahmen werden aus den Knotenpositionen **gerechnet**
(`werkzeuge/agent-wf-bauen.py`, Tabellen `BEREICHE`). Wird eine Haftnotiz auf der
Zeichenfläche mit der Maus verschoben, stimmt diese Rechnung nicht mehr — die Knoten
liegen dann neben ihrem Rahmen. (Passiert z. B. beim Arbeiten in der Oberfläche, wenn
ein Zug auf einer Haftnotiz beginnt: ein Links-Zug auf leerer Fläche ist in n8n eine
Auswahl, ein Links-Zug auf einer Notiz verschiebt sie.)
**Behebung/Regel:** Der **Plan im Bauwerkzeug ist die Quelle**, nicht die Oberfläche:

```bash
cd ../../werkzeuge
bash agent-patchen.sh --aufraeumen          # legt Positionen UND Rahmen neu
python3 anordnung-pruefen.py /tmp/radio-agent-neu.json    # muss 0 Befunde melden
bash agent-einspielen-nur.sh /tmp/radio-agent-neu.json
## n8n neu starten, damit die Fassung greift:
ssh -F ~/.ssh/config ai-server \
  "pct exec 103 -- docker restart n8n"
```

Geprüft am 2026-09-21: 85 Knoten und Rahmen neu gelegt, danach **0 Befunde**,
Bot antwortet (Statikdaten mit Betreiberliste und Testerschlüssel bleiben erhalten).
**Merksatz:** In der Oberfläche nur **ansehen** — nicht ziehen. Wer etwas ändern will,
ändert die Quelle und spielt neu ein (siehe `ANHANG/n8n-oberflaeche.html` §18).

---

### 34. Wenn nichts mehr geht (Reihenfolge)

1. `curl -s http://192.168.178.53:8881/health` — läuft der Dienst?
2. `curl -s http://192.168.178.33/api/nowplaying/1` — läuft der Sender?
3. `bash playlist/16-ausfuehrungen.sh 3` — was hat der Ablauf zuletzt getan?
4. `curl -s http://192.168.178.187:11434/api/tags` — antwortet das Sprachmodell?
5. Läuft n8n? (`docker ps` im LXC 103) — nach jedem Einspielen startet es neu (~20 s).
6. Letzte Fassung einspielen (aus `<projektordner>/sicherungen/radio-fassungen/`) und den Dienst aus
   `<fassung>/dienste/` neu ausrollen.

## Testen

Alle Prüfläufe des Bots, mit Aufruf und Erwartung. Stand 2026-09-21 (Fassung 11);
Stimmen-Prüfung ergänzt 2026-09-23 (Fassung 19) —
alle hier genannten Läufe waren zuletzt **grün**.

Grundsatz: Prüfläufe dürfen den Sendebetrieb **nicht** stören. Wo eine echte Ansage
nötig ist, steht das ausdrücklich dabei (`--live`); sonst wird nur erzeugt
(„trocken").

---

### 35. Schnelle Prüfläufe (Sekunden, ohne Sendebetrieb)

```bash
cd ../../werkzeuge
bash kurz-test.sh            # Stufe 0: 19 Sätze  -> erwartet "19 von 19"
bash antwort-test.sh         # Urteil, Nacharbeit, Antwort, Auswahlknöpfe -> "20 ok, 0 abweichend"
python3 anordnung-pruefen.py /tmp/radio-agent-neu.json   # Zeichenfläche -> "0 Befunde"
bash playlist/11-dienst-art-test.sh                      # Weiche des Bot-Eingangs -> "37 von 37"
```

| Prüflauf | Was er sichert |
| --- | --- |
| `kurz-test.sh` / `kurz-test.js` | dass Stufe 0 die richtigen Sätze erkennt (Liedwunsch, Richtung, Steuerung, Status, Postfachfrage) **und** alles andere an die KI-Kette weiterreicht |
| `antwort-test.sh` / `antwort-test.js` | dass eine leere Nachfass-Antwort keine Ausgabe löscht, dass eine Rückfrage nicht „nachgefasst" wird, dass Auswahlknöpfe auch aus einer zusammengezogenen Liste entstehen, dass ein echter Fehlschlag weiter gemeldet wird |
| `anordnung-pruefen.py` | jeder Knoten in genau einem Rahmen, keine Überlappung, jeder Knoten mit Beschriftung |
| `playlist/11-dienst-art-test.sh` | die Weiche vom Telegram-Update bis zur Entscheidung (Knöpfe, Texte, Dienste) mit der **echten** `EINGABE_JS` |
| `anordnung-doku.sh` | erzeugt `ANORDNUNG.md` neu und prüft dabei alle vier Abläufe |

Diese Läufe holen ihren Code direkt aus dem Erzeuger (`js-holen.py`) — sie prüfen
also die **Quelle**, nicht die laufende Fassung im Speicher.

---

### 36. Dienst prüfen (braucht den laufenden Dienst)

```bash
cd ../../werkzeuge
python3 meldungen/19-meldungen-test.py          # 45 Proben: Textaufbereitung, Postfach, Ansagewege
python3 meldungen/19-meldungen-test.py --live   # zusätzlich eine echte Ansage in den Sender
python3 meldungen/23-lautstaerke-test.py        # 8 Proben: Lautstärke (rechnet + fragt den Dienst)
bash playlist/09-dienst-test.sh                 # alle Wiedergabelisten-Wege ohne Telegram
bash katalog-test.sh                            # Katalogdienst: Kontextsuche, Richtung
bash kontext-test.sh / bash kontext2-test.sh    # Deutung mehrerer Aufträge, Mengen, Bezüge
bash stimme-pruefen.sh                          # sucht eine Sprachprobe, die der Erkenner sauber versteht

## Ueberblick trocken pruefen (keine Ansage im Sender, nur Text und Dauer):
MK=$(cat <dokuordner>/NACHBAU/zugangsdaten/meldung-schluessel.txt)
curl -s -X POST http://192.168.178.53:8881/recherche -H 'Content-Type: application/json' \
  -H "X-Meldung-Schluessel: $MK" -d '{"art":"ueberblick","themen":"ki, raumfahrt","trocken":true}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['dauer_sekunden'], d['themen'], d['presse'], d['wiki'], d['web'], d['quellen'], d['ausgefallen'])"
## erwartet: Sprechzeit je nach Material (0,4–3 Min), Themen beide Themen, Presse ~3 je Thema,
##           Wiki 0/1, ausgefallen nur bei echten Ausfaellen
## ohne Themen (neueste Meldungen der Quellen):  '{"art":"ueberblick","trocken":true}'
## mit gewaehlten Quellen:                        '"quellen":"heise golem"'

## Eigene Suchmaschine (SearXNG in LXC 108) pruefen:
ssh -F ~/.ssh/config ai-server \
  "pct exec 108 -- curl -s -m 20 'http://127.0.0.1:8888/search?q=test&format=json' | head -c 120"
## erwartet: {"query": "test", "results": [ ... ]}   (kein "Too Many Requests")
curl -s -m 30 \
  'http://192.168.178.26:8888/search?q=k%C3%BCnstliche+intelligenz&format=json&language=de-DE' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d["results"]), "Treffer")'
## erwartet: rund 20 deutsche Treffer; im Trockenlauf oben muss dann "web" >= 1 sein
## und "gelesen" mindestens eine Adresse enthalten

## Stimme der Ansagen prüfen (Standard + DEINE-STIMME auf Wunsch + Piper):
curl -s -D - -o /tmp/probe_standard.mp3 -X POST http://192.168.178.53:8881/v1/audio/speech \
  -H 'Content-Type: application/json' -d '{"input":"Test der Standardstimme."}' | grep -i x-stimme
## erwartet: x-stimme: de_thorsten (Standard seit 2026-09-25)
curl -s -D - -o /tmp/probe_deine-stimme.mp3 -X POST http://192.168.178.53:8881/v1/audio/speech \
  -H 'Content-Type: application/json' -d '{"input":"Test der eigenen Stimme.","voice":"deine-stimme"}' | grep -i x-stimme
## erwartet: x-stimme: deine-stimme   (bei Ausfall des Stimmendienstes: x-stimme: de_thorsten + x-stimme-ersatz: 1)
curl -s -D - -o /tmp/probe_piper.mp3 -X POST http://192.168.178.53:8881/v1/audio/speech \
  -H 'Content-Type: application/json' -d '{"input":"Piper-Gegenprobe.","voice":"de_thorsten"}' | grep -i x-stimme
## erwartet: x-stimme: de_thorsten
curl -s http://192.168.178.116:10205/health   # Stimmendienst auf CT 111
## erwartet: {"ok": true, ..., "pitch": 4, "basis": "de-DE-AmalaNeural", "tempo": "+40%", "index_rate": 0.65}

## Hat eine Ansage auf die Ersatzstimme ausweichen muessen? (leer = alles in Ordnung;
## die Meldung erscheint nur, wenn die eigene Stimme gewünscht war)
ssh -F ~/.ssh/config ai-server \
  "pct exec 103 -- docker logs --since 1h radio-tts 2>&1 | grep -i 'eigene Stimme' || echo 'ok - keine Ausweichung'"
```

---

### 37. Ende-zu-Ende über den Bot (Testeingang, echtes n8n)

```bash
cd ../../werkzeuge
python3 meldungen/21-bot-meldungen-test.py       # 6 Proben: Knopf, Werkzeug, Freigabe, Zeitplan, Aufräumen
python3 meldungen/21-bot-meldungen-test.py --live --warten   # mit echter Ansage und Warten auf den Zeitplan
python3 playlist/15-bot-listen-test.py           # Listenwege über den Bot
python3 playlist/15-bot-listen-test.py --spielen # zusätzlich wirklich abspielen (unterbricht die Sendung)
bash bot-test.sh                                 # feste Probesuite (Hilfe, Wunsch, Knopf, Suche, Unsinn)
bash frage.sh "themen: raumfahrt"                # EINZELNE Nachricht (Ansage im Sender! ~1–2 Min)
bash frage.sh "spiele Benzin"                    # einzelne Nachricht
bash knopf.sh w1                                 # einen Knopf drücken
bash sprache-test.sh / bash sprache2-test.sh     # Sprachnachrichten (erzeugt OGG-Dateien)
bash sofort-bot-test.sh / bash sofort-knopf-test.sh  # Sofortwege und der Knopf „Trotzdem sofort spielen"
bash frage.sh "ueberblick ki, raumfahrt"         # Themen-Ueberblick (Ansage im Sender!)
bash frage.sh "themen: photovoltaik aus heise golem"   # Themen + gewaehlte Quellen
bash frage.sh "gib mir einen ueberblick zu ki, aber lies ihn nicht vor"   # darf NICHT sprechen
bash frage.sh "spiele Benzin von Rammstein und danach Hyper Hyper von Scooter"   # Sammelbefehl:
erwartet „läuft jetzt sofort" + „wurde eingereiht"
```

**Wichtig:** `bot-test.sh` nimmt **keine** Nachricht entgegen — es ist eine feste Suite.
Einzelne Nachrichten gehen über `frage.sh` / `knopf.sh`; beide lesen den Testerschlüssel
aus `/tmp/.botschluessel` (600). Fehlt die Datei, entsteht sie so (der Wert wird **nicht**
angezeigt):

```bash
cd ../../werkzeuge
scp -q hol-testerschluessel.js ai-server:/tmp/
ssh -F ~/.ssh/config ai-server \
  "pct push 103 /tmp/hol-testerschluessel.js /tmp/hol-testerschluessel.js >/dev/null && \
   pct exec 103 -- bash -lc 'docker cp /tmp/hol-testerschluessel.js n8n:/tmp/ >/dev/null && \
   docker exec -u node n8n node /tmp/hol-testerschluessel.js'" | head -1 > /tmp/.botschluessel
chmod 600 /tmp/.botschluessel
## Voraussetzung: Tunnel auf den Testeingang
ssh -F ~/.ssh/config -N -L 5678:192.168.178.53:5678 ai-server
```

Den Verlauf einer Ausführung (Frage, Stufe 0, Befehle, Antwort, Knöpfe, Fehler) zeigt:

```bash
cd ../../werkzeuge
cat bot-letzte.js | ssh -F ~/.ssh/config ai-server \
  "pct exec 103 -- bash -c 'cat > /tmp/bot-letzte.js'"
ssh -F ~/.ssh/config ai-server \
  "pct exec 103 -- bash -lc 'docker cp /tmp/bot-letzte.js n8n:/tmp/ >/dev/null && docker exec -u node n8n node /tmp/bot-letzte.js 3'"
```

Erwartet bei einem Sammelbefehl mit mehreren Titeln: `Befehle: spielen#1, spielen#2(einreihen), …`
— die weiteren Titel tragen `(einreihen)`. Beim Überblick: `Stufe 0: ueberblick` und
`Ueberblick: 🎙️ Überblick gesagt (1.3 Min, Themen raumfahrt, 3 aus der Presse, mit Hintergrund, 1 aus dem Netz)`.
Eine alte Angabe „N minuten" wird **ignoriert**.

Einen **einzelnen** Lauf Knoten für Knoten (auch der Grund, warum eine Nachricht
abgelehnt wurde — z. B. „Kein Zugang" bei fehlendem Testerschlüssel):

```bash
cd ../../werkzeuge
scp -q bot-ausfuehrung.js ai-server:/tmp/
ssh -F ~/.ssh/config ai-server \
  "pct push 103 /tmp/bot-ausfuehrung.js /tmp/bot-ausfuehrung.js >/dev/null && \
   pct exec 103 -- bash -lc 'docker cp /tmp/bot-ausfuehrung.js n8n:/tmp/ >/dev/null && \
   docker exec -u node n8n node /tmp/bot-ausfuehrung.js <nummer>'"
```

Die Prüfläufe räumen hinter sich auf (Meldungen werden verworfen, Titel nicht
dauerhaft eingereiht) und melden am Ende „x ok, y abweichend".

---

### 38. Zeichenfläche und Dokumentation

```bash
cd ../../werkzeuge
bash anordnung-doku.sh                       # holt die laufenden Abläufe, prüft, schreibt ANORDNUNG.md
python3 anordnung-uebersicht.py <ablauf.json>  # Knotenliste als Markdown (Bildschirm)
python3 vorschau.py <ablauf.json> bild.png 0.35   # Ablauf als Bild zeichnen
python3 code-pruefen.py <ablauf.json>        # JS-Syntax aller Code-Knoten prüfen
```

---

### 39. Sendebetrieb prüfen (hört man im Radio)

```bash
cd ../../werkzeuge
python3 meldungen/24-live-pegel.py "Test der Lautstaerke. Eins, zwei, drei."
## schneidet den Stream mit, spielt eine Testansage und vergleicht Stimme und Musik
```

Danach prüfen, dass der AutoDJ wieder läuft:

```bash
python3 - <<'PY'
import json, urllib.request
n = json.loads(urllib.request.urlopen("http://192.168.178.33/api/nowplaying/1").read())
print("live:", n["live"]["is_live"], "| läuft:", n["now_playing"]["song"]["text"])
PY
```

---

### 40. Erwartungswerte (gemessen 2026-09-20)

| Vorgang | Erwartung |
| --- | --- |
| Kurzbefehl (Status, Wunsch, Richtung, Postfachfrage) | 0,3–1,7 s |
| Titelliste mit Knöpfen | 25–30 s, Liste vollständig, Knöpfe passend |
| Knopfdruck | ~1 s, Titel läuft sofort |
| Verwaltungsauftrag (KI-Weg) | 20–60 s, mit Rückfrage vor Änderungen |
| Recherche mit Ansage (Wetter) | ~50 s inkl. Sprechzeit |
| Ansage auf Sendung | Musik verstummt, Stimme hörbar auf Sendungslautstärke, danach AutoDJ |
| Postfach-Karte | innerhalb von 5 Minuten nach dem Ablegen |

---

### 41. Was ein Prüflauf **nicht** abdeckt

* Klang der Stimme (nur messbar, nicht automatisch zu beurteilen)
* ob eine Ansage im Radio „gut" klingt (Lautstärke ist gemessen: −11,8 LUFS auf Sendung)
* Sendungen bei ausgelasteter GPU (Antwortzeiten können dann steigen)

---

### 42. Stimmenwahl — Standard und DEINE-STIMME auf Wunsch (seit 2026-09-25)

Der Bot spricht **standardmäßig mit `de_thorsten`** (Piper, läuft immer, keine GPU).
Die eigene Moderationsstimme **„DEINE-STIMME"** wird **nur auf ausdrücklichen Wunsch** verwendet:

* **Wunsch im Telegram:** „sag durch: … **mit eigener Stimme**“, „… **in der eigenen Stimme**“,
  „… **in eigener Stimme**“, „… **mit meiner Stimme**“
  → der Bot setzt `stimme=deine-stimme`; der Zusatz selbst wird **nicht** vorgelesen. Den Wunsch
  erkennt der Eingang **fest** (unabhängig vom Sprachmodell) und reicht ihn an jeden
  Sprech-Befehl weiter.
* **Ohne Wunsch** bleibt `stimme` leer → Standardstimme (Live-Ansage, Meldungen,
  Überblick und Recherche).
* Einzustellen in `/opt/radio-tts/geheim.env`: `TTS_DEFAULT_VOICE=de_thorsten`;
  die eigene Stimme läuft über den externen Dienst (CT 111, Port 10205, `EIGENE_STIMME_URL`).
  Fällt er aus, spricht der Bot mit `de_thorsten` weiter (`EIGENE_STIMME_ERSATZ`) — keine
  Ansage fällt aus; im Protokoll steht dann „Eigene Stimme nicht erreichbar".
* **Prüfen:** jede Erzeugung schreibt eine Zeile **`Stimme: <name>`** ins Protokoll
  (`docker logs radio-tts | grep 'Stimme:'`); `curl -D- … /v1/audio/speech` liefert die
  Kopfzeile `x-stimme`.
* **Ausfall 25.09. (Ursache):** `torch.OutOfMemoryError` auf CT 111 (Karte bis auf
  59–179 MB belegt). Neu in `sprechdienst.py`: vor/nach jeder Wandlung wird der
  CUDA-Speicher freigegeben und ein Speicherfehler **einmal wiederholt** (2 s Pause) —
  vorher blieben 3,2–3,3 GB liegen und verschärften den Folgefehler.
