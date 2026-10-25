"""Price paths: seven ways to simulate where a stock, its market, its sector and its peers could go over the next few
months, for the Price paths view of a company page, and the walk-forward scoring that compares them honestly.

Input (every function): R, a (T, N) array of daily log returns r_t = ln(P_t / P_{t-1}) from dividend- and split-adjusted
closes, oldest first, every column on the same dates. Column 0 is the target stock, column 1 the market (SPY), column 2
(when there is one) the sector ETF, further columns peer stocks. Typically T = 756 (three years) and N = 2-8.

Output of simulate(): paths, an (n, horizon, N) array of cumulative log returns from today's close to each future trading
day, paths[i, k, j] = r*_{0,j} + ... + r*_{k,j} for simulated path i. A price is price0 * exp(paths[i, k, j]).

The models (MODELS), from the most data-driven to the most parametric, and when each one is the right lens:

  joint_bootstrap  Joint (row-wise i.i.d.) bootstrap. Every simulated day is one whole historical day picked at random
                   with replacement, the same date for every asset: r*_t = R[u_t], u_t ~ Uniform{0..T-1}. Keeps the real
                   cross-asset correlation and the fat tails exactly; forgets the order of days. Use as the default when
                   the last three years are a fair sample of what can happen and today is not unusually calm or wild.
  block_bootstrap  Stationary block bootstrap (Politis & Romano 1994). Whole rows again, but in runs of consecutive
                   days: each day starts a new run at a random date with probability p = 1/block, otherwise it takes the
                   day after the previous one (wrapping from the last day to the first); run lengths are geometric with
                   mean `block`. Keeps volatility clustering and short-term momentum too. Use when calm and stormy
                   stretches come in runs (they nearly always do) and you want the simulated paths to have them.
  fhs              Filtered historical simulation (Barone-Adesi, Giannopoulos & Vosper 1999). A GARCH(1,1) per column
                   (garch_fit) turns returns into standardized shocks z_t = (r_t - mu) / sigma_t; the future replays
                   whole rows of z (same date for every asset) through each column's GARCH recursion, started from
                   today's fitted variance: r = mu + sigma z, sigma^2_{t+1} = omega + alpha (r_t - mu)^2 + beta sigma^2_t.
                   Use when today's volatility is clearly above or below its three-year average: the fan starts from
                   today's level and drifts back.
  factor           Linear factor model with bootstrapped residuals. Every non-factor column is regressed on the factor
                   columns (market and sector by default) by OLS, r_j = a_j + sum_k b_jk f_k + e_j; the factors are
                   simulated by a joint bootstrap of their rows and each residual by its own independent bootstrap.
                   Stocks are correlated only through the factors. Use to read the stock as "market and sector beta plus
                   its own story", or when peer correlations are too noisy to trust.
  cholesky         Correlated Gaussian random walk. Daily returns ~ N(mean vector, covariance) of the sample, drawn as
                   mu + L e with L the Cholesky factor (S = L L^T) and e ~ N(0, I). The textbook benchmark (geometric
                   Brownian motion); its thin tails understate crashes, which is exactly what it is here to show.
  t_copula         Student-t copula with empirical marginals. Each asset keeps its own historical distribution (sampled
                   through its empirical quantile function), and the assets are tied together by a t copula whose
                   correlation comes from Kendall's tau, rho = sin(pi tau / 2), and whose degrees of freedom nu are
                   fitted by maximum pseudo-likelihood. Small nu = assets crash together more often than their average
                   correlation suggests (tail dependence). Use for joint-crash questions.
  dcc_garch        DCC-GARCH: GARCH(1,1) volatilities plus Engle's (2002) dynamic conditional correlation,
                   Q_t = (1-a-b) Qbar + a z_{t-1} z_{t-1}^T + b Q_{t-1}, R_t = diag(Q_t)^{-1/2} Q_t diag(Q_t)^{-1/2},
                   simulated forward from today's Q and variances with normal shocks e ~ N(0, R_t). Use when both
                   volatility and correlation are moving now (in a sell-off correlations rise) and you want both to
                   start from today's values and decay back to normal.

Baseline (naive_normal): i.i.d. normal daily returns with the target's own mean and standard deviation, univariate.
Every model is scored against it with the same walk-forward evaluate().

No scipy: the Student-t CDF uses the closed-form series for integer nu (Abramowitz & Stegun 26.7.3-4) or the regularized
incomplete beta by continued fraction (modified Lentz), F(x) = 1 - I_{nu/(nu+x^2)}(nu/2, 1/2) / 2 for x > 0, and a
two-term expansion in 1/nu for nu >= 1000; its inverse is a safeguarded Newton iteration on the log tail; the normal CDF
is math.erfc element by element. All randomness comes
from numpy's default_rng(seed) (PCG64): the same seed gives the same paths on every machine with the same numpy.
"""
import math
import time

import numpy as np

MODELS = ['joint_bootstrap', 'block_bootstrap', 'fhs', 'factor', 'cholesky', 't_copula', 'dcc_garch']
MODEL_INFO = {
    'joint_bootstrap': {'name': 'Joint bootstrap',
                        'short': 'Replays random whole past days for every asset at once: real correlations and fat tails, no memory.'},
    'block_bootstrap': {'name': 'Stationary block bootstrap',
                        'short': 'Replays runs of consecutive past days (10 on average), so calm and stormy stretches stay together.'},
    'fhs': {'name': 'Filtered historical simulation',
            'short': "Past shocks rescaled to today's GARCH volatility, which then evolves day by day."},
    'factor': {'name': 'Market + sector factor model',
               'short': 'Each stock = alpha + betas x the simulated market and sector + its own resampled noise.'},
    'cholesky': {'name': 'Correlated normal (Cholesky)',
                 'short': 'Textbook correlated random walk with the sample mean and covariance; thin tails.'},
    't_copula': {'name': 'Student-t copula',
                 'short': "Each asset's own return distribution, joined by a t copula so crashes come together."},
    'dcc_garch': {'name': 'DCC-GARCH',
                  'short': "Volatility and correlation both start from today's levels and drift back to normal."},
}
BASELINE_INFO = {'naive_normal': {'name': 'Naive normal',
                                  'short': "I.i.d. normal days with the stock's own mean and volatility, no other asset."}}

TRADING_DAYS = 252
LOG2PI = math.log(2 * math.pi)
VAR_FLOOR = 1e-16                     # a daily variance below this (sigma 1e-8 a day) is a constant series
NU_GRID = (3, 4, 5, 6, 8, 10, 15, 20, 30, 50)
EVAL_TAUS = np.round(np.arange(1, 20) * 0.05, 2)     # 0.05, 0.10, ..., 0.95 for the pinball loss


def _grid(xs, ys, cap):
    """All (x, y) pairs of two grids with x + y < cap, as two flat arrays."""
    X, Y = np.meshgrid(np.asarray(xs, float), np.asarray(ys, float), indexing='ij')
    keep = X + Y < cap
    return X[keep], Y[keep]


GARCH_A, GARCH_B = _grid(np.round(np.arange(30) * 0.01 + 0.01, 4), np.round(np.arange(25) * 0.02 + 0.50, 4), 0.999)
DCC_A_GRID = (0.005, 0.01, 0.015, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20)
DCC_B_GRID = (0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.94, 0.95, 0.96, 0.97, 0.98, 0.99)


# ------------------------------------------------------------------ small helpers
def _prep(R):
    """R as a float (T, N) array, a 1-D series as one column, non-finite entries set to 0 (a flat day)."""
    R = np.asarray(R, dtype=float)
    if R.ndim == 1:
        R = R[:, None]
    if R.ndim != 2 or R.shape[0] < 2 or R.shape[1] < 1:
        raise ValueError('R must be a (T, N) array with T >= 2 and N >= 1')
    return np.where(np.isfinite(R), R, 0.0)


