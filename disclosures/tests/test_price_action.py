"""app/price_action.py: every detector on bars built to contain its pattern exactly (and its mirror image), sane firing
rates on random walks, no look-ahead, the volume profile, Elliott's hard rules, fair value gaps, the pooled walk-forward
statistics (clustered t, Benjamini–Hochberg, the evidence grades) and the JSON readings for the page."""
import collections
import datetime as dt
import json
import math
import sys
import time
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import price_action as PA  # noqa: E402


# ------------------------------------------------------------------ bar builders
class Bars:
    """Bars appended one at a time; close_to() opens at the previous close and adds a fixed wick on each side."""

    def __init__(self):
        self.o, self.h, self.l, self.c, self.v = [], [], [], [], []

    def bar(self, o, h, l, c, v=1e6):
        for xs, x in ((self.o, o), (self.h, h), (self.l, l), (self.c, c), (self.v, v)):
            xs.append(float(x))
        return len(self.c) - 1

    def close_to(self, c, wick=0.2, v=1e6):
        o = self.c[-1] if self.c else c
        return self.bar(o, max(o, c) + wick, min(o, c) - wick, c, v)

    def path(self, start, segs, wick=0.2, v=1e6):
        """Straight legs through the pivots: segs = [(target close, bars)]. Returns the pivot bar indices."""
        if not self.c:
            self.close_to(start, wick, v)
        piv = [len(self.c) - 1]
        for tgt, n in segs:
            a = self.c[-1]
            for k in range(1, n + 1):
                self.close_to(a + (tgt - a) * k / n, wick, v)
            piv.append(len(self.c) - 1)
        return piv

    def cycle(self, values, n, wick=0.2, v=1e6):
        for k in range(n):
            self.close_to(values[k % len(values)], wick, v)

    def arrays(self):
        return tuple(np.array(x, float) for x in (self.o, self.h, self.l, self.c, self.v))


def flip(arrs, K=100.0):
    """The mirror image in log price (p → K² / p): ups become downs, ratios are kept, high and low swap."""
    o, h, l, c, v = arrs
    return K * K / o, K * K / l, K * K / h, K * K / c, v


def fired(arrs, rule):
    return {(e['i'], e['dir']) for e in PA.detect(*arrs) if e['rule'] == rule}


def random_walk(n=2500, seed=1, drift=0.0003, vol=0.018):
    rng = np.random.default_rng(seed)
    r = rng.normal(drift, vol, n)
    c = 50 * np.exp(np.cumsum(r))
    o = np.concatenate(([c[0]], c[:-1])) * np.exp(rng.normal(0, 0.004, n))
    h = np.maximum(o, c) * np.exp(np.abs(rng.normal(0, 0.008, n)))
    l = np.minimum(o, c) * np.exp(-np.abs(rng.normal(0, 0.008, n)))
    v = rng.lognormal(13, 0.4, n)
    v[rng.random(n) < 0.01] = 0.0                       # the occasional zero-volume day
    return o, h, l, c, v


def bdays(n, start='2015-01-02'):
    d = dt.date.fromisoformat(start)
    out = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


class Mirror:
    """assert_both: the pattern fires at bar i with direction d, and its mirror image fires there with the opposite."""

    def assert_both(self, arrs, rule, i, d, rule_mirror=None):
        opp = {'bull': 'bear', 'bear': 'bull'}[d]
        self.assertIn((i, d), fired(arrs, rule), rule)
        self.assertIn((i, opp), fired(flip(arrs), rule_mirror or rule), rule_mirror or rule)


# ------------------------------------------------------------------ the catalogue
class Catalogue(unittest.TestCase):
    def test_rules_are_documented(self):
        ids = [r['id'] for r in PA.RULES]
        self.assertEqual(len(ids), len(set(ids)))
        for r in PA.RULES:
            self.assertEqual(set(r), {'id', 'name', 'family', 'dir', 'subjective', 'kind', 'what', 'rule', 'source'}, r['id'])
            self.assertIn(r['family'], PA.FAMILIES)
            self.assertIn(r['dir'], ('bull', 'bear', 'both'))
            self.assertIn(r['kind'], ('event', 'state'))
            self.assertTrue(len(r['what']) > 60 and len(r['rule']) > 30 and r['source'], r['id'])
        for fam in PA.FAMILIES:
            self.assertTrue(any(r['family'] == fam for r in PA.RULES), fam)
        subj = {r['family'] for r in PA.RULES if r['subjective']}
        self.assertTrue({'brooks', 'ict', 'elliott', 'wyckoff'} <= subj)
        self.assertFalse(any(r['subjective'] for r in PA.RULES if r['family'] == 'quant'))
        o, h, l, c, v = random_walk(1500, 3)
        emitted = {e['rule'] for e in PA.detect(o, h, l, c, v)}
        self.assertTrue(emitted <= set(PA.EVENT_RULES), emitted - set(PA.EVENT_RULES))
        for e in PA.detect(o, h, l, c, v):
            want = PA.RULE[e['rule']]['dir']
            self.assertTrue(want == 'both' or want == e['dir'], e)


