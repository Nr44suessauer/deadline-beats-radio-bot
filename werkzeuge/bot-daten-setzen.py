#!/usr/bin/env python3
"""Setzt Schluessel und Betreiberliste in den statischen Daten des Bot-Workflows."""
import json
import sqlite3
import sys

DB = '/var/lib/docker/volumes/n8n_data/_data/database.sqlite'
SCHLUESSEL = sys.argv[1] if len(sys.argv) > 1 else None

db = sqlite3.connect(DB)
zeile = db.execute('select staticData from workflow_entity where id = ?',
                   ('RadioTelegramBot',)).fetchone()
daten = json.loads(zeile[0]) if zeile and zeile[0] else {}
glob = daten.setdefault('global', {})
if SCHLUESSEL:
    glob['testSchluessel'] = SCHLUESSEL
# Betreiberliste und Zwischenspeicher leeren (Testkennungen entfernen).
glob['erlaubte'] = []
glob['suchen'] = {}
glob['letzter'] = {}
glob['interrupt'] = {}
db.execute('update workflow_entity set staticData = ? where id = ?',
           (json.dumps(daten, ensure_ascii=False), 'RadioTelegramBot'))
db.commit()
print('Daten:', json.dumps(daten)[:200])
