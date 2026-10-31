"""app/moves.py (move odds): the compact series and its inverse, mid-rank percentiles, moves and returns ahead, moves
against their own volatility, the similar and more extreme days, the latest day's summary, equal-weighted industry
composites, the build from the bars on file, and the collector's long index history (app/paths.py)."""
import datetime as dt
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import moves as M  # noqa: E402
import paths as P  # noqa: E402


def weekdays(start, n):
    d, out = dt.date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def bars(days, closes):
    return {'t': list(days), 'o': list(closes), 'h': list(closes), 'l': list(closes), 'c': list(closes), 'ac': list(closes), 'v': [100] * len(days)}


class Series(unittest.TestCase):
    def test_encode_decode(self):
        days = weekdays('2026-01-01', 30)
        closes = [100 * math.exp(0.01 * math.sin(i)) for i in range(30)]
        doc = M.encode(days, closes)
        self.assertEqual(len(doc['r']), 29)
        self.assertEqual(len(doc['gaps']), 29)
        self.assertTrue(all(isinstance(x, int) for x in doc['r']))
        back, r = M.decode(json.loads(json.dumps(doc)))
        self.assertEqual(back, days)
        self.assertTrue(np.allclose(r, np.diff(np.log(closes)), atol=0.5e-4))     # whole basis points
        # a gap over 35 days (a long halt) keeps the dates themselves
        doc = M.encode(['2026-01-02', '2026-03-02', '2026-03-03'], [10, 11, 12])
        self.assertNotIn('gaps', doc)
        self.assertEqual(M.decode(doc)[0], ['2026-01-02', '2026-03-02', '2026-03-03'])

    def test_series_drops_bad_closes(self):
        d, c = M.series({'t': ['a', 'b', 'c', 'd'], 'ac': [1.0, None, -2.0, 3.0]})
        self.assertEqual((d, c), (['a', 'd'], [1.0, 3.0]))


class Arithmetic(unittest.TestCase):
    def test_percentiles_are_mid_ranks(self):
        p = M.pct_ranks([1.0, 2.0, 2.0, 3.0, float('nan')])
        self.assertEqual(p[:4].tolist(), [12.5, 50.0, 50.0, 87.5])
        self.assertTrue(math.isnan(p[4]))

    def test_moves_and_returns_ahead(self):
        c = M.cum([0.1, 0.2, -0.05, 0.0])                     # 5 points
        self.assertTrue(np.allclose(M.moves(c, 2)[2:], [0.3, 0.15, -0.05]))
        self.assertTrue(np.isnan(M.moves(c, 2)[:2]).all())
        self.assertTrue(np.allclose(M.ahead(c, 1)[:4], [0.1, 0.2, -0.05, 0.0]))
        self.assertTrue(np.isnan(M.ahead(c, 1)[4]))

    def test_move_against_its_own_volatility(self):
        rng = np.random.default_rng(3)
        r = np.concatenate([rng.normal(0, 0.01, 63), [-0.05]])
        z = M.vol_scaled(r, 1)
        sd = np.std(r[:63], ddof=1)
        self.assertAlmostEqual(z[-1], -0.05 / sd, places=6)
        self.assertTrue(np.isnan(z[:64]).all())                # 63 returns before the move are needed

    def test_similar_and_more_extreme_days(self):
        p = np.array([1.0, 3.0, 5.0, 50.0, 96.0, np.nan])
        self.assertEqual(M.chosen(p, 3.0, 2.5).tolist(), [True, True, True, False, False, False])
        self.assertEqual(M.chosen(p, 3.0, how='extreme').tolist(), [True, True, False, False, False, False])
        self.assertEqual(M.chosen(p, 95.0, how='extreme').tolist(), [False, False, False, False, True, False])

    def test_summary_of_the_latest_day(self):
        rng = np.random.default_rng(7)
        r = np.round(np.concatenate([rng.normal(0.0005, 0.01, 600), [-0.08]]) * 1e4) / 1e4
        days = weekdays('2024-01-01', len(r) + 1)
        s = M.summary(days, r)
        self.assertEqual(s['as_of'], days[-1])
        self.assertAlmostEqual(s['move'], math.expm1(-0.08))
        self.assertAlmostEqual(s['pct'], 100 * 0.5 / len(r))  # the lowest day of all
        self.assertEqual(s['every'], len(r))                  # 1 in every day on file: the only one
        self.assertIsNone(s['last_as'])
        self.assertLess(s['z'], -5)
        n, med, up = s['sim1']
        self.assertGreater(n, 0)
        self.assertLessEqual(n, len(r))
        self.assertTrue(0 <= up <= 1)
        self.assertIsNone(s['ext1'])                          # nothing as low has a known next day
        self.assertEqual(len(s['all21']), 2)


