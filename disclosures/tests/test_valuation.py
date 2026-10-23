"""app/valuation.py: the DCF and its reverse, Monte Carlo, beta and WACC, residual income, the regressions, valuation
bands, sum of the parts, the distress blend, the frames panel and the full build with its ledger."""
import datetime as dt
import json
import math
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import valuation as V  # noqa: E402
import valuation_fixture as FX  # noqa: E402

BASE = {'rev0': 1000.0, 'years': 5, 'growth': 0.08, 'margin': 0.2, 'tax': 0.21, 'da': 0.03, 'capex': 0.04, 'wc': 0.1, 'wacc': 0.09, 'g': 0.025,
        'terminal': 'roic', 'roic': 0.15, 'debt': 200.0, 'cash': 100.0, 'claims': 0.0, 'nonop': 0.0, 'shares': 100.0}


class Model(unittest.TestCase):
    def test_dcf_and_reverse(self):
        r = V.dcf(BASE)
        self.assertTrue(r['ok'])
        self.assertAlmostEqual(r['equity'], r['ev'] - 200 + 100)
        self.assertAlmostEqual(r['perShare'], r['equity'] / 100)
        self.assertGreater(V.value({**BASE, 'growth': 0.12}), r['perShare'])          # more growth, more value
        self.assertGreater(r['perShare'], V.value({**BASE, 'wacc': 0.11}))            # a higher cost of capital, less
        s = V.solve(BASE, 'growth', r['perShare'], -0.3, 0.6)
        self.assertEqual(s['status'], 'ok')
        self.assertAlmostEqual(s['value'], 0.08, places=5)
        self.assertEqual(V.solve(BASE, 'growth', 1e9, -0.3, 0.6)['status'], 'none')
        self.assertFalse(V.dcf({**BASE, 'wacc': 0.02})['ok'])                         # WACC below terminal growth
        path = V.dcf({**BASE, 'growth': V.fade(0.2, 0.025), 'capex': [0.1, 0.09, 0.08, 0.07, 0.065]})
        self.assertTrue(path['ok'])
        self.assertEqual([round(x, 4) for x in V.fade(0.2, 0.025)], [0.2, 0.165, 0.13, 0.095, 0.06])

    def test_monte_carlo(self):
        price = V.value(BASE)
        mc = V.monte_carlo(BASE, price, 0.05, 0.02, n=600, seed=3)
        self.assertLess(mc['p10'], mc['p50'])
        self.assertLess(mc['p50'], mc['p90'])
        self.assertTrue(0.25 < mc['p_above'] < 0.75)                                  # the base value sits near the middle
        self.assertEqual(sum(mc['hist']['counts']) <= 600, True)
        self.assertEqual(V.monte_carlo(BASE, price, 0.05, 0.02, n=600, seed=3)['p50'], mc['p50'])   # seeded

    def test_beta_and_wacc(self):
        rng = random.Random(1)
        days = FX.business_days(dt.date(2024, 1, 1), dt.date(2026, 10, 16))
        m, s, cm, cs = [], [], 100.0, 100.0
        for d in days:
            r = rng.gauss(0.0003, 0.01)
            cm *= math.exp(r)
            cs *= math.exp(1.5 * r + rng.gauss(0, 0.004))
            m.append((d, cm))
            s.append((d, cs))
        b = V.beta(s, m)
        self.assertAlmostEqual(b[0], 1.5, delta=0.15)
        self.assertAlmostEqual(b[1], 0.67 * b[0] + 0.33)
        self.assertIsNone(V.beta(s[:100], m[:100]))                                   # fewer than 52 weeks
        F = {'mcap': 900.0, 'debt': 100.0, 'tax_rate': 0.2, 'interest': 6.0}
        W = V.wacc_of(F, {'treasury_10y': 4.0, 'treasury_5y': 3.8}, None, b)
        self.assertAlmostEqual(W['ke'], 0.04 + b[1] * V.ERP)
        self.assertAlmostEqual(W['kd'], 0.06)                                         # interest ÷ debt
        self.assertAlmostEqual(W['raw'], 0.9 * W['ke'] + 0.1 * 0.06 * 0.8)
        rec = {'analysis': {'implied': {'calibrated_5y_bps': 150}}}
        self.assertAlmostEqual(V.cost_of_debt(rec, {'treasury_5y': 3.8}, 6, 100)[0], 0.053)
        self.assertEqual(V.as_pct(0.0425), 4.25)
        self.assertEqual(V.as_pct(4.25), 4.25)

    def test_residual_income_regression_distress(self):
        self.assertAlmostEqual(V.residual_income(100, 0.1, 0.1), 100)                  # earning exactly the cost of equity: book value
        self.assertGreater(V.residual_income(100, 0.2, 0.1), 100)
        f = V.ols([0.05, 0.1, 0.15, 0.2], [0.8, 1.2, 1.6, 2.0])
        self.assertAlmostEqual(f['b'], 8.0)
        self.assertAlmostEqual(f['r2'], 1.0)
        lo = V.distress(1e-4, 50, 5.0, 90)
        hi = V.distress(0.08, 900, 0.8, 10)
        self.assertLess(lo['pd'], 0.005)
        self.assertGreater(hi['pd'], 0.05)
        self.assertFalse(hi['calibrated'])
        self.assertIsNone(V.distress(0.01))                                             # one part is not a blend
        self.assertAlmostEqual(V.sigmoid(0.622 - 2.143 * 1.1), 0.15, places=2)        # the Altman mapping's anchor

    def test_bands_and_sotp(self):
        periods = V.calendar_quarters(18, FX.TODAY)
        days = FX.business_days(dt.date(2022, 6, 1), dt.date(2026, 10, 16))
        daily = [(d, 50 + 30 * (i / len(days))) for i, d in enumerate(days)]
        eps = [1.0] * len(periods)
        rev = [1e9] * len(periods)
        b = V.bands(daily, periods, eps, rev, 1e8, 0)
        self.assertAlmostEqual(b['pe']['current'], daily[-1][1] / 4, places=1)        # P/E on four quarters of $1
        self.assertGreater(b['pe']['pct'], 0.95)                                        # a rising price: today is at the top
        self.assertAlmostEqual(b['evs']['current'], daily[-1][1] * 1e8 / 4e9, places=2)
        slim = {'nodes': [{'id': 'L:a', 'name': 'Cloud services'}, {'id': 'L:b', 'name': 'Devices'}],
                'links': [{'s': 'L:a', 't': 'revenue', 'v': 300.0}, {'s': 'L:b', 't': 'revenue', 'v': 700.0}]}
        segs = V.segments_of(slim)
        self.assertEqual(segs, [('Cloud services', 300.0), ('Devices', 700.0)])
        buckets = {'sic737': [(i, 6.0) for i in range(8)], 'sic357': [(i + 10, 1.5) for i in range(8)]}
        so = V.sotp(segs, buckets, {'cik': 'x', 'sic': '3571'}, 100.0, 0.0)
        self.assertAlmostEqual(so['point'], (1200 * 6 + 2800 * 1.5) / 100)
        self.assertIsNone(V.sotp(segs[:1], buckets, {'cik': 'x', 'sic': '3571'}, 100.0, 0.0))


