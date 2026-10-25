"""Contract tests for post-stage Flo alert feed: no fabricated times or prices."""
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from scripts import build_flo_alerts as F


class AlertBuildTests(unittest.TestCase):
    NOW = datetime(2026, 10, 26, 16, 0, tzinfo=timezone.utc)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def put(self, name, data):
        (self.path / name).write_text(json.dumps(data), encoding="utf-8")

    def sample(self):
        self.put("events8k.json", {"generated_at": "2026-10-26T15:30:00Z", "rows": [
            {"accession": "000100-26-000001", "ticker": "NVDA", "form": "8-K",
             "filed": "2026-10-26", "accepted": "2026-10-26T15:00:00Z",
             "topics": ["restatement"], "headline": "Correction to previous financial statements",
             "quote": "Reported in official current report",
             "url": "https://www.sec.gov/Archives/edgar/data/100/000100-26-000001.txt"},
            {"accession": "000100-26-000001", "ticker": "NVDA", "form": "8-K",
             "filed": "2026-10-26", "accepted": "2026-10-26T15:00:00Z",
             "topics": ["restatement"], "headline": "Same accession — deduplicate",
             "url": "https://www.sec.gov/Archives/edgar/data/100/000100-26-000001.txt"},
            {"accession": "bad-filing", "ticker": "NVDA", "form": "8-K",
             "filed": "2026-10-26", "accepted": "2026-10-26T15:00:00Z",
             "topics": ["deal"], "url": "https://evil.test/fake"}]})
        self.put("watchlist.json", {"generated_at": "2026-10-26T15:30:00Z", "funds": [
            {"cik": "1067983", "name": "Berkshire Hathaway",
             "filed": "2026-10-26", "period": "2026-09-30",
             "new": [{"ticker": "AAPL"}],
             "source": "https://www.sec.gov/Archives/edgar/data/1067983/0001-index.html"}]})
        self.put("news.json", {"generated_at": "2026-10-26T15:30:00Z", "rows": [
            {"id": "abc", "kind": "release", "published": "2026-10-26T15:30",
             "title": "Company announces project", "tickers": ["MSFT"],
             "url": "https://www.prnewswire.com/news-releases/example.html",
             "source": "PR Newswire"},
            {"id": "xyz", "kind": "release", "published": "2026-10-26T15:30",
             "title": "Unmatched wire", "tickers": [],
             "url": "https://www.prnewswire.com/news-releases/example.html"}]})
        self.put("extremes.json", {
            "generated_at": "2026-10-26T15:35:00Z", "asof": "2026-10-26",
            "fields": ["ticker", "name", "close", "chg1d"],
            "rows": [["IREN", "Iren", 40.0, 0.105], ["OKLO", "Oklo", 30.0, -0.071],
                     ["CRWV", "CoreWeave", 90.0, 0.014],
                     ["SPY", "SPDR S&P 500 ETF", 684.0, 0.0082],
                     ["QQQ", "Nasdaq-100 ETF", 619.0, -0.005]]})

    def test_schema_and_exact_source(self):
        self.sample()
        d = F.build(self.path, self.NOW)
        self.assertEqual(d["schema"], 1)
        counts = {k: len([x for x in d["events"] if x["kind"] == k])
                  for k in ("8k", "13f", "news", "price")}
        self.assertEqual(counts, {"8k": 1, "13f": 1, "news": 1, "price": 2})
        self.assertTrue(all(x["event_at"] for x in d["events"]))
        k8 = next(x for x in d["events"] if x["kind"] == "8k")
        self.assertEqual(k8["priority"], "high")
        self.assertIn("000100-26-000001", k8["id"])
        self.assertTrue(k8["source_url"].startswith("https://www.sec.gov/Archives"))
        f13 = next(x for x in d["events"] if x["kind"] == "13f")
        self.assertEqual(f13["period_end"], "2026-09-30")
        self.assertEqual(f13["filed"], "2026-10-26")
        price = next(x for x in d["events"] if x["ticker"] == "IREN")
        self.assertEqual(price["change_pct"], 10.5)
        self.assertEqual(price["priority"], "medium")
        self.assertIn("NOT live", price["scope"])
        # Market-relative comparisons must come from the SAME published close date.
        self.assertEqual(d["benchmarks"]["SPY"]["asof"], "2026-10-26")
        self.assertAlmostEqual(d["benchmarks"]["SPY"]["change_pct"], 0.82)
        self.assertAlmostEqual(d["benchmarks"]["QQQ"]["change_pct"], -0.5)
        self.assertNotIn("IWM", d["benchmarks"])
        self.assertEqual(counts["price"], 2)  # SPY/QQQ are context, not alerts.

    def test_stale_and_unknown_are_not_live(self):
        self.sample()
        d = F.build(self.path, self.NOW + timedelta(days=15))
        self.assertEqual(d["events"], [])
        self.assertEqual(d["benchmarks"], {})
        self.assertEqual(F.iso if hasattr(F, "iso") else F.stamp("invalid"), "")

    def test_missing_source_returns_no_fake_data(self):
        self.assertEqual(F.build(self.path, self.NOW)["events"], [])
        self.assertEqual(F.build(self.path, self.NOW)["benchmarks"], {})

    def test_price_needs_verified_field_name(self):
        self.put("extremes.json", {"asof": "2026-10-26", "fields": ["ticker", "close"],
                                   "rows": [["NVDA", 250.00]]})
        self.assertEqual(F.build(self.path, self.NOW)["events"], [])


if __name__ == "__main__":
    unittest.main()
