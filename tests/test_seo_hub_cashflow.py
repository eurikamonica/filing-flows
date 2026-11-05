"""scripts/seo_hub.py (crawlable hub views and 8-K event pages, the event archive kept in the store) and
scripts/seo_cashflow.py (cash-flow page per company, capital spending & supply chain per industry)."""
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seo_cashflow as CF  # noqa: E402
import seo_hub as HB  # noqa: E402


def w(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj) if not isinstance(obj, str) else obj)


def test_hub_views_and_events(tmp_path):
    s, store = tmp_path / "site", tmp_path / "store"
    m = s / "disclosures" / "data" / "market"
    w(s / "data" / "index.json", {"companies": [{"cik": 1, "ticker": "AAA", "name": "ALPHA INC", "label": "Q3 2026", "rev": "$1.0B", "yoy": 12.0, "om": 20.0}]})
    w(s / "c" / "aaa" / "index.html", "x")
    w(s / "disclosures" / "index.html", "<html><body>hub</body></html>")
    w(m / "insiders.json", {"since": "2026-08-01", "summary": [
        {"ticker": t, "issuer": f"{t} Inc", "cik": str(i), "buys": 3, "buy_value": 1e6 * (i + 1), "sells": 1, "sell_value": 1e5, "buyers": ["A", "B", "C"], "buyers30": 3,
         "last": "2026-10-30", "cluster": True} for i, t in enumerate(["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"])]})
    ev = lambda acc, cik, co, items, topics, filed: {"accession": acc, "url": "https://www.sec.gov/x", "form": "8-K", "filed": filed, "cik": str(cik), "company": co,
                                                     "items": items, "code": items[0], "topics": topics, "headline": f"{co} news", "quote": "The Company entered into an agreement.", "ticker": "AAA" if cik == 1 else ""}
    w(m / "events8k.json", {"on_file": 3, "days": 30, "counts": {"deal": 1, "earnings": 1}, "rows": [
        ev("0001-26-000001", 1, "ALPHA INC", ["1.01", "9.01"], ["deal"], "2026-10-29"),
        ev("0002-26-000002", 2, "BETA CORP", ["2.02"], ["earnings"], "2026-10-29")]})          # results only: no event page
    pages, n = HB.write(str(s), "https://example.com", str(store), dt.date(2026, 10, 30))
    assert pages == ["insider-trades", "8-k-events"] and n == 1
    ins = (s / "disclosures" / "insider-trades" / "index.html").read_text()
    assert "href='../../c/aaa/'" in ins and "href='../#insiders'" in ins and "<link rel=\"canonical\" href=\"https://example.com/disclosures/insider-trades/\">" in ins
    page = next((s / "events").glob("aaa-deal-2026-10-29-*/index.html")).read_text()
    assert "Entry into a material definitive agreement" in page and "The Company entered into an agreement." in page and "NewsArticle" in page
    assert 'href="insider-trades/"' in (s / "disclosures" / "index.html").read_text()            # the hub links to its snapshots
    # the archive keeps the event after the hub's window has moved on
    w(m / "events8k.json", {"rows": []})
    pages, n = HB.write(str(s), "https://example.com", str(store), dt.date(2026, 11, 30))
    assert n == 1 and "8-k-events" not in pages
    sm = (s / "sitemap-hub.xml").read_text()
    assert "https://example.com/events/" in sm and "sitemap-hub.xml" in (s / "robots.txt").read_text()


