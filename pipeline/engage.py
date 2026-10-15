"""Engagement posts for X — question of the day, today's filers, Reddit trends, today's biggest price moves — written by
the model, polished, queued in Buffer with the real charts.

    python -m pipeline.engage --site https://filing-flows.com/ --kinds question,list --dry-run
    python -m pipeline.engage --site https://filing-flows.com/ --kinds reddit_question,reddit_list --media media

Kinds (config/engage-guide.md describes each format):
  question         one company that filed in the last `days` with the most striking figures -> fact + 2-3 options
  list             every company that filed in the last `days` (cashtags, up to 4 charts) -> "which surprised you?"
  reddit_question  the company trending hardest on investing subreddits -> fact + options  (pipeline/reddit.py)
  reddit_list      the 3-5 companies trending on Reddit, with the standout's filing line (up to 4 charts)
  mover            the site company moving most today (delayed quote, pipeline/quotes.py): "what's happening?" + its
                   latest filing figures; the cause is never guessed, the audience is asked
  explain          the same move as a "someone explain $X" post
  peers            the mover against its closest listed peers (same SIC industry): price, today's move, growth, margin,
                   price/sales — "which one makes more sense?"
  movers           (workflow) rotates mover → peers → explain over the day, within movers.max_per_day
  calendar         who reports earnings on the next trading day (Nasdaq calendar), site companies by market value, with
                   their last quarter's figures and charts
  fund13f          a watched fund's 13F just landed (Berkshire, Scion, Pershing Square …: Disclosures config holdings.watch):
                   new positions, largest adds and cuts, exits
  weekly           Saturday recap thread: fastest growers and biggest margin gains among the week's filers, the week's
                   largest insider purchases, the hottest names on the Signals board, the week's movers
  insider          the largest recent Form 4 open-market purchase by an officer or director of a site company
                   (Disclosures → Insider trades), with the company's latest figures
Each post is drafted from the guide, then polished (sharper opening, same facts), then checked (length, cashtags,
hashtags, no advice words). Written to media/x/pending.json for pipeline/buffer.py; media/x/engage-state.json keeps
what was posted so a company or a format is not repeated within the cooldown. Settings: config/engage.json.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time

from . import events, notify, quotes as Q, reddit, social, tweet

CFG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "engage.json")
GUIDE = os.path.join(os.path.dirname(CFG), "engage-guide.md")
DEFAULTS = {
    "days": 1,                      # "filed in the last N days" for question / list
    "min_revenue": 100_000_000,     # smaller filers are noise on X
    "list_max": 6,                  # cashtags in a list post
    "cooldown_days": 10,            # per company and kind
    "kind_cooldown_hours": 20,      # the same format at most once a day
    "hashtags": ["#earnings", "#stocks"],
    "polish": True,
    "movers": {"min_move_pct": 8, "min_mcap": 5e9, "min_quarter_revenue": 250e6, "max_per_day": 3, "min_gap_minutes": 45,
               "ticker_cooldown_hours": 20, "peers": 2},
}
MOVER_KINDS = ("mover", "explain", "peers")
INSIDER = {"min_value": 250_000, "max_age_days": 5, "cooldown_days": 14}


def cfg():
    out = dict(DEFAULTS)
    try:
        out.update(json.load(open(CFG, encoding="utf-8")))
    except FileNotFoundError:
        pass
    if os.environ.get("MOVERS_MIN_MOVE_PCT"):              # Run workflow → "min_move": try a lower threshold once
        out["movers"] = {**DEFAULTS["movers"], **out.get("movers", {}), "min_move_pct": float(os.environ["MOVERS_MIN_MOVE_PCT"])}
    return out


def guide():
    try:
        return open(GUIDE, encoding="utf-8").read()
    except FileNotFoundError:
        return "Write one neutral, factual engagement post for X under 255 characters, ending with the given hashtags."


# ------------------------------------------------------------------ picking
def recent_filers(rows, days, min_revenue, today):
    since = (today - dt.timedelta(days=days)).isoformat()
    out = [e for e in rows if (e.get("filed") or "") >= since and e.get("ticker") and (e.get("revenue") or 0) >= min_revenue]
    return sorted(out, key=lambda e: -(e.get("revenue") or 0))


def striking(e):
    """How much a filer stands out: growth or shrinkage, extreme margins, big revenue."""
    yoy, om = e.get("yoy"), e.get("om")
    s = (abs(yoy) if isinstance(yoy, (int, float)) else 0) + (abs(om - 10) * 0.5 if isinstance(om, (int, float)) else 0)
    s += 5 if (e.get("revenue") or 0) >= 1e9 else 0
    s += 3 if e.get("starred") else 0
    return s


def one_liner(e):
    bits = [f"${e['ticker']}", e.get("label") or ""]
    if e.get("rev"):
        bits.append(f"revenue {e['rev']}")
    if isinstance(e.get("yoy"), (int, float)):
        bits.append(f"{e['yoy']:+.0f}% Y/Y")
    if isinstance(e.get("om"), (int, float)):
        bits.append(f"operating margin {e['om']:.1f}%")
    if e.get("prelim"):
        bits.append("(preliminary, 8-K)")
    return " · ".join(b for b in bits if b)


# ------------------------------------------------------------------ writing
def clean(post, cashtags, tags, limit=255, allowed=None):
    post = re.sub(r"\s*\n+\s*", " ", post.strip().strip('"“”')).strip()
    missing = [t for t in cashtags if f"${t.upper()}" not in post.upper()]
    if missing:
        raise ValueError("cashtag missing: " + " ".join(missing))
    ok = {t.upper() for t in list(cashtags) + list(allowed or [])}
    extra = {m.upper() for m in re.findall(r"\$([A-Za-z][A-Za-z.]{0,6})\b", post)} - ok
    if extra:
        raise ValueError("only these cashtags may appear: " + " ".join("$" + t for t in sorted(ok)) + f" (not {' '.join('$' + x for x in sorted(extra))})")
    if not all(t.lower() in post.lower() for t in tags):
        post = re.sub(r"(\s*#\w+)+\s*$", "", post).rstrip() + " " + " ".join(tags)
    if tweet.ADVICE.search(re.sub(r"#\w+", "", post)) or "!" in post:
        raise ValueError("advice / hype wording or exclamation mark")
    if social.xlen(post) > limit:
        raise ValueError(f"too long ({social.xlen(post)})")
    return post


def write(kind, task, cashtags, tags, polish=True, allowed=None):
    others = [t for t in (allowed or []) if t not in cashtags]
    msgs = [{"role": "system", "content": guide()},
            {"role": "user", "content": f"FORMAT: {kind}\n\n{task}\n\nCashtags that must appear: " + " ".join(f"${t}" for t in cashtags)
             + (("\nOther cashtags you may use (no others): " + " ".join(f"${t}" for t in others)) if others else "")
             + "\nHashtags to end with, in this order: " + " ".join(tags) + "\n\nWrite the post now."}]
    draft = tweet.chat(msgs)
    if polish:
        msgs += [{"role": "assistant", "content": draft},
                 {"role": "user", "content": "Polish pass: keep every number, cashtag, option and hashtag exactly; sharper, more specific "
                                             "opening; cut filler; under 250 characters. Output only the polished post."}]
        draft = tweet.chat(msgs)
    try:
        return clean(draft, cashtags, tags, allowed=allowed)
    except ValueError as why:
        msgs += [{"role": "assistant", "content": draft},
                 {"role": "user", "content": f"Rewrite: {why}. Under 240 characters, every required cashtag present, ending with the hashtags."}]
        return clean(tweet.chat(msgs), cashtags, tags, allowed=allowed)


# ------------------------------------------------------------------ the kinds
def figures(site, e):
    c, q = notify.find_quarter(site, e["cik"], e["end"], "q")
    return c, q


def plan_question(site, rows, c, today, state_ok):
    cands = [e for e in recent_filers(rows, c["days"], c["min_revenue"], today) if state_ok("question", e["ticker"])]
    if not cands:
        return None
    e = max(cands, key=striking)
    cj, q = figures(site, e)
    if not q:
        return None
    task = ("The company that stands out among the last day's filings:\n" + tweet.headline_lines(cj, q, e["ticker"])
            + "\n\nAsk the question this quarter raises (growth vs. margin, one-off vs. trend, preliminary vs. final…).")
    return {"kind": "question", "task": task, "cashtags": [e["ticker"]], "items": [(e, cj, q)]}


def plan_list(site, rows, c, today, state_ok):
    filers = recent_filers(rows, c["days"], c["min_revenue"], today)
    if len(filers) < 2:
        return None
    picks = sorted(filers, key=striking, reverse=True)[:c["list_max"]]
    standout = picks[0]
    cj, q = figures(site, standout)
    lines = "\n".join("- " + one_liner(e) for e in picks)
    task = (f"{len(filers)} companies on the site filed in the last {c['days']} day(s); the ones to name:\n{lines}\n\n"
            f"The standout is ${standout['ticker']}:\n" + (tweet.headline_lines(cj, q, standout["ticker"]) if q else one_liner(standout)))
    items = []
    for e in picks[:4]:
        cj2, q2 = figures(site, e)
        if q2:
            items.append((e, cj2, q2))
    return {"kind": "list", "task": task, "cashtags": [e["ticker"] for e in picks], "items": items}


def reddit_trends(site_rows, c):
    rc = reddit.cfg()
    known = {(e.get("ticker") or "").upper() for e in site_rows if e.get("ticker")}
    token = None
    try:
        token = reddit._token()
    except Exception as err:
        print(f"::warning::Reddit OAuth not used ({err}); public listing instead")
    threads = []
    for sub in rc["subreddits"]:
        try:
            threads += reddit.hot(sub, rc["per_sub"], token)
        except Exception as err:
            print(f"::warning::r/{sub} not read ({err})")
        if not token:
            time.sleep(2)
    trends = reddit.trending(threads, known, rc)
    print(f"reddit: {len(threads)} threads, {len(trends)} companies on the site trending: "
          + ", ".join(f"{a['ticker']}({a['score']})" for a in trends[:10]))
    return trends


def thread_lines(trend):
    return "\n".join(f"- r/{t['sub']}: \"{t['title']}\" ({t['score']} points, {t['comments']} comments)" for t in trend["threads"][:4])


def plan_reddit_question(site, rows, c, trends, by_ticker, state_ok):
    for a in trends:
        if not state_ok("reddit_question", a["ticker"]):
            continue
        e = by_ticker[a["ticker"]]
        cj, q = figures(site, e)
        if not q:
            continue
        task = (f"Reddit threads behind the trend:\n{thread_lines(a)}\n\nHeadline figures from ${a['ticker']}'s latest filing:\n"
                + tweet.headline_lines(cj, q, a["ticker"]))
        return {"kind": "reddit_question", "task": task, "cashtags": [a["ticker"]], "items": [(e, cj, q)]}
    return None


def plan_reddit_list(site, rows, c, trends, by_ticker, state_ok):
    picks = [a for a in trends if state_ok("reddit_list", a["ticker"])][:5]
    if len(picks) < 3:
        return None
    lines = []
    items = []
    for a in picks:
        e = by_ticker[a["ticker"]]
        lines.append(f"- {one_liner(e)} — Reddit: {a['threads'][0]['title'][:90]!r} ({a['score']} points+comments)")
        if len(items) < 4:
            cj, q = figures(site, e)
            if q:
                items.append((e, cj, q))
    task = "Trending on investing subreddits right now, most-discussed first:\n" + "\n".join(lines)
    return {"kind": "reddit_list", "task": task, "cashtags": [a["ticker"] for a in picks], "items": items}


# ------------------------------------------------------------------ price moves
def money(v):
    if v is None:
        return "—"
    a = abs(v)
    s = (f"${a / 1e12:.2f}T" if a >= 1e12 else f"${a / 1e9:.1f}B" if a >= 1e9 else f"${a / 1e6:.0f}M" if a >= 1e8
         else f"${a / 1e6:.1f}M" if a >= 1e6 else f"${a / 1e3:.0f}K")
    return ("−" if v < 0 else "") + s


def quote_line(t, q, e):
    bits = [f"${t} at ${q['price']:,.2f} ({q['chg_pct']:+.1f}% today)" if q.get("chg_pct") is not None else f"${t} at ${q['price']:,.2f}"]
    if q.get("mcap"):
        bits.append(f"market value {money(q['mcap'])}")
        if e and e.get("revenue"):
            bits.append(f"price/sales ≈ {q['mcap'] / (e['revenue'] * 4):.1f}× (market value ÷ latest quarter's revenue × 4)")
    return " · ".join(bits)


def movers_today(rows, c, live):
    """Site companies by size of today's move, filtered by the movers settings. live: {ticker: quote}."""
    m = c["movers"]
    out = []
    for e in rows:
        t = e.get("ticker")
        q = live.get(Q.canon(t)) if t else None
        if not q or q.get("chg_pct") is None:
            continue
        if q.get("mcap"):
            big, sane = q["mcap"] >= m["min_mcap"], abs(q["chg_pct"]) <= m.get("max_move_pct", 150)
        else:                                  # Yahoo fallback: no market value, so revenue as the size test and a tighter cap
            big, sane = (e.get("revenue") or 0) >= m["min_quarter_revenue"], abs(q["chg_pct"]) <= m.get("max_move_unverified_pct", 50)
        if big and sane and abs(q["chg_pct"]) >= m["min_move_pct"]:
            out.append((e, q))
    return sorted(out, key=lambda eq: -abs(eq[1]["chg_pct"]))


