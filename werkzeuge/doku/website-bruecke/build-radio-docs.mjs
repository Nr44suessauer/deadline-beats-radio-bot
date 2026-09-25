#!/usr/bin/env node
/**
 * Baut die Radio-Dokumentation (KI-Radio-Moderator-Bot „Deadline Beats“) für
 * die Website — Inhalt und Medien.
 *
 *   Quelle:  <dokuordner>/DocOfficial
 *            Das ist die VERÖFFENTLICHUNGSFASSUNG: alle Zugangsdaten sind dort
 *            durch Platzhalter ersetzt. NIE den Arbeitsordner daneben
 *            (Projektordner) verwenden — dort stehen echte Werte.
 *   Ziel:    src/data/radio/…      Inhalt (erzeugte TS-Module, je Dok + Sprache)
 *            public/radio/…        Medien (Bilder, Animationen als MP4, die
 *                                  interaktive n8n-Oberfläche)
 *
 * Aufruf:
 *   node tools/build-radio-docs.mjs                 # alles neu erzeugen
 *   node tools/build-radio-docs.mjs --ohne-medien   # nur den Inhalt
 *   node tools/build-radio-docs.mjs --quelle PFAD   # andere Doku-Quelle
 *   node tools/build-radio-docs.mjs --pruefen       # nur Geheimnis-Prüfung
 *
 * Das Werkzeug schreibt alle Dateien vollständig neu und prüft zum Schluss
 * gegen die echten Zugangswerte des Arbeitsordners: es darf KEIN echter Wert
 * und KEIN Geheimnis-Muster in der Ausgabe stehen. Die Werte werden dafür nur
 * eingelesen und verglichen — nie ausgegeben.
 */
import { spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { basename, dirname, join, normalize, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { marked } from 'marked'

// ── Pfade und Schalter ─────────────────────────────────────────────────────
const PROJEKT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const STANDARD_QUELLE = '<dokuordner>'
const DATEN_ZIEL = join(PROJEKT, 'src/data/radio')
const MEDIEN_ZIEL = join(PROJEKT, 'public/radio')

const args = process.argv.slice(2)
const argWert = (name, vorgabe) => {
  const i = args.indexOf(name)
  return i >= 0 && args[i + 1] ? args[i + 1] : vorgabe
}
const ARBEIT = resolve(argWert('--quelle', STANDARD_QUELLE))
const DOKU = join(ARBEIT, 'DocOfficial')
const OHNE_MEDIEN = args.includes('--ohne-medien')
const NUR_PRUEFEN = args.includes('--pruefen')

// ── Gliederung der Seite ───────────────────────────────────────────────────
const GRUPPEN = [
  {
    id: 'ueberblick', titel: 'Überblick', titelEn: 'Overview', icon: 'radio',
    text: 'Was der Bot ist, wie man ihn bedient und wie das System aufgebaut ist.',
    textEn: 'What the bot is, how to use it and how the system is put together.',
  },
  {
    id: 'technik', titel: 'Technik', titelEn: 'Technology', icon: 'layers',
    text: 'Architektur, Diagramme und Schnittstellen — wie der Bot gebaut ist und spricht.',
    textEn: 'Architecture, diagrams and interfaces — how the bot is built and how it talks.',
  },
  {
    id: 'betrieb', titel: 'Betrieb', titelEn: 'Operations', icon: 'wrench',
    text: 'Einspielen, prüfen, überwachen, Fehler beheben — und die Baugeschichte.',
    textEn: 'Deploy, verify, monitor, troubleshoot — plus the build history.',
  },
  {
    id: 'stimme', titel: 'Stimme', titelEn: 'Voice', icon: 'wave',
    text: 'Die eigene Moderationsstimme „DEINE-STIMME“ und die Anleitung, jede Stimme nachzubauen.',
    textEn: 'The own host voice “DEINE-STIMME” and the guide to recreating any voice.',
  },
  {
    id: 'nachbau', titel: 'Nachbau', titelEn: 'Rebuild', icon: 'box',
    text: 'Den Bot vollständig auf neuer Hardware nachbauen — Dienst, Abläufe, Zugänge, Sender.',
    textEn: 'Rebuild the whole bot on new hardware — service, workflows, credentials, station.',
  },
  {
    id: 'anhang', titel: 'Download', titelEn: 'Downloads', icon: 'image',
    text: 'Die n8n-Vorlagen aller Bots zum Einspielen, die Stimmdaten — und die erzeugten Übersichten.',
    textEn: 'The n8n templates of every bot ready to import, the voice data — plus the generated overviews.',
  },
]

// `datei` ist der Pfad innerhalb von DocOfficial; die englische Fassung liegt
// unter EN/ — fehlt sie dort, zeigt die Seite die deutsche mit Hinweis.
// Die EN-Fassung benutzt englische Ordner-/Dateinamen:
const EN_DATEI = {
  'DOKU/HANDBUCH.md': 'DOCS/MANUAL.md',
  'DOKU/BETRIEB.md': 'DOCS/OPERATIONS.md',
  'DOKU/BAU.md': 'DOCS/BUILD.md',
  'DOKU/STIMME.md': 'DOCS/VOICE.md',
  'NACHBAU/README.md': 'REBUILD/README.md',
  'NACHBAU/umgebung.md': 'REBUILD/environment.md',
  'NACHBAU/zugangsdaten.md': 'REBUILD/credentials.md',
  'NACHBAU/zugangsdaten/UEBERSICHT.md': 'REBUILD/credentials/OVERVIEW.md',
  'dienst/README.md': 'service/README.md',
  'dienst/whisper/README.md': 'service/whisper/README.md',
  'NACHBAU/sender-einrichten.md': 'REBUILD/station-setup.md',
  'NACHBAU/searxng-einrichten.md': 'REBUILD/searxng-setup.md',
  'NACHBAU/stimmen-und-modelle.md': 'REBUILD/voices-and-models.md',
  'NACHBAU/eigene-stimme/README.md': 'REBUILD/own-voice/README.md',
  'NACHBAU/ablaeufe-laufend/README.md': 'REBUILD/running-workflows/README.md',
  'werkzeuge/README.md': 'tools/README.md',
  'werkzeuge/README-projekt.md': 'tools/README-projekt.md',
  'werkzeuge/meldungen/README.md': 'tools/news/README.md',
  'werkzeuge/playlist/README.md': 'tools/playlist/README.md',
  'werkzeuge/tempo/README.md': 'tools/tempo/README.md',
  'NACHBAU/vorlage.md': 'REBUILD/template.md',
  'ANHANG/README.md': 'APPENDIX/README.md',
  'ANHANG/ANORDNUNG.md': 'APPENDIX/LAYOUT.md',
}

const DOKUMENTE = [
  { slug: 'ueberblick', datei: 'README.md', gruppe: 'ueberblick',
    titel: 'Überblick', titelEn: 'Overview',
    kurz: 'Einstieg, Fähigkeiten in Kurzform, Systemüberblick',
    kurzEn: 'Entry point, capabilities at a glance, system overview' },
  { slug: 'handbuch', datei: 'DOKU/HANDBUCH.md', gruppe: 'technik',
    titel: 'Handbuch', titelEn: 'Handbook',
    kurz: 'Fähigkeiten, Architektur, Diagramme, Schnittstellen',
    kurzEn: 'Capabilities, architecture, diagrams, interfaces' },
  { slug: 'betrieb', datei: 'DOKU/BETRIEB.md', gruppe: 'betrieb',
    titel: 'Betrieb', titelEn: 'Operations',
    kurz: 'Einspielen, überwachen, Störungen, Testen',
    kurzEn: 'Deploy, monitor, troubleshooting, testing' },
  { slug: 'bauen', datei: 'DOKU/BAU.md', gruppe: 'betrieb',
    titel: 'Baugeschichte', titelEn: 'Build history',
    kurz: 'Wie der Bot entstand — Bauweise, Entscheidungen, Fassungen',
    kurzEn: 'How the bot came to be — method, decisions, versions' },
  { slug: 'stimme', datei: 'DOKU/STIMME.md', gruppe: 'stimme',
    titel: 'Stimme', titelEn: 'Voice',
    kurz: 'Die Moderationsstimme „DEINE-STIMME“ und eigene Stimmen klonen',
    kurzEn: 'The “DEINE-STIMME” host voice and cloning your own voices' },
  { slug: 'nachbau', datei: 'NACHBAU/README.md', gruppe: 'nachbau',
    titel: 'Nachbau', titelEn: 'Rebuild',
    kurz: 'Was im Ordner liegt und in welcher Reihenfolge man baut',
    kurzEn: 'What the folder holds and the order of assembly' },
  { slug: 'umgebung', datei: 'NACHBAU/umgebung.md', gruppe: 'nachbau',
    titel: 'Umgebung', titelEn: 'Environment',
    kurz: 'Container, Adressen, Ports, Netz und Proxy',
    kurzEn: 'Containers, addresses, ports, network and proxy' },
  { slug: 'zugangsdaten', datei: 'NACHBAU/zugangsdaten.md', gruppe: 'nachbau',
    titel: 'Zugangsdaten', titelEn: 'Credentials',
    kurz: 'Welche Zugänge gebraucht werden und wie sie entstehen',
    kurzEn: 'Which credentials are needed and how they are created' },
  { slug: 'zugangsdaten-uebersicht', datei: 'NACHBAU/zugangsdaten/UEBERSICHT.md', gruppe: 'nachbau',
    titel: 'Zugangsdaten – Übersicht', titelEn: 'Credentials – overview',
    kurz: 'Tabelle aller Werte, Dateien und Rechte',
    kurzEn: 'Table of all values, files and permissions' },
  { slug: 'dienst', datei: 'dienst/README.md', gruppe: 'nachbau',
    titel: 'Dienst radio-tts', titelEn: 'Service radio-tts',
    kurz: 'Die Module des Dienstes — Sprache, Ansage, Katalog',
    kurzEn: 'The service modules — speech, announcement, catalogue' },
  { slug: 'dienst-whisper', datei: 'dienst/whisper/README.md', gruppe: 'nachbau',
    titel: 'Spracherkennung', titelEn: 'Speech recognition',
    kurz: 'whisper.cpp als Dienst für Sprachnachrichten',
    kurzEn: 'whisper.cpp as a service for voice messages' },
  { slug: 'sender', datei: 'NACHBAU/sender-einrichten.md', gruppe: 'nachbau',
    titel: 'Sender einrichten', titelEn: 'Set up the station',
    kurz: 'AzuraCast für den Bot einrichten (DJ-Hafen, Wünsche)',
    kurzEn: 'Set up AzuraCast for the bot (DJ port, requests)' },
  { slug: 'searxng', datei: 'NACHBAU/searxng-einrichten.md', gruppe: 'nachbau',
    titel: 'Eigene Suchmaschine', titelEn: 'Own search engine',
    kurz: 'SearXNG aufsetzen — ohne Sperren im Netz',
    kurzEn: 'Set up SearXNG — web search without blocks' },
  { slug: 'stimmen-modelle', datei: 'NACHBAU/stimmen-und-modelle.md', gruppe: 'nachbau',
    titel: 'Stimmen & Modelle', titelEn: 'Voices & models',
    kurz: 'Welche Stimmen und Modelle geladen werden',
    kurzEn: 'Which voices and models get downloaded' },
  { slug: 'stimme-nachbau', datei: 'NACHBAU/eigene-stimme/README.md', gruppe: 'nachbau',
    titel: 'Stimme nachbauen', titelEn: 'Rebuild the voice',
    kurz: 'Die „DEINE-STIMME“-Kette Schritt für Schritt nachbauen',
    kurzEn: 'Rebuilding the “DEINE-STIMME” pipeline step by step' },
  { slug: 'ablaeufe', datei: 'NACHBAU/ablaeufe-laufend/README.md', gruppe: 'nachbau',
    titel: 'Abläufe einspielen', titelEn: 'Import workflows',
    kurz: 'Die mitgelieferten Abläufe in n8n einspielen',
    kurzEn: 'Import the supplied workflows into n8n' },
  { slug: 'werkzeuge', datei: 'werkzeuge/README.md', gruppe: 'nachbau',
    titel: 'Werkzeuge', titelEn: 'Tools',
    kurz: 'Bauen, einspielen, prüfen — die Werkzeugsammlung',
    kurzEn: 'Build, deploy, verify — the tool collection' },
  { slug: 'werkzeuge-projekt', datei: 'werkzeuge/README-projekt.md', gruppe: 'nachbau',
    titel: 'Werkzeuge des Projekts', titelEn: 'Project tools',
    kurz: 'Der Werkzeugkasten der Arbeitsfassung',
    kurzEn: 'The toolbox of the working copy' },
  { slug: 'werkzeug-meldungen', datei: 'werkzeuge/meldungen/README.md', gruppe: 'nachbau',
    titel: 'Werkzeug: Meldungen', titelEn: 'Tool: messages',
    kurz: 'Postfach, Recherche und Ansagen als Ablauf',
    kurzEn: 'Inbox, research and announcements as a workflow' },
  { slug: 'werkzeug-playlist', datei: 'werkzeuge/playlist/README.md', gruppe: 'nachbau',
    titel: 'Werkzeug: Wiedergabelisten', titelEn: 'Tool: playlists',
    kurz: 'Wiedergabelisten-Aufgaben und ihre Prüfläufe',
    kurzEn: 'Playlist tasks and their test runs' },
  { slug: 'werkzeug-tempo', datei: 'werkzeuge/tempo/README.md', gruppe: 'nachbau',
    titel: 'Werkzeug: Tempo', titelEn: 'Tool: tempo',
    kurz: 'Die Tempo-Änderung (163 s → 1,7 s) mit Messwerten',
    kurzEn: 'The tempo change (163 s → 1.7 s) with measurements' },
  { slug: 'vorlage', datei: 'NACHBAU/vorlage.md', gruppe: 'nachbau',
    titel: 'Vorlage', titelEn: 'Template',
    kurz: 'Muster für einen neuen Ablauf',
    kurzEn: 'Template for a new workflow' },
  { slug: 'anhang', datei: 'ANHANG/README.md', gruppe: 'anhang',
    titel: 'Anhang', titelEn: 'Appendix',
    kurz: 'Erzeugte Übersichten, Aufnahmen und ihre Herstellung',
    kurzEn: 'Generated overviews, recordings and how they are made' },
  { slug: 'anordnung', datei: 'ANHANG/ANORDNUNG.md', gruppe: 'anhang',
    titel: 'Anordnung', titelEn: 'Layout',
    kurz: 'Was auf der Zeichenfläche des Bots steht',
    kurzEn: 'What is on the bot’s canvas' },
]

// ── Querverweise: Dateiname → Ziel-Dokument ────────────────────────────────
// Es gilt immer der längste Treffer; `README.md` allein ist zu mehrdeutig und
// wird nur über die Regeln unten verlinkt.
const QUERVERWEISE = {
  'HANDBUCH.md': 'handbuch',
  'BETRIEB.md': 'betrieb',
  'BAU.md': 'bauen',
  'STIMME.md': 'stimme',
  'ANHANG/README.md': 'anhang',
  'ANHANG/ANORDNUNG.md': 'anordnung',
  // ANHANG/ANORDNUNG.md und werkzeuge/ANORDNUNG.md sind identisch —
  // beide Verweise zeigen auf dasselbe Dokument.
  'ANORDNUNG.md': 'anordnung',
  'werkzeuge/ANORDNUNG.md': 'anordnung',
  'NACHBAU/README.md': 'nachbau',
  'NACHBAU/umgebung.md': 'umgebung',
  'umgebung.md': 'umgebung',
  'NACHBAU/vorlage.md': 'vorlage',
  'vorlage.md': 'vorlage',
  'NACHBAU/zugangsdaten.md': 'zugangsdaten',
  'zugangsdaten.md': 'zugangsdaten',
  'NACHBAU/zugangsdaten/UEBERSICHT.md': 'zugangsdaten-uebersicht',
  'zugangsdaten/UEBERSICHT.md': 'zugangsdaten-uebersicht',
  'UEBERSICHT.md': 'zugangsdaten-uebersicht',
  'dienst/README.md': 'dienst',
  'dienst/README.md': 'dienst',
  'dienst/whisper/README.md': 'dienst-whisper',
  'dienst/whisper/README.md': 'dienst-whisper',
  'whisper/README.md': 'dienst-whisper',
  'NACHBAU/sender-einrichten.md': 'sender',
  'sender-einrichten.md': 'sender',
  'NACHBAU/searxng-einrichten.md': 'searxng',
  'searxng-einrichten.md': 'searxng',
  'NACHBAU/stimmen-und-modelle.md': 'stimmen-modelle',
  'stimmen-und-modelle.md': 'stimmen-modelle',
  'NACHBAU/eigene-stimme/README.md': 'stimme-nachbau',
  'eigene-stimme/README.md': 'stimme-nachbau',
  'NACHBAU/ablaeufe-laufend/README.md': 'ablaeufe',
  'ablaeufe-laufend/README.md': 'ablaeufe',
  'werkzeuge/README.md': 'werkzeuge',
  'werkzeuge/README.md': 'werkzeuge',
  'werkzeuge/README-projekt.md': 'werkzeuge-projekt',
  'werkzeuge/README-projekt.md': 'werkzeuge-projekt',
  'werkzeuge/meldungen/README.md': 'werkzeug-meldungen',
  'werkzeuge/meldungen/README.md': 'werkzeug-meldungen',
  'meldungen/README.md': 'werkzeug-meldungen',
  'werkzeuge/playlist/README.md': 'werkzeug-playlist',
  'werkzeuge/playlist/README.md': 'werkzeug-playlist',
  'playlist/README.md': 'werkzeug-playlist',
  'werkzeuge/tempo/README.md': 'werkzeug-tempo',
  'werkzeuge/tempo/README.md': 'werkzeug-tempo',
  'tempo/README.md': 'werkzeug-tempo',
  // Dasselbe für die englischen Dateinamen der EN-Fassung:
  'MANUAL.md': 'handbuch', 'OPERATIONS.md': 'betrieb',
  'BUILD.md': 'bauen', 'VOICE.md': 'stimme', 'LAYOUT.md': 'anordnung',
  'APPENDIX/README.md': 'anhang', 'APPENDIX/LAYOUT.md': 'anordnung',
  'REBUILD/README.md': 'nachbau', 'REBUILD/environment.md': 'umgebung',
  'REBUILD/credentials.md': 'zugangsdaten',
  'REBUILD/credentials/OVERVIEW.md': 'zugangsdaten-uebersicht',
  'REBUILD/station-setup.md': 'sender', 'REBUILD/searxng-setup.md': 'searxng',
  'REBUILD/voices-and-models.md': 'stimmen-modelle',
  'REBUILD/own-voice/README.md': 'stimme-nachbau',
  'REBUILD/running-workflows/README.md': 'ablaeufe',
  'REBUILD/template.md': 'vorlage',
  'tools/README.md': 'werkzeuge', 'tools/news/README.md': 'werkzeug-meldungen',
  'tools/playlist/README.md': 'werkzeug-playlist', 'tools/tempo/README.md': 'werkzeug-tempo',
  'service/README.md': 'dienst', 'service/whisper/README.md': 'dienst-whisper',
}

/** Nackte `README.md`-Verweise: nur bei eindeutigem Zusammenhang verlinken.
 *  Greift nur, wenn die Auflösung über den Ordner (unten) nichts ergibt. */
const README_REGELN = [
  { slug: 'handbuch', vor: /Zahlen und Namen stammen aus/, ziel: 'ueberblick' },
  { slug: 'bauen', vor: /Beschreibung des Ergebnisses/, ziel: 'ueberblick' },
  { slug: 'bauen', vor: /Was ist der Bot, wie bedient man ihn\?/, ziel: 'ueberblick' },
  { slug: 'anhang', vor: /sie liegen \(siehe/, ziel: 'ueberblick' },
  { slug: 'nachbau', vor: /alle Skripte \+ Anleitung \(/, ziel: 'stimme-nachbau' },
  { slug: 'sender', vor: /sprechen \(siehe/, ziel: 'nachbau' },
]

// ── Medien des Anhangs ─────────────────────────────────────────────────────
const ABLAUFBILDER = [
  ['ablauf-bot-uebersicht.png', 'Der ganze Ablauf als Karte', 'Neun Rahmen mit Übersichtsnotiz'],
  ['ablauf-bot-eingang.png', 'Eingang, Sprachnachricht und Analyse', 'Vom Telegram-Eingang über die Erkennung bis zur Planung'],
  ['ablauf-bot-ausfuehrung.png', 'Ausführung, Werkzeuge, Prüfung', 'Stufe 2 und Stufe 3 im Detail'],
]

const GESAMTBILDER = [
  ['gesamt-radio-telegram-agent.png', 'Radio – Telegram-Agent', 'Der Agent mit 81 Knoten: Eingang, Stufen 0–3, Werkzeuge, Antwort'],
  ['gesamt-werkzeug-radio.png', 'Werkzeug – Radio', 'Suchen, Richtung, Sofortspielen und Einreihen'],
  ['gesamt-werkzeug-azuracast.png', 'Werkzeug – AzuraCast', 'Adressen nachschlagen, aufrufen, Überblick holen'],
  ['gesamt-werkzeug-meldungen.png', 'Werkzeug – Meldungen', 'Postfach, Recherche, Wetter und Ansagen'],
  ['gesamt-radio-ai-moderator.png', 'Radio – AI-Moderator', 'Der Moderator-Ablauf mit Ansagen und Freigabe'],
  ['gesamt-konfiguration-alle-werte.png', 'Konfiguration – alle Werte', 'Eine Quelle für Adressen und Einstellungen'],
  ['gesamt-DEIN-WEBHOOK-PFAD.png', 'Stimmen aus Filmen', 'Formular und Webhook für den Stimmen-Dienst'],
]

const VIDEOS = [
  ['bot-lauf-gesamt.gif', 'bot-lauf-gesamt', 'Der ganze Ablauf in Bewegung', 'Echter Testlauf, eng beschnitten auf die Knotenrechtecke — 5,4 s'],
  ['bot-lauf-kamera.gif', 'bot-lauf-kamera', 'Nahaufnahme mit Kamerafahrt', 'Der Blick folgt dem Lauf durch den Agenten — 6,7 s'],
]

// ── Downloads: n8n-Vorlagen (die „Bots" zum Einspielen) ────────────────────
// Quelle ist `NACHBAU/ablaeufe-laufend/` in der Veröffentlichungsfassung —
// dort stehen Platzhalter statt der echten Zugangswerte.
const VORLAGEN = [
  ['RadioAgentBot.json', 'Radio – Telegram-Agent', 'Radio – Telegram agent',
    'Der Bot selbst: Telegram-Eingang, Stufen 0–3, acht Werkzeuge, Antwort (81 Knoten)',
    'The bot itself: Telegram input, stages 0–3, eight tools, reply (81 nodes)'],
  ['RadioWerkzeug.json', 'Werkzeug – Radio', 'Tool – Radio',
    'Suchen (unscharf und nach Richtung), sofort spielen, einreihen',
    'Search (fuzzy and by mood), play now, queue'],
  ['AzuraWerkzeug.json', 'Werkzeug – AzuraCast', 'Tool – AzuraCast',
    'Adressen nachschlagen, aufrufen, Überblick holen — 263 Endpunkte der Sender-API',
    'Look up addresses, call them, get an overview — 263 station API endpoints'],
  ['MeldungenWerkzeug.json', 'Werkzeug – Meldungen', 'Tool – messages',
    'Postfach, Recherche (Presse, Netz, Feeds), Wetter und Ansagen',
    'Inbox, research (press, web, feeds), weather and announcements'],
  ['Konfiguration.json', 'Konfiguration – alle Werte', 'Configuration – all values',
    'Die Zentrale: alle Abläufe holen hier ihre Adressen und Einstellungen',
    'The hub: every workflow takes its addresses and settings from here'],
  ['StimmenBot.json', 'Stimmen aus Filmen', 'Voices from films',
    'Formular und Webhook für den Stimmen-Dienst (eigene Stimme anlernen)',
    'Form and webhook for the voice service (train your own voice)'],
  ['bjFSfXGqpLg7AAXw.json', 'Radio – AI-Moderator (frühere Fassung)', 'Radio – AI moderator (earlier version)',
    'Wird nicht mehr benutzt, gehört aber zum Bestand',
    'No longer used, but part of the record'],
]

// ── Downloads: Stimmdaten ──────────────────────────────────────────────────
// Die Piper-Stimmen sind frei verfügbar und liegen bei HuggingFace — hier steht
// nur die Liste mit Größen und Adressen, geholt werden sie mit dem Skript.
const STIMMEN = [
  ['de_thorsten (Ersatzstimme)', 'de_DE-thorsten-medium.onnx', '63 MB', 'de/de_DE/thorsten/medium'],
  ['de_kerstin', 'de_DE-kerstin-low.onnx', '63 MB', 'de/de_DE/kerstin/low'],
  ['de_ramona', 'de_DE-ramona-low.onnx', '63 MB', 'de/de_DE/ramona/low'],
  ['de_eva', 'de_DE-eva_k-x_low.onnx', '21 MB', 'de/de_DE/eva_k/x_low'],
]

const PIPER_BASIS = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/'

// ── Kleine Helfer ──────────────────────────────────────────────────────────
const lesen = (pfad) => readFileSync(pfad, 'utf8')
const da = (pfad) => existsSync(pfad)
const tsText = (wert) => JSON.stringify(wert)

function schreibe(pfad, inhalt) {
  mkdirSync(dirname(pfad), { recursive: true })
  writeFileSync(pfad, inhalt, 'utf8')
}

/** Titel → Kennung für Sprungmarken (Umlaute aufgelöst, Rest zu '-'). */
function kennung(text) {
  return text
    .toLowerCase()
    .replaceAll('ä', 'ae').replaceAll('ö', 'oe').replaceAll('ü', 'ue').replaceAll('ß', 'ss')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')   // Link → Linktext
    .replace(/[`*_]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'abschnitt'
}

function escapeHtml(text) {
  return String(text)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
}

/**
 * Mermaid verträgt Klammern nur in Anführungszeichen — sowohl in
 * Kantenbeschriftungen (`-->|Stimme (deine-stimme)|`) als auch in Knotenbeschriftungen
 * (`S[whisper.cpp (Vulkan)]`). Beides bricht sonst mit „Parse error … got 'PS'“
 * ab und das Bild bleibt leer. Hier werden die fehlenden Anführungszeichen
 * ergänzt — genau so, wie es die übrigen Stellen der Doku bereits tun.
 */
function mermaidSaeubern(text) {
  return text
    .split('\n')
    .map((zeile) => {
      // 1) Kantenbeschriftungen: -->|Text|
      let z = zeile.replace(/\|([^|\n]+)\|/g, (treffer, label) => {
        const sauber = label.trim()
        if (/["'`]/.test(sauber)) return treffer      // schon in Anführungszeichen
        if (!/[()[\]]/.test(sauber)) return treffer   // harmlos
        return `|"${sauber}"|`
      })
      // 2) Knotenbeschriftungen: ID[Text]
      z = z.replace(/([A-Za-z0-9_]+)\[([^[\]\n]*)\]/g, (treffer, kennung, label) => {
        const sauber = label.trim()
        if (/["'`]/.test(sauber)) return treffer
        if (!/[()]/.test(sauber)) return treffer
        return `${kennung}["${sauber}"]`
      })
      return z
    })
    .join('\n')
}

// ── Veröffentlichungs-Reinigung (Stand, Datum, Bestandsgrößen) ─────────────
/**
 * Die Website zeigt die Doku OHNE Zeit- und Bestandsangaben: keine
 * Stand-/Datumsangaben, keine Fassungsnummern und keine Archivgrößen
 * (Titelzahlen, Platten). Die QUELLE (DocOfficial) bleibt unverändert —
 * gereinigt wird nur, was diese Seite ausgibt.
 *
 * Codezäune, `Inline-Code` und Verweisziele (`](…)`) sind geschützt: dort
 * stehen Befehle, Pfade und Namen, in denen „2026-09-23“ Teil eines
 * Bezeichners oder Dateinamens ist.
 */
const DE_MONATE = 'Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember'
const EN_MONATE = 'January|February|March|April|May|June|July|August|September|October|November|December'

function saeubereVeroeffentlichung(markdown, lang) {
  const ent = lang === 'en'
  return mitSchutz(markdown, (text) => text
    // „> **Stand:** 2026-09-24 · **Fassung 19** · …“ — die ganze Zeile
    .replace(/^[ \t]*>?[ \t]*\*\*(?:Stand|Status|Date):\*\*[^\n]*\n?/gim, '')
    // „**Webseite:** <https://www.deadlinedriven.dev/>“ — auf der Website selbst sinnlos;
    // dort steht stattdessen das Projekt-Repository (Gegenstück zur README im Repository).
    .replace(/\*\*(?:Webseite|Website):\*\*\s*<https:\/\/www\.deadlinedriven\.dev\/?>/i,
      ent
        ? '**Project repository:** <https://github.com/Nr44suessauer/deadline-beats-radio-bot>'
        : '**Projekt-Repository:** <https://github.com/Nr44suessauer/deadline-beats-radio-bot>')
    // Datumsangaben mit Monatsnamen — „(19./20. September 2026)“, „19.–23. September 2026“
    .replace(new RegExp(`\\s*\\([^()\\n]*(?:${DE_MONATE}|${EN_MONATE})\\s+20\\d{2}[^()\\n]*\\)`, 'gi'), '')
    .replace(new RegExp(`\\b(?:am|vom|from|on)?[ \\t]*\\d{1,2}\\.\\/?\\d{0,2}\\.?\\s*[–—-]?\\s*(?:\\d{1,2}\\.?[ \\t]+)?(?:${DE_MONATE}|${EN_MONATE})[ \\t]+20\\d{2}\\b`, 'gi'), '')
    // „(Stand 2026-09-22)“ / „(**Stand 2026-09-24**)“
    .replace(/\(\s*\*{0,2}(?:Stand|as of)[^*()\n]*20\d{2}[^*()\n]*\*{0,2}\s*\)/gi, '')
    // „**Stand: 24.09.2026**, frisch …“ → „Frisch …“
    .replace(/\*\*(?:Stand|Status):\s*\d{1,2}\.\d{2}\.20\d{2}\*\*[,;]?[ \t]*([a-zäöü])/gi, (_, a) => a.toUpperCase())
    // deutsche Datumsformen — „vom 24.09.“, „21./22.09.2026“, „24.09.2026“
    .replace(/\b(?:vom|am|from|on)\s+\d{1,2}\.\d{0,2}\.?\d{0,4}(?:\.20\d{2})?\b/gi, '')
    .replace(/\b\d{1,2}\.\/\d{1,2}\.\d{2}\.20\d{2}\b/g, '')
    .replace(/\b(?:Stand:?)?[ \t]*\d{1,2}\.\d{2}\.20\d{2}\b/gi, '')
    // englische Tages-Monats-Form — „Stand: 24 Sep 2026“, „24 Sep 2026“
    .replace(/\b(?:Stand|Status|Date):?[ \t]*\d{1,2}[ \t]+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[ \t]+20\d{2}\b/gi, '')
    .replace(/\b\d{1,2}[ \t]+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[ \t]+20\d{2}\b/g, '')
    // „Seit 2026-09-23 sprechen …“ → „Sprechen …“ (am Satzanfang groß)
    .replace(/(\*\*\s*|[:>]\s*|\n|^)\s*Seit\s+20\d{2}-\d{2}-\d{2}\s+([a-zäöü])/gm, (_, vor, b) => vor + b.toUpperCase())
    // „Stand:“/„Stand“ mit Datum — nur die Angabe, der Satz bleibt
    .replace(/(?:\*\*)?(?:Stand|Status):?\*{0,2}\s*20\d{2}-\d{2}-\d{2}[ \t]*[·]?[ \t]*/gi, '')
    // „As of 2026-09-22, the bot …“ → Satz bleibt, Anfangsbuchstabe groß
    .replace(/\bAs of\s+20\d{2}-\d{2}-\d{2},\s*(.)/gi, (_, erster) => erster.toUpperCase())
    .replace(/(?:\*\*)?(?:As of|Status|Date):?\*{0,2}\s*20\d{2}-\d{2}-\d{2}[ \t]*[·]?[ \t]*/gi, '')
    // übrige ISO-Daten (auch „, 2026-09-20“ und „seit 2026-09-23“)
    .replace(/\b(?:gemessen|measured|geprüft|checked|aufgenommen|captured|seit|since|am|vom|on|from)\s+(?:dem\s+|der\s+|the\s+)?20\d{2}-\d{2}-\d{2}\b/gi, '')
    .replace(/[,;·]?[ \t]*20\d{2}-\d{2}-\d{2}\b/g, '')
    // Fassungsnummern
    .replace(/\bFassungen\s+v?\d+(?:\s*[–-]\s*v?\d+)?\b/g, 'Fassungen')
    .replace(/\bversions\s+v?\d+(?:\s*[–-]\s*v?\d+)?\b/gi, 'versions')
    .replace(/\s*\((?:Fassung|Version|Revision)\s*\d+\)/gi, '')
    .replace(/\s*\(v\d+\s*[–-]\s*v?\d+\)/gi, '')
    .replace(/\bFassung\s+\d{1,2}\.\d{2}\.20\d{2}\s*,\s*/g, '')
    .replace(/\(\s*Gilt für Fassung \d+;\s*/g, '(')
    .replace(/\(\s*applies to version \d+;\s*/gi, '(')
    .replace(/\b(?:seit|since|with)\s+(?:Fassung|Version|Revision)\s+\d+[ \t]*/gi, '')
    // Archiv- und Bestandsgrößen (kombinierte Formen ZUERST)
    .replace(/,[ \t]*56[.,]?[ \t]?635[ \t]+(?:Titel|titles|Tracks|tracks)\b/g, '')
    .replace(/\b56[.,]?[ \t]?635\s+Titel\s*\(15[ -]?TB[ -]?Platte\)?,\s*davon\s+48[.,]?[ \t]?729\s+im\s+Wunsch-\/Suchbestand/g, 'eigenes Musikarchiv, davon ein Teil im Wunsch-/Suchbestand')
    .replace(/\b56[.,]?[ \t]?635\s+titles\s*\(15[ -]?TB\s*drive\)?,\s*of which\s+48[.,]?[ \t]?729\s+in/g, 'the music archive, part of it in')
    .replace(/\s*\(\s*48[.,]?[ \t]?729\s+von\s+56[.,]?[ \t]?635\s+Titeln\s+sind\s+durchsuchbar\s*\)/g, ' (durchsuchbar ist nur ein Teil der Titel)')
    .replace(/\s*\(\s*48[.,]?[ \t]?729\s+of\s+56[.,]?[ \t]?635\s+tracks\s+are\s+searchable\s*\)/g, ' (only part of the tracks is searchable)')
    .replace(/48[.,]?[ \t]?729\s+von\s+56[.,]?[ \t]?635\s+Titeln/g, 'ein Teil der Titel')
    .replace(/48[.,]?[ \t]?729\s+of\s+56[.,]?[ \t]?635\s+(?:tracks|titles)/g, 'part of the tracks')
    .replace(/\b56[.,]?[ \t]?635\s+(?:Titel|titles|Tracks|tracks)\b/g, '')
    .replace(/\s*\(\s*48[.,]?[ \t]?729\s+(?:Titel|titles|Tracks|tracks)[^)]*\)/g, '')
    .replace(/,[ \t]*56[.,]?[ \t]?635\s+titles\s*\(15-TB drive\),[ \t]*of which\s+48[.,]?[ \t]?729\s+in/g, 'part of the collection is in')
    .replace(/\s*\(\s*7[.,]?[ \t]?906\s+(?:Titel|titles|Tracks|tracks)\s*\)/g, '')
    .replace(/\|[ \t]*~?[ \t]*15[ \t]?TB[ \t]*\|/g, ent ? '| own folder |' : '| eigener Ordner |')
    .replace(/[,;]?[ \t]*~?[ \t]*15[ -]?TB(?:-Platte|\s*Platte)?\b/g, '')
    .replace(/\s*\([ \t]*15[ \t]?TB[ \t]*\)/g, '')
    // Letzter Schliff: Zeichenreste am Zeilenanfang, leere Klammern, Leerraum
    .replace(/(^|\n)[ \t]*[·.,;:]\s*/g, '$1')
    .replace(/\(\s*\)/g, '')
    .replace(/\(\s*[:;·]\s*/g, '(')
    .replace(/[ \t]+:/g, ':')
    .replace(/\s*[–—-]\s*:\s*/g, ': ')
    .replace(/\.\s*;\s*/g, '. ')
    .replace(/[,;]\s*\)/g, ')')
    .replace(/[,;]\s*([.;,)])/g, '$1')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/[ \t]+([,.;:!?)])/g, '$1')
    .replace(/[ \t]+$/gm, ''))
}

/** Codezäune, `Inline-Code` und Verweisziele für die Regeln unkenntlich machen. */
function mitSchutz(text, fn) {
  const stuecke = []
  const geschuetzt = text.replace(/```([^\n`]*)\n[\s\S]*?```|`[^`\n]*`|\]\([^)\n]*\)/g, (treffer, sprache) => {
    // Mermaid-Bilder sind sichtbarer Inhalt — ihre Beschriftungen werden mitgereinigt.
    if ((sprache ?? '').trim() === 'mermaid') return treffer
    stuecke.push(treffer)
    return `\u0000${stuecke.length - 1}\u0000`
  })
  return fn(geschuetzt).replace(/\u0000(\d+)\u0000/g, (_, nummer) => stuecke[Number(nummer)] ?? '')
}

