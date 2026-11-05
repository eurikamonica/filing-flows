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
    assert f["E02"]["status"] == "insufficient_data" and f["E07"]["status"] == "insufficient_data" and f["J06"]["status"] == "not_applicable" and f["J08"]["status"] == "not_applicable"
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
    assert all(x["status"] == "expired" for x in fo["findings"] if x["rule_id"] in ("A01", "A07", "B02", "C02", "D03")) and fo["summary"]["expired"] == 5
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
    # no cash-flow or earnings-quality page was written for AAA: the traps page does not link to them
    assert "../cash-flow/" not in page and "../earnings-quality/" not in page
    for sub in ("cash-flow", "earnings-quality"):
        (s / "c" / "aaa" / sub).mkdir()
        (s / "c" / "aaa" / sub / "index.html").write_text("<html></html>")
    S.write(str(s), "https://x.test", TODAY)
    linked = (s / "c" / "aaa" / "analysis-traps" / "index.html").read_text()
    assert "href='../cash-flow/'" in linked and "href='../earnings-quality/'" in linked
    main = (s / "c" / "aaa" / "index.html").read_text()
    assert 'href="analysis-traps/"' in main and "Before you read the chart" in main
    hub = (s / "disclosures" / "analysis-traps" / "index.html").read_text()
    assert "FCF growth = the business improved" in hub and "1 of 1" in hub
    pr = json.loads((s / "data" / "traps" / "practice.json").read_text())
    assert pr["items"] and {x["answer"] for x in pr["items"]} <= {"trap", "holds", "unknown"} and all(x["figures"] and x["claim"] for x in pr["items"])
    trap_item = next(x for x in pr["items"] if x["answer"] == "trap")
    assert trap_item["falsified_if"] and trap_item["url"] == f"https://x.test/c/aaa/analysis-traps/#{trap_item['rule']}"
    assert "What would show the trap does not apply" in page and "practice/" in hub
    pp = (s / "disclosures" / "analysis-traps" / "practice" / "index.html").read_text()
    cp = (s / "disclosures" / "analysis-traps" / "cases" / "index.html").read_text()
    assert "C32" in cp and "Comscore" in cp and "P19" in cp and "alleged" in cp and "cases/#C01" in hub and "<a href='../#A01'>" in cp
    from pipeline import trap_cases as TC
    assert len(TC.CASES) == 34 and len(TC.PAPERS) == 27 and all(c[3].startswith("https://") for c in TC.CASES) and all(r in T.NAMES for c in TC.CASES for r in c[8])
    assert "Does it follow?" in pp and "data/traps/practice.json" in pp and "https://x.test/disclosures/analysis-traps/practice/" in (s / "sitemap-traps.xml").read_text()
    assert "sitemap-traps.xml" in (s / "robots.txt").read_text() and "https://x.test/c/aaa/analysis-traps/" in (s / "sitemap-traps.xml").read_text()


def test_phase_two_rules():
    """E02 mid-cycle P/E, J06 a bank's cycle, E07 the DCF's range, J08 a REIT's payout"""
    def hist(vals):
        return {"periods": [[f"{2017 + i}-01-01", f"{2017 + i}-12-31", "fy", f"FY{2017 + i}"] for i in range(len(vals))], "v": {"ni": [[i, [[v, [0, "fy", [i]]]]] for i, v in enumerate(vals)]}}
    c = company(); c["quality"]["hist"] = hist([5e8, 4e8, -1e8, 6e8, 5e8, 5.5e8, 1.5e9, 1.6e9])     # the last two years are the peak
    val = {"inputs": {"mcap": 16e9, "ni": 1.6e9}, "price": 100, "generated_at": "2026-11-05", "dcf": {"value": 164.4, "tv_share": 0.72},
           "sensitivity": {"tornado": [{"input": "Revenue growth (each year)", "how": "±5 pts", "low": 134.4, "high": 200.0}, {"input": "WACC", "how": "±1 pt", "low": 143.9, "high": 191.5}]}, "range": [42.5, 444.4]}
    f = by_id(T.evaluate(c, None, TODAY, val))
    assert f["E02"]["status"] == "triggered" and f["E02"]["observed"]["pe_ttm"] == 10.0 and f["E02"]["observed"]["pe_mid_cycle"] == 29.1 and f["E02"]["severity"] == "high"
    assert f["E07"]["status"] == "review" and f["E07"]["watch"] == "high" and "72% of it is the terminal value" in f["E07"]["explanation"] and "134.40 to 200.00" in f["E07"]["explanation"]
    val["inputs"]["mcap"] = 40e9
    assert by_id(T.evaluate(c, None, TODAY, val))["E02"]["status"] == "review"
    bank = company(); bank["profile"]["sic"] = "6022"; bank["quality"]["hist"] = hist([5e8, 5e8, 6e8, 4e8, 5e8, 6e8, 9e8, 1e9])
    fb = by_id(T.evaluate(bank, None, TODAY, {"inputs": {"mcap": 9e9, "ni": 1e9}}))
    assert fb["J06"]["status"] == "triggered" and fb["J06"]["confidence"] == "low" and fb["E02"]["status"] == "not_applicable" and "credit losses" in fb["J06"]["missing_evidence"][0].lower()
    reit = company(); reit["profile"]["sic"] = "6798"
    reit["quality"]["fy"][1].update({"ni": 30e6}); reit["quality"]["cap"]["fy"][1]["items"].update({"div": -80e6, "capex": -20e6})
    fr = by_id(T.evaluate(reit, None, TODAY))
    assert fr["J08"]["status"] == "clear" and "as a REIT's usually is" in fr["J08"]["explanation"] and fr["J08"]["observed"]["payout_of_ocf"] == 0.62
    reit["quality"]["cap"]["fy"][1]["items"]["div"] = -150e6
    assert by_id(T.evaluate(reit, None, TODAY))["J08"]["status"] == "triggered"