def peers_of(e, rows, live, n):
    same = [x for x in rows if x is not e and x.get("ticker") and x.get("sic") and x.get("sic") == e.get("sic") and live.get(Q.canon(x["ticker"]))]
    if len(same) < n:
        same += [x for x in rows if x is not e and x not in same and x.get("ticker") and x.get("industry") == e.get("industry")
                 and live.get(Q.canon(x["ticker"]))]
    seen, out = {e["ticker"]}, []
    for x in sorted(same, key=lambda x: -(x.get("revenue") or 0)):
        if x["ticker"] not in seen:
            seen.add(x["ticker"]); out.append(x)
    return out[:n]


def plan_mover(kind, site, rows, c, live, state_ok, trends=None):
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%H:%M UTC")
    for e, q in movers_today(rows, c, live):
        if not state_ok("mover", e["ticker"], hours=c["movers"]["ticker_cooldown_hours"]):
            continue
        cj, fq = figures(site, e)
        if not fq:
            continue
        chatter = ""
        for a in trends or []:
            if a["ticker"] == e["ticker"]:
                chatter = "\n\nWhat Reddit is discussing about it (titles, not facts):\n" + thread_lines(a)
        ev = events.explain(e["cik"])
        if ev:
            filed = f"8-K filed {ev['filed']}" + (f" {ev['accepted'][11:16]} ET" if len(ev.get("accepted") or "") >= 16 else "")
            news = (f"\n\nWHAT THE COMPANY FILED WITH THE SEC ({filed}, Item {ev['code']}: {ev['label']}):\n"
                    f"“{ev['quote'] or '(text not read; name the item only)'}”\n"
                    "You may say the company filed this (\"after an 8-K: …\", \"filed today: …\") and quote or closely paraphrase it. "
                    "Do not say it caused the move, and add nothing that is not in the quote.")
            ask = "Then ask the audience how they read it."
        else:
            news, ask = "", "The cause of today's move is NOT in these inputs: do not guess or imply one; ask the audience."
        task = (f"PRICE MOVE (delayed quote, {stamp}): {quote_line(e['ticker'], q, e)}.{news}\n\n"
                f"Latest filing figures (the only other numbers you may use):\n{tweet.headline_lines(cj, fq, e['ticker'])}{chatter}\n\n{ask}")
        items = [(e, cj, fq)]
        cashtags = [e["ticker"]]
        if kind == "peers":
            ps = peers_of(e, rows, live, c["movers"]["peers"])
            if not ps:
                continue
            lines = []
            for x in ps:
                cx, qx = figures(site, x)
                lines.append(f"- {quote_line(x['ticker'], live[Q.canon(x['ticker'])], x)} · {one_liner(x)}")
                if qx:
                    items.append((x, cx, qx))
            task = (f"THE MOVER (delayed quote, {stamp}): {quote_line(e['ticker'], q, e)} · {one_liner(e)}\n\n"
                    f"Its closest listed peers on Filing Flows (same industry: {e.get('industry') or e.get('sic')}):\n" + "\n".join(lines)
                    + "\n\nCompare them on price, today's move, growth, margin and price/sales — only these numbers. Do not guess "
                      "why the mover moved.")
            cashtags += [x["ticker"] for x in ps]
        return {"kind": kind, "task": task, "cashtags": cashtags, "items": items, "mover": e["ticker"],
                "event": ev if kind != "peers" else None}
    return None


