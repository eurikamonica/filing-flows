"""quality.py: the scores on hand-checked companies, the panel from frames, the walk-forward factor test, the frozen
monthly ledger and the published files."""
import datetime as dt
import gzip
import json
import math
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import quality as Q  # noqa: E402

TODAY = dt.date(2026, 10, 19)
M = 1e6


def gz(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, 'wt', encoding='utf-8') as f:
        json.dump(obj, f)


def good_years():
    """A company that passes all nine Piotroski checks in FY2025 (figures in $M)."""
    base = dict(rev=800, gp=320, oi=60, ni=60, ocf=90, capex=40, da=30, sbc=10, buyback=20, div=10, issue=0, interest=15, tax=15,
                pretax=75, sga=150, dil=100e6, assets=1000, ca=380, cl=300, liab=600, eq=400, re=200, cash=100, ltd=320, ar=80, ppe=300)
    y24 = dict(base, rev=900, gp=360, ni=80, ocf=110, assets=1000, ca=400, cl=300, ltd=300, dil=100e6)
    y25 = dict(base, rev=1000, gp=420, oi=130, ni=100, ocf=150, assets=1050, ca=450, cl=300, ltd=250, dil=98e6, ar=90)
    return {2023: base, 2024: y24, 2025: y25}


class Scores(unittest.TestCase):
    def test_piotroski_all_nine(self):
        ys = good_years()
        f = Q.piotroski(ys[2025], ys[2024], ys[2023])
        self.assertEqual((f['score'], f['n']), (9, 9), [s for s in f['signals'] if not s['pass']])
        worse = dict(ys[2025], dil=105e6, ocf=50)                       # new shares; cash flow below net income
        f2 = Q.piotroski(worse, ys[2024], ys[2023])
        self.assertEqual(f2['score'], 7)
        self.assertEqual({s['key'] for s in f2['signals'] if not s['pass']}, {'shares', 'accrual'})

    def test_altman_models_and_zones(self):
        cur = dict(assets=1000, liab=950, ca=100, cl=300, re=-500, oi=-50, eq=50, rev=400)
        z = Q.altman(cur, None, manufacturer=False)
        self.assertEqual((z['model'], z['zone']), ("Z''", 'distress'))
        self.assertAlmostEqual(z['z'], 6.56 * -0.2 + 3.26 * -0.5 + 6.72 * -0.05 + 1.05 * 50 / 950, places=2)
        good = dict(assets=1000, liab=400, ca=500, cl=200, re=400, oi=150, eq=600, rev=1200)
        z = Q.altman(good, 2000, manufacturer=True)
        self.assertEqual(z['model'], 'Z')
        self.assertAlmostEqual(z['z'], 1.2 * .3 + 1.4 * .4 + 3.3 * .15 + 0.6 * 5 + 1.0 * 1.2, places=2)
        self.assertEqual(z['zone'], 'safe')

    def test_beneish_flag_and_neutral_indices(self):
        prev = dict(ar=50, rev=500, gp=200, assets=900, ca=300, ppe=300, ni=40, ocf=60, cl=200, ltd=200, da=30, sga=80)
        cur = dict(ar=200, rev=800, gp=320, assets=1000, ca=350, ppe=320, ni=100, ocf=-50, cl=220, ltd=200, da=32, sga=120)
        b = Q.beneish(cur, prev)
        self.assertTrue(b['flag'])
        self.assertAlmostEqual(b['idx']['dsri'], 2.5, places=3)
        self.assertAlmostEqual(b['idx']['tata'], 0.15, places=3)
        b2 = Q.beneish(dict(cur, sga=None, da=None, ar=55, ni=60, ocf=90), prev)
        self.assertEqual(b2['neutral'], ['depi', 'sgai'])
        self.assertFalse(b2['flag'])
        self.assertIsNone(Q.beneish(dict(cur, ar=None), prev))
        no_ni = {k: v for k, v in cur.items() if k != 'ni'}             # a year without net income tagged: no score
        self.assertIsNone(Q.beneish(no_ni, prev))
        self.assertIsNotNone(Q.beneish(dict(cur, ni=0), prev))           # zero net income is a figure

    def test_yields_owner_earnings_roic_cost_structure(self):
        ys = good_years()
        y = Q.yields(ys[2025], 2000)
        self.assertAlmostEqual(y['sy'], (10 + 20 - 0) / 2000)
        self.assertAlmostEqual(y['fcf_y'], (150 - 40) / 2000)
        self.assertAlmostEqual(y['fcf_sbc_y'], (150 - 40 - 10) / 2000)
        oe = Q.owner_earnings([ys[2023], ys[2024], ys[2025]])
        ppe_s = (300 / 800 + 300 / 900 + 300 / 1000) / 3
        self.assertAlmostEqual(oe['growth_capex'], ppe_s * 100)
        self.assertAlmostEqual(oe['oe'], 100 + 30 - (40 - ppe_s * 100))
        r = Q.roic([ys[2023], ys[2024], ys[2025]])
        nopat = 130 * (1 - 15 / 75)
        self.assertAlmostEqual(r['roic'], round(nopat / (((400 + 250 - 100) + (400 + 300 - 100)) / 2), 4))
        qs = [{'rev': rv, 'oi': rv - (50 + 0.6 * rv)} for rv in (200, 210, 230, 220, 240, 260, 250, 270, 290)]
        cs = Q.cost_structure(qs)
        self.assertAlmostEqual(cs['fixed_q'], 50, places=6)
        self.assertAlmostEqual(cs['var_ratio'], 0.6, places=4)
        self.assertAlmostEqual(cs['dol'], 290 * 0.4 / (290 - 50 - 0.6 * 290), places=2)
        self.assertTrue(cs['reliable'])

    def test_growth_line_and_spearman(self):
        pts = [{'t': f'T{i}', 'ev_s': math.exp(0.5 + 0.02 * x), 'r40': x} for i, x in enumerate(range(0, 60, 6))]
        pts[3]['ev_s'] /= 2                                            # one company at half its peers' multiple
        fit = Q.growth_line(pts)
        self.assertGreater(fit['b'], 0.015)
        cheapest = min(pts, key=lambda p: p['resid'])
        self.assertEqual(cheapest['t'], 'T3')
        self.assertAlmostEqual(Q.spearman(list(range(20)), [x * x for x in range(20)]), 1.0)


