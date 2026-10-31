"""Move odds: how rare an asset's latest move is in its own history, and what followed moves like it — the days in a
band of percentiles around it, and the days at least as extreme — over the next day, week and month.

From the daily bars on the research-paths branch (cache/ohlc/, app/paths.py collect) to public/moves/, which scan.yml
publishes at data/research/paths/moves/; drawn by docs/moves-view.js (every company page, and the hub's Move odds tab,
docs/moves.js):

  a/<KEY>.json  one asset's trading days and daily log returns in whole basis points, compact, so that the browser can
                work out any band, move length, horizon or measure: every valued company (its ticker), the market (SPY,
                QQQ, DIA, IWM, RSP, MDY, and the S&P 500, Nasdaq and Dow indices since 1970 when they are on file:
                IDX-GSPC …), the sector and style ETFs, and an equal-weighted composite of every SIC industry
                (SIC-3674) and SIC major group (SIC-36) with five or more companies on file
  index.json    every asset's latest one-day move, its percentile, its size against its own recent volatility, how often
                moves as large come, its 5- and 21-day moves, and what followed the similar and the more extreme days
                (the hub's leaderboards; the same arithmetic as the view's)
  status.json

Percentiles are mid-ranks among every day on file; "similar" days are within BAND percentile points of the latest
move; "more extreme" days are at least as far out on the same side; returns ahead are close to close, from the day of
the move. Industry composites hold today's companies only (survivors).

    python app/paths.py moves --root P --universe val/public/index.json
"""
import datetime as dt
import json
import math
import re
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import now, write_json             # noqa: E402
import paths as P                             # noqa: E402
import rotation_history as RH                 # noqa: E402

FORMAT = 1
MIN_DAYS = 250                 # an asset is published with a year of trading days or more
BAND = 2.5                     # the index's similar days: within this many percentile points of the latest move
HORIZONS = (1, 5, 10, 21)      # next day, week, two weeks and month (trading days)
VOL_DAYS = 63                  # a move against the volatility of the three months before it
MIN_MEMBERS = 5                # an industry composite needs this many companies, and this many trading on a day
CLIP = (-0.5, 1.0)             # a member's daily return in a composite, at most (a bad print moves no industry)
MARKET = {'SPY': 'S&P 500 (SPY)', 'QQQ': 'Nasdaq-100 (QQQ)', 'DIA': 'Dow Jones Industrials (DIA)', 'IWM': 'Russell 2000 small caps (IWM)',
          'RSP': 'S&P 500 equal weight (RSP)', 'MDY': 'S&P MidCap 400 (MDY)'}
INDEX_NAMES = {'IDX-GSPC': 'S&P 500 index', 'IDX-IXIC': 'Nasdaq Composite index', 'IDX-DJI': 'Dow Jones Industrial Average',
               'IDX-NDX': 'Nasdaq-100 index', 'IDX-RUT': 'Russell 2000 index'}
