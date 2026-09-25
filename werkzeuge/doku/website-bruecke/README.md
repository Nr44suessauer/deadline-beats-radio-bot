# Website-Brücke — Radio-Doku erzeugen

Diese beiden Werkzeuge lagen bis zum 24.09.2026 im Website-Projekt unter `tools/`;
sie erzeugen dort den Reiter **Bot Radio** (`/radio`). Sie gehören inhaltlich zum Bot
und liegen deshalb jetzt hier — als **unveränderte Kopie** jenes Stands (das
Website-Projekt hält sie nicht mehr vor).

| Datei | Aufgabe |
| --- | --- |
| `build-radio-docs.mjs` | liest `DocOfficial/` (Veröffentlichungsfassung) und erzeugt `src/data/radio/**` sowie `public/radio/**`: Markdown → HTML, Mermaid-Reparatur, Medien über ffmpeg, n8n-Vorlagen samt ZIP; prüft am Ende gegen die echten Zugangswerte des Arbeitsordners. |
| `stimmproben.mjs` | spricht die vier DEINE-STIMME-Hörproben über den Sprechdienst (`sprechdienst`, LXC 111, Port 10205, Umgebungsvariable `EIGENE_STIMME`), normalisiert auf −16 LUFS und legt die MP3s unter `public/radio/downloads/deine-stimme/` ab. |

**Zum Ausführen müssen beide nach `DeadlineDrivenWebsite/tools/` kopiert werden** —
sie leiten den Projektordner (Ziel der Ausgabe) aus ihrem eigenen Pfad ab
(`import.meta.url`).

```sh
cd <projektordner>/DeadlineDrivenWebsite
cp ../Ai_Radio_Moderator_Bot/werkzeuge/website-bruecke/*.mjs tools/
node tools/build-radio-docs.mjs --pruefen   # nur die Geheimnis-Gegenprobe
node tools/build-radio-docs.mjs             # Inhalt + Medien neu erzeugen
node tools/stimmproben.mjs --pruefen    # Hörproben nur messen
```

Hinweise zu Quelle, Zielen und Veröffentlichung: `README.md` im Website-Projekt,
Abschnitt „Radio-Dokumentation“.
