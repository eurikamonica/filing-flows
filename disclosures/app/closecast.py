"""Close forecast (the hub's Close forecast tab): where an asset closes today, on each options expiry this week, at the
end of this week, in two weeks, at the end of the month and at the end of the quarter — a distribution for each, pooled
from every source the site reads, each source first scaled so that its ranges held as often as they claim on its own
history.

Sources: each a distribution of the log return from the price now to the target's close (any may be missing):
  options     the options' view at the target (CBOE delayed quotes, about 15 minutes late): P(close > K) at each strike
              of the target's expiry, else the next one, from its smile: N(d2) at the strike's IV less vega × the smile's
              slope (app/ladders.py digital). Risk-neutral: it carries the market's price of risk, not a view of drift.
  markets     Kalshi and Polymarket ladders on the close of that very date (app/consensus.py: bid/ask midpoints where the
              book is tight, the strikes fitted to fall monotonically); an index ladder in points is read at today's
              index/ETF ratio. The tails beyond the last strikes: the log-normal fitted to the ladder.
  implied     the volatility indices' term structure (VIX1D, VIX9D, VIX, VIX3M, VIX6M for the S&P 500; VXN, VXD, RVX for
              the Nasdaq-100, the Dow and the Russell 2000): a log-normal whose total variance is interpolated to the
              target's calendar time (today's close: VIX1D over the minutes left).
  analogs     today: the 60 days whose move by this hour was nearest to today's, their move from this hour to the close
              (app/intraday.py's hourly history); later dates: the 200 days whose volatility against its past year, 5-day
              and 20-day trends were nearest to the last close's, their returns over as many sessions, rescaled to today's
              volatility (EWMA), plus the rest of today from the intraday analogs.
  moves       Move odds (app/moves.py): the days whose one-day move was within 2.5 percentile points of the last
              session's, and their returns over as many sessions (the band widened until 40 days are in it).
  regime      for an asset at its highs, at a low or in a range now (app/highs.py, app/regimes.py), from two weeks out: the
              returns 21 or 63 sessions after its 250 most similar regime days, scaled to the date; not calibrated (their
              record is per event, not per range), so it counts half. Their odds of a 5/10/20% pullback, a new low, a
              rebound or a breakout come with the forecast.
  simulation  4,000 paths of daily returns: past standardised returns drawn at random, each day's volatility updated along
              the path (EWMA, lambda 0.94), from the last close's; the rest of today a normal draw at that volatility.
  factors     today only: the move to the close predicted from the move so far, the gap to VWAP and the first hour (one
              regression per hour of the day, refitted before every day of the asset's history): applied to the centre
              only when it predicted better than zero out of sample, and only as far as it did.
  futures     before the open: the index future's move since the last close (ES, NQ, YM, RTY) sets where the session
              starts.
  order book  the asset's best bid and ask (CBOE), the options' quoted spreads near the money and the ladders' overround:
              a source whose quotes are wide counts half in the pool; a ladder read too long ago for its date (1.5 hours
              for today's close, 6 for the next three days, a day beyond) is left out.

Calibration — the scale k of a source's spread around its median, per hour of the day (today) or per number of sessions
ahead: the k whose 50, 80 and 95% ranges held closest to 50, 80 and 95% of the time on the asset's own history (intraday
analogs and the implied 1-day volatility on the hourly bars of the last two to three years; daily analogs, the simulation
and the volatility indices on ten years of daily closes; recomputed once a day). The options' and the markets' k come
from the ladder backtest (app/ladders.py, branch ladder-history): how often their 80% ranges held at that horizon.

Highs and lows by each date (from now): today's from the 60 analog days' hourly highs and lows from this hour to the
close (scaled by their k); later dates by the reflection principle on the pooled close: P(the high by then > x) =
2 P(the close > x) — so the chance of touching a price comes beside the chance of closing past it.

Pooled: the median starts at the price now and rises by the asset's drift a session (drift(): its own mean daily log
return over the ten years, pulled toward the market's long-run 0.03% a session by how noisy its own is) — today's also
moved by the factors when they predicted out of sample. The markets' own expected value is not used: on every resolved
ladder of the backtest the price now was nearer the close. Left at the price now, the median was too low: on 2019–2026
(the eleven assets, the drift known only from the years before each day) the close ended above it 58% of the time two
weeks on and 64% seven weeks on; above the drifted one 54% and 56%, and nearer at every horizon (|error| 4.34 → 4.30%,
9.54 → 9.22%) — though not in a falling year (2022: 39% → 32% seven weeks on). The spread is the average of the calibrated sources' quantiles around their own medians, half the weight to the
market-implied sources (options, markets, implied), half to the history (analogs, simulation); each source's own
median is kept in its breakdown (src_up: their weighted P(close above the price now)).

Official freezes: at 9:45, 12:00 and 15:00 New York every session the pooled forecasts are frozen and filed on the branch
forecast-ledger (ledger/<YYYY-MM>.json), scored once their dates have closed (public/record.json: how often the close fell
inside the 50, 80 and 95% ranges, by horizon and by freeze time). Anyone can also freeze the live forecast in their own
browser (docs/closecast.js).

    python app/closecast.py --out OUT [--cache DIR] [--h60 DIR] [--live live.json]     one forecast: OUT/forecast.json
    python app/closecast.py ledger --root LEDGER [--freeze FILE] [--closes FILE]          file a freeze, score, publish
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import time
from pathlib import Path
from statistics import NormalDist
from zoneinfo import ZoneInfo

import numpy as np

import consensus as CS
import intraday as I
import ladders as L
import options as OP

SCHEMA = 'closecast.v1'
ET, UTC = ZoneInfo('America/New_York'), dt.timezone.utc
ND = NormalDist()
PGRID = (0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5,
         0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.925, 0.95, 0.975, 0.99, 0.995)
PG = np.array(PGRID)
ZG = np.array([ND.inv_cdf(p) for p in PGRID])
MED = PGRID.index(0.5)
LEVELS = (0.5, 0.8, 0.95)
LV_IX = {c: (PGRID.index(round((1 - c) / 2, 3)), PGRID.index(round((1 + c) / 2, 3))) for c in LEVELS}
KGRID = np.round(np.arange(0.3, 2.501, 0.02), 2)
SOURCES = ('options', 'markets', 'implied', 'analogs', 'moves', 'regime', 'sim')
GROUP = {'options': 'market', 'markets': 'market', 'implied': 'market', 'analogs': 'history', 'moves': 'history', 'regime': 'history',
         'sim': 'history'}
DRIFT_PRIOR, DRIFT_SD = 0.0003, 0.0005   # a session: the market's long-run price drift (≈7.5% a year), how far an asset's may sit
MOVE_BAND = 2.5                # the Move odds' similar days: within this many percentile points of the last move (app/moves.py BAND)
MOVE_MIN = 40                  # at least this many similar days (the band widens until there are)
REGIME_FILES = ('highs', 'lows', 'ranges')   # app/highs.py, app/regimes.py on research-paths public/moves/
REGIME_LABEL = {'highs': 'at its highs', 'atl': 'at an all-time low', '52w': 'at a 52-week low', '3m': 'at a 3-month low',
                'narrow': 'in a narrow range', 'wide': 'in a wide range'}
LAMBDA = 0.94
K_INTRADAY, K_DAILY = 60, 200
N_PATHS = 4000
HORIZONS = (1, 2, 3, 4, 5, 7, 10, 15, 21, 32, 42, 63)       # sessions ahead, calibrated (others interpolated)
FREEZES = ('09:45', '12:00', '15:00')
FREEZE_WINDOW_MIN = 40
MIN_TO_CLOSE = (390, 330, 270, 210, 150, 90, 30, 0)        # minutes from each intraday mark (9:30 … 15:30, 4 pm) to the close
LADDER_PAGES = {'spx': 'SPX', 'ndx': 'NDX', 'dji': 'DJIA', 'rut': 'RUT'}
RAW = 'https://raw.githubusercontent.com/eurikamonica/filing-flows'

ASSETS = [
    # key, Yahoo symbol, name, index (consensus.INDICES id), volatility indices by calendar days, index future
    ('SPY', 'SPY', 'S&P 500 (SPY)', 'spx', {1: '^VIX1D', 9: '^VIX9D', 30: '^VIX', 93: '^VIX3M', 186: '^VIX6M'}, 'ES=F'),
    ('QQQ', 'QQQ', 'Nasdaq-100 (QQQ)', 'ndx', {30: '^VXN'}, 'NQ=F'),
    ('DIA', 'DIA', 'Dow Jones Industrials (DIA)', 'dji', {30: '^VXD'}, 'YM=F'),
    ('IWM', 'IWM', 'Russell 2000 (IWM)', 'rut', {}, 'RTY=F'),          # Cboe's RVX is not on Yahoo: the options carry it
    ('AAPL', 'AAPL', 'Apple (AAPL)', None, {}, None),
    ('MSFT', 'MSFT', 'Microsoft (MSFT)', None, {}, None),
    ('NVDA', 'NVDA', 'Nvidia (NVDA)', None, {}, None),
    ('AMZN', 'AMZN', 'Amazon (AMZN)', None, {}, None),
    ('GOOGL', 'GOOGL', 'Alphabet (GOOGL)', None, {}, None),
    ('META', 'META', 'Meta Platforms (META)', None, {}, None),
    ('TSLA', 'TSLA', 'Tesla (TSLA)', None, {}, None),
]
IX = {ix['id']: ix for ix in CS.INDICES}

# NYSE: full-day closures and 1 pm closes (the calendar the targets are drawn on)
HOLIDAYS = {
    '2025-01-01', '2025-01-09', '2025-01-20', '2025-02-17', '2025-04-18', '2025-05-26', '2025-06-19', '2025-07-04', '2025-09-01',
    '2025-11-27', '2025-12-25',
    '2026-01-01', '2026-01-19', '2026-02-16', '2026-04-03', '2026-05-25', '2026-06-19', '2026-07-03', '2026-09-07', '2026-11-26',
    '2026-12-25',
    '2027-01-01', '2027-01-18', '2027-02-15', '2027-03-26', '2027-05-31', '2027-06-18', '2027-07-05', '2027-09-06', '2027-11-25',
    '2027-12-24',
}
EARLY = {'2025-07-03', '2025-11-28', '2025-12-24', '2026-11-27', '2026-12-24', '2027-11-26'}


def _r(v, d=6):
    return None if v is None or not np.isfinite(v) else round(float(v), d)


def log(msg):
    print(f'  {msg}', flush=True)


def age_h(as_of, now):
    """Hours since a ladder was read: an ISO time, or ladder-history's hour key ('2026-11-10T13', UTC)."""
    if not as_of:
        return None
    try:
        t = dt.datetime.strptime(as_of, '%Y-%m-%dT%H').replace(tzinfo=UTC) if len(as_of) == 13 else dt.datetime.fromisoformat(as_of)
        return (now - t).total_seconds() / 3600
    except ValueError:
        return None


