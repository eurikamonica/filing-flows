"""RRG quadrant portfolios back-tested (the hub's Rotation tab → RRG portfolios): what holding the lines that stand in
chosen quadrants of the Relative Rotation Graph — Leading, Weakening, Lagging, Improving, or any mix of them (Improving
+ Lagging, Leading + Lagging …) — would have returned since 2000, against SPY and the group's equal weight; and what a
portfolio bought at a close returned over the holding period after it (the expected return of buying now, as history
has it).

Data: the Move odds' daily adjusted closes (research-paths public/moves/a/<KEY>.json; app/moves.py), in the groups of
the daily rotation research (rrg_research.build_daily): sector ETFs, index ETFs, styles, countries and regions, bonds and
commodities, industry and theme ETFs, the SIC industries (equal-weight composites of today's companies) and the
companies — each line against SPY. Today's lines only (survivorship: a fund closed or a company gone since is not in
them). A day's return counts at most −50% / +100% (momentum_backtest.CLIP). A day a line does not trade, it keeps its
value.

RRG: the chart's formula (rrg_research.states) on two clocks
  weekly  each week's last close; RS smoothed over 4 weeks, trend n = 14 weeks, scaled over max(52, 3n) weeks; held 1,
          4 or 13 weeks
  daily   every close; 5 days, n = 21 days, max(252, 3n) days; held 1, 5 or 21 trading days
Quadrants (rrg_research.quadrants): Leading (RS-Ratio ≥ 100, RS-Momentum ≥ 100), Weakening (≥ 100, < 100), Lagging
(< 100, < 100), Improving (< 100, ≥ 100).

Portfolios: at each close, the lines whose RRG point stands in the mix's quadrants, equal weight, bought at that close
and held K periods (bought and held: the weights drift with prices); the strategy holds the K latest, an equal share of
the money each (Jegadeesh & Titman's overlapping portfolios), so it does not depend on the period it began. A portfolio
with no line holds cash at 0%. Formed from the first close of 2000 on which at least MIN_LINES lines of the group have
an RRG point; measured from max(K) periods later, when every holding period holds all its portfolios. The 15 mixes of
the four quadrants; all four is the group's equal weight — "ew", all four held one period (rebalanced every period).

Trading: each period the oldest portfolio is sold and a new one bought — two-way turnover 2 × (1 − the share of lines
the two have in common) ÷ K a period (from cash to lines, or back, one way: 1 ÷ K), stored per trading day so the page
takes costs off at any rate as for the momentum back-test.

Expected return of buying at a close: every portfolio's value K periods after it was bought, when the outcome is known
and the portfolio held a line — the mean with a 95% interval from the portfolios that do not overlap (one every K
periods), the median, the share up, the shares ahead of SPY and of the group's equal weight over the same K periods and
their means — from the start, over the last ten and the last five years.

Out (public/backtest/rrg/): index.json (the groups, their lines, the clocks and holding periods) and one
<clock>-<group>.json each, schema rrg-backtest.v1 — the momentum back-test's shape (months, series of month-end values
of $1, stats per period, turn, held) with invested, expect and now (each line's latest RS-Ratio, RS-Momentum, quadrant
and the periods it has stood there).

    python app/rrg_backtest.py --root pth          (after app/paths.py moves; writes pth/public/backtest/rrg/)
"""
from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import momentum_backtest as MB  # noqa: E402
import paths as P  # noqa: E402
import rrg_research as RR  # noqa: E402

SCHEMA = 'rrg-backtest.v1'
QN = RR.QN                                       # 0 leading, 1 weakening, 2 lagging, 3 improving
MIXES = [c for n in (1, 2, 3, 4) for c in itertools.combinations(range(4), n)]
CLOCKS = {'w': {'holds': (1, 4, 13), 'per_year': 52, 'label': 'Weekly RRG (each week\'s last close)'},
          'd': {'holds': (1, 5, 21), 'per_year': 252, 'label': 'Daily RRG (every close)'}}
FIRST = '2000-01-03'                             # the first close a portfolio is formed
WARM = '1998-12-01'                              # the closes before it the RRG needs
MIN_LINES = 4
CHUNK = 400                                      # lines per RRG pass (memory)
GROUPS = [('sectors', 'Sector ETFs against the S&P 500'),
          ('index_etfs', 'Index ETFs against the S&P 500 (QQQ, DIA, IWM, MDY, RSP)'),
          ('styles', 'Style ETFs (growth, value, momentum, low volatility, small caps) against the S&P 500'),
          ('world', 'Countries and regions (ETFs in dollars) against the S&P 500'),
          ('bonds_commodities', 'Bonds and commodities against the S&P 500'),
          ('industry_etfs', 'Industry and theme ETFs against the S&P 500'),
          ('industries', 'SIC industries (equal-weight, today\'s companies) against the S&P 500'),
          ('companies', 'Companies against the S&P 500')]
