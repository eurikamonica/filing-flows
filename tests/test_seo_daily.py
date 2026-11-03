"""scripts/seo_daily.py: the daily lists from the hub's files, grouped by day, companies linked to their pages,
misread filings left out, an index, sitemap-daily.xml in robots.txt."""
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seo_daily as D  # noqa: E402

TODAY = dt.date(2026, 10, 30)


def w(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj))


def test_daily(tmp_path):
    s = tmp_path
    hub = s / "disclosures" / "data"
    w(s / "data" / "index.json", {"companies": [{"cik": 1, "ticker": "AAA", "name": "Alpha Inc"}]})
    (s / "c" / "aaa" / "who-owns").mkdir(parents=True)
    (s / "c" / "aaa" / "who-owns" / "index.html").write_text("x")
    w(hub / "market" / "insiders.json", {"latest": [
        {"code": "P", "ticker": "AAA", "issuer": "Alpha Inc", "insider": "Jane Doe", "role": "CEO", "date": "2026-10-29", "value": 2e6, "price": 20, "shares": 1e5},
        {"code": "P", "ticker": "BBB", "issuer": "Beta Inc", "insider": "Big Error", "role": "10% owner", "date": "2026-10-29", "value": 9.9e9},
        {"code": "P", "ticker": "AAA", "issuer": "Alpha Inc", "insider": "Old", "role": "CFO", "date": "2026-09-01", "value": 1e6},
        {"code": "S", "ticker": "AAA", "issuer": "Alpha Inc", "insider": "Seller", "role": "CFO", "date": "2026-10-28", "value": 5e5, "plan_10b5_1": True},
        {"code": "S", "ticker": "TXN", "issuer": "TEXAS INSTRUMENTS INC", "insider": "KIRK RONALD", "role": "Director", "date": "2026-10-28", "value": 1.9e6}]})
    w(hub / "market" / "stakes.json", {"latest": [
        {"form": "13D", "filed": "2026-10-29", "issuer": "BASSETT FURNITURE INDUSTRIES INC", "ticker": "BSET", "filer": "AUTO SERVICES COMPANY, INC.", "percent": 25.325, "purpose": "x"},
        {"form": "13D", "filed": "2026-10-29", "issuer": "Indaptus Therapeutics, Inc.", "ticker": "INDP", "person": "DAI JUNYI", "percent": 7.0, "purpose": "y"}]})
    w(hub / "market" / "events8k.json", {"rows": [{"ticker": "AAA", "filed": "2026-10-29", "guidance": "raised", "headline": "Alpha raises outlook", "url": "u"}]})
    made = D.write(str(s), "https://example.com", TODAY)
    assert made == ["insider-buying", "insider-selling", "guidance-changes", "activist-stakes"]
    buy = (s / "daily" / "insider-buying" / "index.html").read_text()
    assert "Jane Doe" in buy and "Big Error" not in buy and "Old" not in buy        # a misread filing and an old trade left out
    assert "href='../../c/aaa/who-owns/'" in buy
    sell = (s / "daily" / "insider-selling" / "index.html").read_text()
    assert "10b5-1 plan" in sell and "Texas Instruments Inc" in sell and "Kirk Ronald" in sell      # the filing's capitals cased
    assert "1 company updated its guidance" in (s / "daily" / "guidance-changes" / "index.html").read_text()
    st = (s / "daily" / "activist-stakes" / "index.html").read_text()
    assert "Auto Services Company, Inc. 25.32% of Bassett Furniture Industries Inc" in st and "Dai Junyi 7% of Indaptus" in st
    assert "25.325" not in st and "<td>Dai Junyi</td>" in st and "2 Schedule 13D filings" in st
    idx = (s / "daily" / "index.html").read_text()
    assert "Today in the filings: Oct 30, 2026" in idx and "href='insider-buying/'" in idx
    assert (s / "sitemap-daily.xml").read_text().count("<url>") == 5
    assert "sitemap-daily.xml" in (s / "robots.txt").read_text()
