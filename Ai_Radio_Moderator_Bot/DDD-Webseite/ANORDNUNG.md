# Zeichenfläche der Abläufe der DDD-Webseite-Fassung (erzeugt)

Diese Datei wird **erzeugt**, nicht von Hand gepflegt:

```bash
cd DDD-Webseite
python3 ../werkzeuge/anordnung-uebersicht.py \
  /tmp/ddd-webseite-konfiguration.json /tmp/ddd-webseite-werkzeuge.json \
  /tmp/ddd-webseite-agent.json -o ANORDNUNG.md
```

Sie zeigt, was auf der Fläche steht — welcher Rahmen welche Aufgabe hat und
was unter jedem Knoten als Notiz steht. Die Fassung enthält **fünf** Abläufe
für **einen zweisprachigen Bot** (deutsche und englische Nachrichten im selben
Chat):

| Ablauf | Kennung | Aufgabe |
| --- | --- | --- |
| DDD-Webseite-Konfiguration | `DDD-Webseite-Konfiguration` | alle Adressen, Schlüssel und Aufgabentexte |
| DDD-Webseite-Radio | `DDD-Webseite-Radio` | Titel suchen, Richtung, was läuft (zweisprachig) |
| DDD-Webseite-AzuraCast | `DDD-Webseite-AzuraCast` | Sender-Schnittstelle nachschlagen und aufrufen |
| DDD-Webseite-Meldungen | `DDD-Webseite-Meldungen` | Postfach und Ansagen (Dienst ddd-radio) |
| DDD-Webseite-Bot | `DDD-Webseite-Bot` | der Telegram-Agent (DE/EN) |

## DDD-Webseite Konfiguration - alle Werte

2 Knoten in 2 Rahmen. Jeder Knoten traegt seine Erklaerung als Notiz unter dem Namen.

### Zentrale Werte  ·  `Notiz Zentrale`

Hier stehen alle Adressen, Schluessel und Aufgabentexte. Geaendert wird nur der Knoten **Werte** - danach speichern, kein Neustart.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Eingang` | — (nur im Notizfeld) | -1280, 0 |
| `Werte` | — (nur im Notizfeld) | -1000, 0 |

### DDD-Webseite Konfiguration - alle Werte  ·  `Notiz Doku`

EINE Stelle fuer den ganzen Bot: Adressen, Schluessel, Modell, Aufgabentexte. Bearbeitet wird nur der Knoten 'Werte' (Code). Speichern genuegt, kein Neustart. Alle vier Ablaeufe holen die Werte beim Start ueber den Knoten 'Konfiguration'. Aendern: DDD-Webseite/werkzeuge/agent-wf-bauen-ddd.py (KONFIG), dann bauen-de.sh + einspielen.sh

*(Uebersichtskasten ohne Knoten)*

## DDD-Webseite Werkzeug Radio

17 Knoten in 7 Rahmen. Jeder Knoten traegt seine Erklaerung als Notiz unter dem Namen.

### Weichen  ·  `Notiz W Weichen`

Richtung, Zustand oder Titelsuche - eines von drei.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Eingang` | Felder des Werkzeugs: suchtext, richtung, frage, einreihen. | -900, 0 |
| `Konfiguration` | Alle Adressen, Schluessel und Aufgabentexte (Ablauf DDD-Webseite-Konfiguration). | -900, 260 |
| `Richtung?` | Ja = Stimmung/Genre/Jahrzehnt -> Vorschlaege holen und den ersten spielen. | -660, 0 |
| `Nur Status?` | Ja = Frage zum Programm, keine Suche. | -420, 0 |

### Zweig: Richtung  ·  `Notiz W Richtung`

Stimmung, Genre oder Jahrzehnt aus dem Katalogdienst.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Richtung suchen` | Katalogdienst nach Stimmung, Genre oder Jahrzehnt. | -420, -480 |
| `Vorschlaege aufbereiten` | Macht aus den Vorschlaegen einen ersten Titel oder eine Liste. | -180, -480 |

### Zweig: Titel suchen  ·  `Notiz W Suche`

Katalogdienst (unscharf) und Volltextsuche des Senders.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Suche klug` | Unscharfe Suche im Katalogdienst (tippfehlertolerant). | -420, 706 |
| `Suche Sender` | Volltextsuche des Senders als zweite Quelle. | -180, 706 |
| `Treffer aufbereiten` | Treffer beider Quellen zu einer kurzen Liste machen. | 60, 706 |

