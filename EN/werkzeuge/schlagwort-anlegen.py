#!/usr/bin/env python3
"""Visible grouping of Radio workflow processes (tags).

n8n shows **folders** only with the free registered Community license
(see docs.n8n.io/deploy/host-n8n/community-edition-features.md). Until then
a **tag** — which is visible in every edition and can be filtered at the top of the overview
is used to group workflows. The folder remains in the database
and appears automatically once the license is entered.

Assigned:

 Radio            -> Radio - Telegram-Agent (the bot), Radio - AI-Moderator
 Radio-tool   -> the sub-workflow that the agent calls

No longer attached to the tag "Radio" are the archived versions (old
Wishbot, backup, copy, old tools) — they are located in the archive and would
only make the overview cluttered.

Runs in container 103, **n8n stopped**:

    docker stop n8n && python3 /tmp/schlagwort-anlegen.py && docker start n8n
"""
import secrets
import sqlite3
import string

DB = "/var/lib/docker/volumes/n8n_data/_data/database.sqlite"
ORDNER = "vEDODlq4jIKCUDmf"                     # Folder "Radio"

RADIO = "Radio"
WERKZEUG = "Radio-tool"

AGENT = "RadioAgentBot"
MODERATOR = "bjFSfXGqpLg7AAXw"
TOOLS = ["RadioWerkzeug", "AzuraWerkzeug"]
STILLGELEGT = ["RadioTelegramBot", "RadioTelegramBot-Archiv-2026-09-19",
               "iDfPikpAIqTO9XQ2", "RadioWerkzeugSuche", "RadioWerkzeugRichtung",
               "RadioWerkzeugStatus", "RadioWerkzeugSofort", "RadioWerkzeugDanach"]

ALPHABET = string.ascii_letters + string.digits


def neue_kennung() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(16))


def schlagwort(db, name: str) -> str:
    zeile = db.execute("select id from tag_entity where name = ?", (name,)).fetchone()
    if zeile:
        print(" Tag ’%s’ already exists (%s)" % (name, zeile[0]))
        return zeile[0]
    identifier = neue_kennung()
    db.execute("insert into tag_entity (id, name, createdAt, updatedAt)"
               " values (?, ?, datetime('now'), datetime('now'))", (identifier, name))
    print(" Tag ’%s’ created: %s" % (name, identifier))
    return identifier


def setzen(db, wf: str, tag: str) -> None:
    name = db.execute("select name from workflow_entity where id = ?", (wf,)).fetchone()
    if not name:
        print(" NOTE: Workflow %s missing" % wf)
        return
    already = db.execute("select 1 from workflows_tags where workflowId = ? and tagId = ?",
                       (wf, tag)).fetchone()
    if already:
        print(" ’%s’ already has this tag" % name[0])
    else:
        db.execute("insert into workflows_tags (workflowId, tagId) values (?, ?)", (wf, tag))
        print(" ’%s’ -> tag" % name[0])


def remove(db, wf: str, tag: str) -> None:
    name = db.execute("select name from workflow_entity where id = ?", (wf,)).fetchone()
    weg = db.execute("delete from workflows_tags where workflowId = ? and tagId = ?",
                     (wf, tag)).rowcount
    if not name:
        return
    if weg:
        print(" ’%s’ -> tag removed" % name[0])


db = sqlite3.connect(DB)

tag_radio = schlagwort(db, RADIO)
tag_werkzeug = schlagwort(db, WERKZEUG)

print("\n  Assign:")
setzen(db, AGENT, tag_radio)
setzen(db, MODERATOR, tag_radio)
for wf in TOOLS:
    setzen(db, wf, tag_werkzeug)

print("\n  Detach archived:")
for wf in STILLGELEGT:
    remove(db, wf, tag_radio)
    remove(db, wf, tag_werkzeug)

# Place the lingering copy of the old Wishbot in the archive (reversible:
# isArchived = 0). Identifier and content remain intact.
kopie = db.execute("update workflow_entity set isArchived = 1, active = 0"
                   " where id = 'iDfPikpAIqTO9XQ2'").rowcount
if kopie:
    print("\n  Remaining copy of the old Wishbot archived (iDfPikpAIqTO9XQ2)")

# Folder "Radio" (visible with license) equipped with both tags
for tag in (tag_radio, tag_werkzeug):
    if db.execute("select 1 from folder where id = ?", (ORDNER,)).fetchone():
        if not db.execute("select 1 from folder_tag where folderId = ? and tagId = ?",
                          (ORDNER, tag)).fetchone():
            db.execute("insert into folder_tag (folderId, tagId) values (?, ?)", (ORDNER, tag))
            print(" Folder ‘Radio’ -> tag added")

db.commit()

print("\n  Result:")
for r in db.execute("select t.name, w.name from workflows_tags wt"
                    " join workflow_entity w on w.id = wt.workflowId"
                    " join tag_entity t on t.id = wt.tagId order by t.name, w.name"):
    print(" %-18s %s" % r)
db.close()
