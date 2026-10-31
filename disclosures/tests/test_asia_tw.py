"""asia_tw.py: the 主要進銷貨客戶名單 table read from real annual-report text (pdftotext -layout
excerpts of the FY2025 / 民國114年 reports), units, latest-year choice, and the fetch flow (offline)."""
import json
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import asia_tw as T  # noqa: E402

FIX = Path(__file__).resolve().parent / 'fixtures' / 'asia' / 'tw'


def fx(name):
    return (FIX / name).read_text(encoding='utf-8')


def rows(out, role):
    return {r['label']: r for r in out['rows'] if r['role'] == role}


class RealReports(unittest.TestCase):
    def test_honhai_anonymous_millions(self):
        out = T.parse(fx('2317_honhai_2025.txt'), code='2317', name='鴻海', name_en='HON HAI')
        self.assertEqual(out['fy'], 2025)                      # 114 年 column, not 113
        self.assertEqual(out['currency'], 'TWD')
        c, s = rows(out, 'customer'), rows(out, 'supplier')
        self.assertEqual(set(c), {'戊客戶'})
        self.assertEqual(c['戊客戶']['amount'], 3_574_256 * 1_000_000)   # 單位：新台幣佰萬元
        self.assertAlmostEqual(c['戊客戶']['share'], 0.4411)
        self.assertTrue(c['戊客戶']['anonymous'])
        self.assertEqual(s['L廠商']['amount'], 2_348_108 * 1_000_000)
        self.assertAlmostEqual(s['L廠商']['share'], 0.3699)
        self.assertEqual(out['revenue'], 8_103_105 * 1_000_000)          # 銷貨淨額 114 年
        self.assertEqual(out['purchases'], 6_348_541 * 1_000_000)
        self.assertAlmostEqual(out['concentration']['top1_sales'], 0.4411)
        self.assertIn('戊客戶', c['戊客戶']['sentence'])
        self.assertLessEqual(len(c['戊客戶']['sentence']), 400)
        self.assertTrue(all(r['year'] == 2025 for r in out['rows']))

    def test_mediatek_letters_and_not_applicable(self):
        out = T.parse(fx('2454_mediatek_2025.txt'), code='2454')
        c, s = rows(out, 'customer'), rows(out, 'supplier')
        # 客戶 D was >10% only in 113 (114 cell 不適用) → not a 114 row; 客戶 A only in 114
        self.assertEqual(set(c), {'客戶A', '客戶B', '客戶C'})
        self.assertEqual(c['客戶A']['amount'], 92_314_595_000)            # 仟元
        self.assertAlmostEqual(c['客戶A']['share'], 0.1549)
        self.assertEqual(c['客戶C']['amount'], 67_798_735_000)
        self.assertEqual(set(s), {'廠商A'})                                # 廠商 B 114 = 不適用
        self.assertAlmostEqual(s['廠商A']['share'], 0.7057)
        self.assertEqual(c['客戶B'].get('relation'), '非關係人')
        self.assertTrue(all(r['anonymous'] for r in out['rows']))
        self.assertEqual(out['revenue'], 595_965_682_000)
        self.assertEqual(out['concentration']['n_10pct_sales'], 3)

    def test_largan_numeric_codes_and_ytd_column_skipped(self):
        out = T.parse(fx('3008_largan_2025.txt'), code='3008')
        self.assertEqual(out['fy'], 2025)                                  # not 115 年度截至第一季止
        c, s = rows(out, 'customer'), rows(out, 'supplier')
        self.assertEqual(set(c), {'653021', '632019', '643006', '622020'})
        self.assertEqual(c['653021']['amount'], 18_338_766_000)
        self.assertAlmostEqual(c['653021']['share'], 0.30)
        # rows whose 113 cells are blank sit under the 114 column by position
        self.assertEqual(c['643006']['amount'], 8_140_234_000)
        self.assertEqual(c['622020']['amount'], 6_968_626_000)
        self.assertEqual(c['632019']['amount'], 9_292_586_000)
        self.assertEqual(s['100107']['amount'], 2_942_352_000)
        self.assertEqual(s['110185']['amount'], 1_387_913_000)
        self.assertTrue(all(r['anonymous'] for r in out['rows']))
        self.assertEqual(out['revenue'], 61_147_888_000)                   # 銷貨淨額 over three lines

    def test_finetek_tpex_three_columns(self):
        out = T.parse(fx('4549_finetek_2025.txt'), code='4549')
        c, s = rows(out, 'customer'), rows(out, 'supplier')
        self.assertEqual(c['甲客戶']['amount'], 299_552_000)
        self.assertAlmostEqual(c['甲客戶']['share'], 0.2424)
        self.assertEqual(s['A供應商']['amount'], 104_323_000)
        self.assertTrue(c['甲客戶']['anonymous'] and s['A供應商']['anonymous'])
        self.assertEqual(out['revenue'], 1_235_729_000)

    def test_delta_no_counterparty_over_ten_percent(self):
        out = T.parse(fx('2308_delta_2025.txt'), code='2308')
        self.assertTrue(out['found'])
        self.assertEqual(out['rows'], [])
        self.assertEqual(out['fy'], 2025)
        self.assertTrue(out['concentration']['none_over_10pct_sales'])
        self.assertTrue(out['concentration']['none_over_10pct_purchases'])
        self.assertIsNone(out['revenue'])


