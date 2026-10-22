"""Crowd Flow clocks (app/crowd_clocks.py; research spec v5 §6, §12, §17.2): comparable 13F pairs, the three Hype-map
views, truncation invariance end to end, and the descriptive transition audit."""
import datetime as dt
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import crowd_clocks as CC
import market as M
from holdings13f.core import compare, resolve

CUSIP = {'AAA': 'AAA000001', 'BBB': 'BBB000002', 'CCC': 'CCC000003'}
HOLIDAYS = {'2026-02-16'}                        # Presidents Day: the Feb 14 (Saturday) deadline rolls to Feb 17


def trading_days(a, b):
    d, out = dt.date.fromisoformat(a), []
    while d <= dt.date.fromisoformat(b):
        if d.weekday() < 5 and d.isoformat() not in HOLIDAYS:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def row(t, shares, px=10.0):
    return {'issuer': t + ' INC', 'class': 'COM', 'cusip': CUSIP[t], 'put_call': 'NONE', 'share_type': 'SH', 'shares': shares,
            'value_usd': shares * px, 'id': f'{CUSIP[t]}|COM|NONE|SH'}


_acc = [0]


def filing(period, filed, holdings, amendment='ORIGINAL', confidential=False):
    _acc[0] += 1
    return {'accession': f'0000-{_acc[0]:06d}', 'form': '13F-HR' if amendment == 'ORIGINAL' else '13F-HR/A', 'filed': filed,
            'accepted': filed + 'T16:00:00.000Z', 'period': period, 'amendment': amendment, 'confidential': confidential,
            'rows': [row(t, n) for t, n in holdings.items()]}


def manager(cik, filings, as_of=None):
    fs = [f for f in filings if as_of is None or f['filed'] <= as_of]
    snaps = resolve(fs, as_of)
    for i, s in enumerate(snaps):
        s['changes'] = compare(snaps[i - 1], s) if i else []
        s['baseline_period'] = snaps[i - 1]['period'] if i else None
    return {'cik': cik, 'name': f'Manager {cik}', 'filings': fs, 'snapshots': snaps}


Q4, Q1, Q2 = '2025-12-31', '2026-03-31', '2026-06-30'


def filings_by_manager():
    """Five managers. Deadline checkpoints: Q4 2025 → Feb 17 2026 (Feb 14 is a Saturday, Feb 16 a holiday), decision
    day Feb 18; Q1 2026 → May 15, decision day May 18; Q2 2026 → Aug 14, decision day Aug 17."""
    return {
        '1': [filing(Q4, '2026-02-01', {'AAA': 100, 'BBB': 50}), filing(Q1, '2026-04-20', {'AAA': 120, 'BBB': 50}),
              filing(Q2, '2026-07-20', {'AAA': 125, 'BBB': 40})],
        # files Q1 on May 14 with a cut in AAA, then restates it on Jun 20 (after the deadline checkpoint) as an increase
        '2': [filing(Q4, '2026-02-10', {'AAA': 100}), filing(Q1, '2026-05-14', {'AAA': 80}),
              filing(Q1, '2026-06-20', {'AAA': 110}, 'RESTATEMENT'), filing(Q2, '2026-08-01', {'AAA': 110})],
        # late Q1 filer: seen at 90 days, not at the deadline
        '3': [filing(Q4, '2026-02-12', {'AAA': 100, 'CCC': 10}), filing(Q1, '2026-06-10', {'AAA': 90, 'CCC': 10}),
              filing(Q2, '2026-08-10', {'AAA': 90, 'CCC': 12})],
        # confidential treatment for Q1: never a comparable pair for Q1 (Q4 → Q1)
        '4': [filing(Q4, '2026-02-02', {'AAA': 100}), filing(Q1, '2026-05-01', {'AAA': 105}, confidential=True),
              filing(Q2, '2026-07-30', {'AAA': 105})],
        # held BBB at Q4, never filed again: an unknown, never a sale
        '5': [filing(Q4, '2026-02-03', {'BBB': 70})],
    }


