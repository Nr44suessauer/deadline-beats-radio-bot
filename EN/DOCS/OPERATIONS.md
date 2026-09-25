# Operation — Deploy, Troubleshooting, Testing

## Operations

**Date:** 2026-09-24.

All commands run on your own machine; the tools live in `tools/`,
the service modules in `service/`.

---

### 1. Where What Runs

| Component | Location | Access |
| --- | --- | --- |
| n8n (Bot) | LXC 103 on `ai-server` (192.168.178.32), IP `192.168.178.53`, Port 5678 | `ssh -F ~/.ssh/config ai-server "pct exec 103 -- …"` |
| Service `radio-tts` | Docker container `radio-tts` **in LXC 103** (Port 8881) | `… pct exec 103 -- docker exec radio-tts …` |
| Voting Service `sprechdienst` | systemd service in **CT 111** on `ai-server` (`192.168.178.116`), Port 10205 — own moderation voice | `ssh -F …/proxmox-ssh/config ai-server "pct exec 111 -- …"`; check: `curl -s http://192.168.178.116:10205/health` |
| AzuraCast | LXC 106 on the **data server** (192.168.178.163), Web `http://192.168.178.33` | `ssh -i ~/.ssh/id_ed25519 root@192.168.178.163 "pct exec 106 -- docker exec azuracast …"` |
| Ollama + HA-Whisper | LXC 105 on `ai-server` (`192.168.178.187`) | Port 11434 (speech model), Port 10300 (Home-Assistant-Whisper); the previous `whisper-stt` (**18790**) is shut off — start on demand: `pct exec 105 -- systemctl start whisper-stt` |
| Speech Recognition (Radio) | **whisper-amd** in LXC 112 on `ai-server` (`192.168.178.188:8000`) | whisper.cpp large-v3 on the **MI50** (since 2026-09-23) |
| Custom Search Engine (SearXNG) | LXC 108 on `ai-server` (`192.168.178.26`), Port 8888 | `pct exec 108 -- …`; services `uwsgi` + `redis-server`, setup: `REBUILD/searxng-setup.md` |
| Project Folder | `<dokuordner>/` | Tools, test runs, backups |

Useful addresses: Service `http://192.168.178.53:8881/health`,
Voting Service `http://192.168.178.116:10205/health`,
Station `http://192.168.178.33/api/nowplaying/1`,
Search Engine `http://192.168.178.26:8888/search?q=test&format=json`,
n8n Interface `https://YOUR-N8N-HOST`.

---

### 2. Implement Changes

#### 2.1 Change Behavior (Flow)

```bash
cd ../../werkzeuge

## 3. Fassung sichern (immer vorher!)
bash version-save.sh radio-vN-<datum>-<kurzname> /tmp/beschreibung.md

## 4. change the workflow: adjust the builder (agent-wf-build.py) and/or patch
bash agent-patch.sh --inhalt "Knoten A,Knoten B"     # adopt contents
bash agent-patch.sh --aufraeumen                     # canvas (positions, notes, frames)
bash agent-patch.sh --neu "Neuer Knoten" --umbenennen "Alt=Neu"

## 5. check and deploy
python3 layout-check.py /tmp/radio-agent-neu.json   # Ziel: 0 Befunde
bash agent-import-only.sh /tmp/radio-agent-neu.json
```

The patcher only handles the specified changes and checks at the end: no mask markers,
credentials and keys included, no logic nodes lost, all connection targets
present. After implementation, n8n restarts (~20 s), then the bot is reachable again.

#### 2.2 Change the Service (Language, Announcements, Research, Lists, Mailbox)

```bash
cd ../../werkzeuge
## Module liegen in ../service/*.py
bash service-import.sh        # copies all service/*.py + Dockerfile, rebuilds and restarts
```

The call ends with a self-report of the service (`/katalog/status`,
`/news/status`, `/ansage/status`) — this indicates that it is running.

#### 2.3 Change a Setting (Without Rebuilding)

In `/opt/radio-tts/secret.env` (in LXC 103 on the ai-server), then
`docker compose up -d` in the directory `/opt/radio-tts`:

| Value | Effect | Default |
| --- | --- | --- |
| `LIVE_LAUTSTAERKE_DB` | Announce at this many dB louder | 0 |
| `TTS_ZIEL_RMS_DB` | Target level of speech | -11.5 |
| `TTS_KOMPRESSOR_SCHWELLE_DB` / `TTS_KOMPRESSOR_VERHAELTNIS` | Compression | -19 / 3.0 |
| `TTS_BEGRENZER_DB` / `TTS_BEGRENZER_FREIGABE_MS` | Peak limit / release | -1.0 / 40 |
| `TTS_HOCHPASS_HZ`, `TTS_DEFAULT_VOICE` | Low-pass filter, voice | 80, `de_thorsten` (default; YOUR-VOICE on request: "… with your own voice") |
| `EIGENE_STIMME_URL` | Voting Service (CT 111) | `http://192.168.178.116:10205/tts` |
| `EIGENE_STIMME_ERSATZ` | Backup voice if the Voting Service is unreachable (empty = no backup voice) | `de_thorsten` |
| `EIGENE_STIMME_ZEITABLAUF` | Time limit for voice generation (seconds) | 600 |
| `LIVE_HOST/PORT/MOUNT/USER/PASSWORD` | DJ harbor; `LIVE_USER` is the **own bot account `deine-stimme`** — in the station, speaking appears as **"YOUR-VOICE"** (my access `operator` remains separate) | from the access file |

