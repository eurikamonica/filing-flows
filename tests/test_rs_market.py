"""pipeline/posts_market.py: the market-map post formats plan from the published research files, every phrasing passes
the post checks with the plan's own rules, and the hub images reach the queued post."""
import datetime as dt
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _hub(tmp_path):
    from pipeline import notify
    d = tmp_path / "site" / "disclosures" / "data" / "research" / "market"
    (d / "img").mkdir(parents=True)
    (tmp_path / "site" / "data").mkdir(parents=True)
    (tmp_path / "site" / "data" / "index.json").write_text(json.dumps({"companies": []}))
    W = lambda name, obj: (d / name).write_text(json.dumps(obj))
    W("flows.json", {"periods": [{"key": "prev", "label": "Q3 2026 — this quarter's filings (Jul–Sep)",
                                  "groups": [{"id": "f13", "label": "13F managers", "buy": 2.76e10, "sell": 6.37e10, "net": -3.61e10},
                                             {"id": "ins", "label": "Insiders", "buy": 5.9e9, "sell": 5.8e10, "net": -5.23e10}],
                                  "sectors": [{"id": "utilities", "label": "Utilities", "net": 2.47e9}, {"id": "other", "label": "Other", "net": -3.7e10},
                                              {"id": "technology", "label": "Technology", "net": -1.98e10}],
                                  "top_in": [{"ticker": "XOM", "name": "Exxon", "net": 3.61e9}, {"ticker": "MU", "name": "Micron", "net": 3.07e9}],
                                  "top_out": [{"ticker": "BRK-A", "name": "Berkshire", "net": -3.0e10}, {"ticker": "NVDA", "name": "Nvidia", "net": -7.4e9}]}]})
    race = [{"period": "2024-12-31", "total": 2.672e11, "top": [["AAPL", 7.5e10, 0.28], ["AXP", 4.5e10, 0.17], ["KO", 2.5e10, 0.09]]},
            {"period": "2025-03-31", "total": 2.6e11, "top": [["AAPL", 6.6e10, 0.25], ["AXP", 4.5e10, 0.17], ["KO", 2.8e10, 0.1]]},
            {"period": "2026-06-30", "total": 2.993e11, "top": [["AAPL", 6.6e10, 0.22], ["AXP", 5.1e10, 0.17], ["KO", 3.3e10, 0.11]]}]
    W("managers.json", {"managers": [{"cik": "1067983", "name": "Berkshire Hathaway", "period": "2026-06-30", "prev_period": "2026-03-31", "filed": "2026-08-14",
                                      "total": 2.993e11, "race": race,
                                      "sectors": [{"id": "technology", "label": "Technology", "w": 0.322, "prev_w": 0.2876,
                                                   "positions": [{"ticker": "GOOGL", "issuer": "ALPHABET", "usd": 2.8e10, "prev_usd": 1.56e10, "shares_chg": 0.4524, "status": "added"}]},
                                                  {"id": "financials", "label": "Financials", "w": 0.2696, "prev_w": 0.2788, "positions": []},
                                                  {"id": "consumer-staples", "label": "Consumer staples", "w": 0.1416, "prev_w": 0.1576, "positions": []}]}]})
    W("status.json", {"built_at": "2026-10-17T22:00:00+00:00", "images": ["heatmap.png", "race-1067983.gif"]})
    (d / "img" / "race-1067983.gif").write_bytes(b"GIF89a-test")
    (d / "img" / "heatmap.png").write_bytes(b"\x89PNG-test")
    cells = [["AMZN", "Amazon", "consumer-disc", 2.5e12, [0, 0, 100, 100], -1.8, 0.4, 20.0, 0.75, 1.2, 0.2],
             ["WMT", "Walmart", "consumer-staples", 8e11, [0, 0, 50, 50], 0.0, 0.9, None, None, None, 0.1],
             ["GOOGL", "Alphabet", "technology", 3e12, [0, 0, 100, 100], -3.1, 0.5, 10.0, 0.9, -2.0, 0.15],
             ["TSCO", "Tractor Supply", "consumer-disc", 3e10, [0, 0, 10, 10], 5.4, 0.2, None, None, None, None],
             ["LMT", "Lockheed", "industrials", 1e11, [0, 0, 10, 10], 3.5, 0.3, None, None, None, None],
             ["X", "US Steel", "materials", 1e10, [0, 0, 5, 5], 0.4, 0.3, None, None, None, None]]
    W("heatmap.json", {"asof": "2026-10-16", "box": [1000, 620], "fields": ["ticker", "name", "sector", "mcap", "rect", "chg", "pos52", "smart", "beat_rate", "si_chg", "pt_upside"],
                       "sectors": [{"id": "real-estate", "label": "Real estate", "rect": [0, 0, 1, 1], "chg": 1.2}, {"id": "financials", "label": "Financials", "rect": [0, 0, 1, 1], "chg": -0.7},
                                   {"id": "other", "label": "Other", "rect": [0, 0, 1, 1], "chg": 9.0}], "cells": cells, "metrics": []})
    W("network.json", {"managers": 23, "nodes": [], "edges": [],
                       "crowding": [{"ticker": "AMZN", "holders": 14, "index": 76.8}, {"ticker": "TSM", "holders": 13, "index": 72.9}, {"ticker": "META", "holders": 12, "index": 70.2},
                                    {"ticker": "GOOGL", "holders": 15, "index": 67.0}, {"ticker": "NVDA", "holders": 8, "index": 60.0}],
                       "check": {"quarters": [{"period": "2025-03-31"}] * 6, "mean_spread": 0.0252, "hit_rate": 0.833}})
    W("maturity.json", {"asof_year": 2026, "companies": 1312, "totals": [1e9, 2.1e11, 2.6e11], "wall": {"BB": [0, 3e10, 1e10], "B": [0, 1.2e10, 0], "CCC": [0, 2e9, 0]},
                        "next_year_top": [{"ticker": "F", "name": "Ford", "band": "BB", "usd": 6.2e9}, {"ticker": "T", "name": "AT&T", "band": "BBB", "usd": 5.1e9}]})
    W("thermometer.json", {"gauges": {"buffett": {"value": 2.14, "percentile": 0.98, "history_from": "1951-10-01", "note": "Z.1"},
                                      "cape": {"value": 38.2, "percentile": 0.96, "history_from": "1881-01", "fit": {"next10y_real": 0.012, "lo80": -0.03, "hi80": 0.055}},
                                      "fwd_pe": {"value": 18.3}}})
    W("liquidity.json", {"latest": {"week": "2026-10-14", "net": 5610.2, "chg_1w": -22.5, "chg_4w": 41.0, "chg_52w": -310.0, "fed": 6400.0, "tga": 789.8, "rrp": 0.0,
                                    "hy_spread": 3.12, "curve": 0.55}})
    return notify.Site(str(tmp_path / "site"))


