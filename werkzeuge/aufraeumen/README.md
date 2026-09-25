# Musikarchiv aufgeräumt (2026-09-20)

Aufräumen des AzuraCast-Archivs auf dem Datenserver (LXC 106, Sender
„Deadline Beats", 56.635 Titel auf `/mnt/Content/Music`).

## Ergebnis in Zahlen

| Was | vorher | nachher |
|---|---|---|
| Titel in der Bibliothek | 56.635 | 56.635 (unverändert) |
| Live-/Bootleg-Titel im Hauptbestand | 7.906 | 0 (liegen in `_Archiv/Live/`) |
| Ordner direkt unter `Music/` | 133 | 126 |
| Dateien in `unsorted/` | 9.791 | 0 (Ordner entfernt) |
| Titel mit Tracknummer im Titel | 1.088 | 625 (441 automatisch bereinigt) |
| Titel mit Zahlen-Interpret („01") | 344 | 0 |
| Interpreten mit „feat." | 1.628 | 1 |
| Titel im Bot-Katalog | 56.635 | 48.729 |
| Wiedergabelisten-Zuordnungen | 168 | 168 (unverändert) |

## Was gemacht wurde

1. **Live-/Bootleg-Archiv getrennt.** 42 reine Live-/Bootleg-Sammelordner
   (z. B. `Nirvana …/Other/Concerts`, `…/Live`, `…/03 - Live & Bootleg`) liegen
   jetzt unter **`_Archiv/Live/<alte Struktur>`**. Offizielle Live-Alben
   („KISS – Alive II") bleiben bewusst im Hauptbestand.
2. **Doppelte Künstlerordner zusammengelegt.** Die `<Künstler> - Diskografie …`
   Ordner (21 aus `unsorted/` sowie `Led.Zeppelin.1969-2018`,
   `HammerFall - Diskografie …`, `Good Charlotte - Discography …`) liegen jetzt
   als **`<Künstler>/Diskografie/`** beim Künstler. `unsorted/` ist damit leer.
3. **Tags bereinigt** (nur in der Datenbank, es wurden keine Dateien angefasst):
   - 441 Titel ohne führende Tracknummer („01 - My Crown" → „My Crown")
   - 344 Interpreten, die nur eine Zahl waren, geleert
   - 1.635 „feat."-Interpreten getrennt: Interpret = Hauptkünstler,
     Titel bekommt `(feat. …)` angehängt
4. **Der Bot schlägt nichts aus dem Archiv vor.** Im n8n-Werkzeug
   „Werkzeug - Titel suchen" (Knoten `Treffer aufbereiten`) und im Katalogdienst
   (Modul `katalog.py`) werden Pfade mit `_Archiv/` und `moderation/`
   übersprungen.

## Wichtige Lehre: Ordner verschieben nur über die Schnittstelle

AzuraCast gleicht Medien **über den Pfad** ab (`App\Sync\Task\CheckMediaTask`:
`md5($path)`; fehlt der Pfad, wird der Datensatz gelöscht und neu angelegt).
Ein Verschieben auf der Platte kostet deshalb Medien-Kennung, `unique_id`,
Wiedergabelisten-Zuordnungen und eigene Felder.

Richtig ist die Sammelaktion:

```
PUT /api/station/1/files/batch
{"do":"move","currentDirectory":"<alt>","directory":"<neu>","dirs":[...],"files":[...]}
```

Sie schreibt den Pfad in der Datenbank mit um – alles bleibt erhalten.
Für Dateien gilt: `newPath = directory + "/" + basename(alt)`, für Ordner wird
der Präfix `currentDirectory` durch `directory` ersetzt. Nicht-Medien-Dateien
(Readme, Werbe-URLs) kennt AzuraCast nicht und müssen auf der Platte mit
`mv` mitgenommen werden.

Ebenso wichtig: `song_id` und `text` werden aus Interpret/Album/Titel
berechnet (`App\Entity\Traits\HasSongFields::updateMetaFields`,
`Song::getSongHash`). Wer in der Datenbank Titel ändert, muss beides neu
berechnen – dafür gibt es `05-tags-korrigieren.php`.

## Bewusst NICHT gemacht

- **Genre nicht umgeschrieben.** Die 288 Schreibweisen („Rock | Hard Rock | …")
  sehen unordentlich aus, aber der Katalogdienst fängt das selbst ab: er
  verwirft bei Stimmungswünschen Titel mit mehr als vier Genre-Wörtern und
  rechnet eine „Reinheit". Ein Umschreiben von 56.000 Genres hätte viel Risiko
  bei wenig Gewinn.
- **Fehlende Interpreten (556) nicht geraten.** Eine Ableitung aus dem Pfad
  wäre in vielen Fällen falsch (z. B. liegt Marilyn Manson unter
  `The Prodigy/Diskografie/Keith Flint (The Prodigy)/! Keith Flint Related/…`).
  Ein falscher Interpret schadet der Interpretensuche mehr als ein leerer.
- **Tags nicht in die Dateien geschrieben.** Der Katalogdienst und der Bot
  lesen über die AzuraCast-Schnittstelle, nicht aus den Dateien. Die
  Datenbank-Korrekturen greifen sofort. (Wird eine Datei später neu
  eingelesen, gelten wieder ihre Datei-Tags.)
- **Tracknummern mit reinem Leerzeichen** („01 Bury Me a G") blieben stehen:
  nicht von echten Titeln zu unterscheiden („10 Light Years Away",
  „48 Hours", „99 Luftballons").

## Werkzeuge (in dieser Reihenfolge ausführbar)

| Skript | Aufgabe |
|---|---|
| `01-sicherung.sh` | Datenbank-Dump + Pfad-/Zuordnungslisten nach `/root/azuracast-aufraeumen-<Stempel>/` |
| `02-live-kandidaten.sh` | ermittelt reine Live-/Bootleg-Sammelordner |
| `03-live-verschieben.sh [echt]` | verschiebt sie nach `_Archiv/Live/` (Trockenlauf ohne `echt`) |
| `04-dubletten-zusammenlegen.sh [echt]` | legt Diskografie-Ordner zum Künstler (`<Künstler>/Diskografie/`) |
| `05-tags-korrigieren.php` | Tag-Korrekturen im Container (`DRY=1 php …` für Trockenlauf) |
| `06-bot-filter.py` | fügt den Archiv-Filter in einen n8n-Ablauf ein |
| `07-bot-filter-einspielen.sh <datei> <ablauf>` | spielt den gepatchten Ablauf in n8n ein |
| `08-katalog-einspielen.sh` | baut den Katalogdienst neu und erzeugt den Katalog |
| `09-suchknoten-test.sh` | prüft den Suchknoten mit echten Daten (ohne n8n) |

Die Sicherung liegt auf dem Datenserver unter
`/root/azuracast-aufraeumen-20260920-103645/` (Datenbank-Dump 11 MB gepackt,
`medien-id-pfad.tsv`, `playlist-zuordnungen.tsv`, `live-verschieben.tsv`,
`dubletten-zusammenlegen.tsv`).

Rückweg: Verschiebungen lassen sich mit demselben Skript rückwärts machen
(`currentDirectory`/`directory` tauschen), Tag-Änderungen über den
Datenbank-Dump.
