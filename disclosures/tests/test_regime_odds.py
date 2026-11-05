"""regime_odds.py: the fixed bands, the fan, the dates of the pooled days and the walk-forward test of the similar-days
odds — which may only learn from days whose outcome was known before the year it predicts."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import regime_odds as RO


class Pieces(unittest.TestCase):
    def test_hist(self):
        self.assertEqual(RO.hist([-0.5, -0.1, 0, 0.05, 0.3, np.nan], [-0.2, 0, 0.1]), [1, 1, 2, 1])   # [e, next) bands; NaN left out

    def test_fan(self):
        closes = [np.arange(1, 501, dtype=np.float32), np.full(260, 10.0, np.float32)]
        F = RO.fan(closes, [0] * 20 + [1] * 40, list(range(20)) + list(range(40)))
        self.assertEqual(F['p50'][0], 0.0)
        self.assertEqual(F['n'][0], 60)
        self.assertEqual(F['n'][-1], 28, 'a year on: the first asset\'s 20 days and 8 of the second\'s')
        self.assertGreater(F['p90'][10], F['p10'][10])
        self.assertIsNone(F['p50'][-1], 'only the first asset reaches a year on: under MIN_FAN days')
        self.assertIsNone(RO.fan(closes, [], []))

    def test_day_index(self):
        days = [['2020-01-02', '2020-01-03', '2020-01-06'], ['2021-05-03', '2021-05-04']]
        d = RO.day_index(days, [0, 0, 1], [0, 2, 1])
        self.assertEqual(list(d), [int(np.datetime64(x, 'D').astype(int)) for x in ('2020-01-02', '2020-01-06', '2021-05-04')])
        later = RO.day_index(days, [0, 0], [0, 2], lag=1)
        self.assertEqual(int(later[0]), int(np.datetime64('2020-01-03', 'D').astype(int)))
        self.assertGreater(int(later[1]), 10 ** 6, 'past the end of its data: not known yet')

    def test_score_and_verdict(self):
        rng = np.random.default_rng(1)
        y = (rng.random(4000) < 0.5).astype(float)
        p = np.clip(0.5 + 0.3 * (y - 0.5) + rng.normal(0, 0.1, 4000), 0, 1)
        s = RO.score(p, np.full(4000, 0.5), y)
        self.assertGreater(s['skill'], 0.05)
        self.assertGreater(s['auc'], 0.7)
        self.assertEqual(len(s['calibration']), 10)
        self.assertEqual(RO.verdict(0.03), 'useful')
        self.assertEqual(RO.verdict(0.001), 'none')
        self.assertIsNone(RO.score(p[:50], p[:50], y[:50]), 'too few days to score')


class WalkForward(unittest.TestCase):
    def test_learns_only_from_what_was_known(self):
        # 120 assets, a day every 5 trading days from 2000 to 2016; one condition f. Until 2010 it says nothing about the
        # 3-month outcome; from 2011 a day with a high f rises far more often. A test that peeked would see it early.
        rng = np.random.default_rng(2)
        bdays = np.arange(np.datetime64('2000-01-03'), np.datetime64('2017-01-01'))
        bdays = bdays[np.is_busday(bdays)]
        days = [[str(d) for d in bdays]] * 120
        T = np.arange(0, len(bdays) - 300, 5)
        A = np.repeat(np.arange(120), len(T))
        TT = np.tile(T, 120)
        f = rng.random(len(A))
        yr = bdays[TT].astype('datetime64[Y]').astype(int) + 1970
        p_up = np.where(yr >= 2011, 0.15 + 0.7 * f, 0.5)
        up = (rng.random(len(A)) < p_up).astype(float)
        R = {'asset': A.astype(np.int32), 't': TT.astype(np.int32), 'f': f}
        bt = RO.walk_forward(R, np.ones(len(A), bool), ['f'], lambda k, v: np.asarray(v, float) / 0.1, {'up63': up}, np.where(up > 0, 0.05, -0.05),
                             RO.day_index(days, A, TT), RO.day_index(days, A, TT, lag=RO.LAG), per_year=120, pool_max=20000)
        by = {r[0]: r[2] for r in bt['outcomes']['up63']['by_year']}
        self.assertGreaterEqual(bt['years'][0], 2003, 'three years of known outcomes first')
        self.assertLess(max(by[y] for y in (2011, 2012)), 0.01, "2011–12 are predicted from days known before them: the change cannot be seen yet")
        self.assertGreater(by[2015], 0.04, 'once the new days are known, the odds gain skill (diluted by the older pooled days)')
        self.assertGreater(by[2015], max(by[y] for y in (2011, 2012)) + 0.04)
        self.assertEqual(len(bt['outcomes']['up63']['calibration']), 10)


if __name__ == '__main__':
    unittest.main()
