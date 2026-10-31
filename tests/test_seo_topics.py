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
    c = T.write(str(s), "https://example.com")
    assert c == {"stock-forecast": 1, "who-owns": 1, "guidance": 1, "takeover": 0, "risks": 0}
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
    assert sm.count("<url>") == 3 and "<lastmod>2026-10-20</lastmod>" in sm      # guidance dated by its release
    assert "Sitemap: https://example.com/sitemap-topics.xml" in (s / "robots.txt").read_text()
    assert not (s / "c" / "bbb").exists()                                          # nothing to say: no page
