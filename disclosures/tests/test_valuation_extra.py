"""valuation_extra.py: the classic and alternative lenses, the implied return and the market view."""
import math, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import valuation as M
import valuation_methods as V
import valuation_extra as X


def company(**k):
    F = {'ticker': 'TST', 'kind': 'industrial', 'sector': 'technology', 'price': 50.0, 'shares': 100e6, 'revenue': 1e9, 'oi': 2e8, 'ni': 1.5e8,
         'eps': 1.5, 'equity': 8e8, 'debt': 2e8, 'cash': 1e8, 'claims': 0.0, 'da': 5e7, 'capex': 6e7, 'tax_rate': 0.21, 'g0': 0.10,
         'goodwill': 0.0, 'intangibles': 0.0, 'ca': 6e8, 'liab': 4e8, 'ppe': 3e8, 'div': 3e7, 'years': [(0.1, 0.18), (0.1, 0.2), (0.1, 0.22)], 'src': {}}
    F.update(k)
    F['mcap'] = F['price'] * F['shares']
    return F


W = {'ke': 0.09, 'wacc': 0.085, 'rf': 0.045}


class Lenses(unittest.TestCase):
    def test_graham(self):
        F = company()
        g = X.graham_number(V, F)
        self.assertAlmostEqual(g['point'], math.sqrt(22.5 * 1.5 * 8.0))
        self.assertTrue(g['low'] < g['point'] < g['high'] and g['lens'])
        f = X.graham_formula(V, F, None, 5.5)
        self.assertAlmostEqual(f['point'], 1.5 * (8.5 + 2 * 10) * 4.4 / 5.5)
        self.assertIsNone(X.graham_number(V, company(eps=-1.0)))

    def test_ncav_negative_is_a_reason(self):
        self.assertAlmostEqual(X.ncav(V, company())['point'], 2.0)
        self.assertEqual(X.ncav(V, company(liab=9e8))['negative'], -3.0)

    def test_lynch(self):
        r = X.lynch_pegy(V, company(), None)
        y = 3e7 / 100e6 / 50.0
        self.assertAlmostEqual(r['point'], 1.5 * (10 + y * 100))
        self.assertIn('PEGY', r['note'])
        self.assertNotIn('PEGY', X.lynch_pegy(V, company(g0=-0.2, div=0.0), None)['note'])   # no growth, no yield: not defined

    def test_epv_and_split(self):
        F = company()
        it, split = X.epv(V, F, W, F['years'])
        mbar = 0.2
        gain = 1e9 - 1e9 / 1.1
        maint = 6e7 - 3e8 / 1e9 * gain
        ae = mbar * 1e9 * 0.79 + 5e7 - maint
        self.assertAlmostEqual(it['point'], (ae / 0.085 - 1e8) / 100e6, places=6)
        self.assertAlmostEqual(split['growth_share'], 1 - it['point'] / 50.0)

    def test_fcfe_h_model_and_option(self):
        F = company()
        base = {'growth': M.fade(0.10, M.TERM_G), 'capex': 0.06}
        f = X.fcfe_dcf(V, M, F, W, base)
        self.assertTrue(f and f['point'] > 0 and f['low'] < f['high'])
        h = X.h_model(V, M, F, W)
        d0, g_s = 0.3, min(0.10, 1.5e8 / 8e8 * (1 - 0.2))
        self.assertAlmostEqual(h['point'], d0 * ((1 + M.TERM_G) + 5 * (g_s - M.TERM_G)) / (0.09 - M.TERM_G))
        self.assertAlmostEqual(X.bs_call(100, 100, 1, 0.05, 0.2), 10.4506, places=3)       # the textbook value
        o = X.real_option(V, M, company(oi=-5e7), W, {'growth': [0.4, 0.3, 0.25, 0.2, 0.15]}, 0.15, 0.6, 4.0)
        self.assertTrue(o and o['point'] > 0)

    def test_multifactor_fit(self):
        rows = []
        for i in range(120):
            g, m, rev = (i % 10) / 20, 0.05 + (i % 7) / 30, 1e8 * (1 + i)
            evs = math.exp(0.2 + 1.5 * g + 0.8 * math.log(m) + 0.1 * math.log(rev / 1e9))
            rows.append({'kind': 'industrial', 'ev_sales': evs, 'revenue': rev, 'oi': m * rev, 'g0': g, 'sector': 'technology' if i % 2 else 'industrials'})
        fit = X.multifactor_fit(rows, ridge=1e-9)
        self.assertAlmostEqual(fit['b'][0], 1.5, places=3)
        self.assertAlmostEqual(fit['b'][1], 0.8, places=3)
        it = X.multifactor_item(V, company(), fit)
        self.assertTrue(it and it['low'] < it['point'] < it['high'])

    def test_implied_return(self):
        F = company()
        cons = {'analysts': {'periods': [{'period': '0y', 'eps': {'avg': 1.6, 'numberOfAnalysts': 5}}, {'period': '+1y', 'eps': {'avg': 1.9, 'numberOfAnalysts': 5}}]}}
        ir = X.implied_return(V, M, F, W, None, cons)
        names = [r['method'] for r in ir['rows']]
        self.assertIn("Easton MPEG (analysts' EPS)", names)
        a = 0.3 / 100
        self.assertAlmostEqual(next(r['r'] for r in ir['rows'] if r['method'].startswith('Easton')), a + math.sqrt(a * a + 0.3 / 50))
        self.assertAlmostEqual(ir['spread'], ir['median'] - 0.09)
        self.assertFalse(any(r['method'].startswith('Residual') for r in ir['rows']))   # book + residual income cannot reach 6× book
        ir = X.implied_return(V, M, company(price=12.0), W, None, None)
        ri = next(r for r in ir['rows'] if r['method'].startswith('Residual'))
        self.assertAlmostEqual(M.residual_income(8e8, 1.5e8 / 8e8, ri['r']) / 100e6, 12.0, places=3)

    def test_extra_appends_lenses_only(self):
        F = company()
        out = {'football': [], 'stage': {}, 'notes': []}
        X.extra(V, M, F, W, out, {'rates': {'aaa': 5.5, 'treasury_5y': 4.0}, 'vol': 0.4, 'regressions': {}}, None)
        names = {b['method'] for b in out['football']}
        self.assertTrue({'Graham number', 'Earnings power value (EPV)', 'H-model dividend discount'} <= names)
        self.assertTrue(all(b['lens'] for b in out['football']))
        self.assertIn('implied_return', out)


