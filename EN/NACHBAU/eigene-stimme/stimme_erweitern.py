#!/usr/bin/env python3
"""YOUR-VOICE collector with self-extension (more material at same purity).

Idea: After one pass, the occupied your voice is larger (the assumed
subparts are checked). The center point is recalculated from reference + all previously
accepted pieces -> the next pass finds more of it,
without taking in foreign speakers (window consistency remains mandatory).

Call (in CT 111):
  .venv/bin/python /tmp/stimme_erweitern.py \
 --reference /opt/Applio/assets/datasets/deine-stimme-reference \
 --sources "<glob>" "<glob>" ... \
 --target /opt/Applio/assets/datasets/deine-stimme-total \
 --runden 3 --threshold 0.42 --mindestdauer 1.2
"""
import argparse
import glob
import os
import shutil
import subprocess

import numpy as np
import soundfile as sf
import torch
from speechbrain.inference.speaker import EncoderClassifier

GERAET = "cuda:0"
FENSTER, SCHRITT = 0.9, 0.45


def lade(path):
    d, r = sf.read(path, dtype="float32", always_2d=True)
    w = torch.from_numpy(d.T.copy())
    if w.shape[0] > 1:
        w = w.mean(0, keepdim=True)
    if r != 16000:
        w = torch.nn.functional.interpolate(w.unsqueeze(0), scale_factor=16000.0 / r,
                                            mode="linear", align_corners=False).squeeze(0)
    return w


class Pruefer:
    def __init__(self):
        self.cl = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="/opt/Applio/models/ecapa", run_opts={"device": GERAET})

    def emb_tensor(self, wav):
        with torch.no_grad():
            e = self.cl.encode_batch(wav.to(GERAET))
        e = e.squeeze().cpu().numpy()
        return e / (np.linalg.norm(e) + 1e-9)

    def emb(self, path):
        return self.emb_tensor(lade(path))

    def fenster_sims(self, w, mitte):
        sr = 16000
        n, s = int(FENSTER * sr), int(SCHRITT * sr)
        sims = []
        for start in range(0, w.shape[1] - n + 1, s):
            sims.append(float(self.emb_tensor(w[:, start:start + n]) @ mitte))
        return np.array(sims)


def laeufe(passt, mindest_fenster):
    """All connected hit runs with minimum length (start, End, Mean)."""
    result = []
    i0 = None
    for idx in range(len(passt) + 1):
        ok = idx < len(passt) and bool(passt[idx])
        if ok and i0 is None:
            i0 = idx
        elif not ok and i0 is not None:
            if idx - i0 >= mindest_fenster:
                result.append((i0, idx - 1))
            i0 = None
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", required=True)
    ap.add_argument("--sources", nargs="+", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--runden", type=int, default=3)
    ap.add_argument("--threshold", type=float, default=0.42)
    ap.add_argument("--mindestdauer", type=float, default=1.2)
    ap.add_argument("--report", default="/tmp/stimme_bericht.txt")
    a = ap.parse_args()

    P = Pruefer()
    ref_pfade = sorted(glob.glob(os.path.join(a.reference, "*.wav")))
    print(f"start reference: {len(ref_pfade)} pieces")

    candidates = []
    for muster in a.sources:
        candidates += sorted(glob.glob(muster + "/*.wav"))
    candidates = [f for f in candidates if not f.startswith(a.reference)]
    print(f"Candidates: {len(candidates)}")

    mindest_fenster = max(1, int(np.ceil((a.mindestdauer - FENSTER) / SCHRITT)) + 1)
    report = []
    letzte_ausgabe = None
    for runde in range(1, a.runden + 1):
        # Center point from reference + previously accepted pieces
        ref_embs = np.stack([P.emb(f) for f in ref_pfade])
        mitte = ref_embs.mean(0)
        mitte /= np.linalg.norm(mitte)
        print(f"\n--- Round {runde}: Reference {len(ref_pfade)} pieces")
        output = f"/tmp/deine-stimme5-runde{runde}"
        shutil.rmtree(output, ignore_errors=True)
        os.makedirs(output, exist_ok=True)
        new, total_sec, nr = [], 0.0, 0
        for i, f in enumerate(candidates, 1):
            try:
                w = lade(f)
            except Exception:
                continue
            if w.shape[1] < int(FENSTER * 16000):
                continue
            sims = P.fenster_sims(w, mitte)
            passt = sims >= a.threshold
            for (s0, s1) in laeufe(passt, mindest_fenster):
                from_ = max(0.0, s0 * SCHRITT - 0.08)
                to = min(w.shape[1] / 16000, s1 * SCHRITT + FENSTER + 0.08)
                target = os.path.join(output, f"{nr:05d}_s{int(round(sims[s0:s1+1].mean()*100))}_"
                                             f"{os.path.basename(f)[:4]}_{from_:.1f}.wav")
                subprocess.run(["/usr/bin/ffmpeg", "-nostdin", "-y", "-v", "error",
                                "-ss", f"{from_:.2f}", "-t", f"{to - from_:.2f}", "-i", f,
                                "-c", "copy", target], capture_output=True)
                if os.path.exists(target):
                    new.append(target)
                    total_sec += to - from_
                    nr += 1
            if i % 200 == 0:
                print(f" {i}/{len(candidates)} ... {nr} pieces")
        print(f"Round {runde}: {nr} pieces, {total_sec/60:.1f} minutes")
        report.append(f"Round {runde}: {nr} pieces / {total_sec/60:.1f} Min"
                       f"(Reference {len(ref_pfade)})")
        # next round: accepted pieces as additional reference (covered)
        extra = new[:400]
        ref_pfade = sorted(glob.glob(os.path.join(a.reference, "*.wav"))) + extra
        letzte_ausgabe = output
        if runde > 1 and nr <= len(report) and False:
            break

    shutil.rmtree(a.target, ignore_errors=True)
    shutil.copytree(letzte_ausgabe, a.target)
    anz = len(glob.glob(a.target + "/*.wav"))
    sek = 0.0
    for f in glob.glob(a.target + "/*.wav"):
        try:
            sek += sf.info(f).duration
        except Exception:
            pass
    print(f"\nFINAL: {anz} pieces, {sek/60:.1f} minutes -> {a.target}")
    open(a.report, "w").write("\n".join(report) + "\n")


if __name__ == "__main__":
    main()
