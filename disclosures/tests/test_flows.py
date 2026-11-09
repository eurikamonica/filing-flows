"""app/flows.py: FINRA's daily short sale volume read and added up by week, the daily bars' money flow, a split found
from the two volumes and taken out, big-money net buying against the ticker's own normal, the readings, the quadrants,
the pooled guide and the published files. Offline: FINRA is a stand-in function."""
import datetime as dt
import gzip
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import flows as F  # noqa: E402


def finra_text(day, rows, extra=600):
    """A day's file: the rows given, filler symbols so it reads as a real day, and the trailing record count."""
    lines = ['Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market']
    for sym, sv, tv in rows:
        lines.append(f'{day:%Y%m%d}|{sym}|{sv}|0|{tv}|B,Q,N')
    for k in range(extra):
        lines.append(f'{day:%Y%m%d}|Z{k:04d}|10|0|20|Q')
    lines.append(str(len(lines) - 1))
    return '\n'.join(lines)


def weekdays(a, n):
    d, out = dt.date.fromisoformat(a), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def write_bars(folder, ticker, days, c, h=None, l=None, v=None, ac=None):
    folder.mkdir(parents=True, exist_ok=True)
    n = len(days)
    doc = {'ticker': ticker, 'base': False, 't': [d.isoformat() for d in days], 'o': c, 'h': h or [x * 1.01 for x in c],
           'l': l or [x * 0.99 for x in c], 'c': c, 'ac': ac or c, 'v': v or [1_000_000] * n}
    with gzip.open(folder / f'{ticker}.json.gz', 'wt', encoding='utf-8') as f:
        json.dump(doc, f)


class Parsing(unittest.TestCase):
    def test_parse_day(self):
        text = finra_text(dt.date(2026, 11, 6), [('AAPL', 5591999.06, 13374135.99), ('BF/B', 592373.7, 992154.6),
                                                 ('BRK.B', 10, 30), ('bad sym!', 1, 2), ('ZERO', 0, 0)], extra=0)
        rows = F.parse_day(text)
        self.assertAlmostEqual(rows['AAPL'][0], 5591999.06)
        self.assertIn('BF-B', rows)                     # class shares with a dash, as the daily bars name them
        self.assertIn('BRK-B', rows)
        self.assertNotIn('ZERO', rows)                  # no volume: nothing to read
        self.assertEqual(len(rows), 3)                  # the trailing count and the bad symbol are skipped

    def test_friday(self):
        self.assertEqual(F.friday(dt.date(2026, 11, 2)), dt.date(2026, 11, 6))
        self.assertEqual(F.friday(dt.date(2026, 11, 6)), dt.date(2026, 11, 6))

    def test_snap(self):
        self.assertEqual(F.snap(9.4), 10)
        self.assertEqual(F.snap(0.52), 0.5)              # a 1-for-2 reverse split
        self.assertEqual(F.snap(22.4), 20)               # Amazon's 20-for-1 measured on noisy weeks: the usual ratio wins
        self.assertEqual(F.snap(3.47), 4)                # GameStop's 4-for-1
        self.assertEqual(F.snap(1.52), 1.5)              # a 3-for-2, near a rarer ratio
        self.assertIsNone(F.snap(2.4))                   # near no split ratio: not a split
        self.assertIsNone(F.snap(90))                    # nor a jump of 90×


class Collect(unittest.TestCase):
    def test_days_once_holidays_remembered_newest_first(self):
        with tempfile.TemporaryDirectory() as d:
            today = dt.date(2018, 8, 17)                # FINRA's consolidated files begin on Aug 1, 2018
            asked = []

            def get(url):
                day = dt.datetime.strptime(url[-12:-4], '%Y%m%d').date()
                asked.append(day)
                if day == dt.date(2018, 8, 8):
                    return 403, ''                      # a holiday (as far as this test goes)
                if day == today:
                    return 403, ''                      # not posted yet
                return 200, finra_text(day, [('AAA', 40, 100), ('BBB', 10, 50)])

            st = F.collect(d, minutes=1, today=today, get=get, pause=0, log=lambda *a: None)
            self.assertEqual(asked[0], today)           # newest first
            self.assertEqual(st['last_run']['fetched'], 11)
            self.assertIn('2018-08-08', st['none'])     # old enough to be a holiday
            self.assertNotIn('2018-08-17', st['none'])  # too recent: asked again next run
            W = F.Store(d).year(2018)['weeks']
            self.assertEqual(sorted(W), ['2018-08-03', '2018-08-10', '2018-08-17'])
            self.assertEqual(W['2018-08-10']['days'], ['2018-08-06', '2018-08-07', '2018-08-09', '2018-08-10'])
            self.assertEqual(W['2018-08-10']['s']['AAA'], [160, 400])
            asked.clear()
            F.collect(d, minutes=1, today=today, get=get, pause=0, log=lambda *a: None)
            self.assertEqual(asked, [today])            # every other day is on file or known to have no file
            grid, fin = F.load_finra(d)
            self.assertEqual(grid, ['2018-08-03', '2018-08-10', '2018-08-17'])
            self.assertEqual(fin['BBB'][1], [150, 200, 200])


