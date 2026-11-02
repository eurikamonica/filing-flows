"""Fixed numbers vs the market today (app/assumption_check.py): the persistence of multiples recovered from a known
process, each market and data estimate from a small universe by hand, the DCF with each market number swapped in (the
WACC rebuilt from the market premium, terminal growth kept under the WACC, the tax rate only where the company's own was
not usable), and the published table and each company's swaps from the test universe."""
import json
import math
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import assumption_check as AC  # noqa: E402
import valuation as V  # noqa: E402
import valuation_fixture as FX  # noqa: E402

BASE = {'rev0': 1e10, 'years': 5, 'growth': [0.08, 0.07, 0.06, 0.05, 0.04], 'margin': 0.2, 'tax': 0.21, 'da': 0.03, 'capex': 0.04, 'wc': 0.1, 'wacc': 0.09,
        'g': 0.025, 'terminal': 'roic', 'roic': 0.15, 'debt': 2e9, 'cash': 1e9, 'claims': 0.0, 'nonop': 0.0, 'shares': 1e9}


class Pieces(unittest.TestCase):
    def test_persistence(self):
        rng = random.Random(1)
        hist = {}
        for c in range(200):
            x, xs = 0.0, []
            for q in range(40):
                x = 0.8 * x + rng.gauss(0, 0.1)
                xs.append((math.exp(1.0 + x), (40 - q) * 0.25))
            hist[c] = xs
        rho, n = AC.persistence(hist)
        self.assertLess(abs(rho - 0.8), 0.03)                       # with the short-series bias corrected
        self.assertEqual(n, 200 * 39)

    def test_estimates_by_hand(self):
        Fs, R, rows = {}, {}, []
        for i in range(40):
            c = str(i)
            Fs[c] = {'kind': 'industrial', 'revenue': 100.0, 'ca': 50.0, 'cash': 10.0, 'cl': 30.0 + i % 3, 'tax_rate': 0.18 + 0.001 * i, 'equity': 80.0, 'debt': 30.0,
                     'oi': 20.0, 'mcap': 300.0, 'goodwill': 0, 'intangibles': 0, 'pe': 10.0 + i, 'g0': 0.01 if i < 15 else 0.2}
            R[c] = {'stage': 'high_growth' if i < 20 else 'mature'}
            rows.append({'cik': i, 'icc': 0.10 if i < 20 else 0.08, 'distress_pd': 0.2 if i < 12 else 0.01})
        Fs['0']['_tax_default'] = True
        rates = {'treasury_10y': 4.2, 'aaa': 5.3}
        mkt = {'implied_erp': {'erp': 0.038, 'implied_return': 0.08, 'y10': 0.042, 'companies': 40}, 'earnings_yield': {'real10': 0.018, 'gap_real': 0.025}}
        filings = [{'end': '2026-06-30', 'filed': f'2026-08-{d:02d}'} for d in range(1, 31)] + [{'end': '2026-06-30', 'filed': '2026-09-28'}] * 5
        E = {e['key']: e for e in AC.market_estimates(V, Fs, R, rows, mkt, rates, {}, filings, {}, '2026-11-02',
                                                       betas=[(b, 0.5 * b + 0.5) for b in [0.1 * k for k in range(40)]], raw_wacc=[0.08] * 40)['entries']}
        self.assertEqual(E['erp']['market'], 0.038)
        self.assertAlmostEqual(E['erp']['gap'], 0.038 - V.ERP)
        self.assertEqual((E['erp']['low'], E['erp']['high']), (0.025, 0.038))  # the earnings yield less the real yield: the other read
        self.assertAlmostEqual(E['terminal_g']['market'], 0.042)
        self.assertAlmostEqual(E['terminal_g']['low'], 0.042 - 0.018)          # the breakeven: inflation only
        self.assertAlmostEqual(E['stage_premium']['market'], 0.02)             # 10% − 8%
        self.assertAlmostEqual(E['liq_haircut']['market'], 300 / 80)           # what the market pays for the assets of likely failures
        self.assertAlmostEqual(E['graham_pe']['market'], 17.0)                 # the median P/E of the 15 growing within ±2%
        self.assertAlmostEqual(E['wc_share']['market'], (50 - 10 - 31) / 100)
        self.assertEqual(E['tax_default']['n'], 39)                            # a defaulted rate is left out
        self.assertAlmostEqual(E['blume']['market'], 0.5)
        self.assertGreater(E['lag_days']['market'], 31)                       # the 90th percentile: after the late filers
        self.assertEqual(E['lgd']['market'], 0.60)
        self.assertEqual({e['kind'] for e in E.values()}, {'market', 'data', 'convention', 'definition', 'choice'})

    def test_swaps(self):
        W = {'beta': 1.2, 'rf': 0.042, 'erp': V.ERP, 'w_equity': 0.8, 'w_debt': 0.2, 'kd_after_tax': 0.04}
        est = {'entries': [{'key': 'erp', 'market': 0.03}, {'key': 'terminal_g', 'market': 0.085}, {'key': 'wc_share', 'market': 0.05},
                           {'key': 'roic_clamp', 'low': 0.05, 'high': 0.40}, {'key': 'tax_default', 'market': 0.19}]}
        S = AC.dcf_swaps(V, {'base': BASE, 'W': W, 'roic_now': 0.35, 'tax_default': False}, est)
        rows = {r['key']: r for r in S['rows']}
        self.assertAlmostEqual(S['value'], V.value(BASE))
        self.assertAlmostEqual(rows['erp']['used'], 0.8 * (0.042 + 1.2 * 0.03) + 0.2 * 0.04)   # the WACC rebuilt from the market premium
        self.assertGreater(rows['erp']['value'], S['value'])                   # a lower premium, a higher value
        self.assertAlmostEqual(rows['terminal_g']['value'], V.value({**BASE, 'g': 0.08}), places=6)   # kept 1 point under the WACC
        self.assertAlmostEqual(rows['roic_clamp']['used'], 0.35)               # inside the wider band: its own ROIC
        self.assertNotIn('tax_default', rows)                                  # its own tax rate was usable
        self.assertTrue(math.isfinite(S['all']))
        S2 = AC.dcf_swaps(V, {'base': BASE, 'W': W, 'roic_now': 0.35, 'tax_default': True}, est)
        self.assertIn('tax_default', {r['key'] for r in S2['rows']})
        self.assertIsNone(AC.dcf_swaps(V, None, est))


class OnThePage(unittest.TestCase):
    def test_table_and_swaps(self):
        with tempfile.TemporaryDirectory() as d:
            fx = FX.make(d)
            V.build(fx['root'], fx['prices'], fx['debt'], fx['cons'], today=FX.TODAY, verbose=False)
            pub = Path(fx['root']) / 'public'
            E = json.loads((pub / 'assumptions.json').read_text())
            doc = json.loads((pub / 'c' / '100000.json').read_text())
        keys = {e['key'] for e in E['entries']}
        self.assertTrue({'erp', 'terminal_g', 'g_cap', 'wc_share', 'tax_default', 'roic_clamp', 'blume', 'half_life', 'lgd', 'years'} <= keys)
        erp = next(e for e in E['entries'] if e['key'] == 'erp')
        self.assertEqual(erp['fixed'], V.ERP)
        S = doc['assumption_swaps']
        self.assertAlmostEqual(S['value'], doc['dcf']['value'], places=2)
        self.assertIn('erp', {r['key'] for r in S['rows']})


if __name__ == '__main__':
    unittest.main()
