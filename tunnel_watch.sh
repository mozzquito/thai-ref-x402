#!/bin/bash
# Tunnel watchdog — เรียกโดย cronjob ทุก 5 นาที
# ถ้า api.thaical.xyz ไม่ตอบ 200 ภายใน 15 วิ: ฆ่า cloudflared เก่า + สตาร์ทใหม่
LOG=/workspace/thaical/logs/tunnel_watchdog.log
CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "https://api.thaical.xyz/fx")
if [ "$CODE" = "200" ]; then
  echo "$(date '+%F %T') OK ($CODE)" >> "$LOG"
  exit 0
fi
echo "$(date '+%F %T') DOWN ($CODE) — restarting cloudflared" >> "$LOG"
TOKEN=$(python3 -c "
import json
d=json.load(open('/tmp/tunnel.json'))
print(d.get('t') or d.get('token') or list(d.values())[0])")
for PID in $(pgrep -f "cloudflared tunnel"); do kill -9 "$PID" 2>/dev/null; done
sleep 2
setsid /root/bin/cloudflared tunnel --no-autoupdate run --token "$TOKEN" >> /workspace/thaical/logs/cf-tunnel4.log 2>&1 < /dev/null &
sleep 15
CODE2=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "https://api.thaical.xyz/fx")
echo "$(date '+%F %T') after-restart ($CODE2)" >> "$LOG"
