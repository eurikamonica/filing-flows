"""Quarters the chart could not draw ("flow mismatch", Nov 2026: 761 periods, 59 pages left on an older quarter and 39
companies without a page) — from the real figures of the companies that showed each case."""
from pipeline import build, facts
from pipeline.model import normalize
from pipeline.sankey import build as build_spec

M = 1e6


def _draw(raw):
    N = normalize(raw)
    nodes, links, kind = build_spec(N, None, None)          # raises "flow mismatch" when a node does not balance
    return {n["id"]: n for n in nodes}, links, N


def test_gains_inside_operating_profit_flow_in():
    # Antero Midstream Q3 2026: revenue $327.0M, operating profit $557.2M (a gain on a sale inside it)
    raw = {"revenue": 327.022 * M, "opex_total": -230.206 * M, "oi": 557.228 * M, "pretax": 532.78 * M, "tax": 140.12 * M,
           "pl": 392.66 * M, "ni": 392.52 * M, "ocf": 600.3 * M, "da": 60.84 * M, "sbc": 10.96 * M, "capex": 44.72 * M}
    nodes, links, N = _draw(raw)
    assert "op_gain" in N["flags"] and round(N["opgain"] / M, 3) == 230.206
    assert round(nodes["opgain"]["v"] / M, 3) == 230.206 and "costs" not in nodes
    assert {(l["s"], l["t"]) for l in links} >= {("revenue", "oi"), ("opgain", "oi")}
    # Strategy Q3 2026: gross profit $89.6M, operating profit $20.9B (bitcoin marked to market): the gross-profit path
    raw = {"revenue": 125.43 * M, "cor": 35.79 * M, "gp": 89.63 * M, "oi": 20909.79 * M, "pretax": 20942.28 * M,
           "tax": 1409.31 * M, "ni": 19532.97 * M, "ocf": 4.42 * M, "da": 11.24 * M, "sbc": 13.18 * M, "capex": 0.46 * M}
    nodes, links, N = _draw(raw)
    assert "opex" not in nodes and nodes["opgain"]["v"] == N["oi"] - N["gp"]


def test_pretax_gains_without_an_operating_profit_tag():
    # HASI Q2 2026: revenue $120.8M, pre-tax $188.8M, no operating-profit tag: the gains are labelled pre-tax ones
    raw = {"revenue": 120.79 * M, "pretax": 188.76 * M, "tax": 56.97 * M, "pl": 131.78 * M, "ni": 128.62 * M,
           "ocf": 68.05 * M, "da": 0.2 * M, "sbc": 5.92 * M}
    nodes, _, _ = _draw(raw)
    assert nodes["opgain"]["name"] == "Other gains, net of costs"


def test_minority_interests_larger_than_pretax_earnings():
    # MGM Q3 2026: $39.2M of earnings incl. minority interests, $56.3M of it theirs, a $17.1M loss to shareholders
    raw = {"revenue": 4211.89 * M, "costs_total": 4124.57 * M, "oi": 118.68 * M, "pretax": 21.89 * M, "tax": -17.31 * M,
           "pl": 39.21 * M, "ni": -17.11 * M, "nci": 56.31 * M, "ocf": 532.46 * M, "da": 276.4 * M, "sbc": 15.02 * M,
           "capex": 221.66 * M}
    nodes, _, _ = _draw(raw)
    assert round(nodes["net"]["v"] / M, 2) == 39.21 and "nci" not in nodes
    assert "to shareholders" in " ".join(" ".join(x) for x in nodes["net"]["lines"])
    # Surgery Partners Q2 2026 (no pre-tax tag) and Dana Q2 2026 (nothing left after minority interests): the cash bridge
    for raw in ({"revenue": 848.9 * M, "oi": 102.1 * M, "tax": 2.6 * M, "pl": 29.7 * M, "ni": -15.0 * M, "nci": 44.7 * M,
                 "ocf": 59.3 * M, "da": 39.3 * M, "sbc": 3.8 * M, "capex": 21.8 * M},
                {"revenue": 2010 * M, "oi": 76 * M, "pretax": 59 * M, "tax": 54 * M, "pl": 0.0, "ni": -5 * M, "nci": 5 * M,
                 "ocf": 109 * M, "da": 84 * M, "sbc": 8 * M, "capex": 142 * M}):
        _draw(raw)


def test_bank_revenue_from_its_two_parts():
    # Zions Q2 2026: "Revenues" $182M is its fee income, not its total (net interest income $677M + noninterest $460M)
    raw = facts.bank_revenue({"revenue": 182 * M, "nii": 677 * M, "nonii": 460 * M, "nonint_exp": 551 * M}, "Revenues")
    assert raw["rev_bank"] and raw["revenue"] == 1137 * M
    # FVCBankcorp Q2 2026: no noninterest income tag — from pre-tax = NII + nonII − provision − noninterest expense
    raw = facts.bank_revenue({"revenue": 0.5 * M, "nii": 19.149 * M, "pretax": 10.471 * M, "nonint_exp": 10.6 * M, "prov": 0.0,
                              "int_inc": 31.1 * M}, "RevenueFromContractWithCustomerExcludingAssessedTax")
    assert raw["rev_bank"] and raw["nonii_derived"] and abs(raw["revenue"] - (10.471 + 10.6) * M) < 1
    # a company that is not a bank (no interest income, no noninterest expense) is left alone
    plain = {"revenue": 100 * M, "pretax": 20 * M}
    assert facts.bank_revenue(dict(plain), "Revenues") == plain


def test_undrawn_companies_are_read_again_first(tmp_path, monkeypatch):
    store = build.Store(str(tmp_path))
    q = lambda rev: {"2026-06-30": {"end": "2026-06-30", "form": "10-Q", "raw": {"revenue": rev}}}
    store.put(1, {"profile": {"name": "Big"}, "quarters": q(9e9), "da_v": build.DA_VERSION - 1})
    store.put(36270, {"profile": {"name": "M&T"}, "quarters": q(4.42e8), "da_v": 2})       # fee income only: small
    store.put(3, {"profile": {"name": "Current"}, "quarters": q(1e9), "da_v": build.DA_VERSION})
    store.state["undrawn"] = {"36270": "2026-06-30", "3": "2026-06-30"}
    order = []
    monkeypatch.setattr(build, "companyfacts", lambda cik, accn=None: order.append(cik) or {})
    monkeypatch.setattr(build, "time_up", lambda *a, **k: False)
    monkeypatch.setattr(build, "reread_first", lambda *a, **k: set())
    try:
        build.refresh_da(store, limit=2)
    except Exception:
        pass
    assert order[:1] == [36270]                    # undrawn and on the oldest reading: first, ahead of the larger company
