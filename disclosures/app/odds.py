"""Odds: probability models, each checked against what happened (Disclosures → Odds, and Odds on every company page;
rotation-history.yml).

Market
  recession   the probability that the US is in recession 12 months from now, from the yield curve: the New York Fed's
              probit P = Φ(−0.5333 − 0.6330 × spread), spread = the month's average 10-year less 3-month Treasury yield
              (Estrella and Trubin 2006; coefficients estimated on 1959–2005, so every month since 2006 is out of sample).
              Scored against NBER recession months, 12 months after the forecast and another 12 for NBER's dating lag.
              With the Sahm rule (unemployment against its 12-month low; 0.5 points has marked every recession since 1970)
  regime      a two-state hidden Markov model of SPY's weekly returns (calm and stressed: each a normal distribution with
              its own mean and volatility, and the chance of switching), refitted each year on the years before it
              (Hamilton 1989); the probability of the stressed state now, and from the model the chance SPY is lower in
              13 weeks
Stocks (and SPY)
  touch       the chance the price (split-adjusted, on a weekly close) falls 10% within 4 weeks or 20% within 13, or rises
              as much: a random walk's first-passage probability 2·Φ(−b ÷ σ√h) from the stock's own 26-week volatility, the
              barrier moved half a step out for weekly closes (Broadie, Glasserman and Kou 1997), then recalibrated on past
              years (Platt scaling by year, walk-forward)
  beat SPY    the chance a stock's total return beats SPY's over 13 and 52 weeks: a logistic model of momentum against
              SPY, the distance from the 52-week high and volatility (each ranked within the week), refitted yearly
  S&P 500     the chance a company not in the S&P 500 is added within 12 months: a logistic model of its market value and
              its rank, positive earnings (the last four quarters and the latest one: the index's own rule), trading and
              momentum, on the index's dated additions (index_members.py) from 2011; refitted yearly
  dividend    the chance a dividend payer cuts or skips its dividend within 12 months: a logistic model of the dividend
  cut         yield, the payout ratio (dividends ÷ net income), losses, falling earnings, the past year's return and
              volatility; a cut = a regular payment under 85% of the regular one before it, or no payment by 1.5 times the
              usual interval plus 8 weeks; from 2011, refitted yearly
  default     Merton's distance to default (Debt & rates, app/debt_model.py): the 1-year probability N(−DD). It cannot be
              scored here — the companies on file are today's survivors, none of them defaulted
Every model's walk-forward record — each year predicted only from the years before it — gives its Brier score, its skill
against the base rate the past years implied, its AUC and a calibration table (predicted against observed). Each closed
week's odds are frozen in ledger/odds.json and scored as their outcomes arrive (the live record).

Survivorship: today's companies only (stocks that were delisted are missing; that lowers the observed drawdowns and
dividend cuts a little). History and models, not investment advice.

  python app/odds.py --public hist/public --root hist --members site/members.json --debt site/debt-index.json --ledger hist/ledger/odds.json
"""
import argparse
import datetime as dt
import json
import math
import re
import warnings
from pathlib import Path

import numpy as np

import strategies as ST
from strategies import WEEK, fin

# NBER business cycle peaks and troughs: recession months are those after a peak through the trough
NBER = [('1960-04', '1961-02'), ('1969-12', '1970-11'), ('1973-11', '1975-03'), ('1980-01', '1980-07'), ('1981-07', '1982-11'),
        ('1990-07', '1991-03'), ('2001-03', '2001-11'), ('2007-12', '2009-06'), ('2020-02', '2020-04')]
NBER_LAG_MONTHS = 12                         # NBER dates a recession months after it starts
NYFED = (-0.5333, -0.6330)
TOUCH = [('dn10_4', -0.10, 4), ('up10_4', 0.10, 4), ('dn20_13', -0.20, 13), ('up20_13', 0.20, 13)]
BEAT = [('beat13', 13), ('beat52', 52)]
MIN_DD = -0.5                                # a distance to default below this contradicts a positive share price: inputs off
FIRST_YEAR = 2000                            # walk-forward predictions from here (stock models: 1996 data on)


def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


NCDF = np.vectorize(norm_cdf, otypes=[float])


def _ym(s):
    return int(s[:4]) * 12 + int(s[5:7]) - 1


def recession_months():
    out = set()
    for pk, tr in NBER:
        for m in range(_ym(pk) + 1, _ym(tr) + 1):
            out.add(m)
    return out


# ------------------------------------------------------------------ fitting and scoring
def logit_fit(X, y, lam=1.0, iters=30, w=None):
    """L2-penalized logistic regression by Newton steps on standardized columns. → (mean, sd, beta)."""
    X = np.asarray(X, dtype=float)
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1
    Z = np.hstack([np.ones((len(X), 1)), (X - mu) / sd])
    b = np.zeros(Z.shape[1])
    p0 = min(max(y.mean(), 1e-4), 1 - 1e-4)
    b[0] = math.log(p0 / (1 - p0))
    pen = np.full(Z.shape[1], lam)
    pen[0] = 0
    w = np.ones(len(y)) if w is None else w
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(Z @ b, -30, 30)))
        g = Z.T @ (w * (p - y)) + pen * b
        H = (Z * (w * p * (1 - p))[:, None]).T @ Z + np.diag(pen + 1e-9)
        step = np.linalg.solve(H, g)
        b -= step
        if np.abs(step).max() < 1e-7:
            break
    return mu, sd, b


def logit_predict(m, X):
    mu, sd, b = m
    Z = (np.asarray(X, dtype=float) - mu) / sd
    return 1 / (1 + np.exp(-np.clip(b[0] + Z @ b[1:], -30, 30)))