def test_b08_reads_the_releases_reconciliations():
    """B08 v2: the same costs excluded quarter after quarter, read from the GAAP-to-adjusted table of each release;
    the street-vs-GAAP EPS gap stays the stand-in while fewer than three tables are on file"""
    def recon(label, items, gaap=1e9):
        return {"measure": "non-GAAP net income", "from": "Net income", "gaap": gaap, "adjusted": gaap + sum(a for _, a in items), "items": items, "balanced": True, "rank": 0}
    c = company()
    qs = []
    for i, lab in enumerate(["Q4 2024", "Q1 2025", "Q2 2025", "Q3 2025"]):
        items = [["Stock-based compensation", 3e8], ["Amortization of acquired intangible assets (1)", 5e7]] + ([["Litigation settlement", 3e8]] if i == 1 else [])
        qs.append({"end": f"2025-{3 * i or 1:02d}-{28 if i else 1:02d}" if i else "2024-12-31", "label": lab, "filed": "2025-11-01", "doc_url": f"https://sec.gov/{i}", "nongaap": recon(lab, items)})
    c["quarters"] = qs
    f = by_id(T.evaluate(c, None, TODAY))["B08"]
    assert f["status"] == "triggered" and f["confidence"] == "medium" and f["severity"] == "high"
    rec = f["observed"]["recurring_items"]
    assert [r[1] for r in rec] == ["stock compensation", "amortisation of acquired intangibles"] and rec[0][2] == 4 and rec[0][3] == 1200
    assert "Litigation" not in str(rec) and "2 costs excluded" in f["explanation"] and "35% of GAAP" in f["explanation"]
    assert len(f["evidence"]) == 4 and f["evidence"][0]["url"] == "https://sec.gov/0"
    # only amortisation recurs, and it is small → still triggered, medium
    for q in c["quarters"]:
        q["nongaap"]["items"] = [["Amortization of intangibles", 5e7]] if q["label"] != "Q1 2025" else [["Restructuring", 1e8]]
    f = by_id(T.evaluate(c, None, TODAY))["B08"]
    assert f["status"] == "triggered" and f["severity"] == "medium" and len(f["observed"]["recurring_items"]) == 1
    # nothing recurs → clear, with the tables cited
    for i, q in enumerate(c["quarters"]):
        q["nongaap"]["items"] = [[["Fire", "Flood", "Strike", "Recall"][i] + " costs", 1e8]]
    assert by_id(T.evaluate(c, None, TODAY))["B08"]["status"] == "clear"
    # two tables only → the EPS-gap proxy; none → insufficient with the count in the reason
    del c["quarters"][0]["nongaap"]; del c["quarters"][1]["nongaap"]
    f = by_id(T.evaluate(c, None, TODAY))["B08"]
    assert f["status"] == "insufficient_data" and "2 quarters with a reconciliation" in f["reason"]
    er = {"nongaap": {"points": [{"quarter": f"2025-Q{i}", "street": 2.0, "gaap": 1.5, "gap_pct": 0.333} for i in range(1, 4)]}}
    f = by_id(T.evaluate(c, er, TODAY))["B08"]
    assert f["status"] == "triggered" and f["confidence"] == "low" and "stand-in" in f["how"]


