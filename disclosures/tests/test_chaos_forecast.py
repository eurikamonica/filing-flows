"""chaos_forecast.py: no look-ahead, the calibration's fallbacks, the price decode and the exact RRG inversion."""
import math, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
try:
    import numpy as np
    import sklearn  # noqa: F401
    import chaos_forecast as CF
    import gravity_pendulum as GP
except ImportError:                                   # the hub's other tests need neither
    np = None


def synthetic_panel(E=40, T=36, seed=0):
    """Damped rotation (a noisy oscillator) per company, around sector suns, plus one coordinate filed a period late."""
    rng = np.random.default_rng(seed)
    vars_ = ['rel', 'vola', 'dom']
    U = np.full((E, T, 3), np.nan)
    th = rng.uniform(0, 2 * np.pi, E); r = rng.uniform(1, 3, E)
    for t in range(T):
        th += 0.6
        r = 0.9 * r + 0.3 + rng.normal(0, .1, E)
        U[:, t, 0] = r * np.cos(th) + rng.normal(0, .3, E)
        U[:, t, 1] = 20 + r * np.sin(th) + rng.normal(0, .3, E)
        U[:, t, 2] = np.sin(th + .5) + rng.normal(0, .2, E)
    cals = [f'CY{2010 + i // 4}Q{i % 4 + 1}' for i in range(T)]
    tickers = [f'T{i}' for i in range(E)]
    meta = {t: {'s': 'a' if i % 2 else 'b', 'rev': 1e9, 'n': t} for i, t in enumerate(tickers)}
    sectors = ['a', 'b']
    SUN = np.stack([CF.weighted_centre(U[[i for i in range(E) if meta[tickers[i]]['s'] == s]], [1e9] * (E // 2), vars_) for s in sectors])
    MKT = CF.weighted_centre(U, [1e9] * E, vars_)
    P = CF.Panel('q', cals, vars_, tickers, meta, sectors, {'a': 'A', 'b': 'B'}, U, SUN, MKT)
    return P


@unittest.skipIf(np is None, 'numpy / scikit-learn not installed')
class NoLookAhead(unittest.TestCase):
    def test_library_only_holds_published_outcomes(self):
        P = synthetic_panel()
        planet, _ = P.layers()
        L = CF.Layer(planet, P.lag, ['rel', 'vola', 'dom'], P.vars, 12, m=2, k=10)
        for t in (12, 20, 30):
            e, s, Z, D = L.library(t)
            self.assertTrue((s <= t - 1).all())
            j = P.vars.index('dom')                  # filed a period later: its outcome at s+1 is public at s+2
            self.assertTrue(np.isnan(D[s == t - 1, j]).all())

    def test_forecast_ignores_the_future(self):
        P = synthetic_panel()
        t = 24
        R1 = CF.run_panel(P, ['rel', 'vola', 'dom'], P.vars, 12, m=2, k=10, surrogate=False, verbose=False)
        r1 = next(r for r in R1['recs'] if r['t'] == t)
        P2 = synthetic_panel()
        rng = np.random.default_rng(9)
        P2.U[:, t + 1:] += rng.normal(0, 5, P2.U[:, t + 1:].shape)    # rewrite everything after the origin
        P2.SUN[:, t + 1:] += 3; P2.MKT[t + 1:] -= 2
        R2 = CF.run_panel(P2, ['rel', 'vola', 'dom'], P2.vars, 12, m=2, k=10, surrogate=False, verbose=False)
        r2 = next(r for r in R2['recs'] if r['t'] == t)
        for key in ('delta', 'spread', 'lam'):
            np.testing.assert_array_equal(r1['fp'][key], r2['fp'][key])
        np.testing.assert_array_equal(r1['dP_cal'], r2['dP_cal'])
        np.testing.assert_array_equal(r1['lin'], r2['lin'])

    def test_info_set_lags_filed_coordinates(self):
        X = np.arange(12, dtype=float).reshape(1, 4, 3)
        K = CF.info_set(X, np.array([0, 0, 1]))
        np.testing.assert_array_equal(K[0, :, 0], X[0, :, 0])
        self.assertTrue(np.isnan(K[0, 0, 2]))
        np.testing.assert_array_equal(K[0, 1:, 2], X[0, :-1, 2])


@unittest.skipIf(np is None, 'numpy / scikit-learn not installed')
class Calibration(unittest.TestCase):
    def test_no_history_means_stay_put(self):
        c = CF.Calibrator(2)
        self.assertIsNone(c.fit(5))
        step = CF.Calibrator.apply(None, np.zeros(3), np.ones((3, 2)), np.ones((3, 2)))
        np.testing.assert_array_equal(step, np.zeros((3, 2)))

    def test_learns_to_fall_back_to_the_centre_when_steps_are_noise(self):
        rng = np.random.default_rng(1)
        c = CF.Calibrator(1, min_n=50)
        for t in range(20):
            K = rng.normal(0, 1, (50, 1)); step = rng.normal(0, 1, (50, 1)); actual = -K + rng.normal(0, .1, (50, 1))
            c.add(t, np.array([0]), rng.normal(0, 1, 50), K, step, actual)
        cuts, coef = c.fit(30)
        self.assertTrue(np.all(np.abs(coef[:, 0, 0] + coef[:, 0, 1]) < 0.2))   # landing ~ 0: the sun

    def test_dynamics_are_learnt_on_the_oscillator(self):
        P = synthetic_panel(E=80, T=48)
        R = CF.run_panel(P, ['rel', 'vola'], P.vars, 16, m=2, k=20, verbose=False)
        ev = CF.evaluate(R)
        self.assertGreater(ev['summary']['analog_cal']['arrow_hit'], 0.6)
        self.assertLess(abs(ev['summary']['surrogate']['arrow_hit'] - 0.5), 0.15)


@unittest.skipIf(np is None, 'numpy / scikit-learn not installed')
class RRG(unittest.TestCase):
    def rs(self, n=400, seed=3):
        rng = np.random.default_rng(seed)
        return 100 * np.exp(np.cumsum(rng.normal(0, .02, n)) + .1 * np.sin(np.arange(n) / 9))

    def test_stepper_equals_full_recompute(self):
        rs = self.rs(); S = CF.rrg_series(rs, 14)
        for i in range(120, 398, 31):
            p = CF.RRGStepper(S, i).points([rs[i + 1]])[0]
            self.assertAlmostEqual(p[0], S['x'][i + 1], places=9)
            self.assertAlmostEqual(p[1], S['y'][i + 1], places=9)

    def test_inversion_recovers_the_actual_close(self):
        rs = self.rs(); S = CF.rrg_series(rs, 14)
        for i in (150, 260, 390):
            target = (S['x'][i + 1], S['y'][i + 1])
            r, _, _ = CF.RRGStepper(S, i).invert(target, (1, 1), rs[i], grid=4001)
            self.assertAlmostEqual(r, math.log(rs[i + 1] / rs[i]), delta=2e-4)


@unittest.skipIf(np is None, 'numpy / scikit-learn not installed')
class Helpers(unittest.TestCase):
    def test_calendar(self):
        self.assertEqual(str(CF.cal_end('CY2026Q3')), '2026-09-30')
        self.assertEqual(str(CF.cal_end('2024-02')), '2024-02-29')
        self.assertEqual(CF.next_cal('CY2026Q4'), 'CY2027Q1')
        self.assertEqual(CF.next_cal('2026-12'), '2027-01')

    def test_close_at_takes_the_last_friday_on_or_before(self):
        days = np.datetime64('2026-09-04') + 7 * np.arange(6)
        c = np.array([1, 2, 3, 4, np.nan, 6.])
        self.assertEqual(CF.close_at((days, c), '2026-09-30')[0], 4.0)     # Oct 2 is after; Sep 25 is 4
        self.assertTrue(np.isnan(CF.close_at((days, c), '2026-08-01')[0]))


if __name__ == '__main__':
    unittest.main()


@unittest.skipIf(np is None, 'numpy / scikit-learn not installed')
class GravityModel(unittest.TestCase):
    def synthetic(self, seed=0, N=90, W=420):
        rng = np.random.default_rng(seed)
        days = np.datetime64('2010-01-01') + 7 * np.arange(W)
        sec = np.array(list('abcdef') * (N // 6))
        sect = {s: np.cumsum(rng.normal(0, .02, W)) for s in 'abcdef'}
        mkt = np.cumsum(rng.normal(.001, .02, W))
        C = np.array([50 * np.exp(mkt + sect[s] + np.cumsum(rng.normal(0, .03, W))) for s in sec])
        V = np.full_like(C, 1e6)
        bodies = {b: 30 * np.exp(np.cumsum(rng.normal(0, .02, W))) for b in GP.BODIES}
        return {'days': days, 'tick': np.array([f'T{i}' for i in range(N)]), 'sec': sec, 'rev': np.full(N, 1e9), 'C': C, 'V': V,
                'spy': 100 * np.exp(mkt), 'bodies': bodies}

    def test_predictions_ignore_the_future(self):
        D1 = self.synthetic(); w = 392
        B1 = GP.build(D1)
        p1 = GP.predict_satellites(B1, D1, 4, [w]); q1 = GP.predict_planets(B1, D1, 4, [w])
        D2 = self.synthetic()
        rng = np.random.default_rng(5)
        D2['C'][:, w + 1:] *= np.exp(rng.normal(0, .3, D2['C'][:, w + 1:].shape))     # rewrite every price after week w
        D2['spy'][w + 1:] *= 1.3
        B2 = GP.build(D2)
        p2 = GP.predict_satellites(B2, D2, 4, [w]); q2 = GP.predict_planets(B2, D2, 4, [w])
        np.testing.assert_array_equal(p1[w][0], p2[w][0]); np.testing.assert_allclose(p1[w][1], p2[w][1], rtol=0, atol=1e-12)
        np.testing.assert_allclose(q1[w][1], q2[w][1], rtol=0, atol=1e-12)

    def test_position_is_relative_to_the_sector_without_the_company(self):
        D = self.synthetic(); B = GP.build(D)
        r = GP.logret(D['C'])
        i, t = 4, 50
        same = np.nonzero((D['sec'] == D['sec'][i]) & (np.arange(len(D['sec'])) != i))[0]
        self.assertAlmostEqual(B['sat_r'][i, t], r[i, t] - r[same, t].mean(), places=10)
