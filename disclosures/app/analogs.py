"""Price paths & patterns: where a stock's price may go over the next 63 trading days (about 13 weeks), by historical
simulation.

Every method answers one question, "the last times things looked like this, what happened next?", and returns the
spread of what happened as quantiles of the cumulative log return r_d = log(price on day d ÷ price today), d = 1 … horizon.
The site draws the fan as price today × e^(quantile). No parameter is tuned to make a fan look good: the spread is the
spread of real past outcomes, and evaluate() scores every method walk-forward against a naive baseline.

Inputs
  A price series is (dates, ac): dates as 'YYYY-MM-DD', ac the dividend- and split-adjusted closes, daily, oldest first.
  A missing or non-positive close is carried forward from the last good one (leading ones are dropped). A universe is
  {ticker: (dates, ac)}: about 1,750 stocks plus ETFs (exchange-traded funds: SPY, the SPDR S&P 500 ETF Trust, and the
  sector funds). prepare_universe() converts a universe once when it is used many times (evaluate_universe does).

(A) Analogues: the method of analogues (Lorenz 1969). Describe today by a feature vector, find the past days whose
    feature vectors were nearest, and use what followed each of them as one possible future.

  Features of day t (its "state"), computed from the closes up to and including t only:
    shape  the log-price path over the last L = lookback days, rebased to 0 at its start and divided by its own
           realized volatility:   s_j = (log P[t−L+j] − log P[t−L]) ÷ (σ_L × L),   j = 1 … L,
           where σ_L is the realized volatility of those L daily log returns. Realized volatility here and below is
           the root mean square of daily log returns (no mean removed, the usual definition), so a steady trend does
           not divide by ~0 and every s_j lies in [−1, 1]. With this scaling the squared distance between two shape
           blocks is the mean squared gap between their volatility-normalized paths (each path in units of σ_L × √L),
           about 1 for two unrelated random-walk windows. Dividing by the window's own volatility makes the match about
           the shape of the move, not its size, so a calm stock's past can match a volatile stock's present.
    vol    W_VOL × log(σ_21 ÷ σ_252) ÷ 0.35: is volatility over the last month high or low against the last year?
           0.35 is the typical spread of that log ratio for US stocks, so the unweighted feature has a spread of ~1.
    year   W_RET × (log P[t] − log P[t−252]) ÷ (σ_252 × √252): the 252-day return in units of its own one-year
           volatility (standard normal for a random walk), so the feature means the same for a utility and a biotech.
  Weights: W_VOL = W_RET = 0.35. For two unrelated days the shape then makes up about two thirds of the squared
  distance and each scale feature about one sixth: the shape decides, the scale features break ties between similar
  shapes that happened in very different regimes.
  Distance: Euclidean (straight-line) distance between feature vectors.

  Candidates: every past day t whose features exist and with t + horizon ≤ the as-of day, so the whole future after
  each analogue was known on the forecast date (no look-ahead).
  Selection: the k nearest, greedily and without overlap: take the nearest candidate, drop every candidate within
  min_gap trading days of it (default min_gap = horizon), repeat. Analogues therefore never share any part of their
  futures; overlapping futures would count one episode several times and make the fan look surer than it is. One
  stock's past holds only so many non-overlapping futures (2,500 bars about 25 at a 63-day horizon), so fewer than k
  may come back: 'k' in the output is the number used.
  Weights: w_i = exp(−d_i² ÷ (2 × median_j d_j²)), a Gaussian kernel whose bandwidth is the median analogue distance,
  normalized to sum to 1: the closest matches count most, but no single one dominates.
  Fan ('q'): for each day d of the horizon, the weighted 5/10/25/50/75/90/95% quantiles of the analogues' cumulative
  log returns (weighted quantile: sort the values, place each at the middle of its share of the cumulative weight,
  interpolate linearly). 'end' = the same quantiles at the horizon; 'mean' = the weighted mean outcome; 'p_up' = the
  total weight of the analogues that ended higher.
  Similarity (0–1): 1 − (mean analogue distance ÷ median distance from today to every candidate window, i.e. to a
  random past window), floored at 0. Near 1: today has close precedents. Near 0: the best matches are hardly closer
  than a random day, and the fan is close to an unconditional one.
  Short histories: fewer than lookback + horizon + 50 bars gives None. Between that and 252 + horizon + 50 bars, the
  one-year window shrinks to (bars − horizon − 50) days so that at least 50 candidate days remain.

  self_analogs     the stock's own past only.
  pooled_analogs   every stock's past (the library, build_library): the same features at every sample_step-th day of
                   every ticker (counted back from its newest eligible day; the step grows if the library would exceed
                   max_lib rows), with the forward path stored beside each row. Rows are only windows whose forward
                   period ends on or before the library's end date. A query computes d² = |F|² − 2 F·q + |q|² in
                   chunks of float32 matrix products (F the library rows, q today's features); the shortlist of the
                   nearest max(40k, 2,000) rows is re-ranked by the exact distance in float64. Selection: no two
                   analogues from the same ticker within min_gap trading days, and at most per_period (default
                   max(2, k ÷ 10)) analogues from different stocks within 0.7 × min_gap calendar days of each other
                   (about half a horizon): otherwise one market-wide move (say March 2020) could supply every analogue
                   and the fan would be one episode counted fifty times. The target itself needs only lookback + 50 bars (the outcomes come from
                   other stocks); with less than a year of history its year features use the history it has.

(B) Correlated assets: historical simulation conditioned on the assets that move with (or ahead of) the stock.
  weekly_matrix      weekly log returns of the whole universe on one grid, built once: week ends every 7 calendar days
                     back from end_date (so every week ends on end_date's weekday), the close of a week = the last bar
                     in the 7 days up to its end (none: missing).
  correlated_peers   Pearson correlation of weekly log returns over the last `window` trading days (window × 52 ÷ 252
                     weeks), on the weeks both have (at least 80% of them); the target itself is excluded (by ticker,
                     and any series whose weekly returns are an exact copy of it). Lead-lag: the correlation of the
                     peer's return in week t − lag with the target's in week t, lag = 1 … max_lag weeks; best_lag
                     maximizes its absolute value. lead_p is the two-sided p-value of that best lead correlation by
                     the Fisher z transform: z = atanh(r) × √(n − 3) is about standard normal when there is no
                     correlation, p = 2 × (1 − Φ(|z|)) = erfc(|z| ÷ √2) (Φ the normal cumulative distribution function;
                     erfc the complementary error function, the same quantity as 1 − erf computed without rounding
                     loss), times max_lag (Bonferroni adjustment: the best of max_lag lags was picked), capped at 1.
                     Only the top peers by contemporaneous correlation are tested, so the family of tests is the lags;
                     a scan over all 1,750 tickers by lead would find ~5% "leaders" by chance and is not offered.
                     Sorted by |corr|, largest first.
  peer_conditional   features of each day = the cumulative log returns over each window in `windows` (5, 21, 63 days)
                     of the equal-weight peer basket (the mean of the peers' log returns, needing at least half of them
                     to have prices), of SPY (when it is in the universe, as its own block), and of the target itself,
                     each divided by its standard deviation over the days up to the as-of day. The k nearest past days
                     (non-overlapping, future fully known before as_of, weights as above) give the TARGET's subsequent
                     cumulative returns: "when this stock and the assets that move with it last looked like this, what
                     did this stock do next?"
  lead_lag_forecast  OLS (ordinary least squares) regression of the target's next-`horizon`-day log return on each
                     leader's log return over its last `best_lag` weeks (5 × lag trading days; only peers with
                     lead_p < 0.05), with an intercept, fitted on the `train` days before as_of whose outcomes were
                     known by then. Forecast quantiles by a residual bootstrap: re-draw the residuals in blocks of
                     `horizon` days (the overlapping outcomes are autocorrelated), refit, forecast, and add one more
                     re-drawn residual; 1,000 draws with a fixed seed. None when no peer is a significant leader.
                     r2_in is in-sample and flattered by the overlapping outcomes: evaluate() is the test.

Evaluation (walk-forward): evaluate() forecasts at each origin from data on or before it only (the pooled library and
the weekly matrix are rebuilt to end at the origin, and peers are re-selected), then compares the horizon quantiles
with the realized cumulative return:
  cover80 / cover50  share of outcomes inside the 10–90% / 25–75% band (a calibrated fan gives 0.80 / 0.50)
  pinball            mean pinball (quantile) loss over the 7 published quantile levels 0.05 … 0.95:
                     L_τ(y, q) = max(τ × (y − q), (τ − 1) × (y − q)); lower is better, rewarding sharp and calibrated fans
  ic                 IC (information coefficient): Spearman rank correlation between the forecast median and the
                     realized return across origins (implemented here: Pearson correlation of average ranks)
  pit                PIT (probability integral transform): the forecast distribution function at the realized value,
                     interpolated between the quantiles (0.025 / 0.975 when outside the 5–95% band); uniform on [0, 1]
                     when the fans are calibrated. pit_hist counts them in ten bins.
  Methods 'self', 'pooled', 'peer', 'leadlag' and the 'naive' baseline: the stock's own trailing-252-day distribution of
  63-day returns (the horizon returns ending on each of the last 252 days, unweighted quantiles). Those windows overlap,
  so they hold only about four independent moves and the band is too narrow (cover80 ≈ 0.65–0.7 on a random walk).
  evaluate_universe() pools origins over many tickers (bounded: by default at most 100 tickers × 12 origins, evenly
  spaced subsets), reuses one library / weekly matrix per origin, and adds ic_xs, the mean cross-sectional IC per origin.

Every number returned is finite (no NaN): missing values are None or the result is None. Pure numpy; deterministic.

Usage
  import analogs as A
  out = A.self_analogs(dates, ac)                       # the stock's own past
  lib = A.build_library(universe, 60, 63, 5, '2026-10-23'); out = A.pooled_analogs('NVDA', universe, lib=lib)
  wm = A.weekly_matrix(universe, '2026-10-23', 108); peers = A.correlated_peers(dates, ac, universe, wm=wm)
  A.peer_conditional('NVDA', peers, universe); A.lead_lag_forecast('NVDA', peers, universe)
  A.evaluate_universe('pooled', universe, tickers, ['2023-01-03', '2023-04-03', ...])
"""
import math

