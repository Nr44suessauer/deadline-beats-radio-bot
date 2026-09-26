# Sender einrichten (AzuraCast)

Der Bot arbeitet gegen **jeden** AzuraCast-Sender (getestet mit 0.23.4), wenn die
folgenden Punkte eingerichtet sind. Die Werte des laufenden Senders stehen als
Beispiel daneben.

---

## 0. AzuraCast installieren (falls noch keiner läuft)

Der Bot arbeitet gegen einen **fertigen** Sender — wer noch keinen hat, richtet ihn
**vor** den Schritten 1–8 ein. Offizieller Weg der AzuraCast-Dokumentation
(<https://docs.azuracast.com/>, im Original läuft 0.23.4 auf Debian 12):

```bash
mkdir -p /var/azuracast && cd /var/azuracast
curl -fsSL https://raw.githubusercontent.com/AzuraCast/AzuraCast/main/docker.sh > docker.sh
bash docker.sh install        # fragt nach Port, Konto, Passwort, Zeitzone
```

| Punkt | Wert im Original |
| --- | --- |
| Programm und Daten | `/var/azuracast` (Compose-Datei, `azuracast.env`, `.env`) |
| Musik | eigener Ordner, per Bind-Mount in den Container (im Original `/mnt/Content`, 15-TB-Platte) |
| Ports | **80/443** Oberfläche, **8000** Hörer-Stream, **8005–8496** je Sender/Mount (darin der DJ-Hafen), **2022** SFTP, **9000** |
| Konto | das beim Installieren angelegte Konto (Anmeldung in der Oberfläche) |
| Konsole | `docker exec -it azuracast azuracast_cli list` — z. B. `azuracast:account:login-token <mail>` (Einmal-Anmeldelink), `radio:restart` |

**Prüfen — erst danach weiter:**

```bash
curl -s http://<sender-ip>/api/status | head -c 120      # {"online":true,…}
curl -s http://<sender-ip>/api/nowplaying | head -c 120  # Sender, Titel, Hörer
```

Danach §1 (Sender, Mount, Streamer) und §7 (**API-Schlüssel** anlegen, Format
`kennung:prüfsumme`) — der Schlüssel wird später als `AZ_KEY` im Dienst gebraucht.
Anmeldedaten und Adressen gehören in die eigenen Zugangsdaten (Anleitung:
`zugangsdaten.md`).

---

## 1. Sender anlegen

| Einstellung | Wert im Original | Anmerkung |
| --- | --- | --- |
| Name | `Deadline Beats` | frei |
| Kurzname (shortcode) | `deadline_beats` | bestimmt die Streamadresse |
| Zeitzone | `UTC` | frei |
| Sendeteil (backend) | `liquidsoap` | **Voraussetzung** — hier hängt der DJ-Hafen |
| Ausgabe (frontend) | `icecast` | Hörer-Stream |
| AutoDJ | ein | ohne AutoDJ gibt es keine Rotation |
| Crossfade | 2 s (`normal`) | Original |

**Öffentliche Adressen** (Beispiel):
`http://192.168.178.33/listen/deadline_beats/radio.mp3`,
Hörerfrontend auf Port **8000**, Verwaltungsschnittstelle `/api`.

---

## 2. Mount (Hörer-Ausgang)

| Feld | Beispiel |
| --- | --- |
| Pfad | `/radio.mp3` |
| Format / Bitrate | `mp3`, 192 kbps |
| Standard-Mount | ja |

Reicht einer; der Bot nutzt ihn nicht direkt (er steuert über die API und spricht über
den DJ-Hafen).

---

## 3. Streamer-Zugang (für die Live-Moderation)

**Das ist der wichtigste Punkt.** Die Moderation spricht über den **DJ-Hafen**:

| Einstellung | Wert |
| --- | --- |
| Streamer-Benutzer | **zwei Konten:** eins für den Betreiber (z. B. `betreiber`, Anzeigename „betreiber“) und eins für den Bot (Original: `deine-stimme`, Anzeigename **„DEINE-STIMME“**) |
| Passwort | selbst wählen (Bot-Konto in `geheim.env` als `LIVE_USER`/`LIVE_PASSWORD`) |
| Aktiv | **ja** (beide) |
| Auf Zeiten beschränken (`enforce_schedule`) | **nein** — sonst sprechen Ansagen nur zu bestimmten Zeiten |
| DJ-Zugänge erlauben (`enable_streamers`) | **ja** — in den Sendereinstellungen |

Hafen: Port **8005**, Mount **`/`**, Protokoll `PUT` mit `Content-Type: audio/mpeg`,
Basic-Auth aus Benutzer + Passwort.

**Warum ein eigenes Bot-Konto?** Der Sender zeigt beim Live-Sprechen den
**Anzeigenamen des angemeldeten Streamer-Kontos**. Mit einem eigenen Konto für den
Dienst (Original: `deine-stimme`) steht in der Senderoberfläche und im Player beim Ansagen
**„DEINE-STIMME“** — der manuelle DJ-Zugang des Betreibers läuft getrennt unter seinem
eigenen Namen (Näheres: `zugangsdaten.md` §5).

**Achtung (aus der Praxis):** ohne `enable_streamers = true` antwortet der Hafen mit
401 und die Ansage bleibt stumm. Der Bot prüft das nicht vorab — im Zweifel in den
Sendereinstellungen nachsehen.

---

## 4. Wünsche und Rotation

| Einstellung | Wert im Original | Warum |
| --- | --- | --- |
| Wünsche erlauben (`enable_requests`) | ja | für den Wunschweg |
| Sperrfrist (`request_threshold`) | **0 Minuten** | sonst werden Wünsche abgelehnt, deren Titel „zu kürzlich" lief |
| Wiedergabeliste(n) | `List A` (Typ `default`, aktiv, `include_in_requests`) | das ist die **Rotation** — nur Titel darin laufen von selbst |
| Alles andere im Archiv | nicht in einer Liste | dient als Wunsch- und Suchpool |

Der Bot spielt Wünsche über `PUT /api/station/1/files/batch` mit
`{"do":"immediate"}` (sofort, unterbricht) bzw. `{"do":"queue"}` (einreihen). Vor
einem Sofortwunsch leert er die unterbrechende Warteschlange.

---

## 5. Medien

1. Musik in den Medienordner legen (Original: `/mnt/Content/Music`, im Container
   `/data`).
2. In AzuraCast unter **Medien** einlesen lassen (oder `azuracast_cli
   media:reprocess`).
3. Der Bot braucht **relative Pfade** (die API liefert sie so) — nichts umbauen.

**Nie Dateien per `mv` verschieben, während AzuraCast läuft** — der Abgleich läuft über
`md5(Pfad)`, ein Verschieben löscht den Datensatz samt Wiedergabelisten-Zuordnung. Für
Umsortierungen die API benutzen (`files/batch` mit `do=move`).

---

## 6. Einstellungen, die der Bot nutzt

| Einstellung | Wert | Wirkung |
| --- | --- | --- |
| `enable_requests` | ja | Wunschweg über die API |
| `request_threshold` | 0 | keine Sperrfrist |
| `enable_streamers` | ja | Live-Moderation möglich |
| Zeitzone `UTC` bzw. Europe/Berlin | – | nur Anzeige |

Prüfen mit:

```bash
curl -s -H "X-API-Key: <Schlüssel>" http://<sender>/api/admin/station/1 \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print({k: d[k] for k in ('enable_requests','request_threshold','enable_streamers')})"
```

---

## 7. Benutzer und Rollen

Der Bot handhabt Nutzer, Rollen, Einstellungen und Sicherungen **über die API**
(Werkzeug `azura_aufruf`). Für den Nachbau genügt ein Administratorkonto
(E-Mail + Passwort) und ein API-Schlüssel dieses Kontos.

---

## 8. Prüfliste nach dem Einrichten

```bash
# 1. Läuft der Sender?
curl -s http://<sender>/api/nowplaying/1 | head -c 200

# 2. Ist der DJ-Hafen offen? (erwartet: 401 ohne Zugangsdaten, nicht "connection refused")
curl -s -o /dev/null -w "%{http_code}\n" -X PUT http://<sender>:8005/ --data-binary ""

# 3. Stimmen die Einstellungen?
curl -s -H "X-API-Key: <Schlüssel>" http://<sender>/api/admin/station/1 \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['enable_streamers'], d['request_threshold'])"
# erwartet: True 0

# 4. Wiedergabeliste vorhanden und aktiv?
curl -s -H "X-API-Key: <Schlüssel>" http://<sender>/api/station/1/playlists \
  | python3 -c "import json,sys; print([(p['name'], p['type'], p['is_enabled']) for p in json.load(sys.stdin)])"
```

Danach den Katalog füllen und eine Testansage sprechen (siehe `README.md`, Schritt 7).
