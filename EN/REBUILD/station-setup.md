# Setting Up the Station (AzuraCast)

The bot works with **any** AzuraCast station (tested with 0.23.4) if the following points are set up. The values of the running station are provided as examples.

---

## 0. Install AzuraCast (if none is running yet)

The bot works with a **finished** station — if you do not have one, set it up **before**
steps 1–8. Official way from the AzuraCast documentation
(<https://docs.azuracast.com/>, the original runs 0.23.4 on Debian 12):

```bash
mkdir -p /var/azuracast && cd /var/azuracast
curl -fsSL https://raw.githubusercontent.com/AzuraCast/AzuraCast/main/docker.sh > docker.sh
bash docker.sh install        # asks for port, account, password, time zone
```

| Item | Value in the original |
| --- | --- |
| Program and data | `/var/azuracast` (compose file, `azuracast.env`, `.env`) |
| Music | separate folder, bind-mounted into the container (original `/mnt/Content`, 15 TB disk) |
| Ports | **80/443** UI, **8000** listener stream, **8005–8496** per station/mount (includes the DJ port), **2022** SFTP, **9000** |
| Account | the one created during installation (log in on the UI) |
| Console | `docker exec -it azuracast azuracast_cli list` — e.g. `azuracast:account:login-token <mail>` (one-time login link), `radio:restart` |

**Verify — only then continue:**

```bash
curl -s http://<station-ip>/api/status | head -c 120      # {"online":true,…}
curl -s http://<station-ip>/api/nowplaying | head -c 120  # station, title, listeners
```

Then continue with §1 (station, mount, streamers) and §7 (**create the API key**, format
`identifier:checksum`) — the key is needed later as `AZ_KEY` in the service. Credentials
and addresses belong in your own access data (guide: `credentials.md`).

---

## 1. Create the Station

| Setting | Example Value | Notes |
| --- | --- | --- |
| Name | `Deadline Beats` | free |
| Short Name (shortcode) | `deadline_beats` | determines the stream address |
| Time Zone | `UTC` | free |
| Broadcast (backend) | `liquidsoap` | **Requirement** — here the DJ port is attached |
| Output (frontend) | `icecast` | Listener stream |
| AutoDJ | enabled | without AutoDJ there is no rotation |
| Crossfade | 2 s (`normal`) | original |

**Public Addresses** (example):
`http://192.168.178.33/listen/deadline_beats/radio.mp3`,
Listener frontend on port **8000**, management interface `/api`.

---

## 2. Mount (Listener Output)

| Field | Example |
| --- | --- |
| Path | `/radio.mp3` |
| Format / Bitrate | `mp3`, 192 kbps |
| Default Mount | yes |

One is sufficient; the bot does not use it directly (it controls via the API and speaks through the DJ port).

---

## 3. Streamer Access (for Live Moderation)

**This is the most important point.** Moderation speaks through the **DJ port**:

| Setting | Value |
| --- | --- |
| Streamer User | **two accounts:** one for the operator (e.g., `operator`, display name "operator") and one for the bot (original: `deine-stimme`, display name **"YOUR-VOICE"**) |
| Password | choose yourself (bot account in `secret.env` as `LIVE_USER`/`LIVE_PASSWORD`) |
| Active | **yes** (both) |
| Limit to times (`enforce_schedule`) | **no** — otherwise announcements only speak at certain times |
| Allow DJ access (`enable_streamers`) | **yes** — in the station settings |

Port: **8005**, Mount **`/`**, Protocol `PUT` with `Content-Type: audio/mpeg`, Basic-Auth from user + password.

**Why a separate bot account?** The station shows the **display name of the logged-in streamer account** during live speaking. With a separate account for the service (original: `deine-stimme`), it shows **"YOUR-VOICE"** in the station interface and player during announcements — the manual DJ access of the operator runs separately under his own name (Details: `credentials.md` §5).

**Attention (from practice):** without `enable_streamers = true` the port responds with 401 and the announcement remains silent. The bot does not check this in advance — if in doubt, check in the station settings.

---

## 4. Requests and Rotation

| Setting | Example Value | Why |
| --- | --- | --- |
| Allow Requests (`enable_requests`) | yes | for the request path |
| Request Cooling Time (`request_threshold`) | **0 minutes** | otherwise requests are rejected if the title played "too recently" |
| Playlists | `List A` (Type `default`, active, `include_in_requests`) | this is the **rotation** — only titles in it play automatically |
| Everything Else in the Archive | not in a list | serves as a request and search pool |

The bot plays requests via `PUT /api/station/1/files/batch` with
`{"do":"immediate"}` (immediately, interrupting) or `{"do":"queue"}` (queue). Before an immediate request, it clears the interrupting queue.

---

## 5. Media

1. Place music in the media folder (original: `/mnt/Content/Music`, in container
   `/data`).
2. Let AzuraCast import it under **Media** (or `azuracast_cli media:reprocess`).
3. The bot needs **relative paths** (the API provides them) — no changes required.

**Never move files via `mv` while AzuraCast is running** — the synchronization runs via
`md5(Pfad)`, moving files deletes the dataset along with playlist associations. For reorganization, use the API (`files/batch` with `do=move`).

---

## 6. Settings Used by the Bot

| Setting | Value | Effect |
| --- | --- | --- |
| `enable_requests` | yes | Desired path via API |
| `request_threshold` | 0 | No cooldown period |
| `enable_streamers` | yes | Live moderation possible |
| Time zone `UTC` or Europe/Berlin | – | Display only |

Verify with:

```bash
curl -s -H "X-API-Key: <key>" http://<sender>/api/admin/station/1 \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print({k: d[k] for k in ('enable_requests','request_threshold','enable_streamers')})"
```

---

## 7. Users and Roles

The bot manages users, roles, settings, and backups **via the API**
(Tool `azura_aufruf`). For replication, an administrator account
(email + password) and an API key for this account are sufficient.

---

## 8. Checklist After Setup

```bash
# 1. is the station running?
curl -s http://<sender>/api/nowplaying/1 | head -c 200

# 2. is the DJ port open? (expect: 401 without credentials, not "connection refused")
curl -s -o /dev/null -w "%{http_code}\n" -X PUT http://<sender>:8005/ --data-binary ""

# 3. are the settings correct?
curl -s -H "X-API-Key: <key>" http://<sender>/api/admin/station/1 \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['enable_streamers'], d['request_threshold'])"
# erwartet: True 0

# 4. playlist present and active?
curl -s -H "X-API-Key: <key>" http://<sender>/api/station/1/playlists \
  | python3 -c "import json,sys; print([(p['name'], p['type'], p['is_enabled']) for p in json.load(sys.stdin)])"
```

Then fill the catalog and make a test announcement (see `README.md`, Step 7).