class Measures(unittest.TestCase):
    def test_weekly_bars_money_flow(self):
        days = weekdays('2026-01-05', 10)              # two weeks
        c = [10.0] * 10
        h = [11.0] * 10
        l = [9.0] * 10
        c[0] = 11.0                                     # at the high: all of the day's dollars in
        c[1] = 9.0                                      # at the low: all out
        c[2] = 10.5                                     # three quarters of the range: half in
        v = [100] * 10
        grid = ['2026-01-09', '2026-01-16']
        dv, mf, vol, ac = F.weekly_bars({'t': [x.isoformat() for x in days], 'h': h, 'l': l, 'c': c, 'ac': c, 'v': v}, grid)
        self.assertAlmostEqual(dv[0], 100 * (11 + 9 + 10.5 + 10 + 10))
        self.assertAlmostEqual(mf[0], 1100 - 900 + 0.5 * 1050)
        self.assertEqual(vol[1], 500)
        self.assertEqual(ac[1], 10.0)

    def test_split_found_and_taken_out(self):
        q = [0.4 + 0.02 * math.sin(i) for i in range(60)]
        q = [x / 10 if i < 30 else x for i, x in enumerate(q)]   # a 10-for-1 split in week 30
        self.assertEqual(F.split_steps(q), ({30: 10}, 0))
        self.assertEqual(F.split_steps([0.4 + 0.05 * math.sin(i) for i in range(60)]), ({}, 0))   # noise is not a split
        noisy = [0.1 * (1.8 if i % 3 == 0 else 0.6) * (2 if i >= 30 else 1) for i in range(60)]
        self.assertEqual(F.split_steps(noisy)[0], {})   # a doubling inside weeks that swing as much: not taken for a split
        # a symbol FINRA used for another, smaller security first (Meta's ticker before June 2022): its history is cut
        meta = [0.004 + 0.001 * math.sin(i) for i in range(30)] + [0.45 + 0.02 * math.sin(i) for i in range(30)]
        self.assertEqual(F.split_steps(meta), ({}, 30))
        meta = meta[:24] + [None] * 6 + meta[30:]          # … with weeks of no FINRA figure between the two
        self.assertEqual(F.split_steps(meta), ({}, 30))
        moved = [0.40] * 24 + [None] * 6 + [0.80] * 30     # a step of 2× across a gap is no split either
        self.assertEqual(F.split_steps(moved), ({}, 30))

    def test_big_money_net_buying_against_its_own_normal(self):
        n = 70
        grid = [(dt.date(2025, 1, 3) + dt.timedelta(days=7 * i)).isoformat() for i in range(n)]
        days = weekdays('2024-12-30', 5 * n)
        price = [20.0] * len(days)
        vol = [1_000_000] * len(days)                   # split-adjusted shares a day
        # FINRA (shares as traded): a 2-for-1 split in week 40; half the volume off-exchange; short share 40%, then 46%
        split = 40
        tv = [(5 * 1_000_000 * 0.5) / (2 if i < split else 1) for i in range(n)]
        share = [0.40 if i < 60 else 0.46 for i in range(n)]
        sv = [tv[i] * share[i] for i in range(n)]
        bars = {'t': [x.isoformat() for x in days], 'h': [21.0] * len(days), 'l': [19.0] * len(days), 'c': price, 'ac': price, 'v': vol}
        R = F.ticker_flows(grid, (sv, tv), bars)
        self.assertEqual(R['splits'], {split: 2})
        self.assertIsNone(R['dp'][20])                  # fewer than 26 weeks of its own normal yet
        self.assertAlmostEqual(R['b'][59], 0.40, places=9)
        self.assertAlmostEqual(R['dp'][59], 0.0, places=3)
        self.assertIsNone(R['dp'][split])               # the split's week and the one before are left out
        self.assertIsNone(R['dp'][split - 1])
        self.assertAlmostEqual(R['dp'][30], 0.0, places=3)   # before the split: FINRA's shares put in today's units
        # week 60: 6 points above its normal, on $50M off-exchange (2.5M split-adjusted shares at $20)
        self.assertAlmostEqual(R['dp'][60], 2 * 0.06 * 2_500_000 * 20, delta=1)
        W = F.window(R, 63)
        b = [R['b'][i] for i in range(60, 64)]
        self.assertAlmostEqual(W['x'], 100 * sum(2 * (0.46 - x) for x in b) / 4, places=6)   # of the off-exchange volume
        self.assertGreater(W['x'], 11)                  # about 12 points: 2 × 6
        self.assertAlmostEqual(W['y'], 0.0, places=9)   # every close mid-range: no money flow
        self.assertAlmostEqual(W['dp'], sum(R['dp'][60:64]), places=3)
        self.assertEqual(F.quad(W['x'], W['y']), 0)
        self.assertAlmostEqual(F.window(R, 45)['x'], 0.0, places=9)   # the split does not move the reading

    def test_quadrants_in_the_rrg_order(self):
        self.assertEqual([F.quad(1, 1), F.quad(1, -1), F.quad(-1, -1), F.quad(-1, 1)], [0, 1, 2, 3])
        self.assertEqual(F.QUADS[F.quad(2, -3)], 'Quiet buying')