> **In operation differently (selected by ear, 2026-09-23):** In
> `/opt/radio-tts/secret.env` are `TTS_HOCHPASS_HZ=50`,
> `TTS_KOMPRESSOR_SCHWELLE_DB=-18`, `TTS_KOMPRESSOR_VERHAELTNIS=2.0`, and
> `TTS_ZIEL_RMS_DB=-12.5` — the softer setting ("Variant 3") makes the announcement
> less bright. Check the effect: `docker exec radio-tts env | grep TTS_`.

---

### 6. Backup and Rollback

**Versions** are stored outside the project folder under `<projektordner>/sicherungen/radio-fassungen/<name>/`:
the four flows as JSON, the service modules, the Dockerfile, the n8n database, and
a description (`README.md`). Create and check:

```bash
cd ../../werkzeuge
bash version-save.sh radio-vN-<datum>-<kurzname> /tmp/beschreibung.md
ls -l ../fassungen/radio-vN-.../          # Inhalt ansehen
```

Rollback: implement the flows from the backup (`agent-import-only.sh <file>`) and the service modules from `<version>/dienste/`
with `service-import.sh` redeploy. The included `n8n-daten.sqlite.gz` is
the complete n8n database (last resort).

**Station database**: backups of the station live on `192.168.178.163` under
`/root/azuracast-*` (e.g. state before and after cleaning up the archive).

---

### 7. Monitoring

```bash
## is the service running?
curl -s http://192.168.178.53:8881/health
curl -s http://192.168.178.53:8881/news/status
curl -s http://192.168.178.53:8881/ansage/status
curl -s http://192.168.178.116:10205/health   # Stimmendienst (eigene Stimme "deine-stimme")

## VRAM (reserve for the announcement voice, Ollama is loaded)
ssh -F ~/.ssh/config ai-server \
  "nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader"

## did a requested YOUR-VOICE announcement fall back to the reserve voice? (empty = everything fine;
## the message appears only if YOUR-VOICE was requested)
ssh -F ~/.ssh/config ai-server \
  "pct exec 103 -- docker logs --since 1h radio-tts 2>&1 | grep -i 'own voice' || echo 'ok - no fallback'"

## is the station running? (is_live = is the moderator speaking right now?)
curl -s http://192.168.178.33/api/nowplaying/1 | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['live']['is_live'], d['now_playing']['song']['text'], d['listeners']['current'])"

## what did the bot do last?
cd ../../werkzeuge
bash playlist/16-executions.sh 4      # latest runs with nodes and results
bash ausfuehrungen.sh 3                  # same for the main workflow
cat bot-last.js | ssh -F ~/.ssh/config ai-server \
  "pct exec 103 -- bash -c 'cat > /tmp/bot-last.js'"
ssh -F ~/.ssh/config ai-server \
  "pct exec 103 -- bash -lc 'docker cp /tmp/bot-last.js n8n:/tmp/ >/dev/null && docker exec -u node n8n node /tmp/bot-last.js 3'"
## bot-last.js shows: question, stage 0, commands (with "(enqueue)"), overview answer,
## answer text, buttons and errors per node.
```

**Logs:** Liquidsoap-Protokoll `…/stations/deadline_beats/config/liquidsoap.log` im
AzuraCast-Container (shows announcements as `interrupting_requests: Prepared …`),
n8n im Container `n8n` (LXC 103), Dienst `radio-tts` per `docker logs radio-tts`,
Stimmendienst `sprechdienst` per `pct exec 111 -- journalctl -u sprechdienst -n 50`.

---

### 8. After a restart

| Was | Verhalten |
| --- | --- |
| Dienst `radio-tts` | inbox and catalog are files → they survive; an **open playlist selection** is lost (the bot says "the selection has expired") |
| Stimmendienst `sprechdienst` (CT 111) | starts with systemd; the RVC model loads on the **first** call (~9 s). If it fails, the announcements fall back to `de_thorsten` (Kopfzeile `X-Stimme-Ersatz: 1`) |
| n8n | import overwrites `staticData` — the operator list and keys are set via `erlaubte-setzen.py` / `bot-data-set.py` |
| Ollama | the model is unloaded after 30 min; the next call costs 43.7 s (the schedule keeps it warm with a mini call) |
| station | the AutoDJ keeps running; a running announcement is finished after at most 30 s |

---

### 9. Common tasks

```bash
## station: restart the broadcast part (only if needed)
curl -s -X POST -H "X-API-Key: <key>" http://192.168.178.33/api/station/1/backend/restart

## rebuild the catalog (after moving many files, ~47 s)
curl -s -X POST -H "X-News-Key: <key>" http://192.168.178.53:8881/catalog/refresh

## Betreiber freischalten
python3 erlaubte-setzen.py <chatId>

## test the bot by hand (without Telegram)
bash bot-test.sh "what is playing"
```

---

### 10. Operating rules (learned from damage)

1. **Never deploy masked versions.** When comparing workflows,
   identifiers are replaced by `<SECRET>` — whoever deploys the masked file kills the
   bot (Telegram then answers 404). The patcher checks this itself by now.
2. **Rebuild the import files after every change to the builder** (done
   automatically by `agent-patch.sh`) — otherwise an old version gets deployed.