class Build(unittest.TestCase):
    def test_build_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            fx = FX.make(d)
            st = V.build(fx['root'], fx['prices'], fx['debt'], fx['cons'], today=FX.TODAY, verbose=False)
            self.assertEqual(st['companies'], len(fx['companies']))
            self.assertGreaterEqual(st['with_dcf'], 25)
            self.assertGreaterEqual(st['banks_fit'], 12)
            pub = Path(fx['root']) / 'public'
            ix = json.loads((pub / 'index.json').read_text())
            rows = [dict(zip(ix['fields'], r)) for r in ix['rows']]
            bank = json.loads((pub / 'banks.json').read_text())['fit']
            self.assertGreater(bank['b'], 4)                                            # P/TBV rises with ROTCE (8 in the fixture)
            ind = next(r for r in rows if r['kind'] == 'industrial' and r['cik'] == 100000)
            self.assertTrue(0.05 <= ind['wacc'] <= 0.16 and ind['dcf_value'] > 0 and 0 <= ind['mc_p_above'] <= 1)
            doc = json.loads((pub / 'c' / '100000.json').read_text())
            methods = {b['method'] for b in doc['football']}
            self.assertTrue({'DCF — Monte Carlo 10th–90th percentile', 'P/E vs peers', "Analysts' price targets", 'Polymarket implied price',
                             'Our model (Rotation forecast)', '52-week trading range'} <= methods, methods)
            self.assertEqual(doc['wacc']['kd_how'][:16], '5-year Treasury ')                # the bond-calibrated spread from the debt module
            self.assertTrue(doc['credit']['distress'] and len(doc['credit']['distress']['parts']) == 4)
            self.assertEqual(doc['reverse']['status'], 'ok')
            self.assertIn('pe', doc['bands'])
            b0 = next(r for r in rows if r['kind'] == 'bank')
            bdoc = json.loads((pub / 'c' / f"{b0['cik']}.json").read_text())
            self.assertEqual(bdoc['sector_model']['model'], 'P/TBV vs ROTCE (banks)')
            self.assertNotIn('dcf', bdoc)                                                  # no FCFF model for a bank
            ins = next(r for r in rows if r['kind'] == 'insurer')
            self.assertAlmostEqual(ins['combined_ratio'], 0.93, places=2)
            reit = next(r for r in rows if r['kind'] == 'reit')
            self.assertTrue(reit['p_ffo'] and reit['p_ffo'] > 5)
            led = json.loads((pub / 'ledger.json').read_text())
            self.assertEqual(led['snapshots'], ['2026-10'])
            # a second build in the same month keeps the frozen snapshot; three months on it is scored
            frozen = (Path(fx['root']) / 'cache' / 'ledger' / '2026-10.json').read_text()
            V.build(fx['root'], fx['prices'], fx['debt'], fx['cons'], today=FX.TODAY, verbose=False)
            self.assertEqual((Path(fx['root']) / 'cache' / 'ledger' / '2026-10.json').read_text(), frozen)
            L = json.loads(frozen)
            L['frozen_at'] = '2026-01-05T00:00:00+00:00'
            (Path(fx['root']) / 'cache' / 'ledger' / '2026-01.json').write_text(json.dumps({**L, 'month': '2026-01'}))
            led = V.ledger_update(fx['root'], rows, fx['prices'], FX.TODAY)
            self.assertTrue(any(s['month'] == '2026-01' and s['horizon_months'] == 6 and s['n'] >= 10 for s in led['scores']))



