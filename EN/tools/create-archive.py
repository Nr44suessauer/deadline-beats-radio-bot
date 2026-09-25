#!/usr/bin/env python3
"""Creates an archived backup of the Bot workflow and removes the test flag.

Runs in container 103, while n8n is standing.
The backup gets isArchived=1 - it will therefore appear in the n8n interface
under "Archived" and will never be executed.
"""
import json
import sqlite3
import sys
import uuid

QUELLE = "RadioTelegramBot"
ZIEL = "RadioTelegramBot-Archiv-2026-09-19"
NAME = "Radio - Telegram wish bot (Backup 19.09.2026)"
ORDNER = "vEDODlq4jIKCUDmf"          # Folder "Radio"
TESTKENNUNG = "1"                    # only for test runs, does not belong in the operator list

DB = "/var/lib/docker/volumes/n8n_data/_data/database.sqlite"
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

# --- 1) Remove test flag from the operator list of the running workflow
zeile = db.execute("select staticData from workflow_entity where id = ?", (QUELLE,)).fetchone()
data = json.loads(zeile["staticData"]) if zeile and zeile["staticData"] else {}
glob = data.setdefault("global", {})
before = list(glob.get("allowed") or [])
glob["allowed"] = [k for k in before if k != TESTKENNUNG]
db.execute("update workflow_entity set staticData = ? where id = ?",
           (json.dumps(data, ensure_ascii=False), QUELLE))
print("Operators:", before, "->", glob["allowed"])

# --- 2) Create backup (copy of the current version, archived)
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
     "Backup from 19.09.2026 - plays immediately via the sender’s file interface."),
)

# --- 3) Assign to project, otherwise it will not appear in the interface
projekt = db.execute("select projectId, role from shared_workflow where workflowId = ?",
                     (QUELLE,)).fetchone()
db.execute("delete from shared_workflow where workflowId = ?", (ZIEL,))
db.execute("insert into shared_workflow (workflowId, projectId, role, createdAt, updatedAt)"
           " values (?, ?, ?, datetime('now'), datetime('now'))",
           (ZIEL, projekt["projectId"], projekt["role"]))

# --- 4) Check
for r in db.execute("select id, name, active, isArchived, parentFolderId from workflow_entity"
                    " where id in (?, ?)", (QUELLE, ZIEL)):
    print(" ", dict(r))
print("Project:", projekt["projectId"], "| Node:", len(json.loads(alt["nodes"])))
db.commit()
db.close()
