"""Macro data for the rotation charts: the "long pendulum" (economic data -> 10-Q -> market data).

  fetch   FRED series (St. Louis Fed, public CSV downloads, no key) into <root>/cache/macro/<ID>.csv; a file younger than
          20 hours is not fetched again. Runs in .github/workflows/rotation-history.yml.
  build   public/macro.json:
            weekly   one Friday grid (the RRG grid, since 2000): every series as it was KNOWN that Friday — each
                     observation is placed at the day it was published (period end + a publication lag), so nothing
                     uses a figure before its release; plus derived features (13-week changes, year-on-year rates)
            monthly  month-end values on the same rule, since 1995
            clock    the macro (investment) clock month by month: growth and inflation composites (z-scores of several
                     series, each standardised with data up to that month only), their 6-month momentum and the phase;
                     a walk-forward forecast of next month's point with an 80% range and the error of every past one

  Caveat: FRED serves today's vintage, so revised series (payrolls, industrial production, retail sales, PCE) carry
  later revisions; the publication lag is respected, the revision is not. Market series (yields, spreads, VIX,
  the dollar, oil) are never revised.

    python app/macro_history.py fetch --root hist
    python app/macro_history.py build --root hist
"""
import argparse
import csv
import datetime as dt
import io
import json
import math
import os
import time
import urllib.request
from pathlib import Path

import numpy as np

FRED = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}&cosd=1990-01-01'
FRED_API = ('https://api.stlouisfed.org/fred/series/observations?series_id={id}&api_key={key}&file_type=json'
            '&observation_start=1990-01-01')
