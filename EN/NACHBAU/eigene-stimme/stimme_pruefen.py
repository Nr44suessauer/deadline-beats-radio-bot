#!/usr/bin/env python3
"""Clean collection of ONE voice from all segments (followed by follow).

Working method (solves the "Kazuma is included" problem):
 1. Reference = confirmed speaker cluster (folder with pure segments).
 -> Voice fingerprint (mean of ECAPA embeddings) + **threshold** from
 the similarities within the reference (10%-percentile).
 2. Each source segment is divided into short windows (1.2 s / step 0.6 s).
 -> Mean similarity to the fingerprint AND proportion of matching
 windows. Segments with foreign voice (or mixture) are filtered out.
 3. Output to the target folder (only the clean subparts).

Call (in CT 111):
  .venv/bin/python /tmp/stimme_pruefen.py \
 --reference /tmp/szene-kluster/cluster_1 \
 --sources "/opt/Applio/assets/datasets/kono2/cluster_*" \
 "/opt/Applio/assets/datasets/<more-sources>/cluster_*" \
 --target /opt/Applio/assets/datasets/<clean-pieces>
"""
import argparse
import glob
import os
import shutil

import numpy as np
import soundfile as sf
import torch
from speechbrain.inference.speaker import EncoderClassifier

GERAET = "cuda:0"


def lade(path):
    d, r = sf.read(path, dtype="float32", always_2d=True)
    w = torch.from_numpy(d.T.copy())
    if w.shape[0] > 1:
        w = w.mean(0, keepdim=True)
    if r != 16000:
        w = torch.nn.functional.interpolate(w.unsqueeze(0), scale_factor=16000.0 / r,
                                            mode="linear", align_corners=False).squeeze(0)
    return w


class Stimmpruefer:
    def __init__(self):
        self.cl = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="/opt/Applio/models/ecapa",
            run_opts={"device": GERAET})

    def emb(self, wav):
        with torch.no_grad():
            e = self.cl.encode_batch(wav.to(GERAET))
        e = e.squeeze().cpu().numpy()
        return e / (np.linalg.norm(e) + 1e-9)

    def fenster(self, path, laenge=1.2, schritt=0.6):
        """Split segment into windows -> list of embeddings."""
        w = lade(path)
        sr = 16000
        n = int(laenge * sr)
        s = int(schritt * sr)
        if w.shape[1] <= n:
            return [self.emb(w)]
        embs = []
        for start in range(0, w.shape[1] - n + 1, s):
            embs.append(self.emb(w[:, start:start + n]))
        return embs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", required=True, help="Folder with clean reference segments")
    ap.add_argument("--sources", nargs="+", required=True, help="Globs with candidate segments")
    ap.add_argument("--target", required=True)
    ap.add_argument("--threshold", type=float, default=0.0,
                    help="Minimum similarity (0 = automatic from reference)")
    ap.add_argument("--mindestanteil", type=float, default=0.7,
                    help="Proportion of windows that must match")
    ap.add_argument("--report", default="/tmp/deine-stimme_bericht.txt")
    a = ap.parse_args()

    P = Stimmpruefer()

    ref_dateien = sorted(glob.glob(os.path.join(a.reference, "*.wav")))
    if len(ref_dateien) < 4:
        raise SystemExit(f"Too few reference segments in {a.reference}")
    ref_embs = np.stack([P.emb(lade(f)) for f in ref_dateien])
    mitte = ref_embs.mean(0)
    mitte /= np.linalg.norm(mitte)

    # Benchmark: Similarities WITHIN the reference
    innen = []
    for i in range(len(ref_embs)):
        for j in range(i + 1, len(ref_embs)):
            innen.append(float(ref_embs[i] @ ref_embs[j]))
    innen = np.array(innen)
    p10 = float(np.percentile(innen, 10))
    threshold = a.threshold if a.threshold > 0 else max(0.45, p10 - 0.05)
    print(f"Reference: {len(ref_dateien)} segments | inside: min {innen.min():.2f}"
          f"p10 {p10:.2f} median {np.median(innen):.2f} -> threshold {threshold:.2f}")

    candidates = []
    for muster in a.sources:
        candidates += sorted(glob.glob(muster + "/*.wav")) if not muster.endswith(".wav") \
            else [muster]
    candidates = [f for f in candidates if os.path.dirname(f) != a.reference]
    print(f"Candidates: {len(candidates)}")

    shutil.rmtree(a.target, ignore_errors=True)
    os.makedirs(a.target, exist_ok=True)

    report, sauber, total_sec = [], 0, 0.0
    for i, f in enumerate(candidates, 1):
        try:
            embs = P.fenster(f)
        except Exception as e:
            report.append(f"ERROR {f}: {e}")
            continue
        sims = np.array([float(e @ mitte) for e in embs])
        mittel = float(sims.mean())
        anteil = float((sims >= threshold - 0.10).mean())
        if mittel >= threshold and anteil >= a.mindestanteil:
            target = os.path.join(a.target, f"{sauber:05d}_s{int(round(mittel*100))}_" + os.path.basename(f))
            shutil.copy2(f, target)
            sauber += 1
            try:
                total_sec += float(sf.info(f).duration)
            except Exception:
                pass
            report.append(f"OK   {mittel:.2f} proportion {anteil:.2f}  {f}")
        else:
            report.append(f"output {mittel:.2f} proportion {anteil:.2f}  {f}")
        if i % 100 == 0:
            print(f" {i}/{len(candidates)} ... {sauber} clean")

    open(a.report, "w").write("\n".join(report) + "\n")
    print(f"\n{sauber} from {len(candidates)} segments taken over"
          f"({total_sec/60:.1f} minutes) -> {a.target}")
    print(f"Report: {a.report}")


if __name__ == "__main__":
    main()
