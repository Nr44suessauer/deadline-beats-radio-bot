# Vorlage: der Bot zum Nachbauen

Stand 2026-09-22. Der Bot ist so umgebaut, dass **alle Werte an einer Stelle** stehen
und sich als Vorlage weitergeben lassen.

---

## 1. Die eine Stelle

Ein eigener kleiner Ablauf **`Konfiguration`** enthält genau einen Code-Knoten
(`Werte`) mit allen Angaben:

| Feld | Inhalt |
| --- | --- |
| `sender` | Adresse des Senders (AzuraCast), API-Schlüssel, Sender-Kennung |
| `dienst` | Adresse des eigenen Dienstes (Katalog, Meldungen, Ansage) und der Postfach-Schlüssel |
| `sprache` | Adresse der Spracherkennung (faster-whisper) |
| `sprachmodell` | Adresse von Ollama, Schlüssel, Modellname |
| `telegram` | Adresse der Telegram-Schnittstelle und der Bot-Token |
| `aufgaben` | **alle Texte, die das Sprachmodell liest**: die drei Systemanweisungen (planen, prüfen, ausführen) und die Beschreibungen der acht Werkzeuge |

Aus den Adressen rechnet der Knoten die abgeleiteten Werte selbst
(`sender.api`, `sender.admin`, `sprachmodell.v1`, `telegram.bot`, `telegram.datei`) —
die muss niemand von Hand pflegen.

**Geändert wird nur dieser Knoten.** Die vier Abläufe holen die Werte beim Start über
ihren Knoten `Konfiguration`; in ihnen steht kein einziger Zugangswert mehr. Nach dem
Ändern: speichern, fertig — kein Neustart, kein Erzeuger.

## 2. Wie die Abläufe die Werte holen

```
[Telegram Trigger] ┐
[Test-Eingang]     ├─→ [Konfiguration] ─→ [Weiche Plan?] ─→ [Eingabe] … oder [Meldungen holen] …
[Zeitplan]         ┘
```

Der Aufruf gibt die Nutzlast unverändert wieder aus und hängt `konfig` an. Jeder
Ausdruck liest deshalb aus derselben Quelle:

```js
{{ $('Konfiguration').first().json.konfig.sender.adresse }}
```

Zwei Regeln, die dabei gelten (beide am 2026-09-22 im Testlauf gemessen):

1. **Ein Adressteil muss als GANZER Ausdruck gebaut werden.** n8n löst die Einfügung
   `{{ … }}` mitten in einer Zeichenkette **nicht** auf — im Knoten landete die Adresse
   wörtlich und der Aufruf brach ab mit `Invalid URL: {{ $('Konfiguration')… }}`.
   Falsch: `"{{ $('Konfiguration')…sender.adresse }}/api/station/1/files"`.
   Richtig: `"={{ $('Konfiguration')…sender.adresse + '/api/station/1/files' }}"`.
   Der Erzeuger macht das über die Klasse `Ausdruck` (siehe `agent-wf-bauen.py`):
   `AZ + "/api/station/1"` ergibt genau diese Form.
2. **Die Werkzeugknoten des Agenten** (die acht `Werkzeug …`-Knoten) hängen als
   `ai_tool` am Agenten, nicht im Hauptweg. Sie können den Knoten `Konfiguration`
   deshalb nicht „sehen“ — ob n8n dort Ausdrücke auflöst, zeigt erst ein Testlauf.
   (Am 2026-09-22 geprüft: tut es — der Aufruf „was laeuft gerade“ lief über den
   Agenten und das Werkzeug `was_laeuft` und antwortete korrekt.)

## 3. Umfang der vier Abläufe

| Ablauf | Knoten | holen Werte aus der Zentrale |
| --- | --- | --- |
| `Konfiguration - alle Werte` | 3 | (ist die Zentrale selbst) |
| `Werkzeug - Radio` | 24 | 7 |
| `Werkzeug - AzuraCast` | 22 | 6 |
| `Werkzeug - Meldungen` | 20 | 1 |
| `Radio - Telegram-Agent` | 91 | 26 (davon 10 als Werkzeugknoten) |

## 4. Vorlage weitergeben

```bash
cd ../..
VORLAGE=1 VORLAGE_ZIEL=/tmp/radio-vorlage python3 werkzeuge/agent-wf-bauen.py
```

Ergebnis: `01-konfiguration.json`, `02-werkzeuge.json`, `03-bot.json` — mit
Platzhaltern (`http://DEIN-SENDER`, `DEIN-AZURACAST-API-SCHLUESSEL`,
`DEIN-TELEGRAM-BOT-TOKEN`, `DEIN-MODELL`) statt der Zugangsdaten. Die Aufgaben- und
Werkzeugtexte bleiben erhalten, denn sie sind der Inhalt der Vorlage.

Wer den Bot nachbaut:

1. die drei Dateien in n8n importieren (`Konfiguration` zuerst),
2. den Knoten `Werte` öffnen und die Platzhalter durch eigene Werte ersetzen,
3. die beiden Anmeldedaten in n8n anlegen (Telegram-Konto, Ollama) und an den Knoten
   auswählen,
4. die fünf Abläufe einschalten.

## 5. Prüfen und Einspielen

```bash
python3 werkzeuge/konfiguration-pruefen.py     # 5 Prüfungen (Namen, Verweise,
                                               # Ausdrücke, Erreichbarkeit, Geheimnisse)
python3 werkzeuge/anordnung-pruefen.py /tmp/radio-konfiguration.json \
        /tmp/radio-werkzeuge.json /tmp/radio-agent.json      # muss 0 Befunde melden
bash werkzeuge/konfiguration-einspielen.sh     # importiert und schaltet alle fünf ein
```

**Wichtig für spätere Werkzeugläufe:** `agent-patchen.sh` holt die Zugangswerte heute
aus dem *laufenden Bot* (Muster `api.telegram.org/bot…` und `[0-9a-f]{16}:[0-9a-f]{32}`).
Nach diesem Umbau stehen sie nur noch im Knoten `Werte` — der Patcher muss sie künftig
von dort lesen (aus dem Ablauf `Konfiguration`), sonst baut er mit leeren Werten.

## 6. Was sich sonst geändert hat

- **Sicherungen sind jetzt harmlos**: die Ausgaben von `02-werkzeuge.json` und
  `03-bot.json` enthalten keine Schlüssel und keinen Token mehr. Nur der Ablauf
  `Konfiguration` trägt noch Geheimnisse — genau darum ist die Vorlagen-Fassung
  gefahrlos weiterzugeben.
- Die Prüfung `konfiguration-pruefen.py` ist neu und läuft bei jeder Änderung mit.
