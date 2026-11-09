"""Valuation beside the price (app/ratios.py): weeks, the trailing four quarters known by filing date (the same as
highs.ttm_eps), share counts filed in thousands put right, splits, each ratio against its own history and its industry
(the level chosen, the rank, the premium over the years), the price split into the per-share figure and the multiple,
the valuation research's extra ratios, the lists' stamp, and the move odds build; and the key days the news is fetched
for first (app/move_news.py key_days, to_read; app/move_headlines.py wanted)."""
import datetime as dt
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
try:
    import numpy as np
    import highs as H
    import ratios as RT
except ImportError:                                          # numpy is part of the analysis extras
    np = None


def weekdays(start, n):
    d, out = dt.date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def quarters(n, start='2015-03-31', rev=1e9, shares=1e8, eps=1.0, split_at=None, split=4, thousands=()):
    """n quarters of the income statement store: revenue, diluted shares (×split from quarter split_at on; in thousands
    for the quarters in `thousands`, with their EPS dropped as the store does), EPS."""
    out = []
    for q in range(n):
        end = (dt.date.fromisoformat(start) + dt.timedelta(days=91 * q)).isoformat()
        filed = (dt.date.fromisoformat(end) + dt.timedelta(days=35)).isoformat()
        sh = shares * (split if split_at is not None and q >= split_at else 1)
        f = {'revenue': {'val': rev * (1.02 ** q), 'filed': filed}, 'net_income': {'val': 1e8, 'filed': filed},
             'diluted_shares': {'val': sh / 1000 if q in thousands else sh, 'filed': filed}}
        if q not in thousands:
            f['eps'] = {'val': eps / (split if split_at is not None and q >= split_at else 1), 'filed': filed}
        out.append({'end': end, 'fields': f})
    return out


@unittest.skipIf(np is None, 'numpy not installed')
class Pieces(unittest.TestCase):
    def test_weeks(self):
        days = ['2026-11-02', '2026-11-06', '2026-11-07', '2026-11-08', '2026-11-09']
        w = RT.week_of(days)
        self.assertEqual(len(set(w[:4].tolist())), 1)             # Monday to Sunday: one week
        self.assertEqual(w[4], w[0] + 1)
        self.assertEqual(RT.friday(w[0]), '2026-11-06')
        self.assertEqual(RT.friday(RT.week_of(['1970-01-02'])[0]), '1970-01-02')

    def test_ttm_is_highs_ttm_eps(self):
        days = weekdays('2014-01-01', 3000)
        rng = np.random.default_rng(3)
        recs = []
        for q in range(40):
            if q == 17:                                           # a quarter missing: no four consecutive across it
                continue
            end = (dt.date(2014, 3, 31) + dt.timedelta(days=91 * q)).isoformat()
            lag = 25 + int(rng.integers(0, 60)) + (150 if q == 30 else 0)   # one filed late
            recs.append((min((dt.date.fromisoformat(end) + dt.timedelta(days=lag)).isoformat(), '2030-01-01'), end, float(rng.normal(1, 0.4))))
        recs.append((recs[5][0], recs[5][1], 9.9))                # an amendment filed the same day (the first kept)
        a, b = H.ttm_eps(days, recs), RT.ttm(days, recs)
        self.assertTrue(np.array_equal(np.isnan(a), np.isnan(b)))
        self.assertTrue(np.allclose(a[~np.isnan(a)], b[~np.isnan(b)], rtol=0, atol=1e-12))
        self.assertTrue(np.isnan(b[:60]).all())                   # nothing before four quarters are filed
        self.assertTrue(np.isnan(RT.ttm(days, [])).all())

    def test_share_counts_filed_in_thousands(self):
        sh = [546e6, 574e6, 546e6] + [591e3, 573e3, 583e3, 601e3, 613e3, 614e3] + [614e6, 621e6] * 4
        trusted = [True] * 3 + [False] * 6 + [True] * 8
        fixed = RT.share_units(sh, trusted)
        self.assertEqual(fixed[:3], sh[:3])                       # the good ones before the slip are kept
        self.assertTrue(all(abs(fixed[i] / (sh[i] * 1000) - 1) < 1e-9 for i in range(3, 9)))
        self.assertEqual(fixed[9:], sh[9:])
        # no trusted quarters: the median of all decides, a real split (×4) is left to fix_splits
        sp = [1e8] * 8 + [4e8] * 8 + [4e5] * 2
        f2 = RT.share_units(sp)
        self.assertEqual(f2[:16], sp[:16])
        self.assertEqual(f2[16:], [4e8, 4e8])

    def test_per_share_restated_across_splits_and_units(self):
        q = quarters(16, split_at=8, split=4, thousands=(3, 4))
        rps = RT.per_share(q)
        self.assertEqual(len(rps), 16)
        v = [x[2] for x in rps]
        # revenue ÷ shares in today's basis (four times the shares): smooth across the split and the slipped quarters
        for i in range(1, 16):
            self.assertLess(abs(v[i] / v[i - 1] - 1.02), 1e-9)
        self.assertAlmostEqual(v[0], 1e9 / 4e8)

    def test_ratio_bounds(self):
        r = RT.ratio(np.array([10.0, 10, 10, 10, 10]), np.array([1.0, -1, 0, 0.01, 50]), lo=1.0)
        self.assertEqual(r[0], 10.0)
        self.assertTrue(np.isnan(r[1:]).all())                    # a loss, nothing, over 300, under the floor

    def test_own_stats_and_the_split(self):
        days = weekdays('2016-01-04', 2600)
        n = len(days)
        r = np.full(n, np.nan)
        r[200:] = 10 + 5 * np.sin(np.arange(n - 200) / 90.0)
        r[-1] = 16.0                                              # today: above every day before
        st = RT.own_stats(days, r)
        self.assertTrue(st['at_hi'])
        self.assertFalse(st['at_lo'])
        self.assertEqual(st['pct'], 100.0)
        self.assertEqual(st['hi'], [16.0, days[-1]])
        self.assertEqual(st['since_hi'], 0)
        self.assertEqual(st['from'], days[200])
        self.assertEqual(st['y5']['from'], days[-RT.Y5])
        self.assertEqual(st['y5']['pct'], 100.0)
        self.assertEqual(len(st['q']), 5)
        self.assertLessEqual(st['q'][0], st['q'][2])
        self.assertIsNone(RT.own_stats(days[:100], r[-100:] * np.nan))
        # price = per-share × ratio, so (1 + price) = (1 + per) × (1 + ratio)
        per = np.linspace(1, 3, n)
        px = per * np.where(np.isfinite(r), r, 12.0)
        sp = RT.splits(days, px, per, np.where(np.isfinite(r), r, np.nan), run_start=days[-300])
        ks = [x['k'] for x in sp]
        self.assertEqual(ks, ['1y', '3y', '5y', 'run'])
        for x in sp:
            self.assertAlmostEqual(1 + x['price'], (1 + x['per']) * (1 + x['ratio']), delta=5e-4)
        self.assertEqual(sp[-1]['from'], days[-300])

    def test_sig(self):
        self.assertEqual(RT.sig(38.369), 38.4)
        self.assertEqual(RT.sig(0.0012345), 0.00123)
        self.assertEqual(RT.sig(1234.5), 1234.0)
        self.assertIsNone(RT.sig(float('nan')))


