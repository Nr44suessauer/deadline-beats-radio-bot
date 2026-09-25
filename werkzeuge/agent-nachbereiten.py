#!/usr/bin/env python3
"""Richtet die Radio-Arbeitsablaeufe ein (laeuft im Container 103, waehrend n8n steht).

Aufruf: agent-nachbereiten.py <testschluessel> <chatId...>

  - ordnet Werkzeuge und Agent dem Projekt und dem Ordner
    "Deadline Beats" zu (ohne shared_workflow-Zeile erscheint ein
    Arbeitsablauf in keiner Liste)
  - setzt Testschluessel und Betreiberliste im Agenten
  - raeumt Webhook-Leichen ab: n8n legt fuer jeden Webhook eine Zeile an, die
    beim Abschalten nur entfernt wird, wenn n8n selbst abschaltet. Bleibt eine
    Zeile liegen, laesst sich der neue Bot nicht aktivieren ("The URL path that
    the ... node uses is already taken").

Das Aktivieren/Schalten selbst macht NICHT dieses Skript, sondern der offizielle
Befehl `n8n update:workflow --active=...` (siehe agent-einspielen.sh): n8n 2.x
haelt neben `active` noch die veroeffentlichte Fassung (`activeVersionId`) - ein
Schreiben der Spalte `active` allein wird beim naechsten Start ueberschrieben.
"""
import json
import sqlite3
import sys

PROJEKT = "DEINE-N8N-PROJEKT-KENNUNG"
ORDNER = "vEDODlq4jIKCUDmf"          # der n8n-Ordner
AGENT = "RadioAgentBot"
ZENTRALE = ["Konfiguration", "StimmenBot"]   # gehoeren in denselben Ordner
ALT = "RadioTelegramBot"
WERKZEUGE = ["RadioWerkzeug", "AzuraWerkzeug", "MeldungenWerkzeug"]
# Frueher gab es getrennte Werkzeuge (Titel suchen / Richtung suchen / Was laeuft)
# und eigene Spiel-Werkzeuge (Sofort/Danach). Alles steckt jetzt in EINEM Ablauf
# (RadioWerkzeug). Die alten werden hier nur archiviert - nicht geloescht, damit
# die Fassung nachvollziehbar bleibt.
ALT_WERKZEUGE = ["RadioWerkzeugSuche", "RadioWerkzeugRichtung", "RadioWerkzeugStatus",
                 "RadioWerkzeugSofort", "RadioWerkzeugDanach"]

DB = "/var/lib/docker/volumes/n8n_data/_data/database.sqlite"

schluessel = sys.argv[1]
ids = [str(x) for x in sys.argv[2:]]

db = sqlite3.connect(DB)

for wf in WERKZEUGE + [AGENT] + ZENTRALE:
    db.execute("update workflow_entity set parentFolderId = ? where id = ?", (ORDNER, wf))
    if not db.execute("select 1 from shared_workflow where workflowId = ?", (wf,)).fetchone():
        db.execute("insert into shared_workflow (workflowId, projectId, role, createdAt, updatedAt)"
                   " values (?, ?, 'workflow:owner', datetime('now'), datetime('now'))",
                   (wf, PROJEKT))

# Die Spalte `active` wird NICHT hier gesetzt: das macht der offizielle Befehl
# `n8n update:workflow --active=...` (siehe agent-einspielen.sh). Ein direkter
# Schreibzugriff auf die Spalte wird von n8n beim naechsten Start verworfen.

# abgeschaltete Ablaeufe duerfen keine Webhook-Zeile behalten
leichen = db.execute(
    "delete from webhook_entity where workflowId in"
    " (select id from workflow_entity where active = 0)").rowcount

# alte Werkzeuge stilllegen
alt = db.execute(
    "update workflow_entity set active = 0, isArchived = 1 where id in (%s)"
    % ",".join("?" * len(ALT_WERKZEUGE)), ALT_WERKZEUGE).rowcount

# Der fruehere Wunschbot ist abgeloest: abschalten und ins Archiv legen (bleibt in
# der Oberflaeche unter "Archiviert" nachvollziehbar, Kennung bleibt erhalten).
db.execute("update workflow_entity set active = 0, isArchived = 1 where id = ?", (ALT,))

daten = json.dumps({"global": {"erlaubte": ids, "testSchluessel": schluessel, "suchen": {}}},
                   ensure_ascii=False)
db.execute("update workflow_entity set staticData = ? where id = ?", (daten, AGENT))
db.commit()

print("Webhook-Leichen entfernt:", leichen, "| alte Werkzeuge stillgelegt:", alt)
for r in db.execute(
        "select id, name, active, isArchived, parentFolderId from workflow_entity"
        " where id in (%s)" % ",".join("?" * (len(WERKZEUGE) + 2 + len(ZENTRALE))),
        WERKZEUGE + [AGENT, ALT] + ZENTRALE):
    print("  %-26s aktiv=%s archiviert=%s ordner=%s" % (r[0], r[2], r[3], r[4]))
print("Betreiber:", ids, "| Testschluessel gesetzt:", bool(schluessel))
print("Achtung: Aktivieren/Schalten laeuft ueber n8n update:workflow --active=...")
db.close()
