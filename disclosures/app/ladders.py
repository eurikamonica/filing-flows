"""Closing-price ladders, hour by hour (Consensus tab of each company and index: "Where the close is expected, by date").

Every open Polymarket and Kalshi ladder on where a stock or an index closes on a day, in a week or at the end of a month
("Apple (AAPL) closes above ___ on October 19?", "… closes week of Oct 19 at ___?", "S&P price range on Oct 19 at 4pm EDT")
is read once an hour and every reading is kept:

  ladder    P(close > K) at each listed strike, fitted to fall with the strike → the implied median, the 10% and 90%
            quantiles and the expected value (consensus.ladder_mean: the mass between two strikes at their middle, the two
            tails at the conditional means of the log-normal fitted to the ladder)
  price     the last price of the stock, index or ETF (Yahoo Finance chart API)
  options   the option chain (CBOE delayed quotes, about 15 minutes late) for the expiry on the ladder's date, else the next
            one: that expiry's max pain, call wall (the strike with the most call open interest) and put wall, and the
            options-implied P(close > K) and 80% range at the ladder's date (the digital price: N(d2) at the strike's
            implied volatility, minus vega × the slope of the smile). Index ladders in points use the ETF's chain
            (SPY, QQQ, DIA, IWM) at today's ratio of the two.
  combined  a range from the price, the ladder's expected value, max pain and the walls:
              centre = price + w1 (expected value − price) + w2 (max pain − price)
              range  = the ladder's, the options' and the walls' 80% ranges, averaged (weighted by their interval scores),
                       then widened or narrowed by k so that 80% of past closes fell inside
            w1, w2, the weights and k are fitted on every resolved ladder at the same horizon (≤ 6 hours, 6–24 hours,
            1–3 days, 3–7 days, 1–4 weeks, > 4 weeks); until 20 ladders have resolved at a horizon, priors.

Once the date has passed the official close (Yahoo daily) is attached and every hourly reading is scored (the backtest):
the error of the price, the expected value, the median, max pain and the combined centre; how often the close fell inside
each 80% range; the Brier score of the ladder's and of the options' P(close > K). The combined model is also scored out of
sample (fitted on the earliest 70% of ladders, scored on the latest 30%). Polymarket ladders seen for the first time are
rebuilt hour by hour from their CLOB price history, back to when they were listed — so the backtest starts with the
past weeks, not empty (without the options, which have no history).

Branch ladder-history: cache/m/<YYYY-MM>.json (ladders by the month of their date, with every hourly row),
cache/prices.json, cache/options.json; public/index.json, public/backtest.json and public/t/<TICKER>.json, which the
site reads straight from the branch (data/remote.json → "ladders") so a page is never more than an hour old.

    python app/ladders.py collect --root lad --site-index site/index.json --minutes 8
"""
import argparse
import bisect
import datetime as dt
import json
import math
import re
import sys
import time
import urllib.parse
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import consensus as CS  # noqa: E402
import options as OP  # noqa: E402
from core import read_json, write_json  # noqa: E402

ET = ZoneInfo('America/New_York')
UTC = dt.timezone.utc
IX = {ix['id']: ix for ix in CS.INDICES}
F = ['t', 'spot', 'ev', 'median', 'q10', 'q90', 'mp', 'cw', 'pw', 'oq10', 'omed', 'oq90', 'p', 'op']
BUCKETS = [(0, 6, '≤ 6 hours'), (6, 24, '6–24 hours'), (24, 72, '1–3 days'), (72, 168, '3–7 days'), (168, 744, '1–4 weeks'), (744, 1e9, '> 4 weeks')]
PRIOR = {'w_ev': 0.5, 'w_mp': 0.1, 'rw': {'ladder': 1.0, 'options': 1.0, 'walls': 1.0}, 'k': 1.0, 'basis': 'prior'}
MIN_FIT = 20
HORIZON_DAYS = 120
HISTORY_DAYS = 14
ALPHA = 0.2                                              # 80% ranges
_warned = [0]


def warn(msg):
    """A problem worth seeing in the run's summary (GitHub annotations), the first dozen of each run."""
    print(f'  {msg}', flush=True)
    if _warned[0] < 12 and 'GITHUB_ACTIONS' in __import__('os').environ:
        _warned[0] += 1
        print(f'::warning title=ladders::{msg}', flush=True)


# ------------------------------------------------------------------ time
def utcnow():
    return dt.datetime.now(UTC)


def close_utc(day):
    """16:00 in New York on that day (the close the ladders resolve on), in UTC."""
    d = dt.date.fromisoformat(day)
    return dt.datetime(d.year, d.month, d.day, 16, tzinfo=ET).astimezone(UTC)


def hkey(t):
    return t.astimezone(UTC).strftime('%Y-%m-%dT%H')


def hparse(k):
    return dt.datetime.strptime(k, '%Y-%m-%dT%H').replace(tzinfo=UTC)


def lead_h(k, end):
    return (close_utc(end) - hparse(k)).total_seconds() / 3600


def bucket_of(lead):
    for lo, hi, label in BUCKETS:
        if lo <= lead < hi:
            return label
    return None


def market_hours(t):
    e = t.astimezone(ET)
    return e.weekday() < 5 and (9, 0) <= (e.hour, e.minute) <= (16, 30)


# ------------------------------------------------------------------ which ladders, in which units
def mkey(m):
    return m['url'] if m['source'] == 'polymarket' else f"{m['url']}#{m['kind']}#{m['end']}"


