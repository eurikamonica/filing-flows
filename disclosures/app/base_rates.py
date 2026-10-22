"""The outside view for the Fair value page (app/valuation.py calls it): base rates, the three consensus probabilities,
stage-based methods, sensitivity, river charts and the walk-forward scores of the models.

Base rates (the "outside view", Kahneman and Lovallo; Mauboussin's base-rate book). Every input of the next quarter and
of the 5-year DCF is read from what companies like this one actually did:
  next quarter   revenue growth, EPS growth (year-ago EPS above $0.01), operating- and net-margin change: the year-on-year
                 change of every peer quarter since 2020 (the frames panel: 26 calendar quarters; fourth quarters from the
                 annual frames)
  5 years        revenue CAGR over 3, 5 and 10 years and the 5-year change of the operating margin: every peer window in
                 the annual frames since CY2010
  cost of capital  the peers' WACC today (CAPM beta on two years of weekly prices, the debt module's cost of debt)
  terminal growth  the peers' 10-year revenue CAGR, held between 0% and 3.5%
  multiples      P/E and EV/Sales of every peer at every quarter since the price cache starts (2022-06), with figures
                 known 60 days after the quarter; EV/EBITDA today
Peer group: the same 3-digit SIC industry and size (revenue at the start of each window: under $1B, $1–10B, $10–50B,
over $50B), widened step by step — SIC3, SIC2 × size, SIC2, all × size, all — until it holds at least 40 observations
from at least 5 companies. A probability is the share of those observations at or above what the target requires.

Three consensus probabilities (each beside an inside-view probability, from the company's own history):
  market-implied   the 5-year revenue CAGR at which the DCF gives today's price (reverse DCF)
  Street           the analysts' next-quarter EPS and revenue against the year-ago quarter; the CAGR their mean price
                   target requires
  prediction market  the Polymarket EPS line against the year-ago quarter (beside the market's own probability); the CAGR
                   the Polymarket-implied price requires

Caveats, stated on the page: survivorship (a window needs both ends on file and the company a SIC in today's site list),
the company's own history is in its own peer group, frames are calendar-aligned (fiscal quarters mapped to the nearest
calendar quarter), draws for growth and margin are joint (one peer window) but the WACC and terminal growth are drawn
independently.
"""
import bisect
import datetime as dt
import math
import random
import zlib
from array import array

MIN_OBS, MIN_COS = 40, 5
ANNUAL_FROM = 2010
HISTORY_CONCEPTS = ('OperatingIncomeLoss', 'NetIncomeLoss')        # + the revenue concepts: annual frames back to ANNUAL_FROM
SIZES = [(1e9, 'S'), (1e10, 'M'), (5e10, 'L')]
SIZE_LABEL = {'S': 'revenue under $1B', 'M': 'revenue $1–10B', 'L': 'revenue $10–50B', 'XL': 'revenue over $50B'}
# industries whose earnings follow the economic or commodity cycle (documented rule; the margin-volatility rule adds others)
CYCLICAL_SIC = ('10', '12', '13', '14', '29', '33', '44', '152', '153', '281', '282', '286', '287', '371', '3674', '4512')
OUTSIDE_N = 1000
HORIZONS = {'3m': 91, '12m': 365}


