#!/usr/bin/env bash
# Checks the nodes that store the result and build the answer:
# - an empty follow-up response must not delete a usable output
# (exactly that happened on 2026-09-20 with the selection list)
# - a follow-up question is displayed and equipped with buttons, not “followed up”
# Call:  bash answer-test.sh
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p /tmp/js
for N in ERGEBNIS_SAMMELN_JS ERSATZ_ANTWORT_JS APPEND_COLLECT_JS CHECK_READ_JS ANSWER_BUILD_JS; do
  python3 js-fetch.py agent-wf-build.py "$N" > "/tmp/js/$N.js"
done

node answer-test.js
