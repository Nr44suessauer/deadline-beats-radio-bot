#!/usr/bin/env python3
"""DEINE-STIMME-Sammler mit Selbst-Erweiterung (mehr Material bei gleicher Reinheit).

Idee: Nach einem Durchlauf ist die belegte eigene Stimme groesser (die angenommenen
Teilstuecke sind ja geprueft). Der Mittelpunkt wird aus Referenz + allen bisher
angenommenen Stuecken neu berechnet -> der naechste Durchlauf findet mehr von ihr,
ohne Fremdsprecher aufzunehmen (Fenster-Konsistenz bleibt Pflicht).

Aufruf (im CT 111):
  .venv/bin/python /tmp/stimme_erweitern.py \
      --referenz /opt/Applio/assets/datasets/<deine-referenz> \
      --quellen "<glob>" "<glob>" ... \
      --ziel /opt/Applio/assets/datasets/<dein-datensatz> \
      --runden 3 --schwelle 0.42 --mindestdauer 1.2
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

    def emb_tensor(self, wav):
        with torch.no_grad():
            e = self.cl.encode_batch(wav.to(GERAET))
        e = e.squeeze().cpu().numpy()
        return e / (np.linalg.norm(e) + 1e-9)

    def emb(self, pfad):
        return self.emb_tensor(lade(pfad))

    def fenster_sims(self, w, mitte):
        sr = 16000
        n, s = int(FENSTER * sr), int(SCHRITT * sr)
        sims = []
        for start in range(0, w.shape[1] - n + 1, s):
            sims.append(float(self.emb_tensor(w[:, start:start + n]) @ mitte))
        return np.array(sims)


def laeufe(passt, mindest_fenster):
    """Alle zusammenhaengenden Treffer-Laeufe mit Mindestlaenge (Start, Ende, Mittelwert)."""
    ergebnis = []
    i0 = None
    for idx in range(len(passt) + 1):
        ok = idx < len(passt) and bool(passt[idx])
        if ok and i0 is None:
            i0 = idx
        elif not ok and i0 is not None:
            if idx - i0 >= mindest_fenster:
                ergebnis.append((i0, idx - 1))
            i0 = None
    return ergebnis


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--referenz", required=True)
    ap.add_argument("--quellen", nargs="+", required=True)
    ap.add_argument("--ziel", required=True)
    ap.add_argument("--runden", type=int, default=3)
    ap.add_argument("--schwelle", type=float, default=0.42)
    ap.add_argument("--mindestdauer", type=float, default=1.2)
    ap.add_argument("--bericht", default="/tmp/stimme_bericht.txt")
    a = ap.parse_args()

    P = Pruefer()
    ref_pfade = sorted(glob.glob(os.path.join(a.referenz, "*.wav")))
    print(f"Start-Referenz: {len(ref_pfade)} Stuecke")

    kandidaten = []
    for muster in a.quellen:
        kandidaten += sorted(glob.glob(muster + "/*.wav"))
    kandidaten = [f for f in kandidaten if not f.startswith(a.referenz)]
    print(f"Kandidaten: {len(kandidaten)}")

    mindest_fenster = max(1, int(np.ceil((a.mindestdauer - FENSTER) / SCHRITT)) + 1)
    bericht = []
    letzte_ausgabe = None
    for runde in range(1, a.runden + 1):
        # Mittelpunkt aus Referenz + bisher angenommenen Stuecken
        ref_embs = np.stack([P.emb(f) for f in ref_pfade])
        mitte = ref_embs.mean(0)
        mitte /= np.linalg.norm(mitte)
        print(f"\n--- Runde {runde}: Referenz {len(ref_pfade)} Stuecke")
        ausgabe = f"/tmp/deine-stimme5-runde{runde}"
        shutil.rmtree(ausgabe, ignore_errors=True)
        os.makedirs(ausgabe, exist_ok=True)
        neu, gesamt_sek, nr = [], 0.0, 0
        for i, f in enumerate(kandidaten, 1):
            try:
                w = lade(f)
            except Exception:
                continue
            if w.shape[1] < int(FENSTER * 16000):
                continue
            sims = P.fenster_sims(w, mitte)
            passt = sims >= a.schwelle
            for (s0, s1) in laeufe(passt, mindest_fenster):
                von = max(0.0, s0 * SCHRITT - 0.08)
                bis = min(w.shape[1] / 16000, s1 * SCHRITT + FENSTER + 0.08)
                ziel = os.path.join(ausgabe, f"{nr:05d}_s{int(round(sims[s0:s1+1].mean()*100))}_"
                                             f"{os.path.basename(f)[:4]}_{von:.1f}.wav")
                subprocess.run(["/usr/bin/ffmpeg", "-nostdin", "-y", "-v", "error",
                                "-ss", f"{von:.2f}", "-t", f"{bis - von:.2f}", "-i", f,
                                "-c", "copy", ziel], capture_output=True)
                if os.path.exists(ziel):
                    neu.append(ziel)
                    gesamt_sek += bis - von
                    nr += 1
            if i % 200 == 0:
                print(f"  {i}/{len(kandidaten)} ... {nr} Stuecke")
        print(f"Runde {runde}: {nr} Stuecke, {gesamt_sek/60:.1f} Minuten")
        bericht.append(f"Runde {runde}: {nr} Stuecke / {gesamt_sek/60:.1f} Min "
                       f"(Referenz {len(ref_pfade)})")
        # naechste Runde: angenommene Stuecke als zusaetzliche Referenz (gedeckelt)
        zusatz = neu[:400]
        ref_pfade = sorted(glob.glob(os.path.join(a.referenz, "*.wav"))) + zusatz
        letzte_ausgabe = ausgabe
        if runde > 1 and nr <= len(bericht) and False:
            break

    shutil.rmtree(a.ziel, ignore_errors=True)
    shutil.copytree(letzte_ausgabe, a.ziel)
    anz = len(glob.glob(a.ziel + "/*.wav"))
    sek = 0.0
    for f in glob.glob(a.ziel + "/*.wav"):
        try:
            sek += sf.info(f).duration
        except Exception:
            pass
    print(f"\nENDGUELTIG: {anz} Stuecke, {sek/60:.1f} Minuten -> {a.ziel}")
    open(a.bericht, "w").write("\n".join(bericht) + "\n")


if __name__ == "__main__":
    main()
