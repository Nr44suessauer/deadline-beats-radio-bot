# Zugangsdaten — was nötig ist und wie es entsteht

**Diese Fassung enthält keine Zugangswerte** — der Ordner `NACHBAU/zugangsdaten/` wurde
entfernt; im Arbeitsordner liegen dort die echten Werte (700/600). Diese Datei ist die
**Anleitung**: was nötig ist, wie es entsteht und wo es hingehört — auch für den Fall,
dass die Zugangsdaten erneuert werden müssen (nach einer Weile sollte man Telegram-Token,
Sender-Schlüssel und DJ-Passwort wechseln).

---

## 1. Übersicht

| Zugang | Wofür | Wo erzeugt | Wo er hingehört |
| --- | --- | --- | --- |
| **Telegram-Bot-Token** | der Bot bei Telegram | @BotFather im Chat (`/newbot`) | in die Abläufe (beim Bauen: Umgebungsvariable `TG_TOKEN`) |
| **Eigene Chat-ID** | Betreibererkennung | `@userinfobot` oder die Telegram-API | statische Daten des Ablaufs (`erlaubte`), setzen mit `erlaubte-setzen.py` |
| **AzuraCast-API-Schlüssel** | alles am Sender | AzuraCast → Profil → API-Schlüssel | Abläufe (`AZ_KEY`) + Umgebungsvariable für Skripte |
| **Liquidsoap-/Streamer-Passwörter** | Live-Ansage in den Sender (und manuelles Senden) | AzuraCast: **zwei** Streamer-Konten anlegen — eins für den Betreiber (z. B. `betreiber`), eins für den Bot (z. B. `deine-stimme`, Anzeigename „DEINE-STIMME“) | Bot-Konto als `LIVE_USER`/`LIVE_PASSWORD` in `/opt/radio-tts/geheim.env` |
| **Postfach-Schlüssel** | Meldungen von außen annehmen | selbst erzeugen (32 Zeichen) | `radio/meldung-schluessel.txt` + `geheim.env`/`X-Meldung-Schluessel` |
| **Schlüssel des Testeingangs** | Prüfläufe über den Webhook | selbst erzeugen | `radio/bot-test-schluessel.txt` + statische Daten des Ablaufs |
| **n8n-Anmeldung** | Oberfläche/Projekt | beim ersten Start | Anmeldedaten in n8n |
| **SSH/Proxmox-Zugang** | Container verwalten | eigene Infrastruktur | nicht Teil des Bots |

**Alle selbst erzeugbaren Schlüssel** (Postfach, Testeingang) sind lange Zufallszeichenketten,
z. B. `python3 -c "import secrets;print(secrets.token_urlsafe(24))"`.

---

## 2. Umgebungsdatei des Dienstes (`/opt/radio-tts/geheim.env`)

Vorlage: `dienst/geheim.env.vorlage` — kopieren, ausfüllen, Rechte 600 setzen.

```bash
cp dienst/geheim.env.vorlage /opt/radio-tts/geheim.env
chmod 600 /opt/radio-tts/geheim.env
# ausfüllen, dann: cd /opt/radio-tts && docker compose up -d
```

Enthalten sind: `LIVE_HOST`, `LIVE_PORT`, `LIVE_MOUNT`, `LIVE_USER`,
`LIVE_PASSWORD` (DJ-Hafen) sowie die Lautstärke-Regelwerte (`TTS_*`).

---

## 3. AzuraCast-API-Schlüssel

1. In AzuraCast anmelden → Profil → **API-Schlüssel** → neuen Schlüssel anlegen.
2. Das Format ist `<identifier>:<verifier>` (z. B. `a1b2c3d4e5f6a7b8:…`) — dieser
   Wert ist das `AZ_KEY` beim Bauen.
3. Ohne Oberfläche: der Schlüssel steht in der Tabelle `api_keys` (identifier = erste
   16 Zeichen, verifier = sha512 des zweiten Teils).

