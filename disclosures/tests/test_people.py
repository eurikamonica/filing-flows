"""people.py: the clone backtest, the insider event study, committee overlaps, the 13F preview ledger, the S&P 500
screen and the price-target hit rate, on small synthetic data."""
import datetime as dt
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import numpy  # noqa: F401  (people.py needs it; the collector's check step installs only requirements.txt)
except ImportError:
    raise unittest.SkipTest("numpy is not installed")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
try:                                   # app/people.py needs numpy; the Hub's quick checks run without it (research-people.yml has it)
    import numpy  # noqa: F401,E402
except ImportError:
    raise unittest.SkipTest('numpy is not installed')
import people as P  # noqa: E402


def write_prices(d, ticker, f, start='2024-01-01', n=700):
    rows, day, i = [], dt.date.fromisoformat(start), 0
    while len(rows) < n:
        if day.weekday() < 5:
            rows.append([day.isoformat(), round(f(i), 4), 1_000_000])
            i += 1
        day += dt.timedelta(days=1)
    (d / 'cache' / 'prices').mkdir(parents=True, exist_ok=True)
    with gzip.open(d / 'cache' / 'prices' / f'{ticker}.json.gz', 'wt') as fh:
        json.dump({'ticker': ticker, 'rows': rows}, fh)
    return rows


class FakeU:
    cusip_ticker = {'C1': 'AAA', 'C2': 'BBB'}

    def name(self, t):
        return t + ' Inc'