def world(root, n=60, seed=7):
    """A small market: n companies (two of them hand-built: GOOD passes Piotroski 9/9, BAD sits in Altman's distress
    zone), hub frames, quality frames, prices, tickers and the site index."""
    rnd = random.Random(seed)
    hub = root / 'hub'
    rq = root / 'rq'
    prices = root / 'prices'
    tick_rows, site = [], []
    comps = {}
    for i in range(n):
        cik = str(1000 + i)
        t = 'GOOD' if i == 0 else 'BAD' if i == 1 else f'C{i:02d}'
        sector = 'technology' if i % 2 == 0 else 'industrials'
        sic = 3674 if i % 2 == 0 else 7372
        if t == 'BAD':
            sic = 7372
        tick_rows.append({'ticker': t, 'cik': int(cik), 'title': f'{t} CORP'})
        site.append({'cik': int(cik), 'ticker': t, 'name': f'{t} Corp', 'sector': sector, 'sic': str(sic)})
        if t == 'GOOD':
            years = {y: {k: (v * M if k != 'dil' else v) for k, v in d.items()} for y, d in good_years().items()}
            years[2022] = years[2023]
        else:
            rev0 = rnd.uniform(400, 3000) * M
            g = rnd.uniform(-0.1, 0.4)
            years = {}
            for y in range(2021, 2026):
                rev = rev0 * (1 + g) ** (y - 2021)
                assets = rev * rnd.uniform(0.8, 1.6)
                d = dict(rev=rev, gp=rev * rnd.uniform(0.2, 0.7), oi=rev * rnd.uniform(-0.05, 0.3), ocf=rev * rnd.uniform(0.0, 0.3),
                         capex=rev * rnd.uniform(0.02, 0.1), da=rev * 0.04, sbc=rev * rnd.uniform(0, 0.08),
                         buyback=rev * rnd.uniform(0, 0.08), div=rev * rnd.uniform(0, 0.04), issue=rev * rnd.uniform(0, 0.02),
                         interest=rev * 0.01, tax=rev * 0.03, pretax=rev * 0.15, sga=rev * 0.2, dil=rnd.uniform(50, 200) * M,
                         assets=assets, ca=assets * 0.4, cl=assets * rnd.uniform(0.15, 0.35), eq=assets * 0.45, re=assets * 0.2,
                         cash=assets * 0.1, ltd=assets * rnd.uniform(0.1, 0.4), ar=rev * rnd.uniform(0.08, 0.2), ppe=assets * 0.3)
                d['ni'] = d['oi'] * 0.8
                d['liab'] = d['assets'] - d['eq']
                years[y] = d
            if t == 'BAD':
                years[2025].update(assets=1000 * M, liab=950 * M, ca=100 * M, cl=300 * M, re=-500 * M, oi=-50 * M, eq=50 * M, ni=-60 * M)
        comps[cik] = (t, years, sector)
    for cik, (t, years, sector) in comps.items():
        fixed, var = rnd.uniform(20, 80) * M, rnd.uniform(0.4, 0.8)
        for y, d in years.items():
            end = f'{y}-12-31'
            for concept, key in (('Revenues', 'rev'), ('GrossProfit', 'gp'), ('OperatingIncomeLoss', 'oi'), ('NetIncomeLoss', 'ni')):
                p = hub / 'cache' / 'frames' / f'{concept}-CY{y}.json.gz'
                cur = json.load(gzip.open(p)) if p.exists() else {}
                cur[cik] = [d[key], end]
                gz(p, cur)
            for field, specs in Q.ANNUAL:
                tax, concept, unit = specs[0]
                if d.get(field) is None:
                    continue
                p = Q._qpath(rq, tax, concept, unit, f'CY{y}')
                cur = json.load(gzip.open(p)) if p.exists() else {}
                cur[cik] = [d[field], end]
                gz(p, cur)
            for field, specs in Q.INSTANT:
                tax, concept, unit = specs[0]
                v = d.get('dil') if field == 'so' else d.get(field)
                if v is None:
                    continue
                p = Q._qpath(rq, tax, concept, unit, f'CY{y}Q4I')
                cur = json.load(gzip.open(p)) if p.exists() else {}
                cur[cik] = v
                gz(p, cur)
        # quarters CY2021Q4 … CY2026Q3: operating cost = fixed + var × revenue (so the split is recoverable)
        r0 = years[min(years)]['rev'] / 4
        k = 0
        for y in range(2021, 2027):
            for q in range(1, 5):
                if (y, q) < (2021, 4) or (y, q) > (2026, 3):
                    continue
                rev = r0 * (1.02 ** k) * (1 + 0.03 * ((q % 2) - 0.5))
                k += 1
                vals = {'Revenues': rev, 'GrossProfit': rev * 0.45, 'OperatingIncomeLoss': rev - (fixed + var * rev), 'NetIncomeLoss': rev * 0.05}
                for concept, v in vals.items():
                    p = hub / 'cache' / 'frames' / f'{concept}-CY{y}Q{q}.json.gz'
                    cur = json.load(gzip.open(p)) if p.exists() else {}
                    cur[cik] = v
                    gz(p, cur)
    # prices: weekdays from 2022-06-01 to 2026-10-16; quality names drift up a little
    days, d = [], dt.date(2022, 6, 1)
    while d <= dt.date(2026, 10, 16):
        if d.weekday() < 5:
            days.append(d.isoformat())
        d += dt.timedelta(days=1)
    for cik, (t, years, sector) in list(comps.items()) + [('0', ('SPY', None, None))]:
        drift = 0.0006 if t == 'GOOD' else 0.0002
        p, rows = 50.0, []
        for day in days:
            p *= 1 + drift + rnd.gauss(0, 0.015)
            rows.append([day, round(p, 4), 1000000])
        gz(prices / f'{t}.json.gz', {'ticker': t, 'rows': rows})
    (prices / 'sec-tickers.json').write_text(json.dumps({'rows': tick_rows + [{'ticker': 'SPY', 'cik': 884394, 'title': 'SPDR'}]}))
    (root / 'index.json').write_text(json.dumps({'companies': site, 'sector_names': {'technology': 'Technology', 'industrials': 'Industrials'}}))
    return hub, rq, prices


