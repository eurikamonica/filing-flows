"""scripts/seo_home.py: the home page's plain HTML lists this week's reports and the next reports, linked to pages
that exist; scripts/seo.py: the embed box and the named customers and suppliers on a company page."""
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seo  # noqa: E402
import seo_home as H  # noqa: E402


def w(p, s):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s if isinstance(s, str) else json.dumps(s))


def test_home_block(tmp_path):
    s = tmp_path
    w(s / "index.html", '<main id="app"><div class="loading">Loading…</div></main>')
    w(s / "data" / "index.json", {"companies": [{"cik": 1, "ticker": "AAA", "name": "ALPHA INC", "label": "Q3 2026", "filed": "2026-10-29", "rev": "$1.0B", "yoy": 10.0},
                                                {"cik": 2, "ticker": "BBB", "name": "BETA INC", "label": "Q2 2026", "filed": "2026-08-01"}]})
    for p in ("c/aaa", "c/bbb", "c/bbb/earnings-date", "events"):
        w(s / p / "index.html", "x")
    w(s / "disclosures" / "data" / "research" / "earnings" / "index.json", {"fields": ["ticker", "name", "report_date"], "rows": [["BBB", "BETA INC", "2026-11-03"]]})
    assert H.write(str(s), dt.date(2026, 10, 31))
    t = (s / "index.html").read_text()
    assert "href='c/aaa/'" in t and "Alpha (AAA) Q3 2026 earnings" in t and "href='c/bbb/'" not in t       # BBB did not report this week
    assert "href='c/bbb/earnings-date/'" in t and "href='events/'" in t and "href='gamma/'" not in t          # only pages that exist
    assert not H.write(str(s))                                                                                # written once


def test_ties_and_embed():
    ties = [{"supplier": "AAA", "supplier_cik": 1, "customer": "BBB", "customer_cik": 2, "share": 0.2, "evidence_level": "Stated in 10-K", "source_url": "https://sec.gov/x"}]
    s = seo.ties_section(ties, 1, {2: "bbb"})
    assert "Sells to" in s and "href='../bbb/'" in s and "20% of its revenue" in s
    assert "Buys from" in seo.ties_section(ties, 2, {1: "aaa"})
    b = seo.embed_box("https://x.com/c/aaa/", "https://img/a.jpg", "Alpha Sankey", "Alpha Q3")
    assert "&lt;a href=&quot;https://x.com/c/aaa/&quot;&gt;&lt;img" in b and "c/aaa/embed/" in b


def test_llms_txt_and_the_follow_box(tmp_path):
    """/llms.txt for AI assistants: what the site is, how to cite it, the X account, this week's reports; every static page
    ends with the X account and a citation line (in the page's language on the translated pages)."""
    s = tmp_path
    w(s / "data" / "index.json", {"companies": [{"cik": 1045810, "ticker": "NVDA", "name": "NVIDIA CORP", "label": "Q3 FY27", "filed": "2026-11-01", "rev": "$100B", "yoy": 50.0}]})
    for p in ("c/nvda", "c", "about"):
        w(s / p / "index.html", "x")
    assert H.llms(str(s), "https://filing-flows.com", dt.date(2026, 11, 4)) > 10
    t = (s / "llms.txt").read_text()
    assert t.startswith("# Filing Flows") and "https://x.com/FilingFlows" in t and "Cite a figure as: Filing Flows (https://filing-flows.com/c/<ticker>/)" in t
    assert "[NVIDIA (NVDA) Q3 FY27 earnings](https://filing-flows.com/c/nvda/)" in t and "https://filing-flows.com/about/" in t and "/zh/" not in t
    doc = seo.page("NVIDIA (NVDA) Earnings | Filing Flows", "d", "https://filing-flows.com/c/nvda/", "<p>x</p>", 2, "https://x/og.png")
    assert "Follow @FilingFlows" in doc and "Cite this page: Filing Flows, “NVIDIA (NVDA) Earnings”, <a href=\"https://filing-flows.com/c/nvda/\">" in doc
    assert "关注 @FilingFlows" in seo.localize(doc, "zh-Hans") and "Cite this page" not in seo.localize(doc, "fr")
