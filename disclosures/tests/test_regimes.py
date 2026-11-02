"""At the lows and in a range (app/regimes.py): low days and what followed them (the next new low, the 10% and 20%
rebounds, the low before the rebound, the rebound from it) on a hand-made path checked against a plain loop; a sideways
range, narrow against its own history, and its breakout; the rows thinned; and the published files, the light lists
and the per-asset blocks from a small universe and from the move-odds build."""
import datetime as dt
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
try:
    import numpy as np
    import highs as HI
    import regimes as G
except ImportError:                                          # numpy is part of the analysis extras
    np = None


def weekdays(start, n):
    d, out = dt.date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def lows_path():
    c = list(np.linspace(100, 130, 300))                     # 0-299: a rise (an ATH every day)
    c += list(np.linspace(129, 70, 80))                      # 300-379: the slide, new 52-week lows near its end
    c += list(np.linspace(71, 84, 20))                       # 380-399: a 20% rebound
    c += list(np.linspace(83, 65, 20))                       # 400-419: a new low under 70
    c += list(np.linspace(66, 100, 281))                     # 420-700: the recovery
    return np.array(c)


def ref_low(c, L, t):
    """What followed day t, by a plain loop."""
    n = len(c)
    low = lambda i: min(c[max(0, i - L + 1):i + 1]) if L else min(c[:i + 1])   # noqa: E731
    new_low = [c[i] <= low(i) * (1 + 1e-12) for i in range(n)]
    nxt = next((i for i in range(t + 1, n) if new_low[i]), n)
    mn, r10 = c[t], None
    for i in range(t + 1, min(n, t + 253)):
        mn = min(mn, c[i])
        if c[i] >= 1.10 * mn:
            r10 = i - t
            break
    out = {'next_low': nxt - t, 'r10': r10}
    if r10 is not None:
        p = t + int(np.argmin(c[t:t + r10 + 1]))
        nl = next((i for i in range(p + 1, n) if new_low[i]), n)
        out.update(trough=p - t, fall=c[p] / c[t] - 1, bounce=max(c[p:min(nl, p + 252, n)]) / c[p] - 1)
    return out


@unittest.skipIf(np is None, 'numpy not installed')
class Lows(unittest.TestCase):
    def test_low_days_and_what_followed(self):
        c = lows_path()
        C = G.common(c)
        o = G.low_frame(c, 252, C)
        rows = list(o['t'])
        # a low day: within 15% of the 52-week low with a new one in the last 63 days (and a year of history)
        for t in (379, 390, 410):
            self.assertIn(t, rows)
        self.assertNotIn(300, rows)                           # far above its low, no new low for a year
        self.assertNotIn(398, rows)                           # 84 is 20% above 70
        for t in (379, 385, 405, 419):
            j = rows.index(t)
            ref = ref_low(c, 252, t)
            self.assertEqual(o['next_low'][j], ref['next_low'], t)
            self.assertEqual(o['r10'][j], ref['r10'], t)
            self.assertEqual(o['trough_days'][j], ref['trough'], t)
            self.assertAlmostEqual(o['fall'][j], ref['fall'], places=9)
            self.assertAlmostEqual(o['bounce'][j], ref['bounce'], places=9)
        j = rows.index(379)
        self.assertAlmostEqual(o['bounce'][j], 84 / 70 - 1, places=9)   # from the low to the top of the rebound, before the next low
        self.assertTrue(o['bounce_closed'][j])
        self.assertEqual(o['fall'][j], 0.0)                   # 379 was the low before the rebound
        self.assertEqual(o['dist'][j], 0.0)
        self.assertEqual(o['age'][j], 379 - 299)              # since its last 52-week high
        k = rows.index(405)
        self.assertLess(o['fall'][k], -0.15)                  # 405 is above 65: the low came later, further down
        self.assertEqual(o['lows_left'][k], 6)                # the closes under 70 on the way (days 414-419) were new lows
        self.assertFalse(o['_today'])
        # the all-time low: 65 at day 419 is under the first close (100)
        a = G.low_frame(c, None, C)
        self.assertIn(419, list(a['t']))
        self.assertIn(379, list(a['t']))                      # 70 is under the first close too
        self.assertEqual(a['next_low'][list(a['t']).index(379)], ref_low(c, None, 379)['next_low'])
        self.assertEqual(a['next_low'][list(a['t']).index(419)], len(c) - 419)   # none after: censored at the end

    def test_thin_keeps_the_last(self):
        r = np.arange(1234)
        t = G.thin(r, 100)
        self.assertLessEqual(len(t), 100)
        self.assertEqual(t[-1], 1233)
        self.assertEqual(list(G.thin(np.arange(7), 100)), list(range(7)))


