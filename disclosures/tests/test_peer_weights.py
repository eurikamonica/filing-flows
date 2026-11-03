"""The weighted peer multiples (app/peer_weights.py): the weighted percentile (equal weights give the plain one), the 20%
cap, size weights from market value, revenue and trading value, recency within a peer, a giant and many small peers
by hand, the trading value from the price rows, and the weighted rows on the Fair value page from the test universe
(lenses beside the plain medians, with their algebra in the appendix)."""
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import peer_weights as PW  # noqa: E402
import valuation as V  # noqa: E402
import valuation_fixture as FX  # noqa: E402


class Pieces(unittest.TestCase):
    def test_weighted_quantile(self):
        rng = random.Random(3)
        for n in (2, 5, 9, 40):
            xs = [rng.uniform(1, 50) for _ in range(n)]
            for q in (0.0, 0.25, 0.5, 0.75, 1.0):
                self.assertAlmostEqual(PW.wquantile(xs, [1.0] * n, q), V.pctile(xs, q), places=9)   # equal weights: the plain percentile
        self.assertEqual(PW.wquantile([10, 20, 30], [1, 0, 0], 0.5), 10)        # zero weights drop out
        self.assertGreater(PW.wquantile([10, 20, 30], [0.1, 0.1, 10], 0.5), 20)  # the heavy one pulls the median toward it
        self.assertIsNone(PW.wquantile([], [], 0.5))

    def test_cap(self):
        w = PW.cap_weights({'a': 90, 'b': 5, 'c': 2, 'd': 1, 'e': 1, 'f': 1, 'g': 1, 'h': 1, 'i': 1, 'j': 1}, 0.2)
        self.assertAlmostEqual(sum(w.values()), 1.0, places=9)
        self.assertTrue(all(v <= 0.2 + 1e-9 for v in w.values()))
        self.assertAlmostEqual(w['a'], 0.2, places=9)
        self.assertGreater(w['b'], w['c'])                                      # the rest keep their order
        self.assertAlmostEqual(w['d'], w['e'], places=12)

    def test_size_weights_geometric_mean(self):
        info = {'big': {'mcap': 800, 'revenue': 400, 'dvol': 50}, 'mid': {'mcap': 100, 'revenue': 100, 'dvol': 40}, 'small': {'mcap': 10, 'revenue': 20, 'dvol': 1},
                'novol': {'mcap': 90, 'revenue': 80}}
        w, used = PW.size_weights(list(info), info, cap=1.0)
        self.assertEqual(used, ['mcap', 'revenue', 'dvol'])
        tm, tr, tv = 1000, 600, 91
        raw = {'big': (800 / tm * 400 / tr * 50 / tv) ** (1 / 3), 'mid': (100 / tm * 100 / tr * 40 / tv) ** (1 / 3), 'small': (10 / tm * 20 / tr * 1 / tv) ** (1 / 3),
               'novol': (90 / tm * 80 / tr) ** 0.5}                              # a measure it lacks is left out of its mean
        tot = sum(raw.values())
        for k in raw:
            self.assertAlmostEqual(w[k], raw[k] / tot, places=9)
        # a measure most peers lack is left out for every peer
        info2 = {c: {'mcap': v, 'revenue': v} for c, v in (('a', 3), ('b', 2), ('c', 1))}
        info2['a']['dvol'] = 5
        _, used2 = PW.size_weights(list(info2), info2)
        self.assertEqual(used2, ['mcap', 'revenue'])

    def test_a_giant_and_small_peers(self):
        # ten small peers at about 40x, three large at 15x, 18x and 20x: the plain median is 40x, the weighted one theirs
        cur = {f's{i}': 40.0 + i * 0.1 for i in range(10)}
        cur.update({'g1': 15.0, 'g2': 18.0, 'g3': 20.0})
        info = {c: {'mcap': 1.0, 'revenue': 1.0, 'dvol': 1.0} for c in cur}
        info['g1'] = {'mcap': 500.0, 'revenue': 300.0, 'dvol': 200.0}
        info['g2'] = {'mcap': 400.0, 'revenue': 300.0, 'dvol': 150.0}
        info['g3'] = {'mcap': 300.0, 'revenue': 200.0, 'dvol': 100.0}
        w = PW.weighted(list(cur), cur, {}, info, {'g1': 'BIG1', 'g2': 'BIG2', 'g3': 'BIG3'})
        self.assertAlmostEqual(w['by']['equal'], V.pctile(list(cur.values()), 0.5), places=9)
        self.assertGreater(w['by']['equal'], 39)
        self.assertLess(w['p50'], 30)                                            # the three giants (20% each at most) pull it far down …
        self.assertGreater(w['p50'], 15)                                         # … none of them alone
        self.assertGreater(w['p75'], 39)                                         # the small ones are still in the range
        self.assertEqual([t for t, _ in w['top'][:3]], ['BIG1', 'BIG2', 'BIG3'])
        self.assertAlmostEqual(w['top'][0][1], PW.CAP, places=4)
        self.assertLess(w['n_eff'], 8)                                           # 13 peers amount to about 7 equal ones
        self.assertFalse(w['timed'])
        self.assertIsNone(w['by']['time'])

    def test_recency_within_a_peer(self):
        # every peer traded at 10x years ago and 30x in the last year: the weighted median sits near the recent level
        cur = {f'c{i}': 30.0 for i in range(8)}
        hist = {c: [(30.0, 0.25), (30.0, 0.5), (30.0, 0.75), (10.0, 2.0), (10.0, 2.5), (10.0, 3.0), (10.0, 3.5), (10.0, 4.0)] for c in cur}
        info = {c: {'mcap': 1.0, 'revenue': 1.0} for c in cur}
        w = PW.weighted(list(cur), cur, hist, info)
        self.assertTrue(w['timed'])
        self.assertEqual(w['n_obs'], 8 * 9)
        self.assertEqual(w['p50'], 30.0)                                         # the four recent quarters and today outweigh five old ones
        recent = 1 + 0.5 ** 0.25 + 0.5 ** 0.5 + 0.5 ** 0.75
        old = sum(0.5 ** a for a in (2.0, 2.5, 3.0, 3.5, 4.0))
        self.assertGreater(recent / (recent + old), 0.75)
        self.assertEqual(w['by']['time'], 30.0)
        self.assertGreater(w['p25'], 10)

    def test_volumes_come_from_the_file_that_has_them(self):
        import gzip
        with tempfile.TemporaryDirectory() as d:
            hub, own = Path(d) / 'hub', Path(d) / 'own'
            hub.mkdir()
            own.mkdir()
            with gzip.open(hub / 'X.json.gz', 'wt') as f:
                json.dump({'rows': [['2026-10-27', 10, 100], ['2026-10-28', 11, 200]]}, f)
            with gzip.open(own / 'X.json.gz', 'wt') as f:                     # the top-up: later closes, no volumes
                json.dump({'rows': [['2026-10-28', 11], ['2026-10-30', 12]]}, f)
            px, rows = V.load_prices([hub, own], 'X', raw=True)
        self.assertEqual(px[-1], ('2026-10-30', 12.0))                          # the closes reaching the latest day
        self.assertEqual(rows[-1], ['2026-10-28', 11, 200])                     # the volumes from the hub's file

    def test_dollar_volume(self):
        rows = [[f'2026-01-{i:02d}', 10.0, 1000 * i] for i in range(1, 30)] + [['2026-02-01', 10.0]]
        self.assertEqual(PW.dollar_volume(rows, days=63), 10.0 * 1000 * 15)     # the median of close × volume
        self.assertIsNone(PW.dollar_volume([[f'd{i}', 10.0] for i in range(80)]))  # no volumes on file


