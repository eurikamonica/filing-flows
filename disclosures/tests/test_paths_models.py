"""app/paths_models.py: the seven price-path models (shapes, determinism, what each one is supposed to keep), the
GARCH / DCC / t-copula estimators on data simulated from known parameters, the Student-t functions against closed forms
and table values, the chart summaries, the walk-forward scoring, and the speed of a full run."""
import json
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import paths_models as PM  # noqa: E402


# ------------------------------------------------------------------ data with known structure
def garch_series(T, omega, a, b, rng, nu=None):
    """r_t = sigma_t z_t, sigma^2_t = omega + a r^2_{t-1} + b sigma^2_{t-1}, z normal or unit-variance Student-t."""
    z = rng.standard_normal(T) if nu is None else rng.standard_t(nu, T) * math.sqrt((nu - 2) / nu)
    r = np.empty(T)
    s2 = omega / (1 - a - b)
    for t in range(T):
        r[t] = math.sqrt(s2) * z[t]
        s2 = omega + a * r[t] ** 2 + b * s2
    return r


def equicorr(N, rho):
    C = np.full((N, N), rho)
    np.fill_diagonal(C, 1.0)
    return C


def mv_t(T, C, nu, rng):
    """Multivariate Student-t (nu=None: normal) rows with correlation C."""
    g = rng.standard_normal((T, len(C))) @ np.linalg.cholesky(C).T
    return g if nu is None else g / np.sqrt(rng.chisquare(nu, T) / nu)[:, None]


def daily(paths):
    """The simulated daily log returns back from cumulative paths."""
    return np.diff(paths, axis=1, prepend=0.0)


def acf1(x):
    x = x - x.mean()
    return float((x[1:] * x[:-1]).sum() / (x * x).sum())


def acf1_pooled(X):
    """Lag-1 autocorrelation of the rows of X (paths x days) about their common mean, pooled over all paths."""
    m = X.mean()
    return float(((X[:, 1:] - m) * (X[:, :-1] - m)).sum() / ((X - m) ** 2).sum() * X.shape[1] / (X.shape[1] - 1))


def kurt(x):
    x = x - x.mean()
    return float((x ** 4).mean() / (x * x).mean() ** 2)


def all_past_rows(sim, R, tol=1e-12):
    """Every simulated row equals some historical row (up to the rounding of cumsum then diff)."""
    gap = np.abs(sim[:, None, :] - R[None, :, :]).max(axis=2).min(axis=1)
    return bool(gap.max() < tol)


def lower_tail(d, q):
    """P(asset 0 below its q-quantile | asset 1 below its q-quantile), from daily draws d (M, N)."""
    a, b = d[:, 0], d[:, 1]
    return float(np.mean(a[b <= np.quantile(b, q)] <= np.quantile(a, q)))


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = PM._demo_returns(300, 5, seed=11)

    def test_models_and_info(self):
        self.assertEqual(PM.MODELS, ['joint_bootstrap', 'block_bootstrap', 'fhs', 'factor', 'cholesky', 't_copula', 'dcc_garch'])
        self.assertEqual(set(PM.MODEL_INFO), set(PM.MODELS))
        for m, info in PM.MODEL_INFO.items():
            self.assertTrue(info['name'] and info['short'], m)
            self.assertIn(m, PM.__doc__)                                          # every model is described up top
        with self.assertRaises(ValueError):
            PM.simulate(self.R, 'garch_of_the_gods')

    def test_shapes_finiteness_and_determinism_for_every_model(self):
        for m in PM.MODELS:
            a = PM.simulate(self.R, m, horizon=15, n=120, seed=7)
            b = PM.simulate(self.R, m, horizon=15, n=120, seed=7)
            c = PM.simulate(self.R, m, horizon=15, n=120, seed=8)
            self.assertEqual(a.shape, (120, 15, 5), m)
            self.assertTrue(np.isfinite(a).all(), m)
            np.testing.assert_array_equal(a, b, err_msg=m)                        # same seed, same paths
            self.assertFalse(np.array_equal(a, c), m)                             # another seed, other paths
            d = daily(a)
            np.testing.assert_allclose(np.cumsum(d, axis=1), a, atol=1e-15)       # paths are cumulative sums
            self.assertTrue(0.3 < d[:, :, 0].std() / self.R[:, 0].std() < 3, m)   # daily scale of the history

    def test_degenerate_inputs_degrade_gracefully(self):
        rng = np.random.default_rng(3)
        x = rng.standard_normal(200) * 0.01
        cases = {'constant column': np.column_stack([x, np.zeros(200), rng.standard_normal(200) * 0.01]),
                 'all constant': np.zeros((80, 3)),
                 'T = 60': rng.standard_normal((60, 4)) * 0.02,
                 'one column': x[:, None],
                 'a 1-D series': x,
                 'two columns': rng.standard_normal((100, 2)) * 0.02,
                 'collinear': np.column_stack([x, x, 2 * x, rng.standard_normal(200) * 0.01]),
                 'ties': np.round(rng.standard_normal((150, 3)) * 0.01, 3),
                 'near zero': rng.standard_normal((100, 3)) * 1e-9}
        for name, R in cases.items():
            for m in PM.MODELS:
                P = PM.simulate(R, m, horizon=10, n=100, seed=1)
                self.assertTrue(np.isfinite(P).all(), (name, m))
                txt = json.dumps([PM.summarize(P, 50.0), PM.joint(P, 0, P.shape[2] - 1), PM.sample_paths(P, 50.0, k=5)])
                self.assertNotIn('NaN', txt, (name, m))
                self.assertNotIn('Infinity', txt, (name, m))
                if name == 'constant column':
                    self.assertEqual(float(np.ptp(P[:, :, 1])), 0.0, m)          # a flat series stays flat
        g = PM.garch_fit(np.zeros(100))
        self.assertEqual((g['alpha'], g['beta']), (0.0, 0.0))
        self.assertTrue(np.isfinite(g['z']).all() and np.isfinite(g['sigma2']).all() and len(g['sigma2']) == 100)


