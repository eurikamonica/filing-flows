"""market_maps.py: the money-flow Sankey, managers' sectors and race, the treemap, crowding, the maturity wall, the
gauges and net liquidity, from small fixtures (no network)."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import market_maps as M

CF = ['ticker', 'name', 'S', 'raw', 'f13_b', 'f13_s', 'f13_usd', 'ins_b', 'ins_s', 'ins_usd', 'gov_b', 'gov_s', 'gov_usd', 'actors', 'groups_buy', 'groups_sell', 'S_now']


def row(t, name, f13, ins, gov=0):
    return [t, name, 10, 5, 1, 0, f13, 1, 0, ins, 0, 0, gov, 2, 1, 0, 10]


class Flows(unittest.TestCase):
    def test_groups_to_sectors_to_stocks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            M.write_json(root / 'combined' / 'index.json', {'periods': [{'key': 'prev', 'label': 'Q3', 'start': '2026-07-01', 'end': '2026-09-30'}]})
            M.write_json(root / 'combined' / 'prev.json', {'fields': CF, 'rows': [row('AAPL', 'Apple', 5e9, -1e9), row('XOM', 'Exxon', 2e9, 5e8),
                                                                                 row('META', 'Meta', -3e9, -2e9)]})
            f = M.build_flows(root, {'AAPL': 'technology', 'META': 'technology', 'XOM': 'energy'})
            p = f['periods'][0]
            self.assertEqual(p['top_in'][0]['ticker'], 'AAPL')
            self.assertEqual(p['top_out'][0]['ticker'], 'META')
            buy = {(l['from'], l['to']): l['v'] for l in p['buy']['links']}
            self.assertEqual(buy[('13F managers', 'Technology')], 5e9)      # META's 13F selling is on the other side
            self.assertEqual(buy[('Technology', '$AAPL')], 5e9)
            self.assertEqual(buy[('Energy', '$XOM')], 2.5e9)
            g = {x['id']: x for x in p['groups']}
            self.assertEqual((g['f13']['buy'], g['f13']['sell'], g['ins']['net']), (7e9, 3e9, -2.5e9))


def shard(items):
    return [{'issuer': i, 'cusip': c, 'put_call': pc, 'share_type': 'SH', 'shares': sh, 'value_usd': v, 'ticker': t}
            for i, c, pc, sh, v, t in items]


class Managers(unittest.TestCase):
    def test_sectors_race_crowding_and_walk_forward(self):
        with tempfile.TemporaryDirectory() as d:
            hub = Path(d)
            M.write_json(hub / 'market' / 'watchlist.json', {'funds': [{'cik': '1', 'name': 'Fund A'}, {'cik': '2', 'name': 'Fund B'}, {'cik': '3', 'name': 'Fund C'}]})
            M.write_json(hub / 'market' / 'cusip-tickers.json', {'037833100': 'AAPL'})
            for cik, q1, q2 in (('1', [('APPLE', '037833100', 'NONE', 100, 1000, None), ('EXXON', 'X1', 'NONE', 10, 500, 'XOM')],
                                      [('APPLE', '037833100', 'NONE', 150, 1800, None), ('EXXON', 'X1', 'NONE', 10, 600, 'XOM'), ('OPT', 'X9', 'CALL', 1, 50, 'AAPL')]),
                                ('2', [('APPLE', '037833100', 'NONE', 50, 500, 'AAPL'), ('META', 'M1', 'NONE', 5, 500, 'META')],
                                      [('APPLE', '037833100', 'NONE', 50, 600, 'AAPL'), ('META', 'M1', 'NONE', 5, 700, 'META')]),
                                ('3', [('APPLE', '037833100', 'NONE', 20, 200, 'AAPL')], [('APPLE', '037833100', 'NONE', 20, 240, 'AAPL'), ('TSLA', 'T1', 'NONE', 1, 100, 'TSLA')])):
                M.write_json(hub / 'shards' / 'holdings' / f'{cik}.json',
                             {'snapshots': [{'period': '2025-03-31', 'filed': '2025-05-15', 'positions_shard': f'shards/holdings/{cik}-2025-03-31.json', 'total_usd': sum(x[4] for x in q1) * 1000},
                                            {'period': '2025-06-30', 'filed': '2025-08-14', 'positions_shard': f'shards/holdings/{cik}-2025-06-30.json', 'total_usd': sum(x[4] for x in q2) * 1000}]})
                M.write_json(hub / 'shards' / 'holdings' / f'{cik}-2025-03-31.json', shard(q1))
                M.write_json(hub / 'shards' / 'holdings' / f'{cik}-2025-06-30.json', shard(q2))
            # prices for the walk-forward check: 130 sessions from the 13F deadline
            import gzip
            (hub / 'cache' / 'prices').mkdir(parents=True)
            days = [(dt.date(2025, 5, 1) + dt.timedelta(days=i)).isoformat() for i in range(400) if (dt.date(2025, 5, 1) + dt.timedelta(days=i)).weekday() < 5]
            for t, k in (('AAPL', 1.5), ('XOM', 1.0), ('META', 1.2), ('TSLA', 0.8)):
                with gzip.open(hub / 'cache' / 'prices' / f'{t}.json.gz', 'wt') as f:
                    json.dump({'rows': [[dd, 100 + (k - 1) * 100 * i / len(days), 1e6] for i, dd in enumerate(days)]}, f)
            m = M.build_managers(hub, {'AAPL': 'technology', 'XOM': 'energy', 'META': 'technology', 'TSLA': 'consumer-disc'})
            a = m['managers'][0]
            self.assertEqual((a['total'], a['options_usd'], a['positions']), (2_400_000, 50_000, 2))     # values in thousands → dollars; the call apart
            tech = next(s for s in a['sectors'] if s['id'] == 'technology')
            self.assertEqual((tech['positions'][0]['ticker'], tech['positions'][0]['status']), ('AAPL', 'added'))
            self.assertEqual(a['race'][-1]['top'][0][0], 'AAPL')
            self.assertEqual(m['combined_race'][-1]['top'][0], ['AAPL', 2_640_000, round(2_640_000 / 4_040_000, 4)])
            n = M.build_network(m, hub / 'cache' / 'prices')
            crowd = {c['ticker']: c for c in n['crowding']}
            self.assertEqual(crowd['AAPL']['holders'], 3)
            self.assertTrue(crowd['AAPL']['index'] > 60)
            self.assertEqual(len(n['nodes']), 4)                                        # 3 managers + AAPL (the only shared stock)
            self.assertEqual(len(n['check']['quarters']), 0)                            # fewer than 5 single-holder names: no check yet
            hm = M.build_heatmap({'asof': '2025-06-30', 'fields': ['name', 'mcap', 'chg_pct', 'price', 'sector', 'industry'],
                                  'rows': {'AAPL': ['Apple', 3e12, 1.5, 200, 'Technology', ''], 'XOM': ['Exxon', 5e11, -0.5, 110, 'Energy', ''],
                                           'META': ['Meta', 1.5e12, 2.0, 700, 'Technology', ''], 'ZZ-W': ['warrant', 1e9, 0, 1, 'Finance', '']}},
                                 {'AAPL': 'technology', 'XOM': 'energy', 'META': 'technology'})
            self.assertEqual([c[0] for c in hm['cells']], ['AAPL', 'META', 'XOM'])
            area = sum(c[4][2] * c[4][3] for c in hm['cells'])
            self.assertAlmostEqual(area / (hm['box'][0] * hm['box'][1]), 1.0, delta=0.08)   # the cells tile the box (minus padding)
            self.assertEqual(hm['sectors'][0]['id'], 'technology')


class Gauges(unittest.TestCase):
    def test_shiller_dates_and_fits(self):
        self.assertEqual((M._shiller_month(1871.01), M._shiller_month(1871.1), M._shiller_month(2026.12)), ('1871-01', '1871-10', '2026-12'))
        rows = [['Date', 'P', 'D', 'E', 'CPI', 'Date Fraction', 'Rate GS10', 'Price', 'Dividend', 'Price', 'Earnings', 'Earnings', 'CAPE']]
        for i in range(400):
            y, mo = 1990 + i // 12, i % 12 + 1
            rows.append([y + mo / 100, 100 + i, 2, 5, 100 + i * 0.2, 0, 5.0, 100 + i, 2, 200 + 2 * i, 5, 5, 20 + (i % 10)])
        recs = M.parse_shiller_rows(rows)
        self.assertEqual((recs[0]['month'], recs[-1]['month'], recs[0]['real_tr'], recs[0]['cape']), ('1990-01', '2023-04', 200, 20))
        fwd = M.forward_real_return(recs)
        self.assertAlmostEqual(fwd['1990-01'], (440 / 200) ** 0.1 - 1, places=6)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            M.write_json(root / 'cache' / 'shiller.json', {'source': 'shiller', 'rows': recs})
            (root / 'cache' / 'fred').mkdir(parents=True)
            (root / 'cache' / 'fred' / 'GDP.csv').write_text('observation_date,GDP\n' + '\n'.join(f'{1990 + i // 4}-{i % 4 * 3 + 1:02d}-01,{20000 + i * 10}' for i in range(140)))
            (root / 'cache' / 'fred' / 'NCBEILQ027S.csv').write_text('observation_date,NCBEILQ027S\n' + '\n'.join(f'{1990 + i // 4}-{i % 4 * 3 + 1:02d}-01,{(20000 + i * 10) * 1000 * (1 + i / 100)}' for i in range(140)))
            t = M.build_thermometer(root, {'indices': [{'id': 'spx', 'fwd_pe': 18.3, 'as_of': '2026-10-16'}]})
            g = t['gauges']
            self.assertAlmostEqual(g['buffett']['value'], 2.39, places=2)
            self.assertEqual(g['buffett']['percentile'], 1.0)
            self.assertIn('fit', g['cape'])
            self.assertEqual(g['fwd_pe']['history_n'], 1)
            # liquidity from weekly FRED series
            wk = [(dt.date(2024, 1, 3) + dt.timedelta(days=7 * i)).isoformat() for i in range(60)]
            (root / 'cache' / 'fred' / 'WALCL.csv').write_text('observation_date,WALCL\n' + '\n'.join(f'{d},{7_000_000 - i * 10_000}' for i, d in enumerate(wk)))
            (root / 'cache' / 'fred' / 'WTREGEN.csv').write_text('observation_date,WTREGEN\n' + '\n'.join(f'{d},{800_000}' for d in wk))
            (root / 'cache' / 'fred' / 'RRPONTSYD.csv').write_text('observation_date,RRPONTSYD\n' + '\n'.join(f'{d},{500 - i * 5}' for i, d in enumerate(wk)))
            L = M.build_liquidity(root, since='2024-01-01')
            self.assertEqual(L['latest']['week'], wk[-1])
            self.assertAlmostEqual(L['latest']['net'], 7000 - 590 - 800 - 205, places=1)
            self.assertAlmostEqual(L['latest']['chg_1w'], -5.0, places=1)

    def test_maturity_wall(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            M.write_json(root / 'index.json', {'fields': ['cik', 'ticker', 'name', 'sector', 'rating_band'], 'rows': [[1, 'F', 'Ford', 'consumer-disc', 'BB'], [2, 'T', 'AT&T', 'communication', 'BBB']]})
            M.write_json(root / 'c' / '1.json', {'cik': 1, 'instruments': [{'kind': 'bond', 'face': 1e9, 'maturity': '2027-05-01'}, {'kind': 'revolver', 'face': 5e9, 'carrying': 2e8, 'maturity': '2027-01-01'},
                                                                           {'kind': 'bond', 'carrying': 3e9, 'maturity': '2040-01-01'}, {'kind': 'bond', 'face': 1e8, 'maturity': '2020-01-01'}]})
            M.write_json(root / 'c' / '2.json', {'cik': 2, 'instruments': [{'kind': 'bond', 'face': 4e9, 'maturity': '2028-01-01'}]})
            w = M.build_maturity(root, dt.date(2026, 10, 19))
            self.assertEqual(w['wall']['BB'][:3], [1e8, 1.2e9, 0])
            self.assertEqual(w['wall']['BB'][-1], 3e9)
            self.assertEqual(w['totals'][2], 4e9)
            self.assertEqual(w['next_year_top'][0]['ticker'], 'F')


if __name__ == '__main__':
    unittest.main()
