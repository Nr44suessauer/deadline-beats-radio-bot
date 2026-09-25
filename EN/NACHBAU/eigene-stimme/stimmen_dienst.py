#!/usr/bin/env python3
"""
stimmen_dienst.py — Order service for voice extraction from movies/series (CT 111).

Controls the existing pipeline in the Applio container:
 * prep_dataset.py     Video -> ffmpeg -> Demucs (separate voices) -> speech snippets -> Dataset
 * cluster_speakers.py Speaker embeddings (ECAPA) -> segments by speaker into cluster_0/...

Endpoints (all except /status with key: ?key=... or header X-Key):
 GET  /status      Service and job status
 GET  /finden      ?word=...   Search for series/movie in the libraries
 GET  /datasets                available datasets (segments, minutes, speaker clusters)
 GET  /job                     running/last job including log end
 POST /extrahieren {serie|source, name, folgen?, max_secs?, min_db?, trennen?}
 POST /trennen     {name, n_clusters?}

Only ONE job runs at a time. Status:  /var/lib/voices-service/job.json
Logs:                                       /var/log/voices/<name>-<timestamp>.log
Key:                                 /opt/Applio/voices-service/key.txt
start:  /opt/Applio/.venv/bin/python /opt/Applio/voices-service/stimmen_dienst.py --port 8890
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
BIBLIOTHEKEN = ["/media/disk1", "/media/Content"]        # /media/Content is currently empty
LOGDIR = "/var/log/voices"
STATUS_DIR = "/var/lib/voices-service"
JOB_DATEI = os.path.join(STATUS_DIR, "job.json")
SCHLUESSEL_DATEI = "/opt/Applio/voices-service/key.txt"
VIDEO_ENDUNGEN = ("*.mkv", "*.mp4", "*.avi", "*.mov", "*.wmv", "*.ts", "*.m4v", "*.flv")
NAME_MUSTER = re.compile(r"^[A-Za-z0-9_.-]{2,40}$")

app = FastAPI(title="Stimmen-Service", version="1.0")
_sperre = threading.Lock()
_prozess: subprocess.Popen | None = None      # running subprocess (to cancel)


# ------------------------------------------------------------------ Help

def schluessel_lesen() -> str:
    try:
        return Path(SCHLUESSEL_DATEI).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def check(request: Request) -> None:
    erwartet = schluessel_lesen()
    if not erwartet:
        return  # without key file the service stays open (only start phase)
    gegeben = request.query_params.get("key") or request.headers.get("x-key", "")
    if gegeben != erwartet:
        raise HTTPException(status_code=401, detail="Key missing or incorrect.")


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def job_laden() -> dict | None:
    try:
        return json.loads(Path(JOB_DATEI).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def job_speichern(data: dict) -> None:
    os.makedirs(STATUS_DIR, exist_ok=True)
    tmp = JOB_DATEI + ".tmp"
    Path(tmp).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, JOB_DATEI)


def videos_zaehlen(path: str) -> int:
    if os.path.isfile(path):
        return 1
    count = 0
    for endung in VIDEO_ENDUNGEN:
        count += len(glob.glob(os.path.join(path, "**", endung), recursive=True))
    return count


def finden(word: str) -> list[dict]:
    """Search for series/movie in the libraries: folder names containing the word."""
    w = word.strip()
    hits: list[dict] = []
    if os.path.isabs(w) and os.path.exists(w):
        hits.append({"path": w, "type": "folder" if os.path.isdir(w) else "file",
                        "videos": videos_zaehlen(w)})
        return hits
    search = w.casefold()
    for wurzel in BIBLIOTHEKEN:
        if not os.path.isdir(wurzel):
            continue
        for tiefe in range(1, 5):
            muster = os.path.join(wurzel, *(["*"] * tiefe))
            for folder in glob.glob(muster):
                if not os.path.isdir(folder):
                    continue
                if search in os.path.basename(folder).casefold():
                    hits.append({"path": folder, "type": "folder",
                                    "videos": videos_zaehlen(folder)})
                if len(hits) >= 12:
                    return hits
    return hits


def dataset_info(name: str) -> dict:
    """Segments, total length and speaker clusters of a dataset."""
    folder = os.path.join(DATASETS, name)
    if not os.path.isdir(folder):
        return {}
    def segments_in(path: str) -> tuple[int, float]:
        dateien = sorted(glob.glob(os.path.join(path, "*.wav")))
        seconds = 0.0
        for d in dateien:
            try:
                with wave.open(d, "rb") as w:
                    seconds += w.getnframes() / float(w.getframerate())
            except (wave.Error, OSError):
                pass
        return len(dateien), round(seconds / 60.0, 1)
    count, minutes = segments_in(folder)
    cluster = {}
    for subdir in sorted(glob.glob(os.path.join(folder, "cluster_*"))):
        if os.path.isdir(subdir):
            n, m = segments_in(subdir)
            cluster[os.path.basename(subdir)] = {"segments": n, "minutes": m}
    return {"name": name, "path": folder, "segments": count, "minutes": minutes,
            "cluster": cluster}


def log_ende(path: str, lines: int = 6) -> list[str]:
    try:
        data = Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()
        return data[-lines:]
    except OSError:
        return []


def job_aktuell() -> dict:
    data = job_laden() or {}
    name = data.get("name")
    if name:
        info = dataset_info(name)
        if info:
            data["fortschritt"] = {k: info[k] for k in ("segments", "minutes", "cluster")}
        if data.get("log"):
            data["log_ende"] = log_ende(data["log"])
    return data


# ------------------------------------------------------------------ Job

def _lauf(task: dict, steps: list[list[str]]) -> None:
    """Background run: executes steps sequentially and maintains status."""
    global _prozess
    logpfad = task["log"]
    try:
        with open(logpfad, "a", encoding="utf-8") as log:
            for schritt, cmd in steps:
                task["schritt"] = schritt
                job_speichern(task)
                log.write(f"\n===== {now()}  {schritt}: {' '.join(cmd)}\n")
                log.flush()
                _prozess = subprocess.Popen(cmd, cwd=ARBEIT, stdout=log,
                                            stderr=subprocess.STDOUT)
                rc = _prozess.wait()
                _prozess = None
                if rc != 0:
                    if task.get("status") == "abgebrochen":
                        break
                    task["status"] = "error"
                    task["news"] = (f"Step ’{schritt}’ failed"
                                          f"(Return code {rc}).")
                    break
            else:
                task["status"] = "done"
        if "news" not in task:
            task["result"] = dataset_info(task["name"])
    except Exception as error:  # noqa: BLE001 — Service must never die
        task["status"] = "error"
        task["news"] = f"Exception: {error}"
    task["schritt"] = None
    task["ende"] = now()
    job_speichern(task)


def auftrag_starten(task: dict, steps: list[list[str]]) -> dict:
    global _sperre
    with _sperre:
        alt = job_laden() or {}
        if alt.get("status") == "running":
            raise HTTPException(status_code=409, detail=f"A job is already running: {alt.get('name')}")
        os.makedirs(LOGDIR, exist_ok=True)
        stempel = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        task["log"] = os.path.join(LOGDIR, f"{task['name']}-{stempel}.log")
        task["status"] = "running"
        task["start"] = now()
        task["ende"] = None
        job_speichern(task)
        threading.Thread(target=_lauf, args=(task, steps), daemon=True).start()
    return task


# ------------------------------------------------------------------ Endpoints

@app.get("/status")
def status_ep() -> dict:
    data = job_aktuell()
    return {"ok": True, "service": "voices", "version": "1.0",
            "schluessel_gesetzt": bool(schluessel_lesen()),
            "job": {"status": data.get("status"), "type": data.get("type"),
                    "name": data.get("name")} if data else None}


@app.get("/job")
def job_ep(request: Request) -> dict:
    check(request)
    return job_aktuell()


@app.get("/finden")
def finden_ep(word: str, request: Request) -> dict:
    check(request)
    if not word.strip():
        raise HTTPException(status_code=400, detail="Field ‘word’ is missing.")
    return {"word": word, "hits": finden(word)}


@app.get("/datasets")
def datasets_ep(request: Request) -> dict:
    check(request)
    if not os.path.isdir(DATASETS):
        return {"datasets": []}
    names = sorted(d for d in os.listdir(DATASETS) if os.path.isdir(os.path.join(DATASETS, d)))
    return {"datasets": [dataset_info(n) for n in names]}


@app.post("/extrahieren")
async def extrahieren_ep(request: Request) -> dict:
    check(request)
    data = await request.json()
    source = str(data.get("serie") or data.get("source") or "").strip()
    name = str(data.get("name") or "").strip()
    if not name or not NAME_MUSTER.match(name):
        raise HTTPException(status_code=400, detail="Field ‘name’ is missing or contains illegal characters (allowed: a-z, A-Z, 0-9, . _ -, 2-40 characters).")
    if not source:
        raise HTTPException(status_code=400, detail="Field ‘serie’ is missing (Series/Film or path).")

    target = os.path.join(DATASETS, name)
    if os.path.isdir(target) and glob.glob(os.path.join(target, "**", "*"), recursive=True):
        raise HTTPException(status_code=412, detail=f"Dataset ’{name}’ already exists — please choose another name.")

    if not os.path.exists(source):
        hits = finden(source)
        if not hits:
            raise HTTPException(status_code=404, detail=f"Nothing found for ’{source}’.")
        if len(hits) > 1:
            raise HTTPException(status_code=409, detail={
                "news": f"Multiple matches for ’{source}’ — please be more specific.",
                "hits": [t["path"] for t in hits[:12]]})
        source = hits[0]["path"]
    if videos_zaehlen(source) == 0:
        raise HTTPException(status_code=404, detail=f"No video files under ’{source}’.")

    folgen_roh = data.get("folgen")
    folgen_text = "" if folgen_roh is None else str(folgen_roh).strip()
    try:
        folgen = 1 if folgen_text == "" else max(0, int(folgen_text))
    except ValueError:
        raise HTTPException(status_code=400, detail="Field ‘folgen’ must be a number (0 = all episodes).")
    trennen = str(data.get("trennen", "ja")).strip().lower() in ("ja", "true", "1", "yes")

    cmd = [VENV_PY, PREP, "--source", source, "--name", name]
    if folgen > 0:
        cmd += ["--limit", str(folgen)]
    for feld, arg in (("max_secs", "--max-secs"), ("min_db", "--min-db"), ("model", "--model")):
        wert = str(data.get(feld) or "").strip()
        if wert:
            cmd += [arg, wert]

    steps = [["schneiden", cmd]]
    if trennen:
        steps.append(["trennen", [VENV_PY, CLUSTER, "--dataset", target]])

    task = {"type": "extrahieren", "name": name, "source": source,
               "folgen": folgen, "trennen": trennen}
    auftrag_starten(task, steps)
    return {"started": True, "name": name, "source": source, "trennen": trennen,
            "log": task["log"]}


@app.post("/trennen")
async def trennen_ep(request: Request) -> dict:
    check(request)
    data = await request.json()
    name = str(data.get("name") or "").strip()
    target = os.path.join(DATASETS, name)
    if not name or not os.path.isdir(target):
        raise HTTPException(status_code=404, detail=f"Dataset ’{name}’ does not exist.")
    if not glob.glob(os.path.join(target, "*.wav")):
        raise HTTPException(status_code=412, detail="No segments found to split (already split?).")
    cmd = [VENV_PY, CLUSTER, "--dataset", target]
    if str(data.get("n_clusters") or "").strip():
        cmd += ["--n-clusters", str(int(data["n_clusters"]))]
    task = {"type": "trennen", "name": name, "source": target}
    auftrag_starten(task, [["trennen", cmd]])
    return {"started": True, "name": name, "log": task["log"]}


@app.post("/abbrechen")
def abbrechen_ep(request: Request) -> dict:
    check(request)
    data = job_laden() or {}
    if data.get("status") != "running":
        return {"abgebrochen": False, "news": "No job is running."}
    data["status"] = "abgebrochen"
    data["news"] = "Cancelled by user."
    data["ende"] = now()
    job_speichern(data)
    if _prozess is not None and _prozess.poll() is None:
        try:
            _prozess.kill()
        except OSError:
            pass
    return {"abgebrochen": True, "name": data.get("name")}


def main() -> None:
    parser = argparse.ArgumentParser(description="Voice Service (Film/Series -> RVC Dataset)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8890)
    args = parser.parse_args()
    # On startup: mark a stuck run after a crash/restart as cancelled
    alt = job_laden()
    if alt and alt.get("status") == "running":
        alt["status"] = "abgebrochen"
        alt["news"] = "Service was restarted."
        alt["ende"] = now()
        job_speichern(alt)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
