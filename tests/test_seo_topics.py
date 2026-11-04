"""scripts/seo_topics.py: a page per company and topic only when the data says something, answer-first lead, FAQPage
structured data, the company page linked to its topics, sitemap-topics.xml in robots.txt."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seo_topics as T  # noqa: E402


def w(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj))


def test_pages(tmp_path):
    s = tmp_path
    w(s / "data" / "index.json", {"companies": [{"cik": 1, "ticker": "AAA", "name": "ALPHA WIDGETS & CO", "filed": "2026-10-20", "revenue": 5e9},
                                                 {"cik": 2, "ticker": "BBB", "name": "Beta Inc", "filed": "2026-10-21", "revenue": 1e9}]})
    w(s / "c" / "aaa" / "index.html", "<html><main class='seo'><h1>x</h1></main></html>")
    hub = s / "disclosures" / "data"
    w(hub / "holders" / "AAA.json", {"institutional": [{"manager": "VANGUARD GROUP INC", "value_usd": 2e9, "shares": 1e7, "status": "INCREASE", "period": "2026-06-30"},
                                                       {"manager": "BlackRock, Inc.", "value_usd": 1.5e9, "shares": 8e6, "status": "DECREASE", "period": "2026-06-30"}],
                                     "officials": [{"person": "A Member", "transaction_type": "purchase", "date": "2026-10-01", "amount_min": 1001, "amount_max": 15000}],
                                     "guidance": {"label": "raised", "filed": "2026-10-20", "url": "u",
                                                  "items": [{"metric": "revenue", "name": "Revenue", "period": "FY2026", "unit": "usd", "lo": 1e10, "hi": 1.1e10}]}})
    w(hub / "research" / "valuation" / "c" / "1.json", {"price": 50, "football": [{"method": "DCF", "low": 40, "point": 60, "high": 80}], "dcf": {"value": 60}})
    w(hub / "consensus" / "c" / "1.json", {"analysts": {"targets": {"median": 70, "low": 55, "high": 90, "n": 12}, "rating": {"key": "buy"}}, "beat_rate": 0.75})
    w(s / "data" / "c" / "1.json", {"quarters": [{"label": "Q2 2026", "form": "10-Q", "filed": "2026-08-01", "headline": {"revenue": 1e9, "rev_fmt": "$1.0B", "yoy": 10},
        "nodes": [{"id": "A", "label": "Widgets"}, {"id": "B", "label": "Services"}, {"id": "revenue", "label": "Revenue"}, {"id": "net", "label": "Net earnings"}],
        "links": [{"s": "A", "t": "revenue", "v": 7e8, "q": 6e8, "y": 5e8}, {"s": "B", "t": "revenue", "v": 3e8, "q": 3e8, "y": 3e8},
                  {"s": "revenue", "t": "net", "v": 1e8, "q": 9e7, "y": 8e7}]}]})
    w(hub / "research" / "earnings" / "c" / "AAA.json", {"report_date": "2099-01-15", "quarter": "2098-12-31", "consensus": {"eps": 1.25, "rev": 1.1e9}, "model": {"p": 0.7}})
    c = T.write(str(s), "https://example.com")
    assert c == {"revenue": 1, "earnings-date": 1, "stock-forecast": 1, "who-owns": 1, "guidance": 1, "takeover": 0, "risks": 0}
    page = (s / "c" / "aaa" / "stock-forecast" / "index.html").read_text()
    assert "Alpha Widgets (AAA) trades at $50.00. 12 analysts&#x27; median price target is $70.00 (+40%)" in page
    ld = json.loads(re.search(r'application/ld\+json">(.*?)</script>', page).group(1))
    faq = next(g for g in ld["@graph"] if g["@type"] == "FAQPage")
    assert faq["mainEntity"][0]["name"] == "What is the price target for AAA stock?"
    assert "Did Alpha Widgets raise or lower its guidance?" in (s / "c" / "aaa" / "guidance" / "index.html").read_text()
    assert "Vanguard Group ($2.0B)" in (s / "c" / "aaa" / "who-owns" / "index.html").read_text()
    main = (s / "c" / "aaa" / "index.html").read_text()
    assert "More on AAA" in main and "href='who-owns/'" in main and "takeover/" not in main
    sm = (s / "sitemap-topics.xml").read_text()
    assert sm.count("<url>") == 5 and "<lastmod>2026-10-20</lastmod>" in sm      # guidance dated by its release
    rv = (s / "c" / "aaa" / "revenue" / "index.html").read_text()
    assert "Widgets brought in $700M (70%); Services brought in $300M (30%)" in rv and "10¢ was left as net earnings" in rv
    ed = (s / "c" / "aaa" / "earnings-date" / "index.html").read_text()
    assert "expected to report earnings on Jan 15, 2099" in ed and "Analysts expect EPS of $1.25 on revenue of $1.1B" in ed
    assert "Sitemap: https://example.com/sitemap-topics.xml" in (s / "robots.txt").read_text()
    assert not (s / "c" / "bbb").exists()                                          # nothing to say: no page


def test_topic_wording_and_pages_with_nothing_found():
    """A period named by its last day, one analyst, a range whose ends print the same, an EPA record with nothing on it
    (noindex, out of the sitemap), a reported quarter the site has not read yet (no stale revenue beside it)."""
    assert T.pword("Q@2026-12-27") == "the quarter ending Dec 27, 2026" and T.pword("Q4 2026") == "Q4 2026"
    assert T.grange({"lo": 1.9e9, "hi": 1.94e9, "unit": "usd"}) == "$1.9B"
    co = {"who_name": "Gentex", "ticker": "GNTX"}
    empty = T.risks(co, {"environment": {"facilities": 3, "in_violation": 0, "penalties_5y": 0}, "fedreg": {"count": 2}})
    found = T.risks(co, {"environment": {"facilities": 3, "in_violation": 1, "penalties_5y": 25000}})
    assert empty["noindex"] and not found["noindex"]
    import seo
    doc = seo.noindex(seo.page("T", "d", "https://x/", "<p>x</p>", 3, "https://x/og.png"))
    assert '<meta name="robots" content="noindex, follow">' in doc


def test_one_analyst_and_a_report_the_site_has_not_read():
    import datetime as dt
    p = T.forecast({"who_name": "Intrusion", "ticker": "INTZ"}, {"price": 0.57, "football": []},
                   {"analysts": {"targets": {"median": 9, "low": 9, "high": 9, "n": 1}}})
    assert "One analyst's price target is $9.00" in p["desc"] and "median" not in p["desc"] and "from $9.00 to $9.00" not in p["desc"]
    # reported Oct 28, 2026; the site's latest quarter is Q2 2025: no "Revenue was $15.4M for Q2 2025" beside the result
    er = {"report_date": "2027-01-27", "history": [{"reported": "2026-10-28", "act": 0.53, "est": 0.50, "surprise": 0.06}]}
    old = {"quarters": [{"label": "Q2 2025", "end": "2025-06-30", "headline": {"revenue": 15.4e6, "yoy": 22}}]}
    new = {"quarters": [{"label": "Q3 2026", "end": "2026-09-30", "headline": {"revenue": 16.1e6, "yoy": 9}}]}
    co = {"who_name": "John Marshall Bancorp", "ticker": "JMSB"}
    a = T.earnings_date(co, er, old, {}, today=dt.date(2026, 11, 4))
    b = T.earnings_date(co, er, new, {}, today=dt.date(2026, 11, 4))
    assert "Revenue was" not in a["desc"] and "Revenue" not in a["title"]
    assert "Revenue was $16.1M for Q3 2026" in b["desc"] and "Revenue $16.1M" in b["title"]

def _takeover_site(s):
    """two companies on the Buyouts data: a steady business the LBO model can run, and a loss-maker it cannot"""
    w(s / "data" / "index.json", {"companies": [{"cik": 1, "ticker": "AAA", "name": "Steady Widgets Inc", "filed": "2026-10-20", "revenue": 1e9},
                                                 {"cik": 2, "ticker": "BIO", "name": "Loss Biotherapeutics Inc", "filed": "2026-10-21", "revenue": 3e8}]})
    w(s / "data" / "c" / "2.json", {"quarters": [{"label": "Q2 2026", "headline": {"revenue": 9.93e7, "yoy": 46, "ni": -4.73e7}}]})
    lbo = s / "disclosures" / "data" / "research" / "lbo"
    rates = {"base": 4, "spread_b": 3.5, "as_of": "2026-10-15"}
    w(lbo / "c" / "1.json", {"cik": 1, "ticker": "AAA", "sector": "industrials", "kind": "industrial", "rates": rates, "rumors": [],
                             "inputs": {"revenue": 1e9, "ebitda": 2.5e8, "da": 4e7, "capex": 3e7, "tax_rate": 0.21, "g0": 0.03, "price": 10,
                                        "shares": 1e8, "debt": 3e8, "cash": 5e7, "claims": 0, "price_date": "2026-10-28"},
                             "history": {"acquired": {"p": 0.05, "decile": 7, "lift": 1.2}}})
    w(lbo / "c" / "2.json", {"cik": 2, "ticker": "BIO", "sector": "health", "kind": "industrial", "rates": rates, "rumors": [],
                             "inputs": {"revenue": 3.25e8, "ebitda": -2.88e8, "da": 1.35e7, "capex": 3.2e7, "price": 14.62, "shares": 4.53e8,
                                        "debt": 0, "cash": 2.98e8, "mcap": 6.62e9, "ev": 6.32e9, "g0": 0.345},
                             "history": {"acquired": {"p": 0.0417, "decile": 4, "lift": 0.83}}})
    w(lbo / "board.json", {"rates": rates, "fields": ["cik", "ticker", "irr", "max_price", "flags", "ev"],
                           "rows": [[1, "AAA", 0.25, 14.0, [], 1.25e9], [2, "BIO", None, None, ["no positive EBITDA to borrow against"], 6.32e9]]})
    w(lbo / "history.json", {"premiums": {"n": 1437, "median": 32.5, "p25": 20.0, "p75": 51.8,
                                          "by_sector": [["health", 15, 35.0, 22.0, 45.0], ["industrials", 8, 40.0, 15.0, 60.0]]}})


def test_takeover_pages(tmp_path):
    import shutil
    import pytest
    if not shutil.which("node"):
        pytest.skip("the LBO model runs in Node")
    _takeover_site(tmp_path)
    T.write(str(tmp_path), "https://example.com")
    a = (tmp_path / "c" / "aaa" / "takeover" / "index.html").read_text()
    assert "LBO price, odds and rumors" in a
    for h in ("The buyout, step by step", "years under the buyer", "The exit and the buyer's return", "Price against return", "The figures used"):
        assert h in a, h
    # the page's numbers are the model's own (disclosures/docs/lbo-model.js), not the board's stand-in figures
    import seo_lbo as L
    res, d = L.model_all({1: ({"revenue": 1e9, "ebitda": 2.5e8, "da": 4e7, "capex": 3e7, "tax_rate": 0.21, "g0": 0.03, "price": 10, "shares": 1e8,
                               "debt": 3e8, "cash": 5e7, "claims": 0}, {"base": 4, "spread_b": 3.5})})
    r = res[1]["run"]
    assert res[1]["ok"] and d["premium"] == 0.3
    assert f"would return about {r['irr'] * 100:.0f}% a year" in a and f"{r['irr'] * 100:.1f}%" in a
    assert f"is ${res[1]['max']['price']:,.2f} a share" in a                            # the most a buyer could pay for 20%
    assert "the limit that binds: 65% of the price" in a and "SOFR 4% plus the high-yield B spread 3.5% plus 0.5%" in a
    assert a.count("<td>Year ") == 5 and "Takeovers on record paid a median premium of 32.5%" in a     # industrials: under ten deals
    b = (tmp_path / "c" / "bio" / "takeover" / "index.html").read_text()
    assert "LBO price" not in b and "takeover analysis: odds, deal premiums and rumors" in b
    assert "A leveraged buyout does not work for Loss Biotherapeutics on its latest figures: it has no positive EBITDA to borrow against (−$288M" in b
    assert "Why a leveraged buyout does not fit" in b and "a strategic buyer" in b and "Biotherapeutics&#x27;s" not in b and "Loss Biotherapeutics&#x27; EBITDA" in b
    assert "Takeovers in its sector paid a median premium of 35%" in b and "$19.74" in b      # 14.62 × 1.35
    assert "Could private equity buy Loss Biotherapeutics?" in b
    assert "Loss Biotherapeutics, Q2 2026: revenue $99.3M (+46% year over year), net loss $47.3M." in b    # the Sankey's figure, in words


def test_takeover_without_node(tmp_path, monkeypatch):
    """no Node: the board's summary stands in, and a company the board could not model still gets its reason"""
    import seo_lbo as L
    monkeypatch.setattr(L, "model_all", lambda jobs, site=None, timeout=300: ({}, None))
    _takeover_site(tmp_path)
    T.write(str(tmp_path), "https://example.com")
    a = (tmp_path / "c" / "aaa" / "takeover" / "index.html").read_text()
    assert "would return about 25% a year" in a and "$14.00 a share" in a and "The buyout, step by step" not in a
    b = (tmp_path / "c" / "bio" / "takeover" / "index.html").read_text()
    assert "no positive EBITDA to borrow against" in b and "LBO price" not in b
