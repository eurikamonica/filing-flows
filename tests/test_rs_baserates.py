"""pipeline/posts_valuation.py, the outside-view formats (base_rate_growth, street_base_rate, stage_river, sensitivity_driver):
they plan from the published research/valuation files (app/base_rates.py fields), register with the engage dispatch, and
every rule-written phrasing passes the post checks: numbers from the task only, 250 characters, no advice words, no "!"."""
import datetime as dt
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

KINDS = ["base_rate_growth", "street_base_rate", "stage_river", "sensitivity_driver"]
ADVICE = re.compile(r"\b(buy|sell|bullish|bearish|undervalued|overvalued|moon|crushes|massive)\b", re.I)


def _hub(tmp_path, with_pm=True):
    from tests.test_pipeline import _site
    site = _site(tmp_path)
    hub = site / "disclosures" / "data" / "research" / "valuation"
    (hub / "c").mkdir(parents=True)
    F = ["cik", "ticker", "name", "sector", "kind", "price", "mcap", "implied_growth", "history_growth", "pe", "pe_pct",
         "stage", "stage_value", "p_implied", "p_implied_in", "peer_group", "peer_n", "req_eps_g", "p_street_eps", "p_street_eps_in", "p_street_rev",
         "req_rev_g", "target_growth", "p_target", "pm_eps_strike", "pm_req_eps_g", "p_pm_eps_base", "pm_beat_prob", "p_pm_price",
         "ov_mean", "ov_p10", "ov_p90", "ov_p_above", "comb_ret", "comb_lo", "comb_hi", "sens_driver", "sens_swing", "river_pe_pct"]
    rows = []
    for i in range(20):
        rows.append({"cik": 100000 + i, "ticker": f"T{i:02d}", "name": f"Test Co {i}", "sector": "technology", "kind": "industrial",
                     "price": 187.5 + i, "mcap": 80e9 if i < 10 else 5e9, "implied_growth": 0.142 + i / 1000, "history_growth": 0.061,
                     "pe": 31.2, "pe_pct": 0.5, "stage": "mature" if i % 2 else "growth", "stage_value": 170.0,
                     "p_implied": 0.18 if i == 0 else 0.5, "p_implied_in": 0.3, "peer_group": "SIC 357 (Electronic Computers), revenue over $50B",
                     "peer_n": 212, "req_eps_g": 0.09, "p_street_eps": 0.41, "p_street_eps_in": 0.55, "p_street_rev": 0.6, "req_rev_g": 0.05,
                     "target_growth": 0.16, "p_target": 0.12, "pm_eps_strike": 1.62 if with_pm else None, "pm_req_eps_g": 0.08 if with_pm else None,
                     "p_pm_eps_base": 0.45 if with_pm else None, "pm_beat_prob": 0.62 if with_pm else None, "p_pm_price": 0.2,
                     "ov_mean": 150.0, "ov_p10": 90.0, "ov_p90": 220.0, "ov_p_above": 0.3, "comb_ret": 0.02, "comb_lo": -0.12, "comb_hi": 0.15,
                     "sens_driver": "Operating margin", "sens_swing": 0.44 - i / 100, "river_pe_pct": 0.95 if i < 3 else 0.5})
    (hub / "index.json").write_text(json.dumps({"generated_at": dt.date.today().isoformat(), "fields": F, "rows": [[r[k] for k in F] for r in rows]}))
    doc = {"stage": {"stage": "mature", "why": "revenue growth +3.1%"},
           "river": {"weeks": ["2026-10-09", "2026-10-16"], "price": [187.5, 187.5], "step": [0, 0], "steps": {"from": ["2026-08-29"], "pe": [6.01]},
                     "metrics": {"pe": {"label": "P/E", "levels": [20, 25, 30, 35, 40], "current": 31.2, "median": 26.4, "pct": 0.95, "weeks": 200}}},
           "sensitivity": {"method": "DCF", "base_value": 162.99, "price": 187.5,
                           "tornado": [{"input": "Operating margin", "how": "±3 pts", "low": 127.04, "high": 198.95, "swing": 0.44},
                                       {"input": "Revenue growth (each year)", "how": "±5 pts", "low": 130.29, "high": 201.95, "swing": 0.43},
                                       {"input": "WACC", "how": "±1 pt", "low": 138.0, "high": 197.49, "swing": 0.36}]}}
    for i in range(20):
        (hub / "c" / f"{100000 + i}.json").write_text(json.dumps(doc))
    (site / "disclosures" / "data" / "market").mkdir(parents=True, exist_ok=True)
    (site / "disclosures" / "data" / "market" / "reddit.json").write_text(json.dumps({"rows": [{"ticker": "T00"}]}))
    return site


def _check(engage, p, k):
    from pipeline import local_model as L
    assert p and p["kind"] == k and p["cashtags"], k
    for fb in p["fallbacks"]:
        assert "!" not in fb and not ADVICE.search(fb), (k, fb)
        assert engage.social.xlen(fb) <= 250, (k, engage.social.xlen(fb), fb)
        post = engage.clean(fb, p["cashtags"], p.get("tags") or ["#stocks"], allowed=p.get("allowed"), must=p.get("must"), forbid=p.get("forbid"),
                            lines=p.get("lines", False))
        assert post and all(f"${t}" in post for t in p["cashtags"]), (k, post)
        assert not L.unsupported(post, p["task"]), (k, post, L.unsupported(post, p["task"]))


def test_outside_view_posts_plan_and_pass_checks(tmp_path):
    from pipeline import engage, notify, xkinds as X
    site = notify.Site(str(_hub(tmp_path)))
    rows = site.json("index.json")["companies"]
    by = {r["ticker"]: r for r in rows if r.get("ticker")}
    reg = X.load()
    assert all(k in reg for k in KINDS)
    ok = lambda *a, **k: True
    today = dt.date.today()
    plans = {}
    for k in KINDS:
        plans[k] = engage.registered_plan(k, site, rows, engage.cfg(), by, ok, today)
        _check(engage, plans[k], k)
    p = plans["base_rate_growth"]
    assert p["cashtags"] == ["T00"]
    assert "$T00 needs +14.2% revenue growth a year for 5 years to justify $188 — only 18% of Electronic Computers peers ever did that" in p["fallback"]
    assert "Street expects +9% EPS for $T00 next quarter: 41% of Electronic Computers peers' quarters got there since 2020. Polymarket says 62%" in plans["street_base_rate"]["fallback"]
    assert "a growth company" in plans["stage_river"]["fallback"] and "95th percentile" in plans["stage_river"]["fallback"]
    assert "it would be $150;" in plans["stage_river"]["fallback"]             # 25 × $6.01 = $150.25, the round multiple nearest the median P/E
    assert "Operating margin (±3 pts): $127 to $199 a share around a $163 base case. Next: revenue growth." in plans["sensitivity_driver"]["fallback"]
    assert {"base_rate_growth", "street_base_rate"} <= set(X.expand(["@morning"]))
    assert any(b["kind"] == "engage_street_base_rate" for b in X.buttons())
    assert "## base_rate_growth" in engage.guide()


def test_street_post_without_polymarket(tmp_path):
    from pipeline import engage, notify
    site = notify.Site(str(_hub(tmp_path, with_pm=False)))
    rows = site.json("index.json")["companies"]
    by = {r["ticker"]: r for r in rows if r.get("ticker")}
    p = engage.registered_plan("street_base_rate", site, rows, engage.cfg(), by, lambda *a, **k: True, dt.date.today())
    _check(engage, p, "street_base_rate")
    assert "Polymarket" not in p["fallback"] and "41%" in p["fallback"]
