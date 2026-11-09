"""Momentum factors on weekly total-return closes, for stocks and ETFs alike: absolute (time-series) momentum, relative
momentum against a benchmark and a sector, a composite score, and their cross-sectional percentiles month by month.

Inputs: closes on one Friday grid (adjusted for dividends and splits; None where a ticker has no close) — the rotation
history's (rotation_history.py, branch "rotation-history": the site's companies, SPY and the sector / style ETFs) and the
ETF build's (etf.py, branch "etf-history": every US-listed ETF, Yahoo's weekly bars moved to their Friday). Weeks are
the unit: 4 ≈ a month, 13 ≈ a quarter, 26 ≈ six months, 52 ≈ a year. At week t, with P the ticker's close, B the
benchmark's (SPY), S the sector ETF's, ln the natural log:

  absolute
    m12_1   P[t−4] / P[t−52] − 1    twelve-month momentum skipping the latest month (Jegadeesh & Titman 1993; the skip
                                    leaves out the one-month reversal, Jegadeesh 1990)
    m6_1    P[t−4] / P[t−26] − 1    six months, same skip           m3_1   P[t−4] / P[t−13] − 1   three months
    m1      P[t] / P[t−4] − 1       the latest month: short-term reversal, shown, never in a score
    hi52    P[t] / max(P[t−52..t]) − 1    distance from the 52-week high (George & Hwang 2004); needs 26 closes
    vol     √52 × the standard deviation of the 52 weekly log returns to t (annualised; needs 40 of them)
    ra12    m12_1 / max(vol, √52 × 0.4%)    volatility-scaled momentum (Barroso & Santa-Clara 2015; Daniel & Moskowitz 2016)
    comp    the composite momentum score: the mean over w = 13, 26 and 52 weeks of
                ln(P[t−4] / P[t−w]) / (σ × √(w − 4)),   σ = max(vol / √52, 0.4%) (the weekly standard deviation)
            — each horizon's return skipping the latest month, in units of its own standard deviation (a t-statistic of
            the trend), so a slow and a volatile ticker read on one scale; all three horizons are needed. Moskowitz, Ooi
            & Pedersen (2012) scale time-series momentum by volatility; the horizons blend 3-, 6- and 12-month momentum.
            The floor of 0.4% a week (≈ 2.9% a year, app/opportunity.py's for ETFs) keeps a cash-like fund's steady
            yield from reading as an extreme trend (a T-bill fund would score +7σ to +17σ without it); it binds on
            T-bill, floating-rate and ultra-short bond funds only.
  relative
    rel_b   ln(P[t−4] / P[t−52]) − ln(B[t−4] / B[t−52])    12-1 against the benchmark, a log difference
    rel_s   the same against the sector ETF (stocks with a sector; None for ETFs)
    rs      100 × (P[t] / B[t]) ÷ (P[t−52] / B[t−52])      the relative-strength line's one-year change (100 = kept pace)
    rcomp   comp computed on the relative line P / B: relative momentum across the three horizons, in its own σ units
  cross-section (each month end, the last Friday of a month, and the latest week: the newest on which 90% of the
  tickers still trading have a close)
    the percentile (0–100, ties share their mean rank) of m12_1, m6_1, hi52, ra12 and comp among the tickers of a
    universe with a value that week; the last one is the composite momentum rank. Universes: the site's companies
    ('stocks'); ETFs that are neither leveraged nor inverse nor cash-like ('etf', with the rank inside the ETF's
    asset class too).
    The rank of rel_b equals that of m12_1 (the benchmark is the same for all), so it is not ranked separately.

No look-ahead: every figure at week t uses closes up to t only; a month's percentile uses that week's values only.
Survivorship: the universes are today's tickers, so the early years leave out companies and funds that no longer trade.
None of this is a strategy's return (no costs, borrow or taxes): it is the factor's reading for one ticker.
docs/momentum-view.js computes the weekly series in the browser from the same closes by the same formulas
(tests/test_momentum.py and tests/test_momentum_view.cjs pin both to the same numbers).
"""
import datetime as dt
import json
import math
from array import array
from pathlib import Path

