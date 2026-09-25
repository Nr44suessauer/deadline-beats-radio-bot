# Anhang

## Erzeugte Übersichten (aus dem laufenden Betrieb)

| Datei | Inhalt |
| --- | --- |
| `n8n-oberflaeche.html` | **Der Bot in der n8n-Oberfläche** — je Ablauf ein Gesamtbild und **ein Bild je Modul** (**40 Module in 7 Abläufen**, inkl. „Konfiguration – alle Werte“ und „Stimmen aus Filmen“) mit der Erklärung des Abschnitts und seiner Knotenliste. **Jedes Bild ist anklickbar und zoombar** (Mausrad, Knöpfe, Ziehen, Esc). **Stand: 24.09.2026**, frisch aus der laufenden Oberfläche aufgenommen |
| `bilder/module/` | die sieben **Gesamtbilder** (die 40 Modulbilder wurden nach dem Bau gelöscht, Aufräumung 24.09.2026) |
| `bilder/modulplan.json`, `bilder/startmassstaebe.json` | Aufnahmeplan und Startmaßstäbe — Grundlage für eine neue Aufnahme (die Kacheln und Modulbilder wurden nach dem Bau gelöscht, Aufräumung 24.09.2026) |
| — | die früheren Aufnahmen (alte Ausschnitte, Kacheln und Modulbilder der Durchläufe vom 21./22.09.2026 und des ersten Durchgangs vom 24.09. vor der Text- und Rahmenüberarbeitung) wurden **gelöscht** (Aufräumung am 24.09.2026) |
| `ANORDNUNG.md` | **Zeichenfläche des Bots**: je Rahmen die Erklärung, darunter jeder Knoten mit seiner Beschriftung und Position (erzeugt von `anordnung-doku.sh`, Stand 2026-09-24) |
| `ablauf-bot-uebersicht.png` | der ganze Ablauf als Karte (9 Rahmen, Übersichtsnotiz) |
| `ablauf-bot-eingang.png` | Eingang, Sprachnachricht und Analyse im Detail |
| `ablauf-bot-ausfuehrung.png` | Ausführung, Werkzeuge, Prüfung und Antwort im Detail |
| `bilder/bot-lauf-gesamt.gif` | **der ganze Ablauf in Bewegung** — echter Testlauf, eng beschnitten auf die Knotenrechtecke, 5,6 s, 4,6 MB, 1000×676 |
| `bilder/bot-lauf-kamera.gif` | **Nahaufnahme mit Kamerafahrt** — der Blick folgt dem Lauf, 6,9 s, 4,1 MB, 860×490 |
| `bilder/bot-lauf-gesamt-web.gif` | dieselbe Aufnahme **für einen Beitrag**: 800 Punkte breit, mit Beschriftungsleiste, 3,1 MB |
| `bilder/bot-lauf-kamera-web.gif` | Kamerafahrt für einen Beitrag: 800 Punkte breit, mit Beschriftungsleiste, 4,0 MB |

Die Bilder sind aus dem **laufenden** Ablauf gezeichnet, nicht von Hand. Neu erzeugen:

```bash
cd ../..
python3 werkzeuge/vorschau.py <ablauf.json> bild.png 0.42 x0 y0 x1 y1   # Ausschnitt
VORSCHAU_OHNE_NAMEN=1 python3 werkzeuge/vorschau.py <ablauf.json> karte.png 0.19
bash werkzeuge/anordnung-doku.sh                                        # ANORDNUNG.md
```

Die **Bilder in der n8n-Oberfläche** für `n8n-oberflaeche.html` entstehen aus der
laufenden Anlage. Vor einer Neuaufnahme zuerst die **Anzeigetexte** in Ordnung bringen
(Umlaute: `python3 deutsch-texte.py --anwenden <ablaeufe…>` — läuft im Bauweg von
`agent-patchen.sh` mit) und die **Rahmen** prüfen; der Weg von der Aufnahme bis zum
Dokument (Neuaufnahme nur nötig, wenn sich der Bot geändert hat):

