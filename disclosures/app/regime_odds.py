"""What followed a regime day — at the highs (app/highs.py), at the lows and in a range (app/regimes.py) — as
distributions, and whether the "most similar days" odds have worked out of sample.

  hist(x, edges)        counts of x in the bins (−∞, e1), [e1, e2) … [ek, +∞): the returns 1, 3 and 12 months on and
                        the regime's own measures (the further fall, the rebound, the pullback), on fixed bins, so a
                        company's similar days and every day of the regime draw on the same axis
  fan(closes, a, t)     the return from the day at every point of GRID (each week to a year): its 10 / 25 / 50 / 75 / 90%
                        among the days observed that far
  walk_forward(...)     the test of the similar-days odds. Each year from the third with a pool, a sample of that year's
                        days (one per asset in any 21 trading days) is given the odds of its 250 nearest days — the
                        same features, scaling and rules as the live analogues — found only among days whose 12-month
                        outcome was known before the year began (a random 40,000 of them when there are more); scored
                        against what happened: the Brier score against always saying the pool's base rate (skill), the
                        AUC, the calibration (said against happened, by tenth of the odds) and, for the 3-month
                        direction, the top − bottom fifth of the odds within each year (average 3-month return before
                        costs, with its t over years). By year and overall.
History and a model of it, not a forecast; today's companies only (survivors).
"""
from __future__ import annotations

import math

import numpy as np

GRID = list(range(0, 253, 7))
QS = (0.1, 0.25, 0.5, 0.75, 0.9)
EDGES = {
    'fwd21': [-0.2, -0.15, -0.1, -0.05, 0, 0.05, 0.1, 0.15, 0.2],
    'fwd63': [-0.4, -0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.3, 0.4],
    'fwd252': [-0.5, -0.3, -0.15, 0, 0.15, 0.3, 0.5, 1.0],
    'drop': [-0.5, -0.4, -0.3, -0.2, -0.15, -0.1, -0.05, -0.02],      # a fall from the day (≤ 0)
    'rise': [0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 1.0],             # a rise (≥ 0)
}
MIN_FAN = 30
K = 250
PER_YEAR = 150
POOL_MAX = 40000
MIN_POOL, MIN_YEARS, MIN_KEEP = 1000, 3, 50
SEED = 7
LAG = 252                       # a pool day counts once its 12-month outcome is known: no outcome is seen early


def _r(v, d=4):
    return None if v is None or not np.isfinite(v) else round(float(v), d)


def hist(x, edges):
    """Counts of the finite x in the bins (−∞, e1), [e1, e2) … [ek, +∞)."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return np.bincount(np.searchsorted(np.asarray(edges, float), x, side='right'), minlength=len(edges) + 1).tolist()


def dists(R, sel, extra=()):
    """{measure: counts} for the returns 1, 3 and 12 months on and `extra` [(field, edges key)], over the days in sel."""
    out = {}
    for k in ('fwd21', 'fwd63', 'fwd252'):
        if k in R:
            out[k] = hist(R[k][sel], EDGES[k])
    for f, e in extra:
        if f in R:
            out[f] = hist(R[f][sel], EDGES[e])
    return out


def edges_of(extra=()):
    """The bins' edges the dists were counted on (for the page)."""
    out = {k: EDGES[k] for k in ('fwd21', 'fwd63', 'fwd252')}
    out.update({f: EDGES[e] for f, e in extra})
    return out


def paths(closes, assets, ts, grid=GRID):
    """The return from each day (asset index, day index) at every point of grid: NaN past the end of its data."""
    out = np.full((len(ts), len(grid)), np.nan, np.float32)
    for r, (a, t) in enumerate(zip(assets, ts)):
        c = closes[int(a)]
        t = int(t)
        j = t + np.asarray(grid)
        ok = j < len(c)
        out[r, ok] = c[j[ok]] / c[t] - 1
    return out


def fan(closes, assets, ts, grid=GRID):
    """The 10 / 25 / 50 / 75 / 90% of the return from the day at each point of grid (None where under MIN_FAN days
    were observed that far), with the counts."""
    if not len(ts):
        return None
    P = paths(closes, assets, ts, grid)
    n = np.isfinite(P).sum(0)
    out = {'n': n.tolist()}
    with np.errstate(all='ignore'):
        for q in QS:
            v = np.nanquantile(np.where(np.isfinite(P), P, np.nan), q, axis=0) if np.isfinite(P).any() else np.full(len(grid), np.nan)
            out[f'p{round(100 * q)}'] = [_r(x, 4) if m >= MIN_FAN else None for x, m in zip(v, n)]
    return out


