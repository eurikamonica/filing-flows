"""Gravity-field + serial-pendulum test of the rotation charts' hypothesis (experiment; not part of the site build).

Hypothesis (the owner's): every company is a satellite of its sector (a planet), every sector orbits the market (the star),
and other bodies (rates, oil, gold, the rest of the world, small caps) pull on them. Motion is a chain of pendulums from long
to short: slow economic and 10-Q information sets where the faster market swings settle.

Position, not return.  The charts' "stock vs the S&P, the quarter" is a period return: a VELOCITY. Gravity acts on POSITION,
so here a satellite's position is its cumulative log price relative to its sector (leave-one-out), x_i(t); a planet's is its
sector's cumulative log price relative to SPY, y_s(t). Velocity v = change of position over one period, acceleration = change
of velocity. A restoring force is  a = -k (x - x*) - c v  :  k > 0 pulls back, k < 0 pushes away (momentum).

Serial pendulum in log price.  The chain of anchors is a ladder of exponential averages of position (4, 13, 52, 156 weeks):
  link 1 (shortest, T-n market data)  x - E4
  link 2                               E4 - E13
  link 3 (10-Q horizon)                E13 - E52
  link 4 (longest, economic cycle)     E52 - E156
Each link's coefficient on the next period's velocity is its gravity k_j (negative coefficient = restoring).

Layers tested, nested (each must add out of sample to count):
  M0 damping      v_t
  M1 gravity      + the four links
  M2 tidal        + the planet's last velocity and links (does the sector's motion carry to its satellites?)
  M3 other bodies + last-period moves of TLT, USO, GLD, EEM, IWM x the satellite's own exposure (rolling 104-week beta)
  M4 anchor       + 10-Q fundamentals relative to the sector, published one quarter later (core 250 companies)
  M5 state        M3 with every term allowed to differ in high-volatility weeks (state-dependent = nonlinear dynamics)
Star layer: SPY's own next-period return from its links and the other bodies (a time series, 1,000+ weeks).

Estimation: Fama-MacBeth cross-sections per period (coefficient signs, Newey-West t), and an expanding-window pooled
ridge refitted only on periods whose outcome was known (walk-forward). Scored by the per-period rank IC, the top-minus-
bottom decile return, and out-of-sample R^2 against zero, with period-block bootstrap intervals.
Physics: the fitted M1 equation is a linear dynamical system in (position, its averages); its eigenvalues give the damping
ratio, the orbital period and the Lyapunov exponent (a linear system can only be stable or explode; chaos needs M5-type
state dependence to matter).

  python gravity_pendulum.py --public hist/public --out notes/gravity-pendulum
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np

SPANS = (4, 13, 52, 156)
BODIES = ('TLT', 'USO', 'GLD', 'EEM', 'IWM')
SEED = 20261017


# ------------------------------------------------------------------ data on the weekly grid
def load(public, min_weeks=200):
    public = Path(public)
    D = json.loads((public / 'rrg.json').read_text(encoding='utf-8'))
    g0 = np.datetime64(D['start'])
    W = int((np.datetime64(D['weeks']) - g0).astype(int) // 7) + 1

    def place(start, arr, scale=1.0):
        a = np.full(W, np.nan)
        o = int((np.datetime64(start) - g0).astype(int) // 7)
        v = np.array([np.nan if x is None else x * scale for x in arr], float)
        a[o:o + len(v)] = v[:W - o]
        return a
    spy = place(D['bench']['start'], D['bench']['c'])
    bodies = {s['id']: place(s['start'], s['c']) for s in D['series'] if s['id'] in BODIES}
    tick, sec, rev, C, V = [], [], [], [], []
    for t, m in (D.get('tickers') or {}).items():
        if not m or m.get('s') in (None, 'other'):
            continue
        p = public / 't' / f'{t}.json'
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding='utf-8'))
        if sum(1 for x in d['c'] if x is not None) < min_weeks:
            continue
        tick.append(t); sec.append(m['s']); rev.append(m.get('rev') or 1e6)
        C.append(place(d['start'], d['c'])); V.append(place(d['start'], d.get('v') or [None] * len(d['c']), 1000.0))
    days = g0 + 7 * np.arange(W)
    return {'days': days, 'tick': np.array(tick), 'sec': np.array(sec), 'rev': np.array(rev, float), 'C': np.array(C), 'V': np.array(V),
            'spy': spy, 'bodies': bodies}


def logret(C):
    with np.errstate(divide='ignore', invalid='ignore'):
        r = np.diff(np.log(C), axis=-1, prepend=np.nan)
    r[~np.isfinite(r)] = np.nan
    r[np.abs(r) > 1.0] = np.nan                     # a weekly log move above 100%: a data error, not a move
    return r


def ema_path(x, span, min_obs=None):
    """EMA along the last axis that restarts after gaps; NaN until min_obs observations."""
    a = 2 / (span + 1); min_obs = min_obs or span
    out = np.full_like(x, np.nan); m = np.full(x.shape[:-1], np.nan); n = np.zeros(x.shape[:-1])
    for t in range(x.shape[-1]):
        v = x[..., t]; ok = np.isfinite(v)
        m = np.where(ok, np.where(np.isfinite(m), m + a * (v - m), v), np.nan)
        n = np.where(ok, n + 1, 0)
        out[..., t] = np.where(n >= min_obs, m, np.nan)
    return out


def cumpos(r):
    """Cumulative position from returns, restarting (NaN) across gaps."""
    out = np.full_like(r, np.nan); acc = np.full(r.shape[:-1], np.nan)
    for t in range(r.shape[-1]):
        v = r[..., t]; ok = np.isfinite(v)
        acc = np.where(ok, np.where(np.isfinite(acc), acc + v, 0.0), np.nan)
        out[..., t] = acc
    return out


def chain(x):
    """The serial pendulum's links from a position path (last axis = weeks)."""
    E = [ema_path(x, s) for s in SPANS]
    return np.stack([x - E[0], E[0] - E[1], E[1] - E[2], E[2] - E[3]], axis=-1)


