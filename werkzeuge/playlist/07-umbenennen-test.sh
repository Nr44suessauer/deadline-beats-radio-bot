#!/bin/bash
# Prueft, welche Felder ein PUT zum Umbenennen einer Wiedergabeliste braucht.
set -uo pipefail

SSH="ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 root@192.168.178.163"
API=http://192.168.178.33/api/station/1
K=$($SSH 'pct exec 106 -- docker exec azuracast cat /var/azuracast/api_key.txt')
H=(-H "X-API-Key: $K")
NAME="Umbenennen-Test $RANDOM"

PFAD=$(curl -s "${H[@]}" "$API/files?rowCount=1&searchPhrase=Juliet" | python3 -c "
import json,sys; print(json.load(sys.stdin)['rows'][0]['path'])")

echo "=== Testliste anlegen: $NAME ==="
curl -s -X PUT "${H[@]}" -H 'Content-Type: application/json' "$API/files/batch" \
  -d "$(python3 -c "
import json,sys
print(json.dumps({'do':'playlist','files':[sys.argv[1]],'playlists':['new'],
                  'new_playlist_name':sys.argv[2]}))" "$PFAD" "$NAME")" > /dev/null

ID=$(curl -s "${H[@]}" "$API/playlists" | python3 -c "
import json,sys
for p in json.load(sys.stdin):
    if p['name'] == '''$NAME''': print(p['id']); break")
echo "  Kennung: $ID"

curl -s "${H[@]}" "$API/playlist/$ID" > /tmp/obj.json
echo "  Felder im GET: $(python3 -c "import json;print(len(json.load(open('/tmp/obj.json'))))")"

probe() {   # probe <bezeichnung> <auswahl-JSON-Filter>
  local name="$1"; shift
  python3 - "$1" "$ID" <<'PY' > /tmp/put.json
import json, sys
kern = {"name", "type", "source", "order", "is_enabled", "weight", "backend_options",
        "play_per_songs", "play_per_minutes", "play_per_hour_minute", "include_in_requests",
        "include_in_on_demand", "avoid_duplicates", "playback_order", "schedule_items"}
obj = json.load(open('/tmp/obj.json'))
art, pid = sys.argv[1], sys.argv[2]
if art == "alles":
    koerper = dict(obj)
elif art == "ohne_podcasts":
    koerper = {k: v for k, v in obj.items() if k not in ("podcasts", "links")}
elif art == "kern":
    koerper = {k: v for k, v in obj.items() if k in kern}
koerper["name"] = "Probe " + art
print(json.dumps(koerper, ensure_ascii=False))
PY
  curl -s -o /tmp/antwort.json -w "  %-16s HTTP %{http_code}  " "$1" -X PUT "${H[@]}" \
    -H 'Content-Type: application/json' --data-binary @/tmp/put.json "$API/playlist/$ID"
  local jetzt
  jetzt=$(curl -s "${H[@]}" "$API/playlists" | python3 -c "
import json,sys
for p in json.load(sys.stdin):
    if p['id'] == $ID: print(repr(p['name']))")
  printf 'Name jetzt: %-28s %s\n' "$jetzt" "$(head -c 120 /tmp/antwort.json | tr -d '\n')"
}

echo "=== PUT-Varianten ==="
probe "ohne_podcasts" ohne_podcasts
probe "kern" kern
probe "alles" alles

echo "=== Aufraeumen ==="
curl -s -o /dev/null -w '  DELETE: HTTP %{http_code}\n' -X DELETE "${H[@]}" "$API/playlist/$ID"
curl -s "${H[@]}" "$API/playlists" | python3 -c "
import json,sys
print('  Listen jetzt:', [(p['id'], p['name']) for p in json.load(sys.stdin)])"
