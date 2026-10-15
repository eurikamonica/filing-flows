"""Live (15-minute delayed) US stock quotes for the movers posts (pipeline/engage.py kinds mover / explain / peers).

    python -m pipeline.quotes NVDA AAPL TSLA          # print price, change and market value

quotes(tickers) tries, in order:
  1. Nasdaq's stock screener — ONE request returns every US-listed stock with last price, change %, market value,
     sector and industry (the fast path for scanning the whole site at once)
  2. Yahoo's chart endpoint, one request per ticker (8 at a time), for the tickers the screener did not return
Either can be refused from a cloud runner now and then; the caller gets whatever answered.

Every quote carries "asof", the trading day it belongs to. The screener's download is not always refreshed: it can
still serve the previous session hours later (XMTR showed Oct 14's $95.15, −12% on the evening of Oct 15, when it had
closed at $99.54, +4.6%). So a screener older than the current session is not used, Yahoo quotes from another day are
dropped, and confirm() re-checks a mover against Yahoo before a post quotes it.
"""
import concurrent.futures as cf
import datetime as dt
import re
import sys
from zoneinfo import ZoneInfo

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
NASDAQ = "https://api.nasdaq.com/api/screener/stocks"
CALENDAR = "https://api.nasdaq.com/api/calendar/earnings"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"


def _num(v):
    if v is None:
        return None
    s = re.sub(r"[,$%\s]", "", str(v))
    if s in ("", "NA", "N/A", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


NY = ZoneInfo("America/New_York")


def session_date(now=None):
    """The session whose prices count as today's: today from 9:30 ET on a weekday, otherwise the weekday before."""
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(NY)
    d = now.date()
    if d.weekday() >= 5 or (now.hour, now.minute) < (9, 30):
        d -= dt.timedelta(days=1)
        while d.weekday() >= 5:
            d -= dt.timedelta(days=1)
    return d


def after_close(now=None):
    """True once the current session has closed (4 PM ET) or before it opens: quotes are then a close, not 'today'."""
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(NY)
    return session_date(now) != now.date() or (now.hour, now.minute) >= (16, 0)


def parse_asof(text):
    """'Last price as of Oct 14, 2026' (or an ISO date) → '2026-10-14'."""
    s = str(text or "")
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})", s)
    if m:
        for f in ("%b %d %Y", "%B %d %Y"):
            try:
                return dt.datetime.strptime(f"{m.group(1)[:3] if f == '%b %d %Y' else m.group(1)} {m.group(2)} {m.group(3)}", f).date().isoformat()
            except ValueError:
                pass
    return None


def canon(t):
    return (t or "").strip().upper().replace(".", "-").replace("/", "-")


def parse_nasdaq(payload):
    data = (payload or {}).get("data") or {}
    rows = data.get("rows") or (data.get("table") or {}).get("rows") or []
    stamp = next((v for d in (data, data.get("table") or {}) for k, v in d.items() if k.lower() == "asof" and v), None)
    asof = parse_asof(stamp)
    out = {}
    for r in rows:
        t = canon(r.get("symbol"))
        price = _num(r.get("lastsale"))
        if not t or price is None:
            continue
        out[t] = {"price": price, "chg_pct": _num(r.get("pctchange")), "chg": _num(r.get("netchange")), "mcap": _num(r.get("marketCap")),
                  "volume": _num(r.get("volume")), "name": r.get("name"), "sector": r.get("sector"), "industry": r.get("industry"),
                  "source": "nasdaq", "asof": asof}
    return out


def nasdaq_all(timeout=40):
    r = requests.get(NASDAQ, params={"tableonly": "true", "limit": 10000, "download": "true"}, timeout=timeout,
                     headers={"User-Agent": UA, "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9",
                              "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"})
    r.raise_for_status()
    return parse_nasdaq(r.json())


def parse_calendar(payload):
    """Nasdaq's earnings calendar for one day → [{ticker, name, when, mcap, eps_estimate, estimates, fiscal_quarter}]."""
    rows = (((payload or {}).get("data") or {}).get("rows")) or []
    when = {"time-pre-market": "before the open", "time-after-hours": "after the close"}
    out = []
    for r in rows:
        t = canon(r.get("symbol"))
        if t:
            out.append({"ticker": t, "name": r.get("name"), "when": when.get(r.get("time"), "time not given"),
                        "mcap": _num(r.get("marketCap")), "eps_estimate": r.get("epsForecast") or None,
                        "estimates": _num(r.get("noOfEsts")), "fiscal_quarter": r.get("fiscalQuarterEnding")})
    return out


def earnings_calendar(day, timeout=40):
    r = requests.get(CALENDAR, params={"date": str(day)}, timeout=timeout,
                     headers={"User-Agent": UA, "Accept": "application/json, text/plain, */*", "Origin": "https://www.nasdaq.com",
                              "Referer": "https://www.nasdaq.com/"})
    r.raise_for_status()
    return parse_calendar(r.json())


