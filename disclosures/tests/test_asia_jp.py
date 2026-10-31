"""asia_jp.py: major customers / suppliers read from Japanese annual reports (有価証券報告書, EDINET).

Fixtures (tests/fixtures/asia/jp/): the 主要な販売先 / 仕入先 sections of real 2025–2026 reports, text and table cells
copied from the official EDINET PDFs (disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/<docID>.pdf) — the .htm ones in
EDINET's inline-XBRL table markup, the .txt ones as a PDF's text reads. documents_*.json follow the EDINET API v2
書類一覧API response layout (spec ESE140206, 3-1-2-2). Runs offline."""
import io
import json
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import asia_jp as J  # noqa: E402

FX = Path(__file__).resolve().parent / 'fixtures' / 'asia' / 'jp'


def load(name):
    return (FX / name).read_bytes()


def rows_of(d, role='customer'):
    return [(r['label'], r['amount'], r['share']) for r in d['rows'] if r['role'] == role]


class Customers(unittest.TestCase):
    def test_ibiden_us_customers_latest_year_only(self):
        d = J.parse(load('ibiden_S100YC4B.htm'))
        # AMD (11.0% the year before, "−" this year: under 10%) is dropped
        self.assertEqual(rows_of(d), [('NVIDIA Corp.', 122_470_000_000, 0.294), ('Intel Corp.', 75_319_000_000, 0.181)])
        self.assertEqual(d['code'], 'E00775')
        self.assertEqual(d['name_en'], 'IBIDEN CO.,LTD.')
        self.assertEqual(d['fy'], '2026-03-31')
        self.assertEqual(d['currency'], 'JPY')
        self.assertEqual(d['revenue'], 416_201_000_000)   # consolidated, not the 274,342 non-consolidated figure
        self.assertEqual(d['concentration'], {'top1_sales': 0.294})
        r = d['rows'][0]
        self.assertEqual(r['year'], '2026-03-31')
        self.assertIn('122,470', r['sentence'])
        self.assertLessEqual(len(r['sentence']), 400)

    def test_tokyo_electron_two_single_year_tables(self):
        # one table per year, the year named in the paragraph above each; the 主要な顧客ごとの情報 note is not repeated
        d = J.parse(load('tel_S100YEOO.htm'))
        self.assertEqual(rows_of(d), [('Samsung Electronics Co., Ltd.', 368_079_000_000, 0.151),
                                      ('Taiwan Semiconductor Manufacturing Company Ltd.', 315_813_000_000, 0.129)])
        self.assertEqual(d['revenue'], 2_443_533_000_000)
        self.assertEqual(d['name_en'], 'Tokyo Electron Limited')

    def test_advantest_dashes_and_ifrs_revenue(self):
        d = J.parse(load('advantest_S100YKTA.htm'), code='E01950', name='株式会社アドバンテスト', fy='2026-03-31')
        self.assertEqual(rows_of(d), [('NVIDIA INTERNATIONAL, INC.', 228_273_000_000, 0.202),
                                      ('Taiwan Semiconductor Manufacturing Co., Ltd.', 124_922_000_000, 0.111)])
        self.assertEqual(d['revenue'], 1_128_610_000_000)   # RevenueIFRSSummaryOfBusinessResults
        self.assertEqual(d['code'], 'E01950')

    def test_klab_thousand_yen(self):
        d = J.parse(load('klab_S100XU7P.htm'))
        self.assertEqual(rows_of(d), [('Apple Inc.', 1_836_563_000, 0.268), ('Google Inc.', 1_645_096_000, 0.24),
                                      ('Xsolla (USA), Inc.', 862_721_000, 0.126)])
        self.assertEqual(d['revenue'], 6_856_276_000)   # scale="3"
        self.assertEqual(d['fy'], '2025-12-31')

    def test_drecom_pdf_text_with_wrapped_name(self):
        d = J.parse(load('drecom_S100YGW0.txt').decode('utf-8'), fy='2026-03-31')
        self.assertEqual(rows_of(d), [('Apple,Inc.', 4_742_341_000, 0.27),
                                      ('株式会社バンダイナムコエンターテインメント', 2_702_252_000, 0.153),
                                      ('Google LLC', 4_394_229_000, 0.25)])
        self.assertEqual({r['year'] for r in d['rows']}, {'2026-03-31'})
        self.assertIsNone(d['revenue'])

    def test_ifrs_prose_when_there_is_no_table(self):
        text = ('(6)主要な顧客に関する情報\n'
                '前連結会計年度において、外部顧客への売上高のうち連結損益計算書の売上高の10%以上を占める顧客\n'
                'グループはTaiwan Semiconductor Manufacturing Co., Ltd.及びSamsungグループであり、関連するセグ\n'
                'メントは、いずれも主にテストシステム事業であります。Taiwan Semiconductor Manufacturing Co.,\n'
                'Ltd.及びSamsungグループに対する売上高は、前連結会計年度においてはそれぞれ96,158百万円、87,734\n'
                '百万円であります。\n'
                '当連結会計年度において、外部顧客への売上高のうち連結損益計算書の売上高の10%以上を占める顧客\n'
                'グループはNVIDIAグループ及びTaiwan Semiconductor Manufacturing Co., Ltd.であり、関連するセグメ\n'
                'ントは、いずれも主にテストシステム事業であります。NVIDIAグループ及びTaiwan Semiconductor\n'
                'Manufacturing Co., Ltd.に対する売上高は、当連結会計年度においてはそれぞれ243,735百万円、\n'
                '124,922百万円であります。\n')  # Advantest S100YKTA, 連結財務諸表注記 6.セグメント情報 (6)
        d = J.parse(text, fy='2026-03-31')
        self.assertEqual(rows_of(d), [('NVIDIAグループ', 243_735_000_000, None),
                                      ('Taiwan Semiconductor Manufacturing Co., Ltd.', 124_922_000_000, None)])

    def test_segment_note_table_when_the_main_table_is_missing(self):
        page = load('tel_S100YEOO.htm').decode('utf-8')
        note = page[page.rindex('<p', 0, page.index('主要な顧客ごとの情報')):]
        d = J.parse('<html><body>' + note, fy='2026-03-31')
        self.assertEqual(rows_of(d), [('Samsung Electronics Co., Ltd.', 368_079_000_000, None),
                                      ('Taiwan Semiconductor Manufacturing Company Ltd.', 315_813_000_000, None)])