def fin(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _r(v, d=4):
    return round(v, d) if fin(v) else None


# ------------------------------------------------------------------ peer groups and distributions
def size_of(rev):
    if not fin(rev) or rev <= 0:
        return None
    for edge, k in SIZES:
        if rev < edge:
            return k
    return 'XL'


_KEYS = {}


def group_keys(sic, size):
    """Narrowest first: SIC3 × size, SIC3, SIC2 × size, SIC2, all × size, all."""
    ck = (sic, size)
    if ck in _KEYS:
        return _KEYS[ck]
    s = str(sic or '').strip()
    keys = []
    for g in (s[:3], s[:2]):
        if len(g) in (2, 3) and g.isdigit() and len(s) >= len(g):
            if size:
                keys.append(f'{g}|{size}')
            keys.append(g)
    if size:
        keys.append(f'*|{size}')
    keys.append('*')
    _KEYS[ck] = tuple(keys)
    return _KEYS[ck]


def key_label(key, names=None):
    g, _, size = key.partition('|')
    base = 'all industries' if g == '*' else f'SIC {g}' + (f' ({names[g]})' if names and names.get(g) else '')
    return base + (f', {SIZE_LABEL[size]}' if size else '')


def industry_names(companies):
    """SIC 3- and 2-digit prefix → the most common industry name of the site's companies in it."""
    votes = {}
    for c in companies:
        s, n = str(c.get('sic') or ''), c.get('industry')
        if not n or len(s) < 3:
            continue
        for g in (s[:3], s[:2]):
            votes.setdefault(g, {}).setdefault(n, 0)
            votes[g][n] += 1
    return {g: max(v.items(), key=lambda kv: kv[1])[0] for g, v in votes.items()}


def share_at_least(xs, x):
    return (len(xs) - bisect.bisect_left(xs, x)) / len(xs) if len(xs) and fin(x) else None


def quantile(xs, q):
    if not len(xs):
        return None
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def summary(xs):
    return {'n': len(xs), **{f'p{int(q * 100)}': _r(quantile(xs, q)) for q in (0.1, 0.25, 0.5, 0.75, 0.9)}}


class Dists:
    """Empirical distributions by metric and peer group. An observation is added once and lands in every group key of
    its company, so a query widens without recomputing. finish() sorts; `cut` keeps, for the metrics named, the
    observations that ended before each cutoff year (the backtest must not see the future)."""

    def __init__(self):
        self._obs, self._pairs = {}, {}
        self.vals, self.ncos, self.cut, self.pairs = {}, {}, {}, {}

    def add(self, metric, value, sic, size, year=None, cik=None):
        if fin(value):
            self._obs.setdefault(metric, []).append((value, year, cik, group_keys(sic, size)))

    def add_pair(self, metric, a, b, sic, size, cik=None):
        if fin(a) and fin(b):
            self._pairs.setdefault(metric, []).append(((a, b), cik, group_keys(sic, size)))

    def finish(self, cutoffs=(), cut_metrics=()):
        for m, obs in self._obs.items():
            by, cos = {}, {}
            for v, y, c, keys in obs:
                for k in keys:
                    by.setdefault(k, []).append(v)
                    cos.setdefault(k, set()).add(c)
            self.vals[m] = {k: array('d', sorted(xs)) for k, xs in by.items()}
            self.ncos[m] = {k: len(s) for k, s in cos.items()}
            if m in cut_metrics:
                for cy in sorted(set(cutoffs)):
                    by2 = {}
                    for v, y, c, keys in obs:
                        if y is not None and y < cy:
                            for k in keys:
                                by2.setdefault(k, []).append(v)
                    self.cut.setdefault(m, {})[cy] = {k: array('d', sorted(xs)) for k, xs in by2.items()}
        for m, obs in self._pairs.items():
            by, cos = {}, {}
            for ab, c, keys in obs:
                for k in keys:
                    by.setdefault(k, []).append(ab)
                    cos.setdefault(k, set()).add(c)
            self.pairs[m] = by
            self.ncos[m] = {k: len(s) for k, s in cos.items()}
        self._obs, self._pairs = {}, {}
        return self

    def pick(self, metric, sic, size, cutoff=None, min_obs=MIN_OBS):
        """(group key, sorted values) of the narrowest group with enough observations, or None."""
        table = (self.cut.get(metric) or {}).get(cutoff) if cutoff is not None else self.vals.get(metric)
        if not table:
            return None
        nc = self.ncos.get(metric) or {}
        for k in group_keys(sic, size):
            xs = table.get(k)
            if xs is not None and len(xs) >= min_obs and nc.get(k, 0) >= MIN_COS:
                return k, xs
        return None

    def pick_pairs(self, metric, sic, size, min_obs=MIN_OBS):
        table = self.pairs.get(metric) or {}
        nc = self.ncos.get(metric) or {}
        for k in group_keys(sic, size):
            xs = table.get(k)
            if xs and len(xs) >= min_obs and nc.get(k, 0) >= MIN_COS:
                return k, xs
        return None

    def published(self, names=None):
        """{metric: {group: summary}} for the hub (groups with enough observations only)."""
        out = {}
        for m, table in self.vals.items():
            nc = self.ncos.get(m) or {}
            out[m] = {k: {**summary(xs), 'companies': nc.get(k, 0), 'label': key_label(k, names)}
                      for k, xs in table.items() if len(xs) >= MIN_OBS and nc.get(k, 0) >= MIN_COS}
        return out


def _ann(root, M, concept, year):
    return {cik: row for cik, row in M.frame(root, concept, f'CY{year}').items() if isinstance(row, list) and fin(row[0])}


def annual_history(root, M, last_year):
    """{cik: {'rev': {year: v}, 'oi': {…}, 'ni': {…}}} from the annual frames since ANNUAL_FROM (the first revenue concept a
    company reports wins, as in the quarterly panel)."""
    out = {}
    for y in range(ANNUAL_FROM, last_year + 1):
        for c in M.REVENUE:
            for cik, row in _ann(root, M, c, y).items():
                out.setdefault(cik, {}).setdefault('rev', {}).setdefault(y, row[0])
        for key, c in (('oi', 'OperatingIncomeLoss'), ('ni', 'NetIncomeLoss')):
            for cik, row in _ann(root, M, c, y).items():
                out.setdefault(cik, {}).setdefault(key, {})[y] = row[0]
    return out


def add_history(D, root, M, P, periods, sic_of):
    """The frames-based observations: quarterly year-on-year changes since 2020 and annual windows since CY2010."""
    years_q = [int(p[2:6]) for p in periods]
    n_q = 0
    for cik, rec in P.items():
        sic = sic_of.get(cik)
        if not sic:
            continue
        q = rec.get('q') or {}
        rev, oi, ni, eps = (q.get(k) or [None] * len(periods) for k in ('rev', 'oi', 'ni', 'eps'))
        for i in range(4, len(periods)):
            r0, r1 = rev[i - 4], rev[i]
            ok = fin(r0) and fin(r1) and r0 > 0 and r1 > 0
            size = size_of(4 * r0) if fin(r0) and r0 > 0 else None
            y = years_q[i]
            if ok:
                D.add('rev_yoy_q', clamp(r1 / r0 - 1, -0.95, 5.0), sic, size, y, cik)
                n_q += 1
                if fin(oi[i]) and fin(oi[i - 4]):
                    D.add('opm_chg_q', clamp(oi[i] / r1 - oi[i - 4] / r0, -1.0, 1.0), sic, size, y, cik)
                if fin(ni[i]) and fin(ni[i - 4]):
                    D.add('npm_chg_q', clamp(ni[i] / r1 - ni[i - 4] / r0, -1.0, 1.0), sic, size, y, cik)
            if fin(r1) and r1 > 0 and fin(oi[i]):
                D.add('opm_q', clamp(oi[i] / r1, -1.0, 1.0), sic, size_of(4 * r1), y, cik)
            e0, e1 = eps[i - 4], eps[i]
            if fin(e0) and fin(e1) and e0 > 0.01:
                D.add('eps_yoy_q', clamp(e1 / e0 - 1, -3.0, 5.0), sic, size, y, cik)
    last_year = int(periods[-1][2:6])
    A = annual_history(root, M, last_year)
    n_a = 0
    for cik, a in A.items():
        sic = sic_of.get(cik)
        if not sic:
            continue
        rev, oi = a.get('rev') or {}, a.get('oi') or {}
        for y, r0 in rev.items():
            if not (fin(r0) and r0 > 0):
                continue
            size = size_of(r0)
            for k in (3, 5, 10):
                r1 = rev.get(y + k)
                if fin(r1) and r1 > 0:
                    g = clamp((r1 / r0) ** (1 / k) - 1, -0.5, 1.0)
                    D.add(f'cagr{k}', g, sic, size, y + k, cik)
                    n_a += k == 5
                    if k == 5 and fin(oi.get(y)) and fin(oi.get(y + 5)):
                        dm = clamp(oi[y + 5] / r1 - oi[y] / r0, -1.0, 1.0)
                        D.add('opm_chg5', dm, sic, size, y + 5, cik)
                        D.add_pair('cagr5_dm5', g, dm, sic, size, cik)
    return {'quarterly_obs': n_q, 'five_year_windows': n_a, 'annual_companies': len(A)}


# ------------------------------------------------------------------ small numerics
def norm_cdf(z):
    return 0.5 * math.erfc(-z / math.sqrt(2))


def req_growth(M, base, target, lo=-0.5, hi=1.0, it=36):
    """The constant 5-year revenue growth at which the DCF gives `target` per share: (value, status)."""
    if not (base and fin(target) and target > 0):
        return None, 'none'
    f = lambda g: M.value({**base, 'growth': g}) - target
    flo, fhi = f(lo), f(hi)
    if not (fin(flo) and fin(fhi)):
        return None, 'none'
    if flo > 0:
        return None, 'below'                      # even a shrinking company is worth more: no growth needed
    if fhi < 0:
        return None, 'above'                      # more than 100% a year would be needed
    a, b = lo, hi
    for _ in range(it):
        m = (a + b) / 2
        fm = f(m)
        if not fin(fm):
            return None, 'none'
        if fm < 0:
            a = m
        else:
            b = m
    return (a + b) / 2, 'ok'


def spearman(xs, ys):
    n = len(xs)
    if n < 10:
        return None

    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    a, b = ranks(xs), ranks(ys)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den else None


def ridge(X, y, lam):
    """Least squares with an L2 penalty on every coefficient but the first (the intercept)."""
    k = len(X[0])
    A = [[0.0] * k for _ in range(k)]
    b = [0.0] * k
    for x, t in zip(X, y):
        for i in range(k):
            b[i] += x[i] * t
            xi = x[i]
            row = A[i]
            for j in range(k):
                row[j] += xi * x[j]
    for i in range(1, k):
        A[i][i] += lam
    for c in range(k):                                   # Gaussian elimination with partial pivoting
        p = max(range(c, k), key=lambda r: abs(A[r][c]))
        if abs(A[p][c]) < 1e-12:
            return None
        A[c], A[p], b[c], b[p] = A[p], A[c], b[p], b[c]
        for r in range(c + 1, k):
            f = A[r][c] / A[c][c]
            for j in range(c, k):
                A[r][j] -= f * A[c][j]
            b[r] -= f * b[c]
    w = [0.0] * k
    for c in range(k - 1, -1, -1):
        w[c] = (b[c] - sum(A[c][j] * w[j] for j in range(c + 1, k))) / A[c][c]
    return w


def nice_levels(lo, hi, n=5):
    """n round multiples spanning lo..hi (the river's bands)."""
    if not (fin(lo) and fin(hi)) or hi <= 0:
        return []
    lo = max(lo, 0.0)
    span = max(hi - lo, hi * 0.2)
    raw = span / (n - 1)
    mag = 10 ** math.floor(math.log10(raw))
    step = min((s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw), default=10 * mag)
    start = math.floor(lo / step) * step
    out = [round(start + k * step, 6) for k in range(n)]
    return [x for x in out if x > 0] or [step]


# ------------------------------------------------------------------ stage
STAGES = {
    'pre_profit': {'label': 'Pre-profit / high growth', 'rule': 'operating income ≤ 0 over four quarters and revenue growth ≥ 10%',
                   'methods': [('Path-to-margin DCF', 0.5), ('EV/Sales vs peers', 0.5)],
                   'metrics': 'Rule of 40 (growth + free-cash-flow margin), cash runway, the margin path a DCF needs'},
    'high_growth': {'label': 'High growth', 'rule': 'operating income > 0 and revenue growth ≥ 20%',
                    'methods': [('DCF — Monte Carlo 10th–90th percentile', 0.3), ('Outside view — base-rate Monte Carlo', 0.3),
                                ('EV/Sales vs peers', 0.2), ('P/E vs peers', 0.2)],
                    'metrics': 'Rule of 40, the growth the price requires against peers'},
    'growth': {'label': 'Growth', 'rule': 'operating income > 0 and revenue growth 8–20%',
               'methods': [('DCF — Monte Carlo 10th–90th percentile', 0.35), ('Outside view — base-rate Monte Carlo', 0.25),
                           ('P/E vs peers', 0.25), ('EV/EBITDA vs peers', 0.15)],
               'metrics': 'DCF, base rates of growth and margins'},
    'mature': {'label': 'Mature', 'rule': 'operating income > 0 and revenue growth 0–8% (or below 0 without a 3-year decline)',
               'methods': [('DCF — Monte Carlo 10th–90th percentile', 0.25), ('Owner earnings capitalized', 0.2),
                           ('Shareholder yield (dividends + buybacks)', 0.15), ('P/E vs peers', 0.25), ('EV/EBITDA vs peers', 0.15)],
               'metrics': 'owner earnings (net income + D&A − capex), dividend and buyback yield'},
    'cyclical': {'label': 'Cyclical', 'rule': 'a cyclical industry (mining, energy, chemicals, metals, autos, semiconductors, airlines, '
                                              'homebuilders, shipping) or a quarterly operating margin with σ above 8 points',
                 'methods': [('Normalized (mid-cycle) P/E', 0.35), ('Normalized (mid-cycle) DCF', 0.35), ('EV/EBITDA vs peers', 0.3)],
                 'metrics': 'mid-cycle margin: the median operating margin of every quarter on file since 2020'},
    'decline': {'label': 'Decline / turnaround', 'rule': 'operating income ≤ 0 with growth under 10%, or revenue falling over 1 and 3 years',
                'methods': [('Tangible book (asset value)', 0.4), ('EV/Sales vs peers', 0.3), ('DCF — Monte Carlo 10th–90th percentile', 0.15),
                            ('Owner earnings capitalized', 0.15)],
                'metrics': 'tangible book per share (an asset-value floor; XBRL frames carry no asset-level haircuts), free cash flow to debt'},
    'financial': {'label': 'Financial (bank / insurer)', 'rule': 'SIC of a bank or insurer',
                  'methods': [('Residual income', 0.5), ('P/TBV vs ROTCE (bank peers)', 0.5), ('P/B vs ROE (insurer peers)', 0.5)],
                  'metrics': 'residual income on book value; P/TBV vs ROTCE or P/B vs ROE across peers'},
    'reit': {'label': 'REIT', 'rule': 'SIC 6798', 'methods': [('P/FFO vs REIT peers', 0.7), ('Residual income', 0.3)],
             'metrics': 'funds from operations against REIT peers'},
}


def cagr3_of(revs):
    if len(revs) >= 16 and all(fin(v) for v in revs[-16:-12] + revs[-4:]):
        a, b = sum(revs[-16:-12]), sum(revs[-4:])
        if a > 0 and b > 0:
            return (b / a) ** (1 / 3) - 1
    return None


def stage_of(F, revs, margins):
    """(stage, why) from the company's own figures with the documented rules (STAGES)."""
    if F['kind'] in ('bank', 'insurer'):
        return 'financial', f"{F['kind']} (SIC {F.get('sic')})"
    if F['kind'] == 'reit':
        return 'reit', 'SIC 6798'
    g0, oi, c3 = F.get('g0'), F.get('oi'), cagr3_of(revs)
    sd = stdev(margins[-26:]) if len(margins) >= 8 else None
    gtxt = f'revenue growth {g0 * 100:+.1f}%' if fin(g0) else 'revenue growth unknown'
    if not fin(oi) or oi <= 0:
        if fin(g0) and g0 >= 0.10:
            return 'pre_profit', f'operating income ≤ 0, {gtxt}'
        return 'decline', f'operating income ≤ 0, {gtxt}'
    if fin(g0) and g0 >= 0.20:
        return 'high_growth', gtxt
    s = str(F.get('sic') or '')
    if s.startswith(CYCLICAL_SIC):
        return 'cyclical', f'cyclical industry (SIC {s}), {gtxt}'
    if fin(sd) and sd > 0.08:
        return 'cyclical', f'quarterly operating margin σ {sd * 100:.1f} points, {gtxt}'
    if fin(g0) and g0 >= 0.08:
        return 'growth', gtxt
    if fin(g0) and g0 < 0 and fin(c3) and c3 < 0:
        return 'decline', f'{gtxt}, 3-year CAGR {c3 * 100:+.1f}%'
    return 'mature', gtxt


def stdev(xs):
    xs = [x for x in xs if fin(x)]
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def median_without(xs, x):
    """The median of a sorted list with one occurrence of x removed (x must be in it)."""
    i = bisect.bisect_left(xs, x)
    n = len(xs) - 1
    at = lambda j: xs[j] if j < i else xs[j + 1]
    return at(n // 2) if n % 2 else (at(n // 2 - 1) + at(n // 2)) / 2


def median(xs):
    xs = sorted(x for x in xs if fin(x))
    return quantile(xs, 0.5) if xs else None


# ------------------------------------------------------------------ per company
def _draw(rng, xs):
    return xs[rng.randrange(len(xs))]


def outside_mc(M, base, price, D, sic, size, n=OUTSIDE_N, seed=0):
    """DCF values with every input drawn from the peers: (5-year CAGR, 5-year margin change) as one peer window, WACC
    from the peers today, terminal growth from the peers' 10-year CAGR (0–3.5%)."""
    gp = D.pick_pairs('cagr5_dm5', sic, size)
    g1 = D.pick('cagr5', sic, size) if not gp else None
    if not (gp or g1):
        return None
    w = D.pick('wacc', sic, size, min_obs=12)
    t = D.pick('cagr10', sic, size)
    rng = random.Random(seed)
    m0 = M._at(base['margin'], 0)
    vals = []
    for _ in range(n):
        if gp:
            g, dm = _draw(rng, gp[1])
        else:
            g, dm = _draw(rng, g1[1]), 0.0
        m5 = clamp(m0 + dm, -0.5, 0.7)
        path = [m0 + (m5 - m0) * (k + 1) / M.YEARS for k in range(M.YEARS)]
        tg = clamp(_draw(rng, t[1]), 0.0, 0.035) if t else rng.uniform(0.015, 0.03)
        ww = _draw(rng, w[1]) if w else base['wacc']
        ww = max(ww, tg + 0.01, 0.04)
        v = M.value({**base, 'growth': g, 'margin': path, 'wacc': ww, 'g': tg, 'roic': max(base.get('roic', 0.15), tg + 0.01)})
        if fin(v):
            vals.append(v)
    if len(vals) < n * 0.5:
        return None
    vals.sort()
    lo, hi = quantile(vals, 0.05), quantile(vals, 0.95)
    bins, hist = 30, [0] * 30
    if hi > lo:
        for v in vals:
            if lo <= v <= hi:
                hist[min(bins - 1, int((v - lo) / (hi - lo) * bins))] += 1
    out = {'n': len(vals), 'mean': sum(vals) / len(vals), **{f'p{int(q * 100)}': quantile(vals, q) for q in (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)},
           'p_above': share_at_least(vals, price) if fin(price) and price > 0 else None, 'hist': {'lo': lo, 'hi': hi, 'counts': hist},
           'groups': {'growth_margin': (gp or g1)[0], 'wacc': w[0] if w else None, 'terminal': t[0] if t else None},
           'n_windows': len((gp or g1)[1])}
    out['_vals'] = vals
    return out


def _peer(D, metric, sic, size, names, cutoff=None, min_obs=MIN_OBS):
    p = D.pick(metric, sic, size, cutoff=cutoff, min_obs=min_obs)
    if not p:
        return None
    k, xs = p
    return {'group': k, 'label': key_label(k, names), **summary(xs), 'companies': (D.ncos.get(metric) or {}).get(k), '_xs': xs}


def _prob(peer, x):
    return share_at_least(peer['_xs'], x) if peer and fin(x) else None


def _own_share(xs, x):
    xs = [v for v in xs if fin(v)]
    return (sum(1 for v in xs if v >= x) / len(xs), len(xs)) if xs and fin(x) else (None, len(xs))


def _year_ago(series, periods, end):
    """The value of the calendar quarter a year before the quarter ending `end`, from a panel series."""
    if not end or not series:
        return None
    qp = _quarter_of(end)
    ya = _shift(qp, -4)
    return series[periods.index(ya)] if ya in periods else None


def _quarter_of(end):
    d = dt.date.fromisoformat(str(end)[:10])
    best = None
    for y in (d.year - 1, d.year, d.year + 1):
        for q in range(1, 5):
            qe = (dt.date(y, 3 * q, 1) + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
            gap = abs((qe - d).days)
            if best is None or gap < best[0]:
                best = (gap, f'CY{y}Q{q}')
    return best[1]


def _shift(period, k):
    y, q = int(period[2:6]), int(period[7]) - 1 + k
    return f'CY{y + q // 4}Q{q % 4 + 1}'


def consensus_odds(M, F, base, rec, periods, cons, crow, D, names, own):
    """The probabilities of the three consensus views, outside (peers) and inside (own history)."""
    sic, size = F.get('sic'), size_of(F.get('revenue'))
    q = (rec or {}).get('q') or {}
    out = {}
    p5 = _peer(D, 'cagr5', sic, size, names)

    def growth_odds(target, label, extra=None):
        g, st = req_growth(M, base, target) if base else (None, 'none')
        d = {'label': label, 'price': target, 'required': g, 'status': st, 'what': '5-year revenue CAGR', **(extra or {})}
        if g is not None:
            d['p_outside'] = _prob(p5, g)
            d['p_inside'] = 1 - norm_cdf((g - own['g']) / own['sg']) if own else None
        elif st == 'below':
            d['p_outside'], d['p_inside'] = 1.0, 1.0
        elif st == 'above':
            d['p_outside'], d['p_inside'] = 0.0, 0.0
        if p5:
            d.update({'group': p5['group'], 'group_label': p5['label'], 'n': p5['n']})
        return d
    price = F.get('price')
    if base and fin(price):
        out['market'] = growth_odds(price, 'Market-implied (reverse DCF)')
    a = (cons or {}).get('analysts') or {}
    q0 = next((p for p in a.get('periods') or [] if p.get('period') == '0q'), {}) or {}
    e, rv = q0.get('eps') or {}, q0.get('rev') or {}
    eps_avg = e.get('avg') if fin(e.get('avg')) else (crow or {}).get('eps_q')
    rev_avg = rv.get('avg') if fin(rv.get('avg')) else (crow or {}).get('rev_q')
    end = q0.get('end')
    eps_ya = e.get('yearAgoEps') if fin(e.get('yearAgoEps')) else _year_ago(q.get('eps'), periods, end)
    rev_ya = rv.get('yearAgoRevenue') if fin(rv.get('yearAgoRevenue')) else _year_ago(q.get('rev'), periods, end)
    own_eps = [q['eps'][i] / q['eps'][i - 4] - 1 for i in range(4, len(q.get('eps') or []))
               if fin(q['eps'][i]) and fin(q['eps'][i - 4]) and q['eps'][i - 4] > 0.01]
    own_rev = [q['rev'][i] / q['rev'][i - 4] - 1 for i in range(4, len(q.get('rev') or []))
               if fin(q['rev'][i]) and fin(q['rev'][i - 4]) and q['rev'][i - 4] > 0]
    pe_ = _peer(D, 'eps_yoy_q', sic, size, names)
    pr_ = _peer(D, 'rev_yoy_q', sic, size, names)
    if fin(eps_avg) and fin(eps_ya):
        d = {'label': "Street: next-quarter EPS", 'estimate': eps_avg, 'year_ago': eps_ya, 'quarter_end': end, 'n_analysts': e.get('numberOfAnalysts'),
             'what': 'EPS growth vs the year-ago quarter'}
        if eps_ya > 0.01:
            g = eps_avg / eps_ya - 1
            d['required'] = g
            d['p_outside'] = _prob(pe_, g)
            d['p_inside'], d['n_inside'] = _own_share(own_eps[-20:], g)
            if pe_:
                d.update({'group': pe_['group'], 'group_label': pe_['label'], 'n': pe_['n']})
        else:
            d['note'] = 'the year-ago EPS was not positive: a growth rate would mean nothing'
        out['street_eps'] = d
    if fin(rev_avg) and fin(rev_ya) and rev_ya > 0:
        g = rev_avg / rev_ya - 1
        d = {'label': 'Street: next-quarter revenue', 'estimate': rev_avg, 'year_ago': rev_ya, 'quarter_end': end, 'required': g,
             'what': 'revenue growth vs the year-ago quarter', 'p_outside': _prob(pr_, g)}
        d['p_inside'], d['n_inside'] = _own_share(own_rev[-20:], g)
        if pr_:
            d.update({'group': pr_['group'], 'group_label': pr_['label'], 'n': pr_['n']})
        out['street_rev'] = d
        sh_ya = _year_ago(q.get('sh'), periods, end) or F.get('shares')
        ni_ya = _year_ago(q.get('ni'), periods, end)
        nm_new = eps_avg * sh_ya / rev_avg if fin(eps_avg) and fin(sh_ya) and rev_avg > 0 else None
        nm_old = ni_ya / rev_ya if fin(ni_ya) else None
        if fin(nm_new) and fin(nm_old) and abs(nm_new) <= 1 and abs(nm_old) <= 1:     # else the units do not match (ADRs, share classes)
            need = nm_new - nm_old
            pm_ = _peer(D, 'npm_chg_q', sic, size, names)
            own_m = [q['ni'][i] / q['rev'][i] - q['ni'][i - 4] / q['rev'][i - 4] for i in range(4, len(q.get('rev') or []))
                     if all(fin(v) for v in (q['ni'][i], q['ni'][i - 4], q['rev'][i], q['rev'][i - 4])) and q['rev'][i] > 0 and q['rev'][i - 4] > 0]
            d = {'label': 'Street: next-quarter net margin', 'required': need, 'what': 'net-margin change vs the year-ago quarter (points)',
                 'estimate': eps_avg * sh_ya / rev_avg, 'year_ago': ni_ya / rev_ya, 'p_outside': _prob(pm_, need)}
            d['p_inside'], d['n_inside'] = _own_share(own_m[-20:], need)
            if pm_:
                d.update({'group': pm_['group'], 'group_label': pm_['label'], 'n': pm_['n']})
            out['street_margin'] = d
    T = a.get('targets') or {}
    tm = T.get('mean') if fin(T.get('mean')) else (crow or {}).get('target_mean')
    if base and fin(tm):
        out['street_target'] = growth_odds(tm, "Street: analysts' mean price target", {'n_analysts': T.get('n')})
    strike = (crow or {}).get('pm_eps_strike')
    if fin(strike) and fin(eps_ya):
        d = {'label': 'Polymarket: EPS line', 'strike': strike, 'year_ago': eps_ya, 'p_market': (crow or {}).get('pm_beat_prob'),
             'report_date': (crow or {}).get('pm_report_date'), 'what': 'EPS growth vs the year-ago quarter'}
        if eps_ya > 0.01:
            g = strike / eps_ya - 1
            d['required'] = g
            d['p_outside'] = _prob(pe_, g)
            d['p_inside'], d['n_inside'] = _own_share(own_eps[-20:], g)
            if pe_:
                d.update({'group': pe_['group'], 'group_label': pe_['label'], 'n': pe_['n']})
        out['pm_eps'] = d
    pmp = (crow or {}).get('pm_implied_price')
    if base and fin(pmp):
        out['pm_price'] = growth_odds(pmp, 'Polymarket implied price', {'date': (crow or {}).get('pm_price_date')})
    return out


def stage_block(M, F, base, W, out, rec, D, names):
    """The stage, its own metrics, the stage methods (football items) and the stage-weighted value."""
    q = (rec or {}).get('q') or {}
    revs = [v for v in (q.get('rev') or []) if fin(v)]
    mq = [o / r for o, r in zip(q.get('oi') or [], q.get('rev') or []) if fin(o) and fin(r) and r > 0]
    nm = [n / r for n, r in zip(q.get('ni') or [], q.get('rev') or []) if fin(n) and fin(r) and r > 0]
    stage, why = stage_of(F, q.get('rev') or [], mq)
    S = STAGES[stage]
    sh, rev = F.get('shares'), F.get('revenue')
    sic, size = F.get('sic'), size_of(rev)
    m = {}
    fcf = None
    fin_kind = F['kind'] in ('bank', 'insurer')               # cash-flow measures mean little for a balance-sheet business
    if not fin_kind and fin(F.get('oi')) and fin(rev) and rev > 0:
        fcf = F['oi'] * (1 - F.get('tax_rate', 0.21) if F['oi'] > 0 else 1) + (F.get('da') or 0) - (F.get('capex') or 0)
        m['fcf'] = fcf
        m['fcf_margin'] = fcf / rev
        if fin(F.get('g0')):
            m['rule_of_40'] = (F['g0'] + fcf / rev) * 100
        if fcf < 0 and fin(F.get('cash')):
            m['cash_runway_years'] = F['cash'] / -fcf
        if fin(F.get('debt')) and F['debt'] > 0:
            m['fcf_to_debt'] = fcf / F['debt']
    m['cagr3'] = cagr3_of(q.get('rev') or [])
    m['margin_sigma'] = stdev(mq[-26:]) if len(mq) >= 8 and not fin_kind else None
    items = []
    ke = (W or {}).get('ke')
    g_t = M.TERM_G
    # owner earnings (Buffett): net income + D&A − capex, capitalized at the cost of equity less terminal growth
    if not fin_kind and fin(F.get('ni')) and fin(sh) and sh > 0 and fin(ke) and ke > g_t + 0.01:
        oe = F['ni'] + (F.get('da') or 0) - (F.get('capex') or 0)
        m['owner_earnings'] = oe
        if oe > 0:
            v = lambda k: oe * (1 + g_t) / (k - g_t) / sh
            items.append({'method': 'Owner earnings capitalized', 'low': v(ke + 0.01), 'high': v(max(ke - 0.01, g_t + 0.005)), 'point': v(ke),
                          'note': f'owner earnings {oe / sh:.2f}/share (net income + D&A − capex) ÷ (cost of equity {ke * 100:.1f}% − {g_t * 100:.1f}%)'})
    ann = (rec or {}).get('ann') or {}
    div = (ann.get('div') or (None,))[0]
    bb = (ann.get('buyback') or (None,))[0]
    payout = (div or 0) + (bb or 0)
    if payout > 0 and fin(F.get('mcap')) and F['mcap'] > 0:
        m['dividend_yield'] = (div or 0) / F['mcap']
        m['shareholder_yield'] = payout / F['mcap']
        if fin(ke) and ke > g_t + 0.01 and fin(sh) and sh > 0:
            v = lambda k: payout * (1 + g_t) / (k - g_t) / sh
            items.append({'method': 'Shareholder yield (dividends + buybacks)', 'low': v(ke + 0.01), 'high': v(max(ke - 0.01, g_t + 0.005)),
                          'point': v(ke), 'note': f'dividends + buybacks {payout / sh:.2f}/share a year, yield {payout / F["mcap"] * 100:.1f}%'})
    tbv = (F.get('equity') or 0) - (F.get('goodwill') or 0) - (F.get('intangibles') or 0)
    if fin(sh) and sh > 0 and fin(F.get('equity')):
        m['tangible_book_ps'] = tbv / sh
        if stage == 'decline':
            items.append({'method': 'Tangible book (asset value)', 'low': max(tbv, 0) / sh * 0.8, 'high': max(tbv, 0) / sh, 'point': max(tbv, 0) / sh,
                          'note': 'equity − goodwill − intangibles; the low end takes 20% off for a forced sale'})
    if stage == 'cyclical' and len(mq) >= 8 and fin(rev) and rev > 0 and fin(sh) and sh > 0:
        mid = median(mq)
        m['mid_cycle_margin'] = mid
        m['mid_cycle_net_margin'] = median(nm)
        pe = _peer(D, 'pe_hist', sic, size, names) or _peer(D, 'pe', sic, size, names, min_obs=12)
        n_eps = (median(nm) or 0) * rev / sh
        m['normalized_eps'] = n_eps
        if pe and n_eps > 0:
            items.append({'method': 'Normalized (mid-cycle) P/E', 'low': n_eps * pe['p25'], 'high': n_eps * pe['p75'], 'point': n_eps * pe['p50'],
                          'note': f'mid-cycle EPS {n_eps:.2f} (median net margin {median(nm) * 100:.1f}% since 2020 × revenue) × peer P/E {pe["p50"]:.1f}x'})
        if base and mid > 0:
            vs = [M.value({**base, 'margin': x}) for x in (quantile(sorted(mq), 0.25), mid, quantile(sorted(mq), 0.75))]
            if all(fin(v) for v in vs):
                items.append({'method': 'Normalized (mid-cycle) DCF', 'low': min(vs), 'high': max(vs), 'point': vs[1],
                              'note': f'the DCF at the median operating margin since 2020 ({mid * 100:.1f}%); range: its 25th–75th percentile'})
    if stage == 'pre_profit' and fin(rev) and rev > 0 and fin(sh) and sh > 0 and W:
        tgt = _peer(D, 'opm_q', sic, size, names)
        tm = clamp(tgt['p50'], 0.08, 0.35) if tgt and fin(tgt['p50']) and tgt['p50'] > 0 else 0.15
        m0 = (F['oi'] / rev) if fin(F.get('oi')) else -0.1
        g0 = clamp(F['g0'], 0.0, 0.6) if fin(F.get('g0')) else 0.15
        pb = {'rev0': rev, 'years': M.YEARS, 'growth': M.fade(g0, M.TERM_G), 'margin': [m0 + (tm - m0) * (k + 1) / M.YEARS for k in range(M.YEARS)],
              'tax': F.get('tax_rate', 0.21), 'da': (F.get('da') or 0) / rev, 'capex': (F.get('capex') or 0) / rev, 'wc': M.WC_SHARE,
              'wacc': W['wacc'], 'g': M.TERM_G, 'terminal': 'roic', 'roic': 0.15, 'debt': F['debt'], 'cash': F['cash'],
              'claims': F.get('claims') or 0, 'nonop': 0.0, 'shares': sh}
        vs = [M.value({**pb, 'margin': [m0 + (t - m0) * (k + 1) / M.YEARS for k in range(M.YEARS)]}) for t in (tm - 0.05, tm, tm + 0.05)]
        m['target_margin'] = tm
        if all(fin(v) for v in vs):
            items.append({'method': 'Path-to-margin DCF', 'low': min(vs), 'high': max(vs), 'point': vs[1],
                          'note': f'operating margin from {m0 * 100:.1f}% to the peer median {tm * 100:.1f}% by year {M.YEARS} (±5 points)'})
            out['_path_base'] = pb
    out['football'] += items
    pts = {b['method']: b for b in out['football'] if fin(b.get('point'))}
    used, tot = [], 0.0
    for name, w in S['methods']:
        b = pts.get(name)
        if b:
            used.append({'method': name, 'weight': w, 'point': b['point'], 'low': b.get('low'), 'high': b.get('high')})
            tot += w
    blk = {'stage': stage, 'label': S['label'], 'why': why, 'rule': S['rule'], 'what_matters': S['metrics'], 'metrics': m,
           'methods': [{'method': n, 'weight': w} for n, w in S['methods']], 'rules': {k: v['rule'] for k, v in STAGES.items()}}
    if used and tot > 0:
        for u in used:
            u['weight'] = u['weight'] / tot
        val = sum(u['weight'] * u['point'] for u in used)
        lo = sum(u['weight'] * (u['low'] if fin(u['low']) else u['point']) for u in used)
        hi = sum(u['weight'] * (u['high'] if fin(u['high']) else u['point']) for u in used)
        blk.update({'used': used, 'value': val})
        out['football'].append({'method': f'Stage-weighted value ({S["label"].lower()})', 'low': min(lo, hi), 'high': max(lo, hi), 'point': val,
                                'note': ' + '.join(f'{u["weight"] * 100:.0f}% {u["method"]}' for u in used)})
    return blk


def sensitivity(M, F, base, W, out, D, names):
    """Tornado and two grids for the main method: the DCF (or the path-to-margin DCF) for operating companies, residual
    income for financials, FFO × multiple for REITs."""
    sh, price = F.get('shares'), F.get('price')
    b = base or out.get('_path_base')
    if b:
        v0 = M.value(b)
        if not fin(v0):
            return None
        shift = lambda path, d: [x + d for x in path] if isinstance(path, list) else path + d
        tests = [('Revenue growth (each year)', 'growth', -0.05, 0.05, lambda x, d: shift(x, d), '±5 pts'),
                 ('Operating margin', 'margin', -0.03, 0.03, lambda x, d: shift(x, d), '±3 pts'),
                 ('WACC', 'wacc', 0.01, -0.01, lambda x, d: x + d, '±1 pt'),
                 ('Terminal growth', 'g', -0.005, 0.005, lambda x, d: x + d, '±0.5 pt'),
                 ('Capex (share of revenue)', 'capex', 0.01, -0.01, lambda x, d: shift(x, d), '±1 pt'),
                 ('Tax rate', 'tax', 0.05, -0.05, lambda x, d: clamp(x + d, 0, 0.5), '±5 pts'),
                 ('Working capital per $ of growth', 'wc', 0.10, -0.10, lambda x, d: max(0.0, x + d), '±10 pts')]
        bars = []
        for label, key, dlo, dhi, fn, how in tests:
            lo = M.value({**b, key: fn(b[key], dlo)})
            hi = M.value({**b, key: fn(b[key], dhi)})
            if fin(lo) and fin(hi):
                bars.append({'input': label, 'how': how, 'low': min(lo, hi), 'high': max(lo, hi), 'swing': (max(lo, hi) - min(lo, hi)) / abs(v0)})
        bars.sort(key=lambda x: -x['swing'])
        gs, ws = [-0.10, -0.05, 0.0, 0.05, 0.10], [-0.02, -0.01, 0.0, 0.01, 0.02]
        grid1 = [[_r(M.value({**b, 'growth': shift(b['growth'], dg), 'wacc': max(b['wacc'] + dw, b['g'] + 0.005)}), 2) for dw in ws] for dg in gs]
        g_first = M._at(b['growth'], 0)
        main = 'DCF' if base else 'Path-to-margin DCF'
        res = {'method': main, 'base_value': v0, 'price': price, 'tornado': bars,
               'grid_growth_wacc': {'rows': [_r(g_first + d) for d in gs], 'cols': [_r(b['wacc'] + d) for d in ws], 'row_label': 'year-1 revenue growth (path shifted)',
                                    'col_label': 'WACC', 'values': grid1}}
        pe = _peer(D, 'pe_hist', F.get('sic'), size_of(F.get('revenue')), names) or _peer(D, 'pe', F.get('sic'), size_of(F.get('revenue')), names, min_obs=12)
        if pe and fin(sh) and sh > 0:
            m0 = M._at(b['margin'], 0)
            rev1 = b['rev0'] * (1 + g_first)
            ms = [m0 + d for d in (-0.06, -0.03, 0.0, 0.03, 0.06)]
            mults = [pe[k] for k in ('p10', 'p25', 'p50', 'p75', 'p90')]
            res['grid_margin_multiple'] = {'rows': [_r(x) for x in ms], 'cols': [_r(x, 2) for x in mults], 'row_label': 'operating margin (next year)',
                                           'col_label': f'P/E ({pe["label"]}, 10th–90th percentile)',
                                           'values': [[_r(rev1 * mm * (1 - b['tax']) * k / sh, 2) if mm > 0 else None for k in mults] for mm in ms]}
        if bars:
            res['driver'] = bars[0]['input']
            res['driver_swing'] = bars[0]['swing']
        return res
    ri = out.get('residual_income')
    if ri and fin(sh) and sh > 0:
        f = lambda roe, ke: (M.residual_income(ri['book'], roe, ke) or float('nan')) / sh
        v0 = f(ri['roe'], ri['ke'])
        bars = []
        for label, a, b2, how in (('Return on equity', (ri['roe'] - 0.03, ri['ke']), (ri['roe'] + 0.03, ri['ke']), '±3 pts'),
                                  ('Cost of equity', (ri['roe'], ri['ke'] + 0.01), (ri['roe'], ri['ke'] - 0.01), '±1 pt')):
            lo, hi = f(*a), f(*b2)
            if fin(lo) and fin(hi) and fin(v0) and v0:
                bars.append({'input': label, 'how': how, 'low': min(lo, hi), 'high': max(lo, hi), 'swing': (max(lo, hi) - min(lo, hi)) / abs(v0)})
        bars.sort(key=lambda x: -x['swing'])
        rs, ks = [ri['roe'] + d for d in (-0.04, -0.02, 0, 0.02, 0.04)], [ri['ke'] + d for d in (-0.02, -0.01, 0, 0.01, 0.02)]
        res = {'method': 'Residual income', 'base_value': v0, 'price': price, 'tornado': bars,
               'grid_growth_wacc': {'rows': [_r(x) for x in rs], 'cols': [_r(x) for x in ks], 'row_label': 'return on equity', 'col_label': 'cost of equity',
                                    'values': [[_r(f(r, k), 2) for k in ks] for r in rs]}}
        if bars:
            res['driver'], res['driver_swing'] = bars[0]['input'], bars[0]['swing']
        return res
    return None


def river(M, daily, periods, rec, F, max_weeks=240):
    """Weekly price with the trailing per-share figure of each multiple (known LAG_DAYS after the quarter): P/E (EPS),
    P/S (revenue), P/B (equity), EV/EBITDA (EBITDA and net debt). The page draws price = multiple × figure for round
    multiples spanning the observed 5th–95th percentile."""
    wk = M.weekly(daily)
    if len(wk) < 26:
        return None
    q = (rec or {}).get('q') or {}
    eq = (rec or {}).get('eq_q') or [None] * len(periods)
    n = len(periods)
    get = lambda k: (q.get(k) or [None] * n)
    eps, rev, oi, sh_q = get('eps'), get('rev'), get('oi'), get('sh')
    da_ratio = (F.get('da') or 0) / F['revenue'] if fin(F.get('revenue')) and F['revenue'] > 0 else 0.0
    nd = (F.get('debt') or 0) - (F.get('cash') or 0) + (F.get('claims') or 0)
    known = []
    for i in range(3, n):
        s4 = lambda xs: sum(xs[i - 3:i + 1]) if all(fin(v) for v in xs[i - 3:i + 1]) else None
        sh = sh_q[i] if fin(sh_q[i]) and sh_q[i] > 0 else F.get('shares')
        if not (fin(sh) and sh > 0):
            continue
        e4, r4, o4 = s4(eps), s4(rev), s4(oi)
        known.append(((M.quarter_end(periods[i]) + dt.timedelta(days=M.LAG_DAYS)).isoformat(),
                      e4, r4 / sh if fin(r4) else None, eq[i] / sh if fin(eq[i]) else None,
                      (o4 + da_ratio * r4) / sh if fin(o4) and fin(r4) else None, nd / sh))
    if not known:
        return None
    dates = [k[0] for k in known]
    weeks, price, idx = [], [], []
    for d, c in wk:
        j = bisect.bisect_right(dates, d) - 1
        if j < 0 or not any(fin(x) for x in known[j][1:5]):
            continue
        weeks.append(d)
        price.append(_r(c, 2))
        idx.append(j)
    weeks, price, idx = weeks[-max_weeks:], price[-max_weeks:], idx[-max_weeks:]
    if not weeks:
        return None
    used = sorted(set(idx))
    steps = {'from': [known[j][0] for j in used]}
    for col, k in ((1, 'pe'), (2, 'ps'), (3, 'pb'), (4, 'ev_ebitda'), (5, 'nd')):
        steps[k] = [_r(known[j][col], 4) for j in used]
    pos = {j: n for n, j in enumerate(used)}
    out = {'from': weeks[0], 'weeks': weeks, 'price': price, 'step': [pos[j] for j in idx], 'steps': steps, 'metrics': {},
           'note': f'Weekly closes since {weeks[0]} (the hub\'s price cache starts 2022-06); each figure is the trailing four quarters, '
                   f'counted {M.LAG_DAYS} days after the quarter ends (steps); EV/EBITDA uses today\'s net debt and D&A ratio'}
    for k, label in (('pe', 'P/E'), ('ps', 'P/S'), ('pb', 'P/B'), ('ev_ebitda', 'EV/EBITDA')):
        mult = []
        for p, j in zip(price, out['step']):
            x, ndp = steps[k][j], steps['nd'][j]
            if not (fin(p) and fin(x) and x > 0):
                continue
            v = (p + ndp) / x if k == 'ev_ebitda' and fin(ndp) else p / x
            if 0 < v < (300 if k == 'pe' else 150):
                mult.append(v)
        if len(mult) < 26:
            continue
        ms = sorted(mult)
        cur = mult[-1]
        out['metrics'][k] = {'label': label, 'levels': nice_levels(quantile(ms, 0.05), quantile(ms, 0.95)),
                             'current': _r(cur, 2), 'median': _r(quantile(ms, 0.5), 2), 'pct': _r(sum(1 for v in ms if v < cur) / len(ms), 3), 'weeks': len(ms)}
    return out if out['metrics'] else None


def tiles(M, base, out, D, F, names, mc_vals):
    """One tile per football method: price on top, the base-rate probability below (the share of peers whose 5-year
    revenue CAGR reached what the price requires; for companies valued on book or earnings, the share of peer quarters
    that traded at the P/E the price implies). Plus the outside view's expected price and 80% range."""
    sic, size = F.get('sic'), size_of(F.get('revenue'))
    p5 = _peer(D, 'cagr5', sic, size, names)
    pe = _peer(D, 'pe_hist', sic, size, names) or _peer(D, 'pe', sic, size, names, min_obs=12)
    eps = F.get('eps')
    res = []
    for b in out['football']:
        if b['method'] == '52-week trading range' or not fin(b.get('point')):
            continue
        t = {'method': b['method'], 'price': b['point'], 'low': b.get('low'), 'high': b.get('high')}
        if base and p5:
            g, st = req_growth(M, base, b['point'])
            t.update({'basis': 'growth', 'required': g, 'status': st,
                      'p': _prob(p5, g) if g is not None else (1.0 if st == 'below' else 0.0 if st == 'above' else None)})
            if mc_vals:
                t['p_mc'] = share_at_least(mc_vals, b['point'])
        elif pe and fin(eps) and eps > 0:
            req = b['point'] / eps
            t.update({'basis': 'pe', 'required': req, 'p': _prob(pe, req)})
        res.append(t)
    return {'tiles': res, 'growth_group': ({k: p5[k] for k in ('group', 'label', 'n', 'companies', 'p25', 'p50', 'p75')} if p5 else None),
            'pe_group': ({k: pe[k] for k in ('group', 'label', 'n', 'companies', 'p25', 'p50', 'p75')} if pe else None)}


def enrich(M, out, F, base, W, ctx):
    """Add the outside view to one company's analysis (called at the end of valuation.analyse, before the range)."""
    B = ctx.get('br')
    if not B:
        return out
    D, names = B['D'], B.get('names') or {}
    rec, periods = ctx.get('panel') or {}, B['periods']
    sic, size = F.get('sic'), size_of(F.get('revenue'))
    price = F.get('price')
    own = None
    if base:
        own = {'g': clamp(F['g0'], -0.20, 0.40) if fin(F.get('g0')) else 0.05, 'sg': clamp(F['sg'], 0.03, 0.25) if fin(F.get('sg')) else 0.08}
    # ---- outside view: the peers' distributions next to the company's own figures
    ov = {'size': size, 'size_label': SIZE_LABEL.get(size), 'rows': []}
    q = rec.get('q') or {}
    own_rev = [q['rev'][i] / q['rev'][i - 4] - 1 for i in range(4, len(q.get('rev') or []))
               if fin(q['rev'][i]) and fin(q['rev'][i - 4]) and q['rev'][i - 4] > 0]
    mq = [o / r for o, r in zip(q.get('oi') or [], q.get('rev') or []) if fin(o) and fin(r) and r > 0]

    def row(label, metric, inside, fmt='pct', inside_note=None, min_obs=MIN_OBS):
        p = _peer(D, metric, sic, size, names, min_obs=min_obs)
        ov['rows'].append({'input': label, 'metric': metric, 'fmt': fmt, 'inside': inside, 'inside_note': inside_note,
                           'outside': {k: p[k] for k in ('group', 'label', 'n', 'companies', 'p10', 'p25', 'p50', 'p75', 'p90')} if p else None,
                           'inside_pct': _r(bisect.bisect_left(p['_xs'], inside) / len(p['_xs']), 3) if p and fin(inside) else None})
    row('Revenue growth, a quarter vs the year before', 'rev_yoy_q', median(own_rev[-8:]), inside_note='median of its last 8 quarters')
    row('Revenue CAGR, 5 years', 'cagr5', F.get('g0'), inside_note='its last four quarters vs the four before (the DCF starts here)')
    row('Revenue CAGR, 3 years', 'cagr3', cagr3_of(q.get('rev') or []))
    row('Operating margin', 'opm_q', (F['oi'] / F['revenue']) if fin(F.get('oi')) and fin(F.get('revenue')) and F['revenue'] > 0 else None)
    row('Operating margin change over 5 years (points)', 'opm_chg5', None)
    row('WACC', 'wacc', (W or {}).get('wacc'), min_obs=12)
    row('Terminal growth (peers\' 10-year CAGR)', 'cagr10', M.TERM_G, inside_note='the base DCF\'s fixed assumption')
    row('P/E', 'pe_hist', F.get('pe'), fmt='x', inside_note='today')
    row('EV/Sales', 'evs_hist', F.get('ev_sales'), fmt='x', inside_note='today')
    row('EV/EBITDA', 'ev_ebitda', F.get('ev_ebitda'), fmt='x', inside_note='today (peers: today)', min_obs=12)
    mc_vals = None
    if base:
        omc = outside_mc(M, base, price, D, sic, size, seed=zlib.crc32(str(F.get('ticker')).encode()) + 1)
        if omc:
            mc_vals = omc.pop('_vals')
            g = omc['groups']
            omc['group_labels'] = {k: key_label(v, names) if v else None for k, v in g.items()}
            ov['mc'] = omc
            out['football'].append({'method': 'Outside view — base-rate Monte Carlo', 'low': omc['p10'], 'high': omc['p90'], 'point': omc['p50'],
                                    'note': f"expected {omc['mean']:.2f}; {omc['n']:,} DCFs with growth, margin, WACC and terminal growth drawn from peers "
                                            f"({key_label(g['growth_margin'], names)}, {omc['n_windows']:,} five-year windows)"})
    if out.get('mc'):
        ov['inside_mc'] = {k: out['mc'].get(k) for k in ('n', 'mean', 'p10', 'p50', 'p90', 'p_above')}
    out['outside_view'] = ov
    # ---- consensus probabilities
    out['consensus_odds'] = consensus_odds(M, F, base, rec, periods, ctx.get('cons'), ctx.get('crow'), D, names, own)
    # ---- stage, sensitivity, river
    out['stage'] = stage_block(M, F, base, W, out, rec, D, names)
    sens = sensitivity(M, F, base, W, out, D, names)
    if sens:
        out['sensitivity'] = sens
    out.pop('_path_base', None)
    if ctx.get('river'):
        out['river'] = ctx['river']
    # ---- combined forecast (walk-forward weights; published beside "Our model" unless it beat it out of sample)
    cb = (B.get('combined') or {}).get('live', {}).get(str(F['cik']))
    if cb and fin(price):
        mdl = B['combined']
        sc = ((mdl.get('horizons') or {}).get('3m') or {}).get('scores') or {}
        c, z = sc.get('combined') or {}, sc.get('zero') or {}
        replace = mdl.get('replace_rotation')
        label = 'Our model (combined forecast)' if replace else 'Combined forecast (3 months)'
        note = (f"3-month view; out of sample: error {c.get('mae', 0) * 100:.1f}% vs {z.get('mae', 0) * 100:.1f}% for 'no change', "
                f"80% range held {c.get('coverage80', 0) * 100:.0f}% of the time ({c.get('n', 0):,} forecasts, {c.get('origins', 0)} quarters)") if c else 'walk-forward combination'
        out['football'].append({'method': label, 'low': price * (1 + cb['lo']), 'high': price * (1 + cb['hi']), 'point': price * (1 + cb['ret']), 'note': note})
        out['combined'] = {**cb, 'price': price * (1 + cb['ret']), 'low': price * (1 + cb['lo']), 'high': price * (1 + cb['hi']),
                           'replaces_rotation': bool(replace), 'weights': ((mdl.get('horizons') or {}).get('3m') or {}).get('weights')}
        if replace:
            for b in out['football']:
                if b['method'] == 'Our model (Rotation forecast)':
                    b['method'] = 'Rotation forecast (superseded: higher out-of-sample error)'
    out['base_rates'] = tiles(M, base, out, D, F, names, mc_vals)
    if ov.get('mc'):
        out['base_rates']['expected'] = {'price': ov['mc']['mean'], 'p10': ov['mc']['p10'], 'p90': ov['mc']['p90'], 'p_above': ov['mc']['p_above']}
    return out


# ------------------------------------------------------------------ the backtest panel and the combined forecast
FEATURES = ['dcf_gap', 'pe_gap', 'p_implied', 'target_gap']
FEATURE_LABEL = {'dcf_gap': 'inside view: DCF value ÷ price − 1', 'pe_gap': 'outside view: peer-median P/E × EPS ÷ price − 1',
                 'p_implied': 'outside view: base rate of the growth the price implies', 'target_gap': "analysts' mean target ÷ price − 1"}
CLIP = {'dcf_gap': (-1.0, 3.0), 'pe_gap': (-1.0, 3.0), 'p_implied': (0.0, 1.0), 'target_gap': (-0.8, 2.0)}


def _price_at(dates, px, day):
    j = bisect.bisect_right(dates, day) - 1
    return px[j][1] if j >= 0 else None


def _base_at(M, F, r4, o4, g0, shares, wacc):
    if not (fin(r4) and r4 > 0 and fin(o4) and o4 > 0 and fin(shares) and shares > 0 and fin(wacc)):
        return None
    rev = F.get('revenue') if fin(F.get('revenue')) and F['revenue'] > 0 else r4
    return {'rev0': r4, 'years': M.YEARS, 'growth': M.fade(clamp(g0, -0.2, 0.4) if fin(g0) else 0.05, M.TERM_G), 'margin': o4 / r4,
            'tax': F.get('tax_rate', 0.21), 'da': (F.get('da') or 0) / rev, 'capex': (F.get('capex') or 0) / rev, 'wc': M.WC_SHARE,
            'wacc': max(wacc, M.TERM_G + 0.01), 'g': M.TERM_G, 'terminal': 'roic', 'roic': 0.15, 'debt': F.get('debt') or 0,
            'cash': F.get('cash') or 0, 'claims': F.get('claims') or 0, 'nonop': 0.0, 'shares': shares}


def origin_rows(M, Fs, P, periods, sic_of, today):
    """One row per company and quarter origin (60 days after the quarter ends) with the price then, the trailing figures
    known then, the forward returns at 3 and 12 months, plus a 'live' row per company (today's price, latest figures)."""
    rows, live = [], {}
    for cik, F in Fs.items():
        px = F.get('_px') or []
        if not px:
            continue
        dates = [d for d, _ in px]
        q = (P.get(cik) or {}).get('q') or {}
        n = len(periods)
        rev, oi, eps, sh = ((q.get(k) or [None] * n) for k in ('rev', 'oi', 'eps', 'sh'))
        sic = sic_of.get(cik) or F.get('sic')
        last_i = None
        for i in range(7, n):
            s = lambda xs, a, b: sum(xs[a:b]) if all(fin(v) for v in xs[a:b]) else None
            r4, r8, o4, e4 = s(rev, i - 3, i + 1), s(rev, i - 7, i - 3), s(oi, i - 3, i + 1), s(eps, i - 3, i + 1)
            if not fin(r4) or r4 <= 0:
                continue
            last_i = i
            shares = sh[i] if fin(sh[i]) and sh[i] > 0 else F.get('shares')
            g0 = r4 / r8 - 1 if fin(r8) and r8 > 0 else None
            rec = {'cik': cik, 'sic': sic, 'size': size_of(r4), 'i': i, 'r4': r4, 'o4': o4, 'e4': e4, 'g0': g0, 'shares': shares}
            T = (M.quarter_end(periods[i]) + dt.timedelta(days=M.LAG_DAYS)).isoformat()
            if dates[0] <= T <= dates[-1]:
                p0 = _price_at(dates, px, T)
                fw = {}
                for h, days in HORIZONS.items():
                    d2 = (dt.date.fromisoformat(T) + dt.timedelta(days=days)).isoformat()
                    if d2 <= dates[-1]:
                        p1 = _price_at(dates, px, d2)
                        fw[h] = clamp(p1 / p0 - 1, -0.95, 3.0) if fin(p1) and fin(p0) and p0 > 0 else None
                rows.append({**rec, 'date': T, 'price': p0, 'fwd': fw})
        if last_i is not None:
            r = next((x for x in reversed(rows) if x['cik'] == cik and x['i'] == last_i), None)
            base = r or {'cik': cik}
            if not r:                                           # the latest quarter is not yet 60 days old: rebuild it
                i = last_i
                s = lambda xs, a, b: sum(xs[a:b]) if all(fin(v) for v in xs[a:b]) else None
                r4, r8 = s(rev, i - 3, i + 1), s(rev, i - 7, i - 3)
                base = {'cik': cik, 'sic': sic, 'size': size_of(r4), 'i': i, 'r4': r4, 'o4': s(oi, i - 3, i + 1), 'e4': s(eps, i - 3, i + 1),
                        'g0': r4 / r8 - 1 if fin(r8) and r8 > 0 else None, 'shares': sh[i] if fin(sh[i]) and sh[i] > 0 else F.get('shares')}
            live[cik] = {**{k: v for k, v in base.items() if k not in ('fwd', 'date', 'price')}, 'date': today.isoformat(), 'price': px[-1][1], 'fwd': {}}
    return rows, live


def _peer_median_pe(rows):
    """Per row: the median P/E (0–200) of its peers at the same origin, narrowest group with ≥ 5 companies (itself excluded)."""
    by = {}
    for r in rows:
        pe = r['price'] / r['e4'] if fin(r.get('e4')) and r['e4'] > 0 and fin(r.get('price')) else None
        r['_pe'] = pe if fin(pe) and 0 < pe <= 200 else None
        if r['_pe']:
            for k in group_keys(r['sic'], r['size']):
                by.setdefault(k, []).append((r['_pe'], r['cik']))
    srt = {k: sorted(v for v, _ in xs) for k, xs in by.items()}
    for r in rows:
        r['_peer_pe'] = None
        for k in group_keys(r['sic'], r['size']):
            xs = srt.get(k) or []
            own = r['_pe'] is not None and len(xs) > 0
            n = len(xs) - (1 if own else 0)
            if n >= 5:
                r['_peer_pe'] = median_without(xs, r['_pe']) if own else quantile(xs, 0.5)
                break


def features(M, rows, Fs, D, cons_of):
    """The four signals for each row, from data known at its date (the base rate uses windows that ended before its year)."""
    by_origin = {}
    for r in rows:
        by_origin.setdefault(r['date'][:10] if r.get('live') else r['i'], []).append(r)
    for grp in by_origin.values():
        _peer_median_pe(grp)
    for r in rows:
        F = Fs[r['cik']]
        W = F.get('_W') or {}
        price = r['price']
        x = {}
        b = _base_at(M, F, r['r4'], r.get('o4'), r.get('g0'), r.get('shares'), W.get('wacc'))
        if b and fin(price) and price > 0:
            v = M.value(b)
            if fin(v):
                x['dcf_gap'] = v / price - 1
            g, st = req_growth(M, {**b, 'growth': 0.0}, price, it=30)
            cut = None if r.get('live') else int(r['date'][:4])
            pk = D.pick('cagr5', r['sic'], r['size'], cutoff=cut)
            if pk:
                x['p_implied'] = share_at_least(pk[1], g) if g is not None else (1.0 if st == 'below' else 0.0 if st == 'above' else None)
        if r.get('_peer_pe') and fin(r.get('e4')) and r['e4'] > 0 and fin(price) and price > 0:
            x['pe_gap'] = r['_peer_pe'] * r['e4'] / price - 1
        snaps = cons_of(r['cik'])
        if snaps and fin(price) and price > 0:
            day = r['date'][:10]
            j = bisect.bisect_right([s[0] for s in snaps], day) - 1
            if j >= 0 and (dt.date.fromisoformat(day) - dt.date.fromisoformat(snaps[j][0])).days <= 20:
                tm = snaps[j][1]
                if fin(tm) and tm > 0:
                    x['target_gap'] = tm / price - 1
        r['x'] = {k: clamp(v, *CLIP[k]) for k, v in x.items() if fin(v)}
    return rows


def _design(rows, stats):
    X = []
    for r in rows:
        X.append([1.0] + [((r['x'][k] - stats[k][0]) / stats[k][1]) if k in r['x'] and stats.get(k) else 0.0 for k in FEATURES])
    return X


def _stats(rows):
    st = {}
    for k in FEATURES:
        xs = [r['x'][k] for r in rows if k in r['x']]
        if len(xs) >= 30:
            m = sum(xs) / len(xs)
            sd = math.sqrt(sum((v - m) ** 2 for v in xs) / (len(xs) - 1)) or 1.0
            st[k] = (m, sd)
    return st


def _fit(rows, h, lam_per_row=0.1):
    st = _stats(rows)
    X, y = _design(rows, st), [r['fwd'][h] for r in rows]
    w = ridge(X, y, lam_per_row * len(rows))
    return (w, st) if w else (None, st)


def _predict(w, st, rows):
    return [sum(a * b for a, b in zip(w, x)) for x in _design(rows, st)]


def walk_forward(rows, h, min_train=150):
    """Expanding-window walk-forward: each origin is forecast by a ridge fitted only on rows whose outcome was known by
    then; the 80% interval comes from the earlier out-of-sample errors (split conformal; in-sample errors until 200
    exist). Scored against 'no change' (a random walk) and the training-mean drift, both with conformal intervals."""
    days = HORIZONS[h]
    rows = [r for r in rows if r['fwd'].get(h) is not None]
    origins = sorted({r['date'] for r in rows})
    oos = []                                        # (origin, model residual, zero residual, drift residual)
    res = {'combined': [], 'zero': [], 'drift': []}
    feat_ic = {k: [] for k in FEATURES}
    for T in origins:
        Td = dt.date.fromisoformat(T)
        train = [r for r in rows if (dt.date.fromisoformat(r['date']) + dt.timedelta(days=days)) <= Td]
        test = [r for r in rows if r['date'] == T]
        if len(train) < min_train or len({r['date'] for r in train}) < 2 or len(test) < 10:
            continue
        w, st = _fit(train, h)
        if not w:
            continue
        pred = _predict(w, st, test)
        drift = sum(r['fwd'][h] for r in train) / len(train)
        known = [o for o in oos if (dt.date.fromisoformat(o[0]) + dt.timedelta(days=days)) <= Td]
        if len(known) >= 200:
            rm, rz, rd = ([o[i] for o in known] for i in (1, 2, 3))
        else:
            fitted = _predict(w, st, train)
            rm = [r['fwd'][h] - f for r, f in zip(train, fitted)]
            rz = [r['fwd'][h] for r in train]
            rd = [r['fwd'][h] - drift for r in train]
        qs = {k: (quantile(sorted(v), 0.1), quantile(sorted(v), 0.9)) for k, v in (('combined', rm), ('zero', rz), ('drift', rd))}
        for r, p in zip(test, pred):
            a = r['fwd'][h]
            for k, f in (('combined', p), ('zero', 0.0), ('drift', drift)):
                lo, hi = f + qs[k][0], f + qs[k][1]
                res[k].append((T, f, a, lo <= a <= hi, hi - lo, r['cik']))
            oos.append((T, a - p, a, a - drift))
        for k in FEATURES:
            pairs = [(r['x'][k], r['fwd'][h]) for r in test if k in r['x']]
            if len(pairs) >= 10:
                ic = spearman([p[0] for p in pairs], [p[1] for p in pairs])
                if ic is not None:
                    feat_ic[k].append((ic, len(pairs)))
    scores = {}
    for k, xs in res.items():
        if not xs:
            continue
        by = {}
        for T, f, a, *_ in xs:
            by.setdefault(T, []).append((f, a))
        ics = [spearman([p[0] for p in v], [p[1] for p in v]) for v in by.values()] if k == 'combined' else []
        ics = [v for v in ics if v is not None]
        scores[k] = {'n': len(xs), 'origins': len(by), 'mae': sum(abs(x[2] - x[1]) for x in xs) / len(xs),
                     'coverage80': sum(1 for x in xs if x[3]) / len(xs), 'width80': median([x[4] for x in xs]),
                     'direction_hit': (sum(1 for x in xs if (x[1] > 0) == (x[2] > 0)) / len(xs)) if k != 'zero' else None,
                     'share_up': sum(1 for x in xs if x[2] > 0) / len(xs)}
        if ics:
            scores[k]['ic_mean'] = sum(ics) / len(ics)
            scores[k]['ic_positive_share'] = sum(1 for v in ics if v > 0) / len(ics)
    fic = {k: {'ic_mean': sum(v[0] for v in xs) / len(xs), 'origins': len(xs), 'n': sum(v[1] for v in xs), 'label': FEATURE_LABEL[k]}
           for k, xs in feat_ic.items() if xs}
    return scores, fic, oos, res


def combined_model(M, Fs, rows, live, D, cons_of, today):
    """The combined forecast from origin_rows(): walk-forward scores per horizon, the final fit and today's forecasts."""
    for r in live.values():
        r['live'] = True
    features(M, rows + list(live.values()), Fs, D, cons_of)
    out = {'horizons': {}, 'live': {}, 'features': FEATURE_LABEL, 'origins_on_file': len({r['date'] for r in rows}), 'rows': len(rows)}
    for h, days in HORIZONS.items():
        scores, fic, oos, res = walk_forward(rows, h)
        hr = [r for r in rows if r['fwd'].get(h) is not None]
        blk = {'scores': scores, 'feature_ic': fic, 'n_rows': len(hr), 'origins': len({r['date'] for r in hr})}
        if len(hr) >= 150:
            w, st = _fit(hr, h)
            if w:
                blk['weights'] = {'intercept': w[0], **{k: (w[i + 1] if k in st else 0.0) for i, k in enumerate(FEATURES)}}
                blk['feature_scale'] = {k: list(v) for k, v in st.items()}
                blk['interval_from'] = 'earlier out-of-sample errors' if len(oos) >= 200 else 'in-sample errors (too few out-of-sample yet)'
                if h == '3m':
                    resid = [o[1] for o in oos] if len(oos) >= 200 else [r['fwd'][h] - f for r, f in zip(hr, _predict(w, st, hr))]
                    lo, hi = quantile(sorted(resid), 0.1), quantile(sorted(resid), 0.9)
                    L = list(live.values())
                    for r, p in zip(L, _predict(w, st, L)):
                        out['live'][r['cik']] = {'ret': clamp(p, -0.9, 2.0), 'lo': clamp(p + lo, -0.95, 3.0), 'hi': clamp(p + hi, -0.95, 3.0),
                                                 'horizon_days': days, 'inputs': {k: _r(v) for k, v in r['x'].items()}}
        if h == '3m':
            out['_pred'] = {(x[5], x[0]): x[1] for x in res.get('combined') or []}
        out['horizons'][h] = blk
    return out


# ------------------------------------------------------------------ the other models' scores
def score_rotation(rot_dir, read_json, paired=None, cik_of=None):
    """The Rotation next-quarter / next-month forecasts as the forecast ledger froze and resolved them: error of the forecast
    change vs 'no change', 80%-range coverage, direction vs the share that rose — live and backtest origins apart."""
    if not rot_dir:
        return None
    from pathlib import Path
    root = Path(rot_dir)
    head = read_json(root / 'forecast-ledger.json', {}) or {}
    out = {}
    for f, label in (('q', 'next quarter'), ('m', 'next month')):
        det = read_json(root / f'forecast-ledger-{f}.json', {}) or {}
        fields = det.get('fields') or []
        if not fields:
            continue
        src = {o['origin']: o.get('source') for o in ((head.get('freqs') or {}).get(f) or {}).get('origins') or []}
        ix = {k: fields.index(k) for k in ('close', 'lo80', 'hi80', 'forecast_change_pct', 'actual_change_pct', 'inside80') if k in fields}
        if len(ix) < 6:
            continue
        acc = {}
        pairs = []
        for origin, rows in (det.get('rows') or {}).items():
            s = src.get(origin) or 'unknown'
            for t, r in rows.items():
                fc, ac, ins = r[ix['forecast_change_pct']], r[ix['actual_change_pct']], r[ix['inside80']]
                if not (fin(fc) and fin(ac)):
                    continue
                a = acc.setdefault(s, {'n': 0, 'err': 0.0, 'naive': 0.0, 'inside': 0, 'dir': 0, 'up': 0})
                a['n'] += 1
                a['err'] += abs(ac - fc)
                a['naive'] += abs(ac)
                a['inside'] += bool(ins)
                a['dir'] += (fc > 0) == (ac > 0)
                a['up'] += ac > 0
                if paired is not None and cik_of and f == 'q':
                    c = cik_of.get(t)
                    if c:
                        pairs.append((c, origin, fc / 100, ac / 100))
        out[label] = {s: {'n': a['n'], 'mae_pts': a['err'] / a['n'], 'naive_mae_pts': a['naive'] / a['n'], 'coverage80': a['inside'] / a['n'],
                          'direction_hit': a['dir'] / a['n'], 'share_up': a['up'] / a['n'],
                          'beats_naive': a['err'] < a['naive']} for s, a in acc.items() if a['n']}
        if paired is not None and f == 'q':
            paired.extend(pairs)
    return out or None


def pair_with_combined(pairs, preds, max_days=45):
    """Paired errors on the same companies and quarters: the Rotation forecast vs the combined walk-forward forecast."""
    by = {}
    for (cik, T), f in preds.items():
        by.setdefault(cik, []).append((T, f))
    n, e_rot, e_cmb = 0, 0.0, 0.0
    for cik, origin, fc, ac in pairs:
        try:
            od = dt.date.fromisoformat(str(origin)[:10])
        except ValueError:
            try:
                od = dt.date(int(origin[:4]), 3 * int(origin[-1]), 28)
            except (ValueError, IndexError):
                continue
        best = min(by.get(cik, []), key=lambda x: abs((dt.date.fromisoformat(x[0]) - od).days), default=None)
        if not best or abs((dt.date.fromisoformat(best[0]) - od).days) > max_days:
            continue
        n += 1
        e_rot += abs(ac - fc)
        e_cmb += abs(ac - best[1])
    return {'n': n, 'mae_rotation': e_rot / n, 'mae_combined': e_cmb / n} if n else {'n': 0}


METRIC_LABEL = {'rev_yoy_q': 'revenue growth, quarter vs the year-ago quarter', 'eps_yoy_q': 'EPS growth, quarter vs the year-ago quarter (positive base)',
                'opm_chg_q': 'operating-margin change vs the year-ago quarter (points)', 'npm_chg_q': 'net-margin change vs the year-ago quarter (points)',
                'opm_q': 'quarterly operating margin', 'cagr3': 'revenue CAGR over 3 years', 'cagr5': 'revenue CAGR over 5 years',
                'cagr10': 'revenue CAGR over 10 years', 'opm_chg5': 'operating-margin change over 5 years (points)', 'wacc': 'WACC today',
                'pe': 'P/E today', 'ev_sales': 'EV/Sales today', 'ev_ebitda': 'EV/EBITDA today',
                'pe_hist': 'P/E at each quarter since mid-2022', 'evs_hist': 'EV/Sales at each quarter since mid-2022'}
PUBLISHED = ('rev_yoy_q', 'eps_yoy_q', 'cagr5', 'opm_q', 'opm_chg5', 'wacc', 'pe_hist')


def published_groups(D, names):
    """The hub's base-rate table: for the main metrics, each industry (SIC 3 and 2 digits, all sizes) and each size."""
    out = {}
    for m in PUBLISHED:
        table, nc = D.vals.get(m) or {}, D.ncos.get(m) or {}
        out[m] = {k: {**summary(xs), 'companies': nc.get(k, 0), 'label': key_label(k, names)} for k, xs in table.items()
                  if '|' not in k or k.startswith('*|')
                  if len(xs) >= MIN_OBS and nc.get(k, 0) >= MIN_COS}
    return out


def models_doc(comb, ledger, rot, hier_ix, cons_cal):
    """public/models.json: every model the site publishes, scored out of sample against a naive baseline."""
    h3 = (comb.get('horizons') or {}).get('3m') or {}
    c, z = (h3.get('scores') or {}).get('combined') or {}, (h3.get('scores') or {}).get('zero') or {}
    doc = {'combined': {k: v for k, v in comb.items() if not k.startswith('_') and k != 'live'}, 'live_forecasts': len(comb.get('live') or {}),
           'rotation': rot, 'valuation_ledger': {'snapshots': (ledger or {}).get('snapshots'), 'scores': (ledger or {}).get('scores')}}
    sc = (hier_ix or {}).get('scores') or {}
    if sc:
        doc['hier'] = {'asof': hier_ix.get('asof'), 'horizon': hier_ix.get('horizon'), 'levels': sc,
                       'note': 'pipeline/hier.py, one quarter ahead on a rolling origin: median absolute revenue-growth error of the model '
                               '(cond: given the parent\'s actual growth; uncond: with the parent forecast too) vs the naive forecast (growth '
                               'stays what it was); cover80: the share of actuals inside the 80% interval; beats_naive: entities where uncond < naive.'}
    pr = (cons_cal or {}).get('price') or {}
    if pr:
        doc['polymarket_prices'] = {k: pr.get(k) for k in ('n', 'mean_abs_err_pct', 'inside80')}
        doc['polymarket_prices']['note'] = "Polymarket's implied price (ladder median) frozen before each market's date and scored when it resolved (app/consensus.py)."
    verdict = []
    if c and z:
        better = c['mae'] < z['mae']
        verdict.append(f"Combined forecast, 3 months: mean absolute error {c['mae'] * 100:.1f}% vs {z['mae'] * 100:.1f}% for 'no change' "
                       f"({'better' if better else 'not better'}); 80% range coverage {c['coverage80'] * 100:.0f}% over {c['n']:,} forecasts "
                       f"from {c['origins']} quarters — the quarters, not the forecasts, are the independent sample.")
    pw = comb.get('paired_with_rotation') or {}
    if pw.get('n'):
        verdict.append(f"Paired with the Rotation next-quarter forecasts on {pw['n']:,} company-quarters: error {pw['mae_combined'] * 100:.1f}% (combined) vs "
                       f"{pw['mae_rotation'] * 100:.1f}% (Rotation); " + ('the combined forecast replaces it on the Fair value page.' if comb.get('replace_rotation')
                                                                        else 'the Rotation forecast stays; the combined one is shown beside it.'))
    else:
        verdict.append('No paired comparison with the Rotation forecasts yet (the forecast ledger was not available or does not overlap): the '
                       'Rotation forecast stays as "Our model" and the combined forecast is published beside it with its own score.')
    doc['verdict'] = verdict
    doc['notes'] = ['Walk-forward: every forecast uses only data known 60 days after its quarter ended, and a model fitted on outcomes '
                    'already known then. Analysts\' targets enter only from the consensus module\'s daily snapshots (about a year so far); '
                    'Polymarket prices have no history yet, so their weight is not learned — they are scored in the valuation ledger as months pass.',
                    'The DCF features at past dates use today\'s cost of capital, debt and cash (small look-ahead), stated here.']
    return doc
