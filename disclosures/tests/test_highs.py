"""At the highs (app/highs.py): runs of all-time highs, the first 5 / 10 / 20% pullback and the run's peak on a hand-made
path, still-open outcomes kept as censored, Kaplan–Meier by hand, split-restated point-in-time EPS, the volume ratio,
and the published file and per-asset blocks from the move-odds build."""
import datetime as dt
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
try:
    import numpy as np
    import highs as H
except ImportError:                                          # numpy is part of the analysis extras
    np = None


def weekdays(start, n):
    d, out = dt.date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


@unittest.skipIf(np is None, 'numpy not installed')
class Path_(unittest.TestCase):
    def frame(self):
        # 300 flat-to-rising days, a run of highs, a 12% pullback, recovery, a second run, a 6% dip, the end
        c = list(np.linspace(50, 100, 300))                      # every day an ATH (days 0-299)
        c += list(np.linspace(99, 87.5, 12))                     # 300-311: down to −12.5% (the 10% pullback at 309)
        c += list(np.linspace(89, 100.5, 12))                    # 312-323: back above 100 at 323
        c += list(np.linspace(102, 110, 9))                      # 324-332: a second run of highs
        c += list(np.linspace(108, 104, 5))                      # 333-337: a dip of about 5.5%, still open
        return np.array(c)

    def test_runs_and_pullbacks(self):
        c = self.frame()
        F = H.asset_frame(c)
        n = len(c)
        self.assertTrue(F['ath'][299] and not F['ath'][300])
        first10 = int(np.argmax(c / np.maximum.accumulate(c) - 1 <= -0.10))
        self.assertEqual(F['t10'][299], first10 - 299)           # the first close 10% under the high
        self.assertEqual(F['peak'][250], 299)                    # the run's peak: its last ATH before the pullback
        self.assertEqual(F['run_left'][250], 49)
        self.assertEqual(F['highs_left'][250], 49)
        self.assertTrue(F['ended'][250])
        self.assertEqual(first10, 309)
        self.assertAlmostEqual(F['pull_depth'][250], 87.5 / 100 - 1, places=9)   # the drawdown that ended the run
        self.assertTrue(F['pull_closed'][250])
        self.assertEqual(F['pull_days'][250], 323 - 299)         # back above the peak at 323
        # the second run started at the first ATH after the 10% pullback
        self.assertEqual(F['run_start'][330], 323)
        self.assertEqual(F['age'][330], 7)
        # still waiting: no 10% pullback after the second run — censored at the end, the run not ended
        self.assertFalse(F['ended'][330])
        self.assertEqual(F['t10'][330], n - 330)
        self.assertTrue(np.isfinite(F['t5'][330]) and F['t5'][330] < n - 330)   # the 5% dip happened
        self.assertFalse(F['high'][337])                         # 104 / 110: 5.45% under the high
        runs = H.own_runs(F)
        self.assertEqual(runs[0][:3], (0, 299, 299))

    def test_high_days(self):
        F = H.asset_frame(self.frame())
        self.assertTrue(F['high'][300])                          # day 300: 1% under, an ATH the day before
        self.assertFalse(F['high'][305])                         # more than 5% under the high
        self.assertFalse(F['high'][100])                         # under a year of history: not counted


