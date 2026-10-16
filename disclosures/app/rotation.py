"""Rotation data (4.4) for the momentum clock and the solar system: per company and calendar quarter, a set of variables
the charts can put on any axis —

  profitability  operating, gross and net margin, and each against the same quarter a year earlier (points)
  growth         revenue against a year earlier (%) and its acceleration (this quarter's growth minus last quarter's)
  price          the quarter's return, the return against the S&P 500 (SPY) over one and two quarters, realised volatility
  trading        average daily volume against the company's own average
  ownership      net 13F managers that quarter (buyers − sellers), officials' purchases − sales that quarter

Figures from SEC XBRL frames (frames.py, fourth quarters filled from the annual frames), quarter-end closes and daily
volume from the price cache, 13F from market/by-ticker-history.json, officials from market/officials-trades.json.
Sector suns and the market centre average their companies, weighted by the log of revenue, with every variable clipped
to its 3rd–97th percentile so one outlier does not drag a sun.

Built at publish time (automation/stage-public.py --site-data): the Sankey site's index gives tickers and sectors.
Output is columnar to stay small: 'fields' names the columns of every company's and sun's 'p' rows. A 'monthly' block
(the price-based variables month by month over the last 48 complete months) is split into rotation-monthly.json by the
publish step; the charts draw the quarterly figures through the months between quarter-ends.
"""
import bisect
import datetime as dt
import gzip
import json
import math
import re
from pathlib import Path

import frames as FR

# key, label, unit, centred (True: a change, 0 is neutral; False: a level), group
VARS = [
    ('dom', 'Operating margin vs a year earlier', 'pts', True, 'Profitability'),
    ('om', 'Operating margin', '%', False, 'Profitability'),
    ('dgm', 'Gross margin vs a year earlier', 'pts', True, 'Profitability'),
    ('gm', 'Gross margin', '%', False, 'Profitability'),
    ('dnm', 'Net margin vs a year earlier', 'pts', True, 'Profitability'),
    ('nm', 'Net margin', '%', False, 'Profitability'),
    ('revg', 'Revenue growth vs a year earlier', '%', True, 'Growth'),
    ('reva', 'Revenue growth acceleration', 'pts', True, 'Growth'),
    ('rel', 'Stock vs the S&P 500, the quarter', '%', True, 'Price'),
    ('rel6', 'Stock vs the S&P 500, two quarters', '%', True, 'Price'),
    ('ret', 'Stock return, the quarter', '%', True, 'Price'),
    ('vola', 'Realised volatility (annualised)', '%', False, 'Price'),
    ('volz', 'Trading volume vs its own average', '%', True, 'Trading'),
    ('rs', 'Relative strength rating (1–99)', 'rank', False, 'Price'),
    ('mom121', 'Stock vs the S&P 500 over 12 months, skipping the last', '%', True, 'Price'),
    ('hi52', 'Distance below the 52-week high', '%', False, 'Price'),
    ('f13', 'Net 13F managers (buyers − sellers)', 'managers', True, 'Ownership'),
    ('gov', "Officials' purchases − sales", 'trades', True, 'Ownership'),
    ('pc13', '13F put / call, by value (disclosed options)', 'x', False, 'Options'),
    ('iv30', 'Implied volatility, 30 days (CBOE)', '%', False, 'Options'),
    ('pcoi', 'Put / call open interest (CBOE)', 'x', False, 'Options'),
]
KEYS = [v[0] for v in VARS]
FIELDS = ['cal'] + KEYS + ['rev']
SUN_FIELDS = ['cal'] + KEYS + ['n']


def _rows(root, ticker):
    p = Path(root) / 'cache' / 'prices' / (re.sub(r'[^A-Za-z0-9-]', '_', ticker.upper().replace('.', '-')) + '.json.gz')
    try:
        with gzip.open(p, 'rt', encoding='utf-8') as f:
            return json.load(f)['rows']
    except Exception:
        return None


