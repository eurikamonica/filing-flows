"""Opportunity (机遇): for every stock and ETF on the weekly grid, the probability that its price is higher in 1, 4 and
13 weeks, that buying now and selling then makes money after trading costs, and that selling short now and buying back
then makes money after costs and the borrow fee — with the return range, a score and the signals behind it.

One model per horizon h, pooled across every name, fitted walk-forward (each year predicted only from the years before
it) and frozen every week in a ledger that is scored once the outcomes are known.

  target      z = r ÷ (σ √h): the h-week log return r scaled by the name's own weekly volatility σ (the last 26 weeks,
              at least 1% a week), so a quiet utility and a biotech are on one scale
  model       z = b · x + e, ridge least squares on cross-sectionally standardized signals (each week's names ranked
              against each other: a z-score, clipped to ±3) and a few market-wide ones
  probability P(r > k) = P(e > k ÷ (σ √h) − b · x), e drawn from the model's own residuals (their empirical distribution,
              not a normal curve): k = 0 for the direction, + the round-trip cost for a buy, − (the cost + the borrow fee
              for h weeks) for a short
  cost        one way, by weekly dollar volume: 5 bp above $500M a week, 15 bp above $50M, 40 bp above $5M, else 100 bp;
              borrow 0.5% a year (general collateral; hard-to-borrow names pay far more — not known here)
  edge        P(profit) − the same probability with every timing signal at its average (the same name with its own
              volatility, cost and liquidity — liquidity is what a name is, not news about it), for buying and shorting
  score       0–100: where the better edge ranks among every name that week (each horizon ranked on its own, the best of the
              three kept); a name is flagged buy or short at a horizon when its edge is among the strongest fifth of the week
              and at least 2 points, the trade is more likely than not to make money after costs, and only at the horizons and sides whose flags worked out of sample: the flagged
              trades made money more often than not, on the median and on the average (the extreme 1% capped) after
              costs, and 2 points more often than those same names' no-signal odds said, at least 1 point more in each
              half of the years (the model card's "flagged")
  short       not flagged for names under $5 or trading under $5M a week: they are often hard to borrow, at fees far
              above the 0.5% assumed (the probability is still shown)
  drivers     each signal's contribution b_j × x_j to the prediction, largest first

Signals (point in time: only closes up to the week's own): momentum over 4, 13 and 26 weeks and 52 weeks less the last
4 (Jegadeesh-Titman, 12-1), last week's return (short-term reversal), the distance from the 52-week high (George-Hwang)
and low, the gap to the 40-week average (≈ 200 days), volatility (13 weeks) and its change (13 ÷ 52), the return against
its sector over 13 weeks, dollar volume (liquidity). No market timing: the market's own direction is left to the
regime models (market-wide signals are coded in MARKET_ALL but, fitted on 25 years, they mostly learn a few episodes).
Calibration: the residual-based probabilities are set right by Platt scaling fitted on the same training years.
Survivorship: today's companies only — names that were delisted are missing from the history the model learns from.
ETFs (--kind etfs, app/etf.py's weekly bars since 1993): the same model fitted on ETFs alone, total-return closes
(distributions reinvested), volatility floor 0.4% a week, peers = the ETF's category; cash-like funds (under 3% a year
of volatility) are left out — their direction is their yield; leveraged and inverse funds are never flagged short (their
borrow is usually costly).
Ledger (--ledger): each week's probabilities are frozen once the week has closed (from Sunday) and never edited; each
horizon is scored once its outcome is known (the Brier score, the calibration, how the flagged names did).

Honesty: weekly and monthly direction is close to a coin flip for single stocks; the walk-forward scores in the model
card (Brier skill against the base rate, AUC, the calibration table) say how far from one this gets. History and models,
not investment advice.
"""
import datetime as dt
import json
import math
import warnings
from pathlib import Path

import numpy as np

HORIZONS = {'1w': 1, '1m': 4, '3m': 13}
SIG_WEEKS, SIG_FLOOR = 26, 0.01
RIDGE = 10.0
BORROW = 0.005                 # a year
EDGE_MIN = 0.02               # a side needs this much edge (2 points) ...
TOP_SHARE = 0.2               # ... and to be among the strongest fifth of the week's edges at that horizon
HTB_DV, HTB_PRICE = 5e6, 5.0  # no short side below $5M a week traded or a $5 price: likely hard to borrow, fee unknown
FIRST_TEST_YEARS = 6           # years of history before the first predicted year
CROSS = ['mom4', 'mom13', 'mom26', 'mom52x4', 'rev1', 'hi52', 'lo52', 'ma40', 'vol13', 'volchg', 'rs_sector13', 'dollar_vol']
MARKET = []                    # no market timing: the market's own direction is the regime models' job (probabilities)
MARKET_ALL = ['spx13', 'spx_ma40', 'vix', 'curve', 'credit']
LABELS = {'mom4': 'momentum, 4 weeks', 'mom13': 'momentum, 13 weeks', 'mom26': 'momentum, 26 weeks', 'mom52x4': 'momentum, 12 months less the last one',
          'rev1': "last week's move (reversal)", 'hi52': 'distance from the 52-week high', 'lo52': 'distance from the 52-week low',
          'ma40': 'gap to the 40-week average', 'vol13': 'volatility, 13 weeks', 'volchg': 'volatility rising (13 ÷ 52 weeks)',
          'rs_sector13': 'return against its sector, 13 weeks', 'dollar_vol': 'size and liquidity (dollar volume traded)', 'spx13': 'S&P 500 momentum, 13 weeks',
          'spx_ma40': 'S&P 500 against its 40-week average', 'vix': 'VIX (fear gauge)', 'curve': 'yield curve (10-year − 3-month)',
          'credit': 'credit spread (Baa − 10-year)', 'const': 'average drift'}
EBINS = np.linspace(-8, 8, 641)


def fin(v):
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)


