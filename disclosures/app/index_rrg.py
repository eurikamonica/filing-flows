"""The four index ETFs around their own centre — QQQ (Nasdaq-100), SPY (S&P 500), IWM (Russell 2000), DIA (Dow) —
weekly since 2000, total return (public/rrg.json), with quadrant odds, paths, price ranges and next week's price for
each quadrant. Built by chaos_forecast.build (after macro_history: the cash line needs FRED's 3-month bill), published
as public/index-rrg.json; the weekly forecasts are frozen in ledger/index.json and scored (ledger_update, run by
forecast_ledger.update), summary public/index-ledger.json. The hub's RRG shows it as Lines → “The four indices around
their centre” (docs/rrg-index.js).

Why a centre. SPY overlaps the other three (the Nasdaq-100 and the Dow are mostly large S&P companies), so against SPY
the chart only says “more tech, or more value, than the S&P”, and SPY itself cannot be drawn. Two layers instead:

  relative  each index against the centre of the four: their volatility-weighted geometric mean — weights ∝ 1 / the
            index's standard deviation of weekly log returns over the 26 weeks before (known when the week starts), so
            the volatile Nasdaq-100 and Russell 2000 cannot drag the centre alone. The weighted relative moves add up
            to zero (Σ wᵢ (rᵢ − r_c) = 0): one index leading means others lagging, and all four rotate around it. An
            index is part of its own centre: next week's price for a quadrant takes its own weight out (rising 10% with
            a 30% weight moves it about 7% against the centre).
  absolute  the centre against cash (FRED DGS3MO, the 3-month Treasury bill, compounded weekly at the rate known when
            the week starts): is the market as a whole strong. Price = cash × (centre ÷ cash) × (index ÷ centre).

Fixed before any result was seen — which centre:
  candidates  spy (SPY itself; its own line is undefined), equal (equal-weight geometric mean of the four), vol (above),
              cash (each index against the bill);
  periods     chosen on weekly origins 2003–2011, reported on origins from 2012 (out of sample) for all four, whatever
              they show;
  criteria    (1) quadrant odds: the direct quadrant matrix (smoothed as transition_rrg, λ = 10) at 1, 4 and 13 weeks,
              walk-forward (only pairs whose outcome was known at the origin), Brier skill against staying put and
              against the usual shares; (2) RS-Momentum − 100 against the next four weeks' log return relative to the
              centre: Spearman correlation, pooled over lines and weeks; (3) price-range coverage does not depend on
              the centre (the replay is of the four indices together), so it chooses the replay instead;
  rule        the highest mean over h of min(skill vs stay, skill vs usual shares) on 2003–2011 wins; within 0.002, the
              higher correlation.

Markov (the chosen centre). States: each index's quadrant against the centre × the centre's quadrant against cash
(16; the company page's industry-conditioned head, transition_rrg 'iq'), pooled over the four lines; heads q (quadrant
only) and iq at 1, 4 and 13 weeks; the weekly chain over the 16 joint states for weeks 1–13 and the most common 13-week
paths (seeded simulation). Leader: the order of the four by RS-Ratio (24 states) → which index has the highest RS-Ratio
h weeks later. Four lines give few predictions, so — fixed in advance — origins are weekly (overlapping), skill
intervals come from a moving-block bootstrap over origins (blocks of h weeks), and the label rules are transition_rrg's
with origins counted as independent (weeks ÷ h ≥ 50) and ≥ 2,000 predictions (leader: ≥ 500, one prediction a week).

Price ranges: joint replay — every 13-week run of the four indices' weekly moves (and the bill), replayed from today, so
their correlations and the zero sum hold. Two methods, chosen on 2003–2011 coverage (13-week origins, 80% and 50%
ranges at 4 and 13 weeks, the smaller total gap to nominal), both reported from 2012: plain (the last 156 weeks, as the
company pages) and volatility-scaled (up to the last 520 weeks, each run's moves × today's 26-week volatility ÷ the
volatility when the run began). Each path also runs through the RRG formula: position ranges at 4 and 13 weeks.
"""
import datetime as dt
import itertools
import json
import math
from pathlib import Path

import numpy as np

import transition_rrg as TR

TICKERS = ('QQQ', 'SPY', 'IWM', 'DIA')
NAMES = {'QQQ': 'Nasdaq-100 (QQQ)', 'SPY': 'S&P 500 (SPY)', 'IWM': 'Russell 2000 (IWM)', 'DIA': 'Dow Jones (DIA)'}
CENTRES = ('spy', 'equal', 'vol', 'cash')
CENTRE_NAMES = {'spy': 'SPY', 'equal': 'Equal-weight centre', 'vol': 'Volatility-weighted centre', 'cash': 'Cash (3-month bill)'}
VOL_WEEKS = 26
N_RRG = 14
HORIZONS = (1, 4, 13)
FIT_FROM = np.datetime64('2002-01-04')
SELECT = (np.datetime64('2003-01-03'), np.datetime64('2011-12-30'))
TEST_FROM = np.datetime64('2012-01-06')
STEPS = 13
PLAIN, LONG = 156, 520
MIN_INDEPENDENT, MIN_PREDICTIONS, MIN_LEADER = 50, 2000, 500
SEED = 20261025
LAM = TR.LAMBDA


