"""rank_panel.py (the studio's leaderboards) and the dividend / split events the collector now keeps."""
import datetime as dt, gzip, json, math, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import frames as FR
import rank_panel as R
import rotation_history as RH


def put(root, concept, period, vals):
    p = FR.path_for(root, concept, period)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, 'wt') as f:
        json.dump(vals, f)


class Events(unittest.TestCase):
    def test_dividends_splits_and_the_close_as_traded(self):
        start = dt.datetime(2024, 1, 1, 14, 30, tzinfo=dt.timezone.utc)
        ts = [int((start + dt.timedelta(days=7 * i)).timestamp()) for i in range(6)]
        body = {'chart': {'result': [{'meta': {'gmtoffset': -18000}, 'timestamp': ts,
                                      'indicators': {'quote': [{'close': [10, 11, 12, 13, 14, 15], 'volume': [5] * 6}],
                                                     'adjclose': [{'adjclose': [9, 10, 11, 12.5, 13.6, 15]}]},
                                      'events': {'dividends': {str(ts[3]): {'amount': 0.25, 'date': ts[3]}},
                                                 'splits': {str(ts[1]): {'numerator': 4, 'denominator': 1, 'date': ts[1]}}}}]}}
        rows = RH.parse_yahoo(body)
        self.assertEqual(rows[0], ['2024-01-05', 9.0, 5, 10.0])                  # adjusted close, volume, close as traded
        ev = RH.yahoo_events(body)
        self.assertEqual(ev['div'], [['2024-01-22', 0.25]])
        self.assertEqual(ev['split'], [['2024-01-08', 4.0]])
        self.assertEqual(RH.merge_events(ev, {'div': [['2024-04-22', 0.3]], 'split': []})['div'], [['2024-01-22', 0.25], ['2024-04-22', 0.3]])

    def test_a_refresh_puts_the_rows_on_file_on_the_new_basis(self):
        old = [['2024-01-05', 10.0, 100, 10.0], ['2024-01-12', 11.0, 100, 11.0], ['2024-01-19', 12.0, 100, 12.0]]
        # since then: a dividend (adjusted closes 2% lower before it) and a 2-for-1 split (closes halved, volume doubled)
        new = [['2024-01-19', 12.0 * 0.98 / 2, 200, 6.0], ['2024-01-26', 6.2, 220, 6.2]]
        m = RH.merge(old, new)
        self.assertEqual([r[0] for r in m], ['2024-01-05', '2024-01-12', '2024-01-19', '2024-01-26'])
        self.assertAlmostEqual(m[0][1], 10.0 * 0.49, places=4)
        self.assertAlmostEqual(m[0][3], 5.0, places=4)
        self.assertEqual(m[0][2], 200)
        self.assertEqual(RH.merge(old, [['2024-01-26', 13.0, 100, 13.0]])[0], old[0])   # no overlap: nothing to rebase on


class Shares(unittest.TestCase):
    SPLITS = [['2020-08-31', 4.0]]

    def test_cover_counts_and_restated_weighted_averages(self):
        dei = [('2020-04-17', 4.33e9), ('2020-07-17', 4.28e9), ('2020-10-16', 17.0e9)]
        # the quarter to June as last filed — restated after the split in a later 10-Q (×4) — and one in thousands
        wavg = [('2020-03-28', 17.62e9), ('2020-06-27', 17.42e9), ('2020-12-26', 17110.0e6 / 1000 * 1000)]
        h = R.share_history(dei, wavg, self.SPLITS)
        by = dict(h)
        self.assertAlmostEqual(by['2020-04-17'] / 1e9, 17.32, places=2)          # 4.33 × 4: today's basis
        self.assertAlmostEqual(by['2020-10-16'] / 1e9, 17.0, places=2)           # after the split: as counted
        self.assertTrue(all(16e9 < v < 18e9 for _, v in h), h)                   # the restated averages not ×4 again
        thousands = R.share_history([('2026-05-06', 98.2e6)], [('2026-04-04', 82139.0e6)], [])
        self.assertTrue(all(80e6 < v < 100e6 for _, v in thousands), thousands)

    def test_one_class_of_several_and_no_cover_count(self):
        # the cover page counts class A only; the weighted average covers every class
        h = R.share_history([('2024-05-01', 5.8e9)], [('2024-03-31', 12.4e9)], [])
        self.assertEqual(dict(h)['2024-05-01'], 12.4e9)
        eps = R.share_history([], [], [], eps_sh=[('2023-06-30', 12.9e9), ('2023-09-30', 12.8e9)])
        self.assertEqual(len(eps), 2)
        self.assertEqual(R.restated_bases([['2021-07-20', 4.0], ['2024-06-10', 10.0]], '2021-01-31'), [1.0, 4.0])

    def test_unit_slips_and_a_fourth_quarter_from_a_year_at_another_scale(self):
        self.assertEqual(R.unit_slips([800.0, 850.0, 0.82, 900.0, 950.0]), [800.0, 850.0, None, 900.0, 950.0])
        self.assertEqual(R.unit_slips([800.0, -4000.0, 900.0]), [800.0, -4000.0, 900.0])   # a real loss stays
        root = Path(tempfile.mkdtemp())
        for p, v in (('CY2025Q1', 813.8e6), ('CY2025Q2', 888.8e6), ('CY2025Q3', 853e6)):
            put(root, 'NetIncomeLoss', p, {'9': v})
        put(root, 'NetIncomeLoss', 'CY2025', {'9': [3511, '2025-12-31']})               # tagged in millions
        q = FR.quarterly(root, 'NetIncomeLoss', ['CY2025Q1', 'CY2025Q2', 'CY2025Q3', 'CY2025Q4'])
        self.assertNotIn('9', q['CY2025Q4'])
        put(root, 'NetIncomeLoss', 'CY2025', {'9': [3511e6, '2025-12-31']})
        q = FR.quarterly(root, 'NetIncomeLoss', ['CY2025Q1', 'CY2025Q2', 'CY2025Q3', 'CY2025Q4'])
        self.assertAlmostEqual(q['CY2025Q4']['9'], 3511e6 - (813.8e6 + 888.8e6 + 853e6))

    def test_months_and_asof(self):
        grid = R.months('2024-01', dt.date(2024, 3, 15))
        self.assertEqual(grid, ['2024-01', '2024-02', '2024-03'])
        rows = [['2024-01-05', 10, 100, 11], ['2024-01-26', 12, 100, 13], ['2024-02-23', 14, 200, 15], ['2024-03-08', 16, 0, 17]]
        px, pt, dv = R.monthly(rows, grid)
        self.assertEqual(px, [12, 14, 16])
        self.assertEqual(pt, [13, 15, 17])
        self.assertEqual(dv, [100 * 11 + 100 * 13, 200 * 15, None])
        pts = [('2023-01-10', 1.0), ('2024-01-10', 2.0)]
        self.assertEqual(R.asof(pts, '2024-02-29'), 2.0)
        self.assertIsNone(R.asof(pts, '2023-01-01'))
        self.assertIsNone(R.asof([('2020-01-01', 1.0)], '2024-01-01'))          # too old


