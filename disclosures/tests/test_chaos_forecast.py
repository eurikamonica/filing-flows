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

    def test_planet_weights_use_revenue_reported_by_then(self):
        D1 = self.synthetic(); w = 300
        rng = np.random.default_rng(9)
        D1['rev_t'] = np.repeat(rng.uniform(1e8, 1e11, len(D1['tick']))[:, None], len(D1['days']), axis=1)
        D2 = {**D1, 'rev_t': D1['rev_t'].copy()}
        D2['rev_t'][:, w + 1:] = rng.uniform(1e6, 1e13, D2['rev_t'][:, w + 1:].shape)   # later revenue figures change
        B1, B2 = GP.build(D1), GP.build(D2)
        np.testing.assert_array_equal(B1['sat_r'][:, :w + 1], B2['sat_r'][:, :w + 1])
        self.assertFalse(np.allclose(np.nan_to_num(B1['sat_r'][:, w + 2:]), np.nan_to_num(B2['sat_r'][:, w + 2:])))
        rows = {'T0': [['2010-03-05', 2e9], ['2011-01-07', 3e9]]}
        R = GP.revenue_by_week(D1['days'][:60], np.array(['T0', 'T1']), rows)
        self.assertTrue(np.isnan(R[0, 8]) and R[0, 9] == 2e9 and R[0, 53] == 3e9 and np.isnan(R[1]).all())

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

@unittest.skipIf(np is None, 'numpy / scikit-learn not installed')
class RRGBands(unittest.TestCase):
    def test_band_uses_only_errors_already_known(self):
        g0 = np.datetime64('2000-01-07')
        W = 120; d = g0 + 7 * np.arange(W)
        x = np.linspace(99, 101, W); y = np.full(W, 100.0)
        series = {'A': (d, None, x, y, None)}
        rows = [[w, x[w], y[w], x[w] + 0.5, y[w], 0, 1, 1, 0] for w in range(10, W - 1)]
        lines = {'A': [list(r) for r in rows]}
        band = CF.rrg_bands(lines, series, g0, window=260, q=80)
        first = min(band)
        self.assertGreaterEqual(first - 10, 26)            # 26 weeks of errors before the first band
        # changing an outcome after week w must not change the band at w
        x2 = x.copy(); x2[80:] += 5
        lines2 = {'A': [list(r) for r in rows]}
        band2 = CF.rrg_bands(lines2, {'A': (d, None, x2, y, None)}, g0, window=260, q=80)
        for w in band:
            if w <= 78:
                self.assertEqual(band[w], band2[w])
        self.assertEqual(len(lines['A'][0]), 11)


@unittest.skipIf(np is None, 'numpy / scikit-learn not installed')
class RRGNoLookAhead(unittest.TestCase):
    """Spec v5 §1.1: the weekly RRG analogues' metric and the benchmark drift added to the price use only weeks before
    each origin, so changing every close after week T leaves all forecasts made before T bit-identical."""

    def world(self, bump=False, seed=11, W=520, names=24):
        rng = np.random.default_rng(seed)
        d = np.datetime64('2006-01-06') + 7 * np.arange(W)
        spy = 100 * np.exp(np.cumsum(rng.normal(.001, .02, W)))
        closes = {}
        for i in range(names):
            r = rng.normal(0, .03, W) + .02 * np.sin(np.arange(W) / (6 + i % 5))
            c = spy * np.exp(np.cumsum(r))
            closes[f'T{i}'] = (d, c)
        if bump:                                     # a different future: every close after week T, benchmark included
            T = 470
            spy = spy.copy(); spy[T:] *= np.exp(np.cumsum(rng.normal(.01, .05, W - T)))
            for k, (dd, c) in list(closes.items()):
                c = c.copy(); c[T:] *= np.exp(np.cumsum(rng.normal(-.01, .06, W - T))); closes[k] = (dd, c)
        return d, closes, (d, spy)

    def test_causal_scale_and_drift(self):
        import pandas as pd
        df = pd.DataFrame({'date': np.datetime64('2020-01-03') + 7 * np.arange(6), 'x': [1., 2, 3, 4, 50, 60],
                           'y': [1., 1, 2, 2, 3, 3], 'dx': [0., 1, 1, 1, 1, 1], 'dy': [0., 1, 0, 1, 0, 1]})
        sc = CF.causal_scale(df, np.datetime64('2020-01-31'))      # the first four rows only
        self.assertAlmostEqual(sc[0], np.std([1, 2, 3, 4], ddof=1))
        d = np.datetime64('2020-01-03') + 7 * np.arange(60)
        c = 100 * np.exp(.01 * np.arange(60)); c[30:] *= 3             # a jump later on
        drift = CF.expanding_log_drift(d, c, min_n=10)
        self.assertAlmostEqual(CF.drift_at(drift, d[20]), .01, places=12)
        self.assertEqual(CF.drift_at(drift, d[5]), 0.0)                  # too few returns yet

    def test_experiment_forecasts_ignore_the_future(self):
        d, a, ba = self.world()
        _, b, bb = self.world(bump=True)
        tk = sorted(a)
        ra, ia = CF.rrg_experiment(a, ba, tk, start='2012-01-06', verbose=False)
        rb, ib = CF.rrg_experiment(b, bb, tk, start='2012-01-06', verbose=False)
        cut = str(d[470] - 14)[:10]                                    # origins whose library and inputs predate week T
        fa, fb = ra[ra.date < cut].reset_index(drop=True), rb[rb.date < cut].reset_index(drop=True)
        self.assertGreater(len(fa), 500)
        for col in ('an_x', 'an_y', 'lin_x', 'lin_y', 'r_analog_direct', 'sx', 'sy'):
            np.testing.assert_array_equal(fa[col].to_numpy(), fb[col].to_numpy(), err_msg=col)
        ga, gb = ia[ia.date < cut].reset_index(drop=True), ib[ib.date < cut].reset_index(drop=True)
        np.testing.assert_array_equal(ga['r_inverted'].to_numpy(), gb['r_inverted'].to_numpy())

    def test_site_file_lines_ignore_the_future(self):
        import json, tempfile
        out = []
        for bump in (False, True):
            d, closes, bench = self.world(bump=bump)
            with tempfile.TemporaryDirectory() as tmp:
                ser = [{'id': t, 'name': t, 'group': 'sector-etf', 'sector': 'tech', 'start': str(d[0]),
                        'c': [None if not np.isfinite(v) else float(v) for v in c]} for t, (_, c) in closes.items()]
                doc = {'start': str(d[0]), 'weeks': str(d[-1]), 'series': ser,
                       'bench': {'start': str(d[0]), 'c': [float(v) for v in bench[1]]}, 'tickers': {}}
                Path(tmp, 'rrg.json').write_text(json.dumps(doc))
                Path(tmp, 't').mkdir()
                out.append(CF.rrg_site_file(tmp, weeks_series='2010-01-01', weeks_companies=13))
        g0 = np.datetime64(out[0]['weeks'][0])
        T = int((np.datetime64(str(self.world()[0][470])) - g0).astype(int) // 7)
        checked = 0
        for line, rows in out[0]['lines'].items():
            other = {r[0]: r for r in out[1]['lines'][line]}
            for r in rows:
                if r[0] < T - 1:                                       # forecast made before week T
                    self.assertEqual(r[:9], other[r[0]][:9], (line, r[0]))
                    checked += 1
        self.assertGreater(checked, 1000)


if __name__ == '__main__':
    unittest.main()
