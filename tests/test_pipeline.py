"""Offline tests: run with `python -m pytest tests` (fixtures stand in for SEC endpoints)."""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline import dims, text  # noqa: E402
from pipeline.sankey import pct_change, share  # noqa: E402

DOC = """<html><body>
<div>Table of Contents</div><div>Item 1. Business</div><div>Item 1A. Risk Factors</div>
<p><b>PART I</b></p><p><b>Item 1. Business</b></p>
<p><b>Company Background</b></p>
<p>The Example Company designs and sells widgets and related services to customers in more than forty countries, through its own stores and partners.</p>
<p>The Company's fiscal year is the 52- or 53-week period that ends on the last Saturday of September, which the Company uses for all reporting.</p>
<p><b>Products</b></p>
<p>Widgets come in three sizes and are sold directly and through cellular network carriers, wholesalers, retailers and resellers worldwide.</p>
<p><b>Item 1A. Risk Factors</b></p><p>Risks.</p>
<p><b>Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations</b></p>
<p><b>Widgets</b></p>
<p>Widgets net sales increased during the quarter compared to the same quarter last year primarily due to higher demand for large widgets.</p>
<p><b>Services</b></p>
<p>Services net sales increased due to higher subscription revenue across all regions during the quarter and the first nine months.</p>
<p>Filler paragraph to give the section enough length for the parser to accept it as the real MD&amp;A body and not a table of contents line.</p>
<p><b>Item 3. Quantitative and Qualitative Disclosures About Market Risk</b></p>
</body></html>"""


def test_intro_takes_item1_paragraphs():
    it = text.intro(DOC)
    assert it.startswith("The Example Company designs")
    assert "last Saturday of September" in it


def test_notes_match_heading_exactly():
    md = text.mdna(DOC)
    n = text.match_notes(md, ["Widgets"])
    assert n and n[0]["heading"] == "Widgets" and "large widgets" in n[0]["text"]
    assert text.match_notes(md, ["Gadgets"], fallback=False) == []


def test_partition_finds_lines_that_add_up():
    members = {"a": ("A", 50.0), "b": ("B", 30.0), "c": ("C", 20.0), "ab": ("A+B", 80.0)}
    part = dims.best_partition(members, 100.0)
    assert {l["id"] for l in part["leaves"]} == {"a", "b", "c"}
    assert part["groups"][0]["members"] == ["a", "b"] or set(part["groups"][0]["members"]) == {"a", "b"}


def test_formatting_rules():
    assert pct_change(110, 100) == "+10%"
    assert pct_change(-1, 100) == "n/m"
    assert share(5, 100) == "5.0%" and share(50, 100) == "50%"


def test_fixture_run_renders_site(tmp_path):
    env = dict(os.environ, SEC_FIXTURES=os.path.join(ROOT, "tests", "fixtures"), SEC_USER_AGENT="test test@example.com")
    out = tmp_path / "data"
    subprocess.run([sys.executable, "-m", "pipeline.build", "run", "--store", str(tmp_path / "store"), "--out", str(out)],
                   cwd=ROOT, env=env, check=True, capture_output=True)
    ix = json.load(open(out / "index.json"))
    assert {c["ticker"] for c in ix["companies"]} >= {"AAPL", "META", "CRWV", "BRK-B"}
    apple = json.load(open(out / "c" / "320193.json"))
    q = apple["quarters"][0]
    iphone = next(n for n in q["nodes"] if n["name"] == "iPhone")
    assert iphone["lines"][1][1].startswith("$54.3B · 69% of Products")
    assert iphone["notes"][0]["text"].startswith("iPhone net sales increased")
    assert q["compare"]["vs"] == "Q2 FY26" and len(q["compare"]["bullets"]) == 3
    assert all(isinstance(p, str) and p for p in q["analysis"])