def sample(sel, n, seed=SEED):
    """At most n of the days in sel, at random (seeded: the same days each build)."""
    idx = np.nonzero(sel)[0]
    if len(idx) <= n:
        return idx
    return np.sort(np.random.default_rng(seed).choice(idx, n, replace=False))


# ------------------------------------------------------------------ the walk-forward test
def _auc(p, y):
    pos, neg = y == 1, y == 0
    if not pos.any() or not neg.any():
        return None
    sp = np.sort(p)                                                    # ties share their mean rank
    uniq, first, counts = np.unique(sp, return_index=True, return_counts=True)
    mean_rank = first + (counts + 1) / 2.0
    ranks = mean_rank[np.searchsorted(uniq, p)]
    return float((ranks[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * neg.sum()))


def score(p, b, y):
    """Brier against the base rate, the skill, the AUC and the calibration by tenth of the odds."""
    m = np.isfinite(p) & np.isfinite(b) & np.isfinite(y)
    p, b, y = p[m], b[m], y[m]
    if len(y) < 100:
        return None
    br, bb = float(np.mean((p - y) ** 2)), float(np.mean((b - y) ** 2))
    order = np.argsort(p, kind='mergesort')
    cal = []
    for part in np.array_split(order, 10):
        if len(part):
            cal.append([_r(p[part].mean(), 3), _r(y[part].mean(), 3), int(len(part))])
    return {'n': int(len(y)), 'rate': _r(y.mean(), 4), 'brier': _r(br, 5), 'brier_base': _r(bb, 5), 'skill': _r(1 - br / bb, 4) if bb > 0 else None,
            'auc': _r(_auc(p, y), 3), 'calibration': cal}


def verdict(skill):
    return None if skill is None else 'useful' if skill >= 0.02 else 'small' if skill >= 0.005 else 'none'


def walk_forward(R, gsel, feats, zf, outcomes, ret, day_of, known_day, k=K, per_year=PER_YEAR, pool_max=POOL_MAX, seed=SEED):
    """The similar-days odds tested year by year (module docstring). R: the pooled days (asset, t, the features);
    gsel: the days of one kind of asset; zf(field, values): the analogues' scaling; outcomes {name: 1 / 0 / NaN per
    day}; ret: the 3-month return per day (the spread); day_of / known_day: each day's date and the date its 12-month
    outcome was known (days since 1970; a large number while it is not)."""
    rng = np.random.default_rng(seed)
    yrs = (np.asarray(day_of, 'datetime64[D]').astype('datetime64[Y]').astype(int) + 1970)
    A, T = R['asset'].astype(np.int64), R['t'].astype(np.int64)
    Zall = np.stack([zf(f, R[f]).astype(np.float32) for f in feats], 1)
    names = list(outcomes)
    first = 'up63' if 'up63' in outcomes else names[0]
    rows = {'year': [], 'ret': [], **{f'p_{o}': [] for o in names}, **{f'b_{o}': [] for o in names}, **{f'y_{o}': [] for o in names}}
    years_seen = sorted(set(yrs[gsel].tolist()))
    for Y in years_seen:
        start = int(np.datetime64(f'{Y}-01-01', 'D').astype(int))
        pool = np.nonzero(gsel & (known_day < start))[0]
        if len(pool) < MIN_POOL or len(set(yrs[pool].tolist())) < MIN_YEARS:
            continue
        if len(pool) > pool_max:
            pool = np.sort(rng.choice(pool, pool_max, replace=False))
        base = {o: float(np.nanmean(outcomes[o][pool])) if np.isfinite(outcomes[o][pool]).any() else np.nan for o in names}
        Zp, Fp, Ap, Tp = Zall[pool], np.isfinite(Zall[pool]), A[pool], T[pool]
        cand = np.nonzero(gsel & (yrs == Y) & np.isfinite(outcomes[first]))[0]
        rng.shuffle(cand)
        seen, test = set(), []
        for i in cand:                                                  # one per asset in any 21 trading days
            key = (int(A[i]), int(T[i]) // 21)
            if key in seen:
                continue
            seen.add(key)
            test.append(i)
            if len(test) >= per_year:
                break
        for i in test:
            fm = np.nonzero(np.isfinite(Zall[i]))[0]
            if not len(fm):
                continue
            ok = Fp[:, fm].all(1) & ~((Ap == A[i]) & (Tp > T[i] - 252))
            idx = np.nonzero(ok)[0]
            if len(idx) < MIN_KEEP:
                continue
            D = ((Zp[idx][:, fm] - Zall[i, fm]) ** 2).sum(1)
            mm = min(len(idx), 40 * k)
            part = np.argpartition(D, mm - 1)[:mm]
            keep, taken = [], set()
            for j in part[np.argsort(D[part], kind='mergesort')]:       # the live rule: one per asset in any 21 days
                g = idx[j]
                kk = (int(Ap[g]), int(Tp[g]) // 21)
                if kk in taken:
                    continue
                taken.add(kk)
                keep.append(g)
                if len(keep) >= k:
                    break
            if len(keep) < MIN_KEEP:
                continue
            kp = pool[np.asarray(keep)]
            rows['year'].append(Y)
            rows['ret'].append(float(ret[i]) if np.isfinite(ret[i]) else np.nan)
            for o in names:
                v = outcomes[o][kp]
                rows[f'p_{o}'].append(float(np.nanmean(v)) if np.isfinite(v).any() else np.nan)
                rows[f'b_{o}'].append(base[o])
                rows[f'y_{o}'].append(float(outcomes[o][i]))
    if len(rows['year']) < 200:
        return None
    X = {k: np.asarray(v, float) for k, v in rows.items()}
    yr = X['year'].astype(int)
    out = {'days': int(len(yr)), 'years': [int(yr.min()), int(yr.max())], 'per_year': per_year, 'pool_max': pool_max, 'k': k, 'outcomes': {}}
    for o in names:
        s = score(X[f'p_{o}'], X[f'b_{o}'], X[f'y_{o}'])
        if not s:
            continue
        s['verdict'] = verdict(s['skill'])
        by = []
        for Y in sorted(set(yr.tolist())):
            m = yr == Y
            p, b, y = X[f'p_{o}'][m], X[f'b_{o}'][m], X[f'y_{o}'][m]
            f = np.isfinite(p) & np.isfinite(b) & np.isfinite(y)
            if f.sum() >= 30:
                bb = float(np.mean((b[f] - y[f]) ** 2))
                by.append([int(Y), int(f.sum()), _r(1 - float(np.mean((p[f] - y[f]) ** 2)) / bb, 3) if bb > 0 else None, _r(y[f].mean(), 3)])
        s['by_year'] = by
        out['outcomes'][o] = s
    # the spread: within each year, the top − bottom fifth of the 3-month odds, by their 3-month return (before costs)
    if f'p_{first}' in X:
        tops, bots, alls, diffs = [], [], [], []
        for Y in sorted(set(yr.tolist())):
            m = (yr == Y) & np.isfinite(X[f'p_{first}']) & np.isfinite(X['ret'])
            if m.sum() < 50:
                continue
            p, r = X[f'p_{first}'][m], X['ret'][m]
            lo_, hi_ = np.quantile(p, [0.2, 0.8])
            t_, b_ = r[p >= hi_], r[p <= lo_]
            if len(t_) < 5 or len(b_) < 5:
                continue
            tops.append(t_.mean()); bots.append(b_.mean()); alls.append(r.mean()); diffs.append(t_.mean() - b_.mean())
        if len(diffs) >= 5:
            d = np.asarray(diffs)
            sd = d.std(ddof=1)
            out['spread'] = {'years': len(d), 'top': _r(np.mean(tops)), 'bottom': _r(np.mean(bots)), 'all': _r(np.mean(alls)), 'diff': _r(d.mean()),
                             't': _r(d.mean() / (sd / math.sqrt(len(d))), 2) if sd > 0 else None, 'pos': _r((d > 0).mean(), 3)}
    return out


def day_index(days_list, assets, ts, lag=None):
    """Each pooled day's date (days since 1970) — or, with lag, the date lag trading days later (a large number past
    the end of the asset's data)."""
    big = np.int64(10 ** 7)
    conv = [np.asarray(d, 'datetime64[D]').astype(np.int64) for d in days_list]
    out = np.full(len(ts), big, np.int64)
    A, T = np.asarray(assets, np.int64), np.asarray(ts, np.int64)
    for a in np.unique(A):
        m = A == a
        dd = conv[int(a)]
        j = T[m] + (lag or 0)
        v = np.full(m.sum(), big, np.int64)
        okj = j < len(dd)
        v[okj] = dd[j[okj]]
        out[m] = v
    return out
