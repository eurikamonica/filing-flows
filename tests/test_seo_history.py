"""scripts/seo_history.py on a stand-in site: a page for every quarter, Q/Q and Y/Y pages for the newest, one figure quarter
by quarter (margins, cash flow, the largest revenue lines), the guidance record against what was reported, the History
block on the company page and the sitemaps."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seo_history as SH  # noqa: E402


def w(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj))


def quarter(label, filed, rev, dc, gp, oi, net, k):
    """revenue, its two lines, gross and operating profit, net earnings; q = the quarter before, y = a year earlier (×k)"""
    def n(i, name, v):
        return {"id": i, "name": name, "v": v, "q": v / 1.1, "y": v / k}
    nodes = [n("G:x:DataCenterMember", "Data Center", dc), n("L:x:GamingMember", "Gaming", rev - dc), n("revenue", "Revenue", rev),
             n("gp", "Gross profit", gp), n("oi", "Operating profit", oi), n("net", "Net earnings", net), n("I:rd", "Research &amp; development", rev * .1)]
    links = [{"s": "G:x:DataCenterMember", "t": "revenue", "v": dc}, {"s": "L:x:GamingMember", "t": "revenue", "v": rev - dc},
             {"s": "revenue", "t": "gp", "v": gp}, {"s": "gp", "t": "oi", "v": oi}, {"s": "oi", "t": "net", "v": net}]
    return {"label": label, "form": "10-Q", "filed": filed, "doc_url": "https://www.sec.gov/x", "nodes": nodes, "links": links,
            "analysis": ["Data Center drove the quarter."]}


def site(tmp):
    w(tmp / "data" / "index.json", {"companies": [{"cik": 1, "ticker": "NVDA", "name": "NVIDIA CORP", "filed": "2026-08-26"}]})
    qs = [quarter("Q2 FY27", "2026-08-26", 9.62e10, 8.9e10, 7.2e10, 6.37e10, 5.97e10, 2.06),
          quarter("Q1 FY27", "2026-05-27", 8.16e10, 7.5e10, 6.1e10, 5.3e10, 4.9e10, 1.9),
          quarter("Q4 FY26", "2026-02-25", 7.0e10, 6.2e10, 5.2e10, 4.5e10, 4.2e10, 1.8),
          quarter("Q3 FY26", "2025-11-19", 6.0e10, 5.3e10, 4.4e10, 3.8e10, 3.5e10, 1.7)]
    w(tmp / "data" / "c" / "1.json", {"quarters": qs})
    w(tmp / "data" / "guidance-record" / "1.json", {
        "releases": 6, "since": "2025-02-26", "latest": "2026-08-26", "said": {"raised": 3, "lowered": 1},
        "metrics": [{"name": "Revenue", "metric": "revenue", "basis": "gaap", "unit": "usd",
                     "hits": {"n": 2, "hitOrBeat": 2, "above": 2, "within": 0, "met": 0, "below": 0, "avgVsMid": 4.2},
                     "rows": [{"label": "Q3 FY27", "pending": True, "actual": None, "outcome": None, "vsMid": None,
                               "guides": [{"filed": "2026-08-26", "lo": 1.04e11, "hi": 1.08e11, "change": "first"}]},
                              {"label": "Q2 FY27", "actual": 9.62e10, "outcome": "above", "vsMid": 3.4,
                               "guides": [{"filed": "2026-05-27", "lo": 9.1e10, "hi": 9.5e10}]}]}]})
    w(tmp / "c" / "nvda" / "index.html", '<html lang="en"><body><main class="seo">x</main></body></html>')
    return tmp


def test_history(tmp_path):
    s = site(tmp_path)
    n = SH.write(str(s), "https://example.com")
    assert n == {"quarters": 4, "qoq": 2, "yoy": 2, "metrics": 6, "guidance": 1}
    q = (s / "c" / "nvda" / "q2-fy27" / "index.html").read_text()
    assert "<h1>NVIDIA (NVDA) second quarter fiscal 2027 results (Q2 FY27)</h1>" in q
    assert "reported revenue of $96.2B for the second quarter fiscal 2027 (Q2 FY27), +106% from a year earlier and +10% from the quarter before" in q
    assert '"text": "NVIDIA (NVDA) reported revenue of $96.2B' in q and "data-label='Q2 FY27'" in q and "seo-quarter.js" in q
    assert "q2-fy27-vs-q1-fy27/" in q and "q2-fy27-vs-q2-fy26/" in q and "../q1-fy27/" in q
    qoq = (s / "c" / "nvda" / "q2-fy27-vs-q1-fy27" / "index.html").read_text()
    assert "NVIDIA&#x27;s revenue rose $8.7B (+10%) from $87.5B in Q1 FY27" in qoq or "NVIDIA's revenue rose" in qoq
    assert "The biggest changes: Data Center +$8.1B (+10%)" in qoq.replace("&#x27;", "'")
    yoy = (s / "c" / "nvda" / "q2-fy27-vs-q2-fy26" / "index.html").read_text()
    assert "year over year" in yoy and "Q2 FY26" in yoy
    gm = (s / "c" / "nvda" / "gross-margin" / "index.html").read_text()
    assert "gross margin was 74.8% in Q2 FY27" in gm.replace("&#x27;", "'") and "Over the last 4 quarters" in gm
    assert (s / "c" / "nvda" / "data-center-revenue" / "index.html").exists() and (s / "c" / "nvda" / "research-and-development" / "index.html").exists()
    gh = (s / "c" / "nvda" / "guidance-history" / "index.html").read_text().replace("&#x27;", "'")
    assert "met or beat its own guidance 2 times (100%)" in gh and "raised guidance 3 times and lowered it 1 times" in gh
    assert "$91.0B–$95.0B (May 27, 2026)" in gh and "above the range" in gh and "+3.4%" in gh and "to be reported" in gh
    main = (s / "c" / "nvda" / "index.html").read_text()
    assert 'class="seo-history"' in main and "q3-fy26/" in main and "guidance-history/" in main
    SH.write(str(s), "https://example.com")                                           # once only
    assert (s / "c" / "nvda" / "index.html").read_text().count('class="seo-history"') == 1
    sm = (s / "sitemap-quarters.xml").read_text()
    assert len(re.findall("<url>", sm)) == 4 and "<lastmod>2026-08-26</lastmod>" in sm
    assert len(re.findall("<url>", (s / "sitemap-periods.xml").read_text())) == 4
    robots = (s / "robots.txt").read_text()
    assert all(f"sitemap-{k}.xml" in robots for k in ("quarters", "periods", "metrics"))


def test_year_ago_and_slug():
    assert SH.year_ago("Q2 FY27") == "Q2 FY26" and SH.year_ago("Q3 2026") == "Q3 2025" and SH.year_ago("FY2026") is None
    assert SH.qslug("Q2 FY27") == "q2-fy27"