class Recovery(unittest.TestCase):
    def test_climbing_back_and_new_highs(self):
        c = np.log([100, 90, 95, 101, 80, 120, 110])
        self.assertEqual(M.first_after(c, 1, c[0]), 3)
        self.assertIsNone(M.first_after(c, 5, np.log(130)))
        self.assertEqual(M.first_after(c, 3, np.log(85), up=False), 4)
        bt, be, ht, he = M.recovery(c, [1, 4, 6], 1, -1)
        self.assertEqual((bt, be), ([2, 1], [True, True]))      # day 6 has nothing after it: left out
        self.assertEqual((ht, he), ([2, 1], [True, True]))
        bt, be, ht, he = M.recovery(c, [3], 1, 1)                 # a rise (95 → 101): given back on day 4
        self.assertEqual((bt, be), ([1], [True]))
        self.assertEqual((ht, he), ([2], [True]))                # 120 on day 5 is above the high of 101
        bt, be, _, _ = M.recovery(c, [1], 1, -1, end=2)          # judged on what was known by day 2: still waiting
        self.assertEqual((bt, be), ([1], [False]))

    def test_kaplan_meier_with_waiting_days(self):
        self.assertEqual(M.km([2, 3, 5, 5], [True, False, True, True], at=3), [4, 5, 0.25])
        self.assertEqual(M.km([2, 3, 5, 5], [True, False, True, True], at=21)[2], 1.0)
        n, med, within = M.km([10, 10, 10], [False, False, True], at=21)   # one of three back, the two others still waiting
        self.assertEqual((n, med), (3, None))
        self.assertAlmostEqual(within, 1 / 3)
        self.assertIsNone(M.km([], []))

    def test_the_summary_says_how_long(self):
        rng = np.random.default_rng(5)
        r = np.round(np.concatenate([rng.normal(0.0004, 0.01, 800), [-0.05]]) * 1e4) / 1e4
        s = M.summary(weekdays('2023-01-02', len(r) + 1), r)
        n, med, within = s['back']
        self.assertGreater(n, 5)
        self.assertTrue(med is None or med >= 1)
        self.assertTrue(0 <= within <= 1)
        self.assertEqual(len(s['high']), 3)
        self.assertEqual(len(s['sim10']), 3)
        self.assertIn('sim10', M.FIELDS)
        self.assertIn('back', M.FIELDS)


