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
import os
import time
from threading import Lock
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

from snapshot import SNAPSHOT_SCHEMES, SNAPSHOT_DATE

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

# ---------- Supabase config (persistent cache layer) ----------
_SUPABASE_RAW = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
# Normalize: accept the base URL with OR without /rest/v1 suffix
if _SUPABASE_RAW.endswith("/rest/v1"):
    _SUPABASE_RAW = _SUPABASE_RAW[: -len("/rest/v1")]
SUPABASE_URL = _SUPABASE_RAW
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or ""
SUPABASE_ENABLED = bool(SUPABASE_URL and SUPABASE_KEY)
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN") or ""

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
REQUEST_TIMEOUT = 6              # fail fast — better to fall back than to hang
OUTAGE_COOLDOWN = 5 * 60         # if upstream fails, skip it for 5 min

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
# Circuit breaker: once MFData.in fails, skip it for OUTAGE_COOLDOWN seconds.
_upstream_outage_until = 0


# ---------- Supabase REST helpers ----------
# We use direct REST calls (no supabase-py dependency) — PostgREST is well-documented.
def _supabase_request(method, path, params=None, body=None, timeout=12):
    if not SUPABASE_ENABLED:
        raise RuntimeError("Supabase not configured (set SUPABASE_URL + SUPABASE_KEY)")
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, safe=".*,()<>=:")
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "return=minimal,resolution=merge-duplicates"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body_text = resp.read().decode("utf-8")
        if not body_text:
            return None
        return json.loads(body_text)


def supabase_search_schemes(q, limit=50):
    """Search Supabase schemes table by name / amc / category."""
    qe = q.replace("*", "").replace(",", "")
    params = {
        "select": "family_id,name,amc,category,amfi_code",
        "or": f"(name.ilike.*{qe}*,amc.ilike.*{qe}*,category.ilike.*{qe}*)",
        "limit": str(limit),
        "order": "name.asc",
    }
    return _supabase_request("GET", "schemes", params=params) or []


def supabase_get_holdings(family_id):
    """Get scheme metadata + holdings for one family_id from Supabase."""
    scheme_rows = _supabase_request("GET", "schemes", params={
        "select": "family_id,name,amc,category",
        "family_id": f"eq.{family_id}",
        "limit": "1",
    }) or []
    if not scheme_rows:
        return None
    holdings_rows = _supabase_request("GET", "holdings", params={
        "select": "stock_name,weight_pct,sector,as_of_month",
        "family_id": f"eq.{family_id}",
        "order": "weight_pct.desc",
    }) or []
    months = [h.get("as_of_month") for h in holdings_rows if h.get("as_of_month")]
    return {
        "month": months[0] if months else SNAPSHOT_DATE,
        "total_aum": None,
        "equity_pct": None,
        "equity_holdings": [
            {
                "stock_name": h["stock_name"],
                "weight_pct": float(h["weight_pct"]),
                "sector": h.get("sector"),
            }
            for h in holdings_rows
        ],
        "_source": "supabase",
    }


def supabase_count_schemes():
    """Return scheme count from Supabase (best-effort)."""
    try:
        rows = _supabase_request("GET", "schemes", params={"select": "family_id"})
        return len(rows or [])
    except Exception:
        return 0


def supabase_upsert(table, rows):
    """Bulk upsert (insert or update) rows into a Supabase table."""
    if not rows:
        return 0
    # PostgREST accepts batches; chunk to be safe
    CHUNK = 500
    inserted = 0
    for i in range(0, len(rows), CHUNK):
        _supabase_request("POST", table, body=rows[i:i + CHUNK], timeout=30)
        inserted += len(rows[i:i + CHUNK])
    return inserted


def _upstream_is_down():
    """True if we recently detected MFData.in is unreachable."""
    return time.time() < _upstream_outage_until


def _mark_upstream_down():
    """Trip the circuit breaker — skip MFData.in for the cooldown window."""
    global _upstream_outage_until
    _upstream_outage_until = time.time() + OUTAGE_COOLDOWN


