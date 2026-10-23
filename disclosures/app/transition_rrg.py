"""RRG quadrant transition probabilities and future quadrant paths, checked walk-forward before anything is called a
forecast (research specification v5 §4.4, §8.3, §8.4, §10, §11; tasks T1 and paths).

Lines (weekly, 14-week RRG, the chart's formula — vectorised here, identical to chaos_forecast.rrg_series):
  etf_vs_market         sector / style ETFs and the site-sector indices against SPY;
  company_vs_market     the site's companies against SPY;
  company_vs_industry   each company against its industry without itself (t/<T>.json bx), with the industry (bi)
                        against SPY as the conditioning state.

Heads, fixed before any test result was seen (the chart uses the PRIMARY head of each group):
  q    quadrant now → quadrant h weeks later (h = 1, 4, 13): a smoothed empirical matrix — primary for the two market
       groups;
  iq   (industry quadrant, company quadrant) → company quadrant h weeks later, smoothed toward q — primary for
       company_vs_industry;
  qh   (quadrant, heading of the last weekly step) → quadrant h weeks later — research only;
  chain the weekly chain over (quadrant, heading) states (joint (industry, company) quadrants for company_vs_industry),
       stepped k = 1 … 13 weeks: the future paths; its k-week marginals are scored as their own head.

Smoothing (§8.3): row i → (N_ij + λ prior_j) / (N_i + λ), λ = 10; prior = the overall destination shares for q, the q
row for iq and qh; the chain's rows shrink toward its quadrant-only weekly row.

Walk-forward from 2012-01-06: at each test origin (every h weeks, non-overlapping) the counts use only pairs whose
outcome was known by then (w + h ≤ origin); company lines count only while liquid at the origin (≥ $3, ≥ $10M a week
over 13 weeks, as notes/dual-rrg). Baselines from the same counts: stay put (P(same quadrant) = the training share
of lines that stayed, the rest spread evenly) and overall frequencies. Scores: multiclass Brier and log loss per
prediction, averaged per origin; skill = 1 − model / baseline with a 95% bootstrap interval over origins; classwise
expected calibration error (10 bins).

Labels (fixed in advance): calibrated — Brier skill against both baselines with the interval above zero, ECE ≤ 0.02,
≥ 50 origins; experimental — positive skill against both, but an interval touching zero or ECE > 0.02;
descriptive_only — no skill against one baseline (shown as history, never as a forecast); insufficient_data — fewer
than 50 origins or 2,000 test predictions.

Output public/rrg-transition-model.json: per group and head the full-history matrices the browser applies to any line
on the chart (rrg.js), the evaluation, and the label. Today's companies (survivorship) — stated with the results.
"""
import json
import math
from pathlib import Path

import numpy as np

HORIZONS = (1, 4, 13)
LAMBDA = 10.0
TEST_FROM = np.datetime64('2012-01-06')
FIT_FROM = np.datetime64('2002-01-04')
MIN_ORIGINS, MIN_PREDICTIONS, MAX_ECE = 50, 2000, 0.02
QUADS = ('leading', 'weakening', 'lagging', 'improving')
HEADINGS = ('up_right', 'down_right', 'down_left', 'up_left')
PRIMARY = {'etf_vs_market': 'q', 'company_vs_market': 'q', 'company_vs_industry': 'iq'}
SEED = 20261023


# ------------------------------------------------------------------ the RRG, vectorised over lines
def _ema(A, span, need=None):
    """Row-wise exponential average with the browser's resets: a missing value restarts the average."""
    al = 2 / (span + 1)
    need = min(span, 6) if need is None else need
    L, W = A.shape
    out = np.full((L, W), np.nan)
    m = np.zeros(L); c = np.zeros(L, int)
    for t in range(W):
        v = A[:, t]
        fin = np.isfinite(v)
        m = np.where(fin, np.where(c == 0, v, m + al * (v - m)), 0.0)
        c = np.where(fin, c + 1, 0)
        out[:, t] = np.where(fin & (c >= need), m, np.nan)
    return out


