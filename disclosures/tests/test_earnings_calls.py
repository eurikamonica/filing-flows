"""Isolated fixtures: no external network and no paid data provider."""
import datetime as dt
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import earnings_calls as ec

HTML = (b"<html><main><h1>Wednesday, July 29, 2026</h1>"
        b"<h2>Transcript</h2><p>JONATHAN NEILSON:</p><p>" + b"Welcome to the call. " * 70 +
        b"</p><p>SATYA NADELLA:</p><p>" + b"Revenue and outlook in detail. " * 70 +
        b"</p></main></html>")


class Client:
    def __init__(self, fail=False):
        self.fail = fail

    def json(self, url, sec=False):
        if self.fail:
            raise RuntimeError("HTTP 503")
        assert sec and "data.sec.gov" in url
        return {"filings": {"recent": {"form": ["8-K", "8-K", "10-Q"],
                "items": ["2.02,9.01", "5.02", ""],
                "filingDate": ["2026-07-29", "2026-07-30", "2026-07-30"],
                "accessionNumber": ["0000789019-26-000001", "0000789019-26-000002", "0000789019-26-000003"],
                "primaryDocument": ["msft.htm", "other.htm", "quarter.htm"]}}}

    def get(self, url):
        return HTML


class TestOfficialCalls(unittest.TestCase):
    def setUp(self):
        self.cfg = {"companies": [{"ticker": "MSFT", "cik": 789019,
                    "allowed_ir_hosts": ["www.microsoft.com"],
                    "ir_event_pages": ["https://www.microsoft.com/en-us/investor/events/x"]}]}
        self.today = dt.date(2026, 8, 10)

    def test_transcript_requires_speakers(self):
        self.assertIsNotNone(ec.inspect_ir_html(HTML))
        self.assertIsNone(ec.inspect_ir_html(b"<h2>Transcript</h2><p>No transcript available</p>"))

    def test_sec_8k_is_not_a_transcript(self):
        rows = ec.scan(self.cfg, Client(), today=self.today)["rows"]
        self.assertEqual(len(rows), 2)
        sec = next(r for r in rows if r["kind"] == "sec_earnings_evidence")
        ir = next(r for r in rows if r["kind"] == "official_ir_transcript")
        self.assertEqual(sec["transcript_status"], "not_verified")
        self.assertEqual(ir["transcript_status"], "verified_official_link")
        self.assertEqual(ir["sec_accession"], sec["accession"])

    def test_failed_sec_retains_good_previous(self):
        previous = ec.scan(self.cfg, Client(), today=self.today)
        current = ec.scan(self.cfg, Client(fail=True), previous=previous, today=self.today)
        self.assertEqual(current["status"], "partial")
        self.assertEqual(current["counts"]["sec_earnings_evidence"], 1)
        self.assertEqual(current["counts"]["official_transcripts"], 1)

    def test_reject_unapproved_ir(self):
        self.assertFalse(ec._trusted("https://other.example.org/fake", ["www.microsoft.com"]))
        self.assertFalse(ec._trusted("http://www.microsoft.com/", ["www.microsoft.com"]))

    def test_microsoft_quarter_rollover(self):
        urls = ec.microsoft_candidates(dt.date(2026, 10, 25))
        self.assertIn("fy-2027-q2", urls[0])
        self.assertIn("fy-2027-q1", urls[1])
        self.assertIn("fy-2026-q4", urls[2])


if __name__ == "__main__":
    unittest.main()
