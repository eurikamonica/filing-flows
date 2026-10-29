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
  reddit_hot       Reddit's hottest stock right now (the hub's half-hourly scan) as a cashtag, against what insiders, 13F
                   managers and officials are doing in it (its smart-money score)
  smart_buys       the stocks the traders with the best records are net buying now (smart-money score −100 … +100)
  smart_record     one official, insider or 13F manager with a strong, tested record and a trade in the last month
  all_agree        a stock every group trading it (13F managers, active ETFs, insiders, officials) net-bought this quarter
  qtd_flows        the calendar quarter so far: insiders' and officials' biggest net purchases, the early 13F filers' top add
  pt_upside        "Wall Street rates both $A and $B a Hold — but one has 3.6x the upside" (analysts' price targets)
  versus           "$A or $B — which would you rather have?" for two names people are watching
  drawdown         popular names far below their 52-week highs, one "$RKLB $150 → $50" line each
  setup            one trending stock going into the next session, in bullets (range, YTD, short interest, 8-K, analysts, Polymarket)
  lows52 / highs52 the best-known names that hit new 52-week lows / highs in the last session
  near_lows        profitable large companies trading near their 52-week lows, with how far they are off the high
  records          new all-time highs (or lows) in the last session
  polymarket       Polymarket's odds that this week's reporters beat the EPS line
The Reddit kinds (reddit_question, reddit_list, reddit_hot) use the trending tickers only to pick names: the posts are
normal stock posts with cashtags and never talk about Reddit.
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

from . import context as CTX, events, hashtags as H, notify, quotes as Q, reddit, sec, social, tweet, xkinds as X

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
        text = open(GUIDE, encoding="utf-8").read()
    except FileNotFoundError:
        text = "Write one neutral, factual engagement post for X under 255 characters, ending with the given hashtags."
    return text + X.guide_text()                      # the formats feature modules register (pipeline/posts_*.py)


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
def clean(post, cashtags, tags, limit=255, allowed=None, must=None, forbid=None, lines=False):
    """must: (regex, what to say) — something the reader needs to understand the numbers, e.g. that 6→97 is an RS rating;
    forbid: (regex, why) — wording the post may not use, e.g. a cause for a price move; lines: keep the line breaks of a
    list post ("$RKLB $150 → $50" one per line), at most one blank line in a row."""
    if lines:
        post = "\n".join(x.strip() for x in post.strip().strip('"“”').splitlines())
        post = re.sub(r"\n{3,}", "\n\n", post).strip()
    else:
        post = re.sub(r"\s*\n+\s*", " ", post.strip().strip('"“”')).strip()
    if must and not re.search(must[0], re.sub(r"#\w+", "", post), re.I):
        raise ValueError(must[1])
    if forbid and re.search(forbid[0], re.sub(r"#\w+", "", post), re.I):
        raise ValueError(forbid[1])
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
    post = tweet.fit_tags(post, social.xlen, limit).rstrip()    # too long only because of the hashtags: fewer hashtags
    if social.xlen(post) > limit:
        raise ValueError(f"too long ({social.xlen(post)})")
    return post


def messages(kind, task, cashtags, tags, allowed=None):
    """The chat messages for one engagement post (the API models, the local fallback model and its training examples)."""
    others = [t for t in (allowed or []) if t not in cashtags]
    return [{"role": "system", "content": guide()},
            {"role": "user", "content": f"FORMAT: {kind}\n\n{task}\n\nCashtags that must appear: " + " ".join(f"${t}" for t in cashtags)
             + (("\nOther cashtags you may use (no others): " + " ".join(f"${t}" for t in others)) if others else "")
             + "\nHashtags to end with, in this order: " + " ".join(tags) + "\n\nWrite the post now."}]


def write(kind, task, cashtags, tags, polish=True, allowed=None, must=None, forbid=None, lines=False):
    msgs = messages(kind, task, cashtags, tags, allowed)
    draft = tweet.chat(msgs)
    if polish:
        msgs += [{"role": "assistant", "content": draft},
                 {"role": "user", "content": "Polish pass: keep every number, cashtag, option and hashtag exactly; sharper, more specific "
                                             "opening; cut filler; under 250 characters" + ("; keep the line breaks and one item per line" if lines else "")
                                             + ". Output only the polished post."}]
        draft = tweet.chat(msgs)
    try:
        return clean(draft, cashtags, tags, allowed=allowed, must=must, forbid=forbid, lines=lines)
    except ValueError as why:
        msgs += [{"role": "assistant", "content": draft},
                 {"role": "user", "content": f"Rewrite: {why}. Under 240 characters, every required cashtag present, ending with the hashtags."}]
        return clean(tweet.chat(msgs), cashtags, tags, allowed=allowed, must=must, forbid=forbid, lines=lines)


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


NO_FORUM = (r"\breddit\b|subreddit|wallstreetbets|\bWSB\b|r/\w+", "do not mention Reddit or any forum: just the stocks, their cashtags and the facts")


def plan_reddit_question(site, rows, c, trends, by_ticker, state_ok):
    """The company trending hardest on the investing subreddits — written as a normal post about the stock (its setup in
    bullets when the hub has its prices, else one fact and a 2–3 option question). Reddit only picks the name."""
    today = dt.datetime.now(dt.timezone.utc).date()
    for a in trends:
        if not state_ok("reddit_question", a["ticker"]):
            continue
        p = plan_setup(site, rows, c, by_ticker, state_ok, today, pick=a["ticker"], kind="reddit_question")
        if p:
            p["forbid"] = NO_FORUM
            return p
        e = by_ticker[a["ticker"]]
        cj, q = figures(site, e)
        if not q:
            continue
        task = (f"A stock many investors are watching right now: ${a['ticker']}. Headline figures from its latest filing:\n"
                + tweet.headline_lines(cj, q, a["ticker"]) + "\n\nOne striking fact, then a 2–3 option question. Do not mention where it is discussed.")
        return {"kind": "reddit_question", "task": task, "cashtags": [a["ticker"]], "items": [(e, cj, q)], "forbid": NO_FORUM}
    return None


def plan_reddit_list(site, rows, c, trends, by_ticker, state_ok):
    """The 3–5 most-discussed companies as a cashtag poll with one fact each — no forum talk."""
    picks = [a for a in trends if state_ok("reddit_list", a["ticker"])][:4]
    if len(picks) < 3:
        return None
    lines, items = [], []
    for a in picks:
        e = by_ticker[a["ticker"]]
        lines.append(f"- {one_liner(e)}")
        if len(items) < 4:
            cj, q = figures(site, e)
            if q:
                items.append((e, cj, q))
    tks = [a["ticker"] for a in picks]
    task = (f"{len(picks)} STOCKS INVESTORS ARE WATCHING THIS WEEK, with their latest filing:\n" + "\n".join(lines)
            + "\n\nWrite a cashtag poll: one short line per stock with one number, then “which one are you watching?”. Line breaks. "
              "Do not mention where they are discussed.")
    def poll_line(e):
        t, rev, yoy = e["ticker"], e.get("rev"), e.get("yoy")
        return f"${t}: revenue {rev}, {yoy:+.0f}% Y/Y" if rev and isinstance(yoy, (int, float)) else f"${t}: revenue {rev}" if rev else f"${t}"
    facts = "\n".join(poll_line(by_ticker[t]) for t in tks)
    plain = "\n".join(f"${t}" for t in tks)
    fbs = [f"Stocks investors are watching this week:\n\n{facts}\n\nWhich one are you watching?",
           f"Pick one for the rest of the year:\n\n{plain}\n\nWhich one, and why?",
           f"The most-watched names this week:\n\n{facts}\n\nWhich one would you own?"]
    fbs = [f for f in fbs if social.xlen(f) <= 250] or [fbs[1]]
    return {"kind": "reddit_list", "task": task, "cashtags": tks, "items": items, "forbid": NO_FORUM, "lines": True, "fallback": fbs[0],
            "fallbacks": fbs}


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
        # what else is known today (the hub's 8-Ks, releases, 13D / Form 4 / 144, short interest, options, the market,
        # headlines): context the post may cite, never a cause (pipeline/context.py)
        try:
            known, _facts = CTX.known(lambda n: hub_json(site, n), e, quote=q, skip_8k=bool(ev))
        except Exception as err:
            known = ""
            print(f"::warning::mover context not built ({str(err)[:120]})")
        task = (f"PRICE MOVE (delayed quote, {stamp}): {quote_line(e['ticker'], q, e)}.{news}{known}\n\n"
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
                "event": ev if kind != "peers" else None, "fallback": fb,
                "forbid": (CTX.CAUSAL.pattern, "do not give a cause for the move (no “because”, “due to”, “on news of”, “driven by”)")}
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
_HUB = {}


def hub_bytes(site, rel):
    """A binary file the Disclosures hub publishes (rel under disclosures/data/), or None when it is not there."""
    try:
        if site.remote:
            import requests
            r = requests.get(site.src.rstrip("/") + "/disclosures/data/" + rel, timeout=60)
            return r.content if r.status_code == 200 and r.content else None
        with open(os.path.join(site.src, "disclosures", "data", rel), "rb") as f:
            return f.read()
    except Exception as err:                    # noqa: BLE001 — the post goes out without the picture
        print(f"hub image {rel} not read ({str(err)[:100]})")
        return None


def hub_json(site, name):
    """A file of the Disclosures hub's market data, from the published site or the built folder (read once per run; a
    file that is not there is not asked for again)."""
    key = (site.src, name)
    if key not in _HUB:
        try:
            _HUB[key] = _hub_json(site, name)
        except Exception as err:
            _HUB[key] = err
    if isinstance(_HUB[key], Exception):
        raise _HUB[key]
    return _HUB[key]


def hub_cached(site, rel):
    """hub_file, read once per run (the training corpus plans dozens of posts from the same files)."""
    key = (site.src, "file:" + rel)
    if key not in _HUB:
        try:
            _HUB[key] = hub_file(site, rel)
        except Exception as err:
            _HUB[key] = err
    if isinstance(_HUB[key], Exception):
        raise _HUB[key]
    return _HUB[key]


def _hub_json(site, name):
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
    return insider_plan(t, tk, e, cj, fq, clusters.get(tk), today)


def insider_plan(t, tk, e, cj, fq, cl, today):
    """The post plan for one Form 4 trade (t: a row of the hub's insiders.json; cl: its cluster summary or None). A sale
    (code S) is written as "sold"; without the company on the site (cj/fq None) the post has no chart and no other figures."""
    sale = t.get("code") == "S"
    verb = "sold" if sale else "bought"
    after = f"; holds {t['after']:,.0f} shares after the trade" if t.get("after") else ""
    filed = t.get("filed")
    fresh = bool(filed) and filed >= (today - dt.timedelta(days=2)).isoformat()
    what = f"${tk}" if tk else social.display_name(t.get("issuer") or "the company")
    at = f" at ${t['price']:,.2f}" if t.get("price") is not None else ""
    plan = (" The sale was under a pre-arranged 10b5-1 trading plan." if sale and t.get("plan_10b5_1")
            else " This was NOT under a 10b5-1 plan." if t.get("plan_10b5_1") is False else "")
    figs = (f"\n\nLatest filing figures (the only other numbers you may use):\n{tweet.headline_lines(cj, fq, tk)}" if fq
            else "\n\nNo other figures: use only the numbers above. No chart is attached; do not mention one.")
    task = (f"FORM 4{f' filed {filed}' if filed else ' (filed within two business days of the trade)'}: {t['insider']} ({t.get('title') or t['role']}) {verb} "
            f"{t['shares']:,.0f} shares of {what}{at} on {t['date']} — {money(t['value'])} in the open market{after}."
            + (" Start the post with “JUST FILED:”." if fresh else "")
            + f" Say who {verb}, how many shares, at what price, the trade date and the filing date."
            + plan
            + (" Use the word “sold”, never “sell”. Insiders sell for many reasons (taxes, diversification, planned sales): state the "
               "facts and imply nothing." if sale else "")
            + (f"\nCluster: {cl['buyers30']} insiders bought ${tk} within 30 days ({', '.join(cl['buyers'][:4])})." if cl and not sale else "")
            + figs
            + "\n\nSay what the insider did and when; never say what it means for the stock. Ask the audience how they read it.")
    who = t.get('title') if t.get('title') and len(t['title']) <= 24 else t['role']
    fb = (("JUST FILED: " if fresh else "") + f"{what} {who} {t['insider'].title()} {verb} {t['shares']:,.0f} shares ({money(t['value'])}){at} "
          f"on {t['date']}" + (f", Form 4 filed {filed}." if filed else " (Form 4).")
          + (" Under a 10b5-1 plan." if sale and t.get("plan_10b5_1") else "")
          + (f" {cl['buyers30']} insiders bought in 30 days." if cl and not sale else "") + " How do you read it?")
    return {"kind": "insider", "task": task, "cashtags": [tk] if tk else [], "items": [(e, cj, fq)] if fq else [],
            "insider_url": t.get("url"), "fallback": fb,
            "tags": H.pick("insider_sale" if sale else "insider", e, key=f"insider:{tk or t.get('issuer_cik')}:{t.get('date')}")}


# ------------------------------------------------------------------ one row of the Disclosures hub (Owner: ✦ X on a row)
# The hub's tables (Insider trades, Officials' trades) send the row's own key as the request's ref (a JSON list); the
# row is looked up again in the published data here, so every figure in the post comes from the data, not the browser.
WHOSE = {"SP": "spouse", "DC": "dependent child"}


def _ref(target):
    try:
        v = json.loads(target.get("ref") or "")
    except ValueError:
        v = None
    if not isinstance(v, list):
        raise ValueError("the request does not name a row of the table")
    return v


def _same(a, b):
    if a in (None, "") or b in (None, ""):
        return a in (None, "") and b in (None, "")
    try:
        return abs(float(a) - float(b)) < 1e-6
    except (TypeError, ValueError):
        return str(a) == str(b)


def site_company(rows, by_ticker, cik=None, ticker=None):
    """The site's index row of a company (by CIK, else by ticker), or None when it has no charts on the site."""
    try:
        hit = next((r for r in rows if cik and int(r.get("cik") or 0) == int(cik) and r.get("end")), None)
    except (TypeError, ValueError):
        hit = None
    return hit or (by_ticker.get(ticker) if ticker else None)


def plan_insider_for(site, rows, by_ticker, target, today):
    """Owner: a post about one row of the hub's Insider trades table (ref: [accession, date, code, shares, price])."""
    try:
        accn, day, code, shares, price = (_ref(target) + [None] * 5)[:5]
        d = hub_json(site, "insiders.json")
    except Exception as err:
        print(f"insider_for: {str(err)[:200]}")
        return None
    t = next((t for t in d.get("latest", []) if t.get("accession") == accn and t.get("date") == day and t.get("code") == code
              and _same(t.get("shares"), shares) and _same(t.get("price"), price)), None)
    if not t:
        print(f"insider_for: the trade {accn} of {day} is no longer in the hub's insiders.json")
        return None
    tk = (t.get("ticker") or "").upper().replace("-", ".")
    e = site_company(rows, by_ticker, t.get("issuer_cik"), tk)
    cj, fq = figures(site, e) if e else (None, None)
    cl = next((a for a in d.get("summary", []) if a.get("cluster") and (a.get("ticker") or "").upper().replace("-", ".") == tk), None)
    p = insider_plan(t, tk, e if fq else None, cj, fq, cl, today)
    p["manual"] = True
    return p


def amount_range(lo, hi):
    """An official's disclosed range as filed: "$1,001–$15,000", "over $50,000,000" (the House's open top range is
    stored as its first dollar, 50,000,001)."""
    if lo is None and hi is None:
        return "an undisclosed amount"
    if hi is None:
        return f"over ${lo - 1 if lo % 1000 == 1 else lo:,.0f}"
    return f"${lo:,.0f}–${hi:,.0f}" if lo is not None else f"up to ${hi:,.0f}"


def official_plan(t, e, cj, fq, today):
    """The post plan for one official's reported transaction (a row of the hub's officials-trades.json)."""
    listed = t.get("ticker_status") == "listed" and t.get("name_check") != "check"     # a doubtful ticker: no cashtag
    tk = (t.get("ticker_canon") or t.get("ticker") or "").upper().replace("-", ".") if listed else ""
    name = social.display_name(t.get("listed_name") or "") or re.sub(r"\s*\[[A-Z]{2}\]\s*$", "", t.get("asset_raw") or "the asset")[-80:]
    what = (f"${tk}" if tk else name) + (" options" if t.get("asset_type") == "OP" else "")
    verb = {"purchase": "bought", "sale": "sold", "partial sale": "sold part of a holding in", "exchange": "exchanged"}.get(t.get("type"), t.get("type") or "traded")
    own = t.get("owner") or ""
    who = f"{t['person']}'s {WHOSE[own]}" if own in WHOSE else f"{t['person']} (joint account)" if own == "JT" else t["person"]
    amt = amount_range(t.get("amount_min"), t.get("amount_max"))
    jur = t.get("jurisdiction") or ""
    house = jur in ("US House", "US Senate")             # Congress: periodic transaction reports under the STOCK Act
    src = f"a {jur} periodic transaction report" if house else f"a {jur or 'public'} disclosure"
    filed, day = t.get("filed_date") or t.get("notified") or "", t.get("date") or ""
    try:
        lag = (dt.date.fromisoformat(filed[:10]) - dt.date.fromisoformat(day[:10])).days
    except ValueError:
        lag = None
    figs = (f"\n\nLatest filing figures of the company (the only other numbers you may use):\n{tweet.headline_lines(cj, fq, tk)}" if fq
            else "\n\nNo other figures: use only the numbers above. No chart is attached; do not mention one.")
    task = (f"OFFICIAL'S TRADE, from {src} filed {filed}: {who} {verb} {what} worth {amt} on {day}"
            + (f" — disclosed {lag} days after the trade" if lag is not None and lag >= 0 else "") + ". "
            "Officials report a dollar range, not the amount or the price: give the range exactly as written. Say who, what, the "
            "range, the trade date and the filing date. Never say or imply the trade was improper, informed or a signal for the "
            "stock; use “sold” or “bought”, never “sell” or “buy”. End with one short question to the audience."
            + figs)
    lead = ("Senate disclosure" if jur == "US Senate" else "House disclosure") if house else f"{jur or 'Official'} disclosure"
    fb = f"{lead}: {who} {verb} {what} ({amt}) on {day}, reported {filed}. How do you read it?"
    if t.get("read") == "electronic":                    # a Senate eFD report: an HTML table, no pages
        reply = f"Source: {src[2:]} (Senate eFD), filed {filed}. Not investment advice. {t.get('source_url') or ''}".strip()
    else:
        page = t.get("page") or 1
        url = (t.get("source_url") or "") + (f"#page={page}" if t.get("source_url") else "")
        reply = (f"Source: {src[2:] if src.startswith('a ') else src} {t.get('report_id') or ''}, filed {filed}, page {page}"
                 + ("; read automatically from the PDF" if t.get("read") != "reviewed" else "") + f". Not investment advice. {url}").strip()
    return {"kind": "official", "task": task, "cashtags": [tk] if tk else [], "items": [(e, cj, fq)] if fq else [],
            "source_reply": reply, "fallback": fb, "manual": True,
            "tags": H.pick(("senate" if jur == "US Senate" else "congress") if house else "officials", e,
                           key=f"official:{t.get('report_id')}:{day}:{tk}")}


def plan_official_for(site, rows, by_ticker, target, today):
    """Owner: a post about one row of the hub's Officials' trades table
    (ref: [report_id, date, ticker, type, amount_min, amount_max, owner])."""
    try:
        rid, day, tick, typ, lo, hi, own = (_ref(target) + [None] * 7)[:7]
        d = hub_json(site, "officials-trades.json")
    except Exception as err:
        print(f"official_for: {str(err)[:200]}")
        return None
    t = next((t for t in d.get("trades", []) if t.get("report_id") == rid and t.get("date") == day and (t.get("ticker") or "") == (tick or "")
              and t.get("type") == typ and _same(t.get("amount_min"), lo) and _same(t.get("amount_max"), hi)
              and (t.get("owner") or "") == (own or "")), None)
    if not t:
        print(f"official_for: that transaction of report {rid} is no longer in the hub's officials-trades.json")
        return None
    listed = t.get("ticker_status") == "listed" and t.get("name_check") != "check"
    tk = (t.get("ticker_canon") or t.get("ticker") or "").upper().replace("-", ".") if listed else ""
    e = site_company(rows, by_ticker, None, tk) if tk else None
    cj, fq = figures(site, e) if e else (None, None)
    return official_plan(t, e if fq else None, cj, fq, today)


# ------------------------------------------------------------------ 13D / 13G, Form 144, short interest (hub rows)
def shares_txt(n):
    """12,927,442 → "12.9M"; 40,000 → "40,000"."""
    if n is None:
        return "an undisclosed number of"
    return f"{n / 1e9:.2f}B" if n >= 1e9 else f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n:,.0f}"


