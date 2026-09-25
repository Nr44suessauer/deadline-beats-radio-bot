#!/usr/bin/env python3
"""Setzt Testschluessel und Betreiberliste im Bot-Workflow (Aufruf: daten-setzen.py <schluessel> <id...>)."""
import json
import sqlite3
import sys

DB = "/var/lib/docker/volumes/n8n_data/_data/database.sqlite"
db = sqlite3.connect(DB)
zeile = db.execute("select staticData from workflow_entity where id = ?", ("RadioTelegramBot",)).fetchone()
daten = json.loads(zeile[0]) if zeile and zeile[0] else {}
glob = daten.setdefault("global", {})
glob["testSchluessel"] = sys.argv[1]
glob["erlaubte"] = [str(x) for x in sys.argv[2:]]
glob["suchen"] = {}
glob["letzter"] = {}
glob["interrupt"] = {}
db.execute("update workflow_entity set staticData = ? where id = ?",
           (json.dumps(daten, ensure_ascii=False), "RadioTelegramBot"))
db.commit()
print("Betreiber:", glob["erlaubte"], "| Testschluessel gesetzt:", bool(glob["testSchluessel"]))
