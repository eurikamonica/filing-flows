"""The peer tiers (app/peer_tiers.py): the business-model map of revenue segments (overrides, generic names priced like
the company, rules), the matched tier's window ladder with the reasons a peer is left out, the growth/margin fit (a
known slope recovered, shrunk, its inputs held inside the group), the selected comps, the published peer list, and
the tiers on the Fair value page and in the ledger from the test universe."""
import json
import math
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import peer_tiers as PT  # noqa: E402
import valuation as V  # noqa: E402
import valuation_fixture as FX  # noqa: E402


def universe(n=40, seed=5):
    rng = random.Random(seed)
    R = {}
    for i in range(n):
        g, m = rng.uniform(-0.05, 0.4), rng.uniform(-0.1, 0.4)
        R[str(1000 + i)] = {'ticker': f'P{i}', 'sic': '7372' if i % 2 else '7371', 'stage': 'growth' if 0.08 <= g < 0.2 and m > 0 else 'other',
                            'revenue': 1e9 * rng.uniform(0.2, 20), 'growth': g, 'margin': m, 'mcap': 1e10, 'pe': None,
                            'ev_sales': math.exp(0.5 + 3.0 * g + 2.0 * m + rng.gauss(0, 0.05)), 'ev_ebitda': 20.0}
    R['own'] = {'ticker': 'OWN', 'sic': '7372', 'stage': 'growth', 'revenue': 5e9, 'growth': 0.12, 'margin': 0.2, 'ev_sales': 9.0}
    return R


class Map(unittest.TestCase):
    def test_segment_tags(self):
        M = PT.load_map()
        self.assertEqual(PT.segment_tag(M, 'AAPL', 'Services'), ('platform_services', 'override'))
        self.assertEqual(PT.segment_tag(M, 'ZZZ', 'Services'), (None, 'generic'))        # one word is no business model: priced like the company
        self.assertEqual(PT.segment_tag(M, 'HD', 'Net sales – services')[1], 'generic')
        self.assertEqual(PT.segment_tag(M, 'ZZZ', 'rev_more')[1], 'generic')
        self.assertEqual(PT.segment_tag(M, 'ZZZ', 'AWS')[0], 'cloud_infra')
        self.assertEqual(PT.segment_tag(M, 'ZZZ', 'Advertising services')[0], 'advertising')
        self.assertEqual(PT.segment_tag(M, 'ZZZ', 'Productivity And Server Licensing')[0], 'software')   # not hardware for "server"
        self.assertEqual(PT.segment_tag(M, 'ZZZ', 'AI Clouds, Industrial, & Enterprise')[0], 'semis')    # not software for "cloud"
        self.assertEqual(PT.segment_tag(M, 'ZZZ', 'Third-party seller services')[0], 'marketplace')
        self.assertEqual(PT.segment_tag(M, 'ZZZ', 'Subscription')[0], 'software')
        for t in M['tags'].values():                                                     # every tag can be priced
            self.assertTrue(t.get('groups') or len(t.get('comps') or []) >= 3, t['label'])
            for c in t.get('comps') or []:
                self.assertTrue(len(c) == 2 and c[1], c)                                  # every selected company has its reason
        for co in M['companies'].values():
            self.assertTrue(all(len(c) == 2 and c[1] for c in co['comps']))
        self.assertTrue(set(M['order']) <= set(M['tags']))
        for ov in M['overrides'].values():
            self.assertTrue(set(ov.values()) <= set(M['tags']))

    def test_missing_map(self):
        M = PT.load_map('/nonexistent/peer-map.json')
        self.assertEqual(PT.segment_tag(M, 'AAPL', 'Cloud'), (None, 'no rule'))


