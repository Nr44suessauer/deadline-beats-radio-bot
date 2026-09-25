# Zeichenfläche der Abläufe (erzeugt)

Diese Datei wird **erzeugt**, nicht von Hand gepflegt: `bash anordnung-doku.sh`
holt die laufenden Abläufe aus n8n, prüft die Zeichenfläche und schreibt die
Knotenlisten. Sie zeigt, was auf der Fläche steht — welcher Rahmen welche Aufgabe
hat und was unter jedem Knoten als Notiz steht.

Warum das wichtig ist: der Rahmen wird **aus den Positionen gerechnet**
(`werkzeuge/agent-wf-bauen.py`, Tabellen `BEREICHE`). Liegt ein Knoten außerhalb
seines Rahmens oder überlappen sich zwei Rahmen, meldet `anordnung-pruefen.py`
einen Befund. Ziel ist **0 Befunde**.

| Prüfung | Bedeutung |
| --- | --- |
| Knoten ohne Rahmen | er landet irgendwo ohne Erklärung |
| Knoten in zwei Rahmen | die Bereiche sind falsch geschnitten |
| ragt aus dem Rahmen heraus | die Fläche ist gepflegt-daneben |
| Rahmen überlagern sich | die Bereiche liegen übereinander |
| Knoten ohne Notiz | es fehlt die Beschriftung (muss jeder haben) |

Stand: 2026-09-24 (Fassung 19). Neu erzeugen: `bash anordnung-doku.sh`.

## Radio - Telegram-Agent

83 Knoten in 10 Rahmen. Jeder Knoten traegt seine Erklaerung als Notiz unter dem Namen.

### Sprachnachricht (eigener Zweig oben)  ·  `Notiz Sprachnachricht`

Datei holen, umwandeln, erkennen (Whisper auf dem ai-Server). Erkannt: weiter an **Zugang** - sonst kurze Rückmeldung.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Datei holen` | Pfad der Sprachnachricht bei Telegram holen. | -3800, -2060 |
| `Audio laden` | Datei herunterladen (im Test über stimme.test_url). | -3580, -2060 |
| `Umwandeln` | Spracherkennung auf dem ai-Server (whisper.cpp, MI50). | -3360, -2060 |
| `Transkript` | Nur den Text weitergeben - gedeutet wird später. | -3140, -2060 |
| `Verstanden?` | Nein = nichts verstanden, kurze Rückmeldung. | -2920, -2060 |
| `Gehört Text` | Zeigt zur Kontrolle, was verstanden wurde. | -2700, -2060 |

### Eingang und Zugang  ·  `Notiz Eingang`

Zwei Eingänge; nur der Betreiber kommt durch (Liste `erlaubte`). Die kurzen Wege senden über **Senden (Kurzmeldung)**.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Telegram Trigger` | Eingang im Betreiberchat: Nachrichten und Knopfdrücke. | -4200, -1380 |
| `Test-Eingang` | Nur zum Prüfen: nimmt eine Telegram-Nachricht als JSON an. | -4200, -1060 |
| `Konfiguration` | Alle Werte an einer Stelle | -4200, -700 |
| `Weiche Plan?` | Nachricht oder Zeitplan? | -4200, -520 |
| `Eingabe` | Nachricht, Sprache, Knopfdruck | -3980, -1220 |
| `Sprachnachricht?` | Ja = Sprachnachricht, eigener Zweig oben. | -3760, -1220 |
| `Zugang` | Nur der Betreiber | -3200, -1220 |
| `Kein Zugang` | Kurze Absage. | -2980, -1500 |
| `Freigegeben?` | Nein = Absage, der Lauf endet. | -2980, -1220 |
| `Kein Text` | Kurze Rückfrage bei Nachrichten ohne Text. | -2100, -700 |
| `Senden (Kurzmeldung)` | Kurzer Weg, gleicher Aufruf | -1880, -700 |

