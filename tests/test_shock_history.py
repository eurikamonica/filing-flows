import json
from pathlib import Path
import tempfile
import unittest

from pipeline import shock_history as H


def fixture():
    facts = {}
    def add(tag, end, value, start=None):
        f = {'end':end, 'val':value, 'filed':'2011-02-01', 'form':'10-K', 'accn':'0000000001-11-000001'}
        if start:
            f['start'] = start
        facts.setdefault(tag, {'units':{'USD':[]}})['units']['USD'].append(f)
    for i, end in enumerate(['2010-03-31','2010-06-30','2010-09-30','2010-12-31']):
        # YTD figures test both cash-flow subtraction and Q4 = FY minus 9m.
        for tag, amount in [('Revenues',100),('NetIncomeLoss',-5),('OperatingIncomeLoss',10),
                            ('NetCashProvidedByUsedInOperatingActivities',20),
                            ('PaymentsToAcquirePropertyPlantAndEquipment',3),('CostOfRevenue',60),
                            ('ShareBasedCompensation',2),('ResearchAndDevelopmentExpense',4)]:
            add(tag,end,amount*(i+1),'2010-01-01')
        for tag, amount in [('Assets',1000),('AssetsCurrent',200),('LiabilitiesCurrent',100),
                            ('AccountsReceivableNetCurrent',50),('InventoryNet',20),('AccountsPayableCurrent',30)]:
            add(tag,end,amount)
    for tag, amount in [('Assets',900),('AccountsReceivableNetCurrent',40),('InventoryNet',20),('AccountsPayableCurrent',25)]:
        add(tag,'2009-12-31',amount)
    return {'cik':1, 'facts':{'us-gaap':facts}}


class HistoryTests(unittest.TestCase):
    def test_quarterly_cash_history_and_evidence(self):
        result = H.compute(fixture(), '2026-10-27')
        self.assertEqual(len(result['rows']),4)
        for q in result['rows']:
            self.assertEqual(q['values']['revenue'],100)
            self.assertEqual(q['values']['ocf'],20)
            self.assertEqual(q['values']['capex'],3)
            self.assertEqual(q['values']['gp'],40)
            self.assertEqual(q['values']['ni'],-5)
        self.assertEqual(result['rows'][-1]['sources']['ocf'][1],'ytd')
        self.assertTrue(result['src']['filings'])
        self.assertEqual(result['coverage']['current_assets'],4)

    def test_missing_and_currencies_are_not_filled(self):
        f = fixture()
        del f['facts']['us-gaap']['PaymentsToAcquirePropertyPlantAndEquipment']
        f['facts']['us-gaap']['ResearchAndDevelopmentExpense']['units']['EUR'] = f['facts']['us-gaap']['ResearchAndDevelopmentExpense']['units'].pop('USD')
        r = H.compute(f)
        self.assertEqual(r['coverage']['capex'],0)
        self.assertEqual(r['coverage']['rd'],0)
        self.assertNotIn('capex',r['rows'][0]['values'])

    def test_no_quarter_invented_from_annual_only_or_six_month_gaps(self):
        f = fixture()
        for tag, body in f['facts']['us-gaap'].items():
            body['units']['USD'] = [v for v in body['units']['USD'] if v['end']=='2010-12-31']
        self.assertEqual(H.compute(f)['rows'],[])

    def test_balance_opening_and_ccc(self):
        r = H.compute(fixture())['rows'][0]['values']
        self.assertEqual(r['assets_open'],900)
        self.assertAlmostEqual(r['dso'],40.5)
        self.assertTrue(H.finite(r['ccc']))
        f = fixture()
        del f['facts']['us-gaap']['InventoryNet']
        self.assertNotIn('ccc',H.compute(f)['rows'][0]['values'])

    def test_queue_backoff_and_refresh(self):
        cs = [{'cik':1,'ticker':'AAPL','filed':'2026-10-27','revenue':10}, {'cik':2,'ticker':'X','filed':'2026-10-01'}]
        ledger = {'1':{'v':1,'filed':'2026-10-27','attempted_at':100000}, '2':{'error':'RuntimeError','attempted_at':100000}}
        self.assertEqual(H.queue(cs,ledger,100100),[])
        cs[0]['filed']='2026-10-28'
        self.assertEqual([c['cik'] for c in H.queue(cs,ledger,100100)],[1])
        self.assertEqual(len(H.queue(cs,ledger,100000+8*86400)),2)

    def test_incremental_collect_preserves_success_and_resumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            idx={'companies':[{'cik':1,'ticker':'AAPL','filed':'2026-10-27'}, {'cik':2,'ticker':'X','filed':'2026-10-27'}]}
            def fetch(cik):
                if cik==2:
                    raise RuntimeError('provider unavailable')
                return fixture()
            r=H.collect(tmp,idx,fetch=fetch)
            self.assertEqual((r['processed'],r['failed'],r['pending']),(1,1,1))
            original=(Path(tmp)/'public/c/1.json').read_text()
            r=H.collect(tmp,idx,fetch=lambda cik:self.fail('should reuse successful and backed-off records'))
            self.assertEqual(r['run']['attempted'],0)
            self.assertEqual((Path(tmp)/'public/c/1.json').read_text(),original)
            self.assertEqual(json.loads((Path(tmp)/'public/status.json').read_text())['total'],2)

    def test_identity_mismatch_not_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=H.collect(tmp,{'companies':[{'cik':2}]},fetch=lambda cik:fixture())
            self.assertEqual(r['processed'],0)
            self.assertFalse((Path(tmp)/'public/c/2.json').exists())


if __name__ == '__main__':
    unittest.main()
