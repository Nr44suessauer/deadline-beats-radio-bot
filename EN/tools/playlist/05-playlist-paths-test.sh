##!/bin/bash
# Checks the interface paths for the playlist tasks of the bot
# on a test list (will be deleted again at the end).
# Call:  bash 05-playlist-paths-test.sh
set -uo pipefail

DATENSERVER=192.168.178.163
SSH="ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 root@$DATENSERVER"
API=http://192.168.178.33/api/station/1
K=$($SSH 'pct exec 106 -- docker exec azuracast cat /var/azuracast/api_key.txt')
H=(-H "X-API-Key: $K")

sag() { printf '\n=== %s ===\n' "$1"; }

# --- Retrieve three real title paths from the archive
sag "Get title paths"
PFADE=$(curl -s "${H[@]}" "$API/files?rowCount=3&searchPhrase=Juliet" \
        | python3 -c "
import json,sys
d=json.load(sys.stdin)
for r in d.get('rows',[])[:3]: print(r['path'])
")
echo "$PFADE"
P1=$(echo "$PFADE" | sed -n 1p); P2=$(echo "$PFADE" | sed -n 2p); P3=$(echo "$PFADE" | sed -n 3p)

# --- 1) Create list and fill in one call
sag "1) Create list + fill (files/batch, playlists=[‘new’])"
curl -s -X PUT "${H[@]}" -H 'Content-Type: application/json' "$API/files/batch" \
  -d "$(python3 -c "
import json,sys
print(json.dumps({'do':'playlist','files':[sys.argv[1],sys.argv[2]],
                  'playlists':['new'],'new_playlist_name':'Test run Bot'}))
" "$P1" "$P2")" | head -c 400
echo

# --- 2) Find list
sag "2) List lists"
LISTE=$(curl -s "${H[@]}" "$API/playlists")
echo "$LISTE" | python3 -c "
import json,sys
for p in json.load(sys.stdin):
    print(f\"  id={p['id']}  {p['name']!r}  title={p.get('num_songs')}  aktiv={p.get('is_enabled')}\")
"
ID=$(echo "$LISTE" | python3 -c "
import json,sys
for p in json.load(sys.stdin):
    if p['name'] == 'Test run Bot': print(p['id']); break
")
echo " -> Identifier of test list: $ID"

# --- 3) Read content (m3u)
sag "3) Read content (export/m3u)"
curl -s "${H[@]}" "$API/playlist/$ID/export/m3u" | nl

# --- 4) Add titles (import as m3u)
sag "4) Add titles (POST playlist/{id}/import)"
printf '%s\n' "$P3" > /tmp/extend.m3u
curl -s -X POST "${H[@]}" -F "playlist_file=@/tmp/extend.m3u;filename=extend.m3u" \
  "$API/playlist/$ID/import" | head -c 300
echo
echo " Content afterwards:"
curl -s "${H[@]}" "$API/playlist/$ID/export/m3u" | nl

# --- 5) Empty
sag "5) Empty list (POST playlist/{id}/empty)"
curl -s -X POST "${H[@]}" "$API/playlist/$ID/empty" | head -c 200
echo
echo " Content afterwards: $(curl -s"${H[@]}" "$API/playlist/$ID/export/m3u" | wc -l) lines"

# --- 6) Rename (GET, then complete object PUT)
sag "6) Rename (GET -> PUT with complete object)"
curl -s "${H[@]}" "$API/playlist/$ID" > /tmp/list.json
python3 -c "
import json
d = json.load(open('/tmp/list.json'))
print(' Fields:', len(d), '| Name:', d.get('name'))
json.dump(d, open('/tmp/list-new.json','w'))
" 
python3 -c "
import json
d = json.load(open('/tmp/list-new.json'))
d['name'] = 'Test run Bot 2'
json.dump(d, open('/tmp/list-new.json','w'), ensure_ascii=False)
"
curl -s -X PUT "${H[@]}" -H 'Content-Type: application/json' \
  --data-binary @/tmp/list-new.json "$API/playlist/$ID" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(' new name:', d.get('name'))
"

# --- 7) Delete
sag "7) Delete (DELETE playlist/{id})"
curl -s -o /dev/null -w ' HTTP %{http_code}\n' -X DELETE "${H[@]}" "$API/playlist/$ID"
echo " Lists now:"
curl -s "${H[@]}" "$API/playlists" | python3 -c "
import json,sys
for p in json.load(sys.stdin): print(f\"    id={p['id']}  {p['name']!r}  title={p.get('num_songs')}\")
"