SECTOR_NAME = {t: n for t, _, n in RH.SECTOR_ETFS}
STYLE_NAME = dict(RH.STYLE_ETFS)
# SIC major groups (the first two digits)
SIC2 = {'01': 'Agricultural production: crops', '02': 'Agricultural production: livestock', '07': 'Agricultural services', '08': 'Forestry',
        '09': 'Fishing, hunting and trapping', '10': 'Metal mining', '12': 'Coal mining', '13': 'Oil and gas extraction',
        '14': 'Mining of nonmetallic minerals', '15': 'Building construction', '16': 'Heavy construction', '17': 'Construction: special trades',
        '20': 'Food and kindred products', '21': 'Tobacco products', '22': 'Textile mill products', '23': 'Apparel', '24': 'Lumber and wood products',
        '25': 'Furniture and fixtures', '26': 'Paper and allied products', '27': 'Printing and publishing', '28': 'Chemicals and allied products',
        '29': 'Petroleum refining', '30': 'Rubber and plastics products', '31': 'Leather products', '32': 'Stone, clay, glass and concrete',
        '33': 'Primary metals', '34': 'Fabricated metal products', '35': 'Industrial machinery and computer equipment',
        '36': 'Electronic and electrical equipment', '37': 'Transportation equipment', '38': 'Instruments; medical and optical goods',
        '39': 'Miscellaneous manufacturing', '40': 'Railroads', '41': 'Local and suburban transit', '42': 'Trucking and warehousing',
        '43': 'Postal service', '44': 'Water transportation', '45': 'Air transportation', '46': 'Pipelines, except natural gas',
        '47': 'Transportation services', '48': 'Communications', '49': 'Electric, gas and sanitary services', '50': 'Wholesale: durable goods',
        '51': 'Wholesale: nondurable goods', '52': 'Building materials and garden supply stores', '53': 'General merchandise stores',
        '54': 'Food stores', '55': 'Auto dealers and gas stations', '56': 'Apparel and accessory stores', '57': 'Home furnishings stores',
        '58': 'Eating and drinking places', '59': 'Miscellaneous retail', '60': 'Banks and depository institutions',
        '61': 'Non-depository credit institutions', '62': 'Brokers, dealers and exchanges', '63': 'Insurance carriers',
        '64': 'Insurance agents and brokers', '65': 'Real estate', '67': 'Holding and investment offices (incl. REITs)', '70': 'Hotels and lodging',
        '72': 'Personal services', '73': 'Business services (incl. software)', '75': 'Auto repair and services', '76': 'Miscellaneous repair services',
        '78': 'Motion pictures', '79': 'Amusement and recreation', '80': 'Health services', '81': 'Legal services', '82': 'Educational services',
        '83': 'Social services', '87': 'Engineering, research and management services', '89': 'Services, not elsewhere classified',
        '99': 'Nonclassifiable'}


# ------------------------------------------------------------------ the compact series
def series(bars):
    """(trading days, adjusted closes) of the bars on file, without missing or non-positive closes."""
    days, closes = [], []
    for d, c in zip((bars or {}).get('t') or [], (bars or {}).get('ac') or []):
        if isinstance(c, (int, float)) and math.isfinite(c) and c > 0:
            days.append(d)
            closes.append(float(c))
    return days, closes


def encode(days, closes):
    """{'d0', 'gaps' | 'dates', 'r'}: the first trading day, the calendar days from each trading day to the next (one
    base-36 character each; the dates themselves when a gap exceeds 35 days) and each day's log return in whole basis
    points (r[k] is the return into day k + 1)."""
    r = np.rint(np.diff(np.log(np.asarray(closes, float))) * 1e4).astype(int)
    ds = [dt.date.fromisoformat(d) for d in days]
    gaps = [(b - a).days for a, b in zip(ds, ds[1:])]
    doc = {'d0': days[0], 'r': r.tolist()}
    if all(1 <= g <= 35 for g in gaps):
        doc['gaps'] = ''.join(np.base_repr(g, 36).lower() for g in gaps)
    else:
        doc['dates'] = list(days)
    return doc


def decode(doc):
    """encode()'s inverse: (trading days, daily log returns as fractions)."""
    if doc.get('dates'):
        days = list(doc['dates'])
    else:
        d = dt.date.fromisoformat(doc['d0'])
        days = [doc['d0']]
        for ch in doc.get('gaps') or '':
            d += dt.timedelta(days=int(ch, 36))
            days.append(d.isoformat())
    return days, np.asarray(doc['r'], float) / 1e4


# ------------------------------------------------------------------ the arithmetic (docs/moves-view.js does the same)
def cum(r):
    """Cumulative log return at each trading day: c[0] = 0, c[i] = r[0] + … + r[i - 1]."""
    return np.concatenate([[0.0], np.cumsum(np.asarray(r, float))])


def moves(c, w):
    """The w-day log move ending at each day (NaN for the first w days)."""
    m = np.full(len(c), np.nan)
    m[w:] = c[w:] - c[:-w]
    return m