def _close(rows, day, gap=7):
    i = bisect.bisect_right(rows, [day, float('inf')]) - 1          # rows sorted by date: [date, close(, volume)]
    if i < 0:
        return None
    best = rows[i]
    if (dt.date.fromisoformat(day) - dt.date.fromisoformat(best[0])).days > gap:
        return None
    return best[1]


def _window(rows, start, end):
    lo = bisect.bisect_right(rows, [start, float('inf')])
    hi = bisect.bisect_right(rows, [end, float('inf')])
    return rows[lo:hi]


def _weekly(win):
    """True when the rows are weekly closes (the long history, branch rotation-history) rather than daily ones."""
    if len(win) < 2:
        return False
    d0, d1 = dt.date.fromisoformat(win[0][0]), dt.date.fromisoformat(win[-1][0])
    return (d1 - d0).days / (len(win) - 1) > 3.5


def _volume(win, need=20):
    """Average daily volume in the window; weekly rows hold a week's volume, so they count as five days."""
    v = [r[2] for r in win if len(r) > 2 and r[2]]
    if _weekly(win):
        return sum(v) / len(v) / 5 if len(v) >= max(3, need * 2 // 5) else None
    return sum(v) / len(v) if len(v) >= need else None


def _vola(win, before):
    closes = ([before] if before else []) + [r[1] for r in win if r[1]]
    rets = [math.log(b / a) for a, b in zip(closes, closes[1:]) if a and b and a > 0 and b > 0]
    weekly = _weekly(win)
    if len(rets) < (8 if weekly else 20):
        return None
    m = sum(rets) / len(rets)
    return math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1) * (52 if weekly else 252)) * 100


def _qdates(period):
    """'CY2025Q3' → ('2025-06-30', '2025-09-30'): the previous quarter end and this one."""
    y, q = int(period[2:6]), int(period[-1])
    end = dt.date(y, 3 * q, 1) + dt.timedelta(days=32)
    end = end.replace(day=1) - dt.timedelta(days=1)
    start = dt.date(y, 3 * q - 2, 1) - dt.timedelta(days=1)
    return start.isoformat(), end.isoformat()


def cal_of(day):
    """'2025-09-30' → 'CY2025Q3'."""
    d = dt.date.fromisoformat(day[:10])
    return f'CY{d.year}Q{(d.month - 1) // 3 + 1}'


def _r(v, n=2):
    return None if v is None else round(v, n)


def _margin(num, rev, cap=300):
    if num is None or not rev or rev <= 0:
        return None
    m = 100.0 * num / rev
    return m if abs(m) <= cap else None


def _months_back(day, n):
    d = dt.date.fromisoformat(day)
    y, m = d.year, d.month - n
    while m <= 0:
        y, m = y - 1, m + 12
    return ((dt.date(y, m, 1) + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)).isoformat()


def price_extras(rows, spy, end):
    """At a period's last close: the raw 3/6/9/12-month returns (for the RS rating, weighted 2:1:1:1 like the classic
    rating), the 12-month return against SPY skipping the last month, and how far the close is below its 52-week high."""
    b = _close(rows, end)
    if not b:
        return {}
    ret = lambda n: (lambda a: 100.0 * (b / a - 1) if a else None)(_close(rows, _months_back(end, n)))
    r = [ret(n) for n in (3, 6, 9, 12)]
    out = {'_rs': (0.4 * r[0] + 0.2 * r[1] + 0.2 * r[2] + 0.2 * r[3]) if all(x is not None for x in r) else None}
    a12, a1 = _close(rows, _months_back(end, 12)), _close(rows, _months_back(end, 1))
    s12, s1 = (_close(spy, _months_back(end, 12)), _close(spy, _months_back(end, 1))) if spy else (None, None)
    out['mom121'] = _r(100.0 * (a1 / a12 - 1) - 100.0 * (s1 / s12 - 1)) if a12 and a1 and s12 and s1 else None
    year = _window(rows, _months_back(end, 12), end)
    hi = max((x[1] for x in year if x[1]), default=None)
    out['hi52'] = _r(100.0 * (b / hi - 1)) if hi and len(year) >= (45 if _weekly(year) else 150) else None
    return out