@unittest.skipIf(np is None, 'numpy not installed')
class Pieces(unittest.TestCase):
    def test_km_by_hand(self):
        # times 2, 3 (censored), 5, 5, 8: S(2) = 4/5, S(5) = 4/5 · (1 − 2/3) = 4/15, median at 5
        r = H.km([2, 3, 5, 5, 8], [True, False, True, True, True], grid=[0, 2, 4, 5, 8])
        self.assertEqual(r['median'], 5)
        self.assertEqual(r['curve'], [1.0, 0.8, 0.8, round(4 / 15, 3), 0.0])
        self.assertEqual(r['events'], 4)

    def test_splits_restated(self):
        recs = [{'end': '2013-12-28', 'filed': '2014-01-28', 'eps': 3.625, 'shares': 3.6e9},
                {'end': '2014-03-29', 'filed': '2014-04-24', 'eps': 2.905, 'shares': 3.5e9},
                {'end': '2014-06-28', 'filed': '2014-07-23', 'eps': 0.32, 'shares': 24.2e9},      # 7-for-1
                {'end': '2014-09-27', 'filed': '2014-10-27', 'eps': 0.355, 'shares': 23.9e9}]
        fx = H.fix_splits(recs)
        self.assertAlmostEqual(fx[1][2], 2.905 / 7, places=9)
        self.assertAlmostEqual(fx[0][2], 3.625 / 7, places=9)
        self.assertAlmostEqual(fx[2][2], 0.32, places=9)
        # a share issue that is no split ratio, or EPS not moving with it, leaves EPS alone
        merger = [{'end': '2014-03-29', 'filed': '2014-04-24', 'eps': 1.0, 'shares': 1e9}, {'end': '2014-06-28', 'filed': '2014-07-23', 'eps': 0.9, 'shares': 2.3e9}]
        self.assertEqual([r[2] for r in H.fix_splits(merger)], [1.0, 0.9])
        fake = [{'end': '2014-03-29', 'filed': '2014-04-24', 'eps': 1.0, 'shares': 1e9}, {'end': '2014-06-28', 'filed': '2014-07-23', 'eps': 1.1, 'shares': 2e9}]
        self.assertEqual([r[2] for r in H.fix_splits(fake)], [1.0, 1.1])

    def test_trailing_eps_point_in_time(self):
        recs = [('2020-05-01', '2020-03-31', 1.0), ('2020-08-01', '2020-06-30', 1.0), ('2020-11-01', '2020-09-30', 1.0),
                ('2021-02-01', '2020-12-31', 2.0), ('2021-05-01', '2021-03-31', 1.5)]
        days = ['2021-01-29', '2021-02-01', '2021-04-30', '2021-05-03', '2022-01-03']
        e = H.ttm_eps(days, recs)
        self.assertTrue(math.isnan(e[0]))                        # the fourth quarter not filed yet
        self.assertEqual(e[1], 5.0)
        self.assertEqual(e[2], 5.0)
        self.assertEqual(e[3], 5.5)
        self.assertTrue(math.isnan(e[4]))                        # the last quarter on file is too old

    def test_volume_ratio(self):
        days = weekdays('2020-01-01', 400)
        v = [100.0] * 300 + [200.0] * 100
        r = H.volume_ratio(days, days, v)
        self.assertTrue(math.isnan(r[50]))                       # under a year of volume
        self.assertAlmostEqual(r[250], 1.0)
        self.assertAlmostEqual(r[399], 200 / ((161 * 100 + 100 * 200) / 261), places=2)   # 3 months at 200 vs the year's mean

    def test_own_percentile_has_no_look_ahead(self):
        x = np.arange(1000, dtype=float)
        p = H.own_pct(x, min_hist=100, refresh=10)
        self.assertTrue(np.isnan(p[50]))
        self.assertEqual(p[500], 100.0)                          # a new high of its own history
        y = x.copy(); y[600:] = -1                               # later values change nothing before them
        self.assertEqual(H.own_pct(y, min_hist=100, refresh=10)[500], 100.0)


@unittest.skipIf(np is None, 'numpy not installed')
class Build(unittest.TestCase):
    def universe(self, n_assets=12, n=1400, seed=3):
        rng = np.random.default_rng(seed)
        days = weekdays('2015-01-01', n)
        data, assets, eps = {}, [], {}
        for i in range(n_assets):
            c = 50 * np.exp(np.cumsum(rng.normal(0.0006, 0.015 + 0.002 * i, n)))
            if i == 0:                                           # the last one at its highs now
                c[-60:] = c[-61] * np.exp(np.linspace(0.001, 0.08, 60))
                c[-60:] = np.maximum(c[-60:], np.maximum.accumulate(c)[-61] * np.exp(np.linspace(0.001, 0.08, 60)))
            key = f'C{i}'
            data[key] = (days, c.tolist(), float(c[-1]))
            assets.append({'key': key, 'kind': 'stock', 'cik': 1000 + i, 'name': key})
            eps[str(1000 + i)] = [{'end': (dt.date(2015, 3, 31) + dt.timedelta(days=91 * q)).isoformat(),
                                   'filed': (dt.date(2015, 5, 1) + dt.timedelta(days=91 * q)).isoformat(), 'eps': 0.5 + 0.01 * q, 'shares': 1e9} for q in range(22)]
        spy = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, n)))
        data['SPY'] = (days, spy.tolist(), float(spy[-1]))
        assets.append({'key': 'SPY', 'kind': 'market', 'name': 'S&P 500 (SPY)'})
        return data, assets, eps

    def test_file_and_blocks(self):
        data, assets, eps = self.universe()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'highs.json'
            doc, blocks = H.build(data, assets, eps=eps, out_path=out, verbose=False)
            back = json.loads(out.read_text())
        self.assertEqual(back['schema'], 'highs.v1')
        self.assertEqual(set(back['groups']), {'companies', 'funds'})
        G = back['groups']['companies']
        self.assertGreater(G['base']['days'], 100)
        self.assertEqual(len(G['base']['t10']['curve']), len(H.GRID))
        self.assertIn('pe', G['buckets'])
        for f, b in G['buckets'].items():
            self.assertEqual(len(b['rows']), len(H.BUCKETS[f][2]))
            self.assertEqual(sum(r['days'] for r in b['rows']) <= G['base']['days'], True)
        self.assertTrue(any(r['key'] == 'C0' for r in back['now']))
        c0 = next(r for r in back['now'] if r['key'] == 'C0')
        self.assertTrue(c0['state']['high'])
        self.assertEqual(c0['state']['dd'], 0.0)
        a = c0.get('analogues')
        self.assertIsNotNone(a)
        self.assertLessEqual(a['days'], H.K_ANALOG)
        self.assertNotIn('nearest', a)                           # the list stays light: curves and nearest days in the asset's file
        self.assertNotIn('curve', a['t10'])
        full = blocks['C0']['analogues']
        self.assertEqual(len(full['t10']['curve']), len(H.GRID))
        self.assertNotIn('C0', {e['key'] for e in full['nearest'] if e['date'] > data['C0'][0][-252]})   # none of its own last year
        self.assertIn('pe_pct', H.FEATURES)
        self.assertEqual(set(blocks), {a['key'] for a in assets})
        self.assertIn('own', blocks['C3'])
        self.assertIsNotNone(blocks['C0']['state']['pe'])        # P/E from the EPS store
        json.dumps(back, allow_nan=False)


