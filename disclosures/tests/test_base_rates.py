"""app/base_rates.py: peer groups and their fallbacks, base-rate probabilities, the reverse growth solver, stage rules,
the outside-view Monte Carlo, sensitivity, river charts, the walk-forward combined forecast (no look-ahead, conformal
coverage), the Rotation-ledger scoring and the full build with the outside view."""
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
import base_rates as BR  # noqa: E402
import valuation as V  # noqa: E402
import valuation_fixture as FX  # noqa: E402

BASE = {'rev0': 1000.0, 'years': 5, 'growth': 0.08, 'margin': 0.2, 'tax': 0.21, 'da': 0.03, 'capex': 0.04, 'wc': 0.1, 'wacc': 0.09, 'g': 0.025,
        'terminal': 'roic', 'roic': 0.15, 'debt': 200.0, 'cash': 100.0, 'claims': 0.0, 'nonop': 0.0, 'shares': 100.0}


def add_history(fx, years=range(2010, 2026), seed=11):
    """Annual revenue / operating income / net income frames since CY2010 for the fixture's companies, growing at a
    company-specific rate (so 3-, 5- and 10-year windows exist), and analysts' quarter estimates in the consensus files."""
    rng = random.Random(seed)
    root = Path(fx['root'])
    frames = {}
    for c in fx['companies']:
        cik = str(c['cik'])
        g = rng.uniform(-0.03, 0.15)
        m = rng.uniform(0.05, 0.3)
        r = c['revenue'] * 4 / (1 + g) ** (2026 - years[0])
        for y in years:
            r *= (1 + g) * (1 + rng.gauss(0, 0.03))
            mm = m + rng.gauss(0, 0.02)
            end = f'{y}-12-31'
            for concept, v in (('Revenues', r), ('OperatingIncomeLoss', r * mm), ('NetIncomeLoss', r * mm * 0.78)):
                frames.setdefault((concept, f'CY{y}'), {})
                frames[(concept, f'CY{y}')].setdefault(cik, [v, end])
    for (concept, period), vals in frames.items():
        p = V.frame_path(root, concept, period)
        old = V.read_json(p, {}) or {}
        V.write_json(p, {**vals, **old}, gz=True)
    cons = Path(fx['cons'])
    ix = json.loads((cons / 'index.json').read_text())
    F = ix['fields']
    for row in ix['rows']:
        cik = row[F.index('cik')]
        price = row[F.index('price')]
        p = cons / 'c' / f'{cik}.json'
        doc = json.loads(p.read_text())
        doc['analysts']['periods'] = [{'period': '0q', 'end': '2026-12-31', 'eps': {'avg': 1.10, 'yearAgoEps': 1.0, 'numberOfAnalysts': 9},
                                       'rev': {'avg': 1.05e9, 'yearAgoRevenue': 1.0e9}}]
        doc['snapshots'] = [[(dt.date(2025, 10, 1) + dt.timedelta(days=7 * k)).isoformat(), ['2026-12-31', 1.1, 1.05e9, 4.4, 4.2e9, price * 1.1, 2.0, price]]
                            for k in range(55)]
        p.write_text(json.dumps(doc))
        row[F.index('pm_eps_strike')] = 1.08
        row[F.index('pm_beat_prob')] = 0.62
        row[F.index('target_mean')] = price * 1.1
    (cons / 'index.json').write_text(json.dumps(ix))