# ------------------------------------------------------------------ Saturday recap thread
def _year_ago_om(cj, q):
    try:
        end = dt.date.fromisoformat(q["end"])
    except (KeyError, ValueError):
        return None
    for x in cj.get("quarters") or []:
        try:
            d = abs((dt.date.fromisoformat(x["end"]) - (end - dt.timedelta(days=365))).days)
        except (KeyError, ValueError):
            continue
        if d <= 20:
            return (x.get("headline") or {}).get("om")
    return None


def plan_weekly(site, rows, c, by_ticker, state, today):
    since = (today - dt.timedelta(days=7)).isoformat()
    week = [e for e in rows if (e.get("filed") or "") >= since and e.get("ticker") and (e.get("revenue") or 0) >= 500e6]
    if len(week) < 3:
        print(f"weekly: only {len(week)} sizeable filers this week")
        return None
    growers = sorted((e for e in week if isinstance(e.get("yoy"), (int, float)) and e["yoy"] > 0), key=lambda e: -e["yoy"])[:3]
    margin = []
    for e in sorted(week, key=lambda e: -(e.get("revenue") or 0))[:60]:
        cj, q = figures(site, e)
        if not q:
            continue
        now_om, ago = (q.get("headline") or {}).get("om"), _year_ago_om(cj, q)
        if isinstance(now_om, (int, float)) and isinstance(ago, (int, float)) and abs(now_om) < 200 and abs(ago) < 200:
            margin.append((now_om - ago, e, now_om))
    margin = sorted((m for m in margin if m[0] > 0), key=lambda x: -x[0])[:3]
    try:
        ins = [t for t in hub_json(site, "insiders.json").get("latest", []) if t.get("code") == "P" and (t.get("date") or "") >= since]
    except Exception:
        ins = []
    ins = sorted(ins, key=lambda t: -(t.get("value") or 0))[:3]
    try:
        hot = [r for r in hub_json(site, "signals.json").get("rows", []) if r.get("heat", 0) >= 3][:3]
    except Exception:
        hot = []
    moved = [x for x in state.get("movers_log", []) if x[0][:10] >= since]
    T = lambda t: "$" + t.replace("-", ".")
    posts, allowed = [], []
    if growers:
        posts.append("Fastest revenue growth among this week's filers:\n" + "\n".join(
            f"· {T(e['ticker'])} {e.get('rev')} ({e['yoy']:+.0f}% Y/Y, {e.get('label')})" for e in growers))
        allowed += [e["ticker"] for e in growers]
    if margin:
        posts.append("Biggest operating-margin gains vs a year ago:\n" + "\n".join(
            f"· {T(e['ticker'])} {om:.1f}% ({d:+.1f} pts)" for d, e, om in margin))
        allowed += [e["ticker"] for _, e, _ in margin]
    if ins:
        posts.append("Largest insider purchases filed this week (Form 4):\n" + "\n".join(
            f"· {T(t['ticker'])} {t.get('role')} {t.get('insider', '').title()}: {money(t.get('value'))}" for t in ins))
        allowed += [t["ticker"] for t in ins]
    if hot:
        posts.append("Hottest on the Signals board (13F crowding, insiders, officials, momentum):\n" + "\n".join(
            f"· {T(r['ticker'])}: " + ", ".join(x.replace("_", " ") for x in r["tags"][:3]) for r in hot))
        allowed += [r["ticker"] for r in hot]
    if moved:
        posts.append("This week's big moves we covered: " + ", ".join(sorted({T(x[2]) for x in moved})))
        allowed += [x[2] for x in moved]
    posts = [p if social.xlen(p) <= 280 else p[:270].rsplit("\n", 1)[0] for p in posts]
    allowed = list(dict.fromkeys(t.replace("-", ".") for t in allowed))
    items = []
    for t in allowed:
        if t in by_ticker and len(items) < 4:
            cj, q = figures(site, by_ticker[t])
            if q:
                items.append((by_ticker[t], cj, q))
    task = (f"WEEKLY RECAP, week ending {today:%b} {today.day}. The thread below this post lists:\n" + "\n\n".join(posts)
            + "\n\nWrite the opening post of the thread: the single most striking item, then 'Thread ↓'. One or two cashtags.")
    lead = (growers[0]["ticker"] if growers else allowed[0]) if allowed else None
    return {"kind": "weekly", "task": task, "cashtags": [lead] if lead else [], "allowed": allowed, "items": items, "thread": posts}


