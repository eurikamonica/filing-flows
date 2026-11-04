"""Hybrid RRG (app/rrg_hybrid.py) on synthetic weekly files: no look-ahead in the inputs or the walk-forward fits, the
stacking keeps only blocks that helped, a planted momentum effect is found, and the published files and the ledger."""
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
import rrg_hybrid as HY  # noqa: E402

START = dt.date(1996, 1, 5)                 # a Friday
W = 31 * 52


def write_public(root, n_cos=90, n_funds=12, seed=11, drift=0.0015, spread=0.0):
    """rrg.json (SPY, funds with volume), t/<T>.json for companies whose relative return carries a persistent drift
    (so 12-1 momentum predicts it), industries.json empty. `spread`: each line's noise scaled by exp(N(0, spread)) —
    calm and wild lines side by side."""
    rng = np.random.default_rng(seed)
    days = [START + dt.timedelta(days=7 * k) for k in range(W)]
    pub = Path(root)
    (pub / 't').mkdir(parents=True)
    spy_r = rng.normal(0.0015, 0.02, W)
    spy = 100 * np.exp(np.cumsum(spy_r))

    def line(n, scale):
        out = []
        for _ in range(n):
            mu = np.zeros(W)
            level = 0.0
            for k in range(W):                                   # the line's own drift wanders slowly: momentum works
                if k % 26 == 0:
                    level = 0.6 * level + rng.normal(0, drift)
                mu[k] = level
            r = spy_r + mu + rng.normal(0, scale * math.exp(rng.normal(0, spread)) if spread else scale, W)
            c = 30 * np.exp(np.cumsum(r))
            v = np.exp(rng.normal(13, 0.3, W))
            out.append((c, v))
        return out
    funds = line(n_funds, 0.01)
    cos = line(n_cos, 0.03)
    series = [{'id': f'F{i}', 'name': f'Fund {i}', 'group': 'sector-etf' if i % 2 else 'style-etf', 'start': days[0].isoformat(),
               'c': [round(float(x), 4) for x in c], 'v': [round(float(x) / 1000, 1) for x in v]} for i, (c, v) in enumerate(funds)]
    tickers = {}
    for i, (c, v) in enumerate(cos):
        t = f'C{i:03d}'
        tickers[t] = {'n': f'Company {i}', 's': 'technology', 'rev': 1e9, 'start': days[0].isoformat()}
        (pub / 't' / f'{t}.json').write_text(json.dumps({'start': days[0].isoformat(), 'c': [round(float(x), 4) for x in c],
                                                           'v': [round(float(x) / 1000, 1) for x in v]}))
    doc = {'benchmark': 'SPY', 'start': days[0].isoformat(), 'weeks': days[-1].isoformat(),
           'bench': {'id': 'SPY', 'start': days[0].isoformat(), 'c': [round(float(x), 4) for x in spy]}, 'series': series, 'tickers': tickers}
    (pub / 'rrg.json').write_text(json.dumps(doc))
    (pub / 'industries.json').write_text(json.dumps({'rows': []}))
    return pub, days