def _avg_in(hist, start, end, i):
    v = [h[i] for h in hist if start < h[0] <= end and h[i] is not None]
    return sum(v) / len(v) if v else None


def series(fig, rows, spy, periods, quarters=16, f13=None, gov=None, opt=None, pc13=None, vol_window=None):
    """Points (dicts keyed by FIELDS) for the periods that have revenue and closes at both quarter ends.
    fig: {period: {'rev', 'oi', 'gp', 'ni'}} (frames.figures for one company); f13 / gov: {period: value}."""
    pts = []
    for i, period in enumerate(periods):
        f = fig.get(period)
        if i < 4 or not f:
            continue
        start, end = _qdates(period)
        a, b = _close(rows, start), _close(rows, end)
        if not a or not b:
            continue
        ago = fig.get(periods[i - 4]) or {}
        p = {'cal': period, 'rev': f['rev']}
        for key, num in (('om', 'oi'), ('gm', 'gp'), ('nm', 'ni')):
            now_, then = _margin(f.get(num), f['rev']), _margin(ago.get(num), ago.get('rev'))
            p[key] = _r(now_)
            p['d' + key] = _r(now_ - then) if now_ is not None and then is not None else None
        if p['gm'] is not None and p['gm'] > 100:
            p['gm'] = p['dgm'] = None
        growth = lambda f1, f0: (100.0 * (f1['rev'] / f0['rev'] - 1)) if f1 and f0 and f0.get('rev') and f0['rev'] > 0 else None
        g = growth(f, ago)
        p['revg'] = _r(g) if g is not None and abs(g) <= 1000 else None
        g1 = growth(fig.get(periods[i - 1]), fig.get(periods[i - 5])) if i >= 5 else None
        p['reva'] = _r(g - g1) if p['revg'] is not None and g1 is not None and abs(g1) <= 1000 else None
        ret = 100.0 * (b / a - 1)
        sa, sb = (_close(spy, start), _close(spy, end)) if spy else (None, None)
        p['ret'] = _r(ret)
        p['rel'] = _r(ret - 100.0 * (sb / sa - 1)) if sa and sb else None
        s2 = _qdates(periods[i - 1])[0]
        a2, sa2 = _close(rows, s2), (_close(spy, s2) if spy else None)
        p['rel6'] = _r(100.0 * (b / a2 - 1) - 100.0 * (sb / sa2 - 1)) if a2 and sa2 and sb else None
        win = _window(rows, start, end)
        p['vola'] = _r(_vola(win, a), 1)
        p['vol'] = _volume(win)
        p['f13'] = (f13 or {}).get(period)
        p['gov'] = (gov or {}).get(period)
        p.update(price_extras(rows, spy, end))
        p['pc13'] = (pc13 or {}).get(period)
        p['iv30'] = _r(_avg_in(opt or [], start, end, 2))
        p['pcoi'] = _r(_avg_in(opt or [], start, end, 3), 3)
        pts.append(p)
    pts = pts[-quarters:]
    vols = [p['vol'] for p in pts if p['vol']]
    avg = sum(vols) / len(vols) if vols else None
    for i, p in enumerate(pts):
        if vol_window:                      # the long history: against the trailing quarters, not 16 years of volume
            w = [q['vol'] for q in pts[max(0, i - vol_window + 1):i + 1] if q['vol']]
            avg = sum(w) / len(w) if len(w) >= min(4, vol_window) else None
        p['volz'] = _r(100.0 * (p['vol'] / avg - 1), 1) if p['vol'] and avg else None
    for p in pts:
        p.pop('vol')
    return pts


MONTH_FIELDS = ['ret', 'rel', 'rel3', 'rel6', 'vola', 'volz', 'rs', 'mom121', 'hi52', 'iv30', 'pcoi']


def last_months(n=48, today=None):
    """The last n complete calendar months, oldest first: ['2022-10', …, '2026-09']."""
    today = today or dt.date.today()
    y, m = today.year, today.month - 1
    out = []
    for _ in range(n):
        if m == 0:
            y, m = y - 1, 12
        out.append(f'{y}-{m:02d}')
        m -= 1
    return out[::-1]


