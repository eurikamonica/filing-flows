"""The site owner's lane: the owner's scans and requests go first and are picked up within seconds.

GitHub starts scheduled runs late (scan.yml's 15-minute schedule fires about every 30 minutes, requests.yml's 10-minute
one about as often) and the Supabase wake-up (repository_dispatch, README) is optional. One thing is always running: the
X-post watch relay (post-to-x.yml), one run after another, each checking Supabase every 20 seconds. Each of those checks
also runs `wake` here, which looks at what the owner is waiting for and starts the workflow that does it:

  scan lane      the owner's company requests (company_requests.owner, set by the database) and re-read requests
                 (reread_requests: the owner only) that no scan has claimed yet → scan.yml with fast=true: a short scan
                 that relays itself while an owner company is still being built (scan.yml, pipeline/custom.py)
  requests lane  the owner's report e-mails and comparisons (send_requests that are not X posts, chart_requests) →
                 requests.yml, which serves the owner's first

  intraday lane  not the owner's: on weekdays from 9:10 to 4 pm New York, the hub's live Move odds relay
                 (intraday.yml) — started when no run of it is running or waiting, so it begins with the session and
                 comes back within minutes if it stops (GitHub's schedule alone starts it late or not at all);
                 the repository variable INTRADAY_RELAY=off stops it
  close lane     not the owner's either: on weekdays from 4:11 to 8 pm New York, the hub's Move odds at the close
                 (moves-close.yml, every asset's close in minutes) until the day's close is on file (the branch
                 moves-live) with the closing prints — whether or not the intraday relay, which starts it when the
                 session ends, is still running

A lane starts nothing while a run of its workflow is waiting to start, or when a run started after the request (it
claims the request itself). A regular scan already running when the owner asks wraps up early (should_yield, called by
pipeline/build.py time_up), so the owner's short scan follows within minutes instead of after the 32-minute budget.

    python -m pipeline.owner_lane wake        # one check: start what the owner is waiting for (exit 0 = started one)
    python -m pipeline.owner_lane status      # what the owner is waiting for, by lane

Environment: SUPABASE_URL, SUPABASE_SERVICE_KEY; GITHUB_TOKEN (actions: write) and GITHUB_REPOSITORY to start runs.
"""
import argparse
import datetime as dt
import json
import os
import sys
import tempfile
import time

import requests

LANES = {"scan": {"workflow": "scan.yml", "inputs": {"fast": "true", "hop": "0"}},
         "requests": {"workflow": "requests.yml", "inputs": {}}}
WAITING = ("queued", "pending", "waiting", "requested")   # a run that has not started (or waits for its concurrency group)
RECENT_HOURS = 6              # older open requests are the schedules' business (a request that keeps failing, say)
AGAIN_SECONDS = 90            # one start per lane at most this often (a new run takes a few seconds to show in the API)
YIELD_EVERY = 60              # a running scan asks Supabase at most once a minute whether the owner is waiting
INTRADAY = {"workflow": "intraday.yml", "inputs": {"hop": "0"}}
INTRADAY_WINDOW = (9 * 60 + 10, 16 * 60)   # New York minutes: the relay starts 20 minutes before the open
INTRADAY_EVERY = 120          # a look at its runs at most this often (the watch loop checks every 20 seconds)
INTRADAY_GAP = 15 * 60        # no new run within 15 minutes of the last (a holiday or an early close: it found no session)
CLOSE = {"workflow": "moves-close.yml", "inputs": {}, "status": ("moves-live", "status.json")}
CLOSE_FIRST = 16 * 60 + 11    # New York minutes: a session's bars are final ten minutes after 4 pm (moves_close.GRACE)
CLOSE_DONE = 16 * 60 + 25     # files made before this are made again with the closing prints (moves_close.FIRST)…
CLOSE_REDO = 16 * 60 + 46     # …from this on (moves_close.REDO_AFTER)
CLOSE_END = 20 * 60           # later, the nightly run's business
CLOSE_GAP = 20 * 60           # no new run within 20 minutes of the last
API = "https://api.github.com"


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _ts(s):
    t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def _supa():
    from .notify import Supa, setting
    url, key = setting("SUPABASE_URL", url=True), setting("SUPABASE_SERVICE_KEY")
    return Supa(url, key) if url and key else None


