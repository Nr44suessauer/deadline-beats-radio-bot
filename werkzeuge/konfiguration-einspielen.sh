#!/usr/bin/env bash
# Spielt die Fassung mit zentraler Konfiguration ein: zuerst den neuen Ablauf
# "Konfiguration", dann die drei Werkzeug-Ablaeufe, zuletzt den Bot.
#
# Aufruf:  bash konfiguration-einspielen.sh
# Vorher:  python3 werkzeuge/agent-wf-bauen.py   (schreibt die drei Dateien)
#           + die Zugangswerte aus der Umgebung (TG_TOKEN, AZ_KEY, MELDUNG_SCHLUESSEL)
#
# Es wird NICHTS geloescht: vorhandene Ablaeufe mit denselben Kennungen werden
# ersetzt, alles andere bleibt. Die alte Fassung liegt als Sicherung bereit.
# Zum Schluss liegen die fuenf Ablaeufe im Ordner "Sender 1: Deadline Beats"
# (n8n-ordner-setzen.sh - der Import uebernimmt keine Ordner-Zuordnung).
set -euo pipefail
cd "$(dirname "$0")"

CFG=~/.ssh/config
PROJEKT=DEINE-N8N-PROJEKT-KENNUNG
KONFIG=/tmp/radio-konfiguration.json
WERKZEUGE=/tmp/radio-werkzeuge.json
BOT=/tmp/radio-agent.json
ABLAEUFE="Konfiguration RadioWerkzeug AzuraWerkzeug MeldungenWerkzeug RadioAgentBot"

for D in "$KONFIG" "$WERKZEUGE" "$BOT"; do
  [ -f "$D" ] || { echo "Datei fehlt: $D (erst den Erzeuger laufen lassen)"; exit 1; }
  if grep -q "<GEHEIM>" "$D"; then
    echo "ABBRUCH: $D enthaelt Maskenmerker <GEHEIM>."
    exit 1
  fi
done

echo "--- Bau pruefen"
python3 - "$KONFIG" "$WERKZEUGE" "$BOT" <<'PY'
import json, sys
for pfad in sys.argv[1:]:
    d = json.load(open(pfad, encoding="utf-8"))
    for w in (d if isinstance(d, list) else [d]):
        namen = [k["name"] for k in w["nodes"]]
        hat = " ja" if "Konfiguration" in namen else "nein"
        print(f"  {w['name']:32s} {len(namen):3d} Knoten   Konfiguration: {hat}")
PY

echo "--- Dateien in den Container"
for PAAR in "$KONFIG:/tmp/wf-konfig.json" "$WERKZEUGE:/tmp/wf-werkzeuge.json" "$BOT:/tmp/wf-bot.json"; do
  QUELLE=${PAAR%%:*}
  ZIEL=${PAAR##*:}
  cat "$QUELLE" | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > $ZIEL'"
done

ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  set -e
  for F in wf-konfig.json wf-werkzeuge.json wf-bot.json; do docker cp /tmp/\$F n8n:/tmp/ >/dev/null; done
  echo \"--- Konfiguration importieren (zuerst)\"
  if ! docker exec -u node n8n n8n import:workflow --input=/tmp/wf-konfig.json --projectId=$PROJEKT > /tmp/i1.log 2>&1; then
    echo \"ABBRUCH bei der Konfiguration:\"; cat /tmp/i1.log; exit 1
  fi
  tail -1 /tmp/i1.log
  echo \"--- Werkzeuge importieren\"
  if ! docker exec -u node n8n n8n import:workflow --input=/tmp/wf-werkzeuge.json --projectId=$PROJEKT > /tmp/i2.log 2>&1; then
    echo \"ABBRUCH bei den Werkzeugen:\"; cat /tmp/i2.log; exit 1
  fi
  tail -1 /tmp/i2.log
  echo \"--- Bot importieren\"
  if ! docker exec -u node n8n n8n import:workflow --input=/tmp/wf-bot.json --projectId=$PROJEKT > /tmp/i3.log 2>&1; then
    echo \"ABBRUCH beim Bot:\"; cat /tmp/i3.log; exit 1
  fi
  tail -1 /tmp/i3.log
  echo \"--- einschalten\"
  for W in $ABLAEUFE; do
    docker exec -u node n8n n8n update:workflow --id=\$W --active=true 2>&1 | tail -1
  done
  echo \"--- Zustand\"
  docker exec -u node n8n n8n list:workflow 2>/dev/null | grep -E \"Konfiguration|RadioAgentBot|Werkzeug\" || true
'"

echo "--- Ordner zuordnen"
bash "$(dirname "$0")/n8n-ordner-setzen.sh"