class HistoryAndVolatility(unittest.TestCase):
    def test_older_bars_join_at_the_first_day_on_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = weekdays('2000-01-03', 30)
            old_closes = [10 * (1.01 ** i) for i in range(30)]
            P._write_gz(P.long_path(tmp, 'ABC'), {'ticker': 'ABC', 'end': old[-1], **P.encode_returns(old, old_closes)})
            days = [old[-1]] + weekdays('2000-02-15', 5)
            closes = [50.0, 51, 52, 53, 54, 55]                  # a later basis (a split since): returns are what count
            d, c = M.stitch(tmp, 'ABC', days, closes)
            self.assertEqual(d, old[:-1] + days)
            self.assertAlmostEqual(c[len(old) - 1], 50.0)
            self.assertAlmostEqual(c[0], 50.0 * math.exp(-29 * round(math.log(1.01) * 1e4) / 1e4), places=6)   # whole basis points
            r = np.diff(np.log(c))
            self.assertTrue(np.allclose(r[:29], np.log(1.01), atol=1e-4))
            self.assertEqual(M.stitch(tmp, 'ABC', days[1:], closes[1:]), (days[1:], closes[1:]))   # no shared day: as is
            self.assertEqual(M.stitch(tmp, 'XYZ', days, closes), (days, closes))

    def test_realized_volatility(self):
        rng = np.random.default_rng(9)
        r = rng.normal(0, 0.01, 100)
        v = M.realized(r, 21)
        self.assertTrue(np.isnan(v[:21]).all())
        self.assertAlmostEqual(v[50], np.std(r[29:50], ddof=1) * math.sqrt(252))

    def test_a_volatility_index_judged_by_the_sp500(self):
        days = weekdays('2020-01-01', 400)
        rng = np.random.default_rng(4)
        vix = np.concatenate([[0.0], rng.normal(0, 0.05, 399)])
        spx = np.concatenate([[0.0], rng.normal(0.0004, 0.01, 399)])
        s = M.level_summary(days, vix[1:], 20.0, (days, np.cumsum(spx)))
        self.assertEqual(s['level'], 20.0)
        self.assertAlmostEqual(s['lpct'], M.pct_ranks(np.cumsum(vix))[-1])
        n, med, up = s['out21']
        self.assertGreater(n, 0)
        self.assertTrue(0 <= up <= 1)

    def test_volatility_indices_and_the_term_structure_in_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'pth'
            days = weekdays('2022-01-03', 400)
            rng = np.random.default_rng(12)
            for t, lvl in (('SPY', 400.0), ('IDX-VIX', 20.0), ('IDX-VIX3M', 22.0)):
                closes = list(lvl * np.exp(np.cumsum(rng.normal(0, 0.03 if 'VIX' in t else 0.01, len(days)))))
                P.save(root, t, {'ticker': t, 'source': 'yahoo', 'fetched_at': '2026-01-01T00:00:00+00:00', **bars(days, closes)})
            M.build(root, None)
            out = root / 'public' / 'moves'
            ix = json.loads((out / 'index.json').read_text())
            got = {r[0]: dict(zip(ix['fields'], r)) for r in ix['rows']}
            self.assertEqual(got['IDX-VIX']['kind'], 'volatility')
            self.assertIsNotNone(got['IDX-VIX']['lpct'])
            self.assertIsNotNone(got['IDX-VIX']['out21'])
            self.assertIn('VIX-TERM', got)
            self.assertIsNotNone(got['SPY']['rv21'])
            doc = json.loads((out / 'a' / 'IDX-VIX.json').read_text())
            self.assertEqual(doc['links'], {'outcome': 'SPY'})
            self.assertEqual(doc['names']['SPY'], 'S&P 500 (SPY)')

    def test_the_backfill_fetches_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            days = weekdays('2016-10-17', 30)
            P.save(tmp, 'OLD', {'ticker': 'OLD', 'source': 'yahoo', 'fetched_at': '2026-01-01T00:00:00+00:00', **bars(days, [10.0 + i for i in range(30)])})
            P.save(tmp, 'NEW', {'ticker': 'NEW', 'source': 'yahoo', 'fetched_at': '2026-01-01T00:00:00+00:00', **bars(days, [10.0 + i for i in range(30)])})
            asked = []

            class Client:
                def json(self, url):
                    asked.append(url)
                    if '/NEW?' in url:                             # listed on the first day on file: nothing older
                        ds = days[:1]
                    else:
                        ds = weekdays('2010-01-04', 1850)
                        ds = [d for d in ds if d <= days[5]]
                    ts = [int(dt.datetime.fromisoformat(d + 'T14:30:00+00:00').timestamp()) for d in ds]
                    cl = [5.0 + 0.001 * i for i in range(len(ds))]
                    q = {'open': cl, 'high': cl, 'low': cl, 'close': cl, 'volume': [1] * len(ds)}
                    return {'chart': {'result': [{'timestamp': ts, 'meta': {'gmtoffset': 0}, 'indicators': {'quote': [q], 'adjclose': [{'adjclose': cl}]}}]}}
            done = P.backfill(Client(), tmp, ['OLD', 'NEW', 'MISSING'])
            self.assertEqual((done['fetched'], done['nothing_older'], done['waiting'], done['left']), (1, 1, 1, 1))   # MISSING: not collected yet
            self.assertIn('period1=' + str(int(dt.datetime(1927, 12, 30, tzinfo=dt.timezone.utc).timestamp())), asked[0])
            doc = P.read_long(tmp, 'OLD')
            self.assertEqual(doc['end'], days[0])
            d, r = P.decode_returns(doc)
            self.assertEqual(d[-1], days[0])
            self.assertEqual(d[0], '2010-01-04')
            n = len(asked)
            P.backfill(Client(), tmp, ['OLD', 'NEW'])
            self.assertEqual(len(asked), n)                    # never fetched again

    def test_an_index_from_a_later_date_and_bars_fetched_anew(self):
        with tempfile.TemporaryDirectory() as tmp:
            asked = []

            class Client:                                      # Yahoo: the weekdays from 1960 within period1 … period2
                def json(self, url):
                    asked.append(url)
                    p2 = int(url.split('period2=')[1].split('&')[0])
                    ds = [d for d in weekdays('1960-01-04', 4200) if dt.datetime.fromisoformat(d + 'T14:30:00+00:00').timestamp() <= p2]
                    ts = [int(dt.datetime.fromisoformat(d + 'T14:30:00+00:00').timestamp()) for d in ds]
                    cl = [50.0 * math.exp(0.0002 * i) for i in range(len(ds))]
                    q = {'open': cl, 'high': cl, 'low': cl, 'close': cl, 'volume': [0] * len(ds)}
                    return {'chart': {'result': [{'timestamp': ts, 'meta': {'gmtoffset': 0}, 'indicators': {'quote': [q], 'adjclose': [{'adjclose': cl}]}}]}}

            def on_file(start):                                # the collector's bars and its state.json
                days = weekdays(start, 30)
                P.save(tmp, 'IDX-GSPC', {'ticker': 'IDX-GSPC', 'source': 'yahoo', 'fetched_at': '2026-01-01T00:00:00+00:00', **bars(days, [90.0 + i for i in range(30)])})
                P.write_json(Path(tmp) / 'state.json', {'format': P.FORMAT, 'tickers': {'IDX-GSPC': {'fetched_at': '2026-01-01T00:00:00+00:00', 'first': days[0]}}})
                return days
            days = on_file('1970-01-02')                       # collected from 1970 before the S&P 500 went back to 1928
            self.assertEqual(P.backfill(Client(), tmp, ['IDX-GSPC'])['fetched'], 1)
            self.assertIn('/chart/%5EGSPC?', asked[-1])
            doc = P.read_long(tmp, 'IDX-GSPC')
            self.assertEqual((doc['d0'], doc['end']), ('1960-01-04', '1970-01-02'))
            d, _ = M.stitch(tmp, 'IDX-GSPC', days, [90.0 + i for i in range(30)])
            self.assertEqual((d[0], d[-1], len(d)), ('1960-01-04', days[-1], len(P.decode_returns(doc)[0]) + 29))
            n = len(asked)
            self.assertEqual(P.backfill(Client(), tmp, ['IDX-GSPC'])['left'], 0)
            self.assertEqual(len(asked), n)                    # done
            days = on_file('1975-01-02')                       # fetched anew from another first day: joined there again
            self.assertEqual(P.backfill(Client(), tmp, ['IDX-GSPC'])['fetched'], 1)
            self.assertEqual(P.read_long(tmp, 'IDX-GSPC')['end'], '1975-01-02')
            self.assertEqual(M.stitch(tmp, 'IDX-GSPC', days, [90.0 + i for i in range(30)])[0][0], '1960-01-04')

    def test_volatility_index_symbols(self):
        seen = []

        class Client:
            def json(self, url):
                seen.append(url)
                ds = weekdays('2026-01-05', 30)
                ts = [int(dt.datetime.fromisoformat(d + 'T14:30:00+00:00').timestamp()) for d in ds]
                q = {'open': [1.0] * 30, 'high': [1.0] * 30, 'low': [1.0] * 30, 'close': [20.0 + i for i in range(30)], 'volume': [0] * 30}
                return {'chart': {'result': [{'timestamp': ts, 'meta': {'gmtoffset': 0}, 'indicators': {'quote': [q]}}]}}
        P.fetch(Client(), 'IDX-VIX')
        self.assertIn('/chart/%5EVIX?', seen[-1])
        self.assertIn('period1=' + str(int(dt.datetime(1990, 1, 2, tzinfo=dt.timezone.utc).timestamp())) + '&', seen[-1])
        P.fetch(Client(), 'IDX-GSPC')
        self.assertIn('period1=-', seen[-1])                   # the S&P 500 since 1927