def _month_end(ym, back=0):
    y, m = int(ym[:4]), int(ym[5:]) - back
    while m <= 0:
        y, m = y - 1, m + 12
    return ((dt.date(y, m, 1) + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)).isoformat()


def monthly(rows, spy, months, opt=None, vol_window=None):
    """One row per month (MONTH_FIELDS): the month's return and its return against SPY, against SPY over three and six
    months, realised volatility in the month (annualised) and average daily volume against the company's own average."""
    out, vols = [], []
    for ym in months:
        end, start = _month_end(ym), _month_end(ym, 1)
        b, a = _close(rows, end), _close(rows, start)
        sb = _close(spy, end) if spy else None
        rel = lambda back: (lambda a0, s0: _r(100.0 * (b / a0 - 1) - 100.0 * (sb / s0 - 1)) if a0 and b and s0 and sb else None)(
            _close(rows, _month_end(ym, back)), _close(spy, _month_end(ym, back)) if spy else None)
        win = _window(rows, start, end)
        vol = _volume(win, 12)
        vols.append(vol)
        closes = ([a] if a else []) + [r[1] for r in win if r[1]]
        lr = [math.log(y / x) for x, y in zip(closes, closes[1:]) if x and y and x > 0 and y > 0]
        vola = (math.sqrt(sum((r - sum(lr) / len(lr)) ** 2 for r in lr) / (len(lr) - 1) * 252) * 100) if len(lr) >= 12 else None
        x = price_extras(rows, spy, end)
        out.append([_r(100.0 * (b / a - 1)) if a and b else None, rel(1), rel(3), rel(6), _r(vola, 1), None, x.get('_rs'), x.get('mom121'),
                    x.get('hi52'), _r(_avg_in(opt or [], start, end, 2)), _r(_avg_in(opt or [], start, end, 3), 3)])
    ok = [v for v in vols if v]
    avg = sum(ok) / len(ok) if ok else None
    for i, (row, v) in enumerate(zip(out, vols)):
        if vol_window:
            w = [x for x in vols[max(0, i - vol_window + 1):i + 1] if x]
            avg = sum(w) / len(w) if len(w) >= min(6, vol_window) else None
        row[5] = _r(100.0 * (v / avg - 1), 1) if v and avg else None
    return out


