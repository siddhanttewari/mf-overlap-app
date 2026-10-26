# OverlapIQ Instagram agent

Drafts Instagram carousels for @overlapiq, waits for your approval in a dashboard, then posts them.

```
 GitHub Action (Mon & Thu 06:31 IST)                 overlapiq.in/admin/social            Instagram
 ┌──────────────────────────────────────┐            ┌──────────────────────────┐         ┌─────────┐
 │ sources: new blog post │ fund data │ │  drafts    │ review · edit caption    │ approve │ carousel│
 │          trending topic (web search)│ ─────────▶ │ edit slide text          │ ──────▶ │ posted  │
 │ Claude writes slides + caption      │ (Supabase) │ "rewrite with feedback"  │ (cron)  │         │
 │ Claude reviews for advice/unsourced │ ◀───────── │ reject                   │         │         │
 │ Playwright renders branded JPEGs    │  revisions └──────────────────────────┘         └─────────┘
 └──────────────────────────────────────┘
```

- **Blog** → newest overlapiq.in/blog post not yet posted, from `sitemap.xml`.
- **Data** → computed from the `holdings`/`schemes` tables: overlap between two funds, average overlap inside a category, or most-held stocks. All numbers on the slides come from code; Claude only writes the words around them.
- **Trending** → Claude searches the web for the past week's Indian investing news and picks an educational angle (never tips or calls).
- Every draft gets an automatic compliance pass (advice language, unsupported numbers, recent price data) shown as flags in the dashboard. The disclaimer is appended to every caption.

## Files

| Path | What it does |
|---|---|
| `social/jobs.py` | Entry point: `generate`, `revisions`, `publish` |
| `social/sources.py` | Blog / fund-data / trending briefs |
| `social/writer.py` | Prompts, slide schema, compliance review, final caption |
| `social/render.py` + `templates/slides.html.j2` | Branded 1080×1350 slides → JPEG |
| `social/instagram.py` | Carousel publishing, quota check, token refresh |
| `social/dashboard.py` + `templates/social/` | Approval dashboard (Flask blueprint) |
| `social/schema.sql` | `ig_posts`, `ig_settings`, public `social` bucket (**already applied** to the OverlapIQ Supabase project) |
| `.github/workflows/social-generate.yml` | Drafts twice a week + on demand |
| `.github/workflows/social-publish.yml` | Backup publisher every 2 h |

## Setup (about 30 minutes)

### 1. Instagram access (one time)
1. In the Instagram app, make @overlapiq a **Professional account** (Creator or Business). Personal accounts can't publish via the API.
2. At developers.facebook.com → **Create app** → use case **"Manage messaging & content on Instagram"** (this is the *Instagram API with Instagram Login*; no Facebook Page needed).
3. In the app → Instagram → **API setup with Instagram login** → *Add account* → log in as @overlapiq → **Generate token**. Make sure the permissions include `instagram_business_basic` and `instagram_business_content_publish`.
4. Copy the token (`IG_ACCESS_TOKEN`). Get your user id by opening
   `https://graph.instagram.com/me?fields=user_id,username&access_token=TOKEN` → `user_id` is `IG_USER_ID`.
5. The app can stay in development mode: you're publishing to an account that has a role on the app. The agent refreshes the 60-day token automatically and stores the new one in `ig_settings`.

### 2. Upload the code
Upload the `social/` folder and the two files in `.github/workflows/` to `mf-overlap-app` (GitHub → Add file → Upload files, as usual).

### 3. Plug the dashboard into the app
In `app.py`, after `app = Flask(...)`:

```python
try:
    from social.dashboard import init_social
    init_social(app)
except Exception as e:  # never let the social dashboard take the site down
    app.logger.warning(f"Social dashboard not loaded: {e}")
```

Add to `robots.txt`: `Disallow: /admin/`

### 4. Render environment variables
| Name | Value |
|---|---|
| `SUPABASE_URL` | `https://luujyffaewocvzhzlcax.supabase.co` |
| `SUPABASE_SERVICE_KEY` | Supabase → Settings → API → **service_role** key (not the anon key) |
| `SOCIAL_ADMIN_PASSWORD` | a long password for the dashboard |
| `FLASK_SECRET_KEY` | any long random string (skip if the app already sets `app.secret_key`) |
| `SOCIAL_CRON_KEY` | a long random string (secret part of the publish URL) |
| `IG_USER_ID`, `IG_ACCESS_TOKEN` | from step 1 |
| `GH_DISPATCH_TOKEN` | *optional*: fine-grained PAT on mf-overlap-app with **Actions: Read & write** — enables the "Generate drafts" button and instant re-renders |

### 5. GitHub secrets (repo → Settings → Secrets and variables → Actions)
`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `ANTHROPIC_API_KEY`, `IG_USER_ID`, `IG_ACCESS_TOKEN`.
Optional *variables*: `CLAUDE_MODEL` (default `claude-sonnet-5-5`), `IG_HANDLE` (default `@overlapiq`).

### 6. Publishing scheduler
Add an UptimeRobot HTTP monitor (5-minute interval) for
`https://overlapiq.in/admin/social/cron/<SOCIAL_CRON_KEY>`.
It publishes any approved post whose time has come. The GitHub `social-publish` workflow is a 2-hourly backup; each post is claimed atomically so they never double-post.

### 7. First run
GitHub → Actions → **Social: generate Instagram drafts** → *Run workflow*. In ~5 minutes, drafts appear at **overlapiq.in/admin/social**.

## Using the dashboard
- **Approve · next slot** puts it in the next free slot (Mon/Wed/Fri at 09:30 or 19:00 IST, at least 3 h from other posts). Or pick a time, or **Post now**.
- **Edit slide text** → *Save & re-render* redraws the slides with your wording (no AI involved).
- **Rewrite with feedback** sends it back to Claude with your note (e.g. "hook should speak to first-time SIP investors").
- After approving or rejecting, the next draft opens automatically, so you can clear the queue in one pass on your phone.

## Tuning (env vars, all optional)
| Name | Default | |
|---|---|---|
| `SOCIAL_RUN_MIX` | `blog,data,trending` | sources per run (one draft each) |
| `SOCIAL_DAYS` | `0,2,4` | posting days, 0 = Monday |
| `SOCIAL_SLOTS` | `09:30,19:00` | posting times, IST |
| `IG_API_VERSION` | app default | pin e.g. `v25.0` |
| Brand colours/handle | `config.py → BRAND` | |

## Cost
Per run: 3 drafts ≈ 6 Claude calls plus up to 6 web searches. GitHub Actions: ~4 min per generate run (8 runs/month) and ~1 min per backup publish run (~360 min/month; drop it if the UptimeRobot ping is enough).