class Suppliers(unittest.TestCase):
    def test_tomen_devices_purchase_shares(self):
        d = J.parse(load('tomen_S100YJQ2.htm'))
        # the 'サムスングループ計' subtotal is not a counterparty
        self.assertEqual(rows_of(d, 'supplier'), [('日本サムスン株式会社', None, 0.315), ('上海三星半導体有限公司', None, 0.51),
                                                  ('サムスングループその他', None, 0.003)])
        self.assertEqual(rows_of(d), [('NEW H3C INFORMATION TECHNOLOGIES CO., LTD.', 77_877_000_000, 0.112)])
        self.assertEqual(d['concentration'], {'top1_sales': 0.112, 'top1_purchases': 0.51})
        self.assertEqual({r['year'] for r in d['rows']}, {'2026-03-31'})


class Omitted(unittest.TestCase):
    def test_bridgestone_no_customer_over_ten_percent(self):
        d = J.parse(load('bridgestone_S100XRPR.txt'))
        self.assertEqual(d['rows'], [])
        self.assertEqual(d['concentration'], {})
        self.assertIn('10％以上を占める相手先がない', d['note'])

    def test_under_ten_percent_note(self):
        for s in ('<p>（注）主な相手先別の販売実績及び当該販売実績の総販売実績に対する割合については、当該割合が100分の10'
                  '未満のため記載を省略しております。</p>',
                  '主な相手先別の販売実績及び総販売実績に対する割合は、総販売実績に対する割合が10％以上の相手先がないため、'
                  '記載を省略しております。'):
            d = J.parse(s)
            self.assertEqual(d['rows'], [])
            self.assertIn('記載を省略', d['note'])

    def test_receivables_breakdown_is_not_a_customer_list(self):
        doc = ('<html><body><p>ｂ　売掛金</p><p>相手先別内訳</p><table><tr><td><p>相手先</p></td><td><p>金額(百万円)</p>'
               '</td></tr><tr><td><p>Apple Inc.</p></td><td><p>12,345</p></td></tr></table></body></html>')
        self.assertEqual(J.parse(doc)['rows'], [])


