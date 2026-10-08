import json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import officials, congress, prices

NY_INDEX = '''<html><body>
<a href="/financial-disclosure-statements-elected-officials?f%5B0%5D=filter_term%3A1851">Statewide Elected Officials (48)</a>
<a href="/financial-disclosure-statements-elected-officials?f%5B0%5D=filter_term%3A1856">Senate</a>
<a href="/financial-disclosure-statements-elected-officials?f%5B0%5D=filter_term%3A2786">2025 (210)</a>
<a href="/financial-disclosure-statements-elected-officials?f%5B0%5D=filter_term%3A2661">2024</a>
<ul><li><a href="/2025-governor-kathleen-hochul">Governor - Kathleen Hochul</a></li>
<li><a href="/addabbo-jr-joseph-p-fds-2025">Addabbo Jr., Joseph P.</a></li>
<li><a href="/2024-comptroller-thomas-p-dinapoli">Comptroller - Thomas P. DiNapoli</a></li></ul>
<a href="/financial-disclosure-statements-elected-officials?page=1">Next</a>
</body></html>'''

NY_PAGE = '<html><body><iframe src="https://public.ethics.ny.gov/FDS/Form/_ViewPrintable/880256/55292"></iframe></body></html>'
NY_STATEMENT = '''<html><body><h1>Financial Disclosure Statement</h1><table>
<tr><th>Security</th><th>Category</th></tr>
<tr><td>Widget Corp common stock</td><td>Category C</td></tr>
<tr><td>Bond fund</td><td>$5,000 - $20,000</td></tr></table></body></html>'''

CA_RESPONSE = json.dumps(json.dumps({'documents': [
    {'indexID': 'ABC-123', 'filer': {'firstName': 'Gavin', 'lastName': 'Newsom'}, 'filingDate': '2025-03-28T00:00:00',
     'filingPositions': [{'agency': 'Office of the Governor', 'position': 'Governor', 'filingType': 'Annual', 'filingYear': '2024'}]},
    {'indexID': 'DEF-456', 'filer': {'firstName': 'Pat', 'lastName': 'Lee'},
     'filingPositions': [{'agency': 'Superior Court', 'position': 'Judge', 'filingType': 'Assuming Office', 'filingYear': '2025'}]}],
    'total': 2}))

STOOQ = '''Date,Open,High,Low,Close,Volume
2026-03-30,100,101,99,100.0,1
2026-03-31,101,102,100,102.0,1
2026-04-01,103,104,102,104.0,1
2026-05-15,110,111,109,110.0,1
2026-06-30,120,121,119,120.0,1
'''


class FakeClient:
    def __init__(self, pages):
        self.pages = pages; self.options = {}; self.calls = []
    def get(self, url, **kw):
        self.calls.append(url)
        for key, body in self.pages.items():
            if key in url:
                return body.encode() if isinstance(body, str) else body
        raise RuntimeError('HTTP 404 from test ' + url)
    def request(self, url, **kw):
        return self.get(url), url, 'text/html'
    def json(self, url, **kw):
        return json.loads(self.get(url))
    def post_json(self, url, payload, headers=None):
        self.calls.append(('POST', url, payload))
        if 'SearchDocuments' in url:
            return json.loads(CA_RESPONSE)
        if 'GetRedactedFormPdf' in url:
            return {'PDFDownloadUrl': 'https://form700search.fppc.ca.gov/Download/abc.pdf'}
        if 'openfigi' in url:
            return [{'data': [{'ticker': 'AAPL', 'exchCode': 'US', 'name': 'APPLE INC', 'securityType': 'Common Stock'}]} for _ in payload]
        raise RuntimeError('unexpected POST')


