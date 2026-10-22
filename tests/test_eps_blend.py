"""The EPS forecast's pieces: tag fallback, split restatement, consensus to GAAP, guidance, the frozen-forecast ledger."""
import json

from pipeline import eps_blend as B, eps_fundamental as F, eps_guide as G


def fact(start, end, filed, val, form="10-Q"):
    return {"start": start, "end": end, "filed": filed, "val": val, "form": form, "accn": f"{end}-{form}"}


def test_revenue_tag_fallback_per_quarter_and_pretax_path():
    """A company that moved from SalesRevenueNet to the ASC 606 tag keeps both years; a bank with no operating income
    runs on pretax income."""
    g = {"SalesRevenueNet": {"units": {"USD": [fact("2017-01-01", "2017-03-31", "2017-05-01", 100.0)]}},
         "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [fact("2018-01-01", "2018-03-31", "2018-05-01", 110.0)]}},
         "NetIncomeLoss": {"units": {"USD": [fact("2017-01-01", "2017-03-31", "2017-05-01", 10.0), fact("2018-01-01", "2018-03-31", "2018-05-01", 12.0)]}},
         "IncomeTaxExpenseBenefit": {"units": {"USD": [fact("2017-01-01", "2017-03-31", "2017-05-01", 2.0), fact("2018-01-01", "2018-03-31", "2018-05-01", 3.0)]}},
         "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [fact("2017-01-01", "2017-03-31", "2017-05-01", 1e4), fact("2018-01-01", "2018-03-31", "2018-05-01", 1e4)]}},
         "EarningsPerShareDiluted": {"units": {"USD/shares": [fact("2017-01-01", "2017-03-31", "2017-05-01", .001), fact("2018-01-01", "2018-03-31", "2018-05-01", .0012)]}}}
    q = F.quarterly({"facts": {"us-gaap": g}})
    rev = {r["end"]: r["fields"]["revenue"]["val"] for r in q}
    assert rev == {"2017-03-31": 100.0, "2018-03-31": 110.0}
    obs = F.observations(q, "2019-01-01")
    assert len(obs) == 2 and obs[0]["operating_income"] == obs[0]["pretax_income"] == 12.0


def test_split_restates_earlier_quarters():
    rows = [{"end": "2025-03-31", "eps": 10.0, "diluted_shares": 1e8}, {"end": "2025-06-30", "eps": 1.1, "diluted_shares": 1e9}]
    out = F.split_adjusted(rows)
    assert abs(out[0]["eps"] - 1.0) < 1e-9 and out[0]["diluted_shares"] == 1e9 and out[1]["eps"] == 1.1


def gm():
    return {"2025-09-30": {"eps": 1.00, "filed": "2025-11-01"}, "2025-12-31": {"eps": 1.10, "filed": "2026-02-20", "derived": True},
            "2026-03-31": {"eps": 1.20, "filed": "2026-05-01"}, "2026-06-30": {"eps": 1.30, "filed": "2026-08-01"},
            "2026-09-30": {"eps": 1.40, "filed": "2026-11-01"}}


def test_consensus_converted_to_gaap_with_the_companys_gap():
    cons = {"analysts": {"as_of": "2026-10-20", "periods": [{"period": "0q", "end": "2026-12-31", "eps": {"avg": 1.80, "numberOfAnalysts": 9}}],
                         "surprises": [{"quarter": "2026-03-31", "reported": "2026-04-25", "eps_est": 1.40, "eps_act": 1.45},
                                       {"quarter": "2026-06-30", "reported": "2026-07-25", "eps_est": 1.50, "eps_act": 1.55}]}}
    st = B.street_live(cons, gm(), "2026-12-31", "2026-10-21")
    assert abs(st["gap"] - 0.25) < 1e-9 and abs(st["gaap_equivalent"] - 1.55) < 1e-9 and st["gaps_n"] == 2
    rows = B.street_rows(cons, gm())                                   # the second quarter is forecast with the first's gap
    assert len(rows) == 1 and abs(rows[0]["street"] - (1.50 - 0.25)) < 1e-9
    assert B.street_live(cons, gm(), "2026-12-31", "2026-10-19") is None   # a consensus snapshot from after the cutoff


