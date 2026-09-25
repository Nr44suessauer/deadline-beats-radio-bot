# Eigene Suchmaschine für den Bot (SearXNG in LXC 108)

Stand 2026-09-21. Diese Anleitung richtet die **eigene Suchmaschine** ein, die der
Recherche-Dienst für „normale Internetseiten" benutzt. Ohne sie fragt der Dienst
DuckDuckGo und Bing direkt — und die sperren Rechner ohne Anmeldung
(siehe `../DOKU/BETRIEB.md` §14: DuckDuckGo 202, Mojeek Captcha, Ecosia 403).

| Punkt | Wert |
| --- | --- |
| Container | **LXC 108 „SearXNG"** auf dem ai-server (`pct`) |
| System | Debian 12 (bookworm), 2 Kerne, **1024 MB**, 10 GB Platte, `nesting=1`, `onboot=1` |
| Adresse | **http://192.168.178.26:8888** (DHCP-Adresse der Fritz!Box) |
| Dienst | `searxng.service` (systemd, ruft `uwsgi --ini /etc/uwsgi/apps-available/searxng.ini`) auf `0.0.0.0:8888`, dazu `redis-server` |
| Dienstnutzer | `searxng` (uid 999) |
| Quelle | `/usr/local/searxng/searxng-src` (git, github.com/searxng/searxng) |
| Python-Umgebung | `/usr/local/searxng/searx-pyenv` |
| Einstellungen | `/etc/searxng/settings.yml` |
| Eintrag im Bot | `RECHERCHE_SEARX_URL=http://192.168.178.26:8888` |

---

## 1. Container

```bash
ssh -F proxmox-ssh/config ai-server
pct set 108 -memory 1024 -swap 1024 -onboot 1     # 512 MB sind für uWSGI knapp
# WICHTIG: kein IPv6-DHCP - sonst hängt der Container beim Start minutenlang in
# dhclient-Solicits (gemessen: 68 s Wartezeit je Versuch) und alle Dienste warten.
pct set 108 -net0 name=eth0,bridge=vmbr0,firewall=1,ip=dhcp,ip6=manual,type=veth
pct start 108
pct exec 108 -- sh -c 'ip -4 addr show eth0 | grep inet; python3 -V; free -m | head -2'
```

Erwartet: Debian 12, Python 3.11, Adresse `192.168.178.26`.
**Hinweis:** Die Adresse kommt per DHCP. Ändert sie sich, muss `RECHERCHE_SEARX_URL`
im Dienst angepasst werden (oder im Router eine Adressreservierung für die
MAC-Adresse des Containers eintragen).

## 2. Pakete und Dienstnutzer

```bash
pct exec 108 -- sh -c '
  apt-get update
  apt-get install -y git python3-venv python3-dev build-essential \
                     uwsgi uwsgi-plugin-python3 redis-server'
```

SearXNG braucht für den Limiter einen Schlüssel-Wert-Speicher. Der Dienst nutzt dafür
**Valkey**; ein gewöhnlicher `redis-server` spricht dasselbe Protokoll (RESP) und die
Python-Bibliothek `valkey` verbindet sich damit — deshalb genügt Debian's
`redis-server` (auf diesem Container gemessen: Valkey-Paket nicht in den Quellen).

## 3. Quelle, Umgebung, Einstellungen

Der offizielle Weg (erledigt Nutzer, Umgebung, Quelle, Einstellungen und die
uWSGI-Vorlage in einem Zug):

```bash
pct exec 108 -- bash -lc '
  git clone https://github.com/searxng/searxng /usr/local/searxng/searxng-src
  cd /usr/local/searxng/searxng-src
  ./utils/searxng.sh install user pyenv packages settings uwsgi'
```

Danach die Vorlage an die eigenen Wege anpassen — vor allem **direkt HTTP** nach außen
statt eines Sockets (kein nginx nötig):

```bash
pct exec 108 -- sh -c '
  sed -i "s|^# socket = .*|# socket = /usr/local/searxng/run/socket|" /etc/uwsgi/apps-available/searxng.ini
  grep -q "^http = 0.0.0.0:8888" /etc/uwsgi/apps-available/searxng.ini ||
    printf "\nhttp = 0.0.0.0:8888\nbuffer-size = 8192\n" >> /etc/uwsgi/apps-available/searxng.ini'
```

In `/etc/searxng/settings.yml` sind zwei Einträge entscheidend:

```yaml
use_default_settings: true
search:
  formats: [html, json]      # ohne "json" antwortet der Dienst dem Bot nicht
server:
  secret_key: "<32 Zeichen Zufall>"
  limiter: false             # wichtig für Abrufer ohne Browser-Kennung
  image_proxy: true
  base_url: http://192.168.178.26:8888/
valkey:
  url: valkey://localhost:6379/0
```

