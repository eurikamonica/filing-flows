"""52-week and all-time highs and lows (4.17), once a day after the close.

For every liquid US stock the Hub follows (a price file in cache/prices, not a fund, at least $3 and $10M a day traded)
plus Reddit's current top tickers: a year of daily bars from Yahoo's chart endpoint → the session's close, high and low,
the 52-week high and low (the 251 sessions before it), how far the close sits from each, the change since the year began
and over a month, and whether the session made a new 52-week high or low at some point in the day. The ones at a new
52-week extreme are checked against their whole history (monthly bars since listing): an all-time high or low when the
session's high (low) passed every earlier month's.

Publish: market/extremes.json — the lists (new 52-week lows / highs, all-time highs / lows) and one compact row per
stock for the X posts (pipeline/engage.py: lows52, near_lows, records, drawdown, setup, versus).
"""
import datetime as dt
import gzip
import json
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core import now, read_json, write_json

CHART = 'https://query2.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval={iv}'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
FUND = re.compile(r'\bETF\b|\bETN\b|SPDR|ISHARES|PROSHARES|DIREXION|VANGUARD|INVESCO QQQ|SELECT SECTOR|\bFUND\b|GRAYSCALE|\bTRUST\b|'
                  r'\bNOTES?\b|\bWARRANTS?\b|\bRIGHTS?\b|\bUNITS?\b|DEPOSITARY', re.I)
FIELDS = ['close', 'chg1d', 'hi52', 'lo52', 'from_hi', 'from_lo', 'ytd', 'm1', 'day_hi', 'day_lo', 'dollar_vol', 'new_hi', 'new_lo',
          'ath', 'atl', 'ath_prev', 'atl_prev', 'since', 'peak_date', 'trough_date']


def _r(v, n=4):
    return None if v is None else round(float(v), n)


def universe(root, min_price=3.0, min_dollar_vol=10e6, extra=()):
    """Liquid stocks with a price file in the Hub's cache (the last 20 sessions' closes × volume), funds left out."""
    root = Path(root)
    names = {}
    for r in (read_json(root / 'cache' / 'prices' / 'sec-tickers.json', {}).get('rows') or []):
        t = str(r.get('ticker') or '').upper().replace('.', '-')
        names.setdefault(t, r.get('title') or '')
    out = {}
    for p in (root / 'cache' / 'prices').glob('*.json.gz'):
        t = p.name[:-8]
        if t not in names or FUND.search(names[t] or ''):
            continue
        try:
            with gzip.open(p, 'rt', encoding='utf-8') as f:
                rows = json.load(f).get('rows') or []
        except (OSError, ValueError):
            continue
        last = [r for r in rows[-20:] if len(r) > 2 and r[1] and r[2]]
        if len(last) < 10 or last[-1][1] < min_price:
            continue
        dv = sum(r[1] * r[2] for r in last) / len(last)
        if dv >= min_dollar_vol:
            out[t] = names[t]
    for t in extra:
        t = t.upper().replace('.', '-')
        if t in names and not FUND.search(names[t] or ''):
            out.setdefault(t, names[t])
    return out


def bars(payload):
    """Yahoo chart JSON → [(date, open, high, low, close, volume)] (incomplete bars dropped)."""
    res = ((payload.get('chart') or {}).get('result') or [None])[0]
    if not res:
        raise ValueError('no chart result')
    ts = res.get('timestamp') or []
    q = ((res.get('indicators') or {}).get('quote') or [{}])[0]
    out = []
    for i, t in enumerate(ts):
        o, h, l, c, v = (q.get(k, [None] * len(ts))[i] for k in ('open', 'high', 'low', 'close', 'volume'))
        if None in (h, l, c) or c <= 0:
            continue
        out.append((dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat(), o, h, l, c, v or 0))
    return out


