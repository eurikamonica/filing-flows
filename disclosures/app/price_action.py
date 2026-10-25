"""Price paths & patterns: rule-based price-action readings and signals from daily bars, and what each signal has
historically been followed by, pooled across the covered US stocks and tested walk-forward.

Inputs: o, h, l, c, v — daily open, high, low, close and volume (1-D float arrays, oldest first, split-adjusted; volume
may be zero); ac — the dividend- and split-adjusted close, used only for returns; dates — 'YYYY-MM-DD' strings.

Every school, the subjective ones included (Al Brooks, ICT / smart money concepts, Elliott waves, Wyckoff), is written
here as an explicit rule with fixed parameters, so that it can be tested out of sample. The plain-English explanation,
the exact rule and the source of each one are in RULES ('what', 'rule', 'source'); 'subjective': True marks schools whose
own authors describe them as discretionary — the rule here is an approximation of what they teach, not their method.
RULES entries of kind 'event' fire on single bars (and are backtested); kind 'state' entries are readings of the last bar.

Shared building blocks
  ATR(14)       average true range with Wilder's smoothing: TR = max(high − low, |high − previous close|, |low − previous
                close|); ATR_t = ATR_t−1 + (TR_t − ATR_t−1) / 14, started at the first bar's high − low. It is the unit
                for "small", "strong" and every distance tolerance, so rules scale with each stock's volatility.
  EMA(20)       exponential moving average of the close, weight 2 / 21 on the newest close, started at the first close.
  averages      the 20-bar average spread (high − low) and volume are taken over the 20 bars BEFORE the current one.
  swings        fractals: bar j is a swing high when its high is above the highs of the 3 bars before it and not below
                those of the 3 bars after it (swing low: the mirror). It is known only at bar j + 3 and used from then on.
  extrema       (chart patterns) the same idea on the close with 5 bars on each side, kept alternating (two maxima in a
                row keep the higher), known 5 bars later. Lo, Mamaysky & Wang (2000) smoothed the close with a kernel
                regression and took its extrema; a ±5-bar window (bandwidth 11 bars) is the causal stand-in.
  zigzag        (Elliott) a pivot is confirmed when the price has reversed by 3 × ATR(14) from the running extreme.
  no look-ahead every event at bar i uses only bars 0..i: detect(bars[:k]) equals detect(bars) restricted to i < k
                (tests/test_price_action.py checks this for several k).
Directions: 'bull' = the rule expects the price to rise relative to the stock's normal drift, 'bear' = to fall. Rules
that point nowhere by themselves take a direction from context, stated in their rule text (inside bar: with the 20-bar
EMA slope; doji: against the prior 10-bar move).

Volume profile (Steidlmayer's Market Profile, by volume): each day's volume is spread evenly across its high–low over 50
equal price bins spanning the window's lowest low to highest high. POC (point of control) = midpoint of the bin with the
most volume. Value area: start at the POC bin and add, one bin at a time, whichever neighbour holds more volume until 70%
of the window's volume is inside; VAH / VAL (value area high / low) = its upper / lower edge. HVN / LVN (high / low volume
nodes) = local peaks (at least the mean bin) and troughs (at most 60% of the mean bin) of the 3-bin smoothed histogram.
For events, the 60-bar profile of the bars before the current one is refreshed every 5 bars.

Pooled backtest (Pool)
  forward return  log(ac[i + h] / ac[i]) for h = 5, 20, 60 trading days (NaN when the series ends first).
  excess          the forward return minus the same ticker's mean h-day forward return over all its bars of the same
                  period (before / after the split date), so a rule is not credited with a stock's drift or a bull market.
  signed excess   excess × (+1 for a 'bull' event, −1 for 'bear'): positive = the rule worked.
  mean, hit rate  average signed excess (log units) and the share of events whose signed excess is > 0. Context for the
                  hit rate: baseline_hit(pool) gives the share of ALL bars (every ticker, every day) whose raw h-day
                  forward return is > 0; returns are skewed, so even a coin-flip rule does not score exactly 50%.
  storage         per event: rule, ticker, month, sign (int8) and the raw forward returns (float32); per ticker and month:
                  the count, sum and positives of all bars' forward returns. The excess is formed in result(), so any
                  split date works (it is applied at the start of its calendar month).
  clustered t     events in the same calendar month share the same market moves, so they are not independent. With N
                  events in G months, e = x − mean and S_g = sum of e within month g: SE² = G / (G − 1) × Σ S_g² / N²;
                  t = mean / SE (needs at least 2 months and 10 events). p = 2 × (1 − Φ(|t|)), Φ = the normal CDF
                  written with math.erf.
  split           events before 2021-01-01 are in-sample, from it on out-of-sample. No parameter was fitted on either
                  part; the split separates "the decade the rules were popular in" from "what happened afterwards".
  Benjamini–Hochberg  per horizon, the m rules' out-of-sample p-values are sorted p(1) ≤ … ≤ p(m); with k the largest
                  rank where p(k) ≤ k / m × 0.10, the k smallest are significant (false discovery rate 10%).
  evidence        'strong': BH-significant out of sample and the in-sample mean has the same sign; 'moderate': out-of-
                  sample p < 0.05 without that (not BH-significant, or the in-sample sign disagrees); 'weak': only the
                  in-sample p < 0.05; 'none' otherwise. A grade with evidence_sign −1 means the signal was reliably
                  followed by the OPPOSITE of what it promises.
"""
import bisect
import datetime as dt
import math

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

ATR_N = 14
EMA_N = 20
AVG_N = 20
SWING_K = 3            # fractal half-width (bars each side)
EXT_W = 5              # chart-pattern extrema half-width
ZZ_K = 3.0             # zigzag reversal, in ATRs
PROFILE_BINS = 50
VALUE_AREA = 0.70
PROFILE_STEP = 5       # the event profile is refreshed every 5 bars
PROFILE_EVENT_N = 60
LEVEL_TOL = 0.5        # swing points within 0.5 × ATR form one level
MONTH = 21             # trading days in a month: monthly signals fire on every 21st bar
YEAR = 252
HORIZONS = (5, 20, 60)
SPLIT = '2021-01-01'
BH_Q = 0.10
MIN_EVENTS = 10        # fewer events (or fewer than 2 months) → no t-stat


# ------------------------------------------------------------------ small helpers
def _f(x):
    return np.asarray(x, dtype=float)


def _fin(x):
    return isinstance(x, (int, float, np.floating, np.integer)) and not isinstance(x, bool) and math.isfinite(x)


def _r(x, d=4):
    return round(float(x), d) if _fin(x) else None


def _sh(x, k=1):
    """x delayed by k bars: out[i] = x[i − k] (False or NaN before the start)."""
    x = np.asarray(x)
    out = np.zeros(len(x), bool) if x.dtype == bool else np.full(len(x), np.nan)
    if 0 < k < len(x):
        out[k:] = x[:len(x) - k]
    elif k == 0:
        out[:] = x
    return out


def _mean(x, n):
    """Trailing n-bar mean ending at each bar (NaN for the first n − 1). Sequential cumulative sums, so any prefix of the
    series gives bit-identical values (the no-look-ahead test depends on it)."""
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        cs = np.concatenate(([0.0], np.cumsum(x)))
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def _roll(x, n, how):
    """Trailing n-bar max or min ending at each bar (NaN for the first n − 1)."""
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        w = sliding_window_view(x, n)
        out[n - 1:] = w.max(axis=1) if how == 'max' else w.min(axis=1)
    return out


def ema(x, n=EMA_N):
    a = 2.0 / (n + 1)
    out = np.empty(len(x))
    m = float(x[0]) if len(x) else 0.0
    for i, xi in enumerate(np.asarray(x, float).tolist()):
        m += a * (xi - m)
        out[i] = m
    return out


def atr(h, l, c, n=ATR_N):
    """Wilder's average true range (see the module docstring)."""
    pc = np.concatenate(([c[0]], c[:-1])) if len(c) else c
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    out = np.empty(len(tr))
    m = float(tr[0]) if len(tr) else 0.0
    for i, t in enumerate(tr.tolist()):
        if i:
            m += (t - m) / n
        out[i] = m
    return out


def normal_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def local_extrema(x_hi, x_lo, k):
    """(maxima, minima): bar indices j where x_hi[j] is above the k values before and not below the k after (minima: the
    mirror on x_lo). Each is known at bar j + k."""
    n = len(x_hi)
    if n < 2 * k + 1:
        return np.array([], int), np.array([], int)
    mx, mn = _roll(x_hi, k, 'max'), _roll(x_lo, k, 'min')
    left_mx, left_mn = _sh(mx, 1), _sh(mn, 1)
    right_mx, right_mn = np.full(n, np.nan), np.full(n, np.nan)
    right_mx[:n - k], right_mn[:n - k] = mx[k:], mn[k:]
    with np.errstate(invalid='ignore'):
        hi = (x_hi > left_mx) & (x_hi >= right_mx)
        lo = (x_lo < left_mn) & (x_lo <= right_mn)
    return np.nonzero(hi)[0], np.nonzero(lo)[0]


def zigzag(h, l, a, k=ZZ_K):
    """Causal zigzag pivots [(bar, price, +1 high / −1 low, bar at which it was confirmed)]: a pivot is confirmed once the
    price has moved k × ATR (at the confirming bar) back from the running extreme."""
    piv = []
    d = 0
    hi_i = lo_i = 0
    hi_p, lo_p = (float(h[0]), float(l[0])) if len(h) else (0.0, 0.0)
    ex_i, ex_p = 0, 0.0
    H, L, A = h.tolist(), l.tolist(), a.tolist()
    for i in range(len(H)):
        thr = k * A[i]
        if d == 0:
            if H[i] > hi_p:
                hi_i, hi_p = i, H[i]
            if L[i] < lo_p:
                lo_i, lo_p = i, L[i]
            if thr > 0 and H[i] - lo_p >= thr and lo_i < i:
                piv.append((lo_i, lo_p, -1, i))
                d, ex_i, ex_p = 1, i, H[i]
            elif thr > 0 and hi_p - L[i] >= thr and hi_i < i:
                piv.append((hi_i, hi_p, 1, i))
                d, ex_i, ex_p = -1, i, L[i]
        elif d == 1:
            if H[i] > ex_p:
                ex_i, ex_p = i, H[i]
            elif ex_p - L[i] >= thr:
                piv.append((ex_i, ex_p, 1, i))
                d, ex_i, ex_p = -1, i, L[i]
        else:
            if L[i] < ex_p:
                ex_i, ex_p = i, L[i]
            elif H[i] - ex_p >= thr:
                piv.append((ex_i, ex_p, -1, i))
                d, ex_i, ex_p = 1, i, H[i]
    return piv


def elliott_impulse_ok(p):
    """Six pivot prices P0..P5 (start, ends of waves 1–5). True when they form a motive wave that keeps Elliott's three
    hard rules: wave 2 never retraces beyond the start of wave 1, wave 3 is never the shortest of waves 1, 3 and 5, wave 4
    never enters wave 1's price territory (plus: the waves alternate and wave 3 ends beyond wave 1)."""
    if len(p) != 6:
        return False
    s = 1.0 if p[1] > p[0] else -1.0
    q = [s * x for x in p]
    w1, w2, w3, w4, w5 = q[1] - q[0], q[1] - q[2], q[3] - q[2], q[3] - q[4], q[5] - q[4]
    if min(w1, w2, w3, w4, w5) <= 0:
        return False
    if q[2] <= q[0]:                       # rule 1: wave 2 stays above the start of wave 1
        return False
    if w3 < w1 and w3 < w5:                # rule 2: wave 3 is not the shortest
        return False
    if q[4] <= q[1]:                       # rule 3: wave 4 stays out of wave 1's territory
        return False
    return q[3] > q[1]


def elliott_abc_ok(p5, p0, a, b, c):
    """A-B-C after an impulse from p0 to p5: B does not pass the impulse's end, C does not undo the whole impulse, and
    wave C is at least 0.618 × wave A long."""
    s = 1.0 if p5 > p0 else -1.0
    P5, P0, A, B, C = (s * x for x in (p5, p0, a, b, c))
    return A < P5 and A < B < P5 and C < B and C > P0 and (B - C) >= 0.618 * (P5 - A)


# ------------------------------------------------------------------ the catalogue
NISON = 'Steve Nison, Japanese Candlestick Charting Techniques (1991)'
BROOKS = 'Al Brooks, Reading Price Charts Bar by Bar (2009) and his Trading Price Action books'
LMW = 'Lo, Mamaysky & Wang, "Foundations of Technical Analysis", Journal of Finance (2000); Edwards & Magee, Technical Analysis of Stock Trends (1948)'
WYCKOFF = 'Richard D. Wyckoff (his stock-market course of the 1930s), as taught by the Wyckoff school'
VSA = 'Tom Williams, Volume Spread Analysis (Master the Markets), building on Wyckoff'
ICT = 'Michael J. Huddleston (ICT, the Inner Circle Trader), online teaching; "smart money concepts"'
DOW = 'Dow theory (Charles Dow; William Hamilton, The Stock Market Barometer, 1922); fractal swings: Bill Williams, Trading Chaos (1995)'


def _R(id_, name, family, dir_, subjective, kind, what, rule, source):
    return {'id': id_, 'name': name, 'family': family, 'dir': dir_, 'subjective': subjective, 'kind': kind,
            'what': what, 'rule': rule, 'source': source}


