#!/usr/bin/env python3
"""Bringt den Moderator-Workflow in Ordnung:
- Ausdruecke in Adressen mit '=' (sonst wertet n8n sie nicht aus)
- Suchphrase als echten Abfrageparameter statt roh in der Adresse
- Importdatei im erwarteten Format schreiben
"""
import json
import uuid

QUELLE = '/tmp/moderator.json'
ZIEL = '/tmp/moderator-import.json'

d = json.load(open(QUELLE, encoding='utf-8'))
d = d[0] if isinstance(d, list) else d

AZ = 'http://192.168.178.33'

for n in d['nodes']:
    p = n['parameters']
    if n['name'] == 'Titel finden':
        vorher = p.get('url', '')
        p['url'] = AZ + '/api/station/1/files'
        p['sendQuery'] = True
        p['queryParameters'] = {'parameters': [
            {'name': 'rowCount', 'value': '5'},
            {'name': 'searchPhrase',
             'value': "={{ $('Dateiname').first().json.dateiname.replace(/\\.[a-z0-9]+$/i, '') }}"},
        ]}
        print('Titel finden:')
        print('  vorher :', vorher[:110])
        print('  nachher:', p['url'], '| searchPhrase =',
              p['queryParameters']['parameters'][1]['value'])

for n in d['nodes']:
    u = n['parameters'].get('url')
    if isinstance(u, str) and '{{' in u and not u.startswith('='):
        n['parameters']['url'] = '=' + u
        print('repariert:', n['name'], '->', n['parameters']['url'][:90])

# --- Suchtreffer auswaehlen: /files liefert {rows:[...]}, Zuordnen braucht einen Titel.
treffer = {
    'parameters': {'jsCode': """// Ersten Suchtreffer herausnehmen - Zuordnen und Wunsch abgeben brauchen ihn.
const roh = $input.first().json || {};
if (roh.error) return [{ json: { fehler: 'Der Sender antwortet gerade nicht.' } }];
const zeilen = roh.rows || roh.data || (Array.isArray(roh) ? roh : []);
if (!zeilen.length) return [{ json: { fehler: 'Kein Titel zum Ansagen gefunden.' } }];
return [{ json: zeilen[0] }];
"""}, 'name': 'Treffer waehlen', 'type': 'n8n-nodes-base.code', 'typeVersion': 2,
    'position': [700, 1000], 'id': 'treffer-waehlen',
}

if not any(n['name'] == 'Treffer waehlen' for n in d['nodes']):
    d['nodes'].append(treffer)
    d['connections']['Titel finden'] = {'main': [[{'node': 'Treffer waehlen', 'type': 'main', 'index': 0}]]}
    d['connections']['Treffer waehlen'] = {'main': [[{'node': 'Zuordnen', 'type': 'main', 'index': 0}]]}
    print('Knoten "Treffer waehlen" eingefuegt')

for n in d['nodes']:
    if n['name'] == 'Zuordnen':
        n['parameters']['url'] = "={{ 'http://192.168.178.33/api/station/1/file/' + $json.id }}"
        n.setdefault('onError', 'continueRegularOutput')
        print('Zuordnen:', n['parameters']['url'])
    if n['name'] == 'Wunsch abgeben':
        n['parameters']['url'] = ("={{ 'http://192.168.178.33/api/station/1/request/'"
                                  " + $('Treffer waehlen').first().json.unique_id }}")
        n.setdefault('onError', 'continueRegularOutput')
        print('Wunsch abgeben:', n['parameters']['url'])

d['active'] = False
d['versionId'] = str(uuid.uuid4())

vorlage = json.load(open('/tmp/radio-telegram-import.json', encoding='utf-8'))[0]
eintrag = {
    'id': d['id'],
    'name': d['name'],
    'nodes': d['nodes'],
    'connections': d['connections'],
    'settings': d.get('settings', {'executionOrder': 'v1'}),
    'staticData': d.get('staticData'),
    'active': False,
    'versionId': d['versionId'],
    'createdAt': vorlage['createdAt'],
    'updatedAt': vorlage['updatedAt'],
    'description': '',
    'isArchived': False,
}
json.dump([eintrag], open(ZIEL, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('geschrieben:', ZIEL, '| Knoten:', len(eintrag['nodes']))