def auc(p, y):
    p, y = np.asarray(p), np.asarray(y)
    pos, neg = y == 1, y == 0
    if not pos.any() or not neg.any():
        return None
    o = np.argsort(p)
    r = np.empty(len(p))
    r[o] = np.arange(1, len(p) + 1)
    # ties: average ranks
    _, inv, cnt = np.unique(p, return_inverse=True, return_counts=True)
    sums = np.bincount(inv, weights=r)
    r = (sums / cnt)[inv]
    return float((r[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * neg.sum()))


def card(p, y, clim=None, nb=10, quantile=False):
    """Walk-forward record: n, base rate, Brier, its skill against the base rate known beforehand (clim, per sample),
    AUC, and the calibration table [[mean predicted, observed, n]]."""
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
    ok = np.isfinite(p) & np.isfinite(y)
    p, y = p[ok], y[ok]
    if len(p) < 30:
        return None
    br = float(np.mean((p - y) ** 2))
    c = np.full(len(p), y.mean()) if clim is None else np.asarray(clim, dtype=float)[ok]
    bc = float(np.mean((c - y) ** 2))
    if quantile:
        edges = np.unique(np.quantile(p, np.linspace(0, 1, nb + 1)))
    else:
        edges = np.linspace(0, 1, nb + 1)
    k = np.clip(np.searchsorted(edges, p, side='right') - 1, 0, len(edges) - 2)
    tab = [[round(float(p[k == j].mean()), 4), round(float(y[k == j].mean()), 4), int((k == j).sum())] for j in range(len(edges) - 1) if (k == j).sum()]
    return {'n': int(len(p)), 'base': round(float(y.mean()), 4), 'brier': round(br, 5), 'brier_base': round(bc, 5),
            'skill': round(1 - br / bc, 4) if bc > 0 else None, 'auc': None if auc(p, y) is None else round(auc(p, y), 4), 'calib': tab}


def walk_forward(years, X, y, known_year, first_year, lam=1.0, platt=False, min_pos=0):
    """Fit on the samples whose outcome was known before each year, predict that year. years: the sample's year;
    known_year: the year its outcome became known. → (p, clim) arrays (NaN before first_year or without training)."""
    p = np.full(len(y), np.nan)
    clim = np.full(len(y), np.nan)
    for Y in range(first_year, int(years.max()) + 1):
        tr = (known_year < Y) & np.isfinite(y)
        te = years == Y
        if tr.sum() < 200 or not te.any() or y[tr].min() == y[tr].max() or y[tr].sum() < min_pos:
            continue
        m = logit_fit(X[tr], y[tr], lam)
        p[te] = logit_predict(m, X[te])
        clim[te] = y[tr].mean()
    return p, clim


def recalibrate(years, p, y, known_year, first_year):
    """A second, Platt step on the walk-forward odds themselves: each year's odds set right by a logistic fit of the
    past years' odds against what happened (rare events are where a first fit is most often overconfident)."""
    z = np.log(np.clip(p, 1e-5, 1 - 1e-5) / (1 - np.clip(p, 1e-5, 1 - 1e-5)))[:, None]
    out = np.full(len(p), np.nan)
    for Y in range(first_year, int(years.max()) + 1):
        tr = (known_year < Y) & np.isfinite(y) & np.isfinite(p)
        te = (years == Y) & np.isfinite(p)
        if tr.sum() < 200 or not te.any() or y[tr].sum() < 20:
            continue
        m = logit_fit(z[tr], y[tr], 0.0)
        out[te] = logit_predict(m, z[te])
    ok = np.isfinite(y) & np.isfinite(p)
    last = logit_fit(z[ok], y[ok], 0.0) if ok.sum() >= 200 and y[ok].sum() >= 20 else None
    return out, last


# ------------------------------------------------------------------ market: recession
def monthly_spread(root, public):
    """{month index: the month's average 10-year less 3-month yield} from the raw FRED cache (root/cache/macro), else the
    month-end values in macro.json."""
    out = {}
    try:
        import macro_history as MH
        raw = MH.load_cache(root) if root else {}
        acc = {}
        for d, v in raw.get('T10Y3M', []):
            if fin(v):
                acc.setdefault(d.year * 12 + d.month - 1, []).append(v)
        out = {k: sum(v) / len(v) for k, v in acc.items()}
    except Exception:
        out = {}
    if not out:
        try:
            m = json.loads((Path(public) / 'macro.json').read_text())
            for k, v in zip(m['monthly']['months'], m['monthly']['data'].get('curve') or []):
                if fin(v):
                    out[_ym(k)] = v
        except (OSError, ValueError, KeyError):
            pass
    return out


def recession(root, public, today):
    sp = monthly_spread(root, public)
    if not sp:
        return None
    rec = recession_months()
    now = today.year * 12 + today.month - 1
    last_known = now - NBER_LAG_MONTHS                       # recession months known up to here
    hist, ps, ys, ms = [], [], [], []
    for m in sorted(sp):
        p = norm_cdf(NYFED[0] + NYFED[1] * sp[m])
        hist.append([f'{m // 12}-{m % 12 + 1:02d}', round(p, 4), round(sp[m], 3)])
        if m + 12 <= last_known and m >= _ym('1990-01'):
            ps.append(p); ys.append(1.0 if m + 12 in rec else 0.0); ms.append(m)
    m_last = max(sp)
    sahm = None
    try:
        mj = json.loads((Path(public) / 'macro.json').read_text())
        s_ = [v for v in mj['monthly']['data'].get('sahm') or [] if fin(v)]
        sahm = round(s_[-1], 2) if s_ else None
    except (OSError, ValueError, KeyError):
        pass
    ys_a, ps_a = np.array(ys), np.array(ps)
    after = np.array(ms) >= _ym('2006-01')                  # after the coefficients were estimated
    return {'p': round(norm_cdf(NYFED[0] + NYFED[1] * sp[m_last]), 4), 'month': f'{m_last // 12}-{m_last % 12 + 1:02d}',
            'for_month': f'{(m_last + 12) // 12}-{(m_last + 12) % 12 + 1:02d}', 'spread': round(sp[m_last], 3), 'sahm': sahm,
            'coef': NYFED, 'history': hist, 'card': card(ps_a, ys_a), 'card_oos': card(ps_a[after], ys_a[after]) if after.any() else None,
            'scored_to': f'{(last_known - 12) // 12}-{(last_known - 12) % 12 + 1:02d}'}


# ------------------------------------------------------------------ market: regime (HMM)
def hmm_fit(x, iters=150, seed_split=0.5):
    """Two-state Gaussian hidden Markov model by EM. → (pi, A, mu, sd) with state 1 the higher-volatility one."""
    x = np.asarray(x, dtype=float)
    q = np.quantile(np.abs(x - x.mean()), seed_split)
    mu = np.array([x[np.abs(x - x.mean()) <= q].mean(), x[np.abs(x - x.mean()) > q].mean()])
    sd = np.array([x[np.abs(x - x.mean()) <= q].std() + 1e-4, x[np.abs(x - x.mean()) > q].std() + 1e-4])
    A = np.array([[0.97, 0.03], [0.08, 0.92]])
    pi = np.array([0.8, 0.2])
    T = len(x)
    for _ in range(iters):
        B = np.exp(-0.5 * ((x[:, None] - mu) / sd) ** 2) / (sd * math.sqrt(2 * math.pi)) + 1e-300
        a = np.zeros((T, 2)); c = np.zeros(T)
        a[0] = pi * B[0]; c[0] = a[0].sum(); a[0] /= c[0]
        for t in range(1, T):
            a[t] = (a[t - 1] @ A) * B[t]; c[t] = a[t].sum(); a[t] /= c[t]
        b = np.ones((T, 2))
        for t in range(T - 2, -1, -1):
            b[t] = (A @ (B[t + 1] * b[t + 1])) / c[t + 1]
        g = a * b
        g /= g.sum(1, keepdims=True)
        xi = np.zeros((2, 2))
        for t in range(T - 1):
            m = (a[t][:, None] * A) * (B[t + 1] * b[t + 1])[None, :] / c[t + 1]
            xi += m
        pi = g[0]
        A = xi / xi.sum(1, keepdims=True)
        mu = (g * x[:, None]).sum(0) / g.sum(0)
        sd = np.sqrt((g * (x[:, None] - mu) ** 2).sum(0) / g.sum(0)) + 1e-5
    if sd[0] > sd[1]:
        mu, sd, pi, A = mu[::-1], sd[::-1], pi[::-1], A[::-1, ::-1]
    return pi, A, mu, sd


def hmm_filter(x, P):
    pi, A, mu, sd = P
    a = pi.copy()
    out = np.zeros((len(x), 2))
    for t, v in enumerate(x):
        if t:
            a = a @ A
        if np.isfinite(v):
            a = a * np.exp(-0.5 * ((v - mu) / sd) ** 2) / sd
            a /= a.sum()
        out[t] = a
    return out


def hmm_down(prob, P, h=13):
    """P(the sum of the next h weekly log returns < 0) from the state probabilities now (a normal approximation of the
    mixture, step by step)."""
    _, A, mu, sd = P
    m = v = 0.0
    s = prob.copy()
    for _ in range(h):
        s = s @ A
        e = float(s @ mu)
        m += e
        v += float(s @ (sd ** 2 + mu ** 2)) - e ** 2
    return norm_cdf(-m / math.sqrt(v)) if v > 0 else 0.5


def regime(D, today_t):
    i = D['ix'].get('SPY')
    if i is None:
        return None
    C = D['C'][i]
    lr = np.full(len(C), np.nan)
    lr[1:] = np.log(C[1:] / C[:-1])
    dates = D['dates']
    years = np.array([int(str(d)[:4]) for d in dates])
    first = int(np.where(np.isfinite(lr))[0][0])
    ps, pd_, P_last = np.full(len(C), np.nan), np.full(len(C), np.nan), None
    for Y in range(FIRST_YEAR, int(years[today_t]) + 1):
        tr = np.where((years < Y) & np.isfinite(lr))[0]
        if len(tr) < 200:
            continue
        P = hmm_fit(lr[tr])
        f = hmm_filter(lr[first:today_t + 1], P)
        idx = np.where(years[first:today_t + 1] == Y)[0]
        for k in idx:
            ps[first + k] = f[k, 1]
            pd_[first + k] = hmm_down(f[k], P)
        P_last = P
    # scored: 13-week SPY return below zero, and the stressed state against next 13 weeks' volatility being high
    y = np.full(len(C), np.nan)
    for t in range(len(C) - 13):
        if t + 13 <= today_t and np.isfinite(C[t]) and np.isfinite(C[t + 13]):
            y[t] = 1.0 if C[t + 13] < C[t] else 0.0
    ok = np.isfinite(pd_) & np.isfinite(y)
    yrs_ok = years[ok]
    clim = np.array([np.nanmean(y[(years < yy) & np.isfinite(y)]) for yy in yrs_ok]) if ok.any() else None
    _, A, mu, sd = P_last
    return {'p_stress': round(float(ps[today_t]), 4), 'p_down13': round(float(pd_[today_t]), 4), 'week': str(dates[today_t]),
            'states': {'calm': {'mean_a_year': round(float(mu[0] * 52), 4), 'vol_a_year': round(float(sd[0] * math.sqrt(52)), 4), 'stay': round(float(A[0, 0]), 4)},
                       'stressed': {'mean_a_year': round(float(mu[1] * 52), 4), 'vol_a_year': round(float(sd[1] * math.sqrt(52)), 4), 'stay': round(float(A[1, 1]), 4)}},
            'history': [[str(dates[t]), round(float(ps[t]), 3), round(float(pd_[t]), 3)] for t in range(len(C)) if np.isfinite(ps[t]) and t <= today_t],
            'card': card(pd_[ok], y[ok], clim)}


# ------------------------------------------------------------------ stocks: samples
def month_ends(D, start_year=1996):
    t0 = int(np.searchsorted(D['dates'], np.datetime64(f'{start_year}-01-01')))
    return [t for t in range(max(t0, 52), D['t_end'] + 1) if D['month_end'][t]] + ([D['t_end']] if not D['month_end'][D['t_end']] else [])


def _vol(D, t, L=26):
    r = np.log1p(D['R'][:, t - L + 1:t + 1])
    n = np.isfinite(r).sum(1)
    with np.errstate(invalid='ignore'):
        v = np.nanstd(r, axis=1)
    return np.where(n >= L * 0.75, np.maximum(v, 0.005), np.nan)


def touch_p0(sw, h, x):
    """First-passage odds of a zero-drift random walk with weekly log volatility sw, h weeks, barrier x (±fraction),
    on weekly closes (the barrier half a step further out)."""
    b = abs(math.log(1 + x)) + 0.5826 * sw
    return np.minimum(1.0, 2 * NCDF(-b / (sw * math.sqrt(h))))


def _rank(x):
    """Each column ranked within the sample week to [-1, 1] (NaN stays NaN)."""
    out = np.full(len(x), np.nan)
    ok = np.isfinite(x)
    if ok.sum() > 1:
        r = np.argsort(np.argsort(x[ok]))
        out[ok] = 2 * r / (ok.sum() - 1) - 1
    return out


def stock_panel(D, members=None):
    """Monthly samples of every stock in the universe: features and outcomes for each stock model."""
    C, PS = D['C'], D.get('PS', D['C'])
    S = D.get('sec') or {}
    spy = D['ix'].get('SPY')
    out = {'t': [], 'i': [], 'sw': [], 'y': {}, 'known': {}, 'X': {}}
    for k, _, _ in TOUCH:
        out['y'][k] = []
    for k, _ in BEAT:
        out['y'][k] = []
    Xb = []
    T_end = D['t_end']
    for t in month_ends(D):
        u = ST.universe(D, t)
        idx = np.where(u)[0]
        if len(idx) < 30:
            continue
        sw = _vol(D, t)[idx]
        ok = np.isfinite(sw)
        idx, sw = idx[ok], sw[ok]
        out['t'].append(np.full(len(idx), t)); out['i'].append(idx); out['sw'].append(sw)
        for k, x, h in TOUCH:
            y = np.full(len(idx), np.nan)
            if t + h <= T_end:
                win = PS[idx, t + 1:t + h + 1]
                base = PS[idx, t]
                with np.errstate(invalid='ignore'):
                    hit = (np.nanmin(win, 1) <= base * (1 + x)) if x < 0 else (np.nanmax(win, 1) >= base * (1 + x))
                y = np.where(np.isfinite(base), hit.astype(float), np.nan)
            out['y'][k].append(y)
        # beat SPY: features ranked within the week
        with np.errstate(invalid='ignore', divide='ignore'):
            m121 = C[idx, t - 4] / C[idx, t - 52] - (C[spy, t - 4] / C[spy, t - 52] if spy is not None else 1)
            m13 = C[idx, t] / C[idx, t - 13] - (C[spy, t] / C[spy, t - 13] if spy is not None else 1)
            hi = C[idx, t] / np.nanmax(C[idx, t - 51:t + 1], axis=1)
        Xb.append(np.column_stack([_rank(m121), _rank(m13), _rank(hi), _rank(sw)]))
        for k, h in BEAT:
            y = np.full(len(idx), np.nan)
            if t + h <= T_end and spy is not None:
                with np.errstate(invalid='ignore', divide='ignore'):
                    y = (C[idx, t + h] / C[idx, t] > C[spy, t + h] / C[spy, t]).astype(float)
                y[~np.isfinite(C[idx, t + h])] = np.nan
            out['y'][k].append(y)
    out['t'] = np.concatenate(out['t']); out['i'] = np.concatenate(out['i']); out['sw'] = np.concatenate(out['sw'])
    for k in out['y']:
        out['y'][k] = np.concatenate(out['y'][k])
    out['X']['beat'] = np.nan_to_num(np.vstack(Xb), nan=0.0)
    out['year'] = np.array([int(str(D['dates'][t])[:4]) for t in out['t']])
    return out


def known_year(D, t, h):
    """The year in which an outcome h weeks after week t was known."""
    k = np.minimum(t + h, len(D['dates']) - 1)
    return np.array([int(str(D['dates'][x])[:4]) for x in k])


def touch_models(D, P):
    """Platt-recalibrated first-passage odds, walk-forward. → {model: {'p': oos array, 'card', 'fit': (a, b) latest}}."""
    out = {}
    for k, x, h in TOUCH:
        p0 = touch_p0(P['sw'], h, x)
        z = np.log(np.clip(p0, 1e-4, 1 - 1e-4) / (1 - np.clip(p0, 1e-4, 1 - 1e-4)))[:, None]
        y = P['y'][k]
        ky = known_year(D, P['t'], h)
        p, clim = walk_forward(P['year'], z, y, ky, FIRST_YEAR, lam=0.0)
        ok = np.isfinite(y)
        m = logit_fit(z[ok], y[ok], 0.0)
        out[k] = {'x': x, 'h': h, 'p': p, 'card': card(p, y, clim), 'card_raw': card(p0[np.isfinite(p)], y[np.isfinite(p)]), 'm': m}
    return out


def beat_models(D, P):
    out = {}
    X = P['X']['beat']
    for k, h in BEAT:
        y = P['y'][k]
        p, clim = walk_forward(P['year'], X, y, known_year(D, P['t'], h), FIRST_YEAR, lam=10.0)
        ok = np.isfinite(y)
        out[k] = {'h': h, 'p': p, 'card': card(p, y, clim), 'm': logit_fit(X[ok], y[ok], 10.0),
                  'features': ['momentum 12-1 against SPY', 'return 13 weeks against SPY', 'close ÷ 52-week high', '26-week volatility']}
    return out


# ------------------------------------------------------------------ S&P 500 additions
def sp500_intervals(members):
    """{ticker: [(joined, left)]} for the S&P 500. A day on which ten or more members "left" together within four months
    of the file's build is a change in the source (holdings the builder could not map), not removals: kept as members."""
    rows = (members or {}).get('rows', {})
    ends = {}
    for r in rows.values():
        for a, b in (r.get('was') or {}).get('sp500') or []:
            if b:
                ends[b] = ends.get(b, 0) + 1
    built = str((members or {}).get('generated_at', ''))[:10]
    mass = {b for b, n in ends.items() if n >= 10 and built and 0 <= (np.datetime64(built) - np.datetime64(b)).astype(int) <= 120}
    out = {}
    for t, r in rows.items():
        iv = (r.get('was') or {}).get('sp500') or []
        out[t] = [(np.datetime64(a) if a else None, np.datetime64(b) if b and b not in mass else None) for a, b in iv]
    return out


def mass_removals(members):
    rows = (members or {}).get('rows', {})
    ends = {}
    for t, r in rows.items():
        for a, b in (r.get('was') or {}).get('sp500') or []:
            if b:
                ends.setdefault(b, []).append(t)
    built = str((members or {}).get('generated_at', ''))[:10]
    return {b: sorted(v) for b, v in ends.items() if len(v) >= 10 and built and 0 <= (np.datetime64(built) - np.datetime64(b)).astype(int) <= 120}


def _member(iv, d):
    return any((a is None or a <= d) and (b is None or d < b) for a, b in iv)


def foreign_issuers(site_index):
    """Companies the S&P 500 does not take: foreign private issuers (latest report a 20-F, 40-F or 6-K) and partnerships
    (master limited partnerships: "L.P.", "LP", "Partners")."""
    out = set()
    for c in (site_index or {}).get('companies') or []:
        if not c.get('ticker'):
            continue
        if str(c.get('form') or '').split('/')[0] in ('20-F', '40-F', '6-K') or re.search(r'(?i)\b(L\.?P\.?|Partners)\s*$', str(c.get('name') or '').strip()):
            out.add(c['ticker'])
    return out


def sp500_panel(D, members, start_year=2010, foreign=()):
    S = D.get('sec') or {}
    if not members or 'cap' not in S or 'q-ni' not in S:
        return None
    ivs = sp500_intervals(members)
    built = np.datetime64(str(members.get('generated_at', ''))[:10] or str(D['dates'][D['t_end']]))
    ttm = ST._ttm(S['q-ni'], S['kq'])
    rows, X, y, tt = [], [], [], []
    t0 = int(np.searchsorted(D['dates'], np.datetime64(f'{start_year}-01-01')))
    for t in [x for x in month_ends(D, start_year) if x >= t0]:
        d = D['dates'][t]
        u = ST.universe(D, t)
        cap = S['cap'][:, t]
        okc = u & np.isfinite(cap) & (cap > 0)
        idx = np.where(okc)[0]
        if len(idx) < 100:
            continue
        rank = np.empty(len(idx))
        rank[np.argsort(-cap[idx])] = np.arange(len(idx))
        k = int(S['kq'][t])
        ni = ttm.get(k)
        lastq = S['q-ni'][:, k] if k >= 0 else np.full(len(cap), np.nan)
        for j, i in enumerate(idx):
            tk = D['tickers'][i]
            iv = ivs.get(tk, [])
            if tk in foreign or _member(iv, d):
                continue
            n4 = ni[i] if ni is not None else np.nan
            with np.errstate(invalid='ignore', divide='ignore'):
                r52 = D['C'][i, t] / D['C'][i, t - 52] - 1
            X.append([math.log(cap[i]), math.log1p(rank[j]), 1.0 if fin(n4) and n4 > 0 else 0.0, 1.0 if fin(lastq[i]) and lastq[i] > 0 else 0.0,
                      math.log(max(D['DV'][i, t], 1.0)), max(-0.9, min(3.0, r52)) if fin(r52) else 0.0])
            end = d + 52 * WEEK
            add = any(a is not None and d < a <= end for a, _ in iv)
            y.append(1.0 if add else (0.0 if end <= built else np.nan))
            tt.append(t); rows.append(i)
    if not X:
        return None
    return {'X': np.array(X), 'y': np.array(y), 't': np.array(tt), 'i': np.array(rows),
            'year': np.array([int(str(D['dates'][t])[:4]) for t in tt]),
            'features': ['log market value', 'log rank by market value', 'net income, last 4 quarters > 0', 'net income, latest quarter > 0',
                         'log weekly dollar volume', 'return over 52 weeks']}


def sp500_model(D, SP):
    if SP is None:
        return None
    ky = known_year(D, SP['t'], 52)
    p1, clim = walk_forward(SP['year'], SP['X'], SP['y'], ky, 2013, lam=1.0, min_pos=30)
    p, cal = recalibrate(SP['year'], p1, SP['y'], ky, 2015)
    clim[~np.isfinite(p)] = np.nan
    ok = np.isfinite(SP['y'])
    return {'p': p, 'card': card(p, SP['y'], clim, quantile=True), 'm': logit_fit(SP['X'][ok], SP['y'][ok], 1.0), 'cal': cal, 'features': SP['features']}


# ------------------------------------------------------------------ dividend cuts
def dividend_events(div, alive):
    """Regular payments and cut weeks of one stock: div (T,) amounts by week, alive (T,) has a close.
    → (payments [(week, amount)], cuts [week], typical interval)."""
    pay = [(int(w), float(div[w])) for w in np.where(div > 0)[0]]
    cuts = []
    for k in range(2, len(pay)):
        prev = [a for _, a in pay[max(0, k - 4):k]]
        med = float(np.median(prev))
        reg = [a for a in prev if a <= 1.5 * med]
        if not reg:
            continue
        if pay[k][1] < 0.85 * reg[-1] and pay[k][1] <= 1.5 * med:
            cuts.append(pay[k][0])
    gaps = np.diff([w for w, _ in pay])
    for k in range(1, len(pay) + 1):
        if k < 3:
            continue
        g = float(np.median(gaps[max(0, k - 5):k - 1])) if k - 1 > 0 else 13.0
        limit = int(max(1.5 * g, g + 8))
        last = pay[k - 1][0]
        nxt = pay[k][0] if k < len(pay) else None
        due = last + limit
        if (nxt is None or nxt > due) and due < len(div) and alive[min(due, len(alive) - 1)]:
            cuts.append(due)                                 # skipped: no payment by 1.5 × the usual interval + 8 weeks
    return pay, sorted(set(cuts))


def divcut_panel(D, start_year=2011):
    if 'DIV' not in D:
        return None
    S = D.get('sec') or {}
    ttm = ST._ttm(S['q-ni'], S['kq']) if 'q-ni' in S else {}
    N = len(D['tickers'])
    ev = {}
    for i in range(N):
        if D['is_etf'][i]:
            continue
        div = D['DIV'][i]
        if (div > 0).sum() >= 3:
            ev[i] = dividend_events(div, np.isfinite(D['C'][i]))
    X, y, tt, rows = [], [], [], []
    T_end = D['t_end']
    t0 = int(np.searchsorted(D['dates'], np.datetime64(f'{start_year}-01-01')))
    for t in [x for x in month_ends(D, start_year) if x >= t0]:
        u = ST.universe(D, t)
        k = int(S['kq'][t]) if 'kq' in S else -1
        ni, ni0 = ttm.get(k), ttm.get(k - 4)
        sw = _vol(D, t, 52)
        for i, (pay, cuts) in ev.items():
            if not u[i]:
                continue
            past = [(w, a) for w, a in pay if t - 60 < w <= t]
            if len(past) < 2:
                continue
            gaps = np.diff([w for w, _ in pay if w <= t][-5:])
            g = float(np.median(gaps)) if len(gaps) else 13.0
            if t - past[-1][0] > max(1.5 * g, g + 8):
                continue                                     # not paying now
            ttm_div = float(D['DIV'][i, t - 51:t + 1].sum())
            ps = D['PS'][i, t]
            if not (fin(ps) and ps > 0):
                continue
            yld = ttm_div / ps
            cap = S['cap'][i, t] if 'cap' in S else np.nan
            n4 = ni[i] if ni is not None else np.nan
            n40 = ni0[i] if ni0 is not None else np.nan
            payout = yld * cap / n4 if fin(cap) and fin(n4) and n4 > 0 else np.nan
            with np.errstate(invalid='ignore', divide='ignore'):
                r52 = D['C'][i, t] / D['C'][i, t - 52] - 1
            X.append([min(yld, 0.3), min(payout, 3.0) if fin(payout) else 1.5, 1.0 if fin(n4) and n4 <= 0 else 0.0,
                      1.0 if fin(n4) and fin(n40) and n4 < n40 else 0.0, max(-0.9, min(2.0, r52)) if fin(r52) else 0.0,
                      sw[i] if fin(sw[i]) else 0.05, 1.0 if not fin(payout) else 0.0])
            if t + 52 <= T_end:
                y.append(1.0 if any(t < c <= t + 52 for c in cuts) else 0.0)
            else:
                y.append(1.0 if any(t < c <= T_end for c in cuts) else np.nan)
            tt.append(t); rows.append(i)
    if not X:
        return None
    return {'X': np.array(X), 'y': np.array(y), 't': np.array(tt), 'i': np.array(rows),
            'year': np.array([int(str(D['dates'][t])[:4]) for t in tt]), 'events': ev,
            'features': ['dividend yield', 'payout ratio (dividends ÷ net income)', 'a loss over the last 4 quarters',
                         'net income lower than a year before', 'return over 52 weeks', 'weekly volatility', 'payout unknown or loss']}


def divcut_model(D, DC):
    if DC is None:
        return None
    ky = known_year(D, DC['t'], 52)
    p1, clim = walk_forward(DC['year'], DC['X'], DC['y'], ky, 2013, lam=1.0, min_pos=30)
    p, cal = recalibrate(DC['year'], p1, DC['y'], ky, 2015)
    clim[~np.isfinite(p)] = np.nan
    ok = np.isfinite(DC['y'])
    return {'p': p, 'card': card(p, DC['y'], clim, quantile=True), 'm': logit_fit(DC['X'][ok], DC['y'][ok], 1.0), 'cal': cal, 'features': DC['features']}


def _cal(m, p):
    if m is None:
        return p
    z = np.log(np.clip(p, 1e-5, 1 - 1e-5) / (1 - np.clip(p, 1e-5, 1 - 1e-5)))[:, None]
    return logit_predict(m, z)


# ------------------------------------------------------------------ the current odds of every stock
def current(D, TM, BM, SPM, SP, DCM, DC, debt=None):
    t = D['t_end']
    u = ST.universe(D, t)
    idx = np.where(u | (D['is_etf'] & np.isfinite(D['C'][:, t])))[0]
    sw = _vol(D, t)
    rows = {}
    fields = [k for k, _, _ in TOUCH] + [k for k, _ in BEAT] + ['sp500_12m', 'divcut_12m', 'merton_1y', 'vol']
    spy = D['ix'].get('SPY')
    with np.errstate(invalid='ignore', divide='ignore'):
        m121 = D['C'][:, t - 4] / D['C'][:, t - 52] - (D['C'][spy, t - 4] / D['C'][spy, t - 52] if spy is not None else 1)
        m13 = D['C'][:, t] / D['C'][:, t - 13] - (D['C'][spy, t] / D['C'][spy, t - 13] if spy is not None else 1)
        hi = D['C'][:, t] / np.nanmax(D['C'][:, t - 51:t + 1], axis=1)
    st = np.where(u)[0]
    Xb = np.full((len(D['tickers']), 4), 0.0)
    Xb[st] = np.nan_to_num(np.column_stack([_rank(m121[st]), _rank(m13[st]), _rank(hi[st]), _rank(sw[st])]), nan=0.0)
    sp_now = {}
    if SPM and SP is not None:
        last = SP['t'] == SP['t'].max()
        if SP['t'].max() == t:
            for i, x in zip(SP['i'][last], _cal(SPM.get('cal'), logit_predict(SPM['m'], SP['X'][last]))):
                sp_now[int(i)] = float(x)
    dc_now = {}
    if DCM and DC is not None:
        last = DC['t'] == DC['t'].max()
        if DC['t'].max() == t:
            for i, x in zip(DC['i'][last], _cal(DCM.get('cal'), logit_predict(DCM['m'], DC['X'][last]))):
                dc_now[int(i)] = float(x)
    mert = {}
    if debt:
        F = debt.get('fields') or []
        if 'distance_to_default' in F and 'ticker' in F:
            it, idd = F.index('ticker'), F.index('distance_to_default')
            for r in debt.get('rows') or []:
                if r[it] and fin(r[idd]) and r[idd] >= MIN_DD:
                    mert[r[it]] = norm_cdf(-r[idd])
    for i in idx:
        if not fin(sw[i]):
            continue
        v = []
        for k, x, h in TOUCH:
            p0 = float(touch_p0(np.array([sw[i]]), h, x)[0])
            z = math.log(min(max(p0, 1e-4), 1 - 1e-4) / (1 - min(max(p0, 1e-4), 1 - 1e-4)))
            v.append(round(float(logit_predict(TM[k]['m'], np.array([[z]]))[0]), 4))
        for k, _ in BEAT:
            v.append(round(float(logit_predict(BM[k]['m'], Xb[i:i + 1])[0]), 4) if u[i] else None)
        v.append(round(sp_now[i], 4) if i in sp_now else None)
        v.append(round(dc_now[i], 4) if i in dc_now else None)
        mm = mert.get(D['tickers'][i])
        v.append(round(mm, 6) if mm is not None else None)
        v.append(round(float(sw[i] * math.sqrt(52)), 4))
        rows[D['tickers'][i]] = v
    return fields, rows


def leaders(fields, rows, D, k=25):
    names = {}
    out = {}
    for key, rev in (('sp500_12m', True), ('divcut_12m', True), ('dn20_13', True), ('up20_13', True), ('merton_1y', True), ('beat52', True)):
        j = fields.index(key)
        L = [(t, v[j]) for t, v in rows.items() if v[j] is not None and not D['is_etf'][D['ix'][t]]]
        L.sort(key=lambda x: -x[1] if rev else x[1])
        out[key] = [[t, p] for t, p in L[:k]]
    return out


# ------------------------------------------------------------------ the live ledger
LEDGER_STOCK = ['dn20_13', 'up20_13', 'beat13', 'sp500_12m', 'divcut_12m']
HORIZON = {'dn10_4': 4, 'up10_4': 4, 'dn20_13': 13, 'up20_13': 13, 'beat13': 13, 'beat52': 52, 'sp500_12m': 52, 'divcut_12m': 52, 'down13': 13}


def ledger_update(path, D, fields, rows, market, members=None, DC=None, sha=None, made_at=None):
    path = Path(path)
    try:
        L = json.loads(path.read_text())
    except (OSError, ValueError):
        L = {'v': 1, 'note': "Each closed week's odds, frozen once (per mille for stocks) and never edited (app/odds.py).", 'weeks': []}
    wk = str(D['dates'][D['t_end']])
    if not L['weeks'] or L['weeks'][-1]['week'] < wk:
        tick = sorted(rows)
        e = {'week': wk, 'made_at': made_at or dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
             'market': market, 'tickers': tick, 'p': {}}
        if sha:
            e['sha'] = sha
        for k in LEDGER_STOCK:
            j = fields.index(k)
            e['p'][k] = [None if rows[t][j] is None else int(round(rows[t][j] * 1000)) for t in tick]
        L['weeks'].append(e)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(L, separators=(',', ':')))
    return L, ledger_score(L, D, members, DC)


