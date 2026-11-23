#!/bin/bash
# Hourly sync: /tmp/x402-demo -> /root/thaical (LLM-free backup loop)
while true; do
  rsync -a --exclude '__pycache__' --exclude '*.log' --exclude 'raw/' /tmp/x402-demo/ /root/thaical/ 2>/dev/null
  cd /root/thaical || exit 1
  git add -A 2>/dev/null
  if ! git diff --cached --quiet 2>/dev/null; then
    git commit -qm "auto-sync $(date '+%F %T')" 2>/dev/null
  fi
  sleep 3600
done