GRID0 = dt.date(2000, 1, 7)                      # the RRG grid (rotation_history.START)
# id: (label, unit, frequency, publication lag in days after the period ends, group)
SERIES = {
    'DGS10': ('10-year Treasury yield', '%', 'd', 1, 'Rates'),
    'DGS2': ('2-year Treasury yield', '%', 'd', 1, 'Rates'),
    'DGS3MO': ('3-month Treasury bill', '%', 'd', 1, 'Rates'),
    'T10Y3M': ('Yield curve: 10-year minus 3-month', 'pts', 'd', 1, 'Rates'),
    'T10Y2Y': ('Yield curve: 10-year minus 2-year', 'pts', 'd', 1, 'Rates'),
    'DFII10': ('10-year real yield (TIPS)', '%', 'd', 1, 'Rates'),
    'T10YIE': ('10-year breakeven inflation', '%', 'd', 1, 'Inflation'),
    'FEDFUNDS': ('Fed funds rate', '%', 'm', 1, 'Rates'),
    'BAA10Y': ('Credit spread: Moody\'s Baa minus 10-year', 'pts', 'd', 1, 'Risk'),
    'VIXCLS': ('VIX (S&P 500 implied volatility)', '', 'd', 1, 'Risk'),
    'NFCI': ('Chicago Fed financial conditions (+ = tighter)', '', 'w', 5, 'Risk'),
    'STLFSI4': ('St. Louis Fed financial stress', '', 'w', 6, 'Risk'),
    'DTWEXBGS': ('US dollar, broad trade-weighted', 'index', 'd', 1, 'Markets'),
    'DCOILWTICO': ('Crude oil, WTI', '$', 'd', 1, 'Markets'),
    'WALCL': ('Fed balance sheet (total assets)', '$m', 'w', 1, 'Rates'),
    'ICSA': ('Initial jobless claims', '', 'w', 5, 'Growth'),
    'PAYEMS': ('Nonfarm payrolls', 'k', 'm', 8, 'Growth'),
    'UNRATE': ('Unemployment rate', '%', 'm', 8, 'Growth'),
    'INDPRO': ('Industrial production', 'index', 'm', 17, 'Growth'),
    'RSAFS': ('Retail sales', '$m', 'm', 17, 'Growth'),
    'HOUST': ('Housing starts', 'k', 'm', 19, 'Growth'),
    'UMCSENT': ('Consumer sentiment (Michigan)', '', 'm', 1, 'Growth'),
    'CPIAUCSL': ('Consumer prices (CPI)', 'index', 'm', 15, 'Inflation'),
    'CPILFESL': ('Core CPI (ex food and energy)', 'index', 'm', 15, 'Inflation'),
    'PCEPILFE': ('Core PCE prices', 'index', 'm', 30, 'Inflation'),
    'M2SL': ('Money supply M2', '$bn', 'm', 26, 'Rates'),
}
# features on the weekly grid: key -> (label, unit, how)
FEATURES = [
    ('y10', '10-year yield', '%', ('lvl', 'DGS10')),
    ('y2', '2-year yield', '%', ('lvl', 'DGS2')),
    ('curve', 'Yield curve 10y − 3m', 'pts', ('lvl', 'T10Y3M')),
    ('curve2', 'Yield curve 10y − 2y', 'pts', ('lvl', 'T10Y2Y')),
    ('real10', '10-year real yield', '%', ('lvl', 'DFII10')),
    ('bei10', '10-year breakeven inflation', '%', ('lvl', 'T10YIE')),
    ('ff', 'Fed funds rate', '%', ('lvl', 'FEDFUNDS')),
    ('credit', 'Credit spread (Baa − 10y)', 'pts', ('lvl', 'BAA10Y')),
    ('vix', 'VIX', '', ('lvl', 'VIXCLS')),
    ('nfci', 'Financial conditions (NFCI)', '', ('lvl', 'NFCI')),
    ('stress', 'Financial stress (St. Louis)', '', ('lvl', 'STLFSI4')),
    ('dy10', '10-year yield, 13-week change', 'pts', ('chg', 'DGS10', 13)),
    ('dcurve', 'Yield curve, 13-week change', 'pts', ('chg', 'T10Y3M', 13)),
    ('dcredit', 'Credit spread, 13-week change', 'pts', ('chg', 'BAA10Y', 13)),
    ('usd13', 'Dollar, 13-week change', '%', ('pct', 'DTWEXBGS', 13)),
    ('oil13', 'Oil, 13-week change', '%', ('pct', 'DCOILWTICO', 13)),
    ('fedbs', 'Fed balance sheet, year on year', '%', ('pct', 'WALCL', 52)),
    ('claims', 'Jobless claims (4-week average), year on year', '%', ('pct4', 'ICSA', 52)),
    ('payrolls', 'Payrolls, year on year', '%', ('pct', 'PAYEMS', 52)),
    ('unrate', 'Unemployment rate', '%', ('lvl', 'UNRATE')),
    ('sahm', 'Unemployment vs its 12-month low', 'pts', ('sahm', 'UNRATE')),
    ('ip', 'Industrial production, year on year', '%', ('pct', 'INDPRO', 52)),
    ('retail', 'Retail sales, year on year', '%', ('pct', 'RSAFS', 52)),
    ('houst', 'Housing starts, year on year', '%', ('pct', 'HOUST', 52)),
    ('sent', 'Consumer sentiment', '', ('lvl', 'UMCSENT')),
    ('cpi', 'CPI inflation, year on year', '%', ('pct', 'CPIAUCSL', 52)),
    ('core', 'Core CPI inflation, year on year', '%', ('pct', 'CPILFESL', 52)),
    ('pce', 'Core PCE inflation, year on year', '%', ('pct', 'PCEPILFE', 52)),
    ('m2', 'Money supply M2, year on year', '%', ('pct', 'M2SL', 52)),
]
GROWTH = [('payrolls', 1), ('ip', 1), ('retail', 1), ('houst', 1), ('sent', 1), ('claims', -1), ('sahm', -1)]
INFLATION = [('cpi', 1), ('core', 1), ('pce', 1), ('bei10', 1)]
PHASES = ['Recovery (growth ↑, inflation ↓)', 'Overheat (growth ↑, inflation ↑)', 'Stagflation (growth ↓, inflation ↑)',
          'Reflation (growth ↓, inflation ↓)']


