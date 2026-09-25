# Listenaufgaben (Wiedergabelisten im Sender)

Werkzeuge, Prüfläufe und der Weg Einspielen für die **mehrschichtigen Aufgaben**
des Radio-Bots rund um Wiedergabelisten: bauen, im Telegram-Menü auswählen,
verwalten und abspielen.

Die Logik selbst liegt in **`../../dienst/playlist.py`** und läuft im Dienst
`radio-tts` (LXC 103, Port 8881). Hier liegen die Skripte, mit denen sie
eingespielt, geprüft und in den n8n-Ablauf eingebaut wird.

## Der Weg einer Erweiterung

```bash
cd ../../werkzeuge/playlist

python3 10-zerlegen-test.py        # 1) Erkennung prüfen (Sätze -> Auftrag)
bash 11-dienst-art-test.sh        # 2) Weiche prüfen (Telegram-Update -> Entscheidung)
bash 08-dienst-einspielen.sh       # 3) Modul in den Dienst, Dienst neu bauen
bash 09-dienst-test.sh             # 4) alle Listenwege ohne Telegram
bash 13-listen-patchen.sh          # 5) Ablauf neu bauen, vergleichen, patchen
bash 14-listen-einspielen.sh       # 6) Ablauf einspielen und aktivieren
python3 15-bot-listen-test.py      # 7) Ende-zu-Ende über den Bot
```

Vor Schritt 5/6 gehört eine Sicherung der laufenden Fassung:

```bash
cd ../../werkzeuge
bash fassung-sichern.sh radio-vX-<datum>-<kurzname> /tmp/beschreibung.md
```

Zurück zum gesicherten Stand (nur der Bot-Ablauf):

```bash
bash ../tempo/04-einspielen.sh \
  <datei> RadioAgentBot   # <datei> = Export aus einer Sicherung oder frisch aus n8n
```

## Die Skripte

| Datei | Was es tut |
| --- | --- |
| `05-listenwege-test.sh` | früher Prüflauf der Adressen des Senders (anlegen/ergänzen/leeren) |
| `06-leeren-umbenennen-test.sh`, `07-umbenennen-test.sh` | Einzelprüfungen aus der Bauzeit |
| `08-dienst-einspielen.sh` | kopiert `dienst/playlist.py` in den Dienst, bindet den Router in `main.py` ein, baut und startet den Dienst neu |
| `09-dienst-test.sh` | 13 Schritte: Listen zeigen, Menü, Haken setzen, anlegen, abbrechen, ansehen, umbenennen, leeren, löschen, Listenwahl, unbekannter Auftrag |
| `10-zerlegen-test.py` | Auftragserkennung ohne Dienst und ohne Netz (Attrappen für FastAPI/Pydantic) |
| `11-dienst-art-test.{sh,js}` | schickt echte Telegram-Updates durch **die echte `EINGABE_JS`** und dann durch die Weiche `DIENST_ART_JS` (37 Fälle: Listenknöpfe, Meldungsknöpfe, Texte) |
| `12-neubau-vergleich.py` | listet, was ein vollständiger Neubau gegenüber der laufenden Fassung ändern würde |
| `13-listen-patchen.{sh,py}` | erzeugt den Neubau und setzt **nur** die Listenknoten, `Eingabe`, Verbindungen und Positionen in die laufende Fassung (wiederholbar) |
| `14-listen-einspielen.sh` | importiert die gepatchte Fassung, aktiviert sie, startet n8n neu, prüft Webhook |
| `15-bot-listen-test.py` | Ende-zu-Ende über den Testeingang mit echten Nachrichten im Betreiberchat; `--spielen` testet zusätzlich das Abspielen |
| `16-ausfuehrungen.sh` | zeigt die letzten Läufe des Bot-Ablaufs mit Knotenausgaben (welcher Zweig lief) |

## Warum gepatcht wird und nicht neu gebaut

`agent-einspielen.sh` würde den **ganzen** Ablauf neu erzeugen. Der Erzeuger setzt dabei an den
sechs Werkzeugknoten das Feld `name` (`titel_suchen` und so weiter), das die laufende Fassung
nicht hat — das würde die Werkzeugnamen gegenüber dem Modell ändern und gehört nicht zu dieser
Erweiterung. `13-listen-patchen.py` übernimmt darum chirurgisch:

- die neuen Knoten `Listen Art`, `Listen?`, `Listen Dienst`, `Listen Antwort`, `Listen Senden`
  und die Haftnotiz `Notiz Listen`,
- den neuen Inhalt von `Eingabe` (Feld `knopfRoh`),
- die fünf geänderten Verbindungen,
- die Positionen der sieben verschobenen Knoten.

Danach prüft es: keine Maskenmerker (`<GEHEIM>`), Telegram-Kennung und Schnittstellenschlüssel
enthalten, jedes Verbindungsziel existiert, Knotenzahl passt. Erst dann wird geschrieben.

## Fallstricke (kurz)

- **Feldnamen**: `EINGABE_JS` liefert `isCallback` (nicht `istCallback`). Prüfläufe müssen die
  echte `EINGABE_JS` benutzen, sonst prüfen sie an der Wirklichkeit vorbei.
- **HTML**: Antworten gehen mit `parse_mode: HTML` an Telegram, `&`, `<`, `>` müssen maskiert
  werden (`<Name>` in einem Beispielsatz brach den Versand mit HTTP 400).
- **Menü bearbeiten**: `bearbeiten: true` → `editMessageText`, sonst `sendMessage`.
- **Testlisten wieder löschen**: eine angelegte Liste ist `default` und sofort spielbereit.
- **Abspielen** unterbricht den Sendebetrieb (`flush_and_skip`, dann `immediate` + `queue`).

Ausführliche Fassung: `../../README.md` §11 und `../../DOKU/HANDBUCH.md` §5.
