#!/usr/bin/env python3
"""Thai Reference API — MCP server (stdio JSON-RPC).

Any agent can add this as an MCP server; tools pay $0.005/call via x402
automatically using the wallet configured in env (PAYMENT_PRIVATE_KEY).

Config (env or .env file at THAI_REF_ENV path):
  PAYMENT_PRIVATE_KEY=0x...   # payer wallet (Base Sepolia USDC)
  THAI_REF_URL=https://musicians-recommend-sentence-debug.trycloudflare.com
"""
import json, os, sys, urllib.request, urllib.error

ENV_PATH = os.environ.get("THAI_REF_ENV", "/tmp/x402-demo/.env")
if os.path.exists(ENV_PATH):
    for line in open(ENV_PATH):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)

BASE_URL = os.environ.get("THAI_REF_URL", "https://musicians-recommend-sentence-debug.trycloudflare.com")

TOOLS = [
    {"name": "thai_fx", "description": "Get THB reference FX rates (USD/EUR/JPY/GBP/CNY -> THB). Paid via x402 ($0.005).",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "thai_is_business_day", "description": "Check whether a date is a Thai business day (weekends + Thai holidays). Paid via x402 ($0.005).",
     "inputSchema": {"type": "object", "properties": {"date": {"type": "string", "description": "YYYY-MM-DD"}},
                     "required": ["date"], "additionalProperties": False}},
    {"name": "thai_add_business_days", "description": "Add N Thai business days to a date, skipping weekends and Thai holidays. Paid via x402 ($0.005).",
     "inputSchema": {"type": "object", "properties": {"date": {"type": "string", "description": "YYYY-MM-DD"},
                                                      "n": {"type": "integer", "minimum": 1, "maximum": 90}},
                     "required": ["date", "n"], "additionalProperties": False}},
]
PATHS = {"thai_fx": "/fx", "thai_is_business_day": "/is-business-day", "thai_add_business_days": "/add-business-days"}


def pay_and_call(path_qs: str) -> str:
    from eth_account import Account
    from x402 import x402ClientSync
    from x402.http.utils import decode_payment_required_header, encode_payment_signature_header
    from x402.http.constants import PAYMENT_SIGNATURE_HEADER
    from x402.mechanisms.evm.exact import ExactEvmScheme

    url = BASE_URL + path_qs

    def get(headers=None):
        req = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, r, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e, e.read()

    status, resp, raw = get()
    if status != 402:
        return raw.decode()
    pr = decode_payment_required_header(resp.headers.get("PAYMENT-REQUIRED"))
    acct = Account.from_key(os.environ["PAYMENT_PRIVATE_KEY"])
    client = x402ClientSync()
    client.register(pr.accepts[0].network, ExactEvmScheme(acct))
    payload = client.create_payment_payload(pr)
    status, resp, raw = get({PAYMENT_SIGNATURE_HEADER: encode_payment_signature_header(payload)})
    if status != 200:
        raise RuntimeError(f"payment failed: {status} {raw.decode()[:200]}")
    return raw.decode()


def rpc_result(msg_id, result):
    json.dump({"jsonrpc": "2.0", "id": msg_id, "result": result}, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        m = req.get("method")
        mid = req.get("id")
        if m == "initialize":
            rpc_result(mid, {"protocolVersion": "2024-11-05",
                             "capabilities": {"tools": {}},
                             "serverInfo": {"name": "thai-ref-x402", "version": "0.1.0"}})
        elif m == "notifications/initialized":
            pass
        elif m == "tools/list":
            rpc_result(mid, {"tools": TOOLS})
        elif m == "tools/call":
            name = req["params"]["name"]
            args = req["params"].get("arguments", {})
            try:
                if name == "thai_fx":
                    out = pay_and_call(PATHS[name])
                elif name == "thai_is_business_day":
                    out = pay_and_call(f"{PATHS[name]}?date={args['date']}")
                elif name == "thai_add_business_days":
                    out = pay_and_call(f"{PATHS[name]}?date={args['date']}&n={args['n']}")
                else:
                    raise ValueError(f"unknown tool {name}")
                rpc_result(mid, {"content": [{"type": "text", "text": out}], "isError": False})
            except Exception as e:
                rpc_result(mid, {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True})
        elif m == "ping":
            rpc_result(mid, {})


if __name__ == "__main__":
    main()
