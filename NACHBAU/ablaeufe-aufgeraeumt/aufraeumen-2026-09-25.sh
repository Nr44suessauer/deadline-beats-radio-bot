#!/bin/bash
# Raeumt die nicht mehr aktuellen, senderbezogenen Ablaeufe aus n8n (korrigierte Fassung).
# 1) jeden Ablauf einzeln exportieren und die Kennung in der Datei PRUEFEN
# 2) Zeilen aus der n8n-Datenbank entfernen (Kennungen als einfache Argumente)
# 3) n8n neu starten und den Bestand pruefen
set -euo pipefail
CFG=~/.ssh/config
ZIEL=<dokuordner>/NACHBAU/ablaeufe-aufgeraeumt
mkdir -p "$ZIEL"

PAARE=(
  "RadioTelegramBot|RadioTelegramBot-Wunschbot.json"
  "RadioTelegramBot-Archiv-2026-09-19|RadioTelegramBot-Archiv-2026-09-19.json"
  "iDfPikpAIqTO9XQ2|RadioTelegramBot-copy-v1.json"
  "bjFSfXGqpLg7AAXw|Radio-AI-Moderator.json"
  "da7f06de-0bcf-4fbe-8c8d-ad8927d3d509|RadioAgent-vor-dem-Umbau.json"
  "7Vv3NSFsS7OZaBSd|RadioAgent-Zwischenstand-V2.json"
  "jt2IC4TVPTF1KDLp|RadioAgent-copy.json"
  "zxBICXCfUaMGhNmT|RadioAgent-copy2-V2.json"
  "RadioWerkzeugSuche|Werkzeug-Titel-suchen.json"
  "RadioWerkzeugSofort|Werkzeug-Sofort-spielen.json"
  "RadioWerkzeugDanach|Werkzeug-Danach-spielen.json"
  "RadioWerkzeugStatus|Werkzeug-Was-laeuft.json"
  "RadioWerkzeugRichtung|Werkzeug-Richtung-suchen.json"
)

echo "--- sichern und pruefen"
IDS=""
for paar in "${PAARE[@]}"; do
  id="${paar%%|*}"; name="${paar##*|}"
  ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc 'docker exec -u node n8n n8n export:workflow --id=$id --output=/tmp/wf-$id.json >/dev/null 2>&1; docker exec n8n cat /tmp/wf-$id.json'" > "$ZIEL/$name"
  chmod 600 "$ZIEL/$name"
  python3 - "$ZIEL/$name" "$id" <<'PY'
import json, sys
pfad, erwartet = sys.argv[1], sys.argv[2]
d = json.load(open(pfad, encoding="utf-8"))
w = d[0] if isinstance(d, list) else d
gefunden = w.get("id", "")
if gefunden != erwartet:
    raise SystemExit(f"FEHLER: {pfad} enthaelt {gefunden}, erwartet {erwartet}")
print(f"  ok  {erwartet:45s} {w.get('name','?'):45s} {len(w.get('nodes',[]))} Knoten")
PY
  IDS="$IDS$id "
done
echo "--- entfernen"
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  docker cp /tmp/n8n-weg.js n8n:/tmp/ >/dev/null
  docker exec -u node n8n node /tmp/n8n-weg.js $IDS
'"
echo "--- n8n neu starten"
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  docker restart n8n >/dev/null
  for i in \$(seq 1 40); do
    C=\$(curl -s -o /dev/null -w \"%{http_code}\" http://127.0.0.1:5678/healthz)
    [ \"\$C\" = \"200\" ] && break
    sleep 3
  done
  echo \"  Gesundheit: \$C\"
'"
echo "Fertig."