def owner_ids(supa):
    """The site owners' account ids: site_owners addresses matched to the accounts' rows (subscriptions.email is always
    copied from the account)."""
    from .owner import owner_emails
    emails = owner_emails(supa)
    ids = set()
    for e in emails:
        try:
            rows = supa.select("subscriptions", {"select": "user_id,email", "email": f"ilike.{e}"})
        except RuntimeError:
            continue
        ids |= {r["user_id"] for r in rows if str(r.get("email") or "").strip().lower() == e}
    return ids


def _rows(supa, table, params):
    try:
        return supa.select(table, params)
    except RuntimeError as err:                  # schema.sql not run again yet (no owner column), or no such table
        print(f"owner lane: {table} not read ({str(err)[:100]})")
        return []


def waiting(supa, now=None, ids=None):
    """{'scan': [...], 'requests': [...]}: the owner's requests no run has claimed yet (asked within RECENT_HOURS), each
    {'table', 'id', 'created_at', 'what'}."""
    from .notify import POST_KINDS
    now = now or _now()
    edge = (now - dt.timedelta(hours=RECENT_HOURS)).isoformat()
    out = {"scan": [], "requests": []}
    for r in _rows(supa, "company_requests", {"select": "id,cik,created_at", "owner": "eq.true", "status": "eq.pending",
                                              "created_at": f"gte.{edge}"}):
        out["scan"].append({"table": "company_requests", "id": r["id"], "created_at": r["created_at"], "what": f"build CIK {r['cik']}"})
    for r in _rows(supa, "reread_requests", {"select": "id,cik,created_at", "status": "eq.pending", "created_at": f"gte.{edge}"}):
        out["scan"].append({"table": "reread_requests", "id": r["id"], "created_at": r["created_at"],
                            "what": "re-read every company" if int(r["cik"]) == 0 else f"re-read CIK {r['cik']}"})
    ids = owner_ids(supa) if ids is None else ids
    if ids:
        who = f"in.({','.join(sorted(ids))})"
        for r in _rows(supa, "send_requests", {"select": "*", "status": "eq.pending", "user_id": who, "created_at": f"gte.{edge}"}):
            kind = r.get("kind") or "q"
            if kind in POST_KINDS or kind.startswith("engage_"):      # X posts: post-to-x.yml itself
                continue
            out["requests"].append({"table": "send_requests", "id": r["id"], "created_at": r["created_at"], "what": f"e-mail ({kind})"})
        for r in _rows(supa, "chart_requests", {"select": "id,cik,created_at", "status": "eq.pending", "user_id": who,
                                                "created_at": f"gte.{edge}"}):
            out["requests"].append({"table": "chart_requests", "id": r["id"], "created_at": r["created_at"], "what": f"comparison CIK {r['cik']}"})
    for v in out.values():
        v.sort(key=lambda x: x["created_at"])
    return out


# ------------------------------------------------------------------ GitHub: is a run on its way, and starting one
class GitHub:
    def __init__(self, token, repo, ref="main", session=None):
        self.repo, self.ref, self.s = repo, ref, session or requests.Session()
        self.h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}

    def runs(self, workflow, n=20):
        r = self.s.get(f"{API}/repos/{self.repo}/actions/workflows/{workflow}/runs", params={"per_page": str(n)},
                       headers=self.h, timeout=30)
        r.raise_for_status()
        return r.json().get("workflow_runs") or []

    def start(self, workflow, inputs):
        r = self.s.post(f"{API}/repos/{self.repo}/actions/workflows/{workflow}/dispatches", headers=self.h, timeout=30,
                        data=json.dumps({"ref": self.ref, "inputs": inputs}))
        if r.status_code >= 300:
            raise RuntimeError(f"GitHub {r.status_code}: {r.text[:200]}")

    def file(self, branch, path):
        """A JSON file of a branch, as it is now (the API, not the raw files' cache); None when there is none."""
        r = self.s.get(f"{API}/repos/{self.repo}/contents/{path}", params={"ref": branch}, timeout=30,
                       headers=dict(self.h, Accept="application/vnd.github.raw+json"))
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()