NAMED = {'sectors', 'index_etfs', 'styles', 'world', 'bonds_commodities', 'industry_etfs', 'industries'}


def mix_key(S):
    return '+'.join(QN[k] for k in S)


def group_of(doc):
    """The daily rotation research's group of a Move odds asset (rrg_research.build_daily), or None."""
    k, kind, g = doc.get('key'), doc.get('kind'), doc.get('group')
    if not k or k == 'SPY':
        return None
    if kind == 'sector':
        return 'sectors'
    if k in RR.INDEX_ETFS:
        return 'index_etfs'
    if kind in ('style', 'etf'):
        return {'style': 'styles', 'broad': 'world', 'country': 'world', 'bonds': 'bonds_commodities',
                'commodities': 'bonds_commodities', 'industry': 'industry_etfs'}.get(g)
    if kind == 'industry' and len(str(k)) == 8 and str(k).startswith('SIC-'):
        return 'industries'
    if kind == 'stock':
        return 'companies'
    return None


# ------------------------------------------------------------------ the data
def load(base):
    """(calendar days from WARM, SPY's daily log returns on them, each line's meta {key, ticker, name, group} and its
    daily log returns, lines × days float32 with NaN where it did not trade or was not listed, clipped)."""
    base = Path(base)
    ix = json.loads((base / 'index.json').read_text())
    F = ix['fields']
    keys = list(dict.fromkeys(r[F.index('key')] for r in ix['rows']))     # a key listed twice (USO) read once
    sd, sr = P.decode_returns(json.loads((base / 'a' / 'SPY.json').read_text()))
    cal = [d for d in sd if d >= WARM]
    at = {d: i for i, d in enumerate(cal)}
    spy = np.full(len(cal), np.nan)
    for d, x in zip(sd[1:], sr):
        if d in at:
            spy[at[d]] = x
    rows, meta = [], []
    for k in keys:
        if k == 'SPY':
            continue
        try:
            doc = json.loads((base / 'a' / f'{k}.json').read_text())
            g = group_of(doc)
            if not g:
                continue
            days, r = P.decode_returns(doc)
        except (OSError, ValueError, KeyError):
            continue
        row = np.full(len(cal), np.nan, dtype=np.float32)
        idx = np.fromiter((at.get(d, -1) for d in days[1:]), dtype=np.int64, count=len(r))
        ok = idx >= 0
        row[idx[ok]] = r[ok]
        if not np.isfinite(row).any():
            continue
        rows.append(row)
        meta.append({'key': k, 'ticker': doc.get('ticker') or k, 'name': doc.get('name'), 'group': g})
    L = np.clip(np.vstack(rows), *MB.CLIP) if rows else np.zeros((0, len(cal)), np.float32)
    return cal, spy, meta, L


def levels(L):
    """Lines × days of log returns → value levels, NaN before a line's first return, kept flat on a day without one."""
    have = np.isfinite(L)
    lv = np.exp(np.cumsum(np.where(have, L, 0.0), axis=1, dtype=np.float64))
    return np.where(np.maximum.accumulate(have, axis=1), lv, np.nan)


def grid(cal, clock):
    """The clock's closes: every day, or each week's last trading day (the latest close ends the last week)."""
    if clock == 'd':
        return np.arange(len(cal))
    wk = [dt.date.fromisoformat(d).isocalendar()[:2] for d in cal]
    return np.array([i for i in range(len(cal)) if i == len(cal) - 1 or wk[i + 1] != wk[i]], dtype=np.int64)


def quadrants(C, B, clock):
    """RS-Ratio, RS-Momentum and the quadrant (int8, −1 undefined) of each line against SPY on the clock's grid."""
    p = RR.PARAMS[clock]
    N, T = C.shape
    X = np.full((N, T), np.nan, dtype=np.float32)
    Y = np.full((N, T), np.nan, dtype=np.float32)
    for i in range(0, N, CHUNK):
        a = C[i:i + CHUNK]
        with np.errstate(divide='ignore', invalid='ignore'):
            RS = np.where(np.isfinite(a) & (B[None, :] > 0), 100 * a / B[None, :], np.nan)
        S = RR.states(RS, p['n'], p['sh'], p['long'], p['min_norm'])
        X[i:i + CHUNK], Y[i:i + CHUNK] = S['x'], S['y']
    return X, Y, RR.quadrants(X, Y).astype(np.int8)


