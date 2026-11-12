"""momentum_backtest.py: the daily returns on one calendar, the ranking returns (each period's, 12-1 skipping a month),
the tenths ranked, the overlapping portfolios bought and held (Jegadeesh & Titman), long-short, turnover, the clip of
bad prints, the statistics, and the file — on planted universes where winners keep winning (momentum) and where
yesterday's losers bounce (reversal). No network."""
import datetime as dt
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import momentum_backtest as B  # noqa: E402
import paths as P  # noqa: E402


def weekdays(start, n):
    d, out = dt.date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def universe(tmp, n=240, days=None, drift=None, seed=1, extra=None):
    """public/moves/: index.json and a/<KEY>.json (P.encode_returns) for SPY and n stocks; drift(i, t) the log
    return of stock i on day t (noise added)."""
    days = days or weekdays('1998-12-01', 900)
    rng = np.random.default_rng(seed)
    base = Path(tmp) / 'moves'
    (base / 'a').mkdir(parents=True)
    rows = [['SPY', 'market']]
    spy = np.cumsum(np.concatenate([[0.0], rng.normal(0.0003, 0.01, len(days) - 1)]))
    (base / 'a' / 'SPY.json').write_text(json.dumps(P.encode_returns(days, list(100 * np.exp(spy)))))
    for i in range(n):
        k = f'S{i:03d}'
        r = rng.normal(0, 0.01, len(days) - 1) + np.array([drift(i, t) if drift else 0.0 for t in range(1, len(days))])
        c = 50 * np.exp(np.concatenate([[0.0], np.cumsum(r)]))
        if extra:
            c = extra(i, c)
        (base / 'a' / f'{k}.json').write_text(json.dumps(P.encode_returns(days, list(c))))
        rows.append([k, 'stock'])
    (base / 'index.json').write_text(json.dumps({'fields': ['key', 'kind'], 'rows': rows}))
    return base


class Signals(unittest.TestCase):
    def test_ranking_returns(self):
        L = np.array([[0.01, np.nan], [0.02, 0.05], [0.03, 0.01], [-0.01, 0.02]], dtype=np.float32)
        old = B.RANKS
        try:
            B.RANKS = [('1', 1), ('2', 2)]
            S = B.signals(L)
        finally:
            B.RANKS = old
        self.assertAlmostEqual(float(S['2'][2, 0]), 0.05, places=6)
        self.assertTrue(np.isnan(S['2'][1, 1]))                          # a missing day in the period: not ranked
        self.assertAlmostEqual(float(S['2'][2, 1]), 0.06, places=6)
        self.assertAlmostEqual(float(S['1'][3, 0]), -0.01, places=6)

    def test_twelve_minus_one(self):
        T = 300
        L = np.zeros((T, 1), dtype=np.float32)
        L[T - 1 - 252 + 1:T - 1 - 21 + 1, 0] = 0.001                     # days t-251 … t-21
        L[T - 21:, 0] = 0.05                                              # the skipped month: not counted
        S = B.signals(L)['12-1']
        self.assertAlmostEqual(float(S[T - 1, 0]), 0.231, places=4)

    def test_tenths(self):
        S = np.array([np.arange(300, dtype=float)])
        old = B.MIN_RANKED
        try:
            B.MIN_RANKED = 200
            self.assertEqual(B.members(S, 0, 'top').tolist(), list(range(270, 300)))
            self.assertEqual(B.members(S, 0, 'bottom').tolist(), list(range(30)))
            self.assertIsNone(B.members(S[:, :150], 0, 'top'))           # under 200 ranked: no portfolio
        finally:
            B.MIN_RANKED = old