class Guide(unittest.TestCase):
    def test_pooled_what_followed(self):
        n = 60
        grid = [(dt.date(2025, 1, 3) + dt.timedelta(days=7 * i)).isoformat() for i in range(n)]
        bench = [100.0 * 1.001 ** i for i in range(n)]
        one = lambda dv, mf, r, ac: {'dv': [dv] * n, 'mf': [mf] * n, 'ox': [dv / 50] * n, 'r': [r] * n, 'b': [0.4] * n, 'dp': [0.0] * n, 'ac': ac}
        flows = {'SPY': one(1e9, 0.0, 0.4, bench)}
        # ten tickers buying (both measures up) that beat SPY, ten selling that lag
        for k in range(10):
            flows[f'UP{k}'] = one(1e7, 1e6, 0.43, [100.0 * 1.003 ** i for i in range(n)])
            flows[f'DN{k}'] = one(1e7, -1e6, 0.37, [100.0 * 0.999 ** i for i in range(n)])
        S = F.pooled_stats(flows, grid, bench, etfs={'SPY'})
        P = S['pools']['stocks']
        self.assertEqual(P['tickers'], 20)
        self.assertEqual(P['q'][0]['4']['beat'], 1.0)
        self.assertEqual(P['q'][2]['4']['beat'], 0.0)
        self.assertEqual(P['q'][1]['4']['n'], 0)
        self.assertGreater(P['q'][0]['13']['med'], 0)
        self.assertEqual(P['fifths']['4']['x']['top']['beat'], 1.0)
        self.assertEqual(P['fifths']['4']['x']['bottom']['beat'], 0.0)
        self.assertEqual(S['pools']['etfs']['tickers'], 0)   # SPY itself is the benchmark


class Build(unittest.TestCase):
    def test_files(self):
        with tempfile.TemporaryDirectory() as d:
            root, bars = Path(d) / 'flw', Path(d) / 'ohlc'
            days = weekdays('2025-01-06', 5 * 40)
            store = F.Store(root)
            for i, day in enumerate(days):
                wk = i // 5
                store.add(day, {'SPY': (160_000, 400_000), 'XLK': (160_000 + (20_000 if wk > 34 else 0), 400_000), 'NVDA': (120_000, 400_000)})
            store.save()
            write_bars(bars, 'SPY', days, [500.0] * len(days))
            write_bars(bars, 'XLK', days, [200.0 + 0.1 * i for i in range(len(days))])
            write_bars(bars, 'NVDA', days, [100.0] * len(days))
            write_bars(bars, 'IDX-VIX', days, [15.0] * len(days))
            idx = F.build(root, bars, log=lambda *a: None)
            self.assertEqual(idx['tickers'], ['NVDA', 'SPY', 'XLK'])   # an index has no volume to read
            self.assertIn('XLK', idx['etfs'])
            X = json.loads((root / 'public' / 't' / 'XLK.json').read_text())
            self.assertEqual(X['start'], '2025-01-10')
            self.assertEqual(len(X['dv']), 40)
            self.assertIsNone(X['dp'][10])
            self.assertGreater(X['dp'][36], 0)            # five points above its normal short share
            self.assertEqual(X['r'][36], 4500)
            self.assertEqual(X['b'][36], 4014)           # its own normal already holds week 35's higher share
            self.assertEqual(X['ox'][36], 2000)           # 400,000 shares a day, in thousands
            self.assertTrue((root / 'public' / 'index.json').exists() and (root / 'public' / 'status.json').exists())


if __name__ == '__main__':
    unittest.main()
