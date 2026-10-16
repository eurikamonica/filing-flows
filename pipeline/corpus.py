"""Training examples for the local fallback model (pipeline/local_model.py), built from the site's own data on every
run of .github/workflows/train-local-model.yml.

An example pairs the exact prompt the pipeline sends for a post (compacted by local_model.compact) with a target post
written by fixed rules from the same facts, in several hand-written phrasings. No model output is used. Every target is
checked like a real post (length, cashtags, hashtags, finished sentences, no advice) and against its facts (each number
in the post appears in the input), so the model only ever sees posts that would be accepted.

Breadth: every company quarter, 13F holder change, Form 4 purchase and 8-K the scans add. Depth: targets carry two or
three facts with their context (growth, margin, earnings, the driver; who, how much, when bought, when filed).

    python -m pipeline.corpus --site _site --site-url https://filing-flows.com --known model/corpus-ids.txt --out new.jsonl
"""
import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import re
import sys

from . import engage, events, local_model as L, notify, social, tweet


def _h(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _pick(key, options, n=2):
    """n of the phrasings, chosen by the key (stable from run to run)."""
    k = int(_h(key), 16)
    return [options[(k + i) % len(options)] for i in range(min(n, len(options)))]


def example(kind, key, messages, target, check, cashtags, tags, cik):
    """A checked example, or None when the target would not pass as a post."""
    prompt = L.compact(messages)
    try:
        if check == "engage":
            target = engage.clean(target, cashtags, tags)
        else:
            target = tweet.clean(target, cashtags[0] if cashtags else "", tags, social.xlen)
    except ValueError:
        return None
    if L.unsupported(target, prompt):
        return None
    return {"id": _h(kind, key, target), "kind": kind, "cik": cik, "prompt": prompt, "target": target, "check": check,
            "cashtags": cashtags, "tags": tags, "created": dt.date.today().isoformat()}


# ------------------------------------------------------------------ earnings (owner "Post to X", scan threads)
def _m(v):
    return "—" if v is None else f"${v / 1e9:.1f}B" if abs(v) >= 0.95e9 else f"${v / 1e6:.0f}M" if abs(v) >= 0.95e6 else f"${v / 1e3:.0f}K"


def _driver(q, limit=120):
    """A short sentence from the fixed-rule analysis that explains the quarter (it is in the prompt's facts)."""
    for para in q.get("analysis") or []:
        for s in re.split(r"(?<=[.])\s+(?=[A-Z])", para):
            if 30 <= len(s) <= limit and re.search(r"\d", s) and not s.startswith("Revenue was"):
                return s.rstrip(".") + "."
    return ""


def earnings_examples(site, cfg, known, today, limit=None):
    tags = [t for t in [cfg.get("headline_tag", "#earnings")] + list(cfg.get("hashtags") or []) if t]
    out = []
    files = sorted(glob.glob(os.path.join(site.src, "data", "c", "*.json")))
    for path in files[:limit] if limit else files:
        try:
            c = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        tk = ((c.get("profile") or {}).get("tickers") or [""])[0].replace("-", ".")
        if not tk:
            continue
        for q in (c.get("quarters") or [])[:2]:
            h = q.get("headline") or {}
            if h.get("revenue") is None or not q.get("filed"):
                continue
            key = f"{c['profile']['cik']}:{q['end']}"
            if _h("post", key) in known:
                continue
            # the reader's "today": up to nine days after filing, so the model learns when BREAKING is true
            lag = int(_h("lag", key), 16) % 10
            day = dt.date.fromisoformat(q["filed"][:10]) + dt.timedelta(days=lag)
            lead = ("BREAKING" if lag <= 1 else "JUST FILED") if lag <= 2 else ("EARNINGS" if q.get("form") == "8-K" else f"NEW {q.get('form')}")
            msgs = tweet.post_messages(c, q, tk, tags, kind="post", thread=True, filing=False, today=day)
            rev, ni, label = _m(h.get("revenue")), _m(h.get("ni")), q.get("label")
            yoy = f"{h['yoy']:+.0f}% Y/Y" if h.get("yoy") is not None else ""
            om = f"{h['om']:.1f}%" if h.get("om") is not None else None
            drv = _driver(q)
            T = " ".join(tags)
            phr = [
                lambda: f"{lead} · ${tk} {label}: revenue {rev}{f' ({yoy})' if yoy else ''}" + (f", operating margin {om}" if om else "")
                        + f", net earnings {ni}. {drv} Full breakdown ↓ {T}",
                lambda: f"{lead} · ${tk} {label}: {rev} of revenue{f', {yoy}' if yoy else ''}. Net earnings {ni}"
                        + (f" on a {om} operating margin" if om else "") + f". Charts + what drove it ↓ {T}",
                lambda: f"{lead} · ${tk} {label} — net earnings {ni} on {rev} of revenue" + (f" ({yoy})" if yoy else "")
                        + f". {drv} Full breakdown ↓ {T}",
                lambda: f"{lead} · ${tk} {label}: {drv or f'revenue {rev}.'} Revenue {rev}" + (f", operating margin {om}" if om else "")
                        + f". Full breakdown ↓ {T}",
            ]
            for i, f in enumerate(_pick(key, phr)):
                text = re.sub(r"\s+", " ", f()).replace(" .", ".").replace("..", ".")
                if social.xlen(text) > 270 and drv:
                    text = re.sub(r"\s+", " ", text.replace(drv + " ", ""))
                ex = example("post", key, msgs, text, "tweet", [tk], tags, c["profile"]["cik"])
                if ex:
                    ex["src"] = _h("post", key)
                    out.append(ex)
    return out


# ------------------------------------------------------------------ 13F holders (owner "who bought it")
def holders_examples(site, site_url, known, tickers):
    out = []
    for c in tickers:
        tk = ((c.get("profile") or {}).get("tickers") or [""])[0]
        if not tk:
            continue
        th = tweet.holders_thread(tk, site_url, c["profile"]["cik"])
        if not th:
            continue
        key = f"{tk}:{th['period']}:{th['filed']}"
        if _h("post_holders", key) in known:
            continue
        q = (c.get("quarters") or [{}])[0]
        try:
            msgs = tweet.post_messages(c, q, tk, tweet.HOLDER_TAGS, kind="post_holders", site_url=site_url, thread=True)
        except Exception:
            continue
        P = th["pieces"]
        T, lead, t2 = " ".join(tweet.HOLDER_TAGS), th["lead"], P["tk"]
        b = [f"{w} {m} (filed {d})" for w, m, d in P["buys"]]
        s = [f"{w} {m} (filed {d})" for w, m, d in P["sells"]]
        phr = [th["post"] + " " + T]
        if b:
            phr.append(f"{lead}: 13F filings for the quarter ended {P['period']} show {P['n_add']} funds adding ${t2} and {P['n_cut']} cutting. "
                       f"Biggest buyer: {b[0]}." + (f" Biggest seller: {s[0]}." if s else "") + f" Who's right? {T}")
        if s:
            phr.append(f"{lead}: ${t2} 13F moves, quarter ended {P['period']}: {s[0]}" + (f", while {b[0]}" if b else "")
                       + f". {P['n_add']} added, {P['n_cut']} cut. Which side do you take? {T}")
        for text in _pick(key, phr):
            ex = example("post_holders", key, msgs, text, "tweet", [tk.replace("-", ".")], tweet.HOLDER_TAGS, c["profile"]["cik"])
            if ex:
                ex["src"] = _h("post_holders", key)
                out.append(ex)
    return out


# ------------------------------------------------------------------ Form 4 purchases
def insider_examples(site, rows, by_ticker, insiders, known):
    out = []
    clusters = {a["ticker"]: a for a in insiders.get("summary", []) if a.get("cluster")}
    for t in insiders.get("latest", []):
        tk = (t.get("ticker") or "").upper().replace("-", ".")
        if t.get("code") != "P" or tk not in by_ticker or not t.get("price") or not t.get("shares"):
            continue
        key = f"{t.get('accession')}:{t.get('date')}:{t.get('shares')}"
        if _h("insider", key) in known:
            continue
        e = by_ticker[tk]
        try:
            cj, fq = engage.figures(site, e)
        except Exception:
            continue
        if not fq:
            continue
        day = dt.date.fromisoformat((t.get("filed") or t["date"])[:10]) + dt.timedelta(days=int(_h("lag", key), 16) % 4)
        p = engage.insider_plan(t, tk, e, cj, fq, clusters.get(tk), day)
        tags = p["tags"]
        msgs = engage.messages("insider", p["task"], [tk], tags)
        who = t.get("title") if t.get("title") and len(t["title"]) <= 24 else t["role"]
        lead = "JUST FILED: " if p["task"].find("JUST FILED") >= 0 else ""
        filed = f", Form 4 filed {t['filed']}" if t.get("filed") else ""
        T = " ".join(tags)
        phr = [p["fallback"] + " " + T,
               f"{lead}Insider buy at ${tk}: {t['insider'].title()} ({who}) bought {t['shares']:,.0f} shares at ${t['price']:,.2f} "
               f"on {t['date']}{filed}. How do you read it? {T}",
               f"{lead}${tk} {who} {t['insider'].title()} put {engage.money(t['value'])} into the stock on {t['date']}: "
               f"{t['shares']:,.0f} shares at ${t['price']:,.2f}{filed}. Signal or noise? {T}"]
        for text in _pick(key, phr):
            ex = example("insider", key, msgs, text, "engage", [tk], tags, e["cik"])
            if ex:
                ex["src"] = _h("insider", key)
                out.append(ex)
    return out


# ------------------------------------------------------------------ 8-K current reports
def event_examples(site, rows, known, today, limit=30):
    out, n = [], 0
    since = (today - dt.timedelta(days=21)).isoformat()
    for e in sorted((r for r in rows if r.get("ticker")), key=lambda r: r.get("filed") or "", reverse=True):
        if n >= limit:
            break
        try:
            fs = events.recent_8ks(e["cik"], since)
        except (Exception, SystemExit):
            continue
        for f in fs[:2]:
            key = f["accn"]
            if _h("event8k", key) in known:
                continue
            n += 1
            fresh = f["filed"] >= (today - dt.timedelta(days=2)).isoformat()
            try:
                p = engage.event_plan(site, e, dict(f), require_deal=False, fresh=fresh)
            except (Exception, SystemExit):
                p = None
            if not p:
                continue
            ev, tags, tk = p["event"], p["tags"], e["ticker"]
            msgs = engage.messages("event8k", p["task"], [tk], tags)
            T = " ".join(tags)
            filed_on = dt.date.fromisoformat(ev["filed"])
            day = f"{filed_on:%b} {filed_on.day}"
            lead = "BREAKING: " if "BREAKING" in p["fallback"][:12] else "JUST FILED: " if "JUST FILED" in p["fallback"][:14] else ""
            label = engage.event_label(ev["code"], ev["quote"])
            first = engage.first_sentence(ev["quote"], limit=150)
            phr = [p["fallback"] + " " + T]
            if len(first) >= 40:
                phr.append(f"{lead}${tk} filed an 8-K on {day} (Item {ev['code']}, {label}): “{first}{'' if first.endswith('…') else '.'}” What do you make of it? {T}")
            for text in _pick(key, phr):
                ex = example("event8k", key, msgs, text, "engage", [tk], tags, e["cik"])
                if ex:
                    ex["src"] = _h("event8k", key)
                    out.append(ex)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--site", default="_site", help="the built site (with data/)")
    ap.add_argument("--site-url", default=os.environ.get("X_SITE_URL") or "", help="the published site, for 13F holder files")
    ap.add_argument("--insiders", default="disclosures/docs/data/market/insiders.json")
    ap.add_argument("--known", default="", help="source keys already in the corpus (one per line)")
    ap.add_argument("--out", default="new.jsonl")
    ap.add_argument("--holders", type=int, default=120, help="companies whose 13F holders are read this run")
    ap.add_argument("--events", type=int, default=30, help="8-Ks read from SEC this run")
    args = ap.parse_args()
    known = set(open(args.known).read().split()) if args.known and os.path.exists(args.known) else set()
    site = notify.Site(args.site)
    cfg = social.load_cfg("config/x.json")
    ix = site.json("index.json")
    rows = ix["companies"] if isinstance(ix, dict) else ix
    for e in rows:
        if e.get("ticker"):
            e["ticker"] = e["ticker"].upper().replace("-", ".")
    by_ticker = {}
    for e in rows:
        if e.get("ticker") and (e["ticker"] not in by_ticker or (e.get("filed") or "") > (by_ticker[e["ticker"]].get("filed") or "")):
            by_ticker[e["ticker"]] = e
    today = dt.date.today()
    out = []
    counts = {}

    def add(kind, xs):
        out.extend(xs)
        counts[kind] = len(xs)

    add("post", earnings_examples(site, cfg, known, today))
    try:
        add("insider", insider_examples(site, rows, by_ticker, json.load(open(args.insiders, encoding="utf-8")), known))
    except (OSError, ValueError) as err:
        print(f"::warning::insider examples skipped ({err})")
    if args.site_url and args.holders:
        # a different slice of companies each day: breadth over time without reading every holder file every run
        start = (today.toordinal() * args.holders) % max(1, len(rows))
        pick = (rows[start:] + rows[:start])[:args.holders]
        cs = []
        for e in pick:
            try:
                cs.append(site.json(f"c/{e['cik']}.json"))
            except Exception:
                pass
        add("post_holders", holders_examples(site, args.site_url, known, cs))
    if args.events:
        add("event8k", event_examples(site, rows, known, today, args.events))
    with open(args.out, "w", encoding="utf-8") as f:
        for ex in out:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print("new examples: " + ", ".join(f"{k} {v}" for k, v in counts.items()) + f" → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
