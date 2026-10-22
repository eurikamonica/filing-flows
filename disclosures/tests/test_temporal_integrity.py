"""Truncation invariance of the Rotation inputs (research spec v5 §1.1, §17.1): a sector sun, the market centre, a
weekly site-sector index and the analogue forecasts built on them at period t never change when data after t change —
later outliers, later revenue figures, later prices."""
import copy
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import rotation as ROT
import rotation_history as RH

try:
    import numpy as np
    import sklearn  # noqa: F401
    import chaos_forecast as CF
except ImportError:
    np = None

CALS = [f'CY{2020 + i // 4}Q{i % 4 + 1}' for i in range(10)]


def companies(n=12):
    """Twelve companies with two variables, quarterly revenue in their figures, and points for every quarter."""
    out, figs = [], {}
    for i in range(n):
        fig = {c: {'rev': 1e9 * (1 + i) * (1 + 0.05 * k)} for k, c in enumerate(['CY2019Q4'] + CALS)}
        figs[str(i)] = fig
        out.append({'t': f'T{i}', 'cik': i, 's': 'a' if i % 2 else 'b', 'rev': fig[CALS[-1]]['rev'],
                    'pts': [{'cal': c, 'rel': math.sin(i + k) * 10, 'dom': (i - k) * 0.5, 'rev': fig[c]['rev']} for k, c in enumerate(CALS)]})
    out[0]['pts'][2]['rel'] = 100.0                          # an early outlier: clipped, by bounds known then
    return out, figs


def suns(cos, figs):
    cos = copy.deepcopy(cos)
    for co in cos:
        for p in co['pts']:
            p['_w'] = ROT.known_revenue(figs.get(str(co['cik'])), p['cal'])
    b = ROT.asof_bounds(cos, ['rel', 'dom'])
    return ROT.centre(cos, ['rel', 'dom'], b, 99)


class RotationSuns(unittest.TestCase):
    def test_a_later_outlier_or_revenue_never_moves_a_past_sun(self):
        cos, figs = companies()
        before = suns(cos, figs)
        cos2, figs2 = copy.deepcopy(cos), copy.deepcopy(figs)
        for co in cos2:                                       # the last two quarters change wildly
            for p in co['pts'][-2:]:
                p['rel'] *= 50; p['dom'] -= 400
        for f in figs2.values():
            for c in CALS[-2:]:
                f[c]['rev'] *= 1000
        after = suns(cos2, figs2)
        self.assertEqual(before[:-2], after[:-2])
        self.assertNotEqual(before[-1], after[-1])

    def test_weights_use_the_revenue_reported_by_then(self):
        fig = {'CY2020Q1': {'rev': 5.0}, 'CY2020Q2': {'rev': 7.0}}
        self.assertEqual(ROT.known_revenue(fig, 'CY2020Q3'), 7.0)          # Q2's revenue, filed during Q3
        self.assertEqual(ROT.known_revenue(fig, 'CY2020Q2'), 5.0)          # Q2's own revenue is not public yet
        self.assertIsNone(ROT.known_revenue(fig, 'CY2020Q1'))
        self.assertEqual(ROT._prev_cal('CY2021Q1'), 'CY2020Q4')

    def test_latest_bounds_are_the_pooled_ones(self):
        cos, _ = companies()
        b = ROT.asof_bounds(cos, ['rel'])
        vals = [p['rel'] for c in cos for p in c['pts']]
        self.assertEqual(b['rel'][CALS[-1]], (ROT._quantile(vals, .03), ROT._quantile(vals, .97)))


class RotationBuildSmoke(unittest.TestCase):
    """rotation.build end to end on a tiny synthetic site (index, SEC frames, daily closes): the as-of suns run."""

    def test_build(self):
        import datetime as dt, gzip, json, tempfile
        import frames as FR
        with tempfile.TemporaryDirectory() as tmp:
            site, root = Path(tmp) / 'site', Path(tmp) / 'root'
            site.mkdir(); (root / 'cache' / 'frames').mkdir(parents=True)
            cos = [{'cik': i, 'ticker': f'T{i}', 'name': f'Co {i}', 'sector': 'tech' if i % 2 else 'health',
                    'revenue': 1e9 * i, 'filed': '2026-08-01'} for i in range(1, 9)]
            (site / 'index.json').write_text(json.dumps({'companies': cos, 'sector_names': {'tech': 'Tech', 'health': 'Health'}}))
            periods = FR.calendar_quarters(8 + 5)
            for k, per in enumerate(periods):
                for concept, f in (('Revenues', 1.0), ('OperatingIncomeLoss', 0.2)):
                    with gzip.open(FR.path_for(root, concept, per), 'wt') as fh:
                        json.dump({str(c['cik']): c['revenue'] * f * (1 + 0.03 * k) for c in cos}, fh)
            day0 = dt.date.today() - dt.timedelta(days=1400)
            def prices(t):
                g = 1.0003 + (int(t[1:]) if t[1:].isdigit() else 0) * 1e-5
                return [[(day0 + dt.timedelta(days=i)).isoformat(), 100 * g ** i, 1000 + i % 7] for i in range(1400)
                        if (day0 + dt.timedelta(days=i)).weekday() < 5]
            rot = ROT.build(site, root, top=8, quarters=8, months=12, prices=prices)
        self.assertEqual(len(rot['companies']), 8)
        self.assertEqual(set(rot['sectors']), {'tech', 'health'})
        rows = rot['market']['p']
        self.assertGreaterEqual(len(rows), 3)
        self.assertTrue(all(r[0].startswith('CY') for r in rows))
        self.assertIn('reported by then', rot['note'])


