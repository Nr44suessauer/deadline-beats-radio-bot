# Laufende Abläufe (exakter Zustand)

Diese Dateien sind die **Exporte der laufenden** n8n-Abläufe (**Stand 2026-09-24**)
— damit lässt sich der Bot **exakt** wiederherstellen, ohne ihn neu zu bauen:

```bash
# auf dem Zielsystem in n8n einspielen (Beispiel: Bot)
n8n import:workflow --input=RadioAgentBot.json --projectId=<Projektkennung>
n8n update:workflow --id=RadioAgentBot --active=true
# danach n8n neu starten (sonst läuft die alte Fassung im Speicher)
```

Die drei Werkzeuge (`RadioWerkzeug`, `AzuraWerkzeug`, `MeldungenWerkzeug`) genauso.
Dazu kommen die beiden späteren Abläufe `Konfiguration.json` (die Zentrale
„Konfiguration – alle Werte", aus der alle Abläufe ihre Adressen beziehen) und
`StimmenBot.json` („Stimmen aus Filmen" — Formular/Webhook für den Stimmen-Dienst).
`bjFSfXGqpLg7AAXw.json` ist der frühere KI-Moderator — er wird nicht benutzt, gehört
aber zum Bestand.

---

## Achtung: in der Arbeitsfassung stecken Zugangsdaten

In den HTTP-Knoten der **Arbeitsfassung** stehen der **Telegram-Bot-Token** und der
**AzuraCast-Schlüssel** (deshalb sind die Dateien im Arbeitsordner auf `600` gesetzt).
Dort gilt:

* Nicht weitergeben, nicht in ein Repository, nicht in eine Cloud.
* Der Ordner `../zugangsdaten/` gehört dazu (dort stehen dieselben Werte in Klartext).
* **Nie maskierte Fassungen einspielen** (wenn zur Kontrolle Kennungen durch
  `<GEHEIM>` ersetzt wurden) — das killt den Bot, siehe `../../DOKU/BETRIEB.md`,
  Abschnitt 1.

## Neu erzeugen

Statt zu kopieren kann man die Abläufe auch **bauen** — dann tragen sie die eigenen
Zugangswerte:

```bash
cd ../werkzeuge
export TG_TOKEN=…  AZ_KEY=…  MELDUNG_SCHLUESSEL=…
python3 agent-wf-bauen.py                 # -> /tmp/radio-konfiguration.json, /tmp/radio-werkzeuge.json, /tmp/radio-agent.json
python3 anordnung-pruefen.py /tmp/radio-agent.json     # 0 Befunde
python3 import-agent-vorbereiten.py       # -> /tmp/radio-agent-import.json + /tmp/radio-werkzeuge-import.json
bash agent-einspielen-nur.sh /tmp/radio-agent-import.json
```

Unterschied der beiden Wege:

| Weg | Vorteil | Nachteil |
| --- | --- | --- |
| **Kopieren** (diese Dateien) | exakt derselbe Bot, in Minuten betriebsbereit | braucht die alten Zugangswerte; ein Modell-/Stimmenwechsel ändert nichts daran |
| **Bauen** (`werkzeuge/agent-wf-bauen.py`) | eigene Zugangswerte, alles nachvollziehbar | setzt an den Werkzeugknoten das Feld `name` (kosmetisch, ändert Werkzeugnamen gegenüber dem Modell) |
