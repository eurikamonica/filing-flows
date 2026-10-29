"""Queue the ready-to-post X threads in Buffer (config/x.json "mode": "buffer").

pipeline/social.py writes each thread's chart images into the site (_site/x/) and a manifest (_site/x/pending.json)
during the scan; this runs after the site is live, because Buffer fetches images by public URL:

    python -m pipeline.buffer --site _site --site-url https://filing-flows.com/ --state media-branch/x/buffer-state.json

Secrets / variables: BUFFER_API_KEY (Buffer → Settings → API → Personal Access); BUFFER_CHANNEL_ID optional —
without it the first X / Twitter channel of the account is used (looked up once, then remembered in the state file).
Posts go to the channel's queue (Buffer's own posting schedule); nothing is published without a slot in that schedule.

Buffer's API limits are per account, shared by every workflow that posts (scan, movers, engagement posts, Post to X):
on the free plan 150 requests / 15 min, 600 / day and 1,000 per channel per 30 days (developers.buffer.com/guides/
api-limits). Every run used to spend two lookups before each batch and keep calling into a full queue, which used up
the 30-day allowance in days; after that every run failed with HTTP 429. So the state file (kept on the "media"
branch by scripts/publish-media.sh) remembers:
  - the channel, so a run spends one request per thread and nothing on lookups;
  - the limits Buffer reported (RateLimit headers) and, after a 429 or a full queue, when to try again — runs before
    then call nothing and do not fail;
  - a per-day request budget (config/x.json "buffer_daily_requests", default 30 ≈ 1,000 / 30 days), lowered further
    when the 30-day allowance left is smaller;
  - the threads that could not be queued yet ("backlog"), tried first by the next run and dropped once older than
    "buffer_backlog_hours" (default 12; a stale earnings post is worse than none).
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys

import requests

API = "https://api.buffer.com"
WINDOWS = {"15m": 900, "24h": 86400, "30d": 2592000}
LIMITS = {}          # window seconds -> {"remaining", "reset_in", "quota"} from the latest response
SPENT = [0]          # requests sent by this run


class BufferError(RuntimeError):
    def __init__(self, message, status=None, code=None, window=None, retry_after=None):
        super().__init__(message)
        self.status, self.code, self.window, self.retry_after = status, code, window, retry_after

    @property
    def rate_limited(self):
        return self.status == 429 or self.code == "RATE_LIMIT_EXCEEDED"


def _items(header):
    """'"15m";r=149;t=899, "24h";r=599;t=86399' -> [("15m", {"r": "149", "t": "899"}), ...]."""
    out = []
    for part in (header or "").split(","):
        bits = [b.strip() for b in part.split(";") if b.strip()]
        if not bits:
            continue
        name, params = bits[0].strip('"'), {}
        for b in bits[1:]:
            if "=" in b:
                k, v = b.split("=", 1)
                params[k.strip()] = v.strip().strip('"')
        out.append((name, params))
    return out


def parse_limits(headers):
    """RateLimit / RateLimit-Policy headers -> {window seconds: {"remaining", "reset_in", "quota"}}."""
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    policy = {name: p for name, p in _items(headers.get("ratelimit-policy"))}
    out = {}
    for name, p in _items(headers.get("ratelimit")):
        pol = policy.get(name, {})
        w = pol.get("w") or WINDOWS.get(name)
        try:
            w = int(w)
        except (TypeError, ValueError):
            continue
        row = out.setdefault(w, {})
        for key, src in (("remaining", p.get("r")), ("reset_in", p.get("t")), ("quota", pol.get("q"))):
            try:
                row[key] = int(src)
            except (TypeError, ValueError):
                pass
    return out


def gql(key, query, variables=None):
    SPENT[0] += 1
    r = requests.post(API, json={"query": query, "variables": variables or {}},
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=60)
    LIMITS.update(parse_limits(r.headers))
    try:
        body = r.json()
    except ValueError:
        raise BufferError(f"HTTP {r.status_code}: {r.text[:200]}", status=r.status_code)
    if r.status_code >= 400 or body.get("errors"):
        errs = body.get("errors") or []
        ext = (errs[0].get("extensions") or {}) if errs and isinstance(errs[0], dict) else {}
        try:
            retry = int(r.headers.get("Retry-After"))
        except (TypeError, ValueError):
            retry = None
        raise BufferError(f"HTTP {r.status_code}: {json.dumps(errs or body)[:400]}", status=r.status_code,
                          code=ext.get("code"), window=ext.get("window"), retry_after=retry)
    return body["data"]


def x_channel(key, wanted=None):
    orgs = gql(key, "query { account { organizations { id name } } }")["account"]["organizations"]
    for org in orgs:
        chans = gql(key, "query($org: OrganizationId!) { channels(input: { organizationId: $org }) { id name service isQueuePaused } }",
                    {"org": org["id"]})["channels"]
        for ch in chans:
            if wanted and ch["id"] == wanted:
                return ch
            if not wanted and str(ch.get("service", "")).lower() in ("twitter", "x"):
                return ch
    raise BufferError("no X channel found" + (f" with id {wanted}" if wanted else "") + "; connect X in Buffer or set BUFFER_CHANNEL_ID")


def create_thread(key, channel_id, parts, due_at=None, draft=False):
    """parts: [{"text": str, "images": [public url, ...]}]; the first part carries the charts."""
    thread = [{"text": p["text"], **({"assets": [{"image": {"url": u}} for u in p.get("images", [])[:4]]} if p.get("images") else {})}
              for p in parts]
    inp = {"channelId": channel_id, "text": parts[0]["text"], "schedulingType": "automatic",
           "mode": "customScheduled" if due_at else "addToQueue"}
    if len(parts) == 1:
        if parts[0].get("images"):
            inp["assets"] = [{"image": {"url": u}} for u in parts[0]["images"][:4]]
    else:
        inp["metadata"] = {"twitter": {"thread": thread}}
    if due_at:
        inp["dueAt"] = due_at
    if draft:                       # Owner tools "draft": lands in Buffer's drafts for review and editing, not in the queue
        inp["saveToDraft"] = True
    data = gql(key, """mutation($input: CreatePostInput!) { createPost(input: $input) {
        ... on PostActionSuccess { post { id status dueAt } } ... on MutationError { message } } }""", {"input": inp})
    res = data["createPost"]
    if "message" in res:
        raise BufferError(res["message"])
    return res["post"]


def queue_full(err):
    """Buffer's answer when the channel's queue already holds the plan's maximum of scheduled posts."""
    return not getattr(err, "rate_limited", False) and bool(
        re.search(r"limit|queue is full|maximum|too many (scheduled )?posts|upgrade", str(err), re.I))


