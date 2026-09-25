#!/usr/bin/env bash
# Disables the blocking period for music requests (request_threshold = 0).
set -u
KEY=$(cat /tmp/.azkey)
curl -s -H "X-API-Key: $KEY" http://192.168.178.33/api/admin/station/1 -o /tmp/station-before.json

python3 - <<'PY'
import json
d = json.load(open('/tmp/station-before.json'))
print('before: request_threshold =', d.get('request_threshold'), '| request_delay =', d.get('request_delay'))
d['request_threshold'] = 0
# Backup of the old version
json.dump(d, open('/tmp/station-new.json', 'w'))
PY

curl -s -X PUT -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  --data-binary @/tmp/station-new.json http://192.168.178.33/api/admin/station/1 | head -c 200; echo

echo "--- Check:"
curl -s -H "X-API-Key: $KEY" http://192.168.178.33/api/admin/station/1 | python3 -c "
import json,sys
d = json.load(sys.stdin)
for k in ('enable_requests', 'request_threshold', 'request_delay', 'enable_streamers', 'name'):
    print('  ', k, '=', d.get(k))
"
echo "--- Test: is the stream still running?"
curl -s http://192.168.178.33/api/nowplaying/1 | python3 -c "
import json,sys
n = json.load(sys.stdin)['now_playing']
print('  ', n['song']['text'][:50])
"
