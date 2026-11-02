"""The simulations' walk-forward backtest (app/sim_backtest.py) on synthetic annual frames."""
import datetime as dt
import math
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

import markov as MK  # noqa: E402
import sim_backtest as SB  # noqa: E402


def synthetic(n=260, seed=7, last=2025, stop_losers=True):
    """{cik: {'rev', 'oi', 'ni'}}: yearly growth from a two-regime chain, margins that drift; deep loss-makers with
    little cash stop filing."""
    rng = random.Random(seed)
    A, cash = {}, {}
    for i in range(n):
        cik = str(1000 + i)
        rev, m, fast = 10 ** rng.uniform(7.3, 9.5), rng.uniform(-0.6, 0.25), rng.random() < 0.3
        a = {'rev': {}, 'oi': {}, 'ni': {}}
        c = {}
        for y in range(2010, last + 1):
            if stop_losers and m < -0.15 and y >= 2014 and rng.random() < 0.4:
                break
            a['rev'][y], a['oi'][y], a['ni'][y] = rev, rev * m, rev * m * 0.8
            c[y] = rev * (0.05 if m < -0.2 else 0.4)
            fast = (rng.random() < 0.8) if fast else (rng.random() < 0.1)
            rev *= 1 + max(-0.5, min(1.0, rng.gauss(0.25 if fast else 0.04, 0.15 if fast else 0.06)))
            m = max(-0.9, min(0.5, m + 0.15 * (0.08 - m) + rng.gauss(0, 0.04)))
        A[cik] = a
        cash[cik] = c
    return A, cash


class Small(unittest.TestCase):
    """Smaller settings so the whole backtest runs in a few seconds."""

    def setUp(self):
        self.saved = (SB.N, SB.MAX_COS, SB.FIT_MAX, SB.MIN_CASH_ROWS)
        SB.N, SB.MAX_COS, SB.FIT_MAX, SB.MIN_CASH_ROWS = 60, 120, 200, 5

    def tearDown(self):
        SB.N, SB.MAX_COS, SB.FIT_MAX, SB.MIN_CASH_ROWS = self.saved


class TestBacktest(Small):
    def test_run_reports_every_model_and_horizon(self):
        A, cash = synthetic()
        out = SB.run(A, 2025, {'cash': cash, 'debt': {}}, log=lambda *a: None)
        self.assertEqual([o['year'] for o in out['origins']], [2013, 2015, 2017, 2019])
        for m in ('regime', 'schwartz_moon', 'naive', 'regime_scaled'):
            for h in ('1', '3', '5'):
                x = out['revenue'][m][h]
                self.assertGreater(x['n'], 50)
                self.assertAlmostEqual(x['coverage'] + x['below'] + x['above'], 1.0, places=9)
                self.assertAlmostEqual(sum(x['pit']), 1.0, places=9)
        self.assertIn(out['regime_sd_scale'], SB.SD_SCALES)
        best = out['regime_scales'][str(out['regime_sd_scale'])]['coverage_3y']
        self.assertTrue(all(abs(best - 0.8) <= abs(v['coverage_3y'] - 0.8) for v in out['regime_scales'].values()))
        self.assertTrue(out['margin_loss_makers']['3']['n'] > 0)
        self.assertTrue(out['cash_out_n'] > 0)
        s = out['summary']
        self.assertEqual(s['origins'], [2013, 2015, 2017, 2019])
        self.assertEqual(s['regime_sd_scale'], out['regime_sd_scale'])

    def test_wider_spreads_hold_more(self):
        A, _ = synthetic()
        out = SB.run(A, 2025, None, log=lambda *a: None)
        cov = [out['regime_scales'][str(f)]['coverage_3y'] for f in SB.SD_SCALES]
        self.assertEqual(cov, sorted(cov))

    def test_no_look_ahead(self):
        """What a model knows at an origin does not change when later years change."""
        A, _ = synthetic()
        B = {c: {k: {y: (v * 3 if y > 2015 else v) for y, v in d.items()} for k, d in a.items()} for c, a in A.items()}
        oa, ob = SB.origin_panel(A, 2015), SB.origin_panel(B, 2015)
        self.assertEqual(oa['stats']['g'], ob['stats']['g'])
        self.assertEqual(oa['stats']['loss_kappa'], ob['stats']['loss_kappa'])
        self.assertEqual(oa['gbar'], ob['gbar'])
        self.assertEqual(oa['hist'], ob['hist'])

    def test_cash_out_counts_companies_that_stopped(self):
        A, cash = synthetic()
        out = SB.run(A, 2025, {'cash': cash, 'debt': {}}, log=lambda *a: None)
        A2, _ = synthetic(stop_losers=False)
        out2 = SB.run(A2, 2025, {'cash': cash, 'debt': {}}, log=lambda *a: None)
        self.assertIsNotNone(out['cash_out'])
        self.assertGreater(out['cash_out']['base_rate'], 0.0)       # some loss-makers stopped filing within three years
        self.assertEqual((out2['cash_out'] or {}).get('base_rate', 0.0), 0.0)
        self.assertTrue(all(0 <= b['predicted'] <= 1 for b in out['cash_out']['bins']))


