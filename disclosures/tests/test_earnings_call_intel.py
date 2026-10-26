"""Deterministic IR+SEC fixtures. No paid data and no external HTTP requests."""
import datetime as dt
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import earnings_call_intel as INT
import earnings_calls_phase2 as P2

TRANSCRIPT = (b"<html><h1>Wednesday, July 29, 2026</h1><h2>Transcript</h2>"
              b"<p>JONATHAN NEILSON:</p><p>" + b"Welcome to our earnings call. " * 75 +
              b"</p><p>AMY HOOD:</p><p>We expect FY2027 revenue to be between $100 and $120 billion. "
              b"We expect FY2027 capital expenditures to be between $20 and $30 billion. "
              + b"Other details on the company's financial performance. " * 22 +
              b"</p><p>OPERATOR:</p><p>We will now take questions and answers.</p>"
              b"<p>JANE ANALYST:</p><p>Could you explain how AI capacity affects "
              b"capital expenditures and pricing through next year?</p>"
              b"<p>AMY HOOD:</p><p>Thank you for the question. We are investing "
              b"to meet customer demand, but cannot estimate the exact incremental margin.</p></html>")
IR_INDEX = (b"<html><a href='/investor/call-2026.html'>Q4 2026 Earnings Transcript</a>"
            b"<a href='/investor/transcript-2026.pdf'>Earnings Call Transcript (PDF)</a>"
            b"<a href='https://evil.example/payload'>Earnings Transcript</a>"
            b"<a href='javascript:alert(1)'>Earnings</a>"
            b"<a href='/investor/press.html'>Earnings Press Release</a></html>")


class FixtureClient:
    def __init__(self, fail_index=False):
        self.fail_index = fail_index
    def json(self, url, sec=False):
        return {"filings": {"recent": {"form": ["8-K"], "items": ["2.02,9.01"],
                "filingDate": ["2026-07-29"],
                "accessionNumber": ["0000789019-26-000001"],
                "primaryDocument": ["sample.htm"]}}}
    def get(self, url):
        if "index" in url:
            if self.fail_index:
                raise RuntimeError("upstream unavailable")
            return IR_INDEX
        return TRANSCRIPT


class EarningsIntelTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "max_ir_indexes_per_company": 1, "max_discovery_candidates_per_company": 6,
            "max_verify_html_per_company": 2,
            "companies": [{
                "ticker": "MSFT", "cik": 789019,
                "allowed_ir_hosts": ["ir.example.com"],
                "ir_indexes": ["https://ir.example.com/investor/index.html"],
                "ir_event_pages": [],
                "management_speakers": ["AMY HOOD"],
            }]
        }
        self.day = dt.date(2026, 8, 15)

    def test_official_index_discovery_is_allowlisted(self):
        links = INT.discover_links("https://ir.example.com/investor/index.html",
                                   IR_INDEX, ["ir.example.com"])
        self.assertEqual(len(links), 2)
        self.assertEqual(links[1]["kind"], "transcript_pdf_candidate")
        self.assertFalse(INT.trusted("http://ir.example.com/", ["ir.example.com"]))
        self.assertFalse(INT.trusted("https://ir.example.com.evil.test/", ["ir.example.com"]))
        self.assertFalse(INT.trusted("https://evil.example/payload", ["ir.example.com"]))

    def test_named_turns_guidance_qa_and_math(self):
        turns = INT.split_turns(TRANSCRIPT)
        self.assertEqual(turns[1]["speaker"], "AMY HOOD")
        result = INT.guidance_and_questions(turns, "MSFT", ["AMY HOOD"])
        self.assertEqual(len(result["guidance"]), 2)
        self.assertEqual(result["qa_count_detected"], 1)
        self.assertEqual(result["qa_topic_counts"].get("capex"), 1)
        task = next(x for x in result["quantitative_exercises"] if x["metric"] == "revenue")
        self.assertEqual(task["answer"]["midpoint"], 110)
        self.assertEqual(task["answer"]["width"], 20)
        self.assertIn("unreconciled", task["verification"])
        ratio = next(x for x in result["quantitative_exercises"] if x["type"] == "mechanical_ratio_bounds")
        self.assertEqual(ratio["answer"]["minimum_pct"], 16.67)
        self.assertEqual(ratio["answer"]["maximum_pct"], 30.0)
        relative = next(x for x in result["quantitative_exercises"] if x["type"] == "relative_guidance_width")
        self.assertGreater(relative["answer"]["relative_width_pct"], 0)
        self.assertNotIn("text", result["guidance"][0])  # no transcript redistribution

    def test_no_hallucinated_guidance_from_historical_numbers(self):
        only = [{"speaker": "AMY HOOD", "qa_section": False, "turn": 1,
                 "text": "Revenue was $200 billion and rose 30% year on year."}]
        self.assertEqual(INT.guidance_and_questions(only, "MSFT", ["AMY HOOD"])["guidance"], [])

    def test_same_horizon_guidance_comparison_only(self):
        prior = [{"date": "2026-04-01", "guidance": [{
            "metric": "revenue", "horizon": "FY2027", "unit": "USD billions",
            "low": 80, "high": 100}]}]
        cur = {"guidance": [{"metric": "revenue", "horizon": "FY2027",
                             "unit": "USD billions", "low": 100, "high": 120}]}
        r = INT.guidance_changes(cur, prior)
        self.assertEqual(r[0]["delta"], 20)
        cur["guidance"][0]["horizon"] = "FY2028"
        self.assertEqual(INT.guidance_changes(cur, prior), [])

    def test_phase2_separates_ir_candidate_and_verified(self):
        out = P2.phase2_scan(self.cfg, FixtureClient(), today=self.day)
        self.assertEqual(out["counts"]["official_ir_candidates"], 2)
        self.assertEqual(out["counts"]["official_transcripts"], 1)
        self.assertEqual(out["counts"]["quantitative_exercises"], 5)
        rows = out["rows"]
        for r in rows:
            if r["kind"] == "official_ir_candidate":
                self.assertEqual(r["transcript_status"], "discovered_not_verified")
        checked = next(r for r in rows if r["kind"] == "official_ir_transcript")
        self.assertIn("verified_at", checked)
        repeat = P2.phase2_scan(self.cfg, FixtureClient(), previous=out, today=self.day)
        reread = next(r for r in repeat["rows"] if r["kind"] == "official_ir_transcript")
        self.assertEqual(reread["verified_at"], checked["verified_at"])

    def test_failed_ir_index_preserves_valid_data(self):
        first = P2.phase2_scan(self.cfg, FixtureClient(), today=self.day)
        second = P2.phase2_scan(self.cfg, FixtureClient(fail_index=True),
                                previous=first, today=self.day)
        self.assertEqual(second["status"], "partial")
        self.assertEqual(second["counts"]["official_transcripts"], 1)
        self.assertTrue(second["errors"])


if __name__ == "__main__":
    unittest.main()