def symbols(m):
    """(Yahoo symbol the ladder is quoted in, the option chain to read) — an index ladder in points reads its ETF's chain."""
    if m.get('index'):
        ix = IX.get(m['index'])
        if not ix:
            return None
        if ix['id'] == 'vix':
            return '^VIX', None
        return (ix['symbol'], ix['etf']) if m.get('points') else (ix['etf'], ix['etf'])
    t = (m.get('ticker') or '').replace('.', '-')
    return (t, t) if re.fullmatch(r'[A-Z]{1,5}(-[A-Z])?', t) else None


def strikes_of_legs(kind, legs):
    """The ladder's strikes from its contracts: "above K" → K; brackets → each bucket's upper edge (as bracket_stats)."""
    if kind == 'above':
        return sorted({lo for lo, hi, _ in legs if lo is not None})
    return sorted({hi for lo, hi, _ in legs if hi is not None and lo != hi})


# ------------------------------------------------------------------ prices (Yahoo chart API)
def _chart(h, sym, rng, interval):
    d = h.json(f'{CS.YQ}/v8/finance/chart/{urllib.parse.quote(sym)}?range={rng}&interval={interval}')
    return d['chart']['result'][0]


def collect_prices(h, cache, syms, now):
    for sym in sorted(syms):
        try:
            r = _chart(h, sym, '60d', '60m')
            q = r['indicators']['quote'][0]['close']
            hourly = {hkey(dt.datetime.fromtimestamp(t + 3600, UTC)): round(v, 4) for t, v in zip(r.get('timestamp') or [], q) if v is not None}
            meta = r.get('meta') or {}
            rd = _chart(h, sym, '1y', '1d')
            qd = rd['indicators']['quote'][0]['close']
            daily = {dt.datetime.fromtimestamp(t, ET).date().isoformat(): round(v, 4) for t, v in zip(rd.get('timestamp') or [], qd) if v is not None}
        except Exception as exc:
            warn(f'yahoo {sym}: {str(exc)[:120]}')
            continue
        old = cache.get(sym) or {}
        keep_h = hkey(now - dt.timedelta(days=150))
        H = {k: v for k, v in (old.get('hourly') or []) if k >= keep_h}
        H.update(hourly)
        D = dict(old.get('daily') or [])
        D.update(daily)
        spot = meta.get('regularMarketPrice')
        cache[sym] = {'at': now.isoformat(timespec='seconds'), 'spot': spot if spot else (sorted(H.items())[-1][1] if H else None),
                      'time': dt.datetime.fromtimestamp(meta['regularMarketTime'], UTC).isoformat() if meta.get('regularMarketTime') else None,
                      'hourly': sorted(H.items()), 'daily': sorted(D.items())[-800:]}
    return cache


def spot_at(px, k):
    """The last price known at hour k (the hourly bar that ended by then), else None."""
    H = (px or {}).get('hourly') or []
    i = bisect.bisect_right([x[0] for x in H], k)
    return H[i - 1][1] if i else None


def close_on(px, day, settle_days=4):
    """The official close of that day; a holiday → the last close before it once a few days have passed."""
    D = dict((px or {}).get('daily') or [])
    if day in D:
        return D[day]
    if (utcnow().astimezone(ET).date() - dt.date.fromisoformat(day)).days >= settle_days:
        before = [k for k in D if k <= day]
        if before and (dt.date.fromisoformat(day) - dt.date.fromisoformat(max(before))).days <= 4:
            return D[max(before)]
    return None


# ------------------------------------------------------------------ options (CBOE delayed quotes)
def _max_pain(rows):
    """The strike where the options' holders are paid least at expiry (prefix sums: O(n log n))."""
    calls = sorted((c['k'], c['oi']) for c in rows if c['type'] == 'C' and c['oi'])
    puts = sorted((c['k'], c['oi']) for c in rows if c['type'] == 'P' and c['oi'])
    ks = sorted({k for k, _ in calls} | {k for k, _ in puts})
    if not ks:
        return None
    ck = [k for k, _ in calls]; pk = [k for k, _ in puts]
    c_oi = [0.0]; c_koi = [0.0]
    for k, o in calls:
        c_oi.append(c_oi[-1] + o); c_koi.append(c_koi[-1] + k * o)
    p_oi = [0.0]; p_koi = [0.0]
    for k, o in puts:
        p_oi.append(p_oi[-1] + o); p_koi.append(p_koi[-1] + k * o)
    best, arg = None, None
    for s in ks:
        i = bisect.bisect_left(ck, s)                    # calls with k < s pay s − k
        pay = s * c_oi[i] - c_koi[i]
        j = bisect.bisect_right(pk, s)                   # puts with k > s pay k − s
        pay += (p_koi[-1] - p_koi[j]) - s * (p_oi[-1] - p_oi[j])
        if best is None or pay < best:
            best, arg = pay, s
    return arg


