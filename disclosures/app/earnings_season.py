"""Earnings season (4.18): previews, the scorecard, our own beat model and estimates, post-earnings drift, peer
read-through, prediction-market and options distributions, indicators and the season's breadth — every forecast frozen
in a forecast book (forecast_book.py) before the report and scored after it.

  collect   GAAP diluted EPS for every filer and the last six calendar quarters (SEC XBRL frames,
            EarningsPerShareDiluted in USD per share) — the "as reported" side of the non-GAAP gap. Nothing else is fetched:
            the rest is the hub's own data.
  build     public/ from the consensus branch's public/ (analysts' estimates and history, Polymarket beat markets and
            price ladders, the calendar, the crowd's closed beat markets), the hub's daily closes (cache/prices), options
            (market/options/<T>.json), FINRA short interest, insiders' Form 4 summary and the revenue / net income frames.

What is frozen (cache/book.json) and when: three days before a report or later, our beat probability (with the inputs and
Polymarket's price at that moment), our EPS and revenue estimates beside the analysts', the options-implied move, the peer
read-through; the day after a report, the predicted 60-trading-day drift. Each is resolved once from the actuals.

Honest limits, written into the files: the history behind the model is what the consensus collector has gathered (Yahoo
keeps four quarters per company, so about a year); revisions and revenue estimates exist only from the day the daily
snapshots began; implied moves, insider buying and Polymarket prices enter the model as the frozen live forecasts
resolve. Peers are the same sector (no supplier map). Not investment advice.

    python app/earnings_season.py collect --root re
    python app/earnings_season.py build --root re --cons cons/public --hub data
"""
import argparse
import bisect
import datetime as dt
import gzip
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import forecast_book as FB  # noqa: E402
import frames as FR  # noqa: E402

MODEL = 'beat-logit-v1'
EPS_FRAMES = 'https://data.sec.gov/api/xbrl/frames/us-gaap/EarningsPerShareDiluted/USD-per-shares/{period}.json'
PRIOR_BEAT = 0.75            # the long-run share of US reports above the consensus (shrinkage prior for short histories)
FREEZE_DAYS = 3              # a report this many days away or nearer is frozen
PREVIEW_DAYS = 21            # previews published for reports up to three weeks ahead …
RECENT_DAYS = 10             # … and the results of the last ten days
DRIFT_DAYS = 60              # post-earnings drift horizon, in trading days
RATE = 0.04                  # risk-free rate for the options density (an approximation; documented in the files)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def read_json(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def write_json(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(clean(obj), separators=(',', ':'), ensure_ascii=False, allow_nan=False), encoding='utf-8')


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if hasattr(o, 'item'):
        o = o.item()
    if isinstance(o, float):
        return round(o, 6) if math.isfinite(o) else None
    return o


def fname(t):
    return re.sub(r'[^A-Za-z0-9-]', '_', str(t).upper().replace('.', '-'))


def _f(v):
    try:
        v = float(v)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def clip(v, lo, hi):
    return None if v is None else max(lo, min(hi, v))


def logit(p):
    p = min(0.999, max(0.001, p))
    return math.log(p / (1 - p))


def season_of(quarter_end):
    """The calendar quarter a fiscal quarter belongs to ('2026-08-31' → 'CY2026Q3'), as SEC frames align them."""
    return FR._quarter_of(quarter_end[:10])


def day(s):
    return dt.date.fromisoformat(str(s)[:10])


# ------------------------------------------------------------------ inputs
class Prices:
    """Daily closes from the hub's cache (cache/prices/<TICKER>.json.gz: rows [date, close, volume])."""

    def __init__(self, hub):
        self.dir = Path(hub) / 'cache' / 'prices' if hub else None
        self.c = {}

    def get(self, t):
        t = str(t or '').upper()
        if t in self.c:
            return self.c[t]
        out = None
        if self.dir:
            p = self.dir / (re.sub(r'[^A-Z0-9]', '_', t) + '.json.gz')
            try:
                with gzip.open(p, 'rt', encoding='utf-8') as f:
                    rows = [r for r in json.load(f).get('rows') or [] if len(r) >= 2 and r[1]]
                if rows:
                    out = ([r[0][:10] for r in rows], [float(r[1]) for r in rows], [float(r[2] or 0) if len(r) > 2 else 0.0 for r in rows])
            except (OSError, ValueError):
                out = None
        self.c[t] = out
        return out


def reaction(px, report, spy=None):
    """The move around a report: the close before the report day to the close after it (two sessions, so reports
    before the open and after the close are both inside). (move, excess vs SPY, index of the session after)."""
    if not px:
        return None, None, None
    d, c, _ = px
    i0 = bisect.bisect_left(d, report) - 1                # last session before the report day
    i1 = bisect.bisect_right(d, report)                   # first session after it
    if i0 < 0 or i1 >= len(d) or (day(d[i1]) - day(report)).days > 6 or (day(report) - day(d[i0])).days > 6:
        return None, None, None
    mv = c[i1] / c[i0] - 1
    ex = None
    if spy:
        s0, s1 = _close_on(spy, d[i0]), _close_on(spy, d[i1])
        if s0 and s1:
            ex = mv - (s1 / s0 - 1)
    return mv, ex, i1


def drift(px, i1, spy, n=DRIFT_DAYS):
    """Excess return vs SPY from the session after a report to n sessions later (None until then)."""
    if not px or i1 is None or i1 + n >= len(px[0]):
        return None
    d, c, _ = px
    s0, s1 = _close_on(spy, d[i1]), _close_on(spy, d[i1 + n])
    if not s0 or not s1:
        return None
    return (c[i1 + n] / c[i1] - 1) - (s1 / s0 - 1)


def _close_on(px, date):
    if not px:
        return None
    d, c, _ = px
    i = bisect.bisect_right(d, date) - 1
    return c[i] if i >= 0 and (day(date) - day(d[i])).days <= 5 else None


def realized_vol(px, n=21):
    if not px or len(px[1]) < n + 1:
        return None
    c = np.array(px[1][-(n + 1):])
    r = np.diff(np.log(c))
    return float(np.std(r, ddof=1) * math.sqrt(252))


def momentum(px, n=21):
    if not px or len(px[1]) < n + 1:
        return None
    return px[1][-1] / px[1][-(n + 1)] - 1


def load_consensus(cons):
    """{ticker: compact record} from the consensus branch's public/c/<cik>.json."""
    out = {}
    for p in sorted((Path(cons) / 'c').glob('*.json')):
        d = read_json(p, {}) or {}
        t = d.get('ticker')
        if not t:
            continue
        a = d.get('analysts') or {}
        per = {x.get('period'): x for x in a.get('periods') or []}
        q0, y0 = per.get('0q') or {}, per.get('0y') or {}
        mk = d.get('markets') or []
        out[t] = {
            'ticker': t, 'cik': d.get('cik'), 'name': d.get('name'), 'sector': d.get('sector') or 'Other',
            'price': _f(a.get('price')), 'shares': _f(a.get('shares')), 'next': a.get('next_earnings') or {},
            'q0': q0, 'y0': y0, 'surprises': [s for s in d.get('surprises') or [] if s.get('quarter')],
            'snap_fields': d.get('snapshot_fields') or [], 'snapshots': d.get('snapshots') or [],
            'beat': [m for m in mk if m.get('kind') == 'beat'],
            'above': [m for m in mk if m.get('kind') == 'above' and not m.get('closed') and (m.get('stats') or {}).get('strikes')],
            'eps_ladders': [m for m in mk if m.get('kind') == 'metric' and re.search(r'\bEPS\b|earnings per share', m.get('title') or '', re.I)
                            and (m.get('stats') or {}).get('strikes')],
            'calib': d.get('calibration') or [], 'revenue_history': a.get('revenue_history') or [],
        }
    return out


def snap_series(rec, field):
    """[(date, quarter_end, value)] of one snapshot field, oldest first."""
    F = rec['snap_fields']
    if field not in F:
        return []
    i, j = F.index(field), F.index('quarter_end') if 'quarter_end' in F else None
    out = []
    for dte, row in rec['snapshots']:
        if isinstance(row, list) and len(row) > i and row[i] is not None:
            out.append((dte, row[j] if j is not None else None, row[i]))
    return sorted(out)


