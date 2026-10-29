"""What is known about a company today, for the movers' posts (mover / explain / peers in pipeline/engage.py).

One block of dated, sourced facts the post may draw on — none of them is known to be the cause of the move:

  filings     its 8-Ks of the last two days (classified by the hub: a deal, a CEO change, guidance raised …), Schedules
              13D / 13G and Form 144 notices of the last week, Form 4 purchases and sales of the last two weeks
  releases    press releases, FDA approvals and SEC actions naming it (the hub's News table)
  positioning the latest FINRA short-interest change, the 30-day implied volatility and its change, officials' trades
  the market  SPY and the company's sector ETF today
  headlines   what outlets wrote about it in the last day: GDELT (rate-limited from shared runners, so best effort) and
              Yahoo Finance's headline feed for the ticker — titles as published, never facts

Everything comes from the Disclosures hub's published files (engage.hub_json) and two light requests; a source that does
not answer is left out. The block ends with the rule the post must follow: say what is known, never why the stock moved.
"""
import datetime as dt
import email.utils
import re
import time

import requests

from . import quotes as Q

SECTOR_ETF = {"technology": "XLK", "communication": "XLC", "consumer-disc": "XLY", "consumer-staples": "XLP", "health": "XLV",
              "financials": "XLF", "real-estate": "XLRE", "energy": "XLE", "materials": "XLB", "industrials": "XLI", "utilities": "XLU"}
YAHOO_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={t}&region=US&lang=en-US"
GDELT = ("https://api.gdeltproject.org/api/v2/doc/doc?query=%22{q}%22%20sourcelang:english&mode=artlist&maxrecords=15"
         "&format=json&timespan=24h&sort=hybridrel")
UA = "Mozilla/5.0 (compatible; FilingFlows; +https://filing-flows.com)"
CAUSAL = re.compile(r"(?i)\b(because( of)?|due to|driven by|thanks to|sparked by|fu[e]?led by|on (the )?news|in response to|"
                    r"triggered by|caused by|as investors (cheered|reacted)|on (hopes|fears|optimism|worries))\b")
_last_gdelt = [0.0]


def _hub(load, name):
    try:
        return load(name) or {}
    except Exception:
        return {}


def _canon(t):
    return (t or "").upper().replace(".", "-")


def _ago(day, n):
    return (day - dt.timedelta(days=n)).isoformat()


def _m(v):
    if v is None:
        return "—"
    a = abs(v)
    s = f"${a / 1e9:.1f}B" if a >= 1e9 else f"${a / 1e6:.1f}M" if a >= 1e6 else f"${a / 1e3:.0f}K"
    return ("−" if v < 0 else "") + s


def _sh(n):
    return "—" if n is None else f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n:,.0f}"


