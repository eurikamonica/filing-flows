"""Live (15-minute delayed) US stock quotes for the movers posts (pipeline/engage.py kinds mover / explain / peers).

    python -m pipeline.quotes NVDA AAPL TSLA          # print price, change and market value

quotes(tickers) tries, in order:
  1. Nasdaq's stock screener — ONE request returns every US-listed stock with last price, change %, market value,
     sector and industry (the fast path for scanning the whole site at once)
  2. Yahoo's chart endpoint, one request per ticker (8 at a time), for the tickers the screener did not return
Either can be refused from a cloud runner now and then; the caller gets whatever answered.
"""
import concurrent.futures as cf
import re
import sys

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
NASDAQ = "https://api.nasdaq.com/api/screener/stocks"
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


def canon(t):
    return (t or "").strip().upper().replace(".", "-").replace("/", "-")


def parse_nasdaq(payload):
    rows = ((payload or {}).get("data") or {}).get("rows") or (((payload or {}).get("data") or {}).get("table") or {}).get("rows") or []
    out = {}
    for r in rows:
        t = canon(r.get("symbol"))
        price = _num(r.get("lastsale"))
        if not t or price is None:
            continue
        out[t] = {"price": price, "chg_pct": _num(r.get("pctchange")), "chg": _num(r.get("netchange")), "mcap": _num(r.get("marketCap")),
                  "volume": _num(r.get("volume")), "name": r.get("name"), "sector": r.get("sector"), "industry": r.get("industry"),
                  "source": "nasdaq"}
    return out


def nasdaq_all(timeout=40):
    r = requests.get(NASDAQ, params={"tableonly": "true", "limit": 10000, "download": "true"}, timeout=timeout,
                     headers={"User-Agent": UA, "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9",
                              "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"})
    r.raise_for_status()
    return parse_nasdaq(r.json())


def parse_yahoo(payload):
    res = (((payload or {}).get("chart") or {}).get("result") or [None])[0] or {}
    meta = res.get("meta") or {}
    price = meta.get("regularMarketPrice")
    closes = [c for c in ((((res.get("indicators") or {}).get("quote") or [{}])[0].get("close")) or []) if c is not None]
    # daily bars over five days: the last bar is today's (or the last session's), the one before is the prior close
    prev = closes[-2] if len(closes) >= 2 else (meta.get("previousClose") or meta.get("chartPreviousClose"))
    if price is None:
        return None
    return {"price": float(price), "chg_pct": (price / prev - 1) * 100 if prev else None, "chg": price - prev if prev else None,
            "mcap": None, "volume": meta.get("regularMarketVolume"), "name": meta.get("longName") or meta.get("shortName"),
            "sector": None, "industry": None, "source": "yahoo"}


def yahoo_one(t, timeout=20):
    r = requests.get(YAHOO.format(sym=t.replace(".", "-")), params={"range": "5d", "interval": "1d"}, timeout=timeout,
                     headers={"User-Agent": UA, "Accept": "application/json"})
    r.raise_for_status()
    return parse_yahoo(r.json())


def quotes(tickers, yahoo_limit=400, log=print):
    want = {canon(t) for t in tickers if t}
    got = {}
    try:
        allq = nasdaq_all()
        got = {t: q for t, q in allq.items() if t in want}
        log(f"quotes: Nasdaq screener answered ({len(allq)} US stocks, {len(got)} on the site)")
    except Exception as err:
        log(f"::warning::Nasdaq screener not reached ({str(err)[:120]}); Yahoo per ticker instead")
    rest = sorted(want - set(got))[:yahoo_limit]
    if rest:
        with cf.ThreadPoolExecutor(8) as pool:
            for t, q in zip(rest, pool.map(lambda x: _safe(yahoo_one, x), rest)):
                if q:
                    got[t] = q
        log(f"quotes: Yahoo answered for {sum(1 for t in rest if t in got)} of {len(rest)}")
    return got


def _safe(f, *a):
    try:
        return f(*a)
    except Exception:
        return None


if __name__ == "__main__":
    for t, q in sorted(quotes(sys.argv[1:]).items()):
        print(f"{t:6} ${q['price']:.2f}  {q['chg_pct'] or 0:+.2f}%  mcap {q['mcap'] or 0:,.0f}  ({q['source']})")