def test_earnings_release_8k(tmp_path):
    """Fictional companies EXDV / SMCL: quarter read from the press release tables, units, signs and YTD cash flow."""
    env = dict(os.environ, SEC_FIXTURES=os.path.join(ROOT, "tests", "fixtures"), SEC_USER_AGENT="test test@example.com")
    store = tmp_path / "store"
    subprocess.run([sys.executable, "-m", "pipeline.build", "run", "--store", str(store), "--out", str(tmp_path / "data")],
                   cwd=ROOT, env=env, check=True, capture_output=True)
    x = json.load(open(store / "companies" / "9999901.json"))["quarters"]["2026-08-30"]
    assert x["form"] == "8-K" and x["label"] == "Q4 FY26"
    want = dict(revenue=5240, cor=2870, gp=2370, oi=1110, pretax=1097, tax=165, ni=932, ocf=1600, da=520, sbc=105, capex=1100)
    assert all(abs(x["raw"][k] / 1e6 - v) < 0.01 for k, v in want.items())
    s = json.load(open(store / "companies" / "9999902.json"))["quarters"]["2026-06-30"]
    want = dict(revenue=412.5, oi=-41.1, pretax=-50.3, tax=1.2, pl=-51.5, ni=-51.0, nci=-0.5, ocf=36, capex=65)
    assert all(abs(s["raw"][k] / 1e6 - v) < 0.01 for k, v in want.items())
    seen = json.load(open(store / "state.json"))["seen"]
    assert "0009999901-26-000046" not in seen                     # Item 5.02 8-K is never queued
    page = json.load(open(tmp_path / "data" / "c" / "9999901.json"))["quarters"][0]
    assert page["preliminary"] and "earnings release" in page["subtitle"]


def _statement(header_cells, rows, text=""):
    cell = lambda v: f"<td>$</td><td>({-v:,}</td><td>)</td>" if v < 0 else f"<td>$</td><td>{v:,}</td><td></td>"
    head = "".join(f"<tr><td></td>{''.join(f'<td colspan=3>{h}</td>' for h in hr)}</tr>" for hr in header_cells)
    body = "".join(f"<tr><td>{lab}</td>{''.join(cell(v) for v in vals)}</tr>" for lab, vals in rows)
    return f"<p>{text}</p><p>(in thousands)</p><table>{head}{body}</table>"


FULL_YEAR = [("Revenue", [23300, 20100]), ("Cost of revenue", [3300, 3000]), ("Gross profit", [20000, 17100]),
             ("Operating income", [7800, 6000]), ("Income before income taxes", [9500, 7000]),
             ("Provision for income taxes", [1900, 1400]), ("Net income", [7600, 5600])]


def test_release_full_year_is_not_a_quarter():
    """ReposiTrak-type case: an annual release must not be read as a quarter ending on some other date in the text."""
    import datetime as dt
    from pipeline import release
    html = _statement([["Year Ended June 30,"], ["2026", "2025"]], FULL_YEAR,
                      "Annual results. The company will host a conference call on September 28, 2026.")
    try:
        release.parse(html, dt.date(2026, 9, 30), dt.date(2026, 6, 30), prior_revenue=5.6e6)
        raise AssertionError("an annual table was accepted as a quarter")
    except ValueError as e:
        assert "previous quarter" in str(e)
    rel = release.parse(html, dt.date(2026, 9, 30), dt.date(2026, 6, 30), prior_revenue=None)
    assert rel["end"] == "2026-06-30"            # the header date; the build then skips it as already filed


def test_release_end_must_precede_filing():
    """EQUATOR-type case: a 'quarter' ending the day before the 8-K was filed is not a results release."""
    import datetime as dt
    from pipeline import release
    html = _statement([["Three Months Ended September 30,"], ["2026", "2025"]], FULL_YEAR)
    try:
        release.parse(html, dt.date(2026, 10, 1), dt.date(2026, 6, 30), prior_revenue=None)
        raise AssertionError("accepted a period that ended one day before filing")
    except ValueError as e:
        assert "quarter end" in str(e)