class Bootstraps(unittest.TestCase):
    def test_joint_bootstrap_keeps_correlation_and_fat_tails(self):
        rng = np.random.default_rng(0)
        C = np.array([[1, 0.6, 0.4], [0.6, 1, 0.5], [0.4, 0.5, 1]])
        R = 0.01 * mv_t(756, C, 5, rng)
        P = PM.simulate(R, 'joint_bootstrap', horizon=63, n=1000, seed=0)
        d = daily(P).reshape(-1, 3)
        self.assertTrue(all_past_rows(d[:2000], R))                                # every day is one whole past day
        np.testing.assert_allclose(np.corrcoef(d.T), np.corrcoef(R.T), atol=0.03)
        self.assertGreater(kurt(R[:, 0]), 3.8)                                    # fat-tailed data
        self.assertAlmostEqual(kurt(d[:, 0]), kurt(R[:, 0]), delta=0.12 * kurt(R[:, 0]))

    def test_block_bootstrap_keeps_volatility_clustering(self):
        rng = np.random.default_rng(1)
        r = garch_series(1500, 2e-6, 0.15, 0.80, rng)
        R = np.column_stack([r, 0.5 * r + 0.01 * rng.standard_normal(1500)])
        sample = acf1(r ** 2)
        got = {m: acf1_pooled(daily(PM.simulate(R, m, horizon=250, n=200, seed=1))[:, :, 0] ** 2)
               for m in ('joint_bootstrap', 'block_bootstrap')}
        self.assertGreater(sample, 0.05)
        self.assertLess(abs(got['joint_bootstrap']), 0.03)                        # i.i.d. days: no clustering
        self.assertGreater(got['block_bootstrap'], 0.7 * sample)                  # ~90% survives (lost at block joins)
        self.assertLess(abs(got['block_bootstrap'] - sample), abs(got['joint_bootstrap'] - sample))

    def test_block_lengths_are_geometric_with_the_given_mean(self):
        T = 500
        R = np.column_stack([np.arange(T) * 1e-3, np.zeros(T)])                    # the value encodes the date
        for block in (5, 10, 20):
            idx = np.rint(daily(PM.simulate(R, 'block_bootstrap', horizon=100, n=400, seed=2, block=block))[:, :, 0] * 1e3).astype(int)
            cont = np.mean((idx[:, 1:] - idx[:, :-1]) % T == 1)                    # the day after, wrapping at the end
            self.assertAlmostEqual(cont, 1 - 1 / block, delta=0.01)
        self.assertTrue(((idx[:, 1:] == 0) & (idx[:, :-1] == T - 1)).any())       # runs wrap around the last day


