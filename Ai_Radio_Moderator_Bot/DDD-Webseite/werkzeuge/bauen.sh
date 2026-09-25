#!/bin/bash
# Baut die Ablaeufe der DDD-Webseite-Fassung (ein zweisprachiger Bot, Sender 2).
#
# Zugangswerte kommen aus ../zugangsdaten/ (keine Werte im Skript selbst):
#   api_key.txt                 AzuraCast-Schluessel DIESER Fassung
#   meldung-schluessel.txt      Postfach-Schluessel der Dienst-Instanz ddd-radio
#   test-schluessel.txt         Schluessel des Testeingangs
#   erlaubte-chats.txt          Betreiber-Chat-ID(s)
#   telegram-bot-token.txt      Telegram-Token (Platzhalter, bis der Bot angelegt ist)
#   demo-playlist.txt           Name der Demo-Wiedergabeliste (Musik nur daraus;
#                               fehlt die Datei oder ist sie leer, sind Wuensche gesperrt)
#
# Aufruf:  bash bauen.sh          (TRIGGER_AUS=0 laesst die Telegram-/Zeitplan-Ausloeser an)
#
# Ergebnis (vier Ablaeufe, deutsche UND englische Nachrichten in EINEM Chat):
#   /tmp/ddd-webseite-konfiguration.json    DDD-Webseite-Konfiguration
#   /tmp/ddd-webseite-werkzeuge.json        DDD-Webseite-Radio, -Meldungen
#   /tmp/ddd-webseite-agent.json            DDD-Webseite-Bot
set -e
HIER="$(cd "$(dirname "$0")" && pwd)"
ZUG="$HIER/../zugangsdaten"

export AZ_KEY="$(cat "$ZUG/api_key.txt")"
export MELDUNG_SCHLUESSEL="$(cat "$ZUG/meldung-schluessel.txt")"
export TEST_SCHLUESSEL="$(cat "$ZUG/test-schluessel.txt")"
export ERLAUBTE="$(tr '\n' ',' < "$ZUG/erlaubte-chats.txt")"   # mehrzeilige Datei -> Kommaliste
export TG_TOKEN="$(cat "$ZUG/telegram-bot-token.txt")"
export DEMO_PLAYLIST="$(cat "$ZUG/demo-playlist.txt" 2>/dev/null || true)"   # leer = Wuensche gesperrt
export DIENST_URL="${DIENST_URL:-http://192.168.178.53:8882}"
export TRIGGER_AUS="${TRIGGER_AUS:-1}"

python3 "$HIER/agent-wf-bauen-ddd.py"

# Die Betreiberliste muss ZEICHENKETTEN enthalten: der Bot vergleicht sie mit
# der Chat-ID aus der Nachricht (String). Der Erzeuger schreibt Zahlen.
python3 - <<'PY'
import json
pfad = "/tmp/ddd-webseite-agent.json"
d = json.load(open(pfad, encoding="utf-8"))
w = d[0] if isinstance(d, list) else d
glob = (w.setdefault("staticData", {}) or {}).setdefault("global", {})
glob["erlaubte"] = [str(x) for x in (glob.get("erlaubte") or [])]
json.dump(d, open(pfad, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("erlaubte (als Text):", glob["erlaubte"])
PY
echo "Fertig: /tmp/ddd-webseite-konfiguration.json, -werkzeuge.json, -agent.json"
