"""intraday.py: Yahoo's hourly bars → full sessions → the move at each mark; today's five-minute bars; the odds at the
nearest mark (percentile, the similar days to the close, the next days); the cache; the session check. No network."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import intraday as I

ET = ZoneInfo('America/New_York')


def ts(day, hhmm):
    h, m = map(int, hhmm.split(':'))
    return int(dt.datetime.combine(day, dt.time(h, m), ET).timestamp())


def hourly(n_days=300, seed=4, half_day=None):
    rng = np.random.default_rng(seed)
    t, o, c, day, px = [], [], [], dt.date(2024, 11, 4), 100.0
    while n_days > 0:
        if day.weekday() < 5:
            starts = I.MARKS[:-1] if day != half_day else I.MARKS[:4]
            for s in starts:
                t.append(ts(day, s))
                op = px
                px = px * float(np.exp(rng.normal(0, 0.004)))
                o.append(op)
                c.append(px)
            n_days -= 1
        day += dt.timedelta(days=1)
    return {'meta': {'symbol': 'SPY'}, 'timestamp': t, 'indicators': {'quote': [{'open': o, 'close': c}]}}, day


def today_chart(day, last_hhmm, prev, last_price, start='09:30', end='16:00'):
    t = [ts(day, f'{9 + (30 + 5 * i) // 60:02d}:{(30 + 5 * i) % 60:02d}') for i in range(78)]
    t = [x for x in t if x <= ts(day, last_hhmm)]
    closes = list(np.linspace(prev, last_price, len(t)))
    return {'meta': {'regularMarketPrice': last_price, 'regularMarketTime': ts(day, last_hhmm), 'previousClose': prev,
                     'currentTradingPeriod': {'regular': {'start': ts(day, start), 'end': ts(day, end)}}},
            'timestamp': t, 'indicators': {'quote': [{'close': closes}]}}


class FakeYahoo:
    def __init__(self, hist, today):
        self.hist, self.today, self.urls, self.calls = hist, today, [], 0

    def json(self, url):
        self.urls.append(url)
        self.calls += 1
        res = self.hist if 'range=730d' in url or 'range=60d' in url else self.today
        return {'chart': {'result': [res], 'error': None}}


class Pieces(unittest.TestCase):
    def test_sessions_and_history(self):
        res, _ = hourly(30, half_day=dt.date(2024, 11, 27))
        S = I.sessions(res)
        self.assertNotIn('2024-11-27', S, 'a half day is left out')
        self.assertTrue(all(len(v) == 8 for v in S.values()))
        H = I.history_of(S)
        self.assertEqual(len(H['days']), len(S) - 1, 'the first day has no previous 4 pm')
        d0, d1 = sorted(S)[:2]
        self.assertAlmostEqual(H['marks'][0][7], S[d1][7] / S[d0][7] - 1)
        self.assertEqual(H['close'][0], S[d1][7])

    def test_rest_edges(self):
        self.assertEqual(I.rest_edges(0.006), [-0.01, -0.0075, -0.005, -0.0025, 0.0, 0.0025, 0.005, 0.0075, 0.01])
        self.assertEqual(I.rest_edges(0.02)[-1], 0.04, 'a wide spread: 1% steps')
        self.assertIsNone(I.rest_edges(0))

    def test_history_falls_back_to_the_cache(self):
        res, _ = hourly(150)

        class Down:
            def json(self, url):
                raise RuntimeError('HTTP 429')
        with tempfile.TemporaryDirectory() as d:
            doc = I.load_history(FakeYahoo(res, None), d, 'SPY', 'SPY', '2025-07-01')
            again = I.load_history(Down(), d, 'SPY', 'SPY', '2025-07-02')
            self.assertEqual(again['cols'][0], doc['cols'][0], "a failed fetch: the last day's history serves")
            with self.assertRaises(RuntimeError):
                I.load_history(Down(), Path(d) / 'empty', 'SPY', 'SPY', '2025-07-02')

    def test_nearest_mark(self):
        self.assertEqual(I.nearest_mark(118), 2)        # 11:28 → 11:30
        self.assertEqual(I.nearest_mark(5), 0)          # 9:35 → the open
        self.assertEqual(I.nearest_mark(390), 7)        # 4 pm

    def test_today(self):
        day = dt.date(2026, 11, 5)
        T = I.today_of(today_chart(day, '11:25', 100.0, 99.5))
        self.assertEqual(T['price'], 99.5)
        self.assertEqual(T['prev'], 100.0)
        self.assertEqual(T['path'][0][0], 5, 'the first bar closes five minutes in')
        self.assertEqual(T['path'][-1][0], 120)


class Scan(unittest.TestCase):
    def test_scan_odds_and_cache(self):
        res, day = hourly(300)
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        last_close = res['indicators']['quote'][0]['close'][-1]
        fake = FakeYahoo(res, today_chart(day, '11:28', last_close, last_close * 0.99))
        now = dt.datetime.combine(day, dt.time(11, 29), ET).astimezone(dt.timezone.utc)
        orig = I.assets
        I.assets = lambda: [('SPY', 'SPY', 'S&P 500 (SPY)', 'market'), ('XLK', 'XLK', 'Technology sector (XLK)', 'sector')]
        try:
            with tempfile.TemporaryDirectory() as d:
                doc = I.scan(fake, Path(d) / 'h60', now=now, log=lambda *a: None)
                self.assertTrue((Path(d) / 'h60' / 'SPY.json').exists())
                n730 = sum('range=730d' in u for u in fake.urls)
                I.scan(fake, Path(d) / 'h60', now=now, log=lambda *a: None)
                self.assertEqual(sum('range=730d' in u for u in fake.urls), n730, 'the second scan of the day reads the cache')
        finally:
            I.assets = orig
        self.assertEqual(doc['schema'], I.SCHEMA)
        self.assertTrue(doc['session']['open'])
        a = doc['assets']['SPY']
        self.assertAlmostEqual(a['move'], -0.01, places=6)
        self.assertTrue(a['today'])
        self.assertFalse(doc['session']['short'])
        o = a['odds']
        self.assertEqual(o['mark'], '11:30')
        self.assertGreater(o['days'], 250)
        self.assertLess(o['pct'], 10, 'a 1% fall by 11:30 is rare with 0.4% hourly moves')
        self.assertEqual(sum(o['dist']), o['days'])
        S = o['similar']
        self.assertEqual(S['n'], I.K_SIMILAR)
        self.assertEqual(len(S['fan']), 8 - 2)
        self.assertEqual(S['fan'][0][1:], [0.0] * 5, 'the fan starts at now')
        self.assertLess(S['close'][0], S['close'][1])
        self.assertLess(S['close'][1], S['close'][2])
        self.assertEqual(set(S['next']), {'1', '5', '21'})
        self.assertLessEqual(S['moves_by_then'][1], -0.004, 'the similar days had fallen by then too')
        self.assertEqual(o['base']['n'], o['days'])
        self.assertEqual(len(o['rest_edges']), 9)
        self.assertEqual(sum(S['rest_dist']), S['n'], 'the similar days to the close, in ten bands')
        self.assertEqual(sum(o['base']['rest_dist']), o['days'])
        json.dumps(doc, allow_nan=False)

    def test_an_early_close(self):
        res, day = hourly(200)
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        last_close = res['indicators']['quote'][0]['close'][-1]
        fake = FakeYahoo(res, today_chart(day, '11:00', last_close, last_close * 1.002, end='13:00'))
        now = dt.datetime.combine(day, dt.time(11, 1), ET).astimezone(dt.timezone.utc)
        orig = I.assets
        I.assets = lambda: [('SPY', 'SPY', 'S&P 500 (SPY)', 'market')]
        try:
            with tempfile.TemporaryDirectory() as d:
                doc = I.scan(fake, Path(d), now=now, log=lambda *a: None)
        finally:
            I.assets = orig
        self.assertTrue(doc['session']['short'], 'a 1 pm close is marked')
        self.assertTrue(doc['session']['open'])

    def test_before_the_open_no_odds(self):
        res, day = hourly(200)
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        prev_day = day - dt.timedelta(days=1)
        fake = FakeYahoo(res, today_chart(prev_day, '16:00', 100, 101) | {'meta': {'regularMarketPrice': 101, 'regularMarketTime': ts(prev_day, '16:00'), 'previousClose': 100,
                                                                                  'currentTradingPeriod': {'regular': {'start': ts(day, '09:30'), 'end': ts(day, '16:00')}}}})
        now = dt.datetime.combine(day, dt.time(8, 0), ET).astimezone(dt.timezone.utc)
        orig = I.assets
        I.assets = lambda: [('SPY', 'SPY', 'S&P 500 (SPY)', 'market')]
        try:
            with tempfile.TemporaryDirectory() as d:
                doc = I.scan(fake, Path(d), now=now, log=lambda *a: None)
        finally:
            I.assets = orig
        self.assertFalse(doc['session']['open'])
        self.assertNotIn('odds', doc['assets']['SPY'], "yesterday's last price is no intraday reading")
        self.assertFalse(doc['assets']['SPY']['today'])
        self.assertTrue(I.session_open(fake, now=now + dt.timedelta(minutes=80)), 'twenty minutes before the open counts')
        self.assertFalse(I.session_open(fake, now=now))


if __name__ == '__main__':
    unittest.main()
