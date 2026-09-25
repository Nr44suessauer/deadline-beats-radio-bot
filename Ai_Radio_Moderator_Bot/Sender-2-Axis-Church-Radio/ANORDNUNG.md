## DDD-Webseite Konfiguration - alle Werte

2 Knoten in 2 Rahmen. Jeder Knoten traegt seine Erklaerung als Notiz unter dem Namen.

### Zentrale Werte  ·  `Notiz Zentrale`

Hier stehen alle Adressen, Schluessel und Aufgabentexte. Geaendert wird nur der Knoten **Werte** - danach speichern, kein Neustart.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Eingang` | — (nur im Notizfeld) | -1280, 0 |
| `Werte` | — (nur im Notizfeld) | -1000, 0 |

### DDD-Webseite Konfiguration - alle Werte  ·  `Notiz Doku`

EINE Stelle fuer den ganzen Bot: Adressen, Schluessel, Modell, Aufgabentexte. Bearbeitet wird nur der Knoten 'Werte' (Code). Speichern genuegt, kein Neustart. Alle vier Ablaeufe holen die Werte beim Start ueber den Knoten 'Konfiguration'. Aendern: Sender-2-Axis-Church-Radio/werkzeuge/agent-wf-bauen-ddd.py (KONFIG), dann bauen-de.sh + einspielen.sh

*(Uebersichtskasten ohne Knoten)*

## DDD-Webseite Werkzeug Radio

14 Knoten in 7 Rahmen. Jeder Knoten traegt seine Erklaerung als Notiz unter dem Namen.

### Weichen  ·  `Notiz W Weichen`

Erst die Demo-Playlist holen; dann Richtung, Zustand oder Titelsuche.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Eingang` | Felder des Werkzeugs: suchtext, richtung, frage. | -900, 208 |
| `Konfiguration` | Alle Adressen, Schluessel und Aufgabentexte (Ablauf DDD-Webseite-Konfiguration). | -900, 468 |
| `Playlist holen` | Titel der festgelegten Demo-Playlist (leer = Musikwege gesperrt). | -660, 208 |
| `Richtung?` | Ja = Stimmung/Genre/Jahrzehnt -> Vorschlaege holen und den ersten spielen. | -420, 208 |
| `Nur Status?` | Ja = Frage zum Programm, keine Suche. | -420, 408 |

### Zweig: Richtung  ·  `Notiz W Richtung`

Stimmung, Genre oder Jahrzehnt aus dem Katalogdienst.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Richtung suchen` | Katalogdienst nach Stimmung, Genre oder Jahrzehnt. | -420, -220 |
| `Vorschlaege aufbereiten` | Macht aus den Vorschlaegen einen ersten Titel oder eine Liste. | -180, -220 |

### Zweig: Titel suchen  ·  `Notiz W Suche`

Nur der Katalogdienst (unscharf, tippfehlertolerant) - der Sender wird nur gelesen, nicht durchsucht.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Suche klug` | Unscharfe Suche im Katalogdienst (tippfehlertolerant). | 1240, 548 |
| `Treffer aufbereiten` | Treffer zu einer kurzen Liste machen (nur Demo-Playlist). | 1720, 428 |

### Zweig: Was laeuft  ·  `Notiz W Status`

Nur der Zustand - die Rueckgabe ist der Text.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `NowPlaying` | Was laeuft, was kommt danach, wie viele Zuhoerer. | 90, 428 |
| `Status aufbereiten` | Formuliert den Zustand als Text (Rueckgabe des Werkzeugs). | 330, 428 |

### Abspielen  ·  `Notiz W Abspielen`

Ohne Pfad wird nichts eingetragen - dann bleibt es bei einer Auswahlliste. Mit Pfad geht der Wunsch ueber die oeffentliche Wunsch-Schnittstelle des Senders (kein Schreibrecht noetig) und laeuft in Kuerze.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Treffer da?` | Ja = es gibt einen Titel, der laufen soll. | 540, 0 |
| `Wunsch anfordern` | Traegt den Wunsch ueber die oeffentliche Wunsch-Schnittstelle ein. | 800, 0 |

### Ausgabe  ·  `Notiz W Ausgabe`

Hier endet der Werkzeug-Ablauf - der Text geht an den Agenten zurueck.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Ergebnis` | Ausgabeknoten: hier endet der Werkzeug-Ablauf. | 1240, 0 |

### DDD-Webseite Werkzeug Radio  ·  `Notiz Doku`