### Dienste: Wiedergabelisten und Meldungen  ·  `Notiz Dienste`

Knopf oder Text -> **Dienst Art** -> **Meldung?** -> Modul im Dienst radio-tts. Listen merken sich die Auswahl, Meldungen kommen als Karte mit Knöpfen. Textnachrichten laufen über **Text da?** weiter in die Analyse.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Dienst Art` | Knopf oder Text für einen Dienst? | -2760, 578 |
| `Dienst?` | Ja = eigener Dienst-Zweig | -2540, 578 |
| `Meldung?` | Meldung oder Wiedergabeliste? | -2320, 838 |
| `Listen Dienst` | Modul playlist.py im Dienst | -2320, 1098 |
| `Meldung Dienst` | Modul meldungen.py im Dienst | -2320, 1358 |
| `Text da?` | Nein = Knopf, Bild oder Sticker ohne Text. | -2100, 838 |
| `Dienst Antwort` | Text und Knöpfe aufbereiten | -2100, 1358 |
| `Auftrag` | Kontext für die Analyse | -1880, 838 |
| `Dienst Senden` | sendMessage / editMessageText | -1880, 1358 |
| `Senden fehlgeschlagen?` | Ja = neue Nachricht senden | -1660, 1358 |
| `Dienst Ersatz senden` | Zweiter Versuch per sendMessage | -1440, 1358 |
| `Ende` | Ausgabe des Dienst-Zweigs | -1220, 1358 |

### Postfach (Suchbot -> Moderator)  ·  `Notiz Postfach`

Alle 5 Minuten: neue Meldungen holen und als Karte mit Knöpfen vorlegen. **Meldung anbieten** merkt sie als angeboten - kein zweites Angebot.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Zeitplan Meldungen` | Alle 5 Minuten: Postfach abfragen. | -2760, 1768 |
| `Meldungen holen` | Holt neue Meldungen aus dem Postfach (nur_neue=1 = noch nicht angeboten). | -2540, 1768 |
| `Meldung da?` | Nein = nichts Neues, der Lauf endet hier. | -2320, 1768 |
| `Meldung Karte` | Karte mit Knöpfen bauen | -2100, 1768 |
| `Angebot?` | Nur im Zeitplan-Weg | -1880, 1768 |
| `Meldung anbieten` | Als angeboten merken | -1660, 1768 |

### Stufe 0 und Stufe 1: verstehen und planen  ·  `Notiz Analyse`

**Kurz?** erkennt einfache Befehle ohne Modell, **Kurzbefehl?** schickt sie direkt in die Ausführung. Sonst zerlegt **Planen** die Anweisung in einzelne Befehle.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Kurz?` | Stufe 0: ohne Sprachmodell | -1800, -128 |
| `Kurzbefehl?` | Ja = direkt ausführen | -1580, -128 |
| `Planen` | Stufe 1: Plan aus dem Text | -1360, -128 |
| `Plan merken` | Zählt die Anläufe (max. 3) | -1360, 132 |
| `Plan Antwort` | Liest den Text des Modells aus. | -1140, -128 |
| `Plan nochmal?` | Ja = neuer Anlauf, Nein = Ersatzweg über die Ausführung. | -1140, 132 |
| `Plan da?` | Leer = noch einmal planen | -920, -128 |
| `Befehle lesen` | Ein Element je Befehl | -680, -128 |
| `Befehl da?` | Leer = direkt zur Antwort | -460, -128 |

### Stufe 2: Ausführung im Zyklus  ·  `Notiz Ausführung`

Ein Befehl je Durchlauf - Ausgang 0 = fertig, Ausgang 1 = weiter. Drei Wege: Ersatz ohne Modell, feste Steuerung, Agent mit Werkzeugen.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Schleife` | 0 = fertig, 1 = weiter | -700, 960 |
| `Direkt oder KI?` | Ja = Ersatzweg ohne Modell | -420, 960 |
| `Ersatz Werkzeug` | Werkzeug spielt selbst | -140, 700 |
| `Steuerung?` | Ja = feste Adressen | -140, 960 |
| `Postfach?` | Ja = Frage nach dem Postfach | -140, 1220 |
| `Überblick?` | Ja = Quellen-Überblick | -140, 1480 |
| `Ersatz Antwort` | Schreibt die Ausgabe in den Merker, dann zurück in die Schleife. | 80, 700 |
| `Kurz Steuern` | Nächster Titel, Start/Stop/Neustart - feste Adressen, kein Modell. | 80, 960 |
| `Postfach holen` | Offene Meldungen holen | 80, 1220 |
| `Ausführen` | Ein Befehl je Durchlauf | 80, 1480 |
| `Überblick holen` | Beitrag holen und sprechen | 80, 1740 |
| `Sprachmodell Ausführen` | Sprachmodell für 'Ausführen' (Ollama über die OpenAI-Schnittstelle). | 80, 2000 |
| `Steuerung Antwort` | Formuliert die Antwort des Senders. | 300, 960 |
| `Postfach Antwort` | Liste als Text | 300, 1220 |
| `Ergebnis sammeln` | Schreibt die Ausgabe in den Merker, dann zurück in die Schleife. | 300, 1480 |
| `Überblick Antwort` | Schreibt die Ausgabe in den Merker, dann zurück in die Schleife. | 300, 1740 |