def ahead(c, h):
    """The h-day log return after each day, close to close (NaN for the last h days)."""
    f = np.full(len(c), np.nan)
    f[:-h] = c[h:] - c[:-h]
    return f


def pct_ranks(x):
    """Each finite value's mid-rank percentile (0–100) among the finite values of x; NaN elsewhere."""
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    ok = np.isfinite(x)
    v = x[ok]
    if len(v):
        s = np.sort(v)
        lo, hi = np.searchsorted(s, v, 'left'), np.searchsorted(s, v, 'right')
        out[ok] = 100.0 * (lo + 0.5 * (hi - lo)) / len(v)
    return out


def vol_scaled(r, w, n=VOL_DAYS):
    """Each w-day move over the standard deviation of the n daily returns before the move began, scaled to w days
    (NaN without n returns before it): the move in "sigmas" of its own recent volatility."""
    r = np.asarray(r, float)
    c = cum(r)
    m = moves(c, w)
    s1, s2 = cum(r), cum(r * r)
    z = np.full(len(c), np.nan)
    j = np.arange(w + n, len(c))
    if len(j):
        a, b = j - w - n, j - w
        t1, t2 = s1[b] - s1[a], s2[b] - s2[a]
        sd = np.sqrt(np.maximum((t2 - t1 * t1 / n) / (n - 1), 0.0))
        with np.errstate(divide='ignore', invalid='ignore'):
            z[j] = np.where(sd > 0, m[j] / (sd * math.sqrt(w)), np.nan)
    return z


def chosen(p, at, band=BAND, how='similar'):
    """Days (a boolean mask) like the day at percentile `at`: within `band` points of it ('similar') or at least as
    far out on its side of the median ('extreme')."""
    p = np.asarray(p, float)
    ok = np.isfinite(p)
    if how == 'similar':
        return ok & (np.abs(p - at) <= band)
    return ok & ((p >= at) if at >= 50 else (p <= at))


def brief(f):
    """[days, median, share up] of log returns f as simple returns (None when there are none)."""
    f = np.asarray(f, float)
    f = f[np.isfinite(f)]
    if not len(f):
        return None
    s = np.expm1(f)
    return [int(len(s)), float(np.median(s)), float(np.mean(s > 0))]


def first_after(c, j, level, up=True, end=None):
    """The first trading day after j, up to `end`, whose cumulative level c is at or above `level` (up) or at or below
    it; None when there is none."""
    tail = np.asarray(c[j + 1:(len(c) if end is None else end + 1)], float)
    hit = tail >= level if up else tail <= level
    return j + 1 + int(np.argmax(hit)) if hit.any() else None


def recovery(c, idx, w, side, end=None):
    """For each chosen day j (indices idx), the trading days until the close got back to the close before its w-day
    move (side < 0: climbed back; side > 0: gave the rise back) and until a new high (back to the highest close on file up
    to j), each with whether it happened by `end` (else censored there, the days observed). ([times], [events]) twice."""
    c = np.asarray(c, float)
    end = len(c) - 1 if end is None else end
    peak = np.maximum.accumulate(c)
    out = ([], [], [], [])
    for j in idx:
        if j - w < 0 or j >= end:
            continue
        k = first_after(c, j, c[j - w], up=side < 0, end=end)
        out[0].append((k if k is not None else end) - j)
        out[1].append(k is not None)
        k = first_after(c, j, peak[j], up=True, end=end)
        out[2].append((k if k is not None else end) - j)
        out[3].append(k is not None)
    return out


