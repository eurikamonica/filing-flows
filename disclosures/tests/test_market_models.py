"""Market models (app/market_models.py) on synthetic weekly closes and FRED files: each model's walk-forward machinery,
no look-ahead, the calibration that falls back to the benchmark, the ledger and the published file."""
import datetime as dt
import json
import math
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

import forecast_book as FB  # noqa: E402
import market_models as MM  # noqa: E402

START = dt.date(1993, 1, 1)                                     # a Friday
W = 33 * 52


def garch_returns(rng, n, omega=2e-5, a=0.12, b=0.85):
    r, v = np.zeros(n), omega / (1 - a - b)
    for t in range(n):
        r[t] = math.sqrt(v) * rng.standard_normal()
        v = omega + a * r[t] ** 2 + b * v
    return r


def write_fixture(root, seed=3):
    """rrg.json with SPY and the funds the models read (volatility clustering, no predictable relative returns) and
    FRED csv files (VIX tracking SPY's volatility, a credit spread, the curve, the bill)."""
    rng = np.random.default_rng(seed)
    days = [START + dt.timedelta(days=7 * k) for k in range(W)]
    pub, mac = Path(root) / 'public', Path(root) / 'macro'
    pub.mkdir(parents=True)
    mac.mkdir()
    spy_r = garch_returns(rng, W) + 0.0015
    closes = {'SPY': 100 * np.exp(np.cumsum(spy_r))}
    ids = ['QQQ', 'DIA', 'MDY', 'IWM', 'IJR', 'RSP', 'IWF', 'IWD', 'EEM', 'EFA', 'TLT', 'GLD'] + [s[0] for s in MM.SECTORS]
    for k in ids:
        beta = rng.uniform(0.8, 1.3)
        closes[k] = 50 * np.exp(np.cumsum(beta * spy_r + garch_returns(rng, W, omega=4e-6)))
    series = [{'id': k, 'name': k, 'group': 'style-etf', 'start': days[0].isoformat(), 'c': [round(float(v), 4) for v in closes[k]]} for k in ids]
    doc = {'benchmark': 'SPY', 'start': days[0].isoformat(), 'weeks': days[-1].isoformat(),
           'bench': {'id': 'SPY', 'start': days[0].isoformat(), 'c': [round(float(v), 4) for v in closes['SPY']]}, 'series': series}
    (pub / 'rrg.json').write_text(json.dumps(doc))
    vol = np.sqrt(np.convolve(spy_r ** 2, np.ones(8) / 8, 'same') * 52) * 100
    daily = {'VIXCLS': 3 + 1.1 * vol, 'BAA10Y': 2 + 0.03 * vol + 0.1 * np.sin(np.arange(W) / 40), 'T10Y3M': 1 + np.sin(np.arange(W) / 90),
             'DGS3MO': np.full(W, 2.0), 'NFCI': np.sin(np.arange(W) / 60) * 0.5}
    for sid, x in daily.items():
        (mac / f'{sid}.csv').write_text('observation_date,' + sid + '\n' + '\n'.join(f'{d.isoformat()},{v:.4f}' for d, v in zip(days, x)))
    months = [dt.date(1992 + i // 12, i % 12 + 1, 1) for i in range(12 * 35)]
    (mac / 'CPIAUCSL.csv').write_text('observation_date,CPIAUCSL\n' + '\n'.join(f'{m.isoformat()},{100 * 1.002 ** i:.3f}' for i, m in enumerate(months)))
    return pub, mac, days


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.pub, cls.mac, cls.days = write_fixture(cls.tmp)
        cls.today = cls.days[-1] + dt.timedelta(days=3)
        cls.doc = MM.build(cls.pub, cls.mac, Path(cls.tmp) / 'ledger.json', None, today=cls.today, verbose=False)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)


class TestPublished(Fixture):
    def test_file_and_sections(self):
        d = json.loads((self.pub / 'market-models.json').read_text())
        for k in ('vol', 'regime', 'indices', 'sectors', 'spreads', 'market', 'ledger'):
            self.assertIn(k, d)
        self.assertEqual(d['asof'], self.days[-1].isoformat())
        self.assertEqual(len(d['indices']['rows']), 6)
        self.assertEqual(len(d['sectors']['rows']), 11)

    def test_volatility_beats_the_26_week(self):
        s = next(x for x in self.doc['vol']['scores'] if x['id'] == 'SPY' and x['h'] == 4)
        self.assertGreater(s['gain_vs_hist'], 0.0)                 # volatility clusters: HAR beats the plain 26-week
        self.assertTrue(0.7 <= s['coverage80'] <= 0.9)
        spy = next(a for a in self.doc['vol']['assets'] if a['id'] == 'SPY')
        self.assertTrue(spy['h4']['range'][0] < 0 < spy['h4']['range'][1])
        self.assertIsNotNone(spy.get('vrp'))

    def test_no_skill_falls_back_to_the_benchmark(self):
        """Relative returns here are pure noise: the published odds sit at the base rate, no rotation is forecast."""
        for key in ('indices', 'sectors'):
            for h, s in self.doc[key]['scores'].items():
                self.assertLess(abs(s['brier_skill']), 0.02, (key, h))
                self.assertLessEqual(s['beta_now'], 0.2)
        mk = self.doc['market']['h'][13]
        self.assertAlmostEqual(mk['now']['excess'], mk['now']['history_mean'], places=2)

    def test_regime_states(self):
        R = self.doc['regime']
        self.assertEqual([s['name'] for s in R['states']], ['Calm', 'Normal', 'Stressed'])
        self.assertLess(R['states'][0]['vol_year'], R['states'][2]['vol_year'])
        self.assertAlmostEqual(sum(R['now']), 1.0, places=3)

    def test_ledger(self):
        book = FB.load(Path(self.tmp) / 'ledger.json')
        self.assertTrue(FB.entries(book, 'vol'))
        self.assertTrue(FB.entries(book, 'market'))
        asof = self.days[-1].isoformat()
        self.assertTrue(all(e['asof'] == asof for _, e in FB.entries(book, 'index')))


class TestPieces(unittest.TestCase):
    def test_sums(self):
        x = np.arange(10, dtype=float)
        self.assertEqual(MM.fwd_sum(x, 2)[3], 4 + 5)
        self.assertTrue(np.isnan(MM.fwd_sum(x, 2)[8]))
        self.assertEqual(MM.back_sum(x, 3)[5], 3 + 4 + 5)
        self.assertEqual(MM.back_sum(x, 3, skip=2)[6], 2 + 3 + 4)

    def test_no_look_ahead(self):
        """A forecast made in a year does not change when everything after that year changes."""
        rng = np.random.default_rng(1)
        days = np.datetime64('1995-01-06') + 7 * np.arange(1400)
        r = garch_returns(rng, 1400)
        a = MM.har_walk(days, r, 4)
        r2 = r.copy()
        cut = int(np.searchsorted(days, np.datetime64('2010-01-01')))
        r2[cut:] *= 3
        b = MM.har_walk(days, r2, 4)
        k = cut - 10                                          # a 2009 week: fitted before 2009, features up to it
        self.assertEqual(a['F'][k], b['F'][k])
        self.assertFalse(np.allclose(a['F'][cut + 300], b['F'][cut + 300]))

    def test_shrink_walk(self):
        days = np.datetime64('2000-01-07') + 7 * np.arange(1000)
        rng = np.random.default_rng(2)
        y = rng.standard_normal(1000)
        good = y + 0.1 * rng.standard_normal(1000)
        noise = rng.standard_normal(1000)
        Fc, beta, _ = MM.shrink_walk(days, good, y, 1)
        self.assertGreater(beta[max(beta)], 0.8)              # a forecast that has worked is used
        Fc, beta, _ = MM.shrink_walk(days, noise, y, 1)
        self.assertLess(beta[max(beta)], 0.15)               # one that has not is not
        self.assertEqual(beta[min(beta)], 0.0)                # no record yet: the benchmark

    def test_spread_mean_reversion_found(self):
        rng = np.random.default_rng(4)
        n = 1500
        days = np.datetime64('1995-01-06') + 7 * np.arange(n)
        x = np.zeros(n)
        for t in range(1, n):
            x[t] = 0.9 * x[t - 1] + 0.02 * rng.standard_normal()
        res = MM.spread_model(days, x, 'log', n - 1)
        self.assertEqual(res[13]['score']['chosen'], 'ou')
        self.assertGreater(res[13]['score']['r2_ou'], 0.2)
        rw = np.cumsum(0.02 * rng.standard_normal(n))
        self.assertEqual(MM.spread_model(days, rw, 'log', n - 1)[13]['score']['chosen'], 'rw')

    def test_hmm_recovers_states(self):
        rng = np.random.default_rng(5)
        z = np.repeat([0, 2, 1, 0, 2, 1] * 6, 40)
        mu = np.array([[0.5, -1.0, 0.0], [0.0, 0.0, 0.0], [-1.0, 1.5, 0.5]])
        X = mu[z] + 0.3 * rng.standard_normal((len(z), 3))
        fit = MM.hmm_fit(X)
        a = MM.hmm_filter(X, fit)
        self.assertGreater((a.argmax(1) == z).mean(), 0.9)       # ordered by the VIX column: calm, normal, stressed

    def test_closed_week(self):
        days = np.datetime64('2026-10-16') + 7 * np.arange(4)    # 16, 23, 30 Oct, 6 Nov
        self.assertEqual(str(days[MM.closed_week(days, dt.date(2026, 11, 2))]), '2026-10-30')
        self.assertEqual(str(days[MM.closed_week(days, dt.date(2026, 10, 30))]), '2026-10-23')


if __name__ == '__main__':
    unittest.main()