# ------------------------------------------------------------------ watched funds' 13F
def plan_fund13f(site, rows, c, by_ticker, state, today):
    try:
        d = hub_json(site, "watchlist.json")
    except Exception as err:
        print(f"fund13f: no watchlist ({str(err)[:100]})")
        return None
    since = (today - dt.timedelta(days=4)).isoformat()
    fresh = [f for f in d.get("funds", []) if (f.get("filed") or "") >= since and f"fund13f:{f['cik']}:{f['period']}" not in state]
    if not fresh:
        print("fund13f: no watched fund filed a new 13F in the last four days")
        return None
    f = fresh[0]
    tag = lambda r: f"${r['ticker'].replace('-', '.')}" if r.get("ticker") else r.get("issuer", "")
    line = lambda rs: ", ".join(f"{tag(r)} ({money(r['usd'])})" for r in rs[:4]) or "none"
    task = (f"13F JUST FILED: {f['name']} — holdings at the quarter ended {f['period']}, filed {f['filed']} "
            f"({f['positions']} positions, {money(f['total_usd'])} disclosed).\n"
            f"New positions: {line(f['new'])}\nLargest additions: {line(f['added'])}\nLargest cuts: {line(f['cut'])}\n"
            f"Sold out of: {line(f['exited'])}\nLargest holdings now: " + ", ".join(f"{tag(r)} {r['weight']}%" for r in f["top"][:4])
            + "\n\nDollar figures are the change in shares × the quarter-end price. These are quarter-end holdings, not trades on a "
              "known date. Ask the audience which move stands out.")
    cash = []
    for r in f["new"] + f["added"] + f["exited"] + f["cut"]:
        t = (r.get("ticker") or "").replace("-", ".")
        if t and t not in cash and f"${t}" in task:
            cash.append(t)
    items = []
    for t in cash:
        if t in by_ticker and len(items) < 2:
            cj, fq = figures(site, by_ticker[t])
            if fq:
                items.append((by_ticker[t], cj, fq))
    return {"kind": "fund13f", "task": task, "cashtags": cash[:2], "allowed": cash, "items": items, "fund_key": f"fund13f:{f['cik']}:{f['period']}",
            "fund_url": f.get("source")}