# ------------------------------------------------------------------ the portfolios
def portfolios(C, q, first, holds):
    """Every mix's period returns for every holding period, from the lines' levels C and quadrants q (lines × periods,
    on one clock), portfolios formed from period `first` on. {(mix, K): {'r', 'turn' (a period), 'held', 'invested',
    'R' (each portfolio's value K periods on, less 1; NaN when unknown or empty)}}."""
    N, T = C.shape
    kmax = max(holds)
    qv = np.where((q >= 0) & np.isfinite(C), q, -1).astype(np.int8)
    qv[:, :first] = -1
    cnt = np.stack([(qv == k).sum(0) for k in range(4)]).astype(np.float64)          # lines in each quadrant at t
    # U[j, k, t]: Σ over the lines in quadrant k at t of C[t + j] ÷ C[t] (their value j periods on, each bought for 1)
    U = np.full((kmax + 1, 4, T), np.nan)
    U[0] = cnt
    Cs = np.where(np.isfinite(C), C, 1.0)
    for j in range(1, kmax + 1):
        R = Cs[:, j:] / Cs[:, :T - j]
        qj = qv[:, :T - j]
        for k in range(4):
            U[j, k, :T - j] = np.where(qj == k, R, 0.0).sum(0)
    # the quadrant pairs (where a line stood at t − K, where at t), for the names a new portfolio shares with the one sold
    pairs = {}
    for K in holds:
        a, b = qv[:, :T - K].astype(np.int64), qv[:, K:].astype(np.int64)
        ok = (a >= 0) & (b >= 0)
        code = (a * 4 + b) * (T - K) + np.arange(T - K)[None, :]
        pairs[K] = np.bincount(code[ok], minlength=16 * (T - K)).reshape(4, 4, T - K)
        del a, b, ok, code
    out = {}
    for S in MIXES:
        s = list(S)
        n = cnt[s].sum(0)
        with np.errstate(divide='ignore', invalid='ignore'):
            V = np.where(n > 0, U[:, s, :].sum(1) / np.maximum(n, 1), 1.0)              # (kmax + 1) × T, V[0] = 1
        V[0] = 1.0
        rc = V[1:] / V[:-1] - 1                                                        # cohort t, its j-th period
        for K in holds:
            r = np.zeros(T)
            for j in range(1, K + 1):
                r[j:] += np.nan_to_num(rc[j - 1, :T - j])
            r /= K
            inter = pairs[K][np.ix_(s, s)].sum((0, 1))
            na, nb = n[K:], n[:T - K]
            mx = np.maximum(na, nb)
            tv = np.where((na > 0) & (nb > 0), 2 * (1 - inter / np.maximum(mx, 1)), np.where(mx > 0, 1.0, 0.0)) / K
            R = np.where(n > 0, V[K] - 1, np.nan)
            R[T - K:] = np.nan
            out[(S, K)] = {'r': r, 'tv': np.concatenate([np.zeros(K), tv]), 'n': n, 'R': R}
    return out


