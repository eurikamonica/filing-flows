"""At the highs: how long runs of new all-time highs last and how deep the pullback is that ends them — for every asset of
the move odds (companies, ETFs, indices; the S&P 500 index since 1928), by the state of the run and of the asset when it
was at its highs: how old the run is, how many new highs it made in the last quarter, how far the price stands above its
200-day average, momentum, volatility, valuation (trailing P/E from first-filed quarterly EPS) and volume. Descriptive
history, not a forecast; the hub's Move odds → At the highs view and each asset's file (doc.highs) read it.

Definitions (trading days; adjusted closes — dividends reinvested — so an all-time high is a total-return high)
  ATH day        a close at or above every close before it.
  high day       a day within 5% of the all-time high with an ATH day in the last 21 trading days: an asset "running at
                 its highs". Every high day is an event; consecutive ones overlap, so runs and assets are counted too.
  run            the ATH days between two drawdowns of 10% or more from the high: it starts at the first ATH after a 10%
                 drawdown and its peak is its last ATH before the next one.
  run age        trading days since the run's first ATH.
  pullback x%    the first day the close is x% or more below the all-time high (5%, 10%, 20%): the days until then,
                 with Kaplan–Meier for the ones still waiting at the end of the data.
  run left       trading days from the event to the run's peak (the last ATH before the next 10% pullback); the new highs
                 still to come; the gain from the event to the peak.
  the pullback   the drawdown that ends the run, measured from its peak to its lowest close before the next ATH (one
                 still open counts at its depth so far, in a separate share), and the days to get back to the peak.
State at an event (each a percentile in the asset's own history up to that day where marked, at least three years of it)
  age, highs63 (ATH days in the last 63), dd (from the ATH), ext200 (close vs its 200-day average; own percentile),
  mom (12-1 months; own percentile; companies also against every other company that day), vol (21-day volatility; own
  percentile), pe (price ÷ the sum of the last four first-filed quarterly EPS, positive only; own percentile from three
  years of it), volu (average volume in the last 3 months ÷ the last 12).
Analogues for an asset at its highs now: the 250 high days of the same kind (companies; funds; indices) nearest on the
state variables both have, at most one per asset and 21-day block, and what followed them.
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

NEAR, RECENT, RUN_DD = 0.05, 21, 0.10
PULLS = (0.05, 0.10, 0.20)
HZ = (21, 63, 126, 252)
MIN_HIST = 756                            # three years before an own-history percentile counts
REFRESH = 63                              # the percentile grid is redrawn every quarter
CAP = 5040                                # durations counted up to twenty years
K_ANALOG = 250
SPLITS = (2, 3, 4, 5, 6, 7, 8, 10, 15, 20, 25, 30, 40, 50, 1.5, 2.5, 1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 6, 1 / 8, 1 / 10, 1 / 15, 1 / 20, 1 / 25, 1 / 30, 1 / 50)
FEATURES = ('age', 'highs63', 'dd', 'ext_pct', 'mom_pct', 'vol_pct', 'pe_pct', 'volu')
BUCKETS = {
    'age': ('Run age (trading days since its first ATH)', [0, 21, 63, 126, 252, 504, 1e9], ['under 1 month', '1–3 months', '3–6 months', '6–12 months', '1–2 years', '2 years or more']),
    'highs63': ('New highs in the last 63 trading days', [0, 3, 6, 11, 21, 31, 1e9], ['1–2', '3–5', '6–10', '11–20', '21–30', '31 or more']),
    'ext200': ('Above the 200-day average', [-1e9, 0.05, 0.10, 0.20, 0.30, 0.50, 1e9], ['under 5%', '5–10%', '10–20%', '20–30%', '30–50%', '50% or more']),
    'ext_pct': ('Above the 200-day average, percentile of its own history', [0, 50, 80, 90, 95, 99, 101], ['under 50', '50–80', '80–90', '90–95', '95–99', '99 or more']),
    'mom_pct': ('12-1 month momentum, percentile of its own history', [0, 50, 80, 90, 95, 99, 101], ['under 50', '50–80', '80–90', '90–95', '95–99', '99 or more']),
    'mom_xs': ('12-1 month momentum, percentile among all companies that day', [0, 50, 80, 90, 95, 99, 101], ['under 50', '50–80', '80–90', '90–95', '95–99', '99 or more']),
    'vol_pct': ('21-day volatility, percentile of its own history', [0, 20, 40, 60, 80, 95, 101], ['under 20 (calm)', '20–40', '40–60', '60–80', '80–95', '95 or more (stormy)']),
    'pe_pct': ('Trailing P/E, percentile of its own history', [0, 50, 80, 90, 95, 99, 101], ['under 50', '50–80', '80–90', '90–95', '95–99', '99 or more']),
    'pe': ('Trailing P/E', [0, 15, 25, 35, 50, 80, 1e9], ['under 15', '15–25', '25–35', '35–50', '50–80', '80 or more']),
    'volu': ('Volume, last 3 months vs last 12', [0, 0.8, 1.0, 1.2, 1.5, 2.0, 1e9], ['under 0.8×', '0.8–1.0×', '1.0–1.2×', '1.2–1.5×', '1.5–2.0×', '2× or more']),
}
GROUPS = (('companies', 'Companies (today’s, adjusted closes)'), ('funds', 'ETFs: sectors, styles, the market, countries, bonds, commodities'),
          ('indices', 'Indices (price only; the S&P 500 since 1928)'))
NOTE = ('History, not a forecast. High days overlap (a run of highs counts every day), so runs and assets are given beside '
        'the days. Companies are today’s (survivors), which flatters what came after their highs; adjusted closes make an '
        'all-time high a total-return high. P/E: price ÷ the last four first-filed quarterly diluted EPS (SEC), positive only.')


# ------------------------------------------------------------------ helpers
def _r(v, d=4):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, d) if math.isfinite(f) else None


def own_pct(x, min_hist=MIN_HIST, refresh=REFRESH):
    """The percentile (0-100) of each value among the asset's own values up to that day (the grid of past values redrawn
    every `refresh` days; NaN until `min_hist` values are on file)."""
    n = len(x)
    out = np.full(n, np.nan)
    fin = np.isfinite(x)
    cnt = np.cumsum(fin)
    start = int(np.searchsorted(cnt, min_hist))
    if start >= n:
        return out
    past = np.sort(x[:start + 1][fin[:start + 1]])
    for a in range(start, n, refresh):
        if a > start:                                           # the new values merged in (two sorted runs: linear)
            new = x[a - refresh + 1:a + 1]
            past = np.sort(np.concatenate([past, np.sort(new[np.isfinite(new)])]), kind='stable')
        b = min(n, a + refresh)
        seg = x[a:b]
        ok = np.isfinite(seg)
        out[a:b][ok] = 100.0 * np.searchsorted(past, seg[ok], side='right') / len(past)
    return out


def rolling_mean(x, w, min_frac=0.8):
    fin = np.isfinite(x)
    cs = np.concatenate([[0.0], np.cumsum(np.where(fin, x, 0.0))])
    cn = np.concatenate([[0], np.cumsum(fin)])
    out = np.full(len(x), np.nan)
    if len(x) >= w:
        s, m = cs[w:] - cs[:-w], cn[w:] - cn[:-w]
        out[w - 1:] = np.where(m >= min_frac * w, s / np.maximum(m, 1), np.nan)
    return out


def next_true(cond):
    """For each i, the first j > i with cond[j] (len(cond) if none)."""
    n = len(cond)
    idx = np.where(cond, np.arange(n), n)
    nxt = np.minimum.accumulate(idx[::-1])[::-1]               # first j >= i
    out = np.empty(n, int)
    out[:-1] = nxt[1:]
    out[-1] = n
    return out


def prev_true(cond):
    """For each i, the last j <= i with cond[j] (-1 if none)."""
    idx = np.where(cond, np.arange(len(cond)), -1)
    return np.maximum.accumulate(idx)


def fix_splits(recs):
    """First-filed quarterly EPS restated across the splits the store missed: a jump in diluted shares from one quarter
    to the next that matches a split ratio (within 5%, and EPS closer to moving by it than to standing still) divides
    every earlier EPS by it."""
    recs = sorted([r for r in recs if r.get('eps') is not None and r.get('end') and r.get('filed')], key=lambda r: r['end'])
    f = [1.0] * len(recs)
    for i in range(1, len(recs)):
        a, b = recs[i - 1].get('shares'), recs[i].get('shares')
        if not (a and b and a > 0 and b > 0):
            continue
        q = b / a
        if 0.7 < q < 1.4:
            continue
        s = min(SPLITS, key=lambda x: abs(math.log(q / x)))
        if abs(math.log(q / s)) > 0.05:
            continue
        ea, eb = recs[i - 1]['eps'], recs[i]['eps']
        if ea and eb and ea * eb > 0 and abs(math.log(abs(ea / eb) / s)) >= abs(math.log(abs(ea / eb))):
            continue                                            # EPS moved less like the split than like nothing: no split
        for j in range(i):
            f[j] *= s
    return [(r['filed'], r['end'], r['eps'] / k) for r, k in zip(recs, f)]


def ttm_eps(days, recs):
    """The trailing four quarters' EPS known on each day (point in time: by filing date), NaN when four consecutive
    quarters are not on file."""
    if not recs:
        return np.full(len(days), np.nan)
    by_end = {}
    for filed, end, eps in recs:                                  # each quarter as first filed
        if end not in by_end or filed < by_end[end][0]:
            by_end[end] = (filed, eps)
    ends = sorted(by_end)
    known = []                                                    # (date known, TTM) for each quarter with three before it
    for i in range(3, len(ends)):
        e4 = ends[i - 3:i + 1]
        span = (dt.date.fromisoformat(e4[-1]) - dt.date.fromisoformat(e4[0])).days
        if not 250 <= span <= 300:
            continue
        when = max(by_end[e][0] for e in e4)
        known.append((when, sum(by_end[e][1] for e in e4), e4[-1]))
    known.sort()
    out = np.full(len(days), np.nan)
    if not known:
        return out
    kd = [k[0] for k in known]
    best_end, best = None, np.nan
    j = 0
    for t, d in enumerate(days):                                   # the latest quarter known by then
        while j < len(known) and kd[j] <= d:
            if best_end is None or known[j][2] >= best_end:
                best_end, best = known[j][2], known[j][1]
            j += 1
        if best_end is not None and (dt.date.fromisoformat(d) - dt.date.fromisoformat(best_end)).days <= 200:
            out[t] = best
    return out


def volume_ratio(days, vdays, vols):
    """Average volume over the last 91 calendar days ÷ the last 365 (daily or weekly volumes), on each day."""
    out = np.full(len(days), np.nan)
    if vdays is None or not len(vdays):
        return out
    vt = np.asarray(vdays, dtype='datetime64[D]').astype(np.int64)
    vv = np.array([np.nan if v is None else float(v) for v in vols], float)
    ok = np.isfinite(vv) & (vv >= 0)
    vt, vv = vt[ok], vv[ok]
    if len(vt) < 20:
        return out
    cs = np.concatenate([[0.0], np.cumsum(vv)])
    t = np.asarray(days, dtype='datetime64[D]').astype(np.int64)
    hi = np.searchsorted(vt, t, side='right')
    lo3, lo12 = np.searchsorted(vt, t - 91, side='right'), np.searchsorted(vt, t - 365, side='right')
    n3, n12 = hi - lo3, hi - lo12
    step = np.median(np.diff(vt)) if len(vt) > 1 else 1
    need3, need12 = 0.5 * 91 / max(step, 1) * (5 / 7 if step < 3 else 1), 0.5 * 365 / max(step, 1) * (5 / 7 if step < 3 else 1)
    with np.errstate(invalid='ignore', divide='ignore'):
        r = ((cs[hi] - cs[lo3]) / np.maximum(n3, 1)) / ((cs[hi] - cs[lo12]) / np.maximum(n12, 1))
    good = (n3 >= need3) & (n12 >= need12) & (t <= vt[-1] + 10)
    out[good] = r[good]
    return out


# ------------------------------------------------------------------ one asset
def asset_frame(c, raw=None, eps=None, volu=None):
    """The state and what followed, for every day of one asset (closes c; raw closes for the P/E when the closes are
    dividend-adjusted; the trailing EPS and the volume ratio on the same days): a dict of arrays."""
    c = np.asarray(c, float)
    n = len(c)
    ix = np.arange(n)
    hi = np.maximum.accumulate(c)
    dd = c / hi - 1
    ath = c >= hi * (1 - 1e-12)
    deep = dd <= -RUN_DD
    last_deep = prev_true(deep)
    first_ath = np.minimum.accumulate(np.where(ath, ix, n)[::-1])[::-1]          # the first ATH at or after each day
    run_start = np.where(last_deep >= 0, first_ath[np.clip(last_deep + 1, 0, n - 1)], first_ath[0])
    run_start = np.where(run_start > ix, -1, run_start)
    cath = np.concatenate([[0], np.cumsum(ath)])                                  # ATH days before each index
    last_ath = prev_true(ath)
    F = {'n': n, 'dd': dd, 'ath': ath, 'run_start': run_start}
    F['high'] = (dd >= -NEAR) & (last_ath >= 0) & (ix - last_ath < RECENT) & (ix >= 252)
    F['age'] = np.where(run_start >= 0, ix - run_start, -1).astype(float)
    F['highs63'] = (cath[ix + 1] - cath[np.maximum(0, ix - 62)]).astype(float)
    lr = np.concatenate([[np.nan], np.diff(np.log(c))])
    F['ext200'] = c / rolling_mean(c, 200) - 1
    F['mom'] = np.full(n, np.nan)
    if n > 252:
        F['mom'][252:] = c[231:n - 21] / c[:n - 252] - 1
    F['vol'] = np.full(n, np.nan)
    if n > 21:
        F['vol'][20:] = np.nanstd(np.lib.stride_tricks.sliding_window_view(lr, 21), axis=1) * math.sqrt(252)
    F['pe'] = np.full(n, np.nan)
    if eps is not None:
        px = np.asarray(raw, float) if raw is not None else c
        with np.errstate(invalid='ignore', divide='ignore'):
            pe = np.where(np.asarray(eps) > 0, px / eps, np.nan)
        pe[~((pe > 0) & (pe <= 300))] = np.nan
        F['pe'] = pe
    F['volu'] = np.asarray(volu, float) if volu is not None else np.full(n, np.nan)
    F['ext_pct'], F['mom_pct'], F['vol_pct'], F['pe_pct'] = own_pct(F['ext200']), own_pct(F['mom']), own_pct(F['vol']), own_pct(F['pe'])
    # what followed: the first close x% under the ATH; the run's peak (its last ATH before the 10% pullback)
    for x in PULLS:
        F[f't{round(100 * x)}'] = (next_true(dd <= -x) - ix).astype(float)       # n - i when never: still waiting
    t10 = ix + F['t10'].astype(int)
    F['ended'] = t10 < n
    peak = last_ath[np.clip(t10 - 1, 0, n - 1)]
    F['peak'] = peak
    F['run_left'] = np.maximum(0, peak - ix).astype(float)
    F['highs_left'] = (cath[np.clip(t10, 0, n)] - cath[ix + 1]).astype(float)
    F['gain_left'] = np.maximum(c[np.clip(peak, 0, n - 1)] / c - 1, 0.0)
    # the drawdown after each ATH: its depth to the next ATH (or the end) and the days back
    ai = np.nonzero(ath)[0]
    depth_after, back_after, recovered = np.zeros(n), np.full(n, np.nan), np.zeros(n, bool)
    if len(ai):
        nxt = np.append(ai[1:], n)
        for a, b in zip(ai, nxt):
            if b > a + 1:
                depth_after[a] = dd[a + 1:b].min()
            recovered[a] = b < n
            if b < n:
                back_after[a] = b - a
    pk = np.clip(peak, 0, n - 1)
    F['pull_depth'] = np.where(F['ended'], depth_after[pk], np.nan)
    F['pull_closed'] = F['ended'] & recovered[pk]
    F['pull_days'] = np.where(F['pull_closed'], back_after[pk], np.nan)
    for h in HZ:
        f = np.full(n, np.nan)
        if n > h:
            f[:n - h] = c[h:] / c[:n - h] - 1
        F[f'fwd{h}'] = f
    for h in (63, 252):
        m = np.full(n, np.nan)
        if n > h:
            w = np.lib.stride_tricks.sliding_window_view(dd[1:], h)
            m[:len(w)] = w.min(axis=1)
        F[f'mdd{h}'] = m
    return F


def own_runs(F):
    """The asset's completed runs: (start, peak, days from the first ATH to the peak, gain, the pullback's depth, days back)."""
    out = []
    peaks = np.unique(F['peak'][F['ended'] & (F['peak'] >= 0)])
    for p in peaks:
        s = F['run_start'][p]
        if s < 0:
            continue
        out.append((int(s), int(p), int(p - s), float(F['pull_depth'][p]) if np.isfinite(F['pull_depth'][p]) else None,
                    float(F['pull_days'][p]) if np.isfinite(F['pull_days'][p]) else None))
    return out


# ------------------------------------------------------------------ summaries
def km(times, events, grid=None):
    """Kaplan–Meier on whole days: the survival at each day of `grid`, the median, P(T ≤ h) for h in HZ."""
    t = np.minimum(np.asarray(times, float), CAP).astype(int)
    e = np.asarray(events, bool)
    if not len(t):
        return None
    d = np.bincount(t[e], minlength=CAP + 1)
    allc = np.bincount(t, minlength=CAP + 1)
    at_risk = len(t) - np.concatenate([[0], np.cumsum(allc)[:-1]])
    with np.errstate(invalid='ignore', divide='ignore'):
        haz = np.where(at_risk > 0, d / np.maximum(at_risk, 1), 0.0)
    S = np.cumprod(1 - haz)
    below = np.nonzero(S <= 0.5)[0]
    out = {'n': int(len(t)), 'events': int(e.sum()), 'median': int(below[0]) if len(below) else None,
           'p': {str(h): _r(1 - S[h], 4) for h in HZ}}
    if grid is not None:
        out['curve'] = [_r(S[g], 3) for g in grid]
    return out


def q(x, ps=(0.25, 0.5, 0.75, 0.9)):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if not len(x):
        return None
    return {'n': int(len(x)), **{f'p{round(100 * p)}': _r(np.quantile(x, p), 4) for p in ps}, 'mean': _r(x.mean(), 4), 'up': _r((x > 0).mean(), 4)}


GRID = list(range(0, 253, 7))


def summarize(R, sel, curves=False):
    """What followed the high days in `sel` (a boolean mask over the pooled rows R)."""
    if not sel.any():
        return {'days': 0}
    n = R['n_left'][sel]
    out = {'days': int(sel.sum()), 'runs': int(len(set(zip(R['asset'][sel].tolist(), R['run'][sel].tolist())))),
           'assets': int(len(set(R['asset'][sel].tolist())))}
    for x in ('t5', 't10', 't20'):
        out[x] = km(R[x][sel], R[x][sel] < n, GRID if curves else None)
    out['run_left'] = km(R['run_left'][sel], R['ended'][sel], GRID if curves else None)
    known = R['ended'][sel] | (R['highs_left'][sel] > 0)
    out['more_highs'] = _r((R['highs_left'][sel][known] > 0).mean(), 4) if known.any() else None
    ended = R['ended'][sel]
    out['highs_left'] = q(R['highs_left'][sel][ended])
    out['gain_left'] = q(R['gain_left'][sel][ended])
    out['pullback'] = q(R['pull_depth'][sel][ended], (0.1, 0.25, 0.5, 0.75))
    out['pullback_open'] = _r((~R['pull_closed'][sel][ended]).mean(), 4) if ended.any() else None
    out['days_back'] = q(R['pull_days'][sel][R['pull_closed'][sel]], (0.25, 0.5, 0.75, 0.9))
    for h in HZ:
        out[f'fwd{h}'] = q(R[f'fwd{h}'][sel], (0.1, 0.25, 0.5, 0.75, 0.9))
    for h in (63, 252):
        out[f'mdd{h}'] = q(R[f'mdd{h}'][sel], (0.1, 0.25, 0.5, 0.75))
    return out


def short(s):
    """The bucket tables' cells."""
    if not s or not s.get('days'):
        return {'days': 0}
    t5, t10, rl = s.get('t5') or {}, s.get('t10') or {}, s.get('run_left') or {}
    return {'days': s['days'], 'runs': s['runs'], 'assets': s['assets'], 't5_median': t5.get('median'), 't10_median': t10.get('median'),
            't10_p63': (t10.get('p') or {}).get('63'), 't10_p252': (t10.get('p') or {}).get('252'), 'run_left_median': rl.get('median'),
            'more_highs': s.get('more_highs'), 'pullback_median': (s.get('pullback') or {}).get('p50'), 'pullback_p25': (s.get('pullback') or {}).get('p25'),
            'fwd63': (s.get('fwd63') or {}).get('p50'), 'fwd63_up': (s.get('fwd63') or {}).get('up'), 'fwd252': (s.get('fwd252') or {}).get('p50'),
            'fwd252_up': (s.get('fwd252') or {}).get('up'), 'mdd252': (s.get('mdd252') or {}).get('p50')}