VERSION = 1
FIELDS = ['m12_1', 'm6_1', 'hi52', 'ra12', 'comp']           # ranked; the last is the composite momentum rank
LATEST = ['m12_1', 'm6_1', 'm1', 'hi52', 'vol', 'ra12', 'comp', 'rel_b', 'rel_s', 'rcomp']
W_MONTH, W_QUARTER, W_HALF, W_YEAR = 4, 13, 26, 52
HORIZONS = (W_QUARTER, W_HALF, W_YEAR)
MIN_RANKED = 5
VOL_FLOOR = 0.004                                            # the weekly volatility floor of comp and ra12 (≈ 2.9% a year)
NAN = float('nan')


def _ln(x):
    return math.log(x) if x is not None and x > 0 else None


class Prep:
    """a close series with its logs and the prefix sums of its weekly log returns (sum, sum of squares, count), so the
    52-week volatility at any week is O(1)"""
    __slots__ = ('c', 'logs', 's1', 's2', 'cnt')

    def __init__(self, c):
        self.c = c
        self.logs = [_ln(x) for x in c]
        n = len(c)
        s1, s2, cnt = [0.0] * (n + 1), [0.0] * (n + 1), [0] * (n + 1)
        lg = self.logs
        for i in range(n):
            r = lg[i] - lg[i - 1] if i and lg[i] is not None and lg[i - 1] is not None else None
            s1[i + 1] = s1[i] + (r if r is not None else 0.0)
            s2[i + 1] = s2[i] + (r * r if r is not None else 0.0)
            cnt[i + 1] = cnt[i] + (r is not None)
        self.s1, self.s2, self.cnt = s1, s2, cnt

    def wsd(self, t):
        """the weekly standard deviation of the log returns over the 52 weeks to t (None with fewer than 40)"""
        a = max(1, t - W_YEAR + 1)
        k = self.cnt[t + 1] - self.cnt[a]
        if k < 40:
            return None
        s1 = self.s1[t + 1] - self.s1[a]
        s2 = self.s2[t + 1] - self.s2[a]
        var = (s2 - s1 * s1 / k) / (k - 1)
        return math.sqrt(var) if var > 0 else None


def composite(P, t):
    """the composite score at week t (see the module text) or None"""
    if t >= len(P.c) or t < W_YEAR or P.c[t] is None:
        return None
    sw = P.wsd(t)
    l4 = P.logs[t - W_MONTH]
    if not sw or l4 is None:
        return None
    sw = max(sw, VOL_FLOOR)
    z = 0.0
    for w in HORIZONS:
        lw = P.logs[t - w]
        if lw is None:
            return None
        z += (l4 - lw) / (sw * math.sqrt(w - W_MONTH))
    return z / len(HORIZONS)


def factor_at(P, t, B=None, S=None, Q=None):
    """the factor dict at week t (None when the ticker has no close then). P: Prep of the ticker; B, S: of the benchmark
    and the sector (same grid); Q: of the relative line P / B"""
    c, lg = P.c, P.logs
    if t >= len(c) or c[t] is None:
        return None
    f = {}
    p0, p4 = c[t], (c[t - W_MONTH] if t >= W_MONTH else None)
    for key, w in (('m12_1', W_YEAR), ('m6_1', W_HALF), ('m3_1', W_QUARTER)):
        pw = c[t - w] if t >= w else None
        f[key] = (p4 / pw - 1) if p4 and pw else None
    f['m1'] = (p0 / p4 - 1) if p4 else None
    win = [x for x in c[max(0, t - W_YEAR):t + 1] if x]
    f['hi52'] = (p0 / max(win) - 1) if len(win) >= 26 else None
    sw = P.wsd(t)
    f['vol'] = sw * math.sqrt(52) if sw else None
    f['ra12'] = (f['m12_1'] / max(f['vol'], VOL_FLOOR * math.sqrt(52))) if f['m12_1'] is not None and f['vol'] else None
    f['comp'] = composite(P, t)
    for name, X in (('rel_b', B), ('rel_s', S)):
        f[name] = None
        if X is not None and t >= W_YEAR and t < len(X.c):
            a, b, x, y = lg[t - W_MONTH], lg[t - W_YEAR], X.logs[t - W_MONTH], X.logs[t - W_YEAR]
            if None not in (a, b, x, y):
                f[name] = (a - b) - (x - y)
    f['rs'] = None
    if B is not None and t >= W_YEAR and t < len(B.c):
        a, b, x, y = lg[t], lg[t - W_YEAR], B.logs[t], B.logs[t - W_YEAR]
        if None not in (a, b, x, y):
            f['rs'] = 100 * math.exp((a - x) - (b - y))
    f['rcomp'] = composite(Q, t) if Q is not None else None
    return f


