# DDD-Webseite — demo station with **one** bilingual bot (DE/EN)

As of 2026-09-25 (rebuild: the two single-language bots DE and EN were merged
into **one** bot). This edition was built **on top of** the existing bot: the
running bot (`RadioAgentBot`, station “Deadline Beats”) was **not touched** —
none of its workflows, its station, or its services.

Goal: a **second, dedicated station** (“Axis Church Radio”) with **one bot** you
can write to in **German or English in the same chat window** — music, status and
announcements work in both languages. Later the station will run as a demo on the
website.

**Rights profile (demo, 2026-09-25):** the bot is deliberately limited — it may
**listen, skip (`weiter`/`next`), take wishes only from the fixed playlist
“GEMA-frei”** and speak announcements (news, weather, feeds, free text up to 240
characters). It **cannot administrate the station** (nothing created, changed,
deleted or restarted): its key belongs to a dedicated AzuraCast role
(`Demo-Bot`, permission “manage station broadcasting” on station 2 only). The
station plays **only** the playlist “GEMA-frei”; the older playlists are switched
off but kept in the library.

**Documentation language:** English — this edition is documented in English only.
**In git:** this edition is kept in its own branch **`webseite`** of the project
repository (`mnauendo/radio-bot`); the main branch `Privat` holds station 1 only.
The complete step-by-step rebuild guide is **`NACHBAU/README.md`**.

---

## 1. What is running now

| Part | Where | Address / ID |
| --- | --- | --- |
| **Station** “Axis Church Radio” | AzuraCast (LXC 106, 192.168.178.33), **station number 2** | Listeners: `http://192.168.178.33/listen/ddd_webseite/radio.mp3` (or `:8010/radio.mp3`); harbour (DJ): port **8015**; shortcode `ddd_webseite` |
| Music | playlist **“GEMA-frei”** (the only enabled list) | **4 tracks** (Mozart, Beethoven, Vivaldi) — replaceable at any time; the older “Rotation” (245 tracks) stays in the library but is switched off |
| **Service** `ddd-radio` | LXC 103 (192.168.178.53) | port **8882** (catalogue, mailbox, announcements) |
| **Bot** | n8n (LXC 103), **four** workflows `DDD-Webseite-…` | test entry `/webhook/ddd-webseite-test` |
| **API key** | restricted role `Demo-Bot` (station 2 only) | `zugangsdaten/api_key.txt`; the earlier admin key is kept as `api_key.txt.bak-2026-09-25` |
| Voice | `aqua` via the voice service (CT 111) | fallback: `de_thorsten` (also speaks English text) |
| Streamer accounts | `aqua` (display name “Aqua”) + `marc` | passwords in `zugangsdaten/` |

**One bot instead of two:** 10 workflows (5 DE + 5 EN) became **5**, two services
(ports 8882 and 8883) became **one**, and two Telegram entries became **one**.
Everything runs on **the same station** (number 2). With the rights profile
(2026-09-25) the administration tool was removed as well — **4 workflows** remain.

**Telegram:** not created yet — the bot runs with a placeholder token and
disabled triggers (section 5). Suggested display name at @BotFather:
`DDD-Webseite Radio (DE/EN)`.

---

## 2. How the bilingual chat works

1. **Input** (`EINGABE_JS`): the language of the message is detected with a
   simple, fast rule (umlauts and German function words versus English ones). The
   field `sprache` (`de`/`en`) travels through the whole run. Button presses and
   typed numbers carry no language — there the **last used** language of the chat
   applies. Voice messages are detected again after transcription (Whisper).
2. **Shortcuts (stage 0, no AI)** understand both languages, e.g.
   `spiele …`/`play …`, `danach …`/`queue …`, `nächster`/`weiter`/`next`/`skip`
   (the **only** station control in the demo — there is no pause, no volume, no
   restart), `was läuft`/`what is playing`, `was gibt es für Meldungen`/`messages`,
   `was Peppiges`/`play some rock`, `2` (selection), `überblick …` (German).
   The matched phrase decides the reply language (`next` → English, `nächster` →
   German).
3. **Tools** (radio) receive the language as a `sprache` field and answer in it —
   including the selection lists (“Several tracks match …” / “Mehrere Titel
   passen …”) and their buttons.