# ------------------------------------------------------------------ candlesticks
class Candles(Mirror, unittest.TestCase):
    def decline(self, n=15, to=90.0):
        b = Bars()
        b.path(100, [(to, n)])
        return b

    def test_hammer_and_shooting_star(self):
        b = self.decline()
        i = b.bar(89.7, 89.85, 87.6, 89.8)
        self.assert_both(b.arrays(), 'hammer', i, 'bull', 'shooting_star')
        self.assertNotIn((i, 'bull'), fired(b.arrays(), 'shooting_star'))
        b = Bars()                                      # the same bar after a RISE is not a hammer
        b.path(80, [(90, 15)])
        i = b.bar(89.7, 89.85, 87.6, 89.8)
        self.assertNotIn((i, 'bull'), fired(b.arrays(), 'hammer'))

    def test_engulfing(self):
        b = self.decline()
        b.bar(90.4, 90.5, 89.4, 89.5)
        i = b.bar(89.4, 90.8, 89.3, 90.7)
        self.assert_both(b.arrays(), 'bull_engulfing', i, 'bull', 'bear_engulfing')

    def test_inside_bar_and_doji(self):
        b = Bars()
        b.path(100, [(110, 15)])
        i = b.bar(109.8, 110.1, 109.7, 109.9)
        self.assert_both(b.arrays(), 'inside_bar', i, 'bull')
        b = Bars()
        b.path(100, [(110, 15)])
        i = b.bar(110.0, 110.8, 109.3, 110.02)
        self.assert_both(b.arrays(), 'doji', i, 'bear')     # after a rise a doji points down

    def test_morning_and_evening_star(self):
        b = self.decline(12, 92.0)
        b.bar(92.0, 92.1, 89.9, 90.0)
        b.bar(89.8, 89.95, 89.5, 89.7)
        i = b.bar(89.9, 91.6, 89.8, 91.5)
        self.assert_both(b.arrays(), 'morning_star', i, 'bull', 'evening_star')

    def test_three_soldiers_and_crows(self):
        b = self.decline(10, 95.0)
        b.bar(95.0, 95.95, 94.9, 95.9)
        b.bar(95.5, 96.9, 95.4, 96.8)
        i = b.bar(96.4, 97.8, 96.3, 97.7)
        self.assert_both(b.arrays(), 'three_white_soldiers', i, 'bull', 'three_black_crows')
        self.assertEqual(fired(b.arrays(), 'three_white_soldiers'), {(i, 'bull')})


# ------------------------------------------------------------------ Al Brooks
class Brooks(Mirror, unittest.TestCase):
    def test_h2_buy_and_l2_sell(self):
        b = Bars()
        b.path(100, [(139, 39)], wick=0.3)
        b.bar(139.0, 139.1, 137.8, 138.0)               # pullback starts: lower high
        b.bar(138.0, 139.2, 137.9, 138.9)               # high 1
        b.bar(138.9, 139.0, 137.6, 137.8)
        i = b.bar(137.8, 139.25, 137.7, 139.1)          # high 2, still below the trend high
        self.assertEqual(fired(b.arrays(), 'h2_buy'), {(i, 'bull')})
        self.assertEqual(fired(flip(b.arrays()), 'l2_sell'), {(i, 'bear')})

    def test_always_in_flip(self):
        b = Bars()
        piv = b.path(150, [(100, 60), (150, 60)])
        ev = fired(b.arrays(), 'always_in_flip')
        self.assertEqual(len(ev), 1)
        (i, d), = ev
        self.assertEqual(d, 'bull')
        self.assertTrue(piv[1] < i <= piv[1] + 12, (i, piv))

    def test_wedge_top_and_bottom(self):
        b = Bars()
        piv = b.path(95, [(110, 15), (105, 5), (113, 8), (108, 5), (115, 7), (95, 20)])
        j3 = piv[5]
        self.assert_both(b.arrays(), 'wedge_top', j3 + 8, 'bear', 'wedge_bottom')
        self.assertEqual(fired(b.arrays(), 'wedge_top'), {(j3 + 8, 'bear')})

    def test_strong_and_failed_breakout(self):
        b = Bars()
        b.cycle([100, 101], 30)
        i = b.bar(101, 103.1, 100.9, 103.0)
        self.assert_both(b.arrays(), 'brooks_breakout', i, 'bull')
        b = Bars()
        b.cycle([100, 101], 30)
        b.bar(101, 101.6, 100.9, 101.5)
        i = b.bar(101.5, 101.6, 100.4, 100.5)
        self.assert_both(b.arrays(), 'failed_breakout', i, 'bear')


