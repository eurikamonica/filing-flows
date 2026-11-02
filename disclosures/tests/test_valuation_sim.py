"""app/valuation_sim.py and the drug programs of app/outside.py: grouping ClinicalTrials.gov studies into programs, the
pipeline rNPV solved from the price (its algebra, the catalysts' zero expected move, the guards), the Schwartz–Moon
simulation (determinism and direction of its inputs), the build's output, and docs/sim-view.js drawing it."""
import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'app'))
sys.path.insert(0, str(HERE))
import markov as MK  # noqa: E402
import outside as O  # noqa: E402
import valuation_methods as VMx  # noqa: E402
import valuation_sim as VS  # noqa: E402

TODAY = dt.date(2026, 11, 2)


def study(i, drugs, phase, status='RECRUITING', pcd='2027-06', title='', conditions=('Asthma',), kind='INTERVENTIONAL'):
    return {'id': f'NCT{i:08d}', 'title': title or f'Study {i}', 'phases': [phase] if phase else [], 'type': kind, 'status': status, 'pcd': pcd,
            'conditions': list(conditions), 'drugs': list(drugs), 'n': 100, 'sponsor': 'Acme Therapeutics'}


class Programs(unittest.TestCase):
    def test_grouping(self):
        st = [study(1, ['IDE196', 'Crizotinib'], 'PHASE3', title='IDE196 (Darovasertib) plus crizotinib', conditions=['Uveal Melanoma']),
              study(2, ['Darovasertib'], 'PHASE2', conditions=['Uveal Melanoma']),
              study(3, ['40 mg/day vormatrogine for 12 weeks', 'Placebo'], 'PHASE3', conditions=['Focal Epilepsy']),
              study(4, ['vormatrigine'], 'PHASE2', status='COMPLETED', pcd='2025-05', conditions=['Focal Epilepsy']),
              study(5, ['ABC-1'], 'PHASE1', status='TERMINATED', pcd='2019-01'),              # stopped: not a program
              study(6, ['OLD-9'], 'PHASE2', status='COMPLETED', pcd='2020-03'),               # dormant for years
              study(7, ['Blood draw'], None, kind='OBSERVATIONAL'),
              study(8, ['Placebo-matching tablets'], 'PHASE2'),
              study(9, ['MKT-1'], 'PHASE4'),
              study(10, ['IDE397'], 'PHASE1', conditions=['Solid Tumors']),                  # a different code name: its own program
              study(11, ['Biological: IDE397 then IDE397 for remaining 6 weeks'], 'PHASE1', conditions=['Solid Tumors'])]
        P = {r[0]: r for r in O.trial_programs(st, TODAY)}
        self.assertEqual(len(P), 4, P)
        self.assertEqual(P['ide397'][3], 2)
        dar = next(r for r in P.values() if 'ide196' in [r[0]] + r[7])
        self.assertEqual(dar[1], 'PHASE3')
        self.assertTrue(dar[6])                                            # melanoma: oncology
        self.assertEqual(dar[3], 2)
        vor = next(r for r in P.values() if r[0].startswith('vormatr'))
        self.assertEqual(vor[3], 2)                                        # a typo in one study joins the same program
        self.assertIn('PHASE4', [r[1] for r in P.values()])
        self.assertEqual(O.drug_name('1.0mg/kg/day PRAX-562'), 'prax-562')
        self.assertIsNone(O.drug_name('Placebo'))
        self.assertEqual(O.drug_name('XEN1101 and placebo'), 'xen1101')
        self.assertEqual(O.drug_name('[14C]-DNL343'), 'dnl343')
        s = O.trials_summary(st, TODAY)
        self.assertEqual(len(s['programs']), 4)
        self.assertEqual(s['program_fields'][0], 'drug')

    def test_other_names_join_a_program(self):
        a = study(1, ['XEN1101', 'Placebo'], 'PHASE3', conditions=['Focal Epilepsy'])
        a['other_names'] = [['azetukalner', 'XEN-1101'], []]
        b = study(2, ['Azetukalner'], 'PHASE3', conditions=['Major Depressive Disorder'])
        P = O.trial_programs([a, b], TODAY)
        self.assertEqual(len(P), 1, P)
        self.assertEqual(P[0][3], 2)
        calls = []

        def fetch(url, params):                                         # the API refuses the field once: collect without it
            calls.append(params['fields'])
            if O.CT_OTHER_NAMES in params['fields']:
                raise RuntimeError('HTTP 400')
            return {'studies': []}
        O._ct_other[0] = True
        try:
            O._trials_query({'key': 'acme', 'core': 'acme', 'ticker': 'ACME'}, 'acme', set(), fetch)
            self.assertEqual(len(calls), 2)
            self.assertFalse(O._ct_other[0])
        finally:
            O._ct_other[0] = True

    def test_sponsor_is_the_company(self):
        co = lambda name, ticker='X': {'name': name, 'key': O.norm(name), 'core': O.core(name), 'ticker': ticker}   # noqa: E731
        self.assertFalse(O.is_company('Sunshine Lake Pharma Co., Ltd.', co('Sunshine Biopharma Inc.')))
        self.assertFalse(O.is_company('China Medical University Hospital', co('CHINA PHARMA HOLDINGS, INC.')))
        self.assertFalse(O.is_company('Tarsus University', co('Tarsus Pharmaceuticals, Inc.')))
        self.assertTrue(O.is_company('IDEAYA Biosciences', co('IDEAYA Biosciences, Inc.')))
        self.assertTrue(O.is_company('Novo Nordisk A/S', co('NOVO NORDISK A S')))
        self.assertTrue(O.is_company('Neurocrine UK Limited', co('NEUROCRINE BIOSCIENCES INC')))
        self.assertTrue(O.is_company('GE Healthcare Finland Oy', co('GE HealthCare Technologies Inc.')))
        self.assertTrue(O.is_company('Merck Sharp & Dohme LLC', co('MERCK & CO., INC.', 'MRK')))
        self.assertTrue(O.is_company('Kite, A Gilead Company', co('GILEAD SCIENCES, INC.', 'GILD')))
        self.assertTrue(O.is_company('Eli Lilly and Company', co('ELI LILLY & Co')))

