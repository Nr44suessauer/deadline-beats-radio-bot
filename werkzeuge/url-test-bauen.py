#!/usr/bin/env python3
"""Minimaler Test: loest n8n Ausdruecke in der URL eines HTTP-Knotens auf?"""
import json
import os

AZ = "http://192.168.178.33"
KEY = os.environ["AZ_KEY"]

kopf = [{"name": "X-API-Key", "value": KEY}]


def http(name, methode, url, pos, rumpf=None):
    p = {"method": methode, "url": url, "sendHeaders": True,
         "headerParameters": {"parameters": kopf}}
    if rumpf is not None:
        p["sendBody"] = True
        p["specifyBody"] = "json"
        p["jsonBody"] = rumpf
    return {"parameters": p, "name": name, "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2, "position": pos, "id": f"n{name}",
            "onError": "continueRegularOutput"}


knoten = [
    {"parameters": {"httpMethod": "POST", "path": "radio-url-test", "responseMode": "lastNode",
                    "options": {}},
     "name": "Eingang", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
     "position": [0, 0], "id": "w1", "webhookId": "radio-url-test"},
    {"parameters": {"jsCode": "return [{ json: { id: 5619, unique_id: '5a144d96844fec001d6e9065' } }];"},
     "name": "Felder", "type": "n8n-nodes-base.code", "typeVersion": 2,
     "position": [220, 0], "id": "c1"},
    # A: klassischer Ausdruck mitten in der URL
    http("A klassisch", "PUT", AZ + "/api/station/1/file/{{ $('Felder').first().json.id }}",
         [440, -100], "={{ JSON.stringify({ playlists: [8, 9] }) }}"),
    # B: vollstaendiger Ausdruck (mit = davor)
    http("B voll", "PUT",
         "={{ 'http://192.168.178.33/api/station/1/file/' + $('Felder').first().json.id }}",
         [440, 80], "={{ JSON.stringify({ playlists: [8, 9] }) }}"),
    # C: Bezug auf das laufende Element
    http("C json", "PUT", AZ + "/api/station/1/file/{{ $json.id }}",
         [440, 260], "={{ JSON.stringify({ playlists: [8, 9] }) }}"),
    {"parameters": {"jsCode": """
const hole = (name) => {
  try {
    const j = $(name).first().json;
    return j.success ? 'OK' : ('Fehler: ' + (j.message || JSON.stringify(j.error || j).slice(0, 120)));
  } catch (e) { return 'Ausnahme: ' + e.message; }
};
return [{ json: { A_klassisch: hole('A klassisch'), B_voll: hole('B voll'), C_json: hole('C json') } }];
"""},
     "name": "Ergebnis", "type": "n8n-nodes-base.code", "typeVersion": 2,
     "position": [660, 80], "id": "c9"},
]

verbindungen = {
    "Eingang": {"main": [[{"node": "Felder", "type": "main", "index": 0}]]},
    "Felder": {"main": [[{"node": "A klassisch", "type": "main", "index": 0}]]},
    "A klassisch": {"main": [[{"node": "B voll", "type": "main", "index": 0}]]},
    "B voll": {"main": [[{"node": "C json", "type": "main", "index": 0}]]},
    "C json": {"main": [[{"node": "Ergebnis", "type": "main", "index": 0}]]},
}

wf = [{
    "id": "UrlTestWorkflow",
    "name": "Test - URL-Ausdruck",
    "nodes": knoten,
    "connections": verbindungen,
    "settings": {"executionOrder": "v1"},
    "active": False,
    "versionId": "test-url-1",
    "createdAt": "2026-09-19T00:00:00.000Z",
    "updatedAt": "2026-09-19T00:00:00.000Z",
    "description": "",
    "isArchived": False,
}]

with open("/tmp/url-test.json", "w", encoding="utf-8") as f:
    json.dump(wf, f, ensure_ascii=False, indent=2)
print("geschrieben: /tmp/url-test.json")