### Werkzeuge (Unterschnittstellen des Agenten)  ·  `Notiz Werkzeuge`

Je Werkzeug ein Knoten; er ruft den Werkzeug-Ablauf per `executeWorkflow` auf. Dateipfade und Senderaufrufe bleiben dort - das Modell sieht sie nie.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Werkzeug Titel suchen` | Werkzeug `titel_suchen` für Ausführen und Nacharbeiten. | 740, 2200 |
| `Werkzeug Richtung suchen` | Werkzeug `richtung_suchen` für Ausführen und Nacharbeiten. | 940, 2200 |
| `Werkzeug Was läuft` | Werkzeug `was_laeuft` für Ausführen und Nacharbeiten. | 1140, 2200 |
| `Werkzeug Azura Adressen` | Werkzeug `azura_endpunkte` für Ausführen und Nacharbeiten. | 1340, 2200 |
| `Werkzeug Azura Aufruf` | Werkzeug `azura_aufruf` für Ausführen und Nacharbeiten. | 1540, 2200 |
| `Werkzeug Azura Überblick` | Werkzeug `azura_ueberblick` für Ausführen und Nacharbeiten. | 1740, 2200 |
| `Werkzeug Meldungen` | Werkzeug `meldungen`: Postfach und Ansagen. | 1960, 2200 |
| `Werkzeug Recherche` | Werkzeug `recherche`: Wetter, Nachrichten, Feed, Kurzinfo. | 2180, 2200 |

### Stufe 3: Prüfung, Nachfassen und Antwort  ·  `Notiz Prüfung`

**Lage holen** und **Warteschlange holen** belegen den Senderzustand, **Prüfen** urteilt je Befehl. **Nachfassen?** startet genau einen zweiten Versuch je Befehl. **Antwort bauen** fasst zusammen und baut die Knöpfe, **Senden** schickt per HTML.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Lage holen` | Was läuft gerade - Beleg für die Prüfung. | 880, 960 |
| `Warteschlange holen` | Was eingereiht ist - Beleg für die Prüfung. | 1100, 960 |
| `Befehle und Lage` | Ausgaben + Senderzustand | 1320, 960 |
| `Prüfen?` | Nein = Urteil nach Regeln | 1540, 960 |
| `Prüfen` | Stufe 3: Urteil je Befehl | 1540, 1220 |
| `Prüfung Antwort` | Liest das Urteil des Modells aus. | 1760, 1220 |
| `Prüfung lesen` | ok und grund je Befehl | 1980, 960 |
| `Nachfassen?` | Ja = zweiter Versuch | 2200, 960 |
| `Schleife 2` | Nachfass-Durchgang | 2420, 960 |
| `Nacharbeiten` | Zweiter Versuch je Befehl | 2420, 1220 |
| `Sprachmodell Nacharbeiten` | Sprachmodell für 'Nacharbeiten'. | 2420, 1480 |
| `Nachtrag sammeln` | Schreibt die Ausgabe des zweiten Versuchs in den Merker. | 2640, 1220 |
| `Antwort bauen` | Zusammenfassen + Knöpfe | 2900, 960 |
| `Antwort` | Bereitet den Text für Telegram auf (HTML, ohne Sternchen). | 3120, 960 |
| `Senden` | sendMessage (HTML) | 3340, 960 |