class SectorIndices(unittest.TestCase):
    def test_revenue_history_from_frames(self):
        import gzip, json, tempfile
        import frames as FR
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'cache' / 'frames').mkdir(parents=True)
            with gzip.open(FR.path_for(tmp, 'Revenues', 'CY2024Q4'), 'wt') as fh:
                json.dump({'7': 5e9}, fh)
            h = RH.revenue_history(tmp, [{'t': 'AAA', 'cik': 7}, {'t': 'BBB', 'cik': 8}], since='CY2024Q1')
        self.assertEqual(h, {'AAA': (['2025-02-15'], [5e9])})           # Dec 31 + 46 days

    def test_later_revenue_never_moves_an_earlier_week(self):
        weeks = [f'2021-{m:02d}-{d:02d}' for m in range(1, 13) for d in (1, 15)]
        cos = [{'t': f'T{i}', 's': 'tech', 'rev': 1e9} for i in range(4)]
        series = {f'T{i}': (0, [100 * (1 + 0.01 * (i + 1)) ** k for k in range(len(weeks))]) for i in range(4)}
        hist = {f'T{i}': (['2021-03-01', '2021-08-01'], [1e8 * (i + 1), 2e8 * (i + 1)]) for i in range(4)}
        a = RH.sector_indices(cos, series, weeks, hist)['tech'][1]
        hist2 = {t: (d, [v[0], v[1] * 1e4]) for t, (d, v) in hist.items()}  # the second revenue figure changes
        b = RH.sector_indices(cos, series, weeks, hist2)['tech'][1]
        k = weeks.index('2021-08-01')                                    # levels start at week 1
        self.assertEqual(a[:k - 1], b[:k - 1])
        self.assertNotEqual(a[-1], b[-1])


class IndustryBenchmarks(unittest.TestCase):
    """rotation_history.industry_benchmarks: the most specific SIC level with five other members, a leave-one-out index
    ('ex') that a company's own price never moves, and the full index ('all')."""

    def world(self, bump=False):
        weeks = [f'2021-{m:02d}-{d:02d}' for m in range(1, 13) for d in (1, 8, 15, 22)]
        cos = [{'t': f'S{i}', 's': 'technology', 'sic': '3674', 'ind': 'Semiconductors', 'rev': 1e9} for i in range(7)]
        cos += [{'t': f'P{i}', 's': 'health', 'sic': '2834', 'ind': 'Pharma', 'rev': 1e9} for i in range(2)]
        cos += [{'t': f'H{i}', 's': 'health', 'sic': '8062', 'ind': 'Hospitals', 'rev': 1e9} for i in range(5)]
        series = {}
        for k, c in enumerate(cos):
            series[c['t']] = (0, [100 * (1 + 0.002 * (k + 1)) ** j for j in range(len(weeks))])
        if bump:
            f, cl = series['S0']; series['S0'] = (f, [x * (1.5 if j > 20 else 1) for j, x in enumerate(cl)])
        return cos, series, weeks

    def test_levels_and_leave_one_out(self):
        cos, series, weeks = self.world()
        b = RH.industry_benchmarks(cos, series, weeks)
        self.assertEqual((b['S0']['level'], b['S0']['code'], b['S0']['members']), ('sic4', '3674', 7))
        self.assertEqual(b['S0']['label'], 'SIC 3674 · Semiconductors')
        self.assertEqual(b['P0']['level'], 'sector')                    # 2834 and 28 have one other member; health has 6
        self.assertNotIn('P0', [k for k, v in b.items() if v['level'] == 'sic4'])
        cos2, series2, _ = self.world(bump=True)
        b2 = RH.industry_benchmarks(cos2, series2, weeks)
        self.assertEqual(b['S0']['ex'], b2['S0']['ex'])                  # its own jump never moves its benchmark
        self.assertNotEqual(b['S1']['ex'], b2['S1']['ex'])               # but it moves its peers'
        self.assertNotEqual(b['S0']['all'], b2['S0']['all'])
        # liquidity: a member trading under $10M a week never moves the others' benchmark
        vols = {c['t']: [1e6] * len(weeks) for c in cos}               # $100+ × 1M shares: liquid
        vols['S6'] = [10.0] * len(weeks)                                 # illiquid
        b3 = RH.industry_benchmarks(cos, series, weeks, volumes=vols)
        cos4, series4, _ = self.world()
        f, cl = series4['S6']; series4['S6'] = (f, [x * (3 if j > 20 else 1) for j, x in enumerate(cl)])
        b4 = RH.industry_benchmarks(cos4, series4, weeks, volumes=vols)
        self.assertEqual(b3['S0']['ex'], b4['S0']['ex'])
        self.assertNotEqual(b['S0']['ex'][-1], b3['S0']['ex'][-1])
        # equal weights: the leave-one-out week-1 return is the mean of the others' returns
        others = [math.log(1 + 0.002 * (k + 1)) for k in range(1, 7)]
        self.assertAlmostEqual(math.log(b['S0']['ex'][1] / 100), sum(others) / 6, places=4)