# ------------------------------------------------------------------ market structure and ICT
class Structure(Mirror, unittest.TestCase):
    def build(self):
        b = Bars()
        piv = b.path(104, [(100, 4), (110, 10), (105, 5), (115, 10), (110, 5), (120, 10), (100, 20)])
        return b, piv

    def test_bos_choch_and_labels(self):
        b, piv = self.build()
        bos = piv[5] + 6                                # first close above the 115 swing high (115.2): 116
        choch = piv[6] + 11                             # first close below the 110 swing low (109.8): 109
        self.assertEqual(fired(b.arrays(), 'bos'), {(bos, 'bull')})
        self.assertEqual(fired(b.arrays(), 'choch'), {(choch, 'bear')})
        self.assertEqual(fired(flip(b.arrays()), 'bos'), {(bos, 'bear')})
        st = PA.state(*b.arrays(), bdays(len(b.c)))
        labels = [s['label'] for s in st['structure']['swings']]
        self.assertEqual(labels, [None, None, 'HL', 'HH', 'HL', 'HH'])
        self.assertEqual(st['structure']['trend'], 'down')
        self.assertEqual(st['structure']['last_choch']['level'], 109.8)

    def test_order_block_retest(self):
        b, piv = self.build()
        k = piv[6] + 9                                  # first bar back into the 109.8–111.2 block: close 111
        ev = [e for e in PA.detect(*b.arrays()) if e['rule'] == 'order_block']
        self.assertEqual([(e['i'], e['dir']) for e in ev], [(k, 'bull')])
        self.assertEqual((ev[0]['info']['bottom'], ev[0]['info']['top']), (109.8, 111.2))

    def test_liquidity_sweep(self):
        b = Bars()
        b.path(100, [(110, 10), (104, 6), (109, 5)])
        i = b.bar(109.0, 110.6, 108.9, 109.6)
        self.assert_both(b.arrays(), 'liquidity_sweep', i, 'bear')

    def test_fair_value_gap(self):
        b = Bars()
        b.path(100, [(105, 10)], wick=0.3)
        b.bar(105.0, 107.6, 104.9, 107.5)
        b.bar(107.5, 108.0, 106.0, 107.8)               # low 106.0 above the high two bars back (105.3): a bullish gap
        for c in (108.2, 108.5, 107.5, 106.8):
            b.close_to(c, wick=0.2)
        arrs = b.arrays()
        st = PA.state(*arrs, bdays(len(b.c)))
        gaps = [(g['dir'], g['bottom'], g['top'], g['filled']) for g in st['ict']['fvgs']]
        self.assertIn(('bull', 105.3, 106.0, None), gaps)
        i = b.bar(106.8, 106.9, 105.6, 106.3)           # back into the gap, closes above its bottom
        self.assert_both(b.arrays(), 'fvg_return', i, 'bull')
        self.assertEqual(fired(arrs, 'fvg_return'), set())


# ------------------------------------------------------------------ chart patterns
class Patterns(Mirror, unittest.TestCase):
    def first_close_below(self, c, start, line):
        return next(i for i in range(start, len(c)) if c[i] < line(i))

    def test_head_and_shoulders(self):
        b = Bars()
        piv = b.path(104, [(100, 6), (110, 8), (104, 8), (116, 8), (104.2, 8), (110.3, 8), (95, 20)])
        j2, j4, j5 = piv[3], piv[5], piv[6]
        neck = lambda i: 104 + 0.2 * (i - j2) / (j4 - j2)
        i = self.first_close_below(b.c, j5 + PA.EXT_W, neck)
        self.assertEqual(fired(b.arrays(), 'head_shoulders'), {(i, 'bear')})
        self.assertEqual(fired(flip(b.arrays()), 'inv_head_shoulders'), {(i, 'bull')})
        self.assertEqual(fired(b.arrays(), 'double_top'), set())

    def test_double_top_and_bottom(self):
        b = Bars()
        piv = b.path(104, [(100, 6), (110, 12), (104, 12), (110.5, 12), (95, 20)])
        i = self.first_close_below(b.c, piv[4] + PA.EXT_W, lambda _: 104)
        self.assertEqual(fired(b.arrays(), 'double_top'), {(i, 'bear')})
        self.assertEqual(fired(flip(b.arrays()), 'double_bottom'), {(i, 'bull')})
        self.assertEqual(fired(b.arrays(), 'head_shoulders'), set())

    def test_triangle_breakout(self):
        b = Bars()
        piv = b.path(100, [(110, 8), (100, 8), (108, 8), (102, 8), (106, 8), (104, 5), (112, 8)])
        self.assertEqual(fired(b.arrays(), 'triangle'), {(piv[5] + 7, 'bull')})
        self.assertEqual(fired(flip(b.arrays()), 'triangle'), {(piv[5] + 7, 'bear')})

    def test_flags(self):
        b = Bars()
        b.cycle([100, 100.3], 20, wick=0.1)
        b.path(100, [(109, 6)], wick=0.1)
        b.path(109, [(107.4, 8)], wick=0.1)
        i = b.bar(107.4, 109.6, 107.3, 109.5)
        self.assertEqual(fired(b.arrays(), 'bull_flag'), {(i, 'bull')})
        self.assertEqual(fired(flip(b.arrays()), 'bear_flag'), {(i, 'bear')})

    def test_cup_with_handle(self):
        b = Bars()
        b.path(100, [(110, 10)])
        for t in range(1, 61):
            b.close_to(110 - 25 * math.sin(math.pi * t / 60))
        j = len(b.c) - 1
        b.path(110, [(104, 6), (114, 10)])
        i = next(k for k in range(j + 1, len(b.c)) if b.c[k] > 110)
        self.assertEqual(fired(b.arrays(), 'cup_handle'), {(i, 'bull')})
        b2 = Bars()                                     # a V-shaped base is not a cup
        b2.path(100, [(110, 10), (85, 30), (110, 30), (104, 6), (114, 10)])
        self.assertEqual(fired(b2.arrays(), 'cup_handle'), set())


