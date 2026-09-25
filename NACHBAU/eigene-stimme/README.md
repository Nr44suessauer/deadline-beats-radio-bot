# Eigene Sprecherstimme — Arbeitsanleitung zu den Skripten

Diese Anleitung baut eine **eigene Sprecherstimme** auf eigener Hardware nach: vom
eigenen Tonmaterial bis zum Sprechdienst. Sie gehört zu **`DOKU/STIMME.md`** — dort
steht der vollständige Weg in Ruhe beschrieben (Rechtliches zuerst, dann beide Wege).

> **Diese Fassung enthält keine fremde Stimme und keine Stimmdaten.** Alle Skripte sind
> **Vorlagen**: Die eingetragenen Pfade, Adressen und Namen sind **Beispielwerte aus
> dem Bau** und müssen auf deine Umgebung angepasst werden.
>
> **Rechtliches:** Nur eigenes Material verwenden, an dem du die Rechte hast. Keine
> fremden Stimmen veröffentlichen oder einsetzen. Modell, Datensatz und Hörproben
> nicht weitergeben.

---

## Was in diesem Ordner liegt

| Datei | Zweck |
| --- | --- |
| `stimmen_dienst.py`, `stimmen-dienst.service`, `einrichten-stimmen-dienst.sh` | Rohmaterial: Video → Demucs → Sprachschnitt → Sprecher-Cluster (Dienst **8890**) |
| `cluster-proben.sh` | Hörproben je Sprecher-Cluster (Auswahl der Zielstimme) |
| `stimme_pruefen.py` | Fenster-Prüfung: reine Stücke der Zielstimme gegen die bestätigte Referenz |
| `stimme_sammeln.py` | Sammlung: nur der längste zusammenhängende Trefferlauf je Kandidat |
| `stimme_erweitern.py` | Selbst-Erweiterung in Runden (mehr Material aus mehr Quellen) |
| `rvc-trainieren.sh` | Training im Container (Preprocess → Extract → Train → Index) |
| `sprechdienst.py`, `sprechdienst.service` | Sprechdienst **10205**: Basis-TTS → RVC → WAV (systemd) |
| `tg-sprachnachricht.sh` | Hörprobe per Telegram schicken (optional) |
| `verworfen/` | ein verworfener Weg — nur als Referenz |

Die Datei-Kommentare nennen die **Stellschrauben oben im Skript** (Pfade, Adressen,
Schwellen). Die Methode, Messwerte und Fallstricke stehen in `DOKU/STIMME.md`.

---

## Der Weg in Kurzform

```bash
# 0) Umgebung: NVIDIA-GPU, ffmpeg, Applio/RVC  (siehe DOKU/STIMME.md, Abschnitt 3.2)
# 1) Sprechertrennung einrichten und starten  (Port 8890)
bash einrichten-stimmen-dienst.sh
K=$(cat /opt/stimmen-dienst/schluessel.txt)
curl -s -X POST "http://<GPU-Maschine>:8890/extrahieren?schluessel=$K" \
     -H 'Content-Type: application/json' \
     -d '{"serie":"/pfad/zu/deinem/material","name":"lauf1","folgen":1,"trennen":true}'

# 2) Zielstimme bestätigen (Hörproben je Cluster) und 5-10 saubere Referenzstücke ablegen
bash cluster-proben.sh lauf1 2

# 3) Reine Stücke sammeln (Beispielwerte in den Skripten anpassen)
/opt/Applio/.venv/bin/python stimme_sammeln.py \
  --referenz <deine-referenz> --quellen "<weitere-quellen>/cluster_*" \
  --ziel <dein-datensatz>

# 4) Modell trainieren  (~1 h auf einer RTX 3090 Ti für ~10 Minuten Material)
bash rvc-trainieren.sh <dein-modell> <dein-datensatz> 400 8

# 5) Sprechdienst aufsetzen  (Port 10205; Vertrag: POST /tts, GET /health)
#    sprechdienst.py + sprechdienst.service zum Container bringen, Werte eintragen,
#    systemctl enable --now sprechdienst, /health prüfen

# 6) In radio-tts einbinden  (geheim.env):
#    EIGENE_STIMME_URL=http://<GPU-Maschine>:10205/tts
#    EIGENE_STIMME_NAME=deine-stimme
#    EIGENE_STIMME_ERSATZ=de_thorsten
```

Danach im Chat einfach sagen: **„… mit eigener Stimme“** — oder direkt über
`POST /v1/audio/speech` mit `"voice": "deine-stimme"`.
