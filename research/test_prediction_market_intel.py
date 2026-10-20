import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prediction_market_intel import normalize,cross_venue_comparison,binary_event_impact,brier_score

class MarketIntelTests(unittest.TestCase):
    def test_no_unreviewed_arbitrage(self):
        a={"source":"polymarket","price_implied_probability":.65,"reviewed_event_key":"A"}
        b={"source":"kalshi","price_implied_probability":.41,"reviewed_event_key":"A"}
        self.assertFalse(cross_venue_comparison(a,b)["comparable"])
        a["settlement_verified"]=b["settlement_verified"]=True
        self.assertTrue(cross_venue_comparison(a,b)["comparable"])
    def test_normalization_preserves_unknowns(self):
        r=normalize({"source":"kalshi","title":"Stock target","p":None,"volume":None})
        self.assertIsNone(r["price_implied_probability"])
        self.assertIsNone(r["volume_reported"])
        self.assertEqual(r["mapping_quality"],"unverified")
    def test_binary_scenario_not_double_counted(self):
        r=binary_event_impact(.3,100,130,90)
        self.assertAlmostEqual(r["weighted_revenue_usd"],102)
    def test_no_future_quotes_in_backtest(self):
        rows=[{"price_implied_probability":.7,"resolved_yes":True,"quote_time":"2026-01-01","resolved_at":"2026-01-02"},
              {"price_implied_probability":.99,"resolved_yes":True,"quote_time":"2026-01-04","resolved_at":"2026-01-02"}]
        r=brier_score(rows)
        self.assertEqual(r["n"],1)
        self.assertAlmostEqual(r["brier"],.09)

if __name__=="__main__":unittest.main()
