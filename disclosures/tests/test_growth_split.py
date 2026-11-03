"""Each method against today's price and the present value of growth in it (valuation.growth_split): the gap to the
price, the value less the no-growth value, the five-year revenue growth at which the base DCF gives the method's value
(found again from a value the DCF itself produced), and the same for the price; and the fields on the Fair value page
and in the appendix from the test universe."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import valuation as V  # noqa: E402
import valuation_fixture as FX  # noqa: E402

BASE = {'rev0': 1e10, 'years': 5, 'growth': 0.05, 'margin': 0.2, 'tax': 0.21, 'da': 0.03, 'capex': 0.04, 'wc': 0.1, 'wacc': 0.09, 'g': 0.025,
        'terminal': 'roic', 'roic': 0.15, 'debt': 2e9, 'cash': 1e9, 'claims': 0.0, 'nonop': 0.0, 'shares': 1e9}


class Split(unittest.TestCase):
    def test_methods_and_price(self):
        v12 = V.value({**BASE, 'growth': 0.12})                   # the value the DCF gives at 12% a year
        out = {'football': [{'method': 'A', 'point': v12}, {'method': 'B', 'point': 10.0}, {'method': '52-week trading range', 'low': 1, 'high': 2},
                            {'method': 'C', 'point': None}],
               'pvgo': {'per_share': 15.0, 'basis': 'NOPAT ÷ WACC − net debt', 'rate': 0.09, 'earnings': 1.6e9},
               'reverse': {'status': 'ok', 'implied_growth': 0.07, 'history_growth': 0.05}, 'notes': []}
        V.growth_split(out, BASE, 25.0, 1e9)
        a, b, r, c = out['football']
        self.assertAlmostEqual(a['implied_growth'], 0.12, places=4)   # found again from its own value
        self.assertAlmostEqual(a['vs_price'], v12 / 25.0 - 1, places=12)
        self.assertAlmostEqual(a['pv_growth'], v12 - 15.0, places=12)
        self.assertAlmostEqual(a['pv_growth_share'], (v12 - 15.0) / v12, places=12)
        self.assertLess(b['pv_growth'], 0)                             # below the no-growth value: no growth priced in
        self.assertLess(b['implied_growth'], 0)                        # and shrinking revenue required
        self.assertNotIn('vs_price', r)                                # the trading range is no value
        self.assertNotIn('vs_price', c)
        sp = out['growth_split']
        self.assertEqual(sp['no_growth'], 15.0)
        self.assertAlmostEqual(sp['price_pv_growth'], 10.0)
        self.assertAlmostEqual(sp['price_growth_share'], 0.4)
        self.assertEqual(sp['price_growth'], 0.07)                     # the reverse DCF's own answer
        self.assertTrue(sp['dcf'])

    def test_without_dcf_or_earnings(self):
        out = {'football': [{'method': 'A', 'point': 30.0}], 'notes': []}
        V.growth_split(out, None, 20.0, 1e9)
        a = out['football'][0]
        self.assertAlmostEqual(a['vs_price'], 0.5)
        self.assertNotIn('pv_growth', a)
        self.assertNotIn('implied_growth', a)
        self.assertIsNone(out['growth_split']['no_growth'])
        self.assertFalse(out['growth_split']['dcf'])


class OnThePage(unittest.TestCase):
    def test_fields_on_the_page_and_in_the_appendix(self):
        with tempfile.TemporaryDirectory() as d:
            fx = FX.make(d)
            V.build(fx['root'], fx['prices'], fx['debt'], fx['cons'], today=FX.TODAY, verbose=False)
            doc = json.loads((Path(fx['root']) / 'public' / 'c' / '100000.json').read_text())
        sp = doc['growth_split']
        self.assertTrue(sp['no_growth'] and sp['price'] and 'price_growth' in sp)
        fb = {b['method']: b for b in doc['football']}
        dcf = fb['DCF — Monte Carlo 10th–90th percentile']
        self.assertAlmostEqual(dcf['vs_price'], dcf['point'] / doc['price'] - 1, places=4)   # rounded on publishing
        self.assertAlmostEqual(dcf['pv_growth'], dcf['point'] - sp['no_growth'], delta=0.01)
        self.assertIn('implied_growth', fb['P/E vs peers'])
        hi = max((b for b in doc['football'] if 'implied_growth' in b), key=lambda b: b['point'])
        lo = min((b for b in doc['football'] if 'implied_growth' in b), key=lambda b: b['point'])
        self.assertGreater(hi['implied_growth'], lo['implied_growth'])  # a higher value requires more growth
        apx = {m['method']: m for m in doc['appendix']['methods']}
        self.assertIn('vs_price', apx['P/E vs peers'])
        self.assertIn('pv_growth', apx['P/E vs peers'])


if __name__ == '__main__':
    unittest.main()