def snap_on(series, date, quarter=None):
    """The last snapshot value on or before a date (for that quarter when given)."""
    best = None
    for dte, q, v in series:
        if dte > date:
            break
        if quarter is None or q == quarter:
            best = (dte, v)
    return best


# ------------------------------------------------------------------ options: implied move and the risk-neutral density
def implied_move(opt, report):
    """The options-implied earnings move: the event variance between the last expiry before the report and the first one
    after it, σ₂²T₂ − σ₁²T₂ (the extra variance the report adds), as an expected absolute move √(2/π)·σ_event. Without an
    expiry before the report: the whole move to the first expiry after it. None without a term structure."""
    term = [(e, _f(v)) for e, v in (opt or {}).get('term') or [] if _f(v)]
    asof = str((opt or {}).get('as_of') or '')[:10]
    if not term or not asof or report < asof:
        return None
    t0 = day(asof)
    after = [(e, v) for e, v in term if e > report]
    before = [(e, v) for e, v in term if asof < e < report]
    if not after:
        return None
    e2, s2 = after[0]
    T2 = max((day(e2) - t0).days, 1) / 365
    if before:
        e1, s1 = before[-1]
        ev = (s2 ** 2 - s1 ** 2) * T2
        if ev > 0:
            return {'move': math.sqrt(2 / math.pi) * math.sqrt(ev), 'expiry': e2, 'before': e1, 'iv_after': s2, 'iv_before': s1,
                    'method': 'event variance between the expiries around the report', 'asof': asof}
    return {'move': math.sqrt(2 / math.pi) * s2 * math.sqrt(T2), 'expiry': e2, 'before': None, 'iv_after': s2, 'iv_before': None,
            'method': 'whole move to the first expiry after the report (no expiry before it)', 'asof': asof}


def _bs_call(S, K, T, sig, r):
    sig = np.maximum(sig, 1e-4)
    d1 = (np.log(S / K) + (r + 0.5 * sig ** 2) * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    from math import erf
    N = np.vectorize(lambda x: 0.5 * (1 + erf(x / math.sqrt(2))))
    return S * N(d1) - K * math.exp(-r * T) * N(d2)


def rnd(smile, spot, days, r=RATE):
    """Risk-neutral distribution of the price at one expiry (Breeden–Litzenberger) from the implied-volatility smile: a
    quadratic fit of IV against log-moneyness smooths the quotes, call prices on a fine strike grid, the probability of
    finishing above K = −e^{rT}·∂C/∂K (kept between 0 and 1 and never rising), the density its negative slope.
    Returns {grid, survival, density, median, q10, q90} or None with fewer than five usable quotes."""
    pts = [(float(k), float(v)) for k, v in smile or [] if _f(k) and _f(v) and 0.01 < float(v) < 3 and 0.4 * spot < float(k) < 1.8 * spot]
    if len(pts) < 5 or not spot or days <= 0:
        return None
    K = np.array([p[0] for p in pts])
    iv = np.array([p[1] for p in pts])
    x = np.log(K / spot)
    a = np.polyfit(x, iv, 2)
    T = days / 365
    lo, hi = max(K.min() * 0.9, 0.35 * spot), min(K.max() * 1.1, 1.9 * spot)
    g = np.linspace(lo, hi, 400)
    sig = np.clip(np.polyval(a, np.log(g / spot)), 0.02, 3)
    C = _bs_call(spot, g, T, sig, r)
    surv = np.clip(-math.exp(r * T) * np.gradient(C, g), 0, 1)
    surv = np.minimum.accumulate(surv)
    dens = np.clip(-np.gradient(surv, g), 0, None)

    def q(level):
        idx = np.where(surv <= level)[0]
        return float(g[idx[0]]) if len(idx) else None
    return {'grid': g, 'survival': surv, 'density': dens, 'median': q(0.5), 'q10': q(0.9), 'q90': q(0.1), 'expiry_days': days}


def survival_at(dist, k):
    if not dist:
        return None
    return float(np.interp(k, dist['grid'], dist['survival']))


# ------------------------------------------------------------------ logistic regression (numpy, L2, Newton steps)
def fit_logit(X, y, l2=1.0, iters=30):
    X, y = np.asarray(X, float), np.asarray(y, float)
    mu, sd = X.mean(0), X.std(0)
    sd[sd < 1e-9] = 1
    Z = np.column_stack([np.ones(len(X)), (X - mu) / sd])
    w = np.zeros(Z.shape[1])
    reg = np.eye(Z.shape[1]) * l2
    reg[0, 0] = 0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Z @ w))
        W = p * (1 - p)
        H = Z.T @ (Z * W[:, None]) + reg
        gvec = Z.T @ (p - y) + reg @ w
        step = np.linalg.solve(H, gvec)
        w -= step
        if np.abs(step).max() < 1e-7:
            break
    return {'w': w, 'mu': mu, 'sd': sd}


def predict_logit(m, X):
    X = np.atleast_2d(np.asarray(X, float))
    Z = np.column_stack([np.ones(len(X)), (X - m['mu']) / m['sd']])
    return 1 / (1 + np.exp(-Z @ m['w']))


FEATURES = ['beat_rate', 'mean_surprise', 'has_history', 'sector_season', 'revision_30d', 'has_revision', 'polymarket_logit', 'has_polymarket',
            'implied_move', 'has_implied', 'insider_net', 'has_insider']
OPTIONAL = {'revision_30d': 'has_revision', 'polymarket_logit': 'has_polymarket', 'implied_move': 'has_implied', 'insider_net': 'has_insider'}
MIN_SUPPORT = 150            # an optional input enters the model once this many training reports have it


def vec(f):
    return [f.get(k) if f.get(k) is not None else 0.0 for k in FEATURES]


def fit_beat(rows):
    """Fit on [(features, y)]; optional inputs with too little support are left out (their columns zeroed)."""
    if len(rows) < 40 or len({y for _, y in rows}) < 2:
        return None
    use = {k for k, flag in OPTIONAL.items() if sum(1 for f, _ in rows if f.get(flag)) >= MIN_SUPPORT}
    drop = [i for i, k in enumerate(FEATURES) if (k in OPTIONAL and k not in use) or (k in OPTIONAL.values() and k not in {OPTIONAL[u] for u in use})]
    X = np.array([vec(f) for f, _ in rows])
    X[:, drop] = 0
    m = fit_logit(X, [y for _, y in rows])
    m['drop'] = drop
    m['used'] = [k for i, k in enumerate(FEATURES) if i not in drop]
    m['n'] = len(rows)
    return m


def prob(m, f):
    if not m:
        return None
    x = np.array(vec(f), float)
    x[m['drop']] = 0
    return float(predict_logit(m, x)[0])


# ------------------------------------------------------------------ history: one row per past report
def history(cos, prices, spy):
    """Every past report on file with its outcome, price reaction and drift, oldest first."""
    ev = []
    for t, rec in cos.items():
        px = prices.get(t)
        for s in rec['surprises']:
            est, act, rep = _f(s.get('eps_est')), _f(s.get('eps_act')), s.get('reported')
            if est is None or act is None or not rep:
                continue
            mv, ex, i1 = reaction(px, rep, spy)
            ev.append({'ticker': t, 'sector': rec['sector'], 'quarter': s['quarter'][:10], 'season': season_of(s['quarter']), 'reported': rep[:10],
                       'est': est, 'act': act, 'surprise': _f(s.get('surprise')) if s.get('surprise') is not None else ((act - est) / abs(est) if est else None),
                       'beat': 1 if act > est else 0, 'move': mv, 'excess': ex, 'drift': drift(px, i1, spy),
                       'drift_end': (px[0][i1 + DRIFT_DAYS] if px and i1 is not None and i1 + DRIFT_DAYS < len(px[0]) else None)})
    ev.sort(key=lambda e: (e['reported'], e['ticker']))
    return ev


