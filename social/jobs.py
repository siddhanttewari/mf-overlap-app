"""The agent's jobs. Run from GitHub Actions (or locally):

    python -m social.jobs generate          # new drafts (one per source in SOCIAL_RUN_MIX) + pending revisions
    python -m social.jobs generate --only blog --ref https://overlapiq.in/blog/xyz
    python -m social.jobs revisions         # only process posts marked 'revise' / 'rerender' in the dashboard
    python -m social.jobs publish           # publish approved posts whose scheduled time has passed
"""
import argparse
import json
import sys
import tempfile
import traceback
from datetime import datetime, timezone

from . import config as C, db, instagram, render, sources, writer


def now_utc():
    return datetime.now(timezone.utc)


def log(*a):
    print(f"[{now_utc():%H:%M:%S}]", *a, flush=True)


def render_and_upload(post_id, version, slides):
    with tempfile.TemporaryDirectory() as tmp:
        paths, overflow = render.render_slides(slides, tmp)
        urls = [db.upload_public(f"{post_id}/v{version}/{p.name}", p.read_bytes()) for p in paths]
    return urls, overflow


def create_draft(brief):
    log(f"Writing {brief['source_type']} post: {brief['title'][:80]}")
    post = writer.write_post(brief)
    row = db.insert(C.POSTS_TABLE, {
        "status": "generating", "source_type": brief["source_type"], "source_ref": brief["source_ref"],
        "source_url": brief.get("url"), "title": brief["title"][:300], "topic_summary": post["topic_summary"],
        "slides": post["slides"], "caption": post["caption"], "hashtags": post["hashtags"],
        "alt_text": post["alt_text"], "flags": post["flags"], "version": 1,
        "brief": {k: v for k, v in brief.items() if k != "material"} | {"material": brief["material"][:20000]},
        "sources": brief.get("sources") or ([brief["url"]] if brief.get("url") else []),
    })
    urls, overflow = render_and_upload(row["id"], 1, post["slides"])
    db.update(C.POSTS_TABLE, {"id": row["id"]}, {"status": "draft", "image_urls": urls, "overflow": overflow,
                                                 "updated_at": now_utc()})
    log(f"  draft {row['id']} ready ({len(urls)} slides, {len(post['flags'])} review flags)")
    return row["id"]


def generate(only=None, ref=None):
    made, errors = [], []
    mix = [only] if only else C.RUN_MIX
    for kind in mix:
        maker = sources.BRIEF_MAKERS.get(kind.strip())
        if not maker:
            continue
        try:
            brief = maker(ref) if (kind == "blog" and ref) else maker()
            if not brief:
                log(f"No fresh {kind} material, skipping")
                continue
            made.append(create_draft(brief))
        except Exception as e:
            traceback.print_exc()
            errors.append(f"{kind}: {e}")
    return made, errors


def process_revisions():
    """'revise' = rewrite with editor feedback; 'rerender' = slides edited by hand, just re-draw them."""
    rows = db.select(C.POSTS_TABLE, {"status": "in.(revise,rerender)", "order": "updated_at.asc"}, limit=10)
    for row in rows:
        try:
            version = (row.get("version") or 1) + 1
            patch = {"version": version}
            slides = row["slides"]
            if row["status"] == "revise":
                brief = row["brief"]
                log(f"Revising {row['id']} with feedback: {row.get('feedback', '')[:80]}")
                post = writer.write_post(brief, feedback=row.get("feedback"),
                                         previous={"slides": row["slides"], "caption": row["caption"]})
                slides = post["slides"]
                patch |= {k: post[k] for k in ("slides", "caption", "hashtags", "alt_text", "flags", "topic_summary")}
            urls, overflow = render_and_upload(row["id"], version, slides)
            patch |= {"image_urls": urls, "overflow": overflow, "status": "draft", "error": None,
                      "updated_at": now_utc()}
            db.update(C.POSTS_TABLE, {"id": row["id"]}, patch)
        except Exception as e:
            traceback.print_exc()
            db.update(C.POSTS_TABLE, {"id": row["id"]}, {"status": "draft", "error": f"Revision failed: {e}",
                                                         "updated_at": now_utc()})


def claim(row, from_status="approved"):
    """Atomically move a row to 'publishing' so two schedulers can never post it twice."""
    return db.update(C.POSTS_TABLE, {"id": row["id"], "status": from_status},
                     {"status": "publishing", "updated_at": now_utc()})


def publish_post(row):
    """Publish one row that has already been claimed (status='publishing')."""
    try:
        caption = writer.full_caption(row)
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
        log(f"Publishing {row['id']}: {row['title'][:60]}")
        out = publish_post(row)
        log(f"  -> {out['status']} {out.get('ig_permalink') or out.get('error') or ''}")
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("job", choices=["generate", "revisions", "publish"])
    ap.add_argument("--only", choices=list(sources.BRIEF_MAKERS))
    ap.add_argument("--ref", help="specific blog URL for --only blog")
    a = ap.parse_args(argv)
    if a.job == "generate":
        process_revisions()
        made, errors = generate(a.only, a.ref)
        log(f"Done: {len(made)} new drafts. Errors: {errors or 'none'}")
        if errors and not made:
            sys.exit(1)
    elif a.job == "revisions":
        process_revisions()
    else:
        publish_due()


if __name__ == "__main__":
    main()
