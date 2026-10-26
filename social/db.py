"""Tiny Supabase REST/Storage client using `requests` only (no extra deps for the Flask app)."""
import json
import requests

from . import config as C


class SupabaseError(RuntimeError):
    pass


def _headers(extra=None):
    if not (C.SUPABASE_URL and C.SUPABASE_SERVICE_KEY):
        raise SupabaseError("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
    h = {
        "apikey": C.SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {C.SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def _check(r):
    if r.status_code >= 300:
        raise SupabaseError(f"{r.status_code} {r.request.method} {r.url}: {r.text[:500]}")
    return r


# ---------------------------------------------------------------- tables ----
def select(table, params=None, limit=None):
    params = dict(params or {})
    if limit:
        params["limit"] = str(limit)
    r = requests.get(f"{C.SUPABASE_URL}/rest/v1/{table}", headers=_headers(), params=params, timeout=30)
    return _check(r).json()


def select_all(table, params=None, page=1000):
    """Paginate past PostgREST's default row cap."""
    out, start = [], 0
    while True:
        h = _headers({"Range-Unit": "items", "Range": f"{start}-{start + page - 1}"})
        r = requests.get(f"{C.SUPABASE_URL}/rest/v1/{table}", headers=h, params=params or {}, timeout=60)
        rows = _check(r).json()
        out.extend(rows)
        if len(rows) < page:
            return out
        start += page


def insert(table, row):
    r = requests.post(f"{C.SUPABASE_URL}/rest/v1/{table}", headers=_headers({"Prefer": "return=representation"}),
                      data=json.dumps(row, default=str), timeout=30)
    return _check(r).json()[0]


def update(table, match, patch):
    params = {k: f"eq.{v}" for k, v in match.items()}
    r = requests.patch(f"{C.SUPABASE_URL}/rest/v1/{table}", headers=_headers({"Prefer": "return=representation"}),
                       params=params, data=json.dumps(patch, default=str), timeout=30)
    rows = _check(r).json()
    return rows[0] if rows else None


def upsert(table, row, on_conflict):
    r = requests.post(f"{C.SUPABASE_URL}/rest/v1/{table}", params={"on_conflict": on_conflict},
                      headers=_headers({"Prefer": "resolution=merge-duplicates,return=representation"}),
                      data=json.dumps(row, default=str), timeout=30)
    return _check(r).json()


# --------------------------------------------------------------- storage ----
def upload_public(path, data: bytes, content_type="image/jpeg"):
    """Upload to the public bucket and return the public URL (Instagram fetches from it)."""
    url = f"{C.SUPABASE_URL}/storage/v1/object/{C.STORAGE_BUCKET}/{path}"
    h = _headers({"Content-Type": content_type, "x-upsert": "true", "Cache-Control": "max-age=31536000"})
    _check(requests.post(url, headers=h, data=data, timeout=60))
    return f"{C.SUPABASE_URL}/storage/v1/object/public/{C.STORAGE_BUCKET}/{path}"


# -------------------------------------------------------------- settings ----
def get_setting(key):
    rows = select(C.SETTINGS_TABLE, {"key": f"eq.{key}", "select": "value,updated_at"})
    return rows[0] if rows else None


def set_setting(key, value):
    from datetime import datetime, timezone
    upsert(C.SETTINGS_TABLE, {"key": key, "value": value,
                              "updated_at": datetime.now(timezone.utc).isoformat()}, "key")
