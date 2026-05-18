"""
MF Overlap App — Backend
========================
Thin proxy to MFData.in (https://mfdata.in) with in-memory caching.

Endpoints:
  GET  /                              -> serves the frontend
  GET  /api/health                    -> health check
  GET  /api/stats                     -> total scheme/AMC counts
  GET  /api/search?q=...              -> live scheme search (deduped by family_id)
  GET  /api/holdings/<family_id>      -> holdings for a fund (cached)
  POST /api/refresh                   -> bust caches

Reliability features:
  - Browser-like User-Agent + headers (avoids upstream Cloudflare bot blocks)
  - Retry with backoff on 5xx / 522 / 524 / 429
  - Stale-cache fallback: if upstream fails but we have an older cached
    response, serve that instead of erroring
"""

import urllib.request
import urllib.parse
import urllib.error
import json
import time
from threading import Lock
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

from snapshot import SNAPSHOT_SCHEMES, SNAPSHOT_DATE

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

# Backup data source: MFapi.in for scheme list/NAVs (no holdings)
MFAPI_BASE = "https://api.mfapi.in/mf"

# ---------- Config ----------
MFDATA_BASE = "https://mfdata.in/api/v1"
HOLDINGS_TTL = 60 * 60          # 1 hour fresh
HOLDINGS_STALE_OK = 24 * 60 * 60  # serve stale up to 24h if upstream fails
SEARCH_TTL = 10 * 60            # 10 min fresh
SEARCH_STALE_OK = 6 * 60 * 60
STATS_TTL = 60 * 60
STATS_STALE_OK = 24 * 60 * 60
REQUEST_TIMEOUT = 45

# Browser-looking headers — important on Render where the outbound IP is
# shared/datacenter, and upstream Cloudflare flags non-browser User-Agents.
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://mfdata.in/",
    "Origin": "https://mfdata.in",
}

PLAN_SUFFIXES = [
    " - Direct Plan - Growth", " - Direct Plan - IDCW",
    " - Direct Plan", " - Direct Growth",
    " - Regular Plan - Growth", " - Regular Plan - IDCW",
    " - Regular Plan", " - Regular Growth",
    " - IDCW Payout", " - IDCW Reinvestment", " - IDCW",
    " Direct Plan Growth", " Direct Plan IDCW", " Direct Plan",
    " Regular Plan Growth", " Regular Plan IDCW", " Regular Plan",
]

# ---------- State ----------
_lock = Lock()
_holdings_cache = {}
_search_cache = {}
_stats_cache = {"data": None, "fetched_at": 0}


def _http_get_json(url, retries=2):
    """
    GET a URL with retries on transient upstream errors.
    Cloudflare-fronted endpoints (like mfdata.in) sometimes return 522/524
    when their origin is briefly slow; retrying after a short delay almost
    always succeeds.
    """
    delays = [0, 1.5, 3.5]
    last_err = None
    for attempt in range(retries + 1):
        if delays[min(attempt, len(delays) - 1)] > 0:
            time.sleep(delays[min(attempt, len(delays) - 1)])
        try:
            req = urllib.request.Request(url, headers=HTTP_HEADERS)
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (408, 429, 500, 502, 503, 504, 522, 524):
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
            continue
    raise last_err if last_err else RuntimeError("Unknown error")


def _fresh(entry, ttl):
    return (
        entry
        and entry.get("data") is not None
        and (time.time() - entry.get("fetched_at", 0) < ttl)
    )


def _stale_ok(entry, stale_ttl):
    return (
        entry
        and entry.get("data") is not None
        and (time.time() - entry.get("fetched_at", 0) < stale_ttl)
    )


def _strip_plan_suffix(name):
    if not name:
        return ""
    n = name.strip()
    for suf in PLAN_SUFFIXES:
        if n.endswith(suf):
            return n[: -len(suf)].strip()
    return n


# ---------- Frontend ----------
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ---------- API ----------
@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "holdings_cached": len(_holdings_cache),
        "search_cached": len(_search_cache),
        "data_source": "mfdata.in",
    })


def _snapshot_stats():
    """Synthetic stats payload when live data source is unavailable."""
    amcs = {s["amc"] for s in SNAPSHOT_SCHEMES.values()}
    return {
        "total_schemes": len(SNAPSHOT_SCHEMES),
        "total_amcs": len(amcs),
        "latest_holdings_month": SNAPSHOT_DATE,
        "_source": "snapshot",
    }


def _snapshot_search(q):
    """Search the bundled snapshot — matches by name, AMC, or category."""
    ql = (q or "").lower()
    results = []
    for fid, s in SNAPSHOT_SCHEMES.items():
        hay = f"{s['name']} {s['amc']} {s.get('category', '')}".lower()
        if ql in hay:
            results.append({
                "family_id": fid,           # negative → snapshot marker
                "name": s["name"],
                "category": s.get("category"),
                "amc": s["amc"],
                "amfi_code": None,
                "_source": "snapshot",
            })
    results.sort(key=lambda x: x["name"].lower())
    return results


