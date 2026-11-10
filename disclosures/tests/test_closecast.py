"""app/closecast.py (the Close forecast tab): the calendar and the dates forecast, the quantiles a ladder and a normal
give, the calibration scale that makes ranges hold, the term structure of implied volatility, the pool, a whole asset
from a feed with no network, and the ledger of official freezes."""
import datetime as dt
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import closecast as C  # noqa: E402

ET = C.ET


def et(y, m, d, hh=12, mm=0):
    return dt.datetime(y, m, d, hh, mm, tzinfo=ET)


class Calendar(unittest.TestCase):
    def test_phase(self):
        self.assertEqual(C.phase_of(et(2026, 11, 10, 9, 0))[:2], (dt.date(2026, 11, 10), 'pre'))
        first, ph, left = C.phase_of(et(2026, 11, 10, 12, 45))
        self.assertEqual((first, ph), (dt.date(2026, 11, 10), 'open'))
        self.assertAlmostEqual(left, 195 / 390)
        self.assertEqual(C.phase_of(et(2026, 11, 10, 16, 5))[:2], (dt.date(2026, 11, 11), 'closed'))
        self.assertEqual(C.phase_of(et(2026, 11, 14, 11, 0))[:2], (dt.date(2026, 11, 16), 'closed'))      # Saturday
        self.assertEqual(C.phase_of(et(2026, 11, 25, 17, 0))[0], dt.date(2026, 11, 27))                   # Thanksgiving
        self.assertEqual(C.close_at(dt.date(2026, 11, 27)).hour, 13)                                       # 1 pm close

    def test_targets_mid_week(self):
        exps = ['2026-11-10', '2026-11-11', '2026-11-12', '2026-11-13', '2026-11-16', '2026-11-20', '2026-12-18']
        t = C.targets(et(2026, 11, 10, 12, 30), exps)
        self.assertEqual([(x['date'], x['tags']) for x in t], [
            ('2026-11-10', ['first', 'expiry']), ('2026-11-11', ['expiry']), ('2026-11-12', ['expiry']),
            ('2026-11-13', ['expiry', 'week']), ('2026-11-20', ['2w']), ('2026-11-30', ['month']), ('2026-12-31', ['quarter'])])

    def test_targets_after_friday_close_and_holidays(self):
        t = C.targets(et(2026, 11, 13, 16, 30), ['2026-11-16', '2026-11-18', '2026-11-20'])
        self.assertEqual(t[0], {'date': '2026-11-16', 'tags': ['first', 'expiry']})
        self.assertEqual([x['date'] for x in t if 'week' in x['tags'] or '2w' in x['tags']], ['2026-11-20', '2026-11-27'])
        t = C.targets(et(2026, 12, 21, 10, 0))                       # the year's last weeks: Christmas, the quarter's end
        d = {x['date']: x['tags'] for x in t}
        self.assertIn('week', d['2026-12-24'])                         # Friday the 25th is a holiday
        self.assertEqual(d['2026-12-31'], ['2w', 'month', 'quarter'])
        self.assertEqual(C.sessions_after(dt.date(2026, 11, 24), dt.date(2026, 11, 30)), 3)  # 25, 27, 30


class Quantiles(unittest.TestCase):
    def test_ladder_matches_a_lognormal(self):
        mu, sg, spot = math.log(100), 0.05, 100.0
        ks = list(np.arange(85, 116, 2.5))
        pa = [1 - C.ND.cdf((math.log(k) - mu) / sg) for k in ks]
        q = C.q_ladder(ks, pa, 1.0, spot)
        want = mu + sg * C.ZG - math.log(spot)
        self.assertLess(float(np.max(np.abs(q - want))), 0.006)   # strikes 2.5% apart: linear between them
        q2 = C.q_ladder([k * 10 for k in ks], pa, 0.1, spot)            # a ladder in index points, read at the ratio
        self.assertLess(float(np.max(np.abs(q2 - q))), 1e-9)
        self.assertTrue((np.diff(q) >= 0).all())

    def test_interval_and_cdf(self):
        q = C.q_normal(0.0, 0.02)
        lo, hi = C.interval(q, 0.8)
        self.assertAlmostEqual(hi, 0.02 * 1.2816, places=4)
        self.assertAlmostEqual(lo, -hi, places=6)
        self.assertAlmostEqual(C.cdf_at(q, 0.0), 0.5, places=6)
        self.assertAlmostEqual(C.cdf_at(q, 0.02 * 1.2816), 0.9, places=3)


