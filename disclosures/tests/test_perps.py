"""app/perps.py: crypto exchanges' stock perpetuals, an experiment beside the RRG's money flow — OKX's and Bitget's daily
taker buy and sell read (stand-in exchanges, offline), kept a run at a time, put on the weekly grid, added to the
published flow files, and what the experiment shows so far."""
import datetime as dt
import gzip
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import flows as FL  # noqa: E402
import perps as P  # noqa: E402

MS = lambda d: str(int(dt.datetime.fromisoformat(d + 'T16:00:00+00:00').timestamp() * 1000))   # a day starts 16:00 UTC


def okx_get(url):
    if 'public/instruments' in url:
        return {'data': [{'instId': 'NVDA-USDT-SWAP', 'instCategory': '3', 'settleCcy': 'USDT'},
                         {'instId': 'BRKB-USDT-SWAP', 'instCategory': '3', 'settleCcy': 'USDT'},
                         {'instId': 'SKHYNIX-USDT-SWAP', 'instCategory': '3', 'settleCcy': 'USDT'},   # no daily bars on the site
                         {'instId': 'BTC-USDT-SWAP', 'instCategory': '1', 'settleCcy': 'USDT'}]}
    if 'NVDA-USDT-SWAP' in url:
        return {'data': [[MS('2026-11-05'), '100', '150'], [MS('2026-11-04'), '0', '0'], [MS('2026-11-03'), '80', '20']]}   # [ts, sell, buy]
    if 'BRKB-USDT-SWAP' in url:
        return {'data': [[MS('2026-11-05'), '5', '7']]}
    raise AssertionError('not asked: ' + url)


def bitget_get(url):
    if 'market/contracts' in url:
        return {'data': [{'symbol': 'NVDAUSDT', 'baseCoin': 'NVDA', 'isRwa': 'YES', 'symbolStatus': 'normal'},
                         {'symbol': 'BTCUSDT', 'baseCoin': 'BTC', 'isRwa': 'NO', 'symbolStatus': 'normal'}]}
    if 'taker-buy-sell' in url:
        return {'data': [{'ts': MS('2026-11-05'), 'buyVolume': '2', 'sellVolume': '1'}, {'ts': MS('2026-11-06'), 'buyVolume': '1', 'sellVolume': '3'}]}
    if 'candles' in url:   # [ts, o, h, l, c, base volume, quote volume]: the day's average price 10, then no volume (its close, 12)
        return {'data': [[MS('2026-11-05'), '9', '11', '9', '10', '50', '500'], [MS('2026-11-06'), '12', '12', '12', '12', '0', '0']]}
    raise AssertionError('not asked: ' + url)


class Collect(unittest.TestCase):
    def test_okx_dollars_by_day(self):
        got = P.okx_collect({'NVDA', 'BRK-B'}, get=okx_get, pause=0, log=lambda *a: None)
        self.assertEqual(got['NVDA'], {'2026-11-05': [150.0, 100.0], '2026-11-03': [20.0, 80.0]})   # [buy, sell]; an empty day skipped
        self.assertEqual(got['BRK-B'], {'2026-11-05': [7.0, 5.0]})       # BRKB is Berkshire's class B
        self.assertNotIn('SKHYNIX', got)

    def test_bitget_shares_times_the_days_average_price(self):
        got = P.bitget_collect({'NVDA'}, get=bitget_get, pause=0, log=lambda *a: None)
        self.assertEqual(got, {'NVDA': {'2026-11-05': [20.0, 10.0], '2026-11-06': [12.0, 36.0]}})

    def test_kept_a_run_at_a_time(self):
        with tempfile.TemporaryDirectory() as d:
            P.collect(d, {'NVDA'}, log=lambda *a: None, venues={'okx': lambda t, log: {'NVDA': {'2026-11-03': [1, 2]}}})
            P.collect(d, {'NVDA'}, log=lambda *a: None, venues={'okx': lambda t, log: {'NVDA': {'2026-11-04': [3, 4]}}})
            doc = json.loads((Path(d) / 'cache' / 'perps' / 'okx.json').read_text())
            self.assertEqual(doc, {'NVDA': {'2026-11-03': [1, 2], '2026-11-04': [3, 4]}})

            def broken(t, log):
                raise RuntimeError('451')
            got = P.collect(d, {'NVDA'}, log=lambda *a: None, venues={'bad': broken, 'okx': lambda t, log: {}})
            self.assertIn('okx', got)                  # one venue failing stops nothing else


