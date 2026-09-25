#!/bin/bash
# Nachtrag: Leeren (DELETE) und Umbenennen (PUT) genau pruefen.
set -uo pipefail

SSH="ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 root@192.168.178.163"
API=http://192.168.178.33/api/station/1
K=$($SSH 'pct exec 106 -- docker exec azuracast cat /var/azuracast/api_key.txt')
H=(-H "X-API-Key: $K")

PFAD=$(curl -s "${H[@]}" "$API/files?rowCount=1&searchPhrase=Juliet" | python3 -c "
import json,sys; print(json.load(sys.stdin)['rows'][0]['path'])")
PFAD2=$(curl -s "${H[@]}" "$API/files?rowCount=2&searchPhrase=Juliet" | python3 -c "
import json,sys; print(json.load(sys.stdin)['rows'][1]['path'])")

echo "=== Testliste anlegen ==="
curl -s -X PUT "${H[@]}" -H 'Content-Type: application/json' "$API/files/batch" \
  -d "$(python3 -c "
import json,sys
print(json.dumps({'do':'playlist','files':[sys.argv[1],sys.argv[2]],
                  'playlists':['new'],'new_playlist_name':'Testlauf Bot 3'}))
" "$PFAD" "$PFAD2")" > /dev/null
ID=$(curl -s "${H[@]}" "$API/playlists" | python3 -c "
import json,sys
for p in json.load(sys.stdin):
    if p['name'] == 'Testlauf Bot 3': print(p['id']); break")
echo "  Kennung: $ID | Inhalt: $(curl -s "${H[@]}" "$API/playlist/$ID/export/m3u" | wc -l) Zeilen"

echo "=== Leeren mit DELETE ==="
curl -s -o /tmp/leer.json -w '  HTTP %{http_code}  ' -X DELETE "${H[@]}" "$API/playlist/$ID/empty"
head -c 160 /tmp/leer.json; echo
echo "  Inhalt danach: $(curl -s "${H[@]}" "$API/playlist/$ID/export/m3u" | wc -l) Zeilen"

echo "=== Umbenennen: GET, aendern, PUT ==="
curl -s "${H[@]}" "$API/playlist/$ID" > /tmp/l.json
python3 -c "
import json
d = json.load(open('/tmp/l.json'))
d['name'] = 'Testlauf Bot 4'
json.dump(d, open('/tmp/l-neu.json','w'), ensure_ascii=False)
print('  gesendete Felder:', len(d))
"
curl -s -o /tmp/put.json -w '  HTTP %{http_code}  ' -X PUT "${H[@]}" \
  -H 'Content-Type: application/json' --data-binary @/tmp/l-neu.json "$API/playlist/$ID"
head -c 200 /tmp/put.json; echo
echo "  Name jetzt: $(curl -s "${H[@]}" "$API/playlists" | python3 -c "
import json,sys
for p in json.load(sys.stdin):
    if p['id'] == $ID: print(repr(p['name']))")"

echo "=== Aufraeumen ==="
curl -s -o /dev/null -w '  DELETE Liste: HTTP %{http_code}\n' -X DELETE "${H[@]}" "$API/playlist/$ID"
curl -s "${H[@]}" "$API/playlists" | python3 -c "
import json,sys
print('  Listen jetzt:', [(p['id'], p['name']) for p in json.load(sys.stdin)])"
