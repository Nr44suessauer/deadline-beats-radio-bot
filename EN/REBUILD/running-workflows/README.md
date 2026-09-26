# Running Workflows (exact state)

These files are the **exports of the running** n8n workflows (**as of 2026-09-24**)
— with them, the bot can be **exactly** restored without rebuilding it:

```bash
# deploy into n8n on the target system (example: bot)
n8n import:workflow --input=RadioAgentBot.json --projectId=<Projektkennung>
n8n update:workflow --id=RadioAgentBot --active=true
# then restart n8n (otherwise the old version stays in memory)
```

The three tools (`RadioTool`, `AzuraTool`, `NewsTool`) and the agent are the same as the
German originals. Additionally, `VoiceBot.json` ("Voices from movies" — form/webhook
for the voice service). The central `Konfiguration` workflow and the earlier AI
moderator (`bjFSfXGqpLg7AAXw`) are **not** among the English copies — both exist in
the German original folder.

---

## Note: in this edition these files carry placeholders

The **Telegram bot token** and the **AzuraCast key** in the HTTP nodes are
**placeholders** (`DEIN-…`) here — replace them before importing, or rebuild the
workflows (`../../tools/agent-wf-build.py`). The working copy contains the real values
(permissions `600`). There:

* Do not share, do not put in a repository, do not upload to the cloud.
* In the working copy the folder `../credentials/` belongs to this (same values in plain text).
* **Never insert masked versions** (if identifiers were replaced by
  `<GEHEIM>` for verification) — this will kill the bot, see `../../DOCS/OPERATIONS.md`,
  section 1.

## Rebuild

Instead of copying, the workflows can also be **built** — then they will contain their own
access values:

```bash
cd ../../tools
export TG_TOKEN=…  AZ_KEY=…  MELDUNG_SCHLUESSEL=…
python3 agent-wf-build.py                 # -> /tmp/radio-konfiguration.json, /tmp/radio-werkzeuge.json, /tmp/radio-agent.json
python3 layout-check.py /tmp/radio-agent.json     # 0 findings
python3 import-agent-prepare.py       # -> /tmp/radio-agent-import.json + /tmp/radio-werkzeuge-import.json
bash agent-import-only.sh /tmp/radio-agent-import.json
```

Difference between the two approaches:

| Approach | Advantage | Disadvantage |
| --- | --- | --- |
| **Copy** (these files) | the same bot, operational in minutes | replace the placeholders `DEIN-…` and select the Telegram credential in n8n; a Modell-/Stimmenwechsel change does not affect it |
| **Build** (`tools/agent-wf-build.py`) | own access values, fully traceable | sets the `name` field in the tool nodes (cosmetic, changes tool names compared to the model) |