class Portfolios(unittest.TestCase):
    def test_momentum_and_reversal(self):
        days = weekdays('1998-12-01', 900)
        with tempfile.TemporaryDirectory() as tmp:
            # momentum: the first half of the stocks trend up for good, the rest down — the winners keep winning
            base = universe(tmp, drift=lambda i, t: 0.0015 if i < 120 else -0.0015)
            cal, spy, keys, L = B.load(base)
            start, res, cnt = B.run(cal, spy, L, log=lambda m: None)
            self.assertEqual(cal[start - max(B.HOLDS)], '2000-01-03')       # the common start: 63 days in
            r = {k: v['r'][start:] for k, v in res.items()}
            for K in B.HOLDS:
                self.assertGreater(np.prod(1 + r[('12-1', K, 'top')]), np.prod(1 + r[('12-1', K, 'bottom')]), K)
                self.assertGreater(np.sum(r[('63', K, 'ls')]), 0, K)
            self.assertTrue(np.allclose(r[('21', 5, 'ls')], r[('21', 5, 'top')] - r[('21', 5, 'bottom')]))
            self.assertEqual(int(cnt[start]), 240)
            # turnover: a slow ranking keeps most names from one portfolio to the next — under half of the most it
            # could be (2/K a day, every name changed)
            self.assertLess(res[('12-1', 21, 'top')]['turn'], 0.5 * 2 / 21)
            self.assertAlmostEqual(res[('12-1', 21, 'top')]['n'], 24.0)
        with tempfile.TemporaryDirectory() as tmp:
            # reversal: half of each day's move comes back the next day
            rng = np.random.default_rng(5)
            shocks = rng.normal(0, 0.03, (240, len(days)))
            base = universe(tmp, drift=lambda i, t: shocks[i, t] - 0.5 * shocks[i, t - 1])
            cal, spy, keys, L = B.load(base)
            start, res, _ = B.run(cal, spy, L, log=lambda m: None)
            r = {k: v['r'][start:] for k, v in res.items()}
            self.assertGreater(np.prod(1 + r[('1', 1, 'bottom')]), np.prod(1 + r[('1', 1, 'top')]))
            self.assertLess(np.mean(r[('1', 1, 'ls')]), 0)
            self.assertGreater(res[('1', 1, 'top')]['turn'], 1.5)          # a new tenth every day: almost all of it traded

    def test_bought_and_held(self):
        # two names in a portfolio: +100% then −50% for one, flat for the other — held, the portfolio is back where it
        # began after two days (rebalanced daily it would lose: 1.5 then 0.75 × … )
        L = np.zeros((4, 2), dtype=np.float32)
        L[1, 0], L[2, 0] = math.log(2.0), math.log(0.5)
        Pix = np.exp(np.vstack([np.zeros((1, 2)), np.cumsum(L, axis=0)]))
        rel = Pix[1:4, :][:, [0, 1]] / Pix[0, [0, 1]]
        V = rel.mean(axis=1)
        self.assertAlmostEqual(float(V[1]), 1.5)
        self.assertAlmostEqual(float(V[2]), 1.0)

    def test_bad_prints_clipped(self):
        days = weekdays('1998-12-01', 400)

        def jump(i, c):
            if i == 3:
                c = c.copy()
                c[200:] *= 258.0                                          # a restructuring's ×258 in the adjusted closes
            return c
        with tempfile.TemporaryDirectory() as tmp:
            base = universe(tmp, n=210, days=days, extra=jump)
            cal, spy, keys, L = B.load(base)
            self.assertAlmostEqual(float(np.nanmax(L)), math.log(2.0), places=5)
            self.assertGreaterEqual(float(np.nanmin(L)), math.log(0.5) - 1e-6)


class File(unittest.TestCase):
    def test_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = universe(tmp, drift=lambda i, t: 0.001 if i < 120 else -0.001)
            doc = B.build(base, Path(tmp) / 'out', log=lambda m: None)
            on_disk = json.loads((Path(tmp) / 'out' / 'momentum.json').read_text())
        self.assertEqual(on_disk['schema'], B.SCHEMA)
        self.assertEqual(doc['ranks'], ['1', '5', '10', '21', '63', '12-1'])
        self.assertEqual(doc['holds'], [1, 5, 10, 21, 63])
        self.assertEqual(len(doc['series']), 6 * 5 * 3 + 2)
        n = len(doc['months'])
        self.assertTrue(all(len(v) == n for v in doc['series'].values()))
        self.assertEqual(doc['months'][-1], doc['as_of'])
        st = doc['stats']['12-1|21|ls']['all']
        self.assertGreater(st['cagr'], 0)
        self.assertEqual(doc['stats']['spy']['all']['beta'], 1.0)
        self.assertEqual(doc['stats']['spy']['all']['alpha'], 0.0)
        self.assertAlmostEqual(doc['stats']['spy']['all']['total'], round(doc['series']['spy'][-1] - 1, 3), places=3)
        self.assertIn('12-1|21|top', doc['turn'])
        self.assertNotIn('spy', doc['turn'])
        self.assertEqual(set(doc['periods']), {'all', '10y', '5y'})


if __name__ == '__main__':
    unittest.main()