@unittest.skipIf(np is None, 'numpy not installed')
class Ranges(unittest.TestCase):
    def path(self):
        i = np.arange(1100)
        c = 100 * np.exp(0.15 * np.sin(2 * np.pi * i / 120) + 0.0002 * i)      # wide swings for four years
        coil = c[-1] * np.exp(0.004 * np.sin(2 * np.pi * np.arange(1, 200) / 62))   # 1100-1298: a tight coil
        brk = coil[-1] * np.exp(np.linspace(0.01, 0.12, 60))                   # 1299-1358: the breakout up
        return np.concatenate([c, coil, brk])

    def test_narrow_range_and_breakout(self):
        c = self.path()
        C = G.common(c)
        R = G.range_frame(c, C)
        nr = R['narrow']
        rows = list(nr['t'])
        self.assertIn(1200, rows)                             # inside the coil, the window all coil
        self.assertNotIn(1120, rows)                          # the window still holds the wide swings
        self.assertFalse(any(t > 1300 for t in rows))         # the breakout is no range
        j = rows.index(1200)
        mx, mn = c[1138:1201].max(), c[1138:1201].min()
        self.assertAlmostEqual(nr['width'][j], mx / mn - 1, places=9)
        self.assertLessEqual(nr['width_pct'][j], G.NARROW)    # only the coil's own earlier days were as narrow
        first = next(i for i in range(1201, len(c)) if c[i] > mx or c[i] < mn)
        self.assertEqual(nr['brk'][j], first - 1200)
        self.assertTrue(nr['resolved'][j])
        self.assertEqual(nr['up'][j], 1.0)
        self.assertAlmostEqual(nr['after21'][j], c[first + 21] / c[first] - 1, places=9)
        self.assertEqual(nr['failed'][j], 0.0)                # it never fell back into the lower half
        self.assertGreaterEqual(nr['run'][j], 1100)           # the range began in the coil …
        self.assertEqual(nr['age'][j], 1200 - nr['run'][j] + 1)   # … and its days count from there
        # no day of the coil is a wide range
        self.assertFalse(any(1170 <= t <= 1298 for t in R['wide']['t']))