class Distributions(unittest.TestCase):
    def test_groups_fallback_and_probability(self):
        D = BR.Dists()
        rng = random.Random(1)
        for c in range(6):                                          # SIC 357, size L: 6 companies × 10 windows
            for k in range(10):
                D.add('cagr5', rng.uniform(0.0, 0.2), '3571', 'L', 2020, f'a{c}')
        for c in range(3):                                          # SIC 367: too few companies, falls back to SIC 36
            for k in range(30):
                D.add('cagr5', 0.05, '3674', 'M', 2020, f'b{c}')
        for c in range(4):
            for k in range(10):
                D.add('cagr5', 0.10, '3663', 'M', 2024, f'c{c}')
        D.finish(cutoffs=[2022], cut_metrics=('cagr5',))
        k, xs = D.pick('cagr5', '3571', 'L')
        self.assertEqual(k, '357|L')
        self.assertEqual(len(xs), 60)
        self.assertEqual(D.pick('cagr5', '3674', 'M')[0], '36|M')   # 3 companies in 367 are not enough; SIC 36 × size has 7
        self.assertAlmostEqual(BR.share_at_least(array_of([0.1, 0.2, 0.3, 0.4]), 0.25), 0.5)
        self.assertEqual(BR.share_at_least(array_of([0.1, 0.2]), 0.2), 0.5)  # "at least": ties count
        cut = D.pick('cagr5', '3663', 'M', cutoff=2022)
        self.assertNotIn(0.10, set(cut[1]))                         # the 2024 windows are invisible before 2022
        self.assertEqual(BR.group_keys('3571', 'L'), ('357|L', '357', '35|L', '35', '*|L', '*'))
        self.assertEqual(BR.size_of(5e8), 'S')
        self.assertEqual(BR.size_of(6e10), 'XL')
        self.assertIn('revenue $10–50B', BR.key_label('357|L', {'357': 'Electronic Computers'}))

    def test_req_growth_and_inside_view(self):
        v = V.value(BASE)
        g, st = BR.req_growth(V, BASE, v)
        self.assertEqual(st, 'ok')
        self.assertAlmostEqual(g, 0.08, places=5)
        self.assertEqual(BR.req_growth(V, BASE, 1e9)[1], 'above')
        self.assertEqual(BR.req_growth(V, BASE, 0.01)[1], 'below')
        self.assertAlmostEqual(BR.norm_cdf(0), 0.5)

    def test_stage_rules(self):
        F = {'kind': 'industrial', 'sic': '7372', 'oi': 10.0, 'g0': 0.25, 'revenue': 1e9}
        flat = [0.2] * 12
        self.assertEqual(BR.stage_of(F, [], flat)[0], 'high_growth')
        self.assertEqual(BR.stage_of({**F, 'g0': 0.12}, [], flat)[0], 'growth')
        self.assertEqual(BR.stage_of({**F, 'g0': 0.03}, [], flat)[0], 'mature')
        self.assertEqual(BR.stage_of({**F, 'g0': 0.03, 'sic': '1311'}, [], flat)[0], 'cyclical')
        self.assertEqual(BR.stage_of({**F, 'g0': 0.03}, [], [0.05, 0.3] * 6)[0], 'cyclical')   # margin σ above 8 points
        self.assertEqual(BR.stage_of({**F, 'oi': -5.0, 'g0': 0.4}, [], flat)[0], 'pre_profit')
        self.assertEqual(BR.stage_of({**F, 'oi': -5.0, 'g0': 0.0}, [], flat)[0], 'decline')
        falling = [100 - k for k in range(16)]
        self.assertEqual(BR.stage_of({**F, 'g0': -0.05}, falling, flat)[0], 'decline')
        self.assertEqual(BR.stage_of({**F, 'kind': 'bank'}, [], flat)[0], 'financial')
        self.assertEqual(BR.stage_of({**F, 'oi': -5.0, 'revenue': 3e6}, [], flat)[0], 'pre_revenue')       # a pipeline, not a business yet
        self.assertEqual(BR.stage_of({**F, 'oi': -5.0, 'revenue': None}, [], flat)[0], 'pre_revenue')
        self.assertEqual(BR.stage_of({**F, 'revenue': 3e6}, [], flat)[0], 'high_growth')                   # small but profitable
        self.assertEqual(set(BR.STAGES), {'pre_revenue', 'pre_profit', 'high_growth', 'growth', 'mature', 'cyclical', 'decline', 'financial', 'reit'})
        for s in BR.STAGES.values():
            self.assertTrue(s['rule'] and s['methods'])

    def test_outside_mc_and_sensitivity(self):
        D = BR.Dists()
        rng = random.Random(2)
        for c in range(8):
            for k in range(10):
                g = rng.gauss(0.06, 0.05)
                D.add('cagr5', g, '3571', 'L', 2020, c)
                D.add_pair('cagr5_dm5', g, rng.gauss(0, 0.02), '3571', 'L', c)
                D.add('cagr10', rng.uniform(0.0, 0.06), '3571', 'L', 2020, c)
            D.add('wacc', 0.085 + 0.002 * c, '3571', 'L', 2026, c)
            D.add('wacc', 0.09, '3571', 'L', 2026, c + 100)
        D.finish()
        mc = BR.outside_mc(V, BASE, V.value(BASE), D, '3571', 'L', n=500, seed=1)
        self.assertTrue(mc['p10'] < mc['p50'] < mc['p90'])
        self.assertEqual(len(mc['_vals']), mc['n'])
        self.assertTrue(0 < mc['p_above'] < 1)
        self.assertEqual(mc['groups']['growth_margin'], '357|L')
        out = {'football': [], 'notes': []}
        s = BR.sensitivity(V, {'shares': 100.0, 'price': 10.0, 'sic': '3571', 'revenue': 2e10}, BASE, {'wacc': 0.09}, out, D, {})
        self.assertEqual(len(s['grid_growth_wacc']['values']), 5)
        self.assertAlmostEqual(s['grid_growth_wacc']['values'][2][2], round(V.value(BASE), 2), places=2)   # the centre is the base case
        swings = [b['swing'] for b in s['tornado']]
        self.assertEqual(swings, sorted(swings, reverse=True))
        self.assertGreater(s['grid_growth_wacc']['values'][4][0], s['grid_growth_wacc']['values'][0][4])  # more growth + lower WACC = more value

    def test_river_and_levels(self):
        periods = V.calendar_quarters(V.QUARTERS, FX.TODAY)
        days = FX.business_days(dt.date(2022, 6, 1), dt.date(2026, 10, 16))
        daily = [(d, 100.0) for d in days]
        n = len(periods)
        rec = {'q': {'eps': [1.0] * n, 'rev': [1e9] * n, 'oi': [2e8] * n, 'sh': [1e8] * n}, 'eq_q': [5e9] * n}
        F = {'revenue': 4e9, 'da': 4e8, 'debt': 1e9, 'cash': 0.0, 'claims': 0.0, 'shares': 1e8}
        r = BR.river(V, daily, periods, rec, F)
        self.assertAlmostEqual(r['metrics']['pe']['current'], 25.0)          # $100 on four quarters of $1
        self.assertAlmostEqual(r['metrics']['ps']['current'], 2.5)           # $100 on $40 of sales a share
        self.assertAlmostEqual(r['metrics']['pb']['current'], 2.0)
        self.assertAlmostEqual(r['metrics']['ev_ebitda']['current'], (100 + 10) / 12, places=2)   # EBITDA = 8e8 + 4e8 ⇒ $12 a share
        self.assertEqual(r['weeks'][0], r['from'])
        lv = BR.nice_levels(11.3, 38.7)
        self.assertEqual(len(lv), 5)
        self.assertTrue(lv[0] <= 11.3 and lv[-1] >= 30)

    def test_ridge_and_walk_forward(self):
        w = BR.ridge([[1, x] for x in range(20)], [3 + 2 * x for x in range(20)], 0.0)
        self.assertAlmostEqual(w[0], 3.0, places=6)
        self.assertAlmostEqual(w[1], 2.0, places=6)
        rng = random.Random(4)
        rows = []
        for q in range(16):
            T = (dt.date(2022, 9, 1) + dt.timedelta(days=91 * q)).isoformat()
            for c in range(60):
                s = rng.gauss(0, 1)
                rows.append({'cik': str(c), 'date': T, 'x': {'pe_gap': s, 'dcf_gap': rng.gauss(0, 1)}, 'fwd': {'3m': 0.05 * s + rng.gauss(0, 0.1)}})
        scores, fic, oos, res = BR.walk_forward(rows, '3m')
        c, z = scores['combined'], scores['zero']
        self.assertLess(c['mae'], z['mae'])                                   # a real signal beats "no change"
        self.assertGreater(fic['pe_gap']['ic_mean'], 0.2)
        self.assertLess(abs(fic['dcf_gap']['ic_mean']), 0.15)
        self.assertTrue(0.7 <= c['coverage80'] <= 0.9, c['coverage80'])        # conformal 80% holds roughly 80%
        first = min(x[0] for x in res['combined'])
        self.assertGreater(first, rows[0]['date'])                            # the first origins only train
        noise = [{**r, 'fwd': {'3m': rng.gauss(0, 0.1)}} for r in rows]
        sc2 = BR.walk_forward(noise, '3m')[0]
        self.assertGreater(sc2['combined']['mae'], 0.9 * sc2['zero']['mae'])    # no signal: no real gain


