# Running Workflows (exact state)

These files are the **exports of the running** n8n workflows (**as of 2026-09-24**)
— with them, the bot can be **exactly** restored without rebuilding it:

```bash
# deploy into n8n on the target system (example: bot)
n8n import:workflow --input=RadioAgentBot.json --projectId=<Projektkennung>
n8n update:workflow --id=RadioAgentBot --active=true
# then restart n8n (otherwise the old version stays in memory)
```

The three tools (`RadioWerkzeug`, `AzuraWerkzeug`, `MeldungenWerkzeug`) are the same.
Additionally, there are the two later workflows `Konfiguration.json` (the central
"Configuration – all values", from which all workflows get their addresses) and
`StimmenBot.json` ("Voices from movies" — Formular/Webhook for the voice service).
`bjFSfXGqpLg7AAXw.json` is the earlier AI moderator — it is not used but is part of the set.

---

## Note: in the working copy these files contain access data

In the HTTP nodes of the **working copy** you find the **Telegram bot token** and the
**AzuraCast key** (that is why the files in the working folder are set to `600`). There:

* Do not share, do not put in a repository, do not upload to the cloud.
* The folder `../zugangsdaten/` belongs to this (it contains the same values in plain text).
* **Never insert masked versions** (if identifiers were replaced by
  `<GEHEIM>` for verification) — this will kill the bot, see `../../DOKU/BETRIEB.md`,
  section 1.

## Rebuild

Instead of copying, the workflows can also be **built** — then they will contain their own
access values:

```bash
cd ../werkzeuge
export TG_TOKEN=…  AZ_KEY=…  MELDUNG_SCHLUESSEL=…
python3 agent-wf-bauen.py                 # -> /tmp/radio-konfiguration.json, /tmp/radio-werkzeuge.json, /tmp/radio-agent.json
python3 anordnung-pruefen.py /tmp/radio-agent.json     # 0 Befunde
python3 import-agent-vorbereiten.py       # -> /tmp/radio-agent-import.json + /tmp/radio-werkzeuge-import.json
bash agent-einspielen-nur.sh /tmp/radio-agent-import.json
```

Difference between the two approaches:

| Approach | Advantage | Disadvantage |

| --- | --- | --- |

| **Copy** (these files) | exactly the same bot, operational in minutes | requires the old access values; a Modell-/Stimmenwechsel change does not affect it |

| **Build** (`werkzeuge/agent-wf-bauen.py`) | own access values, fully traceable | sets the `name` field in the tool nodes (cosmetic, changes tool names compared to the model) |