RULES = [
    # candlestick ------------------------------------------------------------------------------------------------
    _R('hammer', 'Hammer / bullish pin bar', 'candlestick', 'bull', False, 'event',
       'A bar with a small body near its top and a long lower wick: sellers pushed the price well down during the day, '
       'buyers pushed it back up by the close. After a decline it is read as a sign that selling is drying up.',
       'Lower wick ≥ 2 × body, upper wick ≤ 25% of the bar range, range ≥ 0.5 × ATR (average true range, 14 days) of the '
       'bar before, and the close is below its 10-day mean (a decline).', NISON),
    _R('shooting_star', 'Shooting star / bearish pin bar', 'candlestick', 'bear', False, 'event',
       'The mirror of the hammer: a small body near the bottom of the bar and a long upper wick. After a rise it is read '
       'as buyers failing to hold a push higher.',
       'Upper wick ≥ 2 × body, lower wick ≤ 25% of the range, range ≥ 0.5 × ATR(14) of the bar before, close above its '
       '10-day mean (a rise).', NISON),
    _R('bull_engulfing', 'Bullish engulfing', 'candlestick', 'bull', False, 'event',
       'A down day followed by an up day whose body (open to close) covers the whole body of the down day. After a '
       'decline it is read as buyers taking over.',
       'Bar i−1 closes below its open, bar i closes above its open, open(i) ≤ close(i−1), close(i) ≥ open(i−1), body(i) > '
       'body(i−1), and close(i−1) is below its 10-day mean.', NISON),
    _R('bear_engulfing', 'Bearish engulfing', 'candlestick', 'bear', False, 'event',
       'An up day followed by a down day whose body covers the whole body of the up day. After a rise it is read as '
       'sellers taking over.',
       'Mirror of the bullish engulfing, with close(i−1) above its 10-day mean.', NISON),
    _R('inside_bar', 'Inside bar', 'candlestick', 'both', False, 'event',
       'A bar whose high and low both stay inside the previous bar\'s range: a pause, a contraction of the range. '
       'Traders treat it as a continuation set-up in the direction of the trend.',
       'high(i) < high(i−1) and low(i) > low(i−1); direction = the slope of the 20-day EMA (exponential moving average) '
       'at bar i (rising → bull).', NISON),
    _R('doji', 'Doji', 'candlestick', 'both', False, 'event',
       'A bar that closes almost exactly where it opened: neither buyers nor sellers won the day. After a move it is read '
       'as indecision that can precede a turn.',
       'Body ≤ 10% of the range and range ≥ 0.3 × ATR(14) of the bar before; direction = against the 10-day move '
       '(close(i) > close(i−10) → bear).', NISON),
    _R('morning_star', 'Morning star', 'candlestick', 'bull', False, 'event',
       'Three bars at the end of a decline: a long down bar, a small-bodied "star", then an up bar that closes well into '
       'the first bar\'s body. Read as a bottoming pattern.',
       'Bar i−2: down, body ≥ 0.6 × ATR(14), close below its 10-day mean; bar i−1: body ≤ 30% of bar i−2\'s and top of '
       'its body below bar i−2\'s midpoint; bar i: up, close above the midpoint of bar i−2\'s body.', NISON),
    _R('evening_star', 'Evening star', 'candlestick', 'bear', False, 'event',
       'The mirror of the morning star at the end of a rise: a long up bar, a small star, then a down bar closing well '
       'into the first bar\'s body.', 'Mirror of the morning star.', NISON),
    _R('three_white_soldiers', 'Three white soldiers', 'candlestick', 'bull', False, 'event',
       'Three up bars in a row, each opening inside the previous body and closing near its high at a new close. Read as '
       'steady buying.',
       'Bars i−2..i: each close > open with body ≥ 0.4 × ATR(14), close > previous close, open between the previous '
       'open and close, upper wick ≤ 30% of the range.', NISON),
    _R('three_black_crows', 'Three black crows', 'candlestick', 'bear', False, 'event',
       'Three down bars in a row, each opening inside the previous body and closing near its low. Read as steady '
       'selling.', 'Mirror of three white soldiers.', NISON),
    # brooks -----------------------------------------------------------------------------------------------------
    _R('always_in', 'Always-in direction', 'brooks', 'both', True, 'state',
       'Al Brooks asks of every chart: if you had to be in the market right now, long or short, which would it be? '
       'That answer is the "always-in" direction.',
       'Long once the 20-bar EMA (exponential moving average) is above its value 5 bars earlier and the last two closes '
       'are above it; short on the mirror; otherwise the previous answer stands.', BROOKS),
    _R('always_in_flip', 'Always-in flip', 'brooks', 'both', True, 'event',
       'The moment the always-in direction changes from short to long (bull) or long to short (bear).',
       'Fires on the bar where the always-in state switches sides (not on its first assignment).', BROOKS),
    _R('trend_or_range', 'Trend or trading range', 'brooks', 'both', True, 'state',
       'Brooks sorts every stretch of a chart into trend (the price travels) or trading range (bars overlap and the '
       'price goes back and forth). Most breakouts of a trading range fail; most trends continue.',
       'Trend when the 20-bar efficiency ratio (|close − close 20 bars ago| ÷ sum of absolute daily changes, after '
       'Perry Kaufman) is ≥ 0.30 and ≥ 70% of the last 20 closes are on one side of the 20-bar EMA; else trading range.',
       BROOKS),
    _R('h2_buy', 'H2 buy (second-leg pullback)', 'brooks', 'bull', True, 'event',
       'In a bull trend pullbacks often come in two legs. Each time a bar\'s high goes above the previous bar\'s high '
       'during the pullback is a "high 1", "high 2"…; the high 2 is Brooks\' classic buy signal.',
       'While always-in long: a pullback starts with a bar whose high is below the previous high; the second time in '
       'that pullback a bar\'s high exceeds the previous bar\'s high (after at least one lower-high bar in between) '
       'fires; a new trend high ends the pullback.', BROOKS),
    _R('l2_sell', 'L2 sell (second-leg rally)', 'brooks', 'bear', True, 'event',
       'The mirror of the H2 in a bear trend: the second time a rally bar\'s low goes below the previous bar\'s low.',
       'Mirror of the H2 while always-in short.', BROOKS),
    _R('wedge_top', 'Wedge top (three pushes up)', 'brooks', 'bear', True, 'event',
       'Three pushes up, each making a higher high with higher lows between, often with fading momentum. Brooks reads a '
       'third push that cannot follow through as exhaustion and expects at least two legs down.',
       'Three consecutive swing highs (3-bar fractals) rising within 60 bars with the lows between them rising; fires '
       'when a close falls below the low between pushes 2 and 3 within 15 bars, unless the high of push 3 is exceeded '
       'first.', BROOKS),
    _R('wedge_bottom', 'Wedge bottom (three pushes down)', 'brooks', 'bull', True, 'event',
       'The mirror: three pushes down to lower lows, then a reversal up.', 'Mirror of the wedge top.', BROOKS),
    _R('brooks_breakout', 'Strong breakout bar', 'brooks', 'both', True, 'event',
       'A breakout of the recent trading range made by a big trend bar that closes near its extreme: Brooks\' sign of '
       'urgency, which tends to be followed by a measured move.',
       'Close beyond the previous 20 bars\' high (low), body ≥ 0.8 × ATR(14) of the bar before, close in the outer 25% '
       'of the bar\'s range.', BROOKS),
    _R('failed_breakout', 'Failed breakout', 'brooks', 'both', True, 'event',
       'A close above the recent range that is back inside within a few bars. Brooks: most breakouts of trading ranges '
       'fail, and a failed breakout traps the traders who bought it.',
       'After a close above the previous 20-bar high (below the low), a close back below (above) that level within 3 '
       'bars fires against the breakout.', BROOKS),
    _R('measured_move', 'Measured-move target', 'brooks', 'both', True, 'state',
       'After a breakout the price often travels about as far as the height of the range it left (a "measured move").',
       'Target = breakout level ± height of the 20-bar range before the last strong breakout bar; reached when a later '
       'high (low) gets there.', BROOKS),
    # structure --------------------------------------------------------------------------------------------------
    _R('swings', 'Swing points HH / HL / LH / LL', 'structure', 'both', False, 'state',
       'A swing high is a peak with lower highs on both sides; a swing low is a trough. Comparing each with the previous '
       'one gives HH (higher high), HL (higher low), LH (lower high) and LL (lower low): an up-trend is HH + HL.',
       'Fractals with k = 3: high(j) above the highs of the 3 bars before and not below those of the 3 after; known only '
       'at bar j + 3.', DOW),
    _R('bos', 'Break of structure (BOS)', 'structure', 'both', False, 'event',
       'A BOS (break of structure) is a close beyond the last swing point in the direction of the current structure: '
       'the trend continuing.',
       'In an up-structure a close above the last unbroken swing high (bull); in a down-structure a close below the last '
       'swing low (bear). The first break of a series only sets the structure.', DOW),
    _R('choch', 'Change of character (CHoCH)', 'structure', 'both', False, 'event',
       'A CHoCH (change of character) is the first close beyond the opposite swing point, against the prevailing '
       'structure: the first sign that the trend may be turning.',
       'In an up-structure a close below the last unbroken swing low (bear, the structure becomes down); mirror in a '
       'down-structure.', DOW),
    # pattern ----------------------------------------------------------------------------------------------------
    _R('head_shoulders', 'Head and shoulders', 'pattern', 'bear', False, 'event',
       'Three peaks, the middle one (the head) highest, the outer two (shoulders) about equal, with a "neckline" through '
       'the two troughs between them. A close below the neckline completes the top.',
       'Five alternating extrema of the close (±5-bar window): E1, E3, E5 peaks with E3 above both, E1 and E5 within 1.5% '
       'of their mean, E2 and E4 within 1.5%; fires at the first close below the line through E2 and E4, unless a close '
       'above E3 comes first or half the pattern width passes.', LMW),
    _R('inv_head_shoulders', 'Inverse head and shoulders', 'pattern', 'bull', False, 'event',
       'The mirror at a bottom: three troughs with the middle one lowest; a close above the neckline completes it.',
       'Mirror of the head and shoulders.', LMW),
    _R('double_top', 'Double top', 'pattern', 'bear', False, 'event',
       'Two peaks at about the same price with a trough between them; a close below that trough completes the top.',
       'Two consecutive close maxima within 1.5% of each other, at least 20 bars apart, the minimum between them at '
       'least 3% below; fires at the first close below that minimum within the pattern\'s width, unless a close 1.5% '
       'above the peaks comes first.', LMW),
    _R('double_bottom', 'Double bottom', 'pattern', 'bull', False, 'event',
       'Two troughs at about the same price; a close above the peak between them completes the bottom.',
       'Mirror of the double top.', LMW),
    _R('triangle', 'Triangle breakout', 'pattern', 'both', False, 'event',
       'Peaks getting lower while troughs get higher: the range contracts into a triangle. The direction of the '
       'breakout is taken as the signal.',
       'Five alternating close extrema with the peaks falling and the troughs rising (LMW\'s triangle); fires at the '
       'first close above the line through the last two peaks (bull) or below the line through the last two troughs '
       '(bear) within half the pattern width.', LMW),
    _R('bull_flag', 'Bull flag', 'pattern', 'bull', False, 'event',
       'A sharp rise (the pole) followed by a short, tight drift down or sideways (the flag), then a break above the '
       'flag: a continuation pattern.',
       'Pole: the close rises ≥ 4 × ATR(14) above the lowest low of the 10 bars ending at the pole bar; flag: 5–15 bars '
       'after it with a range ≤ half the pole, highs no more than 0.25 ATR above the pole bar\'s high and a last close '
       'not above the pole close; fires when a close exceeds the flag\'s high (at most once per 5 bars).',
       'Edwards & Magee, Technical Analysis of Stock Trends (1948); Thomas Bulkowski, Encyclopedia of Chart Patterns (2000)'),
    _R('bear_flag', 'Bear flag', 'pattern', 'bear', False, 'event',
       'A sharp fall followed by a tight drift up or sideways, then a break below the flag.', 'Mirror of the bull flag.',
       'Edwards & Magee, Technical Analysis of Stock Trends (1948); Thomas Bulkowski, Encyclopedia of Chart Patterns (2000)'),
    _R('cup_handle', 'Cup with handle', 'pattern', 'bull', False, 'event',
       'A rounded U-shaped base between two peaks at about the same price (the cup), then a small pullback (the handle) '
       'and a break above the rim. William O\'Neil\'s favourite base for growth stocks.',
       'Two close maxima 30–150 bars apart, the right one 95–103% of the left, cup depth 12–35%, the bottom in the '
       'middle 60% of the cup and ≥ 55% of the cup\'s closes in its lower half (round, not V-shaped); fires at the first '
       'close above the rim within 40 bars while the handle holds (no close more than 12% or half the cup depth below the '
       'rim).', 'William O\'Neil, How to Make Money in Stocks (1988)'),
    # wyckoff ----------------------------------------------------------------------------------------------------
    _R('wyckoff_phase', 'Wyckoff phase', 'wyckoff', 'both', True, 'state',
       'Wyckoff saw markets cycle through accumulation (large operators buying in a trading range after a fall), markup '
       '(the rise), distribution (selling in a range after a rise) and markdown (the fall).',
       'A trading range is 30 bars whose high–low span is ≤ 6 × ATR(14), after a move of ≥ 4 × ATR over the 60 bars '
       'before it (a decline → accumulation, a rise → distribution); the range then lasts at most 30 more bars (30–60 '
       'in all). A sign of strength / weakness, or 3 closes outside the range, ends it (→ markup / markdown); a close '
       'back through the far side of that range ends the markup / markdown (phase: none).', WYCKOFF),
    _R('spring', 'Spring', 'wyckoff', 'bull', True, 'event',
       'Inside an accumulation-type range, the price dips below the range low and closes back inside the same day: '
       'the sellers below the range were shaken out. Volume is recorded (higher volume is the classic reading).',
       'Inside an active Wyckoff range: low < range low and close > range low (at most once per 5 bars); the volume '
       'ratio to its 20-day average is kept in info.', WYCKOFF),
    _R('upthrust', 'Upthrust (Wyckoff)', 'wyckoff', 'bear', True, 'event',
       'The mirror of the spring at the range high: a push above the range that closes back inside.',
       'Inside an active Wyckoff range: high > range high and close < range high.', WYCKOFF),
    _R('sos', 'Sign of strength', 'wyckoff', 'bull', True, 'event',
       'A wide up bar on rising volume that closes above the trading range: demand overcoming supply, the start of '
       'markup.',
       'Close > range high + 0.25 × ATR(14), spread ≥ its 20-bar average and volume ≥ its 20-bar average; ends the range.',
       WYCKOFF),
    _R('sow', 'Sign of weakness', 'wyckoff', 'bear', True, 'event',
       'A wide down bar on rising volume that closes below the trading range: the start of markdown.',
       'Mirror of the sign of strength.', WYCKOFF),
    # vsa --------------------------------------------------------------------------------------------------------
    _R('vsa_bar', 'VSA bar reading', 'vsa', 'both', True, 'state',
       'VSA (volume spread analysis) reads each bar from three things: its spread (high − low), its volume and where it '
       'closes within the bar, each judged against recent bars.',
       'Spread and volume as multiples of their 20-bar averages (narrow < 0.7, wide > 1.3, ultra ≥ 2), close position = '
       '(close − low) ÷ (high − low): low < 1/3, high > 2/3.', VSA),
    _R('no_demand', 'No demand', 'vsa', 'bear', True, 'event',
       'An up bar on a narrow spread with volume lower than the two previous bars: professionals are not interested in '
       'higher prices.',
       'close > previous close, spread < 0.7 × average, volume < each of the 2 previous bars, close position ≤ 0.6.', VSA),
    _R('no_supply', 'No supply', 'vsa', 'bull', True, 'event',
       'A down bar on a narrow spread with volume lower than the two previous bars: no selling pressure.',
       'close < previous close, spread < 0.7 × average, volume < each of the 2 previous bars, close position ≥ 0.4.', VSA),
    _R('stopping_volume', 'Stopping volume', 'vsa', 'bull', True, 'event',
       'Heavy volume on a down move with the close well off the low: large buyers absorbing the selling.',
       'Low at the lowest of 10 bars, volume ≥ 2 × average, spread ≥ average, close position ≥ 0.5.', VSA),
    _R('selling_climax', 'Selling climax (climactic down bar)', 'vsa', 'bull', True, 'event',
       'An ultra-wide bar on ultra-high volume at a new low after a fall: panic selling, read as the end of the move.',
       'Low at the lowest of 20 bars, close below its 10-day mean, spread ≥ 2 × average, volume ≥ 2.5 × average.', VSA),
    _R('buying_climax', 'Buying climax (climactic up bar)', 'vsa', 'bear', True, 'event',
       'An ultra-wide bar on ultra-high volume at a new high after a rise: euphoric buying, read as the end of the move.',
       'High at the highest of 20 bars, close above its 10-day mean, spread ≥ 2 × average, volume ≥ 2.5 × average.', VSA),
    _R('vsa_upthrust', 'Upthrust bar (VSA)', 'vsa', 'bear', True, 'event',
       'A wide bar that pushes to a new high and closes near its low on high volume: a trap for buyers.',
       'High above the previous 10 highs, spread ≥ 1.2 × average, volume ≥ 1.5 × average, close position ≤ 0.3.', VSA),
    _R('vsa_test', 'Test (VSA)', 'vsa', 'bull', True, 'event',
       'A dip below the previous low on low volume that closes near the high, in an up-move: a test showing no supply.',
       'low < previous low, close position ≥ 0.6, spread < average, volume < each of the 2 previous bars, close above '
       'the 20-day EMA.', VSA),
    # profile ----------------------------------------------------------------------------------------------------
    _R('value_area', 'Volume profile: POC, value area, HVN / LVN', 'profile', 'both', False, 'state',
       'A volume profile shows how much volume traded at each price. The POC (point of control) is the busiest price; '
       'the value area holds 70% of the volume, between VAH (value area high) and VAL (value area low); HVN / LVN are '
       'high and low volume nodes.',
       '60 and 250 bars, 50 price bins, each day\'s volume spread evenly over its high–low; value area grown from the '
       'POC toward the heavier neighbour until 70% (see the module docstring).',
       'Peter Steidlmayer (Market Profile, Chicago Board of Trade, 1980s); James Dalton et al., Mind Over Markets (1990)'),
    _R('va_reentry', 'Back into value', 'profile', 'both', False, 'event',
       'After closing outside the value area, the price closes back inside it. Market Profile traders expect it to '
       'rotate through the value area toward the other side (the "80% rule").',
       '60-bar profile of the bars before (refreshed every 5 bars): close(i−1) > VAH and close(i) inside → bear; '
       'close(i−1) < VAL and close(i) inside → bull.',
       'Peter Steidlmayer (Market Profile); James Dalton et al., Mind Over Markets (1990)'),
    _R('vah_breakout', 'Breakout above value', 'profile', 'bull', False, 'event',
       'A close that moves from inside the value area to above its high: acceptance of higher prices.',
       'close(i−1) ≤ VAH < close(i), 60-bar profile of the bars before.', 'Peter Steidlmayer (Market Profile)'),
    _R('val_breakdown', 'Breakdown below value', 'profile', 'bear', False, 'event',
       'A close that moves from inside the value area to below its low.', 'close(i−1) ≥ VAL > close(i).',
       'Peter Steidlmayer (Market Profile)'),
    # levels -----------------------------------------------------------------------------------------------------
    _R('sr_levels', 'Support and resistance levels', 'levels', 'both', False, 'state',
       'Prices where the market has turned more than once. Below the price a level is support (buyers stepped in), above '
       'it resistance (sellers did).',
       'Swing highs and lows (3-bar fractals) within 0.5 × ATR(14) of a level\'s mean join it; ≥ 2 touches make a level; '
       'a bar whose range comes within 0.25 ATR of it is a test; levels untouched for 500 bars are dropped.',
       'Edwards & Magee, Technical Analysis of Stock Trends (1948)'),
    _R('sd_zones', 'Supply and demand zones', 'levels', 'both', True, 'state',
       'A demand zone is the small base the price sat in just before a strong rally: the idea is that unfilled buy '
       'orders remain there. A supply zone is the base before a strong drop.',
       'Base = 1–3 consecutive bars each with a range ≤ 0.7 × ATR(14); a close ≥ 2 × ATR above (below) the base\'s last '
       'close within 3 bars makes a demand (supply) zone from the base\'s lowest low to highest high.',
       'Sam Seiden (Online Trading Academy), supply-and-demand trading'),
    _R('support_bounce', 'Bounce from support', 'levels', 'bull', False, 'event',
       'The price comes down to a support level and closes back above it.',
       'Level with ≥ 2 touches; close(i−1) ≥ level, low(i) within [level − 0.5 ATR, level + 0.25 ATR], close(i) ≥ level '
       '+ 0.25 ATR.', 'Edwards & Magee, Technical Analysis of Stock Trends (1948)'),
    _R('resistance_reject', 'Rejection at resistance', 'levels', 'bear', False, 'event',
       'The price rises to a resistance level and closes back below it.', 'Mirror of the support bounce.',
       'Edwards & Magee, Technical Analysis of Stock Trends (1948)'),
    _R('level_break', 'Break of a level', 'levels', 'both', False, 'event',
       'A close through a support or resistance level: old resistance broken upward (bull) or support broken downward '
       '(bear).',
       'close(i−1) ≤ level and close(i) ≥ level + 0.25 ATR (bull); mirror (bear); level with ≥ 2 touches; one per bar '
       '(the level with most touches).',
       'Edwards & Magee (1948); tested as trading-range breakouts by Brock, Lakonishok & LeBaron, Journal of Finance (1992)'),
    _R('demand_zone_test', 'Return to a demand zone', 'levels', 'bull', True, 'event',
       'The first time the price comes back down into an untested demand zone and closes above its bottom.',
       'First bar after the zone formed with low ≤ zone top and close ≥ zone bottom (zones expire after 500 bars).',
       'Sam Seiden (Online Trading Academy), supply-and-demand trading'),
    _R('supply_zone_test', 'Return to a supply zone', 'levels', 'bear', True, 'event',
       'The first time the price comes back up into an untested supply zone and closes below its top.',
       'Mirror of the demand-zone test.', 'Sam Seiden (Online Trading Academy), supply-and-demand trading'),
    # ict --------------------------------------------------------------------------------------------------------
    _R('fvg_return', 'Return into a fair value gap', 'ict', 'both', True, 'event',
       'An FVG (fair value gap) is a three-bar gap: bar i−2\'s high is below bar i\'s low (bullish), so the middle bar '
       'moved so fast that no trading overlapped. ICT teaches that price tends to come back to "rebalance" the gap and '
       'then continue.',
       'Bullish FVG: high(i−2) < low(i), gap ≥ 0.1 × ATR(14); fires at the first later bar whose low enters the gap and '
       'whose close stays above its bottom (mirror for bearish); gaps expire after 250 bars.', ICT),
    _R('order_block', 'Order block retest', 'ict', 'both', True, 'event',
       'An order block is the last opposite-coloured bar before a strong ("displacement") move that breaks market '
       'structure: ICT reads it as where large orders were placed. A return to it is taken as an entry.',
       'At a BOS or CHoCH bar, the last down bar (for a bullish break) among the 10 bars before, if the close has moved '
       '≥ 1.5 × ATR(14) beyond that bar\'s close; zone = that bar\'s low–high; fires at the first later bar (within 120) '
       'that trades into the zone without closing beyond its far side (bullish block: close ≥ its low).', ICT),
    _R('liquidity_sweep', 'Liquidity sweep', 'ict', 'both', True, 'event',
       'Stops cluster just beyond obvious swing highs and lows ("liquidity"). A sweep is a wick through such a level '
       'that closes back inside: the stops were taken and the move reverses.',
       'high(i) > the latest untaken swing high (3-bar fractal) and close(i) < it → bear; low(i) < the latest untaken '
       'swing low and close(i) > it → bull.', ICT),
    _R('premium_discount', 'Premium / discount', 'ict', 'both', True, 'state',
       'Between the last swing high and swing low (the "dealing range"), the upper half is premium (expensive, where '
       'ICT sells) and the lower half discount (cheap, where ICT buys).',
       'Close above the midpoint of the last swing high and last swing low → premium, below → discount.', ICT),
    _R('fvg', 'Unfilled fair value gaps', 'ict', 'both', True, 'state',
       'FVGs (fair value gaps) the price has not traded back through yet.',
       'A bullish FVG is filled once a later low reaches its bottom (bearish: a high reaches its top).', ICT),
    # elliott ----------------------------------------------------------------------------------------------------
    _R('elliott_count', 'Elliott wave count', 'elliott', 'both', True, 'state',
       'Elliott held that trends move in five waves (1 up, 2 down, 3 up, 4 down, 5 up) and are corrected in three (A, '
       'B, C). Counts are notoriously subjective; this one follows fixed zigzag swings and Elliott\'s three hard rules.',
       'ZigZag pivots at 3 × ATR(14); the latest six alternating pivots that keep the hard rules form the impulse; '
       'Fibonacci ratios of the waves are reported.',
       'R. N. Elliott, The Wave Principle (1938); Frost & Prechter, Elliott Wave Principle (1978)'),
    _R('elliott_impulse', 'Completed 5-wave impulse', 'elliott', 'both', True, 'event',
       'Five waves that satisfy the hard rules have just completed: Elliott expects a three-wave correction against them.',
       'At the bar that confirms pivot 5: wave 2 does not pass the start of wave 1, wave 3 is not the shortest of 1/3/5, '
       'wave 4 stays out of wave 1\'s range; direction = against the impulse.',
       'R. N. Elliott, The Wave Principle (1938); Frost & Prechter, Elliott Wave Principle (1978)'),
    _R('elliott_abc', 'Completed A-B-C correction', 'elliott', 'both', True, 'event',
       'An A-B-C correction after an impulse has completed: Elliott expects the larger trend to resume.',
       'At the bar that confirms pivot C after a valid impulse: B does not pass the impulse end, C does not pass the '
       'impulse start, wave C ≥ 0.618 × wave A; direction = the impulse\'s.',
       'R. N. Elliott, The Wave Principle (1938); Frost & Prechter, Elliott Wave Principle (1978)'),
    # quant ------------------------------------------------------------------------------------------------------
    _R('donchian20', 'Donchian 20-day breakout', 'quant', 'both', False, 'event',
       'A close above the highest high of the previous 20 days (or below the lowest low): the entry of the Turtles\' '
       'System 1, a classic trend-following rule.',
       'close(i) > max(high, previous 20 bars) → bull, < min(low) → bear; only the first bar of a run of breakouts.',
       'Richard Donchian / the Turtles (Richard Dennis and William Eckhardt, 1983); Curtis Faith, Way of the Turtle (2007)'),
    _R('donchian55', 'Donchian 55-day breakout', 'quant', 'both', False, 'event',
       'The same with 55 days: the Turtles\' slower System 2.', 'As donchian20 with 55 bars.',
       'Richard Donchian / the Turtles; Curtis Faith, Way of the Turtle (2007)'),
    _R('tsmom', 'Time-series momentum (12-1)', 'quant', 'both', False, 'event',
       'A stock\'s own return over the past 12 months, leaving out the latest month, predicts the sign of its next '
       'month\'s return in many markets (time-series momentum).',
       'Every 21st bar: r = log(close 21 bars ago ÷ close 252 bars ago); r > 0 → bull, else bear.',
       'Moskowitz, Ooi & Pedersen, "Time Series Momentum", Journal of Financial Economics (2012)'),
    _R('hi52', 'Near the 52-week high', 'quant', 'bull', False, 'event',
       'Stocks trading close to their 52-week high have tended to keep outperforming: investors anchor on the high and '
       'under-react to the good news that took the price there.',
       'Every 21st bar: close ÷ highest close of the last 252 bars (this one included) ≥ 0.95.',
       'George & Hwang, "The 52-Week High and Momentum Investing", Journal of Finance (2004)'),
    _R('st_reversal', 'Short-term reversal', 'quant', 'both', False, 'event',
       'Extreme one-month returns tend to partly reverse the next month (liquidity provision and over-reaction).',
       'r21 = log(close ÷ close 21 bars ago); when it enters the top 10% of the stock\'s own past r21 values (≥ 252 of '
       'them) → bear, the bottom 10% → bull.',
       'Jegadeesh, "Evidence of Predictable Behavior of Security Returns", Journal of Finance (1990)'),
]
RULE = {r['id']: r for r in RULES}
EVENT_RULES = [r['id'] for r in RULES if r['kind'] == 'event']
FAMILIES = ['candlestick', 'brooks', 'structure', 'pattern', 'wyckoff', 'vsa', 'profile', 'levels', 'ict', 'elliott', 'quant']


