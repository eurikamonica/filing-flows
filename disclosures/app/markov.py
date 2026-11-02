"""Regime-switching (Markov chain) Monte Carlo DCF for the Fair value view.

Each year a company is in one of three revenue-growth regimes and next year's regime depends only on this year's (a
first-order Markov chain). The regimes are named from what they turn out to be: on the covered companies they differ in
spread as much as in level (fast growth, uneven growth, steady growth); a regime is called a decline only when its
average growth is negative. Nothing in the model is typed in by hand; every input is
estimated or read from a live source, and its source is written out:

  history             yearly revenue growth and operating margin: the SEC's annual XBRL frames since CY2010 (the same
                      panel as the outside view, app/base_rates.py), with the latest trailing-twelve-month year from the
                      quarterly frames appended when it ends after the last annual frame. Years that start from less
                      than $10M of revenue are left out (growth from a tiny base says nothing about a regime).
  regimes             a three-state hidden Markov model (HMM; Hamilton 1989, fitted by Baum–Welch) of yearly growth,
                      pooled over every covered company of the same size bucket (market value ≥ $10B or below): each
                      regime's average growth and spread, and the chance of moving between regimes, are learned from the
                      data — no growth threshold is set by hand. With too little data the HMM gives way to fixed
                      thresholds (high growth ≥ 10%, steady 0–10%, decline < 0), and the page says so.
  transition matrix   Dirichlet posterior: the company's own (soft, HMM-weighted) year-on-year transitions added to the
                      panel's matrix, the panel weighted as K = 6 pseudo-observations per row.
  today's regime      the HMM's filtered probability of each regime in the latest year; the paths start in each regime in
                      proportion (stratified, so the split is exact).
  years 1–2           analysts' consensus revenue growth for the current and next fiscal year (Yahoo, via the
                      consensus module) when at least three analysts cover it; the spread comes from their low–high range.
  operating margin    starts at the trailing EBIT margin; each year it moves by the panel's median margin change in that
                      regime, plus a pull back toward the starting margin (κ, a pooled panel regression), plus noise (the
                      company's own quarterly margin σ, else the panel residual σ).
  cash flow           the main site's FCFF (web/fsa.js): NOPAT + D&A − capex − 10% of each revenue increase into working
                      capital. Stock-based compensation is already a cost inside GAAP operating income and is not added
                      back, so it is counted once (an earlier version deducted it a second time).
  discounting         the company's own WACC from app/valuation.py (10-year Treasury + Blume beta × ERP, bond-calibrated
                      cost of debt), 10 years, then the site's ROIC-based terminal value at 2.5%.

panel_prior() also publishes, for app/valuation_sim.py's Schwartz–Moon simulation, how persistent yearly growth is (a
pooled AR(1) regression), its residual spread, and how growth surprises and margin changes move together.

The random draws are the same for every company (mulberry32, seed 20251027): common random numbers keep comparisons
between companies and the sensitivity surfaces smooth. disclosures/docs/markov-view.js runs the identical engine in the
browser for the 3D sensitivity charts; tests/test_markov.py checks that the two agree.
"""
import math

THRESH_HIGH = 0.10
THRESH_LOW = 0.0
STATES = ('high', 'steady', 'decline')
K_PRIOR = 6.0           # prior weight per row, in pseudo-observations
YEARS = 10
N_PATHS = 2000
SEED = 20251027
LARGE = 10e9            # size buckets: market value at or above $10B
G_CLIP = (-0.5, 1.0)
MIN_BASE_REV = 10e6     # a year whose starting revenue is below this is left out of the history
HMM_MIN_SEQ = 150       # companies (with two or more years) a bucket needs for its own HMM
SD_FLOOR = 0.015        # an HMM regime's growth spread is at least 1.5 points
TERM_G = 0.025
DEFAULT_PRIOR = [[0.45, 0.45, 0.10], [0.12, 0.73, 0.15], [0.05, 0.60, 0.35]]   # only when the panel is too thin
DEFAULT_G = ([0.20, 0.05, -0.08], [0.10, 0.03, 0.07])
DEFAULT_AR = (0.4, 0.12)                                                       # growth persistence φ, residual σ


