#!/usr/bin/env python3
"""Prueft die Syntax aller Code-Knoten der erzeugten Workflows."""
import json
import subprocess
import sys

dateien = sys.argv[1:] or ['/tmp/radio-telegram-import.json', '/tmp/radio-moderator-import.json']
fehler = 0
for datei in dateien:
    try:
        daten = json.load(open(datei))
    except FileNotFoundError:
        print(f'{datei}: fehlt')
        continue
    daten = daten if isinstance(daten, list) else [daten]
    for wf in daten:
        print(f'== {wf.get("name")} ({wf.get("id")})')
        for n in wf.get('nodes', []):
            if not n['type'].endswith('code'):
                continue
            code = n['parameters'].get('jsCode', '')
            open('/tmp/_check.js', 'w').write(code)
            p = subprocess.run(['node', '--check', '/tmp/_check.js'], capture_output=True, text=True)
            if p.returncode != 0:
                fehler += 1
                erste = [z for z in p.stderr.splitlines() if 'SyntaxError' in z or 'Error' in z]
                print(f'   FEHLER in "{n["name"]}": {erste[0] if erste else p.stderr.strip()[:120]}')
            else:
                print(f'   ok     "{n["name"]}"')
print('\nFehlerhafte Code-Knoten:', fehler)
sys.exit(1 if fehler else 0)
