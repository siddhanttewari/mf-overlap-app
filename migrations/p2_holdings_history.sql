-- ============================================================
-- OverlapIQ P2 — Monthly Portfolio Change Tracker
-- Schema migration: append-only holdings history
-- ============================================================
-- Run this ONCE in the Supabase SQL editor (project: OverlapIQ).
--
-- WHY a separate table instead of adding history to `holdings`:
--   `holdings.family_id` is POSITIONAL (the scraper assigns -(i+1) by list
--   order), so the same id can mean a different fund next month. Keying
--   history on a stable name-slug (`fund_key`) is the only way diffs stay
--   correct as the fund universe changes. This also keeps the existing
--   `holdings` table — which the analyzer + P1 watchlist depend on —
--   completely untouched.
--
-- `fund_key` normalizer (MUST stay identical in scrape_groww_v2.py and app.py):
--   lower-case  →  every run of non [a-z0-9] becomes '-'  →  trim leading/trailing '-'
--   e.g. "ICICI Pru Large & Mid Cap Fund" -> "icici-pru-large-mid-cap-fund"
-- ============================================================

create table if not exists holdings_history (
    fund_key     text     not null,   -- stable slug; survives id reshuffles
    fund_name    text     not null,   -- display name as scraped that month
    amc          text,
    stock_name   text     not null,
    weight_pct   numeric  not null,
    sector       text,
    as_of_month  text     not null,   -- 'YYYY-MM'
    primary key (fund_key, stock_name, as_of_month)
);

-- Fast paths for the diff endpoint
create index if not exists idx_hist_fundkey_month on holdings_history (fund_key, as_of_month);
create index if not exists idx_hist_month          on holdings_history (as_of_month);

-- NOTE on access: this table is read/written with the same SUPABASE_KEY the
-- app already uses for `holdings`/`schemes`. If your existing tables have RLS
-- disabled (the default for SQL-created tables), this one matches. If you have
-- RLS enabled elsewhere and rely on the service key bypassing it, no change is
-- needed — the service key bypasses RLS.

-- ------------------------------------------------------------
-- Baseline backfill: seed the CURRENT snapshot as month 1 so the
-- tracker has something the moment the next scrape lands.
-- Diffs need >= 2 months, so this gives you the baseline; the first
-- visible diff appears after the next monthly snapshot (the 10th).
--
-- Set baseline_month to the month your CURRENT snapshot represents.
-- ------------------------------------------------------------
with cfg as (
    select '2026-06'::text as baseline_month   -- <-- adjust if your live snapshot is older
)
insert into holdings_history
    (fund_key, fund_name, amc, stock_name, weight_pct, sector, as_of_month)
select
    btrim(regexp_replace(lower(s.name), '[^a-z0-9]+', '-', 'g'), '-'),
    s.name,
    s.amc,
    h.stock_name,
    h.weight_pct,
    h.sector,
    cfg.baseline_month
from holdings h
join schemes s on s.family_id = h.family_id
cross join cfg
where h.family_id < 0
on conflict (fund_key, stock_name, as_of_month) do nothing;

-- Sanity check (optional): how many funds/rows landed in the baseline
-- select as_of_month, count(distinct fund_key) funds, count(*) rows
-- from holdings_history group by as_of_month order by as_of_month;