### Radio - Telegram-Agent (Deadline Beats)  ·  `Notiz Übersicht`

Was der Bot kann: Liedwunsch, Richtungswunsch, skip/pause/Status, Wiedergabelisten, Postfach, Recherche (Wetter, Nachrichten, RSS) und Ansagen im laufenden Programm. Alles kommt aus Telegram und geht dorthin zurück. Der Weg einer Nachricht: Eingang -> Stufe 0/1 Analyse -> Stufe 2 Ausführung -> Stufe 3 Prüfung -> Antwort. Sprachnachrichten laufen oben durch Whisper, Dienste und Postfach hängen seitlich dran. Jeder Knoten trägt seinen Zweck als Notiz unter dem Namen, jeder Rahmen erklärt eine Stufe. Rahmenfarben: 1 Sprachnachricht | 2 Eingang | 3 Dienste | 4 Postfach | 5 Stufe 0+1 | 6 Stufe 2 + Werkzeuge | 7 Stufe 3 + Antwort Erzeugt von werkzeuge/agent-wf-bauen.py - nie von Hand ändern. Ändern: agent-patchen.sh --inhalt ... dann agent-einspielen-nur.sh. Doku: README.md Abschnitt 8 bis 12 und werkzeuge/README.md.

*(Uebersichtskasten ohne Knoten)*

### Radio - Telegram-Agent  ·  `Notiz Doku`

Der Bot: Telegram-Eingang -> Stufe 0/1 (verstehen und planen) -> Stufe 2 (ausführen) -> Stufe 3 (Antwort). Der Plan ist die Quelle der Anordnung: werkzeuge/agent-wf-bauen.py (ANORDNUNG, BEREICHE, KURZNOTIZ). Ändern: agent-patchen.sh --aufraeumen -> agent-einspielen-nur.sh /tmp/radio-agent-neu.json -> docker restart n8n Prüfen: anordnung-pruefen.py (0 Befunde), code-pruefen.py (0 fehlerhafte Code-Knoten), DOKU/BETRIEB.md Beschreibung: README.md, DOKU/HANDBUCH.md, DOKU/HANDBUCH.md, DOKU/BETRIEB.md, DOKU/BETRIEB.md, DOKU/BETRIEB.md, DOKU/BAU.md Bild für Bild: ANHANG/n8n-oberflaeche.html  (Projektordner Ai_Radio_Moderator_Bot)

*(Uebersichtskasten ohne Knoten)*

## Werkzeug - Radio

17 Knoten in 7 Rahmen. Jeder Knoten traegt seine Erklaerung als Notiz unter dem Namen.

### Weichen  ·  `Notiz W Weichen`

