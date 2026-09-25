# Tools (build, import, check)

All scripts run on the workstation and talk to the containers and services over
SSH (n8n LXC 103, station LXC 106, GPU machine). This folder is the bot's
**workshop**: the workflow generator, the change and import paths, the checks,
and the tools for images and documentation.

**The build path in one sentence:** `agent-wf-build.py` generates the workflows
("Configuration - all values", the agent and the three tool workflows) as JSON;
`agent-patch.sh` fetches the running version from n8n, rebuilds it and applies
changes; `agent-import-only.sh` imports everything and restarts n8n. Before
every change, run `version-save.sh` - it stores to
`<projektordner>/sicherungen/radio-fassungen/` (outside the project).

---

## 1. The most important scripts

| Script | Task |
| --- | --- |
| `agent-wf-build.py` | the **generator**: builds configuration, agent and the three tool workflows as JSON (`/tmp/...`) |
| `agent-patch.sh` | fetches the running version, rebuilds and applies changes surgically -> `/tmp/radio-agent-neu.json` |
| `agent-import-only.sh` | imports configuration + agent + tools into n8n and restarts n8n |
| `konfiguration-import.sh`, `config-check.py` | import and check the central "Configuration - all values" workflow |
| `service-import.sh` | copies the modules from `../service/` into the container, rebuilds and restarts the service |
| `version-save.sh` | creates a version backup (workflows + modules + n8n database + description), outside the project folder |
| `german-texts.py` | fixes umlauts in the displayed texts of the workflows (runs as part of the build path) |
| `static-data-patch.py`, `erlaubte-setzen.py`, `bot-data-set.py` | maintain static data (allowed chats, test key, chat id) |
| `layout-check.py`, `layout-docs.sh` | check the canvas (0 findings) and write `../APPENDIX/LAYOUT.md` |
| `archive-frame.py`, `docs-note.py`, `note-old-versions.py` | set notes and frames in individual workflows |
| `short-test.sh`, `answer-test.sh`, `answers.js` | check code nodes without n8n |
| `bot-test.sh`, `ask.sh`, `knopf.sh` | operate the bot's test entry |
| `ausfuehrungen.sh`, `bot-last.js` | inspect the latest runs (which branch ran, reply text, buttons) |
| `preview.py`, `imageplan.py`, `module-images-plan.py`, `image-stitch.py`, `gif-capture.js`, `gif-build.py` | create images and animations of the bot (basis of the n8n booklet) |

**Groups:**

| Folder | Content |
| --- | --- |
| `docs/` | the workshop of this **documentation collection**: `n8n-docs-build.py` (HTML booklet), `docs-check.py` (check), `doc-official-build.py` (publication copy with placeholders), `veroeffentlichung-webseite.py` (edition for branch `webseite`: placeholders, defused voice) plus `zweig-webseite-sichern.sh` (mirrors it into the branch), `website-bruecke/` (feeds the website), `code-translate-en.py` (English code edition) |
| `playlist/` | playlist tasks and their checks |
| `news/` | check mailbox, announcements and speech recognition (`19-news-test.py`, `21-bot-news-test.py`, `23-volume-test.py`, `24-live-level.py`) |
| `tempo/` | the tempo change (163 s -> 1.7 s) with its measurements |
| `aufraeumen/` | the one-time music archive clean-up (2026-09-20) with its report |

---

## 2. What to adapt before the first run (rebuild)

| File | Place | In the original | For a rebuild |
| --- | --- | --- | --- |
| all `*.sh` | `CFG=~/.ssh/config` | workstation SSH config | your own SSH config (or plain `ssh`) |
| all `*.sh` | `pct exec 103` / `105` / `106` | original container ids | your own container ids/hosts |
| `agent-import-only.sh`, `agent-patch.sh` | `PROJEKT=YOUR-N8N-PROJECT-ID` | n8n project id | your own project id |
| `agent-patch.sh`, `version-save.sh` | `RADIO=<dokuordner>` | project folder | your own project folder |
| `service-import.sh` | `QUELLE=.../../dienst` | module folder | already correct (neighbour `service/`) |
| `bot-test.sh`, `ask.sh`, `knopf.sh` | test entry address | `127.0.0.1:5678` (inside the n8n container) | your own n8n address |
| `news/*.py`, `playlist/*.sh` | `192.168.178.53:8881` (service), `192.168.178.33` (station) | original addresses | your own addresses |
| `news/19...`, `21...`, `24...` | key file | `../REBUILD/credentials/...` | your own key file |
| `erlaubte-setzen.py` | chat id | operator chat | your own chat id |

**In short:** the original's IP addresses and container ids are inside the scripts;
the logic does not depend on them. Replace them and you have a runnable tool set.

---

## 3. Notes on individual files

* `agent-wf-build-v2-threestage.py` is the **older** generator (predecessor) - no
  longer used, but part of the development history.
* `news/probe-stimme-roh.wav` is a raw recording; the loudness check uses it.
* **Files with identifiers** (`moderator-import.json`, `agent-fassung-2026-09-19.json`)
  are in the folder but **not in git** (mode 600) - they contain the Telegram key
  and the station key.
* `../APPENDIX/LAYOUT.md` is the generated canvas overview; no copy is kept here
  any more (the generator writes it directly).

---

## 4. Order for a rebuild

1. `../REBUILD/README.md` steps 1-4 (service, models, n8n, build workflows).
2. `bash service-import.sh` - bring the modules into the service.
3. `bash agent-import-only.sh /tmp/radio-agent-neu.json` - import the workflows.
4. `python3 erlaubte-setzen.py <chatId>` and `bash telegram-menu.sh`.
5. Checks from `../DOCS/OPERATIONS.md`.
