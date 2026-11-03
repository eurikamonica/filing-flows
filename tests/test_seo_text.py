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
    m = {"name": "BNP PARIBAS FINANCIAL MARKETS", "slug": "example-capital", "cik": "1", "period": "2026-09-30", "filed": "2026-11-01", "positions": 3, "aum": 1e9,
         "holdings": [["AMZN", "AMAZON COM INC", 40.0, 4e8, "DECREASE", -31.3], ["GOOGL", "ALPHABET INC CL A", 35.0, 3.5e8, "DECREASE", -0.02],
                      ["NVDA", "NVIDIA CORP", 25.0, 2.5e8, "INCREASE", 5.5], ["NEW", "SOMETHING NEW INC", 0.0, 1, "NEW", None]],
         "adds": [["NVDA", "INCREASE", 5.5], ["NEW", "NEW", None]], "cuts": [["AMZN", "DECREASE", -31.3]],
         "clone": {"filings": 1, "first_filing": "2026-08-13", "coverage": 0.95, "monthly": []}, "record": {"scored": 1, "decisions": 1, "hit": 1.0}}
    url, doc = P.manager_page(m, "https://example.com")
    assert "<td>Amazon.com</td>" in doc and "<td>Alphabet Inc Class A</td>" in doc and "<td>NVIDIA</td>" in doc
    assert "<td>-31.3%</td>" in doc and "<td>+5.5%</td>" in doc and "<td>&lt;0.1%</td>" in doc and "<td>new</td>" in doc
    assert "decrease -" not in doc and "increase +" not in doc
    assert "1 filing since Aug 13, 2026" in doc and "Of 1 position change scored in 1 separate decision" in doc
    assert "<h1>BNP Paribas Financial Markets: 13F portfolio" in doc and "BNP Paribas Financial Markets' 13F for the quarter" in doc.replace('&#x27;', "'")   # the filer's capitals cased
    assert "3 common-share positions" in doc and "PARIBAS" not in doc


def test_revenue_river_keeps_one_breakdown_and_one_spelling():
    """The river of revenue lines merges 'MEDTECH' and 'MedTech' into one band (the latest spelling), and stops where
    an older quarter's lines are another partition of revenue (product/service against segments), so no band starts
    or stops mid-chart; the mix note names a line reported at both ends."""
    import seo_topics as T

    def q(label, lines):
        return {"label": label, "nodes": [{"id": f"S{i}", "name": n} for i, (n, _) in enumerate(lines)] + [{"id": "revenue", "name": "Revenue"}],
                "links": [{"s": f"S{i}", "t": "revenue", "v": v} for i, (_, v) in enumerate(lines)]}
    qs = [q("Q3 FY27", [("Innovative Medicine", 16.8), ("MedTech", 8.6)]), q("Q2 FY27", [("Innovative Medicine", 15.2), ("MEDTECH", 8.5)]),
          q("Q1 FY27", [("Innovative Medicine", 15.0), ("MEDTECH", 8.0)]), q("Q4 FY26", [("Innovative Medicine", 14.0), ("MEDTECH", 8.1)]),
          q("Q3 FY26", [("Net product sales", 20.0), ("Net service sales", 3.0)]), q("Q2 FY26", [("Net product sales", 19.0), ("Net service sales", 3.0)])]
    svg = T.segment_river("J&J", qs)
    assert "revenue by line, Q4 FY26 to Q3 FY27" in svg and "MEDTECH" not in svg and "MedTech" in svg
    assert "Net product sales" not in svg and "went from" in svg and "0% in" not in svg
    assert T.segment_river("J&J", qs[:2]) == ''                                 # fewer than three comparable quarters: no chart


def test_site_build_has_a_sector_index_and_growth_as_a_multiple(tmp_path):
    """scripts/seo.py on a stand-in data directory: sector/ lists the sectors (the address was a 404), a company that
    grew from a sliver shows 27× rather than +2627%, and a 13F-sized figure prints in trillions."""
    import json
    import seo as S
    data = tmp_path / "data"
    (data / "c").mkdir(parents=True)
    rows = [{"cik": 1, "ticker": "AAA", "name": "ALPHA INC", "sector": "tech", "sic": "7372", "revenue": 3.15e7, "yoy": 2627.0, "om": -30.0, "label": "Q2 2026", "filed": "2026-08-01"},
            {"cik": 2, "ticker": "BBB", "name": "BETA CORP", "sector": "health", "sic": "2834", "revenue": 2e9, "yoy": 5.0, "om": 20.0, "label": "Q2 2026", "filed": "2026-08-02"}]
    (data / "index.json").write_text(json.dumps({"companies": rows, "sector_names": {"tech": "Technology", "health": "Health care"}}))
    for r, ni in ((rows[0], -1e7), (rows[1], 3e8)):
        c, ix = company(r["revenue"], ni, r["om"])
        c["profile"].update({"cik": r["cik"], "name": r["name"], "tickers": [r["ticker"]], "sector": r["sector"]})
        c["quarters"][0]["headline"]["yoy"] = r["yoy"]
        (data / "c" / f"{r['cik']}.json").write_text(json.dumps(c))
    out = tmp_path / "site"
    S.write_pages(str(data), str(out), "https://example.com")
    sectors = (out / "sector" / "index.html").read_text()
    assert "<h1>Earnings by sector</h1>" in sectors and "href='tech/'" in sectors and "1 company" in sectors
    assert "Technology" in (out / "sector" / "tech" / "index.html").read_text()
    az = (out / "c" / "index.html").read_text()
    assert "27× Y/Y" in az and "+2627%" not in az and "+5% Y/Y" in az
    assert S.money(6.8977e12) == "$6.90T" and S.money(999e9) == "$999.0B"
    assert "https://example.com/sector/" in (out / "sitemap.xml").read_text()
