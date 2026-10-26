"""Instagram Content Publishing (Instagram API with Instagram Login).

Flow for a carousel: one child container per image (is_carousel_item=true) -> wait until FINISHED ->
parent CAROUSEL container -> wait -> media_publish. Single image: one container -> publish.
"""
import time
from datetime import datetime, timezone

import requests

from . import config as C, db


class IGError(RuntimeError):
    pass


def _base():
    v = f"/{C.IG_API_VERSION}" if C.IG_API_VERSION else ""
    return f"{C.IG_GRAPH_HOST}{v}"


def get_token():
    """Prefer the refreshed token stored in Supabase; fall back to the env var."""
    try:
        row = db.get_setting("ig_access_token")
        if row and row.get("value"):
            return row["value"]
    except Exception:
        pass
    if not C.IG_ACCESS_TOKEN:
        raise IGError("No Instagram access token: set IG_ACCESS_TOKEN")
    return C.IG_ACCESS_TOKEN


def refresh_token_if_needed(max_age_days=20):
    """Long-lived Instagram Login tokens last 60 days; refresh well before that and store the new one."""
    row = None
    try:
        row = db.get_setting("ig_access_token")
    except Exception:
        pass
    if row and row.get("updated_at"):
        age = datetime.now(timezone.utc) - datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
        if age.days < max_age_days:
            return False
    r = requests.get(f"{C.IG_GRAPH_HOST}/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": get_token()}, timeout=30)
    if r.status_code >= 300:
        raise IGError(f"Token refresh failed: {r.text[:300]}")
    db.set_setting("ig_access_token", r.json()["access_token"])
    return True


def _call(method, path, **params):
    params["access_token"] = get_token()
    r = requests.request(method, f"{_base()}/{path}", params=params if method == "GET" else None,
                         data=params if method == "POST" else None, timeout=60)
    data = r.json() if r.headers.get("content-type", "").startswith(("application/json", "text/javascript")) else {}
    if r.status_code >= 300 or "error" in data:
        err = data.get("error", {})
        raise IGError(f"{err.get('message', r.text[:300])} (code {err.get('code')}, subcode {err.get('error_subcode')})")
    return data


def _create(**params):
    """Create a media container; retry without alt_text if this API version rejects it."""
    try:
        return _call("POST", f"{C.IG_USER_ID}/media", **params)["id"]
    except IGError:
        if "alt_text" not in params:
            raise
        params.pop("alt_text")
        return _call("POST", f"{C.IG_USER_ID}/media", **params)["id"]


def _wait_ready(container_id, timeout_s=180):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        st = _call("GET", container_id, fields="status_code,status")
        code = st.get("status_code")
        if code in ("FINISHED", "PUBLISHED"):
            return
        if code in ("ERROR", "EXPIRED"):
            raise IGError(f"Container {container_id} {code}: {st.get('status')}")
        time.sleep(4)
    raise IGError(f"Container {container_id} not ready after {timeout_s}s")


def publishing_quota():
    """Returns (used, total) for the rolling 24h publishing limit."""
    d = _call("GET", f"{C.IG_USER_ID}/content_publishing_limit", fields="quota_usage,config")
    row = (d.get("data") or [{}])[0]
    return row.get("quota_usage", 0), (row.get("config") or {}).get("quota_total")


def publish(image_urls, caption, alt_texts=None):
    """Publish a single image or carousel. Returns (media_id, permalink)."""
    if not C.IG_USER_ID:
        raise IGError("IG_USER_ID not set")
    if not image_urls:
        raise IGError("No images")
    try:
        used, total = publishing_quota()
        if total and used >= total:
            raise IGError(f"Publishing limit reached ({used}/{total} in last 24h)")
    except IGError as e:
        if "limit reached" in str(e):
            raise
        # quota check is best-effort

    if len(image_urls) == 1:
        params = {"image_url": image_urls[0], "caption": caption}
        if alt_texts:
            params["alt_text"] = alt_texts[0]
        parent = _create(**params)
    else:
        children = []
        for i, url in enumerate(image_urls[:C.MAX_SLIDES]):
            params = {"image_url": url, "is_carousel_item": "true"}
            if alt_texts and i < len(alt_texts) and alt_texts[i]:
                params["alt_text"] = alt_texts[i]
            children.append(_create(**params))
        for cid in children:
            _wait_ready(cid)
        parent = _call("POST", f"{C.IG_USER_ID}/media", media_type="CAROUSEL",
                       children=",".join(children), caption=caption)["id"]
    _wait_ready(parent)
    media_id = _call("POST", f"{C.IG_USER_ID}/media_publish", creation_id=parent)["id"]
    permalink = None
    try:
        permalink = _call("GET", media_id, fields="permalink").get("permalink")
    except IGError:
        pass
    return media_id, permalink
