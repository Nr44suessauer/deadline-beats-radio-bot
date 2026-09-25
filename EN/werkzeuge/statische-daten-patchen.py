#!/usr/bin/env python3
"""Clears the cache in the bot workflow without losing operator and test keys.

Runs after every import (the import overwrites the static data).
Runs in container 103, while n8n is standing.
"""
import json
import sqlite3

DB = "/var/lib/docker/volumes/n8n_data/_data/database.sqlite"

db = sqlite3.connect(DB)
zeile = db.execute("select staticData from workflow_entity where id = ?",
                   ("RadioTelegramBot",)).fetchone()
data = json.loads(zeile[0]) if zeile and zeile[0] else {}
glob = data.setdefault("global", {})
print("before:", sorted(glob.keys()),
      "| Operator:", glob.get("allowed"),
      "| Key set:", bool(glob.get("testSchluessel")))

# Operator list and test keys remain - only clear the cache.
glob["suchen"] = {}
glob["last"] = {}
glob["interrupt"] = {}

db.execute("update workflow_entity set staticData = ? where id = ?",
           (json.dumps(data, ensure_ascii=False), "RadioTelegramBot"))
db.commit()
print("after:", sorted(glob.keys()),
      "| Operator:", glob.get("allowed"),
      "| Key set:", bool(glob.get("testSchluessel")))
