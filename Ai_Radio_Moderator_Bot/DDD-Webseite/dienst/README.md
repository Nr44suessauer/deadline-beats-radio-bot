# Catalogue service (`ddd-radio`) — sources and operation

> **In this edition** the service runs as container `ddd-radio` on **port 8882**
> (station 2, “DDD-Webseite Demo”); its source lives here in
> `DDD-Webseite/dienst/`. The main bot keeps using `radio-tts` on port 8881 —
> the same code.

The container does five jobs: speech output (Piper plus the dedicated
moderation voice), the **catalogue** for fuzzy search and mood suggestions, the
**playlist tasks** (build, manage and play playlists in the station), the
**news mailbox** (accept items from outside and speak them as the moderator),
and **research** (weather, news, feeds, short infos on demand, **topic
overview**). Everything is kept here as source so it does not exist only on
the server.

```
dienst/
├── app/
│   ├── main.py         # FastAPI: speech output, live announcement, wiring of the modules
│   ├── katalog.py      # catalogue: /suche, /genre, /genre/liste, /katalog/*
│   ├── playlist.py     # playlist tasks: /playlist/befehl, /playlist/knopf, /playlist/vorschlag
│   ├── meldungen.py    # mailbox and announcements: /meldungen/*, /ansage/*
│   └── suche.py        # research: /recherche (weather, news, RSS, Wikipedia)
├── Dockerfile          # python:3.12-slim + piper-tts + fastapi + lameenc
└── docker-compose.yml  # port 8882 (host) -> 8881 (container), volumes ./voices and ./daten
```

**Attention when building:** the Dockerfile must copy **every** module
(`COPY app/meldungen.py /app/meldungen.py` …) — otherwise the service reports
`No module named 'meldungen'` and those endpoints are missing.
Deploy and check: `bash ../werkzeuge/dienst-einspielen.sh`, then
`curl -s http://192.168.178.53:8882/health` and `/meldungen/status`.

## Setup on the server

```bash
# copy the sources over (example: katalog.py) — or run ../werkzeuge/dienst-einspielen.sh
cat dienst/app/katalog.py | ssh <your-host> "pct exec 103 -- bash -c 'cat > /opt/ddd-radio/app/katalog.py'"
# build and start
ssh <your-host> "pct exec 103 -- bash -lc 'cd /opt/ddd-radio && docker compose build && docker compose up -d'"
# rebuild the catalogue (after new titles were added to the archive)
ssh <your-host> "pct exec 103 -- curl -s -X POST http://127.0.0.1:8882/katalog/aktualisieren"
```

## Access file `geheim.env` (600, not in Git)

Copy the shipped `geheim.env.vorlage` to `geheim.env` and fill in your values:

```
AZ_URL=http://192.168.178.33
AZ_KEY=<API key of this station>
AZ_STATION_ID=2
KATALOG_DIR=/daten
MELDUNG_SCHLUESSEL=<mailbox key>
LIVE_HOST=192.168.178.33
LIVE_PORT=8015
LIVE_MOUNT=/
LIVE_USER=<bot streamer account>
LIVE_PASSWORD=<its password>
LIVE_NAME=<display name on air>
TTS_HOCHPASS_HZ=50
TTS_KOMPRESSOR_SCHWELLE_DB=-18
TTS_KOMPRESSOR_VERHAELTNIS=2.0
TTS_ZIEL_RMS_DB=-12.5
```

`AZ_URL` points to the station (LXC 106 on `.163` in the reference setup).
`AZ_KEY` is the same key as `/var/azuracast/api_key.txt`. `KATALOG_DIR` is the
place of `katalog.json` inside the container (volume `./daten`). The `LIVE_*`
values are the DJ connection used for live announcements; the station shows
the streamer account `aqua` (display name “Aqua”). The `TTS_*` values are the
“variant 3” loudness chain.