# ------------------------------------------------------------------ Wyckoff and VSA
class WyckoffVSA(Mirror, unittest.TestCase):
    CYCLE = [100, 101, 101.5, 101, 100, 99, 98.5, 99]

    def accumulation(self):
        b = Bars()
        b.path(150, [(100, 70)], wick=0.3)
        b.cycle(self.CYCLE, 40, wick=0.3)
        return b

    def test_spring_and_sign_of_strength(self):
        b = self.accumulation()
        i = b.bar(100.0, 100.3, 97.0, 99.5, 2.5e6)
        b.cycle([100, 101], 3, wick=0.3)
        k = b.bar(101.0, 104.6, 100.9, 104.5, 2e6)
        self.assert_both(b.arrays(), 'spring', i, 'bull', 'upthrust')
        self.assert_both(b.arrays(), 'sos', k, 'bull', 'sow')
        ev = [e for e in PA.detect(*b.arrays()) if e['rule'] == 'spring']
        self.assertEqual(ev[0]['info']['phase'], 'accumulation')
        self.assertGreater(ev[0]['info']['volume_ratio'], 2)
        st = PA.state(*b.arrays(), bdays(len(b.c)))
        self.assertEqual(st['wyckoff']['phase'], 'markup')
        st = PA.state(*[x[:i] for x in b.arrays()], bdays(i))
        self.assertEqual(st['wyckoff']['phase'], 'accumulation')
        self.assertTrue(st['wyckoff']['range']['active'])

    def base(self, n=30):
        b = Bars()
        b.cycle([100, 100.5], n, wick=0.25)
        return b

    def test_no_demand_and_no_supply(self):
        b = self.base()
        c1 = b.c[-1]
        i = b.bar(c1, c1 + 0.25, c1 - 0.1, c1 + 0.1, 0.5e6)
        self.assertIn((i, 'bear'), fired(b.arrays(), 'no_demand'))
        b = self.base()
        c1 = b.c[-1]
        i = b.bar(c1, c1 + 0.1, c1 - 0.25, c1 - 0.1, 0.5e6)
        self.assertIn((i, 'bull'), fired(b.arrays(), 'no_supply'))

    def test_stopping_volume_climaxes_upthrust_test(self):
        b = self.base()
        c1 = b.c[-1]
        i = b.bar(c1, c1 + 0.2, c1 - 1.5, c1 - 0.2, 2.5e6)
        self.assertIn((i, 'bull'), fired(b.arrays(), 'stopping_volume'))
        b = self.base()
        b.path(b.c[-1], [(b.c[-1] - 5, 10)], wick=0.25)
        c1 = b.c[-1]
        i = b.bar(c1, c1 + 0.1, c1 - 2.5, c1 - 2.0, 3e6)
        self.assert_both(b.arrays(), 'selling_climax', i, 'bull', 'buying_climax')
        b = self.base()
        c1, top = b.c[-1], max(b.h[-10:])
        i = b.bar(c1, top + 1.0, c1 - 0.3, c1 - 0.15, 2e6)
        self.assertIn((i, 'bear'), fired(b.arrays(), 'vsa_upthrust'))
        b = Bars()
        b.path(100, [(109, 30)], wick=0.25)
        c1 = b.c[-1]
        i = b.bar(c1, c1 + 0.05, c1 - 0.6, c1, 0.5e6)
        self.assertIn((i, 'bull'), fired(b.arrays(), 'vsa_test'))
        st = PA.state(*b.arrays(), bdays(len(b.c)))
        self.assertEqual(st['vsa']['label'], 'average spread, low volume, closes high, unchanged close')
        self.assertEqual(st['vsa']['events'], ['vsa_test'])