@unittest.skipIf(np is None, 'numpy / scikit-learn not installed')
class ChaosCentres(unittest.TestCase):
    def test_weighted_centre_is_causal(self):
        rng = np.random.default_rng(4)
        U = rng.normal(0, 1, (30, 20, 2))
        W = np.full((30, 20), 1e9)
        a = CF.weighted_centre(U, W, ['x', 'y'])
        U2, W2 = U.copy(), W.copy()
        U2[:, 12:] *= 40; W2[:, 12:] = rng.uniform(1e6, 1e12, (30, 8))
        b = CF.weighted_centre(U2, W2, ['x', 'y'])
        np.testing.assert_array_equal(a[:12], b[:12])

    def test_known_revenue_by_month(self):
        class Q:
            cals = ['CY2020Q1', 'CY2020Q2', 'CY2020Q3']
            tickers = ['A']
            meta = {'A': {'rev': 99.0}}
            rev = np.array([[10.0, 20.0, 30.0]])
        r = CF.known_rev_monthly(Q, ['A'], ['2020-04', '2020-05', '2020-07', '2020-08'])
        # Q1 (Mar 31) counts from May 16; Q2 (Jun 30) from Aug 15
        np.testing.assert_array_equal(r[0], [np.nan, 10.0, 10.0, 20.0])
        np.testing.assert_array_equal(CF.known_rev_quarterly(Q)[0], [np.nan, 10.0, 20.0])

    def test_forecasts_ignore_the_future_with_centres_rebuilt(self):
        """The existing NoLookAhead test edits SUN/MKT directly; here the centres are rebuilt from the changed companies
        the way load_monthly builds them, and the forecasts at t must not move."""
        rng = np.random.default_rng(0)
        E, T = 40, 36
        vars_ = ['rel', 'vola', 'dom']
        U = np.full((E, T, 3), np.nan)
        th = rng.uniform(0, 2 * np.pi, E); r = rng.uniform(1, 3, E)
        for t in range(T):
            th += 0.6; r = 0.9 * r + 0.3 + rng.normal(0, .1, E)
            U[:, t, 0] = r * np.cos(th) + rng.normal(0, .3, E)
            U[:, t, 1] = 20 + r * np.sin(th) + rng.normal(0, .3, E)
            U[:, t, 2] = np.sin(th + .5) + rng.normal(0, .2, E)
        W = np.full((E, T), 1e9) * (1 + np.arange(E))[:, None]
        cals = [f'CY{2010 + i // 4}Q{i % 4 + 1}' for i in range(T)]
        tickers = [f'T{i}' for i in range(E)]
        meta = {t: {'s': 'a' if i % 2 else 'b', 'rev': 1e9, 'n': t} for i, t in enumerate(tickers)}

        def panel(U, W):
            SUN = np.stack([CF.weighted_centre(U[[i for i in range(E) if meta[tickers[i]]['s'] == s]],
                                               W[[i for i in range(E) if meta[tickers[i]]['s'] == s]], vars_) for s in ('a', 'b')])
            MKT = CF.weighted_centre(U, W, vars_)
            return CF.Panel('q', cals, vars_, tickers, meta, ['a', 'b'], {'a': 'A', 'b': 'B'}, U, SUN, MKT)
        t0 = 24
        R1 = CF.run_panel(panel(U, W), ['rel', 'vola'], vars_, 16, m=2, k=20, surrogate=False, verbose=False)
        U2, W2 = U.copy(), W.copy()
        U2[:, t0 + 1:] = U2[:, t0 + 1:] * 25 + 7                        # a different future, outliers included
        W2[:, t0 + 1:] = rng.uniform(1e6, 1e13, (E, T - t0 - 1))
        R2 = CF.run_panel(panel(U2, W2), ['rel', 'vola'], vars_, 16, m=2, k=20, surrogate=False, verbose=False)
        r1 = next(r for r in R1['recs'] if r['t'] == t0)
        r2 = next(r for r in R2['recs'] if r['t'] == t0)
        for key in ('dP_cal', 'dS_cal'):
            np.testing.assert_allclose(r1[key], r2[key], equal_nan=True, err_msg=key)
        np.testing.assert_allclose(r1['fp']['delta'], r2['fp']['delta'], equal_nan=True)


if __name__ == '__main__':
    unittest.main()