def attach_features(ev, cos, calib):
    """The inputs each report had before it happened (only earlier reports are used), added in place."""
    by_t, by_sec = {}, {}
    for e in ev:
        prior = by_t.setdefault(e['ticker'], [])
        e['f'] = base_features(prior, sector_prior(by_sec.get((e['sector'], e['season']), []), e['reported']))
        snaps = snap_series(cos[e['ticker']], 'eps_q') if e['ticker'] in cos else []
        r30 = revision_30d(snaps, e['reported'], e['quarter'])
        if r30 is not None:
            e['f'].update(revision_30d=r30, has_revision=1)
        p = calib.get((e['ticker'], e['reported']))
        if p is not None:
            e['f'].update(polymarket_logit=logit(p), has_polymarket=1)
            e['pm'] = p
        prior.append(e)
        by_sec.setdefault((e['sector'], e['season']), []).append(e)
    return ev


def sector_prior(rows, before):
    return [r for r in rows if r['reported'] < before]


def base_features(prior, sector_rows):
    n = len(prior)
    beats = sum(p['beat'] for p in prior[-8:])
    k = min(n, 8)
    sur = [clip(p['surprise'], -0.5, 0.5) for p in prior[-4:] if p.get('surprise') is not None]
    sb = sum(r['beat'] for r in sector_rows)
    return {'beat_rate': (beats + 3 * PRIOR_BEAT) / (k + 3), 'mean_surprise': sum(sur) / len(sur) if sur else 0.0, 'has_history': 1 if n else 0,
            'sector_season': (sb + 5 * PRIOR_BEAT) / (len(sector_rows) + 5), 'n_prior': n, 'n_sector': len(sector_rows)}


def revision_30d(snaps, before, quarter):
    """Change of the quarter's consensus EPS over the 30 days before a date, from the daily snapshots (None when the
    snapshots do not reach that far back)."""
    a = snap_on(snaps, (day(before) - dt.timedelta(days=1)).isoformat(), quarter)
    b = snap_on(snaps, (day(before) - dt.timedelta(days=30)).isoformat(), quarter)
    if not a or not b or not b[1] or (day(a[0]) - day(b[0])).days < 20:
        return None
    return clip(a[1] / b[1] - 1, -0.3, 0.3) if b[1] > 0 else clip((a[1] - b[1]) / max(abs(b[1]), 0.05), -0.3, 0.3)


def walk_forward(ev, book_rows=()):
    """Monthly walk-forward: each month's reports predicted by a model fitted only on reports before that month.
    Returns ({(ticker, reported): p}, monthly summaries)."""
    rows = [e for e in ev if e.get('f')]
    if not rows:
        return {}, []
    months = sorted({e['reported'][:7] for e in rows})
    oos, per = {}, []
    extra = list(book_rows)
    for m in months:
        train = [(e['f'], e['beat']) for e in rows if e['reported'][:7] < m] + [(f, y) for f, y, d in extra if d[:7] < m]
        test = [e for e in rows if e['reported'][:7] == m]
        model = fit_beat(train)
        if not model:
            continue
        pairs = []
        for e in test:
            p = prob(model, e['f'])
            oos[(e['ticker'], e['reported'])] = p
            pairs.append((p, e['beat']))
        sc = FB.score_prob(pairs)
        per.append({'month': m, 'n': sc['n'], 'brier': sc['brier'], 'brier_base_rate': sc['brier_base_rate'], 'hit_rate': sc['hit_rate'], 'train': len(train)})
    return oos, per


# ------------------------------------------------------------------ the PEAD model (linear, walk-forward)
def sue(prior, est, act):
    diffs = [p['act'] - p['est'] for p in prior[-8:]]
    sd = float(np.std(diffs, ddof=1)) if len(diffs) >= 3 else 0.0
    den = max(sd, 0.02 * abs(est), 0.01)
    return clip((act - est) / den, -6, 6)


def pead_x(e):
    return [1.0, clip(e.get('sue') or 0, -4, 4), clip(e.get('surprise') or 0, -0.5, 0.5), clip(e.get('excess') or 0, -0.3, 0.3)]


def fit_ols(X, y, l2=1e-3):
    X, y = np.asarray(X, float), np.asarray(y, float)
    reg = np.eye(X.shape[1]) * l2
    reg[0, 0] = 0
    return np.linalg.solve(X.T @ X + reg, X.T @ y)


def pead_walk_forward(ev):
    """Fit drift ~ SUE + surprise + 2-day reaction on reports whose 60-day window closed before each month; returns the
    out-of-sample residuals, rank IC and the final coefficients."""
    rows = [e for e in ev if e.get('drift') is not None and e.get('move') is not None]
    months = sorted({e['reported'][:7] for e in rows})
    resid, pairs = [], []
    for m in months:
        train = [e for e in rows if (e.get('drift_end') or '9999') < m + '-01']
        test = [e for e in rows if e['reported'][:7] == m]
        if len(train) < 200:
            continue
        b = fit_ols([pead_x(e) for e in train], [e['drift'] for e in train])
        for e in test:
            pr = float(np.dot(b, pead_x(e)))
            resid.append(e['drift'] - pr)
            pairs.append((pr, e['drift']))
    coef = fit_ols([pead_x(e) for e in rows], [e['drift'] for e in rows]) if len(rows) >= 200 else None
    return {'residuals': resid, 'ic': spearman([a for a, _ in pairs], [b for _, b in pairs]) if len(pairs) >= 30 else None, 'n_oos': len(pairs),
            'coef': coef, 'n': len(rows),
            'top_minus_bottom': quintile_spread(pairs)}


def spearman(a, b):
    if len(a) < 3:
        return None
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    c = np.corrcoef(ra, rb)[0, 1]
    return float(c) if np.isfinite(c) else None


def quintile_spread(pairs):
    if len(pairs) < 50:
        return None
    s = sorted(pairs)
    k = len(s) // 5
    return float(np.mean([y for _, y in s[-k:]]) - np.mean([y for _, y in s[:k]]))


# ------------------------------------------------------------------ peer read-through
def readthrough_beta(ev):
    """Slope (through zero) of a report's surprise on the mean surprise of same-sector reports earlier in that season."""
    xs, ys, by = [], [], {}
    for e in ev:
        key = (e['sector'], e['season'])
        prior = by.setdefault(key, [])
        if len(prior) >= 3 and e.get('surprise') is not None:
            xs.append(np.mean([clip(p['surprise'], -0.5, 0.5) for p in prior]))
            ys.append(clip(e['surprise'], -0.5, 0.5))
        if e.get('surprise') is not None:
            prior.append(e)
    if len(xs) < 50:
        return None, len(xs), None
    x, y = np.array(xs), np.array(ys)
    beta = float((x @ y) / (x @ x)) if (x @ x) > 0 else None
    hit = float(np.mean(np.sign(beta * x) == np.sign(y))) if beta else None
    return beta, len(xs), hit


# ------------------------------------------------------------------ non-GAAP gap (Street EPS vs GAAP diluted EPS)
def collect_eps_frames(root, quarters=6, ua=None):
    """GAAP diluted EPS for every filer, one SEC frame per calendar quarter (cache/eps-frames/<CYyyyyQn>.json)."""
    ua = ua or os.environ.get('SEC_USER_AGENT', '')
    if '@' not in ua:
        raise SystemExit('Set SEC_USER_AGENT to the project name and a contact e-mail (SEC fair-access policy)')
    out = Path(root) / 'cache' / 'eps-frames'
    out.mkdir(parents=True, exist_ok=True)
    got, errors = 0, []
    periods = FR.calendar_quarters(quarters)
    recent = set(periods[-2:])
    for per in periods:
        p = out / f'{per}.json'
        if p.exists() and per not in recent:
            continue
        for attempt in range(3):
            try:
                req = urllib.request.Request(EPS_FRAMES.format(period=per), headers={'User-Agent': ua, 'Accept': 'application/json'})
                with urllib.request.urlopen(req, timeout=60) as r:
                    body = json.loads(r.read().decode('utf-8'))
                rows = {str(x['cik']): [x['val'], x.get('end')] for x in body.get('data', []) if x.get('val') is not None}
                p.write_text(json.dumps(rows, separators=(',', ':')), encoding='utf-8')
                got += 1
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    p.write_text('{}', encoding='utf-8')
                    break
                time.sleep(2 * (attempt + 1))
                if attempt == 2:
                    errors.append(f'{per}: HTTP {exc.code}')
            except Exception as exc:                      # noqa: BLE001 — a network hiccup must not lose the rest
                time.sleep(2 * (attempt + 1))
                if attempt == 2:
                    errors.append(f'{per}: {str(exc)[:80]}')
        time.sleep(0.2)
    st = {'eps_frames_at': now(), 'fetched': got, 'errors': errors, 'periods': periods}
    write_json(Path(root) / 'cache' / 'collect-status.json', st)
    print(f'eps frames: {got} fetched, {len(errors)} errors', flush=True)
    return st


