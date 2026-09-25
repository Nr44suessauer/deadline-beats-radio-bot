# Tempo des Radio-Bots (2026-09-20)

Ausgangslage: eine einfache Ansage („Ich spiele mir etwas von Scooter.") brauchte
**163 s**. Gemessen wurde am Beispiel-Lauf 2052: davon waren ~160 s Modellzeit in
**6 Aufrufen** (`Planen` 51 s, `Prüfen` 25 s, `Nacharbeiten` 74 s mit 3 Aufrufen,
`Ausführen` 8,5 s mit 2 Aufrufen).

## Ergebnis

| Fall | vorher | nachher |
|---|---|---|
| „Ich spiele mir etwas von Scooter." (gesprochen formuliert) | 163 s | **1,7 s** |
| Verwaltungsauftrag (KI-Weg, z. B. Wiedergabeliste) | 70–163 s | **45 s** |
| Aufruf `Planen` | 51 s | **2,3 s** |
| Aufruf `Prüfen` | 25 s | 1,8 s (meist ganz ohne Modell) |
| Aufruf `Nacharbeiten` | 74 s | entfällt im Regelfall |

## Drei Ursachen und was dagegen gemacht wurde

### 1. Das Modell „dachte" bei jeder Anfrage mit

Gemessen mit der echten Planungsanweisung:

| | Dauer | Ausgabe-Token |
|---|---|---|
| wie vorher (`/no_think` im Text) | 9,8 s | 347 |
| mit `reasoning_effort: "none"` | **1,7 s** | **34** |

Ergebnis-JSON in beiden Fällen identisch. Der Textbaustein `/no_think` wird von
`qwen3.6` über die Ollama-Schnittstelle **nicht** beachtet, die Angabe im
Anfragekörper schon. → In `modell_koerper()` (direkte Aufrufe `Planen`, `Prüfen`)
ergänzt.

### 2. Die Prüfstufe meldete Fehlalarme

Im Beispiel-Lauf stufte `Prüfen` einen Befehl als „nicht ok" ein, obwohl das
Werkzeug selbst `OK: "Scooter - Hyper Hyper" läuft jetzt sofort.` gemeldet hatte.
Das löste `Nacharbeiten` mit drei weiteren Modellaufrufen aus (99 s für nichts).

→ `LAGE_JS` erkennt jetzt: melden **alle** Befehle ihren Erfolg mit `OK:`, ist
das Urteil belegt und wird ohne Modell gefällt (`klarErledigt`). Die Werkzeuge
setzen dieses Zeichen selbst, wenn sie ausgeführt haben.

### 3. Gesprochene Formulierungen umgingen den Schnellweg

Der Ablauf hat eine modellfreie Vorschaltstufe (`Kurz?`), die auf „spiele X",
„danach X" und Kurzbefehle reagiert. Die **gesprochene** Formulierung „**Ich
spiele mir etwas von** Scooter" passte nicht ins Muster und landete deshalb in
der kompletten KI-Kette – genau der Fall, der als langsam aufgefallen ist.

→ In `KURZ_JS` erkennt jetzt zusätzlich „ich spiele/will/möchte … (etwas/was) von X",
„kannst du was von X spielen", „spiel mir mal was von X".

Nebenbei behoben: „spiele **drei Lieder** von Rammstein" galt vorher als
*Titelsuche* nach dem Text „drei lieder von rammstein" und lief ins Leere.
Mengenangaben („drei Lieder", „2 Songs", „zwei Titel") gehen jetzt an die KI.
Geprüft mit `02-kurz-test.js` (19 Fälle, alle wie erwartet).

### 4. Das Modell wurde nach 5 Minuten entladen

Der Dienst in LXC 105 hatte `OLLAMA_KEEP_ALIVE=5m`. Ein Neuladen kostet
**gemessen 43,7 s** – das war der Rest der 47 s, die `Planen` im ersten Test noch
brauchte. → In `/etc/systemd/system/ollama.service.d/override.conf` auf `30m`
gesetzt (Sicherung `override.conf.vor-tempo-<Stempel>` liegt daneben). Bleibt das
Modell dauerhaft im Arbeitsspeicher, sind es `-1` statt `30m` (belegt dann
dauerhaft 18,2 GB Grafikspeicher).

## Panne beim Einspielen (2026-09-20) – und die Lehre daraus

Die erste Fassung von `03-tempo-patchen.py` hat die Zugangswerte **nur für den
Vergleich** maskiert, dann aber versehentlich **die maskierte Fassung
eingespielt**. Im laufenden Ablauf stand damit an sieben Stellen `<GEHEIM>`
statt der Telegram-Kennung und des Schnittstellenschlüssels. Folge: jede
Sprachnachricht brach ab (`getFile` → 404, „Die Sprachnachricht konnte nicht
verarbeitet werden") und der Bot konnte keine Antwort mehr senden (`sendMessage`
→ 404). Gemeldet als „Nachricht an den Bot funktioniert nicht".

Behoben durch erneutes Patchen aus der Sicherung mit einem Skript, das die
Maskierung nur für eine **Kopie** verwendet und vor dem Schreiben prüft:

- kein `<GEHEIM>` in der Ausgabe,
- Telegram-Kennung und Schnittstellenschlüssel sind enthalten,
- die zu übernehmenden Knoten enthalten keine Platzhalter.

Geprüft wurde anschließend gegen die echten Dienste: `getFile` mit der
Dateikennung der gescheiterten Sprachnachricht → HTTP 200 mit `file_path`;
`sendMessage` → HTTP 400 „chat not found" (also gültige Adresse); echter Lauf
über den Testeingang in den Betreiberchat: Antwort in 1,9 s zugestellt
(`ok:true`).

**Lehre**: Beim Vergleichen von Abläufen niemals die maskierte Fassung
weiterverwenden – für den Vergleich eine Kopie anlegen und am Ende prüfen, dass
in der Ausgabe die echten Zugangswerte stehen (und keine Platzhalter).

## Was noch übrig ist

Der Knoten `Ausführen` ist ein n8n-**Agentenknoten** (`lmChatOpenAi`). Dort lässt
sich `reasoning_effort` nicht setzen (die n8n-Fassung nutzt das Feld nur im
Responses-Pfad), deshalb denkt das Modell dort weiter mit:

| | Dauer | Ausgabe-Token | Denktext |
|---|---|---|---|
| wie im Agentenknoten | 51,9 s | 2.173 | 8.484 Zeichen |
| mit `reasoning_effort: "none"` | **1,6 s** | 17 | – |

Das sind die verbleibenden ~40 s im KI-Weg. Ein Weg dahin wäre ein kleiner
Zwischendienst vor Ollama (z. B. Port 11435), der bei `/v1/chat/completions`
`reasoning_effort: "none"` ergänzt, und die Anmeldedaten des Bots
(„Ollama (OpenAI-Schnittstelle)") auf diesen Port zeigen. Das war noch nicht
beauftragt und ist deshalb **nicht** eingebaut.

## Werkzeuge in diesem Ordner

| Datei | Zweck |
|---|---|
| `01-fassung-sichern.sh` | entfallen – Fassungs-Sicherungen macht `../fassung-sichern.sh` |
| `02-kurz-test.js` | Vorschaltstufe (`Kurz?`) mit 19 Beispielsätzen prüfen – ohne n8n |
| `03-tempo-patchen.py` | die geänderten Knoten aus dem Neubau in die laufende Fassung übernehmen |
| `04-einspielen.sh` | gepatchten Ablauf in n8n einspielen und n8n neu starten |
| `10-modell-zeitmessung.py` | Modellaufrufe mit/ohne Denken messen (liegt in `aufraeumen/`) |

## Sicherung

`fassungen/radio-v2-2026-09-20-vor-tempo/` – Exporte aller vier Abläufe, die
komplette n8n-Datenbank (`n8n-daten.sqlite.gz`), die Erzeugerskripte dieser
Fassung und der Rückweg im `README.md` dort.
