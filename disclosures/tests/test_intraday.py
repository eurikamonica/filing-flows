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


def hourly(n_days=300, seed=4, half_day=None, volume=True):
    rng = np.random.default_rng(seed)
    t, o, hi, lo, c, v, day, px = [], [], [], [], [], [], dt.date(2024, 11, 4), 100.0
    while n_days > 0:
        if day.weekday() < 5:
            starts = I.MARKS[:-1] if day != half_day else I.MARKS[:4]
            for s in starts:
                t.append(ts(day, s))
                op = px
                px = px * float(np.exp(rng.normal(0, 0.004)))
                o.append(op)
                c.append(px)
                hi.append(max(op, px) * (1 + abs(float(rng.normal(0, 0.001)))))
                lo.append(min(op, px) * (1 - abs(float(rng.normal(0, 0.001)))))
                v.append(float(rng.integers(1_000_000, 5_000_000)) if volume else 0)
            n_days -= 1
        day += dt.timedelta(days=1)
    return {'meta': {'symbol': 'SPY'}, 'timestamp': t, 'indicators': {'quote': [{'open': o, 'high': hi, 'low': lo, 'close': c, 'volume': v}]}}, day


def today_chart(day, last_hhmm, prev, last_price, start='09:30', end='16:00'):
    t = [ts(day, f'{9 + (30 + 5 * i) // 60:02d}:{(30 + 5 * i) % 60:02d}') for i in range(78)]
    t = [x for x in t if x <= ts(day, last_hhmm)]
    closes = list(np.linspace(prev, last_price, len(t)))
    vol = [1000.0 * (i + 1) for i in range(len(t))]                    # heavier later: the VWAP leans to the latest prices
    return {'meta': {'regularMarketPrice': last_price, 'regularMarketTime': ts(day, last_hhmm), 'previousClose': prev,
                     'currentTradingPeriod': {'regular': {'start': ts(day, start), 'end': ts(day, end)}}},
            'timestamp': t, 'indicators': {'quote': [{'close': closes, 'high': [x * 1.0005 for x in closes], 'low': [x * 0.9995 for x in closes], 'volume': vol}]}}


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
        self.assertTrue(all(len(v['p']) == 8 and len(v['h']) == len(v['l']) == len(v['v']) == 7 for v in S.values()))
        H = I.history_of(S)
        self.assertEqual(len(H['days']), len(S) - 1, 'the first day has no previous 4 pm')
        d0, d1 = sorted(S)[:2]
        self.assertAlmostEqual(H['marks'][0][7], S[d1]['p'][7] / S[d0]['p'][7] - 1)
        self.assertEqual(H['close'][0], S[d1]['p'][7])
        b = S[d1]
        self.assertAlmostEqual(H['vw'][0][0], (b['h'][0] + b['l'][0] + b['p'][1]) / 3 / S[d0]['p'][7] - 1, msg='the VWAP after the first hour: its typical price')
        tp = [(b['h'][i] + b['l'][i] + b['p'][i + 1]) / 3 for i in range(7)]
        self.assertAlmostEqual(H['vw'][0][6], sum(x * w for x, w in zip(tp, b['v'])) / sum(b['v']) / S[d0]['p'][7] - 1, msg='at 4 pm: weighted by volume')
        self.assertTrue(all(lo <= hi for lo, hi in zip(H['lo'][0], H['hi'][0])))
        none = I.history_of(I.sessions(hourly(5, volume=False)[0]))
        self.assertTrue(all(v is None for v in none['vw']), 'no volume (some indices): no VWAP')

    def test_vwap(self):
        self.assertEqual(I.vwap_of([2, 4], [0, 2], [1, 3], [1, 3]), [1.0, 2.5])
        self.assertEqual(I.vwap_of([2], [0], [1], [0]), [None])

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
        self.assertEqual(len(T['vwap_path']), len(T['path']))
        self.assertAlmostEqual(T['vwap_path'][0][1], T['path'][0][1], places=6, msg='after one bar the VWAP is its typical price')
        self.assertTrue(T['path'][-1][1] < T['vwap_path'][-1][1] < T['path'][0][1], 'a falling day: the price below its VWAP')


