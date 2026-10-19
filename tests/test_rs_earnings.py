"""Earnings season (disclosures/app/earnings_season.py, forecast_book.py; pipeline/posts_earnings.py): forecasts frozen
before the report and resolved after it, scores, the build on fixture data, and every X post format's phrasings passing
the post checks."""
import datetime as dt
import gzip
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "disclosures", "app"))


def test_forecast_book_freezes_once_and_scores():
    import forecast_book as FB
    b = FB.load("/nonexistent/book.json")
    assert FB.freeze(b, "beat", "AAPL:2026-09-30", "2026-10-30", {"p": 0.8}, meta={"m": 1})
    assert not FB.freeze(b, "beat", "AAPL:2026-09-30", "2026-10-31", {"p": 0.1})          # never rewritten
    assert FB.get(b, "beat", "AAPL:2026-09-30")["forecast"]["p"] == 0.8
    assert FB.resolve(b, "beat", "AAPL:2026-09-30", {"y": 1}) and not FB.resolve(b, "beat", "AAPL:2026-09-30", {"y": 0})
    s = FB.score_prob([(0.8, 1), (0.7, 1), (0.3, 0), (0.9, 0)])
    assert s["n"] == 4 and s["hit_rate"] == 0.75 and 0 < s["brier"] < 1 and s["bins"]
    assert FB.score_point([(1.0, 1.1), (2.0, 1.8)])["mae"] == 0.15
    h = FB.head_to_head([(1.0, 1.5, 1.1), (2.0, 2.0, 2.5)])
    assert h["a_closer"] == 0.75
    assert FB.conformal_halfwidth(list(range(1, 21)), 0.8) == 17 and FB.conformal_halfwidth([1, 2], 0.8) is None
    assert FB.coverage([(0, 2, 1), (0, 2, 3)]) == 0.5


def _cons(tmp, today):
    """A consensus public/ folder: twelve companies with four past reports each, two reporting soon, Polymarket markets."""
    c = tmp / "cons"
    (c / "c").mkdir(parents=True)
    rows, cal = [], []
    for i in range(12):
        t = f"T{i:02d}"
        nxt = (today + dt.timedelta(days=2 if i < 2 else 10 + i)).isoformat()
        surprises = []
        for k in range(4):
            q = f"2025-{3 * (k + 1):02d}-28" if k < 3 else "2025-12-31"
            rep = (dt.date.fromisoformat(q) + dt.timedelta(days=30)).isoformat()
            est = 1.0 + 0.1 * k
            act = est * (1.05 if (i + k) % 3 else 0.9)
            surprises.append({"quarter": q, "reported": rep, "eps_est": est, "eps_act": round(act, 3), "surprise": round(act / est - 1, 4)})
        markets = [{"kind": "beat", "p": 0.7, "eps_strike": 1.4, "report_date": nxt, "closed": False, "url": "https://polymarket.com/x", "basis": "gaap"}] if i < 2 else []
        if i == 0:
            markets.append({"kind": "above", "closed": False, "end": (today + dt.timedelta(days=3)).isoformat(), "title": "T00 closes above?",
                            "url": "https://polymarket.com/y", "stats": {"strikes": [95, 100, 105, 110], "p_above": [0.9, 0.6, 0.3, 0.1], "median": {"value": 102}, "q10": {"value": 95}, "q90": {"value": 110}}})
        doc = {"cik": 1000 + i, "ticker": t, "name": f"Company {i}", "sector": "technology" if i % 2 else "financials",
               "analysts": {"price": 100.0, "shares": 1e9, "next_earnings": {"date": nxt, "estimate": False},
                            "periods": [{"period": "0q", "end": "2026-09-30", "eps": {"avg": 1.4, "low": 1.3, "high": 1.5, "numberOfAnalysts": 10, "yearAgoEps": 1.2},
                                         "rev": {"avg": 2e9, "low": 1.9e9, "high": 2.1e9, "yearAgoRevenue": 1.8e9},
                                         "eps_trend": {"current": 1.4, "30daysAgo": 1.38}, "revisions": {"upLast30days": 2, "downLast30days": 1}}]},
               "snapshot_fields": ["quarter_end", "eps_q", "rev_q", "eps_y", "rev_y", "target_mean", "rating_mean", "price"],
               "snapshots": [[(today - dt.timedelta(days=40)).isoformat(), ["2026-09-30", 1.38, 2e9, 5.0, 8e9, 120, 2.5, 100]],
                             [today.isoformat(), ["2026-09-30", 1.4, 2e9, 5.0, 8e9, 120, 2.5, 100]]],
               "surprises": surprises, "markets": markets,
               "calibration": [{"report_date": s["reported"], "p_day_before": 0.8, "yes": s["eps_act"] > s["eps_est"], "eps_strike": s["eps_est"]} for s in surprises]}
        (c / "c" / f"{1000 + i}.json").write_text(json.dumps(doc))
        cal.append({"date": nxt, "ticker": t})
    (c / "calendar.json").write_text(json.dumps({"rows": cal}))
    return c


