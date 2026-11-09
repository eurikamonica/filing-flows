"""Momentum factors (app/momentum.py): the formulas on a hand-made path (pinned to the same numbers as
tests/test_momentum_view.cjs, so the browser and the build agree), no look-ahead, the 10-month rule, Yahoo's Monday
bars moved to their Friday, percentiles with ties, and the published files (monthly ranks from m0, the latest week with
the sector-relative return and the rank inside a peer group)."""
import datetime as dt
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import momentum as MO  # noqa: E402

C = [100 * math.exp(0.004 * t + 0.03 * math.sin(t / 5)) for t in range(200)]
C[60] = None                                                 # one missing week
B = [100 * math.exp(0.002 * t) for t in range(200)]
S = [100 * math.exp(0.003 * t + 0.01 * math.cos(t / 7)) for t in range(200)]
PINNED = {'m12_1': 0.15901493112293696, 'm6_1': 0.07662205144700773, 'm3_1': -0.01092402959835781, 'm1': 0.010383231119272196,
          'hi52': -0.0006542252031591644, 'vol': 0.029017317337332402, 'ra12': 5.480001106730682, 'comp': 2.764996195310579,
          'rel_b': 0.051570447038167266, 'rel_s': 0.009168154964303454, 'rs': 105.5379209548509, 'rcomp': 0.34307782922918933}


class Factors(unittest.TestCase):
    def test_pinned_and_by_hand(self):
        f = MO.factors(C, B, S)[150]
        for k, v in PINNED.items():
            self.assertAlmostEqual(f[k], v, places=10, msg=k)
        self.assertAlmostEqual(f['m12_1'], C[146] / C[98] - 1, places=12)
        self.assertAlmostEqual(f['rel_b'], math.log(C[146] / C[98]) - math.log(B[146] / B[98]), places=12)
        self.assertAlmostEqual(f['rs'], 100 * (C[150] / B[150]) / (C[98] / B[98]), places=9)
        lg = [math.log(x) if x else None for x in C]
        r = [lg[i] - lg[i - 1] for i in range(99, 151)]
        m = sum(r) / len(r)
        sd = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))
        self.assertAlmostEqual(f['vol'], sd * math.sqrt(52), places=12)
        z = sum((lg[146] - lg[150 - w]) / (sd * math.sqrt(w - 4)) for w in (13, 26, 52)) / 3
        self.assertAlmostEqual(f['comp'], z, places=10)
        self.assertAlmostEqual(f['hi52'], C[150] / max(C[98:151]) - 1, places=12)

    def test_volatility_floor(self):
        # a cash-like fund (≈ 4% a year, almost no volatility): the scores use the weekly floor of 0.4%, not its own σ
        T = [100 * math.exp(0.0008 * t + 0.0002 * math.sin(t)) for t in range(120)]
        f = MO.factors(T)[100]
        lg = [math.log(x) for x in T]
        self.assertLess(f['vol'], 0.002)                                  # its own volatility: under 0.2% a year
        self.assertAlmostEqual(f['comp'], sum((lg[96] - lg[100 - w]) / (0.004 * math.sqrt(w - 4)) for w in (13, 26, 52)) / 3, places=12)
        self.assertAlmostEqual(f['comp'], 0.9958144998789363, places=10)  # tests/test_momentum_view.cjs: the same
        self.assertAlmostEqual(f['ra12'], f['m12_1'] / (0.004 * math.sqrt(52)), places=12)
        self.assertAlmostEqual(f['ra12'], 1.3697959597944076, places=10)

    def test_no_look_ahead_and_missing(self):
        full = MO.factors(C, B, S)
        for k in (120, 160):
            part = MO.factors(C[:k], B[:k], S[:k])
            for t in range(k):
                self.assertEqual(part[t] is None, full[t] is None)
                if part[t]:
                    for key, v in part[t].items():
                        if v is None:
                            self.assertIsNone(full[t][key], (t, key))
                        else:
                            self.assertAlmostEqual(v, full[t][key], places=9, msg=(t, key))
        self.assertIsNone(full[60])                           # no close, no reading
        self.assertIsNone(full[40]['m12_1'])                  # under a year of history
        self.assertIsNone(full[112]['m12_1'])                 # P[t−52] is the missing week
        self.assertIsNotNone(full[100]['comp'])               # 50 of 52 weekly returns are enough
        self.assertIsNone(MO.factors(C)[150]['rel_b'])        # no benchmark, no relative momentum

    def test_month_ends_ten_month_rule_and_fridays(self):
        weeks = MO.friday_grid(dt.date(2024, 1, 1), dt.date(2024, 4, 1))
        self.assertEqual(weeks[0], '2024-01-05')
        me = MO.month_ends(weeks)
        self.assertEqual([weeks[i] for i in me], ['2024-01-26', '2024-02-23', '2024-03-29'])
        c = list(range(1, 60))
        ts = MO.ten_month_rule(c, list(range(0, 50, 4)))
        self.assertEqual(sorted(ts), [36, 40, 44, 48])
        self.assertTrue(all(ts.values()))                     # a rising line is above its ten-month average
        self.assertEqual(MO.friday(dt.date(2024, 1, 8)).isoformat(), '2024-01-12')    # Monday → that Friday
        self.assertEqual(MO.friday(dt.date(2024, 1, 14)).isoformat(), '2024-01-12')   # Sunday → the same week's
        grid = MO.friday_grid(dt.date(2024, 1, 5), dt.date(2024, 3, 1))
        rows = [['2024-01-08', 10], ['2024-01-15', 11], ['2024-01-19', 11.5], ['2024-02-05', 12], ['2024-02-26', 13]]
        f, c = MO.on_grid(rows, grid)
        self.assertEqual(grid[f], '2024-01-12')
        # the last bar of a week wins; the gap of 2024-01-26 and 02-02 carried (two weeks), 02-16 and 02-23 too
        self.assertEqual(c, [10, 11.5, 11.5, 11.5, 12, 12, 12, 13])

    def test_latest_week(self):
        weeks = MO.friday_grid(dt.date(2024, 1, 5), dt.date(2025, 12, 26))
        n = len(weeks)
        s = {f'A{k}': (0, [1.0] * n) for k in range(9)}
        s['DEAD'] = (0, [1.0] * (n - 60))        # stopped more than a quarter before the newest close: not counted
        s['LAG'] = (0, [1.0] * (n - 1))          # without the newest week: 9 of the 10 live tickers have it
        self.assertEqual(MO.latest_index(s, weeks), n - 1)
        s['LAG2'] = (0, [1.0] * (n - 1))         # two without it: 9 of 11, under 90%: the week before
        self.assertEqual(MO.latest_index(s, weeks), n - 2)
        self.assertIsNone(MO.latest_index({}, weeks))

    def test_percentiles(self):
        self.assertEqual(MO._pct({'a': 1, 'b': 2, 'c': 3, 'd': 4}), {})          # fewer than five: no ranks
        p = MO._pct({'a': 1, 'b': 2, 'c': 2, 'd': 3, 'e': 5, 'x': None, 'y': float('nan')})
        self.assertEqual(p, {'a': 0, 'b': 38, 'c': 38, 'd': 75, 'e': 100})


