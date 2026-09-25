#!/usr/bin/env python3
"""Übersetzt die deutschen Texte im Code ins Englische (Zweig `en`).

Übersetzt werden **nur** Kommentare, Dokumentationsblöcke und deutsche Texte
innerhalb von Zeichenketten. Code, Bezeichner, Pfade und Schlüssel bleiben
unangetastet — das wird nach jedem Schreiben geprüft:

  1. Syntax:  `py_compile` (.py), `bash -n` (.sh), `node --check` (.js)
  2. Gerüst:  die Zeichenfolge der Code-Token (Kommentare weg, Texte als «S»)
              muss vorher und nachher gleich sein
  3. Platzhalter: `{…}`, `%s`, `\\n`, `$VAR` in Texten müssen erhalten bleiben

Geschrieben wird nach `EN/<pfad>` — also dieselbe Stelle wie bei den
übersetzten Dokumenten. Ein Zwischenspeicher (`uebersetzungen-code-en.json`)
verhindert doppelte Anfragen; das Sprachmodell läuft lokal (Ollama).

Aufruf:
  python3 werkzeuge/code-uebersetzen-en.py --alle            # alle Dateien
  python3 werkzeuge/code-uebersetzen-en.py <datei> [datei …]
  python3 werkzeuge/code-uebersetzen-en.py --alle --pruefen  # nur prüfen
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tokenize
import urllib.request
from io import StringIO
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent.parent
ADRESS = "http://192.168.178.187:11434"
MODELL = "qwen3-coder:30b"
SPEICHER = PROJEKT / "werkzeuge" / "doku" / "uebersetzungen-code-en.json"
# Wörtliche Ersetzungen für Schnittstellen-Token (Schalter, Wege, Umfeldnamen):
# sie stehen teils nackt in Skripten (ohne Anführungszeichen) und werden
# deshalb am Ende auf jede erzeugte Datei angewandt.
ROHTAUSCH_DATEI = PROJEKT / "werkzeuge" / "doku" / "rohtausch.json"
ENDUNGEN = (".py", ".sh", ".js", ".service", ".vorlage", ".template", ".yml")
UEBERSPRINGEN = {"EN", "DocOfficial", ".git", "__pycache__", "node_modules", "ANHANG"}

# Englische Namen der EN-Fassung (Umstellung vom 2026-09-26):
# deutscher Ordnername/Dateiname im Projekt -> englischer Name unter EN/.
EN_ORDNER = {
    "dienst": "service", "werkzeuge": "tools", "DOKU": "DOCS",
    "NACHBAU": "REBUILD", "ANHANG": "APPENDIX", "doku": "docs",
    "meldungen": "news", "ablaeufe-laufend": "running-workflows",
    "eigene-stimme": "own-voice", "verworfen": "discarded",
    "zugangsdaten": "credentials", "bilder": "images",
}
EN_DATEIEN = {
    "ANORDNUNG.md": "LAYOUT.md", "n8n-oberflaeche.html": "n8n-interface.html",
    "gesamt-konfiguration-alle-werte.png": "overall-configuration-all-values.png",
    "gesamt-radio-ai-moderator.png": "overall-radio-ai-moderator.png",
    "gesamt-radio-telegram-agent.png": "overall-radio-telegram-agent.png",
    "gesamt-DEIN-WEBHOOK-PFAD.png": "overall-voices-from-films.png",
    "gesamt-werkzeug-azuracast.png": "overall-tool-azuracast.png",
    "gesamt-werkzeug-meldungen.png": "overall-tool-news.png",
    "gesamt-werkzeug-radio.png": "overall-tool-radio.png",
    "modulplan.json": "moduleplan.json", "startmassstaebe.json": "startscales.json",
    "BAU.md": "BUILD.md", "BETRIEB.md": "OPERATIONS.md",
    "HANDBUCH.md": "MANUAL.md", "STIMME.md": "VOICE.md",
    "searxng-einrichten.md": "searxng-setup.md", "sender-einrichten.md": "station-setup.md",
    "stimmen-holen.sh": "fetch-voices.sh", "stimmen-und-modelle.md": "voices-and-models.md",
    "umgebung.md": "environment.md", "vorlage.md": "template.md",
    "zugangsdaten.md": "credentials.md", "UEBERSICHT.md": "OVERVIEW.md",
    "AzuraWerkzeug.json": "AzuraTool.json", "MeldungenWerkzeug.json": "NewsTool.json",
    "RadioWerkzeug.json": "RadioTool.json", "StimmenBot.json": "VoiceBot.json",
    "sprechdienst.service": "speech-service.service",
    "stimme_pruefen.py": "check-voice.py", "stimme_sammeln.py": "collect-voice.py",
    "stimme_erweitern.py": "extend-voice.py", "sprechdienst.py": "speech-service.py",
    "cluster-proben.sh": "cluster-samples.sh",
    "einrichten-stimmen-dienst.sh": "setup-voice-service.sh",
    "rvc-trainieren.sh": "rvc-train.sh", "stimmen_dienst.py": "voice-service.py",
    "tg-sprachnachricht.sh": "tg-voice-message.sh",
    "warten-und-proben.sh": "wait-and-sample.sh", "xtts-klon.py": "xtts-clone.py",
    "geheim.env.vorlage": "secret.env.template",
    "katalog.py": "catalog.py", "meldungen.py": "news.py", "suche.py": "search.py",
    "agent-einspielen-nur.sh": "agent-import-only.sh",
    "agent-einspielen.sh": "agent-import.sh",
    "agent-nachbereiten.py": "agent-postprocess.py",
    "agent-patchen.py": "agent-patch.py", "agent-patchen.sh": "agent-patch.sh",
    "agent-wf-bauen-v2-dreistufig.py": "agent-wf-build-v2-threestage.py",
    "agent-wf-bauen.py": "agent-wf-build.py",
    "altfassungen-notieren.py": "note-old-versions.py",
    "anordnung-doku.sh": "layout-docs.sh", "anordnung-pruefen.py": "layout-check.py",
    "anordnung-uebersicht.py": "layout-overview.py",
    "antwort-test.js": "answer-test.js", "antwort-test.sh": "answer-test.sh",
    "antworten.js": "answers.js",
    "archiv-anlegen.py": "create-archive.py", "archiv-rahmen.py": "archive-frame.py",
    "auswertung.py": "evaluation.py",
    "bilder-stitch.py": "image-stitch.py", "bilder-zuschnitt.py": "image-crop.py",
    "bildplan.py": "imageplan.py",
    "bot-ausfuehrung.js": "bot-execution.js", "bot-daten-setzen.py": "bot-data-set.py",
    "bot-letzte.js": "bot-last.js",
    "daten-setzen.py": "data-set.py", "deutsch-texte.py": "german-texts.py",
    "dienst-einspielen.sh": "service-import.sh", "doku-notiz.py": "docs-note.py",
    "code-uebersetzen-en.py": "code-translate-en.py",
    "doc-official-bauen.py": "doc-official-build.py",
    "doku-pruefen.py": "docs-check.py", "n8n-doku-bauen.py": "n8n-docs-build.py",
    "uebersetzungen-en.json": "translations-en.json",
    "durchlauf.sh": "full-run.sh", "eine.js": "one.js", "einspielen.sh": "import.sh",
    "fassung-sichern.sh": "version-save.sh", "formen.sh": "shapes.sh",
    "frage.sh": "ask.sh", "gif-aufnahme.js": "gif-capture.js", "gif-bauen.py": "gif-build.py",
    "hol-testerschluessel.js": "fetch-testkeys.js",
    "import-agent-vorbereiten.py": "import-agent-prepare.py",
    "import-vorbereiten.py": "import-prepare.py", "js-holen.py": "fetch-js.py",
    "katalog-test.sh": "catalog-test.sh",
    "keine-ablehnung-test.sh": "no-rejection-test.sh",
    "konfiguration-einspielen.sh": "config-import.sh",
    "konfiguration-pruefen.py": "config-check.py",
    "kontext-test.sh": "context-test.sh", "kontext2-test.sh": "context2-test.sh",
    "kurz-test.js": "short-test.js", "kurz-test.sh": "short-test.sh",
    "moderator-zurechtmachen.py": "moderator-prepare.py",
    "modulbilder-massstaebe.py": "module-images-scales.py",
    "modulbilder-plan.py": "module-images-plan.py",
    "schlagwort-anlegen.py": "create-tag.py",
    "sofort-bot-test.sh": "instant-bot-test.sh", "sofort-jetzt.sh": "instant-now.sh",
    "sofort-knopf-test.sh": "instant-button-test.sh",
    "sperrfrist-aus.sh": "cooldown-off.sh",
    "sprache-test.sh": "speech-test.sh", "sprache2-test.sh": "speech2-test.sh",
    "statische-daten-patchen.py": "static-data-patch.py",
    "stimme-pruefen.sh": "voice-check.sh",
    "telegram-menue.sh": "telegram-menu.sh", "telegram-wf-bauen.py": "telegram-wf-build.py",
    "url-test-bauen.py": "url-test-build.py", "vorschau.py": "preview.py",
    "18-live-zugang-setzen.sh": "18-live-access-set.sh",
    "19-meldungen-test.py": "19-news-test.py", "21-bot-meldungen-test.py": "21-bot-news-test.py",
    "22-suchbot-beispiel.py": "22-searchbot-example.py",
    "23-lautstaerke-test.py": "23-volume-test.py", "24-live-pegel.py": "24-live-level.py",
    "05-listenwege-test.sh": "05-playlist-paths-test.sh",
    "06-leeren-umbenennen-test.sh": "06-clear-rename-test.sh",
    "07-umbenennen-test.sh": "07-rename-test.sh",
    "08-dienst-einspielen.sh": "08-service-import.sh",
    "09-dienst-test.sh": "09-service-test.sh", "10-zerlegen-test.py": "10-split-test.py",
    "11-dienst-art-test.js": "11-service-type-test.js",
    "11-dienst-art-test.sh": "11-service-type-test.sh",
    "12-neubau-vergleich.py": "12-rebuild-compare.py",
    "13-listen-patchen.py": "13-playlists-patch.py",
    "13-listen-patchen.sh": "13-playlists-patch.sh",
    "14-listen-einspielen.sh": "14-playlists-import.sh",
    "15-bot-listen-test.py": "15-bot-playlists-test.py",
    "16-ausfuehrungen.sh": "16-executions.sh",
    "02-kurz-test.js": "02-short-test.js", "03-tempo-patchen.py": "03-tempo-patch.py",
    "04-einspielen.sh": "04-import.sh",
}


def en_pfad(rel: Path) -> Path:
    """Deutscher Projektpfad -> englischer Pfad der EN-Fassung."""
    teile = [EN_ORDNER.get(t, t) for t in rel.parts]
    if teile:
        teile[-1] = EN_DATEIEN.get(teile[-1], teile[-1])
    return Path(*teile)

# Wörter, an denen deutscher Text erkannt wird
DEUTSCH = re.compile(
    r"[äöüßÄÖÜ]|\b(der|die|das|und|nicht|wird|werden|sind|ist|war|eine|einen|einem|dem|den|für|über|aus|mit|bei|"
    r"nach|wenn|dann|noch|nur|auch|aber|oder|muss|darf|kann|soll|läuft|liegt|gilt|kommt|geht|wird's|Datei|Dateien|"
    r"Wert|Werte|Werten|Name|Namen|Anzahl|Fehler|Pfad|Pfade|Dienst|Dienste|Titel|Titelwunsch|Stunde|Stunden|Minute|Minuten|"
    r"Befehl|Befehle|Bereich|Quelle|Quellen|Sender|Sendung|Stimme|Stimmen|Nachricht|Nachrichten|Schlüssel|Passwort|"
    r"Anzeige|Antwort|Frage|Fragen|Suche|suchen|spielen|spiele|wünscht|Wunsch|Wünsche|Moderation|Ansage|Ansagen|Meldung|"
    r"Meldungen|Prüfung|prüfen|Prüflauf|Einstellung|Einstellungen|Wiedergabeliste|Wiedergabelisten|Titelnummer|Zeile|Zeilen|"
    r"Abschnitt|Abschnitte|Beispiel|Beispiele|Original|Betreiber|Kapitel|Anleitung|Hinweis|Hinweise|Ergebnis|Ergebnisse|"
    r"Tabelle|Spalte|Spalten|Ordner|Dateiname|Umgebung|Zugang|Zugangsdaten|Kennung|Kanal|Format|Grösse|Größe|Länge|Dauer)\b"
)
TRENNER = "@@@"
STAPEL = 15          # Stücke je Anfrage an das Sprachmodell (klein halten:
                     # große Stapel können die Zeitgrenze sprengen)
# Stücke, die nicht übersetzt werden: Pfade, Adressen, Befehle, Platzhalter
# (Adressen und Pfade nur, wenn das Stück NICHTS anderes ist — sonst ginge
# der Text daneben, etwa in `// Kommentar`-Zeilen, verloren)
NICHT_UEBERSETZEN = re.compile(r"^\S*://\S*$|^\s*[/~.$]\S*$|^\s*[A-Za-z0-9_.-]+$|^\s*(sudo|curl|ssh|bash|python3?|docker|pct|systemctl|git|nano)\b")

# Befehlszeilen in Doku-Texten: „python3 x.py …   Beschreibung“ — der
# Beschreibungsteil ist Text und wird übersetzt, der Befehl selbst nicht.
BEFEHL_TEXT = re.compile(
    r"^\s*(?:[A-Z][A-Z0-9_]*=\S+\s+)*"
    r"(python3?|docker|pct|systemctl|curl|bash|sh|git|nano)\b")


def befehlsrest(zeile: str) -> tuple[int, int] | None:
    """Position der Beschreibung hinter einer Befehlszeile (sonst None)."""
    if not BEFEHL_TEXT.match(zeile):
        return None
    treffer = list(re.finditer(r"\s{2,}", zeile))
    if not treffer:
        return None
    von = treffer[-1].end()
    rest = zeile[von:]
    if not rest.strip() or DEUTSCH.search(rest) is None:
        return None
    return von, len(zeile)


def dreifach(zeile: str) -> int | None:
    """Index der drei Anführungszeichen, die einen Textblock begrenzen.

    Vorkommen in Zeichenketten (drei Zeichen als Text) und in Kommentaren
    zählen nicht — sonst würden Code-Zeilen den Blockzustand umschalten.
    Mittige Blockanfänge (Zuweisung plus die drei Zeichen) gelten dagegen
    als Begrenzer.
    """
    pos = zeile.find('"""')
    while pos != -1:
        if pos > 0 and zeile[pos - 1] in "\"'":
            pass                                  # steht in einer Zeichenkette
        else:
            km = kommentar_position(zeile)
            if km is None or pos < km:
                return pos
        pos = zeile.find('"""', pos + 3)
    return None