# ------------------------------------------------------------------ volume profile
class Profile(unittest.TestCase):
    def test_poc_and_value_area_by_hand(self):
        # bins of 0.2 over 100–110; the 104–106 bar puts 500 in bins 20–29, the wide bar 20 in every bin
        p = PA.volume_profile([110, 106], [100, 104], [1000, 5000])
        self.assertAlmostEqual(p['poc'], 104.1)
        self.assertAlmostEqual(float(p['volumes'].sum()), 6000)
        # value area from bin 20 upward: 8 bins hold 4160 < 4200 = 70%, the 9th takes it to 4680
        self.assertAlmostEqual(p['val'], 104.0)
        self.assertAlmostEqual(p['vah'], 105.8)
        self.assertEqual(len(p['edges']), PA.PROFILE_BINS + 1)
        z = PA.volume_profile([110, 105.05, 100.5], [100, 105.05, 100.5], [100, 900, 50])   # a zero-range day: one bin
        self.assertAlmostEqual(z['poc'], 105.1)
        self.assertIsNone(PA.volume_profile([1, 1], [1, 1], [0, 0]))

    def test_value_area_events(self):
        b = Bars()
        b.cycle([100, 100.5, 101, 100.5, 100, 99.5, 99, 99.5], 81, wick=0.1)
        self.assertEqual(b.c[-1], 100)
        k = b.bar(100, 103.2, 99.9, 103.0, 1e5)
        b.bar(103, 103.1, 99.9, 100.0, 1e5)
        arrs = b.arrays()
        self.assertIn((k, 'bull'), fired(arrs, 'vah_breakout'))
        self.assertIn((k + 1, 'bear'), fired(arrs, 'va_reentry'))
        self.assertIn((k, 'bear'), fired(flip(arrs), 'val_breakdown'))
        self.assertIn((k + 1, 'bull'), fired(flip(arrs), 'va_reentry'))
        st = PA.state(*arrs, bdays(len(b.c)))['profile']['60']
        self.assertEqual(st['position'], 'inside value')
        self.assertTrue(98.9 <= st['val'] < st['poc'] < st['vah'] <= 101.2, st)        # the cycle's lows are 98.9


# ------------------------------------------------------------------ levels and zones
class Levels(Mirror, unittest.TestCase):
    def test_support_bounce_and_break(self):
        b = Bars()
        piv = b.path(106, [(100, 6), (106, 6), (100, 6), (106, 6), (100, 6), (104, 4), (95, 9)])
        bounce = piv[5] + 1
        brk = piv[6] + 5                                # closes 104 → 103 … the first close at 99 (≤ 99.8 − 0.25 ATR)
        self.assertEqual(min(i for i, _ in fired(b.arrays(), 'support_bounce')), bounce)
        self.assertIn((bounce, 'bull'), fired(b.arrays(), 'support_bounce'))
        self.assertIn((bounce, 'bear'), fired(flip(b.arrays()), 'resistance_reject'))
        self.assertIn((brk, 'bear'), fired(b.arrays(), 'level_break'))
        st = PA.state(*[x[:brk] for x in b.arrays()], bdays(brk))
        sup = st['levels']['support']
        self.assertTrue(sup and abs(sup[0]['price'] - 99.8) < 1e-9 and sup[0]['touches'] >= 3, sup)

    def test_demand_and_supply_zones(self):
        b = Bars()
        b.cycle([99.6, 100.4], 20, wick=0.1)
        b.bar(100.1, 100.2, 99.85, 100.05)              # the base: two small bars
        b.bar(100.05, 100.2, 99.9, 100.1)
        for c in (101.5, 103.0, 104.5, 103.5, 102.5, 101.5, 100.5):
            b.close_to(c, wick=0.1)
        st = PA.state(*b.arrays(), bdays(len(b.c)))
        self.assertEqual([(z['bottom'], z['top']) for z in st['levels']['demand_zones']], [(99.85, 100.2)])
        i = b.bar(100.5, 100.6, 100.0, 100.4)
        self.assert_both(b.arrays(), 'demand_zone_test', i, 'bull', 'supply_zone_test')