def drug_case(**kw):
    F = {'cik': 1, 'ticker': 'ACME', 'name': 'Acme Therapeutics, Inc.', 'sic': '2836', 'kind': 'industrial', 'revenue': 2e6, 'oi': -150e6,
         'da': 2e6, 'capex': 3e6, 'cash': 600e6, 'debt': 50e6, 'claims': 0.0, 'shares': 100e6, 'price': 12.0, 'mcap': 1.2e9, 'tax_rate': 0.21, 'src': {}}
    F.update(kw)
    W = {'wacc': 0.10, 'ke': 0.10, 'kd': 0.07}
    out = {'stage': {'metrics': {'fcf': -151e6}}, 'football': [], 'notes': []}
    progs = [['zanu', 'PHASE3', True, 3, 'Uveal Melanoma', '2027-03', True, []],
             ['xyl-202', 'PHASE2', True, 2, 'Focal Epilepsy', '2027-09', False, []],
             ['xyl-303', 'PHASE1', True, 1, 'Obesity', None, False, []]]
    trials = {'sponsor': 'Acme Therapeutics', 'programs': progs}
    mature = {'label': 'SIC 283, revenue $10–50B', 'n': 400, 'p25': 0.18, 'p50': 0.28, 'p75': 0.35}
    return F, W, out, trials, mature


