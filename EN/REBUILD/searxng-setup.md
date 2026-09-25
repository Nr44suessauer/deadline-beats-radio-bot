# Custom Search Engine for the Bot (SearXNG in LXC 108)

As of 2026-09-21. This guide sets up the **custom search engine** used by the
research service for "normal web pages." Without it, the service queries
DuckDuckGo and Bing directly — and these block computers without logging in
(see `../DOCS/OPERATIONS.md` §14: DuckDuckGo 202, Mojeek Captcha, Ecosia 403).

| Point | Value |

| --- | --- |

| Container | **LXC 108 "SearXNG"** on the ai-server (`pct`) |

| System | Debian 12 (bookworm), 2 cores, **1024 MB**, 10 GB disk, `nesting=1`, `onboot=1` |

| Address | **http://192.168.178.26:8888** (DHCP address of Fritz!Box) |

| Service | `searxng.service` (systemd, calls `uwsgi --ini /etc/uwsgi/apps-available/searxng.ini`) on `0.0.0.0:8888`, plus `redis-server` |

| Service User | `searxng` (uid 999) |

| Source | `/usr/local/searxng/searxng-src` (git, github.com/searxng/searxng) |

| Python Environment | `/usr/local/searxng/searx-pyenv` |

| Settings | `/etc/searxng/settings.yml` |

| Entry in the Bot | `RECHERCHE_SEARX_URL=http://192.168.178.26:8888` |

---

## 1. Container

```bash
ssh -F proxmox-ssh/config ai-server
pct set 108 -memory 1024 -swap 1024 -onboot 1     # 512 MB is tight for uWSGI
# IMPORTANT: no IPv6 DHCP - otherwise the container hangs for minutes at start in
# dhclient solicits (measured: 68 s wait per attempt) and all services wait.
pct set 108 -net0 name=eth0,bridge=vmbr0,firewall=1,ip=dhcp,ip6=manual,type=veth
pct start 108
pct exec 108 -- sh -c 'ip -4 addr show eth0 | grep inet; python3 -V; free -m | head -2'
```

Expected: Debian 12, Python 3.11, address `192.168.178.26`.
**Note:** The address is obtained via DHCP. If it changes, it must be updated in `RECHERCHE_SEARX_URL`
in the service (or reserve an address in the router for the MAC address of the container).

## 2. Packages and Service User

```bash
pct exec 108 -- sh -c '
  apt-get update
  apt-get install -y git python3-venv python3-dev build-essential \
                     uwsgi uwsgi-plugin-python3 redis-server'
```

SearXNG requires a key-value store for the limiter. The service uses **Valkey**; a regular `redis-server` speaks the same protocol (RESP) and the
Python library `valkey` connects to it — therefore, Debian's
`redis-server` (measured on this container: Valkey package not in the sources) is sufficient.

## 3. Source, Environment, Settings

The official way (handled by the user, environment, source, settings, and the
uWSGI template in one go):

```bash
pct exec 108 -- bash -lc '
  git clone https://github.com/searxng/searxng /usr/local/searxng/searxng-src
  cd /usr/local/searxng/searxng-src
  ./utils/searxng.sh install user pyenv packages settings uwsgi'
```

Then adapt the template to your own paths — especially **direct HTTP** to the outside
instead of a socket (no nginx needed):

```bash
pct exec 108 -- sh -c '
  sed -i "s|^# socket = .*|# socket = /usr/local/searxng/run/socket|" /etc/uwsgi/apps-available/searxng.ini
  grep -q "^http = 0.0.0.0:8888" /etc/uwsgi/apps-available/searxng.ini ||
    printf "\nhttp = 0.0.0.0:8888\nbuffer-size = 8192\n" >> /etc/uwsgi/apps-available/searxng.ini'
```

In `/etc/searxng/settings.yml` two entries are crucial:

```yaml
use_default_settings: true
search:
  formats: [html, json]      # without "json" the service does not answer the bot
server:
  secret_key: "<32 Zeichen Zufall>"
  limiter: false             # important for clients without a browser user agent
  image_proxy: true
  base_url: http://192.168.178.26:8888/
valkey:
  url: valkey://localhost:6379/0
```

**Lesson (measured):** The JSON interface responds to programmatic queries with **`Too Many Requests`** (bot recognition without
link token). For a service in your own network, queried only by the bot, the
limiter should be disabled.

