#!/usr/bin/env python3
"""ThaiCal — Thai bank settlement calendar & reference APIs (x402).

REBUILT 2026-11-21 after /tmp wipe: HTML recovered verbatim from live server,
logic reconstructed. Payment (x402) auto-disables if credentials missing.
"""
import json
import os
import sys
import datetime as dt
import urllib.request
from flask import Flask, jsonify, request, send_file

app = Flask(__name__)
BASE_URL = "https://api.thaical.xyz"
THAICAL_HOME = os.environ.get("THAICAL_HOME", "/workspace/thaical")
SECRETS_DIR = os.path.join(THAICAL_HOME, "secrets")

# ---------- landing (recovered verbatim) ----------
LANDING = open(THAICAL_HOME + "/landing.html", encoding="utf-8").read() \
    if __import__("os").path.exists(THAICAL_HOME + "/landing.html") else None
DOCS = open(THAICAL_HOME + "/docs.html", encoding="utf-8").read() \
    if __import__("os").path.exists(THAICAL_HOME + "/docs.html") else None
if LANDING is None:
    LANDING = open("/tmp/recover-landing.html", encoding="utf-8").read()
if DOCS is None:
    DOCS = open("/tmp/recover-docs.html", encoding="utf-8").read()

PRICING = {
    "currency": "USDC",
    "network": "base-sepolia (testnet — mainnet coming)",
    "model": "free reference layer; HS Code lookup is live (paid via x402); KYB & WHT coming soon",
    "paid_products": [
        {"product": "HS Code lookup (/hs/lookup)", "price_per_call": "$0.005", "status": "live"},
    ],
    "paid_products_planned": [
        {"product": "Thai company KYB (DBD open data)", "price_per_call": "$0.01–0.025"},
        {"product": "Thai withholding tax engine", "price_per_call": "$0.005–0.015"},
    ],
    "payment_protocol": "x402 (HTTP 402 + EIP-3009 USDC transfer)",
    "free_endpoints": ["/fx", "/gold", "/is-business-day", "/bank-business-day",
                        "/add-business-days", "/status", "/metrics", "/sample/*",
                        "/hs/search", "/healthz"],
    "rate_limit": "60 req/min per IP",
}

@app.get("/pricing")
def pricing():
    return jsonify(PRICING)

@app.get("/logo.png")
def logo_png():
    return send_file(THAICAL_HOME + "/thaical-icon.png", mimetype="image/png", max_age=86400)

@app.get("/favicon.ico")
def favicon():
    return send_file(THAICAL_HOME + "/thaical-favicon.ico", mimetype="image/x-icon", max_age=86400)

@app.get("/")
def landing():
    return LANDING

@app.get("/docs")
def docs():
    return DOCS

# ---------- FX (ECB via frankfurter, cached 1h) ----------
_fx_cache = {"t": 0, "d": None}

def fetch_fx():
    import time as _t
    now = _t.time()
    if _fx_cache["d"] and now - _fx_cache["t"] < 3600:
        return _fx_cache["d"]
    raw = urllib.request.urlopen(urllib.request.Request(
        "https://api.frankfurter.app/latest?from=THB&to=USD,EUR,JPY,GBP,CNY"), timeout=20).read()
    d = json.loads(raw)
    _fx_cache["d"] = d
    _fx_cache["t"] = now
    return d

@app.get("/fx")
def fx():
    d = fetch_fx()
    return jsonify({"base": "THB", "date": d.get("date"),
                    "rates": {k: 1.0 / v for k, v in d["rates"].items()},  # 1 unit foreign -> THB
                    "source": "frankfurter.app (ECB)", "cached_at": _fx_cache["t"]})

_gold_cache = {"t": 0, "d": None}
GOLD_TTL = 300  # 5 min, shared by /gold and /status