def rrg_panel(RS, n=14):
    """(x, y) arrays (lines × weeks) — chaos_forecast.rrg_series for every row at once."""
    sh, long = 4, max(52, 3 * n)
    s_ = _ema(RS, sh); t_ = _ema(s_, n)
    ok = np.isfinite(s_) & np.isfinite(t_) & (t_ != 0)
    with np.errstate(divide='ignore', invalid='ignore'):
        dev = np.where(ok, 100 * (s_ / np.where(ok, t_, 1) - 1), np.nan)
    d1 = np.full(dev.shape, np.nan); d1[:, 1:] = dev[:, 1:] - dev[:, :-1]
    roc = _ema(d1, sh)

    def norm(A):
        fin = np.isfinite(A)
        sq = np.where(fin, A * A, 0.0)
        cs = np.concatenate([np.zeros((A.shape[0], 1)), np.cumsum(sq, 1)], 1)
        cn = np.concatenate([np.zeros((A.shape[0], 1), int), np.cumsum(fin, 1)], 1)
        W = A.shape[1]
        k = np.arange(W); lo = np.maximum(0, k - long + 1)
        m = cn[:, k + 1] - cn[:, lo]; s2 = cs[:, k + 1] - cs[:, lo]
        good = fin & (m >= min(long, 26)) & (s2 > 0)
        with np.errstate(divide='ignore', invalid='ignore'):
            return np.where(good, 100 + A / np.sqrt(s2 / np.maximum(m, 1)), np.nan)
    x = norm(dev); y = norm(roc)
    y[~np.isfinite(x)] = np.nan
    return x, y


def states(x, y):
    """(quadrant code 0–3 or −1, heading code 0–3 or −1) per line and week; an axis value or a missing point is −1."""
    q = np.full(x.shape, -1, int)
    fin = np.isfinite(x) & np.isfinite(y) & (x != 100) & (y != 100)
    q[fin & (x > 100) & (y > 100)] = 0
    q[fin & (x > 100) & (y < 100)] = 1
    q[fin & (x < 100) & (y < 100)] = 2
    q[fin & (x < 100) & (y > 100)] = 3
    dx = np.full(x.shape, np.nan); dy = np.full(y.shape, np.nan)
    dx[:, 1:] = x[:, 1:] - x[:, :-1]; dy[:, 1:] = y[:, 1:] - y[:, :-1]
    h = np.full(x.shape, -1, int)
    fh = np.isfinite(dx) & np.isfinite(dy) & (q >= 0)
    h[fh & (dx >= 0) & (dy >= 0)] = 0
    h[fh & (dx >= 0) & (dy < 0)] = 1
    h[fh & (dx < 0) & (dy < 0)] = 2
    h[fh & (dx < 0) & (dy >= 0)] = 3
    return q, h


# ------------------------------------------------------------------ counts, smoothing, scores
def pair_counts(S, D, ok, h, n_from, n_to=4):
    """inc[w] = counts of (state at w → destination at w + h) over the lines eligible at w: shape (W, n_from, n_to);
    the cumulative sum up to w = origin − h is what was known at the origin."""
    L, W = S.shape
    inc = np.zeros((W, n_from, n_to))
    for w in range(W - h):
        a, b = S[:, w], D[:, w + h]
        m = ok[:, w] & (a >= 0) & (b >= 0)
        if m.any():
            np.add.at(inc[w], (a[m], b[m]), 1)
    return inc


def smooth(N, prior, lam=LAMBDA):
    """Row-wise (N_ij + λ prior_j) / (N_i + λ); prior is a vector (one for every row) or a matrix (row-specific)."""
    P = np.broadcast_to(prior, N.shape)
    return (N + lam * P) / (N.sum(1, keepdims=True) + lam)


def brier(P, y, k=4):
    Y = np.eye(k)[y]
    return ((P - Y) ** 2).sum(1)


