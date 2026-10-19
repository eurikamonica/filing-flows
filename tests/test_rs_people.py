"""People & index X posts (pipeline/posts_people.py): each plan picks from the published research/people files and every
rule-written phrasing passes the post checks with the plan's own rules; the SEO pages are written from the same files."""
import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _people(hub):
    W = lambda rel, obj: (hub / rel).parent.mkdir(parents=True, exist_ok=True) or (hub / rel).write_text(json.dumps(obj))
    MF = ["cik", "name", "slug", "aum", "period", "filed", "positions", "clone_start", "clone_end", "clone_total", "spy_total", "excess", "max_dd", "coverage", "hit", "decisions"]
    W("research/people/managers.json", {"fields": MF, "rows": [["1067983", "Berkshire Hathaway", "berkshire-hathaway-1067983", 299e9, "2026-06-30", "2026-08-14", 29,
                                                                "2021-02-17", "2026-10-16", 0.612, 0.548, 0.064, -0.19, 0.96, 0.55, 40]]})
    W("research/people/m/1067983.json", {"cik": "1067983", "name": "Berkshire Hathaway", "slug": "berkshire-hathaway-1067983", "aum": 299e9, "period": "2026-06-30",
                                         "filed": "2026-08-14", "positions": 29, "holdings": [["AAPL", "Apple", 0.22, 66e9, None, None], ["AXP", "American Express", 0.17, 51e9, None, None],
                                                                                              ["KO", "Coca-Cola", 0.11, 32e9, None, None]],
                                         "adds": [["DHI", "NEW", None]], "cuts": [["STZ", "EXIT", -100.0]],
                                         "clone": {"start": "2021-02-17", "end": "2026-10-16", "first_filing": "2021-02-16", "filings": 22, "total": 0.612, "spy_total": 0.548, "excess": 0.064,
                                                   "max_dd": -0.19, "spy_max_dd": -0.25, "coverage": 0.96, "years": 5.66, "monthly": [["2021-02", 1.0, 1.0], ["2024-01", 1.3, 1.25], ["2026-10", 1.612, 1.548]]},
                                         "record": {"scored": 120, "decisions": 40, "hit": 0.55}, "quarters": []})
    OF = ["slug", "name", "chamber", "party", "state", "committees", "trades", "scored", "follow", "trade", "hit", "overlaps", "last", "recent"]
    W("research/people/officials.json", {"fields": OF, "rows": [["jane-roe", "Jane Roe", "US House", "Democrat", "CA", 2, 40, 31, 0.021, 0.03, 0.58, 1, "2026-10-08", 3]]})
    W("research/people/o/jane-roe.json", {"id": "g:JANE ROE", "name": "Jane Roe", "slug": "jane-roe", "chamber": "US House", "party": "Democrat", "state": "CA",
                                          "committees": [["HSAS", "House Committee on Armed Services", ""]], "performance": {"n": 40, "scored": 31, "follow": 0.021, "trade": 0.03, "hit": 0.58, "first": "2024-01-05", "last": "2026-10-08"},
                                          "recent": [["2026-10-08", "LMT", "purchase", 15001, 50000, "Self", "2026-10-14", "https://disclosures-clerk.house.gov/x.pdf"]],
                                          "overlaps": [{"ticker": "LMT", "date": "2026-10-08", "type": "purchase", "amount_min": 15001, "amount_max": 50000, "filed": "2026-10-14", "owner": "Self",
                                                        "committee": "House Committee on Armed Services", "committee_id": "HSAS", "area": "defense", "source_url": "https://disclosures-clerk.house.gov/x.pdf"}]})
    W("research/people/insider_context.json", {"trades": 102742, "window": ["2021-06-01", "2026-10-15"], "min_cell": 30, "note": "n",
                                               "table_fields": ["cell", "n", "mean", "lo", "hi", "median", "hit", "months"], "table": [],
                                               "recent": [{"date": "2026-10-15", "ticker": "CRWV", "insider": "Intrator Michael", "role": "CEO", "side": "buy", "value": 3.0e6, "shares": 50000, "price": 60.0,
                                                           "cluster": False, "plan": False, "url": "https://www.sec.gov/Archives/x", "cell": "buy|CEO|$1M–$10M",
                                                           "expected": {"n": 812, "mean": 0.041, "lo": 0.023, "hi": 0.059, "median": 0.012, "hit": 0.53, "months": 40}}]})
    W("research/people/preview13f.json", {"previews": [{"cik": "1697748", "name": "ARK Investment Management LLC", "quarter": "2026-09-30", "due": "2026-11-14", "base_period": "2026-06-30",
                                                        "first_made": "2026-10-19T05:00:00+00:00",
                                                        "predictions": [{"ticker": "TWST", "d": -1, "weight_last": 0.012, "weight_drift": 0.011, "evidence": [{"source": "Schedule 13G/A", "date": "2026-10-10", "detail": "3.1% of the class (from 5.2%)"}]},
                                                                        {"ticker": "ACHR", "d": 1, "weight_last": 0.02, "weight_drift": 0.021, "evidence": [{"source": "Form 4", "date": "2026-09-12", "detail": "bought 1,000,000 shares"}]}]}],
                                          "scored": [], "predictions_scored": 9, "hit_rate": 0.667})
    SF = ["ticker", "name", "mcap", "price", "ni_4q", "ni_last", "turnover", "monthly_shares", "eligible_earnings", "eligible_liquidity", "eligible", "first_flagged"]
    W("research/people/sp500.json", {"threshold": 22.7e9, "members": 502, "resolved": 4, "joined_within_year": 3, "fields": SF,
                                     "rows": [["ALNY", "Alnylam", 30.1e9, 231.8, 774e6, 164e6, 3.7, 29e6, True, True, True, "2026-10-19"], ["MDB", "MongoDB", 27.3e9, 337.6, 58.9e6, 40.9e6, 6.2, 41e6, True, True, True, "2026-10-19"],
                                              ["CVNA", "Carvana", 60e9, 300.0, 1.2e9, 300e6, 4.0, 30e6, True, True, True, "2026-09-01"], ["NET", "Cloudflare", 103e9, 296.3, -206e6, -170e6, 2.1, 80e6, False, True, False, None]]})
    PF = ["ticker", "name", "sector", "targets", "resolved", "hits", "hit_rate", "pending", "touched_so_far", "median_error_12m", "last_month"]
    W("research/people/pt_hits.json", {"tracking_since": "2025-10-18", "fields": PF, "rows": [["AAPL", "Apple Inc.", "technology", 12, 8, 5, 0.625, 4, 2, -0.08, "2026-10"]]})


