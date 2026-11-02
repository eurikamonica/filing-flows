"""Rotation research on the Relative Rotation Graph: how often lines cross each quadrant line and how often they turn
back first (the "resistance" of the 100 line), whether lagging lines rebound — how often, how fast, how deep they go
first and what the price did after — how long lines stay in a quadrant, which way they turn, how long a full loop takes,
and what followed each quadrant. Descriptive history, never a forecast; the hub's Rotation research view and the RRG
chart's research panel (docs/rrg-lab.js computes the same numbers for the lines on a chart).

The RRG is the chart's formula (rrg.js, transition_rrg.rrg_states) with its parameters per frequency:
  weekly   RS smoothed over 4 weeks, trend window n = 14 weeks, scaled by the last max(52, 3n) weeks (≥ 26 on file)
  daily    RS smoothed over 5 trading days, n = 21 days, scaled by the last max(252, 3n) days (≥ 126 on file)

Groups
  weekly (rotation history, public/rrg-research.json, built after the transition model): sector ETFs, style / size /
          asset ETFs, the index ETFs (QQQ, DIA, IWM, MDY, RSP), the site's sectors, the industries, the companies against
          SPY (counted only while liquid: ≥ $3 and ≥ $10M a week) and the companies against their industry without
          themselves;
  daily   (move-odds bars, public/moves/rrg-research-daily.json, built with the move odds): sector ETFs, style / index
          ETFs, countries, bonds and commodities, industry and theme ETFs, the SIC industries (equal-weight composites
          of today's companies) and the companies (today's valued companies) — all against SPY, from 2005.

What is counted (period = a week or a trading day; quadrants 0 Leading, 1 Weakening, 2 Lagging, 3 Improving)
  transitions   where a line stands h periods after each quadrant.
  boundaries    an approach: a line in the quadrant before the line, within NEAR (one standard unit) of 100 and moving
                toward it (the first period of each such run). Crossed within h: the coordinate passed 100 within h
                periods; turned back: it did not ("resistance"). Also where it landed, how long it took, and the shares
                by approach speed (slow under 0.25 units a period, fast 0.5 or more). The four clockwise lines and the
                two counter-clockwise ones (Weakening → Leading, a re-acceleration; Improving → Lagging, a failed rebound).
  lagging       every entry into Lagging: reached Improving / Leading / back to Weakening within h, how many periods to
                Improving, the lowest RS-Ratio of the spell, and the forward return against the benchmark and of the
                line itself; and every lagging line-period by depth (100 − RS-Ratio: under 1, 1–2, 2 or more) and the
                direction of RS-Momentum, with its share reaching Improving and its forward return.
  quadrants     forward returns (against the benchmark and the line's own) after each quadrant, and after any.
  dwell, direction, cycles: completed runs in each quadrant; quadrant changes clockwise, counter-clockwise or across;
                the periods from one entry into Leading to the next after a visit to Lagging.
A period counts when the line's RRG point is defined; a horizon counts an origin only when the outcome was observed
(no gap and not past the end of the data). Accumulated chunk by chunk, so the medians come from fine histograms
(0.1% for returns).
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np

H_W = (1, 4, 13, 26)
H_D = (1, 5, 21, 63)
NEAR = 1.0
SPEED = (0.25, 0.5)
DEPTH = (1.0, 2.0)
CAP = 1300                       # the longest duration counted, periods
QN = ('leading', 'weakening', 'lagging', 'improving')
# key, from quadrant, to quadrant, axis, sign: +1 when the coordinate rises through 100
BOUNDS = (('improving_to_leading', 3, 0, 'x', 1), ('leading_to_weakening', 0, 1, 'y', -1),
          ('weakening_to_lagging', 1, 2, 'x', -1), ('lagging_to_improving', 2, 3, 'y', 1),
          ('weakening_to_leading', 1, 0, 'y', 1), ('improving_to_lagging', 3, 2, 'y', -1))
PARAMS = {'w': {'sh': 4, 'n': 14, 'long': 52, 'min_norm': 26, 'h': H_W, 'unit': 'weeks'},
          'd': {'sh': 5, 'n': 21, 'long': 252, 'min_norm': 126, 'h': H_D, 'unit': 'trading days'}}


# ------------------------------------------------------------------ the RRG, any frequency
def ema(A, span, need=None):
    """Row-wise exponential average with the browser's resets (a missing value restarts it)."""
    al = 2 / (span + 1)
    need = min(span, 6) if need is None else need
    L, W = A.shape
    out = np.full((L, W), np.nan)
    m = np.zeros(L)
    c = np.zeros(L, int)
    for t in range(W):
        v = A[:, t]
        fin = np.isfinite(v)
        m = np.where(fin, np.where(c == 0, v, m + al * (v - m)), 0.0)
        c = np.where(fin, c + 1, 0)
        out[:, t] = np.where(fin & (c >= need), m, np.nan)
    return out


