# Access Data — What is Needed and How it is Created

**The values are now in the folder `credentials/`** (directory 700, files 600, with `OVERVIEW.md`). This file here is the **guide**: what is needed, how it is created, and where it belongs — also for the case that the access data needs to be renewed (after a while, one should change Telegram tokens, sender keys, and DJ passwords).

---

## 1. Overview

| Access | Purpose | Where Created | Where It Belongs |

| --- | --- | --- | --- |

| **Telegram Bot Token** | the bot in Telegram | @BotFather in chat (`/newbot`) | in the workflows (during build: environment variable `TG_TOKEN`) |

| **Own Chat ID** | operator identification | `@userinfobot` or the Telegram API | static workflow data (`erlaubte`), set with `erlaubte-setzen.py` |

| **AzuraCast API Key** | everything at the station | AzuraCast → Profile → API Key | workflows (`AZ_KEY`) + environment variable for scripts |

| **Liquidsoap/streamer passwords** | live announcements to the station (and manual sending) | AzuraCast: **two** streamer accounts to create — one for the operator (e.g., `operator`), one for the bot (e.g., `deine-stimme`, display name "YOUR-VOICE") | bot account as `LIVE_USER`/`LIVE_PASSWORD` in `/opt/radio-tts/secret.env` |

| **Mailbox Key** | accept messages from outside | self-generated (32 characters) | `radio/meldung-schluessel.txt` + `secret.env`/`X-Meldung-Schluessel` |

| **Key of the Test Input** | test runs via webhook | self-generated | `radio/bot-test-schluessel.txt` + static workflow data |

| **n8n login** | UI/project | at first start | login data in n8n |

| **SSH/Proxmox-Zugang** | container management | own infrastructure | not part of the bot |

**All self-generated keys** (mailbox, test input) are long random character strings, e.g., `python3 -c "import secrets;print(secrets.token_urlsafe(24))"`.

---

## 2. Service Environment File (`/opt/radio-tts/secret.env`)

Template: `service/secret.env.template` — copy, fill out, set permissions to 600.

```bash
cp service/secret.env.template /opt/radio-tts/secret.env
chmod 600 /opt/radio-tts/secret.env
# fill in, then: cd /opt/radio-tts && docker compose up -d
```

Included are: `LIVE_HOST`, `LIVE_PORT`, `LIVE_MOUNT`, `LIVE_USER`,
`LIVE_PASSWORD` (DJ port) as well as the volume control settings (`TTS_*`).

---

## 3. AzuraCast API Key

1. Log in to AzuraCast → Profile → **API Key** → create a new key.
2. The format is `<identifier>:<verifier>` (e.g., `a1b2c3d4e5f6a7b8:…`) — this
   value is the `AZ_KEY` during build.
3. Without UI: the key is in the table `api_keys` (identifier = first
   16 characters, verifier = sha512 of the second part).

With this, the bot can: read (public), write (everything the API allows). The **permissions** are derived from the user account of the key.

---

## 4. Telegram

1. `@BotFather` → `/newbot` → Token (format `123456789:AA…`).
2. Write to the bot in Telegram once (so the chat exists).
3. Determine your own chat ID and enter it in the operator list:
   ```bash
   cd werkzeuge && python3 erlaubte-setzen.py <chatId>
   ```
4. Command menu (optional): `bash telegram-menu.sh`.

---

## 5. DJ Port (Live Announcements)

In AzuraCast: **Radio → Streamer** **two** access points to create — one for the
operator (manual sending) and one for the bot. The **display name of the bot account**
is what the station shows when speaking (Original: user `deine-stimme`, display name
**"YOUR-VOICE"**). The port lies on port **8005**, mount `/`. The values of the **bot account**
move to `secret.env` (`LIVE_USER`, `LIVE_PASSWORD`).

In the original additionally under `/var/azuracast/dj_passwort.txt` (operator) and
`/var/azuracast/bot_streamer_passwort.txt` (bot; both 600) in the AzuraCast container
— pure convenience.

---

## 6. Static Workflow Data

The import overwrites the static data in n8n. After each import check/set:

```bash
python3 erlaubte-setzen.py <chatId>     # Betreiberliste
python3 bot-data-set.py             # test key and base state
python3 static-data-patch.py      # keep existing data, only additions
```

The **Test Input** (Webhook `YOUR-WEBHOOK-PATH`) requires `?schluessel=<Wert>`; this value is in the static data.

---

## 7. Where the Values Are in the Original

| File / Location | Content |

| --- | --- |

| `radio/meldung-schluessel.txt` (600) | Key for the mailbox (`X-Meldung-Schluessel`) |

| `radio/bot-test-schluessel.txt` (600) | Key for the test input |

| `radio/azuracast-zugang.txt` (600) | Collection file: Web login link, stream addresses, DJ access (operator + Bot/YOUR-VOICE), API key |

| `/root/azuracast-zugang.txt` on the data server | the same collection file |

| `/opt/radio-tts/secret.env` (LXC 103) | DJ harbor and volume control values |

| n8n login data | Telegram token and sender key are embedded in the workflow nodes |

| `/var/azuracast/api_key.txt` (Container, 600) | API key (fallback) |

| `/var/azuracast/dj_passwort.txt` (Container, 600) | Password for the operator DJ access (fallback) |

| `/var/azuracast/bot_streamer_passwort.txt` (Container, 600) | Password for the Bot-/Ansagekontos `deine-stimme` |

**Why this is in the workflows:** n8n stores HTTP nodes with their headers —
the sender key and the Telegram token are therefore in the JSON of the workflow. This is
the reason why backups of this workflow (600) are treated as secrets and why **masked versions must never be deployed** (see
`../DOCS/OPERATIONS.md`, section 1).