# ------------------------------------------------------------------ fetch
def _get(url, timeout):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) FilingFlows/1.0 (public data reader)',
                                               'Accept': 'text/csv,application/json;q=0.9,*/*;q=0.5'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def fetch_one(sid, timeout=25):
    """CSV text for one series: the FRED API when FRED_API_KEY is set (fast, reliable), else the public CSV download."""
    key = os.environ.get('FRED_API_KEY', '').strip()
    if key:
        body = json.loads(_get(FRED_API.format(id=sid, key=key), timeout))
        return 'observation_date,' + sid + '\n' + '\n'.join(f"{o['date']},{o['value']}" for o in body.get('observations', []))
    return _get(FRED.format(id=sid), timeout)


def fetch(root, ids=None, max_age_h=20, pause=0.5, budget_s=300, verbose=True):
    folder = Path(root) / 'cache' / 'macro'
    folder.mkdir(parents=True, exist_ok=True)
    got, failed, t0 = [], [], time.time()
    for sid in ids or SERIES:
        p = folder / f'{sid}.csv'
        if p.exists() and time.time() - p.stat().st_mtime < max_age_h * 3600:
            continue
        if time.time() - t0 > budget_s:
            failed.append(f'{sid}: time budget used up (next run)')
            continue
        for attempt in range(2):
            try:
                body = fetch_one(sid)
                rows = parse_csv(body)
                if len(rows) < 12:
                    raise ValueError(f'only {len(rows)} rows')
                p.write_text(body, encoding='utf-8')
                got.append(sid)
                break
            except Exception as exc:              # keep the old file; the next run tries again
                if attempt == 1:
                    failed.append(f'{sid}: {type(exc).__name__} {str(exc)[:120]}')
                time.sleep(2)
        time.sleep(pause)
    if verbose:
        print(f'macro fetch: {len(got)} updated, {len(failed)} failed in {time.time() - t0:.0f}s', *failed, sep='\n  ', flush=True)
        if os.environ.get('GITHUB_ACTIONS'):
            print(f'::notice title=macro fetch::{len(got)} updated, {len(failed)} failed; ' + ' | '.join(failed)[:900], flush=True)
    return got, failed


def parse_csv(text):
    """[(date, value)] from a FRED CSV (header 'observation_date,ID' or 'DATE,ID'; missing values '.')."""
    out = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2:
            continue
        try:
            d = dt.date.fromisoformat(row[0].strip())
        except ValueError:
            continue
        v = row[1].strip()
        if v in ('', '.', 'NA'):
            continue
        try:
            out.append((d, float(v)))
        except ValueError:
            continue
    return out