NAMED = '''(四)最近二年度任一年度中曾占進(銷)貨總額百分之十以上之客戶名稱及其進(銷)貨金額與比例
 2.最近二年度主要銷貨客戶資料
                                                        單位：新台幣仟元
          113 年度                                114 年度
項目  名稱          金額      占全年度  與發行人   名稱          金額      占全年度  與發行人
                              比率(%)  之關係                               比率(%)  之關係
 1   台灣積體電路   1,234,567    35.12   無        台灣積體電路   1,500,000    40.00   無
     製造(股)公司                                  製造(股)公司
 2   Apple Inc.      456,789     13.00   無        Apple Inc.      300,000      8.00   無
     其他          1,823,644     51.88             其他          1,950,000    52.00
     銷貨淨額      3,515,000    100.00             銷貨淨額      3,750,000   100.00
 1.最近二年度主要進貨廠商資料                               單位：新台幣百萬元
年度    供應商名稱      金額       占進貨淨額比率   與發行人之關係
113年   乙公司       820    22.10%          無
114年   乙公司       910    24.30%          本公司之子公司
114年   信越化學工業 400    10.70%          無
三、最近二年度從業員工人數
'''


class Layouts(unittest.TestCase):
    """Named counterparties, wrapped names and the year-per-row layout (constructed in the
    mandated format: no real named excerpt could be fetched from the sandbox)."""

    def test_named_wrapped_and_stacked(self):
        out = T.parse(NAMED)
        c, s = rows(out, 'customer'), rows(out, 'supplier')
        self.assertEqual(c['台灣積體電路製造(股)公司']['amount'], 1_500_000_000)
        self.assertFalse(c['台灣積體電路製造(股)公司']['anonymous'])
        self.assertEqual(c['Apple Inc.']['share'], 0.08)
        self.assertEqual(s['乙公司']['amount'], 910_000_000)
        self.assertTrue(s['乙公司']['anonymous'])
        self.assertEqual(s['乙公司']['relation'], '本公司之子公司')
        self.assertEqual(s['信越化學工業']['amount'], 400_000_000)
        self.assertEqual(out['revenue'], 3_750_000_000)

    def test_anonymous_labels(self):
        for lab in ('甲客戶', '客戶A', '客戶 B', 'A公司', 'L 廠商', '戊', '653021', 'Customer A', '供應商甲', 'B', 'AB客戶'):
            self.assertTrue(T.anonymous(lab), lab)
        for lab in ('台積電', 'Apple Inc.', '鴻海精密工業股份有限公司', 'Dell', '信越化學工業', 'HP Inc.', 'HP', 'LG'):
            self.assertFalse(T.anonymous(lab), lab)

    def test_units(self):
        self.assertEqual(T._unit('單位：新台幣千元'), 1000)
        self.assertEqual(T._unit('單位:新臺幣仟元'), 1000)
        self.assertEqual(T._unit('單位：新台幣佰萬元'), 1_000_000)
        self.assertEqual(T._unit('單位：新台幣百萬元'), 1_000_000)
        self.assertEqual(T._unit('單位：新台幣元'), 1)
        self.assertEqual(T._unit('單位：美金千元'), 'foreign')


class FakeHttp:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def _hit(self, url, data):
        if isinstance(data, bytes):      # form posts arrive url-encoded
            data = {k: v[0] for k, v in parse_qs(data.decode()).items()}
        self.calls.append((url, data))
        for key, val in self.routes:
            if key(url, data or {}):
                return val.pop(0) if isinstance(val, list) else val
        return None

    def get(self, url, params=None, headers=None):
        return self._hit(url, params)

    def post(self, url, data=None, headers=None):
        return self._hit(url, data)


