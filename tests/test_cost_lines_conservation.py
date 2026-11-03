"""pipeline/model.normalize keeps the operating cost lines only within the chart's own conservation check: lines a
little over or short of the total (0.4–0.5%) used to pass normalize and fail sankey._check, and the quarter was not
drawn at all (Dollar Tree, Leidos, Parsons, Dentsply Sirona on Nov 3 2026)."""
import pytest

from pipeline.model import normalize
from pipeline.sankey import build as build_spec

M = 1e6


def raw(rd, sga):
    # revenue 5,000, gross profit 1,000, operating profit 600: operating expenses 400
    return {"revenue": 5000 * M, "gp": 1000 * M, "oi": 600 * M, "pretax": 590 * M, "tax": 120 * M, "ni": 470 * M,
            "ocf": 700 * M, "da": 100 * M, "capex": 150 * M, "rd": rd * M, "sga": sga * M}


@pytest.mark.parametrize("rd,sga,expect", [
    (100, 301.8, "none"),          # 0.45% over operating expenses: the lines overlap; the total only
    (100, 298.2, "other"),         # 0.45% short: the rest drawn as other operating costs
    (100, 300.4, "lines"),         # 0.1% over: within the check, the lines as they are
    (100, 300.0, "lines"),
])
def test_lines_within_the_check(rd, sga, expect):
    Nc = normalize(raw(rd, sga))
    keys = [k for k, _ in Nc["items"]]
    assert {"none": [], "other": ["rd", "sga", "other_opex"], "lines": ["rd", "sga"]}[expect] == keys
    build_spec(Nc, None, None)              # raises "flow mismatch" if the chart does not add up