def test_cash_flow_reading_checked_against_prior_quarter():
    """Jabil-type case: a year-to-date cash-flow table whose header looks quarterly is still read as year-to-date."""
    from pipeline import build, facts
    fx = facts.index_facts(json.load(open(os.path.join(ROOT, "tests", "fixtures",
                                                       "data.sec.gov_api_xbrl_companyfacts_CIK0009999901.json"))))
    rel = {"cf": {"ocf": 5600e6, "da": 2000e6, "sbc": 400e6, "capex": -4000e6}, "cf_quarter": True}
    q = build._release_cash(rel, fx, "2026-05-31", 4)
    assert abs(q["da"] - 520e6) < 1 and abs(q["ocf"] - 1600e6) < 1 and abs(q["capex"] - 1100e6) < 1


def test_release_must_match_filed_columns():
    """A release whose earlier columns disagree with XBRL (wrong column, units or period) is rejected."""
    from pipeline import release
    rel = {"scale": 1e6, "cols": {"revenue": [5240e6, 4610e6, 3900e6], "pl": [932e6, 657e6, 404e6]}}
    ref_q1 = {"revenue": 4610e6, "ni": 657e6, "pl": None}
    assert release.anchor(rel, {"q1": ref_q1, "py": None}) == "q1"
    wrong = {"revenue": 4100e6, "ni": 600e6, "pl": None}
    try:
        release.anchor(rel, {"q1": wrong, "py": None})
        raise AssertionError("accepted a release that disagrees with the filed quarter")
    except ValueError:
        pass
    try:                                                     # the "new" quarter is one already filed
        release.anchor(rel, {"q1": ref_q1}, current_ref={"revenue": 5240e6, "ni": 932e6, "pl": None})
        raise AssertionError("accepted figures that were already filed")
    except ValueError:
        pass


def test_audit_compares_release_with_10q():
    from pipeline import build
    st = {}
    old = {"accn": "x", "raw": {"revenue": 5240e6, "oi": 1110e6, "ni": 932e6, "ocf": 1600e6}}
    build.audit_release(st, 1, old, {"revenue": 5240e6, "oi": 1110e6, "ni": 932e6, "ocf": 1600e6}, "2026-08-30")
    build.audit_release(st, 1, old, {"revenue": 5240e6, "oi": 1110e6, "ni": 932e6, "ocf": 1200e6}, "2026-08-30")
    assert [a["ok"] for a in st["audit"]] == [True, False]
    assert st["audit"][1]["fields"]["ocf"][2] is False
    rc = build.release_check(dict(old, filed="2026-09-24"), {"revenue": 5240e6, "oi": 1110e6, "ni": 932e6, "ocf": 1200e6})
    assert rc["filed"] == "2026-09-24" and rc["ok"] is False
    assert [(f["name"], f["ok"]) for f in rc["fields"]] == [("Revenue", True), ("Operating profit", True),
                                                          ("Net earnings", True), ("Operating cash flow", False)]


def _site(tmp_path):
    env = dict(os.environ, SEC_FIXTURES=os.path.join(ROOT, "tests", "fixtures"), SEC_USER_AGENT="test test@example.com")
    subprocess.run([sys.executable, "-m", "pipeline.build", "run", "--store", str(tmp_path / "store"),
                    "--out", str(tmp_path / "site" / "data")], cwd=ROOT, env=env, check=True, capture_output=True)
    subprocess.run([sys.executable, "scripts/build_site.py", "--data", str(tmp_path / "site" / "data"),
                    "--out", str(tmp_path / "site")], cwd=ROOT, check=True, capture_output=True)
    return tmp_path / "site"


def test_social_threads_fit_and_cite(tmp_path):
    import datetime as dt
    from pipeline import social
    site = _site(tmp_path)
    cfg = dict(social.DEFAULTS, min_revenue=0, max_age_days=10000, max_per_run=50)
    todo = social.candidates(str(site), {"posted": {}}, cfg, today=dt.date(2026, 10, 2))
    assert len(todo) == 6
    for e in todo:
        c, q = social.quarter_of(str(site), e)
        c["intro"] = {"text": "Example text. " * 60, "filed": "2025-10-27"}
        posts = social.compose(c, q, cfg)
        assert all(social.xlen(p) <= 280 for p in posts), [social.xlen(p) for p in posts]
        assert posts[0].startswith("$") and "Revenue" in posts[0]
        assert posts[1].startswith("About ") and "” — 10-K filed Oct 27, 2025, Item 1" in posts[1]
        assert posts[-1].startswith("Source: SEC EDGAR") and "http" not in posts[-1]
    brk = next(e for e in todo if e["cik"] == 1067983)
    assert social.compose(*social.quarter_of(str(site), brk), cfg)[0].startswith("$BRK.B ")


