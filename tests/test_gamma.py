"""Gamma SIC industry builder regressions; no SEC requests."""
import json
import os
import tempfile

from pipeline import gamma


class Store:
    def __init__(self, records):
        self.records = records

    def company(self, cik):
        return self.records[cik]


def history(values):
    # 2024 Q1 through 2026 Q2; use a non-AI sector as a fixture.
    ends = ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31",
            "2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31",
            "2026-03-31", "2026-06-30"]
    return {"quarters": {d: {"raw": {"revenue": v}} for d, v in zip(ends, values)},
            "profile": {"name": "Fixture Company", "tickers": ["FIX"]}}


def profile(cik, sic, ticker, industry):
    return {"cik": cik, "sic": sic, "ticker": ticker, "industry": industry,
            "name": ticker + " Corp", "sector": "financials" if sic == "6021" else "health",
            "revenue": 1.0e9}


def test_growth_requires_comparable_quarters():
    rows = gamma._growth({"2025-03-31": 100, "2025-06-30": 120,
                          "2026-03-31": 130, "2026-06-30": 156})
    assert rows[-1]["yoy"] == 0.30
    assert rows[-1]["qoq"] == 0.20
    skipped = gamma._growth({"2024-03-31": 100, "2025-09-30": 300})
    assert skipped[-1]["qoq"] is None and skipped[-1]["yoy"] is None


def test_all_sic_industries_not_only_theme_lists():
    v = [100e6, 110e6, 115e6, 120e6, 128e6, 142e6,
         148e6, 160e6, 175e6, 187e6]
    store = Store({1: history(v), 2: history([x * 2 for x in v]),
                   3: history([x * 3 for x in v])})
    idx = [profile(1, "6021", "BK1", "National Commercial Banks"),
           profile(2, "6021", "BK2", "National Commercial Banks"),
           profile(3, "2834", "DRUG", "Pharmaceutical Preparations")]
    with tempfile.TemporaryDirectory() as tmp:
        listing = gamma.build(store, tmp, idx)
        assert {x["sic"] for x in listing} == {"6021", "2834"}
        bank = json.load(open(os.path.join(tmp, "gamma", "6021.json")))
        assert len(bank["companies"]) == 2
        assert bank["period"] == "2026Q2"
        assert bank["summary"]["yoy"]["n"] == 2
        assert bank["summary"]["qoq"]["n"] == 2
        assert bank["summary"]["pooled_yoy"]["n"] >= 8
        assert bank["companies"][0]["stage"] != "unknown"
        assert bank["relationships"] == []
        ix = json.load(open(os.path.join(tmp, "gamma", "index.json")))
        assert ix["universe"] == 3


def test_evidenced_customer_links_only():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "chains"))
        with open(os.path.join(tmp, "chains", "index.json"), "w") as f:
            json.dump({"chains": [{"id": "capex"}, {"id": "hosting"}]}, f)
        with open(os.path.join(tmp, "chains", "capex.json"), "w") as f:
            json.dump({"kind": "spend", "companies": [{"id": "SUP", "t": "SUP"}],
                       "matrix": [{"b": "BUY", "s": "SUP", "v": 10, "named": True},
                                  {"b": "OTHER", "s": "SUP", "v": 20, "named": False}]}, f)
        with open(os.path.join(tmp, "chains", "hosting.json"), "w") as f:
            json.dump({"kind": "customers", "companies": [
                {"t": "SUP", "named": [{"b": "CLIENT", "v": 15}],
                 "flows": {"CLIENT": 15, "GUESS": 50}}]}, f)
        rows = []
        gamma._named_edges(rows, tmp, {"SUP"})
        assert {(e["supplier"], e["customer"]) for e in rows} == {
            ("SUP", "BUY"), ("SUP", "CLIENT")}
        assert all(e["kind"] == "named_customer" for e in rows)


def test_quantiles_and_sparse_distribution():
    assert gamma._quantile([1, 2, 3, 4], .5) == 2.5
    assert gamma._dist([])["median"] is None
    assert gamma._dist([.1, .2, .3])["n"] == 3
