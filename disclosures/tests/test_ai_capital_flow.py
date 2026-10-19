import sys
import unittest
from pathlib import Path

# The module is run from the repository root (python -m disclosures.app.ai_capital_flow: it uses pipeline/); the Hub's
# own checks run "unittest discover" inside disclosures/, so the root goes on the path here.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
try:
    from disclosures.app.ai_capital_flow import build, projection, validate, CATEGORY, VENDOR
except ImportError as exc:                       # a checkout without pipeline/: ai-capital-flow.yml runs these tests
    raise unittest.SkipTest(f"ai_capital_flow not importable here ({exc})")

class TestAICapex(unittest.TestCase):
    def test_weights(self):
        validate()
        self.assertAlmostEqual(sum(CATEGORY.values()), 1)
        for row in VENDOR.values():
            self.assertAlmostEqual(sum(row.values()), 1)
    def test_bounded_growth(self):
        hist=[{"fiscal_year": 2024,"cash_capex_usd": 100},{"fiscal_year": 2025,"cash_capex_usd": 200}]
        self.assertAlmostEqual(projection(hist, 2027)["value_usd"], 392)
    def test_missing_does_not_create_facts(self):
        doc=build({"MSFT":[{"fiscal_year":2025,"cash_capex_usd": 100}]},2027)
        self.assertEqual(doc["total_capex_usd"],100)
        self.assertIsNone(next(x for x in doc["companies"] if x["ticker"]=="META")["prediction"])
        for layer in ("buyer:", "category:"):
            self.assertAlmostEqual(sum(x["value_usd"] for x in doc["links"] if x["source"].startswith(layer)),100)
    def test_attribution_not_reported(self):
        doc=build({"GOOGL":[{"fiscal_year":2025,"cash_capex_usd": 50}]})
        self.assertTrue(all(x["status"]=="illustrative_attribution" for x in doc["links"] if x["source"].startswith("category:")))

if __name__ == "__main__":
    unittest.main()
