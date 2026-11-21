#!/bin/bash
# ThaiCal watchdog: (1) /healthz — ล้ม 2 ครั้งติดให้ restart gunicorn
#                   (2) /hs/lookup ต้องตอบ 402 + PAYMENT-REQUIRED — ถ้าได้ 200 = payment fail-open → ALERT
LOG=/workspace/thaical/logs/watchdog.log
STATE=/workspace/thaical/logs/watchdog_failcount
mkdir -p /workspace/thaical/logs
curl -fs --max-time 10 http://127.0.0.1:8404/healthz >/dev/null 2>&1
if [ $? -eq 0 ]; then
  echo 0 > "$STATE"
else
  FAILS=$(cat "$STATE" 2>/dev/null || echo 0)
  FAILS=$((FAILS + 1))
  echo "$FAILS" > "$STATE"
  if [ "$FAILS" -ge 2 ]; then
    echo "$(date '+%F %T') healthz failed $FAILS times — restarting gunicorn" >> "$LOG"
    pkill -f "gunicorn.*thai_ref:app" 2>/dev/null
    sleep 2
    setsid /workspace/thaical/start.sh >/dev/null 2>&1 &
    echo 0 > "$STATE"
    echo "$(date '+%F %T') restart issued" >> "$LOG"
  fi
fi

# payment fail-closed check: unpaid /hs/lookup ต้องได้ 402 พร้อม PAYMENT-REQUIRED header
HDR=/workspace/thaical/logs/.wd_payhdr
CODE=$(curl -s --max-time 10 -D "$HDR" -o /dev/null -w "%{http_code}" \
  "http://127.0.0.1:8404/hs/lookup?code=42023200")
if [ "$CODE" = "200" ] || { [ "$CODE" = "402" ] && ! grep -qi "^payment-required" "$HDR"; }; then
  echo "$(date '+%F %T') ALERT_PAYMENT_OPEN code=$CODE — /hs/lookup ไม่บังคับชำระเงิน (ต้องเป็น 402 + PAYMENT-REQUIRED)" >> "$LOG"
  echo "ALERT_PAYMENT_OPEN code=$CODE"
fi
rm -f "$HDR"
exit 0
