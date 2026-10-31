"""Money flow lab (pipeline/flowlab.py): the filed cash flow of an industry, pay followed to households, two tiers of
suppliers, capital spending by kind of asset, and every company's dollar — money conserved in every view."""
import json
import os

from pipeline import ioflow_beta
from tests.test_ioflow_beta import _setup

CASH = {"ocf": 1_409_877_000, "capex": -219_994_000, "acq": -500_000_000, "buyback": -300_000_000, "div": -280_000_000,
        "borrow": 150_000_000, "inv_other": 20_000_000, "fin_other": -30_000_000, "cash": -250_000_000 + 0}


def _run(tmp_path, mrio=False):
    store, out, index = _setup(tmp_path)
    items = dict(CASH)
    items["cash"] = -sum(v for k, v in items.items() if k != "cash")          # the statement adds up
    store.recs[29905]["quality"] = {"cap": {"ttm": {"label": "TTM to Q3 2026", "end": "2026-09-30", "kind": "ttm", "items": items}}}
    ioflow_beta.build(store, out, index, **({} if mrio else {"mrio_path": os.path.join(out, "none.json")}))
    return out, items


def _conserved(v):
    ins, outs = {}, {}
    for s, t, x, g, n in v["links"]:
        outs[s] = outs.get(s, 0) + x
        ins[t] = ins.get(t, 0) + x
        assert g in "ABCD" and isinstance(n, int) and v["notes"][n]
    for k in set(ins) & set(outs):
        assert abs(ins[k] - outs[k]) <= 1e-3 * max(sum(outs.values()), 1) + 1, k


def test_industry_views(tmp_path):
    out, items = _run(tmp_path)
    d = json.load(open(os.path.join(out, "gamma", "flowlab", "3530.json")))
    assert set(d["views"]) == {"cash", "people", "tiers", "capex"}
    for v in d["views"].values():
        _conserved(v)
    c = d["views"]["cash"]
    flows = {(s, t): x for s, t, x, *_ in c["links"]}
    assert flows[("in:ocf", "pool")] == 1_409_877_000 and flows[("pool", "out:acq")] == 500_000_000
    assert flows[("in:borrow", "pool")] == 150_000_000 and all(g == "A" for s, t, x, g, n in c["links"] if "other" not in s + t)
    p = d["views"]["people"]
    w = {t: x for s, t, x, *_ in p["links"] if s == "p:wages"}
    assert abs(sum(w.values()) - sum(x for s, t, x, *_ in p["links"] if t == "p:wages")) < 2
    assert w["h:housing"] > w["h:food"] > w["h:education"] and all(g == "D" for s, t, x, g, n in p["links"] if s.startswith("p:"))
    t = d["views"]["tiers"]
    assert any(n[0].startswith("t2:") for n in t["nodes"]) and any(n[0] == "v:comp" for n in t["nodes"])
    # tier 2 is part of tier 1, not added on top: what leaves tier 1 equals what came in
    t1_in = sum(x for s, tt, x, *_ in t["links"] if s == "k:p")
    final = sum(x for s, tt, x, *_ in t["links"] if tt.startswith(("t2:", "v:")) or tt == "t1:imports")
    assert abs(t1_in - final) < 1e-6 * t1_in
    cx = d["views"]["capex"]
    assert {n[0] for n in cx["nodes"]} >= {"cx", "a:equipment", "a:structures"}


def test_company_dollar(tmp_path):
    out, items = _run(tmp_path)
    d = json.load(open(os.path.join(out, "flowlab", "c", "29905.json")))
    _conserved(d)
    first = {t: x for s, t, x, *_ in d["links"] if s == "all"}
    assert first["k:capex"] == 219_994_000 and first["k:acq"] == 500_000_000 and first["k:holders"] == 580_000_000
    assert "k:debt" not in first                                               # it borrowed, net
    assert abs(d["total"] - sum(first.values())) < 2 and d["cash"] == "TTM to Q3 2026"
    assert {n[0] for n in d["nodes"]} >= {"k:emp", "p:wages", "p:health", "k:pur", "h:div", "h:buyback"}
    nue = json.load(open(os.path.join(out, "flowlab", "c", "73309.json")))       # no cash statement: operating & capital only
    assert "k:holders" not in {n[0] for n in nue["nodes"]} and nue["cash"] is None
    idx = json.load(open(os.path.join(out, "flowlab", "index.json")))
    assert idx["companies"] == 2 and idx["levels"] >= 2


def test_with_multi_country_tables(tmp_path):
    out, _ = _run(tmp_path, mrio=True)
    d = json.load(open(os.path.join(out, "flowlab", "c", "29905.json")))
    _conserved(d)
    assert any(n[0].endswith("_out") for n in d["nodes"])
