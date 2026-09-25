# Katalogdienst (`radio-tts`) — Quellen und Betrieb

Der Container `radio-tts` macht fünf Dinge: deutsche Sprachausgabe (Piper, für den Moderator),
den **Katalogdienst** für unscharfe Suche und Richtungsvorschläge, die **Listenaufgaben**
(Wiedergabelisten im Sender bauen, verwalten, abspielen), das **Meldungspostfach**
(Meldungen von außen entgegennehmen und als Moderator in den Sender sprechen) und die
**Recherche** (Wetter, Nachrichten, Feeds, Kurzinfos auf Zuruf, **Themen-Überblick**).
Alles liegt hier auch als Quelle, damit es nicht nur auf dem Server steht.

```
dienst/
├── main.py             # FastAPI: Sprachausgabe, Live-Ansage, Einbindung der Module
├── katalog.py          # Katalogdienst: /suche, /genre, /genre/liste, /katalog/*
├── playlist.py         # Listenaufgaben: /playlist/befehl, /playlist/knopf, /playlist/vorschlag
├── meldungen.py        # Postfach und Ansagen: /meldungen/*, /ansage/*
├── suche.py            # Recherche: /recherche (Wetter, Nachrichten, RSS, Wikipedia)
├── Dockerfile          # python:3.12-slim + piper-tts + fastapi + lameenc
└── docker-compose.yml  # Port 8881, Bände ./voices (Stimmen) und ./daten (Katalog, Postfach)
```

**Achtung beim Bauen:** der Dockerfile muss **jedes** Modul mitkopieren
(`COPY app/meldungen.py /app/meldungen.py` …) – sonst meldet der Dienst
`No module named 'meldungen'` und die Adressen fehlen.
Einspielen und prüfen: `bash ../werkzeuge/dienst-einspielen.sh`,
`bash ../werkzeuge/meldungen/19-meldungen-test.py`.

## Aufbau auf dem Server

```bash
CFG=~/.ssh/config
# Quellen hinüberbringen (Beispiel katalog.py)
cat dienst/katalog.py | ssh -F $CFG ai-server "pct exec 103 -- bash -c 'cat > /opt/radio-tts/app/katalog.py'"
# bauen und starten
ssh -F $CFG ai-server "pct exec 103 -- bash -lc 'cd /opt/radio-tts && docker compose build && docker compose up -d'"
# Katalog neu aufbauen (nach neuen Titeln im Archiv)
ssh -F $CFG ai-server "pct exec 103 -- curl -s -X POST http://127.0.0.1:8881/katalog/aktualisieren"
```

Prüfen: `bash ../werkzeuge/katalog-test.sh http://192.168.178.53:8881`

## Zugangsdatei `geheim.env` (600, nicht im Git)

```
AZ_URL=http://192.168.178.33
AZ_KEY=<Schnittstellenschlüssel des Senders>
KATALOG_DIR=/daten
```

`AZ_URL` zeigt auf den Sender (LXC 106 auf `.163`). `AZ_KEY` ist derselbe Schlüssel wie in
`/var/azuracast/api_key.txt`. `KATALOG_DIR` ist der Ablageort von `katalog.json` (Band `./daten`).

## Endpunkte des Katalogs

| Endpunkt | Zweck |
| --- | --- |
| `GET /katalog/status` | Anzahl, Stand, Dauer des letzten Aufbaus |
| `POST /katalog/aktualisieren` | Katalog neu aus dem Sender holen (≈ 47 s) |
| `GET /suche?q=&anzahl=&min_punkte=` | unscharfe Suche (Tippfehler, verhört Gesprochenes) |
| `GET /genre?wort=&anzahl=&mischen=&nur_mit_playlist=` | Vorschläge zu Richtung, Stimmung, Jahrzehnt |
| `GET /genre/liste` | Richtungs- und Hilfsworte (der Bot holt sie beim Bauen) |
| `GET /katalog/kuenstler?anzahl=` | häufigste Interpreten (Hinweistext für die Spracherkennung) |

## Endpunkte der Listenaufgaben

