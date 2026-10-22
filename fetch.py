"""One-off data pull for the valuation-reversion study (not part of the site).

    python fetch.py yahoo <part> <parts> <out>   monthly close (split-adjusted), adjusted close, dividends, splits
    python fetch.py sec <out>                     SEC XBRL frames: shares, EPS, equity, income, revenue since 2008
"""
import datetime as dt
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

YAHOO = ('https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1={p1}&period2={p2}&interval=1mo'
         '&events=div%2Csplit&includeAdjustedClose=true')
BROWSER = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'


def get(url, ua, tries=4, pause=2.0):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': ua, 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 404:
                return None
            time.sleep(pause * (2 ** i) * (3 if e.code == 429 else 1))
        except Exception as e:  # network hiccup
            last = e
            time.sleep(pause * (2 ** i))
    raise RuntimeError(str(last)[:200])


def day(ts, off=0):
    return dt.datetime.fromtimestamp(ts + off, dt.timezone.utc).date().isoformat()


def yahoo(part, parts, out):
    tickers = [t.strip() for t in Path('tickers.txt').read_text().split() if t.strip()]
    mine = tickers[part::parts]
    p1 = int(dt.datetime(1999, 12, 1, tzinfo=dt.timezone.utc).timestamp())
    p2 = int(time.time()) + 86400
    res, bad = {}, {}
    for i, t in enumerate(mine):
        try:
            j = get(YAHOO.format(s=t, p1=p1, p2=p2), BROWSER)
            r = (((j or {}).get('chart') or {}).get('result') or [None])[0]
            if not r:
                bad[t] = 'no result'
                continue
            off = (r.get('meta') or {}).get('gmtoffset') or 0
            q = ((r.get('indicators') or {}).get('quote') or [{}])[0]
            adj = (((r.get('indicators') or {}).get('adjclose') or [{}])[0] or {}).get('adjclose') or []
            cl = q.get('close') or []
            m = []
            for k, ts in enumerate(r.get('timestamp') or []):
                c = cl[k] if k < len(cl) else None
                a = adj[k] if k < len(adj) else None
                if c is None or a is None:
                    continue
                m.append([day(ts, off), round(c, 6), round(a, 6)])
            ev = r.get('events') or {}
            divs = sorted([day(int(k)), v.get('amount')] for k, v in (ev.get('dividends') or {}).items())
            spl = sorted([day(int(k)), v.get('numerator'), v.get('denominator')] for k, v in (ev.get('splits') or {}).items())
            res[t] = {'m': m, 'd': divs, 's': spl, 'cur': (r.get('meta') or {}).get('currency')}
        except Exception as e:
            bad[t] = str(e)[:120]
        if i % 100 == 0:
            print(i, len(mine), t, len(res), len(bad), flush=True)
        time.sleep(0.6)
    Path(out).mkdir(parents=True, exist_ok=True)
    with gzip.open(Path(out) / f'yahoo-{part}.json.gz', 'wt') as f:
        json.dump({'rows': res, 'bad': bad}, f, separators=(',', ':'))
    print('done', len(res), 'ok', len(bad), 'failed')


DUR = [('us-gaap', 'NetIncomeLoss', 'USD'), ('us-gaap', 'Revenues', 'USD'),
       ('us-gaap', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'USD'), ('us-gaap', 'SalesRevenueNet', 'USD'),
       ('us-gaap', 'RevenueFromContractWithCustomerIncludingAssessedTax', 'USD'), ('us-gaap', 'OperatingIncomeLoss', 'USD'),
       ('us-gaap', 'WeightedAverageNumberOfDilutedSharesOutstanding', 'shares'),
       ('us-gaap', 'EarningsPerShareDiluted', 'USD-per-shares'),
       ('us-gaap', 'NetCashProvidedByUsedInOperatingActivities', 'USD')]
INST = [('dei', 'EntityCommonStockSharesOutstanding', 'shares'), ('us-gaap', 'StockholdersEquity', 'USD'),
        ('us-gaap', 'Assets', 'USD'), ('us-gaap', 'LongTermDebt', 'USD'),
        ('us-gaap', 'CashAndCashEquivalentsAtCarryingValue', 'USD')]


def sec(out):
    ua = os.environ.get('SEC_USER_AGENT') or ''
    if '@' not in ua:
        raise SystemExit('SEC_USER_AGENT is not set')
    today = dt.date.today()
    periods = []
    for y in range(2008, today.year + 1):
        periods.append(f'CY{y}')
        for q in range(1, 5):
            if dt.date(y, 3 * q, 1) < today:
                periods.append(f'CY{y}Q{q}')
    res, bad = {}, {}
    jobs = [(tx, tag, u, p) for tx, tag, u in DUR for p in periods] + \
           [(tx, tag, u, p + 'I') for tx, tag, u in INST for p in periods if 'Q' in p]
    for i, (tx, tag, u, p) in enumerate(jobs):
        url = f'https://data.sec.gov/api/xbrl/frames/{tx}/{tag}/{u}/{p}.json'
        try:
            j = get(url, ua, pause=1.0)
            rows = [[d['cik'], d['val'], d.get('end'), d.get('accn'), d.get('start')] for d in (j or {}).get('data', [])]
            res[f'{tag}/{p}'] = rows
        except Exception as e:
            bad[f'{tag}/{p}'] = str(e)[:120]
        if i % 50 == 0:
            print(i, len(jobs), tag, p, len(res), len(bad), flush=True)
        time.sleep(0.15)
    Path(out).mkdir(parents=True, exist_ok=True)
    with gzip.open(Path(out) / 'frames.json.gz', 'wt') as f:
        json.dump({'frames': res, 'bad': bad}, f, separators=(',', ':'))
    print('done', len(res), 'ok', len(bad), 'failed')


if __name__ == '__main__':
    if sys.argv[1] == 'yahoo':
        yahoo(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
    else:
        sec(sys.argv[2])