import numpy as np

QS = np.array([0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95])
QK = ('q05', 'q10', 'q25', 'q50', 'q75', 'q90', 'q95')
LONG = 252              # one trading year: the long volatility window and the yearly return
SHORT = 21              # one trading month: the short volatility window
W_VOL = 0.35            # weight of the volatility-ratio feature
W_RET = 0.35            # weight of the yearly-return feature
VOL_SPREAD = 0.35       # typical spread of log(21-day vol ÷ 252-day vol) for US stocks
VOL_FLOOR = 1e-6        # realized volatility floor (a flat, halted series)
MIN_EXTRA = 50          # a history needs lookback + horizon + 50 bars
CHUNK = 65536           # library rows per matrix product
LEAD_ALPHA = 0.05       # a peer is a leader when its Bonferroni-adjusted lead p-value is below this
SEED = 20261025
METHODS = ('self', 'pooled', 'peer', 'leadlag', 'naive')


# ------------------------------------------------------------------ series
class Series:
    """A price series ready for the methods: day numbers (days since 1970-01-01) and log adjusted closes."""
    __slots__ = ('days', 'lp', 'offset')

    def __init__(self, days, lp, offset=0):
        self.days, self.lp, self.offset = days, lp, offset

    def __len__(self):
        return len(self.lp)

    def head(self, i):
        """The series up to and including bar i."""
        return Series(self.days[:i + 1], self.lp[:i + 1], self.offset)

    def date(self, i):
        return _datestr(self.days[i])


def _datestr(day):
    return str(np.datetime64(int(day), 'D'))


def _day(x):
    """'YYYY-MM-DD' (or a date / numpy datetime64) -> days since 1970-01-01."""
    return int(np.datetime64(x, 'D').astype(np.int64))


def _to_days(dates):
    if isinstance(dates, np.ndarray):
        if dates.dtype.kind in 'iu':
            return dates.astype(np.int64)
        return dates.astype('datetime64[D]').astype(np.int64)
    return np.array(dates, dtype='datetime64[D]').astype(np.int64)


