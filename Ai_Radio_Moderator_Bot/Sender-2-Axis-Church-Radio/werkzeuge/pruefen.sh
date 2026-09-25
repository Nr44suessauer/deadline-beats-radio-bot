#!/usr/bin/env bash
# Prueft die gebauten Ablaeufe der DDD-Webseite-Fassung (ein zweisprachiger Bot):
#  1) Anordnung (Rahmen, Notizen, Flaeche) mit dem Werkzeug der Nachbau-Anleitung
#  2) Code-Knoten (JavaScript-Syntax)
#  3) Vertraege: Kennungen, EIN Sender (2), EIN Dienst (8882), EIN Testeingang,
#     Sprache reist mit (de/en), deutsche UND englische Texte vorhanden
set -euo pipefail
HIER="$(cd "$(dirname "$0")" && pwd)"
# Pruefwerkzeuge des Hauptbot-Ordners (im Git-Zweig unter demselben Pfad; im
# veroeffentlichten Paket liegen sie unter werkzeuge/pruefwerkzeuge/).
NACHBAU=""
for K in "$HIER/../../Sender-1-Deadline-Beats/werkzeuge" "$HIER/pruefwerkzeuge" "$HIER/../../werkzeuge"; do
  if [ -f "$K/anordnung-pruefen.py" ]; then NACHBAU="$K"; break; fi
done
[ -n "$NACHBAU" ] || { echo "Pruefwerkzeuge nicht gefunden (anordnung-pruefen.py)"; exit 1; }
DATEIEN=(/tmp/ddd-webseite-konfiguration.json /tmp/ddd-webseite-werkzeuge.json /tmp/ddd-webseite-agent.json)

for D in "${DATEIEN[@]}"; do
  [ -f "$D" ] || { echo "Datei fehlt: $D - erst bauen (bauen.sh)"; exit 1; }
done

echo "== 1) Anordnung =="
python3 "$NACHBAU/anordnung-pruefen.py" "${DATEIEN[@]}" | tail -1
echo "== 2) Code-Knoten =="
python3 "$NACHBAU/code-pruefen.py" "${DATEIEN[@]}" | tail -1

echo "== 3) Vertraege =="
python3 - "${DATEIEN[@]}" <<'PY'
import json
import sys

pfade = sys.argv[1:]
texte = {}
for f in pfade:
    d = json.load(open(f, encoding="utf-8"))
    w = d[0] if isinstance(d, list) else d
    texte[w["id"]] = json.dumps(d, ensure_ascii=False)

alles = "\n".join(texte.values())
agent = texte.get("DDD-Webseite-Bot", "")
werkzeuge = texte.get("DDD-Webseite-Radio", "")
fehler = 0


def muss(text, name, wie_oft=1, datei=None):
    global fehler
    n = (datei if datei is not None else text).count(name)
    gut = n >= wie_oft
    print(("  ok   " if gut else "  FEHL  ") + f"{n}x {name}")
    if not gut:
        fehler += 1


def darf_nicht(text, name, datei=None):
    global fehler
    n = (datei if datei is not None else text).count(name)
    gut = n == 0
    print(("  ok   " if gut else "  FEHL  ") + f"{n}x {name} (darf nicht)")
    if not gut:
        fehler += 1


print(" -- Kennungen: vier Ablaeufe, keine Sprach-Endung --")
for kennung in ("DDD-Webseite-Konfiguration", "DDD-Webseite-Radio",
                "DDD-Webseite-Meldungen", "DDD-Webseite-Bot"):
    muss(alles, '"id": "' + kennung + '"')
for rest in ('-DE"', '-EN"', "Configuration-EN", "Messages-EN"):
    darf_nicht(alles, rest)
muss(alles, "dddWebseiteTelegram", 1)
darf_nicht(alles, "dddWebseiteTelegramDE")
darf_nicht(alles, "dddWebseiteTelegramEN")

print(" -- ein Sender, ein Dienst, ein Testeingang --")
darf_nicht(alles, "station/1")
darf_nicht(alles, "8883")
darf_nicht(alles, "/news/pending")
darf_nicht(alles, "X-News-Key")
muss(alles, "192.168.178.53:8882")
muss(alles, "ddd-webseite-test", 1)
darf_nicht(alles, "ddd-webseite-test-de")
muss(agent, "DDD-Webseite-Konfiguration")

print(" -- Demo-Rechte: nur zuhoeren, springen, Wuensche --")
darf_nicht(alles, "Werkzeug Azura")
darf_nicht(alles, "azura_")
darf_nicht(alles, "files/batch")
darf_nicht(alles, "interrupting_requests")
darf_nicht(alles, "/debug/")
muss(werkzeuge, "'/request/'", 1)
muss(werkzeuge, "Wunsch anfordern", 4)
muss(werkzeuge, "Playlist holen", 4)
muss(werkzeuge, "demo.playlist", 1)
muss(werkzeuge, "ansage_max", 2)
muss(agent, "'skip'", 3)
darf_nicht(agent, "'lautstaerke'")
darf_nicht(agent, "'restart'")
darf_nicht(agent, "'pause'")

print(" -- die Sprache reist mit (de/en) --")
muss(agent, "sprache_raten", 2)
muss(agent, "for (const q of ['Zugang'", 8)
muss(agent, '"sprache"', 5)
muss(agent, "sprache_raten(textRoh)", 1)
muss(agent, "letzteSprache", 2)
muss(werkzeuge, '"name": "sprache"', 1)
muss(werkzeuge, "eingang.sprache", 4)

print(" -- deutsche Texte unveraendert vorhanden --")
muss(alles, "ist als Wunsch eingeplant", 2)
muss(alles, "Tippe den passenden Knopf oder antworte mit der Nummer", 1)
muss(alles, "Im Postfach liegt nichts Offenes", 1)
muss(alles, "naechster Titel laeuft an", 0)   # alte Schreibweise weg
muss(alles, "Naechster Titel laeuft an", 1)

print(" -- englische Texte vorhanden --")
muss(alles, "is queued as a request", 2)
muss(alles, "NO MATCHES", 1)
muss(alles, "Now playing: ", 1)
muss(alles, "Tap the matching button or answer with the number", 1)
muss(alles, "I did not understand that", 2)
muss(alles, "will play soon", 2)

print(" -- Sprachanweisungen der Modelle --")
muss(alles, "DEUTSCH ODER ENGLISCH", 1)
muss(alles, "Antworte in der Sprache", 1)
muss(alles, "Sprache des Betreibers")
muss(alles, "Axis Church Radio")
muss(alles, "'ansage'", 1)
darf_nicht(alles, "Deadline Beats")

sys.exit(1 if fehler else 0)
PY
echo "Pruefung fertig."