def rolling_beta(y, x, win=104, min_obs=52):
    """Rolling OLS slope of y (N,W) on x (W,), past-only, per row."""
    okx = np.isfinite(x)
    out = np.full(y.shape, np.nan)
    ok = np.isfinite(y) & okx[None]
    Y = np.where(ok, y, 0); X = np.where(ok, x[None], 0); n = ok.astype(float)
    cs = lambda a: np.concatenate([np.zeros(a.shape[:-1] + (1,)), np.cumsum(a, axis=-1)], axis=-1)
    Sx, Sy, Sxx, Sxy, Sn = cs(X), cs(Y), cs(X * X), cs(X * Y), cs(n)
    Wn = y.shape[1]
    for t in range(Wn):
        lo = max(0, t - win + 1)
        nn = Sn[:, t + 1] - Sn[:, lo]
        sx = Sx[:, t + 1] - Sx[:, lo]; sy = Sy[:, t + 1] - Sy[:, lo]
        sxx = Sxx[:, t + 1] - Sxx[:, lo]; sxy = Sxy[:, t + 1] - Sxy[:, lo]
        var = sxx - sx * sx / np.maximum(nn, 1)
        out[:, t] = np.where((nn >= min_obs) & (var > 1e-12), (sxy - sx * sy / np.maximum(nn, 1)) / np.maximum(var, 1e-12), np.nan)
    return out