class Shares(unittest.TestCase):
    """The share count every per-share value divides by (McDonald's DCF read $519,571,000 a share on 711.1 shares)."""

    def test_unit_slips_and_wrong_classes(self):
        cases = {
            'MCD': ([('main site (diluted)', 711.1), ('main site (outstanding)', 707641531)], 246.52, 27.7e9, 707641531),
            'NTNX': ([('main site (diluted)', 287481), ('debt module (cover page)', 270570179)], 66.94, 2.5e9, 270570179),
            'WAT': ([('main site (diluted)', 98204000000), ('main site (outstanding)', 98248111)], 457.47, 3.0e9, 98248111),
            'PLNT': ([('debt module (cover page)', 100), ('analysts (Yahoo)', 84e6)], 50.92, 1.2e9, 84e6),   # Class B only
            'FOUR': ([('main site (diluted)', 1333686), ('main site (outstanding)', 78960120)], 39.43, 3.5e9, 78960120),
            'LEVI': ([('main site (diluted)', 390620582), ('main site (outstanding)', 37602843)], 20.44, 6.4e9, 390620582),
            'AVTX': ([('frames, diluted weighted average', 43602044)], 13.65, 59000, 43602044),   # no revenue to judge by
        }
        for t, (cands, price, rev, want) in cases.items():
            self.assertEqual(V.settle_shares(cands, price, rev)[0], want, t)
        v, src, note = V.settle_shares([('main site (diluted)', 711.1)], 246.52, 27.7e9, implied=711.4e6)
        self.assertEqual((round(v), src), (711100000, 'main site (diluted)'))            # a unit slip read back, with net income ÷ EPS
        self.assertIn('millions', note)
        v, src, note = V.settle_shares([('debt module (cover page)', 100)], 50.92, 1.2e9)
        self.assertIsNone(v)                                                          # nothing plausible: no per-share values
        self.assertIn('left out', note)

    def test_implied_shares(self):
        self.assertEqual(V.implied_shares([1e9, 2e9, None, 3e9], [1.0, 2.0, 1.5, 0.01]), 1e9)    # a near-zero EPS is skipped
        self.assertIsNone(V.implied_shares([1e9], [None]))

    def test_inputs_pick_a_fresh_count_and_the_cover_after_a_split(self):
        meta = {'ticker': 'X', 'name': 'X', 'sic': 3674}
        slim = {'val': {'end': '2026-06-30', 'revenue': 12e9, 'oi': 5e9, 'diluted': 131750000, 'diluted_end': '2026-03-31',
                        'outstanding': 1306546783, 'outstanding_at': '2026-08-03'}}
        F = V.company_inputs(1, meta, {}, slim, {}, {}, 161.74, [])
        self.assertEqual((F['shares'], F['src']['shares']), (1306546783, 'main site (outstanding, after a split or issue)'))
        slim = {'val': {'end': '2026-07-03', 'revenue': 7.7e9, 'oi': 1e9, 'diluted': 9413000, 'diluted_end': '2019-09-29',
                        'outstanding': 7141447, 'outstanding_at': '2016-03-04'}}
        F = V.company_inputs(1, meta, {}, slim, {'snapshot': {'shares': 7141447}}, {'analysts': {'shares': 66564294}}, 196.49, [])
        self.assertEqual((F['shares'], F['src']['shares']), (66564294, 'analysts (Yahoo)'))
        F = V.company_inputs(1, meta, {}, slim, {'snapshot': {'shares': 7141447}}, {}, 196.49, [])
        self.assertIsNone(F['shares'])
        self.assertIn('years old', F['shares_note'])