class Composite(unittest.TestCase):
    def test_equal_weighted_with_enough_members(self):
        days = weekdays('2026-01-05', 4)
        members = [(days, [100, 110, 110, 121]), (days, [50, 50, 55, 55]), (days, [10, 10, 10, 10])]
        d, c = M.composite(members, min_members=3)
        self.assertEqual(d, days)
        self.assertTrue(np.allclose(c, [100, 100 * (1 + 0.1 / 3), 100 * (1 + 0.1 / 3) * (1 + 0.1 / 3), 100 * (1 + 0.1 / 3) ** 3]))

    def test_a_day_with_few_members_in_yet_is_left_out(self):
        days = weekdays('2026-01-05', 6)
        full = [(days, [100 + i for i in range(6)]) for _ in range(5)]
        late = [(days[:-1], [100 + i for i in range(5)]) for _ in range(5)]      # their last close not in yet
        d, _ = M.composite(full + late[:2], min_members=5)
        self.assertEqual(d[-1], days[-1])                     # 5 of the usual 7 in: kept
        d, _ = M.composite(full + late, min_members=5)
        self.assertEqual(d[-1], days[-2])                     # 5 of the usual 10: under 60%, left out
        d, _ = M.composite(full[:2] + late + late, min_members=5)
        self.assertEqual(d[-1], days[-2])                     # 2 in: under the minimum

    def test_a_bad_print_is_clipped(self):
        days = weekdays('2026-01-05', 3)
        members = [(days, [100, 100, 100])] * 4 + [(days, [100, 1, 1])]
        _, c = M.composite(members, min_members=5)
        self.assertAlmostEqual(c[1], 100 * (1 - 0.5 / 5))      # −99% counted as −50%


