#!/usr/bin/env bash
# Holt die laufende Fassung, baut neu, patcht die Aenderungen hinein und legt das
# Ergebnis nach /tmp/radio-agent-neu.json. Es wird NICHTS eingespielt.
#
# Aufruf:  bash agent-patchen.sh ["--neu A,B --inhalt C --umbenennen 'X=Y'"]
# Ohne Angaben werden alle im Neubau zusaetzlichen Knoten uebernommen.
#
# Vorher sichern:  bash fassung-sichern.sh radio-vX-<datum>-<kurzname>
# Danach einspielen: bash agent-einspielen-nur.sh /tmp/radio-agent-neu.json
set -euo pipefail
cd "$(dirname "$0")"

CFG=~/.ssh/config
LAUFEND=/tmp/radio-agent-laufend.json
ZIEL=/tmp/radio-agent-neu.json
RADIO=<dokuordner>

echo "--- laufende Fassung aus n8n holen"
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  docker exec -u node n8n n8n export:workflow --id=RadioAgentBot --output=/tmp/laufend.json >/dev/null 2>&1
  docker exec n8n cat /tmp/laufend.json'" > "$LAUFEND"
python3 -c "
import json
d = json.load(open('$LAUFEND', encoding='utf-8'))
w = d[0] if isinstance(d, list) else d
print('  Knoten:', len(w['nodes']), '| Name:', w.get('name'))
"

# Zugangswerte aus der laufenden Fassung, damit der Neubau dieselben traegt.
# Seit dem Umbau auf "Konfiguration - alle Werte" (22.09.2026) stehen Token und
# Schnittstellenschluessel NICHT mehr im Agenten, sondern im Konfigurations-Ablauf
# -> beide Dateien absuchen.
KONFIG_LAUFEND=/tmp/radio-konfig-laufend.json
export KONFIG_LAUFEND
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  docker exec -u node n8n n8n export:workflow --id=Konfiguration --output=/tmp/konfig-laufend.json >/dev/null 2>&1
  docker exec n8n cat /tmp/konfig-laufend.json'" > "$KONFIG_LAUFEND"
export TG_TOKEN=$(python3 -c "
import re
t = open('$LAUFEND', encoding='utf-8').read() + open('$KONFIG_LAUFEND', encoding='utf-8').read()
m = re.search(r'[0-9]{6,12}:[A-Za-z0-9_-]{33,}', t)
print(m.group(0) if m else '')")
export AZ_KEY=$(python3 -c "
import re
t = open('$LAUFEND', encoding='utf-8').read() + open('$KONFIG_LAUFEND', encoding='utf-8').read()
m = re.search(r'[0-9a-f]{16}:[0-9a-f]{32}', t)
print(m.group(0) if m else '')")
# Der Postfach-Schluessel liegt seit dem Aufraeumen in NACHBAU/zugangsdaten/;
# der alte Ort im Projektordner wird weiter unterstuetzt.
MELDUNG_DATEI="$RADIO/meldung-schluessel.txt"
[ -f "$MELDUNG_DATEI" ] || MELDUNG_DATEI="$RADIO/NACHBAU/zugangsdaten/meldung-schluessel.txt"
export MELDUNG_SCHLUESSEL=$(cat "$MELDUNG_DATEI" 2>/dev/null || echo "")
[ ${#MELDUNG_SCHLUESSEL} -gt 10 ] || { echo "FEHLER: meldung-schluessel.txt fehlt (in $RADIO oder NACHBAU/zugangsdaten/)"; exit 1; }
[ ${#TG_TOKEN} -gt 30 ] || { echo "FEHLER: Telegram-Kennung nicht gefunden (Agent + Konfiguration geprueft)"; exit 1; }
[ ${#AZ_KEY} -gt 40 ] || { echo "FEHLER: Schnittstellenschluessel nicht gefunden (Agent + Konfiguration geprueft)"; exit 1; }
echo "  Kennungen geladen (Telegram ${#TG_TOKEN}, Schnittstelle ${#AZ_KEY}, Meldungen ${#MELDUNG_SCHLUESSEL} Zeichen)"

echo "--- Neubau erzeugen"
python3 agent-wf-bauen.py

echo "--- deutsche Beschriftung (Umlaute statt ae/oe/ue)"
python3 deutsch-texte.py --anwenden --umbenennen-datei /tmp/umbenennen.txt \
  /tmp/radio-agent.json /tmp/radio-werkzeuge.json /tmp/radio-konfiguration.json

# Achtung: die Importdateien NACH der Textueberarbeitung bauen - sonst bekommen
# die Werkzeug-Ablaeufe die Umlaute nicht (am 2026-09-24 passiert: Agent ja,
# die drei Werkzeuge kamen weiter mit "Ausfuehren?" auf den Server).
python3 import-agent-vorbereiten.py >/dev/null

echo "--- patchen"
UMB=$(cat /tmp/umbenennen.txt 2>/dev/null || true)
python3 agent-patchen.py "$LAUFEND" /tmp/radio-agent.json "$ZIEL" --umbenennen "$UMB" "$@"

echo
echo "Fertig. Einspielen mit:  bash agent-einspielen-nur.sh $ZIEL"
