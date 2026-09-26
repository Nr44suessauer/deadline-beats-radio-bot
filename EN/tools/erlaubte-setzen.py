#!/usr/bin/env python3
"""Sets the operator list in the bot workflow (call: erlaubte-setzen.py 1 YOUR-CHAT-ID)."""
import json
import sqlite3
import sys

DB = "/var/lib/docker/volumes/n8n_data/_data/database.sqlite"

db = sqlite3.connect(DB)
zeile = db.execute("select staticData from workflow_entity where id = ?",
                   ("RadioTelegramBot",)).fetchone()
data = json.loads(zeile[0]) if zeile and zeile[0] else {}
glob = data.setdefault("global", {})
glob["allowed"] = [str(x) for x in sys.argv[1:]]
db.execute("update workflow_entity set staticData = ? where id = ?",
           (json.dumps(data, ensure_ascii=False), "RadioTelegramBot"))
db.commit()
print("Operators:", glob["allowed"])
