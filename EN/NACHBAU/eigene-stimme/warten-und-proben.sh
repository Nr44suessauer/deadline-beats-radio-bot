#!/usr/bin/env bash
# Waits for the end of a voice job, then automatically sends the
# cluster listening samples via Telegram.
#
# Usage:  warten-und-proben.sh <dataset> [samples-per-cluster]
# Example: warten-und-proben.sh konosuba 2
set -euo pipefail
CFG=${CFG:-~/.ssh/config}
NAME=${1:?Bitte Dataset-names angeben (z.B. konosuba)}
JE=${2:-2}
CT=${CT:-111}

K=$(ssh -F "$CFG" ai-server "pct exec $CT -- cat /opt/Applio/voices-service/key.txt")
ST="unknown"
J="{}"
for i in $(seq 1 300); do
  J=$(ssh -F "$CFG" ai-server "pct exec $CT -- bash -lc 'curl -s \"http://127.0.0.1:8890/job?key=$K\"'")
  ZEILE=$(printf '%s' "$J" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print('gone / no answer'); raise SystemExit
f = d.get('fortschritt') or {}
print(d.get('status'), '|', d.get('schritt'), '|', f.get('segments', '-'), 'Segmente', f.get('minutes', '-'), 'Min',
      '| Cluster:', ', '.join(k + '=' + str(v.get('segments')) for k, v in (f.get('cluster') or {}).items()) or 'none yet')
" 2>/dev/null || echo "weg / keine Answer")
  echo "[$(date +%H:%M:%S)] $ZEILE"
  ST=$(printf '%s' "$J" | python3 -c "import sys,json; print((json.load(sys.stdin) or {}).get('status','unknown'))" 2>/dev/null || echo unknown)
  [ "$ST" = "running" ] || break
  sleep 60
done

echo "--- run finished with status: $ST"
case "$ST" in
  done|"finished with notes")
    bash "$(dirname "$0")/cluster-proben.sh" "$NAME" "$JE"
    ;;
  *)
    echo "No samples sent (status $ST). Last log lines:"
    printf '%s' "$J" | python3 -c "import sys,json; d=json.load(sys.stdin); [print(' ', z[:160]) for z in (d.get('log_ende') or [])[-5:]]" 2>/dev/null || true
    ;;
esac
