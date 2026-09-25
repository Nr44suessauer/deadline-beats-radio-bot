# Hinweis zu dieser Fassung (DocOfficial)

Diese Fassung ist zum Weitergeben und Veröffentlichen gedacht.
Gebaut am 2026-09-26 aus der Arbeitsfassung
(Ai_Radio_Moderator_Bot).

## Was ersetzt wurde

Alle echten Zugangsdaten sind durch Platzhalter ersetzt - im Einzelnen:

- Telegram-Bot-Token und Chat-Kennungen
- AzuraCast-API-Schlüssel, Web-/DJ-/Streamer-Passwörter
- Postfach-Schlüssel und Schlüssel des Testeingangs
- n8n-Anmeldung, SSH-Schlüssel (privat und öffentlich) samt Kurzbefehlen
- Werte in `NACHBAU/ablaeufe-laufend/` (die Ablauf-Dateien tragen Platzhalter)
- Name und Anschrift des Autors (standen als Projekt-Inhaber in den
  Ablauf-Dateien) — jetzt `DEIN NAME` / `DEINE-E-MAIL`
- die Adresse der n8n-Oberfläche und die Pfade der Webhooks — jetzt
  `DEIN-N8N-HOST` / `DEIN-WEBHOOK-PFAD`
- die Kennungen der eigenen Instanz (Projekt, Fassungen, Zugänge, Knoten,
  Etiketten) und mitgespeicherte Testdaten in den Ablauf-Dateien

Die Platzhalter stehen in Grossbuchstaben, z. B. `DEIN-TELEGRAM-BOT-TOKEN`.
Zum Nachschlagen, was gebraucht wird und wie es entsteht:
`NACHBAU/zugangsdaten.md` und `NACHBAU/zugangsdaten/UEBERSICHT.md`.

## Hinweise

- Netzadressen (192.168.x.x) sind Beispiele aus dem Aufbau des Autors.
  Fuer die eigene Anlage durch die eigenen Adressen ersetzen.
- Die Bilder zeigen nur die Oberflaeche (Ablaeufe, Notizen) - keine echten Werte.
- Neu bauen: im Quellordner `python3 werkzeuge/doc-official-bauen.py`.

## Stimme

Diese Fassung enthält **keine fremde Stimme und keine Stimmdaten** (kein Modell,
keine Trainingsausschnitte, keine Hörproben). Der Dienst spricht zunächst mit einer
freien Standardstimme. Wie du deine **eigene Wunschstimme** einbindest, steht in
`DOKU/STIMME.md` und in der Vorlage `NACHBAU/eigene-stimme/`.

## Was zusätzlich entfernt wurde

Ganz entfernt wurden: die Dateien des Ordners `NACHBAU/zugangsdaten/`, die
Umgebungsdatei `dienst/geheim.env` und alle Audio- und Modelldateien (`.wav`,
`.mp3`, `.onnx`, `.pth`, `.safetensors`). Wie du **deine eigenen Zugangswerte**
anlegst, steht in `NACHBAU/zugangsdaten.md`; die Vorlage für die Umgebungsdatei
liegt als `dienst/geheim.env.vorlage` bei.

## Voice

This edition contains **no third-party voice and no voice data** (no model, no
training clips, no samples). Out of the box the service speaks with a free standard
voice. How to integrate **your own desired voice** is described in `DOKU/STIMME.md`
and in the template `NACHBAU/eigene-stimme/`.

## Also removed

Removed entirely: the files of `NACHBAU/zugangsdaten/`, the environment file
`dienst/geheim.env`, and all audio and model files (`.wav`, `.mp3`, `.onnx`,
`.pth`, `.safetensors`). See `NACHBAU/zugangsdaten.md` for how to create **your
own credentials**; the environment template ships as `dienst/geheim.env.vorlage`.
