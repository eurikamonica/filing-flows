"""Hybrid RRG (Rotation → Hybrid RRG; rotation-history.yml, after the transition model): the RRG blended with the
signals it leaves out, weighted by how well each has ranked the lines that went on to beat SPY — tested walk-forward
against the classic RRG before it is shown, and each closed week's scores frozen in a ledger and scored later.

What the classic RRG does and does not do (measured here; app/transition_rrg.py and app/chaos_forecast.py agree):
  · where a dot moves next is predictable — the EMAs make it so, and the quadrant transition matrices beat staying put;
  · whether the line then beats SPY hardly is: read as a forecast (a ridge on RS-Ratio, RS-Momentum and the last step),
    the classic RRG ranks the next quarter's relative returns with a rank correlation near 0.03 for companies, and the
    blend here, though it ranks better, has not turned that into money after costs (see Scores).

Panels: the sector and style funds of rrg.json (SPDR sectors, QQQ, DIA, MDY, IWM, IJR, RSP, …: real funds only — the
site-sector indices are built from today's companies), and the site's companies while liquid (≥ $3, ≥ $10M a week).

Blocks (each line, each week, from closes and volume up to that week; every input ranked within the week — a z-score
across the panel, clipped at ±3):
  rrg       RS-Ratio and RS-Momentum on 6-, 14- and 26-week windows, and the last weekly step of the 14-week one
  momentum  return against SPY over 52 weeks less the last 4 (Jegadeesh-Titman 12-1), over 13 weeks, over the last 4 and
            over the last week (short-term reversal); volatility against SPY over 26 weeks (the low-volatility anomaly)
  volume    the last complete week's volume against its prior 13 weeks (log; one week back because a file's newest
            weekly bar can carry only its last day's volume), its 4 weeks against the 26 before, the square of the first
            (unusually heavy and unusually light weeks alike) and that week's move × its volume (Campbell, Grossman and
            Wang 1993; Llorente, Michaely, Saar and Wang 2002). The square and the product were added after a study of
            2003–2026 showed both tails of volume trailing (stated: the volume block is not fully out of sample)
Each block is a ridge regression (λ = 30 on the ranked inputs) of the h-week forward log return relative to SPY, less
the panel's average that week (winsorized at 0.5% / 99.5%), refitted every year on the weeks whose outcome was known
by 1 January. The hybrid is the blocks' forecasts weighted by non-negative least squares on their earlier
out-of-sample forecasts (stacking; at least three years of them) — the weights are published, and a block that has not
helped gets none. The classic RRG (14-week x, y and the last step, the same ridge) is fitted alongside as the yardstick.

Per line and horizon (1, 4, 13 weeks): the expected return against SPY (the panel's average of the last five years plus
the hybrid), the chance of beating SPY (from the hybrid's out-of-sample errors in those five years — for companies, the
errors of lines in the same volatility fifth that week) and an 80% range (those errors in units of the line's own
volatility). The Hybrid RRG chart: x = the 13-week forecast, y = the 4-week forecast, each ranked within
the week (100 + z) — the quadrants keep the RRG's names: Leading (both ahead), Weakening (the quarter ahead, the
month not), Lagging, Improving (the month ahead, the quarter not).

Scores, out of sample from 2012 (each year predicted only by fits on earlier years): the weekly rank correlation (IC)
of forecast and outcome with its t over the weeks (overlapping weeks share outcomes: the t uses every h-th week), the
best-minus-worst fifth on non-overlapping holding periods net of trading costs (one way, by weekly dollar volume: 5 bp
above $500M a week, 15 bp above $50M, 40 bp above $5M, else 100 bp; no borrow fee for the sold fifth), deciles, the
Brier skill of the chance of beating SPY against the base rate, and how often the 80% range held. Baskets and the
descriptive tables are in simple returns against SPY (what an equal-weighted basket earns): a mean of log returns
charges volatile lines their volatility as a loss and made the hybrid's spread look several times its real size. Also,
descriptive: what each classic quadrant and each kind of volume week has been followed by.

Survivorship: today's companies only (delisted names are missing; that flatters past losers and so understates
momentum and the low-volatility tilt more than it inflates them). History and models, not investment advice.

  python app/rrg_hybrid.py --public hist/public --ledger hist/ledger/rrg-hybrid.json
"""
import argparse
import datetime as dt
import json
import math
import warnings
from pathlib import Path

import numpy as np

import forecast_book as FB
import transition_rrg as TR

VERSION = 1
HORIZONS = (1, 4, 13)
FIT_FROM = 1998               # the first year of training data
FIRST_OOS = 2004              # the first year forecast (out of sample) — the stacking accumulates from here
TEST_FROM = 2012              # scores are reported from here
EARLY = (2004, 2011)          # the descriptive tables are also shown for these years, before the ones they were found in
STACK_YEARS = 3               # years of out-of-sample block forecasts the stacking needs
RIDGE = 30.0
WINSOR = (0.005, 0.995)
FIFTH = 0.2
COST_TIERS = ((500e6, 5.0), (50e6, 15.0), (5e6, 40.0), (0.0, 100.0))   # weekly dollar volume → one-way cost (bp)
SPIKE, QUIET = math.log(2.0), math.log(0.6)
VOLUME_LAG = 1                # the volume inputs use the last complete week before the one forecast from: a file's
                              # newest weekly bar can hold only its last day's volume (Yahoo's extra bar of the week)
TARGET = "log"                # what the blocks are fitted to: the h-week log return vs SPY. "simple" (the return itself,
                              # winsorized) was tried: companies' 13-week rank correlation fell to 0.020 from 0.065 and
                              # the best − worst basket did no better (+0.69% a quarter before costs against +0.82%)
