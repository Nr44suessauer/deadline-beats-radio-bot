# Aufgeräumte Abläufe (aus n8n entfernt am 2026-09-25)

Hier liegen die **Sicherungen** der Arbeitsabläufe, die am 2026-09-25 aus n8n
entfernt wurden. Es sind **nicht mehr aktuelle Fassungen rund um die
Radiosender** — alte Ausgaben des Bots (Sender „Deadline Beats“) und die
Einzel-Werkzeuge, die später im kombinierten Werkzeug `Werkzeug - Radio`
aufgegangen sind.

**Wichtig:** Die Dateien tragen in dieser Fassung Platzhalter; im Arbeitsordner
enthalten sie echte Schlüssel (AzuraCast, Telegram) — dort Rechte 600 und per
`.gitignore` vom Git ausgeschlossen.

Entfernt wurden sie auf Wunsch des Betreibers („räume die Bots, die nicht mehr
aktuell sind, weg — auf die Radiosender bezogen“). Vorher geprüft: **kein**
aktiver Ablauf verweist auf eine dieser Kennungen (Prüfung über die
n8n-Datenbank), und jede Datei hier wurde nach dem Export gegen ihre Kennung
geprüft.

| Datei | Kennung | Name in n8n | Knoten | letzter Lauf |
| --- | --- | --- | --- | --- |
| `RadioTelegramBot-Wunschbot.json` | `RadioTelegramBot` | Radio - Telegram-Wunschbot | 52 | 19.09.2026 |
| `RadioTelegramBot-Archiv-2026-09-19.json` | `RadioTelegramBot-Archiv-2026-09-19` | Radio - Telegram-Wunschbot (Sicherung 19.09.2026) | 52 | — |
| `RadioTelegramBot-copy-v1.json` | `iDfPikpAIqTO9XQ2` | Radio - Telegram-Wunschbot copy v1 | 52 | — |
| `Radio-AI-Moderator.json` | `bjFSfXGqpLg7AAXw` | Radio - AI-Moderator (Archiv der ersten Fassung) | 26 | 19.09.2026 |
| `RadioAgent-vor-dem-Umbau.json` | `da7f06de-…` | Radio - Telegram-Agent (Fassung 19.09.2026, vor dem Umbau) | 34 | — |
| `RadioAgent-Zwischenstand-V2.json` | `7Vv3NSFsS7OZaBSd` | Radio - Telegram-Agent Zischenstand V2.0 | 88 | — |
| `RadioAgent-copy.json` | `jt2IC4TVPTF1KDLp` | Radio - Telegram-Agent copy | 34 | — |
| `RadioAgent-copy2-V2.json` | `zxBICXCfUaMGhNmT` | Radio - Telegram-Agent copy 2 V2 | 65 | — |
| `Werkzeug-Titel-suchen.json` | `RadioWerkzeugSuche` | Werkzeug - Titel suchen | 11 | 19.09.2026 |
| `Werkzeug-Sofort-spielen.json` | `RadioWerkzeugSofort` | Werkzeug - Sofort spielen | 5 | 19.09.2026 |
| `Werkzeug-Danach-spielen.json` | `RadioWerkzeugDanach` | Werkzeug - Danach spielen | 4 | — |
| `Werkzeug-Was-laeuft.json` | `RadioWerkzeugStatus` | Werkzeug - Was laeuft | 4 | 19.09.2026 |
| `Werkzeug-Richtung-suchen.json` | `RadioWerkzeugRichtung` | Werkzeug - Richtung suchen | 9 | 19.09.2026 |

Nach dem Entfernen bleibt der Bestand **senderbezogen** bei diesen sechs Abläufen
(alle aktiv):

| Sender | Abläufe |
| --- | --- |
| „Deadline Beats“ | `RadioAgentBot`, `RadioWerkzeug`, `AzuraWerkzeug`, `MeldungenWerkzeug`, `Konfiguration`, `StimmenBot` |

Nicht angetastet (gehören nicht zum Radio): die NewsBot-Familie und „recherche
done“ (Website-Nachrichten), Bewerbung – Analyse, Mail Extractor, Brave-Chatbot,
My workflow 1–4, Kevin, AI agent chat, SearchApi AI Agent, Check Online Status
Cluster.

## Wie das Aufräumen lief

`aufraeumen-2026-09-25.sh` (liegt hier als Nachweis) hat je Ablauf:

1. den Ablauf aus n8n exportiert und die Kennung in der Datei geprüft,
2. die Zeilen aus der n8n-Datenbank entfernt
   (`workflow_entity`, `shared_workflow`, `workflow_history` — n8n hat keinen
   Löschbefehl für Abläufe, und die REST-Schnittstelle braucht eine Sitzung),
3. n8n neu gestartet (rund eine Minute Pause für alle Bots).

Danach geprüft: 30 Abläufe in n8n, alle elf senderbezogenen aktiv, beide
Sender-Ströme HTTP 200, Demo-Bot antwortet (1,6 s).