def build(D, liquid_usd=10e6):
    C, V = D['C'], D['V']
    r = logret(C); m = logret(D['spy'][None])[0]
    secs = sorted(set(D['sec'])); w = np.log10(np.maximum(1e6, D['rev']))
    # planets: log-revenue-weighted sector returns; each satellite sees its sector WITHOUT itself
    rs = np.full_like(r, np.nan); planet_r = {}
    for s in secs:
        idx = np.nonzero(D['sec'] == s)[0]
        R = r[idx]; ok = np.isfinite(R); ww = w[idx][:, None] * ok
        tot = np.nansum(np.where(ok, R, 0) * w[idx][:, None], axis=0); den = ww.sum(axis=0)
        planet_r[s] = np.where(ok.sum(0) >= 3, tot / np.maximum(den, 1e-9), np.nan)
        loo_den = den[None] - ww
        rs[idx] = np.where(ok & (loo_den > 0) & (ok.sum(0)[None] >= 4), (tot[None] - np.where(ok, R, 0) * w[idx][:, None]) / np.maximum(loo_den, 1e-9), np.nan)
    sat_r = r - rs                                   # satellite velocity per week (relative to its planet)
    x = cumpos(sat_r)                                # satellite position
    P = np.array([planet_r[s] for s in secs]); y = cumpos(P - m[None])   # planet position relative to the star
    star = cumpos(m[None])[0]
    # dollar volume over the last 13 weeks (liquidity filter at each origin)
    dv = C * V
    dv13 = np.full_like(dv, np.nan)
    cs = np.nancumsum(np.nan_to_num(dv), axis=1); cn = np.cumsum(np.isfinite(dv), axis=1)
    dv13[:, 13:] = (cs[:, 13:] - cs[:, :-13]) / np.maximum(cn[:, 13:] - cn[:, :-13], 1)
    # other bodies: their own weekly returns relative to the star, and each satellite's exposure to them
    body_r = {b: logret(D['bodies'][b][None])[0] - m for b in BODIES if b in D['bodies']}
    beta = {b: rolling_beta(sat_r, br) for b, br in body_r.items()}
    vol13 = np.sqrt(ema_path(m[None] ** 2, 13)[0] * 52)              # star's recent volatility (for the state test)
    return {'r': r, 'sat_r': sat_r, 'x': x, 'links': chain(x), 'secs': secs, 'sidx': np.array([secs.index(s) for s in D['sec']]),
            'y': y, 'plinks': chain(y), 'star': star, 'slinks': chain(star[None])[0], 'm': m, 'body_r': body_r, 'beta': beta,
            'dv13': dv13, 'close': C, 'vol13': vol13}


# ------------------------------------------------------------------ fundamentals anchor (core companies)
def fundamentals(public, D):
    """om, revg, dom relative to the sector, as published: quarter q usable from the end of quarter q+1 (conservative)."""
    import datetime as dt
    d = json.loads((Path(public) / 'rotation-long.json').read_text(encoding='utf-8'))
    F = d['fields']; idx = {k: F.index(k) for k in ('om', 'revg', 'dom')}
    t2i = {t: i for i, t in enumerate(D['tick'])}
    W = len(D['days'])
    out = np.full((len(D['tick']), W, 3), np.nan)
    days = D['days']
    for c in d['companies']:
        i = t2i.get(c['t'])
        if i is None:
            continue
        for row in c['p']:
            cal = row[0]; y_, q = int(cal[2:6]), int(cal[-1])
            q2 = q + 1; y2 = y_ + (q2 > 4); q2 = (q2 - 1) % 4 + 1
            end_m = 3 * q2
            avail = np.datetime64(dt.date(y2 + (end_m == 12), end_m % 12 + 1, 1))
            k = np.searchsorted(days, avail)
            if k >= W:
                continue
            out[i, k:, :] = [np.nan if row[idx[f]] is None else row[idx[f]] for f in ('om', 'revg', 'dom')]
    # relative to the sector: subtract each week's sector median among companies with a value
    for s in set(D['sec']):
        sel = D['sec'] == s
        if sel.sum() < 3:
            continue
        with np.errstate(all='ignore'):
            med = np.nanmedian(out[sel], axis=0)
        out[sel] -= med[None]
    return out