Unterschnittstelle des Agenten fuer Musik: Weichen, Titel suchen, Richtung, Zustand, abspielen. Aufgerufen wird sie ueber die Werkzeugknoten des Agenten (Werkzeug Titel suchen usw.). Der Plan ist die Quelle: Sender-2-Axis-Church-Radio/werkzeuge/agent-wf-bauen-ddd.py (W_ANORDNUNG, W_BEREICHE). Aendern/Pruefen wie beim Agenten; Beschreibung: HANDBUCH.md, HANDBUCH.md, ANHANG/n8n-oberflaeche.html

*(Uebersichtskasten ohne Knoten)*

## DDD-Webseite Bot - Telegram-Agent (DE/EN)

87 Knoten in 10 Rahmen. Jeder Knoten traegt seine Erklaerung als Notiz unter dem Namen.

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

Drei Eingaenge (Telegram, Test, REST); Zugang ueber `erlaubte` oder Testscluessel. Kurze Wege senden ueber **Senden (Kurzmeldung)** oder **JSON antworten (kurz)**.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Telegram Trigger` | Eingang im Betreiberchat: Nachrichten und Knopfdruecke. | -4200, -1380 |
| `Test-Eingang` | Nur zum Pruefen: nimmt eine Telegram-Nachricht als JSON an. | -4200, -1060 |
| `REST-Eingang` | Befehl ohne Telegram (JSON) | -4200, -740 |
| `Konfiguration` | Alle Werte an einer Stelle | -4200, -460 |
| `Weiche Plan?` | Nachricht oder Zeitplan? | -4200, -280 |
| `Eingabe` | Nachricht, Sprache, Knopfdruck | -3980, -1220 |
| `Sprachnachricht?` | Ja = Sprachnachricht, eigener Zweig oben. | -3760, -1220 |
| `Zugang` | Nur der Betreiber | -3200, -1220 |
| `Kein Zugang` | Kurze Absage. | -2980, -1500 |
| `Freigegeben?` | Nein = Absage, der Lauf endet. | -2980, -1220 |
| `Kein Text` | Kurze Rueckfrage bei Nachrichten ohne Text. | -2100, -700 |
| `JSON? (kurz)` | Ja = Antwort als JSON | -1880, -700 |
| `JSON antworten (kurz)` | Gibt die kurze Antwort als JSON an den Aufrufer (REST/Test) zurueck. | -1660, -960 |
| `Senden (Kurzmeldung)` | Kurzer Weg, gleicher Aufruf | -1660, -700 |

### Dienste: Wiedergabelisten und Meldungen  ·  `Notiz Dienste`

Knopf oder Text -> **Dienst Art** -> **Meldung?** -> Modul im Dienst ddd-radio. Listen merken sich die Auswahl; Meldungen kommen als Karte mit Knoepfen. REST- und Testaufrufe bekommen die Ausgabe als JSON statt per Telegram. Textnachrichten laufen ueber **Text da?** weiter in die Analyse.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Dienst Art` | Knopf oder Text fuer einen Dienst? | -2760, 836 |
| `Dienst?` | Ja = eigener Dienst-Zweig | -2540, 836 |
| `Meldung?` | Meldung oder Wiedergabeliste? | -2320, 1096 |
| `Listen Dienst` | Modul playlist.py im Dienst | -2320, 1356 |
| `Meldung Dienst` | Modul meldungen.py im Dienst | -2320, 1616 |
| `Text da?` | Nein = Knopf, Bild oder Sticker ohne Text. | -2100, 1096 |
| `Dienst Antwort` | Text und Knoepfe aufbereiten | -2100, 1616 |
| `JSON antworten (dienst)` | Gibt die Dienst-Antwort als JSON an den Aufrufer (REST/Test) zurueck. | -2100, 1876 |
| `Auftrag` | Kontext fuer die Analyse | -1880, 1096 |
| `JSON? (dienst)` | Ja = Antwort als JSON | -1880, 1616 |
| `Dienst Senden` | sendMessage / editMessageText | -1880, 1876 |
| `Senden fehlgeschlagen?` | Ja = neue Nachricht senden | -1660, 1616 |
| `Dienst Ersatz senden` | Zweiter Versuch per sendMessage | -1440, 1616 |
| `Ende` | Ausgabe des Dienst-Zweigs | -1220, 1616 |

### Postfach (Suchbot -> Moderator)  ·  `Notiz Postfach`