def test_cash_flow_and_supply_chain(tmp_path):
    s = tmp_path
    qs = [{"end": f"2026-0{i}-30", "label": f"Q{i} 2026", "kind": "q", "items": {"ocf": 100.0e6 * i, "capex": -40e6, "buyback": -10e6}} for i in range(1, 5)]
    cos = [{"cik": c, "ticker": t, "name": n, "label": "Q4 2026", "filed": "2026-10-30", "sic": "3674"} for c, t, n in ((1, "AAA", "ALPHA INC"), (2, "BBB", "BETA INC"))]
    w(s / "data" / "index.json", {"companies": cos})
    for c in cos:
        w(s / "c" / c["ticker"].lower() / "index.html", '<nav class="seo-toc" aria-label="On this page"><a href="#sankey">Sankey</a></nav>')
        w(s / "data" / "c" / f"{c['cik']}.json", {"profile": {"name": c["name"]}, "quality": {
            "cap": {"q": qs, "ttm": {"end": "2026-04-30", "label": "TTM to Q4 2026", "items": {"ocf": 1e9, "capex": -1.6e8 * c["cik"], "div": -1e8}}},
            "q": [{"label": "Q4 2026", "ni": 300e6, "ocf": 400e6, "bridge": {"start": 300e6, "items": [["da", 120e6], ["d_ar", -20e6]]},
                   "wc": {"dso": 40, "dio": 30, "dpo": 50, "ccc": 20, "has_inv": True}}]}})
    w(s / "data" / "gamma" / "index.json", {"generated": "2026-10-30", "industries": [{"sic": "3674", "name": "Semiconductors"}]})
    w(s / "data" / "gamma" / "3674.json", {"companies": [{"cik": 1, "ticker": "AAA", "name": "ALPHA INC"}, {"cik": 2, "ticker": "BBB", "name": "BETA INC"}],
                                           "relationships": [{"supplier": "AAA", "customer": "BBB", "share": 0.2, "evidence_level": "Stated in 10-K"}]})
    w(s / "data" / "gamma" / "flowlab" / "3674.json", {"revenue": 1e10, "views": {
        "capex": {"nodes": [["cx", 0, "Capital spending"], ["a:equipment", 1, "Equipment"], ["s:333", 2, "Machinery makers"]],
                  "links": [["cx", "a:equipment", 4e8, "C"], ["a:equipment", "s:333", 3e8, "C"]], "meta": {"classes": {"equipment": 4e8, "structures": 1e8}}}}})
    w(s / "gamma" / "3674" / "index.html", "<h2>Companies</h2>")
    assert CF.write(str(s), "https://example.com") == 3              # two companies, one industry
    p = (s / "c" / "aaa" / "cash-flow" / "index.html").read_text()
    assert "free cash flow of $360M" in p and "Q1 2026" in p and "Depreciation &amp; amortization" in p
    assert 'href="cash-flow/"' in (s / "c" / "aaa" / "index.html").read_text()
    sc = (s / "gamma" / "3674" / "supply-chain" / "index.html").read_text()
    assert "spent $480M on capital projects" in sc and "Machinery makers" in sc and "href='../../../c/bbb/cash-flow/'" in sc
    assert "href='supply-chain/'" in (s / "gamma" / "3674" / "index.html").read_text()
    assert (s / "sitemap-cashflow.xml").read_text().count("<url>") == 3


def test_two_8ks_of_a_day_with_the_same_headline_get_titles_of_their_own(tmp_path):
    """Carlyle Credit Solutions filed two 8-Ks on Nov 4, 2026 for the same acquisition, with the same headline: the link
    audit found two pages with one title. The second part of the title is then the filing's items and accession."""
    import re as _re
    import seo_hub as H

    class L:
        def row(self, ticker, cik):
            return {"cik": cik, "ticker": "CGBD", "name": "Carlyle Credit Solutions", "revenue": 1e8}
    evs = [{"cik": 1544206, "ticker": "CGBD", "company": "Carlyle Credit Solutions", "filed": "2026-11-04", "code": "2.01",
            "items": ["2.01", "9.01"], "topics": ["acquisition"], "headline": "Completion of the merger with the fund",
            "accession": acc, "url": "https://www.sec.gov/x"} for acc in ("0001193125-26-111111", "0001193125-26-222222")]
    H.event_pages(str(tmp_path), "https://filing-flows.com", L(), evs)
    titles = []
    for d in (tmp_path / "events").iterdir():
        p = d / "index.html"
        if d.is_dir() and p.exists():
            titles.append(_re.search(r"<title>(.*?)</title>", p.read_text(encoding="utf-8"), _re.S).group(1))
    assert len(titles) == 2 and len(set(titles)) == 2, titles


def test_two_8ks_of_a_day_whose_titles_fall_back_to_the_same_item_get_titles_of_their_own(tmp_path):
    """The real Carlyle Credit Solutions pair of Nov 4, 2026: one 8-K about the shareholder vote (topic "vote", item 2.01
    as its main item), the other with no topic (item 2.01). Both titles read "completion of an acquisition or disposition
    of assets", but the same-day count was kept per topic ("vote" vs "2.01"), so neither was told apart."""
    import re as _re
    import seo_hub as H

    class L:
        def row(self, ticker, cik):
            return {"cik": cik, "ticker": "CGBD", "name": "Carlyle Credit Solutions", "revenue": 1e8}
    base = {"cik": 1544206, "ticker": "CGBD", "company": "Carlyle Credit Solutions", "filed": "2026-11-04", "code": "2.01",
            "headline": "", "quote": "The merger was completed.", "url": "https://www.sec.gov/x"}
    evs = [dict(base, items=["2.01", "3.03", "5.07", "9.01"], topics=["vote"], accession="0001193125-26-447310"),
           dict(base, items=["1.01", "2.01", "5.03", "9.01"], topics=[], accession="0001193125-26-447280")]
    H.event_pages(str(tmp_path), "https://filing-flows.com", L(), evs)
    titles = []
    for d in (tmp_path / "events").iterdir():
        p = d / "index.html"
        if d.is_dir() and p.exists():
            titles.append(_re.search(r"<title>(.*?)</title>", p.read_text(encoding="utf-8"), _re.S).group(1))
    assert len(titles) == 2 and len(set(titles)) == 2, titles