def expiry_book(spot, chain, today, days=HORIZON_DAYS + 10, band=0.35):
    """Per expiry within the horizon: max pain, call wall, put wall, open interest and the out-of-the-money smile."""
    lo, hi = spot * (1 - band), spot * (1 + band)
    by = {}
    for c in chain:
        try:
            d = (dt.date.fromisoformat(c['exp']) - today).days
        except ValueError:
            continue
        if 0 <= d <= days:
            by.setdefault(c['exp'], []).append(c)
    out = {}
    for e, rows in by.items():
        oi = {}
        for c in rows:
            if lo <= c['k'] <= hi and c['oi']:
                a = oi.setdefault(c['k'], [0, 0])
                a[0 if c['type'] == 'C' else 1] += c['oi']
        cw = max((k for k in oi if oi[k][0]), key=lambda k: oi[k][0], default=None)
        pw = max((k for k in oi if oi[k][1]), key=lambda k: oi[k][1], default=None)
        smile = sorted({c['k']: round(c['iv'], 4) for c in rows if 0.01 < (c['iv'] or 0) < 5 and lo <= c['k'] <= hi and (c['bid'] > 0 or c['oi'] > 0)
                        and ((c['type'] == 'P' and c['k'] <= spot) or (c['type'] == 'C' and c['k'] > spot))}.items())
        out[e] = {'max_pain': _max_pain(rows), 'call_wall': cw, 'put_wall': pw, 'oi_c': sum(v[0] for v in oi.values()),
                  'oi_p': sum(v[1] for v in oi.values()), 'smile': [list(x) for x in smile]}
    return out


def collect_options(h, cache, syms, now):
    open_now = market_hours(now)
    for sym in sorted(syms):
        old = cache.get(sym)
        if old and not open_now and (now - dt.datetime.fromisoformat(old['at'])).total_seconds() < 12 * 3600:
            continue                                     # nothing trades: keep the last chain read
        try:
            payload = h.json(OP.URL.format(sym=OP.cboe_symbol(sym)))
            spot, _, _, chain = OP.parse_chain(payload)
            if not spot or not chain:
                raise RuntimeError('empty chain')
            cache[sym] = {'at': now.isoformat(timespec='seconds'), 'quote_time': payload.get('timestamp'), 'spot': spot,
                          'exps': expiry_book(spot, chain, now.astimezone(ET).date())}
        except Exception as exc:
            warn(f'cboe {sym}: {str(exc)[:120]}')
    return cache


def digital(smile, S, T, cap=0.2):
    """P(S_T > K) at each smile strike: −dC/dK = N(d2) − vega · dσ/dK, the smile's slope from the neighbouring strikes."""
    ks = [k for k, _ in smile]; iv = [v for _, v in smile]
    out = []
    for i, k in enumerate(ks):
        sq = iv[i] * math.sqrt(T)
        if sq <= 0 or k <= 0:
            continue
        d1 = (math.log(S / k) + sq * sq / 2) / sq
        j0, j1 = max(0, i - 1), min(len(ks) - 1, i + 1)
        slope = (iv[j1] - iv[j0]) / (ks[j1] - ks[j0]) if ks[j1] != ks[j0] else 0.0
        vega = S * math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi) * math.sqrt(T)
        corr = max(-cap, min(cap, vega * slope))
        out.append((k, min(1.0, max(0.0, CS._ncdf(d1 - sq) - corr))))
    return out


def interp(ks, ps, k):
    if not ks:
        return None
    if k <= ks[0]:
        return ps[0]
    if k >= ks[-1]:
        return ps[-1]
    i = bisect.bisect_right(ks, k)
    w = (k - ks[i - 1]) / ((ks[i] - ks[i - 1]) or 1)
    return ps[i - 1] + w * (ps[i] - ps[i - 1])


def opt_view(book, end, S, scale, strikes, now):
    """The options' view of one ladder: its expiry (the ladder's date, else the next), max pain, walls, the implied range
    at the ladder's date and P(close > K) at the ladder's strikes."""
    if not book or not book.get('exps') or not S:
        return None
    exps = sorted(book['exps'])
    e = end if end in book['exps'] else next((x for x in exps if x >= end), None)
    if not e:
        return None
    E = book['exps'][e]
    sc = lambda v: None if v is None else round(v * scale, 4)
    v = {'exp': e, 'exact': e == end, 'max_pain': sc(E.get('max_pain')), 'call_wall': sc(E.get('call_wall')), 'put_wall': sc(E.get('put_wall')),
         'oi_c': E.get('oi_c'), 'oi_p': E.get('oi_p'), 'scale': round(scale, 6), 'quote_time': book.get('quote_time')}
    sm = [(k * scale, s) for k, s in E.get('smile') or []]
    if len(sm) >= 4:
        T = max((close_utc(end) - now).total_seconds(), 1800) / (365 * 86400)
        st = CS.ladder_stats(digital(sm, S, T))
        if st:
            v.update({'q10': st['q10']['value'], 'median': st['median']['value'], 'q90': st['q90']['value'],
                      'p': [round(interp(st['strikes'], st['p_above'], k), 4) for k in strikes],
                      'atm_iv': min(sm, key=lambda x: abs(x[0] - S))[1]})
    return v


