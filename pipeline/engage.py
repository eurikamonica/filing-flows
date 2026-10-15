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

from . import notify, quotes as Q, reddit, social, tweet

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


def cfg():
    out = dict(DEFAULTS)
    try:
        out.update(json.load(open(CFG, encoding="utf-8")))
    except FileNotFoundError:
        pass
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
def clean(post, cashtags, tags, limit=255):
    post = re.sub(r"\s*\n+\s*", " ", post.strip().strip('"“”')).strip()
    missing = [t for t in cashtags if f"${t.upper()}" not in post.upper()]
    if missing:
        raise ValueError("cashtag missing: " + " ".join(missing))
    if not all(t.lower() in post.lower() for t in tags):
        post = re.sub(r"(\s*#\w+)+\s*$", "", post).rstrip() + " " + " ".join(tags)
    if tweet.ADVICE.search(re.sub(r"#\w+", "", post)) or "!" in post:
        raise ValueError("advice / hype wording or exclamation mark")
    if social.xlen(post) > limit:
        raise ValueError(f"too long ({social.xlen(post)})")
    return post


def write(kind, task, cashtags, tags, polish=True):
    msgs = [{"role": "system", "content": guide()},
            {"role": "user", "content": f"FORMAT: {kind}\n\n{task}\n\nCashtags that must appear: " + " ".join(f"${t}" for t in cashtags)
             + "\nHashtags to end with, in this order: " + " ".join(tags) + "\n\nWrite the post now."}]
    draft = tweet.chat(msgs)
    if polish:
        msgs += [{"role": "assistant", "content": draft},
                 {"role": "user", "content": "Polish pass: keep every number, cashtag, option and hashtag exactly; sharper, more specific "
                                             "opening; cut filler; under 250 characters. Output only the polished post."}]
        draft = tweet.chat(msgs)
    try:
        return clean(draft, cashtags, tags)
    except ValueError as why:
        msgs += [{"role": "assistant", "content": draft},
                 {"role": "user", "content": f"Rewrite: {why}. Under 240 characters, every cashtag present, ending with the hashtags."}]
        return clean(tweet.chat(msgs), cashtags, tags)


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
    s = f"${a / 1e12:.2f}T" if a >= 1e12 else f"${a / 1e9:.1f}B" if a >= 1e9 else f"${a / 1e6:.0f}M"
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
        big = (q.get("mcap") or 0) >= m["min_mcap"] if q.get("mcap") else (e.get("revenue") or 0) >= m["min_quarter_revenue"]
        if big and abs(q["chg_pct"]) >= m["min_move_pct"]:
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
        task = (f"PRICE MOVE (delayed quote, {stamp}): {quote_line(e['ticker'], q, e)}.\n\n"
                f"Latest filing figures (the only other numbers you may use):\n{tweet.headline_lines(cj, fq, e['ticker'])}{chatter}\n\n"
                "The cause of today's move is NOT in these inputs: do not guess or imply one; ask the audience.")
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
        return {"kind": kind, "task": task, "cashtags": cashtags, "items": items, "mover": e["ticker"]}
    return None


# ------------------------------------------------------------------ main
def make(kinds, site, site_url, media, assets, dry_run=False, force=False):
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
             "peers": lambda: plan_mover("peers", site, rows, c, live, state_ok, trends)}.get(kind, lambda: None)()
        if p:
            plans.append(p)
        else:
            print(f"{kind}: nothing to post")

    tags = [t for t in c["hashtags"] if t]
    made = []
    for p in plans:
        try:
            post = write(p["kind"], p["task"], p["cashtags"], tags, polish=c.get("polish", True))
        except Exception as err:
            print(f"::warning::{p['kind']}: no post ({str(err)[:160]})")
            continue
        e0, cj0, q0 = p["items"][0] if p["items"] else (None, None, None)
        reply = ("Charts: " + "; ".join(f"${e['ticker']} {q['label']} ({q.get('form')} filed {q.get('filed')})" for e, _, q in p["items"])
                 + f". Read automatically from the filings; not investment advice. {site_url}/#c-{e0['cik']}") if e0 else ""
        print(f"[{p['kind']}] {post}" + (f"\n   ↳ {reply}" if reply else ""))
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
                        "posts": [post] + ([reply] if reply else []), "written_by": "model", "images": images})
        json.dump(pending, open(pend_path, "w", encoding="utf-8"), ensure_ascii=False)
        stamp = now.isoformat()
        state[f"kind:{p['kind']}"] = stamp
        for t in p["cashtags"]:
            state[f"{p['kind']}:{t}"] = stamp
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
    args = ap.parse_args()
    kinds = [k.strip() for k in args.kinds.split(",") if k.strip()]
    site = notify.Site(args.site)
    site_url = (args.site_url or os.environ.get("SITE_URL") or (args.site if site.remote else "")).rstrip("/")
    with notify.Assets(site, enabled=not args.dry_run) as assets:
        made = make(kinds, site, site_url, args.media, assets, dry_run=args.dry_run, force=args.force)
    if made and not args.dry_run and os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice::engagement post(s) written for Buffer: {'; '.join(m.split(':')[0] for m in made)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