class Calibration(unittest.TestCase):
    def test_fit_k(self):
        rng = np.random.default_rng(1)
        Q = np.tile(C.q_normal(0, 1.0), (4000, 1))
        wide = C.fit_k(Q, rng.normal(0, 1.5, 4000))
        self.assertAlmostEqual(wide['k'], 1.5, delta=0.08)
        self.assertLess(wide['raw']['0.8'], 0.65)
        self.assertAlmostEqual(wide['fit']['0.8'], 0.8, delta=0.03)
        self.assertAlmostEqual(C.fit_k(Q, rng.normal(0, 0.6, 4000))['k'], 0.6, delta=0.05)
        self.assertIsNone(C.fit_k(Q[:10], np.zeros(10)))

    def test_k_from_inside80(self):
        self.assertAlmostEqual(C.k_from_inside80(0.8), 1.0, places=3)
        self.assertLess(C.k_from_inside80(0.95), 0.7)
        self.assertGreater(C.k_from_inside80(0.7), 1.2)
        self.assertEqual(C.k_at({'1': {'k': 0.8}, '5': {'k': 1.0}}, 5), 1.0)
        self.assertAlmostEqual(C.k_at({'1': {'k': 0.8}, '5': {'k': 1.0}}, 99), 1.0)

    def test_daily_calibration_on_a_random_walk(self):
        rng = np.random.default_rng(5)
        vol = np.exp(np.cumsum(rng.normal(0, 0.03, 1500)) * 0.2) * 0.01
        c = 100 * np.exp(np.cumsum(rng.standard_t(5, 1500) * vol / math.sqrt(5 / 3)))
        vix = {30: vol * math.sqrt(252) * 100 * 1.25}                 # an index that overstates by a quarter
        out = C.calib_daily(c, vix, every=10, sim_every=25)
        self.assertTrue(0.8 <= out['analogs']['5']['k'] <= 1.3, out['analogs']['5'])
        self.assertTrue(0.7 <= out['sim']['5']['k'] <= 1.3, out['sim']['5'])
        self.assertLess(out['implied']['5']['k'], 0.95)                # the overstatement found and scaled away

    def test_implied_sigma(self):
        lv = {9: 20.0, 30: 22.0, 93: 24.0}
        self.assertAlmostEqual(C.implied_sigma(lv, 30), 0.22 * math.sqrt(30 / 365))
        mid = C.implied_sigma(lv, 60)
        self.assertTrue(0.22 * math.sqrt(60 / 365) < mid < 0.24 * math.sqrt(60 / 365))
        self.assertAlmostEqual(C.implied_sigma({1: 13.0, 30: 20.0}, None, minutes=195), 0.13 * math.sqrt(195 / 525600))


class Pool(unittest.TestCase):
    def test_groups_share_the_weight_and_the_centre_is_given(self):
        a = {'qk': C.q_normal(0.01, 0.02), 'w': 1.0}
        b = {'qk': C.q_normal(-0.02, 0.01), 'w': 1.0}
        c = {'qk': C.q_normal(0.0, 0.04), 'w': 0.5}
        q, w = C.pool({'options': a, 'implied': b, 'analogs': c}, 0.0)
        self.assertEqual(w, {'options': 0.25, 'implied': 0.25, 'analogs': 0.5})
        self.assertAlmostEqual(q[C.MED], 0.0)
        self.assertAlmostEqual(q[-1], (0.25 * 0.02 + 0.25 * 0.01 + 0.5 * 0.04) * C.ZG[-1], places=9)
        q, w = C.pool({'sim': c}, 0.003)
        self.assertEqual(w, {'sim': 1.0})
        self.assertAlmostEqual(q[C.MED], 0.003)


