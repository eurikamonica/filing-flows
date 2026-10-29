"""opportunity.py: direction, buy and short odds — the walk-forward model, the flags and their gate, the ETF loader, the
shards and the frozen ledger."""
import datetime as dt
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import opportunity as O


def panel(N=150, T=520, seed=7, mom=0.4):
    """A synthetic weekly panel with a planted momentum effect: next week's return leans toward the last 13 weeks'."""
    rng = np.random.default_rng(seed)
    sig = rng.uniform(0.02, 0.06, N)
    r = np.zeros((N, T))
    for t in range(1, T):
        past = r[:, max(0, t - 13):t].sum(1) if t > 1 else np.zeros(N)
        z = (past - past.mean()) / (past.std() + 1e-9)
        r[:, t] = 0.001 + sig * (mom * np.tanh(z) / 3 + rng.standard_normal(N))
    C = 20 * np.exp(np.cumsum(r, 1))
    V = np.tile(rng.uniform(1e6, 2e9, N)[:, None], (1, T))
    dates = np.datetime64('2000-01-07') + 7 * np.arange(T)
    return {'tickers': [f'T{i:03d}' for i in range(N)], 'names': [f'Co {i}' for i in range(N)],
            'sectors': [['tech', 'energy', 'health'][i % 3] for i in range(N)], 'dates': dates, 'C': C, 'V': V,
            'spx': np.nanmean(C, 0), 'sector_lines': {}}


NO_MACRO = lambda P: {k: np.full(len(P['dates']), np.nan) for k in ('vix', 'curve', 'credit')}


class Pieces(unittest.TestCase):
    def test_capped_mean(self):
        x = np.r_[np.zeros(995), np.full(5, 1e6)]             # half a percent of bad prints
        self.assertLess(O._wmean(x), 1.0)
        self.assertGreater(float(np.mean(x)), 1e3)
        self.assertIsNone(O._wmean([]))

    def test_flag_gate(self):
        good = {'hit': 0.55, 'base_hit': 0.52, 'all_hit': 0.50, 'net_median': 0.01, 'net_mean': 0.012}
        self.assertTrue(O.flag_ok(good))
        self.assertFalse(O.flag_ok({**good, 'hit': 0.49, 'base_hit': 0.40}))     # better than expected, still loses more often
        self.assertFalse(O.flag_ok({**good, 'hit': 0.53}))                        # under 2 points over its own no-signal odds
        self.assertFalse(O.flag_ok({**good, 'base_hit': 0.54}))                   # beat the average name, not its own baseline
        self.assertFalse(O.flag_ok({**good, 'net_median': -0.001}))
        self.assertFalse(O.flag_ok(None))
        self.assertTrue(O.flag_ok({**good, 'halves': [[500, 0.55, 0.52], [500, 0.56, 0.52]]}))
        self.assertFalse(O.flag_ok({**good, 'halves': [[500, 0.58, 0.52], [500, 0.52, 0.52]]}))   # one lucky stretch

    def test_flags_rank_and_disallow(self):
        n = 100
        pb = np.linspace(0.4, 0.8, n)
        p0 = np.full(n, 0.5)
        ps = np.full(n, 0.4)
        edge, side, pct, eb, es = O.flags(pb, ps, p0, p0, np.ones(n, bool))
        self.assertEqual(int((side == 1).sum()), 20)                 # the strongest fifth, all buys
        self.assertTrue(np.all(side[-20:] == 1))
        _, side2, _, _, _ = O.flags(pb, ps, p0, p0, np.ones(n, bool), allow=(False, True))
        self.assertFalse(np.any(side2 == 1))                         # buys switched off: none flagged
        ps2 = np.linspace(0.7, 0.3, n)
        _, side3, _, _, _ = O.flags(np.full(n, 0.4), ps2, p0, p0, np.r_[np.zeros(50, bool), np.ones(50, bool)])
        self.assertFalse(np.any(side3[:50] == -1))                   # hard to borrow: no short flag
        _, side4, _, _, _ = O.flags(np.full(n, 0.45) + np.linspace(0, 0.04, n), ps, np.full(n, 0.40), p0, np.ones(n, bool))
        self.assertFalse(np.any(side4 == 1))                         # a large edge, but under even odds: no flag

    def test_platt_recovers_a_bias(self):
        rng = np.random.default_rng(1)
        p = rng.uniform(0.2, 0.8, 20000)
        y = rng.uniform(size=p.size) < np.clip(p - 0.1, 0, 1)     # the raw probabilities run 10 points high
        q = O.platt_apply(O.platt(p, y), p)
        self.assertLess(abs(q.mean() - y.mean()), 0.01)


