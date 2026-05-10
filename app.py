"""
MF Overlap App — Backend (Session 3, revised: live search)
===========================================================
Thin proxy to MFData.in (https://mfdata.in).

Endpoints:
  GET  /                              -> serves the frontend
  GET  /api/health                    -> health check
  GET  /api/stats                     -> total counts (used in header pill)
  GET  /api/search?q=...              -> live scheme search (deduped by family_id)
  GET  /api/holdings/<family_id>      -> holdings for a fund (cached)
  POST /api/refresh                   -> bust caches

Architecture: live search means we hit MFData.in's /search every keystroke
(debounced on the frontend). All 14,571 schemes are now reachable instead
of only ones that fit our pre-curated category list.
"""

import urllib.request
import urllib.parse
import json
import time
from threading import Lock
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

# ---------- Config ----------
MFDATA_BASE = "https://mfdata.in/api/v1"
HOLDINGS_TTL = 60 * 60          # 1 hour
SEARCH_TTL = 10 * 60            # 10 min
STATS_TTL = 60 * 60             # 1 hour
REQUEST_TIMEOUT = 30

# Suffixes we strip from scheme names so "X Fund - Direct Plan - Growth"
# becomes just "X Fund" in the dropdown.
PLAN_SUFFIXES = [
    " - Direct Plan - Growth", " - Direct Plan - IDCW",
    " - Direct Plan", " - Direct Growth",
    " - Regular Plan - Growth", " - Regular Plan - IDCW",
    " - Regular Plan", " - Regular Growth",
    " - IDCW Payout", " - IDCW Reinvestment",
    " - IDCW",
    " Direct Plan Growth", " Direct Plan IDCW", " Direct Plan",
    " Regular Plan Growth", " Regular Plan IDCW", " Regular Plan",
]

# ---------- Cache ----------
_lock = Lock()
_holdings_cache = {}            # family_id -> {data, fetched_at}
_search_cache = {}              # query_lower -> {data, fetched_at}
_stats_cache = {"data": None, "fetched_at": 0}


def _http_get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "mf-overlap-app/0.4"})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fresh(entry, ttl):
    return (
        entry
        and entry.get("data") is not None
        and (time.time() - entry.get("fetched_at", 0) < ttl)
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


@app.route("/api/stats")
def api_stats():
    """Bare stats for the header pill."""
    with _lock:
        if not _fresh(_stats_cache, STATS_TTL):
            try:
                resp = _http_get_json(f"{MFDATA_BASE}/stats")
                _stats_cache["data"] = resp.get("data", {})
                _stats_cache["fetched_at"] = time.time()
            except Exception as e:
                if not _stats_cache["data"]:
                    return jsonify({"error": str(e)}), 502
        return jsonify(_stats_cache["data"])


@app.route("/api/search")
def api_search():
    """
    Live search proxy.
    Calls MFData.in /search, then dedupes by family_id, preferring
    Direct-plan + Growth-option variants for display.
    """
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
    except urllib.error.HTTPError as e:
        return jsonify({"error": f"Upstream returned {e.code}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    schemes = resp.get("data", []) if isinstance(resp, dict) else []

    # Dedupe by family_id. When multiple variants share a family,
    # pick the Direct + Growth one for display (it's what most investors
    # are tracking).
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
    """Holdings for a fund, cached for 1 hour."""
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
        return jsonify({"error": f"Upstream returned {e.code}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    if resp.get("status") != "success" or not resp.get("data"):
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
    # Local dev defaults; on Render/Heroku/etc., PORT is set by the platform
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
    # 0.0.0.0 lets Render route external traffic to us; on local it's still reachable as localhost
    app.run(host="0.0.0.0", port=port, debug=False)