def test_market_post_kinds_plan_and_pass_the_checks(tmp_path):
    from pipeline import engage, xkinds as X, train_local
    X.load()
    site = _hub(tmp_path)
    ok = lambda *a, **k: True
    today = dt.date(2026, 10, 17)
    got = {k: engage.registered_plan(k, site, [], engage.cfg(), {}, ok, today)
           for k in ("money_flow", "manager_sectors", "holdings_race", "market_map", "crowded", "maturity_wall", "valuation_gauge", "liquidity")}
    for k, p in got.items():
        assert p, k
        assert len(p["fallbacks"]) >= 2, k
        tags = engage.H.pick(engage.kind_tag(k), key=k)
        for fb in p["fallbacks"]:
            post = engage.clean(fb, p["cashtags"], tags, allowed=p.get("allowed"), lines=p.get("lines", False))
            ex = {"check": "engage", "cashtags": p["cashtags"], "tags": tags, "allowed": p.get("allowed"), "lines": p.get("lines", False),
                  "prompt": p["task"] + "\nCashtags: " + " ".join(p["cashtags"])}
            assert train_local.grade(ex, post) == (True, ""), (k, train_local.grade(ex, post), post)
    assert got["money_flow"]["cashtags"] == ["XOM", "BRK.A"] and "Utilities +$2.5B" in got["money_flow"]["fallback"] and "Other" not in got["money_flow"]["fallback"]
    assert got["manager_sectors"]["cashtags"] == ["GOOGL"] and got["manager_sectors"]["hub_images"] == ["research/market/img/race-1067983.gif"]
    assert "Technology 32% (from 29%)" in got["manager_sectors"]["fallback"]
    assert "$AAPL 28% → 22%" in got["holdings_race"]["fallback"] and got["holdings_race"]["allowed"] == ["AAPL", "AXP", "KO"]
    assert got["market_map"]["cashtags"] == ["GOOGL", "AMZN", "WMT"] and "Real estate +1.2%" in got["market_map"]["fallback"]
    assert got["crowded"]["lines"] and got["crowded"]["fallback"].startswith("The most crowded stocks among 23 famous 13F managers:\n\n$GOOGL · 15 of 23 hold it\n$AMZN")
    assert "+2.5 pts" in got["crowded"]["fallback"]
    assert "$210.0B falls due in 2027" in got["maturity_wall"]["fallback"] and "$44.0B of 2027's is rated BB or lower" in got["maturity_wall"]["fallback"]
    assert "Buffett indicator 2.14x GDP (98% percentile since 1951)" in got["valuation_gauge"]["fallback"] and "+1.2%" in got["valuation_gauge"]["fallback"]
    assert got["liquidity"]["fallback"].startswith("Net liquidity (Fed balance sheet − TGA − reverse repo): $5.61T, −$22.5B on the week and +$41.0B over 4 weeks. HY spread 3.12%, 10y−2y +0.55.")
    # the registry: schedules, cooldowns, owner buttons
    assert "market_map" in X.expand(["@morning"]) and {"crowded", "liquidity", "valuation_gauge", "maturity_wall", "holdings_race", "manager_sectors"} <= set(X.expand(["@weekly"]))
    assert X.REG["money_flow"]["cooldown"] == 72 and any(b["kind"] == "engage_market_map" for b in X.buttons())
    # cooldown keys: a second plan of the same manager / week is refused
    assert engage.registered_plan("manager_sectors", site, [], engage.cfg(), {}, lambda k, key, hours=None: key != "1067983", today) is None
    assert engage.registered_plan("liquidity", site, [], engage.cfg(), {}, lambda k, key, hours=None: key != "2026-10-14", today) is None


def test_hub_images_are_attached_to_the_queued_post(tmp_path, monkeypatch):
    """engage.make with a registered kind whose plan names a hub image: the GIF lands in media/x/ and in pending.json."""
    from pipeline import engage, xkinds as X
    X.load()
    site = _hub(tmp_path)
    monkeypatch.setattr(engage.tweet, "chat", lambda msgs: (_ for _ in ()).throw(RuntimeError("no model")))   # the rule-written post is used
    monkeypatch.setattr(engage, "CFG", str(tmp_path / "none.json"))
    media = tmp_path / "media"

    class NoAssets:
        def image(self, *a, **k):
            return None
    made = engage.make(["holdings_race"], site, "https://example.org", str(media), NoAssets())
    assert made and made[0].startswith("holdings_race: ")
    pend = json.load(open(media / "x" / "pending.json"))
    assert len(pend) == 1 and pend[0]["images"] and pend[0]["images"][0].endswith("race-1067983.gif")
    assert (media / "x" / pend[0]["images"][0]).read_bytes() == b"GIF89a-test"
    state = json.load(open(media / "x" / "engage-state.json"))
    assert "holdings_race:1067983" in state and "kind:holdings_race" in state
    assert engage.hub_bytes(site, "research/market/img/none.gif") is None
