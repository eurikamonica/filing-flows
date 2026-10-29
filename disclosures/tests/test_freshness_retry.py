import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import events8k, ownership, insiders, senate, collect
from core import read_json, write_json
from source_status import record
from retry_queue import RetryQueue
from persist_snapshot import merge_live
from test_market import FORM4


class FreshnessRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_status_failure_and_skip_do_not_advance_success(self):
        first = record(self.root, 'senate', {'status':'ok','updated_at':'2026-10-18T00:00:00Z'})
        failure = record(self.root, 'senate', {'status':'error','error':'HTTP 403'})
        skipped = record(self.root, 'senate', {'status':'ok','skipped':'searched recently','updated_at':'2026-10-25T00:00:00Z'})
        self.assertEqual(first['last_success'], failure['last_success'])
        self.assertEqual(skipped['status'], 'error')
        self.assertEqual(skipped['last_success'], first['last_success'])

    def test_live_merge_keeps_other_runs_newer_holdings(self):
        old={'last_attempt':'2026-10-18','managers':['old']}
        new={'last_attempt':'2026-10-25','managers':['new']}
        merged=merge_live({'modules':{'holdings':old,'congress':new}}, {'modules':{'holdings':new,'congress':old}})
        self.assertEqual(merged['modules'], {'holdings':new,'congress':new})

    def test_source_only_holdings_never_calls_price_or_market(self):
        cfg=self.root/'settings.json';write_json(cfg,{'holdings':{},'congress':{'quick_house_batch':0},'prices':{'enabled':True}})
        with patch.object(sys,'argv',['collect','--only','holdings','--defer-enrichment','--config',str(cfg),'--output',str(self.root),'--storage',str(self.root/'storage')]), patch.object(collect,'collect_holdings',return_value={'managers':[],'status':'ok'}), patch.object(collect,'apply_prices') as prices, patch.object(collect.market,'publish') as market:
            self.assertEqual(collect.main(),0)
            prices.assert_not_called();market.assert_not_called()
        self.assertEqual(read_json(self.root/'holdings-status.json',{})['status'],'ok')
        self.assertEqual(read_json(self.root/'live.json',{})['modules']['holdings']['status'],'ok')

    def test_senate_403_is_retained_and_cooled_down(self):
        client=Mock()
        with patch.object(senate,'open_session',side_effect=RuntimeError('HTTP 403')) as opening:
            a=senate.collect(client,self.root)
            b=senate.collect(client,self.root)
            self.assertEqual(opening.call_count,1)
        # eFD's access check turning the runner away is a blocked source (a warning, retried later), not a failed run
        self.assertEqual(a['status'],'blocked');self.assertEqual(b['skipped'],'access cooldown');self.assertEqual(b['status'],'blocked')
        self.assertTrue(b['next_retry_at'])
        self.assertFalse(collect._flag('senate',a)) ; self.assertFalse(collect._flag('senate',b))
        first=record(self.root,'senate',{'status':'error','error':'HTTP 403'})
        cooled=record(self.root,'senate',b)
        self.assertEqual(cooled['status'],'blocked')

    def test_senate_other_errors_still_fail(self):
        with patch.object(senate,'open_session',side_effect=RuntimeError('eFD home page without the agreement form')):
            a=senate.collect(Mock(),self.root)
        self.assertEqual(a['status'],'error');self.assertTrue(collect._flag('senate',a))

    def test_oversized_data_file_is_named_before_push(self):
        import os, persist_snapshot
        cwd=os.getcwd();os.chdir(self.root)
        try:
            Path('docs/data').mkdir(parents=True)
            with open('docs/data/live.json','wb') as f:f.truncate(persist_snapshot.GITHUB_FILE_LIMIT+1)
            with open('docs/data/live.js','wb') as f:f.truncate(persist_snapshot.WARN_BYTES+1)
            Path('docs/data/small.json').write_text('{}')
            errors,warnings=persist_snapshot.too_large(['disclosures/docs/data/live.json','disclosures/docs/data/live.js','disclosures/docs/data/small.json','disclosures/docs/data/gone.json'])
        finally:os.chdir(cwd)
        self.assertEqual(len(errors),1);self.assertIn('live.json',errors[0])
        self.assertEqual(len(warnings),1);self.assertIn('live.js',warnings[0])

    def test_form4_bytes_header_and_durable_retry(self):
        client=Mock();client.get.side_effect=RuntimeError('HTTP 403')
        with patch.object(insiders,'feed_entries',return_value=[('a','https://example/')]):
            first=insiders.collect(client,self.root,{'keep_days':1000})
        self.assertEqual(first['waiting'],1);self.assertEqual(first['status'],'partial')
        retry=RetryQueue(self.root/'cache/insiders');retry.rows['a']['next_retry_at']='2000-01-01';retry.save()
        client.get.side_effect=None;client.get.return_value=b'FILED AS OF DATE: 20261025\n<XML>'+FORM4+b'</XML>'
        with patch.object(insiders,'feed_entries',return_value=[]):
            second=insiders.collect(client,self.root,{'keep_days':1000})
        self.assertEqual(second['read'],1);self.assertEqual(second['waiting'],0)
        self.assertEqual(second['latest_filing_date'],'2026-10-25')

    def test_8k_failed_feed_item_survives_feed_rollover(self):
        client=Mock();client.get.side_effect=RuntimeError('HTTP 403')
        with patch.object(events8k,'feed_entries',return_value=[('a','https://example/')]):
            result=events8k.collect(client,self.root,{'index_days_per_run':0})
        self.assertEqual(result['waiting'],1)
        with patch.object(events8k,'feed_entries',return_value=[]):
            again=events8k.collect(client,self.root,{'index_days_per_run':0})
        self.assertEqual(again['waiting'],1);self.assertEqual(client.get.call_count,1)
        self.assertEqual(again['status'],'partial')

    def test_403_index_never_becomes_completed_day(self):
        for module,folder in [(events8k,'events8k'),(ownership,'ownership')]:
            client=Mock();client.get.side_effect=RuntimeError('HTTP 403')
            with patch.object(module,'feed_entries',return_value=[]):
                module.collect(client,self.root,{'index_days_per_run':1},today=dt.date(2026,10,25))
            state=read_json(self.root/'cache'/folder/'state.json',{})
            self.assertEqual(state['index_days'],[])
            self.assertTrue(read_json(self.root/'cache'/folder/'retry.json',{}))

    def test_ownership_feed_failures_preserved_and_retryable(self):
        client=Mock();client.get.side_effect=RuntimeError('network failure')
        with patch.object(ownership,'feed_entries',return_value=[('a','https://example/')]):
            result=ownership.collect(client,self.root,{'index_days_per_run':0,'batch':1})
        self.assertGreater(result['waiting'],0)
        self.assertEqual(result['status'],'partial')
        self.assertTrue(read_json(self.root/'cache/ownership/retry.json',{}))