# ------------------------------------------------------------------ alignment
def _period_end(d, freq):
    if freq == 'm':
        nxt = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        return nxt - dt.timedelta(days=1)
    if freq == 'q':
        m = 3 * ((d.month - 1) // 3) + 3
        nxt = dt.date(d.year + (m == 12), m % 12 + 1, 1)
        return nxt - dt.timedelta(days=1)
    return d                                      # daily: the date; weekly: FRED dates weeks by their last day


def known_dates(obs, freq, lag):
    """The day each observation became public."""
    return [_period_end(d, freq) + dt.timedelta(days=lag) for d, _ in obs]


def as_of(obs, freq, lag, days):
    """Value known on each day of `days` (sorted dates): the latest observation published on or before it."""
    if not obs:
        return np.full(len(days), np.nan)
    kd = np.array([np.datetime64(d) for d in known_dates(obs, freq, lag)])
    order = np.argsort(kd, kind='stable')
    kd = kd[order]; vals = np.array([v for _, v in obs], float)[order]
    q = np.array([np.datetime64(d) for d in days])
    i = np.searchsorted(kd, q, side='right') - 1
    out = np.where(i >= 0, vals[np.clip(i, 0, None)], np.nan)
    # a series that stopped (or a long gap) should not be carried forward for ever: 400 days at most
    age = (q - kd[np.clip(i, 0, None)]).astype('timedelta64[D]').astype(int)
    return np.where((i >= 0) & (age <= 400), out, np.nan)


def as_of_lagged(obs, freq, lag, days, back_days):
    """The value that was known `back_days` before each day (for year-on-year rates on the as-known basis)."""
    return as_of(obs, freq, lag, [d - dt.timedelta(days=back_days) for d in days])


def load_cache(root):
    folder = Path(root) / 'cache' / 'macro'
    out = {}
    for sid in SERIES:
        p = folder / f'{sid}.csv'
        if p.exists():
            out[sid] = parse_csv(p.read_text(encoding='utf-8'))
    return out


def features(raw, days):
    """{key: array over days} for FEATURES, each on the as-known basis."""
    F = {}
    for key, _, _, how in FEATURES:
        kind, sid = how[0], how[1]
        if sid not in raw:
            continue
        _, _, freq, lag, _ = SERIES[sid]
        obs = raw[sid]
        now = as_of(obs, freq, lag, days)
        if kind == 'lvl':
            F[key] = now
        elif kind == 'chg':
            F[key] = now - as_of_lagged(obs, freq, lag, days, 7 * how[2])
        elif kind == 'pct':
            then = as_of_lagged(obs, freq, lag, days, 7 * how[2] if how[2] != 52 else 365)
            with np.errstate(all='ignore'):
                F[key] = 100 * (now / then - 1)
        elif kind == 'pct4':                      # 4-week average of a weekly series, year on year
            def avg4(shift):
                return np.nanmean(np.stack([as_of_lagged(obs, freq, lag, days, shift + 7 * k) for k in range(4)]), 0)
            with np.errstate(all='ignore'):
                F[key] = 100 * (avg4(0) / avg4(365) - 1)
        elif kind == 'sahm':                      # unemployment minus its low over the past 12 months (as known)
            past = np.stack([as_of_lagged(obs, freq, lag, days, 30 * k) for k in range(13)])
            with np.errstate(all='ignore'):
                F[key] = now - np.nanmin(past, 0)
    return F


def weekly_grid(until):
    n = (until - GRID0).days // 7 + 1
    return [GRID0 + dt.timedelta(days=7 * i) for i in range(n)]


def month_ends(first, until):
    out, y, m = [], first.year, first.month
    while True:
        d = dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)
        if d > until:
            break
        out.append(d)
        y, m = y + (m == 12), m % 12 + 1
    return out


# ------------------------------------------------------------------ the macro clock
def expanding_z(x, min_n=36):
    """z-score of each value against the values up to and including it (no look-ahead)."""
    out = np.full(len(x), np.nan)
    vals = []
    for i, v in enumerate(x):
        if np.isfinite(v):
            vals.append(v)
            if len(vals) >= min_n:
                a = np.array(vals); s = a.std()
                out[i] = (v - a.mean()) / s if s > 0 else 0.0
    return out