class Market(unittest.TestCase):
    def test_market_view(self):
        root = Path(tempfile.mkdtemp())
        (root / 'cache' / 'fred').mkdir(parents=True)
        (root / 'cache' / 'fred' / 'NCBEILQ027S.csv').write_text('DATE,V\n2020-01-01,30000000\n2026-04-01,80000000\n')
        (root / 'cache' / 'fred' / 'GDP.csv').write_text('DATE,V\n2020-01-01,20000\n2026-04-01,32000\n')
        (root / 'cache' / 'fred' / 'DFII10.csv').write_text('DATE,V\n2026-10-27,2.5\n')
        rows = [{'mcap': 1e12, 'ni': 4e10, 'icc': 0.08}, {'mcap': 1e11, 'ni': 6e9, 'icc': 0.10}]
        d = X.market_view(root, rows, {'treasury_10y': 4.5}, '2026-10-29')
        self.assertAlmostEqual(d['buffett']['ratio'], 2.5)
        self.assertEqual(d['buffett']['pct_rank'], 1.0)
        self.assertAlmostEqual(d['earnings_yield']['ey'], 4.6e10 / 1.1e12)
        self.assertAlmostEqual(d['implied_erp']['erp'], (1e12 * 0.08 + 1e11 * 0.10) / 1.1e12 - 0.045)


if __name__ == '__main__':
    unittest.main()