def nongaap(cos, root):
    """Per company: Street EPS (the consensus actual, usually adjusted) against GAAP diluted EPS for the same quarter,
    the gap as a share of the Street figure, and whether the latest gap is much wider than the ones before."""
    frames = {}
    for p in sorted((Path(root) / 'cache' / 'eps-frames').glob('CY*.json')):
        frames[p.stem] = read_json(p, {}) or {}
    rows = []
    for t, rec in cos.items():
        cik = str(rec.get('cik') or '')
        pts = []
        for s in rec['surprises']:
            act = _f(s.get('eps_act'))
            g = (frames.get(season_of(s['quarter'])) or {}).get(cik)
            if act is None or not g or abs(act) < 0.05:
                continue
            gaap = _f(g[0])
            if gaap is None:
                continue
            pts.append({'quarter': s['quarter'][:10], 'street': act, 'gaap': gaap, 'gap': act - gaap, 'gap_pct': (act - gaap) / abs(act)})
        if len(pts) < 3:
            continue
        pts.sort(key=lambda x: x['quarter'])
        last, prev = pts[-1], pts[:-1]
        mean_prev = sum(x['gap_pct'] for x in prev) / len(prev)
        rows.append({'ticker': t, 'name': rec['name'], 'sector': rec['sector'], 'points': pts[-6:], 'gap_pct': last['gap_pct'], 'gap_prev_mean': mean_prev,
                     'widening': last['gap_pct'] - mean_prev, 'flag': bool(last['gap_pct'] >= 0.2 and last['gap_pct'] - mean_prev >= 0.15)})
    rows.sort(key=lambda r: -(r['widening'] or 0))
    return rows


# ------------------------------------------------------------------ our own estimates
def growth_from_frames(fig, cik, season, key):
    """Median year-over-year growth of the last two reported calendar quarters before a season (revenue or net income)."""
    per = fig.get(str(cik)) or {}
    out = []
    s = season
    for k in (1, 2):
        q = FR._shift(s, -k)
        a, b = (per.get(q) or {}).get(key), (per.get(FR._shift(q, -4)) or {}).get(key)
        if a is not None and b and b > 0:
            out.append(a / b - 1)
    return float(np.median(out)) if out else None


def our_estimates(rec, fig, peer_mean):
    """Seasonal baseline from the same quarter a year earlier, grown at the company's recent year-over-year rate (net income
    for EPS, revenue for revenue; SEC frames), nudged by half of the sector's surprise so far this season."""
    q0 = rec['q0']
    end = q0.get('end')
    if not end:
        return {}
    season = season_of(end)
    e, r = q0.get('eps') or {}, q0.get('rev') or {}
    out = {'method': 'same quarter last year × recent y/y growth (SEC frames) × half the sector surprise so far'}
    ya, yr = _f(e.get('yearAgoEps')), _f(r.get('yearAgoRevenue'))
    adj = 1 + 0.5 * (clip(peer_mean, -0.1, 0.1) or 0)
    if ya is not None:
        g = growth_from_frames(fig, rec.get('cik'), season, 'ni')
        base = ya * (1 + clip(g, -0.5, 1.0)) if (g is not None and ya > 0) else ya
        out['eps'] = base * adj if base > 0 else base
        out['eps_growth'] = g
    if yr:
        g = growth_from_frames(fig, rec.get('cik'), season, 'rev')
        out['rev'] = yr * (1 + (clip(g, -0.5, 1.5) or 0)) * (1 + 0.5 * (adj - 1))
        out['rev_growth'] = g
    return out


def revenue_actual(rec, fig, quarter):
    """The reported revenue of a quarter: Yahoo's quarterly chart (calendar labels like 3Q2026), else the SEC frame."""
    cy = season_of(quarter)
    label = f'{cy[-1]}Q{cy[2:6]}'
    for x in rec.get('revenue_history') or []:
        if x.get('date') == label and _f(x.get('revenue')):
            return _f(x['revenue'])
    v = ((fig.get(str(rec.get('cik'))) or {}).get(cy) or {}).get('rev')
    return _f(v)


