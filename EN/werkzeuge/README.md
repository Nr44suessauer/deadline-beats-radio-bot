# Tools (build, import, check)

All scripts run on the workstation and talk to the containers and services over
SSH (n8n LXC 103, station LXC 106, GPU machine). This folder is the bot's
**workshop**: the workflow generator, the change and import paths, the checks,
and the tools for images and documentation.

**The build path in one sentence:** `agent-wf-bauen.py` generates the workflows
("Configuration - all values", the agent and the three tool workflows) as JSON;
`agent-patchen.sh` fetches the running version from n8n, rebuilds it and applies
changes; `agent-einspielen-nur.sh` imports everything and restarts n8n. Before
every change, run `fassung-sichern.sh` - it stores to
`<projektordner>/sicherungen/radio-fassungen/` (outside the project).

---

## 1. The most important scripts

| Script | Task |
| --- | --- |
| `agent-wf-bauen.py` | the **generator**: builds configuration, agent and the three tool workflows as JSON (`/tmp/...`) |
| `agent-patchen.sh` | fetches the running version, rebuilds and applies changes surgically -> `/tmp/radio-agent-neu.json` |
| `agent-einspielen-nur.sh` | imports configuration + agent + tools into n8n and restarts n8n |
| `konfiguration-einspielen.sh`, `konfiguration-pruefen.py` | import and check the central "Configuration - all values" workflow |
| `dienst-einspielen.sh` | copies the modules from `../dienst/` into the container, rebuilds and restarts the service |
| `fassung-sichern.sh` | creates a version backup (workflows + modules + n8n database + description), outside the project folder |
| `deutsch-texte.py` | fixes umlauts in the displayed texts of the workflows (runs as part of the build path) |
| `statische-daten-patchen.py`, `erlaubte-setzen.py`, `bot-daten-setzen.py` | maintain static data (allowed chats, test key, chat id) |
| `anordnung-pruefen.py`, `anordnung-doku.sh` | check the canvas (0 findings) and write `../ANHANG/ANORDNUNG.md` |
| `archiv-rahmen.py`, `doku-notiz.py`, `altfassungen-notieren.py` | set notes and frames in individual workflows |
| `kurz-test.sh`, `antwort-test.sh`, `antworten.js` | check code nodes without n8n |
| `bot-test.sh`, `frage.sh`, `knopf.sh` | operate the bot's test entry |
| `ausfuehrungen.sh`, `bot-letzte.js` | inspect the latest runs (which branch ran, reply text, buttons) |
| `vorschau.py`, `bildplan.py`, `modulbilder-plan.py`, `bilder-stitch.py`, `gif-aufnahme.js`, `gif-bauen.py` | create images and animations of the bot (basis of the n8n booklet) |

**Groups:**

| Folder | Content |
| --- | --- |
| `doku/` | the workshop of this **documentation collection**: `n8n-doku-bauen.py` (HTML booklet), `doku-pruefen.py` (check), `doc-official-bauen.py` (publication copy with placeholders), `website-bruecke/` (feeds the website), `code-uebersetzen-en.py` (English code edition) |
| `playlist/` | playlist tasks and their checks |
| `meldungen/` | check mailbox, announcements and speech recognition (`19-meldungen-test.py`, `21-bot-meldungen-test.py`, `23-lautstaerke-test.py`, `24-live-pegel.py`) |
| `tempo/` | the tempo change (163 s -> 1.7 s) with its measurements |
| `aufraeumen/` | the one-time music archive clean-up (2026-09-20) with its report |

---

## 2. What to adapt before the first run (rebuild)

| File | Place | In the original | For a rebuild |
| --- | --- | --- | --- |
| all `*.sh` | `CFG=~/.ssh/config` | workstation SSH config | your own SSH config (or plain `ssh`) |
| all `*.sh` | `pct exec 103` / `105` / `106` | original container ids | your own container ids/hosts |
| `agent-einspielen-nur.sh`, `agent-patchen.sh` | `PROJEKT=YOUR-N8N-PROJECT-ID` | n8n project id | your own project id |
| `agent-patchen.sh`, `fassung-sichern.sh` | `RADIO=<dokuordner>` | project folder | your own project folder |
| `dienst-einspielen.sh` | `QUELLE=.../../dienst` | module folder | already correct (neighbour `dienst/`) |
| `bot-test.sh`, `frage.sh`, `knopf.sh` | test entry address | `127.0.0.1:5678` (inside the n8n container) | your own n8n address |
| `meldungen/*.py`, `playlist/*.sh` | `192.168.178.53:8881` (service), `192.168.178.33` (station) | original addresses | your own addresses |
| `meldungen/19...`, `21...`, `24...` | key file | `../NACHBAU/zugangsdaten/...` | your own key file |
| `erlaubte-setzen.py` | chat id | operator chat | your own chat id |

**In short:** the original's IP addresses and container ids are inside the scripts;
the logic does not depend on them. Replace them and you have a runnable tool set.

---

## 3. Notes on individual files

* `agent-wf-bauen-v2-dreistufig.py` is the **older** generator (predecessor) - no
  longer used, but part of the development history.
* `meldungen/probe-stimme-roh.wav` is a raw recording; the loudness check uses it.
* **Files with identifiers** (`moderator-import.json`, `agent-fassung-2026-09-19.json`)
  are in the folder but **not in git** (mode 600) - they contain the Telegram key
  and the station key.
* `../ANHANG/ANORDNUNG.md` is the generated canvas overview; no copy is kept here
  any more (the generator writes it directly).

---

## 4. Order for a rebuild

1. `../NACHBAU/README.md` steps 1-4 (service, models, n8n, build workflows).
2. `bash dienst-einspielen.sh` - bring the modules into the service.
3. `bash agent-einspielen-nur.sh /tmp/radio-agent-neu.json` - import the workflows.
4. `python3 erlaubte-setzen.py <chatId>` and `bash telegram-menue.sh`.
5. Checks from `../DOKU/BETRIEB.md`.