def write_world(root, filings, price_end, as_of=None, bump=0.0):
    root = Path(root)
    (root / 'cache' / 'holdings').mkdir(parents=True)
    (root / 'cache' / 'prices').mkdir(parents=True)
    for cik, fs in filings.items():
        with gzip.open(root / 'cache' / 'holdings' / f'{cik}.json.gz', 'wt') as f:
            json.dump(manager(cik, fs, as_of), f)
    days = trading_days('2025-06-02', price_end)
    for t, g in (('SPY', 1.0005), ('AAA', 1.002), ('BBB', 0.999), ('CCC', 1.001)):
        rows, px = [], 100.0
        for d in days:
            if d > '2026-09-01':
                px *= 1 + bump                          # a different recent path in another world
            rows.append([d, round(px, 6), 1000])
            px *= g
        with gzip.open(root / 'cache' / 'prices' / f'{t}.json.gz', 'wt') as f:
            json.dump({'ticker': t, 'source': 'test', 'fetched_at': '2026-10-01T00:00:00+00:00', 'rows': rows}, f)
    (root / 'cache' / 'prices' / 'cusips.json').write_text(json.dumps(
        {c: {'ticker': t, 'security_type': 'Common Stock'} for t, c in CUSIP.items()}))
    (root / 'cache' / 'prices' / 'sec-tickers.json').write_text(json.dumps({'rows': [{'ticker': t, 'title': t + ' Inc'} for t in CUSIP]}))


def build(root, today):
    """build_flows' 13F steps with a fixed clock (keep_after far back, so the test does not age)."""
    U = M.Universe(root)
    clock = CC.clock_from_prices(root, today=today)
    tally = CC.Tally({c for c in CUSIP.values()})
    raw, prices, coverage, managers = M.scan_13f(root, '2000-01-01', None, None, clock, tally)
    skips = {}
    summ = M.summarise(raw, prices, coverage, skips)
    cohort = CC.cohorts(raw, prices, summ, skips, U, tally)
    views = CC.build_states(cohort, coverage, tally, clock, CC.Prices(root))
    return views, tally, coverage, clock, summ, U


def origin(views, key, period):
    return next(o for o in views['pa'][key] if o['period'] == period)


class Clock(unittest.TestCase):
    def test_deadline_rolls_to_a_trading_day_and_decides_at_the_next_close(self):
        c = CC.Clock(trading_days('2025-12-01', '2026-09-30'), today='2026-09-30')
        self.assertEqual(c.anchors(Q4)[1], '2026-02-17')                 # Sat Feb 14 → (holiday Mon) → Tue Feb 17
        self.assertEqual(c.checkpoints(Q4)[1], '2026-02-18')
        self.assertEqual(c.checkpoints(Q1), ['2026-05-01', '2026-05-18', '2026-06-30'])   # 30d Apr 30 → May 1
        self.assertEqual(c.bucket(Q1, '2026-05-15'), 1)                    # filed on the deadline: known at its close
        self.assertEqual(c.bucket(Q1, '2026-05-18'), 2)                    # filed on the decision day: not yet
        self.assertEqual(c.checkpoints('2026-09-30'), [None, None, None])  # past the price file: not reached
        self.assertEqual(CC.prev_q(Q1), Q4)
        self.assertEqual(CC.next_q(Q4), Q1)

    def test_ranges(self):
        self.assertEqual(CC._ranges([None, (1, 1), (1, 1), (2, 1)]), [(0, 1, None), (1, 3, (1, 1)), (3, 4, (2, 1))])


class ComparablePairs(unittest.TestCase):
    def setUp(self):
        self.f = filings_by_manager()
        self.clock = CC.Clock(trading_days('2025-06-02', '2026-09-30'), today='2026-09-30')

    def test_an_amendment_never_changes_what_an_earlier_checkpoint_saw(self):
        pairs, held = CC.manager_pairs(manager('2', self.f['2']), self.clock)
        (lo, hi, ch), (lo2, hi2, ch2) = pairs[Q1]
        self.assertEqual((lo, hi), (1, 2))                                 # the original: at the deadline only
        aaa = next(r for r in ch if r['cusip'] == CUSIP['AAA'])
        self.assertEqual((aaa['prior_shares'], aaa['shares']), (100, 80))
        self.assertEqual((lo2, hi2, ch2), (2, CC.NB, None))                # the restatement: from 90 days on (final)
        self.assertEqual(held[Q1], [(0, CC.NB, None)])     # the restated Q1 holdings (Jun 20) are known at Q2's 30-day checkpoint

    def test_reasons(self):
        tally = CC.Tally()
        for cik, fs in self.f.items():
            CC.manager_pairs(manager(cik, fs), self.clock, tally)
        t = tally.q[Q1]
        self.assertEqual(t['ok'], [1, 2, 3, 3])          # M1 by 30d; + M2 (original) by the deadline; + M3 by 90 days
        self.assertEqual(t['confidential'], 1)
        self.assertEqual(t['not_filed'], 1)              # M5
        self.assertEqual(t['prior_reporters'], 5)
        self.assertEqual(tally.q[Q4]['first_in_feed'], 5)