class Build(unittest.TestCase):
    def test_files(self):
        weeks = MO.friday_grid(dt.date(2015, 1, 2), dt.date(2019, 12, 27))
        n = len(weeks)
        mk = lambda mu, a, ph: [100 * math.exp(mu * t + a * math.sin(t / 6 + ph)) for t in range(n)]
        series = {f'T{k}': (0, mk(0.0005 * k, 0.05, k)) for k in range(8)}
        series['LATE'] = (n - 120, mk(0.003, 0.02, 1)[:120])        # listed two and a half years before the end
        series['SPY'], series['XLK'] = (0, mk(0.001, 0.0, 0)), (0, mk(0.0015, 0.02, 2))
        uni = [f'T{k}' for k in range(8)] + ['LATE']
        groups = {t: ('A' if t in ('T0', 'T1', 'T2', 'T3', 'T4') else 'B') for t in uni}
        with tempfile.TemporaryDirectory() as d:
            summ, latest = MO.build(d, series, weeks, uni, bench=series['SPY'], sector_of={'T7': 'XLK'}, groups=groups,
                                    name='momentum', start='2016-01-01', meta={'T7': {'n': 'Seven'}})
            self.assertEqual(summ['tickers'], 9)
            doc = json.loads((Path(d) / 'momentum' / 'T7.json').read_text())
            me = [i for i in MO.month_ends(weeks) if weeks[i] >= '2016-01-01']
            self.assertEqual(doc['m0'], weeks[me[0]])
            self.assertEqual(len(doc['rows']), len(me))
            self.assertEqual(doc['fields'], MO.FIELDS)
            self.assertTrue(all(0 <= v <= 100 for r in doc['rows'] if r for v in r if v is not None))
            self.assertNotIn('group', doc)                       # group B has four tickers: under five, no group rank
            d0 = json.loads((Path(d) / 'momentum' / 'T0.json').read_text())
            self.assertEqual(d0['group'], 'A')
            self.assertEqual(len(d0['group_comp']), len(d0['rows']))
            late = json.loads((Path(d) / 'momentum' / 'LATE.json').read_text())
            self.assertGreater(late['m0'], doc['m0'])            # its ranks start once it has a year of closes
            L = json.loads((Path(d) / 'momentum-latest.json').read_text())
            self.assertEqual(L['week'], weeks[-1])
            self.assertEqual(L['cols'][:len(MO.LATEST)], MO.LATEST)
            row = dict(zip(L['cols'], L['rows']['T7']))
            self.assertEqual(row['n'], 'Seven')
            f = MO.factors(series['T7'][1], series['SPY'][1], series['XLK'][1])[n - 1]
            self.assertAlmostEqual(row['m12_1'], f['m12_1'], places=4)
            self.assertAlmostEqual(row['rel_s'], f['rel_s'], places=4)
            self.assertAlmostEqual(row['rcomp'], f['rcomp'], places=4)
            self.assertIsNone(dict(zip(L['cols'], L['rows']['T0']))['rel_s'])     # no sector given
            comps = {t: latest[t]['comp'] for t in uni}
            best = max(comps, key=comps.get)
            self.assertEqual(latest[best]['p_comp'], 100)
            self.assertIn('p_comp_group', latest['T0'])
            self.assertIsNone(latest['LATE']['p_comp_group'])     # group B: no group rank


if __name__ == '__main__':
    unittest.main()
