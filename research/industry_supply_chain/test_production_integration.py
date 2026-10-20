"""Offline end-to-end production integration tests with no SEC / web requests."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

from research.industry_supply_chain.ledger import open_db, ensure_company
from research.industry_supply_chain.production import model_scenario, publish

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("integrate_industry",ROOT/"scripts"/"integrate_industry.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Integration(unittest.TestCase):
    def test_research_model_does_not_write_fictional_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            con=open_db(Path(tmp)/"x.sqlite")
            for c,t,n in (("1","GOOGL","Google"),("2","NVDA","NVIDIA")):
                ensure_company(con,{"cik":c,"ticker":t,"name":n,"sic":"3572"},"2026-10-20")
            scenario={"demo_only":True,"buyer":"GOOGL (hypothetical)","period":"2026Q4",
                      "categories":{"compute":{"weight":1,"suppliers":{"NVDA":0.6}}},
                      "recognition_lags":{"0":1},
                      "scenarios":[{"name":"Base","capex_usd":1000}]}
            r=model_scenario(con,scenario,"2026-10-20T00:00:00Z")
            self.assertTrue(r["demo_only"])
            self.assertEqual(r["buyer_cik"],"1")
            self.assertEqual(r["scenarios"][0]["terminal_vendor_usd"]["NVDA"],600)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM attributed_revenue").fetchone()[0],0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM relations").fetchone()[0],0)
            con.close()

    def test_no_feed_stays_visible_as_not_collected(self):
        with tempfile.TemporaryDirectory() as tmp:
            site=Path(tmp)/"site"
            status=module.stage(site,Path(tmp)/"absent")
            self.assertEqual(status["collection"]["status"],"not_collected")
            self.assertEqual(status["publication"]["status"],"artifact_prepared_unverified")
            self.assertTrue((site/"supplier-revenue"/"index.html").exists())
            self.assertTrue((site/"integration-health"/"index.html").exists())
            self.assertEqual(json.loads((site/"data"/"industry-intelligence"/"forecast.json").read_text())["real_forecasts"],[])

    def test_gamma_and_prediction_markets_identity_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/"snapshot"
            (source/"industry").mkdir(parents=True)
            (source/"industry"/"3572.json").write_text(json.dumps({
                "sic":"3572","name":"Computer storage","sector":"Technology",
                "companies":[{"cik":"1","ticker":"ONE","name":"One Inc","sic":"3572"},
                             {"cik":"2","ticker":"TWO","name":"Two Inc","sic":"3572"}],
                "relationships":[{"supplier_cik":"1","customer_cik":"2","evidence_level":"inferred",
                                  "relationship_type":"supplier_customer","value_usd":None}]
            }))
            (source/"industry"/"index.json").write_text(json.dumps({"industries":[{"sic":"3572"}],
                                                                     "coverage":{"companies":2}}))
            (source/"health.json").write_text(json.dumps({"sqlite_counts":{"companies":2,"companies_with_sic":2}}))
            (source/"forecast.json").write_text(json.dumps({"real_forecasts":[],"status":"no_reviewed_forecast"}))
            site=root/"site"
            gamma=site/"data"/"gamma"
            gamma.mkdir(parents=True)
            (gamma/"3572.json").write_text(json.dumps({"sic":"3572","relationships":[]}))
            cons=site/"disclosures"/"data"/"consensus"
            cons.mkdir(parents=True)
            (cons/"markets.json").write_text(json.dumps({"rows":[
                {"ticker":"ONE","source":"kalshi","title":"Company event","p":0.5,"kind":"other","url":"https://example.test"},
                {"ticker":"NOPE","source":"polymarket","title":"Unmatched event","p":0.5}]}))
            a=module.stage(site,source)
            self.assertEqual(a["gamma_integration"]["added_relations"],1)
            edge=json.loads((gamma/"3572.json").read_text())["relationships"][0]
            self.assertIsNone(edge["value_usd"])
            self.assertEqual(edge["evidence_level"],"inferred")
            events=json.loads((site/"data"/"industry-intelligence"/"events.json").read_text())
            self.assertEqual(events["matched_events"],1)
            self.assertEqual(events["events"][0]["causal_revenue_impact"],"not_estimated")

if __name__=="__main__":
    unittest.main()
