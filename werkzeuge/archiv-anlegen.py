#!/usr/bin/env python3
"""Legt eine archivierte Sicherung des Bot-Arbeitsablaufs an und raeumt die Testkennung weg.

Laeuft im Container 103, waehrend n8n steht.
Die Sicherung bekommt isArchived=1 - sie erscheint damit in der n8n-Oberflaeche
unter "Archiviert" und wird nie ausgefuehrt.
"""
import json
import sqlite3
import sys
import uuid

QUELLE = "RadioTelegramBot"
ZIEL = "RadioTelegramBot-Archiv-2026-09-19"
NAME = "Radio - Telegram-Wunschbot (Sicherung 19.09.2026)"
ORDNER = "vEDODlq4jIKCUDmf"          # Ordner "Sender 1: Deadline Beats"
TESTKENNUNG = "1"                    # nur fuer Testlaeufe, gehoert nicht in die Betreiberliste

DB = "/var/lib/docker/volumes/n8n_data/_data/database.sqlite"
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

# --- 1) Testkennung aus der Betreiberliste des laufenden Arbeitsablaufs entfernen
zeile = db.execute("select staticData from workflow_entity where id = ?", (QUELLE,)).fetchone()
daten = json.loads(zeile["staticData"]) if zeile and zeile["staticData"] else {}
glob = daten.setdefault("global", {})
vorher = list(glob.get("erlaubte") or [])
glob["erlaubte"] = [k for k in vorher if k != TESTKENNUNG]
db.execute("update workflow_entity set staticData = ? where id = ?",
           (json.dumps(daten, ensure_ascii=False), QUELLE))
print("Betreiber:", vorher, "->", glob["erlaubte"])

# --- 2) Sicherung anlegen (Kopie der laufenden Fassung, archiviert)
alt = db.execute("select * from workflow_entity where id = ?", (QUELLE,)).fetchone()
db.execute("delete from workflow_entity where id = ?", (ZIEL,))
db.execute(
    """insert into workflow_entity
       (id, name, active, nodes, connections, settings, staticData, pinData, versionId,
        triggerCount, meta, parentFolderId, createdAt, updatedAt, isArchived, versionCounter,
        description, nodeGroups)
       values (?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), 1, 1, ?, '[]')""",
    (ZIEL, NAME, alt["nodes"], alt["connections"], alt["settings"], alt["staticData"],
     alt["pinData"], str(uuid.uuid4()), alt["triggerCount"], alt["meta"], ORDNER,
     "Sicherung vom 19.09.2026 - spielt sofort ueber die Dateischnittstelle des Senders."),
)

# --- 3) Dem Projekt zuordnen, sonst taucht sie in der Oberflaeche nicht auf
projekt = db.execute("select projectId, role from shared_workflow where workflowId = ?",
                     (QUELLE,)).fetchone()
db.execute("delete from shared_workflow where workflowId = ?", (ZIEL,))
db.execute("insert into shared_workflow (workflowId, projectId, role, createdAt, updatedAt)"
           " values (?, ?, ?, datetime('now'), datetime('now'))",
           (ZIEL, projekt["projectId"], projekt["role"]))

# --- 4) Kontrolle
for r in db.execute("select id, name, active, isArchived, parentFolderId from workflow_entity"
                    " where id in (?, ?)", (QUELLE, ZIEL)):
    print(" ", dict(r))
print("Projekt:", projekt["projectId"], "| Knoten:", len(json.loads(alt["nodes"])))
db.commit()
db.close()