3. **Never rebuild completely**, patch instead: a rebuild touches the tool nodes
   and changes the tool names seen by the model.
4. **Back up before every change** (`version-save.sh`).
5. **Check after deploying**: `layout-check.py` (0 findings) and a
   short command via the test input.

## Troubleshooting

Everything here is **self-inflicted** and fixed — with the symptom, the cause, and the rule that came out of it.

---

### 11. The Bot Does Not Respond Anymore (Telegram 404)

**Symptom:** Every message goes unanswered; voice messages report "The voice message could not be processed."
**Cause:** During the comparison of two workflows, the **masked** version (using `<GEHEIM>` instead of the Telegram ID and API key) was inserted.
**Fix/rule:** Never insert masked versions.
**Diagnosis without secrets:** `getFile` with an old `file_id` must return 200; `sendMessage` to an unknown chat must return 400 "chat not found" (not 404).

---

### 12. Tools Fail: "i is not defined"

**Symptom:** The radio tool workflow responds with a JS error.
**Cause:** An **old** import file (`/tmp/radio-werkzeuge-import.json`) was inserted — it still contained a broken search pattern.
**Rule:** Rebuild import files after any changes to the generator; `agent-patch.sh` does this automatically now.

---

### 13. Every List Button Says "I Can't Fulfill This Order Yet"

**Symptom:** Playlist buttons go unanswered.
**Cause:** After renaming a node, the code still read the **old** field (`listenArt`).
**Rule:** After refactoring, look for legacy issues — the patcher checks this automatically.

---

### 14. Announcement Is Not Spoken / Cuts Off

| Symptom | Cause | Solution |
| --- | --- | --- |
| "Generator max buffered length exceeded" | Announcement uploaded in one go; Liquidsoap buffers at the harbor only ~10 s | the service sends **in the broadcast rhythm** (0.2-s segments) |
| First sentence missing | Liquidsoap switches the harbor only after a few seconds | Lead-in silence 5.5 s (`schweigen`), Tail 1.5 s |
| Two requests simultaneously: the second one does not come through | the sender has only **one** harbor; the second one waits | speak one after the other |
| Second request is not played | `request.queue` plays in sequence | empty the interrupting queue before immediate play (`interrupting_requests.flush_and_skip`) |

---

### 15. Request Is Not Accepted

| Message | Meaning |
| --- | --- |
| "This song was already requested and will play soon." | the request is already in the queue — no error |
| "This song or artist was played too recently" | cooldown period; set to **0** in operation (`request_threshold`) so requests always go through |
| "No interrupting tracks to play" | the interrupt queue was itself "recently played" (queue type was `once_per_x_minutes`) — correct type is `default` + `interrupt` |
| Request to choose | multiple titles match — the bot asks intentionally |

---

### 16. Responses Looked Wrong (Fixed Display Errors)

| Symptom | Cause | Solution |
| --- | --- | --- |
| "⚠️ (no output)" instead of the title list | the second attempt was empty and **overwrote** the useful list | empty responses no longer replace anything; retries no longer count as failures |
| No buttons for multiple titles | the model condensed the list into **one** line, `auswahl` did not apply | the bot builds buttons from the numbered list, even from a single line |
| List ends at "5" | text cut off at 300 characters | selection lists can go up to 1200 characters |
| Response does not arrive (Telegram error "can't parse entities") | sharp brackets in the text (e.g., `<Titel>`) at `parse_mode: HTML` | texts are masked (`&`, `<`, `>`) |
| Editing the message fails | message to old/deleted | second send attempt as new message |
| "what are there for messages" reads an unrequested message aloud | the model took "messages" for messages | Level 0 recognizes mailbox questions itself (0.4 s instead of 45 s, **without** announcement) |

---

### 17. Language and Speech Recognition

| Symptom | Cause | Solution |
| --- | --- | --- |
| Short German sentences are recognized as English | `language` was "automatically" | set `de` |
| Names are misheard ("new runners" instead of "Nirvana") | lack of context | Expert hint with the 45 most common interpreters as `prompt` |
| Voice too soft in the program | Piper delivers -16.6 LUFS, the music program -9.8 LUFS (the own voice `deine-stimme` runs through the same chain) | Loudness chain (see `MANUAL.md`, section 2) |
| Announcement does not get louder despite amplification | without compression the limiter has to intervene constantly | Compression **before** the limiter; release 40 ms instead of 120 ms |
| The announcement became softer instead of louder | the limiter's lookahead compared already smoothed values | always compare with the **raw** values |
| Announcement sounds like the **male voice** (`de_thorsten`) instead of `deine-stimme` | the voice service could not speak — usually the GPU was full and RVC responded with `CUDA out of memory` (HTTP 500); `radio-tts` then speaks **intentionally** with the backup voice | Check cause: `nvidia-smi` (backup available?) and the service log (`docker logs radio-tts`, line "your voice not reachable..."); free up space (see below), then speak again |
| First announcement after a long pause takes ~9 s longer | `sprechdienst` loads the RVC model on the first call | No error — only the first generation takes longer |
| Announcement sounds in the station **higher/brighter** differently than in the Telegram samples | **No pitch error** (measured 2026-09-23: fundamental tone 242.3 Hz raw = 242.3 Hz in the stream). The loudness chain in the radio service makes the voice **brighter** (spectral center 2688 → 2929 Hz) and **louder** (-20.8 → -12.2 LUFS) — brighter + louder is perceived as "higher" | no changes needed; for testing: record the stream, find and cut the announcement with `silencedetect`, compare raw vs. broadcast by ear and measurement (path below) |

