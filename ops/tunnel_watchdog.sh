#!/bin/bash
# Tunnel watchdog (no_agent) — cron รันตรง ไม่ผ่าน LLM
# เช็ก: https://api.thaical.xyz ตอบ 200 ไหม; ถ้าไม่ → ฆ่า cloudflared เก่า + สตาร์ทใหม่
# stdout ว่าง = ปกติ = cron ไม่ส่ง Discord; พิมพ์เมื่อมีปัญหาหรือกู้เสร็จเท่านั้น
LOG=/workspace/thaical/logs/tunnel_watchdog.log
CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "https://api.thaical.xyz/fx")
PREV=$(cat /workspace/thaical/logs/.wd_tunnel 2>/dev/null || echo UP)
NOW=UP; [ "$CODE" != "200" ] && NOW=DOWN
echo "$NOW" > /workspace/thaical/logs/.wd_tunnel

if [ "$NOW" = "UP" ]; then
  if [ "$PREV" != "UP" ]; then
    echo "✅ [ThaiCal Tunnel] กู้คืนสำเร็จ — api.thaical.xyz ตอบ 200 แล้ว ($(date '+%F %T'))"
  fi
  exit 0
fi

echo "🚨 [ThaiCal Tunnel] api.thaical.xyz DOWN (code=$CODE) — restarting cloudflared ($(date '+%F %T'))"
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
if [ "$CODE2" = "200" ]; then
  echo "✅ [ThaiCal Tunnel] restart แล้วกลับมาตอบ 200 ($(date '+%F %T'))"
else
  echo "🚨 [ThaiCal Tunnel] restart แล้วยังไม่ตอบ 200 (code=$CODE2) — ต้องตามด้วยมือ ($(date '+%F %T'))"
fi
exit 0