# ------------------------------------------------------------------ shared context
def _ctx(o, h, l, c, v):
    o, h, l, c = _f(o), _f(h), _f(l), _f(c)
    v = np.nan_to_num(_f(v), nan=0.0, posinf=0.0, neginf=0.0)
    n = len(c)
    A = atr(h, l, c) if n else np.zeros(0)
    Ap = _sh(A, 1)
    E = ema(c) if n else np.zeros(0)
    rng = h - l
    body = np.abs(c - o)
    top, bot = np.maximum(o, c), np.minimum(o, c)
    cp = np.where(rng > 0, (c - l) / np.where(rng > 0, rng, 1.0), 0.5)
    avg_sp = _sh(_mean(rng, AVG_N), 1)
    avg_v = _sh(_mean(v, AVG_N), 1)
    sp = np.where(avg_sp > 0, rng / np.where(avg_sp > 0, avg_sp, 1.0), np.nan)
    vr = np.where(avg_v > 0, v / np.where(avg_v > 0, avg_v, 1.0), np.nan)
    shi, slo = local_extrema(h, l, SWING_K)
    is_sh, is_sl = np.zeros(n, bool), np.zeros(n, bool)
    is_sh[shi], is_sl[slo] = True, True
    return {'o': o, 'h': h, 'l': l, 'c': c, 'v': v, 'n': n, 'A': A, 'Ap': Ap, 'E': E, 'rng': rng, 'body': body,
            'top': top, 'bot': bot, 'uw': h - top, 'lw': bot - l, 'cp': cp, 'm10': _mean(c, 10), 'sp': sp, 'vr': vr,
            'is_sh': is_sh, 'is_sl': is_sl,
            'H': h.tolist(), 'L': l.tolist(), 'C': c.tolist(), 'O': o.tolist(), 'AL': A.tolist()}