@unittest.skipIf(np is None, 'numpy not installed')
class Build(unittest.TestCase):
    def setUp(self):
        self.days = weekdays('2015-06-01', 2700)
        rng = np.random.default_rng(11)
        self.data, self.raws, self.assets, self.eps, self.fund = {}, {}, [], {}, {}
        # nine semiconductor companies (SIC 3674), three more in SIC 3672 (the same group 367), one loss-maker
        for i in range(13):
            t = f'S{i}'
            c = 50 * np.exp(np.cumsum(rng.normal(0.0004, 0.015, len(self.days))))
            self.data[t] = (self.days, c, c[-1])
            sic = '3674' if i < 9 else '3672'
            cik = 100 + i
            self.assets.append({'key': t, 'ticker': t, 'kind': 'stock', 'cik': cik, 'sic': sic, 'industry': 'Semiconductors' if sic == '3674' else 'Circuit boards',
                                'sector': 'technology', 'mcap': 1e10 * (13 - i)})
            q = quarters(44, rev=1e9 * (1 + i / 10), eps=1.0 if i != 12 else -0.5)
            self.fund[str(cik)] = q
            self.eps[str(cik)] = [{'end': x['end'], 'filed': x['fields']['eps']['filed'], 'eps': x['fields']['eps']['val'], 'shares': 1e8} for x in q]
        self.assets.append({'key': 'SPY', 'kind': 'market'})
        self.data['SPY'] = (self.days, self.data['S0'][1], 1.0)

    def test_blocks(self):
        blocks, st = RT.build(self.data, {}, self.assets, eps=self.eps, fund=self.fund, names={'36': 'Electronic equipment'}, runs={'S0': self.days[-100]}, verbose=False)
        self.assertNotIn('SPY', blocks)
        self.assertEqual(st['companies'], 13)
        b = blocks['S0']
        for k in ('pe', 'ps'):
            self.assertIn(k, b)
            self.assertIsNotNone(b[k]['now'])
            self.assertEqual(b[k]['ind']['level'], 'industry')    # eight other semis: the four-digit industry
            self.assertEqual(b[k]['ind']['key'], 'SIC-3674')
            self.assertEqual(b[k]['ind']['n'], 8)
            self.assertEqual(b[k]['ind']['top'][0][0], 'S1')      # the largest peer first
            self.assertTrue(0 <= b[k]['ind']['rank'] <= 100)
            self.assertIsNotNone(b[k]['ind']['rel'])
            self.assertIn('rel_pct', b[k]['ind'])
            self.assertEqual([x['k'] for x in b[k]['split']][-1], 'run')
        w = b['w']
        self.assertEqual(len(w['pe']), w['n'])
        self.assertEqual(len(w['pe_ind']), w['n'])
        self.assertEqual(len(w['ps']), w['n'])
        self.assertEqual(dt.date.fromisoformat(w['d0']).weekday(), 4)  # a Friday
        self.assertAlmostEqual(w['pe'][-1], b['pe']['now'], delta=0.06 * b['pe']['now'])
        # three circuit-board makers: too few in their industry, so the group (367: nine semis and two others)
        c = blocks['S9']['ps']['ind']
        self.assertEqual((c['level'], c['key'], c['n']), ('industry group', 'SIC-367', 12))
        self.assertEqual(c['name'], 'Electronic components and accessories')
        # the loss-maker: no P/E, said why; its P/S is there
        self.assertNotIn('pe', blocks['S12'])
        self.assertIn('ps', blocks['S12'])
        json.dumps(blocks, allow_nan=False)

    def test_why_none_and_the_stamp(self):
        last = self.days[-1]
        for r in self.eps['100']:                                 # the year before the last day a loss: TTM EPS negative today
            if '2000' < r['filed'] <= last and r['filed'] >= (dt.date.fromisoformat(last) - dt.timedelta(days=400)).isoformat():
                r['eps'] = -3.0
        blocks, _ = RT.build(self.data, {}, self.assets, eps=self.eps, fund=self.fund, verbose=False)
        b = blocks['S0']
        self.assertIsNone(b['pe']['now'])
        self.assertEqual(b['pe']['why'], 'loss')
        state = {'pe': None}
        RT.stamp(state, blocks['S1'])
        self.assertEqual(state['ps'], blocks['S1']['ps']['now'])
        self.assertEqual(state['ps_all'], blocks['S1']['ps']['pct'])
        self.assertEqual(state['ps_ind'], blocks['S1']['ps']['ind']['rank'])
        self.assertIn('pe_all', state)

    def test_more_from_the_valuation_file(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'c').mkdir()
            (Path(d) / 'c' / '100.json').write_text(json.dumps({'river': {'from': '2022-06-03', 'metrics': {
                'pb': {'current': 46.86, 'median': 45.98, 'pct': 0.586, 'weeks': 232}, 'ev_ebitda': {'current': 30.14, 'median': 24.11, 'pct': 0.97, 'weeks': 232}}},
                'peers': {'pe': {'group': 'sic357', 'n': 24, 'p25': 14.5, 'p50': 24.4, 'p75': 38.9, 'own': 38.1},
                          'ev_sales': {'group': 'sic357', 'n': 26, 'p25': 1.36, 'p50': 3.3, 'p75': 6.12, 'own': 10.57}}}))
            m = RT.more_of(d, 100)
            self.assertEqual([r['k'] for r in m['rows']], ['pb', 'ev_ebitda', 'ev_sales'])
            self.assertEqual(m['rows'][0]['pct'], 58.6)
            self.assertIsNone(m['rows'][0]['peer'])
            self.assertEqual(m['rows'][2]['now'], 10.6)
            self.assertEqual(m['rows'][2]['peer']['mid'], 3.3)
            self.assertEqual(m['peer_pe']['n'], 24)
            self.assertIsNone(RT.more_of(d, 999))
            blocks, _ = RT.build(self.data, {}, self.assets, eps=self.eps, fund=self.fund, val_dir=d, verbose=False)
            self.assertIn('more', blocks['S0'])
            self.assertNotIn('more', blocks['S1'])