class Garch(unittest.TestCase):
    def test_garch_fit_recovers_alpha_and_beta(self):
        for seed, (a, b) in enumerate(((0.08, 0.90), (0.05, 0.93))):
            r = garch_series(5000, 2e-6 * (1 - a - b) * 50, a, b, np.random.default_rng(seed))
            g = PM.garch_fit(r)
            self.assertAlmostEqual(g['alpha'], a, delta=0.05)                      # the spec's +-0.05
            self.assertAlmostEqual(g['beta'], b, delta=0.05)
            self.assertLess(g['alpha'] + g['beta'], 0.999)
            self.assertAlmostEqual(g['omega'], np.var(r) * (1 - g['alpha'] - g['beta']), delta=1e-12)   # variance targeting
            self.assertEqual(len(g['sigma2']), len(r))
            np.testing.assert_allclose(g['z'], (r - g['mu']) / np.sqrt(g['sigma2']))
            self.assertAlmostEqual(np.var(g['z']), 1.0, delta=0.1)
        iid = PM.garch_fit(np.random.default_rng(5).standard_normal(2000) * 0.01)
        self.assertLess(iid['sigma2'].std() / iid['sigma2'].mean(), 0.15)          # no clustering: ~flat variance

    def test_fhs_widens_after_a_volatility_spike(self):
        rng = np.random.default_rng(0)
        base = np.column_stack([garch_series(756, 2e-6, 0.08, 0.90, rng) for _ in range(2)])
        calm, spike = base.copy(), base.copy()
        calm[-20:] *= 0.3
        spike[-20:] *= 4
        width = {}
        for name, R in (('calm', calm), ('spike', spike)):
            fin = PM.simulate(R, 'fhs', horizon=21, n=2000, seed=0)[:, -1, 0]
            q10, q90 = np.quantile(fin, (0.1, 0.9))
            width[name] = q90 - q10
            boot = PM.simulate(R, 'joint_bootstrap', horizon=21, n=2000, seed=0)[:, -1, 0]
            width[name + ' bootstrap'] = np.subtract(*np.quantile(boot, (0.9, 0.1)))
        self.assertGreater(width['spike'], 1.5 * width['calm'])
        self.assertLess(width['calm'], width['calm bootstrap'])                    # calm today: narrower than history
        self.assertGreater(width['spike'], width['spike bootstrap'])               # stormy today: wider


class Gaussian(unittest.TestCase):
    def test_cholesky_reproduces_the_covariance_with_thin_tails(self):
        rng = np.random.default_rng(4)
        C = np.array([[1, 0.6, 0.4], [0.6, 1, 0.5], [0.4, 0.5, 1]])
        R = 0.01 * mv_t(756, C, 5, rng) * np.array([1.5, 1.0, 1.2]) + 0.0004
        d = daily(PM.simulate(R, 'cholesky', horizon=63, n=1000, seed=0)).reshape(-1, 3)
        S = np.cov(R.T)
        self.assertLess(np.abs(np.cov(d.T) - S).max() / np.abs(S).max(), 0.03)
        np.testing.assert_allclose(d.mean(0), R.mean(0), atol=3e-4)
        self.assertAlmostEqual(kurt(d[:, 0]), 3.0, delta=0.15)                     # normal, whatever the data
        L = PM._chol_jitter(np.ones((3, 3)))                                       # singular: jitter, no error
        self.assertTrue(np.isfinite(L).all())
        np.testing.assert_allclose(L @ L.T, np.ones((3, 3)), atol=1e-6)


