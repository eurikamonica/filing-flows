"""macro_history.py: every value is placed at its publication date, and the macro-clock forecast never uses the future."""
import datetime as dt, json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
try:
    import numpy as np
    import macro_history as M
except ImportError:
    np = None


def monthly(n=400, start=(1993, 1), f=lambda i: 100 + i):
    y, m = start; out = []
    for i in range(n):
        out.append((dt.date(y, m, 1), float(f(i))))
        y, m = y + (m == 12), m % 12 + 1
    return out


@unittest.skipIf(np is None, 'numpy not installed')
class Publication(unittest.TestCase):
    def test_monthly_value_appears_only_after_release(self):
        obs = [(dt.date(2020, 1, 1), 1.0), (dt.date(2020, 2, 1), 2.0)]
        v = M.as_of(obs, 'm', 15, [dt.date(2020, 2, 14), dt.date(2020, 2, 15), dt.date(2020, 3, 14), dt.date(2020, 3, 16)])
        self.assertTrue(np.isnan(v[0]))
        self.assertEqual(list(v[1:]), [1.0, 1.0, 2.0])

    def test_daily_and_weekly_lags(self):
        d = [(dt.date(2021, 1, 4), 5.0)]                      # a Monday close
        self.assertTrue(np.isnan(M.as_of(d, 'd', 1, [dt.date(2021, 1, 4)])[0]))
        self.assertEqual(M.as_of(d, 'd', 1, [dt.date(2021, 1, 5)])[0], 5.0)
        w = [(dt.date(2021, 1, 9), 7.0)]                      # claims for the week ending Saturday, out Thursday
        self.assertTrue(np.isnan(M.as_of(w, 'w', 5, [dt.date(2021, 1, 13)])[0]))
        self.assertEqual(M.as_of(w, 'w', 5, [dt.date(2021, 1, 14)])[0], 7.0)

    def test_stale_series_stops(self):
        d = [(dt.date(2010, 1, 1), 1.0)]
        self.assertTrue(np.isnan(M.as_of(d, 'd', 1, [dt.date(2012, 1, 1)])[0]))

    def test_year_on_year_on_the_known_basis(self):
        raw = {'CPIAUCSL': monthly(f=lambda i: 100 * 1.02 ** (i / 12))}
        days = [dt.date(2015, 6, 30)]
        F = M.features(raw, days)
        self.assertAlmostEqual(F['cpi'][0], 2.0, delta=0.05)

    def test_future_data_does_not_change_the_past(self):
        base = {sid: monthly(f=lambda i, k=k: 100 + 5 * np.sin(i / (6 + k)) + i * .1) for k, sid in enumerate(M.SERIES)}
        days = M.month_ends(dt.date(1995, 1, 1), dt.date(2016, 12, 31))
        F1 = M.features(base, days)
        changed = {sid: [(d, v * (3 if d >= dt.date(2016, 1, 1) else 1)) for d, v in obs] for sid, obs in base.items()}
        F2 = M.features(changed, days)
        k = next(i for i, d in enumerate(days) if d >= dt.date(2015, 12, 1))
        for key in F1:
            np.testing.assert_allclose(F1[key][:k], F2[key][:k], equal_nan=True)
        C1, C2 = M.clock(F1, days, '2010-01'), M.clock(F2, days, '2010-01')
        k2 = C1['months'].index('2015-11')
        self.assertEqual(C1['growth_mom'][:k2], C2['growth_mom'][:k2])
        f1 = [r for r in C1['forecast'] if r[0] < k2]; f2 = [r for r in C2['forecast'] if r[0] < k2]
        self.assertEqual(f1, f2)
        self.assertTrue(f1)


@unittest.skipIf(np is None, 'numpy not installed')
class Clock(unittest.TestCase):
    def test_phases(self):
        self.assertEqual([M.phase_of(1, -1), M.phase_of(1, 1), M.phase_of(-1, 1), M.phase_of(-1, -1)], [0, 1, 2, 3])
        self.assertIsNone(M.phase_of(float('nan'), 1))

    def test_expanding_z_uses_the_past_only(self):
        x = np.arange(100, dtype=float)
        z = M.expanding_z(x, min_n=10)
        x2 = x.copy(); x2[60:] = 1e6
        np.testing.assert_allclose(z[:60], M.expanding_z(x2, min_n=10)[:60], equal_nan=True)

    def test_build_writes_macro_json(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / 'cache' / 'macro'; folder.mkdir(parents=True)
            for k, sid in enumerate(M.SERIES):
                rows = monthly(f=lambda i, k=k: 100 + 5 * np.sin(i / (5 + k)) + i * .05)
                folder.joinpath(f'{sid}.csv').write_text('observation_date,' + sid + '\n' + '\n'.join(f'{a},{b}' for a, b in rows))
            doc = M.build(d, today=dt.date(2026, 10, 16), verbose=False)
            self.assertEqual(doc['clock']['months'][0], '2010-01')
            self.assertTrue(doc['clock']['forecast'])
            w0, X = M.weekly_matrix(doc)
            self.assertEqual(w0, (dt.date.fromisoformat(doc['weekly']['start']) - M.GRID0).days // 7)
            json.loads((Path(d) / 'public' / 'macro.json').read_text())


if __name__ == '__main__':
    unittest.main()
