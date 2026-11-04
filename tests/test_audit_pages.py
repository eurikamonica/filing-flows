"""The page audit (scripts/audit_pages.py) on a small site."""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import audit_pages  # noqa: E402
import seo  # noqa: E402


def _q(label, form, R, lines, filed="2026-11-02", rev_fmt="$9.1B", checks=None):
    nodes = [{"id": "revenue", "name": "Revenue", "v": R}] + [{"id": f"L:{n}", "name": n, "v": v} for n, v in lines]
    links = [{"s": f"L:{n}", "t": "revenue", "v": v} for n, v in lines]
    return {"label": label, "form": form, "filed": filed, "nodes": nodes, "links": links, "checks": checks or [],
            "headline": {"rev_fmt": rev_fmt}}


def test_audit_finds_what_was_wrong_in_november(tmp_path):
    site = tmp_path / "_site"
    (site / "data" / "c").mkdir(parents=True)
    rows = [{"cik": 829224, "ticker": "SBUX", "name": "Starbucks Corp", "label": "Q4 FY26"},
            {"cik": 320193, "ticker": "AAPL", "name": "Apple Inc.", "label": "Q4 FY26"},
            {"cik": 1442145, "ticker": "VRSK", "name": "Verisk Analytics", "label": "Q2 2026"},
            {"cik": 1, "ticker": "GONE", "name": "Gone Inc", "label": "Q3 2026"}]
    json.dump({"companies": rows}, open(site / "data" / "index.json", "w"))
    sbux = {"quarters": [_q("Q4 FY26", "8-K", 9141.2e6, [("Company-operated coffeehouses", 7429.6e6), ("Licensed coffeehouses", 1196.1e6),
                                                         ("Other", 515.5e6), ("Net earnings per common share - diluted", 0.39e6)])]}
    aapl = {"quarters": [_q("Q4 FY26", "8-K", 114477e6, [("Europe", 32008e6), ("Greater China", 17539e6), ("Mac", 10792e6),
                                                          ("iPad", 6229e6), ("Services", 31573e6), ("Japan", 6540e6),
                                                          ("Rest of Asia Pacific", 9710e6)], rev_fmt="$114.5B")]}
    vrsk = {"quarters": [_q("Q2 2026", "8-K", 806.3e6, [("Underwriting", 569e6), ("Claims", 237e6)], filed="2026-07-29", rev_fmt="$806.3M")]}
    for cik, c in ((829224, sbux), (320193, aapl), (1442145, vrsk)):
        json.dump(c, open(site / "data" / "c" / f"{cik}.json", "w"))
    for r, text in ((rows[0], "Starbucks made $9.1B"), (rows[1], "Apple made $114.5B"), (rows[2], "Verisk made $790.0M")):
        d = site / "c" / seo.slug_for(r)
        d.mkdir(parents=True)
        (d / "index.html").write_text(f"<html><title>{text}</title></html>")
    rep = audit_pages.audit(str(site), today=dt.date(2026, 11, 2))
    got = {(x["ticker"], x["check"]) for x in rep["items"]}
    assert ("SBUX", "label") in got and ("AAPL", "mixed") in got          # off by 0.075%: the sum check does not see it
    assert ("VRSK", "old8k") in got and ("VRSK", "page") in got and ("GONE", "data") in got
    assert ("SBUX", "page") not in got and ("AAPL", "page") not in got
    audit_pages.main(["--site", str(site)])
    assert json.load(open(site / "data" / "page-audit.json"))["companies"] == 4
