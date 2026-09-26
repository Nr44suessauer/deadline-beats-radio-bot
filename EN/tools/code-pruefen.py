#!/usr/bin/env python3
"""Checks the syntax of all code nodes of the generated workflows."""
import json
import subprocess
import sys

dateien = sys.argv[1:] or ['/tmp/radio-telegram-import.json', '/tmp/radio-moderator-import.json']
error = 0
for file in dateien:
    try:
        data = json.load(open(file))
    except FileNotFoundError:
        print(f'{file}: missing')
        continue
    data = data if isinstance(data, list) else [data]
    for wf in data:
        print(f'== {wf.get("name")} ({wf.get("id")})')
        for n in wf.get('nodes', []):
            if not n['type'].endswith('code'):
                continue
            code = n['parameters'].get('jsCode', '')
            open('/tmp/_check.js', 'w').write(code)
            p = subprocess.run(['node', '--check', '/tmp/_check.js'], capture_output=True, text=True)
            if p.returncode != 0:
                error += 1
                first = [z for z in p.stderr.splitlines() if 'SyntaxError' in z or 'Error' in z]
                print(f'   ERROR in "{n["name"]}": {first[0] if first else p.stderr.strip()[:120]}')
            else:
                print(f'   ok     "{n["name"]}"')
print('\nFaulty code nodes:', error)
sys.exit(1 if error else 0)
