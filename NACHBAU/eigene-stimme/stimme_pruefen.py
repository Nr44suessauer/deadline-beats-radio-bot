#!/usr/bin/env python3
"""Sauberes Sammeln EINER Stimme aus allen Segmenten (Folge fuer Folge).

Arbeitsweise (loest das "Kazuma ist mit drin"-Problem):
  1. Referenz = bestaetigter Sprecher-Cluster (Ordner mit reinen Segmenten).
     -> Stimm-Fingerabdruck (Mittel der ECAPA-Embeddings) + **Messlatte** aus
        den Aehnlichkeiten innerhalb der Referenz (10%-Perzentil).
  2. Jedes Quellsegment wird in kurze Fenster (1,2 s / Schritt 0,6 s) zerlegt.
     -> Mittelwert der Aehnlichkeit zum Fingerabdruck UND Anteil passender
        Fenster. Segmente mit fremder Stimme (oder Mischung) fallen raus.
  3. Ausgabe in den Zielordner (nur die sauberen Teilstuecke).

Aufruf (im CT 111):
  .venv/bin/python /tmp/stimme_pruefen.py \
      --referenz /tmp/szene-kluster/cluster_1 \
      --quellen "/opt/Applio/assets/datasets/kono2/cluster_*" \
                "/opt/Applio/assets/datasets/<weitere-quellen>/cluster_*" \
      --ziel /opt/Applio/assets/datasets/<saubere-stuecke>
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


def lade(pfad):
    d, r = sf.read(pfad, dtype="float32", always_2d=True)
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

    def fenster(self, pfad, laenge=1.2, schritt=0.6):
        """Segment in Fenster zerlegen -> Liste von Embeddings."""
        w = lade(pfad)
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
    ap.add_argument("--referenz", required=True, help="Ordner mit reinen Referenzsegmenten")
    ap.add_argument("--quellen", nargs="+", required=True, help="Glob(s) mit Kandidatensegmenten")
    ap.add_argument("--ziel", required=True)
    ap.add_argument("--schwelle", type=float, default=0.0,
                    help="Mindestaehnlichkeit (0 = automatisch aus der Referenz)")
    ap.add_argument("--mindestanteil", type=float, default=0.7,
                    help="Anteil der Fenster, die passen muessen")
    ap.add_argument("--bericht", default="/tmp/deine-stimme_bericht.txt")
    a = ap.parse_args()

    P = Stimmpruefer()

    ref_dateien = sorted(glob.glob(os.path.join(a.referenz, "*.wav")))
    if len(ref_dateien) < 4:
        raise SystemExit(f"Zu wenige Referenzsegmente in {a.referenz}")
    ref_embs = np.stack([P.emb(lade(f)) for f in ref_dateien])
    mitte = ref_embs.mean(0)
    mitte /= np.linalg.norm(mitte)

    # Messlatte: Aehnlichkeiten INNERHALB der Referenz
    innen = []
    for i in range(len(ref_embs)):
        for j in range(i + 1, len(ref_embs)):
            innen.append(float(ref_embs[i] @ ref_embs[j]))
    innen = np.array(innen)
    p10 = float(np.percentile(innen, 10))
    schwelle = a.schwelle if a.schwelle > 0 else max(0.45, p10 - 0.05)
    print(f"Referenz: {len(ref_dateien)} Segmente | innen: min {innen.min():.2f} "
          f"p10 {p10:.2f} median {np.median(innen):.2f} -> Schwelle {schwelle:.2f}")

    kandidaten = []
    for muster in a.quellen:
        kandidaten += sorted(glob.glob(muster + "/*.wav")) if not muster.endswith(".wav") \
            else [muster]
    kandidaten = [f for f in kandidaten if os.path.dirname(f) != a.referenz]
    print(f"Kandidaten: {len(kandidaten)}")

    shutil.rmtree(a.ziel, ignore_errors=True)
    os.makedirs(a.ziel, exist_ok=True)

    bericht, sauber, gesamt_sek = [], 0, 0.0
    for i, f in enumerate(kandidaten, 1):
        try:
            embs = P.fenster(f)
        except Exception as e:
            bericht.append(f"FEHLER {f}: {e}")
            continue
        sims = np.array([float(e @ mitte) for e in embs])
        mittel = float(sims.mean())
        anteil = float((sims >= schwelle - 0.10).mean())
        if mittel >= schwelle and anteil >= a.mindestanteil:
            ziel = os.path.join(a.ziel, f"{sauber:05d}_s{int(round(mittel*100))}_" + os.path.basename(f))
            shutil.copy2(f, ziel)
            sauber += 1
            try:
                gesamt_sek += float(sf.info(f).duration)
            except Exception:
                pass
            bericht.append(f"OK   {mittel:.2f} anteil {anteil:.2f}  {f}")
        else:
            bericht.append(f"raus {mittel:.2f} anteil {anteil:.2f}  {f}")
        if i % 100 == 0:
            print(f"  {i}/{len(kandidaten)} ... {sauber} sauber")

    open(a.bericht, "w").write("\n".join(bericht) + "\n")
    print(f"\n{sauber} von {len(kandidaten)} Segmenten uebernommen "
          f"({gesamt_sek/60:.1f} Minuten) -> {a.ziel}")
    print(f"Bericht: {a.bericht}")


if __name__ == "__main__":
    main()