class Numbers(unittest.TestCase):
    def test_num(self):
        self.assertEqual(J.num('1,234'), 1234.0)
        self.assertEqual(J.num('△1.8'), -1.8)
        self.assertEqual(J.num('１２，３４５'), 12345.0)
        for s in ('－', '-', '―', '−', '', '※'):
            self.assertIsNone(J.num(s))

    def test_top5_sentence(self):
        d = J.parse('売上高上位５社に対する売上高の割合は62.5％であります。')
        self.assertEqual(d['concentration'], {'top5_sales': 0.625})
        # Advantest S100YKTA (事業等のリスク): two years in one sentence → the current one
        d = J.parse('顧客上位5社による売上高は、前連結会計年度の売上高全体の約48%及び当連結会計年度の同約50%を占めています。')
        self.assertEqual(d['concentration'], {'top5_sales': 0.5})


class FakeHttp:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, params=None, headers=None):
        self.calls.append((url, dict(params or {})))
        return self.routes(url, params or {})


class Listing(unittest.TestCase):
    def setUp(self):
        self.pause, J.PAUSE = J.PAUSE, 0

    def tearDown(self):
        J.PAUSE = self.pause

    def test_list_reports(self):
        def routes(url, params):
            self.assertTrue(url.endswith('/api/v2/documents.json'))
            p = FX / f"documents_{params['date']}.json"
            if p.exists():
                return p.read_bytes()
            return json.dumps({'metadata': {'status': '200', 'resultset': {'count': 0}}, 'results': []}).encode()
        http = FakeHttp(routes)
        reps = J.list_reports(http, '2026-06-18', '2026-06-25', key='KEY')
        self.assertEqual(len(http.calls), 8)   # one call per day
        self.assertEqual(http.calls[0][1], {'date': '2026-06-18', 'type': 2, 'Subscription-Key': 'KEY'})
        # kept: the two 有価証券報告書; dropped: 確認書, a fund's report, a correction (130), a withdrawn report,
        # a 半期報告書 and the repeated "information edited" entry
        self.assertEqual([r['id'] for r in reps], ['S100YC4B', 'S100YJQ2'])
        r = reps[0]
        self.assertEqual((r['code'], r['ticker'], r['name'], r['filed'], r['fy']),
                         ('E00775', '4062', 'イビデン株式会社', '2026-06-18', '2026-03-31'))
        self.assertTrue(r['url'].endswith('S100YC4B'))
        self.assertIsNone(r['name_en'])

    def test_unauthorised_day_is_skipped(self):
        http = FakeHttp(lambda u, p: b'{"StatusCode": 401, "message": "Access denied due to invalid subscription key."}')
        self.assertEqual(J.list_reports(http, '2026-06-18', '2026-06-18'), [])


class Reading(unittest.TestCase):
    def zip_of(self, files):
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w') as z:
            for name, data in files.items():
                z.writestr(name, data)
        return b.getvalue()

    def test_read_report_from_type1_zip(self):
        z = self.zip_of({
            'XBRL/PublicDoc/0102010_honbun_jpcrp030000-asr-001_E00775-000_2026-03-31_01_2026-06-18_ixbrl.htm':
                load('ibiden_S100YC4B.htm'),
            'XBRL/PublicDoc/manifest_PublicDoc.xml': b'<manifest/>',
            'XBRL/AuditDoc/jpaud-aar-cn-001_E00775-000_2026-03-31_01_2026-06-18_ixbrl.htm': b'<html><body/></html>',
        })
        seen = []

        def routes(url, params):
            seen.append((url, params))
            return z
        rep = {'id': 'S100YC4B', 'code': 'E00775', 'name': 'イビデン株式会社', 'fy': '2026-03-31'}
        d = J.read_report(FakeHttp(routes), rep, key='KEY')
        self.assertEqual(seen, [('https://api.edinet-fsa.go.jp/api/v2/documents/S100YC4B', {'type': 1, 'Subscription-Key': 'KEY'})])
        self.assertEqual([r['label'] for r in d['rows']], ['NVIDIA Corp.', 'Intel Corp.'])
        self.assertEqual(d['name_en'], 'IBIDEN CO.,LTD.')
        self.assertEqual(d['revenue'], 416_201_000_000)

    def test_read_report_errors(self):
        rep = {'id': 'S100XXXX'}
        self.assertIsNone(J.read_report(FakeHttp(lambda u, p: None), rep))
        err = b'{"metadata": {"title": "", "status": "404", "message": "Not Found"}}'
        self.assertIsNone(J.read_report(FakeHttp(lambda u, p: err), rep))


if __name__ == '__main__':
    unittest.main()
