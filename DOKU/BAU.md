# Bau — Baugeschichte und Fassungen

## Bau

> **Stand:** 2026-09-25 (laufender Stand: `radio-v21-2026-09-25-zweisprachig`). Diese
> Datei erzählt **wie** der Bot entstand: in welcher Reihenfolge,
> mit welchen Werkzeugen, Entscheidungen und Hindernissen.
>
> * Die **Beschreibung des Ergebnisses** steht in `README.md`, `HANDBUCH.md` und
>   `HANDBUCH.md`.
> * Die **Änderungsliste je Fassung** steht in `BAU.md` (v1–v21).
> * Die **Entwickler-Quellen** liegen in `<dokuordner>/`
>   (Erzeuger, Werkzeuge, Fassungen) — hier im Ordner steht `NACHBAU/` für den Nachbau.
>
> Alle Angaben stammen aus den Fassungssicherungen, den Prüfläufen und dem Protokoll der
> Bausitzungen (19.–25.09.2026).

---

### 1. Das Ziel

Ausgangspunkt (19./20. September 2026): Der eigene Internetradiosender **Deadline Beats**
(AzuraCast, 56.635 Titel) sollte von einem **Telegram-Bot** betrieben werden —
Wünsche sofort oder eingereiht, Richtungswünsche („was aus rock", „90er"), Steuerung
(skip, Status), später **selbst moderieren** (Ansagen im laufenden Programm), ein
Postfach für andere Bots, Recherche für Wetter/Nachrichten/Überblicke.

Alles auf **eigener Hardware**, ohne Cloud: Sprachmodell auf der 3090 Ti, später eine
**eigene Sprecherstimme**, die aus dem eigenen Medienbestand gelernt wurde. Am Ende
stand ein Agent mit acht Werkzeugen, vier Abläufen, sechs Dienstmodulen, eigener
Suchmaschine und eigener Stimme — entstanden in **fünf Tagen**.

---

### 2. Die Bauweise — was dieses Projekt ausmacht

Fünf Regeln prägen den ganzen Bau:

#### 2.1 Erzeuger statt Handarbeit

Der n8n-Ablauf wird **nie** von Hand gebaut oder gezogen.
`werkzeuge/agent-wf-bauen.py` **erzeugt** alle vier Abläufe als JSON (Knoten,
Verbindungen, Positionen, Rahmen, Beschriftungen, Notizen). Änderungen laufen
chirurgisch über `agent-patchen.sh`: nur die genannten Knoten werden ersetzt,
`--aufraeumen` legt Positionen und Rahmen aus dem Plan neu.

> Ein kompletter Neubau ist ausdrücklich verboten — er würde die Werkzeugnamen
> gegenüber dem Sprachmodell ändern (das Modell kennt die Werkzeuge namentlich).

#### 2.2 Fassung vor jeder Änderung

`fassung-sichern.sh <name>` legt unter `<projektordner>/sicherungen/radio-fassungen/<name>/` ab: die vier Abläufe
als JSON, die Dienstmodule, den Dockerfile, die **komplette n8n-Datenbank** und eine
`README.md` mit Beschreibung und Rückweg (Rechte 700/600 — die Abläufe enthalten
Kennungen). Zurückrollen ist damit ein Zweizeiler. So entstanden **19 Fassungen**
(v1…v19) — jede mit einer Zeile in `BAU.md`.

#### 2.3 Erst prüfen, dann einspielen

* Vor dem Einspielen: `anordnung-pruefen.py` (Zeichenfläche), `code-pruefen.py`
  (JS-Knoten), `kurz-test.sh` (Stufe 0), `antwort-test.sh` (Antwortlogik).
* Nach dem Einspielen: ein echter Lauf über den Testeingang und das
  Ausführungsprotokoll `bot-letzte.js` (Frage → Stufe 0 → Befehle → Antwort →
  Knöpfe → Fehler).
* Der Dienst meldet sich nach `dienst-einspielen.sh` selbst (`/health`,
  `/meldungen/status`, `/ansage/status`).

#### 2.4 Quellen = Server

Der Quellstand im Projektordner und der laufende Stand auf dem Server müssen
**byte-gleich** sein — regelmäßige md5-Vergleiche (z. B. `dienst/main.py` ↔
`/opt/radio-tts/app/main.py`, `sprechdienst.py` ↔ CT 111). Was nicht byte-gleich sein kann
(n8n-Datenbank), liegt als Export in `NACHBAU/ablaeufe-laufend/`.

#### 2.5 Dokumentation ist Teil des Baus

Jede Änderung hinterlässt: Fassung + Eintrag in `BAU.md` + betroffene Stellen in
dieser Doku — **mit Datum und Messwerten**. Die Dokumentation dieses Ordners ist selbst
aus diesem Prozess entstanden (erste Fassung am 20.09., seither mehrfach nachgezogen).

---

### 3. Die Chronik

#### 3.1 19./20. September — Grundstein: Archiv, Wunschbot, Fassung v1

* **Archiv prüfen und ordnen:** Das Musikarchiv des Senders wurde durchgesehen
  (Sortierung/Benennung), die AzuraCast-Schnittstelle erschlossen (263 Adressen).
