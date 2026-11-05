"""pipeline/xcard.py: the quarter's one point (the post's opening and the X card's headline), the card's simplified
chart, the rule-based post, and the card drawn by web/sankey.js."""
import struct

import pytest

from pipeline import social, xcard


def quarter(rev=18085, rev_y=17276, oi=5559, oi_y=6745, net=5067, net_y=5787, ocf=6558, segments=None, prev_yoy=None):
    """A Merck-like quarter in $M: revenue → operating profit / costs → pre-tax → net / tax, the cash-flow bridge, and
    (optionally) revenue segments [(name, v, y)]."""
    M = 1e6
    nodes = [{"id": "revenue", "col": 1, "name": "Revenue", "v": rev * M, "color": "rev",
              "lines": [["big", "Revenue"], ["val", f"${rev / 1000:.1f}B"], ["mut", "Y/Y +5% · Q/Q +9%"]]},
             {"id": "oi", "col": 2, "name": "Operating profit", "v": oi * M, "color": "profit",
              "lines": [["name", "Operating profit"], ["val", "$5.6B · 31% of revenue"], ["mut", "Y/Y −18% · Q/Q n/m"]]},
             {"id": "costs", "col": 2, "name": "Costs & expenses", "v": (rev - oi) * M, "color": "cost"},
             {"id": "I:rd", "col": 3, "name": "Research & development", "v": (rev - oi) * 0.4 * M, "color": "cost"},
             {"id": "I:sga", "col": 3, "name": "SG&A", "v": (rev - oi) * 0.6 * M, "color": "cost"},
             {"id": "pretax", "col": 3, "name": "Pre-tax earnings", "v": oi * M, "color": "profit"},
             {"id": "net", "col": 4, "name": "Net earnings", "v": net * M, "color": "profit",
              "lines": [["name", "Net earnings"], ["val", "$5.1B · 91% of pre-tax"], ["mut", "Y/Y −12% · Q/Q n/m"]]},
             {"id": "tax", "col": 4, "name": "Income tax", "v": (oi - net) * M, "color": "cost"},
             {"id": "da", "col": 4, "name": "Depreciation", "v": 726 * M, "color": "profit"},
             {"id": "ocf", "col": 5, "name": "Operating cash flow", "v": ocf * M, "color": "profit"},
             {"id": "fcf", "col": 6, "name": "Free cash flow", "v": (ocf - 1040) * M, "color": "profit"},
             {"id": "capex", "col": 6, "name": "Capital expenditures", "v": 1040 * M, "color": "cost"}]
    links = [{"s": "revenue", "t": "oi", "v": oi * M, "y": oi_y * M, "color": "profit"},
             {"s": "revenue", "t": "costs", "v": (rev - oi) * M, "y": (rev_y - oi_y) * M, "color": "cost"},
             {"s": "costs", "t": "I:rd", "v": (rev - oi) * 0.4 * M, "color": "cost"},
             {"s": "costs", "t": "I:sga", "v": (rev - oi) * 0.6 * M, "color": "cost"},
             {"s": "oi", "t": "pretax", "v": oi * M, "y": oi_y * M, "color": "profit"},
             {"s": "pretax", "t": "net", "v": net * M, "y": net_y * M, "color": "profit"},
             {"s": "pretax", "t": "tax", "v": (oi - net) * M, "y": (oi_y - net_y) * M, "color": "cost"},
             {"s": "net", "t": "ocf", "v": (ocf - 726) * M, "color": "profit"},
             {"s": "da", "t": "ocf", "v": 726 * M, "y": 532 * M, "color": "profit"},
             {"s": "ocf", "t": "fcf", "v": (ocf - 1040) * M, "color": "profit"},
             {"s": "ocf", "t": "capex", "v": 1040 * M, "color": "cost"}]
    for i, (name, v, y) in enumerate(segments or []):
        nodes.insert(i, {"id": f"L:{i}", "col": 0, "name": name, "v": v * M, "color": "rev"})
        links.insert(i, {"s": f"L:{i}", "t": "revenue", "v": v * M, "y": y * M, "color": "rev"})
    q = {"label": "Q3 2026", "end": "2026-09-30", "filed": "2026-11-04", "form": "10-Q", "nodes": nodes, "links": links,
         "headline": {"revenue": rev * M, "yoy": (rev / rev_y - 1) * 100, "ni": net * M, "om": oi / rev * 100, "oi": oi * M, "ocf": ocf * M}}
    prev = {"label": "Q2 2026", "end": "2026-06-30", "headline": {"yoy": prev_yoy}} if prev_yoy is not None else None
    c = {"profile": {"name": "MERCK & CO., INC.", "tickers": ["MRK"], "cik": 310158}, "quarters": [q] + ([prev] if prev else [])}
    return c, q