class FakeFeed:
    """Everything from memory: an hourly history, ten years of daily closes, a chain, two ladders, the VIX family."""

    def __init__(self, now):
        self.now = now
        self.today = now.astimezone(ET).date().isoformat()
        rng = np.random.default_rng(3)
        n = 600
        days = [(dt.date(2024, 1, 2) + dt.timedelta(days=i)).isoformat() for i in range(n)]
        marks = np.cumsum(rng.normal(0, 0.003, (n, 8)), axis=1)
        closes = 500 * np.exp(np.cumsum(marks[:, 7]))
        vw = (marks[:, 1:] * 0.8).tolist()
        self.hist = {'cols': [days, marks.tolist(), closes.tolist(), vw, (marks[:, 1:] + 0.001).tolist(), (marks[:, 1:] - 0.001).tolist()]}
        m = 2600
        self.d = {'t': [(dt.date(2016, 1, 4) + dt.timedelta(days=i)).isoformat() for i in range(m)],
                  'c': list(400 * np.exp(np.cumsum(rng.normal(0.0003, 0.011, m))))}
        self.d['ac'] = self.d['c']
        self.vols = {'^VIX1D': 14.0, '^VIX9D': 18.0, '^VIX': 19.0, '^VIX3M': 20.0, '^VIX6M': 21.0, '^GSPC': 7500.0}

    def quote(self, sym):
        if sym in self.vols:
            return {'price': self.vols[sym], 'prev': self.vols[sym]}
        return {'price': 750.0, 'prev': 752.0, 'time': self.now.timestamp(), 'path': [[5, 751.0], [60, 749.0], [180, 750.0]],
                'vwap_path': [[5, 751.0], [60, 750.0], [180, 750.4]]}

    def futures_move(self, sym, day):
        return {'symbol': sym, 'price': 7510.0, 'at_close': 7520.0, 'move': -0.0013}

    def chain(self, sym):
        sm = [[k, round(0.18 + 0.002 * abs(750 - k), 4)] for k in range(700, 801, 5)]
        exps = {e: {'smile': sm, 'max_pain': 745.0, 'call_wall': 760.0, 'put_wall': 740.0} for e in
                ('2026-11-10', '2026-11-11', '2026-11-13', '2026-11-20', '2026-12-18', '2026-12-31', '2027-01-15')}
        return {'exps': exps, 'spreads': {'2026-11-10': 0.3, '2026-11-11': 0.05}, 'quote_time': '2026-11-10 17:30:00',
                'book': {'bid': 749.98, 'ask': 750.02, 'bid_size': 300, 'ask_size': 100}}

    def hourly(self, key, sym):
        return self.hist

    def daily(self, key, sym):
        return self.d


class Asset(unittest.TestCase):
    def test_spy_from_a_feed_with_no_network(self):
        now = et(2026, 11, 10, 12, 35).astimezone(dt.timezone.utc)
        feed = FakeFeed(now)
        cal = {'assets': {'SPY': {'intraday': {'analogs': [{'k': 1.1}] * 7, 'implied': [{'k': 1.4}] * 7},
                                  'daily': {'analogs': {'1': {'k': 1.0}, '63': {'k': 1.05}}, 'sim': {'1': {'k': 1.0}, '63': {'k': 0.8}},
                                            'implied': {'1': {'k': 0.8}, '63': {'k': 0.85}}},
                                  'factors': [None] + [{'coef': [0, 0, 0, 0], 'r2_oos': -0.01, 'n': 300}] * 6}}}
        ks = [7450 + 25 * i for i in range(5)]
        fresh, old = (now - dt.timedelta(minutes=10)).isoformat(), '2026-11-10T13'           # read 10 minutes ago; at 8 am
        lad = [{'source': 'kalshi', 'kind': 'bracket', 'end': '2026-11-10', 'units': '^GSPC', 'strikes': ks, 'p_above': [0.9, 0.7, 0.5, 0.3, 0.1], 'as_of': fresh},
               {'source': 'kalshi', 'kind': 'above', 'end': '2026-11-10', 'units': '^GSPC', 'strikes': ks, 'p_above': [0.99, 0.98, 0.9, 0.8, 0.7], 'as_of': old},
               {'source': 'polymarket', 'kind': 'above', 'end': '2026-11-13', 'units': 'SPY', 'strikes': [730, 740, 750, 760, 770], 'p_above': [0.95, 0.8, 0.5, 0.2, 0.05], 'as_of': old}]
        kl = {'*': {'≤ 6 hours': {'options': 0.65, 'markets': 0.8}, '1–3 days': {'options': 1.2, 'markets': 1.0}}}
        a = C.forecast_asset(C.ASSETS[0], feed, cal, kladder=kl, now=now, ladders=lad)
        self.assertEqual(a['phase'], 'open')
        self.assertEqual(a['mark'], '12:30')
        dates = [t['date'] for t in a['targets']]
        self.assertEqual(dates, ['2026-11-10', '2026-11-11', '2026-11-13', '2026-11-20', '2026-11-30', '2026-12-31'])
        today = a['targets'][0]
        self.assertEqual(set(today['src']), {'options', 'markets', 'implied', 'analogs'})   # no simulation for today's close
        self.assertEqual(today['src']['options']['k'], 0.65)
        self.assertEqual(today['src']['implied']['k'], 1.4)
        self.assertAlmostEqual(today['src']['options']['w'] + today['src']['markets']['w'] + today['src']['implied']['w'], 0.5, places=3)
        self.assertAlmostEqual(today['q'][C.MED], 0.0)                 # centred at the price (the factors did not hold)
        self.assertFalse(a['factors']['applied'])
        self.assertTrue(0 < today['p_prev'] < 0.5)                     # below yesterday's close now
        self.assertEqual(len(today['src']['markets']['ladders']), 1)    # the 8 am ladder is too old for today's close
        fri = a['targets'][2]
        self.assertEqual(fri['tags'], ['expiry', 'week'])
        self.assertIn('markets', fri['src'])                           # 4.6 hours old: still fine three days out
        self.assertIn('sim', fri['src'])
        widths = [t['q'][C.LV_IX[0.8][1]] - t['q'][C.LV_IX[0.8][0]] for t in a['targets']]
        self.assertEqual(widths, sorted(widths))                       # further out, wider
        json.dumps(a, allow_nan=False)


