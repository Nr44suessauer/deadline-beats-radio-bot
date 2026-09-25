# Build — Construction History and Versions

## Build history

> **Date:** 2026-09-25 (current version: `radio-v21-2026-09-25-zweisprachig`).
> This file tells **how** the bot was built: in what order, with which tools,
> decisions, and obstacles.
>
> * The **description of the result** is in `README.md`, `HANDBUCH.md`, and `HANDBUCH.md`.
> * The **change list per version** is in `BAU.md` (v1–v21).
> * The **developer sources** are in `<dokuordner>/` (creators, tools, versions) — here in the folder `NACHBAU/` for reconstruction.
>
> All information comes from version backups, test runs, and the construction meeting protocol (19.–25.09.2026).

---

### 1. The Goal

Starting point (19./20. September 2026): The own internet radio station **Deadline Beats** (AzuraCast, 56,635 titles) should be operated by a **Telegram bot** — immediate or queued requests, direction wishes ("what out of rock", "90s"), control (skip, status), later **self-moderation** (announcements in the running program), a mailbox for other bots, research for weather/news/overviews.

Everything on **own hardware**, without cloud: Speech model on the 3090 Ti, later a **custom voice**, learned from the own media collection. In the end, an agent with eight tools, four workflows, six service modules, own search engine, and own voice — built in **five days**.

---

### 2. The Construction Method — What Makes This Project Unique

Five rules shape the entire construction:

#### 2.1 Creator Instead of Manual Work

The n8n workflow is **never** built or drawn by hand. `werkzeuge/agent-wf-bauen.py` **generates** all four workflows as JSON (nodes, connections, positions, frames, labels, notes). Changes run surgically through `agent-patchen.sh`: only the named nodes are replaced, `--aufraeumen` lays out positions and frames anew from the plan.

> A complete rebuild is expressly forbidden — it would change the tool names relative to the language model (the model knows the tools by name).

#### 2.2 Version Before Each Change

`fassung-sichern.sh <name>` stores under `<projektordner>/sicherungen/radio-fassungen/<name>/`: the four workflows as JSON, the service modules, the Dockerfile, the **complete n8n database**, and a `README.md` with description and rollback path (rights 700/600 — the workflows contain identifiers). Rolling back is thus a two-liner. This way, **19 versions** (v1…v19) were created — each with a line in `BAU.md`.

#### 2.3 Test Before Deployment

* Before deployment: `anordnung-pruefen.py` (canvas), `code-pruefen.py` (JS nodes), `kurz-test.sh` (level 0), `antwort-test.sh` (response logic).
* After deployment: a real run through the test input and the execution log `bot-letzte.js` (question → level 0 → commands → response → buttons → errors).
* The service reports to itself after `dienst-einspielen.sh` (`/health`, `/meldungen/status`, `/ansage/status`).

#### 2.4 Source Code = Server

The source code in the project folder and the running state on the server must be **bit-for-bit identical** — regular md5 comparisons (e.g., `dienst/main.py` ↔ `/opt/radio-tts/app/main.py`, `sprechdienst.py` ↔ CT 111). What cannot be bit-for-bit identical (n8n database) is stored as an export in `NACHBAU/ablaeufe-laufend/`.

#### 2.5 Documentation Is Part of the Construction

Each change leaves: version + entry in `BAU.md` + affected sections in this documentation — **with date and measurements**. The documentation of this folder was itself generated from this process (first version on 20.09., since then repeatedly updated).

---

### 3. The Chronicle

#### 3.1 September 180 — Foundation: Archive, Wishbot, Version v1

* **Check and organize the archive:** The radio station's music archive was reviewed
  (Sortierung/Benennung), the AzuraCast interface was accessed (263 addresses).
* **Immediate play found:** `PUT /files/batch` with `do=immediate` ("Play Now")
  directly enters the interrupting queue — without pre-checks. Before that, the
  queue is cleared (`interrupting_requests.flush_and_skip`), so that the
  **latest** wish wins. The backend control deliberately uses `start`, **never**
  `play` (an unknown action responds with 200 but restarts the broadcast part).
* **First Wishbot** in n8n (`RadioTelegramBot`): Text and voice messages,
  archive search, spielen/einreihen; language model on Ollama for free text.
* **Version v1** secured: "Initial state (four workflows, as they ran)".

#### 3.2 September 20 — the day of great leaps (v2–v9)

