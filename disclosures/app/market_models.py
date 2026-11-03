"""Market models (Disclosures → Market models; rotation-history.yml, after the macro data and the odds): six forecasts of
the market as a whole, each tested walk-forward against a simple benchmark before it is shown, and each week's forecasts
frozen in a ledger and scored when the outcome is known.

Data: the weekly closes on rrg.json's Friday grid (dividend- and split-adjusted, since 1990: SPY, the SPDR sector funds and
the style funds — QQQ, DIA, MDY for the S&P MidCap 400, IWM, IJR for the S&P SmallCap 600 …), FRED as it was known each
Friday (macro_history.as_of: VIX and the CBOE indices for the Nasdaq-100, the Russell 2000 and the Dow, Moody's Baa less
the 10-year Treasury, the 10-year less 3-month curve, the 3-month bill, the Chicago Fed's financial conditions, CPI), the
sector aggregates of the site's companies (rotation-long.json) and, for the indices' current fundamentals, the members
(members.json) with their SEC figures and market values (rank/).

Walk-forward: every model is refitted once a year on the weeks whose outcome was known before 1 January, and predicts the
weeks of that year; the scores below count only those predictions. Overlapping h-week outcomes are not independent, so
counts of independent outcomes are weeks ÷ h. Settings (horizons, features, the ridge penalty, the benchmarks, the
first test year) were fixed before any result was seen and are reported whatever they show.

  1 volatility  HAR (Corsi 2009) on weekly squared returns: log of the next h weeks' variance on the logs of the last 1, 4
                and 26 weeks' (and, where an implied volatility exists, of the implied variance); h = 4 and 13 weeks.
                Benchmark: the last 26 weeks' volatility (what most sites show). Scores: QLIKE (the loss that ranks variance
                forecasts consistently, Patton 2011) against the benchmark's; the 80% range of the h-week return (the
                forecast volatility × the 10th and 90th percentiles of past standardized outcomes) and how often it held.
                Variance risk premium: implied variance (VIX², …) less the HAR forecast, annualized.
  2 indices     the six index funds (SPY, QQQ, DIA, MDY, IWM, IJR) against their equal-weight centre: the next 4 and 13
                weeks' relative log return on each index's momentum (52 weeks less the last 4; 13 weeks), the last 4 weeks
                (reversal) and its volatility against the centre's (all ranked within the week), plus market-wide
                conditions — the change in the credit spread over 13 weeks, the yield curve, the variance risk premium and
                the stressed-regime probability — each with its own coefficient per index; ridge, pooled. Benchmarks: no
                rotation (every index expected to match the centre) and momentum alone. Scores: rank correlation of
                forecast and outcome within the week, Brier skill of P(beats the centre), and the best-minus-worst pick.
  3 regime      a three-state hidden Markov model (Hamilton 1989) of SPY's weekly return, the level of the VIX and the
                4-week change in the credit spread, each state a normal distribution with its own means and spreads;
                calm, normal and stressed by the VIX. Probabilities are filtered (each week from the weeks up to it).
                Scored: P(SPY falls 10% or more within 13 weeks) from the states' past rates, against the base rate.
                From the out-of-sample weeks: how SPY, the six indices and the sectors did in the next 13 weeks by state.
  4 sectors     the eleven SPDR sector funds against SPY, as the indices plus the site's sector aggregates of the latest
                quarter on file (revenue growth against a year earlier, its acceleration, the operating margin against a
                year earlier — 46 days after the quarter ends). Benchmarks: none and momentum alone (Moskowitz and
                Grinblatt 1999).
  5 spreads     ratios (IWM/SPY, MDY/SPY, IJR/IWM — S&P's profitability screen against the Russell 2000 —, QQQ/DIA,
                RSP/SPY breadth, XLY/XLP, IWF/IWD, EEM/EFA) and two rates spreads (credit, curve): the next 4 and 13
                weeks' change by a random walk, by mean reversion (an AR(1), Ornstein–Uhlenbeck in discrete time) and by
                trend (the last 13 weeks' change); which one a spread follows is chosen on 2000–2011 and reported from 2012.
  6 market      SPY's return over cash, 13 and 52 weeks ahead: one regression per predictor (the variance risk premium,
                the curve, the credit spread and its change, the VIX, SPY's own 52-week excess return, financial
                conditions, inflation), their forecasts averaged (Rapach, Strauss and Zhou 2010). Benchmark: the past
                average (Goyal and Welch 2008). Score: out-of-sample R² against it, direction against the base rate.

Honest expectations: volatility is predictable; relative performance a little; the market's direction hardly at all.
Statistical models on public data, not investment advice.

  python app/market_models.py --public hist/public --macro hist/cache/macro --ledger hist/ledger/market-models.json \\
      --members site/members.json
"""
import argparse
import datetime as dt
import json
import math
import warnings
from pathlib import Path

import numpy as np

import forecast_book as FB
import macro_history as MH

VERSION = 1
FIRST_TEST = 2003           # the first year scored (earlier years train only)
SPREAD_SELECT = (2000, 2011)   # spreads: the model each one follows is chosen on these years, scored from the next
MIN_TRAIN = 156             # weeks of outcomes a fit needs
EPS_VAR = 0.0025 ** 2       # weekly variance floor (0.25% a week)
RIDGE = 30.0                # ridge penalty on standardized features (rotation models), fixed in advance
HORIZONS = (4, 13)
Z80 = 1.2815515655446004
COST_BP = 5.0               # one way, per fund (liquid ETFs)
INDICES = [('SPY', 'S&P 500'), ('QQQ', 'Nasdaq-100'), ('DIA', 'Dow Jones'), ('MDY', 'S&P MidCap 400'),
           ('IWM', 'Russell 2000'), ('IJR', 'S&P SmallCap 600')]
INDEX_MEMBERS = {'SPY': 'sp500', 'QQQ': 'ndx', 'DIA': 'dji', 'MDY': 'sp400', 'IWM': 'r2000', 'IJR': 'sp600'}
SECTORS = [('XLK', 'technology', 'Technology'), ('XLC', 'communication', 'Communication Services'),
           ('XLY', 'consumer-disc', 'Consumer Discretionary'), ('XLP', 'consumer-staples', 'Consumer Staples'),
           ('XLV', 'health', 'Health Care'), ('XLF', 'financials', 'Financials'), ('XLRE', 'real-estate', 'Real Estate'),
           ('XLE', 'energy', 'Energy'), ('XLB', 'materials', 'Materials'), ('XLI', 'industrials', 'Industrials'),
           ('XLU', 'utilities', 'Utilities')]
VOL_ASSETS = [t for t, _ in INDICES] + [t for t, _, _ in SECTORS] + ['TLT', 'GLD', 'EFA', 'EEM']
IMPLIED = {'SPY': 'VIXCLS', 'QQQ': 'VXNCLS', 'IWM': 'RVXCLS', 'DIA': 'VXDCLS'}
RATIOS = [('IWM/SPY', 'IWM', 'SPY', 'Small caps vs the S&P 500'), ('MDY/SPY', 'MDY', 'SPY', 'Mid caps vs the S&P 500'),
          ('IJR/IWM', 'IJR', 'IWM', 'S&P 600 vs Russell 2000 (the profitability screen)'), ('QQQ/DIA', 'QQQ', 'DIA', 'Nasdaq-100 vs the Dow'),
          ('RSP/SPY', 'RSP', 'SPY', 'Equal weight vs cap weight (breadth)'), ('XLY/XLP', 'XLY', 'XLP', 'Discretionary vs staples (risk appetite)'),
          ('IWF/IWD', 'IWF', 'IWD', 'Growth vs value'), ('EEM/EFA', 'EEM', 'EFA', 'Emerging vs developed markets')]
RATE_SPREADS = [('credit', 'BAA10Y', 'Credit spread: Baa less 10-year Treasury (points)'), ('curve', 'T10Y3M', 'Yield curve: 10-year less 3-month (points)')]
MACRO_IDS = ('VIXCLS', 'VXNCLS', 'RVXCLS', 'VXDCLS', 'VXVCLS', 'BAA10Y', 'T10Y3M', 'DGS3MO', 'NFCI', 'CPIAUCSL', 'DFII10')
FUND_COLS = ('revg', 'reva', 'dom')                # rotation-long sector fields: revenue growth, its acceleration, margin vs a year earlier
FUND_LAG_DAYS = 46


def fin(v):
    return v is not None and isinstance(v, (int, float, np.floating)) and math.isfinite(v)


def r_(v, d=4):
    return round(float(v), d) if fin(v) else None


# ------------------------------------------------------------------ data
def load_grid(public):
    """(days, {id: weekly closes}) on rrg.json's Friday grid; NaN where a fund has no close."""
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
    C = {s['id']: full(s) for s in D.get('series') or []}
    C[D.get('benchmark') or 'SPY'] = full(D.get('bench'))
    return days, C


