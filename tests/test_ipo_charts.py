"""The standard Sankey for prospectus periods (pipeline/ipo_charts.py) and the opt-in lines it uses in the site's
chart builder (pipeline/model.py, sankey.py, analysis.py): a filing's own cost lines, its non-operating lines one by
one and named non-cash items of the cash bridge. Every chart is checked for conservation by sankey.build itself."""
import json
from pathlib import Path

import pytest

from pipeline import analysis, ipo_charts as C, model, sankey
from pipeline.sankey import Fmt

B = 1e9


def ids(nodes):
    return {n["id"]: n for n in nodes}


def flow(links, s, t):
    return sum(l["v"] for l in links if l["s"] == s and l["t"] == t)


def loss_raw(**extra):
    # revenue 100, operating costs 115 (its own three lines), interest +5, a non-cash fair-value loss 200, other -10
    return {"revenue": 100 * B, "oi": -15 * B, "pretax": -220 * B, "tax": 1 * B, "ni": -221 * B, "pl": -221 * B,
            "costs_total": 115 * B, "ocf": -10 * B, "da": 2 * B, "sbc": 8 * B, "capex": 3 * B,
            "cost_lines": [("compute", "Compute", 60 * B), ("people", "Personnel", 30 * B), ("other", "Other costs", 25 * B)],
            "nonop_lines": [("interest", "Interest income", 5 * B), ("fv", "Fair value of notes", -200 * B, "non-cash"),
                            ("other_ie", "Other expense", -10 * B)],
            "bridge_lines": [("fv_back", "Fair value of notes", 200 * B, "non-cash, added back"),
                             ("other_back", "Other instruments", 10 * B)], **extra}


def test_without_the_new_keys_nothing_changes():
    base = {k: v for k, v in loss_raw().items() if k not in ("cost_lines", "nonop_lines", "bridge_lines")}
    a = sankey.build(model.normalize(base), None, None)
    b = sankey.build(model.normalize({**base, "cost_lines": [], "nonop_lines": [], "bridge_lines": []}), None, None)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_loss_layout_draws_each_line():
    N = model.normalize(loss_raw())
    assert [k for k, _ in N["items"]] == ["compute", "people", "other"] and model.item_label(N, "people") == "Personnel"
    nodes, links, kind = sankey.build(N, None, None)
    n = ids(nodes)
    assert kind == "loss"
    assert n["total"]["v"] == pytest.approx(326 * B)                  # revenue + interest income + net loss
    assert n["NL:interest"]["col"] == n["revenue"]["col"] and flow(links, "NL:interest", "total") == pytest.approx(5 * B)
    assert flow(links, "total", "NL:fv") == pytest.approx(200 * B) and n["NL:fv"]["lines"][-1] == ["mut", "non-cash"]
    assert n["I:compute"]["name"] == "Compute" and flow(links, "opcosts", "I:people") == pytest.approx(30 * B)
    assert "nonop_out" not in n and "nonop_in" not in n
    # the cash bridge: named add-backs, the rest of working capital (removed here), cash used in operations
    assert flow(links, "BL:fv_back", "bridge") == pytest.approx(200 * B)
    assert n["wc_out"]["v"] == pytest.approx(9 * B)                   # -10 + 221 - 2 - 8 - 210
    assert n["burn"]["v"] == pytest.approx(10 * B)
    text = analysis.paragraphs(Fmt(100 * B), "H1 2026", N, None, None)
    assert "chiefly fair value of notes ($200.0B, non-cash)" in text[1]
    assert "$200.0B of fair value of notes" in text[2] and "Working capital and other items used $9.0B" in text[2]


def test_profit_layout_draws_each_line():
    raw = {"revenue": 100 * B, "gp": 60 * B, "rd": 10 * B, "sga": 20 * B, "oi": 30 * B, "pretax": 28 * B, "tax": 5 * B,
           "ni": 23 * B, "pl": 23 * B, "ocf": 40 * B, "da": 5 * B, "sbc": 3 * B, "capex": 6 * B,
           "nonop_lines": [("interest", "Interest income", 4 * B), ("fx", "Foreign exchange loss", -6 * B)],
           "bridge_lines": [("gain", "Gain on sale", -2 * B), ("impair", "Impairment", 4 * B)]}
    N = model.normalize(raw)
    nodes, links, kind = sankey.build(N, None, None)
    n = ids(nodes)
    assert kind == "profit"
    assert flow(links, "oi", "NL:fx") == pytest.approx(6 * B) and flow(links, "NL:interest", "pretax") == pytest.approx(4 * B)
    assert flow(links, "oi", "pretax") == pytest.approx(24 * B)
    assert flow(links, "net", "BL:gain") == pytest.approx(2 * B) and n["BL:gain"]["color"] == "noncash"
    assert flow(links, "BL:impair", "ocf") == pytest.approx(4 * B)
    assert flow(links, "net", "ocf") == pytest.approx(21 * B)        # 23 - 2 removed
    assert n["wc_in"]["v"] == pytest.approx(7 * B)                    # 40 - 23 - 5 - 3 - (4 - 2)