```bash
cd ../../werkzeuge
python3 modulbilder-plan.py  ../ANHANG/bilder/modulplan.json \
  ../../Ai_Radio_Moderator_Bot/NACHBAU/ablaeufe-laufend/*.json     # Plan rechnen
python3 modulbilder-massstaebe.py ../../Ai_Radio_Moderator_Bot/ANHANG/bilder/modulplan.json \
  ../../Ai_Radio_Moderator_Bot/ANHANG/bilder/startmassstaebe.json /tmp/cap   # Maßstäbe + Aufnahmezettel
#   ... Kacheln in der Oberfläche aufnehmen (Browsersteuerung) nach ANHANG/bilder/kacheln/ ...
python3 bilder-stitch.py ../../Ai_Radio_Moderator_Bot/ANHANG/bilder/modulplan.json \
  ../../Ai_Radio_Moderator_Bot/ANHANG/bilder/kacheln \
  ../../Ai_Radio_Moderator_Bot/ANHANG/bilder/module                    # zusammensetzen
cd ../..
python3 werkzeuge/n8n-doku-bauen.py                                    # einbetten
```

**Vor jeder neuen Aufnahme den Kachelordner leeren!** Sonst mischt `bilder-stitch.py`
alte Kacheln derselben Module dazu (gleicher Name `__t1__`) — im Bild erscheinen dann
helle Bänder und doppelte Knoten aus einem früheren Lauf:
`mkdir -p bilder/kacheln-alt && mv bilder/kacheln/*.png bilder/kacheln-alt/`.

### Aufnahme in der Oberfläche (erprobt)

Das Aufnahmeprogramm steuert die geöffnete n8n-Seite. Sechs Regeln, ohne die die
Bilder falsch werden (alle am 2026-09-22 durchgemessen):

1. **Licht erzwingen** — `page.emulateMedia({ colorScheme: 'light' })`. n8n folgt der
   Systemeinstellung; ohne das kommt die dunkle Fläche, auf der die Rahmenfarben und
   die weissen Karten kaum zu erkennen sind.
2. **Bedienelemente ausblenden**, sonst liegen in jeder Kachel „Execute workflow“, die
   Knotenknöpfe rechts oben und der Tab-„Pill“ der Kopfleiste:
   `[data-test-id="canvas-controls"], [data-test-id="canvas-minimap"],
   [class*="executionButtons"], [data-test-id="canvas-node-toolbar"],
   [data-test-id="canvas-handle-plus-wrapper"], [class*="_nodeButtonsWrapper"]
   { display: none !important; }`
   `[class*="tab-bar-container"], [class*="_main-header"] { visibility: hidden !important; }`
   (visibility statt display — die Kopfleiste bestimmt sonst das Layout mit.)
   Danach die **Maus aus der Fläche** bewegen (z. B. auf `5,800`), sonst erscheinen
   Knoten-Werkzeugleisten.
3. **Aufnahmefläche messen, nicht raten**: `[data-test-id="canvas"]` mit
   `getBoundingClientRect()` — am 2026-09-24: **1380×807,8 ab (200,65)**, Fenster
   1580×906. Das Maß ändert sich, wenn das Browserfenster anders geöffnet wird — dann
   `KLIP`/`FENSTER` in `modulbilder-plan.py` nachziehen.
4. **Maßstab setzen** mit `zoom-in-button`/`zoom-out-button` (je Klick ×1,2 bzw.
   ÷1,2). Es gibt **keinen Anschlag** nach unten: jeder Ablauf startet nach dem Laden
   auf seinem eigenen Einpasswert (gemessen → `bilder/startmassstaebe.json`).
   Erreichbar ist deshalb genau `Startwert · 1,2^k` — `modulbilder-massstaebe.py`
   rechnet diese Werte in den Plan und schreibt je Ablauf einen Aufnahmezettel;
   es ergänzt außerdem die **Schutzränder** (Notizen malen unten über ihren Rahmen
   hinaus). **Nicht auf `zoom-to-fit` verlassen** — der Knopf greift nicht immer.
5. **Verschieben** mit einem künstlichen `WheelEvent` auf `.vue-flow__pane`:
   gemessen gilt `Δtx = −0,5 · deltaX`. Also `deltaX = −2 · Δx`. Je Kachel nachrechnen,
   bis der Restversatz 0 ist (meist 2–3 Ereignisse).
6. **Warten, bis die Fläche steht.** Der Maßstab steckt in
   `style="transform: translate(…px,…px) scale(…)"` (große Werte in
   Exponentialschreibweise — Zahlen mit `-?[\d.]+(?:e[+-]?\d+)?` auslesen). Vor der
   Aufnahme zweimal im Abstand von 120 ms denselben Wert abwarten, dann noch ~0,7 s,
   sonst verschiebt die laufende Bewegung die Kachel um einige Pixel.

Kachelname: `<bild>__t<nr>__x<tx>__y<ty>__s<maßstab>.png` (tx/ty/maßstab aus der
Aufnahme, gerundet auf ganze Pixel; der Maßstab mit 5 Stellen).

### GIF-Aufnahmen (Stand 2026-09-22)