class Pipeline(unittest.TestCase):
    def test_rates_and_curve(self):
        self.assertAlmostEqual(VS.loa('1', False), 0.520 * 0.289 * 0.578 * 0.906)
        self.assertAlmostEqual(round(VS.loa('1', False), 3), 0.079)          # the report's 7.9% from phase 1
        self.assertAlmostEqual(round(VS.loa('2', False), 3), 0.151)
        self.assertAlmostEqual(round(VS.loa('3', False), 3), 0.524)
        self.assertLess(VS.loa('2', True), VS.loa('2', False))               # oncology is harder
        self.assertAlmostEqual(VS.years_to_launch('3', None, TODAY), 3.3 / 2 + 1.3)
        self.assertAlmostEqual(VS.years_to_launch('1', None, TODAY), 2.3 / 2 + 3.6 + 3.3 + 1.3)
        self.assertAlmostEqual(VS.years_to_launch('2', '2027-11-02', TODAY), 365 / 365.25 + 3.3 + 1.3, places=6)
        self.assertGreater(VS.pv_per_peak(2, 0.1, 0.3), VS.pv_per_peak(6, 0.1, 0.3))

    def test_solved_from_the_price(self):
        F, W, out, trials, mature = drug_case()
        r, why = VS.rnpv(F, W, out, trials, mature, TODAY, VMx)
        self.assertIsNone(why)
        self.assertEqual(len(r['programs']), 3)
        lhs = sum(p['loa'] * p['f'] for p in r['programs']) * r['required_peak']
        self.assertAlmostEqual(lhs, r['ev'] + r['pv_burn'], delta=1.0)    # Σ LOA × f × S = EV + PV(burn)
        self.assertAlmostEqual(r['ev'], 1.2e9 - (600e6 - 50e6))
        self.assertLess(r['required_peak_lo'], r['required_peak'])
        self.assertLess(r['required_peak'], r['required_peak_hi'])
        self.assertGreater(r['required_peak_lead'], r['required_peak'])
        self.assertAlmostEqual(r['p_none'], (1 - r['programs'][0]['loa']) * (1 - r['programs'][1]['loa']) * (1 - r['programs'][2]['loa']))
        self.assertAlmostEqual(sum(p['value_ps'] for p in r['programs']) * F['shares'], r['ev'] + r['pv_burn'], delta=1.0)
        self.assertEqual([c['drug'] for c in r['catalysts']], ['zanu', 'xyl-202'])
        for c in r['catalysts']:                                           # the price already holds the bet
            self.assertAlmostEqual(c['p_success'] * c['up_ps'] + (1 - c['p_success']) * c['down_ps'], 0.0, places=9)
        self.assertTrue(r['calc']['steps'] and r['calc']['assumptions'])
        cheap, _ = VS.rnpv({**F, 'price': 1.0, 'mcap': 0.1e9}, W, out, trials, mature, TODAY, VMx)
        self.assertEqual(cheap['required_peak'], 0.0)                      # the price is below the cash left after the trials: nothing asked

    def test_guards(self):
        F, W, out, trials, mature = drug_case()
        self.assertEqual(VS.rnpv({**F, 'sic': '7372'}, W, out, trials, mature, TODAY, VMx), (None, None))
        self.assertIn('profitable', VS.rnpv({**F, 'oi': 5e6}, W, out, trials, mature, TODAY, VMx)[1])
        many = {**trials, 'programs': [[f'd{i}', 'PHASE1', True, 1, '', None, False, []] for i in range(40)]}
        self.assertIn('more than one company', VS.rnpv(F, W, out, many, mature, TODAY, VMx)[1])
        self.assertIn('next Beyond the filings build', VS.rnpv(F, W, out, {'sponsor': 'Acme Therapeutics'}, mature, TODAY, VMx)[1])


def burner(**kw):
    F = {'kind': 'industrial', 'revenue': 400e6, 'oi': -80e6, 'da': 20e6, 'capex': 30e6, 'cash': 300e6, 'debt': 100e6, 'claims': 0.0,
         'shares': 200e6, 'price': 10.0, 'g0': 0.25, 'sg': 0.08, 'sm': 0.03, 'tax_rate': 0.21}
    F.update(kw)
    W = {'wacc': 0.10, 'kd': 0.07}
    out = {'stage': {'metrics': {'fcf': -90e6}}}
    prior = {'g_phi': 0.45, 'g_res_sd': 0.12, 'kappa': 0.3, 'm_sd': 0.02, 'rho_gm': 0.2, 'g_pairs': 5000, 'rho_n': 4000}
    return F, W, out, prior