@unittest.skipIf(np is None, 'numpy not installed')
class InTheMoveOdds(unittest.TestCase):
    def test_moves_build_publishes_the_ratios(self):
        import moves as M
        import paths as P
        with tempfile.TemporaryDirectory() as tmp:
            root, val, epsd, fundd = Path(tmp) / 'pth', Path(tmp) / 'val', Path(tmp) / 'eps', Path(tmp) / 'fund'
            epsd.mkdir()
            fundd.mkdir()
            days = weekdays('2019-01-07', 1400)
            rng = np.random.default_rng(5)

            def put(t, drift=0.0005, scale=0.012):
                c = list(100 * np.exp(np.cumsum(rng.normal(drift, scale, len(days)))))
                P.save(root, t, {'ticker': t, 'source': 'yahoo', 'fetched_at': '2026-01-01T00:00:00+00:00', 't': list(days), 'o': c, 'h': c, 'l': c,
                                 'c': c, 'ac': c, 'v': [1000 + 10 * (i % 7) for i in range(len(days))]})
            for t in ('SPY', 'XLK'):
                put(t)
            rows = []
            for i in range(8):
                t = f'CO{i}'
                put(t, drift=0.001, scale=0.02)
                rows.append([1000 + i, t, f'COMPANY {i} INC', 'technology', 'industrial', 1e9 * (10 - i)])
                (val / 'c').mkdir(parents=True, exist_ok=True)
                (val / 'c' / f'{1000 + i}.json').write_text(json.dumps({'cik': 1000 + i, 'industry': 'Semis', 'sic': '3674'}))
                q = quarters(30, start='2018-12-31')
                (fundd / f'{1000 + i}.json').write_text(json.dumps({'quarters': q}))
                (epsd / f'{1000 + i}.json').write_text(json.dumps({'records': [{'end': x['end'], 'filed': x['fields']['eps']['filed'], 'eps': 0.6, 'shares': 1e8} for x in q]}))
            (val / 'index.json').write_text(json.dumps({'fields': ['cik', 'ticker', 'name', 'sector', 'kind', 'mcap'], 'rows': rows}))
            st = M.build(root, val / 'index.json', eps_dir=epsd, fund_dir=fundd)
            self.assertEqual(st['errors'], [])
            self.assertEqual(st['ratios']['companies'], 8)
            out = root / 'public' / 'moves'
            doc = json.loads((out / 'a' / 'CO0.json').read_text())
            self.assertIn('ratios', doc)
            self.assertEqual(doc['ratios']['ps']['ind']['name'], 'Semis')
            self.assertEqual(doc['ratios']['ps']['ind']['n'], 7)
            self.assertIn('ps', doc['highs']['state'])            # stamped into the state
            hd = json.loads((out / 'highs.json').read_text())
            for r in hd['now']:
                if r['key'].startswith('CO'):
                    self.assertIn('ps_all', r['state'])           # and into the list, written after the stamp
            self.assertNotIn('ratios', json.loads((out / 'a' / 'SPY.json').read_text()))