# ------------------------------------------------------------------ tomorrow's earnings
def next_trading_day(today):
    d = today + dt.timedelta(days=1)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


def plan_calendar(site, rows, c, by_ticker, today):
    day = next_trading_day(today)
    try:
        cal = Q.earnings_calendar(day)
    except Exception as err:
        print(f"calendar: Nasdaq calendar not reached ({str(err)[:100]})")
        return None
    ours = [r for r in cal if r["ticker"].replace("-", ".") in by_ticker]
    ours.sort(key=lambda r: -(r.get("mcap") or 0))
    picks = ours[:c["list_max"]]
    print(f"calendar: {len(cal)} companies report on {day}, {len(ours)} of them on the site")
    if len(picks) < 2:
        return None
    lines, items = [], []
    for r in picks:
        e = by_ticker[r["ticker"].replace("-", ".")]
        est = f" · EPS estimate {r['eps_estimate']} ({r['estimates']:.0f} analysts, per Nasdaq)" if r.get("eps_estimate") and r.get("estimates") else ""
        lines.append(f"- ${e['ticker']} reports {r['when']}{' · market value ' + money(r['mcap']) if r.get('mcap') else ''}{est}\n"
                     f"  last quarter on Filing Flows: {one_liner(e)}")
        if len(items) < 4:
            cj, fq = figures(site, e)
            if fq:
                items.append((e, cj, fq))
    task = (f"EARNINGS ON {day:%A %b} {day.day} (Nasdaq calendar), the largest companies first:\n" + "\n".join(lines)
            + "\n\nThe charts attached show each one's LAST quarter. Say who reports and when; one fact for the biggest; ask "
              "which report the audience is watching or what number matters most.")
    return {"kind": "calendar", "task": task, "cashtags": [by_ticker[r["ticker"].replace("-", ".")]["ticker"] for r in picks], "items": items}


