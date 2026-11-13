"""combo_backtest.py: the momentum percentiles and ranking returns, a strategy week by week (bought in the band's top
and the entry quadrants, held through the buffer, sold below it or in the exit quadrants; its trades, turnover and the
equal weight it holds), and the file — the strategies, their recent and long-run statistics, trades and lengths, today's
holdings, the walk-forward record and today's order — on hand-made weeks and a planted universe. No network."""
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import combo_backtest as CB  # noqa: E402
from test_rrg_backtest import universe, weekdays  # noqa: E402


class Signals(unittest.TestCase):
    def test_percentiles(self):
        M = np.array([[1.0, np.nan], [3.0, 2.0], [2.0, 1.0], [np.nan, 5.0]])
        old = CB.MIN_RANKED
        try:
            CB.MIN_RANKED = 3
            P = CB.percentiles(M)
        finally:
            CB.MIN_RANKED = old
        self.assertEqual(P[:, 0].tolist()[:3], [0.0, 1.0, 0.5])
        self.assertTrue(np.isnan(P[3, 0]))
        self.assertEqual(P[1:, 1].tolist(), [0.5, 0.0, 1.0])
        self.assertTrue(np.isnan(P[0, 1]))
        self.assertTrue(np.all(np.isnan(CB.percentiles(M[:, :1]))))      # MIN_RANKED (200): too few to rank

    def test_momentum(self):
        C = np.vstack([1.01 ** np.arange(60), np.ones(60)])
        M = CB.momentum(C)
        self.assertAlmostEqual(M['12-1'][0, 59], 1.01 ** (55 - 7) - 1)    # C[t − 4] ÷ C[t − 52]
        self.assertAlmostEqual(M['3m'][0, 59], 1.01 ** 13 - 1)
        self.assertTrue(np.isnan(M['12-1'][0, 51]))                      # not a year of closes yet
        self.assertEqual(M['6-1'][1, 40], 0.0)


class Simulate(unittest.TestCase):
    def test_entry_hold_exit(self):
        T = 8
        # three companies: A in the top and Improving from week 1, Lagging at week 5; B in the top but Leading
        # throughout (never Improving); C slips from the top 10% to the buffer at week 3 and out at week 6
        pct = np.array([[0.5, 0.95, 0.95, 0.95, 0.95, 0.95, 0.95, 0.95],
                        [0.99] * T,
                        [0.95, 0.95, 0.95, 0.85, 0.85, 0.85, 0.70, 0.70]], dtype=np.float32)
        q = np.array([[3, 3, 3, 3, 3, 2, 2, 2], [0] * T, [3] * T], dtype=np.int8)
        r = np.vstack([np.full(T, 0.10), np.full(T, 0.0), np.full(T, -0.05)])
        s = CB.simulate(r, pct, q, (3,), (2,), (10, 20), 0)
        # A bought at week 1 (in the top and Improving), sold at week 5 (Lagging); C bought at week 0, held in the
        # buffer through week 5, sold at week 6 (below the top 20%); B never (not Improving)
        self.assertEqual(sorted(zip(s['tk'].tolist(), s['te'].tolist(), s['tx'].tolist())), [(0, 1, 5), (2, 0, 6)])
        self.assertEqual(s['n'].tolist(), [1, 2, 2, 2, 2, 1, 0, 0])
        self.assertAlmostEqual(s['r'][1], -0.05)                          # week 1: C alone
        self.assertAlmostEqual(s['r'][2], (0.10 - 0.05) / 2)              # weeks 2-5: A and C equal weight
        self.assertAlmostEqual(s['r'][6], -0.05)                          # week 6: C alone (A sold at 5)
        self.assertEqual(s['r'][7], 0.0)                                  # cash
        self.assertAlmostEqual(s['tv'][1], 0.5)                           # A bought: half the new portfolio
        self.assertAlmostEqual(s['tv'][5], 0.5)                           # A sold: half the old one
        self.assertAlmostEqual(s['tv'][6], 1.0)                           # C sold, nothing bought
        self.assertEqual(s['open'].tolist(), [])
        # momentum alone: no quadrant rule — B and C bought at once, A when it reaches the top
        m = CB.simulate(r, pct, q, None, None, (10, 20), 0)
        self.assertEqual(m['n'].tolist()[:2], [2, 3])
        self.assertEqual(sorted(m['open'].tolist()), [0, 1])
        self.assertEqual(int(m['since'][0]), 1)