Richtung, Zustand oder Titelsuche - eines von drei.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Eingang` | Felder des Werkzeugs: suchtext, richtung, frage, einreihen. | -900, 0 |
| `Konfiguration` | Alle Adressen, Schluessel und Aufgabentexte (Ablauf Konfiguration). | -900, 260 |
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
| `Suche klug` | Unscharfe Suche im Katalogdienst (tippfehlertolerant). | -420, 688 |
| `Suche Sender` | Volltextsuche des Senders als zweite Quelle. | -180, 688 |
| `Treffer aufbereiten` | Treffer beider Quellen zu einer kurzen Liste machen. | 60, 688 |

### Zweig: Was laeuft  ·  `Notiz W Status`

Nur der Zustand - die Rueckgabe ist der Text.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `NowPlaying` | Was laeuft, was kommt danach, wie viele Zuhoerer. | -420, 1116 |
| `Status aufbereiten` | Formuliert den Zustand als Text (Rueckgabe des Werkzeugs). | -180, 1116 |

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

### Werkzeug - Radio  ·  `Notiz Doku`

Unterschnittstelle des Agenten fuer Musik: Weichen, Titel suchen, Richtung, Zustand, abspielen. Aufgerufen wird sie ueber die Werkzeugknoten des Agenten (Werkzeug Titel suchen usw.). Der Plan ist die Quelle: werkzeuge/agent-wf-bauen.py (W_ANORDNUNG, W_BEREICHE). Aendern/Pruefen wie beim Agenten; Beschreibung: DOKU/HANDBUCH.md, DOKU/HANDBUCH.md, ANHANG/n8n-oberflaeche.html

*(Uebersichtskasten ohne Knoten)*

## Werkzeug - AzuraCast

17 Knoten in 5 Rahmen. Jeder Knoten traegt seine Erklaerung als Notiz unter dem Namen.

### Weichen  ·  `Notiz AZ Weichen`

Adressen nachschlagen, eine Schnittstelle aufrufen oder Ueberblick geben.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Eingang` | Felder des Werkzeugs: suche, methode, pfad, koerper, bestaetigt, frage. | -900, 0 |
| `Konfiguration` | Alle Adressen, Schluessel und Aufgabentexte (Ablauf Konfiguration). | -900, 260 |
| `Adressen suchen?` | Ja = Adressen der Senderschnittstelle nachschlagen. | -660, 0 |
| `Aufruf?` | Ja = eine Schnittstelle des Senders aufrufen. | -420, 0 |

### Zweig: Adressen  ·  `Notiz AZ Adressen`

Das Verzeichnis des Katalogdienstes nach Adressen durchsuchen.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Beschreibung holen` | Adressverzeichnis vom Katalogdienst holen. | -420, -480 |
| `Adressen finden` | Kurze Liste der passenden Adressen mit Feldern. | -180, -480 |

### Zweig: Aufruf  ·  `Notiz AZ Aufruf`

**Wache** prueft Methode und Pfad; Aendern nur mit `bestaetigt: true`. Zwei Schritte: Trockenlauf zurueckgeben oder wirklich aufrufen.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Wache` | Prueft Methode und Pfad - Schreiben nur mit bestaetigt=true. | 300, 0 |
| `Ausfuehren?` | Ja = aufrufen, Nein = Trockenlauf zurueckgeben. | 540, 0 |
| `Nur lesen?` | Ja = GET (lesen), Nein = aendern (POST/PUT/DELETE). | 780, 0 |
| `Trockenlauf` | Zeigt, was der Aufruf taete, ohne etwas zu aendern. | 780, 560 |
| `Lesen` | Liest vom Sender. | 1020, 220 |
| `Schreiben` | Aendert am Sender - nur nach ausdruecklicher Bestaetigung. | 1020, 460 |
| `Aufruf Ergebnis` | Antwort des Senders kurz zusammengefasst. | 1260, 0 |

### Zweig: Ueberblick  ·  `Notiz AZ Ueberblick`

