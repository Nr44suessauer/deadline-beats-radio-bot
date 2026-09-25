#!/usr/bin/env python3
"""Sets test key and operator list in bot workflow (call: data-setzen.py <key> <id...>)."""
import json
import sqlite3
import sys

DB = "/var/lib/docker/volumes/n8n_data/_data/database.sqlite"
db = sqlite3.connect(DB)
zeile = db.execute("select staticData from workflow_entity where id = ?", ("RadioTelegramBot",)).fetchone()
data = json.loads(zeile[0]) if zeile and zeile[0] else {}
glob = data.setdefault("global", {})
glob["testSchluessel"] = sys.argv[1]
glob["allowed"] = [str(x) for x in sys.argv[2:]]
glob["suchen"] = {}
glob["last"] = {}
glob["interrupt"] = {}
db.execute("update workflow_entity set staticData = ? where id = ?",
           (json.dumps(data, ensure_ascii=False), "RadioTelegramBot"))
db.commit()
print("Operators:", glob["allowed"], "| Test key set:", bool(glob["testSchluessel"]))