def _ev(out, rule, i, d, **info):
    out.append({'rule': rule, 'i': int(i), 'dir': d, 'info': {k: (_r(x) if isinstance(x, float) else x) for k, x in info.items()}})


def _mask_events(out, rule, mask, d):
    for i in np.nonzero(mask)[0].tolist():
        _ev(out, rule, i, d)


def _zone_tests(zones, X, rule, maxlen, out):
    """zones: dicts {'t': bar formed, 'bottom', 'top', 'dir'}. The first later bar (within maxlen) that trades into the zone
    decides it: a close that holds (≥ bottom for a bull zone, ≤ top for a bear zone) is a `rule` event, otherwise the
    zone is broken. Adds 'status' ('active' / 'tested' / 'broken' / 'expired') and 'k' (the deciding bar) to each zone."""
    h, l, c, n = X['h'], X['l'], X['c'], X['n']
    for z in zones:
        a, b = z['t'] + 1, min(n, z['t'] + 1 + maxlen)
        z['k'] = None
        seg = (l[a:b] <= z['top']) if z['dir'] == 'bull' else (h[a:b] >= z['bottom'])
        if b > a and seg.any():
            k = a + int(np.argmax(seg))
            z['k'] = k
            held = c[k] >= z['bottom'] if z['dir'] == 'bull' else c[k] <= z['top']
            z['status'] = 'tested' if held else 'broken'
            if held:
                _ev(out, rule, k, z['dir'], bottom=float(z['bottom']), top=float(z['top']), formed=int(z['t']))
        else:
            z['status'] = 'active' if z['t'] + maxlen >= n - 1 else 'expired'
    return zones


# ------------------------------------------------------------------ candlestick
def _candles(X):
    out = []
    n = X['n']
    if n < 4:
        return out, {}
    o, h, l, c, Ap, A = X['o'], X['h'], X['l'], X['c'], X['Ap'], X['A']
    body, rng, uw, lw, m10, top, bot, E = X['body'], X['rng'], X['uw'], X['lw'], X['m10'], X['top'], X['bot'], X['E']
    o1, c1, h1, l1, b1, t1, bo1 = _sh(o), _sh(c), _sh(h), _sh(l), _sh(body), _sh(top), _sh(bot)
    o2, c2, b2 = _sh(o, 2), _sh(c, 2), _sh(body, 2)
    A3 = _sh(A, 3)
    mid2 = (o2 + c2) / 2
    with np.errstate(invalid='ignore'):
        _mask_events(out, 'hammer', (rng > 0) & (lw >= 2 * body) & (uw <= 0.25 * rng) & (rng >= 0.5 * Ap) & (c < m10), 'bull')
        _mask_events(out, 'shooting_star', (rng > 0) & (uw >= 2 * body) & (lw <= 0.25 * rng) & (rng >= 0.5 * Ap) & (c > m10), 'bear')
        _mask_events(out, 'bull_engulfing', (c1 < o1) & (c > o) & (o <= c1) & (c >= o1) & (body > b1) & (c1 < _sh(m10)), 'bull')
        _mask_events(out, 'bear_engulfing', (c1 > o1) & (c < o) & (o >= c1) & (c <= o1) & (body > b1) & (c1 > _sh(m10)), 'bear')
        ins = (h < h1) & (l > l1)
        up_e = E > _sh(E)
        _mask_events(out, 'inside_bar', ins & up_e, 'bull')
        _mask_events(out, 'inside_bar', ins & ~up_e, 'bear')
        doji = (rng > 0) & (body <= 0.1 * rng) & (rng >= 0.3 * Ap) & (np.arange(n) >= 10)
        rose = c > _sh(c, 10)
        _mask_events(out, 'doji', doji & rose, 'bear')
        _mask_events(out, 'doji', doji & ~rose, 'bull')
        _mask_events(out, 'morning_star', (c2 < o2) & (b2 >= 0.6 * A3) & (c2 < _sh(m10, 2)) & (b1 <= 0.3 * b2) & (t1 < mid2)
                     & (c > o) & (c > mid2), 'bull')
        _mask_events(out, 'evening_star', (c2 > o2) & (b2 >= 0.6 * A3) & (c2 > _sh(m10, 2)) & (b1 <= 0.3 * b2) & (bo1 > mid2)
                     & (c < o) & (c < mid2), 'bear')
        up = (c > o) & (body >= 0.4 * Ap) & (uw <= 0.3 * rng)
        st = (c > c1) & (o >= o1) & (o <= c1)
        tws = up & _sh(up) & _sh(up, 2) & st & _sh(st)
        _mask_events(out, 'three_white_soldiers', tws & ~_sh(tws), 'bull')
        dn = (c < o) & (body >= 0.4 * Ap) & (lw <= 0.3 * rng)
        st = (c < c1) & (o <= o1) & (o >= c1)
        tbc = dn & _sh(dn) & _sh(dn, 2) & st & _sh(st)
        _mask_events(out, 'three_black_crows', tbc & ~_sh(tbc), 'bear')
    return out, {}


# ------------------------------------------------------------------ Al Brooks
def _always_in(X):
    c, E = X['c'], X['E']
    with np.errstate(invalid='ignore'):
        up = (E > _sh(E, 5)) & (c > E) & (_sh(c) > _sh(E))
        dn = (E < _sh(E, 5)) & (c < E) & (_sh(c) < _sh(E))
    sig = np.where(up, 1, np.where(dn, -1, 0))
    idx = np.where(sig != 0, np.arange(len(c)), -1)
    last = np.maximum.accumulate(idx) if len(c) else idx
    return np.where(last >= 0, sig[np.maximum(last, 0)], 0)


def _pullback_second_leg(P, AI, side):
    """Bars where the second leg of a pullback ends (H2 when side = +1 on highs, L2 when side = −1 on lows)."""
    fires = []
    run = None
    inpb, cnt, seen = False, 0, False
    for i in range(1, len(P)):
        if AI[i] != side:
            run = None
            continue
        x, x1 = side * P[i], side * P[i - 1]
        if run is None or AI[i - 1] != side:
            run, inpb, cnt = x, False, 0
            continue
        if x > run:
            run, inpb, cnt = x, False, 0
            continue
        if not inpb:
            if x < x1:
                inpb, cnt, seen = True, 0, True
            continue
        if x > x1:
            if seen:
                cnt += 1
                seen = False
                if cnt == 2:
                    fires.append(i)
        else:
            seen = True
    return fires


def _brooks(X):
    out = []
    n = X['n']
    o, h, l, c, E, Ap, body, cp = X['o'], X['h'], X['l'], X['c'], X['E'], X['Ap'], X['body'], X['cp']
    H, L, C = X['H'], X['L'], X['C']
    ai = _always_in(X)
    if n > 1:
        prev = np.concatenate(([0], ai[:-1]))
        flip = (ai != prev) & (ai != 0) & (prev != 0)
        _mask_events(out, 'always_in_flip', flip & (ai == 1), 'bull')
        _mask_events(out, 'always_in_flip', flip & (ai == -1), 'bear')
    AI = ai.tolist()
    for i in _pullback_second_leg(H, AI, 1):
        _ev(out, 'h2_buy', i, 'bull')
    for i in _pullback_second_leg(L, AI, -1):
        _ev(out, 'l2_sell', i, 'bear')
    # wedges: three pushes on confirmed fractal swings
    is_sh, is_sl = X['is_sh'], X['is_sl']
    shs, sls, arm_t, arm_b = [], [], None, None
    for i in range(n):
        j = i - SWING_K
        if j >= 0 and is_sh[j]:
            shs.append(j)
            if len(shs) >= 3:
                j1, j2, j3 = shs[-3:]
                if H[j1] < H[j2] < H[j3] and j3 - j1 <= 60 and min(L[j2 + 1:j3]) > min(L[j1 + 1:j2]):
                    arm_t = (min(L[j2 + 1:j3]), j3 + 15, H[j3], j1, j3)
        if j >= 0 and is_sl[j]:
            sls.append(j)
            if len(sls) >= 3:
                j1, j2, j3 = sls[-3:]
                if L[j1] > L[j2] > L[j3] and j3 - j1 <= 60 and max(H[j2 + 1:j3]) < max(H[j1 + 1:j2]):
                    arm_b = (max(H[j2 + 1:j3]), j3 + 15, L[j3], j1, j3)
        if arm_t:
            if i > arm_t[1] or H[i] > arm_t[2]:
                arm_t = None
            elif C[i] < arm_t[0]:
                _ev(out, 'wedge_top', i, 'bear', trigger=arm_t[0], first_push=arm_t[3], third_push=arm_t[4])
                arm_t = None
        if arm_b:
            if i > arm_b[1] or L[i] < arm_b[2]:
                arm_b = None
            elif C[i] > arm_b[0]:
                _ev(out, 'wedge_bottom', i, 'bull', trigger=arm_b[0], first_push=arm_b[3], third_push=arm_b[4])
                arm_b = None
    # breakouts of the 20-bar range, strong and failed
    hh, ll = _sh(_roll(h, 20, 'max')), _sh(_roll(l, 20, 'min'))
    with np.errstate(invalid='ignore'):
        bu = (c > hh) & (body >= 0.8 * Ap) & (cp >= 0.75) & (c > o)
        bd = (c < ll) & (body >= 0.8 * Ap) & (cp <= 0.25) & (c < o)
    _mask_events(out, 'brooks_breakout', bu, 'bull')
    _mask_events(out, 'brooks_breakout', bd, 'bear')
    HH, LL = hh.tolist(), ll.tolist()
    pu = pd = None
    for i in range(n):
        if pu is not None:
            if i > pu[1]:
                pu = None
            elif C[i] < pu[0]:
                _ev(out, 'failed_breakout', i, 'bear', level=pu[0], breakout=pu[2])
                pu = None
        if pd is not None:
            if i > pd[1]:
                pd = None
            elif C[i] > pd[0]:
                _ev(out, 'failed_breakout', i, 'bull', level=pd[0], breakout=pd[2])
                pd = None
        if HH[i] == HH[i] and C[i] > HH[i]:
            pu = (HH[i], i + 3, i)
        if LL[i] == LL[i] and C[i] < LL[i]:
            pd = (LL[i], i + 3, i)
    # state
    with np.errstate(invalid='ignore', divide='ignore'):
        ad = np.abs(np.diff(c, prepend=c[:1]))
        s20 = _mean(ad, 20) * 20
        er = np.where(s20 > 0, np.abs(c - _sh(c, 20)) / np.where(s20 > 0, s20, 1.0), np.nan)
        fa = _mean((c > E).astype(float), 20)
        trend = (er >= 0.30) & ((fa >= 0.7) | (fa <= 0.3))
    mm = None
    strong = np.nonzero(bu | bd)[0]
    if len(strong):
        b = int(strong[-1])
        height = float(hh[b] - ll[b])
        up = bool(bu[b])
        tgt = float(hh[b] + height) if up else float(ll[b] - height)
        reached = bool((h[b + 1:] >= tgt).any()) if up else bool((l[b + 1:] <= tgt).any())
        mm = {'i': b, 'dir': 'bull' if up else 'bear', 'level': float(hh[b] if up else ll[b]), 'height': height,
              'target': tgt, 'reached': reached}
    raw = {'ai': ai, 'er': er, 'fa': fa, 'trend': trend, 'mm': mm}
    return out, raw


# ------------------------------------------------------------------ market structure + ICT
def _structure(X):
    """Swing points with labels, BOS / CHoCH, liquidity sweeps, order blocks and fair value gaps."""
    out = []
    n = X['n']
    H, L, C, O, AL = X['H'], X['L'], X['C'], X['O'], X['AL']
    is_sh, is_sl = X['is_sh'], X['is_sl']
    swings = []                                 # (bar, price, 'high'|'low', label, confirmed at)
    last_h = last_l = None                      # [price, bar, broken]
    prev_hp = prev_lp = None
    sweep_h = sweep_l = None                    # latest untaken swing (price, bar)
    trend = 0
    breaks = []                                 # {'i', 'kind', 'dir', 'level', 'swing'}
    obs = []
    for i in range(n):
        j = i - SWING_K
        if j >= 0 and is_sh[j]:
            lab = '' if prev_hp is None else ('HH' if H[j] > prev_hp else 'LH')
            swings.append((j, H[j], 'high', lab, i))
            prev_hp = H[j]
            last_h = [H[j], j, False]
            sweep_h = (H[j], j)                     # a fractal high is not exceeded by the 3 bars after it
        if j >= 0 and is_sl[j]:
            lab = '' if prev_lp is None else ('LL' if L[j] < prev_lp else 'HL')
            swings.append((j, L[j], 'low', lab, i))
            prev_lp = L[j]
            last_l = [L[j], j, False]
            sweep_l = (L[j], j)
        # liquidity sweeps: a wick through the latest untaken swing that closes back inside
        if sweep_h is not None and H[i] > sweep_h[0]:
            if C[i] < sweep_h[0]:
                _ev(out, 'liquidity_sweep', i, 'bear', level=sweep_h[0], swing=sweep_h[1])
            sweep_h = None
        if sweep_l is not None and L[i] < sweep_l[0]:
            if C[i] > sweep_l[0]:
                _ev(out, 'liquidity_sweep', i, 'bull', level=sweep_l[0], swing=sweep_l[1])
            sweep_l = None
        # BOS / CHoCH on closes
        kind = None
        if last_h is not None and not last_h[2] and C[i] > last_h[0]:
            last_h[2] = True
            kind = 'bos' if trend == 1 else ('choch' if trend == -1 else None)
            lvl, sw, d, trend = last_h[0], last_h[1], 'bull', 1
        elif last_l is not None and not last_l[2] and C[i] < last_l[0]:
            last_l[2] = True
            kind = 'bos' if trend == -1 else ('choch' if trend == 1 else None)
            lvl, sw, d, trend = last_l[0], last_l[1], 'bear', -1
        if kind:
            _ev(out, kind, i, d, level=lvl, swing=sw)
            breaks.append({'i': i, 'kind': kind, 'dir': d, 'level': lvl, 'swing': sw})
            # order block: the last opposite-coloured bar among the 10 before the break, if the move from it is a
            # displacement of at least 1.5 ATR
            for k in range(i - 1, max(-1, i - 11), -1):
                if (d == 'bull' and C[k] < O[k]) or (d == 'bear' and C[k] > O[k]):
                    if abs(C[i] - C[k]) >= 1.5 * AL[i]:
                        obs.append({'t': i, 'bar': k, 'bottom': L[k], 'top': H[k], 'dir': d})
                    break
    _zone_tests(obs, X, 'order_block', 120, out)
    # fair value gaps
    h, l, c, A = X['h'], X['l'], X['c'], X['A']
    fvgs = []
    if n >= 3:
        with np.errstate(invalid='ignore'):
            h2, l2 = _sh(h, 2), _sh(l, 2)
            bu = np.nonzero((h2 < l) & (l - h2 >= 0.1 * A))[0]
            be = np.nonzero((l2 > h) & (l2 - h >= 0.1 * A))[0]
        fvgs = [{'t': int(i), 'bottom': float(h[i - 2]), 'top': float(l[i]), 'dir': 'bull'} for i in bu] + \
               [{'t': int(i), 'bottom': float(h[i]), 'top': float(l[i - 2]), 'dir': 'bear'} for i in be]
        fvgs.sort(key=lambda z: z['t'])
        _zone_tests(fvgs, X, 'fvg_return', 250, out)
        for z in fvgs:                             # filled = a later bar traded through the whole gap
            seg = l[z['t'] + 1:] <= z['bottom'] if z['dir'] == 'bull' else h[z['t'] + 1:] >= z['top']
            z['filled'] = int(z['t'] + 1 + np.argmax(seg)) if seg.any() else None
    raw = {'swings': swings, 'trend': trend, 'breaks': breaks, 'obs': obs, 'fvgs': fvgs,
           'sweep_h': sweep_h, 'sweep_l': sweep_l}
    return out, raw


