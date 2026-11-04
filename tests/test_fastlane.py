"""Earnings fast lane (pipeline/fastlane.py): who is watched, the feed, and the overlay a full scan lays on its site."""
import datetime as dt
import json
import os

from pipeline import fastlane as F

FEED = """<feed><entry>
<title>8-K - Apple Inc. (0000320193) (Filer)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/320193/000032019326000024/0000320193-26-000024-index.htm"/>
<summary type="html"> &lt;b&gt;Filed:&lt;/b&gt; 2026-11-02 &lt;b&gt;AccNo:&lt;/b&gt; 0000320193-26-000024
&lt;br&gt;Item 2.02: Results of Operations and Financial Condition
&lt;br&gt;Item 9.01: Financial Statements and Exhibits</summary>
<updated>2026-11-02T16:30:23-05:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="8-K"/>
<id>urn:tag:sec.gov,2008:accession-number=0000320193-26-000024</id>
</entry><entry>
<title>8-K - SMALL CO (0000000042) (Filer)</title>
<summary type="html">&lt;br&gt;Item 2.02: Results of Operations</summary>
<category scheme="https://www.sec.gov/" label="form type" term="8-K"/>
<id>urn:tag:sec.gov,2008:accession-number=0000000042-26-000001</id>
</entry><entry>
<title>8-K - NVIDIA CORP (0001045810) (Filer)</title>
<summary type="html">&lt;br&gt;Item 5.02: Departure of Directors</summary>
<category scheme="https://www.sec.gov/" label="form type" term="8-K"/>
<id>urn:tag:sec.gov,2008:accession-number=0001045810-26-000099</id>
</entry></feed>"""

MEMBERS = {"rows": {"AAPL": {"now": ["sp500", "ndx", "r1000"]}, "NVDA": {"now": ["sp500", "ndx"]},
                    "SMLL": {"now": ["r2000"]}, "BRK.B": {"now": ["sp500"]}}}
TICKERS = {"0": {"cik_str": 320193, "ticker": "AAPL"}, "1": {"cik_str": 1045810, "ticker": "NVDA"},
           "2": {"cik_str": 42, "ticker": "SMLL"}, "3": {"cik_str": 1067983, "ticker": "BRK-B"}}


def test_watched_companies_are_index_members_with_a_cik():
    w = F.members(MEMBERS, TICKERS)
    assert w == {320193: "AAPL", 1045810: "NVDA", 1067983: "BRK.B"}       # BRK.B ↔ SEC's BRK-B; Russell 2000 only: no


def test_only_index_members_earnings_releases_are_hits():
    e = F.parse_feed(FEED)
    assert [x["accn"] for x in e] == ["0000320193-26-000024", "0000000042-26-000001", "0001045810-26-000099"]
    assert e[0]["items"] == ["2.02", "9.01"] and e[0]["cik"] == 320193
    w = F.members(MEMBERS, TICKERS)
    h = F.hits(e, w, claimed={})
    assert [(x["ticker"], x["accn"]) for x in h] == [("AAPL", "0000320193-26-000024")]   # not 5.02, not a non-member
    assert F.hits(e, w, claimed={"0000320193-26-000024": {}}) == []                   # claimed by a watcher already


def test_earnings_hours():
    et = F.ET
    assert F.in_window(dt.datetime(2026, 11, 2, 16, 30, tzinfo=et), busy=True)
    assert F.in_window(dt.datetime(2026, 11, 2, 7, 0, tzinfo=et), busy=True)
    assert not F.in_window(dt.datetime(2026, 11, 2, 12, 0, tzinfo=et), busy=True)
    assert F.in_window(dt.datetime(2026, 11, 2, 12, 0, tzinfo=et))
    assert not F.in_window(dt.datetime(2026, 11, 2, 23, 0, tzinfo=et))
    assert not F.in_window(dt.datetime(2026, 11, 7, 16, 30, tzinfo=et))                # a Saturday


def _q(end, form, accn=None):
    a = (accn or "0000320193-26-000001").replace("-", "")
    return {"end": end, "form": form, "label": end, "index_url": f"https://www.sec.gov/Archives/edgar/data/320193/{a}/x-index.htm"}


