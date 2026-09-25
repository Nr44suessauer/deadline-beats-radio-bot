#!/usr/bin/env python3
"""
stimmen_dienst.py — Auftrags-Dienst fuer die Stimmen-Extraktion aus Filmen/Serien (CT 111).

Steuert die vorhandene Pipeline im Applio-Container:
  * prep_dataset.py     Video -> ffmpeg -> Demucs (Stimmen trennen) -> Sprach-Schnipsel -> Dataset
  * cluster_speakers.py Sprecher-Embeddings (ECAPA) -> Segmente nach Sprecher in cluster_0/... legen

Endpunkte (alle ausser /status mit Schluessel: ?schluessel=... oder Kopf X-Schluessel):
  GET  /status      Dienst- und Auftragszustand
  GET  /finden      ?wort=...   Serie/Film in den Bibliotheken suchen
  GET  /datasets                vorhandene Datasets (Segmente, Minuten, Sprecher-Cluster)
  GET  /job                     laufender/letzter Auftrag inkl. Log-Ende
  POST /extrahieren {serie|quelle, name, folgen?, max_secs?, min_db?, trennen?}
  POST /trennen     {name, n_clusters?}

Es laeuft immer nur EIN Auftrag. Zustand:  /var/lib/stimmen-dienst/job.json
Logs:                                       /var/log/stimmen/<name>-<zeitstempel>.log
Schluessel:                                 /opt/Applio/stimmen-dienst/schluessel.txt
Start:  /opt/Applio/.venv/bin/python /opt/Applio/stimmen-dienst/stimmen_dienst.py --port 8890
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import threading
import wave
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request

VENV_PY = "/opt/Applio/.venv/bin/python"
PREP = "/opt/Applio/pipeline/prep_dataset.py"
CLUSTER = "/opt/Applio/pipeline/cluster_speakers.py"
ARBEIT = "/opt/Applio"
DATASETS = os.path.join(ARBEIT, "assets", "datasets")
BIBLIOTHEKEN = ["/media/disk1", "/media/Content"]        # /media/Content ist derzeit leer
LOGDIR = "/var/log/stimmen"
STATUS_DIR = "/var/lib/stimmen-dienst"
JOB_DATEI = os.path.join(STATUS_DIR, "job.json")
SCHLUESSEL_DATEI = "/opt/Applio/stimmen-dienst/schluessel.txt"
VIDEO_ENDUNGEN = ("*.mkv", "*.mp4", "*.avi", "*.mov", "*.wmv", "*.ts", "*.m4v", "*.flv")
NAME_MUSTER = re.compile(r"^[A-Za-z0-9_.-]{2,40}$")

app = FastAPI(title="Stimmen-Dienst", version="1.0")
_sperre = threading.Lock()
_prozess: subprocess.Popen | None = None      # laufender Unterprozess (zum Abbrechen)


# ------------------------------------------------------------------ Hilfen

def schluessel_lesen() -> str:
    try:
        return Path(SCHLUESSEL_DATEI).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def pruefe(request: Request) -> None:
    erwartet = schluessel_lesen()
    if not erwartet:
        return  # ohne Schluesseldatei bleibt der Dienst offen (nur Startphase)
    gegeben = request.query_params.get("schluessel") or request.headers.get("x-schluessel", "")
    if gegeben != erwartet:
        raise HTTPException(status_code=401, detail="Schluessel fehlt oder passt nicht.")


def jetzt() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def job_laden() -> dict | None:
    try:
        return json.loads(Path(JOB_DATEI).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def job_speichern(daten: dict) -> None:
    os.makedirs(STATUS_DIR, exist_ok=True)
    tmp = JOB_DATEI + ".tmp"
    Path(tmp).write_text(json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, JOB_DATEI)


def videos_zaehlen(pfad: str) -> int:
    if os.path.isfile(pfad):
        return 1
    anzahl = 0
    for endung in VIDEO_ENDUNGEN:
        anzahl += len(glob.glob(os.path.join(pfad, "**", endung), recursive=True))
    return anzahl


def finden(wort: str) -> list[dict]:
    """Serie/Film in den Bibliotheken suchen: Ordnernamen, die das Wort enthalten."""
    w = wort.strip()
    treffer: list[dict] = []
    if os.path.isabs(w) and os.path.exists(w):
        treffer.append({"pfad": w, "art": "ordner" if os.path.isdir(w) else "datei",
                        "videos": videos_zaehlen(w)})
        return treffer
    suche = w.casefold()
    for wurzel in BIBLIOTHEKEN:
        if not os.path.isdir(wurzel):
            continue
        for tiefe in range(1, 5):
            muster = os.path.join(wurzel, *(["*"] * tiefe))
            for ordner in glob.glob(muster):
                if not os.path.isdir(ordner):
                    continue
                if suche in os.path.basename(ordner).casefold():
                    treffer.append({"pfad": ordner, "art": "ordner",
                                    "videos": videos_zaehlen(ordner)})
                if len(treffer) >= 12:
                    return treffer
    return treffer


def dataset_info(name: str) -> dict:
    """Segmente, Gesamtlaenge und Sprecher-Cluster eines Datasets."""
    ordner = os.path.join(DATASETS, name)
    if not os.path.isdir(ordner):
        return {}
    def segmente_in(pfad: str) -> tuple[int, float]:
        dateien = sorted(glob.glob(os.path.join(pfad, "*.wav")))
        sekunden = 0.0
        for d in dateien:
            try:
                with wave.open(d, "rb") as w:
                    sekunden += w.getnframes() / float(w.getframerate())
            except (wave.Error, OSError):
                pass
        return len(dateien), round(sekunden / 60.0, 1)
    anzahl, minuten = segmente_in(ordner)
    cluster = {}
    for unter in sorted(glob.glob(os.path.join(ordner, "cluster_*"))):
        if os.path.isdir(unter):
            n, m = segmente_in(unter)
            cluster[os.path.basename(unter)] = {"segmente": n, "minuten": m}
    return {"name": name, "pfad": ordner, "segmente": anzahl, "minuten": minuten,
            "cluster": cluster}


def log_ende(pfad: str, zeilen: int = 6) -> list[str]:
    try:
        daten = Path(pfad).read_text(encoding="utf-8", errors="ignore").splitlines()
        return daten[-zeilen:]
    except OSError:
        return []


def job_aktuell() -> dict:
    daten = job_laden() or {}
    name = daten.get("name")
    if name:
        info = dataset_info(name)
        if info:
            daten["fortschritt"] = {k: info[k] for k in ("segmente", "minuten", "cluster")}
        if daten.get("log"):
            daten["log_ende"] = log_ende(daten["log"])
    return daten


# ------------------------------------------------------------------ Auftrag

def _lauf(aufgabe: dict, schritte: list[list[str]]) -> None:
    """Hintergrundlauf: fuehrt die Schritte nacheinander aus und pflegt den Zustand."""
    global _prozess
    logpfad = aufgabe["log"]
    try:
        with open(logpfad, "a", encoding="utf-8") as log:
            for schritt, cmd in schritte:
                aufgabe["schritt"] = schritt
                job_speichern(aufgabe)
                log.write(f"\n===== {jetzt()}  {schritt}: {' '.join(cmd)}\n")
                log.flush()
                _prozess = subprocess.Popen(cmd, cwd=ARBEIT, stdout=log,
                                            stderr=subprocess.STDOUT)
                rc = _prozess.wait()
                _prozess = None
                if rc != 0:
                    if aufgabe.get("status") == "abgebrochen":
                        break
                    aufgabe["status"] = "fehler"
                    aufgabe["meldung"] = (f"Schritt '{schritt}' brach ab "
                                          f"(Rueckgabewert {rc}).")
                    break
            else:
                aufgabe["status"] = "fertig"
        if "meldung" not in aufgabe:
            aufgabe["ergebnis"] = dataset_info(aufgabe["name"])
    except Exception as fehler:  # noqa: BLE001 — Dienst soll nie sterben
        aufgabe["status"] = "fehler"
        aufgabe["meldung"] = f"Ausnahme: {fehler}"
    aufgabe["schritt"] = None
    aufgabe["ende"] = jetzt()
    job_speichern(aufgabe)


def auftrag_starten(aufgabe: dict, schritte: list[list[str]]) -> dict:
    global _sperre
    with _sperre:
        alt = job_laden() or {}
        if alt.get("status") == "laufend":
            raise HTTPException(status_code=409, detail=f"Es laeuft schon ein Auftrag: {alt.get('name')}")
        os.makedirs(LOGDIR, exist_ok=True)
        stempel = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        aufgabe["log"] = os.path.join(LOGDIR, f"{aufgabe['name']}-{stempel}.log")
        aufgabe["status"] = "laufend"
        aufgabe["start"] = jetzt()
        aufgabe["ende"] = None
        job_speichern(aufgabe)
        threading.Thread(target=_lauf, args=(aufgabe, schritte), daemon=True).start()
    return aufgabe


# ------------------------------------------------------------------ Endpunkte

@app.get("/status")
def status_ep() -> dict:
    daten = job_aktuell()
    return {"ok": True, "dienst": "stimmen", "version": "1.0",
            "schluessel_gesetzt": bool(schluessel_lesen()),
            "job": {"status": daten.get("status"), "art": daten.get("art"),
                    "name": daten.get("name")} if daten else None}


@app.get("/job")
def job_ep(request: Request) -> dict:
    pruefe(request)
    return job_aktuell()


@app.get("/finden")
def finden_ep(wort: str, request: Request) -> dict:
    pruefe(request)
    if not wort.strip():
        raise HTTPException(status_code=400, detail="Feld 'wort' fehlt.")
    return {"wort": wort, "treffer": finden(wort)}


@app.get("/datasets")
def datasets_ep(request: Request) -> dict:
    pruefe(request)
    if not os.path.isdir(DATASETS):
        return {"datasets": []}
    namen = sorted(d for d in os.listdir(DATASETS) if os.path.isdir(os.path.join(DATASETS, d)))
    return {"datasets": [dataset_info(n) for n in namen]}


@app.post("/extrahieren")
async def extrahieren_ep(request: Request) -> dict:
    pruefe(request)
    daten = await request.json()
    quelle = str(daten.get("serie") or daten.get("quelle") or "").strip()
    name = str(daten.get("name") or "").strip()
    if not name or not NAME_MUSTER.match(name):
        raise HTTPException(status_code=400, detail="Feld 'name' fehlt oder enthaelt unerlaubte Zeichen (erlaubt: a-z, A-Z, 0-9, . _ -, 2-40 Zeichen).")
    if not quelle:
        raise HTTPException(status_code=400, detail="Feld 'serie' fehlt (Serie/Film oder Pfad).")

    ziel = os.path.join(DATASETS, name)
    if os.path.isdir(ziel) and glob.glob(os.path.join(ziel, "**", "*"), recursive=True):
        raise HTTPException(status_code=412, detail=f"Dataset '{name}' existiert schon — bitte anderen Namen waehlen.")

    if not os.path.exists(quelle):
        treffer = finden(quelle)
        if not treffer:
            raise HTTPException(status_code=404, detail=f"Nichts gefunden zu '{quelle}'.")
        if len(treffer) > 1:
            raise HTTPException(status_code=409, detail={
                "meldung": f"Mehrere Treffer zu '{quelle}' — bitte genauer angeben.",
                "treffer": [t["pfad"] for t in treffer[:12]]})
        quelle = treffer[0]["pfad"]
    if videos_zaehlen(quelle) == 0:
        raise HTTPException(status_code=404, detail=f"Keine Videodateien unter '{quelle}'.")

    folgen_roh = daten.get("folgen")
    folgen_text = "" if folgen_roh is None else str(folgen_roh).strip()
    try:
        folgen = 1 if folgen_text == "" else max(0, int(folgen_text))
    except ValueError:
        raise HTTPException(status_code=400, detail="Feld 'folgen' muss eine Zahl sein (0 = alle Folgen).")
    trennen = str(daten.get("trennen", "ja")).strip().lower() in ("ja", "true", "1", "yes")

    cmd = [VENV_PY, PREP, "--source", quelle, "--name", name]
    if folgen > 0:
        cmd += ["--limit", str(folgen)]
    for feld, arg in (("max_secs", "--max-secs"), ("min_db", "--min-db"), ("modell", "--model")):
        wert = str(daten.get(feld) or "").strip()
        if wert:
            cmd += [arg, wert]

    schritte = [["schneiden", cmd]]
    if trennen:
        schritte.append(["trennen", [VENV_PY, CLUSTER, "--dataset", ziel]])

    aufgabe = {"art": "extrahieren", "name": name, "quelle": quelle,
               "folgen": folgen, "trennen": trennen}
    auftrag_starten(aufgabe, schritte)
    return {"gestartet": True, "name": name, "quelle": quelle, "trennen": trennen,
            "log": aufgabe["log"]}


@app.post("/trennen")
async def trennen_ep(request: Request) -> dict:
    pruefe(request)
    daten = await request.json()
    name = str(daten.get("name") or "").strip()
    ziel = os.path.join(DATASETS, name)
    if not name or not os.path.isdir(ziel):
        raise HTTPException(status_code=404, detail=f"Dataset '{name}' gibt es nicht.")
    if not glob.glob(os.path.join(ziel, "*.wav")):
        raise HTTPException(status_code=412, detail="Keine Segmente zum Trennen gefunden (schon getrennt?).")
    cmd = [VENV_PY, CLUSTER, "--dataset", ziel]
    if str(daten.get("n_clusters") or "").strip():
        cmd += ["--n-clusters", str(int(daten["n_clusters"]))]
    aufgabe = {"art": "trennen", "name": name, "quelle": ziel}
    auftrag_starten(aufgabe, [["trennen", cmd]])
    return {"gestartet": True, "name": name, "log": aufgabe["log"]}


@app.post("/abbrechen")
def abbrechen_ep(request: Request) -> dict:
    pruefe(request)
    daten = job_laden() or {}
    if daten.get("status") != "laufend":
        return {"abgebrochen": False, "meldung": "Es laeuft kein Auftrag."}
    daten["status"] = "abgebrochen"
    daten["meldung"] = "Vom Nutzer abgebrochen."
    daten["ende"] = jetzt()
    job_speichern(daten)
    if _prozess is not None and _prozess.poll() is None:
        try:
            _prozess.kill()
        except OSError:
            pass
    return {"abgebrochen": True, "name": daten.get("name")}


def main() -> None:
    parser = argparse.ArgumentParser(description="Stimmen-Dienst (Film/Serie -> RVC-Dataset)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8890)
    args = parser.parse_args()
    # Beim Start: einen nach einem Absturz/Neustart haengengebliebenen Lauf als abgebrochen kennzeichnen
    alt = job_laden()
    if alt and alt.get("status") == "laufend":
        alt["status"] = "abgebrochen"
        alt["meldung"] = "Dienst wurde neu gestartet."
        alt["ende"] = jetzt()
        job_speichern(alt)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
