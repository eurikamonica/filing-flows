-- Filing Flows accounts: run once in the Supabase SQL editor (cloud or self-hosted).
-- Sign-in is passwordless (a 6-digit code by e-mail); each signed-in user owns one row of preferences.

create extension if not exists pgcrypto;

create table if not exists public.subscriptions (
  user_id      uuid primary key references auth.users (id) on delete cascade,
  email        text not null,                           -- always copied from the account (see trigger)
  tickers      text[]  not null default '{}',           -- followed companies, e.g. {AAPL,MU}
  sectors      text[]  not null default '{}',           -- followed sector ids, e.g. {technology}
  all_above    boolean not null default false,          -- every company with quarterly revenue >= min_revenue
  min_revenue  bigint  not null default 1000000000,
  starred      boolean not null default false,          -- the site's starred list
  frequency    text    not null default 'daily' check (frequency in ('instant', 'daily')),
  digest_hour  smallint not null default 8,               -- the daily report's hour, in the reader's time zone
  daily_scope  text    not null default 'follows' check (daily_scope in ('follows', 'all')),   -- the daily report: the
                                                        -- companies followed, or every company that filed (full report)
  tz           text,                                    -- the reader's time zone (from the browser), e.g. Asia/Shanghai
  email_on     boolean not null default true,
  push_on      boolean not null default true,           -- Android app notifications
  final_too    boolean not null default true,           -- after an 8-K chart, also send the 10-Q/10-K version
  chart_q      boolean not null default false,          -- also the chart compared with the previous quarter
  chart_y      boolean not null default false,          -- also the chart compared with the same quarter a year earlier
  chart_history boolean not null default false,         -- also the multi-quarter history chart
  attach_images text   not null default 'png' check (attach_images in ('png', 'jpg', 'none')),   -- chart files attached
  attach_pdf   boolean not null default true,           -- a PDF report attached (profile, charts, analysis)
  cmp_decreases boolean not null default false,         -- comparison charts also draw decreases (hatched, dashed)
  changes_detail boolean not null default false,        -- list every line's change, not only the three main ones
  custom_compare boolean not null default false,        -- company pages offer "compare any two periods"
  fcf_basis    text    not null default 'company' check (fcf_basis in ('company', 'noted', 'ocf')),   -- free cash flow: the
                                                        -- company's own figure where it can be drawn ('noted': and say why
                                                        -- when it is not), or operating cash flow − capex for every company
  chart_drag_zoom boolean not null default false,       -- company pages: drag charts with the mouse, wheel to zoom
  lines_unmatched boolean not null default false,       -- show revenue lines that add up to neither total, with the gap
  unsub_token  uuid    not null default gen_random_uuid(),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

-- added after the first release: keeps older projects in step when this file is run again
alter table public.subscriptions add column if not exists final_too boolean not null default true;
alter table public.subscriptions add column if not exists chart_q boolean not null default false;
alter table public.subscriptions add column if not exists chart_y boolean not null default false;
alter table public.subscriptions add column if not exists chart_history boolean not null default false;
alter table public.subscriptions add column if not exists attach_images text not null default 'png';
alter table public.subscriptions add column if not exists attach_pdf boolean not null default true;
alter table public.subscriptions add column if not exists cmp_decreases boolean not null default false;
alter table public.subscriptions add column if not exists changes_detail boolean not null default false;
alter table public.subscriptions add column if not exists custom_compare boolean not null default false;
alter table public.subscriptions add column if not exists digest_hour smallint not null default 8;
alter table public.subscriptions add column if not exists tz text;
alter table public.subscriptions add column if not exists daily_scope text not null default 'follows';
alter table public.subscriptions add column if not exists fcf_basis text not null default 'company';
alter table public.subscriptions add column if not exists chart_drag_zoom boolean not null default false;
alter table public.subscriptions add column if not exists lines_unmatched boolean not null default false;
alter table public.subscriptions alter column frequency set default 'daily';   -- new accounts: the 8:00 daily report
do $$ begin
  alter table public.subscriptions add constraint subscriptions_attach_images_check check (attach_images in ('png', 'jpg', 'none'));
exception when duplicate_object then null;
end $$;
do $$ begin
  alter table public.subscriptions add constraint subscriptions_digest_check check (digest_hour between 0 and 23 and length(tz) <= 64);