def states(RS, n=14, sh=4, long=None, min_norm=26):
    """RS-Ratio x and RS-Momentum y (lines × periods) and the states behind them; transition_rrg.rrg_states with the
    smoothing, the scaling window and its minimum as parameters (long defaults to max(52, 3n))."""
    long = max(52, 3 * n) if long is None else max(long, 3 * n)
    s_ = ema(RS, sh)
    t_ = ema(s_, n)
    ok = np.isfinite(s_) & np.isfinite(t_) & (t_ != 0)
    with np.errstate(divide='ignore', invalid='ignore'):
        dev = np.where(ok, 100 * (s_ / np.where(ok, t_, 1) - 1), np.nan)
    d1 = np.full(dev.shape, np.nan)
    d1[:, 1:] = dev[:, 1:] - dev[:, :-1]
    roc = ema(d1, sh)

    def norm(A):
        fin = np.isfinite(A)
        sq = np.where(fin, A * A, 0.0)
        cs = np.concatenate([np.zeros((A.shape[0], 1)), np.cumsum(sq, 1)], 1)
        cn = np.concatenate([np.zeros((A.shape[0], 1), int), np.cumsum(fin, 1)], 1)
        k = np.arange(A.shape[1])
        lo = np.maximum(0, k - long + 1)
        m = cn[:, k + 1] - cn[:, lo]
        s2 = cs[:, k + 1] - cs[:, lo]
        good = fin & (m >= min(long, min_norm)) & (s2 > 0)
        with np.errstate(divide='ignore', invalid='ignore'):
            return np.where(good, 100 + A / np.sqrt(s2 / np.maximum(m, 1)), np.nan)
    x = norm(dev)
    y = norm(roc)
    y[~np.isfinite(x)] = np.nan
    return {'x': x, 'y': y, 's': s_, 't': t_, 'dev': dev, 'roc': roc, 'sh': sh, 'n': n, 'long': long}


def quadrants(x, y):
    """0 Leading, 1 Weakening, 2 Lagging, 3 Improving; −1 where undefined."""
    q = np.where(x >= 100, np.where(y >= 100, 0, 1), np.where(y < 100, 2, 3))
    return np.where(np.isfinite(x) & np.isfinite(y), q, -1)


# ------------------------------------------------------------------ accumulators
class Hist:
    """Durations in whole periods, 0 … CAP."""

    def __init__(self):
        self.c = np.zeros(CAP + 1, np.int64)

    def add(self, v):
        v = np.asarray(v, int).ravel()
        v = v[(v >= 0)]
        self.c += np.bincount(np.minimum(v, CAP), minlength=CAP + 1)[:CAP + 1]

    def summary(self):
        n = int(self.c.sum())
        if not n:
            return {'n': 0}
        cum = np.cumsum(self.c)
        q = lambda p: int(np.searchsorted(cum, p * n))
        mean = float((self.c * np.arange(CAP + 1)).sum() / n)
        return {'n': n, 'median': q(0.5), 'p25': q(0.25), 'p75': q(0.75), 'mean': round(mean, 2)}


