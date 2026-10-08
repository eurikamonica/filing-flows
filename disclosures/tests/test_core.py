import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from core import *
FIX=Path(__file__).parent/'fixtures'

class DataTests(unittest.TestCase):
    def test_numbers_missing_and_commas(self):
        self.assertIsNone(number(''))
        self.assertIsNone(number(None))
        self.assertIsNone(number('nan'))
        self.assertEqual(number('1,234.5'),1234.5)

    def test_zero_denominator(self):
        self.assertIsNone(ratio(5,0))
        self.assertIsNone(ratio(None,2))
        self.assertEqual(ratio(0,2),0)

    def test_real_cot_mapping(self):
        r=json.loads((FIX/'cot-sample.json').read_text())
        out=normalize_cot(r,'72hh-3qpy','disaggregated')
        self.assertEqual(len(out),5)
        mm=next(x for x in out if x['group']=='Managed money')
        self.assertEqual(mm['net'],65114-84004)
        self.assertEqual(mm['code'],'001602')

    def test_cot_missing_schema_is_not_zero(self):
        r=json.loads((FIX/'cot-sample.json').read_text())
        del r[0]['m_money_positions_long_all']
        with self.assertRaises(ValueError):normalize_cot(r,'72hh-3qpy','disaggregated')

    def test_cot_week_change_gaps_and_index(self):
        template=json.loads((FIX/'cot-sample.json').read_text())[0]
        records=[]
        for i in range(53):
            r=copy.deepcopy(template)
            r['report_date_as_yyyy_mm_dd']=(dt.date(2024,1,2)+dt.timedelta(weeks=i)).isoformat()
            r['m_money_positions_long_all']=str(100000+i*100)
            records.append(r)
        mm=[r for r in normalize_cot(records,'72hh-3qpy','disaggregated')if r['group']=='Managed money']
        self.assertIsNone(mm[50]['index_52_observations'])
        self.assertEqual(mm[51]['index_52_observations'],100)
        self.assertEqual(mm[-1]['weekly_change'],100)
        gapped=[r for r in normalize_cot([records[0],records[2]],'72hh-3qpy','disaggregated')if r['group']=='Managed money']
        self.assertIsNone(gapped[-1]['weekly_change'])

    def test_cot_flat_index_undefined(self):
        template=json.loads((FIX/'cot-sample.json').read_text())[0]
        rows=[]
        for i in range(52):
            r=copy.deepcopy(template);r['report_date_as_yyyy_mm_dd']=(dt.date(2024,1,2)+dt.timedelta(weeks=i)).isoformat();rows.append(r)
        self.assertTrue(all(x['index_52_observations'] is None for x in normalize_cot(rows,'x','disaggregated')))

    def test_bank_real_ytd_to_quarter(self):
        rows=normalize_banks([r['data']for r in json.loads((FIX/'fdic-sample.json').read_text())['data']])
        lookup={r['date']:r for r in rows}
        self.assertEqual(lookup['2026-06-30']['net_income_quarter'],31335000-13974000)
        self.assertEqual(lookup['2026-03-31']['net_income_quarter'],13974000)
        self.assertEqual(lookup['2025-12-31']['net_income_quarter'],49644000-38227000)
        self.assertIsNone(lookup['2025-09-30']['net_income_quarter'])
        self.assertIsNotNone(lookup['2026-03-31']['assets_qoq'])
        self.assertEqual(lookup['2026-06-30']['assets'],4091315000) # thousands, no accidental x1000

    def test_bank_null_not_zero(self):
        r={'CERT':1,'NAME':'Test','REPDTE':'20240630','ASSET':None,'NETINC':None,'DEP':0}
        row=normalize_banks([r])[0]
        self.assertIsNone(row['net_income_quarter'])
        self.assertIsNone(row['loan_deposit_ratio'])

    def test_bank_dedup_correction(self):
        a={'CERT':1,'NAME':'Test','REPDTE':'20240331','ASSET':100,'NETINC':2}
        b={**a,'ASSET':120}
        rows=normalize_banks([a,b]);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['assets'],120)

    def test_npx_real_xml(self):
        rows=parse_npx((FIX/'npx-votes.xml').read_bytes(),'https://www.sec.gov/test.xml')
        self.assertEqual(len(rows),31)
        self.assertEqual(rows[0]['issuer'],'BOYD GAMING CORPORATION')
        self.assertEqual(rows[0]['shares_voted'],408310)
        self.assertEqual(rows[0]['votes'][0]['management_alignment'],'FOR')
        self.assertTrue(any(v['how']=='1 YEAR'for r in rows for v in r['votes']))

    def test_npx_cover_is_not_vote_table(self):
        self.assertIsNone(parse_npx((FIX/'npx-cover.xml').read_bytes(),'url'))

    def test_npx_split_vote_totals(self):
        data=b'''<proxyVoteTable xmlns="urn:test"><proxyTable><issuerName>Example</issuerName><sharesVoted>100</sharesVoted><sharesOnLoan>20</sharesOnLoan><vote><voteRecord><howVoted>FOR</howVoted><sharesVoted>40</sharesVoted><managementRecommendation>AGAINST</managementRecommendation></voteRecord><voteRecord><howVoted>AGAINST</howVoted><sharesVoted>60</sharesVoted><managementRecommendation>FOR</managementRecommendation></voteRecord></vote></proxyTable></proxyVoteTable>'''
        row=parse_npx(data,'url')[0]
        self.assertEqual(row['shares_voted'],100)
        self.assertEqual(sum(v['shares']for v in row['votes']),100)
        self.assertEqual(row['votes'][0]['management_alignment'],'AGAINST')

    def test_npx_zero_and_missing_votes(self):
        row=parse_npx(b'<proxyVoteTable><proxyTable><sharesVoted>0</sharesVoted></proxyTable></proxyVoteTable>','url')[0]
        self.assertEqual(row['shares_voted'],0)
        self.assertEqual(row['votes'],[])
        self.assertIsNone(row['shares_on_loan'])

    def test_xml_rejects_entities(self):
        with self.assertRaises(ValueError):parse_xml(b'<!DOCTYPE x [<!ENTITY e "evil">]><x>&e;</x>')

    def test_discovery_history_and_dedup(self):
        recent={'form':['N-PX','13F-HR'],'accessionNumber':['a','b'],'filingDate':['2025-08-01','2025-08-01']}
        class Stub:
            def json(self,url,sec=False):
                if url.endswith('CIK0000000001.json'):
                    return {'name':'Test','filings':{'recent':recent,'files':[{'name':'CIK0000000001-submissions-001.json','filingTo':'2025-01-01'}]}}
                return {'form':['N-PX','N-PX/A','N-PX'],'accessionNumber':['a','c','d'],'filingDate':['2025-08-01','2024-08-21','2020-01-01']}
        name,rows=discover_npx(Stub(),'0000000001','2024-01-01')
        self.assertEqual([r['accessionNumber']for r in rows],['a','c'])

    def test_discovery_official_fixture(self):
        class Stub:
            def json(self,url,sec=False):return json.loads((FIX/'npx-submissions.json').read_text())
        name,rows=discover_npx(Stub(),'0001630243','2024-01-01')
        self.assertTrue(any(r['accessionNumber']=='0001630243-25-000012'for r in rows))
        self.assertTrue(all(r['form'].startswith('N-PX')for r in rows))

    def test_failed_refresh_preserves_previous_rows(self):
        old={'rows':[{'x':1}], 'updated_at':'yesterday'}
        def failed(*a):raise RuntimeError('offline')
        value=refresh_module(old,failed,None,{})
        self.assertEqual(value['status'],'error')
        self.assertEqual(value['rows'],[{'x':1}])
        self.assertEqual(value['updated_at'],'yesterday')
        self.assertEqual(old,{'rows':[{'x':1}], 'updated_at':'yesterday'})

    def test_npx_amendments_remain_separate(self):
        files=[{'accessionNumber':'0000000001-25-000002','form':'N-PX/A','filingDate':'2025-09-01'},
               {'accessionNumber':'0000000001-25-000001','form':'N-PX','filingDate':'2025-08-01'}]
        def download(client,cik,name,f):return {'accession':f['accessionNumber'],'votes':[{'test':1}], 'parse_status':'parsed'}
        with patch('core.discover_npx',return_value=('Test',files)),patch('core.download_npx',side_effect=download):
            result=collect_npx(None,{'ciks':['1'],'since':'2024-01-01'},{})
        self.assertEqual(len(result['filings']),2)
        self.assertEqual(result['status'],'ok')

    def test_npx_failure_retried_not_completed(self):
        files=[{'accessionNumber':'0000000001-25-000001','form':'N-PX','filingDate':'2025-08-01'}]
        with patch('core.discover_npx',return_value=('Test',files)),patch('core.download_npx',side_effect=RuntimeError('offline')):
            r=collect_npx(None,{'ciks':['1'],'since':'2024-01-01'},{})
        self.assertEqual(r['status'],'partial');self.assertEqual(r['filings'][0]['parse_status'],'failed')
        with patch('core.discover_npx',return_value=('Test',files)),patch('core.download_npx',return_value={'accession':files[0]['accessionNumber'],'parse_status':'parsed','first_seen_at':'today'}) as download:
            r=collect_npx(None,{'ciks':['1'],'since':'2024-01-01'},r)
        self.assertTrue(download.called)
        self.assertEqual(r['filings'][0]['parse_status'],'parsed')

    def test_npx_cap_disclosed(self):
        files=[{'accessionNumber':'a'},{'accessionNumber':'b'}]
        with patch('core.discover_npx',return_value=('Test',files)),patch('core.download_npx',return_value={'accession':'a','parse_status':'parsed'}):
            r=collect_npx(None,{'ciks':['1'],'since':'2024-01-01','max_filings_per_cik':1},{})
        self.assertTrue(r['coverage'][0]['truncated']);self.assertEqual(r['status'],'partial')

    def test_publish_official_separate_from_demo(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'demo.js').write_text('DEMO')
            publish(p,{'modules':{},'mode':'official'})
            self.assertEqual((p/'demo.js').read_text(),'DEMO')
            self.assertTrue((p/'live.js').read_text().startswith('window.DISCLOSURE_LIVE'))
            self.assertEqual(read_json(p/'live.json',{})['mode'],'official')

    def test_missing_contact_stops_sec_request(self):
        with tempfile.TemporaryDirectory()as tmp,patch.dict(os.environ,{'SEC_USER_AGENT':''}):
            with self.assertRaises(ValueError):Client(tmp,{}).get('https://data.sec.gov/test',sec=True)

    def test_configured_sec_identity_used_when_environment_empty(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'SEC_USER_AGENT': ''}), patch('core.urlopen') as opener:
            response = MagicMock()
            response.url = 'https://data.sec.gov/test'
            response.read.return_value = b'{}'
            opener.return_value.__enter__.return_value = response
            Client(tmp, {'sec_user_agent': 'Eurika eurikamonica@gmail.com'}).get(response.url, sec=True)
            self.assertEqual(opener.call_args.args[0].get_header('User-agent'), 'Eurika eurikamonica@gmail.com')

    def test_sec_environment_overrides_configured_identity(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'SEC_USER_AGENT': 'Override contact@sample.org'}), patch('core.urlopen') as opener:
            response = MagicMock()
            response.url = 'https://data.sec.gov/test'
            response.read.return_value = b'{}'
            opener.return_value.__enter__.return_value = response
            Client(tmp, {'sec_user_agent': 'Eurika eurikamonica@gmail.com'}).get(response.url, sec=True)
            self.assertEqual(opener.call_args.args[0].get_header('User-agent'), 'Override contact@sample.org')

if __name__=='__main__':unittest.main()