**"In the station, it sounds higher" — measured on 2026-09-23:** The path was compared step by step (raw YOUR-VOICE file → loudness chain in the service → MP3/Sendetakt →
stream): The **fundamental tone is identical** (242.3 Hz raw and in the stream recording, autocorrelation); the **spectral center** rises from 2688 Hz to 2929 Hz, the **loudness** from -20.8 to -12.2 LUFS. The cause is the intended loudness chain (high-pass 80 Hz, compression 3:1, limiter) — Telegram listening samples without the chain sound warmer. Measurement path: record the stream with `ffmpeg` (`-c copy`), find the announcement with `silencedetect=noise=-40dB:d=2.5`, cut the section (`ffmpeg -ss … -t … -ac 1 -ar 22050`), compare the fundamental tone with a small autocorrelation script.

**Fixed on 2026-09-23 (my choice "Variant 3"):** The loudness chain is
deactivated — `TTS_HOCHPASS_HZ=50`, `TTS_KOMPRESSOR_SCHWELLE_DB=-18`,
`TTS_KOMPRESSOR_VERHAELTNIS=2.0`, `TTS_ZIEL_RMS_DB=-12.5` (instead of 80 / -19 / 3.0 /
-11.5; in `/opt/radio-tts/secret.env`, safety next to it). Less compression = the voice sounds less bright; the level is at -12.8 instead of -12.2 dBFS speech RMS. Check: `docker exec radio-tts env | grep TTS_`.

**Graphics memory (this was the cause on 2026-09-23):** The 3090 Ti (24 GB) carried
simultaneously Ollama (18.7 GB — loaded directly before each bot announcement), the old
`whisper-stt` (1.8 GB), the Home-Assistant-Whisper (1.8 GB), ComfyUI (0.3 GB), and the
YOUR-VOICE service — together more than fits in. **Fixed:** `whisper-stt` (LXC 105) is
stopped and set to manual operation (not wired since the move of speech recognition to the MI50; start on demand `systemctl start whisper-stt`), `sprechdienst` frees its CUDA intermediate storage after each announcement and runs with
`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`. Reserve in operation: around 2.6 GB.

---

### 18. Operation and Interpretation

| Symptom | Explanation |
| --- | --- |
| "No selection list available" | The marked list is exhausted or the service was restarted → search again |
| "Selection has expired" | Open playlist selection does not survive a service restart |
| The bot asks even though the title was clear | Two hits were too close together — better to ask than to play the wrong title |
| "Not completed: No. 1" after a follow-up query | Occurred earlier, fixed (version 7) |
| `/api/nowplaying` still shows the old title | The address is **15 s** cached |

---

### 19. Station Archive

| Symptom | Cause | Rule |
| --- | --- | --- |
| After moving files, titles are missing, playlists are empty | AzuraCast balances by `md5(Pfad)` — moving platters deletes the entry | Move folders **only via the API** (`files/batch` with `do=move`) |
| Search finds nothing, even though the word is present | Multiple words are linked with **AND** | Omit filler words or search fuzzily in the catalog service |
| A search run suddenly delivers Russian titles | An empty search delivers the **entire** archive (alphabetically first) | Never search without a term (the tools prevent this) |
| The bot suggests live recordings | `_Archiv/` (7,906 titles) and `moderation/` | Excluded from the search index and the tool |

---

### 20. Multiple Titles in a Message — Only the Last One Played

**Symptom:** "play X and then Y" (and any message with multiple music requests):
At the end, only the last title played, the others reported "not completed."
**Cause:** Each request was entered as **Immediate Play** (`do=immediate`) and
cut off the previous one; Level 3 no longer saw the first title as playing.
**Behebung/Regel (version 10):** With multiple music commands in a message, the
**first plays immediately**, all subsequent ones are **automatically queued** (`einreihen=true`).
Measured: "play Benzin by Rammstein and then Hyper Hyper by Scooter" →
"now playing immediately" + "queued." Up to **ten** tasks per message.

---

### 21. "next" Restarted the Broadcast Part

**Symptom:** After "next," the stream was briefly gone (broadcast part restarted).
**Cause:** `/api/station/1/backend/{action}` only knows `skip, disconnect, start, stop,
reload, restart`. An **unknown** action — here `play` — still responds with
**200 "Service restarted"** and restarts the broadcast part (measured on a running station on 2026-09-20).
**Behebung/Regel (version 10):** "next" is mapped to `start`. Use only
these six actions.

---

### 22. Overview: Weather Missing, 8 Minutes Were Only 4.7

*(Applies to version 10; since version 11, there is no minute indication anymore.)*

**Symptom:** In the overview, "weather not reachable," and "overview 8 minutes"
ended after 4.7 minutes.
**Cause:** The public weather feeds (wetter.de, wetter.com, tagesschau) deliver
**404**; each source read only 4 messages, making the cache too small.
**Fix/rule:** Weather in the overview comes from **Open-Meteo** (location from
`RECHERCHE_WETTER_ORT`), each source reads **10** messages, and the text is shortened to around the target length (1050 characters per minute measured). Result:
1 Min → 72 s, 3 Min → 194 s, 8 Min → 491 s.

---

### 23. Long Announcement Cuts Off (n8n Timeout)