def _entry(end="2026-09-26", accn="0000320193-26-000024", at=None):
    at = at or F.stamp_now()
    return {"meta": {"cik": 320193, "accn": accn, "ticker": "AAPL", "end": end, "filed": "2026-11-02", "label": "Q4 FY26", "at": at},
            "company": {"quarters": [_q(end, "8-K", accn)]},
            "row": {"cik": 320193, "ticker": "AAPL", "label": "Q4 FY26", "end": end, "filed": "2026-11-02", "form": "8-K"}}


def test_overlay_only_where_it_is_newer_than_the_site():
    e = _entry()
    assert F.newer(e, None)                                                          # not on the site yet
    assert F.newer(e, {"quarters": [_q("2026-06-27", "10-Q")]})                      # the site still shows Q3
    assert not F.newer(e, {"quarters": [_q("2026-09-26", "8-K", "0000320193-26-000024")]})   # the scan read it
    assert not F.newer(e, {"quarters": [_q("2026-09-26", "10-K")]})                  # the 10-K is in: it wins
    assert not F.newer(e, {"quarters": [_q("2026-12-27", "8-K")]})                   # a later quarter on the site


def test_apply_lays_the_overlay_on_a_scan_that_started_before_the_release(tmp_path):
    data, lane = tmp_path / "_site" / "data", tmp_path / "lane"
    (data / "c").mkdir(parents=True)
    json.dump({"quarters": [_q("2026-06-27", "10-Q")]}, open(data / "c" / "320193.json", "w"))
    json.dump({"companies": [{"cik": 320193, "ticker": "AAPL", "filed": "2026-07-31", "form": "10-Q"},
                             {"cik": 34088, "ticker": "XOM", "filed": "2026-10-31", "form": "8-K"}]}, open(data / "index.json", "w"))
    F.save(str(lane / "overlay" / "320193.json"), _entry())
    old = (F.utcnow() - dt.timedelta(days=9)).isoformat(timespec="seconds") + "Z"
    F.save(str(lane / "overlay" / "1045810.json"), dict(_entry(at=old), meta=dict(_entry(at=old)["meta"], cik=1045810)))
    F.main(["apply", "--data", str(data), "--lane", str(lane)])
    c = json.load(open(data / "c" / "320193.json"))
    ix = json.load(open(data / "index.json"))
    assert c["quarters"][0]["end"] == "2026-09-26"
    assert [r["ticker"] for r in ix["companies"]] == ["AAPL", "XOM"]                 # newest filing first
    assert not os.path.exists(data / "c" / "1045810.json")                           # expired: the scan has it by now
    F.main(["apply", "--data", str(data), "--lane", str(lane)])                      # again: nothing changes
    assert json.load(open(data / "index.json")) == ix


def test_a_page_a_scan_took_back_is_published_again(tmp_path):
    lane = tmp_path / "lane"
    now = dt.datetime(2026, 11, 2, 22, 0)
    at = (now - dt.timedelta(minutes=30)).isoformat(timespec="seconds") + "Z"
    F.save(str(lane / "overlay" / "320193.json"), _entry(at=at))
    q3 = {"quarters": [_q("2026-06-27", "10-Q")]}
    q4 = {"quarters": [_q("2026-09-26", "8-K", "0000320193-26-000024")]}
    assert [h["ticker"] for h in F.taken_back(str(lane), {}, lambda cik: q3, now=now)] == ["AAPL"]
    assert F.taken_back(str(lane), {}, lambda cik: q4, now=now) == []                   # the live site shows it
    assert F.taken_back(str(lane), {}, lambda cik: None, now=now) == []                 # site not reachable: wait
    recent = {"0000320193-26-000024": {"re": (now - dt.timedelta(minutes=5)).isoformat(timespec="seconds") + "Z"}}
    assert F.taken_back(str(lane), recent, lambda cik: q3, now=now) == []               # published again just now
    fresh = (now - dt.timedelta(minutes=5)).isoformat(timespec="seconds") + "Z"
    F.save(str(lane / "overlay" / "320193.json"), _entry(at=fresh))
    assert F.taken_back(str(lane), {}, lambda cik: q3, now=now) == []                   # the CDN may not show it yet