Anlagen, Sendeteil, Ausgabe und Wiedergabelisten in einem Text.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Anlagen` | Anlagen und ob Sendeteil und Ausgabe laufen. | -420, 1020 |
| `Zustand` | Zustand von Sendeteil und Ausgabe. | -180, 1020 |
| `Wiedergabelisten` | Wiedergabelisten mit Titelzahl. | 60, 1020 |
| `Ueberblick` | Fasst den Ueberblick als Text zusammen. | 300, 1020 |

### Werkzeug - AzuraCast  ·  `Notiz Doku`

Unterschnittstelle fuer den Sender: Adressen nachschlagen, Schnittstelle aufrufen, Ueberblick. Die Adressen kommen aus der OpenAPI-Beschreibung des Senders (263 Endpunkte). Der Plan ist die Quelle: werkzeuge/agent-wf-bauen.py (W_ANORDNUNG_AZ, W_AZ_BEREICHE). Aendern/Pruefen wie beim Agenten; Beschreibung: DOKU/HANDBUCH.md, ANHANG/n8n-oberflaeche.html

*(Uebersichtskasten ohne Knoten)*

## Werkzeug - Meldungen

14 Knoten in 6 Rahmen. Jeder Knoten traegt seine Erklaerung als Notiz unter dem Namen.

### Weichen  ·  `Notiz M Weichen`

Recherche, Ansage, Verwerfen oder Sprechtext - der Auftrag entscheidet. Jede Weiche prueft ein Feld des Werkzeugs.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Eingang` | Felder des Werkzeugs: auftrag, kennung, text, art, wort, ansagen. | -900, 120 |
| `Konfiguration` | Alle Adressen, Schluessel und Aufgabentexte (Ablauf Konfiguration). | -900, 380 |
| `Recherche?` | Ja = recherchieren (art=wetter, nachrichten, rss oder wikipedia). | -660, 120 |
| `Sprechen?` | Ja = eine Ansage sprechen (auftrag ansagen oder text). | -660, 380 |
| `Freier Text?` | Ja = freier Text, Nein = Meldung aus dem Postfach. | -420, 160 |
| `Verwerfen?` | Ja = Meldung als verworfen weglegen. | -420, 620 |
| `Kennung?` | Ja = Sprechtext zeigen, Nein = offene Meldungen auflisten. | -420, 880 |

### Recherche  ·  `Notiz M Recherche`

Wetter, Nachrichten, Feed oder Kurzinfo holen, als Meldung ablegen und ansagen.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Recherche holen` | Holt die Daten, legt sie als Meldung ab und sagt sie bei ansagen=true an. | 400, -140 |

### Ansagen  ·  `Notiz M Ansage`

Freien Text oder eine abgelegte Meldung live in den Sender sprechen.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Freie Ansage` | Spricht freien Text live in den Sender. | 400, 324 |
| `Meldung ansagen` | Spricht eine abgelegte Meldung live in den Sender. | 400, 544 |

### Postfach  ·  `Notiz M Postfach`

Offene Meldungen auflisten, Sprechtext zeigen oder eine Meldung verwerfen.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Meldung verwerfen` | Setzt die Meldung auf verworfen. | 400, 972 |
| `Sprechtext holen` | Zeigt den Text, den der Moderator sprechen wuerde. | 400, 1232 |
| `Offene holen` | Offene Meldungen (wichtige zuerst). | 400, 1492 |

### Ausgabe  ·  `Notiz M Ausgabe`

Hier endet der Werkzeug-Ablauf - der Text geht an den Agenten zurueck.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Ergebnis Meldungen` | Ausgabeknoten: hier endet der Werkzeug-Ablauf. | 900, 620 |

### Werkzeug - Meldungen  ·  `Notiz Doku`

Unterschnittstelle fuer Ansage und Postfach: Recherche, freie Ansage, Meldung sprechen/verwerfen. Spricht ueber den Dienst radio-tts (Piper + DJ-Hafen), legt Meldungen im Postfach ab. Der Plan ist die Quelle: werkzeuge/agent-wf-bauen.py (W_MELD_ANORDNUNG, W_MELD_BEREICHE). Aendern/Pruefen wie beim Agenten; Beschreibung: DOKU/HANDBUCH.md §1.3, DOKU/HANDBUCH.md