def ledger_score(L, D, members=None, DC=None):
    """The frozen odds against what happened, for every horizon that has passed."""
    pos = {str(d): i for i, d in enumerate(D['dates'])}
    PS = D.get('PS', D['C'])
    ivs = sp500_intervals(members) if members else {}
    built = np.datetime64(str((members or {}).get('generated_at', ''))[:10] or str(D['dates'][D['t_end']]))
    P, Y = {k: [] for k in LEDGER_STOCK + ['down13']}, {k: [] for k in LEDGER_STOCK + ['down13']}
    spy = D['ix'].get('SPY')
    for e in L.get('weeks', []):
        t = pos.get(e['week'])
        if t is None:
            continue
        try:                                                  # frozen once the next week was under way: from the week after
            if dt.datetime.fromisoformat(e['made_at']) > dt.datetime.fromisoformat(e['week'] + 'T12:00:00+00:00') + dt.timedelta(days=3):
                t += 1
        except (KeyError, ValueError):
            pass
        for k in LEDGER_STOCK:
            h = HORIZON[k]
            if t + h > D['t_end']:
                continue
            for tk, p in zip(e['tickers'], e['p'].get(k, [])):
                i = D['ix'].get(tk)
                if p is None or i is None or not np.isfinite(PS[i, t]):
                    continue
                y = None
                if k in ('dn20_13', 'up20_13'):
                    win = PS[i, t + 1:t + h + 1]
                    if np.isfinite(win).any():
                        y = float(np.nanmin(win) <= PS[i, t] * 0.8) if k == 'dn20_13' else float(np.nanmax(win) >= PS[i, t] * 1.2)
                elif k == 'beat13' and spy is not None and np.isfinite(D['C'][i, t + h]):
                    y = float(D['C'][i, t + h] / D['C'][i, t] > D['C'][spy, t + h] / D['C'][spy, t])
                elif k == 'sp500_12m' and ivs:
                    d = D['dates'][t]
                    y = float(any(a is not None and d < a <= d + 52 * WEEK for a, _ in ivs.get(tk, [])))
                elif k == 'divcut_12m' and DC is not None and i in DC['events']:
                    y = float(any(t < c <= t + h for c in DC['events'][i][1]))
                if y is not None:
                    P[k].append(p / 1000); Y[k].append(y)
        m = e.get('market') or {}
        if fin(m.get('p_down13')) and spy is not None and t + 13 <= D['t_end']:
            P['down13'].append(m['p_down13']); Y['down13'].append(float(D['C'][spy, t + 13] < D['C'][spy, t]))
    return {'weeks': len(L.get('weeks', [])), 'since': L['weeks'][0]['week'] if L.get('weeks') else None,
            'cards': {k: card(np.array(P[k]), np.array(Y[k])) for k in P if len(P[k]) >= 30}}


