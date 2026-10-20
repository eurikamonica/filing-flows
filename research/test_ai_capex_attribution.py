import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ai_capex_attribution import calculate

SAMPLE = {
    "demo_only": True, "buyer": "TestCo", "period": "2026Q4",
    "recognition_lags": {"-1": 0.2, "0": 0.5, "1": 0.3},
    "categories": {
        "compute": {"weight": 0.75, "suppliers": {"NVDA": 0.5, "AVGO": 0.3}},
        "network": {"weight": 0.25, "suppliers": {"ANET": 0.4}}
    },
    "scenarios": [{"name": "Base", "capex_usd": 1000}]
}

class CapexTest(unittest.TestCase):
    def test_terminal_allocation_and_timing(self):
        x = calculate(SAMPLE)["scenarios"][0]
        self.assertAlmostEqual(x["terminal_vendor_usd"]["NVDA"], 375)
        self.assertAlmostEqual(x["terminal_vendor_usd"]["AVGO"], 225)
        self.assertAlmostEqual(x["terminal_vendor_usd"]["ANET"], 100)
        self.assertAlmostEqual(sum(x["terminal_vendor_usd"].values()) +
                               sum(x["unallocated_by_category_usd"].values()), 1000)
        rows = [v for v in x["revenue_timing_estimate_usd"] if v["vendor"] == "NVDA"]
        self.assertEqual([r["period"] for r in rows], ["2026Q3", "2026Q4", "2027Q1"])
        self.assertAlmostEqual(sum(r["value_usd"] for r in rows), 375)

    def test_refuse_overallocation(self):
        bad = {**SAMPLE, "categories": {"over": {"weight": 1, "suppliers": {"A": .7, "B": .5}}}}
        with self.assertRaises(ValueError):
            calculate(bad)

    def test_refuse_unlabelled_projection(self):
        with self.assertRaises(ValueError):
            calculate({**SAMPLE, "demo_only": False})

if __name__ == "__main__":
    unittest.main()