# ------------------------------------------------------------------ classic chart patterns (Lo–Mamaysky–Wang style)
def _patterns(X):
    out = []
    n = X['n']
    c, h, l, A = X['c'], X['h'], X['l'], X['A']
    C, H, L = X['C'], X['H'], X['L']
    mx, mn = local_extrema(c, c, EXT_W)
    conf = {}
    for j in mx.tolist():
        conf.setdefault(j + EXT_W, []).append((j, 1))
    for j in mn.tolist():
        conf.setdefault(j + EXT_W, []).append((j, -1))
    E = []                                         # alternating extrema [(bar, close, +1 max / −1 min)]
    pend = []                                      # armed patterns waiting for their breakout
    seen = set()
    tris = []
    near = lambda a, b, tol=0.015: abs(a - b) <= tol * (abs(a) + abs(b)) / 2

    def line(j1, p1, j2, p2, i):
        return p1 + (p2 - p1) * (i - j1) / (j2 - j1)

    for i in range(n):
        for j, s in conf.get(i, ()):
            if E and E[-1][2] == s:
                if s * C[j] > s * E[-1][1]:
                    E[-1] = (j, C[j], s)
                else:
                    continue
            else:
                E.append((j, C[j], s))
            if len(E) >= 5:
                (j1, e1, s1), (j2, e2, _), (j3, e3, _), (j4, e4, _), (j5, e5, _) = E[-5:]
                key = (j1, j5)
                if key not in seen:
                    seen.add(key)
                    half = (j5 - j1) // 2
                    if s1 == 1 and e3 > e1 and e3 > e5 and near(e1, e5) and near(e2, e4):
                        pend.append({'rule': 'head_shoulders', 'dir': 'bear', 'line': (j2, e2, j4, e4), 'cancel': e3,
                                     'until': j5 + half, 'piv': [j1, j2, j3, j4, j5]})
                    if s1 == -1 and e3 < e1 and e3 < e5 and near(e1, e5) and near(e2, e4):
                        pend.append({'rule': 'inv_head_shoulders', 'dir': 'bull', 'line': (j2, e2, j4, e4), 'cancel': e3,
                                     'until': j5 + half, 'piv': [j1, j2, j3, j4, j5]})
                    # one triangle per pattern: a window sharing 4 extrema with an armed triangle is the same one
                    new_tri = not any(len(t_ & {j1, j2, j3, j4, j5}) >= 4 for t_ in tris)
                    if new_tri and s1 == 1 and e1 > e3 > e5 and e2 < e4:
                        tris.append({j1, j2, j3, j4, j5})
                        pend.append({'rule': 'triangle', 'dir': 'both', 'up': (j3, e3, j5, e5), 'dn': (j2, e2, j4, e4),
                                     'until': j5 + half, 'piv': [j1, j2, j3, j4, j5]})
                    if new_tri and s1 == -1 and e1 < e3 < e5 and e2 > e4:
                        tris.append({j1, j2, j3, j4, j5})
                        pend.append({'rule': 'triangle', 'dir': 'both', 'up': (j2, e2, j4, e4), 'dn': (j3, e3, j5, e5),
                                     'until': j5 + half, 'piv': [j1, j2, j3, j4, j5]})
            if len(E) >= 3:
                (j1, e1, s1), (j2, e2, _), (j3, e3, _) = E[-3:]
                key = ('d', j1, j3)
                if key not in seen and j3 - j1 >= 20 and near(e1, e3):
                    seen.add(key)
                    if s1 == 1 and e2 <= 0.97 * min(e1, e3):
                        pend.append({'rule': 'double_top', 'dir': 'bear', 'level': e2, 'cancel': 1.015 * max(e1, e3),
                                     'until': j3 + (j3 - j1), 'piv': [j1, j2, j3]})
                    if s1 == -1 and e2 >= 1.03 * max(e1, e3):
                        pend.append({'rule': 'double_bottom', 'dir': 'bull', 'level': e2, 'cancel': min(e1, e3) / 1.015,
                                     'until': j3 + (j3 - j1), 'piv': [j1, j2, j3]})
            if s == 1 and E[-1][0] == j:            # cup with handle: this maximum is the right rim
                for jl, el, sl in reversed(E[:-1]):
                    if sl != 1:
                        continue
                    w = j - jl
                    if w > 150:
                        break
                    if w < 30 or not (0.95 * el <= C[j] <= 1.03 * el) or ('c', jl, j) in seen:
                        continue
                    seg = c[jl:j + 1]
                    bot = float(seg.min())
                    rim = max(el, C[j])
                    depth = 1 - bot / el
                    pos = (int(np.argmin(seg))) / w
                    mid = (el + bot) / 2
                    if 0.12 <= depth <= 0.35 and 0.2 <= pos <= 0.8 and float(seg[1:-1].max()) <= rim and \
                            float((seg < mid).mean()) >= 0.55:
                        seen.add(('c', jl, j))
                        pend.append({'rule': 'cup_handle', 'dir': 'bull', 'level': rim,
                                     'cancel': rim * (1 - min(0.12, depth / 2)), 'until': j + 40, 'piv': [jl, j]})
                        break
        keep = []
        for p in pend:
            r = p['rule']
            if i > p['until']:
                continue
            fired = False
            if r in ('head_shoulders', 'inv_head_shoulders'):
                nk = line(*p['line'], i)
                if (r == 'head_shoulders' and C[i] > p['cancel']) or (r == 'inv_head_shoulders' and C[i] < p['cancel']):
                    continue
                if (r == 'head_shoulders' and C[i] < nk) or (r == 'inv_head_shoulders' and C[i] > nk):
                    _ev(out, r, i, p['dir'], neckline=nk, pivots=p['piv'])
                    fired = True
            elif r == 'triangle':
                up, dn = line(*p['up'], i), line(*p['dn'], i)
                if C[i] > up:
                    _ev(out, r, i, 'bull', upper=up, lower=dn, pivots=p['piv'])
                    fired = True
                elif C[i] < dn:
                    _ev(out, r, i, 'bear', upper=up, lower=dn, pivots=p['piv'])
                    fired = True
            elif r in ('double_top', 'double_bottom'):
                if (r == 'double_top' and C[i] > p['cancel']) or (r == 'double_bottom' and C[i] < p['cancel']):
                    continue
                if (r == 'double_top' and C[i] < p['level']) or (r == 'double_bottom' and C[i] > p['level']):
                    _ev(out, r, i, p['dir'], level=p['level'], pivots=p['piv'])
                    fired = True
            elif r == 'cup_handle':
                if C[i] < p['cancel']:
                    continue
                if i > p['piv'][1] and C[i] > p['level']:
                    _ev(out, r, i, 'bull', rim=p['level'], pivots=p['piv'])
                    fired = True
            if not fired:
                keep.append(p)
        pend = keep
    # flags: pole, then a tight 5–15-bar flag, then a close beyond it
    lo10, hi10 = _roll(l, 10, 'min'), _roll(h, 10, 'max')
    bull_m, bear_m = np.zeros(n, bool), np.zeros(n, bool)
    with np.errstate(invalid='ignore'):
        pole_u = c - lo10
        pole_d = hi10 - c
        for m in range(5, 16):
            if n < m + 12:
                break
            fh, fl = _sh(_roll(h, m, 'max')), _sh(_roll(l, m, 'min'))
            pu, pdn, pc, ph, pl, pa = (_sh(x, m + 1) for x in (pole_u, pole_d, c, h, l, A))
            c1 = _sh(c)
            bull_m |= (pu >= 4 * pa) & (fh - fl <= 0.5 * pu) & (fh <= ph + 0.25 * pa) & (c1 <= pc) & (c > fh)
            bear_m |= (pdn >= 4 * pa) & (fh - fl <= 0.5 * pdn) & (fl >= pl - 0.25 * pa) & (c1 >= pc) & (c < fl)
    for rule, m_, d in (('bull_flag', bull_m, 'bull'), ('bear_flag', bear_m, 'bear')):
        last = -99
        for i in np.nonzero(m_)[0].tolist():
            if i - last >= 5:
                _ev(out, rule, i, d)
                last = i
    return out, {'extrema': E, 'pending': pend}


# ------------------------------------------------------------------ Wyckoff
WY_RANGE, WY_SPAN, WY_PRIOR, WY_MOVE, WY_LIFE = 30, 6.0, 60, 4.0, 30   # a range lasts 30–60 bars


def _wyckoff(X):
    out = []
    n = X['n']
    h, l, c, A = X['h'], X['l'], X['c'], X['A']
    H, L, C, AL = X['H'], X['L'], X['C'], X['AL']
    SP, VR = np.nan_to_num(X['sp']).tolist(), np.nan_to_num(X['vr']).tolist()
    rh, rl = _roll(h, WY_RANGE, 'max').tolist(), _roll(l, WY_RANGE, 'min').tolist()
    rng = None                         # {'lo', 'hi', 'start', 'found', 'kind'}
    phase, since, ranges = None, None, []
    last_sp = last_ut = -99
    outside = 0
    trail = None                       # the range a markup / markdown left: crossing back through it ends the phase
    for i in range(n):
        if trail is not None and ((phase == 'markup' and C[i] < trail['lo']) or (phase == 'markdown' and C[i] > trail['hi'])):
            phase, since, trail = None, i, None
        if rng is None:
            s = i - WY_RANGE + 1
            if s - WY_PRIOR >= 0 and rh[i] - rl[i] <= WY_SPAN * AL[i]:
                move = C[s] - C[s - WY_PRIOR]
                if abs(move) >= WY_MOVE * AL[i]:
                    kind = 'accumulation' if move < 0 else 'distribution'
                    rng = {'lo': rl[i], 'hi': rh[i], 'start': s, 'found': i, 'kind': kind}
                    phase, since, outside = kind, i, 0
                    ranges.append(rng)
            continue
        lo, hi, a = rng['lo'], rng['hi'], AL[i]
        end = None
        if C[i] > hi + 0.25 * a and SP[i] >= 1.0 and VR[i] >= 1.0:
            _ev(out, 'sos', i, 'bull', range_low=lo, range_high=hi)
            end = 'markup'
        elif C[i] < lo - 0.25 * a and SP[i] >= 1.0 and VR[i] >= 1.0:
            _ev(out, 'sow', i, 'bear', range_low=lo, range_high=hi)
            end = 'markdown'
        else:
            if L[i] < lo <= C[i] <= hi and i - last_sp >= 5:
                _ev(out, 'spring', i, 'bull', range_low=lo, volume_ratio=VR[i], phase=rng['kind'])
                last_sp = i
            if H[i] > hi >= C[i] >= lo and i - last_ut >= 5:
                _ev(out, 'upthrust', i, 'bear', range_high=hi, volume_ratio=VR[i], phase=rng['kind'])
                last_ut = i
            outside = outside + 1 if (C[i] > hi or C[i] < lo) else 0
            if outside >= 3:
                end = 'markup' if C[i] > hi else 'markdown'
            elif i - rng['found'] >= WY_LIFE:
                end = 'expired'
        if end:
            rng['end'] = i
            rng['result'] = end
            phase, since = (None, i) if end == 'expired' else (end, i)
            trail = None if end == 'expired' else rng
            rng = None
    return out, {'phase': phase, 'since': since, 'ranges': ranges, 'active': rng}


# ------------------------------------------------------------------ volume spread analysis
def _vsa(X):
    out = []
    n = X['n']
    if n < AVG_N + 3:
        return out, {}
    h, l, c, v, sp, vr, cp, m10, E = X['h'], X['l'], X['c'], X['v'], X['sp'], X['vr'], X['cp'], X['m10'], X['E']
    c1, l1, v1, v2 = _sh(c), _sh(l), _sh(v), _sh(v, 2)
    lowv = (v < v1) & (v < v2)
    with np.errstate(invalid='ignore'):
        _mask_events(out, 'no_demand', (c > c1) & (sp < 0.7) & lowv & (cp <= 0.6), 'bear')
        _mask_events(out, 'no_supply', (c < c1) & (sp < 0.7) & lowv & (cp >= 0.4), 'bull')
        _mask_events(out, 'stopping_volume', (l <= _roll(l, 10, 'min')) & (vr >= 2) & (sp >= 1) & (cp >= 0.5), 'bull')
        _mask_events(out, 'selling_climax', (l <= _roll(l, 20, 'min')) & (c < m10) & (sp >= 2) & (vr >= 2.5), 'bull')
        _mask_events(out, 'buying_climax', (h >= _roll(h, 20, 'max')) & (c > m10) & (sp >= 2) & (vr >= 2.5), 'bear')
        _mask_events(out, 'vsa_upthrust', (h > _sh(_roll(h, 10, 'max'))) & (sp >= 1.2) & (vr >= 1.5) & (cp <= 0.3), 'bear')
        _mask_events(out, 'vsa_test', (l < l1) & (cp >= 0.6) & (sp < 1) & lowv & (c > E), 'bull')
    return out, {}