class Model(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.P = panel()
        cls.R = O.run(cls.P, NO_MACRO(cls.P))

    def test_walk_forward_finds_the_planted_effect(self):
        c = self.R['horizons']['1w']['card']
        self.assertGreater(c['ic_mean'], 0.05)
        self.assertGreater(c['up']['brier_skill'], 0)
        self.assertGreater(c['coef']['mom13'], 0)
        self.assertGreaterEqual(c['oos_years'][0], 2000 + O.FIRST_TEST_YEARS)
        for k in ('up', 'buy', 'short'):
            for lo, hi, n, p, y in c[k]['calibration']:
                self.assertTrue(lo <= p <= hi + 1e-9)
        self.assertEqual(len(c['buy']['edge_deciles']), 10)
        self.assertIn('flag_ok', c['buy'])

    def test_rows(self):
        rows = O.rows_now(self.P, self.R)
        self.assertEqual(len(rows), 150)
        r = rows[0]
        for hk in O.HORIZONS:
            pu, pb, ps, q10, q50, q90, cost, edge, side, pct = r['h'][hk]
            self.assertTrue(0 < pu < 1 and 0 < pb < 1 and 0 < ps < 1)
            self.assertLessEqual(pb, pu + 1e-9)                       # costs make a profit no likelier than a rise
            self.assertTrue(q10 <= q50 <= q90)
            self.assertIn(side, ('buy', 'short', 'none'))
        self.assertTrue(0 <= r['score'] <= 100)
        self.assertEqual(len(r['drivers']), 4)
        flagged = [x for x in rows if x['side'] != 'none']
        for x in flagged:
            hk = x['best_h']
            self.assertTrue(self.R['horizons'][hk]['card'][x['side']]['flag_ok'])

    def test_publish_and_shards(self):
        with tempfile.TemporaryDirectory() as d:
            summ = O.publish(d, self.P, self.R, 'stocks')
            strict = lambda c: (_ for _ in ()).throw(ValueError('not JSON: ' + c))
            doc = json.loads((Path(d) / 'opportunity-stocks.json').read_text(), parse_constant=strict)   # no NaN / Infinity
            self.assertEqual(len(doc['rows']), summ['names'])
            self.assertEqual(doc['fields_h'][8], 'side')
            sh = json.loads((Path(d) / 'opportunity-stocks' / 'T.json').read_text())
            self.assertEqual(len(sh['rows']), 150)
            self.assertIn('flags', sh['cards']['1m'])
            self.assertEqual(O.shard_of('brk-b'), 'B')
            self.assertEqual(O.shard_of('^X'), '_')


class Ledger(unittest.TestCase):
    def test_freeze_resolve_compact(self):
        P = panel(N=80, T=460, seed=3)
        cut = 420                                                    # pretend the data ended at week 420
        Pc = {**P, 'C': P['C'][:, :cut + 1], 'V': P['V'][:, :cut + 1], 'dates': P['dates'][:cut + 1], 'spx': P['spx'][:cut + 1]}
        R = O.run(Pc, NO_MACRO(Pc))
        rows = O.rows_now(Pc, R)
        D = R['_now']['date']
        d = dt.date.fromisoformat(D)
        L = {'kind': 'stocks', 'origins': {}}
        self.assertFalse(O.freeze(L, R, rows, today=d + dt.timedelta(days=1)))        # Saturday: not settled yet
        self.assertTrue(O.freeze(L, R, rows, 'abc', today=d + dt.timedelta(days=2)))  # Sunday
        self.assertFalse(O.freeze(L, R, rows, today=d + dt.timedelta(days=3)))        # frozen once
        rec = L['origins'][D]
        self.assertEqual(len(rec['tickers']), len(rows))
        self.assertEqual(len(rec['h']['1w']['side']), len(rows))
        # four weeks on: 1w and 1m scored, 3m waits
        self.assertEqual(O.resolve(L, P, today=d + dt.timedelta(days=4 * 7 + 2)), 2)
        self.assertEqual(set(rec['res']), {'1w', '1m'})
        self.assertIn('tickers', rec)
        sc = rec['res']['1w']
        self.assertEqual(sc['n'], len(rows))
        self.assertEqual(sum(b[0] for b in sc['up']['calib']), sc['n'])
        # thirteen weeks on: everything scored, the rows dropped
        self.assertEqual(O.resolve(L, P, today=d + dt.timedelta(days=13 * 7 + 2)), 1)
        self.assertNotIn('tickers', rec)
        pub = O.ledger_public(L)
        self.assertEqual(pub['frozen'], 1)
        self.assertEqual(pub['scored'], 1)
        self.assertEqual(pub['totals']['3m']['origins'], 1)
        self.assertTrue(0 <= pub['totals']['1w']['up']['rate'] <= 1)

    def test_scoring_uses_returns(self):
        rec = {'tickers': ['A', 'B'], 'base': {'1w': [0.5, 0.45, 0.4]},
               'h': {'1w': {'pu': [900, 100], 'pb': [800, 100], 'ps': [100, 800], 'e': [50, 50], 'c': [1000, 1000], 'side': 'bs'}}}
        C = np.array([[10.0, 11.0], [10.0, 9.0]])
        C = np.tile(C, (15, 1))                                      # 30 rows (A, B, A, B, …) so the scorer has enough names
        tick = [f'X{i}' for i in range(30)]
        rec['tickers'] = tick
        for k in ('pu', 'pb', 'ps', 'e', 'c'):
            rec['h']['1w'][k] = rec['h']['1w'][k] * 15
        rec['h']['1w']['side'] = 'bs' * 15
        pos = {t: i for i, t in enumerate(tick)}
        sc = O.score_origin(rec, '1w', 1, C, 0, 1, pos)
        self.assertAlmostEqual(sc['up']['rate'], 0.5)
        self.assertEqual(sc['flag_buy']['hit'], 1.0)                   # +10% less 0.1%
        self.assertEqual(sc['flag_short']['hit'], 1.0)                 # −10%: the short made money
        self.assertLess(sc['up']['brier'], 0.05)


class Etf(unittest.TestCase):
    def test_loader(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'public').mkdir()
            (root / 'cache' / 'market').mkdir(parents=True)
            F = ['symbol', 'name', 'asset_class', 'category', 'vol', 'leveraged', 'inverse']
            rows = [['AAA', 'A fund', 'Equity', 'Large Blend', 0.18, True, False], ['BIL', 'T-bills', 'Fixed income', 'Ultrashort Bond', 0.004, False, False],
                    ['SPY', 'S&P 500', 'Equity', 'Large Blend', 0.16, False, False]]
            (root / 'public' / 'index.json').write_text(json.dumps({'fields': F, 'rows': rows}))
            start = dt.date(2010, 1, 4)                                  # a Monday: Yahoo's weekly bars
            for sym, g in (('AAA', 0.002), ('BIL', 0.0001), ('SPY', 0.0015)):
                w = [[(start + dt.timedelta(days=7 * i)).isoformat(), 100 * (1 + g) ** i, 90 * (1 + g) ** i, 1000 + i] for i in range(200)]
                (root / 'cache' / 'market' / f'{sym}.json').write_text(json.dumps({'weekly': w}))
            P = O.load_etf_panel(root)
            self.assertEqual(P['tickers'], ['AAA', 'SPY'])               # the cash-like fund left out
            self.assertEqual(P['left_out_cash_like'], 1)
            j = int(np.where(np.isfinite(P['C'][0]))[0][0])
            self.assertEqual(str(P['dates'][j]), '2010-01-08')          # Monday's bar → that week's Friday
            self.assertAlmostEqual(P['C'][0, j], 90.0)                   # the adjusted (total-return) close
            self.assertAlmostEqual(P['V'][0, j], 1000 * 100.0)           # dollar volume
            self.assertEqual(P['sectors'], ['Equity', 'Equity'])         # a category under 8 funds → the asset class
            self.assertEqual(P['floor'], O.ETF_FLOOR)
            self.assertEqual(list(P['no_short']), [True, False])             # leveraged: never flagged short


if __name__ == '__main__':
    unittest.main()
