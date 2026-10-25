"""Offline tests for published, source-backed Flo event feed (no network)."""
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "build_flo_alerts.py"
spec = importlib.util.spec_from_file_location("build_flo_alerts", MODULE)
alerts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alerts)
NOW = datetime(2026, 10, 26, 16, 0, tzinfo=timezone.utc)


def write(root, name, value):
    (root / name).write_text(json.dumps(value), encoding="utf-8")


class FloPublishedFeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_source_anchored_multi_feed_output(self):
        write(self.root, "events8k.json", {
            "generated_at": "2026-10-26T15:30:00Z", "rows": [
                {"form": "8-K", "ticker": "NVDA", "accession": "0001045810-26-000199",
                 "url": "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000199/",
                 "filed": "2026-10-26", "accepted": "2026-10-26T10:20",
                 "topics": ["restatement"], "label": "Restatement filing",
                 "quote": "A portion of the 2026 filing requires amendment"},
                {"form": "8-K", "ticker": "AAPL", "accession": "spoof",
                 "url": "https://malware.invalid/x", "filed": "2026-10-26",
                 "accepted": "2026-10-26T10:20", "topics": ["auditor"]},
                {"form": "10-K", "ticker": "AAPL", "accession": "not-8k",
                 "url": "https://www.sec.gov/Archives/edgar/data/1/a/",
                 "filed": "2026-10-26", "topics": ["deal"]}
            ]})
        write(self.root, "watchlist.json", {
            "generated_at": "2026-10-26T14:00:00Z", "funds": [{
                "cik": "1067983", "name": "Berkshire Hathaway", "filed": "2026-10-26",
                "period": "2026-09-30",
                "source": "https://www.sec.gov/Archives/edgar/data/1067983/000106798326000001/",
                "new": [{"ticker": "AAPL"}],
                "added": [{"ticker": "NVDA"}],
                "cut": [{"ticker": "BAC"}],
                "exited": [{"ticker": "XYZ"}]}]})
        write(self.root, "news.json", {"generated_at": "2026-10-26T15:15:00Z", "rows": [
            {"id": "news-one", "source": "PR Newswire", "title": "NVIDIA press release",
             "url": "https://www.prnewswire.com/news-releases/nvda-2026.html",
             "published": "2026-10-26T15:12:00Z", "tickers": ["NVDA"]},
            {"id": "news-unknown", "source": "PR Newswire", "title": "Unknown company",
             "url": "https://www.prnewswire.com/news-releases/unknown.html",
             "published": "2026-10-26T15:12:00Z", "tickers": []},
            {"id": "news-unsafe", "source": "SEC", "title": "Unsafe source",
             "url": "https://notsec.gov/news", "published": "2026-10-26T15:12:00Z",
             "tickers": ["NVDA"]}]})
        write(self.root, "extremes.json", {
            "generated_at": "2026-10-26T15:30:00Z", "asof": "2026-10-26",
            "fields": ["ticker","close","chg1d"],
            "rows": [["IREN", 45.5, -0.12], ["CRWV", 76.2, 0.085],
                     ["MSFT", 420, 0.01], ["BAD", 3, 99]]})
        built=alerts.build(self.root,NOW)
        self.assertEqual(built["schema"],1)
        by={x["kind"]: [e for e in built["events"] if e["kind"]==x["kind"]]
            for x in built["events"]}
        self.assertEqual(set(by),{"8k","13f","news","price"})
        self.assertEqual(len(by["8k"]),1)
        sec=by["8k"][0]
        self.assertEqual(sec["priority"],"high")
        # EDGAR acceptance clock is Eastern; 10:20 EDT -> 14:20 UTC
        self.assertEqual(sec["event_at"],"2026-10-26T14:20:00Z")
        f13=by["13f"][0]
        self.assertEqual(f13["period_end"],"2026-09-30")
        self.assertEqual(f13["symbols"],["AAPL","NVDA","BAC","XYZ"])
        self.assertEqual(f13["manager"],"Berkshire Hathaway")
        self.assertEqual(f13["changes"]["Added"],["NVDA"])
        self.assertIn("trade",f13["scope"].lower())
        self.assertEqual(len(by["news"]),1)
        self.assertEqual(by["news"][0]["ticker"],"NVDA")
        self.assertEqual({x["ticker"] for x in by["price"]},{"IREN","CRWV"})
        self.assertEqual(by["price"][0]["price_asof"],"2026-10-26")
        self.assertIn("NOT live",by["price"][0]["scope"])
        self.assertTrue(all(x["id"] and x["event_at"] for x in built["events"]))
        self.assertEqual(len(built["events"]),5)

    def test_backfill_and_missing_data_never_fabricated(self):
        write(self.root,"events8k.json",{"generated_at":"2026-10-26T16:00:00Z",
                "rows":[{"accession":"old","ticker":"NVDA",
                "url":"https://www.sec.gov/Archives/edgar/data/1/old/",
                "form":"8-K","filed":"2026-09-10","topics":["bankruptcy"]}]})
        result=alerts.build(self.root,NOW)
        self.assertEqual(result["events"],[])
        self.assertFalse(result["sources"]["13f"])
        self.assertFalse(result["sources"]["price"])
        self.assertFalse(result["sources"]["news"])

    def test_invalid_links_and_missing_symbols(self):
        self.assertFalse(alerts.SEC.match("https://sec.gov.evil.invalid/Archives/"))
        self.assertEqual(alerts.symbol("NVDA"),"NVDA")
        self.assertEqual(alerts.symbol("<script>"),"")
        self.assertFalse(alerts.recent("2026-01-01",NOW,4))
        self.assertEqual(alerts.stamp("2026-10-26T10:20",eastern=True),
                         "2026-10-26T14:20:00Z")
        self.assertEqual(alerts.stamp("invalid"),"")


if __name__ == "__main__":
    unittest.main()
