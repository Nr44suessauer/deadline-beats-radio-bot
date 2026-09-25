#!/usr/bin/env python3
"""Leert die Zwischenspeicher im Bot-Workflow, ohne Betreiber und Testschluessel zu verlieren.

Wird nach jedem Import ausgefuehrt (der Import ueberschreibt die statischen Daten).
Laeuft im Container 103, waehrend n8n steht.
"""
import json
import sqlite3

DB = "/var/lib/docker/volumes/n8n_data/_data/database.sqlite"

db = sqlite3.connect(DB)
zeile = db.execute("select staticData from workflow_entity where id = ?",
                   ("RadioTelegramBot",)).fetchone()
daten = json.loads(zeile[0]) if zeile and zeile[0] else {}
glob = daten.setdefault("global", {})
print("vorher :", sorted(glob.keys()),
      "| Betreiber:", glob.get("erlaubte"),
      "| Schluessel gesetzt:", bool(glob.get("testSchluessel")))

# Betreiberliste und Testschluessel bleiben - nur die Zwischenspeicher leeren.
glob["suchen"] = {}
glob["letzter"] = {}
glob["interrupt"] = {}

db.execute("update workflow_entity set staticData = ? where id = ?",
           (json.dumps(daten, ensure_ascii=False), "RadioTelegramBot"))
db.commit()
print("nachher:", sorted(glob.keys()),
      "| Betreiber:", glob.get("erlaubte"),
      "| Schluessel gesetzt:", bool(glob.get("testSchluessel")))