# ------------------------------------------------------------------ statistics
def stats(r, b, months_end, since, py):
    """From period `since` on: the annual return, volatility, their ratio, the maximum drawdown, the share of months up
    and ahead of SPY, beta and alpha against SPY (on the clock's periods)."""
    x, bb = r[since:], b[since:]
    if len(x) < max(20, py // 2):
        return None
    v = np.cumprod(1 + x)
    cagr = v[-1] ** (py / len(x)) - 1
    vol = float(np.std(x, ddof=1) * math.sqrt(py))
    dd = float(np.min(v / np.maximum.accumulate(v)) - 1)
    me = [i - since for i in months_end if i >= since]
    vm = np.concatenate([[1.0], v[me]])
    bm = np.concatenate([[1.0], np.cumprod(1 + bb)[me]])
    mr, br = vm[1:] / vm[:-1] - 1, bm[1:] / bm[:-1] - 1
    cov = np.cov(x, bb, ddof=1)
    beta = float(cov[0, 1] / cov[1, 1]) if cov[1, 1] > 0 else None
    alpha = float((np.mean(x) - (beta or 0) * np.mean(bb)) * py) if beta is not None else None
    return {'cagr': MB._r(cagr), 'vol': MB._r(vol), 'ratio': MB._r(cagr / vol if vol > 0 else None, 2), 'mdd': MB._r(dd),
            'up': MB._r(float(np.mean(mr > 0))) if len(mr) else None, 'ahead': MB._r(float(np.mean(mr > br))) if len(mr) else None,
            'beta': MB._r(beta, 2), 'alpha': MB._r(alpha), 'total': MB._r(v[-1] - 1, 3)}


def expect(R, Rb, Re, since, K):
    """The portfolios bought from period `since` on, K periods later: their mean (95% interval from one portfolio every
    K periods), median, share up, share ahead of SPY and of the group's equal weight bought the same day, the means of
    those two and the mean gaps to them."""
    t = np.arange(len(R))
    m = (t >= since) & np.isfinite(R) & np.isfinite(Rb) & np.isfinite(Re)
    if m.sum() < 10:
        return None
    x, xb, xe = R[m], Rb[m], Re[m]
    idx = np.flatnonzero(m)
    ind = R[idx[(idx - idx[0]) % K == 0]]
    se = float(np.std(ind, ddof=1) / math.sqrt(len(ind))) if len(ind) > 2 else None
    mu = float(np.mean(x))
    return {'n': int(m.sum()), 'n_indep': int(len(ind)), 'mean': MB._r(mu, 5), 'lo': MB._r(mu - 1.96 * se, 5) if se is not None else None,
            'hi': MB._r(mu + 1.96 * se, 5) if se is not None else None, 'median': MB._r(float(np.median(x)), 5),
            'up': MB._r(float(np.mean(x > 0))), 'beat': MB._r(float(np.mean(x > xb))), 'spy': MB._r(float(np.mean(xb)), 5),
            'excess': MB._r(float(np.mean(x - xb)), 5), 'beat_ew': MB._r(float(np.mean(x > xe))), 'ew': MB._r(float(np.mean(xe)), 5),
            'excess_ew': MB._r(float(np.mean(x - xe)), 5)}


def dwell(q):
    """Periods each line has stood in its latest quadrant (counting the latest)."""
    last = q[:, -1:]
    same = (q == last)[:, ::-1]
    run = np.where(same.all(1), q.shape[1], np.argmin(same, axis=1))
    return run


# ------------------------------------------------------------------ one group on one clock
def build_group(cal, spy_lv, meta, lv, clock, key, label, log=print):
    cfg = CLOCKS[clock]
    holds, py = cfg['holds'], cfg['per_year']
    g = grid(cal, clock)
    days = [cal[i] for i in g]
    C, B = lv[:, g], spy_lv[g]
    N, T = C.shape
    X, Y, q = quadrants(C, B, clock)
    defined = (q >= 0).sum(0)
    f0 = next((i for i, d in enumerate(days) if d >= FIRST), None)
    first = next((t for t in range(f0, T) if defined[t] >= min(MIN_LINES, N)), None) if f0 is not None else None
    kmax = max(holds)
    if first is None or T - (first + kmax) < max(20, py // 2):
        return None
    start = first + kmax
    res = portfolios(C, q, first, holds)
    b = np.concatenate([[0.0], B[1:] / B[:-1] - 1])
    months_end = [i for i in range(start, T) if i == T - 1 or days[i][:7] != days[i + 1][:7]]
    last = dt.date.fromisoformat(days[-1])
    since = {}
    for pname, yrs in MB.PERIODS:
        if yrs is None:
            since[pname] = start
        else:
            cut = last.replace(year=last.year - yrs).isoformat()
            since[pname] = max(start, next((i for i, d in enumerate(days) if d > cut), start))
    per_day = py / 252.0                                     # turnover a period → a trading day
    doc = {'schema': SCHEMA, 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
           'as_of': days[-1], 'clock': clock, 'clock_label': cfg['label'], 'group': key, 'label': label, 'lines': N,
           'start': days[start], 'formed_from': days[first], 'holds': list(holds), 'per_year': py,
           'quadrants': list(QN), 'mixes': [mix_key(S) for S in MIXES],
           'rrg': {k: RR.PARAMS[clock][k] for k in ('sh', 'n', 'long', 'min_norm')},
           'months': [days[i] for i in months_end], 'periods': {p: days[i] for p, i in since.items()},
           'traded': [int(defined[i]) for i in months_end],
           'series': {}, 'stats': {}, 'turn': {}, 'held': {}, 'invested': {}, 'expect': {}}

    def put(name, r):
        v = np.cumprod(1 + r[start:])
        doc['series'][name] = [MB._sig(float(v[i - start])) for i in months_end]
        doc['stats'][name] = {p: stats(r, b, months_end, i, py) for p, i in since.items()}
    for (S, K), v in res.items():
        name = f'{mix_key(S)}|{K}'
        put(name, v['r'])
        tv = v['tv'][start:]
        doc['turn'][name] = MB._r(float(np.mean(tv)) * per_day, 5)
        n = v['n'][first:]
        doc['held'][name] = MB._r(float(np.mean(n[n > 0])), 1) if (n > 0).any() else None
        doc['invested'][name] = MB._r(float(np.mean(n > 0)), 3)
        Rb = np.full(T, np.nan)
        Rb[:T - K] = B[K:] / B[:T - K] - 1
        Re = res[((0, 1, 2, 3), K)]['R']                         # the group's equal weight bought the same day
        doc['expect'][name] = {p: expect(v['R'], Rb, Re, i, K) for p, i in since.items()}
    put('spy', b)
    put('ew', res[((0, 1, 2, 3), 1)]['r'])
    # now: each line's latest point
    run = dwell(q)
    named = key in NAMED
    rows = []
    for i in np.flatnonzero(q[:, -1] >= 0):
        m = meta[i]
        row = [m['key'], round(float(X[i, -1]), 2), round(float(Y[i, -1]), 2), int(q[i, -1]), int(run[i])]
        if named:
            row.insert(1, m.get('name') or m['key'])
        rows.append(row)
    rows.sort(key=lambda r: r[0])
    doc['now'] = {'date': days[-1], 'fields': ['key'] + (['name'] if named else []) + ['x', 'y', 'q', 'periods'], 'rows': rows}
    log(f'  rrg backtest {clock}-{key}: {N} lines, {days[first]} … {days[-1]}, {len(rows)} with a point now')
    return doc


def build(base, out_dir, groups=None, clocks=('w', 'd'), log=print):
    t0 = time.monotonic()
    cal, spy, meta, L = load(base)
    log(f'rrg backtest: {len(meta)} lines, {len(cal)} days {cal[0]} … {cal[-1]}')
    spy_lv = levels(spy[None, :])[0]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    index = {'schema': 'rrg-backtest-index.v1', 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
             'as_of': cal[-1], 'quadrants': list(QN), 'mixes': [mix_key(S) for S in MIXES],
             'clocks': {c: {'holds': list(CLOCKS[c]['holds']), 'label': CLOCKS[c]['label']} for c in clocks}, 'groups': []}
    for key, label in GROUPS:
        if groups and key not in groups:
            continue
        rows = [i for i, m in enumerate(meta) if m['group'] == key]
        if len(rows) < 2:
            continue
        lv = levels(L[rows])
        gm = [meta[i] for i in rows]
        entry = {'key': key, 'label': label, 'lines': len(rows), 'clocks': {}}
        for clock in clocks:
            try:
                doc = build_group(cal, spy_lv, gm, lv, clock, key, label, log)
            except Exception as exc:                       # one group never loses the others
                log(f'  rrg backtest {clock}-{key}: {type(exc).__name__} {exc}')
                doc = None
            if not doc:
                continue
            name = f'{clock}-{key}.json'
            tmp = out / (name + '.tmp')
            tmp.write_text(json.dumps(doc, separators=(',', ':'), allow_nan=False), encoding='utf-8')
            tmp.replace(out / name)
            entry['clocks'][clock] = {'file': name, 'start': doc['start'], 'lines_now': len(doc['now']['rows'])}
        if entry['clocks']:
            index['groups'].append(entry)
        del lv
    (out / 'index.json').write_text(json.dumps(index, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    log(f'rrg backtest: {len(index["groups"])} groups to {out} in {time.monotonic() - t0:.0f}s')
    return index


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--root', required=True, help="research-paths' working copy (public/moves/ in, public/backtest/rrg/ out)")
    ap.add_argument('--groups', default='', help='comma-separated group keys (all when empty)')
    a = ap.parse_args()
    root = Path(a.root)
    build(root / 'public' / 'moves', root / 'public' / 'backtest' / 'rrg', [g for g in a.groups.split(',') if g] or None)


if __name__ == '__main__':
    main()