def max_age_h(lead_h):
    """How old a ladder's prices may be for a date `lead_h` hours away (older: its book has moved on without it)."""
    return 1.5 if lead_h <= 6 else 6.0 if lead_h <= 72 else 24.0


# ------------------------------------------------------------------ the calendar
def is_session(d):
    return d.weekday() < 5 and d.isoformat() not in HOLIDAYS


def next_session(d):
    d += dt.timedelta(days=1)
    while not is_session(d):
        d += dt.timedelta(days=1)
    return d


def open_at(d):
    return dt.datetime(d.year, d.month, d.day, 9, 30, tzinfo=ET)


def close_at(d):
    return dt.datetime(d.year, d.month, d.day, 13 if d.isoformat() in EARLY else 16, tzinfo=ET)


def last_session_until(d):
    while not is_session(d):
        d -= dt.timedelta(days=1)
    return d


def sessions_after(a, b):
    """Sessions s with a < s <= b."""
    n, d = 0, a
    while d < b:
        d = next_session(d)
        if d <= b:
            n += 1
    return n


def phase_of(now):
    """(the first session whose close is ahead, 'pre' | 'open' | 'closed', the share of that session still to come)."""
    t = now.astimezone(ET)
    d = t.date()
    if is_session(d) and t < close_at(d):
        if t < open_at(d):
            return d, 'pre', 1.0
        return d, 'open', max(0.0, (close_at(d) - t).total_seconds() / (close_at(d) - open_at(d)).total_seconds())
    return next_session(d), 'closed', 1.0


