"""Strategies: a library of published trading rules tested on the site's weekly history, with trading costs, out-of-sample
splits, overfitting statistics and a live paper ledger (Disclosures → Strategies; rotation-history.yml).

Data (the branch rotation-history, public/): every company's weekly closes since 1990 (t/<T>.json: dividend- and
split-adjusted closes c, the close as traded p, volume v, splits sp), SPY and the sector, style and asset-class ETFs,
the Fed funds rate (macro.json) for cash, and the SEC quarterly figures and month-end market values (rank/). The 13F
crowd strategy also reads the quarter-by-quarter 13F aggregates (docs/data/market/by-ticker-quarters.json).

The engine — one week at a time, decided on a week's close and earned over the next:
  weights     each rule sets target weights on its rebalance weeks (the last Friday of a month, or every week); between
              rebalances the weights drift with prices
  costs       one way, on every change of weight, by the name's weekly dollar volume (13-week mean): 5 bp above $500M a
              week, 15 bp above $50M, 40 bp above $5M, else 100 bp (app/opportunity.py's schedule)
  cash        what is not invested earns the Fed funds rate; borrowed money (weights above 100%) pays it + 0.5% a year;
              short proceeds earn it and shorts pay a 0.5% a year borrow fee
  universe    stocks with a close now and a year ago, a close as traded of at least $5 (splits undone) and at least $5M
              of weekly dollar volume (13-week mean); ETFs from their first full year of data
Parameters are fixed in advance — each rule as its paper published it — never fitted to this history. The grids
of nearby settings (lookbacks, cut-offs, targets) are run only to measure overfitting:
  PBO         the probability of backtest overfitting (Bailey, Borwein, López de Prado and Zhu 2017): the history cut
              into 10 blocks, every half as "in sample" (252 splits), the best setting in sample ranked out of sample;
              PBO = how often it lands in the bottom half
  DSR         the deflated Sharpe ratio (Bailey and López de Prado 2014): the probability that the true Sharpe ratio is
              above zero after allowing for every setting tried here (the trial count), for skew and fat tails
  PSR         the probabilistic Sharpe ratio: the same without the trial count
Out of sample: each rule's performance before and after its paper was published (McLean and Pontiff 2016: anomalies
lose about a third after publication), and the live ledger — each week's positions frozen once the week has closed
(ledger/strategies.json on the data branch), scored on the next weeks' prices, never recomputed.

Survivorship: the stock universe is today's companies only — names delisted, merged or bankrupt are missing, which flatters
every long stock rule (most of all low volatility and long-only momentum). The equal-weighted universe of the same
survivors is shown as their benchmark, and long-short rules are less affected. History and rules, not investment advice.

  python app/strategies.py --public hist/public --ledger hist/ledger/strategies.json --quarters docs/data/market/by-ticker-quarters.json
"""
import argparse
import datetime as dt
import itertools
import json
import math
import warnings
from pathlib import Path

import numpy as np

START = np.datetime64('1995-01-06')          # backtests begin here (cash rates from 1995; five years of closes behind)
MIN_PRICE, MIN_DV = 5.0, 5e6                 # the stock universe: $5 as traded, $5M a week
BORROW, FIN_SPREAD = 0.005, 0.005            # a year: the short borrow fee; the spread over cash on borrowed money
REB_LAG_WEEKS = 13                           # SEC quarterly figures used 13 weeks after the quarter ends (10-Q / 10-K filed)
F13_LAG_DAYS = 46                            # 13F holdings public 45 days after the quarter
WEEK, DAY = np.timedelta64(7, 'D'), np.timedelta64(1, 'D')
ETF_SET = ['SPY', 'IWM', 'QQQ', 'EFA', 'EEM', 'TLT', 'GLD', 'USO']
SECTORS = ['XLK', 'XLY', 'XLP', 'XLV', 'XLF', 'XLE', 'XLB', 'XLI', 'XLU', 'XLC', 'XLRE']


def fin(v):
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)


def cost_one_way(dv):
    """One-way trading cost (a fraction) from weekly dollar volume (opportunity.py's schedule)."""
    dv = np.nan_to_num(dv, nan=0.0)
    return np.where(dv >= 5e8, 0.0005, np.where(dv >= 5e7, 0.0015, np.where(dv >= 5e6, 0.004, 0.01)))