| Endpunkt | Zweck |
| --- | --- |
| `POST /playlist/befehl` | `{chatId, text}` — ein Satz („baue eine Playlist Sommer aus Scooter") |
| `POST /playlist/knopf` | `{chatId, daten}` — Knopfdruck (`p3`, `pa`, `pf`, `px`, `l1`, `j`, `n`, `v`) |
| `POST /playlist/vorschlag` | Kandidaten zu einem Suchbegriff |
| `GET /playlist/status` | offene Auswahlen, Senderschnittstelle |

Der Zustand (offene Auswahl je Chat) liegt im Arbeitsspeicher des Dienstes; ein Neustart
verwirft ihn. Ausführlich: `../README.md` §11.

## Endpunkte des Meldungspostfachs

| Endpunkt | Zweck |
| --- | --- |
| `POST /meldungen/neu` | Meldung(en) abgeben (Suchbot) |
| `GET /meldungen/offen` | offene Meldungen (`nur_neue=1` = noch nicht vorgelegt) |
| `GET /meldungen/text/<kennung>` | Vorschau des Sprechtextes |
| `POST /meldungen/angeboten` | als vorgelegt merken |
| `POST /meldungen/erledigt` | gesagt / verworfen / abgelaufen |
| `POST /ansage/meldung`, `POST /ansage/text` | live sprechen (`trocken: true` = nur erzeugen) |
| `GET /meldungen/status`, `GET /ansage/status` | Kontrolle (ohne Schlüssel) |

Alles außer den beiden Status-Adressen verlangt `X-Meldung-Schluessel`
(`/daten/meldung-schluessel.txt`, wird beim ersten Start erzeugt).
Das Postfach liegt in `/daten/meldungen.json`, der Sprechtext entsteht aus Vorlagen je
Meldungsart (Wetter, Nachrichten, RSS, Verkehr, Hinweis, Musik).
Für die Ansage braucht der Dienst den Ansage-Zugang (`LIVE_*` in `geheim.env`;
eigenes Bot-Konto `deine-stimme`, im Sender erscheint beim Sprechen „DEINE-STIMME“),
einzurichten mit `../werkzeuge/meldungen/18-live-zugang-setzen.sh`.
Ausführlich: `../werkzeuge/meldungen/README.md` und `../README.md` §12.

## Endpunkt der Recherche

| Endpunkt | Zweck |
| --- | --- |
| `POST /recherche` | `{art, wort, themen, quellen, ansagen, wichtig, trocken, quelle}` — holt Wetter/Nachrichten/Feed/Kurzinfo/**Themen-Überblick**, legt eine Meldung ab und sagt sie auf Wunsch an |
| `GET /recherche/feeds` | die **21** Quellen, die Arten und die Einstellungen des Überblicks |

**Arten:** `wetter`, `nachrichten`, `rss`, `wikipedia`, `ueberblick`.
Der **Themen-Überblick** (`art=ueberblick`) bekommt `themen` („ki, raumfahrt“) und optional
`quellen`; er sucht je Thema Presse-Schlagzeilen (Google News), Hintergrund (Wikipedia),
Treffer der Websuche samt gelesener Seite und passende Meldungen der Feeds. Eine
Zeitvorgabe gibt es **nicht** — die Länge folgt dem Material
(`RECHERCHE_UEBERBLICK_MAX_ZEICHEN`, Vorgabe 6000 ≈ 5,7 Min). Ohne `themen` kommen die
neuesten Meldungen der gewählten Quellen.

Quellen (ohne Schlüssel): Open-Meteo (Wetter), **21 RSS-Feeds** deutscher Nachrichten- und
Fachseiten, Google News (Presse zum Thema), Wikipedia, Websuche (eigene SearXNG über
`RECHERCHE_SEARX_URL`, sonst DuckDuckGo/Bing) und eigene Seiten ohne Feed über
`RECHERCHE_WEBSEITEN`. Braucht ebenfalls `X-Meldung-Schluessel`, weil es Meldungen anlegt
und sprechen kann.

## Katalogdatei

`./daten/katalog.json` — je Titel Kennungen (`id`, `uid`, `song`, `unique_id`, `song_id`),
Interpret, Titel, Album, Genre, Länge, Pfad, Wiedergabelisten, Jahr, dazu die Rechenfelder
`heu` (normalisierter Suchtext), `kurz` (Interpret + Titel + Album), `kern` (nur Interpret +
Titel, Grundlage der Kernprüfung), `woerter`, `kern_woerter` und die Buchstaben-Bitmuster
`maske`/`maske_all`. Etwa 44 MB, Aufbau ≈ 47 s, Speicherbedarf des Containers ≈ 215 MB.

Nach neuen Titeln im Archiv **neu aufbauen**, sonst findet die unscharfe Suche sie nicht.