# ------------------------------------------------------------------ insider purchases (Form 4)
def hub_json(site, name):
    """A file of the Disclosures hub's market data, from the published site or the built folder."""
    import requests
    if site.remote:
        r = requests.get(site.src.rstrip("/") + "/disclosures/data/market/" + name, timeout=60)
        r.raise_for_status()
        return r.json()
    return json.load(open(os.path.join(site.src, "disclosures", "data", "market", name), encoding="utf-8"))


def plan_insider(site, rows, c, by_ticker, state_ok, today):
    cfg = {**INSIDER, **(c.get("insider") or {})}
    try:
        d = hub_json(site, "insiders.json")
    except Exception as err:
        print(f"insider: no Form 4 data ({str(err)[:100]})")
        return None
    since = (today - dt.timedelta(days=cfg["max_age_days"])).isoformat()
    clusters = {a["ticker"]: a for a in d.get("summary", []) if a.get("cluster")}
    cands = []
    for t in d.get("latest", []):
        tk = (t.get("ticker") or "").upper().replace("-", ".")
        if t.get("code") != "P" or (t.get("value") or 0) < cfg["min_value"] or t.get("date", "") < since or tk not in by_ticker:
            continue
        if t.get("role") not in ("CEO", "CFO", "President", "COO", "Chair", "Officer", "Director"):
            continue
        if not state_ok("insider", tk, hours=24 * cfg["cooldown_days"]):
            continue
        cands.append((tk, t))
    if not cands:
        return None
    tk, t = max(cands, key=lambda x: ((x[0] in clusters), x[1]["value"]))
    e = by_ticker[tk]
    cj, fq = figures(site, e)
    if not fq:
        return None
    cl = clusters.get(tk)
    after = f"; holds {t['after']:,.0f} shares after the trade" if t.get("after") else ""
    task = (f"FORM 4 (filed with the SEC within two business days of the trade): {t['insider']} ({t.get('title') or t['role']}) bought "
            f"{t['shares']:,.0f} shares of ${tk} at ${t['price']:,.2f} on {t['date']} — {money(t['value'])} in the open market{after}."
            + (" This was NOT under a 10b5-1 plan." if t.get("plan_10b5_1") is False else "")
            + (f"\nCluster: {cl['buyers30']} insiders bought ${tk} within 30 days ({', '.join(cl['buyers'][:4])})." if cl else "")
            + f"\n\nLatest filing figures (the only other numbers you may use):\n{tweet.headline_lines(cj, fq, tk)}"
            + "\n\nSay what the insider did and when; never say it means the stock will rise. Ask the audience how they read it.")
    return {"kind": "insider", "task": task, "cashtags": [tk], "items": [(e, cj, fq)], "insider_url": t.get("url")}


