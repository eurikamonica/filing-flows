"""crowding.py: holdings crowding from every 13F manager — holders, top-ten holders and value per stock and quarter, the
0–100 score, the quarters scored."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import crowding as CR  # noqa: E402


def pos(cusip, usd, put_call='NONE', share_type='SH'):
    return {'cusip': cusip, 'value_usd': usd, 'put_call': put_call, 'share_type': share_type, 'issuer': cusip + ' INC'}


def manager(i, periods, extra=(), filler=21):
    """A manager with `filler` small stock positions (so its top ten counts) plus `extra` positions, in each period."""
    snaps = []
    for p in periods:
        book = [pos(f'F{i:03d}{j:03d}X', 1000 + j) for j in range(filler)] + [pos(c, v) for c, v in extra]
        snaps.append({'period': p, 'complete': True, 'positions': book})
    return {'cik': str(i), 'snapshots': snaps}


class Crowding(unittest.TestCase):
    def test_scores_breadth_and_top_ten_share(self):
        is_fund = lambda c: c == 'ETF000001'
        g = CR.Gather(is_fund, keep_after='2024-12-31')
        P = ['2025-03-31', '2025-06-30']
        for i in range(30):                         # A: every manager, always a top-ten bet; B: 22 managers, tiny
            extra = [('AAA000001', 10 ** 7), ('ETF000001', 10 ** 9)]
            if i < 22:
                extra.append(('BBB000001', 10))
            if i < 25:
                extra.append(('CCC000001', 5 * 10 ** 6))   # C: 25 managers, a top-ten bet for all of them
            g.see(manager(i, P, extra))
        # options, other quantity types, an incomplete report and an old quarter are left out
        g.see({'snapshots': [{'period': '2025-06-30', 'complete': True, 'positions': [pos('AAA000001', 1, put_call='CALL'), pos('AAA000001', 1, share_type='PRN')]},
                             {'period': '2025-06-30', 'complete': False, 'positions': [pos('AAA000001', 1)]},
                             {'period': '2024-09-30', 'complete': True, 'positions': [pos('AAA000001', 1)]}]})
        self.assertEqual(g.tot['2025-06-30'][:2], [30, 30])
        self.assertNotIn('ETF000001', g.per['2025-06-30'])
        self.assertNotIn('2024-09-30', g.per)
        doc = CR.build(g, {'AAA000001': 'AAA', 'BBB000001': 'BBB', 'CCC000001': 'CCC'}, {'AAA': 'Triple A Inc'}.get, stamp='t')
        self.assertEqual(doc['periods'], P)
        self.assertEqual(doc['managers'], [30, 30])
        self.assertEqual(doc['fields'], ['holders', 'top10', 'usd_m', 'score', 'conviction'])
        a, b, c = doc['rows']['AAA'], doc['rows']['BBB'], doc['rows']['CCC']
        self.assertEqual((a[0][1], a[1][1], a[4][1]), (30, 30, 1.0))
        self.assertEqual((b[0][1], b[1][1], b[4][1]), (22, 0, 0.0))
        self.assertEqual((c[0][1], c[1][1]), (25, 25))
        self.assertEqual(a[2][1], 300.0)                                  # $ millions held
        self.assertGreater(a[3][1], c[3][1])                              # most held and always a top-ten bet
        self.assertGreater(c[3][1], b[3][1])
        # 100 × √(breadth × top share): A every manager, top ten for all; C 25 of 30 both ways; B never a top-ten bet
        self.assertEqual((a[3][1], c[3][1], b[3][1]), (100.0, round(100 * 25 / 30, 1), 0.0))
        self.assertEqual(doc['names'], {'AAA': 'Triple A Inc', 'BBB': '', 'CCC': ''})
        self.assertNotIn('F000000X', doc['rows'])                         # the filler lines have no ticker

    def test_small_books_make_no_top_ten_and_thin_stocks_are_not_scored(self):
        g = CR.Gather(lambda c: False, keep_after='2024-12-31')
        for i in range(12):
            g.see(manager(i, ['2025-03-31'], [('DDD000001', 10 ** 6)], filler=3))   # four positions each: too few to count
        doc = CR.build(g, {'DDD000001': 'DDD'})
        d = doc['rows']['DDD']
        self.assertEqual((d[0][0], d[1][0], d[4][0]), (12, 0, None))
        self.assertIsNone(d[3][0])                                        # held by fewer than MIN_HOLDERS: no score
        self.assertEqual(doc['managers_big'], [0])

    def test_quarters_most_managers_filed(self):
        g = CR.Gather(lambda c: False, keep_after='2020-12-31')
        g.tot.update({'2025-03-31': [100, 0, 0], '2025-06-30': [90, 0, 0], '2025-09-30': [20, 0, 0], '2024-12-31': [70, 0, 0]})
        self.assertEqual(CR.periods_of(g), ['2024-12-31', '2025-03-31', '2025-06-30'])
        self.assertEqual(CR.periods_of(g, {'2025-09-30': 95}), ['2024-12-31', '2025-03-31', '2025-06-30', '2025-09-30'])
        self.assertIsNone(CR.build(CR.Gather(lambda c: False), {}))

    def test_the_score_is_an_absolute_level(self):
        g = CR.Gather(lambda c: False, keep_after='2024-12-31')
        for i in range(40):                         # E: half the managers, a top-ten bet for a quarter of them
            g.see(manager(i, ['2025-03-31'], [('EEE000001', 10 ** 7 if i < 10 else 10)] if i < 20 else []))
        e = CR.build(g, {'EEE000001': 'EEE'})['rows']['EEE']
        self.assertEqual((e[0][0], e[1][0]), (20, 10))
        self.assertEqual(e[3][0], round(100 * (0.5 * 0.25) ** 0.5, 1))   # √(½ × ¼) — not a rank among other stocks
        self.assertEqual(e[4][0], 0.5)                                  # of its own holders, half have it in their top ten


if __name__ == '__main__':
    unittest.main()