def km(times, events, at=21):
    """Kaplan–Meier over recovery times with censoring: [days, median days (None when half never recovered), share
    recovered within `at` days] (None without days)."""
    t, e = np.asarray(times, float), np.asarray(events, bool)
    if not len(t):
        return None
    order = np.lexsort((~e, t))                         # by time, recoveries before censorings on the same day
    t, e = t[order], e[order]
    s, risk, median, s_at, i = 1.0, len(t), None, 1.0, 0
    while i < len(t):
        j, d = i, 0
        while j < len(t) and t[j] == t[i]:
            d += int(e[j])
            j += 1
        if d:
            s *= 1.0 - d / risk
            if median is None and s <= 0.5:
                median = int(t[i])
        if t[i] <= at:
            s_at = s
        risk -= j - i
        i = j
    return [int(len(t)), median, 1.0 - s_at]


def summary(days, r, band=BAND):
    """The latest day's move against the asset's history: index.json's numbers."""
    c = cum(r)
    last = len(c) - 1
    m1 = moves(c, 1)
    p1 = pct_ranks(m1)
    x, at = m1[last], p1[last]
    out = {'as_of': days[-1], 'd0': days[0], 'n': int(np.isfinite(m1).sum()), 'move': math.expm1(x), 'pct': at}
    side = chosen(p1, at, how='extreme')
    k = int(side.sum())
    out['every'] = out['n'] / k if k else None
    before = np.flatnonzero(side[:last])
    out['last_as'] = days[int(before[-1])] if len(before) else None
    z = vol_scaled(r, 1)
    out['z'] = float(z[last]) if np.isfinite(z[last]) else None
    zp = pct_ranks(z)
    out['zpct'] = float(zp[last]) if np.isfinite(zp[last]) else None
    for w in (5, 21):
        mw = moves(c, w)
        out[f'move{w}'] = math.expm1(mw[last]) if np.isfinite(mw[last]) else None
        out[f'pct{w}'] = float(pct_ranks(mw)[last]) if np.isfinite(mw[last]) else None
    sim, ext = chosen(p1, at, band, 'similar'), side
    for h in HORIZONS:
        f = ahead(c, h)
        out[f'sim{h}'] = brief(f[sim])
        out[f'ext{h}'] = brief(f[ext])
        a = brief(f[np.isfinite(m1)])
        out[f'all{h}'] = a[1:] if a else None
    bt, be, ht, he = recovery(c, np.flatnonzero(sim & (np.arange(len(c)) != last)), 1, -1 if x <= 0 else 1)
    out['back'], out['high'] = km(bt, be), km(ht, he)
    return out


# ------------------------------------------------------------------ industry composites
def composite(members, min_members=MIN_MEMBERS, share=0.6):
    """An equal-weighted daily composite of members [(days, closes)]: each day's mean simple return of the members that
    traded that day and the one before, clipped to CLIP, chained from 100, on the days with min_members of them or
    more and at least `share` of the most that traded on any of the 20 days before (so a day for which only a few
    members' bars are in yet is left out). (days, closes) or None."""
    by_day, firsts = {}, set()
    for ds, cs in members:
        if len(ds) < 2:
            continue
        firsts.add(ds[0])
        cs = np.asarray(cs, float)
        rets = np.clip(cs[1:] / cs[:-1] - 1.0, *CLIP)
        for d, v in zip(ds[1:], rets):
            s = by_day.setdefault(d, [0.0, 0])
            s[0] += float(v)
            s[1] += 1
    every = sorted(by_day)
    counts = [by_day[d][1] for d in every]
    days = [d for i, d in enumerate(every) if counts[i] >= max(min_members, share * max(counts[max(0, i - 20):i + 1]))]
    if not days:
        return None
    anchor = max((d for d in set(every) | firsts if d < days[0]), default=None)   # the trading day before the first return
    level, out_d, out_c = 100.0, ([anchor] if anchor else []), ([100.0] if anchor else [])
    for d in days:
        tot, n = by_day[d]
        if out_d:
            level *= 1.0 + tot / n
        out_d.append(d)
        out_c.append(level)
    return (out_d, out_c) if len(out_d) >= 2 else None