def _day(iso):
    """'2026-10-16' → 'Oct 16' (the year when it is not this one is kept by the caller's text)."""
    try:
        d = dt.date.fromisoformat(iso[:10])
        return f"{d:%b} {d.day}"
    except (TypeError, ValueError):
        return iso or ""


def _what(tk, name):
    return f"${tk}" if tk else social.display_name(name or "the company")


def _figs(fq, cj, tk):
    return (f"\n\nLatest filing figures of the company (the only other numbers you may use):\n{tweet.headline_lines(cj, fq, tk)}" if fq
            else "\n\nNo other figures: use only the numbers above. No chart is attached; do not mention one.")


def holder_name(r):
    """The largest reporting person when the filing spells the name properly, else the filer (EDGAR's upper case)."""
    if r.get("holder"):                                  # the hub's choice (app/ownership.py holder_of), in reading order
        return social.display_name(r["holder"])
    p = (r.get("person") or "").strip()
    return p if p and p != p.upper() else social.display_name(r.get("filer") or p or "A holder")


def stake_plan(r, tk, e, cj, fq, today):
    """The post plan for one Schedule 13D / 13G (a row of the hub's stakes.json)."""
    form, d13 = r.get("form") or "13D", (r.get("form") or "").startswith("13D")
    who, what = holder_name(r), _what(tk, r.get("issuer"))
    pct = r.get("percent")
    stake = f"{pct:g}% of {what}" if pct is not None else f"a stake in {what}"
    group = f" (one of {r['persons']} reporting persons filing together; the percent is the largest single holding)" if (r.get("persons") or 1) > 1 else ""
    below = r.get("label") == "below 5%"
    change = change_fb = ""
    if r.get("prev_percent") is not None and r.get("change") is not None:
        way = 'up' if r['change'] > 0 else 'down' if r['change'] < 0 else 'unchanged'
        change = f", {way} from {r['prev_percent']:g}% in its previous filing ({r.get('prev_filed') or 'on file'})"
        change_fb = f", {way} from {r['prev_percent']:g}%" + (f" ({_day(r['prev_filed'])})" if r.get("prev_filed") else "")
    kind = ("a Schedule 13D: the holder may seek to influence the company" if d13
            else f"a Schedule 13G: a passive holder{' (' + r['rule'] + ')' if r.get('rule') else ''}")
    filed = r.get("filed") or ""
    fresh = filed >= (today - dt.timedelta(days=2)).isoformat()
    purpose = r.get("purpose") or ""
    task = (f"SCHEDULE {form} filed {filed}{' (amendment no. ' + str(r['amendment']) + ')' if r.get('amendment') else ''}, {kind}. "
            f"{who}{group} reports {stake} ({shares_txt(r.get('shares'))} shares) as of {r.get('event_date') or filed}{change}."
            + (" The holding is now below 5%: the filer no longer has to report it." if below else "")
            + (" This is a new 13D, not an amendment." if form == "13D" else "")
            + (f"\nItem 4 (purpose), in the filer's words: {purpose[:400]}" if purpose else "")
            + (" Start the post with “JUST FILED:”." if fresh else "")
            + " Say who, how much (percent and shares), the change when given, and the filing date"
            + ("; give the purpose in a few of the filer's own words." if purpose else ".")
            + " Never call anyone an activist unless the purpose says they seek changes; never say what it means for the stock."
            + _figs(fq, cj, tk)
            + "\n\nEnd with one short question to the audience.")
    lead = ("JUST FILED: " if fresh else "") + ("Below 5%" if below else f"New {form}" if not form.endswith("/A") else f"{form}")
    fb = (f"{lead}: {who} reports {stake} ({shares_txt(r.get('shares'))} shares){change_fb}, "
          f"filed {_day(filed)}. What happens next?")
    url = r.get("url") or ""
    reply = f"The filing: Schedule {form} on {social.display_name(r.get('issuer') or '')}, filed {filed}. Not investment advice. {url}".strip()
    return {"kind": "stake", "task": task, "cashtags": [tk] if tk else [], "items": [(e, cj, fq)] if fq else [], "source_reply": reply,
            "fallback": fb, "manual": True,
            "tags": H.pick("stake" if d13 else "stake_passive", e, key=f"stake:{r.get('accession')}")}


