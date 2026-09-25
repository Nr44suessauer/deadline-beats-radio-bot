#!/bin/bash
# Prueft die Schnittstellenwege fuer die Wiedergabelisten-Aufgaben des Bots
# an einer Testliste (wird am Ende wieder geloescht).
# Aufruf:  bash 05-listenwege-test.sh
set -uo pipefail

DATENSERVER=192.168.178.163
SSH="ssh -o BatchMode=yes -i ~/.ssh/id_ed25519 root@$DATENSERVER"
API=http://192.168.178.33/api/station/1
K=$($SSH 'pct exec 106 -- docker exec azuracast cat /var/azuracast/api_key.txt')
H=(-H "X-API-Key: $K")

sag() { printf '\n=== %s ===\n' "$1"; }

# --- Drei echte Titelpfade aus dem Archiv holen
sag "Titelpfade besorgen"
PFADE=$(curl -s "${H[@]}" "$API/files?rowCount=3&searchPhrase=Juliet" \
        | python3 -c "
import json,sys
d=json.load(sys.stdin)
for r in d.get('rows',[])[:3]: print(r['path'])
")
echo "$PFADE"
P1=$(echo "$PFADE" | sed -n 1p); P2=$(echo "$PFADE" | sed -n 2p); P3=$(echo "$PFADE" | sed -n 3p)

# --- 1) Liste anlegen und in einem Aufruf fuellen
sag "1) Liste anlegen + fuellen (files/batch, playlists=['new'])"
curl -s -X PUT "${H[@]}" -H 'Content-Type: application/json' "$API/files/batch" \
  -d "$(python3 -c "
import json,sys
print(json.dumps({'do':'playlist','files':[sys.argv[1],sys.argv[2]],
                  'playlists':['new'],'new_playlist_name':'Testlauf Bot'}))
" "$P1" "$P2")" | head -c 400
echo

# --- 2) Liste finden
sag "2) Listen auflisten"
LISTE=$(curl -s "${H[@]}" "$API/playlists")
echo "$LISTE" | python3 -c "
import json,sys
for p in json.load(sys.stdin):
    print(f\"  id={p['id']}  {p['name']!r}  titel={p.get('num_songs')}  aktiv={p.get('is_enabled')}\")
"
ID=$(echo "$LISTE" | python3 -c "
import json,sys
for p in json.load(sys.stdin):
    if p['name'] == 'Testlauf Bot': print(p['id']); break
")
echo "  -> Kennung der Testliste: $ID"

# --- 3) Inhalt auslesen (m3u)
sag "3) Inhalt auslesen (export/m3u)"
curl -s "${H[@]}" "$API/playlist/$ID/export/m3u" | nl

# --- 4) Titel ergaenzen (import als m3u)
sag "4) Titel ergaenzen (POST playlist/{id}/import)"
printf '%s\n' "$P3" > /tmp/ergaenzen.m3u
curl -s -X POST "${H[@]}" -F "playlist_file=@/tmp/ergaenzen.m3u;filename=ergaenzen.m3u" \
  "$API/playlist/$ID/import" | head -c 300
echo
echo "  Inhalt danach:"
curl -s "${H[@]}" "$API/playlist/$ID/export/m3u" | nl

# --- 5) Leeren
sag "5) Liste leeren (POST playlist/{id}/empty)"
curl -s -X POST "${H[@]}" "$API/playlist/$ID/empty" | head -c 200
echo
echo "  Inhalt danach: $(curl -s "${H[@]}" "$API/playlist/$ID/export/m3u" | wc -l) Zeilen"

# --- 6) Umbenennen (GET, dann komplettes Objekt PUT)
sag "6) Umbenennen (GET -> PUT mit komplettem Objekt)"
curl -s "${H[@]}" "$API/playlist/$ID" > /tmp/liste.json
python3 -c "
import json
d = json.load(open('/tmp/liste.json'))
print('  Felder:', len(d), '| Name:', d.get('name'))
json.dump(d, open('/tmp/liste-neu.json','w'))
" 
python3 -c "
import json
d = json.load(open('/tmp/liste-neu.json'))
d['name'] = 'Testlauf Bot 2'
json.dump(d, open('/tmp/liste-neu.json','w'), ensure_ascii=False)
"
curl -s -X PUT "${H[@]}" -H 'Content-Type: application/json' \
  --data-binary @/tmp/liste-neu.json "$API/playlist/$ID" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('  neuer Name:', d.get('name'))
"

# --- 7) Loeschen
sag "7) Loeschen (DELETE playlist/{id})"
curl -s -o /dev/null -w '  HTTP %{http_code}\n' -X DELETE "${H[@]}" "$API/playlist/$ID"
echo "  Listen jetzt:"
curl -s "${H[@]}" "$API/playlists" | python3 -c "
import json,sys
for p in json.load(sys.stdin): print(f\"    id={p['id']}  {p['name']!r}  titel={p.get('num_songs')}\")
"
