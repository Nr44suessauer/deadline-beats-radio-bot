#!/usr/bin/env python3
"""Entfernt verwaiste Webhook-Eintraege (Workflow existiert nicht mehr)."""
import sqlite3

DB = '/var/lib/docker/volumes/n8n_data/_data/database.sqlite'
db = sqlite3.connect(DB)
verwaist = db.execute(
    'select workflowId, webhookPath, method, node from webhook_entity '
    'where workflowId not in (select id from workflow_entity)').fetchall()
print('verwaiste Webhooks:', verwaist)
db.execute('delete from webhook_entity where workflowId not in (select id from workflow_entity)')
db.commit()
print('Webhooks jetzt:', db.execute(
    'select workflowId, webhookPath, method, node from webhook_entity').fetchall())
