FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VOICE_DIR=/voices

# lameenc = MP3-Kodierer (kein ffmpeg nötig), piper-tts = Sprachausgabe
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir piper-tts fastapi "uvicorn[standard]" lameenc

WORKDIR /app
COPY app/main.py /app/main.py
COPY app/katalog.py /app/katalog.py
COPY app/playlist.py /app/playlist.py
COPY app/meldungen.py /app/meldungen.py
COPY app/suche.py /app/suche.py

EXPOSE 8881
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8881", "--log-level", "warning"]