# ------------------------------------------------------------------ build
def build(root, cons, hub, today=None, verbose=True):
    root, cons = Path(root), Path(cons)
    hub = Path(hub) if hub else None
    today = today or dt.date.today()
    T = today.isoformat()
    pub = root / 'public'
    (pub / 'c').mkdir(parents=True, exist_ok=True)
    book_path = root / 'cache' / 'book.json'
    book = FB.load(book_path)

    cos = load_consensus(cons)
    prices = Prices(hub)
    spy = prices.get('SPY')
    calib = {}
    for rec in cos.values():
        for c in rec['calib']:
            if c.get('report_date') and c.get('p_day_before') is not None:
                calib[(rec['ticker'], c['report_date'][:10])] = (float(c['p_day_before']), bool(c.get('yes')), c.get('eps_strike'))
    calib_p = {k: v[0] for k, v in calib.items()}
    cal = (read_json(cons / 'calendar.json', {}) or {}).get('rows') or []
    periods = FR.calendar_quarters(10, today)
    fig = FR.figures(hub, periods) if hub and (hub / 'cache' / 'frames').exists() else {}
    opt_dir = hub / 'market' / 'options' if hub else None
    options = {}
    if opt_dir and opt_dir.exists():
        for p in opt_dir.glob('*.json'):
            d = read_json(p, {})
            if d and d.get('ticker'):
                options[d['ticker'].upper()] = d
    si = {r['ticker'].upper(): r for r in ((read_json(hub / 'market' / 'short-interest.json', {}) or {}).get('rows') or []) if r.get('ticker')} if hub else {}
    ins = {}
    for r in ((read_json(hub / 'market' / 'insiders.json', {}) or {}).get('summary') or []) if hub else []:
        if r.get('ticker'):
            ins[r['ticker'].upper()] = (r.get('buy_value') or 0) - (r.get('sell_value') or 0)

    # ---- history, features, walk-forward model
    ev = attach_features(history(cos, prices, spy), cos, calib_p)
    by_t = {}
    for e in ev:
        prior = by_t.setdefault(e['ticker'], [])
        e['sue'] = sue(prior, e['est'], e['act'])
        prior.append(e)
    book_rows = []
    for k, e in FB.entries(book, 'beat', resolved=True):
        f = (e.get('meta') or {}).get('features')
        if f and (e.get('actual') or {}).get('y') is not None:
            book_rows.append((f, int(e['actual']['y']), e['asof']))
    seen = {k for k, e in FB.entries(book, 'beat', resolved=True) if (e.get('meta') or {}).get('features')}
    hist_rows = [e for e in ev if f"{e['ticker']}:{e['quarter']}" not in seen]     # a frozen report trains with its live inputs
    oos, monthly = walk_forward(hist_rows, book_rows)
    model = fit_beat([(e['f'], e['beat']) for e in hist_rows] + [(f, y) for f, y, _ in book_rows])
    pead = pead_walk_forward(ev)
    pead_w = FB.conformal_halfwidth(pead['residuals'], 0.8)
    beta, beta_n, beta_hit = readthrough_beta(ev)

    # ---- the current season (the calendar quarter most reports of the last ~75 days belong to)
    recent = [e for e in ev if e['reported'] >= (today - dt.timedelta(days=75)).isoformat()]
    counts = {}
    for e in recent:
        counts[e['season']] = counts.get(e['season'], 0) + 1
    cur_season = max(counts.items(), key=lambda kv: (kv[1] >= 20, kv[0]))[0] if counts else None
    upcoming_season = None
    sec_now = {}
    for e in ev:
        sec_now.setdefault((e['sector'], e['season']), []).append(e)

    # ---- live forecasts for upcoming reports, frozen near the report
    previews, frozen_new = {}, 0
    for rec in cos.values():
        nx = rec['next'] or {}
        d = (nx.get('date') or '')[:10]
        q0 = rec['q0']
        quarter = (q0.get('end') or '')[:10]
        if not d or not quarter or not (T <= d <= (today + dt.timedelta(days=PREVIEW_DAYS)).isoformat()):
            continue
        t = rec['ticker']
        season = season_of(quarter)
        upcoming_season = upcoming_season or season
        prior = by_t.get(t, [])
        srows = [r for r in sec_now.get((rec['sector'], season), []) if r['reported'] <= T]
        f = base_features(prior, srows)
        r30 = revision_30d(snap_series(rec, 'eps_q'), T, quarter)
        if r30 is None:
            tr = q0.get('eps_trend') or {}
            if _f(tr.get('current')) is not None and _f(tr.get('30daysAgo')):
                c0, c30 = _f(tr['current']), _f(tr['30daysAgo'])
                r30 = clip(c0 / c30 - 1, -0.3, 0.3) if c30 > 0 else clip((c0 - c30) / max(abs(c30), 0.05), -0.3, 0.3)
        if r30 is not None:
            f.update(revision_30d=r30, has_revision=1)
        bm = next((m for m in rec['beat'] if not m.get('closed') and (m.get('report_date') or '9999')[:10] >= T and m.get('p') is not None), None)
        if bm:
            f.update(polymarket_logit=logit(float(bm['p'])), has_polymarket=1)
        im = implied_move(options.get(t.upper()), d)
        if im:
            f.update(implied_move=im['move'], has_implied=1)
        if t.upper() in ins:
            f.update(insider_net=float(np.sign(ins[t.upper()])), has_insider=1)
        p = prob(model, f)
        peer = [clip(r['surprise'], -0.5, 0.5) for r in srows if r.get('surprise') is not None]
        peer_mean = float(np.mean(peer)) if len(peer) >= 3 else None
        ours = our_estimates(rec, fig, peer_mean)
        e_, r_ = q0.get('eps') or {}, q0.get('rev') or {}
        hist_moves = [abs(x['move']) for x in prior[-8:] if x.get('move') is not None]
        key = f'{t}:{quarter}'
        days_to = (day(d) - today).days
        if days_to <= FREEZE_DAYS:
            meta = {'reported': d, 'model': MODEL, 'features': {k: v for k, v in f.items() if k in FEATURES}}
            if p is not None and FB.freeze(book, 'beat', key, T, {'p': p, 'polymarket': float(bm['p']) if bm else None,
                                                                  'strike': bm.get('eps_strike') if bm else None, 'est': _f(e_.get('avg'))}, meta=meta):
                frozen_new += 1
            if ours.get('eps') is not None and _f(e_.get('avg')) is not None:
                FB.freeze(book, 'eps', key, T, {'ours': ours['eps'], 'analysts': _f(e_.get('avg')), 'low': _f(e_.get('low')), 'high': _f(e_.get('high'))},
                          meta={'reported': d})
            if ours.get('rev') and _f(r_.get('avg')):
                FB.freeze(book, 'rev', key, T, {'ours': ours['rev'], 'analysts': _f(r_.get('avg'))}, meta={'reported': d})
            if im:
                FB.freeze(book, 'move', key, T, {'implied': im['move'], 'avg_actual': float(np.mean(hist_moves)) if hist_moves else None,
                                                 'expiry': im['expiry']}, meta={'reported': d})
            if beta is not None and peer_mean is not None:
                FB.freeze(book, 'readthrough', key, T, {'pred': beta * peer_mean, 'peer_mean': peer_mean, 'n_peers': len(peer)}, meta={'reported': d})
        fr = FB.get(book, 'beat', key)
        disp = (( _f(e_.get('high')) - _f(e_.get('low'))) / abs(_f(e_.get('avg')))) if all(_f(e_.get(k)) is not None for k in ('high', 'low')) and _f(e_.get('avg')) else None
        rv = q0.get('revisions') or {}
        n_an = _f(e_.get('numberOfAnalysts'))
        breadth = ((rv.get('upLast30days') or 0) - (rv.get('downLast30days') or 0)) / n_an if n_an else None
        previews[t] = {
            'ticker': t, 'cik': rec['cik'], 'name': rec['name'], 'sector': rec['sector'], 'report_date': d, 'date_estimated': bool(nx.get('estimate')),
            'quarter': quarter, 'season': season, 'days_to': days_to,
            'consensus': {'eps': _f(e_.get('avg')), 'eps_low': _f(e_.get('low')), 'eps_high': _f(e_.get('high')), 'n': n_an, 'year_ago_eps': _f(e_.get('yearAgoEps')),
                          'rev': _f(r_.get('avg')), 'rev_low': _f(r_.get('low')), 'rev_high': _f(r_.get('high')), 'year_ago_rev': _f(r_.get('yearAgoRevenue')),
                          'revision_30d': r30, 'revision_breadth': breadth, 'dispersion': disp},
            'polymarket': ({'p': float(bm['p']), 'strike': bm.get('eps_strike'), 'basis': bm.get('basis'), 'url': bm.get('url'), 'volume': bm.get('volume')} if bm else None),
            'model': {'p': p, 'version': MODEL, 'inputs': {k: f.get(k) for k in FEATURES if f.get(k) is not None},
                      'frozen': bool(fr), 'frozen_at': fr and fr.get('frozen_at'), 'frozen_p': fr and fr['forecast'].get('p')},
            'ours': ours, 'implied': im, 'avg_move': float(np.mean(hist_moves)) if hist_moves else None, 'moves_n': len(hist_moves),
            'history': [{'quarter': x['quarter'], 'reported': x['reported'], 'est': x['est'], 'act': x['act'], 'surprise': x['surprise'], 'beat': x['beat'],
                         'move': x['move'], 'excess': x['excess']} for x in prior[-8:]],
            'beat_rate': (sum(x['beat'] for x in prior[-8:]) / len(prior[-8:])) if prior else None,
            'readthrough': {'peer_mean': peer_mean, 'n_peers': len(peer), 'beta': beta, 'pred': (beta * peer_mean) if (beta is not None and peer_mean is not None) else None},
        }

    # ---- resolve frozen forecasts from the actuals
    ev_key = {(e['ticker'], e['quarter']): e for e in ev}
    resolved_now = 0
    for fam in ('beat', 'eps', 'rev', 'move', 'readthrough'):
        for k, e in FB.entries(book, fam, resolved=False):
            t, q = k.split(':', 1)
            h = ev_key.get((t, q))
            if not h:
                continue
            if fam == 'beat':
                ok = FB.resolve(book, fam, k, {'y': h['beat'], 'act': h['act'], 'est': h['est'], 'surprise': h['surprise'], 'reported': h['reported']})
            elif fam == 'eps':
                ok = FB.resolve(book, fam, k, {'act': h['act']})
            elif fam == 'rev':
                ra = revenue_actual(cos.get(t, {'revenue_history': [], 'cik': None}), fig, q)
                ok = FB.resolve(book, fam, k, {'act': ra}) if ra else False
            elif fam == 'move':
                ok = FB.resolve(book, fam, k, {'move': h['move'], 'abs': abs(h['move'])}) if h.get('move') is not None else False
            else:
                ok = FB.resolve(book, fam, k, {'surprise': h['surprise']}) if h.get('surprise') is not None else False
            resolved_now += bool(ok)

    # ---- post-earnings drift: predicted for the reports of the last ten days, frozen once
    pead_rows = []
    coef = pead['coef']
    for e in ev:
        if coef is None or e['reported'] < (today - dt.timedelta(days=RECENT_DAYS + 4)).isoformat() or e.get('move') is None:
            continue
        pr = float(np.dot(coef, pead_x(e)))
        key = f"{e['ticker']}:{e['quarter']}"
        FB.freeze(book, 'pead', key, T, {'pred': pr}, interval=[pr - pead_w, pr + pead_w] if pead_w else None,
                  meta={'reported': e['reported'], 'sue': e['sue'], 'surprise': e['surprise'], 'reaction': e['excess']})
        fz = FB.get(book, 'pead', key)
        pead_rows.append({'ticker': e['ticker'], 'name': cos[e['ticker']]['name'], 'sector': e['sector'], 'reported': e['reported'],
                          'surprise': e['surprise'], 'sue': e['sue'], 'reaction': e['excess'], 'pred': fz['forecast']['pred'],
                          'low': (fz.get('interval') or [None, None])[0], 'high': (fz.get('interval') or [None, None])[1]})
    for k, e in FB.entries(book, 'pead', resolved=False):
        t, q = k.split(':', 1)
        h = ev_key.get((t, q))
        if h and h.get('drift') is not None:
            FB.resolve(book, 'pead', k, {'drift': h['drift']})
    pead_rows.sort(key=lambda r: -abs(r['pred'] or 0))

    # ---- scorecard: the last nine weeks of reports
    since = (today - dt.timedelta(days=63)).isoformat()
    sc_rows, weeks = [], {}
    for e in ev:
        if e['reported'] < since:
            continue
        key = f"{e['ticker']}:{e['quarter']}"
        fb_ = FB.get(book, 'beat', key)
        mv = FB.get(book, 'move', key)
        pm = calib.get((e['ticker'], e['reported']))
        pm_p = pm[0] if pm else ((fb_ or {}).get('forecast') or {}).get('polymarket')
        mp = ((fb_ or {}).get('forecast') or {}).get('p')
        src = 'frozen' if mp is not None else ('backtest' if oos.get((e['ticker'], e['reported'])) is not None else None)
        if mp is None:
            mp = oos.get((e['ticker'], e['reported']))
        row = {'ticker': e['ticker'], 'name': cos[e['ticker']]['name'], 'sector': e['sector'], 'reported': e['reported'], 'quarter': e['quarter'],
               'est': e['est'], 'act': e['act'], 'surprise': e['surprise'], 'beat': e['beat'], 'polymarket': pm_p,
               'polymarket_right': (None if pm_p is None else int((pm_p >= 0.5) == bool(e['beat']))), 'model': mp, 'model_source': src,
               'model_right': (None if mp is None else int((mp >= 0.5) == bool(e['beat']))),
               'implied': ((mv or {}).get('forecast') or {}).get('implied'), 'move': e['move'], 'excess': e['excess']}
        sc_rows.append(row)
        wk = (day(e['reported']) - dt.timedelta(days=day(e['reported']).weekday())).isoformat()
        w = weeks.setdefault(wk, {'week': wk, 'n': 0, 'beats': 0, 'pm_n': 0, 'pm_right': 0, 'model_n': 0, 'model_right': 0, 'frozen_n': 0, 'frozen_right': 0,
                                  'moves_n': 0, 'moves_inside': 0})
        w['n'] += 1
        w['beats'] += e['beat']
        if row['polymarket_right'] is not None:
            w['pm_n'] += 1
            w['pm_right'] += row['polymarket_right']
        if row['model_right'] is not None:
            w['model_n'] += 1
            w['model_right'] += row['model_right']
            if src == 'frozen':
                w['frozen_n'] += 1
                w['frozen_right'] += row['model_right']
        if row['implied'] is not None and row['move'] is not None:
            w['moves_n'] += 1
            w['moves_inside'] += int(abs(row['move']) <= row['implied'])
    sc_rows.sort(key=lambda r: (r['reported'], r['ticker']), reverse=True)
    pm_all = FB.score_prob([(v[0], v[1]) for v in calib.values()])
    frozen = FB.score_prob([(e['forecast']['p'], e['actual']['y']) for _, e in FB.entries(book, 'beat', resolved=True)])
    bt = FB.score_prob([(oos[(e['ticker'], e['reported'])], e['beat']) for e in hist_rows if oos.get((e['ticker'], e['reported'])) is not None])
    common = [(oos.get((e['ticker'], e['reported'])), e.get('pm'), e['beat']) for e in hist_rows
              if oos.get((e['ticker'], e['reported'])) is not None and e.get('pm') is not None]
    blend = [(1 / (1 + math.exp(-(logit(a) + logit(b)) / 2)), y) for a, b, y in common]
    eps_h2h = FB.head_to_head([(e['forecast']['ours'], e['forecast']['analysts'], e['actual']['act']) for _, e in FB.entries(book, 'eps', resolved=True)])
    rev_h2h = FB.head_to_head([(e['forecast']['ours'], e['forecast']['analysts'], e['actual']['act']) for _, e in FB.entries(book, 'rev', resolved=True)])
    mv_res = [(e['forecast']['implied'], e['actual']['abs']) for _, e in FB.entries(book, 'move', resolved=True) if e['forecast'].get('implied')]
    rt_res = [(e['forecast']['pred'], e['actual']['surprise']) for _, e in FB.entries(book, 'readthrough', resolved=True)]
    pead_res = [(e['forecast']['pred'], e['actual']['drift']) for _, e in FB.entries(book, 'pead', resolved=True)]
    scorecard = {
        'generated_at': now(), 'rows': sc_rows, 'weeks': sorted(weeks.values(), key=lambda w: w['week'], reverse=True),
        'polymarket': pm_all, 'model_frozen': frozen, 'model_backtest': bt, 'backtest_months': monthly,
        'common': {'n': len(common), 'model': FB.score_prob([(a, y) for a, _, y in common]), 'polymarket': FB.score_prob([(b, y) for _, b, y in common]),
                   'blend': FB.score_prob(blend)},
        'eps_vs_analysts': eps_h2h, 'rev_vs_analysts': rev_h2h,
        'moves': {'n': len(mv_res), 'inside': (sum(1 for a, b in mv_res if b <= a) / len(mv_res)) if mv_res else None,
                  'mean_ratio': (float(np.mean([b / a for a, b in mv_res if a])) if mv_res else None)},
        'readthrough': {'n': len(rt_res), 'sign_hit': (float(np.mean([np.sign(a) == np.sign(b) for a, b in rt_res if a])) if rt_res else None),
                        'beta': beta, 'beta_n': beta_n, 'beta_in_sample_hit': beta_hit},
        'pead': {'n_resolved': len(pead_res), 'ic_resolved': spearman([a for a, _ in pead_res], [b for _, b in pead_res]) if len(pead_res) >= 10 else None,
                 'ic_backtest': pead['ic'], 'n_backtest': pead['n_oos'], 'top_minus_bottom_backtest': pead['top_minus_bottom'],
                 'interval80': pead_w},
        'model': {'version': MODEL, 'inputs_used': (model or {}).get('used'), 'trained_on': (model or {}).get('n'),
                  'weights': dict(zip(['intercept'] + FEATURES, [float(x) for x in (model or {}).get('w', [])])) if model else None},
        'note': ('Polymarket: the price 24 hours before each beat market closed (the consensus branch keeps them). Our model: a logistic regression '
                 'fitted only on earlier reports — "frozen" rows were published before the report, "backtest" rows are the monthly walk-forward '
                 '(each month predicted by a model fitted on the months before). A call is right when the probability is on the side of 50% the '
                 'result fell on. History is what the consensus collector has gathered (about four quarters per company). Not investment advice.'),
    }

    # ---- season breadth and the calendar heatmap: the season under way (the quarter most companies report next), with
    # the one before for comparison
    ups = {}
    for rec in cos.values():
        if (rec['q0'].get('end') or '') and (rec['next'] or {}).get('date'):
            sq_ = season_of(rec['q0']['end'])
            ups[sq_] = ups.get(sq_, 0) + 1
    season = max(ups.items(), key=lambda kv: kv[1])[0] if ups else cur_season
    srows = [e for e in ev if e['season'] == season] if season else []
    prev_season = FR._shift(season, -1) if season else None
    prows = [e for e in ev if e['season'] == prev_season] if prev_season else []
    eps_y = {t: snap_series(rec, 'eps_y') for t, rec in cos.items()}
    rev_q = {t: snap_series(rec, 'rev_q') for t, rec in cos.items()}

    def post_revision(e):
        s = eps_y.get(e['ticker']) or []
        a = snap_on(s, (day(e['reported']) - dt.timedelta(days=1)).isoformat())
        b = snap_on(s, (day(e['reported']) + dt.timedelta(days=7)).isoformat())
        if not a or not b or b[0] <= e['reported'] or not a[1] or a[1] <= 0:
            return None
        x = b[1] / a[1] - 1
        return x if abs(x) <= 0.12 else None              # larger jumps are the fiscal year rolling over, not a revision

    def rev_beat(e):
        pre = snap_on(rev_q.get(e['ticker']) or [], (day(e['reported']) - dt.timedelta(days=1)).isoformat(), e['quarter'])
        if not pre or not pre[1]:
            return None
        ra = revenue_actual(cos[e['ticker']], fig, e['quarter'])
        return None if ra is None else int(ra > pre[1])

    def agg(rows):
        n = len(rows)
        sur = [clip(r['surprise'], -1, 1) for r in rows if r.get('surprise') is not None]
        rb = [x for x in (rev_beat(r) for r in rows) if x is not None]
        pr = [x for x in (post_revision(r) for r in rows) if x is not None]
        return {'n': n, 'beats': sum(r['beat'] for r in rows), 'beat_pct': (sum(r['beat'] for r in rows) / n) if n else None,
                'mean_surprise': float(np.mean(sur)) if sur else None, 'median_surprise': float(np.median(sur)) if sur else None,
                'rev_n': len(rb), 'rev_beat_pct': (sum(rb) / len(rb)) if rb else None,
                'est_raised': sum(1 for x in pr if x > 0.005), 'est_cut': sum(1 for x in pr if x < -0.005), 'est_n': len(pr),
                'mean_reaction': float(np.mean([r['excess'] for r in rows if r.get('excess') is not None])) if any(r.get('excess') is not None for r in rows) else None}
    sectors = {}
    for e in srows:
        sectors.setdefault(e['sector'], []).append(e)
    seasons_hist = {}
    for e in ev:
        seasons_hist.setdefault(e['season'], []).append(e)
    days_ = {}
    for e in srows:
        dd = days_.setdefault(e['reported'], {'date': e['reported'], 'n': 0, 'beats': 0, 'misses': 0, 'sur': [], 'upcoming': 0})
        dd['n'] += 1
        dd['beats' if e['beat'] else 'misses'] += 1
        if e.get('surprise') is not None:
            dd['sur'].append(clip(e['surprise'], -1, 1))
    for r in cal:
        dte = (r.get('date') or '')[:10]
        if T <= dte <= (today + dt.timedelta(days=21)).isoformat():
            dd = days_.setdefault(dte, {'date': dte, 'n': 0, 'beats': 0, 'misses': 0, 'sur': [], 'upcoming': 0})
            dd['upcoming'] += 1
    heat = [{**{k: v for k, v in x.items() if k != 'sur'}, 'mean_surprise': float(np.mean(x['sur'])) if x['sur'] else None}
            for x in sorted(days_.values(), key=lambda x: x['date'])]
    season_doc = {'generated_at': now(), 'season': season, 'upcoming_season': upcoming_season, 'overall': agg(srows),
                  'previous': {'season': prev_season, **agg(prows)},
                  'sectors': sorted([{'sector': s, **agg(rows)} for s, rows in sectors.items()], key=lambda r: -r['n']),
                  'history': [{'season': s, 'n': len(rows), 'beat_pct': sum(r['beat'] for r in rows) / len(rows)}
                              for s, rows in sorted(seasons_hist.items()) if len(rows) >= 50],
                  'calendar': heat,
                  'note': ('A report beats when the actual EPS (as the consensus source records it, usually adjusted) is above the average estimate. '
                           'Revenue beats count only reports whose revenue estimate was captured before the report (daily snapshots began Oct 2026). '
                           '"Estimates raised / cut" is the change of the current fiscal year EPS consensus from the day before the report to a week '
                           'after — a proxy for guidance, which is not parsed. Reaction: two-session move vs SPY.')}

    # ---- indicators: options, squeeze, non-GAAP gap, distributions
    opt_rows = []
    for t, o in options.items():
        px = prices.get(t)
        rv = realized_vol(px)
        iv = _f(o.get('iv30'))
        opt_rows.append({'ticker': t, 'iv30': iv / 100 if iv else None, 'rv30': rv, 'vrp': (iv / 100 - rv) if (iv and rv) else None,
                         'skew25': _f(o.get('skew25')), 'pc_oi': _f(o.get('pc_oi')), 'pc_vol': _f(o.get('pc_vol')), 'spot': _f(o.get('spot')),
                         'name': (cos.get(t) or {}).get('name'), 'as_of': o.get('as_of')})
    opt_rows.sort(key=lambda r: -(r['vrp'] if r['vrp'] is not None else -9))
    sq = []
    for t, r in si.items():
        rec = cos.get(t) or cos.get(t.replace('-', '.'))
        px = prices.get(t)
        if not rec or not rec.get('shares') or not px:
            continue
        price, short, dtc, adv = px[1][-1], _f(r.get('short')), _f(r.get('dtc')), _f(r.get('adv'))
        if not short or not dtc or price < 3 or (adv or 0) * price < 5e6:
            continue
        pct_ = short / rec['shares']
        mom = momentum(px)
        if pct_ < 0.05 or pct_ > 1.5 or mom is None:
            continue
        sq.append({'ticker': rec['ticker'], 'name': rec['name'], 'sector': rec['sector'], 'short_pct': pct_, 'dtc': dtc, 'momentum': mom,
                   'score': pct_ * dtc * max(0.5, 1 + mom), 'price': price,
                   'next_report': (rec['next'] or {}).get('date')})
    sq.sort(key=lambda r: -r['score'])
    ng = nongaap(cos, root)
    dists = []
    for t, rec in cos.items():
        o = options.get(t.upper())
        for m in rec['above'][:2]:
            st = m.get('stats') or {}
            end = (m.get('end') or '')[:10]
            if not o or not end or end < T:
                continue
            sm = None
            for s in o.get('smiles') or []:
                if s.get('exp') and s['exp'] >= end and (day(s['exp']) - day(end)).days <= 7:
                    sm = s
                    break
            if not sm:
                continue
            dist = rnd(sm.get('pts'), _f(o.get('spot')), max((day(sm['exp']) - day(str(o.get('as_of'))[:10])).days, 1))
            if not dist:
                continue
            ks = st.get('strikes') or []
            dists.append({'ticker': t, 'name': rec['name'], 'kind': 'price', 'title': m.get('title'), 'url': m.get('url'), 'end': end, 'expiry': sm['exp'],
                          'spot': _f(o.get('spot')), 'strikes': ks, 'polymarket_above': st.get('p_above'),
                          'options_above': [survival_at(dist, k) for k in ks],
                          'polymarket': {'median': (st.get('median') or {}).get('value'), 'q10': (st.get('q10') or {}).get('value'), 'q90': (st.get('q90') or {}).get('value')},
                          'options': {'median': dist['median'], 'q10': dist['q10'], 'q90': dist['q90']},
                          'density': [[float(g), float(v)] for g, v in zip(dist['grid'][::10], dist['density'][::10])]})
        for m in rec['eps_ladders'][:1]:
            st = m.get('stats') or {}
            dists.append({'ticker': t, 'name': rec['name'], 'kind': 'eps', 'title': m.get('title'), 'url': m.get('url'), 'end': (m.get('end') or '')[:10],
                          'strikes': st.get('strikes'), 'polymarket_above': st.get('p_above'), 'consensus': _f((rec['q0'].get('eps') or {}).get('avg')),
                          'polymarket': {'median': (st.get('median') or {}).get('value'), 'q10': (st.get('q10') or {}).get('value'), 'q90': (st.get('q90') or {}).get('value')}})
    for t, pv in previews.items():
        pv['options'] = next(({k: r[k] for k in ('vrp', 'iv30', 'rv30', 'skew25', 'pc_oi', 'pc_vol')} for r in opt_rows if r['ticker'] == t.upper()), None)
        pv['squeeze'] = next(({k: r[k] for k in ('short_pct', 'dtc', 'momentum', 'score')} for r in sq if r['ticker'] == t), None)
        pv['nongaap'] = next(({k: r[k] for k in ('gap_pct', 'gap_prev_mean', 'widening', 'flag', 'points')} for r in ng if r['ticker'] == t), None)
        pv['distributions'] = [x for x in dists if x['ticker'] == t]

    # ---- results of the last ten days on the preview pages
    for e in ev:
        if e['reported'] < (today - dt.timedelta(days=RECENT_DAYS)).isoformat():
            continue
        t = e['ticker']
        key = f"{t}:{e['quarter']}"
        pv = previews.get(t)
        if pv is None:
            rec = cos[t]
            pv = previews[t] = {'ticker': t, 'cik': rec['cik'], 'name': rec['name'], 'sector': rec['sector'], 'report_date': e['reported'], 'quarter': e['quarter'],
                                'season': e['season'], 'days_to': (day(e['reported']) - today).days,
                                'history': [{'quarter': x['quarter'], 'reported': x['reported'], 'est': x['est'], 'act': x['act'], 'surprise': x['surprise'],
                                             'beat': x['beat'], 'move': x['move'], 'excess': x['excess']} for x in by_t.get(t, [])[-8:]]}
        fb_, mv = FB.get(book, 'beat', key), FB.get(book, 'move', key)
        pz = FB.get(book, 'pead', key)
        pv.setdefault('results', []).append({'quarter': e['quarter'], 'reported': e['reported'], 'est': e['est'], 'act': e['act'], 'surprise': e['surprise'],
                                             'beat': e['beat'], 'move': e['move'], 'excess': e['excess'],
                                             'model_p': ((fb_ or {}).get('forecast') or {}).get('p'),
                                             'polymarket_p': (calib.get((t, e['reported'])) or [None])[0],
                                             'implied': ((mv or {}).get('forecast') or {}).get('implied'),
                                             'pead': (pz or {}).get('forecast', {}).get('pred') if pz else None,
                                             'pead_range': (pz or {}).get('interval') if pz else None})

    # ---- write public/
    for p in (pub / 'c').glob('*.json'):
        p.unlink()
    for t, pv in previews.items():
        write_json(pub / 'c' / f'{fname(t)}.json', {'generated_at': now(), **pv})
    idx_fields = ['ticker', 'name', 'sector', 'report_date', 'days_to', 'eps', 'n', 'polymarket', 'model', 'implied', 'avg_move', 'beat_rate', 'dispersion',
                  'revision_30d', 'surprise', 'move', 'ours_eps', 'frozen']
    idx = []
    for t, pv in sorted(previews.items(), key=lambda kv: (kv[1].get('report_date') or '', kv[0])):
        c_ = pv.get('consensus') or {}
        res = (pv.get('results') or [{}])[-1]
        idx.append([t, pv.get('name'), pv.get('sector'), pv.get('report_date'), pv.get('days_to'), c_.get('eps'), c_.get('n'),
                    (pv.get('polymarket') or {}).get('p'), (pv.get('model') or {}).get('p'), (pv.get('implied') or {}).get('move'), pv.get('avg_move'),
                    pv.get('beat_rate'), c_.get('dispersion'), c_.get('revision_30d'), res.get('surprise'), res.get('move'),
                    (pv.get('ours') or {}).get('eps'), bool((pv.get('model') or {}).get('frozen'))])
    write_json(pub / 'index.json', {'generated_at': now(), 'today': T, 'fields': idx_fields, 'rows': idx,
                                    'note': 'Reports in the next three weeks (previews) and the last ten days (results). Model: our beat probability; implied: '
                                            'the options-implied move; avg_move: the average absolute two-session move after the last eight reports.'})
    write_json(pub / 'scorecard.json', scorecard)
    write_json(pub / 'season.json', season_doc)
    write_json(pub / 'pead.json', {'generated_at': now(), 'rows': pead_rows[:300], 'interval80': pead_w, 'ic_backtest': pead['ic'],
                                   'coef': dict(zip(['intercept', 'sue', 'surprise', 'reaction'], [float(x) for x in coef])) if coef is not None else None,
                                   'n_train': pead['n'],
                                   'note': ('Predicted excess return over SPY for the 60 sessions after the report, from a linear model of past reports '
                                            '(standardised surprise, surprise, two-session reaction), fitted walk-forward; the range covers 80% of past '
                                            'out-of-sample errors (split conformal). Frozen the day it is first shown.')})
    write_json(pub / 'readthrough.json', {'generated_at': now(), 'beta': beta, 'beta_n': beta_n, 'season': upcoming_season,
                                          'rows': sorted([{'ticker': t, 'name': pv['name'], 'sector': pv['sector'], 'report_date': pv['report_date'], **(pv.get('readthrough') or {})}
                                                          for t, pv in previews.items() if (pv.get('readthrough') or {}).get('pred') is not None],
                                                         key=lambda r: -abs(r['pred']))[:200],
                                          'note': 'Peers are companies in the same sector that already reported this season (no supplier map). pred = beta × their mean surprise.'})
    write_json(pub / 'squeeze.json', {'generated_at': now(), 'rows': sq[:150], 'settlement_date': ((read_json(hub / 'market' / 'short-interest.json', {}) or {}).get('settlement_date') if hub else None),
                                      'note': ('Score = short interest as a share of shares outstanding (a proxy for the float) × days to cover × (1 + one-month '
                                               'return, floored at 0.5). FINRA short interest twice a month; price ≥ $3 and $5M a day traded. A ranking, not a prediction.')})
    write_json(pub / 'options.json', {'generated_at': now(), 'rows': opt_rows,
                                      'note': 'VRP = 30-day implied volatility − 30-day realised volatility (daily closes); skew25 and put/call ratios from the hub\'s CBOE snapshot.'})
    write_json(pub / 'nongaap.json', {'generated_at': now(), 'rows': ng[:400],
                                      'note': ('Street EPS (the actual the consensus source records, usually adjusted) vs GAAP diluted EPS from SEC XBRL frames for the '
                                               'same calendar quarter. Flag: the latest gap is at least 20% of Street EPS and 15 points wider than the average of the quarters before.')})
    write_json(pub / 'distributions.json', {'generated_at': now(), 'rows': dists,
                                            'note': (f'Options: risk-neutral distribution at the expiry on or just after the market\'s date (Breeden–Litzenberger on a quadratic '
                                                     f'smile fit, r = {RATE:.0%}); Polymarket: the ladder\'s prices of finishing above each strike. Risk-neutral is not real-world.')})
    FB.prune(book, 'pead', 6000)
    for fam in ('beat', 'eps', 'rev', 'move', 'readthrough'):
        FB.prune(book, fam, 20000)
    FB.save(book_path, book)
    status = {'built_at': now(), 'companies': len(cos), 'reports_history': len(ev), 'previews': len(previews), 'season': season,
              'frozen_new': frozen_new, 'resolved_now': resolved_now, 'book': {f: len(v) for f, v in book['families'].items()},
              'options': len(options), 'squeeze': len(sq), 'nongaap': len(ng), 'distributions': len(dists), 'model_trained_on': (model or {}).get('n')}
    write_json(pub / 'status.json', status)
    if verbose:
        print('earnings season: ' + json.dumps(status), flush=True)
    return status


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('collect')
    c.add_argument('--root', required=True)
    c.add_argument('--quarters', type=int, default=6)
    b = sub.add_parser('build')
    b.add_argument('--root', required=True)
    b.add_argument('--cons', required=True, help='public/ of the consensus-history branch')
    b.add_argument('--hub', default='', help='the hub data folder (cache/prices, cache/frames, market/…)')
    a = ap.parse_args()
    if a.cmd == 'collect':
        collect_eps_frames(a.root, a.quarters)
    else:
        build(a.root, a.cons, a.hub)


if __name__ == '__main__':
    main()
