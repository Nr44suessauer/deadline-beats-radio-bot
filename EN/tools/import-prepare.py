#!/usr/bin/env python3
"""Prepares the import file (n8n expects an array with identifier + timestamps)."""
import datetime
import json
import sys

source = sys.argv[1] if len(sys.argv) > 1 else '/tmp/radio-telegram.json'
target = sys.argv[2] if len(sys.argv) > 2 else '/tmp/radio-telegram-import.json'

d = json.load(open(source))
now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
d.setdefault('createdAt', now)
d['updatedAt'] = now
d['description'] = None
d['isArchived'] = False
json.dump([d], open(target, 'w'), ensure_ascii=False, indent=2)
print('Workflow identifier:', d['id'], '| File:', target, '| Node:', len(d['nodes']))