def plan_stake_for(site, rows, by_ticker, target, today):
    """Owner: a post about one row of the hub's 13D / 13G table (ref: [accession])."""
    try:
        accn = (_ref(target) + [None])[0]
        d = hub_json(site, "stakes.json")
    except Exception as err:
        print(f"stake_for: {str(err)[:200]}")
        return None
    r = next((r for r in d.get("latest", []) if r.get("accession") == accn), None)
    if not r:
        print(f"stake_for: the filing {accn} is no longer in the hub's stakes.json")
        return None
    tk = (r.get("ticker") or "").upper().replace("-", ".")
    e = site_company(rows, by_ticker, r.get("issuer_cik"), tk)
    cj, fq = figures(site, e) if e else (None, None)
    return stake_plan(r, tk, e if fq else None, cj, fq, today)


def relation(text):
    """'Officer, Director, 10% Stockholder' → 'officer, director and 10% stockholder'."""
    parts = [x.strip().lower() for x in (text or "").split(",") if x.strip()]
    return ", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else (parts[0] if parts else "")


def f144_plan(r, tk, e, cj, fq, today):
    """The post plan for one Form 144 notice (a row of the hub's form144.json)."""
    who = social.display_name(r.get("seller_name") or r.get("seller") or "An insider")     # "Marc A. Nemati", not EDGAR's "Nemati Marc A."
    rel = relation(r.get("relationship"))
    what = _what(tk, r.get("issuer"))
    filed = r.get("filed") or ""
    fresh = filed >= (today - dt.timedelta(days=2)).isoformat()
    value = f" (market value about {money(r['value'])}, as given in the notice)" if r.get("value") else ""
    task = (f"FORM 144 filed {filed}: {who}{', ' + rel + ',' if rel else ''} gave notice of a planned sale of {shares_txt(r.get('shares'))} "
            f"shares of {what}{value}, approximate sale date {r.get('sale_date') or 'not given'}"
            + (f", through {r['broker']}" if r.get("broker") else "") + "."
            + (f" The shares were acquired by: {r['acquired']}." if r.get("acquired") else "")
            + (f" The notice names a 10b5-1 trading plan adopted {r['plan_date']}." if r.get("plan_date") else "")
            + (f" Sold in the past three months: {money(r['sold_3m'])}." if r.get("sold_3m") else "")
            + (" Start the post with “JUST FILED:”." if fresh else "")
            + " A Form 144 is a notice of an intended sale, not a trade: write “gave notice of a planned sale”, never “sold”, and never "
              "the word “sell”. Insiders sell for many reasons (taxes, diversification, planned sales): state the facts and imply nothing."
            + _figs(fq, cj, tk)
            + "\n\nEnd with one short question to the audience.")
    fb = (("JUST FILED: " if fresh else "") + f"Form 144: {what} {rel + ' ' if rel else ''}{who} gave notice of a planned sale of "
          f"{shares_txt(r.get('shares'))} shares" + (f" (~{money(r['value'])})" if r.get("value") else "")
          + (f" around {_day(r['sale_date'])}" if r.get("sale_date") else "")
          + (f", under a 10b5-1 plan adopted {_day(r['plan_date'])}" if r.get("plan_date") else "") + ". Routine or telling?")
    reply = f"The notice: Form 144 on {social.display_name(r.get('issuer') or '')}, filed {filed}. A notice is not a trade. {r.get('url') or ''}".strip()
    return {"kind": "form144", "task": task, "cashtags": [tk] if tk else [], "items": [(e, cj, fq)] if fq else [], "source_reply": reply,
            "fallback": fb, "manual": True, "tags": H.pick("form144", e, key=f"form144:{r.get('accession')}")}


def plan_f144_for(site, rows, by_ticker, target, today):
    """Owner: a post about one row of the hub's Form 144 table (ref: [accession])."""
    try:
        accn = (_ref(target) + [None])[0]
        d = hub_json(site, "form144.json")
    except Exception as err:
        print(f"f144_for: {str(err)[:200]}")
        return None
    r = next((r for r in d.get("latest", []) if r.get("accession") == accn), None)
    if not r:
        print(f"f144_for: the notice {accn} is no longer in the hub's form144.json")
        return None
    tk = (r.get("ticker") or "").upper().replace("-", ".")
    e = site_company(rows, by_ticker, r.get("issuer_cik"), tk)
    cj, fq = figures(site, e) if e else (None, None)
    return f144_plan(r, tk, e if fq else None, cj, fq, today)


def short_plan(r, day, prev_day, e, cj, fq):
    """The post plan for one stock's FINRA short interest (a row of the hub's short-interest.json)."""
    tk = (r.get("ticker") or "").upper().replace("-", ".")
    chg = r.get("change_pct")
    move = f", {chg:+.1f}% from {shares_txt(r.get('prev'))} on {prev_day}" if chg is not None and prev_day else ""
    hist = [h for h in (r.get("hist") or []) if h[1] is not None]
    trend = (f" Over the last {len(hist)} settlement dates it went from {shares_txt(hist[0][1])} ({hist[0][0]}) to "
             f"{shares_txt(hist[-1][1])}." if len(hist) >= 3 else "")
    dtc = f"; {r['dtc']:g} days to cover at an average daily volume of {shares_txt(r.get('adv'))} shares" if r.get("dtc") is not None else ""
    task = (f"FINRA SHORT INTEREST, settlement date {day} (published about a week later): {shares_txt(r.get('short'))} shares of ${tk} "
            f"were sold short{move}{dtc}." + trend
            + (" A stock split changed the share counts between the two dates." if r.get("split") else "")
            + " Short interest is a snapshot of open short positions, not trades: never predict a squeeze or say what it means for the "
              "price; write “shares sold short” or “short interest”, never the word “sell”."
            + _figs(fq, cj, tk)
            + "\n\nEnd with one short question to the audience.")
    fb = (f"Short interest in ${tk}: {shares_txt(r.get('short'))} shares as of {_day(day)}"
          + (f", {chg:+.1f}% vs {_day(prev_day)}" if chg is not None and prev_day else "")
          + (f" — {r['dtc']:g} days to cover" if r.get("dtc") is not None else "") + " (FINRA). Bets or hedges?")
    reply = f"Source: FINRA consolidated short interest, settlement date {day}. Not investment advice. https://www.finra.org/finra-data/browse-catalog/equity-short-interest"
    return {"kind": "short", "task": task, "cashtags": [tk], "items": [(e, cj, fq)] if fq else [], "source_reply": reply,
            "fallback": fb, "manual": True, "tags": H.pick("short", e, key=f"short:{tk}:{day}")}


def plan_short_for(site, rows, by_ticker, target, today):
    """Owner: a post about one row of the hub's Short interest table (ref: [ticker, settlement date])."""
    try:
        tick, day = (_ref(target) + [None, None])[:2]
        d = hub_json(site, "short-interest.json")
    except Exception as err:
        print(f"short_for: {str(err)[:200]}")
        return None
    if d.get("settlement_date") != day:
        print(f"short_for: the hub now shows {d.get('settlement_date')}, not {day}; nothing posted")
        return None
    r = next((r for r in d.get("rows", []) if r.get("ticker") == tick), None)
    if not r:
        print(f"short_for: {tick} is not in the hub's short-interest.json")
        return None
    tk = (tick or "").upper().replace("-", ".")
    e = site_company(rows, by_ticker, None, tk)
    cj, fq = figures(site, e) if e else (None, None)
    return short_plan(r, day, d.get("previous_date"), e if fq else None, cj, fq)


NEWS_LEAD = {"release": "Press release", "fda": "FDA", "sec_action": "SEC action", "suspension": "SEC trading suspension",
             "sec_release": "SEC"}


def news_plan(r, tk, e, cj, fq, today):
    """The post for one row of the hub's News table (app/news.py): the headline as the source published it, attributed."""
    kind, src = r.get("kind") or "release", r.get("source") or "the source"
    when = (r.get("published") or "").replace("T", " ")
    fresh = (r.get("published") or "") >= (today - dt.timedelta(days=1)).isoformat()
    who = social.display_name(r.get("company") or "") or f"${tk}"
    title = (r.get("title") or "").strip()
    what = {"release": f"a press release {who} published on {src}", "fda": f"an FDA record ({src})",
            "sec_action": "an SEC enforcement release", "suspension": "an SEC trading-suspension order",
            "sec_release": "an SEC press release"}.get(kind, f"a release on {src}")
    task = (f"NEWS, {what}, {when} UTC, about ${tk}: “{title}”."
            + " Say what was announced, attributed to its source, in the headline's own terms: the headline is the source's claim, "
              "not a verified fact, and it is the only fact you may use about it; no numbers that are not in it."
            + (" Start with “JUST IN:”." if fresh else "")
            + (" An SEC action states allegations unless it says the case was settled or decided: say “alleges” / “charged”, "
               "never that wrongdoing was proven." if kind in ("sec_action", "sec_release") else "")
            + (f"\n\nLatest filing figures of the company (context, at most one):\n{tweet.headline_lines(cj, fq, tk)}" if fq
               else "\n\nNo other figures. No chart is attached; do not mention one.")
            + "\n\nEnd with one short question to the audience.")
    lead = ("JUST IN: " if fresh else "") + NEWS_LEAD.get(kind, "News")
    fb = f"{lead}: ${tk} — “{title[:170]}{'…' if len(title) > 170 else ''}” ({src}). How do you read it?"
    reply = f"Source: {src}, {when} UTC. A headline, not investment advice. {r.get('url') or ''}".strip()
    tagkind = {"fda": "fda", "sec_action": "sec_action", "suspension": "sec_action", "sec_release": "sec_action"}.get(kind, "news")
    return {"kind": "news", "task": task, "cashtags": [tk], "items": [(e, cj, fq)] if fq else [], "source_reply": reply,
            "fallback": fb, "manual": True, "tags": H.pick(tagkind, e, key=f"news:{r.get('id')}")}


