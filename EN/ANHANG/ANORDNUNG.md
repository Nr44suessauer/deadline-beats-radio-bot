# Canvas layout of the workflows (generated)

This file is **generated**, not maintained by hand: it lists, per frame, its
heading and description, and below that every node with its note and position.
It is built from the English workflow copies in `NACHBAU/ablaeufe-laufend/`.

Layout check (same check as the German edition): **0 finding(s)**. The check looks at
nodes without a frame, nodes in two frames, nodes sticking out of their frame,
overlapping frames and nodes without a note — the target is **0 findings**.

Stand: 24 Sep 2026 (English edition). Regenerate: `python3 EN/werkzeuge/anordnung-en.py
EN/NACHBAU/ablaeufe-laufend/*.json`

## Radio - Telegram Agent (EN)

83 nodes in 10 frames. Every node carries its explanation as a note below its name.

### Voice message (own branch above)  ·  `Note voice message`

Fetch the file, convert it, recognise it (Whisper on the ai server). Recognised: on to **Access** - otherwise short feedback.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Fetch file` | Fetch the voice message's path from Telegram. | -3800, -2060 |
| `Download audio` | Download the file (in tests via stimme.test_url). | -3580, -2060 |
| `Convert` | Speech recognition on the ai server (whisper.cpp, MI50). | -3360, -2060 |
| `Transcript` | Pass on the text only - interpretation happens later. | -3140, -2060 |
| `Understood?` | No = nothing understood, short feedback. | -2920, -2060 |
| `Heard text` | Shows what was understood, for control. | -2700, -2060 |

### Entry and access  ·  `Note entry`

Two entry points; only the operator gets through (list `erlaubte`). The short paths send via **Send (short note)**.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Telegram Trigger` | Entry in the operator chat: messages and button presses. | -4200, -1380 |
| `Test input` | For testing only: accepts a Telegram message as JSON. | -4200, -1060 |
| `Configuration` | All values in one place | -4200, -700 |
| `Plan switch?` | Message or schedule? | -4200, -520 |
| `Input` | Message, voice, button press | -3980, -1220 |
| `Voice message?` | Yes = voice message, its own branch above. | -3760, -1220 |
| `Access` | Operator only | -3200, -1220 |
| `No access` | Short refusal. | -2980, -1500 |
| `Allowed?` | No = refusal, the run ends. | -2980, -1220 |
| `No text` | Short question back for messages without text. | -2100, -700 |
| `Send (short note)` | Short path, same call | -1880, -700 |

### Services: playlists and messages  ·  `Note services`

Button or text -> **Service kind** -> **Message?** -> module in the radio-tts service. Lists remember the selection, messages arrive as a card with buttons. Text messages continue via **Text present?** into the analysis.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Service kind` | Button or text for a service? | -2760, 578 |
| `Service?` | Yes = its own service branch | -2540, 578 |
| `Message?` | Message or playlist? | -2320, 838 |
| `Playlist service` | Module playlist.py in the service | -2320, 1098 |
| `Message service` | Module meldungen.py in the service | -2320, 1358 |
| `Text present?` | No = button, image or sticker without text. | -2100, 838 |
| `Service reply` | Prepare text and buttons | -2100, 1358 |
| `Task` | Context for the analysis | -1880, 838 |
| `Service send` | sendMessage / editMessageText | -1880, 1358 |
| `Send failed?` | Yes = send a new message | -1660, 1358 |
| `Service fallback send` | Second attempt via sendMessage | -1440, 1358 |
| `End` | Output of the service branch | -1220, 1358 |

### Inbox (search bot -> moderator)  ·  `Note inbox`

Every 5 minutes: fetch new messages and present them as a card with buttons. **Offer message** marks them as offered - no second offer.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Schedule messages` | Every 5 minutes: poll the inbox. | -2760, 1768 |
| `Fetch messages` | Fetches new messages from the inbox (nur_neue=1 = not yet offered). | -2540, 1768 |
| `Message present?` | No = nothing new, the run ends here. | -2320, 1768 |
| `Message card` | Build a card with buttons | -2100, 1768 |
| `Offer?` | Only on the schedule path | -1880, 1768 |
| `Offer message` | Mark as offered | -1660, 1768 |

### Stage 0 and stage 1: understand and plan  ·  `Note analysis`

