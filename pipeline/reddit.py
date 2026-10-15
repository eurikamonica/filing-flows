"""Reddit trends -> discussion posts for X (queued in Buffer with the company's chart).

    python -m pipeline.reddit --site https://filing-flows.com/ --media media --top 2
    python -m pipeline.reddit --site https://filing-flows.com/ --dry-run        # print the trend table and the posts

1. Reads the hot threads of a few investing subreddits (config/reddit.json). With REDDIT_CLIENT_ID /
   REDDIT_CLIENT_SECRET (a free "script" app at reddit.com/prefs/apps) it uses the OAuth API; without them the public
   JSON listing, which is rate-limited but enough for a daily run.
2. Finds the companies people are talking about: cashtags ($NVDA) and bare tickers in titles, matched against the
   companies on the site (so every pick has a chart). Score = upvotes + 2 x comments, over the last `hours`.
3. For the top companies not posted about recently (media/x/reddit-state.json), GitHub Models writes one discussion
   post from config/reddit-guide.md (hook, one fact, a 2-3 option question) and the chart PNG is drawn; both go into
   media/x/pending.json, which pipeline/buffer.py queues in Buffer (scripts/publish-media.sh in the workflow).
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time

import requests

from . import notify, social, tweet

CFG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "reddit.json")
GUIDE = os.path.join(os.path.dirname(CFG), "reddit-guide.md")
UA = os.environ.get("REDDIT_USER_AGENT") or "FilingFlows/1.0 (earnings charts; by u/filingflows)"
DEFAULTS = {
    "subreddits": ["stocks", "wallstreetbets", "investing", "ValueInvesting", "StockMarket", "options"],
    "hours": 36, "per_sub": 60, "top": 2, "min_score": 150, "min_threads": 1, "cooldown_days": 7,
    "hashtags": ["#stocks", "#earnings"],
    "ignore": ["A", "I", "AI", "ALL", "AM", "AN", "ARE", "AT", "BE", "BIG", "BY", "CAN", "CEO", "CFO", "DD", "DO", "EPS", "ETF",
               "EV", "FED", "FOMC", "FOR", "GDP", "GO", "HAS", "IMO", "IN", "IPO", "IS", "IT", "LOL", "ME", "MY", "NEW", "NO",
               "NOW", "OF", "ON", "OP", "OR", "PE", "PM", "PT", "RE", "SEC", "SO", "TL", "DR", "TO", "UK", "UP", "US", "USA",
               "WSB", "YOLO", "YTD", "ATH", "CPI", "PPI", "Q", "QQQ", "SPY", "VOO", "VTI", "IRA", "ROTH", "ER", "DCA"],
}


def cfg():
    out = dict(DEFAULTS)
    try:
        out.update(json.load(open(CFG, encoding="utf-8")))
    except FileNotFoundError:
        pass
    return out


# ------------------------------------------------------------------ reddit
def _token():
    cid, sec = os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
    if not (cid and sec):
        return None
    r = requests.post("https://www.reddit.com/api/v1/access_token", auth=(cid, sec), data={"grant_type": "client_credentials"},
                      headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def hot(sub, limit, token=None):
    """The subreddit's hot listing as a list of {title, score, comments, created, url, sub}."""
    if token:
        url, headers = f"https://oauth.reddit.com/r/{sub}/hot", {"Authorization": f"Bearer {token}", "User-Agent": UA}
    else:
        url, headers = f"https://www.reddit.com/r/{sub}/hot.json", {"User-Agent": UA}
    for attempt in range(3):
        r = requests.get(url, params={"limit": min(limit, 100), "raw_json": 1}, headers=headers, timeout=30)
        if r.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        r.raise_for_status()
        break
    else:
        raise RuntimeError(f"r/{sub}: rate limited")
    out = []
    for ch in r.json().get("data", {}).get("children", []):
        d = ch.get("data") or {}
        if d.get("stickied") or d.get("pinned"):
            continue
        out.append({"sub": sub, "title": d.get("title") or "", "score": int(d.get("score") or 0), "comments": int(d.get("num_comments") or 0),
                    "created": float(d.get("created_utc") or 0), "url": "https://www.reddit.com" + (d.get("permalink") or ""),
                    "flair": d.get("link_flair_text") or "", "text": (d.get("selftext") or "")[:400]})
    return out