def test_social_posts_thread_in_order_and_never_twice(tmp_path):
    from pipeline import social
    calls = []

    class Resp:
        def __init__(self, data):
            self.status_code, self._d, self.text = 200, data, ""

        def json(self):
            return self._d

    class Session:
        def post(self, url, **kw):
            calls.append((url.rsplit("/", 1)[-1], kw.get("json")))
            return Resp({"data": {"id": f"id{len(calls)}"}})

    x = social.X.__new__(social.X)
    x.auth, x.s = None, Session()
    ids = social.post_thread(x, ["one", "two", "three"], [b"png1", b"png2"])
    assert [c[0] for c in calls] == ["upload", "upload", "tweets", "tweets", "tweets"]
    assert calls[2][1]["media"]["media_ids"] == ["id1", "id2"] and "reply" not in calls[2][1]
    assert calls[3][1]["reply"]["in_reply_to_tweet_id"] == ids[0] and calls[4][1]["reply"]["in_reply_to_tweet_id"] == ids[1]
    st = {"posted": {"9999901:2026-08-30": {}}}                     # the 8-K was posted ...
    assert social.posted_already(st, 9999901, "2026-08-30") and social.posted_already(st, 9999901, "2026-09-01")
    assert not social.posted_already(st, 9999901, "2026-05-31")    # ... a different quarter is not blocked


def test_social_renders_chart_png(tmp_path):
    from pipeline import social
    site = _site(tmp_path)
    c = json.load(open(site / "data" / "c" / "320193.json"))
    pngs = social.render_charts(str(site), [(c["quarters"][0], None), (c["quarters"][0], "y")])
    assert len(pngs) == 2 and all(p.startswith(b"\x89PNG") and len(p) > 100_000 for p in pngs)


def test_social_email_digest(tmp_path):
    import datetime as dt
    import smtplib
    from pipeline import social
    site = _site(tmp_path)
    cfg = dict(social.DEFAULTS, min_revenue=0, max_age_days=10000, max_per_run=3, site_url="https://example.github.io/ff/")
    items = []
    for e in social.candidates(str(site), {"posted": {}}, cfg, today=dt.date(2026, 10, 2)):
        c, q = social.quarter_of(str(site), e)
        items.append((e, c, q, social.compose(c, q, cfg), list(zip(social.image_names(e, q, 2), [b"\x89PNG" + b"0" * 900_000] * 2))))
    msg = social.build_email(items, cfg, "me@example.com", "me@example.com")
    assert msg["Subject"].startswith("Filing Flows: 3 new charts ready to post")
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert html.count("<pre") == sum(len(i[3]) for i in items) and "x.com/intent/post?text=" in html
    assert len(list(msg.iter_attachments())) == 6
    assert [len(b) for b in social.batches(items, max_bytes=2_000_000)] == [1, 1, 1]
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent.append(host)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def login(self, u, p):
            sent.append(u)

        def send_message(self, m):
            sent.append(m["To"])
    real, smtplib.SMTP_SSL = smtplib.SMTP_SSL, FakeSMTP
    try:
        social.send_email(msg, "me@example.com", "app-password")
    finally:
        smtplib.SMTP_SSL = real
    assert sent == ["smtp.gmail.com", "me@example.com", "me@example.com"]