def vsa_label(sp, vr, cp, up):
    """Plain words for one bar: spread, volume, where it closed, up or down."""
    def size(x, words):
        if not _fin(x):
            return None
        return words[0] if x < 0.7 else (words[3] if x >= 2 else (words[2] if x > 1.3 else words[1]))
    parts = [size(sp, ('narrow spread', 'average spread', 'wide spread', 'ultra-wide spread')),
             size(vr, ('low volume', 'average volume', 'high volume', 'ultra-high volume')),
             'closes low' if cp < 1 / 3 else ('closes high' if cp > 2 / 3 else 'closes mid-bar'),
             'up bar' if up else 'down bar']
    return ', '.join(p for p in parts if p)


# ------------------------------------------------------------------ volume profile
def _profiles(Hw, Lw, Vw, bins=PROFILE_BINS, va=VALUE_AREA):
    """Batched volume profiles: Hw, Lw, Vw are (W, m) windows. Returns (edges (W, bins+1), vol (W, bins), poc index,
    value-area low index a, high index b, valid mask)."""
    W = Hw.shape[0]
    lo, hi = Lw.min(axis=1), Hw.max(axis=1)
    edges = lo[:, None] + (hi - lo)[:, None] * (np.arange(bins + 1) / bins)[None, :]
    span = Hw - Lw
    ov = np.minimum(Hw[:, :, None], edges[:, None, 1:]) - np.maximum(Lw[:, :, None], edges[:, None, :-1])
    np.clip(ov, 0.0, None, out=ov)
    w = ov / np.where(span > 0, span, 1.0)[:, :, None]
    zr, zc = np.nonzero(span <= 0)
    if len(zr):
        w[zr, zc] = 0.0
        width = np.where(hi > lo, hi - lo, 1.0)
        k = np.clip(((Hw[zr, zc] - lo[zr]) / width[zr] * bins).astype(int), 0, bins - 1)
        w[zr, zc, k] = 1.0
    vol = np.einsum('wmb,wm->wb', w, Vw)
    tot = vol.sum(axis=1)
    valid = (tot > 0) & (hi > lo)
    poc = np.argmax(vol, axis=1)
    r = np.arange(W)
    a, b = poc.copy(), poc.copy()
    acc, target = vol[r, poc].copy(), va * tot
    for _ in range(bins - 1):
        need = (acc < target) & ((a > 0) | (b < bins - 1))
        if not need.any():
            break
        dn = np.where(a > 0, vol[r, np.maximum(a - 1, 0)], -1.0)
        up = np.where(b < bins - 1, vol[r, np.minimum(b + 1, bins - 1)], -1.0)
        go_up = need & (up >= dn)
        go_dn = need & ~go_up
        b += go_up
        a -= go_dn
        acc += np.where(go_up, up, 0.0) + np.where(go_dn, dn, 0.0)
    return edges, vol, poc, a, b, valid


def volume_profile(h, l, v, bins=PROFILE_BINS, va=VALUE_AREA):
    """One window's volume profile (see the module docstring): {'poc', 'vah', 'val', 'hvn', 'lvn', 'edges', 'volumes'}, or
    None when the window has no volume or no price range."""
    h, l = _f(h), _f(l)
    v = np.nan_to_num(_f(v), nan=0.0, posinf=0.0, neginf=0.0)
    if not len(h):
        return None
    edges, vol, poc, a, b, valid = _profiles(h[None, :], l[None, :], v[None, :], bins, va)
    if not valid[0]:
        return None
    e, vv, p = edges[0], vol[0], int(poc[0])
    mid = (e[:-1] + e[1:]) / 2
    s = np.convolve(vv, np.ones(3) / 3, mode='same')
    m = s.mean()
    pk = [j for j in range(1, bins - 1) if s[j] > s[j - 1] and s[j] >= s[j + 1] and s[j] >= m]
    tr = [j for j in range(1, bins - 1) if s[j] < s[j - 1] and s[j] <= s[j + 1] and s[j] <= 0.6 * m]
    return {'poc': float(mid[p]), 'vah': float(e[int(b[0]) + 1]), 'val': float(e[int(a[0])]), 'edges': e, 'volumes': vv,
            'hvn': [float(mid[j]) for j in sorted(pk, key=lambda j: -s[j])[:3]],
            'lvn': [float(mid[j]) for j in sorted(tr, key=lambda j: s[j])[:3]]}


def _profile_events(X):
    out = []
    n, N, S = X['n'], PROFILE_EVENT_N, PROFILE_STEP
    if n <= N + 1:
        return out, {}
    starts = np.arange(N, n, S)
    idx = starts[:, None] - N + np.arange(N)[None, :]
    edges, vol, poc, a, b, valid = _profiles(X['h'][idx], X['l'][idx], X['v'][idx])
    r = np.arange(len(starts))
    val, vah = edges[r, a], edges[r, b + 1]
    blk = (np.arange(n) - N) // S
    ok = (blk >= 0) & (np.arange(n) >= 1)
    bi = np.clip(blk, 0, len(starts) - 1)
    VAL, VAH = np.where(ok & valid[bi], val[bi], np.nan), np.where(ok & valid[bi], vah[bi], np.nan)
    c, c1 = X['c'], _sh(X['c'])
    with np.errstate(invalid='ignore'):
        inside = (c >= VAL) & (c <= VAH)
        _mask_events(out, 'va_reentry', (c1 > VAH) & inside, 'bear')
        _mask_events(out, 'va_reentry', (c1 < VAL) & inside, 'bull')
        _mask_events(out, 'vah_breakout', (c1 <= VAH) & (c1 >= VAL) & (c > VAH), 'bull')
        _mask_events(out, 'val_breakdown', (c1 >= VAL) & (c1 <= VAH) & (c < VAL), 'bear')
    return out, {}


# ------------------------------------------------------------------ support / resistance, supply / demand
LEVEL_LIFE = 500
LEVEL_COOL = 10        # one event of each kind per level per 10 bars


def _merge_levels(levels, tol):
    """Levels whose prices have drifted within `tol` of each other become one (touches add up, the price is the mean of
    all their swing prices)."""
    levels = sorted(levels, key=lambda z: z['price'])
    out = []
    for lv in levels:
        if out and lv['price'] - out[-1]['price'] <= tol:
            a = out[-1]
            a['sum'] += lv['sum']
            a['touches'] += lv['touches']
            a['price'] = a['sum'] / a['touches']
            a['first'], a['last'] = min(a['first'], lv['first']), max(a['last'], lv['last'])
            for r_, t_ in lv['cool'].items():
                a['cool'][r_] = max(a['cool'].get(r_, -99), t_)
        else:
            out.append(lv)
    return out


def _levels(X):
    out = []
    n = X['n']
    H, L, C, AL = X['H'], X['L'], X['C'], X['AL']
    is_sh, is_sl = X['is_sh'], X['is_sl']
    levels = []                                  # {'price', 'sum', 'touches', 'first', 'last'}
    act, act_px = [], []                         # levels with ≥ 2 touches, sorted by price (rebuilt when they change)
    dirty = False
    for i in range(n):
        j = i - SWING_K
        if j >= 0:
            for px, ok in ((H[j], is_sh[j]), (L[j], is_sl[j])):
                if not ok:
                    continue
                tol = LEVEL_TOL * AL[i]
                best, bd = None, tol
                for lv in levels:
                    d = abs(lv['price'] - px)
                    if d <= bd and j - lv['last'] <= LEVEL_LIFE:
                        best, bd = lv, d
                if best is None:
                    levels.append({'price': px, 'sum': px, 'touches': 1, 'first': j, 'last': j, 'cool': {}})
                else:
                    best['sum'] += px
                    best['touches'] += 1
                    best['price'] = best['sum'] / best['touches']
                    best['last'] = j
                    dirty = True
        if dirty or (i % 50 == 0):
            levels = _merge_levels([lv for lv in levels if i - lv['last'] <= LEVEL_LIFE], LEVEL_TOL * AL[i])
            act = sorted((lv for lv in levels if lv['touches'] >= 2), key=lambda z: z['price'])
            act_px = [lv['price'] for lv in act]
            dirty = False
        if i == 0 or not act:
            continue
        a = AL[i - 1]
        lo, hi = bisect.bisect_left(act_px, min(L[i], C[i - 1]) - 0.5 * a), bisect.bisect_right(act_px, max(H[i], C[i - 1]) + 0.5 * a)
        got = {}
        for lv in act[lo:hi]:
            P = lv['price']
            if C[i - 1] >= P and P - 0.5 * a <= L[i] <= P + 0.25 * a and C[i] >= P + 0.25 * a:
                k = ('support_bounce', 'bull')
            elif C[i - 1] <= P and P - 0.25 * a <= H[i] <= P + 0.5 * a and C[i] <= P - 0.25 * a:
                k = ('resistance_reject', 'bear')
            elif C[i - 1] <= P and C[i] >= P + 0.25 * a:
                k = ('level_break', 'bull')
            elif C[i - 1] >= P and C[i] <= P - 0.25 * a:
                k = ('level_break', 'bear')
            else:
                continue
            if i - lv['cool'].get(k[0], -99) < LEVEL_COOL:
                continue
            if k not in got or lv['touches'] > got[k]['touches']:
                got[k] = lv
        for (rule, d), lv in sorted(got.items(), key=lambda z: z[0]):
            lv['cool'][rule] = i
            _ev(out, rule, i, d, level=lv['price'], touches=lv['touches'])
    # supply / demand zones: a 1–3-bar base of small bars, then a 2-ATR move within 3 bars
    h, l, c, A, rng = X['h'], X['l'], X['c'], X['A'], X['rng']
    small = rng <= 0.7 * A
    zones, done = [], set()
    with np.errstate(invalid='ignore'):
        hits = []
        for k in (1, 2, 3):
            sb, cb, Ab, nxt = _sh(small, k), _sh(c, k), _sh(A, k), _sh(small, k - 1)
            hits += [(int(i), k, 'bull') for i in np.nonzero(sb & ~nxt & (c - cb >= 2 * Ab))[0]]
            hits += [(int(i), k, 'bear') for i in np.nonzero(sb & ~nxt & (cb - c >= 2 * Ab))[0]]
    for i, k, d in sorted(hits):
        b = i - k
        if (b, d) in done:
            continue
        done.add((b, d))
        s = b
        while s - 1 >= 0 and b - (s - 1) < 3 and small[s - 1]:
            s -= 1
        zones.append({'t': i, 'base': (s, b), 'bottom': float(l[s:b + 1].min()), 'top': float(h[s:b + 1].max()), 'dir': d})
    zb = _zone_tests([z for z in zones if z['dir'] == 'bull'], X, 'demand_zone_test', LEVEL_LIFE, out)
    zs = _zone_tests([z for z in zones if z['dir'] == 'bear'], X, 'supply_zone_test', LEVEL_LIFE, out)
    return out, {'levels': levels, 'zones': sorted(zb + zs, key=lambda z: z['t'])}


# ------------------------------------------------------------------ Elliott waves
def _elliott(X):
    out = []
    piv = zigzag(X['h'], X['l'], X['A'])
    imps = []
    for m in range(5, len(piv)):
        P = [p[1] for p in piv[m - 5:m + 1]]
        if elliott_impulse_ok(P):
            up = P[1] > P[0]
            imps.append(m)
            _ev(out, 'elliott_impulse', piv[m][3], 'bear' if up else 'bull', impulse='up' if up else 'down',
                start=piv[m - 5][0], end=piv[m][0])
            if m + 3 < len(piv):
                a, b, c = (piv[m + k][1] for k in (1, 2, 3))
                if elliott_abc_ok(P[5], P[0], a, b, c):
                    _ev(out, 'elliott_abc', piv[m + 3][3], 'bull' if up else 'bear', impulse='up' if up else 'down',
                        c_end=piv[m + 3][0])
    return out, {'pivots': piv, 'impulses': imps}


def elliott_count(piv):
    """The current count from zigzag pivots [(bar, price, ±1, confirmed at)]: the latest valid impulse and what followed,
    else a partial impulse still forming. Returns {'label', 'waves': [(name, pivot index)], 'ratios'}."""
    def ratios(P):
        w = [abs(P[k + 1] - P[k]) for k in range(len(P) - 1)]
        r = {}
        if len(w) >= 2 and w[0]:
            r['wave2_retrace'] = w[1] / w[0]
        if len(w) >= 3 and w[0]:
            r['wave3_vs_wave1'] = w[2] / w[0]
        if len(w) >= 4 and w[2]:
            r['wave4_retrace'] = w[3] / w[2]
        if len(w) >= 5 and w[0]:
            r['wave5_vs_wave1'] = w[4] / w[0]
        return r
    N = len(piv)
    for m in range(N - 1, 4, -1):
        P = [p[1] for p in piv[m - 5:m + 1]]
        if not elliott_impulse_ok(P):
            continue
        if N - 1 - m > 3:
            break                                # the last impulse is too old: look for a partial count instead
        up = P[1] > P[0]
        waves = [(str(k), m - 5 + k) for k in range(6)]
        r = ratios(P)
        after = N - 1 - m
        if after == 0:
            label = f"5-wave impulse {'up' if up else 'down'} complete: an A-B-C correction is expected"
        elif after == 1:
            label, waves = 'correction: wave A done, wave B under way', waves + [('A', m + 1)]
        elif after == 2:
            label, waves = 'correction: waves A and B done, wave C under way', waves + [('A', m + 1), ('B', m + 2)]
        else:
            a, b, c = (piv[m + k][1] for k in (1, 2, 3))
            ok = elliott_abc_ok(P[5], P[0], a, b, c)
            label = ('A-B-C correction complete: the impulse direction may resume' if ok else
                     'the move after the impulse does not fit an A-B-C; count open')
            waves = waves + [('A', m + 1), ('B', m + 2), ('C', m + 3)]
        if after >= 1:
            A_ = abs(piv[m + 1][1] - P[5])
            if after >= 2 and A_:
                r['b_retrace_of_a'] = abs(piv[m + 2][1] - piv[m + 1][1]) / A_
            if after >= 3 and A_:
                r['c_vs_a'] = abs(piv[m + 3][1] - piv[m + 2][1]) / A_
        return {'label': label, 'direction': 'up' if up else 'down', 'waves': waves, 'ratios': r}
    for k in (5, 4):                             # a partial impulse among the latest pivots (waves 1–4 or 1–3)
        if N < k:
            continue
        P = [p[1] for p in piv[N - k:]]
        s = 1.0 if P[1] > P[0] else -1.0
        q = [s * x for x in P]
        ok = q[1] > q[0] and q[0] < q[2] < q[1] and q[3] > q[1]
        if ok and k == 5:
            ok = q[1] < q[4] < q[3]
        if ok:
            return {'label': f"impulse {'up' if s > 0 else 'down'} forming: waves 1–{k - 1} counted, wave {k} under way",
                    'direction': 'up' if s > 0 else 'down', 'waves': [(str(t), N - k + t) for t in range(k)],
                    'ratios': ratios(P)}
    return {'label': 'no valid count (the latest swings break the hard rules)', 'direction': None, 'waves': [], 'ratios': {}}


