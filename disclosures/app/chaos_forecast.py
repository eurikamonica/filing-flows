"""Next-step forecasts for the rotation charts (Disclosures -> Rotation), by the method of analogues.

Every dot on the momentum clock, the solar system and the 3-D / 4-D boxes is a point in a state space. This module
asks, for each dot, "when the system was in a similar place, moving in a similar way, where did it go next?":

  1. Solar coordinates.  A company's position = market + (its sector sun - market) + (company - its sun).
     The planet layer (company - sun) and the sun layer (sun - market) are forecast separately, the market centre by
     its own past mean. This is exactly what the solar charts draw, so a forecast arrow on a planet is a move
     relative to its sun.
  2. Phase space.  Takens-style delay embedding: position and velocity (m=2) or position, velocity and acceleration
     (m=3) of a few coordinates, each in units of its typical spread.
  3. Analogues (Lorenz 1969; Farmer & Sidorowich 1987).  The k nearest past states of ANY company (or sector) whose
     next step was already public at the forecast date; the kernel-weighted mean of their next steps is the
     forecast, their spread the cone of uncertainty.
  4. Local divergence.  How far apart the analogues end up, against how close they started (log ratio per step): a
     finite-time, local stretching rate. It is a diagnostic of how predictable that region is, NOT a Lyapunov
     exponent of the market and NOT proof of deterministic chaos.
  5. Calibration.  Each variable's raw forecast is multiplied by a factor learnt only from earlier out-of-sample
     forecasts (separately for calm / middling / stretching regions), so a region with no skill gets an arrow of
     length ~0 instead of a confident wrong one.
  6. Price.  On the quarterly and monthly charts "stock vs the S&P 500" (rel) is a price coordinate:
     next close = close x (1 + (forecast rel + expected S&P return) / 100). On the RRG the next (RS-Ratio,
     RS-Momentum) point is a deterministic function of next week's close, so the forecast point is mapped back to the
     close whose RRG point is nearest to it (see rrg_* below).

Information set (no look-ahead): price-based coordinates at the period's last close; margins, growth and 13F one period
later (they are filed weeks after the quarter ends), so a quarter's forecast uses the previous quarter's figures. A past
state enters the analogue library only once its NEXT step was public at the forecast date.

Usage
  python chaos_forecast.py --public hist/public                 # writes public/chaos-forecast*.json (site files)
  python chaos_forecast.py --public hist/public --backtest out   # plus the full walk-forward experiment tables
"""
import argparse
import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import axis_registry as AR
from sklearn.neighbors import KDTree

PRICE_VARS = ['rel', 'rel3', 'rel6', 'ret', 'vola', 'volz', 'rs', 'mom121', 'hi52', 'iv30', 'pcoi']
FUND_VARS = ['dom', 'om', 'dgm', 'gm', 'dnm', 'nm', 'revg', 'reva', 'f13', 'gov', 'pc13']
# what the site forecasts and draws arrows for (variables with enough history; options data starts too late)
FORECAST_Q = ['rel', 'rel6', 'vola', 'volz', 'rs', 'mom121', 'hi52', 'dom', 'om', 'dgm', 'gm', 'dnm', 'nm', 'revg', 'reva']   # 13F starts 2025: too short
FORECAST_M = ['rel', 'rel3', 'rel6', 'volz', 'rs', 'mom121', 'hi52']   # monthly volatility is empty in the long file
EMBED_Q = ['rel', 'mom121', 'vola', 'hi52', 'dom', 'revg']        # chosen by the embedding grid (chaos_experiments.py)
EMBED_M = ['rel', 'rel3', 'hi52', 'volz']
SEED = 20261017


# ------------------------------------------------------------------ data
def cal_end(cal):
    """'CY2026Q3' -> 2026-09-30, '2026-09' -> 2026-09-30."""
    if cal.startswith('CY'):
        y, q = int(cal[2:6]), int(cal[-1])
        m = 3 * q
    else:
        y, m = int(cal[:4]), int(cal[5:7])
    nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
    return nxt - dt.timedelta(days=1)


def next_cal(cal):
    if cal.startswith('CY'):
        y, q = int(cal[2:6]), int(cal[-1])
        return f'CY{y + (q == 4)}Q{q % 4 + 1}'
    y, m = int(cal[:4]), int(cal[5:7])
    return f'{y + (m == 12)}-{m % 12 + 1:02d}'


class Panel:
    """Companies (E,T,V), sector suns (S,T,V) and the market centre (T,V), raw units as the site shows them."""

    def __init__(self, freq, cals, vars_, tickers, meta, sectors, sec_names, U, SUN, MKT):
        self.freq, self.cals, self.vars, self.tickers, self.meta = freq, cals, vars_, tickers, meta
        self.sectors, self.sec_names, self.U, self.SUN, self.MKT = sectors, sec_names, U, SUN, MKT
        self.vi = {v: i for i, v in enumerate(vars_)}
        self.ci = {c: i for i, c in enumerate(cals)}
        self.sidx = np.array([sectors.index(meta[t]['s']) if meta[t]['s'] in sectors else -1 for t in tickers])
        # filed after the period: lagged one period in the information set
        self.lag = np.array([1 if (freq == 'q' and v in FUND_VARS) else 0 for v in vars_])

    def layers(self):
        """planet = company - its sun, sun = sun - market (NaN where a sun is missing)."""
        sun_of = np.where(self.sidx[:, None, None] >= 0, self.SUN[np.maximum(self.sidx, 0)], np.nan)
        return self.U - sun_of, self.SUN - self.MKT[None]


def _rows(fields, rows):
    return [{k: r[i] for i, k in enumerate(fields)} for r in rows]


def load_quarterly(path):
    d = json.loads(Path(path).read_text(encoding='utf-8'))
    F, SF = d['fields'], d['sun_fields']
    vars_ = [k for k in F if k not in ('cal', 'rev')]
    cos = [(c, _rows(F, c['p'])) for c in d['companies']]
    suns = {k: _rows(SF, v['p']) for k, v in d['sectors'].items()}
    mkt = _rows(SF, d['market']['p'])
    cals = sorted({r['cal'] for _, rs in cos for r in rs} | {r['cal'] for rs in suns.values() for r in rs} | {r['cal'] for r in mkt})
    ci = {c: i for i, c in enumerate(cals)}
    tickers = [c['t'] for c, _ in cos]
    meta = {c['t']: {'n': c.get('n'), 's': c.get('s'), 'rev': c.get('rev'), 'cik': c.get('cik')} for c, _ in cos}
    sectors = sorted(suns)
    U = np.full((len(tickers), len(cals), len(vars_)), np.nan)
    REV = np.full((len(tickers), len(cals)), np.nan)
    for e, (_, rs) in enumerate(cos):
        for r in rs:
            U[e, ci[r['cal']]] = [np.nan if r.get(v) is None else r[v] for v in vars_]
            if r.get('rev') is not None:
                REV[e, ci[r['cal']]] = r['rev']
    SUN = np.full((len(sectors), len(cals), len(vars_)), np.nan)
    for s, k in enumerate(sectors):
        for r in suns[k]:
            SUN[s, ci[r['cal']]] = [np.nan if r.get(v) is None else r[v] for v in vars_]
    MKT = np.full((len(cals), len(vars_)), np.nan)
    for r in mkt:
        MKT[ci[r['cal']]] = [np.nan if r.get(v) is None else r[v] for v in vars_]
    names = {k: v.get('name', k) for k, v in d['sectors'].items()}
    P = Panel('q', cals, vars_, tickers, meta, sectors, names, U, SUN, MKT)
    P.rev = REV                                          # each quarter's own revenue (weights: known_rev_quarterly)
    return P


def weighted_centre(U, rev, vars_):
    """The site's sun / market average: log-revenue weights, each variable clipped to its 3rd-97th percentile. rev is
    one revenue per company or, as of each period, an (E, T) array of what each company had reported by then; the clip
    bounds are taken over the periods up to each one (expanding), so a past centre never moves with later data
    (research spec v5 §1.1). Fewer than ten values known: no clipping yet."""
    R = np.asarray(rev, float)
    if R.ndim == 1:
        R = np.repeat(R[:, None], U.shape[1], axis=1)
    w = np.log10(np.maximum(1e6, np.nan_to_num(R, nan=1e6)))
    out = np.full(U.shape[1:], np.nan)
    for j in range(U.shape[2]):
        x = U[:, :, j]
        fin = np.isfinite(x)
        if fin.sum() < 10:
            continue
        xc = x.copy()
        seen = np.empty(0)
        for t in range(x.shape[1]):
            seen = np.concatenate([seen, x[fin[:, t], t]])
            if len(seen) >= 10:
                lo, hi = np.percentile(seen, 3), np.percentile(seen, 97)
                xc[:, t] = np.clip(x[:, t], lo, hi)
        num = np.nansum(np.where(fin, xc * w, 0), axis=0)
        den = np.sum(np.where(fin, w, 0), axis=0)
        cnt = fin.sum(axis=0)
        out[:, j] = np.where(cnt >= 3, num / np.maximum(den, 1e-9), np.nan)
    return out


def known_rev_quarterly(P):
    """(E, T): the revenue each company had reported by the end of each calendar quarter — the latest quarter before it
    with revenue on file (P.rev holds each quarter's own revenue)."""
    R = getattr(P, 'rev', None)
    if R is None:
        return np.array([[P.meta[t]['rev'] or np.nan] * len(P.cals) for t in P.tickers], float)
    out = np.full(R.shape, np.nan)
    last = np.full(R.shape[0], np.nan)
    for t in range(R.shape[1]):
        out[:, t] = last                                   # quarter t's own revenue is filed during the next quarter
        last = np.where(np.isfinite(R[:, t]) & (R[:, t] > 0), R[:, t], last)
    return out


def known_rev_monthly(Pq, tickers, months, filed_after=46):
    """(E, months): each company's latest quarterly revenue public by the month's end — a quarter's revenue counts from
    46 days after the quarter (the 10-Q deadline is 40–45 days)."""
    R = getattr(Pq, 'rev', None)
    out = np.full((len(tickers), len(months)), np.nan)
    if R is None:
        out[:] = np.array([Pq.meta[t]['rev'] or np.nan for t in tickers], float)[:, None]
        return out
    avail = [cal_end(c) + dt.timedelta(days=filed_after) for c in Pq.cals]
    rows = [Pq.tickers.index(t) for t in tickers]
    for m, mo in enumerate(months):
        end = cal_end(mo)
        for e, r in enumerate(rows):
            for q in range(len(avail) - 1, -1, -1):
                if avail[q] <= end and np.isfinite(R[r, q]) and R[r, q] > 0:
                    out[e, m] = R[r, q]
                    break
    return out


def load_monthly(path, Pq):
    d = json.loads(Path(path).read_text(encoding='utf-8'))
    months, MF = d['months'], d['fields']
    tickers = [t for t in Pq.tickers if t in d['companies']]
    U = np.full((len(tickers), len(months), len(MF)), np.nan)
    for e, t in enumerate(tickers):
        for i, r in enumerate(d['companies'][t][:len(months)]):
            if r:
                U[e, i] = [np.nan if x is None else x for x in r]
    meta = {t: Pq.meta[t] for t in tickers}
    rev = known_rev_monthly(Pq, tickers, months)          # (E, months): revenue reported by each month's end
    sectors = Pq.sectors
    SUN = np.full((len(sectors), len(months), len(MF)), np.nan)
    for s, k in enumerate(sectors):
        idx = [e for e, t in enumerate(tickers) if meta[t]['s'] == k]
        if idx:
            SUN[s] = weighted_centre(U[idx], rev[idx], MF)
    MKT = weighted_centre(U, rev, MF)
    return Panel('m', months, MF, tickers, meta, sectors, Pq.sec_names, U, SUN, MKT)


