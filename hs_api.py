"""Thai Customs Tariff (HS) API — Flask blueprint.

Data: $THAICAL_HOME/hs_data.json (11,414 8-digit codes, Thai/English, MFN duty)
Source: github.com/Soe-Moe/thai-customs-tariff-json (ISC licence), Thai Customs ITD
REFTRC/REFDRT open data, effective 2022-01-01.

Endpoints:
  GET /hs/search?q=...          FREE — up to 10 hits; MFN duty on first 3 only
  GET /hs/lookup?code=01012100  PAID ($0.005 via x402, mounted by thai_ref.py)

Designed to be mounted by thai_ref.py:  app.register_blueprint(hs_bp)
The x402 payment route /hs/lookup is declared by the parent app; here everything is plain.
"""
import json
import os
import re
try:
    from unidecode import unidecode as _unidecode
except Exception:  # pragma: no cover — optional dep
    _unidecode = lambda s: s  # noqa: E731

from flask import Blueprint, jsonify, request

THAICAL_HOME = os.environ.get("THAICAL_HOME", "/workspace/thaical")
HS_DATA_FILE = THAICAL_HOME + "/hs_data.json"
FREE_SAMPLE = 3
TOP_N = 10
_THAI_RE = re.compile(r"[\u0E00-\u0E7F]")

hs_bp = Blueprint("hs", __name__, url_prefix="/hs")

with open(HS_DATA_FILE, encoding="utf-8") as f:
    RECORDS = json.load(f)

BY_CODE = {r["hs_code"]: r for r in RECORDS}


def _norm(s: str) -> str:
    """Lowercase + strip accents for EN search; Thai text used as-is (lowercased)."""
    return _unidecode(s).lower().strip()

# prebuilt lowercase search blobs: "th||en"
_SEARCH = [(r, (r["description_th"] + "||" + r["description_en"]).lower(),
            _norm(r["description_en"])) for r in RECORDS]


def _summary(r):
    return {
        "hs_code": r["hs_code"],
        "description_th": r["description_th"],
        "description_en": r["description_en"],
        "duty_mfn_percent": r["duty_mfn_percent"],
    }


@hs_bp.get("/search")
def hs_search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"error": "query parameter 'q' must be at least 2 characters"}), 400
    ql = q.lower()
    # unidecode/accents-stripping only makes sense for non-Thai queries
    qn = None if _THAI_RE.search(q) else _norm(q)
    tokens = [t for t in re.split(r"\s+", ql) if len(t) >= 2]
    # the any()-token fallback needs >=3-char tokens (2-char tokens are too noisy)
    or_tokens = [t for t in tokens if len(t) >= 3]
    # ให้คะแนน: วลีตรงเป๊ะ 5, ทุก token 3, บาง token 1 (+2 ถ้าตรงทั้งคำ)
    scored = []
    for r, blob, blobn in _SEARCH:
        if ql in blob or (qn and qn in blobn):
            s = 5
        elif tokens and all(t in blob for t in tokens):
            s = 3
        elif or_tokens and any(t in blob for t in or_tokens):
            s = 1
        else:
            continue
        for t in tokens:
            if re.search(r"(?<![a-z])" + re.escape(t) + r"(?![a-z])", blob):
                s += 2
        scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    hits = [r for _, r in scored[:TOP_N]]
    results = []
    for i, r in enumerate(hits):
        item = {"hs_code": r["hs_code"],
                "description_th": r["description_th"],
                "description_en": r["description_en"]}
        if i < FREE_SAMPLE:
            item["duty_mfn_percent"] = r["duty_mfn_percent"]
        else:
            item["duty_mfn_percent"] = None
            item["locked"] = True
        results.append(item)
    return jsonify({
        "query": q,
        "total_matches_shown": len(hits),
        "results": results,
        "note": f"MFN duty included free for the first {FREE_SAMPLE} results; "
                f"duty for the remaining hits requires the paid /hs/lookup endpoint.",
        "source": "Thai Customs ITD via Soe-Moe/thai-customs-tariff-json (ISC)",
    })


@hs_bp.get("/lookup")
def hs_lookup():
    code = (request.args.get("code") or "").strip()
    if not re.fullmatch(r"\d{8}", code):
        return jsonify({"error": "'code' must be exactly 8 digits"}), 400
    r = BY_CODE.get(code)
    if not r:
        return jsonify({"error": f"HS code {code} not found", "code": code}), 404
    return jsonify({
        "hs_code": r["hs_code"],
        "description_th": r["description_th"],
        "description_en": r["description_en"],
        "duty_mfn_percent": r["duty_mfn_percent"],
        "duty_specific_baht": r["duty_specific_baht"],
        "regime": "MFN (WTO bound/applied, effective 2022-01-01)",
        "source": "Thai Customs ITD via Soe-Moe/thai-customs-tariff-json (ISC)",
    })
