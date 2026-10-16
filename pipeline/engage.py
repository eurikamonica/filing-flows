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
import math
import os
import re
import sys
import time

from . import events, notify, quotes as Q, reddit, sec, social, tweet

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
    if tweet.cut_off(post):
        raise ValueError("the post stops mid-sentence; finish the last sentence")
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
    if not threads:                        # Reddit refused (no OAuth secrets on a cloud runner): mention counts instead
        try:
            trends = [a for a in reddit.apewisdom(known) if a["mentions"] >= rc.get("min_mentions", 15)]
            print(f"::notice::reddit: no threads read; ApeWisdom mention counts used ({len(trends)} companies on the site: "
                  + ", ".join(f"{a['ticker']} {a['mentions']}" for a in trends[:8]) + ")")
        except Exception as err:
            print(f"::warning::ApeWisdom not read either ({str(err)[:120]})")
    print(f"reddit: {len(threads)} threads, {len(trends)} companies on the site trending: "
          + ", ".join(f"{a['ticker']}({a['score']})" for a in trends[:10]))
    return trends


def thread_lines(trend):
    if not trend.get("threads"):
        before = f", {trend['mentions_before']} the day before" if trend.get("mentions_before") is not None else ""
        rank = f"; #{trend['rank']} most-mentioned stock" + (f" (#{trend['rank_before']} a day earlier)" if trend.get("rank_before") else "") if trend.get("rank") else ""
        return f"- mentioned {trend['mentions']} times across investing subreddits in 24 hours{before}{rank} (counts from ApeWisdom; no thread titles)"
    return "\n".join(f"- r/{t['sub']}: \"{t['title']}\" ({t['score']} points, {t['comments']} comments)" for t in trend["threads"][:4])