class Weeks(unittest.TestCase):
    def test_friday_of(self):
        self.assertEqual(P.friday_of('2026-11-02'), '2026-11-06')
        self.assertEqual(P.friday_of('2026-11-06'), '2026-11-06')   # Friday from 11:00 in New York: still that week
        self.assertEqual(P.friday_of('2026-11-07'), '2026-11-13')   # the weekend: the week after
        self.assertEqual(P.friday_of('2026-11-08'), '2026-11-13')

    def test_weekly_both_venues(self):
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / 'cache' / 'perps'
            c.mkdir(parents=True)
            (c / 'okx.json').write_text(json.dumps({'NVDA': {'2026-11-03': [10, 5], '2026-11-08': [1, 1]}}))
            (c / 'bitget.json').write_text(json.dumps({'NVDA': {'2026-11-05': [2, 4]}}))
            W = P.weekly(d, ['2026-10-30', '2026-11-06', '2026-11-13'])
            self.assertEqual(W['NVDA'], ([None, 12, 1], [None, 9, 1]))


class Experiment(unittest.TestCase):
    def test_stats(self):
        n = 30
        grid = [(dt.date(2026, 4, 3) + dt.timedelta(days=7 * i)).isoformat() for i in range(n)]
        spy = [100.0] * n
        flows = {'SPY': {'ac': spy, 'mf': [0.0] * n, 'dv': [1.0] * n, 'r': [0.4] * n, 'b': [0.4] * n}}
        perps = {}
        for k in range(12):                            # net taker buying that rises with the stock the same week
            sign = [1 if (i + k) % 2 else -1 for i in range(n)]
            ac = [100.0]
            for i in range(1, n):
                ac.append(ac[-1] * (1 + 0.02 * sign[i] * (1 + k / 10)))
            flows[f'T{k}'] = {'ac': ac, 'mf': [s * 0.1 for s in sign], 'dv': [1.0] * n, 'r': [0.4] * n, 'b': [0.4] * n}
            perps[f'T{k}'] = ([1e7 * (1 + 0.1 * s * (1 + k / 10)) for s in sign], [1e7] * n)
        perps['T0'][0][5] = 0.0                        # a quiet week: under $5M traded, left out
        perps['T0'][1][5] = 1e6
        S = P.stats(perps, flows, grid)
        self.assertEqual(S['tickers'], 12)
        self.assertEqual(S['n'], 12 * n - 1)
        self.assertGreater(S['rel']['rho'], 0.9)       # moves with the stock that week
        self.assertGreater(S['y']['rho'], 0.8)        # (the toy's money flow is only ±: ties)
        self.assertLess(S['next']['rho'], -0.9)        # this toy alternates: the next week goes the other way
        self.assertLess(S['persist']['rho'], -0.9)
        self.assertEqual(S['ic']['weeks'], n - 1)
        self.assertIsNone(P.stats(perps, {k: v for k, v in flows.items() if k != 'SPY'}, grid))

    def test_published_with_the_flows(self):
        with tempfile.TemporaryDirectory() as d:
            root, bars = Path(d) / 'flw', Path(d) / 'ohlc'
            days = []
            day = dt.date(2025, 1, 6)
            while len(days) < 5 * 40:
                if day.weekday() < 5:
                    days.append(day)
                day += dt.timedelta(days=1)
            store = FL.Store(root)
            for x in days:
                store.add(x, {'SPY': (160_000, 400_000), 'NVDA': (120_000, 400_000)})
            store.save()
            bars.mkdir()
            for t in ('SPY', 'NVDA'):
                with gzip.open(bars / f'{t}.json.gz', 'wt') as f:
                    json.dump({'t': [x.isoformat() for x in days], 'h': [11.0] * len(days), 'l': [9.0] * len(days), 'c': [10.0] * len(days),
                               'ac': [10.0] * len(days), 'v': [1_000_000] * len(days)}, f)
            c = root / 'cache' / 'perps'
            c.mkdir(parents=True)
            last = days[-1]
            (c / 'okx.json').write_text(json.dumps({'NVDA': {last.isoformat(): [3e6, 1e6]}, 'XYZ': {last.isoformat(): [1, 1]}}))
            idx = FL.build(root, bars, log=lambda *a: None)
            N = json.loads((root / 'public' / 't' / 'NVDA.json').read_text())
            self.assertEqual(N['pb'][-1], 3000)
            self.assertEqual(N['ps'][-1], 1000)
            self.assertIsNone(N['pb'][0])
            self.assertNotIn('pb', json.loads((root / 'public' / 't' / 'SPY.json').read_text()))
            self.assertEqual(idx['perps']['tickers'], ['NVDA'])   # a ticker without daily bars is left out
            self.assertEqual(idx['perps']['venues'], ['OKX', 'Bitget'])


if __name__ == '__main__':
    unittest.main()