# ------------------------------------------------------------------ Elliott waves
class Elliott(unittest.TestCase):
    def test_hard_rules(self):
        self.assertTrue(PA.elliott_impulse_ok([100, 110, 104, 120, 113, 125]))
        self.assertTrue(PA.elliott_impulse_ok([125, 113, 120, 104, 110, 100]))        # a falling impulse
        self.assertFalse(PA.elliott_impulse_ok([100, 110, 99, 120, 113, 125]))        # wave 2 below the start
        self.assertFalse(PA.elliott_impulse_ok([100, 110, 104, 112, 111, 123]))       # wave 3 the shortest
        self.assertFalse(PA.elliott_impulse_ok([100, 110, 104, 120, 109, 125]))       # wave 4 in wave 1's range
        self.assertTrue(PA.elliott_abc_ok(150, 100, 136, 144, 124))
        self.assertFalse(PA.elliott_abc_ok(150, 100, 136, 152, 124))                  # B beyond the impulse end

    def test_finds_a_constructed_impulse_and_abc(self):
        b = Bars()
        piv = b.path(106, [(100, 6), (120, 20), (108, 12), (140, 32), (126, 14), (150, 24), (136, 14), (144, 8),
                           (124, 20), (140, 16)])
        ev = [e for e in PA.detect(*b.arrays()) if e['rule'].startswith('elliott')]
        imp = [e for e in ev if e['rule'] == 'elliott_impulse']
        self.assertEqual(len(imp), 1)
        self.assertEqual(imp[0]['dir'], 'bear')                                        # after an up impulse: a correction
        self.assertEqual((imp[0]['info']['start'], imp[0]['info']['end']), (piv[1], piv[6]))
        self.assertTrue(piv[6] < imp[0]['i'] <= piv[6] + 8)
        abc = [e for e in ev if e['rule'] == 'elliott_abc']
        self.assertEqual([e['dir'] for e in abc], ['bull'])
        self.assertTrue(piv[9] < abc[0]['i'] <= piv[9] + 8)
        st = PA.state(*b.arrays(), bdays(len(b.c)))['elliott']
        self.assertTrue(st['label'].startswith('A-B-C correction complete'), st['label'])
        self.assertEqual([w['wave'] for w in st['waves']], ['0', '1', '2', '3', '4', '5', 'A', 'B', 'C'])
        self.assertAlmostEqual(st['waves'][5]['price'], 150.2)
        self.assertTrue(0.5 < st['ratios']['wave2_retrace'] < 0.7)

    def test_rejects_an_impulse_whose_wave3_is_shortest(self):
        imp = lambda w3_end: [e for e in PA.detect(*self.five(w3_end)) if e['rule'] == 'elliott_impulse']
        self.assertEqual(imp(128), [])                  # wave 3 = 18 < wave 1 = 20 and wave 5 = 23: not an impulse
        self.assertEqual(len(imp(136)), 1)              # the same swings with wave 3 = 26: found (the control)

    @staticmethod
    def five(w3_end):
        b = Bars()
        b.path(106, [(100, 6), (120, 20), (110, 10), (w3_end, 18), (w3_end - 6, 6), (w3_end - 6 + 23, 23),
                     (w3_end - 6, 20)])
        return b.arrays()


# ------------------------------------------------------------------ quantitative rules
class Quant(Mirror, unittest.TestCase):
    def test_donchian(self):
        b = Bars()
        b.cycle([100, 101], 60)
        i = b.close_to(102.0)
        self.assert_both(b.arrays(), 'donchian20', i, 'bull')
        self.assert_both(b.arrays(), 'donchian55', i, 'bull')
        self.assertEqual(fired(b.arrays(), 'donchian20'), {(i, 'bull')})

    def test_momentum_and_52_week_high(self):
        b = Bars()
        b.path(50, [(90, 400)])
        months = {i for i in range(len(b.c)) if i % PA.MONTH == PA.MONTH - 1 and i >= PA.YEAR}
        self.assertEqual(fired(b.arrays(), 'tsmom'), {(i, 'bull') for i in months})
        self.assertEqual(fired(b.arrays(), 'hi52'), {(i, 'bull') for i in months})
        self.assertEqual(fired(flip(b.arrays()), 'tsmom'), {(i, 'bear') for i in months})
        self.assertEqual(fired(flip(b.arrays()), 'hi52'), set())

    def test_short_term_reversal(self):
        o, h, l, c, v = random_walk(400, 5, 0.0, 0.01)
        b = Bars()
        for x in zip(o, h, l, c, v):
            b.bar(*x)
        for _ in range(21):
            b.close_to(b.c[-1] * 1.015, wick=0.1)
        ev = fired(b.arrays(), 'st_reversal')
        self.assertTrue(any(400 <= i < 421 and d == 'bear' for i, d in ev), ev)