class Build(unittest.TestCase):
    def test_build_from_the_bars_on_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, val = Path(tmp) / 'pth', Path(tmp) / 'val'
            days = weekdays('2024-01-02', 400)
            rng = np.random.default_rng(11)

            def put(t, drift=0.0, scale=0.01):
                closes = list(100 * np.exp(np.cumsum(rng.normal(drift, scale, len(days)))))
                P.save(root, t, {'ticker': t, 'source': 'yahoo', 'fetched_at': '2026-01-01T00:00:00+00:00', **bars(days, closes)})
            for t in ('SPY', 'XLK', 'IDX-GSPC'):
                put(t)
            rows = []
            for i in range(6):
                t = f'CO{i}'
                put(t, scale=0.02)
                rows.append([1000 + i, t, f'COMPANY {i} INC', 'technology', 'industrial', 1e9 * (10 - i)])
                (val / 'c').mkdir(parents=True, exist_ok=True)
                (val / 'c' / f'{1000 + i}.json').write_text(json.dumps({'cik': 1000 + i, 'industry': 'Semiconductors & Related Devices', 'sic': '3674'}, indent=2))
            (val / 'index.json').write_text(json.dumps({'fields': ['cik', 'ticker', 'name', 'sector', 'kind', 'mcap'], 'rows': rows}))
            st = M.build(root, val / 'index.json')
            self.assertEqual(st['errors'], [])
            out = root / 'public' / 'moves'
            ix = json.loads((out / 'index.json').read_text())
            got = {r[0]: dict(zip(ix['fields'], r)) for r in ix['rows']}
            self.assertIn('SIC-3674', got)
            self.assertEqual(got['SIC-3674']['members'], 6)
            self.assertEqual(got['SIC-3674']['kind'], 'industry')
            self.assertEqual(got['IDX-GSPC']['kind'], 'index')
            self.assertEqual(got['CO0']['industry'], 'SIC-3674')
            doc = json.loads((out / 'a' / 'CO0.json').read_text())
            self.assertEqual(doc['links'], {'industry': 'SIC-3674', 'sector': 'XLK', 'market': 'SPY'})
            self.assertEqual(doc['names']['SIC-3674'], 'Semiconductors & Related Devices (SIC 3674)')
            self.assertEqual(M.decode(doc)[0], days)
            self.assertEqual(ix['as_of'], days[-1])
            self.assertEqual(ix['breadth']['stocks'], 6)
            self.assertEqual(json.loads((out / 'status.json').read_text())['counts']['stock'], 6)
            # an asset gone from the files is gone from the output
            (root / 'cache' / 'ohlc' / 'CO5.json.gz').unlink()
            M.build(root, val / 'index.json')
            self.assertFalse((out / 'a' / 'CO5.json').exists())


class LongHistory(unittest.TestCase):
    def test_index_symbols_and_start_dates(self):
        seen = []

        class Client:
            def json(self, url):
                seen.append(url)
                days = weekdays('2026-01-05', 30)
                ts = [int(dt.datetime.fromisoformat(d + 'T14:30:00+00:00').timestamp()) for d in days]
                q = {'open': [1.0] * 30, 'high': [1.0] * 30, 'low': [1.0] * 30, 'close': [1.0 + i for i in range(30)], 'volume': [0] * 30}
                return {'chart': {'result': [{'timestamp': ts, 'meta': {'gmtoffset': 0}, 'indicators': {'quote': [q]}}]}}
        P.fetch(Client(), 'IDX-GSPC')
        self.assertIn('%5EGSPC', seen[-1])
        self.assertIn('period1=' + str(int(dt.datetime(1927, 12, 30, tzinfo=dt.timezone.utc).timestamp())) + '&', seen[-1])
        P.fetch(Client(), 'SPY')
        self.assertIn('/chart/SPY?', seen[-1])
        p1 = int(seen[-1].split('period1=')[1].split('&')[0])
        self.assertGreater(p1, dt.datetime(2015, 1, 1, tzinfo=dt.timezone.utc).timestamp())
        self.assertIn('IDX-GSPC', P.LONG_HISTORY)
        self.assertNotIn('SMH', P.ETFS)                       # the path models keep their own ETFs
        self.assertIn('SMH', P.MOVES_ETFS)


if __name__ == '__main__':
    unittest.main()
