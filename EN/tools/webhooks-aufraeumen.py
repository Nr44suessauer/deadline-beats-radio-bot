#!/usr/bin/env python3
"""Removes orphaned webhook entries (workflow no longer exists)."""
import sqlite3

DB = '/var/lib/docker/volumes/n8n_data/_data/database.sqlite'
db = sqlite3.connect(DB)
verwaist = db.execute(
    'select workflowId, webhookPath, method, node from webhook_entity '
    'where workflowId not in (select id from workflow_entity)').fetchall()
print('orphaned webhooks:', verwaist)
db.execute('delete from webhook_entity where workflowId not in (select id from workflow_entity)')
db.commit()
print('Webhooks now:', db.execute(
    'select workflowId, webhookPath, method, node from webhook_entity').fetchall())