def covered(runs, item):
    """Why no new run is needed for this request (or None): a run is waiting to start, or a run was created after the
    request — it claims it when it gets there (scan.yml and requests.yml claim at their start)."""
    asked = _ts(item["created_at"])
    for r in runs:
        if r.get("status") in WAITING:
            return f"run {r.get('id')} is waiting to start"
        if r.get("created_at") and _ts(r["created_at"]) >= asked - dt.timedelta(seconds=5):
            return f"run {r.get('id')} started after the request"
    return None


def _state_path():
    return os.path.join(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir(), "owner-lane.json")


def _state():
    try:
        with open(_state_path()) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(st):
    try:
        with open(_state_path(), "w") as f:
            json.dump(st, f)
    except OSError:
        pass


def intraday_window(now=None):
    """Weekdays from 9:10 to 4 pm New York: when the hub's intraday relay (intraday.yml) should be running."""
    from zoneinfo import ZoneInfo
    t = (now or _now()).astimezone(ZoneInfo("America/New_York"))
    return t.weekday() < 5 and INTRADAY_WINDOW[0] <= t.hour * 60 + t.minute < INTRADAY_WINDOW[1]


def wake_intraday(gh, now=None, state=None, log=print):
    """The intraday lane: in the window, start intraday.yml unless a run of it is running or waiting, or one was created
    in the last 15 minutes. Returns True when it started one."""
    now = now or _now()
    if os.environ.get("INTRADAY_RELAY", "").strip().lower() == "off" or not intraday_window(now):
        return False
    st = _state() if state is None else state
    last = st.get("intraday")
    if last and (now - _ts(last)).total_seconds() < INTRADAY_EVERY:
        return False
    st["intraday"] = now.isoformat()
    if state is None:
        _save(st)
    for r in gh.runs(INTRADAY["workflow"], 10):
        if r.get("status") in WAITING or r.get("status") == "in_progress":
            return False
        if r.get("created_at") and (now - _ts(r["created_at"])).total_seconds() < INTRADAY_GAP:
            return False
    gh.start(INTRADAY["workflow"], INTRADAY["inputs"])
    log("::notice::intraday lane: started intraday.yml (the hub's live Move odds)")
    return True