def targets(now, expiries=()):
    """The dates forecast: the first close ahead, each options expiry of that week, the week's last session, the next
    week's, the month's and the quarter's — [{date, tags}] by date (one date, several tags)."""
    first, _, _ = phase_of(now)
    fri = first + dt.timedelta(days=4 - first.weekday())
    week = last_session_until(fri)
    week2 = last_session_until(fri + dt.timedelta(days=7))
    nm = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    month = last_session_until(nm - dt.timedelta(days=1))
    qm = ((first.month - 1) // 3 + 1) * 3
    qe = (dt.date(first.year + (qm == 12), qm % 12 + 1, 1)) - dt.timedelta(days=1)
    quarter = last_session_until(qe)
    tags = {}
    tags.setdefault(first, []).append('first')
    for e in sorted(expiries):
        d = dt.date.fromisoformat(e) if isinstance(e, str) else e
        if first <= d <= week and is_session(d):
            tags.setdefault(d, []).append('expiry')
    for d, tag in ((week, 'week'), (week2, '2w'), (month, 'month'), (quarter, 'quarter')):
        if d >= first:
            tags.setdefault(d, []).append(tag)
    return [{'date': d.isoformat(), 'tags': tags[d]} for d in sorted(tags)]


# ------------------------------------------------------------------ quantile helpers (log returns at PGRID)
def q_samples(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 10:
        return None
    return np.quantile(x, PG)


def q_normal(mu, sigma):
    if not (sigma > 0):
        return None
    return mu + sigma * ZG


def q_ladder(ks, pa, to_asset, spot):
    """Quantiles of log(X × to_asset / spot) from a ladder: strikes ks (ascending, in the ladder's units) and P(X > K)
    (non-increasing). Inside the ladder: linear between strikes; beyond it, the log-normal fitted to the ladder (else the
    ladder's own spread)."""
    ks = [float(k) for k in ks]
    F = [1 - float(p) for p in pa]
    if len(ks) < 2 or not spot or not to_asset or ks[0] <= 0:
        return None
    for i in range(1, len(F)):
        F[i] = max(F[i], F[i - 1])
    fit = CS._lognormal_fit(ks, [1 - f for f in F])
    if fit and not (0 < fit[1] <= 2.5):
        fit = None
    span = math.log(ks[-1] / ks[0]) / 4 or 0.01
    out = []
    for p in PGRID:
        if F[0] <= p <= F[-1] and F[-1] > F[0]:
            j = int(np.searchsorted(F, p, side='left'))
            j = min(max(j, 1), len(F) - 1)
            a, b = F[j - 1], F[j]
            w = 0.0 if b <= a else (p - a) / (b - a)
            k = ks[j - 1] + w * (ks[j] - ks[j - 1])
        elif fit:
            mu, sg = fit
            k = math.exp(mu + sg * ND.inv_cdf(p))
            k = min(k, ks[0]) if p < F[0] else max(k, ks[-1])
        else:
            k = ks[0] * math.exp(span * ND.inv_cdf(p / max(F[0], 1e-6)) / 2) if p < F[0] else ks[-1] * math.exp(-span * ND.inv_cdf((1 - p) / max(1 - F[-1], 1e-6)) / 2)
        out.append(math.log(max(k, 1e-9) * to_asset / spot))
    q = np.maximum.accumulate(np.asarray(out, float))
    return q


def scale(q, k):
    """A source's quantiles with its spread around its median scaled by k."""
    q = np.asarray(q, float)
    m = q[MED]
    return m + k * (q - m)


def interval(q, c):
    """(low, high) of the central c range from quantiles at PGRID (interpolated in normal scores)."""
    lo, hi = (1 - c) / 2, (1 + c) / 2
    return float(np.interp(ND.inv_cdf(lo), ZG, q)), float(np.interp(ND.inv_cdf(hi), ZG, q))


def cdf_at(q, y):
    """P(X <= y) under quantiles q at PGRID (normal-score interpolation, tails to the grid's ends)."""
    return float(ND.cdf(float(np.interp(y, q, ZG, left=ZG[0] - 0.5, right=ZG[-1] + 0.5))))


# ------------------------------------------------------------------ calibration: the k that makes the ranges hold
def fit_k(Q, y):
    """Q: n × len(PGRID) forecasts, y: n outcomes. The k (KGRID) whose 50/80/95% ranges' hit rates are closest to 50/80/95%
    — with the hit rates at k = 1 and at the k chosen."""
    Q = np.asarray(Q, float)
    y = np.asarray(y, float)
    ok = np.isfinite(y) & np.isfinite(Q).all(axis=1)
    Q, y = Q[ok], y[ok]
    if len(y) < 30:
        return None
    m = Q[:, MED]
    d = y - m
    err = np.zeros(len(KGRID))
    hits = {}
    for c in LEVELS:
        a, b = Q[:, LV_IX[c][0]] - m, Q[:, LV_IX[c][1]] - m
        h = ((d[None, :] >= KGRID[:, None] * a[None, :]) & (d[None, :] <= KGRID[:, None] * b[None, :])).mean(axis=1)
        err += (h - c) ** 2
        hits[c] = h
    i = int(np.argmin(err))
    j1 = int(np.argmin(np.abs(KGRID - 1.0)))
    return {'k': float(KGRID[i]), 'n': int(len(y)), 'raw': {str(c): _r(hits[c][j1], 3) for c in LEVELS}, 'fit': {str(c): _r(hits[c][i], 3) for c in LEVELS}}


def k_from_inside80(inside):
    """The scale that turns a normal 80% range holding `inside` of the time into one holding 80%."""
    if inside is None or not np.isfinite(inside):
        return None
    inside = min(max(float(inside), 0.55), 0.995)
    return round(ND.inv_cdf(0.9) / ND.inv_cdf(0.5 + inside / 2), 3)


def k_at(table, n):
    """k at n sessions from {sessions: {k}} (log-linear between the calibrated horizons, flat beyond them)."""
    pts = sorted((int(h), v['k']) for h, v in (table or {}).items() if v and v.get('k'))
    if not pts:
        return None
    hs = [h for h, _ in pts]
    ks = [k for _, k in pts]
    n = max(n, 1)
    return float(np.interp(math.log(n), np.log(hs), ks))


# ------------------------------------------------------------------ daily history: EWMA volatility, analogs, simulation
def ewma(r, lam=LAMBDA):
    """EWMA variance after each day (s2[t] uses r[0..t])."""
    s2 = np.empty(len(r))
    v = float(np.nanvar(r[:20])) if len(r) >= 20 else float(np.nanvar(r))
    for t, x in enumerate(r):
        v = lam * v + (1 - lam) * (x * x if np.isfinite(x) else v)
        s2[t] = v
    return s2


def features(c, s2):
    """Per day: volatility against its past year (log), the 20-day and 5-day trends in units of volatility."""
    lc = np.log(c)
    s = np.sqrt(s2)
    n = len(c)
    f = np.full((n, 3), np.nan)
    for t in range(260, n):
        f[t, 0] = math.log(s[t] / np.median(s[t - 252:t]))
        f[t, 1] = (lc[t] - lc[t - 20]) / (s[t] * math.sqrt(20))
        f[t, 2] = (lc[t] - lc[t - 5]) / (s[t] * math.sqrt(5))
    return f


def analog_sample(c, s2, f, t, n, k=K_DAILY, sd=None):
    """The n-session log returns after the k days most like day t (their trend and volatility; outcomes known by t),
    rescaled to day t's volatility."""
    lc = np.log(c)
    last = t - n                                                     # a neighbour's n-day outcome is known by day t
    cand = np.arange(260, max(260, last + 1))
    cand = cand[np.isfinite(f[cand]).all(axis=1)]
    if len(cand) < k or not np.isfinite(f[t]).all():
        return None
    sd = sd if sd is not None else np.nanstd(f[260:], axis=0)
    dist = (((f[cand] - f[t]) / sd) ** 2).sum(axis=1)
    near = cand[np.argpartition(dist, k)[:k]]
    fwd = lc[near + n] - lc[near]
    return fwd * np.sqrt(s2[t] / s2[near])


def move_pct(r):
    """Each day's one-day move as a percentile (mid-rank) among every day's (app/moves.py's percentiles)."""
    r = np.asarray(r, float)
    ok = np.isfinite(r)
    out = np.full(len(r), np.nan)
    v = np.sort(r[ok])
    lo = np.searchsorted(v, r[ok], side='left')
    hi = np.searchsorted(v, r[ok], side='right')
    out[ok] = 100.0 * (lo + (hi - lo) / 2) / len(v)
    return out


def moves_sample(lc, pct, t, n, skip=0, band=MOVE_BAND):
    """Move odds: the log returns over n sessions after the days whose one-day move was within `band` percentile points
    of day t's (outcomes known by day t; `skip` sessions after the similar day first: in the session, today is the day
    after the last close), the band doubled until MOVE_MIN days are in it."""
    last = t - n - skip
    if last < 260 or not np.isfinite(pct[t]):
        return None
    cand = np.arange(1, last + 1)
    cand = cand[np.isfinite(pct[cand])]
    b = band
    while b <= 20:
        near = cand[np.abs(pct[cand] - pct[t]) <= b]
        if len(near) >= MOVE_MIN:
            return lc[near + skip + n] - lc[near + skip]
        b *= 2
    return None


def regime_q(an, n):
    """Quantiles at PGRID of the log return over n sessions from a regime's analogues (app/highs.py, regimes.py: their
    returns 21 and 63 sessions on, p10 … p90), scaled to n (spread by √time, centre by time); tails continued in normal
    scores from the outer quartile steps."""
    h = 21 if n <= 32 else 63
    d = (an or {}).get(f'fwd{h}') or {}
    ks = [('p10', 0.1), ('p25', 0.25), ('p50', 0.5), ('p75', 0.75), ('p90', 0.9)]
    if any(d.get(k) is None for k, _ in ks) or (d.get('n') or 0) < 50:
        return None
    zs = np.array([ND.inv_cdf(p) for _, p in ks])
    xs = np.log1p(np.array([float(d[k]) for k, _ in ks]))
    xs = np.maximum.accumulate(xs)
    lo_slope = (xs[1] - xs[0]) / (zs[1] - zs[0])
    hi_slope = (xs[4] - xs[3]) / (zs[4] - zs[3])
    q = np.where(ZG < zs[0], xs[0] + (ZG - zs[0]) * lo_slope, np.where(ZG > zs[-1], xs[-1] + (ZG - zs[-1]) * hi_slope, np.interp(ZG, zs, xs)))
    med = xs[2]
    return med * n / h + (q - med) * math.sqrt(n / h)


def sim_paths(r, s2, t, n_max, n_paths=N_PATHS, rng=None):
    """Cumulative log returns of n_paths paths over n_max sessions after day t: standardised returns of days ≤ t drawn at
    random, the variance updated along each path (EWMA)."""
    rng = rng or np.random.default_rng(7)
    z = r[1:t + 1] / np.sqrt(s2[:t])
    z = z[np.isfinite(z)]
    if len(z) < 250 or n_max < 1:
        return None
    v = np.full(n_paths, s2[t])
    cum = np.zeros((n_paths, n_max))
    acc = np.zeros(n_paths)
    draws = rng.choice(z, size=(n_paths, n_max))
    for d in range(n_max):
        x = np.sqrt(v) * draws[:, d]
        acc = acc + x
        cum[:, d] = acc
        v = LAMBDA * v + (1 - LAMBDA) * x * x
    return cum


def implied_sigma(levels, days, minutes=None):
    """Total volatility (not annualised) to a target `days` calendar days away from the volatility indices' levels by
    tenor {days: level}; `minutes` to the close for today's (VIX1D over the minutes left, else the nearest tenor)."""
    lv = {int(k): float(v) for k, v in (levels or {}).items() if v and np.isfinite(v) and v > 0}
    if not lv:
        return None
    if minutes is not None:
        lev = lv.get(1) or lv[min(lv)]
        return lev / 100 * math.sqrt(max(minutes, 1) / 525600)
    tn = sorted(lv)
    var = {d: (lv[d] / 100) ** 2 * d / 365 for d in tn}
    days = max(days, 1 / 24)
    if days <= tn[0]:
        return math.sqrt((lv[tn[0]] / 100) ** 2 * days / 365)
    if days >= tn[-1]:
        return math.sqrt((lv[tn[-1]] / 100) ** 2 * days / 365)
    return math.sqrt(float(np.interp(days, tn, [var[d] for d in tn])))


# ------------------------------------------------------------------ backtests (calibration)
def calib_intraday(hist, vol_hist=None, k=K_INTRADAY, min_days=120):
    """Per intraday mark (9:30 … 15:30): the analogs' and the implied volatility's k on the asset's hourly history."""
    cols = hist.get('cols') or []
    if len(cols) < 3 or len(cols[0]) < min_days + 30:
        return None
    days = cols[0]
    Mx = np.asarray(cols[1], float)
    vol_lvl = None
    if vol_hist and len(vol_hist.get('cols') or []) >= 3:
        vd = vol_hist['cols'][0]
        vM = np.asarray(vol_hist['cols'][1], float)
        vC = np.asarray(vol_hist['cols'][2], float)
        prev = {vd[i]: vC[i - 1] for i in range(1, len(vd))}
        at = {vd[i]: prev[vd[i]] * (1 + vM[i]) for i in range(1, len(vd))}
        vol_lvl = np.array([at.get(d, np.full(8, np.nan)) for d in days], float)
    out = {'analogs': [], 'implied': []}
    for j in range(7):
        m = Mx[:, j]
        rest = np.log((1 + Mx[:, 7]) / (1 + m))
        Qa, ya, Qi, yi = [], [], [], []
        for i in range(min_days, len(days)):
            if not (np.isfinite(m[i]) and np.isfinite(rest[i])):
                continue
            cand = np.nonzero(np.isfinite(m[:i]) & np.isfinite(rest[:i]))[0]
            if len(cand) >= k:
                near = cand[np.argpartition(np.abs(m[cand] - m[i]), k - 1)[:k]]
                q = q_samples(rest[near])
                if q is not None:
                    Qa.append(q)
                    ya.append(rest[i])
            if vol_lvl is not None and np.isfinite(vol_lvl[i, j]) and vol_lvl[i, j] > 0:
                sg = vol_lvl[i, j] / 100 * math.sqrt(MIN_TO_CLOSE[j] / 525600)
                Qi.append(q_normal(-sg * sg / 2, sg))
                yi.append(rest[i])
        out['analogs'].append(fit_k(Qa, ya) if Qa else None)
        out['implied'].append(fit_k(Qi, yi) if Qi else None)
    return out


def calib_daily(c, vol=None, every=5, sim_every=10, rng=None):
    """Per horizon (sessions ahead): the daily analogs', the simulation's and the volatility indices' k on the asset's
    daily closes (vol: {tenor days: array of index levels on the same days, NaN where missing})."""
    c = np.asarray(c, float)
    if len(c) < 900:
        return None
    r = np.concatenate([[np.nan], np.diff(np.log(c))])
    r[0] = 0.0
    s2 = ewma(r)
    f = features(c, s2)
    sd = np.nanstd(f[260:], axis=0)
    lc = np.log(c)
    rng = rng or np.random.default_rng(11)
    out = {'analogs': {}, 'moves': {}, 'sim': {}, 'implied': {}}
    hmax = max(HORIZONS)
    start = 760
    pct = move_pct(r)
    for n in HORIZONS:
        Q, y = [], []
        for t in range(start, len(c) - n, every):
            s = moves_sample(lc, pct, t, n)
            if s is not None:
                Q.append(q_samples(s))
                y.append(lc[t + n] - lc[t])
        out['moves'][str(n)] = fit_k(Q, y)
    for n in HORIZONS:
        Q, y = [], []
        for t in range(start, len(c) - n, every):
            s = analog_sample(c, s2, f, t, n, sd=sd)
            if s is not None:
                Q.append(q_samples(s))
                y.append(lc[t + n] - lc[t])
        out['analogs'][str(n)] = fit_k(Q, y)
    sims = []
    for t in range(start, len(c) - 1, sim_every):
        cum = sim_paths(r, s2, t, hmax, n_paths=1000, rng=rng)
        if cum is not None:
            sims.append((t, np.quantile(cum, PG, axis=0).T))          # hmax × len(PGRID)
    for n in HORIZONS:
        Q = [qs[n - 1] for t, qs in sims if t + n < len(c)]
        y = [lc[t + n] - lc[t] for t, qs in sims if t + n < len(c)]
        out['sim'][str(n)] = fit_k(Q, y)
    if vol:
        for n in HORIZONS:
            Q, y = [], []
            for t in range(start, len(c) - n, every):
                lv = {d: arr[t] for d, arr in vol.items() if np.isfinite(arr[t])}
                sg = implied_sigma(lv, n * 7 / 5)
                if sg:
                    Q.append(q_normal(-sg * sg / 2, sg))
                    y.append(lc[t + n] - lc[t])
            out['implied'][str(n)] = fit_k(Q, y)
    return out


def factor_model(hist, j, min_days=250):
    """Today's move from mark j to the close regressed on the move so far, the gap to VWAP and the first hour, refitted
    before every day of the last part of the history: {coef (the fit on every day), r2_oos (against forecasting zero), n}."""
    cols = hist.get('cols') or []
    if len(cols) < 4 or j < 1 or j > 6:
        return None
    Mx = np.asarray(cols[1], float)
    VW = np.array([r if r else [np.nan] * 7 for r in cols[3]], float)
    y = np.log((1 + Mx[:, 7]) / (1 + Mx[:, j]))
    X = np.column_stack([np.ones(len(y)), np.log1p(Mx[:, j]), np.log((1 + Mx[:, j]) / (1 + VW[:, j - 1])), np.log((1 + Mx[:, 1]) / (1 + Mx[:, 0]))])
    ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
    idx = np.nonzero(ok)[0]
    if len(idx) < min_days + 60:
        return None
    pred, act = [], []
    for i in idx[min_days:]:
        tr = idx[idx < i]
        b, *_ = np.linalg.lstsq(X[tr], y[tr], rcond=None)
        pred.append(float(X[i] @ b))
        act.append(float(y[i]))
    pred, act = np.asarray(pred), np.asarray(act)
    r2 = 1 - float(((act - pred) ** 2).sum() / (act ** 2).sum()) if (act ** 2).sum() > 0 else None
    b, *_ = np.linalg.lstsq(X[idx], y[idx], rcond=None)
    return {'coef': [_r(v, 6) for v in b], 'r2_oos': _r(r2, 4), 'n': int(len(act))}


# ------------------------------------------------------------------ the data
class Feed:
    """Every read, cached under `root`: Yahoo charts, ten years of daily closes, the hourly history (shared with
    app/intraday.py), CBOE chains (15 minutes), the prediction-market ladders (10 minutes), the ladder backtest."""

    def __init__(self, root, h60, now, http=None):
        self.root, self.h60, self.now = Path(root), Path(h60), now
        self.today = now.astimezone(ET).date().isoformat()
        self.h = http or CS.Http({'query2.finance.yahoo.com': 0.35, 'cdn.cboe.com': 0.3, 'cdn-api.cboe.com': 0.3, 'api.elections.kalshi.com': 0.6,
                                  'gamma-api.polymarket.com': 0.2, 'raw.githubusercontent.com': 0.1})
        self.root.mkdir(parents=True, exist_ok=True)

    def _read(self, name):
        try:
            return json.loads((self.root / name).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None

    def _write(self, name, doc):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')

    def _fresh(self, doc, seconds):
        try:
            return doc and (self.now - dt.datetime.fromisoformat(doc['at'])).total_seconds() < seconds
        except (KeyError, ValueError, TypeError):
            return False

    def quote(self, sym):
        return I.today_of(I.chart(self.h, sym, '1d', '5m'))

    def futures_move(self, sym, prev_close_day):
        """The future's move since the 4 pm of `prev_close_day` (the last session), from its five-minute bars."""
        res = self.h.json(f'{CS.YQ}/v8/finance/chart/{sym}?range=5d&interval=5m&includePrePost=true')['chart']['result'][0]
        ts = res.get('timestamp') or []
        cl = ((res.get('indicators') or {}).get('quote') or [{}])[0].get('close') or []
        mark = close_at(prev_close_day).timestamp()
        base = last = None
        for t, c in zip(ts, cl):
            if c is None:
                continue
            if t <= mark - 300:
                base = c
            last = c
        meta = res.get('meta') or {}
        last = meta.get('regularMarketPrice') or last
        if not base or not last:
            return None
        return {'symbol': sym, 'price': _r(last, 2), 'at_close': _r(base, 2), 'move': _r(last / base - 1, 5),
                'time': dt.datetime.fromtimestamp(meta['regularMarketTime'], UTC).isoformat() if meta.get('regularMarketTime') else None}

    def daily(self, key, sym, years=10):
        """Ten years of daily closes (and adjusted closes), read once a day — again once the day's session has closed
        (ten minutes after its close), so a close just made is on file for the ledger."""
        name = f'daily/{key}.json'
        doc = self._read(name)
        d0 = self.now.astimezone(ET).date()
        closed = last_session_until(d0) if self.now.astimezone(ET) >= close_at(last_session_until(d0)) + dt.timedelta(minutes=10) \
            else last_session_until(d0 - dt.timedelta(days=1))
        if doc and doc.get('refreshed') == self.today and (doc.get('t') or [''])[-1] >= closed.isoformat():
            return doc
        if doc and doc.get('tried') and (self.now - dt.datetime.fromisoformat(doc['tried'])).total_seconds() < 1800 and doc.get('refreshed') == self.today:
            return doc                                                 # tried in the last half hour: Yahoo has not the close yet
        try:
            res = I.chart(self.h, sym, f'{years}y', '1d')
            ts = res.get('timestamp') or []
            q = ((res.get('indicators') or {}).get('quote') or [{}])[0].get('close') or []
            ac = (((res.get('indicators') or {}).get('adjclose') or [{}])[0] or {}).get('adjclose') or q
            rows = [(dt.datetime.fromtimestamp(t, ET).date().isoformat(), c, a) for t, c, a in zip(ts, q, ac) if c and a and c > 0 and a > 0]
            today_bar = rows and rows[-1][0] == self.today and phase_of(self.now)[1] != 'closed'
            if today_bar:
                rows = rows[:-1]                                     # the session still trading: its bar is not a close
            doc = {'key': key, 'symbol': sym, 'refreshed': self.today, 'tried': self.now.isoformat(timespec='seconds'), 't': [x[0] for x in rows],
                   'c': [round(x[1], 4) for x in rows], 'ac': [round(x[2], 4) for x in rows]}
            self._write(name, doc)
        except Exception as exc:                                       # noqa: BLE001
            log(f'daily {sym}: {str(exc)[:120]}')
        return doc

    def hourly(self, key, sym):
        try:
            return I.load_history(self.h, self.h60, key, sym, self.today)
        except Exception as exc:                                       # noqa: BLE001
            log(f'hourly {sym}: {str(exc)[:120]}')
            return None

    def chain(self, sym):
        """The option book (app/ladders.py expiry_book: per expiry the out-of-the-money smile, max pain, walls) with the
        quotes' spreads near the money and the underlying's best bid and ask; re-read every 15 minutes."""
        name = f'chains/{sym}.json'
        doc = self._read(name)
        open_now = phase_of(self.now)[1] == 'open'
        if self._fresh(doc, 900 if open_now else 6 * 3600):
            return doc
        try:
            payload = self.h.json(OP.URL.format(sym=OP.cboe_symbol(sym)))
            spot, iv30, _, chain = OP.parse_chain(payload)
            if not spot or not chain:
                raise RuntimeError('empty chain')
            today = self.now.astimezone(ET).date()
            book = L.expiry_book(spot, chain, today, days=130)
            spreads = {}
            for e in book:
                near = [c for c in chain if c['exp'] == e and abs(c['k'] / spot - 1) <= 0.03 and c['bid'] > 0 and c['ask'] > c['bid']
                        and ((c['type'] == 'P' and c['k'] <= spot) or (c['type'] == 'C' and c['k'] > spot))]
                if near:
                    spreads[e] = round(float(np.median([(c['ask'] - c['bid']) / ((c['ask'] + c['bid']) / 2) for c in near])), 4)
            d = payload.get('data') or {}
            doc = {'at': self.now.isoformat(timespec='seconds'), 'quote_time': payload.get('timestamp'), 'spot': spot, 'iv30': iv30,
                   'exps': book, 'spreads': spreads,
                   'book': {k: d.get(k) for k in ('bid', 'ask', 'bid_size', 'ask_size', 'last_trade_time', 'volume', 'prev_day_close')}}
            self._write(name, doc)
        except Exception as exc:                                       # noqa: BLE001
            log(f'cboe {sym}: {str(exc)[:120]}')
        return doc

    def ladders(self):
        """Open ladders on a close [{source, kind, end, units: Yahoo symbol of the strikes, strikes, p_above, overround,
        as_of, title, url}]: Kalshi's index ladders and the Polymarket events app/ladders.py has found, re-read every
        10 minutes; ladder-history's hourly copy where a read fails."""
        doc = self._read('ladders.json')
        if self._fresh(doc, 600):
            return doc['rows']
        rows, pages = [], {}
        for page in sorted({LADDER_PAGES[a[3]] for a in ASSETS if a[3]} | {a[0] for a in ASSETS if not a[3]}):
            try:
                pages[page] = self.h.json(f'{RAW}/ladder-history/public/t/{page}.json')
            except Exception:                                          # noqa: BLE001 — no ladder page for it
                pass
        now_s = self.now.isoformat(timespec='seconds')
        for page, d in pages.items():                                  # the hourly copy, then refreshed below
            for r in d.get('open') or []:
                if r.get('strikes') and r.get('p') and r.get('kind') in ('above', 'bracket'):
                    pts = [(k, p) for k, p in zip(r['strikes'], r['p']) if p is not None]
                    st = CS.ladder_stats(pts) if len(pts) >= 2 else None
                    if st:
                        rows.append({'source': r['source'], 'kind': r['kind'], 'end': r['end'], 'units': r.get('sym'), 'strikes': st['strikes'],
                                     'p_above': st['p_above'], 'as_of': r.get('as_of'), 'title': r.get('title'), 'url': r.get('url'), 'via': 'ladder-history'})
        fresh = []
        try:
            for m in CS.kalshi_index_scan(self.h, self.root, minutes=1.0, verbose=False):
                st = m.get('stats') or {}
                ix = IX.get(m.get('index'))
                if m.get('kind') in ('above', 'bracket') and st.get('strikes') and ix:
                    fresh.append({'source': 'kalshi', 'kind': m['kind'], 'end': m['end'], 'units': ix['symbol'], 'strikes': st['strikes'],
                                  'p_above': st['p_above'], 'overround': st.get('overround'), 'as_of': now_s, 'title': m.get('title'), 'url': m.get('url'), 'via': 'kalshi'})
        except Exception as exc:                                       # noqa: BLE001
            log(f'kalshi: {str(exc)[:120]}')
        for r in [x for x in rows if x['source'] == 'polymarket' and '/event/' in (x.get('url') or '')]:
            slug = r['url'].split('/event/')[1]
            try:
                ev = self.h.json(f'{CS.GAMMA}/events?slug={slug}')
                e = ev[0] if isinstance(ev, list) and ev else None
                if not e or e.get('closed'):
                    continue
                kind = CS.poly_kind(e.get('title') or '')
                base = {'source': 'polymarket', 'kind': kind, 'title': e.get('title'), 'url': r['url'], 'end': (e.get('endDate') or '')[:10], 'closed': False}
                for m in CS.poly_rows(e, base, e.get('title') or '', e.get('markets') or []):
                    st = m.get('stats') or {}
                    if m.get('kind') in ('above', 'bracket') and st.get('strikes'):
                        fresh.append({'source': 'polymarket', 'kind': m['kind'], 'end': r['end'], 'units': r['units'], 'strikes': st['strikes'],
                                      'p_above': st['p_above'], 'overround': st.get('overround'), 'as_of': now_s, 'title': r.get('title'), 'url': r['url'], 'via': 'polymarket'})
            except Exception as exc:                                   # noqa: BLE001
                log(f'polymarket {slug}: {str(exc)[:100]}')
        seen = {(f['source'], f['end'], f['units'], f['kind']) for f in fresh}
        rows = fresh + [r for r in rows if (r['source'], r['end'], r['units'], r['kind']) not in seen]
        self._write('ladders.json', {'at': now_s, 'rows': rows})
        return rows

    def regimes(self):
        """{asset: [the regimes it is in now — at its highs, at a low, in a range — with the state and the analogues' odds]}
        from research-paths' public/moves/{highs,lows,ranges}.json (app/highs.py, app/regimes.py), read once a day."""
        doc = self._read('regimes.json')
        if doc and doc.get('refreshed') == self.today:
            return doc['assets']
        mine = {a[0] for a in ASSETS}
        out = {}
        keep = ('days', 'assets', 't5', 't10', 't20', 'run_left', 'more_highs', 'gain_left', 'pullback', 'mdd63', 'fwd21', 'fwd63', 'next_low', 'r10', 'r20',
                'fall', 'bounce', 'breakout', 'up_first', 'failed_up', 'failed_down', 'after63_up', 'after63_down')
        for f in REGIME_FILES:
            try:
                d = self.h.json(f'{RAW}/research-paths/public/moves/{f}.json')
            except Exception as exc:                                   # noqa: BLE001
                log(f'regimes {f}: {str(exc)[:100]}')
                continue
            now = d.get('now') or []
            groups = now.items() if isinstance(now, dict) else [('highs', now)]
            for reg, rows in groups:
                for r in rows or []:
                    if r.get('key') in mine and r.get('analogues'):
                        st = r.get('state') or {}
                        out.setdefault(r['key'], []).append({'file': f, 'regime': reg, 'label': REGIME_LABEL.get(reg, reg),
                                                             'state': {k: st.get(k) for k in ('date', 'close', 'ath', 'ath_date', 'dd', 'dd_ath', 'age', 'run_gain', 'highs63',
                                                                                              'low', 'low_date', 'lows63', 'width', 'width_pct', 'pos', 'hi', 'lo', 'since', 'days_in')
                                                                       if st.get(k) is not None},
                                                             'analogues': {k: v for k, v in r['analogues'].items() if k in keep}})
        if out or not doc:
            self._write('regimes.json', {'refreshed': self.today, 'assets': out})
        return out if out or not doc else doc.get('assets') or {}

    def ladder_k(self):
        """{page or '*': {bucket: {options: k, markets: k, n}}} from the ladder backtest (each page's own when it has 20
        markets at that horizon, else every ladder's)."""
        doc = self._read('ladder_k.json')
        if doc and doc.get('refreshed') == self.today:
            return doc['k']
        out = {}
        try:
            ix = self.h.json(f'{RAW}/ladder-history/public/index.json')
            out['*'] = {b['bucket']: {'options': k_from_inside80((b.get('inside80') or {}).get('options')), 'markets': k_from_inside80((b.get('inside80') or {}).get('ladder')),
                                      'n': b.get('markets')} for b in ix.get('backtest') or [] if (b.get('markets') or 0) >= 20}
            for page in sorted({LADDER_PAGES[a[3]] for a in ASSETS if a[3]} | {a[0] for a in ASSETS if not a[3]}):
                try:
                    d = self.h.json(f'{RAW}/ladder-history/public/t/{page}.json')
                except Exception:                                      # noqa: BLE001
                    continue
                own = {b['bucket']: {'options': k_from_inside80((b.get('inside80') or {}).get('options')), 'markets': k_from_inside80((b.get('inside80') or {}).get('ladder')),
                                     'n': b.get('markets')} for b in d.get('backtest') or [] if (b.get('markets') or 0) >= 20}
                if own:
                    out[page] = own
            self._write('ladder_k.json', {'refreshed': self.today, 'k': out})
        except Exception as exc:                                       # noqa: BLE001
            log(f'ladder backtest: {str(exc)[:120]}')
            out = (doc or {}).get('k') or {}
        return out


def vol_key(sym):
    return 'VOL-' + sym.lstrip('^')


def calibration(feed, log_=log, assets=None):
    """Every asset's k (once a day, cached): intraday per mark, daily per horizon; and the factor models per mark."""
    doc = feed._read('calibration.json')
    if doc and doc.get('refreshed') == feed.today and all(k in doc.get('assets', {}) for k in (assets or [a[0] for a in ASSETS])):
        return doc
    t0 = time.time()
    out = {'refreshed': feed.today, 'assets': {}}
    for key, sym, _, _, vols, _ in ASSETS:
        if assets and key not in assets:
            continue
        a = {}
        hist = feed.hourly(key, sym)
        vh = None
        if vols:
            vs = vols.get(1) or vols[min(vols)]
            vh = feed.hourly(vol_key(vs), vs)
        if hist:
            try:
                a['intraday'] = calib_intraday(hist, vh)
                a['factors'] = [factor_model(hist, j) for j in range(7)]
            except Exception as exc:                                   # noqa: BLE001
                log_(f'calibration {key} intraday: {str(exc)[:120]}')
        d = feed.daily(key, sym)
        if d and len(d.get('ac') or []) > 900:
            vol = {}
            for tenor, vs in vols.items():
                if tenor == 1:
                    continue                                           # VIX1D: today's close only (the intraday k)
                vd = feed.daily(vol_key(vs), vs)
                if vd and vd.get('t'):
                    m = dict(zip(vd['t'], vd['c']))
                    vol[tenor] = np.array([m.get(t, np.nan) for t in d['t']], float)
            try:
                a['daily'] = calib_daily(np.asarray(d['ac'], float), vol or None)
            except Exception as exc:                                   # noqa: BLE001
                log_(f'calibration {key} daily: {str(exc)[:120]}')
        out['assets'][key] = a
    out['seconds'] = round(time.time() - t0, 1)
    feed._write('calibration.json', out)
    return out


# ------------------------------------------------------------------ one asset's forecast
def drift(closes):
    """The median's rise a session (log): the mean daily log return of `closes` (as traded: dividends not added back),
    pulled toward DRIFT_PRIOR as a normal prior of sd DRIFT_SD would — the noisier the asset, the nearer the prior
    (ten years: SPY keeps most of its own, NVDA or TSLA about half). (drift, its own mean or None)."""
    c = np.asarray(closes, float)
    c = c[np.isfinite(c) & (c > 0)]
    if len(c) < 260:
        return DRIFT_PRIOR, None
    r = np.diff(np.log(c))
    n, own, var = len(r), float(r.mean()), float(r.var())
    if not var > 0:
        return DRIFT_PRIOR, own
    return (DRIFT_PRIOR / DRIFT_SD ** 2 + n * own / var) / (1 / DRIFT_SD ** 2 + n / var), own


def pool(srcs, centre):
    """Quantiles pooled from calibrated sources {name: {q, w}}: each around its own median, half the weight to each
    group (market-implied, history) present, then placed at `centre`."""
    groups = {}
    for name, s in srcs.items():
        if s.get('qk') is not None:
            groups.setdefault(GROUP[name], []).append((name, s))
    if not groups:
        return None, {}
    weights = {}
    acc = np.zeros(len(PGRID))
    for g, members in groups.items():
        tot = sum(s['w'] for _, s in members) or 1
        for name, s in members:
            w = (1 / len(groups)) * s['w'] / tot
            weights[name] = round(w, 4)
            q = np.asarray(s['qk'], float)
            acc += w * (q - q[MED])
    return centre + acc, weights


def forecast_asset(spec, feed, cal, live=None, kladder=None, now=None, ladders=None, rng=None, regimes=None):
    key, sym, name, ixid, vols, fut = spec
    now = now or feed.now
    first, phase, frac = phase_of(now)
    rng = rng or np.random.default_rng(int(now.timestamp()) % 100000)
    q = (live or {}).get(key) or None
    if q is None:
        try:
            q = feed.quote(sym)
        except Exception as exc:                                       # noqa: BLE001
            log(f'{key}: {str(exc)[:120]}')
            return None
    price, prev = q.get('price'), q.get('prev')
    if not price:
        return None
    t_price = q.get('time')
    out = {'key': key, 'name': name, 'symbol': sym, 'price': _r(price, 4), 'prev': _r(prev, 4), 'phase': phase,
           'time': dt.datetime.fromtimestamp(t_price, UTC).astimezone(ET).isoformat() if isinstance(t_price, (int, float)) else t_price,
           'path': [[x, _r(p, 4)] for x, p in (q.get('path') or [])], 'start': _r(price, 4), 'targets': []}
    start = price
    if fut:
        # the last close the asset's price stands at: before the open and in the session, the session before today's;
        # after the close, today's (or the last session's on a holiday or a weekend)
        d0 = now.astimezone(ET).date()
        last_close = last_session_until(d0 - dt.timedelta(days=1)) if phase in ('pre', 'open') else last_session_until(d0)
        try:
            fm = feed.futures_move(fut, last_close)
            if fm:
                if phase == 'open' and prev:
                    fm['vs_asset'] = _r((1 + fm['move']) / (price / prev) - 1, 5)   # the future's move less the asset's
                out['futures'] = fm
                if phase in ('pre', 'closed') and fm.get('move') is not None and abs(fm['move']) < 0.08:
                    start = price * (1 + fm['move'])                  # where the next session is set to start
                    out['start'] = _r(start, 4)
        except Exception as exc:                                       # noqa: BLE001
            log(f'{key} futures: {str(exc)[:100]}')
    if ixid and IX.get(ixid):
        out['index'] = {'id': ixid, 'name': IX[ixid]['name'], 'symbol': IX[ixid]['symbol']}
    # the inputs
    chain = feed.chain(sym)
    if chain and chain.get('book'):
        out['book'] = chain['book'] | {'quote_time': chain.get('quote_time')}
    hist = feed.hourly(key, sym)
    d = feed.daily(key, sym)
    acal = (cal or {}).get('assets', {}).get(key) or {}
    vol_now = {}
    for tenor, vs in (vols or {}).items():
        try:
            vq = (live or {}).get(vol_key(vs)) or feed.quote(vs)
            if vq and vq.get('price'):
                vol_now[tenor] = float(vq['price'])
        except Exception as exc:                                       # noqa: BLE001
            log(f'{vs}: {str(exc)[:100]}')
    if vol_now:
        out['vol'] = {str(k): _r(v, 2) for k, v in sorted(vol_now.items())}
    ratio = None
    if ixid and IX.get(ixid):
        try:
            iq = (live or {}).get('IDX-' + IX[ixid]['symbol'].lstrip('^')) or feed.quote(IX[ixid]['symbol'])
            if iq and iq.get('price'):
                ratio = price / float(iq['price'])                     # asset per index point
                out['index'] |= {'price': _r(iq['price'], 2), 'ratio': _r(ratio, 8)}
        except Exception as exc:                                       # noqa: BLE001
            log(f'{key} index: {str(exc)[:100]}')
    # today's intraday pieces: the analogs' rest of the day, the factor centre
    j = None
    intra_rest = intra_hilo = None
    shift = 0.0
    if phase in ('open', 'pre') and hist and len((hist.get('cols') or [[]])[0]) >= 150:
        Mx = np.asarray(hist['cols'][1], float)
        if phase == 'open':
            mins = (now.astimezone(ET) - open_at(first)).total_seconds() / 60
            j = I.nearest_mark(min(max(mins, 0), 389))
            j = min(j, 6)
            move = math.log(price / prev) if prev else 0.0
        else:
            j = 0
            move = math.log(start / prev) if prev else 0.0
        m = np.log1p(Mx[:, j])
        rest = np.log((1 + Mx[:, 7]) / (1 + Mx[:, j]))
        ok = np.nonzero(np.isfinite(m) & np.isfinite(rest))[0]
        if len(ok) >= K_INTRADAY:
            near = ok[np.argpartition(np.abs(m[ok] - move), K_INTRADAY - 1)[:K_INTRADAY]]
            intra_rest = rest[near]
            cols = hist['cols']
            if len(cols) >= 6:                                         # their highs and lows from this hour to the close
                pad = lambda rows: np.array([x if x else [np.nan] * 7 for x in rows], float)   # noqa: E731
                HI, LO = pad(cols[4]), pad(cols[5])
                base = 1 + Mx[near, j]
                intra_hilo = (np.log((1 + np.nanmax(HI[near, j:7], axis=1)) / base), np.log((1 + np.nanmin(LO[near, j:7], axis=1)) / base))
        fm_ = ((acal.get('factors') or [None] * 7)[j]) if j is not None and j >= 1 else None
        out['factors'] = factor_view(fm_, q, prev, price, j) if phase == 'open' else {'mark': '09:30', 'shift': 0.0, 'applied': False,
                                                                                      'note': 'before the open: the factors start at 10:30'}
        shift = out['factors'].get('shift') or 0.0
    out['mark'] = I.MARKS[j] if j is not None else None
    # the daily pieces
    c = np.asarray((d or {}).get('ac') or [], float)
    mu, mu_own = drift((d or {}).get('c') or (d or {}).get('ac') or [])
    out['drift'] = {'session': _r(mu, 6), 'own': _r(mu_own, 6) if mu_own is not None else None, 'prior': DRIFT_PRIOR, 'prior_sd': DRIFT_SD}
    last = prev if phase == 'open' else price                          # the last close: yesterday's in the session, else the price
    out['last_close'] = _r(last, 4) if last else None
    r = s2 = f = None
    if len(c) > 900:
        r = np.concatenate([[0.0], np.diff(np.log(c))])
        s2 = ewma(r)
        f = features(c, s2)
    ts = targets(now, list((chain or {}).get('exps') or {}))
    n_max = max((sessions_after(first, dt.date.fromisoformat(t['date'])) for t in ts), default=0)
    cum = sim_paths(r, s2, len(c) - 1, max(n_max + (1 if phase != 'open' else 0), 1), rng=rng) if r is not None else None
    sd_f = np.nanstd(f[260:], axis=0) if f is not None else None
    lcl = np.log(c) if len(c) else None
    pct = move_pct(r) if r is not None else None
    if pct is not None and np.isfinite(pct[-1]):
        out['last_move'] = {'date': (d or {}).get('t', [None])[-1], 'move': _r(math.expm1(r[-1]), 5), 'pct': _r(pct[-1], 1)}
    if regimes:
        out['regimes'] = regimes
    lad = [x for x in (ladders or []) if x.get('end')]
    page = LADDER_PAGES.get(ixid) if ixid else key
    kl = (kladder or {}).get(page) or {}
    kall = (kladder or {}).get('*') or {}
    for t in ts:
        day = dt.date.fromisoformat(t['date'])
        n_after = sessions_after(first, day)                           # whole sessions after the first one
        close_t = close_at(day)
        cal_days = max((close_t - now).total_seconds() / 86400, 1 / 1440)
        lead_h = cal_days * 24
        bucket = L.bucket_of(lead_h)
        n_eq = n_after + (frac if phase == 'open' else 1.0)            # sessions of risk ahead, today's share included
        n_daily = n_after + (0 if phase == 'open' else 1)              # whole sessions after the last close (or today's)
        today_only = n_after == 0 and phase in ('open', 'pre')         # today's close: the intraday sources
        srcs = {}
        # options
        if chain and chain.get('exps'):
            exps = sorted(chain['exps'])
            e = t['date'] if t['date'] in chain['exps'] else next((x for x in exps if x >= t['date']), None)
            if e:
                sm = chain['exps'][e].get('smile') or []
                if len(sm) >= 4:
                    st = CS.ladder_stats(L.digital(sm, start, cal_days / 365))
                    if st:
                        qq = q_ladder(st['strikes'], st['p_above'], 1.0, start)
                        if qq is not None:
                            k = ((kl.get(bucket) or {}).get('options') or (kall.get(bucket) or {}).get('options') or 1.0)
                            sp = (chain.get('spreads') or {}).get(e)
                            srcs['options'] = {'q': qq, 'k': k, 'w': 0.5 if sp is not None and sp > 0.25 else 1.0, 'exp': e, 'exact': e == t['date'],
                                               'spread': sp, 'max_pain': chain['exps'][e].get('max_pain'), 'call_wall': chain['exps'][e].get('call_wall'),
                                               'put_wall': chain['exps'][e].get('put_wall'), 'as_of': chain.get('quote_time')}
        # prediction markets on this date
        mine = []
        for x in lad:
            if x['end'] != t['date']:
                continue
            ag = age_h(x.get('as_of'), now)
            if ag is None or ag > max_age_h(lead_h):
                continue                                               # read too long ago for a date this close
            u = x.get('units')
            if u == sym:
                to = 1.0
            elif ixid and IX.get(ixid) and u == IX[ixid]['symbol'] and ratio:
                to = ratio
            else:
                continue
            qq = q_ladder(x['strikes'], x['p_above'], to, start)
            if qq is not None:
                mine.append((qq, len(x['strikes']), x))
        if mine:
            wsum = sum(n for _, n, _ in mine)
            qq = sum(qx * n for qx, n, _ in mine) / wsum
            k = ((kl.get(bucket) or {}).get('markets') or (kall.get(bucket) or {}).get('markets') or 1.0)
            ovr = [x.get('overround') for _, _, x in mine if x.get('overround')]
            wide = any(o < 0.9 or o > 1.15 for o in ovr) or max(n for _, n, _ in mine) < 5
            srcs['markets'] = {'q': qq, 'k': k, 'w': 0.5 if wide else 1.0,
                               'ladders': [{'source': x['source'], 'kind': x['kind'], 'title': x.get('title'), 'url': x.get('url'), 'strikes': len(x['strikes']),
                                            'overround': x.get('overround'), 'as_of': x.get('as_of'), 'age_h': _r(age_h(x.get('as_of'), now), 2)} for _, _, x in mine]}
        # implied volatility
        if vol_now:
            if today_only:
                mins = (close_t - max(now.astimezone(ET), open_at(first))).total_seconds() / 60
                sg = implied_sigma(vol_now, None, minutes=mins)        # VIX1D (else the nearest tenor) over the minutes left
                kk = ((acal.get('intraday') or {}).get('implied') or [None] * 7)[j] if j is not None else None
                kv = (kk or {}).get('k')
            else:
                sg = implied_sigma({k: v for k, v in vol_now.items() if k != 1} or vol_now, n_eq * 7 / 5)
                kv = k_at((acal.get('daily') or {}).get('implied'), n_daily)
            if sg:
                srcs['implied'] = {'q': q_normal(-sg * sg / 2, sg), 'k': kv or 1.0, 'w': 1.0, 'sigma': _r(sg, 5),
                                   'tenors': sorted(vol_now) if not today_only else [1 if 1 in vol_now else min(vol_now)]}
        # analogs
        if today_only:
            if intra_rest is not None:
                kk = ((acal.get('intraday') or {}).get('analogs') or [None] * 7)[j]
                srcs['analogs'] = {'q': q_samples(intra_rest), 'k': (kk or {}).get('k') or 1.0, 'w': 1.0, 'n': int(len(intra_rest)), 'mark': I.MARKS[j]}
        elif f is not None and n_daily >= 1:
            s = analog_sample(c, s2, f, len(c) - 1, n_daily, sd=sd_f)
            if s is not None:
                if phase == 'open' and intra_rest is not None:
                    s = rng.choice(s, 4000) + rng.choice(intra_rest, 4000)   # the rest of today, then the sessions after
                srcs['analogs'] = {'q': q_samples(s), 'k': k_at((acal.get('daily') or {}).get('analogs'), n_daily) or 1.0, 'w': 1.0, 'n': K_DAILY,
                                   'sessions': n_daily}
        # Move odds: after days whose last move was as rare as this one
        if pct is not None and not today_only and n_daily >= 1:
            s = moves_sample(lcl, pct, len(c) - 1, n_daily, skip=1 if phase == 'open' else 0)
            if s is not None:
                nm = int(len(s))
                if phase == 'open' and intra_rest is not None:
                    s = rng.choice(s, 4000) + rng.choice(intra_rest, 4000)
                srcs['moves'] = {'q': q_samples(s), 'k': k_at((acal.get('daily') or {}).get('moves'), n_daily) or 1.0, 'w': 1.0, 'n': nm,
                                 'sessions': n_daily, 'pct': _r(pct[-1], 1)}
        # the regime it is in now (at its highs, at a low, in a range): its analogues' returns, from two weeks out
        if regimes and not today_only and n_daily >= 10:
            for rg in regimes:
                qq = regime_q(rg.get('analogues'), n_daily)
                if qq is not None:
                    srcs['regime'] = {'q': qq, 'k': 1.0, 'w': 0.5, 'regime': rg['regime'], 'label': rg['label'],
                                      'n': (rg['analogues'].get('fwd21' if n_daily <= 32 else 'fwd63') or {}).get('n'), 'calibrated': False}
                    break
        # simulation
        if cum is not None and not today_only and n_daily >= 1:
            x = cum[:, n_daily - 1]
            if phase == 'open':
                x = x + rng.normal(0, math.sqrt(s2[-1] * frac), len(x))
            srcs['sim'] = {'q': np.quantile(x, PG), 'k': k_at((acal.get('daily') or {}).get('sim'), n_daily) or 1.0, 'w': 1.0, 'paths': int(len(x)),
                           'sessions': n_daily}
        for s in srcs.values():
            s['qk'] = scale(s['q'], s['k']) if s.get('q') is not None else None
        centre = mu * n_eq + (shift if today_only else 0.0)            # the price now, the drift to then (the factors' shift, today)
        pooled, weights = pool(srcs, centre)
        if pooled is None:
            continue
        pooled = np.maximum.accumulate(pooled)
        if today_only and intra_hilo is not None:
            kk = (((acal.get('intraday') or {}).get('analogs') or [None] * 7)[j] or {}).get('k') or 1.0
            hq, lq = q_samples(intra_hilo[0]), q_samples(intra_hilo[1])
            hilo = {'method': 'analogs', 'n': int(len(intra_hilo[0])), 'k': kk,
                    'high': [_r(max(0.0, v * kk), 6) for v in hq] if hq is not None else None,
                    'low': [_r(min(0.0, v * kk), 6) for v in lq] if lq is not None else None}
            pth = [x for _, x in (q.get('path') or [])]
            if pth and phase == 'open':
                hilo['so_far'] = [_r(math.log(max(pth) / start), 6), _r(math.log(min(pth) / start), 6)]
        else:                                                          # the reflection principle: P(max > x) = 2 P(close > x)
            hilo = {'method': 'reflection',
                    'high': [_r(max(0.0, float(np.interp(ND.inv_cdf((1 + p_) / 2), ZG, pooled))), 6) for p_ in PGRID],
                    'low': [_r(min(0.0, float(np.interp(ND.inv_cdf(p_ / 2), ZG, pooled))), 6) for p_ in PGRID]}
        tgt = {'date': t['date'], 'tags': t['tags'], 'close_at': close_t.isoformat(), 'sessions': n_after, 'risk_sessions': _r(n_eq, 3), 'lead_h': _r(lead_h, 2),
               'bucket': bucket, 'centre': _r(centre, 6), 'q': [_r(v, 6) for v in pooled], 'weights': weights,
               'p_up': _r(1 - cdf_at(pooled, 0.0), 4), 'p_prev': _r(1 - cdf_at(pooled, math.log(last / start)), 4) if last else None,
               'src_up': _r(sum(weights.get(n, 0) * (1 - cdf_at(s['qk'], 0.0)) for n, s in srcs.items() if s.get('qk') is not None), 4),
               'hilo': hilo, 'src': {}}
        for name_, s in srcs.items():
            info = {k: v for k, v in s.items() if k not in ('q', 'qk', 'w')}
            info['k'] = _r(s.get('k'), 3)
            info['w'] = weights.get(name_, 0.0)
            info['q'] = [_r(v, 6) for v in s['qk']] if s.get('qk') is not None else None
            info['raw_median'] = _r(float(np.asarray(s['q'])[MED]), 6) if s.get('q') is not None else None
            tgt['src'][name_] = info
        out['targets'].append(tgt)
    return out


def factor_view(fm, q, prev, price, j):
    """The factor model at mark j, today's inputs and the centre it moves (zero when it did not predict out of sample)."""
    v = {'mark': I.MARKS[j] if j is not None else None, 'shift': 0.0, 'applied': False}
    if not fm:
        v['note'] = 'no model at this hour'
        return v
    v |= {'r2_oos': fm.get('r2_oos'), 'n': fm.get('n'), 'coef': fm.get('coef')}
    vw = q.get('vwap_path') or []
    path = q.get('path') or []
    if not prev or not path or not vw:
        v['note'] = 'no VWAP for this asset (an index) or no bars yet'
        return v
    first_hour = None
    p_open = path[0][1] if path else None
    p_1030 = next((p for x, p in path if x >= 60), None)
    if p_open and p_1030:
        first_hour = math.log(p_1030 / p_open)
    x = [1.0, math.log(price / prev), math.log(price / vw[-1][1]), first_hour if first_hour is not None else 0.0]
    pred = float(np.dot(fm['coef'], x)) if fm.get('coef') and all(c is not None for c in fm['coef']) else 0.0
    v['inputs'] = {'move': _r(x[1], 5), 'vs_vwap': _r(x[2], 5), 'first_hour': _r(first_hour, 5)}
    v['predicted'] = _r(pred, 6)
    r2 = fm.get('r2_oos')
    if r2 is not None and r2 > 0.005:
        v['shift'] = _r(pred, 6)
        v['applied'] = True
    else:
        v['note'] = 'did not predict the close better than zero out of sample: not applied'
    return v


# ------------------------------------------------------------------ the official freezes
def freeze_due(now, done=()):
    """The freeze slot due now ('09:45' …) on a session: within FREEZE_WINDOW_MIN minutes after it and not done yet."""
    t = now.astimezone(ET)
    if not is_session(t.date()) or t >= close_at(t.date()):
        return None
    for s in FREEZES:
        hh, mm = map(int, s.split(':'))
        at = t.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if at <= t < at + dt.timedelta(minutes=FREEZE_WINDOW_MIN) and f'{t.date().isoformat()} {s}' not in done:
            return s
    return None


def freeze_doc(fc, slot):
    """The compact frozen copy of a forecast: per asset and target the pooled quantiles in price, each source's 2.5, 10,
    50, 90 and 97.5% (in price)."""
    sel = [PGRID.index(p) for p in (0.025, 0.1, 0.5, 0.9, 0.975)]
    day = dt.datetime.fromisoformat(fc['generated_at']).astimezone(ET).date().isoformat()
    out = {'slot': f'{day} {slot}', 'day': day, 'time': slot, 'at': fc['generated_at'], 'pgrid': list(PGRID), 'assets': {}}
    for k, a in (fc.get('assets') or {}).items():
        s0 = a.get('start') or a.get('price')
        if not s0:
            continue
        out['assets'][k] = {'start': s0, 'prev': a.get('prev'), 'targets': [
            {'date': t['date'], 'tags': t['tags'], 'bucket': t['bucket'], 'lead_h': t['lead_h'],
             'q': [round(s0 * math.exp(v), 4) for v in t['q']],
             'src': {n: [round(s0 * math.exp(s['q'][i]), 4) for i in sel] for n, s in t['src'].items() if s.get('q')}}
            for t in a.get('targets') or []]}
    return out


def score(frozen_q, actual):
    """PIT, inside 50/80/95%, the median's error and the mean quantile (pinball) loss of one frozen forecast (prices)."""
    q = np.asarray(frozen_q, float)
    lq = np.log(q)
    y = math.log(actual)
    pit = cdf_at(lq, y)
    ins = {str(c): bool(interval(lq, c)[0] <= y <= interval(lq, c)[1]) for c in LEVELS}
    pin = float(np.mean([(p - (y < v)) * (y - v) for p, v in zip(PGRID, lq)]))
    return {'pit': round(pit, 4), 'inside': ins, 'err': round(actual / q[MED] - 1, 5), 'pinball': round(pin, 6)}


def ledger(root, freeze=None, closes=None, now=None):
    """File a freeze (once per slot), score every frozen target whose close is known, publish public/record.json."""
    root = Path(root)
    now = now or dt.datetime.now(UTC)
    (root / 'ledger').mkdir(parents=True, exist_ok=True)
    (root / 'public').mkdir(parents=True, exist_ok=True)
    added = False
    if freeze:
        p = root / 'ledger' / f"{freeze['day'][:7]}.json"
        doc = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'freezes': []}
        if not any(f['slot'] == freeze['slot'] for f in doc['freezes']):
            doc['freezes'].append(freeze)
            doc['freezes'].sort(key=lambda f: f['slot'])
            p.write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')
            added = True
    closes = closes or {}
    rows = []
    months = sorted((root / 'ledger').glob('*.json'))[-4:]
    for p in months:
        doc = json.loads(p.read_text(encoding='utf-8'))
        changed = False
        for fz in doc['freezes']:
            for k, a in fz['assets'].items():
                for t in a['targets']:
                    if 'score' not in t:
                        y = (closes.get(k) or {}).get(t['date'])
                        if y:
                            t['actual'] = y
                            t['score'] = score(t['q'], y)
                            t['src_inside80'] = {n: bool(v[1] <= y <= v[3]) for n, v in (t.get('src') or {}).items()}
                            changed = True
                    if 'score' in t:
                        rows.append({'slot': fz['slot'], 'time': fz['time'], 'asset': k, 'date': t['date'], 'tags': t['tags'], 'bucket': t['bucket'],
                                     'start': a['start'], 'actual': t['actual'], 'q50': t['q'][MED], 'lo80': t['q'][PGRID.index(0.1)],
                                     'hi80': t['q'][PGRID.index(0.9)], **t['score'], 'src80': t.get('src_inside80')})
        if changed:
            p.write_text(json.dumps(doc, separators=(',', ':')), encoding='utf-8')

    def summary(sel):
        if not sel:
            return None
        return {'n': len(sel), 'inside': {str(c): round(float(np.mean([r['inside'][str(c)] for r in sel])), 3) for c in LEVELS},
                'mae': round(float(np.mean([abs(r['err']) for r in sel])), 5), 'pinball': round(float(np.mean([r['pinball'] for r in sel])), 6),
                'src80': {n: round(float(np.mean([r['src80'][n] for r in sel if r.get('src80') and n in r['src80']])), 3)
                          for n in SOURCES if any(r.get('src80') and n in r['src80'] for r in sel)}}
    buckets = [b for _, _, b in L.BUCKETS]
    latest = {}
    for p in months[-1:]:
        doc = json.loads(p.read_text(encoding='utf-8'))
        for fz in doc['freezes'][-6:]:
            latest[fz['slot']] = fz
    record = {'generated_at': now.isoformat(timespec='seconds'), 'pgrid': list(PGRID), 'n': len(rows),
              'all': summary(rows), 'by_bucket': {b: summary([r for r in rows if r['bucket'] == b]) for b in buckets},
              'by_time': {s: summary([r for r in rows if r['time'] == s]) for s in FREEZES},
              'by_asset': {a[0]: summary([r for r in rows if r['asset'] == a[0]]) for a in ASSETS},
              'recent': sorted(rows, key=lambda r: (r['date'], r['slot']), reverse=True)[:300],
              'latest': [latest[k] for k in sorted(latest)][-6:]}
    (root / 'public' / 'record.json').write_text(json.dumps(record, separators=(',', ':')), encoding='utf-8')
    return {'added': added, 'scored': len(rows)}


# ------------------------------------------------------------------ the run
def run(out, cache, h60, live_path=None, now=None, feed=None, assets=None, log_=log):
    now = now or dt.datetime.now(UTC)
    feed = feed or Feed(cache, h60, now)
    t0 = time.time()
    live = {}
    if live_path and Path(live_path).exists():
        try:
            doc = json.loads(Path(live_path).read_text(encoding='utf-8'))
            for k, a in (doc.get('assets') or {}).items():
                if a.get('price') and a.get('prev'):
                    tt = dt.datetime.fromisoformat(a['time']).timestamp() if a.get('time') else None
                    live[k] = {'price': a['price'], 'prev': a['prev'], 'time': tt,
                               'path': [[x, a['prev'] * (1 + v)] for x, v in a.get('path') or []],
                               'vwap_path': [[x, a['prev'] * (1 + v)] for x, v in a.get('vwap_path') or []] or None}
        except (OSError, ValueError, KeyError) as exc:
            log_(f'live.json: {exc}')
    cal = calibration(feed, log_, assets)
    kl = feed.ladder_k()
    lad = feed.ladders()
    try:
        regs = feed.regimes()
    except Exception as exc:                                           # noqa: BLE001
        log_(f'regimes: {exc}')
        regs = {}
    first, phase, frac = phase_of(now)
    fc = {'schema': SCHEMA, 'generated_at': now.isoformat(timespec='seconds'), 'phase': phase, 'first': first.isoformat(),
          'share_left': _r(frac, 4), 'pgrid': list(PGRID), 'levels': list(LEVELS), 'freezes': list(FREEZES),
          'calibration': {'refreshed': cal.get('refreshed'), 'seconds': cal.get('seconds')}, 'assets': {}, 'errors': []}
    for spec in ASSETS:
        if assets and spec[0] not in assets:
            continue
        try:
            a = forecast_asset(spec, feed, cal, live=live, kladder=kl, now=now, ladders=lad, regimes=regs.get(spec[0]))
        except Exception as exc:                                       # noqa: BLE001 — one asset's failure never stops the run
            fc['errors'].append(f'{spec[0]}: {str(exc)[:160]}')
            log_(f'{spec[0]}: {exc}')
            continue
        if a:
            a['calibration'] = calib_summary((cal.get('assets') or {}).get(spec[0]) or {})
            fc['assets'][spec[0]] = a
    fc['seconds'] = round(time.time() - t0, 1)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'forecast.json').write_text(json.dumps(fc, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    done = _done_slots(cache)
    slot = freeze_due(now, done=done)
    due = None
    if slot and fc['assets']:
        fz = freeze_doc(fc, slot)
        (out / 'freeze.json').write_text(json.dumps(fz, separators=(',', ':')), encoding='utf-8')
        due = fz['slot']
    elif phase == 'closed':                                           # after a session: score what it closed, once
        last = last_session_until(now.astimezone(ET).date())
        if now >= close_at(last) + dt.timedelta(minutes=15) and f'{last.isoformat()} close' not in done:
            due = f'{last.isoformat()} close'
    if due:
        (out / 'ledger_due').write_text(due, encoding='utf-8')         # scripts/forecast-publish.sh files it on forecast-ledger
    closes = {}
    for spec in ASSETS:
        d = feed._read(f'daily/{spec[0]}.json')
        if d and d.get('t'):
            closes[spec[0]] = dict(zip(d['t'][-80:], d['c'][-80:]))
    (out / 'closes.json').write_text(json.dumps(closes, separators=(',', ':')), encoding='utf-8')
    return fc


def calib_summary(a):
    """The k's in short, for the page: intraday per mark, daily at 1, 5, 21 and 63 sessions, the factors' out-of-sample R²."""
    s = {}
    intra = a.get('intraday') or {}
    for src in ('analogs', 'implied'):
        if intra.get(src):
            s[f'intraday_{src}'] = [None if x is None else {'k': x['k'], 'n': x['n'], 'raw': x['raw'], 'fit': x['fit']} for x in intra[src]]
    daily = a.get('daily') or {}
    for src in ('analogs', 'moves', 'sim', 'implied'):
        if daily.get(src):
            s[f'daily_{src}'] = {h: daily[src].get(h) for h in ('1', '5', '21', '63') if daily[src].get(h)}
    if a.get('factors'):
        s['factors_r2'] = [None if x is None else x.get('r2_oos') for x in a['factors']]
    return s


def _done_slots(cache):
    try:
        return set(json.loads((Path(cache) / 'frozen.json').read_text(encoding='utf-8')))
    except (OSError, ValueError):
        return set()


def mark_frozen(cache, slot):
    p = Path(cache) / 'frozen.json'
    s = _done_slots(cache) | {slot}
    p.write_text(json.dumps(sorted(s)[-60:]), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd')
    lg = sub.add_parser('ledger')
    lg.add_argument('--root', required=True)
    lg.add_argument('--freeze')
    lg.add_argument('--closes')
    mf = sub.add_parser('frozen')
    mf.add_argument('--cache', required=True)
    mf.add_argument('--slot', required=True)
    ap.add_argument('--out', default='fcout')
    ap.add_argument('--cache', default='fc')
    ap.add_argument('--h60', default='h60')
    ap.add_argument('--live')
    ap.add_argument('--assets', help='comma-separated keys (a check)')
    a = ap.parse_args()
    if a.cmd == 'ledger':
        fz = json.loads(Path(a.freeze).read_text(encoding='utf-8')) if a.freeze and Path(a.freeze).exists() else None
        cl = json.loads(Path(a.closes).read_text(encoding='utf-8')) if a.closes and Path(a.closes).exists() else None
        print(json.dumps(ledger(a.root, fz, cl)))
        return
    if a.cmd == 'frozen':
        mark_frozen(a.cache, a.slot)
        return
    fc = run(a.out, a.cache, a.h60, a.live, assets=set(a.assets.split(',')) if a.assets else None)
    print(json.dumps({'assets': len(fc['assets']), 'targets': sum(len(x['targets']) for x in fc['assets'].values()), 'phase': fc['phase'],
                      'seconds': fc['seconds'], 'errors': fc['errors'][:6]}))


if __name__ == '__main__':
    main()