### Zweig: Was laeuft  ·  `Notiz W Status`

Nur der Zustand - die Rueckgabe ist der Text.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `NowPlaying` | Was laeuft, was kommt danach, wie viele Zuhoerer. | -420, 1134 |
| `Status aufbereiten` | Formuliert den Zustand als Text (Rueckgabe des Werkzeugs). | -180, 1134 |

### Abspielen  ·  `Notiz W Abspielen`

Ohne Pfad wird nichts eingetragen - dann bleibt es bei einer Auswahlliste. Mit Pfad: erst die unterbrechende Warteschlange leeren, dann sofort oder hinten an.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Treffer da?` | Ja = es gibt einen Titel, der laufen soll. | 540, 0 |
| `Einreihen?` | Ja = nur einreihen, nicht unterbrechen. | 780, 0 |
| `Warteschlange leeren` | Leert die unterbrechende Warteschlange des Senders. | 1020, -260 |
| `Sofort eintragen` | Traegt den Titel sofort in die unterbrechende Warteschlange ein. | 1260, -260 |
| `Danach eintragen` | Haengt den Titel hinter das Laufende. | 1260, 180 |

### Ausgabe  ·  `Notiz W Ausgabe`

Hier endet der Werkzeug-Ablauf - der Text geht an den Agenten zurueck.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Ergebnis` | Ausgabeknoten: hier endet der Werkzeug-Ablauf. | 1700, 0 |

### DDD-Webseite Werkzeug Radio  ·  `Notiz Doku`

Unterschnittstelle des Agenten fuer Musik: Weichen, Titel suchen, Richtung, Zustand, abspielen. Aufgerufen wird sie ueber die Werkzeugknoten des Agenten (Werkzeug Titel suchen usw.). Der Plan ist die Quelle: DDD-Webseite/werkzeuge/agent-wf-bauen-ddd.py (W_ANORDNUNG, W_BEREICHE). Aendern/Pruefen wie beim Agenten; Beschreibung: HANDBUCH.md, HANDBUCH.md, ANHANG/n8n-oberflaeche.html

*(Uebersichtskasten ohne Knoten)*

## DDD-Webseite Bot - Telegram-Agent (DE/EN)

83 Knoten in 10 Rahmen. Jeder Knoten traegt seine Erklaerung als Notiz unter dem Namen.

### Sprachnachricht (eigener Zweig oben)  ·  `Notiz Sprachnachricht`

Datei holen, umwandeln, erkennen (Whisper auf dem ai-Server). Erkannt: weiter an **Zugang** - sonst kurze Rueckmeldung.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Datei holen` | Pfad der Sprachnachricht bei Telegram holen. | -3800, -2060 |
| `Audio laden` | Datei herunterladen (im Test ueber stimme.test_url). | -3580, -2060 |
| `Umwandeln` | Spracherkennung auf dem ai-Server (whisper.cpp, MI50). | -3360, -2060 |
| `Transkript` | Nur den Text weitergeben - gedeutet wird spaeter. | -3140, -2060 |
| `Verstanden?` | Nein = nichts verstanden, kurze Rueckmeldung. | -2920, -2060 |
| `Gehoert Text` | Zeigt zur Kontrolle, was verstanden wurde. | -2700, -2060 |

### Eingang und Zugang  ·  `Notiz Eingang`

Zwei Eingaenge; nur der Betreiber kommt durch (Liste `erlaubte`). Die kurzen Wege senden ueber **Senden (Kurzmeldung)**.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Telegram Trigger` | Eingang im Betreiberchat: Nachrichten und Knopfdruecke. | -4200, -1380 |
| `Test-Eingang` | Nur zum Pruefen: nimmt eine Telegram-Nachricht als JSON an. | -4200, -1060 |
| `Konfiguration` | Alle Werte an einer Stelle | -4200, -700 |
| `Weiche Plan?` | Nachricht oder Zeitplan? | -4200, -520 |
| `Eingabe` | Nachricht, Sprache, Knopfdruck | -3980, -1220 |
| `Sprachnachricht?` | Ja = Sprachnachricht, eigener Zweig oben. | -3760, -1220 |
| `Zugang` | Nur der Betreiber | -3200, -1220 |
| `Kein Zugang` | Kurze Absage. | -2980, -1500 |
| `Freigegeben?` | Nein = Absage, der Lauf endet. | -2980, -1220 |
| `Kein Text` | Kurze Rueckfrage bei Nachrichten ohne Text. | -2100, -700 |
| `Senden (Kurzmeldung)` | Kurzer Weg, gleicher Aufruf | -1880, -700 |

