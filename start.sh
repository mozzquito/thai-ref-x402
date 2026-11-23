#!/bin/bash
# ThaiCal API start script — gunicorn from /workspace/thaical on 127.0.0.1:8404
export THAICAL_HOME=/workspace/thaical
cd /workspace/thaical || exit 1
mkdir -p logs
exec /usr/local/bin/gunicorn -w 2 --chdir /workspace/thaical -b 127.0.0.1:8404 thai_ref:app >> /workspace/thaical/logs/thai_ref.log 2>&1
