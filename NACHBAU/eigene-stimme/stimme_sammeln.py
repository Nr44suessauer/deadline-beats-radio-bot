#!/usr/bin/env python3
"""deine Stimme aus ALLEN Folgen sammeln - reine, zugeschnittene Teilstuecke.

Verbesserungen gegenueber v3:
  * Referenz = bestaetigter DEINE-STIMME-Cluster (<deine-referenz>, vom Nutzer bestaetigt)
  * Jedes Segment wird in 0,9-s-Fenster (Schritt 0,45 s) zerlegt; nur der
    **laengste zusammenhaengende Treffer-Lauf** wird behalten (Mischreste am
    Anfang/Ende werden weggeschnitten)
  * Ausgabe in Original-Qualitaet (ffmpeg-Schnitt), Bericht mit Minuten je Quelle

Aufruf (im CT 111):
  .venv/bin/python /tmp/stimme_sammeln.py \
      --referenz /opt/Applio/assets/datasets/<deine-referenz> \
      --quellen "/opt/Applio/assets/datasets/kono2/cluster_*" \
                "/opt/Applio/assets/datasets/<weitere-quellen>/cluster_*" \
                "/opt/Applio/assets/datasets/kono13/cluster_*" \
      --ziel /opt/Applio/assets/datasets/<dein-datensatz>
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


def lade(pfad):
    d, r = sf.read(pfad, dtype="float32", always_2d=True)
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
    ap.add_argument("--referenz", required=True)
    ap.add_argument("--quellen", nargs="+", required=True)
    ap.add_argument("--ziel", required=True)
    ap.add_argument("--schwelle", type=float, default=0.0)
    ap.add_argument("--mindestanteil", type=float, default=0.7)
    ap.add_argument("--bericht", default="/tmp/deine-stimme_gesamt_bericht.txt")
    a = ap.parse_args()

    P = Pruefer()

    ref_dateien = sorted(glob.glob(os.path.join(a.referenz, "*.wav")))
    ref_embs = np.stack([P.emb(lade(f)) for f in ref_dateien])
    mitte = ref_embs.mean(0); mitte /= np.linalg.norm(mitte)
    innen = [float(ref_embs[i] @ ref_embs[j])
             for i in range(len(ref_embs)) for j in range(i + 1, len(ref_embs))]
    p10 = float(np.percentile(innen, 10))
    schwelle = a.schwelle if a.schwelle > 0 else max(0.42, p10 - 0.05)
    print(f"Referenz {len(ref_dateien)} Segmente | innen p10 {p10:.2f} "
          f"median {np.median(innen):.2f} -> Schwelle {schwelle:.2f}")

    kandidaten = []
    for muster in a.quellen:
        kandidaten += sorted(glob.glob(muster + "/*.wav"))
    kandidaten = [f for f in kandidaten if not f.startswith(a.referenz)]
    print(f"Kandidaten: {len(kandidaten)}")

    shutil.rmtree(a.ziel, ignore_errors=True)
    os.makedirs(a.ziel, exist_ok=True)

    bericht, sauber, sekunden = [], 0, 0.0
    for i, f in enumerate(kandidaten, 1):
        try:
            w = lade(f)
        except Exception as e:
            bericht.append(f"FEHLER {f}: {e}")
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
        passt = sims >= schwelle
        # laengsten zusammenhaengenden Treffer-Lauf suchen (bei Gleichstand: bester Mittelwert)
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
            bericht.append(f"raus     {f}")
            continue
        _, score, bester_anfang, bester_ende = best
        dauer = (bester_ende - bester_anfang) * SCHRITT + FENSTER
        if dauer < 1.2:
            bericht.append(f"kurz     {f}")
            continue
        # zuschneiden (kleine Zugabe, damit nichts abgeschnitten klingt)
        von = max(0.0, bester_anfang * SCHRITT - 0.08)
        bis = min(w.shape[1] / sr, (bester_ende * SCHRITT + FENSTER) + 0.08)
        ziel = os.path.join(a.ziel, f"{sauber:05d}_s{int(round(score*100))}_"
                                    + os.path.basename(f))
        subprocess.run(["/usr/bin/ffmpeg", "-nostdin", "-y", "-v", "error",
                        "-ss", f"{von:.2f}", "-t", f"{bis - von:.2f}", "-i", f,
                        "-c", "copy", ziel], capture_output=True)
        if not os.path.exists(ziel):
            bericht.append(f"fehler   {f}")
            continue
        sauber += 1
        sekunden += bis - von
        bericht.append(f"OK       {von:5.2f}-{bis:5.2f}s  {f}")
        if i % 100 == 0:
            print(f"  {i}/{len(kandidaten)} ... {sauber} sauber, {sekunden/60:.1f} Min")

    open(a.bericht, "w").write("\n".join(bericht) + "\n")
    print(f"\n{sauber} Teilstuecke, {sekunden/60:.1f} Minuten -> {a.ziel}")
    print(f"Bericht: {a.bericht}")


if __name__ == "__main__":
    main()