def test_release_reconciliation_tables():
    """pipeline/release.reconciliation on two shapes: a table that runs down (GAAP, items, adjusted) and one that runs
    across (Visa: GAAP and non-GAAP as columns), and the rank that prefers net income → adjusted over EBITDA chains"""
    from pipeline import release as R
    def html(rows):
        return "<html><body><p>Reconciliation of GAAP to non-GAAP measures (in millions)</p><table>" + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</table></body></html>"
    down = [["", "Three Months Ended September 30, 2025", "September 30, 2024"], ["Net income", "$ 1,000", "$ 900"], ["Stock-based compensation", "200", "180"], ["Amortization of acquired intangibles", "50", "50"],
            ["Income tax effect of adjustments", "(60)", "(55)"], ["Non-GAAP net income", "$ 1,190", "$ 1,075"], ["Diluted shares", "500", "510"]]
    r = R.reconciliation(R.read_tables(html(down)), scale=1e6)
    assert r and r["rank"] == 0 and r["gaap"] == 1e9 and r["adjusted"] == 1.19e9 and r["balanced"]
    assert [x[0] for x in r["items"]] == ["Stock-based compensation", "Amortization of acquired intangibles", "Income tax effect of adjustments"] and r["items"][2][1] == -6e7
    unbalanced = [row[:] for row in down]; unbalanced[5][1] = "$ 1,500"; unbalanced[5][2] = "$ 1,400"
    assert R.reconciliation(R.read_tables(html(unbalanced)), scale=1e6) is None
    ebitda = [["", "2025"], ["Net income", "$ 1,000"], ["Interest expense", "100"], ["Depreciation and amortization", "300"], ["EBITDA", "1,400"], ["Restructuring charges", "50"], ["Adjusted EBITDA", "$ 1,450"]]
    r2 = R.reconciliation(R.read_tables(html(ebitda) + html(down)), scale=1e6)
    assert r2["rank"] == 0 and "non-gaap" in r2["measure"].lower()
    r3 = R.reconciliation(R.read_tables(html(ebitda)), scale=1e6)
    assert r3 and r3["rank"] in (1, 2)


def test_evidence_changes(tmp_path):
    """a newer filing that makes a trap go or appear is logged (store/traps-changes.json, data/traps/changes.json) and
    reaches Flo's alert feed with the filing it rests on; the first run only saves the state; a status that changes
    without a newer filing is not a change"""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import seo_traps as S
    s, store = tmp_path / "site", tmp_path / "store"
    (s / "data" / "c").mkdir(parents=True); (s / "c" / "aaa").mkdir(parents=True); (s / "disclosures" / "data" / "market").mkdir(parents=True)
    (s / "c" / "aaa" / "index.html").write_text('<html><main class="seo"><nav class="seo-toc"><a href="#s">S</a></nav></main></html>')
    (s / "data" / "index.json").write_text(json.dumps({"companies": [{"cik": 1, "ticker": "AAA", "name": "ALPHA INC", "sector": "technology", "revenue": 1.1e9, "filed": "2025-11-01"}]}))
    (s / "disclosures" / "data" / "market" / "flo-alerts.json").write_text(json.dumps({"schema": 1, "events": [{"id": "8k:x", "kind": "8k"}]}))
    c = company(); (s / "data" / "c" / "1.json").write_text(json.dumps(c))
    S.write(str(s), "https://x.test", TODAY, store=str(store))
    ch = json.loads((s / "data" / "traps" / "changes.json").read_text())
    assert ch["first_run"] and ch["changes"] == [] and json.loads((store / "traps-state.json").read_text())["companies"]["1"]["f"]["A01"][0] == "triggered"
    # the same filing, A01 now clear (a rule change, say: capex no longer fell) → the state moves on, no change is logged
    c2 = json.loads(json.dumps(c)); c2["quality"]["cap"]["fy"][-1]["items"]["capex"] = -60e6; c2["quality"]["fy"][-1]["bridge"]["items"] = [["d_ar", -10e6], ["d_inv", -5e6]]
    (s / "data" / "c" / "1.json").write_text(json.dumps(c2))
    S.write(str(s), "https://x.test", TODAY, store=str(store))
    assert json.loads((s / "data" / "traps" / "changes.json").read_text())["changes"] == []
    assert json.loads((store / "traps-state.json").read_text())["companies"]["1"]["f"]["A01"][0] == "clear"
    # back to the first figures on a newer filing → A01 newly triggered, logged once, in the feed; then the next filing releases it
    (s / "data" / "c" / "1.json").write_text(json.dumps(c))
    S.write(str(s), "https://x.test", TODAY, store=str(store))        # same filing again: nothing logged, state = triggered
    c2["quarters"][0].update({"end": "2025-12-31", "label": "Q4 2025", "filed": "2026-02-01", "doc_url": "https://www.sec.gov/Archives/edgar/data/1/0001-26-1.htm"})
    (s / "data" / "c" / "1.json").write_text(json.dumps(c2))
    S.write(str(s), "https://x.test", TODAY, store=str(store))
    S.write(str(s), "https://x.test", TODAY, store=str(store))
    ch = json.loads((s / "data" / "traps" / "changes.json").read_text())
    a01 = [x for x in ch["changes"] if x["rule"] == "A01"]
    assert len(a01) == 1 and a01[0]["kind"] == "released" and a01[0]["from"] == "triggered" and a01[0]["to"] == "clear" and a01[0]["as_of"] == "2025-12-31" and a01[0]["prev_as_of"] == "2025-09-30"
    assert a01[0]["url"] == "https://x.test/c/aaa/analysis-traps/#A01" and not ch["first_run"]
    feed = json.loads((s / "disclosures" / "data" / "market" / "flo-alerts.json").read_text())
    ev = [e for e in feed["events"] if e["kind"] == "trap"]
    assert feed["events"][0]["id"] == "8k:x" and ev and all(e["source_url"].startswith("https://www.sec.gov/Archives/") for e in ev)
    rel = next(e for e in ev if e["rule"] == "A01")
    assert rel["priority"] == "info" and rel["change"] == "released" and "no longer triggered" in rel["title"] and rel["ticker"] == "AAA"
    hub = (s / "disclosures" / "analysis-traps" / "index.html").read_text()
    assert "What a newer filing changed" in hub and "no longer triggered" in hub and "(was 2025-09-30)" in hub
    assert json.loads((store / "traps-changes.json").read_text())["changes"] == ch["changes"]


