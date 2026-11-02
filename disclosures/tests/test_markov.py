"""app/markov.py: the regime-switching Monte Carlo — yearly histories (annual frames, trailing twelve months), the hidden
Markov model's regimes, the panel prior and the Dirichlet posterior, consensus years, determinism, the build's output, and
that docs/markov-view.js (the browser engine) gives the same values from the same model."""
import random
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'app'))
sys.path.insert(0, str(HERE))
import markov as M  # noqa: E402


def model(**kw):
    m = {'years': 10, 'start': 1, 'P': [[0.5, 0.4, 0.1], [0.15, 0.7, 0.15], [0.05, 0.6, 0.35]], 'g': [0.2, 0.05, -0.06],
         'g_sd': [0.06, 0.03, 0.04], 'cons': [], 'cons_sd': 0.0, 'dm': [0.004, 0.0, -0.01], 'kappa': 0.3, 'm_sd': 0.01, 'm0': 0.3,
         'rev0': 400e9, 'tax': 0.16, 'da': 0.03, 'capex': 0.03, 'wc': 0.1, 'wacc': 0.085, 'g_term': 0.025, 'roic': 0.3,
         'debt': 100e9, 'cash': 130e9, 'claims': 0.0, 'shares': 15e9}
    m.update(kw)
    return m