exception when duplicate_object then null;
end $$;
do $$ begin
  alter table public.subscriptions add constraint subscriptions_daily_scope_check check (daily_scope in ('follows', 'all'));
exception when duplicate_object then null;
end $$;
alter table public.subscriptions drop constraint if exists subscriptions_fcf_basis_check;   -- re-made: choices may grow
alter table public.subscriptions add constraint subscriptions_fcf_basis_check check (fcf_basis in ('company', 'noted', 'ocf'));

-- what each user has already been sent (written by the notifier with the secret key only)
create table if not exists public.deliveries (
  user_id  uuid not null references auth.users (id) on delete cascade,
  item     text not null,                               -- "<cik>:<quarter end>"
  sent_at  timestamptz not null default now(),
  primary key (user_id, item)
);

alter table public.subscriptions enable row level security;
alter table public.deliveries enable row level security;   -- no policies: invisible to the website and app

drop policy if exists "read own" on public.subscriptions;
drop policy if exists "insert own" on public.subscriptions;
drop policy if exists "update own" on public.subscriptions;
drop policy if exists "delete own" on public.subscriptions;
create policy "read own"   on public.subscriptions for select using (auth.uid() = user_id);
create policy "insert own" on public.subscriptions for insert with check (auth.uid() = user_id);
create policy "update own" on public.subscriptions for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "delete own" on public.subscriptions for delete using (auth.uid() = user_id);

-- a user cannot point their reports at someone else's inbox: the address always comes from the signed-in account
create or replace function public.subscriptions_lock_email() returns trigger
language plpgsql security definer set search_path = public, auth as $$
begin
  select u.email into new.email from auth.users u where u.id = new.user_id;
  new.updated_at := now();
  if tg_op = 'INSERT' then                    -- the unsubscribe token and start date are never chosen by the client
    new.unsub_token := gen_random_uuid();
    new.created_at := now();
  else
    new.unsub_token := old.unsub_token;
    new.created_at := old.created_at;
  end if;
  return new;
end $$;

create unique index if not exists subscriptions_unsub_token on public.subscriptions (unsub_token);

drop trigger if exists subscriptions_lock_email on public.subscriptions;
create trigger subscriptions_lock_email before insert or update on public.subscriptions
  for each row execute function public.subscriptions_lock_email();

-- one-click unsubscribe from the link in every e-mail (works without signing in)
create or replace function public.unsubscribe(token uuid) returns boolean
language sql security definer set search_path = public as $$
  with u as (update public.subscriptions set email_on = false, updated_at = now() where unsub_token = token returning 1)
  select exists (select 1 from u);
$$;
revoke all on function public.unsubscribe(uuid) from public;
grant execute on function public.unsubscribe(uuid) to anon, authenticated;

-- "Delete my account" on the alerts page: removes the sign-in and, through the foreign keys, every row about the user
create or replace function public.delete_account() returns boolean
language sql security definer set search_path = public, auth as $$
  with d as (delete from auth.users where id = auth.uid() returning 1)
  select exists (select 1 from d);
$$;
revoke all on function public.delete_account() from public;
grant execute on function public.delete_account() to authenticated;

-- "Email me this report": a signed-in reader asks for any quarter on the site; the sender mails it to their own address
create table if not exists public.send_requests (
  id          bigint generated always as identity primary key,
  user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
  cik         integer not null check (cik > 0),
  period_end  date not null,
  status      text not null default 'pending' check (status in ('pending', 'sending', 'sent', 'failed')),
  attempts    integer not null default 0,
  error       text,
  created_at  timestamptz not null default now(),
  claimed_at  timestamptz,
  sent_at     timestamptz
);
alter table public.send_requests add column if not exists kind text not null default 'q';
-- kinds: q a quarter, fy a fiscal year, thread the X thread of a quarter (site owner only), day the daily report of one
-- filing date (period_end; cik 0)
alter table public.send_requests drop constraint if exists send_requests_kind_check;
alter table public.send_requests add constraint send_requests_kind_check check (kind in ('q', 'fy', 'thread', 'day'));
alter table public.send_requests drop constraint if exists send_requests_cik_check;
alter table public.send_requests add constraint send_requests_cik_check check (cik > 0 or (kind = 'day' and cik = 0));
drop index if exists public.send_requests_one_pending;       -- a quarter and a fiscal year can end on the same day
create unique index if not exists send_requests_one_pending_kind on public.send_requests (user_id, cik, period_end, kind)
  where status in ('pending', 'sending');
