#!/usr/bin/env python3
"""Bereitet die Importdatei fuer alle Radio-Arbeitsablaeufe auf.

n8n erwartet ein Array mit Kennung und Zeitstempeln. Aufruf:
  import-agent-vorbereiten.py            -> Werkzeuge + Agent
  import-agent-vorbereiten.py werkzeuge  -> nur die Werkzeuge
"""
import datetime
import json
import sys

was = sys.argv[1] if len(sys.argv) > 1 else "alles"
jetzt = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def aufbereiten(w):
    w.setdefault("createdAt", jetzt)
    w["updatedAt"] = jetzt
    w["description"] = None
    w["isArchived"] = False
    return w


werkzeuge = json.load(open("/tmp/radio-werkzeuge.json", encoding="utf-8"))
agent = json.load(open("/tmp/radio-agent.json", encoding="utf-8"))

if was in ("alles", "werkzeuge"):
    datei = "/tmp/radio-werkzeuge-import.json"
    daten = [aufbereiten(w) for w in werkzeuge]
    json.dump(daten, open(datei, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("Werkzeuge:", datei, "|", len(daten), "Arbeitsablaeufe")

if was in ("alles", "agent"):
    datei = "/tmp/radio-agent-import.json"
    json.dump([aufbereiten(agent)], open(datei, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("Agent:", datei, "| Knoten:", len(agent["nodes"]))