Alle 5 Minuten: neue Meldungen holen und als Karte mit Knoepfen vorlegen. **Meldung anbieten** merkt sie als angeboten - kein zweites Angebot.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Zeitplan Meldungen` | Alle 5 Minuten: Postfach abfragen. | -2760, 2322 |
| `Meldungen holen` | Holt neue Meldungen aus dem Postfach (nur_neue=1 = noch nicht angeboten). | -2540, 2322 |
| `Meldung da?` | Nein = nichts Neues, der Lauf endet hier. | -2320, 2322 |
| `Meldung Karte` | Karte mit Knoepfen bauen | -2100, 2322 |
| `Angebot?` | Nur im Zeitplan-Weg | -1880, 2322 |
| `Meldung anbieten` | Als angeboten merken | -1660, 2322 |

### Stufe 0 und Stufe 1: verstehen und planen  ·  `Notiz Analyse`

**Kurz?** erkennt einfache Befehle ohne Modell, **Kurzbefehl?** schickt sie direkt in die Ausfuehrung. Sonst zerlegt **Planen** die Anweisung in einzelne Befehle.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Kurz?` | Stufe 0: ohne Sprachmodell | -1800, 112 |
| `Kurzbefehl?` | Ja = direkt ausfuehren | -1580, 112 |
| `Planen` | Stufe 1: Plan aus dem Text | -1360, 112 |
| `Plan merken` | Zaehlt die Anlaeufe (max. 3) | -1360, 372 |
| `Plan Antwort` | Liest den Text des Modells aus. | -1140, 112 |
| `Plan nochmal?` | Ja = neuer Anlauf, Nein = Ersatzweg ueber die Ausfuehrung. | -1140, 372 |
| `Plan da?` | Leer = noch einmal planen | -920, 112 |
| `Befehle lesen` | Ein Element je Befehl | -680, 112 |
| `Befehl da?` | Leer = direkt zur Antwort | -460, 112 |

### Stufe 2: Ausfuehrung im Zyklus  ·  `Notiz Ausfuehrung`

Ein Befehl je Durchlauf - Ausgang 0 = fertig, Ausgang 1 = weiter. Drei Wege: Ersatz ohne Modell, feste Steuerung, Agent mit Werkzeugen.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Schleife` | 0 = fertig, 1 = weiter | -700, 1060 |
| `Direkt oder KI?` | Ja = Ersatzweg ohne Modell | -420, 1060 |
| `Ersatz Werkzeug` | Werkzeug spielt selbst | -140, 800 |
| `Steuerung?` | Ja = feste Adressen | -140, 1060 |
| `Postfach?` | Ja = Frage nach dem Postfach | -140, 1320 |
| `Ueberblick?` | Ja = Quellen-Ueberblick | -140, 1580 |
| `Ersatz Antwort` | Schreibt die Ausgabe in den Merker, dann zurueck in die Schleife. | 80, 800 |
| `Kurz Steuern` | Naechster Titel - feste Adresse, kein Modell. | 80, 1060 |
| `Postfach holen` | Offene Meldungen holen | 80, 1320 |
| `Ausfuehren` | Ein Befehl je Durchlauf | 80, 1580 |
| `Ueberblick holen` | Beitrag holen und sprechen | 80, 1840 |
| `Sprachmodell Ausfuehren` | Sprachmodell fuer 'Ausfuehren' (Ollama ueber die OpenAI-Schnittstelle). | 80, 2100 |
| `Steuerung Antwort` | Formuliert die Antwort des Senders. | 300, 1060 |
| `Postfach Antwort` | Liste als Text | 300, 1320 |
| `Ergebnis sammeln` | Schreibt die Ausgabe in den Merker, dann zurueck in die Schleife. | 300, 1580 |
| `Ueberblick Antwort` | Schreibt die Ausgabe in den Merker, dann zurueck in die Schleife. | 300, 1840 |

### Werkzeuge (Unterschnittstellen des Agenten)  ·  `Notiz Werkzeuge`

Je Werkzeug ein Knoten; er ruft den Werkzeug-Ablauf per `executeWorkflow` auf. Dateipfade und Senderaufrufe bleiben dort - das Modell sieht sie nie.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Werkzeug Titel suchen` | Werkzeug `titel_suchen` fuer Ausfuehren und Nacharbeiten. | 740, 2200 |
| `Werkzeug Richtung suchen` | Werkzeug `richtung_suchen` fuer Ausfuehren und Nacharbeiten. | 940, 2200 |
| `Werkzeug Was laeuft` | Werkzeug `was_laeuft` fuer Ausfuehren und Nacharbeiten. | 1140, 2200 |
| `Werkzeug Meldungen` | Werkzeug `meldungen`: Postfach und Ansagen. | 1960, 2200 |
| `Werkzeug Recherche` | Werkzeug `recherche`: Wetter, Nachrichten, Feed, Kurzinfo. | 2180, 2200 |