class NewYorkTests(unittest.TestCase):
    def test_filters_and_listing(self):
        f = officials.ny_filters(NY_INDEX)
        self.assertEqual(f['Statewide Elected Officials'], '1851'); self.assertEqual(f['2025'], '2786')
        rows = officials.ny_listing(NY_INDEX)
        self.assertEqual(len(rows), 3)
        meta = officials.ny_meta(rows[0][0], rows[0][1], 'Statewide Elected Officials')
        self.assertEqual((meta['index_year'], meta['person'], meta['office']), (2025, 'Kathleen Hochul', 'Governor'))
        meta = officials.ny_meta(rows[1][0], rows[1][1], 'Senate')
        self.assertEqual((meta['index_year'], meta['office']), (2025, 'Senate'))

    def test_discovery_filters_by_year_and_office(self):
        c = FakeClient({'ethics.ny.gov/financial-disclosure': NY_INDEX})
        catalog, errors, coverage = officials.discover_ny(c, {'years': [2025], 'offices': ['Statewide Elected Officials', 'Senate']}, {})
        self.assertEqual(sorted(m['person'] for m in catalog.values()), ['Addabbo Jr., Joseph P.', 'Kathleen Hochul'])
        self.assertFalse(errors)
        self.assertTrue(all(cv['jurisdiction'] == 'ny' for cv in coverage))

    def test_html_statement_candidates_include_categories(self):
        pages = officials.html_to_pages(NY_STATEMENT.encode())
        self.assertEqual(pages[0]['method'], 'html')
        cands = congress.make_candidates(pages, 'ny-x', 'deadbeef', {'C': [20000, 60000]})
        texts = sorted(c['amount_text'] for c in cands)
        self.assertEqual(texts, ['$5,000 - $20,000', 'Category C'])
        cat = next(c for c in cands if c['amount_text'] == 'Category C')
        self.assertEqual((cat['amount_min'], cat['amount_max']), (20000, 60000))
        unconfigured = congress.make_candidates(pages, 'ny-x', 'deadbeef', None)
        self.assertTrue(any('not configured' in c['amount_text'] for c in unconfigured))

    def test_fetch_ny_document_follows_printable(self):
        c = FakeClient({'ethics.ny.gov/2025-governor': NY_PAGE, 'public.ethics.ny.gov/FDS': NY_STATEMENT})
        raw, extra = officials.fetch_ny_document(c, {'source_url': 'https://ethics.ny.gov/2025-governor-kathleen-hochul'})
        self.assertIn(b'Category C', raw); self.assertIn('_ViewPrintable', extra['document_url'])


class CaliforniaTests(unittest.TestCase):
    def test_double_encoded_response(self):
        metas, total = officials.ca_documents(json.loads(CA_RESPONSE))
        self.assertEqual(total, 2); self.assertEqual(metas[0]['person'], 'Gavin Newsom')
        self.assertEqual(metas[0]['filed_date'], '2025-03-28'); self.assertEqual(metas[1]['filed_date'], '')
        self.assertEqual(metas[1]['office'], 'Judge · Superior Court'); self.assertEqual(metas[0]['doc_kind'], 'ca-pdf')

    def test_discovery_and_download(self):
        c = FakeClient({'Download/abc.pdf': '%PDF-1.4 fake'})
        catalog, errors, coverage = officials.discover_ca(c, {'years': [2025], 'positions': ['Governor']}, {})
        self.assertEqual(len(catalog), 2); self.assertFalse(errors)
        meta = next(iter(catalog.values()))
        raw, extra = officials.fetch_ca_document(c, meta)
        self.assertTrue(raw.startswith(b'%PDF'))
        post = [x for x in c.calls if isinstance(x, tuple) and 'GetRedactedFormPdf' in x[1]][0]
        self.assertEqual(post[2]['indexID'], meta['ca']['indexID'])

    def test_search_payload_shape(self):
        p = officials.ca_search_payload(2025, position='Senator')
        self.assertEqual(p['searchFieldQueryInfos'][0], {'queryField': 'FilerPosition', 'filterValue': 'Senator'})
        self.assertEqual(p['searchFieldQueryInfos'][-1], {'queryField': 'FilingYear', 'filterValue': '2025'})