| Version | What was built | Effect (measured) |
| --- | --- | --- |
| **v2** `…-vor-tempo` | Backup point before tempo change | Rollback point (163 s per announcement) |
| **v3** `…-mit-tempo` | `reasoning_effort: none`, **Rule decision instead of model**, fast path for spoken formulations, `OLLAMA_KEEP_ALIVE=30m` | Announcements in **1.7 s** instead of 163 s |
| **v4** `…-mit-listen` | Module `playlist.py`: build/manage/start lists via a dedicated service route | **0.2–0.7 s** per step |
| **v5** `…-mit-meldungen` | Module `meldungen.py`: Mailbox, spoken texts, **live announcement** via the DJ port, Telegram sharing with buttons, 5-minute schedule | The bot **speaks itself** in the program |
| **v6** `…-mit-recherche` | Module `suche.py`: Weather (Open-Meteo), news/RSS, Wikipedia, `POST /research`, tool `research` | "search for the weather for X" — and **multiple tasks** in one message |
| **v7** `…-auswahlliste` | Empty responses no longer replace anything, follow-up questions are not considered a failure, buttons directly from the list | A wish with multiple hits ends with **buttons** |
| **v8** `…-moderationslautstaerke` | Volume chain: High-pass filter, compression 3:1, level control, lookahead limiter | Moderation **−16.6 → −13.1 LUFS** (file), **−11.8 LUFS** on broadcast (~4 dB louder) |
| **v9** `…-oberflaeche` | Workflow canvas: calculated frames, colors per level, labeling at **each** node, overview note; check and documentation tools | The workflow explains itself upon opening (**0 findings**) |

