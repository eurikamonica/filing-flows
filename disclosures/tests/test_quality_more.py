"""quality_more.py on hand-checked figures: the Dechow F-score, Montier's C-score, modified-Jones residuals, Sloan's
persistence, Quality Minus Junk, taxes, goodwill and the non-GAAP gap."""
import math
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import quality_more as QM  # noqa: E402

M = 1e6


def yr(end, **k):
    base = dict(end=end, assets=1000 * M, ca=400 * M, cl=200 * M, liab=500 * M, eq=500 * M, cash=100 * M, ltd=200 * M, ltd_c=20 * M,
                ar=100 * M, inv=80 * M, rev=1000 * M, gp=400 * M, cogs=600 * M, oi=150 * M, ni=100 * M, ocf=130 * M, ppe=300 * M,
                da=40 * M, oca=20 * M, issue=0, debt_issue=0, dil=100e6, div=20 * M, buyback=30 * M)
    base.update({kk: (v * M if isinstance(v, (int, float)) and kk not in ('dil',) and abs(v) < 1e5 else v) for kk, v in k.items()})
    return base


class Screens(unittest.TestCase):
    def test_dechow_by_hand(self):
        p2, p, c = yr('2023-12-31'), yr('2024-12-31'), yr('2025-12-31', ar=150, inv=100, rev=1100, ni=120, assets=1100, ca=480, debt_issue=50)
        d = QM.dechow(c, p, p2)
        avg = 1050 * M
        # RSST: WC = (CA − cash) − (CL − current debt); NCO = (TA − CA) − (TL − CL − long-term debt); FIN = −(debt)
        wc0, wc1 = (480 - 100) - (200 - 20), (400 - 100) - (200 - 20)
        nco0, nco1 = (1100 - 480) - (500 - 200 - 180), (1000 - 400) - (500 - 200 - 180)
        rsst = ((wc0 - wc1) + (nco0 - nco1)) * M / avg
        x = dict(rsst_acc=rsst, ch_rec=50 * M / avg, ch_inv=20 * M / avg, soft_assets=(1100 - 300 - 100) / 1100,
                 ch_cs=(1100 - 50) / 1000 - 1, ch_roa=120 * M / avg - 100 * M / 1000e6, issue=1.0)
        for k, v in x.items():
            self.assertAlmostEqual(d['x'][k], v, places=3, msg=k)
        pv = -7.893 + 0.790 * x['rsst_acc'] + 2.518 * x['ch_rec'] + 1.191 * x['ch_inv'] + 1.979 * x['soft_assets'] + 0.171 * x['ch_cs'] - 0.932 * x['ch_roa'] + 1.029
        self.assertAlmostEqual(d['f'], 1 / (1 + math.exp(-pv)) / 0.0037, places=2)
        self.assertEqual(d['assumed'], [])
        quiet = QM.dechow(yr('2025-12-31'), yr('2024-12-31'), yr('2023-12-31'))
        self.assertLess(quiet['f'], d['f'])
        self.assertIsNone(QM.dechow(yr('2025-12-31', ar=None), p))

    def test_cscore_signs(self):
        p, c = yr('2024-12-31'), yr('2025-12-31', ni=150, ocf=100, ar=130, inv=110, oca=40, da=30, assets=1200)
        cs = QM.cscore(c, p)
        self.assertEqual((cs['score'], cs['n']), (6, 6))
        self.assertEqual(QM.cscore(yr('2025-12-31'), yr('2024-12-31'))['score'], 0)
        self.assertIsNone(QM.cscore({'end': 'x'}, {'end': 'y'}))

    def test_jones_recovers_the_model(self):
        rnd = random.Random(3)
        obs = []
        for i in range(60):
            inv_a, drev, ppe = 1 / rnd.uniform(500, 5000), rnd.uniform(-0.2, 0.4), rnd.uniform(0.1, 0.8)
            ta = 0.01 + 20 * inv_a + 0.05 * drev - 0.08 * ppe + (0.2 if i == 0 else rnd.gauss(0, 0.002))
            obs.append({'key': i, 'group': 'tech|2025', 'ta': ta, 'inv_a': inv_a, 'drev': drev, 'ppe': ppe, 'roa': rnd.uniform(-0.1, 0.2)})
        res = QM.jones(obs)
        self.assertEqual(len(res), 60)
        self.assertGreater(res[0]['da'], 0.1)                       # the planted outlier: accruals the model cannot explain
        self.assertTrue(all(abs(res[i]['da']) < 0.03 for i in range(1, 60)))
        self.assertFalse(QM.jones(obs[:5]))                         # too few in the group

    def test_persistence_split(self):
        rnd = random.Random(5)
        obs = {'tech': []}
        for _ in range(200):
            c, a = rnd.uniform(-0.05, 0.2), rnd.uniform(-0.1, 0.1)
            obs['tech'].append((c, a, 0.01 + 0.8 * c + 0.4 * a + rnd.gauss(0, 0.005)))
        p = QM.persistence(obs)['tech']
        self.assertAlmostEqual(p['b_cash'], 0.8, delta=0.03)
        self.assertAlmostEqual(p['b_acc'], 0.4, delta=0.05)
        self.assertGreater(p['r2'], 0.9)

    def test_stability(self):
        recs = [yr(f'{y}-12-31', ni=100 + 10 * (y % 2), ocf=130 + 40 * (y % 2)) for y in range(2020, 2026)]
        s = QM.stability(recs)
        self.assertEqual(s['years'], 6)
        self.assertLess(s['smooth'], 1)                              # profit steadier than cash flow
        self.assertEqual(s['loss_years'], 0)
        self.assertIsNone(QM.stability(recs[:2]))