// ── Markdown → HTML ────────────────────────────────────────────────────────

/** Basisordner je Dokument (für relative Verweise wie `../umgebung.md`). */
const DOK_BASIS = new Map(
  DOKUMENTE.map((d) => [d.slug, dirname(d.datei).replace(/^\.$/, '')]),
)

function wandleUm(markdown, dok, lang) {
  markdown = saeubereVeroeffentlichung(markdown, lang)
  const slug = dok.slug
  const vergeben = new Map()
  const toc = []
  let titel = ''

  const anker = (text) => {
    const basis = kennung(text)
    const nr = (vergeben.get(basis) ?? 0) + 1
    vergeben.set(basis, nr)
    return nr === 1 ? basis : `${basis}-${nr}`
  }

  const renderer = {
    heading(token) {
      if (token.depth === 1) {
        titel = (token.text ?? '').replace(/[`*_]/g, '').trim()
        return ''
      }
      const text = this.parser.parseInline(token.tokens)
      const roh = (token.text ?? '').trim()
      const id = anker(roh)
      if (token.depth === 2 || token.depth === 3) toc.push({ id, text: roh, depth: token.depth })
      return `<h${token.depth} id="${id}" class="rd-h${token.depth}">${text}` +
        `<a class="rd-anchor" href="#${id}" aria-label="Abschnitt verlinken">#</a></h${token.depth}>\n`
    },

    code(token) {
      const sprache = ((token.lang ?? '').trim().toLowerCase().split(/\s+/)[0]) ?? ''
      if (sprache === 'mermaid') {
        // Mermaid liest den Text selbst aus dem Element (textContent) — die
        // Umschreibungen der Entitäten (&lt;br/&gt;) sind dort wieder roh.
        return `<div class="rd-mermaid"><div class="mermaid">${escapeHtml(mermaidSaeubern(token.text))}</div></div>\n`
      }
      const klasse = sprache ? ` class="language-${sprache}"` : ''
      const label = sprache && sprache !== 'text'
        ? `<span class="rd-code-lang">${escapeHtml(sprache.toUpperCase())}</span>`
        : ''
      return `<div class="rd-code">${label}<pre><code${klasse}>${escapeHtml(token.text)}</code></pre></div>\n`
    },

    blockquote(token) {
      const inhalt = this.parser.parse(token.tokens)
      let klasse = 'rd-note'
      const kopf = inhalt.trimStart().replace(/^<p>/, '').replace(/^<strong>/, '')
      if (/^(Achtung|Warnung|Vorsicht|Gefahr|Attention|Warning)/i.test(kopf)) klasse += ' rd-note--warn'
      else if (/^(Stand|Date|Fassung|Version|Status)[:.\s]/i.test(kopf)) klasse += ' rd-note--meta'
      else if (/^(Tipp|Hinweis|Merke|Praxis|Note|Beispiel|Tip|Lesson|Lehre)/i.test(kopf)) klasse += ' rd-note--info'
      return `<blockquote class="${klasse}">${inhalt}</blockquote>\n`
    },

    link({ href, title, tokens }) {
      const text = this.parser.parseInline(tokens)
      const ziel = (href ?? '').trim()
      const t = title ? ` title="${escapeHtml(title)}"` : ''
      const zielSlug = verweisZiel(ziel, slug)
      if (zielSlug) return `<a class="rd-xref" href="/radio?doc=${zielSlug}" data-doc="${zielSlug}"${t}>${text}</a>`
      if (/^https?:/i.test(ziel)) return `<a href="${escapeHtml(ziel)}" target="_blank" rel="noopener"${t}>${text}</a>`
      return `<a href="${escapeHtml(ziel)}"${t}>${text}</a>`
    },

    image({ href, title, text }) {
      const quelle = `/radio/medien/${basename(href ?? '')}`
      const bild = `<img src="${escapeHtml(quelle)}" alt="${escapeHtml(text ?? '')}" loading="lazy" decoding="async">`
      const unterschrift = title ? `<figcaption>${escapeHtml(title)}</figcaption>` : ''
      return `<figure class="rd-img">${bild}${unterschrift}</figure>\n`
    },
  }

  marked.use({ gfm: true, renderer })
  let html = marked.parse(markdown)

  // Tabellen auf schmalen Geräten waagerecht scrollbar machen
  html = html.replaceAll('<table>', '<div class="rd-table-wrap"><table>')
  html = html.replaceAll('</table>', '</table></div>')

  html = verlinkeInlineVerweise(html, dok)

  const trenner = html.search(/<h2[\s>]/)
  const leadHtml = (trenner >= 0 ? html.slice(0, trenner) : '').trim()
  const rumpf = (trenner >= 0 ? html.slice(trenner) : html).trim()

  return { titel, leadHtml, html: rumpf, toc }
}

/**
 * Ziel-Dokument eines Verweises bestimmen.
 *
 * Aufgelöst wird wie im Dateisystem: `../README.md` in
 * `dienst/README.md` zeigt auf `NACHBAU/README.md`. Findet sich
 * dort nichts, wird der Verweis unverändert und zuletzt nur sein Dateiname
 * versucht (so trifft `../BETRIEB.md` aus einem Unterordner die Hauptdoku).
 */
function verweisZiel(href, slug) {
  const roh = (href ?? '').trim()
  if (!roh || roh.startsWith('#') || /^[a-z][a-z0-9+.-]*:/i.test(roh)) return null

  const [pfad, anker = ""] = roh.split('#')
  const ohneQuery = (pfad ?? '').split('?')[0] ?? ''
  if (!ohneQuery) return null

  const basis = DOK_BASIS.get(slug) ?? ''
  const kandidaten = []
  if (ohneQuery.startsWith('/')) kandidaten.push(ohneQuery.slice(1))
  else kandidaten.push(normalize(join(basis, ohneQuery)))
  kandidaten.push(normalize(ohneQuery))
  const name = basename(ohneQuery)
  if (name) kandidaten.push(name)

  for (const kandidat of kandidaten) {
    const ziel = QUERVERWEISE[kandidat]
    if (ziel && ziel !== slug) return anker ? `${ziel}#${anker}` : ziel
  }
  return null
}

function docHinweis(ziel, text) {
  const [slug, anker = ''] = ziel.split('#')
  const marke = anker ? `#${anker}` : ''
  return `<a class="rd-xref" href="/radio?doc=${slug}${marke}" data-doc="${slug}"><code>${escapeHtml(text)}</code></a>`
}

/** Inline-Code, der einen bekannten Doku-Namen nennt, anklickbar machen. */
function verlinkeInlineVerweise(html, dok) {
  const regeln = README_REGELN.filter((r) => r.slug === dok.slug)
  return teileAusserhalbCode(html, (teil) =>
    teil.replace(/<code>([^<]+)<\/code>/g, (treffer, text, versatz, ganz) => {
      const name = text.trim()
      const ziel = verweisZiel(name, dok.slug)
      if (ziel) return docHinweis(ziel, name)
      // `README.md` allein ist mehrdeutig — nur bei klarem Zusammenhang
      if (name === 'README.md' && regeln.length) {
        const davor = ganz.slice(Math.max(0, versatz - 200), versatz).replace(/\s+/g, ' ')
        const regel = regeln.find((r) => r.vor.test(davor))
        if (regel) return docHinweis(regel.ziel, name)
      }
      return treffer
    }))
}

/** Wendet `fn` auf alles außerhalb von `<pre>`-Blöcken an. */
function teileAusserhalbCode(html, fn) {
  return html
    .split(/(<pre[\s\S]*?<\/pre>)/)
    .map((teil, i) => (i % 2 ? teil : fn(teil)))
    .join('')
}

// ── Inhalt erzeugen ────────────────────────────────────────────────────────
function erzeugeInhalt() {
  if (!da(join(DOKU, 'HINWEIS.md'))) {
    console.error(`✗ ${DOKU} ist nicht die Veröffentlichungsfassung (HINWEIS.md fehlt).`)
    console.error('  Ohne Platzhalter-Fassung NICHT weiterarbeiten — dort stehen echte Zugangsdaten.')
    process.exit(1)
  }

  const docsOrdner = join(DATEN_ZIEL, 'docs')
  rmSync(docsOrdner, { recursive: true, force: true })
  mkdirSync(docsOrdner, { recursive: true })

  const lader = new Map()   // slug → { de: Zeile, en: Zeile }
  const fehltEn = []
  let bytes = 0
  const befunde = []

  for (const dok of DOKUMENTE) {
    const dePfad = join(DOKU, dok.datei)
    if (!da(dePfad)) {
      befunde.push(`Quelltext fehlt: ${dok.datei}`)
      continue
    }
    lader.set(dok.slug, { de: '', en: '' })
    for (const lang of ['de', 'en']) {
      const enPfad = join(DOKU, 'EN', EN_DATEI[dok.datei] ?? dok.datei)
      const eigenerText = lang === 'en' && da(enPfad)
      const quelle = eigenerText ? enPfad : dePfad
      const umgewandelt = wandleUm(lesen(quelle), dok, lang)
      const datei = `${dok.slug}-${lang}.ts`
      const modul = [
        '// Erzeugt von tools/build-radio-docs.mjs — nicht von Hand bearbeiten.',
        "import type { RadioDoc } from '../types'",
        '',
        'const doc: RadioDoc = {',
        `  titel: ${tsText(umgewandelt.titel || dok.titel)},`,
        `  leadHtml: ${tsText(umgewandelt.leadHtml)},`,
        `  html: ${tsText(umgewandelt.html)},`,
        `  toc: ${JSON.stringify(umgewandelt.toc)},`,
        `  abschnitte: ${umgewandelt.toc.filter((t) => t.depth === 2).length},`,
        `  uebersetzt: ${eigenerText},`,
        '}',
        '',
        'export default doc',
        '',
      ].join('\n')
      const zielPfad = join(docsOrdner, datei)
      schreibe(zielPfad, modul)
      bytes += statSync(zielPfad).size
      const eintrag = lader.get(dok.slug)
      if (eintrag) eintrag[lang] = `    ${lang}: () => import('./docs/${dok.slug}-${lang}'),`
      if (lang === 'en' && !eigenerText) fehltEn.push(dok.slug)
    }
  }

  const gruppenText = GRUPPEN.map((g) => `  {
    id: ${tsText(g.id)},
    titel: ${tsText(g.titel)},
    titelEn: ${tsText(g.titelEn)},
    icon: ${tsText(g.icon)},
    text: ${tsText(g.text)},
    textEn: ${tsText(g.textEn)},
  },`).join('\n')

  const dokText = DOKUMENTE.map((d) => `  {
    slug: ${tsText(d.slug)},
    gruppe: ${tsText(d.gruppe)},
    titel: ${tsText(d.titel)},
    titelEn: ${tsText(d.titelEn)},
    kurz: ${tsText(d.kurz)},
    kurzEn: ${tsText(d.kurzEn)},
    datei: ${tsText(d.datei)},
  },`).join('\n')

  const laderText = [...lader.entries()].map(([slug, e]) => `  ${tsText(slug)}: {
${e.de}
${e.en}
  },`).join('\n')

  const fehltEnText = fehltEn.map((s) => `  ${tsText(s)}: true,`).join('\n')

  const index = `// Erzeugt von tools/build-radio-docs.mjs — nicht von Hand bearbeiten.
// Inhaltliche Quelle: Ai_Radio_Moderator_Bot/DocOfficial (Veröffentlichungs-
// fassung mit Platzhaltern). Neu erzeugen: node tools/build-radio-docs.mjs
import type { RadioDoc } from './types'

export interface RadioGruppe {
  id: string
  titel: string
  titelEn: string
  icon: string
  text: string
  textEn: string
}

export interface RadioDokument {
  slug: string
  gruppe: string
  titel: string
  titelEn: string
  kurz: string
  kurzEn: string
  /** Quelldatei in der Doku-Sammlung, z. B. NACHBAU/umgebung.md. */
  datei: string
}

export const RADIO_GRUPPEN: RadioGruppe[] = [
${gruppenText}
]

export const RADIO_DOKUMENTE: RadioDokument[] = [
${dokText}
]

/** Dokumente ohne englische Fassung — die Seite zeigt dann die deutsche. */
export const RADIO_EN_FEHLT: Record<string, boolean> = {
${fehltEnText}
}

type Lader = () => Promise<{ default: RadioDoc }>

const LADER: Record<string, { de: Lader; en: Lader }> = {
${laderText}
}

export function radioDokumentLaden(slug: string, lang: 'de' | 'en'): Promise<RadioDoc> {
  const eintrag = LADER[slug]
  if (!eintrag) return Promise.reject(new Error('Unbekanntes Dokument: ' + slug))
  return eintrag[lang]().then((m) => m.default)
}

export function radioDokumentFinden(slug: string): RadioDokument | undefined {
  return RADIO_DOKUMENTE.find((d) => d.slug === slug)
}
`
  schreibe(join(DATEN_ZIEL, 'index.ts'), index)

  const groesse = (bytes / 1024).toFixed(0)
  console.log(`✓ Inhalt: ${DOKUMENTE.length} Dokumente, ${lader.size * 2} Fassungen, ${groesse} KB`)
  if (fehltEn.length) console.log(`  (ohne englische Fassung: ${fehltEn.join(', ')})`)
  if (befunde.length) {
    console.error('✗ Fehler beim Erzeugen:')
    for (const b of befunde) console.error(`   ${b}`)
    process.exit(1)
  }
}

// ── Medien erzeugen ────────────────────────────────────────────────────────
function findeFfmpeg() {
  if (process.env.FFMPEG) return process.env.FFMPEG
  const statisch = join(homedir(), 'Applications', 'ffmpeg-7.0.2-amd64-static', 'ffmpeg')
  if (da(statisch)) return statisch
  return spawnSync('ffmpeg', ['-version'], { stdio: 'ignore' }).status === 0 ? 'ffmpeg' : null
}

function erzeugeMedien() {
  const quelle = join(DOKU, 'ANHANG')
  const ziel = join(MEDIEN_ZIEL, 'medien')
  rmSync(MEDIEN_ZIEL, { recursive: true, force: true })
  mkdirSync(ziel, { recursive: true })

  let anzahl = 0
  const kopiere = (von, nach) => {
    if (!da(von)) return false
    schreibe(nach, readFileSync(von))
    anzahl++
    return true
  }

  // Die interaktive n8n-Oberfläche (in sich geschlossen, ~4,5 MB)
  kopiere(join(quelle, 'n8n-oberflaeche.html'), join(MEDIEN_ZIEL, 'n8n-oberflaeche.html'))

  const ablauf = []
  for (const [datei, titel, text] of ABLAUFBILDER) {
    if (kopiere(join(quelle, datei), join(ziel, datei))) {
      ablauf.push({ src: `/radio/medien/${datei}`, titel, text })
    }
  }

  const module = []
  for (const [datei, titel, text] of GESAMTBILDER) {
    if (kopiere(join(quelle, 'bilder/module', datei), join(ziel, datei))) {
      module.push({ src: `/radio/medien/${datei}`, titel, text })
    }
  }

  const ffmpeg = findeFfmpeg()
  const videos = []
  for (const [gif, name, titel, text] of VIDEOS) {
    const von = join(quelle, 'bilder', gif)
    if (!da(von)) continue
    const mp4 = join(ziel, `${name}.mp4`)
    const poster = join(ziel, `${name}.poster.jpg`)
    let fertig = false
    if (ffmpeg) {
      const lauf = spawnSync(ffmpeg, [
        '-y', '-v', 'error', '-i', von,
        '-c:v', 'libx264', '-crf', '30', '-preset', 'medium',
        '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an', mp4,
      ], { encoding: 'utf8', maxBuffer: 8 * 1024 * 1024 })
      if (lauf.status === 0 && da(mp4)) {
        spawnSync(ffmpeg, ['-y', '-v', 'error', '-ss', '1', '-i', von, '-frames:v', '1', '-q:v', '4', poster], { stdio: 'ignore' })
        anzahl++
        fertig = true
      } else {
        console.warn(`   ! ffmpeg scheiterte für ${gif}: ${(lauf.stderr || '').trim().split('\n').slice(-1)[0]}`)
      }
    }
    if (fertig) {
      videos.push({
        src: `/radio/medien/${name}.mp4`,
        poster: da(poster) ? `/radio/medien/${name}.poster.jpg` : '',
        titel,
        text,
      })
    } else if (kopiere(von, join(ziel, gif))) {
      videos.push({ src: `/radio/medien/${gif}`, poster: '', titel, text })
    }
  }

  schreibe(join(DATEN_ZIEL, 'medien.ts'), [
    '// Erzeugt von tools/build-radio-docs.mjs — nicht von Hand bearbeiten.',
    '',
    'export interface RadioMedium {',
    '  src: string',
    '  titel: string',
    '  text: string',
    '}',
    '',
    'export interface RadioVideo extends RadioMedium {',
    '  poster: string',
    '}',
    '',
    `export const RADIO_ABLAUFBILDER: RadioMedium[] = ${JSON.stringify(ablauf, null, 2)}`,
    '',
    `export const RADIO_MODULBILDER: RadioMedium[] = ${JSON.stringify(module, null, 2)}`,
    '',
    `export const RADIO_VIDEOS: RadioVideo[] = ${JSON.stringify(videos, null, 2)}`,
    '',
    '/** Die interaktive n8n-Oberfläche (eigene Datei, öffnet im neuen Tab). */',
    "export const RADIO_OBERFLAECHE = '/radio/n8n-oberflaeche.html'",
    '',
  ].join('\n'))

  console.log(`✓ Medien: ${anzahl} Dateien (ffmpeg: ${ffmpeg ? 'ja' : 'NEIN — Animationen bleiben GIF'})`)
}

// ── Downloads erzeugen (n8n-Vorlagen und Stimmdaten) ───────────────────────
/** CRC-32 nach IEEE (für das ZIP-Format). */
function crc32(puffer) {
  let tabelle = crc32.tabelle
  if (!tabelle) {
    tabelle = new Int32Array(256)
    for (let i = 0; i < 256; i++) {
      let wert = i
      for (let k = 0; k < 8; k++) wert = wert & 1 ? 0xedb88320 ^ (wert >>> 1) : wert >>> 1
      tabelle[i] = wert
    }
    crc32.tabelle = tabelle
  }
  let crc = -1
  for (const byte of puffer) crc = (crc >>> 8) ^ tabelle[(crc ^ byte) & 0xff]
  return (crc ^ -1) >>> 0
}

/**
 * Kleines ZIP ohne Fremdbibliothek (Verfahren „store" — kein Packen).
 * Die Vorlagen sind zusammen ~230 KB, das genügt vollkommen.
 */
function zipBauen(eintraege) {
  const lokal = []
  const zentral = []
  let versatz = 0
  for (const { name, daten } of eintraege) {
    const namePuffer = Buffer.from(name, 'utf8')
    const crc = crc32(daten)
    const kopf = Buffer.alloc(30)
    kopf.writeUInt32LE(0x04034b50, 0)
    kopf.writeUInt16LE(20, 4)      // Mindestversion
    kopf.writeUInt16LE(0x0800, 6)  // Dateiname in UTF-8
    kopf.writeUInt16LE(0, 8)       // Verfahren: store
    kopf.writeUInt16LE(0, 10)      // Uhrzeit
    kopf.writeUInt16LE(0x21, 12)   // Datum (1980-01-01)
    kopf.writeUInt32LE(crc, 14)
    kopf.writeUInt32LE(daten.length, 18)
    kopf.writeUInt32LE(daten.length, 22)
    kopf.writeUInt16LE(namePuffer.length, 26)
    kopf.writeUInt16LE(0, 28)
    lokal.push(kopf, namePuffer, daten)

    const eintrag = Buffer.alloc(46)
    eintrag.writeUInt32LE(0x02014b50, 0)
    eintrag.writeUInt16LE(20, 4)
    eintrag.writeUInt16LE(20, 6)
    eintrag.writeUInt16LE(0x0800, 8)
    eintrag.writeUInt16LE(0, 10)
    eintrag.writeUInt16LE(0, 12)
    eintrag.writeUInt16LE(0x21, 14)
    eintrag.writeUInt32LE(crc, 16)
    eintrag.writeUInt32LE(daten.length, 20)
    eintrag.writeUInt32LE(daten.length, 24)
    eintrag.writeUInt16LE(namePuffer.length, 28)
    eintrag.writeUInt16LE(0, 30)   // Zusatzfeld
    eintrag.writeUInt16LE(0, 32)   // Kommentar
    eintrag.writeUInt16LE(0, 34)   // Datenträger
    eintrag.writeUInt16LE(0, 36)   // interne Attribute
    eintrag.writeUInt32LE(0, 38)   // externe Attribute
    eintrag.writeUInt32LE(versatz, 42)
    zentral.push(eintrag, namePuffer)
    versatz += kopf.length + namePuffer.length + daten.length
  }

  const zentralVerzeichnis = Buffer.concat(zentral)
  const ende = Buffer.alloc(22)
  ende.writeUInt32LE(0x06054b50, 0)
  ende.writeUInt16LE(0, 4)
  ende.writeUInt16LE(0, 6)
  ende.writeUInt16LE(eintraege.length, 8)
  ende.writeUInt16LE(eintraege.length, 10)
  ende.writeUInt32LE(zentralVerzeichnis.length, 12)
  ende.writeUInt32LE(versatz, 16)
  ende.writeUInt16LE(0, 20)
  return Buffer.concat([...lokal, zentralVerzeichnis, ende])
}

function erzeugeDownloads() {
  const quelle = join(DOKU, 'NACHBAU')
  const ziel = join(MEDIEN_ZIEL, 'downloads')
  rmSync(ziel, { recursive: true, force: true })
  mkdirSync(join(ziel, 'n8n'), { recursive: true })

  // 1) n8n-Vorlagen einzeln und als Paket
  const dateien = []
  const zipEintraege = []
  for (const [datei, titel, titelEn, text, textEn] of VORLAGEN) {
    const von = join(quelle, 'ablaeufe-laufend', datei)
    if (!da(von)) {
      console.warn(`   ! Vorlage fehlt: ${datei}`)
      continue
    }
    const daten = readFileSync(von)
    schreibe(join(ziel, 'n8n', datei), daten)
    zipEintraege.push({ name: datei, daten })
    dateien.push({
      datei: `n8n/${datei}`,
      name: datei,
      titel,
      titelEn,
      text,
      textEn,
      groesse: daten.length,
    })
  }
  if (zipEintraege.length) {
    schreibe(join(ziel, 'n8n-vorlagen.zip'), zipBauen(zipEintraege))
  }

  // 2) Skript zum Holen der Piper-Stimmen
  kopiereDatei(join(quelle, 'stimmen-holen.sh'), join(ziel, 'stimmen-holen.sh'))

  const stimmen = STIMMEN.map(([name, datei, groesse, pfad]) => ({
    name,
    datei,
    groesse,
    url: `${PIPER_BASIS}${pfad}/${datei}`,
    urlJson: `${PIPER_BASIS}${pfad}/${datei}.json`,
  }))

  const ts = `// Erzeugt von tools/build-radio-docs.mjs — nicht von Hand bearbeiten.

/** Eine herunterladbare Datei (n8n-Vorlage o. Ä.). */
export interface RadioDatei {
  /** Pfad unter /radio/ … */
  datei: string
  /** Dateiname, wie er heruntergeladen wird */
  name: string
  titel: string
  titelEn: string
  text: string
  textEn: string
  /** Größe in Bytes */
  groesse: number
}

/** Eine Piper-Stimme (liegt bei HuggingFace, frei verfügbar). */
export interface RadioStimme {
  name: string
  datei: string
  groesse: string
  url: string
  urlJson: string
}

export const RADIO_VORLAGEN: RadioDatei[] = ${JSON.stringify(dateien, null, 2)}

export const RADIO_VORLAGEN_ZIP = ${JSON.stringify(zipEintraege.length ? '/radio/downloads/n8n-vorlagen.zip' : '')}

export const RADIO_STIMMEN_SKRIPT = '/radio/downloads/stimmen-holen.sh'

export const RADIO_STIMMEN: RadioStimme[] = ${JSON.stringify(stimmen, null, 2)}

export const PIPER_QUELLE = ${JSON.stringify(PIPER_BASIS)}
`
  schreibe(join(DATEN_ZIEL, 'downloads.ts'), ts)

  const gesamt = dateien.reduce((summe, d) => summe + d.groesse, 0)
  console.log(`✓ Downloads: ${dateien.length} n8n-Vorlagen (${(gesamt / 1024).toFixed(0)} KB) + ZIP + Stimmenskript`)
}

function kopiereDatei(von, nach) {
  if (!da(von)) return false
  schreibe(nach, readFileSync(von))
  return true
}

// ── Geheimnis-Gegenprobe ───────────────────────────────────────────────────
const MUSTER = [
  [/\b\d{6,12}:[A-Za-z0-9_-]{33,}\b/, 'Telegram-Bot-Token'],
  [/\b[0-9a-f]{16}:[0-9a-f]{32}\b/, 'AzuraCast-Schlüssel'],
  [/-----BEGIN [A-Z ]*PRIVATE KEY-----/, 'privater Schlüssel'],
  [/\bhf_[A-Za-z0-9]{20,}\b/, 'HuggingFace-Token'],
  [/\bsk-[A-Za-z0-9_-]{20,}\b/, 'API-Schlüssel (sk-)'],
  // Personenbezug: Name, Anschrift, eigene Adressen (nicht die Beispiele).
  [/\bDEIN-NACHNAME\b/, 'Name des Autors'],
  [/\bmarc\b/i, 'Vorname des Betreibers'],
  [/deadlinedriven\.(?:dev|de)/i, 'eigene Adresse (Domain)'],
  // Kennungen der eigenen n8n-Instanz
  [/\brQ6DFC63JlNQbiar\b/, 'n8n-Projektkennung'],
  [/\bmfdjuurEX7lAAWc2\b/, 'n8n-Zugangskennung (Telegram)'],
  [/\bradioOllamaOpenAi\b/, 'n8n-Zugangskennung (Ollama)'],
  [/"shared"\s*:/, 'n8n-Buchhaltung (shared)'],
  [/"versionId"\s*:/, 'n8n-Buchhaltung (versionId)'],
  [/"pinData"\s*:/, 'n8n-Testdaten (pinData)'],
  [/"projectId"\s*:/, 'n8n-Projektzuordnung'],
  // Beliebige Anschriften — Beispiel-Domains und Platzhalter sind erlaubt.
  [/\b[A-Za-z0-9._%+-]+@(?!beispiel\.|example\.|DEINE|YOUR)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/, 'E-Mail-Adresse'],
]

/**
 * Echte Werte des Arbeitsordners einsammeln (nur zum Vergleichen).
 *
 * Bewusst NICHT „jede Zeile“: in `azuracast-zugang.txt`, `n8n-zugang.txt` und
 * `UEBERSICHT.md` stehen auch Erklärungen, IP-Adressen und Beispiele — die
 * würden als „Wert“ jede Doku-Seite treffen. Es zählen nur die Dateien, die
 * genau einen Zugangswert enthalten, plus die Schlüsselwerte der `geheim.env`.
 */
const WERT_DATEIEN = [
  'telegram-bot-token.txt',
  'api_key.txt',
  'dj_passwort.txt',
  'bot_streamer_passwort.txt',
  'bot-test-schluessel.txt',
  'meldung-schluessel.txt',
  'meldung-schluessel-container.txt',
]

function echteWerte() {
  const werte = new Set()
  const ordner = join(ARBEIT, 'NACHBAU', 'zugangsdaten')
  if (!da(ordner)) return [...werte]

  for (const name of WERT_DATEIEN) {
    const p = join(ordner, name)
    if (!da(p)) continue
    for (const zeile of lesen(p).split('\n')) {
      const s = zeile.trim()
      if (s.length >= 8 && !s.startsWith('#')) werte.add(s)
    }
  }

  // Chat-Kennungen (reine Zahlen)
  const ids = join(ordner, 'telegram-chat-ids.txt')
  if (da(ids)) {
    for (const m of lesen(ids).matchAll(/\d{6,}/g)) werte.add(m[0])
  }

  // Geheimwerte aus der geheim.env — nur Schlüssel, die einen Wert tragen.
  // Adressen/Ports/Verzeichnisse bleiben außen vor: die stehen als Beispiel
  // in der Doku und sind keine Geheimnisse.
  const env = join(ordner, 'geheim.env')
  if (da(env)) {
    for (const zeile of lesen(env).split('\n')) {
      const [schluessel, wert] = zeile.split('=')
      if (!schluessel || !wert) continue
      const istGeheim = /(PASSWOR|TOKEN|SECRET|SCHLUESSEL|SCHLUES)/i.test(schluessel) || schluessel.endsWith('_KEY')
      if (!istGeheim) continue
      const sauber = wert.trim()
      if (sauber.length < 8) continue
      if (/^(\d{1,3}\.){3}\d{1,3}/.test(sauber) || /^https?:/.test(sauber) || /^\/|^\d+$/.test(sauber)) continue
      werte.add(sauber)
    }
  }

  return [...werte]
}

function pruefeAusgabe() {
  const werte = echteWerte()
  const befunde = []

  const durchsucheText = (pfad, mitMustern) => {
    const text = lesen(pfad)
    if (mitMustern) {
      for (const [rx, name] of MUSTER) {
        if (rx.test(text)) befunde.push(`${pfad}: Muster „${name}“ gefunden`)
      }
    }
    for (const wert of werte) {
      if (text.includes(wert)) befunde.push(`${pfad}: echter Zugangswert enthalten (Länge ${wert.length})`)
    }
  }

  const gehe = (p, mitMustern) => {
    for (const e of readdirSync(p, { withFileTypes: true })) {
      const kind = join(p, e.name)
      if (e.isDirectory()) gehe(kind, mitMustern)
      else if (/\.(ts|json|html)$/.test(e.name)) durchsucheText(kind, mitMustern)
    }
  }

  if (da(DATEN_ZIEL)) gehe(DATEN_ZIEL, true)
  if (da(MEDIEN_ZIEL)) gehe(MEDIEN_ZIEL, false) // nur exakte Werte, keine Muster
  // Die Vorlagen sind Textdateien — hier auch auf Geheimnis-Muster prüfen.
  if (da(join(MEDIEN_ZIEL, 'downloads'))) gehe(join(MEDIEN_ZIEL, 'downloads'), true)

  return { befunde, geprueft: werte.length }
}

// ── Ablauf ─────────────────────────────────────────────────────────────────
console.log(`Quelle:  ${DOKU}`)
console.log(`Inhalt:  ${DATEN_ZIEL}`)
if (!OHNE_MEDIEN) console.log(`Medien:  ${MEDIEN_ZIEL}`)

if (NUR_PRUEFEN) {
  const { befunde, geprueft } = pruefeAusgabe()
  if (befunde.length) {
    console.error('✗ Prüfung fehlgeschlagen:')
    for (const b of befunde) console.error(`   ${b}`)
    process.exit(1)
  }
  console.log(`✓ Prüfung sauber (${geprueft} echte Werte verglichen).`)
  process.exit(0)
}

erzeugeInhalt()
if (!OHNE_MEDIEN) {
  erzeugeMedien()
  erzeugeDownloads()
}

const { befunde, geprueft } = pruefeAusgabe()
if (befunde.length) {
  console.error('✗ Geheimnis-Prüfung fehlgeschlagen:')
  for (const b of befunde) console.error(`   ${b}`)
  process.exit(1)
}
console.log(`✓ Geheimnis-Prüfung: sauber (${geprueft} echte Werte verglichen, 0 Treffer).`)