# ------------------------------------------------------------------ the store: one record per ladder, filed by the month of its date
class Store:
    def __init__(self, root):
        self.dir = Path(root) / 'cache' / 'm'
        self.months = {}
        self.dirty = set()
        if self.dir.exists():
            for p in sorted(self.dir.glob('*.json')):
                self.months[p.stem] = read_json(p, {})

    def get(self, key, end):
        return self.months.get(end[:7], {}).get(key)

    def put(self, rec):
        self.months.setdefault(rec['end'][:7], {})[rec['key']] = rec
        self.dirty.add(rec['end'][:7])

    def all(self):
        return [r for m in self.months.values() for r in m.values()]

    def touch(self, rec):
        self.dirty.add(rec['end'][:7])

    def save(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        for m in self.dirty:
            (self.dir / f'{m}.json').write_text(json.dumps(self.months[m], separators=(',', ':')), encoding='utf-8')


def new_record(m, key):
    sym, opt = symbols(m)
    legs = m.get('legs') or []
    strikes = ((m.get('stats') or {}).get('strikes')) or strikes_of_legs(m['kind'], legs)
    return {'key': key, 'source': m['source'], 'kind': m['kind'], 'ticker': m['ticker'], 'cik': m.get('cik'), 'index': m.get('index'),
            'points': m.get('points'), 'title': m.get('title'), 'url': m.get('url'), 'end': m['end'], 'sym': sym, 'opt': opt,
            'strikes': list(strikes), 'legs': legs, 'rows': [], 'actual': None, 'backfill': 'none' if legs else 'n/a'}


def align(rec, strikes):
    """Grow the record's strike list (Polymarket adds strikes as the price moves) and re-align the stored rows."""
    union = sorted(set(rec['strikes']) | set(strikes))
    if union == rec['strikes']:
        return
    pos = {k: i for i, k in enumerate(rec['strikes'])}
    for r in rec['rows']:
        for j in (12, 13):
            if r[j] is not None:
                r[j] = [r[j][pos[k]] if k in pos else None for k in union]
    rec['strikes'] = union


def make_row(k, S, st, ov, strikes):
    g = lambda q: ((st or {}).get(q) or {}).get('value')
    ps = dict(zip(st['strikes'], st['p_above'])) if st else {}
    o = ov or {}
    r4 = lambda v: None if v is None else round(v, 4)
    return [k, r4(S), r4(g('mean')), r4(g('median')), r4(g('q10')), r4(g('q90')), o.get('max_pain'), o.get('call_wall'), o.get('put_wall'),
            r4(o.get('q10')), r4(o.get('median')), r4(o.get('q90')), [ps.get(x) for x in strikes] if st else None,
            o.get('p') if o.get('p') else None]


def put_row(rec, row):
    rows = rec['rows']
    i = bisect.bisect_left([r[0] for r in rows], row[0])
    if i < len(rows) and rows[i][0] == row[0]:
        rows[i] = row
    else:
        rows.insert(i, row)


def snapshot(store, m, prices, books, now):
    key = mkey(m)
    rec = store.get(key, m['end']) or new_record(m, key)
    if m.get('legs'):
        rec['legs'] = m['legs']
    st = m['stats']
    align(rec, st['strikes'])
    px = prices.get(rec['sym']) or {}
    S = px.get('spot')
    scale = 1.0
    if rec['opt'] and rec['opt'] != rec['sym']:          # an index in points: the ETF's chain at today's ratio
        e = (prices.get(rec['opt']) or {}).get('spot')
        scale = S / e if S and e else None
    ov = opt_view(books.get(rec['opt']), rec['end'], S, scale, rec['strikes'], now) if rec['opt'] and scale else None
    if ov:
        rec['opt_meta'] = {k: ov.get(k) for k in ('exp', 'exact', 'scale', 'quote_time', 'atm_iv', 'oi_c', 'oi_p')}
    put_row(rec, make_row(hkey(now), S, st, ov, rec['strikes']))
    rec['title'], rec['url'], rec['seen'] = m.get('title'), m.get('url'), now.isoformat(timespec='seconds')
    store.put(rec)
    return rec


# ------------------------------------------------------------------ the past hours of a ladder from the CLOB price history
SPAN = {'day': 3, 'week': 9, 'month': 35, 'year': 90}


def period_of(rec):
    t = (rec.get('title') or '').lower()
    return 'week' if 'week' in t else 'year' if re.search(r'(end of|in) \d{4}\b|year[- ]end', t) else 'month' if re.search(r'end of|\bin (january|february|march|april|may|june|july|august|september|october|november|december)\b', t) else 'day' if re.search(r'\bon \w+ \d', t) else 'other'


def backfill(h, rec, prices, budget):
    """Rebuild the hours before the first live reading from each strike's CLOB price history. Returns the requests used."""
    legs = [l for l in rec.get('legs') or [] if l[2]]
    if rec.get('backfill') != 'none' or not legs:
        return 0
    if len(legs) > budget:
        return -1
    end_c = close_utc(rec['end'])
    start = end_c - dt.timedelta(days=SPAN.get(period_of(rec), 60))
    stop = min([end_c] + [hparse(r[0]) for r in rec['rows'][:1]])
    used = 0
    series = []
    days = (stop - start).total_seconds() / 86400
    fid = 60 if days <= 15 else 180 if days <= 45 else 720       # the CLOB refuses long spans at fine resolution
    try:
        for lo, hi, tok in legs:
            q = f'{CS.CLOB}/prices-history?market={tok}&startTs={int(start.timestamp())}&endTs={int(stop.timestamp())}'
            try:
                hist = h.json(q + f'&fidelity={fid}').get('history', [])
            except RuntimeError as e:
                if 'HTTP 400' not in str(e) or fid >= 1440:
                    raise
                hist = h.json(q + '&fidelity=1440').get('history', [])
                used += 1
            used += 1
            series.append({hkey(dt.datetime.fromtimestamp(x['t'], UTC)): float(x['p']) for x in hist if x.get('p') is not None and x.get('t')})
    except Exception as exc:
        warn(f'clob {rec["key"][-50:]}: {str(exc)[:100]}')
        rec['backfill_tries'] = rec.get('backfill_tries', 0) + 1
        if rec['backfill_tries'] >= 3:
            rec['backfill'] = 'failed'
        return used
    have = {r[0] for r in rec['rows']}
    last = [None] * len(legs)
    for k in sorted(set().union(*series)):
        for i, s in enumerate(series):
            if k in s:
                last[i] = s[k]
        if k in have or any(v is None for v in last) or hparse(k) >= stop:
            continue
        st = CS.poly_ladder(rec['kind'], [((lo, hi), p) for (lo, hi, _), p in zip(legs, last)])
        if not st:
            continue
        align(rec, st['strikes'])
        put_row(rec, make_row(k, spot_at(prices.get(rec['sym']), k), st, None, rec['strikes']))
    rec['backfill'] = 'done'
    return used


# ------------------------------------------------------------------ the combined range and the backtest
def rd(r):
    return dict(zip(F, r))


def center(d, P):
    S = d['spot']
    if not S:
        return None
    ev = d['ev'] if d['ev'] else S
    mp = d['mp'] if d['mp'] else S
    return S + P['w_ev'] * (ev - S) + P['w_mp'] * (mp - S)


def intervals(d):
    """The 80% ranges at one reading: (name, middle, low, high)."""
    out = []
    if d['q10'] and d['q90'] and d['median'] and d['q10'] < d['median'] < d['q90']:
        out.append(('ladder', d['median'], d['q10'], d['q90']))
    if d['oq10'] and d['oq90'] and d['omed'] and d['oq10'] < d['omed'] < d['oq90']:
        out.append(('options', d['omed'], d['oq10'], d['oq90']))
    if d['pw'] and d['cw'] and 0 < d['pw'] < d['cw']:
        out.append(('walls', math.sqrt(d['pw'] * d['cw']), d['pw'], d['cw']))
    return out


def combine(d, P):
    c = center(d, P)
    if not c or c <= 0:
        return None
    iv = intervals(d)
    W = sum(P['rw'].get(n, 1.0) for n, *_ in iv)
    if not iv or W <= 0:
        return {'center': c, 'lo': None, 'hi': None}
    lw = sum(P['rw'].get(n, 1.0) * math.log(m / lo) for n, m, lo, hi in iv) / W
    uw = sum(P['rw'].get(n, 1.0) * math.log(hi / m) for n, m, lo, hi in iv) / W
    return {'center': c, 'lo': c * math.exp(-P['k'] * lw), 'hi': c * math.exp(P['k'] * uw)}


def iscore(lo, hi, y):
    """Interval score of an 80% range, relative to the outcome (lower is better: narrow, and the outcome inside)."""
    return ((hi - lo) + (2 / ALPHA) * max(0.0, lo - y) + (2 / ALPHA) * max(0.0, y - hi)) / y


def by_market(groups, fn):
    """Mean of fn over each market's readings, then over markets (every ladder counts once, however long it was open)."""
    vals = []
    for g in groups:
        v = [x for x in (fn(d, g) for d in g['rows']) if x is not None]
        if v:
            vals.append(sum(v) / len(v))
    return (sum(vals) / len(vals) if vals else None), len(vals)


def samples(resolved, per=12):
    out = {}
    for rec in resolved:
        a = rec['actual']
        per_b = {}
        for r in rec['rows']:
            d = rd(r)
            d['lead'] = lead_h(d['t'], rec['end'])
            if d['lead'] < 0 or not d['spot']:
                continue
            per_b.setdefault(bucket_of(d['lead']), []).append(d)
        for b, rows in per_b.items():
            if len(rows) > per:
                rows = [rows[round(i * (len(rows) - 1) / (per - 1))] for i in range(per)]
            out.setdefault(b, []).append({'key': rec['key'], 'end': rec['end'], 'ticker': rec['ticker'], 'actual': a, 'strikes': rec['strikes'], 'rows': rows})
    return out


def _abs_log(c, y):
    return abs(math.log(y / c)) if c and c > 0 and y > 0 else None


def fit(groups):
    best, P = None, dict(PRIOR)
    for a in range(11):
        for b in range(11 - a):
            Q = {'w_ev': a / 10, 'w_mp': b / 10}
            loss, n = by_market(groups, lambda d, g: _abs_log(center(d, Q), g['actual']))
            if loss is not None and (best is None or loss < best - 1e-12):
                best, P = loss, {**P, **Q}
    rw = {}
    for name in ('ladder', 'options', 'walls'):
        s, n = by_market(groups, lambda d, g: next((iscore(lo, hi, g['actual']) for nm, m, lo, hi in intervals(d) if nm == name), None))
        rw[name] = 1 / s if s and n >= 5 else None
    top = max([v for v in rw.values() if v] or [1.0])
    P['rw'] = {k: round(v / top, 3) if v else PRIOR['rw'][k] for k, v in rw.items()}

    def cover(k):
        Q = {**P, 'k': k}
        c, _ = by_market(groups, lambda d, g: (lambda r: None if not r or r['lo'] is None else float(r['lo'] <= g['actual'] <= r['hi']))(combine(d, Q)))
        return c

    lo, hi = 0.2, 6.0
    if cover(hi) is not None:
        for _ in range(30):
            mid = (lo + hi) / 2
            if (cover(mid) or 0) < 1 - ALPHA:
                lo = mid
            else:
                hi = mid
        P['k'] = round(hi, 3)
    P['basis'] = 'backtest'
    return P


def evaluate(groups, P):
    """The backtest numbers of one horizon: errors, how often the close fell inside each 80% range, Brier scores."""
    err = lambda f: by_market(groups, lambda d, g: (lambda v: None if not v else abs(v / g['actual'] - 1))(f(d)))[0]
    comb = lambda d: combine(d, P)
    inside = lambda name: by_market(groups, lambda d, g: next((float(lo <= g['actual'] <= hi) for nm, m, lo, hi in intervals(d) if nm == name), None))[0]

    def brier(d, g, which):
        ps, ops = d['p'] or [], d['op'] or []
        s = [((ps[i] if which == 'ladder' else ops[i]) - (1.0 if g['actual'] > k else 0.0)) ** 2
             for i, k in enumerate(g['strikes']) if i < len(ps) and ps[i] is not None and i < len(ops) and ops[i] is not None]
        return sum(s) / len(s) if s else None

    bl, n_pairs = by_market(groups, lambda d, g: brier(d, g, 'ladder'))
    bo, _ = by_market(groups, lambda d, g: brier(d, g, 'options'))
    ball, _ = by_market(groups, lambda d, g: (lambda s: sum(s) / len(s) if s else None)(
        [(p - (1.0 if g['actual'] > k else 0.0)) ** 2 for p, k in zip(d['p'] or [], g['strikes']) if p is not None]))
    return {'markets': len(groups), 'readings': sum(len(g['rows']) for g in groups),
            'mae': {'price': err(lambda d: d['spot']), 'ev': err(lambda d: d['ev']), 'median': err(lambda d: d['median']),
                    'max_pain': err(lambda d: d['mp']), 'combined': err(lambda d: (comb(d) or {}).get('center'))},
            'inside80': {'ladder': inside('ladder'), 'options': inside('options'), 'walls': inside('walls'),
                         'combined': by_market(groups, lambda d, g: (lambda r: None if not r or r['lo'] is None else float(r['lo'] <= g['actual'] <= r['hi']))(comb(d)))[0]},
            'brier': {'ladder': bl, 'options': bo, 'markets_both': n_pairs, 'ladder_all': ball}}


def backtest(resolved, models=None):
    """Per horizon: the fitted (or prior) model and its numbers; out of sample for the combined range when enough resolved."""
    S = samples(resolved)
    out, fitted = [], {}
    for lo, hi, label in BUCKETS:
        groups = S.get(label) or []
        if models is not None:                           # a company's own ladders, scored with the model fitted on all
            P = models.get(label, PRIOR)
            if groups:
                out.append({'bucket': label, **evaluate(groups, P), 'model': P})
            continue
        P = fit(groups) if len(groups) >= MIN_FIT else dict(PRIOR)
        P['n'] = len(groups)
        fitted[label] = P
        if not groups:
            continue
        row = {'bucket': label, **evaluate(groups, P), 'model': P}
        if len(groups) >= MIN_FIT:
            g2 = sorted(groups, key=lambda g: g['end'])
            cut = int(len(g2) * 0.7)
            Ptr = fit(g2[:cut])
            ev = evaluate(g2[cut:], Ptr)
            row['oos'] = {'train': cut, 'test': len(g2) - cut, 'mae': ev['mae'], 'inside80': ev['inside80']['combined']}
        out.append(row)
    return (fitted if models is None else models), out


# ------------------------------------------------------------------ collect, resolve, publish
def resolve(store, prices, now):
    n = 0
    for rec in store.all():
        if rec.get('actual') is not None or not rec['rows']:
            continue
        if now < close_utc(rec['end']) + dt.timedelta(minutes=40):
            continue
        a = close_on(prices.get(rec['sym']), rec['end'])
        if a:
            rec['actual'], rec['resolved_at'] = a, now.isoformat(timespec='seconds')
            store.touch(rec)
            n += 1
    return n


def prune(store, now):
    old = (now - dt.timedelta(days=180)).date().isoformat()
    gone = (now - dt.timedelta(days=730)).date().isoformat()
    for mon, recs in list(store.months.items()):
        for key, rec in list(recs.items()):
            if rec['end'] < gone:
                del recs[key]; store.dirty.add(mon)
            elif rec['end'] < old and rec['rows'] and rec['rows'][0][12] is not None:
                for r in rec['rows']:
                    r[12] = r[13] = None
                store.dirty.add(mon)


def collect(root, site_index, minutes=8.0, verbose=True):
    t0 = time.time()
    root = Path(root)
    now = utcnow()
    h = CS.Http({'gamma-api.polymarket.com': 0.25, 'clob.polymarket.com': 0.2, 'api.elections.kalshi.com': 0.2,
                 'query2.finance.yahoo.com': 0.6, 'cdn.cboe.com': 0.4})
    mapper = CS.Mapper(CS.universe(site_index))
    found = CS.poly_scan(h, mapper, verbose=verbose, closed_pages=2)
    try:
        found += CS.kalshi_index_scan(h, root, minutes=2, verbose=verbose)
    except Exception as exc:
        warn(f'kalshi: {exc}')
    today = now.astimezone(ET).date()
    far = (today + dt.timedelta(days=HORIZON_DAYS)).isoformat()
    back = (today - dt.timedelta(days=45)).isoformat()
    ladders = [m for m in found if m['kind'] in ('above', 'bracket') and m.get('end') and symbols(m)]
    live = [m for m in ladders if not m['closed'] and m.get('stats') and today.isoformat() <= m['end'] <= far]
    closed = [m for m in ladders if m['closed'] and m['source'] == 'polymarket' and m.get('legs') and back <= m['end'] < today.isoformat()]
    store = Store(root)
    for m in closed:                                     # first seen closed: a record to rebuild from the price history
        key = mkey(m)
        if not store.get(key, m['end']):
            store.put(new_record(m, key))
    syms, opts = set(), set()
    for group, is_live in ((live, True), (closed, False)):
        for m in group:
            s, o = symbols(m)
            syms.add(s)
            if o:
                syms.add(o)
                if is_live:
                    opts.add(o)
            if m.get('index') and IX.get(m['index'], {}).get('etf'):      # both, for the ratio of the index to its ETF
                syms |= {IX[m['index']]['symbol'], IX[m['index']]['etf']}
    prices = collect_prices(h, read_json(root / 'cache' / 'prices.json', {}), syms, now)
    books = collect_options(h, read_json(root / 'cache' / 'options.json', {}), opts, now)
    for m in live:
        snapshot(store, m, prices, books, now)
    used, budget = 0, 600
    waiting = [r for r in store.all() if r.get('backfill') == 'none']
    past = sorted([r for r in waiting if r['end'] < today.isoformat()], key=lambda r: r['end'], reverse=True)   # the backtest first
    todo = past + sorted([r for r in waiting if r['end'] >= today.isoformat()], key=lambda r: r['end'])
    for rec in todo:
        if time.time() - t0 > minutes * 60 * 0.8 or used >= budget:
            break
        u = backfill(h, rec, prices, budget - used)
        if u > 0:
            used += u
            store.touch(rec)
    n_res = resolve(store, prices, now)
    prune(store, now)
    store.save()
    write_json(root / 'cache' / 'prices.json', prices)
    write_json(root / 'cache' / 'options.json', books)
    pub = publish(root, store, prices, now)
    out = {'live': len(live), 'closed_seen': len(closed), 'backfill_requests': used, 'resolved_now': n_res, 'requests': h.calls,
           'minutes': round((time.time() - t0) / 60, 1), **pub}
    write_json(root / 'state.json', {**read_json(root / 'state.json', {}), 'last': out, 'at': now.isoformat(timespec='seconds')})
    return out


def _r(v, d=4):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(v, d)


def _bt_round(rows):
    def rr(o):
        if isinstance(o, dict):
            return {k: rr(v) for k, v in o.items()}
        if isinstance(o, list):
            return [rr(v) for v in o]
        return _r(o, 5) if isinstance(o, float) else o
    return rr(rows)


def page_doc(t, recs, prices, models, now, bt_all=None, n_all=0):
    today = now.astimezone(ET).date().isoformat()
    open_, done = [], []
    fresh = hkey(now - dt.timedelta(hours=6))
    ix = next((r['index'] for r in recs if r.get('index')), None)
    page_sym = IX[ix]['symbol'] if ix else (t.replace('.', '-'))
    for rec in recs:
        if rec.get('actual') is None and rec['end'] >= today and rec['rows'] and rec['rows'][-1][0] >= fresh:
            last = rd(rec['rows'][-1])
            P = models.get(bucket_of(max(0.0, lead_h(last['t'], rec['end']))), PRIOR)
            to_page = 1.0
            if ix and rec['sym'] != page_sym:                # an ETF ladder on an index page: in index points at today's ratio
                a, b = (prices.get(page_sym) or {}).get('spot'), (prices.get(rec['sym']) or {}).get('spot')
                to_page = a / b if a and b else None
            hist = []
            cut = hkey(now - dt.timedelta(days=HISTORY_DAYS))
            for r in rec['rows']:
                if r[0] < cut:
                    continue
                d = rd(r)
                c = combine(d, models.get(bucket_of(max(0.0, lead_h(d['t'], rec['end']))), PRIOR)) or {}
                hist.append([d['t'], d['spot'], d['ev'], d['median'], d['q10'], d['q90'], d['mp'], d['cw'], d['pw'], _r(c.get('center')), _r(c.get('lo')), _r(c.get('hi'))])
            comb = combine(last, P) or {}
            open_.append({'key': rec['key'], 'source': rec['source'], 'kind': rec['kind'], 'title': rec['title'], 'url': rec['url'], 'end': rec['end'],
                          'period': period_of(rec), 'sym': rec['sym'], 'to_page': _r(to_page, 6), 'close_utc': close_utc(rec['end']).isoformat(),
                          'lead_h': _r(lead_h(last['t'], rec['end']), 1), 'as_of': last['t'], 'strikes': rec['strikes'], 'p': last['p'], 'op': last['op'],
                          'spot': last['spot'], 'ev': last['ev'], 'median': last['median'], 'q10': last['q10'], 'q90': last['q90'],
                          'options': {**(rec.get('opt_meta') or {}), 'max_pain': last['mp'], 'call_wall': last['cw'], 'put_wall': last['pw'],
                                      'q10': last['oq10'], 'median': last['omed'], 'q90': last['oq90']} if rec.get('opt') else None,
                          'combined': {'center': _r(comb.get('center')), 'lo': _r(comb.get('lo')), 'hi': _r(comb.get('hi')),
                                       'w_ev': P['w_ev'], 'w_mp': P['w_mp'], 'rw': P['rw'], 'k': P['k'], 'basis': P['basis'], 'n': P.get('n', 0),
                                       'bucket': bucket_of(max(0.0, lead_h(last['t'], rec['end'])))},
                          'history': hist, 'readings': len(rec['rows'])})
        elif rec.get('actual') is not None and rec['rows']:
            rows = [rd(r) for r in rec['rows']]
            last = rows[-1]
            day = next((d for d in reversed(rows) if lead_h(d['t'], rec['end']) >= 24), None)
            done.append({'title': rec['title'], 'url': rec['url'], 'end': rec['end'], 'kind': rec['kind'], 'source': rec['source'], 'actual': rec['actual'],
                         'last': {k: last[k] for k in ('t', 'spot', 'ev', 'median', 'q10', 'q90', 'mp')},
                         'day_before': {k: day[k] for k in ('t', 'spot', 'ev', 'median', 'q10', 'q90', 'mp')} if day else None, 'readings': len(rows)})
    open_.sort(key=lambda m: (m['end'], m['kind'] != 'above'))
    done.sort(key=lambda m: m['end'], reverse=True)
    resolved = [r for r in recs if r.get('actual') is not None and r['rows']]
    _, bt = backtest(resolved, models) if resolved else (None, [])
    px = prices.get(page_sym) or {}
    return {'ticker': t, 'cik': next((r['cik'] for r in recs if r.get('cik')), None), 'index': ix, 'generated_at': now.isoformat(timespec='seconds'),
            'symbol': page_sym, 'spot': px.get('spot'), 'spot_time': px.get('time'),
            'hourly': [x for x in (px.get('hourly') or []) if x[0] >= hkey(now - dt.timedelta(days=HISTORY_DAYS))],
            'open': open_, 'resolved': done[:40], 'backtest': _bt_round(bt), 'resolved_n': len(resolved),
            'backtest_all': _bt_round(bt_all or []), 'resolved_all': n_all, 'buckets': [b[2] for b in BUCKETS]}


def publish(root, store, prices, now):
    pub = Path(root) / 'public'
    (pub / 't').mkdir(parents=True, exist_ok=True)
    recs = store.all()
    resolved = [r for r in recs if r.get('actual') is not None and r['rows']]
    models, bt = backtest(resolved)
    by_t = {}
    for r in recs:
        by_t.setdefault(r['ticker'], []).append(r)
    index = []
    for t, rs in sorted(by_t.items()):
        doc = page_doc(t, rs, prices, models, now, bt, len(resolved))
        if not doc['open'] and not doc['resolved']:
            continue
        (pub / 't' / f'{t.replace(".", "-")}.json').write_text(json.dumps(CS._clean(doc), separators=(',', ':')), encoding='utf-8')
        nxt = doc['open'][0] if doc['open'] else None
        pg = (lambda v: _r(v * nxt['to_page']) if v is not None and nxt.get('to_page') else None) if nxt else (lambda v: None)
        index.append([t, doc['cik'], doc['index'], len(doc['open']), doc['resolved_n'], _r(doc['spot']),
                      nxt['end'] if nxt else None, pg(nxt['ev']) if nxt else None, pg((nxt['combined'] or {}).get('lo')) if nxt else None,
                      pg((nxt['combined'] or {}).get('hi')) if nxt else None])
    note = ('Hourly readings of every Polymarket / Kalshi closing-price ladder; the close from Yahoo Finance; options from CBOE '
            'delayed quotes. Errors are |forecast ÷ close − 1|, each ladder counted once (its readings at that horizon averaged). '
            'Brier: (P(close > K) − outcome)² over the ladder\'s strikes, on readings where the options had a view too.')
    write_json(pub / 'backtest.json', CS._clean({'generated_at': now.isoformat(timespec='seconds'), 'resolved': len(resolved), 'rows': _bt_round(bt),
                                                 'models': _bt_round(models), 'note': note}))
    write_json(pub / 'index.json', CS._clean({'generated_at': now.isoformat(timespec='seconds'),
                                              'fields': ['ticker', 'cik', 'index', 'open', 'resolved', 'spot', 'next_end', 'next_ev', 'next_lo', 'next_hi'],
                                              'rows': index, 'resolved': len(resolved), 'backtest': _bt_round(bt), 'note': note}))
    return {'pages': len(index), 'resolved': len(resolved), 'markets': len(recs)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['collect', 'publish'])
    ap.add_argument('--root', default='lad')
    ap.add_argument('--site-index', default=None)
    ap.add_argument('--minutes', type=float, default=8)
    a = ap.parse_args()
    if a.cmd == 'collect':
        try:
            print(json.dumps(collect(a.root, a.site_index, a.minutes)), flush=True)
        except Exception:
            import traceback
            tb = traceback.format_exc().strip().splitlines()
            print('\n'.join(tb), flush=True)
            print('::error title=ladders::' + ' | '.join(x.strip() for x in tb[-6:])[:900], flush=True)
            raise
    else:
        now = utcnow()
        print(json.dumps(publish(a.root, Store(a.root), read_json(Path(a.root) / 'cache' / 'prices.json', {}), now)), flush=True)


if __name__ == '__main__':
    main()
