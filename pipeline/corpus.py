"""Training examples for the local fallback model (pipeline/local_model.py), built from the site's own data on every
run of .github/workflows/train-local-model.yml.

An example pairs the exact prompt the pipeline sends for a post (compacted by local_model.compact) with a target post
written by fixed rules from the same facts, in several hand-written phrasings. No model output is used. Every target is
checked like a real post (length, cashtags, hashtags, finished sentences, no advice) and against its facts (each number
in the post appears in the input), so the model only ever sees posts that would be accepted.

Breadth: every company quarter, 13F holder change, Form 4 purchase and sale, 8-K, and rows of the hub's 13D / 13G, Form 144,
short interest and officials' trades (House and Senate) tables the scans add. Depth: targets carry two or
three facts with their context (growth, margin, earnings, the driver; who, how much, when bought, when filed).

Market posts (market_examples): the formats that travel on X — "$A or $B?", same Hold rating with very different
price-target upside, "$RKLB $150 → $50", a stock's setup in bullets, the day's new 52-week and all-time highs and lows,
quality names near their lows, Polymarket's earnings odds, the trending stock (never a post about Reddit), the smart-money
lists — planned from the published hub files by the same engage.plan_* functions the posting workflow uses, many plans a
day per kind (each next plan without the names already used), every rule-written phrasing of a plan a target.

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

VERSION = 2          # bump when targets or prompts change: older examples are dropped and rebuilt (2: −$44M, no shells)


def _h(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _pick(key, options, n=2):
    """n of the phrasings, chosen by the key (stable from run to run)."""
    k = int(_h(key), 16)
    return [options[(k + i) % len(options)] for i in range(min(n, len(options)))]


def example(kind, key, messages, target, check, cashtags, tags, cik, allowed=None, lines=False, forbid=None, must=None, hold=None):
    """A checked example, or None when the target would not pass as a post. allowed / lines / forbid / must: the plan's
    extra checks (other cashtags a list may name, line breaks kept, wording it may not or must use), kept on the example
    so the evaluation grades a generated post the same way; hold: the key that decides the held-out share (default: cik)."""
    prompt = L.compact(messages)
    try:
        if check == "engage":
            target = engage.clean(target, cashtags, tags, allowed=allowed, must=must, forbid=forbid, lines=lines)
        else:
            target = tweet.clean(target, cashtags[0] if cashtags else "", tags, social.xlen)
    except ValueError:
        return None
    if L.unsupported(target, prompt):
        return None
    ex = {"id": _h(kind, key, target), "v": VERSION, "kind": kind, "cik": cik, "prompt": prompt, "target": target, "check": check,
          "cashtags": cashtags, "tags": tags, "created": dt.date.today().isoformat()}
    extra = {"allowed": [t for t in allowed or [] if t not in cashtags] or None, "lines": bool(lines) or None,
             "forbid": list(forbid) if forbid else None, "must": list(must) if must else None, "hold": hold}
    ex.update({k: v for k, v in extra.items() if v})
    return ex


# ------------------------------------------------------------------ earnings (owner "Post to X", scan threads)
def _m(v):
    return tweet.usd(v)


def _driver(q, limit=120):
    """A short sentence from the fixed-rule analysis that explains the quarter (it is in the prompt's facts)."""
    for para in q.get("analysis") or []:
        for s in re.split(r"(?<=[.])\s+(?=[A-Z])", para):
            if 30 <= len(s) <= limit and re.search(r"\d", s) and not s.startswith("Revenue was"):
                return s.rstrip(".") + "."
    return ""


def earnings_examples(site, cfg, known, today, limit=None):
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
            if (h.get("revenue") or 0) < 5e6 or not q.get("filed") or abs(h.get("yoy") or 0) > 500:
                continue                               # shells and broken quarters: never posted, not worth learning
            key = f"{c['profile']['cik']}:{q['end']}"
            if _h("post", key) in known:
                continue
            # the reader's "today": up to nine days after filing, so the model learns when BREAKING is true
            lag = int(_h("lag", key), 16) % 10
            day = dt.date.fromisoformat(q["filed"][:10]) + dt.timedelta(days=lag)
            lead = ("BREAKING" if lag <= 1 else "JUST FILED") if lag <= 2 else ("EARNINGS" if q.get("form") == "8-K" else f"NEW {q.get('form')}")
            tags = tweet.post_tags(c, q, cfg, tk, "post")             # as the posting pipeline picks them
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
        tags = tweet.post_tags(c, q, {}, tk, "post_holders")
        try:
            msgs = tweet.post_messages(c, q, tk, tags, kind="post_holders", site_url=site_url, thread=True)
        except Exception:
            continue
        P = th["pieces"]
        T, lead, t2 = " ".join(tags), th["lead"], P["tk"]
        b = [f"{w} {m} (filed {d})" for w, m, d in P["buys"]]
        s = [f"{w} {m} (filed {d})" for w, m, d in P["sells"]]
        phr = [th["post"] + " " + T]
        if b:
            phr.append(f"{lead}: 13F filings for the quarter ended {P['period']} show {P['n_add']} funds adding ${t2} and {P['n_cut']} cutting. "
                       f"Biggest buyer: {b[0]}." + (f" Biggest seller: {s[0]}." if s else "") + f" Who's right? {T}")
        if s:
            phr.append(f"{lead}: ${t2} 13F moves, quarter ended {P['period']}: {s[0]}" + (f", while {b[0]}" if b else "")
                       + f". {P['n_add']} added, {P['n_cut']} cut. Which side do you take? {T}")
        if len(b) >= 2:
            phr.append(f"{lead}: who bought ${t2} in the quarter ended {P['period']}? {b[0]}; {b[1]}. "
                       f"{P['n_add']} funds added in all, {P['n_cut']} cut. Conviction or crowding? {T}")
        if len(s) >= 2:
            phr.append(f"{lead}: the biggest ${t2} sellers, quarter ended {P['period']} (13F): {s[0]}; {s[1]}. "
                       f"{P['n_cut']} cut, {P['n_add']} added. Who's right? {T}")
        for text in _pick(key, phr, 3):                  # 13F posts were the rarest kind: three phrasings each
            ex = example("post_holders", key, msgs, text, "tweet", [tk.replace("-", ".")], tags, c["profile"]["cik"])
            if ex:
                ex["src"] = _h("post_holders", key)
                out.append(ex)
    return out


# ------------------------------------------------------------------ Form 4 purchases
def insider_examples(site, rows, by_ticker, insiders, known, trades=None):
    """Form 4 posts: every purchase and sale in the collector's trade file (cache/insiders/trades.json.gz, the last ~120
    days) and the published latest ones, sales written as "sold" with their 10b5-1 plan, companies without charts on the
    site as text-only posts (the owner's ✦ X on any row of the hub writes those too)."""
    out, done = [], set()
    clusters = {a["ticker"]: a for a in insiders.get("summary", []) if a.get("cluster")}
    for t in list(trades or []) + list(insiders.get("latest", [])):
        tk = (t.get("ticker") or "").upper().replace("-", ".")
        code = t.get("code")
        if code not in ("P", "S") or not tk or not re.fullmatch(r"[A-Z][A-Z0-9.]{0,6}", tk) or not t.get("price") or not t.get("shares"):
            continue
        key = f"{t.get('accession')}:{t.get('date')}:{t.get('shares')}" + ("" if code == "P" else ":S")   # purchases keep their old key
        if key in done or _h("insider", key) in known:
            continue
        done.add(key)
        e = engage.site_company(rows, by_ticker, t.get("issuer_cik"), tk)
        try:
            cj, fq = engage.figures(site, e) if e else (None, None)
        except Exception:
            cj, fq = None, None
        day = dt.date.fromisoformat((t.get("filed") or t["date"])[:10]) + dt.timedelta(days=int(_h("lag", key), 16) % 4)
        p = engage.insider_plan(t, tk, e if fq else None, cj, fq, clusters.get(tk) if code == "P" else None, day)
        tags = p["tags"]
        msgs = engage.messages("insider", p["task"], [tk], tags)
        who = t.get("title") if t.get("title") and len(t["title"]) <= 24 else t["role"]
        name = t["insider"].title()
        lead = "JUST FILED: " if p["task"].find("JUST FILED") >= 0 else ""
        filed = f", Form 4 filed {t['filed']}" if t.get("filed") else ""
        T = " ".join(tags)
        if code == "P":
            phr = [p["fallback"] + " " + T,
                   f"{lead}Insider purchase at ${tk}: {name} ({who}) bought {t['shares']:,.0f} shares at ${t['price']:,.2f} "
                   f"on {t['date']}{filed}. How do you read it? {T}",
                   f"{lead}${tk} {who} {name} put {engage.money(t['value'])} into the stock on {t['date']}: "
                   f"{t['shares']:,.0f} shares at ${t['price']:,.2f}{filed}. Signal or noise? {T}"]
        else:
            plan = " under a pre-arranged 10b5-1 plan" if t.get("plan_10b5_1") else ""
            phr = [p["fallback"] + " " + T,
                   f"{lead}Insider sale at ${tk}: {name} ({who}) sold {t['shares']:,.0f} shares at ${t['price']:,.2f} "
                   f"on {t['date']}{plan}{filed}. Routine or telling? {T}",
                   f"{lead}${tk} {who} {name} sold {engage.money(t['value'])} of stock on {t['date']}: "
                   f"{t['shares']:,.0f} shares at ${t['price']:,.2f}{plan}{filed}. How do you read it? {T}"]
        cik = (e or {}).get("cik") or int(t.get("issuer_cik") or 0) or None
        for text in _pick(key, phr, 3 if code == "P" else 2):      # purchases are rarer: every phrasing
            ex = example("insider", key, msgs, text, "engage", [tk], tags, cik)
            if ex:
                ex["src"] = _h("insider", key)
                out.append(ex)
    return out


# ------------------------------------------------------------------ the hub's other tables (✦ X on any row)
def _hub(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _company(site, rows, by_ticker, cik, tk):
    e = engage.site_company(rows, by_ticker, cik, tk)
    try:
        cj, fq = engage.figures(site, e) if e else (None, None)
    except Exception:
        cj, fq = None, None
    return (e if fq else None), cj, fq


def hub_examples(site, rows, by_ticker, known, market, limits=None):
    """Posts for one row of the hub's 13D / 13G, Form 144, Short interest and Officials' trades (House and Senate) tables,
    from the published files in `market` (disclosures/docs/data/market): the plan's rule-based post plus one or two other
    phrasings, each checked like a real post."""
    lim = {"stake": 500, "form144": 400, "short": 300, "official": 600, "event8k": 500, "news": 400, **(limits or {})}
    out = {"stake": [], "form144": [], "short": [], "official": [], "event8k": [], "news": []}
    today = dt.date.today()

    def add(kind, key, p, phr, n, cik):
        tk = p["cashtags"]
        msgs = engage.messages(kind, p["task"], tk, p["tags"])
        T = " ".join(p["tags"])
        for text in _pick(key, [p["fallback"] + " " + T] + [x + " " + T for x in phr], n):
            ex = example(kind, key, msgs, text, "engage", tk, p["tags"], cik)
            if ex:
                ex["src"] = _h(kind, key)
                out[kind].append(ex)

    st = _hub(os.path.join(market, "stakes.json"))
    for r in st.get("latest", []):
        tk = (r.get("ticker") or "").upper().replace("-", ".")
        key = f"stake:{r.get('accession')}"
        if len(out["stake"]) >= lim["stake"] or not tk or r.get("percent") is None or _h("stake", key) in known:
            continue
        e, cj, fq = _company(site, rows, by_ticker, r.get("issuer_cik"), tk)
        p = engage.stake_plan(r, tk, e, cj, fq, dt.date.fromisoformat((r.get("filed") or today.isoformat())[:10]) + dt.timedelta(days=int(_h(key), 16) % 4))
        who, form, filed = engage.holder_name(r), r["form"], engage._day(r.get("filed"))
        sh = engage.shares_txt(r.get("shares"))
        lead = "JUST FILED: " if "JUST FILED" in p["task"] else ""
        chg = (f", {'up' if r['change'] > 0 else 'down'} from {r['prev_percent']:g}%" if r.get("change") and r.get("prev_percent") is not None else "")
        kind_txt = "may seek to influence the company" if form.startswith("13D") else "a passive holder"
        phr = [f"{lead}{who} reports {r['percent']:g}% of ${tk} ({sh} shares){chg} in a Schedule {form} filed {filed} — {kind_txt}. "
               f"What do you make of it?",
               f"{lead}Schedule {form} on ${tk}: {who} holds {r['percent']:g}% ({sh} shares){chg}, filed {filed}. Who blinks first?"
               if form.startswith("13D") else
               f"{lead}Schedule {form} on ${tk}: {who} holds {r['percent']:g}% ({sh} shares){chg}, filed {filed}. Long-term holder or trade?"]
        add("stake", key, p, phr, 2, (e or {}).get("cik") or int(r.get("issuer_cik") or 0) or None)

    fm = _hub(os.path.join(market, "form144.json"))
    for r in fm.get("latest", []):
        tk = (r.get("ticker") or "").upper().replace("-", ".")
        key = f"form144:{r.get('accession')}"
        if len(out["form144"]) >= lim["form144"] or not tk or not r.get("shares") or _h("form144", key) in known:
            continue
        e, cj, fq = _company(site, rows, by_ticker, r.get("issuer_cik"), tk)
        p = engage.f144_plan(r, tk, e, cj, fq, dt.date.fromisoformat((r.get("filed") or today.isoformat())[:10]) + dt.timedelta(days=int(_h(key), 16) % 4))
        who = social.display_name(r.get("seller_name") or r.get("seller") or "")
        rel = engage.relation(r.get("relationship")) or "insider"
        sh, val = engage.shares_txt(r["shares"]), (f" (~{engage.money(r['value'])})" if r.get("value") else "")
        lead = "JUST FILED: " if "JUST FILED" in p["task"] else ""
        phr = [f"{lead}${tk} {rel} {who} filed a Form 144 for a planned sale of {sh} shares{val}"
               + (f", approx. sale date {engage._day(r['sale_date'])}" if r.get("sale_date") else "") + ". Routine or telling?",
               f"{lead}Notice of a planned sale at ${tk}: {who} ({rel}), {sh} shares{val}"
               + (f", shares from {r['acquired'].lower()}" if r.get("acquired") and len(r["acquired"]) <= 40 else "") + " (Form 144). How do you read it?"]
        add("form144", key, p, phr, 2, (e or {}).get("cik") or int(r.get("issuer_cik") or 0) or None)

    si = _hub(os.path.join(market, "short-interest.json"))
    day, prev = si.get("settlement_date"), si.get("previous_date")
    pick = [r for r in si.get("rows", []) if r.get("change_pct") is not None and (r.get("adv") or 0) >= 200_000]
    pick.sort(key=lambda r: -abs(r["change_pct"]))
    for r in pick:
        tk = (r.get("ticker") or "").upper().replace("-", ".")
        key = f"short:{tk}:{day}"
        if len(out["short"]) >= lim["short"] or not day or not re.fullmatch(r"[A-Z][A-Z0-9.]{0,6}", tk) or _h("short", key) in known:
            continue
        e, cj, fq = _company(site, rows, by_ticker, None, tk)
        p = engage.short_plan(r, day, prev, e, cj, fq)
        sh = engage.shares_txt(r.get("short"))
        phr = [f"${tk} short interest {'rose' if r['change_pct'] > 0 else 'fell'} {abs(r['change_pct']):.1f}% to {sh} shares as of "
               f"{engage._day(day)}" + (f", {r['dtc']:g} days to cover" if r.get("dtc") is not None else "") + " (FINRA). Bets or hedges?",
               f"{sh} shares of ${tk} sold short as of {engage._day(day)}, {r['change_pct']:+.1f}% vs {engage._day(prev)} (FINRA). "
               "What changed?"]
        add("short", key, p, phr, 2, (e or {}).get("cik"))

    ev = _hub(os.path.join(market, "events8k.json"))
    for r in ev.get("rows", []):
        tk = (r.get("ticker") or "").upper().replace("-", ".")
        key = f"8k:{r.get('accession')}"
        if len(out["event8k"]) >= lim["event8k"] or not tk or not r.get("quote") or (r.get("score") or 0) < 3 or _h("event8k", key) in known:
            continue
        e, cj, fq = _company(site, rows, by_ticker, r.get("cik"), tk)
        p = engage.event_row_plan(r, e, cj, fq, dt.date.fromisoformat(r["filed"]) + dt.timedelta(days=int(_h(key), 16) % 4))
        if not p:
            continue
        head = p["fallback"].split(":", 1)[0] if p["fallback"].startswith(("BREAKING", "JUST")) else ""
        what = p["event"]["label"]
        phr = [f"{head + ': ' if head else ''}${tk} filed an 8-K on {engage._day(r['filed'])} — {what}. "
               + (f"The press release: “{r['headline'][:110]}”. " if r.get("headline") and len(r["headline"]) <= 110 else "")
               + "How do you read it?"]
        add("event8k", key, p, phr, 2, (e or {}).get("cik") or int(r.get("cik") or 0) or None)

    nw = _hub(os.path.join(market, "news.json"))
    for r in nw.get("rows", []):
        tks = [t.upper().replace("-", ".") for t in r.get("tickers") or []]
        key = f"news:{r.get('id')}"
        if len(out["news"]) >= lim["news"] or not tks or not r.get("title") or _h("news", key) in known:
            continue
        e, cj, fq = _company(site, rows, by_ticker, None, tks[0])
        p = engage.news_plan(r, tks[0], e, cj, fq, dt.date.fromisoformat(r["published"][:10]) + dt.timedelta(days=int(_h(key), 16) % 3))
        phr = [f"${tks[0]} on {r.get('source')}: “{r['title'][:160]}”. What do you make of it?"]
        add("news", key, p, phr, 2, (e or {}).get("cik"))

    off = _hub(os.path.join(market, "officials-trades.json"))
    for t in off.get("trades", []):
        listed = t.get("ticker_status") == "listed" and t.get("name_check") != "check"
        tk = (t.get("ticker_canon") or t.get("ticker") or "").upper().replace("-", ".") if listed else ""
        key = f"official:{t.get('report_id')}:{t.get('date')}:{tk}:{t.get('type')}:{t.get('amount_min')}:{t.get('owner')}"
        if len(out["official"]) >= lim["official"] or not tk or t.get("asset_type") == "OP" or _h("official", key) in known:
            continue
        e, cj, fq = _company(site, rows, by_ticker, None, tk)
        p = engage.official_plan(t, e, cj, fq, today)
        own = t.get("owner") or ""
        who = (f"{t['person']}'s {engage.WHOSE[own]}" if own in engage.WHOSE else f"{t['person']} (joint account)" if own == "JT" else t["person"])
        verb = {"purchase": "bought", "sale": "sold", "partial sale": "sold part of a holding in", "exchange": "exchanged"}.get(t.get("type"), "traded")
        amt = engage.amount_range(t.get("amount_min"), t.get("amount_max"))
        chamber = "Senate" if t.get("jurisdiction") == "US Senate" else "House"
        phr = [f"{who} {verb} ${tk} ({amt}) on {t.get('date')}, per a {chamber} transaction report filed {t.get('filed_date')}. "
               "Noise or worth tracking?"]
        add("official", key, p, phr, 2, (e or {}).get("cik"))
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


# ------------------------------------------------------------------ market posts (analysts, Polymarket, highs / lows, trending, smart money)
MARKET = {"pt_upside": 10, "versus": 12, "drawdown": 5, "setup": 40, "lows52": 5, "highs52": 5, "near_lows": 5, "records": 3,
          "polymarket": 8, "reddit_hot": 8, "reddit_question": 8, "reddit_list": 4, "smart_buys": 3, "smart_record": 8, "all_agree": 6,
          "qtd_flows": 1}                  # plans per kind and run (each next one without the names already used)


class HubSite:
    """The built site for the company files, the published hub (its URL, or a folder holding disclosures/data/) for the
    market files the plans read."""

    def __init__(self, site, hub):
        self._site, self.src = site, str(hub).rstrip("/")
        self.remote = bool(re.match(r"https?://", self.src))

    def json(self, path):
        return self._site.json(path)

    def quarter(self, e):
        return self._site.quarter(e)


def market_examples(site, rows, by_ticker, known, today, limits=None):
    """{kind: [examples]} for the market post formats. A kind's plans are drawn one after another, each without the names
    the earlier ones used (as the posting cooldown would), up to MARKET[kind]; every rule-written phrasing ("fallbacks")
    of a plan is a target, checked with the plan's own rules (cashtags allowed in a list, line breaks, no forum talk)."""
    lim = {**MARKET, **(limits or {})}
    c = engage.cfg()
    ext, d = engage.extremes(site)
    asof = (d or {}).get("asof") or today.isoformat()
    hot = [t for t in engage.trending(site) if t in by_ticker]
    trends = [{"ticker": t, "score": 100 - i, "mentions": 0} for i, t in enumerate(hot)]
    setup_picks = engage.popular(site, by_ticker, ext, engage.consensus(site), 150) if ext else []

    def plans(kind, n, ok, used):
        def one(f):
            try:
                return f()
            except Exception as err:
                print(f"::warning::{kind} examples: {str(err)[:140]}")
                return None
        if kind == "setup":                       # one stock per plan: the popular names in turn
            got = 0
            for t in setup_picks:
                if got >= n:
                    return
                if t in used:
                    continue
                p = one(lambda: engage.plan_setup(site, rows, c, by_ticker, ok, today, pick=t))
                used.add(t)
                if p:
                    got += 1
                    yield p
            return
        for _ in range(n):
            if kind == "reddit_question":
                p = one(lambda: engage.plan_reddit_question(site, rows, c, trends, by_ticker, ok))
            elif kind == "reddit_list":
                p = one(lambda: engage.plan_reddit_list(site, rows, c, trends, by_ticker, ok))
            else:
                p = one(lambda: getattr(engage, "plan_" + kind)(site, rows, c, by_ticker, ok, today))
            if not p:
                return
            yield p

    out = {}
    for kind, n in lim.items():
        used, xs = set(), out.setdefault(kind, [])
        ok = lambda k, key, hours=None: key not in used
        for p in plans(kind, n, ok, used):
            names = list(p["cashtags"]) + [t for t in p.get("allowed") or [] if t not in p["cashtags"]]
            ev = (p.get("event_key") or "").split(":", 1)[-1]
            fresh = (set(names) | {ev}) - used - {""}
            if kind != "setup" and not fresh:
                break                                 # the plan does not move on (one post a day by design)
            used |= set(names) | {ev}
            key = f"{kind}:{asof}:{','.join(names)}" + (f":{ev}" if ev else "")
            if _h(kind, key) in known:
                continue
            e0 = p["items"][0][0] if p.get("items") else None
            tags = p.get("tags") or engage.H.pick(engage.KIND_TAGS.get(kind, "earnings"), e0, key=f"{kind}:" + ",".join(p["cashtags"]))
            msgs = engage.messages(kind, p["task"], p["cashtags"], tags, p.get("allowed"))
            first = by_ticker.get(p["cashtags"][0]) if p["cashtags"] else None
            for text in p.get("fallbacks") or ([p["fallback"]] if p.get("fallback") else []):
                ex = example(kind, key, msgs, text, "engage", p["cashtags"], tags, (first or {}).get("cik"), allowed=p.get("allowed"),
                             lines=p.get("lines", False), forbid=p.get("forbid"), must=p.get("must"), hold=p["cashtags"][0] if p["cashtags"] else None)
                if ex:
                    ex["src"] = _h(kind, key)
                    xs.append(ex)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--site", default="_site", help="the built site (with data/)")
    ap.add_argument("--site-url", default=os.environ.get("X_SITE_URL") or "", help="the published site, for 13F holder files")
    ap.add_argument("--insiders", default="disclosures/docs/data/market/insiders.json")
    ap.add_argument("--insider-trades", default="disclosures/docs/data/cache/insiders/trades.json.gz",
                    help="the collector's Form 4 trade file: every purchase and sale of the last ~120 days")
    ap.add_argument("--market", default="disclosures/docs/data/market",
                    help="the hub's published tables (8-K events, news, 13D / 13G, Form 144, short interest, officials' trades)")
    ap.add_argument("--known", default="", help="source keys already in the corpus (one per line)")
    ap.add_argument("--out", default="new.jsonl")
    ap.add_argument("--holders", type=int, default=2000, help="companies with 13F holders read this run (one request each)")
    ap.add_argument("--events", type=int, default=80, help="8-Ks read from SEC this run")
    ap.add_argument("--hub", default="", help="the published Disclosures hub for the market posts (default: --site-url; a URL or a folder with disclosures/data/)")
    args = ap.parse_args()
    known = set()
    if args.known and os.path.exists(args.known):
        lines = open(args.known).read().split()
        if lines and lines[0] == f"#v{VERSION}":           # keys from an older corpus version are rebuilt
            known = set(lines[1:])
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
        counts[kind] = counts.get(kind, 0) + len(xs)

    add("post", earnings_examples(site, cfg, known, today))
    try:
        trades = []
        if args.insider_trades and os.path.exists(args.insider_trades):
            import gzip
            with gzip.open(args.insider_trades, "rt", encoding="utf-8") as f:
                trades = json.load(f)
        add("insider", insider_examples(site, rows, by_ticker, json.load(open(args.insiders, encoding="utf-8")), known, trades))
    except (OSError, ValueError) as err:
        print(f"::warning::insider examples skipped ({err})")
    if args.site_url and args.holders:
        # only companies the site publishes 13F holders for (its index), a different slice each day when there are more
        # than one run reads; a company already in the corpus for its latest 13F quarter costs one request and is skipped
        have = None
        try:
            import requests
            r = requests.get(f"{args.site_url.rstrip('/')}/disclosures/data/holders/index.json", timeout=60)
            have = {t.upper().replace(".", "-") for t in (r.json().get("tickers") or [])} if r.status_code == 200 else None
        except Exception as err:
            print(f"::warning::holders index not read ({str(err)[:120]}); trying every company")
        cand = [e for e in rows if e.get("ticker") and (have is None or e["ticker"].upper().replace(".", "-") in have)]
        cand.sort(key=lambda e: -(e.get("revenue") or 0))
        start = (today.toordinal() * args.holders) % max(1, len(cand)) if len(cand) > args.holders else 0
        pick = (cand[start:] + cand[:start])[:args.holders]
        print(f"13F holders: {len(cand)} companies with a holders file" + (" (index not read)" if have is None else "") + f", reading {len(pick)}")
        cs = []
        for e in pick:
            try:
                cs.append(site.json(f"c/{e['cik']}.json"))
            except Exception:
                pass
        add("post_holders", holders_examples(site, args.site_url, known, cs))
    if args.market and os.path.isdir(args.market):
        try:
            for kind, xs in hub_examples(site, rows, by_ticker, known, args.market).items():
                add(kind, xs)
        except Exception as err:
            print(f"::warning::hub table examples skipped ({str(err)[:160]})")
    if args.events:
        add("event8k", event_examples(site, rows, known, today, args.events))
    hub = args.hub or args.site_url
    if hub:
        try:
            for kind, xs in market_examples(HubSite(site, hub), rows, by_ticker, known, today).items():
                add(kind, xs)
        except Exception as err:
            print(f"::warning::market post examples skipped ({str(err)[:160]})")
    with open(args.out, "w", encoding="utf-8") as f:
        for ex in out:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print("new examples: " + ", ".join(f"{k} {v}" for k, v in counts.items()) + f" → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