# ------------------------------------------------------------------ quantitative rules
def _quant(X):
    out = []
    n = X['n']
    h, l, c = X['h'], X['l'], X['c']
    with np.errstate(invalid='ignore', divide='ignore'):
        for N, rule in ((20, 'donchian20'), (55, 'donchian55')):
            up = c > _sh(_roll(h, N, 'max'))
            dn = c < _sh(_roll(l, N, 'min'))
            _mask_events(out, rule, up & ~_sh(up), 'bull')
            _mask_events(out, rule, dn & ~_sh(dn), 'bear')
        lc = np.log(np.where(c > 0, c, np.nan))
        mom = _sh(lc, MONTH) - _sh(lc, YEAR)
        hi52 = c / _roll(c, YEAR, 'max')
        r21 = lc - _sh(lc, MONTH)
    month_bar = (np.arange(n) % MONTH == MONTH - 1) & (np.arange(n) >= YEAR)
    with np.errstate(invalid='ignore'):
        _mask_events(out, 'tsmom', month_bar & (mom > 0), 'bull')
        _mask_events(out, 'tsmom', month_bar & (mom <= 0), 'bear')
        _mask_events(out, 'hi52', month_bar & (hi52 >= 0.95), 'bull')
    pct = np.full(n, np.nan)
    hist = []
    prev = 0
    R = r21.tolist()
    for i in range(n):
        x = R[i]
        if x != x:
            continue
        if len(hist) >= YEAR:
            p = bisect.bisect_left(hist, x) / len(hist)
            pct[i] = p
            zone = 1 if p >= 0.9 else (-1 if p <= 0.1 else 0)
            if zone and zone != prev:
                _ev(out, 'st_reversal', i, 'bear' if zone > 0 else 'bull', pct=p, r21=x)
            prev = zone
        bisect.insort(hist, x)
    return out, {'mom': mom, 'hi52': hi52, 'r21': r21, 'pct': pct}


# ------------------------------------------------------------------ detection
FAMILY_FN = (('candlestick', _candles), ('brooks', _brooks), ('structure', _structure), ('pattern', _patterns),
             ('wyckoff', _wyckoff), ('vsa', _vsa), ('profile', _profile_events), ('levels', _levels),
             ('elliott', _elliott), ('quant', _quant))


def _analyse(o, h, l, c, v):
    X = _ctx(o, h, l, c, v)
    events, raw = [], {}
    if X['n'] >= 2:
        for fam, fn in FAMILY_FN:
            ev, r = fn(X)
            events += ev
            raw[fam] = r
    events.sort(key=lambda e: (e['i'], e['rule'], e['dir']))
    return X, events, raw


def detect(o, h, l, c, v):
    """Every event of every rule: a list of {'rule', 'i', 'dir', 'info'} sorted by bar, each computed from bars 0..i only."""
    return _analyse(o, h, l, c, v)[1]


# ------------------------------------------------------------------ the reading at the last bar
def _d(dates, i):
    return dates[i] if dates is not None and 0 <= i < len(dates) else None


def _last_test(X, P, start):
    """Last bar since `start` whose range came within 0.25 ATR of price P (None if none)."""
    a = 0.25 * X['A'][start:]
    hit = (X['l'][start:] - a <= P) & (X['h'][start:] + a >= P)
    return start + int(len(hit) - 1 - np.argmax(hit[::-1])) if hit.any() else None


def _profile_json(p, d=4):
    if not p:
        return None
    return {'poc': _r(p['poc'], d), 'vah': _r(p['vah'], d), 'val': _r(p['val'], d), 'hvn': [_r(x, d) for x in p['hvn']],
            'lvn': [_r(x, d) for x in p['lvn']], 'edges': [_r(x, d) for x in p['edges']],
            'volumes': [round(float(x)) for x in p['volumes']]}


def _zone_json(z, dates, d=4):
    out = {'dir': z['dir'], 'bottom': _r(z['bottom'], d), 'top': _r(z['top'], d), 'formed': _d(dates, z['t']),
           'status': z.get('status')}
    if 'base' in z:
        out['start'] = _d(dates, z['base'][0])
    elif 'bar' in z:
        out['start'] = _d(dates, z['bar'])
    else:
        out['start'] = _d(dates, z['t'] - 2)
    if z.get('k') is not None:
        out['end'] = _d(dates, z['k'])
    if 'filled' in z:
        out['filled'] = _d(dates, z['filled']) if z['filled'] is not None else None
    return out


def _nearest(items, price, key, k=3):
    return sorted(items, key=lambda z: abs(key(z) - price))[:k]


def _active_levels(X, raw):
    n = X['n']
    return [lv for lv in raw['levels']['levels'] if lv['touches'] >= 2 and n - 1 - lv['last'] <= LEVEL_LIFE]


def _ev_json(e, dates):
    return {'date': _d(dates, e['i']), 'rule': e['rule'], 'name': RULE.get(e['rule'], {}).get('name', e['rule']),
            'dir': e['dir'], 'family': RULE.get(e['rule'], {}).get('family'), 'info': e['info']}


def state(o, h, l, c, v, dates):
    """The current reading at the last bar, family by family (JSON-serializable). Keys: 'date', 'close', 'atr',
    'candlestick', 'brooks', 'structure', 'pattern', 'wyckoff', 'vsa', 'profile', 'levels', 'ict', 'elliott', 'quant',
    'recent' (the events of the last 10 bars)."""
    X, events, raw = _analyse(o, h, l, c, v)
    n = X['n']
    if n < 2:
        return {'date': _d(dates, n - 1), 'close': _r(X['c'][-1]) if n else None, 'recent': []}
    i, px = n - 1, float(X['c'][-1])
    A = float(X['A'][-1])
    dp = 2 if px >= 1 else 4
    R = lambda x: _r(x, dp)
    out = {'date': _d(dates, i), 'close': R(px), 'atr': R(A)}
    # candlestick: what fired on the last bar
    out['candlestick'] = {'last_bar': [{'rule': e['rule'], 'dir': e['dir']} for e in events
                                       if e['i'] == i and RULE.get(e['rule'], {}).get('family') == 'candlestick']}
    # Brooks
    B = raw['brooks']
    ai = B['ai']
    ch = np.nonzero(ai != ai[-1])[0]
    mm = B['mm']
    out['brooks'] = {'always_in': {1: 'long', -1: 'short'}.get(int(ai[-1])),
                     'since': _d(dates, int(ch[-1]) + 1) if len(ch) else _d(dates, 0),
                     'trend_or_range': 'trend' if bool(B['trend'][-1]) else 'trading range',
                     'efficiency_ratio': _r(B['er'][-1], 3), 'share_closes_above_ema20': _r(B['fa'][-1], 3),
                     'ema20': R(X['E'][-1]),
                     'measured_move': None if not mm else {'date': _d(dates, mm['i']), 'dir': mm['dir'], 'level': R(mm['level']),
                                                           'height': R(mm['height']), 'target': R(mm['target']),
                                                           'reached': mm['reached']}}
    # structure
    S = raw['structure']
    sw = S['swings'][-8:]
    lastk = lambda kind: next((b for b in reversed(S['breaks']) if b['kind'] == kind), None)
    bj = lambda b: None if not b else {'date': _d(dates, b['i']), 'dir': b['dir'], 'level': R(b['level']),
                                       'swing_date': _d(dates, b['swing'])}
    out['structure'] = {'trend': {1: 'up', -1: 'down'}.get(S['trend']),
                        'swings': [{'date': _d(dates, j), 'price': R(p), 'kind': k, 'label': lab or None,
                                    'confirmed': _d(dates, cf)} for j, p, k, lab, cf in sw],
                        'last_bos': bj(lastk('bos')), 'last_choch': bj(lastk('choch'))}
    # chart patterns waiting for their breakout
    def trigger(p):
        ln = lambda j1, p1, j2, p2: p1 + (p2 - p1) * (i - j1) / (j2 - j1)
        if 'level' in p:
            return {'close_' + ('above' if p['dir'] == 'bull' else 'below'): R(p['level'])}
        if 'line' in p:
            return {'close_' + ('above' if p['dir'] == 'bull' else 'below'): R(ln(*p['line']))}
        return {'close_above': R(ln(*p['up'])), 'close_below': R(ln(*p['dn']))}
    out['pattern'] = {'armed': [{'rule': p['rule'], 'dir': p['dir'], 'pivots': [_d(dates, j) for j in p['piv']],
                                 'trigger': trigger(p), 'until': _d(dates, p['until']) if p['until'] < n else None}
                                for p in raw['pattern']['pending'] if p['until'] >= i]}
    # Wyckoff
    W = raw['wyckoff']
    act = W['active']
    lastr = W['ranges'][-1] if W['ranges'] else None
    out['wyckoff'] = {'phase': W['phase'], 'since': _d(dates, W['since']) if W['since'] is not None else None,
                      'range': None if not lastr else {'low': R(lastr['lo']), 'high': R(lastr['hi']),
                                                       'start': _d(dates, lastr['start']), 'kind': lastr['kind'],
                                                       'active': act is lastr,
                                                       'end': _d(dates, lastr['end']) if 'end' in lastr else None,
                                                       'result': lastr.get('result')}}
    # VSA
    sp, vr, cp = X['sp'][-1], X['vr'][-1], X['cp'][-1]
    out['vsa'] = {'label': vsa_label(sp, vr, cp, X['c'][-1] >= X['c'][-2]), 'spread_ratio': _r(sp, 2),
                  'volume_ratio': _r(vr, 2), 'close_position': _r(cp, 2),
                  'events': [e['rule'] for e in events if e['i'] == i and RULE.get(e['rule'], {}).get('family') == 'vsa']}
    # volume profile
    out['profile'] = {}
    for N in (60, 250):
        s = max(0, n - N)
        p = volume_profile(X['h'][s:], X['l'][s:], X['v'][s:])
        pj = _profile_json(p, dp)
        if pj:
            pj['bars'] = n - s
            pj['position'] = 'above value' if px > p['vah'] else ('below value' if px < p['val'] else 'inside value')
        out['profile'][str(N)] = pj
    # levels and zones
    lv = _active_levels(X, raw)
    lj = lambda z: {'price': R(z['price']), 'touches': z['touches'], 'first': _d(dates, z['first']),
                    'last_swing': _d(dates, z['last']), 'last_test': _d(dates, _last_test(X, z['price'], z['first']))}
    zs = raw['levels']['zones']
    out['levels'] = {'support': [lj(z) for z in _nearest([z for z in lv if z['price'] < px], px, lambda z: z['price'])],
                     'resistance': [lj(z) for z in _nearest([z for z in lv if z['price'] >= px], px, lambda z: z['price'])],
                     'demand_zones': [_zone_json(z, dates, dp) for z in _nearest(
                         [z for z in zs if z['dir'] == 'bull' and z['status'] == 'active'], px, lambda z: (z['top'] + z['bottom']) / 2)],
                     'supply_zones': [_zone_json(z, dates, dp) for z in _nearest(
                         [z for z in zs if z['dir'] == 'bear' and z['status'] == 'active'], px, lambda z: (z['top'] + z['bottom']) / 2)]}
    # ICT
    mid = lambda z: (z['top'] + z['bottom']) / 2
    unf = [z for z in S['fvgs'] if z['filled'] is None and i - z['t'] <= 250]
    obs = [z for z in S['obs'] if z['status'] == 'active']
    lsh = next((s_ for s_ in reversed(S['swings']) if s_[2] == 'high'), None)
    lsl = next((s_ for s_ in reversed(S['swings']) if s_[2] == 'low'), None)
    pdz = None
    if lsh and lsl and lsh[1] > lsl[1]:
        m_ = (lsh[1] + lsl[1]) / 2
        pdz = {'range_high': R(lsh[1]), 'range_low': R(lsl[1]), 'high_date': _d(dates, lsh[0]), 'low_date': _d(dates, lsl[0]),
               'equilibrium': R(m_), 'zone': 'premium' if px > m_ else 'discount',
               'position': _r((px - lsl[1]) / (lsh[1] - lsl[1]), 3)}
    out['ict'] = {'premium_discount': pdz,
                  'fvgs': [_zone_json(z, dates, dp) for z in _nearest(unf, px, mid, 6)],
                  'order_blocks': [_zone_json(z, dates, dp) for z in _nearest(obs, px, mid, 6)],
                  'liquidity': {'buy_side': None if not S['sweep_h'] else {'price': R(S['sweep_h'][0]), 'date': _d(dates, S['sweep_h'][1])},
                                'sell_side': None if not S['sweep_l'] else {'price': R(S['sweep_l'][0]), 'date': _d(dates, S['sweep_l'][1])}}}
    # Elliott
    piv = raw['elliott']['pivots']
    cnt = elliott_count(piv)
    out['elliott'] = {'label': cnt['label'], 'direction': cnt['direction'],
                      'waves': [{'wave': w, 'date': _d(dates, piv[k][0]), 'price': R(piv[k][1])} for w, k in cnt['waves']],
                      'ratios': {k: _r(x, 3) for k, x in cnt['ratios'].items()},
                      'zigzag_atr': ZZ_K, 'pivots': [{'date': _d(dates, p[0]), 'price': R(p[1]), 'kind': 'high' if p[2] > 0 else 'low'}
                                                     for p in piv[-10:]]}
    # quant
    Q = raw['quant']
    hh = lambda N: float(X['h'][-N:].max())
    ll = lambda N: float(X['l'][-N:].min())
    out['quant'] = {'donchian20': {'upper': R(hh(20)), 'lower': R(ll(20))}, 'donchian55': {'upper': R(hh(55)), 'lower': R(ll(55))},
                    'mom_12_1': _r(Q['mom'][-1], 4), 'tsmom': None if not _fin(Q['mom'][-1]) else ('bull' if Q['mom'][-1] > 0 else 'bear'),
                    'hi52_ratio': _r(Q['hi52'][-1], 4), 'r21': _r(Q['r21'][-1], 4), 'r21_percentile': _r(Q['pct'][-1], 3)}
    out['recent'] = [_ev_json(e, dates) for e in events if e['i'] >= n - 10]
    return out