def _nth(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def headlines_yahoo(ticker, since, n=6, timeout=15):
    """[(published ISO, title, publisher)] from Yahoo Finance's headline feed for the ticker."""
    r = requests.get(YAHOO_RSS.format(t=ticker.replace(".", "-")), headers={"User-Agent": UA}, timeout=timeout)
    r.raise_for_status()
    out = []
    for item in re.findall(r"(?s)<item>(.*?)</item>", r.text):
        title = re.search(r"(?s)<title>(.*?)</title>", item)
        when = re.search(r"<pubDate>(.*?)</pubDate>", item)
        try:
            d = email.utils.parsedate_to_datetime(when.group(1)).astimezone(dt.timezone.utc) if when else None
        except (TypeError, ValueError):
            d = None
        t = re.sub(r"\s+", " ", re.sub(r"<!\[CDATA\[|\]\]>", "", title.group(1) if title else "")).strip()
        if t and d and d.isoformat() >= since:
            out.append((d.strftime("%Y-%m-%d %H:%M"), t, "Yahoo Finance"))
    return out[:n]


def headlines_gdelt(name, n=6, tries=2, timeout=20):
    """[(seen, title, domain)] from GDELT's document search for the company's name (one request per 5 seconds at most;
    GitHub's shared runners are often over GDELT's limit, so a 429 is retried once and then given up)."""
    q = re.sub(r"[^A-Za-z0-9 &.-]", "", name).strip()
    if len(q) < 3:
        return []
    for i in range(tries):
        wait = 6 - (time.monotonic() - _last_gdelt[0])
        if wait > 0:
            time.sleep(wait)
        _last_gdelt[0] = time.monotonic()
        r = requests.get(GDELT.format(q=requests.utils.quote(q)), headers={"User-Agent": UA}, timeout=timeout)
        if r.status_code == 429:
            continue
        r.raise_for_status()
        out = []
        for a in (r.json() or {}).get("articles") or []:
            t, s = (a.get("title") or "").strip(), a.get("seendate") or ""
            if t and q.split()[0].lower() in t.lower():
                out.append((f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[9:11]}:{s[11:13]}", re.sub(r"\s+([.,'])", r"\1", t), a.get("domain") or ""))
        return out[:n]
    return []


def known(load, e, day=None, quote=None, with_headlines=True, skip_8k=False, log=print):
    """(text block, facts dict) for company e (a site index row: ticker, cik, name, sector) on `day` (New York date).
    load(name) returns one of the hub's market/*.json files."""
    day = day or (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=4)).date()
    tk, cik = _canon(e.get("ticker")), str(e.get("cik") or "").lstrip("0")
    lines, facts = [], {}

    ev = _hub(load, "events8k.json")
    mine = [r for r in ev.get("rows", []) if (str(r.get("cik") or "") == cik or _canon(r.get("ticker")) == tk) and r.get("filed", "") >= _ago(day, 2)]
    for r in ([] if skip_8k else mine[:2]):                  # skip_8k: the post already quotes today's 8-K
        what = (r.get("label") if str(r.get("label") or "").startswith("guidance ") else f"guidance {r['guidance']}") \
            if r.get("guidance") in ("raised", "lowered", "withdrawn", "mixed", "narrowed", "widened", "initiated") else r.get("label") or "an 8-K"
        when = r.get("filed") + (f" {r['accepted'][11:16]} ET" if len(r.get("accepted") or "") >= 16 else "")
        q = r.get("guidance_quote") or r.get("quote") or r.get("headline") or ""
        lines.append(f"- 8-K filed {when}, items {', '.join(x for x in r.get('items') or [] if x != '9.01') or '9.01'} ({what})"
                     + (f": “{q[:260]}”" if q else ""))
    facts["events8k"] = mine[:2]

    news = _hub(load, "news.json")
    rel = [r for r in news.get("rows", []) if tk in [_canon(t) for t in r.get("tickers") or []] and r.get("published", "") >= _ago(day, 2)]
    for r in rel[:3]:
        lines.append(f"- {r.get('source')} ({r.get('published', '')[:16].replace('T', ' ')} UTC): “{r.get('title')}”")
    facts["news"] = rel[:3]

    st = _hub(load, "stakes.json")
    for r in [r for r in st.get("latest", []) if _canon(r.get("ticker")) == tk and r.get("filed", "") >= _ago(day, 7)][:2]:
        ch = f", {'up' if r['change'] > 0 else 'down'} from {r['prev_percent']:g}%" if r.get("change") and r.get("prev_percent") is not None else ""
        lines.append(f"- Schedule {r.get('form')} filed {r.get('filed')}: {r.get('holder') or r.get('filer')} reports {r.get('percent'):g}%{ch}"
                     if r.get("percent") is not None else f"- Schedule {r.get('form')} filed {r.get('filed')} by {r.get('filer')}")
    fm = _hub(load, "form144.json")
    for r in [r for r in fm.get("latest", []) if _canon(r.get("ticker")) == tk and r.get("filed", "") >= _ago(day, 7)][:2]:
        lines.append(f"- Form 144 filed {r.get('filed')}: {r.get('seller_name') or r.get('seller')} ({(r.get('relationship') or '').lower()}) gave "
                     f"notice of a planned sale of {_sh(r.get('shares'))} shares (~{_m(r.get('value'))})")
    ins = _hub(load, "insiders.json")
    for t in [t for t in ins.get("latest", []) if _canon(t.get("ticker")) == tk and t.get("date", "") >= _ago(day, 14)][:2]:
        lines.append(f"- Form 4: {t.get('insider', '').title()} ({t.get('title') or t.get('role')}) {'bought' if t.get('code') == 'P' else 'sold'} "
                     f"{_sh(t.get('shares'))} shares ({_m(t.get('value'))}) on {t.get('date')}")
    off = _hub(load, "officials-trades.json")
    for t in [t for t in off.get("trades", []) if _canon(t.get("ticker_canon")) == tk and t.get("filed_date", "") >= _ago(day, 7)][:1]:
        lines.append(f"- {t.get('jurisdiction')} disclosure filed {t.get('filed_date')}: {t.get('person')} — {t.get('type')} on {t.get('date')}")

    si = _hub(load, "short-interest.json")
    s = next((r for r in si.get("rows", []) if _canon(r.get("ticker")) == tk), None)
    if s and s.get("change_pct") is not None:
        lines.append(f"- Short interest {si.get('settlement_date')}: {_sh(s.get('short'))} shares, {s['change_pct']:+.1f}% vs {si.get('previous_date')}"
                     + (f", {s['dtc']:g} days to cover" if s.get("dtc") is not None else ""))
    op = _hub(load, "options.json")
    o = next((r for r in op.get("rows", []) if _canon(r.get("ticker")) == tk), None)
    if o and o.get("iv30") is not None:
        lines.append(f"- Options (last close): 30-day implied volatility {o['iv30']:.1f}%"
                     + (f", {o['iv30_chg']:+.1f} pts on the day" if o.get("iv30_chg") is not None else "")
                     + (f", {_nth(round(o['iv30_pct'] * 100))} percentile of its history" if o.get("iv30_pct") is not None else ""))

    mkt = []
    for sym in ["SPY", SECTOR_ETF.get(e.get("sector") or "")]:
        if not sym:
            continue
        try:
            q = Q.yahoo_one(sym)
            if q and q.get("chg_pct") is not None and q.get("asof") == (quote or {}).get("asof", q.get("asof")):
                mkt.append(f"{sym} {q['chg_pct']:+.1f}%")
        except Exception as err:
            log(f"context: {sym} quote not read ({str(err)[:80]})")
    if mkt:
        lines.append("- The market the same session: " + ", ".join(mkt))
        facts["market"] = mkt

    heads = []
    if with_headlines:
        since = (dt.datetime.combine(day, dt.time(0)) - dt.timedelta(hours=20)).replace(tzinfo=dt.timezone.utc).isoformat()
        try:
            heads += headlines_gdelt(e.get("name") or tk)
        except Exception as err:
            log(f"context: GDELT not read ({str(err)[:80]})")
        try:
            have = {h[1].lower() for h in heads}
            heads += [h for h in headlines_yahoo(tk, since) if h[1].lower() not in have]
        except Exception as err:
            log(f"context: Yahoo headlines not read ({str(err)[:80]})")
    facts["headlines"] = heads[:6]
    text = ""
    if lines:
        text += (f"\n\nWHAT IS KNOWN ABOUT ${tk.replace('-', '.')} (public filings and data, dated; none of these is known to be the "
                 "cause of the move):\n" + "\n".join(lines))
    if heads:
        text += ("\n\nHEADLINES OF THE LAST DAY (what outlets wrote — titles, not verified facts; never present them as facts):\n"
                 + "\n".join(f"- {h[0]} · {h[2]}: “{h[1][:160]}”" for h in heads[:6]))
    if text:
        text += ("\n\nYou may mention one or two of these, attributed and dated (“an 8-K filed today says …”, “Form 4: the CFO sold …”, "
                 "“headlines today: …”). Never say or imply that any of them caused the move: no “because”, “due to”, “on news of”, "
                 "“driven by”, “sparked”, “in response to”.")
    return text, facts