def plan_news_for(site, rows, by_ticker, target, today):
    """Owner: a post about one row of the hub's News table (ref: [id])."""
    try:
        nid = (_ref(target) + [None])[0]
        d = hub_json(site, "news.json")
    except Exception as err:
        print(f"news_for: {str(err)[:200]}")
        return None
    r = next((r for r in d.get("rows", []) if r.get("id") == nid), None)
    if not r or not r.get("tickers"):
        print(f"news_for: the item {nid} is not in the hub's news.json (or names no listed company)")
        return None
    tk = r["tickers"][0].upper().replace("-", ".")
    e = site_company(rows, by_ticker, None, tk)
    cj, fq = figures(site, e) if e else (None, None)
    return news_plan(r, tk, e if fq else None, cj, fq, today)


# ------------------------------------------------------------------ 8-K events (current reports)
# hashtags per post kind: now picked from pools by pipeline/hashtags.py (kept for reference and older callers)
TAGS = {"event8k": ["#8K", "#SEC", "#stocks", "#investing"],
        "fund13f": ["#13F", "#hedgefunds", "#smartmoney", "#stocks", "#investing"],
        "insider": ["#insiders", "#Form4", "#stocks", "#investing"]}
TOPIC_TAG = {"guidance raised": "#guidance", "guidance lowered": "#guidance", "guidance withdrawn": "#guidance",
             "a share buyback": "#buybacks", "a share offering (dilution)": "#dilution", "an FDA decision": "#FDA",
             "a restatement": "#restatement", "a delisting notice": "#delisting", "a cybersecurity incident": "#cybersecurity",
             "layoffs or restructuring": "#layoffs", "a contract award": "#contracts", "a dividend change": "#dividends",
             "bankruptcy": "#bankruptcy", "a CFO change": "#leadership", "an impairment": "#impairment",
             "a merger or acquisition": "#MergersAndAcquisitions", "a CEO change": "#leadership", "1.01": "#deal", "1.03": "#bankruptcy",
             "4.02": "#restatement", "5.02": "#leadership", "2.01": "#MergersAndAcquisitions", "2.02": "#earnings", "1.05": "#cybersecurity",
             "3.01": "#delisting", "2.05": "#restructuring", "2.06": "#impairment"}


def event_tags(code, label, profile=None, key=""):
    """#8K, the event's topic (a merger, a CEO change, ...), the industry, a general tag (pipeline/hashtags.py)."""
    return H.pick("8k", profile, topic=TOPIC_TAG.get(label) or TOPIC_TAG.get(code), key=key or f"{code}:{label}")


KIND_TAGS = {"event8k": "8k", "fund13f": "13f", "fund13f_for": "13f", "insider": "insider", "movers": "movers", "official": "congress",
             "stake": "stake", "form144": "form144", "short": "short", "news": "news", "reddit_hot": "reddit", "smart_buys": "smart",
             "smart_record": "smart", "all_agree": "flows", "qtd_flows": "flows", "pt_upside": "analysts", "versus": "versus",
             "drawdown": "drawdown", "setup": "setup", "lows52": "lows", "highs52": "highs", "near_lows": "lows", "records": "highs",
             "polymarket": "polymarket"}


ABBR = re.compile(r"\b(?:Inc|Ltd|Corp|Co|LLC|L\.P|LP|No|Nos|U\.S|Mr|Ms|Dr|St|Jr|S\.A|N\.V|plc)\.$")


def kind_tag(kind):
    """The hashtag pool of a post kind: the built-in table, else what its feature module registered."""
    reg = X.get(kind)
    return KIND_TAGS.get(kind) or (reg["tag"] if reg else "earnings")


def registered_plan(kind, site, rows, c, by_ticker, state_ok, today):
    """A plan from a feature module (pipeline/posts_*.py, pipeline/xkinds.py); None for an unknown kind."""
    reg = X.get(kind)
    if not reg:
        print(f"{kind}: unknown post kind")
        return None
    p = reg["plan"](site, rows, c, by_ticker, state_ok, today)
    if p:
        p.setdefault("kind", kind)
        p.setdefault("items", [])
    return p


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
            idx = sec.get_json(sec.filing_index_url(e["cik"], sub["accn"]))
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
        room = 255 - sum(len(t) + 1 for t in event_tags(ev["code"], label, e, sub["accn"])) - social.xlen(head) - len(": “” How do you read it?") - 2
        short = first_sentence(ev["quote"], limit=max(0, room))
        fb = f"{head}: “{short}{'' if short.endswith('…') else '.'}” How do you read it?" if len(short) >= 40 else f"{head}. How do you read it?"
        return {"kind": "event8k", "task": task, "cashtags": [e["ticker"]], "items": [(e, cj, fq)], "event": ev,
                "event_key": f"event8k:{sub['accn']}", "fallback": fb, "tags": event_tags(ev["code"], label, e, sub["accn"]),
                "thread": quote_replies(ev["quote"])}


def event_row_plan(r, e, cj, fq, today):
    """The post for one row of the hub's 8-K events table (app/events8k.py), written from the row alone (no SEC request):
    what the 8-K reports and its key sentences. e is the company's site row (with its figures) or None (text only)."""
    tk = (r.get("ticker") or (e or {}).get("ticker") or "").upper().replace("-", ".")
    if not tk:
        return None
    name = social.display_name(r.get("company") or (e or {}).get("name") or "")
    filed = r.get("filed") or ""
    when = filed + (f" {r['accepted'][11:16]} ET" if len(r.get("accepted") or "") >= 16 else "")
    fresh = filed >= (today - dt.timedelta(days=2)).isoformat()
    breaking = fresh and (r.get("score") or 0) >= 7
    g = r.get("guidance") if r.get("guidance") in ("raised", "lowered", "withdrawn", "reaffirmed", "mixed", "narrowed", "widened", "initiated") else None
    glabel = r.get("label") if str(r.get("label") or "").startswith("guidance ") else f"guidance {g}"     # "guidance raised and narrowed"
    label = glabel if g and (r.get("topics") or [""])[0] == "guidance" else (r.get("label") or events.ITEMS.get(r.get("code") or "", "a current report"))
    quote = r.get("guidance_quote") if g in ("raised", "lowered", "withdrawn", "mixed", "narrowed", "widened") and r.get("guidance_quote") else r.get("quote") or ""
    try:
        d = dt.date.fromisoformat(filed)
        filed_txt = f"{d:%b} {d.day}"
    except ValueError:
        filed_txt = filed
    items = ", ".join(x for x in r.get("items") or [] if x != "9.01") or "9.01"
    figs = (f"\n\nLatest filing figures (context, at most one):\n{tweet.headline_lines(cj, fq, tk)}" if fq
            else "\n\nNo other figures: use only the words above. No chart is attached; do not mention one.")
    task = (f"8-K CURRENT REPORT filed {when} by ${tk} ({name}): Items {items} — {label}."
            + (f"\nThe press release's title: “{r['headline']}”" if r.get("headline") else "")
            + f"\nWhat the filing says (quote; the only facts you may use about the event):\n“{quote or '(text not read; name the item only)'}”"
            + figs + "\n\n"
            + ("Start the post with “BREAKING:” — a material event filed in the last two days. " if breaking
               else "Start with “JUST FILED:”. " if fresh else f"Start with “8-K ({filed_txt}):” — it was filed on {filed_txt}, not today. ")
            + "Then say concretely what happened, using the quote: who did what with whom, the amounts and dates it gives, and the "
              "filing date. No facts beyond the quote; finish every sentence; never predict the stock's reaction; end with one short "
              "question to the audience.")
    lead = "BREAKING: " if breaking else "JUST FILED: " if fresh else ""
    head = f"{lead}${tk} 8-K filed {filed_txt} — {label}"
    tags = event_tags(r.get("code") or "", label, e, r.get("accession") or "")
    room = 255 - sum(len(t) + 1 for t in tags) - social.xlen(head) - len(": “” How do you read it?") - 2
    short = first_sentence(quote, limit=max(0, room))
    fb = f"{head}: “{short}{'' if short.endswith('…') else '.'}” How do you read it?" if len(short) >= 40 else f"{head}. How do you read it?"
    ev = {"code": r.get("code") or "", "label": label, "filed": filed, "url": r.get("url") or ""}
    return {"kind": "event8k", "task": task, "cashtags": [tk], "items": [(e, cj, fq)] if fq else [], "event": ev,
            "event_key": f"event8k:{r.get('accession')}", "fallback": fb, "tags": tags, "thread": quote_replies(quote), "manual": True}


def plan_filing8k(site, rows, target, today):
    """Owner tools: a post about one company's 8-K — the accession given (target['ref']), or else its most material 8-K of
    the last 45 days (earnings releases included). A company without charts on the site is written from the hub's 8-K
    events row (text only)."""
    cik = int(target["cik"])
    want = re.sub(r"[^0-9-]", "", str(target.get("ref") or ""))
    if want and "-" not in want and len(want) == 18:
        want = f"{want[:10]}-{want[10:12]}-{want[12:]}"
    e = next((r for r in rows if r.get("cik") == cik and r.get("ticker")), None)
    if not e:
        try:
            hub = hub_json(site, "events8k.json")
        except Exception as err:
            hub = {}
            print(f"filing8k: the hub's 8-K events not read ({str(err)[:100]})")
        r = next((r for r in hub.get("rows", []) if want and r.get("accession") == want), None)
        if r:
            return event_row_plan(r, None, None, None, today)
        print(f"filing8k: CIK {cik} is not on the site" + (f" and {want} is not in the hub's 8-K events" if want else ""))
        return None
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
            + "\n\nSay in the first sentence that the numbers are the RS rating (relative strength, 1–99) and that the jump "
              "took three months, e.g. “RS rating, 3 months: $AAA 6→97 …”. Then list them as cashtags with their rating jump, "
              "name the biggest climber in a few words, ask which one the audience thinks holds up.")
    fb = ("RS rating (relative strength vs ~600 large companies, 1–99) jumped in 3 months: "
          + ", ".join(f"${t} {then}→{now}" for _, now, then, t in picks) + ". Which one holds up?")
    return {"kind": "rsleaders", "task": task, "cashtags": [t for *_, t in picks], "items": items, "fallback": fb,
            "must": (r"\bRS\b|relative[ -]strength", "say that the numbers are the RS rating (relative strength, 1–99), "
                                                     "e.g. “RS rating, 3 months: $AAA 6→97”"),
            "tags": H.pick("rs", (items[0][0] if items else None), key="rsleaders:" + ",".join(t for *_, t in picks))}


# ------------------------------------------------------------------ smart money, all flows, Reddit's hottest (hub data)
# Every disclosed trade by 13F managers, active ETFs, insiders and officials scored by what the stock did next
# (disclosures/app/smart.py → data/smart/), the groups side by side per period (data/smart/combined/), and Reddit's
# hottest ticker right now (disclosures/app/reddit_hot.py → data/market/reddit.json).
SMART = {"min_votes": 3, "min_skilled": 2, "min_decisions": 8, "min_p": 0.65, "record_days": 30}
GNAME = {"f13": "13F managers", "etf": "active ETFs", "ins": "insiders", "gov": "officials"}
GONE = {"f13": "13F manager", "etf": "active ETF", "ins": "insider", "gov": "official"}


def _tk(t):
    return (t or "").upper().replace("-", ".")


