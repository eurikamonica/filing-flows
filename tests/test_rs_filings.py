"""pipeline/posts_filings.py: every Filings-radar post kind plans from the published files, and every rule-written phrasing
passes the post checks (cashtags, length, no advice, finished sentences, every number in the task)."""
import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _hub(tmp_path):
    from tests.test_pipeline import _site
    from pipeline import notify
    site = _site(tmp_path)
    rf = site / "disclosures" / "data" / "research" / "filings"
    rf.mkdir(parents=True)
    W = lambda name, obj: (rf / f"{name}.json").write_text(json.dumps(obj))
    W("redflags", {"rows": [
        {"accession": "0000000888-26-000010", "cik": 888, "ticker": "AAPL", "company": "Apple Inc.", "form": "8-K", "filed": "2026-10-18", "kind": "auditor",
         "change": "resigned", "old": "Stephano Slack LLC", "new": "Marcum LLP", "disagreements": False, "severity": "high", "url": "https://www.sec.gov/x/",
         "quote": "Stephano Slack LLC resigned as the independent registered public accounting firm."},
        {"accession": "0000000111-26-000001", "cik": 111, "ticker": "META", "company": "Meta Platforms", "form": "NT 10-Q", "filed": "2026-10-17", "kind": "late",
         "reason": "The Company requires additional time to complete its inventory count", "significant_change": True, "severity": "high", "url": "https://www.sec.gov/y/"},
        {"accession": "0000000222-26-000002", "cik": 222, "ticker": "CRWV", "company": "CoreWeave", "form": "8-K", "filed": "2026-10-18", "kind": "listing", "exchange": "Nasdaq",
         "reason": "share price below $1", "deadline": "2027-04-12", "determination": False, "severity": "low", "url": "https://www.sec.gov/z/"}]})
    W("letters", {"topic_names": {"revenue": "revenue recognition", "non_gaap": "non-GAAP measures"}, "threads": [
        {"cik": 320193, "ticker": "AAPL", "company": "Apple Inc.", "first": "2026-08-01", "last": "2026-10-15", "n": 3, "topics": ["revenue", "non_gaap"],
         "about_form": "10-K", "about_period": "2025-12-31", "closed": True, "letters": [{"excerpt": "Please tell us how you identify performance obligations."}]}]})
    W("capital", {"buybacks": [{"accession": "0000000999-26-000011", "cik": 320193, "ticker": "AAPL", "company": "Apple Inc.", "filed": "2026-10-18", "amount": 110e9,
                                "increase": True, "expires": None, "no_expiration": True, "mcap": 3.5e12, "pct_mcap": 0.0314, "headline": "Apple authorizes buyback", "url": "https://www.sec.gov/b/"}]})
    W("dilution", {"offerings": [{"accession": "0000000333-26-000004", "cik": 333, "ticker": "CRWV", "company": "CoreWeave", "form": "424B5", "filed": "2026-10-17", "kind": "atm",
                                  "amount": 1.5e9, "mcap": 30e9, "pct_mcap": 0.05, "url": "https://www.sec.gov/d/"}],
                   "share_growth": [{"ticker": "CRWV", "change": 0.12, "shares": 560000000, "shares_year_ago": 500000000}]})
    W("ipos", {"lockups": [{"symbol": "ACME", "company": "Acme Robotics, Inc.", "date": "2026-04-20", "filed": "2026-04-20", "price": 18.0, "lockup_ends": "2026-10-24", "since_ipo": 0.5},
                           {"symbol": "ZETA", "company": "Zeta Labs Inc", "date": "2026-04-25", "filed": "2026-04-25", "price": 30.0, "lockup_ends": "2026-10-28", "since_ipo": -0.2}]})
    W("deals", {"deals": [{"target_ticker": "META", "target": "Meta Platforms", "acquirer": "BigPharma Corp.", "acquirer_ticker": "AAPL", "cash": 45.5, "ratio": None, "value": 45.5,
                           "target_price": 44.0, "spread": 0.0341, "annualized": 0.08, "close_by": "2027-03-31", "status": "pending"},
                          {"target_ticker": "CRWV", "target": "CoreWeave", "acquirer": "Acquirer Two Corp", "acquirer_ticker": None, "cash": 12.0, "ratio": None, "value": 12.0,
                           "target_price": 11.9, "spread": 0.0084, "annualized": 0.09, "close_by": "2026-11-20", "status": "pending"}]})
    W("paycomp", {"rows": [{"ticker": "AAPL", "company": "Apple Inc.", "fy_end": "2025-12-31", "total": 25e6, "cap": 40e6, "tsr": 120.0, "peer_tsr": 140.0,
                            "total_chg": 0.25, "tsr_chg": -0.2, "misaligned": True, "mcap": 3.5e12}]})
    W("gov", {"overlap": [{"person": "Jane Roe", "chamber": "House", "ticker": "AAPL", "type": "purchase", "amount_min": 15001, "amount_max": 50000, "date": "2026-10-10",
                           "filed": "2026-10-15", "contracts_90d": 2.5e9, "lobbying_4q": 3e6, "lobbying_issues": ["Defense", "Taxes"], "source_url": "https://x/"}]})
    s = notify.Site(str(site))
    rows = s.json("index.json")["companies"]
    for e in rows:
        e["ticker"] = (e.get("ticker") or "").upper().replace("-", ".")
    by = {r["ticker"]: r for r in rows if r.get("ticker")}
    return s, rows, by


