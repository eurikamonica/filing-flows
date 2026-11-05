"""pipeline/traps.py: the analysis-trap rules on small company files — each status, the normal explanations, the
priority list (one per overlap group), expiry; and the pages scripts/seo_traps.py writes."""
import datetime as dt
import json
import sys
from pathlib import Path

from pipeline import traps as T

TODAY = dt.date(2026, 11, 5)


def company(**kw):
    """a company file with two fiscal years and six quarters; keyword overrides"""
    fy = [{"end": "2024-12-31", "label": "FY2024", "ocf": 100e6, "wc": {"rev": 1e9}, "bridge": {"items": [["d_ar", -10e6], ["d_inv", -5e6]], "residual": 0}},
          {"end": "2025-12-31", "label": "FY2025", "ocf": 130e6, "wc": {"rev": 1.1e9}, "bridge": {"items": [["d_ar", 15e6], ["d_inv", 0]], "residual": 0}}]
    cap_fy = [{"end": "2024-12-31", "items": {"capex": -60e6}}, {"end": "2025-12-31", "items": {"capex": -20e6}}]
    shares = [{"end": "2024-12-31", "label": "FY2024", "sbc": 40e6, "bb": 0, "diluted": 100e6}, {"end": "2025-12-31", "label": "FY2025", "sbc": 60e6, "bb": 10e6, "diluted": 106e6}]
    qs = []
    for i, (end, rev, ar, dso) in enumerate([("2024-06-30", 250e6, 100e6, 36), ("2024-09-30", 260e6, 104e6, 36), ("2024-12-31", 270e6, 110e6, 37), ("2025-03-31", 275e6, 112e6, 37),
                                             ("2025-06-30", 280e6, 160e6, 52), ("2025-09-30", 290e6, 170e6, 53)]):
        qs.append({"end": end, "label": f"Q{i}", "wc": {"rev": rev, "ar_c": ar, "dso": dso}})
    val = {"cash_all": 50e6, "debt": 400e6, "b_ltd_c": 120e6, "end": "2025-09-30"}
    drivers = {"q": [{"end": "2025-09-30", "prev": "2024-09-30", "label": "Q3 2025", "prev_label": "Q3 2024", "cur": {"ni": 50e6}, "pri": {"ni": 50e6}, "dil0": 100e6, "dil1": 90e6,
                      "eps": {"eps0": 0.5, "eps1": 0.556}}]}
    c = {"profile": {"cik": 1, "name": "Alpha Inc", "sic": "3674"}, "quarters": [{"end": "2025-09-30", "label": "Q3 2025", "filed": "2025-11-01", "doc_url": "https://sec.gov/q3"}],
         "years": [{"end": "2025-12-31", "doc_url": "https://sec.gov/fy"}],
         "quality": {"fy": fy, "q": qs, "val": val, "drivers": drivers, "cap": {"fy": cap_fy, "shares": shares, "ttm": {"items": {"ocf": 10e6, "capex": -20e6}}, "maturities": None}}}
    c["quality"].update(kw)
    return c


def by_id(doc):
    return {f["rule_id"]: f for f in doc["findings"]}


def test_every_rule_triggers_on_the_demo_company_and_the_priority_keeps_one_per_group():
    er = {"nongaap": {"points": [{"quarter": "2025-03-31", "street": 1.0, "gaap": 0.8, "gap_pct": 0.25}, {"quarter": "2025-06-30", "street": 1.1, "gaap": 0.9, "gap_pct": 0.22},
                                 {"quarter": "2025-09-30", "street": 1.2, "gaap": 1.0, "gap_pct": 0.2}]}}
    d = T.evaluate(company(), er, TODAY)
    f = by_id(d)
    assert all(f[k]["status"] == "triggered" for k in ("A01", "A07", "B02", "B08", "C02", "D03")), {k: v["status"] for k, v in f.items()}
    a = f["A01"]
    assert a["observed"]["fcf_prior"] == 40e6 and a["observed"]["fcf_current"] == 110e6 and a["observed"]["capex_reduction"] == 40e6 and a["observed"]["wc_release"] == 30e6
    # the rulebook's worked example (§3.1): 40 → 110, +30 working capital, +40 capex, nothing else — the whole increase is temporary
    assert "100% of the increase came from sources that need not repeat" in a["explanation"] and "was unchanged" in a["explanation"]
    assert a["severity"] == "high" and a["alternative_explanations"] and a["missing_evidence"]
    assert f["A07"]["observed"]["sbc_pct_revenue"] == 0.0545 and "rose 6.0%" in f["A07"]["explanation"]
    assert f["B02"]["observed"]["receivables_yoy"] == 0.6346 and f["B02"]["severity"] == "high"
    assert f["C02"]["observed"]["due_12m"] == 120e6 and f["C02"]["observed"]["due_source"].startswith("the current portion") and "$70M short" in f["C02"]["explanation"]
    assert f["D03"]["observed"]["eps_growth_from_share_count"] is not None and "all of the EPS growth is the smaller denominator" in f["D03"]["explanation"]
    # one finding per overlap group in the priority list: A01 and B02 share cash_conversion, A07 and D03 share share_count
    assert d["priority"] == ["B02", "A07", "C02"] or d["priority"][0] in ("B02", "A01")
    assert len({f[k]["group"] for k in d["priority"]}) == len(d["priority"]) and d["summary"]["triggered"] == 6
    assert f["A01"]["evidence"][0]["url"] == "https://sec.gov/fy"


