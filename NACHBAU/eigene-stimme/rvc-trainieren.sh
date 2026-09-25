#!/usr/bin/env bash
# RVC-Training auf einem Cluster-Ordner anstossen (laeuft im Container CT 111,
# im Hintergrund - ueberlebt das Schliessen des Terminals).
#
# Aufruf:   rvc-trainieren.sh <modell> <datensatz-ordner> [epochen] [batch]
# Beispiel: rvc-trainieren.sh deine-stimme /opt/Applio/assets/datasets/<weitere-quellen>/cluster_0 150 8
#
# Protokoll: /var/log/stimmen/train-<modell>-<zeit>.log  (Pfad wird ausgegeben)
set -euo pipefail
CT=${CT:-111}
M=${1:?Modellname fehlt}
D=${2:?Datensatz-Ordner fehlt}
E=${3:-150}
B=${4:-8}
CFG=${CFG:-~/.ssh/config}

# 1) Allgemeines Auftragsskript in den Container legen
ssh -F "$CFG" ai-server "pct exec $CT -- bash -s" <<'REMOTE'
set -euo pipefail
mkdir -p /opt/Applio/stimmen-dienst
cat > /opt/Applio/stimmen-dienst/train-auftrag.sh <<'INNEN'
#!/usr/bin/env bash
# Wird mit M (Modellname), D (Datensatz), E (Epochen), B (Batch) im Umfeld gestartet.
set -euo pipefail
cd /opt/Applio
echo "--- 1/4 Vorbereiten (preprocess)"
.venv/bin/python core.py preprocess --model-name "$M" --dataset-path "$D" --sample-rate 40000 \
    --cut-preprocess Skip --normalization-mode post --cpu-cores 4
echo "--- 2/4 Merkmale (extract, rmvpe)"
.venv/bin/python core.py extract --model-name "$M" --f0-method rmvpe --gpu 0 \
    --sample-rate 40000 --cpu-cores 4
echo "--- 3/4 Training ($E Epochen)"
.venv/bin/python core.py train --model-name "$M" --total-epoch "$E" --batch-size "$B" --gpu 0 \
    --save-every-epoch 50 --save-only-latest --sample-rate 40000
echo "--- 4/4 Index"
.venv/bin/python core.py index --model-name "$M"
echo "=== FERTIG ==="
INNEN
chmod +x /opt/Applio/stimmen-dienst/train-auftrag.sh
REMOTE

# 2) Training im Hintergrund starten
ssh -F "$CFG" ai-server "pct exec $CT -- bash -s" <<REMOTE
set -euo pipefail
mkdir -p /var/log/stimmen
LOG=/var/log/stimmen/train-$M-\$(date +%Y%m%d-%H%M%S).log
echo "=== Start \$(date) | Modell $M | Daten $D | Epochen $E | Batch $B ===" > "\$LOG"
M='$M' D='$D' E='$E' B='$B' nohup bash /opt/Applio/stimmen-dienst/train-auftrag.sh >> "\$LOG" 2>&1 &
sleep 2
echo "PID \$! | LOG=\$LOG"
REMOTE