**Symptom:** A multi-minute contribution was only partially delivered or the execution reported a timeout.
**Cause:** The announcement nodes had a **5-minute** timeout; the service sends at a transmission rate, so an 8-minute contribution requires about 10 minutes (generation + speaking).
**Rule:** Set the timeout for announcement and overview nodes to **15 minutes** (900000 ms); before a long contribution, check that no second announcement is running (the DJ port only supports one).

---

### 24. Search Engines Block the Bot — "normal web pages" were missing

**Symptom:** The topic overview brought headlines and Wikipedia articles but no page from the open web ("Web 0").
**Cause:** Public search engines block unregistered machines very differently (measured on 2026-09-21 from the service container): DuckDuckGo responds with **202** without hits, Mojeek with **Captcha**, Ecosia with **403**, kicker.de with 403 — only **Bing** delivers a results list. The links there are also wrapped (`bing.com/ck/a?…&u=a1<base64>`); without unpacking, no page is readable.
The SearXNG instance in **LXC 108** is only a **source code clone** (/opt/searxng, no service, no port) — it does not run.
**Fix/rule:** The service tries **its own SearXNG** (`RECHERCHE_SEARX_URL`), then DuckDuckGo, then Bing (with unpacking the links). If all fail, press releases, Wikipedia, and the 21 feeds contribute to the entry — web search is silently skipped. Own pages without feeds belong in `RECHERCHE_WEBSEITEN` (comma-separated).
**Completed on 2026-09-21:** The own instance runs in **LXC 108** on `http://192.168.178.26:8888` (setup: `REBUILD/searxng-setup.md`), the
service has `RECHERCHE_SEARX_URL` set. Measured: 20 German hits per search term, and each topic overview now reads at least one web page per topic.

---

### 25. "unreachable" for sources that had nothing to do with the topic

**Symptom:** The response named 20 sources as "unreachable".
**Cause:** In topic mode, each source without a relevant message was counted as a failure.
**Rule:** `ausgefallen` contains only real failures (not ladbar/leer). "No hits for the topic" is not a failure and is not reported.

---

### 26. Speech Filter Missed "Info" from "Informatik"

**Symptom:** On the radio, "application area of rmatik" could be heard.
**Cause:** The rule that removes source references like "Details at." lacked a **word boundary** and thus deleted the "Info" in "Informatik".
**Fix/rule:** Add word boundary at the end — and apply such patterns only at the **end of the text**, otherwise every "Information" in the middle of a sentence disappears. Also added: Image credits ("All rights reserved", IMAGO, picture alliance) and
Wikipedia source references (`[1]`, `[ 1.1 ]`) are no longer read out. For
source names as addresses, the main domain is taken (`de.wikipedia.org` → "Wikipedia").

---

### 27. Own Search Engine Responded with "Too Many Requests"

**Symptom:** The fresh SearXNG instance delivered only `…/search?q=…&format=json` on `429 Too Many Requests`, in the browser (HTML) it worked.
**Cause:** `server.limiter: true` in `/etc/searxng/settings.yml`. The limiter is intended for
public instances and requires a link token from requesters — a bot without
browser identification falls through.
**Rule:** Set `limiter: false` for the internal instance `systemctl restart uwsgi`. Additionally, `search.formats` must **`json`** —
otherwise SearXNG denies the JSON interface entirely.

---

### 28. Wikipedia did not find "künstliche intelligenz" (artificial intelligence)

**Symptom:** For a multi-word topic, no background ("Wiki 0") was found, even though the article exists.
**Cause:** The introduction interface requires the **exact** title: `…/page/summary/künstliche_intelligenz` (German for "artificial intelligence") responds with **404**, `Künstliche_Intelligenz` does not. Also, the spelling with only the initial capital letter ("Künstliche intelligenz") is incorrect. Additionally, Wikipedia provides a **disambiguation** for abbreviations like "KI" (`type: disambiguation`), whose text is worthless as background ("KI stands for: Sumerian deity, ...").
**Fix/rule:** First try several spellings, then use the search interface (`action=query&list=search`) to get the correct title; discard articles with `type != "standard"`. Measured result: "künstliche intelligenz" → "Künstliche Intelligenz is a research and application field of computer science..."

---

### 29. Press coverage displaced web and feed in topic overview

**Symptom:** The entry consisted almost entirely of headlines, "Web 0", despite the own search engine being active.
**Cause:** The quotas were smaller than the need: 4 slots per topic (`RECHERCHE_THEMA_MELDUNGEN`), of which up to 3 from the press and 1 from Wikipedia — leaving nothing for web and feeds. Press hits also carry **no** text, so the entry was content-poor.
**Fix/rule:** Now allocate **6** slots per topic, and the press gets only as many as leave room for Wikipedia, web, and feeds each **one** slot. This way, each topic gets headlines **and** content (read page) **and** background.

---

### 30. "Right arrow" and marks in speech text

**Symptom:** In the middle of the entry, "… an | tagesschau.de Search Right arrow Right arrow" could be heard.
**Cause:** Two characteristics of modern pages: Symbol labels are in `<svg><title>` elements (multiple `title` elements per page — the reader attached them all to the page title), and navigation aids for readers (`class="visually-hidden"`, `aria-hidden="true"`) were in the middle of paragraphs.
**Fix/rule:** Only take the **first** `title` outside of skipped areas as page title (`aria-hidden`/`visually-hidden` sorted out) and remove the marks addition after the title (`… | tagesschau.de`).

