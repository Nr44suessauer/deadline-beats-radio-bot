#!/usr/bin/env python3
"""Collect your voice from ALL episodes - pure, tailored subparts.

Improvements compared to v3:
 * Reference = confirmed YOUR-VOICE cluster (deine-stimme-reference, confirmed by the user)
 * Each segment is divided into 0.9-s windows (step 0.45 s); only the
 **longest contiguous hit run** is retained (mixed residues at the
 beginning/end are cut off)
 * Output in original quality (ffmpeg cut), report with minutes per source

Call (in CT 111):
  .venv/bin/python /tmp/stimme_sammeln.py \
 --reference /opt/Applio/assets/datasets/deine-stimme-reference \
 --sources "/opt/Applio/assets/datasets/kono2/cluster_*" \
 "/opt/Applio/assets/datasets/<more-sources>/cluster_*" \
 "/opt/Applio/assets/datasets/kono13/cluster_*" \
 --target /opt/Applio/assets/datasets/deine-stimme-total
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

    def emb(self, wav):
        with torch.no_grad():
            e = self.cl.encode_batch(wav.to(GERAET))
        e = e.squeeze().cpu().numpy()
        return e / (np.linalg.norm(e) + 1e-9)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", required=True)
    ap.add_argument("--sources", nargs="+", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--threshold", type=float, default=0.0)
    ap.add_argument("--mindestanteil", type=float, default=0.7)
    ap.add_argument("--report", default="/tmp/deine-stimme_gesamt_bericht.txt")
    a = ap.parse_args()

    P = Pruefer()

    ref_dateien = sorted(glob.glob(os.path.join(a.reference, "*.wav")))
    ref_embs = np.stack([P.emb(lade(f)) for f in ref_dateien])
    mitte = ref_embs.mean(0); mitte /= np.linalg.norm(mitte)
    innen = [float(ref_embs[i] @ ref_embs[j])
             for i in range(len(ref_embs)) for j in range(i + 1, len(ref_embs))]
    p10 = float(np.percentile(innen, 10))
    threshold = a.threshold if a.threshold > 0 else max(0.42, p10 - 0.05)
    print(f"Reference {len(ref_dateien)} segments | inside p10 {p10:.2f}"
          f"median {np.median(innen):.2f} -> threshold {threshold:.2f}")

    candidates = []
    for muster in a.sources:
        candidates += sorted(glob.glob(muster + "/*.wav"))
    candidates = [f for f in candidates if not f.startswith(a.reference)]
    print(f"Candidates: {len(candidates)}")

    shutil.rmtree(a.target, ignore_errors=True)
    os.makedirs(a.target, exist_ok=True)

    report, sauber, seconds = [], 0, 0.0
    for i, f in enumerate(candidates, 1):
        try:
            w = lade(f)
        except Exception as e:
            report.append(f"ERROR {f}: {e}")
            continue
        sr = 16000
        n, s = int(FENSTER * sr), int(SCHRITT * sr)
        if w.shape[1] < n:
            continue
        sims = []
        for start in range(0, w.shape[1] - n + 1, s):
            e = P.emb(w[:, start:start + n])
            sims.append(float(e @ mitte))
        sims = np.array(sims)
        passt = sims >= threshold
        # search for longest consecutive hit run (in case of tie: best average)
        best = None
        i0 = None
        for idx in range(len(sims) + 1):
            ok = idx < len(sims) and bool(passt[idx])
            if ok and i0 is None:
                i0 = idx
            elif not ok and i0 is not None:
                m = float(sims[i0:idx].mean())
                kandidat = (idx - i0, m, i0, idx - 1)
                if best is None or kandidat[:2] > best[:2]:
                    best = kandidat
                i0 = None
        if best is None:
            report.append(f"remove     {f}")
            continue
        _, score, best_start, bester_ende = best
        duration = (bester_ende - best_start) * SCHRITT + FENSTER
        if duration < 1.2:
            report.append(f"short     {f}")
            continue
        # trim (small addition, so nothing sounds cut off)
        from_ = max(0.0, best_start * SCHRITT - 0.08)
        to = min(w.shape[1] / sr, (bester_ende * SCHRITT + FENSTER) + 0.08)
        target = os.path.join(a.target, f"{sauber:05d}_s{int(round(score*100))}_"
                                    + os.path.basename(f))
        subprocess.run(["/usr/bin/ffmpeg", "-nostdin", "-y", "-v", "error",
                        "-ss", f"{from_:.2f}", "-t", f"{to - from_:.2f}", "-i", f,
                        "-c", "copy", target], capture_output=True)
        if not os.path.exists(target):
            report.append(f"error   {f}")
            continue
        sauber += 1
        seconds += to - from_
        report.append(f"OK       {from_:5.2f}-{to:5.2f}s  {f}")
        if i % 100 == 0:
            print(f" {i}/{len(candidates)} ... {sauber} clean, {seconds/60:.1f} Min")

    open(a.report, "w").write("\n".join(report) + "\n")
    print(f"\n{sauber} parts, {seconds/60:.1f} minutes -> {a.target}")
    print(f"Report: {a.report}")


if __name__ == "__main__":
    main()
