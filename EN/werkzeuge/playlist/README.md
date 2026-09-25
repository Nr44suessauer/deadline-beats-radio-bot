# Playlist tasks (playlists in the station)

Tools, test runs and the deploy path for the radio bot's **multi-step tasks**
around playlists: build, select in the Telegram menu, manage and play.

The logic itself lives in **`../../dienst/playlist.py`** and runs in the
`radio-tts` service (LXC 103, port 8881). This folder holds the scripts that
deploy it, check it and patch it into the n8n workflow.

## The path of an extension

```bash
cd ../../werkzeuge/playlist

python3 10-zerlegen-test.py        # 1) check parsing (sentences -> job)
bash 11-dienst-art-test.sh        # 2) check the switch (Telegram update -> decision)
bash 08-dienst-einspielen.sh       # 3) module into the service, rebuild the service
bash 09-dienst-test.sh             # 4) all playlist paths without Telegram
bash 13-listen-patchen.sh          # 5) rebuild the workflow, compare, patch
bash 14-listen-einspielen.sh       # 6) deploy the workflow and activate it
python3 15-bot-listen-test.py      # 7) end to end via the bot
```

Before step 5/6 a backup of the running version belongs there:

```bash
cd ../../werkzeuge
bash fassung-sichern.sh radio-vX-<date>-<shortname> /tmp/description.md
```

Back to the saved state (bot workflow only):

```bash
bash ../tempo/04-einspielen.sh \
  <datei> RadioAgentBot   # <datei> = export from a backup or fresh from n8n
```

## The scripts

| File | What it does |
| --- | --- |
| `05-listenwege-test.sh` | earlier test run of the station addresses (create/extend/clear) |
| `06-leeren-umbenennen-test.sh`, `07-umbenennen-test.sh` | single checks from the build phase |
| `08-dienst-einspielen.sh` | copies `dienst/playlist.py` into the service, wires the router into `main.py`, rebuilds and restarts the service |
| `09-dienst-test.sh` | 13 steps: show lists, menu, tick, create, cancel, view, rename, clear, delete, list selection, unknown job |
| `10-zerlegen-test.py` | job parsing without service and without network (mocks for FastAPI/Pydantic) |
| `11-dienst-art-test.{sh,js}` | sends real Telegram updates through **the real `INPUT_JS`** and then through the `SERVICE_TYPE_JS` switch (37 cases: playlist buttons, news buttons, texts) |
| `12-neubau-vergleich.py` | lists what a complete rebuild would change against the running version |
| `13-listen-patchen.{sh,py}` | creates the rebuild and patches **only** the playlist nodes, `Input`, connections and positions into the running version (repeatable) |
| `14-listen-einspielen.sh` | imports the patched version, activates it, restarts n8n, checks the webhook |
| `15-bot-listen-test.py` | end to end via the test input with real messages in the operator chat; `--spielen` additionally tests playing |
| `16-ausfuehrungen.sh` | shows the latest runs of the bot workflow with node outputs (which branch ran) |

## Why we patch instead of rebuilding

`agent-einspielen.sh` would rebuild the **whole** workflow. The builder sets the
`name` field on the six tool nodes (`search_title` and so on), which the running
version does not have — that would change the tool names seen by the model and
does not belong to this extension. `13-listen-patchen.py` therefore patches
surgically:

- the new nodes `Listen type`, `Listen?`, `Listen service`, `Listen answer`,
  `Listen send` and the sticky note `Note Listen`,
- the new content of `Input` (field `knopfRoh`),
- the five changed connections,
- the positions of the seven moved nodes.

Afterwards it checks: no mask markers (`<SECRET>`), Telegram identifier and
interface key present, every connection target exists, node count matches. Only
then it writes.

## Pitfalls (short)

- **Field names**: `INPUT_JS` returns `isCallback` (not `istCallback`). Test runs
  must use the real `INPUT_JS`, otherwise they test past reality.
- **HTML**: answers go to Telegram with `parse_mode: HTML`, `&`, `<`, `>` must be
  escaped (`<Name>` in a sample sentence broke the send with HTTP 400).
- **Editing the menu**: `edit: true` → `editMessageText`, otherwise `sendMessage`.
- **Delete test lists again**: a created list is `default` and immediately ready to play.
- **Playing** interrupts the broadcast (`flush_and_skip`, then `immediate` + `queue`).

Full version: `../../README.md` §11 and `../../DOKU/HANDBUCH.md` §5.
