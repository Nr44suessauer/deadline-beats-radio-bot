#!/usr/bin/env python3
"""Baut die veröffentlichungsfähige Fassung (DocOfficial) der DDD-Webseite-Ausgabe.

Kopiert die Ausgabe (englische Doku, Dienst, Werkzeuge, Wert-Vorlagen) und
ersetzt alle echten Zugangsdaten durch Platzhalter (YOUR-…). Zum Schluss prüft
das Werkzeug selbst, dass kein echter Wert mehr auffindbar ist.

Aufruf:  python3 werkzeuge/veroeffentlichung-bauen.py [--ziel PFAD]
Vorgabe: DocOfficial/ neben dieser Ausgabe.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
from pathlib import Path

QUELLE = Path(__file__).resolve().parent.parent            # DDD-Webseite
ZIEL_STANDARD = QUELLE / "DocOfficial"
ZUG = QUELLE / "zugangsdaten"
GEHEIM_ENV = QUELLE / "dienst" / "geheim.env"
PRUEFTOOLS = QUELLE.parent / "NACHBAU" / "werkzeuge"       # Prüfwerkzeuge des Projekts
LIZENZ = QUELLE.parent / "LICENSE"

PH = {
    "token": "YOUR-TELEGRAM-BOT-TOKEN",
    "chat": "YOUR-CHAT-ID",           # in Beispieldateien durch eine neutrale Nummer ersetzt
    "azura": "YOUR-AZURACAST-API-KEY",
    "streamer": "YOUR-STREAMER-PASSWORD",
    "botstreamer": "YOUR-BOT-STREAMER-PASSWORD",
    "dj": "YOUR-DJ-PASSWORD",
    "inbox": "YOUR-INBOX-KEY",
    "test": "YOUR-TEST-ENTRY-KEY",
    "geheim": "YOUR-SECRET",
    "name": "YOUR NAME",
    "mail": "YOUR-EMAIL",
    "projekt": "YOUR-N8N-PROJECT-ID",
    "ollama": "YOUR-OLLAMA-CREDENTIAL",
    "betreiber": "operator",
}


def werte_sammeln() -> dict[str, str]:
    """Liest die echten Werte ein (nur zum Ersetzen, es wird nichts ausgegeben)."""
    werte: dict[str, str] = {}

    def aus_datei(datei: str, art: str) -> None:
        p = ZUG / datei
        if not p.exists():
            return
        for zeile in p.read_text(encoding="utf-8", errors="replace").splitlines():
            s = zeile.strip()
            if len(s) >= 8:
                werte[s] = art

    aus_datei("api_key.txt", "azura")
    aus_datei("meldung-schluessel.txt", "inbox")
    aus_datei("test-schluessel.txt", "test")
    aus_datei("telegram-bot-token.txt", "token")
    aus_datei("streamer-aqua.txt", "botstreamer")
    aus_datei("streamer-marc.txt", "dj")

    # Chat-Kennungen (reine Zahlen) aus der Betreiberliste
    p = ZUG / "erlaubte-chats.txt"
    if p.exists():
        for nummer in re.findall(r"\d{6,}", p.read_text(encoding="utf-8", errors="replace")):
            werte[nummer] = "chat"

    # geheim.env: Werte sensibler Schlüsselnamen
    if GEHEIM_ENV.exists():
        for zeile in GEHEIM_ENV.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" not in zeile or zeile.strip().startswith("#"):
                continue
            schluessel, _, wert = zeile.partition("=")
            wert = wert.strip()
            if len(wert) < 8:
                continue
            if not re.search(r"PASSWORT|PASSWORD|KEY|TOKEN|SCHLUESSEL|SCHLUES|SECRET", schluessel, re.I):
                continue
            if "AZ_" in schluessel:
                art = "azura"
            elif "LIVE" in schluessel:
                art = "botstreamer"
            elif "MELDUNG" in schluessel:
                art = "inbox"
            else:
                art = "geheim"
            werte[wert] = art
    return werte


def vorlagen_schreiben(ziel: Path) -> list[str]:
    """Schreibt die Wert-Dateien als Platzhalter-Fassung."""
    z = ziel / "zugangsdaten"
    z.mkdir(parents=True, exist_ok=True)
    dateien = {
        "api_key.txt": PH["azura"],
        "meldung-schluessel.txt": PH["inbox"],
        "test-schluessel.txt": PH["test"],
        "erlaubte-chats.txt": PH["chat"],
        "telegram-bot-token.txt": PH["token"],
        "streamer-aqua.txt": PH["botstreamer"],
        "streamer-operator.txt": PH["dj"],
    }
    fertig: list[str] = []
    for name, inhalt in dateien.items():
        p = z / name
        p.write_text(inhalt + "\n", encoding="utf-8")
        fertig.append(str(p.relative_to(ziel)))
    return fertig


def geheim_vorlage(ziel: Path) -> str:
    p = ziel / "dienst" / "geheim.env.vorlage"
    p.write_text(
        "# Dienst ddd-radio - copy this file to geheim.env, fill in your values,\n"
        "# then set the permissions to 600 (chmod 600 geheim.env).\n"
        "\n"
        "AZ_URL=http://YOUR-STATION-HOST\n"
        "AZ_KEY=YOUR-AZURACAST-API-KEY\n"
        "AZ_STATION_ID=2\n"
        "KATALOG_DIR=/daten\n"
        "MELDUNG_SCHLUESSEL=YOUR-INBOX-KEY\n"
        "LIVE_HOST=YOUR-STATION-HOST\n"
        "LIVE_PORT=8015\n"
        "LIVE_MOUNT=/\n"
        "LIVE_USER=YOUR-BOT-STREAMER\n"
        "LIVE_PASSWORD=YOUR-BOT-STREAMER-PASSWORD\n"
        "LIVE_NAME=YOUR-BOT-DISPLAY-NAME\n"
        "TTS_HOCHPASS_HZ=50\n"
        "TTS_KOMPRESSOR_SCHWELLE_DB=-18\n"
        "TTS_KOMPRESSOR_VERHAELTNIS=2.0\n"
        "TTS_ZIEL_RMS_DB=-12.5\n",
        encoding="utf-8")
    return str(p.relative_to(ziel))


def saeubern(ziel: Path, werte: dict[str, str]) -> tuple[int, int]:
    """Ersetzt alle echten Werte und bekannten Geheimnismuster im Text."""
    # Arbeitspfade des Autors -> neutrale Wege
    pfade = [
        (r"/media/discData/docs/projects/proxmox-ssh/config", "$HOME/.ssh/config"),
        (r"/media/discData/docs/projects/proxmox-ssh", "$HOME/.ssh"),
        (r"/media/discData/docs/projects/Ai_Radio_Moderator_Bot/DDD-Webseite",
         "<dokuordner>/DDD-Webseite"),
        (r"/media/discData/docs/projects/Ai_Radio_Moderator_Bot", "<dokuordner>"),
        (r"/media/discData/docs/projects", "<projektordner>"),
    ]
    # Anpassungen, die nur das Paket betreffen (Quelle bleibt unverändert)
    anpassungen = [
        # pruefen.sh holt die Prüfwerkzeuge im Paket aus dem eigenen Ordner
        (r'NACHBAU="\$HIER/\.\./\.\./werkzeuge"', 'NACHBAU="$HIER/pruefwerkzeuge"'),
    ]
    muster = [
        (re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{33,}\b"), "token"),
        (re.compile(r"\b[0-9a-f]{16}:[0-9a-f]{32}\b"), "azura"),
        (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
         None),   # Sonderfall: fester Hinweistext
        (re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"), "geheim"),
        (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "geheim"),
        # Name und Anschrift des Autors
        (re.compile(r"Marc\s+Nauendorf\s*<\s*marc@deadlinedriven\.(?:dev|de)\s*>"), "name"),
        (re.compile(r"\b[A-Za-z0-9._%+-]+@deadlinedriven\.(?:dev|de)\b"), "mail"),
        (re.compile(r"\bMarc\s+Nauendorf\b"), "name"),
        # Kennungen der eigenen Instanz
        (re.compile(r"\brQ6DFC63JlNQbiar\b"), "projekt"),
        (re.compile(r"\bradioOllamaOpenAi\b"), "ollama"),
        (re.compile(r"\bradioOllama01\b"), "ollama"),
        # Vorname des Betreibers (als Beispiel-Benutzerkonto genannt)
        (re.compile(r"\bmarc\b", re.I), "betreiber"),
    ]
    geprueft = 0
    geaendert = 0
    for p in ziel.rglob("*"):
        if not p.is_file():
            continue
        try:
            alt = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue                      # Binärzeug = nicht betroffen
        geprueft += 1
        neu = alt
        for musterchen, ersatz in pfade + anpassungen:
            neu = re.sub(musterchen, ersatz, neu)
        for wert in sorted(werte, key=len, reverse=True):
            if wert not in neu:
                continue
            art = werte[wert]
            ersatz = "123456789" if art == "chat" else PH[art]
            neu = neu.replace(wert, ersatz)
        for rx, art in muster:
            if art is None:
                neu = rx.sub("(placeholder: put your own private key here)", neu)
            else:
                neu = rx.sub(PH[art], neu)
        if neu != alt:
            p.write_text(neu, encoding="utf-8")
            geaendert += 1
    return geprueft, geaendert


def pruefen(ziel: Path, werte: dict[str, str]) -> list[str]:
    """Sucht übersehene echte Werte und Geheimnismuster."""
    befunde: list[str] = []
    muster = [
        re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{33,}\b"),
        re.compile(r"\b[0-9a-f]{16}:[0-9a-f]{32}\b"),
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
        re.compile(r"\bNauendorf\b"),
        re.compile(r"\bmarc\b", re.I),
        re.compile(r"\bdeadlinedriven\.(?:dev|de)\b"),
        re.compile(r"\brQ6DFC63JlNQbiar\b"),
        re.compile(r"\bradioOllama\w*\b"),
        re.compile(r"/media/discData"),
    ]
    for p in ziel.rglob("*"):
        if not p.is_file():
            continue
        try:
            t = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = p.relative_to(ziel)
        for wert in werte:
            if wert in t:
                befunde.append(f"{rel}: echter Wert noch enthalten (Länge {len(wert)})")
        for rx in muster:
            if rx.search(t):
                befunde.append(f"{rel}: Muster gefunden ({rx.pattern[:32]}…)")
    return befunde


def main() -> int:
    zerleger = argparse.ArgumentParser(description="Veröffentlichungsfassung der DDD-Webseite-Ausgabe bauen")
    zerleger.add_argument("--ziel", type=Path, default=ZIEL_STANDARD,
                          help=f"Zielordner (Vorgabe: {ZIEL_STANDARD})")
    args = zerleger.parse_args()
    ziel: Path = args.ziel

    if not ZUG.exists():
        print(f"Bitte aus der Ausgabe heraus starten - {ZUG} fehlt.")
        return 1

    print(f"Quelle: {QUELLE}")
    print(f"Ziel:   {ziel}")

    # 1) Ordner frisch kopieren
    if ziel.exists():
        shutil.rmtree(ziel)

    def nicht_kopieren(pfad: str, namen: list[str]) -> set[str]:
        """Wertdateien, Archive und Baustände bleiben draußen; sie werden unten
        durch Platzhalter-Fassungen ersetzt. Das Werkzeug selbst bleibt draußen
        (es enthält die Ersetzungstabelle)."""
        del pfad
        weg = {"DocOfficial", ".git", "__pycache__", "altfassungen", "ablaeufe-gebaut",
               "zugangsdaten", "ANORDNUNG.md", "geheim.env", "veroeffentlichung-bauen.py",
               ".venv", "daten", "voices"}
        return weg.intersection(namen)

    shutil.copytree(QUELLE, ziel, ignore=nicht_kopieren)
    anzahl = sum(1 for p in ziel.rglob("*") if p.is_file())
    print(f"Kopiert: {anzahl} Dateien")

    # 2) Echte Werte einsammeln
    werte = werte_sammeln()
    print(f"Echte Werte zum Ersetzen: {len(werte)}")

    # 3) Platzhalter-Dateien schreiben
    fertig = vorlagen_schreiben(ziel)
    fertig.append(geheim_vorlage(ziel))
    print("Platzhalter-Dateien neu geschrieben:")
    for f in fertig:
        print(f"   {f}")

    # 3b) Prüfwerkzeuge (Anordnung, Code) mit ins Paket
    pr = ziel / "werkzeuge" / "pruefwerkzeuge"
    pr.mkdir(parents=True, exist_ok=True)
    for name in ("anordnung-pruefen.py", "code-pruefen.py"):
        quelle = PRUEFTOOLS / name
        if quelle.exists():
            shutil.copy2(quelle, pr / name)
    print(f"Prüfwerkzeuge kopiert: {sorted(p.name for p in pr.iterdir())}")

    # 3c) Lizenz mit ins Paket
    if LIZENZ.exists():
        shutil.copy2(LIZENZ, ziel / "LICENSE")
        print("LICENSE kopiert")

    # 4) Alle Texte durchgehen
    geprueft, geaendert = saeubern(ziel, werte)
    print(f"Texte geprüft: {geprueft}, davon mit Platzhaltern versehen: {geaendert}")

    # 5) Hinweis für die Leser schreiben
    hinweis = ziel / "HINWEIS.md"
    hinweis.write_text(
        "# Note about this edition (DocOfficial)\n"
        "\n"
        "This copy is meant for sharing and publishing. It was built on\n"
        f"{dt.date.today().isoformat()} from the working copy (DDD-Webseite edition,\n"
        "one bilingual bot for German and English).\n"
        "\n"
        "## What was replaced\n"
        "\n"
        "All real credentials were replaced by placeholders - in detail:\n"
        "\n"
        "- Telegram bot token and chat IDs\n"
        "- AzuraCast API key, DJ/streamer passwords\n"
        "- mailbox key and test entry key\n"
        "- the n8n project id and instance credential ids\n"
        "- name and e-mail of the author\n"
        "- working paths of the author's machine\n"
        "\n"
        "The placeholders are uppercase, e.g. `YOUR-TELEGRAM-BOT-TOKEN`.\n"
        "Fill in your own values in `zugangsdaten/` and copy\n"
        "`dienst/geheim.env.vorlage` to `dienst/geheim.env`, then follow\n"
        "`NACHBAU/README.md`.\n"
        "\n"
        "## Notes\n"
        "\n"
        "- Network addresses (192.168.x.x) are examples from the author's setup -\n"
        "  replace them with your own.\n"
        "- The documentation of this edition is English; the workflows' node notes\n"
        "  are German working material.\n"
        "- Rebuild this copy: in the working copy run\n"
        "  `python3 werkzeuge/veroeffentlichung-bauen.py`.\n",
        encoding="utf-8")
    print("HINWEIS.md geschrieben")

    # 6) Gegenprobe
    befunde = pruefen(ziel, werte)
    if befunde:
        print("PRUEFUNG FEHLGESCHLAGEN - es sind noch Werte/Muster enthalten:")
        for b in befunde[:30]:
            print("   ", b)
        return 1

    groesse = sum(p.stat().st_size for p in ziel.rglob("*") if p.is_file())
    anzahl = sum(1 for p in ziel.rglob("*") if p.is_file())
    print("Prüfung: sauber - kein echter Wert und kein Geheimnis-Muster mehr gefunden.")
    print(f"Fertig: {ziel} ({anzahl} Dateien, {groesse / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