class Build(unittest.TestCase):
    def test_the_panel(self):
        root = Path(tempfile.mkdtemp())
        today = dt.date(2026, 10, 20)
        periods = FR.calendar_quarters((today.year - 2009) * 4 + (today.month - 1) // 3, today)
        for i, p in enumerate(periods):
            put(root, 'Revenues', p, {'1': 1e9 * (1 + .02 * i), '2': 5e8})
            put(root, 'NetIncomeLoss', p, {'1': 1e8, '2': -1e7})
            y, q = int(p[2:6]), int(p[-1])
            end = (dt.date(y + (q == 4), (3 * q) % 12 + 1, 1) - dt.timedelta(days=1))
            cover = (end + dt.timedelta(days=25)).isoformat()
            # company 1 split 2-for-1 in 2020: counted 50M before, 100M after
            put(root, 'EntityCommonStockSharesOutstanding', p + 'I', {'1': [50e6 if cover < '2020-06-01' else 100e6, cover]})
            put(root, 'StockholdersEquity', p + 'I', {'1': [2e9, end.isoformat()]})
        weeks = [(dt.date(2015, 1, 2) + dt.timedelta(days=7 * i)).isoformat() for i in range(600)]
        rows = [[w, 20.0 * (1.001 ** i), 1e6, 20.0 * (1.001 ** i)] for i, w in enumerate(weeks) if w <= today.isoformat()]
        docs = {'AAA': {'rows': rows, 'ev': {'div': [], 'split': [['2020-06-01', 2.0]]}},
                'BBB': {'rows': rows}}                                                # fetched before events were kept
        cos = [{'t': 'AAA', 'n': 'A Corp', 's': 'technology', 'cik': 1}, {'t': 'BBB', 'n': 'B Corp', 's': 'energy', 'cik': 2}]
        st = R.build(root / 'rank', cos, docs, frames_root=root, today=today, names={'technology': 'Technology'}, nasdaq=False)
        self.assertEqual((st['companies'], st['with_cap'], st['splits_unknown']), (2, 1, 1))
        meta = json.loads((root / 'rank' / 'meta.json').read_text())
        self.assertEqual(meta['cos'][0], ['AAA', 'A Corp', 'technology'])
        self.assertEqual(meta['months']['start'], '2000-01')
        self.assertEqual(meta['quarters'][0], '2009Q1')
        cap = json.loads((root / 'rank' / 'm-cap.json').read_text())['rows']
        i0 = cap[0][0]
        vals = cap[0][1:]
        g = R.months('2000-01', today)
        k19, k24 = g.index('2019-12') - i0, g.index('2024-12') - i0
        close19 = [r for r in rows if r[0] <= '2019-12-31'][-1][3]
        self.assertAlmostEqual(vals[k19], close19 * 100e6 / 1e6, delta=vals[k19] * 0.002)   # 50M then = 100M today
        self.assertTrue(vals[k24] > vals[k19])
        self.assertEqual(cap[1], [])                                                  # no split history: no value
        rev = json.loads((root / 'rank' / 'q-rev.json').read_text())['rows']
        self.assertEqual(rev[0][0], 0)
        self.assertAlmostEqual(rev[0][1], 1000)
        eq = json.loads((root / 'rank' / 'q-eq.json').read_text())['rows']
        self.assertEqual(eq[0][1], 2000)


if __name__ == '__main__':
    unittest.main()