class Rotation(unittest.TestCase):
    def test_score_and_pair(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ff = ['close', 'price', 'lo80', 'hi80', 'rel_next', 'model', 'forecast_change_pct', 'actual_change_pct', 'gap_pts', 'inside80',
                  'direction_right', 'actual_close']
            rows = {'2025-06-30': {'AAA': [100, 103, 90, 115, 0.0, 'g', 3.0, 5.0, 2.0, True, True, 105],
                                   'BBB': [50, 49, 45, 55, 0.0, 'g', -2.0, 8.0, 10.0, False, False, 54]}}
            (root / 'forecast-ledger-q.json').write_text(json.dumps({'fields': ff, 'rows': rows}))
            (root / 'forecast-ledger.json').write_text(json.dumps({'freqs': {'q': {'origins': [{'origin': '2025-06-30', 'source': 'backtest'}]}}}))
            paired = []
            s = BR.score_rotation(root, V.read_json, paired, {'AAA': '1', 'BBB': '2'})
            b = s['next quarter']['backtest']
            self.assertEqual(b['n'], 2)
            self.assertAlmostEqual(b['mae_pts'], 6.0)
            self.assertAlmostEqual(b['naive_mae_pts'], 6.5)
            self.assertAlmostEqual(b['coverage80'], 0.5)
            pc = BR.pair_with_combined(paired, {('1', '2025-07-10'): 0.04, ('2', '2025-07-10'): 0.0})
            self.assertEqual(pc['n'], 2)
            self.assertAlmostEqual(pc['mae_rotation'], (0.02 + 0.10) / 2)
            self.assertAlmostEqual(pc['mae_combined'], (0.01 + 0.08) / 2)
            self.assertIsNone(BR.score_rotation(None, V.read_json))


class Build(unittest.TestCase):
    def test_build_with_outside_view(self):
        with tempfile.TemporaryDirectory() as d:
            fx = FX.make(d)
            add_history(fx)
            st = V.build(fx['root'], fx['prices'], fx['debt'], fx['cons'], today=FX.TODAY, verbose=False)
            self.assertGreater(st['base_rate_windows'], 300)
            self.assertEqual(st['with_stage'], st['companies'])
            self.assertGreaterEqual(st['with_outside_mc'], 25)
            pub = Path(fx['root']) / 'public'
            ix = json.loads((pub / 'index.json').read_text())
            rows = [dict(zip(ix['fields'], r)) for r in ix['rows']]
            ind = next(r for r in rows if r['cik'] == 100000)
            self.assertTrue(0 <= ind['p_implied'] <= 1 and ind['peer_group'])
            self.assertAlmostEqual(ind['req_eps_g'], 0.10, places=6)                # 1.10 vs a year-ago 1.00
            self.assertAlmostEqual(ind['pm_req_eps_g'], 0.08, places=6)
            self.assertAlmostEqual(ind['pm_beat_prob'], 0.62)
            self.assertTrue(0 <= ind['p_street_eps'] <= 1 and 0 <= ind['p_pm_eps_base'] <= 1)
            self.assertGreaterEqual(ind['p_pm_eps_base'], ind['p_street_eps'])     # a lower bar is cleared at least as often
            self.assertTrue(ind['ov_p10'] < ind['ov_mean'] < ind['ov_p90'] * 1.5)
            doc = json.loads((pub / 'c' / '100000.json').read_text())
            co = doc['consensus_odds']
            self.assertEqual(set(co) >= {'market', 'street_eps', 'street_rev', 'street_target', 'pm_eps', 'pm_price'}, True, set(co))
            self.assertLess(co['street_target']['p_outside'], co['market']['p_outside'] + 1e-9)    # a target above the price needs more growth
            tiles = doc['base_rates']['tiles']
            self.assertTrue(all('price' in t and 'p' in t for t in tiles))
            self.assertTrue(any(t['basis'] == 'growth' for t in tiles))
            by = {t['method']: t for t in tiles}
            hi, lo = max(tiles, key=lambda t: t['price']), min(tiles, key=lambda t: t['price'])
            if hi['basis'] == lo['basis'] == 'growth' and hi['p'] is not None and lo['p'] is not None:
                self.assertLessEqual(hi['p'], lo['p'])                            # a higher price is reached by fewer peers
            self.assertIn('Outside view — base-rate Monte Carlo', by)
            self.assertTrue(doc['stage']['stage'] in BR.STAGES and doc['stage'].get('value'))
            self.assertTrue(any(b['method'].startswith('Stage-weighted value') for b in doc['football']))
            self.assertTrue(doc['sensitivity']['tornado'] and doc['sensitivity']['grid_margin_multiple']['values'])
            self.assertTrue(set(doc['river']['metrics']) >= {'pe', 'ps'})
            rv = doc['river']
            self.assertEqual(len(rv['weeks']), len(rv['step']))
            self.assertEqual(len(rv['steps']['from']), len(rv['steps']['pe']))
            self.assertTrue(all(rv['steps']['from'][j] <= w for w, j in zip(rv['weeks'], rv['step'])))   # a figure is used only once known
            ov = doc['outside_view']
            self.assertTrue(any(r['metric'] == 'cagr5' and r['outside'] for r in ov['rows']))
            self.assertTrue(ov['mc'] and ov['inside_mc'])
            self.assertIn('Combined forecast (3 months)', {b['method'] for b in doc['football']})
            self.assertIn('Our model (Rotation forecast)', {b['method'] for b in doc['football']})   # not replaced without a paired win
            bank = next(r for r in rows if r['kind'] == 'bank')
            bdoc = json.loads((pub / 'c' / f"{bank['cik']}.json").read_text())
            self.assertEqual(bdoc['stage']['stage'], 'financial')
            self.assertEqual(bdoc['sensitivity']['method'], 'Residual income')
            m = json.loads((pub / 'models.json').read_text())
            sc = m['combined']['horizons']['3m']['scores']
            self.assertTrue({'combined', 'zero', 'drift'} <= set(sc))
            self.assertIn('target_gap', m['combined']['horizons']['3m']['weights'])
            self.assertTrue(m['verdict'])
            brj = json.loads((pub / 'base_rates.json').read_text())
            self.assertIn('cagr5', brj['groups'])
            self.assertTrue(all('|' not in k or k.startswith('*|') for k in brj['groups']['cagr5']))
            led = json.loads((Path(fx['root']) / 'cache' / 'ledger' / '2026-10.json').read_text())
            self.assertEqual(led['fields'][:4], ['price', 'dcf_value', 'mc_p_above', 'distress_pd'])
            self.assertEqual(len(next(iter(led['rows'].values()))), len(led['fields']))


def array_of(xs):
    from array import array
    return array('d', sorted(xs))


if __name__ == '__main__':
    unittest.main()