def fetch(sym, rng, iv, timeout=25):
    req = urllib.request.Request(CHART.format(sym=sym, rng=rng, iv=iv), headers={'User-Agent': UA, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return bars(json.loads(r.read().decode('utf-8')))


def stats(b, asof=None):
    """One stock's numbers from a year of daily bars (the last bar = the session), or None when too short or stale."""
    if len(b) < 60:
        return None
    d, o, h, l, c, v = b[-1]
    if asof and d != asof:
        return None
    prior = b[-252:-1]
    hi_prior, lo_prior = max(x[2] for x in prior), min(x[3] for x in prior)
    hi52, lo52 = max(hi_prior, h), min(lo_prior, l)
    year = d[:4]
    base = next((x[4] for x in reversed(b[:-1]) if x[0][:4] < year), None)
    m1 = b[-22][4] if len(b) > 22 else None
    peak = max(prior + [b[-1]], key=lambda x: x[2])
    trough = min(prior + [b[-1]], key=lambda x: x[3])
    dvol = sum(x[4] * x[5] for x in b[-20:]) / min(20, len(b))
    return {'date': d, 'close': _r(c, 4), 'chg1d': _r(c / b[-2][4] - 1, 4), 'hi52': _r(hi52, 4), 'lo52': _r(lo52, 4),
            'from_hi': _r(c / hi52 - 1, 4), 'from_lo': _r(c / lo52 - 1, 4), 'ytd': _r(c / base - 1, 4) if base else None,
            'm1': _r(c / m1 - 1, 4) if m1 else None, 'day_hi': _r(h, 4), 'day_lo': _r(l, 4), 'dollar_vol': round(dvol),
            'new_hi': int(h > hi_prior), 'new_lo': int(l < lo_prior), 'peak_date': peak[0], 'trough_date': trough[0]}


def all_time(monthly, s):
    """(all-time high?, all-time low?, the earlier record high, the earlier record low, first month) from monthly bars;
    the current month is left out of the earlier records."""
    if not monthly:
        return None, None, None, None, None
    cur = s['date'][:7]
    earlier = [m for m in monthly if m[0][:7] < cur]
    if not earlier:
        return None, None, None, None, monthly[0][0]
    hi_prev, lo_prev = max(m[2] for m in earlier), min(m[3] for m in earlier)
    return int(s['day_hi'] > hi_prev), int(s['day_lo'] < lo_prev), _r(hi_prev, 4), _r(lo_prev, 4), monthly[0][0]


def session_date(today=None):
    """The last weekday on or before today (the session the bars should end on)."""
    d = today or dt.datetime.now(dt.timezone.utc).date()
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d.isoformat()


def collect(client, root, cfg=None):
    """Fetch, compute, and keep the result in cache/extremes/latest.json; publish() writes the public file."""
    cfg = cfg or {}
    root = Path(root)
    t0 = time.time()
    hot = [r.get('ticker') for r in (read_json(root / 'market' / 'reddit.json', {}).get('rows') or [])[:30]]
    names = universe(root, cfg.get('min_price', 3.0), cfg.get('min_dollar_vol', 10e6), extra=[t for t in hot if t])
    budget = float(cfg.get('minutes', 8)) * 60
    rows, errors, stale = {}, [], 0

    def one(t):
        if time.time() - t0 > budget:
            return t, None, 'budget'
        try:
            return t, fetch(t, '1y', '1d'), None
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                time.sleep(3)
            return t, None, f'HTTP {exc.code}'
        except Exception as exc:
            return t, None, str(exc)[:60]

    got = {}
    with ThreadPoolExecutor(int(cfg.get('workers', 8))) as pool:
        for t, b, err in pool.map(one, sorted(names)):
            if b:
                got[t] = b
            elif err and err != 'budget':
                errors.append(f'{t}: {err}')
    # the session: the most common last bar date (a stock that did not trade today is stale, not a new low)
    last = {}
    for b in got.values():
        if b:
            last[b[-1][0]] = last.get(b[-1][0], 0) + 1
    asof = max(last.items(), key=lambda kv: kv[1])[0] if last else session_date()
    for t, b in got.items():
        s = stats(b, asof)
        if s is None:
            stale += 1
            continue
        rows[t] = s
    # all-time check for the stocks at a 52-week extreme today
    cands = [t for t, s in rows.items() if s['new_hi'] or s['new_lo']]

    def hist(t):
        try:
            return t, fetch(t, 'max', '1mo')
        except Exception as exc:
            return t, exc

    with ThreadPoolExecutor(6) as pool:
        for t, m in pool.map(hist, cands[:400]):
            if isinstance(m, Exception):
                errors.append(f'{t} history: {str(m)[:60]}')
                continue
            ath, atl, hp, lp, since = all_time(m, rows[t])
            rows[t].update(ath=ath, atl=atl, ath_prev=hp, atl_prev=lp, since=since)
    out = {'generated_at': now(), 'asof': asof, 'universe': len(names), 'fetched': len(got), 'stale': stale, 'names': names,
           'rows': rows, 'errors': errors[:30], 'seconds': round(time.time() - t0)}
    write_json(root / 'cache' / 'extremes' / 'latest.json', out)
    return {'status': 'ok' if rows else 'error', 'asof': asof, 'stocks': len(rows), 'new_lows': sum(s['new_lo'] for s in rows.values()),
            'new_highs': sum(s['new_hi'] for s in rows.values()), 'errors': errors[:5], 'seconds': out['seconds'], 'updated_at': now()}


def publish(root, market_dir):
    d = read_json(Path(root) / 'cache' / 'extremes' / 'latest.json', {}) or {}
    rows, names = d.get('rows') or {}, d.get('names') or {}
    if not rows:
        return None
    big = lambda t: rows[t]['dollar_vol']
    new_lo = sorted([t for t in rows if rows[t]['new_lo']], key=big, reverse=True)
    new_hi = sorted([t for t in rows if rows[t]['new_hi']], key=big, reverse=True)
    out = {'generated_at': d.get('generated_at'), 'asof': d.get('asof'), 'universe': d.get('universe'), 'stocks': len(rows),
           'fields': ['ticker', 'name'] + FIELDS,
           'rows': [[t, (names.get(t) or '')[:48]] + [rows[t].get(k) for k in FIELDS] for t in sorted(rows)],
           'new_lows': new_lo, 'new_highs': new_hi,
           'ath': [t for t in new_hi if rows[t].get('ath')], 'atl': [t for t in new_lo if rows[t].get('atl')],
           'note': ('Daily bars from Yahoo Finance for the liquid US stocks the Hub follows (funds left out). A new 52-week high or low: the '
                    'session\'s high (low) passed the 251 sessions before it. All-time: passed every earlier month since the first one on file.')}
    write_json(Path(market_dir) / 'extremes.json', out)
    return {'asof': out['asof'], 'new_lows': len(new_lo), 'new_highs': len(new_hi), 'ath': len(out['ath']), 'atl': len(out['atl'])}
