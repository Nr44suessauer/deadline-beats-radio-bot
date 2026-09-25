#!/usr/bin/env python3
"""Prepares the import file for all radio workflows.

n8n expects an array with identifier and timestamps. Call:
 import-agent-prepare.py            -> Tools + Agent
 import-agent-prepare.py werkzeuge  -> only the tools
"""
import datetime
import json
import sys

was = sys.argv[1] if len(sys.argv) > 1 else "everything"
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def aufbereiten(w):
    w.setdefault("createdAt", now)
    w["updatedAt"] = now
    w["description"] = None
    w["isArchived"] = False
    return w


werkzeuge = json.load(open("/tmp/radio-werkzeuge.json", encoding="utf-8"))
agent = json.load(open("/tmp/radio-agent.json", encoding="utf-8"))

if was in ("everything", "werkzeuge"):
    file = "/tmp/radio-werkzeuge-import.json"
    data = [aufbereiten(w) for w in werkzeuge]
    json.dump(data, open(file, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("Tools:", file, "|", len(data), "Arbeitsablaeufe")

if was in ("everything", "agent"):
    file = "/tmp/radio-agent-import.json"
    json.dump([aufbereiten(agent)], open(file, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("Agent:", file, "| Node:", len(agent["nodes"]))
