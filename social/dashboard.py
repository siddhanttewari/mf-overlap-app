"""Approval dashboard at /admin/social — review, edit, approve/schedule, reject or send back drafts.

Wire into the main app (app.py):

    from social.dashboard import init_social
    init_social(app)
"""
import hmac
import secrets
import threading
from datetime import datetime, timedelta, timezone
from functools import wraps

import requests
from flask import (Blueprint, abort, flash, redirect, render_template, request, session, url_for)

from . import config as C, db, writer

bp = Blueprint("social", __name__, url_prefix="/admin/social", template_folder="templates")

STATUS_TABS = [
    ("draft", "To review"), ("approved", "Scheduled"), ("published", "Published"),
    ("failed", "Failed"), ("working", "In progress"), ("rejected", "Rejected"),
]
WORKING = "in.(generating,revise,rerender,publishing)"
EDIT_SKIP = {"type", "items", "unit", "n"}


# ------------------------------------------------------------------ auth ---
def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("social_admin"):
            return redirect(url_for("social.login", next=request.path))
        return fn(*a, **kw)
    return wrapper


def csrf_token():
    if "social_csrf" not in session:
        session["social_csrf"] = secrets.token_urlsafe(24)
    return session["social_csrf"]


@bp.before_request
def _csrf_check():
    if request.method == "POST" and request.endpoint != "social.login":
        if not hmac.compare_digest(request.form.get("csrf", ""), session.get("social_csrf", "")):
            abort(400, "Bad CSRF token — reload the page")


@bp.app_context_processor
def _inject():
    return {"csrf_token": csrf_token, "tabs": STATUS_TABS, "brand": C.BRAND}