def fetch_gold():
    import time as _t
    now = _t.time()
    if _gold_cache["d"] and now - _gold_cache["t"] < GOLD_TTL:
        return _gold_cache["d"]
    f = fetch_fx()
    usd_thb = 1.0 / f["rates"]["USD"]
    g = json.loads(urllib.request.urlopen(urllib.request.Request(
        "https://api.gold-api.com/price/XAU"), timeout=20).read())
    xau_usd = g.get("price") or g.get("Price")
    baht_weight = 15.244  # grams per tael
    xau_thb = xau_usd * usd_thb
    per_bw = xau_thb * baht_weight / 31.1035
    d = {"xau_usd_per_oz": xau_usd, "usd_thb": usd_thb,
         "xau_thb_per_baht_weight": round(per_bw, 2),
         "thai_965_estimate_per_baht_weight": round(per_bw * 0.965, 2),
         "note": "Derived from spot. NOT the official association price."}
    _gold_cache["d"] = d
    _gold_cache["t"] = now
    return d

@app.get("/gold")
def gold():
    return jsonify(fetch_gold())

# ---------- business days (holidays lib) ----------
try:
    import holidays as _hol
    _TH = _hol.TH(years=range(2024, 2029))
except Exception:
    _TH = {}

def _parse_date(d):
    try:
        return dt.date.fromisoformat(d)
    except (TypeError, ValueError):
        return None

@app.get("/is-business-day")
def is_biz():
    d = request.args.get("date") or dt.date.today().isoformat()
    day = _parse_date(d)
    if day is None:
        return jsonify({"error": "invalid date — expected YYYY-MM-DD"}), 400
    hol = _TH.get(day)
    return jsonify({"date": d, "is_business_day": day.weekday() < 5 and not hol,
                    "weekend": day.weekday() >= 5, "holiday_name": hol,
                    "day_name": day.strftime("%a")})

@app.get("/bank-business-day")
def bank_biz():
    d = request.args.get("date") or dt.date.today().isoformat()
    day = _parse_date(d)
    if day is None:
        return jsonify({"error": "invalid date — expected YYYY-MM-DD"}), 400
    hol = _TH.get(day)
    return jsonify({"date": d, "is_bank_business_day": day.weekday() < 5 and not hol,
                    "weekend": day.weekday() >= 5, "holiday_name": hol,
                    "day_name": day.strftime("%a"),
                    "note": "BOT convention: Mon-Fri excluding government holidays."})

@app.get("/add-business-days")
def add_biz():
    d = request.args.get("date") or dt.date.today().isoformat()
    try:
        n = int(request.args.get("n", 1))
    except ValueError:
        return jsonify({"error": "invalid n — expected an integer"}), 400
    day = _parse_date(d)
    if day is None:
        return jsonify({"error": "invalid date — expected YYYY-MM-DD"}), 400
    if n < 0:
        return jsonify({"error": "n must be >= 0"}), 400
    added = 0
    while added < n:
        day += dt.timedelta(days=1)
        if day.weekday() < 5 and day not in _TH:
            added += 1
    return jsonify({"from": d, "n": n, "result": day.isoformat()})

# ---------- free samples ----------
@app.get("/sample/<name>")
def sample(name):
    if name == "is-business-day":
        return jsonify({"date": "2026-12-11", "is_business_day": True, "weekend": False,
                        "holiday_name": None, "day_name": "Fri", "sample": True})
    if name == "bank-business-day":
        return jsonify({"date": "2026-12-31", "is_bank_business_day": False, "weekend": False,
                        "holiday_name": "วันสิ้นปี", "day_name": "Thu", "sample": True,
                        "note": "BOT convention: Mon-Fri excluding government holidays."})
    if name == "add-business-days":
        return jsonify({"from": "2026-12-25", "n": 5, "result": "2027-01-05", "sample": True})
    if name == "fx":
        return jsonify({"base": "THB", "date": "2026-11-13", "usd_thb": 33.9156,
                        "rates": {"USD": 33.9156, "EUR": 37.48, "JPY": 0.212, "GBP": 44.86, "CNY": 5.08},
                        "source": "frankfurter.app (ECB)", "sample": True})
    if name == "gold":
        return jsonify({"xau_usd_per_oz": 3896.87, "usd_thb": 33.9156,
                        "xau_thb_per_baht_weight": 8628.0,
                        "thai_965_estimate_per_baht_weight": 8326.5,
                        "note": "Derived from spot. NOT the official association price.", "sample": True})
    return jsonify({"error": "not implemented"}), 404