class Tiers(unittest.TestCase):
    def test_matched_window_ladder(self):
        R = universe()
        mt = PT.matched(R, 'own', 'ev_sales')
        self.assertIsNotNone(mt['window'])
        w = next(x for x in PT.WINDOWS if x['key'] == mt['window'])
        for c in mt['members']:
            r = R[c]
            self.assertEqual(r['sic'][:w['sic']], '7372'[:w['sic']])
            self.assertLessEqual(abs(r['growth'] - 0.12), w['growth'] + 1e-9)
            self.assertLessEqual(abs(r['margin'] - 0.2), w['margin'] + 1e-9)
            self.assertTrue(5e9 / w['size'] <= r['revenue'] <= 5e9 * w['size'])
        self.assertGreaterEqual(mt['n'], PT.MIN_PEERS)
        self.assertEqual(mt['tried'][-1][0], mt['window'])
        self.assertTrue(mt['p25'] <= mt['p50'] <= mt['p75'])
        out = next(c for c in R if c != 'own' and c not in mt['members'] and R[c]['sic'] == '7372')
        self.assertIsNotNone(PT.why_not(R, 'own', out, w))
        self.assertEqual(PT.matched({'own': R['own']}, 'own', 'ev_sales')['window'], None)   # nobody like it

    def test_adjusted_recovers_the_slopes(self):
        R = universe(n=80)
        ciks = [c for c in R if c != 'own']
        ad = PT.adjusted(R, 'own', 'ev_sales', ciks)
        true = math.exp(0.5 + 3.0 * 0.12 + 2.0 * 0.2)
        self.assertLess(abs(ad['p50'] / true - 1), 0.15)                # the line through the peers, at its own growth and margin
        self.assertGreater(ad['r2'], 0.8)
        self.assertLess(ad['per10']['growth'], math.exp(0.3) - 1)       # shrunk toward zero …
        self.assertGreater(ad['per10']['growth'], 0.15)                 # … not to it
        self.assertTrue(ad['p25'] < ad['p50'] < ad['p75'])
        self.assertFalse(ad['clamped'])
        R['own']['growth'] = 3.0                                         # far outside the group: held at its 95th percentile
        ad2 = PT.adjusted(R, 'own', 'ev_sales', ciks)
        self.assertTrue(ad2['clamped'])
        self.assertLess(ad2['used']['growth'], 0.5)
        self.assertIsNone(PT.adjusted(R, 'own', 'ev_sales', ciks[:5]))  # too few peers to fit

    def test_selected(self):
        R = universe()
        t2c = {r['ticker']: c for c, r in R.items()}
        M = {'tags': {}, 'order': [], 'overrides': {}, 'companies': {'OWN': {'comps': [['P1', 'a'], ['P3', 'b'], ['P5', 'c'], ['NOPE', 'd']]}}}
        se = PT.selected(M, R, t2c, 'own', 'OWN', 'ev_sales')
        self.assertEqual(se['n'], 3)
        self.assertEqual(se['missing'], ['NOPE'])
        self.assertAlmostEqual(se['p50'], sorted(R[t2c[t]]['ev_sales'] for t in ('P1', 'P3', 'P5'))[1], places=9)
        M['companies']['OWN']['comps'] = [['P1', 'a'], ['P3', 'b']]
        self.assertNotIn('p50', PT.selected(M, R, t2c, 'own', 'OWN', 'ev_sales'))     # two are too few
        self.assertIsNone(PT.selected(M, R, t2c, 'own', 'OTHER', 'ev_sales'))

    def test_peer_list(self):
        R = {'1': {'ticker': 'A', 'mcap': 2e9, 'pe': 20.0, 'ev_sales': 3.0}, '2': {'ticker': 'B', 'mcap': 5e9}}
        hist = {'pe': {'1': [(18.0, 0.4), (16.0, 1.4)]}, 'ev_sales': {'1': [(2.5, 0.4)]}}
        D = PT.rows_doc(R, hist, '2026-11-02')
        self.assertEqual(D['ages'], [0.4, 1.4])
        a = dict(zip(D['fields'], next(r for r in D['rows'] if r[1] == 'A')))
        self.assertEqual(a['pe_hist'], [18.0, 16.0])
        self.assertEqual(a['evs_hist'], [2.5, None])
        self.assertEqual(D['rows'][0][1], 'B')                         # largest first
        json.dumps(D, allow_nan=False)


class OnThePage(unittest.TestCase):
    def test_tiers_list_and_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            fx = FX.make(d)
            cfg = Path(d) / 'peer-map.json'
            M = json.loads(PT.CONFIG.read_text())
            M['companies'] = {'T000': {'comps': [['T003', 'chips'], ['T006', 'chips'], ['T009', 'chips'], ['T012', 'chips']]}}
            cfg.write_text(json.dumps(M))
            keep, PT.CONFIG = PT.CONFIG, cfg
            try:
                V.build(fx['root'], fx['prices'], fx['debt'], fx['cons'], today=FX.TODAY, verbose=False)
            finally:
                PT.CONFIG = keep
            pub = Path(fx['root']) / 'public'
            doc = json.loads((pub / 'c' / '100000.json').read_text())
            L = json.loads((pub / 'peers-list.json').read_text())
            snap = json.loads(next((Path(fx['root']) / 'cache' / 'ledger').glob('*.json')).read_text())
        P = doc['peers']['pe']
        self.assertTrue(P['members'] and all(isinstance(c, int) for c in P['members']))
        self.assertNotIn(100000, P['members'])                          # never its own peer
        self.assertIn(P['matched']['window'], ('tight', 'medium', 'wide'))
        self.assertEqual(P['selected']['n'], 4)
        fb = {b['method']: b for b in doc['football']}
        for m in ('P/E vs peers, matched', 'P/E vs peers, selected'):
            self.assertTrue(fb[m]['lens'])
        self.assertIn('Selected companies and why', {r[0] for m in doc['appendix']['methods'] if m['method'] == 'P/E vs peers, selected' for r in m['inputs']})
        self.assertIn('stage', doc['peer_base'])
        F = L['fields']
        self.assertEqual(F, PT.ROW_FIELDS)
        rows = {r[0]: dict(zip(F, r)) for r in L['rows']}
        self.assertEqual(len(rows), len(fx['companies']))
        self.assertTrue(rows[100000]['pe_hist'] and len(rows[100000]['pe_hist']) == len(L['ages']))
        self.assertEqual(snap['fields'], V.LEDGER_FIELDS)
        r0 = next(iter(snap['rows'].values()))
        self.assertEqual(len(r0), len(V.LEDGER_FIELDS))
        self.assertTrue(fin_any(snap['rows'], V.LEDGER_FIELDS.index('pe_selected')))


def fin_any(rows, i):
    return any(isinstance(r[i], (int, float)) for r in rows.values())


if __name__ == '__main__':
    unittest.main()