class RHist:
    """Log returns: 0.1% bins over ±100% (the rest at the ends), with exact sums and shares above zero."""
    W, LIM = 0.001, 1.0

    def __init__(self):
        self.nb = int(round(2 * self.LIM / self.W)) + 1
        self.c = np.zeros(self.nb, np.int64)
        self.n = 0
        self.s = 0.0
        self.up = 0

    def add(self, v):
        v = np.asarray(v, float).ravel()
        v = v[np.isfinite(v)]
        if not len(v):
            return
        b = np.clip(np.rint((v + self.LIM) / self.W).astype(int), 0, self.nb - 1)
        self.c += np.bincount(b, minlength=self.nb)
        self.n += len(v)
        self.s += float(v.sum())
        self.up += int((v > 0).sum())

    def summary(self):
        if not self.n:
            return {'n': 0}
        cum = np.cumsum(self.c)
        q = lambda p: float(np.expm1(np.searchsorted(cum, p * self.n) * self.W - self.LIM))
        return {'n': int(self.n), 'median': round(q(0.5), 4), 'p25': round(q(0.25), 4), 'p75': round(q(0.75), 4),
                'mean': round(float(np.expm1(self.s / self.n)), 4), 'up': round(self.up / self.n, 4)}


def _next_true(cond, defined):
    """For each period t, the first s ≥ t with cond[s] reached through defined periods only (W + 10**6 if none)."""
    L, W = cond.shape
    INF = W + 10 ** 6
    out = np.full((L, W), INF, np.int64)
    nxt = np.full(L, INF, np.int64)
    for t in range(W - 1, -1, -1):
        nxt = np.where(defined[:, t], np.where(cond[:, t], t, nxt), INF)
        out[:, t] = nxt
    return out


def _run_end(defined):
    """For each defined period, the last period of its run of defined periods (−1 where undefined)."""
    L, W = defined.shape
    out = np.full((L, W), -1, np.int64)
    end = np.full(L, -1, np.int64)
    for t in range(W - 1, -1, -1):
        end = np.where(defined[:, t], np.where(end >= 0, end, t), -1)
        if t + 1 < W:
            end = np.where(defined[:, t] & ~defined[:, t + 1], t, end)
        out[:, t] = end
    return out


def _forward(LC, h):
    """log level h periods on minus now (NaN past the end)."""
    out = np.full(LC.shape, np.nan)
    if h < LC.shape[1]:
        out[:, :-h] = LC[:, h:] - LC[:, :-h]
    return out


