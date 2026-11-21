#!/usr/bin/env python3
"""x402 Market Tracker — ติดตามตลาด x402 โลกจาก CDP Bazaar
สแกนรายการบริการทั้งหมด จัดกลุ่มตาม keyword ในชื่อ/description
เก็บ snapshot รายวัน แล้ว diff หา "ของใหม่" + "หมวดไหนโต"
เรียก:  python3 market_tracker.py [scan|diff|report]
"""
import json, os, re, sys, time
THAICAL_HOME = os.environ.get("THAICAL_HOME", "/workspace/thaical")
from collections import Counter

SNAP_DIR = THAICAL_HOME + "/market_snapshots"
os.makedirs(SNAP_DIR, exist_ok=True)

# หมวดหมู่ตาม keyword (เรียงตามตลาดจริงจากรายงาน Turnkey/Feldspar)
CATS = {
    "web-search-scrape": ["search", "scrape", "crawl", "web", "exa", "firecrawl", "browserbase", "serp"],
    "crypto-onchain": ["crypto", "token", "chain", "defi", "dex", "coin", "nft", "wallet", "bitcoin", "eth"],
    "business-contact-kyb": ["company", "business", "contact", "lead", "enrich", "email", "crm", "kyb"],
    "social": ["social", "twitter", "x ", "linkedin", "instagram", "reddit", "telegram", "discord"],
    "ai-inference-llm": ["llm", "gpt", "inference", "model", "openai", "claude", "gemini", "ai ", "image", "video gen"],
    "dev-tools": ["code", "dev", "deploy", "host", "dns", "ssl", "github", "ci ", "test"],
    "data-reference": ["holiday", "calendar", "weather", "fx", "exchange rate", "reference", "statistic", "geo", "map"],
    "news-content": ["news", "article", "blog", "rss", "content"],
    "finance-legal-tax": ["tax", "invoice", "accounting", "payroll", "compliance", "legal", "customs", "duty", "wht"],
    "media-gen": ["tts", "stt", "voice", "speech", "music", "design", "photo"],
}

def bazaar_pages(max_pages=5):
    from x402.http import HTTPFacilitatorClientSync
    from x402.extensions.bazaar.facilitator_client import (
        BazaarExtension, ListDiscoveryResourcesParams,
    )
    from cdp.x402 import create_facilitator_config
    key = json.load(open(THAICAL_HOME + "/secrets/cdp-api-key.json"))
    cfg = create_facilitator_config(key["name"], key["privateKey"])
    fac = HTTPFacilitatorClientSync({"url": cfg["url"], "create_headers": cfg["create_headers"]})
    bz = BazaarExtension(fac)
    # SDK pagination: ListDiscoveryResourcesParams(offset=..., limit=...),
    # response.pagination carries (limit, offset, total) — ไม่ใช่ cursor
    out, seen, offset, limit = [], set(), 0, 100
    for _ in range(max_pages):
        res = bz.list_resources(ListDiscoveryResourcesParams(limit=limit, offset=offset))
        items = res.items or []
        for r in items:
            url = getattr(r, "resource", None)
            if url and url in seen:      # de-dup ตาม resource URL
                continue
            if url:
                seen.add(url)
            out.append(r)
        pg = getattr(res, "pagination", None)
        total = getattr(pg, "total", 0) if pg else 0
        offset += len(items)
        if not items or (total and offset >= total):
            break
    return out

def classify(r):
    text = " ".join(filter(None, [getattr(r, "service_name", ""), getattr(r, "description", "")])).lower()
    for cat, kws in CATS.items():
        if any(k in text for k in kws):
            return cat
    return "other"

def _acc_field(acc, name):
    """accepts[0] อาจเป็น dict หรือ object — อ่าน field แบบรองรับทั้งสองแบบ"""
    if acc is None:
        return None
    if isinstance(acc, dict):
        return acc.get(name)
    return getattr(acc, name, None)

def scan():
    today = time.strftime("%Y-%m-%d")
    try:
        items = bazaar_pages()
    except Exception as e:
        print(f"scan failed: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
    if not items:
        print("scan failed: bazaar returned 0 items — snapshot not written", file=sys.stderr)
        sys.exit(1)
    recs, seen = [], set()
    for r in items:
        url = getattr(r, "resource", None)
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        acc = (getattr(r, "accepts", None) or [None])[0]
        recs.append({"name": r.service_name, "resource": url,
                     "cat": classify(r), "amount": _acc_field(acc, "amount"),
                     "network": _acc_field(acc, "network")})
    snap = {"date": today, "scanned": time.strftime("%Y-%m-%dT%H:%M"), "total": len(recs),
            "by_cat": Counter(r["cat"] for r in recs), "items": recs}
    json.dump(snap, open(f"{SNAP_DIR}/{today}.json", "w"), ensure_ascii=False, default=dict)
    return snap

def diff():
    files = sorted(f for f in os.listdir(SNAP_DIR) if f.endswith(".json"))
    if len(files) < 2:
        return None
    prev = json.load(open(f"{SNAP_DIR}/{files[-2]}"))
    cur = json.load(open(f"{SNAP_DIR}/{files[-1]}"))
    prev_names = {r["name"] for r in prev["items"]}
    new = [r for r in cur["items"] if r["name"] not in prev_names]
    gone = prev_names - {r["name"] for r in cur["items"]}
    growth = {}
    for cat in set(list(prev["by_cat"]) + list(cur["by_cat"])):
        a, b = prev["by_cat"].get(cat, 0), cur["by_cat"].get(cat, 0)
        if b != a:
            growth[cat] = b - a
    return {"new": new, "gone": list(gone)[:10], "growth": growth,
            "prev_date": prev["date"], "cur_date": cur["date"]}

def report():
    cur = json.load(open(f"{SNAP_DIR}/{sorted(os.listdir(SNAP_DIR))[-1]}"))
    d = diff()
    L = [f"# x402 Market Tracker — {cur['date']} (สแกน {cur['scanned']})", "",
         f"รวม {cur['total']} บริการ หมวดยอดนิยม:"]
    for cat, n in Counter(cur["by_cat"]).most_common(8):
        L.append(f"- {cat}: {n}")
    if d:
        L += ["", f"## ใหม่วันนี้ ({len(d['new'])})"]
        for r in d["new"][:15]:
            amt = r.get("amount") or "?"
            L.append(f"- [{r['cat']}] {r['name']} ({amt} units · {r.get('network','')})")
        if d["growth"]:
            L += ["", "หมวดที่เปลี่ยน: " + ", ".join(f"{k}{'+' if v>0 else ''}{v}" for k, v in sorted(d["growth"].items(), key=lambda x: -abs(x[1])))]
    else:
        L.append("\n(ยังไม่มี snapshot ก่อนหน้า — รอบแรก)")
    return "\n".join(L)

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "scan":
        s = scan()
        print(f"สแกนแล้ว: {s['total']} บริการ → {SNAP_DIR}/{s['date']}.json")
    elif cmd == "diff":
        print(json.dumps(diff(), ensure_ascii=False, indent=1)[:2000])
    else:
        print(report())
