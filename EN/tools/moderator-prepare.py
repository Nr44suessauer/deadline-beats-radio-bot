#!/usr/bin/env python3
"""Bring the moderator workflow into order:
- Expressions in addresses with '=' (otherwise n8n does not evaluate them)
- Search phrase as actual query parameter instead of raw in the address
- Write import file in the expected format
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
    if n['name'] == 'Find title':
        before = p.get('url', '')
        p['url'] = AZ + '/api/station/1/files'
        p['sendQuery'] = True
        p['queryParameters'] = {'parameters': [
            {'name': 'rowCount', 'value': '5'},
            {'name': 'searchPhrase',
             'value': "={{ $('Filename').first().json.filename.replace(/\\.[a-z0-9]+$/i, '') }}"},
        ]}
        print('Find title:')
        print(' before :', before[:110])
        print(' afterwards:', p['url'], '| searchPhrase =',
              p['queryParameters']['parameters'][1]['value'])

for n in d['nodes']:
    u = n['parameters'].get('url')
    if isinstance(u, str) and '{{' in u and not u.startswith('='):
        n['parameters']['url'] = '=' + u
        print('fixed:', n['name'], '->', n['parameters']['url'][:90])

# --- Select search hits: /files returns {rows:[...]}, Assigning needs a title.
hits = {
    'parameters': {'jsCode': """// Take out the first search hit - assignment and submitting the wish need it.
const raw = $input.first().json || {};
if (raw.error) return [{ json: { error: 'The station is not responding right now.' } }];
const lines = raw.rows || raw.data || (Array.isArray(raw) ? raw : []);
if (!lines.length) return [{ json: { error: 'Kein Titel to the Announcements found.' } }];
return [{ json: lines[0] }];
"""}, 'name': 'hits choose', 'type': 'n8n-nodes-base.code', 'typeVersion': 2,
    'position': [700, 1000], 'id': 'hits-choose',
}

if not any(n['name'] == 'Select hit' for n in d['nodes']):
    d['nodes'].append(hits)
    d['connections']['Find title'] = {'main': [[{'node': 'Select hit', 'type': 'main', 'index': 0}]]}
    d['connections']['Select hit'] = {'main': [[{'node': 'Zuordnen', 'type': 'main', 'index': 0}]]}
    print('Node "Select hits" inserted')

for n in d['nodes']:
    if n['name'] == 'Zuordnen':
        n['parameters']['url'] = "={{ 'http://192.168.178.33/api/station/1/file/' + $json.id }}"
        n.setdefault('onError', 'continueRegularOutput')
        print('Assign:', n['parameters']['url'])
    if n['name'] == 'Place wish':
        n['parameters']['url'] = ("={{ 'http://192.168.178.33/api/station/1/request/'"
                                  " + $('hits choose').first().json.unique_id }}")
        n.setdefault('onError', 'continueRegularOutput')
        print('Submit request:', n['parameters']['url'])

d['active'] = False
d['versionId'] = str(uuid.uuid4())

vorlage = json.load(open('/tmp/radio-telegram-import.json', encoding='utf-8'))[0]
entry = {
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
json.dump([entry], open(ZIEL, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('written:', ZIEL, '| Node:', len(entry['nodes']))
