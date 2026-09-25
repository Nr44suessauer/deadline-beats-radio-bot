#!/usr/bin/env python3
"""Checks the order recognition of the list module - without service and without network.

The dependencies of FastAPI/Pydantic are replaced by dummies, so that
the module can be imported locally.

Call:  python3 10-zerlegen-test.py
"""
import sys
import types
from pathlib import Path

# ---- Dummies, so that playlist.py can be imported locally
fastapi = types.ModuleType("fastapi")


class _Router:
    def post(self, *_a, **_k):
        return lambda f: f

    def get(self, *_a, **_k):
        return lambda f: f


class HTTPException(Exception):
    def __init__(self, status_code=500, detail=""):
        self.status_code, self.detail = status_code, detail


fastapi.APIRouter = _Router
fastapi.HTTPException = HTTPException
sys.modules["fastapi"] = fastapi

pydantic = types.ModuleType("pydantic")


class BaseModel:
    def __init__(self, **felder):
        for k, v in felder.items():
            setattr(self, k, v)


pydantic.BaseModel = BaseModel
pydantic.Field = lambda default="", **_k: default
sys.modules["pydantic"] = pydantic

sys.path.insert(0, "<dokuordner>/service")
import playlist  # noqa: E402

FAELLE = [
    ("which playlists exist", "listen", "", ""),
    ("show me the lists", "listen", "", ""),
    ("build a playlist called Summer from Scooter", "build", "Sommer", "Scooter"),
    ("create a playlist named Summer with Scooter", "build", "Sommer", "Scooter"),
    ("build a playlist from scooter", "build", "scooter", "scooter"),
    ("make me a playlist 90s hits", "build", "90s hits", "90s hits"),
    ("play the playlist Sommer", "playback", "Sommer", ""),
    ("start the list Summer 2026", "playback", "Summer 2026", ""),
    ("play a playlist", "playback", "", ""),
    ("what is in the playlist Sommer", "view", "Sommer", ""),
    ("show the content of the list List A", "view", "List A", ""),
    ("rename the playlist Summer to Summer 2026", "rename", "Sommer", ""),
    ("empty the playlist Summer", "clear", "Sommer", ""),
    ("delete the playlist Summer", "delete", "Sommer", ""),
    ("add Hyper Hyper to the playlist Summer", "extend", "Sommer", "Hyper Hyper"),
    ("remove Hyper Hyper from the playlist Summer", "titel_entfernen", "Sommer", ""),
    ("do something with the station", "unclear", "", ""),
    ("play Gasoline", "unclear", "", ""),
]

good = 0
for text, type, name, criterion in FAELLE:
    job = playlist.auftrag_lesen(text)
    result = (job.get("type"), job.get("name", ""), job.get("criterion", ""))
    expected = (type, name, criterion)
    ok = result == expected
    good += ok
    print(("ok   " if ok else "ABW. ") + f'"{text}"')
    if not ok:
        print(f" is : {result}")
        print(f" should: {expected}")

print(f"\n{good} of {len(FAELLE)} as expected")

# Additional test: new name when renaming
for text, expected in [("rename the playlist Summer to Summer 2026", "Summer 2026"),
                   ("rename the list List A to Best of", "Best of")]:
    result = playlist._neuer_name(text)
    print(("ok   " if result == expected else "ABW. ") + f'new name from "{text}" -> "{result}"')

# Additional test: "and play it" should start immediately after creation
for text, expected in [("build a playlist from scooter and play it", True),
                   ("create a playlist 90s and let it run immediately", True),
                   ("build a playlist Sommer from Scooter", False),
                   ("play the playlist Sommer", False),
                   ("what is in the playlist Sommer", False)]:
    result = bool(playlist.auftrag_lesen(text).get("play_later"))
    print(("ok   " if result == expected else "ABW. ") + f'then play from "{text}" -> {result}')

# Additional test: the intention at the end does not belong in the search term
for text, name, criterion in [
    ("build a playlist test from Scooter and play it", "test", "Scooter"),
    ("build a playlist from Scooter and play it", "Scooter", "Scooter"),
    ("create a playlist 90s from Scooter immediately", "90s", "Scooter"),
    ("build a playlist from Scooter and Rammstein", "Scooter and Rammstein", "Scooter and Rammstein"),
]:
    a = playlist.auftrag_lesen(text)
    result = (a.get("name"), a.get("criterion"))
    ok = result == (name, criterion)
    print(("ok   " if ok else "ABW. ") + f'"{text}" -> {result}' + ("" if ok else f" should: {(name, criterion)}"))