### Dienste: Wiedergabelisten und Meldungen  ·  `Notiz Dienste`

Knopf oder Text -> **Dienst Art** -> **Meldung?** -> Modul im Dienst ddd-radio. Listen merken sich die Auswahl, Meldungen kommen als Karte mit Knoepfen. Textnachrichten laufen ueber **Text da?** weiter in die Analyse.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Dienst Art` | Knopf oder Text fuer einen Dienst? | -2760, 578 |
| `Dienst?` | Ja = eigener Dienst-Zweig | -2540, 578 |
| `Meldung?` | Meldung oder Wiedergabeliste? | -2320, 838 |
| `Listen Dienst` | Modul playlist.py im Dienst | -2320, 1098 |
| `Meldung Dienst` | Modul meldungen.py im Dienst | -2320, 1358 |
| `Text da?` | Nein = Knopf, Bild oder Sticker ohne Text. | -2100, 838 |
| `Dienst Antwort` | Text und Knoepfe aufbereiten | -2100, 1358 |
| `Auftrag` | Kontext fuer die Analyse | -1880, 838 |
| `Dienst Senden` | sendMessage / editMessageText | -1880, 1358 |
| `Senden fehlgeschlagen?` | Ja = neue Nachricht senden | -1660, 1358 |
| `Dienst Ersatz senden` | Zweiter Versuch per sendMessage | -1440, 1358 |
| `Ende` | Ausgabe des Dienst-Zweigs | -1220, 1358 |

### Postfach (Suchbot -> Moderator)  ·  `Notiz Postfach`

Alle 5 Minuten: neue Meldungen holen und als Karte mit Knoepfen vorlegen. **Meldung anbieten** merkt sie als angeboten - kein zweites Angebot.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Zeitplan Meldungen` | Alle 5 Minuten: Postfach abfragen. | -2760, 1768 |
| `Meldungen holen` | Holt neue Meldungen aus dem Postfach (nur_neue=1 = noch nicht angeboten). | -2540, 1768 |
| `Meldung da?` | Nein = nichts Neues, der Lauf endet hier. | -2320, 1768 |
| `Meldung Karte` | Karte mit Knoepfen bauen | -2100, 1768 |
| `Angebot?` | Nur im Zeitplan-Weg | -1880, 1768 |
| `Meldung anbieten` | Als angeboten merken | -1660, 1768 |

### Stufe 0 und Stufe 1: verstehen und planen  ·  `Notiz Analyse`