**Short way?** recognises simple commands without a model, **Shortcut?** sends them straight into execution. Otherwise **Plan** splits the instruction into single commands.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Short way?` | Stage 0: without language model | -1800, -128 |
| `Shortcut?` | Yes = execute directly | -1580, -128 |
| `Plan` | Stage 1: plan from the text | -1360, -128 |
| `Remember plan` | Counts the attempts (max. 3) | -1360, 132 |
| `Plan reply` | Extracts the model's text. | -1140, -128 |
| `Plan again?` | Yes = new attempt, no = fallback via execution. | -1140, 132 |
| `Plan present?` | Empty = plan once more | -920, -128 |
| `Read commands` | One item per command | -680, -128 |
| `Command present?` | Empty = straight to the reply | -460, -128 |

### Stage 2: execution in the loop  ·  `Note execution`

One command per pass - output 0 = done, output 1 = continue. Three paths: fallback without model, fixed controls, agent with tools.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Loop` | 0 = done, 1 = continue | -700, 960 |
| `Direct or AI?` | Yes = fallback path without model | -420, 960 |
| `Fallback tool` | Tool plays by itself | -140, 700 |
| `Controls?` | Yes = fixed addresses | -140, 960 |
| `Inbox?` | Yes = question about the inbox | -140, 1220 |
| `Overview?` | Yes = source overview | -140, 1480 |
| `Fallback reply` | Writes the output into the store, then back into the loop. | 80, 700 |
| `Short controls` | Next track, start/stop/restart - fixed addresses, no model. | 80, 960 |
| `Fetch inbox` | Fetch open messages | 80, 1220 |
| `Execute` | One command per pass | 80, 1480 |
| `Fetch overview` | Fetch the piece and speak it | 80, 1740 |
| `Language model execute` | Language model for 'Execute' (Ollama via the OpenAI interface). | 80, 2000 |
| `Controls reply` | Phrases the station's reply. | 300, 960 |
| `Inbox reply` | List as text | 300, 1220 |
| `Collect result` | Writes the output into the store, then back into the loop. | 300, 1480 |
| `Overview reply` | Writes the output into the store, then back into the loop. | 300, 1740 |

### Tools (sub-interfaces of the agent)  ·  `Note tools`

One node per tool; it calls the tool workflow via `executeWorkflow`. File paths and station calls stay there - the model never sees them.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Tool title search` | Tool `titel_suchen` for Execute and Retry work. | 740, 2200 |
| `Tool direction search` | Tool `richtung_suchen` for Execute and Retry work. | 940, 2200 |
| `Tool what's playing` | Tool `was_laeuft` for Execute and Retry work. | 1140, 2200 |
| `Tool Azura addresses` | Tool `azura_endpunkte` for Execute and Retry work. | 1340, 2200 |
| `Tool Azura call` | Tool `azura_aufruf` for Execute and Retry work. | 1540, 2200 |
| `Tool Azura overview` | Tool `azura_ueberblick` for Execute and Retry work. | 1740, 2200 |
| `Tool messages` | Tool `meldungen`: inbox and announcements. | 1960, 2200 |
| `Tool research` | Tool `recherche`: weather, news, feed, short info. | 2180, 2200 |

### Stage 3: check, retry and reply  ·  `Note check`