def macro_weekly(macro_dir, days):
    """{FRED id: value known on each Friday} (macro_history.as_of: the publication lag respected)."""
    out = {}
    py_days = [dt.date.fromisoformat(str(d)) for d in days]
    for sid in MACRO_IDS:
        p = Path(macro_dir) / f'{sid}.csv'
        if not p.exists():
            continue
        obs = MH.parse_csv(p.read_text(encoding='utf-8'))
        _, _, freq, lag, _ = MH.SERIES.get(sid, ('', '', 'd', 1, ''))
        out[sid] = MH.as_of(obs, freq, lag, py_days)
    if 'CPIAUCSL' in out:                                 # inflation over the past year, as known
        p = Path(macro_dir) / 'CPIAUCSL.csv'
        obs = MH.parse_csv(p.read_text(encoding='utf-8'))
        _, _, freq, lag, _ = MH.SERIES['CPIAUCSL']
        then = MH.as_of_lagged(obs, freq, lag, py_days, 365)
        with np.errstate(invalid='ignore', divide='ignore'):
            out['infl'] = out['CPIAUCSL'] / then - 1
    return out


def cash_weekly(days, M):
    """Weekly log return of the 3-month bill: the yield known when the week began, seven days of it."""
    y = M.get('DGS3MO')
    r = np.full(len(days), np.nan)
    if y is None:
        return np.zeros(len(days))
    r[1:] = np.log1p(np.nan_to_num(y[:-1], nan=np.nan) / 100) * 7 / 365.25
    return np.where(np.isfinite(r), r, 0.0)


def log_ret(c):
    with np.errstate(divide='ignore', invalid='ignore'):
        r = np.full(len(c), np.nan)
        r[1:] = np.log(c[1:] / c[:-1])
    return r


def fwd_sum(x, h):
    """Σ x[t+1 … t+h] for each t (NaN if any is missing or past the end)."""
    W = len(x)
    out = np.full(W, np.nan)
    cs = np.concatenate([[0.0], np.cumsum(np.where(np.isfinite(x), x, 0.0))])
    bad = np.concatenate([[0], np.cumsum(~np.isfinite(x))])
    t = np.arange(W - h)
    ok = bad[t + h + 1] - bad[t + 1] == 0
    out[t] = np.where(ok, cs[t + h + 1] - cs[t + 1], np.nan)
    return out


def back_sum(x, k, skip=0):
    """Σ x[t − skip − k + 1 … t − skip] for each t (NaN if any is missing)."""
    W = len(x)
    out = np.full(W, np.nan)
    cs = np.concatenate([[0.0], np.cumsum(np.where(np.isfinite(x), x, 0.0))])
    bad = np.concatenate([[0], np.cumsum(~np.isfinite(x))])
    t = np.arange(k + skip - 1, W)
    hi, lo = t - skip + 1, t - skip - k + 1
    ok = bad[hi] - bad[lo] == 0
    out[t] = np.where(ok, cs[hi] - cs[lo], np.nan)
    return out


def back_mean(x, k):
    return back_sum(x, k) / k


def years_of(days):
    return np.array([int(str(d)[:4]) for d in days])


def train_mask(days, end_idx, valid, year):
    """Rows whose outcome (the week end_idx) was known before 1 January of `year`."""
    cut = np.datetime64(f'{year}-01-01')
    W = len(days)
    e = np.clip(end_idx, 0, W - 1)
    return valid & (end_idx < W) & (days[e] < cut)


# ------------------------------------------------------------------ small regressions
def ols(X, y, lam=0.0):
    """(coefficients with the intercept first) — ridge on standardized columns when lam > 0 (intercept not penalized)."""
    mu, sd = X.mean(0), X.std(0)
    sd = np.where(sd > 1e-12, sd, 1.0)
    Z = (X - mu) / sd
    A = Z.T @ Z + lam * np.eye(Z.shape[1])
    b = np.linalg.solve(A, Z.T @ (y - y.mean())) if Z.shape[1] else np.zeros(0)
    return {'mu': mu, 'sd': sd, 'b': b, 'a': float(y.mean())}


def predict(m, X):
    return m['a'] + ((X - m['mu']) / m['sd']) @ m['b']


def qlike(rv, f):
    q = rv / f
    return q - np.log(q) - 1


def oos_r2(y, f, f0):
    ok = np.isfinite(y) & np.isfinite(f) & np.isfinite(f0)
    if ok.sum() < 20:
        return None
    d0 = ((y[ok] - f0[ok]) ** 2).sum()
    return float(1 - ((y[ok] - f[ok]) ** 2).sum() / d0) if d0 > 0 else None


def brier_skill(p, y, p0):
    ok = np.isfinite(p) & np.isfinite(y) & np.isfinite(p0)
    if ok.sum() < 20:
        return None, int(ok.sum())
    b, b0 = ((p[ok] - y[ok]) ** 2).mean(), ((p0[ok] - y[ok]) ** 2).mean()
    return (float(1 - b / b0) if b0 > 0 else None), int(ok.sum())


def spearman(a, b):
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return np.nan
    ra, rb = np.argsort(np.argsort(a[ok])), np.argsort(np.argsort(b[ok]))
    if ra.std() == 0 or rb.std() == 0:
        return np.nan
    return float(np.corrcoef(ra, rb)[0, 1])


# ------------------------------------------------------------------ using a forecast only as far as it has worked before
MIN_CAL = 260               # five years of earlier out-of-sample forecasts with outcomes before a model is trusted at all
                            # (two years, tried first, let the 2000–2002 bear market alone set the 2003 regime odds)


def shrink_walk(days, F, y, h, base=None):
    """The published forecast: base + β × (F − base), β refitted each year by least squares on the model's earlier
    out-of-sample forecasts whose outcomes were known by then, clipped to [0, 1] — a model with no record yet, or no
    skill, gives the benchmark (base; None = 0: no change, no rotation). Also each year's out-of-sample errors of the
    published forecast (for probabilities and ranges). F, y: (members × weeks) or (weeks)."""
    one = F.ndim == 1
    F2, y2 = (F[None], y[None]) if one else (F, y)
    b2 = np.zeros_like(F2) if base is None else (base[None] if one else base)
    W = F2.shape[1]
    yrs = years_of(days)
    end_day = days[np.clip(np.arange(W) + h, 0, W - 1)]
    beyond = np.arange(W) + h >= W
    Fc = np.full_like(F2, np.nan)
    beta, errs = {}, {}
    for Y in sorted(set(yrs[np.isfinite(F2).any(0)].tolist())):
        known = (~beyond) & (end_day < np.datetime64(f'{Y}-01-01')) & (yrs < Y)
        m = known[None] & np.isfinite(F2) & np.isfinite(y2) & np.isfinite(b2)
        dF, dy = (F2 - b2)[m], (y2 - b2)[m]
        bt = float(np.clip((dF * dy).sum() / (dF * dF).sum(), 0.0, 1.0)) if m.sum() >= MIN_CAL and (dF * dF).sum() > 0 else 0.0
        beta[Y] = bt
        te = (yrs == Y)[None] & np.isfinite(F2)
        Fc[te] = (b2 + bt * (F2 - b2))[te]
        errs[Y] = (y2 - (b2 + bt * (F2 - b2)))[m] if m.sum() >= MIN_CAL else None
    return (Fc[0] if one else Fc), beta, errs


# ------------------------------------------------------------------ 1. volatility (HAR)
def har_features(r, iv=None):
    r2 = np.where(np.isfinite(r), r * r, np.nan)
    f = [np.log(np.maximum(r2, EPS_VAR)), np.log(np.maximum(back_mean(r2, 4), EPS_VAR)), np.log(np.maximum(back_mean(r2, 26), EPS_VAR))]
    if iv is not None:
        f.append(np.log(np.maximum((iv / 100) ** 2 / 52, EPS_VAR)))
    return np.vstack(f).T, r2


def har_walk(days, r, h, iv=None, first=None):
    """Walk-forward HAR: per week the forecast of the mean weekly variance over the next h weeks (HAR, and the 26-week
    benchmark), the realized one, the h-week return and the standardized-outcome quantiles of the fit used."""
    X, r2 = har_features(r, iv)
    y_rv = fwd_sum(r2, h) / h
    R = fwd_sum(r, h)
    W = len(days)
    end = np.arange(W) + h
    okX = np.isfinite(X).all(1)
    valid = okX & np.isfinite(y_rv) & (y_rv > 0)
    yrs = years_of(days)
    F = np.full(W, np.nan)
    Q = np.full((W, 2), np.nan)
    if first is None:
        if not okX.any():
            return None
        first = int(yrs[np.argmax(okX)]) + 4
    for Y in range(first, int(yrs[-1]) + 1):
        tr = train_mask(days, end, valid, Y)
        if tr.sum() < MIN_TRAIN:
            continue
        m = ols(X[tr], np.log(np.maximum(y_rv[tr], EPS_VAR)))
        res = np.log(np.maximum(y_rv[tr], EPS_VAR)) - predict(m, X[tr])
        s2 = float(res.var())
        fit_f = np.exp(predict(m, X[tr]) + s2 / 2)
        z = R[tr] / np.sqrt(h * fit_f)
        z = z[np.isfinite(z)]
        te = (yrs == Y) & okX
        F[te] = np.exp(predict(m, X[te]) + s2 / 2)
        if len(z) >= 50:
            Q[te] = np.quantile(z, [0.1, 0.9])
    hist = np.exp(X[:, 2])
    return {'F': F, 'hist': hist, 'rv': y_rv, 'R': R, 'Q': Q, 'X': X}