class TestPanelNow(unittest.TestCase):
    def test_as_at_an_origin(self):
        A, _ = synthetic()
        p = SB.panel_now(A, 2019)
        o = SB.origin_panel(A, 2019)['stats']
        for k in ('loss_kappa', 'loss_a', 'g_phi', 'g_res_sd', 'rho_gm', 'kappa'):
            self.assertEqual(p[k], o[k])
        self.assertEqual(p['year'], 2019)
        self.assertIn('every SEC filer', p['source'])
        self.assertIsNone(SB.panel_now({}, 2019))


class TestPieces(unittest.TestCase):
    def test_complete_year(self):
        A = {str(i): {'rev': {2023: 1.0, 2024: 1.0, **({2025: 1.0} if i < 50 else {})}} for i in range(100)}
        self.assertEqual(SB.complete_year(A, 2026), 2024)          # 2025 has half the companies: still coming in
        A = {str(i): {'rev': {2023: 1.0, 2024: 1.0, 2025: 1.0, 2026: 1.0}} for i in range(100)}
        self.assertEqual(SB.complete_year(A, 2026), 2025)          # the current year never counts

    def test_calibration(self):
        rows = [(0.9, True)] * 90 + [(0.9, False)] * 10 + [(0.1, False)] * 90 + [(0.1, True)] * 10
        c = SB.calibration(rows)
        self.assertEqual(c['n'], 200)
        self.assertAlmostEqual(c['base_rate'], 0.5)
        self.assertGreater(c['skill'], 0.5)
        self.assertEqual([b['n'] for b in c['bins']], [100, 100])
        flat = SB.calibration([(0.5, True), (0.5, False)] * 50)
        self.assertAlmostEqual(flat['skill'], 0.0)

    def test_balances(self):
        F = {('CashAndCashEquivalentsAtCarryingValue', 'CY2015Q4I'): {'1': 5.0, '2': [7.0, '2015-12-31']},
             ('LongTermDebt', 'CY2015Q4I'): {'1': 3.0, '3': float('nan')}}
        b = SB.balances(lambda c, p: F.get((c, p)), [2014, 2015])
        self.assertEqual(b['cash'], {'1': {2015: 5.0}, '2': {2015: 7.0}})
        self.assertEqual(b['debt'], {'1': {2015: 3.0}})

    def test_reuse(self):
        today = dt.date(2026, 11, 2)
        prev = {'version': SB.VERSION, 'last_year': 2025, 'generated_at': '2026-10-20T10:00:00+00:00'}
        self.assertIs(SB.reuse(prev, 2025, today), prev)
        self.assertIsNone(SB.reuse({**prev, 'generated_at': '2026-09-01T10:00:00+00:00'}, 2025, today))
        self.assertIsNone(SB.reuse({**prev, 'version': SB.VERSION + 1}, 2025, today))
        self.assertIsNone(SB.reuse(prev, 2026, today))
        self.assertIsNone(SB.reuse({}, 2025, today))

    def test_page_text(self):
        s = {'origins': [2013, 2019], 'regime_sd_scale': 1.5,
             'regime': {'coverage_3y': 0.68, 'below_3y': 0.18, 'above_3y': 0.14, 'n_3y': 2000},
             'regime_scaled': {'coverage_3y': 0.80, 'below_3y': 0.11, 'above_3y': 0.09, 'n_3y': 2000},
             'schwartz_moon': {'coverage_3y': 0.81, 'below_3y': 0.10, 'above_3y': 0.09, 'n_3y': 2000},
             'margin': {'coverage_3y': 0.71, 'n_3y': 400}, 'profit': {'skill_3y': 0.02, 'n_3y': 400}}
        r = SB.for_page(s, 'regime')
        self.assertIn('held 80%', r['text'])
        self.assertIn('× 1.5', r['text'])
        self.assertIn('68%', r['text'])
        m = SB.for_page(s, 'schwartz_moon')
        self.assertIn('about right', m['text'])
        self.assertIn('not scored yet', m['text'])
        self.assertIsNone(SB.for_page(None, 'regime'))
        r1 = SB.for_page({**s, 'regime_sd_scale': 1.0}, 'regime')
        self.assertIn('too narrow', r1['text'])
        self.assertNotIn('× 1', r1['text'])


class TestShrunkSpread(unittest.TestCase):
    def test_between_own_and_panel(self):
        gs = [0.05, 0.06, 0.04, 0.05, 0.07]
        own = MK._winsor_mean_sd(gs)[1]
        v, how = MK.shrunk_sd(gs, 0.2)
        self.assertEqual(how, 'shrunk')
        self.assertTrue(own < v < 0.2)
        self.assertAlmostEqual(v, math.sqrt((4 * own * own + 4 * 0.04) / 8))
        self.assertEqual(MK.shrunk_sd([0.1, 0.2], 0.2), (0.2, 'panel'))


if __name__ == '__main__':
    unittest.main()
