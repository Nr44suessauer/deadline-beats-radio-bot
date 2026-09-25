#!/usr/bin/env python3
"""XTTS-v2-Klon: spricht <Text> mit dem Stimmklang der Referenzaufnahme.

Aufruf (im CT 111):
  /opt/xtts/venv/bin/python /opt/xtts/xtts-klon.py \
      --referenz /pfad/referenz.wav --text "Hallo!" --ausgabe /tmp/klon.wav [--sprache de]
"""
import argparse
import os

os.environ.setdefault("COQUI_TOS_AGREED", "1")     # Lizenzhinweis von XTTS automatisch bestaetigen

from TTS.api import TTS                             # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--referenz", required=True,
               help="WAV-Datei(en) – mehrere mit Komma trennen (werden gemittelt)")
p.add_argument("--text", required=True)
p.add_argument("--ausgabe", required=True)
p.add_argument("--sprache", default="de")
p.add_argument("--modell", default="tts_models/multilingual/multi-dataset/xtts_v2")
p.add_argument("--geraet", default="cuda")
a = p.parse_args()

refs = [r.strip() for r in a.referenz.split(",") if r.strip()]
referenz = refs if len(refs) > 1 else refs[0]

tts = TTS(a.modell).to(a.geraet)
tts.tts_to_file(text=a.text, speaker_wav=referenz, language=a.sprache, file_path=a.ausgabe)
print("fertig:", a.ausgabe)
