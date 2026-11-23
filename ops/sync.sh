#!/bin/bash
# Hourly sync (source = /workspace/thaical, target = /root/thaical backup) — LLM-free
SRC="${THAICAL_HOME:-/workspace/thaical}"
while true; do
  rsync -a --exclude '__pycache__' --exclude '*.log' --exclude 'raw/' --exclude 'archive/' \
        --exclude 'secrets/' --exclude 'logs/' --exclude 'gh.env' --exclude '.env' \
        --exclude 'cdp-api-key.json' --exclude 'metrics.jsonl' --exclude '.git' \
        "$SRC/" /root/thaical/ 2>/dev/null
  cd /root/thaical || exit 1
  git add -A 2>/dev/null
  git diff --cached --quiet 2>/dev/null || git commit -qm "auto-sync $(date '+%F %T')" 2>/dev/null
  sleep 3600
done