def _hub(tmp, today):
    h = tmp / "hub"
    (h / "cache" / "prices").mkdir(parents=True)
    (h / "market" / "options").mkdir(parents=True)
    days = [today - dt.timedelta(days=k) for k in range(600, -1, -1)]
    days = [d for d in days if d.weekday() < 5]
    for i in range(12):
        rows = [[d.isoformat(), 100 + (j % 17) * 0.5 + (0.3 if i == 0 else 0), 2e6] for j, d in enumerate(days)]
        with gzip.open(h / "cache" / "prices" / f"T{i:02d}.json.gz", "wt") as f:
            json.dump({"rows": rows}, f)
    with gzip.open(h / "cache" / "prices" / "SPY.json.gz", "wt") as f:
        json.dump({"rows": [[d.isoformat(), 500 + j * 0.05, 5e7] for j, d in enumerate(days)]}, f)
    asof = today.isoformat()
    exp1, exp2 = (today + dt.timedelta(days=1)).isoformat(), (today + dt.timedelta(days=4)).isoformat()
    smile = [[k, 0.5 - 0.002 * (k - 100) + 0.0005 * (k - 100) ** 2] for k in range(80, 125, 5)]
    for i in range(2):
        (h / "market" / "options" / f"T{i:02d}.json").write_text(json.dumps({"ticker": f"T{i:02d}", "spot": 100.0, "iv30": 60.0, "skew25": 0.05, "pc_oi": 0.9, "pc_vol": 1.1,
                                                                            "as_of": asof, "term": [[exp1, 0.4], [exp2, 0.7]], "smiles": [{"exp": exp2, "days": 4, "pts": smile}]}))
    (h / "market" / "short-interest.json").write_text(json.dumps({"settlement_date": "2026-09-30", "rows": [{"ticker": "T03", "short": 2e8, "dtc": 6.0, "adv": 3e7}]}))
    (h / "market" / "insiders.json").write_text(json.dumps({"summary": [{"ticker": "T00", "buy_value": 5e6, "sell_value": 0}]}))
    return h


def test_earnings_build_freezes_previews_and_resolves(tmp_path):
    import earnings_season as ES
    import forecast_book as FB
    today = dt.date(2026, 10, 19)
    cons, hub = _cons(tmp_path, today), _hub(tmp_path, today)
    root = tmp_path / "re"
    st = ES.build(root, cons, hub, today=today, verbose=False)
    assert st["reports_history"] == 48 and st["previews"] == 12 and st["book"]["beat"] == 2 and st["frozen_new"] == 2
    pub = root / "public"
    d = json.loads((pub / "c" / "T00.json").read_text())
    assert d["model"]["frozen"] and 0 < d["model"]["p"] < 1 and d["polymarket"]["p"] == 0.7
    assert d["implied"]["method"].startswith("event variance") and d["implied"]["move"] > 0
    assert d["ours"]["eps"] and d["options"]["vrp"] is not None and d["distributions"][0]["options_above"][0] > d["distributions"][0]["options_above"][-1]
    ix = json.loads((pub / "index.json").read_text())
    assert len(ix["rows"]) == 12 and "frozen" in ix["fields"]
    sc = json.loads((pub / "scorecard.json").read_text())
    assert sc["polymarket"]["n"] == 48 and sc["model"]["inputs_used"] and sc["model"]["trained_on"] == 48
    sq = json.loads((pub / "squeeze.json").read_text())
    assert sq["rows"][0]["ticker"] == "T03" and sq["rows"][0]["score"] > 0
    assert json.loads((pub / "season.json").read_text())["calendar"]
    # the frozen probability never moves, even when the inputs change; the report resolves it once the actual arrives
    book0 = FB.load(root / "cache" / "book.json")
    p0 = FB.get(book0, "beat", "T00:2026-09-30")["forecast"]["p"]
    doc = json.loads((cons / "c" / "1000.json").read_text())
    doc["markets"][0]["p"] = 0.2
    doc["surprises"].append({"quarter": "2026-09-30", "reported": (today + dt.timedelta(days=2)).isoformat(), "eps_est": 1.4, "eps_act": 1.5, "surprise": 0.0714})
    doc["analysts"]["next_earnings"]["date"] = "2027-01-28"
    (cons / "c" / "1000.json").write_text(json.dumps(doc))
    later = today + dt.timedelta(days=4)
    ES.build(root, cons, hub, today=later, verbose=False)
    book1 = FB.load(root / "cache" / "book.json")
    e = FB.get(book1, "beat", "T00:2026-09-30")
    assert e["forecast"]["p"] == p0 and e["actual"]["y"] == 1
    sc = json.loads((pub / "scorecard.json").read_text())
    assert sc["model_frozen"]["n"] == 1 and sc["eps_vs_analysts"]["n"] == 1
    res = json.loads((pub / "c" / "T00.json").read_text())["results"][0]
    assert res["beat"] == 1 and abs(res["model_p"] - p0) < 1e-6