def test_lines_that_do_not_add_up_are_left_out():
    raw = loss_raw(nonop_lines=[("interest", "Interest income", 5 * B), ("fv", "Fair value of notes", -150 * B)])
    N = model.normalize(raw)
    assert "nonop_lines" not in N and "nonop_lines_dropped" in N["flags"]
    nodes, _, _ = sankey.build(N, None, None)
    assert "nonop_out" in ids(nodes)


def test_expenses_above_operating_profit_are_drawn_net():
    raw = {"revenue": 100 * B, "oi": 10 * B, "pretax": 13 * B, "tax": 3 * B, "ni": 10 * B, "pl": 10 * B,
           "nonop_lines": [("gain", "Gain", 15 * B), ("loss", "Loss", -12 * B)]}
    nodes, _, kind = sankey.build(model.normalize(raw), None, None)
    n = ids(nodes)
    assert kind == "profit" and "nonop_in" in n and not any(k.startswith("NL:") for k in n)


def test_labels_and_the_period_compared_with():
    p = lambda s, e, **k: {"start": s, "end": e, **k}
    assert C.label(p("2025-01-01", "2025-12-31")) == "FY 2025"
    assert C.label(p("2026-01-01", "2026-06-30")) == "H1 2026"
    assert C.label(p("2026-04-01", "2026-06-30")) == "Q2 2026"
    assert C.label(p("2025-10-01", "2026-03-31")) == "6M to Mar 2026"
    assert C.label(p("2024-07-01", "2025-06-30")) == "FY to Jun 2025"
    assert C.label(p("2025-01-01", "2025-06-30", label="H1 2025")) == "H1 2025"
    periods = [p("2026-01-01", "2026-06-30"), p("2025-01-01", "2025-06-30"), p("2025-04-01", "2025-06-30"),
               p("2025-01-01", "2025-12-31")]
    assert C.prior_of(periods[0], periods) is periods[1]
    assert C.prior_of(periods[3], periods) is None


def test_anthropic_prospectus_charts():
    doc = json.loads((Path(__file__).parent.parent / "pipeline/data/ipo/2130357.json").read_text())
    out = C.charts(doc)
    assert out["default"] == "2026-01-01_2026-06-30"
    labels = [(c["label"], c["vs"]) for c in out["periods"]]
    assert labels == [("H1 2026", "H1 2025"), ("FY 2025", "FY 2024"), ("H1 2025", None), ("FY 2024", "FY 2023"),
                      ("FY 2023", None)]
    h1 = out["periods"][0]
    n = ids(h1["nodes"])
    assert h1["kind"] == "loss" and h1["period"] == "fy" and h1["compare_y"]["vs"] == "H1 2025"
    assert n["revenue"]["v"] == pytest.approx(16.286 * B) and n["NL:fair_value"]["v"] == pytest.approx(72.388 * B)
    assert n["BL:fair_value_addback"]["v"] == pytest.approx(72.388 * B) and n["ocf"]["v"] == pytest.approx(3.929 * B)
    assert n["I:compute"]["name"].startswith("Compute") and "8,945" in n["I:compute"]["source"]
    assert all("Q/Q" not in ln[1] for x in h1["nodes"] for ln in x["lines"])
    assert h1["headline"]["fcf"] == pytest.approx(3.447 * B) and round(h1["headline"]["yoy"]) == 1300
    assert any("non-cash" in t for t in h1["analysis"]) and len(h1["compare_y"]["bullets"]) == 3
    fy24 = out["periods"][3]
    assert ids(fy24["nodes"])["revenue"]["lines"][1][1] == "$0.39B"   # billions: the loss is 21 times revenue
    assert h1["subtitle"] == "Six months ended Jun 30, 2026 · GAAP · Y/Y vs. H1 2025"