def ratio(c, b):
    """the relative line c / b on the same grid (None where either is missing)"""
    return [(x / y) if x and y else None for x, y in zip(c, b)] + [None] * max(0, len(c) - len(b))


def factors(c, b=None, s=None):
    """per-week factor dicts for closes c (None where missing) against the benchmark b and the sector s (lists on the
    same grid, or None); None where c has no close"""
    P = Prep(c)
    B = Prep(b) if b else None
    S = Prep(s) if s else None
    Q = Prep(ratio(c, b)) if b else None
    return [factor_at(P, t, B, S, Q) for t in range(len(c))]


def month_ends(weeks):
    """indices of the last Friday of each calendar month in `weeks` (ISO dates); the current month is not finished"""
    return [i for i in range(len(weeks) - 1) if weeks[i][:7] != weeks[i + 1][:7]]


def ten_month_rule(c, me):
    """{month-end index: the close above the mean of the last 10 month-end closes (this one included)} — Faber (2007)"""
    out = {}
    for j, i in enumerate(me):
        if j < 9 or i >= len(c) or c[i] is None:
            continue
        cl = [c[k] for k in me[j - 9:j + 1] if k < len(c) and c[k] is not None]
        if len(cl) == 10:
            out[i] = c[i] > sum(cl) / 10
    return out


def friday(d):
    """the Friday of a date's week (Monday–Sunday): Yahoo dates its weekly bars by the Monday"""
    return d + dt.timedelta(days=4 - d.weekday())


