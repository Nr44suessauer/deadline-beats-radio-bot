#!/usr/bin/env bash
# Erzeugt ANORDNUNG.md: eine Uebersicht der Zeichenflaeche aller vier Abläufe.
# Holt die laufenden Fassungen aus n8n, prueft sie und schreibt die Tabelle.
#
# Aufruf:  bash anordnung-doku.sh
set -euo pipefail
cd "$(dirname "$0")"

CFG=~/.ssh/config
TMP=/tmp/anordnung
mkdir -p "$TMP"

holen() {   # holen <Workflow-Id> <Zieldatei>
  ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
    docker exec -u node n8n n8n export:workflow --id=$1 --output=/tmp/w.json >/dev/null 2>&1
    docker exec n8n cat /tmp/w.json'" > "$2"
}

echo "--- laufende Abläufe holen"
holen RadioAgentBot "$TMP/agent.json"
holen RadioWerkzeug "$TMP/werkzeug-radio.json"
holen AzuraWerkzeug "$TMP/werkzeug-azura.json"
holen MeldungenWerkzeug "$TMP/werkzeug-meldungen.json"
# Archiv der ersten Fassung: nicht im Bauwerkzeug, aber mit Rahmen (archiv-rahmen.py)
holen bjFSfXGqpLg7AAXw "$TMP/archiv-moderator.json"

echo "--- Zeichenflaeche pruefen"
python3 anordnung-pruefen.py "$TMP/agent.json" "$TMP/werkzeug-radio.json" \
  "$TMP/werkzeug-azura.json" "$TMP/werkzeug-meldungen.json" "$TMP/archiv-moderator.json"

echo "--- Uebersicht schreiben"
{
  cat <<'KOPF'
# Zeichenfläche der Abläufe (erzeugt)

Diese Datei wird **erzeugt**, nicht von Hand gepflegt: `bash anordnung-doku.sh`
holt die laufenden Abläufe aus n8n, prüft die Zeichenfläche und schreibt die
Knotenlisten. Sie zeigt, was auf der Fläche steht — welcher Rahmen welche Aufgabe
hat und was unter jedem Knoten als Notiz steht.

Warum das wichtig ist: der Rahmen wird **aus den Positionen gerechnet**
(`werkzeuge/agent-wf-bauen.py`, Tabellen `BEREICHE`). Liegt ein Knoten außerhalb
seines Rahmens oder überlappen sich zwei Rahmen, meldet `anordnung-pruefen.py`
einen Befund. Ziel ist **0 Befunde**.

| Prüfung | Bedeutung |
| --- | --- |
| Knoten ohne Rahmen | er landet irgendwo ohne Erklärung |
| Knoten in zwei Rahmen | die Bereiche sind falsch geschnitten |
| ragt aus dem Rahmen heraus | die Fläche ist gepflegt-daneben |
| Rahmen überlagern sich | die Bereiche liegen übereinander |
| Knoten ohne Notiz | es fehlt die Beschriftung (muss jeder haben) |

Stand: 2026-09-24 (Fassung 19). Neu erzeugen: `bash anordnung-doku.sh`.

KOPF
  python3 anordnung-uebersicht.py "$TMP/agent.json" "$TMP/werkzeug-radio.json" \
    "$TMP/werkzeug-azura.json" "$TMP/werkzeug-meldungen.json" \
    "$TMP/archiv-moderator.json"
} > ../ANHANG/ANORDNUNG.md

echo "geschrieben: ANHANG/ANORDNUNG.md"
wc -l ANORDNUNG.md
