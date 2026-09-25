##!/bin/bash
# Checks which fields a PUT needs to rename a playlist.
set -uo pipefail

SSH="ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 root@192.168.178.163"
API=http://192.168.178.33/api/station/1
K=$($SSH 'pct exec 106 -- docker exec azuracast cat /var/azuracast/api_key.txt')
H=(-H "X-API-Key: $K")
NAME="Rename test $RANDOM"

PFAD=$(curl -s "${H[@]}" "$API/files?rowCount=1&searchPhrase=Juliet" | python3 -c "
import json,sys; print(json.load(sys.stdin)['rows'][0]['path'])")

echo "=== Creating test list: $NAME ==="
curl -s -X PUT "${H[@]}" -H 'Content-Type: application/json' "$API/files/batch" \
  -d "$(python3 -c "
import json,sys
print(json.dumps({'do':'playlist','files':[sys.argv[1]],'playlists':['new'],
                  'new_playlist_name':sys.argv[2]}))" "$PFAD" "$NAME")" > /dev/null

ID=$(curl -s "${H[@]}" "$API/playlists" | python3 -c "
import json,sys
for p in json.load(sys.stdin):
    if p['name'] == '''$NAME''': print(p['id']); break")
echo " ID: $ID"

curl -s "${H[@]}" "$API/playlist/$ID" > /tmp/obj.json
echo " Fields in GET: $(python3 -c"import json;print(len(json.load(open('/tmp/obj.json'))))")"

probe() {   # test <name> <selection-JSON-filter>
  local name="$1"; shift
  python3 - "$1" "$ID" <<'PY' > /tmp/put.json
import json, sys
core = {"name", "type", "source", "order", "is_enabled", "weight", "backend_options",
        "play_per_songs", "play_per_minutes", "play_per_hour_minute", "include_in_requests",
        "include_in_on_demand", "avoid_duplicates", "playback_order", "schedule_items"}
obj = json.load(open('/tmp/obj.json'))
type, pid = sys.argv[1], sys.argv[2]
if type == "everything":
    body = dict(obj)
elif type == "ohne_podcasts":
    body = {k: v for k, v in obj.items() if k not in ("podcasts", "left")}
elif type == "core":
    body = {k: v for k, v in obj.items() if k in core}
body["name"] = "test " + type
print(json.dumps(body, ensure_ascii=False))
PY
  curl -s -o /tmp/answer.json -w " %-16s HTTP %{http_code}" "$1" -X PUT "${H[@]}" \
    -H 'Content-Type: application/json' --data-binary @/tmp/put.json "$API/playlist/$ID"
  local now
  now=$(curl -s "${H[@]}" "$API/playlists" | python3 -c "
import json,sys
for p in json.load(sys.stdin):
    if p['id'] == $ID: print(repr(p['name']))")
  printf 'Name now: %-28s %s\n' "$now" "$(head -c 120 /tmp/answer.json | tr -d '\n')"
}

echo "=== PUT variants ==="
probe "ohne_podcasts" ohne_podcasts
probe "core" core
probe "everything" everything

echo "=== Cleanup ==="
curl -s -o /dev/null -w ' DELETE: HTTP %{http_code}\n' -X DELETE "${H[@]}" "$API/playlist/$ID"
curl -s "${H[@]}" "$API/playlists" | python3 -c "
import json,sys
print(' Lists now:', [(p['id'], p['name']) for p in json.load(sys.stdin)])"
