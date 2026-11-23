#!/bin/bash
# ThaiCal API watchdog (no_agent) — cron รันตรง ไม่ผ่าน LLM
# เช็ก: (1) /healthz 200 (ล้ม 2 ครั้งติด → restart gunicorn)
#       (2) /hs/lookup ยังตอบ 402 + PAYMENT-REQUIRED (fail-open → ALERT)
# stdout ว่าง = ปกติ = cron ไม่ส่ง Discord; พิมพ์เมื่อมีปัญหาหรือกู้เสร็จเท่านั้น
LOG=/workspace/thaical/logs/watchdog.log
STATE=/workspace/thaical/logs/watchdog_failcount
mkdir -p /workspace/thaical/logs

HEALTH=DOWN
curl -fs --max-time 10 http://127.0.0.1:8404/healthz >/dev/null 2>&1 && HEALTH=UP

PREV_HEALTH=$(cat /workspace/thaical/logs/.wd_health 2>/dev/null || echo UP)
echo "$HEALTH" > /workspace/thaical/logs/.wd_health

if [ "$HEALTH" = "UP" ]; then
  echo 0 > "$STATE"
  if [ "$PREV_HEALTH" != "UP" ]; then
    echo "✅ [ThaiCal API] กู้คืนสำเร็จ — /healthz ตอบ 200 แล้ว ($(date '+%F %T'))"
  fi
else
  FAILS=$(cat "$STATE" 2>/dev/null || echo 0)
  FAILS=$((FAILS + 1))
  echo "$FAILS" > "$STATE"
  if [ "$FAILS" -ge 2 ]; then
    echo "🚨 [ThaiCal API] /healthz ล้ม $FAILS ครั้งติด — สั่ง restart gunicorn ($(date '+%F %T'))"
    echo "$(date '+%F %T') healthz failed $FAILS times — restarting gunicorn" >> "$LOG"
    pkill -f "gunicorn.*thai_ref:app" 2>/dev/null
    sleep 2
    setsid /workspace/thaical/start.sh >/dev/null 2>&1 &
    echo "$(date '+%F %T') restart issued" >> "$LOG"
    echo 0 > "$STATE"
    echo "$HEALTH" > /workspace/thaical/logs/.wd_health   # ยัง DOWN จนกว่ารอบหน้าจะเห็น UP → รอบหน้ารายงาน recovery
  fi
fi

# payment fail-closed check: unpaid /hs/lookup ต้องได้ 402 พร้อม PAYMENT-REQUIRED header
HDR=/workspace/thaical/logs/.wd_payhdr
CODE=$(curl -s --max-time 10 -D "$HDR" -o /dev/null -w "%{http_code}" \
  "http://127.0.0.1:8404/hs/lookup?code=42023200")
if [ "$CODE" = "200" ] || { [ "$CODE" = "402" ] && ! grep -qi "^payment-required" "$HDR"; }; then
  echo "🚨 [ThaiCal API] ALERT_PAYMENT_OPEN code=$CODE — /hs/lookup ไม่บังคับชำระเงิน (ต้องเป็น 402 + PAYMENT-REQUIRED) ($(date '+%F %T'))"
  echo "$(date '+%F %T') ALERT_PAYMENT_OPEN code=$CODE" >> "$LOG"
fi
rm -f "$HDR"
exit 0