def _site_with_research(tmp_path, today):
    import earnings_season as ES
    sys.path.insert(0, ROOT)
    from tests.test_pipeline import _site
    from pipeline import notify
    site = _site(tmp_path)
    cons, hub = _cons(tmp_path, today), _hub(tmp_path, today)
    ES.build(tmp_path / "re", cons, hub, today=today, verbose=False)
    dst = site / "disclosures" / "data" / "research" / "earnings"
    import shutil
    shutil.copytree(tmp_path / "re" / "public", dst)
    # a finished week for the scorecard and recent moves: pretend two reports happened last week with implied moves
    sc = json.loads((dst / "scorecard.json").read_text())
    wk = (today - dt.timedelta(days=today.weekday() + 7)).isoformat()
    sc["weeks"].insert(0, {"week": wk, "n": 9, "beats": 7, "pm_n": 9, "pm_right": 7, "model_n": 9, "model_right": 6, "frozen_n": 4, "frozen_right": 3, "moves_n": 3, "moves_inside": 2})
    for i, t in enumerate(("T04", "T05", "T06")):
        sc["rows"].insert(0, {"ticker": t, "reported": (today - dt.timedelta(days=2)).isoformat(), "surprise": 0.1 - 0.1 * i, "polymarket": 0.8, "polymarket_right": 1 if i < 2 else 0,
                              "implied": 0.05, "move": 0.08 - 0.05 * i, "model": 0.7, "model_right": 1})
    (dst / "scorecard.json").write_text(json.dumps(sc))
    pe = json.loads((dst / "pead.json").read_text())
    pe["interval80"] = 0.2
    pe["rows"] = [{"ticker": f"T0{k}", "reported": (today - dt.timedelta(days=1)).isoformat(), "surprise": 0.05, "pred": v} for k, v in zip(range(4, 8), (0.04, 0.03, 0.02, -0.05))]
    (dst / "pead.json").write_text(json.dumps(pe))
    ng = {"rows": [{"ticker": "T08", "name": "Company 8", "flag": True, "gap_pct": 0.3, "gap_prev_mean": 0.1, "points": [{"street": 2.0, "gaap": 1.4}]},
                   {"ticker": "T09", "name": "Company 9", "flag": True, "gap_pct": 0.25, "gap_prev_mean": 0.05, "points": [{"street": 1.0, "gaap": 0.75}]}]}
    (dst / "nongaap.json").write_text(json.dumps(ng))
    rt = json.loads((dst / "readthrough.json").read_text())
    rt["beta"] = 0.64
    rt["rows"] = [{"ticker": "T01", "name": "Company 1", "sector": "technology", "report_date": (today + dt.timedelta(days=2)).isoformat(), "peer_mean": 0.04, "n_peers": 5, "pred": 0.026},
                  {"ticker": "T03", "name": "Company 3", "sector": "technology", "report_date": (today + dt.timedelta(days=4)).isoformat(), "peer_mean": 0.04, "n_peers": 5, "pred": 0.026}]
    (dst / "readthrough.json").write_text(json.dumps(rt))
    se = json.loads((dst / "season.json").read_text())
    se.update(season="CY2026Q3", overall={"n": 48, "beats": 40, "beat_pct": 0.8333, "mean_surprise": 0.031, "est_n": 0, "est_raised": 0, "est_cut": 0},
              previous={"season": "CY2026Q2", "n": 50, "beat_pct": 0.78},
              sectors=[{"sector": "technology", "n": 24, "beat_pct": 0.9}, {"sector": "financials", "n": 24, "beat_pct": 0.75}])
    (dst / "season.json").write_text(json.dumps(se))
    op = json.loads((dst / "options.json").read_text())
    op["rows"] = [{"ticker": f"T{k:02d}", "iv30": 0.6, "rv30": 0.3, "vrp": 0.3 - 0.01 * k} for k in range(3)]
    (dst / "options.json").write_text(json.dumps(op))
    s = notify.Site(str(site))
    rows = s.json("index.json")["companies"]
    for e in rows:
        e["ticker"] = (e.get("ticker") or "").upper().replace("-", ".")
    return s, rows, {r["ticker"]: r for r in rows if r.get("ticker")}


