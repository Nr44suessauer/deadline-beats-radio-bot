#!/usr/bin/env bash
# Zeigt die Form der AzuraCast-Antworten (Schluessel + Beispiele).
for p in "/api/station/1/history" "/api/station/1/queue" "/api/station/1/files?rowCount=2"; do
  echo "=== $p"
  curl -s -H "X-API-Key: $AZ_KEY" "http://192.168.178.33$p" -o /tmp/f.json
  python3 - <<'PY'
import json
d = json.load(open('/tmp/f.json'))
if isinstance(d, list):
    d = {'liste': d}
print('Schluessel:', list(d.keys())[:14])
for k, v in d.items():
    if isinstance(v, list) and v:
        print('  Liste:', k, '| Eintrag-Schluessel:', list(v[0].keys())[:14])
        s = v[0].get('song') or {}
        print('    song-Schluessel:', list(s.keys())[:14])
        print('    song.id:', s.get('id'), '| song.text:', s.get('text'))
        print('    unique_id im Eintrag:', v[0].get('unique_id'), '| played_at:', v[0].get('played_at'))
        break
PY
done