def test_clear_insufficient_not_applicable_and_expired():
    c = company()
    c["quality"]["cap"]["fy"][1]["items"]["capex"] = -60e6                      # no capex cut
    c["quality"]["fy"][1]["bridge"]["items"] = [["d_ar", -10e6], ["d_inv", -5e6]]     # no working-capital release
    c["quality"]["cap"]["shares"][1].update({"bb": 90e6, "diluted": 99e6})          # buybacks cover the SBC
    c["quality"]["val"].update({"cash_all": 500e6})
    f = by_id(T.evaluate(c, None, TODAY))
    assert f["A01"]["status"] == "clear" and f["A07"]["status"] == "clear" and f["C02"]["status"] == "clear" and f["C02"]["observed"]["cover_ratio"] == 4.17
    assert f["B08"]["status"] == "insufficient_data" and f["B08"]["severity"] is None
    bank = company(); bank["profile"]["sic"] = "6021"
    fb = by_id(T.evaluate(bank, None, TODAY))
    assert fb["A01"]["status"] == "not_applicable" and fb["B02"]["status"] == "not_applicable" and "financial" in fb["A01"]["reason"]
    old = company(); old["quarters"][0]["filed"] = "2024-01-15"
    fo = T.evaluate(old, None, TODAY)
    assert all(x["status"] == "expired" for x in fo["findings"] if x["rule_id"] != "B08") and fo["summary"]["expired"] == 5
    assert fo["findings"][0]["status_before_expiry"] == "triggered"
    # a loss: EPS growth has no meaning; no debt figure read: not "no debt"
    loss = company(); loss["quality"]["drivers"]["q"][0]["cur"]["ni"] = -5e6
    assert by_id(T.evaluate(loss, None, TODAY))["D03"]["status"] == "not_applicable"
    brk = company(); brk["quality"]["val"] = {"cash_all": 40e9, "debt": 0, "debt_how": "no debt tagged"}
    assert by_id(T.evaluate(brk, None, TODAY))["C02"]["status"] == "insufficient_data"
    # a review, not a pattern: one quarter of receivables outgrowing revenue
    one = company(); one["quality"]["q"][4]["wc"]["ar_c"] = 115e6
    assert by_id(T.evaluate(one, None, TODAY))["B02"]["status"] == "review"


def test_pages(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import seo_traps as S
    s = tmp_path
    (s / "data" / "c").mkdir(parents=True)
    (s / "data" / "c" / "1.json").write_text(json.dumps(company()))
    (s / "data" / "index.json").write_text(json.dumps({"companies": [{"cik": 1, "ticker": "AAA", "name": "ALPHA INC", "sector": "technology", "revenue": 1.1e9, "filed": "2025-11-01", "label": "Q3 2025"}]}))
    (s / "c" / "aaa").mkdir(parents=True)
    (s / "c" / "aaa" / "index.html").write_text('<html><main class="seo"><nav class="seo-toc" aria-label="On this page"><a href="#sankey">Sankey</a></nav><h1>x</h1></main></html>')
    (s / "robots.txt").write_text("User-agent: *\nAllow: /\nSitemap: https://x.test/sitemap.xml\n")
    n = S.write(str(s), "https://x.test", TODAY)
    assert n == 1
    doc = json.loads((s / "data" / "traps" / "1.json").read_text())
    assert doc["summary"]["triggered"] >= 4 and doc["rule_version"] == T.RULE_VERSION
    ix = json.loads((s / "data" / "traps" / "index.json").read_text())
    assert ix["rows"][0][0] == "AAA" and "A01" in ix["rows"][0][5]
    page = (s / "c" / "aaa" / "analysis-traps" / "index.html").read_text()
    assert "Alpha (AAA): analysis traps" in page and "What would explain it innocently" in page and "Triggered" in page and "noindex" not in page
    assert "Data: Q3 2025" in page and "Not investment advice" in page and "insufficient" in page.lower()
    main = (s / "c" / "aaa" / "index.html").read_text()
    assert 'href="analysis-traps/"' in main and "Before you read the chart" in main
    hub = (s / "disclosures" / "analysis-traps" / "index.html").read_text()
    assert "FCF growth = the business improved" in hub and "1 of 1" in hub
    assert "sitemap-traps.xml" in (s / "robots.txt").read_text() and "https://x.test/c/aaa/analysis-traps/" in (s / "sitemap-traps.xml").read_text()