class StudentT(unittest.TestCase):
    def test_cdf_matches_closed_forms_and_the_normal_limit(self):
        x = np.linspace(-50, 50, 2001)
        np.testing.assert_allclose(PM.t_cdf(x, 1), 0.5 + np.arctan(x) / np.pi, atol=1e-14)        # Cauchy
        np.testing.assert_allclose(PM.t_cdf(x, 2), 0.5 + x / (2 * np.sqrt(2 + x * x)), atol=1e-14)
        y = np.linspace(-8, 8, 321)
        y2 = y * y / 4
        f4 = 0.5 + 3 / 8 * y / np.sqrt(1 + y2) * (1 - y2 / (3 * (1 + y2)))                   # nu = 4 closed form
        np.testing.assert_allclose(PM.t_cdf(y, 4), f4, atol=1e-14)
        N = PM.norm_cdf(x)
        self.assertLess(np.abs(PM.t_cdf(x, 1e6) - N).max(), 1e-6)                                  # t_inf -> normal
        self.assertLess(np.abs(PM.t_cdf(x, 1e4) - N).max(), 2e-5)
        np.testing.assert_allclose(PM.t_cdf(x, math.inf), N, atol=1e-15)
        self.assertAlmostEqual(PM.norm_cdf(1.959963984540054), 0.975, places=15)
        np.testing.assert_allclose(PM.t_cdf(-y, 7.3), 1 - PM.t_cdf(y, 7.3), atol=1e-15)            # symmetric
        for nu in (3, 10, 30):                     # integer series and incomplete-beta continued fraction agree
            np.testing.assert_allclose(PM.t_cdf(y, nu), PM.t_cdf(y, nu + 1e-10), atol=1e-12)
        self.assertLess(abs(PM.t_cdf(5.0, 999.999999) - PM.t_cdf(5.0, 1000.0)), 1e-9)            # branch switch
        self.assertEqual(PM.t_cdf(0.0, 3.5), 0.5)
        self.assertTrue(math.isnan(PM.t_cdf(float('nan'), 3)))

    def test_quantiles_match_tables_and_invert_the_cdf(self):
        table = {(10, 0.975): 2.228138851986, (3, 0.95): 2.353363434802, (5, 0.99): 3.364929998907,
                 (30, 0.975): 2.042272456301, (1, 0.975): 12.706204736175, (2, 0.975): 4.302652729750}
        for (nu, p), v in table.items():
            self.assertAlmostEqual(PM.t_ppf(p, nu), v, delta=1e-9)
            self.assertAlmostEqual(PM.t_ppf(1 - p, nu), -v, delta=1e-9)
        self.assertAlmostEqual(PM.norm_ppf(0.975), 1.959963984540054, places=13)
        p = np.concatenate([np.logspace(-10, -1, 120), np.linspace(0.1, 0.9, 81), 1 - np.logspace(-10, -1, 120)])
        for nu in PM.NU_GRID + (3.5, 7.3, 2000.0, math.inf):
            q = PM.t_ppf(p, nu)
            F = PM.t_cdf(q, nu)
            self.assertLess(np.abs(F - p).max(), 1e-13, nu)
            lo = p < 0.5
            self.assertLess(np.abs(F[lo] / p[lo] - 1).max(), 1e-8, nu)                             # relative, deep tail
        mid = (p > 1e-6) & (p < 1 - 1e-6)                                  # where tan(pi (p - 1/2)) is itself accurate
        np.testing.assert_allclose(PM.t_ppf(p[mid], 1), np.tan(np.pi * (p[mid] - 0.5)), rtol=1e-9, atol=1e-15)
        self.assertEqual(list(PM.t_ppf([0.0, 0.5, 1.0], 4)), [-np.inf, 0.0, np.inf])