# t57sb01 answers in the shape doc.twse.com.tw serves (Big5 HTML; trimmed)
STEP1 = '''<html><body><table>
<tr><td>年度</td><td>資料類型</td><td>檔案名稱</td><td>檔案說明</td><td>上傳日期</td></tr>
<tr><td>114</td><td>F04 股東會年報</td><td><a href='javascript:readfile2("F","2317","2025_2317_20260519F04.pdf");'>2025_2317_20260519F04.pdf</a></td>
<td>114年度年報</td><td>115/05/19 17:40:01</td></tr>
<tr><td>114</td><td>F04 股東會年報</td><td><a href='javascript:readfile2("F","2317","2025_2317_20260520F14.pdf");'>2025_2317_20260520F14.pdf</a></td>
<td>英文版年報</td><td>115/05/20</td></tr>
</table></body></html>'''.encode('cp950')
STEP9 = b"<html><body><center><a href='/pdf/2025_2317_20260519F04_20260519_174001.pdf'>2025_2317_20260519F04.pdf</a></center></body></html>"
BLOCK = '<html><body>因為安全性考量，您所執行的頁面無法呈現。<BR>FOR SECURITY REASONS, THIS PAGE CAN NOT BE ACCESSED.</body></html>'.encode()


class Fetching(unittest.TestCase):
    def setUp(self):
        self.slept = []
        self._sleep = T.SLEEP
        T.SLEEP = self.slept.append

    def tearDown(self):
        T.SLEEP = self._sleep

    def test_list_reports_universe(self):
        http = FakeHttp([(lambda u, d: u == T.TWSE_LIST, (FIX / 'twse_t187ap03_L.json').read_bytes()),
                         (lambda u, d: u == T.TPEX_LIST, (FIX / 'tpex_t187ap03_O.json').read_bytes())])
        reps = T.list_reports(http, '2026-01-01', '2026-10-30')
        by = {r['code']: r for r in reps}
        self.assertEqual(by['2330']['name_en'], 'TSMC')
        self.assertEqual(by['2330']['name'], '台積電')
        self.assertEqual(by['2330']['fy'], 2025)
        self.assertEqual(by['4549']['board'], 'TPEx')
        self.assertEqual(by['4549']['name_en'], 'FineTek')
        self.assertIn('co_id=2317', by['2317']['url'])
        self.assertIn('year=114', by['2317']['url'])
        self.assertEqual(len(reps), len(by))
        self.assertTrue(all(set(r) >= {'id', 'code', 'name', 'name_en', 'filed', 'fy', 'url'} for r in reps))

    def test_latest_fy(self):
        self.assertEqual(T.latest_fy('2026-10-30'), 2025)
        self.assertEqual(T.latest_fy('2026-03-01'), 2024)

    def test_listing_and_link_parsing(self):
        files = T.annual_files(STEP1)
        self.assertEqual([f['file'] for f in files], ['2025_2317_20260519F04.pdf'])   # English one dropped
        self.assertEqual(files[0]['uploaded'], '2026-05-19')
        self.assertEqual(T.pdf_link(STEP9), 'https://doc.twse.com.tw/pdf/2025_2317_20260519F04_20260519_174001.pdf')

    def test_read_report_backs_off_on_block_page(self):
        text = fx('2317_honhai_2025.txt').encode('utf-8')
        http = FakeHttp([(lambda u, d: d.get('step') == '1', [BLOCK, STEP1]),
                         (lambda u, d: d.get('step') == '9', STEP9),
                         (lambda u, d: u.endswith('.pdf'), text)])
        out = T.read_report(http, {'code': '2317', 'name': '鴻海', 'name_en': 'HON HAI', 'fy': 2025})
        self.assertEqual(out['filed'], '2026-05-19')
        self.assertEqual(out['code'], '2317')
        self.assertEqual(rows(out, 'customer')['戊客戶']['amount'], 3_574_256_000_000)
        self.assertIn(10, self.slept)                     # the throttle page triggered a back-off
        self.assertTrue(T.blocked(BLOCK))
        self.assertFalse(T.blocked(STEP1))

    def test_read_report_none_when_unavailable(self):
        http = FakeHttp([])
        self.assertIsNone(T.read_report(http, {'code': '9999', 'fy': 2025}))


if __name__ == '__main__':
    unittest.main()