Die beiden GIFs im Kopf dieser Datei entstehen aus einem **echten Testlauf** des Bots.
Zwei Programme genügen, beide ohne Fremdpakete:

| Werkzeug | Aufgabe |
| --- | --- |
| `werkzeuge/gif-aufnahme.js` | steuert ein eigenes Brave-Fenster über das Browser-Protokoll, stellt Maßstab und Blick, löst den Testlauf aus und nimmt den Bildschirmstrom auf |
| `werkzeuge/gif-bauen.py` | rechnet die Bildfolge zum GIF (gemeinsame Farbtabelle, Originalzeit, Mitlauf-Beschnitt) |

Gesamtbild (der ganze Bot in Bewegung):

```bash
cd ../..
node werkzeuge/gif-aufnahme.js aufnehmen --ablauf RadioAgentBot \
  --ziel /tmp/gif-lauf/gesamt --dauer 26 --vorlauf 6 --befehl "spiele nirvana lithium"
python3 werkzeuge/gif-bauen.py /tmp/gif-lauf/gesamt \
  ../../Ai_Radio_Moderator_Bot/ANHANG/bilder/bot-lauf-gesamt.gif \
  --abschnitte "6,6:15,6" --zeitgleich --luecke-max 250 --breite 1000 --farben 48 \
  --inhalt --inhalt-rand 2 --rahmen 1
```

`--inhalt` schneidet **eng auf die Knotenrechtecke** (die Grenze wird im Browser an
allen `.vue-flow__node` gemessen und im Bericht abgelegt), `--inhalt-rand 2` lässt
2 % Luft, `--rahmen 1` zieht eine feine graue Linie — sonst verschwimmt die helle
n8n-Fläche mit einem weißen Seitenhintergrund.

Kamerafahrt (derselbe Lauf auf einer größeren Zeichenfläche; der Blick wird in der
Nachbearbeitung gesetzt):

```bash
node werkzeuge/gif-aufnahme.js aufnehmen --ablauf RadioAgentBot \
  --ziel /tmp/gif-lauf/gross --fenster 3200x2200 --massstab 0.36 --dauer 24 \
  --vorlauf 6 --befehl "spiele nirvana lithium"
python3 werkzeuge/gif-bauen.py /tmp/gif-lauf/gross \
  ../../Ai_Radio_Moderator_Bot/ANHANG/bilder/bot-lauf-kamera.gif \
  --abschnitte "6,4:15,1" --mitlaufen 12 --fenster 1300x740 --breite 860 --farben 40 \
  --zeitgleich --luecke-max 250 --rahmen 1
```

`--mitlaufen` braucht keinen Zeitplan: je Bild wird die Fläche bestimmt, die sich zum
vorigen Bild geändert hat (Schwelle 12), über 0,6 s geglättet und als Ausschnitt
herausgeschnitten. Die Kamera trifft den Lauf dadurch von selbst — und bleibt an der
Stelle, an der gerade etwas passiert.

**Was am 2026-09-22 durchgemessen wurde** (sieben Punkte, ohne die es nicht geht):

1. **Nur ein Lauf aus der Oberfläche wird gezeichnet.** Wird der Testeingang über die
   Produktivadresse `/webhook/DEIN-WEBHOOK-PFAD` ausgelöst, ändert sich das Bild **gar
   nicht** — 328 Bilder, alle bitgleich. Richtig ist: im Editor
   `execute-workflow-button-Test-Eingang` anklicken und dann
   `POST /webhook-test/DEIN-WEBHOOK-PFAD?schluessel=…` senden.
2. **Der ganze Lauf dauert nur rund 5 Sekunden.** Einzelbilder über
   `Page.captureScreenshot` brauchen etwa 140 ms (rund 7 Bilder je Sekunde) — zu grob.
   Deshalb `Page.startScreencast` (JPEG): es zeichnet bei jeder Neuzeichnung, gemessen
   40 bis 240 ms Abstand.
3. **Der Bildstrom liefert die ganze Seite**, nicht die Zeichenfläche. Der Beschnitt
   kommt deshalb aus `masse` in `aufnahme.json` (Fläche ab 200,65 in 2400×1400).
4. **Maßstab und Blick**: Das Mausrad **verschiebt nur** (Faktor −0,5 je Einheit),
   Strg ändert nichts, der Maßstab geht **nur über die Knöpfe** (×1,2 je Klick).
   Genauer als ein halber Knopfschritt geht es nicht — sonst pendelt die Regelung.
   Die Verschiebung liegt auf `.vue-flow__transformationpane` (nicht auf
   `.vue-flow__viewport`), am Zahlenwert der `matrix(…)`.