class Research:
    """One group's numbers, accumulated over chunks of lines that share a grid."""

    def __init__(self, horizons, unit):
        self.H, self.unit = tuple(horizons), unit
        self.lines = 0
        self.first = self.last = None
        self.trans = {h: np.zeros((4, 4), np.int64) for h in self.H}
        self.bound = {b[0]: {'episodes': 0, 'crossed': {h: [0, 0] for h in self.H}, 'landed': [0, 0], 'time': Hist(),
                             'speed': [[0, 0, 0] for _ in range(3)]} for b in BOUNDS}
        self.lag = {'entries': 0, 'improving': {h: [0, 0] for h in self.H}, 'leading': {h: [0, 0] for h in self.H},
                    'weakening': {h: [0, 0] for h in self.H}, 'time': Hist(), 'depth': RHist(),
                    'rel': {h: RHist() for h in self.H}, 'abs': {h: RHist() for h in self.H},
                    'states': {(d, u): {'n': 0, 'improving': {h: [0, 0] for h in self.H}, 'rel': RHist()}
                               for d in range(3) for u in range(2)}}
        self.quad_rel = {q: {h: RHist() for h in self.H} for q in range(5)}
        self.quad_abs = {q: {h: RHist() for h in self.H} for q in range(5)}
        self.dwell = {q: Hist() for q in range(4)}
        self.dirn = [0, 0, 0]
        self.cycle = Hist()

    def add(self, x, y, C, B, days, ok=None):
        """x, y (lines × periods) from states(); C the lines' own closes, B their benchmarks' (same shape; NaN allowed);
        days the period dates; ok an optional mask of the periods that may start a count (liquid companies)."""
        if not x.shape[0]:
            return
        L, W = x.shape
        q = quadrants(x, y)
        D = q >= 0
        okm = D if ok is None else (D & ok)
        has = D.any(1)
        self.lines += int(has.sum())
        if has.any():
            f, l = days[np.argmax(D.any(0))], days[W - 1 - np.argmax(D.any(0)[::-1])]
            self.first = str(f)[:10] if self.first is None else min(self.first, str(f)[:10])
            self.last = str(l)[:10] if self.last is None else max(self.last, str(l)[:10])
        with np.errstate(divide='ignore', invalid='ignore'):
            LC = np.where((C > 0) & np.isfinite(C), np.log(C), np.nan)
            LB = np.where((B > 0) & np.isfinite(B), np.log(B), np.nan)
        LR = LC - LB
        end = _run_end(D)
        T = np.arange(W)[None, :]
        Hmax = max(self.H)
        nq = [_next_true(q == k, D) for k in range(4)]
        # transitions and forward returns by quadrant
        for h in self.H:
            if h >= W:
                continue
            a, b = q[:, :-h], q[:, h:]
            m = okm[:, :-h] & (b >= 0) & (end[:, :-h] >= T[:, :-h] + h)
            np.add.at(self.trans[h], (a[m], b[m]), 1)
            fr, fa = _forward(LR, h), _forward(LC, h)
            for k in range(4):
                sel = okm & (q == k)
                self.quad_rel[k][h].add(fr[sel])
                self.quad_abs[k][h].add(fa[sel])
            self.quad_rel[4][h].add(fr[okm])
            self.quad_abs[4][h].add(fa[okm])
        # boundaries: the first period of each near-and-approaching run
        prev = np.full((L, W), np.nan)
        for name, src, dst, ax, sg in BOUNDS:
            c = x if ax == 'x' else y
            prev[:] = np.nan
            prev[:, 1:] = c[:, :-1]
            dist = sg * (100 - c)
            step = sg * (c - prev)
            ev = (q == src) & (dist > 0) & (dist <= NEAR) & (step > 0)
            start = ev.copy()
            start[:, 1:] &= ~ev[:, :-1]
            start &= okm
            side = (c >= 100) if sg > 0 else (c < 100)
            nxt = _next_true(side, np.isfinite(c))
            fst = np.full((L, W), 10 ** 9, np.int64)
            fst[:, :-1] = nxt[:, 1:]                       # the first s > t on the far side
            ii, tt = np.nonzero(start)
            B_ = self.bound[name]
            B_['episodes'] += len(ii)
            if not len(ii):
                continue
            tc = fst[ii, tt] - tt                          # periods to the crossing (huge: never)
            obs = end[ii, tt] - tt                         # periods observed after t
            for h in self.H:
                crossed = tc <= h
                seen = crossed | (obs >= h)
                B_['crossed'][h][0] += int((crossed & seen).sum())
                B_['crossed'][h][1] += int(seen.sum())
            cx = tc <= Hmax
            if cx.any():
                B_['time'].add(tc[cx])
                land = q[ii[cx], np.minimum(fst[ii[cx], tt[cx]], W - 1)]
                B_['landed'][0] += int((land == dst).sum())
                B_['landed'][1] += int(len(land))
            sp = np.abs(step[ii, tt])
            band = np.where(sp < SPEED[0], 0, np.where(sp < SPEED[1], 1, 2))
            hs = self.H[1] if len(self.H) > 1 else self.H[0]
            crossed_m, seen_m = tc <= hs, (tc <= hs) | (obs >= hs)
            for k in range(3):
                sel = band == k
                B_['speed'][k][0] += int(sel.sum())
                B_['speed'][k][1] += int((crossed_m & seen_m & sel).sum())
                B_['speed'][k][2] += int((seen_m & sel).sum())
        # lagging: entries and every lagging period
        ent = np.zeros((L, W), bool)
        ent[:, 1:] = (q[:, 1:] == 2) & (q[:, :-1] >= 0) & (q[:, :-1] != 2)
        ent &= okm
        ii, tt = np.nonzero(ent)
        G = self.lag
        G['entries'] += len(ii)
        if len(ii):
            obs = end[ii, tt] - tt
            for key, k in (('improving', 3), ('leading', 0), ('weakening', 1)):
                tk = nq[k][ii, tt] - tt
                for h in self.H:
                    hit = tk <= h
                    seen = hit | (obs >= h)
                    G[key][h][0] += int((hit & seen).sum())
                    G[key][h][1] += int(seen.sum())
                if key == 'improving':
                    G['time'].add(tk[tk <= Hmax])
            # the lowest RS-Ratio of the spell (to its exit, at most Hmax periods)
            ext = np.minimum.reduce([nq[k][ii, tt] for k in (0, 1, 3)])
            lim = np.minimum(np.minimum(ext - 1, end[ii, tt]), tt + Hmax)
            lows = np.array([np.nanmin(x[i, t:lv + 1]) if lv >= t else np.nan for i, t, lv in zip(ii, tt, lim)])
            G['depth'].add(np.log((lows) / 100))             # stored as a log ratio: the summary turns it back
            for h in self.H:
                G['rel'][h].add(_forward(LR, h)[ii, tt])
                G['abs'][h].add(_forward(LC, h)[ii, tt])
        lagm = okm & (q == 2)
        if lagm.any():
            prevy = np.full((L, W), np.nan)
            prevy[:, 1:] = y[:, :-1]
            depth = np.where(100 - x < DEPTH[0], 0, np.where(100 - x < DEPTH[1], 1, 2))
            up = (y >= prevy).astype(int)
            hm = self.H[len(self.H) // 2]
            fr = _forward(LR, hm)
            ti = nq[3] - T
            obs = end - T
            for d in range(3):
                for u in range(2):
                    sel = lagm & (depth == d) & (up == u) & np.isfinite(prevy)
                    S = G['states'][(d, u)]
                    S['n'] += int(sel.sum())
                    for h in self.H:
                        hit = (ti <= h) & sel
                        seen = sel & ((ti <= h) | (obs >= h))
                        S['improving'][h][0] += int((hit & seen).sum())
                        S['improving'][h][1] += int(seen.sum())
                    S['rel'].add(fr[sel])
        # dwell, direction, cycles
        for i in range(L):
            qi, di = q[i], D[i]
            idx = np.nonzero(di)[0]
            if len(idx) < 2:
                continue
            seg = np.split(idx, np.nonzero(np.diff(idx) > 1)[0] + 1)
            for s in seg:
                qs = qi[s]
                ch = np.nonzero(np.diff(qs))[0]
                if len(ch):
                    d = (qs[ch + 1] - qs[ch]) % 4
                    self.dirn[0] += int((d == 1).sum())
                    self.dirn[1] += int((d == 3).sum())
                    self.dirn[2] += int((d == 2).sum())
                    bnd = np.concatenate([[0], ch + 1, [len(qs)]])
                    for a, b in zip(bnd[1:-2], bnd[2:-1]):    # completed runs: a change on both sides
                        self.dwell[int(qs[a])].add([b - a])
                entries = [s[0] + j for j in range(1, len(qs)) if qs[j] == 0 and qs[j - 1] != 0]
                for a, b in zip(entries, entries[1:]):
                    if (qi[a:b] == 2).any():
                        self.cycle.add([b - a])

    def to_json(self):
        pr = lambda c: {'hits': int(c[0]), 'n': int(c[1]), 'share': round(c[0] / c[1], 4) if c[1] else None}
        H = [str(h) for h in self.H]
        hm = self.H[len(self.H) // 2]
        hs = self.H[1] if len(self.H) > 1 else self.H[0]
        out = {'lines': self.lines, 'from': self.first, 'to': self.last, 'unit': self.unit, 'horizons': list(self.H),
               'transitions': {str(h): self.trans[h].tolist() for h in self.H}}
        out['boundaries'] = []
        for name, src, dst, ax, sg in BOUNDS:
            B_ = self.bound[name]
            out['boundaries'].append({'key': name, 'from': QN[src], 'to': QN[dst], 'axis': 'RS-Ratio' if ax == 'x' else 'RS-Momentum',
                                      'rising': sg > 0, 'episodes': B_['episodes'], 'crossed': {str(h): pr(B_['crossed'][h]) for h in self.H},
                                      'landed_in_target': pr(B_['landed']), 'periods_to_cross': B_['time'].summary(),
                                      'by_speed': [{'speed': s, 'episodes': v[0], 'crossed': pr(v[1:]), 'horizon': hs}
                                                   for s, v in zip(('slow', 'medium', 'fast'), B_['speed'])]})
        G = self.lag
        dep = G['depth'].summary()
        if dep.get('n'):
            dep = {k: (round(100 * (1 + v), 3) if k in ('median', 'p25', 'p75', 'mean') else v) for k, v in dep.items() if k != 'up'}
        out['lagging'] = {'entries': G['entries'], **{k: {h: pr(G[k][int(h)]) for h in H} for k in ('improving', 'leading', 'weakening')},
                          'periods_to_improving': G['time'].summary(), 'lowest_rs_ratio': dep,
                          'forward_vs_benchmark': {h: G['rel'][int(h)].summary() for h in H},
                          'forward_own': {h: G['abs'][int(h)].summary() for h in H},
                          'states': [{'depth': ('under 1', '1 to 2', '2 or more')[d], 'momentum': ('falling', 'rising')[u],
                                      'n': S['n'], 'improving': {h: pr(S['improving'][int(h)]) for h in H},
                                      'forward_vs_benchmark': {str(hm): S['rel'].summary()}}
                                     for (d, u), S in G['states'].items()]}
        out['quadrants'] = {'forward_vs_benchmark': {(QN + ('any',))[k]: {h: self.quad_rel[k][int(h)].summary() for h in H} for k in range(5)},
                            'forward_own': {(QN + ('any',))[k]: {h: self.quad_abs[k][int(h)].summary() for h in H} for k in range(5)}}
        out['dwell'] = {QN[k]: self.dwell[k].summary() for k in range(4)}
        tot = sum(self.dirn)
        out['direction'] = {'changes': tot, 'clockwise': round(self.dirn[0] / tot, 4) if tot else None,
                            'counter_clockwise': round(self.dirn[1] / tot, 4) if tot else None,
                            'across': round(self.dirn[2] / tot, 4) if tot else None}
        out['cycles'] = self.cycle.summary()
        return out


def research(x, y, C, B, days, horizons=H_W, unit='weeks', ok=None):
    """One panel's research as JSON (a single chunk)."""
    R = Research(horizons, unit)
    R.add(x, y, C, B, days, ok)
    return R.to_json()


# ------------------------------------------------------------------ weekly: the rotation history
INDEX_ETFS = ('QQQ', 'DIA', 'IWM', 'MDY', 'RSP')
NOTE = ('History, not a forecast: counts over every line-period on file (overlapping windows, so lines and periods are '
        'not independent). Companies and industries are today\'s (survivors), which flatters what came after weak spells.')


def build_weekly(public, L=None, out_name='rrg-research.json', verbose=True):
    """public/rrg-research.json from the rotation history (transition_rrg.load's arrays when given)."""
    import transition_rrg as TR
    public = Path(public)
    L = L or TR.load(public)
    days, spy = L['days'], L['spy']
    P = PARAMS['w']
    D = json.loads((public / 'rrg.json').read_text(encoding='utf-8'))
    grp = {s['id']: s.get('group') for s in D.get('series') or []}

    def rel(A, Bm):
        with np.errstate(divide='ignore', invalid='ignore'):
            return np.where((Bm > 0) & np.isfinite(A), 100 * A / Bm, np.nan)

    def run(A, Bm, ok=None, chunk=500):
        if not len(A):
            return None
        R = Research(P['h'], P['unit'])
        for i in range(0, len(A), chunk):
            a = A[i:i + chunk]
            b = np.broadcast_to(Bm, A.shape)[i:i + chunk] if Bm.shape[0] == 1 else Bm[i:i + chunk]
            S = states(rel(a, b), P['n'], P['sh'], P['long'], P['min_norm'])
            R.add(S['x'], S['y'], a, np.broadcast_to(b, a.shape), days, None if ok is None else ok[i:i + chunk])
        return R.to_json()
    groups = {}
    E, ids = L['E'], L['etf_ids']
    pick = lambda f: np.array([E[i] for i, s in enumerate(ids) if f(s)]) if len(E) else np.zeros((0, len(days)))
    specs = [('sectors', 'Sector ETFs against the S&P 500', pick(lambda s: grp.get(s) == 'sector-etf'), spy[None], None),
             ('index_etfs', 'Index ETFs against the S&P 500 (QQQ, DIA, IWM, MDY, RSP)', pick(lambda s: s in INDEX_ETFS), spy[None], None),
             ('styles', 'Style, size and asset ETFs against the S&P 500', pick(lambda s: grp.get(s) == 'style-etf' and s not in INDEX_ETFS), spy[None], None),
             ('site_sectors', 'The site\'s sectors (its companies) against the S&P 500', pick(lambda s: grp.get(s) == 'site-sector'), spy[None], None),
             ('industries', 'Industries against the S&P 500', L['I'], spy[None], None)]
    ok = TR.liquid(L['C'], L['V']) if len(L['C']) else None
    specs.append(('companies', 'Companies against the S&P 500 (counted while liquid)', L['C'], spy[None], ok))
    for key, label, A, Bm, mask in specs:
        try:
            r = run(A, Bm, mask)
        except Exception as exc:                          # one group never loses the others
            print('rrg research', key, type(exc).__name__, exc, flush=True)
            r = None
        if r and r['lines']:
            groups[key] = {'label': label, **r}
    if len(L['C']):
        has = np.isfinite(L['BX']).any(1)
        if has.any():
            try:
                r = run(L['C'][has], L['BX'][has], ok[has])
                if r and r['lines']:
                    groups['companies_vs_industry'] = {'label': 'Companies against their industry without themselves (while liquid)', **r}
            except Exception as exc:
                print('rrg research companies_vs_industry', type(exc).__name__, exc, flush=True)
    doc = {'schema': 'rrg_research.v1', 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
           'freq': 'w', 'rrg': {k: P[k] for k in ('sh', 'n', 'long', 'min_norm')}, 'near': NEAR, 'speed': list(SPEED),
           'depth': list(DEPTH), 'groups': groups, 'note': NOTE}
    (public / out_name).write_text(json.dumps(doc, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    if verbose:
        print('rrg research (weekly):', {k: v['lines'] for k, v in groups.items()}, flush=True)
    return doc


# ------------------------------------------------------------------ daily: the move-odds bars
DAILY_FROM = '2005-01-03'
ORDER_D = ('sectors', 'index_etfs', 'styles', 'world', 'bonds_commodities', 'industry_etfs', 'industries', 'companies')


def build_daily(data, assets, out_path, chunk=400, verbose=True):
    """public/moves/rrg-research-daily.json from moves.build's daily closes: data {key: (days, closes, last)} and its
    asset list (key, kind, group)."""
    if 'SPY' not in data:
        return None
    sd, sc = data['SPY'][0], data['SPY'][1]
    grid = [d for d in sd if d >= DAILY_FROM]
    if len(grid) < 600:
        return None
    pos = {d: i for i, d in enumerate(grid)}
    W = len(grid)
    days = np.array(grid, dtype='datetime64[D]')

    def row(key, fill=5):
        a = np.full(W, np.nan)
        ds, cs = data[key][0], data[key][1]
        for d, c in zip(ds, cs):
            i = pos.get(d)
            if i is not None:
                a[i] = c
        fin = np.nonzero(np.isfinite(a))[0]           # a missing day inside the asset's range: the close before (≤ 5 days)
        if len(fin):
            gap = 0
            for i in range(fin[0] + 1, fin[-1] + 1):
                if np.isfinite(a[i]):
                    gap = 0
                elif gap < fill:
                    a[i] = a[i - 1]
                    gap += 1
        return a
    spy = row('SPY')
    P = PARAMS['d']
    by = {}
    for a in assets:
        k, kind, g = a['key'], a.get('kind'), a.get('group')
        if k not in data or k == 'SPY':
            continue
        if kind == 'sector':
            by.setdefault('sectors', []).append(k)
        elif k in INDEX_ETFS:
            by.setdefault('index_etfs', []).append(k)
        elif kind in ('style', 'etf') and g == 'style':
            by.setdefault('styles', []).append(k)
        elif kind in ('style', 'etf') and g in ('broad', 'country'):
            by.setdefault('world', []).append(k)
        elif kind in ('style', 'etf') and g in ('bonds', 'commodities'):
            by.setdefault('bonds_commodities', []).append(k)
        elif kind in ('style', 'etf') and g == 'industry':
            by.setdefault('industry_etfs', []).append(k)
        elif kind == 'industry' and len(str(k)) == 8 and str(k).startswith('SIC-'):
            by.setdefault('industries', []).append(k)
        elif kind == 'stock':
            by.setdefault('companies', []).append(k)
    labels = {'sectors': 'Sector ETFs against the S&P 500', 'index_etfs': 'Index ETFs against the S&P 500 (QQQ, DIA, IWM, MDY, RSP)',
              'styles': 'Style ETFs (growth, value, momentum, low volatility) against the S&P 500',
              'world': 'Countries and regions (ETFs in dollars) against the S&P 500',
              'bonds_commodities': 'Bonds and commodities against the S&P 500', 'industry_etfs': 'Industry and theme ETFs against the S&P 500',
              'industries': 'SIC industries (equal-weight, today\'s companies) against the S&P 500', 'companies': 'Companies against the S&P 500'}
    groups = {}
    for g in ORDER_D:
        keys = by.get(g) or []
        if not keys:
            continue
        R = Research(P['h'], P['unit'])
        try:
            for i in range(0, len(keys), chunk):
                A = np.array([row(k) for k in keys[i:i + chunk]])
                with np.errstate(divide='ignore', invalid='ignore'):
                    RS = np.where((spy > 0) & np.isfinite(A), 100 * A / spy[None], np.nan)
                S = states(RS, P['n'], P['sh'], P['long'], P['min_norm'])
                R.add(S['x'], S['y'], A, np.broadcast_to(spy[None], A.shape), days)
        except Exception as exc:
            print('rrg research daily', g, type(exc).__name__, exc, flush=True)
            continue
        r = R.to_json()
        if r['lines']:
            groups[g] = {'label': labels[g], **r}
    doc = {'schema': 'rrg_research.v1', 'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
           'freq': 'd', 'from': DAILY_FROM, 'rrg': {k: P[k] for k in ('sh', 'n', 'long', 'min_norm')}, 'near': NEAR,
           'speed': list(SPEED), 'depth': list(DEPTH), 'groups': groups, 'note': NOTE}
    Path(out_path).write_text(json.dumps(doc, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    if verbose:
        print('rrg research (daily):', {k: v['lines'] for k, v in groups.items()}, flush=True)
    return doc


def load_moves(moves_dir, kinds=None):
    """(data, assets) from published move-odds files (public/moves/a/*.json): each asset's adjusted daily closes,
    rebuilt from its returns, for build_daily outside moves.build (tests, a rebuild)."""
    import paths as PT
    data, assets = {}, []
    for p in sorted((Path(moves_dir) / 'a').glob('*.json')):
        d = json.loads(p.read_text(encoding='utf-8'))
        if kinds and d.get('kind') not in kinds:
            continue
        days, r = PT.decode_returns(d)
        lv = np.exp(np.concatenate([[0.0], np.cumsum(r)]))
        data[d['key']] = (days, lv.tolist(), d.get('last'))
        assets.append({'key': d['key'], 'kind': d.get('kind'), 'group': d.get('group')})
    return data, assets