def test_earnings_posts_every_phrasing_passes(tmp_path):
    from pipeline import engage, hashtags as H, posts_earnings as P, xkinds as X  # noqa: F401
    X.load()
    today = dt.date(2026, 10, 19)
    s, rows, by = _site_with_research(tmp_path, today)
    c = engage.cfg()
    ok = lambda *a, **k: True
    got = {}
    for k in ("earn_preview", "earn_three_way", "earn_scorecard", "earn_moves", "earn_pead", "earn_breadth", "earn_squeeze", "earn_nongaap", "earn_vrp",
              "earn_readthrough", "earn_dist"):
        got[k] = engage.registered_plan(k, s, rows, c, by, ok, today)
    assert got["earn_preview"]["cashtags"] == ["T00"] and "• Polymarket: 70% chance of a beat" in got["earn_preview"]["fallback"]
    assert got["earn_three_way"] is None                                            # only two reporters with both numbers
    assert "Polymarket called 7 of 9" in got["earn_scorecard"]["fallback"] and "our model (frozen before each report) 3 of 4" in got["earn_scorecard"]["fallback"]
    assert got["earn_moves"]["allowed"] == ["T04", "T05", "T06"] and "$T04: options ±5.0% → moved +8.0%" in got["earn_moves"]["fallback"]
    assert got["earn_pead"] and "80% range: ±20%" in got["earn_pead"]["fallback"]
    assert "Q3 2026 earnings so far: 83% of 48 reports beat EPS estimates (Q2 2026: 78%)" in got["earn_breadth"]["fallback"] and "strongest: technology 90% (24)" in got["earn_breadth"]["task"]
    assert got["earn_squeeze"] is None                                              # one ranked name
    assert got["earn_nongaap"]["cashtags"] == ["T08", "T09"] and "Street $2.00 vs GAAP $1.40" in got["earn_nongaap"]["fallback"]
    assert got["earn_vrp"]["allowed"] == ["T00", "T01", "T02"]
    assert got["earn_readthrough"]["cashtags"] == ["T01", "T03"] and "Read-through: +2.6%" in got["earn_readthrough"]["fallback"]
    assert got["earn_dist"]["cashtags"] == ["T00"] and "Polymarket's median is $102" in got["earn_dist"]["fallback"]
    for k, p in got.items():
        if not p:
            continue
        tags = H.pick(engage.kind_tag(k), None, key=k)
        for fb in p["fallbacks"]:
            post = engage.clean(fb, p["cashtags"], tags, allowed=p.get("allowed"), must=p.get("must"), forbid=p.get("forbid"), lines=p.get("lines", False))
            assert ("\n" in post) == bool(p.get("lines")), (k, post)
            assert "reddit" not in post.lower()
    assert "earn_preview" in X.expand(["@evening"]) and "earn_scorecard" in X.expand(["@weekly"])
    views = json.load(open(os.path.join(ROOT, "disclosures", "docs", "views.json")))
    assert any(v["id"] == "earnings" and v["global"] == "EarningsPreviewView" for v in views)