## Catalogue endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /katalog/status` | number of tracks, date and duration of the last build |
| `POST /katalog/aktualisieren` | rebuild the catalogue from the station (≈ 47 s) |
| `GET /suche?q=&anzahl=&min_punkte=` | fuzzy search (typos, misheard speech) |
| `GET /genre?wort=&anzahl=&mischen=&nur_mit_playlist=` | suggestions by direction, mood, decade |
| `GET /genre/liste` | direction and helper words (the bot fetches them at build time) |
| `GET /katalog/kuenstler?anzahl=` | most frequent artists (hint text for speech recognition) |

## Playlist endpoints

| Endpoint | Purpose |
| --- | --- |
| `POST /playlist/befehl` | `{chatId, text}` — one sentence (“build a summer playlist from Scooter”) |
| `POST /playlist/knopf` | `{chatId, daten}` — button press (`p3`, `pa`, `pf`, `px`, `l1`, `j`, `n`, `v`) |
| `POST /playlist/vorschlag` | candidates for a search term |
| `GET /playlist/status` | open selections, station interface |

The state (open selection per chat) lives in the service’s memory; a restart
clears it.

## Mailbox endpoints

| Endpoint | Purpose |
| --- | --- |
| `POST /meldungen/neu` | drop off item(s) (search bot) |
| `GET /meldungen/offen` | open items (`nur_neue=1` = not yet presented) |
| `GET /meldungen/text/<id>` | preview of the spoken text |
| `POST /meldungen/angeboten` | mark as presented |
| `POST /meldungen/erledigt` | said / discarded / expired |
| `POST /ansage/meldung`, `POST /ansage/text` | speak live (`trocken: true` = generate only) |
| `GET /meldungen/status`, `GET /ansage/status` | check (no key needed) |

Everything except the two `status` addresses requires `X-Meldung-Schluessel`
(`/daten/meldung-schluessel.txt`, created on first start). The mailbox is
stored in `/daten/meldungen.json`; the spoken text is built from templates per
item type (weather, news, RSS, traffic, hint, music). For announcements the
service needs the DJ connection (`LIVE_*` in `geheim.env`) — set up like
described above.

## Research endpoint

| Endpoint | Purpose |
| --- | --- |
| `POST /recherche` | `{art, wort, themen, quellen, ansagen, wichtig, trocken, quelle}` — fetches weather/news/feed/short info/**topic overview**, stores an item and optionally speaks it |
| `GET /recherche/feeds` | the **21** sources, the types and the overview settings |

**Types:** `wetter`, `nachrichten`, `rss`, `wikipedia`, `ueberblick`.
The **topic overview** (`art=ueberblick`) takes `themen` (“ki, raumfahrt”) and
optional `quellen`; per topic it collects press headlines (Google News),
background (Wikipedia), web-search hits including the read page, and matching
feed items. There is **no** time parameter — the length follows the material
(`RECHERCHE_UEBERBLICK_MAX_ZEICHEN`, default 6000 ≈ 5.7 min). Without `themen`
the newest items of the chosen sources are used.

Sources (no key): Open-Meteo (weather), **21 RSS feeds** of German news and
specialist pages, Google News (press on the topic), Wikipedia, web search
(own SearXNG via `RECHERCHE_SEARX_URL`, else DuckDuckGo/Bing) and own pages
without feed via `RECHERCHE_WEBSEITEN`. It also needs `X-Meldung-Schluessel`
because it stores items and can speak.

## Catalogue file

`./daten/katalog.json` — per track the IDs (`id`, `uid`, `song`, `unique_id`,
`song_id`), artist, title, album, genre, length, path, playlists, year, plus
the computed fields `heu` (normalised search text), `kurz` (artist + title +
album), `kern` (artist + title only, basis of the core check), `woerter`,
`kern_woerter` and the letter bit masks `maske`/`maske_all`. About 44 MB,
build ≈ 47 s, container memory ≈ 215 MB.

After new titles were added to the archive, **rebuild** it — otherwise the
fuzzy search cannot find them.