# ---- the state kept between runs (media branch x/buffer-state.json) ----

def _now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def _iso(t):
    return t.isoformat().replace("+00:00", "Z")


def _when(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def load_state(path):
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
        return st if isinstance(st, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(path, st):
    if not path:
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, path)


def thread_key(parts):
    return hashlib.sha1(json.dumps([p["text"] for p in parts], ensure_ascii=False).encode()).hexdigest()[:16]


def waiting_until(st, now):
    """(time, reason) before which nothing is sent, or (None, None)."""
    for field, reason in (("blocked_until", "Buffer's API limit"), ("queue_full_until", "the Buffer queue is full")):
        t = _when(st.get(field))
        if t and t > now:
            return t, reason
    return None, None


def budget(st, now, daily):
    """Requests this run may spend: what is left of today's share, of the 30-day allowance spread over the days to
    its reset, and of the 24-hour and 15-minute windows (one kept in reserve in each)."""
    day = now.date().isoformat()
    spent = st.get("spent") if (st.get("spent") or {}).get("day") == day else {"day": day, "requests": 0}
    st["spent"] = spent
    left = daily - spent["requests"]
    seen = st.get("limits") or {}
    at = _when(st.get("limits_at"))
    for w, row in seen.items():
        r, t = row.get("remaining"), row.get("reset_in")
        if r is None:
            continue
        if at and t is not None and now >= at + dt.timedelta(seconds=t):
            continue                                   # that window has reset since it was read
        if int(w) >= 2592000:
            days = max(1.0, (t or 2592000) / 86400 - ((now - at).total_seconds() / 86400 if at else 0))
            left = min(left, int(r / days))
        else:
            left = min(left, r - 1)
    return max(0, left)


def note_limits(st, now):
    if LIMITS:
        st["limits"] = {str(w): row for w, row in sorted(LIMITS.items())}
        st["limits_at"] = _iso(now)


def summary(st):
    row = (st.get("limits") or {}).get("2592000") or {}
    return (f"30-day requests left {row['remaining']}/{row.get('quota', '?')}" if "remaining" in row else "limits not read yet") + \
        f"; today {st.get('spent', {}).get('requests', 0)} request(s); {len(st.get('backlog', []))} thread(s) waiting"


def build_items(items, cfg, base, now):
    from . import social
    out = []
    for it in items:
        posts = social.strip_links(it["posts"]) if social.links_off(cfg) else it["posts"]   # config/x.json "links": false
        imgs = [n for n in it.get("images", []) if social.media_ok(cfg, n.rsplit(".", 1)[-1].lower())]   # "media": no GIF unless allowed
        if len(imgs) < len(it.get("images", [])):
            print(f"buffer: {it['label']}: left out {len(it['images']) - len(imgs)} image(s) of a type the X post options leave out")
        parts = [{"text": p, "images": ([f"{base}/x/{n}" for n in imgs] if i == 0 else [])} for i, p in enumerate(posts)]
        out.append({"label": it["label"], "parts": parts, "draft": bool(it.get("draft")), "key": thread_key(parts),
                    "made_at": it.get("made_at") or _iso(now)})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="_site")
    ap.add_argument("--site-url", default=os.environ.get("SITE_URL", ""))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--config", default="config/x.json")
    ap.add_argument("--state", default=os.environ.get("BUFFER_STATE", ""), help="JSON kept between runs (media branch)")
    args = ap.parse_args(argv)
    from . import social
    cfg = social.load_cfg(args.config)
    key = os.environ.get("BUFFER_API_KEY", "")
    now = _now()
    st = load_state(args.state)
    path = os.path.join(args.site, "x", "pending.json")
    items = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
    base = args.site_url.rstrip("/")
    if items and not base:
        print("::error::site URL unknown; Buffer needs public image URLs")
        sys.exit(1)
    new = build_items(items, cfg, base, now)
    keep_hours = float(cfg.get("buffer_backlog_hours", 12))
    sent = set(st.get("sent", []))
    todo, seen = [], set()
    for it in st.get("backlog", []) + new:              # what waited first, then this run's threads
        made = _when(it.get("made_at")) or now
        if it["key"] in seen or it["key"] in sent:
            continue
        if now - made > dt.timedelta(hours=keep_hours):
            print(f"buffer: dropped {it['label']} — waited over {keep_hours:g} h for room in Buffer")
            continue
        seen.add(it["key"])
        todo.append(it)
    if not todo:
        print("buffer: nothing queued by the scan")
        if st:
            save_state(args.state, st)
        return 0

    def finish(left, code=0):
        st["backlog"] = left[-int(cfg.get("buffer_backlog_max", 12)):]
        note_limits(st, now)
        st["updated_at"] = _iso(now)
        save_state(args.state, st)
        print("buffer: " + summary(st))
        return code

    if args.dry_run:
        for it in todo:
            print(f"would queue {it['label']}: {len(it['parts'])} posts, images {it['parts'][0]['images']}")
        return 0
    if not key:
        print(f"::warning::BUFFER_API_KEY missing; {len(todo)} thread(s) not queued")
        return finish(todo)
    until, why = waiting_until(st, now)
    if until:
        print(f"::warning::{why}: Buffer is not called again before {_iso(until)}; {len(todo)} thread(s) wait for then"
              + (f" (last answer: {st.get('last_error')})" if st.get("last_error") else ""))
        return finish(todo)
    allowed = budget(st, now, int(os.environ.get("BUFFER_DAILY_REQUESTS") or cfg.get("buffer_daily_requests", 30)))
    if allowed <= 0:
        print(f"::warning::today's share of the Buffer API allowance is used ({summary(st)}); {len(todo)} thread(s) wait for the next run")
        return finish(todo)

    def spend():
        st["spent"]["requests"] += 1

    wanted = os.environ.get("BUFFER_CHANNEL_ID") or None
    ch = (st.get("channel") or {}) if not wanted else {"id": wanted, "name": "BUFFER_CHANNEL_ID", "service": "x"}
    if wanted and (st.get("channel") or {}).get("id") == wanted:
        ch = st["channel"]
    if not ch.get("id"):
        if allowed < 3:
            print(f"::warning::the X channel lookup needs 2 requests and only {allowed} are left today; set BUFFER_CHANNEL_ID to skip it")
            return finish(todo)
        before = SPENT[0]
        try:
            ch = x_channel(key)
        except BufferError as err:
            st["spent"]["requests"] += SPENT[0] - before
            return blocked(st, err, now, todo, finish)
        st["spent"]["requests"] += SPENT[0] - before
        allowed -= SPENT[0] - before
        st["channel"] = {k: ch.get(k) for k in ("id", "name", "service")}
    print(f"buffer: channel {ch.get('name')} ({ch.get('service')}, {ch['id']}){' · queue paused' if ch.get('isQueuePaused') else ''}; "
          f"{len(todo)} thread(s), up to {allowed} request(s) this run")
    failed, left = 0, []
    for i, it in enumerate(todo):
        if allowed <= 0:
            left = todo[i:]
            print(f"::warning::{len(left)} thread(s) wait for the next run (today's share of the Buffer API allowance is used)")
            break
        try:
            allowed -= 1
            spend()
            post = create_thread(key, ch["id"], it["parts"], draft=it.get("draft"))
            print(f"{'saved as a Buffer draft' if it.get('draft') else 'queued'} {it['label']}: post {post['id']} ({post.get('status')}, due {post.get('dueAt')})")
            st["sent"] = (st.get("sent", []) + [it["key"]])[-200:]
            st.pop("last_error", None)
        except BufferError as err:
            if err.rate_limited:
                return blocked(st, err, now, todo[i:], finish)
            if queue_full(err):
                # the plan's scheduled-post limit (10 on the free plan): nothing more fits until Buffer posts some, so the
                # rest waits (and Buffer is not asked again for a while) instead of failing (a full queue is not a broken key)
                hours = float(cfg.get("buffer_full_queue_hours", 2))
                st["queue_full_until"] = _iso(now + dt.timedelta(hours=hours))
                st["last_error"] = str(err)[:300]
                print(f"::warning::Buffer queue is full ({err}); {len(todo) - i} thread(s) wait, next try after {st['queue_full_until']}")
                return finish(todo[i:])
            if re.search(r"channel", str(err), re.I) and not wanted:
                st.pop("channel", None)                    # a remembered channel that is gone: look it up next run
            failed += 1
            st["last_error"] = str(err)[:300]
            print(f"::warning::{it['label']} not queued: {err}")
    return finish(left, 1 if failed else 0)


def blocked(st, err, now, left, finish):
    """A 429: wait until Buffer says the exhausted window resets (Retry-After), and do not fail the run."""
    secs = err.retry_after
    if secs is None:
        win = WINDOWS.get(str(err.window or ""), 900)
        secs = (LIMITS.get(win) or {}).get("reset_in") or min(win, 6 * 3600)
    st["blocked_until"] = _iso(now + dt.timedelta(seconds=int(secs) + 60))
    st["last_error"] = str(err)[:300]
    print(f"::warning::Buffer API limit reached ({err.window or 'window unknown'}): no more requests before "
          f"{st['blocked_until']}; {len(left)} thread(s) wait. A paid Buffer plan raises the limit (buffer.com/pricing).")
    return finish(left)


if __name__ == "__main__":
    sys.exit(main())
