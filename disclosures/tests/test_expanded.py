import unittest,sys,tempfile,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import expanded
from core import now,read_json
from shards import publish_shards,safe_path

class ExpandedTests(unittest.TestCase):
 def test_cot_plus_code_and_rename(self):
  class Client:
   def json(self,url):return [{'cftc_contract_market_code':'13874+','market_and_exchange_names':'OLD','latest_report':'2025-01-01T00:00:00'},{'cftc_contract_market_code':'13874+','market_and_exchange_names':'NEW','latest_report':'2026-01-01T00:00:00'}]
  result=expanded.discover_cot(Client(),{'since':'2023-01-01','datasets':[{'id':'gpe5-46if','family':'tff'}]})
  self.assertEqual(len(result),1);self.assertEqual(result[0]['name'],'NEW');safe_path('/tmp','shards/cot/gpe5-46if-13874+.json')
 def test_bank_incomplete_directory_rejected(self):
  class Client:
   def json(self,url):return {'meta':{'total':3},'data':[{'data':{'CERT':14,'NAME':'TEST'}}]}
  with self.assertRaisesRegex(ValueError,'Incomplete'):expanded.discover_banks(Client(),{})
 def test_bank_duplicate_rejected(self):
  class Client:
   def json(self,url):return {'meta':{'total':2},'data':[{'data':{'CERT':14,'NAME':'TEST'}}]*2}
  with self.assertRaisesRegex(ValueError,'duplicate'):expanded.discover_banks(Client(),{})
 def test_bank_queue_resume_and_series_retention(self):
  cfg={'since':'20200101','active_only':True,'discover_all':True,'batch_size':1,'refresh_hours':168}
  catalog=[{'id':'1','cert':1,'name':'A'},{'id':'2','cert':2,'name':'B'}]
  with patch.object(expanded,'discover_banks',return_value=catalog),patch.object(expanded,'collect_banks',return_value={'rows':[{'date':'2026-06-30'}]}):
   first=expanded.collect_banks_expanded(None,cfg,{})
   second=expanded.collect_banks_expanded(None,cfg,first)
  self.assertEqual(first['counts']['processed'],1);self.assertEqual(second['counts']['processed'],2);self.assertEqual(second['counts']['pending'],0)
 def test_discovery_error_retains_catalog_and_data(self):
  cfg={'since':'20200101','batch_size':1}
  old={'directory':[{'id':'1','cert':1,'name':'A'}],'series':[{'id':'1','cert':1,'name':'A','rows':[{'date':'2026-06-30'}],'last_success':now()}]}
  with patch.object(expanded,'discover_banks',side_effect=ValueError('blocked')):out=expanded.collect_banks_expanded(None,cfg,old)
  self.assertEqual(out['status'],'partial');self.assertEqual(out['series'][0]['rows'],old['series'][0]['rows'])
 def test_refresh_error_retains_prior_series(self):
  cfg={'since':'20200101','discover_all':False,'certs':[1],'batch_size':1}
  old={'series':[{'id':'1','cert':1,'name':'A','rows':[{'date':'2026-06-30'}],'last_success':now()}]}
  with patch.object(expanded,'collect_banks',side_effect=ValueError('403')):out=expanded.collect_banks_expanded(None,cfg,old,True)
  self.assertTrue(out['series'][0]['stale']);self.assertEqual(len(out['series'][0]['rows']),1)
 def test_legacy_rows_migrate_by_entity(self):
  rows=[{'cert':1,'name':'A','date':'2025-03-31'},{'cert':2,'name':'B','date':'2025-03-31'},{'cert':1,'name':'A','date':'2025-06-30'}]
  result=expanded.migrate_series({'rows':rows},'banks');self.assertEqual(len(result),2);self.assertEqual(len(result['1']['rows']),2)
 def test_npx_document_queue_resumes_independent_of_filer_scan(self):
  found=[{'accessionNumber':f'0000000001-26-{i:06d}','filingDate':'2026-08-01','form':'N-PX'}for i in range(1,4)]
  def download(client,cik,name,f):return {'accession':f['accessionNumber'],'cik':cik,'filer':name,'form':'N-PX','filing_date':f['filingDate'],'fetched_at':now(),'parse_status':'parsed','votes':[]}
  with tempfile.TemporaryDirectory()as d:
   cfg={'_data_root':d,'since':'2024-01-01','discover_all':False,'ciks':['1'],'batch_size':1,'document_batch_size':1}
   with patch.object(expanded,'discover_npx',return_value=('TEST',found))as scanner,patch.object(expanded,'download_npx',side_effect=download):
    first=expanded.collect_npx_expanded(None,cfg,{})
    second=expanded.collect_npx_expanded(None,cfg,first)
    self.assertEqual(scanner.call_count,1)
   self.assertEqual(first['counts']['pending_filings'],2);self.assertEqual(second['counts']['downloaded_filings'],2);self.assertEqual(second['counts']['pending_filings'],1)
 def test_npx_error_keeps_original_document(self):
  old={'filings':[{'accession':'0000000001-26-000001','cik':'0000000001','filer':'TEST','form':'N-PX','filing_date':'2026-08-01','fetched_at':now(),'parse_status':'parsed','votes':[{'issuer':'KEEP'}]}]}
  meta={'accessionNumber':'0000000001-26-000001','filingDate':'2026-08-01','form':'N-PX'}
  with tempfile.TemporaryDirectory()as d:
   cfg={'_data_root':d,'since':'2024-01-01','discover_all':False,'ciks':['1'],'batch_size':1,'document_batch_size':1}
   with patch.object(expanded,'discover_npx',return_value=('TEST',[meta])),patch.object(expanded,'download_npx',side_effect=ValueError('failed')):out=expanded.collect_npx_expanded(None,cfg,old,True)
  self.assertEqual(out['filings'][0]['votes'][0]['issuer'],'KEEP');self.assertEqual(out['status'],'partial')
 def test_vote_chunks_and_lazy_republish(self):
  filing={'accession':'0000000001-26-000001','cik':'1','votes':[{'id':i}for i in range(2100)]}
  with tempfile.TemporaryDirectory()as d:
   publish_shards(d,{'modules':{'npx':{'filings':[filing]}}})
   data=read_json(Path(d)/'live.json',{});summary=data['modules']['npx']['filings'][0]
   self.assertEqual(summary['vote_count'],2100);self.assertNotIn('votes',summary)
   header=read_json(Path(d)/summary['shard'],{});self.assertEqual(len(header['vote_chunks']),3)
   self.assertEqual(len(read_json(Path(d)/header['vote_chunks'][-1],[])),100)
   publish_shards(d,data);self.assertEqual(read_json(Path(d)/summary['shard'],{}),header)
 def test_catalog_shard_roundtrip_and_missing_error(self):
  from shards import hydrate_catalogs
  with tempfile.TemporaryDirectory()as d:
   original={'modules':{'banks':{'directory':[{'id':'14','name':'TEST'}],'series':[]}}}
   publish_shards(d,original)
   compact=read_json(Path(d)/'live.json',{})
   self.assertNotIn('directory',compact['modules']['banks'])
   self.assertEqual(hydrate_catalogs(d,compact)['modules']['banks']['directory'],original['modules']['banks']['directory'])
   (Path(d)/'catalogs/banks.json').unlink()
   with self.assertRaisesRegex(ValueError,'Missing'):hydrate_catalogs(d,read_json(Path(d)/'live.json',{}))
 def test_npx_queue_state_survives_publication(self):
  payload={'modules':{'npx':{'filings':[],'filing_directory':{'acc':{'cik':'1'}},'filer_attempts':{'1':{'last_success':now()}},'document_attempts':{}}}}
  with tempfile.TemporaryDirectory()as d:
   publish_shards(d,payload)
   public=read_json(Path(d)/'live.json',{})['modules']['npx'];private=read_json(Path(d)/'npx-queue-state.json',{})
   self.assertNotIn('filing_directory',public);self.assertEqual(private['filing_directory'],payload['modules']['npx']['filing_directory'])
if __name__=='__main__':unittest.main()
