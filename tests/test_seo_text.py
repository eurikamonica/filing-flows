"""The words of the static pages: a loss written as cents lost (not '−25¢ … lost'), a sliver of revenue making no margin,
a 13F manager's holders cased and its position changes with one sign."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seo  # noqa: E402
import seo_people as P  # noqa: E402


def company(rev, ni, om, segs=()):
    nodes = [{"id": f"S{i}", "name": n} for i, (n, _) in enumerate(segs)] + [{"id": "revenue", "name": "Revenue"}, {"id": "netloss" if ni < 0 else "net", "name": "Net"}]
    links = [{"s": f"S{i}", "t": "revenue", "v": v} for i, (_, v) in enumerate(segs)] + [{"s": "revenue", "t": "netloss" if ni < 0 else "net", "v": abs(ni)}]
    c = {"profile": {"cik": 9, "name": "LOSSY CORP", "tickers": ["LSY"], "sector": "tech", "industry": "Semiconductors"},
         "quarters": [{"label": "Q2 2026", "form": "10-Q", "filed": "2026-08-01", "headline": {"revenue": rev, "yoy": -3, "om": om, "ni": ni, "ocf": -1e7},
                       "nodes": nodes, "links": links}]}
    ix = {"cik": 9, "ticker": "LSY", "name": "LOSSY CORP", "sic": "3674", "revenue": rev, "yoy": -3, "om": om, "label": "Q2 2026"}
    return c, ix


def test_a_loss_in_cents_and_a_sliver_of_revenue():
    url, doc = seo.company_page(*company(1e8, -2.5e7, -30.0, [("Widgets Member", 6e7), ("Parts [Member]", 4e7)]), [], "Technology", "https://example.com")
    assert "<b>25¢</b> of every $1 of revenue lost" in doc and "-25¢" not in doc
    assert "operating margin <b>-30.0%</b>" in doc and "Widgets $60.0M, Parts $40.0M" in doc    # the lines' XBRL leftovers gone
    url, doc = seo.company_page(*company(50, -3e6, -5817056.8), [], "Technology", "https://example.com")
    assert "¢" not in doc and "5817056" not in doc and "n/m" in doc                         # $50 of revenue: no margin to speak of


def test_manager_holders_cased_and_changes_signed_once():
    m = {"name": "Example Capital", "slug": "example-capital", "cik": "1", "period": "2026-09-30", "filed": "2026-11-01", "positions": 3, "aum": 1e9,
         "holdings": [["AMZN", "AMAZON COM INC", 40.0, 4e8, "DECREASE", -31.3], ["GOOGL", "ALPHABET INC CL A", 35.0, 3.5e8, "DECREASE", -0.02],
                      ["NVDA", "NVIDIA CORP", 25.0, 2.5e8, "INCREASE", 5.5], ["NEW", "SOMETHING NEW INC", 0.0, 1, "NEW", None]],
         "adds": [["NVDA", "INCREASE", 5.5], ["NEW", "NEW", None]], "cuts": [["AMZN", "DECREASE", -31.3]],
         "clone": {"filings": 1, "first_filing": "2026-08-13", "coverage": 0.95, "monthly": []}, "record": {"scored": 1, "decisions": 1, "hit": 1.0}}
    url, doc = P.manager_page(m, "https://example.com")
    assert "<td>Amazon.com</td>" in doc and "<td>Alphabet Inc Class A</td>" in doc and "<td>NVIDIA</td>" in doc
    assert "<td>-31.3%</td>" in doc and "<td>+5.5%</td>" in doc and "<td>&lt;0.1%</td>" in doc and "<td>new</td>" in doc
    assert "decrease -" not in doc and "increase +" not in doc
    assert "1 filing since Aug 13, 2026" in doc and "Of 1 position change scored in 1 separate decision" in doc