### Stufe 3: Pruefung, Nachfassen und Antwort  ·  `Notiz Pruefung`

**Lage holen** und **Warteschlange holen** belegen den Senderzustand, **Pruefen** urteilt je Befehl. **Nachfassen?** startet genau einen zweiten Versuch je Befehl. **Antwort bauen** fasst zusammen und baut die Knoepfe; **Senden** schickt per HTML - oder **JSON antworten** gibt die Antwort als JSON zurueck.

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
| `JSON? (lang)` | Ja = Antwort als JSON | 3340, 960 |
| `Senden` | sendMessage (HTML) | 3560, 960 |
| `JSON antworten` | Gibt die Antwort als JSON an den Aufrufer (REST/Test) zurueck. | 3560, 1220 |

### DDD-Webseite Bot - zweisprachiger Telegram-Agent (DE/EN)  ·  `Notiz Uebersicht`

EIN Bot, EIN Chat: der Betreiber schreibt deutsch oder englisch. Die Sprache wird am Eingang erkannt (Feld `sprache`) und reist mit - Kurzbefehle, Werkzeugantworten und die Antworten des Modells folgen ihr. Inhalte (Nachrichten, Wetter) und die Verwaltungswege des Dienstes bleiben deutsch. Was der Bot kann: Musikwuensche aus der festgelegten Demo-Wiedergabeliste, "weiter" (Titelwechsel), Programmstatus, Postfach, Recherche (Wetter, Nachrichten, RSS) und Ansagen im laufenden Programm. Verwalten kann der Bot nichts: der Schluessel darf nur zuhoeren, springen und Wuensche annehmen (siehe zugangsdaten/api_key.txt). Alles kommt aus Telegram und geht dorthin zurueck - oder per REST- oder Testeingang als JSON ({"text": "..."} plus Schluessel; Antwort {ok, antwort, tastatur, sprache}). Gespielt wird auf dem Sender "Axis Church Radio" (Sender 2). Der Weg einer Nachricht: Eingang -> Stufe 0/1 Analyse -> Stufe 2 Ausfuehrung -> Stufe 3 Pruefung -> Antwort. Sprachnachrichten laufen oben durch Whisper, Dienste und Postfach haengen seitlich dran. Jeder Knoten traegt seinen Zweck als Notiz unter dem Namen, jeder Rahmen erklaert eine Stufe. Rahmenfarben: 1 Sprachnachricht | 2 Eingang | 3 Dienste | 4 Postfach | 5 Stufe 0+1 | 6 Stufe 2 + Werkzeuge | 7 Stufe 3 + Antwort Erzeugt von Sender-2-Axis-Church-Radio/werkzeuge/agent-wf-bauen-ddd.py - nie von Hand aendern. Aendern: bauen.sh, pruefen.sh, einspielen.sh. Doku: README.md (deutsch) und EN/README.md (englisch).

*(Uebersichtskasten ohne Knoten)*

### DDD-Webseite Bot - Telegram-Agent (DE/EN) mit REST-Eingang  ·  `Notiz Doku`

Der Bot: Telegram-Eingang -> Stufe 0/1 (verstehen und planen) -> Stufe 2 (ausfuehren) -> Stufe 3 (Antwort). REST-Eingang: POST .../webhook/ddd-webseite-rest mit {"text": "..."} + Schluessel - Antwort als JSON. Der Plan ist die Quelle der Anordnung: Sender-2-Axis-Church-Radio/werkzeuge/agent-wf-bauen-ddd.py (ANORDNUNG, BEREICHE, KURZNOTIZ). Aendern: bauen-de.sh (erzeugt /tmp/ddd-webseite-agent.json), dann einspielen.sh Pruefen: pruefen.sh (Anordnung + Code-Knoten), Betrieb: Sender-2-Axis-Church-Radio/README.md Beschreibung: README.md, HANDBUCH.md, HANDBUCH.md, BETRIEB.md, BETRIEB.md, BETRIEB.md, BAU.md Bild fuer Bild: ANHANG/n8n-oberflaeche.html  (Projektordner Ai_Radio_Moderator_Bot/Sender-2-Axis-Church-Radio)

*(Uebersichtskasten ohne Knoten)*