def signed(v, d=0):
    return ("+" if v > 0 else "−" if v < 0 else "") + f"{abs(v):,.{d}f}"


def smart_file(site, rel):
    """A file of the hub's smart-money data (data/smart/…), or None when it is not published yet."""
    try:
        return hub_file(site, "smart/" + rel)
    except Exception as err:
        print(f"smart money: {rel} not available ({str(err)[:100]})")
        return None


def fnv_bucket(actor_id):
    """The actor's bucket file name — the same FNV-1a hash as disclosures/app/smart.py bucket()."""
    h = 0x811c9dc5
    for b in actor_id.encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xffffffff
    return f"{h % 128:02x}"


def smart_context(site, tk):
    """One stock's smart score now and how each group is voting (or None)."""
    d = smart_file(site, "t/" + re.sub(r"[^A-Za-z0-9-]", "_", tk.replace(".", "-")) + ".json")
    if not d or not d.get("now"):
        return None, ""
    n, votes = d["now"], d.get("votes") or []
    by = {}
    for v in votes:
        b = by.setdefault(v[2], [0, 0])
        b[0 if v[4] > 0 else 1] += 1
    parts = [f"{GNAME.get(g, g)} {b[0]} net buyers / {b[1]} net sellers" for g, b in by.items()]
    line = (f"Smart-money score {signed(n['S'])} on a scale of −100 to +100 (each trader's vote weighted by how often their past "
            f"trades beat SPY over the next 3 months; {n['n']} votes; everyone counted alike: {signed(n['raw'])}). " + "; ".join(parts) + ".")
    return n, line


def plan_reddit_hot(site, rows, c, by_ticker, state_ok, today):
    """The most-discussed stock right now (the hub's half-hourly Reddit scan picks it) as a setup post: where it trades,
    the year so far, short interest, filings, analysts, Polymarket and the smart money — the post never mentions Reddit."""
    hot = [t for t in trending(site)[:5] if state_ok("reddit_hot", t, hours=72)]
    for t in hot:
        p = plan_setup(site, rows, c, by_ticker, state_ok, today, pick=t, kind="reddit_hot")
        if p:
            p["forbid"] = NO_FORUM
            return p
    for tk in hot:                         # no price data for a setup: what the disclosed money is doing in it
        n, ctx = smart_context(site, tk)
        e = by_ticker.get(tk)
        cj, fq = figures(site, e) if e else (None, None)
        if not n and not fq:
            continue
        task = (f"A STOCK MANY INVESTORS ARE WATCHING RIGHT NOW: ${tk}.\n\nWHAT THE DISCLOSED MONEY IS DOING IN ${tk} (SEC and congressional "
                f"filings):\n" + (ctx or "No 13F manager, ETF, insider or official has traded it in the current windows.")
                + (f"\n\nLatest filing figures:\n{tweet.headline_lines(cj, fq, tk)}" if fq else "\n\nNo chart is attached; do not mention one.")
                + "\n\nOpen with the cashtag, then what the filings show in one sentence. Say “score” with its −100 to +100 scale if you "
                  "give it. Do not mention where it is discussed; never say what the stock will do; ask whether the attention and the filings agree.")
        fb = (f"${tk} is on a lot of watchlists right now. "
              + (f"The filings: smart-money score {signed(n['S'])} of ±100 from {n['n']} disclosed trades, weighted by each trader's record. "
                 if n else "No insider, 13F manager or official has traded it lately. ")
              + "Do the attention and the filings agree?")
        return {"kind": "reddit_hot", "task": task, "cashtags": [tk], "items": [(e, cj, fq)] if fq else [], "fallback": fb, "forbid": NO_FORUM,
                "tags": H.pick("reddit", e, key=f"reddit_hot:{tk}:{today}")}
    print("reddit_hot: no trending name with enough data, or all posted within three days")
    return None


def plan_smart_buys(site, rows, c, by_ticker, state_ok, today):
    """The stocks the traders with the best records are net buying now (smart-money score, −100 … +100)."""
    cfg = {**SMART, **(c.get("smart") or {})}
    d = smart_file(site, "index.json")
    if not d or not d.get("stocks"):
        return None
    F = d["stock_fields"]
    rows_ = [dict(zip(F, r)) for r in d["stocks"]]
    cands = [r for r in rows_ if (r.get("S") or 0) >= 50 and r["votes"] >= cfg["min_votes"] and r["skilled_buyers"] >= cfg["min_skilled"]
             and r["skilled_buyers"] > r["skilled_sellers"] and state_ok("smart_buys", _tk(r["ticker"]), hours=24 * 10)]
    cands.sort(key=lambda r: (_tk(r["ticker"]) in by_ticker, r["S"], r["skilled_buyers"]), reverse=True)
    picks = cands[:5]
    if len(picks) < 3:
        print("smart_buys: fewer than three stocks with skilled net buying")
        return None
    bt = ((d.get("backtest") or {}).get("all") or {}).get("smart") or {}
    top = next((b for b in bt.get("buckets") or [] if b[0].startswith("+50")), None)
    lines = []
    for r in picks:
        groups = ", ".join(f"{GNAME[g]} {signed(r['S_' + g])}" for g in ("f13", "etf", "ins", "gov") if r.get("S_" + g) is not None)
        lines.append(f"- ${_tk(r['ticker'])} ({r['name']}): score {signed(r['S'])}, {r['skilled_buyers']} net buyers with a winning record vs "
                     f"{r['skilled_sellers']} such sellers, {r['votes']} votes; by group: {groups}")
    items = []
    for r in picks:
        e = by_ticker.get(_tk(r["ticker"]))
        if e and len(items) < 4:
            cj, fq = figures(site, e)
            if fq:
                items.append((e, cj, fq))
    task = ("SMART-MONEY SCORE (−100 … +100): every disclosed trade by 13F managers, active ETFs, insiders and officials is scored by "
            "what the stock did next (its return against SPY over 63 trading days); today's net buyers and sellers of each stock are "
            "weighted by those records. Highest scores now:\n" + "\n".join(lines)
            + (f"\n\nHonesty line you may use: in the walk-forward backtest, stocks scoring +50 to +100 beat the typical stock "
               f"{top[4] * 100:.0f}% of the time over the next 3 months ({top[1]:,} stock-months)." if top and top[4] is not None else "")
            + "\n\nSay in the first sentence that the numbers are a score weighted by traders' track records. List the cashtags with their "
              "scores, name what stands out in a few words, ask which one the audience would dig into. Never say they will rise.")
    fb = ("Smart-money score (disclosed trades weighted by each trader's track record, −100 to +100): "
          + ", ".join(f"${_tk(r['ticker'])} {signed(r['S'])}" for r in picks) + ". Which one would you dig into?")
    return {"kind": "smart_buys", "task": task, "cashtags": [_tk(r["ticker"]) for r in picks], "items": items, "fallback": fb,
            "must": (r"score|record", "say the numbers are a score weighted by traders' track records (−100 to +100)"),
            "tags": H.pick("smart", items[0][0] if items else None, key="smart_buys:" + ",".join(r["ticker"] for r in picks))}


def plan_smart_record(site, rows, c, by_ticker, state_ok, today):
    """One trader with a strong, tested record (an official first, then insiders and 13F managers) who just traded."""
    cfg = {**SMART, **(c.get("smart") or {})}
    d = smart_file(site, "index.json")
    if not d:
        return None
    F = d["leader_fields"]
    since = (today - dt.timedelta(days=cfg["record_days"])).isoformat()
    for g in ("gov", "ins", "f13"):
        for raw in (d.get("leaders") or {}).get(g) or []:
            a = dict(zip(F, raw))
            if (a.get("decisions") or a["scored"]) < cfg["min_decisions"] or (a["p"] or 0) < cfg["min_p"] or (a["last"] or "") < since:
                continue
            if not state_ok("smart_record", a["id"], hours=24 * 30):
                continue
            b = smart_file(site, f"a/{g}/{fnv_bucket(a['id'])}.json")
            rec = ((b or {}).get("actors") or {}).get(a["id"])
            if not rec or not rec.get("trades"):
                continue
            t = rec["trades"][0]                        # [date, ticker, d, size, conviction, ex, ex2, follow, right, known, ref]
            tk = _tk(t[1])
            s = rec["stats"]
            e = by_ticker.get(tk)
            cj, fq = figures(site, e) if e else (None, None)
            verb = "bought" if t[2] > 0 else "sold"
            size = (f" (about {t[3] * 100:.1f}% of the portfolio)" if g in ("f13", "etf") else f" (${t[3]:,.0f}{' midpoint of the disclosed range' if g == 'gov' else ''})") if t[3] else ""
            who = f"{a['name']}" + (f", {a['sub']}" if a.get("sub") else "")
            task = (f"TRACK RECORD from public filings ({GONE[g]}; every disclosed trade scored by the stock's return against SPY over the "
                    f"next 63 trading days — a sale counts as right when the stock lagged): {who}. {s['scored']} trades scored in "
                    f"{s.get('decisions') or s['scored']} separate decisions; right on {s['hit'] * 100:.0f}% of them, {s['acc'] * 100:.0f}% weighted by "
                    f"size and move; buys right {(s['buy']['hit'] or 0) * 100:.0f}% ({s['buy']['n']}), sales {(s['sell']['hit'] or 0) * 100:.0f}% ({s['sell']['n']}); "
                    f"average excess return per trade {s['alpha'] * 100:+.1f}%.\nLATEST DISCLOSED TRADE: {verb} ${tk}{size} on {t[0]}, disclosed {t[9]}."
                    + (f"\n\nLatest filing figures of ${tk}:\n{tweet.headline_lines(cj, fq, tk)}" if fq else "\n\nNo chart is attached; do not mention one.")
                    + "\n\nOpen with the record (name and hit rate), then the latest trade. Past accuracy is no promise — never imply the "
                      "new trade will work; ask whether the audience thinks it is skill or luck.")
            fb = (f"Track record: {a['name']} — right on {s['hit'] * 100:.0f}% of {s['scored']} disclosed trades (stock vs SPY 3 months later). "
                  f"Latest: {verb} ${tk} on {t[0]}. Skill or luck?")
            return {"kind": "smart_record", "task": task, "cashtags": [tk], "items": [(e, cj, fq)] if fq else [], "fallback": fb,
                    "event_key": f"smart_record:{a['id']}", "must": (r"\d+%", "give the hit rate as a percentage"),
                    "tags": H.pick("congress" if g == "gov" else "insider" if g == "ins" else "13f", e, key=f"smart_record:{a['id']}")}
    print("smart_record: no strong, tested record with a trade in the last month")
    return None


def _combined_rows(site, key):
    d = smart_file(site, f"combined/{key}.json")
    ix = smart_file(site, "combined/index.json")
    if not d or not ix:
        return None, None
    per = next((p for p in ix.get("periods") or [] if p["key"] == key), {"label": key})
    F = d["fields"]
    return [dict(zip(F, r)) for r in d.get("rows") or []], per


def group_line(r, g):
    b, s_, u = r.get(g + "_b") or 0, r.get(g + "_s") or 0, r.get(g + "_usd") or 0
    if not b and not s_:
        return None
    return f"{GNAME[g]} {b} net buyers / {s_} net sellers ({'+' if u >= 0 else '−'}{money(abs(u))} net)"