class SchwartzMoon(unittest.TestCase):
    def run_sm(self, tm=0.15, n=800, **kw):
        F, W, out, prior = burner(**kw)
        res, why = VS.schwartz_moon(F, W, out, prior, {'treasury_1y': 4.2}, None, '2026-11-02', tm, n=n)
        self.assertIsNone(why)
        return res

    def test_engine(self):
        a, b = self.run_sm(), self.run_sm()
        self.assertEqual(a[1]['mean'], b[1]['mean'])                       # common random numbers: deterministic
        item, blk = a
        self.assertTrue(item['lens'])
        self.assertTrue(blk['p10'] <= blk['p50'] <= blk['p90'])
        self.assertEqual(len(blk['survival']), 10)
        self.assertTrue(all(x >= y for x, y in zip(blk['survival'], blk['survival'][1:])))   # survival never rises
        self.assertTrue(all(x <= y for x, y in zip(blk['profit_by'], blk['profit_by'][1:])))
        self.assertAlmostEqual(blk['p_fail10'], 1 - blk['survival'][-1])
        rich = self.run_sm(cash=3e9)[1]
        poor = self.run_sm(cash=50e6)[1]
        self.assertLess(rich['p_fail5'], poor['p_fail5'])                  # more cash: less chance of running out
        self.assertLess(self.run_sm(tm=0.05)[1]['mean'], self.run_sm(tm=0.25)[1]['mean'])
        self.assertGreaterEqual(poor['dilution']['median_new_shares'], rich['dilution']['median_new_shares'])

    def test_credit_line_and_maturities(self):
        F, W, out, prior = burner(cash=120e6, debt=400e6)
        sm = lambda drec: VS.schwartz_moon(F, W, out, prior, {'treasury_1y': 4.2}, None, '2026-11-02', 0.15, n=800, drec=drec)[0][1]   # noqa: E731
        base = sm(None)
        line = sm({'analysis': {'revolver_available': 300e6}})
        wall = sm({'snapshot': {'maturities': {'as_of': '2026-06-30', 'next12m': 0, 'y2': 250e6, 'y3': 0}}})
        self.assertLess(line['p_fail5'], base['p_fail5'])                  # a credit line buys time
        self.assertEqual(wall['p_fail5'], base['p_fail5'])                  # maturing debt is rolled over in the simulation...
        self.assertGreater(wall['p_fail5_norefi'], base['p_fail5'])         # ...and must be repaid in the stress beside it
        self.assertIsNone(base['p_fail5_norefi'])
        self.assertEqual(line['inputs']['credit_line'], 300e6)
        self.assertEqual(wall['inputs']['due'], [0, 250e6, 0, 0, 0])
        self.assertIsNone(base['inputs']['due'])
        self.assertEqual(base['mean'] >= 0, True)

    def test_loss_makers_margin_from_one_regression(self):
        F, W, out, prior = burner()
        run = lambda a: VS.schwartz_moon(F, W, out, {**prior, 'loss_a': a, 'loss_kappa': 0.2}, {}, None, None, 0.15, n=800)[0][1]   # noqa: E731
        lo, hi = run(-0.03), run(0.03)
        self.assertLess(lo['profit_by'][4], hi['profit_by'][4])            # the regression's intercept sets where losses settle
        self.assertEqual(lo['inputs']['a_loss'], -0.03)
        F['years'] = [(0.3, -0.2), (0.25, -0.2), (0.2, -0.2), (0.22, -0.2)]
        sg, how = VS.growth_spread(F, 0.2)
        self.assertTrue(0.03 <= sg < 0.2 and 'shrunk' in how)

    def test_stock_pay_is_not_cash(self):
        plain, paid = self.run_sm(cash=150e6)[1], self.run_sm(cash=150e6, sbc=60e6)[1]
        self.assertLess(paid['p_fail5'], plain['p_fail5'])                  # stock-based pay does not drain the cash
        self.assertEqual(paid['mean'] >= plain['mean'], True)
        self.assertAlmostEqual(paid['inputs']['sbc'], 0.15)

    def test_liquidity(self):
        room, due, asof = VS.liquidity({'debt': 300e6}, {'analysis': {'revolver_available': None}, 'snapshot': {
            'revolver_available': 50e6, 'maturities': {'as_of': '2025-12-31', 'rest_of_year': 20e6, 'y2': 400e6, 'y4': 10e6}}})
        self.assertEqual(room, 50e6)
        self.assertEqual(due, [20e6, 280e6, 0.0, 0.0, 0.0])                # never more due than the debt on the balance sheet
        self.assertEqual(asof, '2025-12-31')
        self.assertEqual(VS.liquidity({'debt': 1.0}, None), (0.0, None, None))

    def test_who_gets_it(self):
        F, W, out, prior = burner(oi=50e6)
        out = {'stage': {'metrics': {'fcf': 40e6}}}
        self.assertEqual(VS.schwartz_moon(F, W, out, prior, {}, None, None, 0.15), (None, None))      # profitable and cash-generating
        F, W, out, prior = burner(oi=80e6)                                   # 20% margin, investing more than it earns: a utility
        out = {'stage': {'metrics': {'fcf': -40e6}}}
        self.assertEqual(VS.schwartz_moon(F, W, out, prior, {}, None, None, 0.15), (None, None))
        F, W, out, prior = burner(oi=8e6)                                    # 2% margin and burning cash: in
        self.assertIsNotNone(VS.schwartz_moon(F, W, out, prior, {}, None, None, 0.15, n=200)[0])
        F, W, out, prior = burner(revenue=10e6)
        self.assertIn('$25M', VS.schwartz_moon(F, W, out, prior, {}, None, None, 0.15)[1])