## 4. Starting Services

```bash
pct exec 108 -- sh -c 'systemctl enable --now redis-server'
```

For the application, **do not** use a SysV Emperor (which waits for
`network-online.target` and therefore starts only after full network setup), but a custom systemd unit:

```bash
pct exec 108 -- bash -s <<'UNIT'
cat > /etc/systemd/system/searxng.service <<'DIENST'
[Unit]
Description=SearXNG (uWSGI-Anwendung)
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=simple
ExecStart=/usr/bin/uwsgi --ini /etc/uwsgi/apps-available/searxng.ini
Restart=always
RestartSec=3
KillSignal=SIGINT

[Install]
WantedBy=multi-user.target
DIENST
systemctl daemon-reload
systemctl enable --now searxng
UNIT
```

Deactivate the SysV path `uwsgi` and remove the Vassal linking entry —
otherwise, two uWSGI instances will start and compete for port 8888:

```bash
pct exec 108 -- sh -c 'systemctl disable uwsgi; systemctl stop uwsgi; \
  rm -f /etc/uwsgi/apps-enabled/searxng.ini'
```

## 5. Checking
```bash
# lokal im Container
pct exec 108 -- curl -s -m 20 "http://127.0.0.1:8888/search?q=test&format=json" | head -c 200

# from inside the service container (the path the bot takes)
pct exec 103 -- curl -s -m 30 \
  "http://192.168.178.26:8888/search?q=k%C3%BCnstliche+intelligenz&format=json&language=de-DE" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d["results"]), "Treffer")'
```

Expected: a list of results (`{"query": ..., "results": [...]}`), e.g., 20 results with
`engine: "google cse"`, `bing`, `duckduckgo`, `wikipedia`.
Port check: `ss -lntp` shows `0.0.0.0:8888` (uwsgi) and `127.0.0.1:6379` (redis).

**Restart test** (must work without manual intervention):

```bash
ssh -F proxmox-ssh/config ai-server \
  "pct reboot 108 && sleep 25 && pct exec 108 -- sh -c '\
     systemctl is-system-running; systemctl is-active searxng redis-server; \
     curl -s -m 25 \"http://127.0.0.1:8888/search?q=test&format=json\" | head -c 80'"
```

Expected: `running`, `active active`, a list of results. Measured on 2026-09-21 after
`pct reboot`: container back within seconds, services `active`, search delivers results.

## 6. Switching the Bot to Use It

In the service directory on LXC 103 (`/opt/radio-tts`) the value is in
`docker-compose.yml` — or it comes from `RECHERCHE_SEARX_URL` in the environment:

```yaml
    environment:
      RECHERCHE_SEARX_URL: ${RECHERCHE_SEARX_URL:-http://192.168.178.26:8888}
```

```bash
pct exec 103 -- bash -lc 'cd /opt/radio-tts && docker compose up -d'
pct exec 103 -- docker exec radio-tts printenv RECHERCHE_SEARX_URL
```

Afterwards, each topic overview will provide **at least one read web page per topic** (service response: "…, 1 from the web", field `gelesen`
contains the addresses).

## 7. Proving It Works

```bash
# dry run (does not speak, shows only numbers and text)
MK=$(cat <dokuordner>/REBUILD/credentials/meldung-schluessel.txt)
curl -s -X POST http://192.168.178.53:8881/recherche -H 'Content-Type: application/json' \
  -H "X-Meldung-Schluessel: $MK" \
  -d '{"type":"overview","topics":"artificial intelligence","dry":true}' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("Presse",d["presse"],"Wiki",d["wiki"],"Web",d["web"],d["gelesen"])'
```

Measured on 2026-09-21: `Presse 3, Wiki 1, Web 1, ['https://www.tagesschau.de/…']`,
response time 79 s, clean text (no "right arrow", no mark in the title).

## 8. Maintenance

```bash
# Aktualisieren (Quelle + Einstellungen)
pct exec 108 -- bash -lc 'cd /usr/local/searxng/searxng-src && git pull && \
  ./utils/searxng.sh instance update && systemctl restart uwsgi'

# Protokoll
pct exec 108 -- journalctl -u uwsgi -n 40 --no-pager
```

Changes to `settings.yml` are sufficient with `systemctl restart searxng`.