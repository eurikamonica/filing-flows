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
  frequency    text    not null default 'instant' check (frequency in ('instant', 'daily')),
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
do $$ begin
  alter table public.subscriptions add constraint subscriptions_attach_images_check check (attach_images in ('png', 'jpg', 'none'));
exception when duplicate_object then null;
end $$;

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
do $$ begin
  alter table public.send_requests add constraint send_requests_kind_check check (kind in ('q', 'fy'));
exception when duplicate_object then null;
end $$;
drop index if exists public.send_requests_one_pending;       -- a quarter and a fiscal year can end on the same day
create unique index if not exists send_requests_one_pending_kind on public.send_requests (user_id, cik, period_end, kind)
  where status in ('pending', 'sending');
create index if not exists send_requests_status on public.send_requests (status, created_at);

alter table public.send_requests enable row level security;
drop policy if exists "read own requests" on public.send_requests;
drop policy if exists "ask for reports" on public.send_requests;
create policy "read own requests" on public.send_requests for select using (auth.uid() = user_id);
create policy "ask for reports" on public.send_requests for insert with check (auth.uid() = user_id);

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