def logloss(P, y):
    return -np.log(np.clip(P[np.arange(len(y)), y], 1e-6, 1))


def boot_skill(model, base, reps=2000, seed=SEED):
    """1 − Σmodel / Σbase over origins (per-origin mean scores), with a 95% bootstrap interval over origins."""
    model, base = np.asarray(model, float), np.asarray(base, float)
    if len(model) < 5:
        return None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(model), (reps, len(model)))
    s = 1 - model[idx].sum(1) / base[idx].sum(1)
    return [round(float(1 - model.sum() / base.sum()), 4), round(float(np.percentile(s, 2.5)), 4), round(float(np.percentile(s, 97.5)), 4)]


def ece(P, y, bins=10):
    """Classwise expected calibration error: for each class, |mean predicted − observed share| per probability bin,
    weighted by the bin's share of predictions; averaged over classes."""
    if not len(y):
        return None
    Y = np.eye(P.shape[1])[y]
    out = []
    for j in range(P.shape[1]):
        p, o = P[:, j], Y[:, j]
        b = np.minimum((p * bins).astype(int), bins - 1)
        e = 0.0
        for k in range(bins):
            m = b == k
            if m.any():
                e += m.mean() * abs(p[m].mean() - o[m].mean())
        out.append(e)
    return round(float(np.mean(out)), 4)


def reliability(P, y, bins=10):
    """Pooled over classes: [[mean predicted, observed share, n] per bin] for a calibration plot."""
    Y = np.eye(P.shape[1])[y]
    p, o = P.ravel(), Y.ravel()
    b = np.minimum((p * bins).astype(int), bins - 1)
    return [[round(float(p[b == k].mean()), 4), round(float(o[b == k].mean()), 4), int((b == k).sum())] for k in range(bins) if (b == k).any()]


def label(ev):
    if ev['origins'] < MIN_ORIGINS or ev['predictions'] < MIN_PREDICTIONS:
        return 'insufficient_data'
    sp, sf = ev['brier_skill_vs_stay'], ev['brier_skill_vs_freq']
    if not sp or not sf or sp[0] <= 0 or sf[0] <= 0:
        return 'descriptive_only'
    if sp[1] > 0 and sf[1] > 0 and ev['ece'] is not None and ev['ece'] <= MAX_ECE:
        return 'calibrated'
    return 'experimental'


def baselines(Nq):
    """(stay-put matrix, overall-frequency vector) from quadrant-to-quadrant counts."""
    tot = Nq.sum()
    stay = np.trace(Nq) / tot if tot else 0.25
    S = np.full((4, 4), (1 - stay) / 3); np.fill_diagonal(S, stay)
    freq = Nq.sum(0) / tot if tot else np.full(4, 0.25)
    return S, freq


# ------------------------------------------------------------------ the direct heads, walk-forward
def head_states(Q, H, IQ, head):
    """The row each line-week reads in a head's matrix: the quadrant (q), 4·quadrant + heading (qh), 4·industry
    quadrant + quadrant (iq); −1 where it is undefined."""
    if head == 'q':
        return Q
    if head == 'qh':
        return np.where((H >= 0) & (Q >= 0), 4 * Q + H, -1)
    return np.where((IQ >= 0) & (Q >= 0), 4 * IQ + Q, -1)