# ------------------------------------------------------------------ the panel at one timescale
def features_at(B, t, h, fund=None, min_price=3.0):
    """The satellites' features at week t for an h-week step, and who is eligible (liquid, priced, with a full pendulum).
    Uses data up to week t only."""
    x, L, PL = B['x'], B['links'], B['plinks']
    v = x[:, t] - x[:, t - h]
    vp = B['y'][:, t] - B['y'][:, t - h]                           # planets' last velocity
    feats = {'v': v}
    for j in range(4):
        feats[f'k{j + 1}'] = L[:, t, j]
    feats['planet_v'] = vp[B['sidx']]
    for j in range(4):
        feats[f'pk{j + 1}'] = PL[B['sidx'], t, j]
    for b, br in B['body_r'].items():
        move = np.nansum(br[t - h + 1:t + 1]) if np.isfinite(br[t - h + 1:t + 1]).sum() >= max(1, h // 2) else np.nan
        feats[f'b_{b}'] = B['beta'][b][:, t] * move
    if fund is not None:
        for j, f in enumerate(('om', 'revg', 'dom')):
            feats[f'f_{f}'] = fund[:, t, j]
    ok = np.isfinite(v) & np.isfinite(L[:, t]).all(-1) & (B['close'][:, t] >= min_price) & (B['dv13'][:, t] >= 10e6)
    return ok, feats


def panel(B, D, h, fund=None, start='2004-01-01', min_price=3.0):
    days = D['days']
    t0 = int(np.searchsorted(days, np.datetime64(start)))
    origins = np.arange(t0 + (t0 % h), len(days) - h, h)
    rows = []
    x = B['x']
    for t in origins:
        tgt = x[:, t + h] - x[:, t]
        ok, feats = features_at(B, t, h, fund, min_price)
        ok = ok & np.isfinite(tgt)
        if ok.sum() < 30:
            continue
        rows.append({'t': t, 'idx': np.nonzero(ok)[0], 'y': tgt[ok], 'raw': tgt[ok], 'X': {k: f[ok] for k, f in feats.items()},
                     'calm': B['vol13'][t] <= np.nanmedian(B['vol13'][:t + 1])})
    return rows


SITE_COLS = ['v', 'k1', 'k2', 'k3', 'k4', 'planet_v', 'pk1', 'pk2', 'pk3', 'pk4']     # M2: the layer that held out of sample


def predict_satellites(B, D, h, weeks, cols=SITE_COLS, ridge=10.0):
    """Walk-forward predictions of the next h-week log return relative to the sector, at any weeks (the latest included,
    whose outcome is unknown). Training: the h-grid panel rows whose outcome had ended by the prediction week.
    Returns {week: (company indices, prediction)}."""
    rows = panel(B, D, h)
    Xs, ys = design(rows, cols)
    tt = [r['t'] for r in rows]
    p = len(cols); G = np.zeros((p, p)); g = np.zeros(p); added = 0; out = {}
    for t in sorted(set(int(w) for w in weeks)):
        while added < len(rows) and tt[added] + h <= t:
            G += Xs[added].T @ Xs[added]; g += Xs[added].T @ ys[added]; added += 1
        if added < 20:
            continue
        b = np.linalg.solve(G + ridge * np.eye(p) * added, g)
        ok, feats = features_at(B, t, h)
        if ok.sum() < 30:
            continue
        X = np.column_stack([zcs(feats[c][ok]) for c in cols])
        out[t] = (np.nonzero(ok)[0], X @ b)
    return out


def predict_planets(B, D, h, weeks, ridge=50.0):
    """Walk-forward predictions of each sector's next h-week log return relative to SPY (its own pendulum and velocity)."""
    y, PL = B['y'], B['plinks']
    def feats(t):
        v = y[:, t] - y[:, t - h]
        X = {'v': v, **{f'k{j + 1}': PL[:, t, j] for j in range(4)}}
        ok = np.isfinite(v) & np.isfinite(PL[:, t]).all(-1)
        return ok, X
    cols = ['v', 'k1', 'k2', 'k3', 'k4']
    rows = []
    for t in range(260, y.shape[1] - h, h):
        ok, X = feats(t); tgt = y[:, t + h] - y[:, t]; ok = ok & np.isfinite(tgt)
        if ok.sum() >= 6:
            rows.append({'t': t, 'y': tgt[ok], 'X': {k: v[ok] for k, v in X.items()}, 'calm': True})
    Xs, ys = design(rows, cols); tt = [r['t'] for r in rows]
    p = len(cols); G = np.zeros((p, p)); g = np.zeros(p); added = 0; out = {}
    for t in sorted(set(int(w) for w in weeks)):
        while added < len(rows) and tt[added] + h <= t:
            G += Xs[added].T @ Xs[added]; g += Xs[added].T @ ys[added]; added += 1
        if added < 20:
            continue
        b = np.linalg.solve(G + ridge * np.eye(p) * added, g)
        ok, X = feats(t)
        if ok.sum() < 6:
            continue
        # the cross-sectional model predicts each sector relative to the average sector; add the planets' mean drift (0)
        Z = np.column_stack([zcs(X[c][ok]) for c in cols])
        out[t] = (np.nonzero(ok)[0], Z @ b)
    return out


def zcs(a):
    """Cross-sectional winsorised z-score (1st-99th percentile); NaN -> 0 (the period mean)."""
    out = np.zeros_like(a, dtype=float); ok = np.isfinite(a)
    if ok.sum() < 5:
        return out
    lo, hi = np.percentile(a[ok], [1, 99]); b = np.clip(a[ok], lo, hi)
    sd = b.std()
    out[ok] = (b - b.mean()) / sd if sd > 0 else 0
    return out


def design(rows, cols, state=False):
    Xs, ys = [], []
    for r in rows:
        X = np.column_stack([zcs(r['X'][c]) for c in cols])
        if state:
            X = np.column_stack([X, X * (0.0 if r['calm'] else 1.0)])
        y = r['y']; lo, hi = np.percentile(y, [1, 99]); y = np.clip(y, lo, hi); y = y - y.mean()
        Xs.append(X); ys.append(y)
    return Xs, ys


def spearman(a, b):
    ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def block_ci(x, block=4, reps=2000, seed=SEED):
    x = np.asarray([v for v in x if np.isfinite(v)]); n = len(x)
    if n < 10:
        return [float('nan')] * 3
    rng = np.random.default_rng(seed); nb = math.ceil(n / block); means = []
    for _ in range(reps):
        st = rng.integers(0, n - block + 1, nb)
        means.append(np.concatenate([x[s:s + block] for s in st])[:n].mean())
    return [float(x.mean()), float(np.quantile(means, .025)), float(np.quantile(means, .975))]


def fama_macbeth(rows, cols, nw_lags=4):
    Xs, ys = design(rows, cols)
    coefs = []
    for X, y in zip(Xs, ys):
        A = np.c_[np.ones(len(y)), X]
        b = np.linalg.lstsq(A, y, rcond=None)[0][1:]
        coefs.append(b)
    Bm = np.array(coefs); T = len(Bm); mu = Bm.mean(0); e = Bm - mu
    S = (e * e).sum(0) / T
    for L in range(1, nw_lags + 1):
        S += 2 * (1 - L / (nw_lags + 1)) * (e[L:] * e[:-L]).sum(0) / T
    se = np.sqrt(S / T)
    return {c: {'coef': float(m_), 't': float(m_ / s_) if s_ > 0 else float('nan')} for c, m_, s_ in zip(cols, mu, se)}


def walk_forward(rows, cols, h, test_from, state=False, ridge=10.0, keep=False):
    """Expanding pooled ridge on standardised features; at origin t only periods whose target ended by t are used."""
    Xs, ys = design(rows, cols, state)
    p = Xs[0].shape[1]
    G = np.zeros((p, p)); g = np.zeros(p); added = 0; out = []
    tt = [r['t'] for r in rows]
    for i, r in enumerate(rows):
        while added < i and tt[added] + h <= r['t']:
            G += Xs[added].T @ Xs[added]; g += Xs[added].T @ ys[added]; added += 1
        if r['t'] < test_from or added < 20:
            continue
        b = np.linalg.solve(G + ridge * np.eye(p) * max(1, added), g)
        pred = Xs[i] @ b
        y = ys[i]; raw = r['raw']
        q = np.quantile(pred, [.1, .9])
        ids = r['idx'] if 'idx' in r else np.arange(len(pred))
        top, bot = set(ids[pred >= q[1]]), set(ids[pred <= q[0]])
        if out and 'top' in out[-1]:                    # one-way turnover of the two legs since the last rebalance
            pt, pb = out[-1]['top'], out[-1]['bot']
            turn = 0.5 * (len(top ^ pt) / max(1, len(top) + len(pt)) * 2 + len(bot ^ pb) / max(1, len(bot) + len(pb)) * 2) / 2
        else:
            turn = 1.0
        out.append({'t': r['t'], 'ic': spearman(pred, y), 'ls': float(raw[pred >= q[1]].mean() - raw[pred <= q[0]].mean()),
                    'top': top, 'bot': bot, 'turn': turn,
                    'sse': float(((y - pred) ** 2).sum()), 'sst': float((y ** 2).sum()), 'n': len(y),
                    **({'pred': pred, 'ids': ids, 'raw': raw, 'b': b} if keep else {})})
    return out


def score(out, h):
    if not out:
        return {}
    ic = [o['ic'] for o in out]; ls = [o['ls'] for o in out]
    r2 = 1 - sum(o['sse'] for o in out) / sum(o['sst'] for o in out)
    per_year = 52 / h
    lsm = np.mean(ls); lss = np.std(ls)
    turn = float(np.mean([o['turn'] for o in out[1:]])) if len(out) > 1 else 1.0
    cost = 2 * 2 * 0.0010 * turn                   # 10 bp per side, both legs, buy and sell
    net = [x - cost for x in ls]
    return {'periods': len(out), 'avg_n': float(np.mean([o['n'] for o in out])), 'ic': block_ci(ic), 'ls_per_period': block_ci(ls),
            'turnover_one_way': turn, 'ls_net_10bp': block_ci(net),
            'ls_annual_sharpe': float(lsm / lss * math.sqrt(per_year)) if lss > 0 else None, 'oos_r2': float(r2),
            'ic_hit': float(np.mean(np.array(ic) > 0))}


# ------------------------------------------------------------------ physics of the fitted M1 equation
def physics(b_v, k, h):
    """Linear dynamics at weekly resolution implied by: next h-week velocity = b_v * last velocity + sum_j k_j link_j (all in
    the same units as the regression in raw, unstandardised form). State: [x - E156, E4 - E156, E13 - E156, E52 - E156, v].
    Returns eigenvalues per period h, damping ratio, period (weeks) and the Lyapunov exponent (per year)."""
    al = [2 / (s + 1) for s in SPANS]
    # one step of h weeks, approximate: positions move by v_next; EMAs move toward x by 1-(1-a)^h
    A = np.zeros((5, 5))
    # v_next = b_v v + k1 (x - E4) + k2 (E4 - E13) + k3 (E13 - E52) + k4 (E52 - E156) ; in deviation coords d0..d3 = (x,E4,E13,E52) - E156
    kv = np.array([k[0], k[1] - k[0], k[2] - k[1], k[3] - k[2]])           # coefficients on d0..d3
    lam = [1 - (1 - a) ** h for a in al]
    A[4, :4] = kv; A[4, 4] = b_v
    # x' = x + v' ; E_j' = E_j + lam_j (x' - E_j); E156' likewise; deviations relative to E156'
    # build in level coordinates then project (translation invariant)
    M = np.zeros((6, 6))     # [x, E4, E13, E52, E156, v]
    dev = np.array([[1, 0, 0, 0, -1, 0], [0, 1, 0, 0, -1, 0], [0, 0, 1, 0, -1, 0], [0, 0, 0, 1, -1, 0]])
    vrow = np.zeros(6); vrow[:5] = kv @ dev[:, :5]; vrow[5] = b_v
    M[5] = vrow
    M[0] = np.eye(6)[0] + vrow
    for j, lj in enumerate(lam):
        e = np.zeros(6); e[1 + j] = 1 - lj; M[1 + j] = e + lj * M[0]
    # project out the common translation: coordinates d = (x,E4,E13,E52)-E156 and v
    Pm = np.zeros((5, 6)); Pm[:4] = dev; Pm[4, 5] = 1
    Lift = np.zeros((6, 5)); Lift[:4, :4] = np.eye(4); Lift[5, 4] = 1        # E156 = 0 representative
    Ad = Pm @ M @ Lift
    ev = np.linalg.eigvals(Ad)
    i = int(np.argmax(np.abs(ev))); lam_max = ev[i]
    out = {'eigs': [complex(e) for e in ev], 'max_abs': float(abs(lam_max)), 'lyapunov_per_year': float(math.log(abs(lam_max)) * 52 / h)}
    osc = [e for e in ev if abs(e.imag) > 1e-6]
    if osc:
        e = max(osc, key=abs); r_ = abs(e); th = abs(np.angle(e))
        out['period_weeks'] = float(2 * math.pi / th * h); out['damping_ratio'] = float(-math.log(r_) / math.hypot(math.log(r_), th))
    return out


def raw_m1(rows, cols=('v', 'k1', 'k2', 'k3', 'k4')):
    """Pooled OLS in raw units (no standardisation), for the physics."""
    X = np.vstack([np.column_stack([r['X'][c] for c in cols]) for r in rows]); y = np.concatenate([r['y'] - r['y'].mean() for r in rows])
    ok = np.isfinite(X).all(1) & np.isfinite(y)
    lo, hi = np.percentile(y[ok], [1, 99])
    b = np.linalg.lstsq(X[ok], np.clip(y[ok], lo, hi), rcond=None)[0]
    return dict(zip(cols, b))


def star_layer(B, D, h, test_from):
    """SPY's next h-week return from its own links, its last velocity and the other bodies' last moves (time series)."""
    days = D['days']; m = B['m']; star = B['star']; SL = B['slinks']
    rows = []
    for t in range(260, len(days) - h, h):
        tgt = star[t + h] - star[t]; v = star[t] - star[t - h]
        f = [v, *SL[t]] + [np.nansum(B['body_r'][b][t - h + 1:t + 1]) for b in B['body_r']]
        if np.isfinite(tgt) and np.isfinite(f).all():
            rows.append((t, f, tgt))
    out = []
    for i, (t, f, y) in enumerate(rows):
        if days[t] < np.datetime64(test_from):
            continue
        past = [(f_, y_) for (t_, f_, y_) in rows if t_ + h <= t]
        if len(past) < 52:
            continue
        X = np.array([p[0] for p in past]); Y = np.array([p[1] for p in past])
        mu, sd = X.mean(0), X.std(0) + 1e-12
        A = np.c_[np.ones(len(X)), (X - mu) / sd]
        b = np.linalg.solve(A.T @ A + 5 * np.eye(A.shape[1]) * (np.arange(A.shape[1]) > 0), A.T @ Y)
        pred = np.r_[1, (np.array(f) - mu) / sd] @ b
        out.append((pred, y, Y.mean()))
    P_ = np.array(out)
    r2 = 1 - ((P_[:, 1] - P_[:, 0]) ** 2).sum() / ((P_[:, 1] - P_[:, 2]) ** 2).sum()   # vs the past mean (Campbell-Thompson)
    hit = float(np.mean(np.sign(P_[:, 0]) == np.sign(P_[:, 1])))
    return {'periods': len(P_), 'oos_r2_vs_mean': float(r2), 'direction_hit': hit, 'share_up': float(np.mean(P_[:, 1] > 0))}


def planet_layer(B, D, h, test_from):
    """Sectors relative to SPY: next velocity from their links and last velocity (11 planets, pooled)."""
    days = D['days']; y = B['y']; PL = B['plinks']
    rows = []
    for t in range(260, len(days) - h, h):
        tgt = y[:, t + h] - y[:, t]; v = y[:, t] - y[:, t - h]
        ok = np.isfinite(tgt) & np.isfinite(v) & np.isfinite(PL[:, t]).all(-1)
        if ok.sum() >= 6:
            rows.append({'t': t, 'idx': np.nonzero(ok)[0], 'y': tgt[ok], 'raw': tgt[ok], 'X': {'v': v[ok], **{f'k{j + 1}': PL[ok, t, j] for j in range(4)}},
                         'calm': True})
    cols = ['v', 'k1', 'k2', 'k3', 'k4']
    out = walk_forward(rows, cols, h, int(np.searchsorted(days, np.datetime64(test_from))), ridge=50.0)
    s = score(out, h)
    s['fama_macbeth'] = fama_macbeth(rows, cols)
    s['physics'] = physics(*(lambda b: (b['v'], [b['k1'], b['k2'], b['k3'], b['k4']]))(raw_m1(rows)), h)
    return s


def run(public, out_dir, test_from='2012-01-01'):
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    D = load(public)
    print('companies on file', len(D['tick']), 'weeks', len(D['days']), flush=True)
    B = build(D)
    fund = fundamentals(public, D)
    core = np.isfinite(fund).any(axis=(1, 2))
    print('core companies with 10-Q anchors', int(core.sum()), flush=True)
    t_test = int(np.searchsorted(D['days'], np.datetime64(test_from)))
    base = ['v']; grav = base + ['k1', 'k2', 'k3', 'k4']; tidal = grav + ['planet_v', 'pk1', 'pk2', 'pk3', 'pk4']
    bodies = tidal + [f'b_{b}' for b in B['body_r']]; anchor = bodies + ['f_om', 'f_revg', 'f_dom']
    models = [('M0 damping', base, False), ('M1 gravity (pendulum links)', grav, False), ('M2 + tidal (planet)', tidal, False),
              ('M3 + other bodies', bodies, False), ('M5 M3 x volatility state', bodies, True)]
    res = {'test_from': test_from, 'universe': {}, 'core': {}, 'fama_macbeth': {}, 'physics': {}, 'star': {}, 'planet': {}}
    for h, name in [(1, 'week'), (4, 'month'), (13, 'quarter')]:
        rows = panel(B, D, h, fund)
        print(f'== {name}: {len(rows)} origins, avg {np.mean([len(r["y"]) for r in rows]):.0f} companies', flush=True)
        res['universe'][name] = {}
        for label, cols, st in models:
            s = score(walk_forward(rows, cols, h, t_test, state=st), h)
            res['universe'][name][label] = s
            print(f'  {label:28s} IC {s["ic"][0]:+.4f} [{s["ic"][1]:+.4f},{s["ic"][2]:+.4f}]  L-S {100 * s["ls_per_period"][0]:+.2f}%  R2 {s["oos_r2"]:+.4f}', flush=True)
        res['fama_macbeth'][name] = fama_macbeth(rows, bodies)
        # core universe with the 10-Q anchor
        crow = []
        for r in rows:
            sel = core[r['idx']]
            if sel.sum() >= 30:
                crow.append({**r, 'idx': r['idx'][sel], 'y': r['y'][sel], 'raw': r['raw'][sel], 'X': {k: v[sel] for k, v in r['X'].items()}})
        res['core'][name] = {}
        for label, cols in [('M3 + other bodies', bodies), ('M4 + 10-Q anchor', anchor)]:
            s = score(walk_forward(crow, cols, h, t_test), h)
            res['core'][name][label] = s
            print(f'  core {label:23s} IC {s["ic"][0]:+.4f} [{s["ic"][1]:+.4f},{s["ic"][2]:+.4f}]  L-S {100 * s["ls_per_period"][0]:+.2f}%', flush=True)
        res['fama_macbeth'][name + '_core_anchor'] = fama_macbeth(crow, anchor)
        b = raw_m1(rows)
        res['physics'][name] = {'raw_coefficients': b, **physics(b['v'], [b['k1'], b['k2'], b['k3'], b['k4']], h)}
        res['star'][name] = star_layer(B, D, h, test_from)
        res['planet'][name] = planet_layer(B, D, h, test_from)
        print('  physics', {k: v for k, v in res['physics'][name].items() if k != 'eigs'}, flush=True)
        print('  star', res['star'][name], flush=True)
    # robustness: both halves of the test period, with costs
    res['halves'] = {}
    for h, name in [(1, 'week'), (4, 'month'), (13, 'quarter')]:
        rows = panel(B, D, h)
        for lo, hi in [('2012-01-01', '2019-01-01'), ('2019-01-01', '2100-01-01')]:
            sub = [r for r in rows if D['days'][r['t']] < np.datetime64(hi)]
            t0 = int(np.searchsorted(D['days'], np.datetime64(lo)))
            for label, cols in [('M1 gravity', grav), ('M2 + tidal', tidal)]:
                res['halves'][f'{name}|{lo[:4]}-{min(int(hi[:4]) - 1, 2026)}|{label}'] = score(walk_forward(sub, cols, h, t0), h)
    (out_dir / 'results.json').write_text(json.dumps(res, indent=1, default=lambda o: str(o) if isinstance(o, complex) else float(o)), encoding='utf-8')
    return res


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--public', default='hist/public')
    ap.add_argument('--out', default='notes/gravity-pendulum')
    ap.add_argument('--test-from', default='2012-01-01')
    a = ap.parse_args()
    run(a.public, a.out, a.test_from)