def plan_all_agree(site, rows, c, by_ticker, state_ok, today):
    """A stock that every group trading it was net buying in this quarter's filings: 13F managers, insiders, officials …"""
    for key in ("prev", "qtd"):
        rs, per = _combined_rows(site, key)
        if not rs:
            continue
        cands = [r for r in rs if r["groups_buy"] >= 2 and not r["groups_sell"] and state_ok("all_agree", _tk(r["ticker"]), hours=24 * 14)]
        cands.sort(key=lambda r: (r["groups_buy"], _tk(r["ticker"]) in by_ticker, sum(r[g + "_usd"] for g in GNAME)), reverse=True)
        if not cands:
            continue
        r = cands[0]
        tk = _tk(r["ticker"])
        e = by_ticker.get(tk)
        cj, fq = figures(site, e) if e else (None, None)
        lines = [x for x in (group_line(r, g) for g in GNAME) if x]
        task = (f"ALL FLOWS, {per['label']} (SEC 13F and N-PORT reports, Form 4, House and Senate disclosures; each name counted once, "
                f"its trades netted): every group that traded ${tk} was a net buyer — " + "; ".join(lines) + "."
                + (f" Smart-money score now {signed(r['S_now'])} of ±100." if r.get("S_now") is not None else "")
                + (f"\n\nLatest filing figures:\n{tweet.headline_lines(cj, fq, tk)}" if fq else "\n\nNo chart is attached; do not mention one.")
                + "\n\nOpen with the agreement (how many groups, which), give each group's count, ask whether it means anything. "
                  "13F holdings are quarter-end positions reported weeks later; say nothing about where the stock goes.")
        fb = (f"${tk}, {per['label'].split(' (')[0]}: every group that traded it was a net buyer — " + "; ".join(lines) + ". Signal or coincidence?")
        if social.xlen(fb) > 250:
            fb = f"${tk}: {r['groups_buy']} groups of disclosed traders (13F managers, insiders, officials, ETFs) were all net buyers, none net sellers. Signal or coincidence?"
        return {"kind": "all_agree", "task": task, "cashtags": [tk], "items": [(e, cj, fq)] if fq else [], "fallback": fb,
                "tags": H.pick("flows", e, key=f"all_agree:{tk}:{key}")}
    print("all_agree: no stock net-bought by two groups or more and sold by none")
    return None


def plan_qtd_flows(site, rows, c, by_ticker, state_ok, today):
    """The quarter so far: insiders' and officials' biggest net purchases, and what the early 13F filers added."""
    q, per = _combined_rows(site, "qtd")
    p, per_p = _combined_rows(site, "prev")
    if not q:
        return None
    ins = sorted([r for r in q if (r.get("ins_usd") or 0) > 0], key=lambda r: -r["ins_usd"])[:2]
    gov = sorted([r for r in q if (r.get("gov_b") or 0) > (r.get("gov_s") or 0)], key=lambda r: (-r["gov_b"], -r["gov_usd"]))[:2]
    f13 = sorted([r for r in (p or []) if (r.get("f13_usd") or 0) > 0], key=lambda r: -r["f13_usd"])[:1]
    picks, seen = [], set()
    for r in ins + gov + f13:
        if _tk(r["ticker"]) not in seen:
            seen.add(_tk(r["ticker"]))
            picks.append(r)
    if len(picks) < 3:
        print("qtd_flows: too little in the quarter so far")
        return None
    lines = [f"- insiders: ${_tk(r['ticker'])} {money(r['ins_usd'])} net purchases ({r['ins_b']} insiders)" for r in ins]
    lines += [f"- officials: ${_tk(r['ticker'])} {r['gov_b']} members net buyers ({r['gov_s']} net sellers)" for r in gov]
    lines += [f"- early 13F filers for {per_p['label'].split(' —')[0]}: ${_tk(r['ticker'])} {money(r['f13_usd'])} net added ({r['f13_b']} managers)" for r in f13]
    items = []
    for r in picks:
        e = by_ticker.get(_tk(r["ticker"]))
        if e and len(items) < 4:
            cj, fq = figures(site, e)
            if fq:
                items.append((e, cj, fq))
    label = per["label"]
    task = (f"{label.upper()} — what the disclosed money did (Form 4 open-market trades, House and Senate reports, and the 13F "
            f"reports arriving for the last quarter):\n" + "\n".join(lines)
            + "\n\nOpen with the quarter so far, then the standout of each group with its cashtag and number, then a question.")
    fb = (f"{label.split(' (')[0]}: " + "; ".join(l[2:] for l in lines[:3]) + ". Which one would you look into?")
    if social.xlen(fb) > 250:
        fb = f"{label.split(' (')[0]}, the disclosed money: " + ", ".join(f"${_tk(r['ticker'])}" for r in picks) + " lead. Which one would you look into?"
    return {"kind": "qtd_flows", "task": task, "cashtags": [_tk(r["ticker"]) for r in picks[:3]], "allowed": [_tk(r["ticker"]) for r in picks],
            "items": items, "fallback": fb, "tags": H.pick("flows", items[0][0] if items else None, key=f"qtd_flows:{today}")}


# ------------------------------------------------------------------ market posts: analysts, Polymarket, 52-week and all-time highs / lows
# The formats that travel on X: two stocks side by side ("$A or $B?"), the same Wall Street rating with very different
# price-target upside, how far the popular names sit below their highs, one stock's setup in bullets, the day's new
# 52-week lows / highs, quality names near their lows, all-time highs / lows, Polymarket's earnings odds. Sources: the
# hub's consensus (analysts + Polymarket / Kalshi, data/consensus/index.json), highs and lows (data/market/extremes.json,
# disclosures/app/extremes.py), short interest, 8-Ks, news, Reddit's trending tickers (used for the picks only — the posts
# never talk about Reddit), the smart-money score. Each plan carries "fallbacks": several rule-written phrasings, the first
# used when no model answers and all of them as training targets for the local models (pipeline/corpus.py).
SUFFIX_RE = re.compile(r"(,?\s+(Inc|Incorporated|Corp|Corporation|Co|Company|Companies|Ltd|Limited|plc|PLC|Holdings?|Group|N\.?V|S\.?A|AG|SE|"
                       r"L\.?P|LLC|Class [A-C]|Common Stock|\(The\))\.?)+$", re.I)


def short_name(name, tk=""):
    """"McDONALD'S CORP" → "McDonald's"; "Bank of America Corporation" → "Bank of America"."""
    n = social.display_name((name or tk).strip())
    n = re.sub(r"\s*/[A-Z]{2,}/?$", "", n)
    for _ in range(3):
        n = SUFFIX_RE.sub("", n).strip(" ,.")
    return n or tk


def px_fmt(v):
    return f"${v:,.0f}" if v >= 20 else f"${v:,.2f}"


def pct_fmt(v, d=0):
    return f"{'+' if v > 0 else '−' if v < 0 else ''}{abs(v) * 100:.{d}f}%"


def eps_fmt(v):
    """EPS as written in a post: $1.15, −$0.08."""
    return "n/a" if v is None else f"{'−' if v < 0 else ''}${abs(v):,.2f}"


def hub_market(site, name):
    try:
        return hub_json(site, name)
    except Exception as err:
        print(f"market posts: {name} not available ({str(err)[:90]})")
        return None


def extremes(site):
    """{ticker: row} of the day's highs and lows (data/market/extremes.json) and the file itself."""
    d = hub_market(site, "extremes.json")
    if not d:
        return {}, {}
    F = d["fields"]
    return {_tk(r[0]): dict(zip(F, r)) for r in d.get("rows") or []}, d


def consensus(site):
    try:
        d = hub_cached(site, "consensus/index.json")
    except Exception as err:
        print(f"market posts: consensus not available ({str(err)[:90]})")
        return {}
    F = d["fields"]
    return {_tk(r[F.index("ticker")]): dict(zip(F, r)) for r in d.get("rows") or [] if r[F.index("ticker")]}


def trending(site):
    """Reddit's trending tickers right now (the hub's half-hourly scan) — used to pick names, never mentioned."""
    try:
        return [_tk(r["ticker"]) for r in hub_cached(site, "market/reddit.json").get("rows") or []]
    except Exception:
        return []


def rating_word(m):
    if m is None:
        return None
    return "Hold" if 2.6 <= m <= 3.4 else "Underperform" if m > 3.4 else None    # "Buy" ratings cannot be quoted (no advice words)


def popular(site, by_ticker, ext, cons, limit=60):
    """The names people follow: Reddit's trending tickers first, then the most traded stocks the site and the hub know."""
    seen, out = set(), []
    for t in trending(site) + sorted(ext, key=lambda t: -(ext[t].get("dollar_vol") or 0)):
        if t in seen or t not in ext:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= limit:
            break
    return out


def _chart(site, by_ticker, tk):
    e = by_ticker.get(tk)
    if not e:
        return None
    cj, fq = figures(site, e)
    return (e, cj, fq) if fq else None


def _items(site, by_ticker, tks, n=4):
    out = []
    for t in tks:
        x = _chart(site, by_ticker, t)
        if x:
            out.append(x)
        if len(out) >= n:
            break
    return out


def _name(t, ext, cons):
    return short_name((cons.get(t) or {}).get("name") or (ext.get(t) or {}).get("name") or t, t)


def plan_pt_upside(site, rows, c, by_ticker, state_ok, today):
    """Wall Street rates both a Hold — but one has several times the price-target upside."""
    cons = consensus(site)
    ext, _ = extremes(site)
    pop = set(popular(site, by_ticker, ext, cons, 120)) | set(by_ticker)
    cands = []
    for t, r in cons.items():
        px, tg, rm = r.get("price"), r.get("target_mean"), r.get("rating_mean")
        if t not in pop or not px or not tg or rating_word(rm) != "Hold" or (r.get("eps_q_n") or 0) < 4:
            continue
        up = tg / px - 1
        if 0.03 <= up <= 1.5:
            cands.append((up, t, r))
    cands.sort()
    best = None
    for hi_up, hb, rb in reversed(cands):
        if not state_ok("pt_upside", hb, hours=24 * 14):
            continue
        for lo_up, ha, ra in cands:
            if ha == hb or hi_up / lo_up < 2.5 or not state_ok("pt_upside", ha, hours=24 * 14):
                continue
            best = (ha, ra, lo_up, hb, rb, hi_up)
            break
        if best:
            break
    if not best:
        print("pt_upside: no pair of Hold-rated names with very different upside")
        return None
    a, ra, ua, b, rb, ub = best
    ratio = ub / ua
    lines = f"${a} → PT ${ra['target_mean']:,.2f} ({pct_fmt(ua)})\n${b} → PT ${rb['target_mean']:,.2f} ({pct_fmt(ub)})"
    task = (f"ANALYSTS' CONSENSUS (Yahoo Finance): both rated Hold on average (${a} {ra['rating_mean']:.1f}, ${b} {rb['rating_mean']:.1f} on the "
            f"1–5 scale, 1 the most positive; write only “Hold”).\n- ${a}: price ${ra['price']:,.2f}, mean price target ${ra['target_mean']:,.2f} = {pct_fmt(ua)} upside\n"
            f"- ${b}: price ${rb['price']:,.2f}, mean price target ${rb['target_mean']:,.2f} = {pct_fmt(ub)} upside\n- {b}'s upside is {ratio:.1f}x {a}'s.\n\n"
            "Format with line breaks: one line that both are rated Hold, one line on the gap, the two “$TICKER → PT $X (+Y%)” lines, "
            "then a question (is the market missing one, or is the other the safer bet?). Never say which to own.")
    f1 = f"Wall Street rates both ${a} and ${b} a Hold.\n\nBut one has {ratio:.1f}x the upside.\n\n{lines}\n\nIs the market sleeping on ${b}, or is ${a} the safer bet?"
    f2 = f"Same rating, very different upside. Analysts call ${a} and ${b} a Hold, yet:\n\n{lines}\n\nWhich target is wrong?"
    f3 = f"${a} and ${b}: both a consensus Hold.\n\n{lines}\n\n{ratio:.1f}x the upside for ${b}. What does Wall Street see that the market doesn't?"
    return {"kind": "pt_upside", "task": task, "cashtags": [a, b], "items": _items(site, by_ticker, [a, b], 2), "fallback": f1,
            "fallbacks": [f1, f2, f3], "lines": True, "tags": H.pick("analysts", (_chart(site, by_ticker, a) or [None])[0], key=f"pt:{a}:{b}")}