def head_prior(Pq, head):
    """Each row's smoothing target: the overall destination shares (q), the q row of the same quadrant (qh, iq)."""
    if head == 'q':
        return None
    return Pq[np.arange(16) // 4] if head == 'qh' else Pq[np.arange(16) % 4]


class Direct:
    """Cumulative pair counts of one horizon, so the matrices known at any origin are a lookup: at origin o only the
    pairs whose outcome week w + h ≤ o count (cum[o − h])."""

    def __init__(self, Q, H, IQ, ok, h, heads):
        self.Q, self.ok, self.h, self.heads = Q, ok, h, heads
        self.S = {k: head_states(Q, H, IQ, k) for k in heads}
        self.cq = np.cumsum(pair_counts(Q, Q, ok, h, 4), 0)
        self.cum = {k: np.cumsum(pair_counts(self.S[k], Q, ok, h, 16), 0) for k in heads if k != 'q'}

    def known(self, o):
        """(quadrant matrix, stay-put matrix, frequency vector, {head: matrix}) from the pairs known at origin o."""
        if o - self.h < 0:
            return None
        Nq = self.cq[o - self.h]
        if Nq.sum() < 200:
            return None
        Pq = smooth(Nq, Nq.sum(0) / Nq.sum())
        Sb, fb = baselines(Nq)
        M = {'q': Pq}
        for k in self.heads:
            if k != 'q':
                M[k] = smooth(self.cum[k][o - self.h], head_prior(Pq, k))
        return Pq, Sb, fb, M

    def predict(self, o, head):
        """(eligible-line mask, probabilities) at origin o; a line whose head state is undefined falls back to q."""
        K = self.known(o)
        if K is None:
            return None
        Pq, _, _, M = K
        a = self.Q[:, o]
        m = self.ok[:, o] & (a >= 0)
        if head == 'q':
            return m, Pq[a[m]]
        s = self.S[head][:, o][m]
        return m, np.where((s >= 0)[:, None], M[head][np.maximum(s, 0)], Pq[a[m]])


def _scores():
    return {'model': [], 'stay': [], 'freq': [], 'll_model': [], 'll_stay': [], 'll_freq': [], 'P': [], 'y': []}


def _add(r, P, Pst, Pfr, y):
    r['model'].append(brier(P, y).mean()); r['stay'].append(brier(Pst, y).mean()); r['freq'].append(brier(Pfr, y).mean())
    r['ll_model'].append(logloss(P, y).mean()); r['ll_stay'].append(logloss(Pst, y).mean()); r['ll_freq'].append(logloss(Pfr, y).mean())
    r['P'].append(P); r['y'].append(y)


def _summary(r, spacing):
    P = np.vstack(r['P']) if r['P'] else np.zeros((0, 4))
    y = np.concatenate(r['y']) if r['y'] else np.zeros(0, int)
    mean = lambda a: round(float(np.mean(a)), 4) if a else None
    ev = {'origins': len(r['model']), 'predictions': int(len(y)), 'spacing_weeks': spacing,
          'brier': mean(r['model']), 'brier_stay': mean(r['stay']), 'brier_freq': mean(r['freq']),
          'brier_skill_vs_stay': boot_skill(r['model'], r['stay']), 'brier_skill_vs_freq': boot_skill(r['model'], r['freq']),
          'logloss_skill_vs_stay': boot_skill(r['ll_model'], r['ll_stay']), 'logloss_skill_vs_freq': boot_skill(r['ll_model'], r['ll_freq']),
          'ece': ece(P, y), 'reliability': reliability(P, y) if len(y) else []}
    ev['label'] = label(ev)
    return ev


def evaluate_direct(Q, H, IQ, ok, days, h, heads):
    """Walk-forward scores of the direct heads at horizon h, origins every h weeks from TEST_FROM (non-overlapping).
    Q / H / IQ: quadrant, heading and conditioning-quadrant codes (lines × weeks); ok: eligible line-weeks."""
    W = Q.shape[1]
    F = Direct(Q, H, IQ, ok, h, heads)
    per = {k: _scores() for k in heads}
    for o in range(int(np.searchsorted(days, TEST_FROM)), W - h, h):
        K = F.known(o)
        if K is None:
            continue
        _, Sb, fb, _ = K
        b = Q[:, o + h]
        for k in heads:
            m, P = F.predict(o, k)
            keep = b[m] >= 0
            if keep.sum() < 3:
                break
            y, a = b[m][keep], Q[:, o][m][keep]
            _add(per[k], P[keep], Sb[a], np.repeat(fb[None], len(y), 0), y)
    return {k: _summary(r, h) for k, r in per.items()}


# ------------------------------------------------------------------ the weekly chain (future paths)
def chain_states(Q, H, IQ, joint):
    """Chain state per line-week: 4·quadrant + heading (16), or 4·industry quadrant + company quadrant when joint."""
    return head_states(Q, H, IQ, 'iq' if joint else 'qh')


def chain_quad_of(joint):
    """The company quadrant of each of the 16 chain states."""
    return np.arange(16) % 4 if joint else np.arange(16) // 4


def chain_matrix(N16, Nq1, joint):
    """16 × 16 weekly transitions, each row shrunk toward the quadrant-only weekly row spread over the destination's
    sub-states in their observed shares (so the chain stays a proper distribution)."""
    qof = chain_quad_of(joint)
    tot = N16.sum(0) + 1e-9
    sub = tot / np.array([tot[qof == qof[d]].sum() for d in range(16)])
    Pq = smooth(Nq1, Nq1.sum(0) / max(Nq1.sum(), 1))
    prior = Pq[qof][:, qof] * sub[None, :]
    P = smooth(N16, prior)
    return P / P.sum(1, keepdims=True)


def chain_quadrant(dist, joint):
    """Collapse a distribution over the 16 chain states to the 4 company quadrants."""
    qof = chain_quad_of(joint)
    return np.stack([dist[..., qof == q].sum(-1) for q in range(4)], -1)


class Chain:
    """The weekly chain known at any origin: pairs (w → w + 1) with w + 1 ≤ o."""

    def __init__(self, Q, H, IQ, ok, joint):
        self.Q, self.ok, self.joint = Q, ok, joint
        self.S = chain_states(Q, H, IQ, joint)
        self.c16 = np.cumsum(pair_counts(self.S, self.S, ok, 1, 16, 16), 0)
        self.cq1 = np.cumsum(pair_counts(Q, Q, ok, 1, 4), 0)

    def matrix(self, o):
        if o - 1 < 0 or self.c16[o - 1].sum() < 200:
            return None
        return chain_matrix(self.c16[o - 1], self.cq1[o - 1], self.joint)

    def predict(self, o, k):
        """(eligible-line mask, k-week company-quadrant probabilities) at origin o."""
        P1 = self.matrix(o)
        if P1 is None:
            return None
        s = self.S[:, o]
        m = self.ok[:, o] & (s >= 0)
        return m, chain_quadrant(np.linalg.matrix_power(P1, k)[s[m]], self.joint)


def evaluate_chain(Q, H, IQ, ok, days, joint, ks=HORIZONS):
    """The chain's k-week marginals scored like a direct head (origins every k weeks), against the same baselines."""
    W = Q.shape[1]
    C = Chain(Q, H, IQ, ok, joint)
    out = {}
    for k in ks:
        cqk = np.cumsum(pair_counts(Q, Q, ok, k, 4), 0)
        r = _scores()
        for o in range(int(np.searchsorted(days, TEST_FROM)), W - k, k):
            if o - k < 0 or cqk[o - k].sum() < 200:
                continue
            pr = C.predict(o, k)
            if pr is None:
                continue
            m, P = pr
            b = Q[:, o + k][m]
            keep = b >= 0
            if keep.sum() < 3:
                continue
            Sb, fb = baselines(cqk[o - k])
            y, a = b[keep], Q[:, o][m][keep]
            _add(r, P[keep], Sb[a], np.repeat(fb[None], len(y), 0), y)
        out[str(k)] = _summary(r, k)
    return out, C.matrix(W)


# ------------------------------------------------------------------ the group run and the published model
def group_model(name, X, Y, ok, days, IX=None, IY=None):
    """Everything published for one group of lines: full-history matrices for every head and horizon, the
    walk-forward evaluations, labels, the weekly chain and its evaluation."""
    Q, H = states(X, Y)
    IQ = states(IX, IY)[0] if IX is not None else np.full(Q.shape, -1, int)
    heads = ['q', 'qh'] + (['iq'] if IX is not None else [])
    joint = IX is not None
    m0 = days >= FIT_FROM
    okf = ok & m0[None, :]
    out = {'lines': int(X.shape[0]), 'primary': PRIMARY[name], 'heads': {}, 'horizons': list(HORIZONS)}
    for h in HORIZONS:
        ev = evaluate_direct(Q, H, IQ, okf, days, h, heads)
        inc = pair_counts(Q, Q, okf, h, 4).sum(0)
        Pq = smooth(inc, inc.sum(0) / max(inc.sum(), 1))
        full = {'q': {'counts': inc.astype(int).tolist(), 'P': np.round(Pq, 4).tolist()}}
        Sb, fb = baselines(inc)
        full['stay'] = np.round(Sb, 4).tolist(); full['freq'] = np.round(fb, 4).tolist()
        for k in heads:
            if k == 'q':
                continue
            N = pair_counts(head_states(Q, H, IQ, k), Q, okf, h, 16).sum(0)
            full[k] = {'counts': N.astype(int).tolist(), 'P': np.round(smooth(N, head_prior(Pq, k)), 4).tolist()}
        for k in heads:
            out['heads'].setdefault(k, {})[str(h)] = {**full[k], 'eval': ev[k], 'label': ev[k]['label']}
        out.setdefault('baselines', {})[str(h)] = {'stay': full['stay'], 'freq': full['freq']}
    ch, P1 = evaluate_chain(Q, H, IQ, okf, days, joint)
    out['chain'] = {'states': 'industry quadrant × company quadrant' if joint else 'quadrant × heading of the last weekly step',
                    'joint': joint, 'P1': np.round(P1, 5).tolist(), 'eval': ch, 'labels': {k: v['label'] for k, v in ch.items()}}
    span = days[okf.any(0)]
    out['from'] = str(span[0])[:10] if len(span) else None
    out['to'] = str(span[-1])[:10] if len(span) else None
    return out


def load(public, n=14, min_weeks=156):
    """The weekly grid, SPY, the ETF / site-sector lines and the companies (closes, volume, industry benchmarks)."""
    public = Path(public)
    D = json.loads((public / 'rrg.json').read_text(encoding='utf-8'))
    g0 = np.datetime64(D['start'])
    W = int((np.datetime64(D['weeks']) - g0).astype(int) // 7) + 1
    days = g0 + 7 * np.arange(W)

    def place(start, arr, scale=1.0):
        a = np.full(W, np.nan)
        o = int((np.datetime64(start) - g0).astype(int) // 7)
        v = np.array([np.nan if x is None else x * scale for x in arr], float)
        if o < W:
            a[max(0, o):o + len(v)] = v[max(0, -o):W - o]
        return a
    spy = place(D['bench']['start'], D['bench']['c'])
    etfs = [s for s in D['series'] if s.get('group') in ('sector-etf', 'style-etf', 'site-sector')]
    E = np.array([place(s['start'], s['c']) for s in etfs]) if etfs else np.zeros((0, W))
    cos, C, V, BX, BI = [], [], [], [], []
    for t, m in (D.get('tickers') or {}).items():
        p = public / 't' / f'{t}.json'
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding='utf-8'))
        if sum(1 for x in d['c'] if x is not None) < min_weeks:
            continue
        cos.append(t)
        C.append(place(d['start'], d['c'])); V.append(place(d['start'], d.get('v') or [None] * len(d['c']), 1000.0))
        BX.append(place(d['start'], d['bx']) if d.get('bx') else np.full(W, np.nan))
        BI.append(place(d['start'], d['bi']) if d.get('bi') else np.full(W, np.nan))
    return {'days': days, 'spy': spy, 'etf_ids': [s['id'] for s in etfs], 'E': E, 'cos': cos,
            'C': np.array(C) if C else np.zeros((0, W)), 'V': np.array(V) if V else np.zeros((0, W)),
            'BX': np.array(BX) if BX else np.zeros((0, W)), 'BI': np.array(BI) if BI else np.zeros((0, W))}


def liquid(C, V, min_price=3.0, min_dollar_volume=10e6):
    """Line-weeks a company is liquid: close ≥ $3 and mean weekly dollar volume over 13 weeks ≥ $10M (≥ 10 weeks)."""
    dv = C * V
    fin = np.isfinite(dv)
    cs = np.concatenate([np.zeros((dv.shape[0], 1)), np.cumsum(np.where(fin, dv, 0), 1)], 1)
    cn = np.concatenate([np.zeros((dv.shape[0], 1), int), np.cumsum(fin, 1)], 1)
    W = dv.shape[1]
    k = np.arange(W); lo = np.maximum(0, k - 12)
    s, n = cs[:, k + 1] - cs[:, lo], cn[:, k + 1] - cn[:, lo]
    with np.errstate(divide='ignore', invalid='ignore'):
        mean = np.where(n > 0, s / np.maximum(n, 1), np.nan)
    return np.isfinite(C) & (C >= min_price) & (n >= 10) & (mean >= min_dollar_volume)


def build(public, out_name='rrg-transition-model.json', verbose=True):
    L = load(public)
    days, spy = L['days'], L['spy']
    with np.errstate(divide='ignore', invalid='ignore'):
        rel = lambda A, B: np.where((B > 0) & np.isfinite(A), 100 * A / B, np.nan)
        groups = {}
        if len(L['E']):
            ex, ey = rrg_panel(rel(L['E'], spy[None]))
            groups['etf_vs_market'] = group_model('etf_vs_market', ex, ey, np.isfinite(ex), days)
        if len(L['C']):
            ok = liquid(L['C'], L['V'])
            cx, cy = rrg_panel(rel(L['C'], spy[None]))
            groups['company_vs_market'] = group_model('company_vs_market', cx, cy, ok, days)
            has = np.isfinite(L['BX']).any(1)
            if has.any():
                ix, iy = rrg_panel(rel(L['BI'][has], spy[None]))
                bx, by = rrg_panel(rel(L['C'][has], L['BX'][has]))
                groups['company_vs_industry'] = group_model('company_vs_industry', bx, by, ok[has], days, ix, iy)
    doc = {'schema_version': 'rrg_transition_model.v1', 'generated_at': str(np.datetime64('now'))[:19] + 'Z',
           'rrg': {'freq': 'w', 'n': 14}, 'quadrants': list(QUADS), 'headings': list(HEADINGS), 'lambda': LAMBDA,
           'test_from': str(TEST_FROM), 'gates': {'min_origins': MIN_ORIGINS, 'min_predictions': MIN_PREDICTIONS, 'max_ece': MAX_ECE,
                                                  'calibrated': 'Brier skill vs stay-put and vs overall frequencies, both 95% intervals above 0, ECE <= 0.02',
                                                  'experimental': 'positive Brier skill vs both, an interval touching 0 or ECE above 0.02',
                                                  'descriptive_only': 'no skill vs one of the baselines: history only, not a forecast',
                                                  'insufficient_data': 'fewer than 50 origins or 2,000 test predictions'},
           'primary': PRIMARY, 'groups': groups,
           'note': ('Weekly 14-week RRG. Probabilities come from smoothed empirical transition matrices fitted on every pair '
                    'whose outcome is known; each head was scored walk-forward from 2012 against staying put and the overall '
                    'quadrant frequencies, and only labelled heads are shown as forecasts. Paths: the weekly chain over quadrant '
                    'and the direction of the last step (company vs industry: the joint industry and company quadrants), stepped '
                    'week by week. Companies count only while liquid (≥ $3, ≥ $10M a week). Today\'s companies: survivorship '
                    'flatters every model alike. History-based, not investment advice.')}
    (Path(public) / out_name).write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')
    if verbose:
        for g, v in groups.items():
            print('transition model', g, 'lines', v['lines'], {h: v['heads'][v['primary']][h]['label'] for h in map(str, HORIZONS)},
                  'chain', v['chain']['labels'], flush=True)
    return doc
