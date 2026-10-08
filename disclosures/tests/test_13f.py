import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
import unittest
from holdings13f.core import parse_filing, resolve, compare, aggregate, key
from holdings13f.build import filing_list


def fixture(filed='2026-08-14', amendment='', shares=10, value=100, cusip='123456789', put='', period='06-30-2026'):
    cover=f'''<edgarSubmission xmlns="urn:cover"><formData><coverPage><reportCalendarOrQuarter>{period}</reportCalendarOrQuarter><filingManager><name>Test Manager</name></filingManager><amendmentType>{amendment}</amendmentType></coverPage><summaryPage><tableEntryTotal>1</tableEntryTotal><tableValueTotal>{value}</tableValueTotal><isConfidentialOmitted>false</isConfidentialOmitted></summaryPage></formData></edgarSubmission>'''.encode()
    table=f'''<informationTable xmlns="urn:table"><infoTable><nameOfIssuer>Test Issuer</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>{cusip}</cusip><value>{value}</value><shrsOrPrnAmt><sshPrnamt>{shares}</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt><putCall>{put}</putCall></infoTable></informationTable>'''.encode()
    meta=dict(form='13F-HR/A' if amendment else '13F-HR',filed=filed,accession=filed+amendment,url='https://www.sec.gov/')
    return cover,table,meta


def filing(**kwargs):
    c,t,m=fixture(**kwargs)
    return parse_filing(c,[t],m)


class Tests(unittest.TestCase):
    def test_namespace_and_sec_date(self):
        f=filing()
        self.assertEqual(f['period'],'2026-06-30')
        self.assertEqual(f['rows'][0]['value_usd'],100)

    def test_legacy_thousands(self):
        self.assertEqual(filing(filed='2022-11-14')['rows'][0]['value_usd'],100000)

    def test_new_form_old_period(self):
        self.assertEqual(filing(period='12-31-2022')['unit_multiplier'],1)

    def test_summary_mismatch(self):
        c,t,m=fixture()
        with self.assertRaises(ValueError):
            parse_filing(c.replace(b'<tableEntryTotal>1',b'<tableEntryTotal>2'),[t],m)

    def test_total_mismatch(self):
        c,t,m=fixture()
        with self.assertRaises(ValueError):
            parse_filing(c.replace(b'<tableValueTotal>100',b'<tableValueTotal>10000'),[t],m)

    def test_restatement_replaces(self):
        a=filing();b=filing(filed='2026-08-15',amendment='RESTATEMENT',shares=20)
        self.assertEqual(resolve([a,b])[0]['positions'][0]['shares'],20)

    def test_new_holdings_append(self):
        a=filing();b=filing(filed='2026-08-15',amendment='NEW HOLDINGS',cusip='987654321')
        self.assertEqual(len(resolve([a,b])[0]['positions']),2)

    def test_append_same_security_aggregate(self):
        a=filing();b=filing(filed='2026-08-15',amendment='NEW HOLDINGS',shares=5)
        self.assertEqual(resolve([a,b])[0]['positions'][0]['shares'],15)

    def test_point_in_time(self):
        a=filing();b=filing(filed='2026-08-15',amendment='RESTATEMENT',shares=20)
        self.assertEqual(resolve([a,b],'2026-08-14')[0]['positions'][0]['shares'],10)

    def test_missing_original(self):
        a=resolve([filing(amendment='NEW HOLDINGS')])[0]
        self.assertFalse(a['complete'])
        self.assertEqual(compare(a,a),[])

    def test_option_separation(self):
        a=filing()['rows'];b=filing(put='PUT')['rows'];c=filing(put='CALL')['rows']
        self.assertEqual(len(aggregate(a+b+c)),3)

    def test_price_change_not_quantity_change(self):
        a=resolve([filing()])[0];b=resolve([filing(value=200)])[0]
        self.assertEqual(compare(a,b)[0]['status'],'UNCHANGED')
        self.assertEqual(compare(a,b)[0]['delta_value_usd'],100)

    def test_entry_exit(self):
        a=resolve([filing()])[0];b=resolve([filing(cusip='987654321')])[0]
        self.assertEqual({r['status'] for r in compare(a,b)},{'NEW','EXIT'})
        self.assertIsNone(next(r for r in compare(a,b) if r['status']=='NEW')['delta_pct'])

    def test_unknown_amendment(self):
        with self.assertRaises(ValueError):filing(amendment='OTHER')

    def test_duplicate_original_is_flagged(self):
        a=filing();b=filing(filed='2026-08-15')
        self.assertFalse(resolve([a,b])[0]['complete'])

    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError):filing(value='NaN')

    def test_submissions_archives_and_nt(self):
        class Fake:
            def json(self,url):
                if url.endswith('old.json'):
                    return {'form':['13F-HR'],'filingDate':['2024-02-14'],'accessionNumber':['old']}
                return {'name':'Test','filings':{'recent':{'form':['13F-NT','10-K'],'filingDate':['2026-08-14']*2,'accessionNumber':['notice','10k']},'files':[{'name':'old.json','filingTo':'2024-12-31'}]}}
        _,records=filing_list(Fake(),1,'2023-01-01')
        self.assertEqual([r['accession'] for r in records],['old','notice'])

if __name__=='__main__':unittest.main()