def fill_latest_quarter_prices(Pq, Pm, closes=None):
    """The newest calendar quarter has rows only for early filers; its price coordinates are known for everyone at the
    quarter's last close, so fill them from the monthly file (rel and rel6 compounded from monthly returns, the levels
    at the quarter's last month, volatility and volume as three-month means). Only the latest quarter is touched."""
    last = Pq.cals[-1]
    if not last.startswith('CY'):
        return 0
    y, q = int(last[2:6]), int(last[-1])
    months = [f'{y}-{3 * q - 2 + k:02d}' for k in range(3)]
    py, pq = (y, q - 1) if q > 1 else (y - 1, 4)
    months6 = [f'{py}-{3 * pq - 2 + k:02d}' for k in range(3)] + months
    if not all(m in Pm.ci for m in months6):
        return 0
    filled = 0
    T = Pq.ci[last]
    for e, t in enumerate(Pq.tickers):
        if t not in Pm.tickers:
            continue
        m = Pm.tickers.index(t)
        row = lambda mon, k: Pm.U[m, Pm.ci[mon], Pm.vi[k]]
        def comp(ms):
            r = np.array([row(x, 'ret') for x in ms]); s = r - np.array([row(x, 'rel') for x in ms])
            if not (np.isfinite(r).all() and np.isfinite(s).all()):
                return np.nan
            return 100 * (np.prod(1 + r / 100) - np.prod(1 + s / 100))
        vals = {'rel': comp(months), 'rel6': comp(months6), 'ret': 100 * (np.prod([1 + row(x, 'ret') / 100 for x in months]) - 1),
                'rs': row(months[-1], 'rs'), 'mom121': row(months[-1], 'mom121'), 'hi52': row(months[-1], 'hi52'),
                'vola': quarter_vola(closes.get(t), last) if closes else np.nan, 'volz': np.nanmean([row(x, 'volz') for x in months])}
        for k, v in vals.items():
            if k in Pq.vi and not np.isfinite(Pq.U[e, T, Pq.vi[k]]) and np.isfinite(v):
                Pq.U[e, T, Pq.vi[k]] = v
                filled += 1
    # the suns and the market for the latest quarter, from the filled company rows (the file's are early filers only)
    rev = list(known_rev_quarterly(Pq)[:, T])           # revenue reported by the end of the quarter
    for s, k in enumerate(Pq.sectors):
        idx = [e for e, t in enumerate(Pq.tickers) if Pq.meta[t]['s'] == k]
        if idx:
            c = weighted_centre(Pq.U[idx][:, T:T + 1], [rev[e] for e in idx], Pq.vars)[0]
            Pq.SUN[s, T] = np.where(np.isfinite(Pq.SUN[s, T]) & np.isin(Pq.vars, FUND_VARS), Pq.SUN[s, T], c)
    c = weighted_centre(Pq.U[:, T:T + 1], rev, Pq.vars)[0]
    Pq.MKT[T] = np.where(np.isfinite(Pq.MKT[T]) & np.isin(Pq.vars, FUND_VARS), Pq.MKT[T], c)
    return filled


def quarter_vola(series, cal):
    """Realised volatility of a calendar quarter from weekly closes, annualised, in % — the long file's definition
    (weekly log returns from the last Friday before the quarter to the last Friday in it; checked against its values)."""
    if series is None:
        return np.nan
    d, c = series
    y, q = int(cal[2:6]), int(cal[-1])
    start, end = np.datetime64(dt.date(y, 3 * q - 2, 1)), np.datetime64(cal_end(cal))
    x = c[(d > start - 7) & (d <= end)]
    r = np.diff(np.log(x)); r = r[np.isfinite(r)]
    return float(np.std(r, ddof=1) * math.sqrt(52) * 100) if len(r) >= 6 else np.nan


def weekly_closes(tdir, tickers):
    """{ticker: (dates ndarray[datetime64[D]], closes ndarray)} from public/t/<T>.json (Friday closes)."""
    out = {}
    for t in tickers:
        p = Path(tdir) / f'{t}.json'
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding='utf-8'))
        c = np.array([np.nan if x is None else x for x in d['c']], float)
        days = np.datetime64(d['start']) + 7 * np.arange(len(c))
        out[t] = (days, c)
    return out


def close_at(series, day):
    days, c = series
    i = np.searchsorted(days, np.datetime64(day), side='right') - 1
    while i >= 0 and not np.isfinite(c[i]):
        i -= 1
    return (c[i], str(days[i])) if i >= 0 and (np.datetime64(day) - days[i]).astype(int) <= 10 else (np.nan, None)


# ------------------------------------------------------------------ the forecaster
def info_set(X, lag):
    """Value known at the end of period t: X[t] for price coordinates, X[t-1] for those filed a period later."""
    out = X.copy()
    for j, L in enumerate(lag):
        if L:
            out[..., L:, j] = X[..., :-L, j]
            out[..., :L, j] = np.nan
    return out


def robust_scale(X, upto):
    x = X[:, :upto].reshape(-1, X.shape[-1])
    q75, q25 = np.nanpercentile(x, 75, axis=0), np.nanpercentile(x, 25, axis=0)
    s = (q75 - q25) / 1.349
    sd = np.nanstd(x, axis=0)
    return np.where(np.isfinite(s) & (s > 0), s, np.where(np.isfinite(sd) & (sd > 0), sd, 1.0))


def embed(K, scale, emb, m):
    """Delay embedding of the known coordinates: [position, velocity(, acceleration)] in units of typical spread."""
    Z = K[..., emb] / scale[emb]
    parts = [Z]
    if m >= 2:
        V = np.full_like(Z, np.nan); V[:, 1:] = Z[:, 1:] - Z[:, :-1]; parts.append(V)
    if m >= 3:
        A = np.full_like(Z, np.nan); A[:, 1:] = V[:, 1:] - V[:, :-1]; parts.append(A)
    return np.concatenate(parts, axis=-1)


class Layer:
    """One layer of the solar system (planets around suns, or suns around the market) with a walk-forward forecast."""

    def __init__(self, X, lag, emb_vars, vars_, first_test, m=2, k=60, vel_weight=1.0):
        self.X, self.lag, self.vars = X, np.asarray(lag), list(vars_)
        self.E, self.T, self.V = X.shape
        self.K = info_set(X, self.lag)                         # known at t
        self.scale = robust_scale(self.K, first_test)
        self.emb = [self.vars.index(v) for v in emb_vars]
        self.m, self.k = m, k
        Z = embed(self.K, self.scale, self.emb, m)
        if m >= 2:
            Z[..., len(self.emb):] *= vel_weight
        self.Z = Z
        nxt = np.full_like(X, np.nan); nxt[:, :-1] = X[:, 1:]  # next period's actual values
        self.D = nxt - self.K                                   # step from the last known value to next period's value
        self.nxt = nxt

    def library(self, t):
        """Library rows (e, s) whose embedding is complete and whose next step was public by the end of period t:
        price coordinates need s+1 <= t, coordinates filed a period later s+2 <= t (masked per variable)."""
        s_max = t - 1
        okZ = np.isfinite(self.Z[:, :s_max + 1]).all(axis=-1)
        e, s = np.nonzero(okZ)
        D = self.D[e, s].copy()
        late = (s[:, None] + 1 + self.lag[None, :]) > t
        D[late] = np.nan
        return e, s, self.Z[e, s], D

    def forecast(self, t, rng=None, surrogate=False, tree_cache=None):
        """Analogue forecast of next period for every entity at origin t. Returns dict of arrays (E,V) / (E,)."""
        e_lib, s_lib, Zl, Dl = self.library(t)
        q = np.isfinite(self.Z[:, t]).all(axis=-1)
        out = {'q': q, 'delta': np.full((self.E, self.V), np.nan), 'spread': np.full((self.E, self.V), np.nan),
               'lam': np.full(self.E, np.nan), 'n_lib': len(e_lib), 'dist': np.full(self.E, np.nan)}
        if len(e_lib) < 3 * self.k or not q.any():
            return out
        if surrogate:                                   # placebo: next steps shuffled across the library
            Dl = Dl[(rng or np.random.default_rng(SEED)).permutation(len(Dl))]
        tree = KDTree(Zl)
        k = min(self.k, len(Zl))
        dist, idx = tree.query(self.Z[q, t], k=k)
        h = np.maximum(np.median(dist, axis=1, keepdims=True), 1e-9)
        w = np.exp(-(dist / h) ** 2)                          # Gaussian kernel, bandwidth = median analogue distance
        Dn = Dl[idx]                                          # (nq, k, V)
        fin = np.isfinite(Dn)
        W = w[..., None] * fin
        den = W.sum(axis=1)
        mu = np.where(den > 1e-6, (W * np.nan_to_num(Dn)).sum(axis=1) / np.maximum(den, 1e-12), np.nan)
        var = np.where(den > 1e-6, (W * (np.nan_to_num(Dn) - mu[:, None]) ** 2).sum(axis=1) / np.maximum(den, 1e-12), np.nan)
        out['delta'][q] = mu
        out['spread'][q] = np.sqrt(var)
        # local divergence: how far apart the analogues' next positions are, against how close their present was
        pos = slice(0, len(self.emb))
        p0 = Zl[idx][..., pos] - self.Z[q, t][:, None, pos]
        d0 = (w * np.linalg.norm(p0, axis=-1)).sum(axis=1) / w.sum(axis=1)
        nxt_pos = Dn[..., self.emb] / self.scale[self.emb] + Zl[idx][..., pos]   # each analogue's next position
        centre = np.nansum(w[..., None] * np.nan_to_num(nxt_pos), axis=1) / w.sum(axis=1)[:, None]
        d1 = (w * np.linalg.norm(np.nan_to_num(nxt_pos - centre[:, None]), axis=-1)).sum(axis=1) / w.sum(axis=1)
        out['lam'][q] = np.log(np.maximum(d1, 1e-9) / np.maximum(d0, 1e-9))
        out['dist'][q] = h[:, 0]
        return out

    def linear(self, t, ridge=1.0):
        """Same inputs, linear map (a pooled VAR in phase space: damped rotation when its eigenvalues are complex)."""
        e_lib, s_lib, Zl, Dl = self.library(t)
        q = np.isfinite(self.Z[:, t]).all(axis=-1)
        pred = np.full((self.E, self.V), np.nan)
        if len(e_lib) < 50 or not q.any():
            return pred
        A = np.c_[np.ones(len(Zl)), Zl]
        Aq = np.c_[np.ones(q.sum()), self.Z[q, t]]
        for j in range(self.V):
            ok = np.isfinite(Dl[:, j])
            if ok.sum() < 50:
                continue
            G = A[ok].T @ A[ok] + ridge * np.eye(A.shape[1]); G[0, 0] -= ridge
            b = np.linalg.solve(G, A[ok].T @ Dl[ok, j])
            pred[q, j] = Aq @ b
        return pred

    def mean_reversion(self, t):
        """Gravity toward the centre: next = rho x known, rho per variable from the library (pooled AR(1))."""
        pred = np.full((self.E, self.V), np.nan)
        x, y = self.K[:, :t], self.nxt[:, :t]
        for j in range(self.V):
            s_ok = (np.arange(t)[None, :] + 1 + self.lag[j]) <= t
            ok = np.isfinite(x[..., j]) & np.isfinite(y[..., j]) & s_ok
            if ok.sum() < 30:
                continue
            a, b = x[..., j][ok], y[..., j][ok]
            rho = float(np.clip((a * b).sum() / max((a * a).sum(), 1e-12), -1, 1.2))
            pred[:, j] = (rho - 1) * self.K[:, t, j]
        return pred


def momentum(L, t):
    """Keep moving: next step = last step (only for coordinates in the embedding)."""
    pred = np.zeros((L.E, L.V))
    for j in range(L.V):
        prev = L.K[:, t - 1, j] if t >= 1 else np.nan
        pred[:, j] = L.K[:, t, j] - prev
    return pred


# ------------------------------------------------------------------ calibration (learnt from earlier forecasts only)
class Calibrator:
    """Stacked, walk-forward calibration of the landing point. Per variable and per local-divergence tercile:
        next = a * known + b * (known + analogue step)
    fitted by least squares on earlier forecasts whose outcome was public before the origin. It nests "stay put"
    (a=1, b=0), "fall back to the sun" (a=b=0) and the raw analogue (a=0, b=1), so a coordinate with no skill gets the
    best naive landing point instead of a confident wrong one. Too little history -> stay put (a=1, b=0)."""

    def __init__(self, V, min_n=200):
        self.V, self.min_n = V, min_n
        self.R, self.lam, self.K, self.L, self.A = [], [], [], [], []

    def add(self, origin, lag, lam, known, step, step_actual):
        n = len(lam)
        self.R.append(np.tile(origin + 1 + lag, (n, 1))); self.lam.append(lam)
        self.K.append(known); self.L.append(known + step); self.A.append(known + step_actual)

    def fit(self, t):
        if not self.R:
            return None
        R = np.vstack(self.R); lam = np.concatenate(self.lam); K = np.vstack(self.K); L = np.vstack(self.L); A = np.vstack(self.A)
        ok_lam = np.isfinite(lam)
        cuts = np.nanpercentile(lam[ok_lam & (R[:, 0] <= t)], [33.3, 66.7]) if (ok_lam & (R[:, 0] <= t)).sum() > 90 else np.array([np.inf, np.inf])
        tert = np.digitize(np.nan_to_num(lam, nan=0), cuts)
        coef = np.tile(np.array([1.0, 0.0]), (3, self.V, 1))
        for g in range(3):
            for j in range(self.V):
                ok = (R[:, j] <= t) & np.isfinite(K[:, j]) & np.isfinite(L[:, j]) & np.isfinite(A[:, j]) & (tert == g)
                if ok.sum() >= self.min_n:
                    X = np.c_[K[ok, j], L[ok, j]]
                    G = X.T @ X + 1e-6 * np.trace(X.T @ X) * np.eye(2)
                    coef[g, j] = np.linalg.solve(G, X.T @ A[ok, j])
        return cuts, coef

    @staticmethod
    def apply(fit, lam, known, step):
        """Calibrated step (landing point minus the known position)."""
        if fit is None:
            return np.zeros_like(step)
        cuts, coef = fit
        g = np.digitize(np.nan_to_num(lam, nan=0), cuts)
        jj = np.arange(step.shape[1])[None, :]
        a, b = coef[g[:, None], jj, 0], coef[g[:, None], jj, 1]
        land = a * known + b * (known + step)
        return land - known


