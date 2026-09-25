# Catalog Service (`radio-tts`) — Sources and Operation

The container `radio-tts` performs five tasks: German speech output (Piper, for the moderator),
the **Catalog Service** for fuzzy search and direction suggestions, the **Playlist Tasks**
(building, managing, and playing playlists in the station), the **Message Inbox**
(receiving messages from outside and speaking them as a moderator in the station), and
**Research** (weather, news, feeds, quick info on demand, **Topic Overview**).
Everything is also available here as a source, so it is not only on the server.

```
dienst/
├── main.py             # FastAPI: voice output, live announcement, module wiring
├── katalog.py          # Katalogdienst: /suche, /genre, /genre/liste, /katalog/*
├── playlist.py         # Listenaufgaben: /playlist/befehl, /playlist/knopf, /playlist/vorschlag
├── meldungen.py        # inbox and announcements: /news/*, /announce/*
├── suche.py            # Recherche: /recherche (Wetter, Nachrichten, RSS, Wikipedia)
├── Dockerfile          # python:3.12-slim + piper-tts + fastapi + lameenc
└── docker-compose.yml  # port 8881, volumes ./voices (voices) and ./daten (catalog, inbox)
```

**Attention when building:** the Dockerfile must **copy every** module (`COPY app/meldungen.py /app/meldungen.py` …) – otherwise the service
`No module named 'meldungen'` will report missing addresses.
Deployment and verification: `bash ../werkzeuge/dienst-einspielen.sh`,
`bash ../werkzeuge/meldungen/19-meldungen-test.py`.

## Server Setup

```bash
CFG=~/.ssh/config
# copy the sources over (example katalog.py)
cat dienst/katalog.py | ssh -F $CFG ai-server "pct exec 103 -- bash -c 'cat > /opt/radio-tts/app/katalog.py'"
# build and start
ssh -F $CFG ai-server "pct exec 103 -- bash -lc 'cd /opt/radio-tts && docker compose build && docker compose up -d'"
# rebuild the catalog (after new titles in the archive)
ssh -F $CFG ai-server "pct exec 103 -- curl -s -X POST http://127.0.0.1:8881/katalog/aktualisieren"
```

Check: `bash ../werkzeuge/katalog-test.sh http://192.168.178.53:8881`

## Access File `geheim.env` (600, not in Git)

```
AZ_URL=http://192.168.178.33
AZ_KEY=<station interface key>
KATALOG_DIR=/daten
```

`AZ_URL` points to the station (LXC 106 on `.163`). `AZ_KEY` is the same key as in
`/var/azuracast/api_key.txt`. `KATALOG_DIR` is the storage location for `katalog.json` (band `./daten`).

## Catalog Endpoints

| Endpoint | Purpose |

| --- | --- |

| `GET /katalog/status` | Number, status, duration of the last build |

| `POST /katalog/aktualisieren` | Retrieve the catalog from the station (≈ 47 s) |

| `GET /suche?q=&anzahl=&min_punkte=` | Fuzzy search (typos, misheard speech) |

| `GET /genre?wort=&anzahl=&mischen=&nur_mit_playlist=` | Suggestions for direction, mood, decade |

| `GET /genre/liste` | Direction and helper words (the bot fetches them during build) |

| `GET /katalog/kuenstler?anzahl=` | Most frequent interpreters (hint text for speech recognition) |

## Playlist Task Endpoints

| Endpoint | Purpose |

| --- | --- |

| `POST /playlist/befehl` | `{chatId, text}` — a sentence ("build a playlist Summer from Scooter") |

| `POST /playlist/knopf` | `{chatId, daten}` — button press (`p3`, `pa`, `pf`, `px`, `l1`, `j`, `n`, `v`) |

| `POST /playlist/vorschlag` | Candidates for a search term |

| `GET /playlist/status` | open selections, station interface |

The state (open selection per chat) is in the service's memory; a restart discards it.
Detailed: `../README.md` §11.

## Message Inbox Endpoints

| Endpoint | Purpose |

| --- | --- |

| `POST /meldungen/neu` | Submit message(s) (search bot) |

| `GET /meldungen/offen` | open messages (`nur_neue=1` = not yet presented) |

| `GET /meldungen/text/<kennung>` | preview of the speaking text |

| `POST /meldungen/angeboten` | mark as presented |

| `POST /meldungen/erledigt` | spoken / discarded / expired |

| `POST /ansage/meldung`, `POST /ansage/text` | speak live (`trocken: true` = only generate) |

| `GET /meldungen/status`, `GET /ansage/status` | control (without key) |

Everything except the two status addresses requires `X-Meldung-Schluessel`
(`/daten/meldung-schluessel.txt`, generated on the first start).
The inbox is located in `/daten/meldungen.json`, the speaking text is generated from templates per
message type (weather, news, RSS, traffic, notice, music).
For the announcement, the service needs the announcement access (`LIVE_*` in `geheim.env`;
own bot account `deine-stimme`, in the station appears as "YOUR-VOICE" when speaking),
configured with `../werkzeuge/meldungen/18-live-zugang-setzen.sh`.
Detailed: `../werkzeuge/meldungen/README.md` and `../README.md` §12.

## Research Endpoint

| Endpoint | Purpose |

| --- | --- |

| `POST /research` | `{art, wort, themen, quellen, ansagen, wichtig, trocken, quelle}` — fetches the **Topic Overview**, submits a message, and speaks it on request |

| `GET /recherche/feeds` | the **21** sources, the types, and the settings of the overview |

**Types:** `wetter`, `nachrichten`, `rss`, `wikipedia`, `ueberblick`.
The **Topic Overview** (`art=ueberblick`) receives `themen` ("ki, spaceflight") and optionally
`quellen`; it searches for press headlines (Google News), background (Wikipedia),
web search results with the read page, and matching feed messages. There is **no**
time limit — the length follows the material
(`RECHERCHE_UEBERBLICK_MAX_ZEICHEN`, default 6000 ≈ 5.7 min). Without `themen`, the
most recent messages from the selected sources are returned.

Sources (without keys): Open-Meteo (Weather), **21 RSS feeds** of German news and specialist sites, Google News (press coverage), Wikipedia, web search (own SearXNG via `RECHERCHE_SEARX_URL`, otherwise DuckDuckGo/Bing), and own pages without feed via `RECHERCHE_WEBSEITEN`. Also requires `X-Meldung-Schluessel` because it creates notifications and can speak.

## Catalog File

`./daten/katalog.json` — per title identifiers (`id`, `uid`, `song`, `unique_id`, `song_id`), performer, title, album, genre, length, path, playlists, year, plus the fields `heu` (normalized search text), `kurz` (performer + title + album), `kern` (only performer + title, basis for core verification), `woerter`, `kern_woerter` and the letter bit patterns `maske`/`maske_all`. Approximately 44 MB, build time ≈ 47 s, container memory requirement ≈ 215 MB.

Rebuild after new titles in the archive, otherwise the fuzzy search will not find them.