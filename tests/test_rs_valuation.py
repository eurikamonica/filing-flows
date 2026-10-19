"""pipeline/posts_valuation.py: the fair value & credit X post formats plan from the published research/valuation files,
register with the engage dispatch, and every rule-written phrasing passes the post checks."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _hub(tmp_path):
    from tests.test_pipeline import _site
    site = _site(tmp_path)
    hub = site / "disclosures" / "data" / "research" / "valuation"
    (hub / "c").mkdir(parents=True)
    F = ["cik", "ticker", "name", "sector", "kind", "price", "mcap", "wacc", "beta", "kd", "dcf_value", "dcf_gap", "mc_p_above", "mc_p10", "mc_p90",
         "implied_growth", "history_growth", "pvgo_share", "pe", "pe_pct", "evs", "evs_pct", "peer_pe_mid", "target_mean", "pm_price", "our_price",
         "range_low", "range_high", "distress_pd", "distance_to_default", "altman_z", "cds_bps", "ri_value", "sector_value", "combined_ratio", "p_ffo"]
    rows = []
    for i in range(40):
        cik, tk = 100000 + i, f"T{i:02d}"
        big = i < 12
        rows.append({"cik": cik, "ticker": tk, "name": f"Test Co {i}", "sector": "technology", "kind": "industrial", "price": 100.0 + i,
                     "mcap": (60e9 if big else 3e9), "wacc": 0.08 + (0.04 if i == 3 else 0), "beta": 1.1, "kd": 0.05 + (0.03 if i == 3 else 0),
                     "dcf_value": 90.0 + i * 2, "dcf_gap": None, "mc_p_above": (i % 10) / 10, "mc_p10": 70.0, "mc_p90": 150.0,
                     "implied_growth": 0.12, "history_growth": 0.08, "pvgo_share": 0.72 if i == 0 else 0.4, "pe": 20.0 + i, "pe_pct": 0.05 if i < 4 else 0.5,
                     "evs": 5.0, "evs_pct": 0.5, "peer_pe_mid": 22.0, "target_mean": 120.0, "pm_price": 105.0, "our_price": 108.0, "range_low": 60.0,
                     "range_high": 160.0, "distress_pd": 0.02 + i * 0.01 if i < 6 else 0.001, "distance_to_default": 2.5, "altman_z": 1.9, "cds_bps": 300,
                     "ri_value": 80.0, "sector_value": None, "combined_ratio": None, "p_ffo": None})
    import datetime as dt
    (hub / "index.json").write_text(json.dumps({"generated_at": dt.date.today().isoformat(), "fields": F, "rows": [[r[k] for k in F] for r in rows]}))
    doc = {"pvgo": {"per_share": 28.0, "growth_share": 0.72, "basis": "NOPAT ÷ WACC − net debt", "earnings": 5.2e9, "rate": 0.08},
           "wacc": {"wacc": 0.12, "kd": 0.08, "kd_how": "effective rate", "beta": 1.3}, "reverse": {"status": "ok", "implied_growth": 0.12, "history_growth": 0.08},
           "football": [{"method": "DCF — Monte Carlo 10th–90th percentile", "low": 70.0, "high": 150.0, "point": 92.0},
                        {"method": "P/E vs peers", "low": 88.0, "high": 110.0, "point": 99.0}, {"method": "Analysts' price targets", "low": 95.0, "high": 130.0, "point": 120.0},
                        {"method": "Polymarket implied price", "low": 98.0, "high": 112.0, "point": 105.0}, {"method": "Our model (Rotation forecast)", "low": 90.0, "high": 125.0, "point": 108.0}]}
    for i in range(40):
        (hub / "c" / f"{100000 + i}.json").write_text(json.dumps(doc))
    (site / "disclosures" / "data" / "market").mkdir(parents=True, exist_ok=True)
    (site / "disclosures" / "data" / "market" / "reddit.json").write_text(json.dumps({"rows": [{"ticker": "T00"}, {"ticker": "T03"}]}))
    return site


def test_valuation_posts_plan_and_pass_checks(tmp_path):
    from pipeline import engage, notify, xkinds as X
    import datetime as dt
    site = notify.Site(str(_hub(tmp_path)))
    rows = site.json("index.json")["companies"]
    by = {r["ticker"]: r for r in rows if r.get("ticker")}
    reg = X.load()
    kinds = ["pvgo_growth", "fair_value_range", "mc_odds", "distress_watch", "wacc_gap", "pe_band"]
    assert all(k in reg for k in kinds)
    assert set(X.expand(["@weekly"])) >= {"mc_odds", "distress_watch", "wacc_gap"}
    ok = lambda *a, **k: True
    today = dt.date.today()
    for k in kinds:
        p = engage.registered_plan(k, site, rows, engage.cfg(), by, ok, today)
        assert p and p["kind"] == k and p["cashtags"], k
        for fb in p["fallbacks"]:
            post = engage.clean(fb, p["cashtags"], p.get("tags") or ["#stocks"], allowed=p.get("allowed"), must=p.get("must"), forbid=p.get("forbid"),
                                lines=p.get("lines", False))
            assert all(f"${t}" in post for t in p["cashtags"]), (k, post)
            # every number in the post is in the task (what the local model is trained and graded on)
            from pipeline import local_model as L
            assert not L.unsupported(post, p["task"]), (k, post, L.unsupported(post, p["task"]))
    p = engage.registered_plan("pvgo_growth", site, rows, engage.cfg(), by, ok, today)
    assert p["cashtags"] == ["T00"] and "72% of $T00's price is a bet on growth" in p["fallback"]
    p = engage.registered_plan("wacc_gap", site, rows, engage.cfg(), by, ok, today)
    assert p["cashtags"] == ["T03"]
    p = engage.registered_plan("pe_band", site, rows, engage.cfg(), by, ok, today)
    assert "bottom of their own P/E range" in p["fallback"]
    assert any(b["kind"] == "engage_distress_watch" for b in X.buttons())