create index if not exists send_requests_status on public.send_requests (status, created_at);

alter table public.send_requests enable row level security;
drop policy if exists "read own requests" on public.send_requests;
drop policy if exists "ask for reports" on public.send_requests;
create policy "read own requests" on public.send_requests for select using (auth.uid() = user_id);
-- the insert policy ("ask for reports") is created further down, after public.am_i_owner()

-- a request starts pending, and at most 30 reports a day per reader (it only ever goes to their own inbox)
create or replace function public.send_requests_guard() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  new.status := 'pending'; new.attempts := 0; new.error := null; new.claimed_at := null; new.sent_at := null;
  new.created_at := now();
  if (select count(*) from public.send_requests r
      where r.user_id = new.user_id and r.created_at > now() - interval '24 hours') >= 30 then
    raise exception 'limit: 30 reports a day' using errcode = 'P0001';
  end if;
  return new;
end $$;
drop trigger if exists send_requests_guard on public.send_requests;
create trigger send_requests_guard before insert on public.send_requests
  for each row execute function public.send_requests_guard();

-- Optional, for delivery within a minute or two instead of the 10-minute check: wake the GitHub workflow.
-- Needs the pg_net extension (Database -> Extensions) and two Vault secrets (see README); without them nothing happens.
create or replace function public.send_requests_wake() returns trigger
language plpgsql security definer set search_path = public as $$
declare tok text; repo text; evt text := coalesce(tg_argv[0], 'send-request');
begin
  begin
    select decrypted_secret into tok from vault.decrypted_secrets where name = 'github_dispatch_token';
    select decrypted_secret into repo from vault.decrypted_secrets where name = 'github_repo';
    if tok is not null and repo is not null then
      perform net.http_post(
        url := 'https://api.github.com/repos/' || repo || '/dispatches',
        body := jsonb_build_object('event_type', evt),
        headers := jsonb_build_object('Authorization', 'Bearer ' || tok, 'Accept', 'application/vnd.github+json',
                                      'User-Agent', 'filing-flows', 'Content-Type', 'application/json'));
    end if;
  exception when others then
    null;                                       -- no Vault or pg_net: the scheduled check sends it
  end;
  return null;
end $$;
drop trigger if exists send_requests_wake on public.send_requests;
create trigger send_requests_wake after insert on public.send_requests
  for each statement execute function public.send_requests_wake();