class Build(unittest.TestCase):
    def test_build_publishes_scores_factors_and_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            hub, rq, prices = world(root)
            st = Q.build(rq, hub, prices, root / 'index.json', today=TODAY)
            self.assertEqual(st['companies'], 60)
            self.assertGreaterEqual(st['piotroski_9'], 1)
            self.assertGreaterEqual(st['distress'], 1)
            ix = json.loads((rq / 'public' / 'index.json').read_text())
            F = ix['fields']
            rows = {r[0]: dict(zip(F, r)) for r in ix['rows']}
            self.assertEqual(rows['GOOD']['f_score'], 9)
            self.assertEqual((rows['BAD']['z_zone'], rows['BAD']['z_model']), ('distress', "Z''"))
            self.assertEqual(rows['GOOD']['z_model'], 'Z')                        # SIC 3674: a manufacturer
            self.assertTrue(rows['C02']['dol'] and rows['C02']['var_ratio'] is not None)
            self.assertTrue(all(r['wacc'] for r in rows.values()))
            self.assertTrue(any(r.get('resid') is not None for r in rows.values()))
            c = json.loads((rq / 'public' / 'c' / 'GOOD.json').read_text())
            self.assertEqual(len(c['metrics']['piotroski']['signals']), 9)
            self.assertIn('margins', c)
            fac = json.loads((rq / 'public' / 'factors.json').read_text())['factors']
            self.assertGreater(fac['composite']['months'], 12)
            self.assertIn('mean_ic', fac['f_score'])
            led = json.loads((rq / 'public' / 'ledger.json').read_text())
            self.assertIn('2026-10', led['months'])
            frozen = json.loads((rq / 'ledger' / 'composite.json').read_text())['months']['2026-10']['ranks']
            # a second build the same month keeps the frozen ranking untouched
            with mock.patch.object(Q, 'composite', return_value={t: 0.5 for t in rows}):
                Q.build(rq, hub, prices, root / 'index.json', today=TODAY)
            self.assertEqual(json.loads((rq / 'ledger' / 'composite.json').read_text())['months']['2026-10']['ranks'], frozen)
            mg = json.loads((rq / 'public' / 'margins.json').read_text())['sectors']
            self.assertIn('_all', mg)
            self.assertTrue((rq / 'public' / 'scatter.json').exists() and (rq / 'public' / 'status.json').exists())

    def test_collect_reads_frames_and_keeps_final_periods(self):
        with tempfile.TemporaryDirectory() as d:
            calls = []

            class Fake:
                def json(self, url, sec=False):
                    calls.append(url)
                    if 'EntityCommonStock' in url:
                        raise RuntimeError('HTTP 404')
                    annual = not url.rstrip('.json').endswith('I')
                    return {'data': [{'cik': 320193, 'val': 5, 'end': '2025-09-27'}] if annual else [{'cik': 320193, 'val': 7}]}
            r = Q.collect(Fake(), d, minutes=5, today=TODAY)
            self.assertEqual(r['errors'], 0)
            n = len(calls)
            self.assertEqual(n, sum(len(s) for _, s in Q.INSTANT) * 13 + sum(len(s) for _, s in Q.ANNUAL) * len(Q.annual_periods(TODAY)))
            self.assertEqual(json.load(gzip.open(Q._qpath(d, 'us-gaap', 'Assets', 'USD', 'CY2025Q4I'))), {'320193': 7})
            calls.clear()
            Q.collect(Fake(), d, minutes=5, today=TODAY)                         # everything fresh: nothing fetched
            self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
