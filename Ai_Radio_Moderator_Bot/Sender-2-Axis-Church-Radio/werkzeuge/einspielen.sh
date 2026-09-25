#!/usr/bin/env bash
# Spielt die Ablaeufe der DDD-Webseite-Fassung ein: EIN zweisprachiger Bot
# (deutsche und englische Nachrichten in einem Chat), vier Ablaeufe.
# Voraussetzung: bauen.sh ist gelaufen.
#
# Der Lauf erledigt alles in einem Zug:
#   1. die vier neuen Ablaeufe importieren
#   2. die alten zehn Ablaeufe (Fassungen mit -DE/-EN) aus n8n entfernen und den
#      entfallenen Ablauf "DDD-Webseite-AzuraCast" (Verwaltung, gibt es nicht mehr)
#   3. die vier neuen einschalten und in den Ordner "Sender 2: Axis Church Radio"
#      legen, dann n8n neu starten (Webhooks anmelden)
#   4. Gesundheit, Testeingang, REST-Eingang und Ablaufliste pruefen
#
# Die Telegram- und Zeitplan-Ausloeser sind ABSICHTLICH abgeschaltet
# (TRIGGER_AUS=1 beim Bauen): zuerst den Token eintragen, dann die Knoten
# aktivieren und den Ablauf einmal aus-/einschalten (siehe README).
#
# Der bestehende Bot (RadioAgentBot usw.) wird NICHT angefasst; n8n wird einmal
# neu gestartet, damit die neuen Webhooks greifen.
set -euo pipefail

CFG=/media/discData/docs/projects/proxmox-ssh/config
PROJEKT=rQ6DFC63JlNQbiar
K=/tmp/ddd-webseite-konfiguration.json
W=/tmp/ddd-webseite-werkzeuge.json
A=/tmp/ddd-webseite-agent.json

# Kennungen der neuen Fassung (ohne Sprach-Endung)
NEU="DDD-Webseite-Konfiguration DDD-Webseite-Radio DDD-Webseite-Meldungen DDD-Webseite-Bot"
# Kennungen der alten Fassungen (werden entfernt) plus der entfallene AzuraCast-Ablauf
ALT="DDD-Webseite-AzuraCast DDD-Webseite-Konfiguration-DE DDD-Webseite-Radio-DE DDD-Webseite-AzuraCast-DE DDD-Webseite-Meldungen-DE DDD-Webseite-Bot-DE DDD-Webseite-Configuration-EN DDD-Webseite-Radio-EN DDD-Webseite-AzuraCast-EN DDD-Webseite-Messages-EN DDD-Webseite-Bot-EN"

for D in "$K" "$W" "$A"; do
  [ -f "$D" ] || { echo "Datei fehlt: $D - erst bauen (bauen.sh)"; exit 1; }
  grep -q "<GEHEIM>" "$D" && { echo "ABBRUCH: $D enthaelt Maskenmerker"; exit 1; }
done

# Kleines Hilfsprogramm: entfernt die alten Ablaeufe aus der n8n-Datenbank.
# (n8n hat keinen Loeschbefehl fuer Ablaeufe; die REST-Schnittstelle braucht
# eine Sitzung. Direkt in der SQLite geht es - danach n8n neu starten.)
cat > /tmp/ddd-alt-weg.js <<'JS'
const sqlite3 = require("/usr/local/lib/node_modules/n8n/node_modules/.pnpm/sqlite3@5.1.7/node_modules/sqlite3");
const ids = process.argv.slice(2);
const db = new sqlite3.Database("/home/node/.n8n/database.sqlite");
const frage = ids.map(() => "?").join(",");
db.serialize(() => {
  db.run("delete from workflow_entity where id in (" + frage + ")", ids);
  db.run("delete from shared_workflow where workflowId in (" + frage + ")", ids);
});
db.close(() => {
  db.all("select id from workflow_entity where id like 'DDD-Webseite%'", (e, r) => {
    console.log("  vorhanden: " + (r || []).map((x) => x.id).sort().join(", "));
  });
});
JS

# Kleines Hilfsprogramm: legt den Ordner "Sender 2: Axis Church Radio" an (falls er
# fehlt) und ordnet die vier Ablaeufe zu. `n8n import:workflow` uebernimmt die
# Ordner-Zuordnung NICHT - ohne diesen Schritt liegen die Ablaeufe zuoberst
# ohne Ordner (der private Bot liegt in "Sender 1: Deadline Beats").
cat > /tmp/ddd-ordner.js <<'JS'
const sqlite3 = require("/usr/local/lib/node_modules/n8n/node_modules/.pnpm/sqlite3@5.1.7/node_modules/sqlite3");
const db = new sqlite3.Database("/home/node/.n8n/database.sqlite");
const ORDNER = "RWEPQ3wEjcfpTacL";
const NAME = "Sender 2: Axis Church Radio";
const PROJEKT = "rQ6DFC63JlNQbiar";
const IDS = ["DDD-Webseite-Konfiguration", "DDD-Webseite-Radio",
             "DDD-Webseite-Meldungen", "DDD-Webseite-Bot"];