# ------------------------------------------------------------------ random walks, no look-ahead, speed
class Robustness(unittest.TestCase):
    RARE = {'head_shoulders', 'inv_head_shoulders', 'double_top', 'double_bottom', 'cup_handle', 'triangle', 'bull_flag',
            'bear_flag', 'wedge_top', 'wedge_bottom', 'elliott_impulse', 'elliott_abc', 'sos', 'sow', 'selling_climax',
            'buying_climax', 'three_white_soldiers', 'three_black_crows'}

    def test_sane_rates_on_random_walks(self):
        cnt, bars = collections.Counter(), 0
        for seed in (11, 12, 13):
            o, h, l, c, v = random_walk(2500, seed)
            bars += len(c)
            cnt.update(e['rule'] for e in PA.detect(o, h, l, c, v))
        for rule in PA.EVENT_RULES:
            rate = cnt[rule] / bars
            self.assertLess(rate, 0.25, rule)
            if rule in self.RARE:
                self.assertLess(rate, 0.01, (rule, rate))

    def test_no_look_ahead(self):
        key = lambda e: (e['i'], e['rule'], e['dir'], json.dumps(e['info'], sort_keys=True))
        for seed in (21, 22):
            arrs = random_walk(1300, seed)
            full = PA.detect(*arrs)
            for k in (260, 517, 801, 1111, 1299):
                part = PA.detect(*[x[:k] for x in arrs])
                self.assertEqual(sorted(map(key, part)), sorted(key(e) for e in full if e['i'] < k), (seed, k))

    def test_benchmark(self):
        arrs = random_walk(2500, 31)
        best = min(self._time(arrs) for _ in range(3))
        n = len(PA.detect(*arrs))
        print(f'\n  price_action.detect: {best * 1000:.0f} ms for 2,500 bars, all {len(PA.EVENT_RULES)} event rules '
              f'({n} events)', file=sys.stderr)
        self.assertLess(best, 1.0)                     # target ≈ 0.3 s; generous for slow CI machines

    @staticmethod
    def _time(arrs):
        t = time.perf_counter()
        PA.detect(*arrs)
        return time.perf_counter() - t

    def test_short_and_degenerate_inputs(self):
        for n in (0, 1, 2, 5, 30):
            arrs = random_walk(max(n, 1), 4)
            arrs = [x[:n] for x in arrs]
            self.assertIsInstance(PA.detect(*arrs), list)
            if n:
                json.dumps(PA.state(*arrs, bdays(n)), allow_nan=False)
                json.dumps(PA.overlays(*arrs, bdays(n)), allow_nan=False)
        o, h, l, c, v = random_walk(300, 6)
        PA.detect(o, h, l, c, np.zeros(300))           # no volume at all
        ev = PA.detect(*random_walk(1500, 7))
        json.dumps(ev, allow_nan=False)                 # events (with their info) are JSON as they are
        self.assertTrue(all(set(e) == {'rule', 'i', 'dir', 'info'} and isinstance(e['i'], int) for e in ev))
        self.assertEqual([e['i'] for e in ev], sorted(e['i'] for e in ev))


# ------------------------------------------------------------------ the page's JSON
class Readings(unittest.TestCase):
    STATE_KEYS = {'date', 'close', 'atr', 'candlestick', 'brooks', 'structure', 'pattern', 'wyckoff', 'vsa', 'profile',
                  'levels', 'ict', 'elliott', 'quant', 'recent'}
    OVERLAY_KEYS = {'start', 'end', 'candles', 'swings', 'breaks', 'levels', 'zones', 'fvgs', 'order_blocks', 'donchian',
                    'profile', 'elliott', 'events'}

    def test_state_and_overlays(self):
        arrs = random_walk(2500, 41)
        dates = bdays(2500)
        st = PA.state(*arrs, dates)
        json.dumps(st, allow_nan=False)
        self.assertEqual(set(st), self.STATE_KEYS)
        self.assertEqual(st['date'], dates[-1])
        self.assertIn(st['brooks']['always_in'], ('long', 'short'))
        self.assertIn(st['brooks']['trend_or_range'], ('trend', 'trading range'))
        for k in ('swings', 'last_bos', 'last_choch', 'trend'):
            self.assertIn(k, st['structure'])
        for N in ('60', '250'):
            p = st['profile'][N]
            self.assertEqual(len(p['edges']), PA.PROFILE_BINS + 1)
            self.assertEqual(len(p['volumes']), PA.PROFILE_BINS)
            self.assertTrue(p['val'] <= p['poc'] <= p['vah'])
        self.assertEqual(set(st['levels']), {'support', 'resistance', 'demand_zones', 'supply_zones'})
        self.assertTrue(len(st['levels']['support']) <= 3 and len(st['levels']['resistance']) <= 3)
        self.assertEqual(set(st['ict']), {'premium_discount', 'fvgs', 'order_blocks', 'liquidity'})
        self.assertEqual(set(st['quant']), {'donchian20', 'donchian55', 'mom_12_1', 'tsmom', 'hi52_ratio', 'r21', 'r21_percentile'})
        self.assertIn('label', st['elliott'])
        self.assertIn('phase', st['wyckoff'])
        self.assertTrue(all(e['date'] in dates[-10:] for e in st['recent']))
        ov = PA.overlays(*arrs, dates, last=120)
        json.dumps(ov, allow_nan=False)
        self.assertEqual(set(ov), self.OVERLAY_KEYS)
        self.assertEqual(len(ov['candles']), 120)
        self.assertEqual(ov['start'], dates[-120])
        self.assertEqual(len(ov['donchian']['upper20']), 120)
        self.assertTrue(all(e['date'] >= dates[-120] for e in ov['events']))
        self.assertTrue(all(s['date'] >= dates[-120] for s in ov['swings']))


