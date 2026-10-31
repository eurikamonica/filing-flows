"""asia_hk.py: the "Major customers and suppliers" disclosure (Listing Rules App. D2 para 31) read from
HKEXnews annual reports. Offline: the fixtures are the pdftotext -layout text of the relevant pages of real
FY2025 reports (the section plus the income-statement revenue row), and two real title-search answers."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import asia_hk as H  # noqa: E402

FX = Path(__file__).resolve().parent / 'fixtures' / 'asia' / 'hk'


def load(name):
    return (FX / name).read_text(encoding='utf-8')


# fixture -> (fy, currency, revenue, top1_sales, top5_sales, top1_purchases, top5_purchases, bounds, named rows)
CASES = {
    # two-column page, the section in the right-hand column of the MD&A; Home Depot is not named in the report
    '00669_techtronic_2025.txt': (2025, 'USD', 15_259_533_000, 0.454, 0.533, 0.05, 0.156, {}, []),
    # bilingual page, chart call-outs on the right; BYD named as one of the five largest customers and suppliers
    '00285_byd_electronic_2025.txt': (2025, 'CNY', 179_477_404_000, 0.5545, 0.8511, 0.427, 0.594, {},
                                      [('customer', 'BYD', None), ('supplier', 'BYD', None)]),
    # comparatives in the same sentence: '(2024: approximately 46.2%)', 'as compared to approximately 15.8% of last year'
    '02382_sunny_optical_2025.txt': (2025, 'CNY', 43_229_126_000, 0.113, 0.451, 0.162, 0.336, {}, []),
    '02018_aac_technologies_2025.txt': (2025, 'CNY', 31_816_988_000, 0.323, 0.725, 0.066, 0.22, {}, []),
    # 'sold less than 27% ... to its five largest customers' plus a two-row supplier table
    '00992_lenovo_2025_26.txt': (2026, 'USD', 83_074_555_000, None, None, 0.10, 0.39,
                                 {'top5_sales': ('<', 0.27)}, []),
    '01810_xiaomi_2025.txt': (2025, 'CNY', 457_286_687_000, 0.085, 0.131, 0.121, 0.309, {}, []),
    # small concentration; revenue is the unlabelled total under a 'Revenues' heading
    '00700_tencent_2025.txt': (2025, 'CNY', 751_766_000_000, 0.034, 0.065, 0.044, 0.188, {}, []),
    # a table with Sales / Purchases columns for 2025 and 2024
    '02020_anta_sports_2025.txt': (2025, 'CNY', 80_219_000_000, 0.038, 0.073, 0.037, 0.146, {}, []),
    # 'less than 30% of the Group's sales and less than 30% of the Group's purchases ... respectively'
    '00016_shk_properties_2025_26.txt': (2026, 'HKD', 94_194_000_000, None, None, None, None,
                                         {'top5_sales': ('<', 0.30), 'top5_purchases': ('<', 0.30)}, []),
    # bilingual, English in the right-hand column under a centred heading
    '00291_cr_beer_2025.txt': (2025, 'CNY', 37_985_000_000, None, None, None, None,
                               {'top5_sales': ('<', 0.30), 'top5_purchases': ('<', 0.30)}, []),
    # 'The largest customer is Tencent, which is a substantial shareholder of the Company.'
    '01022_feiyu_2025.txt': (2025, 'CNY', 810_239_000, 0.018, 0.037, 0.118, 0.214, {},
                             [('customer', 'Tencent', 0.018)]),
    # bullet list 'the largest supplier: 9%'; GM named in the credit-risk note, outside the section
    '01316_nexteer_2025.txt': (2025, 'USD', 4_584_217_000, 0.34, 0.76, 0.09, 0.25, {},
                               [('customer', 'General Motors Company', 0.34)]),
    # one table row for both sides: 'The largest supplier/customer   17.39   29.30' under procurement / sales columns
    '02313_shenzhou_2025.txt': (2025, 'CNY', 30_993_732_000, 0.293, 0.8648, 0.1739, 0.3065, {}, []),
}


class FixtureTest(unittest.TestCase):
    def test_fixtures(self):
        for name, (fy, cur, rev, t1s, t5s, t1p, t5p, bounds, rows) in CASES.items():
            with self.subTest(name):
                r = H.parse(load(name), code=name[:5])
                c = r['concentration']
                self.assertEqual(r['code'], name[:5])
                self.assertEqual(r['fy'], fy)
                self.assertEqual(r['currency'], cur)
                self.assertAlmostEqual(r['revenue'], rev, delta=1)
                for f, want in zip(H.FIELDS, (t1s, t5s, t1p, t5p)):
                    if want is None:
                        self.assertIsNone(c[f], f)
                    else:
                        self.assertAlmostEqual(c[f], want, places=6, msg=f)
                got_bounds = {f: (b['op'], b['value']) for f, b in c.get('bounds', {}).items()}
                self.assertEqual(got_bounds, bounds)
                self.assertEqual([(x['role'], x['label'], x['share']) for x in r['rows']], rows)
                self.assertTrue(c['sentences'])
                for x in r['rows']:
                    self.assertLessEqual(len(x['sentence']), 400)
                    self.assertEqual(x['year'], fy)
                    self.assertIn(x['role'], ('customer', 'supplier'))

    def test_sentences_kept_for_bounds(self):
        c = H.parse(load('00016_shk_properties_2025_26.txt'))['concentration']
        self.assertTrue(any('less than 30%' in s for s in c['sentences']))


class SentenceTest(unittest.TestCase):
    """Wordings as filed (FY2025 directors' reports)."""

    def read(self, text):
        r = H.parse('MAJOR CUSTOMERS AND SUPPLIERS\n' + text + '\n', fy=2025)
        c = r['concentration']
        return {f: c[f] for f in H.FIELDS if c[f] is not None}, \
            {f: (b['op'], b['value']) for f, b in c.get('bounds', {}).items()}, r['rows']

    def test_less_than_30_both(self):
        vals, bounds, _ = self.read(
            'During the year, the Group purchased less than 30% of its goods and services from its 5 largest\n'
            'suppliers and sold less than 30% of its goods to its 5 largest customers.')
        self.assertEqual(vals, {})
        self.assertEqual(bounds, {'top5_purchases': ('<', 0.3), 'top5_sales': ('<', 0.3)})

    def test_less_than_30_one_figure_two_sides(self):
        vals, bounds, _ = self.read(
            'During the year, the respective percentage of purchases attributable to the Group’s five largest\n'
            'suppliers combined and the revenue from sales of goods or rendering of services attributable to the\n'
            'Group’s five largest customers combined was less than 30% of the total purchases and revenue.')
        self.assertEqual(bounds, {'top5_purchases': ('<', 0.3), 'top5_sales': ('<', 0.3)})

    def test_pair_respectively(self):
        vals, bounds, _ = self.read(
            'During the year ended 31 December 2025, the percentage of the Group’s revenue attributable to the\n'
            'Group’s largest customer and the five largest customers in aggregate were approximately 98.7% and\n'
            '99.9% respectively (2024: 98.3% and 99.8%). During the year ended 31 December 2025, the percentage of\n'
            'the Group’s purchases attributable to the Group’s largest supplier and the five largest suppliers in\n'
            'aggregate were approximately 66.1% and approximately 81.1% (2024: 69.0% and 85.2%) respectively.')
        self.assertEqual(vals, {'top1_sales': 0.987, 'top5_sales': 0.999, 'top1_purchases': 0.661, 'top5_purchases': 0.811})
        self.assertEqual(bounds, {})

    def test_elliptic_largest_and_top_five(self):
        vals, _, _ = self.read(
            'For the year ended 31 December 2025, the largest and top five customers of the Group accounted for\n'
            'approximately 32.7% and 65.0% of the total revenue of the Group respectively (2024: 19.4% and 56.1%).\n\n'
            'The aggregate purchases during the year attributable to the Group’s largest and top five suppliers were\n'
            'approximately 12.6% and 37.4% of the Group’s total purchases respectively (2024: 19.2% and 67.3%).')
        self.assertEqual(vals, {'top1_sales': 0.327, 'top5_sales': 0.65, 'top1_purchases': 0.126, 'top5_purchases': 0.374})

    def test_prior_year_in_text(self):
        vals, _, _ = self.read(
            'In 2025, the revenue from the largest customer accounted for approximately 11.3% of the Group’s total\n'
            'revenue as compared to approximately 15.8% of last year.')
        self.assertEqual(vals, {'top1_sales': 0.113})

    def test_interest_sentence_ignored(self):
        vals, bounds, _ = self.read(
            'None of the Directors, their close associates or any shareholder (which to the knowledge of the\n'
            'Directors owns more than 5% of the Company’s issued share capital) had any interest in the Group’s\n'
            'five largest customers or suppliers.')
        self.assertEqual((vals, bounds), ({}, {}))

    def test_named_largest_customer(self):
        vals, _, rows = self.read(
            'Sales to the Group’s largest customer, Apple Inc., accounted for approximately 41.2% of the Group’s\n'
            'total revenue and sales to the five largest customers accounted for approximately 70.3%.')
        self.assertEqual(vals, {'top1_sales': 0.412, 'top5_sales': 0.703})
        self.assertEqual([(r['role'], r['label'], r['share']) for r in rows], [('customer', 'Apple Inc.', 0.412)])

    def test_no_section(self):
        r = H.parse('Chairman’s Statement\nThe Group recorded revenue growth in 2025.\n')
        self.assertFalse(r['found'])
        self.assertEqual(r['rows'], [])
        self.assertTrue(all(r['concentration'][f] is None for f in H.FIELDS))


class ListingTest(unittest.TestCase):
    def setUp(self):
        self._interval = H.MIN_INTERVAL
        H.MIN_INTERVAL = 0

    def tearDown(self):
        H.MIN_INTERVAL = self._interval

    def test_list_reports(self):
        en = (FX / 'search_en_20260409.json').read_bytes()
        zh = (FX / 'search_zh_20260409.json').read_bytes()
        calls = []

        class Http:
            def get(self, url, params=None, headers=None):
                calls.append((url, dict(params or {})))
                return en if params.get('lang') == 'E' else zh

            def post(self, url, data=None, headers=None):
                raise AssertionError('no POST')

        reps = H.list_reports(Http(), '2026-04-09', '2026-04-09')
        self.assertEqual(len(reps), 19)
        self.assertEqual({c[1]['lang'] for c in calls}, {'E', 'ZH'})
        p = calls[0][1]
        self.assertEqual((p['t1code'], p['t2code'], p['fromDate'], p['toDate'], p['searchType']),
                         ('40000', '40100', '20260409', '20260409', '1'))
        by = {r['code']: r for r in reps}
        t = by['00700']
        self.assertEqual((t['name_en'], t['name'], t['fy'], t['filed']), ('TENCENT', '騰訊控股', 2025, '2026-04-09'))
        self.assertEqual(t['url'], 'https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0409/2026040901231.pdf')
        self.assertEqual(by['02020']['name'], '安踏體育')
        for r in reps:
            self.assertRegex(r['code'], r'^\d{5}$')
            self.assertTrue(r['id'] and r['url'].endswith('.pdf'))
            self.assertNotIn('_c.pdf', r['url'])

    def test_row_filters(self):
        base = {'NEWS_ID': '1', 'STOCK_CODE': '00700', 'STOCK_NAME': 'TENCENT', 'DATE_TIME': '26/06/2026 16:38',
                'FILE_LINK': '/listedco/listconews/sehk/2026/0626/x.pdf'}
        self.assertIsNone(H.row_to_report(dict(base, TITLE='INTERIM REPORT 2026')))
        self.assertIsNone(H.row_to_report(dict(base, TITLE='Environmental, Social and Governance Report 2025')))
        self.assertIsNone(H.row_to_report(dict(base, TITLE='Annual Report 2025 (Chinese Version)')))
        self.assertIsNone(H.row_to_report(dict(base, TITLE='AUDITED ACCOUNTS AS AT 31 DECEMBER 2025')))
        self.assertIsNotNone(H.row_to_report(dict(base, TITLE='Annual Report 2025 and ESG Report')))
        self.assertEqual(H.row_to_report(dict(base, TITLE='2025&#x2f;26 ANNUAL REPORT'))['fy'], 2026)

    def test_stock_id(self):
        raw = (FX / 'prefix_00669.jsonp').read_bytes()

        class Http:
            def get(self, url, params=None, headers=None):
                return raw

        self.assertEqual(H.stock_id(Http(), '669'), 1557)


class ReadReportTest(unittest.TestCase):
    def setUp(self):
        self._interval, self._pdf = H.MIN_INTERVAL, H.pdf_to_text
        H.MIN_INTERVAL = 0

    def tearDown(self):
        H.MIN_INTERVAL, H.pdf_to_text = self._interval, self._pdf

    def test_read_report_with_text_stub(self):
        text = load('01022_feiyu_2025.txt')
        H.pdf_to_text = lambda data, layout=True, timeout=180: text

        class Http:
            def get(self, url, params=None, headers=None):
                return b'%PDF-1.7 stub'

        rep = {'id': '1', 'code': '01022', 'name': '飛魚科技', 'name_en': 'FEIYU', 'fy': 2025, 'url': 'https://x/y.pdf'}
        r = H.read_report(Http(), rep)
        self.assertEqual((r['code'], r['name'], r['name_en'], r['fy'], r['currency']), ('01022', '飛魚科技', 'FEIYU', 2025, 'CNY'))
        self.assertAlmostEqual(r['concentration']['top5_purchases'], 0.214)
        self.assertEqual(r['rows'][0]['label'], 'Tencent')

    def test_read_report_not_pdf(self):
        class Http:
            def get(self, url, params=None, headers=None):
                return b'<html>not found</html>'

        self.assertIsNone(H.read_report(Http(), {'url': 'https://x/y.pdf'}))


if __name__ == '__main__':
    unittest.main()