def test_social_send_one_on_request(tmp_path, monkeypatch=None):
    """The site's "Email me this thread" request: one quarter, both charts attached, regardless of earlier sends."""
    import smtplib
    from pipeline import social
    site = _site(tmp_path)
    got = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def login(self, u, p):
            pass

        def send_message(self, m):
            got.append(m)
    real, smtplib.SMTP_SSL = smtplib.SMTP_SSL, FakeSMTP
    os.environ.update(MAIL_USERNAME="me@example.com", MAIL_PASSWORD="x")
    try:
        social.send_one(str(site), dict(social.DEFAULTS), "320193", "2026-06-27")
    finally:
        smtplib.SMTP_SSL = real
        del os.environ["MAIL_USERNAME"], os.environ["MAIL_PASSWORD"]
    names = [p.get_filename() for p in got[0].iter_attachments()]
    assert got[0]["Subject"].endswith("AAPL") and names == ["AAPL-Q3-FY26-1-chart.png", "AAPL-Q3-FY26-2-vs-Q3-FY25.png"]


# ------------------------------------------------------------------ reader alerts (pipeline/notify.py)
class _FakeSupa:
    """Supabase REST stand-in: eq / in / lt / gte / is filters, insert that ignores duplicates, PATCH that returns rows."""
    def __init__(self, subs, dels=(), requests=()):
        self.t = {"subscriptions": [dict(r) for r in subs], "deliveries": [dict(r) for r in dels],
                  "send_requests": [dict(r) for r in requests]}
        self.deleted = []

    @property
    def dels(self):
        return self.t["deliveries"]

    @staticmethod
    def _match(row, params):
        for k, v in params.items():
            if k in ("select", "order", "limit", "offset"):
                continue
            op, _, val = v.partition(".")
            cur = row.get(k)
            if op == "eq" and str(cur) != val:
                return False
            if op == "in" and str(cur) not in val.strip("()").split(","):
                return False
            if op == "is" and cur is not (val == "true"):
                return False
            if op in ("lt", "gte") and (cur is None or not (str(cur) < val if op == "lt" else str(cur) >= val)):
                return False
        return True

    def select(self, table, params):
        return [dict(r) for r in self.t[table] if self._match(r, params)]

    def insert(self, table, rows):
        have = {(d["user_id"], d["item"]) for d in self.t[table]}
        self.t[table] += [dict(r) for r in rows if (r["user_id"], r["item"]) not in have]

    def update(self, table, params, fields):
        out = []
        for r in self.t[table]:
            if self._match(r, params):
                r.update(fields)
                out.append(dict(r))
        return out

    def delete(self, table, params):
        self.deleted.append(params)


class _FakeMailer:
    def __init__(self):
        self.sent = []

    def send(self, m):
        self.sent.append(m)

    def close(self):
        pass


def _sub(uid, **kw):
    row = {"user_id": uid, "email": f"{uid}@example.com", "tickers": [], "sectors": [], "all_above": False,
           "min_revenue": 1_000_000_000, "starred": False, "frequency": "instant", "email_on": True,
           "unsub_token": f"00000000-0000-4000-8000-{uid.encode().hex()[:12]:0>12}", "created_at": "2026-07-01T00:00:00+00:00"}
    row.update(kw)
    return row