# ------------------------------------------------------------------ main
def make(kinds, site, site_url, media, assets, dry_run=False, force=False, plan_only=False):
    """Plan, write, polish and check the posts of these kinds; draw the charts into media/x/ and append to
    media/x/pending.json. force=True ignores the per-format cooldown (Owner tools "write it now"). Returns the labels made."""
    c = cfg()
    ix = site.json("index.json")
    rows = ix["companies"] if isinstance(ix, dict) else ix
    for e in rows:
        if e.get("ticker"):
            e["ticker"] = e["ticker"].upper().replace("-", ".")
    by_ticker = {}
    for e in rows:
        t = e.get("ticker")
        if t and (t not in by_ticker or (e.get("filed") or "") > (by_ticker[t].get("filed") or "")):
            by_ticker[t] = e
    today = dt.datetime.now(dt.timezone.utc).date()
    now = dt.datetime.now(dt.timezone.utc)

    xdir = os.path.join(media, "x")
    state_path = os.path.join(xdir, "engage-state.json")
    state = json.load(open(state_path, encoding="utf-8")) if os.path.exists(state_path) else {}

    def state_ok(kind, ticker, hours=None):
        since = now - (dt.timedelta(hours=hours) if hours else dt.timedelta(days=c["cooldown_days"]))
        return (state.get(f"{kind}:{ticker}") or "") < since.isoformat()

    log = [x for x in state.get("movers_log", []) if x[0][:10] == today.isoformat()]

    def kind_ok(kind):
        if kind == "fund13f":              # one post per fund and filing, however many funds file the same day
            return True
        if kind in MOVER_KINDS:            # movers: a daily cap and a minimum gap instead of once a day per format
            if force:
                return True
            if len(log) >= c["movers"]["max_per_day"]:
                print(f"{kind}: {len(log)} mover posts already today (max_per_day)")
                return False
            return not log or log[-1][0] < (now - dt.timedelta(minutes=c["movers"]["min_gap_minutes"])).isoformat()
        return force or (state.get(f"kind:{kind}") or "") < (now - dt.timedelta(hours=c["kind_cooldown_hours"])).isoformat()

    if "movers" in kinds:                  # the workflow's rotation: mover, then peers, then explain
        kinds = [k for k in kinds if k != "movers"] + [MOVER_KINDS[[0, 2, 1][len(log) % 3]]]
    trends = None
    live = None
    plans = []
    for kind in kinds:
        if not kind_ok(kind):
            print(f"{kind}: posted recently; skipped")
            continue
        if kind in ("reddit_question", "reddit_list") and trends is None:
            trends = reddit_trends(rows, c)
        if kind in MOVER_KINDS and live is None:
            wanted = sorted({e["ticker"] for e in rows if e.get("ticker") and (e.get("revenue") or 0) >= c["movers"]["min_quarter_revenue"] / 4},
                            key=lambda t: -(by_ticker[t].get("revenue") or 0))
            live = Q.quotes(wanted)
            top = movers_today(rows, c, live)[:8]
            print("movers: " + (", ".join(f"{e['ticker']} {q['chg_pct']:+.1f}%" for e, q in top) or "none past the threshold"))
        p = {"question": lambda: plan_question(site, rows, c, today, state_ok),
             "list": lambda: plan_list(site, rows, c, today, state_ok),
             "reddit_question": lambda: plan_reddit_question(site, rows, c, trends, by_ticker, state_ok),
             "reddit_list": lambda: plan_reddit_list(site, rows, c, trends, by_ticker, state_ok),
             "mover": lambda: plan_mover("mover", site, rows, c, live, state_ok, trends),
             "explain": lambda: plan_mover("explain", site, rows, c, live, state_ok, trends),
             "peers": lambda: plan_mover("peers", site, rows, c, live, state_ok, trends),
             "insider": lambda: plan_insider(site, rows, c, by_ticker, state_ok, today),
             "calendar": lambda: plan_calendar(site, rows, c, by_ticker, today),
             "fund13f": lambda: plan_fund13f(site, rows, c, by_ticker, state, today),
             "weekly": lambda: plan_weekly(site, rows, c, by_ticker, state, today)}.get(kind, lambda: None)()
        if p:
            plans.append(p)
        else:
            print(f"{kind}: nothing to post")

    if plan_only:                          # the workflow's cheap first pass: is there anything to post at all?
        for p in plans:
            print(f"planned: {p['kind']} " + " ".join("$" + t for t in p["cashtags"]))
        return [p["kind"] for p in plans]
    tags = [t for t in c["hashtags"] if t]
    made = []
    for p in plans:
        try:
            post = write(p["kind"], p["task"], p["cashtags"], tags, polish=c.get("polish", True), allowed=p.get("allowed"))
        except Exception as err:
            print(f"::warning::{p['kind']}: no post ({str(err)[:160]})")
            continue
        e0, cj0, q0 = p["items"][0] if p["items"] else (None, None, None)
        reply = ("Charts: " + "; ".join(f"${e['ticker']} {q['label']} ({q.get('form')} filed {q.get('filed')})" for e, _, q in p["items"])
                 + f". Read automatically from the filings; not investment advice. {site_url}/#c-{e0['cik']}") if e0 else ""
        if reply and social.xlen(reply) > 280:
            reply = reply.replace(" Read automatically from the filings; not investment advice.", " Not investment advice.")
        filing = f"The Form 4: {p['insider_url']}" if p.get("insider_url") else f"The 13F: {p['fund_url']}" if p.get("fund_url") else ""
        if p.get("event"):
            ev = p["event"]
            filing = f"The filing: 8-K Item {ev['code']} ({ev['label']}), filed {ev['filed']}. {ev['url']}"
            if social.xlen(filing) > 280:
                filing = f"The filing: 8-K Item {ev['code']}, filed {ev['filed']}. {ev['url']}"
        print(f"[{p['kind']}] {post}" + "".join(f"\n   ↳ {x}" for x in list(p.get("thread") or []) + [filing, reply] if x))
        if dry_run:
            made.append(f"{p['kind']}: {post}")
            continue
        os.makedirs(xdir, exist_ok=True)
        images = []
        for e, cj, q in p["items"][:4]:
            png = assets.image(e, cj, q, "std", "png")
            if png:
                name = social.image_names(e, q, 1)[0].replace("-1-chart", f"-{p['kind']}")
                open(os.path.join(xdir, name), "wb").write(png)
                images.append(name)
        pend_path = os.path.join(xdir, "pending.json")
        pending = json.load(open(pend_path, encoding="utf-8")) if os.path.exists(pend_path) else []
        pending.append({"cik": e0["cik"] if e0 else None, "end": e0["end"] if e0 else None, "label": f"{p['kind']}: " + " ".join(p["cashtags"]),
                        "posts": [post] + list(p.get("thread") or []) + [x for x in (filing, reply) if x], "written_by": "model", "images": images})
        json.dump(pending, open(pend_path, "w", encoding="utf-8"), ensure_ascii=False)
        stamp = now.isoformat()
        state[f"kind:{p['kind']}"] = stamp
        for t in p["cashtags"]:
            state[f"{p['kind']}:{t}"] = stamp
        if p.get("fund_key"):
            state[p["fund_key"]] = stamp
        if p.get("mover"):
            state[f"mover:{p['mover']}"] = stamp
            log.append([stamp, p["kind"], p["mover"]])
            state["movers_log"] = [x for x in state.get("movers_log", []) if x[0] >= (now - dt.timedelta(days=7)).isoformat()] + [log[-1]]
        json.dump(state, open(state_path, "w", encoding="utf-8"))
        made.append(f"{p['kind']}: {post}")
    return made


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--site", default=os.environ.get("SITE_URL") or "_site")
    ap.add_argument("--site-url", default=None)
    ap.add_argument("--media", default=os.environ.get("MEDIA_DIR", "media"))
    ap.add_argument("--kinds", default="question,list,reddit_question,reddit_list",
                    help="comma-separated: question, list, reddit_question, reddit_list, mover, explain, peers, movers (rotation)")
    ap.add_argument("--force", action="store_true", help="ignore the per-format cooldown")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--plan-only", action="store_true", help="only decide whether anything would be posted; exit 3 when nothing")
    args = ap.parse_args()
    kinds = [k.strip() for k in args.kinds.split(",") if k.strip()]
    site = notify.Site(args.site)
    site_url = (args.site_url or os.environ.get("SITE_URL") or (args.site if site.remote else "")).rstrip("/")
    if args.plan_only:
        return 0 if make(kinds, site, site_url, args.media, None, plan_only=True, force=args.force) else 3
    with notify.Assets(site, enabled=not args.dry_run) as assets:
        made = make(kinds, site, site_url, args.media, assets, dry_run=args.dry_run, force=args.force)
    if made and not args.dry_run and os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice::engagement post(s) written for Buffer: {'; '.join(m.split(':')[0] for m in made)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
