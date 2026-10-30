"""odds.py: the scoring (AUC, calibration card), the logistic fit and the walk-forward split, the first-passage odds,
the hidden Markov model, the recession months and the yield-curve probit, dividend cuts, the S&P 500 membership guard
and the frozen ledger."""
import json
import math
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import odds as O
import strategies as S

warnings.filterwarnings('ignore', category=RuntimeWarning)


class Scoring(unittest.TestCase):
    def test_auc_and_card(self):
        self.assertAlmostEqual(O.auc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]), 1.0)
        self.assertAlmostEqual(O.auc([0.5, 0.5, 0.5, 0.5], [0, 1, 0, 1]), 0.5)
        rng = np.random.default_rng(0)
        p = rng.uniform(0, 1, 20000)
        y = (rng.uniform(0, 1, 20000) < p).astype(float)              # perfectly calibrated
        c = O.card(p, y)
        self.assertGreater(c['skill'], 0.2)
        for pred, obs, n in c['calib']:
            self.assertAlmostEqual(pred, obs, delta=0.04)
        self.assertIsNone(O.card(p[:10], y[:10]))

    def test_logit_and_walk_forward(self):
        rng = np.random.default_rng(1)
        X = rng.normal(size=(6000, 2))
        y = (rng.uniform(size=6000) < 1 / (1 + np.exp(-(0.5 + 2 * X[:, 0])))).astype(float)
        m = O.logit_fit(X, y, 0.0)
        self.assertAlmostEqual(m[2][1] / m[1][0], 2.0, delta=0.25)      # the slope on the raw scale
        years = np.repeat(np.arange(2000, 2006), 1000)
        p, clim = O.walk_forward(years, X, y, years, 2001)
        self.assertTrue(np.isnan(p[years == 2000]).all())               # nothing before the first year with training
        self.assertTrue(np.isfinite(p[years == 2003]).all())
        y2 = y.copy(); y2[years == 2003] = 1 - y2[years == 2003]       # change a year's outcomes: its odds do not move
        p2, _ = O.walk_forward(years, X, y2, years, 2001)
        np.testing.assert_allclose(p[years <= 2003], p2[years <= 2003])


class Models(unittest.TestCase):
    def test_touch_odds(self):
        sw = np.array([0.02, 0.05])
        p = O.touch_p0(sw, 13, -0.2)
        self.assertTrue((p > 0).all() and (p <= 1).all() and p[1] > p[0])   # more volatile, likelier
        rng = np.random.default_rng(2)
        hits = 0
        for _ in range(4000):                                          # a weekly random walk: the formula is close
            path = np.cumsum(rng.normal(0, 0.05, 13))
            hits += path.min() <= math.log(0.8)
        self.assertAlmostEqual(float(O.touch_p0(np.array([0.05]), 13, -0.2)[0]), hits / 4000, delta=0.04)

    def test_hmm_finds_two_volatilities(self):
        rng = np.random.default_rng(3)
        x = np.concatenate([rng.normal(0.003, 0.01, 300), rng.normal(-0.004, 0.04, 100), rng.normal(0.003, 0.01, 300)])
        P = O.hmm_fit(x, iters=60)
        self.assertLess(P[3][0], P[3][1])                               # state 1 is the stressed one
        f = O.hmm_filter(x, P)
        self.assertGreater(f[350:395, 1].mean(), 0.8)
        self.assertLess(f[600:, 1].mean(), 0.2)
        self.assertGreater(O.hmm_down(f[380], P), O.hmm_down(f[650], P))

    def test_recession_months_and_probit(self):
        rec = O.recession_months()
        self.assertIn(O._ym('2008-12'), rec)
        self.assertNotIn(O._ym('2007-12'), rec)                         # the peak month itself is not a recession month
        self.assertIn(O._ym('2020-04'), rec)
        self.assertAlmostEqual(O.norm_cdf(O.NYFED[0] + O.NYFED[1] * 0.0), O.norm_cdf(-0.5333), places=6)
        self.assertGreater(O.norm_cdf(O.NYFED[0] + O.NYFED[1] * -1.0), 0.5)   # an inverted curve: odds above a half

    def test_dividend_cuts(self):
        T = 200
        div = np.zeros(T)
        for w in range(5, 100, 13):
            div[w] = 0.50
        div[109] = 0.25                                                # halved
        for w in range(122, 160, 13):
            div[w] = 0.25
        div[161] = 3.0                                                 # a special: not a cut afterwards
        alive = np.ones(T, dtype=bool)
        pay, cuts = O.dividend_events(div, alive)
        self.assertIn(109, cuts)
        self.assertEqual([c for c in cuts if c < 160], [109])
        self.assertTrue(any(c > 161 for c in cuts))                    # then nothing for long: a skip

    def test_mass_removal_is_a_source_change(self):
        rows = {f'T{k}': {'was': {'sp500': [['2010-01-01', '2026-10-01']]}} for k in range(12)}
        rows['ONE'] = {'was': {'sp500': [['2010-01-01', '2020-05-01']]}}
        iv = O.sp500_intervals({'generated_at': '2026-10-30T00:00:00+00:00', 'rows': rows})
        self.assertIsNone(iv['T0'][0][1])                              # twelve "left" together last month: still members
        self.assertEqual(str(iv['ONE'][0][1]), '2020-05-01')
        self.assertIn('2026-10-01', O.mass_removals({'generated_at': '2026-10-30', 'rows': rows}))

    def test_foreign_and_partnerships(self):
        f = O.foreign_issuers({'companies': [{'ticker': 'TSM', 'form': '20-F'}, {'ticker': 'EPD', 'form': '10-K', 'name': 'Enterprise Products Partners L.P.'},
                                             {'ticker': 'AAPL', 'form': '10-Q', 'name': 'Apple Inc.'}, {'ticker': 'ET', 'form': '10-K', 'name': 'Energy Transfer LP'}]})
        self.assertEqual(f, {'TSM', 'EPD', 'ET'})


class Ledger(unittest.TestCase):
    def test_freeze_once_and_score(self):
        T = 120
        rng = np.random.default_rng(4)
        C = 100 * np.cumprod(1 + rng.normal(0, 0.06, (3, T)), axis=1)
        dates = np.datetime64('2020-01-03') + np.arange(T) * S.WEEK
        D = {'tickers': ['SPY', 'AAA', 'BBB'], 'ix': {'SPY': 0, 'AAA': 1, 'BBB': 2}, 'dates': dates, 'C': C, 'PS': C, 't_end': 100,
             'is_etf': np.array([True, False, False])}
        fields = O.LEDGER_STOCK
        rows = {'AAA': [0.9, 0.1, 0.5, None, None], 'BBB': [0.1, 0.9, 0.5, None, None]}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'l.json'
            made = str(dates[100]) + 'T20:00:00+00:00'
            L, _ = O.ledger_update(p, D, fields, rows, {'p_down13': 0.4}, made_at=made)
            L, _ = O.ledger_update(p, D, fields, rows, {'p_down13': 0.4}, made_at=made)
            self.assertEqual(len(L['weeks']), 1)
            self.assertEqual(L['weeks'][0]['p']['dn20_13'], [900, 100])
            D['t_end'] = 119                                           # 19 weeks later: the 13-week odds are scored
            sc = O.ledger_score(L, D)
            self.assertEqual(sc['weeks'], 1)
            self.assertEqual(sc['cards'], {})                          # two cases: too few for a card


if __name__ == '__main__':
    unittest.main()
