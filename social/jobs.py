"""GitHub Actions worker: draws drafts into slide images and publishes approved posts. No AI involved.

Drafts are written by a scheduled Claude task, which inserts rows into ig_posts with status 'render'.

    python -m social.jobs work       # render pending drafts + publish posts that are due (hourly)
    python -m social.jobs render     # only render
    python -m social.jobs publish    # only publish
    python -m social.jobs pending    # exit 0 if anything needs rendering (lets the workflow skip installing Chromium)
"""
import argparse
import sys
import tempfile
import traceback
from datetime import datetime, timezone

from . import config as C, db, instagram, posts, render


def now_utc():
    return datetime.now(timezone.utc)


def log(*a):
    print(f"[{now_utc():%H:%M:%S}]", *a, flush=True)


RENDER_STATUSES = "in.(render,rerender)"


def render_and_upload(post_id, version, slides):
    with tempfile.TemporaryDirectory() as tmp:
        paths, overflow = render.render_slides(slides, tmp)
        urls = [db.upload_public(f"{post_id}/v{version}/{p.name}", p.read_bytes()) for p in paths]
    return urls, overflow


def render_pending():
    rows = db.select(C.POSTS_TABLE, {"status": RENDER_STATUSES, "order": "updated_at.asc"}, limit=10)
    for row in rows:
        try:
            # Version bump only when re-drawing something already drawn (keeps old image URLs intact)
            version = (row.get("version") or 1) + (1 if row.get("image_urls") else 0)
            insight = (row.get("brief") or {}).get("insight")
            clean = posts.normalize(row, insight)
            log(f"Rendering {row['id']} v{version}: {(row.get('title') or '')[:60]}")
            urls, overflow = render_and_upload(row["id"], version, clean["slides"])
            db.update(C.POSTS_TABLE, {"id": row["id"]}, {
                "slides": clean["slides"], "hashtags": clean["hashtags"], "image_urls": urls,
                "overflow": overflow, "version": version, "status": "draft", "error": None,
                "updated_at": now_utc()})
        except Exception as e:
            traceback.print_exc()
            db.update(C.POSTS_TABLE, {"id": row["id"]}, {"status": "draft" if row.get("image_urls") else "failed",
                                                         "error": f"Rendering failed: {e}"[:1000],
                                                         "updated_at": now_utc()})
    return rows


def claim(row, from_status="approved"):
    """Atomically move a row to 'publishing' so two schedulers can never post it twice."""
    return db.update(C.POSTS_TABLE, {"id": row["id"], "status": from_status},
                     {"status": "publishing", "updated_at": now_utc()})


def publish_post(row):
    """Publish one row that has already been claimed (status='publishing')."""
    try:
        caption = posts.full_caption(row)
        alts = [row.get("alt_text")] + [None] * (len(row["image_urls"]) - 1)
        media_id, permalink = instagram.publish(row["image_urls"], caption, alts)
        return db.update(C.POSTS_TABLE, {"id": row["id"]}, {
            "status": "published", "ig_media_id": media_id, "ig_permalink": permalink,
            "published_at": now_utc(), "error": None, "updated_at": now_utc()})
    except Exception as e:
        traceback.print_exc()
        return db.update(C.POSTS_TABLE, {"id": row["id"]}, {"status": "failed", "error": str(e)[:1000],
                                                            "updated_at": now_utc()})


def publish_due():
    try:
        if instagram.refresh_token_if_needed():
            log("Instagram token refreshed")
    except Exception as e:
        log(f"Token refresh skipped: {e}")
    rows = db.select(C.POSTS_TABLE, {"status": "eq.approved", "scheduled_for": f"lte.{now_utc().isoformat()}",
                                     "order": "scheduled_for.asc"}, limit=3)
    for row in rows:
        if not claim(row):
            continue  # another runner got it
        log(f"Publishing {row['id']}: {(row.get('title') or '')[:60]}")
        out = publish_post(row)
        log(f"  -> {out['status']} {out.get('ig_permalink') or out.get('error') or ''}")
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("job", choices=["work", "render", "publish", "pending"])
    a = ap.parse_args(argv)
    if a.job == "pending":
        n = len(db.select(C.POSTS_TABLE, {"status": RENDER_STATUSES, "select": "id"}, limit=1))
        print("render-needed" if n else "nothing-to-render")
        sys.exit(0 if n else 1)
    if a.job in ("work", "render"):
        render_pending()
    if a.job in ("work", "publish"):
        publish_due()


if __name__ == "__main__":
    main()