if __name__ == '__main__':
    unittest.main()


class TopUpPrices(unittest.TestCase):
    """Companies the hub does not price (CoreWeave, Nebius: no 13F manager the hub follows holds them) get daily closes
    from Yahoo into the branch's own cache, and the build reads them after the hub's."""

    def test_missing_tickers_are_fetched_and_read(self):
        import io
        import urllib.error
        import urllib.request
        today = dt.date(2026, 10, 23)
        with tempfile.TemporaryDirectory() as tmp:
            root, hub = Path(tmp) / 'val', Path(tmp) / 'hub'
            V.write_json(hub / 'AAPL.json.gz', {'rows': [['2026-10-22', 250.0]]}, gz=True)
            V.write_json(root / 'site' / 'index.json', {'companies': [
                {'cik': 320193, 'ticker': 'AAPL', 'revenue': 9e10}, {'cik': 1769628, 'ticker': 'CRWV', 'revenue': 2.5e9},
                {'cik': 1513845, 'ticker': 'NBIS', 'revenue': 5.8e8}, {'cik': 1, 'ticker': 'ZZZZ', 'revenue': 1e6}]})
            asked = []
            day = int(dt.datetime(2026, 10, 22, 20, tzinfo=dt.timezone.utc).timestamp())

            class Resp(io.BytesIO):
                headers = {}

            def fake(req, timeout=30):
                if '/history/t/' in req.full_url:                                   # the site's weekly closes: CRWV only
                    t = req.full_url.rsplit('/', 1)[1][:-5]
                    asked.append('site:' + t)
                    if t != 'CRWV':
                        raise urllib.error.HTTPError(req.full_url, 404, 'Not Found', {}, None)
                    return Resp(json.dumps({'start': '2026-10-09', 'c': [98.0, None, 101.5]}).encode())
                t = req.full_url.split('/chart/')[1].split('?')[0]
                asked.append(t)
                if t == 'ZZZZ':
                    raise urllib.error.HTTPError(req.full_url, 404, 'Not Found', {}, None)
                body = {'chart': {'result': [{'timestamp': [day - 86400, day], 'indicators': {'quote': [{'close': [100.0, 101.5], 'volume': [1, 2]}]}}]}}
                return Resp(json.dumps(body).encode())
            real = urllib.request.urlopen
            urllib.request.urlopen = fake
            try:
                st = V.collect_prices(root, hub, today=today, site_url='https://example.org/')
                again = V.collect_prices(root, hub, today=today, site_url='https://example.org/')
            finally:
                urllib.request.urlopen = real
            self.assertEqual(sorted(a for a in asked if not a.startswith('site:')), ['NBIS', 'ZZZZ'])   # CRWV: the site's
            self.assertEqual(sorted(a[5:] for a in asked if a.startswith('site:')), ['CRWV', 'NBIS', 'ZZZZ'])   # AAPL: the hub's
            self.assertEqual(st['saved'], 2)
            self.assertEqual(st['by_source'], {'site-weekly': 1, 'yahoo': 1})
            self.assertEqual(again['wanted'], 0)                                    # fresh, and ZZZZ remembered as unknown
            dirs = [hub, root / 'cache' / 'prices']
            self.assertEqual(V.load_prices(dirs, 'CRWV'), [('2026-10-09', 98.0), ('2026-10-23', 101.5)])
            self.assertEqual(V.load_prices(dirs, 'NBIS')[-1], ('2026-10-22', 101.5))
            wk = [((dt.date(2025, 1, 3) + dt.timedelta(days=7 * i)).isoformat(), 100 * math.exp(0.02 * ((-1) ** i))) for i in range(60)]
            self.assertAlmostEqual(V.annual_vol(wk), V.stdev([math.log(b[1] / a[1]) for a, b in zip(wk[-53:], wk[-52:])]) * math.sqrt(52))
            self.assertEqual(V.load_prices(dirs, 'AAPL'), [('2026-10-22', 250.0)])
            self.assertEqual(V.load_prices(dirs, 'ZZZZ'), [])