Damit kann der Bot: lesen (öffentlich), schreiben (alles, was die API erlaubt). Die
**Rechte** ergeben sich aus dem Benutzerkonto des Schlüssels.

---

## 4. Telegram

1. `@BotFather` → `/newbot` → Token (Format `123456789:AA…`).
2. Dem Bot im Telegram einmal schreiben (damit der Chat existiert).
3. Eigene Chat-ID ermitteln und in die Betreiberliste eintragen:
   ```bash
   cd werkzeuge && python3 erlaubte-setzen.py <chatId>
   ```
4. Befehlsmenü (optional): `bash telegram-menue.sh`.

---

## 5. DJ-Hafen (Live-Ansage)

In AzuraCast: **Rundfunk → Streamer** **zwei** Zugänge anlegen — einen für den
Betreiber (manuelles Senden) und einen für den Bot. Der **Anzeigename des Bot-Kontos**
ist das, was der Sender beim Sprechen zeigt (Original: Benutzer `deine-stimme`, Anzeigename
**„DEINE-STIMME“**). Der Hafen liegt auf Port **8005**, Mount `/`. Die Werte des **Bot-Kontos**
wandern nach `geheim.env` (`LIVE_USER`, `LIVE_PASSWORD`).

Im Original zusätzlich unter `/var/azuracast/dj_passwort.txt` (Betreiber) und
`/var/azuracast/bot_streamer_passwort.txt` (Bot; beide 600) im AzuraCast-Container
abgelegt — reine Bequemlichkeit.

---

## 6. Statische Daten des Ablaufs

Der Import überschreibt die statischen Daten in n8n. Nach jedem Einspielen prüfen/setzen:

```bash
python3 erlaubte-setzen.py <chatId>     # Betreiberliste
python3 bot-daten-setzen.py             # Testschlüssel und Grundzustand
python3 statische-daten-patchen.py      # Vorhandenes behalten, nur Ergänzungen
```

Der **Testeingang** (Webhook `DEIN-WEBHOOK-PFAD`) verlangt `?schluessel=<Wert>`; dieser
Wert steht in den statischen Daten.

---

## 7. Wo die Werte im Original liegen

| Datei / Ort | Inhalt |
| --- | --- |
| `radio/meldung-schluessel.txt` (600) | Schlüssel für das Postfach (`X-Meldung-Schluessel`) |
| `radio/bot-test-schluessel.txt` (600) | Schlüssel des Testeingangs |
| `radio/azuracast-zugang.txt` (600) | Sammeldatei: Web-Login-Link, Streamadressen, DJ-Zugänge (Betreiber + Bot/DEINE-STIMME), API-Schlüssel |
| `/root/azuracast-zugang.txt` auf dem Datenserver | dieselbe Sammeldatei |
| `/opt/radio-tts/geheim.env` (LXC 103) | DJ-Hafen und Lautstärke-Regelwerte |
| n8n-Anmeldedaten | Telegram-Token und Sender-Schlüssel stecken in den Knoten der Abläufe |
| `/var/azuracast/api_key.txt` (Container, 600) | API-Schlüssel (Notbehelf) |
| `/var/azuracast/dj_passwort.txt` (Container, 600) | Passwort des Betreiber-DJ-Zugangs (Notbehelf) |
| `/var/azuracast/bot_streamer_passwort.txt` (Container, 600) | Passwort des Bot-/Ansagekontos `deine-stimme` |

**Warum das in den Abläufen steckt:** n8n speichert HTTP-Knoten mit ihren Kopfzeilen —
der Sender-Schlüssel und der Telegram-Token stehen deshalb im JSON des Ablaufs. Das ist
der Grund, warum Sicherungen dieses Ablaufs (600) wie Geheimnisse behandelt werden und
warum **maskierte Fassungen niemals eingespielt werden dürfen** (siehe
`../DOKU/BETRIEB.md`, Abschnitt 1).