def wake_close(gh, now=None, state=None, log=print):
    """The close lane: on weekdays from 4:11 to 8 pm New York, start moves-close.yml until the day's close is on file
    (moves-live's status.json) with the closing prints — from 4:11 while the day is missing, from 4:46 when its files
    were made before 4:25. Nothing while a run of it is running or waiting, or after a run made since then: within 20
    minutes of it, or at all once it finished well (it did what was due; on a holiday, nothing: moves_close.py --due).
    Looks at most every two minutes. Returns True when it started one."""
    from zoneinfo import ZoneInfo
    now = now or _now()
    t = now.astimezone(ZoneInfo("America/New_York"))
    if t.weekday() >= 5 or not CLOSE_FIRST <= t.hour * 60 + t.minute < CLOSE_END:
        return False
    st = _state() if state is None else state
    last = st.get("close")
    if last and (now - _ts(last)).total_seconds() < INTRADAY_EVERY:
        return False
    st["close"] = now.isoformat()
    if state is None:
        _save(st)
    at = lambda m: t.replace(hour=m // 60, minute=m % 60, second=0, microsecond=0)   # noqa: E731
    s = gh.file(*CLOSE["status"]) or {}
    if s.get("as_of") != t.date().isoformat():
        since = at(CLOSE_FIRST)
    elif s.get("built_at") and _ts(s["built_at"]) < at(CLOSE_DONE):
        since = at(CLOSE_REDO)
    else:
        return False                                   # on file with the closing prints
    if t < since:
        return False
    for r in gh.runs(CLOSE["workflow"], 10):
        if r.get("status") in WAITING or r.get("status") == "in_progress":
            return False
        made = _ts(r["created_at"]) if r.get("created_at") else None
        if made and made >= since and ((now - made).total_seconds() < CLOSE_GAP or r.get("conclusion") == "success"):
            return False                               # a run since: give it time, or it did what was due
    gh.start(CLOSE["workflow"], CLOSE["inputs"])
    log("::notice::close lane: started moves-close.yml (the hub's Move odds at the close)")
    return True


def wake(supa, gh, now=None, state=None, log=print):
    """Start the workflow each lane needs; returns the lanes started."""
    now = now or _now()
    st = _state() if state is None else state
    started = []
    todo = waiting(supa, now)
    for lane, items in todo.items():
        if not items:
            continue
        last = st.get(lane)
        if last and (now - _ts(last)).total_seconds() < AGAIN_SECONDS:
            log(f"owner lane {lane}: started {int((now - _ts(last)).total_seconds())} s ago, waiting for it")
            continue
        cfg = LANES[lane]
        runs = gh.runs(cfg["workflow"])
        why = covered(runs, items[0])
        if why:
            log(f"owner lane {lane}: {len(items)} waiting ({items[0]['what']}); {why}")
            continue
        gh.start(cfg["workflow"], cfg["inputs"])
        st[lane] = now.isoformat()
        started.append(lane)
        log(f"::notice::owner lane {lane}: started {cfg['workflow']} for {', '.join(x['what'] for x in items[:4])}"
            + (f" and {len(items) - 4} more" if len(items) > 4 else ""))
    if state is None and started:
        _save(st)
    return started


# ------------------------------------------------------------------ a running regular scan makes way (pipeline/build.py)
_yield = {"at": None, "answer": False}


def should_yield(now_mono=None):
    """True once the owner asked for a company or a re-read that this scan did not claim: the scan stops taking on new
    work so the owner's short scan (already queued by the watch relay) starts within minutes. Never in a fast scan
    itself (OWNER_FAST=true), never without Supabase; asks at most once a minute; once True, stays True."""
    if _yield["answer"] or os.environ.get("OWNER_FAST") == "true":
        return _yield["answer"]
    t = time.monotonic() if now_mono is None else now_mono
    if _yield["at"] is not None and t - _yield["at"] < YIELD_EVERY:
        return False
    _yield["at"] = t
    try:
        supa = _supa()
        if not supa:
            return False
        since = os.environ.get("OWNER_CLAIMED_AT") or _started.isoformat()
        got = waiting(supa, ids=set())["scan"]
        mine = [x for x in got if _ts(x["created_at"]) > _ts(since)]
        if mine:
            print(f"::notice::the owner asked for {mine[0]['what']}: this scan wraps up early for the owner's short scan")
            _yield["answer"] = True
    except Exception as err:                       # never let the check stop a scan
        print(f"owner lane: yield check skipped ({str(err)[:100]})")
    return _yield["answer"]


_started = _now()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["wake", "status"])
    args = ap.parse_args()
    supa = _supa()
    if not supa:
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY not set: no owner lane.")
        sys.exit(1)
    try:
        if args.cmd == "status":
            for lane, items in waiting(supa).items():
                print(f"{lane}: {len(items)} waiting" + "".join(f"\n  {x['created_at'][:19]} {x['what']}" for x in items))
            sys.exit(0)
        token, repo = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
        if not token or not repo:
            print("GITHUB_TOKEN / GITHUB_REPOSITORY not set: the owner lane cannot start runs.")
            sys.exit(1)
        gh = GitHub(token, repo, os.environ.get("GITHUB_REF_NAME") or "main")
        try:
            wake_intraday(gh)
        except Exception as err:                   # never in the way of the owner's lanes
            print(f"intraday lane: check skipped ({str(err)[:120]})")
        try:
            wake_close(gh)
        except Exception as err:                   # nor this one
            print(f"close lane: check skipped ({str(err)[:120]})")
        sys.exit(0 if wake(supa, gh) else 1)
    except SystemExit:
        raise
    except Exception as err:                       # the watch loop carries on whatever happens here
        print(f"::warning::owner lane check failed: {str(err)[:200]}")
        sys.exit(2)


if __name__ == "__main__":
    main()
