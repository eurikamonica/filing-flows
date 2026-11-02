"""At the lows and in a range — the other two regimes beside the highs (app/highs.py), for every asset of the move odds:

At the lows (an all-time low; a 52-week low; a 3-month low — the bottom of its recent range)
  low day       a day within 15% of that low with a new one in the last 63 trading days (and a year of history): running
                at its lows, like a stock that made a 52-week low last month and bounced a little.
  state         how far under its all-time high, how long since its last high of the same span (the age of the slide), new
                lows in the last 63 days, how far under its 200-day average, momentum, volatility, P/E and volume (each
                against its own history where marked, as for the highs).
  what followed the next new low (Kaplan–Meier days: the slide went on), a 10% and a 20% rebound from the lowest close
                from that day on (the days to it), the trough (the lowest close before the 10% rebound: its days and how
                much further down from that day), the rebound from that trough (how high before the next new low, or
                still going), the returns and the further falls over 3 and 12 months.
In a range (sideways over the last 63 trading days: the net move under a quarter of the range's width)
  narrow        the range's width (high ÷ low − 1) in the bottom 15% of the asset's own 63-day widths: a tight coil.
  wide          the width in its top 30%: wide swings that go nowhere.
  state         the width, its own percentile, days in the range (since the episode began: up to 10 days out of the state
                do not end it), where the price sits in it, volatility, how far from the 200-day average and the all-time
                high, P/E, volume.
  what followed the breakout: the first close above the range's high or under its low (Kaplan–Meier days to either),
                which way, the move 1 and 3 months after the breakout, how often it fell back into the middle of the
                range within a month (a false breakout), the returns and the largest rise and fall over 3 months.
Each day in a regime is an event (they overlap, so episodes and assets are counted beside the days); analogues for an
asset in a regime now: the 250 nearest days of the same kind of asset on the state both have, at most one per asset
and 21 days, none of its own from the last year. Descriptive history, not a forecast.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

import highs as HI

NEAR, RECENT, H = 0.15, 63, 252
CAP_ROWS = 500                 # days kept per asset and regime (evenly spaced; the last always): they overlap anyway
LOWS = (('atl', 'At an all-time low', None), ('52w', 'At a 52-week low', 252), ('3m', 'At a 3-month low (the bottom of its range)', 63))
RANGES = (('narrow', 'In a narrow range (a tight coil)'), ('wide', 'In a wide range (wide swings, no trend)'))
RW = 63
NARROW, WIDE, TREND = 15, 70, 0.25
GAP = 10                       # trading days out of a range state that still count as the same range
HZ = HI.HZ
K = HI.K_ANALOG
GRID = HI.GRID
LOW_FEATURES = ('age', 'lows63', 'dist', 'dd_ath', 'ext_pct', 'mom_pct', 'vol_pct', 'pe_pct', 'volu')
RANGE_FEATURES = ('width', 'width_pct', 'age', 'pos', 'dd_ath', 'ext200', 'vol_pct', 'pe_pct', 'volu')
SCALE = {'age': ('log', 1.0), 'lows63': ('lin', 8.0), 'dist': ('lin', 0.02), 'dd_ath': ('lin', 0.15), 'ext_pct': ('lin', 25.0), 'mom_pct': ('lin', 25.0),
         'vol_pct': ('lin', 25.0), 'pe_pct': ('lin', 25.0), 'volu': ('log', 0.25), 'width': ('log', 0.3), 'width_pct': ('lin', 15.0), 'pos': ('lin', 0.2),
         'ext200': ('lin', 0.08)}
P_EDGES = [0, 1, 5, 20, 50, 80, 101]
P_LABELS = ['under 1 (lowest)', '1–5', '5–20', '20–50', '50–80', '80 or more']
LOW_BUCKETS = {
    'dd_ath': ('Under its all-time high', [-1.01, -0.8, -0.6, -0.4, -0.2, 0.001], ['80% or more', '60–80%', '40–60%', '20–40%', 'under 20%']),
    'age': ('Days since its last high of the same span (the slide’s age)', [0, 21, 63, 126, 252, 504, 1e9], ['under 1 month', '1–3 months', '3–6 months', '6–12 months', '1–2 years', '2 years or more']),
    'lows63': ('New lows in the last 63 trading days', [0, 3, 6, 11, 21, 1e9], ['1–2', '3–5', '6–10', '11–20', '21 or more']),
    'ext200': ('Against its 200-day average', [-10, -0.5, -0.3, -0.15, -0.05, 10], ['50% or more under', '30–50% under', '15–30% under', '5–15% under', 'within 5% or above']),
    'mom_pct': ('12-1 month momentum, percentile of its own history', P_EDGES, P_LABELS),
    'mom_xs': ('12-1 month momentum, percentile among all companies that day', P_EDGES, P_LABELS),
    'vol_pct': ('21-day volatility, percentile of its own history', [0, 20, 40, 60, 80, 95, 101], ['under 20 (calm)', '20–40', '40–60', '60–80', '80–95', '95 or more (stormy)']),
    'pe_pct': ('Trailing P/E, percentile of its own history', P_EDGES, P_LABELS),
    'pe': ('Trailing P/E', [0, 10, 15, 25, 40, 1e9], ['under 10', '10–15', '15–25', '25–40', '40 or more']),
    'volu': ('Volume, last 3 months vs last 12', [0, 0.8, 1.0, 1.2, 1.5, 2.0, 1e9], ['under 0.8×', '0.8–1.0×', '1.0–1.2×', '1.2–1.5×', '1.5–2.0×', '2× or more']),
}
RANGE_BUCKETS = {
    'width': ('The range’s width (63-day high ÷ low − 1)', [0, 0.05, 0.10, 0.15, 0.25, 0.40, 1e9], ['under 5%', '5–10%', '10–15%', '15–25%', '25–40%', '40% or more']),
    'age': ('Trading days in the range so far', [0, 5, 21, 63, 126, 1e9], ['under 5', '5–21', '21–63', '63–126', '126 or more']),
    'pos': ('Where the price sits in the range', [-0.01, 1 / 3, 2 / 3, 1.01], ['bottom third', 'middle third', 'top third']),
    'dd_ath': ('Under its all-time high', [-1.01, -0.5, -0.2, -0.05, 0.001], ['50% or more', '20–50%', '5–20%', 'within 5%']),
    'ext200': ('Against its 200-day average', [-10, -0.1, 0, 0.1, 10], ['10% or more under', '0–10% under', '0–10% above', '10% or more above']),
    'vol_pct': ('21-day volatility, percentile of its own history', [0, 20, 40, 60, 80, 101], ['under 20 (calm)', '20–40', '40–60', '60–80', '80 or more']),
    'pe_pct': ('Trailing P/E, percentile of its own history', [0, 20, 50, 80, 101], ['under 20', '20–50', '50–80', '80 or more']),
    'volu': ('Volume, last 3 months vs last 12', [0, 0.7, 0.85, 1.0, 1.2, 1e9], ['under 0.7×', '0.7–0.85×', '0.85–1.0×', '1.0–1.2×', '1.2× or more']),
}
NOTE = ('History, not a forecast. Days in a regime overlap, so episodes and assets are given beside the days. Companies are '
        'today’s (survivors), which flatters what came after their lows; adjusted closes (dividends reinvested). P/E: price ÷ the '
        'last four first-filed quarterly diluted EPS (SEC), positive only.')
_r = HI._r


# ------------------------------------------------------------------ one asset
def rolling(c, w, fn):
    out = np.full(len(c), np.nan)
    if len(c) >= w:
        out[w - 1:] = fn(np.lib.stride_tricks.sliding_window_view(c, w), axis=1)
    return out


def common(c, raw=None, eps=None, volu=None):
    """The state variables every regime shares (highs.asset_frame's), by day."""
    n = len(c)
    lr = np.concatenate([[np.nan], np.diff(np.log(c))])
    C = {'n': n, 'dd_ath': c / np.maximum.accumulate(c) - 1, 'ext200': c / HI.rolling_mean(c, 200) - 1, 'mom': np.full(n, np.nan), 'vol': np.full(n, np.nan),
         'pe': np.full(n, np.nan), 'volu': np.asarray(volu, float) if volu is not None else np.full(n, np.nan)}
    if n > 252:
        C['mom'][252:] = c[231:n - 21] / c[:n - 252] - 1
    if n > 21:
        C['vol'][20:] = np.nanstd(np.lib.stride_tricks.sliding_window_view(lr, 21), axis=1) * math.sqrt(252)
    if eps is not None:
        px = np.asarray(raw, float) if raw is not None else c
        with np.errstate(invalid='ignore', divide='ignore'):
            pe = np.where(np.asarray(eps) > 0, px / eps, np.nan)
        pe[~((pe > 0) & (pe <= 300))] = np.nan
        C['pe'] = pe
    C['ext_pct'], C['mom_pct'], C['vol_pct'], C['pe_pct'] = HI.own_pct(C['ext200']), HI.own_pct(C['mom']), HI.own_pct(C['vol']), HI.own_pct(C['pe'])
    return C


def thin(rows, cap=CAP_ROWS):
    """At most `cap` of the rows, evenly spaced, the last one kept."""
    if len(rows) <= cap:
        return rows
    step = int(math.ceil(len(rows) / cap))
    return rows[::-1][::step][::-1]


def fwd_min(c, h):
    """The lowest close over the next h days, from each day (NaN when they are not all on file)."""
    n = len(c)
    out = np.full(n, np.nan)
    if n > h:
        out[:n - h] = np.lib.stride_tricks.sliding_window_view(c[1:], h).min(axis=1)
    return out


def _first(mask):
    """The first True of a boolean array (−1 if none)."""
    i = int(np.argmax(mask)) if len(mask) else 0
    return i if len(mask) and mask[i] else -1


def low_frame(c, L, C):
    """Low days for a lookback L (None: all-time) and what followed each: {column: values over the low days}."""
    n = len(c)
    ix = np.arange(n)
    if L is None:
        lo, hi = np.minimum.accumulate(c), np.maximum.accumulate(c)
    else:
        lo, hi = rolling(c, L, np.min), rolling(c, L, np.max)
    with np.errstate(invalid='ignore'):
        new_low = np.isfinite(lo) & (c <= lo * (1 + 1e-12))
        new_high = np.isfinite(hi) & (c >= hi * (1 - 1e-12))
        dist = c / lo - 1
    last_low, last_high = HI.prev_true(new_low), HI.prev_true(new_high)
    with np.errstate(invalid='ignore'):
        day = (dist <= NEAR) & (last_low >= 0) & (ix - last_low < RECENT) & (ix >= 252)
    cl = np.concatenate([[0], np.cumsum(new_low)])
    lows63 = cl[ix + 1] - cl[np.maximum(0, ix - 62)]
    nxt_low = HI.next_true(new_low)
    rows = thin(np.nonzero(day)[0])
    m = len(rows)
    out = {'t': rows, 'dist': dist[rows], 'lows63': lows63[rows].astype(float), 'age': np.where(last_high[rows] >= 0, rows - last_high[rows], rows).astype(float),
           'next_low': (nxt_low[rows] - rows).astype(float), 'n_left': (n - rows).astype(float)}
    for k in ('r10', 'r20', 'trough_days', 'fall', 'lows_left', 'bounce', 'bounce_days'):
        out[k] = np.full(m, np.nan)
    out['ended'], out['bounce_closed'] = np.zeros(m, bool), np.zeros(m, bool)
    for j, t in enumerate(rows):
        seg = c[t + 1:t + 1 + H]
        if not len(seg):
            out['r10'][j] = out['r20'][j] = 0
            continue
        mn = np.minimum(c[t], np.minimum.accumulate(seg))             # the lowest close from here on
        i10, i20 = _first(seg >= 1.10 * mn), _first(seg >= 1.20 * mn)
        out['r10'][j] = i10 + 1 if i10 >= 0 else len(seg)
        out['r20'][j] = i20 + 1 if i20 >= 0 else len(seg)
        if i10 < 0:
            continue
        out['ended'][j] = True
        p = t + int(np.argmin(c[t:t + 2 + i10]))                      # the trough: the lowest close before the 10% rebound
        out['trough_days'][j] = p - t
        out['fall'][j] = c[p] / c[t] - 1
        out['lows_left'][j] = cl[t + 2 + i10] - cl[t + 1]
        nl = nxt_low[p]
        end = min(nl, p + 252, n)
        out['bounce'][j] = c[p:end].max() / c[p] - 1
        out['bounce_closed'][j] = nl < n and nl <= p + 252
        out['bounce_days'][j] = int(np.argmax(c[p:end])) if end > p else np.nan
    for h in HZ:
        f = np.full(m, np.nan)
        ok = rows + h < n
        f[ok] = c[rows[ok] + h] / c[rows[ok]] - 1
        out[f'fwd{h}'] = f
    for h in (63, 252):
        out[f'fall{h}'] = fwd_min(c, h)[rows] / c[rows] - 1
    out['run'] = np.where(last_high[rows] >= 0, last_high[rows], -1)
    for k in ('dd_ath', 'ext200', 'ext_pct', 'mom', 'mom_pct', 'vol', 'vol_pct', 'pe', 'pe_pct', 'volu'):
        out[k] = np.asarray(C[k])[rows]
    out['_today'] = bool(day[n - 1])
    out['_last_low'] = int(last_low[n - 1])
    return out


def range_frame(c, C):
    """Days in a narrow or a wide range and what followed: {regime: {column: values}}."""
    n = len(c)
    ix = np.arange(n)
    mx, mn = rolling(c, RW, np.max), rolling(c, RW, np.min)
    with np.errstate(invalid='ignore', divide='ignore'):
        width = mx / mn - 1
        net = np.full(n, np.nan)
        net[RW - 1:] = np.abs(np.log(c[RW - 1:] / c[:n - RW + 1]))
        flat = net <= TREND * np.log(mx / mn)
        pos = (c - mn) / (mx - mn)
    wpct = HI.own_pct(width)
    out = {}
    for name in ('narrow', 'wide'):
        with np.errstate(invalid='ignore'):
            inr = flat & ((wpct <= NARROW) if name == 'narrow' else (wpct >= WIDE)) & (ix >= 252)
        # days in the range so far: since the episode began (a gap of up to GAP days out of the state does not end it,
        # as the width's percentile and the flatness flicker around their thresholds)
        run = np.zeros(n)
        start = np.full(n, -1)
        s0, last = -1, -10 ** 9
        for t in range(n):
            if inr[t]:
                if t - last > GAP:
                    s0 = t
                last = t
                run[t], start[t] = t - s0 + 1, s0
        rows = thin(np.nonzero(inr)[0])
        m = len(rows)
        o = {'t': rows, 'width': width[rows], 'width_pct': wpct[rows], 'pos': pos[rows], 'age': run[rows], 'run': start[rows], 'n_left': (n - rows).astype(float)}
        for k in ('brk', 'up', 'after21', 'after63', 'failed'):
            o[k] = np.full(m, np.nan)
        o['resolved'] = np.zeros(m, bool)
        for j, t in enumerate(rows):
            seg = c[t + 1:t + 1 + 252]
            if not len(seg):
                o['brk'][j] = 0
                continue
            iu, idn = _first(seg > mx[t]), _first(seg < mn[t])
            cand = [x for x in (iu, idn) if x >= 0]
            if not cand:
                o['brk'][j] = len(seg)
                continue
            i = min(cand)
            s = t + 1 + i
            o['brk'][j], o['resolved'][j], o['up'][j] = i + 1, True, 1.0 if i == iu else 0.0
            if s + 21 < n:
                o['after21'][j] = c[s + 21] / c[s] - 1
            if s + 63 < n:
                o['after63'][j] = c[s + 63] / c[s] - 1
            mid = (mx[t] + mn[t]) / 2
            nxt = c[s + 1:s + 22]
            if len(nxt) == 21:
                o['failed'][j] = float((nxt < mid).any() if i == iu else (nxt > mid).any())
        for h in HZ:
            f = np.full(m, np.nan)
            ok = rows + h < n
            f[ok] = c[rows[ok] + h] / c[rows[ok]] - 1
            o[f'fwd{h}'] = f
        o['rise63'] = -fwd_min(-c, 63)[rows] / c[rows] - 1
        o['fall63'] = fwd_min(c, 63)[rows] / c[rows] - 1
        for k in ('dd_ath', 'ext200', 'ext_pct', 'mom', 'mom_pct', 'vol', 'vol_pct', 'pe', 'pe_pct', 'volu'):
            o[k] = np.asarray(C[k])[rows]
        o['_today'] = bool(inr[n - 1])
        o['_now'] = {'width': _r(width[-1]), 'width_pct': _r(wpct[-1]), 'pos': _r(pos[-1]), 'age': int(run[-1]), 'hi': _r(mx[-1]), 'lo': _r(mn[-1]),
                     'since': int(start[-1]) if run[-1] else None, 'days_in': int(inr[max(0, int(start[-1])):].sum()) if run[-1] else 0}
        out[name] = o
    return out


# ------------------------------------------------------------------ summaries
def summarize_low(R, sel, curves=False):
    if not sel.any():
        return {'days': 0}
    n = R['n_left'][sel]
    out = {'days': int(sel.sum()), 'runs': int(len(set(zip(R['asset'][sel].tolist(), R['run'][sel].tolist())))), 'assets': int(len(set(R['asset'][sel].tolist())))}
    g = GRID if curves else None
    out['next_low'] = HI.km(R['next_low'][sel], R['next_low'][sel] < n, g)
    out['r10'] = HI.km(R['r10'][sel], R['r10'][sel] < np.minimum(n - 1, H), g)
    out['r20'] = HI.km(R['r20'][sel], R['r20'][sel] < np.minimum(n - 1, H), g)
    e = R['ended'][sel]
    out['trough_days'] = HI.q(R['trough_days'][sel][e], (0.25, 0.5, 0.75, 0.9))
    out['fall'] = HI.q(R['fall'][sel][e], (0.1, 0.25, 0.5, 0.75))
    out['lows_left'] = HI.q(R['lows_left'][sel][e], (0.25, 0.5, 0.75, 0.9))
    out['more_lows'] = _r((R['lows_left'][sel][e] > 0).mean()) if e.any() else None
    out['bounce'] = HI.q(R['bounce'][sel][e], (0.1, 0.25, 0.5, 0.75, 0.9))
    out['bounce_open'] = _r((~R['bounce_closed'][sel][e]).mean()) if e.any() else None
    for h in HZ:
        out[f'fwd{h}'] = HI.q(R[f'fwd{h}'][sel], (0.1, 0.25, 0.5, 0.75, 0.9))
    for h in (63, 252):
        out[f'fall{h}'] = HI.q(R[f'fall{h}'][sel], (0.1, 0.25, 0.5, 0.75))
    return out


def short_low(s):
    if not s or not s.get('days'):
        return {'days': 0}
    g = lambda k, f: ((s.get(k) or {}).get(f))                          # noqa: E731
    return {'days': s['days'], 'runs': s['runs'], 'assets': s['assets'], 'next_low_median': g('next_low', 'median'), 'next_low_p63': (g('next_low', 'p') or {}).get('63'),
            'r10_median': g('r10', 'median'), 'r10_p63': (g('r10', 'p') or {}).get('63'), 'r20_median': g('r20', 'median'), 'fall_median': g('fall', 'p50'),
            'bounce_median': g('bounce', 'p50'), 'fwd63': g('fwd63', 'p50'), 'fwd63_up': g('fwd63', 'up'), 'fwd252': g('fwd252', 'p50'), 'fwd252_up': g('fwd252', 'up'),
            'fall252': g('fall252', 'p50')}


def summarize_range(R, sel, curves=False):
    if not sel.any():
        return {'days': 0}
    n = R['n_left'][sel]
    out = {'days': int(sel.sum()), 'runs': int(len(set(zip(R['asset'][sel].tolist(), R['run'][sel].tolist())))), 'assets': int(len(set(R['asset'][sel].tolist())))}
    out['breakout'] = HI.km(R['brk'][sel], R['resolved'][sel], GRID if curves else None)
    res = R['resolved'][sel]
    up = R['up'][sel][res]
    out['up_first'] = _r(up.mean()) if len(up) else None
    for h in (21, 63, 126, 252):
        b = R['brk'][sel]
        seen = res & (b <= h) | (n - 1 >= h)
        out[f'within{h}'] = {'up': _r(((res & (R['up'][sel] == 1) & (b <= h)) & seen).sum() / max(1, seen.sum())),
                             'down': _r(((res & (R['up'][sel] == 0) & (b <= h)) & seen).sum() / max(1, seen.sum())), 'n': int(seen.sum())}
    for d, lab in ((1, 'up'), (0, 'down')):
        s2 = res & (R['up'][sel] == d)
        out[f'after21_{lab}'] = HI.q(R['after21'][sel][s2], (0.1, 0.25, 0.5, 0.75, 0.9))
        out[f'after63_{lab}'] = HI.q(R['after63'][sel][s2], (0.1, 0.25, 0.5, 0.75, 0.9))
        f = R['failed'][sel][s2]
        f = f[np.isfinite(f)]
        out[f'failed_{lab}'] = _r(f.mean()) if len(f) else None
    for h in HZ:
        out[f'fwd{h}'] = HI.q(R[f'fwd{h}'][sel], (0.1, 0.25, 0.5, 0.75, 0.9))
    out['rise63'] = HI.q(R['rise63'][sel], (0.25, 0.5, 0.75, 0.9))
    out['fall63'] = HI.q(R['fall63'][sel], (0.1, 0.25, 0.5, 0.75))
    return out


def short_range(s):
    if not s or not s.get('days'):
        return {'days': 0}
    g = lambda k, f: ((s.get(k) or {}).get(f))                          # noqa: E731
    return {'days': s['days'], 'runs': s['runs'], 'assets': s['assets'], 'breakout_median': g('breakout', 'median'), 'breakout_p63': (g('breakout', 'p') or {}).get('63'),
            'up_first': s.get('up_first'), 'after63_up': g('after63_up', 'p50'), 'after63_down': g('after63_down', 'p50'), 'failed_up': s.get('failed_up'),
            'failed_down': s.get('failed_down'), 'fwd63': g('fwd63', 'p50'), 'fwd63_up': g('fwd63', 'up'), 'fwd252': g('fwd252', 'p50'), 'fwd252_up': g('fwd252', 'up')}


def _z(k, v):
    how, s = SCALE[k]
    v = np.asarray(v, float)
    with np.errstate(invalid='ignore', divide='ignore'):
        return (np.log1p(np.maximum(v, 0)) if k == 'age' else np.log(np.maximum(v, 1e-6)) if how == 'log' else v) / s


def analogues(R, gsel, now, feats_all, asset, t_abs, k=K):
    feats = [f for f in feats_all if now.get(f) is not None and np.isfinite(now[f])]
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
    mm = min(len(idx), 40 * k)
    part = np.argpartition(D, mm - 1)[:mm]
    keep, taken = [], set()
    for j in part[np.argsort(D[part])]:
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


LITE_LOW = {'next_low': ('median', 'p'), 'r10': ('median', 'p'), 'r20': ('median', 'p'), 'fall': ('p50',), 'bounce': ('p50',), 'fwd63': ('p50', 'up'), 'fwd252': ('p50', 'up'),
            'fall252': ('p50',)}
LITE_RANGE = {'breakout': ('median', 'p'), 'after63_up': ('p50',), 'after63_down': ('p50',), 'fwd63': ('p50', 'up'), 'fwd252': ('p50', 'up')}


def _lite(block, keep):
    """A list row: the state and the analogues' few numbers the list shows (the rest is in the asset's own file)."""
    out = {'state': block['state']}
    A = block.get('analogues')
    if A:
        out['analogues'] = {'days': A.get('days'), **{k: {f: (A.get(k) or {}).get(f) for f in fs} for k, fs in keep.items()},
                            **{k: A[k] for k in ('up_first', 'more_lows', 'failed_up', 'failed_down') if k in A}}
    return out


# ------------------------------------------------------------------ the build
def build(data, assets, eps=None, volumes=None, raw=None, out_dir=None, verbose=True, now_max=300):
    """lows.json and ranges.json from the move odds' daily closes (the inputs of highs.build). Returns (lows doc, ranges
    doc, per-asset blocks {key: {'lows': {regime: block}, 'ranges': {regime: block}}})."""
    eps, volumes, raw = eps or {}, volumes or {}, raw or {}
    gi = {g: i for i, (g, _) in enumerate(HI.GROUPS)}
    lowR = {k: {} for k, _, _ in LOWS}
    rngR = {k: {} for k, _ in RANGES}
    meta, moms = [], {}
    for a in assets:
        key, g = a['key'], HI.KIND_GROUP.get(a.get('kind'))
        if g is None or key not in data or str(key).startswith('VIX'):
            continue
        days, c = data[key][0], np.asarray(data[key][1], float)
        if len(c) < 504 or not np.all(np.isfinite(c)) or (c <= 0).any():
            continue
        e, rd = None, None
        recs = eps.get(str(a.get('cik'))) if a.get('cik') else None
        if recs:
            e = HI.ttm_eps(days, HI.fix_splits(recs))
            if key in raw:
                dn = np.asarray(days, dtype='datetime64[D]')
                rt, rv = np.asarray(raw[key][0], dtype='datetime64[D]'), np.array([np.nan if v is None else float(v) for v in raw[key][1]], float)
                j = np.searchsorted(dn, rt)
                ok = (j < len(dn)) & np.isfinite(rv) & (rv > 0)
                ok[ok] = dn[j[ok]] == rt[ok]
                rd = np.array(c)
                if ok.any():
                    rd[j[ok]] = rv[ok]
                    j0 = int(j[ok][0])
                    rd[:j0] = c[:j0] * (rd[j0] / c[j0])
        vr = HI.volume_ratio(days, *volumes[key]) if key in volumes else None
        C = common(c, raw=rd, eps=e, volu=vr)
        ai = len(meta)
        t = len(c) - 1
        m = {'key': key, 'group': g, 'days': days, 'a': a, 't': t, 'close': float(c[-1]), 'mom': float(C['mom'][t]) if np.isfinite(C['mom'][t]) else None,
             'common': {k: _r(C[k][t]) for k in ('dd_ath', 'ext200', 'ext_pct', 'mom', 'mom_pct', 'vol', 'vol_pct', 'pe', 'pe_pct', 'volu')}, 'lows': {}, 'ranges': {}}
        for k, _, L in LOWS:
            o = low_frame(c, L, C)
            if o['_today']:
                j = len(o['t']) - 1
                m['lows'][k] = {'now': {f: float(o[f][j]) for f in LOW_FEATURES}, 'state': {**{f: _r(o[f][j]) for f in ('dist', 'lows63', 'age')},
                                'low': _r(c[-1] / (1 + o['dist'][j])),
                                'low_date': days[o['_last_low']] if o['_last_low'] >= 0 else None, 'since': days[t - int(o['age'][j])] if o['age'][j] <= t else None}}
            if len(o['t']):
                o['asset'] = np.full(len(o['t']), ai, np.int32)
                o['group'] = np.full(len(o['t']), gi[g], np.int8)
                lowR[k].setdefault('parts', []).append({kk: v for kk, v in o.items() if not kk.startswith('_')})
        rf = range_frame(c, C)
        for k, _ in RANGES:
            o = rf[k]
            if o['_today']:
                j = len(o['t']) - 1
                nw = o['_now']
                m['ranges'][k] = {'now': {f: float(o[f][j]) for f in RANGE_FEATURES}, 'state': {**nw, 'since': days[nw['since']] if nw['since'] is not None else None}}
            if len(o['t']):
                o['asset'] = np.full(len(o['t']), ai, np.int32)
                o['group'] = np.full(len(o['t']), gi[g], np.int8)
                rngR[k].setdefault('parts', []).append({kk: v for kk, v in o.items() if not kk.startswith('_')})
        if g == 'companies':
            moms[ai] = C['mom'].astype(np.float32)
        meta.append(m)
    if not meta:
        return None, None, {}

    def cat(parts):
        keys = parts[0].keys()
        return {k: np.concatenate([p[k] for p in parts]) for k in keys}
    LR = {k: cat(v['parts']) for k, v in lowR.items() if v.get('parts')}
    RR = {k: cat(v['parts']) for k, v in rngR.items() if v.get('parts')}
    # momentum among all companies that day, for the lows (the factor's rank): every company's 12-1 momentum on one grid
    for k, R in LR.items():
        R['mom_xs'] = np.full(len(R['t']), np.nan)
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
        S = np.sort(M, axis=0)
        del M

        def xs(day, v):
            c_ = gpos.get(day)
            if c_ is None or v is None or not np.isfinite(v) or cnt[c_] < 50:
                return np.nan
            return 100.0 * np.searchsorted(S[:cnt[c_], c_], v, side='right') / cnt[c_]
        for R in LR.values():
            for j in np.nonzero(R['group'] == gi['companies'])[0]:
                R['mom_xs'][j] = xs(meta[int(R['asset'][j])]['days'][int(R['t'][j])], R['mom'][j])
        for m in meta:
            if m['group'] == 'companies':
                v = xs(m['days'][m['t']], m['mom'])
                m['common']['mom_xs'] = _r(v, 2) if np.isfinite(v) else None
        del S
    now_t = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    lows = {'schema': 'lows.v1', 'generated_at': now_t, 'params': {'near': NEAR, 'recent': RECENT, 'horizon': H, 'grid': GRID, 'horizons': list(HZ)},
            'regimes': {}, 'now': {}, 'note': NOTE}
    ranges = {'schema': 'ranges.v1', 'generated_at': now_t, 'params': {'window': RW, 'narrow_pct': NARROW, 'wide_pct': WIDE, 'trend': TREND, 'grid': GRID, 'horizons': list(HZ)},
              'regimes': {}, 'now': {}, 'note': NOTE.replace('after their lows', 'after these days')}
    blocks = {}
    for k, label, _ in LOWS:
        R = LR.get(k)
        if R is None:
            continue
        REG = {'label': label, 'groups': {}}
        for g, glab in HI.GROUPS:
            gsel = R['group'] == gi[g]
            if not gsel.any():
                continue
            G = {'label': glab, 'base': summarize_low(R, gsel, curves=True), 'buckets': {}}
            for f, (title, edges, labels) in LOW_BUCKETS.items():
                v = R.get(f)
                if v is None or not np.isfinite(v[gsel]).any():
                    continue
                G['buckets'][f] = {'title': title, 'rows': [{'label': lab, **short_low(summarize_low(R, gsel & np.isfinite(v) & (v >= lo) & (v < hi)))}
                                                            for lo, hi, lab in zip(edges[:-1], edges[1:], labels)]}
            REG['groups'][g] = G
        lows['regimes'][k] = REG
        lst = []
        for ai, m in enumerate(meta):
            if k not in m['lows']:
                continue
            x = m['lows'][k]
            now = {**x['now'], **{f: m['common'][f] if m['common'].get(f) is not None else np.nan for f in ('dd_ath', 'ext_pct', 'mom_pct', 'vol_pct', 'pe_pct', 'volu')}}
            sel, feats, keep = analogues(R, R['group'] == gi[m['group']], now, LOW_FEATURES, ai, m['t'])
            b = {'state': {**m['common'], **x['state'], 'date': m['days'][m['t']], 'close': _r(m['close'])}}
            if sel is not None:
                b['analogues'] = {'features': feats, **summarize_low(R, sel, curves=True),
                                  'nearest': [{'key': meta[int(R['asset'][j])]['key'], 'date': meta[int(R['asset'][j])]['days'][int(R['t'][j])], 'age': _r(R['age'][j], 0),
                                               'dd_ath': _r(R['dd_ath'][j]), 'r10': _r(R['r10'][j], 0) if R['ended'][j] else None, 'fall': _r(R['fall'][j]),
                                               'bounce': _r(R['bounce'][j]), 'fwd252': _r(R['fwd252'][j]), 'seen': int(min(R['n_left'][j] - 1, H))} for j in keep[:12]]}
            blocks.setdefault(m['key'], {}).setdefault('lows', {})[k] = b
            lst.append({'key': m['key'], 'name': m['a'].get('name'), 'kind': m['a'].get('kind'), 'group': m['group'], 'sector': m['a'].get('sector'), **_lite(b, LITE_LOW)})
        lst.sort(key=lambda r: ((r['state'].get('dd_ath') or 0), r['key']))
        lows['now'][k] = lst[:now_max]
    for k, label in RANGES:
        R = RR.get(k)
        if R is None:
            continue
        REG = {'label': label, 'groups': {}}
        for g, glab in HI.GROUPS:
            gsel = R['group'] == gi[g]
            if not gsel.any():
                continue
            G = {'label': glab, 'base': summarize_range(R, gsel, curves=True), 'buckets': {}}
            for f, (title, edges, labels) in RANGE_BUCKETS.items():
                v = R.get(f)
                if v is None or not np.isfinite(v[gsel]).any():
                    continue
                G['buckets'][f] = {'title': title, 'rows': [{'label': lab, **short_range(summarize_range(R, gsel & np.isfinite(v) & (v >= lo) & (v < hi)))}
                                                            for lo, hi, lab in zip(edges[:-1], edges[1:], labels)]}
            REG['groups'][g] = G
        ranges['regimes'][k] = REG
        lst = []
        for ai, m in enumerate(meta):
            if k not in m['ranges']:
                continue
            x = m['ranges'][k]
            now = {**x['now'], **{f: m['common'][f] if m['common'].get(f) is not None else np.nan for f in ('dd_ath', 'ext200', 'vol_pct', 'pe_pct', 'volu')}}
            sel, feats, keep = analogues(R, R['group'] == gi[m['group']], now, RANGE_FEATURES, ai, m['t'])
            b = {'state': {**m['common'], **x['state'], 'date': m['days'][m['t']], 'close': _r(m['close'])}}
            if sel is not None:
                b['analogues'] = {'features': feats, **summarize_range(R, sel, curves=True),
                                  'nearest': [{'key': meta[int(R['asset'][j])]['key'], 'date': meta[int(R['asset'][j])]['days'][int(R['t'][j])], 'width': _r(R['width'][j]),
                                               'age': _r(R['age'][j], 0), 'brk': _r(R['brk'][j], 0) if R['resolved'][j] else None,
                                               'up': None if not R['resolved'][j] else bool(R['up'][j]), 'after63': _r(R['after63'][j]), 'fwd252': _r(R['fwd252'][j]), 'seen': int(min(R['n_left'][j] - 1, 252))} for j in keep[:12]]}
            blocks.setdefault(m['key'], {}).setdefault('ranges', {})[k] = b
            lst.append({'key': m['key'], 'name': m['a'].get('name'), 'kind': m['a'].get('kind'), 'group': m['group'], 'sector': m['a'].get('sector'), **_lite(b, LITE_RANGE)})
        lst.sort(key=lambda r: ((r['state'].get('width') or 0) * (1 if k == 'narrow' else -1), r['key']))
        ranges['now'][k] = lst[:now_max]
    if out_dir:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / 'lows.json').write_text(json.dumps(lows, separators=(',', ':'), allow_nan=False), encoding='utf-8')
        (Path(out_dir) / 'ranges.json').write_text(json.dumps(ranges, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    if verbose:
        print('lows:', {k: (v['groups'].get('companies') or {}).get('base', {}).get('days') for k, v in lows['regimes'].items()}, {k: len(v) for k, v in lows['now'].items()},
              'ranges:', {k: (v['groups'].get('companies') or {}).get('base', {}).get('days') for k, v in ranges['regimes'].items()}, {k: len(v) for k, v in ranges['now'].items()}, flush=True)
    return lows, ranges, blocks