4. **Language model**: analysis and execution understand both languages; the
   execution model is told the language explicitly and answers in it. Internal
   values (`art`, `auftrag`, `ansagen` …) stay German.
5. **Announcements** speak the text they are given — English text is spoken in
   English by the `aqua` voice (verified).

**Deliberately German:** the content (news, weather, feeds — the station’s
sources), the service’s admin paths (playlist menus, the message card sent by the
schedule) and the file/tool names.

**Fixed 2026-09-25:** the status query ("what is playing", and the stage-3 proof of
state) read **station 1** — the workflows now take the station number from the
configuration (`senderId` = 2), so the bot shows *this* station's program. On the same
day the execution model got a stricter language rule: English requests are confirmed
in English ("The announcement has been broadcasted."). Both bots — main station and
demo station — now behave identically in German and English.

---

## 3. Folders and files

| Path | Content |
| --- | --- |
| `zugangsdaten/` | the value files (API key, test key, mailbox key, streamer passwords, Telegram token, `demo-playlist.txt` = name of the demo playlist; empty = wishes locked). The working copy holds real values (700/600) — **never publish**; the publishable copy (`DocOfficial/`) ships placeholders |
| `dienst/` | the `ddd-radio` service (station number via `AZ_STATION_ID=2`), `geheim.env` with the values |
| `werkzeuge/agent-wf-bauen-ddd.py` | workflow generator (fork of `../werkzeuge/agent-wf-bauen.py`) |
| `werkzeuge/bauen.sh` | builds the **four** workflows into `/tmp/ddd-webseite-*.json` |
| `werkzeuge/pruefen.sh` | layout + code + contracts (IDs, language plumbing, texts, demo rights) |
| `werkzeuge/einspielen.sh` | imports the four workflows, **removes the old ten and the former `DDD-Webseite-AzuraCast`**, activates them, puts them into the n8n folder **Sender 2: Axis Church Radio**, restarts n8n |
| `werkzeuge/dienst-einspielen.sh` | deploys `dienst/` to LXC 103, removes the old instances, starts the container |
| `werkzeuge/ausfuehrung-lesen.js` | reads the last execution of a workflow from the n8n database |
| `chat-fenster.html` | the **chat window** (browser page): sends commands to the REST input and shows the answer — replaces the Telegram input (open locally, enter the test key once) |
| `NACHBAU/` | the **complete rebuild guide** (`NACHBAU/README.md`, English): station, service, workflows, Telegram, voice, checks |
| `ANORDNUNG.md` | generated overview of the canvas (4 workflows) |

---

## 4. Usage and test entry

**German commands** behave like the main bot (0.4–2 s). **English commands** run
either as a shortcut (listed above, equally fast) or through the language model
(free sentences like “can you put on some rock”, “announce: …” — 10–50 s
depending on the model).

Test entry (without Telegram): posts a Telegram message as JSON and **answers in
the same request** (same JSON shape as the REST input below); the answer is also
visible in the execution:

```bash
KEY=$(cat DDD-Webseite/zugangsdaten/test-schluessel.txt)
curl -s -X POST "http://192.168.178.53:5678/webhook/ddd-webseite-test?schluessel=$KEY" \
  -H 'Content-Type: application/json' \
  -d '{"message": {"message_id": 1, "chat": {"id": 7333665467, "type": "private"},
       "from": {"id": 7333665467, "first_name": "Test"}, "text": "what is playing right now"}}'

cat DDD-Webseite/werkzeuge/ausfuehrung-lesen.js | ssh -F /media/discData/docs/projects/proxmox-ssh/config ai-server \
  "pct exec 103 -- bash -c 'cat > /tmp/aus.js && docker cp /tmp/aus.js n8n:/tmp/ >/dev/null && \
   docker exec -u node n8n node /tmp/aus.js DDD-Webseite-Bot'"
```

### REST input — commands without Telegram

The bot also takes a plain JSON command over its own webhook and answers **in
the same HTTP request** (`ok`, `antwort`, `tastatur`, `sprache`). No Telegram
token, no chat ID — a valid test key alone opens the bot:

```bash
KEY=$(cat DDD-Webseite/zugangsdaten/test-schluessel.txt)
curl -s -X POST "http://192.168.178.53:5678/webhook/ddd-webseite-rest?schluessel=$KEY" \
  -H 'Content-Type: application/json' \
  -d '{"text": "what is playing right now"}'
# {"ok":true,"antwort":"Now playing: …\nNext: …\nListeners: 0","tastatur":null,"sprache":"en"}
```