class CanadaTests(unittest.TestCase):
    def test_registry_listing_and_paging(self):
        body = '''<p>11097 Result(s) — page 2 of 370</p>
        <a href="/en/client?clientId=9384ECEA-ee00-f011-8193-001dd8b72449">Mark Carney</a> Prime Minister
        <a href="/en/client?clientId=9384ecea-ee00-f011-8193-001dd8b72449">Mark Carney</a>
        <a href="/en/public-registry/Details?declarationId=23a7babd-c591-f111-81ad-001dd8b72449">Gift</a>'''
        rows = officials.canada_listing(body, officials.CANADA + '/en/public-registry')
        self.assertEqual(rows, [(officials.CANADA + '/en/client?clientId=9384ecea-ee00-f011-8193-001dd8b72449', 'Mark Carney')])
        self.assertEqual(officials.canada_page_info(body), (11097, 2, 370))
        c = FakeClient({'ethicscanada.ca/en/public-registry': body})
        catalog, errors, coverage, state = officials.discover_canada(c, {'max_index_pages_per_run': 2}, {}, {'next_page': 369})
        self.assertEqual(len(catalog), 1); self.assertEqual(state['next_page'], 1); self.assertFalse(errors)

    def test_sedi_probe_reports_block(self):
        class Blocked(FakeClient):
            def request(self, url, **kw):
                raise RuntimeError('Redirected to a challenge/bot-protection page at validate.perfdrive.com')
        self.assertEqual(officials.probe_sedi(Blocked({}), {})['status'], 'blocked')


class PriceTests(unittest.TestCase):
    def test_quarter_average_and_close_on(self):
        rows = prices.parse_stooq(STOOQ, '2026-01-01')
        avg, close, days = prices.quarter_average(rows, '2026-06-30')
        self.assertAlmostEqual(avg, (104 + 110 + 120) / 3); self.assertEqual(close, 120.0); self.assertEqual(days, 3)
        self.assertEqual(prices.close_on(rows, '2026-05-17'), (110.0, '2026-05-15'))
        self.assertEqual(prices.close_on(rows, '2026-08-30'), (None, None))
        self.assertEqual(prices.stooq_symbol('BRK/B'), 'brk-b.us')
        with self.assertRaises(ValueError):
            prices.parse_stooq('<html><body>Exceeded the daily hits limit</body></html>', '2026-01-01')
        payload = {'chart': {'result': [{'timestamp': [1782777600, 1782864000], 'indicators': {'quote': [{'close': [100.5, None]}]}}]}}
        self.assertEqual(prices.parse_yahoo(payload, '2026-01-01'), [['2026-06-30', 100.5]])

    def test_apply_prices_annotates_positions_and_records(self):
        import tempfile
        c = FakeClient({'stooq.com': '<html>Exceeded the daily hits limit</html>', 'yahoo.com': json.dumps({'chart': {'result': [{'timestamp': [1774915200, 1775001600, 1775088000, 1778889600, 1782777600], 'indicators': {'quote': [{'close': [100.0, 102.0, 104.0, 110.0, 120.0]}]}}]}})})
        data = {'modules': {'holdings': {'managers': [{'cik': '1', 'snapshots': [{'period': '2026-06-30', 'positions': [
            {'cusip': '037833100', 'put_call': 'NONE', 'share_type': 'SH', 'shares': 10, 'value_usd': 1200},
            {'cusip': '037833100', 'put_call': 'CALL', 'share_type': 'SH', 'shares': 1, 'value_usd': 1}]}]}]},
            'congress': {'records': [{'ticker': 'AAPL', 'transaction_date': '2026-05-17', 'amount_min': 1001, 'amount_max': 15000}]}}}
        with tempfile.TemporaryDirectory() as tmp:
            status = prices.apply_prices(data, c, {'ticker_batch': 5, 'cusip_batch': 10}, tmp)
        pos = data['modules']['holdings']['managers'][0]['snapshots'][0]['positions']
        self.assertEqual(pos[0]['ticker'], 'AAPL'); self.assertAlmostEqual(pos[0]['price_avg_q'], 109.0)
        self.assertNotIn('ticker', pos[1])
        rec = data['modules']['congress']['records'][0]
        self.assertEqual(rec['price_on_date'], 110.0); self.assertAlmostEqual(rec['est_shares_min'], 9.1); self.assertAlmostEqual(rec['est_shares_max'], 136.36)
        self.assertEqual(status['counts']['positions_priced'], 1); self.assertEqual(status['status'], 'ok')


if __name__ == '__main__':
    unittest.main()
