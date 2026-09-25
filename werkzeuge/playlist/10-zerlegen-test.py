#!/usr/bin/env python3
"""Prueft die Auftragserkennung des Listen-Moduls - ohne Dienst und ohne Netz.

Die Abhaengigkeiten von FastAPI/Pydantic werden durch Attrappen ersetzt, damit
das Modul lokal importiert werden kann.

Aufruf:  python3 10-zerlegen-test.py
"""
import sys
import types
from pathlib import Path

# ---- Attrappen, damit playlist.py lokal importierbar ist
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

sys.path.insert(0, "<dokuordner>/dienst")
import playlist  # noqa: E402

FAELLE = [
    ("welche Wiedergabelisten gibt es", "listen", "", ""),
    ("zeige mir die Listen", "listen", "", ""),
    ("baue eine Playlist Sommer aus Scooter", "bauen", "Sommer", "Scooter"),
    ("erzeuge eine playlist namens Sommer mit Scooter", "bauen", "Sommer", "Scooter"),
    ("baue eine playlist aus scooter", "bauen", "scooter", "scooter"),
    ("mach mir eine playlist 90er hits", "bauen", "90er hits", "90er hits"),
    ("spiele die Playlist Sommer", "abspielen", "Sommer", ""),
    ("starte die Liste Sommer 2026", "abspielen", "Sommer 2026", ""),
    ("spiele eine playlist", "abspielen", "", ""),
    ("was ist in der Playlist Sommer", "ansehen", "Sommer", ""),
    ("zeige den Inhalt der Liste List A", "ansehen", "List A", ""),
    ("benenne die Playlist Sommer in Sommer 2026 um", "umbenennen", "Sommer", ""),
    ("leere die Playlist Sommer", "leeren", "Sommer", ""),
    ("loesche die Playlist Sommer", "loeschen", "Sommer", ""),
    ("nimm Hyper Hyper in die Playlist Sommer", "ergaenzen", "Sommer", "Hyper Hyper"),
    ("entferne Hyper Hyper aus der Playlist Sommer", "titel_entfernen", "Sommer", ""),
    ("mach irgendwas mit dem Sender", "unklar", "", ""),
    ("spiele Benzin", "unklar", "", ""),
]

gut = 0
for text, art, name, kriterium in FAELLE:
    auftrag = playlist.auftrag_lesen(text)
    ist = (auftrag.get("art"), auftrag.get("name", ""), auftrag.get("kriterium", ""))
    soll = (art, name, kriterium)
    ok = ist == soll
    gut += ok
    print(("ok   " if ok else "ABW. ") + f'"{text}"')
    if not ok:
        print(f"        ist : {ist}")
        print(f"        soll: {soll}")

print(f"\n{gut} von {len(FAELLE)} wie erwartet")

# Zusatzprobe: neuer Name beim Umbenennen
for text, soll in [("benenne die Playlist Sommer in Sommer 2026 um", "Sommer 2026"),
                   ("nenne die liste List A in Best of um", "Best of")]:
    ist = playlist._neuer_name(text)
    print(("ok   " if ist == soll else "ABW. ") + f'neuer Name aus "{text}" -> "{ist}"')

# Zusatzprobe: "und spiele sie" soll nach dem Anlegen gleich starten
for text, soll in [("baue eine playlist aus scooter und spiele sie", True),
                   ("erstelle eine playlist 90er und lass sie gleich laufen", True),
                   ("baue eine playlist Sommer aus Scooter", False),
                   ("spiele die Playlist Sommer", False),
                   ("was ist in der Playlist Sommer", False)]:
    ist = bool(playlist.auftrag_lesen(text).get("danach_spielen"))
    print(("ok   " if ist == soll else "ABW. ") + f'danach spielen aus "{text}" -> {ist}')

# Zusatzprobe: die Absicht am Ende gehoert nicht in den Suchbegriff
for text, name, kriterium in [
    ("baue eine playlist Probe aus Scooter und spiele sie", "Probe", "Scooter"),
    ("baue eine playlist aus Scooter und spiele sie", "Scooter", "Scooter"),
    ("erstelle eine playlist 90er aus Scooter sofort", "90er", "Scooter"),
    ("baue eine playlist aus Scooter und Rammstein", "Scooter und Rammstein", "Scooter und Rammstein"),
]:
    a = playlist.auftrag_lesen(text)
    ist = (a.get("name"), a.get("kriterium"))
    ok = ist == (name, kriterium)
    print(("ok   " if ok else "ABW. ") + f'"{text}" -> {ist}' + ("" if ok else f"  soll: {(name, kriterium)}"))