def test_the_point_of_the_quarter():
    c, q = quarter()                                                   # sales +5%, operating profit −18%
    ins = xcard.insight(c, q)
    assert ins["kind"] == "squeeze" and ins["line"] == "revenue grew 5% but operating profit fell 18%"
    assert ins["headline"].endswith("sold more but kept less") and [s[0] for s in ins["stats"]] == ["Revenue", "Operating profit"]
    c, q = quarter(rev=10230, rev_y=6194, oi=3021, oi_y=1702, net=2034, net_y=1246)     # profit outgrows sales
    assert xcard.insight(c, q)["kind"] == "leverage"
    c, q = quarter(rev=10230, rev_y=6194, oi=3021, oi_y=1702, net=2034, net_y=1246, segments=[("Communications", 6583, 3310), ("Harsh", 2042, 1516), ("Sensors", 1605, 1368)])
    assert xcard.insight(c, q)["kind"] in ("leverage", "segment")
    c, q = quarter(rev=1000, rev_y=1100, oi=-50, oi_y=40, net=-80, net_y=30)              # a swing to a loss
    ins = xcard.insight(c, q)
    assert ins["kind"] in ("loss", "decline") and "loss" in ins["line"] + ins["headline"] or "fell" in ins["line"]


def test_the_card_has_fewer_lines():
    c, q = quarter(segments=[(f"Segment {i}", 3000 - i * 400, 2900 - i * 400) for i in range(6)])
    sp = xcard.spec(c, q)
    ids = [n["id"] for n in sp["nodes"]]
    assert not {"ocf", "da", "fcf", "capex"} & set(ids)                       # no cash-flow bridge
    assert sorted({n["col"] for n in sp["nodes"]}) == [0, 1, 2, 3]             # sources, revenue, operating profit, net
    assert not any(i.startswith("I:") for i in ids)                         # no cost breakdowns
    assert "pretax" not in ids and any(l["s"] == "oi" and l["t"] == "net" for l in sp["links"])   # pass-through skipped
    assert sum(1 for l in sp["links"] if l["t"] == "revenue") == 4 and "x:other" in ids          # top 3 + "3 other lines"
    net = next(n for n in sp["nodes"] if n["id"] == "net")
    assert net["lines"][1][1].endswith("of operating profit") and net["lines"][2] == ["xdn", "−12% Y/Y"]
    xc = sp["xcard"]
    assert xc["kicker"] == "$MRK · Merck & Co. · Q3 2026 earnings" and "sold more but kept less" in xc["headline"]
    assert "@FilingFlows" in xc["credit"] and "not investment advice" in xc["credit"]
    assert xcard.plain_spec(c, q)["xcard"]["headline"] == ""


def test_rule_post_opens_with_the_point():
    c, q = quarter()
    post = xcard.rule_post(c, q, ["#earnings", "#pharma"])
    assert post.startswith("$MRK: Revenue grew 5% but operating profit fell 18%. Q3 2026 revenue $18.1B (+5% Y/Y)")
    assert post.endswith("👇 #earnings #pharma") and social.xlen(post) <= 270
    assert "BREAKING" not in post and "🚨" not in post


def test_x_images_from_the_config():
    c, q = quarter()
    assert [s for s, _, _ in social.post_images(c, q, {"images": ["x"]})] == ["x"]
    q["compare_y"] = {"vs": "Q3 2025"}
    assert [s for s, _, _ in social.post_images(c, q, {"images": ["x", "standard", "year_ago"]})] == ["x", "1-chart", "2-vs-Q3-2025"]
    assert social.email_images({"images": ["x"], "email_images": ["standard"]}) == ["standard"]
    assert social.email_images({"images": ["standard", "year_ago"]}) == ["standard", "year_ago"]   # an older config.json


def test_card_is_drawn_big():
    pytest.importorskip("playwright")
    c, q = quarter()
    try:
        with social.Charts("web") as ch:
            png = ch.image(("chart", xcard.spec(c, q), None), "png", scale=1)
            std = ch.image(("chart", q, None), "png", scale=1)
    except Exception as err:                                              # no browser here
        pytest.skip(f"no Chromium: {err}")
    w, h = struct.unpack(">II", png[16:24])
    sw, sh = struct.unpack(">II", std[16:24])
    assert png.startswith(b"\x89PNG") and w >= 1600 and 1.0 <= w / h <= 2.0      # about 4:3 to 2:1, a phone shows it whole
    assert (sw, sh) != (w, h)                                                     # the site's chart is drawn as before
