##!/bin/bash
# Postscript: Check deleting (DELETE) and renaming (PUT) precisely.
set -uo pipefail

SSH="ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 root@192.168.178.163"
API=http://192.168.178.33/api/station/1
K=$($SSH 'pct exec 106 -- docker exec azuracast cat /var/azuracast/api_key.txt')
H=(-H "X-API-Key: $K")

PFAD=$(curl -s "${H[@]}" "$API/files?rowCount=1&searchPhrase=Juliet" | python3 -c "
import json,sys; print(json.load(sys.stdin)['rows'][0]['path'])")
PFAD2=$(curl -s "${H[@]}" "$API/files?rowCount=2&searchPhrase=Juliet" | python3 -c "
import json,sys; print(json.load(sys.stdin)['rows'][1]['path'])")

echo "=== Create test list ==="
curl -s -X PUT "${H[@]}" -H 'Content-Type: application/json' "$API/files/batch" \
  -d "$(python3 -c "
import json,sys
print(json.dumps({'do':'playlist','files':[sys.argv[1],sys.argv[2]],
                  'playlists':['new'],'new_playlist_name':'Test run Bot 3'}))
" "$PFAD" "$PFAD2")" > /dev/null
ID=$(curl -s "${H[@]}" "$API/playlists" | python3 -c "
import json,sys
for p in json.load(sys.stdin):
    if p['name'] == 'Test run Bot 3': print(p['id']); break")
echo " Identifier: $ID | Content: $(curl -s"${H[@]}" "$API/playlist/$ID/export/m3u" | wc -l) lines"

echo "=== Empty with DELETE ==="
curl -s -o /tmp/empty.json -w ' HTTP %{http_code}' -X DELETE "${H[@]}" "$API/playlist/$ID/empty"
head -c 160 /tmp/empty.json; echo
echo " Content afterwards: $(curl -s"${H[@]}" "$API/playlist/$ID/export/m3u" | wc -l) lines"

echo "=== Rename: GET, change, PUT ==="
curl -s "${H[@]}" "$API/playlist/$ID" > /tmp/l.json
python3 -c "
import json
d = json.load(open('/tmp/l.json'))
d['name'] = 'Test run Bot 4'
json.dump(d, open('/tmp/l-new.json','w'), ensure_ascii=False)
print(' sent fields:', len(d))
"
curl -s -o /tmp/put.json -w ' HTTP %{http_code}' -X PUT "${H[@]}" \
  -H 'Content-Type: application/json' --data-binary @/tmp/l-new.json "$API/playlist/$ID"
head -c 200 /tmp/put.json; echo
echo " Name now: $(curl -s"${H[@]}" "$API/playlists" | python3 -c"
import json,sys
for p in json.load(sys.stdin):
    if p['id'] == $ID: print(repr(p['name']))")"

echo "=== Cleanup ==="
curl -s -o /dev/null -w ' DELETE list: HTTP %{http_code}\n' -X DELETE "${H[@]}" "$API/playlist/$ID"
curl -s "${H[@]}" "$API/playlists" | python3 -c "
import json,sys
print(' Lists now:', [(p['id'], p['name']) for p in json.load(sys.stdin)])"