class KeyDays(unittest.TestCase):
    def a_file(self, root):
        d = Path(root) / 'public' / 'moves' / 'a'
        d.mkdir(parents=True)
        (d / 'ACME.json').write_text(json.dumps({'highs': {'state': {'ath_date': '2026-10-30', 'high': True, 'run_start': '2026-09-01'},
                                                           'own': {'last': [{'start': '2024-01-10', 'peak': '2024-06-03'}, {'start': '2025-02-03', 'peak': '2025-03-04'}]}},
                                                 'lows': {'52w': {'state': {'low_date': '2026-04-08', 'since': '2026-03-01'}}}}))

    def test_key_days_from_the_asset_file(self):
        import move_news as N
        with tempfile.TemporaryDirectory() as d:
            self.a_file(d)
            k = N.key_days(d, 'ACME')
            self.assertEqual(k[0], ('2026-10-30', 'the latest all-time high'))
            self.assertIn(('2026-09-01', "this run's first high"), k)
            self.assertIn(('2024-06-03', "a run's peak"), k)
            self.assertIn(('2026-04-08', 'the 52-week low'), k)
            self.assertEqual([x[0] for x in k], sorted([x[0] for x in k], reverse=True))
            self.assertEqual(N.key_days(d, 'NONE'), [])

    def test_the_key_days_are_read_and_searched_early(self):
        import move_news as N
        import move_headlines as MH
        days = weekdays('2023-01-02', 900)
        closes = [100 * math.exp(0.0004 * i) for i in range(len(days))]
        kd = days[300]
        filings = [['0001-24-000001', '8-K', kd, '08:00', '8.01'], ['0001-24-000002', '8-K', days[301], '08:00', '8.01']]
        doc = {'filings': filings, 'read': {}, 'tried': {}}
        self.assertEqual(N.to_read(doc, days, closes), [])            # quiet days: not read
        self.assertEqual(N.to_read(doc, days, closes, [kd]), ['0001-24-000001'])
        today = dt.date.fromisoformat(days[-1])
        w = MH.wanted({'days': {}, 'windows': []}, days, closes, today, keys=[kd])
        win = ((dt.date.fromisoformat(kd) - dt.timedelta(days=1)).isoformat(), kd)
        self.assertIn(win, w)
        self.assertLess(w.index(win), 14)                             # after the last week and twelve months, before the rest
        self.assertNotIn(win, MH.wanted({'days': {}, 'windows': []}, days, closes, today))


if __name__ == '__main__':
    unittest.main()
