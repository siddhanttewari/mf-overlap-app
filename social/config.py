"""Central configuration for the OverlapIQ Instagram agent.

Everything secret comes from environment variables (Render env vars for the
dashboard, GitHub Actions secrets for the generator/publisher).
"""
import os
from zoneinfo import ZoneInfo


def env(name, default=None):
    v = os.environ.get(name)
    return v if v not in (None, "") else default


# --- Supabase -------------------------------------------------------------
SUPABASE_URL = (env("SUPABASE_URL") or "").rstrip("/").removesuffix("/rest/v1")
# Service-role key: needed to write drafts and upload images. Never expose to the browser.
SUPABASE_SERVICE_KEY = env("SUPABASE_SERVICE_KEY") or env("SUPABASE_SERVICE_ROLE_KEY") or env("SUPABASE_KEY")
STORAGE_BUCKET = env("SOCIAL_BUCKET", "social")
POSTS_TABLE = "ig_posts"
SETTINGS_TABLE = "ig_settings"

# --- Instagram (Instagram API with Instagram Login) -------------------------
IG_USER_ID = env("IG_USER_ID")
IG_ACCESS_TOKEN = env("IG_ACCESS_TOKEN")  # long-lived token; refreshed + stored in ig_settings
IG_GRAPH_HOST = env("IG_GRAPH_HOST", "https://graph.instagram.com")
# Leave blank to use your Meta app's default API version; set e.g. "v25.0" to pin.
IG_API_VERSION = env("IG_API_VERSION", "")

# --- Dashboard ------------------------------------------------------------
ADMIN_PASSWORD = env("SOCIAL_ADMIN_PASSWORD")
SECRET_KEY = env("FLASK_SECRET_KEY") or env("SECRET_KEY")
# Optional: lets the dashboard trigger the GitHub Action immediately ("Generate now", "Re-render")
GH_DISPATCH_TOKEN = env("GH_DISPATCH_TOKEN")
# Secret path segment for /admin/social/cron/<key> (publishing scheduler pinged by UptimeRobot)
CRON_KEY = env("SOCIAL_CRON_KEY")
GH_REPO = env("GH_REPO", "siddhanttewari/mf-overlap-app")
GH_GENERATE_WORKFLOW = env("GH_WORKER_WORKFLOW", "social-generate.yml")  # the hourly render & publish worker

# --- Content --------------------------------------------------------------
SITE_URL = env("SITE_URL", "https://overlapiq.in")
TZ = ZoneInfo("Asia/Kolkata")
# Default posting slots (IST) used by "Next free slot"
POSTING_SLOTS = [(int(h), int(m)) for h, m in
                 (s.split(":") for s in env("SOCIAL_SLOTS", "09:30,19:00").split(","))]
POSTING_DAYS = [int(d) for d in env("SOCIAL_DAYS", "0,2,4").split(",")]  # Mon, Wed, Fri

BRAND = {
    "name": "OverlapIQ",
    "handle": env("IG_HANDLE", "@overlapiq"),
    "site": "overlapiq.in",
    # Matches the overlapiq.in logo: indigo->blue and purple->pink circles on dark slate
    "bg": "#0F172A",
    "bg2": "#1E1B4B",
    "ink": "#F8FAFC",
    "muted": "#A5B4FC",
    "accent": "#818CF8",     # indigo (text highlights, numbers)
    "accent2": "#EC4899",    # pink
    "grad_a": "#6366F1", "grad_b": "#3B82F6",   # logo circle 1
    "grad_c": "#A855F7", "grad_d": "#EC4899",   # logo circle 2
    "danger": "#F87171",
    "card": "#FFFFFF",
    "card_ink": "#0F172A",
}

SLIDE_W, SLIDE_H = 1080, 1350  # 4:5 portrait, the tallest ratio IG feed allows
MAX_SLIDES = 10                 # IG carousel limit
