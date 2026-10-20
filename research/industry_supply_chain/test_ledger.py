"""Offline tests; SEC network calls intentionally not exercised."""
import json
import tempfile
from pathlib import Path
import unittest

try:
    from .ledger import open_db, ingest_gamma, add_relation, coverage, reconcile
    from .sec_capex import quarterly_cash_capex, universe, save_cash_capex, save_submissions
except ImportError:
    from ledger import open_db, ingest_gamma, add_relation, coverage, reconcile
    from sec_capex import quarterly_cash_capex, universe, save_cash_capex, save_submissions


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.db=open_db(Path(self.t.name)/"research.sqlite")
        self.gamma=Path(self.t.name)/"site"/"gamma"
        self.gamma.mkdir(parents=True)
        (self.gamma/"index.json").write_text(json.dumps(
            {"industries":[{"sic":"3572","name":"Storage Equipment","sector":"Technology"}]}))
        (self.gamma/"3572.json").write_text(json.dumps({
            "companies":[{"cik":"00000001","ticker":"ONE","name":"One Inc","current":{"end":"2026-06-30"}},
                         {"cik":"00000002","ticker":"TWO","name":"Two Inc"}],
            "relationships":[{"supplier_cik":"1","customer_cik":"2","source":"chain_customer_disclosure"},
                             {"supplier":"OTHER","customer":"TWO"}]}))

    def tearDown(self):
        self.db.close()
        self.t.cleanup()

    def test_gamma_census_does_not_invent_evidence(self):
        result=ingest_gamma(self.db,self.gamma.parent)
        self.assertEqual(result["imported_company_records"],2)
        self.assertEqual(result["unresolved_or_unsafe_edges"],1)
        c=coverage(self.db)
        self.assertEqual((c["companies"],c["industries"],c["relations"],c["verified_relations"]),(2,1,1,0))
        r=self.db.execute("SELECT reported_transaction_usd,evidence_level FROM relations").fetchone()
        self.assertIsNone(r["reported_transaction_usd"])
        self.assertEqual(r["evidence_level"],"inferred")

    def test_value_rejected_without_sec_evidence(self):
        ingest_gamma(self.db,self.gamma.parent)
        with self.assertRaises(ValueError):
            add_relation(self.db,{"supplier_cik":"1","customer_cik":"2","reported_transaction_usd":10})
        with self.assertRaises(ValueError):
            add_relation(self.db,{"supplier_cik":"1","customer_cik":"2",
                                  "evidence_level":"disclosed","source":{"url":"https://example.com"}})

    def test_disclosed_relation_requires_traceable_sec_accession(self):
        ingest_gamma(self.db,self.gamma.parent)
        r=add_relation(self.db,{"supplier_cik":"1","customer_cik":"2","category":"customer",
                "evidence_level":"disclosed","reported_transaction_usd":125,
                "source":{"url":"https://www.sec.gov/Archives/edgar/data/1/a.htm",
                          "accession":"0001-26-000001","filed_at":"2026-08-01","form":"10-Q"}})
        actual=self.db.execute("SELECT reported_transaction_usd,evidence_id FROM relations WHERE relation_id=?",(r,)).fetchone()
        self.assertEqual(actual["reported_transaction_usd"],125)
        self.assertTrue(actual["evidence_id"])

    def test_quarterly_cash_capex_and_asof_gate(self):
        fact={"facts":{"us-gaap":{"PaymentsToAcquirePropertyPlantAndEquipment":{"units":{"USD":[
          {"start":"2026-01-01","end":"2026-03-31","val":90,"form":"10-Q","filed":"2026-04-20","accn":"a","fy":2026,"fp":"Q1"},
          {"start":"2026-01-01","end":"2026-09-30","val":270,"form":"10-Q","filed":"2026-10-15","accn":"b","fy":2026,"fp":"Q3"},
          {"start":"2026-01-01","end":"2026-12-31","val":350,"form":"10-K","filed":"2027-02-15","accn":"c","fy":2026,"fp":"FY"}]}}}}}
        old=quarterly_cash_capex(fact,"2026-11-01")
        self.assertEqual([x["end"] for x in old],["2026-03-31"])
        latest=quarterly_cash_capex(fact,"2027-02-20")
        self.assertEqual(latest[-1]["end"],"2026-12-31")
        self.assertEqual(latest[-1]["quarterly_value"],80)
        self.assertEqual(latest[-1]["method"],"ytd_difference")
        universe(self.db,{"0":{"cik_str":1,"ticker":"ONE","title":"One Inc"}})
        self.assertEqual(save_cash_capex(self.db,"1",fact,as_of="2027-02-20"),2)
        self.assertEqual(coverage(self.db)["capex_rows"],2)

    def test_sic_extracted_without_implying_full_coverage(self):
        universe(self.db,{"0":{"cik_str":3,"ticker":"THR","title":"Third Inc"}})
        row=self.db.execute("SELECT sic FROM companies WHERE cik='3'").fetchone()
        self.assertIsNone(row["sic"])
        save_submissions(self.db,"3",{"name":"Third Inc","sic":"3572",
                                     "sicDescription":"Computer Storage Devices","tickers":["THR"]})
        row=self.db.execute("SELECT sic FROM companies WHERE cik='3'").fetchone()
        self.assertEqual(row["sic"],"3572")

    def test_reconciliation_requires_real_comparable_revenue(self):
        ingest_gamma(self.db,self.gamma.parent)
        self.db.execute("""INSERT INTO attributed_revenue VALUES(?,?,?,?,?,?,?,?,?)""",
                        ("base","1","2","network","2026-06-30",90,"2026-05-01","estimated","bottom-up"))
        self.db.commit()
        missing=reconcile(self.db,"base","2026-06-30","2026-09-01")
        self.assertEqual(len(missing),1)
        self.assertIsNone(missing[0]["percentage_error"])
        self.db.execute("""INSERT INTO financials VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        ("2","revenue_segment","2026-06-30",2026,"Q2",100,"issuer_segment",
                         "https://www.sec.gov/Archives/edgar/data/2/x","demo-accession",
                         "2026-08-01","2026-08-01"))
        self.db.commit()
        result=reconcile(self.db,"base","2026-06-30","2026-09-01")
        self.assertAlmostEqual(result[0]["percentage_error"],-0.1)
        self.assertAlmostEqual(result[0]["unattributed_other_customers_usd"],10)

if __name__=="__main__":
    unittest.main()