def test_eps_bridge_order_and_chart_contracts(tmp_path):
    """R02: NI 100 → 100, shares 100 → 80: EPS 1.00 → 1.25, profit part 0, share part 0.25. §37 contracts for A01 (G01)
    and C02 (G04): the values add up, missing working capital is declared in coverage, not drawn as zero"""
    c = company(); c["quality"]["drivers"]["q"][0].update({"eps": {"eps0": 1.0, "eps1": 1.25}, "dil0": 100, "dil1": 80, "cur": {"ni": 100}, "pri": {"ni": 100}})
    f = by_id(T.evaluate(c, None, TODAY))["D03"]
    assert f["observed"]["eps_from_profit"] == 0 and f["observed"]["eps_from_share_count"] == 0.25 and f["status"] == "triggered"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import seo_traps as S
    doc = T.evaluate(company(), None, TODAY)
    a = S.chart_contract(by_id(doc)["A01"], doc)
    v = {x["name"]: x["value"] for x in a["values"]}
    assert a["chart_id"] == "fcf_bridge" and a["data_kind"] == "observed" and a["coverage"] == "complete" and v["prior_fcf"] == 40e6 and v["current_fcf"] == 110e6 and v["capex_reduction"] == 40e6
    assert abs(v["current_fcf"] - v["prior_fcf"] - v["capex_reduction"] - v["wc_cash_change"]) <= abs(v["current_fcf"] - v["prior_fcf"]) and a["sources"][0]["url"] and a["evidence_cutoff"] == doc["filed"]
    c2 = company(); [fy.pop("bridge") for fy in c2["quality"]["fy"]]
    d2 = T.evaluate(c2, None, TODAY)
    a2 = S.chart_contract(by_id(d2)["A01"], d2)
    assert a2 is None or (a2["coverage"].startswith("partial") and not any(x["name"] == "wc_cash_change" for x in a2["values"]))
    l = S.chart_contract(by_id(doc)["C02"], doc)
    assert l and l["chart_id"] == "liquidity_matrix" and {x["name"] for x in l["values"]} == {"cash", "due_12m", "fcf_ttm", "debt"} and "no credit facility" in l["coverage"]
    assert S.chart_contract(by_id(doc)["D03"], doc) is None
    html = S.finding_html(by_id(doc)["A01"], "Alpha", doc)
    assert "class='trap-chart'" in html and '"chart_id":"fcf_bridge"' in html