* `text` = the command, German or English (same shortcuts, same model paths).
* The key may be in the URL (`?schluessel=…`) or in the body
  (`"schluessel": "…"`) — a wrong key answers “Kein Zugang”.
* **All three answer paths** return JSON: short way, service way (playlists,
  mailbox) and main way. Buttons arrive as data in `tastatur`.
* Slow commands (model runs, announcements) keep the request open — allow a few
  minutes for those.

### Chat window — replaces the Telegram input

`chat-fenster.html` is a ready-made browser chat: open the file (double-click),
enter the address (pre-filled) and the test key **once** (kept locally in the
browser), then type as in Telegram — Enter sends. It talks directly to the REST
input, so it works without Telegram and without the n8n interface. Verified
end to end on 2026-09-25 (German, English and wrong key).

## 5. Setting up Telegram (when the bot should go live)

1. Create one bot at **@BotFather** (suggested: `DDD-Webseite Radio (DE/EN)`) and
   copy the **token**.
2. Store the token: fill `zugangsdaten/telegram-bot-token.txt`, then run
   `bauen.sh` + `einspielen.sh` — **or** enter it directly in n8n in the node
   “Konfiguration”, field `telegram.token`, and save.
3. In n8n create a **Telegram credential** (Credentials → New → Telegram; paste
   the token) and select it in the “Telegram Trigger” node
   (`dddWebseiteTelegram`).
4. **Switch on the disabled triggers**: “Telegram Trigger” and “Zeitplan
   Meldungen” (right-click → remove deactivation). Then **deactivate and
   reactivate** the workflow so the Telegram trigger registers.
5. Operator access: the workflow uses the same operator chat ID as the main bot
   (`staticData.global.erlaubte`); add more IDs there.

## 6. Announcements (voice)

The service uses the dedicated voice **`aqua`** (`TTS_DEFAULT_VOICE`), with the
same loudness chain as the main bot (variant 3). If the voice service is down,
`de_thorsten` takes over — also for English text. Verified: English
announcements of 9.8 s and 10.2 s (on air as streamer **“Axis KI”** — the
account is `aqua`, `live: true`), a German announcement of 9.8 s.

**Demo limits (2026-09-25):** free text announcements are capped at **240
characters** (`demo.ansage_max`); the same text is **not repeated within 90
seconds** (`ANSAGE_SPERRE_SEK` in the service) and every command speaks **exactly
once** (agent step limit 4). News, weather, feeds and the topic overview are
researched and spoken by the service itself — the user needs no special rights
for that. Every announcement carries 5.5 s of lead silence (the harbour swallows
the first seconds on connect) and 1.5 s tail — a short sentence therefore sounds
short.

## 7. Website (later)

* **Player**: embed the listener address, e.g.

  ```html
  <audio controls preload="none"
         src="http://192.168.178.33/listen/ddd_webseite/radio.mp3"></audio>
  ```

* The station is **not publicly reachable yet** — a reverse proxy entry is
  missing (same as the main station; `…:8010` is LAN-only). Then just swap the
  `src`.
* **Rights note**: the demo station plays **only GEMA-free music** from the fixed
  playlist “GEMA-frei” (4 tracks; extend or replace at any time — upload, assign
  to the playlist, rebuild the catalogue; see `NACHBAU/README.md` §3.1). Public
  streaming carries the same obligations as the main station.

## 8. Checks performed (2026-09-25, merged bot)