# ── Sprachmodell ────────────────────────────────────────────────────────────
def schuetzen(text: str) -> tuple[str, list[str]]:
    """Ersetzt Platzhalter durch Ersatzziffern, die das Modell nicht anfasst."""
    werte: list[str] = []

    def ersatz(m: re.Match[str]) -> str:
        werte.append(m.group(0))
        return f"«{len(werte) - 1}»"

    return PLATZHALTER.sub(ersatz, text), werte


def freigeben(text: str, werte: list[str]) -> str:
    for i, wert in enumerate(werte):
        text = text.replace(f"«{i}»", wert)
    return text


def uebersetze_stuecke(stuecke: list[str], kontext: str) -> list[str]:
    """Übersetzt eine Liste von Textstücken (gleiche Reihenfolge, gleiche Anzahl).

    Das Sprachmodell bekommt die Stücke mit `@@@` getrennt und muss sie genauso
    zurückgeben. Jede Antwort wird geprüft: keine Nummerierung, keine
    Zeilenumbrüche (die Stücke sind Zeilenschnipsel), Anzahl muss stimmen.
    """
    if not stuecke:
        return []
    geschuetzt: list[str] = []
    werte_liste: list[list[str]] = []
    for stueck in stuecke:
        geschuetztes, werte = schuetzen(stueck)
        geschuetzt.append(geschuetztes)
        werte_liste.append(werte)
    auftrag = (
        "Translate the following German text fragments of a software project into English.\n"
        "Rules:\n"
        f"- The fragments are separated by a line containing only {TRENNER}.\n"
        f"- Answer with the {len(stuecke)} translated fragments in the same order, also "
        f"separated by a line containing only {TRENNER}. Nothing else — no numbering, no "
        "comments, no explanations.\n"
        "- Keep the meaning; do not shorten. Keep code identifiers, paths, URLs, options "
        "and placeholders ({…}, %s, $VAR, \\n, \\t) exactly as they are.\n"
        "- If a fragment is already English, return it unchanged.\n"
        f"- Context: {kontext}\n\n"
    )
    auftrag += f"\n{TRENNER}\n".join(geschuetzt)
    daten = json.dumps({"model": MODELL, "prompt": auftrag, "stream": False,
                        "options": {"temperature": 0.1}}).encode()
    anfrage = urllib.request.Request(f"{ADRESS}/api/generate", data=daten,
                                    headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(anfrage, timeout=300) as antwort:
        text = json.loads(antwort.read().decode()).get("response", "")

    teile = [t.strip() for t in text.split(TRENNER)]
    # Manche Modelle nummerieren trotzdem: führende „[3]“ o. Ä. entfernen.
    teile = [re.sub(r"^\[\d+\]\s*", "", t) for t in teile]
    if len(stuecke) == 1:
        # Ein Stück: keine Trennung nötig (das Modell schreibt sie gern mit).
        # Mehrzeilige Antworten sind Beiwerk — die Stücke sind immer
        # Zeilenschnipsel: Trennzeichen, Echo und Ankündigung verwerfen.
        zeilen_antwort = [z.strip() for z in text.splitlines()
                          if z.strip() and z.strip() != TRENNER]
        zeilen_antwort = [z for z in zeilen_antwort if z != stuecke[0].strip()]
        if len(zeilen_antwort) > 1 and zeilen_antwort[0].endswith(":"):
            zeilen_antwort = zeilen_antwort[1:]
        teile = [zeilen_antwort[0] if zeilen_antwort else ""]
    if len(teile) != len(stuecke):
        raise RuntimeError(f"Antwort zergliedert sich in {len(teile)} statt {len(stuecke)} Teile")
    teile = [freigeben(t, w) for t, w in zip(teile, werte_liste)]
    for alt, neu in zip(stuecke, teile):
        if not neu:
            raise RuntimeError(f"leere Übersetzung für {alt[:40]!r}")
        if "\n" in neu:
            raise RuntimeError(f"Übersetzung mit Zeilenumbruch: {neu[:60]!r}")
    return teile


NICHT_UEBERSETZT: list[str] = []


def uebersetze_einzeln(stuecke: list[str], kontext: str) -> list[str]:
    """Notnagel: jedes Stück einzeln übersetzen (wenn die Sammelantwort zerfällt).

    Bleibt ein Stück hartnäckig (Zeitüberschreitung, leere Antwort), wird es
    UNVERÄNDERT übernommen und gemerkt — besser als ein ganzer Abbruch; die
    Liste steht am Ende im Bericht und wird von Hand nachgeholt.
    """
    ergebnis: list[str] = []
    for stueck in stuecke:
        try:
            ergebnis += uebersetze_stuecke([stueck], kontext)
        except Exception:                               # noqa: BLE001
            ergebnis.append(stueck)
            NICHT_UEBERSETZT.append(stueck)
    return ergebnis


def speicher() -> dict[str, str]:
    if SPEICHER.exists():
        return json.loads(SPEICHER.read_text(encoding="utf-8"))
    return {}


def rohtausch() -> list[tuple[re.Pattern[str], str]]:
    """Wörtliche Ersetzungen mit Wortgrenzen (Bezeichner sicher).

    `KATALOG_URL` wird zu `CATALOG_URL`, `TROCKENLAUF` aber nicht von
    `TROCKEN` angetastet — die Grenzen richten sich danach, ob das Wort
    mit einem Wortzeichen beginnt/endet.
    """
    roh: dict[str, str] = {}
    if ROHTAUSCH_DATEI.exists():
        roh = json.loads(ROHTAUSCH_DATEI.read_text(encoding="utf-8"))
    muster: list[tuple[re.Pattern[str], str]] = []
    for alt, wert in roh.items():
        links = r"(?<![A-Za-z0-9_])" if re.match(r"\w", alt) else ""
        rechts = r"(?![A-Za-z0-9_])" if re.search(r"\w$", alt) else ""
        muster.append((re.compile(links + re.escape(alt) + rechts), wert))
    return muster


def cache_schluessel(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:24]


def uebersetzung(stueck: str, speicher_datei: dict[str, str]) -> str:
    """Übersetzung zum Stück: voller Text, sonst Einzelwort ohne Randleerzeichen."""
    u = speicher_datei.get(cache_schluessel(stueck))
    if u is not None:
        return u
    kern = stueck.strip()
    if kern != stueck:
        u = speicher_datei.get(cache_schluessel(kern))
        if u is not None:
            vorn = stueck[:len(stueck) - len(stueck.lstrip())]
            hinten = stueck[len(stueck.rstrip()):]
            return vorn + u + hinten
    return stueck


# ── Zerlegen und Zusammensetzen ────────────────────────────────────────────
def ist_deutsche_datei(text: str) -> bool:
    """Grobe Erkennung: enthält die Datei überhaupt deutschen Text?"""
    if re.search(r"[äöüßÄÖÜ]", text):
        return True
    return len(DEUTSCH.findall(text)) >= 3


def stelle_stuecke(zeilen: list[str], endung: str,
                   speicher_datei: dict[str, str] | None = None
                   ) -> list[tuple[int, int, int, str]]:
    """Wo steht übersetzbarer Text? Rückgabe: (Zeilennummer, von, bis, Anführung).

    `von`/`bis` sind Zeichenpositionen innerhalb der Zeile (bis = exklusiv);
    `Anführung` ist `"` oder `'`, wenn das Stück in einer Zeichenkette steht
    (dort dürfen keine gleichen Anführungszeichen hineinkommen), sonst "".
    """
    stellen: list[tuple[int, int, int, str]] = []

    def passt(text: str) -> bool:
        # Ohne Buchstaben gibt es nichts zu übersetzen (‘‘, $2, 2026-09-22 …) —
        # solche Schnipsel sind Code oder Zahlwerk und bleiben unangetastet.
        kern = text.strip()
        if not kern or re.search(r"[A-Za-z]", kern) is None:
            return False
        # Einzelwörter (ohne Leerzeichen/Punkt) gelten nur dann als Text,
        # wenn im Zwischenspeicher eine Übersetzung hinterlegt ist — so sind
        # Code-Bezeichner weiterhin geschützt, Wörter wie „spielen“ oder
        # „--trocken“ aber übersetzbar.
        if re.fullmatch(r"[A-Za-z0-9_.\-äöüßÄÖÜ]+", kern):
            return (speicher_datei is not None
                    and cache_schluessel(kern) in speicher_datei)
        return not NICHT_UEBERSETZEN.search(text)

    def nimm_doku(nr: int, zeile: str, von: int, bis: int) -> None:
        if passt(zeile[von:bis]):
            stellen.append((nr, von, bis, ""))
            return
        rest = befehlsrest(zeile)
        if rest is not None:
            stellen.append((nr, rest[0], rest[1], ""))
    im_text = False          # innerhalb eines """- oder '''-Blocks
    for nr, zeile in enumerate(zeilen):
        streifen = zeile.strip()
        if endung == ".py":
            if im_text:
                ende = dreifach(zeile)
                if ende is None:
                    nimm_doku(nr, zeile, 0, len(zeile))
                    continue
                nimm_doku(nr, zeile, 0, ende)
                im_text = False
                continue
            start = dreifach(zeile)
            if start is not None:
                rest = zeile[start + 3:]
                if '"""' in rest:                      # einzeiliger Text
                    nimm_doku(nr, zeile, start + 3, start + 3 + rest.rfind('"""'))
                else:
                    im_text = True
                    nimm_doku(nr, zeile, start + 3, len(zeile))
                continue
        if streifen.startswith("#"):
            marke = zeile.index("#") + 1
            if passt(zeile[marke:]):
                stellen.append((nr, marke, len(zeile), ""))
            continue
        # Kommentar am Zeilenende (nicht in Anführungszeichen)
        position = kommentar_position(zeile)
        if position is not None and passt(zeile[position + 1:]):
            stellen.append((nr, position + 1, len(zeile), ""))
        # Zeichenkette in der Zeile (Anzeigetexte)
        for von, bis, anfuehrung in zeichenketten(zeile):
            if position is not None and von > position:      # steht im Kommentar
                continue
            if passt(zeile[von:bis]):
                stellen.append((nr, von, bis, anfuehrung))
    return stellen


def zeichenketten(zeile: str) -> list[tuple[int, int, str]]:
    """Alle vollständigen Zeichenketten einer Zeile: (von, bis, Anführung).

    Läuft Zeichen für Zeichen, damit Anführungszeichen richtig gepaart werden
    (ein Muster würde auf Zeilen mit mehreren Ketten danebenliegen).
    """
    stellen: list[tuple[int, int, str]] = []
    i = 0
    while i < len(zeile):
        z = zeile[i]
        if z in "\"'":
            j = i + 1
            while j < len(zeile):
                if zeile[j] == "\\":
                    j += 2
                    continue
                if zeile[j] == z:
                    break
                j += 1
            if j < len(zeile):
                stellen.append((i + 1, j, z))
                i = j + 1
                continue
        i += 1
    return stellen


def kommentar_position(zeile: str) -> int | None:
    """Index des `#`, das einen Kommentar beginnt (nicht in Anführungszeichen)."""
    in_einfach = in_doppelt = False
    for i, z in enumerate(zeile):
        if z == "'" and not in_doppelt:
            in_einfach = not in_einfach
        elif z == '"' and not in_einfach:
            in_doppelt = not in_doppelt
        elif z == "#" and not in_einfach and not in_doppelt:
            return i
    return None


def typografisch(text: str, anfuehrung: str, ist_bytes: bool = False) -> str:
    """Gerade Anführungszeichen wandeln — Platzhalter wie {k['name']} auslassen.

    Das Trennzeichen der Stelle wird IMMER gewandelt: ein Apostroph in
    „What's“ würde sonst die Zeichenkette sprengen. Andere gerade Zeichen nur
    im Fließtext (mit Leerzeichen) — in Code-Stücken wie b'name="' wäre die
    Wandlung falsch.
    """
    fliess = not ist_bytes and (anfuehrung == "" or " " in text)

    def wandle(teil: str) -> str:
        if anfuehrung in ("'", ""):
            teil = re.sub(r"(?<!\\)'([^']*)'", "\u2018\\1\u2019", teil)
            teil = re.sub(r"(?<!\\)'", "\u2019", teil)
        if anfuehrung in ('"', ""):
            teil = re.sub(r"(?<!\\)\"([^\"]*)\"", "\u201c\\1\u201d", teil)
            teil = re.sub(r'(?<!\\)"', "\u201c", teil)
        if fliess and anfuehrung == '"':
            teil = re.sub(r"(?<!\\)'([^']*)'", "\u2018\\1\u2019", teil)
            teil = re.sub(r"(?<!\\)'", "\u2019", teil)
        return teil

    teile = []
    letzte = 0
    for m in PLATZHALTER.finditer(text):
        teile.append(wandle(text[letzte:m.start()]))
        teile.append(m.group(0))
        letzte = m.end()
    teile.append(wandle(text[letzte:]))
    return "".join(teile)


def setze_zusammen(zeilen: list[str], stellen: list[tuple[int, int, int, str]],
                   uebersetzt: list[str], endung: str = "") -> list[str]:
    # WICHTIG: je Zeile von RECHTS nach LINKS ersetzen — sonst verschieben sich
    # die Positionen der weiteren Stellen derselben Zeile, sobald eine
    # Übersetzung länger oder kürzer ist als das Original.
    neu = list(zeilen)
    nach_zeile: dict[int, list[tuple[int, int, str, str]]] = {}
    for (nr, von, bis, anfuehrung), ersatz in zip(stellen, uebersetzt):
        nach_zeile.setdefault(nr, []).append((von, bis, anfuehrung, ersatz))
    for nr, liste in nach_zeile.items():
        zeile = neu[nr]
        for von, bis, anfuehrung, ersatz in sorted(liste, key=lambda s: s[0], reverse=True):
            alt = zeile[von:bis]
            # Leerzeichen am Anfang erhalten (Kommentarzeichen trennt sonst)
            if alt.startswith(" ") and not ersatz.startswith(" "):
                ersatz = " " + ersatz
            # Gerade Anführungszeichen der Übersetzung in typografische
            # wandeln (Einzelheiten in `typografisch`): gerade Zeichen können
            # Zeichenketten sprengen — ein Apostroph in „What's new“ beendet
            # z. B. einen einfachen Shell-Abschnitt. Wurde der Baustein
            # unverändert übernommen, bleibt er wie er ist — er stammt dann
            # eins zu eins aus der geprüften Quelle. In Python-Dokumentzeilen
            # ("""-Blöcke, kein Anführungszeichen-Kontext) NICHT wandeln:
            # dort stehen oft Ausdrücke wie {tabelle([("…", "…")])}, deren
            # gerade Zeichen CODE sind.
            if (ersatz.strip() and ersatz.strip() != alt.strip()
                    and not (endung == ".py" and anfuehrung == "")):
                ist_bytes = (von > 0 and zeile[von - 1] in "bB"
                             and (von < 2 or not zeile[von - 2].isalnum()))
                ersatz = typografisch(ersatz, anfuehrung, ist_bytes)
            zeile = zeile[:von] + ersatz + zeile[bis:]
        neu[nr] = zeile
    return neu


# ── Prüfungen ──────────────────────────────────────────────────────────────
# Befehls-Schalter (--einmal, --trocken …) werden BEWUSST übersetzt
# (--once, --dry-run) — sie sind keine Platzhalter und stehen deshalb nicht
# mehr in der Musterliste. Alle übrigen Platzhalter bleiben geschützt.
PLATZHALTER = re.compile(r"\{[^}]*\}|%[sdf%]|\$[A-Za-z_][A-Za-z0-9_]*|\\[nt]")


def platzhalter(text: str) -> list[str]:
    # Ausdrücke in geschweiften Klammern mit doppelten Anführungszeichen
    # (Vorlagen wie {bild_html("…", "…")}) NICHT vergleichen — dort darf
    # der Text innen übersetzt werden. Ebenso Ausdrücke MIT Leerzeichen
    # (etwa `{ /* Kommentar */ }` in JavaScript-Schnipseln): dort steht Text,
    # kein Platzhalter.
    return sorted(p for p in PLATZHALTER.findall(text)
                  if not (p.startswith("{") and '"' in p)
                  and not (p.startswith("{") and " " in p))


TEXT_TOKENS = {tokenize.STRING}
FSTRING_MIDDLE = getattr(tokenize, "FSTRING_MIDDLE", None)
if FSTRING_MIDDLE is not None:
    # Ab Python 3.12 sind die Texte in f-Strings eigene Token — ohne Maske
    # hielte die Gerüstprüfung jede übersetzte f-Zeichenkette für Code.
    TEXT_TOKENS.add(FSTRING_MIDDLE)


def geruest_python(quelle: str) -> str | None:
    """Tokengerüst: Kommentare weg, Texte als «S» — Code bleibt erkennbar."""
    try:
        teile = []
        for tok in tokenize.generate_tokens(StringIO(quelle).readline):
            if tok.type == tokenize.COMMENT:
                continue
            if tok.type == FSTRING_MIDDLE:
                # Texte in f-Zeichenketten NICHT vergleichen: die Wortstellung
                # verschiebt sie beim Übersetzen (deutsch „… aus {x} heraus“,
                # englisch „… from {x}“). Die {…}-Felder selbst sichert die
                # Platzhalterprüfung ab.
                continue
            if tok.type in TEXT_TOKENS:
                teile.append("«S»")
            else:
                teile.append(tok.string)
        return " ".join(teile)
    except tokenize.TokenError:
        return None


def _maskiere(zeile: str) -> str:
    """Zeichenketten in einer Zeile durch S ersetzen — Zeichen für Zeichen.

    Wichtig: `'"'` (ein Anführungszeichen als Text) darf die Zählung nicht
    stören — deshalb EIN Durchlauf mit passendem Gegenstück statt zweier
    Ersetzungsläufe.
    """
    ergebnis = []
    i = 0
    while i < len(zeile):
        z = zeile[i]
        if z in "'\"":
            j = zeile.find(z, i + 1)
            if j != -1:
                ergebnis.append(z + "S" + z)
                i = j + 1
                continue
        ergebnis.append(z)
        i += 1
    return "".join(ergebnis)


def geruest_schlicht(quelle: str, endung: str) -> str:
    """Für Shell/JS: Kommentarzeilen weg, Anführungszeichen-Inhalte ersetzt."""
    heiler = re.compile(r"#[^\n]*") if endung != ".js" else re.compile(r"//[^\n]*")
    teile = []
    for zeile in quelle.splitlines():
        # Erst die Anführungszeichen-Inhalte maskieren, DANN Kommentare entfernen:
        # sonst schneidet das `#` in `${#VAR}` mitten in den Text. Typografische
        # Zeichen zählen erst NACH dem Maskieren wie gerade — ein ’ innerhalb
        # einer Zeichenkette darf die Maskierung nicht stören, ein ’ im freien
        # Text soll aber dem ’… der Übersetzung entsprechen.
        ohne = _maskiere(zeile)
        ohne = heiler.sub("#K" if endung != ".js" else "//K", ohne)
        ohne = (ohne.replace("\u2019", "'").replace("\u2018", "'")
                    .replace("\u201c", '"').replace("\u201d", '"'))
        teile.append(ohne.strip())
    return "\n".join(teile)


def syntax_okatei(pfad: Path) -> tuple[bool, str]:
    endung = pfad.suffix
    if endung == ".py":
        befehl = [sys.executable, "-m", "py_compile", str(pfad)]
    elif endung == ".sh":
        befehl = ["bash", "-n", str(pfad)]
    elif endung == ".js":
        befehl = ["node", "--check", str(pfad)]
    else:
        return True, ""
    ergebnis = subprocess.run(befehl, capture_output=True, text=True)
    return ergebnis.returncode == 0, (ergebnis.stderr or ergebnis.stdout).strip()[:300]


# ── Ablauf ─────────────────────────────────────────────────────────────────
def dateien(wurzel: Path) -> list[Path]:
    alle: list[Path] = []
    for p in sorted(wurzel.rglob("*")):
        if not p.is_file() or p.suffix not in ENDUNGEN:
            continue
        rel = p.relative_to(wurzel)
        if any(teil in UEBERSPRINGEN for teil in rel.parts):
            continue
        if any(teil.startswith(".") for teil in rel.parts):
            continue
        alle.append(p)
    return alle


def uebersetze_datei(pfad: Path, speicher_datei: dict[str, str], nur_pruefen: bool,
                     ohne_modell: bool = False) -> str:
    rel = pfad.relative_to(PROJEKT)
    ziel = PROJEKT / "EN" / en_pfad(rel)
    zeilen = pfad.read_text(encoding="utf-8").splitlines()
    if not ist_deutsche_datei("\n".join(zeilen)):
        return f"– {rel}: kein deutscher Text"
    stellen = stelle_stuecke(zeilen, pfad.suffix, speicher_datei)
    if not stellen:
        return f"– {rel}: kein deutscher Text"

    stuecke = [zeilen[nr][von:bis] for nr, von, bis, _ in stellen]
    fehlend = [s for s in stuecke
               if cache_schluessel(s) not in speicher_datei
               and cache_schluessel(s.strip()) not in speicher_datei]
    if fehlend and ohne_modell and not nur_pruefen:
        return f"◐ {rel}: {len(fehlend)} von {len(stellen)} Stellen fehlen noch"
    if fehlend and not nur_pruefen:
        neue: list[str] = []
        for anfang in range(0, len(fehlend), STAPEL):
            portion = fehlend[anfang:anfang + STAPEL]
            try:
                neue += uebersetze_stuecke(portion, f"{rel}")
            except Exception:                           # noqa: BLE001
                try:
                    neue += uebersetze_einzeln(portion, f"{rel}")
                except Exception as fehler:             # noqa: BLE001
                    return f"✗ {rel}: {fehler}"
        for alt, neu in zip(fehlend, neue):
            speicher_datei[cache_schluessel(alt)] = neu

    uebersetzt = [uebersetzung(s, speicher_datei) for s in stuecke]

    # Zwischenspeicher kann alte, fehlerhafte Stücke enthalten: prüfen und neu holen.
    kaputt = [s for s, u in zip(stuecke, uebersetzt) if "\n" in u or not u.strip()]
    if kaputt and ohne_modell and not nur_pruefen:
        # Ohne Modell nur verwerfen — die Stelle bleibt deutsch, das ist sicher.
        for alt in kaputt:
            speicher_datei.pop(cache_schluessel(alt), None)
        uebersetzt = [uebersetzung(s, speicher_datei) for s in stuecke]
    if kaputt and not nur_pruefen and not ohne_modell:
        for alt in kaputt:
            speicher_datei.pop(cache_schluessel(alt), None)
        neue = []
        for anfang in range(0, len(kaputt), STAPEL):
            portion = kaputt[anfang:anfang + STAPEL]
            try:
                neue += uebersetze_stuecke(portion, rel)
            except Exception:                           # noqa: BLE001
                neue += uebersetze_einzeln(portion, rel)
        for alt, neu in zip(kaputt, neue):
            speicher_datei[cache_schluessel(alt)] = neu
        uebersetzt = [uebersetzung(s, speicher_datei) for s in stuecke]

    # Platzhalter müssen erhalten bleiben. Alte Speichereinträge können sie
    # verändert haben → Eintrag verwerfen und (mit Schutz) erneut übersetzen.
    kaputt_p = [s for s, u in zip(stuecke, uebersetzt)
                if platzhalter(s) and platzhalter(s) != platzhalter(u)]
    if kaputt_p and ohne_modell and not nur_pruefen:
        for alt in kaputt_p:
            speicher_datei.pop(cache_schluessel(alt), None)
        uebersetzt = [uebersetzung(s, speicher_datei) for s in stuecke]
    if kaputt_p and not nur_pruefen and not ohne_modell:
        for alt in kaputt_p:
            speicher_datei.pop(cache_schluessel(alt), None)
        for anfang in range(0, len(kaputt_p), STAPEL):
            portion = kaputt_p[anfang:anfang + STAPEL]
            try:
                neue = uebersetze_stuecke(portion, rel)
            except Exception:                           # noqa: BLE001
                try:
                    neue = uebersetze_einzeln(portion, rel)
                except Exception as fehler:             # noqa: BLE001
                    ziel.unlink(missing_ok=True)
                    return f"✗ {rel}: {fehler}"
            for alt, neu in zip(portion, neue):
                speicher_datei[cache_schluessel(alt)] = neu
        uebersetzt = [uebersetzung(s, speicher_datei) for s in stuecke]
    for alt, neu in zip(stuecke, uebersetzt):
        if platzhalter(alt) and platzhalter(alt) != platzhalter(neu):
            ziel.unlink(missing_ok=True)
            return f"✗ {rel}: Platzhalter verändert in {alt[:40]!r}"

    def geruest_gleich(quelle: str, ergebnis: str) -> bool:
        if pfad.suffix == ".py":
            vorher, nachher = geruest_python(quelle), geruest_python(ergebnis)
            return vorher is not None and nachher is not None and vorher == nachher
        return geruest_schlicht(quelle, pfad.suffix) == geruest_schlicht(ergebnis, pfad.suffix)

    def platzhalter_gleich(uebersetzt_liste: list[str]) -> bool:
        for alt, neu in zip(stuecke, uebersetzt_liste):
            if platzhalter(alt) and platzhalter(alt) != platzhalter(neu):
                return False
        return True

    neu_zeilen = setze_zusammen(zeilen, stellen, uebersetzt, pfad.suffix)
    quelle_neu = "\n".join(neu_zeilen) + "\n"

    # Beide Seiten MIT abschließendem Zeilenumbruch vergleichen — sonst
    # unterscheidet sich das Token NEWLINE und jede .py-Datei fällt durch.
    if (not geruest_gleich("\n".join(zeilen) + "\n", quelle_neu)
            and not nur_pruefen and not ohne_modell):
        # Alte Speichereinträge können den Quelltext zerlegt haben
        # (Anführungszeichen, geschweifte Klammern) → verwerfen, einmal frisch
        # übersetzen und erneut prüfen.
        for alt in stuecke:
            speicher_datei.pop(cache_schluessel(alt), None)
        frische: list[str] = []
        try:
            for anfang in range(0, len(stuecke), STAPEL):
                frische += uebersetze_stuecke(stuecke[anfang:anfang + STAPEL], rel)
        except Exception:                               # noqa: BLE001
            try:
                frische = uebersetze_einzeln(stuecke, rel)
            except Exception as fehler:                 # noqa: BLE001
                ziel.unlink(missing_ok=True)
                return f"✗ {rel}: {fehler}"
        if len(frische) != len(stuecke) or not platzhalter_gleich(frische):
            ziel.unlink(missing_ok=True)
            return f"✗ {rel}: Platzhalter verändert (frische Übersetzung)"
        for alt, neu in zip(stuecke, frische):
            speicher_datei[cache_schluessel(alt)] = neu
        uebersetzt = frische
        neu_zeilen = setze_zusammen(zeilen, stellen, uebersetzt, pfad.suffix)
        quelle_neu = "\n".join(neu_zeilen) + "\n"

    if not geruest_gleich("\n".join(zeilen) + "\n", quelle_neu):
        ziel.unlink(missing_ok=True)
        return f"✗ {rel}: Codegerüst hat sich verändert"

    if nur_pruefen:
        return f"· {rel}: {len(stellen)} Stellen (Prüflauf)"

    ziel.parent.mkdir(parents=True, exist_ok=True)
    endtext = quelle_neu
    for muster, wert in rohtausch():
        endtext = muster.sub(lambda _m: wert, endtext)
    ziel.write_text(endtext, encoding="utf-8")
    ok, meldung = syntax_okatei(ziel)
    if not ok:
        ziel.unlink()
        return f"✗ {rel}: Syntaxfehler nach dem Übersetzen — {meldung}"
    return f"✓ {rel}: {len(stellen)} Stellen übersetzt"


def main() -> int:
    zerleger = argparse.ArgumentParser(description="Code-Texte ins Englische übersetzen")
    zerleger.add_argument("dateien", nargs="*", type=Path)
    zerleger.add_argument("--alle", action="store_true")
    zerleger.add_argument("--pruefen", action="store_true")
    zerleger.add_argument("--ohne-modell", action="store_true",
                          help="Nur aus dem Zwischenspeicher übersetzen, kein Modellaufruf")
    args = zerleger.parse_args()

    ziele = dateien(PROJEKT) if args.alle else [p.resolve() for p in args.dateien]
    ziele.sort(key=lambda p: p.stat().st_size)   # kleine zuerst
    if not ziele:
        print(__doc__)
        return 2

    speicher_datei = speicher()
    gut = schlecht = offen = 0
    for p in ziele:
        ergebnis = uebersetze_datei(p, speicher_datei, args.pruefen, args.ohne_modell)
        print(ergebnis, flush=True)
        if ergebnis.startswith("✗"):
            schlecht += 1
        elif ergebnis.startswith("◐"):
            offen += 1
        else:
            gut += 1
        if not args.pruefen:
            SPEICHER.write_text(json.dumps(speicher_datei, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    print(f"\n{gut} in Ordnung, {schlecht} mit Fehlern, {offen} offen · "
          f"Speicher: {len(speicher_datei)} Stücke")
    if NICHT_UEBERSETZT:
        print(f"\n{len(NICHT_UEBERSETZT)} Stellen blieben unverändert (Modell lieferte nichts):")
        for stelle in NICHT_UEBERSETZT[:25]:
            print(f"  · {stelle[:90]!r}")
    return 1 if schlecht else 0


if __name__ == "__main__":
    sys.exit(main())