class Built(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.pub, cls.days = write_public(cls.tmp)
        cls.ledger = Path(cls.tmp) / 'ledger.json'
        cls.today = cls.days[-1] + dt.timedelta(days=2)
        cls.doc = HY.build(cls.pub, cls.ledger, today=cls.today, verbose=False, force=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)


class TestBuild(Built):
    def test_files(self):
        d = json.loads((self.pub / 'rrg-hybrid.json').read_text())
        self.assertEqual(d['asof'], self.days[-1].isoformat())
        self.assertEqual(d['volume_week'], self.days[-1 - HY.VOLUME_LAG].isoformat())     # volume runs a week behind
        self.assertEqual(set(d['panels']), {'funds', 'companies'})
        co = json.loads((self.pub / 'rrg-hybrid-companies.json').read_text())
        self.assertGreater(len(co['rows']), len(d['panels']['companies']['rows']) - 1)
        row = d['panels']['funds']['rows'][0]
        for h in ('h1', 'h4', 'h13'):
            self.assertTrue(0 <= row[h]['p'] <= 1)
            self.assertLessEqual(row[h]['lo'], row[h]['hi'])
        self.assertEqual(len(row['tail']['hybrid'][0]), HY.TAIL_WEEKS + 1)

    def test_planted_momentum_is_found(self):
        s = self.doc['panels']['companies']['scores']['13']
        self.assertGreater(s['ic']['hybrid']['ic'], 0.05)          # the drift persists: the hybrid ranks it
        self.assertGreater(s['ic']['momentum']['ic'], 0.05)
        w = self.doc['panels']['companies']['weights_now']['13']
        self.assertGreater(w['momentum'], 0)
        self.assertTrue(all(v >= 0 for v in w.values()))              # non-negative stacking
        self.assertTrue(0.7 <= s['range80'] <= 0.9)
        b = s['best_minus_worst']                                     # baskets in simple returns, before and after costs
        self.assertGreater(b['gross'], b['mean'])
        self.assertIn('best_minus_worst_vol_neutral', s)                  # None here: under 25 names per volatility fifth
        early = [r for r in self.doc['panels']['companies']['describe'] if r.get('early')]
        self.assertTrue(early and all(r['early']['weeks'] >= 8 for r in early))   # the 2004–2011 check is there

    def test_ledger_freezes_and_resolves(self):
        book = FB.load(self.ledger)
        fams = set(book['families'])
        self.assertEqual(fams, {f'{p}:{h}' for p in ('funds', 'companies') for h in HY.HORIZONS})
        # a second build 13 weeks later resolves the first week's 1-, 4- and 13-week forecasts
        tmp = tempfile.mkdtemp()
        try:
            led = Path(tmp) / 'l.json'
            early = self.days[-14] + dt.timedelta(days=2)
            HY.build(self.pub, led, today=early, verbose=False, force=True)
            HY.build(self.pub, led, today=self.today, verbose=False, force=True)
            b = FB.load(led)
            for h in HY.HORIZONS:
                done = FB.entries(b, f'companies:{h}', resolved=True)
                self.assertEqual(len(done), 1, h)
                self.assertEqual(len(done[0][1]['actual']['rel']), len(done[0][1]['forecast']['ids']))
            sc = HY.ledger_scores(b)
            self.assertIsNotNone(sc['companies:13']['ic'])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_skips_a_week_already_built(self):
        self.assertIsNone(HY.build(self.pub, None, today=self.today, verbose=False))


class TestPieces(unittest.TestCase):
    def test_no_look_ahead_in_inputs_and_fits(self):
        tmp = tempfile.mkdtemp()
        try:
            pub, days = write_public(tmp, n_cos=40, n_funds=6)
            D = HY.load(pub)
            P = D['panels']['companies']
            Fe = HY.features(P['C'], P['V'], D['spy'], P['liq'])
            R = HY.walk_forward(D['days'], Fe, 4)
            cut = int(np.searchsorted(D['days'], np.datetime64('2015-01-01')))
            C2 = P['C'].copy()
            C2[:, cut:] *= np.exp(np.random.default_rng(3).normal(0, 0.2, C2[:, cut:].shape))
            Fe2 = HY.features(C2, P['V'], D['spy'], P['liq'])
            R2 = HY.walk_forward(D['days'], Fe2, 4)
            k = cut - 30                                          # a 2014 week: inputs up to it, fits on years before
            for name in ('x14', 'mom12_1', 'vz1'):
                np.testing.assert_array_equal(Fe['raw'][name][:, k], Fe2['raw'][name][:, k])
            np.testing.assert_allclose(R['S'][:, k], R2['S'][:, k])
            self.assertFalse(np.allclose(np.nan_to_num(R['S'][:, cut + 300]), np.nan_to_num(R2['S'][:, cut + 300])))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_volatility_groups(self):
        vol = np.array([[0.01, np.nan], [0.05, 0.02], [0.03, 0.04], [0.02, 0.01], [0.04, 0.03]])
        ok = np.ones(vol.shape, bool)
        g = HY.vol_groups(vol, ok, 5)
        self.assertEqual(g[:, 0].tolist(), [0, 4, 2, 1, 3])                 # ranked within the week, calmest = 0
        self.assertEqual(g[0, 1], -1)                                      # no volatility yet: no group
        self.assertEqual(sorted(g[1:, 1].tolist()), [0, 1, 2, 3])
        self.assertTrue((HY.vol_groups(vol, ok, 1)[np.isfinite(vol)] == 0).all())

    def test_ranges_hold_in_every_volatility_fifth(self):
        tmp = tempfile.mkdtemp()
        try:
            pub, _ = write_public(tmp, n_cos=60, n_funds=6, seed=5, spread=0.4)
            D = HY.load(pub)
            P = D['panels']['companies']
            Fe = HY.features(P['C'], P['V'], D['spy'], P['liq'])
            R = HY.walk_forward(D['days'], Fe, 13, groups=5)
            ev = HY.evaluate(D['days'], Fe, R, 13, 'companies')
            self.assertEqual(len(ev['range80_by_vol']), 5)
            for v in ev['range80_by_vol']:
                self.assertTrue(0.7 <= v <= 0.9, ev['range80_by_vol'])
            self.assertLess(abs(ev['beat_spy']['bias']), 0.06)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_nnls(self):
        rng = np.random.default_rng(1)
        A = rng.normal(size=(500, 3))
        y = A @ np.array([0.7, 0.0, 0.2]) - 0.5 * A[:, 1] + rng.normal(0, 0.01, 500)
        w = HY.nnls(A, y)
        self.assertTrue((w >= 0).all())
        self.assertEqual(w[1], 0.0)                               # a block that hurts gets no weight
        self.assertAlmostEqual(w[0], 0.7, places=1)

    def test_quadrants_and_closed_week(self):
        q = HY.quad(np.array([[101.0, 101.0, 99.0, 99.0, np.nan]]), np.array([[101.0, 99.0, 99.0, 101.0, 100.0]]))
        self.assertEqual(q.tolist(), [[0, 1, 2, 3, -1]])
        days = np.datetime64('2026-10-16') + 7 * np.arange(4)
        self.assertEqual(str(days[HY.closed_week(days, dt.date(2026, 11, 4))]), '2026-10-30')

    def test_costs_by_dollar_volume(self):
        C = np.full((3, 20), 10.0)
        V = np.array([np.full(20, 6e7), np.full(20, 6e6), np.full(20, 1e5)])     # $600M, $60M, $1M a week
        Fe = HY.features(C, V, np.full(20, 100.0), np.ones((3, 20), bool))
        self.assertEqual([round(float(x) * 1e4) for x in Fe['cost'][:, -1]], [5, 15, 100])


if __name__ == '__main__':
    unittest.main()