def vol_model(days, C, M, today_idx):
    yrs = years_of(days)
    out_assets, scores, vrp = [], [], {}
    for a in VOL_ASSETS:
        c = C.get(a)
        if c is None or np.isfinite(c).sum() < MIN_TRAIN + 30:
            continue
        r = log_ret(c)
        ivs = M.get(IMPLIED.get(a)) if IMPLIED.get(a) else None
        row = {'id': a, 'start': str(days[np.argmax(np.isfinite(c))])}
        for h in HORIZONS:
            res = har_walk(days, r, h, None, None)
            if not res:
                continue
            resx = har_walk(days, r, h, ivs) if ivs is not None and np.isfinite(ivs).sum() > MIN_TRAIN else None
            F, hist, rv, R, Q = res['F'], res['hist'], res['rv'], res['R'], res['Q']
            te = (yrs >= FIRST_TEST) & np.isfinite(F) & np.isfinite(rv) & np.isfinite(hist)
            sc = {'h': h, 'n': int(te.sum()), 'independent': int(te.sum() // h)}
            if te.sum() >= 52:
                ql, ql0 = qlike(rv[te], F[te]).mean(), qlike(rv[te], hist[te]).mean()
                sc.update({'qlike': r_(ql), 'qlike_hist': r_(ql0), 'gain_vs_hist': r_(1 - ql / ql0),
                           'log_mae': r_(np.abs(np.log(rv[te] / F[te])).mean()), 'log_mae_hist': r_(np.abs(np.log(rv[te] / hist[te])).mean())})
                lo, hi = Q[te, 0] * np.sqrt(h * F[te]), Q[te, 1] * np.sqrt(h * F[te])
                okR = np.isfinite(R[te]) & np.isfinite(lo)
                sc['coverage80'] = r_(((R[te][okR] >= lo[okR]) & (R[te][okR] <= hi[okR])).mean()) if okR.sum() else None
                s0 = np.sqrt(h * hist[te])
                sc['coverage80_hist'] = r_(((R[te] >= -Z80 * s0) & (R[te] <= Z80 * s0)).mean())
                if resx is not None:
                    tex = te & np.isfinite(resx['F'])
                    if tex.sum() >= 52:
                        sc['qlike_with_implied'] = r_(qlike(rv[tex], resx['F'][tex]).mean())
                        sc['qlike_without_on_same_weeks'] = r_(qlike(rv[tex], F[tex]).mean())
                if ivs is not None:
                    iv_var = (ivs / 100) ** 2 / 52
                    tei = te & np.isfinite(iv_var)
                    if tei.sum() >= 52:
                        sc['qlike_implied_alone'] = r_(qlike(rv[tei], iv_var[tei]).mean())
                        sc['qlike_on_implied_weeks'] = r_(qlike(rv[tei], F[tei]).mean())
            t = today_idx
            best = resx['F'] if resx is not None and fin(resx['F'][t]) else F     # with an implied volatility, always (fixed in advance)
            sc['model'] = 'HAR + implied' if best is not F else 'HAR'
            if best is not F and sc.get('qlike_with_implied') is not None:
                tex = te & np.isfinite(resx['F'])
                sc['gain_vs_hist_used'] = r_(1 - qlike(rv[tex], resx['F'][tex]).mean() / qlike(rv[tex], hist[tex]).mean())
            else:
                sc['gain_vs_hist_used'] = sc.get('gain_vs_hist')
            if fin(best[t]):
                Qb = resx['Q'] if best is not F else Q
                q = Qb[t] if np.isfinite(Qb[t]).all() else np.array([-Z80, Z80])
                sig = math.sqrt(h * best[t])
                row[f'h{h}'] = {'vol': r_(math.sqrt(52 * best[t])), 'hist_vol': r_(math.sqrt(52 * hist[t])),
                                'range': [r_(math.exp(q[0] * sig) - 1), r_(math.exp(q[1] * sig) - 1)], 'uses_implied': best is not F}
            scores.append({'id': a, **sc})
            if h == 4:
                row['_F4'] = F
                if ivs is not None:
                    v = (ivs / 100) ** 2 - 52 * F
                    vrp[a] = v
                    row['implied_vol'] = r_(ivs[t] / 100) if fin(ivs[t]) else None
                    row['vrp'] = r_(v[t]) if fin(v[t]) else None
        out_assets.append(row)
    return out_assets, scores, vrp


# ------------------------------------------------------------------ 3. regime (three-state HMM)
def _hmm_fb(X, mu, var, P, pi):
    T, K = X.shape[0], len(pi)
    logB = -0.5 * (((X[:, None, :] - mu[None]) ** 2) / var[None] + np.log(2 * np.pi * var[None])).sum(2)
    mx = logB.max(1, keepdims=True)
    B = np.exp(logB - mx)
    alpha = np.zeros((T, K))
    c = np.zeros(T)
    a = pi * B[0]
    c[0] = a.sum() or 1e-300
    alpha[0] = a / c[0]
    for t in range(1, T):
        a = (alpha[t - 1] @ P) * B[t]
        c[t] = a.sum() or 1e-300
        alpha[t] = a / c[t]
    beta = np.ones((T, K))
    for t in range(T - 2, -1, -1):
        beta[t] = (P @ (B[t + 1] * beta[t + 1])) / c[t + 1]
    gamma = alpha * beta
    gamma /= gamma.sum(1, keepdims=True)
    xi = np.zeros((K, K))
    for t in range(T - 1):
        xi += np.outer(alpha[t], B[t + 1] * beta[t + 1]) * P / c[t + 1]
    return gamma, xi, float(np.log(c).sum() + mx.sum()), alpha


def hmm_fit(X, K=3, iters=80, init=None, tol=1e-6):
    """Baum–Welch for a K-state HMM with diagonal Gaussian emissions; states ordered by their mean of column 1 (the
    VIX), lowest first. X standardized by the caller."""
    T, d = X.shape
    if init:
        mu, var, P, pi = (np.array(init[k], float) for k in ('mu', 'var', 'P', 'pi'))
    else:
        q = np.quantile(X[:, 1], [1 / 3, 2 / 3])
        lab = np.digitize(X[:, 1], q)
        mu = np.array([X[lab == k].mean(0) if (lab == k).sum() > d else X.mean(0) for k in range(K)])
        var = np.array([np.maximum(X[lab == k].var(0), 0.05) if (lab == k).sum() > d else X.var(0) for k in range(K)])
        P = np.full((K, K), 0.05 / (K - 1)) + np.eye(K) * (0.95 - 0.05 / (K - 1))
        pi = np.full(K, 1 / K)
    prev = -np.inf
    for _ in range(iters):
        g, xi, ll, _ = _hmm_fb(X, mu, var, P, pi)
        w = g.sum(0) + 1e-9
        mu = (g.T @ X) / w[:, None]
        var = np.maximum((g.T @ (X ** 2)) / w[:, None] - mu ** 2, 0.02)
        P = (xi + 1e-6) / (xi + 1e-6).sum(1, keepdims=True)
        pi = g[0] + 1e-6
        pi /= pi.sum()
        if ll - prev < tol * abs(ll):
            break
        prev = ll
    o = np.argsort(mu[:, 1])
    return {'mu': mu[o].tolist(), 'var': var[o].tolist(), 'P': P[np.ix_(o, o)].tolist(), 'pi': pi[o].tolist(), 'll': ll}


def hmm_filter(X, fit):
    mu, var, P, pi = (np.array(fit[k], float) for k in ('mu', 'var', 'P', 'pi'))
    return _hmm_fb(X, mu, var, P, pi)[3]


STATE_NAMES = ['Calm', 'Normal', 'Stressed']


def regime_model(days, C, M, today_idx):
    spy = C.get('SPY')
    r = log_ret(spy)
    vix = M.get('VIXCLS')
    baa = M.get('BAA10Y')
    if vix is None or baa is None:
        return None, None
    W = len(days)
    dcr = np.full(W, np.nan)
    dcr[4:] = baa[4:] - baa[:-4]
    X = np.vstack([r, np.log(vix), dcr]).T
    ok = np.isfinite(X).all(1)
    yrs = years_of(days)
    probs = np.full((W, 3), np.nan)
    fits = {}
    prev = None
    first_data = int(yrs[np.argmax(ok)])
    for Y in range(first_data + 4, int(yrs[-1]) + 1):
        tr = ok & (days < np.datetime64(f'{Y}-01-01'))
        if tr.sum() < 200:
            continue
        mu, sd = X[tr].mean(0), X[tr].std(0)
        Z = (X - mu) / sd
        fit = hmm_fit(Z[tr], init=prev, iters=60 if prev else 120)
        prev = {k: fit[k] for k in ('mu', 'var', 'P', 'pi')}
        fits[Y] = {**fit, 'scale_mu': mu.tolist(), 'scale_sd': sd.tolist()}
        idx = np.where(ok & (yrs <= Y))[0]
        a = hmm_filter(Z[idx], fit)
        sel = yrs[idx] == Y
        probs[idx[sel]] = a[sel]
    # outcomes: SPY's next 13 weeks
    R13 = fwd_sum(r, 13)
    down10 = np.where(np.isfinite(R13), (R13 <= math.log(0.9)).astype(float), np.nan)
    rv13 = fwd_sum(np.where(np.isfinite(r), r * r, np.nan), 13)
    # P(down 10%) from each state's past rate (only outcomes known before the year), against the base rate
    pd_, p0 = np.full(W, np.nan), np.full(W, np.nan)
    end = np.arange(W) + 13
    have = np.isfinite(probs).all(1)
    for Y in sorted(fits):
        tr = train_mask(days, end, have & np.isfinite(down10), Y)
        if tr.sum() < 100:
            continue
        w = probs[tr]
        rate = (w * down10[tr, None]).sum(0) / np.maximum(w.sum(0), 1e-9)
        base = float(down10[tr].mean())
        te = (yrs == Y) & have
        pd_[te] = probs[te] @ rate
        p0[te] = base
    raw_skill, _ = brier_skill(np.where(yrs >= FIRST_TEST, pd_, np.nan), down10, np.where(yrs >= FIRST_TEST, p0, np.nan))
    # published: the base rate plus the states' signal only as far as it has worked before (shrink_walk)
    pc, beta, _ = shrink_walk(days, pd_, down10, 13, base=p0)
    pd_ = np.clip(pc, 0.0, 1.0)
    sel = yrs >= FIRST_TEST
    skill, n = brier_skill(np.where(sel, pd_, np.nan), down10, np.where(sel, p0, np.nan))
    Y_last = max(fits) if fits else None
    t = today_idx
    out = {'states': [], 'now': [r_(v) for v in probs[t]] if np.isfinite(probs[t]).all() else None,
           'p_down10_13w': r_(pd_[t]), 'base_down10_13w': r_(p0[t]),
           'score': {'down10_13w_brier_skill': r_(skill), 'down10_13w_brier_skill_raw': r_(raw_skill), 'n': n, 'independent': n // 13,
                     'beta_now': r_(beta.get(int(yrs[-1])))},
           'fits': len(fits)}
    if Y_last:
        f = fits[Y_last]
        mu_s = np.array(f['mu']) * np.array(f['scale_sd']) + np.array(f['scale_mu'])
        sd_s = np.sqrt(np.array(f['var'])) * np.array(f['scale_sd'])
        P = np.array(f['P'])
        for k in range(3):
            out['states'].append({'name': STATE_NAMES[k], 'ret_year': r_(mu_s[k, 0] * 52), 'vol_year': r_(sd_s[k, 0] * math.sqrt(52)),
                                  'vix': r_(math.exp(mu_s[k, 1]), 1), 'credit_4w': r_(mu_s[k, 2], 3), 'stay': r_(P[k, k]),
                                  'weeks': r_(1 / max(1e-6, 1 - P[k, k]), 1)})
        out['P'] = [[r_(v) for v in row] for row in P.tolist()]
        out['fitted_on'] = f'weeks before {Y_last}-01-01'
    # out-of-sample weeks by their likeliest state: the next 13 weeks
    lab = np.where(have, np.nanargmax(np.where(have[:, None], probs, -1), 1), -1)
    oos = sel & have & np.isfinite(R13)
    out['by_state'] = []
    for k in range(3):
        m = oos & (lab == k)
        out['by_state'].append({'name': STATE_NAMES[k], 'weeks': int(m.sum()), 'spy_13w': r_(np.mean(R13[m])) if m.sum() else None,
                                'spy_13w_vol': r_(math.sqrt(np.mean(rv13[m]) * 52 / 13)) if m.sum() else None,
                                'down10_share': r_(np.mean(down10[m])) if m.sum() else None})
    hist_from = np.argmax(have)
    out['history'] = {'start': str(days[hist_from]), 'p': [[r_(v, 3) for v in row] for row in probs[hist_from:t + 1]]}
    return out, {'probs': probs, 'lab': lab, 'have': have}


# ------------------------------------------------------------------ 2 & 4. rotation (indices, sectors)
def xs_z(A):
    """Within each week (row), z-score across the members present; NaN stays NaN."""
    m = np.nanmean(A, 1, keepdims=True)
    s = np.nanstd(A, 1, keepdims=True)
    with np.errstate(invalid='ignore', divide='ignore'):
        Z = (A - m) / np.where(s > 1e-12, s, np.nan)
    return np.clip(Z, -3, 3)


def rotation_panel(days, C, members, base, fund=None, min_members=3):
    """Per member (rows) and week (columns): relative log returns against the base (the members' equal-weight centre
    when base is None), the features (momentum 52-4 and 13 weeks, the last 4, volatility against the base's, and the
    fundamental columns when given, each ranked within the week) and the forward relative returns."""
    ids = [m for m in members if C.get(m) is not None and np.isfinite(C[m]).sum() > 60]
    R = np.vstack([log_ret(C[m]) for m in ids])
    W = R.shape[1]
    avail = np.isfinite(R)
    if base is None:
        n = avail.sum(0)
        rb = np.where(n >= min_members, np.nanmean(np.where(avail, R, np.nan), 0), np.nan)
    else:
        rb = log_ret(C[base])
    rel = R - rb[None]
    feats = {'mom52_4': np.vstack([back_sum(x, 48, 4) for x in rel]), 'mom13': np.vstack([back_sum(x, 13) for x in rel]),
             'rev4': np.vstack([back_sum(x, 4) for x in rel])}
    vb = np.sqrt(back_mean(rb ** 2, 26))
    feats['vol'] = np.vstack([np.log(np.sqrt(back_mean(x ** 2, 26)) / vb) for x in R])
    for k, by_id in (fund or {}).items():
        feats[k] = np.vstack([by_id.get(m, np.full(W, np.nan)) for m in ids])
    Z = {k: xs_z(v.T).T for k, v in feats.items()}
    fwd = {h: np.vstack([fwd_sum(x, h) for x in rel]) for h in HORIZONS}
    return {'ids': ids, 'rel': rel, 'feat': Z, 'raw': feats, 'fwd': fwd, 'W': W}


def macro_features(days, M, vrp_spy, regime_probs):
    W = len(days)
    baa = M.get('BAA10Y', np.full(W, np.nan))
    d13 = np.full(W, np.nan)
    d13[13:] = baa[13:] - baa[:-13]
    f = {'credit_13w': d13, 'curve': M.get('T10Y3M', np.full(W, np.nan)),
         'vrp': vrp_spy if vrp_spy is not None else np.full(W, np.nan),
         'stress': regime_probs[:, 2] if regime_probs is not None else np.full(W, np.nan)}
    return f


def rotation_model(days, P, macro, kinds, first_test=FIRST_TEST, top=1):
    """Walk-forward ridge for every horizon: forecasts, P(beats the base) from the fit's residuals, the leader odds from
    residual vectors of whole training weeks, and the scores against no rotation and momentum alone."""
    ids, W = P['ids'], P['W']
    L = len(ids)
    yrs = years_of(days)
    fk = list(P['feat'])
    mk = [k for k in macro if np.isfinite(macro[k]).sum() > 260]
    out = {}
    for h in HORIZONS:
        rows = []
        for i in range(L):
            Xi = [P['feat'][k][i] for k in fk]
            Xi += [np.where(np.isfinite(macro[k]), macro[k], np.nan) for k in mk]
            rows.append(np.vstack(Xi).T)
        X = np.stack(rows)                                 # L × W × (features + macro)
        y = P['fwd'][h]                                    # L × W
        nf, nm = len(fk), len(mk)
        # fundamentals may be missing early: neutral (0) after ranking; momentum and volatility must exist
        core = np.isfinite(X[:, :, :4]).all(2)
        Xf = np.where(np.isfinite(X), X, 0.0)
        end = np.arange(W) + h
        F = np.full((L, W), np.nan)
        Fm = np.full((L, W), np.nan)
        Pbeat = np.full((L, W), np.nan)
        Pbase = np.full((L, W), np.nan)
        Plead = np.full((L, W), np.nan)
        coefs = None
        Rv_by_year = {}
        macro_ok = np.isfinite(X[:, :, nf:]).all(2) if nm else np.ones((L, W), bool)

        def design(Xs, i_idx):
            """features, then each macro column times a member dummy, then member intercepts."""
            n = Xs.shape[0]
            D = np.zeros((n, L))
            D[np.arange(n), i_idx] = 1.0
            parts = [Xs[:, :nf]]
            if nm:
                parts.append((Xs[:, nf:, None] * D[:, None, :]).reshape(n, nm * L))
            parts.append(D)
            return np.hstack(parts)
        last_year = int(yrs[-1])
        first_year = int(yrs[np.argmax(core.any(0))]) + 3
        for Y in range(max(first_year, 1995), last_year + 1):
            ii, tt = np.where(core & macro_ok & np.isfinite(y))
            keep = train_mask(days, end[tt], np.ones(len(tt), bool), Y)
            ii, tt = ii[keep], tt[keep]
            if len(tt) < MIN_TRAIN * 2:
                continue
            Xtr = design(Xf[ii, tt], ii)
            m = ols(Xtr, y[ii, tt], lam=RIDGE)
            mm = ols(Xf[ii, tt][:, [fk.index('mom52_4')]], y[ii, tt], lam=RIDGE)
            res = y[ii, tt] - predict(m, Xtr)
            base_rate = float((y[ii, tt] > 0).mean())
            # residual vectors of whole weeks (every member present) for the leader odds
            full_weeks = [t for t in np.unique(tt) if (tt == t).sum() == L]
            Rv = np.full((len(full_weeks), L), np.nan)
            pos = {t: k for k, t in enumerate(full_weeks)}
            for k_, (i_, t_) in enumerate(zip(ii, tt)):
                if t_ in pos:
                    Rv[pos[t_], i_] = res[k_]
            te_t = np.where((yrs == Y))[0]
            Rv_by_year[Y] = Rv
            for t in te_t:
                live = [i for i in range(L) if core[i, t] and macro_ok[i, t]]
                if len(live) < 3:
                    continue
                Xte = design(Xf[live, t], np.array(live))
                F[live, t] = predict(m, Xte)
                Fm[live, t] = predict(mm, Xf[live, t][:, [fk.index('mom52_4')]])
                Pbase[live, t] = base_rate
            if Y == last_year:
                names = fk + [f'{k}×{ids[i]}' for k in mk for i in range(L)] + [f'const×{i}' for i in ids]
                coefs = {n_: r_(b / s, 5) for n_, b, s in zip(names, m['b'], m['sd'])}
        # the published forecast: the model only as far as it has worked out of sample before (shrink_walk)
        Fc, beta, errs = shrink_walk(days, F, y, h)
        for t in np.where(np.isfinite(Fc).any(0))[0]:
            Y = int(yrs[t])
            e = errs.get(Y)
            live = np.where(np.isfinite(Fc[:, t]))[0]
            for i in live:
                Pbeat[i, t] = float((Fc[i, t] + e > 0).mean()) if e is not None and len(e) else Pbase[i, t]
            Rv = Rv_by_year.get(Y)
            if Rv is not None and len(Rv) >= 50 and len(live) == L:
                best = np.argmax(Fc[:, t][None, :] + Rv, 1)
                Plead[:, t] = np.bincount(best, minlength=L) / len(Rv)
        # scores (out of sample, from first_test)
        sc = {'h': h, 'beta_now': r_(beta.get(last_year)), 'beta_by_year': {str(k): r_(v, 3) for k, v in beta.items() if k >= first_test}}
        test = years_of(days) >= first_test
        ics, icm, ls, lsm, ws = [], [], [], [], []
        for t in np.where(test)[0][::h]:                   # non-overlapping origins
            ok = np.isfinite(F[:, t]) & np.isfinite(y[:, t])
            if ok.sum() < 3:
                continue
            ics.append(spearman(F[ok, t], y[ok, t]))
            icm.append(spearman(Fm[ok, t], y[ok, t]))
            o = np.where(ok)[0]
            k = min(top, len(o) // 2)
            hi_ = o[np.argsort(F[o, t])[-k:]]
            lo_ = o[np.argsort(F[o, t])[:k]]
            ls.append(y[hi_, t].mean() - y[lo_, t].mean() - 4 * COST_BP / 1e4)
            him = o[np.argsort(Fm[o, t])[-k:]]
            lom = o[np.argsort(Fm[o, t])[:k]]
            lsm.append(y[him, t].mean() - y[lom, t].mean() - 4 * COST_BP / 1e4)
            ws.append(str(days[t])[:4])
        ics, icm = np.array([v for v in ics if np.isfinite(v)]), np.array([v for v in icm if np.isfinite(v)])
        msk = test[None, :] & np.isfinite(Pbeat) & np.isfinite(y)
        bs, nb = brier_skill(Pbeat[msk], (y[msk] > 0).astype(float), Pbase[msk])
        # the raw model's own probabilities, for the record: its forecast plus its in-sample residual spread
        raw_p = np.full_like(F, np.nan)
        for t in np.where(test & np.isfinite(F).any(0))[0]:
            e = errs.get(int(yrs[t]))
            if e is not None and len(e):
                sdev = np.std(e)
                for i in np.where(np.isfinite(F[:, t]))[0]:
                    raw_p[i, t] = 0.5 * (1 + math.erf(F[i, t] / (sdev * math.sqrt(2))))
        mr = test[None, :] & np.isfinite(raw_p) & np.isfinite(y) & np.isfinite(Pbase)
        bs_raw, _ = brier_skill(raw_p[mr], (y[mr] > 0).astype(float), Pbase[mr])
        sc['brier_skill_raw'] = r_(bs_raw)
        sc.update({'origins': len(ics), 'ic': r_(ics.mean()) if len(ics) else None,
                   'ic_t': r_(ics.mean() / (ics.std(ddof=1) / math.sqrt(len(ics)))) if len(ics) > 2 and ics.std() > 0 else None,
                   'ic_momentum': r_(icm.mean()) if len(icm) else None, 'brier_skill': r_(bs), 'n': nb,
                   'best_minus_worst': r_(np.mean(ls)) if ls else None, 'best_minus_worst_momentum': r_(np.mean(lsm)) if lsm else None,
                   'hit_best_minus_worst': r_(np.mean(np.array(ls) > 0)) if ls else None, 'per_year': h and r_(52 / h * np.mean(ls)) if ls else None,
                   'top': top})
        out[h] = {'F': Fc, 'F_raw': F, 'Pbeat': Pbeat, 'Plead': Plead, 'score': sc, 'coefs': coefs}
    return out


def rotation_summary(days, P, res, names, t):
    rows = []
    for i, k in enumerate(P['ids']):
        row = {'id': k, 'name': names.get(k, k)}
        for h in HORIZONS:
            R = res[h]
            row[f'h{h}'] = {'rel': r_(R['F'][i, t]), 'rel_model': r_(R['F_raw'][i, t]), 'p_beat': r_(R['Pbeat'][i, t]), 'p_lead': r_(R['Plead'][i, t])}
        row['signals'] = {kk: r_(P['raw'][kk][i, t]) for kk in P['raw']}
        row['ranked'] = {kk: r_(P['feat'][kk][i, t], 2) for kk in P['feat']}
        rows.append(row)
    return rows


def sector_fundamentals(public, days, sectors):
    """{field: {fund id: weekly values}}: the site's sector aggregates (rotation-long.json) of the latest calendar quarter
    on file 46 days after it ended. sectors: [(fund id, site sector key)]."""
    p = Path(public) / 'rotation-long.json'
    if not p.exists():
        return None
    D = json.loads(p.read_text(encoding='utf-8'))
    fields = D.get('sun_fields') or D.get('fields') or []
    S = D.get('sectors') or {}
    W = len(days)
    out = {}
    for f in FUND_COLS:
        if f not in fields:
            continue
        j = fields.index(f)
        out[f] = {}
        for etf, s in sectors:
            A = np.full(W, np.nan)
            for row in sorted((S.get(s) or {}).get('p') or [], key=lambda r: r[0]):
                q = row[0]
                y, qq = int(q[2:6]), int(q[-1])
                end = dt.date(y + (qq == 4), (3 * qq) % 12 + 1, 1) - dt.timedelta(days=1)
                known = np.datetime64(end + dt.timedelta(days=FUND_LAG_DAYS))
                v = row[j] if j < len(row) else None
                if fin(v):
                    A[days >= known] = v
            out[f][etf] = A
    return out or None


# ------------------------------------------------------------------ 5. spreads
def spread_series(days, C, M):
    out = []
    for sid, a, b, name in RATIOS:
        if C.get(a) is None or C.get(b) is None:
            continue
        with np.errstate(divide='ignore', invalid='ignore'):
            x = np.log(C[a] / C[b])
        out.append((sid, name, x, 'log'))
    for sid, fid, name in RATE_SPREADS:
        if M.get(fid) is not None:
            out.append((sid, name, M[fid], 'level'))
    return out


def spread_model(days, x, kind, today_idx):
    W = len(days)
    yrs = years_of(days)
    res = {}
    for h in HORIZONS:
        y = np.full(W, np.nan)
        y[:W - h] = x[h:] - x[:W - h]
        m13 = np.full(W, np.nan)
        m13[13:] = x[13:] - x[:-13]
        end = np.arange(W) + h
        valid = np.isfinite(y) & np.isfinite(x) & np.isfinite(m13)
        fc = {k: np.full(W, np.nan) for k in ('rw', 'ou', 'trend')}
        half = np.full(W, np.nan)
        resq = {}
        first = int(yrs[np.argmax(np.isfinite(x))]) + 4
        for Y in range(first, int(yrs[-1]) + 1):
            tr = train_mask(days, end, valid, Y)
            if tr.sum() < MIN_TRAIN:
                continue
            te = (yrs == Y) & np.isfinite(x) & np.isfinite(m13)
            # AR(1) of the weekly level on the weeks before the year: x(t+1) = c + φ x(t)
            idx = np.where(np.isfinite(x[:-1]) & np.isfinite(x[1:]) & (days[1:] < np.datetime64(f'{Y}-01-01')))[0]
            if len(idx) < MIN_TRAIN:
                continue
            x0, x1 = x[idx], x[idx + 1]
            phi = float(np.cov(x0, x1)[0, 1] / np.var(x0, ddof=1))
            phi = min(max(phi, -0.99), 0.9995)
            mu = float((x1.mean() - phi * x0.mean()) / (1 - phi))
            fc['rw'][te] = 0.0
            fc['ou'][te] = (mu - x[te]) * (1 - phi ** h)
            b = ols(m13[tr][:, None], y[tr])
            fc['trend'][te] = predict(b, m13[te][:, None])
            half[te] = math.log(0.5) / math.log(phi) if 0 < phi < 1 else np.nan
            for k in fc:
                f_tr = {'rw': np.zeros(tr.sum()), 'ou': (mu - x[tr]) * (1 - phi ** h), 'trend': predict(b, m13[tr][:, None])}[k]
                e = y[tr] - f_tr
                resq.setdefault(Y, {})[k] = np.quantile(e, [0.1, 0.9]).tolist()
        sel = (yrs >= SPREAD_SELECT[0]) & (yrs <= SPREAD_SELECT[1])
        rep = yrs > SPREAD_SELECT[1]
        mse = lambda k, m: float(np.nanmean((y[m] - fc[k][m]) ** 2))   # noqa: E731
        ok = lambda m: m & np.isfinite(y) & np.isfinite(fc['ou']) & np.isfinite(fc['trend'])  # noqa: E731
        s_sel, s_rep = ok(sel), ok(rep)
        chosen = 'rw'
        if s_sel.sum() >= 104:
            base = mse('rw', s_sel)
            gains = {k: 1 - mse(k, s_sel) / base for k in ('ou', 'trend')}
            k_best = max(gains, key=gains.get)
            chosen = k_best if gains[k_best] > 0.01 else 'rw'     # 1% better than a random walk, fixed in advance
        # published: the chosen model only as far as it has worked before; range: errors in units of the spread's own
        # recent volatility (the last 26 weekly changes), so it widens when the spread is moving more
        Fc, beta, errs = shrink_walk(days, fc[chosen], y, h)
        dx = np.full(W, np.nan)
        dx[1:] = x[1:] - x[:-1]
        sdh = np.sqrt(back_mean(dx * dx, 26) * h)
        lo, hi = np.full(W, np.nan), np.full(W, np.nan)
        for Y in sorted(beta):
            known = train_mask(days, end, np.isfinite(y) & np.isfinite(Fc) & np.isfinite(sdh), Y) & (yrs < Y)
            z = (y[known] - Fc[known]) / sdh[known]
            z = z[np.isfinite(z)]
            if len(z) < 50:
                continue
            q = np.quantile(z, [0.1, 0.9])
            te = (yrs == Y) & np.isfinite(Fc) & np.isfinite(sdh)
            lo[te], hi[te] = Fc[te] + q[0] * sdh[te], Fc[te] + q[1] * sdh[te]
        score = {'h': h, 'chosen': chosen, 'n': int(s_rep.sum()), 'independent': int(s_rep.sum() // h), 'beta_now': r_(beta.get(int(yrs[-1])))}
        if s_rep.sum() >= 52:
            base = mse('rw', s_rep)
            score.update({f'r2_{k}': r_(1 - mse(k, s_rep) / base) for k in ('ou', 'trend')})
            okp = s_rep & np.isfinite(Fc)
            score['r2_published'] = r_(1 - float(np.mean((y[okp] - Fc[okp]) ** 2)) / float(np.mean(y[okp] ** 2))) if okp.sum() >= 52 else None
            okq = s_rep & np.isfinite(lo)
            score['coverage80'] = r_(((y[okq] >= lo[okq]) & (y[okq] <= hi[okq])).mean()) if okq.sum() else None
        t = today_idx
        now = {'forecast': r_(Fc[t], 5), 'range': [r_(lo[t], 5), r_(hi[t], 5)] if fin(lo[t]) else None,
               'ou': r_(fc['ou'][t], 5), 'trend': r_(fc['trend'][t], 5), 'half_life_weeks': r_(half[t], 1)}
        res[h] = {'score': score, 'now': now, 'fc': Fc}
    return res


def spreads_block(days, C, M, today_idx):
    out = []
    t = today_idx
    for sid, name, x, kind in spread_series(days, C, M):
        if np.isfinite(x).sum() < MIN_TRAIN * 2 or not fin(x[t]):
            continue
        res = spread_model(days, x, kind, t)
        win = x[max(0, t - 155):t + 1]
        win = win[np.isfinite(win)]
        z = (x[t] - win.mean()) / win.std() if len(win) > 50 and win.std() > 0 else None
        k0 = max(0, t - 520)
        hist = [r_(v, 4) for v in x[k0:t + 1]]
        out.append({'id': sid, 'name': name, 'kind': kind, 'now': r_(x[t], 4), 'z_3y': r_(z, 2),
                    'history': {'start': str(days[k0]), 'x': hist},
                    **{f'h{h}': {**res[h]['now'], **res[h]['score']} for h in HORIZONS}, '_x': x})
    return out


# ------------------------------------------------------------------ 6. the market (combination forecast)
def market_predictors(days, C, M, vrp_spy, cash):
    W = len(days)
    spy = C['SPY']
    r = log_ret(spy)
    ex = r - cash
    baa = M.get('BAA10Y', np.full(W, np.nan))
    d13 = np.full(W, np.nan)
    d13[13:] = baa[13:] - baa[:-13]
    vix = M.get('VIXCLS', np.full(W, np.nan))
    return {'vrp': vrp_spy if vrp_spy is not None else np.full(W, np.nan), 'curve': M.get('T10Y3M', np.full(W, np.nan)),
            'credit': baa, 'credit_13w': d13, 'vix': np.log(vix), 'momentum_52w': back_sum(ex, 52),
            'conditions': M.get('NFCI', np.full(W, np.nan)), 'inflation': M.get('infl', np.full(W, np.nan))}


PREDICTOR_NAMES = {'vrp': 'Variance risk premium (VIX² − HAR forecast)', 'curve': 'Yield curve, 10-year − 3-month',
                   'credit': 'Credit spread, Baa − 10-year', 'credit_13w': 'Credit spread, 13-week change', 'vix': 'VIX (log)',
                   'momentum_52w': 'SPY over cash, last 52 weeks', 'conditions': 'Chicago Fed financial conditions',
                   'inflation': 'CPI inflation, past year (as published)'}


def market_model(days, C, M, cash, vrp_spy, F4, today_idx):
    W = len(days)
    yrs = years_of(days)
    r = log_ret(C['SPY'])
    ex = r - cash
    preds = market_predictors(days, C, M, vrp_spy, cash)
    out = {'predictors': [], 'h': {}}
    t = today_idx
    for h in (13, 52):
        y = fwd_sum(ex, h)
        cash_h = fwd_sum(cash, h)
        end = np.arange(W) + h
        Fk = {k: np.full(W, np.nan) for k in preds}
        Fhm = np.full(W, np.nan)
        res_by_year, base_up = {}, {}
        for Y in range(1997, int(yrs[-1]) + 1):
            valid_y = np.isfinite(y)
            tr0 = train_mask(days, end, valid_y, Y)
            if tr0.sum() < MIN_TRAIN:
                continue
            te = yrs == Y
            Fhm[te] = y[tr0].mean()
            base_up[Y] = float(((y[tr0] + cash_h[tr0]) > 0).mean()) if np.isfinite(cash_h[tr0]).all() else float((y[tr0] > 0).mean())
            for k, x in preds.items():
                tr = tr0 & np.isfinite(x)
                if tr.sum() < MIN_TRAIN:
                    continue
                m = ols(x[tr][:, None], y[tr])
                ok = te & np.isfinite(x)
                Fk[k][ok] = predict(m, x[ok][:, None])
        stack = np.vstack([Fk[k] for k in preds])
        n_av = np.isfinite(stack).sum(0)
        comb = np.where(n_av >= 3, np.nanmean(np.where(np.isfinite(stack), stack, np.nan), 0), np.nan)
        # the published forecast: the past average plus the combination only as far as it has beaten the average before
        Fc, beta, errs = shrink_walk(days, comb, y, h, base=Fhm)
        Pup, P0 = np.full(W, np.nan), np.full(W, np.nan)
        lo, hi = np.full(W, np.nan), np.full(W, np.nan)
        sig = np.sqrt(h * F4) if F4 is not None else np.full(W, np.nan)
        ch = np.where(np.isfinite(cash_h), cash_h, cash * h)
        for Y in sorted(errs):
            e = errs[Y]
            te = np.where((yrs == Y) & np.isfinite(Fc))[0]
            if e is None or not len(e):
                continue
            # the errors in units of the volatility forecast at their origins, for the range
            known = train_mask(days, end, np.isfinite(y) & np.isfinite(Fc) & np.isfinite(sig), Y) & (yrs < Y)
            z = (y[known] - (Fhm[known] + beta.get(int(Y), 0.0) * (comb[known] - Fhm[known]))) / sig[known]
            z = z[np.isfinite(z)]
            q = np.quantile(z, [0.1, 0.9]) if len(z) >= 50 else None
            e0 = y[known] - Fhm[known]                       # the benchmark's errors on the same weeks: like for like
            e0 = e0[np.isfinite(e0)]
            for tt in te:
                Pup[tt] = float(((Fc[tt] + e + ch[tt]) > 0).mean())
                P0[tt] = float(((Fhm[tt] + e0 + ch[tt]) > 0).mean()) if len(e0) else base_up.get(int(Y), np.nan)
                if q is not None and fin(sig[tt]):
                    lo[tt], hi[tt] = Fc[tt] + q[0] * sig[tt], Fc[tt] + q[1] * sig[tt]
        test = yrs >= FIRST_TEST
        ym = np.where(test, y, np.nan)
        sc = {'h': h, 'n': int((test & np.isfinite(y) & np.isfinite(comb)).sum()), 'beta_now': r_(beta.get(int(yrs[-1]))),
              'beta_by_year': {str(k): r_(v, 3) for k, v in beta.items() if k >= FIRST_TEST}}
        sc['independent'] = sc['n'] // h
        sc['r2_published'] = r_(oos_r2(ym, Fc, Fhm))
        sc['r2_combination'] = r_(oos_r2(ym, comb, Fhm))
        sc['r2_combination_ct'] = r_(oos_r2(ym, np.maximum(comb, 0), Fhm))
        sc['r2_each'] = {k: r_(oos_r2(ym, Fk[k], Fhm)) for k in preds}
        up = np.where(np.isfinite(y) & np.isfinite(cash_h), ((y + cash_h) > 0).astype(float), np.nan)
        bs, nb = brier_skill(np.where(test, Pup, np.nan), up, np.where(test, P0, np.nan))
        sc['up_brier_skill'] = r_(bs)
        okc = test & np.isfinite(lo) & np.isfinite(y)
        sc['coverage80'] = r_(((y[okc] >= lo[okc]) & (y[okc] <= hi[okc])).mean()) if okc.sum() else None
        out['h'][h] = {'score': sc, 'now': {'excess': r_(Fc[t]), 'combination': r_(comb[t]), 'p_up': r_(Pup[t]), 'base_up': r_(P0[t]),
                                             'range': [r_(lo[t]), r_(hi[t])], 'history_mean': r_(Fhm[t]),
                                             'each': {k: r_(Fk[k][t]) for k in preds}}}
    out['predictors'] = [{'id': k, 'name': PREDICTOR_NAMES[k], 'now': r_(preds[k][t])} for k in preds]
    return out


# ------------------------------------------------------------------ the indices' fundamentals now (members, SEC figures)
def index_fundamentals(members_path, public):
    """For each of the six indices: its members on the site with a market value, their combined trailing net income and
    revenue (SEC figures, rank/), the earnings yield Σ net income ÷ Σ market value, and the share of members covered.
    Today's members only: descriptive, not a model input (no history of membership outside the S&P 500 and the Dow)."""
    try:
        mem = json.loads(Path(members_path).read_text(encoding='utf-8'))
        meta = json.loads((Path(public) / 'rank' / 'meta.json').read_text(encoding='utf-8'))
        cap = json.loads((Path(public) / 'rank' / 'm-cap.json').read_text(encoding='utf-8'))['rows']
        ni = json.loads((Path(public) / 'rank' / 'q-ni.json').read_text(encoding='utf-8'))['rows']
        rev = json.loads((Path(public) / 'rank' / 'q-rev.json').read_text(encoding='utf-8'))['rows']
    except (OSError, ValueError, KeyError, TypeError):
        return None
    tick = [c[0] for c in meta.get('cos') or []]
    pos = {t: i for i, t in enumerate(tick)}

    def last(row, k=1):
        vals = [v for v in (row or []) if fin(v)]
        return vals[-k:] if len(vals) >= k else None

    def ttm(row, back=0):
        if not row:
            return None
        xs = list(row)
        while xs and not fin(xs[-1]):
            xs.pop()
        if back:
            xs = xs[:-back] if len(xs) > back else []
        q = xs[-4:]
        return sum(q) if len(q) == 4 and all(fin(v) for v in q) else None
    out = {}
    for etf, key in INDEX_MEMBERS.items():
        names = [t for t, r in (mem.get('rows') or {}).items() if key in (r.get('now') or [])]
        n_all = (mem.get('indexes') or {}).get(key, {}).get('n') or len(names)
        caps, nis, nis0, revs, revs0, n, losers = 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0
        for tkr in names:
            i = pos.get(tkr)
            if i is None or i >= len(cap) or i >= len(ni):
                continue
            c = last(cap[i])
            a, a0 = ttm(ni[i]), ttm(ni[i], 4)
            b, b0 = ttm(rev[i]) if i < len(rev) else None, ttm(rev[i], 4) if i < len(rev) else None
            if not c or a is None:
                continue
            n += 1
            losers += a < 0
            caps += c[0]
            nis += a
            if a0 is not None and b is not None and b0 is not None:
                nis0 += a0
                revs += b
                revs0 += b0
        out[etf] = {'members': n_all, 'covered': n, 'earnings_yield': r_(nis / caps) if caps > 0 else None,      # both in $ millions
                    'earnings_growth': r_(nis / nis0 - 1) if nis0 > 0 and revs0 > 0 and nis0 / revs0 >= 0.02 else None,   # not on a tiny base
                    'revenue_growth': r_(revs / revs0 - 1) if revs0 > 0 else None, 'loss_share': r_(losers / n) if n else None}
    return out


# ------------------------------------------------------------------ ledger
def closed_week(days, today):
    """The last Friday whose week has closed (Saturday onward), and its index."""
    lim = np.datetime64(today) - np.timedelta64(1, 'D')
    k = int(np.searchsorted(days, lim, side='right') - 1)
    return max(k, 0)


def ledger_update(book, days, t, C, cash, vol_rows, idx_res, idx_P, sec_res, sec_P, spreads, mk, regime):
    asof = str(days[t])
    meta = {'model': f'market_models v{VERSION}'}
    W = len(days)
    for row in vol_rows:
        for h in HORIZONS:
            v = row.get(f'h{h}')
            if v and fin(v.get('vol')):
                FB.freeze(book, 'vol', f'{row["id"]}:{h}:{asof}', asof, {'vol': v['vol'], 'lo': v['range'][0], 'hi': v['range'][1]}, meta=meta)
    for fam, P, res in (('index', idx_P, idx_res), ('sector', sec_P, sec_res)):
        if not P:
            continue
        for i, k in enumerate(P['ids']):
            for h in HORIZONS:
                p, f = res[h]['Pbeat'][i, t], res[h]['F'][i, t]
                if fin(p):
                    FB.freeze(book, fam, f'{k}:{h}:{asof}', asof, {'p': r_(p), 'rel': r_(f), 'lead': r_(res[h]['Plead'][i, t])}, meta=meta)
    for s in spreads:
        for h in HORIZONS:
            n_ = s[f'h{h}']
            if fin(n_.get('forecast')):
                FB.freeze(book, 'spread', f'{s["id"]}:{h}:{asof}', asof, {'chg': n_['forecast'], 'lo': (n_.get('range') or [None])[0],
                                                                         'hi': (n_.get('range') or [None, None])[1], 'x': s['now']}, meta=meta)
    for h, b in (mk or {}).get('h', {}).items():
        n_ = b['now']
        if fin(n_.get('p_up')):
            FB.freeze(book, 'market', f'SPY:{h}:{asof}', asof, {'p': n_['p_up'], 'excess': n_['excess'], 'lo': n_['range'][0], 'hi': n_['range'][1]}, meta=meta)
    if regime and fin(regime.get('p_down10_13w')):
        FB.freeze(book, 'regime', f'SPY:13:{asof}', asof, {'p': regime['p_down10_13w'], 'base': regime.get('base_down10_13w'),
                                                           'states': regime.get('now')}, meta=meta)
    # resolve what has an outcome by the closed week t
    ix = {str(d): k for k, d in enumerate(days)}
    r_spy = log_ret(C['SPY'])

    def outcome_sum(r, k0, h):
        if k0 + h > t:
            return None
        s = r[k0 + 1:k0 + h + 1]
        return float(s.sum()) if np.isfinite(s).all() else None
    for fam in ('vol', 'index', 'sector', 'spread', 'market', 'regime'):
        for key, e in FB.entries(book, fam, resolved=False):
            parts = key.split(':')
            h = int(parts[1])
            k0 = ix.get(e['asof'])
            if k0 is None or k0 + h > t:
                continue
            if fam == 'vol':
                c = C.get(parts[0])
                if c is None:
                    continue
                r = log_ret(c)
                s = r[k0 + 1:k0 + h + 1]
                if np.isfinite(s).all():
                    FB.resolve(book, fam, key, {'vol': r_(math.sqrt(52 * float((s ** 2).mean()))), 'ret': r_(math.exp(s.sum()) - 1)})
            elif fam in ('index', 'sector'):
                P = idx_P if fam == 'index' else sec_P
                if not P or parts[0] not in P['ids']:
                    continue
                i = P['ids'].index(parts[0])
                v = outcome_sum(P['rel'][i], k0, h)
                if v is not None:
                    FB.resolve(book, fam, key, {'rel': r_(v), 'y': int(v > 0)})
            elif fam == 'spread':
                s = next((x for x in spreads if x['id'] == parts[0]), None)
                if s is None:
                    continue
                x_now = s['_x'][k0 + h] if k0 + h < W else None
                if fin(x_now) and fin(s['_x'][k0]):
                    FB.resolve(book, fam, key, {'chg': r_(x_now - s['_x'][k0], 5)})
            elif fam in ('market', 'regime'):
                v = outcome_sum(r_spy, k0, h)
                if v is None:
                    continue
                if fam == 'market':
                    cs = outcome_sum(cash, k0, h) or 0.0
                    FB.resolve(book, fam, key, {'excess': r_(v - cs), 'y': int(v > 0)})
                else:
                    FB.resolve(book, fam, key, {'y': int(v <= math.log(0.9)), 'ret': r_(v)})


def ledger_scores(book):
    out = {}
    for fam, pkey in (('index', 'p'), ('sector', 'p'), ('market', 'p'), ('regime', 'p')):
        pairs = [(e['forecast'].get(pkey), e['actual'].get('y')) for _, e in FB.entries(book, fam, resolved=True)
                 if fin(e['forecast'].get(pkey)) and e['actual'] and e['actual'].get('y') is not None]
        out[fam] = {'resolved': len(pairs), 'pending': len(FB.entries(book, fam, resolved=False))}
        if len(pairs) >= 10:
            out[fam].update(FB.score_prob(pairs))
    vr = [(e['forecast'], e['actual']) for _, e in FB.entries(book, 'vol', resolved=True) if e['actual']]
    out['vol'] = {'resolved': len(vr), 'pending': len(FB.entries(book, 'vol', resolved=False))}
    if vr:
        inside = [f['lo'] <= a['ret'] <= f['hi'] for f, a in vr if fin(f.get('lo')) and fin(a.get('ret'))]
        err = [abs(math.log(a['vol'] / f['vol'])) for f, a in vr if fin(a.get('vol')) and a['vol'] > 0 and fin(f.get('vol')) and f['vol'] > 0]
        out['vol'].update({'coverage80': r_(np.mean(inside)) if inside else None, 'log_mae': r_(np.mean(err)) if err else None})
    sp = [(e['forecast'], e['actual']) for _, e in FB.entries(book, 'spread', resolved=True) if e['actual']]
    out['spread'] = {'resolved': len(sp), 'pending': len(FB.entries(book, 'spread', resolved=False))}
    if sp:
        inside = [f['lo'] <= a['chg'] <= f['hi'] for f, a in sp if fin(f.get('lo')) and fin(f.get('hi')) and fin(a.get('chg'))]
        out['spread']['coverage80'] = r_(np.mean(inside)) if inside else None
    return out


# ------------------------------------------------------------------ everything
def build(public, macro_dir, ledger=None, members=None, today=None, verbose=True):
    with warnings.catch_warnings(), np.errstate(all='ignore'):
        warnings.simplefilter('ignore', RuntimeWarning)
        return _build(public, macro_dir, ledger, members, today, verbose)


def _build(public, macro_dir, ledger=None, members=None, today=None, verbose=True):
    t0 = dt.datetime.now()
    today = today or dt.date.today()
    days, C = load_grid(public)
    M = macro_weekly(macro_dir, days)
    cash = cash_weekly(days, M)
    t = closed_week(days, today)
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    # 1 volatility
    vol_rows, vol_scores, vrp = vol_model(days, C, M, t)
    F4 = next((r_['_F4'] for r_ in vol_rows if r_['id'] == 'SPY' and '_F4' in r_), None)
    log(f'market models: volatility for {len(vol_rows)} funds')
    # 3 regime (before the rotation models, which use its stressed probability)
    regime, reg_arrays = regime_model(days, C, M, t)
    log('market models: regime ' + ('ok' if regime else 'skipped (no VIX or credit spread)'))
    macro = macro_features(days, M, vrp.get('SPY'), reg_arrays['probs'] if reg_arrays else None)
    # 2 indices
    idx_names = dict(INDICES)
    idx_P = rotation_panel(days, C, [k for k, _ in INDICES], None)
    idx_res = rotation_model(days, idx_P, macro, None, top=1) if len(idx_P['ids']) >= 3 else None
    # 4 sectors
    sec_ids = [s[0] for s in SECTORS]
    fund = sector_fundamentals(public, days, [(s[0], s[1]) for s in SECTORS])
    sec_P = rotation_panel(days, C, sec_ids, 'SPY', fund=fund)
    sec_res = rotation_model(days, sec_P, macro, None, top=3) if len(sec_P['ids']) >= 5 else None
    log('market models: indices and sectors')
    # 5 spreads
    spreads = spreads_block(days, C, M, t)
    # 6 market
    mk = market_model(days, C, M, cash, vrp.get('SPY'), F4, t) if 'SPY' in C else None
    log('market models: spreads and the market')
    fundamentals = index_fundamentals(members, public) if members else None
    doc = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'version': VERSION, 'asof': str(days[t]),
           'first_test': FIRST_TEST, 'horizons': list(HORIZONS),
           'vol': {'assets': [{k: v for k, v in r.items() if not k.startswith('_')} for r in vol_rows], 'scores': vol_scores,
                   'vix': r_(M['VIXCLS'][t], 2) if 'VIXCLS' in M else None,
                   'vix_term': r_(M['VIXCLS'][t] / M['VXVCLS'][t], 3) if 'VIXCLS' in M and 'VXVCLS' in M else None},
           'regime': regime,
           'indices': {'rows': rotation_summary(days, idx_P, idx_res, idx_names, t) if idx_res else [],
                       'scores': {h: idx_res[h]['score'] for h in HORIZONS} if idx_res else {},
                       'coefs': idx_res[13]['coefs'] if idx_res else None, 'fundamentals': fundamentals,
                       'conditions': {k: r_(v[t]) for k, v in macro.items()}},
           'sectors': {'rows': rotation_summary(days, sec_P, sec_res, {s[0]: s[2] for s in SECTORS}, t) if sec_res else [],
                       'scores': {h: sec_res[h]['score'] for h in HORIZONS} if sec_res else {},
                       'coefs': sec_res[13]['coefs'] if sec_res else None, 'fundamentals_from': 'rotation-long.json' if fund else None},
           'spreads': [{k: v for k, v in s.items() if not k.startswith('_')} for s in spreads],
           'market': {'predictors': mk['predictors'], 'h': {h: {k: v for k, v in b.items() if not k.startswith('_')} for h, b in mk['h'].items()}} if mk else None,
           'note': __doc__.split('\n\n')[1]}
    if regime and reg_arrays:                                # how each index and sector did by state (out of sample)
        lab, have = reg_arrays['lab'], reg_arrays['have']
        sel = years_of(days) >= FIRST_TEST
        cond = []
        for P, kind in ((idx_P, 'index'), (sec_P, 'sector')):
            for i, k in enumerate(P['ids']):
                y = P['fwd'][13][i]
                row = {'id': k, 'kind': kind}
                for s in range(3):
                    m = sel & have & (lab == s) & np.isfinite(y)
                    row[STATE_NAMES[s]] = r_(y[m].mean()) if m.sum() >= 26 else None
                cond.append(row)
        regime['leaders_by_state'] = cond
    if ledger:
        book = FB.load(ledger)
        ledger_update(book, days, t, C, cash, vol_rows, idx_res, idx_P, sec_res, sec_P, spreads, mk, regime)
        FB.save(ledger, book)
        doc['ledger'] = ledger_scores(book)
    doc['seconds'] = round((dt.datetime.now() - t0).total_seconds(), 1)
    (Path(public) / 'market-models.json').write_text(json.dumps(clean(doc), separators=(',', ':')), encoding='utf-8')
    log(f'market models: written in {doc["seconds"]}s')
    return doc


def clean(x):
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return float(x) if math.isfinite(x) else None
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--public', required=True)
    ap.add_argument('--macro', required=True)
    ap.add_argument('--ledger', default=None)
    ap.add_argument('--members', default=None)
    a = ap.parse_args()
    build(a.public, a.macro, a.ledger, a.members)


if __name__ == '__main__':
    main()