def sic_of(val_dir, cik):
    """(SIC code, industry name) from research-valuation's public/c/<cik>.json (its first few kilobytes)."""
    try:
        with open(Path(val_dir) / 'c' / f'{int(cik)}.json', encoding='utf-8') as f:
            head = f.read(6000)
    except (OSError, ValueError, TypeError):
        return None, None
    m = re.search(r'"sic"\s*:\s*"?(\d{3,4})"?', head)
    n = re.search(r'"industry"\s*:\s*"((?:[^"\\]|\\.)*)"', head)
    code = m.group(1).zfill(4) if m else None
    return code, (json.loads('"' + n.group(1) + '"') if n else None)


# ------------------------------------------------------------------ writing
def _dump(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(doc, separators=(',', ':'), ensure_ascii=False, allow_nan=False), encoding='utf-8')
    tmp.replace(path)


def _r(v, n=4):
    """Floats to n decimals (non-finite ones to None); anything else as it is."""
    if isinstance(v, float):
        return round(float(v), n) if math.isfinite(v) else None
    return v


FIELDS = ['key', 'ticker', 'name', 'kind', 'sector', 'industry', 'cik', 'members', 'as_of', 'd0', 'n', 'last', 'move', 'pct', 'z', 'zpct', 'every',
          'last_as', 'move5', 'pct5', 'move21', 'pct21'] + [f'{s}{h}' for s in ('sim', 'ext', 'all') for h in HORIZONS] + ['back', 'high']