db.serialize(() => {
  db.run("insert or ignore into folder (id, name, parentFolderId, projectId, createdAt, updatedAt)"
       + " values (?, ?, null, ?, datetime('now'), datetime('now'))", [ORDNER, NAME, PROJEKT]);
  for (const id of IDS) {
    db.run("update workflow_entity set parentFolderId = ? where id = ?", [ORDNER, id]);
  }
});
db.all("select id from workflow_entity where parentFolderId = ? order by id", [ORDNER], (e, r) => {
  if (e) { console.log("FEHLER: " + e.message); } else {
    console.log("  Ordner \"" + NAME + "\": " + (r || []).map((x) => x.id).join(", "));
  }
  db.close();
});
JS

echo "--- uebertragen"
for paar in "$K:wf-ddd-k.json" "$W:wf-ddd-w.json" "$A:wf-ddd-a.json" "/tmp/ddd-alt-weg.js:ddd-alt-weg.js" "/tmp/ddd-ordner.js:ddd-ordner.js"; do
  datei="${paar%%:*}"; name="${paar##*:}"
  cat "$datei" | ssh -F "$CFG" ai-server "pct exec 103 -- bash -c 'cat > /tmp/$name'"
  echo "  $name"
done

echo "--- importieren, aufraeumen, einschalten"
ssh -F "$CFG" ai-server "pct exec 103 -- bash -lc '
  set -e
  for f in wf-ddd-k wf-ddd-w wf-ddd-a ddd-alt-weg ddd-ordner; do docker cp /tmp/\$f.json n8n:/tmp/ 2>/dev/null || docker cp /tmp/\$f.js n8n:/tmp/ >/dev/null; done
  importiere() {
    if ! docker exec -u node n8n n8n import:workflow --input=/tmp/\$1.json --projectId=$PROJEKT > /tmp/imp.log 2>&1; then
      echo \"ABBRUCH bei \$1:\"; cat /tmp/imp.log; exit 1
    fi
    echo \"  \$1: \$(tail -1 /tmp/imp.log)\"
  }
  importiere wf-ddd-k; importiere wf-ddd-w; importiere wf-ddd-a
  echo \"--- alte Fassungen entfernen\"
  docker exec -u node n8n node /tmp/ddd-alt-weg.js $ALT
  echo \"--- einschalten\"
  for W in $NEU; do
    docker exec -u node n8n n8n update:workflow --id=\$W --active=true 2>&1 | tail -1
  done
  echo \"--- Ordner zuordnen\"
  docker exec -u node n8n node /tmp/ddd-ordner.js
  echo \"--- n8n neu starten (Webhooks anmelden)\"
  docker restart n8n >/dev/null
  for i in \$(seq 1 40); do
    C=\$(curl -s -o /dev/null -w \"%{http_code}\" http://127.0.0.1:5678/healthz 2>/dev/null || true)
    [ \"\$C\" = \"200\" ] && break
    sleep 3
  done
  echo \"n8n Gesundheit: \$C\"
  for i in \$(seq 1 40); do
    W1=\$(curl -s -o /dev/null -w \"%{http_code}\" -X POST http://127.0.0.1:5678/webhook/ddd-webseite-test -H \"Content-Type: application/json\" -d \"{}\" 2>/dev/null || true)
    [ \"\$W1\" != \"404\" ] && break
    sleep 3
  done
  echo \"Testeingang /webhook/ddd-webseite-test: \$W1\"
  for i in \$(seq 1 40); do
    W2=\$(curl -s -o /dev/null -w \"%{http_code}\" -X POST http://127.0.0.1:5678/webhook/ddd-webseite-rest -H \"Content-Type: application/json\" -d \"{}\" 2>/dev/null || true)
    [ \"\$W2\" != \"404\" ] && break
    sleep 3
  done
  echo \"REST-Eingang /webhook/ddd-webseite-rest: \$W2\"
  echo \"--- Ablaufliste\"
  docker exec -u node n8n n8n list:workflow 2>/dev/null | grep -i \"DDD-Webseite\" || true
'"
