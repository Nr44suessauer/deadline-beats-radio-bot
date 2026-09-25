#!/usr/bin/env bash
# Trigger RVC training on a cluster folder (runs in container CT 111,
# in the background - survives closing the terminal).
#
# Call:   rvc-trainieren.sh <model> <dataset-folder> [epochs] [batch]
# Example: rvc-trainieren.sh deine-stimme /opt/Applio/assets/datasets/<more-sources>/cluster_0 150 8
#
# Log: /var/log/voices/train-<model>-<time>.log  (path will be printed)
set -euo pipefail
CT=${CT:-111}
M=${1:?model name missing}
D=${2:?dataset folder missing}
E=${3:-150}
B=${4:-8}
CFG=${CFG:-~/.ssh/config}

# 1) Place general job script into the container
ssh -F "$CFG" ai-server "pct exec $CT -- bash -s" <<'REMOTE'
set -euo pipefail
mkdir -p /opt/Applio/voices-service
cat > /opt/Applio/voices-service/train-job.sh <<'INNEN'
#!/usr/bin/env bash
# Started with M (Modelname), D (Dataset), E (Epochs), B (Batch) in the environment.
set -euo pipefail
cd /opt/Applio
echo "--- 1/4 Preparing (preprocess)"
.venv/bin/python core.py preprocess --model-name "$M" --dataset-path "$D" --sample-rate 40000 \
    --cut-preprocess Skip --normalization-mode post --cpu-cores 4
echo "--- 2/4 Features (extract, rmvpe)"
.venv/bin/python core.py extract --model-name "$M" --f0-method rmvpe --gpu 0 \
    --sample-rate 40000 --cpu-cores 4
echo "--- 3/4 Training ($E epochs)"
.venv/bin/python core.py train --model-name "$M" --total-epoch "$E" --batch-size "$B" --gpu 0 \
    --save-every-epoch 50 --save-only-latest --sample-rate 40000
echo "--- 4/4 Index"
.venv/bin/python core.py index --model-name "$M"
echo "=== DONE ==="
INNEN
chmod +x /opt/Applio/voices-service/train-job.sh
REMOTE

# 2) start training in the background
ssh -F "$CFG" ai-server "pct exec $CT -- bash -s" <<REMOTE
set -euo pipefail
mkdir -p /var/log/voices
LOG=/var/log/voices/train-$M-\$(date +%Y%m%d-%H%M%S).log
echo "=== start \$(date) | Model $M | Data $D | Epochs $E | Batch $B ===" > "\$LOG"
M='$M' D='$D' E='$E' B='$B' nohup bash /opt/Applio/voices-service/train-job.sh >> "\$LOG" 2>&1 &
sleep 2
echo "PID \$! | LOG=\$LOG"
REMOTE