# ---------- status (recovered format) ----------
@app.get("/healthz")
def healthz():
    return jsonify({"ok": True})

@app.get("/status")
def status():
    today = dt.date.today().isoformat()
    try:
        f = fetch_fx(); fx_ok = f.get("date")
    except Exception:
        fx_ok = None
    try:
        fetch_gold(); gold_ok = True
    except Exception:
        gold_ok = False
    return jsonify({"service": "ThaiCal — Thai Reference API", "date": today,
                    "payment": "enabled" if PAYMENTS_ENABLED else "disabled",
                    "endpoints": {
                        "/fx": {"status": "ok" if fx_ok else "degraded", "data_date": fx_ok},
                        "/gold": {"status": "ok" if gold_ok else "degraded"},
                        "/is-business-day": {"status": "ok"},
                        "/bank-business-day": {"status": "ok"},
                        "/add-business-days": {"status": "ok"},
                        "/hs/search": {"status": "ok"},
                        "/hs/lookup": {"status": "payment_required" if PAYMENTS_ENABLED else "payment_disabled"},
                    }})

# ---------- HS blueprint (free to mount; paid via x402 when credentials exist) ----------
from hs_api import hs_bp
app.register_blueprint(hs_bp)

# ---------- x402 payment middleware (auto-disable if credentials missing) ----------
import os
PAYMENTS_ENABLED = False
if os.path.exists(SECRETS_DIR + "/.env") and os.path.exists(SECRETS_DIR + "/cdp-api-key.json"):
    try:
        from x402 import x402ClientSync  # noqa: F401 — import check
        from x402.http import HTTPFacilitatorClientSync
        from x402.server import x402ResourceServerSync
        from x402.mechanisms.evm.exact import ExactEvmServerScheme
        from x402.http.middleware.flask import payment_middleware

        env = {k.strip(): v.strip() for k, v in
               (l.split("=", 1) for l in open(SECRETS_DIR + "/.env")
                if "=" in l and not l.startswith("#")
                and not l.upper().startswith("PAYMENT_PRIVATE_KEY"))}
        # SELLER_ADDRESS is mandatory — never fall back to any payer key/address
        seller = env.get("SELLER_ADDRESS")
        if not seller:
            raise RuntimeError("SELLER_ADDRESS missing from .env (secrets dir) — "
                               "refusing to start payments (payer keys must not be used as pay-to)")
        key = json.load(open(SECRETS_DIR + "/cdp-api-key.json"))
        from cdp.x402 import create_facilitator_config
        cfg = create_facilitator_config(key["name"], key["privateKey"])
        facilitator = HTTPFacilitatorClientSync({"url": cfg["url"], "create_headers": cfg["create_headers"]})
        server = x402ResourceServerSync(facilitator)
        server.register("eip155:84532", ExactEvmServerScheme())

        def opts():
            return {"price": "$0.005", "pay_to": seller, "network": "eip155:84532"}
        routes = {
            "/hs/lookup": {
                "accepts": [{"scheme": "exact", "pay_to": seller, "price": "$0.005",
                             "network": "eip155:84532",
                             "description": "Full Thai Customs HS record + MFN duty for one 8-digit code"}],
            },
        }
        payment_middleware(app, routes, server)
        PAYMENTS_ENABLED = True
    except Exception as e:
        import traceback, sys
        with open(THAICAL_HOME + "/x402_disable.log", "w") as f:
            f.write(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
        print("x402 payment UNAVAILABLE (fail closed):", e, file=sys.stderr, flush=True)

# FAIL CLOSED: server ยังรันเพื่อ free endpoints แต่ /hs/lookup ต้องไม่เปิดฟรี
# (hs_api.hs_lookup อ่าน config นี้ — ถ้า False จะตอบ 503 {"error": "payment unavailable"})
app.config["PAYMENTS_ENABLED"] = PAYMENTS_ENABLED
if not PAYMENTS_ENABLED:
    print("x402 payments disabled — /hs/lookup returns 503 (fail closed)", file=sys.stderr, flush=True)

# ---------- WSGI guard: rate limit + metrics (ครอบ x402 middleware) ----------
import time as _time
from collections import defaultdict

RATE_LIMIT = 30         # per worker (x2 workers ≈ 60/min/IP)
WINDOW = 60
_hits = defaultdict(list)
_metrics = defaultdict(lambda: defaultdict(int))   # day -> status -> count
METRICS_FILE = THAICAL_HOME + "/metrics.jsonl"
_last_sweep = [0.0]
_LOOPBACK = ("127.0.0.1", "::1", "localhost")

def _403_response(start_response, msg):
    start_response("403 Forbidden", [("Content-Type", "application/json")])
    return [json.dumps({"error": msg}).encode()]

class _Guard:
    def __init__(self, wsgi):
        self.wsgi = wsgi
    def __call__(self, environ, start_response):
        remote = (environ.get("REMOTE_ADDR") or "?")
        # real traffic arrives via the Cloudflare tunnel — require the CF header
        # (loopback is exempt so local health checks / smoke tests work)
        ip = environ.get("HTTP_CF_CONNECTING_IP")
        if not ip:
            if remote not in _LOOPBACK:
                return _403_response(start_response, "missing CF-Connecting-IP")
            ip = remote
        ip = ip.split(",")[0].strip()
        now = _time.time()
        if now - _last_sweep[0] > 60:   # sweep empty deques at most once/min
            _last_sweep[0] = now
            for k in [k for k, v in _hits.items() if not v]:
                del _hits[k]
        q = _hits[ip]
        q[:] = [t for t in q if now - t < WINDOW]
        path = environ.get("PATH_INFO", "")
        paid_path = path.startswith("/hs/")
        if paid_path and len(q) >= RATE_LIMIT:
            day = _time.strftime("%Y-%m-%d")
            _metrics[day]["429"] += 1
            start_response("429 Too Many Requests",
                           [("Content-Type", "application/json"), ("Retry-After", "60")])
            return [b'{"error": "rate limit exceeded (60 req/min per IP)"}']
        if paid_path:
            q.append(now)

        def _log(status, headers, exc_info=None):
            code = int(status.split(" ", 1)[0])
            if path not in ("/metrics",):
                day = _time.strftime("%Y-%m-%d")
                _metrics[day][str(code)] += 1
                try:
                    with open(METRICS_FILE, "a") as f:
                        f.write(json.dumps({"t": _time.strftime("%Y-%m-%dT%H:%M:%S"),
                                            "ip": ip, "path": path, "status": code}) + "\n")
                except Exception:
                    pass
            return start_response(status, headers, exc_info)
        return self.wsgi(environ, _log)

app.wsgi_app = _Guard(app.wsgi_app)

@app.get("/metrics")
def metrics():
    day = _time.strftime("%Y-%m-%d")
    m = dict(_metrics.get(day, {}))
    m["paid_ok_ips_today"] = len({e["ip"] for e in
        (json.loads(l) for l in open(METRICS_FILE) if day in l)
        if e["path"].startswith("/hs/") and e["status"] == 200 and e["ip"] != "127.0.0.1"})
    m["payments_enabled"] = PAYMENTS_ENABLED
    return jsonify(m)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8404)
