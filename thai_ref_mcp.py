#!/usr/bin/env python3
"""ThaiCal MCP wrapper (stdio JSON-RPC 2.0) — rebuilt 2026-11-23.

Exposes Thai reference tools to MCP clients. Free endpoints only.
Run:  python3 thai_ref_mcp.py
"""
import json
import sys
import urllib.request

API = "https://api.thaical.xyz"

TOOLS = [
    {
        "name": "thai_fx",
        "description": "THB reference FX rates (USD/EUR/JPY/GBP/CNY -> THB), ECB daily, cached 1h. Free.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "thai_is_business_day",
        "description": "Is a date a Thai business day? (weekends + Thai holidays). Free.",
        "inputSchema": {"type": "object",
                        "properties": {"date": {"type": "string", "description": "YYYY-MM-DD"}},
                        "required": ["date"]},
    },
    {
        "name": "thai_bank_business_day",
        "description": "Thai bank business day check (BOT convention) — for settlement/payment dates. Free.",
        "inputSchema": {"type": "object",
                        "properties": {"date": {"type": "string", "description": "YYYY-MM-DD"}},
                        "required": ["date"]},
    },
    {
        "name": "thai_add_business_days",
        "description": "Add N Thai business days to a date, skipping weekends and Thai holidays. Free.",
        "inputSchema": {"type": "object",
                        "properties": {"date": {"type": "string", "description": "YYYY-MM-DD"},
                                        "n": {"type": "integer", "description": "days to add"}},
                        "required": ["date", "n"]},
    },
    {
        "name": "thai_hs_search",
        "description": "Search Thai customs HS 8-digit codes (TH/EN). Free preview: first 3 results with MFN duty; full duty via paid /hs/lookup ($0.005 x402).",
        "inputSchema": {"type": "object",
                        "properties": {"q": {"type": "string", "description": "Thai or English product description"}},
                        "required": ["q"]},
    },
]

def get(path):
    req = urllib.request.Request(API + path, headers={"Accept": "application/json",
                                                      "User-Agent": "ThaiCal-MCP/2.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def call_tool(name, args):
    if name == "thai_fx":
        return get("/fx")
    if name == "thai_is_business_day":
        return get("/is-business-day?date=" + args["date"])
    if name == "thai_bank_business_day":
        return get("/bank-business-day?date=" + args["date"])
    if name == "thai_add_business_days":
        return get("/add-business-days?date=" + args["date"] + "&n=" + str(args["n"]))
    if name == "thai_hs_search":
        from urllib.parse import quote
        return get("/hs/search?q=" + quote(args["q"]))
    return {"error": "unknown tool: " + str(name)}

def reply(rid, result):
    print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}), flush=True)

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = msg.get("id")
        method = msg.get("method", "")
        if method == "initialize":
            reply(rid, {
                "protocolVersion": msg.get("params", {}).get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "thaical-mcp", "version": "2.0.0"},
            })
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            reply(rid, {"tools": TOOLS})
        elif method == "tools/call":
            p = msg.get("params", {})
            try:
                out = call_tool(p.get("name"), p.get("arguments") or {})
                reply(rid, {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False)}]})
            except Exception as e:
                print(json.dumps({"jsonrpc": "2.0", "id": rid,
                                  "error": {"code": -32603, "message": str(e)}}), flush=True)
        elif method and rid is not None:
            print(json.dumps({"jsonrpc": "2.0", "id": rid,
                              "error": {"code": -32601, "message": "method not found: " + method}}), flush=True)

if __name__ == "__main__":
    main()
