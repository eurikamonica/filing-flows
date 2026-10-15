"""Offline acceptance tests. Created by ChatGPT (OpenAI)."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from engine import analyze
from gemini import explain
from adapter import convert
from training import generate, read_dataset
from student import train,predict

class AccountingTests(unittest.TestCase):
    def setUp(self):self.data=json.loads((ROOT/'examples/demo.json').read_text())
    def test_known_financials(self):
        p=analyze(self.data)['periods'][1];m=p['metrics']
        self.assertEqual(m['accruals']['value'],35);self.assertEqual(m['fcf']['value'],25)
        self.assertAlmostEqual(m['accrual_ratio']['value'],35/850)
        self.assertEqual(m['noa']['value'],500);self.assertEqual(m['nfo']['value'],140)
        self.assertEqual(m['balance_residual']['value'],0)
        self.assertAlmostEqual(m['rnoa']['value'],105/465)
        self.assertEqual(p['reserves'][0]['pretax_release_benefit'],20)
    def test_missing_is_not_zero(self):
        del self.data['periods'][1]['values']['ocf']
        m=analyze(self.data)['periods'][1]['metrics']
        self.assertIsNone(m['accruals']['value']);self.assertIsNone(m['fcf']['value'])
    def test_missing_reserve_movement(self):
        del self.data['periods'][1]['reserves'][0]['other']
        r=analyze(self.data)['periods'][1]['reserves'][0]
        self.assertIsNone(r['residual']);self.assertIsNone(r['pretax_release_benefit'])
    def test_utilization_is_not_release(self):
        r=self.data['periods'][1]['reserves'][0];r['releases']['value']=0;r['utilization']['value']=30
        p=analyze(self.data)['periods'][1]
        self.assertNotIn('reserve_release',[x['id'] for x in p['findings']])
    def test_non_income_release(self):
        self.data['periods'][1]['reserves'][0]['release_in_income']=False
        self.assertIsNone(analyze(self.data)['periods'][1]['reserves'][0]['pretax_release_benefit'])
    def test_no_average_for_gap(self):
        self.data['periods'][1]['start']='2026-01-01';self.data['periods'][1]['end']='2026-12-31'
        self.assertIsNone(analyze(self.data)['periods'][1]['metrics']['rnoa']['value'])
    def test_unknown_source(self):
        self.data['periods'][0]['values']['revenue']['source_ids']=['invented']
        with self.assertRaises(ValueError):analyze(self.data)
    def test_invalid_numbers(self):
        for v in [True,float('nan'),float('inf')]:
            self.data['periods'][0]['values']['revenue']['value']=v
            with self.assertRaises(ValueError):analyze(self.data)
    def test_ytd_rejected(self):
        self.data['periods'][0]['kind']='quarter'
        with self.assertRaises(ValueError):analyze(self.data)
    def test_negative_denominator(self):
        for p in self.data['periods']:p['values']['assets']['value']=-1
        self.assertIsNone(analyze(self.data)['periods'][1]['metrics']['accrual_ratio']['value'])
    def test_mismatched_rollforward(self):
        self.data['periods'][1]['reserves'][0]['closing']['value']=99
        r=analyze(self.data)['periods'][1]['reserves'][0]
        self.assertFalse(r['reconciles']);self.assertIsNone(r['pretax_release_benefit'])
    def test_adapter_no_invented_dates(self):
        x=convert({'quarters':[{'end':'2025-12-31','headline':{'ni':3}}]})
        self.assertIsNone(x['periods'][0]['start']);self.assertTrue(x['import_notes'])
    def test_router(self):
        m=train();self.assertEqual(predict('warranty reserve release',m)['label'],'reserves')
        self.assertEqual(predict('zzzz',m)['label'],'unknown')
    def test_training_split_and_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'data.jsonl';rows=generate(20)
            p.write_text('\n'.join(json.dumps(r) for r in rows));self.assertEqual(len(read_dataset(p)),80)
            rows[0]['origin']='gemini';p.write_text('\n'.join(json.dumps(r) for r in rows))
            with self.assertRaises(ValueError):read_dataset(p)
    def test_company_leak(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'data.jsonl';rows=generate(20);rows[0]['split']='train'
            p.write_text('\n'.join(json.dumps(r) for r in rows))
            with self.assertRaises(ValueError):read_dataset(p)

class GeminiTests(unittest.TestCase):
    def setUp(self):self.report=analyze(json.loads((ROOT/'examples/demo.json').read_text()))
    def transport(self,request):
        self.assertIn('generativelanguage.googleapis.com',request.full_url)
        return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps({'summary':'Review cash conversion.','observations':[{'text':'Inspect reserve estimates.','source_ids':['demo-2025']}],'limitations':['Not proof of manipulation.']})}]}}]}
    def test_disabled_without_key(self):
        with patch.dict(os.environ,{},clear=True),tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):explain(self.report,d,self.transport)
    def test_cache_budget_and_no_training(self):
        with patch.dict(os.environ,{'FSA_BETA_GEMINI_KEY':'fake','FSA_BETA_GEMINI_MODEL':'test-model','FSA_BETA_FREE_PROJECT_CONFIRMED':'1'},clear=True),tempfile.TemporaryDirectory() as d:
            a=explain(self.report,d,self.transport);self.assertFalse(a['training_eligible'])
            self.assertTrue(explain(self.report,d,self.transport)['cached'])
            changed=copy.deepcopy(self.report);changed['company']='Different'
            with self.assertRaises(ValueError):explain(changed,d,self.transport)
    def test_unknown_evidence_rejected(self):
        def bad(req):
            x=self.transport(req);obj=json.loads(x['candidates'][0]['content']['parts'][0]['text']);obj['observations'][0]['source_ids']=['bogus'];x['candidates'][0]['content']['parts'][0]['text']=json.dumps(obj);return x
        with patch.dict(os.environ,{'FSA_BETA_GEMINI_KEY':'fake','FSA_BETA_GEMINI_MODEL':'test','FSA_BETA_FREE_PROJECT_CONFIRMED':'1'},clear=True),tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):explain(self.report,d,bad)

if __name__=='__main__':unittest.main()