def _fin(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def state_of(g):
    return 0 if g >= THRESH_HIGH else (2 if g < THRESH_LOW else 1)


# ------------------------------------------------------------------ deterministic draws (identical in markov-view.js)
def mulberry32(seed):
    st = [seed & 0xFFFFFFFF]

    def r():
        st[0] = (st[0] + 0x6D2B79F5) & 0xFFFFFFFF
        t = st[0]
        t = ((t ^ (t >> 15)) * (1 | t)) & 0xFFFFFFFF
        t = ((t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return r


_DRAWS = {}


def draws(n=N_PATHS, years=YEARS, seed=SEED):
    """(U, Zg, Zm): flat lists of n × years uniforms and two standard normals (Box–Muller), cached."""
    key = (n, years, seed)
    if key not in _DRAWS:
        r = mulberry32(seed)

        def nrm():
            u = 0.0
            while u == 0.0:
                u = r()
            v = r()
            return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)
        U, Zg, Zm = [], [], []
        for _ in range(n * years):
            U.append(r())
            Zg.append(nrm())
            Zm.append(nrm())
        _DRAWS[key] = (U, Zg, Zm)
    return _DRAWS[key]


def start_states(p, n):
    """Each path's starting regime: today's regime, or — with the HMM's probabilities — a stratified split, path i taking
    the regime whose cumulative probability first exceeds (i + ½) ÷ n."""
    sp = p.get('start_p')
    if not sp:
        return [p['start']] * n
    cum = [sp[0], sp[0] + sp[1], 1.0]
    out = []
    for i in range(n):
        u = (i + 0.5) / n
        out.append(0 if u < cum[0] else (1 if u < cum[1] else 2))
    return out


# ------------------------------------------------------------------ the engine
def simulate(p, n=N_PATHS, dg=0.0, wacc=None, P=None, track=False):
    """Per-share values of n paths. p: the 'model' dict built by params(). dg shifts every regime's growth (and the
    consensus years); wacc and P override the model's. track=True also returns the value at each horizon t (the cash
    flows to year t plus a terminal value at t), for the density-over-time chart."""
    U, Zg, Zm = draws(n, p['years'])
    T = p['years']
    w = p['wacc'] if wacc is None else wacc
    P = P or p['P']
    cum = [(row[0], row[0] + row[1]) for row in P]
    gT, roic, tax = p['g_term'], p['roic'], p['tax']
    cap = max(w - gT, 0.01)
    reinv = 1 - gT / roic
    cons, csd = p.get('cons') or [], p.get('cons_sd') or 0.0
    g, gsd, dm = p['g'], p['g_sd'], p['dm']
    kap, msd, m0 = p['kappa'], p['m_sd'], p['m0']
    da, wc = p['da'], p['wc']
    capex = p['capex'] if isinstance(p['capex'], list) else [p['capex']]
    claims = p['debt'] + p['claims'] - p['cash']
    sh = p['shares']
    s0 = start_states(p, n)
    out = [0.0] * n
    hv = [[0.0] * n for _ in range(T)] if track else None
    for i in range(n):
        s, rev, m, pv, df = s0[i], p['rev0'], m0, 0.0, 1.0
        base = i * T
        for t in range(T):
            k = base + t
            u = U[k]
            c = cum[s]
            s = 0 if u < c[0] else (1 if u < c[1] else 2)
            if t < len(cons):
                gr = cons[t] + dg + csd * Zg[k]
            else:
                gr = g[s] + dg + gsd[s] * Zg[k]
            gr = _clamp(gr, G_CLIP[0], G_CLIP[1])
            prev = rev
            rev = prev * (1 + gr)
            m = _clamp(m + dm[s] + kap * (m0 - m) + msd * Zm[k], -0.5, 0.7)
            ebit = rev * m
            nopat = ebit * (1 - tax) if ebit > 0 else ebit
            fcff = nopat + rev * (da - capex[min(t, len(capex) - 1)]) - (rev - prev) * wc
            df /= 1 + w
            pv += fcff * df
            if track or t == T - 1:
                nxt = rev * (1 + gT)
                e1 = nxt * m
                tv = (e1 * (1 - tax) if e1 > 0 else e1) * reinv / cap
                v = (pv + tv * df - claims) / sh
                if track:
                    hv[t][i] = v
                if t == T - 1:
                    out[i] = v
    return (out, hv) if track else out


def pctile(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def summarize(vals, price):
    vals = [v for v in vals if _fin(v)]
    if len(vals) < 100:
        return None
    q = {f'p{int(k * 100)}': pctile(vals, k) for k in (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)}
    lo, hi = q['p5'], q['p95']
    bins, hist = 30, [0] * 30
    if hi > lo:
        for v in vals:
            if lo <= v <= hi:
                hist[min(bins - 1, int((v - lo) / (hi - lo) * bins))] += 1
    return {'n': len(vals), **q, 'mean': sum(vals) / len(vals),
            'p_above': sum(1 for v in vals if v > price) / len(vals) if _fin(price) and price > 0 else None,
            'hist': {'lo': lo, 'hi': hi, 'counts': hist}}


def occupancy(P, start, years=YEARS, start_p=None):
    """π_t = π_0 Pᵗ for t = 0..years (the analytic regime probabilities), from today's regime or its probabilities."""
    if start_p:
        pi = list(start_p)
    else:
        pi = [0.0, 0.0, 0.0]
        pi[start] = 1.0
    rows = [pi]
    for _ in range(years):
        pi = [sum(pi[i] * P[i][j] for i in range(3)) for j in range(3)]
        rows.append(pi)
    return rows


# ------------------------------------------------------------------ histories
def yearly(revs, ois=None):
    """From quarterly revenue (oldest first): [(growth, margin or None)] for non-overlapping trailing-twelve-month years
    ending at the latest quarter, oldest first. growth = TTM / TTM four quarters earlier − 1."""
    revs = list(revs or [])
    ois = list(ois or [])
    if len(ois) != len(revs):
        ois = [None] * (len(revs) - len(ois)) + ois if len(ois) < len(revs) else ois[-len(revs):]

    def ttm(xs, end):
        w = xs[end - 3:end + 1]
        return sum(w) if end >= 3 and len(w) == 4 and all(_fin(v) for v in w) else None
    out = []
    end = len(revs) - 1
    while end - 4 >= 3:
        a, b = ttm(revs, end), ttm(revs, end - 4)
        if not (_fin(a) and _fin(b) and b > 0 and a > 0):
            break
        if b < MIN_BASE_REV:                                # growth from a tiny base: the run of usable years ends here
            break
        o = ttm(ois, end)
        out.append((a / b - 1, o / a if _fin(o) else None))
        end -= 4
    return out[::-1]


def annual_years(a):
    """From the annual frames ({'rev': {year: v}, 'oi': {year: v}}): ([(growth, margin)], the last year) over the latest
    run of consecutive years, oldest first; a year whose starting revenue is under $10M ends the run."""
    rev, oi = (a or {}).get('rev') or {}, (a or {}).get('oi') or {}
    ys = sorted(int(y) for y, v in rev.items() if _fin(v) and v > 0)
    if len(ys) < 2:
        return [], None
    out, y = [], ys[-1]
    while (y - 1) in rev and _fin(rev.get(y - 1)) and rev[y - 1] >= MIN_BASE_REV and _fin(rev.get(y)) and rev[y] > 0:
        o = oi.get(y)
        out.append((rev[y] / rev[y - 1] - 1, o / rev[y] if _fin(o) else None))
        y -= 1
    return out[::-1], ys[-1]


def merge_years(annual, ttm, ttm_end_year):
    """The annual history, with the latest trailing-twelve-month year appended when it ends in a later calendar year
    than the last annual frame; the quarterly history alone when there are no annual frames."""
    hist, last = annual if isinstance(annual, tuple) else (annual or [], None)
    if not hist:
        return list(ttm or [])
    out = list(hist)
    if ttm and _fin(ttm_end_year) and last is not None and ttm_end_year > last:
        out.append(ttm[-1])
    return out


def bucket_of(mcap):
    return 'large' if _fin(mcap) and mcap >= LARGE else 'small'


def _winsor_mean_sd(xs):
    xs = [_clamp(x, G_CLIP[0], G_CLIP[1]) for x in xs if _fin(x)]
    if len(xs) < 2:
        return None, None
    m = sum(xs) / len(xs)
    return m, math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


SD_SHRINK_K = 4.0       # pseudo-years of the panel's growth surprise in a company's own growth spread (app/sim_backtest.py)


def shrunk_sd(gs, panel_sd, k=SD_SHRINK_K):
    """(σ, how): a company's spread of yearly growth over its last five years, shrunk toward the panel's growth surprise
    (the AR(1) residual) with k pseudo-years: √((n σ_own² + k σ_panel²) ÷ (n + k)), n = the own years less one. Own
    spreads from a few years understate what can happen: alone they put 61% of actual three-year revenues inside the 80%
    range in the backtest; shrunk at k = 4, 81%."""
    own = _winsor_mean_sd(gs[-5:])[1] if len(gs) >= 3 else None
    if not _fin(panel_sd):
        return own, 'own'
    if not _fin(own):
        return panel_sd, 'panel'
    n = min(len(gs), 5) - 1
    return math.sqrt((n * own * own + k * panel_sd * panel_sd) / (n + k)), 'shrunk'


# ------------------------------------------------------------------ the hidden Markov model (three Gaussian regimes)
def _npdf(x, mu, sd):
    z = (x - mu) / sd
    return max(math.exp(-0.5 * z * z) / (sd * 2.5066282746310002), 1e-300)


def _fb(xs, mu, sd, P, pi):
    """Scaled forward–backward for one sequence: (γ per year, Σ ξ as a 3 × 3 table, log-likelihood)."""
    T = len(xs)
    B = [[_npdf(x, mu[j], sd[j]) for j in range(3)] for x in xs]
    alpha, c = [], []
    a = [pi[j] * B[0][j] for j in range(3)]
    ct = sum(a) or 1e-300
    alpha.append([v / ct for v in a])
    c.append(ct)
    for t in range(1, T):
        prev = alpha[-1]
        a = [sum(prev[i] * P[i][j] for i in range(3)) * B[t][j] for j in range(3)]
        ct = sum(a) or 1e-300
        alpha.append([v / ct for v in a])
        c.append(ct)
    beta = [[1.0, 1.0, 1.0] for _ in range(T)]
    for t in range(T - 2, -1, -1):
        nb = [B[t + 1][j] * beta[t + 1][j] for j in range(3)]
        beta[t] = [sum(P[i][j] * nb[j] for j in range(3)) / c[t + 1] for i in range(3)]
    gamma = []
    for t in range(T):
        g = [alpha[t][j] * beta[t][j] for j in range(3)]
        s = sum(g) or 1e-300
        gamma.append([v / s for v in g])
    xi = [[0.0] * 3 for _ in range(3)]
    for t in range(T - 1):
        for i in range(3):
            for j in range(3):
                xi[i][j] += alpha[t][i] * P[i][j] * B[t + 1][j] * beta[t + 1][j] / c[t + 1]
    return gamma, xi, sum(math.log(v) for v in c)


def _threshold_init(seqs):
    groups, counts, first = [[], [], []], [[1.0] * 3 for _ in range(3)], [1.0] * 3
    for xs in seqs:
        st = [state_of(x) for x in xs]
        first[st[0]] += 1
        for x, s in zip(xs, st):
            groups[s].append(x)
        for a, b in zip(st, st[1:]):
            counts[a][b] += 1
    mu, sd = [], []
    for s in range(3):
        m, d = _winsor_mean_sd(groups[s]) if len(groups[s]) >= 2 else (DEFAULT_G[0][s], DEFAULT_G[1][s])
        mu.append(m)
        sd.append(max(d or DEFAULT_G[1][s], SD_FLOOR))
    P = [[v / sum(r) for v in r] for r in counts]
    return mu, sd, P, [v / sum(first) for v in first]


def hmm_fit(seqs, init=None, iters=150, tol=1e-7):
    """Baum–Welch for a three-regime Gaussian HMM pooled over many short sequences (each company's yearly growth,
    clipped at −50% / +100%). Started from the threshold classification (or `init`); regimes sorted by mean growth,
    highest first. None when there is too little data or a regime ends up nearly empty (under 2% of the years)."""
    seqs = [[_clamp(x, G_CLIP[0], G_CLIP[1]) for x in s if _fin(x)] for s in seqs]
    seqs = [s for s in seqs if s]
    n_obs = sum(len(s) for s in seqs)
    if len(seqs) < 30 or n_obs < 200:
        return None
    if init:
        mu, sd, P, pi = list(init['mu']), list(init['sd']), [list(r) for r in init['P']], list(init['pi'])
    else:
        mu, sd, P, pi = _threshold_init(seqs)
    prev, ll, it = -math.inf, -math.inf, 0
    w = [0.0] * 3
    for it in range(1, iters + 1):
        a_pi, a_xi = [0.0] * 3, [[0.0] * 3 for _ in range(3)]
        a_g, a_gx, a_gxx = [0.0] * 3, [0.0] * 3, [0.0] * 3
        ll = 0.0
        for xs in seqs:
            gamma, xi, l = _fb(xs, mu, sd, P, pi)
            ll += l
            for j in range(3):
                a_pi[j] += gamma[0][j]
            for t, x in enumerate(xs):
                for j in range(3):
                    gj = gamma[t][j]
                    a_g[j] += gj
                    a_gx[j] += gj * x
                    a_gxx[j] += gj * x * x
            for i in range(3):
                for j in range(3):
                    a_xi[i][j] += xi[i][j]
        pi = [(v + 1e-9) / (sum(a_pi) + 3e-9) for v in a_pi]
        P = [[(a_xi[i][j] + 1e-9) / (sum(a_xi[i]) + 3e-9) for j in range(3)] if sum(a_xi[i]) > 0 else P[i] for i in range(3)]
        for j in range(3):
            if a_g[j] > 1e-9:
                mu[j] = a_gx[j] / a_g[j]
                sd[j] = max(math.sqrt(max(a_gxx[j] / a_g[j] - mu[j] ** 2, 0.0)), SD_FLOOR)
        w = [v / n_obs for v in a_g]
        if ll - prev < tol * abs(ll):
            break
        prev = ll
    order = sorted(range(3), key=lambda j: -mu[j])
    fit = {'mu': [mu[j] for j in order], 'sd': [sd[j] for j in order], 'P': [[P[i][j] for j in order] for i in order],
           'pi': [pi[j] for j in order], 'weights': [w[j] for j in order], 'll': ll, 'n_obs': n_obs, 'n_seq': len(seqs), 'iters': it}
    if min(fit['weights']) < 0.02:
        return None
    return fit


def hmm_posterior(xs, fit):
    """One company's history under a fitted HMM: the probability of each regime in each year (γ), its soft transition
    counts (Σ ξ) and the regime probabilities in the latest year."""
    xs = [_clamp(x, G_CLIP[0], G_CLIP[1]) for x in xs if _fin(x)]
    if not xs:
        return None
    gamma, xi, ll = _fb(xs, fit['mu'], fit['sd'], fit['P'], fit['pi'])
    return {'gamma': gamma, 'xi': xi, 'now': gamma[-1], 'll': ll}


THRESHOLD_LABELS = ['High growth', 'Steady', 'Decline']


def regime_labels(g, sd, method):
    """Names for the three regimes from what they are: the fixed thresholds' names, or — for the HMM, whose regimes can
    differ in spread as much as in level — 'fast growth' for the highest, 'decline' for one whose average is negative, and
    otherwise 'uneven' and 'steady' growth when one of the other two varies far more than the other, else by level."""
    if method != 'hmm':
        return list(THRESHOLD_LABELS)
    out = ['Fast growth' if g[0] >= 0.15 else 'Higher growth', None, None]
    rest = [1, 2]
    for j in rest:
        if g[j] < 0:
            out[j] = 'Decline'
    free = [j for j in rest if out[j] is None]
    if len(free) == 2:
        a, b = free
        if sd[a] > 1.6 * sd[b]:
            out[a], out[b] = 'Uneven growth', 'Steady growth'
        elif sd[b] > 1.6 * sd[a]:
            out[a], out[b] = 'Steady growth', 'Uneven growth'
        else:
            out[a], out[b] = 'Moderate growth', 'Slow growth'
    elif len(free) == 1:
        out[free[0]] = 'Moderate growth'
    return out


# ------------------------------------------------------------------ the panel
def _stats(G, up, fit, shared=False):
    """One bucket's estimates. G: [(years, ...)] companies with two or more years. A row or regime with too few
    observations takes the whole panel's (`up`), and only when the whole panel is thin too, the fixed fallback — each such
    case is listed in 'thin'."""
    thin = []
    counts = [[0.0] * 3 for _ in range(3)]
    g_by = [[], [], []]
    dm_by = [[], [], []]
    rev_x, rev_y, ar_x, ar_y, gm, loss, prof = [], [], [], [], [], [], []
    occ = [0.0, 0.0, 0.0]
    for ys in G:
        gs = [g for g, _ in ys]
        if fit:
            post = hmm_posterior(gs, fit)
            st = [max(range(3), key=lambda j: row[j]) for row in post['gamma']]
            for i in range(3):
                for j in range(3):
                    counts[i][j] += post['xi'][i][j]
            for row in post['gamma']:
                for j in range(3):
                    occ[j] += row[j]
        else:
            st = [state_of(g) for g in gs]
            for a, b in zip(st, st[1:]):
                counts[a][b] += 1
            for s in st:
                occ[s] += 1
        for g, s in zip(gs, st):
            g_by[s].append(g)
        ms = [m for _, m in ys if _fin(m)]
        mbar = sum(ms) / len(ms) if ms else None
        for (g1, m1), (g2, m2), s in zip(ys, ys[1:], st[1:]):
            ar_x.append(_clamp(g1, *G_CLIP))
            ar_y.append(_clamp(g2, *G_CLIP))
            if _fin(m1) and _fin(m2):                       # loss-makers' path to profit (app/valuation_sim.py)
                if -1.0 <= m1 < 0:
                    loss.append((m1, _clamp(m2 - m1, -0.5, 0.5)))
                elif 0 <= m1 < 0.6:
                    prof.append(_clamp(m2 - m1, -0.5, 0.5))
            if _fin(m1) and _fin(m2) and abs(m2 - m1) < 0.5:
                dm_by[s].append(m2 - m1)
                gm.append((_clamp(g1, *G_CLIP), _clamp(g2, *G_CLIP), m2 - m1))
                if _fin(mbar) and len(ms) >= 3:
                    rev_x.append(mbar - m1)
                    rev_y.append(m2 - m1)
    n_rows = [sum(r) for r in counts]
    if fit:
        P = [list(r) for r in fit['P']]
        g = list(fit['mu'])
        gsd = [_clamp(v, 0.01, 0.40) for v in fit['sd']]
        if shared:
            thin.append('regimes from the whole panel\'s HMM (too few companies in this size bucket for their own)')
    else:
        P = []
        for i in range(3):
            if n_rows[i] >= 20:
                P.append([(counts[i][j] + 0.5) / (n_rows[i] + 1.5) for j in range(3)])
            elif up:
                P.append(up['P'][i])
                thin.append(f'{STATES[i]} row from the whole panel')
            else:
                P.append(DEFAULT_PRIOR[i])
                thin.append(f'{STATES[i]} row: fixed fallback')
        g, gsd = [], []
        for s in range(3):
            m, sd = _winsor_mean_sd(g_by[s])
            if len(g_by[s]) >= 20:
                g.append(m)
                gsd.append(_clamp(sd, 0.01, 0.40))
            elif up:
                g.append(up['g'][s])
                gsd.append(up['g_sd'][s])
                thin.append(f'{STATES[s]} growth from the whole panel')
            else:
                g.append(DEFAULT_G[0][s])
                gsd.append(DEFAULT_G[1][s])
                thin.append(f'{STATES[s]} growth: fixed fallback')
    dm = []
    for s in range(3):
        xs = sorted(dm_by[s])
        dm.append(_clamp(xs[len(xs) // 2], -0.05, 0.05) if len(xs) >= 20 else (up['dm'][s] if up else 0.0))   # median: robust to one-off charges
    kappa, msd = (up['kappa'], up['m_sd']) if up else (0.3, 0.02)
    if len(rev_x) >= 30:
        mx, my = sum(rev_x) / len(rev_x), sum(rev_y) / len(rev_y)
        sxx = sum((x - mx) ** 2 for x in rev_x)
        if sxx > 0:
            b = sum((x - mx) * (y - my) for x, y in zip(rev_x, rev_y)) / sxx
            a = my - b * mx
            kappa = _clamp(b, 0.05, 0.8)
            res = [y - a - b * x for x, y in zip(rev_x, rev_y)]
            msd = _clamp(math.sqrt(sum(r * r for r in res) / max(1, len(res) - 2)), 0.005, 0.08)
    elif not up:
        thin.append('margin pull-back: fixed fallback')
    # growth persistence: g(t+1) = a + φ g(t) + e, pooled; and how growth surprises and margin changes move together
    phi, ga, gres, rho = (up['g_phi'], up['g_a'], up['g_res_sd'], up['rho_gm']) if up else (DEFAULT_AR[0], TERM_G * (1 - DEFAULT_AR[0]), DEFAULT_AR[1], 0.0)
    if len(ar_x) >= 100:
        mx, my = sum(ar_x) / len(ar_x), sum(ar_y) / len(ar_y)
        sxx = sum((x - mx) ** 2 for x in ar_x)
        if sxx > 0:
            b = sum((x - mx) * (y - my) for x, y in zip(ar_x, ar_y)) / sxx
            phi, ga = _clamp(b, 0.0, 0.95), my - b * mx
            res = [y - ga - phi * x for x, y in zip(ar_x, ar_y)]
            gres = _clamp(math.sqrt(sum(r * r for r in res) / max(1, len(res) - 2)), 0.02, 0.40)
    elif not up:
        thin.append('growth persistence: fixed fallback')
    if len(gm) >= 100:
        e = [g2 - ga - phi * g1 for g1, g2, _ in gm]
        d = [x for _, _, x in gm]
        me, md = sum(e) / len(e), sum(d) / len(d)
        se = math.sqrt(sum((x - me) ** 2 for x in e))
        sd_ = math.sqrt(sum((x - md) ** 2 for x in d))
        if se > 0 and sd_ > 0:
            rho = _clamp(sum((x - me) * (y - md) for x, y in zip(e, d)) / (se * sd_), -0.9, 0.9)
    lk = _loss_margins(loss, prof, up)
    if lk.pop('_thin', False):
        thin.append('loss-makers\' margins: from the whole panel' if up else 'loss-makers\' margins: fixed fallback')
    tot = sum(occ) or 1.0
    return {**lk, 'method': 'hmm' if fit else 'thresholds', 'labels': regime_labels(g, gsd, 'hmm' if fit else 'thresholds'), 'P': P, 'counts': [[round(v, 2) for v in r] for r in counts], 'firms': len(G),
            'transitions': round(sum(n_rows), 1), 'g': g, 'g_sd': gsd, 'g_n': [round(v, 1) for v in occ], 'occupancy': [v / tot for v in occ],
            'dm': dm, 'kappa': kappa, 'm_sd': msd, 'kappa_n': len(rev_x), 'g_phi': phi, 'g_a': ga, 'g_res_sd': gres, 'g_pairs': len(ar_x),
            'rho_gm': rho, 'rho_n': len(gm), 'thin': thin,
            'hmm': {k: fit[k] for k in ('mu', 'sd', 'P', 'pi', 'weights', 'll', 'n_obs', 'n_seq', 'iters')} if fit else None}


def _mad_sd(xs):
    c = sorted(xs)[len(xs) // 2]
    return 1.4826 * sorted(abs(x - c) for x in xs)[len(xs) // 2]


def _loss_margins(loss, prof, up):
    """How loss-making companies' operating margins move: Δm = a − κ_loss × m + e over company-years with a margin between
    −100% and 0 (Δm winsorized at ±50 points), and how big the surprise e is — larger the deeper the loss: its robust
    spread (1.4826 × the median absolute deviation) in five bins of |m|, fitted as s0 + s1 × |m|. For profitable years, the
    robust spread of Δm. Too few observations: the whole panel's, else a stated fallback."""
    if len(loss) < 300 or len(prof) < 300:
        if up:
            return {k: up[k] for k in ('loss_kappa', 'loss_a', 'loss_sd0', 'loss_sd1', 'prof_sd', 'loss_n')} | {'_thin': True}
        return {'loss_kappa': 0.2, 'loss_a': -0.01, 'loss_sd0': 0.05, 'loss_sd1': 0.4, 'prof_sd': 0.035, 'loss_n': len(loss), '_thin': True}
    X, Y = [m for m, _ in loss], [d for _, d in loss]
    mx, my = sum(X) / len(X), sum(Y) / len(Y)
    b = sum((x - mx) * (y - my) for x, y in zip(X, Y)) / (sum((x - mx) ** 2 for x in X) or 1.0)
    a = my - b * mx
    kap = _clamp(-b, 0.05, 0.8)
    res = sorted(((abs(x), y - a - b * x) for x, y in zip(X, Y)), key=lambda t: t[0])
    k = len(res) // 5
    pts = [(sum(r[0] for r in res[i * k:(i + 1) * k]) / k, _mad_sd([r[1] for r in res[i * k:(i + 1) * k]])) for i in range(5)]
    px, py = sum(x for x, _ in pts) / 5, sum(y for _, y in pts) / 5
    s1 = sum((x - px) * (y - py) for x, y in pts) / (sum((x - px) ** 2 for x, _ in pts) or 1.0)
    s1 = _clamp(s1, 0.0, 0.8)
    s0 = _clamp(py - s1 * px, 0.01, 0.10)
    return {'loss_kappa': kap, 'loss_a': _clamp(a, -0.10, 0.10), 'loss_sd0': s0, 'loss_sd1': s1, 'prof_sd': _clamp(_mad_sd(prof), 0.01, 0.10),
            'loss_n': len(loss)}


def panel_prior(companies):
    """companies: iterable of dicts with 'years' ([(growth, margin)], oldest first) and 'mcap'. Per size bucket and for
    the whole panel ('all'): the HMM's regimes and transition matrix (or the threshold counts), regime growth, regime
    margin drift, the margin pull-back κ, growth persistence and the growth–margin correlation."""
    cos = [c for c in companies if len(c.get('years') or []) >= 2]
    groups = {'all': [c['years'] for c in cos]}
    for c in cos:
        groups.setdefault(bucket_of(c.get('mcap')), []).append(c['years'])
    fit_all = hmm_fit([[g for g, _ in ys] for ys in groups['all']]) if len(groups['all']) >= HMM_MIN_SEQ else None
    out = {'all': _stats(groups['all'], None, fit_all)}
    for name in sorted(k for k in groups if k != 'all'):
        G = groups[name]
        fit, shared = fit_all, True
        if fit_all and len(G) >= HMM_MIN_SEQ:
            own = hmm_fit([[g for g, _ in ys] for ys in G], init=fit_all)
            if own:
                fit, shared = own, False
        out[name] = _stats(G, out['all'], fit, shared=shared and fit is not None)
    return out


def posterior(own_counts, prior_P, k=K_PRIOR):
    """Row-wise Dirichlet posterior mean: (own counts + k × prior row) ÷ (row total + k)."""
    return [[(own_counts[i][j] + k * prior_P[i][j]) / (sum(own_counts[i]) + k) for j in range(3)] for i in range(3)]


def consensus_growth(cons_c, price_date=None, rev0=None):
    """[year-1, year-2] consensus revenue growth (decimals) and their spread from the analysts' low–high range."""
    per = {p.get('period'): p for p in ((cons_c or {}).get('analysts') or {}).get('periods') or []}
    gs, sds, how = [], [], []
    for key, label in (('0y', 'current fiscal year'), ('+1y', 'next fiscal year')):
        p = per.get(key) or {}
        r = p.get('rev') or {}
        n = r.get('numberOfAnalysts')
        if p.get('end') and price_date and str(p['end'])[:10] < str(price_date)[:10]:
            continue                                        # that fiscal year is over: its growth is history, not a forecast
        if not (_fin(r.get('growth')) and _fin(n) and n >= 3 and -0.5 < r['growth'] < 1.5):
            break
        gs.append(r['growth'])
        if _fin(r.get('low')) and _fin(r.get('high')) and _fin(r.get('avg')) and r['avg'] > 0:
            sds.append(_clamp((r['high'] - r['low']) / r['avg'] / 4, 0.005, 0.10))
        how.append(f"{label}: {r['growth'] * 100:.1f}% ({int(n)} analysts)")
    if not gs:
        return [], None, None
    return gs, (sum(sds) / len(sds) if sds else 0.02), '; '.join(how)


def params(F, base, W, years_hist, prior_b, cons_c=None, price_date=None, sd_scale=1.0):
    """The model for one company, every number with its source. base: the site's base DCF inputs (valuation.analyse).
    sd_scale: every regime's growth spread × this — the factor the walk-forward backtest fits so that the 80% range of
    revenue three years out holds 80% of what happened (app/sim_backtest.py; 1 without a backtest)."""
    if not (prior_b and years_hist and base and W):
        return None
    gs = [g for g, _ in years_hist]
    hmm = prior_b.get('hmm') if prior_b.get('method') == 'hmm' else None
    start_p = None
    if hmm:
        post = hmm_posterior(gs, hmm)
        own = post['xi']
        start_p = [round(v, 6) for v in post['now']]
        tot = sum(start_p)
        start_p = [v / tot for v in start_p]
        st = [max(range(3), key=lambda j: row[j]) for row in post['gamma']]
    else:
        st = [state_of(g) for g in gs]
        own = [[0] * 3 for _ in range(3)]
        for a, b in zip(st, st[1:]):
            own[a][b] += 1
    P = posterior(own, prior_b['P'])
    cons, csd, cons_how = consensus_growth(cons_c, price_date)
    sm = F.get('sm')
    m_sd = _clamp(sm, 0.005, 0.08) if _fin(sm) else prior_b['m_sd']
    start = max(range(3), key=lambda j: start_p[j]) if start_p else st[-1]
    sd_scale = sd_scale if _fin(sd_scale) and 0.5 <= sd_scale <= 3 else 1.0
    model = {'years': YEARS, 'start': start, 'P': P, 'g': prior_b['g'], 'g_sd': [v * sd_scale for v in prior_b['g_sd']], 'cons': cons, 'cons_sd': csd or 0.0,
             'dm': prior_b['dm'], 'kappa': prior_b['kappa'], 'm_sd': m_sd, 'm0': base['margin'] if not isinstance(base['margin'], list) else base['margin'][0],
             'rev0': base['rev0'], 'tax': base['tax'], 'da': base['da'], 'capex': base['capex'], 'wc': base['wc'],
             'wacc': W['wacc'], 'g_term': base['g'], 'roic': base['roic'], 'debt': base['debt'], 'cash': base['cash'],
             'claims': base['claims'], 'shares': base['shares']}
    if start_p:
        model['start_p'] = start_p
    hm = prior_b.get('hmm') or {}
    src = {'matrix': (f"own transitions ({sum(map(sum, own)):.1f}, weighted by the HMM's regime probabilities) + the panel's HMM matrix "
                      f"({prior_b['firms']} companies, {hm.get('n_obs', 0)} company-years) at K = {K_PRIOR:g}") if hmm else
                     f"own regime transitions ({sum(map(sum, own))}) + panel prior ({prior_b['transitions']} transitions, {prior_b['firms']} companies) at K = {K_PRIOR:g}",
           'regimes': (f"hidden Markov model of yearly growth, pooled over {hm.get('n_seq')} companies ({hm.get('n_obs')} company-years, "
                       f"annual XBRL frames since 2010): regimes average {', '.join(f'{v * 100:+.1f}%' for v in prior_b['g'])}") if hmm else
                      'fixed thresholds: high growth ≥ 10%, steady 0–10%, decline < 0 (too little history for the HMM)',
           'now': ('the HMM\'s probability of each regime in the latest year: ' + ' / '.join(f'{v * 100:.0f}%' for v in start_p)) if start_p else
                  f'the latest year\'s growth ({gs[-1] * 100:+.1f}%) sets the regime',
           'growth': (f"the HMM's regime means and spreads ({'/'.join(f'{v:.0f}' for v in prior_b['g_n'])} company-years per regime)" if hmm else
                      f"panel means by regime ({'/'.join(f'{v:.0f}' for v in prior_b['g_n'])} company-years)")
                     + (f"; spreads × {sd_scale:g}, fitted in the walk-forward backtest so that the 80% range of revenue three years out holds about "
                        "80% of what happened (as estimated, the spreads made it too narrow)" if sd_scale != 1.0 else ''),
           'years_1_2': cons_how or 'no consensus with ≥ 3 analysts: the regime model from year 1',
           'margin': f"trailing EBIT margin {model['m0'] * 100:.1f}%; regime drift = panel median; κ = {prior_b['kappa']:.2f} (pooled regression, {prior_b['kappa_n']} pairs)",
           'margin_sd': 'company quarterly EBIT-margin σ' if _fin(sm) else 'panel residual σ',
           'sbc': 'already a cost inside GAAP operating income, so counted once (not added back, not deducted again)',
           'wacc': 'the company WACC above (Treasury + Blume beta × ERP, bond-calibrated cost of debt)',
           'terminal': f"{base['g'] * 100:.1f}% growth, reinvestment = g ÷ ROIC ({base['roic'] * 100:.0f}%)"}
    if prior_b.get('thin'):
        src['thin'] = 'too few observations in this size bucket: ' + '; '.join(prior_b['thin'])
    return {'model': model, 'method': prior_b.get('method', 'thresholds'),
            'labels': prior_b.get('labels') or regime_labels(prior_b['g'], prior_b['g_sd'], prior_b.get('method', 'thresholds')),
            'own_counts': [[round(v, 3) for v in r] for r in own],
            'history': [[round(g, 4), (round(m, 4) if _fin(m) else None)] for g, m in years_hist],
            'states': st,
            'prior': {'P': prior_b['P'], 'counts': prior_b['counts'], 'firms': prior_b['firms'], 'transitions': prior_b['transitions']},
            'k': K_PRIOR, 'sources': src}


def run(F, base, W, years_hist, prior_b, price, cons_c=None, price_date=None, sd_scale=1.0):
    """The 'markov' block of a company's Fair value document, or None."""
    pr = params(F, base, W, years_hist, prior_b, cons_c, price_date, sd_scale)
    if not pr:
        return None
    vals = simulate(pr['model'])
    s = summarize(vals, price)
    if not s:
        return None
    pr.update(s)
    pr['seed'] = SEED
    pr['occupancy'] = occupancy(pr['model']['P'], pr['model']['start'], start_p=pr['model'].get('start_p'))
    return pr