**Lehre (gemessen):** Mit `limiter: true` antwortet die JSON-Schnittstelle
programmatischen Abrufern mit **`Too Many Requests`** (Bot-Erkennung ohne
Link-Token). Für einen Dienst im eigenen Netz, den nur der Bot fragt, ist der
Limiter abzustellen.

## 4. Dienste starten

```bash
pct exec 108 -- sh -c 'systemctl enable --now redis-server'
```

Für die Anwendung **keinen** SysV-Emperor benutzen (der wartet auf
`network-online.target` und wird deshalb erst nach der vollständigen
Netzwerkeinrichtung gestartet), sondern eine eigene systemd-Einheit:

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

Den SysV-Weg `uwsgi` dabei **abschalten** und den Vassal-Verknüpfungseintrag entfernen —
sonst starten zwei uWSGI-Instanzen und streiten um Port 8888:

```bash
pct exec 108 -- sh -c 'systemctl disable uwsgi; systemctl stop uwsgi; \
  rm -f /etc/uwsgi/apps-enabled/searxng.ini'
```

## 5. Prüfen
```bash
# lokal im Container
pct exec 108 -- curl -s -m 20 "http://127.0.0.1:8888/search?q=test&format=json" | head -c 200

# aus dem Dienstcontainer heraus (der Weg, den der Bot nimmt)
pct exec 103 -- curl -s -m 30 \
  "http://192.168.178.26:8888/search?q=k%C3%BCnstliche+intelligenz&format=json&language=de-DE" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d["results"]), "Treffer")'
```

Erwartet: eine Trefferliste (`{"query": ..., "results": [...]}`), z. B. 20 Treffer mit
`engine: "google cse"`, `bing`, `duckduckgo`, `wikipedia`.
Portkontrolle: `ss -lntp` zeigt `0.0.0.0:8888` (uwsgi) und `127.0.0.1:6379` (redis).

**Neustartprobe** (muss ohne Handgriffe klappen):

```bash
ssh -F proxmox-ssh/config ai-server \
  "pct reboot 108 && sleep 25 && pct exec 108 -- sh -c '\
     systemctl is-system-running; systemctl is-active searxng redis-server; \
     curl -s -m 25 \"http://127.0.0.1:8888/search?q=test&format=json\" | head -c 80'"
```

Erwartet: `running`, `active active`, eine Trefferliste. Gemessen am 2026-09-21 nach
`pct reboot`: Container nach Sekunden wieder da, Dienste `active`, Suche liefert Treffer.

## 6. Den Bot darauf umstellen

Im Dienstverzeichnis auf LXC 103 (`/opt/radio-tts`) steht der Wert in
`docker-compose.yml` — oder er kommt aus `RECHERCHE_SEARX_URL` in der Umgebung:

```yaml
    environment:
      RECHERCHE_SEARX_URL: ${RECHERCHE_SEARX_URL:-http://192.168.178.26:8888}
```

```bash
pct exec 103 -- bash -lc 'cd /opt/radio-tts && docker compose up -d'
pct exec 103 -- docker exec radio-tts printenv RECHERCHE_SEARX_URL
```

Danach liefert jeder Themen-Überblick zusätzlich **mindestens eine gelesene
Netzseite je Thema** (Rückmeldung des Dienstes: „…, 1 aus dem Netz", Feld `gelesen`
enthält die Adressen).

## 7. Nachweisen, dass es wirkt

```bash
# Trockenlauf (spricht nicht, zeigt nur Zahlen und Text)
MK=$(cat <dokuordner>/NACHBAU/zugangsdaten/meldung-schluessel.txt)
curl -s -X POST http://192.168.178.53:8881/recherche -H 'Content-Type: application/json' \
  -H "X-Meldung-Schluessel: $MK" \
  -d '{"art":"ueberblick","themen":"künstliche intelligenz","trocken":true}' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("Presse",d["presse"],"Wiki",d["wiki"],"Web",d["web"],d["gelesen"])'
```

Gemessen am 2026-09-21: `Presse 3, Wiki 1, Web 1, ['https://www.tagesschau.de/…']`,
Sprechzeit 79 s, sauberer Text (kein „Pfeil rechts", keine Marke im Titel).

## 8. Pflege

```bash
# Aktualisieren (Quelle + Einstellungen)
pct exec 108 -- bash -lc 'cd /usr/local/searxng/searxng-src && git pull && \
  ./utils/searxng.sh instance update && systemctl restart uwsgi'

# Protokoll
pct exec 108 -- journalctl -u uwsgi -n 40 --no-pager
```

Bei Änderungen an `settings.yml` genügt `systemctl restart searxng`.