# ------------------------------------------------------------------ data
def _rolling_mean(a, w):
    """Mean over the last w columns (NaN ignored; NaN where fewer than w // 2 values)."""
    x = np.nan_to_num(a, nan=0.0)
    n = np.isfinite(a).astype(float)
    cs = np.cumsum(np.pad(x, ((0, 0), (1, 0))), axis=1)
    cn = np.cumsum(np.pad(n, ((0, 0), (1, 0))), axis=1)
    T = a.shape[1]
    lo = np.maximum(np.arange(T) + 1 - w, 0)
    s = cs[:, np.arange(T) + 1] - cs[:, lo]
    c = cn[:, np.arange(T) + 1] - cn[:, lo]
    with np.errstate(invalid='ignore', divide='ignore'):
        return np.where(c >= max(1, w // 2), s / np.maximum(c, 1), np.nan)


def load(public, quarters_file=None, limit=None, today=None, dividends=False):
    """Every t/<T>.json on one Friday grid → D: tickers, sectors, is_etf, dates, C (adjusted), PX (as traded, splits
    undone), DV (weekly dollar volume), R (weekly simple returns), cost (one-way), rf (weekly cash return), and the SEC
    and 13F panels when on file."""
    public = Path(public)
    today = np.datetime64(today or dt.date.today())
    rrg = json.loads((public / 'rrg.json').read_text())
    g0 = np.datetime64(rrg['start'])
    W = int((today - g0).astype(int) // 7) + 2
    etf_ids = {s['id'] for s in rrg['series'] if not str(s['id']).startswith('s:')} | {'SPY'}
    files = sorted((public / 't').glob('*.json'))
    if limit:
        keep = {f'{t}.json' for t in ETF_SET + SECTORS}
        files = [f for f in files if f.name in keep] + [f for f in files if f.name not in keep][:limit]
    T, S, E, Cs, Ps, DVs, DIVs, PSs = [], [], [], [], [], [], [], []
    for f in files:
        try:
            d = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        t = d.get('t') or f.stem
        c = d.get('c') or []
        i0 = int((np.datetime64(d['start']) - g0).astype(int) // 7)
        n = min(len(c), W - i0)
        if i0 < 0 or n < 60:
            continue
        row = np.full(W, np.nan)
        row[i0:i0 + n] = [x if fin(x) and x > 0 else np.nan for x in c[:n]]
        p = d.get('p') or []
        prow = np.full(W, np.nan)
        if len(p) >= n:
            prow[i0:i0 + n] = [x if fin(x) and x > 0 else np.nan for x in p[:n]]
            if dividends:
                PSs.append(prow.copy())
            undo = np.ones(n)                                   # the close as traded then: later splits undone
            for wk, ratio in d.get('sp') or []:
                if fin(ratio) and ratio > 0 and 0 < wk <= n:
                    undo[:int(wk)] *= ratio
            prow[i0:i0 + n] *= undo
        else:
            prow[i0:i0 + n] = row[i0:i0 + n]
            if dividends:
                PSs.append(prow.copy())
        v = d.get('v') or []
        dvrow = np.full(W, np.nan)
        if len(v) >= n:
            pp = np.array(p[:n] if len(p) >= n else c[:n], dtype=float)
            dvrow[i0:i0 + n] = np.array([x if fin(x) else np.nan for x in v[:n]], dtype=float) * 1e3 * pp
        is_etf = t in etf_ids or d.get('s') in (None, '', 'etf')
        T.append(t); S.append('etf' if is_etf else (d.get('s') or 'other')); E.append(is_etf)
        Cs.append(row); Ps.append(prow); DVs.append(dvrow)
        if dividends:                                           # dividends per share by week (split-adjusted, as p)
            drow = np.zeros(W)
            for wk, amt in d.get('d') or []:
                if fin(amt) and amt > 0 and 0 <= i0 + int(wk) < W:
                    drow[i0 + int(wk)] += amt
            DIVs.append(drow)
    C, PX, DV = np.array(Cs), np.array(Ps), np.array(DVs)
    last = int(np.where(np.isfinite(C).any(0))[0].max()) + 1
    C, PX, DV = C[:, :last], PX[:, :last], DV[:, :last]
    dates = g0 + np.arange(last) * WEEK
    R = np.full_like(C, np.nan)
    with np.errstate(invalid='ignore', divide='ignore'):
        R[:, 1:] = C[:, 1:] / C[:, :-1] - 1
    R = np.clip(R, -0.95, 3.0)                                 # a data glitch never makes or loses a fortune
    dv13 = _rolling_mean(DV, 13)
    D = {'tickers': T, 'sectors': S, 'is_etf': np.array(E), 'dates': dates, 'C': C, 'PX': PX, 'DV': dv13, 'R': R,
         'cost': cost_one_way(dv13), 'ix': {t: i for i, t in enumerate(T)}}
    if dividends:
        D['DIV'] = np.array(DIVs)[:, :last]
        D['PS'] = np.array(PSs)[:, :last]                       # the close split-adjusted (as p), the dividends' basis
    D['rf'] = cash_rate(public, dates)
    D['month_end'] = np.array([(dates[i] + WEEK).astype('datetime64[M]') != dates[i].astype('datetime64[M]') for i in range(len(dates))])
    D['complete'] = np.array([dates[i] + DAY <= today for i in range(len(dates))])   # a Friday's week is closed from Saturday
    D['t0'] = int(np.searchsorted(dates, START))
    have = np.isfinite(C).sum(0)                        # a week is in once closed and nine in ten names have its close
    D['complete'] &= have >= 0.9 * have[-12:].max()
    D['t_end'] = int(np.where(D['complete'])[0].max())     # the last such week: every rule stops there
    D['sec'] = sec_panel(public, D)
    D['f13'] = f13_panel(quarters_file, D) if quarters_file else None
    return D


def cash_rate(public, dates):
    """Weekly cash return from the Fed funds rate (macro.json, monthly from 1995; earlier weeks use the first month)."""
    rf = np.full(len(dates), np.nan)
    try:
        m = json.loads((Path(public) / 'macro.json').read_text())
        lv = m.get('levels') or {}
        if lv.get('bill3m'):
            months, vals = [], []
            y, mo = map(int, lv['start'].split('-'))
            for v in lv['bill3m']:
                months.append(f'{y}-{mo:02d}'); vals.append(v)
                y, mo = y + (mo == 12), mo % 12 + 1
        else:
            months, vals = m['monthly']['months'], m['monthly']['data']['ff']
        by = {k: v for k, v in zip(months, vals) if fin(v)}
    except (OSError, ValueError, KeyError):
        by = {}
    first = by[min(by)] if by else 3.0
    prev = first
    for i, d in enumerate(dates):
        k = str(d.astype('datetime64[M]'))
        v = by.get(k, prev if k > (min(by) if by else '') else first)
        prev = v
        rf[i] = (1 + v / 100) ** (1 / 52) - 1
    return rf


def sec_panel(public, D):
    """Month-end market value ($M, rank/m-cap) and the SEC quarterly net income and equity (rank/q-ni, q-eq) on the weekly
    grid, each used only once it was known: a month's market value from the next week on, a quarter's figures 13 weeks
    after the quarter ends."""
    rk = Path(public) / 'rank'
    try:
        meta = json.loads((rk / 'meta.json').read_text())
    except (OSError, ValueError):
        return None
    cos = [c[0] for c in meta['cos']]
    m0 = np.datetime64(meta['months']['start'])
    qlab = meta['quarters']
    N, T = len(D['tickers']), len(D['dates'])
    wk_month = D['dates'].astype('datetime64[M]')

    def rows(name):
        try:
            return json.loads((rk / f'{name}.json').read_text())['rows']
        except (OSError, ValueError):
            return None
    out = {}
    cap = rows('m-cap')
    if cap:
        A = np.full((N, T), np.nan)
        mi = ((wk_month - m0).astype(int) - 1)               # the last month-end before this week's month
        for t, r in zip(cos, cap):
            i = D['ix'].get(t)
            if i is None or not r:
                continue
            i0, vals = int(r[0]), np.array([v if fin(v) else np.nan for v in r[1:]], dtype=float)
            j = mi - i0
            ok = (j >= 0) & (j < len(vals))
            A[i, ok] = vals[j[ok]]
        out['cap'] = A
    qend = [(np.datetime64(f"{q[:4]}-{int(q[-1]) * 3:02d}") + np.timedelta64(1, 'M')).astype('datetime64[D]') - DAY for q in qlab]   # the quarter's last day
    known = np.array([e + REB_LAG_WEEKS * WEEK for e in qend])
    kq = np.searchsorted(known, D['dates'], side='right') - 1   # the latest quarter known each week (-1: none)
    for name in ('q-ni', 'q-eq'):
        rr = rows(name)
        if not rr:
            continue
        Q = np.full((N, len(qlab)), np.nan)
        for t, r in zip(cos, rr):
            i = D['ix'].get(t)
            if i is None or not r:
                continue
            i0 = int(r[0])
            vals = [v if fin(v) else np.nan for v in r[1:]]
            Q[i, i0:i0 + len(vals)] = vals[:len(qlab) - i0]
        out[name] = Q
    out['kq'] = kq
    return out


def f13_panel(path, D):
    """13F breadth: each quarter's new holders minus exits over the holders, per stock, from the day the quarter's 13F
    filings were due (45 days after it ended)."""
    try:
        q = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    F = q.get('fields') or []
    if not {'new', 'exits', 'holders'} <= set(F):
        return None
    iN, iX, iH = F.index('new'), F.index('exits'), F.index('holders')
    cov = q.get('coverage') or []
    full = max(cov) if cov else 0
    periods = [np.datetime64(p) for p in q['periods']]
    N = len(D['tickers'])
    B = np.full((N, len(periods)), np.nan)
    for t, rows in (q.get('rows') or {}).items():
        i = D['ix'].get(t)
        if i is None:
            continue
        for k, r in enumerate(rows):
            if r and k < len(periods) and cov[k] >= 0.8 * full and r[iH]:
                B[i, k] = (r[iN] - r[iX]) / r[iH]
    known = np.array([p + F13_LAG_DAYS * DAY for p in periods])
    return {'B': B, 'kq': np.searchsorted(known, D['dates'], side='right') - 1, 'periods': [str(p) for p in periods],
            'first': str(known[next((k for k, c in enumerate(cov) if c >= 0.8 * full), 0)])}


# ------------------------------------------------------------------ the engine
def universe(D, t):
    """The stock universe at week t (see the module notes)."""
    if '_u' not in D:
        D['_u'] = {}
    if t not in D['_u']:
        C, PX, DV = D['C'], D['PX'], D['DV']
        ok = ~D['is_etf'] & np.isfinite(C[:, t]) & (np.isfinite(C[:, t - 52]) if t >= 52 else False)
        ok &= np.nan_to_num(PX[:, t]) >= MIN_PRICE
        ok &= np.nan_to_num(DV[:, t]) >= MIN_DV
        D['_u'][t] = ok
    return D['_u'][t]


def rebalance_weeks(D, every, start):
    T = D.get('t_end', len(D['dates']) - 1) + 1
    if every == 'W':
        return list(range(start, T))
    return [t for t in range(start, T) if D['month_end'][t]]


def simulate(D, Wt, start, end=None):
    """Wt: {t: weights (N,)} — the targets set on week t's close. Returns weekly net returns from week start + 1 on,
    with gross returns, turnover, costs and exposure, and the weights held after the last week (what the rule holds
    for the next one)."""
    R, cost, rf = D['R'], D['cost'], D['rf']
    N = R.shape[0]
    end = D.get('t_end', len(D['dates']) - 1) if end is None else end
    w = np.zeros(N)
    net, gross, turn, costs, expo, longs, shorts, t_out = [], [], [], [], [], [], [], []
    bw, fw = (1 + BORROW) ** (1 / 52) - 1, (1 + FIN_SPREAD) ** (1 / 52) - 1
    for t in range(start, end):
        c_t = 0.0
        to = 0.0
        if t in Wt:
            tgt = np.nan_to_num(Wt[t])
            dw = np.abs(tgt - w)
            to = float(dw.sum())
            c_t = float((dw * cost[:, t]).sum())
            w = tgt
        r = np.nan_to_num(R[:, t + 1])
        held = float((w * r).sum())
        cashw = 1.0 - float(w.sum())
        cash = cashw * rf[t + 1] + (cashw * fw if cashw < 0 else 0.0)
        sh = float(-w[w < 0].sum())
        g = held + cash
        gf = g - sh * bw                                      # the borrow fee is paid from cash
        p = (1 - c_t) * (1 + gf) - 1                          # costs come out of capital before the week (positions shrink with it)
        net.append(p); gross.append(g); turn.append(to); costs.append(c_t)
        expo.append(float(np.abs(w).sum())); longs.append(float(w[w > 0].sum())); shorts.append(sh); t_out.append(t + 1)
        if 1 + gf > 0.02:
            w = w * (1 + r) / (1 + gf)
        else:
            w = np.zeros(N)                                   # wiped out: the rule stops
    hold = w
    T = len(D['dates'])
    if end in Wt:                                             # the rule's targets for the next week, when it rebalances now
        hold = np.nan_to_num(Wt[end])
    return {'t': np.array(t_out, dtype=int), 'net': np.array(net), 'gross': np.array(gross), 'turn': np.array(turn),
            'cost': np.array(costs), 'expo': np.array(expo), 'long': np.array(longs), 'short': np.array(shorts), 'hold': hold,
            'end': end if end < T else T - 1}


# ------------------------------------------------------------------ the rules
def _w(D):
    return np.zeros(len(D['tickers']))


def _have(D, t, sym, weeks=52):
    i = D['ix'].get(sym)
    return i is not None and t >= weeks and np.isfinite(D['C'][i, t]) and np.isfinite(D['C'][i, t - weeks])


def _ret(D, i, t, L, skip=0):
    C = D['C']
    a, b = C[i, t - skip], C[i, t - L]
    return a / b - 1 if np.isfinite(a) and np.isfinite(b) and b > 0 else np.nan


def _vol(D, i, t, L):
    r = D['R'][i, max(1, t - L + 1):t + 1]
    r = r[np.isfinite(r)]
    return float(np.std(np.log1p(r)) * math.sqrt(52)) if len(r) >= max(4, L // 2) else np.nan


def first_week(D, syms, weeks=52):
    """The first week on or after START with every one of syms on file for `weeks` weeks."""
    for t in range(D['t0'], len(D['dates'])):
        if all(_have(D, t, s, weeks) for s in syms):
            return t
    return None


def r_hold(D, sym='SPY'):
    t0 = first_week(D, [sym], 1)
    w = _w(D); w[D['ix'][sym]] = 1.0
    return {t0: w}, t0


def r_mix(D, mix=(('SPY', 0.6), ('TLT', 0.4))):
    t0 = first_week(D, [s for s, _ in mix], 1)
    out = {}
    for t in rebalance_weeks(D, 'M', t0):
        w = _w(D)
        for s, x in mix:
            w[D['ix'][s]] = x
        out[t] = w
    return out, t0


def r_equal_universe(D):
    t0 = D['t0']
    out = {}
    for t in rebalance_weeks(D, 'M', t0):
        u = universe(D, t)
        if u.sum() >= 20:
            out[t] = u / u.sum()
    return out, t0


def r_trend(D, ma=40, sym='SPY'):
    """Faber (2007): hold the index when its month-end close is above its 10-month (≈ 40-week) average, else cash."""
    t0 = first_week(D, [sym], ma)
    i = D['ix'][sym]
    out = {}
    for t in rebalance_weeks(D, 'M', t0):
        w = _w(D)
        avg = np.nanmean(D['C'][i, t - ma + 1:t + 1])
        if D['C'][i, t] > avg:
            w[i] = 1.0
        out[t] = w
    return out, t0


def r_dual_momentum(D, L=52):
    """Antonacci (2014), global equities momentum: if the S&P 500 beat cash over 12 months, hold the stronger of US and
    international stocks, else bonds."""
    t0 = first_week(D, ['SPY', 'EFA', 'TLT'], L)
    out = {}
    for t in rebalance_weeks(D, 'M', t0):
        w = _w(D)
        rs, re_ = _ret(D, D['ix']['SPY'], t, L), _ret(D, D['ix']['EFA'], t, L)
        cash = float(np.prod(1 + D['rf'][t - L + 1:t + 1]) - 1)
        if rs > cash:
            w[D['ix']['SPY' if rs >= re_ else 'EFA']] = 1.0
        else:
            w[D['ix']['TLT']] = 1.0
        out[t] = w
    return out, t0


def r_tsmom(D, L=52, target=0.30, cap=3.0):
    """Moskowitz, Ooi and Pedersen (2012), time-series momentum: each asset long when its past year's return was
    positive, short when negative, sized to the same volatility (each to 30% a year, divided by the number of assets)."""
    t0 = first_week(D, ['SPY', 'TLT'], L)
    out = {}
    for t in rebalance_weeks(D, 'M', t0):
        w = _w(D)
        ok = [s for s in ETF_SET if s != 'QQQ' and _have(D, t, s, L)]
        for s in ok:
            i = D['ix'][s]
            r, v = _ret(D, i, t, L), _vol(D, i, t, 26)
            if fin(r) and fin(v) and v > 0:
                w[i] = np.sign(r) * min(target / v, 4.0) / len(ok)
        g = np.abs(w).sum()
        if g > cap:
            w *= cap / g
        out[t] = w
    return out, t0


def r_sector_momentum(D, L=26, top=3):
    """Moskowitz and Grinblatt (1999), industry momentum: the sector ETFs with the strongest past six months, equal weight."""
    t0 = first_week(D, SECTORS[:9], L)
    out = {}
    for t in rebalance_weeks(D, 'M', t0):
        ok = [(s, _ret(D, D['ix'][s], t, L)) for s in SECTORS if _have(D, t, s, L)]
        ok = [x for x in ok if fin(x[1])]
        w = _w(D)
        for s, _ in sorted(ok, key=lambda x: -x[1])[:top]:
            w[D['ix'][s]] = 1.0 / top
        out[t] = w
    return out, t0


def r_vol_target(D, target=0.15, L=13, cap=2.0, sym='SPY'):
    """Moreira and Muir (2017), volatility-managed portfolios: the index sized each month to a 15% target from its recent
    realized volatility, up to 2× (borrowed at cash + 0.5%)."""
    t0 = first_week(D, [sym], max(L, 4))
    i = D['ix'][sym]
    out = {}
    for t in rebalance_weeks(D, 'M', t0):
        w = _w(D)
        v = _vol(D, i, t, L)
        w[i] = min(cap, target / v) if fin(v) and v > 0 else 1.0
        out[t] = w
    return out, t0


def r_risk_parity(D, syms=('SPY', 'TLT', 'GLD'), L=26):
    """Inverse-volatility weights (Qian 2005; Asness, Frazzini and Pedersen 2012 without the leverage): stocks, Treasuries
    and gold, each weighted by one over its six-month volatility, monthly."""
    t0 = first_week(D, list(syms), L)
    out = {}
    for t in rebalance_weeks(D, 'M', t0):
        inv = {s: 1 / _vol(D, D['ix'][s], t, L) for s in syms}
        tot = sum(v for v in inv.values() if fin(v))
        w = _w(D)
        for s, v in inv.items():
            if fin(v):
                w[D['ix'][s]] = v / tot
        out[t] = w
    return out, t0


def r_halloween(D, sym='SPY'):
    """Bouman and Jacobsen (2002), "Sell in May": the index from November to April, cash from May to October."""
    t0 = first_week(D, [sym], 1)
    i = D['ix'][sym]
    out, prev = {}, None
    for t in range(t0, len(D['dates'])):
        nxt = int(str(D['dates'][t] + WEEK)[5:7])
        on = nxt in (11, 12, 1, 2, 3, 4)
        if on != prev:
            w = _w(D)
            w[i] = 1.0 if on else 0.0
            out[t] = w
            prev = on
    return out, t0


def r_january(D):
    """Keim (1983) / Reinganum (1983), the January effect: small caps (IWM) over large (SPY) in January, flat otherwise."""
    t0 = first_week(D, ['IWM', 'SPY'], 1)
    out, prev = {}, None
    for t in range(t0, len(D['dates'])):
        on = str(D['dates'][t] + WEEK)[5:7] == '01'
        if on != prev:
            w = _w(D)
            if on:
                w[D['ix']['IWM']], w[D['ix']['SPY']] = 1.0, -1.0
            out[t] = w
            prev = on
    return out, t0


def r_pullback(D, L=20, k=2.0, hold=4, sym='SPY'):
    """Bollinger bands as a dip-buying rule (Bollinger 2001): buy the index after a weekly close below its 20-week average
    less two standard deviations, hold four weeks, else cash."""
    t0 = first_week(D, [sym], L)
    i = D['ix'][sym]
    C = D['C'][i]
    out, left, prev = {}, 0, None
    for t in range(t0, len(D['dates'])):
        win = C[t - L + 1:t + 1]
        if np.isfinite(C[t]) and C[t] < np.nanmean(win) - k * np.nanstd(win):
            left = hold
        on = left > 0
        left = max(0, left - 1)
        if on != prev:
            w = _w(D)
            w[i] = 1.0 if on else 0.0
            out[t] = w
            prev = on
    return out, t0


def _xs(D, score, top=0.1, side='long', every='M', bottom=False, start=None, min_names=50, pool=None):
    """Cross-sectional rule: on each rebalance week, rank the universe by score(D, t, idx) and hold the top fraction
    (bottom=True: the lowest scores) equally weighted; side 'ls' also shorts the other end."""
    out = {}
    start = D['t0'] if start is None else start
    for t in rebalance_weeks(D, every, start):
        u = universe(D, t)
        idx = np.where(u)[0]
        if pool:
            idx = idx[np.argsort(-np.nan_to_num(D['DV'][idx, t]))[:pool]]
        if len(idx) < min_names:
            continue
        s = score(D, t, idx)
        ok = np.isfinite(s)
        idx, s = idx[ok], s[ok]
        if len(idx) < min_names:
            continue
        o = np.argsort(s)
        if not bottom:
            o = o[::-1]
        k = max(1, int(round(top * len(idx))))
        w = _w(D)
        w[idx[o[:k]]] = 1.0 / k
        if side == 'ls':
            w[idx[o[-k:]]] = -1.0 / k
        out[t] = w
    return out, start


def s_mom(L=52, skip=4):
    def f(D, t, idx):
        C = D['C']
        with np.errstate(invalid='ignore', divide='ignore'):
            return C[idx, t - skip] / C[idx, t - L] - 1
    return f


def s_high(D, t, idx):
    C = D['C'][idx, t - 51:t + 1]
    with np.errstate(invalid='ignore', divide='ignore'):
        return D['C'][idx, t] / np.nanmax(C, axis=1)


def s_vol(L=52):
    def f(D, t, idx):
        r = np.log1p(D['R'][idx, t - L + 1:t + 1])
        n = np.isfinite(r).sum(1)
        with np.errstate(invalid='ignore'):
            v = np.nanstd(r, axis=1)
        return np.where(n >= int(L * 0.75), v, np.nan)
    return f


def s_last_week(D, t, idx):
    return D['R'][idx, t]


def _ttm(Q, kq):
    """Trailing four quarters known at each week: Q (N, quarters), kq the latest known quarter index per week."""
    out = {}
    for k in sorted(set(int(x) for x in kq if x >= 3)):
        blk = Q[:, k - 3:k + 1]
        v = blk.sum(1)
        v[~np.isfinite(blk).all(1)] = np.nan
        out[k] = v
    return out


def s_earnings_yield(D, t, idx):
    S = D.get('sec') or {}
    if 'q-ni' not in S or 'cap' not in S:
        return np.full(len(idx), np.nan)
    k = int(S['kq'][t])
    if k < 3:
        return np.full(len(idx), np.nan)
    if '_ttm_ni' not in S:
        S['_ttm_ni'] = _ttm(S['q-ni'], S['kq'])
    ni = S['_ttm_ni'][k][idx]
    cap = S['cap'][idx, t]
    with np.errstate(invalid='ignore', divide='ignore'):
        ey = ni / cap
    return np.where((ni > 0) & (cap > 0), ey, np.nan)


def s_roe(D, t, idx):
    S = D.get('sec') or {}
    if 'q-ni' not in S or 'q-eq' not in S:
        return np.full(len(idx), np.nan)
    k = int(S['kq'][t])
    if k < 3:
        return np.full(len(idx), np.nan)
    if '_ttm_ni' not in S:
        S['_ttm_ni'] = _ttm(S['q-ni'], S['kq'])
    ni, eq = S['_ttm_ni'][k][idx], S['q-eq'][idx, k]
    with np.errstate(invalid='ignore', divide='ignore'):
        r = ni / eq
    return np.where(eq > 0, r, np.nan)


def s_breadth(D, t, idx):
    F = D.get('f13')
    if not F:
        return np.full(len(idx), np.nan)
    k = int(F['kq'][t])
    return F['B'][idx, k] if k >= 0 else np.full(len(idx), np.nan)


def r_pairs(D, form=52, trade=26, n_pairs=20, pool=400, k=2.0):
    """Gatev, Goetzmann and Rouwenhorst (2006), pairs trading by the distance method: every six months, the 20 pairs of
    stocks in the same sector whose normalized prices moved closest over the past year (among the 400 most traded); a
    pair is opened when the gap between them exceeds two of its standard deviations (long the laggard, short the leader,
    each leg 1/20 of capital) and closed when the gap closes or the six months end."""
    C = D['C']
    out = {}
    T = len(D['dates'])
    t = max(D['t0'], form)
    while t < T:
        u = universe(D, t)
        idx = np.where(u & np.isfinite(C[:, t - form:t + 1]).all(1))[0]
        idx = idx[np.argsort(-np.nan_to_num(D['DV'][idx, t]))[:pool]]
        pairs = []
        secs = np.array(D['sectors'])[idx]
        X = C[idx, t - form:t + 1] / C[idx, t - form:t - form + 1]
        for sec in set(secs):
            m = np.where(secs == sec)[0]
            if len(m) < 2:
                continue
            Y = X[m]
            d = ((Y[:, None, :] - Y[None, :, :]) ** 2).sum(-1)
            a, b = np.triu_indices(len(m), 1)
            for j in np.argsort(d[a, b])[:n_pairs]:
                pairs.append((float(d[a[j], b[j]]), idx[m[a[j]]], idx[m[b[j]]]))
        pairs = sorted(pairs)[:n_pairs]
        info = []
        for _, i, j in pairs:
            s = np.log(C[i, t - form:t + 1] / C[i, t - form]) - np.log(C[j, t - form:t + 1] / C[j, t - form])
            info.append((i, j, float(np.std(s)), C[i, t], C[j, t]))
        state = [0] * len(info)
        end = min(T, t + trade)
        for u_ in range(t, end):
            changed = False
            for q, (i, j, sd, ci0, cj0) in enumerate(info):
                if not (np.isfinite(C[i, u_]) and np.isfinite(C[j, u_])) or sd <= 0:
                    continue
                gap = (math.log(C[i, u_] / ci0) - math.log(C[j, u_] / cj0)) / sd
                if state[q] == 0 and abs(gap) > k and u_ < end - 1:
                    state[q] = -1 if gap > 0 else 1        # +1: long i, short j
                    changed = True
                elif state[q] != 0 and (gap * -state[q] <= 0 or u_ == end - 1):
                    state[q] = 0
                    changed = True
            if changed or (u_ == end - 1):
                w = _w(D)
                for q, (i, j, *_r) in enumerate(info):
                    if state[q]:
                        w[i] += state[q] / n_pairs
                        w[j] -= state[q] / n_pairs
                out[u_] = w
        t = end
    return out, max(D['t0'], form)


# the library: id → (name, group, paper, year, rules, the rule and its settings, the family's grid for overfitting)
LIB = [
    dict(id='spy', name='S&P 500 (SPY), bought and held', group='Benchmarks', paper='—', year=None, bench=True,
         rule=lambda D: r_hold(D, 'SPY'), rules='SPY held throughout, dividends reinvested.'),
    dict(id='ew', name='Equal-weighted universe (today\'s survivors)', group='Benchmarks', paper='—', year=None, bench=True,
         rule=r_equal_universe, rules='Every stock of the universe, equal weight, rebalanced monthly — the benchmark for the stock rules, '
         'with the same survivorship as them.'),
    dict(id='6040', name='60/40 stocks and Treasuries', group='Benchmarks', paper='—', year=None, bench=True,
         rule=r_mix, rules='60% SPY and 40% long Treasuries (TLT), rebalanced monthly.'),
    dict(id='trend', name='Trend: S&P 500 above its 10-month average', group='Trend & momentum', paper='Faber (2007)', year=2007,
         rule=r_trend, params={'ma': 40}, grid={'ma': [20, 30, 40, 52]},
         rules='At each month-end, hold SPY if it closed above its 40-week (≈ 10-month) average, else cash.'),
    dict(id='dualmom', name='Dual momentum (US, international, bonds)', group='Trend & momentum', paper='Antonacci (2014)', year=2014,
         rule=r_dual_momentum, params={'L': 52}, grid={'L': [26, 39, 52]},
         rules='Monthly: if SPY beat cash over 12 months, hold the stronger of SPY and EFA; otherwise long Treasuries (TLT).'),
    dict(id='tsmom', name='Time-series momentum across asset classes', group='Trend & momentum',
         paper='Moskowitz, Ooi and Pedersen (2012)', year=2012, rule=r_tsmom, params={'L': 52}, grid={'L': [13, 26, 52]},
         rules='Monthly: US large and small caps, developed and emerging markets, Treasuries, gold and oil (SPY, IWM, EFA, '
         'EEM, TLT, GLD, USO as each becomes available), long if its 12-month return is positive, short if negative, each '
         'sized to 30% volatility ÷ the number of assets, gross exposure up to 3×.'),
    dict(id='mom', name='Stock momentum, 12-1 (top decile)', group='Trend & momentum', paper='Jegadeesh and Titman (1993)', year=1993,
         rule=lambda D, L=52, skip=4, top=0.1: _xs(D, s_mom(L, skip), top), params={'L': 52, 'skip': 4, 'top': 0.1},
         grid={'L': [26, 39, 52], 'skip': [0, 4], 'top': [0.1, 0.2]},
         rules='Monthly: the tenth of the universe with the highest return from 12 months to 1 month ago, equal weight.'),
    dict(id='momls', name='Stock momentum, long winners and short losers', group='Trend & momentum',
         paper='Jegadeesh and Titman (1993)', year=1993,
         rule=lambda D, L=52, skip=4, top=0.1: _xs(D, s_mom(L, skip), top, 'ls'), params={'L': 52, 'skip': 4, 'top': 0.1},
         rules='Monthly: long the top tenth by 12-1 month return, short the bottom tenth, equal weight (dollar neutral).'),
    dict(id='high52', name='Near the 52-week high (top decile)', group='Trend & momentum', paper='George and Hwang (2004)', year=2004,
         rule=lambda D, top=0.1: _xs(D, s_high, top), params={'top': 0.1}, grid={'top': [0.1, 0.2, 0.3]},
         rules='Monthly: the tenth of the universe closest to its 52-week high, equal weight.'),
    dict(id='sectormom', name='Sector rotation: strongest sectors', group='Rotation', paper='Moskowitz and Grinblatt (1999)', year=1999,
         rule=r_sector_momentum, params={'L': 26, 'top': 3}, grid={'L': [13, 26, 52], 'top': [2, 3, 4]},
         rules='Monthly: the three SPDR sector ETFs with the highest six-month return, equal weight.'),
    dict(id='lowvol', name='Low volatility (lowest fifth)', group='Factors', paper='Ang, Hodrick, Xing and Zhang (2006); Baker, Bradley and Wurgler (2011)', year=2006,
         rule=lambda D, L=52, top=0.2: _xs(D, s_vol(L), top, bottom=True), params={'L': 52, 'top': 0.2},
         grid={'L': [26, 52], 'top': [0.1, 0.2, 0.3]},
         rules='Monthly: the fifth of the universe with the lowest volatility of weekly returns over the past year, equal weight.'),
    dict(id='value', name='Earnings yield (cheapest fifth, SEC figures)', group='Factors', paper='Basu (1977)', year=1977, site=True,
         rule=lambda D, top=0.2: _xs(D, s_earnings_yield, top), params={'top': 0.2},
         rules='Monthly: the fifth of the universe with the highest trailing-12-month net income ÷ market value (both from the '
         'site\'s SEC data: quarters used 13 weeks after they end, the last month-end market value), profitable names only. From 2010.'),
    dict(id='quality', name='Profitability: highest return on equity (SEC figures)', group='Factors', paper='Novy-Marx (2013); Fama and French (2015)', year=2013, site=True,
         rule=lambda D, top=0.2: _xs(D, s_roe, top), params={'top': 0.2},
         rules='Monthly: the fifth of the universe with the highest trailing-12-month net income ÷ equity (SEC figures, 13 weeks '
         'after the quarter), positive equity only. From 2010.'),
    dict(id='breadth', name='13F breadth: most new holders (site 13F data)', group='Factors', paper='Chen, Hong and Stein (2002)', year=2002, site=True,
         rule=lambda D, top=0.1: _xs(D, s_breadth, top), params={'top': 0.1},
         rules='Monthly: the tenth of the universe whose count of 13F holders grew most in the latest quarter (new holders less '
         'exits ÷ holders), used from the 45-day filing deadline. The site\'s 13F history is short: under two years.'),
    dict(id='reversal', name='Short-term reversal (weekly, long losers, short winners)', group='Mean reversion & seasonality',
         paper='Lehmann (1990); Jegadeesh (1990)', year=1990,
         rule=lambda D, top=0.1: _xs(D, s_last_week, top, 'ls', every='W', bottom=True, pool=500), params={'top': 0.1},
         rules='Weekly, among the 500 most traded stocks: long the tenth that fell most last week, short the tenth that rose '
         'most — a rule that trades all of its capital every week, so its costs show.'),
    dict(id='pullback', name='Buy the dip: S&P 500 below its lower Bollinger band', group='Mean reversion & seasonality',
         paper='Bollinger (2001)', year=2001, rule=r_pullback, params={'L': 20, 'k': 2.0, 'hold': 4},
         grid={'k': [1.5, 2.0, 2.5], 'hold': [2, 4, 8]},
         rules='Hold SPY for four weeks after a weekly close below its 20-week average less two standard deviations, else cash.'),
    dict(id='halloween', name='Sell in May: S&P 500 from November to April', group='Mean reversion & seasonality',
         paper='Bouman and Jacobsen (2002)', year=2002, rule=r_halloween,
         rules='SPY from the start of November to the end of April, cash from May to October.'),
    dict(id='january', name='January effect: small caps over large caps', group='Mean reversion & seasonality',
         paper='Keim (1983)', year=1983, rule=r_january,
         rules='In January only, long small caps (IWM) and short large caps (SPY), equal dollars; flat the rest of the year.'),
    dict(id='voltarget', name='Volatility-targeted S&P 500 (15%)', group='Portfolio & leverage', paper='Moreira and Muir (2017)', year=2017,
         rule=r_vol_target, params={'target': 0.15, 'L': 13}, grid={'target': [0.10, 0.15, 0.20], 'L': [4, 13, 26]},
         rules='Monthly: SPY sized to 15% ÷ its volatility over the last 13 weeks, up to 2× (borrowing at cash + 0.5%).'),
    dict(id='riskparity', name='Risk parity: stocks, Treasuries, gold', group='Portfolio & leverage',
         paper='Qian (2005); Asness, Frazzini and Pedersen (2012)', year=2005, rule=r_risk_parity, params={'L': 26}, grid={'L': [13, 26, 52]},
         rules='Monthly: SPY, TLT and GLD weighted by one over their six-month volatility (no leverage).'),
    dict(id='pairs', name='Pairs trading (distance method)', group='Pairs', paper='Gatev, Goetzmann and Rouwenhorst (2006)', year=2006,
         rule=r_pairs, params={'k': 2.0}, grid={'k': [1.5, 2.0, 2.5]},
         rules='Every six months, the 20 same-sector pairs among the 400 most traded stocks whose normalized prices tracked most '
         'closely over the past year; a pair opens when its gap exceeds two standard deviations (long the laggard, short the '
         'leader, 1/20 of capital a leg) and closes when the gap closes or at six months.'),
]
ENSEMBLE = dict(id='ensemble', name='Ensemble: every rule, risk-weighted', group='Ensemble', paper='—', year=None,
                rules='Each month, every non-benchmark rule with a year of returns, weighted by one over its volatility over the '
                'past year (no rule is chosen by its past return); costs are those of the rules.')


# ------------------------------------------------------------------ statistics
def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_ppf(p):
    lo, hi = -10.0, 10.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if _norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def moments(x):
    x = np.asarray(x, dtype=float)
    m, s = x.mean(), x.std()
    if s == 0:
        return 0.0, 3.0
    z = (x - m) / s
    return float((z ** 3).mean()), float((z ** 4).mean())


def psr(sr, n, skew, kurt, sr0=0.0):
    """Probabilistic Sharpe ratio (weekly, not annualized): P(true SR > sr0)."""
    if n < 3:
        return None
    den = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    if den <= 0:
        return None
    return _norm_cdf((sr - sr0) * math.sqrt(n - 1) / math.sqrt(den))


def sr0_for_trials(srs):
    """The Sharpe ratio expected from the best of len(srs) trials with no skill (Bailey and López de Prado 2014)."""
    n = len(srs)
    if n < 2:
        return 0.0
    v = float(np.var(srs, ddof=1))
    g = 0.5772156649
    return math.sqrt(v) * ((1 - g) * _norm_ppf(1 - 1 / n) + g * _norm_ppf(1 - 1 / (n * math.e)))


def metrics(net, rf, spy=None, dates=None):
    """Annualized results of weekly net returns (rf: the matching weekly cash returns; spy: SPY's weekly returns)."""
    net = np.asarray(net, dtype=float)
    n = len(net)
    if n < 26:
        return None
    ex = net - rf
    eq = np.cumprod(1 + net)
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1
    cagr = eq[-1] ** (52 / n) - 1
    vol = float(net.std() * math.sqrt(52))
    sd_ex = ex.std()
    sr_w = float(ex.mean() / sd_ex) if sd_ex > 0 else 0.0
    dn = np.sqrt(np.mean(np.minimum(ex, 0) ** 2))
    sk, ku = moments(ex)
    out = {'weeks': n, 'cagr': float(cagr), 'vol': vol, 'sharpe': sr_w * math.sqrt(52), 'sortino': float(ex.mean() / dn * math.sqrt(52)) if dn > 0 else None,
           'maxdd': float(dd.min()), 'calmar': float(cagr / -dd.min()) if dd.min() < 0 else None, 'hit': float((net > 0).mean()),
           'worst_week': float(net.min()), 'best_week': float(net.max()), 'skew': sk, 'kurt': ku, 'sr_w': sr_w,
           'psr': psr(sr_w, n, sk, ku), 'total': float(eq[-1] - 1)}
    if dates is not None:
        out['from'], out['to'] = str(dates[0] - WEEK), str(dates[-1])
        k = int(np.argmin(dd))
        out['maxdd_at'] = str(dates[k])
    if spy is not None:
        sx = np.asarray(spy, dtype=float) - rf
        ok = np.isfinite(sx)
        if ok.sum() > 26 and sx[ok].var() > 0:
            b = float(np.cov(ex[ok], sx[ok])[0, 1] / sx[ok].var())
            out['beta'] = b
            out['alpha'] = float((ex[ok].mean() - b * sx[ok].mean()) * 52)
            out['corr'] = float(np.corrcoef(ex[ok], sx[ok])[0, 1])
    return out


def yearly(net, dates):
    out = {}
    for y in sorted({str(d)[:4] for d in dates}):
        m = np.array([str(d)[:4] == y for d in dates])
        out[y] = float(np.prod(1 + net[m]) - 1)
    return out


def pbo(M, S=10):
    """Probability of backtest overfitting by combinatorially symmetric cross-validation: M (weeks × settings) of
    weekly excess returns over a common window."""
    T, n = M.shape
    if n < 2 or T < S * 8:
        return None
    blocks = np.array_split(np.arange(T), S)
    lam = []
    for ins in itertools.combinations(range(S), S // 2):
        i_idx = np.concatenate([blocks[k] for k in ins])
        o_idx = np.concatenate([blocks[k] for k in range(S) if k not in ins])

        def sr(ix):
            x = M[ix]
            sd = x.std(0)
            return np.where(sd > 0, x.mean(0) / np.where(sd > 0, sd, 1), 0)
        best = int(np.argmax(sr(i_idx)))
        oos = sr(o_idx)
        rank = (oos < oos[best]).sum() + 0.5 * ((oos == oos[best]).sum() - 1) + 1     # 1 = worst … n = best
        om = rank / (n + 1)
        lam.append(math.log(om / (1 - om)))
    lam = np.array(lam)
    return {'pbo': float((lam <= 0).mean()), 'splits': len(lam), 'settings': n, 'median_logit': float(np.median(lam))}


# ------------------------------------------------------------------ running the library
def run_one(D, spec, params=None):
    p = dict(spec.get('params') or {})
    p.update(params or {})
    Wt, t0 = spec['rule'](D, **p)
    if t0 is None or not Wt:
        return None
    t0 = max(t0, min(Wt))
    return simulate(D, Wt, t0)


def _variants(spec):
    g = spec.get('grid')
    if not g:
        return []
    keys = list(g)
    return [dict(zip(keys, vals)) for vals in itertools.product(*(g[k] for k in keys))]


def ensemble(D, sims, ids, L=52):
    """Inverse-volatility mix of the rules' weekly net returns, weights set each month-end from the past year only."""
    T = len(D['dates'])
    ret = np.full((len(ids), T), np.nan)
    for k, i in enumerate(ids):
        s = sims[i]
        ret[k, s['t']] = s['net']
    out_t, out_r, w = [], [], None
    for t in range(1, T):
        if w is not None:
            r = ret[:, t]
            ok = np.isfinite(r) & (w > 0)
            if ok.any():
                out_t.append(t)
                out_r.append(float((w[ok] * r[ok]).sum() / w[ok].sum()))
        if D['month_end'][t]:
            past = ret[:, max(0, t - L + 1):t + 1]
            n = np.isfinite(past).sum(1)
            with np.errstate(invalid='ignore'):
                v = np.nanstd(past, axis=1)
            ww = np.where((n >= L * 0.9) & (v > 0), 1 / np.where(v > 0, v, 1), 0)
            if (ww > 0).sum() >= 3:
                w = ww
    return {'t': np.array(out_t, dtype=int), 'net': np.array(out_r)}


def run_all(D, verbose=False):
    sims, grids, srs = {}, {}, []
    spy = run_one(D, LIB[0])
    spy_r = np.full(len(D['dates']), np.nan)
    spy_r[spy['t']] = spy['net']
    for spec in LIB:
        s = run_one(D, spec)
        if s is None:
            if verbose:
                print('  ', spec['id'], 'no history', flush=True)
            continue
        sims[spec['id']] = s
        if not spec.get('bench'):
            m = metrics(s['net'], D['rf'][s['t']])
            if m:
                srs.append(m['sr_w'])
        var = _variants(spec)
        if var:
            res = []
            for p in var:
                v = run_one(D, spec, p)
                if v is not None and len(v['net']) > 52:
                    res.append((p, v))
                    m = metrics(v['net'], D['rf'][v['t']])
                    if m and p != {k: spec['params'][k] for k in p}:
                        srs.append(m['sr_w'])
            grids[spec['id']] = res
        if verbose:
            print('  ', spec['id'], len(s['net']), 'weeks', flush=True)
    ids = [s['id'] for s in LIB if not s.get('bench') and s['id'] in sims]
    ens = ensemble(D, sims, ids)
    if len(ens['net']) > 52:
        sims['ensemble'] = ens
    return sims, grids, srs, spy_r


def family_pbo(D, res):
    if len(res) < 2:
        return None
    t0 = max(v['t'][0] for _, v in res)
    t1 = min(v['t'][-1] for _, v in res)
    if t1 - t0 < 120:
        return None
    M = np.array([v['net'][(v['t'] >= t0) & (v['t'] <= t1)] - D['rf'][t0:t1 + 1] for _, v in res]).T
    out = pbo(M)
    if out:
        out['from'], out['to'] = str(D['dates'][t0]), str(D['dates'][t1])
        out['variants'] = [{'params': p, 'sharpe': round(float((M[:, k].mean() / M[:, k].std()) * math.sqrt(52)), 3) if M[:, k].std() > 0 else None}
                           for k, (p, _) in enumerate(res)]
    return out


def _r(v, d=4):
    if v is None:
        return None
    if isinstance(v, float):
        return round(v, d) if math.isfinite(v) else None
    return v


def _rd(m, d=4):
    return {k: _r(v, d) for k, v in m.items()} if m else None


def summarize(D, sims, grids, srs, spy_r, live=None):
    dates = D['dates']
    sr0 = sr0_for_trials(srs) if len(srs) >= 2 else 0.0
    rows, curves = [], {}
    specs = {s['id']: s for s in LIB}
    specs['ensemble'] = ENSEMBLE
    for sid, s in sims.items():
        spec = specs[sid]
        t, net = s['t'], s['net']
        rf = D['rf'][t]
        dt_ = dates[t]
        full = metrics(net, rf, spy_r[t], dt_)
        if not full:
            continue
        row = {'id': sid, 'name': spec['name'], 'group': spec['group'], 'paper': spec['paper'], 'year': spec.get('year'),
               'rules': spec['rules'], 'bench': bool(spec.get('bench')), 'site': bool(spec.get('site')), 'params': spec.get('params'),
               'full': _rd(full), 'yearly': {k: _r(v) for k, v in yearly(net, dt_).items()}}
        ss = np.isfinite(spy_r[t])
        if ss.sum() > 26:
            row['spy_same'] = _rd(metrics(spy_r[t][ss], rf[ss], None, dt_[ss]))
        if spec.get('year'):
            cut = np.datetime64(f"{spec['year'] + 1}-01-01")
            pre, post = dt_ < cut, dt_ >= cut
            row['pre'] = _rd(metrics(net[pre], rf[pre], spy_r[t][pre], dt_[pre])) if pre.sum() >= 52 else None
            row['post'] = _rd(metrics(net[post], rf[post], spy_r[t][post], dt_[post])) if post.sum() >= 52 else None
        l5 = dt_ >= dates[-1] - 52 * 5 * WEEK
        row['last5'] = _rd(metrics(net[l5], rf[l5], spy_r[t][l5], dt_[l5])) if l5.sum() >= 52 else None
        if not spec.get('bench'):
            row['dsr'] = _r(psr(full['sr_w'], full['weeks'], full['skew'], full['kurt'], sr0))
        if 'turn' in s:
            yrs = len(net) / 52
            row['turnover'] = _r(float(s['turn'].sum() / yrs), 2)
            row['cost_drag'] = _r(float(s['cost'].sum() / yrs))
            row['exposure'] = _r(float(s['expo'].mean()), 3)
            row['gross_cagr'] = _r(float(np.prod(1 + s['gross']) ** (52 / len(net)) - 1))
            h = s['hold']
            nz = np.where(np.abs(h) > 1e-6)[0]
            o = nz[np.argsort(-np.abs(h[nz]))]
            row['holdings'] = [[D['tickers'][i], _r(float(h[i]), 4)] for i in o[:25]]
            row['n_holdings'] = int(len(nz))
            row['cash'] = _r(float(1 - h.sum()), 4)
        if sid in grids and grids[sid]:
            row['pbo'] = family_pbo(D, grids[sid])
        if live and sid in live:
            row['live'] = live[sid]
        rows.append(row)
        eq = np.cumprod(1 + net)
        curves[sid] = {'i0': int(t[0] - 1), 'eq': [float(f'{x:.5g}') for x in np.concatenate([[1.0], eq])]}
    return rows, curves, sr0


# ------------------------------------------------------------------ the live ledger
def holdings_now(D, sims):
    """What each rule holds for the week after the last closed week: {id: {ticker: weight}}."""
    out = {}
    for sid, s in sims.items():
        if 'hold' not in s:
            continue
        h = s['hold']
        nz = np.where(np.abs(h) > 1e-6)[0]
        out[sid] = {D['tickers'][i]: round(float(h[i]), 6) for i in nz}
    return out


def ledger_update(path, D, sims, sha=None, made_at=None):
    """Freeze this week's positions once the week has closed; score every frozen week whose next close is known."""
    path = Path(path)
    try:
        L = json.loads(path.read_text())
    except (OSError, ValueError):
        L = {'v': 1, 'note': 'Each closed week\'s positions of every rule, frozen once and never edited (app/strategies.py).', 'rules': {}}
    comp = np.where(D['complete'])[0]
    if not len(comp):
        return L, {}
    t_now = int(comp.max())
    wk = str(D['dates'][t_now])
    made = made_at or dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    hold = holdings_now(D, sims)
    for sid, h in hold.items():
        r = L['rules'].setdefault(sid, {'since': wk, 'weeks': []})
        if not r['weeks'] or r['weeks'][-1]['week'] < wk:
            r['weeks'].append({'week': wk, 'w': h, 'made_at': made, **({'sha': sha} if sha else {})})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(L, separators=(',', ':')))
    return L, live_scores(D, L)


def live_scores(D, L):
    """Each rule's results since its first frozen week, from the frozen weights only."""
    out = {}
    pos = {str(d): i for i, d in enumerate(D['dates'])}
    for sid, r in L.get('rules', {}).items():
        Wt = {}
        for e in r['weeks']:
            t = pos.get(e['week'])
            if t is None:
                continue
            try:                                          # frozen after the next week had begun (Monday 12:00 UTC): its
                late = dt.datetime.fromisoformat(e['made_at']) > dt.datetime.fromisoformat(e['week'] + 'T12:00:00+00:00') + dt.timedelta(days=3)
            except (KeyError, ValueError):                # positions count from the week after, so no week is scored
                late = False                              # with positions set once it was under way
            t += 1 if late else 0
            w = np.zeros(len(D['tickers']))
            for tk, x in e['w'].items():
                i = D['ix'].get(tk)
                if i is not None:
                    w[i] = x
            Wt[t] = w
        if not Wt:
            continue
        t0 = min(Wt)
        last_known = int(np.where(D['complete'] & np.isfinite(D['C'][D['ix']['SPY']]))[0].max()) if 'SPY' in D['ix'] else t0
        if last_known <= t0:
            out[sid] = {'since': r['since'], 'weeks': 0}
            continue
        s = simulate(D, Wt, t0, last_known)
        eq = np.cumprod(1 + s['net'])
        out[sid] = {'since': r['since'], 'weeks': int(len(s['net'])), 'ret': _r(float(eq[-1] - 1)),
                    'curve': [[str(D['dates'][t]), _r(float(x), 5)] for t, x in zip(s['t'], eq)][-260:]}
    return out


# ------------------------------------------------------------------ publish
def publish(out_dir, D, rows, curves, sr0, n_trials, live_from=None):
    out_dir = Path(out_dir)
    comp = np.where(D['complete'])[0]
    doc = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
           'asof': str(D['dates'][int(comp.max())]) if len(comp) else None, 'start': str(START),
           'trials': n_trials, 'sr0_weekly': _r(sr0), 'sr0_annual': _r(sr0 * math.sqrt(52)),
           'assumptions': {'cost': '5 bp ≥ $500M weekly dollar volume, 15 bp ≥ $50M, 40 bp ≥ $5M, else 100 bp, one way',
                           'cash': 'Fed funds rate', 'borrow': BORROW, 'financing_spread': FIN_SPREAD,
                           'universe': f'stocks ≥ ${MIN_PRICE:.0f} as traded and ≥ ${MIN_DV / 1e6:.0f}M a week, a year of closes',
                           'sec_lag_weeks': REB_LAG_WEEKS, 'f13_lag_days': F13_LAG_DAYS},
           'survivorship': "Today's companies only: delisted, merged and bankrupt stocks are missing, which flatters long stock rules.",
           'rows': rows}
    (out_dir / 'strategies.json').write_text(json.dumps(doc, separators=(',', ':')))
    dates = D['dates']
    (out_dir / 'strategies-curves.json').write_text(json.dumps({'start': str(dates[0]), 'curves': curves}, separators=(',', ':')))
    return {'rules': len(rows), 'trials': n_trials, 'asof': doc['asof']}


def main():
    ap = argparse.ArgumentParser(description='Strategies: published rules backtested with costs, overfitting tests, live ledger')
    ap.add_argument('--public', default='hist/public')
    ap.add_argument('--ledger', default=None)
    ap.add_argument('--quarters', default=None, help='docs/data/market/by-ticker-quarters.json (the 13F breadth rule)')
    ap.add_argument('--sha', default=None)
    ap.add_argument('--limit', type=int, default=None)
    a = ap.parse_args()
    warnings.filterwarnings('ignore', category=RuntimeWarning)
    D = load(a.public, a.quarters, a.limit)
    print(len(D['tickers']), 'names,', len(D['dates']), 'weeks', flush=True)
    sims, grids, srs, spy_r = run_all(D, verbose=True)
    live = None
    if a.ledger:
        _, live = ledger_update(a.ledger, D, sims, a.sha)
    rows, curves, sr0 = summarize(D, sims, grids, srs, spy_r, live)
    print(json.dumps(publish(a.public, D, rows, curves, sr0, len(srs))))


if __name__ == '__main__':
    main()