# ------------------------------------------------------------------ the pooled walk-forward test
class Statistics(unittest.TestCase):
    def test_forward_returns(self):
        fr = PA.forward_returns([100, 110, 121, 0, 133.1], horizons=(1, 2))
        self.assertAlmostEqual(fr[1][0], math.log(1.1))
        self.assertAlmostEqual(fr[2][0], math.log(1.21))
        self.assertTrue(math.isnan(fr[1][2]) and math.isnan(fr[1][4]) and math.isnan(fr[2][3]))

    def test_normal_cdf_and_bh(self):
        self.assertAlmostEqual(PA.normal_cdf(1.959964), 0.975, places=5)
        self.assertAlmostEqual(PA.p_two_sided(1.959964), 0.05, places=5)
        p = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216]
        sig = PA.benjamini_hochberg({k: x for k, x in enumerate(p)}, 0.10)
        self.assertEqual([k for k in range(10) if sig[k]], [0, 1, 2, 3, 4, 5])        # largest k: p(6) = 0.06 ≤ 6/10 × 0.1

    def test_clustered_t_by_hand(self):
        x = [1, 2, 3, 4, 2, 3, 4, 5, 0, 1, 2, 3]
        g = [1] * 4 + [2] * 4 + [3] * 4
        m, t = PA.clustered_t(x, g, min_clusters=2)
        self.assertAlmostEqual(m, 2.5)
        S = [sum(xi - 2.5 for xi, gi in zip(x, g) if gi == k) for k in (1, 2, 3)]   # 0, 4, −6
        se = math.sqrt(3 / 2 * sum(s * s for s in S)) / 12
        self.assertAlmostEqual(t, 2.5 / se)
        self.assertEqual(PA.clustered_t([1.0] * 5, [1] * 5), (None, None))
        self.assertEqual(PA.clustered_t(x, g), (2.5, None))                          # 3 months: too few for a t
        # one month of perfectly correlated events counts as one observation, not as many
        rng = np.random.default_rng(0)
        mo = np.repeat(np.arange(40), 25)
        shock = rng.normal(0, 1, 40)[mo] + rng.normal(0, 0.1, 1000)
        _, t_cl = PA.clustered_t(shock, mo)
        naive = shock.mean() / (shock.std(ddof=1) / math.sqrt(1000))
        self.assertLess(abs(t_cl), abs(naive) / 3)

    def synthetic_pool(self, n_tickers=40, n=2500, seed=7):
        rng = np.random.default_rng(seed)
        dates = bdays(n, '2014-01-02')
        pool = PA.Pool()
        for t in range(n_tickers):
            r = rng.normal(0.0003, 0.018, n)
            planted = np.nonzero(rng.random(n) < 0.015)[0]
            for i in planted:
                r[i + 1:i + 6] += 0.002                 # +1% (log) over the next 5 days
            ac = 40 * np.exp(np.cumsum(r))
            ev = [('planted', int(i), 'bull') for i in planted]
            for k in range(20):
                for i in np.nonzero(rng.random(n) < 0.004)[0]:
                    ev.append((f'noise{k}', int(i), 'bull' if rng.random() < 0.5 else 'bear'))
            pool.add(f'T{t}', dates, ac, ev)
        return pool

    def test_pool_finds_the_planted_rule_and_not_the_noise(self):
        pool = self.synthetic_pool()
        res = pool.result(split='2021-01-01', horizons=(5, 20, 60))
        P = res['planted']
        self.assertEqual(P['evidence'][5], 'strong')
        self.assertTrue(0.006 < P['horizons'][5]['oos']['mean'] < 0.014, P['horizons'][5])
        self.assertGreater(P['horizons'][5]['oos']['hit'], 0.55)
        self.assertEqual(P['n_is'] + P['n_oos'], P['n_events_total'])
        self.assertGreater(P['n_oos'], 300)
        noise = [res[f'noise{k}'] for k in range(20)]
        for h in (5, 20, 60):
            grades = collections.Counter(r['evidence'][h] for r in noise)
            self.assertGreaterEqual(grades['none'], 14, (h, grades))
            self.assertLessEqual(grades['strong'], 1, (h, grades))
        # ~100 out-of-sample events each with σ ≈ 4% per event: a noise rule's mean has a standard error near 0.4%
        self.assertLess(float(np.median([abs(r['horizons'][5]['oos']['mean']) for r in noise])), 0.005)
        base = pool.baseline_hit()
        self.assertTrue(0.45 < base[5]['oos'] < 0.6, base)
        self.assertEqual(PA.baseline_hit(pool), base)
        json.dumps(res, allow_nan=False)

    def test_pool_with_detected_events(self):
        pool = PA.Pool()
        dates = bdays(1500, '2016-01-04')
        for t in range(3):
            o, h, l, c, v = random_walk(1500, 50 + t)
            pool.add(f'R{t}', dates, c, PA.detect(o, h, l, c, v))
        res = pool.result()
        self.assertTrue(set(res) <= set(PA.EVENT_RULES) and len(res) > 30)
        for r in res.values():
            self.assertEqual(set(r['evidence']), set(PA.HORIZONS))
            self.assertTrue(all(g in ('strong', 'moderate', 'weak', 'none') for g in r['evidence'].values()))
            for h in PA.HORIZONS:
                self.assertEqual(set(r['horizons'][h]), {'is', 'oos'})
                self.assertEqual(set(r['horizons'][h]['oos']), {'n', 'months', 'mean', 'hit', 't', 'p'})
        json.dumps(res, allow_nan=False)


if __name__ == '__main__':
    unittest.main()
