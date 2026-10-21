"""The four-level growth model (pipeline/hier.py): run with `python -m pytest tests/test_hier.py`."""
import json
import os
import random
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline import hier, chainmodel as CM  # noqa: E402


def test_same_company_growth_ignores_new_coverage():
    a = {k: 100.0 * 1.1 ** ((k - 8100) / 4) for k in range(8100, 8112)}
    b = {k: 50.0 for k in range(8108, 8112)}                      # covered only from the last four quarters
    gs = hier.group_series([a, b])
    assert abs(gs[8111][0] - 0.1) < 1e-9                          # 10% a year, not a jump when b appears
    assert gs[8111][1] == 1 and abs(gs[8111][2] - (a[8111] + 50)) < 1e-9


def test_company_learns_its_beta_and_forecasts_from_the_year_ago_quarter():
    rnd = random.Random(3)
    P = {k: 0.05 + 0.1 * ((k // 2) % 2) for k in range(8060, 8116)}    # the industry's growth alternates
    y, g_prev = {}, 0.0
    for k in range(8056, 8112):
        y[k] = 100.0 if k < 8060 else y[k - 4] * (1 + (0.01 + 0.5 * g_prev + 1.2 * P[k] + rnd.gauss(0, 0.01)))
        g_prev = y[k] / y[k - 4] - 1 if k >= 8060 else 0.0
    g = hier.yoy(y)
    m = hier.entity_model(g, P, hier.STRUCT)
    assert m["own"] and 0.9 < m["mu"][2] < 1.5 and m["dataw"] > 0.5      # a beta of 1.2 from a prior of 0.5
    assert m["bt"]["uncond"] < m["bt"]["naive"]
    path = {k: P[k] for k in range(8112, 8116)}
    fc = hier.forecast_entity(m, g, y, path, 8111)
    assert len(fc) == 4 and fc[0][0] == CM.qlabel(8112)
    q, growth, rev, lo, hi, sd = fc[0]
    assert abs(rev - y[8108] * (1 + growth)) < 0.2 and lo < rev < hi          # rounded in the output


def test_sibling_median_beta_is_the_prior_centre():
    P = {k: 0.1 * (-1) ** (k // 3) for k in range(8060, 8112)}
    def company(beta):
        y, gp = {}, 0.0
        for k in range(8056, 8112):
            y[k] = 100.0 if k < 8060 else y[k - 4] * (1 + 0.7 * gp + beta * P[k])
            gp = y[k] / y[k - 4] - 1 if k >= 8060 else 0.0
        return hier.yoy(y)
    m0, sd0 = hier.pooled([company(b) for b in (0.2, 0.3, 0.9)], P)
    assert 0.2 < m0[2] < 0.5 and sd0 == hier.STRUCT[1]
    assert hier.pooled([company(0.3)], P) is None