def plan_versus(site, rows, c, by_ticker, state_ok, today):
    """“$A or $B — which would you rather have?” for two names people are watching, with one fact each."""
    cons = consensus(site)
    ext, _ = extremes(site)
    pop = [t for t in popular(site, by_ticker, ext, cons, 40) if state_ok("versus", t, hours=24 * 7)]
    if len(pop) < 2:
        return None
    a = pop[0]
    ya = ext[a].get("ytd")
    b = next((t for t in pop[1:12] if ya is not None and ext[t].get("ytd") is not None and (ext[t]["ytd"] > 0) != (ya > 0)), pop[1])
    def fact(t):
        r, k = ext[t], cons.get(t) or {}
        bits = [f"{pct_fmt(r['ytd'])} this year" if r.get("ytd") is not None else None,
                f"{pct_fmt(r['from_hi'])} from its 52-week high" if r.get("from_hi") is not None and r["from_hi"] <= -0.1 else None,
                f"analysts' target {pct_fmt(k['target_mean'] / k['price'] - 1)} away" if k.get("target_mean") and k.get("price") else None]
        return [x for x in bits if x]
    fa, fb = fact(a), fact(b)
    task = (f"TWO STOCKS PEOPLE ARE WATCHING:\n- ${a} ({_name(a, ext, cons)}): price {px_fmt(ext[a]['close'])}; " + "; ".join(fa) +
            f"\n- ${b} ({_name(b, ext, cons)}): price {px_fmt(ext[b]['close'])}; " + "; ".join(fb) +
            "\n\nWrite a short either/or post: “$A or $B — which would you rather have?” style, optionally one fact each. Never say which to own.")
    f1 = f"${a} or ${b} what stock would you rather have?"
    f2 = f"${a} ({fa[0]}) or ${b} ({fb[0]}) — which one would you rather own for the next year?" if fa and fb else f"${a} or ${b}? Pick one for the next 12 months."
    f3 = f"One stock for the next 12 months: ${a} or ${b}?"
    return {"kind": "versus", "task": task, "cashtags": [a, b], "items": _items(site, by_ticker, [a, b], 2), "fallback": f1,
            "fallbacks": [f1, f2, f3], "tags": H.pick("versus", (_chart(site, by_ticker, a) or [None])[0], key=f"vs:{a}:{b}")}


def plan_drawdown(site, rows, c, by_ticker, state_ok, today):
    """The popular names far below their 52-week highs: “$RKLB $150 → $50”."""
    cons = consensus(site)
    ext, _ = extremes(site)
    pop = popular(site, by_ticker, ext, cons, 80)
    picks = [t for t in pop if (ext[t].get("from_hi") or 0) <= -0.35 and ext[t].get("hi52") and state_ok("drawdown", t, hours=24 * 10)][:6]
    if len(picks) < 4:
        print("drawdown: fewer than four popular names 35%+ below their highs")
        return None
    lines = "\n".join(f"${t} {px_fmt(ext[t]['hi52'])} → {px_fmt(ext[t]['close'])}" for t in picks)
    task = ("POPULAR STOCKS FAR BELOW THEIR 52-WEEK HIGHS (52-week high → last close):\n"
            + "\n".join(f"- ${t} ({_name(t, ext, cons)}): high {px_fmt(ext[t]['hi52'])} on {ext[t].get('peak_date')}, now {px_fmt(ext[t]['close'])} "
                        f"({pct_fmt(ext[t]['from_hi'])})" for t in picks)
            + "\n\nFormat with line breaks: a short hook, then one “$TICKER $high → $now” line per stock, then a closing line or question. "
              "No advice, no prediction.")
    f1 = f"Remember the highs?\n\n{lines}\n\nWhich one gets back there first?"
    f2 = f"From their 52-week highs:\n\n{lines}\n\nBuying the dip is easy when there's no dip, right?"
    f3 = f"52-week high → today:\n\n{lines}\n\nWhich of these is the opportunity, and which is the trap?"
    return {"kind": "drawdown", "task": task, "cashtags": picks[:2], "allowed": picks, "items": _items(site, by_ticker, picks),
            "fallback": f1, "fallbacks": [f1, f2, f3], "lines": True,
            "tags": H.pick("drawdown", None, key="drawdown:" + ",".join(picks))}


def _list_post(kind, site, rows, by_ticker, state_ok, tks, head, ext, cons, fmt_line, closing, tag, n=8):
    picks = [t for t in tks if state_ok(kind, t, hours=24 * 5)][:n]
    if len(picks) < 4:
        print(f"{kind}: fewer than four names")
        return None
    def body(k):
        return "\n".join(fmt_line(t) for t in picks[:k])
    tags = H.pick(tag, None, key=f"{kind}:" + ",".join(picks))
    room = 250 - social.xlen(" " + " ".join(tags))          # the hashtags stay
    k = len(picks)
    while k > 4 and social.xlen(f"{head}\n\n{body(k)}\n\n{max(closing, key=len)}") > room:
        k -= 1
    picks = picks[:k]
    task = (f"{head.upper()}:\n" + "\n".join(f"- {fmt_line(t)} · close {px_fmt(ext[t]['close'])}, {pct_fmt(ext[t]['from_hi'])} from the 52-week high, "
                                             f"YTD {pct_fmt(ext[t]['ytd']) if ext[t].get('ytd') is not None else 'n/a'}" for t in picks)
            + "\n\nFormat with line breaks: the headline line, one line per stock exactly as listed (name and cashtag), then one short closing question.")
    fbs = [f"{head}\n\n{body(k)}\n\n{q}" for q in closing]
    return {"kind": kind, "task": task, "cashtags": picks[:2], "allowed": picks, "items": _items(site, by_ticker, picks),
            "fallback": fbs[0], "fallbacks": fbs, "lines": True, "tags": tags}


def plan_lows52(site, rows, c, by_ticker, state_ok, today):
    """“All these stocks hit new 52-week lows today”: the best-known names that did."""
    ext, d = extremes(site)
    cons = consensus(site)
    if not d or d.get("asof", "") < (today - dt.timedelta(days=3)).isoformat():
        return None
    known = [t for t in (d.get("new_lows") or []) if t in by_ticker or t in cons]
    return _list_post("lows52", site, rows, by_ticker, state_ok, known, f"All these stocks hit new 52-week lows on {_day(d['asof'])}", ext, cons,
                      lambda t: f"{_name(t, ext, cons)} ${t}", ["Which one is a bargain, and which one is a value trap?", "Any of these on your list?"], "lows")


def plan_highs52(site, rows, c, by_ticker, state_ok, today):
    """The best-known names at new 52-week highs."""
    ext, d = extremes(site)
    cons = consensus(site)
    if not d or d.get("asof", "") < (today - dt.timedelta(days=3)).isoformat():
        return None
    known = [t for t in (d.get("new_highs") or []) if t in by_ticker or t in cons]
    return _list_post("highs52", site, rows, by_ticker, state_ok, known, f"New 52-week highs on {_day(d['asof'])}", ext, cons,
                      lambda t: f"{_name(t, ext, cons)} ${t} {pct_fmt(ext[t]['ytd']) if ext[t].get('ytd') is not None else ''} YTD".replace("  ", " "),
                      ["Which one still has room?", "Momentum or exhaustion?"], "highs")


def plan_near_lows(site, rows, c, by_ticker, state_ok, today):
    """Quality companies (profitable, large) trading near their 52-week lows, with how far they are off the high."""
    ext, d = extremes(site)
    cons = consensus(site)
    qual = [t for t, e in by_ticker.items() if t in ext and isinstance(e.get("om"), (int, float)) and e["om"] >= 10
            and (e.get("revenue") or 0) >= 1e9 and (ext[t].get("from_lo") or 9) <= 0.08 and (ext[t].get("from_hi") or 0) <= -0.15]
    qual.sort(key=lambda t: ext[t]["from_hi"])
    return _list_post("near_lows", site, rows, by_ticker, state_ok, qual, "Quality stocks trading near their 52-week lows", ext, cons,
                      lambda t: f"{_name(t, ext, cons)} ${t}: {pct_fmt(ext[t]['from_hi'])}",
                      ["Which one would you look at first?", "Opportunity or trap?"], "lows")


def plan_records(site, rows, c, by_ticker, state_ok, today):
    """All-time highs (or lows) set in the last session."""
    ext, d = extremes(site)
    cons = consensus(site)
    if not d or d.get("asof", "") < (today - dt.timedelta(days=3)).isoformat():
        return None
    ath = [t for t in d.get("ath") or [] if t in by_ticker or t in cons]
    atl = [t for t in d.get("atl") or [] if t in by_ticker or t in cons]
    if len(ath) >= 4:
        return _list_post("records", site, rows, by_ticker, state_ok, ath, f"New all-time highs on {_day(d['asof'])}", ext, cons,
                          lambda t: f"{_name(t, ext, cons)} ${t} {px_fmt(ext[t]['day_hi'])}", ["Which one is next?", "Still early, or late?"], "highs")
    if len(atl) >= 4:
        return _list_post("records", site, rows, by_ticker, state_ok, atl, f"New all-time lows on {_day(d['asof'])}", ext, cons,
                          lambda t: f"{_name(t, ext, cons)} ${t} {px_fmt(ext[t]['day_lo'])}", ["Is there a floor anywhere here?", "Bottom, or more to come?"], "lows")
    print("records: fewer than four known names at an all-time high or low")
    return None