**Kurz?** erkennt einfache Befehle ohne Modell, **Kurzbefehl?** schickt sie direkt in die Ausfuehrung. Sonst zerlegt **Planen** die Anweisung in einzelne Befehle.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Kurz?` | Stufe 0: ohne Sprachmodell | -1800, -128 |
| `Kurzbefehl?` | Ja = direkt ausfuehren | -1580, -128 |
| `Planen` | Stufe 1: Plan aus dem Text | -1360, -128 |
| `Plan merken` | Zaehlt die Anlaeufe (max. 3) | -1360, 132 |
| `Plan Antwort` | Liest den Text des Modells aus. | -1140, -128 |
| `Plan nochmal?` | Ja = neuer Anlauf, Nein = Ersatzweg ueber die Ausfuehrung. | -1140, 132 |
| `Plan da?` | Leer = noch einmal planen | -920, -128 |
| `Befehle lesen` | Ein Element je Befehl | -680, -128 |
| `Befehl da?` | Leer = direkt zur Antwort | -460, -128 |

### Stufe 2: Ausfuehrung im Zyklus  ·  `Notiz Ausfuehrung`

Ein Befehl je Durchlauf - Ausgang 0 = fertig, Ausgang 1 = weiter. Drei Wege: Ersatz ohne Modell, feste Steuerung, Agent mit Werkzeugen.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Schleife` | 0 = fertig, 1 = weiter | -700, 960 |
| `Direkt oder KI?` | Ja = Ersatzweg ohne Modell | -420, 960 |
| `Ersatz Werkzeug` | Werkzeug spielt selbst | -140, 700 |
| `Steuerung?` | Ja = feste Adressen | -140, 960 |
| `Postfach?` | Ja = Frage nach dem Postfach | -140, 1220 |
| `Ueberblick?` | Ja = Quellen-Ueberblick | -140, 1480 |
| `Ersatz Antwort` | Schreibt die Ausgabe in den Merker, dann zurueck in die Schleife. | 80, 700 |
| `Kurz Steuern` | Naechster Titel, Start/Stop/Neustart - feste Adressen, kein Modell. | 80, 960 |
| `Postfach holen` | Offene Meldungen holen | 80, 1220 |
| `Ausfuehren` | Ein Befehl je Durchlauf | 80, 1480 |
| `Ueberblick holen` | Beitrag holen und sprechen | 80, 1740 |
| `Sprachmodell Ausfuehren` | Sprachmodell fuer 'Ausfuehren' (Ollama ueber die OpenAI-Schnittstelle). | 80, 2000 |
| `Steuerung Antwort` | Formuliert die Antwort des Senders. | 300, 960 |
| `Postfach Antwort` | Liste als Text | 300, 1220 |
| `Ergebnis sammeln` | Schreibt die Ausgabe in den Merker, dann zurueck in die Schleife. | 300, 1480 |
| `Ueberblick Antwort` | Schreibt die Ausgabe in den Merker, dann zurueck in die Schleife. | 300, 1740 |

### Werkzeuge (Unterschnittstellen des Agenten)  ·  `Notiz Werkzeuge`

Je Werkzeug ein Knoten; er ruft den Werkzeug-Ablauf per `executeWorkflow` auf. Dateipfade und Senderaufrufe bleiben dort - das Modell sieht sie nie.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Werkzeug Titel suchen` | Werkzeug `titel_suchen` fuer Ausfuehren und Nacharbeiten. | 740, 2200 |
| `Werkzeug Richtung suchen` | Werkzeug `richtung_suchen` fuer Ausfuehren und Nacharbeiten. | 940, 2200 |
| `Werkzeug Was laeuft` | Werkzeug `was_laeuft` fuer Ausfuehren und Nacharbeiten. | 1140, 2200 |
| `Werkzeug Azura Adressen` | Werkzeug `azura_endpunkte` fuer Ausfuehren und Nacharbeiten. | 1340, 2200 |
| `Werkzeug Azura Aufruf` | Werkzeug `azura_aufruf` fuer Ausfuehren und Nacharbeiten. | 1540, 2200 |
| `Werkzeug Azura Ueberblick` | Werkzeug `azura_ueberblick` fuer Ausfuehren und Nacharbeiten. | 1740, 2200 |
| `Werkzeug Meldungen` | Werkzeug `meldungen`: Postfach und Ansagen. | 1960, 2200 |
| `Werkzeug Recherche` | Werkzeug `recherche`: Wetter, Nachrichten, Feed, Kurzinfo. | 2180, 2200 |

### Stufe 3: Pruefung, Nachfassen und Antwort  ·  `Notiz Pruefung`

**Lage holen** und **Warteschlange holen** belegen den Senderzustand, **Pruefen** urteilt je Befehl. **Nachfassen?** startet genau einen zweiten Versuch je Befehl. **Antwort bauen** fasst zusammen und baut die Knoepfe, **Senden** schickt per HTML.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Lage holen` | Was laeuft gerade - Beleg fuer die Pruefung. | 880, 960 |
| `Warteschlange holen` | Was eingereiht ist - Beleg fuer die Pruefung. | 1100, 960 |
| `Befehle und Lage` | Ausgaben + Senderzustand | 1320, 960 |
| `Pruefen?` | Nein = Urteil nach Regeln | 1540, 960 |
| `Pruefen` | Stufe 3: Urteil je Befehl | 1540, 1220 |
| `Pruefung Antwort` | Liest das Urteil des Modells aus. | 1760, 1220 |
| `Pruefung lesen` | ok und grund je Befehl | 1980, 960 |
| `Nachfassen?` | Ja = zweiter Versuch | 2200, 960 |
| `Schleife 2` | Nachfass-Durchgang | 2420, 960 |
| `Nacharbeiten` | Zweiter Versuch je Befehl | 2420, 1220 |
| `Sprachmodell Nacharbeiten` | Sprachmodell fuer 'Nacharbeiten'. | 2420, 1480 |
| `Nachtrag sammeln` | Schreibt die Ausgabe des zweiten Versuchs in den Merker. | 2640, 1220 |
| `Antwort bauen` | Zusammenfassen + Knoepfe | 2900, 960 |
| `Antwort` | Bereitet den Text fuer Telegram auf (HTML, ohne Sternchen). | 3120, 960 |
| `Senden` | sendMessage (HTML) | 3340, 960 |