class Build(unittest.TestCase):
    def test_build_and_page(self):
        import valuation as V
        import valuation_fixture as FX
        d = tempfile.mkdtemp()
        try:
            fx = FX.make(d)
            outside = Path(d) / 'outside'
            pre = next(c for c in fx['companies'] if c['sic'] == '2836')
            V.write_json(outside / 'c' / f"{pre['cik']}.json", {'cik': pre['cik'], 'trials': {
                'sponsor': pre['name'], 'programs': [['zanu', 'PHASE3', True, 3, 'Uveal Melanoma', '2027-03', True, []],
                                                     ['xyl-202', 'PHASE2', True, 2, 'Epilepsy', None, False, []]]}})
            st = V.build(fx['root'], fx['prices'], fx['debt'], fx['cons'], today=FX.TODAY, verbose=False, outside=outside)
            self.assertEqual(st['with_pipeline_rnpv'], 1)
            self.assertGreater(st['with_schwartz_moon'], 0)
            pub = Path(fx['root']) / 'public'
            ix = json.loads((pub / 'index.json').read_text())
            for f in ('sm_mean', 'sm_fail5', 'pipe_req_peak', 'mk_method'):
                self.assertIn(f, ix['fields'])
            A = json.loads((pub / 'c' / f"{pre['cik']}.json").read_text())
            self.assertGreater(A['rnpv']['required_peak'], 0)
            sm_docs = [json.loads(p.read_text()) for p in (pub / 'c').glob('*.json')]
            sm_docs = [x for x in sm_docs if x.get('schwartz_moon')]
            for x in sm_docs:
                m = next(m for m in x['appendix']['methods'] if m['method'].startswith('Schwartz–Moon'))
                self.assertTrue(m['fit'] and 'None' not in m['fit'])
                self.assertIsNone(m['weight'])                             # a lens: not in the stage-weighted value
                lows = [b['low'] for b in x['football'] if not b.get('lens') and b['method'] != '52-week trading range']
                self.assertTrue(x['range'] is None or abs(x['range'][0] - min(lows)) < 1e-9)
            others = [json.loads(p.read_text()) for p in (pub / 'c').glob('*.json')]
            self.assertTrue(any(any(n['method'].startswith('Schwartz–Moon') for n in o['appendix']['not_used']) for o in others))
            if shutil.which('node'):
                js = HERE.parent / 'docs' / 'sim-view.js'
                code = ("const SV=require(process.argv[1]);const fs=require('fs');let bad=0,n=0;"
                        "for(const f of process.argv.slice(2)){const d=JSON.parse(fs.readFileSync(f,'utf8'));if(!(d.rnpv||d.schwartz_moon||d.rnpv_why))continue;"
                        "const el={innerHTML:''};SV.mount(el,d);n++;const t=el.innerHTML.replace(/<[^>]+>/g,' ');if(/undefined|NaN/.test(t)||el.innerHTML.length<500)bad++;}"
                        "process.stdout.write(JSON.stringify({n,bad}))")
                files = [str(p) for p in (pub / 'c').glob('*.json')]
                res = subprocess.run(['node', '-e', code, str(js)] + files, capture_output=True, text=True, timeout=60)
                self.assertEqual(res.returncode, 0, res.stderr)
                got = json.loads(res.stdout)
                self.assertGreater(got['n'], 1)
                self.assertEqual(got['bad'], 0)
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