def tickers_in(title, known, ignore):
    """Tickers a title names: $CASHTAGS always; bare upper-case words only when they are a known ticker and not a word."""
    found = set()
    for m in re.finditer(r"\$([A-Za-z]{1,5})\b", title):
        t = m.group(1).upper()
        if t in known:
            found.add(t)
    for m in re.finditer(r"\b([A-Z]{2,5})\b", title):
        t = m.group(1)
        if t in known and t not in ignore:
            found.add(t)
    return found


def trending(threads, known, c):
    """[{ticker, score, threads:[...]}] sorted by score, over threads newer than c['hours']."""
    since = time.time() - c["hours"] * 3600
    agg = {}
    ignore = set(c["ignore"])
    for t in threads:
        if t["created"] < since:
            continue
        for tick in tickers_in(t["title"], known, ignore):
            a = agg.setdefault(tick, {"ticker": tick, "score": 0, "threads": []})
            a["score"] += t["score"] + 2 * t["comments"]
            a["threads"].append(t)
    rows = [a for a in agg.values() if a["score"] >= c["min_score"] and len(a["threads"]) >= c["min_threads"]]
    for a in rows:
        a["threads"].sort(key=lambda t: -(t["score"] + 2 * t["comments"]))
    return sorted(rows, key=lambda a: -a["score"])


# ------------------------------------------------------------------ the post
def guide():
    try:
        return open(GUIDE, encoding="utf-8").read()
    except FileNotFoundError:
        return "Write one neutral discussion post for X about the trending company, under 260 characters, ending with the hashtags."


def clean(post, ticker, tags, limit=260):
    post = re.sub(r"\s*\n+\s*", " ", post.strip().strip('"“”')).strip()
    if f"${ticker.upper()}" not in post.upper():
        raise ValueError("cashtag missing")
    if not all(t.lower() in post.lower() for t in tags):
        post = re.sub(r"(\s*#\w+)+\s*$", "", post).rstrip() + " " + " ".join(tags)
    if tweet.ADVICE.search(re.sub(r"#\w+", "", post)):
        raise ValueError("advice / hype wording")
    if social.xlen(post) > limit:
        raise ValueError(f"too long ({social.xlen(post)})")
    return post


