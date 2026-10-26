"""No-date-fabrication regressions for the independent Actual Weights pipeline."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import actual_weights as A


class ActualWeightsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "etf"
        self.pub = self.root / "public"
        (self.pub / "e").mkdir(parents=True)
        self.doc = {"symbol": "DIA", "name": "SPDR Dow Jones ETF",
                    "holdings": {"date": "2026-10-23", "source": "sponsor holdings file",
                                 "sector_map": {"GS": "Financials", "MSFT": "Information Technology"}},
                    "weights": [["GS", 0.12, 123], ["MSFT", 0.19, 456]]}
        self.write()

    def write(self):
        (self.pub / "e" / "DIA.json").write_text(json.dumps(self.doc), encoding="utf-8")

    def test_real_dates_and_no_fake_backfill(self):
        status = A.capture(self.root, self.pub, [{"symbol": "DIA", "aum": 10}])
        self.assertEqual(status["published"], 1)
        output = json.loads((self.pub / "weights" / "DIA.json").read_text())
        self.assertEqual([s["date"] for s in output["snapshots"]], ["2026-10-23"])
        self.assertEqual(output["snapshots"][0]["sectors"]["MSFT"], "Information Technology")
        self.assertAlmostEqual(output["snapshots"][0]["equity_weight_covered"], 0.31)
        A.capture(self.root, self.pub, [{"symbol": "DIA", "aum": 10}])
        self.assertEqual(len(json.loads((self.pub / "weights" / "DIA.json").read_text())["snapshots"]), 1)
        self.doc["holdings"]["date"] = "2026-11-01"
        self.doc["weights"][0][1] = 0.13
        self.write()
        A.capture(self.root, self.pub, [{"symbol": "DIA", "aum": 10}])
        actual = json.loads((self.pub / "weights" / "DIA.json").read_text())["snapshots"]
        self.assertEqual([s["date"] for s in actual], ["2026-10-23", "2026-11-01"])
        self.assertAlmostEqual(actual[0]["positions"][1][1], 0.12)

    def test_unknown_date_basis_is_not_treated_as_reported(self):
        doc = dict(self.doc)
        doc["holdings"] = {"date": "2026-10-23", "source": "sponsor holdings file"}
        snap = A.take_snapshot(doc)
        self.assertEqual(snap["date_basis"], "unknown")
        doc["holdings"]["date_basis"] = "reported"
        self.assertEqual(A.take_snapshot(doc)["date_basis"], "reported")
        doc["holdings"]["date_basis"] = "observed"
        self.assertEqual(A.take_snapshot(doc)["date_basis"], "observed")

    def test_bad_date_is_rejected(self):
        self.doc["holdings"]["date"] = "2026-02-30"
        self.assertIsNone(A.take_snapshot(self.doc))

    def test_no_wrong_normalization(self):
        positions = A.compact_positions([["MSFT", .19], ["GS", .12], ["UNKNOWN!", 1.0]])
        self.assertAlmostEqual(sum(w for _, w in positions), 0.31)
        self.assertEqual(len(positions), 2)


if __name__ == "__main__":
    unittest.main()