def friday_grid(start, end):
    a, b = friday(start), friday(end)
    return [(a + dt.timedelta(days=7 * i)).isoformat() for i in range((b - a).days // 7 + 1)]


def on_grid(rows, weeks):
    """[[date, close], …] (any weekday; the last bar of a week wins) → (first index, closes) on the Friday grid, a
    missing week inside the history carried from the week before for at most two weeks; (None, []) without closes"""
    at = {}
    for d, v in rows or []:
        if v is not None and v > 0:
            at[friday(dt.date.fromisoformat(d)).isoformat()] = v
    if not at:
        return None, []
    idx = {w: i for i, w in enumerate(weeks)}
    pos = sorted(idx[w] for w in at if w in idx)
    if not pos:
        return None, []
    f, l = pos[0], pos[-1]
    out, last, gap = [], None, 0
    for i in range(f, l + 1):
        v = at.get(weeks[i])
        if v is None and last is not None and gap < 2:
            v, gap = last, gap + 1
        elif v is not None:
            gap = 0
        out.append(v)
        last = v if v is not None else last
    return f, out


def _pct(values):
    """{key: percentile 0–100} of a {key: value} dict, ties sharing their mean rank; {} with fewer than MIN_RANKED"""
    items = sorted((v, k) for k, v in values.items() if v is not None and math.isfinite(v))
    n = len(items)
    if n < MIN_RANKED:
        return {}
    out, i = {}, 0
    while i < n:
        j = i
        while j + 1 < n and items[j + 1][0] == items[i][0]:
            j += 1
        r = (i + j) / 2
        for k in range(i, j + 1):
            out[items[k][1]] = int(round(100 * r / (n - 1)))
        i = j + 1
    return out


def at_weeks(series, me, L=None, bench=None):
    """the factors of every ticker — series: {ticker: (first index, closes)} on the grid — at the month-end indices `me`
    (the ranked FIELDS only, as one array per field with NaN for none: thousands of tickers × hundreds of months stay
    small) and at the latest index L (every factor, against the benchmark's (first index, closes) for rel_b, rs, rcomp).
    Returns {ticker: ([array per FIELD], factor dict at L or None)}"""
    n = max((f + len(c) for f, c in series.values()), default=0)
    if bench:
        n = max(n, bench[0] + len(bench[1]))
    if L is not None:
        n = max(n, L + 1)
    full = lambda fc: [None] * fc[0] + list(fc[1]) + [None] * (n - fc[0] - len(fc[1]))
    B = Prep(full(bench)) if bench else None
    out = {}
    for t, fc in series.items():
        c = full(fc)
        P = Prep(c)
        lo, hi = fc[0], fc[0] + len(fc[1])
        cols = [array('d', [NAN]) * len(me) for _ in FIELDS]
        for j, i in enumerate(me):
            if lo <= i < hi:
                f = factor_at(P, i)
                if f:
                    for k, key in enumerate(FIELDS):
                        v = f.get(key)
                        if v is not None:
                            cols[k][j] = v
        last = None
        if L is not None and lo <= L < hi:
            last = factor_at(P, L, B, None, Prep(ratio(c, B.c)) if B else None)
        out[t] = (cols, last)
    return out


def percentiles(F, me, members, fields=None):
    """{ticker: [array('b') per field: the percentile 0–100 per month, −1 for none]} for the tickers in `members` at
    the month ends (positions in F's arrays); fields: the FIELDS positions to rank (all by default)"""
    members = [t for t in members if t in F]
    fields = list(range(len(FIELDS))) if fields is None else fields
    table = {t: [array('b', [-1]) * len(me) for _ in fields] for t in members}
    for j in range(len(me)):
        for q, k in enumerate(fields):
            pc = _pct({t: F[t][0][k][j] for t in members})
            for t, v in pc.items():
                table[t][q][j] = v
    return table


def latest_index(series, weeks, share=0.9, live=W_QUARTER):
    """the last grid week on which at least `share` of the live tickers have a close (the newest week of the build may
    hold only some of them); live: a close within `live` weeks of the newest close on file — a ticker that stopped
    trading (or whose prices stopped coming) long ago neither counts nor holds the week back"""
    ends = [f + len(c) - 1 for f, c in series.values() if c]
    if not ends:
        return None
    top = max(ends)
    ends = [e for e in ends if e >= top - live]
    for i in range(min(top, len(weeks) - 1), -1, -1):
        if sum(1 for e in ends if e >= i) >= share * len(ends):
            return i
    return None


def _r(v, d=4):
    return None if v is None or not math.isfinite(v) else round(v, d)


def _rel(series, t, sec, L):
    """12-1 of ticker t against the ticker `sec` (both in series) at week L, a log difference; None when either lacks a close"""
    def lg(x, i):
        f, c = series[x]
        return _ln(c[i - f]) if f <= i < f + len(c) else None
    a, b, x, y = lg(t, L - W_MONTH), lg(t, L - W_YEAR), lg(sec, L - W_MONTH), lg(sec, L - W_YEAR)
    return None if None in (a, b, x, y) else (a - b) - (x - y)


def build(pub, series, weeks, universe, bench=None, sector_of=None, groups=None, name='momentum', start='2005-01-01', meta=None):
    """write pub/<name>/<TICKER>.json (the monthly percentiles since `start`: one row per month end, the last Friday of
    each month, from m0; the browser's grid gives the dates) and pub/<name>-latest.json (the latest
    week: every factor's value and percentile per ticker, for the leaderboards). universe: the tickers ranked; bench:
    the benchmark's (first index, closes); sector_of: {ticker: its sector ETF's ticker in `series`} for rel_s; groups:
    {ticker: a peer group} for a second rank of the composite inside the group; meta: {ticker: {field: value}} copied into
    the latest file. Returns (a summary, {ticker: {column: value}} at the latest week)."""
    pub = Path(pub)
    (pub / name).mkdir(parents=True, exist_ok=True)
    uni = [t for t in dict.fromkeys(universe) if t in series and series[t][1]]
    me = [i for i in month_ends(weeks) if weeks[i] >= start]
    sub = {t: series[t] for t in uni}
    L = latest_index(sub, weeks)
    F = at_weeks(sub, me, L, bench)
    table = percentiles(F, me, uni)
    comp_k = len(FIELDS) - 1
    gtab = {}
    if groups:
        by = {}
        for t in uni:
            if groups.get(t):
                by.setdefault(groups[t], []).append(t)
        for g, ts in by.items():
            if len(ts) >= MIN_RANKED:
                for t, cols in percentiles(F, me, ts, [comp_k]).items():
                    gtab[t] = cols[0]
    written = 0
    for t, cols in table.items():
        rows = [[None if cols[k][j] < 0 else cols[k][j] for k in range(len(FIELDS))] for j in range(len(me))]
        first = next((j for j, r in enumerate(rows) if any(v is not None for v in r)), None)
        if first is None:
            continue
        doc = {'v': VERSION, 't': t, 'universe': name, 'n': len(uni), 'fields': FIELDS, 'm0': weeks[me[first]],     # one row per month end from m0
               'rows': [r if any(v is not None for v in r) else None for r in rows[first:]]}
        if t in gtab:
            doc['group'] = groups.get(t)
            doc['group_comp'] = [None if v < 0 else v for v in list(gtab[t])[first:]]
        (pub / name / f'{t}.json').write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')
        written += 1
    # the latest week: the values (rel_s against the sector ETF) and their percentiles
    latest = {}
    if L is not None:
        vals = {t: F[t][1] for t in uni if F[t][1]}
        pcL = {k: _pct({t: f.get(k) for t, f in vals.items()}) for k in FIELDS}
        gL = {}
        if groups:
            for g in {groups.get(t) for t in vals if groups.get(t)}:
                gL.update(_pct({t: vals[t].get('comp') for t in vals if groups.get(t) == g}))
        for t, f in vals.items():
            sec = (sector_of or {}).get(t)
            f = dict(f, rel_s=_rel(series, t, sec, L) if sec and sec in series and sec != t else None)
            latest[t] = [_r(f.get(k)) for k in LATEST] + [pcL[k].get(t) for k in FIELDS] + ([gL.get(t)] if groups else [])
    cols = LATEST + ['p_' + k for k in FIELDS] + (['p_comp_group'] if groups else [])
    mcols = sorted({k for m in (meta or {}).values() for k in (m or {})})
    doc = {'v': VERSION, 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'universe': name,
           'week': weeks[L] if L is not None else None, 'month': weeks[me[-1]] if me else None, 'n': len(latest), 'cols': cols + mcols,
           'rows': {t: r + [((meta or {}).get(t) or {}).get(k) for k in mcols] for t, r in latest.items()},
           'note': ('Values at the latest week (closes to then; the newest week may be partial) and their percentiles (0–100) among '
                    'the universe; p_comp is the composite momentum rank' + (', p_comp_group the same inside the peer group' if groups else '') +
                    '. m12_1 = P[t−4w]/P[t−52w] − 1; comp = mean over 13, 26 and 52 weeks of ln(P[t−4w]/P[t−w]) ÷ (weekly σ × √(w−4)); '
                    'rel_b / rel_s = 12-1 against SPY / the sector ETF (log difference); rcomp = comp of the line P/SPY. Today\'s '
                    'tickers only (survivorship). Not investment advice.')}
    (pub / f'{name}-latest.json').write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')
    return ({'tickers': written, 'months': len(me), 'latest_week': doc['week'], 'ranked_latest': len(latest)},
            {t: dict(zip(cols, r)) for t, r in latest.items()})