def plan_setup(site, rows, c, by_ticker, state_ok, today, pick=None, kind="setup"):
    """One stock's setup going into the next session, in bullets: where it trades against its range, the year so far,
    short interest, the latest filing or release, analysts, Polymarket, the smart money."""
    ext, _ = extremes(site)
    cons = consensus(site)
    cands = ([pick] if pick else []) + [t for t in trending(site)[:10] if t in ext]
    tk = next((t for t in cands if t and t in ext and state_ok(kind, t, hours=72)), None)
    if not tk:
        print(f"{kind}: no trending name with price data")
        return None
    r, k = ext[tk], cons.get(tk) or {}
    facts = []
    if r.get("from_lo") is not None and r["from_lo"] <= 0.1:
        facts.append(("lo", f"Trading near its 52-week low, around {px_fmt(r['close'])}"))
    elif r.get("from_hi") is not None and r["from_hi"] >= -0.05:
        facts.append(("hi", f"Trading near its 52-week high, around {px_fmt(r['close'])}"))
    elif r.get("from_hi") is not None:
        facts.append(("hi", f"{pct_fmt(r['from_hi'])} from its 52-week high of {px_fmt(r['hi52'])}"))
    if r.get("ytd") is not None:
        facts.append(("ytd", f"{'Up' if r['ytd'] > 0 else 'Down'} roughly {abs(r['ytd']) * 100:.0f}% YTD"))
    si = hub_market(site, "short-interest.json") or {}
    srow = next((x for x in si.get("rows") or [] if _tk(x.get("ticker")) == tk), None)
    if srow and srow.get("dtc"):
        facts.append(("si", f"Short interest {srow['dtc']:.1f} days to cover" + (f" ({'+' if srow['change_pct'] > 0 else '−'}{abs(srow['change_pct']):.0f}% since mid-month)"
                                                                                  if srow.get("change_pct") else "")))
    if k.get("pm_beat_prob") is not None and k.get("pm_report_date"):
        facts.append(("pm", f"Polymarket: {k['pm_beat_prob'] * 100:.0f}% odds it beats EPS on {_day(k['pm_report_date'])}"))
    elif k.get("next_earnings"):
        facts.append(("er", f"Reports earnings {_day(k['next_earnings'])}"))
    if k.get("target_mean") and k.get("price"):
        facts.append(("pt", f"Analysts' target ${k['target_mean']:,.2f} ({pct_fmt(k['target_mean'] / k['price'] - 1)})"))
    ev = hub_market(site, "events8k.json") or {}
    e8 = next((x for x in ev.get("rows") or [] if _tk(x.get("ticker")) == tk and (x.get("filed") or "") >= (today - dt.timedelta(days=30)).isoformat()), None)
    if e8:
        facts.append(("8k", f"8-K filed {_day(e8['filed'])}: {event_label(e8.get('code'), e8.get('quote'))}"))
    n, _ = smart_context(site, tk)
    if n and n.get("S") is not None and abs(n["S"]) >= 30:
        facts.append(("sm", f"Smart-money score {signed(n['S'])} of ±100 (insiders, 13F, officials, weighted by record)"))
    if len(facts) < 3:
        print(f"{kind}: too little on {tk}")
        return None
    day = next_trading_day(today).strftime("%A")
    tags = H.pick("setup", (_chart(site, by_ticker, tk) or [None])[0], key=f"{kind}:{tk}:{today}")
    room = 250 - social.xlen(" " + " ".join(tags))          # the hashtags stay
    task = (f"${tk} ({_name(tk, ext, cons)}) GOING INTO {day.upper()} — the facts (use only these):\n" + "\n".join(f"- {f}" for _, f in facts)
            + "\n\nFormat: first line “$TICKER going into <day>”, then 3–5 bullet lines starting with “• ”, then one short closing line "
              "that frames the tension (no prediction, no advice).")
    def fb(intro, close, nb):
        body = "\n".join("• " + f for _, f in facts[:nb])
        txt = f"{intro}\n\n{body}\n\n{close}"
        while social.xlen(txt) > room and nb > 2:
            nb -= 1
            body = "\n".join("• " + f for _, f in facts[:nb])
            txt = f"{intro}\n\n{body}\n\n{close}"
        return txt
    f1 = fb(f"${tk} going into {day}", "What's your read?", 5)
    f2 = fb(f"${tk} into {day}:", "Setup or trap?", 4)
    f3 = fb(f"Watching ${tk} into {day}", "Where does it go from here?", 3)
    return {"kind": kind, "task": task, "cashtags": [tk], "items": _items(site, by_ticker, [tk], 1), "fallback": f1, "fallbacks": [f1, f2, f3],
            "lines": True, "tags": tags}


def plan_polymarket(site, rows, c, by_ticker, state_ok, today):
    """Polymarket's odds that the companies reporting this week beat the EPS line."""
    cons = consensus(site)
    soon = (today + dt.timedelta(days=7)).isoformat()
    rows_ = [(t, r) for t, r in cons.items() if r.get("pm_beat_prob") is not None and r.get("pm_report_date")
             and today.isoformat() <= r["pm_report_date"] <= soon and state_ok("polymarket", t, hours=24 * 5)]
    rows_.sort(key=lambda x: (x[0] not in by_ticker, x[1]["pm_report_date"], -(x[1]["poly_markets"] or 0)))
    if not rows_:
        print("polymarket: no Polymarket earnings market this week")
        return None
    if len(rows_) >= 3:
        picks = rows_[:5]
        lines = "\n".join(f"${t} {_day(r['pm_report_date'])}: {r['pm_beat_prob'] * 100:.0f}%" for t, r in picks)
        task = ("POLYMARKET — the crowd's odds that each company beats the EPS line it set, for the companies reporting this week:\n"
                + "\n".join(f"- ${t} reports {r['pm_report_date']}: {r['pm_beat_prob'] * 100:.0f}% chance of beating EPS {eps_fmt(r['pm_eps_strike'])}; analysts expect "
                            f"{eps_fmt(r['eps_q'])} ({r['eps_q_n']} estimates)" + (f"; beat {r['beat_rate'] * 100:.0f}% of its last 8 reports" if r.get("beat_rate") is not None else "")
                            for t, r in picks)
                + "\n\nFormat with line breaks: a headline line, one “$TICKER day: NN%” line each, then a question (which one surprises?).")
        f1 = f"Polymarket odds of an earnings beat this week:\n\n{lines}\n\nWhich one surprises the crowd?"
        f2 = f"Earnings this week. Polymarket's chance of a beat:\n\n{lines}\n\nWho's the crowd wrong about?"
        tks = [t for t, _ in picks]
        return {"kind": "polymarket", "task": task, "cashtags": tks[:2], "allowed": tks, "items": _items(site, by_ticker, tks), "fallback": f1,
                "fallbacks": [f1, f2], "lines": True, "tags": H.pick("polymarket", None, key="poly:" + ",".join(tks))}
    t, r = rows_[0]
    br = f" It beat {r['beat_rate'] * 100:.0f}% of its last 8 reports." if r.get("beat_rate") is not None else ""
    task = (f"POLYMARKET: {r['pm_beat_prob'] * 100:.0f}% chance ${t} beats EPS of {eps_fmt(r['pm_eps_strike'])} when it reports on {r['pm_report_date']}. "
            + (f"Analysts expect {eps_fmt(r['eps_q'])} ({r['eps_q_n']} estimates)." if r.get("eps_q") is not None else "") + f"{br}\n\nOne post: the odds, the line, the analysts, one question.")
    f1 = f"Polymarket gives ${t} a {r['pm_beat_prob'] * 100:.0f}% chance of beating EPS {eps_fmt(r['pm_eps_strike'])} on {_day(r['pm_report_date'])}." + (f" Analysts expect {eps_fmt(r['eps_q'])}." if r.get("eps_q") is not None else "") + f"{br} Too high or too low?"
    f2 = f"${t} reports {_day(r['pm_report_date'])}. The crowd on Polymarket: {r['pm_beat_prob'] * 100:.0f}% it beats {eps_fmt(r['pm_eps_strike'])}. Do you take the over?"
    return {"kind": "polymarket", "task": task, "cashtags": [t], "items": _items(site, by_ticker, [t], 1), "fallback": f1, "fallbacks": [f1, f2],
            "tags": H.pick("polymarket", (_chart(site, by_ticker, t) or [None])[0], key=f"poly:{t}")}


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
        reg = X.get(kind)
        hours = (c.get("kind_cooldown") or {}).get(kind, reg["cooldown"] if reg else c["kind_cooldown_hours"])
        return force or (state.get(f"kind:{kind}") or "") < (now - dt.timedelta(hours=hours)).isoformat()

    kinds = X.expand(kinds, cap=int(c.get("registered_per_run", 4)), seed=today.toordinal())   # "@close" → the modules' kinds (pipeline/xkinds.py)
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
             "reddit_hot": lambda: plan_reddit_hot(site, rows, c, by_ticker, state_ok, today),
             "smart_buys": lambda: plan_smart_buys(site, rows, c, by_ticker, state_ok, today),
             "smart_record": lambda: plan_smart_record(site, rows, c, by_ticker, state_ok, today),
             "all_agree": lambda: plan_all_agree(site, rows, c, by_ticker, state_ok, today),
             "qtd_flows": lambda: plan_qtd_flows(site, rows, c, by_ticker, state_ok, today),
             "pt_upside": lambda: plan_pt_upside(site, rows, c, by_ticker, state_ok, today),
             "versus": lambda: plan_versus(site, rows, c, by_ticker, state_ok, today),
             "drawdown": lambda: plan_drawdown(site, rows, c, by_ticker, state_ok, today),
             "setup": lambda: plan_setup(site, rows, c, by_ticker, state_ok, today),
             "lows52": lambda: plan_lows52(site, rows, c, by_ticker, state_ok, today),
             "highs52": lambda: plan_highs52(site, rows, c, by_ticker, state_ok, today),
             "near_lows": lambda: plan_near_lows(site, rows, c, by_ticker, state_ok, today),
             "records": lambda: plan_records(site, rows, c, by_ticker, state_ok, today),
             "polymarket": lambda: plan_polymarket(site, rows, c, by_ticker, state_ok, today),
             "filing8k": lambda: plan_filing8k(site, rows, target or {}, today),
             "fund13f_for": lambda: plan_fund13f_for(site, rows, by_ticker, target or {}),
             "insider_for": lambda: plan_insider_for(site, rows, by_ticker, target or {}, today),
             "official_for": lambda: plan_official_for(site, rows, by_ticker, target or {}, today),
             "stake_for": lambda: plan_stake_for(site, rows, by_ticker, target or {}, today),
             "f144_for": lambda: plan_f144_for(site, rows, by_ticker, target or {}, today),
             "short_for": lambda: plan_short_for(site, rows, by_ticker, target or {}, today),
             "news_for": lambda: plan_news_for(site, rows, by_ticker, target or {}, today)}.get(kind, lambda: registered_plan(kind, site, rows, c, by_ticker, state_ok, today))()
        if p:
            plans.append(p)
        else:
            print(f"{kind}: nothing to post")

    if plan_only:                          # the workflow's cheap first pass: is there anything to post at all?
        for p in plans:
            print(f"planned: {p['kind']} " + " ".join("$" + t for t in p["cashtags"]))
        return [p["kind"] for p in plans]
    made = []
    for p in plans:
        e0 = p["items"][0][0] if p.get("items") else None
        tags = p.get("tags") or H.pick(kind_tag(p["kind"]), e0, key=f"{p['kind']}:" + ",".join(p["cashtags"]))
        try:
            post = write(p["kind"], p["task"], p["cashtags"], tags, polish=c.get("polish", True), allowed=p.get("allowed"), must=p.get("must"),
                         forbid=p.get("forbid"), lines=p.get("lines", False))
        except Exception as err:
            post = None
            if p.get("fallback"):                  # the model is down: a plain rule-based post with the same facts
                try:
                    post = clean(p["fallback"], p["cashtags"], tags, allowed=p.get("allowed"), must=p.get("must"), forbid=p.get("forbid"),
                                 lines=p.get("lines", False))
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
        filing = (p.get("source_reply") or (f"The Form 4: {p['insider_url']}" if p.get("insider_url")
                                            else f"The 13F: {p['fund_url']}" if p.get("fund_url") else ""))
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
        for rel in (p.get("hub_images") or [])[:max(0, 4 - len(images))]:   # a picture the hub publishes (a map, a GIF)
            data = hub_bytes(site, rel)
            if data:
                name = f"{p['kind']}-{today.isoformat()}-{os.path.basename(rel)}"
                open(os.path.join(xdir, name), "wb").write(data)
                images.append(name)
        pend_path = os.path.join(xdir, "pending.json")
        pending = json.load(open(pend_path, encoding="utf-8")) if os.path.exists(pend_path) else []
        pending.append({"cik": e0["cik"] if e0 else None, "end": e0["end"] if e0 else None, "label": f"{p['kind']}: " + " ".join(p["cashtags"]),
                        "posts": [post] + list(p.get("thread") or []) + [x for x in (filing, reply) if x], "written_by": "model", "images": images,
                        **({"draft": True} if draft else {})})
        json.dump(pending, open(pend_path, "w", encoding="utf-8"), ensure_ascii=False)
        stamp = now.isoformat()
        if not p.get("manual"):            # one chosen row (hub ✦ X) leaves the scheduled format's daily turn alone
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