def to_series(dates, ac):
    """(dates, adjusted closes) -> Series; bad closes carried forward, leading bad ones dropped."""
    days = _to_days(dates)
    a = np.array(ac, dtype=float)
    n = min(len(days), len(a))
    days, a = days[:n], a[:n]
    ok = np.isfinite(a) & (a > 0)
    if not ok.any():
        return Series(np.zeros(0, np.int64), np.zeros(0), 0)
    first = int(np.argmax(ok))
    idx = np.maximum.accumulate(np.where(ok, np.arange(n), 0))[first:]
    return Series(days[first:], np.log(a[idx]), first)


def _as_series(x, ac=None):
    if isinstance(x, Series):
        return x
    if ac is not None:
        return to_series(x, ac)
    if isinstance(x, (tuple, list)) and len(x) == 2:
        return to_series(x[0], x[1])
    raise TypeError('expected (dates, ac) or a Series')


def prepare_universe(universe):
    """{ticker: (dates, ac)} -> {ticker: Series}, converted once (every function accepts either form)."""
    if all(isinstance(v, Series) for v in universe.values()):
        return universe
    return {t: _as_series(v) for t, v in universe.items()}


def _target(target, universe):
    """(Series, ticker or None) for a ticker in the universe or a (dates, ac) / Series target."""
    if isinstance(target, str):
        if universe is None or target not in universe:
            return None, target
        return _as_series(universe[target]), target
    return _as_series(target), None


def _asof_index(S, as_of):
    """Index of the as-of bar: None -> the last bar; an int -> that index of the original arrays; a date -> the last
    bar on or before it (-1 when the series starts later)."""
    if as_of is None:
        return len(S) - 1
    if isinstance(as_of, (int, np.integer)) and not isinstance(as_of, bool):
        return min(int(as_of) - S.offset, len(S) - 1)
    return int(np.searchsorted(S.days, _day(as_of), side='right')) - 1


def _align(S, days, max_gap=7):
    """S's log close on each of `days`: its last bar on or before the day if within max_gap calendar days, else NaN."""
    out = np.full(len(days), np.nan)
    if not len(S):
        return out
    i = np.searchsorted(S.days, days, side='right') - 1
    ii = np.maximum(i, 0)
    ok = (i >= 0) & (days - S.days[ii] <= max_gap)
    out[ok] = S.lp[ii[ok]]
    return out


def _wret(x, w):
    """Cumulative log return over the last w bars at every bar (NaN where undefined)."""
    out = np.full(len(x), np.nan)
    if 0 < w < len(x):
        out[w:] = x[w:] - x[:-w]
    return out


# ------------------------------------------------------------------ small numerics
def _r(x, nd=4):
    x = float(x)
    return round(x, nd) if math.isfinite(x) else 0.0


def _rlist(a, nd=4):
    a = np.asarray(a, dtype=float)
    return np.round(np.where(np.isfinite(a), a, 0.0), nd).tolist()


def _kernel(dist):
    """w_i = exp(−d_i² ÷ (2 × median d²)), normalized to sum to 1."""
    d2 = np.asarray(dist, float) ** 2
    m = max(float(np.median(d2)), 1e-24)
    w = np.maximum(np.exp(-d2 / (2 * m)), 1e-12)
    return w / w.sum()


def _wq(V, w, qs=QS):
    """Weighted quantiles of each column of V (k × H): sort, place each value at the middle of its cumulative weight,
    interpolate linearly. Returns (len(qs) × H)."""
    V = np.asarray(V, float)
    if V.ndim == 1:
        V = V[:, None]
    order = np.argsort(V, axis=0, kind='stable')
    Vs = np.take_along_axis(V, order, axis=0)
    Ws = np.asarray(w, float)[order]
    C = np.cumsum(Ws, axis=0)
    P = (C - Ws / 2) / C[-1]
    out = np.empty((len(qs), V.shape[1]))
    for h in range(V.shape[1]):
        out[:, h] = np.interp(qs, P[:, h], Vs[:, h])
    return out


def rankdata(x):
    """Ranks 1 … n, ties given the average of the ranks they span."""
    x = np.asarray(x, float)
    n = len(x)
    if n == 0:
        return np.zeros(0)
    order = np.argsort(x, kind='mergesort')
    xs = x[order]
    brk = np.r_[True, xs[1:] != xs[:-1], True]
    starts = np.nonzero(brk)[0]
    grp = np.cumsum(brk[:-1]) - 1
    avg = (starts[:-1] + starts[1:] - 1) / 2 + 1
    ranks = np.empty(n)
    ranks[order] = avg[grp]
    return ranks


