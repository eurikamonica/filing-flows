import unittest,sys,tempfile,datetime as dt
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from discovery import parse_master,select_batch,discover_sec
from shards import publish_shards,hydrate,safe_path
from core import read_json
HEADER=b'CIK|Company Name|Form Type|Date Filed|Filename\n'
class DiscoveryTests(unittest.TestCase):
 def test_master_names_forms_and_window(self):
  raw=HEADER+b'123|TEST & CO|13F-HR|2025-03-01|edgar/data/123/0000000123-25-000001.txt\n123|TEST & CO|13F-HR/A|2025-04-01|edgar/data/123/0000000123-25-000002.txt\n456|FUND|N-PX|2025-08-01|edgar/data/456/0000000456-25-000001.txt\n123|TEST|10-K|2025-04-01|edgar/data/123/0000000123-25-000003.txt\n123|TEST|13F-HR|2024-03-01|edgar/data/123/0000000123-24-000003.txt'
  rows=parse_master(raw,'2025-01-01');self.assertEqual(len(rows),2);self.assertEqual(rows[0]['filing_count'],2);self.assertEqual(rows[0]['latest_filing'],'2025-04-01');self.assertEqual(rows[1]['kind'],'npx')
 def test_block_page_cannot_replace_index(self):
  with self.assertRaises(ValueError):parse_master(b'<html>Access denied</html>','2025-01-01')
 def test_invalid_path(self):
  self.assertEqual(parse_master(HEADER+b'123|BAD|13F-HR|2025-01-01|../../evil.txt','2025-01-01'),[])
 def test_active_index_refresh_budget(self):
  from unittest.mock import Mock
  today=dt.datetime.now(dt.timezone.utc)
  q=(today.month-1)//3+1
  start=f'{today.year}-{(q-1)*3+1:02d}-01'
  key=f'{today.year}/QTR{q}'
  cfg={'since':start,'active_index_refresh_minutes':20}
  old={'indices':{key:{'rows':[], 'checked_at':(today-dt.timedelta(minutes=22)).isoformat(),'since':start}}}
  client=Mock()
  client.get.return_value=HEADER+b'123|TEST|13F-HR|2026-10-01|edgar/data/123/0000000123-26-000001.txt\n'
  result=discover_sec(client,cfg,old)
  self.assertTrue(client.get.called,'Active index older than 20 minutes should be refreshed')
  self.assertEqual(result['since'],start)
  client.reset_mock()
  recent={'indices':{key:{'rows':[],'checked_at':today.isoformat(),'since':start}}}
  discover_sec(client,cfg,recent)
  client.get.assert_not_called()

 def test_batch_fairness_and_cap(self):
  old=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=5)).isoformat()
  items=[{'cik':str(i)} for i in range(10)]
  selected=select_batch(items,{'0':{'last_success':old}},4,'cik')
  self.assertEqual(len(selected),4);self.assertIn('0',[r['cik'] for r in selected]);self.assertEqual(len({r['cik'] for r in selected}),4)
 def test_success_resumes_next_batch(self):
  current=dt.datetime.now(dt.timezone.utc).isoformat()
  self.assertEqual(select_batch([{'cik':'1'},{'cik':'2'}],{'1':{'last_success':current}},1,'cik'),[{'cik':'2'}])
 def test_error_backoff(self):
  current=dt.datetime.now(dt.timezone.utc).isoformat()
  self.assertEqual(select_batch([{'cik':'1'}],{'1':{'last_attempt':current,'error':'403'}},2,'cik'),[])
 def test_invalid_budget(self):
  with self.assertRaises(ValueError):select_batch([],{},0,'cik')
 def test_shard_roundtrip_and_main_small(self):
  payload={'modules':{'holdings':{'managers':[{'cik':'123','name':'TEST','snapshots':[{'period':'2025-12-31','total_usd':2,'positions':[{'cusip':'A','value_usd':2}]}],'filings':[{'accession':'abc'}]}]},'congress':{'reports':[{'report_id':'house-1','candidates':[{'id':'abc'}]}]}}}
  with tempfile.TemporaryDirectory()as d:
   publish_shards(d,payload);small=read_json(Path(d)/'live.json',{})
   self.assertNotIn('snapshots',small['modules']['holdings']['managers'][0]);self.assertEqual(small['modules']['congress']['reports'][0]['candidate_count'],1)
   self.assertEqual(hydrate(d,small),payload)
 def test_missing_shard_is_not_empty_portfolio(self):
  with tempfile.TemporaryDirectory()as d:
   with self.assertRaises(ValueError):hydrate(d,{'modules':{'holdings':{'managers':[{'shard':'shards/holdings/1.json'}]}}})
 def test_shard_traversal_rejected(self):
  with self.assertRaises(ValueError):safe_path('/tmp','shards/holdings/../../private.json')
 def test_lazy_republish_preserves_payload(self):
  payload={'modules':{'holdings':{'managers':[{'cik':'123','snapshots':[],'filings':[]}]},'congress':{'reports':[{'report_id':'house-1','candidates':[{'id':'kept'}]}]}}}
  with tempfile.TemporaryDirectory()as d:
   publish_shards(d,payload)
   before=(Path(d)/'shards/congress/house-1.json').read_bytes()
   compact=read_json(Path(d)/'live.json',{});publish_shards(d,compact)
   self.assertEqual(before,(Path(d)/'shards/congress/house-1.json').read_bytes())
   self.assertEqual(hydrate(d,read_json(Path(d)/'live.json',{})),payload)
 def test_page_text_stays_in_the_shard(self):
  # every statement's page text lives in its shard only: in live.json it pushed the file past GitHub's 100 MiB limit
  row={'report_id':'house-2','person':'A','text_preview':'— Page 1 —\nlong text','page_methods':[{'page':1,'method':'ocr'}],'candidates':[{'id':'c'}]}
  with tempfile.TemporaryDirectory()as d:
   publish_shards(d,{'modules':{'congress':{'reports':[row]}}})
   small=read_json(Path(d)/'live.json',{});summary=small['modules']['congress']['reports'][0]
   self.assertNotIn('text_preview',summary);self.assertNotIn('page_methods',summary);self.assertEqual(summary['person'],'A')
   self.assertEqual(read_json(Path(d)/'shards/congress/house-2.json',{})['text_preview'],row['text_preview'])
   self.assertEqual(hydrate(d,small)['modules']['congress']['reports'][0],row)
   # rows already published before the change (lazy, with the text) lose it on the next publish; the shard keeps it
   lazy={**{k:v for k,v in row.items() if k!='candidates'},'shard':'shards/congress/house-2.json','candidate_count':1}
   publish_shards(d,{'modules':{'congress':{'reports':[lazy]}}})
   again=read_json(Path(d)/'live.json',{})['modules']['congress']['reports'][0]
   self.assertNotIn('text_preview',again);self.assertEqual(read_json(Path(d)/'shards/congress/house-2.json',{})['text_preview'],row['text_preview'])
 def test_blank_house_filing_date_preserved(self):
  from congress import house_meta
  row={'DocID':'10001','Year':'2025','First':'Test','Last':'Filer','FilingType':'O','FilingDate':''}
  self.assertEqual(house_meta(row)['filed_date'],'')
if __name__=='__main__':unittest.main()