CAL_YEARS = 5                 # the level, the base rate and the error distributions come from the last 5 years …
CAL_GROUPS = {'companies': 5, 'funds': 1}   # … companies' errors kept apart by volatility fifth (within each week).
                              # Chosen on 2007–2011, before the scored years, among since 1998 / 10 / 5 years × pooled /
                              # by fifth: by fifth, companies' 80% ranges held 80% in every fifth (pooled: 75% in the
                              # calmest, 85% in the wildest); funds (29 lines) did better pooled
TAIL_WEEKS = 8
LEDGER_MAX_LINES = 800        # the ledger freezes every fund and the 800 companies with the most dollar volume that week
TOP_ROWS = 25                 # companies in the main file (best and worst by the 13-week forecast); the rest in their own file
BLOCKS = {'rrg': ['x14', 'y14', 'dx14', 'dy14', 'x6', 'y6', 'x26', 'y26'],
          'momentum': ['mom12_1', 'mom13', 'rev4', 'rev1', 'vol26'],
          'volume': ['vz1', 'vz4', 'vz1sq', 'rev1_vz1']}
CLASSIC = ['x14', 'y14', 'dx14', 'dy14']
BLOCK_NAMES = {'rrg': 'RRG geometry (6, 14 and 26 weeks)', 'momentum': 'Momentum, reversal and volatility', 'volume': 'Volume anomalies'}
FEATURE_NAMES = {'x14': 'RS-Ratio, 14 weeks', 'y14': 'RS-Momentum, 14 weeks', 'dx14': 'Last step of RS-Ratio', 'dy14': 'Last step of RS-Momentum',
                 'x6': 'RS-Ratio, 6 weeks', 'y6': 'RS-Momentum, 6 weeks', 'x26': 'RS-Ratio, 26 weeks', 'y26': 'RS-Momentum, 26 weeks',
                 'mom12_1': 'vs SPY, 52 weeks less the last 4', 'mom13': 'vs SPY, 13 weeks', 'rev4': 'vs SPY, last 4 weeks', 'rev1': 'vs SPY, last week',
                 'vol26': 'Volatility vs SPY, 26 weeks', 'vz1': 'Volume last full week vs its prior 13', 'vz4': 'Volume, 4 weeks vs the 26 before',
                 'vz1sq': 'Unusual volume either way (square)', 'rev1_vz1': 'Last week\'s move × its volume'}
QUADS = ('Leading', 'Weakening', 'Lagging', 'Improving')


def fin(v):
    return v is not None and isinstance(v, (int, float, np.floating)) and math.isfinite(v)


def r_(v, d=4):
    return round(float(v), d) if fin(v) else None


def years_of(days):
    return np.array([int(str(d)[:4]) for d in days])