@bp.route("/login", methods=["GET", "POST"])
def login():
    if not C.ADMIN_PASSWORD:
        return "Set SOCIAL_ADMIN_PASSWORD to enable the dashboard.", 503
    if request.method == "POST":
        if hmac.compare_digest(request.form.get("password", ""), C.ADMIN_PASSWORD):
            session.permanent = True
            session["social_admin"] = True
            nxt = request.args.get("next") or ""
            return redirect(nxt if nxt.startswith("/admin/social") else url_for("social.queue"))
        flash("Wrong password")
    return render_template("social/login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.pop("social_admin", None)
    return redirect(url_for("social.login"))


# --------------------------------------------------------------- helpers ---
def ist(dt_str):
    if not dt_str:
        return None
    return datetime.fromisoformat(str(dt_str).replace("Z", "+00:00")).astimezone(C.TZ)


def next_free_slot():
    taken = db.select(C.POSTS_TABLE, {"status": "in.(approved,published,publishing)", "select": "scheduled_for",
                                      "scheduled_for": f"gte.{(datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}"})
    taken = [ist(r["scheduled_for"]) for r in taken if r.get("scheduled_for")]
    t = datetime.now(C.TZ) + timedelta(minutes=30)
    for day in range(0, 60):
        d = (t + timedelta(days=day)).date()
        if d.weekday() not in C.POSTING_DAYS:
            continue
        for h, m in sorted(C.POSTING_SLOTS):
            slot = datetime(d.year, d.month, d.day, h, m, tzinfo=C.TZ)
            if slot < t:
                continue
            if all(abs((slot - x).total_seconds()) > 3 * 3600 for x in taken):
                return slot
    return t


def dispatch_workflow(inputs=None):
    """Kick the GitHub Action now instead of waiting for its schedule. Returns True if triggered."""
    if not C.GH_DISPATCH_TOKEN:
        return False
    r = requests.post(
        f"https://api.github.com/repos/{C.GH_REPO}/actions/workflows/{C.GH_GENERATE_WORKFLOW}/dispatches",
        headers={"Authorization": f"Bearer {C.GH_DISPATCH_TOKEN}", "Accept": "application/vnd.github+json"},
        json={"ref": "main", "inputs": inputs or {}}, timeout=20)
    return r.status_code == 204


def get_post(pid):
    rows = db.select(C.POSTS_TABLE, {"id": f"eq.{pid}"})
    if not rows:
        abort(404)
    return rows[0]


# ----------------------------------------------------------------- views ---
@bp.route("/")
@login_required
def queue():
    status = request.args.get("status", "draft")
    flt = WORKING if status == "working" else f"eq.{status}"
    order = "scheduled_for.asc" if status == "approved" else "updated_at.desc"
    posts = db.select(C.POSTS_TABLE, {"status": flt, "order": order,
                                      "select": "id,status,source_type,title,topic_summary,image_urls,flags,"
                                                "scheduled_for,published_at,ig_permalink,error,updated_at"}, limit=60)
    counts = {}
    for key, _ in STATUS_TABS:
        f = WORKING if key == "working" else f"eq.{key}"
        counts[key] = len(db.select(C.POSTS_TABLE, {"status": f, "select": "id"}, limit=200))
    return render_template("social/queue.html", posts=posts, status=status, counts=counts, ist=ist,
                           can_dispatch=bool(C.GH_DISPATCH_TOKEN))


@bp.route("/post/<pid>")
@login_required
def detail(pid):
    post = get_post(pid)
    return render_template("social/detail.html", p=post, ist=ist, full_caption=writer.full_caption(post),
                           next_slot=next_free_slot(), edit_skip=EDIT_SKIP)


@bp.route("/post/<pid>/action", methods=["POST"])
@login_required
def action(pid):
    post = get_post(pid)
    act = request.form.get("action")
    now = datetime.now(timezone.utc)
    patch = {"updated_at": now}

    if act in ("save", "approve_slot", "approve_at", "approve_now"):
        patch["caption"] = request.form.get("caption", post["caption"]).strip()
        patch["hashtags"] = [("#" + t.lstrip("#")) for t in request.form.get("hashtags", "").split() if t.strip("#")]

    if act == "save":
        flash("Caption saved")
    elif act == "approve_slot":
        patch |= {"status": "approved", "scheduled_for": next_free_slot().astimezone(timezone.utc)}
    elif act == "approve_at":
        try:
            when = datetime.fromisoformat(request.form["when"]).replace(tzinfo=C.TZ)
        except (KeyError, ValueError):
            flash("Pick a valid date and time"); return redirect(url_for("social.detail", pid=pid))
        patch |= {"status": "approved", "scheduled_for": when.astimezone(timezone.utc)}
    elif act == "approve_now":

        from .jobs import publish_post
        row = db.update(C.POSTS_TABLE, {"id": pid}, patch | {"status": "publishing", "scheduled_for": now})
        # Publishing a carousel can take ~30-60s (Instagram processes each image), longer than a typical
        # gunicorn worker timeout, so do it in the background; the page shows "publishing" until done.
        threading.Thread(target=publish_post, args=(row,), daemon=True).start()
        flash("Publishing to Instagram now — refresh in a minute to see the link.")
        return redirect(url_for("social.detail", pid=pid))
    elif act == "unschedule":
        patch |= {"status": "draft", "scheduled_for": None}
    elif act == "reject":
        patch |= {"status": "rejected", "feedback": request.form.get("feedback") or None}
    elif act == "revise":
        fb = (request.form.get("feedback") or "").strip()
        if not fb:
            flash("Tell the agent what to change"); return redirect(url_for("social.detail", pid=pid))
        patch |= {"status": "revise", "feedback": fb}
    elif act == "rerender":
        slides = post["slides"]
        for i, s in enumerate(slides):
            for k, v in list(s.items()):
                if k in EDIT_SKIP:
                    continue
                field = f"s{i}_{k}"
                if field in request.form:
                    val = request.form[field].strip()
                    s[k] = [x.strip() for x in val.splitlines() if x.strip()] if isinstance(v, list) else val
        patch |= {"status": "rerender", "slides": slides}
    elif act == "retry":
        patch |= {"status": "approved", "scheduled_for": now, "error": None}
    else:
        abort(400)

    db.update(C.POSTS_TABLE, {"id": pid}, patch)
    if act in ("revise", "rerender"):
        flash("Sent back to the agent — refreshing now." if dispatch_workflow({"job": "revisions"})
              else "Queued — the agent will pick it up on its next run.")
    if act.startswith("approve"):
        flash(f"Approved — scheduled for {ist(patch['scheduled_for'].isoformat()):%a %d %b, %I:%M %p} IST")
    if act in ("reject", "approve_slot", "approve_at"):
        nxt = db.select(C.POSTS_TABLE, {"status": "eq.draft", "id": f"neq.{pid}", "order": "created_at.asc",
                                        "select": "id"}, limit=1)
        if nxt:
            return redirect(url_for("social.detail", pid=nxt[0]["id"]))
        return redirect(url_for("social.queue"))
    return redirect(url_for("social.detail", pid=pid))


@bp.route("/generate", methods=["POST"])
@login_required
def generate_now():
    only = request.form.get("only") or ""
    ok = dispatch_workflow({"job": "generate", "only": only})
    flash("The agent is generating new drafts — they appear here in ~3-5 minutes." if ok
          else "Couldn't trigger the agent. Set GH_DISPATCH_TOKEN, or run the 'Social: generate' Action on GitHub.")
    return redirect(url_for("social.queue"))


_cron_lock = threading.Lock()


@bp.route("/cron/<key>")
def cron(key):
    """Ping this every 5-15 min (e.g. an UptimeRobot monitor) to publish due posts without GitHub Actions."""
    if not C.CRON_KEY or not hmac.compare_digest(key, C.CRON_KEY):
        abort(404)
    if _cron_lock.locked():
        return "busy", 200

    def run():
        with _cron_lock:
            from .jobs import publish_due
            publish_due()

    threading.Thread(target=run, daemon=True).start()
    return "ok", 200


def init_social(app):
    if not app.secret_key:
        if not C.SECRET_KEY:
            app.logger.warning("Social dashboard disabled: set FLASK_SECRET_KEY")
            return
        app.secret_key = C.SECRET_KEY
    app.config.setdefault("PERMANENT_SESSION_LIFETIME", timedelta(days=14))
    app.config.setdefault("SESSION_COOKIE_SECURE", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    app.register_blueprint(bp)