---

### 31. No search after a restart of LXC 108

**Symptom:** After `pct reboot 108`, the search engine did not respond for minutes ("Web 0" in topic overview), even though both services were listed as `enabled`.
**Cause:** Two things together:
1. The container hung in the network setup — `ip6=dhcp` triggered dhclient-Solicits with wait times up to **68 s**, `networking.service` remained at "activating".
2. The application ran over the **SysV-Emperor** (`/etc/init.d/uwsgi`), whose unit is `After=network-online.target` — it started only after the network.
**Fix/rule:** In the container, set `ip6=manual` (`pct set 108 -net0 … ,ip6=manual`) and start the application via a **dedicated systemd unit** `searxng.service` (`ExecStart=/usr/bin/uwsgi --ini /etc/uwsgi/apps-available/searxng.ini`, `After=network.target`); switch off SysV-`uwsgi` and remove the Vassal entry, otherwise two uWSGI instances will compete for port 8888. Restart test is part of acceptance: `pct reboot 108` → `systemctl is-system-running` = `running`, `searxng` = `active`, search delivers hits.

---

### 32. Arrangement shifted — nodes outside the frames

**Symptom:** `layout-check.py` reported in the agent **7 nodes without frames** (`Kurzbefehl?`, `Planen`, `Plan Antwort`, `Plan da?`, `Befehle lesen`, `Befehl da?`, `Kurz?`), a frame **without nodes** and **two overlapping frames** (`Notiz Analyse` / `Notiz Dienste`). In the interface, the blue frame "Level 0 and Level 1" was below the nodes it should explain.
**Cause:** The frames are calculated from the node positions (`tools/agent-wf-build.py`, Tables `BEREICHE`). When a sticky note is moved on the drawing surface with the mouse, this calculation is no longer correct — the nodes then lie beside their frame. (This happens, for example, when working in the interface, if a drag starts on a sticky note: a left drag on an empty area is a selection in n8n, a left drag on a note moves it.)
**Fix/rule:** The **plan in the building tool is the source**, not the interface:

```bash
cd ../../werkzeuge
bash agent-patch.sh --aufraeumen          # legt Positionen UND Rahmen neu
python3 layout-check.py /tmp/radio-agent-neu.json    # must report 0 findings
bash agent-import-only.sh /tmp/radio-agent-neu.json
## restart n8n so the new version takes effect:
ssh -F ~/.ssh/config ai-server \
  "pct exec 103 -- docker restart n8n"
```

Checked on 2026-09-21: 85 nodes and frames replaced, no **0 findings** afterward.
Bot responds (static data with operator list and tester key remain intact).
**Note:** On the surface, only **view** — do not pull. Anyone wanting to change something
should modify the source and re-run (see `APPENDIX/n8n-interface.html` §18).

---

### 33. If Nothing Else Works (Order)

1. `curl -s http://192.168.178.53:8881/health` — is the service running?
2. `curl -s http://192.168.178.33/api/nowplaying/1` — is the transmitter running?
3. `bash playlist/16-executions.sh 3` — what did the workflow do last?
4. `curl -s http://192.168.178.187:11434/api/tags` — does the language model respond?
5. Is n8n running? (`docker ps` in LXC 103) — it restarts after each deployment (~20 s).
6. Deploy the latest version (`fassungen/radio-v20-…`) and roll out the service from
   `<fassung>/dienste/` anew.

## Testing

All bot tests, with call and expectation. As of 2026-09-21 (version 11);
voice test added on 2026-09-23 (version 19) —
all listed tests were last **green**.

Principle: Tests must not disrupt the broadcast. Where a real announcement
is necessary, it is explicitly stated (`--live`); otherwise, only generated
("dry run").

---

### 34. Quick Tests (Seconds, without broadcast)

```bash
cd ../../werkzeuge
bash short-test.sh            # stage 0: 19 sentences -> expect "19 of 19"
bash answer-test.sh         # verdict, follow-up, answer, selection buttons -> "20 ok, 0 differing"
python3 layout-check.py /tmp/radio-agent-neu.json   # canvas -> "0 findings"
bash playlist/11-service-type-test.sh                      # bot input switch -> "37 of 37"
```

| Test | What it ensures |
| --- | --- |
| `short-test.sh` / `short-test.js` | that level 0 correctly identifies the right sentences (song request, direction, control, status, mailbox query) **and** passes everything else to the AI chain |
| `answer-test.sh` / `answer-test.js` | that an empty follow-up response does not clear the output, that a follow-up query is not "followed up," that selection buttons can also come from a compressed list, that a real failure is reported further |
| `layout-check.py` | each node in exactly one frame, no overlap, each node with labeling |
| `playlist/11-service-type-test.sh` | the switch from Telegram update to decision (buttons, texts, services) with the **real** `EINGABE_JS` |
| `layout-docs.sh` | generates `LAYOUT.md` anew and checks all four processes during this |

These tests pull their code directly from the generator (`fetch-js.py`) — they thus test
the **source**, not the running version in memory.

---

### 35. Service Test (requires the running service)

