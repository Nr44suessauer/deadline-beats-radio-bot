#!/usr/bin/env python3
"""Sichtbare Gruppierung der Radio-Arbeitsablaeufe (Schlagwoerter).

n8n zeigt **Ordner** nur mit der kostenlosen registrierten Community-Lizenz
(siehe docs.n8n.io/deploy/host-n8n/community-edition-features.md). Bis dahin
gruppiert ein **Schlagwort (Tag)** — das ist in jeder Edition sichtbar und laesst
sich oben in der Uebersicht filtern. Der Ordner liegt trotzdem in der Datenbank
und erscheint automatisch, sobald die Lizenz eingetragen ist.

Vergeben wird:

  Radio            -> Radio - Telegram-Agent (der Bot), Radio - AI-Moderator
  Radio-Werkzeug   -> der Unter-Arbeitsablauf, den der Agent aufruft

Nicht mehr am Schlagwort "Radio" haengen die stillgelegten Fassungen (alter
Wunschbot, Sicherung, Kopie, alte Werkzeuge) — sie liegen im Archiv und wuerden
die Uebersicht nur unuebersichtlich machen.

Laeuft im Container 103, **n8n gestoppt**:

    docker stop n8n && python3 /tmp/schlagwort-anlegen.py && docker start n8n
"""
import secrets
import sqlite3
import string

DB = "/var/lib/docker/volumes/n8n_data/_data/database.sqlite"
ORDNER = "vEDODlq4jIKCUDmf"                     # der n8n-Ordner

RADIO = "Radio"
WERKZEUG = "Radio-Werkzeug"

AGENT = "RadioAgentBot"
MODERATOR = "bjFSfXGqpLg7AAXw"
WERKZEUGE = ["RadioWerkzeug", "AzuraWerkzeug"]
STILLGELEGT = ["RadioTelegramBot", "RadioTelegramBot-Archiv-2026-09-19",
               "iDfPikpAIqTO9XQ2", "RadioWerkzeugSuche", "RadioWerkzeugRichtung",
               "RadioWerkzeugStatus", "RadioWerkzeugSofort", "RadioWerkzeugDanach"]

ALPHABET = string.ascii_letters + string.digits


def neue_kennung() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(16))


def schlagwort(db, name: str) -> str:
    zeile = db.execute("select id from tag_entity where name = ?", (name,)).fetchone()
    if zeile:
        print("  Schlagwort '%s' gibt es schon (%s)" % (name, zeile[0]))
        return zeile[0]
    kennung = neue_kennung()
    db.execute("insert into tag_entity (id, name, createdAt, updatedAt)"
               " values (?, ?, datetime('now'), datetime('now'))", (kennung, name))
    print("  Schlagwort '%s' angelegt: %s" % (name, kennung))
    return kennung


def setzen(db, wf: str, tag: str) -> None:
    name = db.execute("select name from workflow_entity where id = ?", (wf,)).fetchone()
    if not name:
        print("  HINWEIS: Arbeitsablauf %s fehlt" % wf)
        return
    schon = db.execute("select 1 from workflows_tags where workflowId = ? and tagId = ?",
                       (wf, tag)).fetchone()
    if schon:
        print("  '%s' hat das Schlagwort schon" % name[0])
    else:
        db.execute("insert into workflows_tags (workflowId, tagId) values (?, ?)", (wf, tag))
        print("  '%s' -> Schlagwort" % name[0])


def entfernen(db, wf: str, tag: str) -> None:
    name = db.execute("select name from workflow_entity where id = ?", (wf,)).fetchone()
    weg = db.execute("delete from workflows_tags where workflowId = ? and tagId = ?",
                     (wf, tag)).rowcount
    if not name:
        return
    if weg:
        print("  '%s' -> Schlagwort entfernt" % name[0])


db = sqlite3.connect(DB)

tag_radio = schlagwort(db, RADIO)
tag_werkzeug = schlagwort(db, WERKZEUG)

print("\n  Zuordnen:")
setzen(db, AGENT, tag_radio)
setzen(db, MODERATOR, tag_radio)
for wf in WERKZEUGE:
    setzen(db, wf, tag_werkzeug)

print("\n  Stillgelegtes abhaengen:")
for wf in STILLGELEGT:
    entfernen(db, wf, tag_radio)
    entfernen(db, wf, tag_werkzeug)

# Die liegengebliebene Kopie des alten Wunschbots ins Archiv legen (umkehrbar:
# isArchived = 0). Kennung und Inhalt bleiben erhalten.
kopie = db.execute("update workflow_entity set isArchived = 1, active = 0"
                   " where id = 'iDfPikpAIqTO9XQ2'").rowcount
if kopie:
    print("\n  Restkopie des alten Wunschbots archiviert (iDfPikpAIqTO9XQ2)")

# Ordner "Radio" (sichtbar mit Lizenz) mit beiden Schlagwoertern versehen
for tag in (tag_radio, tag_werkzeug):
    if db.execute("select 1 from folder where id = ?", (ORDNER,)).fetchone():
        if not db.execute("select 1 from folder_tag where folderId = ? and tagId = ?",
                          (ORDNER, tag)).fetchone():
            db.execute("insert into folder_tag (folderId, tagId) values (?, ?)", (ORDNER, tag))
            print("  Ordner 'Radio' -> Schlagwort ergaenzt")

db.commit()

print("\n  Ergebnis:")
for r in db.execute("select t.name, w.name from workflows_tags wt"
                    " join workflow_entity w on w.id = wt.workflowId"
                    " join tag_entity t on t.id = wt.tagId order by t.name, w.name"):
    print("    %-18s %s" % r)
db.close()