# ------------------------------------------------------------------ publish
def _jd(o):
    return json.dumps(o, separators=(',', ':'), default=lambda v: None if isinstance(v, float) and not math.isfinite(v) else (float(v) if isinstance(v, np.floating) else int(v) if isinstance(v, np.integer) else str(v)))


def main():
    ap = argparse.ArgumentParser(description='Odds: probability models with calibration (app/odds.py)')
    ap.add_argument('--public', default='hist/public')
    ap.add_argument('--root', default=None, help='hist/ (the raw FRED cache for the monthly yield spread)')
    ap.add_argument('--members', default=None, help='members.json (app/index_members.py): the S&P 500 additions')
    ap.add_argument('--debt', default=None, help="Debt & rates' index.json (distance to default)")
    ap.add_argument('--site-index', default=None, help="the Sankey site's index.json (each company's latest form)")
    ap.add_argument('--ledger', default=None)
    ap.add_argument('--sha', default=None)
    ap.add_argument('--limit', type=int, default=None)
    a = ap.parse_args()
    warnings.filterwarnings('ignore', category=RuntimeWarning)

    def rj(p):
        try:
            return json.loads(Path(p).read_text()) if p else None
        except (OSError, ValueError):
            return None
    members, debt = rj(a.members), rj(a.debt)
    foreign = foreign_issuers(rj(a.site_index))
    D = ST.load(a.public, None, a.limit, dividends=True)
    today = dt.date.today()
    print(len(D['tickers']), 'names', flush=True)
    rec = recession(a.root, a.public, today)
    reg = regime(D, D['t_end'])
    print('market done', flush=True)
    P = stock_panel(D)
    TM, BM = touch_models(D, P), beat_models(D, P)
    print('touch and beat done', len(P['t']), 'samples', flush=True)
    SP = sp500_panel(D, members, foreign=foreign)
    SPM = sp500_model(D, SP)
    DC = divcut_panel(D)
    DCM = divcut_model(D, DC)
    print('S&P 500 and dividends done', flush=True)
    fields, rows = current(D, TM, BM, SPM, SP, DCM, DC, debt)
    market = {'p_stress': reg and reg['p_stress'], 'p_down13': reg and reg['p_down13'], 'recession': rec and rec['p']}
    live = None
    if a.ledger:
        _, live = ledger_update(a.ledger, D, fields, rows, market, members, DC, a.sha)
    spy = rows.get('SPY')
    models = {}
    for k, m in TM.items():
        models[k] = {'kind': 'touch', 'x': m['x'], 'h': m['h'], 'card': m['card'], 'card_raw': m['card_raw'],
                     'platt': [round(float(m['m'][2][0]), 4), round(float(m['m'][2][1] / m['m'][1][0]), 4)]}
    for k, m in BM.items():
        models[k] = {'kind': 'beat', 'h': m['h'], 'card': m['card'], 'features': m['features'],
                     'weights': [round(float(b), 4) for b in m['m'][2][1:]]}
    if SPM:
        models['sp500_12m'] = {'kind': 'sp500', 'h': 52, 'card': SPM['card'], 'features': SPM['features'], 'weights': [round(float(b), 4) for b in SPM['m'][2][1:]]}
    if DCM:
        models['divcut_12m'] = {'kind': 'divcut', 'h': 52, 'card': DCM['card'], 'features': DCM['features'], 'weights': [round(float(b), 4) for b in DCM['m'][2][1:]]}
    doc = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'asof': str(D['dates'][D['t_end']]),
           'market': {'recession': rec, 'regime': reg, 'spy': dict(zip(fields, spy)) if spy else None},
           'models': models, 'leaders': leaders(fields, rows, D), 'live': live,
           'counts': {'stocks': sum(1 for t in rows if not D['is_etf'][D['ix'][t]]), 'samples': int(len(P['t'])), 'foreign_left_out': len(foreign)},
           'data_notes': {'sp500_source_changes': {b: len(v) for b, v in mass_removals(members).items()},
                          'merton_left_out': sum(1 for r in (debt or {}).get('rows') or [] if fin(r[(debt.get('fields') or []).index('distance_to_default')]) and
                                                 r[(debt.get('fields') or []).index('distance_to_default')] < MIN_DD) if debt and 'distance_to_default' in (debt.get('fields') or []) else 0},
           'survivorship': "Today's companies only: delisted stocks are missing, which lowers the observed drawdowns and dividend cuts a little."}
    pub = Path(a.public)
    (pub / 'odds.json').write_text(_jd(doc))
    (pub / 'odds-stocks.json').write_text(_jd({'asof': doc['asof'], 'fields': fields, 'rows': rows}))
    print(json.dumps({'stocks': doc['counts']['stocks'], 'recession': rec and rec['p'], 'stress': reg and reg['p_stress'],
                      'skill': {k: (m['card'] or {}).get('skill') for k, m in models.items()}}))


if __name__ == '__main__':
    main()
