# Template: The Bot for Replication

As of 2026-09-22, the bot has been restructured so that **all values are in one place**
and can be passed on as a template.

---

## 1. The One Place

A small dedicated process **`Konfiguration`** contains exactly one code node
(`Werte`) with all the details:

| Field | Content |
| --- | --- |
| `sender` | Address of the sender (AzuraCast), API key, station ID |
| `dienst` | Address of the own service (catalog, notifications, announcements) and mailbox key |
| `sprache` | Address of speech recognition (faster-whisper) |
| `sprachmodell` | Address of Ollama, key, model name |
| `telegram` | Address of the Telegram interface and bot token |
| `aufgaben` | **all texts that the speech model reads**: the three system commands (plan, check, execute) and the descriptions of the eight tools |

The node calculates the derived values (`sender.api`, `sender.admin`, `sprachmodell.v1`, `telegram.bot`, `telegram.datei`) itself
from the addresses —
these do not need to be maintained manually.

**Only this node is changed.** The four processes retrieve the values at startup via
their node `Konfiguration`; none of them contain any access values anymore. After changing:
save, done — no restart, no creator.

## 2. How the Processes Retrieve the Values

```
[Telegram Trigger] ┐
[test input]       ├─→ [Configuration] ─→ [branch plan?] ─→ [input] … or [fetch news] …
[Zeitplan]         ┘
```

The call returns the payload unchanged and attaches `konfig`. Each
expression therefore reads from the same source:

```js
{{ $('Konfiguration').first().json.konfig.sender.adresse }}
```

Two rules apply here (both tested on 2026-09-22):

1. **A URL component must be built as a COMPLETE expression.** n8n does not resolve
   `{{ … }}` in the middle of a string — the address landed literally in the node
   and the call failed with `Invalid URL: {{ $('Konfiguration')… }}`.
   Incorrect: `"{{ $('Konfiguration')…sender.adresse }}/api/station/1/files"`.
   Correct: `"={{ $('Konfiguration')…sender.adresse + '/api/station/1/files' }}"`.
   The creator handles this via the class `Ausdruck` (see `agent-wf-bauen.py`):
   `AZ + "/api/station/1"` results in exactly this form.
2. **The agent's tool nodes** (the eight `Werkzeug …` nodes) are attached as
   `ai_tool` to the agent, not in the main path. They therefore cannot see the node `Konfiguration`
   — whether n8n resolves expressions there is shown only in a test run.
   (Checked on 2026-09-22: it does — the call "what is running" went through the
   agent and the tool `was_laeuft` and responded correctly.)

## 3. Scope of the Four Processes

| Process | Nodes | Retrieve Values from Central |
| --- | --- | --- |
| `Konfiguration - alle Werte` | 3 | (is the central itself) |
| `Werkzeug - Radio` | 24 | 7 |
| `Werkzeug - AzuraCast` | 22 | 6 |
| `Werkzeug - Meldungen` | 20 | 1 |
| `Radio - Telegram-Agent` | 91 | 26 (of which 10 as tool nodes) |

## 4. Passing on the Template

```bash
cd ../..
VORLAGE=1 VORLAGE_ZIEL=/tmp/radio-vorlage python3 werkzeuge/agent-wf-bauen.py
```

Result: `01-konfiguration.json`, `02-werkzeuge.json`, `03-bot.json` — with
placeholders (`http://DEIN-SENDER`, `DEIN-AZURACAST-API-SCHLUESSEL`,
`DEIN-TELEGRAM-BOT-TOKEN`, `DEIN-MODELL`) instead of access data. The task and
tool texts remain intact, as they are part of the template.

For those replicating the bot:

1. import the three files into n8n (`Konfiguration` first),
2. open the node `Werte` and replace the placeholders with your own values,
3. create the two login data in n8n (Telegram account, Ollama) and select them in the node,
4. activate the five processes.

## 5. Testing and Integration

```bash
python3 werkzeuge/konfiguration-pruefen.py     # 5 checks (names, references,
                                               # expressions, reachability, secrets)
python3 werkzeuge/anordnung-pruefen.py /tmp/radio-konfiguration.json \
        /tmp/radio-werkzeuge.json /tmp/radio-agent.json      # must report 0 findings
bash werkzeuge/konfiguration-einspielen.sh     # imports and enables all five
```

**Important for future tool runs:** `agent-patchen.sh` retrieves the access values today
from the *running bot* (pattern `api.telegram.org/bot…` and `[0-9a-f]{16}:[0-9a-f]{32}`).
After this restructuring, they are available only in the node `Werte` — the patcher must read them from there in the future (from the process `Configuration`), otherwise it will run with empty values.

## 6. Other Changes

- **Backups are now harmless**: the outputs of `02-werkzeuge.json` and
  `03-bot.json` no longer contain keys and tokens. Only the `Konfiguration` process still
  carries secrets — that's why the template version can be safely
  shared.
- The check `konfiguration-pruefen.py` is new and runs on every change.