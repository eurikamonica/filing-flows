"""forecast_ledger.py: a published forecast is frozen and never rewritten; outcomes and gaps are filled only after the
target period has closed."""
import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
try:
    import numpy as np
    import sklearn  # noqa: F401
    import forecast_ledger as FL
except ImportError:
    np = None


def chaos_doc(origins, price_mult=1.0, tickers=('AAA', 'BBB')):
    """A minimal chaos-forecast.json: one row per ticker per origin."""
    tg = [o[:4] + '-' + f'{int(o[5:]) % 12 + 1:02d}' if int(o[5:]) < 12 else f'{int(o[:4]) + 1}-01' for o in origins]
    comp = {}
    for t in tickers:
        comp[t] = [[i, [0.5], [1.0], 0.1, 100.0, 102.0 * price_mult, 90.0, 115.0, 1] for i in range(len(origins))]
    return {'vars': ['rel'], 'origins': list(origins), 'targets': tg, 'companies': comp}


@unittest.skipIf(np is None, 'numpy / scikit-learn not installed')
class Freeze(unittest.TestCase):
    def test_first_run_seeds_backtest_and_freezes_live(self):
        L = {'freq': 'm', 'origins': []}
        doc = chaos_doc(['2026-07', '2026-08', '2026-09'])
        added = FL.freeze(L, FL.entries_from_chaos(doc), '2026-09', 'sha1', 't1')
        self.assertEqual(added, [('2026-07', 'backtest'), ('2026-08', 'backtest'), ('2026-09', 'live')])
        self.assertEqual(L['started'], '2026-09')
        live = L['origins'][-1]
        self.assertEqual((live['made_at'], live['code']), ('t1', 'sha1'))
        self.assertIsNone(L['origins'][0]['made_at'])

    def test_live_forecast_is_never_rewritten(self):
        L = {'freq': 'm', 'origins': []}
        FL.freeze(L, FL.entries_from_chaos(chaos_doc(['2026-08', '2026-09'])), '2026-09', 'sha1', 't1')
        # the next build recomputes the same origin with different numbers and a new company
        doc2 = chaos_doc(['2026-08', '2026-09'], price_mult=1.5, tickers=('AAA', 'BBB', 'CCC'))
        FL.freeze(L, FL.entries_from_chaos(doc2), '2026-09', 'sha2', 't2')
        live = L['origins'][-1]
        self.assertEqual(live['rows']['AAA'][1], 102.0)               # unchanged
        self.assertEqual(live['code'], 'sha1')
        self.assertIn('CCC', live['rows']); self.assertEqual(live['late'], ['CCC'])
        self.assertEqual(L['origins'][0]['rows']['AAA'][1], 102.0)    # backtest seed unchanged too
        # the late row has its own first publication (spec v5 §1.1): t2 and sha2, not the batch's t1 / sha1
        self.assertEqual((live['row_published'], live['row_code']), ({'CCC': 't2'}, {'CCC': 'sha2'}))
        self.assertEqual(live['made_at'], 't1')
        FL.freeze(L, FL.entries_from_chaos(doc2), '2026-09', 'sha3', 't3')   # seen again: nothing moves
        self.assertEqual(live['row_published'], {'CCC': 't2'})

    def test_new_origin_becomes_live_and_missed_ones_are_not_backfilled(self):
        L = {'freq': 'm', 'origins': []}
        FL.freeze(L, FL.entries_from_chaos(chaos_doc(['2026-07'])), '2026-07', 's', 't1')
        # two months later (a missed month): 2026-08 never was live, 2026-09 is
        doc = chaos_doc(['2026-07', '2026-08', '2026-09'], price_mult=1.2)
        added = FL.freeze(L, FL.entries_from_chaos(doc), '2026-09', 's2', 't3')
        self.assertEqual(added, [('2026-09', 'live')])
        self.assertEqual([e['origin'] for e in L['origins']], ['2026-07', '2026-09'])
        self.assertEqual(L['origins'][0]['rows']['AAA'][1], 102.0)


@unittest.skipIf(np is None, 'numpy / scikit-learn not installed')
class Resolve(unittest.TestCase):
    def closes(self, start='2026-06-05', n=30, step=1.0):
        days = np.datetime64(start) + 7 * np.arange(n)
        return (days, 100.0 + step * np.arange(n))

    def test_outcome_only_after_the_target_closes(self):
        L = {'freq': 'm', 'origins': []}
        FL.freeze(L, FL.entries_from_chaos(chaos_doc(['2026-08', '2026-09'])), '2026-09', 's', 't')
        c = self.closes()
        FL.resolve_calendar(L, {'AAA': c, 'BBB': c}, '2026-10-16')
        done, pending = L['origins']
        self.assertEqual(done['target'], '2026-09')
        self.assertIn('AAA', done['outcome'])
        self.assertEqual(pending['outcome'], {})                     # October has not closed on 2026-10-16
        # the close used is the last Friday on or before the target month's end (2026-09-25 -> index 16)
        self.assertAlmostEqual(done['outcome']['AAA'][0], 116.0)

    def test_gaps(self):
        e = {'rows': {'AAA': [100.0, 102.0, 90.0, 115.0, 0.5, 1], 'BBB': [100.0, 98.0, 90.0, 110.0, -0.5, 1]},
             'outcome': {'AAA': [120.0], 'BBB': [95.0]}}
        rows, s = FL.score_calendar(e)
        self.assertEqual(rows['AAA'], [2.0, 20.0, 18.0, False, True])  # +2% forecast, +20% actual, outside 90–115
        self.assertEqual(rows['BBB'], [-2.0, -5.0, -3.0, True, True])
        self.assertEqual((s['n'], s['resolved'], s['direction_hit'], s['inside80']), (2, 2, 1.0, 0.5))

    def test_relative_hit_ignores_market_direction(self):
        fc = list(range(10)); ac = [10 + v for v in range(10)]          # everything up; ranks agree
        self.assertEqual(FL._relative_hit(fc, ac), 1.0)
        self.assertEqual(FL._relative_hit(fc, ac[::-1]), 0.0)

    def test_update_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            pub = Path(d) / 'public'; (pub / 't').mkdir(parents=True)
            days0 = '2026-06-05'
            for t in ('AAA', 'BBB'):
                (pub / 't' / f'{t}.json').write_text(json.dumps({'start': days0, 'c': [100 + i for i in range(20)]}))
            (pub / 'chaos-forecast-monthly.json').write_text(json.dumps(chaos_doc(['2026-08', '2026-09'])))
            (pub / 'rrg.json').write_text(json.dumps({'weeks': '2026-10-16', 'start': days0}))
            out = FL.update(d, 'abc', verbose=False)
            self.assertEqual([o['source'] for o in out['freqs']['m']['origins']], ['backtest', 'live'])
            self.assertTrue((Path(d) / 'ledger' / 'm.json').exists())
            det = json.loads((pub / 'forecast-ledger-m.json').read_text())
            self.assertEqual(len(det['rows']['2026-08']['AAA']), len(det['fields']))
            self.assertEqual(det['rows']['2026-09']['AAA'][-1], None)   # pending


if __name__ == '__main__':
    unittest.main()