class Build(unittest.TestCase):
    def test_file(self):
        olds = CB.MIN_RANKED, CB.MIN_HELD
        try:
            CB.MIN_RANKED, CB.MIN_HELD = 10, 1
            with tempfile.TemporaryDirectory() as tmp:
                base = universe(tmp, n=40, kind='stock', group=None, days=weekdays('1998-12-01', 2400))
                doc = CB.build(base, Path(tmp) / 'out' / 'combo.json', log=lambda m: None)
                on_disk = json.loads((Path(tmp) / 'out' / 'combo.json').read_text())
        finally:
            CB.MIN_RANKED, CB.MIN_HELD = olds
        self.assertEqual(on_disk['schema'], CB.SCHEMA)
        self.assertEqual(doc['companies'], 40)
        keys = [k for k in doc['series'] if k not in ('spy', 'ew')]
        self.assertEqual(len(keys), len(CB.RULES) * len(CB.MEASURES) * len(CB.BANDS))
        self.assertIn('dip-ride|12-1|10', keys)
        self.assertTrue(all(len(v) == len(doc['months']) for v in doc['series'].values()))
        self.assertEqual(doc['months'][-1], doc['as_of'])
        self.assertEqual(set(doc['periods']), {'all', '10y', '5y', '3y', '1y'})
        st = doc['stats']['mom|12-1|10']['all']
        self.assertTrue({'cagr', 'excess', 't', 'turn_w', 'mdd'} <= set(st))
        self.assertAlmostEqual(doc['stats']['ew']['all']['excess'], 0.0, places=6)
        tr = doc['trades']['mom|12-1|10']
        self.assertEqual(len(tr['hist']), CB.DUR_BINS)
        self.assertEqual(sum(tr['hist']), tr['n'])
        self.assertTrue(0 <= tr['win'] <= 1 and tr['weeks_median'] >= 1)
        self.assertEqual(doc['rule_quadrants']['dip-ride'], {'enter': [2], 'exit': [1]})
        # today's holdings and the readings of the companies held
        for k in keys:
            for key, since, ret in doc['now'][k]:
                self.assertIn(key, doc['companies_now']['rows'])
                self.assertLessEqual(since, doc['as_of'])
        self.assertEqual(doc['companies_now']['fields'], ['pct_12-1', 'pct_6-1', 'pct_3m', 'x', 'y', 'q'])
        # the years: the first from the start, the last this year
        self.assertEqual(doc['years']['spy'][-1][0], int(doc['as_of'][:4]))
        # the walk-forward record and today's order
        w = doc['walk']['1y']
        self.assertTrue(w['records'])
        self.assertEqual(w['fields'], ['key', 'score', 'ir', 'ir_all', 'gap', 'held', 'eligible'])
        self.assertEqual(len(w['now']), len(keys))
        scores = [r[1] for r in w['now'] if r[6]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(abs(r[1] - min(r[2], r[3])) < 0.011 for r in w['now']))   # the lower of the two ratios
        rec = w['records'][0]
        self.assertTrue({'year', 'pick', 'pick_next', 'avg_next', 'rank'} <= set(rec))
        self.assertTrue(1 <= rec['rank'] <= len(keys))
        self.assertEqual(w['summary']['strategies'], len(keys))
        self.assertEqual(len(w['series']['pick']), len(w['months']))


if __name__ == '__main__':
    unittest.main()