def build(root, universe_path, val_dir=None, limit=0):
    """Write public/moves/ from the bars on file; returns the status."""
    t0 = time.monotonic()
    root = Path(root)
    out = root / 'public' / 'moves'
    val_dir = Path(val_dir) if val_dir else (Path(universe_path).parent if universe_path else None)
    comps = P.universe(universe_path) if universe_path else []
    if limit:
        comps = comps[:limit]
    assets, errors = [], []
    # the market, its indices' long history, the sector and style ETFs
    for t in list(MARKET) + list(INDEX_NAMES) + [x for x, _, _ in RH.SECTOR_ETFS] + [x for x, _ in RH.STYLE_ETFS if x not in MARKET]:
        kind = 'market' if t in MARKET else 'index' if t in INDEX_NAMES else 'sector' if t in SECTOR_NAME else 'style'
        name = MARKET.get(t) or INDEX_NAMES.get(t) or (SECTOR_NAME.get(t) and f'{SECTOR_NAME[t]} sector ({t})') or f'{STYLE_NAME.get(t, t)} ({t})'
        assets.append({'key': t, 'ticker': None if kind == 'index' else t, 'name': name, 'kind': kind,
                       'sector': next((k for x, k, _ in RH.SECTOR_ETFS if x == t), None)})
    # every valued company, with its industry
    sics = {}
    for c in comps:
        code, ind = sic_of(val_dir, c.get('cik')) if val_dir and c.get('cik') else (None, None)
        sics[c['t']] = (code, ind)
        assets.append({'key': c['t'], 'ticker': c['t'], 'name': c.get('name'), 'kind': 'stock', 'sector': c.get('sector'), 'cik': c.get('cik'),
                       'sic': code, 'mcap': c.get('mcap')})
    data = {}
    for a in assets:
        bars = P.load(root, a['key'])
        if not bars:
            continue
        ds, cs = series(bars)
        if len(ds) > MIN_DAYS:
            data[a['key']] = (ds, cs, (bars.get('c') or [None])[-1])
    # composites: SIC industries (four digits) and major groups (two), five companies or more
    groups = {}
    for a in assets:
        if a['kind'] == 'stock' and a['key'] in data and a.get('sic'):
            for key in (f"SIC-{a['sic']}", f"SIC-{a['sic'][:2]}"):
                groups.setdefault(key, []).append(a)
    links = {}
    for key, mem in sorted(groups.items()):
        if len(mem) < MIN_MEMBERS:
            continue
        comp = composite([data[m['key']][:2] for m in mem])
        if not comp or len(comp[0]) <= MIN_DAYS:
            continue
        code = key[4:]
        name = (sics.get(mem[0]['key'], (None, None))[1] if len(code) == 4 else SIC2.get(code)) or f'SIC {code}'
        secs = [m.get('sector') for m in mem if m.get('sector')]
        top = [m['key'] for m in sorted(mem, key=lambda m: -(m.get('mcap') or 0))[:12]]
        assets.append({'key': key, 'ticker': None, 'name': f'{name} (SIC {code})', 'kind': 'industry', 'level': len(code),
                       'sector': max(set(secs), key=secs.count) if secs else None, 'members': len(mem), 'top': top})
        data[key] = (comp[0], comp[1], None)
        for m in mem:
            if len(code) == 4 or m['key'] not in links:
                links[m['key']] = key
    names = {a['key']: a.get('name') for a in assets}
    rows, written = [], set()
    for a in assets:
        if a['key'] not in data:
            continue
        ds, cs, last = data[a['key']]
        try:
            enc = encode(ds, cs)
            days, r = decode(enc)
            s = summary(days, r)
        except Exception as exc:                                        # noqa: BLE001
            errors.append(f"{a['key']}: {str(exc)[:160]}")
            continue
        ln = {}
        if a['kind'] in ('stock', 'industry'):
            if a['kind'] == 'stock' and links.get(a['key']):
                ln['industry'] = links[a['key']]
            if a.get('sector'):
                etf = P.SECTOR_ETF.get(a['sector'])
                if etf and etf in data:
                    ln['sector'] = etf
            ln['market'] = 'SPY'
        doc = {'format': FORMAT, 'key': a['key'], 'ticker': a.get('ticker'), 'name': a.get('name'), 'kind': a['kind'], 'sector': a.get('sector'),
               'cik': a.get('cik'), 'as_of': ds[-1], 'last': last, 'links': ln, 'names': {k: names.get(k, k) for k in ln.values()}, **enc}
        for k in ('members', 'top', 'level', 'sic'):
            if a.get(k) is not None:
                doc[k] = a[k]
        _dump(out / 'a' / f"{a['key']}.json", doc)
        written.add(f"{a['key']}.json")
        s.update(key=a['key'], ticker=a.get('ticker'), name=a.get('name'), kind=a['kind'], sector=a.get('sector'), industry=ln.get('industry'),
                 cik=a.get('cik'), members=a.get('members'), last=last)
        rows.append([[_r(x) for x in v] if isinstance(v, list) else _r(v) for v in (s.get(f) for f in FIELDS)])
    for p in (out / 'a').glob('*.json'):                                # assets no longer on file
        if p.name not in written:
            p.unlink()
    stocks = [r for r in rows if r[FIELDS.index('kind')] == 'stock']
    as_of = max((r[FIELDS.index('as_of')] for r in stocks), default=None)
    today = [r for r in stocks if r[FIELDS.index('as_of')] == as_of and r[FIELDS.index('pct')] is not None]
    pi = FIELDS.index('pct')
    breadth = {'stocks': len(today), 'down5': sum(1 for r in today if r[pi] <= 5) / len(today) if today else None,
               'up5': sum(1 for r in today if r[pi] >= 95) / len(today) if today else None}
    counts = {}
    for r in rows:
        counts[r[FIELDS.index('kind')]] = counts.get(r[FIELDS.index('kind')], 0) + 1
    _dump(out / 'index.json', {'format': FORMAT, 'generated_at': now(), 'as_of': as_of, 'band': BAND, 'horizons': list(HORIZONS),
                               'breadth': {k: _r(v) for k, v in breadth.items()}, 'fields': FIELDS, 'rows': rows})
    status = {'built_at': now(), 'as_of': as_of, 'assets': len(rows), 'counts': counts, 'seconds': round(time.monotonic() - t0, 1),
              'errors': errors[:40]}
    write_json(out / 'status.json', status)
    return status