class Views(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / 'full'
        write_world(cls.root, filings_by_manager(), '2026-09-30')
        cls.views, cls.tally, cls.coverage, cls.clock, cls.summ, cls.U = build(cls.root, '2026-09-30')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_quarter_aligned_uses_every_comparable_pair_and_the_same_quarter_price(self):
        qa = {o['period']: o for o in self.views['qa']}
        self.assertEqual(sorted(qa), [Q1, Q2])
        a = qa[Q1]['states']['AAA']
        # M1 +, M2 restated + (100 → 110), M3 − (100 → 90); M4 confidential: out
        self.assertEqual((a['add'], a['cut'], a['x'], a['prior']), (2, 1, 1, 4))
        self.assertEqual(a['matched'], 3)
        self.assertAlmostEqual(a['cov'], 0.75)
        self.assertAlmostEqual(a['y'], CC.Prices(self.root).change('AAA', Q4, Q1))
        self.assertEqual(qa[Q1]['meta']['price_window'], [Q4, Q1])

    def test_public_as_of_the_deadline_sees_only_what_was_filed(self):
        o = origin(self.views, CC.PRIMARY, Q1)
        self.assertEqual(o['meta']['decision_day'], '2026-05-18')
        a = o['states']['AAA']
        # M1 + and M2's original − (May 14); M3 filed Jun 10: not yet; M4 confidential
        self.assertEqual((a['add'], a['cut'], a['x']), (1, 1, 0))
        self.assertEqual(CC.quadrant(a['x'], a['y']), 'boundary')
        b = o['states']['BBB']
        self.assertEqual((b['x'], b['prior'], b['matched']), (0, 2, 1))   # M5 never filed: unknown, not a sale
        self.assertAlmostEqual(b['cov'], 0.5)
        late = origin(self.views, 2, Q1)['states']['AAA']                 # 90 days: M2 restated (+), M3 (−)
        self.assertEqual((late['add'], late['cut']), (2, 1))

    def test_missing_is_not_zero(self):
        o = origin(self.views, 0, Q1)                                      # 30 days: only M1
        self.assertEqual(o['states']['CCC']['n'], 0)                       # M3 has not filed: no comparable manager
        self.assertFalse(CC.eligible(o['states']['CCC'], 'all_eligible'))

    def test_forward_returns_from_the_decision_day(self):
        o = origin(self.views, CC.PRIMARY, Q1)
        px = CC.Prices(self.root)
        f = px.forward('AAA', '2026-05-18', 28, self.clock.latest())
        self.assertAlmostEqual(o['states']['AAA']['f4w'], f)
        self.assertAlmostEqual(o['states']['AAA']['e4w'], f - px.forward('SPY', '2026-05-18', 28, self.clock.latest()))
        q2 = origin(self.views, CC.PRIMARY, Q2)
        self.assertIsNone(q2['states']['AAA']['e12w'])                     # Aug 17 + 12 weeks is after the last close

    def test_audit_keeps_each_clock_apart(self):
        A = CC.audit(self.views, self.tally, self.coverage, 'now')
        self.assertEqual(A['status'], 'descriptive_only')
        self.assertIsNone(A['probabilities'])
        for key in ('quarter_aligned', 'public_knowledge_asof_30d', 'public_knowledge_asof_45d', 'public_knowledge_asof_90d'):
            self.assertIn(key, A['views'])
            for pop in ('all_eligible', 'covered'):
                m = A['views'][key][pop]
                self.assertEqual([r['from'] for r in m['rows']], list(CC.QUADS))
                for r in m['rows']:
                    if r['n']:
                        self.assertAlmostEqual(sum(c['p'] for c in r['cells']), 1, places=3)
        self.assertIn('post_publication', A['views']['public_knowledge_asof_45d']['covered'])
        self.assertNotIn('post_publication', A['views']['quarter_aligned']['covered'])
        cal = A['filing_calendar']['by_quarter'][Q1]
        self.assertEqual(cal['reports'], 4)                                # first filings only, not the restatement
        self.assertEqual(cal['share_by_day']['46'], 0.75)                  # M3 filed after the deadline

    def test_hype_history_rows_and_clock_labels(self):
        legacy = {**CC.legacy_series(self.summ, self.U, sorted(self.coverage)), '_clock': {'view_id': 'legacy_snapshot'}}
        signals = [{'ticker': t, 'f13': {'buyers': 1}} for t in ('AAA', 'BBB')]
        H = CC.hype_history(self.views, signals, legacy, self.U, 'now')
        self.assertEqual(H['schema_version'], 'hype_history.v2')
        self.assertEqual(set(H['views']), {'legacy_snapshot', 'quarter_aligned', 'public_knowledge_asof'})
        pa = H['views']['public_knowledge_asof']
        self.assertTrue(all(o['kind'] in ('45d', 'live') for o in pa['origins']))
        j = pa['periods'].index(Q1)
        self.assertEqual(H['rows']['AAA']['pa'][j][0], 0)
        jq = H['views']['quarter_aligned']['periods'].index(Q1)
        self.assertEqual(H['rows']['AAA']['qa'][jq][0], 1)
        self.assertEqual(H['rows']['AAA']['qa'][jq][9], 2)                 # the original count also takes M4's confidential report

    def test_boundaries_and_clipping(self):
        self.assertEqual(CC.quadrant(0, 0.3), 'boundary')
        self.assertEqual(CC.quadrant(3, 0), 'boundary')
        self.assertEqual(CC.quadrant(3, 2.5), 'BR')                        # a +250% move stays +250% in the data
        self.assertEqual(CC.quadrant(-1, -0.2), 'SF')
        self.assertIsNone(CC.quadrant(None, 0.1))


class TruncationInvariance(unittest.TestCase):
    """§1.1 / §17.1: rebuild the world as it stood before day T (filings filed before T, closes before T); every as-of
    state at a decision day before T must come out the same."""

    def test_as_of_states_do_not_move_when_later_data_arrive(self):
        T = '2026-06-01'
        with tempfile.TemporaryDirectory() as tmp:
            full, cut = Path(tmp) / 'full', Path(tmp) / 'cut'
            write_world(full, filings_by_manager(), '2026-09-30')
            write_world(cut, filings_by_manager(), '2026-05-29', as_of='2026-05-31')
            vf = build(full, '2026-09-30')[0]
            vc = build(cut, '2026-05-31')[0]
        checked = 0
        for key, seq in vc['pa'].items():
            if key == 'live':
                continue
            for o in seq:
                if o['meta']['decision_day'] >= T:
                    continue
                g = origin(vf, key, o['period'])
                self.assertEqual(o['meta']['decision_day'], g['meta']['decision_day'])
                for t, s in o['states'].items():
                    for k in ('x', 'add', 'cut', 'same', 'entry', 'exit', 'prior', 'matched', 'n', 'y'):
                        self.assertEqual(s[k], g['states'][t][k], (key, o['period'], t, k))
                    checked += 1
        self.assertGreaterEqual(checked, 6)

    def test_the_price_window_end_moves_the_legacy_snapshot_not_the_quarter_aligned_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / 'a', Path(tmp) / 'b'
            write_world(a, filings_by_manager(), '2026-09-30')
            write_world(b, filings_by_manager(), '2026-10-30', bump=0.01)
            va, vb = build(a, '2026-09-30')[0], build(b, '2026-10-30')[0]
            ra, rb = M.price_stats(a, 'AAA')['r3m'], M.price_stats(b, 'AAA')['r3m']
        self.assertNotAlmostEqual(ra, rb, places=3)                        # legacy Y: the trailing window moved
        qa = lambda v: {o['period']: o['states']['AAA']['y'] for o in v['qa']}
        self.assertEqual(qa(va), qa(vb))                                   # quarter-aligned Y: fixed by the quarter
        pa = lambda v: origin(v, CC.PRIMARY, Q1)['states']['AAA']['y']
        self.assertEqual(pa(va), pa(vb))                                   # as-of Y: fixed by the decision day


class Audit(unittest.TestCase):
    def test_wilson_and_matrix_counts(self):
        lo, hi = CC.wilson(5, 10)
        self.assertLess(lo, 0.5); self.assertGreater(hi, 0.5)
        self.assertEqual(CC.wilson(0, 0), (None, None))
        st = lambda x, y: {'x': x, 'y': y, 'n': 6, 'matched': 6, 'cov': 1.0, 'prior': 6}
        seq = [{'period': Q4, 'states': {'A': st(2, 0.1), 'B': st(-1, 0.1), 'C': st(0, 0.1)}},
               {'period': Q1, 'states': {'A': st(1, -0.1), 'B': st(-2, -0.3), 'C': st(1, 0.2)}}]
        m = CC.matrix(seq, 'covered')
        rows = {r['from']: r for r in m['rows']}
        self.assertEqual(rows['BR']['cells'][CC.QUADS.index('BF')]['n'], 1)
        self.assertEqual(rows['SR']['cells'][CC.QUADS.index('SF')]['n'], 1)
        self.assertEqual(rows['boundary']['cells'][CC.QUADS.index('BR')]['n'], 1)
        self.assertEqual((m['quarter_pairs'], m['stock_quarters']), (1, 3))


if __name__ == '__main__':
    unittest.main()