def test_filings_posts_plan_and_pass_the_checks(tmp_path):
    from pipeline import engage, posts_filings as P, xkinds as X
    X.load()
    s, rows, by = _hub(tmp_path)
    today = dt.date(2026, 10, 19)
    ok = lambda *a, **k: True
    c = engage.cfg()
    got = {}
    for k in ("red_flag", "sec_letter", "buyback", "dilution", "lockups", "merger_arb", "ceo_pay", "gov_trades"):
        assert k in X.REG and X.REG[k]["module"] == "pipeline.posts_filings"
        got[k] = engage.registered_plan(k, s, rows, c, by, ok, today)
        assert got[k], k
    assert got["red_flag"]["cashtags"] == ["AAPL"] and "Stephano Slack LLC resigned" in got["red_flag"]["fallback"] and got["red_flag"]["fallback"].startswith("BREAKING: ")
    assert "$110.0B of buybacks — 3.1% of its market cap" in got["buyback"]["fallback"]
    assert got["dilution"]["cashtags"] == ["CRWV"] and "Shares outstanding +12% in a year" in got["dilution"]["fallback"]
    assert got["lockups"]["allowed"] == ["ACME", "ZETA"] and "$ACME Oct 24 (+50% since the IPO)" in got["lockups"]["fallback"]
    assert got["merger_arb"]["cashtags"] == ["META", "CRWV"] and "$META ← $AAPL: +3.4%" in got["merger_arb"]["fallback"]
    assert "$25.0M (+25%)" in got["ceo_pay"]["fallback"] and "$120 (-20%)" in got["ceo_pay"]["fallback"]
    assert got["gov_trades"]["cashtags"] == ["AAPL"] and "$15,001–$50,000" in got["gov_trades"]["fallback"]
    assert got["sec_letter"]["fallback"].startswith("The SEC's review of $AAPL's 10-K")
    from pipeline import local_model as L
    for k, p in got.items():
        tags = p.get("tags") or engage.H.pick(engage.kind_tag(k), None, key=k)
        for fb in p["fallbacks"]:
            post = engage.clean(fb, p["cashtags"], tags, allowed=p.get("allowed"), lines=p.get("lines", False))
            assert ("\n" in post) == bool(p.get("lines")), (k, post)
            prompt = L.compact(engage.messages(k, p["task"], p["cashtags"], tags, p.get("allowed")))
            assert not L.unsupported(post, prompt), (k, post, L.unsupported(post, prompt))
    # a second pass with the cooldown state of the first: the one-filing kinds move on or return None, never the same key
    used = {p.get("event_key") for p in got.values()}
    not_again = lambda kind, key, hours=None: f"{kind}:{key}" not in used and not any(u and u.endswith(":" + str(key)) for u in used)
    p2 = engage.registered_plan("red_flag", s, rows, c, by, not_again, today)
    assert p2 and p2["cashtags"] == ["META"] and "NT 10-Q" in p2["fallback"]
    assert X.expand(["@events"]) and {"red_flag", "buyback", "dilution"} <= set(X.expand(["@events"]))
    labels = {b["kind"] for b in X.buttons()}
    assert {"engage_red_flag", "engage_merger_arb", "engage_ceo_pay"} <= labels