# ------------------------------------------------------------------ data
def load_prices(public):
    """(days, closes 4 × W) on rrg.json's Friday grid; NaN where a fund has no close."""
    D = json.loads((Path(public) / 'rrg.json').read_text(encoding='utf-8'))
    g0 = np.datetime64(D['start'])
    W = int((np.datetime64(D['weeks']) - g0).astype(int) // 7) + 1
    days = g0 + 7 * np.arange(W)

    def full(ent):
        a = np.full(W, np.nan)
        if not ent:
            return a
        o = int((np.datetime64(ent['start']) - g0).astype(int) // 7)
        c = np.array([np.nan if v is None else v for v in ent['c']], float)
        a[o:o + len(c)] = c[:W - o]
        return a
    by = {s['id']: s for s in D.get('series') or []}
    P = np.vstack([full(D.get('bench')) if t == 'SPY' else full(by.get(t)) for t in TICKERS])
    return days, P


def bill_rates(macro_dir):
    """[(date, annual yield %)] of FRED DGS3MO from macro_history's cache (missing days '.' skipped)."""
    p = Path(macro_dir) / 'DGS3MO.csv'
    out = []
    try:
        for line in p.read_text(encoding='utf-8').splitlines()[1:]:
            d, _, v = line.partition(',')
            try:
                out.append((np.datetime64(d.strip()), float(v)))
            except ValueError:
                continue
    except OSError:
        return []
    return out


def cash_returns(days, rates):
    """Weekly log return of holding the bill: the yield known before the week began (the last one up to the Friday
    before), compounded for seven days; NaN before FRED's first value."""
    r = np.full(len(days), np.nan)
    if not rates:
        return r
    d = np.array([x[0] for x in rates]); y = np.array([x[1] for x in rates])
    for t in range(1, len(days)):
        k = np.searchsorted(d, days[t - 1], side='right') - 1
        if k >= 0 and (days[t - 1] - d[k]).astype(int) <= 14:
            r[t] = math.log(1 + y[k] / 100) * 7 / 365.25
    return r


def log_returns(P):
    with np.errstate(divide='ignore', invalid='ignore'):
        R = np.full(P.shape, np.nan)
        R[:, 1:] = np.log(P[:, 1:] / P[:, :-1])
    return R


def vol_weights(R, weeks=VOL_WEEKS):
    """Weights for week t from the 26 weekly returns before it (t − 26 … t − 1): ∝ 1 / standard deviation, all four
    needed (at least 20 returns each); NaN otherwise. Known when week t starts."""
    L, W = R.shape
    Wt = np.full((L, W), np.nan)
    for t in range(weeks, W):
        seg = R[:, t - weeks:t]
        ok = np.isfinite(seg).sum(1) >= 20
        if not ok.all():
            continue
        sd = np.array([np.nanstd(s, ddof=1) for s in seg])
        if (sd <= 0).any():
            continue
        w = 1 / sd
        Wt[:, t] = w / w.sum()
    return Wt


def trailing_sd(R, weeks=VOL_WEEKS):
    """Each line's standard deviation of the 26 weekly returns up to and including week t (NaN with fewer than 20)."""
    L, W = R.shape
    out = np.full((L, W), np.nan)
    for t in range(weeks - 1, W):
        seg = R[:, t - weeks + 1:t + 1]
        n = np.isfinite(seg).sum(1)
        with np.errstate(invalid='ignore'):
            s = np.nanstd(seg, 1, ddof=1)
        out[:, t] = np.where(n >= 20, s, np.nan)
    return out


def centre_returns(R, cash):
    """{centre: weekly log return of the centre} and the volatility weights (4 × W)."""
    Wv = vol_weights(R)
    allf = np.isfinite(R).all(0)
    eq = np.where(allf, R.mean(0) if R.size else np.nan, np.nan)
    vol = np.where(allf & np.isfinite(Wv).all(0), np.nansum(Wv * np.nan_to_num(R), 0), np.nan)
    return {'spy': R[TICKERS.index('SPY')], 'equal': eq, 'vol': vol, 'cash': cash}, Wv


def level(r, start=100.0):
    """An index level from weekly log returns: NaN until the first return, a missing week carries the level."""
    out = np.full(len(r), np.nan)
    v = None
    for t, x in enumerate(r):
        if v is None:
            if np.isfinite(x):
                v = start
                out[t] = v
            continue
        if np.isfinite(x):
            v *= math.exp(x)
        out[t] = v
    return out


def relative(P, L):
    with np.errstate(divide='ignore', invalid='ignore'):
        return np.where(np.isfinite(P) & np.isfinite(L)[None, :] & (L[None, :] > 0), 100 * P / L[None, :], np.nan)


# ------------------------------------------------------------------ walk-forward scores (weekly origins, block bootstrap)
def block_skill(model, base, h, reps=2000, seed=SEED):
    """1 − Σmodel / Σbase over origins, 95% interval from a moving-block bootstrap (blocks of h origins: overlapping
    weekly origins are not independent)."""
    model, base = np.asarray(model, float), np.asarray(base, float)
    n = len(model)
    if n < 10:
        return None
    b = max(1, min(h, n // 3))
    rng = np.random.default_rng(seed)
    k = int(math.ceil(n / b))
    starts = rng.integers(0, n - b + 1, (reps, k))
    idx = (starts[:, :, None] + np.arange(b)[None, None, :]).reshape(reps, -1)[:, :n]
    s = 1 - model[idx].sum(1) / base[idx].sum(1)
    return [round(float(1 - model.sum() / base.sum()), 4), round(float(np.percentile(s, 2.5)), 4), round(float(np.percentile(s, 97.5)), 4)]


def labelled(ev, h, min_pred=MIN_PREDICTIONS):
    """transition_rrg's label rules with weekly origins counted as independent (origins ÷ h)."""
    if ev['origins'] / h < MIN_INDEPENDENT or ev['predictions'] < min_pred:
        return 'insufficient_data'
    sp, sf = ev['brier_skill_vs_stay'], ev['brier_skill_vs_freq']
    if not sp or not sf or sp[0] <= 0 or sf[0] <= 0:
        return 'descriptive_only'
    if sp[1] > 0 and sf[1] > 0 and ev['ece'] is not None and ev['ece'] <= TR.MAX_ECE:
        return 'calibrated'
    return 'experimental'


def summarise(rec, h, min_pred=MIN_PREDICTIONS, k=4):
    P = np.vstack(rec['P']) if rec['P'] else np.zeros((0, k))
    y = np.concatenate(rec['y']) if rec['y'] else np.zeros(0, int)
    mean = lambda a: round(float(np.mean(a)), 4) if a else None
    ev = {'origins': len(rec['model']), 'independent_origins': round(len(rec['model']) / h, 1), 'predictions': int(len(y)),
          'brier': mean(rec['model']), 'brier_stay': mean(rec['stay']), 'brier_freq': mean(rec['freq']),
          'brier_skill_vs_stay': block_skill(rec['model'], rec['stay'], h), 'brier_skill_vs_freq': block_skill(rec['model'], rec['freq'], h),
          'ece': TR.ece(P, y) if len(y) else None}
    ev['label'] = labelled(ev, h, min_pred)
    return ev


def _rec():
    return {'model': [], 'stay': [], 'freq': [], 'P': [], 'y': []}


def _add(rec, P, Pst, Pfr, y, k=4):
    rec['model'].append(TR.brier(P, y, k).mean()); rec['stay'].append(TR.brier(Pst, y, k).mean()); rec['freq'].append(TR.brier(Pfr, y, k).mean())
    rec['P'].append(P); rec['y'].append(y)


def origins(days, lo, hi, W, h):
    return [o for o in range(W - h) if lo <= days[o] <= hi]


def eval_direct(Q, IQ, ok, days, h, periods, heads=('q',)):
    """{period: {head: evaluation}} of the direct heads at horizon h, weekly origins."""
    W = Q.shape[1]
    cq = np.cumsum(TR.pair_counts(Q, Q, ok, h, 4), 0)
    S = {k: TR.head_states(Q, None, IQ, k) for k in heads if k != 'q'}
    cs = {k: np.cumsum(TR.pair_counts(S[k], Q, ok, h, 16), 0) for k in S}
    out = {}
    for name, (lo, hi) in periods.items():
        rec = {k: _rec() for k in heads}
        for o in origins(days, lo, hi, W, h):
            if o - h < 0:
                continue
            Nq = cq[o - h]
            if Nq.sum() < 100:
                continue
            Pq = TR.smooth(Nq, Nq.sum(0) / Nq.sum(), LAM)
            Sb, fb = TR.baselines(Nq)
            a, b = Q[:, o], Q[:, o + h]
            m = ok[:, o] & (a >= 0) & (b >= 0)
            if not m.any():
                continue
            for k in heads:
                if k == 'q':
                    Pm = Pq[a[m]]
                else:
                    M = TR.smooth(cs[k][o - h], TR.head_prior(Pq, k), LAM)
                    s = S[k][:, o][m]
                    Pm = np.where((s >= 0)[:, None], M[np.maximum(s, 0)], Pq[a[m]])
                _add(rec[k], Pm, Sb[a[m]], np.repeat(fb[None], m.sum(), 0), b[m])
        out[name] = {k: summarise(r, h) for k, r in rec.items()}
    return out


def momentum_ic(Y, R_rel, days, lo, hi, h=4):
    """Spearman correlation of RS-Momentum − 100 at week t with the next h weeks' relative log return, pooled over
    lines and weeks in [lo, hi]; 95% interval from a moving-block bootstrap over weeks."""
    W = Y.shape[1]
    fwd = np.full(Y.shape, np.nan)
    for t in range(W - h):
        seg = R_rel[:, t + 1:t + h + 1]
        fwd[:, t] = np.where(np.isfinite(seg).all(1), seg.sum(1), np.nan)
    ts = [t for t in range(W - h) if lo <= days[t] <= hi]
    pairs = [(t, Y[i, t] - 100, fwd[i, t]) for t in ts for i in range(Y.shape[0]) if np.isfinite(Y[i, t]) and np.isfinite(fwd[i, t])]
    if len(pairs) < 50:
        return None
    rank = lambda a: np.argsort(np.argsort(a)).astype(float)
    def rho(sel):
        a = np.array([pairs[j][1] for j in sel]); b = np.array([pairs[j][2] for j in sel])
        ra, rb = rank(a), rank(b)
        return float(np.corrcoef(ra, rb)[0, 1])
    base = rho(range(len(pairs)))
    weeks = sorted({p[0] for p in pairs})
    byw = {}
    for j, p in enumerate(pairs):
        byw.setdefault(p[0], []).append(j)
    rng = np.random.default_rng(SEED)
    n, b = len(weeks), max(1, h)
    sims = []
    for _ in range(300):
        st = rng.integers(0, max(1, n - b + 1), int(math.ceil(n / b)))
        sel = [j for s0 in st for w in weeks[s0:s0 + b] for j in byw[w]]
        sims.append(rho(sel))
    return [round(base, 4), round(float(np.percentile(sims, 2.5)), 4), round(float(np.percentile(sims, 97.5)), 4), len(pairs)]


# ------------------------------------------------------------------ the leader: order by RS-Ratio → leader h weeks on
def leader_states(X):
    """(order state 0–23 or −1, leader 0–3 or −1) per week: the permutation of the four by RS-Ratio, highest first."""
    perms = {p: i for i, p in enumerate(itertools.permutations(range(4)))}
    W = X.shape[1]
    st, ld = np.full(W, -1), np.full(W, -1)
    for t in range(W):
        x = X[:, t]
        if np.isfinite(x).all():
            order = tuple(int(i) for i in np.argsort(-x, kind='stable'))
            st[t], ld[t] = perms[order], order[0]
    return st, ld


def leader_matrix(st, ld, upto, h):
    """Smoothed 24 × 4 matrix (and the stay share, the leader shares) from pairs whose outcome week ≤ upto."""
    N = np.zeros((24, 4))
    for w in range(0, upto - h + 1):
        if w >= FIT0 and st[w] >= 0 and ld[w + h] >= 0:
            N[st[w], ld[w + h]] += 1
    tot = N.sum()
    if tot < 50:
        return None
    freq = N.sum(0) / tot
    lead_of = np.array([p[0] for p in itertools.permutations(range(4))])
    stay = sum(N[s, lead_of[s]] for s in range(24)) / tot
    return TR.smooth(N, freq, LAM), stay, freq, lead_of, N


FIT0 = 0                                              # set by build: the first week of FIT_FROM


def eval_leader(st, ld, days, h, periods):
    W = len(st)
    out = {}
    for name, (lo, hi) in periods.items():
        rec = _rec()
        for o in origins(days, lo, hi, W, h):
            if st[o] < 0 or ld[o + h] < 0:
                continue
            M = leader_matrix(st, ld, o, h)
            if M is None:
                continue
            P, stay, freq, lead_of, _ = M
            cur = lead_of[st[o]]
            Pst = np.full(4, (1 - stay) / 3); Pst[cur] = stay
            y = np.array([ld[o + h]])
            _add(rec, P[st[o]][None], Pst[None], freq[None], y)
        out[name] = summarise(rec, h, MIN_LEADER)
    return out


# ------------------------------------------------------------------ joint replay: price and position ranges
def replay_paths(R, cash, o, method, steps=STEPS, sd=None):
    """(paths × 4 × steps) weekly log moves of the four, and (paths × steps) the bill's, from every 13-week run in the
    window before origin o; vol: each run × today's 26-week volatility ÷ the volatility when the run began."""
    window = PLAIN if method == 'plain' else LONG
    lo = max(1, o - window + 1)
    starts = np.arange(lo, o - steps + 2)
    if len(starts) < 20:
        return None
    idx = starts[:, None] + np.arange(steps)[None, :]
    X = R[:, idx].transpose(1, 0, 2)                                  # paths × lines × steps
    good = np.isfinite(X).all((1, 2))
    X, starts = X[good], starts[good]
    if len(X) < 20:
        return None
    if method == 'vol':
        s_now = sd[:, o]
        s_then = sd[:, starts - 1].T                                  # paths × lines (known when the run began)
        k = s_now[None, :] / s_then
        k = np.where(np.isfinite(k) & (k > 0), np.clip(k, 0.25, 4), 1.0)
        X = X * k[:, :, None]
    c_now = cash[o] if np.isfinite(cash[o]) else 0.0
    C = np.full((len(X), steps), c_now)
    return X, C


def coverage(R, cash, sd, days, method, lo, hi, ks=(1, 4, 13)):
    """Share of realised moves inside the replayed 80% and 50% ranges, origins every 13 weeks in [lo, hi]."""
    W = R.shape[1]
    hit = {k: {'80': [], '50': []} for k in ks}
    for o in range(0, W - max(ks)):
        if not (lo <= days[o] <= hi) or (o - int(np.searchsorted(days, lo))) % 13:
            continue
        rp = replay_paths(R, cash, o, method, sd=sd)
        if rp is None:
            continue
        X, _ = rp
        cum = np.cumsum(X, 2)
        for k in ks:
            real = R[:, o + 1:o + k + 1].sum(1)
            okr = np.isfinite(R[:, o + 1:o + k + 1]).all(1)
            q = np.percentile(cum[:, :, k - 1], [10, 25, 75, 90], axis=0)
            for i in range(4):
                if okr[i]:
                    hit[k]['80'].append(q[0, i] <= real[i] <= q[3, i]); hit[k]['50'].append(q[1, i] <= real[i] <= q[2, i])
    out = {}
    for k in ks:
        c80 = float(np.mean(hit[k]['80'])) if hit[k]['80'] else None
        c50 = float(np.mean(hit[k]['50'])) if hit[k]['50'] else None
        out[str(k)] = {'c80': None if c80 is None else round(c80, 4), 'c50': None if c50 is None else round(c50, 4), 'n': len(hit[k]['80']),
                       'label': TR.band_label(c80, c50) if c80 is not None else 'insufficient_data'}
    return out


def gap(cov):
    return sum(abs(cov[str(k)]['c80'] - 0.8) + abs(cov[str(k)]['c50'] - 0.5) for k in (4, 13)
               if cov[str(k)]['c80'] is not None) if cov else math.inf


def relative_moves(X, C, centre, w):
    """(paths × 4 × steps) relative log moves of each index against the centre along each path (weights at origin)."""
    if centre == 'equal':
        rc = X.mean(1)
    elif centre == 'vol':
        rc = (X * w[None, :, None]).sum(1)
    elif centre == 'spy':
        rc = X[:, TICKERS.index('SPY'), :]
    else:
        rc = C
    return X - rc[:, None, :]


# ------------------------------------------------------------------ next week: the close for each quadrant
def step_one(S, rel, o, i, rr):
    """(x, y) one week on for line i after a relative log move rr (the chart's formula)."""
    _, X, Y = TR.step_paths(S, rel, o, np.array([i]), np.array([[[rr]]]))
    return float(X[0, 0, 0]), float(Y[0, 0, 0])


def thresholds(S, rel, o, i, own, price):
    """Next week's close at which RS-Ratio and RS-Momentum cross 100 (everything else flat), own = how much of the
    index's own move its centre takes (its weight; 1 − own of the move is relative), and the close range of each
    reachable quadrant."""
    k = 1 - own
    if k <= 0 or not np.isfinite(price):
        return None

    def cross(f):
        lo, hi = -0.6, 0.6
        flo, fhi = f(lo) - 100, f(hi) - 100
        if not (np.isfinite(flo) and np.isfinite(fhi)):
            return None
        if flo >= 0:
            return -math.inf
        if fhi < 0:
            return math.inf
        for _ in range(60):
            mid = (lo + hi) / 2
            if f(mid) - 100 >= 0:
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2
    rx = cross(lambda r: step_one(S, rel, o, i, k * r)[0])
    ry = cross(lambda r: step_one(S, rel, o, i, k * r)[1])
    if rx is None or ry is None:
        return None
    P = lambda r: None if not np.isfinite(r) else round(float(price * math.exp(r)), 2)
    cuts = sorted([(rx, 'x'), (ry, 'y')])
    ranges, prev = [], -math.inf
    for r, _ in cuts + [(math.inf, None)]:
        if r > prev:
            mid = (max(prev, -0.6) + min(r, 0.6)) / 2
            x, y = (mid >= rx), (mid >= ry)
            q = 'leading' if x and y else 'weakening' if x else 'improving' if y else 'lagging'
            ranges.append([q, P(prev), P(r)])
        prev = r
    return {'x100': P(rx), 'y100': P(ry), 'ranges': ranges, 'own_weight': round(own, 4)}


# ------------------------------------------------------------------ the chain's paths
def chain_paths(P1, s0, steps=STEPS, n=20000, top=5, seed=SEED):
    """The most common routes of the index's quadrant over 13 weeks from joint state s0 — each simulated path read as
    the quadrants it visits in order (a stay is one step), as rrg-odds.js does — with their shares (seeded)."""
    rng = np.random.default_rng(seed)
    cum = np.cumsum(P1, 1)
    s = np.full(n, s0)
    seq = np.zeros((n, steps), int)
    for j in range(steps):
        u = rng.random(n)
        s = np.minimum((u[:, None] > cum[s]).sum(1), 15)
        seq[:, j] = s % 4
    routes = {}
    for row in seq:
        r = [s0 % 4]
        for q in row:
            if q != r[-1]:
                r.append(int(q))
        routes[tuple(r)] = routes.get(tuple(r), 0) + 1
    best = sorted(routes.items(), key=lambda kv: -kv[1])[:top]
    return [[list(k), round(v / n, 4)] for k, v in best]


# ------------------------------------------------------------------ the build
def r4(v, n=4):
    return None if v is None or not np.isfinite(v) else round(float(v), n)


def build(public, macro_dir=None, out_name='index-rrg.json', verbose=True):
    global FIT0
    public = Path(public)
    macro_dir = Path(macro_dir) if macro_dir else public.parent / 'cache' / 'macro'
    days, P = load_prices(public)
    W = len(days)
    FIT0 = int(np.searchsorted(days, FIT_FROM))
    R = log_returns(P)
    cash = cash_returns(days, bill_rates(macro_dir))
    rc, Wv = centre_returns(R, cash)
    levels = {c: level(r) for c, r in rc.items()}
    sd = trailing_sd(R)
    periods = {'select': SELECT, 'test': (TEST_FROM, days[-1])}
    fit_ok = (days >= FIT_FROM)[None, :]
    # the comparison of centres
    compare, states = {}, {}
    for c in CENTRES:
        if not np.isfinite(levels[c]).any():
            continue
        RS = relative(P, levels[c])
        if c == 'spy':                               # SPY against itself is constant (up to rounding): no line
            RS[TICKERS.index('SPY')] = np.nan
        S = TR.rrg_states(RS, N_RRG)
        Q, _ = TR.states(S['x'], S['y'])
        ok = (Q >= 0) & fit_ok
        Rrel = R - rc[c][None, :]
        res = {'lines': int((np.isfinite(S['x']).sum(1) > 0).sum())}
        for h in HORIZONS:
            ev = eval_direct(Q, None, ok, days, h, periods)
            for per in periods:
                res.setdefault(per, {})[str(h)] = ev[per]['q']
        for per, (lo, hi) in periods.items():
            res[per]['ic4'] = momentum_ic(S['y'], Rrel, days, lo, hi)
            sk = [min(res[per][str(h)]['brier_skill_vs_stay'][0], res[per][str(h)]['brier_skill_vs_freq'][0])
                  for h in HORIZONS if res[per][str(h)]['brier_skill_vs_stay'] and res[per][str(h)]['brier_skill_vs_freq']]
            res[per]['score'] = round(float(np.mean(sk)), 4) if len(sk) == len(HORIZONS) else None
        compare[c] = res
        states[c] = (RS, S, Q)
        if verbose:
            print('centre', c, 'select', res['select']['score'], 'ic', res['select']['ic4'], '| test', res['test']['score'], 'ic', res['test']['ic4'], flush=True)
    ranked = sorted((c for c in compare if compare[c]['select']['score'] is not None),
                    key=lambda c: (-compare[c]['select']['score'], -((compare[c]['select']['ic4'] or [0])[0])))
    chosen = ranked[0] if ranked else 'vol'
    if ranked:                                       # every centre within 0.002 of the best: the higher correlation
        near = [c for c in ranked if compare[ranked[0]]['select']['score'] - compare[c]['select']['score'] <= 0.002]
        chosen = max(near, key=lambda c: ((compare[c]['select']['ic4'] or [-9])[0], -ranked.index(c)))
    # the replay method
    cov = {m: {per: coverage(R, cash, sd, days, m, lo, hi) for per, (lo, hi) in periods.items()} for m in ('plain', 'vol')}
    method = 'vol' if gap(cov['vol']['select']) < gap(cov['plain']['select']) else 'plain'
    if verbose:
        print('chosen centre', chosen, '| replay', method, {m: {p: {k: (v['c80'], v['c50']) for k, v in x.items()} for p, x in d.items()} for m, d in cov.items()}, flush=True)
    # the published model: the chosen centre, conditioned on the centre against cash
    RS, S, Q = states[chosen]
    H = TR.states(S['x'], S['y'])[1]
    cond = chosen != 'cash' and np.isfinite(levels['cash']).any()
    if cond:
        RSc = relative(levels[chosen][None, :], levels['cash'])
        Sc = TR.rrg_states(RSc, N_RRG)
        qc = TR.states(Sc['x'], Sc['y'])[0][0]
    else:
        RSc, Sc, qc = None, None, np.full(W, -1)
    IQ = np.repeat(qc[None, :], 4, 0)
    ok = (Q >= 0) & fit_ok
    heads = ('q', 'iq') if cond else ('q',)
    model = {'heads': {}, 'centre': chosen, 'conditioned_on': 'the centre against cash' if cond else None}
    for h in HORIZONS:
        ev = eval_direct(Q, IQ, ok, days, h, {'test': periods['test']}, heads)['test']
        inc = TR.pair_counts(Q, Q, ok, h, 4).sum(0)
        Pq = TR.smooth(inc, inc.sum(0) / max(inc.sum(), 1), LAM)
        Sb, fb = TR.baselines(inc)
        full = {'q': Pq}
        if cond:
            N16 = TR.pair_counts(TR.head_states(Q, H, IQ, 'iq'), Q, ok, h, 16).sum(0)
            full['iq'] = TR.smooth(N16, TR.head_prior(Pq, 'iq'), LAM)
        for k in heads:
            model['heads'].setdefault(k, {})[str(h)] = {'P': np.round(full[k], 4).tolist(), 'eval': ev[k], 'label': ev[k]['label']}
        model.setdefault('baselines', {})[str(h)] = {'stay': np.round(Sb, 4).tolist(), 'freq': np.round(fb, 4).tolist()}
    primary = 'iq' if cond else 'q'
    model['primary'] = primary
    # the weekly chain over (centre-vs-cash quadrant, index quadrant)
    chain = None
    if cond:
        C = TR.Chain(Q, H, IQ, ok, True)
        P1 = C.matrix(W)
        cev = {}
        for k in HORIZONS:
            cqk = np.cumsum(TR.pair_counts(Q, Q, ok, k, 4), 0)
            rec = _rec()
            for o in origins(days, TEST_FROM, days[-1], W, k):
                if o - k < 0 or cqk[o - k].sum() < 100:
                    continue
                pr = C.predict(o, k)
                if pr is None:
                    continue
                m, Pm = pr
                b = Q[:, o + k][m]
                keep = b >= 0
                if not keep.any():
                    continue
                Sb, fb = TR.baselines(cqk[o - k])
                _add(rec, Pm[keep], Sb[Q[:, o][m][keep]], np.repeat(fb[None], keep.sum(), 0), b[keep])
            cev[str(k)] = summarise(rec, k)
        chain = {'states': 'centre-vs-cash quadrant × index quadrant', 'P1': np.round(P1, 5).tolist() if P1 is not None else None,
                 'eval': cev, 'labels': {k: v['label'] for k, v in cev.items()}}
    # the leader
    st, ld = leader_states(S['x'])
    lev = {str(h): eval_leader(st, ld, days, h, {'test': periods['test']})['test'] for h in HORIZONS}
    # today: the last week every index has a close
    o = int(max(t for t in range(W) if np.isfinite(P[:, t]).all()))
    rp = replay_paths(R, cash, o, method, sd=sd)
    now, lead_now = {}, None
    wts = Wv[:, o + 1] if o + 1 < W and np.isfinite(Wv[:, o + 1]).all() else vol_weights(np.concatenate([R, np.full((4, 1), np.nan)], 1))[:, o + 1]
    own = {'equal': np.full(4, 0.25), 'vol': wts, 'spy': np.array([0, 1.0, 0, 0]), 'cash': np.zeros(4)}[chosen]
    if rp is not None:
        X, Cc = rp
        Rrel_paths = relative_moves(X, Cc, chosen, wts)
    for i, t in enumerate(TICKERS):
        x, y = S['x'][i, o], S['y'][i, o]
        row = {'name': NAMES[t], 'close': r4(P[i, o], 2), 'x': r4(x, 3), 'y': r4(y, 3), 'quad': int(Q[i, o]) if Q[i, o] >= 0 else None,
               'weight': r4(own[i]) if chosen in ('equal', 'vol') else None}
        if Q[i, o] >= 0:
            s16 = int(4 * IQ[i, o] + Q[i, o]) if cond and IQ[i, o] >= 0 else None
            row['state'] = s16
            row['odds'] = {}
            for h in HORIZONS:
                hd = model['heads'][primary][str(h)]
                Pm = np.array(hd['P'])
                row['odds'][str(h)] = [round(float(v), 4) for v in (Pm[s16] if primary == 'iq' and s16 is not None else np.array(model['heads']['q'][str(h)]['P'])[Q[i, o]])]
            if chain and chain['P1'] is not None and s16 is not None:
                P1 = np.array(chain['P1'])
                dist = np.eye(16)[s16]
                weeks = []
                for _ in range(STEPS):
                    dist = dist @ P1
                    weeks.append([round(float(v), 4) for v in TR.chain_quadrant(dist, True)])
                row['chain'] = weeks
                row['paths'] = chain_paths(P1, s16)
        if rp is not None and np.isfinite(P[i, o]):
            cum = np.cumsum(X[:, i, :], 1)
            qs = np.percentile(cum, [10, 25, 50, 75, 90], axis=0)
            row['fan'] = {f'q{p}': [round(float(P[i, o] * math.exp(v)), 2) for v in qs[j]] for j, p in enumerate((10, 25, 50, 75, 90))}
            if np.isfinite(S['x'][i, o]) and not (chosen == 'spy' and t == 'SPY'):
                _, Xp, Yp = TR.step_paths(S, RS, o, np.array([i]), Rrel_paths[:, i, :][None])
                row['box'] = {str(k): [r4(np.nanpercentile(Xp[0, :, k - 1], 10), 2), r4(np.nanpercentile(Xp[0, :, k - 1], 90), 2),
                                       r4(np.nanpercentile(Yp[0, :, k - 1], 10), 2), r4(np.nanpercentile(Yp[0, :, k - 1], 90), 2)] for k in (4, 13)}
                row['fan_rrg'] = [[r4(np.nanmedian(Xp[0, :, j]), 2), r4(np.nanmedian(Yp[0, :, j]), 2)] for j in range(STEPS)]
        if np.isfinite(S['x'][i, o]) and not (chosen == 'spy' and t == 'SPY'):
            row['next_week'] = thresholds(S, RS, o, i, float(own[i]), float(P[i, o]))
        now[t] = row
    if st[o] >= 0:
        lead_now = {'order': [TICKERS[j] for j in list(itertools.permutations(range(4)))[st[o]]], 'odds': {}}
        for h in HORIZONS:
            M = leader_matrix(st, ld, W - 1, h)
            if M is not None:
                lead_now['odds'][str(h)] = {TICKERS[j]: round(float(M[0][st[o]][j]), 4) for j in range(4)}
    centre_now = None
    if cond:
        cx, cy = Sc['x'][0, o], Sc['y'][0, o]
        centre_now = {'x': r4(cx, 3), 'y': r4(cy, 3), 'quad': int(qc[o]) if qc[o] >= 0 else None}
        if rp is not None:
            cpath = (X * own[None, :, None]).sum(1) if chosen in ('equal', 'vol') else X[:, 1, :] if chosen == 'spy' else None
            if cpath is not None:
                _, Xc, Yc = TR.step_paths(Sc, RSc, o, np.array([0]), (cpath - Cc)[None])
                centre_now['box'] = {str(k): [r4(np.nanpercentile(Xc[0, :, k - 1], 10), 2), r4(np.nanpercentile(Xc[0, :, k - 1], 90), 2),
                                              r4(np.nanpercentile(Yc[0, :, k - 1], 10), 2), r4(np.nanpercentile(Yc[0, :, k - 1], 90), 2)] for k in (4, 13)}
    first = int(np.argmax(np.isfinite(levels[chosen])))
    sig = lambda a: [None if not np.isfinite(v) else float(f'{v:.6g}') for v in a[first:]]
    doc = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'week': str(days[o])[:10], 'start': str(days[first])[:10],
           'tickers': list(TICKERS), 'names': NAMES, 'centre': chosen, 'centre_names': CENTRE_NAMES, 'replay': method,
           'levels': {c: sig(v) for c, v in levels.items()},
           'weights': {t: sig(Wv[i]) for i, t in enumerate(TICKERS)},
           'compare': compare, 'coverage': cov, 'model': model, 'chain': chain, 'leader': {'eval': lev, 'labels': {h: v['label'] for h, v in lev.items()}},
           'now': now, 'leader_now': lead_now, 'centre_now': centre_now,
           'rule': ('Chosen on weekly origins 2003–2011: the highest mean over 1, 4 and 13 weeks of the quadrant matrix\'s Brier skill against '
                    'the weaker of staying put and the usual shares; within 0.002, the higher correlation of RS-Momentum with the next four '
                    'weeks\' relative return. Reported from 2012 for every centre, whatever it shows.'),
           'note': ('Weekly closes adjusted for dividends (Yahoo Finance); cash: FRED DGS3MO. Odds from walk-forward matrices fitted on all weeks '
                    'since 2002 for today\'s forecast; labels from origins since 2012 (weekly, overlapping, block bootstrap). Price ranges replay '
                    'every 13-week run of the four together; next week\'s closes hold the other three (and the bill) where they are.')}
    (public / out_name).write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')
    return doc


# ------------------------------------------------------------------ the ledger: each week's forecast frozen, then scored
def ledger_entries(doc):
    """{ticker: [quad now, odds 1/4/13, close, fan q10/q25/q75/q90 at 1/4/13]} of the live week."""
    rows = {}
    for t, r in (doc.get('now') or {}).items():
        if r.get('odds') and r.get('fan'):
            f = r['fan']
            rows[t] = {'quad': r['quad'], 'odds': r['odds'], 'close': r['close'],
                       'fan': {str(k): [f['q10'][k - 1], f['q25'][k - 1], f['q75'][k - 1], f['q90'][k - 1]] for k in HORIZONS}}
    return rows


def ledger_update(root, made_at=None, sha=None):
    """Freeze this week's index forecast (once), resolve the horizons that have passed, write public/index-ledger.json."""
    root = Path(root)
    public, led = root / 'public', root / 'ledger'
    try:
        doc = json.loads((public / 'index-rrg.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    p = led / 'index.json'
    try:
        L = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        L = {'origins': []}
    have = {e['origin'] for e in L['origins']}
    if doc['week'] not in have:
        rows = ledger_entries(doc)
        if rows:
            L['origins'].append({'origin': doc['week'], 'centre': doc['centre'], 'made_at': made_at, 'code': sha, 'rows': rows, 'outcome': {}})
    days, P = load_prices(public)
    pos = {str(d)[:10]: i for i, d in enumerate(days)}
    centre = doc['centre']
    R = log_returns(P)
    cash = cash_returns(days, bill_rates(root / 'cache' / 'macro'))
    levels = {c: level(r) for c, r in centre_returns(R, cash)[0].items()}
    RSl = relative(P, levels.get(centre, levels['vol']))
    if centre == 'spy':
        RSl[TICKERS.index('SPY')] = np.nan
    S = TR.rrg_states(RSl, N_RRG)
    Q, _ = TR.states(S['x'], S['y'])
    for e in L['origins']:
        o = pos.get(e['origin'])
        if o is None:
            continue
        for t, r in e['rows'].items():
            i = TICKERS.index(t)
            for h in HORIZONS:
                key = f'{t}|{h}'
                if key in e['outcome'] or o + h >= len(days) or not np.isfinite(P[i, o + h]):
                    continue
                e['outcome'][key] = [int(Q[i, o + h]), round(float(P[i, o + h]), 2)]
    # scores of the resolved forecasts
    summ = {}
    for h in HORIZONS:
        b, inside80, inside50, n = [], [], [], 0
        for e in L['origins']:
            for t, r in e['rows'].items():
                out = e['outcome'].get(f'{t}|{h}')
                if not out or out[0] < 0:
                    continue
                pr = np.array(r['odds'][str(h)])
                b.append(float(((pr - np.eye(4)[out[0]]) ** 2).sum()))
                lo80, lo50, hi50, hi80 = r['fan'][str(h)][0], r['fan'][str(h)][1], r['fan'][str(h)][2], r['fan'][str(h)][3]
                inside80.append(lo80 <= out[1] <= hi80); inside50.append(lo50 <= out[1] <= hi50)
                n += 1
        summ[str(h)] = {'resolved': n, 'brier': round(float(np.mean(b)), 4) if b else None,
                        'inside80': round(float(np.mean(inside80)), 4) if inside80 else None, 'inside50': round(float(np.mean(inside50)), 4) if inside50 else None}
    L['origins'] = L['origins'][-600:]
    led.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(L, separators=(',', ':')), encoding='utf-8')
    pub = {'generated_at': made_at, 'origins': len(L['origins']), 'first': L['origins'][0]['origin'] if L['origins'] else None, 'summary': summ,
           'recent': [{'origin': e['origin'], 'rows': {t: {'quad': r['quad'], 'odds4': r['odds']['4'], 'close': r['close'],
                                                           'out4': e['outcome'].get(f'{t}|4')} for t, r in e['rows'].items()}} for e in L['origins'][-12:]]}
    (public / 'index-ledger.json').write_text(json.dumps(pub, separators=(',', ':')), encoding='utf-8')
    return {'origins': len(L['origins']), 'summary': summ}


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--public', default='hist/public')
    ap.add_argument('--macro', default=None)
    a = ap.parse_args()
    d = build(a.public, a.macro)
    print(json.dumps({'centre': d['centre'], 'replay': d['replay'], 'week': d['week']}))