* **Sofortspielen gefunden:** `PUT /files/batch` mit `do=immediate` („Play Now")
  hängt direkt in die unterbrechende Warteschlange — ohne Vorprüfungen. Davor wird
  die Warteschlange geleert (`interrupting_requests.flush_and_skip`), damit der
  **neueste** Wunsch gewinnt. Die Backend-Steuerung nutzt bewusst `start`, **nie**
  `play` (eine unbekannte Aktion antwortet zwar 200, startet aber den Sendeteil neu).
* **Erster Wunschbot** in n8n (`RadioTelegramBot`): Text- und Sprachnachrichten,
  Archivsuche, spielen/einreihen; Sprachmodell auf Ollama für freien Text.
* **Fassung v1** gesichert: „Ausgangszustand (vier Abläufe, wie sie liefen)".

#### 3.2 20. September — der Tag der großen Sprünge (v2–v9)

| Fassung | Was gebaut wurde | Wirkung (gemessen) |
| --- | --- | --- |
| **v2** `…-vor-tempo` | Sicherungspunkt vor der Tempo-Änderung | Rückrollpunkt (163 s je Ansage) |
| **v3** `…-mit-tempo` | `reasoning_effort: none`, **Regelurteil statt Modell**, Schnellweg für gesprochene Formulierungen, `OLLAMA_KEEP_ALIVE=30m` | Ansagen in **1,7 s** statt 163 s |
| **v4** `…-mit-listen` | Modul `playlist.py`: Listen bauen/verwalten/starten über einen eigenen Dienstweg | **0,2–0,7 s** je Schritt |
| **v5** `…-mit-meldungen` | Modul `meldungen.py`: Postfach, Sprechtexte, **Live-Ansage** über den DJ-Hafen, Telegram-Freigabe mit Knöpfen, 5-Minuten-Zeitplan | Der Bot **spricht selbst** im Programm |
| **v6** `…-mit-recherche` | Modul `suche.py`: Wetter (Open-Meteo), Nachrichten/RSS, Wikipedia, `POST /recherche`, Werkzeug `recherche` | „suche nach dem Wetter für X" — und **mehrere Aufgaben** in einer Nachricht |
| **v7** `…-auswahlliste` | Leere Antworten ersetzen nichts mehr, Rückfrage gilt nicht als Fehlschlag, Knöpfe direkt aus der Liste | Ein Wunsch mit mehreren Treffern endet mit **Knöpfen** |
| **v8** `…-moderationslautstaerke` | Lautstärke-Kette: Hochpass, Verdichtung 3:1, Pegelregelung, Begrenzer mit Vorausschau | Moderation **−16,6 → −13,1 LUFS** (Datei), **−11,8 LUFS** auf Sendung (~4 dB lauter) |
| **v9** `…-oberflaeche` | Zeichenfläche des Ablaufs: berechnete Rahmen, Farben je Stufe, Beschriftung an **jedem** Knoten, Übersichtsnotiz; Prüf- und Doku-Werkzeuge | Der Ablauf erklärt sich beim Öffnen selbst (**0 Befunde**) |

Dazwischen der **Umbau vom Wunschbot zum Agenten**: vier Abläufe (der Telegram-Agent +
drei Werkzeug-Abläufe), dreistufige Kette **Planen → Ausführen → Prüfen** — der Agent
prüft jeden Auftrag **gegen den echten Senderzustand** („Antworten sind belegt, nicht
behauptet"). Die alten Wunschbot-Abläufe blieben als Archiv erhalten.

#### 3.3 21. September — Überblick, Sammelbefehle, eigene Suchmaschine (v10–v12)

* **v10:** `art=ueberblick` in `POST /recherche` (mehrere Quellen, Länge in Minuten;
  `ANSAGE_MAX_ZEICHEN` 700 → **9000** ≈ 8,5 Minuten); Stufe-0-Wort **„überblick"**;
  Sammelbefehle bis 10 Aufgaben (erster Titel sofort, weitere eingereiht);
  Ansage-Zeitabläufe der n8n-Knoten auf 15 Minuten (der Dienst sendet im Sendetakt =
  Echtzeit).
* **v11:** **Themen-Überblick** statt Zeitvorgabe (`themen` statt `laenge`) — je Thema
  Presse (Google News), Wikipedia, Netzseite (gelesen) und passende Feeds;
  **Feeds 6 → 21**; Sprechfilter-Fehler behoben („Info" aus „Informatik" wurde
  gelöscht); Stufe-0-Befehle „überblick <themen>" und „themen: …".
* **v12:** **Eigene Suchmaschine** — SearXNG in LXC 108 (`192.168.178.26:8888`,
  uWSGI + redis, `limiter: false`, Formate html+json), angebunden über
  `RECHERCHE_SEARX_URL`; dazu Überblick-Korrekturen (Plätze je Thema 4 → 6,
  Wikipedia über die Such-Schnittstelle, Seitenleser filtert Bedienhilfen). Neue
  Werkzeuge: `bot-ausfuehrung.js`, `hol-testerschluessel.js`.

#### 3.4 21./22. September — die Oberfläche als Anleitung (v13–v18)

Die n8n-Oberfläche wurde zum **selbsterklärenden Dokument** ausgebaut:

* **v13:** Anordnung wiederhergestellt (7 Knoten lagen außerhalb ihrer Rahmen),
  bebilderte Anleitung `ANHANG/n8n-oberflaeche.html` (23 Bilder). Betriebsregel:
  in der Oberfläche nur ansehen, nicht ziehen.
* **v14:** Archiv „Radio – AI-Moderator" aufgeräumt: sechs Rahmen, Notiz an **jedem**
  der 19 Knoten (`archiv-rahmen.py`).
* **v15:** Dokumentations-Notiz an allen fünf geführten Abläufen, Altfassung-Notiz an
  den 13 alten Abläufen.
* **v16:** `bildplan.py` + `bilder-zuschnitt.py` — 95 Aufnahmen bei Maßstab 0,7–1,4
  (vorher 0,45–0,9), Beschriftungen lesbar.
* **v17:** Modulbilder je Ablauf (`modulbilder-plan.py`, `bilder-stitch.py`),
  anklickbar mit Zoom (reines JavaScript). Gesamtbild des Agenten 2525×1706 Punkte.
* **v18:** Sechs Ursachen der misslungenen Bilder gefunden und behoben (Maßstab über
  die Zoomknöpfe statt `zoom-to-fit`, helles Bild erzwungen, Bedienelemente
  ausgeblendet, Aufnahmefläche gemessen statt angenommen, Modulausschnitt =
  Vereinigung von Rahmen und Knoten, Aufnahme erst nach Stillstand).

#### 3.5 22. September — Vorlage und Zentrale

* **Zentrale Konfiguration:** neuer Ablauf `Konfiguration` mit **allen** Adressen,
  Schlüsseln, Modellwerten und Modelltexten (3 Systemanweisungen, 8
  Werkzeugbeschreibungen). Die vier Abläufe holen sie über einen
  Sub-Workflow-Knoten. Prüfwerkzeuge: `konfiguration-pruefen.py` (5 Prüfungen),
  `konfiguration-einspielen.sh`; Vorlagenmodus `VORLAGE=1` erzeugt eine frische
  Installation ohne private Werte (`NACHBAU/vorlage.md`).
* **Gemessene n8n-Regel** (beim Umbau entdeckt): `{{ … }}` mitten in einer
  Zeichenkette wird **nicht** aufgelöst — es muss `={{ … + '/pfad' }}` sein.

#### 3.6 23. September — Spracherkennung auf die MI50

Die Sprach­erkennung der Sprachnachrichten wurde von der 3090 Ti auf die bisher
ungenutzte **AMD Instinct MI50** verlegt: neuer Container **112 „whisper-amd"**
(`192.168.178.188:8000`) mit **whisper.cpp + Vulkan** (large-v3). Gemessen:
~**1,3 s je Sprachnachricht**. Der alte Dienst (`whisper-stt`, LXC 105, Port 18790)
blieb zunächst als Ersatzweg stehen. Die Adresse liegt seitdem in der zentralen
`Konfiguration` (`sprache.adresse`) — die Abläufe fragen sie von dort ab.

#### 3.7 23. September — die eigene Stimme (v19) und ihr Abend

Der große Tag: Aus dem eigenen Medienbestand entstand die **Ansagestimme „DEINE-STIMME"** —
Rohmaterial trennen (Demucs + ECAPA-Cluster), Referenz von mir bestätigen
lassen, reine Stücke sammeln, RVC-Modell `<dein-modell>` trainieren, Sprechdienst bauen.
Die **vollständige Geschichte** steht in `STIMME.md`, die **allgemeine Anleitung
zum Nachbauen für jede Serie** in `STIMME.md`.

* **v19** `radio-v19-2026-09-23-eigene-stimme`: `radio-tts` kennt die Stimme `deine-stimme`
  (externer Dienst auf CT 111, Port 10205), damalige Vorgabe `TTS_DEFAULT_VOICE=deine-stimme`
  (seit 2026-09-25 ist `de_thorsten` die Vorgabe — DEINE-STIMME auf Wunsch, siehe 3.9),
  Ersatzweg `EIGENE_STIMME_ERSATZ=de_thorsten` mit Kopfzeile `X-Stimme-Ersatz: 1`.
  **Kein n8n-Ablauf musste geändert werden** — die Abläufe übergeben keine feste
  Stimme, die Dienstvorgabe greift überall (Live-Ansage, Meldungen, Überblick,
  Trockenläufe).
* **Am selben Abend — der GPU-Vorfall:** Die ersten echten Ansagen klangen männlich,
  weil die GPU voll war (Ollama 18,7 GB direkt vor jeder Ansage + alter `whisper-stt`
  1,8 GB + HA-Whisper 1,8 GB + ComfyUI + DEINE-STIMME) — RVC brach mit `CUDA out of memory`
  ab (HTTP 500), `radio-tts` nahm den Ersatzweg. **Behoben:** `whisper-stt` gestoppt
  und auf Handbetrieb gestellt (1,76 GB frei), DEINE-STIMME gibt nach jeder Ansage den
  CUDA-Zwischenspeicher zurück, `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`.
  Reserve seitdem ~2,6 GB. (Details: `BETRIEB.md` §7.)
* **Und meine Stimmenwahl**, per Hörproben: Tonhöhe **+4**, Tempo
  **+40 %** (statt der zwischenzeitlichen Klarheitsfassung +20 %), `index_rate`
  **0,65** (Mischung aus Basisstimme und Trainingsmaterial) — das ist das feste
  Klangbild der eigenen Stimme (seit 25.09. auf Wunsch), ~**1050 Zeichen je Minute**.

#### 3.8 24./25. September — Anzeige, Doku und der zweisprachige Bot (v20–v21)

* **v20** `radio-v20-2026-09-24-deutsche-beschriftung`: Umlaute in allen Anzeigefeldern
  (Knoten, Notizen, Zettel), Werkzeug `deutsch-texte.py`; Zettelhöhen wachsen mit der
  Zeilenzahl (`dokunotiz`, `44 + 32·n`).
* **Doku-Umbau:** aus zwölf Büchern wurden vier Bände (`HANDBUCH`, `BETRIEB`, `BAU`,
  `STIMME`); die Erzeuger-Kopien liegen in `NACHBAU/`.
* **v21** `radio-v21-2026-09-25-zweisprachig`: Der Bot versteht **deutsch und englisch**
  in einem Chat. Neu: `sprache_raten` am Eingang, englische Kurzbefehle der Stufe 0,
  Werkzeugantworten in der Sprache des Betreibers (`sprache`-Feld), verstärkte
  Sprachregel im Ausführungs-Prompt. **Zwei Fehler gefunden und behoben:** „was läuft"
  fragte die falsche Sender-Kennung ab (jetzt `senderId` aus der Konfiguration),
  und englische Ansagen wurden deutsch bestätigt
  (die Bestätigung folgt jetzt der Sprache). Prüfungen: Status/Wunsch/Liste/Auswahl/
  Postfach/Ansage/Sprachnachricht je Sprache, 13 Beispiele grün.
  Rückweg: `radio-v21-vor-zweisprachig-2026-09-25`.
* **n8n-Ordner und -Tags:** die Abläufe liegen im Ordner `Deadline Beats`
  (6 Abläufe), derselbe Name als Schlagwort. Die Zuordnung setzt das Einspielskript
  (`n8n-ordner-setzen.sh`) — `n8n import:workflow` übernimmt keine Ordner.

#### 3.9 25. September (abends) — Stimmenwahl und der zweite GPU-Vorfall (v28)

* **v28** `radio-v28-2026-09-25-stimmenwahl`: **Standardstimme ist wieder
  `de_thorsten`** (Piper, läuft immer); die **eigene Stimme auf ausdrücklichen Wunsch**
  („… mit eigener Stimme"). Die Werkzeuge („Werkzeug Meldungen", „Werkzeug Recherche")
  haben dafür ein Feld **`stimme`**; es wird an `/ansage/text`, `/ansage/meldung` und
  `POST /recherche` durchgereicht (`dienst/suche.py`). Der Zusatz „mit eigener Stimme"
  gehört nur ins Feld und wird **nicht vorgelesen**. Der Dienst schreibt je Ansage
  eine Zeile **`Stimme: <name>`** ins Protokoll.
* **Der GPU-Vorfall (zweiter):** `sprechdienst` antwortete mit **HTTP 500
  (`torch.OutOfMemoryError`)** — die Karte war bis auf 59–179 MB belegt (Ollama
  18,3 GB + Reste); `radio-tts` nahm den Ersatzweg. **Behoben in `sprechdienst.py`
  (Quelle `NACHBAU/eigene-stimme/`):** vor und nach jeder Wandlung wird der
  CUDA-Zwischenspeicher freigegeben, ein Speicherfehler wird **einmal wiederholt**
  (2 s Pause). Nach CT 111 ausgerollt, drei Proben grün (HTTP 200, 1,5–2,0 s).

---

### 4. Was jede Schicht macht (Kurzüberblick)

| Schicht | Was | Wo | Details |
| --- | --- | --- | --- |
| Auslöser & Abläufe | Telegram-Eingang, Stufen 0–3, Werkzeuge | n8n, LXC 103 | `HANDBUCH.md` |
| Zentrale Werte | Adressen, Schlüssel, Modelltexte | Ablauf `Konfiguration` | `NACHBAU/vorlage.md` |
| Sprachausgabe & mehr | Sprache, Ansagen, Katalog, Listen, Postfach, Recherche | `radio-tts`, LXC 103, :8881 | `HANDBUCH.md` |
| Sender | Icecast + Liquidsoap/AutoDJ, 56.635 Titel, Wunschpool | AzuraCast, LXC 106 (.163) | `BETRIEB.md` |
| Sprachmodell | Planen, Ausführen, Prüfen | Ollama, LXC 105 | `HANDBUCH.md` §4.4 |
| Spracherkennung | Sprachnachrichten → Text | whisper-amd, LXC 112 (MI50) | `HANDBUCH.md` §3 |
| Eigene Stimme | Ansagen mit Standardstimme (`de_thorsten`) oder „DEINE-STIMME" auf Wunsch | sprechdienst, CT 111, :10205 | `STIMME.md` |
| Eigene Suche | Netz für Überblicke | SearXNG, LXC 108 | `NACHBAU/searxng-einrichten.md` |

---

### 5. Gemessene Meilensteine

| Datum | Meilenstein | Wert |
| --- | --- | --- |
| 20.09. | Wunsch über die KI-Kette (vorher) | 163 s |
| 20.09. | Wunsch über Stufe 0 (nachher) | **1,7 s** |
| 20.09. | Listen-Schritt über den Dienst | 0,2–0,7 s |
| 20.09. | Moderation auf Sendelautstärke | −11,8 LUFS auf Sendung |
| 21.09. | Beispiel-Überblick „themen: raumfahrt" | 1,3 Min Beitrag |
| 21.09. | Feeds des Überblicks | 21 Quellen |
| 23.09. | Spracherkennung (MI50) | ~1,3 s je Nachricht |
| 23.09. | DEINE-STIMME-Datensatz | 280 Stücke / 10:44 Min |
| 23.09. | Training `<dein-modell>` | 400 Epochen / 15.600 Schritte, ~1 h |
| 23.09. | DEINE-STIMME-Ansage (warm) | 1,4–3,8 s je Satz (erste ~9 s) |
| 23.09. | Sprechtempo der Stimme | ~1050 Zeichen/Minute (+40 %) |
| 23.09. | Ansageweg des Bots (gleicher Satz) | 5,5 s → **4,7 s** nach Tempo-Umstellung |
| 23.09. | GPU-Reserve nach dem Vorfall | ~2,6 GB (vorher 39 MB) |

---

### 6. Entscheidungen und verworfene Wege

| Entscheidung | Warum |
| --- | --- |
| Sofortspielen über `files/batch do=immediate` + Warteschlange leeren | keine Vorprüfungen, kein „Queue is not empty"; der neueste Wunsch gewinnt |
| Backend-Steuerung `start`, nie `play` | unbekannte Aktionen antworten mit 200 und starten den Sendeteil neu |
| Werkzeuge spielen selbst (Modell sieht keine Pfade) | kleinere Modelle erfinden Pfade und kündigen nur an |
| Antworten gegen den echten Senderzustand prüfen | „belegt, nicht behauptet" |
| Eine Zentrale (`Konfiguration`) für alle Werte | kein Adress-Raten, eine Stelle zum Ändern |
| **Kein** n8n-Umbau für die Stimme | die Abläufe übergeben keine Stimme — Dienstvorgabe genügt |
| Wiedergabeliste 9 (Unterbrecher) aufgegeben | `once_per_x_minutes` blockierte 1 Minute; `files/batch` ist besser |
| XTTS v2 verworfen | Stimme kam ~3,4 Halbtöne zu tief heraus, klanglich unterlegen (`STIMME.md` §11) |
| Aussprache-Regeln („Rööhre") verworfen | auf meinen Zuruf: „verwerfe röhre" — Text wird normal gesprochen |
| Klarheitsfassung +20 % → zurück zu **+40 %** | meine Wahl am 23.09.: Dynamik geht vor |
| Eigenes Streamer-Konto `deine-stimme` für die Ansagen | der Sender zeigt beim Sprechen „DEINE-STIMME“ statt meines Namens; manueller DJ-Zugang bleibt eigenes Konto |
| `whisper-stt` (18790) stillgelegt | seit dem MI50-Umzug nicht mehr verdrahtet; machte GPU-Platz für die Stimme frei |
| Ein kompletter Ablauf-Neubau ist verboten | würde die Werkzeugnamen gegenüber dem Modell ändern |

---

### 7. Die Werkzeuge des Baus

Sie liegen in `werkzeuge/` (Entwicklung) — hier die wichtigsten:

| Werkzeug | Zweck |
| --- | --- |
| `agent-wf-bauen.py` | **erzeugt** alle vier Abläufe (Quelle der Wahrheit für Knoten, Texte, Code) |
| `agent-patchen.sh` | ersetzt einzelne Knoten im laufenden Ablauf; `--aufraeumen` legt die Zeichenfläche neu |
| `agent-einspielen-nur.sh` | importiert Abläufe und startet n8n neu |
| `anordnung-pruefen.py`, `anordnung-doku.sh` | prüft die Zeichenfläche (Ziel: 0 Befunde); schreibt `ANHANG/ANORDNUNG.md` |
| `code-pruefen.py` | prüft den JS-Code der Knoten |
| `kurz-test.sh`, `antwort-test.sh` | Stufe 0 (19 Sätze) und Antwortlogik (20 Proben) — direkt aus dem Erzeuger |
| `konfiguration-pruefen.py`, `konfiguration-einspielen.sh` | prüft und spielt die Zentrale ein (5 Prüfungen) |
| `fassung-sichern.sh` | legt eine Fassung an (Abläufe, Module, n8n-DB, Beschreibung) |
| `dienst-einspielen.sh` | rollt die Dienstmodule aus, baut neu, prüft sich selbst |
| `bot-test.sh`, `frage.sh`, `knopf.sh` | Probesuite und Einzelnachrichten über den Testeingang |
| `bot-letzte.js`, `bot-ausfuehrung.js`, `ausfuehrungen.sh` | Ausführungsprotokolle (Stufen, Befehle, Urteile, Knöpfe) |
| `meldungen/*`, `playlist/*` | Bereichsprüfungen (Postfach/Ansagen, Listenwege) |
| `bildplan.py`, `modulbilder-plan.py`, `bilder-zuschnitt.py`, `bilder-stitch.py`, `n8n-doku-bauen.py` | erzeugen die Bilder-Anleitung (`ANHANG/n8n-oberflaeche.html`) |
| `altfassungen-notieren.py`, `archiv-rahmen.py` | Notizen für Archiv und Altfassungen |
| **Stimme** (Werkstatt, `docs/projects/VoiceAssistent/` + `NACHBAU/eigene-stimme/`) | `einrichten-stimmen-dienst.sh`, `stimmen_dienst.py`, `cluster-proben.sh`, `deine-stimme_sammeln3/4/5.py`, `rvc-trainieren.sh`, `sprechdienst.py`, `tg-sprachnachricht.sh` |

---

### 8. Nachbauen

* `NACHBAU/README.md` — die vollständige Anleitung (Bausteine, Schritte 1–8,
  Prüfläufe, was anders sein darf).
* `NACHBAU/vorlage.md` — Vorlagenmodus (frische Installation ohne private Werte).
* `NACHBAU/eigene-stimme/` — die Stimme nachbauen (Skripte + Anleitung);
  **allgemein für jede Serie:** `STIMME.md`.
* `NACHBAU/zugangsdaten.md` — die Anleitung zu den Zugangswerten (diese Fassung
  enthält keine Werte).

---

### 9. Wo man was nachliest

| Frage | Datei |
| --- | --- |
| Was ist der Bot, wie bedient man ihn? | `README.md` |
| Was kann er (Beispiele, Messwerte, Grenzen)? | `HANDBUCH.md` |
| Wie arbeitet er (Stufen, Komponenten, Entscheidungen)? | `HANDBUCH.md` |
| Welche Adressen gibt es? | `HANDBUCH.md` |
| Betrieb: einspielen, überwachen, sichern | `BETRIEB.md` |
| Prüfläufe mit Aufruf und Erwartung | `BETRIEB.md` |
| Bekannte Störungen und Lösungen | `BETRIEB.md` |
| Alle Fassungen und was sie brachten | `BAU.md` |
| Wie die eigene Stimme entstand (Geschichte) | `STIMME.md` |
| Eine Stimme aus einer Serie klonen (Anleitung) | `STIMME.md` |
| Nachbau auf neuer Hardware | `NACHBAU/README.md` |
| Entwickler-Quellen, Fassungen, Werkzeuge | `<dokuordner>/` |
| Die Oberfläche im Bild | `ANHANG/n8n-oberflaeche.html` |

## Fassungen

Jede Änderung am laufenden Bot wird als **Fassung** gesichert: die vier Abläufe als
JSON, die Dienstmodule, der Dockerfile, die n8n-Datenbank und eine Beschreibung.
Ablage: `<projektordner>/sicherungen/radio-fassungen/<name>/`.

Anlegen: `bash werkzeuge/fassung-sichern.sh <name> [beschreibung.md]`

---

| Fassung | Inhalt | Wirkung für den Nutzer |
| --- | --- | --- |
| **v1** `radio-v1-2026-09-20` | Ausgangszustand (vier Abläufe, wie sie liefen) | Wünsche, Richtung, Status — über die KI-Kette, langsam |
| **v2** `…-vor-tempo` | Stand **vor** der Tempo-Änderung | Sicherungspunkt zum Zurückrollen (163 s je Ansage) |
| **v3** `…-mit-tempo` | `reasoning_effort: none`, Regelurteil statt Modell, Schnellweg für gesprochene Formulierungen, `OLLAMA_KEEP_ALIVE=30m` | Ansagen in **1,7 s** statt 163 s |
| **v4** `…-mit-listen` | Wiedergabelisten-Aufgaben über einen eigenen Dienstweg (0,2–0,7 s je Schritt) | „lege eine Playlist an", „spiele sie", „lösche sie" |
| **v5** `…-mit-meldungen` | Postfach, Moderations- und Sprechtexte, **Live-Ansage** über den DJ-Hafen, Telegram-Freigabe mit Knöpfen, 5-Minuten-Zeitplan, Werkzeug `meldungen` | Der Bot **spricht selbst** im Programm |
| **v6** `…-mit-recherche` | Modul `suche.py`: Wetter (Open-Meteo), Nachrichten-/RSS-Feeds, Wikipedia; `POST /recherche`; Auftragsart `recherche`; Werkzeug `recherche` | „suche nach dem Wetter für X", „lies die Nachrichten vor" — und **mehrere Aufgaben** in einer Nachricht |
| **v7** `…-auswahlliste` | Auswahllisten gehen nicht mehr verloren (leere Antworten ersetzen nichts), Rückfrage gilt nicht als Fehlschlag, Knöpfe aus der Liste, Postfachfragen in Stufe 0 | Ein Wunsch mit mehreren Treffern endet mit **Knöpfen** statt mit „keine Ausgabe" |
| **v8** `…-moderationslautstaerke` | Lautstärke-Kette: Hochpass, Verdichtung 3:1, Pegelregelung, Begrenzer mit Vorausschau | Moderation **~4 dB lauter**, im üblichen Verhältnis zur Musik |
| **v9** `…-oberflaeche` | Zeichenfläche des Ablaufs: berechnete Rahmen, Farben je Stufe, Beschriftung an **jedem** Knoten, Übersichtsnotiz, Prüf- und Doku-Werkzeuge | Der Ablauf erklärt sich beim Öffnen selbst (0 Befunde) |
| **v10** `radio-v10-2026-09-20-ueberblick-sammelbefehle` | Dienst: `art=ueberblick` in `POST /recherche` (mehrere Quellen, Länge in Minuten, `ANSAGE_MAX_ZEICHEN` 700 → 9000, neue Meldungsart `ueberblick` mit Vor-/Nachspann, Wetter über Open-Meteo); Ablauf: Stufe-0-Wort **„überblick"**, neuer Zweig `Ueberblick holen`/`Ueberblick Antwort`, **Sammelbefehle bis 10** (erster Titel sofort, weitere Titel eingereiht), kürzere Antworten bei vielen Aufgaben, Zeitabläufe der Ansageknoten auf 15 Minuten | Ein Wort genügt für einen **mehrminütigen** Nachrichtenüberblick aus wählbaren Quellen — und bis zu zehn Aufgaben in einer Nachricht, ohne dass ein Titelwunsch den anderen abschneidet. *(Die Sicherung in `fassungen/radio-v10-…/` ist der Stand **vor** dieser Änderung = Rückrollpunkt; der Stand danach steht in `NACHBAU/ablaeufe-laufend/` und `dienst/`.)* |
| **v11** `radio-v11-2026-09-21-themen-ueberblick` | Dienst: **Themen-Überblick** statt Zeitvorgabe (`themen` statt `laenge`), je Thema Presse-Schlagzeilen (Google News), Wikipedia-Hintergrund, Websuche samt Lesen der Seite und passende Feed-Meldungen; **Feeds 6 → 21**; normale Internetseiten über `RECHERCHE_WEBSEITEN` und Websuche (DDG/Bing, optional eigene SearXNG); Sprechfilter-Fehler behoben („Info“ aus „Informatik“ wurde gelöscht, Bildnachweise/Quellenverweise wurden vorgelesen). Ablauf: Stufe-0-Befehle **„überblick <themen>“** und **„themen: …“** | „überblick ki, raumfahrt“ → 1,5 Min Beitrag mit Schlagzeilen, Wikipedia-Hintergrund und Feed-Treffern; keine Minutenangabe mehr nötig. *(Sicherung = Stand **nach** der Änderung, also der laufende Zustand.)* |
| **v12** `radio-v12-2026-09-21-eigene-suchmaschine` | **Eigene Suchmaschine** in LXC 108 „SearXNG" (`http://192.168.178.26:8888`, Debian 12, 1 GB, uWSGI + redis, `limiter: false`, `formats: html+json`) und `RECHERCHE_SEARX_URL` im Dienst; Korrekturen im Themen-Überblick: Plätze je Thema **4 → 6** mit reserviertem Platz für Netz/Feed (die Presse verdrängte sie vorher — „Web 0"), Wikipedia-Titel über die Such-Schnittstelle („künstliche intelligenz" fand nichts), Begriffsklärungen verworfen, Seitenleser filtert Bedienhilfen (`visually-hidden`/`aria-hidden`, `<svg><title>`) und Marken im Titel. Neue Werkzeuge: `bot-ausfuehrung.js`, `hol-testerschluessel.js` | Zu jedem Thema kommt jetzt eine **gelesene Netzseite** dazu (live: „themen: raumfahrt" → 1,3 Min, 3 Schlagzeilen, Hintergrund, **1 aus dem Netz**), und der Sprechtext ist sauber (kein „Pfeil rechts", keine Marken). Einrichtung zum Nachbauen: `NACHBAU/searxng-einrichten.md` |
| **v13** `radio-v13-2026-09-21-anordnung-aufgeraeumt` | **Anordnung der Zeichenfläche** aus dem Plan wiederhergestellt (`agent-patchen.sh --aufraeumen` legt **alle** Positionen und Rahmen neu, verwaiste Haftnotizen fallen weg): im Agenten lagen 7 Knoten der Stufe 0/1 außerhalb ihres Rahmens, ein Rahmen war leer, zwei überlappten sich. **Neu:** bebilderte Dokumentation `ANHANG/n8n-oberflaeche.html` (23 Bilder, eingebettet, erzeugt von `werkzeuge/n8n-doku-bauen.py`) | Die Oberfläche erklärt sich wieder von selbst — jeder Knoten liegt in seinem Rahmen (`anordnung-pruefen.py`: **0 Befunde**) — und es gibt eine Anleitung „Teil für Teil mit Bild". Betriebsregel: in der Oberfläche nur ansehen, nicht ziehen (siehe `BETRIEB.md` §22) |
| **v14** `radio-v14-2026-09-21-archiv-aufgeraeumt` | **Archiv „Radio - AI-Moderator“ eingerichtet:** sechs Rahmen (Eingänge, Kontext, Text und Stimme, Ausgabe, Nachverfolgung, Alte Hilfsmittel) und eine Notiz an **jedem** der 19 Knoten — angelegt mit dem neuen `werkzeuge/archiv-rahmen.py` (rechnet die Bereiche aus den Knotenpositionen, additiv: keine Logik geändert); `anordnung-doku.sh` nimmt das Archiv jetzt mit in `ANHANG/ANORDNUNG.md` | Auch das Archivfenster erklärt sich selbst (19/19 Knoten mit Notiz, **0 Befunde**) — die UI ist damit vollständig aufgeräumt |
| **v15** `radio-v15-2026-09-21-notizen-und-doku-in-der-ui` | **Notizen und Dokumentation in der Oberfläche** für **alle** Radio-Abläufe: die fünf geführten Abläufe bekommen eine **Dokumentations-Notiz** (was der Ablauf ist, wer ihn aufruft, wie man ihn ändert und prüft, welche Dateien ihn beschreiben) — beim Agenten und den drei Werkzeugen aus dem Bauwerkzeug (`dokunotiz()` in `agent-wf-bauen.py`), beim Archiv aus `archiv-rahmen.py`. Die **13 alten Abläufe** (Wunschbot, Kopien, einzelne Werkzeug-Abläufe, Sicherungen) erhalten je eine **Altfassung-Notiz** über `werkzeuge/altfassungen-notieren.py`. Neue Anleitung: Abschnitt 19 in `ANHANG/n8n-oberflaeche.html` | Beim Öffnen eines beliebigen Radio-Ablaufs steht sofort da, was er ist — auch bei den alten Fassungen; nichts ist mehr ein Rätsel. Alle Abläufe bleiben unverändert in Betrieb (Prüfung: 0 Befunde, 0 fehlerhafte Code-Knoten) |
| **v16** `radio-v16-2026-09-21-doku-ausschnitte` | **Bilder-Anleitung lesbar gemacht.** Neue Werkzeuge `werkzeuge/bildplan.py` (rechnet je Ablauf Ausschnitte von 1–4 Knoten samt Blickpunkt und Maßstab) und `bilder-zuschnitt.py` (schneidet den leeren Rand weg). **95 Aufnahmen bei Maßstab 0,7–1,4** statt 0,45–0,9; `ANHANG/n8n-oberflaeche.html` neu aufgebaut: Kapitel je Ablauf, Abschnitte je Bereich, je Bild eine Beschriftung mit den Knotennamen; alte Bilder lagen in `ANHANG/bilder/alt/` — gelöscht (Aufräumung 24.09.2026) | In der Anleitung sind die Beschriftungen **lesbar** (etwa 18–20 px statt 6 px im Bild) — man sieht jetzt, was auf der Fläche steht |
| **v17** `radio-v17-2026-09-22-modulbilder-zoom` | **Anleitung in Modulbildern.** `werkzeuge/modulbilder-plan.py` (Gesamtbild je Ablauf + ein Bild je Modul, Maßstab so, dass ein Modul in höchstens sechs Kacheln passt) und `werkzeuge/bilder-stitch.py` (setzt Kacheln pixelgenau zusammen — die Transformationswerte stehen im Dateinamen). Wichtig gemessen: das eingebettete Browserfenster ist **1417×895**, die Malfläche **1375×797**. `ANHANG/n8n-oberflaeche.html` neu: je Ablauf Gesamtbild, Modulverzeichnis, je Modul **Erklärung + Bild + Knotenliste** — und **jedes Bild ist anklickbar**: Zoom-Ansicht mit Mausrad, Knöpfen und Ziehen (reines JavaScript) | Ein Bild je Modul mit den Abschnittserklärungen darunter; wer mehr sehen will, klickt das Bild und zoomt. Gesamtbild des Agenten: 2525×1706 Punkte |
| **v18** `radio-v18-2026-09-22-bilder-korrekt` | **Bilder der Anleitung in Ordnung gebracht.** Sechs Ursachen gefunden und behoben: (1) **Maßstab** wird jetzt mit den Zoomknöpfen gesetzt und nachgemessen (×1,2 bzw. ÷1,2) statt über `zoom-to-fit` — der Knopf greift nicht immer, dann blieb der Maßstab 1,0 und die Gesamtbilder wurden aus dem falschen Abstand aufgenommen (dunkle Fläche mit verschobenen Streifen); (2) **helles Bild erzwungen** (`emulateMedia colorScheme light`) — n8n folgt der Systemeinstellung, die neuen Aufnahmen waren dunkel, die Rahmenfarben kaum zu sehen; (3) **Bedienelemente ausgeblendet** (Zoomknöpfe, Minimap, „Execute workflow“, Knoten-Werkzeugleisten) und die Maus aus der Fläche gefahren — vorher lagen sie in jeder Kachel; (4) **Aufnahmefläche gemessen** statt angenommen: `[data-test-id="canvas"]` = **1613×840 ab (42,65)** (Fenster ≈ 1655×938), vorher mit 1417×895/1375×797 gerechnet; (5) **Modulausschnitt = Vereinigung von Rahmen und allen darin liegenden Knoten** (`modulbilder-plan.py`) — vorher schnitt der Rahmen Knoten mit ihren Notizen an; (6) **Aufnahme erst nach Stillstand** (Transform zweimal gleich + 0,7 s; Verschieben über `WheelEvent`, gemessen `Δtx = −0,5·deltaX`) — vorher verschob die laufende Bewegung Kacheln um einige Pixel. Außerdem: der Kachelordner wird vor jeder Aufnahme geleert (alte Kacheln mischten sich sonst ins Bild) und `bilder-stitch.py` kann leere Ränder anschneiden (`--ohne-zuschnitt` schaltet es ab). Aufnahmevorschrift steht in `ANHANG/README.md` | Die Anleitung zeigt jetzt helle, vollständige Bilder: **kein Werkzeugkasten im Bild, kein angeschnittener Knoten, lesbare Schrift**, alle 35 Module und 5 Gesamtbilder aus einem Durchlauf. Nötig war dafür nichts vom Nutzer — die Ursachen lagen alle in der Aufnahme |
| **v19** `radio-v19-2026-09-23-eigene-stimme` | Dienst: **eigene Moderationsstimme „DEINE-STIMME"** als wählbare, externe Stimme (`main.py`: `ist_eigene_stimme`/`erzeuge_audio_eigene`/`erzeuge_audio_gewaehlt`); **Ersatzweg** `EIGENE_STIMME_ERSATZ` (Standard `de_thorsten`) samt Protokollzeile und Kopfzeile `X-Stimme-Ersatz: 1`; `/health` mit `deine-stimme`-Block; `/v1/audio/voices` listet `deine-stimme`; Zeitablauf `EIGENE_STIMME_ZEITABLAUF=600 s` (Erzeugung ~1,6× Echtzeit, gemessen); `meldungen.py`-Trockenlauf nutzt dieselbe Stimmenwahl; `docker-compose.yml`: `TTS_DEFAULT_VOICE=deine-stimme`, `EIGENE_STIMME_URL`, `EIGENE_STIMME_ERSATZ`. **Kein Ablauf geändert** (die Abläufe übergeben keine feste Stimme). Herkunft/Nachbau: `STIMME.md`, `NACHBAU/eigene-stimme/` | Alle Ansagen des Bots (Live, Meldungen, Überblick) sprechen mit der **eigenen Stimme**; fällt der Stimmendienst aus (GPU-Maschine), spricht der Bot ersatzweise mit `de_thorsten` weiter — keine Ansage fällt aus. Piper-Stimmen bleiben über `voice`/`stimme` wählbar. *(Sicherung = Stand nach der Änderung; Rückweg in `fassungen/radio-v19-…/README.md`)* **Nachtrag 23.09.:** Die Ansagen laufen im Sender über ein **eigenes Streamer-Konto `deine-stimme`** (Anzeigename „DEINE-STIMME“) — beim Sprechen erscheint „DEINE-STIMME“ statt des Betreibernamens (`LIVE_USER` in `geheim.env`; Betreiberzugang `betreiber` bleibt getrennt). |
| **v20** `radio-v20-2026-09-24-deutsche-beschriftung` | **Oberfläche in richtiger Schreibweise und mit sauber gefassten Rahmen.** Neues Werkzeug `werkzeuge/deutsch-texte.py` ersetzt in **allen sieben Abläufen** die ASCII-Schreibweise der sichtbaren Texte durch Umlaute („Prüfung", „läuft", „Überblick") — nur Haftnotizen, Knotenbeschriftungen und Untertitel; Datei- und Befehlsnamen bleiben unangetastet (`n8n-oberflaeche.html`, `--aufraeumen`, `anordnung-pruefen.py` sind geschützt, nachgemessen). Knoten mit Namensänderung werden samt Verweisen (Verbindungen, `$('…')`) umgezogen (15 Umbenennungen im Agenten). **Rahmen des Archivs neu gefasst:** die Knoten stehen wieder auf gleichmäßigen Spaltenabständen und alle sieben Rahmen sind aus den im Browser gemessenen Knotenmaßen gerechnet — kein Knoten oder Untertitel ragt mehr heraus (Randabstände 16–40 px, im Browser nachgemessen), die Notiztexte überdecken keine Knoten mehr. **Doku-Notizen:** `dokunotiz()` rechnet jetzt mit der echten Zeilenhöhe (`44 + 32·n`) — die Konfigurations-Notiz war unten abgeschnitten. **Bauweg:** Token und Schnittstellenschlüssel kommen jetzt aus dem Ablauf „Konfiguration – alle Werte" (dort liegen sie seit dem 22.09.), `agent-patchen.sh`/`agent-patchen.py` lesen sie aus beiden Dateien; `agent-einspielen-nur.sh` spielt den Konfigurations-Ablauf mit ein. **Bilder:** alle 86 Kacheln neu aufgenommen (40 Module + 7 Übersichten), `ANHANG/n8n-oberflaeche.html` neu gebaut (4,42 MB); die vorherigen Kacheln lagen in `ANHANG/bilder/kacheln-2026-09-24-v1/` — gelöscht (Aufräumung 24.09.2026); Kacheln und Modulbilder dieser Fassung wurden nach dem Bau ebenfalls gelöscht (es bleiben `modulplan.json`, `startmassstaebe.json` und die sieben Gesamtbilder) | Die Anleitung zeigt jetzt **lesbare deutsche Beschriftungen** (ä/ö/ü überall), und im Archiv-Ablauf liegen alle Knoten samt Beschriftung sauber in ihrem Rahmen — nichts verdeckt mehr die Schrift. Im Betrieb ist nichts umgestellt: derselbe Bot, dieselben Wege, nur die Oberfläche und ihre Bilder sind korrigiert. *(Sicherung = Stand vor der Änderung, inkl. Datenbank; Rückweg in `fassungen/radio-v20-…/README.md`)* **Nachtrag 24.09.:** **englische Fassung** angelegt unter `EN/` — dieselbe Anleitung samt aller Dokumente übersetzt, die sieben Abläufe als englische Kopien (Kennungen `…EN`, nur Anzeigetexte übersetzt, nicht im Betrieb) und englisch aufgenommene Bilder; die Werkzeuge dafür liegen in `EN/werkzeuge/`. |

---

### Was eine Fassung enthält

```
fassungen/radio-v9-2026-09-20-oberflaeche/
  README.md            Beschreibung dieser Fassung
  ablaeufe/            RadioAgentBot.json, RadioWerkzeug.json, AzuraWerkzeug.json,
                       MeldungenWerkzeug.json, bjFSfXGqpLg7AAXw.json
  dienste/             main.py, katalog.py, playlist.py, meldungen.py, suche.py,
                       whisper_server.py, Dockerfile, docker-compose.yml
  bau/                 die Zwischenstände des Baus (Erzeuger-Ausgaben)
  n8n-daten.sqlite.gz  vollständige n8n-Datenbank (letzter Ausweg)
  ARCHITEKTUR-der-Doku.md, README-der-Doku.md    die Projektdokumentation zum Stand
```

Rechte: Verzeichnisse 700, Dateien 600 (die Abläufe enthalten Kennungen).

---

### Zurückrollen

```bash
cd ../../werkzeuge
bash agent-einspielen-nur.sh ../fassungen/radio-v7-2026-09-20-auswahlliste/ablaeufe/RadioAgentBot.json
## Dienstmodule aus der Fassung neu ausrollen
cp ../fassungen/<fassung>/dienste/*.py ../dienst/ && bash dienst-einspielen.sh
```

Die n8n-Datenbank (`n8n-daten.sqlite.gz`) nur im Notfall einspielen: n8n stoppen,
Datei entpacken, ersetzen, n8n starten.

---

### Nicht mehr vorhandene Zwischenstände

Die Abläufe `RadioTelegramBot`, `RadioWerkzeugSuche` und die alte
Eingangsweiche sind **archiviert** bzw. ersetzt — sie liegen nicht mehr aktiv in n8n.
Der Ablauf `bjFSfXGqpLg7AAXw` (der frühere KI-Moderator) existiert noch, wird aber
nicht benutzt; er wird bei jeder Sicherung mitgenommen.