def spearman(a, b):
    """Spearman rank correlation (Pearson correlation of average ranks) over the pairs where both are finite; None
    with fewer than 3 pairs or a constant side."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return None
    ra, rb = rankdata(a[ok]), rankdata(b[ok])
    ra, rb = ra - ra.mean(), rb - rb.mean()
    den = math.sqrt(float((ra * ra).sum() * (rb * rb).sum()))
    return float((ra * rb).sum() / den) if den > 0 else None


def _pcorr(X, y):
    """Pearson correlation of every column of X with y over the rows where both are finite (pairwise complete).
    Returns (r, n); r is NaN where n < 3 or a side is constant."""
    M = np.isfinite(X) & np.isfinite(y)[:, None]
    n = M.sum(axis=0)
    nn = np.maximum(n, 1)
    Xz = np.where(M, X, 0.0)
    Yz = np.where(M, y[:, None], 0.0)
    Xc = np.where(M, Xz - Xz.sum(axis=0) / nn, 0.0)
    Yc = np.where(M, Yz - Yz.sum(axis=0) / nn, 0.0)
    sxy, sxx, syy = (Xc * Yc).sum(axis=0), (Xc * Xc).sum(axis=0), (Yc * Yc).sum(axis=0)
    den = np.sqrt(sxx * syy)
    ok = (n >= 3) & (den > 1e-300)
    r = np.full(X.shape[1], np.nan)
    r[ok] = np.clip(sxy[ok] / den[ok], -1.0, 1.0)
    return r, n


def _fisher_p(r, n, tests):
    """Two-sided p-value of a correlation by the Fisher z transform, Bonferroni-adjusted for `tests` tests."""
    if not (math.isfinite(r) and n > 3):
        return 1.0
    z = math.atanh(min(max(r, -0.9999999), 0.9999999)) * math.sqrt(n - 3)
    return min(1.0, tests * math.erfc(abs(z) / math.sqrt(2)))


# ------------------------------------------------------------------ analogue features and output
def _rv(c2, t, n):
    """Realized volatility (root mean square of daily log returns) over the n bars ending at bar t."""
    return np.maximum(np.sqrt(np.maximum((c2[t] - c2[t - n]) / n, 0.0)), VOL_FLOOR)


def _features(lp, t, lookback, long_w, c2=None):
    """Feature rows (shape, vol, year: see the module docstring) of the days t, from lp[:t + 1] only."""
    t = np.asarray(t, dtype=np.int64)
    if c2 is None:
        r = np.diff(lp)
        c2 = np.r_[0.0, np.cumsum(r * r)]
    P = lp[t[:, None] + np.arange(-lookback, 1)]
    path = P[:, 1:] - P[:, :1]
    vw = _rv(c2, t, lookback)
    vs, vl = _rv(c2, t, min(SHORT, long_w)), _rv(c2, t, long_w)
    F = np.empty((len(t), lookback + 2))
    F[:, :lookback] = path / (vw[:, None] * lookback)
    F[:, lookback] = W_VOL * np.log(vs / vl) / VOL_SPREAD
    F[:, lookback + 1] = W_RET * (lp[t] - lp[t - long_w]) / (vl * math.sqrt(long_w))
    return F


def _greedy(ts, k, gap):
    """Positions (in the given nearest-first order) of up to k candidates no two within `gap` bars of each other."""
    if not len(ts):
        return np.zeros(0, int)
    blocked = np.zeros(int(ts.max()) + gap + 2, bool)
    keep = []
    for j, t in enumerate(ts.tolist()):
        if blocked[t]:
            continue
        keep.append(j)
        if len(keep) >= k:
            break
        blocked[max(0, t - gap + 1):t + gap] = True
    return np.asarray(keep, int)


def _fan(method, paths, dist, med_all, rows, head):
    """The common output: neighbours, weights, the fan per day, the horizon quantiles, p_up and similarity."""
    paths = np.asarray(paths, float)
    dist = np.asarray(dist, float)
    w = _kernel(dist)
    Q = _wq(paths, w)
    fwd = paths[:, -1]
    nb = [{**rows[j], 'dist': _r(dist[j]), 'w': _r(w[j], 5), 'fwd': _r(fwd[j]), 'path': _rlist(paths[j])}
          for j in range(len(dist))]
    sim = max(0.0, 1.0 - float(dist.mean()) / med_all) if med_all > 0 else 0.0
    return {'method': method, **head, 'k': len(nb), 'neighbors': nb,
            'q': {key: _rlist(Q[i]) for i, key in enumerate(QK)},
            'end': {key: _r(Q[i, -1]) for i, key in enumerate(QK)},
            'mean': _r(w @ fwd), 'p_up': _r(w[fwd > 0].sum()), 'similarity': _r(min(sim, 1.0)),
            'dist_random': _r(med_all)}


# ------------------------------------------------------------------ (A) self analogues
def self_analogs(dates, ac, horizon=63, lookback=60, k=25, min_gap=None, as_of=None):
    """Analogues from the stock's own past (see the module docstring). as_of: None (last bar), a date, or an index
    into the given arrays. None when the history up to as_of is shorter than lookback + horizon + 50 bars."""
    return _self(_as_series(dates, ac), horizon, lookback, k, min_gap, as_of)


def _self(S, horizon=63, lookback=60, k=25, min_gap=None, as_of=None):
    i = _asof_index(S, as_of)
    n_av = i + 1
    if i < 0 or n_av < lookback + horizon + MIN_EXTRA or k < 1:
        return None
    lw = min(LONG, n_av - horizon - MIN_EXTRA)
    lp = S.lp[:n_av]
    r = np.diff(lp)
    c2 = np.r_[0.0, np.cumsum(r * r)]
    cand = np.arange(max(lw, lookback), i - horizon + 1)
    if not len(cand):
        return None
    F = _features(lp, np.r_[cand, i], lookback, lw, c2)
    d = np.sqrt(((F[:-1] - F[-1]) ** 2).sum(axis=1))
    gap = horizon if min_gap is None else max(1, int(min_gap))
    order = np.argsort(d, kind='stable')
    idx = order[_greedy(cand[order], k, gap)]
    tt = cand[idx]
    paths = lp[tt[:, None] + np.arange(1, horizon + 1)] - lp[tt][:, None]
    rows = [{'date': S.date(t)} for t in tt]
    head = {'as_of': S.date(i), 'horizon': horizon, 'lookback': lookback, 'last_close': _r(math.exp(lp[i]), 4),
            'n_candidates': int(len(cand)), 'long_window': int(lw)}
    return _fan('self', paths, d[idx], float(np.median(d)), rows, head)


# ------------------------------------------------------------------ (A) pooled analogues
class Library:
    """Feature rows of every ticker's past windows with the forward path after each (float32), for repeated queries.
    tick / t / day: the row's ticker index, bar index in that ticker's series, and date (days since 1970-01-01)."""

    def __init__(self, F, fwd, tick, t, day, tickers, lookback, horizon, step, end_day):
        self.F, self.fwd, self.tick, self.t, self.day = F, fwd, tick, t, day
        self.sq = (F.astype(np.float64) ** 2).sum(axis=1).astype(np.float32)
        self.tickers, self.lookback, self.horizon, self.step, self.end_day = tickers, lookback, horizon, step, end_day

    def __len__(self):
        return len(self.F)

    @property
    def end_date(self):
        return _datestr(self.end_day)


def build_library(universe, lookback=60, horizon=63, sample_step=5, end_date=None, max_lib=200000):
    """The pooled analogue library: every sample_step-th day t of every ticker with t ≥ 252 and the bar t + horizon on
    or before end_date (default: the latest date in the universe). The step grows when the rows would exceed max_lib."""
    U = [(tk, _as_series(v)) for tk, v in sorted(universe.items())]
    U = [(tk, S) for tk, S in U if len(S)]
    end = _day(end_date) if end_date is not None else (max(int(S.days[-1]) for _, S in U) if U else 0)
    first_t = max(LONG, lookback)
    plan = []
    for tk, S in U:
        last_t = int(np.searchsorted(S.days, end, side='right')) - 1 - horizon
        if last_t >= first_t:
            plan.append((tk, S, last_t))
    counts = np.array([p[2] - first_t + 1 for p in plan], float)
    step = max(1, int(sample_step))
    if counts.size:
        step = max(step, int(math.ceil(counts.sum() / max(1, max_lib))))
        while np.ceil(counts / step).sum() > max_lib:
            step += 1
    Fs, fws, ticks, ts, days, names = [], [], [], [], [], []
    ar = np.arange(1, horizon + 1)
    for j, (tk, S, last_t) in enumerate(plan):
        t = np.arange(last_t, first_t - 1, -step)[::-1]
        lp = S.lp
        r = np.diff(lp[:last_t + horizon + 1])
        c2 = np.r_[0.0, np.cumsum(r * r)]
        Fs.append(_features(lp, t, lookback, LONG, c2).astype(np.float32))
        fws.append((lp[t[:, None] + ar] - lp[t][:, None]).astype(np.float32))
        ticks.append(np.full(len(t), j, np.int32))
        ts.append(t.astype(np.int32))
        days.append(S.days[t])
        names.append(tk)
    d = lookback + 2
    cat = lambda xs, shape, dt: np.concatenate(xs) if xs else np.zeros(shape, dt)
    return Library(cat(Fs, (0, d), np.float32), cat(fws, (0, horizon), np.float32), cat(ticks, 0, np.int32),
                   cat(ts, 0, np.int32), cat(days, 0, np.int64), names, lookback, horizon, step, end)


def feature_vector(dates, ac, lookback=60, as_of=None):
    """Today's analogue features (shape, vol, year) for querying a library: from the bars up to as_of only; the
    one-year window shrinks to the history there is when shorter. None with fewer than lookback + 50 bars."""
    S = _as_series(dates, ac)
    i = _asof_index(S, as_of)
    if i < 0 or i + 1 < lookback + MIN_EXTRA:
        return None
    return _features(S.lp[:i + 1], [i], lookback, min(LONG, i))[0]


def query(lib, feature_vector, k, min_gap=None, per_period=None):
    """The k nearest library rows to feature_vector, nearest first: no two from one ticker within min_gap bars (default
    the library's horizon), at most per_period (default max(2, k ÷ 10)) within 0.7 × min_gap calendar days of each
    other across tickers. Returns (row indices, distances, median distance to all rows)."""
    n = len(lib)
    if n == 0 or k < 1:
        return np.zeros(0, int), np.zeros(0), 0.0
    q = np.asarray(feature_vector, np.float32)
    d2 = np.empty(n, np.float32)
    for a in range(0, n, CHUNK):
        d2[a:a + CHUNK] = lib.sq[a:a + CHUNK] - 2.0 * (lib.F[a:a + CHUNK] @ q)
    d2 += np.float32(q.astype(np.float64) @ q.astype(np.float64))
    np.maximum(d2, 0, out=d2)
    gap = lib.horizon if min_gap is None else max(1, int(min_gap))
    per = max(2, k // 10) if per_period is None else int(per_period)
    period = max(1, int(round(0.7 * gap)))
    M = min(n, max(40 * k, 2000))
    q64 = q.astype(np.float64)
    while True:
        part = np.argpartition(d2, M - 1)[:M] if M < n else np.arange(n)
        exact = ((lib.F[part].astype(np.float64) - q64) ** 2).sum(axis=1)     # the shortlist re-ranked in float64
        o = np.argsort(exact, kind='stable')
        part, exact = part[o], exact[o]
        sel = _greedy_pooled(lib.tick[part].tolist(), lib.t[part].tolist(), lib.day[part].tolist(), k, gap, per, period)
        if len(sel) >= k or M >= n:
            break
        M = min(n, 4 * M)
    return part[sel], np.sqrt(exact[sel]), float(np.sqrt(np.median(d2)))


def _greedy_pooled(ticks, ts, days, k, gap, per, period):
    by_tick, buckets, keep = {}, {}, []
    for j, (tk, t, day) in enumerate(zip(ticks, ts, days)):
        lst = by_tick.get(tk)
        if lst and any(abs(t - u) < gap for u in lst):
            continue
        if per > 0:
            b = day // period
            near = sum(1 for bb in (b - 1, b, b + 1) for u in buckets.get(bb, ()) if abs(day - u) < period)
            if near >= per:
                continue
        keep.append(j)
        if len(keep) >= k:
            break
        by_tick.setdefault(tk, []).append(t)
        buckets.setdefault(day // period, []).append(day)
    return np.asarray(keep, int)


def pooled_analogs(target, universe, horizon=63, lookback=60, k=50, sample_step=5, as_of_date=None, max_lib=200000,
                   lib=None, per_period=None):
    """Analogues from every ticker's past. target: a ticker in the universe or (dates, ac). lib: a library from
    build_library to reuse (it must end on or before the as-of date); built here otherwise. per_period: see query()
    (0 switches the cap on analogues from one period across tickers off)."""
    S, _ = _target(target, universe)
    if S is None:
        return None
    i = _asof_index(S, as_of_date)
    if i < 0 or i + 1 < lookback + MIN_EXTRA:
        return None
    cutoff = _day(as_of_date) if as_of_date is not None else int(S.days[i])
    if lib is None:
        lib = build_library(universe, lookback, horizon, sample_step, _datestr(cutoff), max_lib)
    elif lib.lookback != lookback or lib.horizon != horizon or lib.end_day > cutoff:
        raise ValueError('library does not match: lookback/horizon differ or it ends after the as-of date')
    if len(lib) == 0:
        return None
    lp = S.lp[:i + 1]
    fq = _features(lp, [i], lookback, min(LONG, i))[0]
    idx, dist, med = query(lib, fq, k, per_period=per_period)
    if not len(idx):
        return None
    rows = [{'ticker': lib.tickers[int(lib.tick[r])], 'date': _datestr(lib.day[r])} for r in idx]
    head = {'as_of': S.date(i), 'horizon': horizon, 'lookback': lookback, 'last_close': _r(math.exp(lp[i]), 4),
            'n_library': len(lib), 'library_step': lib.step, 'n_tickers': len({r['ticker'] for r in rows})}
    return _fan('pooled', lib.fwd[idx].astype(np.float64), dist, med, rows, head)


# ------------------------------------------------------------------ (B) correlated assets
class WeeklyMatrix:
    """Weekly log returns R (weeks × tickers) on the grid E (weeks + 1 week ends, days since 1970-01-01)."""

    def __init__(self, end_day, E, tickers, R):
        self.end_day, self.E, self.tickers, self.R = end_day, E, tickers, R
        self.col = {t: j for j, t in enumerate(tickers)}


def weekly_matrix(universe, end_date, weeks):
    """Weekly log returns of every ticker for the `weeks` weeks ending on end_date (built once, shared by
    correlated_peers calls)."""
    end = _day(end_date)
    E = end - 7 * np.arange(weeks, -1, -1, dtype=np.int64)
    tickers = sorted(universe)
    LP = np.full((weeks + 1, len(tickers)), np.nan)
    for j, tk in enumerate(tickers):
        LP[:, j] = _align(_as_series(universe[tk]), E, 6)
    return WeeklyMatrix(end, E, tickers, np.diff(LP, axis=0))


def correlated_peers(target_dates, target_ac, universe, window=504, top=8, max_lag=4, freq='W', wm=None,
                     target_ticker=None, end_date=None):
    """The assets whose weekly returns moved most with the target's over the last `window` trading days, with their
    lead-lag correlations (see the module docstring). end_date: the forecast date (default: the target's last date);
    only weeks ending on or before it are used. wm: a weekly_matrix to reuse, ending on or before end_date (built here
    otherwise). target_ticker: the target's ticker in the universe, excluded. Sorted by |corr|, largest first."""
    if str(freq).upper() != 'W':
        raise ValueError("only weekly returns (freq='W') are supported")
    return _peers(_as_series(target_dates, target_ac), universe, window, top, max_lag, wm, target_ticker, end_date)


def _peers(S, universe, window=504, top=8, max_lag=4, wm=None, tkr=None, end_date=None):
    i = _asof_index(S, end_date)
    max_lag = max(1, int(max_lag))
    if i < 0:
        return []
    W = max(10, int(round(window * 52 / 252)))
    cutoff = _day(end_date) if end_date is not None else int(S.days[i])
    if wm is None:
        wm = weekly_matrix(universe, _datestr(cutoff), W + max_lag)
    elif wm.end_day > cutoff:
        raise ValueError('weekly matrix ends after the forecast date')
    R = wm.R
    Tn = R.shape[0]
    W = min(W, Tn - max_lag)
    if W < 10 or R.shape[1] == 0:
        return []
    y = np.diff(_align(S.head(i), wm.E, 6))
    yc = y[Tn - W:]
    if np.isfinite(yc).sum() < 0.8 * W:
        return []
    Xc = R[Tn - W:]
    r0, n0 = _pcorr(Xc, yc)
    M = np.isfinite(Xc) & np.isfinite(yc)[:, None]
    same = (n0 >= 3) & (np.where(M, np.abs(Xc - yc[:, None]), 0.0) <= 1e-12).all(axis=0)
    ok = ~same & (n0 >= 0.8 * W) & np.isfinite(r0)
    if tkr is not None and tkr in wm.col:
        ok[wm.col[tkr]] = False
    cand = np.nonzero(ok)[0]
    sel = cand[np.argsort(-np.abs(r0[cand]), kind='stable')][:max(0, int(top))]
    if not len(sel):
        return []
    lag_r, lag_n = {}, {}
    for L in range(1, max_lag + 1):
        lag_r[L], lag_n[L] = _pcorr(R[Tn - W - L:Tn - L][:, sel], yc)
    out = []
    for a, j in enumerate(sel):
        ll = {L: (float(lag_r[L][a]) if np.isfinite(lag_r[L][a]) else 0.0) for L in lag_r}
        best = max(ll, key=lambda L: (abs(ll[L]), -L))
        out.append({'ticker': wm.tickers[j], 'corr': _r(r0[j]), 'n': int(n0[j]),
                    'lead_lag': {L: _r(v) for L, v in ll.items()}, 'best_lag': int(best), 'lead_corr': _r(ll[best]),
                    'lead_p': float(f'{_fisher_p(ll[best], int(lag_n[best][a]), max_lag):.4g}')})
    return out


def _basket(A, w, need):
    """Equal-weight basket: the mean over members of their w-bar log returns, NaN with fewer than `need` members."""
    D = np.full(A.shape, np.nan)
    if w < len(A):
        D[w:] = A[w:] - A[:-w]
    f = np.isfinite(D)
    cnt = f.sum(axis=1)
    s = np.where(f, D, 0.0).sum(axis=1)
    return np.where(cnt >= need, s / np.maximum(cnt, 1), np.nan)


def _peer_names(peers, universe, tkr):
    out = []
    for p in peers or []:
        tk = p.get('ticker') if isinstance(p, dict) else p
        if isinstance(tk, str) and tk in universe and tk != tkr and tk not in out:
            out.append(tk)
    return out


def peer_conditional(target, peers, universe, horizon=63, k=40, windows=(5, 21, 63), as_of=None, target_ticker=None):
    """Analogue days of the target and its peers (the equal-weight basket of `peers`, SPY when in the universe, and the
    target itself), each described by its cumulative log returns over `windows`; the forecast is what the TARGET did
    next. peers: tickers or correlated_peers output. None on a short history or with no peer and no SPY."""
    S, tkr = _target(target, universe)
    tkr = tkr or target_ticker
    if S is None:
        return None
    i = _asof_index(S, as_of)
    windows = sorted({int(w) for w in windows if int(w) >= 1})
    if not windows or i < 0:
        return None
    wmax = windows[-1]
    if i + 1 < wmax + horizon + MIN_EXTRA:
        return None
    members = [p for p in _peer_names(peers, universe, tkr) if p != 'SPY']
    use_spy = 'SPY' in universe and tkr != 'SPY'
    if not members and not use_spy:
        return None
    days, lp = S.days[:i + 1], S.lp[:i + 1]
    cols, names = [], []
    if members:
        A = np.column_stack([_align(_as_series(universe[m]), days) for m in members])
        need = max(1, int(math.ceil(len(members) / 2)))
        for w in windows:
            cols.append(_basket(A, w, need)); names.append(f'basket_{w}')
    if use_spy:
        a = _align(_as_series(universe['SPY']), days)
        for w in windows:
            cols.append(_wret(a, w)); names.append(f'spy_{w}')
    for w in windows:
        cols.append(_wret(lp, w)); names.append(f'own_{w}')
    X = np.column_stack(cols)
    valid = np.isfinite(X).all(axis=1)
    if not valid[i] or valid.sum() < MIN_EXTRA:
        return None
    sd = X[valid].std(axis=0)
    sd = np.where(sd > 1e-12, sd, 1.0)
    Z = np.where(np.isfinite(X), X / sd, 0.0)
    cand = np.nonzero(valid[:max(0, i - horizon + 1)])[0]
    if not len(cand):
        return None
    d = np.sqrt(((Z[cand] - Z[i]) ** 2).sum(axis=1))
    order = np.argsort(d, kind='stable')
    idx = order[_greedy(cand[order], k, horizon)]
    tt = cand[idx]
    paths = lp[tt[:, None] + np.arange(1, horizon + 1)] - lp[tt][:, None]
    rows = [{'date': S.date(t)} for t in tt]
    head = {'as_of': S.date(i), 'horizon': horizon, 'windows': windows, 'last_close': _r(math.exp(lp[i]), 4),
            'basket': members, 'spy': bool(use_spy), 'n_candidates': int(len(cand)),
            'features': {nm: _r(X[i, j]) for j, nm in enumerate(names)}}
    return _fan('peer', paths, d[idx], float(np.median(d)), rows, head)


def lead_lag_forecast(target, peers_with_lags, universe, horizon=21, train=756, as_of=None, target_ticker=None,
                      n_boot=1000):
    """OLS forecast of the target's next-`horizon`-day log return from its significant leaders' last-`best_lag`-week
    returns, with residual-bootstrap quantiles (see the module docstring). None without a leader (lead_p < 0.05) or
    with too little data."""
    S, tkr = _target(target, universe)
    tkr = tkr or target_ticker
    if S is None:
        return None
    leaders, seen = [], set()
    for p in peers_with_lags or []:
        if not isinstance(p, dict):
            continue
        tk, pv, lag = p.get('ticker'), p.get('lead_p'), p.get('best_lag')
        if (tk in universe and tk != tkr and tk not in seen and pv is not None and pv < LEAD_ALPHA
                and lag is not None and int(lag) >= 1):
            leaders.append((tk, int(lag)))
            seen.add(tk)
    if not leaders:
        return None
    i = _asof_index(S, as_of)
    if i < 0:
        return None
    days, lp = S.days[:i + 1], S.lp[:i + 1]
    X = np.column_stack([_wret(_align(_as_series(universe[tk]), days), 5 * lag) for tk, lag in leaders])
    t = np.arange(max(0, i - train), i - horizon + 1)
    if not len(t) or not np.isfinite(X[i]).all():
        return None
    y = lp[t + horizon] - lp[t]
    ok = np.isfinite(X[t]).all(axis=1) & np.isfinite(y)
    p = len(leaders)
    if ok.sum() < max(60, 10 * (p + 1)):
        return None
    A = np.c_[np.ones(int(ok.sum())), X[t][ok]]
    yy = y[ok]
    coef = np.linalg.lstsq(A, yy, rcond=None)[0]
    fit = A @ coef
    resid = yy - fit
    sst = float(((yy - yy.mean()) ** 2).sum())
    r2 = 1 - float((resid ** 2).sum()) / sst if sst > 0 else 0.0
    a_now = np.r_[1.0, X[i]]
    point = float(a_now @ coef)
    n = len(yy)
    L = max(1, min(horizon, n))
    nb = int(math.ceil(n / L))
    rng = np.random.default_rng(SEED)
    starts = rng.integers(0, n - L + 1, size=(n_boot, nb))
    bidx = (starts[:, :, None] + np.arange(L)).reshape(n_boot, -1)[:, :n]
    B = (fit[None, :] + resid[bidx]) @ np.linalg.pinv(A).T
    draws = B @ a_now + resid[rng.integers(0, n, n_boot)]
    q = np.quantile(draws, QS)
    return {'method': 'leadlag', 'as_of': S.date(i), 'horizon': horizon, 'n_train': n, 'n_leaders': p,
            'alpha': _r(coef[0], 6), 'beta': {tk: _r(coef[j + 1], 4) for j, (tk, _) in enumerate(leaders)},
            'leaders': [{'ticker': tk, 'lag_weeks': lag, 'beta': _r(coef[j + 1], 4), 'x_now': _r(X[i, j])}
                        for j, (tk, lag) in enumerate(leaders)],
            'r2_in': _r(r2), 'point': _r(point), 'q_end': {key: _r(q[j]) for j, key in enumerate(QK)},
            'p_up': _r(float((draws > 0).mean()))}


# ------------------------------------------------------------------ walk-forward evaluation
def _pit(qv, y):
    qv = np.maximum.accumulate(np.asarray(qv, float)) + np.arange(len(qv)) * 1e-12
    if y < qv[0]:
        return 0.025
    if y > qv[-1]:
        return 0.975
    return float(np.interp(y, qv, QS))


def _score(rows):
    keys = ('n', 'cover80', 'cover50', 'pinball', 'ic', 'pit', 'pit_hist')
    if not rows:
        return {**{k: None for k in keys}, 'n': 0, 'pit': [], 'pit_hist': [0] * 10}
    Q = np.array([[r['q'][k] for k in QK] for r in rows], float)
    y = np.array([r['realized'] for r in rows], float)
    e = y[:, None] - Q
    pin = np.maximum(QS * e, (QS - 1) * e)
    pit = [_pit(Q[j], y[j]) for j in range(len(y))]
    return {'n': len(rows), 'cover80': _r(np.mean((y >= Q[:, 1]) & (y <= Q[:, 5]))),
            'cover50': _r(np.mean((y >= Q[:, 2]) & (y <= Q[:, 4]))), 'pinball': _r(pin.mean(), 6),
            'ic': (None if (s := spearman(Q[:, 3], y)) is None else _r(s)),
            'pit': [_r(v, 3) for v in pit], 'pit_hist': np.histogram(pit, bins=10, range=(0, 1))[0].tolist()}


def _forecast_end(method, S, tkr, universe, i, cut, horizon, kw, cache):
    """The 7 horizon quantiles forecast at bar i from data on or before `cut` (a date string), or None."""
    Sh = S.head(i)
    if method == 'naive':
        j = np.arange(max(horizon, i - LONG + 1), i + 1)
        if len(j) < MIN_EXTRA:
            return None
        return np.quantile(Sh.lp[j] - Sh.lp[j - horizon], QS)
    if method == 'self':
        out = _self(Sh, horizon, kw.get('lookback', 60), kw.get('k', 25), kw.get('min_gap'))
        return None if out is None else np.array([out['end'][k] for k in QK])
    if method == 'pooled':
        lookback, step, max_lib = kw.get('lookback', 60), kw.get('sample_step', 5), kw.get('max_lib', 200000)
        key = ('lib', cut, lookback, horizon, step, max_lib)
        if key not in cache:
            cache[key] = build_library(universe, lookback, horizon, step, cut, max_lib)
        out = pooled_analogs(Sh, universe, horizon, lookback, kw.get('k', 50), step, cut, max_lib, lib=cache[key])
        return None if out is None else np.array([out['end'][k] for k in QK])
    window, max_lag, top = kw.get('window', 504), kw.get('max_lag', 4), kw.get('top', 8)
    weeks = max(10, int(round(window * 52 / 252))) + max_lag
    key = ('wm', cut, weeks)
    if key not in cache:
        cache[key] = weekly_matrix(universe, cut, weeks)
    peers = _peers(Sh, universe, window, top, max_lag, cache[key], tkr, cut)
    if method == 'peer':
        out = peer_conditional(Sh, peers, universe, horizon, kw.get('k', 40), kw.get('windows', (5, 21, 63)),
                               target_ticker=tkr)
        return None if out is None else np.array([out['end'][k] for k in QK])
    out = lead_lag_forecast(Sh, peers, universe, horizon, kw.get('train', 756), target_ticker=tkr)
    return None if out is None else np.array([out['q_end'][k] for k in QK])


def evaluate(method, target, universe, origins, horizon=63, *, cache=None, **kw):
    """Walk-forward score of one method on one target: at each origin (a date, or an index into the target's arrays)
    forecast from data on or before it, compare the horizon quantiles with the realized cumulative log return.
    Returns {'n', 'cover80', 'cover50', 'pinball', 'ic', 'pit', 'pit_hist', 'n_skipped', 'rows'}. kw go to the method
    (lookback, k, min_gap, sample_step, max_lib, window, top, max_lag, windows, train). cache: a dict shared across
    calls with the same origins (libraries and weekly matrices per origin)."""
    if method not in METHODS:
        raise ValueError(f'method must be one of {METHODS}')
    if method in ('pooled', 'peer', 'leadlag'):
        universe = prepare_universe(universe)          # converted once, not once per origin
    S, tkr = _target(target, universe)
    cache = {} if cache is None else cache
    rows, skipped = [], 0
    for o in origins:
        if S is None:
            skipped += 1
            continue
        i = _asof_index(S, o)
        if i < 0 or i + horizon >= len(S):
            skipped += 1
            continue
        cut = S.date(i) if isinstance(o, (int, np.integer)) else str(np.datetime64(o, 'D'))
        q = _forecast_end(method, S, tkr, universe, i, cut, horizon, kw, cache)
        if q is None or not np.isfinite(q).all():
            skipped += 1
            continue
        rows.append({'ticker': tkr, 'origin': cut, 'q': {k: _r(q[j]) for j, k in enumerate(QK)},
                     'realized': _r(S.lp[i + horizon] - S.lp[i])})
    return {'method': method, **_score(rows), 'n_skipped': skipped, 'rows': rows}


def _spread_pick(xs, m):
    """At most m items of xs, evenly spaced (all of them when there are no more than m)."""
    xs = list(xs)
    if len(xs) <= m:
        return xs
    return [xs[j] for j in sorted(set(np.linspace(0, len(xs) - 1, m).round().astype(int).tolist()))]


def evaluate_universe(method, universe, tickers, origins_dates, horizon=63, max_tickers=100, max_origins=12,
                      return_rows=False, **kw):
    """evaluate() pooled over many tickers and origins (evenly spaced subsets of at most max_tickers × max_origins):
    the scorecard of one method. One library / weekly matrix per origin, shared by every ticker. Adds ic_xs, the mean
    over origins of the cross-sectional Spearman IC (origins with at least 5 tickers scored)."""
    U = prepare_universe(universe)
    tks = _spread_pick([t for t in tickers if t in U], max_tickers)
    ods = _spread_pick([str(np.datetime64(o, 'D')) for o in origins_dates], max_origins)
    rows, skipped = [], 0
    for o in ods:
        cache = {}
        for t in tks:
            r = evaluate(method, t, U, [o], horizon, cache=cache, **kw)
            rows += r['rows']
            skipped += r['n_skipped']
    out = {'method': method, **_score(rows), 'n_skipped': skipped, 'n_tickers': len(tks), 'n_origins': len(ods)}
    xs = []
    for o in ods:
        g = [r for r in rows if r['origin'] == o]
        if len(g) >= 5:
            s = spearman([r['q']['q50'] for r in g], [r['realized'] for r in g])
            if s is not None:
                xs.append(s)
    out['ic_xs'] = _r(np.mean(xs)) if xs else None
    if return_rows:
        out['rows'] = rows
    return out