def compose(c_json, q, trend, tags):
    ticker = trend["ticker"]
    lines = [f"- r/{t['sub']}: \"{t['title']}\" ({t['score']} points, {t['comments']} comments)" for t in trend["threads"][:5]]
    task = (f"Reddit threads that made {ticker} trend in the last day or so:\n" + "\n".join(lines)
            + "\n\nHeadline figures from the latest filing (the only numbers you may use):\n" + tweet.headline_lines(c_json, q, ticker)
            + "\n\nHashtags to end with, in this order: " + " ".join(tags) + "\n\nWrite the post now.")
    msgs = [{"role": "system", "content": guide()}, {"role": "user", "content": task}]
    draft = tweet.chat(msgs)
    try:
        return clean(draft, ticker, tags)
    except ValueError as why:
        msgs += [{"role": "assistant", "content": draft},
                 {"role": "user", "content": f"Rewrite: {why}. Keep the cashtag in the first sentence, under 240 characters, ending with the hashtags."}]
        return clean(tweet.chat(msgs), ticker, tags)


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--site", default=os.environ.get("SITE_URL") or "_site", help="published site URL (or the built folder)")
    ap.add_argument("--site-url", default=None)
    ap.add_argument("--media", default=os.environ.get("MEDIA_DIR", "media"))
    ap.add_argument("--top", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true", help="print the trends and the posts; draw and write nothing")
    args = ap.parse_args()
    c = cfg()
    top = args.top or c["top"]
    site = notify.Site(args.site)
    site_url = (args.site_url or os.environ.get("SITE_URL") or (args.site if site.remote else "")).rstrip("/")

    ix = site.json("index.json")
    rows = ix["companies"] if isinstance(ix, dict) else ix
    by_ticker = {}
    for e in rows:
        t = (e.get("ticker") or "").upper().replace("-", ".")
        if t and (t not in by_ticker or (e.get("filed") or "") > (by_ticker[t].get("filed") or "")):
            by_ticker[t] = e

    token = None
    try:
        token = _token()
    except Exception as err:
        print(f"::warning::Reddit OAuth not used ({err}); public listing instead")
    threads = []
    for sub in c["subreddits"]:
        try:
            threads += hot(sub, c["per_sub"], token)
        except Exception as err:
            print(f"::warning::r/{sub} not read ({err})")
        if not token:
            time.sleep(2)
    trends = trending(threads, set(by_ticker), c)
    print(f"{len(threads)} threads read; {len(trends)} companies on the site trending")
    for a in trends[:15]:
        print(f"  {a['ticker']:6} score {a['score']:6}  {len(a['threads'])} threads  e.g. {a['threads'][0]['title'][:80]!r}")
    if not trends:
        return 0

    xdir = os.path.join(args.media, "x")
    state_path = os.path.join(xdir, "reddit-state.json")
    state = json.load(open(state_path, encoding="utf-8")) if os.path.exists(state_path) else {}
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=c["cooldown_days"])).isoformat()
    picks = [a for a in trends if (state.get(a["ticker"]) or "") < cutoff][:top]
    if not picks:
        print("every trending company was posted about within the cooldown")
        return 0

    x_cfg = social.load_cfg("config/x.json")
    tags = [t for t in c["hashtags"] if t]
    made = 0
    with notify.Assets(site, enabled=not args.dry_run) as assets:
        for a in picks:
            e0 = by_ticker[a["ticker"]]
            c_json, q = notify.find_quarter(site, e0["cik"], e0["end"], "q")
            if not q:
                continue
            e = {"cik": int(e0["cik"]), "end": q["end"], "form": q.get("form"), "ticker": a["ticker"], "name": c_json["profile"]["name"]}
            try:
                post = compose(c_json, q, a, tags)
            except Exception as err:
                print(f"::warning::no post for {a['ticker']} ({str(err)[:160]})")
                continue
            reply = (f"Chart: {c_json['profile']['name']} {q['label']} from revenue to profit and cash, read from the {q.get('form')} "
                     f"filed {q.get('filed')}. Not investment advice. {site_url}/#c-{e['cik']}")
            print(f"{a['ticker']}: {post}\n   ↳ {reply}")
            if args.dry_run:
                continue
            png = assets.image(e, c_json, q, "std", "png")
            name = social.image_names(e, q, 1)[0].replace("-1-chart", "-reddit-chart")
            os.makedirs(xdir, exist_ok=True)
            images = []
            if png:
                open(os.path.join(xdir, name), "wb").write(png)
                images = [name]
            pend_path = os.path.join(xdir, "pending.json")
            pending = json.load(open(pend_path, encoding="utf-8")) if os.path.exists(pend_path) else []
            pending.append({"cik": e["cik"], "end": e["end"], "label": f"{a['ticker']} {q['label']} (reddit trend)",
                            "posts": [post, reply], "written_by": "model", "images": images})
            json.dump(pending, open(pend_path, "w", encoding="utf-8"), ensure_ascii=False)
            state[a["ticker"]] = dt.datetime.now(dt.timezone.utc).isoformat()
            json.dump(state, open(state_path, "w", encoding="utf-8"))
            made += 1
    if made and os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice::{made} Reddit-trend post(s) written for Buffer: " + ", ".join(a["ticker"] for a in picks[:made]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
