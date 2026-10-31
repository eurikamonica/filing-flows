"""asia_kr.py: major customers and suppliers from Korean annual reports (사업보고서) on DART — on trimmed real sections
from the DART viewer (fixtures/asia/kr/*.html, 2025 reports filed March 2026), a dart4-style document.xml zip, a
list.json answer and the public search page. Offline."""
import io
import json
import sys
import unittest
import urllib.parse
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import asia_kr as K  # noqa: E402

FX = Path(__file__).resolve().parent / 'fixtures' / 'asia' / 'kr'
K.MIN_INTERVAL = 0


def read(name, **meta):
    return K.parse((FX / name).read_bytes(), **meta)


def by(doc, role):
    return {r['label']: r for r in doc['rows'] if r['role'] == role}


class FakeHttp:
    """Answers by URL path; records every call."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, params=None, headers=None):
        self.calls.append((url, dict(params or {})))
        for key, ans in self.routes.items():
            if key in url:
                return ans(params or {}) if callable(ans) else ans
        return None


class TestCustomers(unittest.TestCase):
    def test_samsung_named_customers_and_top5(self):
        d = read('samsung.html')
        cust = by(d, 'customer')
        self.assertEqual(list(cust), ['Alphabet', 'Apple', 'Deutsche Telekom', 'Hong Kong Techtronics',
                                      'Supreme Electronics'])
        self.assertTrue(all(r['amount'] is None and r['share'] is None for r in cust.values()))
        self.assertAlmostEqual(d['concentration']['top5_sales'], 0.15)
        self.assertIsNone(d['concentration']['top1_sales'])
        self.assertEqual(cust['Apple']['year'], 2025)
        self.assertIn('주요 매출처는 Alphabet', cust['Apple']['sentence'])
        self.assertEqual(d['revenue'], 333_605_938e6)
        self.assertEqual(d['fy'], '2025-12-31')
        self.assertEqual(d['currency'], 'KRW')

    def test_skhynix_describes_customers_without_names(self):
        d = read('skhynix.html', fy='2025-12-31')
        self.assertEqual(d['rows'], [])
        self.assertEqual(d['revenue'], 97_146_675e6)
        self.assertTrue(all(v is None for v in d['concentration'].values()))

    def test_lg_display_lettered_customers_with_amounts(self):
        d = read('lgdisplay.html')
        cust = by(d, 'customer')
        self.assertEqual(list(cust), ['"가"사', '"나"사'])
        self.assertEqual(cust['"가"사']['amount'], 14_835_862e6)       # not the 2024 figure in brackets
        self.assertEqual(cust['"나"사']['amount'], 3_412_768e6)
        self.assertTrue(cust['"가"사']['anonymous'])
        self.assertTrue(cust['"가"사']['share_derived'])
        self.assertAlmostEqual(cust['"가"사']['share'], 14_835_862 / 25_810_082, places=3)
        self.assertAlmostEqual(d['concentration']['top10_sales'], 0.92)
        self.assertAlmostEqual(d['concentration']['top1_sales'], 0.5748, places=3)

    def test_lg_innotek_single_unnamed_customer(self):
        d = read('lginnotek.html')
        self.assertEqual(by(d, 'customer'), {})
        c = d['concentration']
        self.assertEqual(c['top1_sales_amount'], 17_748_770e6)
        self.assertAlmostEqual(c['top1_sales'], 17_748_770 / 21_896_603, places=3)
        self.assertAlmostEqual(c['top10_sales'], 0.87)

    def test_semco_single_customer_share(self):
        d = read('semco.html')
        cust = by(d, 'customer')
        self.assertEqual(list(cust), ['삼성전자'])                    # '삼성전자와 그 종속회사' → 삼성전자
        self.assertAlmostEqual(cust['삼성전자']['share'], 0.27)
        self.assertAlmostEqual(d['concentration']['top1_sales'], 0.27)
        self.assertIn('삼성전자', by(d, 'supplier'))                   # also its sensor-IC supplier

    def test_mobis_shares_in_order(self):
        d = read('mobis.html')
        cust = by(d, 'customer')
        self.assertEqual(list(cust), ['현대자동차', '기아'])
        self.assertAlmostEqual(cust['현대자동차']['share'], 0.394)
        self.assertAlmostEqual(cust['기아']['share'], 0.358)
        self.assertAlmostEqual(d['concentration']['top1_sales'], 0.394)

    def test_lg_energy_solution_top5_only(self):
        d = read('lgensol.html')
        self.assertEqual(by(d, 'customer'), {})
        self.assertAlmostEqual(d['concentration']['top5_sales'], 0.63)

    def test_samsung_sdi_names_with_aliases(self):
        d = read('samsungsdi.html')
        self.assertEqual(list(by(d, 'customer')),
                         ['Bayerische Motoren Werke', 'Volkswagen Group', '삼성전자', 'Stellantis', 'AES'])
        self.assertEqual(d['revenue'], 13_266_731e6)

    def test_lnf_external_customer_table(self):
        d = read('lnf.html')
        cust = by(d, 'customer')
        self.assertEqual(list(cust), ['외부고객1', '외부고객2'])
        self.assertAlmostEqual(cust['외부고객1']['share'], 0.88)       # this year, not last year's 85%
        self.assertAlmostEqual(cust['외부고객2']['share'], 0.12)
        self.assertTrue(cust['외부고객1']['anonymous'])

    def test_isu_petasys_transposed_table(self):
        d = read('isupetasys.html')
        a = by(d, 'customer')['A사']
        self.assertEqual(a['amount'], 447_470e6)
        self.assertAlmostEqual(a['share'], 0.4113)
        self.assertAlmostEqual(d['concentration']['top1_sales'], 0.4113)

    def test_ecopro_bm_combined_share(self):
        d = read('ecoprobm.html')
        self.assertEqual(list(by(d, 'customer')), ['삼성SDI', 'SK온'])
        self.assertAlmostEqual(d['concentration']['named_sales'], 0.923)
        self.assertEqual(d['revenue'], 2_531_576_384_113)             # 단위: 원

    def test_mcnex_and_bh_mixed_prose(self):
        self.assertEqual(list(by(read('mcnex.html'), 'customer')), ['삼성전자', '현대자동차', '현대모비스', 'LG전자'])
        self.assertEqual(list(by(read('bh.html'), 'customer')), ['삼성 디스플레이'])

    def test_section_without_names_gives_no_rows(self):
        text = ('<P>마. 주요 매출처</P><P>당사의 주요 매출처는 국내외 완성차 업체 및 글로벌 IT 기업으로, 특정 고객에 대한 '
                '의존도는 높지 않습니다.</P><P>당사는 일본, 한국 등에 생산시설을 보유한 업계의 주요 공급사로부터 '
                '웨이퍼를 공급받고 있습니다.</P>')
        d = K.parse(text)
        self.assertEqual(d['rows'], [])


class TestSuppliers(unittest.TestCase):
    def test_samsung_material_table_and_prose(self):
        sup = by(read('samsung.html'), 'supplier')
        for n in ('Qualcomm', 'MediaTek', '삼성전기', 'CSOT', '솔브레인', 'SILTRONIC', 'SK실트론', '비에이치', 'Apple',
                  'NVIDIA', 'Intel', 'WNC'):
            self.assertIn(n, sup)
        q = sup['Qualcomm']
        self.assertIsNone(q['amount'])                                # the amount is the item's, not Qualcomm's
        self.assertEqual(q['items'][0]['item'], '모바일AP 솔루션')
        self.assertEqual(q['items'][0]['amount'], 138_272e8)          # 억원
        self.assertAlmostEqual(q['items'][0]['share'], 0.185)
        self.assertEqual(sup['Apple']['items'][0]['item'], 'Cover Glass')
        self.assertEqual(len([k for k in sup if k.startswith('WNC')]), 1)

    def test_lg_innotek_current_year_column(self):
        sup = by(read('lginnotek.html'), 'supplier')
        sony = sup['Sony']['items'][0]
        self.assertEqual((sony['item'], sony['amount'], sony['share']), ('Image Sensor', 6_436_276e6, 0.41))
        self.assertIn('Mitsubishi Gas Chemical', sup)

    def test_companies_with_commas_in_names(self):
        sup = by(read('mcnex.html'), 'supplier')
        self.assertIn('LARGAN PRECISION Co., Ltd', sup)
        self.assertIn('JIANGXI LIAN CHUANG ELECTRONIC Co., Ltd', sup)
        self.assertIn('SAMT SG PTE.LTD', sup)

    def test_amount_with_share_in_one_cell(self):
        sup = by(read('bh.html'), 'supplier')
        self.assertEqual({i['item'] for i in sup['두산']['items']}, {'CCL', 'B/S'})
        ccl = [i for i in sup['두산']['items'] if i['item'] == 'CCL'][0]
        self.assertEqual((ccl['amount'], ccl['share']), (19_749e6, 0.349))

    def test_mobis_prose_suppliers(self):
        self.assertEqual(list(by(read('mobis.html'), 'supplier')), ['POSCO', '현대제철', '현대EP', 'GS칼텍스', '삼양사'])

    def test_lg_energy_solution_and_others(self):
        sup = by(read('lgensol.html'), 'supplier')
        self.assertEqual(list(sup)[:3], ['LG화학', '포스코퓨처엠', 'Nichia'])   # ㈜ dropped
        self.assertIn('L&F', sup)
        self.assertIn('동우화인켐', by(read('lgdisplay.html'), 'supplier'))
        self.assertIn('유미코아', by(read('samsungsdi.html'), 'supplier'))
        isu = by(read('isupetasys.html'), 'supplier')
        self.assertEqual([i['item'] for i in isu['PANASONIC']['items']], ['THIN CORE', 'PREPREG'])

    def test_no_supplier_from_industry_description(self):
        self.assertEqual(by(read('skhynix.html'), 'supplier'), {})

    def test_rows_shape(self):
        for f in FX.glob('*.html'):
            for r in K.parse(f.read_bytes())['rows']:
                self.assertIn(r['role'], ('customer', 'supplier'))
                self.assertLessEqual(len(r['sentence']), 400)
                self.assertTrue(r['share'] is None or 0 <= r['share'] <= 1)
                self.assertEqual(set(r) >= {'role', 'label', 'amount', 'share', 'year', 'sentence'}, True)


class TestXml(unittest.TestCase):
    def test_document_zip(self):
        raw = (FX / 'mobis_document.zip').read_bytes()
        d = K.parse(raw, rcept_no='20260309001878')
        self.assertEqual(d['code'], '00164788')
        self.assertEqual(d['name'], '현대모비스')
        self.assertEqual(d['revenue'], 61_118_127e6)
        self.assertEqual(d['fy'], '2025-12-31')
        cust, sup = by(d, 'customer'), by(d, 'supplier')
        self.assertAlmostEqual(cust['현대자동차']['share'], 0.394)
        self.assertEqual(list(sup), ['POSCO', '현대제철', '현대EP', 'GS칼텍스', '삼양사'])

    def xml(self):
        z = zipfile.ZipFile(io.BytesIO((FX / 'mobis_document.zip').read_bytes()))
        return z.read('20260309001878.xml').decode('utf-8')

    def test_euc_kr_and_later_sections_ignored(self):
        x = self.xml().replace('encoding="utf-8"', 'encoding="euc-kr"')
        x = x.replace('</BODY>', '<SECTION-1><TITLE>X. 대주주 등과의 거래내용</TITLE><P>회사의 주요 매출처는 '
                                 '현대글로비스입니다.</P></SECTION-1></BODY>')
        d = K.parse(x.encode('cp949'))
        self.assertNotIn('현대글로비스', by(d, 'customer'))
        self.assertIn('기아', by(d, 'customer'))

    def test_te_cells_and_titles(self):
        blocks, meta = K.normalise(self.xml())
        self.assertIn(('h', '4. 매출 및 수주상황'), blocks)
        tables = [b for k, b in blocks if k == 'table']
        self.assertTrue(any(c['t'] == '816' for t in tables for r in t for c in r))


class TestNumbers(unittest.TestCase):
    def test_units(self):
        self.assertEqual(K.money('333조 6,059억원'), 333.6059e12)
        self.assertEqual(K.money('14,835,862백만원'), 14_835_862e6)
        self.assertEqual(K.unit_of('(단위 : 억원, %)'), 1e8)
        self.assertEqual(K.unit_of('(단위: 백만원)'), 1e6)
        self.assertEqual(K.unit_of('(단위 : 원)'), 1.0)
        self.assertEqual(K.num('(1,234)'), -1234)
        self.assertEqual(K.pct('18.5%'), 0.185)
        self.assertEqual(K.fy_from_title('[기재정정]사업보고서 (2025.12)'), '2025-12-31')
        self.assertEqual(K.fy_from_title('사업보고서 (2026.03)'), '2026-03-31')


class TestListing(unittest.TestCase):
    def corp_zip(self):
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w') as z:
            z.writestr('CORPCODE.xml', (FX / 'corpcode_sample.xml').read_bytes())
        return b.getvalue()

    def test_list_json(self):
        K._corp_cache.clear()
        page = (FX / 'list_a001.json').read_bytes()
        http = FakeHttp({'corpCode.xml': self.corp_zip(), 'list.json': page})
        reps = K.list_reports(http, '2026-03-01', '2026-04-30', key='k')
        self.assertEqual(len(reps), 6)
        ss = [r for r in reps if r['code'] == '00126380'][0]
        self.assertEqual(ss['id'], '20260310002820')
        self.assertEqual(ss['name'], '삼성전자')
        self.assertEqual(ss['name_en'], 'SAMSUNG ELECTRONICS CO,.LTD')
        self.assertEqual(ss['filed'], '2026-03-10')
        self.assertEqual(ss['fy'], '2025-12-31')
        self.assertEqual(ss['stock_code'], '005930')
        self.assertEqual(ss['url'], 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260310002820')
        self.assertTrue([r for r in reps if r['code'] == '00105961'][0]['amended'])
        lists = [p for u, p in http.calls if 'list.json' in u]
        self.assertEqual(lists[0]['pblntf_ty'], 'A')
        self.assertEqual(lists[0]['pblntf_detail_ty'], 'A001')
        self.assertEqual((lists[0]['bgn_de'], lists[0]['end_de']), ('20260301', '20260430'))
        self.assertEqual(lists[0]['page_count'], '100')
        self.assertEqual(len(lists), 1)                               # 61 days: one window without corp_code

    def test_three_month_windows_and_no_data(self):
        K._corp_cache.clear()
        http = FakeHttp({'corpCode.xml': self.corp_zip(),
                         'list.json': json.dumps({'status': '013', 'message': '조회된 데이타가 없습니다.'}).encode()})
        self.assertEqual(K.list_reports(http, '2026-01-01', '2026-12-31', key='k'), [])
        wins = [(p['bgn_de'], p['end_de']) for u, p in http.calls if 'list.json' in u]
        self.assertEqual(len(wins), 5)
        self.assertEqual(wins[0], ('20260101', '20260331'))

    def test_public_search_without_key(self):
        page = (FX / 'search_20260310.html').read_bytes()
        http = FakeHttp({'detailSearch.ax': lambda p: page if p.get('currentPage') == '1' else b'<table></table>'})
        reps = K.list_reports(http, '2026-03-10', '2026-03-10', key='')
        self.assertEqual(len(reps), 15)
        self.assertTrue(all(r['fy'] == '2025-12-31' and r['filed'] == '2026-03-10' for r in reps))
        self.assertIn('00454937', {r['code'] for r in reps})
        self.assertEqual({r['corp_cls'] for r in reps} - {'Y', 'K', 'N', 'E', None}, set())


class TestReading(unittest.TestCase):
    def test_viewer_nodes(self):
        nodes = K.viewer_nodes((FX / 'mobis_main.html').read_text(encoding='utf-8'))
        picked = [n['text'] for n in K.pick_nodes(nodes)]
        self.assertIn('4. 매출 및 수주상황', picked)
        self.assertIn('1. 요약재무정보', picked)
        self.assertNotIn('5. 위험관리 및 파생거래', picked)
        self.assertNotIn('1. 회사의 개요', picked)
        n = [x for x in nodes if x['text'] == '4. 매출 및 수주상황'][0]
        self.assertEqual((n['rcpNo'], n['dcmNo'], n['dtd']), ('20260309001878', '11101680', 'dart4.xsd'))

    def test_read_report_through_viewer(self):
        main = (FX / 'mobis_main.html').read_bytes()
        body = (FX / 'mobis.html').read_bytes()
        nodes = {n['eleId']: n['text'] for n in K.viewer_nodes(main.decode('utf-8'))}

        def section(p):
            return body if nodes.get(p.get('eleId')) == '4. 매출 및 수주상황' else b'<html><body></body></html>'
        http = FakeHttp({'main.do': main, 'viewer.do': section})
        d = K.read_report(http, {'id': '20260309001878', 'code': '00164788'}, key='')
        self.assertEqual(d['name'], '현대모비스')
        self.assertEqual(d['code'], '00164788')
        self.assertAlmostEqual(by(d, 'customer')['기아']['share'], 0.358)
        self.assertEqual(d['url'], 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260309001878')

    def test_read_report_with_key(self):
        z = (FX / 'mobis_document.zip').read_bytes()
        http = FakeHttp({'document.xml': z})
        d = K.read_report(http, {'id': '20260309001878', 'code': '00164788', 'name': '현대모비스',
                                 'name_en': 'HYUNDAI MOBIS', 'fy': '2025-12-31'}, key='k')
        self.assertEqual(http.calls[0][1], {'crtfc_key': 'k', 'rcept_no': '20260309001878'})
        self.assertEqual(d['name_en'], 'HYUNDAI MOBIS')
        self.assertEqual(len(by(d, 'customer')), 2)
        self.assertEqual(d['concentration']['top1_purchases'], None)


if __name__ == '__main__':
    unittest.main()