def composite(F, parts):
    zs = [sign * expanding_z(F[k]) for k, sign in parts if k in F]
    if not zs:
        return np.full(len(next(iter(F.values()))), np.nan)
    Z = np.stack(zs)
    ok = np.isfinite(Z).sum(0)
    with np.errstate(all='ignore'):
        return np.where(ok >= max(2, len(zs) // 2), np.nansum(Z, 0) / np.maximum(ok, 1), np.nan)


def phase_of(gx, gy):
    if not (np.isfinite(gx) and np.isfinite(gy)):
        return None
    return 0 if gx >= 0 > gy else 1 if gx >= 0 and gy >= 0 else 2 if gy >= 0 else 3


def clock_forecast(X, first_test, min_train=48, ridge=1.0):
    """Walk-forward one-month-ahead forecast of the clock point. X: (T, 4) = growth level, inflation level, growth
    momentum, inflation momentum. Model for each of the two momenta: ridge on the current four coordinates and the last
    change (fit on months whose outcome was known at the origin). 80% range: the empirical 10th-90th percentile of
    past errors (also only those known at the origin). Returns rows [t, gx_next, gy_next, lo_x, hi_x, lo_y, hi_y]."""
    T = len(X)
    dX = np.vstack([np.full((1, 4), np.nan), np.diff(X, axis=0)])
    Z = np.hstack([X, dX[:, 2:4]])                # features at t
    Y = np.vstack([X[1:, 2:4], np.full((1, 2), np.nan)])    # momentum next month
    rows, errs = [], []
    for t in range(first_test, T):
        tr = np.arange(t)                         # outcomes for months < t are known at t (Y[s] = X[s+1], s+1 <= t)
        ok = tr[np.isfinite(Z[tr]).all(1) & np.isfinite(Y[tr]).all(1)]
        if len(ok) < min_train or not np.isfinite(Z[t]).all():
            continue
        A = np.hstack([Z[ok], np.ones((len(ok), 1))]); mu = A.mean(0); mu[-1] = 0; sd = A.std(0); sd[-1] = 1; sd[sd == 0] = 1
        An = (A - mu) / sd
        W = np.linalg.solve(An.T @ An + ridge * np.eye(An.shape[1]), An.T @ Y[ok])
        z = (np.append(Z[t], 1) - mu) / sd
        yhat = z @ W
        past = np.array([e for e in errs if e[0] < t]).reshape(-1, 3)
        if len(past) >= 24:
            lo = np.percentile(past[:, 1:], 10, axis=0); hi = np.percentile(past[:, 1:], 90, axis=0)
        else:
            res = Y[ok] - An @ W
            lo = np.percentile(res, 10, axis=0); hi = np.percentile(res, 90, axis=0)
        rows.append([t, float(yhat[0]), float(yhat[1]), float(yhat[0] + lo[0]), float(yhat[0] + hi[0]),
                     float(yhat[1] + lo[1]), float(yhat[1] + hi[1])])
        if t + 1 < T and np.isfinite(X[t + 1, 2:4]).all():
            errs.append((t + 1, X[t + 1, 2] - yhat[0], X[t + 1, 3] - yhat[1]))    # known from month t+1 on
    return rows


def clock(F, months, first_show='2010-01'):
    g = composite(F, GROWTH); i_ = composite(F, INFLATION)
    gm = g - np.concatenate([np.full(6, np.nan), g[:-6]]); im = i_ - np.concatenate([np.full(6, np.nan), i_[:-6]])
    X = np.stack([g, i_, gm, im], 1)
    ms = [d.strftime('%Y-%m') for d in months]
    first_test = next((k for k, m in enumerate(ms) if m >= '2005-01'), 0)
    fc = clock_forecast(X, first_test)
    # score: point error, direction of the step, inside the 80% box
    hits, inside, err = [], [], []
    for t, nx, ny, lx, hx, ly, hy in fc:
        if t + 1 >= len(X) or not np.isfinite(X[t + 1, 2:4]).all():
            continue
        ax, ay = X[t + 1, 2], X[t + 1, 3]
        err.append(math.hypot(ax - nx, ay - ny))
        inside.append(lx <= ax <= hx and ly <= ay <= hy)
        sx, sy = ax - X[t, 2], ay - X[t, 3]; fx, fy = nx - X[t, 2], ny - X[t, 3]
        if math.hypot(sx, sy) > 0 and math.hypot(fx, fy) > 0:
            hits.append(sx * fx + sy * fy > 0)
    persist = [math.hypot(X[t + 1, 2] - X[t, 2], X[t + 1, 3] - X[t, 3]) for t, *_ in fc
               if t + 1 < len(X) and np.isfinite(X[t:t + 2, 2:4]).all()]
    k0 = next((k for k, m in enumerate(ms) if m >= first_show), 0)
    fc_show = [[r[0] - k0] + [round(v, 3) for v in r[1:]] for r in fc if r[0] >= k0]
    return {'months': ms[k0:], 'growth': _r(g[k0:]), 'inflation': _r(i_[k0:]), 'growth_mom': _r(gm[k0:]), 'inflation_mom': _r(im[k0:]),
            'phase': [phase_of(a, b) for a, b in zip(gm[k0:], im[k0:])], 'phases': PHASES,
            'forecast': fc_show, 'forecast_fields': ['month', 'growth_mom_next', 'inflation_mom_next', 'lo_x', 'hi_x', 'lo_y', 'hi_y'],
            'score': {'months': len(err), 'mean_point_error': _f(np.mean(err)) if err else None,
                      'standing_still_error': _f(np.mean(persist)) if persist else None,
                      'step_direction_hit': _f(np.mean(hits)) if hits else None, 'inside80': _f(np.mean(inside)) if inside else None,
                      'from': ms[fc[0][0]] if fc else None},
            'growth_parts': [k for k, _ in GROWTH], 'inflation_parts': [k for k, _ in INFLATION]}


def _r(a, d=3):
    return [None if not np.isfinite(v) else round(float(v), d) for v in a]


def _f(v):
    return None if v is None or not np.isfinite(v) else round(float(v), 4)


# ------------------------------------------------------------------ build
def build(root, today=None, verbose=True):
    root = Path(root); raw = load_cache(root)
    if not raw:
        if verbose:
            print('macro build: no cached series; skipped', flush=True)
        return None
    today = today or dt.date.today()
    weeks = weekly_grid(today - dt.timedelta(days=(today.weekday() - 4) % 7))
    Fw = features(raw, weeks)
    months = month_ends(dt.date(1995, 1, 1), today)
    Fm = features(raw, months)
    w0 = next(i for i, d in enumerate(weeks) if d >= dt.date(2009, 1, 1))
    doc = {'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), 'source': 'FRED, Federal Reserve Bank of St. Louis',
           'series': {sid: {'label': s[0], 'unit': s[1], 'freq': s[2], 'lag_days': s[3], 'group': s[4],
                            'first': str(raw[sid][0][0]) if sid in raw and raw[sid] else None,
                            'last': str(raw[sid][-1][0]) if sid in raw and raw[sid] else None} for sid, s in SERIES.items()},
           'features': [{'key': k, 'label': l, 'unit': u, 'series': h[1], 'group': SERIES[h[1]][4]} for k, l, u, h in FEATURES if k in Fw],
           'weekly': {'start': str(weeks[w0]), 'grid_index0': w0, 'data': {k: _r(v[w0:]) for k, v in Fw.items()}},
           'monthly': {'months': [d.strftime('%Y-%m') for d in months], 'data': {k: _r(v) for k, v in Fm.items()}},
           'clock': clock(Fm, months),
           'note': ('Every value is placed at the day it was published (period end plus the usual release lag), so a chart '
                    'or a model reading a week sees only what was public that week. FRED serves the latest vintage: '
                    'revised series (payrolls, industrial production, retail sales, PCE) include later revisions.')}
    out = root / 'public' / 'macro.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    if verbose:
        sc = doc['clock']['score']
        print(f'macro.json: {len(doc["features"])} features, {len(Fw[next(iter(Fw))]) - w0} weeks since {doc["weekly"]["start"]}; '
              f'clock {doc["clock"]["months"][0]}..{doc["clock"]["months"][-1]} score {sc}', flush=True)
    return doc


def weekly_matrix(root_or_doc, keys=None):
    """(grid_index0, {key: np.array}) from macro.json, aligned to the RRG weekly grid (index 0 = 2000-01-07)."""
    doc = root_or_doc if isinstance(root_or_doc, dict) else json.loads(Path(root_or_doc).read_text(encoding='utf-8'))
    w = doc['weekly']
    return w['grid_index0'], {k: np.array([np.nan if v is None else v for v in a], float) for k, a in w['data'].items()
                              if keys is None or k in keys}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['fetch', 'build'])
    ap.add_argument('--root', default='hist')
    a = ap.parse_args()
    if a.cmd == 'fetch':
        fetch(a.root)
    else:
        build(a.root)


if __name__ == '__main__':
    main()