class Regimes(unittest.TestCase):
    def test_states_and_yearly(self):
        self.assertEqual([M.state_of(g) for g in (0.25, 0.10, 0.099, 0.0, -0.01)], [0, 0, 1, 1, 2])
        revs = [100e6] * 4 + [110e6] * 4 + [99e6] * 4 + [104e6] * 4      # TTM 400 → 440 → 396 → 416 ($M)
        ys = M.yearly(revs, [10e6] * 16)
        self.assertEqual(len(ys), 3)
        self.assertAlmostEqual(ys[0][0], 0.10)
        self.assertAlmostEqual(ys[1][0], -0.10)
        self.assertAlmostEqual(ys[2][0], 416 / 396 - 1)
        self.assertAlmostEqual(ys[2][1], 40 / 416)
        self.assertEqual(M.yearly([1e8] * 7), [])                      # fewer than two full trailing years
        self.assertEqual(len(M.yearly([1e6] * 8 + [2e6] * 8)), 0)   # growth from a tiny base says nothing
        # annual frames: the latest run of consecutive years; the trailing year is appended when it ends later
        a = {'rev': {2018: 50e6, 2020: 100e6, 2021: 120e6, 2022: 108e6, 2023: 5e6, 2024: 6e6, 2025: 9e6}, 'oi': {2021: 12e6}}
        self.assertEqual(M.annual_years(a), ([], 2025))                  # 2024 starts from $5M: nothing usable at the end
        a = {'rev': {2018: 50e6, 2020: 100e6, 2021: 120e6, 2022: 108e6}, 'oi': {2021: 12e6}}
        hist, last = M.annual_years(a)
        self.assertEqual(last, 2022)
        self.assertEqual(len(hist), 2)                                     # 2019 is missing: the run starts at 2020
        self.assertAlmostEqual(hist[0][0], 0.2)
        self.assertAlmostEqual(hist[0][1], 0.1)
        self.assertEqual(M.merge_years((hist, last), [(0.5, None), (0.07, 0.2)], 2023)[-1], (0.07, 0.2))
        self.assertEqual(len(M.merge_years((hist, last), [(0.07, 0.2)], 2022)), 2)
        self.assertEqual(M.merge_years(([], None), [(0.07, 0.2)], 2022), [(0.07, 0.2)])

    def test_posterior_and_panel(self):
        prior = [[0.5, 0.4, 0.1], [0.1, 0.8, 0.1], [0.1, 0.5, 0.4]]
        P = M.posterior([[0, 0, 0], [6, 0, 0], [0, 0, 0]], prior, k=6)
        for x, y in zip(P[0], prior[0]):
            self.assertAlmostEqual(x, y)                                  # no own data: the prior
        self.assertAlmostEqual(P[1][0], (6 + 0.6) / 12)                     # half own, half prior
        for r in P:
            self.assertAlmostEqual(sum(r), 1.0)
        cos = [{'mcap': 50e9, 'years': [(0.15, 0.2), (0.12, 0.21), (0.05, 0.2), (0.04, 0.19)]} for _ in range(30)]
        cos += [{'mcap': 1e9, 'years': [(0.02, 0.1), (-0.05, 0.08)]} for _ in range(5)]
        pp = M.panel_prior(cos)                                            # too few companies for the HMM: thresholds
        self.assertEqual(pp['large']['method'], 'thresholds')
        self.assertEqual(pp['large']['counts'][0], [30, 30, 0])
        self.assertEqual(pp['large']['transitions'], 90)
        self.assertIn('all', pp)
        self.assertTrue(pp['small']['thin'])                               # 5 small companies: rows borrowed from the panel
        self.assertEqual(pp['small']['P'][0], pp['all']['P'][0])
        for b in pp.values():
            for r in b['P']:
                self.assertAlmostEqual(sum(r), 1.0, places=9)

    def test_hmm_recovers_regimes(self):
        rng = random.Random(1)
        mu, sd = [0.25, 0.05, -0.10], [0.08, 0.03, 0.05]
        P = [[0.6, 0.35, 0.05], [0.1, 0.8, 0.1], [0.05, 0.5, 0.45]]
        cos = []
        for c in range(400):
            s, ys = rng.choices([0, 1, 2], [0.2, 0.65, 0.15])[0], []
            for _ in range(rng.randint(4, 15)):
                s = rng.choices([0, 1, 2], P[s])[0]
                ys.append((mu[s] + sd[s] * rng.gauss(0, 1), 0.15 + rng.gauss(0, 0.02)))
            cos.append({'years': ys, 'mcap': 1e9})
        pp = M.panel_prior(cos)
        b = pp['all']
        self.assertEqual(b['method'], 'hmm')
        self.assertEqual(b['labels'], ['Fast growth', 'Moderate growth', 'Decline'])          # named for what was learned
        self.assertEqual(M.regime_labels([0.31, 0.10, 0.05], [0.4, 0.14, 0.05], 'hmm'), ['Fast growth', 'Uneven growth', 'Steady growth'])
        self.assertEqual(M.regime_labels([0.2, 0.05, -0.1], [0.1, 0.03, 0.07], 'thresholds'), M.THRESHOLD_LABELS)
        for got, want in zip(b['g'], mu):
            self.assertAlmostEqual(got, want, delta=0.02)
        for i in range(3):
            for j in range(3):
                self.assertAlmostEqual(b['P'][i][j], P[i][j], delta=0.08)
        self.assertTrue(0.2 < b['g_phi'] < 0.7)                            # persistent but mean-reverting growth
        post = M.hmm_posterior([0.30, 0.28, 0.33], b['hmm'])
        self.assertGreater(post['now'][0], 0.8)                            # three years of 30% growth: the high regime
        F = {'sm': 0.01}
        base = {'margin': 0.2, 'rev0': 1e9, 'tax': 0.2, 'da': 0.03, 'capex': 0.03, 'wc': 0.1, 'g': 0.025, 'roic': 0.2, 'debt': 0, 'cash': 0,
                'claims': 0, 'shares': 1e8}
        pr = M.params(F, base, {'wacc': 0.09}, [(0.3, 0.2), (0.28, 0.2), (0.33, 0.2)], b)
        self.assertEqual(pr['method'], 'hmm')
        self.assertAlmostEqual(sum(pr['model']['start_p']), 1.0)
        self.assertEqual(pr['model']['start'], 0)
        s0 = M.start_states(pr['model'], 1000)
        self.assertAlmostEqual(s0.count(0) / 1000, pr['model']['start_p'][0], delta=0.002)   # stratified: exact shares

    def test_consensus_years(self):
        cons = {'analysts': {'periods': [
            {'period': '0y', 'end': '2026-09-30', 'rev': {'growth': 0.06, 'numberOfAnalysts': 30, 'low': 400, 'high': 440, 'avg': 420}},
            {'period': '+1y', 'end': '2027-09-30', 'rev': {'growth': 0.07, 'numberOfAnalysts': 2}}]}}
        gs, sd, how = M.consensus_growth(cons, '2026-08-01')
        self.assertEqual(gs, [0.06])                                       # +1y has only two analysts
        self.assertAlmostEqual(sd, 40 / 420 / 4)
        self.assertIn('30 analysts', how)
        gs, _, _ = M.consensus_growth(cons, '2026-10-21')                  # the fiscal year has ended: not a forecast
        self.assertEqual(gs, [])

    def test_engine(self):
        a, b = M.simulate(model(), n=500), M.simulate(model(), n=500)
        self.assertEqual(a, b)                                             # common random numbers: deterministic
        med = lambda xs: sorted(xs)[len(xs) // 2]
        self.assertGreater(med(M.simulate(model(), n=500, dg=0.02)), med(a))
        self.assertLess(med(M.simulate(model(), n=500, wacc=0.10)), med(a))
        self.assertEqual(M.simulate(model(sbc=0.06), n=500), a)            # stock pay is inside operating income: counted once
        mixed = M.simulate(model(start_p=[0.5, 0.5, 0.0]), n=500)
        self.assertNotEqual(mixed, a)
        out, hv = M.simulate(model(), n=200, track=True)
        self.assertEqual(len(hv), 10)
        self.assertEqual(hv[-1], out)
        occ = M.occupancy(model()['P'], 1)
        self.assertEqual(occ[0], [0.0, 1.0, 0.0])
        self.assertAlmostEqual(sum(occ[-1]), 1.0)
        self.assertEqual(M.occupancy(model()['P'], 1, start_p=[0.2, 0.8, 0.0])[0], [0.2, 0.8, 0.0])

    @unittest.skipUnless(shutil.which('node'), 'node is not installed')
    def test_browser_engine_matches(self):
        m = model(cons=[0.06, 0.07], cons_sd=0.01, capex=[0.04, 0.035, 0.03], start_p=[0.3, 0.5, 0.2])
        js = HERE.parent / 'docs' / 'markov-view.js'
        code = ("const MV=require(process.argv[1]);const m=JSON.parse(require('fs').readFileSync(0,'utf8'));"
                "const r=MV.mulberry32(20251027);process.stdout.write(JSON.stringify({u:[r(),r(),r()],v:Array.from(MV.simulate(m,{n:300}))}))")
        res = subprocess.run(['node', '-e', code, str(js)], input=json.dumps(m), capture_output=True, text=True, timeout=60)
        self.assertEqual(res.returncode, 0, res.stderr)
        got = json.loads(res.stdout)
        r = M.mulberry32(M.SEED)
        self.assertEqual(got['u'], [r(), r(), r()])
        py = M.simulate(m, n=300)
        self.assertLess(max(abs(x - y) / max(1.0, abs(x)) for x, y in zip(py, got['v'])), 1e-9)

    def test_build_writes_the_section(self):
        import valuation as V
        import valuation_fixture as FX
        d = tempfile.mkdtemp()
        try:
            fx = FX.make(d)
            st = V.build(fx['root'], fx['prices'], fx['debt'], fx['cons'], today=FX.TODAY, verbose=False)
            self.assertEqual(st['with_markov'], st['with_dcf'])
            pub = Path(fx['root']) / 'public'
            mk = json.loads((pub / 'markov.json').read_text())
            self.assertIn('all', mk['buckets'])
            ix = json.loads((pub / 'index.json').read_text())
            self.assertIn('mk_p50', ix['fields'])
            docs = [json.loads(f.read_text()) for f in (pub / 'c').glob('*.json')]
            with_mk = [x for x in docs if x.get('markov')]
            self.assertTrue(with_mk)
            for x in with_mk:
                k = x['markov']
                self.assertTrue(k['p10'] <= k['p50'] <= k['p90'])
                self.assertEqual(k['model']['wacc'], x['wacc']['wacc'])
                self.assertTrue(any(f['method'].startswith('Regime-switching') for f in x['football']))
                for key in ('matrix', 'regimes', 'now', 'growth', 'years_1_2', 'margin', 'sbc', 'wacc', 'terminal'):
                    self.assertIn(key, k['sources'])
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
