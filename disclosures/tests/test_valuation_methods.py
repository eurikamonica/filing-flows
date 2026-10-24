"""app/valuation_methods.py: the methods for pre-revenue and cash-burning companies, high growth, banks, insurers and
REITs (each checked against its formula by hand), and the appendix every company page carries."""
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import valuation as V  # noqa: E402
import valuation_methods as VM  # noqa: E402
import valuation_fixture as FX  # noqa: E402

W = {'ke': 0.10, 'wacc': 0.09, 'rf': 0.045, 'erp': 0.045, 'beta': 1.2, 'beta_raw': 1.3, 'kd': 0.06, 'kd_how': 'x', 'kd_after_tax': 0.047,
     'tax': 0.21, 'w_debt': 0.2, 'w_equity': 0.8, 'raw': 0.09}


class Formulas(unittest.TestCase):
    def test_justified_book_and_ddm_by_hand(self):
        F = {'shares': 10.0, 'equity': 100.0, 'goodwill': 0.0, 'intangibles': 0.0, 'ni': 12.0, 'src': {}}
        jb = VM.justified_book(F, W, 4.0, bank=False)
        # ROE 12%, payout 1/3 → g = 8% capped at 4% → P/B = (0.12 − 0.04) ÷ (0.10 − 0.04)
        self.assertAlmostEqual(jb['point'], 10 * (0.12 - 0.04) / (0.10 - 0.04), places=6)
        self.assertEqual(jb['method'], 'Justified P/B (Gordon growth)')
        self.assertTrue(jb['low'] < jb['point'] < jb['high'] and jb['calc']['steps'])
        bank = VM.justified_book({**F, 'goodwill': 20.0}, W, 4.0, bank=True)          # tangible book 80, ROTCE 15%
        self.assertEqual(bank['method'], 'Justified P/TBV (Gordon growth)')
        self.assertAlmostEqual(bank['point'], 8 * (0.15 - 0.04) / (0.10 - 0.04), places=6)
        dd = VM.ddm({**F, 'shares': 10.0}, W, 5.0, True, V)                           # REIT: g = terminal growth 2.5%
        self.assertAlmostEqual(dd['point'], 0.5 * 1.025 / (0.10 - 0.025), places=6)
        self.assertIsNone(VM.ddm(F, W, 0.0, False, V))                                  # no dividend, no model

    def test_survival_weighting(self):
        F = {'shares': 10.0, 'equity': 60.0, 'goodwill': 10.0, 'intangibles': 0.0, 'src': {}}
        going = {'method': 'Path-to-margin DCF, dilution-adjusted', 'point': 20.0, 'low': 15.0, 'high': 25.0}
        sv = VM.survival_weighted(F, going, 0.1, None)
        p = 1 - 0.9 ** 5
        self.assertAlmostEqual(sv['point'], (1 - p) * 20 + p * 50 * 0.8 / 10, places=6)
        rw = VM.survival_weighted(F, going, None, 2.0)                                 # from the runway: 0.5 − 2/10 = 30%
        self.assertAlmostEqual(rw['point'], 0.7 * 20 + 0.3 * 4.0, places=6)
        self.assertIsNone(VM.survival_weighted(F, going, None, None))

    def test_dilution_and_exit_multiple(self):
        F = {'price': 10.0, 'shares': 100.0, 'revenue': 1000.0, 'oi': -200.0, 'tax_rate': 0.21, 'cash': 50.0, 'debt': 0.0, 'src': {}}
        pb = {'rev0': 1000.0, 'years': 5, 'growth': V.fade(0.3, V.TERM_G), 'margin': [-0.2 + 0.35 * (k + 1) / 5 for k in range(5)], 'tax': 0.21,
              'da': 0.03, 'capex': 0.05, 'wc': 0.1, 'wacc': 0.10, 'g': 0.025, 'terminal': 'roic', 'roic': 0.15, 'debt': 0.0, 'cash': 50.0,
              'claims': 0.0, 'nonop': 0.0, 'shares': 100.0}
        v, burn, gap, new, r = VM.path_dilution(V, pb, F)
        self.assertGreater(burn, 50)
        self.assertAlmostEqual(gap, burn - 50)
        self.assertAlmostEqual(new, gap / 10.0)
        self.assertAlmostEqual(v, r['equity'] / (100 + new))
        self.assertLess(v, r['perShare'])                                              # dilution lowers the value per share
        item = VM.path_dilution_item(V, pb, F, 0.15, -0.2)
        self.assertTrue(item['low'] <= item['point'] <= item['high'])
        ex = VM.exit_multiple(V, pb, F, W, 0.15, {'p25': 15.0, 'p50': 20.0, 'p75': 28.0, 'n': 40, 'label': 'peers'}, new)
        rev5 = 1000.0
        for g in pb['growth']:
            rev5 *= 1 + g
        self.assertAlmostEqual(ex['point'], rev5 * 0.15 * 0.79 * 20 / 1.15 ** 5 / (100 + new), places=6)

    def test_rule40_fit_recovers_the_slope(self):
        rows = []
        for k in range(60):
            x = -0.2 + k * 0.01
            g, fcf_m = x * 0.6, x * 0.4
            rows.append({'kind': 'industrial', 'g0': g, 'revenue': 1e9, 'oi': (fcf_m * 1e9) / 0.79 if fcf_m > 0 else fcf_m * 1e9, 'tax_rate': 0.21,
                         'da': 0.0, 'capex': 0.0, 'ev_sales': math.exp(0.5 + 3.0 * x)})
        fit = VM.rule40_fit(rows)
        self.assertAlmostEqual(fit['b'], 3.0, places=3)
        self.assertAlmostEqual(fit['a'], 0.5, places=3)
        it = VM.rule40_item({'shares': 10.0, 'revenue': 100.0, 'g0': 0.3, 'oi': 10.0, 'tax_rate': 0.0, 'da': 0, 'capex': 0, 'debt': 0, 'cash': 0, 'src': {}}, fit)
        self.assertAlmostEqual(it['point'], math.exp(0.5 + 3.0 * 0.4) * 100 / 10, places=3)

    def test_net_cash_floor(self):
        it, ev = VM.net_cash_floor({'shares': 100.0, 'cash': 800.0, 'debt': 100.0, 'claims': 0.0, 'mcap': 1500.0, 'src': {}})
        self.assertAlmostEqual(it['point'], 7.0)
        self.assertAlmostEqual(ev, 800.0)


