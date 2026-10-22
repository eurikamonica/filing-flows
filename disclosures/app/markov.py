"""Regime-switching (Markov chain) Monte Carlo DCF for the Fair value view.

Each year a company is in one of three revenue-growth regimes — high growth (trailing-year revenue growth ≥ 10%), steady
(0–10%) or decline (< 0) — and next year's regime depends only on this year's (a first-order Markov chain). Nothing in
the model is typed in by hand; every input is estimated or read from a live source, and its source is written out:

  transition matrix   Dirichlet posterior: the company's own year-on-year regime transitions (from its trailing-twelve-
                      month revenue history) added to a prior estimated from the whole covered panel of the same size
                      bucket (market value ≥ $10B or below), the prior weighted as K = 6 pseudo-observations per row.
  regime growth       panel mean and standard deviation of yearly growth inside each regime (same size bucket),
                      winsorized at −50% / +100%.
  years 1–2           analysts' consensus revenue growth for the current and next fiscal year (Yahoo, via the
                      consensus module) when at least three analysts cover it; the spread comes from their low–high range.
  operating margin    starts at the trailing EBIT margin; each year it moves by the panel's mean margin change in that
                      regime, plus a pull back toward the starting margin (κ, a pooled panel regression), plus noise (the
                      company's own quarterly margin σ, else the panel residual σ).
  cash flow           the main site's FCFF (web/fsa.js): NOPAT + D&A − capex − 10% of each revenue increase into working
                      capital, minus stock-based compensation as a share of revenue (latest annual XBRL), because
                      issuing shares to staff is a real cost to existing holders.
  discounting         the company's own WACC from app/valuation.py (10-year Treasury + Blume beta × ERP, bond-calibrated
                      cost of debt), 10 years, then the site's ROIC-based terminal value at 2.5%.

The random draws are the same for every company (mulberry32, seed 20251027): common random numbers keep comparisons
between companies and the sensitivity surfaces smooth. disclosures/docs/markov-view.js runs the identical engine in the
browser for the 3D sensitivity charts; tests/test_markov_valuation.py checks that the two agree.
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
DEFAULT_PRIOR = [[0.45, 0.45, 0.10], [0.12, 0.73, 0.15], [0.05, 0.60, 0.35]]   # only when the panel is too thin
DEFAULT_G = ([0.20, 0.05, -0.08], [0.10, 0.03, 0.07])


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
    da, wc, sbc = p['da'], p['wc'], p['sbc']
    capex = p['capex'] if isinstance(p['capex'], list) else [p['capex']]
    claims = p['debt'] + p['claims'] - p['cash']
    sh = p['shares']
    out = [0.0] * n
    hv = [[0.0] * n for _ in range(T)] if track else None
    for i in range(n):
        s, rev, m, pv, df = p['start'], p['rev0'], m0, 0.0, 1.0
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
            fcff = nopat + rev * (da - capex[min(t, len(capex) - 1)] - sbc) - (rev - prev) * wc
            df /= 1 + w
            pv += fcff * df
            if track or t == T - 1:
                nxt = rev * (1 + gT)
                e1 = nxt * m
                tv = ((e1 * (1 - tax) if e1 > 0 else e1) * reinv - nxt * sbc) / cap
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


def occupancy(P, start, years=YEARS):
    """π_t = π_0 Pᵗ for t = 0..years (the analytic regime probabilities)."""
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
        o = ttm(ois, end)
        out.append((a / b - 1, o / a if _fin(o) else None))
        end -= 4
    return out[::-1]


def bucket_of(mcap):
    return 'large' if _fin(mcap) and mcap >= LARGE else 'small'


def _winsor_mean_sd(xs):
    xs = [_clamp(x, G_CLIP[0], G_CLIP[1]) for x in xs if _fin(x)]
    if len(xs) < 2:
        return None, None
    m = sum(xs) / len(xs)
    return m, math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def panel_prior(companies):
    """companies: iterable of dicts with 'years' (from yearly()) and 'mcap'. Per size bucket: transition counts and the
    prior matrix, regime growth mean / σ, regime margin change, and the pooled margin reversion κ with its residual σ."""
    new = lambda: {'counts': [[0] * 3 for _ in range(3)], 'g': [[], [], []], 'dm': [[], [], []], 'rev_x': [], 'rev_y': [], 'firms': 0}
    acc = {'all': new()}
    for c in companies:
        ys = c.get('years') or []
        if len(ys) < 2:
            continue
        st = [state_of(g) for g, _ in ys]
        ms = [m for _, m in ys if _fin(m)]
        mbar = sum(ms) / len(ms) if ms else None
        for B in (acc.setdefault(bucket_of(c.get('mcap')), new()), acc['all']):
            B['firms'] += 1
            for (g, _), s in zip(ys, st):
                B['g'][s].append(g)
            for a, b in zip(st, st[1:]):
                B['counts'][a][b] += 1
            for (_, m1), (_, m2), s in zip(ys, ys[1:], st[1:]):
                if _fin(m1) and _fin(m2) and abs(m2 - m1) < 0.5:
                    B['dm'][s].append(m2 - m1)
                    if _fin(mbar) and len(ms) >= 3:
                        B['rev_x'].append(mbar - m1)
                        B['rev_y'].append(m2 - m1)

    def stats(B, up):
        """One bucket's estimates; a row or regime with too few observations takes the whole panel's (`up`), and only
        when the whole panel is thin too, the fixed fallback — each such case is listed in 'thin'."""
        thin = []
        n_rows = [sum(r) for r in B['counts']]
        P = []
        for i in range(3):
            if n_rows[i] >= 20:
                P.append([(B['counts'][i][j] + 0.5) / (n_rows[i] + 1.5) for j in range(3)])
            elif up:
                P.append(up['P'][i])
                thin.append(f'{STATES[i]} row from the whole panel')
            else:
                P.append(DEFAULT_PRIOR[i])
                thin.append(f'{STATES[i]} row: fixed fallback')
        g, gsd = [], []
        for s in range(3):
            m, sd = _winsor_mean_sd(B['g'][s])
            if len(B['g'][s]) >= 20:
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
            xs = sorted(B['dm'][s])
            dm.append(_clamp(xs[len(xs) // 2], -0.05, 0.05) if len(xs) >= 20 else (up['dm'][s] if up else 0.0))   # median: robust to one-off charges
        kappa, msd = (up['kappa'], up['m_sd']) if up else (0.3, 0.02)
        X, Y = B['rev_x'], B['rev_y']
        if len(X) >= 30:
            mx, my = sum(X) / len(X), sum(Y) / len(Y)
            sxx = sum((x - mx) ** 2 for x in X)
            if sxx > 0:
                b = sum((x - mx) * (y - my) for x, y in zip(X, Y)) / sxx
                a = my - b * mx
                kappa = _clamp(b, 0.05, 0.8)
                res = [y - a - b * x for x, y in zip(X, Y)]
                msd = _clamp(math.sqrt(sum(r * r for r in res) / max(1, len(res) - 2)), 0.005, 0.08)
        elif not up:
            thin.append('margin pull-back: fixed fallback')
        return {'P': P, 'counts': B['counts'], 'firms': B['firms'], 'transitions': sum(n_rows), 'g': g, 'g_sd': gsd,
                'g_n': [len(x) for x in B['g']], 'dm': dm, 'kappa': kappa, 'm_sd': msd, 'kappa_n': len(X), 'thin': thin}
    out = {'all': stats(acc['all'], None)}
    for name, B in acc.items():
        if name != 'all':
            out[name] = stats(B, out['all'])
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


def params(F, base, W, years_hist, prior_b, cons_c=None, price_date=None):
    """The model for one company, every number with its source. base: the site's base DCF inputs (valuation.analyse)."""
    if not (prior_b and years_hist and base and W):
        return None
    st = [state_of(g) for g, _ in years_hist]
    own = [[0] * 3 for _ in range(3)]
    for a, b in zip(st, st[1:]):
        own[a][b] += 1
    P = posterior(own, prior_b['P'])
    cons, csd, cons_how = consensus_growth(cons_c, price_date)
    sm = F.get('sm')
    m_sd = _clamp(sm, 0.005, 0.08) if _fin(sm) else prior_b['m_sd']
    sbc = F.get('sbc')
    sbc_share = _clamp(sbc / F['revenue'], 0.0, 0.5) if _fin(sbc) and sbc > 0 and _fin(F.get('revenue')) and F['revenue'] > 0 else 0.0
    model = {'years': YEARS, 'start': st[-1], 'P': P, 'g': prior_b['g'], 'g_sd': prior_b['g_sd'], 'cons': cons, 'cons_sd': csd or 0.0,
             'dm': prior_b['dm'], 'kappa': prior_b['kappa'], 'm_sd': m_sd, 'm0': base['margin'] if not isinstance(base['margin'], list) else base['margin'][0],
             'rev0': base['rev0'], 'tax': base['tax'], 'da': base['da'], 'capex': base['capex'], 'wc': base['wc'], 'sbc': sbc_share,
             'wacc': W['wacc'], 'g_term': base['g'], 'roic': base['roic'], 'debt': base['debt'], 'cash': base['cash'],
             'claims': base['claims'], 'shares': base['shares']}
    src = {'matrix': f"own regime transitions ({sum(map(sum, own))}) + panel prior ({prior_b['transitions']} transitions, {prior_b['firms']} companies) at K = {K_PRIOR:g}",
           'growth': f"panel means by regime ({'/'.join(str(n) for n in prior_b['g_n'])} company-years)",
           'years_1_2': cons_how or 'no consensus with ≥ 3 analysts: the regime model from year 1',
           'margin': f"trailing EBIT margin {model['m0'] * 100:.1f}%; regime drift = panel median; κ = {prior_b['kappa']:.2f} (pooled regression, {prior_b['kappa_n']} pairs)",
           'margin_sd': 'company quarterly EBIT-margin σ' if _fin(sm) else 'panel residual σ',
           'sbc': f"stock-based compensation {sbc_share * 100:.1f}% of revenue (latest annual XBRL)" if sbc_share else 'no stock-based compensation tagged: not deducted',
           'wacc': 'the company WACC above (Treasury + Blume beta × ERP, bond-calibrated cost of debt)',
           'terminal': f"{base['g'] * 100:.1f}% growth, reinvestment = g ÷ ROIC ({base['roic'] * 100:.0f}%)"}
    if prior_b.get('thin'):
        src['thin'] = 'too few observations in this size bucket: ' + '; '.join(prior_b['thin'])
    return {'model': model, 'own_counts': own, 'history': [[round(g, 4), (round(m, 4) if _fin(m) else None)] for g, m in years_hist],
            'prior': {'P': prior_b['P'], 'counts': prior_b['counts'], 'firms': prior_b['firms'], 'transitions': prior_b['transitions']},
            'k': K_PRIOR, 'sources': src}


def run(F, base, W, years_hist, prior_b, price, cons_c=None, price_date=None):
    """The 'markov' block of a company's Fair value document, or None."""
    pr = params(F, base, W, years_hist, prior_b, cons_c, price_date)
    if not pr:
        return None
    vals = simulate(pr['model'])
    s = summarize(vals, price)
    if not s:
        return None
    pr.update(s)
    pr['seed'] = SEED
    pr['occupancy'] = occupancy(pr['model']['P'], pr['model']['start'])
    return pr
