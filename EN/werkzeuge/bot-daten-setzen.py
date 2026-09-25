#!/usr/bin/env python3
"""Sets keys and operator list in the static data of the bot workflow."""
import json
import sqlite3
import sys

DB = '/var/lib/docker/volumes/n8n_data/_data/database.sqlite'
KEY = sys.argv[1] if len(sys.argv) > 1 else None

db = sqlite3.connect(DB)
zeile = db.execute('select staticData from workflow_entity where id = ?',
                   ('RadioTelegramBot',)).fetchone()
data = json.loads(zeile[0]) if zeile and zeile[0] else {}
glob = data.setdefault('global', {})
if KEY:
    glob['testSchluessel'] = KEY
# Clear operator list and cache (remove test identifiers).
glob['allowed'] = []
glob['suchen'] = {}
glob['last'] = {}
glob['interrupt'] = {}
db.execute('update workflow_entity set staticData = ? where id = ?',
           (json.dumps(data, ensure_ascii=False), 'RadioTelegramBot'))
db.commit()
print('Data:', json.dumps(data)[:200])
