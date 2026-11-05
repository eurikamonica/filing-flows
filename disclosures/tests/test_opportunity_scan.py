"""opportunity_scan.py: the combined score (alignment, weekly ranks, weights learnt only from earlier years, the
calibration, the buyer's test), this week's rows (merged sources, flags, packing, missing inputs), the scoreboard, the
ledger and a whole build without any forecast history; oos_store's files."""
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import forecast_book as FB
import oos_store
import opportunity_scan as S

nan = np.nan


def weeks(n, start='2010-01-01'):                   # 2010-01-01 is a Friday
    return np.datetime64(start) + 7 * np.arange(n)


class Store(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            X = np.array([[1.5, nan, -2.25], [1e6, 0.1, nan]], np.float32)
            p = oos_store.save(Path(d) / 'sub' / 'x.npz', ['A', 'B'], weeks(3), X, {'model': 'm'})
            self.assertTrue(p.exists())
            self.assertFalse(list((Path(d) / 'sub').glob('*.tmp.npz')), 'written whole, then moved into place')
            z = oos_store.load(p)
            self.assertEqual(z['tickers'], ['A', 'B'])
            self.assertTrue((z['dates'] == weeks(3).astype('datetime64[D]')).all())
            self.assertEqual(float(z['X'][0, 0]), 1.5)
            self.assertTrue(np.isnan(z['X'][0, 1]) and np.isnan(z['X'][1, 2]))
            self.assertEqual(float(z['X'][1, 0]), 6e4, "clipped into float16's range")
            self.assertEqual(z['meta']['model'], 'm')
            self.assertIn('saved_at', z['meta'])
            before = p.stat().st_mtime_ns, z['meta']['saved_at']
            oos_store.save(p, ['A', 'B'], weeks(3), X, {'model': 'm', 'saved_at': 'later'})
            self.assertEqual((p.stat().st_mtime_ns, oos_store.load(p)['meta']['saved_at']), before, 'the same forecasts: the file is left as it is')
            X2 = X.copy()
            X2[1, 1] = 0.2
            oos_store.save(p, ['A', 'B'], weeks(3), X2, {'model': 'm', 'saved_at': 'later'})
            self.assertEqual(oos_store.load(p)['meta']['saved_at'], 'later', 'a changed forecast is written')
            self.assertIsNone(oos_store.load(Path(d) / 'missing.npz'))
            (Path(d) / 'bad.npz').write_bytes(b'PK\x03\x04 torn')
            self.assertIsNone(oos_store.load(Path(d) / 'bad.npz'))


class Score(unittest.TestCase):
    def test_align(self):
        days = weeks(5)
        z = {'tickers': ['B', 'X', 'A'], 'dates': np.concatenate([days[[1, 2, 4]], [np.datetime64('2030-01-04')]]).astype('datetime64[D]'),
             'X': np.array([[1, 2, 3, 7], [9, 9, 9, 9], [4, 5, 6, 8]], np.float32)}
        out = S.align(z, ['A', 'B', 'C'], days)
        np.testing.assert_array_equal(out[0], [nan, 4, 5, nan, 6])
        np.testing.assert_array_equal(out[1], [nan, 1, 2, nan, 3])
        self.assertTrue(np.isnan(out[2]).all(), 'a name the model never saw stays empty')
        self.assertTrue(np.isnan(S.align(None, ['A'], days)).all())

    def test_pct_ranks(self):
        X = np.arange(60, dtype=float)[:, None].repeat(2, 1)
        ok = np.ones_like(X, bool)
        ok[:20, 1] = False                                   # week 1: 40 names, fewer than MIN_NAMES
        P = S.pct_ranks(X, ok)
        self.assertEqual(P[0, 0], 0.0)
        self.assertEqual(P[59, 0], 1.0)
        self.assertTrue(np.isnan(P[:, 1]).all())

    def test_weights_use_only_earlier_years(self):
        days = weeks(52 * 8)                                 # 2010–2017
        yrs = S.years_of(days)
        ics = {'a': np.where(yrs < 2016, 0.1, 10.0), 'b': np.full(len(days), -0.02)}
        w = S.weights_by_year(ics, days, [2016, 2017])
        self.assertAlmostEqual(w[2016]['a'], 0.1, msg="2016's weights see no week of 2016 (nor its outcomes)")
        self.assertEqual(w[2016]['b'], 0.0, 'a negative record weighs nothing')
        self.assertGreater(w[2017]['a'], 0.1, "2016's weeks count once their outcomes are known")
        self.assertEqual(S.weights_by_year({'a': np.full(len(days), nan)}, days, [2016])[2016], {'a': 1.0}, 'no record: equal weights')

    def test_combine_leaves_a_missing_model_out(self):
        days = weeks(3)
        pa = np.array([[0.2] * 3, [0.8] * 3])
        pb = np.array([[1.0] * 3, [nan] * 3])
        out = S.combine({'a': pa, 'b': pb}, {2010: {'a': 1.0, 'b': 3.0}}, days)
        self.assertAlmostEqual(out[0, 0], (0.2 + 3.0) / 4)
        self.assertAlmostEqual(out[1, 0], 0.8)

    def test_calibration_learns_from_the_years_before(self):
        # the top tenth beats SPY 80% of the time until 2016 and 20% from 2017: 2017's probabilities still come from
        # the years before (80%), and the test scores them against what happened
        rng = np.random.default_rng(3)
        days = weeks(52 * 7, '2012-01-06')
        yrs = S.years_of(days)
        N = 200
        Sc = np.repeat((np.arange(N) / (N - 1))[:, None], len(days), 1)
        top = (np.arange(N) >= 180)[:, None]
        p = np.where(top, np.where(yrs < 2017, 0.8, 0.2)[None], 0.5)
        Y = np.where(rng.random((N, len(days))) < p, 0.05, -0.05)
        Y[:, -S.H:] = nan                                     # the last 13 weeks' outcomes are not known yet
        P, test, now, base = S.calibrate(Sc, Y, np.ones_like(Y, bool), days)
        in17 = yrs == 2017
        self.assertTrue(np.isnan(P[:, yrs < S.TEST_FROM]).all(), 'nothing said before the first test year')
        self.assertAlmostEqual(float(np.nanmean(P[180:, in17])), 0.8, delta=0.03)
        self.assertAlmostEqual(float(np.nanmean(P[:100, in17])), 0.5, delta=0.03)
        self.assertEqual(len(test['table']), S.DECILES)
        self.assertLess(test['table'][-1]['happened'], test['table'][-1]['said'], 'the later reversal shows up in the test')
        self.assertEqual(len(now), S.DECILES)

    def test_buyers_test(self):
        X = np.arange(100.0)[:, None]
        Y = np.where(X >= 90, 0.1, np.where(X < 10, -0.1, 0.0))
        cost = np.full(X.shape, 0.01)
        vs_spy, vs_all, bot = S.top_tests(X, Y, np.ones_like(X, bool), cost)
        avg = (10 * math.expm1(0.1) + 10 * math.expm1(-0.1)) / 100
        self.assertAlmostEqual(vs_spy[0], math.expm1(0.1) - 0.02, msg='the top tenth, its costs in and out')
        self.assertAlmostEqual(vs_all[0], math.expm1(0.1) - avg - 0.02)
        self.assertAlmostEqual(bot[0], math.expm1(-0.1) - avg, msg='leaving a name out costs nothing')


def sources(asof='2026-10-30'):
    opp = {'asof': asof, 'fields_h': ['p_up', 'p_buy', 'r_p10', 'r_p50', 'r_p90'],
           'cards': {'3m': {'up': {'brier_skill': 0.0203, 'auc': 0.571}, 'ic_mean': 0.09, 'ic_t': 24.9, 'buy': {'flag_ok': True}, 'oos_years': [1996, 2026]}},
           'rows': [{'t': 'AAA', 'n': 'AAA CORP', 's': 'technology', 'side': 'buy', 'best_h': '1m', 'score': 80, 'drivers': [['mom13', 0.1]],
                     'h': {'1m': [0.6012, 0.58, -0.1, 0.01, 0.12], '3m': [0.6466, 0.63, -0.16, 0.05, 0.3]}},
                    {'t': 'BBB', 'n': 'BBB INC', 's': 'energy', 'side': 'none', 'h': {'3m': [0.41, 0.4, -0.3, -0.02, 0.2]}}]}
    F = ['dn10_4', 'up10_4', 'dn20_13', 'up20_13', 'beat13', 'beat52', 'sp500_12m', 'divcut_12m', 'merton_1y', 'vol']
    odds_stocks = {'fields': F, 'rows': {'AAA': [0.18, 0.21, 0.17, 0.23, 0.48, 0.46, 0.5, 0.04, 0.0, 0.3],
                                         'BBB': [0.3, 0.2, 0.35, 0.15, 0.45, 0.44, 0.3, 0.25, 0.01, 0.5]}}
    ma_rows = {'rows': [{'id': 'AAA', 'close': 100.0, 'd200': 0.05123, 'gap40': 0.04, 'x50_200': ['2026-10-28', 1, 4], 'up50_200': 1, 'hd_pct': 0.95,
                         'guid': 1, 'guid_last': ['2026-10-01', 'raised'], 'gap_hybrid': 0.2, 'pct_hybrid': 0.7},
                        {'id': 'BBB', 'close': 20.0, 'd200': -0.2, 'guid': 0, 'guid_last': ['2025-01-02', 'raised'], 'hd_pct': 0.5}]}
    rrg = {'rows': [{'id': 'AAA', 'h13': {'rel': 0.02, 'p': 0.55, 'lo': -0.1, 'hi': 0.12}, 'classic': [101, 99]}]}
    MF = ['key', 'ticker', 'name', 'kind', 'as_of', 'last', 'move', 'pct', 'z', 'every', 'move5', 'move21', 'sim21', 'ext21', 'all21', 'rvpct', 'd0']
    moves = {'as_of': '2026-11-04', 'fields': MF, 'rows': [['AAA', 'AAA', 'Aaa Corp', 'stock', '2026-11-04', 101.5, 0.0512, 97.04, 3.1, 30.2, 0.04, 0.06,
                                                           [300, 0.02, 0.56], [500, 0.03, 0.55], [0.02, 0.57], 40.4, '1999-01-04'],
                                                          ['SPY', 'SPY', 'SPDR', 'etf', '2026-11-04', 500, 0.01, 80, 1, 3, 0, 0, None, None, None, 10, '1993-01-29']]}
    highs = {'now': [{'key': 'AAA', 'group': 'companies', 'state': {'dd': 0.0, 'age': 20, 'highs63': 5},
                      'analogues': {'days': 250, 't10': {'p': {'63': 0.4}}, 'gain_left': {'p50': 0.08}, 'fwd63': {'p50': 0.03, 'up': 0.58}}}]}
    low = lambda reg: {'key': 'BBB', 'group': 'companies', 'state': {'dd_ath': -0.4 if reg != 'atl' else -0.9},
                       'analogues': {'days': 250, 'fwd63': {'p50': 0.05, 'up': 0.6}, 'next_low': {'p': {'63': 0.7}}, 'r10': {'p': {'63': 0.8}}}}
    lows = {'now': {'52w': [low('52w')], 'atl': [low('atl')], '3m': []}}
    ranges = {'now': {'narrow': [{'key': 'CCC', 'group': 'companies', 'state': {'width': 0.05}, 'analogues': {'days': 250, 'breakout': {'p': {'21': 0.9}}}}]}}
    return {'opportunity': opp, 'odds_stocks': odds_stocks, 'ma_rows': ma_rows, 'rrg_companies': rrg, 'moves': moves, 'highs': highs, 'lows': lows, 'ranges': ranges}


class Rows(unittest.TestCase):
    def test_merged_rows_and_flags(self):
        rows = S.rows_now(sources(), {'AAA': ['sp500', 'r1000']}, {'AAA': {'score': 91.2, 'tenth': 10, 'p_beat': 0.45, 'parts': [1.0, 0.7, None]}}, '2026-11-04')
        a, b = rows
        self.assertEqual(a['t'], 'AAA', 'sorted by the combined score, names without one last')
        self.assertEqual(a['n'], 'Aaa Corp', "the move odds' spelling of the name over the SEC's capitals")
        self.assertEqual(a['opp']['up3m'], 0.647)
        self.assertEqual(a['ma']['d200'], 0.051)
        self.assertEqual(a['move']['last'], 101.5)
        self.assertEqual(a['rrg']['quad'], 'weakening')
        for f in ('buy', 'above200', 'golden', 'ath', 'bigup', 'raised', 'far_above'):
            self.assertIn(f, a['f'])
        self.assertNotIn('sp500_cand', a['f'], 'a member is no candidate')
        self.assertEqual(b['lo']['reg'], 'atl', 'the most extreme low wins')
        for f in ('atl', 'below200', 'sp500_cand', 'divcut'):
            self.assertIn(f, b['f'])
        self.assertFalse({'raised', 'guided', 'lowered'} & set(b['f']), 'guidance older than GUIDE_DAYS is no flag')
        self.assertNotIn('score', b)

    def test_missing_sources(self):
        rows = S.rows_now({'opportunity': sources()['opportunity']}, {}, {})
        self.assertEqual([r['t'] for r in rows], ['AAA', 'BBB'])
        self.assertEqual(rows[0]['f'], ['buy'])
        self.assertFalse({'odds', 'ma', 'move', 'hi'} & set(rows[0]))

    def test_pack(self):
        rows = S.rows_now(sources(), {}, {})
        cols, packed = S.pack(rows)
        self.assertEqual(set(cols), set(S.SECTIONS))
        a = packed[0]
        self.assertEqual(dict(zip(cols['opp'], a['opp']))['up3m'], 0.647)
        self.assertNotIn('ma', packed[1]) if not rows[1].get('ma') else self.assertEqual(len(packed[1]['ma']), len(cols['ma']))
        self.assertEqual(len(a['odds']), len(cols['odds']))

    def test_scoreboard_and_verdicts(self):
        src = sources()
        board = S.scoreboard({'opportunity': src['opportunity'], 'odds': {'models': {'up20_13': {'card': {'skill': 0.104, 'auc': 0.72, 'base': 0.22}},
                                                                                     'beat13': {'card': {'skill': -0.001}}}}}, None)
        by = {x['key']: x for x in board}
        self.assertEqual(by['opp:3m']['verdict'], 'useful')
        self.assertEqual(by['odds:up20_13']['verdict'], 'useful')
        self.assertEqual(by['odds:beat13']['verdict'], 'none')
        self.assertEqual(by['hist:moves']['verdict'], 'history')
        self.assertEqual(S.verdict_skill(0.006), 'small')
        self.assertEqual(S.verdict_rank({'mean': 0.05, 't': 2.5}, {'mean': 0.01, 't': 2.1}), 'pays')
        self.assertEqual(S.verdict_rank({'mean': 0.05, 't': 2.5}, {'mean': 0.01, 't': 0.5}), 'ranks')
        self.assertEqual(S.verdict_rank({'mean': 0.05, 't': 1.0}, None), 'weak')
        self.assertEqual(S.verdict_rank({'mean': -0.01, 't': 3}, None), 'none')


class Ledger(unittest.TestCase):
    def test_freeze_then_score(self):
        rng = np.random.default_rng(5)
        days, N = weeks(30), 40
        ids = [f'T{i}' for i in range(N)]
        Sc = np.full((N, 30), nan)
        Sc[:, 10] = np.arange(N) / (N - 1)
        rel = rng.normal(0, 0.02, (N, 30))
        C, V = np.full((N, 30), 50.0), np.full((N, 30), 1e6)
        cut = lambda X, t: X[:, :t + 1]                      # the data as it stood in week t
        bits = lambda t: {'days': days[:t + 1], 't': t, 'ids': ids, 'S': cut(Sc, t), 'C': cut(C, t), 'V': cut(V, t), 'rel': cut(rel, t), 'pcts': {'opp': cut(Sc, t)}}
        rows = [{'t': k, 'ix': [], 'p_beat': 0.5} for k in ids]
        book = FB.load('/nonexistent/ledger.json')
        S.ledger_update(book, bits(10), rows)
        self.assertEqual(len(FB.entries(book, f'scan:{S.H}', resolved=False)), 1)
        S.ledger_update(book, bits(20), rows)                # 13 weeks have not passed: still waiting
        self.assertEqual(len(FB.entries(book, f'scan:{S.H}', resolved=True)), 0)
        Sc[:, 25] = Sc[:, 10]
        S.ledger_update(book, bits(25), rows)
        done = FB.entries(book, f'scan:{S.H}', resolved=True)
        self.assertEqual(len(done), 1)
        self.assertAlmostEqual(done[0][1]['actual']['rel'][3], round(float(rel[3, 11:24].sum()), 5))
        sc = S.ledger_scores(book)
        self.assertEqual(sc['resolved_weeks'], 1)
        self.assertIsNotNone(sc['ic'])


class Build(unittest.TestCase):
    def test_build_without_forecast_histories(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            pub, mv = d / 'public', d / 'moves'
            pub.mkdir()
            mv.mkdir()
            src = sources()
            for name, key in (('opportunity-stocks.json', 'opportunity'), ('odds-stocks.json', 'odds_stocks'), ('ma-hybrid-rows.json', 'ma_rows'),
                              ('rrg-hybrid-companies.json', 'rrg_companies')):
                (pub / name).write_text(json.dumps(src[key]))
            for name, key in (('index.json', 'moves'), ('highs.json', 'highs'), ('lows.json', 'lows'), ('ranges.json', 'ranges')):
                (mv / name).write_text(json.dumps(src[key]))
            (d / 'members.json').write_text(json.dumps({'indexes': {'sp500': {'name': 'S&P 500', 'n': 1}}, 'rows': {'AAA': {'now': ['r1000', 'sp500']}}}))
            doc = S.build(pub, oos=d / 'oos', moves=mv, members=d / 'members.json', ledger=d / 'ledger.json', verbose=False)
            self.assertIsNone(doc['composite'])
            text = (pub / 'opportunity-scan.json').read_text()
            self.assertNotIn('NaN', text)
            out = json.loads(text)
            self.assertEqual(out['counts']['rows'], 2)
            self.assertEqual(out['counts']['sp500'], 1)
            r = next(x for x in out['rows'] if x['t'] == 'AAA')
            self.assertEqual(r['ix'], ['sp500', 'r1000'], 'in the order of INDEX_ORDER')
            self.assertEqual(dict(zip(out['cols']['opp'], r['opp']))['up3m'], 0.647)
            self.assertEqual(out['sources']['moves'], '2026-11-04')
            self.assertNotIn('ledger', out, 'no combined score: nothing frozen')
            self.assertFalse((d / 'ledger.json').exists())
            self.assertIn('opp:3m', [x['key'] for x in out['scoreboard']])


if __name__ == '__main__':
    unittest.main()