*(Uebersichtskasten ohne Knoten)*

## Radio - AI-Moderator

19 Knoten in 7 Rahmen. Jeder Knoten traegt seine Erklaerung als Notiz unter dem Namen.

### Eingänge  ·  `Notiz Eingänge`

Von Hand, per Formular oder von außen starten - alles läuft in dieselbe Kette.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Manuell` | Von Hand starten (Prüflauf). | -660, -140 |
| `Formular` | Start über das n8n-Formular: Titel, Wunschtext, Stimme. | -660, 40 |
| `Webhook` | Start von außen (Zeitplan oder fremdes Werkzeug). | -660, 260 |

### Kontext  ·  `Notiz Kontext`

Was läuft gerade, und was ist zuletzt passiert? Das ist die Grundlage für den Moderationstext.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Felder` | Eingaben sammeln: Titel, Wunschtext, Stimme, Ansage ja/nein. | -408, 40 |
| `Jetzt läuft` | Was läuft gerade am Sender? (AzuraCast) | -208, 40 |
| `Recherche` | Meldungen und Kontext für die Moderation sammeln. | -8, 40 |

### Text und Stimme  ·  `Notiz Text und Stimme`

Aus dem Kontext wird ein Sprechtext, daraus eine fertige Datei.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Moderationstext` | Den Sprechtext vom Sprachmodell (Ollama) erzeugen lassen. | 240, 40 |
| `Text säubern` | Sprechtext aufbereiten: Links, Emoji, Abkürzungen, Satzgrenze. | 440, 40 |
| `Stimme` | Sprache erzeugen (Piper im Dienst radio-tts). | 640, 40 |
| `Dateiname` | Dateinamen der Ansage bauen. | 840, 40 |

### Ausgabe  ·  `Notiz Ausgabe`

Entweder live sprechen (unterbricht das Programm kurz) oder hochladen (läuft danach als eigener Titel).

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Modus` | Ja = live sprechen, nein = hochladen. | 1088, 40 |
| `Live sprechen` | Die Ansage live in den DJ-Hafen sprechen. | 1308, -15 |
| `Hochladen` | Die Ansage als Titel hochladen (Weg ohne Unterbrechung). | 1308, 160 |

### Nachverfolgung  ·  `Notiz Nachverfolgung`

Nach dem Hochladen: warten, den Titel im Archiv finden, den Wunsch zuordnen und abgeben.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Warten` | Warten, bis der Sender den Titel verarbeitet hat. | 1556, 160 |
| `Titel finden` | Den frisch hochgeladenen Titel im Archiv suchen. | 1748, 160 |
| `Zuordnen` | Wunsch und gefundenen Titel einander zuordnen. | 1956, 160 |
| `Wunsch abgeben` | Den Wunsch beim Sender abgeben. | 2148, 160 |
| `Antwort` | Antwort für den Aufrufer bauen. | 2356, 40 |

### Alte Hilfsmittel  ·  `Notiz Alte Hilfsmittel`

Reste der ersten Fassung - nicht angeschlossen, nur zur Erinnerung.

| Knoten | Erklaerung (Notiz am Knoten) | Position |
| --- | --- | --- |
| `Treffer wählen` | Alter Helfer: ersten Treffer der Suche wählen (nicht mehr verbunden). | 780, 1056 |

### Radio - AI-Moderator (Archiv)  ·  `Notiz Doku`

Erste Fassung der Moderation: Text erzeugen, sprechen, in den Sender stellen. NICHT in Betrieb - im Betrieb moderiert der Agent (RadioAgentBot) über den Dienst radio-tts. Rahmen und Beschriftungen: werkzeuge/archiv-rahmen.py (nicht im Bauwerkzeug). Beschreibung: DOKU/BAU.md, DOKU/HANDBUCH.md, ANHANG/n8n-oberflaeche.html (Abschnitt 16).

*(Uebersichtskasten ohne Knoten)*

