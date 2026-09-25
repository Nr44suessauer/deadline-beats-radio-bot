#!/usr/bin/env python3
"""Bereitet die Importdatei auf (n8n erwartet ein Array mit Kennung + Zeitstempeln)."""
import datetime
import json
import sys

quelle = sys.argv[1] if len(sys.argv) > 1 else '/tmp/radio-telegram.json'
ziel = sys.argv[2] if len(sys.argv) > 2 else '/tmp/radio-telegram-import.json'

d = json.load(open(quelle))
jetzt = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
d.setdefault('createdAt', jetzt)
d['updatedAt'] = jetzt
d['description'] = None
d['isArchived'] = False
json.dump([d], open(ziel, 'w'), ensure_ascii=False, indent=2)
print('Workflow-Kennung:', d['id'], '| Datei:', ziel, '| Knoten:', len(d['nodes']))