def _http_get_json(url, retries=1, timeout=None):
    """
    GET with one quick retry. Default timeout is REQUEST_TIMEOUT (short)
    for user-facing calls. Pass a larger value for seed/admin work where
    we'd rather wait than fail.
    """
    t = timeout if timeout is not None else REQUEST_TIMEOUT
    last_err = None
    for attempt in range(retries + 1):
        if attempt > 0:
            time.sleep(0.4)
        try:
            req = urllib.request.Request(url, headers=HTTP_HEADERS)
            with urllib.request.urlopen(req, timeout=t) as resp:
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

    # 1) Try MFData.in for the richest stats (when available)
    if not _upstream_is_down():
        try:
            resp = _http_get_json(f"{MFDATA_BASE}/stats")
            data = resp.get("data", {})
            with _lock:
                _stats_cache["data"] = data
                _stats_cache["fetched_at"] = time.time()
            return jsonify(data)
        except Exception:
            _mark_upstream_down()

    # 2) Fall back: stale cache
    if _stale_ok(_stats_cache, STATS_STALE_OK):
        return jsonify({**_stats_cache["data"], "_stale": True})

    # 3) Supabase count (if populated)
    if SUPABASE_ENABLED:
        count = supabase_count_schemes()
        if count > 0:
            return jsonify({
                "total_schemes": count,
                "total_amcs": None,
                "latest_holdings_month": SNAPSHOT_DATE,
                "_source": "supabase",
            })

    # 4) Bundled snapshot
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

    # 1) Try Supabase first (persistent cache, always fast)
    if SUPABASE_ENABLED:
        try:
            results = supabase_search_schemes(q)
            if results:
                with _lock:
                    _search_cache[key] = {"data": results, "fetched_at": time.time()}
                return jsonify(results)
        except Exception as e:
            print(f"[supabase] search failed for '{q}': {e}")

    # 2) Circuit breaker: skip MFData.in if recently failed
    if _upstream_is_down():
        if _stale_ok(cached, SEARCH_STALE_OK):
            return jsonify(cached["data"])
        return jsonify(_snapshot_search(q))

    # 3) Try MFData.in live
    url = f"{MFDATA_BASE}/search?q={urllib.parse.quote(q)}"
    try:
        resp = _http_get_json(url)
    except Exception:
        _mark_upstream_down()
        if _stale_ok(cached, SEARCH_STALE_OK):
            return jsonify(cached["data"])
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
        # Maybe it's a snapshot ID we seeded into Supabase
        if SUPABASE_ENABLED:
            try:
                data = supabase_get_holdings(family_id)
                if data and data.get("equity_holdings"):
                    return jsonify(data)
            except Exception as e:
                print(f"[supabase] holdings failed for {family_id}: {e}")
        return jsonify({"error": "Unknown snapshot fund"}), 404

    with _lock:
        cached = _holdings_cache.get(family_id)
        if _fresh(cached, HOLDINGS_TTL):
            return jsonify(cached["data"])

    # 1) Try Supabase first (persistent cache, always fast)
    if SUPABASE_ENABLED:
        try:
            data = supabase_get_holdings(family_id)
            if data and data.get("equity_holdings"):
                with _lock:
                    _holdings_cache[family_id] = {"data": data, "fetched_at": time.time()}
                return jsonify(data)
        except Exception as e:
            print(f"[supabase] holdings failed for {family_id}: {e}")

    # 2) Circuit breaker — don't hang the user if we know upstream is down
    if _upstream_is_down():
        if _stale_ok(cached, HOLDINGS_STALE_OK):
            return jsonify(cached["data"])
        return jsonify({"error": "Live data source temporarily unavailable. Try a snapshot fund instead."}), 503

    url = f"{MFDATA_BASE}/families/{family_id}/holdings"
    try:
        resp = _http_get_json(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return jsonify({"error": "Holdings not available for this fund"}), 404
        _mark_upstream_down()
        if _stale_ok(cached, HOLDINGS_STALE_OK):
            return jsonify(cached["data"])
        return jsonify({"error": f"Upstream returned {e.code}"}), 502
    except Exception as e:
        _mark_upstream_down()
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
    global _upstream_outage_until
    with _lock:
        _holdings_cache.clear()
        _search_cache.clear()
        _stats_cache["data"] = None
        _stats_cache["fetched_at"] = 0
    _upstream_outage_until = 0  # reset circuit breaker — try upstream again
    return jsonify({"status": "refreshed"})


# ---------- Admin endpoints (token-protected) ----------
def _require_admin():
    if not ADMIN_TOKEN:
        return jsonify({"error": "ADMIN_TOKEN env var not set"}), 503
    provided = request.headers.get("X-Admin-Token") or request.args.get("token", "")
    if provided != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401
    return None


@app.route("/api/admin/status")
def admin_status():
    err = _require_admin()
    if err:
        return err
    return jsonify({
        "supabase_enabled": SUPABASE_ENABLED,
        "supabase_url": SUPABASE_URL if SUPABASE_ENABLED else None,
        "supabase_scheme_count": supabase_count_schemes() if SUPABASE_ENABLED else 0,
        "upstream_outage_active": _upstream_is_down(),
        "snapshot_count": len(SNAPSHOT_SCHEMES),
    })


@app.route("/api/admin/seed-snapshot", methods=["GET", "POST"])
def admin_seed_snapshot():
    """Populate Supabase with the bundled snapshot funds."""
    err = _require_admin()
    if err:
        return err
    if not SUPABASE_ENABLED:
        return jsonify({"error": "Supabase not configured"}), 503

    scheme_rows = []
    holdings_rows = []
    for fid, s in SNAPSHOT_SCHEMES.items():
        scheme_rows.append({
            "family_id": fid,
            "name": s["name"],
            "amc": s["amc"],
            "category": s.get("category"),
            "amfi_code": None,
        })
        for stock, weight in s["holdings"].items():
            holdings_rows.append({
                "family_id": fid,
                "stock_name": stock,
                "weight_pct": weight,
                "sector": None,
                "as_of_month": s.get("month", SNAPSHOT_DATE),
            })

    try:
        s_count = supabase_upsert("schemes", scheme_rows)
        h_count = supabase_upsert("holdings", holdings_rows)
        return jsonify({
            "status": "ok",
            "schemes_seeded": s_count,
            "holdings_seeded": h_count,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/seed-holdings-batch", methods=["GET", "POST"])
def admin_seed_holdings_batch():
    """
    Fetch holdings for a batch of funds that don't have any in Supabase yet.
    Call this repeatedly until it reports 0 funds remaining.
    Query params: ?batch_size=50  (default 50, max 100)
    """
    err = _require_admin()
    if err:
        return err
    if not SUPABASE_ENABLED:
        return jsonify({"error": "Supabase not configured"}), 503

    batch_size = min(int(request.args.get("batch_size", "50")), 100)

    # Find schemes with no holdings yet
    try:
        all_schemes = _supabase_request("GET", "schemes", params={
            "select": "family_id",
            "family_id": "gt.0",  # skip negative snapshot IDs
            "limit": "10000",
        }) or []
        existing_holdings = _supabase_request("GET", "holdings", params={
            "select": "family_id",
            "limit": "100000",
        }) or []
    except Exception as e:
        return jsonify({"error": f"Supabase query failed: {e}"}), 502

    with_holdings = {h["family_id"] for h in existing_holdings}
    pending = [s["family_id"] for s in all_schemes if s["family_id"] not in with_holdings]

    if not pending:
        return jsonify({
            "status": "complete",
            "total_schemes": len(all_schemes),
            "schemes_with_holdings": len(with_holdings),
            "remaining": 0,
        })

    batch = pending[:batch_size]
    seeded = 0
    errors = 0
    for fid in batch:
        try:
            url = f"{MFDATA_BASE}/families/{fid}/holdings"
            resp = _http_get_json(url, timeout=30, retries=2)
            if resp.get("status") != "success":
                errors += 1
                continue
            payload = resp.get("data", {})
            month = payload.get("month")
            rows = [
                {
                    "family_id": fid,
                    "stock_name": h["stock_name"],
                    "weight_pct": h["weight_pct"],
                    "sector": h.get("sector"),
                    "as_of_month": month,
                }
                for h in payload.get("equity_holdings", [])
                if h.get("stock_name") and h.get("weight_pct") is not None
            ]
            if rows:
                supabase_upsert("holdings", rows)
                seeded += 1
            time.sleep(2.2)  # rate limit politeness
        except Exception:
            errors += 1

    return jsonify({
        "status": "batch_done",
        "batch_size": len(batch),
        "seeded_this_batch": seeded,
        "errors_this_batch": errors,
        "total_remaining": len(pending) - len(batch),
        "total_schemes": len(all_schemes),
        "schemes_with_holdings": len(with_holdings) + seeded,
    })


@app.route("/api/admin/seed-from-mfdata", methods=["GET", "POST"])
def admin_seed_from_mfdata():
    """
    Seed Supabase with live MFData.in data. Use when MFData.in is back online.
    Query params:
      ?categories=Flexi+Cap,Large+Cap   (comma-sep, default: equity + hybrid)
      ?max_per_category=200             (default: 200)
      ?fetch_holdings=1                 (default: 1)
    """
    err = _require_admin()
    if err:
        return err
    if not SUPABASE_ENABLED:
        return jsonify({"error": "Supabase not configured"}), 503

    cats_param = request.args.get("categories", "")
    if cats_param:
        categories = [c.strip() for c in cats_param.split(",") if c.strip()]
    else:
        categories = [
            "Flexi Cap", "Large Cap", "Large & Mid Cap", "Mid Cap", "Small Cap",
            "Multi Cap", "ELSS", "Focused Fund", "Value Fund", "Contra Fund",
            "Index Funds", "Sectoral/Thematic", "Dividend Yield Fund",
            "Multi Asset Allocation", "Aggressive Hybrid Fund",
            "Balanced Advantage Fund", "Equity Savings",
        ]
    max_per_cat = int(request.args.get("max_per_category", "200"))
    # Default: fetch only scheme metadata (fast). Holdings is opt-in
    # because it can take 30+ minutes for thousands of funds.
    fetch_holdings = request.args.get("fetch_holdings", "0") == "1"

    families = {}
    fetched_log = []
    for cat in categories:
        try:
            url = (
                f"{MFDATA_BASE}/schemes?category={urllib.parse.quote(cat)}"
                f"&plan_type=direct&limit={max_per_cat}"
            )
            # Long timeout for seed — MFData.in can be slow when fetching
            # large category listings, but we'd rather wait than retry.
            resp = _http_get_json(url, timeout=45, retries=2)
            for s in resp.get("data", []):
                fid = s.get("family_id")
                if not fid or fid in families:
                    continue
                families[fid] = {
                    "family_id": fid,
                    "name": _strip_plan_suffix(s.get("name") or ""),
                    "amc": s.get("amc_name"),
                    "category": s.get("category") or cat,
                    "amfi_code": s.get("amfi_code"),
                }
            fetched_log.append({"category": cat, "running_total": len(families)})
            time.sleep(2.0)  # polite delay between category fetches
        except Exception as e:
            fetched_log.append({"category": cat, "error": str(e)})

    if not families:
        return jsonify({
            "status": "no_data",
            "error": "MFData.in returned no schemes — it may still be down",
            "log": fetched_log,
        }), 502

    scheme_rows = list(families.values())
    schemes_seeded = supabase_upsert("schemes", scheme_rows)

    holdings_seeded = 0
    holdings_errors = 0
    if fetch_holdings:
        for fid in families:
            try:
                url = f"{MFDATA_BASE}/families/{fid}/holdings"
                resp = _http_get_json(url, timeout=30, retries=2)
                if resp.get("status") != "success":
                    continue
                payload = resp.get("data", {})
                month = payload.get("month")
                rows = [
                    {
                        "family_id": fid,
                        "stock_name": h["stock_name"],
                        "weight_pct": h["weight_pct"],
                        "sector": h.get("sector"),
                        "as_of_month": month,
                    }
                    for h in payload.get("equity_holdings", [])
                    if h.get("stock_name") and h.get("weight_pct") is not None
                ]
                if rows:
                    supabase_upsert("holdings", rows)
                    holdings_seeded += len(rows)
                # Polite delay — MFData.in rate-limits at 30/min
                time.sleep(2.5)
            except Exception:
                holdings_errors += 1

    return jsonify({
        "status": "ok",
        "schemes_seeded": schemes_seeded,
        "holdings_seeded": holdings_seeded,
        "holdings_errors": holdings_errors,
        "categories_log": fetched_log,
    })


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