def overlays(o, h, l, c, v, dates, last=120):
    """What to draw on a candlestick chart of the last `last` bars (JSON-serializable): 'candles' [date, o, h, l, c, v],
    'swings', 'breaks' (BOS / CHoCH), 'levels', 'zones' (supply / demand bands), 'fvgs', 'order_blocks', 'donchian'
    (the 20- and 55-day channels of the bars BEFORE each date: a close beyond the line is a breakout), 'profile' (the
    60-bar POC / VAH / VAL), 'elliott' (pivots of the current count) and 'events' (date, rule, dir, price to pin it at)."""
    X, events, raw = _analyse(o, h, l, c, v)
    n = X['n']
    s = max(0, n - last)
    px = float(X['c'][-1]) if n else 0.0
    dp = 2 if px >= 1 else 4
    R = lambda x: _r(x, dp)
    out = {'start': _d(dates, s), 'end': _d(dates, n - 1),
           'candles': [[_d(dates, k), R(X['o'][k]), R(X['h'][k]), R(X['l'][k]), R(X['c'][k]), round(float(X['v'][k]))]
                       for k in range(s, n)]}
    if n < 2:
        return {**out, 'swings': [], 'breaks': [], 'levels': [], 'zones': [], 'fvgs': [], 'order_blocks': [],
                'donchian': {}, 'profile': None, 'elliott': [], 'events': []}
    S = raw['structure']
    out['swings'] = [{'date': _d(dates, j), 'price': R(p), 'kind': k, 'label': lab or None} for j, p, k, lab, _ in S['swings'] if j >= s]
    out['breaks'] = [{'date': _d(dates, b['i']), 'kind': b['kind'], 'dir': b['dir'], 'level': R(b['level']),
                      'from': _d(dates, b['swing'])} for b in S['breaks'] if b['i'] >= s]
    lo, hi = float(X['l'][s:].min()), float(X['h'][s:].max())
    pad = 0.1 * (hi - lo)
    out['levels'] = [{'price': R(z['price']), 'touches': z['touches'], 'kind': 'support' if z['price'] < px else 'resistance',
                      'first': _d(dates, z['first']), 'last_swing': _d(dates, z['last'])}
                     for z in _active_levels(X, raw) if lo - pad <= z['price'] <= hi + pad]
    vis = lambda z: z['status'] == 'active' or (z.get('k') is not None and z['k'] >= s)
    out['zones'] = [_zone_json(z, dates, dp) for z in raw['levels']['zones'] if vis(z) and z['t'] < n]
    out['fvgs'] = [_zone_json(z, dates, dp) for z in S['fvgs'] if z['t'] >= s or (z['filled'] is None and n - 1 - z['t'] <= 250)]
    out['order_blocks'] = [_zone_json(z, dates, dp) for z in S['obs'] if vis(z)]
    don = {'dates': [_d(dates, k) for k in range(s, n)]}
    for N in (20, 55):
        up, dn = _sh(_roll(X['h'], N, 'max')), _sh(_roll(X['l'], N, 'min'))
        don[f'upper{N}'] = [R(x) for x in up[s:]]
        don[f'lower{N}'] = [R(x) for x in dn[s:]]
    out['donchian'] = don
    p = volume_profile(X['h'][max(0, n - 60):], X['l'][max(0, n - 60):], X['v'][max(0, n - 60):])
    out['profile'] = None if not p else {'poc': R(p['poc']), 'vah': R(p['vah']), 'val': R(p['val'])}
    piv = raw['elliott']['pivots']
    cnt = elliott_count(piv)
    out['elliott'] = [{'wave': w, 'date': _d(dates, piv[k][0]), 'price': R(piv[k][1])} for w, k in cnt['waves']]
    out['events'] = [{'date': _d(dates, e['i']), 'rule': e['rule'], 'dir': e['dir'],
                      'price': R(X['l'][e['i']] if e['dir'] == 'bull' else X['h'][e['i']])} for e in events if e['i'] >= s]
    return out


# ------------------------------------------------------------------ pooled walk-forward backtest
def forward_returns(ac, horizons=HORIZONS):
    """h → array of log(ac[i + h] / ac[i]); NaN where i + h is past the end or a price is missing or not positive."""
    ac = _f(ac)
    with np.errstate(invalid='ignore', divide='ignore'):
        lg = np.log(np.where(ac > 0, ac, np.nan))
    out = {}
    for h in horizons:
        r = np.full(len(ac), np.nan)
        if 0 < h < len(ac):
            r[:-h] = lg[h:] - lg[:-h]
        out[h] = r
    return out


def month_id(date):
    return int(date[:4]) * 12 + int(date[5:7]) - 1


def clustered_t(x, groups):
    """Mean of x, its standard error clustered by group, t = mean / SE (see the module docstring). None when there are
    fewer than MIN_EVENTS values or 2 groups."""
    x = np.asarray(x, float)
    N = len(x)
    if N < MIN_EVENTS:
        return None, None
    m = float(x.mean())
    _, inv = np.unique(groups, return_inverse=True)
    G = int(inv.max()) + 1
    if G < 2:
        return m, None
    Sg = np.bincount(inv, weights=x - m, minlength=G)
    se = math.sqrt(G / (G - 1) * float((Sg ** 2).sum())) / N
    return m, (m / se if se > 0 else None)


def p_two_sided(t):
    return None if t is None or not math.isfinite(t) else 2.0 * (1.0 - normal_cdf(abs(t)))


def benjamini_hochberg(pvals, q=BH_Q):
    """{key: True / False} for {key: p}: True for the k smallest p-values, k the largest rank with p(k) ≤ k / m × q."""
    items = sorted(((p, k) for k, p in pvals.items() if p is not None), key=lambda z: z[0])
    m = len(items)
    kmax = 0
    for r, (p, _) in enumerate(items, 1):
        if p <= r / m * q:
            kmax = r
    sig = {k: False for k in pvals}
    for r, (p, k) in enumerate(items, 1):
        sig[k] = r <= kmax
    return sig


class Pool:
    """Events of many tickers with their forward returns, for the pooled test. Per event it keeps the month, the rule,
    the ticker, the sign of its direction and the h-day forward log return; per ticker and month it keeps the count, sum
    and number of positive forward returns of all bars, so each ticker's mean over any period (and the excess of each
    event over it) is exact for a split at a calendar-month boundary."""

    def __init__(self, horizons=HORIZONS):
        self.horizons = tuple(horizons)
        self.tickers = []
        self.rules = []
        self._rule_ix = {}
        self._ev = {'rule': [], 'tk': [], 'month': [], 'sign': [], 'fwd': []}
        self._tm = []                         # per ticker: (months, count (m, H), sum (m, H), positive (m, H))
        self.n_dropped = 0

    def add(self, ticker, dates, ac, events):
        """events: dicts {'rule', 'i', 'dir'} or tuples (rule, i, dir), as detect() returns them."""
        H = self.horizons
        fr = forward_returns(ac, H)
        F = np.stack([fr[h] for h in H], axis=1)                  # (n, H)
        mo = np.array([month_id(d) for d in dates], dtype=np.int32)
        um, inv = np.unique(mo, return_inverse=True)
        ok = np.isfinite(F)
        cnt = np.zeros((len(um), len(H)))
        sm = np.zeros((len(um), len(H)))
        pos = np.zeros((len(um), len(H)))
        for k in range(len(H)):
            cnt[:, k] = np.bincount(inv, weights=ok[:, k].astype(float), minlength=len(um))
            sm[:, k] = np.bincount(inv, weights=np.where(ok[:, k], F[:, k], 0.0), minlength=len(um))
            pos[:, k] = np.bincount(inv, weights=(ok[:, k] & (F[:, k] > 0)).astype(float), minlength=len(um))
        t = len(self.tickers)
        self.tickers.append(ticker)
        self._tm.append((um, cnt, sm, pos))
        n = len(dates)
        rows = []
        for e in events:
            rule, i, d = (e['rule'], e['i'], e['dir']) if isinstance(e, dict) else (e[0], e[1], e[2])
            if not (0 <= i < n) or d not in ('bull', 'bear'):
                self.n_dropped += 1
                continue
            if rule not in self._rule_ix:
                self._rule_ix[rule] = len(self.rules)
                self.rules.append(rule)
            rows.append((self._rule_ix[rule], i, 1 if d == 'bull' else -1))
        if rows:
            R_ = np.array(rows, dtype=np.int64)
            self._ev['rule'].append(R_[:, 0].astype(np.int16))
            self._ev['tk'].append(np.full(len(R_), t, np.int32))
            self._ev['month'].append(mo[R_[:, 1]])
            self._ev['sign'].append(R_[:, 2].astype(np.int8))
            self._ev['fwd'].append(F[R_[:, 1]].astype(np.float32))

    def _cat(self):
        e = self._ev
        if not e['rule']:
            return None
        return (np.concatenate(e['rule']), np.concatenate(e['tk']), np.concatenate(e['month']),
                np.concatenate(e['sign']).astype(float), np.concatenate(e['fwd']).astype(float))

    def _ticker_means(self, split_m):
        """(T, 2, H) mean forward return of each ticker in-sample (0) and out-of-sample (1)."""
        T, Hn = len(self.tickers), len(self.horizons)
        M = np.full((T, 2, Hn), np.nan)
        for t, (um, cnt, sm, _) in enumerate(self._tm):
            for per, mk in ((0, um < split_m), (1, um >= split_m)):
                c_, s_ = cnt[mk].sum(axis=0), sm[mk].sum(axis=0)
                M[t, per] = np.where(c_ > 0, s_ / np.where(c_ > 0, c_, 1), np.nan)
        return M

    def baseline_hit(self, split=SPLIT):
        """Share of ALL bars (every ticker, every day) with a positive h-day forward return, in- and out-of-sample: the
        hit rate a coin-flip 'bull' rule would score on raw returns."""
        sm_ = month_id(split)
        out = {}
        for k, h in enumerate(self.horizons):
            r = {}
            for per, name in ((0, 'is'), (1, 'oos')):
                c_ = p_ = 0.0
                for um, cnt, _, pos in self._tm:
                    mk = (um < sm_) if per == 0 else (um >= sm_)
                    c_ += cnt[mk, k].sum()
                    p_ += pos[mk, k].sum()
                r[name] = _r(p_ / c_, 4) if c_ else None
                r[f'n_{name}'] = int(c_)
            out[h] = r
        return out

    def result(self, split=SPLIT, horizons=None):
        """rule id → {'name', 'family', 'dir', 'n_is', 'n_oos', 'n_events_total', 'n_bull', 'n_bear', 'horizons': {h: {'is':
        {...}, 'oos': {...}}}, 'evidence': {h: grade}, 'evidence_sign': {h: +1 / −1 / 0}}. Each period block holds
        'n', 'months', 'mean' (signed excess log return), 'hit' (share > 0), 't' (month-clustered), 'p'."""
        H = tuple(horizons or self.horizons)
        hk = [self.horizons.index(h) for h in H]
        split_m = month_id(split)
        out = {}
        E = self._cat()
        if E is None:
            return out
        rule, tk, mo, sign, fwd = E
        M = self._ticker_means(split_m)
        per = (mo >= split_m).astype(int)
        res = {}
        for ri, rid in enumerate(self.rules):
            sel = rule == ri
            info = RULE.get(rid, {})
            r = {'name': info.get('name', rid), 'family': info.get('family'), 'dir': info.get('dir'),
                 'n_events_total': int(sel.sum()), 'n_bull': int((sel & (sign > 0)).sum()), 'n_bear': int((sel & (sign < 0)).sum()),
                 'n_is': int((sel & (per == 0)).sum()), 'n_oos': int((sel & (per == 1)).sum()), 'horizons': {}}
            for h, k in zip(H, hk):
                blk = {}
                for p_, name in ((0, 'is'), (1, 'oos')):
                    m_ = sel & (per == p_)
                    x = (fwd[m_, k] - M[tk[m_], p_, k]) * sign[m_]
                    g = mo[m_]
                    ok = np.isfinite(x)
                    x, g = x[ok], g[ok]
                    mean, t = clustered_t(x, g)
                    blk[name] = {'n': int(len(x)), 'months': int(len(np.unique(g))), 'mean': _r(mean, 5),
                                 'hit': _r(float((x > 0).mean()), 4) if len(x) else None, 't': _r(t, 3),
                                 'p': _r(p_two_sided(t), 6)}
                r['horizons'][h] = blk
            res[rid] = r
        for h in H:
            sig = benjamini_hochberg({rid: res[rid]['horizons'][h]['oos']['p'] for rid in res})
            for rid, r in res.items():
                b = r['horizons'][h]
                po, pi = b['oos']['p'], b['is']['p']
                mo_, mi = b['oos']['mean'], b['is']['mean']
                agree = mo_ is not None and mi is not None and mo_ * mi > 0
                if sig[rid] and agree:
                    g = 'strong'
                elif po is not None and po < 0.05:
                    g = 'moderate'
                elif pi is not None and pi < 0.05:
                    g = 'weak'
                else:
                    g = 'none'
                r.setdefault('evidence', {})[h] = g
                ref = mo_ if g in ('strong', 'moderate') else (mi if g == 'weak' else None)
                r.setdefault('evidence_sign', {})[h] = 0 if not ref else (1 if ref > 0 else -1)
                r.setdefault('bh_significant', {})[h] = bool(sig[rid])
        return res


def baseline_hit(pool, split=SPLIT):
    """The unconditional share of positive h-day forward returns in a Pool, in- and out-of-sample (see Pool.baseline_hit)."""
    return pool.baseline_hit(split)
