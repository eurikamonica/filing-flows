"""intraday_rotation.py: Yahoo's five-minute bars → sessions bar by bar (the last price closing its bar); the grid and
its coding; Chaikin's flow bar by bar; relative volume and the inflow rank against the sessions before; the file from a
fake feed (the cache, today's bars reused, a bar still forming read at the next scan). No network."""
import datetime as dt
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import intraday_rotation as IR

ET = ZoneInfo('America/New_York')


def ts(day, hhmm):
    h, m = map(int, hhmm.split(':'))
    return int(dt.datetime.combine(day, dt.time(h, m), ET).timestamp())


def sessions_before(day, n):
    out, d = [], day
    while len(out) < n:
        d -= dt.timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return out[::-1]


def chart_of(days, bars_per_day, seed, drift=0.0, upclose=0.0, prev=None, last_point=None, base=100.0, vol=1000):
    """A Yahoo chart: five-minute bars for each day (bars_per_day[i] of them); upclose pushes closes toward the bar's high
    (money flowing in); last_point: (time, price) appended as Yahoo's last price."""
    rng = np.random.default_rng(seed)
    t, op_, hi, lo, c, v, px = [], [], [], [], [], [], base
    for day, n in zip(days, bars_per_day):
        for k in range(n):
            m = 9 * 60 + 30 + 5 * k
            t.append(ts(day, f'{m // 60:02d}:{m % 60:02d}'))
            op = px * (1.002 if k == 0 else 1.0)                     # a gap at the open
            op_.append(op)
            px = op * float(np.exp(drift + rng.normal(0, 0.001)))
            h_, l_ = max(op, px) * 1.0006, min(op, px) * 0.9994
            cl = min(h_, px + upclose * (h_ - px))
            hi.append(h_)
            lo.append(l_)
            c.append(cl)
            v.append(float(vol * (1 + (k == 0))))
            px = cl
    if last_point:
        t.append(ts(days[-1], last_point[0]))
        op_.append(last_point[1])
        hi.append(last_point[1])
        lo.append(last_point[1])
        c.append(last_point[1])
        v.append(0)
    return {'meta': {'regularMarketPrice': c[-1], 'previousClose': prev or base, 'currentTradingPeriod': {'regular': {
        'start': ts(days[-1], '09:30'), 'end': ts(days[-1], '16:00')}}},
        'timestamp': t, 'indicators': {'quote': [{'open': op_, 'high': hi, 'low': lo, 'close': c, 'volume': v}]}}


class Bars(unittest.TestCase):
    def test_bars_and_the_last_price(self):
        day = dt.date(2026, 11, 11)
        res = chart_of([day], [12], 1, last_point=('10:31', 101.5))
        b = IR.bars_of(res)['2026-11-11']
        self.assertEqual(sorted(b), list(range(1, 14)))              # 9:30 → bar 1 (closes 9:35) … 10:25 → bar 12
        self.assertEqual(b[13], [101.5, 101.5, 101.5, 0.0])           # 10:31: the bar forming, 13 (10:30–10:35)
        res = chart_of([day], [12], 1, last_point=('10:28', 101.5))
        b2 = IR.bars_of(res)['2026-11-11']
        self.assertEqual(sorted(b2), list(range(1, 13)))
        self.assertEqual(b2[12][2], 101.5)                            # 10:28 falls in the 10:25 bar: it closes it
        self.assertGreaterEqual(b2[12][0], 101.5)
        self.assertEqual(b2[12][3], b[12][3])                         # no volume added
        four = chart_of([day], [78], 2, last_point=('16:00', 99.0))
        self.assertEqual(IR.bars_of(four)['2026-11-11'][78][2], 99.0)  # 4 pm's print closes the last bar

    def test_grid_coding(self):
        days = ['a', 'b']
        closes = IR.on_grid(days, [3, 2], {'a': {2: [1, 1, 10.0, 5]}, 'b': {1: [1, 1, 11.0, 5]}})
        self.assertEqual(closes, [10.0, 10.0, 10.0, 11.0, 11.0])      # the first close fills the start; no trade keeps the last
        self.assertIsNone(IR.on_grid(days, [3, 2], {}))
        rng = np.random.default_rng(3)
        c = list(100 * np.exp(np.cumsum(rng.normal(0, 0.002, 500))))
        c0, d = IR.code(c)
        back = IR.decode(c0, d)
        self.assertLess(max(abs(x / y - 1) for x, y in zip(back, c)), 6e-6)   # half a tenth of a basis point, no drift
        self.assertEqual(d[0], 0)

    def test_chaikin(self):
        bars = {1: [11.0, 9.0, 11.0, 100], 2: [11.0, 9.0, 9.0, 100], 3: [11.0, 9.0, 10.0, 100], 4: [10.0, 10.0, 10.0, 50]}
        dv, nf = IR.flows(bars, 5)
        self.assertEqual(len(dv), 5)
        self.assertAlmostEqual(nf[0], dv[0])                          # closed at the high: all in
        self.assertAlmostEqual(nf[1], -dv[1])                         # at the low: all out
        self.assertAlmostEqual(nf[2], 0.0)                            # mid-range
        self.assertEqual((nf[3], dv[4]), (0.0, 0.0))                  # no range; no bar
        self.assertAlmostEqual(IR.share(dv, nf), (dv[0] - dv[1]) / sum(dv))