class TCopula(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(0)
        cls.Xt = np.expm1(0.01 * mv_t(1000, equicorr(4, 0.5), 4, rng))    # t copula nu = 4, skewed marginals
        cls.Xg = 0.01 * mv_t(1000, equicorr(4, 0.5), None, rng)           # Gaussian copula

    def test_kendall_tau_and_its_correlation(self):
        X = np.random.default_rng(9).standard_normal((60, 3))
        X[:, 1] += X[:, 0]
        X[::7, 2] = 0.0                                                    # ties
        tau = PM.kendall_tau(X)
        for i in range(3):
            for j in range(3):
                s = np.sign(X[:, None, i] - X[None, :, i]) * np.sign(X[:, None, j] - X[None, :, j])
                ni = (np.sign(X[:, None, i] - X[None, :, i]) ** 2).sum()
                nj = (np.sign(X[:, None, j] - X[None, :, j]) ** 2).sum()
                self.assertAlmostEqual(tau[i, j], s.sum() / math.sqrt(ni * nj), places=12)        # tau-b by brute force
        fit = PM.t_copula_fit(self.Xg)
        np.testing.assert_allclose(fit['rho'], np.sin(np.pi * fit['tau'] / 2), atol=1e-12)
        self.assertTrue(np.all(np.abs(fit['rho'][~np.eye(4, dtype=bool)] - 0.5) < 0.08))         # se ~0.025 at T = 1000
        bad = PM._nearest_corr(np.array([[1, 0.9, -0.9], [0.9, 1, 0.9], [-0.9, 0.9, 1]]))         # not PD
        self.assertGreater(np.linalg.eigvalsh(bad)[0], 0)
        np.testing.assert_allclose(np.diag(bad), 1.0)

    def test_degrees_of_freedom(self):
        self.assertLessEqual(PM.t_copula_fit(self.Xt)['nu'], 8)
        self.assertGreaterEqual(PM.t_copula_fit(self.Xg)['nu'], 20)

    def test_crashes_come_together_more_than_under_cholesky(self):
        dt = daily(PM.simulate(self.Xt, 't_copula', horizon=63, n=1000, seed=0)).reshape(-1, 4)
        dc = daily(PM.simulate(self.Xt, 'cholesky', horizon=63, n=1000, seed=0)).reshape(-1, 4)
        truth = lower_tail(mv_t(200_000, equicorr(4, 0.5), 4, np.random.default_rng(12345)), 0.02)   # ~0.31
        self.assertGreater(lower_tail(dt, 0.02), lower_tail(dc, 0.02) + 0.05)
        self.assertAlmostEqual(lower_tail(dt, 0.02), truth, delta=0.1)           # nu and rho are estimated

    def test_marginals_are_the_empirical_distributions(self):
        d = daily(PM.simulate(self.Xt, 't_copula', horizon=50, n=1000, seed=1)).reshape(-1, 4)
        for j in range(4):
            x = self.Xt[:, j]
            self.assertTrue(x.min() <= d[:, j].min() and d[:, j].max() <= x.max())
            qs = np.linspace(0.05, 0.95, 19)
            np.testing.assert_allclose(np.quantile(d[:, j], qs), np.quantile(x, qs), atol=0.12 * x.std())


class Dcc(unittest.TestCase):
    def test_dcc_recovers_persistent_time_varying_correlation(self):
        rng = np.random.default_rng(0)
        T, a0, b0 = 1500, 0.05, 0.93
        Qbar = np.array([[1, 0.4, 0.3], [0.4, 1, 0.35], [0.3, 0.35, 1]])
        Q, Z = Qbar.copy(), np.empty((T, 3))
        for t in range(T):
            d = np.sqrt(np.diag(Q))
            Z[t] = np.linalg.cholesky(Q / np.outer(d, d)) @ rng.standard_normal(3)
            Q = (1 - a0 - b0) * Qbar + a0 * np.outer(Z[t], Z[t]) + b0 * Q
        R = 0.01 * Z
        G = PM._garch_many(R)
        D = PM.dcc_fit(G['z'])
        self.assertGreater(D['a'] + D['b'], 0.8)
        self.assertAlmostEqual(D['a'], a0, delta=0.03)
        self.assertLess(D['a'] + D['b'], 0.999)
        P = PM.simulate(R, 'dcc_garch', horizon=30, n=300, seed=0)
        self.assertTrue(np.isfinite(P).all())
        flat = 0.01 * mv_t(1500, equicorr(3, 0.4), None, rng)              # constant correlation: no dynamics
        self.assertLess(PM.dcc_fit(PM._garch_many(flat)['z'])['a'], 0.03)


class Factor(unittest.TestCase):
    def test_stocks_co_move_only_through_the_factors(self):
        rng = np.random.default_rng(2)
        T = 756
        m = rng.standard_normal(T) * 0.01
        s = 0.5 * m + rng.standard_normal(T) * 0.006
        common = rng.standard_normal(T) * 0.008                            # shared, but not a factor
        a = 1.1 * m + 0.5 * s + common + rng.standard_normal(T) * 0.006
        b = 0.9 * m + 0.3 * s + common + rng.standard_normal(T) * 0.006
        R = np.column_stack([a, m, s, b])
        F = PM.factor_fit(R)
        self.assertEqual((F['factors'], F['others']), ([1, 2], [0, 3]))
        B, E, Sf = F['coef'][1:], F['resid'], np.cov(R[:, [1, 2]].T)
        cov = B[:, 0] @ Sf @ B[:, 1]
        implied = cov / math.sqrt((B[:, 0] @ Sf @ B[:, 0] + E[:, 0].var()) * (B[:, 1] @ Sf @ B[:, 1] + E[:, 1].var()))
        d = daily(PM.simulate(R, 'factor', horizon=63, n=1000, seed=0)).reshape(-1, 4)
        sim = np.corrcoef(d[:, 0], d[:, 3])[0, 1]
        self.assertAlmostEqual(sim, implied, delta=0.03)
        self.assertLess(sim, np.corrcoef(a, b)[0, 1] - 0.15)               # the shared non-factor part is gone
        self.assertTrue(all_past_rows(d[:2000, [1, 2]], R[:, [1, 2]]))    # factors: whole past rows
        np.testing.assert_allclose(F['coef'][1:, 0], [1.1, 0.5], atol=0.15)


class Summaries(unittest.TestCase):
    def test_summarize_by_hand(self):
        P = np.log(np.array([[1.00, 0.85, 0.95], [1.10, 1.20, 1.25], [0.95, 0.90, 0.78], [1.02, 1.04, 1.06]]))[:, :, None]
        s = PM.summarize(P, 100.0, qs=(0.25, 0.5, 0.75))
        self.assertEqual(len(s['q']), 3)
        self.assertEqual(s['q'][2][1], round(float(np.median([95, 125, 78, 106])), 2))
        self.assertEqual(set(s['end']), {'p25', 'p50', 'p75', 'mean'})
        self.assertAlmostEqual(s['end']['mean'], 101.0)
        self.assertEqual((s['p_down10'], s['p_up10'], s['p_down20'], s['p_up20']), (0.25, 0.25, 0.25, 0.25))
        self.assertEqual(s['p_touch_down10'], 0.5)                         # paths 1 (85) and 3 (78)
        mdd = sorted([0.15, 0.0, 1 - 78 / 100, 0.0])                       # running peak includes price0
        self.assertAlmostEqual(s['mdd']['p50'], float(np.quantile(mdd, 0.5)), places=4)
        self.assertAlmostEqual(s['mdd']['p90'], float(np.quantile(mdd, 0.9)), places=4)
        self.assertIsNone(PM.summarize(P, 0.0))

    def test_summarize_on_a_simulation(self):
        R = PM._demo_returns(500, 4, seed=1)
        P = PM.simulate(R, 'joint_bootstrap', horizon=63, n=1000, seed=0)
        s = PM.summarize(P, 123.45)
        self.assertEqual(len(s['q']), 63)
        self.assertTrue(all(len(row) == 7 and row == sorted(row) for row in s['q']))
        self.assertEqual(list(s['end']), ['p05', 'p10', 'p25', 'p50', 'p75', 'p90', 'p95', 'mean'])
        self.assertEqual(s['q'][-1][3], s['end']['p50'])
        for k in ('p_down10', 'p_up10', 'p_down20', 'p_up20', 'p_touch_down10'):
            self.assertTrue(0 <= s[k] <= 1, k)
        self.assertLessEqual(s['p_down20'], s['p_down10'])
        self.assertGreaterEqual(s['p_touch_down10'], s['p_down10'])        # ending below implies touching
        self.assertTrue(0 <= s['mdd']['p50'] <= s['mdd']['p90'] < 1)
        self.assertAlmostEqual(s['vol'], R[:, 0].std() * math.sqrt(252), delta=0.03)
        self.assertEqual(s['end']['p95'], float(f"{s['end']['p95']:.4g}"))   # 4 significant digits
        self.assertNotIn('NaN', json.dumps(s))

    def test_joint_and_sample_paths(self):
        rng = np.random.default_rng(0)
        x = rng.standard_normal(1000) * 0.15
        P = np.stack([np.stack([x, x], 1)] * 2, 1)                         # (1000, 2, 2): identical assets
        j = PM.joint(P, 0, 1)
        self.assertEqual(j['p_a_given_b'], 1.0)
        self.assertAlmostEqual(j['corr'], 1.0)
        self.assertAlmostEqual(j['tail_corr'], 1.0)
        self.assertAlmostEqual(j['p_a'], float(np.mean(x < -0.10)), places=4)
        Q = P.copy()
        Q[:, :, 0] = rng.standard_normal((1000, 1)) * 0.15                  # independent
        j = PM.joint(Q, 0, 1)
        self.assertAlmostEqual(j['p_a_given_b'], j['p_a'], delta=0.08)
        self.assertLess(abs(j['corr']), 0.1)
        self.assertIsNone(PM.joint(P[:30], 0, 1)['p_a_given_b'])           # fewer than 20 such paths
        S = PM.simulate(PM._demo_returns(300, 3, seed=2), 'cholesky', horizon=20, n=500, seed=0)
        sp = PM.sample_paths(S, 50.0, k=40, seed=3)
        self.assertEqual(len(sp), 40)
        self.assertTrue(all(len(p) == 20 for p in sp))
        ends = [p[-1] for p in sp]
        self.assertEqual(ends, sorted(ends))
        fin = np.sort(50.0 * np.exp(S[:, -1, 0]))
        self.assertLess(ends[0], fin[int(0.03 * 500)])                     # spread over the whole distribution
        self.assertGreater(ends[-1], fin[int(0.97 * 500)])
        self.assertEqual(sp, PM.sample_paths(S, 50.0, k=40, seed=3))
        self.assertEqual(len(PM.sample_paths(S[:10], 50.0, k=40)), 10)


class WalkForward(unittest.TestCase):
    def test_coverage_of_the_right_model_on_its_own_data(self):
        rng = np.random.default_rng(100)
        window, h, k = 252, 10, 300                                        # 300 non-overlapping 10-day outcomes
        T = window + h * k
        R = rng.standard_normal((T, 2)) * np.array([0.015, 0.01]) + 0.0003
        origins = list(range(window, T - h + 1, h)) + [10, T]              # the last two cannot be scored
        for res in (PM.evaluate(R, 'cholesky', origins, horizon=h, window=window, n=400, seed=0),
                    PM.naive_normal(R, origins, horizon=h, window=window, n=400, seed=0)):
            self.assertEqual(res['n'], k)
            self.assertAlmostEqual(res['cover80'], 0.8, delta=0.08)
            self.assertAlmostEqual(res['cover50'], 0.5, delta=0.08)
            self.assertEqual(len(res['pit']), k)
            self.assertTrue(all(0 <= p <= 1 for p in res['pit']))
            self.assertAlmostEqual(float(np.mean(res['pit'])), 0.5, delta=0.05)
            self.assertLess(np.histogram(res['pit'], bins=5, range=(0, 1))[0].max(), 0.3 * k)      # roughly uniform
            self.assertAlmostEqual(res['width80'], 2 * 1.2816 * 0.015 * math.sqrt(h), delta=0.01)
            self.assertGreater(res['pinball'], 0)

    def test_no_look_ahead_and_every_model_scored(self):
        R = PM._demo_returns(330, 4, seed=5)
        origins = [200, 250, 280]
        a = PM.evaluate(R, 'fhs', origins, horizon=20, window=150, n=200, seed=1)
        R2 = R.copy()
        R2[300:] *= 5                                                      # after the last origin + horizon
        R2[:50] = 0.0                                                      # before the first window
        self.assertEqual(a, PM.evaluate(R2, 'fhs', origins, horizon=20, window=150, n=200, seed=1))
        allm = PM.evaluate_all(R, origins, horizon=20, window=150, n=200, seed=1)
        self.assertEqual(list(allm), PM.MODELS + ['naive_normal'])
        for name, res in allm.items():
            self.assertEqual(res['n'], 3, name)
            self.assertTrue(0 <= res['cover80'] <= 1 and res['pinball'] > 0 and res['width80'] > 0, name)
        self.assertEqual(allm['fhs'], {**a})
        self.assertEqual(PM.evaluate(R, 'cholesky', [5, 400], horizon=20, window=150)['n'], 0)

    def test_full_run_is_fast(self):
        t = PM.benchmark(T=756, N=5, n=1000, horizon=63)
        print(f"\n  all 7 models, T=756 N=5 n=1000 horizon=63: {t['total']:.2f} s "
              + ' · '.join(f'{m} {t[m] * 1000:.0f} ms' for m in PM.MODELS))
        self.assertLess(t['total'], 3.0)


if __name__ == '__main__':
    unittest.main()
