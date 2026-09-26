# Werkzeuge (Bauen, Einspielen, Prüfen)

Alle Skripte laufen auf dem Arbeitsplatzrechner und sprechen über SSH mit den
Containern und Diensten (n8n LXC 103, Sender LXC 106, GPU-Rechner). Dieser Ordner
ist die **Werkstatt** des Bots: der Erzeuger der Abläufe, die Änderungs- und
Einspielwege, die Prüfläufe und die Werkzeuge für Bilder und Dokumentation.

**Der Bauweg in einem Satz:** `agent-wf-bauen.py` erzeugt die Abläufe
(„Konfiguration – alle Werte", den Agenten und die drei Werkzeug-Abläufe) als
JSON; `agent-patchen.sh` holt die laufende Fassung aus n8n, baut sie neu und
übernimmt Änderungen; `agent-einspielen-nur.sh` spielt alles ein und startet n8n
neu. Vor jeder Änderung `fassung-sichern.sh` laufen lassen — es sichert nach
`<projektordner>/sicherungen/radio-fassungen/` (außerhalb des Projekts).

---

## 1. Die wichtigsten Skripte

| Skript | Aufgabe |
| --- | --- |
| `agent-wf-bauen.py` | der **Erzeuger**: baut Konfiguration, Agent und die drei Werkzeug-Abläufe als JSON (`/tmp/…`) |
| `agent-patchen.sh` | holt die laufende Fassung, baut neu, übernimmt Änderungen chirurgisch → `/tmp/radio-agent-neu.json` |
| `agent-einspielen-nur.sh` | spielt Konfiguration + Agent + Werkzeuge in n8n ein und startet n8n neu |
| `konfiguration-einspielen.sh`, `konfiguration-pruefen.py` | die Zentrale „Konfiguration – alle Werte“ einspielen bzw. prüfen |
| `charakter-einspielen.py` | setzt den Charakter der Stimme aus `../charakter.md` in die laufende Zentrale – ohne Neubau und ohne n8n-Neustart (sichert vorher, prüft nachher) |
| `dienst-einspielen.sh` | kopiert die Module aus `../dienst/` in den Container, baut und startet den Dienst neu |
| `fassung-sichern.sh` | legt eine Fassungs-Sicherung an (Abläufe + Module + n8n-Datenbank + Beschreibung), außerhalb des Projektordners |
| `deutsch-texte.py` | bringt Umlaute in die Anzeigetexte der Abläufe (läuft im Bauweg mit) |
| `statische-daten-patchen.py`, `erlaubte-setzen.py`, `bot-daten-setzen.py` | statische Daten pflegen (erlaubte Chats, Testschlüssel, Chat-Kennung) |
| `anordnung-pruefen.py`, `anordnung-doku.sh` | prüfen die Zeichenfläche (0 Befunde) und schreiben `../ANHANG/ANORDNUNG.md` |
| `archiv-rahmen.py`, `doku-notiz.py`, `altfassungen-notieren.py` | Notizen und Rahmen in einzelnen Abläufen setzen |
| `kurz-test.sh`, `antwort-test.sh`, `antworten.js` | prüfen Code-Knoten ohne n8n |
| `bot-test.sh`, `frage.sh`, `knopf.sh` | Testeingang des Bots bedienen |
| `ausfuehrungen.sh`, `bot-letzte.js` | die letzten Läufe ansehen (welcher Zweig lief, Antworttext, Knöpfe) |
| `vorschau.py`, `bildplan.py`, `modulbilder-plan.py`, `bilder-stitch.py`, `gif-aufnahme.js`, `gif-bauen.py` | Bilder und Animationen des Bots erzeugen (Grundlage des n8n-Hefts) |

**Gruppen:**

| Ordner | Inhalt |
| --- | --- |
| `doku/` | die Werkstatt dieser **Dokumentations-Sammlung**: `n8n-doku-bauen.py` (HTML-Heft), `doku-pruefen.py` (Prüfung), `doc-official-bauen.py` (Veröffentlichungsfassung mit Platzhaltern), `veroeffentlichung-webseite.py` (Fassung für den Zweig `webseite`: Platzhalter, entschärfte Stimme) samt `zweig-webseite-sichern.sh` (spielt sie in den Zweig ein), `website-bruecke/` (versorgt die Website), `code-uebersetzen-en.py` (englische Code-Fassung) |
| `playlist/` | Wiedergabelisten-Aufgaben und ihre Prüfläufe |
| `meldungen/` | Postfach, Ansagen und Spracherkennung prüfen (`19-meldungen-test.py`, `21-bot-meldungen-test.py`, `23-lautstaerke-test.py`, `24-live-pegel.py`) |
| `tempo/` | die Tempo-Änderung (163 s → 1,7 s) mit ihren Messungen |
| `aufraeumen/` | die einmalige Musikarchiv-Aufräumung (2026-09-20) samt Ergebnisbericht |

---

## 2. Was vor dem ersten Lauf angepasst wird (Nachbau)

| Datei | Stelle | Im Original | Für einen Nachbau |
| --- | --- | --- | --- |
| alle `*.sh` | `CFG=~/.ssh/config` | SSH-Konfiguration des Arbeitsplatzes | eigene SSH-Konfiguration (oder direktes `ssh`) |
| alle `*.sh` | `pct exec 103` / `105` / `106` | LXC-Container-IDs des Originals | eigene Container-IDs/Hosts |
| `agent-einspielen-nur.sh`, `agent-patchen.sh` | `PROJEKT=DEINE-N8N-PROJEKT-KENNUNG` | n8n-Projektkennung | eigene Projektkennung |
| `agent-patchen.sh`, `fassung-sichern.sh` | `RADIO=<dokuordner>` | Projektordner | eigener Projektordner |
| `charakter-einspielen.py` | `CFG=…`, `PROJEKT=…` | SSH-Konfiguration und n8n-Projektkennung des Originals | eigene Werte |
| `dienst-einspielen.sh` | `QUELLE=…/../dienst` | Modulordner | passt bereits (Nachbarordner `dienst/`) |
| `bot-test.sh`, `frage.sh`, `knopf.sh` | Adresse des Testeingangs | `127.0.0.1:5678` (im n8n-Container) | eigene n8n-Adresse |
| `meldungen/*.py`, `playlist/*.sh` | `192.168.178.53:8881` (Dienst), `192.168.178.33` (Sender) | Adressen des Originals | eigene Adressen |
| `meldungen/19…`, `21…`, `24…` | Schlüsseldatei | `../NACHBAU/zugangsdaten/…` | eigene Schlüsseldatei |
| `erlaubte-setzen.py` | Chat-ID | Betreiberchat | eigene Chat-ID |

**Kurz:** die IP-Adressen und Container-IDs des Originals stecken in den Skripten;
die Logik ist davon unabhängig. Wer sie ersetzt, hat ein lauffähiges Werkzeugset.

---

## 3. Hinweise zu einzelnen Dateien

* `agent-wf-bauen-v2-dreistufig.py` ist der **ältere** Erzeuger (Vorläufer) — er wird
  nicht mehr benutzt, gehört aber zur Entwicklungsgeschichte.
* `meldungen/probe-stimme-roh.wav` ist eine rohe Aufnahme; die Lautstärke-Prüfung
  arbeitet damit.
* **Dateien mit Kennungen** (`moderator-import.json`, `agent-fassung-2026-09-19.json`)
  tragen in dieser Fassung Platzhalter; der Arbeitsordner hält sie mit den echten
  Werten (Rechte 600).
* `../ANHANG/ANORDNUNG.md` ist die erzeugte Zeichenflächen-Übersicht; hier im Ordner
  liegt keine Kopie mehr (der Erzeuger schreibt direkt dorthin).

---

## 4. Reihenfolge beim Nachbau

1. `../NACHBAU/README.md` Schritte 1–4 (Dienst, Modelle, n8n, Abläufe bauen).
2. `bash dienst-einspielen.sh` — Module in den Dienst bringen.
3. `bash agent-einspielen-nur.sh /tmp/radio-agent-neu.json` — Abläufe einspielen.
4. `python3 erlaubte-setzen.py <chatId>` und `bash telegram-menue.sh`.
5. Prüfläufe aus `../DOKU/BETRIEB.md`.
