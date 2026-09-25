#!/usr/bin/env python3
"""XTTS-v2 Clone: speaks <Text> with the voice style of the reference recording.

Call (in CT 111):
  /opt/xtts/venv/bin/python /opt/xtts/xtts-klon.py \
 --reference /path/reference.wav --text "Hallo!" --output /tmp/klon.wav [--voice de]
"""
import argparse
import os

os.environ.setdefault("COQUI_TOS_AGREED", "1")     # Automatically confirm XTTS license notice

from TTS.api import TTS                             # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--reference", required=True,
               help="WAV file(s) – separate multiple files with comma (they will be averaged)")
p.add_argument("--text", required=True)
p.add_argument("--output", required=True)
p.add_argument("--voice", default="de")
p.add_argument("--model", default="tts_models/multilingual/multi-dataset/xtts_v2")
p.add_argument("--geraet", default="cuda")
a = p.parse_args()

refs = [r.strip() for r in a.reference.split(",") if r.strip()]
reference = refs if len(refs) > 1 else refs[0]

tts = TTS(a.model).to(a.geraet)
tts.tts_to_file(text=a.text, speaker_wav=reference, language=a.voice, file_path=a.output)
print("done:", a.output)