def test_notify_matches_follows_and_sends_once(tmp_path):
    import datetime as dt
    from pipeline import notify
    site = _site(tmp_path)
    subs = [
        _sub("ann", tickers=["aapl"]),                                     # instant, one company
        _sub("bea", sectors=["technology"], frequency="daily"),            # daily digest of a sector
        _sub("cal", all_above=True, min_revenue=50_000_000_000),           # every company >= $50B
        _sub("dan", tickers=["META"]),                                     # already got META
        _sub("eve", tickers=["AAPL"], email_on=False),                     # unsubscribed
        _sub("fay", tickers=["AAPL"], created_at="2026-09-20T00:00:00+00:00"),   # signed up after the filing
        _sub("gus", tickers=["BRK.B"]),                                    # dots and dashes are the same ticker
    ]
    supa = _FakeSupa(subs, [{"user_id": "dan", "item": "1326801:2026-06-30", "sent_at": "2026-07-31T12:00:00+00:00"}])
    mail = _FakeMailer()
    notify.MAX_AGE_DAYS = 100
    try:
        afternoon = dt.datetime(2026, 9, 25, 15, 0, tzinfo=dt.timezone.utc)
        n = notify.run(notify.Site(site), supa, mail, "Filing Flows <me@example.com>", "https://ex.github.io/ff",
                       now=afternoon, images=False, hour=22, daily_limit=100)
        got = {m["To"].split("@")[0]: m for m in mail.sent}
        assert n == 3 and sorted(got) == ["ann", "cal", "gus"], sorted(got)
        assert got["ann"]["Subject"].startswith("AAPL Q3 FY26: revenue $")
        assert got["gus"]["Subject"].startswith("BRK-B ")
        body = got["ann"].get_body(("html",)).get_content()
        assert "Why you got this: you follow AAPL" in body and "#unsubscribe-00000000-0000-4000-8000-" in body
        assert "https://ex.github.io/ff/#c-320193-" in body and "What changed vs" in body
        assert got["ann"]["List-Unsubscribe"].startswith("<https://ex.github.io/ff/#unsubscribe-")
        cal = {k.split(":")[0] for k in (d["item"] for d in supa.dels if d["user_id"] == "cal")}
        assert cal == {"320193", "1326801", "1067983"}, cal                  # Apple, Meta, Berkshire
        # the same run again sends nothing; the daily digest waits for its hour and then goes out once
        mail.sent.clear()
        assert notify.run(notify.Site(site), supa, mail, "x", "", now=afternoon, images=False, hour=22, daily_limit=100) == 0
        evening = afternoon.replace(hour=22, minute=20)
        assert notify.run(notify.Site(site), supa, mail, "x", "", now=evening, images=False, hour=22, daily_limit=100) == 1
        assert mail.sent[0]["To"] == "bea@example.com" and mail.sent[0]["Subject"].startswith("Your daily charts: ")
        assert notify.run(notify.Site(site), supa, mail, "x", "", now=evening.replace(hour=23), images=False, hour=22, daily_limit=100) == 0
        # 8-K and 10-Q charts of one quarter are different items; final_too off skips the 10-Q after a sent 8-K
        got = {"9999901:2026-08-30:8-K": "2026-09-24T21:00:00+00:00"}
        tenq = {"cik": 9999901, "end": "2026-08-30", "form": "10-Q"}
        assert notify.delivered(got, {"cik": 9999901, "end": "2026-08-30", "form": "8-K"})
        assert not notify.delivered(got, tenq) and notify.delivered(got, tenq, final_too=False)
        assert notify.delivered(got, dict(tenq, end="2026-09-01"), final_too=False)
        assert not notify.delivered({"9999901:2026-05-31:8-K": "x"}, tenq, final_too=False)
        # the 24-hour sending limit holds the rest back
        supa2, mail2 = _FakeSupa([_sub("h1", tickers=["AAPL"]), _sub("h2", tickers=["AAPL"])]), _FakeMailer()
        assert notify.run(notify.Site(site), supa2, mail2, "x", "", now=afternoon, images=False, hour=22, daily_limit=1) == 1
    finally:
        notify.MAX_AGE_DAYS = 3


def test_notify_email_has_inline_chart(tmp_path):
    import datetime as dt
    from pipeline import notify
    site = _site(tmp_path)
    supa, mail = _FakeSupa([_sub("ann", tickers=["AAPL", "META"])]), _FakeMailer()
    notify.MAX_AGE_DAYS = 100
    try:
        notify.run(notify.Site(site), supa, mail, "x", "https://ex.github.io/ff",
                   now=dt.datetime(2026, 9, 25, 15, tzinfo=dt.timezone.utc), hour=22, daily_limit=10)
    finally:
        notify.MAX_AGE_DAYS = 3
    m = mail.sent[0]
    imgs = [p for p in m.walk() if p.get_content_type() == "image/jpeg"]
    html = m.get_body(("html",)).get_content()
    assert len(imgs) == 2 and all(p.get_content().startswith(b"\xff\xd8\xff") for p in imgs)
    assert all(f'cid:{p["Content-ID"][1:-1]}' in html for p in imgs)
    assert sum(len(p.get_content()) for p in imgs) < 2_000_000
    open(tmp_path / "alert.eml", "wb").write(bytes(m))


