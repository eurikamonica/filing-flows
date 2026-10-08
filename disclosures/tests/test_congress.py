import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from congress import parse_amount,read_house_index,house_meta,positioned_ranges,make_candidates,load_reviewed,REVIEW_FIELDS,public_excerpt

class CongressTests(unittest.TestCase):
    def test_interval_and_open_end(self):
        self.assertEqual(parse_amount('$1,001 - $15,000'),(1001,15000))
        self.assertEqual(parse_amount('Over $50,000,000'),(50000001,None))
        with self.assertRaises(ValueError):parse_amount('$15,000 - $1,001')

    def test_index_year_distinct_from_filing_year(self):
        row={'DocID':'10075701','Year':'2025','FilingType':'O','FilingDate':'5/15/2026','First':'Nancy','Last':'Pelosi','StateDst':'CA11'}
        m=house_meta(row)
        self.assertEqual(m['index_year'],2025);self.assertEqual(m['filed_date'],'2026-05-15')
        self.assertIn('/2025/',m['source_url'])

    def test_unsupported_filing_code_not_guessed(self):
        with self.assertRaises(ValueError):house_meta({'DocID':'123','Year':'2026','FilingType':'UNKNOWN'})

    def test_index_archive_reads_only_expected_member(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:
            z.writestr('2026FD.txt','First\tLast\tDocID\tYear\tFilingType\tFilingDate\nA\tB\t12\t2026\tP\t1/1/2026\n')
            z.writestr('../escape.txt','ignored')
        rows=read_house_index(stream.getvalue(),2026);self.assertEqual(rows[0]['DocID'],'12')

    def test_visual_columns_prevent_asset_income_mix(self):
        def w(text,x,y,width=35):return {'text':text,'x0':x,'x1':x+width,'top':y,'bottom':y+10}
        words=[w('$5,000,001',280,400,50),w('-',335,400,5),w('$100,001',445,400,45),w('-',495,400,5),w('$25,000,000',280,411,55),w('$1,000,000',445,411,55)]
        ranges=positioned_ranges(words)
        self.assertEqual([(r['amount_min'],r['amount_max'])for r in ranges],[(5000001,25000000),(100001,1000000)])

    def test_candidates_never_auto_approved(self):
        c=make_candidates([{'page':1,'method':'ocr','mean_word_confidence':99,'text':'Something $1,001 - $15,000'}],'house-1','hash')[0]
        self.assertEqual(c['kind'],'unclassified');self.assertEqual(c['review_status'],'needs_review');self.assertEqual(c['asset'],'')

    def test_review_hash_mismatch_rejected(self):
        r={'id':'a','report_id':'r','source_sha256':'wrong','page':'1','kind':'asset','asset':'Example','amount_min':'1001','amount_max':'15000','reviewer':'Test','reviewed_at':'2026-10-06','valuation_basis':'Reported value'}
        with tempfile.TemporaryDirectory()as tmp:
            p=Path(tmp)/'review.csv'
            with p.open('w',newline='')as f:w=csv.DictWriter(f,fieldnames=REVIEW_FIELDS);w.writeheader();w.writerow(r)
            records,errors=load_reviewed(p,[{'report_id':'r','source_sha256':'actual','page_count':1}])
            self.assertEqual(records,[]);self.assertTrue(any('hash mismatch'in e for e in errors))

    def test_missing_transaction_date_rejected(self):
        r={'id':'a','report_id':'r','source_sha256':'same','page':'1','kind':'transaction','asset':'Example','amount_min':'1001','amount_max':'15000','reviewer':'Test','reviewed_at':'2026-10-06','transaction_type':'purchase','transaction_date':''}
        with tempfile.TemporaryDirectory()as tmp:
            p=Path(tmp)/'review.csv'
            with p.open('w',newline='')as f:w=csv.DictWriter(f,fieldnames=REVIEW_FIELDS);w.writeheader();w.writerow(r)
            records,errors=load_reviewed(p,[{'report_id':'r','source_sha256':'same','page_count':1}])
            self.assertEqual(records,[]);self.assertTrue(errors)

    def test_preview_residential_address_minimized(self):
        self.assertEqual(public_excerpt('123 Example Lane - Home & Vineyard'),'[Residential address omitted] - Home & Vineyard')

if __name__=='__main__':unittest.main()