class QMJ(unittest.TestCase):
    def test_better_companies_rank_higher(self):
        rnd = random.Random(1)
        inputs = {}
        for i in range(40):
            q = i / 39                                                  # 0 = junk … 1 = quality
            recs = [yr(f'{y}-12-31', gp=300 + 300 * q + 20 * (y - 2020) * q, ni=20 + 150 * q + 10 * (y - 2020) * q + rnd.gauss(0, 30 * (1 - q)),
                       ocf=30 + 160 * q + 10 * (y - 2020) * q, ltd=400 - 300 * q, ltd_c=0, div=5 + 40 * q, buyback=5 + 50 * q, dil=(100 + (1 - q) * 5 * (y - 2020)) * 1e6)
                    for y in range(2020, 2026)]
            inputs[i] = QM.qmj_inputs(recs, beta=1.5 - q, ivol=0.5 - 0.3 * q, z=1 + 3 * q)
        sc = QM.qmj_scores(inputs)
        self.assertEqual(len(sc), 40)
        self.assertGreater(sc[39]['qmj'], 1)
        self.assertLess(sc[0]['qmj'], -1)
        r = [sc[i]['qmj'] for i in range(40)]
        self.assertGreater(sum(r[i] < r[i + 5] for i in range(35)), 30)
        self.assertTrue(all(sc[39][p] > 0 for p in ('profitability', 'growth', 'safety', 'payout')))

    def test_inputs(self):
        recs = [yr(f'{y}-12-31') for y in range(2021, 2026)]
        x = QM.qmj_inputs(recs, 1.1, 0.25, 3.2)
        self.assertAlmostEqual(x['gpoa'], 0.4)
        self.assertAlmostEqual(x['roe'], 0.2)
        self.assertAlmostEqual(x['lev'], 0.2)
        self.assertEqual(x['growth_years'], 4)
        self.assertAlmostEqual(x['npop'], 0.5)                       # (20 + 30) / 100 a year


class Other(unittest.TestCase):
    def test_taxes(self):
        recs = [yr(f'{y}-12-31', tax=20, tax_paid=10, pretax=100) for y in range(2022, 2026)]
        t = QM.taxes(recs)
        self.assertEqual(t['years'], 3)
        self.assertAlmostEqual(t['cash_to_book'], 0.5)
        self.assertAlmostEqual(t['cash_etr'], 0.1)
        self.assertAlmostEqual(t['book_etr'], 0.2)
        self.assertIsNone(QM.taxes([yr('2025-12-31')]))

    def test_goodwill(self):
        recs = [yr('2024-12-31', gw=300, intang=100), yr('2025-12-31', gw=450, intang=100, gw_imp=50)]
        g = QM.goodwill(recs, mcap=400 * M)
        self.assertAlmostEqual(g['gw_equity'], 1.1)
        self.assertEqual(g['tangible_equity'], -50 * M)
        self.assertEqual(len(g['signs']), 3)
        self.assertIsNone(QM.goodwill([yr('2025-12-31')]))

    def test_nongaap(self):
        street = [{'quarter': q, 'eps_act': 1.0} for q in ('2025-09-27', '2025-12-27', '2026-03-28', '2026-06-27')]
        qs = [('2025-09-30', 80 * M), ('2025-12-31', 80 * M), ('2026-03-31', 80 * M), ('2026-06-30', 80 * M)]
        n = QM.nongaap(street, qs, 100e6)
        self.assertAlmostEqual(n['gap'], 0.2)
        self.assertAlmostEqual(n['ratio'], 1.25)
        self.assertIsNone(QM.nongaap(street, qs[:2], 100e6))           # quarters that do not match
        self.assertIsNone(QM.nongaap(street[:3], qs, 100e6))


if __name__ == '__main__':
    unittest.main()