```bash
cd ../../werkzeuge
python3 news/19-news-test.py          # 45 Proben: Textaufbereitung, Postfach, Ansagewege
python3 news/19-news-test.py --live   # additionally a real announcement on air
python3 news/23-volume-test.py        # 8 samples: volume (calculates + asks the service)
bash playlist/09-service-test.sh                 # all playlist paths without Telegram
bash catalog-test.sh                            # Katalogdienst: Kontextsuche, Richtung
bash context-test.sh / bash context2-test.sh    # interpretation of multiple commands, quantities, references
bash voice-check.sh                          # finds a speech sample that the recognizer understands cleanly

## check the overview dry (no announcement on air, text and duration only):
MK=$(cat <dokuordner>/REBUILD/credentials/meldung-schluessel.txt)
curl -s -X POST http://192.168.178.53:8881/recherche -H 'Content-Type: application/json' \
  -H "X-Meldung-Schluessel: $MK" -d '{"art":"ueberblick","themen":"ki, raumfahrt","trocken":true}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['dauer_sekunden'], d['themen'], d['presse'], d['wiki'], d['web'], d['quellen'], d['ausgefallen'])"
## expect: speaking time depends on material (0.4-3 min), topics both topics, press ~3 per topic,
##           wiki 0/1, failed only on real outages
## without topics (latest news from the sources):  '{"type":"overview","dry":true}'
## with selected sources:                         '"sources":"heise golem"'

## Eigene Suchmaschine (SearXNG in LXC 108) pruefen:
ssh -F ~/.ssh/config ai-server \
  "pct exec 108 -- curl -s -m 20 'http://127.0.0.1:8888/search?q=test&format=json' | head -c 120"
## erwartet: {"query": "test", "results": [ ... ]}   (kein "Too Many Requests")
curl -s -m 30 \
  'http://192.168.178.26:8888/search?q=k%C3%BCnstliche+intelligenz&format=json&language=de-DE' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d["results"]), "Treffer")'
## expect: about 20 German hits; in the dry run above "web" must then be >= 1
## and "read" must contain at least one address

## check the announcement voice (default + YOUR-VOICE on request + Piper):
curl -s -D - -o /tmp/probe_standard.mp3 -X POST http://192.168.178.53:8881/v1/audio/speech \
  -H 'Content-Type: application/json' -d '{"input":"Standard voice test."}' | grep -i x-stimme
## expect: x-stimme: de_thorsten (default since 2026-09-25)
curl -s -D - -o /tmp/probe_deine-stimme.mp3 -X POST http://192.168.178.53:8881/v1/audio/speech \
  -H 'Content-Type: application/json' -d '{"input":"Test of the own voice.","voice":"deine-stimme"}' | grep -i x-stimme
## expect: x-stimme: deine-stimme   (if the voice service fails: x-stimme: de_thorsten + x-stimme-ersatz: 1)
curl -s -D - -o /tmp/probe_piper.mp3 -X POST http://192.168.178.53:8881/v1/audio/speech \
  -H 'Content-Type: application/json' -d '{"input":"Piper-Gegenprobe.","voice":"de_thorsten"}' | grep -i x-stimme
## erwartet: x-stimme: de_thorsten
curl -s http://192.168.178.116:10205/health   # voice service on CT 111
## erwartet: {"ok": true, ..., "pitch": 4, "basis": "de-DE-AmalaNeural", "tempo": "+40%", "index_rate": 0.65}

## did a requested YOUR-VOICE announcement fall back to the reserve voice? (empty = everything fine;
## the message appears only if YOUR-VOICE was requested)
ssh -F ~/.ssh/config ai-server \
  "pct exec 103 -- docker logs --since 1h radio-tts 2>&1 | grep -i 'own voice' || echo 'ok - no fallback'"
```

---

### 36. End-to-End through the Bot (Test input, real n8n)

```bash
cd ../../werkzeuge
python3 news/21-bot-news-test.py       # 6 samples: button, tool, release, schedule, cleanup
python3 news/21-bot-news-test.py --live --warten   # with a real announcement and waiting for the schedule
python3 playlist/15-bot-playlists-test.py           # playlist paths via the bot
python3 playlist/15-bot-playlists-test.py --spielen # additionally play for real (interrupts the broadcast)
bash bot-test.sh                                 # feste Probesuite (Hilfe, Wunsch, Knopf, Suche, Unsinn)
bash ask.sh "themen: raumfahrt"                # EINZELNE Nachricht (Ansage im Sender! ~1–2 Min)
bash ask.sh "spiele Benzin"                    # einzelne Nachricht
bash knopf.sh w1                                 # press a button
bash speech-test.sh / bash speech2-test.sh     # Sprachnachrichten (erzeugt OGG-Dateien)
bash instant-bot-test.sh / bash instant-button-test.sh  # immediate paths and the button "play immediately anyway"
bash ask.sh "ueberblick ki, raumfahrt"         # Themen-Ueberblick (Ansage im Sender!)
bash ask.sh "topics: photovoltaics from heise golem"   # topics + selected sources
bash ask.sh "give me an overview of ai, but do not read it aloud"   # must NOT speak
bash ask.sh "play Benzin by Rammstein and then Hyper Hyper by Scooter"   # batch command:
expect "plays right now" + "was enqueued"
```

**Important:** `bot-test.sh` does not **accept** any message — it is a fixed suite.
Individual messages go through `ask.sh` / `knopf.sh`; both read the tester key
from `/tmp/.botschluessel` (600). If the file is missing, it is created as follows (the value is **not**
displayed):