def plan_reddit_question(site, rows, c, trends, by_ticker, state_ok):
    for a in trends:
        if not state_ok("reddit_question", a["ticker"]):
            continue
        e = by_ticker[a["ticker"]]
        cj, q = figures(site, e)
        if not q:
            continue
        task = (f"{'Reddit threads behind the trend' if a.get('threads') else 'How much Reddit is talking about it (counts only — say nothing about what they say)'}:\n{thread_lines(a)}\n\nHeadline figures from ${a['ticker']}'s latest filing:\n"
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
        lines.append(f"- {one_liner(e)} — Reddit: {a['threads'][0]['title'][:90]!r} ({a['score']} points+comments)" if a.get("threads")
                     else f"- {one_liner(e)} — {a['mentions']} Reddit mentions in 24 hours (was {a.get('mentions_before', '?')})")
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


def move_day(q):
    """'today' while the session is open; after the close (and in drafts read later) the session's date, e.g. 'on Oct 15'."""
    if Q.after_close() and q.get("asof"):
        d = dt.date.fromisoformat(q["asof"])
        return f"on {d:%b} {d.day}"
    return "today"


def quote_line(t, q, e):
    bits = [f"${t} at ${q['price']:,.2f} ({q['chg_pct']:+.1f}% {move_day(q)})" if q.get("chg_pct") is not None else f"${t} at ${q['price']:,.2f}"]
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
    checked = {}

    def sure(t):                       # every quoted price is re-read from Yahoo and dated to this session first
        k = Q.canon(t)
        if k not in checked:
            checked[k] = Q.confirm(k, live[k]) if live.get(k) else None
        return checked[k]

    for e, q in movers_today(rows, c, live):
        if not state_ok("mover", e["ticker"], hours=c["movers"]["ticker_cooldown_hours"]):
            continue
        q = sure(e["ticker"])
        if not q or q.get("chg_pct") is None or abs(q["chg_pct"]) < c["movers"]["min_move_pct"]:
            continue
        day = move_day(q)
        stamp = (f"close of the {q['asof']} session; write “{day}”, never “today”" if day != "today"
                 else f"delayed quote, {dt.datetime.now(Q.NY):%H:%M} ET")
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
            if ev["code"] in BREAKING_ITEMS or event_label(ev["code"], ev["quote"]) in ("a merger or acquisition", "a CEO change"):
                ask = "Start the post with “BREAKING:” (a material 8-K filed today). " + ask
        else:
            news, ask = "", "The cause of this move is NOT in these inputs: do not guess or imply one; ask the audience."
        task = (f"PRICE MOVE (delayed quote, {stamp}): {quote_line(e['ticker'], q, e)}.{news}\n\n"
                f"Latest filing figures (the only other numbers you may use):\n{tweet.headline_lines(cj, fq, e['ticker'])}{chatter}\n\n{ask}")
        items = [(e, cj, fq)]
        cashtags = [e["ticker"]]
        if kind == "peers":
            ps = [x for x in peers_of(e, rows, live, c["movers"]["peers"]) if sure(x["ticker"])]
            if not ps:
                continue
            lines = []
            for x in ps:
                cx, qx = figures(site, x)
                lines.append(f"- {quote_line(x['ticker'], sure(x['ticker']), x)} · {one_liner(x)}")
                if qx:
                    items.append((x, cx, qx))
            task = (f"THE MOVER (delayed quote, {stamp}): {quote_line(e['ticker'], q, e)} · {one_liner(e)}\n\n"
                    f"Its closest listed peers on Filing Flows (same industry: {e.get('industry') or e.get('sic')}):\n" + "\n".join(lines)
                    + "\n\nCompare them on price, the day's move, growth, margin and price/sales — only these numbers. Do not guess "
                      "why the mover moved.")
            cashtags += [x["ticker"] for x in ps]
        h = (fq.get("headline") or {})
        fact = (f" Last quarter: revenue {h.get('rev_fmt')}" + (f" ({h['yoy']:+.0f}% Y/Y)" if h.get("yoy") is not None else "")
                + (f", operating margin {h['om']:.1f}%" if h.get("om") is not None else "") + ".") if h.get("rev_fmt") else ""
        filed = f" after an 8-K ({event_label(ev['code'], ev['quote'])})." if ev else "."
        if kind == "peers":
            fb = f"${e['ticker']} {q['chg_pct']:+.1f}% {day} at ${q['price']:,.2f} vs " + ", ".join(
                f"${x['ticker']} {sure(x['ticker'])['chg_pct']:+.1f}%" for x in ps) + ". Which one makes more sense here?"
        else:
            lead = "Someone explain" if kind == "explain" else "What's happening with"
            if ev and (ev["code"] in BREAKING_ITEMS or event_label(ev["code"], ev["quote"]) in ("a merger or acquisition", "a CEO change")):
                lead = "BREAKING: " + lead
            fb = f"{lead} ${e['ticker']}? {q['chg_pct']:+.1f}% {day} at ${q['price']:,.2f}{filed}{fact}"
            if social.xlen(fb) > 235:
                fb = f"{lead} ${e['ticker']}? {q['chg_pct']:+.1f}% {day} at ${q['price']:,.2f}{filed}"
        return {"kind": kind, "task": task, "cashtags": cashtags, "items": items, "mover": e["ticker"],
                "event": ev if kind != "peers" else None, "fallback": fb}
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
def hub_file(site, rel):
    """Any published file of the Disclosures hub (rel: a path under disclosures/data/)."""
    import requests
    if site.remote:
        r = requests.get(site.src.rstrip("/") + "/disclosures/data/" + rel, timeout=60)
        r.raise_for_status()
        return r.json()
    return json.load(open(os.path.join(site.src, "disclosures", "data", rel), encoding="utf-8"))


def fund_summary(site, cik, accn=None):
    """One manager's 13F as the watchlist shape: new / added / cut / exited / top, from its published shards."""
    m = hub_file(site, f"shards/holdings/{int(cik)}.json")
    snaps = [s for s in m.get("snapshots", []) if s.get("complete") and s.get("positions_shard")]
    if accn:
        a = re.sub(r"[^0-9]", "", accn)
        pick = [i for i, s in enumerate(snaps) if a and a in re.sub(r"[^0-9]", "", json.dumps(s.get("sources") or ""))]
        if not pick:
            raise ValueError(f"accession {accn} not among the processed 13Fs of CIK {cik}")
        i = pick[-1]
    else:
        i = len(snaps) - 1
    if i < 0:
        raise ValueError(f"no processed 13F for CIK {cik} yet (the hub collects managers in batches)")
    cur = hub_file(site, snaps[i]["positions_shard"])
    prev = hub_file(site, snaps[i - 1]["positions_shard"]) if i > 0 else []
    try:
        cmap = hub_file(site, "market/cusip-tickers.json")
    except Exception:
        cmap = {}
    def book(rows):
        out = {}
        for r in rows or []:
            if r.get("put_call", "NONE") != "NONE" or r.get("share_type", "SH") != "SH":
                continue
            a = out.setdefault(r["cusip"], {"cusip": r["cusip"], "issuer": r.get("issuer"), "shares": 0, "usd": 0})
            a["shares"] += r.get("shares") or 0
            a["usd"] += r.get("value_usd") or 0
        return out
    now_, before = book(cur), book(prev)
    total = sum(x["usd"] for x in now_.values()) or 1
    rows = []
    for c_, x in now_.items():
        b = before.get(c_)
        px = x["usd"] / x["shares"] if x["shares"] else 0
        rows.append({"ticker": cmap.get(c_, ""), "issuer": x["issuer"], "usd": round((x["shares"] - (b["shares"] if b else 0)) * px),
                     "new": b is None and i > 0, "weight": round(100 * x["usd"] / total, 1), "value": x["usd"]})
    gone = [{"ticker": cmap.get(c_, ""), "issuer": b["issuer"], "usd": b["usd"]} for c_, b in before.items() if c_ not in now_]
    s = snaps[i]
    return {"cik": int(cik), "name": m.get("label") or m.get("name"), "period": s["period"], "filed": s.get("filed"),
            "positions": len(now_), "total_usd": total,
            "new": sorted([r for r in rows if r["new"]], key=lambda r: -r["value"]),
            "added": sorted([r for r in rows if not r["new"] and r["usd"] > 0], key=lambda r: -r["usd"]),
            "cut": sorted([{**r, "usd": -r["usd"]} for r in rows if r["usd"] < 0], key=lambda r: -r["usd"]),
            "exited": sorted(gone, key=lambda r: -r["usd"]), "top": sorted(rows, key=lambda r: -r["weight"])[:6],
            "source": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={int(cik)}&type=13F-HR&dateb=&owner=include&count=40"}


def plan_fund13f_for(site, rows, by_ticker, target):
    """Owner tools: a post about one manager's 13F (target cik = the manager; ref = an accession, or the latest)."""
    try:
        f = fund_summary(site, target["cik"], target.get("ref") or None)
    except Exception as err:
        print(f"fund13f: {str(err)[:200]}")
        return None
    p = fund_plan(site, f, by_ticker)
    p["fund_key"] = f"fund13f:{f['cik']}:{f['period']}"
    return p


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
    return fund_plan(site, fresh[0], by_ticker)


def fund_plan(site, f, by_ticker):
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
    nm = lambda r: f"${r['ticker'].replace('-', '.')}" if r.get("ticker") and r["ticker"].replace("-", ".") in cash[:2] + cash else (r.get("issuer") or "").title()
    bits = ([f"new: {', '.join(nm(r) for r in f['new'][:2])}"] if f["new"] else []) \
        + ([f"biggest cut: {nm(f['cut'][0])} −{money(f['cut'][0]['usd'])}"] if f["cut"] else []) \
        + ([f"biggest add: {nm(f['added'][0])} +{money(f['added'][0]['usd'])}"] if f["added"] else []) \
        + ([f"largest holding: {nm(f['top'][0])} {f['top'][0]['weight']}%"] if f["top"] else [])
    fb = f"13F: {f['name']} (quarter ended {f['period']}) — " + "; ".join(bits) + ". Which move stands out?"
    for t in cash[:2]:
        if f"${t}" not in fb:
            fb = fb.replace(". Which move", f" · ${t}. Which move", 1)
    return {"kind": "fund13f", "task": task, "cashtags": cash[:2], "allowed": cash, "items": items, "fund_key": f"fund13f:{f['cik']}:{f['period']}",
            "fund_url": f.get("source"), "fallback": fb}


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
    tags_ = [by_ticker[r["ticker"].replace("-", ".")]["ticker"] for r in picks]
    fb = f"Reporting on {day:%A}: " + ", ".join(f"${t} ({r['when']})" for t, r in zip(tags_, picks)) + ". Which one are you watching?"
    while social.xlen(fb) > 235 and len(tags_) > 2:
        tags_, picks = tags_[:-1], picks[:-1]
        fb = f"Reporting on {day:%A}: " + ", ".join(f"${t} ({r['when']})" for t, r in zip(tags_, picks)) + ". Which one are you watching?"
    return {"kind": "calendar", "task": task, "cashtags": tags_, "items": items, "fallback": fb}


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
    filed = t.get("filed")
    fresh = bool(filed) and filed >= (today - dt.timedelta(days=2)).isoformat()
    task = (f"FORM 4{f' filed {filed}' if filed else ' (filed within two business days of the trade)'}: {t['insider']} ({t.get('title') or t['role']}) bought "
            f"{t['shares']:,.0f} shares of ${tk} at ${t['price']:,.2f} on {t['date']} — {money(t['value'])} in the open market{after}."
            + (" Start the post with “JUST FILED:”." if fresh else "")
            + " Say who bought, how many shares, at what price, the trade date and the filing date."
            + (" This was NOT under a 10b5-1 plan." if t.get("plan_10b5_1") is False else "")
            + (f"\nCluster: {cl['buyers30']} insiders bought ${tk} within 30 days ({', '.join(cl['buyers'][:4])})." if cl else "")
            + f"\n\nLatest filing figures (the only other numbers you may use):\n{tweet.headline_lines(cj, fq, tk)}"
            + "\n\nSay what the insider did and when; never say it means the stock will rise. Ask the audience how they read it.")
    who = t.get('title') if t.get('title') and len(t['title']) <= 24 else t['role']
    fb = (("JUST FILED: " if fresh else "") + f"${tk} {who} {t['insider'].title()} bought {t['shares']:,.0f} shares ({money(t['value'])}) at "
          f"${t['price']:,.2f} on {t['date']}" + (f", Form 4 filed {filed}." if filed else " (Form 4).")
          + (f" {cl['buyers30']} insiders bought in 30 days." if cl else "") + " How do you read it?")
    return {"kind": "insider", "task": task, "cashtags": [tk], "items": [(e, cj, fq)], "insider_url": t.get("url"), "fallback": fb,
            "tags": TAGS["insider"]}


# ------------------------------------------------------------------ 8-K events (current reports)
# hashtags per post kind (the general config hashtags are for earnings posts); an 8-K adds one for its topic
TAGS = {"event8k": ["#8K", "#SEC", "#stocks", "#investing"],
        "fund13f": ["#13F", "#hedgefunds", "#smartmoney", "#stocks", "#investing"],
        "insider": ["#insiders", "#Form4", "#stocks", "#investing"]}
TOPIC_TAG = {"a merger or acquisition": "#MergersAndAcquisitions", "a CEO change": "#leadership", "1.01": "#deal", "1.03": "#bankruptcy",
             "4.02": "#restatement", "5.02": "#leadership", "2.01": "#MergersAndAcquisitions", "2.02": "#earnings", "1.05": "#cybersecurity",
             "3.01": "#delisting", "2.05": "#restructuring", "2.06": "#impairment"}


def event_tags(code, label):
    t = TOPIC_TAG.get(label) or TOPIC_TAG.get(code)
    return TAGS["event8k"][:2] + ([t] if t else []) + TAGS["event8k"][2:]


ABBR = re.compile(r"\b(?:Inc|Ltd|Corp|Co|LLC|L\.P|LP|No|Nos|U\.S|Mr|Ms|Dr|St|Jr|S\.A|N\.V|plc)\.$")


def first_sentence(quote, limit=170):
    """The quote's first sentence, abbreviations (Inc., Ltd., U.S.) not taken for its end, asides like (the “Company”)
    dropped, shortened at a word with … if long."""
    q = re.sub(r"\s*\((?:the\s+)?[“\"][^)]{1,40}[”\"]\)", "", (quote or "").strip())
    out, start = q, 0
    for m in re.finditer(r"[.!?](?=\s+[A-Z“\"])", q):
        if not ABBR.search(q[:m.end()]):
            out = q[:m.end()]
            break
    out = out.strip().rstrip(".")
    return out if len(out) <= limit else out[:limit].rsplit(" ", 1)[0].rstrip(",;") + " …"


def quote_replies(quote, head="What the filing says:"):
    """The filing's key sentences as one or two replies (each under 280 characters)."""
    q = (quote or "").strip()
    if not q:
        return []
    first = f"{head}\n“{q}”"
    if social.xlen(first) <= 280:
        return [first]
    cut = q[:240].rsplit(" ", 1)[0]
    rest = q[len(cut):].strip()
    rest = rest if social.xlen(rest) <= 270 else rest[:262].rsplit(" ", 1)[0] + " …"
    return [f"{head}\n“{cut} …", f"… {rest}”"]


# the items worth a post on their own, with a weight; BREAKING only for the first group
EVENT_ITEMS = {"1.03": 10, "4.02": 9, "5.01": 9, "2.01": 8, "1.05": 8, "1.01": 6, "5.02": 6, "2.06": 6, "3.01": 6, "2.05": 5,
               "8.01": 3, "7.01": 2}
BREAKING_ITEMS = {"1.03", "4.02", "5.01", "2.01", "1.05"}
DEAL = re.compile(r"(?i)\b(merger|acquire|acquisition|to be acquired|definitive agreement|tender offer|all-cash|per share in cash|"
                  r"buyback|repurchase program|share repurchase|spin-?off|strategic alternatives|chief executive officer|"
                  r"resign|terminated|bankruptcy|chapter 11|restatement|delist)")


def event_label(code, quote):
    """A plain name for what the 8-K reports, sharper than the item title when the text says what it is."""
    q = quote or ""
    if code in ("1.01", "2.01", "8.01", "7.01") and re.search(r"(?i)merger|to be acquired|acquire|acquisition|tender offer", q):
        return "a merger or acquisition"
    if re.search(r"(?i)repurchase|buyback", q):
        return "a share buyback"
    if code == "5.02" and re.search(r"(?i)chief executive officer|\bCEO\b", q):
        return "a CEO change"
    if code == "5.02" and re.search(r"(?i)chief financial officer|\bCFO\b", q):
        return "a CFO change"
    return events.ITEMS.get(code, "a current report")


def plan_event8k(site, rows, c, by_ticker, state_ok, today):
    """The most important 8-K filed in the last day by a company on the site: deals, CEO/CFO changes, bankruptcies,
    restatements, cyber incidents, impairments, delisting notices, buybacks. Earnings releases (2.02) have their own posts."""
    from . import scan
    by_cik = {}
    for e in rows:
        if e.get("ticker") and e.get("cik") and (e["cik"] not in by_cik or (e.get("filed") or "") > (by_cik[e["cik"]].get("filed") or "")):
            by_cik[e["cik"]] = e
    since = (today - dt.timedelta(days=1 if today.weekday() else 3)).isoformat()
    cands = []
    for page in range(3):
        try:
            entries = scan._parse_atom(sec.get(sec.current_feed_url("8-K", start=page * 100)))
        except (Exception, SystemExit) as err:
            print(f"event8k: EDGAR feed not read ({str(err)[:120]})")
            break
        for f in entries:
            e = by_cik.get(f["cik"])
            items = [x for x in (f.get("items") or "").split(",") if x]
            w = max([EVENT_ITEMS.get(x, 0) for x in items] or [0])
            if not e or not w or (f.get("filed") or "") < since or not state_ok("event8k", f["accn"], hours=24 * 30):
                continue
            cands.append((w * (1 + math.log10(max(1e8, e.get("revenue") or 1e8)) - 8), e, f, items))
        if len(entries) < 100:
            break
    cands.sort(key=lambda x: -x[0])
    print("::notice::event8k: " + (", ".join(f"{e['ticker']} {','.join(i)}" for _, e, _, i in cands[:8]) or "no material 8-K from a site company"))
    for score, e, f, items in cands[:6]:
        p = event_plan(site, e, {"accn": f["accn"], "form": f["form"], "filed": f["filed"], "accepted": f.get("updated") or "", "items": items})
        if p:
            return p
    return None


def event_plan(site, e, sub, require_deal=True, fresh=True):
    """The post for one 8-K of company e (sub: accn, form, filed, accepted, items[, primary]), or None."""
    if not sub.get("primary"):
        try:
            idx = sec.get_json(sec.filing_index_url(e["cik"], f["accn"]))
            names = [i["name"] for i in idx.get("directory", {}).get("item", []) if re.search(r"\.html?$", i["name"], re.I)]
            sub["primary"] = next((n for n in names if not re.search(r"(?i)ex[-_]?\d", n)), names[0] if names else "")
        except (Exception, SystemExit) as err:
            print(f"event8k: {e['ticker']} filing index not read ({str(err)[:100]})")
            return None
    if True:
        ev = events.describe(e["cik"], sub)
        if require_deal and ev["code"] in ("8.01", "7.01") and not DEAL.search(ev["quote"] or ""):
            return None                                # "other events" only when the text names a deal, buyback or the like
        cj, fq = figures(site, e)
        if not fq:
            return None
        label = event_label(ev["code"], ev["quote"])
        # BREAKING: any material item (weight 6+: agreements, officer changes, impairments, delisting notices, ...) filed in
        # the last two days; an older filing is dated instead, never called breaking
        breaking = fresh and (ev["code"] in BREAKING_ITEMS or EVENT_ITEMS.get(ev["code"], 0) >= 6
                              or label in ("a merger or acquisition", "a CEO change"))
        when = f"{ev['filed']}" + (f" {ev['accepted'][11:16]} ET" if len(ev.get("accepted") or "") >= 16 else "")
        filed_on = dt.date.fromisoformat(ev["filed"])
        filed_txt = f"{filed_on:%b} {filed_on.day}"
        task = (f"8-K CURRENT REPORT filed {when} by ${e['ticker']} ({display(e)}): Item {ev['code']} — {ev['label']}"
                + (f" ({label})" if label != ev["label"] else "") + f".\nWhat the filing says (quote; the only facts you may use about the event):\n"
                f"“{ev['quote'] or '(text not read; name the item only)'}”\n\nLatest filing figures (context, at most one):\n"
                f"{tweet.headline_lines(cj, fq, e['ticker'])}\n\n"
                + ("Start the post with “BREAKING:” — a material event filed in the last two days. " if breaking
                   else "Start with “JUST FILED:”. " if fresh else f"Start with “8-K ({filed_txt}):” — it was filed on {filed_txt}, not today. ")
                + "Then say concretely what happened, using the quote: WHO did WHAT with WHOM (name the counterparty), the dollar "
                  "amounts, share counts and dates the quote gives, and the filing date. No facts beyond the quote; finish every "
                  "sentence; never predict the stock's reaction; end with one short question to the audience.")
        lead = "BREAKING: " if breaking else "JUST FILED: " if fresh else ""
        head = f"{lead}${e['ticker']} 8-K filed {filed_txt} — {label}"
        room = 255 - sum(len(t) + 1 for t in event_tags(ev["code"], label)) - social.xlen(head) - len(": “” How do you read it?") - 2
        short = first_sentence(ev["quote"], limit=max(0, room))
        fb = f"{head}: “{short}{'' if short.endswith('…') else '.'}” How do you read it?" if len(short) >= 40 else f"{head}. How do you read it?"
        return {"kind": "event8k", "task": task, "cashtags": [e["ticker"]], "items": [(e, cj, fq)], "event": ev,
                "event_key": f"event8k:{sub['accn']}", "fallback": fb, "tags": event_tags(ev["code"], label),
                "thread": quote_replies(ev["quote"])}


def plan_filing8k(site, rows, target, today):
    """Owner tools: a post about one company's 8-K — the accession given (target['ref']), or else its most material 8-K of
    the last 45 days (earnings releases included)."""
    cik = int(target["cik"])
    e = next((r for r in rows if r.get("cik") == cik and r.get("ticker")), None)
    if not e:
        print(f"filing8k: CIK {cik} is not on the site")
        return None
    want = re.sub(r"[^0-9-]", "", str(target.get("ref") or ""))
    if want and "-" not in want and len(want) == 18:
        want = f"{want[:10]}-{want[10:12]}-{want[12:]}"
    try:
        fs = events.recent_8ks(cik, (today - dt.timedelta(days=400 if want else 45)).isoformat())
    except (Exception, SystemExit) as err:
        print(f"filing8k: 8-Ks of {cik} not listed ({str(err)[:120]})")
        return None
    if want:
        fs = [f for f in fs if f["accn"] == want]
        if not fs:
            print(f"filing8k: accession {want} is not among {e['ticker']}'s 8-Ks")
            return None
    if not fs:
        print(f"filing8k: {e['ticker']} filed no 8-K in 45 days")
        return None
    f = min(fs, key=lambda f: min([events.PRIORITY.index(x) for x in f["items"] if x in events.PRIORITY] or [99]))
    fresh = f["filed"] >= (today - dt.timedelta(days=2)).isoformat()
    return event_plan(site, e, dict(f), require_deal=False, fresh=fresh)


def display(e):
    return social.display_name(e.get("name") or "")


# ------------------------------------------------------------------ options and relative strength (from the Disclosures hub)
def plan_ivmove(site, rows, c, by_ticker, state_ok, today):
    """The biggest one-day jump in 30-day implied volatility among the companies on the site (CBOE delayed quotes)."""
    try:
        d = hub_json(site, "options.json")
    except Exception as err:
        print(f"ivmove: no option data ({str(err)[:100]})")
        return None
    cands = [r for r in d.get("rows", []) if r.get("iv30_chg") is not None and (r.get("iv30") or 0) >= 15
             and r["ticker"].replace("-", ".") in by_ticker and state_ok("ivmove", r["ticker"], hours=24 * 5)]
    cands.sort(key=lambda r: -abs(r["iv30_chg"]))
    if not cands or abs(cands[0]["iv30_chg"]) < 4:
        print("ivmove: no implied-volatility move of 4 points or more")
        return None
    r = cands[0]
    tk = r["ticker"].replace("-", ".")
    e = by_ticker[tk]
    cj, fq = figures(site, e)
    lvl = lambda v: f"${v:,.0f}" if v and v >= 100 else (f"${v:,.2f}" if v else "—")
    task = (f"OPTIONS (CBOE delayed quotes, end of day {str(d.get('generated_at') or '')[:10]}): ${tk} 30-day implied volatility "
            f"{r['iv30']:.1f}% ({r['iv30_chg']:+.1f} points on the day). Stock {lvl(r.get('spot'))}. Put/call open interest "
            f"{r.get('pc_oi') or '—'}. Largest call open interest at {lvl(r.get('call_wall'))}, largest put open interest at "
            f"{lvl(r.get('put_wall'))}; max pain {lvl(r.get('max_pain'))} for {r.get('max_pain_exp') or 'the next monthly expiry'}.\n\n"
            + (f"Latest filing figures (context, at most one):\n{tweet.headline_lines(cj, fq, tk)}\n\n" if fq else "")
            + "Say what the options market did in plain words (implied volatility = the move option prices expect, not a direction). "
              "Never say why. Ask the audience what they think is being priced in.")
    fb = (f"${tk} options: 30-day implied volatility {r['iv30']:.1f}%, {r['iv30_chg']:+.1f} points today. Put/call open interest "
          f"{r.get('pc_oi') or '—'}. What is the market pricing in?")
    return {"kind": "ivmove", "task": task, "cashtags": [tk], "items": [(e, cj, fq)] if fq else [], "fallback": fb}


def plan_opt13f(site, rows, c, by_ticker, state_ok, today):
    """The biggest change in disclosed put or call positions (13F) on a company on the site, once per quarter and name."""
    try:
        d = hub_json(site, "options13f.json")
    except Exception as err:
        print(f"opt13f: no 13F option data ({str(err)[:100]})")
        return None
    qtr = d.get("quarter") or ""
    cands = []
    for r in d.get("rows", []):
        tk = (r.get("ticker") or "").replace("-", ".")
        if r.get("fund") or tk not in by_ticker or not state_ok("opt13f", f"{qtr}:{tk}", hours=24 * 120):
            continue
        for side, key in (("puts", "d_put_usd"), ("calls", "d_call_usd")):
            if abs(r.get(key) or 0) >= 1e9:
                cands.append((abs(r[key]), side, key, tk, r))
    if not cands:
        print("opt13f: no disclosed option change of $1B or more on a site company")
        return None
    _, side, key, tk, r = max(cands)
    e = by_ticker[tk]
    cj, fq = figures(site, e)
    top = "; ".join(f"{x['manager'].title()} {'puts' if x['pc'] == 'PUT' else 'calls'} {money(x['usd'])}" for x in (r.get("top") or [])[:3])
    task = (f"13F FILINGS for the quarter ended {qtr} (filed up to 45 days later): managers disclosed {money(r['put_usd'])} of ${tk} puts "
            f"({r['put_mgrs']} managers) and {money(r['call_usd'])} of calls ({r['call_mgrs']} managers), valued at the underlying shares. "
            f"Since each holder's previous quarter: puts {'+' if r['d_put_usd'] >= 0 else '−'}{money(abs(r['d_put_usd']))}, calls "
            f"{'+' if r['d_call_usd'] >= 0 else '−'}{money(abs(r['d_call_usd']))}. Largest holders: {top}.\n\n"
            "Rules: 13F shows long options only and many holders are market makers hedging, so a put is NOT necessarily a bet against "
            "the stock — say so in a few words. Never say the stock will fall or rise. Ask what the audience reads into it.")
    fb = (f"${tk}: managers' disclosed {side} {'rose' if r[key] >= 0 else 'fell'} {money(abs(r[key]))} in the {qtr[:7]} 13Fs — now "
          f"{money(r['put_usd'])} puts vs {money(r['call_usd'])} calls (many are hedges). Read anything into it?")
    return {"kind": "opt13f", "task": task, "cashtags": [tk], "items": [(e, cj, fq)] if fq else [], "fallback": fb,
            "event_key": f"opt13f:{qtr}:{tk}"}


def plan_rsleaders(site, rows, c, by_ticker, state_ok, today):
    """New relative-strength leaders: companies whose RS rating (1–99) climbed into the 90s over the last three months."""
    try:
        d = hub_json(site, "rotation-monthly.json")
    except Exception as err:
        print(f"rsleaders: no relative-strength data ({str(err)[:100]})")
        return None
    f = d.get("fields") or []
    if "rs" not in f:
        return None
    i = f.index("rs")
    leaders = []
    for tk, m in (d.get("companies") or {}).items():
        t = tk.replace("-", ".")
        if t not in by_ticker or len(m) < 4 or m[-1][i] is None or m[-4][i] is None:
            continue
        if m[-1][i] >= 90 and m[-1][i] - m[-4][i] >= 20:
            leaders.append((m[-1][i] - m[-4][i], m[-1][i], m[-4][i], t))
    leaders.sort(reverse=True)
    picks = leaders[:5]
    if len(picks) < 3:
        print("rsleaders: fewer than three new leaders")
        return None
    month = (d.get("months") or [""])[-1]
    lines = [f"- ${t}: RS rating {now} (was {then} three months earlier) · {one_liner(by_ticker[t])}" for _, now, then, t in picks]
    items = []
    for _, _, _, t in picks[:4]:
        cj, fq = figures(site, by_ticker[t])
        if fq:
            items.append((by_ticker[t], cj, fq))
    task = (f"NEW RELATIVE-STRENGTH LEADERS at the end of {month} (RS rating 1–99: 3/6/9/12-month returns ranked against ~600 large "
            "companies; it describes past price strength, not the future):\n" + "\n".join(lines)
            + "\n\nList them as cashtags with their rating jump, name the biggest climber in a few words, ask which one the audience "
              "thinks holds up.")
    fb = ("New relative-strength leaders: " + ", ".join(f"${t} {then}→{now}" for _, now, then, t in picks)
          + " (RS rating, 3 months). Which one holds up?")
    return {"kind": "rsleaders", "task": task, "cashtags": [t for *_, t in picks], "items": items, "fallback": fb}


# ------------------------------------------------------------------ main
def make(kinds, site, site_url, media, assets, dry_run=False, force=False, plan_only=False, target=None, draft=False):
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
        if kind in ("fund13f", "event8k"):  # one post per filing (event8k: at most one per run, any number a day)
            return True
        if kind in MOVER_KINDS:            # movers: a daily cap and a minimum gap instead of once a day per format
            if force:
                return True
            if len(log) >= c["movers"]["max_per_day"]:
                print(f"{kind}: {len(log)} mover posts already today (max_per_day)")
                return False
            return not log or log[-1][0] < (now - dt.timedelta(minutes=c["movers"]["min_gap_minutes"])).isoformat()
        hours = (c.get("kind_cooldown") or {}).get(kind, c["kind_cooldown_hours"])
        return force or (state.get(f"kind:{kind}") or "") < (now - dt.timedelta(hours=hours)).isoformat()

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
             "weekly": lambda: plan_weekly(site, rows, c, by_ticker, state, today),
             "event8k": lambda: plan_event8k(site, rows, c, by_ticker, state_ok, today),
             "ivmove": lambda: plan_ivmove(site, rows, c, by_ticker, state_ok, today),
             "opt13f": lambda: plan_opt13f(site, rows, c, by_ticker, state_ok, today),
             "rsleaders": lambda: plan_rsleaders(site, rows, c, by_ticker, state_ok, today),
             "filing8k": lambda: plan_filing8k(site, rows, target or {}, today),
             "fund13f_for": lambda: plan_fund13f_for(site, rows, by_ticker, target or {})}.get(kind, lambda: None)()
        if p:
            plans.append(p)
        else:
            print(f"{kind}: nothing to post")

    if plan_only:                          # the workflow's cheap first pass: is there anything to post at all?
        for p in plans:
            print(f"planned: {p['kind']} " + " ".join("$" + t for t in p["cashtags"]))
        return [p["kind"] for p in plans]
    general = [t for t in c["hashtags"] if t]
    made = []
    for p in plans:
        tags = p.get("tags") or TAGS.get(p["kind"]) or general
        try:
            post = write(p["kind"], p["task"], p["cashtags"], tags, polish=c.get("polish", True), allowed=p.get("allowed"))
        except Exception as err:
            post = None
            if p.get("fallback"):                  # the model is down: a plain rule-based post with the same facts
                try:
                    post = clean(p["fallback"], p["cashtags"], tags, allowed=p.get("allowed"))
                    print(f"::warning::{p['kind']}: model unavailable, rule-based post used ({str(err)[:160]})")
                except ValueError as why:
                    print(f"::warning::{p['kind']}: rule-based post not usable ({why})")
            if not post:
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
            print(f"::notice title=dry run {p['kind']}::{post}")
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
                        "posts": [post] + list(p.get("thread") or []) + [x for x in (filing, reply) if x], "written_by": "model", "images": images,
                        **({"draft": True} if draft else {})})
        json.dump(pending, open(pend_path, "w", encoding="utf-8"), ensure_ascii=False)
        stamp = now.isoformat()
        state[f"kind:{p['kind']}"] = stamp
        for t in p["cashtags"]:
            state[f"{p['kind']}:{t}"] = stamp
        if p.get("fund_key"):
            state[p["fund_key"]] = stamp
        if p.get("event_key"):
            state[p["event_key"]] = stamp
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