def test_notify_supabase_rest_paging_and_keys():
    from pipeline import notify
    calls = []

    class R:
        def __init__(self, data=None, code=200):
            self._d, self.status_code, self.text = data, code, ""

        def json(self):
            return self._d

    class S:
        def get(self, url, params=None, headers=None, timeout=None):
            calls.append(("get", url, params, headers))
            rows = [{"i": i} for i in range(5)]
            off, lim = int(params["offset"]), int(params["limit"])
            return R(rows[off:off + lim])

        def post(self, url, data=None, headers=None, timeout=None):
            calls.append(("post", url, data, headers))
            return R(None, 201)

    sb = notify.Supa("https://p.supabase.co/", "sb_secret_abc", session=S())
    sb.PAGE = 2
    assert [r["i"] for r in sb.select("deliveries", {"select": "*"})] == [0, 1, 2, 3, 4]
    assert calls[0][1] == "https://p.supabase.co/rest/v1/deliveries" and len(calls) == 3
    assert calls[0][3]["apikey"] == "sb_secret_abc" and "Authorization" not in calls[0][3]
    sb.insert("deliveries", [{"user_id": "u", "item": "1:2026-06-30"}])
    assert "ignore-duplicates" in calls[-1][3]["Prefer"]
    legacy = notify.Supa("https://p.supabase.co", "eyJhbGciOi.x.y", session=S())
    legacy.select("subscriptions", {})
    assert calls[-1][3]["Authorization"] == "Bearer eyJhbGciOi.x.y"


def _as_final_10q(site):
    """Turn the fixture's EXDV 8-K quarter into the 10-Q that replaced it (with the release check the build records)."""
    cpath, ipath = site / "data" / "c" / "9999901.json", site / "data" / "index.json"
    c, ix = json.load(open(cpath)), json.load(open(ipath))
    q = c["quarters"][0]
    q.update(form="10-Q", filed="2026-10-01", preliminary=False, release_check={
        "filed": "2026-09-24", "accn": "x", "ok": False, "fields": [
            {"key": "revenue", "name": "Revenue", "release": 5.24e9, "final": 5.24e9, "ok": True},
            {"key": "ni", "name": "Net earnings", "release": 9.32e8, "final": 9.32e8, "ok": True},
            {"key": "ocf", "name": "Operating cash flow", "release": 1.6e9, "final": 1.2e9, "ok": False}]})
    e = next(x for x in ix["companies"] if x["cik"] == 9999901)
    e.update(form="10-Q", filed="2026-10-01", prelim=False, after_release="2026-09-24", release_ok=False)
    json.dump(c, open(cpath, "w"))
    json.dump(ix, open(ipath, "w"))


def test_notify_final_10q_after_8k_is_optional_and_labelled(tmp_path):
    import datetime as dt
    from pipeline import notify
    site = _site(tmp_path)
    _as_final_10q(site)
    got = [{"user_id": u, "item": "9999901:2026-08-30:8-K", "sent_at": "2026-09-24T21:17:00+00:00"} for u in ("ann", "bob")]
    supa = _FakeSupa([_sub("ann", tickers=["EXDV"]), _sub("bob", tickers=["EXDV"], final_too=False)], got)
    mail = _FakeMailer()
    now = dt.datetime(2026, 10, 1, 21, 30, tzinfo=dt.timezone.utc)
    assert notify.run(notify.Site(site), supa, mail, "x", "https://ex.github.io/ff", now=now, images=False,
                      hour=22, daily_limit=50) == 1
    m = mail.sent[0]
    assert m["To"] == "ann@example.com" and m["Subject"].endswith("(final 10-Q)"), m["Subject"]
    body = m.get_body(("plain",)).get_content()
    assert "You received the preliminary chart from the earnings release (8-K) on Sep 24, 2026." in body
    assert "Revenue and net earnings match the release. Revised: operating cash flow $1.6B in the release, $1.2B as filed." in body
    assert "· final" in body.split("\n")[3]
    assert {d["item"] for d in supa.dels if d["user_id"] == "ann"} == {"9999901:2026-08-30:8-K", "9999901:2026-08-30"}