class OnTheFairValuePage(unittest.TestCase):
    def test_weighted_rows_beside_the_plain_ones(self):
        with tempfile.TemporaryDirectory() as d:
            fx = FX.make(d)
            V.build(fx['root'], fx['prices'], fx['debt'], fx['cons'], today=FX.TODAY, verbose=False)
            pub = Path(fx['root']) / 'public'
            doc = json.loads((pub / 'c' / '100000.json').read_text())
            reit = next(c for c in fx['companies'] if str(c.get('sic')) == '6798')
            rdoc = json.loads((pub / 'c' / f"{reit['cik']}.json").read_text())
        fb = {b['method']: b for b in doc['football']}
        for m in ('P/E vs peers', 'EV/EBITDA vs peers', 'EV/Sales vs peers'):
            self.assertIn(m + ', weighted', fb)
            wb = fb[m + ', weighted']
            self.assertTrue(wb['lens'])                                          # shown beside, not in the stage-weighted value
            self.assertFalse(fb[m].get('lens'))
            self.assertTrue(wb['low'] <= wb['point'] <= wb['high'])
        pw = doc['peers']['pe']['weighted']
        self.assertEqual(pw['parts'], ['mcap', 'revenue', 'dvol'])              # the fixture's prices carry volumes
        self.assertTrue(pw['timed'] and pw['n_obs'] > pw['n'])
        self.assertAlmostEqual(pw['by']['equal'], doc['peers']['pe']['p50'], places=3)
        self.assertFalse(doc['peers']['ev_ebitda']['weighted']['timed'])       # no quarterly EBITDA history: today only
        apx = {m['method']: m for m in doc['appendix']['methods']}
        a = apx['P/E vs peers, weighted']
        self.assertIn('weighted peer median P/E', a['formula'])
        self.assertTrue(any('equal peers' in s for s in a['steps']))
        self.assertIn('Weighting the peers', a['fit'])
        self.assertTrue(any(r[0] == 'Largest weights' for r in a['inputs']))
        self.assertIn('P/FFO vs REIT peers, weighted', {b['method'] for b in rdoc['football']})
        self.assertIn('weighted', rdoc['sector_model']['peers'])


if __name__ == '__main__':
    unittest.main()
