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
  unsub_token  uuid    not null default gen_random_uuid(),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

-- added after the first release: keeps older projects in step when this file is run again
alter table public.subscriptions add column if not exists final_too boolean not null default true;

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
create unique index if not exists send_requests_one_pending on public.send_requests (user_id, cik, period_end)
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
declare tok text; repo text;
begin
  begin
    select decrypted_secret into tok from vault.decrypted_secrets where name = 'github_dispatch_token';
    select decrypted_secret into repo from vault.decrypted_secrets where name = 'github_repo';
    if tok is not null and repo is not null then
      perform net.http_post(
        url := 'https://api.github.com/repos/' || repo || '/dispatches',
        body := jsonb_build_object('event_type', 'send-request'),
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