# ------------------------------------------------------------------ walk-forward over a panel
def run_panel(P, emb_vars, forecast_vars, first_test, m=2, k=60, vel_weight=1.0, surrogate=True, keep=None, verbose=True):
    """Walk-forward analogue forecasts for every origin from 1 to T-1 (the last origin has no outcome: the live
    forecast). Returns per-origin records for companies, suns and the market plus the live forecast."""
    planet, sundev = P.layers()
    fv = [P.vi[v] for v in forecast_vars]
    lagv = P.lag[fv]
    Lp = Layer(planet[..., fv], lagv, emb_vars, forecast_vars, first_test, m, k, vel_weight)
    Ls = Layer(sundev[..., fv], lagv, emb_vars, forecast_vars, first_test, m, max(15, k // 4), vel_weight)
    # fallback phase space from price coordinates only, for dots whose filed figures are missing (e.g. a company that does
    # not tag operating income): same targets, its own calibration; the evaluation stays on the primary model
    price_emb = [v for v in emb_vars if v in PRICE_VARS]
    Lp2 = Layer(planet[..., fv], lagv, price_emb, forecast_vars, first_test, m, k, vel_weight) if price_emb and price_emb != list(emb_vars) else None
    Ls2 = Layer(sundev[..., fv], lagv, price_emb, forecast_vars, first_test, m, max(15, k // 4), vel_weight) if Lp2 else None
    mkt_K = info_set(P.MKT[None, :, fv], lagv)[0]
    calP, calS = Calibrator(len(fv)), Calibrator(len(fv), min_n=60)
    calP2, calS2 = Calibrator(len(fv)), Calibrator(len(fv), min_n=60)

    def merged(L1, L2, f1, f2, d1, d2):
        if L2 is None:
            return f1, d1
        use = ~f1['q'] & f2['q']
        f = {**f1, 'q': f1['q'] | use, 'fallback': use}
        for key in ('delta', 'spread'):
            f[key] = np.where(use[:, None], f2[key], f1[key])
        f['lam'] = np.where(use, f2['lam'], f1['lam'])
        return f, np.where(use[:, None], d2, d1)
    rng = np.random.default_rng(SEED)
    recs = []
    live = None
    T = len(P.cals)
    for t in range(max(2, m), T):
        fp1, fs1 = Lp.forecast(t), Ls.forecast(t)
        fitP, fitS = calP.fit(t), calS.fit(t)
        dP1 = np.where(fp1['q'][:, None], Calibrator.apply(fitP, fp1['lam'], np.nan_to_num(Lp.K[:, t]), np.nan_to_num(fp1['delta'])), np.nan)
        dS1 = np.where(fs1['q'][:, None], Calibrator.apply(fitS, fs1['lam'], np.nan_to_num(Ls.K[:, t]), np.nan_to_num(fs1['delta'])), np.nan)
        if Lp2 is not None:
            fp2, fs2 = Lp2.forecast(t), Ls2.forecast(t)
            dP2 = Calibrator.apply(calP2.fit(t), fp2['lam'], np.nan_to_num(Lp.K[:, t]), np.nan_to_num(fp2['delta']))
            dS2 = Calibrator.apply(calS2.fit(t), fs2['lam'], np.nan_to_num(Ls.K[:, t]), np.nan_to_num(fs2['delta']))
        else:
            fp2 = fs2 = dP2 = dS2 = None
        fp, dP_cal = merged(Lp, Lp2, fp1, fp2, dP1, dP2)
        fs, dS_cal = merged(Ls, Ls2, fs1, fs2, dS1, dS2)
        # market centre: its own expanding mean of next-period values (no analogues: too few points)
        mk_next = np.array([np.nanmean(P.MKT[1:t + 1 - L, j]) if t + 1 - L > 1 else np.nan for j, L in zip(fv, lagv)])
        rec = {'t': t, 'fp': fp, 'fs': fs, 'dP_cal': np.where(fp['q'][:, None], dP_cal, np.nan),
               'dS_cal': np.where(fs['q'][:, None], dS_cal, np.nan), 'mk_next': mk_next,
               'fp_primary': fp1, 'dP_cal_primary': dP1}
        if t < T - 1:
            rec['lin'] = Lp.linear(t)
            rec['mr'] = Lp.mean_reversion(t)
            rec['mom'] = momentum(Lp, t)
            if surrogate:
                rec['sur'] = Lp.forecast(t, rng=rng, surrogate=True)['delta']
            # outcomes feed the calibrators (they only become usable once public: Calibrator.fit checks dates)
            calP.add(t, lagv, fp1['lam'][fp1['q']], Lp.K[fp1['q'], t], fp1['delta'][fp1['q']], Lp.D[fp1['q'], t])
            calS.add(t, lagv, fs1['lam'][fs1['q']], Ls.K[fs1['q'], t], fs1['delta'][fs1['q']], Ls.D[fs1['q'], t])
            if Lp2 is not None:
                calP2.add(t, lagv, fp2['lam'][fp2['q']], Lp.K[fp2['q'], t], fp2['delta'][fp2['q']], Lp.D[fp2['q'], t])
                calS2.add(t, lagv, fs2['lam'][fs2['q']], Ls.K[fs2['q'], t], fs2['delta'][fs2['q']], Ls.D[fs2['q'], t])
            recs.append(rec)
        else:
            live = rec
        if verbose and (t % 12 == 0 or t == T - 1):
            print(f'  origin {P.cals[t]}: library {fp1["n_lib"]}, forecasts {int(fp1["q"].sum())} (+{int(fp["q"].sum() - fp1["q"].sum())} price-only)', flush=True)
    return {'P': P, 'Lp': Lp, 'Ls': Ls, 'fv': fv, 'vars': forecast_vars, 'lag': lagv, 'recs': recs, 'live': live,
            'mkt_K': mkt_K, 'first_test': first_test, 'fitP': calP.fit(T), 'fitS': calS.fit(T)}


# ------------------------------------------------------------------ evaluation
def spearman(a, b):
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 8:
        return np.nan
    ra = np.argsort(np.argsort(a[ok])); rb = np.argsort(np.argsort(b[ok]))
    return float(np.corrcoef(ra, rb)[0, 1])


def block_ci(x, reps=2000, seed=SEED):
    """Mean and 95% interval by resampling periods (each period one block: all companies that date together)."""
    x = np.asarray([v for v in x if np.isfinite(v)])
    if len(x) < 5:
        return np.nan, np.nan, np.nan
    r = np.random.default_rng(seed).choice(x, (reps, len(x)), replace=True).mean(axis=1)
    return float(x.mean()), float(np.quantile(r, .025)), float(np.quantile(r, .975))


def evaluate(R):
    """Two separate questions, each against its naive baseline (planet layer = company relative to its sun):
      arrow    - does the predicted step point the way the dot actually moved? (cosine in the default chart plane)
      landing  - is the predicted landing point closer than "stay put" and than "fall back to the sun"?
    For rel (a period return) the step is predictable almost by construction (returns do not persist, so the dot
    snaps back toward its sun); the landing point is what the price decode uses, so it is scored on its own."""
    P, Lp, vars_ = R['P'], R['Lp'], R['vars']
    test = [r for r in R['recs'] if r['t'] >= R['first_test']]
    j_rel = vars_.index('rel')
    jx = vars_.index('dom') if 'dom' in vars_ else vars_.index('hi52')
    models = ['persist', 'sun', 'momentum', 'mean_rev', 'linear', 'analog', 'analog_cal', 'surrogate']
    se = {m: [[] for _ in vars_] for m in models}
    rel_mse = {m: [] for m in models}
    ic = {m: [] for m in models}
    spread = {m: [] for m in models}
    cos2 = {m: [] for m in models}
    lam_err = []
    for r in test:
        t, fp = r['t'], r.get('fp_primary', r['fp'])          # like-for-like with the baselines (same phase space)
        q = fp['q']
        K = Lp.K[:, t]
        actual = Lp.D[:, t]                     # actual step; actual landing = K + actual
        steps = {'persist': np.zeros_like(actual), 'sun': -K, 'momentum': r['mom'], 'mean_rev': r['mr'], 'linear': r['lin'],
                 'analog': fp['delta'], 'analog_cal': r.get('dP_cal_primary', r['dP_cal']), 'surrogate': r.get('sur', np.full_like(actual, np.nan))}
        ok_all = q & np.isfinite(K[:, j_rel]) & np.isfinite(actual[:, j_rel])
        for m_, st in steps.items():
            st = np.where(q[:, None], st, np.nan)
            err = (actual - st) ** 2                 # = (actual landing - predicted landing)^2
            for j in range(len(vars_)):
                ok = np.isfinite(err[:, j]) & q
                se[m_][j].extend(err[ok, j] / Lp.scale[j] ** 2)
            ok = ok_all & np.isfinite(st[:, j_rel])
            rel_mse[m_].append(np.mean(err[ok, j_rel]) if ok.sum() else np.nan)
            land_hat, land = K[:, j_rel] + st[:, j_rel], K[:, j_rel] + actual[:, j_rel]
            if m_ not in ('persist', 'sun'):
                ic[m_].append(spearman(land_hat[ok], land[ok]))
                if ok.sum() >= 20:
                    lo, hi = np.quantile(land_hat[ok], [.2, .8])
                    spread[m_].append(float(land[ok][land_hat[ok] >= hi].mean() - land[ok][land_hat[ok] <= lo].mean()))
            elif m_ == 'persist':
                ic[m_].append(spearman(K[ok, j_rel], land[ok]))     # does this quarter's out-performance carry over?
            ax = np.c_[actual[:, jx] / Lp.scale[jx], actual[:, j_rel] / Lp.scale[j_rel]]
            px = np.c_[st[:, jx] / Lp.scale[jx], st[:, j_rel] / Lp.scale[j_rel]]
            ok2 = np.isfinite(ax).all(1) & np.isfinite(px).all(1) & (np.linalg.norm(px, axis=1) > 1e-9) & (np.linalg.norm(ax, axis=1) > 1e-9)
            if ok2.any():
                cos2[m_].extend((ax[ok2] * px[ok2]).sum(1) / (np.linalg.norm(ax[ok2], axis=1) * np.linalg.norm(px[ok2], axis=1)))
        ok = ok_all & np.isfinite(fp['delta'][:, j_rel])
        lam_err.extend(zip(fp['lam'][ok], np.abs(actual[ok, j_rel] - r.get('dP_cal_primary', r['dP_cal'])[ok, j_rel]) / Lp.scale[j_rel],
                           fp['spread'][ok, j_rel] / Lp.scale[j_rel]))
    mse = {m_: [np.mean(se[m_][j]) if se[m_][j] else np.nan for j in range(len(vars_))] for m_ in models}
    best_naive = [np.nanmin([mse['persist'][j], mse['sun'][j]]) for j in range(len(vars_))]
    landing = {m_: {v: {'vs_stay': 1 - mse[m_][j] / mse['persist'][j], 'vs_best_naive': 1 - mse[m_][j] / best_naive[j]}
                    for j, v in enumerate(vars_)} for m_ in models}
    base = np.array(rel_mse['sun'])           # for rel the better naive landing is the sun (returns do not persist)
    summary = {}
    for m_ in models:
        c = np.array(cos2[m_]) if cos2[m_] else np.array([np.nan])
        summary[m_] = {'arrow_hit': float(np.mean(c > 0)) if cos2[m_] else None, 'arrow_cosine': float(np.nanmean(c)) if cos2[m_] else None,
                       'rel_landing_vs_sun': landing[m_]['rel']['vs_best_naive'],
                       'rel_landing_mse_minus_sun_ci': block_ci(np.array(rel_mse[m_]) - base) if m_ != 'sun' else None,
                       'rel_landing_ic_ci': block_ci(ic[m_]) if ic[m_] else None,
                       'rel_quintile_spread_ci': block_ci(spread[m_]) if spread[m_] else None}
    le = np.array(lam_err)
    lam_tab = []
    if len(le) > 100:
        cuts = np.nanquantile(le[:, 0], [0, .2, .4, .6, .8, 1])
        for a, b in zip(cuts[:-1], cuts[1:]):
            sel = (le[:, 0] >= a) & (le[:, 0] <= b)
            lam_tab.append({'lam_lo': float(a), 'lam_hi': float(b), 'n': int(sel.sum()), 'abs_err_rel_sd': float(le[sel, 1].mean()),
                            'analog_spread_sd': float(le[sel, 2].mean())})
    return {'landing': landing, 'summary': summary, 'lambda_vs_error': lam_tab, 'n_test_periods': len(test),
            'plane': [vars_[jx], 'rel'], 'test_from': P.cals[R['first_test']], 'test_to': P.cals[test[-1]['t']] if test else None}


def price_backtest(R, closes, window=None, scale_mode='own'):
    """Decode next-period price from the forecast rel coordinate and score it against the actual close."""
    P, Lp, Ls, vars_ = R['P'], R['Lp'], R['Ls'], R['vars']
    j = vars_.index('rel')
    jr = P.vi.get('ret')
    rows = []
    spy_hist = (P.MKT[:, jr] - P.MKT[:, P.vi['rel']]) if jr is not None else None   # market ret - market rel ~ SPY
    resid_hist = []                                                                 # (resolved_at, |z|) for conformal
    for r in R['recs']:
        t = r['t']
        fp, fs = r['fp'], r['fs']
        c0, c1 = P.cals[t], P.cals[t + 1]
        d0, d1 = cal_end(c0), cal_end(c1)
        spy_mu = float(np.nanmean(spy_hist[1:t + 1])) if spy_hist is not None and t > 4 else 0.0   # expected S&P return
        sun_part = np.where(P.sidx >= 0, Ls.K[np.maximum(P.sidx, 0), t, j] + np.nan_to_num(r['dS_cal'][np.maximum(P.sidx, 0), j]), np.nan)
        mk_part = r['mk_next'][j]
        cuts = None
        hist = np.array([h[1] for h in resid_hist if h[0] <= t and (window is None or h[0] > t - window)])
        q80 = float(np.quantile(hist, .8)) if len(hist) > 200 else np.nan
        q95 = float(np.quantile(hist, .95)) if len(hist) > 200 else np.nan
        new_resid = []
        for e, tk in enumerate(P.tickers):
            if not fp['q'][e] or tk not in closes:
                continue
            k_now = Lp.K[e, t, j]
            rel_hat = mk_part + sun_part[e] + k_now + r['dP_cal'][e, j]
            rel_raw = mk_part + sun_part[e] + k_now + fp['delta'][e, j]
            rel_act = P.U[e, t + 1, P.vi['rel']]
            p0, _ = close_at(closes[tk], d0)
            p1, _ = close_at(closes[tk], d1)
            if not (np.isfinite(rel_hat) and np.isfinite(p0)):
                continue
            sd = interval_scale(P, Lp, fp, e, t, j, scale_mode) / 100        # in log-price units
            ret_hat = rel_hat + spy_mu
            lr = math.log(max(1e-6, 1 + ret_hat / 100))                      # intervals in log price: always positive
            row = {'origin': c0, 'target': c1, 'ticker': tk, 'sector': P.meta[tk]['s'], 'close': p0,
                   'rel_hat': rel_hat, 'rel_hat_raw': rel_raw, 'rel_actual': rel_act, 'rel_zero': mk_part,
                   'price_hat': p0 * (1 + ret_hat / 100), 'price_actual': p1, 'lam': fp['lam'][e], 'analog_sd': sd,
                   'lo80': p0 * math.exp(lr - q80 * sd) if np.isfinite(q80) else np.nan,
                   'hi80': p0 * math.exp(lr + q80 * sd) if np.isfinite(q80) else np.nan,
                   'lo95': p0 * math.exp(lr - q95 * sd) if np.isfinite(q95) else np.nan,
                   'hi95': p0 * math.exp(lr + q95 * sd) if np.isfinite(q95) else np.nan}
            rows.append(row)
            if np.isfinite(p1) and p1 > 0:
                new_resid.append(abs(math.log(p1 / p0) - lr) / sd)
        for z in new_resid:
            resid_hist.append((t + 1, z))
    return rows


def interval_scale(P, Lp, fp, e, t, j, mode='own', w=None):
    """Scale of the price interval for company e at origin t: the analogues' spread, the stock's own trailing
    root-mean-square stock-vs-S&P move (last 8 quarters / 12 months, known at t), or their geometric mean."""
    a = float(fp['spread'][e, j]); a = a if np.isfinite(a) and a > 1e-6 else float(Lp.scale[j])
    if mode == 'analog':
        return a
    w = w or (8 if P.freq == 'q' else 12)
    hist = P.U[e, max(0, t - w + 1):t + 1, P.vi['rel']]
    hist = hist[np.isfinite(hist)]
    b = float(np.sqrt(np.mean(hist ** 2))) if len(hist) >= 3 else a
    return b if mode == 'own' else math.sqrt(a * b)


def price_summary(rows, first_test_cal):
    import collections
    rows = [r for r in rows if r['origin'] >= first_test_cal and np.isfinite(r['rel_actual']) and np.isfinite(r['price_actual'])]
    if not rows:
        return {}
    a = np.array([r['rel_actual'] for r in rows]); h = np.array([r['rel_hat'] for r in rows]); z = np.array([r['rel_zero'] for r in rows])
    hr = np.array([r['rel_hat_raw'] for r in rows])
    pa = np.array([r['price_actual'] for r in rows]); ph = np.array([r['price_hat'] for r in rows]); p0 = np.array([r['close'] for r in rows])
    by = collections.defaultdict(list)
    for r in rows:
        by[r['origin']].append(r)
    ic = [spearman(np.array([x['rel_hat'] for x in g]), np.array([x['rel_actual'] for x in g])) for g in by.values()]
    icr = [spearman(np.array([x['rel_hat_raw'] for x in g]), np.array([x['rel_actual'] for x in g])) for g in by.values()]
    pm = lambda g, k: np.array([x[k] for x in g])
    mse_d = [np.mean((pm(g, 'rel_actual') - pm(g, 'rel_hat')) ** 2) - np.mean((pm(g, 'rel_actual') - pm(g, 'rel_zero')) ** 2) for g in by.values()]
    cov = lambda lo, hi: float(np.mean([(r['price_actual'] >= r[lo]) & (r['price_actual'] <= r[hi]) for r in rows if np.isfinite(r[lo])])) if any(np.isfinite(r[lo]) for r in rows) else None
    dir_hit = float(np.mean(np.sign(ph - p0) == np.sign(pa - p0)))
    base_up = float(np.mean(pa > p0))
    return {'n': len(rows), 'periods': len(by),
            'rel_rmse_forecast': float(np.sqrt(np.mean((a - h) ** 2))), 'rel_rmse_raw_analog': float(np.sqrt(np.mean((a - hr) ** 2))),
            'rel_rmse_market_only': float(np.sqrt(np.mean((a - z) ** 2))),
            'mse_minus_market_only_ci': block_ci(mse_d),
            'ic_calibrated_ci': block_ci(ic), 'ic_raw_analog_ci': block_ci(icr),
            'price_mape': float(np.mean(np.abs(ph - pa) / pa)), 'price_direction_hit': dir_hit, 'share_of_up_moves': base_up,
            'coverage80': cov('lo80', 'hi80'), 'coverage95': cov('lo95', 'hi95'),
            # by period (each period one block: a market-wide shock moves every company at once)
            'coverage80_by_period_ci': block_ci([np.mean([(x['price_actual'] >= x['lo80']) & (x['price_actual'] <= x['hi80']) for x in g if np.isfinite(x['lo80'])])
                                                 for g in by.values() if any(np.isfinite(x['lo80']) for x in g)]),
            'coverage95_by_period_ci': block_ci([np.mean([(x['price_actual'] >= x['lo95']) & (x['price_actual'] <= x['hi95']) for x in g if np.isfinite(x['lo95'])])
                                                 for g in by.values() if any(np.isfinite(x['lo95']) for x in g)])}


# ------------------------------------------------------------------ RRG (weekly): exact price <-> point map
def _ema(a, span, min_count=None):
    al = 2 / (span + 1); out = np.full(len(a), np.nan); m = None; c = 0
    need = min(span, 6) if min_count is None else min_count
    for i, v in enumerate(a):
        if not np.isfinite(v):
            m = None; c = 0; continue
        m = v if m is None else m + al * (v - m); c += 1
        out[i] = m if c >= need else np.nan
    return out


def rrg_series(rs, n=14, freq='w'):
    """Python port of rrg.js rrgCalc: RS-Ratio x and RS-Momentum y around 100, with the intermediate EMA states the
    one-step stepper needs. rs = 100 * close / SPY on the weekly grid."""
    sh = 4 if freq == 'w' else 2
    long = max(52, 3 * n) if freq == 'w' else max(24, 3 * n)
    s_ = _ema(rs, sh); t_ = _ema(s_, n)
    ok = np.isfinite(s_) & np.isfinite(t_) & (t_ != 0)
    dev = np.where(ok, 100 * (s_ / np.where(ok, t_, 1) - 1), np.nan)
    d1 = np.full(len(dev), np.nan); d1[1:] = dev[1:] - dev[:-1]
    roc = _ema(d1, sh)

    def norm(a):
        out = np.full(len(a), np.nan)
        fin = np.isfinite(a); sq = np.where(fin, a * a, 0.0)
        cs = np.r_[0, np.cumsum(sq)]; cn = np.r_[0, np.cumsum(fin)]
        for k in np.nonzero(fin)[0]:
            lo = max(0, k - long + 1)
            m = cn[k + 1] - cn[lo]; s2 = cs[k + 1] - cs[lo]
            if m >= min(long, 26) and s2 > 0:
                out[k] = 100 + a[k] / math.sqrt(s2 / m)
        return out
    x = norm(dev); y = norm(roc); y[~np.isfinite(x)] = np.nan
    return {'x': x, 'y': y, 's': s_, 't': t_, 'dev': dev, 'roc': roc, 'sh': sh, 'n': n, 'long': long}


def rrg_xy(rs, n=14, freq='w'):
    S = rrg_series(rs, n, freq)
    return S['x'], S['y']


class RRGStepper:
    """The RRG at week i, able to give the next point for any hypothetical next RS value with exactly the browser's
    formula (one EMA step each, the normalising window extended by the new value), vectorised over candidates.
    So a forecast point maps back to the next close: the RS value whose next point is nearest to it."""

    def __init__(self, S, i):
        self.S, self.i = S, i
        L = S['long']
        self.wdev = S['dev'][max(0, i - L + 2):i + 1]; self.wdev = self.wdev[np.isfinite(self.wdev)]
        self.wroc = S['roc'][max(0, i - L + 2):i + 1]; self.wroc = self.wroc[np.isfinite(self.wroc)]

    def points(self, rs_next):
        S, i = self.S, self.i
        a_sh, a_n = 2 / (S['sh'] + 1), 2 / (S['n'] + 1)
        s1 = S['s'][i] + a_sh * (np.asarray(rs_next, float) - S['s'][i])
        t1 = S['t'][i] + a_n * (s1 - S['t'][i])
        dev1 = 100 * (s1 / t1 - 1)
        roc1 = S['roc'][i] + a_sh * ((dev1 - S['dev'][i]) - S['roc'][i])
        x = 100 + dev1 / np.sqrt(((self.wdev ** 2).sum() + dev1 ** 2) / (len(self.wdev) + 1))
        y = 100 + roc1 / np.sqrt(((self.wroc ** 2).sum() + roc1 ** 2) / (len(self.wroc) + 1))
        return np.c_[x, y]

    def invert(self, target_xy, scale_xy, rs_now, lo=-.25, hi=.25, grid=501):
        """Relative log-return r (next RS = RS x e^r) whose next point is nearest the target (in scaled units)."""
        r = np.linspace(lo, hi, grid)
        pts = self.points(rs_now * np.exp(r))
        d = np.hypot((pts[:, 0] - target_xy[0]) / scale_xy[0], (pts[:, 1] - target_xy[1]) / scale_xy[1])
        k = int(np.nanargmin(d))
        return float(r[k]), pts, r


def rrg_rows(closes, bench, tickers, n=14):
    """Per line: RS vs the benchmark on the weekly grid, the browser's RRG coordinates, and one row per week with the
    embedding [x, y, dx, dy], the next step (tx, ty) and next week's relative log return."""
    import pandas as pd
    bd, bc = bench
    series = {}
    for t in tickers:
        if t not in closes:
            continue
        d, c = closes[t]
        idx = np.searchsorted(bd, d)
        ok = (idx < len(bd)) & (bd[np.minimum(idx, len(bd) - 1)] == d)
        b = np.full(len(d), np.nan); b[ok] = bc[idx[ok]]
        rs = 100 * c / b
        S = rrg_series(rs, n)
        series[t] = (d, rs, S['x'], S['y'], S)
    rows = []
    for t, (d, rs, x, y, _) in series.items():
        dx = np.r_[np.nan, np.diff(x)]; dy = np.r_[np.nan, np.diff(y)]
        nx = np.r_[x[1:], np.nan]; ny = np.r_[y[1:], np.nan]
        with np.errstate(divide='ignore', invalid='ignore'):
            r_next = np.r_[np.log(rs[1:] / rs[:-1]), np.nan]
        rows.append(pd.DataFrame({'t': t, 'date': d, 'i': np.arange(len(d)), 'x': x, 'y': y, 'dx': dx, 'dy': dy,
                                  'tx': nx - x, 'ty': ny - y, 'r_next': r_next}))
    df = pd.concat(rows, ignore_index=True).dropna(subset=['x', 'y', 'dx', 'dy'])
    df = df[df.date >= np.datetime64('2002-01-01')].sort_values('date').reset_index(drop=True)
    return series, df


RRG_EMB = ['x', 'y', 'dx', 'dy']


def causal_scale(df, upto):
    """Per-axis spread of the RRG embedding [x, y, dx, dy] over the rows dated before `upto` only: the metric of a past
    origin's analogue search never depends on later weeks (research spec v5 §1.1; it used the whole history before)."""
    X = df.loc[(df.date < upto).to_numpy(), RRG_EMB].to_numpy(float)
    s = np.nanstd(X, axis=0, ddof=1) if len(X) > 1 else np.full(len(RRG_EMB), np.nan)
    return np.where(np.isfinite(s) & (s > 0), s, 1.0)


def expanding_log_drift(dates, closes, min_n=52):
    """(dates, mean weekly log return through each date): the benchmark's drift as known at that week, 0 before min_n
    returns. Replaces one full-history mean added to every past week's price."""
    c = np.asarray(closes, float)
    with np.errstate(divide='ignore', invalid='ignore'):
        lc = np.log(np.where(c > 0, c, np.nan))
    fin = np.isfinite(lc)
    lr = np.full(len(c), np.nan)
    last = None
    for i in range(len(c)):                          # returns between consecutive finite closes (gaps skipped)
        if fin[i]:
            if last is not None:
                lr[i] = lc[i] - lc[last]
            last = i
    ok = np.isfinite(lr)
    cs, cn = np.cumsum(np.where(ok, lr, 0.0)), np.cumsum(ok)
    return np.asarray(dates), np.where(cn >= min_n, cs / np.maximum(cn, 1), 0.0)


def drift_at(drift, day):
    d, m = drift
    i = int(np.searchsorted(d, np.datetime64(day), side='right')) - 1
    return float(m[i]) if i >= 0 else 0.0


def rrg_experiment(closes, bench, tickers, start='2012-01-06', n=14, k=80, refit_every=13, verbose=True):
    """Weekly walk-forward on the RRG: analogue forecast of the next (RS-Ratio, RS-Momentum) step vs persistence,
    rotation continuation and a linear map; then the forecast point mapped back to next week's relative return."""
    import pandas as pd
    series, df = rrg_rows(closes, bench, tickers, n)
    X = df[RRG_EMB].to_numpy(float)
    dates = np.sort(df.date.unique())
    test_dates = dates[dates >= np.datetime64(start)]
    out = []
    tree = None; built = None
    for wi, day in enumerate(test_dates):
        if tree is None or wi % refit_every == 0:
            sc = causal_scale(df, day)                                          # the metric as known at the refit
            lib = (df.date < day).to_numpy() & np.isfinite(df.tx).to_numpy()   # next point known by day (lib date < day)
            Zl, Tl = X[lib] / sc, df.loc[lib, ['tx', 'ty']].to_numpy()
            Rl = df.loc[lib, 'r_next'].to_numpy()
            tree = KDTree(Zl); built = day
            A = np.c_[np.ones(len(Zl)), Zl]
            Blin = np.linalg.lstsq(A, Tl, rcond=None)[0]
        qm = (df.date == day).to_numpy()
        if not qm.any():
            continue
        Zq = X[qm] / sc
        dist, idx = tree.query(Zq, k=min(k, len(Zl)))
        h = np.maximum(np.median(dist, 1, keepdims=True), 1e-9); w = np.exp(-(dist / h) ** 2)
        mu = (w[..., None] * Tl[idx]).sum(1) / w.sum(1)[:, None]
        r_an = (w * Rl[idx]).sum(1) / w.sum(1)               # analogues' own next relative return (direct read-out)
        lin = np.c_[np.ones(len(Zq)), Zq] @ Blin
        sub = df[qm]
        for row, m_, ra, li in zip(sub.itertuples(index=False), mu, r_an, lin):
            # rotation continuation: same angular speed and radius change around (100, 100) as last week
            a1 = math.atan2(row.y - 100, row.x - 100); a0 = math.atan2(row.y - row.dy - 100, row.x - row.dx - 100)
            r1 = math.hypot(row.x - 100, row.y - 100); r0 = math.hypot(row.x - row.dx - 100, row.y - row.dy - 100)
            dth = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
            rr = r1 * (r1 / r0 if r0 > 1e-6 else 1)
            rot = (100 + rr * math.cos(a1 + dth) - row.x, 100 + rr * math.sin(a1 + dth) - row.y)
            out.append({'t': row.t, 'date': str(row.date)[:10], 'i': row.i, 'x': row.x, 'y': row.y, 'tx': row.tx, 'ty': row.ty,
                        'an_x': m_[0], 'an_y': m_[1], 'lin_x': li[0], 'lin_y': li[1], 'rot_x': rot[0], 'rot_y': rot[1],
                        'r_next': row.r_next, 'r_analog_direct': ra, 'sx': sc[0], 'sy': sc[1]})
        if verbose and wi % 104 == 0:
            print('  RRG week', str(day)[:10], 'library', len(Zl), flush=True)
    res = pd.DataFrame(out)
    # price inversion: the forecast point mapped back to next week's relative return through the exact one-step map
    inv = []
    g0 = []
    for row in res.itertuples(index=False):
        d, rs, x, y, S = series[row.t]
        st = RRGStepper(S, int(row.i))
        gx, gy = st.points([rs[int(row.i)]])[0]                 # G0: zero relative return, the smoothing carried forward
        g0.append((gx - row.x, gy - row.y))
        r_inv, pts, grid = st.invert((row.x + row.an_x, row.y + row.an_y), (row.sx, row.sy), rs[int(row.i)])
        # identifiability: how much the next point moves per 1% of relative return (steeper = better determined)
        j0 = len(grid) // 2
        slope = float(np.hypot(*(pts[j0 + 1] - pts[j0 - 1])) / (grid[j0 + 1] - grid[j0 - 1]) / 100)
        r_lin, _, _ = st.invert((row.x + row.lin_x, row.y + row.lin_y), (row.sx, row.sy), rs[int(row.i)])
        inv.append({'t': row.t, 'date': row.date, 'r_next': row.r_next, 'r_inverted': r_inv, 'r_inverted_linear': r_lin,
                    'r_analog_direct': row.r_analog_direct, 'pts_per_pct': slope})
    if len(res):
        res['g0_x'] = [g[0] for g in g0]; res['g0_y'] = [g[1] for g in g0]
    return res, pd.DataFrame(inv)


def rrg_summary(res, inv):
    def skill(px, py):
        e = (res.tx - px) ** 2 + (res.ty - py) ** 2
        e0 = res.tx ** 2 + res.ty ** 2
        return float(1 - e.mean() / e0.mean())

    def cos(px, py):
        c = (res.tx * px + res.ty * py) / (np.hypot(res.tx, res.ty) * np.hypot(px, py) + 1e-12)
        return float((c > 0).mean()), float(c.mean())
    import collections
    out = {'rows': int(len(res)), 'weeks': int(res.date.nunique()), 'tickers': int(res.t.nunique()),
           'from': res.date.min(), 'to': res.date.max()}
    models = {'rotation': (res.rot_x, res.rot_y), 'linear': (res.lin_x, res.lin_y), 'analog': (res.an_x, res.an_y)}
    if 'g0_x' in res:
        models['g0'] = (res.g0_x, res.g0_y)
    quad = lambda x, y: np.where((x > 100) & (y > 100), 0, np.where((x > 100) & (y < 100), 1, np.where((x < 100) & (y < 100), 2,
                                                                                                      np.where((x < 100) & (y > 100), 3, 4))))
    actual_q = quad(res.x + res.tx, res.y + res.ty)
    for name, (px, py) in models.items():
        h, mc = cos(px, py)
        out[name] = {'step_skill_vs_persist': skill(px, py), 'direction_hit': h, 'mean_cosine': mc,
                     'next_quadrant_hit': float((quad(res.x + px, res.y + py) == actual_q).mean())}
        if name != 'g0' and 'g0_x' in res:          # the mechanical baseline (spec v5 §11.3 G0): skill beyond the smoothing
            e = (res.tx - px) ** 2 + (res.ty - py) ** 2
            e0 = (res.tx - res.g0_x) ** 2 + (res.ty - res.g0_y) ** 2
            out[name]['step_skill_vs_g0'] = float(1 - e.mean() / e0.mean())
    out['persistence'] = {'next_quadrant_hit': float((quad(res.x, res.y) == actual_q).mean())}
    if len(inv):
        by = collections.defaultdict(list)
        for r in inv.itertuples(index=False):
            by[r.date].append(r)
        ic = [spearman(np.array([x.r_inverted for x in g]), np.array([x.r_next for x in g])) for g in by.values()]
        icd = [spearman(np.array([x.r_analog_direct for x in g]), np.array([x.r_next for x in g])) for g in by.values()]
        icl = [spearman(np.array([x.r_inverted_linear for x in g]), np.array([x.r_next for x in g])) for g in by.values()]
        out['price_inversion'] = {'rows': int(len(inv)), 'ic_inverted_ci': block_ci(ic), 'ic_direct_analog_ci': block_ci(icd), 'ic_inverted_linear_ci': block_ci(icl),
                                  # a forecast exactly on the grid's zero says nothing about the sign: left out
                                  'sign_hit_inverted': float((np.sign(inv.r_inverted) == np.sign(inv.r_next))[inv.r_inverted != 0].mean()),
                                  'share_inverted_zero': float((inv.r_inverted == 0).mean()),
                                  'median_pts_per_pct': float(inv.pts_per_pct.median()),
                                  'corr_inverted_vs_direct': float(np.corrcoef(inv.r_inverted, inv.r_analog_direct)[0, 1])}
    return out


RRG_QUADS = ('leading', 'weakening', 'lagging', 'improving', 'boundary')


def rrg_quadrant(x, y):
    """Leading (x > 100, y > 100), weakening (x > 100, y < 100), lagging, improving; boundary on an axis; None if unknown."""
    if x is None or y is None or not (np.isfinite(x) and np.isfinite(y)):
        return None
    if x == 100 or y == 100:
        return 'boundary'
    return ('leading' if y > 100 else 'weakening') if x > 100 else ('improving' if y > 100 else 'lagging')


def rrg_transitions(series, groups, start='2010-01-01', horizons=(1, 4, 13)):
    """Descriptive RRG quadrant transitions (spec v5 §4.4, §6.7 style; status descriptive_only): per group of lines and
    horizon h, how often a line in quadrant i at week w was in quadrant j at week w + h, pooled over weeks since start,
    with Wilson 95% intervals (weeks treated as independent — they are not: overlapping windows), the spread of the row
    shares across calendar years, and the count of non-overlapping h-week windows (the independent periods)."""
    import crowd_clocks as CC
    t0 = np.datetime64(start)
    out = {}
    for gname, ids in groups.items():
        g = {}
        for h in horizons:
            cnt = {i: {j: 0 for j in RRG_QUADS} for i in RRG_QUADS}
            by_year = {}
            first = last = None
            for t in ids:
                if t not in series:
                    continue
                d, rs, x, y, _ = series[t]
                for w in range(len(d) - h):
                    if d[w] < t0:
                        continue
                    a, b = rrg_quadrant(x[w], y[w]), rrg_quadrant(x[w + h], y[w + h])
                    if a is None or b is None:
                        continue
                    cnt[a][b] += 1
                    yr = str(d[w])[:4]
                    by_year.setdefault(yr, {i: {j: 0 for j in RRG_QUADS} for i in RRG_QUADS})[a][b] += 1
                    first = d[w] if first is None or d[w] < first else first
                    last = d[w] if last is None or d[w] > last else last
            rows = []
            for i in RRG_QUADS:
                n = sum(cnt[i].values())
                cells = []
                for j in RRG_QUADS:
                    lo, hi = CC.wilson(cnt[i][j], n)
                    spread = [yc[i][j] / sum(yc[i].values()) for yc in by_year.values() if sum(yc[i].values()) >= 30]
                    cells.append({'n': cnt[i][j], 'p': round(cnt[i][j] / n, 4) if n else None, 'lo': lo, 'hi': hi,
                                  'year_min': round(min(spread), 4) if spread else None, 'year_max': round(max(spread), 4) if spread else None})
                rows.append({'from': i, 'n': n, 'cells': cells})
            span = int((last - first).astype('timedelta64[D]').astype(int) // 7) + 1 if first is not None else 0
            g[str(h)] = {'rows': rows, 'line_weeks': sum(r['n'] for r in rows), 'lines': sum(1 for t in ids if t in series),
                         'independent_periods': span // h, 'from': str(first)[:10] if first is not None else None,
                         'to': str(last)[:10] if last is not None else None}
        out[gname] = g
    return {'status': 'descriptive_only', 'quadrants': list(RRG_QUADS), 'horizons_weeks': list(horizons), 'groups': out,
            'note': ('How often a line in one RRG quadrant (around 100 / 100) was in each quadrant h weeks later, pooled over '
                     'weeks and lines. Rotation is smooth by construction, so staying put and clockwise moves dominate at '
                     'short horizons; weeks overlap, so the independent periods are the non-overlapping windows. History, not '
                     'a forecast.')}


def dual_transitions(tdir, tickers, bench, n=14, start='2010-01-01', horizons=(1, 4, 13)):
    """The dual RRG, described (spec v5 §4.4; descriptive_only): for every company whose weekly file carries its industry
    benchmarks (rotation_history.industry_benchmarks: bx without the company, bi with it), the company's quadrant against
    its industry without itself h weeks later, by where it and its industry (against SPY) stood. Rows: (industry
    quadrant, company quadrant); Wilson intervals; non-overlapping windows."""
    import crowd_clocks as CC
    bd, bc = bench
    t0 = np.datetime64(start)
    cnt = {h: {} for h in horizons}
    used, first, last = 0, None, None
    for t in tickers:
        p = Path(tdir) / f'{t}.json'
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding='utf-8'))
        if not d.get('bx') or not d.get('bi'):
            continue
        arr = lambda a: np.array([np.nan if x is None else x for x in a], float)
        c, bx, bi = arr(d['c']), arr(d['bx']), arr(d['bi'])
        days = np.datetime64(d['start']) + 7 * np.arange(len(c))
        idx = np.searchsorted(bd, days)
        ok = (idx < len(bd)) & (bd[np.minimum(idx, len(bd) - 1)] == days)
        spy = np.full(len(c), np.nan); spy[ok] = bc[idx[ok]]
        with np.errstate(divide='ignore', invalid='ignore'):
            Sc = rrg_series(np.where(bx > 0, 100 * c / bx, np.nan), n)
            Si = rrg_series(np.where(spy > 0, 100 * bi / spy, np.nan), n)
        used += 1
        for w in range(len(days)):
            if days[w] < t0:
                continue
            iq, cq = rrg_quadrant(Si['x'][w], Si['y'][w]), rrg_quadrant(Sc['x'][w], Sc['y'][w])
            if iq is None or cq is None:
                continue
            for h in horizons:
                if w + h >= len(days):
                    continue
                nq = rrg_quadrant(Sc['x'][w + h], Sc['y'][w + h])
                if nq is None:
                    continue
                row = cnt[h].setdefault((iq, cq), {q: 0 for q in RRG_QUADS})
                row[nq] += 1
            first = days[w] if first is None or days[w] < first else first
            last = days[w] if last is None or days[w] > last else last
    out = {}
    span = int((last - first).astype('timedelta64[D]').astype(int) // 7) + 1 if first is not None else 0
    for h in horizons:
        rows = []
        for iq in RRG_QUADS[:4]:
            for cq in RRG_QUADS[:4]:
                r = cnt[h].get((iq, cq))
                if not r:
                    continue
                nn = sum(r.values())
                rows.append({'industry': iq, 'from': cq, 'n': nn,
                             'cells': [{'n': r[q], 'p': round(r[q] / nn, 4), 'lo': CC.wilson(r[q], nn)[0], 'hi': CC.wilson(r[q], nn)[1]} for q in RRG_QUADS]})
        out[str(h)] = {'rows': rows, 'independent_periods': span // h}
    return {'status': 'descriptive_only', 'companies': used, 'from': str(first)[:10] if first is not None else None,
            'to': str(last)[:10] if last is not None else None, 'horizons_weeks': list(horizons), 'quadrants': list(RRG_QUADS), 'by_horizon': out,
            'note': ('Each company against its industry without itself (most specific SIC level with five or more other '
                     'companies, each counted while liquid; today\'s companies), grouped by where the company stood against that industry and where the '
                     'industry stood against the S&P 500; the share in each quadrant h weeks later. History, not a forecast.')}


def rrg_site_file(public, n=14, k=80, weeks_series='2010-01-01', weeks_companies=13, library_tickers=None, summary=None, gravity=None):
    """chaos-rrg.json: for the RRG lines the page offers (sector / style ETFs, site sectors, the largest companies per
    sector and the long-rotation companies), the forecast next point for each of the last weeks (out of sample: the
    library only holds weeks whose next point was known) and the next close read back from it."""
    public = Path(public)
    D = json.loads((public / 'rrg.json').read_text(encoding='utf-8'))
    grid0 = np.datetime64(D['start'])
    def arr(ent):
        c = np.array([np.nan if v is None else v for v in ent['c']], float)
        return (np.datetime64(ent['start']) + 7 * np.arange(len(c)), c)
    closes = {s['id']: arr(s) for s in D['series']}
    bench = arr(D['bench'])
    by_sec = {}
    for t, m in (D.get('tickers') or {}).items():
        if m and m.get('s'):
            by_sec.setdefault(m['s'], []).append((m.get('rev') or 0, t))
    top = {t for v in by_sec.values() for _, t in sorted(v, reverse=True)[:10]}
    lib = set(library_tickers or []) | top
    closes.update(weekly_closes(public / 't', sorted(lib)))
    ids = list(closes)
    series, df = rrg_rows(closes, bench, ids, n)
    X = df[RRG_EMB].to_numpy(float)
    weeks = np.sort(df.date.unique())
    drift = expanding_log_drift(*bench)           # the benchmark's average weekly log return as known at each week
    out_weeks = weeks[weeks >= np.datetime64(weeks_series)] if isinstance(weeks_series, str) else weeks[-weeks_series:]
    series_ids = {s['id'] for s in D['series']}
    sec_of = {s['id']: s.get('sector') for s in D['series'] if s.get('group') in ('sector-etf', 'site-sector')}
    gw = {}
    if gravity is not None:                       # weekly gravity forecasts vs SPY (satellite + planet), same weekly grid
        widx = [int((w - grid0).astype('timedelta64[D]').astype(int) // 7) for w in out_weeks]
        gsat, gpla = gravity.preds(1, widx)
        for w in widx:
            if w in gsat and w in gpla:
                pm = dict(zip(gpla[w][0], gpla[w][1]))
                sm = {gravity.D['tick'][i]: p_ + pm.get(gravity.secs.index(gravity.D['sec'][i]), np.nan) for i, p_ in zip(*gsat[w])}
                for sid, sk in sec_of.items():
                    if sk in gravity.secs and gravity.secs.index(sk) in pm:
                        sm[sid] = pm[gravity.secs.index(sk)]
                gw[w] = sm
    lines = {}
    tree, tree_w, dates_np, tx_ok = None, None, df.date.to_numpy(), np.isfinite(df.tx.to_numpy())
    for w in out_weeks:
        # the library: weeks before w whose next point is known. Rebuilt every 13 weeks (older weeks keep the tree
        # built at the start of their block, so a library is never later than its week; the last 13 weeks get their own)
        recent_w = w >= weeks[-weeks_companies]
        if tree is None or recent_w or (w - tree_w).astype('timedelta64[D]').astype(int) >= 91:
            lib_m = (dates_np < w) & tx_ok
            if lib_m.sum() < 1000:
                continue
            sc = causal_scale(df, w)              # metric from the weeks before w only, fixed until the next rebuild
            tree, tree_w = KDTree(X[lib_m] / sc), w; T = df.loc[lib_m, ['tx', 'ty']].to_numpy()
        qm = (df.date == w).to_numpy()
        if not qm.any():
            continue
        sub = df[qm]
        recent = w >= weeks[-weeks_companies]
        keep = np.array([(t in series_ids) or recent for t in sub.t])
        if not keep.any():
            continue
        sub = sub[keep]; Zq = X[qm][keep] / sc
        spy_mu = drift_at(drift, w)
        dist, idx = tree.query(Zq, k=min(k, lib_m.sum()))
        h = np.maximum(np.median(dist, 1, keepdims=True), 1e-9); wgt = np.exp(-(dist / h) ** 2)
        mu = (wgt[..., None] * T[idx]).sum(1) / wgt.sum(1)[:, None]
        wi = int((w - grid0).astype('timedelta64[D]').astype(int) // 7)
        for row, m_ in zip(sub.itertuples(index=False), mu):
            d, rs, x, y, S = series[row.t]
            st = RRGStepper(S, int(row.i))
            c_now = closes[row.t][1][int(row.i)]
            g = gw.get(wi, {}).get(row.t)
            if g is not None and np.isfinite(g):
                # gravity + tidal: forecast next week's price vs SPY, then the exact RRG step that price implies
                nx, ny = st.points([rs[int(row.i)] * math.exp(g)])[0]
                lines.setdefault(row.t, []).append([wi, r4(row.x, 3), r4(row.y, 3), r4(nx, 3), r4(ny, 3), r4(g, 5),
                                                    r4(c_now, 4), r4(c_now * math.exp(g + spy_mu), 4), 1])
                continue
            r_inv, _, _ = st.invert((row.x + m_[0], row.y + m_[1]), (sc[0], sc[1]), rs[int(row.i)])
            lines.setdefault(row.t, []).append([wi, r4(row.x, 3), r4(row.y, 3), r4(row.x + m_[0], 3), r4(row.y + m_[1], 3), r4(r_inv, 5),
                                                r4(c_now, 4), r4(c_now * math.exp(r_inv + spy_mu), 4), 0])
    rrg_bands(lines, series, grid0)
    grp = {s['id']: s.get('group') for s in D['series']}
    transitions = rrg_transitions(series, {
        'industry_vs_market': [t for t in series if grp.get(t) in ('sector-etf', 'site-sector')],
        'company_vs_market': [t for t in series if t not in grp]})
    try:
        transitions['dual'] = dual_transitions(public / 't', sorted(set(lib)), bench, n)
    except Exception as exc:                        # an older history without industry benchmarks
        transitions['dual'] = {'status': 'unavailable', 'note': f'{type(exc).__name__}: {exc}'}
    days = [str(grid0 + 7 * i) for i in range(int((weeks[-1] - grid0).astype('timedelta64[D]').astype(int) // 7) + 1)]
    doc = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'freq': 'w', 'n': n, 'k': k,
           'weeks': days, 'fields': ['week', 'x', 'y', 'next_x', 'next_y', 'rel_logret', 'close', 'close_next', 'model', 'half80_x', 'half80_y'],
           'models': ['analogues in RRG space, price read back', 'gravity + tidal price forecast, RRG step computed from it'],
           'lines': lines, 'backtest': summary or {}, 'transitions': transitions,
           'note': ('Next RS-Ratio / RS-Momentum: kernel-weighted mean of the next steps of the 80 most similar past weekly states '
                    '(position and last step) of any line. The next point is an exact function of next week\'s close (same formula '
                    'as the chart), so the close whose point is nearest the forecast is the price read back from it; plus the '
                    'benchmark\'s average weekly return up to that week. The analogue metric (the spread of each coordinate) '
                    'is measured on the weeks before each library rebuild only, so no past week uses later data.')}
    (public / 'chaos-rrg.json').write_text(json.dumps(jsonable(doc), separators=(',', ':')), encoding='utf-8')
    return doc


def rrg_bands(lines, series, grid0, window=260, q=80):
    """80% half-widths of the forecast next point, appended to every row: the q-th percentile of the absolute errors of
    the forecasts (all lines pooled) whose outcome was public by that week — errors of the last `window` weeks before
    it. Rows before 26 weeks of errors get None."""
    errs = {}
    for line, rows in lines.items():
        d, _, x, y, _ = series[line]
        for r in rows:
            i = int(np.searchsorted(d, grid0 + 7 * r[0]))
            if i + 1 < len(x) and i < len(d) and d[i] == grid0 + 7 * r[0] and np.isfinite(x[i + 1]) and np.isfinite(y[i + 1]) \
                    and r[3] is not None and r[4] is not None:
                errs.setdefault(r[0], []).append((abs(x[i + 1] - r[3]), abs(y[i + 1] - r[4])))
    band = {}
    weeks = sorted({r[0] for rows in lines.values() for r in rows})
    known = sorted(errs)
    for w in weeks:
        use = [e for k in known if w - window <= k <= w - 1 for e in errs[k]]
        if len({k for k in known if w - window <= k <= w - 1}) >= 26 and use:
            a = np.array(use)
            band[w] = (r4(np.percentile(a[:, 0], q), 3), r4(np.percentile(a[:, 1], q), 3))
    for rows in lines.values():
        for r in rows:
            r.extend(band.get(r[0], (None, None)))
    return band


def rrg_gravity_backtest(public, Gv, n=14, start='2012-01-06', every=2):
    """Weekly walk-forward of the gravity + tidal forecast on the RRG: IC of next week's return vs SPY across companies,
    and whether the RRG step computed from the forecast price points the way the dot actually moved (every 2nd week)."""
    public = Path(public)
    D = json.loads((public / 'rrg.json').read_text(encoding='utf-8'))
    grid0 = np.datetime64(D['start'])
    bc = np.array([np.nan if v is None else v for v in D['bench']['c']], float)
    bench = (np.datetime64(D['bench']['start']) + 7 * np.arange(len(bc)), bc)
    days = Gv.D['days']; t0 = int(np.searchsorted(days, np.datetime64(start)))
    weeks = list(range(t0, len(days) - 1, every))
    sat, pla = Gv.preds(1, weeks)
    C = Gv.D['C']; spy = Gv.D['spy']
    with np.errstate(all='ignore'):
        rs = 100 * C / spy[None]
    S_cache = {}
    ics, hit, cos_ = [], [], []
    for w in weeks:
        if w not in sat or w not in pla:
            continue
        pm = dict(zip(pla[w][0], pla[w][1]))
        idx, sp = sat[w]
        pred = np.array([p_ + pm.get(Gv.secs.index(Gv.D['sec'][i]), np.nan) for i, p_ in zip(idx, sp)])
        with np.errstate(all='ignore'):
            act = np.log(rs[idx, w + 1] / rs[idx, w])
        ok = np.isfinite(pred) & np.isfinite(act)
        if ok.sum() < 30:
            continue
        ics.append(spearman(pred[ok], act[ok]))
        for i, p_ in zip(idx[ok][:400:4], pred[ok][:400:4]):             # a sample of lines for the RRG step check
            if i not in S_cache:
                S_cache[i] = rrg_series(rs[i], n)
            S = S_cache[i]
            if not (np.isfinite(S['x'][w]) and np.isfinite(S['x'][w + 1])):
                continue
            nx, ny = RRGStepper(S, w).points([rs[i, w] * math.exp(p_)])[0]
            ax, ay = S['x'][w + 1] - S['x'][w], S['y'][w + 1] - S['y'][w]
            px, py = nx - S['x'][w], ny - S['y'][w]
            c = (ax * px + ay * py) / (math.hypot(ax, ay) * math.hypot(px, py) + 1e-12)
            cos_.append(c)
    return {'weeks': len(ics), 'ic_ci': block_ci(ics), 'step_direction_hit': float(np.mean(np.array(cos_) > 0)) if cos_ else None,
            'step_mean_cosine': float(np.mean(cos_)) if cos_ else None, 'from': start}


def galaxy_site_file(public, Gv, n=14, weeks_out=104, per_sector=150, fc_weeks=13):
    """galaxy.json for Rotation -> Galaxy: the market at the centre of a universe, every sector a galaxy, its companies the
    stars, the style / asset ETFs distant bodies. Every position is a weekly RRG point (RS-Ratio, RS-Momentum; the chart's
    exact formula, 14-week window): sectors and bodies against SPY, companies against their sector's index. Angle = where in
    the rotation cycle, distance = how strong. Next step for the last weeks from the gravity + tidal model: next week's price
    forecast, then the exact RRG step it implies. Values stored as round(100 x (v - 100))."""
    public = Path(public)
    D = json.loads((public / 'rrg.json').read_text(encoding='utf-8'))
    grid0 = np.datetime64(D['start'])
    W = int((np.datetime64(D['weeks']) - grid0).astype(int) // 7) + 1
    def full(ent):
        a = np.full(W, np.nan); o = int((np.datetime64(ent['start']) - grid0).astype(int) // 7)
        c = np.array([np.nan if v is None else v for v in ent['c']], float); a[o:o + len(c)] = c[:W - o]; return a
    spy = full(D['bench'])
    w0 = W - weeks_out
    enc = lambda a: [None if not np.isfinite(v) else int(round(100 * (v - 100))) for v in a]
    def rrg_vs(c, base):
        with np.errstate(all='ignore'):
            rs = np.where((base > 0) & np.isfinite(base) & np.isfinite(c), 100 * c / base, np.nan)
        return rs, rrg_series(rs, n)
    fcw = list(range(W - fc_weeks, W))
    gsat, gpla = Gv.preds(1, fcw) if Gv is not None else ({}, {})
    names = {s['sector']: s['name'].replace(' · site companies', '') for s in D['series'] if s.get('group') == 'site-sector'}
    levels = {s['sector']: full(s) for s in D['series'] if s.get('group') == 'site-sector'}
    # the market of these companies: equal-weighted (in logs) average of the sector indices, each rebased to its first week
    lv_ok = {k: v for k, v in levels.items() if k != 'other'}
    with np.errstate(all='ignore'):
        logs = np.array([np.log(v) - np.log(v[np.isfinite(v)][0]) for v in lv_ok.values()])
    site_mkt = np.exp(np.nanmean(logs, axis=0)) * 100
    galaxies = {}
    for sec, lv in levels.items():
        if sec == 'other':
            continue
        rs2, S2 = rrg_vs(lv, site_mkt)
        rs, S = rrg_vs(lv, spy)
        fx, fy = [None] * fc_weeks, [None] * fc_weeks
        fxm, fym = [None] * fc_weeks, [None] * fc_weeks
        if Gv is not None and sec in Gv.secs:
            pi = Gv.secs.index(sec)
            for k, w in enumerate(fcw):
                if w in gpla and np.isfinite(S['x'][w]):
                    pm = dict(zip(gpla[w][0], gpla[w][1]))
                    if pi in pm:
                        nx, ny = RRGStepper(S, w).points([rs[w] * math.exp(pm[pi])])[0]
                        fx[k], fy[k] = int(round(100 * (nx - 100))), int(round(100 * (ny - 100)))
                        # against the market of these companies: the sector's forecast minus the sectors' average forecast
                        mx_, my_ = RRGStepper(S2, w).points([rs2[w] * math.exp(pm[pi] - float(np.mean(list(pm.values()))))])[0]
                        fxm[k], fym[k] = int(round(100 * (mx_ - 100))), int(round(100 * (my_ - 100)))
        galaxies[sec] = {'name': names.get(sec, sec), 'x': enc(S['x'][w0:]), 'y': enc(S['y'][w0:]), 'fx': fx, 'fy': fy,
                         'xm': enc(S2['x'][w0:]), 'ym': enc(S2['y'][w0:]), 'fxm': fxm, 'fym': fym, 'members': 0}
    bodies = []
    for s_ in D['series']:
        if s_.get('group') != 'style-etf':
            continue
        rs, S = rrg_vs(full(s_), spy)
        if np.isfinite(S['x'][w0:]).sum() < 26:
            continue
        _, S2 = rrg_vs(full(s_), site_mkt)
        bodies.append([s_['id'], s_['name'], enc(S['x'][w0:]), enc(S['y'][w0:]), enc(S2['x'][w0:]), enc(S2['y'][w0:])])
    # stars: the largest liquid companies of each sector (liquid at the latest week, as the gravity model's universe)
    meta = D.get('tickers') or {}
    B = Gv.B if Gv is not None else None
    stars = []
    by_sec = {}
    for i, t in enumerate(Gv.D['tick'] if Gv is not None else []):
        sec = Gv.D['sec'][i]
        if sec not in galaxies:
            continue
        liquid = np.isfinite(B['dv13'][i, -1]) and B['dv13'][i, -1] >= 10e6 and B['close'][i, -1] >= 3
        if liquid:
            by_sec.setdefault(sec, []).append((meta.get(t, {}).get('rev') or 0, i, t))
    for sec, lst in by_sec.items():
        lst.sort(reverse=True)
        galaxies[sec]['members'] = len(lst)
        for rev, i, t in lst[:per_sector]:
            rs, S = rrg_vs(Gv.D['C'][i], levels[sec])
            if np.isfinite(S['x'][w0:]).sum() < 13:
                continue
            fx, fy, fr = [None] * fc_weeks, [None] * fc_weeks, [None] * fc_weeks
            for k, w in enumerate(fcw):
                if w in gsat and np.isfinite(S['x'][w]):
                    sm = dict(zip(gsat[w][0], gsat[w][1]))
                    if i in sm:
                        nx, ny = RRGStepper(S, w).points([rs[w] * math.exp(sm[i])])[0]
                        fx[k], fy[k], fr[k] = int(round(100 * (nx - 100))), int(round(100 * (ny - 100))), int(round(1e4 * sm[i]))
            c = Gv.D['C'][i]
            stars.append([t, meta.get(t, {}).get('n') or t, sec, int(rev), enc(S['x'][w0:]), enc(S['y'][w0:]), fx, fy, fr,
                          r4(c[-1], 2) if np.isfinite(c[-1]) else None])
    days = [str(grid0 + 7 * k) for k in range(w0, W)]
    doc = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'n': n, 'weeks': days, 'fc_from': weeks_out - fc_weeks,
           'centres': {'mkt': 'the market of these companies (equal-weighted average of the sector indices)', 'spy': 'SPY'},
           'scale': 'value = 100 + v / 100', 'benchmark': 'SPY',
           'star_fields': ['ticker', 'name', 'sector', 'revenue', 'x', 'y', 'next_x', 'next_y', 'next_rel_logret_bp', 'close'],
           'galaxies': galaxies, 'bodies': bodies, 'stars': stars,
           'note': ('Universe: the market at the centre — either the market of these companies (the sector indices averaged with equal '
                    'weight) or SPY (cap-weighted, dominated by the largest companies). Galaxies: the Sankey site\'s sectors (log-revenue-'
                    'weighted indices of their companies) placed by their weekly RRG point against that centre. Stars: each sector\'s largest liquid companies, placed by their RRG point against '
                    'their sector inside the galaxy. Distant bodies: style and asset ETFs against SPY. Angle = phase of the rotation '
                    '(leading, weakening, lagging, improving, clockwise); distance = strength, compressed so the far ones fit. Next step: '
                    'the gravity + tidal model\'s forecast of next week\'s price relative to the parent, drawn as the exact RRG step it '
                    'implies. Today\'s companies only.')}
    (public / 'galaxy.json').write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')
    return doc


# ------------------------------------------------------------------ the site files
def r4(x, nd=3):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


class Gravity:
    """The gravity + tidal model of gravity_pendulum.py (satellite = company vs its sector, planet = sector vs SPY, short
    pendulum restoring, long pendulum momentum, the planet's motion carried to its satellites), trained walk-forward on the
    site's companies' weekly closes. It forecasts the price coordinate; the analogues keep forecasting the other ones."""

    def __init__(self, public):
        import gravity_pendulum as GP
        self.GP = GP
        self.D = GP.load(public)
        self.B = GP.build(self.D)
        self.idx = {}
        for i, t in enumerate(self.D['tick']):
            self.idx[t] = i; self.idx[t.replace('-', '.')] = i
        self.secs = self.B['secs']
        self.m = self.B['m']
        self.cache = {}

    def week(self, day):
        return int(np.searchsorted(self.D['days'], np.datetime64(day), side='right') - 1)

    def preds(self, h, weeks):
        key = (h, tuple(sorted(set(weeks))))
        if key not in self.cache:
            self.cache[key] = (self.GP.predict_satellites(self.B, self.D, h, weeks), self.GP.predict_planets(self.B, self.D, h, weeks))
        return self.cache[key]

    def spy_mu(self, w, h):
        r = self.m[:w + 1]; r = r[np.isfinite(r)]
        return float(r.mean() * h) if len(r) > 52 else 0.0


def gravity_price_rows(P, Gv, closes, first_test_cal):
    """Next-period price of every company from the gravity + tidal model, on the chart's own calendar (quarter or month
    ends): log price vs SPY forecast = satellite + its planet; plus the S&P's past average. Ranges: walk-forward conformal
    in log price, scaled by the stock's trailing stock-vs-S&P moves (as the analogue rows)."""
    h = 13 if P.freq == 'q' else 4
    weeks = {t: Gv.week(cal_end(c)) for t, c in enumerate(P.cals) if t >= 1}
    sat, pla = Gv.preds(h, list(weeks.values()))
    jrel = P.vi['rel']; win = 8 if P.freq == 'q' else 12
    rows, resid = [], []
    for t in sorted(weeks):
        w = weeks[t]
        if w not in sat or w not in pla:
            continue
        si, sp = sat[w]; sm = dict(zip(si, sp)); pm = dict(zip(pla[w][0], pla[w][1]))
        mu = Gv.spy_mu(w, h)
        hist = np.array([z for (rt, z) in resid if rt <= t])
        q80 = float(np.quantile(hist, .8)) if len(hist) > 200 else np.nan
        q95 = float(np.quantile(hist, .95)) if len(hist) > 200 else np.nan
        new = []
        for e, tk in enumerate(P.tickers):
            gi = Gv.idx.get(tk)
            if gi is None or gi not in sm or tk not in closes:
                continue
            ps = Gv.secs.index(Gv.D['sec'][gi])
            if ps not in pm:
                continue
            pred = sm[gi] + pm[ps]                                     # log return vs SPY over the next h weeks
            p0, _ = close_at(closes[tk], cal_end(P.cals[t]))
            if not np.isfinite(p0):
                continue
            lr = pred + mu
            hst = P.U[e, max(0, t - win + 1):t + 1, jrel]; hst = hst[np.isfinite(hst)]
            sd = (float(np.sqrt(np.mean(hst ** 2))) if len(hst) >= 3 else 10.0) / 100
            last = t + 1 >= len(P.cals)
            p1 = close_at(closes[tk], cal_end(P.cals[t + 1]))[0] if not last else np.nan
            rel_act = P.U[e, t + 1, jrel] if not last else np.nan
            rel_hat = 100 * (math.exp(lr) - math.exp(mu))
            rows.append({'origin': P.cals[t], 'target': next_cal(P.cals[t]), 'ticker': tk, 'sector': P.meta[tk]['s'], 'close': p0,
                         'rel_hat': rel_hat, 'rel_hat_raw': rel_hat, 'rel_actual': rel_act, 'rel_zero': 0.0, 'model': 'gravity',
                         'price_hat': p0 * math.exp(lr), 'price_actual': p1, 'lam': np.nan, 'analog_sd': sd,
                         'lo80': p0 * math.exp(lr - q80 * sd) if np.isfinite(q80) else np.nan, 'hi80': p0 * math.exp(lr + q80 * sd) if np.isfinite(q80) else np.nan,
                         'lo95': p0 * math.exp(lr - q95 * sd) if np.isfinite(q95) else np.nan, 'hi95': p0 * math.exp(lr + q95 * sd) if np.isfinite(q95) else np.nan,
                         'sun_rel_hat': 100 * (math.exp(pm[ps] + mu) - math.exp(mu)), 'sun_key': Gv.D['sec'][gi]})
            if np.isfinite(p1) and p1 > 0:
                new.append(abs(math.log(p1 / p0) - lr) / sd)
        for z in new:
            resid.append((t + 1, z))
    return rows


def site_file(R, closes, price_rows, summary, price_sum, keep_periods=None, gravity_rows=None, price_analog=None):
    """Compact JSON for rotation.js: per company / sun / market and per origin, the forecast next value of each
    variable (raw units, as the chart shows them), the 80% half-width, the local divergence and the decoded price."""
    P, Lp, Ls, vars_ = R['P'], R['Lp'], R['Ls'], R['vars']
    recs = R['recs'] + ([R['live']] if R['live'] else [])
    if keep_periods:                                # a count of origins, or the first origin kept ('2010-01')
        recs = [r for r in recs if P.cals[r['t']] >= keep_periods] if isinstance(keep_periods, str) else recs[-keep_periods:]
    j = vars_.index('rel')
    pr = {(r['ticker'], r['origin']): r for r in price_rows}
    live_prices = live_price_rows(R, closes)
    pr.update({(r['ticker'], r['origin']): r for r in live_prices})
    gr = {(r['ticker'], r['origin']): r for r in (gravity_rows or [])}
    pr.update(gr)                                   # the gravity model's price where it covers the company
    sun_over = {}
    for r in gravity_rows or []:
        sun_over.setdefault((r['sun_key'], r['origin']), r['sun_rel_hat'])
    origins = [P.cals[r['t']] for r in recs]
    cos = {}
    for e, tk in enumerate(P.tickers):
        rows = []
        for oi, r in enumerate(recs):
            t, fp = r['t'], r['fp']
            if not fp['q'][e]:
                continue
            s = P.sidx[e]
            if s < 0:
                continue
            # next absolute value = market next + sun's known + sun step + planet's known + planet step
            nxt = r['mk_next'] + Ls.K[s, t] + np.nan_to_num(r['dS_cal'][s]) + Lp.K[e, t] + np.nan_to_num(r['dP_cal'][e])
            hw = 1.2816 * np.sqrt(fp['spread'][e] ** 2 + np.nan_to_num(r['fs']['spread'][s]) ** 2)   # planet and sun analogue spreads
            p = pr.get((tk, P.cals[t]))
            g = gr.get((tk, P.cals[t]))
            if g is not None:
                nxt = nxt.copy(); nxt[j] = g['rel_hat']      # the price coordinate's landing from the gravity model
            rows.append([oi, [r4(v, 2) for v in nxt], [r4(v, 2) for v in hw], r4(fp['lam'][e], 2),
                         r4(p['close'], 4) if p else None, r4(p['price_hat'], 4) if p else None,
                         r4(p['lo80'], 4) if p else None, r4(p['hi80'], 4) if p else None, 1 if g is not None else 0])
        if rows:
            cos[tk] = rows
    suns = {}
    for s, k in enumerate(P.sectors):
        rows = []
        for oi, r in enumerate(recs):
            t, fs = r['t'], r['fs']
            if not fs['q'][s]:
                continue
            nxt = r['mk_next'] + Ls.K[s, t] + np.nan_to_num(r['dS_cal'][s])
            if (k, P.cals[t]) in sun_over:
                nxt = nxt.copy(); nxt[j] = sun_over[(k, P.cals[t])]
            rows.append([oi, [r4(v, 2) for v in nxt], [r4(1.2816 * v, 2) for v in fs['spread'][s]], r4(fs['lam'][s], 2)])
        if rows:
            suns[k] = rows
    market = [[oi, [r4(v, 2) for v in r['mk_next']]] for oi, r in enumerate(recs)]
    return {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'freq': P.freq,
            'method': 'method of analogues in delay-embedded solar coordinates, calibrated by local divergence tercile',
            'origins': origins, 'targets': [next_cal(c) for c in origins], 'vars': vars_, 'embed': [vars_[i] for i in R['Lp'].emb],
            'embed_m': R['Lp'].m, 'k': R['Lp'].k,
            'fields': ['origin', 'next', 'half80', 'lam', 'close', 'price', 'lo80', 'hi80', 'price_model'],
            'price_models': ['analogues', 'gravity + tidal (short pendulum restoring, long pendulum momentum, sector carried to its companies)'],
            'companies': cos, 'suns': suns, 'market': market,
            'test_from': P.cals[R['first_test']],
            'axis_spec': (spec := AR.axis_spec(vars_, P.freq)), 'semantic_axis_spec_id': AR.semantic_axis_spec_id(spec),
            'caveats': [
                f'Origins before {P.cals[R["first_test"]]} are an in-sample warm-up: the coordinates\' typical spreads (the '
                'analogue metric) were measured on data through that period. Scorecards start there.',
                'Sector suns and the market centre are rebuilt as of each period (clip bounds over the periods up to then, '
                'weights = revenue reported by then), but the companies are today\'s: firms that left the market are missing '
                'from the early years (survivorship), which flatters every model.'],
            'backtest': {'state': summary, 'price': price_sum, 'price_analog': price_analog,
                         'price_model': 'gravity' if gravity_rows else 'analog'},
            'note': ('Each arrow: where the dot\'s next period lands on average among the most similar past states (any company, '
                     'position and velocity), shrunk toward no move by how well such arrows did before. lam: local divergence '
                     'of those analogues (log ratio per step; higher = they fan out = less predictable). Not a Lyapunov exponent '
                     'and not proof of chaos. The price coordinate (stock vs the S&P) and the price come from the gravity + tidal '
                     'model where it covers the company (price_model 1), otherwise from the analogues: close x exp(forecast vs '
                     'the S&P + the S&P\'s past average). '
                     'Origins before the last are walk-forward backtest forecasts whose analogue library held only steps public '
                     'at the time; see caveats for what is still retrospective.')}


def live_price_rows(R, closes):
    """Decoded prices for the live origin (no outcome yet)."""
    P, Lp, Ls, vars_ = R['P'], R['Lp'], R['Ls'], R['vars']
    r = R['live']
    if not r:
        return []
    j = vars_.index('rel'); jr = P.vi.get('ret')
    t = r['t']; d0 = cal_end(P.cals[t])
    spy_hist = (P.MKT[:, jr] - P.MKT[:, P.vi['rel']]) if jr is not None else None
    spy_mu = float(np.nanmean(spy_hist[1:t + 1])) if spy_hist is not None else 0.0
    # conformal multipliers from all resolved backtest rows
    q80 = R.get('q80'); q95 = R.get('q95')
    rows = []
    for e, tk in enumerate(P.tickers):
        if not r['fp']['q'][e] or tk not in closes or P.sidx[e] < 0:
            continue
        s = P.sidx[e]
        rel_hat = r['mk_next'][j] + Ls.K[s, t, j] + np.nan_to_num(r['dS_cal'][s, j]) + Lp.K[e, t, j] + np.nan_to_num(r['dP_cal'][e, j])
        p0, _ = close_at(closes[tk], d0)
        if not (np.isfinite(rel_hat) and np.isfinite(p0)):
            continue
        sd = interval_scale(P, Lp, r['fp'], e, t, j, R.get('scale_mode', 'own')) / 100; ret_hat = rel_hat + spy_mu
        lr = math.log(max(1e-6, 1 + ret_hat / 100))
        rows.append({'origin': P.cals[t], 'ticker': tk, 'close': p0, 'rel_hat': rel_hat, 'price_hat': p0 * (1 + ret_hat / 100),
                     'lo80': p0 * math.exp(lr - q80 * sd) if q80 else np.nan,
                     'hi80': p0 * math.exp(lr + q80 * sd) if q80 else np.nan})
    return rows


def conformal_q(price_rows, first_test_cal):
    z = [abs(math.log(r['price_actual'] / r['close']) - math.log(r['price_hat'] / r['close'])) / r['analog_sd'] for r in price_rows
         if r['origin'] >= first_test_cal and np.isfinite(r['price_actual']) and r['price_actual'] > 0 and r['price_hat'] > 0]
    return (float(np.quantile(z, .8)), float(np.quantile(z, .95))) if len(z) > 200 else (None, None)


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 6)
    if isinstance(o, np.integer):
        return int(o)
    return o


def build(public, backtest_dir=None, verbose=True, rrg_backtest=False):
    public = Path(public)
    Pq = load_quarterly(public / 'rotation-long.json')
    Pm = load_monthly(public / 'rotation-long-monthly.json', Pq) if (public / 'rotation-long-monthly.json').exists() else None
    closes = weekly_closes(public / 't', Pq.tickers)
    if Pm is not None:
        n = fill_latest_quarter_prices(Pq, Pm, closes)
        if verbose:
            print('latest quarter price coordinates filled from monthly and weekly closes:', n)
    out = {}
    try:
        Gv = Gravity(public)
        if verbose:
            print('gravity model: companies on file', len(Gv.D['tick']), flush=True)
    except Exception as exc:                          # the analogues still give every arrow and price
        print('gravity model unavailable:', type(exc).__name__, exc, flush=True)
        Gv = None
    for P, fvars, evars, first, keep, name in [(Pq, FORECAST_Q, EMBED_Q, '2015', None, 'chaos-forecast.json'),
                                                (Pm, FORECAST_M, EMBED_M, '2013', '2010-01', 'chaos-forecast-monthly.json')]:
        if P is None:
            continue
        fvars = [v for v in fvars if v in P.vi]
        ft = next(i for i, c in enumerate(P.cals) if cal_end(c).year >= int(first))
        if verbose:
            print(f'== {P.freq}: {len(P.tickers)} companies x {len(P.cals)} periods, test from {P.cals[ft]}', flush=True)
        # m=3 (position, velocity, acceleration) and k from the embedding grid (chaos_experiments.py grid)
        R = run_panel(P, [v for v in evars if v in fvars], fvars, ft, m=3, k=60 if P.freq == 'q' else 100, verbose=verbose)
        summ = evaluate(R)
        prow = price_backtest(R, closes)
        R['q80'], R['q95'] = conformal_q(prow, P.cals[ft])
        psum = price_summary(prow, P.cals[ft])
        grow, gsum = [], {}
        if Gv is not None:
            grow = gravity_price_rows(P, Gv, closes, P.cals[ft])
            gsum = price_summary(grow, P.cals[ft])
            if verbose:
                print('  price: analogues IC', psum.get('ic_calibrated_ci'), '| gravity IC', gsum.get('ic_calibrated_ci'),
                      'coverage80', gsum.get('coverage80'), flush=True)
        doc = site_file(R, closes, prow, jsonable(summ['summary']), jsonable(gsum or psum), keep_periods=keep,
                        gravity_rows=grow, price_analog=jsonable(psum))
        (public / name).write_text(json.dumps(jsonable(doc), separators=(',', ':')), encoding='utf-8')
        out[P.freq] = {'summary': summ, 'price': gsum or psum, 'price_analog': psum, 'R': R, 'price_rows': grow or prow}
        if verbose:
            print(json.dumps(jsonable({'state': summ['summary'], 'price': psum}), indent=1)[:3000], flush=True)
    if (public / 'rrg.json').exists():
        prev = public / 'chaos-rrg.json'
        summ = None
        try:
            summ = json.loads(prev.read_text(encoding='utf-8')).get('backtest') if prev.exists() else None
        except (OSError, ValueError):
            summ = None
        if rrg_backtest:                       # the weekly walk-forward is slow-ish (minutes): only when asked
            closes_all = weekly_closes(public / 't', Pq.tickers + ['SPY'])
            res, inv = rrg_experiment(closes_all, closes_all['SPY'], Pq.tickers, verbose=verbose)
            summ = rrg_summary(res, inv)
        if rrg_backtest and Gv is not None:
            summ = dict(summ or {}, gravity=rrg_gravity_backtest(public, Gv))
        if Gv is not None:
            try:
                g = galaxy_site_file(public, Gv)
                out['galaxy'] = {'stars': len(g['stars']), 'galaxies': len(g['galaxies']), 'bodies': len(g['bodies'])}
                if verbose:
                    print('galaxy:', out['galaxy'], flush=True)
            except Exception as exc:
                print('galaxy file skipped:', type(exc).__name__, exc, flush=True)
        doc = rrg_site_file(public, library_tickers=Pq.tickers, summary=summ, gravity=Gv)
        out['rrg'] = {'lines': len(doc['lines']), 'backtest': summ}
        if verbose:
            print('RRG forecasts for', len(doc['lines']), 'lines', flush=True)
    if backtest_dir:
        write_backtest(out, Path(backtest_dir))
    return out


def write_backtest(out, folder):
    import pandas as pd
    folder.mkdir(parents=True, exist_ok=True)
    for f, o in out.items():
        if f == 'rrg':
            (folder / 'summary_rrg.json').write_text(json.dumps(jsonable(o), indent=1)); continue
        pd.DataFrame(o['price_rows']).to_csv(folder / f'price_rows_{f}.csv', index=False)
        rows = [{'model': m, 'var': v, **x} for m, d in o['summary']['landing'].items() for v, x in d.items()]
        pd.DataFrame(rows).to_csv(folder / f'landing_skill_{f}.csv', index=False)
        (folder / f'summary_{f}.json').write_text(json.dumps(jsonable({'state': o['summary'], 'price': o['price']}), indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--public', default='hist/public')
    ap.add_argument('--backtest', default=None, help='folder for the full walk-forward tables')
    ap.add_argument('--rrg-backtest', action='store_true', help='also re-run the weekly RRG walk-forward (a few minutes)')
    a = ap.parse_args()
    build(a.public, a.backtest, rrg_backtest=a.rrg_backtest)


if __name__ == '__main__':
    main()