class Reading(unittest.TestCase):
    def test_against_the_sessions_before(self):
        days = [d.isoformat() for d in sessions_before(dt.date(2026, 11, 11), 20)]
        rng = np.random.default_rng(7)
        hist = {}
        for d in days:                                                # 20 sessions of flat flow, about 1,000 shares a bar
            hist[d] = {k: [10.1, 9.9, 10.0 + float(rng.normal(0, 0.03)), 1000.0] for k in range(1, 79)}
        today = {k: [10.1, 9.9, 10.09, 2000.0] for k in range(1, 31)}   # closes near the highs on twice the volume
        r = IR.reading(today, 30, hist, '2026-11-11')
        self.assertEqual(r['n'], 20)
        self.assertAlmostEqual(r['rvol'], 2.0, delta=0.02)
        self.assertGreater(r['share'], 0.8)
        self.assertEqual(r['rank'], 1.0)
        self.assertGreater(r['z'], 3)
        self.assertAlmostEqual(r['h1'], r['share'], places=3)
        quiet = IR.reading(today, 30, {d: hist[d] for d in days[:5]}, '2026-11-11')
        self.assertNotIn('rvol', quiet)                               # under ten sessions to compare: no rank, no relative volume
        self.assertNotIn('rank', quiet)


class Build(unittest.TestCase):
    def test_the_file(self):
        today = dt.date(2026, 11, 11)
        before = sessions_before(today, 22)
        now = dt.datetime.combine(today, dt.time(11, 7), ET).astimezone(dt.timezone.utc)   # bar 19 (11:00–11:05) done, 20 forming
        feed = {}
        for i, t in enumerate(IR.tickers()):
            flow = 0.6 if t == 'XLE' else -0.6 if t == 'XLU' else 0.0
            feed[(t, '1mo')] = chart_of(before + [today], [78] * 21 + [42] + [20], seed=i, upclose=0.0, base=50 + i)
            feed[(t, '1d')] = chart_of([today], [20], seed=100 + i, upclose=flow, prev=50 + i, base=50 + i, last_point=('11:06', 50 + i + 0.2))
        calls = []

        def chart(h, sym, rng, interval):
            calls.append((sym, rng))
            if sym == 'BAD':
                raise RuntimeError('no chart')
            return feed[(sym, rng)]
        with tempfile.TemporaryDirectory() as tmp:
            doc = IR.build(None, Path(tmp) / 'm5', chart, now=now, log=lambda m: None)
            n_month = sum(1 for _, r in calls if r == '1mo')
            doc2 = IR.build(None, Path(tmp) / 'm5', chart, now=now, log=lambda m: None)   # the month from the cache now
            self.assertEqual(sum(1 for _, r in calls if r == '1mo'), n_month)
            self.assertEqual(json.dumps(doc2['assets']['XLK']['c']), json.dumps(doc['assets']['XLK']['c']))
            cached = json.loads((Path(tmp) / 'm5' / 'SPY.json').read_text())
            self.assertEqual(cached['refreshed'], '2026-11-11')
            self.assertNotIn('2026-11-11', cached['days'])           # today's comes with every scan
        s = doc['session']
        self.assertEqual((s['date'], s['open'], s['k'], s['kf'], s['last']), ('2026-11-11', True, 20, 19, '11:10'))
        self.assertEqual(len(doc['days']), IR.PRIOR + 1)
        self.assertEqual(doc['slots'][-1], 20)
        self.assertIn(42, doc['slots'])                              # an early close keeps its own count
        self.assertEqual(len(doc['assets']), len(IR.tickers()))
        for t, a in doc['assets'].items():
            self.assertEqual(len(a['c']), sum(doc['slots']), t)
            self.assertEqual((len(a['dv']), len(a['nf'])), (20, 20), t)
            self.assertEqual(a['now']['k'], 19)
        xle, xlu, spy = (doc['assets'][t]['now'] for t in ('XLE', 'XLU', 'SPY'))
        self.assertGreater(xle['share'], 0.3)
        self.assertLess(xlu['share'], -0.3)
        self.assertGreater(xle['rank'], 0.9)
        self.assertLess(xlu['rank'], 0.1)
        self.assertEqual(xle['n'], 20)
        closes = IR.decode(doc['assets']['SPY']['c0'], doc['assets']['SPY']['c'])
        self.assertAlmostEqual(closes[-1], 50.2, places=3)            # the last price closes today's last bar
        self.assertEqual([g[0] for g in doc['groups']], [g for g, _, _ in IR.GROUPS])
        o = doc['assets']['XLK']['o']
        self.assertEqual(len(o), len(doc['days']))
        self.assertTrue(all(x and x > 0 for x in o))                  # each session's opening price: the gaps can be left out
        self.assertEqual(o[-1], round(IR.opens_of(feed[('XLK', '1d')])['2026-11-11'], 4))
        self.assertEqual(cached['opens'].keys(), cached['days'].keys())
        json.dumps(doc, allow_nan=False)


if __name__ == '__main__':
    unittest.main()