class ConcurrentPublishRegression(unittest.TestCase):
    def test_real_git_push_keeps_newer_holdings_and_its_cache(self):
        import os
        import subprocess
        import persist_snapshot
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);remote=root/'remote.git';one=root/'one';two=root/'two'
            def g(cwd,*args):
                return subprocess.run(['git',*args],cwd=cwd,check=True,capture_output=True,text=True).stdout
            g(root,'init','--bare','--initial-branch=main',str(remote))
            g(root,'clone',str(remote),str(one))
            g(one,'config','user.name','Test');g(one,'config','user.email','test@example.org')
            folder=one/'disclosures/docs/data';folder.mkdir(parents=True)
            write_json(folder/'live.json',{'modules':{'holdings':{'last_attempt':'2026-10-18'}},'generated_at':'2026-10-18'})
            write_json(folder/'cache/holdings/1.json',{'value':'old'})
            g(one,'add','.');g(one,'commit','-m','base');g(one,'push','origin','main')
            g(root,'clone',str(remote),str(two))
            # Another collector commits fresh holdings while our price job still holds the old input.
            write_json(folder/'live.json',{'modules':{'holdings':{'last_attempt':'2026-10-25'}},'generated_at':'2026-10-25'})
            write_json(folder/'cache/holdings/1.json',{'value':'new'})
            g(one,'add','.');g(one,'commit','-m','fresh holdings');g(one,'push','origin','main')
            folder2=two/'disclosures/docs/data'
            write_json(folder2/'live.json',{'modules':{'holdings':{'last_attempt':'2026-10-18'},'prices':{'updated_at':'2026-10-25'}},'generated_at':'2026-10-25'})
            write_json(folder2/'cache/holdings/1.json',{'value':'old enriched'})
            before=Path.cwd()
            try:
                os.chdir(two/'disclosures');persist_snapshot.main()
            finally: os.chdir(before)
            live=json.loads(g(two,'show','HEAD:disclosures/docs/data/live.json'))
            cache=json.loads(g(two,'show','HEAD:disclosures/docs/data/cache/holdings/1.json'))
            self.assertEqual(live['modules']['holdings']['last_attempt'],'2026-10-25')
            self.assertIn('prices',live['modules'])
            self.assertEqual(cache['value'],'new')

if __name__=='__main__':unittest.main()