# ------------------------------------------------------------------ data
def load(public):
    """{'days', 'spy', panels: {'funds': {...}, 'companies': {...}}} — closes, volume (shares), names."""
    L = TR.load(public)
    days, spy = L['days'], L['spy']
    D = json.loads((Path(public) / 'rrg.json').read_text(encoding='utf-8'))
    g0, W = days[0], len(days)

    def place(start, arr, scale=1.0):
        a = np.full(W, np.nan)
        o = int((np.datetime64(start) - g0).astype(int) // 7)
        v = np.array([np.nan if x is None else x * scale for x in arr], float)
        if o < W:
            a[max(0, o):o + len(v)] = v[max(0, -o):W - o]
        return a
    funds = [s for s in D.get('series') or [] if s.get('group') in ('sector-etf', 'style-etf')]
    FC = np.array([place(s['start'], s['c']) for s in funds]) if funds else np.zeros((0, W))
    FV = np.array([place(s['start'], s.get('v') or [None] * len(s['c']), 1000.0) for s in funds]) if funds else np.zeros((0, W))
    tick = D.get('tickers') or {}
    panels = {'funds': {'ids': [s['id'] for s in funds], 'names': {s['id']: s.get('name') or s['id'] for s in funds},
                        'groups': {s['id']: s.get('group') for s in funds}, 'C': FC, 'V': FV, 'liq': np.isfinite(FC)},
              'companies': {'ids': L['cos'], 'names': {t: (tick.get(t) or {}).get('n') or t for t in L['cos']},
                            'groups': {t: (tick.get(t) or {}).get('s') for t in L['cos']}, 'C': L['C'], 'V': L['V'],
                            'liq': TR.liquid(L['C'], L['V'])}}
    return {'days': days, 'spy': spy, 'panels': panels}


def log_ret(C):
    r = np.full(C.shape, np.nan)
    with np.errstate(divide='ignore', invalid='ignore'):
        r[:, 1:] = np.log(C[:, 1:] / C[:, :-1])
    return r


def back_sum(x, k, skip=0):
    """Σ x[t − skip − k + 1 … t − skip] per row (NaN when any is missing)."""
    L, W = x.shape
    cs = np.concatenate([np.zeros((L, 1)), np.cumsum(np.where(np.isfinite(x), x, 0.0), 1)], 1)
    bad = np.concatenate([np.zeros((L, 1), int), np.cumsum(~np.isfinite(x), 1)], 1)
    out = np.full((L, W), np.nan)
    t = np.arange(k + skip - 1, W)
    hi, lo = t - skip + 1, t - skip - k + 1
    ok = bad[:, hi] - bad[:, lo] == 0
    out[:, t] = np.where(ok, cs[:, hi] - cs[:, lo], np.nan)
    return out


def fwd_sum(x, h):
    """Σ x[t + 1 … t + h] per row (NaN when any is missing or past the end)."""
    L, W = x.shape
    cs = np.concatenate([np.zeros((L, 1)), np.cumsum(np.where(np.isfinite(x), x, 0.0), 1)], 1)
    bad = np.concatenate([np.zeros((L, 1), int), np.cumsum(~np.isfinite(x), 1)], 1)
    out = np.full((L, W), np.nan)
    t = np.arange(max(0, W - h))
    ok = bad[:, t + h + 1] - bad[:, t + 1] == 0
    out[:, t] = np.where(ok, cs[:, t + h + 1] - cs[:, t + 1], np.nan)
    return out


def quad(x, y):
    q = np.where(x >= 100, np.where(y >= 100, 0, 1), np.where(y >= 100, 3, 2))
    return np.where(np.isfinite(x) & np.isfinite(y), q, -1)


def xs_z(A, ok):
    """Within each week (column), the z-score across the panel's usable lines, clipped at ±3 (float32)."""
    B = np.where(ok, A, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        m = np.nanmean(B, 0, keepdims=True)
        s = np.nanstd(B, 0, keepdims=True)
    with np.errstate(invalid='ignore', divide='ignore'):
        Z = (B - m) / np.where(s > 1e-12, s, np.nan)
    return np.clip(Z, -3, 3).astype(np.float32)


def features(C, V, spy, liq):
    """The raw signals and the ranked (z-scored) inputs of every block, the weekly relative move and the costs."""
    RS = np.where((spy[None] > 0) & np.isfinite(C), 100 * C / spy[None], np.nan)
    raw = {}
    for n in (6, 14, 26):
        S = TR.rrg_states(RS, n)
        raw[f'x{n}'], raw[f'y{n}'] = S['x'], S['y']
    dx = np.full(RS.shape, np.nan); dy = np.full(RS.shape, np.nan)
    dx[:, 1:] = raw['x14'][:, 1:] - raw['x14'][:, :-1]
    dy[:, 1:] = raw['y14'][:, 1:] - raw['y14'][:, :-1]
    raw['dx14'], raw['dy14'] = dx, dy
    rel = log_ret(C) - log_ret(spy[None])
    raw['mom12_1'] = back_sum(rel, 48, 4)
    raw['mom13'] = back_sum(rel, 13)
    raw['rev4'] = back_sum(rel, 4)
    raw['rev1'] = rel
    with np.errstate(invalid='ignore'):
        raw['vol26'] = np.sqrt(back_sum(rel * rel, 26) / 26)
    with np.errstate(divide='ignore', invalid='ignore'):
        lv = np.log(np.where(V > 0, V, np.nan))
    lag = VOLUME_LAG
    if lag:
        lv = np.concatenate([np.full((lv.shape[0], lag), np.nan), lv[:, :-lag]], 1)
    moved = rel if not lag else np.concatenate([np.full((rel.shape[0], lag), np.nan), rel[:, :-lag]], 1)
    raw['move_vw'] = moved                                            # the relative move of that same (volume) week
    raw['vz1'] = lv - back_sum(lv, 13, 1) / 13                       # the volume week against its prior 13 (log)
    raw['vz4'] = back_sum(lv, 4) / 4 - back_sum(lv, 26, 4) / 26      # its 4 weeks against the 26 before
    raw['vz1sq'] = raw['vz1'] ** 2
    ok = liq & np.isfinite(RS)
    Z = {k: xs_z(raw[k], ok) for k in raw if k not in ('rev1_vz1', 'move_vw')}
    Z['rev1_vz1'] = xs_z(xs_z(moved, ok).astype(float) * Z['vz1'].astype(float), ok)   # that week's move × its volume
    dv = C * V
    with np.errstate(invalid='ignore'):
        dv13 = back_sum(np.where(np.isfinite(dv), dv, np.nan), 13) / 13
    cost = np.full(C.shape, COST_TIERS[-1][1] / 1e4)
    for lim, bp in reversed(COST_TIERS):
        cost = np.where(np.isfinite(dv13) & (dv13 >= lim), bp / 1e4, cost)
    return {'raw': raw, 'Z': Z, 'rel': rel, 'ok': ok, 'cost': cost.astype(np.float32), 'q': quad(raw['x14'], raw['y14'])}


# ------------------------------------------------------------------ fitting
def ridge(X, y, lam=RIDGE):
    mu, sd = X.mean(0), X.std(0)
    sd = np.where(sd > 1e-12, sd, 1.0)
    Zx = (X - mu) / sd
    b = np.linalg.solve(Zx.T @ Zx + lam * np.eye(Zx.shape[1]), Zx.T @ (y - y.mean()))
    return {'mu': mu, 'sd': sd, 'b': b, 'a': float(y.mean())}


def ridge_predict(m, X):
    return m['a'] + ((X - m['mu']) / m['sd']) @ m['b']


def nnls(A, y):
    """Non-negative least squares without an intercept (active set: drop the most negative weight until none is)."""
    keep = list(range(A.shape[1]))
    w = np.zeros(A.shape[1])
    while keep:
        sol, *_ = np.linalg.lstsq(A[:, keep], y, rcond=None)
        if (sol >= 0).all():
            w[keep] = sol
            return w
        keep.pop(int(np.argmin(sol)))
    return w


def known_before(days, h, year):
    """Weeks whose h-week outcome was known before 1 January of `year`."""
    W = len(days)
    e = np.minimum(np.arange(W) + h, W - 1)
    return (np.arange(W) + h < W) & (days[e] < np.datetime64(f'{year}-01-01'))


def vol_groups(vol, ok, n):
    """Each line's volatility group within its week (0 = the calmest … n − 1), −1 where it has no volatility yet."""
    g = np.full(vol.shape, -1, np.int8)
    for t in range(vol.shape[1]):
        c = ok[:, t] & np.isfinite(vol[:, t])
        k = int(c.sum())
        if not k:
            continue
        r = np.argsort(np.argsort(vol[c, t], kind='stable'), kind='stable')
        g[c, t] = (r * max(n, 1) // k).astype(np.int8)
    return g


def demean(Y, ok):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        m = np.nanmean(np.where(ok & np.isfinite(Y), Y, np.nan), 0, keepdims=True)
    return Y - m


def walk_forward(days, Fe, h, groups=1):
    """Every block and the classic RRG, refitted yearly; then the stacked hybrid and its probabilities and ranges (their
    errors kept apart in `groups` volatility groups)."""
    groups = max(int(groups or 1), 1)
    Z, ok, rel = Fe['Z'], Fe['ok'], Fe['rel']
    yrs = years_of(days)
    Yraw = fwd_sum(rel, h)
    Ydm = demean(Yraw if TARGET == "log" else np.expm1(Yraw), ok)
    L, W = Yraw.shape
    sets = dict(BLOCKS, classic=CLASSIC)
    Xs = {b: np.stack([Z[k] for k in cols], 2) for b, cols in sets.items()}          # L × W × k (float32)
    core = ok & np.all([np.isfinite(Xs[b]).all(2) for b in sets], 0)
    F = {b: np.full((L, W), np.nan, np.float32) for b in sets}
    coefs, last = {}, int(yrs[-1])
    for Y in range(FIRST_OOS, last + 1):
        tr = core & np.isfinite(Ydm) & known_before(days, h, Y)[None] & (yrs >= FIT_FROM)[None]
        if tr.sum() < 2000:
            continue
        y = Ydm[tr]
        lo, hi = np.quantile(y, WINSOR)
        y = np.clip(y, lo, hi)
        te = core & (yrs == Y)[None]
        for b in sets:
            m = ridge(Xs[b][tr].astype(float), y)
            F[b][te] = ridge_predict(m, Xs[b][te].astype(float))
            if Y == last:
                coefs[b] = {k: r_(c / s, 6) for k, c, s in zip(sets[b], m['b'], m['sd'])}
    # stacking: non-negative weights on the blocks' earlier out-of-sample forecasts
    names = list(BLOCKS)
    S = np.full((L, W), np.nan, np.float32)
    weights, mu_by, base_by, res_by, z_by = {}, {}, {}, {}, {}
    vol = Fe['raw']['vol26']
    grp = vol_groups(vol, ok, groups)
    since = (lambda Y: (yrs >= Y - CAL_YEARS)[None]) if CAL_YEARS else (lambda Y: np.ones((1, W), bool))
    for Y in range(FIRST_OOS, last + 1):
        te = core & (yrs == Y)[None] & np.all([np.isfinite(F[b]) for b in names], 0)
        prev = core & np.isfinite(Ydm) & known_before(days, h, Y)[None] & (yrs >= FIRST_OOS)[None] & np.all([np.isfinite(F[b]) for b in names], 0)
        enough = len(set(yrs[prev.any(0)].tolist())) >= STACK_YEARS
        if enough:
            A = np.stack([F[b][prev] for b in names], 1).astype(float)
            y = Ydm[prev]
            lo, hi = np.quantile(y, WINSOR)
            w = nnls(A, np.clip(y, lo, hi))
        else:
            w = np.zeros(len(names))
        weights[Y] = w
        S[te] = np.stack([F[b][te] for b in names], 1) @ w
        # calibration — the level (the panel's average relative return), the base rate and the errors of the published
        # forecast — from the last CAL_YEARS years of known outcomes, the errors kept by volatility group
        known = ok & np.isfinite(Yraw) & known_before(days, h, Y)[None] & (yrs >= FIT_FROM)[None]
        trn = known & since(Y)
        if trn.sum() < 2000:
            trn = known
        if trn.sum() < 2000:
            continue
        mu_by[Y] = float(np.mean(Yraw[trn]))
        base_by[Y] = float(np.mean(Yraw[trn] > 0))
        pv = prev & since(Y) if enough else None
        if enough and pv.sum() < 2000:
            pv = prev
        if enough:
            Sp = np.stack([F[b][pv] for b in names], 1).astype(float) @ w
            e = Yraw[pv] - mu_by[Y] - Sp
            v, g = vol[pv] * math.sqrt(h), grp[pv]
        else:
            e = Yraw[trn] - mu_by[Y]
            v, g = vol[trn] * math.sqrt(h), grp[trn]
        # (the expected return stays the panel's level plus the hybrid: adding each group's own level as well ranked worse —
        # companies' 13-week rank correlation 0.051 against 0.065 — so the group's level shows only in its errors)
        z = e / np.where(v > 1e-6, v, np.nan)
        rng = np.random.default_rng(Y)
        res_by[Y], z_by[Y] = {}, {}
        for k in [-1] + list(range(groups)):              # −1: every line together (and lines with no volatility yet)
            idx = np.flatnonzero(g == k) if k >= 0 else np.arange(len(e))
            if len(idx) < 500:
                continue
            pick = rng.choice(idx, min(len(idx), 40000), replace=False)
            res_by[Y][k] = np.sort(e[pick])
            zz = z[pick][np.isfinite(z[pick])]
            z_by[Y][k] = np.quantile(zz, [0.1, 0.9]) if len(zz) > 100 else np.array([-1.2816, 1.2816])
    E = np.full((L, W), np.nan, np.float32)
    P = np.full((L, W), np.nan, np.float32)
    P0 = np.full((L, W), np.nan, np.float32)
    LO = np.full((L, W), np.nan, np.float32)
    HI = np.full((L, W), np.nan, np.float32)
    for Y in res_by:
        te = np.isfinite(S) & (yrs == Y)[None]
        if not te.any() or -1 not in res_by[Y]:
            continue
        e_s = mu_by[Y] + S[te].astype(float)
        E[te] = e_s
        P0[te] = base_by[Y]
        v = vol[te] * math.sqrt(h)
        g = grp[te]
        own = np.isin(g, [k for k in res_by[Y] if k >= 0])
        p, lo_, hi_ = (np.full(len(e_s), np.nan) for _ in range(3))
        for k in res_by[Y]:
            sel = (g == k) if k >= 0 else ~own
            if not sel.any():
                continue
            r = res_by[Y][k]
            p[sel] = 1 - np.searchsorted(r, -e_s[sel]) / len(r)
            lo_[sel] = e_s[sel] + z_by[Y][k][0] * v[sel]
            hi_[sel] = e_s[sel] + z_by[Y][k][1] * v[sel]
        P[te], LO[te], HI[te] = p, lo_, hi_
    return {'F': F, 'S': S, 'E': E, 'P': P, 'P0': P0, 'LO': LO, 'HI': HI, 'Yraw': Yraw, 'Ydm': Ydm, 'core': core,
            'weights': {int(k): [r_(x) for x in v] for k, v in weights.items()}, 'coefs': coefs}


# ------------------------------------------------------------------ scores
def weekly_ic(Fc, Y, ok, weeks):
    out = []
    for t in weeks:
        m = ok[:, t] & np.isfinite(Fc[:, t]) & np.isfinite(Y[:, t])
        if m.sum() < 8:
            continue
        a, b = Fc[m, t], Y[m, t]
        if np.ptp(a) == 0:
            continue
        ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
        out.append(float(np.corrcoef(ra, rb)[0, 1]))
    return np.array(out)


def ic_stats(ic):
    if len(ic) < 10:
        return None
    return {'ic': r_(ic.mean()), 't': r_(ic.mean() / (ic.std(ddof=1) / math.sqrt(len(ic))), 2), 'pos': r_((ic > 0).mean(), 3), 'weeks': int(len(ic))}


def evaluate(days, Fe, R, h, panel):
    """Out-of-sample scores from TEST_FROM: ICs (hybrid, each block, classic, raw 12-1 momentum), the best-minus-worst
    fifth net of costs, the top fifth against SPY, deciles, Brier skill, range coverage, IC by year."""
    yrs = years_of(days)
    ok = Fe['ok'] & R['core']
    Yraw, Ydm, S = R['Yraw'], R['Ydm'], R['S']
    test = np.where(yrs >= TEST_FROM)[0]
    every = test[::h]                                    # non-overlapping origins
    out = {'h': h}
    sig = {'hybrid': S, **{b: R['F'][b] for b in BLOCKS}, 'classic': R['F']['classic'], 'momentum_12_1': Fe['raw']['mom12_1']}
    out['ic'] = {k: ic_stats(weekly_ic(v, Ydm, ok, every)) for k, v in sig.items()}
    # by year (hybrid and classic), every week (overlapping) for a steadier yearly figure
    by_year = {}
    for Y in range(TEST_FROM, int(yrs[-1]) + 1):
        wk = np.where(yrs == Y)[0]
        a, b = weekly_ic(S, Ydm, ok, wk), weekly_ic(R['F']['classic'], Ydm, ok, wk)
        if len(a) >= 10:
            by_year[str(Y)] = [r_(a.mean(), 3), r_(b.mean(), 3) if len(b) else None]
    out['ic_by_year'] = by_year
    # portfolios on non-overlapping origins, in simple returns against SPY — what an equal-weighted basket earns (the
    # mean log return would charge the wild lines their volatility as if it were a loss: in log terms the best − worst
    # fifth looked like +4.9% a quarter for companies; in money it was about nothing after costs)
    ls, ls_gross, top, ls_classic, hits, top_hit, vn = [], [], [], [], [], [], []
    deciles = [[] for _ in range(10)]
    cost = Fe['cost']
    vg = vol_groups(Fe['raw']['vol26'], Fe['ok'], 5) if panel != 'funds' else None
    for t in every:
        m = ok[:, t] & np.isfinite(S[:, t]) & np.isfinite(Yraw[:, t])
        if m.sum() < (10 if panel == 'funds' else 50):
            continue
        s, y, c = S[m, t], np.expm1(Yraw[m, t].astype(float)), cost[m, t]
        if np.ptp(s) == 0:
            continue
        q = np.quantile(s, [FIFTH, 1 - FIFTH])
        hi_, lo_ = s >= q[1], s <= q[0]
        if not hi_.any() or not lo_.any():
            continue
        net = (y[hi_].mean() - 2 * c[hi_].mean()) - (y[lo_].mean() + 2 * c[lo_].mean())
        ls.append(net)
        ls_gross.append(y[hi_].mean() - y[lo_].mean())
        if vg is not None:                               # the same, within each volatility fifth (volatility-neutral)
            g, parts = vg[m, t], []
            for k in range(5):
                gk = g == k
                if gk.sum() >= 25 and np.ptp(s[gk]) > 0:
                    qk = np.quantile(s[gk], [FIFTH, 1 - FIFTH])
                    a_, b_ = gk & (s >= qk[1]), gk & (s <= qk[0])
                    parts.append((y[a_].mean() - 2 * c[a_].mean()) - (y[b_].mean() + 2 * c[b_].mean()))
            if parts:
                vn.append(float(np.mean(parts)))
        top.append(y[hi_].mean() - 2 * c[hi_].mean())
        top_hit.append(float((y[hi_] > 0).mean()))
        hits.append(net > 0)
        sc = R['F']['classic'][m, t]
        if np.ptp(sc) > 0:
            qc = np.quantile(sc, [FIFTH, 1 - FIFTH])
            ls_classic.append((y[sc >= qc[1]].mean() - 2 * c[sc >= qc[1]].mean()) - (y[sc <= qc[0]].mean() + 2 * c[sc <= qc[0]].mean()))
        ranks = np.argsort(np.argsort(s)) / max(1, len(s) - 1)
        d = np.minimum((ranks * 10).astype(int), 9)
        for k in range(10):
            if (d == k).any():
                deciles[k].append((float(y[d == k].mean()), float((y[d == k] > 0).mean())))
    per_year = 52 / h

    def spread(xs):
        xs = np.array(xs)
        if len(xs) < 8:
            return None
        return {'mean': r_(xs.mean()), 't': r_(xs.mean() / (xs.std(ddof=1) / math.sqrt(len(xs))), 2), 'per_year': r_(xs.mean() * per_year),
                'hit': r_((xs > 0).mean(), 3), 'worst': r_(xs.min()), 'periods': int(len(xs))}
    out['best_minus_worst'] = spread(ls)
    if out['best_minus_worst'] and ls_gross:
        out['best_minus_worst']['gross'] = r_(np.mean(ls_gross))           # before trading costs
    out['best_minus_worst_vol_neutral'] = spread(vn) if vn else None
    out['best_minus_worst_classic'] = spread(ls_classic)
    out['top_fifth_vs_spy'] = spread(top)
    if top_hit:
        out['top_fifth_vs_spy']['share_beating'] = r_(np.mean(top_hit), 3)
    out['deciles'] = [{'decile': k + 1, 'rel': r_(np.mean([a for a, _ in d])), 'beat': r_(np.mean([b for _, b in d]), 3), 'periods': len(d)}
                      for k, d in enumerate(deciles) if d]
    # chance of beating SPY, against the base rate (every week from TEST_FROM)
    mk = ok & np.isfinite(R['P']) & np.isfinite(Yraw) & (yrs >= TEST_FROM)[None]
    yb = (Yraw[mk] > 0).astype(float)
    b1 = float(((R['P'][mk] - yb) ** 2).mean()) if mk.any() else None
    b0 = float(((R['P0'][mk] - yb) ** 2).mean()) if mk.any() else None
    out['beat_spy'] = {'brier_skill': r_(1 - b1 / b0) if b0 else None, 'n': int(mk.sum()), 'base_rate': r_(yb.mean(), 3) if mk.any() else None,
                       'bias': r_(float(R['P'][mk].mean() - yb.mean()), 3) if mk.any() else None}   # mean forecast − the share that did
    bins = []
    pv = R['P'][mk]
    for lo_ in np.arange(0, 1, 0.1):
        sel = (pv >= lo_) & (pv < lo_ + 0.1)
        if sel.sum() >= 200:
            bins.append([r_(lo_, 1), r_(pv[sel].mean(), 3), r_(yb[sel].mean(), 3), int(sel.sum())])
    out['beat_spy']['calibration'] = bins
    mr = ok & np.isfinite(R['LO']) & np.isfinite(Yraw) & (yrs >= TEST_FROM)[None]
    out['range80'] = r_(((Yraw[mr] >= R['LO'][mr]) & (Yraw[mr] <= R['HI'][mr])).mean(), 3) if mr.any() else None
    fifth = vol_groups(Fe['raw']['vol26'], Fe['ok'], 5)[mr]                # … and by volatility fifth, calmest first
    held = (Yraw[mr] >= R['LO'][mr]) & (Yraw[mr] <= R['HI'][mr])
    out['range80_by_vol'] = [r_(held[fifth == k].mean(), 3) if (fifth == k).sum() >= 200 else None for k in range(5)]
    out['weights_by_year'] = {str(k): v for k, v in R['weights'].items() if k >= TEST_FROM - 1}
    return out


def describe(days, Fe, panel):
    """Descriptive, from TEST_FROM: the average return against the panel that followed each classic quadrant and each
    kind of volume week (the group's mean less the panel's that week, averaged over non-overlapping weeks, with t)."""
    yrs = years_of(days)
    ok, rel, q = Fe['ok'], Fe['rel'], Fe['q']
    vz1, r1 = Fe['raw']['vz1'], Fe['raw']['move_vw']           # the volume week and its own move (VOLUME_LAG)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        lo = np.nanquantile(np.where(ok, r1, np.nan), 1 / 3, axis=0)
        hi = np.nanquantile(np.where(ok, r1, np.nan), 2 / 3, axis=0)
    up, down = r1 >= hi[None], r1 <= lo[None]
    spike, quiet = vz1 >= SPIKE, vz1 <= QUIET
    base = ok & np.isfinite(vz1) & np.isfinite(r1)
    groups = [('quadrant', n, base & (q == k)) for k, n in enumerate(QUADS)]
    groups += [('volume', 'Volume ≥ 2× its 13-week average', base & spike), ('volume', 'Up week on ≥ 2× volume', base & up & spike),
               ('volume', 'Down week on ≥ 2× volume', base & down & spike), ('volume', 'Volume ≤ 0.6× its 13-week average', base & quiet),
               ('volume', 'Ordinary volume (between)', base & ~spike & ~quiet)]
    groups += [('quadrant_volume', f'{n} on ≥ 2× volume', base & (q == k) & spike) for k, n in enumerate(QUADS)]
    out = []
    min_n = 3 if panel == 'funds' else 20
    for h in HORIZONS:
        Yd = demean(np.expm1(fwd_sum(rel, h)), ok)              # simple returns, as a basket earns them
        weeks = np.where(yrs >= TEST_FROM)[0][::h]
        early = np.where((yrs >= EARLY[0]) & (yrs <= EARLY[1]))[0][::h]   # the years before, where nobody looked

        def series(G, ws):
            vals = []
            for t in ws:
                m = G[:, t] & np.isfinite(Yd[:, t])
                if m.sum() >= min_n:
                    vals.append(float(Yd[m, t].mean()))
            return np.array(vals)
        for kind, name, G in groups:
            v = series(G, weeks)
            if len(v) >= 10:
                row = {'kind': kind, 'group': name, 'h': h, 'rel': r_(v.mean()), 't': r_(v.mean() / (v.std(ddof=1) / math.sqrt(len(v))), 2),
                       'beat_share': r_((v > 0).mean(), 3), 'weeks': len(v), 'share_of_weeks': r_(np.mean(G[base]), 4) if base.any() else None}
                ve = series(G, early)
                if len(ve) >= 8:
                    row['early'] = {'rel': r_(ve.mean()), 't': r_(ve.mean() / (ve.std(ddof=1) / math.sqrt(len(ve))), 2), 'weeks': len(ve)}
                out.append(row)
    return out


# ------------------------------------------------------------------ now
def closed_week(days, today):
    lim = np.datetime64(today) - np.timedelta64(1, 'D')
    return max(int(np.searchsorted(days, lim, side='right') - 1), 0)


def hybrid_xy(R13, R4, ok, t):
    """The Hybrid RRG coordinates at week t: 100 + the 13-week (x) and 4-week (y) forecasts ranked within the week."""
    def z(S):
        m = ok[:, t] & np.isfinite(S[:, t])
        out = np.full(S.shape[0], np.nan)
        if m.sum() >= 3 and np.ptp(S[m, t]) > 0:
            v = S[m, t].astype(float)
            out[m] = np.clip(100 + (v - v.mean()) / v.std(), 96, 104)
        return out
    return z(R13['S']), z(R4['S'])


def current_rows(days, P, Fe, Rs, t, spy, panel):
    ids, C = P['ids'], P['C']
    ok = Fe['ok']
    xh, yh = hybrid_xy(Rs[13], Rs[4], ok, t)
    rows = []
    drift = spy_drift(spy, t)
    for i, k in enumerate(ids):
        if not (ok[i, t] and np.isfinite(Rs[13]['S'][i, t])):
            continue
        row = {'id': k, 'name': P['names'].get(k, k), 'group': P['groups'].get(k), 'close': r_(C[i, t], 4),
               'classic': [r_(Fe['raw']['x14'][i, t], 2), r_(Fe['raw']['y14'][i, t], 2)], 'hybrid': [r_(xh[i], 2), r_(yh[i], 2)],
               'volume_x': r_(math.exp(Fe['raw']['vz1'][i, t]), 2) if fin(Fe['raw']['vz1'][i, t]) else None,
               'cost_bp': r_(Fe['cost'][i, t] * 1e4, 0)}
        for h in HORIZONS:
            R = Rs[h]
            e = R['E'][i, t]
            row[f'h{h}'] = {'rel': r_(e), 'p': r_(R['P'][i, t], 3), 'lo': r_(R['LO'][i, t]), 'hi': r_(R['HI'][i, t]),
                            'price': r_(C[i, t] * math.exp(e + drift * h), 2) if fin(e) and fin(C[i, t]) else None,
                            'price_lo': r_(C[i, t] * math.exp(R['LO'][i, t] + drift * h), 2) if fin(R['LO'][i, t]) and fin(C[i, t]) else None,
                            'price_hi': r_(C[i, t] * math.exp(R['HI'][i, t] + drift * h), 2) if fin(R['HI'][i, t]) and fin(C[i, t]) else None}
        w = Rs[13]['weights'].get(int(str(days[t])[:4])) or [0, 0, 0]
        row['mix13'] = {b: r_(wb * float(Rs[13]['F'][b][i, t]), 5) if np.isfinite(Rs[13]['F'][b][i, t]) else None for b, wb in zip(BLOCKS, w)}
        if panel == 'funds':
            lo = max(0, t - TAIL_WEEKS)
            tx, ty = [], []
            for s in range(lo, t + 1):
                a, b = hybrid_xy(Rs[13], Rs[4], ok, s)
                tx.append(r_(a[i], 2)); ty.append(r_(b[i], 2))
            row['tail'] = {'hybrid': [tx, ty], 'classic': [[r_(v, 2) for v in Fe['raw']['x14'][i, lo:t + 1]], [r_(v, 2) for v in Fe['raw']['y14'][i, lo:t + 1]]]}
        rows.append(row)
    return rows


def spy_drift(spy, t, weeks=520):
    """SPY's average weekly log return over the last ten years to week t (the price targets add it to the relative
    forecast; the market's own direction is not forecast here — see Market models)."""
    s = spy[max(0, t - weeks):t + 1]
    s = s[np.isfinite(s)]
    return float(np.log(s[-1] / s[0]) / (len(s) - 1)) if len(s) > 52 else 0.0


# ------------------------------------------------------------------ ledger
def ledger_update(book, days, t, panels_out):
    """Freeze this closed week's scores (one entry per panel and horizon, the lines as arrays); resolve every frozen
    week whose horizon has passed with the relative returns that followed."""
    asof = str(days[t])
    for panel, (P, Fe, Rs) in panels_out.items():
        ok = Fe['ok']
        for h in HORIZONS:
            R = Rs[h]
            m = ok[:, t] & np.isfinite(R['S'][:, t])
            if not m.any():
                continue
            if m.sum() > LEDGER_MAX_LINES:                    # the most traded lines that week (13-week dollar volume)
                dv = np.where(m, P['C'][:, t] * np.nan_to_num(P['V'][:, max(0, t - 12):t + 1]).mean(1), -np.inf)
                m = np.zeros_like(m)
                m[np.argsort(dv)[-LEDGER_MAX_LINES:]] = True
            ids = [P['ids'][i] for i in np.where(m)[0]]
            FB.freeze(book, f'{panel}:{h}', asof, asof, {'ids': ids, 's': [r_(v, 5) for v in R['S'][m, t]],
                                                         'p': [r_(v, 3) for v in R['P'][m, t]], 'base': r_(np.nanmean(R['P0'][m, t]), 3)},
                      meta={'model': f'rrg_hybrid v{VERSION}', 'weights': R['weights'].get(int(asof[:4]))})
            ix = {k: i for i, k in enumerate(P['ids'])}
            rel = Fe['rel']
            for key, e in FB.entries(book, f'{panel}:{h}', resolved=False):
                k0 = int(np.searchsorted(days, np.datetime64(e['asof'])))
                if k0 >= len(days) or str(days[k0]) != e['asof'] or k0 + h > t:
                    continue
                out = []
                for k in e['forecast']['ids']:
                    i = ix.get(k)
                    s = rel[i, k0 + 1:k0 + h + 1] if i is not None else None
                    out.append(r_(float(s.sum()), 5) if s is not None and np.isfinite(s).all() else None)
                FB.resolve(book, f'{panel}:{h}', key, {'rel': out})


def ledger_scores(book):
    out = {}
    for fam in sorted(book.get('families') or {}):
        ents = FB.entries(book, fam, resolved=True)
        ics, ls, pairs = [], [], []
        for _, e in ents:
            s, p, y = e['forecast']['s'], e['forecast']['p'], (e['actual'] or {}).get('rel') or []
            v = [(a, b, c) for a, b, c in zip(s, p, y) if fin(a) and fin(c)]
            if len(v) >= 8:
                a = np.array([x[0] for x in v]); c = np.expm1(np.array([x[2] for x in v]))   # simple returns vs SPY
                if np.ptp(a) > 0:
                    ra, rc = np.argsort(np.argsort(a)), np.argsort(np.argsort(c))
                    ics.append(float(np.corrcoef(ra, rc)[0, 1]))
                    q = np.quantile(a, [FIFTH, 1 - FIFTH])
                    ls.append(float(c[a >= q[1]].mean() - c[a <= q[0]].mean()))
            pairs += [(b, c > 0) for _, b, c in v if fin(b)]
        sc = FB.score_prob(pairs) if pairs else {}
        out[fam] = {'resolved_weeks': len(ics), 'pending_weeks': len(FB.entries(book, fam, resolved=False)), 'ic': r_(np.mean(ics)) if ics else None,
                    'best_minus_worst': r_(np.mean(ls)) if ls else None, 'brier_skill': sc.get('skill'), 'predictions': sc.get('n')}
    return out


# ------------------------------------------------------------------ everything
def fresh(public, asof, max_days=3):
    """The published file is for the same closed week, by this version, and under max_days old: nothing to redo (the
    workflow runs every three hours; the forecasts change once a week)."""
    try:
        d = json.loads((Path(public) / 'rrg-hybrid.json').read_text(encoding='utf-8'))
        made = dt.datetime.fromisoformat(d['generated_at'])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return d.get('version') == VERSION and d.get('asof') == asof and (dt.datetime.now(dt.timezone.utc) - made).days < max_days


def build(public, ledger=None, today=None, verbose=True, force=False):
    t0 = dt.datetime.now()
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    D = load(public)
    days, spy = D['days'], D['spy']
    t = closed_week(days, today or dt.date.today())
    if not force and fresh(public, str(days[t])):
        log(f'rrg hybrid: week ending {days[t]} already built — kept')
        return None
    doc = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'version': VERSION, 'asof': str(days[t]),
           'volume_week': str(days[max(t - VOLUME_LAG, 0)]), 'horizons': list(HORIZONS), 'test_from': TEST_FROM, 'blocks': {b: {'name': BLOCK_NAMES[b], 'inputs': [FEATURE_NAMES[k] for k in BLOCKS[b]]} for b in BLOCKS},
           'classic_inputs': [FEATURE_NAMES[k] for k in CLASSIC], 'costs_bp': [[lim, bp] for lim, bp in COST_TIERS], 'panels': {},
           'note': __doc__.split('\n\n')[0]}
    kept = {}
    for panel, P in D['panels'].items():
        if len(P['ids']) < 5:
            continue
        with warnings.catch_warnings(), np.errstate(all='ignore'):
            warnings.simplefilter('ignore', RuntimeWarning)
            Fe = features(P['C'], P['V'], spy, P['liq'])
            groups = CAL_GROUPS.get(panel, 1)
            Rs = {h: walk_forward(days, Fe, h, groups) for h in HORIZONS}
            ev = {h: evaluate(days, Fe, Rs[h], h, panel) for h in HORIZONS}
            rows = current_rows(days, P, Fe, Rs, t, spy, panel)
            desc = describe(days, Fe, panel)
        doc['panels'][panel] = {'lines': len(P['ids']), 'now': len(rows), 'scores': {str(h): ev[h] for h in HORIZONS},
                                'calibration': {'years': CAL_YEARS, 'vol_groups': groups},
                                'weights_now': {str(h): dict(zip(BLOCKS, Rs[h]['weights'].get(int(str(days[t])[:4])) or [0, 0, 0])) for h in HORIZONS},
                                'coefs': {str(h): Rs[h]['coefs'] for h in HORIZONS}, 'describe': desc, 'rows': rows,
                                'spy_drift_week': r_(spy_drift(spy, t), 5)}
        kept[panel] = (P, Fe, Rs)
        log(f"rrg hybrid {panel}: {len(rows)} lines now; IC 13w hybrid {(ev[13]['ic']['hybrid'] or {}).get('ic')} classic {(ev[13]['ic']['classic'] or {}).get('ic')}")
    co = doc['panels'].get('companies')
    if co:
        allrows = co['rows']
        (Path(public) / 'rrg-hybrid-companies.json').write_text(json.dumps(clean({'generated_at': doc['generated_at'], 'asof': doc['asof'], 'rows': allrows}),
                                                                           separators=(',', ':')), encoding='utf-8')
        ranked = sorted([r for r in allrows if fin((r.get('h13') or {}).get('rel'))], key=lambda r: -r['h13']['rel'])
        co['rows'] = ranked[:TOP_ROWS] + ranked[-TOP_ROWS:] if len(ranked) > 2 * TOP_ROWS else ranked
        co['rows_file'] = 'rrg-hybrid-companies.json'
    if ledger:
        book = FB.load(ledger)
        ledger_update(book, days, t, kept)
        FB.save(ledger, book)
        doc['ledger'] = ledger_scores(book)
    doc['seconds'] = round((dt.datetime.now() - t0).total_seconds(), 1)
    (Path(public) / 'rrg-hybrid.json').write_text(json.dumps(clean(doc), separators=(',', ':')), encoding='utf-8')
    log(f"rrg hybrid: written in {doc['seconds']}s")
    return doc


def clean(x):
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return float(x) if math.isfinite(x) else None
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--public', required=True)
    ap.add_argument('--ledger', default=None)
    ap.add_argument('--force', action='store_true', help='rebuild even when this closed week is already published')
    a = ap.parse_args()
    build(a.public, a.ledger, force=a.force)


if __name__ == '__main__':
    main()
