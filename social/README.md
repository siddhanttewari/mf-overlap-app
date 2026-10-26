# OverlapIQ Instagram agent

Drafts Instagram carousels for @overlapiq, waits for approval in a dashboard, then posts them. No paid API keys.

```
 Claude scheduled task (daily 06:45 IST)     GitHub Action (hourly)          overlapiq.in/admin/social      Instagram
 ─ Mon & Thu: 3 new drafts                   ─ draws drafts into branded     ─ review, edit, approve,  ──▶  carousel
   (blog post · fund data · trending topic)    1080×1350 slide images          schedule, reject,               posted
 ─ every day: rewrites you asked for        ─ publishes approved posts       "rewrite with feedback"
          │ writes rows (status=render)              ▲ reads/updates rows                │
          └──────────────────────────▶  Supabase: ig_posts  ◀──────────────────────────────┘
```

- **Claude** (scheduled task "OverlapIQ Instagram drafts" in the Claude app, runs on your Claude plan) writes slide copy + captions and self-reviews them for advice language and unsupported numbers.
- **Fund-data numbers** come from the database function `ig_data_insight()` (same junk filter as the site), and the worker overwrites any chart/stat number with them, so they can't be invented.
- **GitHub Action** `social-generate.yml` ("Social: render & publish") renders slides with Playwright and publishes due posts. `social-publish.yml` is a manual fallback.
- **Dashboard** at `/admin/social`; publishing is also triggered every 5 min by an UptimeRobot ping to `/admin/social/cron/<SOCIAL_CRON_KEY>`.
- The disclaimer is appended to every caption automatically.

## Settings

Render environment: `SOCIAL_ADMIN_PASSWORD`, `FLASK_SECRET_KEY`, `SOCIAL_CRON_KEY`, `IG_USER_ID`, `IG_ACCESS_TOKEN` (Supabase uses the existing `SUPABASE_URL` / `SUPABASE_KEY`, which must be the service_role key). Optional: `GH_DISPATCH_TOKEN` (fine-grained PAT, Actions: read & write) to enable "Draw pending drafts now" and instant re-renders.

GitHub Actions secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `IG_USER_ID`, `IG_ACCESS_TOKEN`.

Optional env: `SOCIAL_DAYS` (default `0,2,4` = Mon/Wed/Fri), `SOCIAL_SLOTS` (default `09:30,19:00` IST), `IG_API_VERSION`. Brand colours: `config.py → BRAND`.

## Database (already applied to the OverlapIQ Supabase project)
`ig_posts`, `ig_settings`, public storage bucket `social`, view `ig_holdings_clean`, functions `ig_data_insight()` and helpers. See `schema.sql`.
