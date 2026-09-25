#!/usr/bin/env bash
# Wartet auf das Ende eines Stimm-Auftrags und sendet danach automatisch die
# Cluster-Hoerproben per Telegram.
#
# Aufruf:  warten-und-proben.sh <dataset> [proben-je-cluster]
# Beispiel: warten-und-proben.sh konosuba 2
set -euo pipefail
CFG=${CFG:-~/.ssh/config}
NAME=${1:?Bitte Dataset-Namen angeben (z.B. konosuba)}
JE=${2:-2}
CT=${CT:-111}

K=$(ssh -F "$CFG" ai-server "pct exec $CT -- cat /opt/Applio/stimmen-dienst/schluessel.txt")
ST="unbekannt"
J="{}"
for i in $(seq 1 300); do
  J=$(ssh -F "$CFG" ai-server "pct exec $CT -- bash -lc 'curl -s \"http://127.0.0.1:8890/job?schluessel=$K\"'")
  ZEILE=$(printf '%s' "$J" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print('weg / keine Antwort'); raise SystemExit
f = d.get('fortschritt') or {}
print(d.get('status'), '|', d.get('schritt'), '|', f.get('segmente', '-'), 'Segmente', f.get('minuten', '-'), 'Min',
      '| Cluster:', ', '.join(k + '=' + str(v.get('segmente')) for k, v in (f.get('cluster') or {}).items()) or 'noch keine')
" 2>/dev/null || echo "weg / keine Antwort")
  echo "[$(date +%H:%M:%S)] $ZEILE"
  ST=$(printf '%s' "$J" | python3 -c "import sys,json; print((json.load(sys.stdin) or {}).get('status','unbekannt'))" 2>/dev/null || echo unbekannt)
  [ "$ST" = "laufend" ] || break
  sleep 60
done

echo "--- Lauf beendet mit Status: $ST"
case "$ST" in
  fertig|"fertig mit Hinweisen")
    bash "$(dirname "$0")/cluster-proben.sh" "$NAME" "$JE"
    ;;
  *)
    echo "Keine Proben gesendet (Status $ST). Letzte Logzeilen:"
    printf '%s' "$J" | python3 -c "import sys,json; d=json.load(sys.stdin); [print(' ', z[:160]) for z in (d.get('log_ende') or [])[-5:]]" 2>/dev/null || true
    ;;
esac