# ------------------------------------------------------------------ data
def load_panel(public, kind='stocks', limit=None):
    """The weekly grid of every t/<T>.json (stocks; kind 'etfs': the rotation ETFs and anything else on file) → tickers,
    names, sectors, dates (np datetime64[D]), C (N × T closes, adjusted), V (N × T dollar volume)."""
    public = Path(public)
    rrg = json.loads((public / 'rrg.json').read_text())
    start = np.datetime64(rrg['start'])
    W = len(rrg['bench']['c'])
    dates = start + 7 * np.arange(W)
    etf_ids = {s['id'] for s in rrg['series'] if not str(s['id']).startswith('s:')}
    files = sorted((public / 't').glob('*.json'))
    if limit:
        files = files[:limit]
    T, N, S, Cs, Vs = [], [], [], [], []
    for f in files:
        try:
            d = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        t = d.get('t') or f.stem
        is_etf = t in etf_ids or d.get('s') in (None, '', 'etf')
        if (kind == 'stocks') == is_etf:
            continue
        c = np.array([x if fin(x) and x > 0 else np.nan for x in d.get('c') or []], dtype=float)
        v = np.array([x if fin(x) else np.nan for x in d.get('v') or []], dtype=float)
        i0 = int((np.datetime64(d['start']) - start).astype(int) // 7)
        row, vrow = np.full(W, np.nan), np.full(W, np.nan)
        n = min(len(c), W - i0)
        if i0 < 0 or n < 60:
            continue
        row[i0:i0 + n], vrow[i0:i0 + n] = c[:n], v[:n] * 1e3 * c[:n] if len(v) >= n else np.nan
        T.append(t); N.append(d.get('n') or t); S.append(d.get('s') or 'other'); Cs.append(row); Vs.append(vrow)
    spx = np.array([x if fin(x) else np.nan for x in rrg['bench']['c']], dtype=float)
    sectors = {s['id'][2:]: np.array([x if fin(x) else np.nan for x in s.get('c') or []], dtype=float)
               for s in rrg['series'] if str(s['id']).startswith('s:')}
    for k, a in list(sectors.items()):                       # each sector line on the grid from its own start
        i0 = int((np.datetime64(next(s for s in rrg['series'] if s['id'] == 's:' + k).get('start') or rrg['start']) - start).astype(int) // 7)
        row = np.full(W, np.nan)
        row[i0:i0 + len(a)] = a[:W - i0]
        sectors[k] = row
    return {'tickers': T, 'names': N, 'sectors': S, 'dates': dates, 'C': np.array(Cs), 'V': np.array(Vs), 'spx': spx, 'sector_lines': sectors}


ETF_START = np.datetime64('1993-01-01')      # a Friday: the grid of week-ending Fridays for the ETFs
ETF_FLOOR = 0.004                            # weekly volatility floor for ETFs (stocks: SIG_FLOOR)
CASH_VOL = 0.03                              # ETFs with under 3% a year of volatility (cash, T-bills, ultra-short bonds) left out


def load_etf_panel(root, limit=None):
    """The ETFs of the etf-history branch (root/public/index.json, root/cache/market/<SYM>.json weekly bars [date, close,
    adjusted close, volume]) on a grid of week-ending Fridays: total-return closes (distributions reinvested), dollar volume,
    the category (or the asset class when its category has under 8 funds) in place of a sector. Cash-like funds are left
    out: their direction is their yield."""
    root = Path(root)
    idx = json.loads((root / 'public' / 'index.json').read_text())
    F = idx['fields']
    funds = [dict(zip(F, r)) for r in idx['rows']]
    if limit:
        funds = funds[:limit]
    cat_n = {}
    for r in funds:
        cat_n[r.get('category')] = cat_n.get(r.get('category'), 0) + 1
    W = int((np.datetime64(dt.date.today()) - ETF_START).astype(int) // 7) + 2
    dates = ETF_START + 7 * np.arange(W)
    T, N, S, Cs, Vs, PX, NS = [], [], [], [], [], [], []
    cash = 0
    for r in funds:
        sym = r['symbol']
        if fin(r.get('vol')) and r['vol'] < CASH_VOL:
            cash += 1
            continue
        f = root / 'cache' / 'market' / f'{sym}.json'
        try:
            w = json.loads(f.read_text()).get('weekly') or []
        except (OSError, ValueError):
            continue
        row, vrow, last = np.full(W, np.nan), np.full(W, np.nan), np.nan
        for b in w:
            if len(b) < 3 or not fin(b[2]) or b[2] <= 0:
                continue
            j = int((np.datetime64(b[0][:10]) - ETF_START).astype(int) + 4) // 7
            if 0 <= j < W:
                row[j] = b[2]
                vrow[j] = b[3] * b[1] if len(b) > 3 and fin(b[3]) and fin(b[1]) else np.nan
                last = b[1] if fin(b[1]) else last
        if np.isfinite(row).sum() < 60:
            continue
        cat = r.get('category')
        T.append(sym); N.append(r.get('name') or sym); S.append(cat if cat and cat_n.get(cat, 0) >= 8 else (r.get('asset_class') or 'other'))
        Cs.append(row); Vs.append(vrow); PX.append(last); NS.append(bool(r.get('leveraged') or r.get('inverse')))
    C = np.array(Cs)
    spx = C[T.index('SPY')] if 'SPY' in T else np.nanmedian(C, axis=0)
    return {'tickers': T, 'names': N, 'sectors': S, 'dates': dates, 'C': C, 'V': np.array(Vs), 'spx': spx, 'sector_lines': {},
            'floor': ETF_FLOOR, 'price_now': np.array(PX, dtype=float), 'left_out_cash_like': cash,
            'no_short': np.array(NS, dtype=bool)}           # leveraged and inverse funds: borrow usually costly, never flagged short


def macro_weekly(public, dates):
    """VIX, the yield curve and the credit spread on the grid (macro.json's weekly features, as published)."""
    out = {k: np.full(len(dates), np.nan) for k in ('vix', 'curve', 'credit')}
    p = Path(public) / 'macro.json'
    if not p.exists():
        return out
    m = json.loads(p.read_text()).get('weekly') or {}
    s0 = np.datetime64(m.get('start')) if m.get('start') else None
    if s0 is None:
        return out
    off = int((s0 - dates[0]).astype(int) // 7)
    for k in out:
        a = (m.get('data') or {}).get(k) or []
        for j, v in enumerate(a):
            if fin(v) and 0 <= off + j < len(dates):
                out[k][off + j] = v
    for k in out:                                              # carry the last published value forward
        a = out[k]
        for j in range(1, len(a)):
            if not np.isfinite(a[j]) and np.isfinite(a[j - 1]):
                a[j] = a[j - 1]
    return out


# ------------------------------------------------------------------ signals
def _lag(a, k):
    out = np.full_like(a, np.nan)
    if k < a.shape[-1]:
        out[..., k:] = a[..., :-k] if k else a
    return out


def _roll(a, w, fn):
    """Rolling statistic over the last w columns (NaN-aware), per row."""
    out = np.full_like(a, np.nan)
    for t in range(w - 1, a.shape[-1]):
        out[..., t] = fn(a[..., t - w + 1:t + 1], axis=-1)
    return out


def _zcs(x):
    """Cross-sectional z-score each week (column), clipped to ±3."""
    with np.errstate(invalid='ignore', divide='ignore'):
        m = np.nanmean(x, axis=0, keepdims=True)
        s = np.nanstd(x, axis=0, keepdims=True)
        z = (x - m) / np.where(s > 0, s, np.nan)
    return np.clip(z, -3, 3)


def signals(P, macro):
    C, V = P['C'], P['V']
    L = np.log(C)
    r1 = L - _lag(L, 1)
    with np.errstate(invalid='ignore', all='ignore'):
        sig = np.sqrt(_roll(r1, SIG_WEEKS, np.nanvar))
        sig = np.where(np.isfinite(sig), np.maximum(sig, P.get('floor', SIG_FLOOR)), np.nan)
        hi = _roll(C, 52, np.nanmax)
        lo = _roll(C, 52, np.nanmin)
        ma = _roll(C, 40, np.nanmean)
        v13 = np.sqrt(_roll(r1, 13, np.nanvar))
        v52 = np.sqrt(_roll(r1, 52, np.nanvar))
        dv = _roll(V, 13, np.nanmean)
        sec_ret = np.full_like(C, np.nan)
        m13 = L - _lag(L, 13)
        groups = {}
        for i, s in enumerate(P['sectors']):
            groups.setdefault(s, []).append(i)
        for s, ix in groups.items():
            line = P['sector_lines'].get(s)
            if line is not None:
                ll = np.log(line)
                sec_ret[ix] = ll - _lag(ll, 13)
            elif len(ix) >= 5:                                 # no sector line (ETFs): the group's own average
                sec_ret[ix] = np.nanmean(m13[ix], axis=0)
        raw = {'mom4': L - _lag(L, 4), 'mom13': L - _lag(L, 13), 'mom26': L - _lag(L, 26), 'mom52x4': _lag(L, 4) - _lag(L, 52),
               'rev1': r1, 'hi52': C / hi - 1, 'lo52': C / lo - 1, 'ma40': C / ma - 1, 'vol13': v13, 'volchg': np.log(v13 / v52),
               'rs_sector13': (L - _lag(L, 13)) - sec_ret, 'dollar_vol': np.log(np.maximum(np.nan_to_num(dv, nan=0.0), 1.0))}
        X = {k: _zcs(v) for k, v in raw.items()}
        spx = np.log(P['spx'])
        sma = _roll(P['spx'][None, :], 40, np.nanmean)[0]
        mk = {'spx13': (spx - _lag(spx, 13)) * 4, 'spx_ma40': (P['spx'] / sma - 1) * 5, 'vix': (macro['vix'] - 20) / 10,
              'curve': macro['curve'] / 2, 'credit': (macro['credit'] - 2.5) / 1}
    return X, mk, sig, r1, dv


def design(X, mk, t, names=None):
    """The rows of week t: (n × K) with a constant, cross-sectional signals and market ones (a missing one at 0)."""
    n = next(iter(X.values())).shape[0]
    cols = [np.ones(n)] + [np.nan_to_num(X[k][:, t]) for k in CROSS] + [np.full(n, 0.0 if not np.isfinite(mk[k][t]) else mk[k][t]) for k in MARKET]
    return np.column_stack(cols)


FEATS = ['const'] + CROSS + MARKET
BASE = ['const', 'dollar_vol']          # kept in the no-signal baseline: what the name is, not a timing signal


def baseline(D):
    """The rows with every timing signal at its average (0) and the baseline columns as they are."""
    D0 = np.zeros_like(D)
    for k in BASE:
        j = FEATS.index(k)
        D0[:, j] = D[:, j]
    return D0


# ------------------------------------------------------------------ fitting
def labels(C, sig, h):
    L = np.log(C)
    with np.errstate(invalid='ignore'):
        r = np.full_like(C, np.nan)
        r[:, :-h] = L[:, h:] - L[:, :-h]
        z = r / (sig * math.sqrt(h))
    return r, z


def weekly_stats(X, mk, z, ok_rows):
    """Per week t: X'X and X'z over the names with a label (the sufficient statistics; cumulated for any training span)."""
    T = z.shape[1]
    K = len(FEATS)
    XX, Xz, n = np.zeros((T, K, K)), np.zeros((T, K)), np.zeros(T)
    for t in range(T):
        m = ok_rows[:, t] & np.isfinite(z[:, t])
        if m.sum() < 20:
            continue
        D = design(X, mk, t)[m]
        y = np.clip(z[m, t], -8, 8)
        XX[t], Xz[t], n[t] = D.T @ D, D.T @ y, m.sum()
    return XX, Xz, n


def ridge(XX, Xz, lam=RIDGE):
    K = XX.shape[0]
    A = XX + lam * np.eye(K)
    A[0, 0] -= lam                                             # the constant is not shrunk
    return np.linalg.solve(A, Xz)


def ecdf_of(res):
    """Residuals → a cumulative distribution on EBINS (for P(e ≤ x))."""
    res = res[np.isfinite(res)]
    h, _ = np.histogram(np.clip(res, EBINS[0], EBINS[-1]), bins=EBINS)
    c = np.concatenate([[0.0], np.cumsum(h)]) / max(1, len(res))
    return c


def cdf(c, x):
    return np.interp(x, EBINS, c)


def quantile_of(c, q):
    return float(np.interp(q, c, EBINS))


def cost_one_way(dv):
    """One-way trading cost (a fraction) from weekly dollar volume."""
    return np.where(dv >= 5e8, 0.0005, np.where(dv >= 5e7, 0.0015, np.where(dv >= 5e6, 0.004, 0.01)))


def auc(p, y):
    o = np.argsort(p)
    y = y[o]
    n1 = y.sum()
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return None
    ranks = np.arange(1, len(y) + 1)
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def _logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def platt(p, y, iters=30):
    """Platt scaling: P(y) = σ(a + b · logit(p)), fitted by Newton's method — sets the residual-based probabilities right
    where the residuals depend on the signals (the pooled distribution is not every name's)."""
    x, y = _logit(p), y.astype(float)
    a, b = 0.0, 1.0
    for _ in range(iters):
        q = 1 / (1 + np.exp(-(a + b * x)))
        w = q * (1 - q)
        g = np.array([np.sum(y - q), np.sum((y - q) * x)])
        H = np.array([[np.sum(w), np.sum(w * x)], [np.sum(w * x), np.sum(w * x * x)]]) + 1e-9 * np.eye(2)
        step = np.linalg.solve(H, g)
        a, b = a + step[0], b + step[1]
        if np.abs(step).max() < 1e-7:
            break
    return float(a), float(b)


def platt_apply(ab, p):
    return 1 / (1 + np.exp(-(ab[0] + ab[1] * _logit(p))))


def _raw(ec, zhat, s, cst, h):
    """Residual-based P(up), P(buy profit), P(short profit)."""
    with np.errstate(invalid='ignore', divide='ignore'):
        return (1 - cdf(ec, -zhat), 1 - cdf(ec, cst / s - zhat), cdf(ec, -(cst + BORROW * h / 52) / s - zhat))


def _outcomes(r, cst, h):
    return (r > 0, r > cst, r < -(cst + BORROW * h / 52))


def _wmean(x, caps=None):
    """The mean with the extreme 1% on each side capped (a few bad prints — an unadjusted split — would swamp a plain mean);
    caps: the (low, high) to cap at, else this sample's own 1st and 99th percentiles."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if not len(x):
        return None
    lo, hi = caps if caps else np.quantile(x, [0.01, 0.99])
    return float(np.mean(np.clip(x, lo, hi)))


def _halves(fl, y, base, yr):
    """The flagged hit rate and its no-signal expectation in the earlier and the later half of the out-of-sample years."""
    out = []
    if not fl.any():
        return out
    mid = np.median(np.unique(yr[fl]))
    for m in (yr <= mid, yr > mid):
        f = fl & m
        out.append([int(f.sum()), round(float(y[f].mean()), 4), round(float(base[f].mean()), 4)] if f.sum() >= 100 else [int(f.sum()), None, None])
    return out


def flag_ok(f):
    """Flags at a horizon and side only where they worked out of sample: the flagged trades made money more often than not,
    on the median and on the (capped) average after costs, and 2 points more often than the same names were expected to
    with no signal (base_hit: their own no-signal probability — the signals, not the choice of liquid names, did it), and
    at least 1 point more in each half of the years on their own (halves) — not one lucky stretch."""
    halves_ok = all(h[1] is not None and h[1] - h[2] >= 0.01 for h in (f or {}).get('halves') or []) if (f or {}).get('halves') is not None else True
    return bool(f and f.get('hit') is not None and f['hit'] > 0.5 and f['hit'] - f.get('base_hit', f['all_hit']) >= 0.02 and halves_ok
                and (f.get('net_median') or 0) > 0 and (f.get('net_mean') or 0) > 0)


def _pct_rank(x):
    """Percentile rank 0..1 of each value among the finite ones."""
    out = np.full(len(x), np.nan)
    m = np.isfinite(x)
    if m.sum():
        o = np.argsort(np.argsort(x[m]))
        out[m] = (o + 0.5) / m.sum()
    return out


def flags(pb, ps, p0b, p0s, can_short, allow=(True, True)):
    """The week's sides: edge = P(profit) − the same with no signal; a side when the better edge reaches EDGE_MIN and is
    among the top TOP_SHARE of the week's edges, and the trade is more likely than not to make money. allow: (buy, short) — a side whose flags did not work out of sample is
    ranked and shown but never flagged. → (edge, side 1 buy / −1 short / 0 none, percentile, eb, es)."""
    eb, es = pb - p0b, np.where(can_short, ps - p0s, -np.inf)
    eb_a, es_a = (eb if allow[0] else np.full_like(eb, -np.inf)), (es if allow[1] else np.full_like(eb, -np.inf))
    edge = np.maximum(eb_a, es_a)
    if not (allow[0] or allow[1]):
        edge = np.maximum(eb, es)
    edge_f = np.where(np.isfinite(edge), edge, np.nan)
    pct = _pct_rank(edge_f)
    on = (edge_f >= EDGE_MIN) & (pct >= 1 - TOP_SHARE) & (allow[0] or allow[1])
    buy = eb_a >= es_a
    on &= np.where(buy, pb, ps) > 0.5                           # and the trade itself more likely than not to make money
    side = np.where(on, np.where(buy, 1, -1), 0)
    return edge_f, side, pct, eb, np.where(np.isfinite(es), es, np.nan)


def run(P, macro, today=None, verbose=False):
    """Walk-forward scores and today's probabilities for every name."""
    X, mk, sig, r1, dv = signals(P, macro)
    C, dates = P['C'], P['dates']
    T = C.shape[1]
    years = np.array([int(str(d)[:4]) for d in dates])
    have = np.isfinite(C) & np.isfinite(sig) & np.isfinite(X['mom26'])
    first_year = int(years[np.argmax(have.sum(0) >= 50)]) + FIRST_TEST_YEARS
    out = {'horizons': {}, 'asof': str(dates[-1]), 'features': FEATS}
    cur_t = T - 1
    while cur_t > 0 and not np.isfinite(C[:, cur_t]).any():  # weeks not reached yet
        cur_t -= 1
    while cur_t > 0 and (np.isfinite(C[:, cur_t]).sum() < 0.5 * np.isfinite(C[:, cur_t - 1]).sum()):
        cur_t -= 1                                             # a week only partly on file: the one before
    names_now = have[:, cur_t]
    D_now = design(X, mk, cur_t)
    cost_now = 2 * cost_one_way(np.nan_to_num(dv[:, cur_t], nan=0.0))
    for hk, h in HORIZONS.items():
        r, z = labels(C, sig, h)
        XX, Xz, n = weekly_stats(X, mk, z, have)
        cXX, cXz = np.cumsum(XX, 0), np.cumsum(Xz, 0)

        def fit(t_end):
            """The model, its residual distribution, its calibration and the base rates from the weeks up to t_end."""
            b = ridge(cXX[t_end], cXz[t_end])
            zh, zz, ss, cc, rr = [], [], [], [], []
            for t in range(0, t_end + 1, 4):                   # every 4th week: quick, and the overlap matters less
                m = have[:, t] & np.isfinite(z[:, t])
                if m.sum():
                    zh.append(design(X, mk, t)[m] @ b); zz.append(np.clip(z[m, t], -8, 8))
                    ss.append(sig[m, t] * math.sqrt(h)); cc.append(2 * cost_one_way(np.nan_to_num(dv[m, t], nan=0.0))); rr.append(r[m, t])
            if not zh:
                return None
            zh, zz, ss, cc, rr = map(np.concatenate, (zh, zz, ss, cc, rr))
            ec = ecdf_of(zz - zh)
            raw, ys = _raw(ec, zh, ss, cc, h), _outcomes(rr, cc, h)
            return {'b': b, 'ec': ec, 'platt': [platt(p_, y_) for p_, y_ in zip(raw, ys)], 'base': [float(y_.mean()) for y_ in ys]}

        def predict(M, D, s, cst):
            raw = _raw(M['ec'], D @ M['b'], s, cst, h)
            return [platt_apply(ab, p_) for ab, p_ in zip(M['platt'], raw)]

        oos = {k: [] for k in ('p', 'y', 'base', 'ev')}
        ics, by_year = [], {}
        for Y in range(first_year, int(years[cur_t]) + 1):
            t_end = int(np.searchsorted(years, Y)) - h - 1        # the last week whose outcome is known before Y starts
            if t_end < 52:
                continue
            M = fit(t_end)
            if not M:
                continue
            ty = np.where(years == Y)[0]
            ty = ty[ty <= T - 1 - h]
            ps, ys = [], []
            for t in ty:
                m = have[:, t] & np.isfinite(r[:, t])
                if m.sum() < 20:
                    continue
                D = design(X, mk, t)[m]
                dvt = np.nan_to_num(dv[m, t], nan=0.0)
                cst = 2 * cost_one_way(dvt)
                s_ = sig[m, t] * math.sqrt(h)
                pr = predict(M, D, s_, cst)
                p0 = predict(M, baseline(D), s_, cst)
                can = dvt >= HTB_DV
                if P.get('no_short') is not None:
                    can &= ~P['no_short'][m]
                edge, side, pct, eb, es = flags(pr[1], pr[2], p0[1], p0[2], can)
                g = np.expm1(r[m, t])                         # the simple return
                net_b, net_s = g - cst, -g - cst - BORROW * h / 52
                oos['ev'].append(np.column_stack([eb, es, side, net_b, net_s, np.full(len(eb), Y)]))
                ps.append(np.column_stack(pr)); ys.append(np.column_stack(_outcomes(r[m, t], cst, h)).astype(float))
                if m.sum() >= 50:
                    zhat = D @ M['b']
                    ics.append(float(np.corrcoef(np.argsort(np.argsort(zhat)), np.argsort(np.argsort(r[m, t])))[0, 1]))
            if not ps:
                continue
            p_, y_ = np.vstack(ps), np.vstack(ys)
            by_year[Y] = {'n': int(len(p_)), 'brier': float(np.mean((p_[:, 0] - y_[:, 0]) ** 2)), 'brier_base': float(np.mean((M['base'][0] - y_[:, 0]) ** 2)),
                          'up_rate': float(y_[:, 0].mean()), 'auc': auc(p_[:, 0], y_[:, 0].astype(int))}
            oos['p'].append(p_); oos['y'].append(y_); oos['base'].append(np.tile(M['base'], (len(p_), 1)))
        if not oos['p']:
            continue
        p_all, y_all, b_all, ev = (np.vstack(oos[k]) for k in ('p', 'y', 'base', 'ev'))
        card = {'oos_years': [int(min(by_year)), int(max(by_year))], 'n': int(len(p_all)),
                'ic_mean': float(np.mean(ics)) if ics else None,
                'ic_t': float(np.mean(ics) / (np.std(ics) / math.sqrt(len(ics)))) if len(ics) > 2 and np.std(ics) > 0 else None,
                'by_year': {str(k): v for k, v in by_year.items()}}
        for j, key in enumerate(('up', 'buy', 'short')):
            p, y, bh = p_all[:, j], y_all[:, j], b_all[:, j]
            calib = []
            for lo_ in np.arange(0.20, 0.80, 0.04):
                m = (p >= lo_) & (p < lo_ + 0.04)
                if m.sum() >= 200:
                    calib.append([round(float(lo_), 2), round(float(lo_ + 0.04), 2), int(m.sum()), round(float(p[m].mean()), 4), round(float(y[m].mean()), 4)])
            dec = np.quantile(p, [0.1, 0.9])
            br, bb = float(np.mean((p - y) ** 2)), float(np.mean((bh - y) ** 2))
            card[key] = {'brier': br, 'brier_base': bb, 'brier_skill': 1 - br / bb if bb else None, 'auc': auc(p, y.astype(int)),
                         'rate': float(y.mean()), 'top_decile': float(y[p >= dec[1]].mean()), 'bottom_decile': float(y[p <= dec[0]].mean()),
                         'calibration': calib}
        # does the edge pay? deciles of each side's edge → how often that trade made money after costs, and the average net
        for j, key, col in ((1, 'buy', 0), (2, 'short', 1)):
            e_, ok_ = ev[:, col], np.isfinite(ev[:, col])
            net = ev[:, 3 + col]
            caps = tuple(np.quantile(net[np.isfinite(net)], [0.01, 0.99]))
            qs_ = np.quantile(e_[ok_], np.linspace(0, 1, 11))
            dec_ = []
            for a_, b_ in zip(qs_[:-1], qs_[1:]):
                mm = ok_ & (e_ >= a_) & (e_ <= b_)
                if mm.sum() >= 100:
                    dec_.append([round(float(a_), 4), round(float(b_), 4), int(mm.sum()), round(float(p_all[mm, j].mean()), 4),
                                 round(float(y_all[mm, j].mean()), 4), round(_wmean(net[mm], caps), 5), round(float(np.median(net[mm])), 5)])
            fl = ev[:, 2] == (1 if key == 'buy' else -1)
            card[key]['edge_deciles'] = dec_
            card[key]['flagged'] = {'n': int(fl.sum()), 'share': float(fl.mean()), 'hit': float(y_all[fl, j].mean()) if fl.any() else None,
                                    'base_hit': float(np.mean(p_all[fl, j] - ev[fl, col])) if fl.any() else None,
                                    'halves': _halves(fl, y_all[:, j], p_all[:, j] - ev[:, col], ev[:, 5]),
                                    'net_mean': _wmean(net[fl], caps) if fl.any() else None, 'net_median': float(np.median(net[fl])) if fl.any() else None,
                                    'all_hit': float(y_all[:, j].mean()), 'all_net_mean': _wmean(net, caps), 'all_net_median': float(np.median(net))}
            card[key]['flag_ok'] = flag_ok(card[key]['flagged'])
        # the model for today: every week whose outcome is known
        M = fit(cur_t - h)
        s_now = sig[:, cur_t] * math.sqrt(h)
        p_up, p_buy, p_short = predict(M, D_now, s_now, cost_now)
        p0 = predict(M, baseline(D_now), s_now, cost_now)       # the same name with no timing information
        zhat = D_now @ M['b']
        qs = {q: quantile_of(M['ec'], q) for q in (0.1, 0.5, 0.9)}
        card.update({'coef': {f: float(v) for f, v in zip(FEATS, M['b'])}, 'base_up': M['base'][0], 'base_buy': M['base'][1],
                     'base_short': M['base'][2], 'platt': M['platt'], 'residual_quantiles': {str(q): v for q, v in qs.items()}})
        out['horizons'][hk] = {'weeks': h, 'card': card, 'p_up': p_up, 'p_buy': p_buy, 'p_short': p_short, 'p0': p0, 'zhat': zhat, 's': s_now,
                               'q': {q: np.expm1(s_now * (zhat + v)) for q, v in qs.items()}, 'cost': cost_now, 'b': M['b']}
        if verbose:
            print(hk, json.dumps({k: {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in card[k].items() if kk != 'calibration'}
                                  for k in ('up', 'buy', 'short')}), 'IC', round(card['ic_mean'] or 0, 4), 't', round(card['ic_t'] or 0, 1))
    out['_now'] = {'t': cur_t, 'names': names_now, 'D': D_now, 'date': str(dates[cur_t]), 'dv': np.nan_to_num(dv[:, cur_t], nan=0.0),
                   'price': C[:, cur_t]}
    return out


def rows_now(P, R):
    """One row per name with a price this week: per horizon [p_up, p_buy, p_short, r_p10, r_p50, r_p90, cost, edge, side,
    strength (the edge's percentile this week; none at a horizon where neither side's flags worked out of sample)], the
    score (the best strength, 0–100; none when no horizon ranks), the side, its horizon, a hard-to-borrow flag and the top
    drivers."""
    now = R['_now']
    m = now['names']
    D = now['D']
    price = P.get('price_now') if P.get('price_now') is not None else now['price']
    can_short = (now['dv'] >= HTB_DV) & (np.nan_to_num(price, nan=0.0) >= HTB_PRICE)
    if P.get('no_short') is not None:
        can_short &= ~P['no_short']
    per = {}
    for hk, H in R['horizons'].items():
        ok = m & np.isfinite(H['p_up']) & np.isfinite(H['p_buy']) & np.isfinite(H['p_short'])
        edge, side, pct, eb, es = (np.full(len(m), np.nan) for _ in range(5))
        allow = (bool(H['card']['buy'].get('flag_ok')), bool(H['card']['short'].get('flag_ok')))
        e_, s_, p_, b_, x_ = flags(H['p_buy'][ok], H['p_short'][ok], H['p0'][1][ok], H['p0'][2][ok], can_short[ok], allow)
        edge[ok], side[ok], pct[ok], eb[ok], es[ok] = e_, s_, p_, b_, x_
        if not any(allow):
            pct[:] = np.nan                                    # no proven side at this horizon: shown, not ranked
        per[hk] = (ok, edge, side, pct)
    rows = []
    for i in np.where(m)[0]:
        rec = {'t': P['tickers'][i], 'n': P['names'][i], 's': P['sectors'][i], 'h': {}}
        best, best_any = (-1.0, 'none', None), (-1.0, None)
        num = lambda v, d: round(float(v), d) if np.isfinite(v) else None
        for hk, H in R['horizons'].items():
            ok, edge, side, pct = per[hk]
            if not ok[i]:
                continue
            sd = {1: 'buy', -1: 'short'}.get(int(side[i]), 'none')
            rec['h'][hk] = [round(float(H['p_up'][i]), 4), round(float(H['p_buy'][i]), 4), round(float(H['p_short'][i]), 4),
                            round(float(H['q'][0.1][i]), 4), round(float(H['q'][0.5][i]), 4), round(float(H['q'][0.9][i]), 4),
                            round(float(H['cost'][i]), 5), num(edge[i], 4), sd, num(pct[i], 3)]
            if sd != 'none' and pct[i] > best[0]:
                best = (float(pct[i]), sd, hk)
            if np.isfinite(pct[i]) and pct[i] > best_any[0]:
                best_any = (float(pct[i]), hk)
        if not rec['h']:
            continue
        hk_d = best[2] or best_any[1] or '1m'
        H = R['horizons'].get(hk_d) or next(iter(R['horizons'].values()))
        contrib = D[i] * H['b']
        order = np.argsort(-np.abs(contrib[1:])) + 1
        rec['drivers'] = [[FEATS[j], round(float(contrib[j]), 4)] for j in order[:4]]
        sc = best[0] if best[2] else best_any[0]
        rec['score'] = round(100 * sc, 1) if sc >= 0 else None
        rec['side'], rec['best_h'] = best[1], hk_d
        if not can_short[i]:
            rec['htb'] = 1
        rows.append(rec)
    rows.sort(key=lambda r: (r['side'] == 'none', -(r['score'] if r['score'] is not None else -1)))
    return rows


SHARD_FIELDS = ('t', 'n', 's', 'h', 'drivers', 'score', 'side', 'best_h', 'htb')


def shard_of(t):
    c = (str(t) or '_')[0].upper()
    return c if c.isalnum() else '_'


def card_brief(cards):
    """What one company's card needs from the model cards: per horizon the walk-forward skill and whether flags are on."""
    return {hk: {'years': c['oos_years'], 'ic': c['ic_mean'], **{k: {'skill': c[k]['brier_skill'], 'auc': c[k]['auc'], 'rate': c[k]['rate']}
                                                                  for k in ('up', 'buy', 'short')},
                 'flags': {k: {'on': c[k].get('flag_ok'), 'hit': c[k]['flagged']['hit'], 'base_hit': c[k]['flagged'].get('base_hit'), 'all_hit': c[k]['flagged']['all_hit'],
                               'net_median': c[k]['flagged']['net_median'], 'all_net_median': c[k]['flagged']['all_net_median']}
                           for k in ('buy', 'short')}}
            for hk, c in cards.items()}


def publish(out_dir, P, R, kind):
    """opportunity-<kind>.json (the screener and the model cards) and opportunity-<kind>/<A-Z, 0-9, _>.json (each name's row
    with a brief of the cards, for the company and ETF pages)."""
    out_dir = Path(out_dir)
    rows = rows_now(P, R)
    cards = {hk: {k: v for k, v in H['card'].items()} for hk, H in R['horizons'].items()}
    doc = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'asof': R['_now']['date'], 'kind': kind,
           'horizons': {hk: H['weeks'] for hk, H in R['horizons'].items()},
           'fields_h': ['p_up', 'p_buy', 'p_short', 'r_p10', 'r_p50', 'r_p90', 'cost', 'edge', 'side', 'strength'],
           'rules': {'edge_min': EDGE_MIN, 'top_share': TOP_SHARE, 'htb_dollar_volume': HTB_DV, 'htb_price': HTB_PRICE, 'borrow': BORROW},
           'labels': LABELS, 'cards': cards, 'rows': rows,
           'method': __doc__.split('\n\n')[1] if __doc__ else ''}
    (out_dir / f'opportunity-{kind}.json').write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')
    sd = out_dir / f'opportunity-{kind}'
    sd.mkdir(parents=True, exist_ok=True)
    for f in sd.glob('*.json'):
        f.unlink()
    brief = card_brief(cards)
    shards = {}
    for r in rows:
        shards.setdefault(shard_of(r['t']), {})[r['t']] = {k: r[k] for k in SHARD_FIELDS if k in r}
    for k, rs in shards.items():
        (sd / f'{k}.json').write_text(json.dumps({'asof': doc['asof'], 'generated_at': doc['generated_at'], 'kind': kind, 'horizons': doc['horizons'],
                                                  'fields_h': doc['fields_h'], 'rules': doc['rules'], 'labels': LABELS, 'cards': brief, 'rows': rs},
                                                 separators=(',', ':')), encoding='utf-8')
    return {'names': len(rows), 'buy': sum(r['side'] == 'buy' for r in rows), 'short': sum(r['side'] == 'short' for r in rows),
            **{hk: {'ic': round(c['ic_mean'] or 0, 4), **{f'{k}_skill': round(c[k]['brier_skill'] or 0, 4) for k in ('up', 'buy', 'short')},
                    **{f'{k}_flags': [c[k]['flag_ok'], round(c[k]['flagged']['hit'] or 0, 3), round(c[k]['flagged'].get('base_hit') or 0, 3), round(c[k]['flagged']['all_hit'], 3),
                                      round(c[k]['flagged']['net_median'] or 0, 4), round(c[k]['flagged']['all_net_median'], 4)] for k in ('buy', 'short')}}
               for hk, c in cards.items()}}


# ------------------------------------------------------------------ ledger
LEDGER_KEEP = 520                             # origins kept (ten years of weeks)
SETTLE_DAYS = 2                               # a week counts as closed two days after its Friday (every ticker refreshed)


def _read(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def freeze(L, R, rows, sha=None, today=None, made_at=None):
    """Freeze this week's forecasts once the week has closed (two days after its Friday) and before the next one is on
    file; never changed afterwards. Probabilities in thousandths, costs in hundredths of a basis point... (bp × 100)."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    D = R['_now']['date']
    O = L.setdefault('origins', {})
    d = dt.date.fromisoformat(D)
    if D in O or not (d + dt.timedelta(days=SETTLE_DAYS) <= today < d + dt.timedelta(days=7 + SETTLE_DAYS)):
        return False
    rec = {'made_at': made_at or dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'sha': sha,
           'base': {hk: [round(H['card']['base_up'], 4), round(H['card']['base_buy'], 4), round(H['card']['base_short'], 4)]
                    for hk, H in R['horizons'].items()},
           'tickers': [r['t'] for r in rows], 'h': {}}
    for hk in R['horizons']:
        cols = [r['h'].get(hk) for r in rows]
        k = lambda j, f=1000: [int(round(c[j] * f)) if c else -1 for c in cols]
        rec['h'][hk] = {'pu': k(0), 'pb': k(1), 'ps': k(2), 'e': k(7), 'c': k(6, 1e6),
                        'side': ''.join({'buy': 'b', 'short': 's'}.get(c[8], '-') if c else ' ' for c in cols)}
    O[D] = rec
    return True


def _calib_bins(p, y, nb=10):
    out = []
    for b in range(nb):
        m = (p >= b / nb) & (p < (b + 1) / nb) if b < nb - 1 else (p >= b / nb)
        out.append([int(m.sum()), round(float(p[m].sum()), 3), int(y[m].sum())])
    return out


def score_origin(rec, hk, h, C, t0, t1, pos):
    """Score one frozen origin at one horizon against what happened (today's adjusted closes at both ends)."""
    H = rec['h'][hk]
    ix = np.array([pos.get(t, -1) for t in rec['tickers']])
    pu, pb, ps, e = (np.array(H[k], dtype=float) / 1000 for k in ('pu', 'pb', 'ps', 'e'))
    cost = np.array(H['c'], dtype=float) / 1e6
    side = np.array(list(H['side']))
    have = (ix >= 0) & (pu >= 0)
    c0, c1 = np.full(len(ix), np.nan), np.full(len(ix), np.nan)
    c0[have], c1[have] = C[ix[have], t0], C[ix[have], t1]
    ok = have & np.isfinite(c0) & np.isfinite(c1) & (c0 > 0)
    if ok.sum() < 20:
        return None
    r = np.expm1(np.log(c1[ok] / c0[ok]))
    cst, sd, ee = cost[ok], side[ok], e[ok]
    nb, ns = r - cst, -r - cst - BORROW * h / 52
    y = {'up': r > 0, 'buy': nb > 0, 'short': ns > 0}
    p = {'up': pu[ok], 'buy': pb[ok], 'short': ps[ok]}
    base = dict(zip(('up', 'buy', 'short'), rec['base'][hk]))
    out = {'n': int(ok.sum()), 'missing': int(len(ix) - ok.sum())}
    for k in ('up', 'buy', 'short'):
        out[k] = {'rate': round(float(y[k].mean()), 4), 'p_mean': round(float(p[k].mean()), 4),
                  'brier': round(float(np.mean((p[k] - y[k]) ** 2)), 5), 'brier_base': round(float(np.mean((base[k] - y[k]) ** 2)), 5),
                  'calib': _calib_bins(p[k], y[k].astype(int))}
    for k, ch, net in (('buy', 'b', nb), ('short', 's', ns)):
        fl = sd == ch
        caps = tuple(np.quantile(net, [0.01, 0.99]))
        out['flag_' + k] = {'n': int(fl.sum()), 'hit': round(float((net[fl] > 0).mean()), 4) if fl.any() else None,
                            'net_mean': round(_wmean(net[fl], caps), 5) if fl.any() else None,
                            'net_median': round(float(np.median(net[fl])), 5) if fl.any() else None,
                            'all_hit': round(float((net > 0).mean()), 4), 'all_net_mean': round(_wmean(net, caps), 5),
                            'all_net_median': round(float(np.median(net)), 5)}
        top = np.where(fl)[0][np.argsort(-ee[fl])][:10]
        tk = np.array(rec['tickers'])[ok]
        out['flag_' + k]['top'] = [[str(tk[j]), round(float(p[k][j]), 3), round(float(ee[j]), 3), round(float(r[j]), 4)] for j in top]
    return out


def resolve(L, P, today=None):
    """Score every frozen origin whose horizon has closed; drop an origin's rows once all its horizons are scored."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    dates, C = P['dates'], P['C']
    pos = {t: i for i, t in enumerate(P['tickers'])}
    done = 0
    for D, rec in L.get('origins', {}).items():
        if 'tickers' not in rec:
            continue
        t0 = int(np.searchsorted(dates, np.datetime64(D)))
        if t0 >= len(dates) or str(dates[t0]) != D:
            continue
        res = rec.setdefault('res', {})
        for hk, h in HORIZONS.items():
            if hk in res or hk not in rec['h']:
                continue
            t1 = t0 + h
            if t1 >= len(dates) or dt.date.fromisoformat(str(dates[t1])) + dt.timedelta(days=SETTLE_DAYS) > today:
                continue
            sc = score_origin(rec, hk, h, C, t0, t1, pos)
            if sc:
                res[hk] = sc
                done += 1
        if all(hk in res for hk in rec['h']):
            del rec['tickers'], rec['h']
    keep = sorted(L.get('origins', {}))[-LEDGER_KEEP:]
    L['origins'] = {k: L['origins'][k] for k in keep}
    return done


def ledger_public(L):
    """What the page reads: per origin the scores (without the calibration counts), and the totals over every scored
    origin per horizon: Brier skill against the base rate, calibration, and how the flagged trades did against all."""
    origins, tot = [], {}
    for D in sorted(L.get('origins', {}), reverse=True):
        rec = L['origins'][D]
        res = rec.get('res') or {}
        origins.append({'date': D, 'made_at': rec.get('made_at'), 'sha': (rec.get('sha') or '')[:10],
                        'n': len(rec['tickers']) if 'tickers' in rec else max([v['n'] + v['missing'] for v in res.values()] or [0]),
                        'res': {hk: {k: ({kk: vv for kk, vv in v.items() if kk != 'calib'} if isinstance(v, dict) else v) for k, v in sc.items()}
                                for hk, sc in res.items()}})
        for hk, sc in res.items():
            T = tot.setdefault(hk, {'origins': 0, 'n': 0, **{k: {'sq': 0.0, 'sq_base': 0.0, 'y': 0, 'p': 0.0, 'calib': [[0, 0.0, 0] for _ in range(10)]}
                                                              for k in ('up', 'buy', 'short')},
                                    'flag_buy': [0, 0.0, 0.0], 'flag_short': [0, 0.0, 0.0], 'all_buy': [0, 0.0, 0.0], 'all_short': [0, 0.0, 0.0]})
            T['origins'] += 1
            n = sc['n']
            T['n'] += n
            for k in ('up', 'buy', 'short'):
                a = T[k]
                a['sq'] += sc[k]['brier'] * n; a['sq_base'] += sc[k]['brier_base'] * n; a['y'] += sc[k]['rate'] * n; a['p'] += sc[k]['p_mean'] * n
                for b, (cn, cp, cy) in enumerate(sc[k]['calib']):
                    a['calib'][b][0] += cn; a['calib'][b][1] += cp; a['calib'][b][2] += cy
            for k in ('buy', 'short'):
                f = sc['flag_' + k]
                if f['n']:
                    T['flag_' + k][0] += f['n']; T['flag_' + k][1] += f['hit'] * f['n']; T['flag_' + k][2] += f['net_mean'] * f['n']
                T['all_' + k][0] += n; T['all_' + k][1] += f['all_hit'] * n; T['all_' + k][2] += f['all_net_mean'] * n
    totals = {}
    for hk, T in tot.items():
        n = max(1, T['n'])
        o = {'origins': T['origins'], 'n': T['n']}
        for k in ('up', 'buy', 'short'):
            a = T[k]
            o[k] = {'rate': a['y'] / n, 'p_mean': a['p'] / n, 'brier': a['sq'] / n, 'brier_base': a['sq_base'] / n,
                    'skill': 1 - a['sq'] / a['sq_base'] if a['sq_base'] else None,
                    'calib': [[b / 10, (b + 1) / 10, cn, cp / cn if cn else None, cy / cn if cn else None] for b, (cn, cp, cy) in enumerate(a['calib'])]}
        for k in ('flag_buy', 'flag_short', 'all_buy', 'all_short'):
            m_, h_, r_ = T[k]
            o[k] = {'n': m_, 'hit': h_ / m_ if m_ else None, 'net_mean': r_ / m_ if m_ else None}
        totals[hk] = o
    return {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'kind': L.get('kind'),
            'frozen': len(origins), 'scored': sum(1 for o in origins if o['res']), 'origins': origins, 'totals': totals}


def ledger_update(ledger_path, out_dir, P, R, rows, kind, sha=None, today=None):
    ledger_path = Path(ledger_path)
    L = _read(ledger_path, None) or {'kind': kind, 'origins': {}}
    froze = freeze(L, R, rows, sha, today)
    scored = resolve(L, P, today)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(L, separators=(',', ':')), encoding='utf-8')
    pub = ledger_public(L)
    (Path(out_dir) / f'opportunity-ledger-{kind}.json').write_text(json.dumps(pub, separators=(',', ':')), encoding='utf-8')
    return {'froze': R['_now']['date'] if froze else None, 'scored_now': scored, 'frozen': pub['frozen'], 'scored': pub['scored']}


def main():
    import argparse
    ap = argparse.ArgumentParser(description='Opportunity: direction, buy and short odds (app/opportunity.py)')
    ap.add_argument('--public', default='hist/public', help="stocks: public/ of rotation-history (t/<T>.json, rrg.json)")
    ap.add_argument('--root', default=None, help="ETFs: the etf-history checkout (public/index.json, cache/market/)")
    ap.add_argument('--kind', default='stocks', choices=['stocks', 'etfs'])
    ap.add_argument('--ledger', default=None, help='the frozen-forecast ledger file (kept on the data branch)')
    ap.add_argument('--sha', default=None)
    ap.add_argument('--limit', type=int, default=None)
    a = ap.parse_args()
    warnings.filterwarnings('ignore', category=RuntimeWarning)
    if a.kind == 'etfs':
        P = load_etf_panel(a.root or 'etf', a.limit)
        out_dir = Path(a.root or 'etf') / 'public'
        macro = {k: np.full(len(P['dates']), np.nan) for k in ('vix', 'curve', 'credit')}
    else:
        P = load_panel(a.public, 'stocks', a.limit)
        out_dir = Path(a.public)
        macro = macro_weekly(a.public, P['dates'])
    print(len(P['tickers']), a.kind, 'on file', flush=True)
    R = run(P, macro, verbose=True)
    summ = publish(out_dir, P, R, a.kind)
    if a.ledger:
        summ['ledger'] = ledger_update(a.ledger, out_dir, P, R, rows_now(P, R), a.kind, a.sha)
    print(json.dumps(summ))


if __name__ == '__main__':
    main()