### DDD-Webseite Bot - zweisprachiger Telegram-Agent (DE/EN)  ·  `Notiz Uebersicht`

EIN Bot, EIN Chat: der Betreiber schreibt deutsch oder englisch. Die Sprache wird am Eingang erkannt (Feld `sprache`) und reist mit - Kurzbefehle, Werkzeugantworten und die Antworten des Modells folgen ihr. Inhalte (Nachrichten, Wetter) und die Verwaltungswege des Dienstes bleiben deutsch. Was der Bot kann: Liedwunsch, Richtungswunsch, skip/pause/Status, Wiedergabelisten, Postfach, Recherche (Wetter, Nachrichten, RSS) und Ansagen im laufenden Programm. Alles kommt aus Telegram und geht dorthin zurueck; gespielt wird auf dem Sender "DDD-Webseite Demo" (Sender 2). Der Weg einer Nachricht: Eingang -> Stufe 0/1 Analyse -> Stufe 2 Ausfuehrung -> Stufe 3 Pruefung -> Antwort. Sprachnachrichten laufen oben durch Whisper, Dienste und Postfach haengen seitlich dran. Jeder Knoten traegt seinen Zweck als Notiz unter dem Namen, jeder Rahmen erklaert eine Stufe. Rahmenfarben: 1 Sprachnachricht | 2 Eingang | 3 Dienste | 4 Postfach | 5 Stufe 0+1 | 6 Stufe 2 + Werkzeuge | 7 Stufe 3 + Antwort Erzeugt von DDD-Webseite/werkzeuge/agent-wf-bauen-ddd.py - nie von Hand aendern. Aendern: bauen.sh, pruefen.sh, einspielen.sh. Doku: README.md (deutsch) und EN/README.md (englisch).

*(Uebersichtskasten ohne Knoten)*

### DDD-Webseite Bot - Telegram-Agent (DE/EN)  ·  `Notiz Doku`

Der Bot: Telegram-Eingang -> Stufe 0/1 (verstehen und planen) -> Stufe 2 (ausfuehren) -> Stufe 3 (Antwort). Der Plan ist die Quelle der Anordnung: DDD-Webseite/werkzeuge/agent-wf-bauen-ddd.py (ANORDNUNG, BEREICHE, KURZNOTIZ). Aendern: bauen-de.sh (erzeugt /tmp/ddd-webseite-agent.json), dann einspielen.sh Pruefen: pruefen.sh (Anordnung + Code-Knoten), Betrieb: DDD-Webseite/README.md Beschreibung: README.md, HANDBUCH.md, HANDBUCH.md, BETRIEB.md, BETRIEB.md, BETRIEB.md, BAU.md Bild fuer Bild: ANHANG/n8n-oberflaeche.html  (Projektordner Ai_Radio_Moderator_Bot)

*(Uebersichtskasten ohne Knoten)*
