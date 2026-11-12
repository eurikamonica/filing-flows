"""rrg_backtest.py: the groups of the Move odds' lines, the levels and the weekly clock, the overlapping portfolios of a
quadrant mix (cash when empty, the equal weight when all four, bought and held), the turnover, the expected returns and
the files — on hand-made lines and on planted lines whose strength against SPY goes round in cycles, so a line above
its trend keeps rising for a while (the right half of the RRG beats the left over the next period). No network."""
import datetime as dt
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import paths as P  # noqa: E402
import rrg_backtest as B  # noqa: E402


def weekdays(start, n):
    d, out = dt.date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def universe(tmp, n=12, days=None, seed=3, cycle=130, amp=0.2, kind='sector', group='sector', extra=None):
    """public/moves/: index.json and a/<KEY>.json for SPY and n lines whose log strength against SPY is a sine of the
    given period (trading days) at a random phase, plus noise."""
    days = days or weekdays('1998-12-01', 2600)
    rng = np.random.default_rng(seed)
    base = Path(tmp) / 'moves'
    (base / 'a').mkdir(parents=True)
    T = len(days)
    spy = np.cumsum(np.concatenate([[0.0], rng.normal(0.0003, 0.01, T - 1)]))
    doc = P.encode_returns(days, list(100 * np.exp(spy)))
    doc.update(key='SPY', ticker='SPY', kind='market', group='market', name='S&P 500 (SPY)')
    (base / 'a' / 'SPY.json').write_text(json.dumps(doc))
    rows = [['SPY', 'market']]
    t = np.arange(T)
    for i in range(n):
        k = f'S{i:02d}'
        rs = amp * np.sin(2 * math.pi * t / cycle + rng.uniform(0, 2 * math.pi))
        c = 50 * np.exp(spy + rs + np.cumsum(rng.normal(0, 0.004, T)))
        if extra:
            c = extra(i, c)
        doc = P.encode_returns(days, list(c))
        doc.update(key=k, ticker=k, kind=kind, group=group, name=f'Line {i}')
        (base / 'a' / f'{k}.json').write_text(json.dumps(doc))
        rows.append([k, kind])
    (base / 'index.json').write_text(json.dumps({'fields': ['key', 'kind'], 'rows': rows}))
    return base


class Groups(unittest.TestCase):
    def test_group_of(self):
        g = lambda **d: B.group_of(d)                                     # noqa: E731
        self.assertEqual(g(key='XLK', kind='sector', group='sector'), 'sectors')
        self.assertEqual(g(key='QQQ', kind='market', group='market'), 'index_etfs')
        self.assertEqual(g(key='MTUM', kind='style', group='style'), 'styles')
        self.assertEqual(g(key='EWJ', kind='etf', group='country'), 'world')
        self.assertEqual(g(key='VTI', kind='etf', group='broad'), 'world')
        self.assertEqual(g(key='TLT', kind='etf', group='bonds'), 'bonds_commodities')
        self.assertEqual(g(key='GLD', kind='style', group='commodities'), 'bonds_commodities')
        self.assertEqual(g(key='SMH', kind='style', group='industry'), 'industry_etfs')
        self.assertEqual(g(key='SIC-1311', kind='industry'), 'industries')
        self.assertEqual(g(key='AAPL', kind='stock'), 'companies')
        self.assertIsNone(g(key='SPY', kind='market'))
        self.assertIsNone(g(key='^VIX', kind='volatility', group='volatility'))
        self.assertIsNone(g(key='^N225', kind='index', group='world'))

    def test_levels_and_weeks(self):
        L = np.array([[np.nan, 0.1, np.nan, 0.1], [0.0, 0.0, 0.0, 0.0]])
        lv = B.levels(L)
        self.assertTrue(np.isnan(lv[0, 0]))                              # before its first return
        self.assertAlmostEqual(lv[0, 2], lv[0, 1])                        # a day without a return: flat
        self.assertAlmostEqual(lv[0, 3] / lv[0, 1], math.exp(0.1))
        cal = ['2024-03-26', '2024-03-27', '2024-03-28', '2024-04-01', '2024-04-02']   # Good Friday: the week ends Thursday
        self.assertEqual(B.grid(cal, 'w').tolist(), [2, 4])               # the latest close ends the last week
        self.assertEqual(B.grid(cal, 'd').tolist(), [0, 1, 2, 3, 4])


class Portfolios(unittest.TestCase):
    def test_mix_mechanics(self):
        T = 8
        C = np.vstack([1.1 ** np.arange(T), np.ones(T)])                  # one line +10% a period, one flat
        q = np.vstack([np.full(T, 3), np.full(T, 2)]).astype(np.int8)     # improving, lagging throughout
        res = B.portfolios(C, q, 0, (1, 2))
        r = lambda S, K: res[(S, K)]['r']                                 # noqa: E731
        self.assertTrue(np.allclose(r((3,), 1)[1:], 0.1))
        self.assertTrue(np.allclose(r((3,), 2)[2:], 0.1))
        self.assertTrue(np.allclose(r((2,), 1), 0.0))
        self.assertTrue(np.allclose(r((0,), 1), 0.0))                     # nothing Leading: cash
        self.assertEqual(float(res[((0,), 1)]['n'].sum()), 0.0)
        self.assertTrue(np.all(np.isnan(res[((0,), 1)]['R'])))            # no portfolio to judge
        self.assertTrue(np.allclose(r((0, 1, 2, 3), 1)[1:], 0.05))        # the equal weight, rebalanced each period
        # held two periods: each portfolio bought and held (1.1 + 1) ÷ 2, then (1.21 + 1) ÷ 2; the strategy averages
        # the two it holds
        second = (1.21 + 1) / 2 / ((1.1 + 1) / 2) - 1
        self.assertTrue(np.allclose(r((0, 1, 2, 3), 2)[2:], (0.05 + second) / 2))
        self.assertAlmostEqual(float(res[((2, 3), 2)]['R'][0]), (1.21 + 1) / 2 - 1)    # a portfolio two periods on
        self.assertTrue(np.isnan(res[((2, 3), 2)]['R'][T - 2]))           # its outcome not known yet
        self.assertTrue(np.allclose(res[((3,), 1)]['tv'][1:], 0.0))       # the same line throughout: nothing traded

    def test_turnover(self):
        T = 10
        C = np.ones((2, T))
        q = np.vstack([np.where(np.arange(T) % 2 == 0, 0, 2), np.full(T, 0)]).astype(np.int8)  # in and out of Leading
        res = B.portfolios(C, q, 0, (1,))
        tv = res[((0,), 1)]['tv'][1:]
        self.assertTrue(np.allclose(tv, 1.0))                             # half the names change each period: 2 × ½
        tv2 = res[((2,), 1)]['tv'][1:]
        self.assertTrue(np.allclose(tv2, 1.0))                            # into a line from cash and back: one way, all of it


