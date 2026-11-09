"""pipeline/rollforward.py: two balance sheets and the flows between them. A synthetic company whose statements
articulate exactly (no residual), one whose balance is tagged at one date only (falls into "other", never a movement),
and the identity assets = liabilities + equity at both dates."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import rollforward as RL  # noqa: E402
from pipeline import fsa as W  # noqa: E402


def facts(bal):
    """{concept: {day: value}} → the indexed-facts shape rollforward reads (instants only)"""
    return {"__instants__": {c: {d: {"val": v, "accn": "x", "form": "10-Q", "filed": d} for d, v in days.items()} for c, days in bal.items()}}


D0, D1 = "2025-06-30", "2025-09-30"
BAL = {"Assets": {D0: 1000, D1: 1100}, "Liabilities": {D0: 600, D1: 640}, "StockholdersEquity": {D0: 400, D1: 460},
       "CashAndCashEquivalentsAtCarryingValue": {D0: 100, D1: 130}, "AccountsReceivableNetCurrent": {D0: 200, D1: 230}, "InventoryNet": {D0: 150, D1: 160},
       "PropertyPlantAndEquipmentNet": {D0: 400, D1: 420}, "Goodwill": {D0: 100, D1: 100},
       "AccountsPayableCurrent": {D0: 120, D1: 135}, "LongTermDebtNoncurrent": {D0: 300, D1: 320}}
# the quarter: NI 80, D&A 30, SBC 5, ΔAR −30 (uses cash), ΔInv −10, ΔAP +15 → OCF 90; capex 50; borrowed 20; buyback 25
Q = {"start": D0, "end": D1, "label": "Q3 2025", "ni": 80, "ocf": 90,
     "bridge": {"items": [["da", 30], ["sbc", 5], ["d_ar", -30], ["d_inv", -10], ["d_ap", 15]]}}
CAP = {"q": [{"end": D1, "items": {"ocf": 90, "capex": -50, "borrow": 20, "buyback": -25}, "inv": -50, "fin": -5, "dcash": 35}]}


def by(r):
    return {a["k"]: a for a in r["accounts"]}


def test_articulation_exact():
    fx = facts(BAL)
    r = RL.compute(fx, W.Evidence(fx), [Q], CAP)
    assert r and len(r["q"]) == 1 and not r["y"]
    p = r["q"][0]
    a = by(p)
    # cash: 100 + 90 − 50 − 5 = 135, the balance says 130 → residual −5 (the statements' cash includes something the line does not)
    assert a["cash"]["explained"] == 35 and a["cash"]["residual"] == -5
    assert a["ar"]["delta"] == 30 and a["ar"]["explained"] == 30 and a["ar"]["residual"] == 0
    assert a["inv"]["explained"] == 10 and a["ap"]["explained"] == 15 and a["ap"]["residual"] == 0
    assert a["ppe"]["explained"] == 20 and a["ppe"]["residual"] == 0          # +50 capex − 30 D&A
    assert a["debt"]["explained"] == 20 and a["debt"]["residual"] == 0
    assert a["eq"]["explained"] == 60 and a["eq"]["residual"] == 0           # 80 + 5 − 25
    assert [f[0] for f in a["eq"]["flows"]] == ["ni", "sbc", "buyback"] and r["labels"]["buyback"] == "Share buybacks" and r["labels"]["oci"]
    assert {d["k"] for d in p["detail"]} >= {"cash", "ar", "inv", "ppe", "gw", "ap", "debt", "eq"} and next(d for d in p["detail"] if d["k"] == "ar")["parent"] == "ar"
    # the plugs: other assets = 1000 − (100+200+150+400+100) = 50 → 1100 − 1040 = 60; other liabilities 180 → 185
    assert (a["oth_a"]["open"], a["oth_a"]["close"]) == (50, 60) and (a["oth_l"]["open"], a["oth_l"]["close"]) == (180, 185)
    assert p["identity_gap"] == 0 and p["totals"]["eq_close"] == 460 and p["data_kind"] == "observed"
    assert 0.9 <= p["explained_share"] <= 1 and all("Goodwill" in x for x in a["gw"]["tags"])
    # the period's cash flow statement for the detailed card: NI → non-cash → working capital → OCF → sections → Δcash
    cf = p["cf"]
    assert cf["ni"] == 80 and cf["ocf"] == 90 and [x[0] for x in cf["noncash"]] == ["da", "sbc"] and [x[0] for x in cf["wc"]] == ["d_ar", "d_inv", "d_ap"]
    assert cf["op_other"] == 90 - 80 - 30 - 5 + 30 + 10 - 15 and [x[0] for x in cf["inv"]] == ["capex"] and cf["inv_other_gap"] == 0
    assert [x[0] for x in cf["fin"]] == ["buyback", "borrow"] and cf["fin_other_gap"] == 0 and cf["dcash"] == 35


def test_one_date_tag_is_not_a_movement():
    bal = dict(BAL)
    bal["IntangibleAssetsNetExcludingGoodwill"] = {D1: 40}            # tagged at the quarter end only (a 10-K detail)
    fx = facts(bal)
    a = by(RL.compute(fx, W.Evidence(fx), [Q], CAP)["q"][0])
    assert a["gw"]["delta"] == 0 and "IntangibleAssetsNetExcludingGoodwill" not in a["gw"]["tags"]
    assert a["oth_a"]["close"] == 60                                   # it stays inside "other assets", the totals unchanged


def test_year_on_year_adds_four_quarters():
    days = ["2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30", "2025-09-30"]
    bal = {c: {d: v * (1 + i * 0.1) for i, d in enumerate(days)} for c, v in
           {"Assets": 1000, "Liabilities": 600, "StockholdersEquity": 400, "CashAndCashEquivalentsAtCarryingValue": 100, "AccountsPayableCurrent": 120}.items()}
    qs = [{"start": days[i], "end": days[i + 1], "label": f"Q{i + 1}", "ni": 10, "ocf": 12, "bridge": {"items": [["d_ap", 3]]}} for i in range(4)]
    cap = {"q": [{"end": q["end"], "items": {"ocf": 12, "buyback": -4}, "inv": -2, "fin": -4} for q in qs]}
    fx = facts(bal)
    r = RL.compute(fx, W.Evidence(fx), qs, cap)
    assert len(r["q"]) == 4 and len(r["y"]) == 1
    y = r["y"][0]
    assert y["start"] == days[0] and y["end"] == days[-1] and y["quarters"] == ["Q1", "Q2", "Q3", "Q4"] and y["data_kind"] == "derived"
    a = by(y)
    assert a["ap"]["explained"] == 12 and abs(a["ap"]["delta"] - 48) < 1e-9 and a["eq"]["explained"] == 24   # 4 × (10 − 4)
    assert a["cash"]["explained"] == 4 * (12 - 2 - 4)
    # a quarter missing the line → the four-quarter sum is not pretended
    cap["q"][1]["items"].pop("buyback")
    a2 = by(RL.compute(fx, W.Evidence(fx), qs, cap)["y"][0])
    assert [f[0] for f in a2["eq"]["flows"]] == ["ni"]


def test_notes_explain_and_overlap_is_folded():
    """the notes: OCI explains equity, goodwill recognised replaces the cash paid for acquisitions, lease additions
    explain PP&E and lease liabilities; a negative plug (two tagged lines overlapping) is folded into an 'other' line"""
    bal = dict(BAL)
    bal["OtherAssetsNoncurrent"] = {D0: 60, D1: 70}; bal["DeferredIncomeTaxAssetsNet"] = {D0: 20, D1: 20}   # 1000 − (100+200+150+400+100+60+20) = −30: overlap
    fx = facts(bal)
    fx["OtherComprehensiveIncomeLossNetOfTax"] = {(D0, D1): {"val": -7, "accn": "x", "form": "10-Q", "filed": D1}}
    fx["GoodwillAcquiredDuringPeriod"] = {(D0, D1): {"val": 12, "accn": "x", "form": "10-Q", "filed": D1}}
    cap = {"q": [{"end": D1, "items": {"ocf": 90, "capex": -50, "acq": -20, "borrow": 20, "buyback": -25}, "inv": -70, "fin": -5, "dcash": 15}]}
    r = RL.compute(fx, W.Evidence(fx), [Q], cap)
    p = r["q"][0]
    a = by(p)
    assert [n[0] for n in a["eq"]["notes"]] == ["oci"] and a["eq"]["from_notes"] == -7 and a["eq"]["residual"] == 460 - 400 - 60 + 7
    assert [n[0] for n in a["gw"]["notes"]] == ["gw_acq"] and not any(f[0] == "acq" for f in a["gw"]["flows"]) and a["gw"]["residual"] == 0 - 12
    assert a["oth_a"]["open"] == 50                                                      # merged: the untagged rest is positive
    d = {x["k"]: x for x in p["detail"]}
    assert d["onca"]["open"] == 60 - 30 and d["onca"]["close"] == 70 - 30 and d["oth_a"]["open"] == 0 and d["oth_a"]["close"] == 0   # detail: the overlap comes out of 'other non-current assets', the plug never below zero
    assert d["dta"]["open"] == 20 and d["gw"]["notes"][0][0] == "gw_acq" and d["eq"]["notes"][0][0] == "oci"
    assert sum(x["close"] for x in p["detail"] if x["side"] == "a") == 1100