**Fetch status** and **Fetch queue** provide evidence of the station state, **Check** judges each command. **Retry?** starts exactly one second attempt per command. **Build reply** summarises and builds the buttons, **Send** posts via HTML.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Fetch status` | What is playing - evidence for the check. | 880, 960 |
| `Fetch queue` | What is queued - evidence for the check. | 1100, 960 |
| `Commands and status` | Outputs + station state | 1320, 960 |
| `Check?` | No = judgement by rules | 1540, 960 |
| `Check` | Stage 3: verdict per command | 1540, 1220 |
| `Check reply` | Extracts the model's verdict. | 1760, 1220 |
| `Read check` | ok and grund per command | 1980, 960 |
| `Retry?` | Yes = second attempt | 2200, 960 |
| `Loop 2` | Follow-up pass | 2420, 960 |
| `Retry work` | Second attempt per command | 2420, 1220 |
| `Language model retry` | Language model for 'Retry work'. | 2420, 1480 |
| `Collect follow-up` | Writes the second attempt's output into the store. | 2640, 1220 |
| `Build reply` | Summarise + buttons | 2900, 960 |
| `Reply` | Prepares the text for Telegram (HTML, without asterisks). | 3120, 960 |
| `Send` | sendMessage (HTML) | 3340, 960 |

### Radio - Telegram Agent (Deadline Beats)  ·  `Note overview`

What the bot can do: song requests, direction requests, skip/pause/status, playlists, inbox, research (weather, news, RSS) and announcements on air. Everything comes from Telegram and goes back there. The path of a message: entry -> stage 0/1 analysis -> stage 2 execution -> stage 3 check -> reply. Voice messages run through Whisper at the top, services and inbox hang off to the side. Each node carries its purpose as a note under its name, each frame explains one stage. Frame colours: 1 voice message | 2 entry | 3 services | 4 inbox | 5 stage 0+1 | 6 stage 2 + tools | 7 stage 3 + reply Created by werkzeuge/agent-wf-bauen.py - never change by hand. Change: agent-patchen.sh --inhalt ... then agent-einspielen-nur.sh. Docs: README.md sections 8 to 12 and werkzeuge/README.md.

*(overview box without nodes)*

### Radio - Telegram Agent  ·  `Note docs`

The bot: Telegram entry -> stage 0/1 (understand and plan) -> stage 2 (execute) -> stage 3 (reply). The plan is the source of the layout: werkzeuge/agent-wf-bauen.py (ANORDNUNG, BEREICHE, KURZNOTIZ). Change: agent-patchen.sh --aufraeumen -> agent-einspielen-nur.sh /tmp/radio-agent-neu.json -> docker restart n8n Check: anordnung-pruefen.py (0 findings), code-pruefen.py (0 faulty code nodes), DOKU/BETRIEB.md Description: README.md, DOKU/HANDBUCH.md, DOKU/HANDBUCH.md, DOKU/BETRIEB.md, DOKU/BETRIEB.md, DOKU/BETRIEB.md, DOKU/BAU.md Picture by picture: ANHANG/n8n-oberflaeche.html  (project folder Ai_Radio_Moderator_Bot)

*(overview box without nodes)*

## Tool - Radio (EN)

17 nodes in 7 frames. Every node carries its explanation as a note below its name.

### Switches  ·  `Note W switches`

Direction, state or title search - one of three.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Entry` | Tool fields: suchtext, richtung, frage, einreihen. | -900, 0 |
| `Configuration` | All addresses, keys and task texts (Configuration workflow). | -900, 260 |
| `Direction?` | Yes = mood/genre/decade -> fetch suggestions and play the first one. | -660, 0 |
| `Status only?` | Yes = question about the programme, no search. | -420, 0 |

### Branch: direction  ·  `Note W direction`

Mood, genre or decade from the catalogue service.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Search direction` | Catalogue service by mood, genre or decade. | -420, -480 |
| `Prepare suggestions` | Turns the suggestions into a first track or a list. | -180, -480 |

### Branch: title search  ·  `Note W search`

Catalogue service (fuzzy) and the station's full-text search.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Smart search` | Fuzzy search in the catalogue service (typo tolerant). | -420, 688 |
| `Station search` | Station full-text search as a second source. | -180, 688 |
| `Prepare hits` | Combines hits from both sources into a short list. | 60, 688 |

### Branch: what's playing  ·  `Note W status`

