"""Offline invariants for the scheduled FSA question generator (no GPU/network)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import fsa_hourly_bank as bank


class HourlyQuestionBankTests(unittest.TestCase):
    def test_18_questions_balanced_statements_and_entries(self):
        for seed in range(100,130):
            rows=bank.synthetic(seed,18)
            self.assertEqual(len(rows),18)
            self.assertEqual(len({x["id"] for x in rows}),18)
            for entry in rows:
                self.assertEqual(entry["expected"],json.loads(entry["output"]))
                self.assertTrue(entry["training_eligible"])
                if entry["task"]=="journal_entry":
                    entries=entry["expected"]["entries"]
                    self.assertEqual(sum(x["debit"] for x in entries),sum(x["credit"] for x in entries))
                if entry["task"]=="three_statements":
                    data=entry["expected"];bs=data["BS"];scf=data["SCF"]
                    self.assertEqual(bs["cash"]+bs["inventory"]+bs["ppe"],bs["debt"]+bs["equity"])
                    self.assertEqual(data["IS"]["NI"],data["IS"]["revenue"]-data["IS"]["COGS"])
                    self.assertEqual(scf["cash_change"],bs["cash"]-100)
                if entry["task"]=="evidence_abstention":
                    self.assertIsNone(entry["expected"]["long_term_debt"])

    def test_research_rights_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"registry.json"
            records=[
              {"id":"licensed-1","review_status":"approved","ml_rights":"owned",
               "public_redistribution_allowed":True,"rights_evidence":"owner grant",
               "facts":[{"name":"Revenue","value":123,"unit":"USD millions",
                         "period":"FY2024","locator":"p3 t1","verified":True}]},
              {"id":"unlicensed-2","review_status":"approved","ml_rights":"unknown",
               "facts":[{"name":"Revenue","value":456,"unit":"USD millions",
                         "period":"FY2024","locator":"p3","verified":True}]}
            ]
            path.write_text(json.dumps(records),encoding="utf-8")
            rows,issues=bank.from_reports(path)
            self.assertEqual(len(rows),1)
            self.assertEqual(len(issues),1)
            self.assertEqual(rows[0]["expected"]["value"],123)
            self.assertTrue(rows[0]["training_eligible"])
            self.assertIn("123 USD millions",rows[0]["input"])

    def test_sec_period_and_same_accession(self):
        def rec(end,start,val,accn):
            return {"form":"10-K","fp":"FY","end":end,"start":start,
                    "val":val,"accn":accn,"filed":"2026-02-01"}
        curr=rec("2025-12-31","2025-01-01",120,"b")
        prev=rec("2024-12-31","2024-01-01",100,"a")
        doc={"facts":{"us-gaap":{
          "RevenueFromContractWithCustomerExcludingAssessedTax":{"units":{"USD":[prev,curr]}},
          "NetCashProvidedByUsedInOperatingActivities":{"units":{"USD":[rec("2025-12-31","2025-01-01",60,"b")]}},
          "PaymentsToAcquirePropertyPlantAndEquipment":{"units":{"USD":[rec("2025-12-31","2025-01-01",10,"b")]}}
        }}}
        results=bank.from_sec(doc,"FAKE","fixture")
        by={x["task"]:x for x in results}
        self.assertAlmostEqual(by["sec_revenue_growth"]["expected"]["value"],.2)
        self.assertEqual(by["sec_fcf"]["expected"]["value"],50)
        self.assertFalse(by["sec_fcf"]["training_eligible"])

    def test_error_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"evaluation.json"
            p.write_text(json.dumps({"protocols":{"open_dev":{"examples":[
              {"task":"journal_entry","correct":False},
              {"task":"accrual_ratio","correct":False},
              {"task":"accrual_ratio","correct":True}]}}}),encoding="utf-8")
            report=bank.error_report(p)
            self.assertEqual(report["seen"],3)
            self.assertEqual(report["wrong"],2)
            self.assertEqual(report["by_task"]["accrual_ratio"],1)


if __name__=="__main__":
    unittest.main()