-- The site owner: only accounts listed here see the owner tools (#owner: the X thread panel on company pages).
-- Add your own address once in the SQL Editor:  insert into public.site_owners (email) values ('you@example.com');
-- The list cannot be read through the website (no policies); the site only asks "am I the owner?".
create table if not exists public.site_owners (email text primary key);
alter table public.site_owners enable row level security;
create or replace function public.am_i_owner() returns boolean
language sql stable security definer set search_path = public, auth as $$
  select exists (select 1 from public.site_owners o join auth.users u on lower(u.email) = lower(o.email)
                 where u.id = auth.uid());
$$;
revoke all on function public.am_i_owner() from public;
do $$ begin
  revoke all on function public.am_i_owner() from anon;
  grant execute on function public.am_i_owner() to authenticated;
exception when undefined_object then null;            -- plain Postgres without Supabase's roles
end $$;

-- "Email me this thread" goes straight to the owner's inbox: only the site owner may ask for a thread
drop policy if exists "ask for reports" on public.send_requests;
create policy "ask for reports" on public.send_requests for insert
  with check (auth.uid() = user_id and (kind <> 'thread' or public.am_i_owner()));

-- The owner's preferences (#owner page): read and changed by the site owner only; read by the workflows with the secret key.
create table if not exists public.owner_settings (
  id              boolean primary key default true check (id),      -- a single row
  thread_direct   boolean not null default true,     -- "Email me this thread" sends at once (false: opens a GitHub issue)
  daily_on        boolean not null default true,     -- the owner's daily report: new filings with charts, analysis, X threads
  daily_hour      smallint not null default 8 check (daily_hour between 0 and 23),
  tz              text not null default 'Asia/Shanghai' check (length(tz) <= 64),
  min_revenue     bigint not null default 1000000000 check (min_revenue >= 0),   -- companies in the daily report
  instant_threads boolean not null default false,    -- also e-mail new X threads right after each scan
  daily_scope     text not null default 'min_revenue' check (daily_scope in ('min_revenue', 'all')),   -- 'all': every
                                                     -- company that filed (the full report), not only those over min_revenue
  reader_copy     boolean not null default false,    -- the owner also gets the reader e-mails their own alert settings ask for
  updated_at      timestamptz not null default now()
);
alter table public.owner_settings add column if not exists daily_scope text not null default 'min_revenue';
alter table public.owner_settings add column if not exists reader_copy boolean not null default false;
do $$ begin
  alter table public.owner_settings add constraint owner_settings_daily_scope_check check (daily_scope in ('min_revenue', 'all'));
exception when duplicate_object then null;
end $$;
insert into public.owner_settings (id) values (true) on conflict do nothing;
alter table public.owner_settings enable row level security;
drop policy if exists "owner reads settings" on public.owner_settings;
drop policy if exists "owner changes settings" on public.owner_settings;
do $$ begin
  create policy "owner reads settings" on public.owner_settings for select to authenticated using (public.am_i_owner());
  create policy "owner changes settings" on public.owner_settings for update to authenticated
    using (public.am_i_owner()) with check (public.am_i_owner());
exception when undefined_object then                  -- plain Postgres without Supabase's roles
  create policy "owner reads settings" on public.owner_settings for select using (public.am_i_owner());
  create policy "owner changes settings" on public.owner_settings for update using (public.am_i_owner()) with check (public.am_i_owner());
end $$;

-- Optional outside clock for the scan (README: "Scan more often"): GitHub starts scheduled runs late or skips them when
-- busy; Supabase's pg_cron can call this every few minutes instead. Uses the same two Vault secrets as the wake-up above.
-- Only the database itself may call it (never the website): the grants below take it away from everyone else.
create or replace function public.github_dispatch(evt text) returns void
language plpgsql security definer set search_path = public as $$
declare tok text; repo text;
begin
  select decrypted_secret into tok from vault.decrypted_secrets where name = 'github_dispatch_token';
  select decrypted_secret into repo from vault.decrypted_secrets where name = 'github_repo';
  if tok is null or repo is null then
    raise notice 'github_dispatch: add the Vault secrets github_dispatch_token and github_repo first';
    return;
  end if;
  perform net.http_post(
    url := 'https://api.github.com/repos/' || repo || '/dispatches',
    body := jsonb_build_object('event_type', evt),
    headers := jsonb_build_object('Authorization', 'Bearer ' || tok, 'Accept', 'application/vnd.github+json',
                                  'User-Agent', 'filing-flows', 'Content-Type', 'application/json'));
end $$;
revoke all on function public.github_dispatch(text) from public;
do $$ begin
  revoke all on function public.github_dispatch(text) from anon, authenticated;
exception when undefined_object then null;            -- plain Postgres without Supabase's roles
end $$;

-- "Compare any two periods" on a company page (readers who turned it on in their alerts): the sender draws the chart
-- from SEC data and writes it back into the row; the page shows it. At most 20 a day per reader.
create table if not exists public.chart_requests (
  id          bigint generated always as identity primary key,
  user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
  cik         integer not null check (cik > 0),
  kind        text not null default 'q' check (kind in ('q', 'fy')),
  a_end       date not null,
  b_end       date not null,
  status      text not null default 'pending' check (status in ('pending', 'working', 'done', 'failed')),
  error       text,
  result      jsonb,
  created_at  timestamptz not null default now(),
  claimed_at  timestamptz,
  done_at     timestamptz,
  check (a_end <> b_end)
);
create index if not exists chart_requests_status on public.chart_requests (status, created_at);
create index if not exists chart_requests_user on public.chart_requests (user_id, cik, created_at desc);
alter table public.chart_requests enable row level security;
drop policy if exists "read own charts" on public.chart_requests;
drop policy if exists "ask for charts" on public.chart_requests;
create policy "read own charts" on public.chart_requests for select using (auth.uid() = user_id);
create policy "ask for charts" on public.chart_requests for insert with check (auth.uid() = user_id);

create or replace function public.chart_requests_guard() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  new.status := 'pending'; new.error := null; new.result := null; new.claimed_at := null; new.done_at := null;
  new.created_at := now();
  if (select count(*) from public.chart_requests r
      where r.user_id = new.user_id and r.created_at > now() - interval '24 hours') >= 20 then
    raise exception 'limit: 20 comparisons a day' using errcode = 'P0001';
  end if;
  return new;
end $$;
drop trigger if exists chart_requests_guard on public.chart_requests;
create trigger chart_requests_guard before insert on public.chart_requests
  for each row execute function public.chart_requests_guard();
drop trigger if exists chart_requests_wake on public.chart_requests;
create trigger chart_requests_wake after insert on public.chart_requests
  for each statement execute function public.send_requests_wake('chart-request');

-- "Build this company" from the site's search: the next scan fetches its last five 10-Qs and two 10-Ks.
create table if not exists public.company_requests (
  id          bigint generated always as identity primary key,
  user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
  cik         integer not null check (cik > 0),
  status      text not null default 'pending' check (status in ('pending', 'queued', 'done', 'failed')),
  error       text,
  created_at  timestamptz not null default now(),
  claimed_at  timestamptz,
  done_at     timestamptz
);
create unique index if not exists company_requests_one_open on public.company_requests (user_id, cik)
  where status in ('pending', 'queued');
create index if not exists company_requests_status on public.company_requests (status, created_at);
alter table public.company_requests enable row level security;
drop policy if exists "read own companies" on public.company_requests;
drop policy if exists "ask for companies" on public.company_requests;
create policy "read own companies" on public.company_requests for select using (auth.uid() = user_id);
create policy "ask for companies" on public.company_requests for insert with check (auth.uid() = user_id);

create or replace function public.company_requests_guard() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  new.status := 'pending'; new.error := null; new.claimed_at := null; new.done_at := null; new.created_at := now();
  if (select count(*) from public.company_requests r
      where r.user_id = new.user_id and r.created_at > now() - interval '24 hours') >= 10 then
    raise exception 'limit: 10 companies a day' using errcode = 'P0001';
  end if;
  return new;
end $$;
drop trigger if exists company_requests_guard on public.company_requests;
create trigger company_requests_guard before insert on public.company_requests
  for each row execute function public.company_requests_guard();
drop trigger if exists company_requests_wake on public.company_requests;
create trigger company_requests_wake after insert on public.company_requests
  for each statement execute function public.send_requests_wake('company-request');

-- The owner's "Re-read stored figures" (Owner tools): the next scan reads these companies' stored figures again from SEC
-- (cik 0 = every stored company, a few dozen per scan). Only the site owner can ask; the scan claims them with the secret key.
create table if not exists public.reread_requests (
  id          bigint generated always as identity primary key,
  user_id     uuid not null default auth.uid() references auth.users (id) on delete cascade,
  cik         integer not null check (cik >= 0),
  status      text not null default 'pending' check (status in ('pending', 'queued', 'done', 'failed')),
  error       text,
  created_at  timestamptz not null default now(),
  claimed_at  timestamptz,
  done_at     timestamptz
);
create index if not exists reread_requests_status on public.reread_requests (status, created_at);
alter table public.reread_requests enable row level security;
drop policy if exists "owner reads rereads" on public.reread_requests;
drop policy if exists "owner asks rereads" on public.reread_requests;
create policy "owner reads rereads" on public.reread_requests for select using (auth.uid() = user_id and public.am_i_owner());
create policy "owner asks rereads" on public.reread_requests for insert with check (auth.uid() = user_id and public.am_i_owner());
create or replace function public.reread_requests_guard() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  new.status := 'pending'; new.error := null; new.claimed_at := null; new.done_at := null; new.created_at := now();
  if (select count(*) from public.reread_requests r
      where r.user_id = new.user_id and r.created_at > now() - interval '24 hours') >= 200 then
    raise exception 'limit: 200 re-reads a day' using errcode = 'P0001';
  end if;
  return new;
end $$;
drop trigger if exists reread_requests_guard on public.reread_requests;
create trigger reread_requests_guard before insert on public.reread_requests
  for each row execute function public.reread_requests_guard();
drop trigger if exists reread_requests_wake on public.reread_requests;
create trigger reread_requests_wake after insert on public.reread_requests
  for each statement execute function public.send_requests_wake('reread');

