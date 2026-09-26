# Cleaned-up workflows (removed from n8n on 2026-09-25)

This is where the **backups** of the workflows that were removed from n8n on
2026-09-25 are kept. They are **no longer current versions around the
radio stations** — old issues of the bot (station "Deadline Beats") and the
single tools that later merged into the combined tool `Tool - Radio`.

**Important:** The files contain real keys (AzuraCast, Telegram) —
therefore permissions 600 and excluded from git via `.gitignore`.

They were removed at the operator's request ("clear out the bots that are no
longer current — related to the radio stations"). Checked beforehand: **no**
active workflow references any of these identifiers (checked via the
n8n database), and every file here was checked against its identifier after the
export.

| File | Identifier | Name in n8n | Nodes | last run |
| --- | --- | --- | --- | --- |
| `RadioTelegramBot-Wunschbot.json` | `RadioTelegramBot` | Radio - Telegram request bot | 52 | 2026-09-19 |
| `RadioTelegramBot-Archiv-2026-09-19.json` | `RadioTelegramBot-Archiv-2026-09-19` | Radio - Telegram request bot (backup 2026-09-19) | 52 | — |
| `RadioTelegramBot-copy-v1.json` | `iDfPikpAIqTO9XQ2` | Radio - Telegram request bot copy v1 | 52 | — |
| `Radio-AI-Moderator.json` | `bjFSfXGqpLg7AAXw` | Radio - AI-Moderator (archive of the first version) | 26 | 2026-09-19 |
| `RadioAgent-vor-dem-Umbau.json` | `da7f06de-…` | Radio - Telegram Agent (version 2026-09-19, before the rebuild) | 34 | — |
| `RadioAgent-Zwischenstand-V2.json` | `7Vv3NSFsS7OZaBSd` | Radio - Telegram Agent intermediate state V2.0 | 88 | — |
| `RadioAgent-copy.json` | `jt2IC4TVPTF1KDLp` | Radio - Telegram Agent copy | 34 | — |
| `RadioAgent-copy2-V2.json` | `zxBICXCfUaMGhNmT` | Radio - Telegram Agent copy 2 V2 | 65 | — |
| `Werkzeug-Titel-suchen.json` | `RadioWerkzeugSuche` | Tool - Search title | 11 | 2026-09-19 |
| `Werkzeug-Sofort-spielen.json` | `RadioWerkzeugSofort` | Tool - Play now | 5 | 2026-09-19 |
| `Werkzeug-Danach-spielen.json` | `RadioWerkzeugDanach` | Tool - Play later | 4 | — |
| `Werkzeug-Was-laeuft.json` | `RadioWerkzeugStatus` | Tool - What is running | 4 | 2026-09-19 |
| `Werkzeug-Richtung-suchen.json` | `RadioWerkzeugRichtung` | Tool - Search direction | 9 | 2026-09-19 |

After the removal, the station-related stock remains at these six workflows
(all active):

| Station | Workflows |
| --- | --- |
| "Deadline Beats" | `RadioAgentBot`, `RadioWerkzeug`, `AzuraWerkzeug`, `MeldungenWerkzeug`, `Konfiguration`, `StimmenBot` |

Not touched (not part of the radio): the NewsBot family and "recherche
done" (website news), Bewerbung – Analyse, Mail Extractor, Brave-Chatbot,
My workflow 1–4, Kevin, AI agent chat, SearchApi AI Agent, Check Online Status
Cluster.

## How the clean-up ran

`aufraeumen-2026-09-25.sh` (kept here as evidence) did, for each workflow:

1. exported it from n8n and checked the identifier in the file,
2. removed the rows from the n8n database
   (`workflow_entity`, `shared_workflow`, `workflow_history` — n8n has no
   delete command for workflows, and the REST interface needs a session),
3. restarted n8n (about a minute of pause for all bots).

Checked afterwards: 30 workflows in n8n, all six station-related ones
active, both radio streams HTTP 200, demo bot responds (1.6 s).