def _quantile(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    return s[min(len(s) - 1, max(0, int(q * (len(s) - 1))))]


def _f13_history(root):
    """{TICKER: {period: net managers}} for the well-covered 13F quarters."""
    try:
        h = json.loads((Path(root) / 'market' / 'by-ticker-history.json').read_text(encoding='utf-8'))
    except Exception:
        return {}
    cov = h.get('coverage') or []
    best = max(cov) if cov else 0
    keep = [i for i, n in enumerate(cov) if best and n >= 0.6 * best]
    cals = [cal_of(p) for p in h.get('periods', [])]
    out = {}
    for t, vals in (h.get('rows') or {}).items():
        out[t.replace('-', '.')] = {cals[i]: vals[i] for i in keep if i < len(vals) and vals[i] is not None}
    # a ticker missing from a covered quarter had no net change that quarter
    out['_covered'] = [cals[i] for i in keep]
    return out


def _gov_history(root):
    """{TICKER: {period: purchases − sales}} from the officials' trades on file, for quarters the file fully covers."""
    try:
        d = json.loads((Path(root) / 'market' / 'officials-trades.json').read_text(encoding='utf-8'))
    except Exception:
        return {}, []
    trades = d.get('trades') or []
    dates = sorted(t['date'] for t in trades if t.get('date'))
    if not dates:
        return {}, []
    first = cal_of(dates[0])
    out = {}
    for t in trades:
        tk = (t.get('ticker_canon') or t.get('ticker') or '').upper().replace('-', '.')
        if not tk or not t.get('date'):
            continue
        k = cal_of(t['date'])
        if k <= first:                       # the earliest quarter is only partly on file
            continue
        sign = 1 if t.get('type') == 'purchase' else -1 if 'sale' in (t.get('type') or '') else 0
        if sign:
            out.setdefault(tk, {})[k] = out.get(tk, {}).get(k, 0) + sign
    covered = sorted({cal_of(x) for x in dates if cal_of(x) > first})
    return out, covered


def rs_ratings(groups):
    """groups: lists of (holder, key) whose holder[key] is a raw weighted return; replaced by its 1–99 percentile."""
    for g in groups:
        vals = sorted(h[k] for h, k in g if h[k] is not None)
        n = len(vals)
        for h, k in g:
            if h[k] is None:
                continue
            if n < 10:
                h[k] = None
                continue
            below = bisect.bisect_left(vals, h[k])
            same = bisect.bisect_right(vals, h[k]) - below
            h[k] = max(1, min(99, round(1 + 98 * (below + same / 2) / n)))


def _options_inputs(root):
    """(daily option history per ticker from the CBOE collector, 13F put/call by value per ticker and calendar quarter)"""
    hist = {}
    try:
        h = json.loads((Path(root) / 'cache' / 'options' / 'history.json').read_text(encoding='utf-8'))
        hist = {t.replace('-', '.'): sorted(rows) for t, rows in h.items()}
    except Exception:
        pass
    pc = {}
    try:
        o = json.loads((Path(root) / 'market' / 'options13f.json').read_text(encoding='utf-8'))
        for r in o.get('rows', []):
            if r.get('ticker') and not r.get('fund'):
                pc[r['ticker'].replace('-', '.')] = {cal_of(p): round(put / call, 3) for p, call, put, *_ in r.get('hist', []) if call}
    except Exception:
        pass
    return hist, pc


def build(site_data, root, top=600, quarters=16, months=48, prices=None, frames_root=None, vol_windows=(None, None)):
    """prices: ticker → rows (default: the daily price cache under root); frames_root: where the XBRL frames are cached
    (default root). The long history (app/rotation_history.py) passes weekly closes since 2000 and its own frames."""
    site_data, root = Path(site_data), Path(root)
    load = prices or (lambda t: _rows(root, t))
    ix = json.loads((site_data / 'index.json').read_text(encoding='utf-8'))
    names = ix.get('sector_names') or {}
    latest = {}
    for r in ix.get('companies', []):
        if r.get('ticker') and (r['cik'] not in latest or (r.get('filed') or '') > (latest[r['cik']].get('filed') or '')):
            latest[r['cik']] = r
    flows = {}
    try:
        f = json.loads((root / 'market' / 'by-ticker.json').read_text(encoding='utf-8'))
        flows = {t.replace('-', '.'): dict(zip(f['fields'], v)) for t, v in f.get('rows', {}).items()}
    except Exception:
        pass
    h13 = _f13_history(root)
    covered13 = set(h13.pop('_covered', []))
    hgov, covered_gov = _gov_history(root)
    opt_hist, pc13 = _options_inputs(root)
    periods = FR.calendar_quarters(quarters + 5)
    figs = FR.figures(frames_root or root, periods)
    spy = load('SPY')
    out = []
    for r in sorted(latest.values(), key=lambda r: -(r.get('revenue') or 0)):
        if len(out) >= top:
            break
        fig = figs.get(str(r['cik']))
        rows = load(r['ticker']) if fig else None
        if not rows:
            continue
        tk = r['ticker'].replace('-', '.')
        f13 = {p: (h13.get(tk) or {}).get(p, 0) for p in covered13}
        gov = {p: (hgov.get(tk) or {}).get(p, 0) for p in covered_gov}
        pts = series(fig, rows, spy, periods, quarters, f13, gov, opt_hist.get(tk), pc13.get(tk), vol_window=vol_windows[0])
        if len(pts) < 3:
            continue
        fl = flows.get(tk) or {}
        out.append({'t': r['ticker'], 'n': r.get('name'), 'cik': r['cik'], 's': r.get('sector') or 'other', 'ind': r.get('industry'),
                    'rev': r.get('revenue'), 'net13f': (fl.get('buyers', 0) - fl.get('sellers', 0)) if fl else None,
                    'usd13f': fl.get('usd_net'), 'pts': pts})
    by_cal = {}
    for co in out:
        for p in co['pts']:
            p['rs'] = p.pop('_rs', None)
            by_cal.setdefault(p['cal'], []).append((p, 'rs'))
    rs_ratings(by_cal.values())
    # clip bounds and robust scales per variable, pooled over every company-quarter
    bounds, meta = {}, []
    for key, label, unit, centred, group in VARS:
        vals = [p[key] for c in out for p in c['pts'] if p.get(key) is not None]
        lo, hi = _quantile(vals, 0.03), _quantile(vals, 0.97)
        q1, q3 = _quantile(vals, 0.25), _quantile(vals, 0.75)
        bounds[key] = (lo, hi)
        meta.append({'key': key, 'label': label, 'unit': unit, 'centred': centred, 'group': group, 'n': len(vals),
                     'lo': _r(lo), 'hi': _r(hi), 'median': _r(_quantile(vals, 0.5)),
                     'scale': _r(((q3 - q1) / 1.349) if vals and q3 is not None and q3 > q1 else None, 4)})
    clip = lambda k, v: None if v is None or bounds[k][0] is None else max(bounds[k][0], min(bounds[k][1], v))

    def average(cos):
        per = {}
        for co in cos:
            w = math.log10(max(co['rev'] or 1e6, 1e6))
            for p in co['pts']:
                a = per.setdefault(p['cal'], {'n': 0, **{k: [0.0, 0.0] for k in KEYS}})
                a['n'] += 1
                for k in KEYS:
                    v = clip(k, p.get(k))
                    if v is not None:
                        a[k][0] += w * v; a[k][1] += w
        rows = []
        for cal, a in sorted(per.items()):
            if a['n'] >= 3:
                rows.append([cal] + [_r(a[k][0] / a[k][1]) if a[k][1] else None for k in KEYS] + [a['n']])
        return rows[-quarters:]

    by_sector = {}
    for co in out:
        by_sector.setdefault(co['s'], []).append(co)
    sun = {s: {'name': names.get(s, s), 'p': average(cos)} for s, cos in by_sector.items()}
    market = {'name': 'Market', 'p': average(out)}
    for co in out:
        co['p'] = [[p.get(k) for k in FIELDS] for p in co.pop('pts')]
    cals = sorted({row[0] for co in out for row in co['p']})[-quarters:]
    months = last_months(months)
    month_rows = {}
    for co in out:
        rows = load(co['t'])
        if rows:
            m = monthly(rows, spy, months, opt_hist.get(co['t'].replace('-', '.')), vol_window=vol_windows[1])
            if sum(1 for r in m if r[1] is not None) >= 6:
                month_rows[co['t']] = m
    ri = MONTH_FIELDS.index('rs')
    rs_ratings([[(r[i], ri) for r in month_rows.values()] for i in range(len(months))])
    return {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'benchmark': 'SPY' if spy else None,
            'fields': FIELDS, 'sun_fields': SUN_FIELDS, 'vars': meta, 'quarters': cals,
            'note': ('Calendar quarters (SEC frames align fiscal quarters to the nearest calendar quarter; a fourth quarter a '
                     'company did not tag on its own is the year minus its first three). Returns run from one calendar '
                     'quarter-end close to the next; "vs the S&P 500" subtracts SPY over the same dates. Margins are against '
                     'revenue; growth and margin changes compare with the same quarter a year earlier. Realised volatility: '
                     'daily log returns in the quarter, annualised. Volume: average daily volume in the quarter against the '
                     "company's own average. 13F: managers that added minus managers that cut, in quarters most managers on "
                     "file have reported. Officials: purchases minus sales in the US House reports on file. Sector suns and "
                     'the market centre weight companies by the log of revenue, each variable clipped to its 3rd–97th '
                     'percentile.'),
            'companies': out, 'sectors': sun, 'market': market,
            'monthly': {'months': months, 'fields': MONTH_FIELDS, 'companies': month_rows}}