class Ledger(unittest.TestCase):
    def test_freeze_score_and_record(self):
        self.assertEqual(C.freeze_due(et(2026, 11, 10, 9, 50)), '09:45')
        self.assertIsNone(C.freeze_due(et(2026, 11, 10, 9, 50), done={'2026-11-10 09:45'}))
        self.assertIsNone(C.freeze_due(et(2026, 11, 10, 10, 40)))
        self.assertIsNone(C.freeze_due(et(2026, 11, 14, 12, 5)))      # Saturday
        fc = {'generated_at': et(2026, 11, 10, 9, 50).astimezone(dt.timezone.utc).isoformat(),
              'assets': {'SPY': {'start': 750.0, 'prev': 752.0, 'targets': [
                  {'date': '2026-11-10', 'tags': ['first'], 'bucket': '≤ 6 hours', 'lead_h': 6.2, 'q': list(C.q_normal(0, 0.006)),
                   'src': {'options': {'q': list(C.q_normal(0, 0.005))}, 'analogs': {'q': list(C.q_normal(0, 0.008))}}},
                  {'date': '2026-11-13', 'tags': ['week'], 'bucket': '3–7 days', 'lead_h': 78, 'q': list(C.q_normal(0, 0.02)), 'src': {}}]}}}
        fz = C.freeze_doc(fc, '09:45')
        self.assertEqual(fz['slot'], '2026-11-10 09:45')
        self.assertAlmostEqual(fz['assets']['SPY']['targets'][0]['q'][C.MED], 750.0)
        with tempfile.TemporaryDirectory() as tmp:
            r = C.ledger(tmp, fz, {'SPY': {'2026-11-10': 748.0}}, now=et(2026, 11, 10, 16, 20))
            self.assertEqual(r, {'added': True, 'scored': 1})
            self.assertEqual(C.ledger(tmp, fz, {}, now=et(2026, 11, 10, 16, 30))['added'], False)       # once per slot
            rec = json.loads((Path(tmp) / 'public' / 'record.json').read_text())
            row = rec['recent'][0]
            self.assertEqual((row['asset'], row['date'], row['actual']), ('SPY', '2026-11-10', 748.0))
            self.assertTrue(row['inside']['0.8'])                      # −0.27% against a ±0.77% 80% range
            self.assertAlmostEqual(row['pit'], C.ND.cdf(math.log(748 / 750) / 0.006), places=3)
            self.assertEqual(row['src80'], {'options': True, 'analogs': True})
            self.assertEqual(rec['by_time']['09:45']['n'], 1)
            self.assertEqual(len(rec['latest']), 1)


if __name__ == '__main__':
    unittest.main()