Only the state - the return value is the text.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `NowPlaying` | What is playing, what comes next, how many listeners. | -420, 1116 |
| `Prepare status` | Phrases the state as text (the tool's return value). | -180, 1116 |

### Playback  ·  `Note W playback`

Without a path nothing is inserted - then it stays a selection list. With a path: first clear the interrupting queue, then insert now or at the back.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Hits present?` | Yes = there is a track that should play. | 540, 0 |
| `Queue it?` | Yes = only queue it, do not interrupt. | 780, 0 |
| `Clear queue` | Clears the station's interrupting queue. | 1020, -260 |
| `Insert now` | Inserts the track into the interrupting queue right away. | 1260, -260 |
| `Insert after` | Appends the track after the current one. | 1260, 180 |

### Output  ·  `Note W output`

The tool workflow ends here - the text goes back to the agent.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Result` | Output node: the tool workflow ends here. | 1700, 0 |

### Tool - Radio  ·  `Note docs`

Sub-interface of the agent for music: switches, title search, direction, state, playback. It is called through the agent's tool nodes (Tool title search etc.). The plan is the source: werkzeuge/agent-wf-bauen.py (W_ANORDNUNG, W_BEREICHE). Change/check like the agent; description: DOKU/HANDBUCH.md, DOKU/HANDBUCH.md, ANHANG/n8n-oberflaeche.html

*(overview box without nodes)*

## Tool - AzuraCast (EN)

17 nodes in 5 frames. Every node carries its explanation as a note below its name.

### Switches  ·  `Note AZ switches`

Look up addresses, call an endpoint, or give an overview.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Entry` | Tool fields: suche, methode, pfad, koerper, bestaetigt, frage. | -900, 0 |
| `Configuration` | All addresses, keys and task texts (Configuration workflow). | -900, 260 |
| `Look up addresses?` | Yes = look up addresses of the station API. | -660, 0 |
| `API call?` | Yes = call an endpoint of the station. | -420, 0 |

### Branch: addresses  ·  `Note AZ addresses`

Search the catalogue service directory for addresses.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Fetch description` | Fetch the address directory from the catalogue service. | -420, -480 |
| `Find addresses` | Short list of matching addresses with their fields. | -180, -480 |

### Branch: call  ·  `Note AZ call`

**Guard** checks method and path; changes only with `bestaetigt: true`. Two steps: return a dry run or actually call.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Guard` | Checks method and path - write access only with bestaetigt=true. | 300, 0 |
| `Execute?` | Yes = call, no = return a dry run. | 540, 0 |
| `Read only?` | Yes = GET (read), no = change (POST/PUT/DELETE). | 780, 0 |
| `Dry run` | Shows what the call would do, without changing anything. | 780, 560 |
| `Read` | Reads from the station. | 1020, 220 |
| `Write` | Changes the station - only after explicit confirmation. | 1020, 460 |
| `Call result` | Station response, summarised briefly. | 1260, 0 |

### Branch: overview  ·  `Note AZ overview`

Mounts, broadcast backend, output and playlists in one text.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Mounts` | Mounts and whether broadcast backend and output are running. | -420, 1020 |
| `State` | State of broadcast backend and output. | -180, 1020 |
| `Playlists` | Playlists with track counts. | 60, 1020 |
| `Overview` | Summarises the overview as text. | 300, 1020 |

### Tool - AzuraCast  ·  `Note docs`

Sub-interface for the station: look up addresses, call an endpoint, give an overview. The addresses come from the station's OpenAPI description (263 endpoints). The plan is the source: werkzeuge/agent-wf-bauen.py (W_ANORDNUNG_AZ, W_AZ_BEREICHE). Change/check like the agent; description: DOKU/HANDBUCH.md, ANHANG/n8n-oberflaeche.html

*(overview box without nodes)*

## Tool - Messages (EN)

14 nodes in 6 frames. Every node carries its explanation as a note below its name.

### Switches  ·  `Note M switches`

Research, announcement, discard or speech text - the task decides. Each switch checks one field of the tool.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Entry` | Tool fields: auftrag, kennung, text, art, wort, ansagen. | -900, 120 |
| `Configuration` | All addresses, keys and task texts (Configuration workflow). | -900, 380 |
| `Research?` | Yes = research (art=wetter, nachrichten, rss or wikipedia). | -660, 120 |
| `Speak?` | Yes = speak an announcement (auftrag ansagen or text). | -660, 380 |
| `Free text?` | Yes = free text, no = message from the inbox. | -420, 160 |
| `Discard?` | Yes = set the message aside as discarded. | -420, 620 |
| `ID?` | Yes = show the speech text, no = list open messages. | -420, 880 |

### Research  ·  `Note M research`

Fetch weather, news, feed or a short info, file it as a message and announce it.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Fetch research` | Fetches the data, files it as a message and announces it when ansagen=true. | 400, -140 |

### Announcements  ·  `Note M announcement`

Speak free text or a stored message live on air.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Free announcement` | Speaks free text live on air. | 400, 324 |
| `Announce message` | Speaks a stored message live on air. | 400, 544 |

### Inbox  ·  `Note M inbox`

List open messages, show the speech text, or discard a message.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Discard message` | Marks the message as discarded. | 400, 972 |
| `Fetch speech text` | Shows the text the moderator would speak. | 400, 1232 |
| `Fetch open ones` | Open messages (important ones first). | 400, 1492 |

### Output  ·  `Note M output`

The tool workflow ends here - the text goes back to the agent.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Result messages` | Output node: the tool workflow ends here. | 900, 620 |

### Tool - Messages  ·  `Note docs`

Sub-interface for announcements and the inbox: research, free announcement, speak/discard a message. Speaks via the radio-tts service (Piper + DJ mount), files messages in the inbox. The plan is the source: werkzeuge/agent-wf-bauen.py (W_MELD_ANORDNUNG, W_MELD_BEREICHE). Change/check like the agent; description: DOKU/HANDBUCH.md §1.3, DOKU/HANDBUCH.md

*(overview box without nodes)*

## Radio - AI Moderator (EN)

19 nodes in 7 frames. Every node carries its explanation as a note below its name.

### Entries  ·  `Note entries`

Started by hand, by form or from outside - everything runs into the same chain.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Manual` | Start by hand (test run). | -660, -140 |
| `Form` | Start via the n8n form: title, request text, voice. | -660, 40 |
| `Webhook` | Start from outside (schedule or another tool). | -660, 260 |

### Context  ·  `Note context`

What is playing, and what happened last? This is the basis for the moderation text.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Fields` | Collect inputs: title, request text, voice, announcement yes/no. | -408, 40 |
| `Now playing` | What is playing on the station right now? (AzuraCast) | -208, 40 |
| `Research` | Collect messages and context for the moderation. | -8, 40 |

### Text and voice  ·  `Note text and voice`

Out of the context comes a speech text, and out of that a finished file.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Moderation text` | Have the language model (Ollama) create the speech text. | 240, 40 |
| `Clean text` | Prepare the speech text: links, emoji, abbreviations, sentence boundary. | 440, 40 |
| `Voice` | Generate speech (Piper in the radio-tts service). | 640, 40 |
| `File name` | Build the announcement's file name. | 840, 40 |

### Output  ·  `Note output`

Either speak live (briefly interrupts the programme) or upload (then plays as its own track).

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Mode` | Yes = speak live, no = upload. | 1088, 40 |
| `Speak live` | Speak the announcement live into the DJ mount. | 1308, -15 |
| `Upload` | Upload the announcement as a track (path without interruption). | 1308, 160 |

### Follow-up  ·  `Note follow-up`

After the upload: wait, find the track in the archive, match the request and submit it.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Wait` | Wait until the station has processed the track. | 1556, 160 |
| `Find title` | Search the archive for the freshly uploaded track. | 1748, 160 |
| `Match` | Match the request and the found track. | 1956, 160 |
| `Submit request` | Submit the request to the station. | 2148, 160 |
| `Reply` | Build the reply for the caller. | 2356, 40 |

### Old helpers  ·  `Note old helpers`

Remains of the first edition - not connected, kept as a reminder.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Choose hit` | Old helper: pick the search's first hit (no longer connected). | 780, 1056 |

### Radio - AI Moderator (archive)  ·  `Note docs`

First edition of the moderation: create text, speak it, put it on the station. NOT in operation - the live agent (RadioAgentBot) moderates via the radio-tts service. Frames and labels: werkzeuge/archiv-rahmen.py (not part of the builder). Description: DOKU/BAU.md, DOKU/HANDBUCH.md, ANHANG/n8n-oberflaeche.html (section 16).

*(overview box without nodes)*

## Configuration - all values (EN)

2 nodes in 2 frames. Every node carries its explanation as a note below its name.

### Central values  ·  `Note centre`

All addresses, keys and task texts live here. Only the **Values** node is edited - then save, no restart.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Entry` | — (note field only) | -1280, 0 |
| `Values` | — (note field only) | -1000, 0 |

### Configuration - all values  ·  `Note docs`

ONE place for the whole bot: addresses, keys, model, task texts. Only the 'Values' node (code) is edited. Saving is enough, no restart. All four workflows fetch the values at start via their 'Configuration' node. Change: werkzeuge/agent-wf-bauen.py (KONFIG) -> agent-einspielen-nur.sh

*(overview box without nodes)*

## Voices from Films (EN)

20 nodes in 3 frames. Every node carries its explanation as a note below its name.

### Start  ·  `Note 214`

**Form** (WEB) or **Webhook** (API). Fields: series/film, dataset name, episodes, separate speakers.

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Form` | WEB form to start. (note field only) | -1100, -240 |

### Search and start  ·  `Note 566`

`/finden` searches the library; exactly one hit starts `/extrahieren` (cutting + Demucs + speaker clustering in the RVC container).

*(overview box without nodes)*

### Wait and report  ·  `Note 132`

Poll `/job` every 45 s (max. 60 min), result via Telegram. The RVC training itself then runs in Applio (WebUI).

| Node | Explanation (note on the node) | Position |
| --- | --- | --- |
| `Running?` | No = send a message. (note field only) | 680, -240 |
| `Wait` | Wait 45 seconds. (note field only) | 900, -240 |

### Without a frame

`Webhook`, `Fields`, `Inputs ok?`, `Find`, `Hits`, `One hit?`, `Start`, `Reply`, `Job`, `Status`, `Done?`, `Abort?`, `Telegram result`, `Telegram timeout`, `Telegram failed start`, `Telegram notice`, `End`