In between, the **rebuild of the Wishbot into an Agent**: four workflows (the Telegram Agent +
three tool workflows), three-stage chain **Plan → Execute → Check** — the agent
checks each task **against the actual station state** ("responses are documented, not
claimed"). The old Wishbot workflows were kept as an archive.

#### 3.3 September 21 — Overview, Batch Commands, Own Search Engine (v10–v12)

* **v10:** `art=ueberblick` in `POST /research` (multiple sources, length in minutes;
  `ANSAGE_MAX_ZEICHEN` 700 → **9000** ≈ 8.5 minutes); Level-0-word **"overview"**;
  batch commands up to 10 tasks (first title immediately, others queued);
  announcement timeframes of the n8n nodes set to 15 minutes (the service sends in broadcast rhythm =
  real-time).
* **v11:** **Topic Overview** instead of time constraint (`themen` instead of `laenge`) — per topic
  press (Google News), Wikipedia, website (read) and matching feeds;
  **Feeds 6 → 21**; speech filter errors fixed ("Info" from "Informatik" was
  deleted); Level-0-commands "overview <topics>" and "topics: …".
* **v12:** **Own Search Engine** — SearXNG in LXC 108 (`192.168.178.26:8888`,
  uWSGI + redis, `limiter: false`, formats html+json), connected via
  `RECHERCHE_SEARX_URL`; plus overview corrections (places per topic 4 → 6,
  Wikipedia via the search interface, page reader filters help texts). New
  tools: `bot-ausfuehrung.js`, `hol-testerschluessel.js`.

#### 3.4 September 185 — the Interface as a Guide (v13–v18)

The n8n interface has been expanded to a **self-explanatory document**:

* **v13:** Restored layout (7 nodes were outside their frames), illustrated guide `ANHANG/n8n-oberflaeche.html` (23 images). Operating rule: view in the interface, do not drag.
* **v14:** Cleaned up archive "Radio – AI Moderator": six frames, note at **each** of the 19 nodes (`archiv-rahmen.py`).
* **v15:** Documentation note at all five guided workflows, old version note at the 13 old workflows.
* **v16:** `bildplan.py` + `bilder-zuschnitt.py` — 95 captures at scale 0.7–1.4 (previously 0.45–0.9), labels readable.
* **v17:** Workflow images per workflow (`modulbilder-plan.py`, `bilder-stitch.py`), clickable with zoom (pure JavaScript). Agent image 2525×1706 pixels.
* **v18:** Found and fixed six causes of failed images (zoom via zoom buttons instead of `zoom-to-fit`, forced bright image, interface elements hidden, capture area measured instead of assumed, module cutout = union of frames and nodes, capture only after stillness).

#### 3.5 September 22 — Template and Central Configuration

* **Central Configuration:** new workflow `Konfiguration` with **all** addresses, keys, model values, and model texts (3 system instructions, 8 tool descriptions). The four workflows retrieve it via a sub-workflow node. Testing tools: `konfiguration-pruefen.py` (5 tests), `konfiguration-einspielen.sh`; template mode `VORLAGE=1` generates a fresh installation without private values (`NACHBAU/vorlage.md`).
* **Measured n8n Rule** (discovered during the rebuild): `{{ … }}` in the middle of a string **is not** resolved — it must be `={{ … + '/pfad' }}`.

#### 3.6 September 23 — Speech Recognition on the MI50

Speech recognition for voice messages was moved from the 3090 Ti to the previously unused **AMD Instinct MI50**: new container **112 "whisper-amd"** (`192.168.178.188:8000`) with **whisper.cpp + Vulkan** (large-v3). Measured: ~**1.3 seconds per voice message**. The old service (`whisper-stt`, LXC 105, port 18790) remains as a fallback. The address is now in the central `Konfiguration` (`sprache.adresse`) — workflows query it from there.

#### 3.7 September 23 — Own Voice (v19) and Its Evening

The big day: From the own media stock, the **voice announcement "YOUR-VOICE"** was created — raw material separation (Demucs + ECAPA-Cluster), confirmation from me, collection of pure pieces, training of RVC model `<your-model>`, building of the speech service. The **complete story** is in `STIMME.md`, the **general guide for rebuilding for each series** in `STIMME.md`.

* **v19** `radio-v19-2026-09-23-eigene-stimme`: `radio-tts` knows the voice `deine-stimme` (external service on CT 111, port 10205), preset `TTS_DEFAULT_VOICE=deine-stimme` (since 2026-09-25 the default is `de_thorsten` — YOUR-VOICE on request, see 3.9), fallback `EIGENE_STIMME_ERSATZ=de_thorsten` with header `X-Stimme-Ersatz: 1`. **No n8n workflow needed to be changed** — workflows do not pass a fixed voice, the service preset applies everywhere (live announcement, messages, overview, dry runs).
* **On the same evening — the GPU incident:** The first real announcements sounded male because the GPU was full (Ollama 18.7 GB directly before each announcement + old `whisper-stt` 1.8 GB + HA-Whisper 1.8 GB + ComfyUI + YOUR-VOICE) — RVC crashed with `CUDA out of memory` (HTTP 500), `radio-tts` took the fallback path. **Fixed:** `whisper-stt` stopped and set to manual operation (1.76 GB free), YOUR-VOICE returns the CUDA intermediate cache after each announcement, `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`. Reserve since then ~2.6 GB. (Details: `BETRIEB.md` §7.)
* **And my voice choice**, by listening tests: pitch **+4**, tempo **+40%** (instead of the interim clarity version +20%), `index_rate` **0.65** (blend of base voice and training material) — this is the fixed sound of your own voice (since 25 Sep on request), ~**1050 characters per minute**.

#### 3.8 September 24–25 — display, docs, and the bilingual bot (v20–v21)

* **v20** `radio-v20-2026-09-24-deutsche-beschriftung`: umlauts in all display fields
  (nodes, notes, sticky notes), tool `deutsch-texte.py`; sticky note height grows with
  the number of lines (`dokunotiz`, `44 + 32·n`).
* **Docs rebuilt:** twelve books became four volumes (`HANDBUCH`, `BETRIEB`, `BAU`,
  `STIMME`); the builder copies live in `NACHBAU/`.
* **v21** `radio-v21-2026-09-25-zweisprachig`: the bot understands **German and English**
  in one chat. New: `sprache_raten` at the input, English stage-0 shortcuts, tool replies
  in the operator's language (`sprache` field), a stricter language rule in the execution
  prompt. **Two bugs found and fixed:** "what is playing" was hard-wired to a wrong
  station ID (now `senderId` from the configuration),
  and English announcements were confirmed in German (the confirmation now follows the
  language). Checks: status/request/list/selection/mailbox/announcement/voice message in
  each language, 13 samples green.
  Rollback: `radio-v21-vor-zweisprachig-2026-09-25`.
* **n8n folders and tags:** the workflows live in the folder `Deadline Beats`
  (6 workflows), the same name as a tag. The deploy
  script (`n8n-ordner-setzen.sh`) sets the folder —
  `n8n import:workflow` does not carry folder assignments.

#### 3.9 September 25 (evening) — voice selection and the second GPU incident (v28)

* **v28** `radio-v28-2026-09-25-stimmenwahl`: **the default voice is `de_thorsten` again**
  (Piper, always available); **your own voice on explicit request** ("… with your own voice").
  The tools ("Werkzeug Meldungen", "Werkzeug Recherche") therefore have a field
  **`stimme`**; it is passed through to `/ansage/text`, `/ansage/meldung`, and
  `POST /recherche` (`dienst/suche.py`). The phrase "with your own voice" belongs only in
  the field and is **not read out**. Each announcement writes a line
  **`Stimme: <name>`** to the service log.
* **The GPU incident (second):** `sprechdienst` answered with **HTTP 500
  (`torch.OutOfMemoryError`)** — the card was filled to 59–179 MB free (Ollama
  18.3 GB + leftovers); `radio-tts` took the fallback path. **Fixed in `sprechdienst.py`
  (source `NACHBAU/eigene-stimme/`):** the CUDA cache is released before and after every
  conversion, and a memory failure is **retried once** (2 s pause). Deployed to CT 111,
  three probes green (HTTP 200, 1.5–2.0 s).

---

### 4. What Each Layer Does (Overview)

| Layer | What | Where | Details |
| --- | --- | --- | --- |
| Trigger & Flows | Telegram input, Stages 0–3, Tools | n8n, LXC 103 | `HANDBUCH.md` |
| Central Values | Addresses, Keys, Model Texts | Flow `Konfiguration` | `NACHBAU/vorlage.md` |
| Speech Output & More | Language, Announcements, Catalog, Lists, Mailbox, Research | `radio-tts`, LXC 103, :8881 | `HANDBUCH.md` |
| station | Icecast + Liquidsoap/AutoDJ, 56,635 Tracks, Wish Pool | AzuraCast, LXC 106 (.163) | `BETRIEB.md` |
| Speech Model | Planning, Execution, Verification | Ollama, LXC 105 | `HANDBUCH.md` §4.4 |
| Speech Recognition | Speech Messages → Text | whisper-amd, LXC 112 (MI50) | `HANDBUCH.md` §3 |
| Personal Voice | Announcements with default voice (`de_thorsten`) or "YOUR-VOICE" on request | sprechdienst, CT 111, :10205 | `STIMME.md` |
| Personal Search | Network for Overviews | SearXNG, LXC 108 | `NACHBAU/searxng-einrichten.md` |

---

### 5. Measured Milestones

| Date | Milestone | Value |
| --- | --- | --- |
| 20.09. | Wish through AI Chain (before) | 163 s |
| 20.09. | Wish through Stage 0 (after) | **1.7 s** |
| 20.09. | List Step through Service | 0.2–0.7 s |
| 20.09. | Moderation on Send Volume | −11.8 LUFS on Broadcast |
| 21.09. | Overview Example "themen: raumfahrt" | 1.3 Min Contribution |
| 21.09. | Overview Feeds | 21 Sources |
| 23.09. | Speech Recognition (MI50) | ~1.3 s per Message |
| 23.09. | YOUR-VOICE Dataset | 280 Entries / 10:44 Min |
| 23.09. | Training `<your-model>` | 400 Epochs / 15,600 Steps, ~1 h |
| 23.09. | Warm YOUR-VOICE Announcement | 1.4–3.8 s per Sentence (first ~9 s) |
| 23.09. | Speaking Rate of Voice | ~1050 Zeichen/Minute (+40 %) |
| 23.09. | Bot Announcement Path (same Sentence) | 5.5 s → **4.7 s** after Tempo Adjustment |
| 23.09. | GPU Reserve after Incident | ~2.6 GB (previously 39 MB) |

---

### 6. Decisions and Rejected Paths

| Decision | Why |
| --- | --- |
| Immediate Play via `files/batch do=immediate` + Queue Clearing | no pre-checks, no "Queue is not empty"; latest wish wins |
| Backend Control `start`, never `play` | unknown actions respond with 200 and restart the broadcast part |
| Tools Play Themselves (Model Does Not See Paths) | smaller models invent paths and only announce |
| Check Responses Against Actual station State | "occupied, not claimed" |
| One Central (`Konfiguration`) for All Values | no address guessing, one place to change |
| **No** n8n Refit for the Voice | the flows do not pass a voice — service directive suffices |
| Abandoned WPL 9 (Interrupter) | `once_per_x_minutes` blocked 1 minute; `files/batch` is better |
| XTTS v2 Rejected | Voice came out ~3.4 semitones too low, sounded inferior (`STIMME.md` §11) |
| Pronunciation Rules ("Rööhre") Rejected | Operator: "reject röhre" — text is spoken normally |
| Clarity Adjustment +20 % → back to **+40 %** | Operator Choice on 23.09.: Dynamics Prevail |
| Personal Streamer Account `deine-stimme` for Announcements | the station shows "YOUR-VOICE" instead of the Operator Name when speaking; manual DJ access remains personal account |
| `whisper-stt` (18790) Decommissioned | not wired since MI50 move; freed GPU space for the voice |
| A Complete Flow Rebuild Is Prohibited | would change tool names relative to the model |

---

### 7. The Construction Tools

You are in `werkzeuge/` (Development) — here are the most important ones:

| Tool | Purpose |
| --- | --- |
| `agent-wf-bauen.py` | **generates** all four flows (source of truth for nodes, texts, code) |
| `agent-patchen.sh` | replaces individual nodes in the running flow; `--aufraeumen` resets the drawing surface |
| `agent-einspielen-nur.sh` | imports flows and restarts n8n |
| `anordnung-pruefen.py`, `anordnung-doku.sh` | checks the drawing surface (goal: 0 findings); writes `ANHANG/ANORDNUNG.md` |
| `code-pruefen.py` | checks the JS code of the nodes |
| `kurz-test.sh`, `antwort-test.sh` | Stage 0 (19 sentences) and response logic (20 samples) — directly from the generator |
| `konfiguration-pruefen.py`, `konfiguration-einspielen.sh` | checks and plays the central unit (5 checks) |
| `fassung-sichern.sh` | creates a version (flows, modules, n8n-DB, description) |
| `dienst-einspielen.sh` | rolls out the service modules, rebuilds, checks itself |
| `bot-test.sh`, `frage.sh`, `knopf.sh` | test suite and individual messages through the test input |
| `bot-letzte.js`, `bot-ausfuehrung.js`, `ausfuehrungen.sh` | execution logs (stages, commands, judgments, buttons) |
| `meldungen/*`, `playlist/*` | area checks (inbox/announcements, list paths) |
| `bildplan.py`, `modulbilder-plan.py`, `bilder-zuschnitt.py`, `bilder-stitch.py`, `n8n-doku-bauen.py` | generate the image guide (`ANHANG/n8n-oberflaeche.html`) |
| `altfassungen-notieren.py`, `archiv-rahmen.py` | notes for archive and old versions |
| **Voice** (workshop, `docs/projects/VoiceAssistent/` + `NACHBAU/eigene-stimme/`) | `einrichten-stimmen-dienst.sh`, `stimmen_dienst.py`, `cluster-proben.sh`, `deine-stimme_sammeln3/4/5.py`, `rvc-trainieren.sh`, `sprechdienst.py`, `tg-sprachnachricht.sh` |

---

### 8. Rebuilding

* `NACHBAU/README.md` — the complete guide (blocks, steps 1–8,
  test runs, what can be different).
* `NACHBAU/vorlage.md` — template mode (fresh installation without private values).
* `NACHBAU/eigene-stimme/` — rebuild the voice (scripts + guide);
  **general for each series:** `STIMME.md`.
* `NACHBAU/zugangsdaten/` — access values (700/600) plus `UEBERSICHT.md`.

---

### 9. Where to Look for What

| Question | File |
| --- | --- |
| What is the bot, how do you operate it? | `README.md` |
| What can it do (examples, measurements, limits)? | `HANDBUCH.md` |
| How does it work (stages, components, decisions)? | `HANDBUCH.md` |
| What addresses are there? | `HANDBUCH.md` |
| Operation: installation, monitoring, security | `BETRIEB.md` |
| Test runs with call and expectation | `BETRIEB.md` |
| Known issues and solutions | `BETRIEB.md` |
| All versions and what they brought | `BAU.md` |
| How the own voice came about (history) | `STIMME.md` |
| Clone a voice from a series (guide) | `STIMME.md` |
| Rebuild on new hardware | `NACHBAU/README.md` |
| Developer sources, versions, tools | `<dokuordner>/` |
| The interface in the image | `ANHANG/n8n-oberflaeche.html` |

## Versions

Every change to the running bot is secured as a **version**: the four workflows as
JSON, the service modules, the Dockerfile, the n8n database, and a description.
Storage location: `<projektordner>/sicherungen/radio-fassungen/<name>/`.

Creation: `bash werkzeuge/fassung-sichern.sh <name> [beschreibung.md]`

---

| Version | Content | Effect for the User |
| --- | --- | --- |
| **v1** `radio-v1-2026-09-20` | Initial state (four workflows, as they ran) | Wishes, direction, status — through the AI chain, slow |
| **v2** `…-vor-tempo` | State **before** the speed change | Backup point for rollback (163 s per announcement) |
| **v3** `…-mit-tempo` | `reasoning_effort: none`, Rule judgment instead of model, fast path for spoken formulations, `OLLAMA_KEEP_ALIVE=30m` | Announcements in **1.7 s** instead of 163 s |
| **v4** `…-mit-listen` | Playlist tasks via a separate service path (0.2–0.7 s per step) | "create a playlist", "play it", "delete it" |
| **v5** `…-mit-meldungen` | Mailbox, moderation and speech texts, **live announcement** via the DJ port, Telegram sharing with buttons, 5-minute schedule, tool `news` | The bot **speaks itself** on air |
| **v6** `…-mit-recherche` | Module `suche.py`: Weather (Open-Meteo), news-/RSS-Feeds, Wikipedia; `POST /research`; task type `research`; tool `research` | "search for the weather for X", "read out the news" — and **multiple tasks** in one message |
| **v7** `…-auswahlliste` | Selection lists no longer get lost (empty responses replace nothing), follow-up does not count as failure, buttons from the list, mailbox questions in stage 0 | A wish with multiple hits ends with **buttons** instead of "no output" |
| **v8** `…-moderationslautstaerke` | Volume chain: high-pass, compression 3:1, level control, lookahead limiter | Moderation **~4 dB louder**, in the usual ratio to the music |
| **v9** `…-oberflaeche` | Workflow canvas: calculated frames, colors per stage, labeling at **each** node, overview note, check and doc tools | The workflow explains itself upon opening (0 findings) |
| **v10** `radio-v10-2026-09-20-ueberblick-sammelbefehle` | Service: `art=ueberblick` in `POST /research` (multiple sources, length in minutes, `ANSAGE_MAX_ZEICHEN` 700 → 9000, new message type `ueberblick` with Vor-/Nachspann, weather via Open-Meteo); Workflow: stage-0-word **"overview"**, new branch `Ueberblick holen`/`Ueberblick Antwort`, **batch commands up to 10** (first title immediately, subsequent titles queued), shorter responses for many tasks, announcement node timeframes on 15 minutes | One word suffices for a **multi-minute** news overview from selectable sources — and up to ten tasks in one message, without a title request cutting off another. *(The backup in `fassungen/radio-v10-…/` is the state **before** this change = rollback point; the state after is in `NACHBAU/ablaeufe-laufend/` and `dienst/`).*
| **v11** `radio-v11-2026-09-21-themen-ueberblick` | Service: **Topic Overview** instead of time specification (`themen` instead of `laenge`), per topic press headlines (Google News), Wikipedia background, web search including reading the page and matching feed messages; **Feeds 6 → 21**; normal web pages via `RECHERCHE_WEBSEITEN` and web search (DDG/Bing, optional own SearXNG); Speech filter errors fixed ("Info" from "Informatik" was deleted, Bildnachweise/Quellenverweise were read out). Workflow: stage-0-commands **"overview <topics>"** and **"topics: …"** | "overview ki, space travel" → 1.5 min contribution with headlines, Wikipedia background, and feed hits; no time specification needed anymore. *(Backup = state **after** the change, i.e., the running state.)* |
| **v12** `radio-v12-2026-09-21-eigene-suchmaschine` | **Own search engine** in LXC 108 "SearXNG" (`http://192.168.178.26:8888`, Debian 12, 1 GB, uWSGI + redis, `limiter: false`, `formats: html+json`) and `RECHERCHE_SEARX_URL` in the service; Corrections in the topic overview: places per topic **4 → 6** with reserved place for Netz/Feed (the press displaced them before — "Web 0"), Wikipedia titles via the search interface ("artificial intelligence" found nothing), term clarifications discarded, page reader filters out help pages (`visually-hidden`/`aria-hidden`, `<svg><title>`) and brands in the title. New tools: `bot-ausfuehrung.js`, `hol-testerschluessel.js` | Each topic now comes with a **read web page** (live: "topics: space travel" → 1.3 min, 3 headlines, background, **1 from the web**), and the speech text is clean (no "right arrow", no brands). Setup for rebuilding: `NACHBAU/searxng-einrichten.md` |
| **v13** `radio-v13-2026-09-21-anordnung-aufgeraeumt` | **Arrangement of the canvas** restored from the plan (`agent-patchen.sh --aufraeumen` sets **all** positions and frames anew, empty sticky notes fall away): in the agent, 7 nodes of stage 0/1 were outside their frame, one frame was empty, two overlapped. **New:** illustrated documentation `ANHANG/n8n-oberflaeche.html` (23 images, embedded, generated by `werkzeuge/n8n-doku-bauen.py`) | The surface explains itself again — each node lies in its frame (`anordnung-pruefen.py`: **0 findings**) — and there is a guide "part by part with images". Operating rule: in the surface, only look, do not drag (see `BETRIEB.md` §22) |
| **v14** `radio-v14-2026-09-21-archiv-aufgeraeumt` | **Archive "Radio - AI-Moderator" set up:** six frames (Inputs, Context, Text and Voice, Output, Follow-up, Old Tools) and a note at **each** of the 19 nodes — set up with the new `werkzeuge/archiv-rahmen.py` (calculates the areas from the node positions, additively: no logic changed); `anordnung-doku.sh` now takes the archive with it in `ANHANG/ANORDNUNG.md` | Also the archive window explains itself (19/19 nodes with note, **0 findings**) — the UI is now fully tidy |
| **v15** `radio-v15-2026-09-21-notizen-und-doku-in-der-ui` | **Notes and documentation in the surface** for **all** radio workflows: the five led workflows get a **documentation note** (what the workflow is, who calls it, how to change and check it, which files describe it) — at the agent and the three tools from the building tool (`dokunotiz()` in `agent-wf-bauen.py`), at the archive from `archiv-rahmen.py`. The **13 old workflows** (Wishbot, copies, individual tool workflows, backups) receive each a **legacy note** via `werkzeuge/altfassungen-notieren.py`. New guide: Section 19 in `ANHANG/n8n-oberflaeche.html` | Upon opening any radio workflow, it is immediately clear what it is — also for the old versions; nothing is a mystery anymore. All workflows remain unchanged in operation (check: 0 findings, 0 faulty code nodes) |
| **v16** `radio-v16-2026-09-21-doku-ausschnitte` | **Guide images made readable.** New tools `werkzeuge/bildplan.py` (calculates each workflow snippets of 1–4 nodes with view point and scale) and `bilder-zuschnitt.py` (cuts the empty border away). **95 captures at scale 0.7–1.4** instead of 0.45–0.9; `ANHANG/n8n-oberflaeche.html` rebuilt: chapter per workflow, section per area, each image with a label with the node names; old images were in `ANHANG/bilder/alt/` — deleted (cleanup 2026-09-24) | In the guide, the labels are **readable** (about 18–20 px instead of 6 px in the image) — one can now see what is on the surface |
| **v17** `radio-v17-2026-09-22-modulbilder-zoom` | **Guide in module images.** `werkzeuge/modulbilder-plan.py` (Overall image per workflow + one image per module, scale so that a module fits in at most six tiles) and `werkzeuge/bilder-stitch.py` (assembles tiles pixel-precisely — the transformation values are in the filename). Important measured: the embedded browser window is **1417×895**, the drawing surface **1375×797**. `ANHANG/n8n-oberflaeche.html` rebuilt: per workflow overall image, module directory, per module **explanation + image + node list** — and **each image is clickable**: zoom view with mouse wheel, buttons, and dragging (pure JavaScript) | One image per module with the section explanations underneath; who wants to see more, clicks the image and zooms. Overall image of the agent: 2525×1706 points |
| **v18** `radio-v18-2026-09-22-bilder-korrekt` | **Guide images organized.** Six causes found and fixed: (1) **Scale** is now set and measured with the zoom buttons (×1.2 or ÷1.2) instead of `zoom-to-fit` — the button did not always work, then the scale remained 1.0 and the overall images were taken from the wrong distance (dark area with shifted stripes); (2) **forced bright image** (`emulateMedia colorScheme light`) — n8n follows the system setting, the new captures were dark, the frame colors barely visible; (3) **interface elements hidden** (zoom buttons, minimap, "Execute workflow", node toolbars) and the mouse taken out of the surface — before, they lay in each tile; (4) **capture surface measured** instead of assumed: `[data-test-id="canvas"]` = **1613×840 ab (42.65)** (window ≈ 1655×938), before calculated with 1417×895/1375×797; (5) **module snippet = union of frame and all nodes inside** (`modulbilder-plan.py`) — before, the frame cut nodes with their notes; (6) **capture only after stillness** (transform twice the same + 0.7 s; move via `WheelEvent`, measured `Δtx = −0,5·deltaX`) — before, the running movement shifted tiles by a few pixels. Additionally: the tile folder is emptied before each capture (old tiles mixed into the image otherwise) and `bilder-stitch.py` can trim empty borders (`--ohne-zuschnitt` switches it off). Capture instructions in `ANHANG/README.md` | The guide now shows bright, complete images: **no toolbar in the image, no cut-off node, readable text**, all 35 modules and 5 overall images from one run. Nothing was needed from the user — the causes lay all in the capture |
| **v19** `radio-v19-2026-09-23-eigene-stimme` | Service: **own moderation voice "YOUR-VOICE"** as selectable, external voice (`main.py`: `ist_eigene_stimme`/`erzeuge_audio_eigene`/`erzeuge_audio_gewaehlt`); **fallback path** `EIGENE_STIMME_ERSATZ` (standard `de_thorsten`) with log line and header `X-Stimme-Ersatz: 1`; `/health` with `deine-stimme`-block; `/v1/audio/voices` lists `deine-stimme`; time flow `EIGENE_STIMME_ZEITABLAUF=600 s` (generation ~1.6× real-time, measured); `meldungen.py` dry run uses the same voice selection; `docker-compose.yml`: `TTS_DEFAULT_VOICE=deine-stimme`, `EIGENE_STIMME_URL`, `EIGENE_STIMME_ERSATZ`. **No workflow changed** (the workflows do not pass a fixed voice). Herkunft/Nachbau: `STIMME.md`, `NACHBAU/eigene-stimme/` | All announcements of the bot (live, messages, overview) speak with the **own voice**; if the voice service fails (GPU machine), the bot continues speaking with `de_thorsten` as a fallback — no announcement falls out. Piper voices remain selectable via `voice`/`stimme`. *(Backup = state after the change; rollback in `fassungen/radio-v19-…/README.md`)* **Addendum 23.09.:** The announcements run in the station via an **own streamer account `deine-stimme`** (display name "YOUR-VOICE") — when speaking, "YOUR-VOICE" appears instead of my name (`LIVE_USER` in `geheim.env`; my access `operator` remains separate). |
| **v20** `radio-v20-2026-09-24-deutsche-beschriftung` | **Surface in correct spelling and with neatly framed frames.** New tool `werkzeuge/deutsch-texte.py` replaces the ASCII spelling of visible texts in **all seven workflows** with umlauts ("check", "läuft", "overview") — only sticky notes, node labels, and subtitles; file and command names remain untouched (`n8n-oberflaeche.html`, `--aufraeumen`, `anordnung-pruefen.py` are protected, measured). Nodes with name changes are moved with references (connections, `$('…')`) (15 renamings in the agent). **Archive frame reframed:** the nodes now stand on evenly spaced column distances and all seven frames are calculated from the browser-measured node sizes — no node or subtitle sticks out anymore (margin distances 16–40 px, measured in the browser), the note texts no longer cover any nodes. **Doc notes:** `dokunotiz()` now calculates with the real line height (`44 + 32·n`) — the configuration note was cut off at the bottom. **Build path:** tokens and interface keys now come from the workflow "Configuration – all values" (they have been there since 22.09.), `agent-patchen.sh`/`agent-patchen.py` read them from both files; `agent-einspielen-nur.sh` imports the configuration workflow along. **Images:** all 86 tiles newly captured (40 modules + 7 overviews), `ANHANG/n8n-oberflaeche.html` rebuilt (4.42 MB); the previous tiles were in `ANHANG/bilder/kacheln-2026-09-24-v1/` — deleted (cleanup 2026-09-24); the tiles and module images of that state were deleted after the build as well (only `modulplan.json`, `startmassstaebe.json` and the seven overview images remain) | The guide now shows **readable German labels** (ä/ö/ü everywhere), and in the archive workflow, all nodes with labels lie neatly in their frame — nothing covers the text anymore. In operation, nothing is rearranged: the same bot, the same paths, only the surface and its images are corrected. *(Backup = state before the change, including database; rollback in `fassungen/radio-v20-…/README.md`)* **Note 24 Sep:** **English edition** added under `EN/` — this folder: all documents translated, the seven workflows as English copies (IDs `…EN`, only display texts translated, not in operation, not imported) and English screenshots; the tools for this live in `EN/werkzeuge/`. The running bot including the voice is untouched. |

---

### What a version contains

```
fassungen/radio-v9-2026-09-20-oberflaeche/
  README.md            Beschreibung dieser Fassung
  ablaeufe/            RadioAgentBot.json, RadioWerkzeug.json, AzuraWerkzeug.json,
                       MeldungenWerkzeug.json, bjFSfXGqpLg7AAXw.json
  dienste/             main.py, katalog.py, playlist.py, meldungen.py, suche.py,
                       whisper_server.py, Dockerfile, docker-compose.yml
  bau/                 the intermediate build states (builder outputs)
  n8n-daten.sqlite.gz  complete n8n database (last resort)
  ARCHITEKTUR-der-Doku.md, README-der-Doku.md    the project documentation as of this version
```

Permissions: Directories 700, Files 600 (the workflows contain credentials).

---

### Rollback

```bash
cd ../../werkzeuge
bash agent-einspielen-nur.sh ../fassungen/radio-v7-2026-09-20-auswahlliste/ablaeufe/RadioAgentBot.json
## redeploy the service modules from the version
cp ../fassungen/<fassung>/dienste/*.py ../dienst/ && bash dienst-einspielen.sh
```

The n8n database (`n8n-daten.sqlite.gz`) should only be restored in emergencies: stop n8n,
unpack the file, replace the existing database, and start n8n.

---

### No Longer Existing Intermediate States

The workflows `RadioTelegramBot`, `RadioWerkzeugSuche` and the old
incoming switch are **archived** or replaced — they are no longer active in n8n.
The workflow `bjFSfXGqpLg7AAXw` (the former AI moderator) still exists but is not used;
it is included in every backup.
