# Speed of the radio bot (2026-09-20)

Starting point: a simple announcement ("I'll play something by Scooter.") needed
**163 s**. Measured on example run 2052: ~160 s of that was model time in
**6 calls** (`Plan` 51 s, `Check` 25 s, `Follow up` 74 s with 3 calls,
`Execute` 8.5 s with 2 calls).

## Result

| Case | before | after |
|---|---|---|
| "I'll play something by Scooter." (spoken phrasing) | 163 s | **1.7 s** |
| Management job (AI path, e.g. playlist) | 70–163 s | **45 s** |
| `Plan` call | 51 s | **2.3 s** |
| `Check` call | 25 s | 1.8 s (mostly without model at all) |
| `Follow up` call | 74 s | usually not needed |

## Three causes and what was done about them

### 1. The model "thought along" on every request

Measured with the real planning instruction:

| | duration | output tokens |
|---|---|---|
| as before (`/no_think` in the text) | 9.8 s | 347 |
| with `reasoning_effort: "none"` | **1.7 s** | **34** |

Resulting JSON identical in both cases. The `/no_think` text snippet is **not**
honored by `qwen3.6` via the Ollama interface; the field in the request body is.
→ Added in `modell_koerper()` (direct calls `Plan`, `Check`).

### 2. The check stage reported false alarms

In the example run `Check` rated a command as "not ok" although the tool itself
had reported `OK: "Scooter - Hyper Hyper" läuft jetzt sofort.` That triggered
`Follow up` with three more model calls (99 s for nothing).

→ `LAGE_JS` now recognizes: if **all** commands report success with `OK:`, the
verdict is proven and is made without a model (`klarErledigt`). The tools set
this marker themselves when they have executed.

### 3. Spoken phrasings bypassed the fast path

The workflow has a model-free pre-stage (`Short?`) that reacts to "spiele X",
"danach X" and short commands. The **spoken** phrasing "**Ich spiele mir etwas
von** Scooter" did not match the pattern and therefore landed in the complete AI
chain — exactly the case that was noticed as slow.

→ `KURZ_JS` now additionally recognizes "ich spiele/will/möchte … (etwas/was)
von X", "kannst du was von X spielen", "spiel mir mal was von X".

Also fixed on the way: "spiele **drei Lieder** von Rammstein" was previously
treated as a *title search* for the text "drei lieder von rammstein" and ran
into the void. Quantity statements ("drei Lieder", "2 Songs", "zwei Titel") now
go to the AI. Checked with `02-kurz-test.js` (19 cases, all as expected).

### 4. The model was unloaded after 5 minutes

The service in LXC 105 had `OLLAMA_KEEP_ALIVE=5m`. A reload costs **measured
43.7 s** — that was the rest of the 47 s that `Plan` still needed in the first
test. → Set to `30m` in `/etc/systemd/system/ollama.service.d/override.conf`
(backup `override.conf.vor-tempo-<stamp>` lies next to it). If the model should
stay in memory permanently, use `-1` instead of `30m` (then permanently uses
18.2 GB of VRAM).

## Mishap during deployment (2026-09-20) – and the lesson

The first version of `03-tempo-patchen.py` masked the credentials **for the
comparison only**, but then accidentally **deployed the masked version**. In the
running workflow, seven places then had `<SECRET>` instead of the Telegram
identifier and the interface key. Result: every voice message aborted (`getFile`
→ 404, "the voice message could not be processed") and the bot could no longer
send an answer (`sendMessage` → 404). Reported as "message to the bot does not
work".

Fixed by patching again from the backup with a script that uses the masking only
for a **copy** and checks before writing:

- no `<SECRET>` in the output,
- Telegram identifier and interface key are present,
- the adopted nodes contain no placeholders.

Afterwards it was checked against the real services: `getFile` with the file
identifier of the failed voice message → HTTP 200 with `file_path`;
`sendMessage` → HTTP 400 "chat not found" (i.e. valid address); a real run via
the test input into the operator chat: answer delivered in 1.9 s (`ok:true`).

**Lesson**: when comparing workflows, never reuse the masked version — make a
copy for the comparison and check at the end that the output contains the real
credentials (and no placeholders).

## What is still left

The `Execute` node is an n8n **agent node** (`lmChatOpenAi`). `reasoning_effort`
cannot be set there (the n8n version only uses the field on the responses path),
so the model keeps thinking along:

| | duration | output tokens | thinking text |
|---|---|---|---|
| as in the agent node | 51.9 s | 2,173 | 8,484 characters |
| with `reasoning_effort: "none"` | **1.6 s** | 17 | – |

That is the remaining ~40 s on the AI path. One way there would be a small
intermediate service in front of Ollama (e.g. port 11435) that adds
`reasoning_effort: "none"` on `/v1/chat/completions`, and pointing the bot's
credentials ("Ollama (OpenAI interface)") at that port. That was not commissioned
yet and is therefore **not** built in.

## Tools in this folder

| File | Purpose |
|---|---|
| `01-fassung-sichern.sh` (removed) | create a version backup of the workflows (+ n8n database) |
| `02-kurz-test.js` | check the pre-stage (`Short?`) with 19 example sentences – without n8n |
| `03-tempo-patchen.py` | adopt the changed nodes from the rebuild into the running version |
| `04-einspielen.sh` | deploy the patched workflow into n8n and restart n8n |
| `10-modell-zeitmessung.py` | measure model calls with/without thinking (lives in `aufraeumen/`) |

## Backup

`fassungen/radio-v2-2026-09-20-vor-tempo/` – exports of all four workflows, the
complete n8n database (`n8n-daten.sqlite.gz`), the builder scripts of this version
and the way back in the `README.md` there.