def _ret(a):
    """A 0-d result as a Python float, anything else as the array."""
    return float(a) if np.ndim(a) == 0 else a


def _sig(v, d=4):
    """v rounded to d significant digits as a plain float (None if not finite): float(f'{v:.{d}g}')."""
    v = float(v)
    return float(f'{v:.{d}g}') if math.isfinite(v) else None


def _p(mask):
    """Share of True in a boolean array, rounded to 4 decimals."""
    return round(float(np.mean(mask)), 4) if np.size(mask) else None


def _corr(x, y):
    """Pearson correlation sum((x-xbar)(y-ybar)) / sqrt(sum (x-xbar)^2 sum (y-ybar)^2); None for < 3 points or no spread."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3:
        return None
    dx, dy = x - x.mean(), y - y.mean()
    den = math.sqrt(float(dx @ dx) * float(dy @ dy))
    return round(float(dx @ dy) / den, 4) if den > 1e-300 else None


def _cum(daily):
    """Cumulative log returns along the day axis: paths[:, k] = daily[:, 0] + ... + daily[:, k]."""
    return np.cumsum(daily, axis=1)


def _chol_jitter(S):
    """Lower Cholesky factor L of a covariance S = L L^T. If S is not positive definite (a constant column, collinear
    columns), add a diagonal jitter eps * I with eps = 1e-12 * mean(diag S), x100 each retry; last resort the
    eigenvalue square root V sqrt(max(lambda, 0)) (not triangular, but V D V^T = S as well)."""
    S = np.atleast_2d(np.asarray(S, float))
    S = (S + S.T) / 2
    scale = max(float(np.mean(np.diag(S))), 1e-300)
    eps = 0.0
    for _ in range(8):
        try:
            return np.linalg.cholesky(S + eps * np.eye(len(S)))
        except np.linalg.LinAlgError:
            eps = scale * 1e-12 if eps == 0.0 else eps * 100
    w, V = np.linalg.eigh(S)
    return V * np.sqrt(np.maximum(w, 0.0))


def _nearest_corr(C, floor=1e-6):
    """A positive-definite correlation matrix near C: symmetrize, then (up to 50 times) clip the eigenvalues at `floor`,
    C = V max(Lambda, floor) V^T, and rescale to a unit diagonal, C_ij / sqrt(C_ii C_jj), until the smallest eigenvalue
    is above floor / 10. A matrix that is already positive definite comes back unchanged."""
    C = np.atleast_2d(np.array(C, dtype=float))
    C = np.where(np.isfinite(C), C, 0.0)
    C = (C + C.T) / 2
    np.fill_diagonal(C, 1.0)
    for _ in range(50):
        w, V = np.linalg.eigh(C)
        if w[0] > floor / 10:
            break
        C = (V * np.maximum(w, floor)) @ V.T
        d = np.sqrt(np.diag(C))
        C = C / np.outer(d, d)
        C = (C + C.T) / 2
        np.fill_diagonal(C, 1.0)
    return C


def _chol_lower(A):
    """Batched Cholesky for many small matrices stored batch-last, A of shape (N, N, B): returns L as a list of lists
    with L[i][j] a (B,) array, A = L L^T, L_jj = sqrt(A_jj - sum_k<j L_jk^2), L_ij = (A_ij - sum_k<j L_ik L_jk) / L_jj.
    Pivots are floored at 1e-12 A_jj so a nearly singular matrix never gives NaN. Element-wise, so fast for N <= 10."""
    N = A.shape[0]
    L = [[None] * N for _ in range(N)]
    for j in range(N):
        s = A[j, j].copy()
        for k in range(j):
            s -= L[j][k] * L[j][k]
        s = np.maximum(s, 1e-12 * np.abs(A[j, j]) + 1e-300)
        d = np.sqrt(s)
        L[j][j] = d
        for i in range(j + 1, N):
            v = A[i, j].copy()
            for k in range(j):
                v -= L[i][k] * L[j][k]
            L[i][j] = v / d
    return L


def _logdet_quad(A, w):
    """For batch-last matrices A (N, N, B) and vectors w (N, B): log|A| = 2 sum_j log L_jj and the quadratic form
    w^T A^{-1} w = |y|^2 with L y = w solved by forward substitution, y_j = (w_j - sum_k<j L_jk y_k) / L_jj."""
    L = _chol_lower(A)
    N = A.shape[0]
    logdet = np.zeros(A.shape[2])
    quad = np.zeros(A.shape[2])
    y = [None] * N
    for j in range(N):
        r = w[j].copy()
        for k in range(j):
            r -= L[j][k] * y[k]
        y[j] = r / L[j][j]
        quad += y[j] * y[j]
        logdet += 2 * np.log(L[j][j])
    return logdet, quad


# ------------------------------------------------------------------ normal and Student-t distributions (no scipy)
_erfc = np.frompyfunc(math.erfc, 1, 1)
_ACK_A = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02,
          -3.066479806614716e+01, 2.506628277459239e+00)
_ACK_B = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01,
          -1.328068155288572e+01)
_ACK_C = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00,
          4.374664141464968e+00, 2.938163982698783e+00)
_ACK_D = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00)


def norm_cdf(x):
    """Standard normal CDF, Phi(x) = erfc(-x / sqrt 2) / 2, with math.erfc element by element (full double precision,
    accurate relative to the value deep in the lower tail)."""
    x = np.asarray(x, dtype=float)
    return _ret(np.asarray(0.5 * _erfc(-x / math.sqrt(2.0)), dtype=float))


def norm_ppf(p):
    """Standard normal quantile Phi^{-1}(p): Acklam's rational approximation (relative error 1.2e-9) polished by one
    Halley step on Phi(x) = p, x <- x - u / (1 + x u / 2), u = (Phi(x) - p) sqrt(2 pi) exp(x^2 / 2); computed on the
    smaller tail q = min(p, 1-p) and mirrored. p = 0 or 1 give -inf / +inf, p outside [0, 1] NaN."""
    p0 = np.asarray(p, dtype=float)
    p = p0.ravel()
    q = np.clip(np.minimum(p, 1 - p), 1e-300, 0.5)
    q = np.where(np.isnan(q), 0.5, q)
    x = np.empty_like(q)
    with np.errstate(all='ignore'):
        lo = q < 0.02425
        t = np.sqrt(-2 * np.log(q[lo]))
        c, d = _ACK_C, _ACK_D
        x[lo] = (((((c[0] * t + c[1]) * t + c[2]) * t + c[3]) * t + c[4]) * t + c[5]) / \
                ((((d[0] * t + d[1]) * t + d[2]) * t + d[3]) * t + 1)
        r0 = q[~lo] - 0.5
        r = r0 * r0
        a, b = _ACK_A, _ACK_B
        x[~lo] = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * r0 / \
                 (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
        e = np.asarray(norm_cdf(x), dtype=float) - q
        u = e * math.sqrt(2 * math.pi) * np.exp(0.5 * x * x)
        xr = x - u / (1 + 0.5 * x * u)
        x = np.where(np.isfinite(xr), xr, x)
    out = np.where(p < 0.5, x, -x)
    out = np.where(p == 0, -np.inf, np.where(p == 1, np.inf, out))
    out = np.where((p < 0) | (p > 1) | np.isnan(p), np.nan, out)
    return _ret(out.reshape(p0.shape))


def _betacf(a, b, x, eps=1e-15, max_iter=5000):
    """Continued fraction of the regularized incomplete beta (modified Lentz, as in Numerical Recipes' betacf):
    I_x(a, b) = x^a (1-x)^b / (a B(a, b)) * 1/(1+ d1/(1+ d2/(1+ ...))), with
    d_{2m} = m (b-m) x / ((a+2m-1)(a+2m)) and d_{2m+1} = -(a+m)(a+b+m) x / ((a+2m)(a+2m+1)).
    Converges quickly for x < (a+1)/(a+b+2); a, b scalars, x an array."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = np.ones_like(x)
    d = 1.0 - qab * x / qap
    d = 1.0 / np.where(np.abs(d) < tiny, tiny, d)
    h = d.copy()
    for m in range(1, max_iter + 1):
        m2 = 2.0 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / np.where(np.abs(d) < tiny, tiny, d)
        c = 1.0 + aa / c
        c = np.where(np.abs(c) < tiny, tiny, c)
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / np.where(np.abs(d) < tiny, tiny, d)
        c = 1.0 + aa / c
        c = np.where(np.abs(c) < tiny, tiny, c)
        de = d * c
        h *= de
        if not np.any(np.abs(de - 1.0) >= eps):
            break
    return h


def betainc(a, b, x, y=None):
    """Regularized incomplete beta I_x(a, b) = B(x; a, b) / B(a, b) for an array x in [0, 1]; y = 1 - x may be passed
    separately to keep precision when x is close to 1. Uses the continued fraction directly when
    x < (a+1)/(a+b+2) and the symmetry I_x(a, b) = 1 - I_{1-x}(b, a) otherwise."""
    x = np.asarray(x, dtype=float)
    y = 1.0 - x if y is None else np.asarray(y, dtype=float)
    out = np.empty_like(x)
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    flip = x > (a + 1.0) / (a + b + 2.0)
    with np.errstate(divide='ignore', invalid='ignore'):
        for sel, aa, bb, xx, yy, flipped in ((~flip, a, b, x, y, False), (flip, b, a, y, x, True)):
            if not sel.any():
                continue
            xs, ys = xx[sel], yy[sel]
            front = np.exp(aa * np.log(xs) + bb * np.log(ys) - lbeta) / aa
            I = front * _betacf(aa, bb, xs)
            out[sel] = 1.0 - I if flipped else I
    return out


def _t_sf_series(y, m):
    """Upper tail P(T > y), y >= 0, for an integer nu = m (A&S 26.7.3-4). With theta = atan(y / sqrt m),
    c^2 = m / (m + y^2), s = y / sqrt(m + y^2), the CDF is 1/2 + A/2 where
    even m: A = s (1 + 1/2 c^2 + 1*3/(2*4) c^4 + ... + 1*3*...*(m-3)/(2*4*...*(m-2)) c^(m-2)),
    odd m:  A = (2/pi) (theta + s c (1 + 2/3 c^2 + ... + 2*4*...*(m-3)/(3*5*...*(m-2)) c^(m-3))), A = 2 theta / pi for m = 1.
    Exact up to rounding (absolute error ~1e-16)."""
    den = m + y * y
    c2 = m / den
    s = y / np.sqrt(den)
    if m % 2 == 0:
        term = np.ones_like(y)
        tot = term.copy()
        for k in range(1, m // 2):
            term = term * c2 * ((2 * k - 1) / (2 * k))
            tot += term
        A = s * tot
    else:
        th = np.arctan(y / math.sqrt(m))
        if m == 1:
            A = th * (2 / math.pi)
        else:
            term = np.ones_like(y)
            tot = term.copy()
            for k in range(1, (m - 1) // 2):
                term = term * c2 * ((2 * k) / (2 * k + 1))
                tot += term
            A = (2 / math.pi) * (th + s * np.sqrt(c2) * tot)
    return 0.5 - 0.5 * A


def _t_sf(y, nu):
    """Upper tail P(T_nu > y) for y >= 0, accurate relative to its value in the far tail.
    integer nu <= 100: the closed-form series (absolute error ~1e-16), switched to the continued fraction where the
    tail is < 1e-3 so the relative error stays ~1e-13;
    other nu < 1000: (1/2) I_{nu/(nu+y^2)}(nu/2, 1/2) by continued fraction (under ~100 terms);
    nu >= 1000: the expansion in 1/nu, Phi(-y) + phi(y) [(y^3 + y) / (4 nu) + (3y^7 - 7y^5 - 5y^3 - 3y) / (96 nu^2)]
    (absolute error < 1e-9, where the continued fraction would need thousands of terms); nu = inf: Phi(-y)."""
    y = np.minimum(np.asarray(y, dtype=float), 1e150)
    if math.isinf(nu):
        return np.asarray(norm_cdf(-y), dtype=float)
    if nu >= 1000:
        yc = np.minimum(y, 40.0)                       # phi(40) = 0: avoids inf * 0 in the polynomial
        phi = np.exp(-0.5 * yc * yc) / math.sqrt(2 * math.pi)
        y2 = yc * yc
        corr = (y2 + 1) * yc / (4 * nu) + (((3 * y2 - 7) * y2 - 5) * y2 - 3) * yc / (96 * nu * nu)
        return np.maximum(np.asarray(norm_cdf(-y), dtype=float) + phi * corr, 0.0)
    if nu == round(nu) and nu <= 100:
        s = _t_sf_series(y, int(round(nu)))
        small = s < 1e-3
        if small.any():
            ys = y[small]
            den = nu + ys * ys
            s[small] = 0.5 * betainc(nu / 2, 0.5, nu / den, ys * ys / den)
        return s
    den = nu + y * y
    return 0.5 * betainc(nu / 2, 0.5, nu / den, y * y / den)


def _t_logc(nu):
    """log of the Student-t density's constant, log Gamma((nu+1)/2) - log Gamma(nu/2) - log(nu pi) / 2."""
    return math.lgamma((nu + 1) / 2) - math.lgamma(nu / 2) - 0.5 * math.log(nu * math.pi)


def t_pdf(x, nu):
    """Student-t density f(x) = Gamma((nu+1)/2) / (sqrt(nu pi) Gamma(nu/2)) (1 + x^2/nu)^(-(nu+1)/2); nu = inf: normal."""
    x = np.asarray(x, dtype=float)
    nu = float(nu)
    if math.isinf(nu):
        return _ret(np.exp(-0.5 * x * x) / math.sqrt(2 * math.pi))
    return _ret(np.exp(_t_logc(nu) - (nu + 1) / 2 * np.log1p(x * x / nu)))


def t_cdf(x, nu):
    """Student-t CDF F_nu(x) (nu > 0, may be inf): F = P(T > -x) for x < 0 and 1 - P(T > x) for x >= 0, the tail from
    _t_sf (closed-form series for integer nu, incomplete beta otherwise: F(x) = 1 - I_{nu/(nu+x^2)}(nu/2, 1/2) / 2).
    Accurate to ~1e-15 absolute, and relative to the value in the lower tail. NaN in, NaN out."""
    nu = float(nu)
    if not nu > 0:
        raise ValueError('nu must be > 0')
    x0 = np.asarray(x, dtype=float)
    x = x0.ravel()
    out = np.full(x.shape, np.nan)
    ok = ~np.isnan(x)
    xs = x[ok]
    s = _t_sf(np.abs(xs), nu)
    out[ok] = np.where(xs < 0, s, 1.0 - s)
    return _ret(out.reshape(x0.shape))


def t_ppf(p, nu):
    """Student-t quantile F_nu^{-1}(p). nu = 1: tan(pi (p - 1/2)); nu = 2: (2p-1) / sqrt(2p(1-p)); nu = inf: Phi^{-1}(p).
    Otherwise solve P(T > y) = q, q = min(p, 1-p), by Newton on the log tail, y <- y + (log S(y) - log q) S(y) / f(y),
    from Fisher's expansion y0 = z + g1/nu + g2/nu^2 + g3/nu^3 + g4/nu^4 (z = Phi^{-1}(1-q), A&S 26.7.5), kept inside
    the bracket [z, (K/q)^(1/nu)] (the t quantile is beyond the normal one; S(y) <= K y^-nu with
    K = Gamma((nu+1)/2) nu^((nu-1)/2) / (sqrt(nu pi) Gamma(nu/2))) and bisected whenever Newton would leave it.
    Converges to ~1e-13 relative in a handful of steps; the sign is restored at the end."""
    nu = float(nu)
    if not nu > 0:
        raise ValueError('nu must be > 0')
    p0 = np.asarray(p, dtype=float)
    if math.isinf(nu):
        return norm_ppf(p0)
    p = p0.ravel()
    out = np.full(p.shape, np.nan)
    ok = (p > 0) & (p < 1)
    q = np.minimum(p[ok], 1.0 - p[ok])
    with np.errstate(divide='ignore', invalid='ignore', over='ignore'):
        if nu == 1:
            y = 1.0 / np.tan(np.pi * q)
        elif nu == 2:
            y = (1 - 2 * q) / np.sqrt(2 * q * (1 - q))
        else:
            y = _t_isf(q, nu)
    out[ok] = np.where(p[ok] < 0.5, -y, y)
    out[p == 0] = -np.inf
    out[p == 1] = np.inf
    return _ret(out.reshape(p0.shape))


def _t_isf(q, nu, max_iter=100):
    """The y >= 0 with P(T_nu > y) = q for q in (0, 1/2] (see t_ppf for the method)."""
    q = np.asarray(q, dtype=float)
    y = np.zeros_like(q)
    act = q < 0.5
    if not act.any():
        return y
    qa = q[act]
    z = -np.asarray(norm_ppf(qa), dtype=float)
    z2 = z * z
    g1 = (z2 + 1) * z / 4
    g2 = ((5 * z2 + 16) * z2 + 3) * z / 96
    g3 = (((3 * z2 + 19) * z2 + 17) * z2 - 15) * z / 384
    g4 = ((((79 * z2 + 776) * z2 + 1482) * z2 - 1920) * z2 - 945) * z / 92160
    ya = z + g1 / nu + g2 / nu ** 2 + g3 / nu ** 3 + g4 / nu ** 4
    logK = _t_logc(nu) + (nu - 1) / 2 * math.log(nu)
    lo = z.copy()
    hi = np.maximum(np.exp(np.minimum((logK - np.log(qa)) / nu, math.log(1e150))), z) * (1 + 1e-12) + 1e-300
    ya = np.clip(ya, lo, hi)
    logq = np.log(qa)
    lc = _t_logc(nu)
    for _ in range(max_iter):
        S = _t_sf(ya, nu)
        f = np.exp(lc - (nu + 1) / 2 * np.log1p(ya * ya / nu))
        above = S > qa                               # tail still too big: the root is further out
        lo = np.where(above, ya, lo)
        hi = np.where(above, hi, ya)
        step = (np.log(S) - logq) * S / f
        new = ya + step
        tiny = (np.abs(step) <= 1e-13 * np.maximum(1.0, ya)) | (hi - lo <= 1e-14 * hi)
        bad = ~((new > lo) & (new < hi)) & ~tiny
        mid = np.where(hi > 4 * lo, np.sqrt(lo * hi), 0.5 * (lo + hi))
        new = np.where(bad, mid, new)
        done = np.all(tiny)
        ya = new
        if done:
            break
    y[act] = ya
    return y


# ------------------------------------------------------------------ GARCH(1,1)
def _garch_ll(e2, v, a, b, max_cells=6_000_000):
    """Gaussian log-likelihood of GARCH(1,1) with variance targeting for many (alpha, beta) at once.
    e2: (T, N) squared demeaned returns; v: (N,) their mean; a, b: (K, N) candidate alpha, beta per column.
    sigma^2_0 = v, sigma^2_t = omega + alpha e^2_{t-1} + beta sigma^2_{t-1}, omega = v (1 - alpha - beta);
    loglik = -1/2 sum_t (log 2 pi + log sigma^2_t + e^2_t / sigma^2_t). Returns (K, N)."""
    T, N = e2.shape
    K = a.shape[0]
    out = np.empty((K, N))
    kc = max(1, int(max_cells // (T * N)))
    for k0 in range(0, K, kc):
        aa, bb = a[k0:k0 + kc], b[k0:k0 + kc]
        om = v * (1 - aa - bb)
        S = np.empty((T,) + aa.shape)
        S[0] = v
        for t in range(1, T):
            np.multiply(bb, S[t - 1], out=S[t])
            S[t] += om
            S[t] += aa * e2[t - 1]
        out[k0:k0 + kc] = -0.5 * (T * LOG2PI + np.log(S).sum(0) + (e2[:, None, :] / S).sum(0))
    return out


def _garch_many(R, rounds=4):
    """garch_fit for every column of R (T, N) at once (one vectorized grid search over all columns).
    Coarse grid alpha = 0.01..0.30 (step 0.01) x beta = 0.50..0.98 (step 0.02), alpha + beta < 0.999; then `rounds`
    local 5 x 5 grids around each column's best point with the step halved each round (alpha in [0, 0.40],
    beta in [0, 0.999), alpha + beta < 0.999). The homoskedastic model (alpha = beta = 0, sigma^2 = v) is kept when its
    likelihood is at least as high, and always for a constant column (v < 1e-16)."""
    T, N = R.shape
    mu = R.mean(0)
    e = R - mu
    e2 = e * e
    v_raw = e2.mean(0)
    const = v_raw < VAR_FLOOR
    v = np.maximum(v_raw, VAR_FLOOR)
    a = np.repeat(GARCH_A[:, None], N, axis=1)
    b = np.repeat(GARCH_B[:, None], N, axis=1)
    ll = _garch_ll(e2, v, a, b)
    k = np.argmax(ll, axis=0)
    cols = np.arange(N)
    ba, bb, bl = a[k, cols], b[k, cols], ll[k, cols]
    oa, ob = np.meshgrid(np.arange(-2, 3), np.arange(-2, 3), indexing='ij')
    oa, ob = oa.ravel()[:, None].astype(float), ob.ravel()[:, None].astype(float)
    da, db = 0.005, 0.01
    for _ in range(rounds):
        ca = np.clip(ba + da * oa, 0.0, 0.40)
        cb = np.clip(bb + db * ob, 0.0, 0.998)
        bad = ca + cb >= 0.999
        ca, cb = np.where(bad, 0.0, ca), np.where(bad, 0.0, cb)
        lc = np.where(bad, -np.inf, _garch_ll(e2, v, ca, cb))
        k = np.argmax(lc, axis=0)
        better = lc[k, cols] > bl
        ba = np.where(better, ca[k, cols], ba)
        bb = np.where(better, cb[k, cols], bb)
        bl = np.where(better, lc[k, cols], bl)
        da, db = da / 2, db / 2
    ll0 = -0.5 * T * (LOG2PI + np.log(v) + v_raw / v)
    flat = const | (ll0 >= bl)
    alpha = np.where(flat, 0.0, ba)
    beta = np.where(flat, 0.0, bb)
    omega = v * (1 - alpha - beta)
    S = np.empty((T, N))
    S[0] = v
    for t in range(1, T):
        S[t] = omega + alpha * e2[t - 1] + beta * S[t - 1]
    z = np.where(const, 0.0, e / np.sqrt(S))
    loglik = -0.5 * (T * LOG2PI + np.log(S).sum(0) + (e2 / S).sum(0))
    return {'mu': mu, 'omega': omega, 'alpha': alpha, 'beta': beta, 'sigma2': S, 'z': z, 'loglik': loglik,
            'e_last': e[-1], 'const': const}


def garch_fit(r):
    """GARCH(1,1) by Gaussian quasi-maximum likelihood with variance targeting, for one series r of daily log returns:
    r_t = mu + e_t, mu = mean(r), e_t = sigma_t z_t, sigma^2_t = omega + alpha e^2_{t-1} + beta sigma^2_{t-1},
    omega = var(e) (1 - alpha - beta) (so the long-run variance is the sample variance), sigma^2_0 = var(e).
    Maximizes loglik = -1/2 sum (log 2 pi + log sigma^2_t + e^2_t / sigma^2_t) over a grid alpha in [0.01, 0.30],
    beta in [0.50, 0.98], alpha + beta < 0.999, then four rounds of a finer local grid. A constant or near-constant
    series, or one where volatility does not cluster at all, falls back to alpha = beta = 0.
    Returns dict(mu, omega, alpha, beta, sigma2 (fitted conditional variances, same length as r), z (standardized
    residuals (r - mu) / sigma_t), loglik)."""
    r = np.asarray(r, dtype=float).ravel()
    G = _garch_many(_prep(r))
    return {'mu': float(G['mu'][0]), 'omega': float(G['omega'][0]), 'alpha': float(G['alpha'][0]),
            'beta': float(G['beta'][0]), 'sigma2': G['sigma2'][:, 0].copy(), 'z': G['z'][:, 0].copy(),
            'loglik': float(G['loglik'][0])}


# ------------------------------------------------------------------ dependence: Kendall's tau, t copula, DCC
def _avg_ranks(X):
    """Column-wise ranks 1..T, ties sharing their average rank: rank = (#{x_s < x} + #{x_s <= x} + 1) / 2."""
    S = np.sort(X, axis=0)
    out = np.empty_like(X, dtype=float)
    for j in range(X.shape[1]):
        lo = np.searchsorted(S[:, j], X[:, j], 'left')
        hi = np.searchsorted(S[:, j], X[:, j], 'right')
        out[:, j] = (lo + hi + 1) / 2.0
    return out


def kendall_tau(X, max_cells=1_500_000):
    """Kendall's tau-b between every pair of columns of X (T, N):
    tau_ij = sum_{s,t} sgn(x_si - x_ti) sgn(x_sj - x_tj) / sqrt(n_i n_j), n_i = number of untied pairs in column i
    (= the same sum with j = i). Computed as M = D^T D with D the sign matrix of all ordered pairs, in chunks of rows,
    O(T^2 N^2) but vectorized. A constant column has tau 0 with everything (diagonal 1)."""
    X = _prep(X)
    T, N = X.shape
    M = np.zeros((N, N))
    c = max(1, int(max_cells // (T * N)))
    for i0 in range(0, T, c):
        D = np.sign(X[i0:i0 + c, None, :] - X[None, :, :]).reshape(-1, N)
        M += D.T @ D
    d = np.sqrt(np.diag(M))
    den = np.outer(d, d)
    tau = np.divide(M, den, out=np.zeros_like(M), where=den > 0)
    np.fill_diagonal(tau, 1.0)
    return tau


def t_copula_fit(R, nus=NU_GRID):
    """Student-t copula: correlation rho_ij = sin(pi tau_ij / 2) from Kendall's tau (exact for elliptical copulas),
    made positive definite if needed (_nearest_corr); degrees of freedom by maximum pseudo-likelihood over `nus` on the
    rank pseudo-observations u_tj = rank_tj / (T + 1), x = t_nu^{-1}(u):
    log c(u) = log Gamma((nu+N)/2) + (N-1) log Gamma(nu/2) - N log Gamma((nu+1)/2) - log|rho| / 2
               - (nu+N)/2 log(1 + x^T rho^{-1} x / nu) + (nu+1)/2 sum_j log(1 + x_j^2 / nu).
    Returns dict(rho, tau, nu, loglik {nu: sum of log c}); nu is None for a single column."""
    X = _prep(R)
    T, N = X.shape
    tau = kendall_tau(X)
    rho = _nearest_corr(np.sin(np.pi * tau / 2))
    if N == 1:
        return {'rho': rho, 'tau': tau, 'nu': None, 'loglik': {}}
    U = _avg_ranks(X) / (T + 1)
    L = _chol_jitter(rho)
    logdet = float(np.linalg.slogdet(rho)[1])
    uq, inv = np.unique(U.ravel(), return_inverse=True)
    ll = {}
    for nu in nus:
        nu = float(nu)
        Xt = np.asarray(t_ppf(uq, nu), dtype=float)[inv].reshape(U.shape)
        Y = np.linalg.solve(L, Xt.T)
        quad = (Y * Y).sum(0)
        c = math.lgamma((nu + N) / 2) + (N - 1) * math.lgamma(nu / 2) - N * math.lgamma((nu + 1) / 2) - 0.5 * logdet
        lt = c - (nu + N) / 2 * np.log1p(quad / nu) + (nu + 1) / 2 * np.log1p(Xt * Xt / nu).sum(1)
        ll[int(nu) if nu == int(nu) else nu] = float(lt.sum())
    best = max(ll, key=ll.get)
    return {'rho': rho, 'tau': tau, 'nu': best, 'loglik': ll}


def _dcc_qbar(z):
    """Qbar, the unconditional correlation of the standardized residuals: z^T z / T scaled to a unit diagonal; a column
    with no variation is uncorrelated with the rest; made positive definite if needed."""
    T, N = z.shape
    C = z.T @ z / T
    d = np.sqrt(np.diag(C))
    ok = d > 1e-12
    den = np.outer(np.where(ok, d, 1.0), np.where(ok, d, 1.0))
    C = np.where(np.outer(ok, ok), C / den, 0.0)
    return _nearest_corr(C)


def _dcc_loglik(z, Qbar, a, b, max_cells=2_500_000):
    """DCC(1,1) correlation log-likelihood for many (a, b) at once (a, b: (K,) arrays), Q_0 = Qbar,
    Q_t = (1-a-b) Qbar + a z_{t-1} z_{t-1}^T + b Q_{t-1}, R_t = diag(Q_t)^{-1/2} Q_t diag(Q_t)^{-1/2},
    L_C = -1/2 sum_t (log|R_t| + z_t^T R_t^{-1} z_t - z_t^T z_t), using log|R_t| = log|Q_t| - sum_i log q_ii,t and
    z^T R^{-1} z = w^T Q^{-1} w with w_i = sqrt(q_ii) z_i (one batched Cholesky per chunk of candidates)."""
    T, N = z.shape
    K = len(a)
    zzT = np.ascontiguousarray((z[:, :, None] * z[:, None, :]).transpose(1, 2, 0))       # (N, N, T)
    zsq = (z * z).sum(1)
    out = np.empty(K)
    kc = max(1, int(max_cells // (N * N * T)))
    for k0 in range(0, K, kc):
        aa, bb = a[k0:k0 + kc], b[k0:k0 + kc]
        kk = len(aa)
        Qs = np.empty((N, N, T, kk))
        c0 = (1 - aa - bb) * Qbar[:, :, None]
        Q = np.repeat(Qbar[:, :, None], kk, axis=2)
        Qs[:, :, 0] = Q
        for t in range(1, T):
            Q = c0 + aa * zzT[:, :, t - 1, None] + bb * Q
            Qs[:, :, t] = Q
        Qf = Qs.reshape(N, N, T * kk)
        d = np.sqrt(np.maximum(np.stack([Qf[i, i] for i in range(N)]), 1e-300))
        w = d * np.repeat(z.T, kk, axis=1)
        logdet, quad = _logdet_quad(Qf, w)
        lt = -0.5 * (logdet - 2 * np.log(d).sum(0) + quad - np.repeat(zsq, kk))
        out[k0:k0 + kk] = lt.reshape(T, kk).sum(0)
    return out


def dcc_fit(z, rounds=4):
    """Engle's (2002) DCC(1,1) on standardized residuals z (T, N) (from garch_fit of each column), by maximum likelihood
    (_dcc_loglik): a grid a in {0, 0.005, ..., 0.20} x b in {0.50, ..., 0.99} with a + b < 0.999, then `rounds` local
    5 x 5 grids around the best point (steps 0.005 / 0.01, halved each round; a in [0, 0.30], b in [0, 0.999)).
    Returns dict(a, b, Qbar, Q_next, loglik), Q_next = (1-a-b) Qbar + a z_T z_T^T + b Q_T: the first forecast day's Q."""
    z = _prep(z)
    T, N = z.shape
    Qbar = _dcc_qbar(z)
    if N == 1:
        return {'a': 0.0, 'b': 0.0, 'Qbar': Qbar, 'Q_next': Qbar.copy(), 'loglik': 0.0}
    A, B = _grid(DCC_A_GRID, DCC_B_GRID, 0.999)
    A, B = np.concatenate([[0.0], A]), np.concatenate([[0.0], B])
    ll = _dcc_loglik(z, Qbar, A, B)
    k = int(np.argmax(ll))
    ba, bb, bl = float(A[k]), float(B[k]), float(ll[k])
    oa, ob = np.meshgrid(np.arange(-2, 3), np.arange(-2, 3), indexing='ij')
    da, db = 0.005, 0.01
    for _ in range(rounds):
        ca = np.clip(ba + da * oa.ravel(), 0.0, 0.30)
        cb = np.clip(bb + db * ob.ravel(), 0.0, 0.998)
        keep = ca + cb < 0.999
        ca, cb = ca[keep], cb[keep]
        if len(ca):
            lc = _dcc_loglik(z, Qbar, ca, cb)
            k = int(np.argmax(lc))
            if lc[k] > bl:
                ba, bb, bl = float(ca[k]), float(cb[k]), float(lc[k])
        da, db = da / 2, db / 2
    Q = Qbar.copy()
    for t in range(1, T):
        Q = (1 - ba - bb) * Qbar + ba * np.outer(z[t - 1], z[t - 1]) + bb * Q
    Q_next = (1 - ba - bb) * Qbar + ba * np.outer(z[-1], z[-1]) + bb * Q
    return {'a': ba, 'b': bb, 'Qbar': Qbar, 'Q_next': Q_next, 'loglik': bl}


# ------------------------------------------------------------------ the seven simulators: daily log returns (n, h, N)
def _sim_joint_bootstrap(R, horizon, n, rng, **_):
    """r*_{i,k} = R[u_{i,k}] with u i.i.d. uniform on {0, ..., T-1}: whole historical rows."""
    idx = rng.integers(0, len(R), size=(n, horizon))
    return R[idx]


def _sim_block_bootstrap(R, horizon, n, rng, block=10, **_):
    """Politis-Romano stationary bootstrap of whole rows: u_0 uniform; then with probability p = 1/block a new block
    starts at a uniform random row, otherwise u_k = (u_{k-1} + 1) mod T. Block lengths ~ Geometric(p), mean `block`.
    Vectorized: the index on day k is (start of its block + days since the block began) mod T."""
    T = len(R)
    p = 1.0 / max(float(block), 1.0)
    new = rng.random((n, horizon)) < p
    new[:, 0] = True
    starts = rng.integers(0, T, size=(n, horizon))
    k = np.arange(horizon)
    last = np.maximum.accumulate(np.where(new, k, 0), axis=1)          # day on which the current block began
    idx = (np.take_along_axis(starts, last, axis=1) + (k - last)) % T
    return R[idx]


def _sim_fhs(R, horizon, n, rng, **_):
    """Filtered historical simulation: z = standardized GARCH residuals (T, N); each day draws one whole row z_u
    (u uniform, same date for every asset) and r = mu + sigma z with sigma^2 started at
    omega + alpha e_T^2 + beta sigma^2_T and updated by sigma^2 <- omega + alpha (r - mu)^2 + beta sigma^2."""
    G = _garch_many(R)
    mu, om, al, be, Z = G['mu'], G['omega'], G['alpha'], G['beta'], G['z']
    s2 = np.broadcast_to(om + al * G['e_last'] ** 2 + be * G['sigma2'][-1], (n, R.shape[1])).copy()
    idx = rng.integers(0, len(R), size=(horizon, n))
    out = np.empty((n, horizon, R.shape[1]))
    for k in range(horizon):
        e = np.sqrt(s2) * Z[idx[k]]
        out[:, k] = mu + e
        s2 = om + al * e * e + be * s2
    return out


def factor_fit(R, factors=(1, 2)):
    """OLS of every non-factor column on the factor columns that exist: r_j = a_j + sum_k b_jk f_k + e_j,
    coefficients (X^T X)^{-1} X^T r_j with X = [1, F] (least squares, so a constant factor is harmless).
    Returns dict(factors, others, coef ((1 + K) x M: intercepts then betas), resid (T x M))."""
    R = _prep(R)
    T, N = R.shape
    fac = sorted({int(f) for f in factors if 0 <= int(f) < N})
    oth = [j for j in range(N) if j not in fac]
    X = np.column_stack([np.ones(T)] + [R[:, f] for f in fac])
    Y = R[:, oth]
    coef = np.linalg.lstsq(X, Y, rcond=None)[0] if oth else np.zeros((X.shape[1], 0))
    return {'factors': fac, 'others': oth, 'coef': coef, 'resid': Y - X @ coef}


def _sim_factor(R, horizon, n, rng, factors=(1, 2), **_):
    """Factor columns: joint bootstrap of their rows; other columns: a + b . f + e with each residual e_j bootstrapped
    independently from its own fitted residuals (so stocks co-move only through the factors). With no factor column
    this is an independent bootstrap of each column."""
    T, N = R.shape
    F = factor_fit(R, factors)
    fac, oth, coef, E = F['factors'], F['others'], F['coef'], F['resid']
    out = np.empty((n, horizon, N))
    idx = rng.integers(0, T, size=(n, horizon))
    f = R[idx][:, :, fac] if fac else np.zeros((n, horizon, 0))
    if fac:
        out[:, :, fac] = f
    if oth:
        ie = rng.integers(0, T, size=(n, horizon, len(oth)))
        e = E[ie, np.arange(len(oth))]
        out[:, :, oth] = coef[0] + f @ coef[1:] + e
    return out


def _sim_cholesky(R, horizon, n, rng, **_):
    """r* = mu + L e, e ~ N(0, I_N), mu the sample mean vector, L L^T the sample covariance (ddof 1); a column with
    no variance (< 1e-16) gets a zero row of L, so it stays exactly at its mean."""
    mu = R.mean(0)
    S = np.atleast_2d(np.cov(R, rowvar=False))
    L = _chol_jitter(S)
    L[np.diag(S) < VAR_FLOOR] = 0.0
    e = rng.standard_normal((n, horizon, R.shape[1]))
    return mu + e @ L.T


def _emp_quantile(S, U):
    """Empirical quantile with linear interpolation between sorted observations (numpy's default 'linear' rule):
    Q_j(u) = s_(k) + (h - k)(s_(k+1) - s_(k)), h = u (T - 1), k = floor(h), for sorted columns S (T, N), U (M, N)."""
    T, N = S.shape
    h = np.clip(U, 0.0, 1.0) * (T - 1)
    k = np.clip(np.floor(h).astype(np.int64), 0, max(T - 2, 0))
    frac = h - k
    cols = np.arange(N)
    lo = S[k, cols]
    hi = S[np.minimum(k + 1, T - 1), cols]
    return lo + frac * (hi - lo)


def _sim_t_copula(R, horizon, n, rng, **_):
    """u = t_nu(x), x = L g / sqrt(W / nu), g ~ N(0, I), W ~ chi^2_nu, L L^T = rho (t_copula_fit); then each column
    r*_j = Q_j(u_j), its empirical quantile function. Daily draws i.i.d."""
    T, N = R.shape
    fit = t_copula_fit(R)
    M = n * horizon
    if N == 1:
        U = rng.random((M, 1))
    else:
        nu = float(fit['nu'])
        L = _chol_jitter(fit['rho'])
        g = rng.standard_normal((M, N)) @ L.T
        W = rng.chisquare(nu, M) / nu
        U = np.asarray(t_cdf(g / np.sqrt(W)[:, None], nu), dtype=float)
    return _emp_quantile(np.sort(R, axis=0), U).reshape(n, horizon, N)


def _sim_dcc_garch(R, horizon, n, rng, **_):
    """GARCH(1,1) per column, DCC(1,1) on the standardized residuals; forward: Q starts at Q_next, each day
    e = diag(Q)^{-1/2} chol(Q) g (so e ~ N(0, R_t)), r = mu + sigma e, then Q <- (1-a-b) Qbar + a e e^T + b Q and
    sigma^2 <- omega + alpha (r - mu)^2 + beta sigma^2."""
    T, N = R.shape
    G = _garch_many(R)
    D = dcc_fit(G['z'])
    a, b = D['a'], D['b']
    live = ~G['const']                                                  # a constant column stays exactly flat
    mu, al, be = (G[k][:, None] for k in ('mu', 'alpha', 'beta'))
    om = np.where(live, G['omega'], 0.0)[:, None]
    s2 = np.repeat(np.where(live, G['omega'] + G['alpha'] * G['e_last'] ** 2 + G['beta'] * G['sigma2'][-1], 0.0)[:, None],
                   n, axis=1)
    Q = np.repeat(D['Q_next'][:, :, None], n, axis=2)
    c0 = (1 - a - b) * D['Qbar'][:, :, None]
    g = rng.standard_normal((horizon, N, n))
    out = np.empty((n, horizon, N))
    eps = np.empty((N, n))
    for k in range(horizon):
        L = _chol_lower(Q)
        for i in range(N):
            acc = L[i][0] * g[k, 0]
            for j in range(1, i + 1):
                acc = acc + L[i][j] * g[k, j]
            eps[i] = acc / np.sqrt(np.maximum(Q[i, i], 1e-300))
        e = np.sqrt(s2) * eps
        out[:, k] = (mu + e).T
        Q = c0 + a * (eps[:, None, :] * eps[None, :, :]) + b * Q
        s2 = om + al * e * e + be * s2
    return out


_SIMS = {'joint_bootstrap': _sim_joint_bootstrap, 'block_bootstrap': _sim_block_bootstrap, 'fhs': _sim_fhs,
         'factor': _sim_factor, 'cholesky': _sim_cholesky, 't_copula': _sim_t_copula, 'dcc_garch': _sim_dcc_garch}


def simulate(R, model, horizon=63, n=1000, seed=0, factors=(1, 2), block=10):
    """Simulated cumulative log-return paths, shape (n, horizon, N): paths[i, k, j] = sum of the simulated daily log
    returns of asset j over days 0..k of path i. R: (T, N) daily log returns (see the module docstring); model: one of
    MODELS; factors: factor columns for the 'factor' model; block: mean block length for 'block_bootstrap'.
    Deterministic given seed (numpy default_rng)."""
    if model not in _SIMS:
        raise ValueError(f'unknown model {model!r}; expected one of {MODELS}')
    R = _prep(R)
    horizon, n = int(horizon), int(n)
    if horizon < 1 or n < 1:
        raise ValueError('horizon and n must be >= 1')
    rng = np.random.default_rng(seed)
    daily = _SIMS[model](R, horizon, n, rng, factors=factors, block=block)
    return _cum(daily)


def _sim_naive(R, horizon, n, rng):
    """Baseline: column 0 only, r* ~ N(mean, sd) i.i.d. (sample mean and standard deviation, ddof 1). (n, horizon, 1)."""
    r = R[:, 0]
    sd = float(r.std(ddof=1)) if len(r) > 1 else 0.0
    return _cum(r.mean() + sd * rng.standard_normal((n, horizon, 1)))


# ------------------------------------------------------------------ summaries for the charts
def _qkey(q):
    """0.05 -> 'p05', 0.5 -> 'p50', 0.025 -> 'p2.5'."""
    pct = round(q * 100, 6)
    return f'p{int(pct):02d}' if pct == int(pct) else f'p{pct:g}'


def summarize(paths, price0, col=0, qs=(0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)):
    """The fan chart and headline numbers of one asset. Prices P_ik = price0 exp(paths[i, k, col]).
    'q': for each horizon day k = 1..h, [quantile of P_.k at each q in qs] (4 significant digits);
    'end': the quantiles at the horizon ('p05' ... 'p95') and the 'mean' final price;
    'p_down10' / 'p_up10' / 'p_down20' / 'p_up20': P(P_h / price0 - 1 <= -10%), P(>= +10%), P(<= -20%), P(>= +20%);
    'mdd': {'p50', 'p90'} quantiles of each path's maximum drawdown max_k (1 - P_k / max(price0, P_1..P_k)) (fractions);
    'p_touch_down10': P(min_k P_k <= 0.9 price0), touching -10% at any point;
    'vol': annualized volatility sqrt(252) x std of the simulated daily log returns of `col`.
    Returns None when price0 is not a positive number."""
    try:
        p0 = float(price0)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(p0) and p0 > 0):
        return None
    paths = np.asarray(paths, dtype=float)
    if paths.ndim == 2:
        paths = paths[:, :, None]
    c = np.where(np.isfinite(paths[:, :, col]), paths[:, :, col], 0.0)
    n, h = c.shape
    P = p0 * np.exp(c)
    qs = tuple(float(q) for q in qs)
    Q = np.quantile(P, qs, axis=0).T
    fin = P[:, -1]
    end = {_qkey(q): _sig(np.quantile(fin, q)) for q in qs}
    end['mean'] = _sig(fin.mean())
    ret = fin / p0 - 1
    run = np.maximum.accumulate(np.concatenate([np.full((n, 1), p0), P], axis=1), axis=1)[:, 1:]
    mdd = (1 - P / run).max(axis=1)
    inc = np.diff(c, axis=1, prepend=0.0)
    vol = float(inc.std(ddof=1)) * math.sqrt(TRADING_DAYS) if inc.size > 1 else 0.0
    return {'n': n, 'horizon': h, 'price0': p0, 'qs': list(qs), 'q': [[_sig(v) for v in row] for row in Q], 'end': end,
            'p_down10': _p(ret <= -0.10), 'p_up10': _p(ret >= 0.10), 'p_down20': _p(ret <= -0.20), 'p_up20': _p(ret >= 0.20),
            'mdd': {'p50': _sig(np.quantile(mdd, 0.5)), 'p90': _sig(np.quantile(mdd, 0.9))},
            'p_touch_down10': _p(P.min(axis=1) <= 0.9 * p0), 'vol': _sig(vol)}


def joint(paths, a=0, b=1, thr=-0.10):
    """How two assets fall together, from their final cumulative log returns x_a, x_b:
    'p_a_given_b' = P(x_a < thr | x_b < thr), i.e. a ends below exp(thr) - 1 given b does (None with fewer than 20 such
    paths); 'p_a' = P(x_a < thr); 'p_b' = P(x_b < thr); 'n_b' = number of paths with x_b < thr;
    'corr' = Pearson correlation of x_a and x_b; 'tail_corr' = the same correlation over the paths where b is in its
    worst 10%. None if a or b is not a column of paths."""
    paths = np.asarray(paths, dtype=float)
    if paths.ndim != 3 or not (0 <= a < paths.shape[2] and 0 <= b < paths.shape[2]):
        return None
    xa, xb = paths[:, -1, a], paths[:, -1, b]
    mb = xb < thr
    nb = int(mb.sum())
    worst = np.argsort(xb, kind='stable')[:max(3, int(math.ceil(0.10 * len(xb))))]
    return {'p_a_given_b': round(float((xa[mb] < thr).mean()), 4) if nb >= 20 else None, 'p_a': _p(xa < thr),
            'p_b': _p(mb), 'n_b': nb, 'corr': _corr(xa, xb), 'tail_corr': _corr(xa[worst], xb[worst]), 'thr': thr}


def sample_paths(paths, price0, col=0, k=40, seed=0):
    """k price paths (lists of horizon prices, days 1..h, 4 significant digits) spread evenly over the distribution of
    final values: sort the paths by final value and take the ranks floor((i + u) n / k), i = 0..k-1, with one random
    offset u in [0, 1) from default_rng(seed) (systematic sampling: evenly spaced ranks). Returned from lowest to
    highest final value; [] when price0 is not a positive number."""
    try:
        p0 = float(price0)
    except (TypeError, ValueError):
        return []
    if not (math.isfinite(p0) and p0 > 0):
        return []
    paths = np.asarray(paths, dtype=float)
    if paths.ndim == 2:
        paths = paths[:, :, None]
    c = paths[:, :, col]
    n = len(c)
    k = max(0, min(int(k), n))
    if not k:
        return []
    order = np.argsort(c[:, -1], kind='stable')
    u = np.random.default_rng(seed).random()
    ranks = np.minimum(np.floor((np.arange(k) + u) * n / k).astype(int), n - 1)
    return [[_sig(v) for v in p0 * np.exp(c[i])] for i in order[ranks]]


# ------------------------------------------------------------------ walk-forward scoring
def _score(R_full, sim_final, origins, horizon, window, seed):
    """Shared walk-forward scorer. For each usable origin o (o >= window, o + horizon <= T): s = sim_final(R[o-window:o],
    seed + i), the simulated cumulative log returns of column 0 at the horizon; y = sum R[o:o+horizon, 0], the realized one.
    cover80 / cover50: share of y inside [q10, q90] / [q25, q75] of s; pinball: mean over tau = 0.05..0.95 and origins of
    (tau - 1{y < q_tau})(y - q_tau); pit: (#{s < y} + #{s = y} / 2) / len(s); width80: mean q90 - q10."""
    R = _prep(R_full)
    T = len(R)
    used, c80, c50, pin, pit, wid = [], [], [], [], [], []
    for i, o in enumerate(origins):
        o = int(o)
        if o < window or o + horizon > T or window < 2:
            continue
        s = np.asarray(sim_final(R[o - window:o], seed + i), dtype=float)
        y = float(R[o:o + horizon, 0].sum())
        q10, q25, q75, q90 = np.quantile(s, (0.10, 0.25, 0.75, 0.90))
        qt = np.quantile(s, EVAL_TAUS)
        used.append(o)
        c80.append(q10 <= y <= q90)
        c50.append(q25 <= y <= q75)
        pin.append(float(np.mean((EVAL_TAUS - (y < qt)) * (y - qt))))
        pit.append(round((float(np.sum(s < y)) + 0.5 * float(np.sum(s == y))) / len(s), 4))
        wid.append(q90 - q10)
    if not used:
        return {'n': 0, 'cover80': None, 'cover50': None, 'pinball': None, 'pit': [], 'width80': None, 'origins': []}
    return {'n': len(used), 'cover80': round(float(np.mean(c80)), 4), 'cover50': round(float(np.mean(c50)), 4),
            'pinball': _sig(np.mean(pin), 6), 'pit': pit, 'width80': _sig(np.mean(wid), 6), 'origins': used}


def evaluate(R_full, model, origins, horizon=63, window=756, n=500, seed=0, **kw):
    """Walk-forward score of one model on column 0: at each origin o in `origins` with o >= window and
    o + horizon <= T, fit and simulate on R_full[o-window:o] only (no look-ahead) and compare with the realized
    cumulative log return over R_full[o:o+horizon]. **kw goes to simulate (factors, block). Returns
    {'model', 'n', 'cover80', 'cover50', 'pinball', 'pit', 'width80', 'origins'} (see _score). Well calibrated:
    cover80 ~ 0.8, cover50 ~ 0.5, PIT uniform; among calibrated models a lower pinball loss is sharper and better."""
    def fin(Rw, s):
        return simulate(Rw, model, horizon=horizon, n=n, seed=s, **kw)[:, -1, 0]
    out = _score(R_full, fin, origins, horizon, window, seed)
    return {'model': model, **out}


def naive_normal(R_full, origins, horizon=63, window=756, n=500, seed=0):
    """The baseline scored exactly like evaluate(): i.i.d. normal daily returns with column 0's own mean and standard
    deviation over the window, univariate."""
    def fin(Rw, s):
        return _sim_naive(Rw, horizon, n, np.random.default_rng(s))[:, -1, 0]
    return {'model': 'naive_normal', **_score(R_full, fin, origins, horizon, window, seed)}


def evaluate_all(R_full, origins, horizon=63, window=756, n=500, seed=0, models=None, **kw):
    """evaluate() for every model in `models` (default MODELS) plus the 'naive_normal' baseline, as {name: result}."""
    out = {m: evaluate(R_full, m, origins, horizon=horizon, window=window, n=n, seed=seed, **kw) for m in (models or MODELS)}
    out['naive_normal'] = naive_normal(R_full, origins, horizon=horizon, window=window, n=n, seed=seed)
    return out


# ------------------------------------------------------------------ benchmark
def _demo_returns(T=756, N=5, seed=0):
    """Synthetic but realistic daily log returns: market and sector with GARCH(1,1) Student-t(5) shocks, stocks =
    alpha + beta x market + gamma x sector-specific + their own GARCH noise. Column order as in the module docstring."""
    rng = np.random.default_rng(seed)

    def garch(omega, a, b, nu=5.0):
        z = rng.standard_t(nu, T) * math.sqrt((nu - 2) / nu)
        r = np.empty(T)
        s2 = omega / (1 - a - b)
        for t in range(T):
            r[t] = math.sqrt(s2) * z[t]
            s2 = omega + a * r[t] ** 2 + b * s2
        return r
    m = 0.0004 + garch(2e-6, 0.10, 0.88)
    cols = [None, m]
    if N > 2:
        cols.append(0.0002 + 0.9 * m + garch(1e-6, 0.06, 0.92))
    sect = cols[2] - 0.9 * m if N > 2 else np.zeros(T)
    stock = lambda beta, gam: 0.0003 + beta * m + gam * sect + garch(4e-6, 0.07, 0.90)   # noqa: E731
    cols[0] = stock(1.2, 0.8)
    for j in range(3, N):
        cols.append(stock(0.8 + 0.1 * j, 0.6))
    return np.column_stack(cols[:N])


def benchmark(T=756, N=5, n=1000, horizon=63, seed=0):
    """Seconds taken by simulate() for each model on synthetic data of the given size, plus their 'total'."""
    R = _demo_returns(T, N, seed)
    times = {}
    for m in MODELS:
        t0 = time.perf_counter()
        simulate(R, m, horizon=horizon, n=n, seed=seed)
        times[m] = time.perf_counter() - t0
    times['total'] = sum(times.values())
    return times


if __name__ == '__main__':
    tm = benchmark()
    for k, v in tm.items():
        print(f'{k:16s} {v * 1000:8.1f} ms')