@unittest.skipIf(np is None, 'numpy not installed')
class InTheMoveOdds(unittest.TestCase):
    def test_moves_build_publishes_the_highs(self):
        import moves as M
        import paths as P
        with tempfile.TemporaryDirectory() as tmp:
            root, val, epsd = Path(tmp) / 'pth', Path(tmp) / 'val', Path(tmp) / 'eps'
            epsd.mkdir()
            days = weekdays('2021-01-04', 900)
            rng = np.random.default_rng(5)

            def put(t, drift=0.0005, scale=0.012):
                c = list(100 * np.exp(np.cumsum(rng.normal(drift, scale, len(days)))))
                P.save(root, t, {'ticker': t, 'source': 'yahoo', 'fetched_at': '2026-01-01T00:00:00+00:00', 't': list(days), 'o': c, 'h': c, 'l': c,
                                 'c': c, 'ac': c, 'v': [1000 + 10 * (i % 7) for i in range(len(days))]})
            for t in ('SPY', 'XLK'):
                put(t)
            rows = []
            for i in range(4):
                t = f'CO{i}'
                put(t, drift=0.001, scale=0.02)
                rows.append([1000 + i, t, f'COMPANY {i} INC', 'technology', 'industrial', 1e9 * (10 - i)])
                (val / 'c').mkdir(parents=True, exist_ok=True)
                (val / 'c' / f'{1000 + i}.json').write_text(json.dumps({'cik': 1000 + i, 'industry': 'Semis', 'sic': '3674'}))
                (epsd / f'{1000 + i}.json').write_text(json.dumps({'records': [
                    {'end': (dt.date(2021, 3, 31) + dt.timedelta(days=91 * q)).isoformat(), 'filed': (dt.date(2021, 5, 1) + dt.timedelta(days=91 * q)).isoformat(),
                     'eps': 0.6, 'shares': 1e9} for q in range(14)]}))
            (val / 'index.json').write_text(json.dumps({'fields': ['cik', 'ticker', 'name', 'sector', 'kind', 'mcap'], 'rows': rows}))
            st = M.build(root, val / 'index.json', eps_dir=epsd)
            self.assertEqual(st['errors'], [])
            out = root / 'public' / 'moves'
            hd = json.loads((out / 'highs.json').read_text())
            self.assertIn('companies', hd['groups'])
            self.assertEqual(st['highs']['eps_companies'], 4)
            doc = json.loads((out / 'a' / 'CO0.json').read_text())
            self.assertIn('highs', doc)
            self.assertEqual(doc['highs']['state']['date'], days[-1])
            self.assertIsNotNone(doc['highs']['state']['volu'])       # the volume of the bars on file
            self.assertTrue(any(json.loads((out / 'a' / f'CO{i}.json').read_text())['highs']['state'].get('pe') for i in range(4)))


if __name__ == '__main__':
    unittest.main()
