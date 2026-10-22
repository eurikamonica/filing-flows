"""app/markov.py: the regime-switching Monte Carlo — regimes from trailing-twelve-month revenue, the panel prior and the
Dirichlet posterior, consensus years, determinism, the build's output, and that docs/markov-view.js (the browser engine)
gives the same values from the same model."""
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
         'rev0': 400e9, 'tax': 0.16, 'da': 0.03, 'capex': 0.03, 'wc': 0.1, 'sbc': 0.03, 'wacc': 0.085, 'g_term': 0.025, 'roic': 0.3,
         'debt': 100e9, 'cash': 130e9, 'claims': 0.0, 'shares': 15e9}
    m.update(kw)
    return m


class Regimes(unittest.TestCase):
    def test_states_and_yearly(self):
        self.assertEqual([M.state_of(g) for g in (0.25, 0.10, 0.099, 0.0, -0.01)], [0, 0, 1, 1, 2])
        revs = [100.0] * 4 + [110.0] * 4 + [99.0] * 4 + [104.0] * 4      # TTM 400 → 440 → 396 → 416
        ys = M.yearly(revs, [10.0] * 16)
        self.assertEqual(len(ys), 3)
        self.assertAlmostEqual(ys[0][0], 0.10)
        self.assertAlmostEqual(ys[1][0], -0.10)
        self.assertAlmostEqual(ys[2][0], 416 / 396 - 1)
        self.assertAlmostEqual(ys[2][1], 40 / 416)
        self.assertEqual(M.yearly([1.0] * 7), [])                      # fewer than two full trailing years

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
        pp = M.panel_prior(cos)
        self.assertEqual(pp['large']['counts'][0], [30, 30, 0])
        self.assertEqual(pp['large']['transitions'], 90)
        self.assertIn('all', pp)
        self.assertTrue(pp['small']['thin'])                               # 5 small companies: rows borrowed from the panel
        self.assertEqual(pp['small']['P'][0], pp['all']['P'][0])
        for b in pp.values():
            for r in b['P']:
                self.assertAlmostEqual(sum(r), 1.0, places=9)

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
        self.assertLess(med(M.simulate(model(sbc=0.06), n=500)), med(a))    # stock pay is a cost
        out, hv = M.simulate(model(), n=200, track=True)
        self.assertEqual(len(hv), 10)
        self.assertEqual(hv[-1], out)
        occ = M.occupancy(model()['P'], 1)
        self.assertEqual(occ[0], [0.0, 1.0, 0.0])
        self.assertAlmostEqual(sum(occ[-1]), 1.0)

    @unittest.skipUnless(shutil.which('node'), 'node is not installed')
    def test_browser_engine_matches(self):
        m = model(cons=[0.06, 0.07], cons_sd=0.01, capex=[0.04, 0.035, 0.03])
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
                for key in ('matrix', 'growth', 'years_1_2', 'margin', 'sbc', 'wacc', 'terminal'):
                    self.assertIn(key, k['sources'])
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