class Pages(unittest.TestCase):
    def test_every_company_page_has_the_appendix_and_the_right_methods(self):
        with tempfile.TemporaryDirectory() as d:
            fx = FX.make(d)
            st = V.build(fx['root'], fx['prices'], fx['debt'], fx['cons'], today=FX.TODAY, verbose=False)
            pub = Path(fx['root']) / 'public'
            self.assertTrue(st['rule40_fit'] and st['rule40_fit'] >= 30)
            docs = {c['cik']: json.loads((pub / 'c' / f"{c['cik']}.json").read_text()) for c in fx['companies']}
            for cik, doc in docs.items():
                A = doc['appendix']
                self.assertTrue(A['inputs'] and A['assumptions'] and A['methods'], cik)
                self.assertTrue(all('calc' not in b for b in doc['football']))           # the algebra lives in the appendix
                for m in A['methods']:
                    self.assertIn('formula', m)
                    if m.get('kind') == 'model':
                        self.assertTrue(m['formula'] and m['steps'], (cik, m['method']))
                self.assertNotIn('NaN', json.dumps(A))
            kind = {c['cik']: c for c in fx['companies']}
            meth = lambda cik: {b['method'] for b in docs[cik]['football']}
            banks = [c for c, k in kind.items() if k['sic'] == '6021']
            self.assertTrue(all({'Justified P/TBV (Gordon growth)', 'Dividend discount (Gordon)'} <= meth(c) for c in banks))
            ins = [c for c, k in kind.items() if k['sic'] == '6331']
            self.assertTrue(all('Justified P/B (Gordon growth)' in meth(c) for c in ins))
            reit = [c for c, k in kind.items() if k['sic'] == '6798']
            self.assertTrue(all('Dividend discount (Gordon)' in meth(c) for c in reit))
            pre = [c for c, k in kind.items() if k['sic'] == '7372' and k['name'] and docs[c].get('stage', {}).get('stage') == 'pre_profit']
            self.assertEqual(len(pre), 4)
            for c in pre:
                self.assertTrue({'Path-to-margin DCF, dilution-adjusted', 'Survival-weighted value', 'Exit-multiple (venture) method'} <= meth(c), meth(c))
                self.assertIn('DCF — Monte Carlo 10th–90th percentile', {x['method'] for x in docs[c]['appendix']['not_used']})
            prerev = [c for c, k in kind.items() if k['sic'] == '2836']
            self.assertEqual(docs[prerev[0]]['stage']['stage'], 'pre_revenue')
            self.assertIn('Net cash (floor)', meth(prerev[0]))
            self.assertTrue(docs[prerev[0]]['stage']['metrics'].get('market_implied_pipeline'))
            w = docs[banks[0]]['appendix']['wacc']
            self.assertTrue(w['formula'].startswith('WACC') and len(w['steps']) >= 4)


if __name__ == '__main__':
    unittest.main()