class Build(unittest.TestCase):
    def test_cycles(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = universe(tmp)
            index = B.build(base, Path(tmp) / 'out', log=lambda m: None)
            docs = {c: json.loads((Path(tmp) / 'out' / f'{c}-sectors.json').read_text()) for c in ('w', 'd')}
            on_disk = json.loads((Path(tmp) / 'out' / 'index.json').read_text())
        self.assertEqual(on_disk['groups'][0]['key'], 'sectors')
        self.assertEqual(set(on_disk['groups'][0]['clocks']), {'w', 'd'})
        self.assertEqual(index['mixes'][0], 'leading')
        self.assertEqual(len(index['mixes']), 15)
        for c, d in docs.items():
            self.assertEqual(d['schema'], B.SCHEMA)
            self.assertEqual(d['holds'], list(B.CLOCKS[c]['holds']))
            self.assertEqual(len(d['series']), 15 * 3 + 2)
            self.assertTrue(all(len(v) == len(d['months']) for v in d['series'].values()))
            self.assertEqual(d['months'][-1], d['as_of'])
            self.assertEqual(d['series']['ew'], d['series']['leading+weakening+lagging+improving|1'])
            self.assertEqual(d['stats']['spy']['all']['beta'], 1.0)
            self.assertGreaterEqual(d['formed_from'], B.FIRST)
            # a line above its trend keeps rising for a while: the right half beats the left over the next period
            K = d['holds'][0]
            right, left = d['stats'][f'leading+weakening|{K}']['all'], d['stats'][f'lagging+improving|{K}']['all']
            self.assertGreater(right['cagr'] - left['cagr'], 0.05, c)
            e_r, e_l = d['expect'][f'leading+weakening|{K}']['all'], d['expect'][f'lagging+improving|{K}']['all']
            self.assertGreater(e_r['excess'], 0, c)
            self.assertLess(e_l['excess'], 0, c)
            self.assertLessEqual(e_r['lo'], e_r['mean'])
            self.assertGreaterEqual(e_r['hi'], e_r['mean'])
            self.assertGreater(e_r['n'], e_r['n_indep'] - 1)
            self.assertGreater(e_r['excess_ew'], 0, c)                     # ahead of the equal weight too
            self.assertTrue(0 <= e_r['beat_ew'] <= 1 and e_r['ew'] is not None)
            e_all = d['expect']['leading+weakening+lagging+improving|1']['all']
            self.assertAlmostEqual(e_all['excess_ew'], 0.0, places=5)       # the equal weight against itself
            # longer holds trade less a day
            self.assertGreater(d['turn'][f'improving|{K}'], d['turn'][f'improving|{d["holds"][-1]}'])
            self.assertTrue(0 < d['invested']['improving|1'] <= 1)
            self.assertNotIn('spy', d['turn'])
            # now: every line with a point, its name, quadrant and how long it has stood there
            self.assertEqual(d['now']['fields'], ['key', 'name', 'x', 'y', 'q', 'periods'])
            self.assertEqual(len(d['now']['rows']), 12)
            self.assertTrue(all(r[4] in (0, 1, 2, 3) and r[5] >= 1 for r in d['now']['rows']))
            q = {r[0]: r[4] for r in d['now']['rows']}
            x = {r[0]: r[2] for r in d['now']['rows']}
            self.assertTrue(all((x[k] >= 100) == (q[k] in (0, 1)) for k in q if abs(x[k] - 100) > 0.01))   # right of 100: Leading / Weakening

    def test_bad_prints_and_companies(self):
        def jump(i, c):
            if i == 2:
                c = c.copy()
                c[900:] *= 258.0
            return c
        with tempfile.TemporaryDirectory() as tmp:
            base = universe(tmp, n=6, kind='stock', group=None, extra=jump)
            cal, spy, meta, L = B.load(base)
            self.assertEqual({m['group'] for m in meta}, {'companies'})
            self.assertAlmostEqual(float(np.nanmax(L)), math.log(2.0), places=5)
            B.build(base, Path(tmp) / 'out', clocks=('w',), log=lambda m: None)
            d = json.loads((Path(tmp) / 'out' / 'w-companies.json').read_text())
        self.assertEqual(d['now']['fields'], ['key', 'x', 'y', 'q', 'periods'])          # companies: tickers only
        self.assertEqual(d['label'], 'Companies against the S&P 500')


if __name__ == '__main__':
    unittest.main()