def test_guidance_quarter_and_full_year_fourth_quarter():
    g = {"releases": [{"filed": "2026-10-28", "url": "https://x", "rows": [
        {"period": "fy", "basis": "gaap", "lo": 5.0, "hi": 5.2, "mid": 5.1, "text": "full-year GAAP EPS $5.00 to $5.20"}]}]}
    out = B.guidance(g, gm(), "2026-12-31", "2026-11-05", 0.25)
    assert out and abs(out["value"] - (5.1 - (1.2 + 1.3 + 1.4))) < 1e-9 and out["kind"].startswith("full year")
    g2 = {"releases": [{"filed": "2026-10-28", "url": "https://x", "rows": [
        {"period": "q", "basis": "adjusted", "lo": 1.7, "hi": 1.9, "mid": 1.8, "text": "fourth-quarter adjusted EPS $1.70-$1.90"}]}]}
    out = B.guidance(g2, gm(), "2026-12-31", "2026-11-05", 0.25)
    assert abs(out["value"] - 1.55) < 1e-9
    assert G.parse(["For the fourth quarter, the Company expects GAAP diluted earnings per share of $1.40 to $1.50."])[0]["quarter"] == 4


def test_predictability_and_probability_shrink():
    frows = [{"cik": "1", "actual": 1.0, "forecast": 1.0 + e, "scale": 1.0, "filed": f"2025-0{i % 9 + 1}-01", "cutoff": "2026-01-01",
              "same_quarter_last_year": 0.9} for i, e in enumerate([.01, -.02, .01, .02, -.01] * 12)]
    frows += [{"cik": "2", "actual": 1.0, "forecast": 1.0 + e, "scale": 1.0, "filed": f"2025-0{i % 9 + 1}-01", "cutoff": "2026-01-01",
               "same_quarter_last_year": 0.9} for i, e in enumerate([.4, -.5, .3, -.6, .5] * 12)]
    v_at = B.add_predictability(frows)
    assert v_at("1", None) < 1 < v_at("2", None)                       # the steady company gets the narrower range
    pool = B.residuals(frows, "forecast")
    assert 0 <= B.p_up(pool, 1.0, 1.0, 0.9) <= 1


def test_ledger_freezes_until_reported_then_scores(tmp_path):
    """A forecast is refreshed each run until the quarter's report is on the site, then frozen and scored on the 10-Q."""
    from pipeline import eps_gaap
    store = tmp_path / "eps-fundamental"
    store.mkdir()
    rows = []
    for y in range(2021, 2027):
        for qn, (s, e) in enumerate((("01-01", "03-31"), ("04-01", "06-30"), ("07-01", "09-30"), ("10-01", "12-31"))):
            end = f"{y}-{e}"
            if end > "2026-06-30":
                continue
            filed = f"{y}-{['05', '08', '11'][qn]}-01" if qn < 3 else f"{y + 1}-02-20"
            rev = 100.0 * (1.05 ** (y - 2021)) * (1 + .02 * qn)
            ni = rev * .1
            rows.append({"end": end, "fields": {k: {"val": v, "filed": filed, "tag": k, "accn": end} for k, v in {
                "revenue": rev, "operating_income": rev * .15, "pretax_income": rev * .13, "tax_expense": rev * .03,
                "net_income": ni, "diluted_shares": 1e4, "eps": ni / 1e4}.items()}})
    (store / "7.json").write_text(json.dumps({"cik": 7, "ticker": "SEVN", "quarters": rows}))
    out, ledger, index = tmp_path / "out", tmp_path / "ledger.json", tmp_path / "index.json"
    index.write_text(json.dumps({"companies": [{"cik": 7, "end": "2026-06-30"}]}))
    B.run(store, out, ledger=str(ledger), index=str(index), today="2026-08-10")
    book = json.loads(ledger.read_text())
    assert list(book["rows"]) == ["7|2026-09-30"] and not book["rows"]["7|2026-09-30"]["locked"]
    first = book["rows"]["7|2026-09-30"]["point"]
    index.write_text(json.dumps({"companies": [{"cik": 7, "end": "2026-09-30"}]}))         # the release is in
    B.run(store, out, ledger=str(ledger), index=str(index), today="2026-10-25")
    book = json.loads(ledger.read_text())
    assert book["rows"]["7|2026-09-30"]["locked"] and book["rows"]["7|2026-09-30"]["point"] == first
    rows.append({"end": "2026-09-30", "fields": {k: {**v, "filed": "2026-11-01", "val": v["val"]} for k, v in rows[-4]["fields"].items()}})
    (store / "7.json").write_text(json.dumps({"cik": 7, "ticker": "SEVN", "quarters": rows}))
    card = B.run(store, out, ledger=str(ledger), index=str(index), today="2026-11-02")
    r = json.loads(ledger.read_text())["rows"]["7|2026-09-30"]
    assert r["actual"] is not None and r["valid"] and card["scored"] == 1
    doc = json.loads((out / "7.json").read_text())
    sep = next(x for x in doc["ledger"] if x["target_end"] == "2026-09-30")
    assert sep["actual"] == r["actual"]
    assert any(x["target_end"] == "2026-12-31" and not x["locked"] for x in doc["ledger"])   # the next quarter is now open