def _snapshot_holdings_payload(fid):
    """Convert snapshot.SCHEMES entry into the same shape as MFData.in returns."""
    s = SNAPSHOT_SCHEMES[fid]
    return {
        "month": s.get("month", SNAPSHOT_DATE),
        "total_aum": None,
        "equity_pct": None,
        "equity_holdings": [
            {"stock_name": stock, "weight_pct": weight, "sector": None}
            for stock, weight in s["holdings"].items()
        ],
        "_source": "snapshot",
    }


@app.route("/api/stats")
def api_stats():
    with _lock:
        if _fresh(_stats_cache, STATS_TTL):
            return jsonify(_stats_cache["data"])

    try:
        resp = _http_get_json(f"{MFDATA_BASE}/stats")
        data = resp.get("data", {})
        with _lock:
            _stats_cache["data"] = data
            _stats_cache["fetched_at"] = time.time()
        return jsonify(data)
    except Exception:
        # Stale cache first, then snapshot fallback so the UI never shows hard error
        if _stale_ok(_stats_cache, STATS_STALE_OK):
            return jsonify({**_stats_cache["data"], "_stale": True})
        return jsonify(_snapshot_stats())


@app.route("/api/search")
def api_search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify([])

    key = q.lower()
    with _lock:
        cached = _search_cache.get(key)
        if _fresh(cached, SEARCH_TTL):
            return jsonify(cached["data"])

    url = f"{MFDATA_BASE}/search?q={urllib.parse.quote(q)}"
    try:
        resp = _http_get_json(url)
    except Exception:
        # Try stale cache first
        if _stale_ok(cached, SEARCH_STALE_OK):
            return jsonify(cached["data"])
        # Fall back to snapshot search so UI is never empty
        return jsonify(_snapshot_search(q))

    schemes = resp.get("data", []) if isinstance(resp, dict) else []

    by_family = {}
    for s in schemes:
        fid = s.get("family_id")
        if not fid:
            continue
        is_direct = s.get("plan_type") == "direct"
        is_growth = "Growth" in (s.get("name") or "") or "IDCW" not in (s.get("name") or "")
        priority = (1 if is_direct else 0) * 10 + (1 if is_growth else 0)
        existing = by_family.get(fid)
        if not existing or priority > existing["_priority"]:
            by_family[fid] = {
                "family_id": fid,
                "name": _strip_plan_suffix(s.get("name") or ""),
                "category": s.get("category"),
                "amc": s.get("amc_name"),
                "amfi_code": s.get("amfi_code"),
                "_priority": priority,
            }

    result = []
    for entry in by_family.values():
        entry.pop("_priority", None)
        result.append(entry)
    result.sort(key=lambda x: x["name"].lower())

    with _lock:
        _search_cache[key] = {"data": result, "fetched_at": time.time()}
    return jsonify(result)


@app.route("/api/holdings/<int:family_id>")
def api_holdings(family_id):
    # Snapshot entries use negative family_ids — serve directly from bundle
    if family_id < 0:
        if family_id in SNAPSHOT_SCHEMES:
            return jsonify(_snapshot_holdings_payload(family_id))
        return jsonify({"error": "Unknown snapshot fund"}), 404

    with _lock:
        cached = _holdings_cache.get(family_id)
        if _fresh(cached, HOLDINGS_TTL):
            return jsonify(cached["data"])

    url = f"{MFDATA_BASE}/families/{family_id}/holdings"
    try:
        resp = _http_get_json(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return jsonify({"error": "Holdings not available for this fund"}), 404
        if _stale_ok(cached, HOLDINGS_STALE_OK):
            return jsonify(cached["data"])
        return jsonify({"error": f"Upstream returned {e.code}"}), 502
    except Exception as e:
        if _stale_ok(cached, HOLDINGS_STALE_OK):
            return jsonify(cached["data"])
        return jsonify({"error": f"Upstream unavailable: {e}"}), 502

    if resp.get("status") != "success" or not resp.get("data"):
        if _stale_ok(cached, HOLDINGS_STALE_OK):
            return jsonify(cached["data"])
        return jsonify({"error": "No holdings data"}), 404

    payload = resp["data"]
    with _lock:
        _holdings_cache[family_id] = {"data": payload, "fetched_at": time.time()}
    return jsonify(payload)


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    with _lock:
        _holdings_cache.clear()
        _search_cache.clear()
        _stats_cache["data"] = None
        _stats_cache["fetched_at"] = 0
    return jsonify({"status": "refreshed"})


# ---------- Run ----------
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    is_local = os.environ.get("PORT") is None
    print()
    print("=" * 60)
    print("  MF Overlap App — backend running")
    print("=" * 60)
    print(f"  Data source : mfdata.in")
    if is_local:
        print(f"  Open in browser: http://localhost:{port}")
        print(f"  To stop: press Ctrl+C in this window")
    else:
        print(f"  Listening on port {port}")
    print("=" * 60)
    print()
    app.run(host="0.0.0.0", port=port, debug=False)