def parse_yahoo(payload):
    res = (((payload or {}).get("chart") or {}).get("result") or [None])[0] or {}
    meta = res.get("meta") or {}
    price = meta.get("regularMarketPrice")
    if price is None:
        return None
    day = lambda ts: dt.datetime.fromtimestamp(ts, dt.timezone.utc).astimezone(NY).date().isoformat()
    asof = day(meta["regularMarketTime"]) if meta.get("regularMarketTime") else None
    closes = (((res.get("indicators") or {}).get("quote") or [{}])[0].get("close")) or []
    bars = [(day(ts), c) for ts, c in zip(res.get("timestamp") or [], closes) if c is not None]
    if asof and bars:                         # the prior close: the last daily bar from before the quote's own day
        before = [c for d, c in bars if d < asof]
        prev = before[-1] if before else None
    else:
        plain = [c for c in closes if c is not None]
        prev = plain[-2] if len(plain) >= 2 else None
    prev = prev or meta.get("previousClose") or meta.get("chartPreviousClose")
    return {"price": float(price), "chg_pct": (price / prev - 1) * 100 if prev else None, "chg": price - prev if prev else None,
            "mcap": None, "volume": meta.get("regularMarketVolume"), "name": meta.get("longName") or meta.get("shortName"),
            "sector": None, "industry": None, "source": "yahoo", "asof": asof}


def yahoo_one(t, timeout=20):
    r = requests.get(YAHOO.format(sym=t.replace(".", "-")), params={"range": "5d", "interval": "1d"}, timeout=timeout,
                     headers={"User-Agent": UA, "Accept": "application/json"})
    r.raise_for_status()
    return parse_yahoo(r.json())


def quotes(tickers, yahoo_limit=400, log=print, now=None):
    want = {canon(t) for t in tickers if t}
    expect = session_date(now).isoformat()
    got, sizes = {}, {}
    try:
        allq = nasdaq_all()
        asof = next((q["asof"] for q in allq.values() if q.get("asof")), None)
        if asof and asof < expect:
            log(f"::warning::Nasdaq screener still shows the {asof} session (expected {expect}); Yahoo per ticker instead")
            sizes = {t: q for t, q in allq.items() if t in want}       # its market values still size the companies
        else:
            got = {t: q for t, q in allq.items() if t in want}
            log(f"quotes: Nasdaq screener answered ({len(allq)} US stocks, {len(got)} on the site, prices as of {asof or 'an unstated time'})")
            # the screener lists every exchange-listed stock: a site ticker it lacks trades over the counter, was delisted
            # or renamed — no market value to check, and its "move" is often a reverse split or a stale quote. Skip them.
            return got
    except Exception as err:
        log(f"::warning::Nasdaq screener not reached ({str(err)[:120]}); Yahoo per ticker instead")
    rest = sorted(want, key=lambda t: (t not in sizes, -(sizes.get(t, {}).get("mcap") or 0), t))[:yahoo_limit]
    stale = 0
    if rest:
        with cf.ThreadPoolExecutor(8) as pool:
            for t, q in zip(rest, pool.map(lambda x: _safe(yahoo_one, x), rest)):
                if not q:
                    continue
                if q.get("asof") and q["asof"] != expect:
                    stale += 1
                    continue
                old = sizes.get(t)
                if old and old.get("mcap") and old.get("price"):           # yesterday's market value moved to today's price
                    q["mcap"] = old["mcap"] * q["price"] / old["price"]
                got[t] = q
        log(f"quotes: Yahoo answered for {len(got)} of {len(rest)}" + (f" ({stale} from another day, dropped)" if stale else ""))
    return got


def confirm(t, q, now=None, log=print):
    """Re-read one quote from Yahoo before a post uses it. Returns the quote to post (Yahoo's when it agrees and is current,
    so price and change are the freshest), or None when the two sources disagree or the move cannot be dated to today."""
    expect = session_date(now).isoformat()
    y = q if q.get("source") == "yahoo" else _safe(yahoo_one, t)
    if not y or y.get("chg_pct") is None:
        if q.get("asof") == expect:
            return q
        log(f"{t}: quote not confirmed (Yahoo did not answer; screener date {q.get('asof') or 'unknown'}); skipped")
        return None
    if y.get("asof") != expect:
        log(f"{t}: Yahoo's quote is from {y.get('asof')}, not the {expect} session; skipped")
        return None
    if y is not q and (abs(y["price"] / q["price"] - 1) > 0.02 or abs(y["chg_pct"] - (q.get("chg_pct") or 0)) > 1.5):
        log(f"{t}: sources disagree (screener ${q['price']:,.2f} {q.get('chg_pct') or 0:+.1f}%, Yahoo ${y['price']:,.2f} "
            f"{y['chg_pct']:+.1f}% on {y['asof']}); skipped")
        return None
    out = dict(q)
    out.update({k: y[k] for k in ("price", "chg_pct", "chg", "asof")})
    if q.get("mcap") and q.get("price") and y is not q:
        out["mcap"] = q["mcap"] * y["price"] / q["price"]
    out["source"] = q.get("source", "yahoo") + ("+yahoo" if y is not q else "")
    return out


def _safe(f, *a):
    try:
        return f(*a)
    except Exception:
        return None


if __name__ == "__main__":
    for t, q in sorted(quotes(sys.argv[1:]).items()):
        print(f"{t:6} ${q['price']:.2f}  {q['chg_pct'] or 0:+.2f}%  mcap {q['mcap'] or 0:,.0f}  as of {q.get('asof')}  ({q['source']})")