```bash
cd ../../werkzeuge
scp -q fetch-testkeys.js ai-server:/tmp/
ssh -F ~/.ssh/config ai-server \
  "pct push 103 /tmp/fetch-testkeys.js /tmp/fetch-testkeys.js >/dev/null && \
   pct exec 103 -- bash -lc 'docker cp /tmp/fetch-testkeys.js n8n:/tmp/ >/dev/null && \
   docker exec -u node n8n node /tmp/fetch-testkeys.js'" | head -1 > /tmp/.botschluessel
chmod 600 /tmp/.botschluessel
## Prerequisite: tunnel to the test entry
ssh -F ~/.ssh/config -N -L 5678:192.168.178.53:5678 ai-server
```

The history of a run (question, stage 0, commands, answer, buttons, errors) is shown by:

```bash
cd ../../werkzeuge
cat bot-last.js | ssh -F ~/.ssh/config ai-server \
  "pct exec 103 -- bash -c 'cat > /tmp/bot-last.js'"
ssh -F ~/.ssh/config ai-server \
  "pct exec 103 -- bash -lc 'docker cp /tmp/bot-last.js n8n:/tmp/ >/dev/null && docker exec -u node n8n node /tmp/bot-last.js 3'"
```

Expected for a batch command with several titles: `commands: play#1, play#2(enqueue), …`
— the further titles carry `(enqueue)`. For the overview: `stage 0: overview` and
`Overview: 🎙️ overview spoken (1.3 min, topics space travel, 3 from the press, with background, 1 from the web)`.
An old "N minutes" input is **ignored**.

A **single** run node by node (also the reason why a message
was rejected — e.g. "no access" when the test key is missing):

```bash
cd ../../werkzeuge
scp -q bot-execution.js ai-server:/tmp/
ssh -F ~/.ssh/config ai-server \
  "pct push 103 /tmp/bot-execution.js /tmp/bot-execution.js >/dev/null && \
   pct exec 103 -- bash -lc 'docker cp /tmp/bot-execution.js n8n:/tmp/ >/dev/null && \
   docker exec -u node n8n node /tmp/bot-execution.js <nummer>'"
```

The test runs clean up after themselves (news are discarded, titles are not
permanently enqueued) and report at the end "x ok, y differing".

---

### 37. Canvas and documentation

```bash
cd ../../werkzeuge
bash layout-docs.sh                       # retrieves the running processes, checks, writes LAYOUT.md
python3 layout-overview.py <ablauf.json>  # node list as Markdown (screen)
python3 preview.py <ablauf.json> bild.png 0.35   # process as image
python3 code-pruefen.py <ablauf.json>        # JS syntax of all code nodes check
```

---

### 38. Check the broadcast (audible on the radio)

```bash
cd ../../werkzeuge
python3 news/24-live-level.py "Test of volume. One, two, three."
## cuts the stream, plays a test announcement, and compares voice and music
```

Then check that the AutoDJ is running again:

```bash
python3 - <<'PY'
import json, urllib.request
n = json.loads(urllib.request.urlopen("http://192.168.178.33/api/nowplaying/1").read())
print("live:", n["live"]["is_live"], "| running:", n["now_playing"]["song"]["text"])
PY
```

---

### 39. Expected Values (measured 2026-09-20)

| Process | Expectation |
| --- | --- |
| Short command (status, request, direction, mailbox query) | 0.3–1.7 s |
| Title list with buttons | 25–30 s, list complete, buttons appropriate |
| Button press | ~1 s, title starts immediately |
| Management order (AI path) | 20–60 s, with confirmation before changes |
| Research with announcement (weather) | ~50 s including speaking time |
| Announcement during broadcast | Music muted, voice audible at broadcast volume, followed by AutoDJ |
| Mailbox card | within 5 minutes after deposit |

---

### 40. What a Test Run **Does Not** Cover

* Voice quality (only measurable, not automatically assessable)
* whether a broadcast sounds "good" (volume is measured: −11,8 LUFS on broadcast)
* broadcasts during GPU overload (response times may increase then)

---

### 41. Voice Selection — Default and YOUR-VOICE on Request (since 2026-09-25)

The bot speaks **with `de_thorsten` by default** (Piper, always available, no GPU).
The own moderation voice **"YOUR-VOICE"** is used **only on explicit request**:

* **Request in Telegram:** "sag durch: … **with your own voice**", "… **in your own voice**"
  → the bot sets `stimme=deine-stimme`; the phrase itself is **not** read out.
* **Without a request** `stimme` stays empty → default voice (live announcement, messages,
  overview, and research).
* Configured in `/opt/radio-tts/secret.env`: `TTS_DEFAULT_VOICE=de_thorsten`;
  your own voice runs via the external service (CT 111, port 10205, `EIGENE_STIMME_URL`).
  If it fails, the bot continues with `de_thorsten` (`EIGENE_STIMME_ERSATZ`) — no
  announcement falls out; the log then shows "Eigene Stimme nicht erreichbar".
* **Check:** every generation writes a line **`Stimme: <name>`** to the log
  (`docker logs radio-tts | grep 'Stimme:'`); `curl -D- … /v1/audio/speech` returns the
  header `x-stimme`.
* **Outage 25 Sep (cause):** `torch.OutOfMemoryError` on CT 111 (card filled to
  59–179 MB free). New in `speech-service.py`: CUDA cache is released before/after every
  conversion and a memory failure is **retried once** (2 s pause) — before,
  3.2–3.3 GB stayed behind and worsened the follow-up error.
