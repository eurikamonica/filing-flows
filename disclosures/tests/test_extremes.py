"""extremes.py: 52-week and all-time highs and lows from daily and monthly bars."""
import datetime as dt
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import extremes as X


def daily(n, f, start='2025-10-01'):
    out, d, i = [], dt.date.fromisoformat(start), 0
    while len(out) < n:
        if d.weekday() < 5:
            c = f(i)
            out.append((d.isoformat(), c, c * 1.01, c * 0.99, c, 1_000_000))
            i += 1
        d += dt.timedelta(days=1)
    return out


class Stats(unittest.TestCase):
    def test_new_low_and_distance_from_high(self):
        b = daily(260, lambda i: 100 - i * 0.2)                           # a steady slide: today is the lowest low
        s = X.stats(b)
        self.assertEqual((s['new_lo'], s['new_hi']), (1, 0))
        self.assertAlmostEqual(s['from_hi'], b[-1][4] / max(x[2] for x in b[-252:]) - 1, places=4)
        self.assertLess(s['ytd'], 0)
        self.assertIsNone(X.stats(b, asof='2030-01-01'))                   # a stock that did not trade that session

    def test_all_time(self):
        s = {'date': '2026-10-19', 'day_hi': 210.0, 'day_lo': 205.0}
        monthly = [('2019-03-01', 0, 150, 20, 140, 0), ('2024-01-01', 0, 200, 90, 180, 0), ('2026-10-01', 0, 210, 190, 205, 0)]
        self.assertEqual(X.all_time(monthly, s), (1, 0, 200.0, 20.0, '2019-03-01'))
        self.assertEqual(X.all_time([('2026-10-01', 0, 210, 190, 205, 0)], s)[:2], (None, None))   # listed this month


class Publish(unittest.TestCase):
    def test_collect_and_publish(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            X.write_json(root / 'cache' / 'prices' / 'sec-tickers.json', {'rows': [{'ticker': 'LOW', 'title': "LOWE'S COMPANIES"},
                                                                                {'ticker': 'HIGH', 'title': 'HIGH FLYER INC'},
                                                                                {'ticker': 'SPY', 'title': 'SPDR S&P 500 ETF TRUST'}]})
            for t in ('LOW', 'HIGH', 'SPY'):
                with gzip.open(root / 'cache' / 'prices' / f'{t}.json.gz', 'wt') as f:
                    json.dump({'rows': [['2026-10-01', 50.0, 1_000_000]] * 20}, f)
            series = {'LOW': daily(260, lambda i: 100 - i * 0.2), 'HIGH': daily(260, lambda i: 50 + i * 0.3)}
            monthly = {'LOW': [('2010-01-01', 0, 300, 20, 200, 0)] + [(series['LOW'][-1][0][:7] + '-01', 0, 60, 47, 48, 0)],
                       'HIGH': [('2021-01-01', 0, 90, 10, 50, 0)] + [(series['HIGH'][-1][0][:7] + '-01', 0, 130, 120, 127, 0)]}
            fake = lambda sym, rng, iv, timeout=25: series[sym] if rng == '1y' else monthly[sym]
            with mock.patch.object(X, 'fetch', side_effect=fake):
                r = X.collect(None, root, {'workers': 2})
            self.assertEqual((r['stocks'], r['new_lows'], r['new_highs']), (2, 1, 1))     # the ETF is left out
            pub = X.publish(root, root / 'market')
            self.assertEqual(pub, {'asof': series['LOW'][-1][0], 'new_lows': 1, 'new_highs': 1, 'ath': 1, 'atl': 0})
            d2 = json.loads((root / 'market' / 'extremes.json').read_text())
            self.assertEqual((d2['new_lows'], d2['ath'], d2['atl']), (['LOW'], ['HIGH'], []))   # LOW is far above its 2010 low
            row = dict(zip(d2['fields'], next(x for x in d2['rows'] if x[0] == 'HIGH')))
            self.assertEqual((row['new_hi'], row['ath'], row['ath_prev'], row['since']), (1, 1, 90.0, '2021-01-01'))


if __name__ == '__main__':
    unittest.main()
