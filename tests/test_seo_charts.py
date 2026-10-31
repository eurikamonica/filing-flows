"""scripts/seo_svg.py and seo_charts.py: charts drawn into the search pages (inline SVG) and the slots for the
interactive views."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seo  # noqa: E402
import seo_charts as SC  # noqa: E402
import seo_svg as SV  # noqa: E402


def test_svg_shapes():
    b = SV.bars([("Q1", 10e9), ("Q2", -2e9), ("Q3", 12e9)], seo.money, "Revenue")
    assert b.startswith("<figure") and "<svg" in b and "role='img'" in b and "$12.0B" in b and "−$2.0B" in b
    assert SV.bars([("Q1", 1)], seo.money, "x") == ""                                # one point: nothing drawn
    assert "Apple" in SV.hbars([("Apple", 5), ("Pear", 2)], str, "Fruit")
    assert SV.scatter([("A", 1, 2, 5), ("B", 3, 4, 9), ("C", -1, 0, 1), ("ME", 9, 9, 3)], "x", "y", "t", me="ME").count("ME (") == 1
    assert "guided range" in SV.ranges([("Q1", 1, 2, 1.5)], str, "g")


def test_company_charts_and_split():
    c = {"profile": {"name": "Acme"}, "quality": {
        "cap": {"ttm": {"label": "TTM", "items": {"ocf": 5e9, "capex": -1e9, "buyback": -3e9, "cash": -1e9}},
                "shares": [{"label": "FY22", "diluted": 1.0e9}, {"label": "FY23", "diluted": 0.98e9}, {"label": "FY24", "diluted": 9.7e9}],
                "maturities": {"fy": 2025, "label": "FY25", "at": "2025-12-31", "buckets": [[1, 1e9], [2, 2e9], [6, 5e9]], "cash": 3e9, "sti": 0, "ltd": 8e9}},
        "q": [{"label": f"Q{i}", "ni": 1e9 * i, "ocf": 1.2e9 * i} for i in range(1, 5)]}}
    rows = [{"cik": i, "ticker": f"T{i}", "sic": "3674", "yoy": i * 5, "om": i * 3, "revenue": 1e9 * i} for i in range(1, 6)]
    h = SC.static(c, {"cik": 3, "ticker": "T3", "sic": "3674", "industry": "Semis"}, rows, seo.money)
    for s in ("where the cash came from", "profit against cash", "diluted shares", "split-adjusted", "10-for-1 split before FY24",
              "debt falling due", "2026", "Later", "in its industry", "T3 ("):
        assert s in h, s
    live = SC.live(320193, "AAPL", "3571", "technology", [{"id": "ai", "name": "AI", "role": "buyer"}], {"chain-ai": "https://x/ai.jpg"})
    assert "data-kind='hub:rotation'" in live and "data-kind='flowlab'" in live and "https://x/ai.jpg" in live and "seo-embed.js" in live
