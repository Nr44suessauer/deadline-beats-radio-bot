#!/usr/bin/env python3
"""Minimal test: does it resolve n8n expressions in the URL of an HTTP node?"""
import json
import os

AZ = "http://192.168.178.33"
KEY = os.environ["AZ_KEY"]

kopf = [{"name": "X-API-Key", "value": KEY}]


def http(name, method, url, pos, body=None):
    p = {"method": method, "url": url, "sendHeaders": True,
         "headerParameters": {"parameters": kopf}}
    if body is not None:
        p["sendBody"] = True
        p["specifyBody"] = "json"
        p["jsonBody"] = body
    return {"parameters": p, "name": name, "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2, "position": pos, "id": f"n{name}",
            "onError": "continueRegularOutput"}


nodes = [
    {"parameters": {"httpMethod": "POST", "path": "radio-url-test", "responseMode": "lastNode",
                    "options": {}},
     "name": "Entry", "type": "n8n-nodes-base.webhook", "typeVersion": 2,
     "position": [0, 0], "id": "w1", "webhookId": "radio-url-test"},
    {"parameters": {"jsCode": "return [{ json: { id: 5619, unique_id: '5a144d96844fec001d6e9065' } }];"},
     "name": "Felder", "type": "n8n-nodes-base.code", "typeVersion": 2,
     "position": [220, 0], "id": "c1"},
    # A: classic expression in the middle of the URL
    http("A classic", "PUT", AZ + "/api/station/1/file/{{ $('Felder').first().json.id }}",
         [440, -100], "={{ JSON.stringify({ playlists: [8, 9] }) }}"),
    # B: complete expression (with = before)
    http("B full", "PUT",
         "={{ 'http://192.168.178.33/api/station/1/file/' + $('Felder').first().json.id }}",
         [440, 80], "={{ JSON.stringify({ playlists: [8, 9] }) }}"),
    # C: reference to the current element
    http("C json", "PUT", AZ + "/api/station/1/file/{{ $json.id }}",
         [440, 260], "={{ JSON.stringify({ playlists: [8, 9] }) }}"),
    {"parameters": {"jsCode": """
const get = (name) => {
 try {
 const j = $(name).first().json;
 return j.success ? 'OK' : ('Error: ' + (j.message || JSON.stringify(j.error || j).slice(0, 120)));
 } catch (e) { return 'Ausnahme: ' + e.message; }
};
return [{ json: { A_klassisch: hole('A classical'), B_voll: hole('B voll'), C_json: hole('C json') } }];
"""},
     "name": "result", "type": "n8n-nodes-base.code", "typeVersion": 2,
     "position": [660, 80], "id": "c9"},
]

verbindungen = {
    "Entry": {"main": [[{"node": "Felder", "type": "main", "index": 0}]]},
    "Felder": {"main": [[{"node": "A classic", "type": "main", "index": 0}]]},
    "A classic": {"main": [[{"node": "B full", "type": "main", "index": 0}]]},
    "B full": {"main": [[{"node": "C json", "type": "main", "index": 0}]]},
    "C json": {"main": [[{"node": "result", "type": "main", "index": 0}]]},
}

wf = [{
    "id": "UrlTestWorkflow",
    "name": "Test - URL expression",
    "nodes": nodes,
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
print("written: /tmp/url-test.json")
