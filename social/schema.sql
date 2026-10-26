-- OverlapIQ Instagram agent: tables + public image bucket.
-- Safe to re-run.

create extension if not exists pgcrypto;

create table if not exists public.ig_posts (
  id            uuid primary key default gen_random_uuid(),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  status        text not null default 'draft'
                check (status in ('generating','draft','revise','rerender','approved','publishing',
                                  'published','failed','rejected')),
  source_type   text not null check (source_type in ('blog','data','trending')),
  source_ref    text,
  source_url    text,
  sources       jsonb not null default '[]',
  title         text,
  topic_summary text,
  slides        jsonb not null default '[]',
  caption       text not null default '',
  hashtags      jsonb not null default '[]',
  alt_text      text,
  image_urls    jsonb not null default '[]',
  overflow      jsonb not null default '[]',
  flags         jsonb not null default '[]',
  brief         jsonb,
  feedback      text,
  version       int not null default 1,
  scheduled_for timestamptz,
  published_at  timestamptz,
  ig_media_id   text,
  ig_permalink  text,
  error         text
);
create index if not exists ig_posts_status_idx on public.ig_posts (status, scheduled_for);
create index if not exists ig_posts_source_idx on public.ig_posts (source_type, source_ref);

create table if not exists public.ig_settings (
  key        text primary key,
  value      text,
  updated_at timestamptz not null default now()
);

-- Only the service-role key (server side) may touch these tables; no public policies.
alter table public.ig_posts    enable row level security;
alter table public.ig_settings enable row level security;

-- Public bucket: Instagram must be able to fetch the slide images by URL.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('social', 'social', true, 8388608, array['image/jpeg','image/png'])
on conflict (id) do update set public = true;