def test_people_posts_pass_their_checks(tmp_path):
    from tests.test_pipeline import _market_hub
    from pipeline import engage, hashtags as H, posts_people as P, xkinds as X  # noqa: F401
    s, rows, by, today = _market_hub(tmp_path)
    _people(tmp_path / "site" / "disclosures" / "data")
    c = engage.cfg()
    ok = lambda *a, **k: True
    got = {k: engage.registered_plan(k, s, rows, c, by, ok, today) for k in ("clone13f", "committee_trade", "insider_context", "preview13f", "sp500_candidates", "pt_hitrate")}
    assert got["clone13f"]["cashtags"] == ["AAPL"] and "+61%" in got["clone13f"]["fallback"] and "SPY" in got["clone13f"]["fallback"]
    assert got["committee_trade"]["cashtags"] == ["LMT"] and "Armed Services" in got["committee_trade"]["fallback"]
    assert got["insider_context"]["cashtags"] == ["CRWV"] and "n=812" in got["insider_context"]["fallback"] and "+2.3% to +5.9%" in got["insider_context"]["fallback"]
    assert got["preview13f"]["allowed"] == ["TWST", "ACHR"] and "estimate" in got["preview13f"]["fallback"]
    assert got["sp500_candidates"]["allowed"] == ["ALNY", "MDB", "CVNA"] and "$NET" not in got["sp500_candidates"]["fallback"]
    assert got["pt_hitrate"]["cashtags"] == ["AAPL"] and "5 of 8" in got["pt_hitrate"]["fallback"]
    for k, p in got.items():
        tags = p.get("tags") or H.pick(engage.kind_tag(k), None, key=k)
        for fb in p["fallbacks"]:
            post = engage.clean(fb, p["cashtags"], tags, allowed=p.get("allowed"), must=p.get("must"), forbid=p.get("forbid"), lines=p.get("lines", False))
            from pipeline import local_model as L
            assert not L.unsupported(post, p["task"]), (k, post, L.unsupported(post, p["task"]))
    try:
        engage.clean("Jane Roe is guilty of insider trading in $LMT, a scandal.", ["LMT"], ["#x"], forbid=P.NO_ACCUSE)
        raise AssertionError("an accusation passed")
    except ValueError:
        pass
    assert "#SP500" in H.KINDS["index"]
    assert {b["kind"] for b in X.buttons()} >= {"engage_clone13f", "engage_pt_hitrate"}
    assert "sp500_candidates" in X.expand(["@weekly"]) and "insider_context" in X.expand(["@morning"])


def test_seo_people_pages(tmp_path):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import seo_people
    _people(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "robots.txt").write_text("User-agent: *\nAllow: /\nSitemap: https://x.test/sitemap.xml\n")
    assert seo_people.write_pages(str(tmp_path / "research" / "people"), str(out), "https://x.test/") == (1, 1)
    m = (out / "m" / "berkshire-hathaway-1067983" / "index.html").read_text()
    assert "<title>Berkshire Hathaway 13F portfolio" in m and '"@type": "Organization"' in m and "+61.2%" in m and "<svg" in m
    o = (out / "o" / "jane-roe" / "index.html").read_text()
    assert "Armed Services" in o and "not a finding of wrongdoing" in o and 'rel="canonical" href="https://x.test/o/jane-roe/"' in o
    sm = (out / "sitemap-people.xml").read_text()
    assert "https://x.test/m/berkshire-hathaway-1067983/" in sm and "https://x.test/o/" in sm
    assert "sitemap-people.xml" in (out / "robots.txt").read_text()