5. **Die Knöpfe erst nach dem Einstellen ausblenden.** Wer zuerst ausblendet, klickt
   ins Leere (makelloser Standbild-Effekt: alle 328 Bilder gleich).
6. **Das schönste Bild kommt zuletzt**: die grünen Kanten des Ergebnisses zeichnet n8n
   erst bei etwa 15 s — vorher passiert nur das Aufleuchten der Knoten.
7. **Anmeldung**: Das Aufnahmeprofil `~/gif-aufnahme-profil-brave` enthält eine Kopie
   der n8n-Kekse aus dem eigenen Brave-Profil. Es ist deshalb wie ein Zugangswert zu
   behandeln (nur dem eigenen Benutzer lesbar). Wer es löscht, muss sich einmal von
   Hand anmelden (`node werkzeuge/gif-aufnahme.js anmelden`).

Beide GIFs sind absichtlich unter 5 MB gehalten (Zielgröße für die Dokumentation);
Stellschrauben sind `--breite`, `--farben` und `--jedes`.

**Fassung für einen Beitrag** (Webseite, Blog, Chat): 800 Punkte breit, ohne Rahmen,
mit Beschriftung im Bild. Die Leiste sitzt oben, ist 30 Punkte hoch und wird von
DejaVu Sans Bold gesetzt:

```bash
python3 werkzeuge/gif-bauen.py /tmp/gif-lauf/gesamt \
  ../../Ai_Radio_Moderator_Bot/ANHANG/bilder/bot-lauf-gesamt-web.gif \
  --abschnitte "6,6:15,6" --zeitgleich --luecke-max 250 --breite 800 --farben 48 \
  --inhalt --inhalt-rand 2 \
  --titel "Radio-Agent · Testlauf — der ganze Ablauf"
```

Für die Kamerafahrt dasselbe mit `--mitlaufen 12 --fenster 1300x740 --breite 800
--farben 40 --titel "Radio-Agent · Testlauf — der Blick folgt dem Lauf"`.
Stellschrauben für die Leiste: `--titel-hoehe`, `--titel-hintergrund` (Vorgabe
`f2f4f7`), `--titel-schrift` (Vorgabe `333b47`).


## Entwicklungsdokumente

| Datei | Inhalt |
| --- | --- |
| `entwicklung/README.md` | die **Arbeitsdokumentation** des Projekts: jede Änderung, jede Messung und jeder Fallstrick in der Reihenfolge ihres Entstehens (rund 1.660 Zeilen) |
| `entwicklung/ARCHITEKTUR.md` | Architektur in Kurzform: Stufen 0–3, Knotenzahlen, Vorschläge zum Vereinfachen |

Die Dokumente der Werkzeuge und des Dienstes stehen direkt bei ihren Ordnern:
`werkzeuge/README.md` (Bauen, Einspielen, Prüfen), `dienst/README.md` und
`dienst/sprachmodell.md` (Sprachdienst), `werkzeuge/meldungen/README.md` (Postfach),
`werkzeuge/playlist/README.md` (Listen), `werkzeuge/tempo/README.md` (Tempo-Änderung).

## Der Projektordner

**Alles liegt in einem Ordner**:

```
README.md                            Einstieg, Fähigkeiten, Systemüberblick
HINWEIS.md                           Hinweis zu dieser Fassung (Platzhalter)
charakter.md                         der Charakter der Stimme (Rolle und Ton für alle Modell-Antworten)
LICENSE                              Lizenz (MIT)
DOKU/                                die vier Bände (HANDBUCH, BETRIEB, BAU, STIMME)
NACHBAU/                             Anleitung zum Nachbauen, Einrichtungs-Dokumente, Vorlagen
dienst/                              die Module des Sprachdienstes radio-tts (+ whisper/, whisper-amd/)
werkzeuge/                           Bauen, Einspielen, Prüfen; `doku/` = Werkstatt dieser Sammlung
ANHANG/                              Beilagen (n8n-Heft, Zeichenflächen, Bilder, Entwicklungsdokumente)
EN/                                  dieselbe Sammlung auf Englisch
```

Die früheren Versionssicherungen (`fassungen/`, v1–v21) wurden entfernt und liegen
gesammelt außerhalb des Projekts unter `<projektordner>/sicherungen/`.

**Zugangsdaten stehen bewusst nicht in der Dokumentation** — nur die Orte, an denen
sie liegen (siehe `README.md`, Abschnitt 6 und `NACHBAU/zugangsdaten/UEBERSICHT.md`).