class Clone(unittest.TestCase):
    def test_clone_follows_prices_after_the_filing(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            write_prices(d, 'SPY', lambda i: 100 * (1 + 0.0004) ** i)
            write_prices(d, 'AAA', lambda i: 50 * (1 + 0.001) ** i)
            write_prices(d, 'BBB', lambda i: 20.0)
            px = P.Px([d / 'cache' / 'prices'])
            snaps = [['2024-12-31', '2025-02-14', 1000, [['C1', 10, 600], ['C2', 20, 400]], {}], ['2025-03-31', '2025-05-15', 1100, [['C1', 10, 700], ['C2', 20, 400]], {}]]
            bt = P.clone_backtest(snaps, FakeU(), px, today=dt.date(2025, 9, 30).toordinal())
            self.assertEqual(bt['filings'], 2)
            self.assertGreater(bt['total'], bt['spy_total'])        # AAA rises faster than SPY, BBB is flat
            self.assertEqual(bt['start'][:7], '2025-02')
            self.assertEqual(bt['coverage'], 1.0)
            self.assertIsNone(P.clone_backtest([['2024-12-31', '2025-02-14', 1000, None, None]], FakeU(), px))


class Insiders(unittest.TestCase):
    def test_event_study_rows_and_lookup(self):
        trades = []
        base = dt.date(2025, 1, 6).toordinal()
        for k in range(80):
            trades.append([base + k * 4, 'AAA', 1, 500_000, 'CEO', 0.05, 0.04 + (0.02 if k % 2 else -0.01), f'i:{k % 20}'])
        table = P.insider_study(trades)
        row = table['buy|CEO|$100K–$1M']
        self.assertEqual(row['n'], 80)
        self.assertLess(row['lo'], row['mean'])
        self.assertLess(row['mean'], row['hi'])
        key, got = P.lookup(table, 'buy', 'CEO', 500_000, True)
        self.assertEqual(key, 'buy|CEO|$100K–$1M|cluster')          # 20 insiders traded the same way within 30 days
        self.assertEqual(P.lookup(table, 'buy', 'CEO', 500_000, False)[0], 'buy|CEO|$100K–$1M')
        key, got = P.lookup(table, 'buy', 'CFO', 500_000, False)
        self.assertEqual(key, 'buy')                                 # no CFO rows: the broadest one
        self.assertEqual(P.lookup(table, 'sale', 'CFO', 1, False), (None, None))

    def test_clusters(self):
        base = dt.date(2025, 1, 6).toordinal()
        trades = [[base, 'AAA', 1, 1, 'CEO', 0, 0, 'i:a'], [base + 10, 'AAA', 1, 1, 'CFO', 0, 0, 'i:b'], [base + 50, 'AAA', 1, 1, 'CEO', 0, 0, 'i:c']]
        self.assertEqual(P.clusters(trades), [True, True, False])


class Officials(unittest.TestCase):
    def test_jurisdiction_and_name_matching(self):
        cfg = P.cfg_load()
        self.assertEqual(P.jurisdiction(cfg, 'HSAS', 'industrials', '3760'), 'defense')
        self.assertEqual(P.jurisdiction(cfg, 'HSAS02', 'industrials', '3760'), 'defense')       # a subcommittee inherits
        self.assertIsNone(P.jurisdiction(cfg, 'HSAS', 'technology', '7372'))
        self.assertEqual(P.jurisdiction(cfg, 'SSBK', 'financials', '6021'), 'financials')
        self.assertIsNone(P.jurisdiction(cfg, 'XXXX', 'financials', '6021'))
        self.assertEqual(P.person_key('David J. Taylor'), 'david taylor')
        self.assertEqual(P.person_key('A. Mitchell McConnell Jr.'), 'mitchell mcconnell')
        L = {'people': {'B1': {'bioguide': 'B1', 'name': 'Dan Crenshaw', 'keys': {'dan crenshaw'}, 'last': 'crenshaw', 'initials': {'d'}, 'chamber': 'US House'},
                        'B2': {'bioguide': 'B2', 'name': 'Kevin Mullin', 'keys': {'kevin mullin'}, 'last': 'mullin', 'initials': {'k'}, 'chamber': 'US House'}}}
        self.assertEqual(P.match_legislator(L, 'Daniel Crenshaw', 'US House')['bioguide'], 'B1')
        self.assertIsNone(P.match_legislator(L, 'Markwayne Mullin', 'US Senate'))


class Index(unittest.TestCase):
    def test_sp500_screen_and_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, root = Path(tmp) / 'hub', Path(tmp) / 'root'
            (d / 'cache' / 'prices').mkdir(parents=True)
            P.wj(d / 'cache' / 'prices' / 'sec-tickers.json', {'rows': [{'ticker': 'AAA', 'cik': 1, 'title': 'AAA INC'}, {'ticker': 'BBB', 'cik': 2, 'title': 'BBB CORP'},
                                                                         {'ticker': 'SPY', 'cik': 3, 'title': 'SPDR S&P 500 ETF TRUST'}, {'ticker': 'MEM', 'cik': 4, 'title': 'MEMBER CO'}]})
            today = dt.date(2026, 10, 19)
            for t in ('AAA', 'BBB', 'MEM'):
                write_prices(d, t, lambda i: 100.0, start='2025-06-01', n=360)          # 1M shares a day: $25B a year traded
            cfg = P.cfg_load()
            cfg['sp500_min_mcap'] = 1e10
            qs = P.calendar_quarters(today, 6)
            self.assertEqual(qs[0], 'CY2026Q2')
            for q in qs:
                P.wj(root / 'cache' / 'frames' / f'NetIncomeLoss-{q}.json', {'1': [5e8, None, None], '2': [-1e8, None, None], '4': [5e8, None, None]})
            P.wj(root / 'cache' / 'frames' / f'Shares-{qs[0]}I.json', {'1': [2e8, '2026-07-30', 'x'], '2': [2e8, '2026-07-30', 'x'], '4': [2e8, '2026-07-30', 'x']})   # $20B cap
            cons = Path(tmp) / 'cons'
            P.wj(cons / 'cache' / 'constituents.json', {'spx': {'members': [['MEM', None]] + [[f'M{i}', None] for i in range(480)], 'source': 't', 'at': 'now'}})
            px = P.Px([d / 'cache' / 'prices'])
            out = P.sp500(root, d, cfg, px, cons, today)
            rows = {r[0]: dict(zip(out['fields'], r)) for r in out['rows']}
            self.assertIn('AAA', rows)
            self.assertTrue(rows['AAA']['eligible'])
            self.assertFalse(rows['BBB']['eligible_earnings'])
            self.assertNotIn('MEM', rows)                              # already a member
            self.assertEqual(out['history'][0][0], 'AAA')
            # a year later AAA has joined: the call is scored
            P.wj(cons / 'cache' / 'constituents.json', {'spx': {'members': [['MEM', None], ['AAA', None]] + [[f'M{i}', None] for i in range(480)], 'source': 't', 'at': 'now'}})
            out2 = P.sp500(root, d, cfg, px, cons, today + dt.timedelta(days=1))
            self.assertEqual(out2['history'][0][3], (today + dt.timedelta(days=1)).isoformat())

    def test_quarter_values_fill_q4_from_the_year(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, root = Path(tmp) / 'hub', Path(tmp) / 'root'
            (d / 'cache' / 'prices').mkdir(parents=True)
            P.wj(d / 'cache' / 'prices' / 'sec-tickers.json', {'rows': [{'ticker': 'AAA', 'cik': 1, 'title': 'AAA INC'}]})
            write_prices(d, 'AAA', lambda i: 100.0, start='2025-06-01', n=360)
            today = dt.date(2026, 10, 19)
            for q in P.calendar_quarters(today, 6):
                if not q.endswith('Q4'):
                    P.wj(root / 'cache' / 'frames' / f'NetIncomeLoss-{q}.json', {'1': [1e8, None, None]})
            P.wj(root / 'cache' / 'frames' / 'NetIncomeLoss-CY2025.json', {'1': [4e8, None, None]})
            P.wj(root / 'cache' / 'frames' / 'Shares-CY2026Q2I.json', {'1': [5e8, '2026-07-30', 'x']})
            cfg = P.cfg_load()
            cfg['sp500_min_mcap'] = 1e10
            out = P.sp500(root, d, cfg, P.Px([d / 'cache' / 'prices']), None, today)
            self.assertEqual(out['rows'][0][4], 4e8)                   # Q4 2025 = 4e8 − 3 × 1e8, four quarters = 4e8


class Targets(unittest.TestCase):
    def test_pt_hits_resolve_after_twelve_months(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, cons = Path(tmp) / 'hub', Path(tmp) / 'cons'
            write_prices(d, 'AAA', lambda i: 100 + i * 0.1, start='2024-06-03', n=600)
            (cons / 'companies').mkdir(parents=True)
            snaps = {'2024-07-01': ['2024-06-30', 1, 1, 1, 1, 120.0, 2.5, 102.0], '2024-07-02': ['2024-06-30', 1, 1, 1, 1, 121.0, 2.5, 102.1],
                     '2024-08-01': ['2024-06-30', 1, 1, 1, 1, 200.0, 2.5, 104.0], '2026-09-01': ['2026-06-30', 1, 1, 1, 1, 160.0, 2.5, 150.0]}
            P.wj(cons / 'companies' / '1.json', {'ticker': 'AAA', 'name': 'AAA', 'sector': 'technology', 'snapshots': snaps})
            out = P.pt_hits(cons, P.Px([d / 'cache' / 'prices']), dt.date(2026, 10, 19))
            r = dict(zip(out['fields'], out['rows'][0]))
            self.assertEqual((r['targets'], r['resolved'], r['hits'], r['pending']), (3, 2, 1, 1))   # 120 reached, 200 not, 160 still open
            self.assertEqual(out['tracking_since'], '2024-07-01')


if __name__ == '__main__':
    unittest.main()
