#!/usr/bin/env python3
"""Sets up Radio work processes (runs in container 103, while n8n stands by).

Call: agent-nachbereiten.py <testkey> <chatId...>

 - assigns tools and agent to the project and folder "Radio"
 (without shared_workflow line, a workflow appears in no list)
 - sets test key and operator list in the agent
 - cleans up webhook corpses: n8n creates a line for each webhook,
 which is only removed when n8n itself shuts down. If a
 line remains, the new bot cannot be activated ("The URL path that
 the ... node uses is already taken").

Activating/switching itself is NOT done by this script, but by the official
command `n8n update:workflow --active=...` (see agent-deploy.sh): n8n 2.x
maintains beside `active` also the published version (`activeVersionId`) - a
write to the `active` column alone will be overwritten on next start.
"""
import json
import sqlite3
import sys

PROJEKT = "YOUR-N8N-PROJECT-ID"
ORDNER = "vEDODlq4jIKCUDmf"
AGENT = "RadioAgentBot"
ALT = "RadioTelegramBot"
TOOLS = ["RadioWerkzeug", "AzuraWerkzeug", "MeldungenWerkzeug"]
# Previously there were separate tools (search for title / search for direction / what's running)
# and own play tools (Immediate/After). Everything is now in ONE process
# (RadioTool). The old ones are only archived here - not deleted, so that
# the version remains traceable.
ALT_WERKZEUGE = ["RadioWerkzeugSuche", "RadioWerkzeugRichtung", "RadioWerkzeugStatus",
                 "RadioWerkzeugSofort", "RadioWerkzeugDanach"]

DB = "/var/lib/docker/volumes/n8n_data/_data/database.sqlite"

key = sys.argv[1]
ids = [str(x) for x in sys.argv[2:]]

db = sqlite3.connect(DB)

for wf in TOOLS + [AGENT]:
    db.execute("update workflow_entity set parentFolderId = ? where id = ?", (ORDNER, wf))
    if not db.execute("select 1 from shared_workflow where workflowId = ?", (wf,)).fetchone():
        db.execute("insert into shared_workflow (workflowId, projectId, role, createdAt, updatedAt)"
                   " values (?, ?, 'workflow:owner', datetime('now'), datetime('now'))",
                   (wf, PROJEKT))

# The `active` column is NOT set here: this is done by the official command
# `n8n update:workflow --active=...` (see agent-deploy.sh). A direct
# write access to the column will be discarded by n8n on next start.

# deactivated workflows must not keep webhook lines
leichen = db.execute(
    "delete from webhook_entity where workflowId in"
    " (select id from workflow_entity where active = 0)").rowcount

# archive old tools
alt = db.execute(
    "update workflow_entity set active = 0, isArchived = 1 where id in (%s)"
    % ",".join("?" * len(ALT_WERKZEUGE)), ALT_WERKZEUGE).rowcount

# The former wishbot has been replaced: deactivate and put into archive (remains visible
# in the interface under "Archived" traceable, identifier remains intact).
db.execute("update workflow_entity set active = 0, isArchived = 1 where id = ?", (ALT,))

data = json.dumps({"global": {"allowed": ids, "testSchluessel": key, "suchen": {}}},
                   ensure_ascii=False)
db.execute("update workflow_entity set staticData = ? where id = ?", (data, AGENT))
db.commit()

print("Webhook corpses removed:", leichen, "| old tools archived:", alt)
for r in db.execute(
        "select id, name, active, isArchived, parentFolderId from workflow_entity"
        " where id in (%s)" % ",".join("?" * (len(TOOLS) + 2)),
        TOOLS + [AGENT, ALT]):
    print(" %-26s active=%s archived=%s folder=%s" % (r[0], r[2], r[3], r[4]))
print("Operators:", ids, "| Test key set:", bool(key))
print("Attention: Activating/switching runs via n8n update:workflow --active=...")
db.close()