# ------------------------------------------------------------------ analogues
SCALE = {'age': ('log', 1.0), 'highs63': ('lin', 8.0), 'dd': ('lin', 0.02), 'ext_pct': ('lin', 25.0), 'mom_pct': ('lin', 25.0),
         'vol_pct': ('lin', 25.0), 'pe_pct': ('lin', 25.0), 'volu': ('log', 0.25)}


def _z(k, v):
    how, s = SCALE[k]
    v = np.asarray(v, float)
    with np.errstate(invalid='ignore', divide='ignore'):
        return (np.log1p(np.maximum(v, 0)) if how == 'log' and k == 'age' else np.log(v) if how == 'log' else v) / s


def analogues(R, gsel, now, asset, t_abs, k=K_ANALOG):
    """The high days of the group nearest to `now` (feature dict) on the features it has, at most one per asset and
    21-day block, none from the same asset in the last year; their mask over R."""
    feats = [f for f in FEATURES if now.get(f) is not None and np.isfinite(now[f])]
    ok = gsel.copy()
    for f in feats:
        ok &= np.isfinite(R[f])
    ok &= ~((R['asset'] == asset) & (R['t'] > t_abs - 252))
    idx = np.nonzero(ok)[0]
    if len(idx) < 30:
        return None, feats, []
    D = np.zeros(len(idx))
    for f in feats:
        D += (_z(f, R[f][idx]) - _z(f, now[f])) ** 2
    m = min(len(idx), 40 * k)
    part = np.argpartition(D, m - 1)[:m]
    order = part[np.argsort(D[part])]
    taken, keep = set(), []
    for j in order:
        i = idx[j]
        key = (int(R['asset'][i]), int(R['t'][i]) // 21)
        if key in taken:
            continue
        taken.add(key)
        keep.append(i)
        if len(keep) >= k:
            break
    sel = np.zeros(len(R['t']), bool)
    sel[keep] = True
    return sel, feats, keep


# ------------------------------------------------------------------ the build
KIND_GROUP = {'stock': 'companies', 'sector': 'funds', 'style': 'funds', 'market': 'funds', 'etf': 'funds', 'index': 'indices'}


def _state(F, days, closes, last):
    """One asset's last day: where it stands against its high and its run, and the state variables."""
    t = F['n'] - 1
    la = int(prev_true(F['ath'])[t])
    st = {'date': days[t], 'close': _r(closes[t], 4), 'ath_date': days[la] if la >= 0 else None, 'ath': _r(closes[la], 4) if la >= 0 else None,
          'dd': _r(F['dd'][t]), 'high': bool(F['high'][t]),
          **{f: _r(F[f][t]) for f in ('age', 'highs63', 'ext200', 'ext_pct', 'mom', 'mom_pct', 'vol', 'vol_pct', 'pe', 'pe_pct', 'volu')}}
    if F['run_start'][t] >= 0:
        s0 = int(F['run_start'][t])
        st.update(run_start=days[s0], run_gain=_r(closes[t] / closes[s0] - 1), run_highs=int(F['ath'][s0:t + 1].sum()))
    return st


def build(data, assets, eps=None, volumes=None, raw=None, out_path=None, verbose=True, now_max=400):
    """highs.json from the move odds' daily closes: data {key: (days, closes, last)}, assets [{key, kind, group, name,
    cik, ticker}], eps {cik: [records]} (the first-filed quarterly EPS store), volumes {key: (days, volumes)}, raw
    {key: (days, raw closes)} for the P/E. Returns (doc, per-asset blocks for the assets' own files)."""
    eps, volumes, raw = eps or {}, volumes or {}, raw or {}
    keep_cols = list(FEATURES) + ['ext200', 'mom', 'vol', 'pe', 't5', 't10', 't20', 'run_left', 'ended', 'highs_left', 'gain_left', 'pull_depth',
                                  'pull_closed', 'pull_days'] + [f'fwd{h}' for h in HZ] + ['mdd63', 'mdd252']
    rows = {k: [] for k in ['asset', 'run', 't', 'n_left', 'group'] + keep_cols}
    meta, moms, gi = [], {}, {g: i for i, (g, _) in enumerate(GROUPS)}
    for a in assets:
        key, g = a['key'], KIND_GROUP.get(a.get('kind'))
        if g is None or key not in data or str(key).startswith('VIX'):
            continue
        days, closes = data[key][0], np.asarray(data[key][1], float)
        if len(closes) < 504 or not np.all(np.isfinite(closes)) or (closes <= 0).any():
            continue
        e, rd = None, None
        recs = eps.get(str(a.get('cik'))) if a.get('cik') else None
        if recs:
            e = ttm_eps(days, fix_splits(recs))
            if key in raw:                                          # raw closes (split-adjusted, not dividend-adjusted)
                dn = np.asarray(days, dtype='datetime64[D]')
                rt, rv = np.asarray(raw[key][0], dtype='datetime64[D]'), np.array([np.nan if v is None else float(v) for v in raw[key][1]], float)
                j = np.searchsorted(dn, rt)
                ok = (j < len(dn)) & np.isfinite(rv) & (rv > 0)
                ok[ok] = dn[j[ok]] == rt[ok]
                rd = np.array(closes)
                if ok.any():
                    rd[j[ok]] = rv[ok]
                    j0 = int(j[ok][0])                              # before the raw closes: the adjusted ones, joined there
                    rd[:j0] = closes[:j0] * (rd[j0] / closes[j0])
        vr = volume_ratio(days, *volumes[key]) if key in volumes else None
        F = asset_frame(closes, raw=rd, eps=e, volu=vr)
        ai = len(meta)
        t = F['n'] - 1
        m = {'key': key, 'group': g, 'days': days, 'a': a, 'runs': own_runs(F), 'state': _state(F, days, closes, data[key][2]),
             'now': {f: float(F[f][t]) for f in FEATURES} if F['high'][t] else None, 't': t}
        meta.append(m)
        if g == 'companies':
            moms[ai] = F['mom'].astype(np.float32)
        hs = np.nonzero(F['high'])[0]
        if len(hs):
            rows['asset'].append(np.full(len(hs), ai, np.int32))
            rows['run'].append(F['run_start'][hs].astype(np.int32))
            rows['t'].append(hs.astype(np.int32))
            rows['n_left'].append((F['n'] - hs).astype(np.int32))
            rows['group'].append(np.full(len(hs), gi[g], np.int8))
            for k in keep_cols:
                rows[k].append(np.asarray(F[k])[hs].astype(bool if k in ('ended', 'pull_closed') else np.float32))
        del F
    if not meta:
        return None, {}
    R = {k: np.concatenate(v) if v else np.zeros(0) for k, v in rows.items()}
    del rows
    # momentum among all companies that day (the factor's rank): every company's 12-1 momentum on one grid of days
    R['mom_xs'] = np.full(len(R['t']), np.nan, np.float32)
    cols_sorted, gpos = None, {}
    if moms:
        grid = sorted({d for i in moms for d in meta[i]['days'][-9000:]})
        gpos = {d: j for j, d in enumerate(grid)}
        gd = np.array(grid, dtype='datetime64[D]')
        M = np.full((len(moms), len(grid)), np.nan, np.float32)
        for r_, (i, mo) in enumerate(moms.items()):
            ds = np.array(meta[i]['days'], dtype='datetime64[D]')
            j = np.searchsorted(gd, ds)
            ok = (j < len(grid)) & (gd[np.minimum(j, len(grid) - 1)] == ds)
            M[r_, j[ok]] = mo[ok]
        del moms
        cnt = np.isfinite(M).sum(0)
        cols_sorted = np.sort(M, axis=0)                            # NaN last
        del M
        cj = np.nonzero(R['group'] == gi['companies'])[0]
        col = np.array([gpos.get(meta[int(R['asset'][j])]['days'][int(R['t'][j])], -1) for j in cj])
        for j, c in zip(cj, col):
            if c >= 0 and cnt[c] >= 50 and np.isfinite(R['mom'][j]):
                R['mom_xs'][j] = 100.0 * np.searchsorted(cols_sorted[:cnt[c], c], R['mom'][j], side='right') / cnt[c]

    def xs_now(day, v):
        c = gpos.get(day)
        if cols_sorted is None or c is None or v is None or not np.isfinite(v):
            return None
        k = int(np.isfinite(cols_sorted[:, c]).sum())
        return _r(100.0 * np.searchsorted(cols_sorted[:k, c], v, side='right') / k, 2) if k >= 50 else None
    doc = {'schema': 'highs.v1', 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
           'params': {'near': NEAR, 'recent': RECENT, 'run_drawdown': RUN_DD, 'pullbacks': list(PULLS), 'horizons': list(HZ), 'grid': GRID,
                      'min_history': MIN_HIST, 'analogues': K_ANALOG}, 'groups': {}, 'now': [], 'note': NOTE}
    for g, label in GROUPS:
        gsel = R['group'] == gi[g]
        if not gsel.any():
            continue
        firsts = [meta[i]['days'][0] for i in set(R['asset'][gsel].tolist())]
        G = {'label': label, 'from': min(firsts) if firsts else None, 'base': summarize(R, gsel, curves=True), 'buckets': {}}
        for f, (title, edges, labels) in BUCKETS.items():
            v = R[f]
            if not np.isfinite(v[gsel]).any():
                continue
            G['buckets'][f] = {'title': title, 'rows': [{'label': lab, **short(summarize(R, gsel & np.isfinite(v) & (v >= lo) & (v < hi_)))}
                                                        for lo, hi_, lab in zip(edges[:-1], edges[1:], labels)]}
        doc['groups'][g] = G
    # every asset: its last day and its own past runs; at its highs, its analogues
    blocks = {}
    for ai, m in enumerate(meta):
        key, a, runs = m['key'], m['a'], m['runs']
        own = {'runs': len(runs), 'run_days': q([r[2] for r in runs], (0.25, 0.5, 0.75)),
               'pullback': q([r[3] for r in runs if r[3] is not None], (0.25, 0.5, 0.75)),
               'days_back': q([r[4] for r in runs if r[4] is not None], (0.25, 0.5, 0.75)),
               'last': [{'start': m['days'][r[0]], 'peak': m['days'][r[1]], 'days': r[2], 'pullback': _r(r[3]), 'days_back': r[4]} for r in runs[-8:]]}
        state = m['state']
        if m['group'] == 'companies':
            state['mom_xs'] = xs_now(state['date'], state.get('mom'))
        block = {'state': state, 'own': own}
        if m['now'] is not None:
            sel, feats, keep = analogues(R, R['group'] == gi[m['group']], m['now'], ai, m['t'])
            if sel is not None:
                block['analogues'] = {'features': feats, **summarize(R, sel, curves=True),
                                      'nearest': [{'key': meta[int(R['asset'][j])]['key'], 'date': meta[int(R['asset'][j])]['days'][int(R['t'][j])],
                                                   'age': _r(R['age'][j], 0), 'highs63': _r(R['highs63'][j], 0), 'run_left': _r(R['run_left'][j], 0) if R['ended'][j] else None,
                                                   't10': _r(R['t10'][j], 0) if R['t10'][j] < R['n_left'][j] else None, 'pullback': _r(R['pull_depth'][j]),
                                                   'fwd252': _r(R['fwd252'][j])} for j in keep[:12]]}
            lite = dict(block)                                      # the list: no curves or nearest days (they are in the asset's file)
            if 'analogues' in lite:
                lite['analogues'] = {k: ({kk: vv for kk, vv in v.items() if kk != 'curve'} if isinstance(v, dict) else v)
                                     for k, v in lite['analogues'].items() if k != 'nearest'}
            lite.pop('own', None)
            doc['now'].append({'key': key, 'name': a.get('name'), 'kind': a.get('kind'), 'group': m['group'], 'sector': a.get('sector'), **lite})
        blocks[key] = block
    doc['now'].sort(key=lambda r: (-(r['state'].get('highs63') or 0), r['key']))
    doc['now'] = doc['now'][:now_max]
    if out_path:
        Path(out_path).write_text(json.dumps(doc, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    if verbose:
        print('highs:', {g: v['base']['days'] for g, v in doc['groups'].items()}, 'at their highs now:', len(doc['now']), flush=True)
    return doc, blocks


def load_eps(folder):
    """{cik: records} from the first-filed EPS store (data branch, eps-gaap/<cik>.json)."""
    out = {}
    for p in Path(folder).glob('*.json'):
        try:
            out[p.stem] = json.loads(p.read_text(encoding='utf-8')).get('records') or []
        except (OSError, ValueError):
            continue
    return out