def test_notify_sends_reports_readers_ask_for(tmp_path):
    import datetime as dt
    from pipeline import notify
    site = _site(tmp_path)
    reqs = [
        {"id": 1, "user_id": "ann", "cik": 320193, "period_end": "2026-06-27", "status": "pending", "attempts": 0, "created_at": "2026-10-02T10:00:00+00:00"},
        {"id": 2, "user_id": "ann", "cik": 1326801, "period_end": "2026-06-30", "status": "pending", "attempts": 0, "created_at": "2026-10-02T10:00:01+00:00"},
        {"id": 3, "user_id": "ann", "cik": 320193, "period_end": "2019-12-28", "status": "pending", "attempts": 0, "created_at": "2026-10-02T10:00:02+00:00"},
        {"id": 4, "user_id": "zed", "cik": 320193, "period_end": "2026-06-27", "status": "pending", "attempts": 0, "created_at": "2026-10-02T10:00:03+00:00"},
        {"id": 5, "user_id": "cat", "cik": 9999901, "period_end": "2026-08-30", "status": "pending", "attempts": 0, "created_at": "2026-10-02T10:00:04+00:00"},
    ]
    subs = [_sub("ann", email_on=False), _sub("cat")]                 # ann turned alerts off: asking still works
    supa, mail = _FakeSupa(subs, (), reqs), _FakeMailer()
    now = dt.datetime(2026, 10, 2, 10, 5, tzinfo=dt.timezone.utc)
    n = notify.run(notify.Site(site), supa, mail, "x", "https://ex.github.io/ff", now=now, images=False,
                   hour=22, daily_limit=50, requests_only=True)
    st = {r["id"]: r for r in supa.t["send_requests"]}
    assert n == 2 and [m["To"] for m in mail.sent] == ["ann@example.com", "cat@example.com"]
    assert mail.sent[0]["Subject"] == "Your reports: AAPL Q3 FY26, META Q2 2026"
    assert "The 2 reports you asked for." in mail.sent[0].get_body(("plain",)).get_content()
    assert "Why you got this: you asked for this report." in mail.sent[0].get_body(("plain",)).get_content()
    assert [st[i]["status"] for i in (1, 2, 3, 4, 5)] == ["sent", "sent", "failed", "failed", "sent"]
    assert st[3]["error"] == "that quarter is no longer on the site" and st[4]["error"].startswith("no e-mail")
    # nothing left: a second run sends nothing
    mail.sent.clear()
    assert notify.run(notify.Site(site), supa, mail, "x", "", now=now, images=False, hour=22, daily_limit=50,
                      requests_only=True) == 0
    # the mail server refuses: the request goes back to waiting, and fails after three tries
    class Broken(_FakeMailer):
        def send(self, m):
            raise OSError("smtp down")
    supa.t["send_requests"].append({"id": 6, "user_id": "cat", "cik": 320193, "period_end": "2026-06-27",
                                    "status": "pending", "attempts": 0, "created_at": "2026-10-02T10:06:00+00:00"})
    for want in ("pending", "pending", "failed"):
        notify.run(notify.Site(site), supa, Broken(), "x", "", now=now, images=False, hour=22, daily_limit=50, requests_only=True)
        assert supa.t["send_requests"][-1]["status"] == want
    # a request a crashed run left "sending" for more than half an hour is picked up again
    supa.t["send_requests"].append({"id": 7, "user_id": "cat", "cik": 320193, "period_end": "2026-06-27", "status": "sending",
                                    "attempts": 0, "claimed_at": "2026-10-02T09:00:00+00:00", "created_at": "2026-10-02T09:00:00+00:00"})
    mail.sent.clear()
    assert notify.run(notify.Site(site), supa, mail, "x", "", now=now, images=False, hour=22, daily_limit=50,
                      requests_only=True) == 1