@unittest.skipIf(np is None, 'numpy not installed')
class Build(unittest.TestCase):
    def universe(self, n_assets=14, n=1500, seed=7):
        rng = np.random.default_rng(seed)
        days = weekdays('2015-01-01', n)
        data, assets = {}, []
        for i in range(n_assets):
            c = 50 * np.exp(np.cumsum(rng.normal(0.0003, 0.015 + 0.002 * i, n)))
            if i == 0:                                           # at a 52-week low now
                c[-40:] = c[-41] * np.exp(np.linspace(-0.01, -0.45, 40))
            if i == 1:                                           # in a tight coil now
                c[-90:] = c[-91] * np.exp(0.002 * np.sin(2 * np.pi * np.arange(90) / 62))
            key = f'C{i}'
            data[key] = (days, c.tolist(), float(c[-1]))
            assets.append({'key': key, 'kind': 'stock', 'cik': 1000 + i, 'name': key})
        spy = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, n)))
        data['SPY'] = (days, spy.tolist(), float(spy[-1]))
        assets.append({'key': 'SPY', 'kind': 'market', 'name': 'S&P 500 (SPY)'})
        return data, assets

    def test_files_lists_and_blocks(self):
        data, assets = self.universe()
        with tempfile.TemporaryDirectory() as tmp:
            lows, ranges, blocks = G.build(data, assets, out_dir=tmp, verbose=False)
            L = json.loads((Path(tmp) / 'lows.json').read_text())
            R = json.loads((Path(tmp) / 'ranges.json').read_text())
        self.assertEqual(L['schema'], lows['schema'])
        self.assertEqual(set(L['regimes']), {'atl', '52w', '3m'})
        self.assertEqual(set(R['regimes']), {'narrow', 'wide'})
        base = L['regimes']['52w']['groups']['companies']['base']
        self.assertGreater(base['days'], 100)
        self.assertEqual(len(base['next_low']['curve']), len(HI.GRID))
        for f, b in L['regimes']['52w']['groups']['companies']['buckets'].items():
            self.assertEqual(len(b['rows']), len(G.LOW_BUCKETS[f][2]))
            self.assertLessEqual(sum(r['days'] for r in b['rows']), base['days'])
        # C0 at a 52-week low now: on the list (light), its full block in its file
        c0 = next(r for r in L['now']['52w'] if r['key'] == 'C0')
        self.assertEqual(c0['state']['date'], data['C0'][0][-1])
        self.assertLessEqual(c0['state']['dist'], G.NEAR)
        self.assertIn('low_date', c0['state'])
        self.assertNotIn('nearest', c0['analogues'])
        self.assertNotIn('curve', c0['analogues']['next_low'])
        full = blocks['C0']['lows']['52w']['analogues']
        self.assertLessEqual(full['days'], HI.K_ANALOG)
        self.assertEqual(len(full['r10']['curve']), len(HI.GRID))
        self.assertNotIn('C0', {e['key'] for e in full['nearest'] if e['date'] > data['C0'][0][-252]})   # none of its own last year
        # C1 in a narrow range now
        self.assertTrue(any(r['key'] == 'C1' for r in R['now']['narrow']))
        b1 = blocks['C1']['ranges']['narrow']
        self.assertLess(b1['state']['width'], 0.02)
        self.assertIn('breakout', b1['analogues'])
        json.dumps(L, allow_nan=False)
        json.dumps(R, allow_nan=False)
        json.dumps(blocks, allow_nan=False)


@unittest.skipIf(np is None, 'numpy not installed')
class InTheMoveOdds(unittest.TestCase):
    def test_moves_build_publishes_the_lows_and_ranges(self):
        import moves as M
        import paths as P
        with tempfile.TemporaryDirectory() as tmp:
            root, val = Path(tmp) / 'pth', Path(tmp) / 'val'
            days = weekdays('2021-01-04', 900)
            rng = np.random.default_rng(9)

            def put(t, drift=0.0005, scale=0.012, crash=False):
                c = 100 * np.exp(np.cumsum(rng.normal(drift, scale, len(days))))
                if crash:
                    c[-30:] = c[-31] * np.exp(np.linspace(-0.02, -0.5, 30))
                c = list(c)
                P.save(root, t, {'ticker': t, 'source': 'yahoo', 'fetched_at': '2026-01-01T00:00:00+00:00', 't': list(days), 'o': c, 'h': c, 'l': c,
                                 'c': c, 'ac': c, 'v': [1000 + 10 * (i % 7) for i in range(len(days))]})
            for t in ('SPY', 'XLK'):
                put(t)
            rows = []
            for i in range(4):
                t = f'CO{i}'
                put(t, drift=0.001, scale=0.02, crash=i == 0)
                rows.append([1000 + i, t, f'COMPANY {i} INC', 'technology', 'industrial', 1e9 * (10 - i)])
                (val / 'c').mkdir(parents=True, exist_ok=True)
                (val / 'c' / f'{1000 + i}.json').write_text(json.dumps({'cik': 1000 + i, 'industry': 'Semis', 'sic': '3674'}))
            (val / 'index.json').write_text(json.dumps({'fields': ['cik', 'ticker', 'name', 'sector', 'kind', 'mcap'], 'rows': rows}))
            st = M.build(root, val / 'index.json')
            self.assertEqual(st['errors'], [])
            out = root / 'public' / 'moves'
            L = json.loads((out / 'lows.json').read_text())
            self.assertTrue((out / 'ranges.json').exists())
            self.assertIn('52w', L['regimes'])
            self.assertGreaterEqual(st['regimes']['lows_52w'], 1)
            doc = json.loads((out / 'a' / 'CO0.json').read_text())
            self.assertIn('52w', doc['lows'])
            self.assertEqual(doc['lows']['52w']['state']['date'], days[-1])
            self.assertTrue(math.isfinite(doc['lows']['52w']['state']['volu']))      # the volume of the bars on file


if __name__ == '__main__':
    unittest.main()