class VwapOdds(unittest.TestCase):
    def hist(self, rows):
        """rows: (gap at 11:30 as price/VWAP-1, the 4 pm close against VWAP, came back) → a hand-built history."""
        days, M, C, VW, HI, LO = [], [], [], [], [], []
        for i, (g, end, back) in enumerate(rows * 40):
            days.append(f'2025-{1 + i // 28:02d}-{1 + i % 28:02d}')
            vw = [0.0] * 7                                            # the VWAP stays at the previous close
            m = [0.0, g / 2, g, g, g, g, g, end]
            M.append(m)
            C.append(100.0 * (1 + 0.001 * i))
            VW.append(vw)
            hi = [max(m[b], m[b + 1]) for b in range(7)]
            lo = [min(m[b], m[b + 1]) for b in range(7)]
            if not back:                                              # never reaches the VWAP after 11:30
                for b in range(2, 7):
                    hi[b], lo[b] = (min(hi[b], -0.0005), lo[b]) if g < 0 else (hi[b], max(lo[b], 0.0005))
            HI.append(hi)
            LO.append(lo)
        return {'cols': [days, M, C, VW, HI, LO]}

    def test_back_and_above(self):
        H = self.hist([(-0.004, -0.003, False), (-0.004, 0.002, True), (0.003, 0.004, False)])
        V = I.vwap_odds(H, -0.004, 2, k=80)
        self.assertEqual(V['similar']['n'], 80)
        self.assertAlmostEqual(V['similar']['back'], 0.5, msg='half the days below VWAP came back to it')
        self.assertAlmostEqual(V['similar']['above'], 0.5, msg='and those closed above it')
        self.assertAlmostEqual(V['base']['above'], 2 / 3, places=3)
        self.assertEqual(I.vwap_odds(H, -0.006, 2)['pct'], 0.0, 'further below VWAP than any day')
        self.assertEqual(I.vwap_odds(H, 0.006, 2)['pct'], 100.0)
        self.assertIsNone(I.vwap_odds(H, 0.001, 0), 'no VWAP at the open')
        self.assertIsNone(I.vwap_odds({'cols': H['cols'][:3]}, 0.001, 2), 'a history without VWAP')
        at4 = I.vwap_odds(H, -0.003, 7)
        self.assertNotIn('back', at4['similar'], 'at 4 pm: nothing left to come back in')


class Scan(unittest.TestCase):
    def test_scan_odds_and_cache(self):
        res, day = hourly(300)
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        last_close = res['indicators']['quote'][0]['close'][-1]
        fake = FakeYahoo(res, today_chart(day, '11:28', last_close, last_close * 0.99))
        now = dt.datetime.combine(day, dt.time(11, 29), ET).astimezone(dt.timezone.utc)
        orig = I.assets
        I.assets = lambda: [('SPY', 'SPY', 'S&P 500 (SPY)', 'market'), ('XLK', 'XLK', 'Technology sector (XLK)', 'sector'),
                            ('IDX-GSPC', '^GSPC', 'S&P 500 index', 'index')]
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
        self.assertLess(a['vs_vwap'], 0, 'a falling day trades below its VWAP')
        self.assertNotIn('vwap', doc['assets']['IDX-GSPC'], "an index's volume is no trade's: no VWAP")
        self.assertIn('odds', doc['assets']['IDX-GSPC'])
        self.assertEqual(len(a['vwap_path']), len(a['path']))
        V = a['vwap_odds']
        self.assertEqual((V['mark'], V['j']), ('11:30', 2))
        self.assertEqual(V['gap'], a['vs_vwap'])
        self.assertEqual(len(V['bins']), 10)
        self.assertEqual(sum(b[0] for b in V['bins']), V['days'], 'every day in one band of the gap')
        self.assertEqual(V['similar']['n'], I.K_SIMILAR)
        self.assertTrue(0 <= V['similar']['back'] <= 1 and 0 <= V['base']['above'] <= 1)
        self.assertLessEqual(V['similar']['gaps'][0], V['gap'])
        self.assertEqual(set(V['similar']['next']), {'1', '5', '21'})
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