| Check | Result |
| --- | --- |
| Layout (`anordnung-pruefen.py`) | **0 findings** |
| Code nodes (`code-pruefen.py`) | **0 faulty** |
| Contracts (`pruefen.sh`): four IDs, one service (8882), one test entry, `sprache` travels with every call, German **and** English texts present, **demo rights** (no admin tool, wish endpoint `/request/`, playlist gate, announcement cap) | clean |
| Shortcut probe (30 sentences, German and English, local without n8n) | all as expected |
| DE: “was läuft gerade” | “Jetzt laeuft: … Danach: … Zuhoerer: 0” (1.5 s) |
| EN: “what is playing right now” | “Now playing: … Next: … Listeners: 0” (0.5 s) |
| DE: “spiele Eminem” / EN: “play Guns N' Roses” | selection list **in the matching language**, with buttons (~0.7 s each) |
| Selecting “3” after the English list | “OK: \"Guns N' Roses - Paradise City\" is playing now.” — the station played “Paradise City” |
| EN: “next” | “The next track is starting.” |
| DE: “weiter” (2026-09-25) | “Naechster Titel laeuft an.” — skip works with the restricted key |
| DE: “spiele Mozart” (track is in the playlist) | wish accepted: “OK: … ist als Wunsch eingeplant und laeuft in Kuerze.” — the station played it |
| DE: “spiele Scooter” (not in the playlist) | “Diesen Titel gibt es nicht in der Demo-Playlist.” |
| DE: “sag durch: …” twice in a row | spoken **once**; the second call is suppressed (“… gerade eben schon - ich habe sie nicht wiederholt.”), announcement log 20 → 21 |
| DE: “lies die nachrichten vor” | current news researched and spoken (≈ 24 s, “Tankrabatt”) |
| DE/EN: mailbox | “Im Postfach liegt nichts Offenes.” / “There is nothing open in the mailbox.” |
| DE: “sag durch: …” | spoken (9.8 s), reply “✅ Die Begrüßung wurde erfolgreich im Radio angesagt.” |
| EN: “announce into the stream: …” | spoken (10.2 s), **live: Aqua**, reply “✅ The announcement has been broadcast to the station.” |
| REST input (2026-09-25): wrong key | `{"ok":true,"antwort":"⛔ Kein Zugang. …"}` — access refused |
| REST input: DE “was läuft gerade” | “Jetzt laeuft: … Danach: … Zuhoerer: 1” (`sprache: de`) |
| REST input: EN “what is playing now” | “Now playing: … Next: … Listeners: …” (`sprache: en`) |
| REST input: service way “welche Wiedergabelisten gibt es” | playlist list as JSON — `GEMA-frei` enabled, `default`/`Rotation` switched off |
| Chat window (`chat-fenster.html`, file://) | message in, answer bubble out — full loop verified in a browser |
| After n8n restart | REST webhook re-registers (answer again within seconds) |
| n8n organization (2026-09-25) | the four workflows sit in the folder **Sender 2: Axis Church Radio**; the private bot sits in **Sender 1: Deadline Beats** (scripts set this after every import) |

Importing restarts n8n **once** (~1 minute downtime for all bots); the main bot’s
workflows are unchanged.

**Known edges:** content (news/weather) is German; the model’s English replies
depend on the model (the fast shortcuts do not); administrative requests
(playlists, users, restart) are politely declined — the demo has no rights for
them.

## 9. Rebuilding / changing

The **complete rebuild guide** — station, service, workflows, Telegram, voice,
checks — is in **`NACHBAU/README.md`**. Day-to-day commands (reference
installation):

```bash
cd DDD-Webseite/werkzeuge
bash bauen.sh               # four workflows -> /tmp/ddd-webseite-*.json
bash pruefen.sh             # layout + code + contracts
bash einspielen.sh          # import + activate (restarts n8n)
bash dienst-einspielen.sh   # update the service on LXC 103
```

Edit in **one** place: the `Werte` node of `DDD-Webseite-Konfiguration` —
addresses, keys, model, all task texts **and the demo values** (`demo.playlist`,
`demo.ansage_max`; the playlist name comes from `zugangsdaten/demo-playlist.txt`
at build time). The generator lives in `werkzeuge/agent-wf-bauen-ddd.py` (based on
`../werkzeuge/agent-wf-bauen.py`).

For handing out: `python3 werkzeuge/veroeffentlichung-bauen.py` builds a
placeholder copy into `DocOfficial/` (English, without real values).

## 10. Open items

* Create the Telegram bot and enter the token (section 5).
* Reverse proxy for the public listener address (section 7).
* Curate the playlist “GEMA-frei” as desired (upload → assign → rebuild the
  catalogue; `NACHBAU/README.md` §3.1). More GEMA-free tracks can be added at any
  time.
* Rare English special cases (e.g. “overview of …”) run through the model; their
  content (news/weather) stays German.
* n8n's own chat window (chat hub) is not wired up; the REST chat window
  (`chat-fenster.html`) covers the need — the hub can be added later on top of
  the same REST answer paths.
