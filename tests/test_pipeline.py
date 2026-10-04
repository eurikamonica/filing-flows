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
    out = out_dir = tmp_path / "data"
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
    # operating cash flow splits into capital expenditures and free cash flow
    by = {n["id"]: n for n in q["nodes"]}
    assert abs(by["fcf"]["v"] - (by["ocf"]["v"] - by["capex"]["v"])) < 1 and by["ocf"]["pos"] == "above"
    out = {l["t"]: l["v"] for l in q["links"] if l["s"] == "ocf"}
    assert set(out) == {"fcf", "capex"} and abs(sum(out.values()) - by["ocf"]["v"]) < 1
    assert by["fcf"]["lines"][1][1].endswith("of OCF") and any("FCF margin" in l[1] for l in by["fcf"]["lines"])
    # capex larger than operating cash flow: all of OCF goes to capex, the gap enters as negative free cash flow
    smcl = json.load(open(out_dir / "c" / "9999902.json"))["quarters"][0]
    sb = {n["id"]: n for n in smcl["nodes"]}
    into = {l["s"]: l["v"] for l in smcl["links"] if l["t"] == "capex"}
    assert "fcf" not in sb and set(into) == {"ocf", "fcf_neg"}
    assert abs(into["ocf"] - sb["ocf"]["v"]) < 1 and abs(sum(into.values()) - sb["capex"]["v"]) < 1


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
        parts = social.compose_parts(c, q, cfg)
        posts = [x["text"] for x in parts]
        n = len(posts)
        assert all(social.xlen(p) <= 280 for p in posts), [social.xlen(p) for p in posts]
        assert posts[0].startswith("$") and "Revenue" in posts[0] and f" filed {social.fdate(q['filed'])}" in posts[0]
        assert "Chart" in posts[0].split("\n\n")[-2]                       # what the attached images show
        assert all(p.endswith(f"\n\n{i + 1}/{n}") for i, p in enumerate(posts))
        about = next(p for p in posts if p.startswith("About "))
        assert "in its own words (10-K filed Oct 27, 2025, Item 1):\n“" in about
        roles = [x["role"] for x in parts]
        assert roles[0] == "headline" and roles[-1] == "source" and "analysis" in roles
        assert posts[-1].startswith(f"Source: {social.display_name(c['profile']['name'])} ") and "http" not in posts[-1]
        assert " #earnings" in posts[0].split("\n")[0] and " results" not in posts[0].split("\n")[0]   # the headline tag
        tagged = [i for i, p in enumerate(posts) if f"\n\n#stocks #investing\n\n{i + 1}/{n}" in p]          # the general tags
        assert len(tagged) == 1 and tagged[0] > 0 and (tagged[0] == n - 1 or social.xlen(posts[-1]) > 250), tagged
        assert sum(p.count("#earnings") for p in posts) == 1
        if social.revenue_mix(q):
            biz = posts[roles.index("business")]
            assert biz.startswith("What ") and "Industry: " in biz and "revenue came from:" in biz
    brk = next(e for e in todo if e["cik"] == 1067983)
    assert social.compose(*social.quarter_of(str(site), brk), cfg)[0].startswith("$BRK.B ")
    # hashtags come from config/x.json: cleaned, no repeats, none at all when switched off
    assert social.hashtags(["stocks", "#Stocks", "#S&P 500!", "#2026", ""]) == ["#stocks", "#SP500"]
    assert social.hashtags("#a, b") == ["#a", "#b"]
    plain = social.compose(*social.quarter_of(str(site), brk), dict(cfg, headline_tag="", hashtags=[]))
    assert " results" in plain[0].split("\n")[0] and not any("#" in p.replace("#c-", "") for p in plain)


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
    def __init__(self, subs, dels=(), requests=(), **tables):
        self.t = {"subscriptions": [dict(r) for r in subs], "deliveries": [dict(r) for r in dels],
                  "send_requests": [dict(r) for r in requests], **{k: [dict(r) for r in v] for k, v in tables.items()}}
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
        _sub("bea", sectors=["technology"], frequency="daily", tz="Asia/Shanghai", digest_hour=8),   # daily report, 8:00 Shanghai
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
        # the same run again sends nothing; the daily report waits for 8:00 in the reader's time zone, then goes out once
        mail.sent.clear()
        assert notify.run(notify.Site(site), supa, mail, "x", "", now=afternoon, images=False, daily_limit=100) == 0
        morning = dt.datetime(2026, 9, 26, 0, 20, tzinfo=dt.timezone.utc)          # 8:20 in Shanghai
        assert notify.run(notify.Site(site), supa, mail, "x", "", now=morning, images=False, daily_limit=100) == 1
        m = mail.sent[0]
        assert m["To"] == "bea@example.com" and m["Subject"].startswith("Your daily report, Sep 26: "), m["Subject"]
        body = m.get_body(("plain",)).get_content()
        assert body.startswith("Your daily report for Saturday, September 26, 2026: ") and "In this report:" in body
        assert "What the company does:" in body and "Industry: Electronic Computers (Technology sector)" in body
        assert notify.run(notify.Site(site), supa, mail, "x", "", now=morning.replace(hour=1), images=False, daily_limit=100) == 0
        # the window: a report that could not go out by noon waits for the next morning
        sub = {"frequency": "daily", "tz": "Asia/Shanghai", "digest_hour": 8}
        assert notify.is_due(sub, None, dt.datetime(2026, 9, 26, 3, 59, tzinfo=dt.timezone.utc))
        assert not notify.is_due(sub, None, dt.datetime(2026, 9, 26, 4, 1, tzinfo=dt.timezone.utc))
        assert not notify.is_due(sub, None, dt.datetime(2026, 9, 25, 23, 59, tzinfo=dt.timezone.utc))
        assert notify.is_due(dict(sub, tz=None), None, dt.datetime(2026, 9, 26, 12, 30, tzinfo=dt.timezone.utc))   # New York
        assert notify.is_due(dict(sub, tz="Not/AZone"), None, dt.datetime(2026, 9, 26, 12, 30, tzinfo=dt.timezone.utc))
        # across a clock change: 8:00 in New York is 13:00 UTC in winter
        assert notify.local_slot(dt.datetime(2026, 11, 2, 13, 30, tzinfo=dt.timezone.utc), 8, "America/New_York").hour == 13
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
    assert st[3]["error"] == "that period is no longer on the site" and st[4]["error"].startswith("no e-mail")
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


def test_settings_forgive_pasted_names_and_rest_path(monkeypatch=None):
    import os
    from pipeline import notify
    old = {k: os.environ.get(k) for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY")}
    try:
        os.environ["SUPABASE_URL"] = "SUPABASE_URL = https://abc.supabase.co/rest/v1/"
        assert notify.setting("SUPABASE_URL", url=True) == "https://abc.supabase.co"
        os.environ["SUPABASE_URL"] = "https://abc.supabase.co"
        assert notify.setting("SUPABASE_URL", url=True) == "https://abc.supabase.co"
        os.environ["SUPABASE_SERVICE_KEY"] = " SUPABASE_SERVICE_KEY: 'sb_secret_xyz'\n"
        assert notify.setting("SUPABASE_SERVICE_KEY") == "sb_secret_xyz"
        os.environ["SUPABASE_SERVICE_KEY"] = "eyJhbGciOiJIUzI1NiJ9.e30.sig"
        assert notify.setting("SUPABASE_SERVICE_KEY") == "eyJhbGciOiJIUzI1NiJ9.e30.sig"
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v



def test_email_extra_charts_and_attachments_follow_preferences():
    import email
    from pipeline import notify
    c = {"profile": {"name": "Apple Inc.", "cik": 320193, "tickers": ["AAPL"]},
         "quarters": [{"end": "2026-06-27", "label": "Q3 FY26", "form": "10-Q", "filed": "2026-07-31", "nodes": [],
                       "headline": {"revenue": 109.4e9, "rev_fmt": "$109.4B", "yoy": 16.4, "ni": 29.8e9, "ni_fmt": "$29.8B", "om": 32.6},
                       "analysis": ["Revenue was $109.4B."],
                       "compare": {"vs": "Q2 FY26", "bullets": ["Revenue fell $1.8B versus Q2 FY26."]},
                       "compare_y": {"vs": "Q3 FY25", "bullets": ["Revenue rose $15.4B versus Q3 FY25."]}},
                      {"end": "2026-03-28", "label": "Q2 FY26", "form": "10-Q", "filed": "2026-05-01", "nodes": [],
                       "headline": {"revenue": 111.2e9, "yoy": 17, "ni": 29.6e9, "om": 32.3}}]}
    q = c["quarters"][0]
    e = {"cik": 320193, "end": q["end"], "form": "10-Q", "ticker": "AAPL", "name": "Apple Inc.", "rev": "$109.4B"}
    sub = {"email": "r@example.com", "unsub_token": "t", "chart_q": True, "chart_y": False, "chart_history": True,
           "attach_images": "jpg", "attach_pdf": True}
    assert notify.views_for(sub, c, q) == ["std", "q", "h"]
    assert notify.views_for({}, c, q) == ["std"]
    k = notify.item_key(e)
    extras = {k: {"inline": {"q": b"Q" * 100, "h": b"H" * 100},
                  "files": [("AAPL-Q3-FY26-report.pdf", b"%PDF" * 50, "application", "pdf"),
                            ("AAPL-Q3-FY26-sankey.jpg", b"J" * 300, "image", "jpeg")]}}
    msg = notify.build_message(sub, [(e, c, q, ["you asked for this report"])], "https://x.io/ff", {k: b"S" * 100},
                               "FF <a@b.c>", requested=True, extras=extras)
    m = email.message_from_bytes(msg.as_bytes())
    parts = [(p.get_content_type(), p.get_content_disposition(), p.get_filename()) for p in m.walk()]
    inline = [x for x in parts if x[1] == "inline"]
    attached = [x[2] for x in parts if x[1] == "attachment"]
    assert len(inline) == 3, parts                          # this quarter + vs previous quarter + history
    assert attached == ["AAPL-Q3-FY26-report.pdf", "AAPL-Q3-FY26-sankey.jpg"], attached
    html = [p for p in m.walk() if p.get_content_type() == "text/html"][0].get_payload(decode=True).decode()
    assert "What changed vs Q2 FY26" in html and "Quarter by quarter" in html and "Attached: AAPL-Q3-FY26-report.pdf" in html
    assert "#c-320193-all" in html

    os.environ["MAIL_MAX_BYTES"] = "520"                     # room for the pictures (300) and the PDF (200), not the image file
    try:
        msg = notify.build_message(sub, [(e, c, q, ["x"])], "https://x.io/ff", {k: b"S" * 100}, "FF <a@b.c>",
                                   requested=True, extras=extras)
    finally:
        del os.environ["MAIL_MAX_BYTES"]
    m = email.message_from_bytes(msg.as_bytes())
    attached = [p.get_filename() for p in m.walk() if p.get_content_disposition() == "attachment"]
    assert attached == ["AAPL-Q3-FY26-report.pdf"], attached
    assert "Some files were left out" in m.as_string()


def test_report_html_has_profile_charts_and_analysis():
    from pipeline import notify
    c = {"profile": {"name": "NIKE, Inc.", "cik": 320187, "tickers": ["NKE"], "exchanges": ["NYSE"], "sic": "3021",
                     "industry": "Rubber & Plastics Footwear", "fye": "0531", "category": "Large accelerated filer"},
         "intro": {"text": "NIKE, Inc. was incorporated in 1967 under the laws of the State of Oregon.", "filed": "2025-07-17"},
         "quarters": [{"end": "2026-08-31", "label": "Q1 FY27", "form": "10-Q", "filed": "2026-10-02", "nodes": [],
                       "index_url": "https://www.sec.gov/Archives/edgar/data/320187/000032018726000045/0000320187-26-000045-index.htm",
                       "headline": {"revenue": 11.2e9, "rev_fmt": "$11.2B", "yoy": -4, "ni": 0.71e9, "ni_fmt": "$0.71B", "om": 8.2},
                       "analysis": ["Revenue was $11.2B in Q1 FY27."],
                       "compare_y": {"vs": "Q1 FY26", "bullets": ["Revenue fell $0.51B versus Q1 FY26."]}}]}
    q = c["quarters"][0]
    e = {"cik": 320187, "end": q["end"], "form": "10-Q", "ticker": "NKE"}
    html = notify.report_html(e, c, q, ["std", "y"], {"std": '<svg viewBox="0 0 2400 1200"></svg>', "y": '<svg viewBox="0 0 2400 1300"></svg>'},
                              "https://x.io/ff")
    for want in ("NIKE, Inc.", "incorporated in 1967", "Fiscal year ends May 31", "Revenue was $11.2B", "What changed vs Q1 FY26",
                 "compared with Q1 FY26", "0000320187-26-000045", "Not investment advice", "Rubber &amp; Plastics Footwear"):
        assert want in html, want
    assert html.count("<figure") == 2


def test_quotes_skip_footnotes_and_small_amounts_keep_their_size():
    from pipeline import social
    from pipeline.sankey import Fmt
    q = {"form": "10-Q", "nodes": [{"id": "revenue", "v": 1, "notes": [{"text": "(1) The percent change excluding currency changes "
         "represents a non-GAAP financial measure.\nRevenues decreased 4% due to lower wholesale shipments in Greater China."}]}]}
    assert social.filing_quote(q)[0].startswith("Revenues decreased 4%")
    assert Fmt(11e9).money(-3e6) == "−$3.0M" and Fmt(11e9).money(0.19e9) == "$0.19B"


def test_decreases_setting_reaches_the_drawings_and_the_intro_reaches_the_email():
    import email
    from pipeline import notify

    class FakeCharts:
        def __init__(self):
            self.calls = []

        def image(self, what, fmt="png", scale=2, quality=None, width=None):
            self.calls.append(("image", what[0], what[2] if what[0] == "chart" else None,
                               (what[3] if len(what) > 3 else {}) if what[0] == "chart" else None, fmt))
            return b"IMG" * 10

        def svg(self, what, aria="Chart"):
            self.calls.append(("svg", what[0], what[2] if what[0] == "chart" else None,
                               (what[3] if len(what) > 3 else {}) if what[0] == "chart" else None, "svg"))
            return '<svg viewBox="0 0 2400 1200"></svg>'

        def pdf(self, html, footer=""):
            self.calls.append(("pdf", "hatched area" in html, None, None, "pdf"))
            return b"%PDF-1.4"

    q = {"end": "2026-08-31", "label": "Q1 FY27", "form": "10-Q", "filed": "2026-10-02", "nodes": [],
         "headline": {"revenue": 11.2e9, "rev_fmt": "$11.2B", "yoy": -4, "ni": 0.71e9, "ni_fmt": "$0.71B", "om": 8.2},
         "analysis": ["Revenue was $11.2B."], "compare": {"vs": "Q4 FY26", "bullets": ["Revenue rose."]},
         "compare_y": {"vs": "Q1 FY26", "bullets": ["Revenue fell."]}}
    c = {"profile": {"name": "NIKE, Inc.", "cik": 320187, "tickers": ["NKE"]},
         "intro": {"text": "NIKE, Inc. was incorporated in 1967 under the laws of the State of Oregon. " * 12, "filed": "2025-07-17"},
         "quarters": [q]}
    e = {"cik": 320187, "end": q["end"], "form": "10-Q", "ticker": "NKE"}
    sub = {"email": "r@example.com", "chart_y": True, "cmp_decreases": True, "attach_images": "png", "attach_pdf": True}
    fake = FakeCharts()
    with notify.Assets(None, charts=fake) as a:
        pics, extras = a.for_message(sub, [(e, c, q, ["x"])], "https://x.io/ff", 10)
    drawn = {(k, mode): opts for k, kind, mode, opts, fmt in fake.calls if kind == "chart"}
    assert drawn[("image", "y")] == {"decreases": True}          # the year-ago comparison, with decreases
    assert drawn[("image", None)] == {"decreases": False}        # this quarter's chart has nothing to compare
    assert ("pdf", True, None, None, "pdf") in fake.calls         # the PDF explains the hatching
    msg = notify.build_message(sub, [(e, c, q, ["x"])], "https://x.io/ff", pics, "FF <a@b.c>", requested=True, extras=extras)
    html = [p for p in email.message_from_bytes(msg.as_bytes()).walk() if p.get_content_type() == "text/html"][0]
    html = html.get_payload(decode=True).decode()
    assert "incorporated in 1967" in html and "Item 1. Business" in html
    assert len(notify.intro_text(c, 420)) <= 421
    assert "hatched area with a dashed outline" in html

    sub["cmp_decreases"] = False
    fake.calls.clear()
    with notify.Assets(None, charts=fake) as a:
        a.for_message(sub, [(e, c, q, ["x"])], "https://x.io/ff", 10)
    assert all(opts == {"decreases": False} for k, kind, mode, opts, fmt in fake.calls if kind == "chart")


def test_detail_option_lists_every_change():
    import email
    from pipeline import notify
    q = {"end": "2026-06-27", "label": "Q3 FY26", "form": "10-Q", "filed": "2026-07-31",
         "headline": {"revenue": 109.4e9, "rev_fmt": "$109.4B", "yoy": 16, "ni": 29.8e9, "ni_fmt": "$29.8B", "om": 32.6},
         "compare": {"vs": "Q2 FY26", "bullets": ["a"]}, "compare_y": {"vs": "Q3 FY25", "bullets": ["Revenue rose."]},
         "nodes": [{"id": "revenue", "col": 1, "color": "rev", "name": "Revenue", "v": 109.4e9, "q": 111.2e9, "y": 94.0e9,
                    "cmp": "Δ −$1.8B", "cmp_y": "Δ +$15.4B"},
                   {"id": "L:a", "col": 0, "color": "rev", "name": "iPhone", "v": 54.3e9, "q": 57.0e9, "y": 44.6e9,
                    "cmp": "Δ −$2.7B · scale −1.1 · mix −1.7", "cmp_y": "Δ +$9.7B · scale +8.1 · mix +1.6"},
                   {"id": "rd", "col": 4, "color": "cost", "name": "Research &amp; development", "v": 11.7e9, "q": 11.4e9, "y": None}]}
    rows = notify.change_rows(q)
    assert [r["name"] for r in rows] == ["iPhone", "Revenue", "Research & development"]   # left to right
    assert rows[0]["dy"] == "+$9.7B" and rows[0]["py"] == "+22%" and rows[0]["mix_y"] == "scale +8.1 · mix +1.6"
    assert rows[1]["mix_q"] == "" and rows[2]["dy"] == "—"
    c = {"profile": {"name": "Apple Inc.", "cik": 320193}, "quarters": [q]}
    e = {"cik": 320193, "end": q["end"], "form": "10-Q", "ticker": "AAPL"}
    for detail, want in ((False, False), (True, True)):
        msg = notify.build_message({"email": "r@x.io", "changes_detail": detail}, [(e, c, q, ["x"])], "https://x.io", {},
                                   "FF <a@b.c>", requested=True)
        html = [p for p in email.message_from_bytes(msg.as_bytes()).walk() if p.get_content_type() == "text/html"][0]
        html = html.get_payload(decode=True).decode()
        assert ("All changes" in html) is want and "What changed vs Q3 FY25" in html
    page = notify.report_html(e, c, q, ["std"], {}, "", detail=True)
    assert "all changes" in page and "scale +8.1 · mix +1.6" in page


def _fictional_10k(tmp_path):
    """A fictional calendar-year filer with two 10-Ks and quarterly 10-Qs in companyfacts (dollars)."""
    from pipeline import sec
    M = 1_000_000
    def fact(start, end, v, form="10-K"):
        return {"start": start, "end": end, "val": int(v * M), "accn": "0009999903-26-000001", "form": form, "filed": "2026-02-20"}
    years = {"2024": (900, 500, 150, 60, 110, 180), "2025": (1100, 580, 220, 80, 150, 240)}   # rev, cor, opex, tax, ni, ocf
    g = {"Revenues": [], "CostOfRevenue": [], "OperatingExpenses": [], "OperatingIncomeLoss": [], "IncomeTaxExpenseBenefit": [],
         "NetIncomeLoss": [], "NetCashProvidedByUsedInOperatingActivities": [],
         "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": []}
    for y, (rev, cor, opex, tax, ni, ocf) in years.items():
        s, e = f"{y}-01-01", f"{y}-12-31"
        oi = rev - cor - opex
        for k, v in (("Revenues", rev), ("CostOfRevenue", cor), ("OperatingExpenses", opex), ("OperatingIncomeLoss", oi),
                     ("IncomeTaxExpenseBenefit", tax), ("NetIncomeLoss", ni), ("NetCashProvidedByUsedInOperatingActivities", ocf),
                     ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", ni + tax)):
            g[k].append(fact(s, e, v))
            g[k].append(fact(s, f"{y}-09-30", v * 0.74, "10-Q"))                # nine months, for the fourth quarter
            if k != "NetCashProvidedByUsedInOperatingActivities":
                g[k].append(fact(f"{y}-07-01", f"{y}-09-30", v * 0.25, "10-Q"))
    cf = {"cik": 9999903, "entityName": "Annual Example Corp", "facts": {"us-gaap": {k: {"units": {"USD": v}} for k, v in g.items()}}}
    sub = {"cik": "9999903", "name": "Annual Example Corp", "tickers": ["ANEX"], "exchanges": ["NYSE"], "sic": "3571",
           "sicDescription": "Electronic Computers", "fiscalYearEnd": "1231", "category": "Large accelerated filer",
           "filings": {"recent": {"accessionNumber": ["0009999903-26-000001"], "filingDate": ["2026-02-20"],
                                  "reportDate": ["2025-12-31"], "form": ["10-K"], "primaryDocument": ["anex-20251231.htm"],
                                  "items": [""]}}}
    d = tmp_path / "fx"
    d.mkdir()
    old = sec.FIXTURES
    sec.FIXTURES = str(d)
    for url, body in ((sec.companyfacts_url(9999903), cf), (sec.submissions_url(9999903), sub)):
        open(sec._fixture_path(url), "w").write(json.dumps(body))
    return old


def test_annual_chart_from_a_10k(tmp_path):
    from pipeline import build, sec
    old = _fictional_10k(tmp_path)
    try:
        build._sub.clear(); build._cf.clear()
        store = build.Store(str(tmp_path / "store"))
        end = build.process_filing(store, 9999903, "0009999903-26-000001", "10-K")
        c = store.company(9999903)
        assert end == "2025-12-31" and "2025-12-31" in c["years"]
        assert c["periods"]["fy"] == ["2024-12-31", "2025-12-31"]
        build.render(store, str(tmp_path / "out"))
        out = json.load(open(tmp_path / "out" / "c" / "9999903.json"))
        fy = out["years"][0]
        assert fy["label"] == "FY2025" and fy["key"] == "fy-2025-12-31" and fy["headline"]["revenue"] == 1100e6
        assert fy["compare_y"]["vs"] == "FY2024" and fy["compare"] is None
        rev = next(n for n in fy["nodes"] if n["id"] == "revenue")
        assert any(l[1].startswith("Y/Y +22%") and "Q/Q" not in l[1] for l in rev["lines"]), rev["lines"]
        assert "quarter" not in " ".join(fy["analysis"]).lower().replace("quarterly", "")
        q4 = out["quarters"][0]
        assert q4["label"] == "Q4 2025" and abs(q4["headline"]["revenue"] - 1100e6 * 0.26) < 2e6   # full year minus nine months
        assert [p["label"] for p in out["periods"]["fy"]] == ["FY2025", "FY2024"]
        assert out["periods"]["fy"][0]["fy"] == 2025                         # the picker groups periods by fiscal year
        assert {(p["label"], p["q"], p["fy"]) for p in out["periods"]["q"]} >= {("Q4 2025", 4, 2025), ("Q3 2024", 3, 2024)}
    finally:
        sec.FIXTURES = old
        build._sub.clear(); build._cf.clear()


def test_compare_any_two_periods(tmp_path):
    from pipeline import build, custom, sec
    old = _fictional_10k(tmp_path)
    try:
        build._sub.clear(); build._cf.clear()
        pl = custom.comparison(9999903, "fy", "2025-12-31", "2024-12-31")
        assert pl["label"] == "FY2025" and pl["compare"]["vs"] == "FY2024" and pl["compare_y"] is None
        assert pl["custom"]["b_label"] == "FY2024" and "compared with" in pl["subtitle"]
        rev = next(n for n in pl["nodes"] if n["id"] == "revenue")
        assert any(l[1] == "vs FY2024 +22%" for l in rev["lines"]), rev["lines"]
        assert rev["q"] == 900e6 and "cmp" in rev                # the comparison strips read B's values
        assert "previous quarter" not in " ".join(pl["analysis"] + pl["compare"]["bullets"])
        q = custom.comparison(9999903, "q", "2025-09-30", "2024-09-30")
        assert q["label"] == "Q3 2025" and q["compare"]["vs"] == "Q3 2024"
        for bad in (("q", "2025-09-30", "2025-09-30"), ("fy", "2025-12-31", "2019-12-31")):
            try:
                custom.comparison(9999903, *bad)
                raise AssertionError(f"accepted {bad}")
            except ValueError:
                pass
    finally:
        sec.FIXTURES = old
        build._sub.clear(); build._cf.clear()


def test_request_queues(tmp_path):
    from pipeline import custom
    now = __import__("datetime").datetime(2026, 10, 3, 4, 0, tzinfo=__import__("datetime").timezone.utc)

    class Fake:
        def __init__(self):
            self.rows = {"chart_requests": [{"id": 1, "cik": 1, "kind": "q", "a_end": "2025-09-30", "b_end": "2024-09-30",
                                             "status": "pending", "created_at": "2026-10-03T03:59:00Z"}],
                         "company_requests": [{"id": 7, "cik": 320193, "status": "pending", "created_at": "2026-10-03T03:00:00Z"},
                                              {"id": 8, "cik": 4242, "status": "queued", "created_at": "2026-10-02T03:00:00Z"}]}
            self.updates = []

        def _match(self, row, params):
            for k, v in params.items():
                op, _, val = v.partition(".")
                if op == "eq" and str(row.get(k)) != val:
                    return False
                if op == "lt" and (row.get(k) is None or not (str(row.get(k)) < val)):   # NULL never matches, as in SQL
                    return False
                if op == "in" and str(row.get(k)) not in val.strip("()").split(","):
                    return False
            return True

        def update(self, table, params, fields):
            got = [r for r in self.rows[table] if self._match(r, params)]
            for r in got:
                r.update(fields)
            self.updates.append((table, params, fields))
            return [dict(r) for r in got]

        def select(self, table, params):
            return [dict(r) for r in self.rows[table] if self._match(r, {k: v for k, v in params.items() if k != "select"})]

    f = Fake()
    real = custom.comparison
    custom.comparison = lambda cik, kind, a, b: {"label": "X", "nodes": [], "links": []}
    try:
        assert custom.process_charts(f, now) == 1
    finally:
        custom.comparison = real
    assert f.rows["chart_requests"][0]["status"] == "done" and f.rows["chart_requests"][0]["result"]["label"] == "X"
    f.rows["company_requests"] += [{"id": 9, "cik": 1652044, "status": "pending", "created_at": "2026-10-03T03:30:00Z"},
                                   {"id": 10, "cik": 320193, "status": "pending", "created_at": "2026-10-03T03:40:00Z"}]
    assert custom.claim_companies(f, now, limit=1) == [320193]          # one company per scan here: the oldest ask
    st = {r["id"]: r["status"] for r in f.rows["company_requests"]}
    assert st[7] == st[10] == "queued" and st[9] == "pending"            # the same company asked twice rides along
    for r in f.rows["company_requests"]:
        if r["id"] in (7, 10):
            r.update(status="pending", claimed_at=None)
    f.rows["company_requests"] = [r for r in f.rows["company_requests"] if r["id"] != 9]
    assert custom.claim_companies(f, now) == [320193]
    site = tmp_path / "site"
    (site / "data" / "c").mkdir(parents=True)
    (site / "data" / "c" / "320193.json").write_text("{}")
    custom.finish_companies(f, str(site))
    st = {r["id"]: r["status"] for r in f.rows["company_requests"]}
    assert st == {7: "done", 8: "failed", 10: "done"}


def test_email_me_a_fiscal_year(tmp_path):
    """'Email me' on a full-year page: the annual chart, not the fourth quarter that ends the same day."""
    import datetime as dt
    from pipeline import build, notify, sec
    old = _fictional_10k(tmp_path)
    try:
        build._sub.clear(); build._cf.clear()
        store = build.Store(str(tmp_path / "store"))
        build.process_filing(store, 9999903, "0009999903-26-000001", "10-K")
        build.render(store, str(tmp_path / "site" / "data"))
    finally:
        sec.FIXTURES = old
        build._sub.clear(); build._cf.clear()
    reqs = [{"id": 1, "user_id": "ann", "cik": 9999903, "period_end": "2025-12-31", "kind": "fy", "status": "pending",
             "attempts": 0, "created_at": "2026-10-02T10:00:00+00:00"},
            {"id": 2, "user_id": "ann", "cik": 9999903, "period_end": "2025-12-31", "kind": "q", "status": "pending",
             "attempts": 0, "created_at": "2026-10-02T10:00:01+00:00"},
            {"id": 3, "user_id": "cat", "cik": 9999903, "period_end": "2025-12-31", "status": "pending",   # an older row: no kind
             "attempts": 0, "created_at": "2026-10-02T10:00:02+00:00"}]
    supa, mail = _FakeSupa([_sub("ann", chart_y=True, chart_history=True, changes_detail=True), _sub("cat")], (), reqs), _FakeMailer()
    now = dt.datetime(2026, 10, 2, 10, 5, tzinfo=dt.timezone.utc)
    assert notify.run(notify.Site(tmp_path / "site"), supa, mail, "x", "https://ex.github.io/ff", now=now, images=False,
                      hour=22, daily_limit=50, requests_only=True) == 2
    assert [r["status"] for r in supa.t["send_requests"]] == ["sent", "sent", "sent"]
    ann = mail.sent[0]
    assert ann["Subject"] == "Your reports: ANEX FY2025, ANEX Q4 2025"
    text = ann.get_body(("plain",)).get_content()
    assert "#c-9999903-fy-2025-12-31" in text and "#c-9999903-2025-12-31" in text
    assert "ANEX · FY2025 full year · 10-K filed" in text
    assert "All changes (vs FY2024):" in text                       # a year has no previous-quarter column
    assert mail.sent[1]["Subject"].startswith("ANEX Q4 2025")
    c = json.load(open(tmp_path / "site" / "data" / "c" / "9999903.json"))
    y = c["years"][0]
    e = {"cik": 9999903, "end": y["end"], "period": "fy"}
    assert notify.item_key(e) == "9999903:2025-12-31:fy" and notify.views_for({"chart_history": True}, c, y) == ["std"]
    html = notify.report_html(e, c, y, ["std"], {}, "https://ex", detail=True)
    assert "fiscal year ended" in html and "this year against the year before" in html


def test_company_list_and_reader_requests_first(tmp_path):
    from pipeline import build
    env = dict(os.environ, SEC_FIXTURES=os.path.join(ROOT, "tests", "fixtures"), SEC_USER_AGENT="test test@example.com")
    out = tmp_path / "data"
    ciks = tmp_path / "ciks.txt"
    ciks.write_text("1067983\nnot-a-cik\n")
    r = subprocess.run([sys.executable, "-m", "pipeline.build", "run", "--store", str(tmp_path / "store"), "--out", str(out),
                        "--build-ciks-file", str(ciks), "--max-filings", "40"], cwd=ROOT, env=env, check=True,
                       capture_output=True, text=True)
    old = os.environ.get("SEC_FIXTURES")
    from pipeline import sec
    sec.FIXTURES = env["SEC_FIXTURES"]
    try:
        assert build.company_ciks(["ms", "AAPL", "brk.b", "320193", "", "NOPE", "x;y"]) == [320193, 1067983]
    finally:
        sec.FIXTURES = old or ""
    lst = json.load(open(out / "companies.json"))["companies"]
    assert lst[0] == [320193, "AAPL", "Apple Inc."] and len({x[0] for x in lst}) == len(lst)
    st = json.load(open(tmp_path / "store" / "state.json"))
    assert not any(p["cik"] == 1067983 for p in st["pending"].values())        # the asked-for company was processed
    assert os.path.exists(out / "c" / "1067983.json"), r.stdout[-2000:]
    # companies stored before the period list existed get it on a later run
    store = build.Store(str(tmp_path / "store"))
    c = store.company(320193)
    c.pop("periods", None)
    store.put(320193, c)
    old = os.environ.get("SEC_FIXTURES")
    from pipeline import sec
    sec.FIXTURES = env["SEC_FIXTURES"]
    try:
        build._cf.clear()
        build.refresh_periods(store)
    finally:
        sec.FIXTURES = old or ""
        build._cf.clear()
    assert store.company(320193)["periods"]["q"][-1] == "2026-06-27"


def test_pending_filings_wait_by_hours_not_by_runs(tmp_path):
    """Scans every few minutes must not give up on a filing whose XBRL data is a few hours late."""
    from pipeline import build
    store = build.Store(str(tmp_path / "store"))
    st = store.state
    real = build.process_filing
    build.process_filing = lambda *a, **k: (_ for _ in ()).throw(build.Pending("XBRL facts not available yet"))
    try:
        st["pending"]["a1"] = {"cik": 1, "form": "10-Q", "filed": "2026-10-03", "tries": 0}
        for i in range(40):                                   # 40 runs, 15 minutes apart: 10 hours
            t = (__import__("datetime").datetime(2026, 10, 3, 0, 0) + __import__("datetime").timedelta(minutes=15 * i)).isoformat()
            build._process_one(store, st, "a1", st["pending"]["a1"], {}, t)
        assert "a1" in st["pending"] and st["pending"]["a1"]["tries"] == 40
        build._process_one(store, st, "a1", st["pending"]["a1"], {}, "2026-10-04T00:05:00")
        assert "a1" not in st["pending"] and st["seen"]["a1"]["s"].startswith("skip: XBRL")
    finally:
        build.process_filing = real


def test_company_description_without_a_10k():
    """No 10-K yet: the earnings release's "About" paragraph, else Note 1 of the 10-Q; a 10-K's Item 1 always wins."""
    from pipeline import build, notify, social, text
    release = """<p><b>Micron Technology, Inc. Reports Results for the Fourth Quarter of Fiscal 2026</b></p>
      <p><b>About Non-GAAP Financial Measures</b></p><p>Non-GAAP gross margin excludes stock-based compensation and other
      items that management believes are not indicative of ongoing results of operations.</p>
      <p><b>About Micron Technology, Inc.</b></p><p>We are an industry leader in innovative memory and storage solutions
      transforming how the world uses information to enrich life for all, delivering DRAM, NAND and NOR products.</p>
      <p>To learn more about Micron Technology, Inc. (Nasdaq: MU), visit micron.com.</p>
      <p><b>Forward-Looking Statements</b></p><p>This press release contains forward-looking statements.</p>"""
    about = text.about(release, ["MICRON TECHNOLOGY INC"], ["MU"])
    assert about.startswith("We are an industry leader") and "micron.com" not in about and "Non-GAAP" not in about
    inline = ('<div><span style="font-weight:700">About NVIDIA</span><br/>NVIDIA (NASDAQ: NVDA) is the world leader in '
              'accelerated computing, with a full-stack platform for data centers, gaming and automotive markets.</div>'
              '<div>Certain statements in this press release including the benefits of NVIDIA products are forward-looking '
              'statements that are subject to risks and uncertainties.</div>')
    nv = text.about(inline, ["NVIDIA CORP"], ["NVDA"])
    assert nv.startswith("NVIDIA (NASDAQ: NVDA) is the world leader") and "forward-looking" not in nv
    assert text.about("<p><b>About the Conference Call</b></p><p>" + "Example will host a call. " * 6 + "</p>",
                      ["EXAMPLE CORP"], ["EXC"]) is None
    tenq = """<p>NOTES TO CONDENSED CONSOLIDATED FINANCIAL STATEMENTS</p>
      <p><b>Note 1 — Organization and Description of Business</b></p>
      <p>Sample Cloud Holdings, Inc. (the “Company”) provides cloud infrastructure for artificial intelligence workloads,
      operating data centers in the United States and Europe.</p>
      <p><b>Basis of Presentation</b></p><p>The accompanying unaudited condensed consolidated financial statements have
      been prepared in accordance with U.S. GAAP for interim financial information and should be read with the 10-K.</p>"""
    n1 = text.note1(tenq, ["SAMPLE CLOUD HOLDINGS INC"], ["SMCL"])
    assert n1.startswith("Sample Cloud Holdings, Inc. (the “Company”) provides") and "accompanying" not in n1
    apple = open(os.path.join(ROOT, "tests", "fixtures",
                              "www.sec.gov_Archives_edgar_data_320193_000032019326000020_aapl-20260627.htm")).read()
    assert text.note1(apple, ["Apple Inc."], ["AAPL"]) is None          # Note 1 is only accounting policies there
    # ranking: 10-K > 8-K > 10-Q; the newer filing of the same kind wins
    c = {}
    assert build.set_intro(c, "from the 10-Q", "u1", "2026-05-01", "10-Q")
    assert build.set_intro(c, "from the release", "u2", "2026-04-20", "8-K") and c["intro"]["source"] == "8-K"
    assert not build.set_intro(c, "older 10-Q", "u3", "2026-08-01", "10-Q")
    assert build.set_intro(c, "Item 1", "u4", "2025-10-31", "10-K") and not build.set_intro(c, "release", "u5", "2026-10-01", "8-K")
    assert not build.set_intro(c, "an older 10-K", "u6", "2024-10-31", "10-K") and c["intro"]["text"] == "Item 1"
    assert build.intro_rank({"intro": {"text": "stored before sources existed"}}) == 3
    # every place that quotes it says where it is from
    rel = {"intro": {"text": "We make memory.", "filed": "2026-09-23", "source": "8-K"}}
    assert notify.intro_source(rel) == "From the company’s earnings release (8-K) filed Sep 23, 2026, “About” section"
    assert text.intro_cite({"text": "x", "filed": "2026-05-01", "source": "10-Q"}, short=True) == "10-Q filed May 1, 2026, Note 1"
    assert notify.intro_source({"intro": {"text": "x", "filed": "2025-10-31"}}).endswith("Item 1. Business")


def _xbrl_files(d, cik, accn, stem, facts_, labels):
    """A filing directory with an XBRL instance and label linkbase (fixture files for sec.get)."""
    from pipeline import sec
    ctx, body = [], []
    for i, (concept, start, end, v) in enumerate(facts_):
        ctx.append(f'<xbrli:context id="c{i}"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">{cik}'
                   f'</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>{start}</xbrli:startDate>'
                   f'<xbrli:endDate>{end}</xbrli:endDate></xbrli:period></xbrli:context>')
        prefix, local = concept.split(":")
        body.append(f'<{prefix}:{local} contextRef="c{i}" unitRef="usd" decimals="-6">{v}</{prefix}:{local}>')
    inst = ('<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:us-gaap="http://fasb.org/us-gaap/2025" '
            'xmlns:abc="http://abc.example/2026">' + "".join(ctx) + "".join(body) + "</xbrli:xbrl>")
    locs = "".join(f'<link:loc xlink:type="locator" xlink:href="abc.xsd#{k}" xlink:label="loc_{k}"/>'
                   f'<link:label xlink:type="resource" xlink:label="lab_{k}_{r}" xlink:role="http://www.xbrl.org/2003/role/{r}">{t}</link:label>'
                   f'<link:labelArc xlink:type="arc" xlink:from="loc_{k}" xlink:to="lab_{k}_{r}"/>'
                   for k, roles in labels.items() for r, t in roles.items())
    lab = ('<link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xlink="http://www.w3.org/1999/xlink">'
           f'<link:labelLink>{locs}</link:labelLink></link:linkbase>')
    files = {f"{stem}_htm.xml": inst, f"{stem}_lab.xml": lab}
    idx = {"directory": {"item": [{"name": n} for n in files]}}
    open(sec._fixture_path(sec.filing_index_url(cik, accn)), "w").write(json.dumps(idx))
    for n, t in files.items():
        open(sec._fixture_path(sec.doc_url(cik, accn, n)), "w").write(t)
    return inst, lab


def test_capex_found_by_its_printed_name_when_the_tag_is_the_companys_own(tmp_path):
    """No standard capex tag in companyfacts: the filing's own line "Purchases of property and equipment" (a custom
    tag) is used; the quarter is year-to-date minus the previous filing's year-to-date; the note says where it is from."""
    from pipeline import build, dims, sec
    d = tmp_path / "fx"
    d.mkdir()
    old = sec.FIXTURES
    sec.FIXTURES = str(d)
    try:
        roles = {"abc_PaymentsForPropertyAndEquipmentNet": {"label": "Payments For Property And Equipment Net",
                                                             "negatedLabel": "Purchases of property and equipment"},
                 "us-gaap_ProceedsFromSaleOfPropertyPlantAndEquipment": {"label": "Proceeds from sale of equipment"},
                 "abc_PaymentsForCapitalizedSoftware": {"negatedLabel": "Capitalized software"}}
        cur = [("abc:PaymentsForPropertyAndEquipmentNet", "2026-01-01", "2026-06-30", 900e6),    # six months
               ("abc:PaymentsForPropertyAndEquipmentNet", "2025-01-01", "2025-06-30", 700e6),
               ("us-gaap:ProceedsFromSaleOfPropertyPlantAndEquipment", "2026-01-01", "2026-06-30", 950e6),
               ("abc:PaymentsForCapitalizedSoftware", "2026-01-01", "2026-06-30", 80e6)]
        inst, lab = _xbrl_files(d, 4242, "0000004242-26-000020", "abc-20260630", cur, roles)
        _xbrl_files(d, 4242, "0000004242-26-000010", "abc-20260331",
                    [("abc:PaymentsForPropertyAndEquipmentNet", "2026-01-01", "2026-03-31", 400e6),   # three months
                     ("abc:PaymentsForPropertyAndEquipmentNet", "2025-01-01", "2025-03-31", 300e6)], roles)
        found = dims.capex_lines(inst, dims.label_roles(lab))
        assert found["concept"] == "abc:PaymentsForPropertyAndEquipmentNet" and found["label"] == "Purchases of property and equipment"
        sub = {"filings": {"recent": {"accessionNumber": ["0000004242-26-000020", "0000004242-26-000010"],
                                      "reportDate": ["2026-06-30", "2026-03-31"], "form": ["10-Q", "10-Q"],
                                      "filingDate": ["2026-08-01", "2026-05-01"], "primaryDocument": ["a.htm", "b.htm"]}}}
        raw, comp = {"capex": None}, {"q1_end": "2026-03-31", "py_end": "2025-06-30",
                                      "raw_q1": {"capex": None}, "raw_py": {"capex": None}}
        src = build.capex_from_filing(4242, sub, {}, raw, comp, "2026-06-30", inst, lab)
        assert raw["capex"] == 500e6                                  # 900 (six months) - 400 (three months)
        assert comp["raw_py"]["capex"] == 400e6 and comp["raw_q1"]["capex"] == 400e6
        note = build.capex_note(src)
        assert note.startswith("Capital expenditures = the cash-flow line “Purchases of property and equipment” "
                               "(abc:PaymentsForPropertyAndEquipmentNet, the company’s own XBRL tag)")
        # a standard tag in companyfacts wins, and the largest of the capex tags is the main line
        fx = {"PaymentsToAcquirePropertyPlantAndEquipment": {("2026-04-01", "2026-06-30"): {"val": 20e6, "filed": "x"}},
              "PaymentsToAcquireOilAndGasPropertyAndEquipment": {("2026-04-01", "2026-06-30"): {"val": 2e9, "filed": "x"}},
              "__labels__": {"PaymentsToAcquireOilAndGasPropertyAndEquipment": "Payments to Acquire Oil and Gas Property and Equipment"}}
        from pipeline import facts
        assert facts.value(fx, "capex", "2026-06-30") == 2e9
        raw2 = {"capex": 2e9}
        src2 = build.capex_from_filing(4242, sub, fx, raw2, {}, "2026-06-30", None, None)
        assert src2 == {"concept": "us-gaap:PaymentsToAcquireOilAndGasPropertyAndEquipment",
                        "label": "Payments to Acquire Oil and Gas Property and Equipment", "how": "xbrl"}
        assert "Proceeds from selling assets" in build.FCF_NOTE
    finally:
        sec.FIXTURES = old


def test_every_node_says_where_its_figure_comes_from(tmp_path):
    """Reported lines name the line and its XBRL tag (and how a quarter was derived); calculated ones say how."""
    env = dict(os.environ, SEC_FIXTURES=os.path.join(ROOT, "tests", "fixtures"), SEC_USER_AGENT="test test@example.com")
    out = tmp_path / "data"
    subprocess.run([sys.executable, "-m", "pipeline.build", "run", "--store", str(tmp_path / "store"), "--out", str(out)],
                   cwd=ROOT, env=env, check=True, capture_output=True)
    q = json.load(open(out / "c" / "320193.json"))["quarters"][0]
    src = {n["id"]: n.get("source") for n in q["nodes"]}
    assert all(src.values()), [k for k, v in src.items() if not v]               # nothing left unexplained
    assert src["revenue"].startswith("Reported line:") and "(us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax)" in src["revenue"]
    assert "year-to-date figure minus the prior year-to-date" in src["ocf"]          # cash flow: year-to-date in a 10-Q
    assert src["cor"] == "Calculated: revenue − gross profit." and src["opex"].startswith("Calculated: gross profit − operating profit")
    assert src["wc_out"].startswith("Calculated: operating cash flow − net earnings")
    assert "aapl:IPhoneMember on ProductOrServiceAxis" in src["L:aapl:IPhoneMember"]
    assert src["capex"].startswith("Reported line: “Payments To Acquire Property Plant And Equipment”")
    by = {n["id"]: n for n in q["nodes"]}
    assert by["revenue"]["tag"] == "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax" and "tag" not in by["cor"]
    assert q["cite"]["text"] == ("Apple Inc., Form 10-Q for the quarter ended June 27, 2026, filed July 31, 2026 "
                                 "(accession 0000320193-26-000020)")
    assert q["cite"]["ix"].startswith("https://www.sec.gov/ix?doc=/Archives/edgar/data/320193/") and q["cite"]["index"]
    # quarters stored before sources existed get them on a later run, from SEC's company facts
    from pipeline import build, sec
    store = build.Store(str(tmp_path / "store"))
    c = store.company(320193)
    for x in c["quarters"].values():
        x.pop("src", None)
    store.put(320193, c)
    old = sec.FIXTURES
    sec.FIXTURES = env["SEC_FIXTURES"]
    try:
        build._cf.clear()
        build.refresh_periods(store)
    finally:
        sec.FIXTURES = old
        build._cf.clear()
    assert all(x["src"]["revenue"]["c"] == "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
               for x in store.company(320193)["quarters"].values())
    rel = json.load(open(out / "c" / "9999902.json"))["quarters"][0]                 # read from an earnings release
    rs = {n["id"]: n.get("source") for n in rel["nodes"]}
    assert rs["I:rd"] == "Reported line: “Technology and development” in the earnings release’s tables (8-K, Exhibit 99.1)."
    assert rs["capex"].startswith("Reported line: “Purchases of property and equipment” in the earnings release")
    assert rs["fcf_neg"].startswith("Calculated: capital expenditures − operating cash flow")
    assert rel["cite"]["text"].startswith("Sample Cloud Holdings, Inc., Form 8-K, Exhibit 99.1 (earnings release) for the quarter ended")
    assert rel["cite"]["ix"] is None and rel["cite"]["doc"].endswith("ex99-1.htm")


# ------------------------------------------------------------------ daily reports and the owner's e-mails
def test_owner_daily_report(tmp_path):
    """Every morning at the owner's hour: every filing since the last report in one e-mail, largest first, with the
    filing, what the company does, both charts, the analysis and the X thread; then not again until the next morning."""
    import datetime as dt
    from pipeline import notify, owner, social
    site = notify.Site(_site(tmp_path))
    cfg = dict(social.DEFAULTS, max_age_days=10000, site_url="https://ex.github.io/ff")
    s = dict(owner.DEFAULTS, min_revenue=2e9)
    st = {}
    morning = dt.datetime(2026, 9, 25, 0, 30, tzinfo=dt.timezone.utc)            # 8:30 in Shanghai
    assert owner.due_slot(morning - dt.timedelta(hours=1), s, st) is None           # 7:30: not yet
    slot = owner.due_slot(morning, s, st)
    assert slot == dt.datetime(2026, 9, 25, 0, 0, tzinfo=dt.timezone.utc)
    got = []
    assert owner.send_daily(site, st, cfg, s, morning, slot, got.append, "me@example.com", ["owner@example.com"], cfg["site_url"]) == 1
    m = got[0]
    assert m["Subject"].startswith("Daily report, Sep 25: 5 new filings — AAPL, BRK-B, META, EXDV, CRWV"), m["Subject"]  # SMCL < $2B
    text = m.get_body(("plain",)).get_content()
    html = m.get_body(("html",)).get_content()
    assert "In this report:" in text and "What the company does:" in text and "Chart 2: The same flows compared with Q3 FY25" in text
    assert "X thread (" in text and "--- Post 1 · Headline and charts · " in text and "accession 0000320193-26-000020" in text
    imgs = [p for p in m.walk() if p.get_content_type() == "image/jpeg"]
    assert len(imgs) == 10 and all(f'cid:{p["Content-ID"][1:-1]}' in html for p in imgs)       # two charts each
    assert html.count("<pre") == sum(len(social.compose_parts(*site.quarter(e), cfg))
                                     for e in owner.pending(site.json("index.json"), {}, s, cfg, morning))
    assert owner.due_slot(morning + dt.timedelta(minutes=30), s, st) is None        # sent: not again this morning
    tomorrow = morning + dt.timedelta(days=1)
    slot2 = owner.due_slot(tomorrow, s, st)
    assert slot2 and owner.send_daily(site, st, cfg, s, tomorrow, slot2, got.append, "me", ["o@x.com"], "") == 0   # nothing new
    assert owner.due_slot(tomorrow, s, st) is None and len(got) == 1
    assert owner.due_slot(morning, dict(s, daily_on=False), {}) is None
    # settings: Supabase's row over config/x.json over the defaults; the report goes to the site owners
    supa = _FakeSupa([], owner_settings=[{"id": True, "daily_hour": 7, "tz": "Europe/Berlin", "thread_direct": False}],
                     site_owners=[{"email": "Owner@Example.com"}])
    got_s = owner.settings(supa, {"min_revenue": 5e9})
    assert (got_s["daily_hour"], got_s["tz"], got_s["min_revenue"], got_s["thread_direct"]) == (7, "Europe/Berlin", 5e9, False)
    assert owner.addresses(supa) == ["owner@example.com"] and owner.settings(None)["daily_hour"] == 8


def test_requests_for_threads_and_days(tmp_path):
    """The owner's "Email me this thread" (PNG files attached, owner only) and a day's report from the home page."""
    import datetime as dt
    from pipeline import notify
    site = _site(tmp_path)
    ix = json.load(open(site / "data" / "index.json"))
    meta = next(e for e in ix["companies"] if e["ticker"] == "META")
    meta["also"] = [dict(end="2026-03-31", label="Q1 2026", filed="2026-07-31", form="10-Q", rev="$56.3B", revenue=56.3e9, yoy=20)]
    json.dump(ix, open(site / "data" / "index.json", "w"))
    assert [notify.item_key(e) for e in notify.entries_for_day(ix, "2026-07-31")] == ["320193:2026-06-27", "1326801:2026-03-31"]
    mk = lambda i, u, cik, end, kind: {"id": i, "user_id": u, "cik": cik, "period_end": end, "kind": kind, "status": "pending",
                                       "attempts": 0, "created_at": f"2026-10-02T10:00:0{i}+00:00"}
    reqs = [mk(1, "own", 320193, "2026-06-27", "thread"), mk(2, "ann", 320193, "2026-06-27", "thread"),
            mk(3, "ann", 0, "2026-07-30", "day"), mk(4, "bob", 0, "2026-07-30", "day"), mk(5, "own", 0, "2026-07-31", "day"),
            mk(6, "bob", 0, "2026-10-03", "day")]
    subs = [_sub("own"), _sub("ann", tickers=["AAPL"]), _sub("bob")]
    supa = _FakeSupa(subs, (), reqs, site_owners=[{"email": "own@example.com"}], owner_settings=[{"id": True, "min_revenue": 0}])
    mail = _FakeMailer()
    now = dt.datetime(2026, 10, 2, 10, 5, tzinfo=dt.timezone.utc)
    n = notify.run(notify.Site(site), supa, mail, "x", "https://ex.github.io/ff", now=now, images=True, daily_limit=50,
                   requests_only=True)
    st = {r["id"]: r for r in supa.t["send_requests"]}
    assert [st[i]["status"] for i in range(1, 7)] == ["sent", "failed", "sent", "sent", "sent", "failed"], st
    assert st[2]["error"] == "only the site owner can ask for X threads" and st[6]["error"] == "no filings that day"
    assert n == 4 and len(mail.sent) == 4
    thread = next(m for m in mail.sent if m["Subject"].startswith("X thread: Apple Inc. Q3 FY26"))
    assert [p.get_filename() for p in thread.iter_attachments()] == ["AAPL-Q3-FY26-1-chart.png", "AAPL-Q3-FY26-2-vs-Q3-FY25.png"]
    assert "Attach to post 1: AAPL-Q3-FY26-1-chart.png (Chart 1: Q3 FY26: where the revenue went" in thread.get_body(("plain",)).get_content()
    ann = next(m for m in mail.sent if m["To"] == "ann@example.com")            # follows AAPL; META filed that day
    body = ann.get_body(("plain",)).get_content()
    assert body.startswith("None of the companies you follow filed on Thursday, July 30, 2026.") and "META" in body
    bob = next(m for m in mail.sent if m["To"] == "bob@example.com")            # follows nothing: every company over $1B
    assert bob["Subject"].startswith("Your daily report, Jul 30: META") and "you follow no companies yet" in bob.get_body(("plain",)).get_content()
    own = next(m for m in mail.sent if m["To"] == "own@example.com" and m["Subject"].startswith("Daily report"))
    assert own["Subject"].startswith("Daily report, Jul 31: 2 new filings — AAPL, META"), own["Subject"]
    assert "X thread (" in own.get_body(("plain",)).get_content()


def test_full_daily_report_and_owner_reader_copy(tmp_path):
    """Alerts → "Daily report covers: every company that filed"; the owner's full report; the owner's reader copy."""
    import datetime as dt
    from pipeline import notify, owner, social
    site = _site(tmp_path)
    ix = json.load(open(site / "data" / "index.json"))
    morning = dt.datetime(2026, 9, 26, 0, 20, tzinfo=dt.timezone.utc)              # 8:20 in Shanghai
    daily = dict(frequency="daily", tz="Asia/Shanghai", digest_hour=8)
    subs = [_sub("fio", tickers=["META"], daily_scope="all", **daily),          # the full report, follows META
            _sub("gil", tickers=["META"], **daily),                             # the usual report: only META
            _sub("own", tickers=["AAPL"], **daily)]                             # the site owner's own alerts
    osets = [{"id": True, "reader_copy": False}]
    supa = _FakeSupa(subs, site_owners=[{"email": "Own@example.com"}], owner_settings=osets)
    mail = _FakeMailer()
    notify.MAX_AGE_DAYS = 100
    try:
        n = notify.run(notify.Site(site), supa, mail, "x", "https://ex.github.io/ff", now=morning, images=False, daily_limit=100)
        got = {m["To"].split("@")[0]: m for m in mail.sent}
        assert n == 2 and sorted(got) == ["fio", "gil"], sorted(got)          # the owner: no reader copy unless asked for
        body = got["fio"].get_body(("plain",)).get_content()
        assert body.startswith("Your full daily report for Saturday, September 26, 2026: 6 new charts since the last one, "
                               "1 for companies you follow (listed first)."), body[:200]
        assert got["fio"]["Subject"].startswith("Your daily report, Sep 26: META, ")      # the followed company first
        assert f"Why you got this: {notify.FULL_WHY}." in body and "Why you got this: you follow META." in body
        assert len({d["item"] for d in supa.dels if d["user_id"] == "fio"}) == 6
        assert got["gil"]["Subject"] == "Your daily report, Sep 26: META"
        # the owner asks for the reader version too: their own alerts (AAPL) arrive as for any reader
        osets[0]["reader_copy"] = True
        supa.t["owner_settings"] = [dict(osets[0])]
        mail.sent.clear()
        assert notify.run(notify.Site(site), supa, mail, "x", "", now=morning, images=False, daily_limit=100) == 1
        assert mail.sent[0]["To"] == "own@example.com" and mail.sent[0]["Subject"] == "Your daily report, Sep 26: AAPL"
    finally:
        notify.MAX_AGE_DAYS = 3

    # a day's report on request: the reader's full version; the owner gets the owner's report and, asked for, the reader's
    mk = lambda i, u: {"id": i, "user_id": u, "cik": 0, "period_end": "2026-07-31", "kind": "day", "status": "pending",
                       "attempts": 0, "created_at": f"2026-10-02T10:00:0{i}+00:00"}
    supa2 = _FakeSupa([_sub("fio", tickers=["BRK.B"], daily_scope="all"), _sub("own", tickers=["META"])], (),
                      [mk(1, "fio"), mk(2, "own")], site_owners=[{"email": "own@example.com"}],
                      owner_settings=[{"id": True, "reader_copy": True, "daily_scope": "all", "min_revenue": 900e9}])
    mail2 = _FakeMailer()
    now = dt.datetime(2026, 10, 2, 10, 5, tzinfo=dt.timezone.utc)
    assert notify.run(notify.Site(site), supa2, mail2, "x", "", now=now, images=False, daily_limit=50, requests_only=True) == 3
    fio = next(m for m in mail2.sent if m["To"] == "fio@example.com")
    assert fio.get_body(("plain",)).get_content().startswith("The full report for filings dated Friday, July 31, 2026: 1 filing.")
    mine = [m for m in mail2.sent if m["To"] == "own@example.com"]
    assert sorted(m["Subject"].split(",")[0] for m in mine) == ["Daily report", "Your daily report"], [m["Subject"] for m in mine]
    own_body = next(m for m in mine if m["Subject"].startswith("Daily report")).get_body(("plain",)).get_content()
    assert own_body.startswith("The full report for filings dated Friday, July 31, 2026: 1 filing, every company that filed "
                               "(the full report), largest first."), own_body[:200]       # $900B minimum, yet AAPL is in
    assert [r["status"] for r in supa2.t["send_requests"]] == ["sent", "sent"]

    # the owner's scheduled report: over the minimum, or everything with the full report
    s = dict(owner.DEFAULTS, min_revenue=900e9)
    cfg = dict(social.DEFAULTS, max_age_days=10000)
    assert owner.pending(ix, {}, s, cfg, morning) == []
    assert len(owner.pending(ix, {}, dict(s, daily_scope="all"), cfg, morning)) == 6
    assert owner.scope_words(s) == "companies with quarterly revenue of $900B or more"

    # long reports: the top names the companies in full, the end list stops at REST_MAX with a link to the rest
    items = notify._load_items(notify.Site(site), {}, [(e, [notify.FULL_WHY]) for e in ix["companies"]])
    keep = notify.REST_MAX
    notify.REST_MAX = 2
    try:
        m = notify.build_message(_sub("fio"), items, "https://ex.github.io/ff", {}, "x", daily=True, full_count=1, day="Today")
    finally:
        notify.REST_MAX = keep
    text = m.get_body(("plain",)).get_content()
    assert "- and 5 more, listed at the end" in text and "- and 3 more on the site: https://ex.github.io/ff/#home" in text
    html = m.get_body(("html",)).get_content()
    assert "and 5 more listed at the end" in html and 'href="https://ex.github.io/ff/#home"' in html


def test_data_checks(tmp_path):
    """pipeline/checks.py: what is flagged as a probable error (warn) or explained (note), and where it shows."""
    import datetime as dt
    from pipeline import checks, notify, social
    from pipeline.model import normalize
    raw = lambda R, **kw: dict({"revenue": R, "ni": 0.1 * R, "tax": 0.02 * R, "pretax": 0.12 * R, "oi": 0.12 * R,
                                "ocf": 0.2 * R, "da": 0.03 * R, "capex": 0.05 * R}, **kw)
    codes = lambda found: sorted((x["level"], x["code"]) for x in found)
    c = {"quarters": {"2025-08-28": {"end": "2025-08-28", "q1_end": "2025-05-29"}}}
    # a 14-week quarter (53-week fiscal year) and big but real growth: notes only
    q = {"end": "2026-09-03", "q1_end": "2026-05-28", "py_end": "2025-08-28", "form": "8-K"}
    got = checks.checks(q, c, normalize(raw(54e9)), normalize(raw(41e9)), normalize(raw(11.3e9)))
    assert codes(got) == [("note", "long_quarter"), ("note", "revenue_jump")], got
    assert "14 weeks (98 days)" in got[0]["text"] and "4.8× the year-ago quarter ($11.3B then)" in got[1]["text"]
    # a fourth quarter derived from the 10-K that collapses: a probable error
    q4 = {"end": "2026-06-30", "q1_end": "2026-03-31", "py_end": "2025-06-30", "form": "10-K"}
    got = checks.checks(q4, {}, normalize(raw(13460)), normalize(raw(2.0e6)), normalize(raw(4.75e6)))
    assert codes(got) == [("warn", "derived_jump")] and "0.3% of the year-ago quarter" in got[0]["text"]
    assert checks.has_warning(got)
    # cash flow far above revenue: unusual (note), or out of scale with revenue and earnings alike (warn)
    assert codes(checks.checks({}, {}, normalize(raw(19.3e9, ocf=23.1e9)))) == [("note", "ocf_over_revenue")]
    assert codes(checks.checks({}, {}, normalize(raw(1e7, ocf=9e7, ni=1e6)))) == [("warn", "ocf_scale")]
    small = normalize(raw(1e5, ni=-9e5, pretax=-9e5, tax=0, oi=-9e5, ocf=-8e5))      # tiny revenue, cash burn = the loss
    assert ("warn", "ocf_scale") not in codes(checks.checks({}, {}, small))
    # restated year-to-date capex, a rare tax rate, a pre-tax figure that did not reconcile
    assert ("warn", "capex_negative") in codes(checks.checks({}, {}, normalize(raw(1e9, capex=-5e7))))
    assert ("note", "tax_rate") in codes(checks.checks({}, {}, normalize(raw(1e9, tax=0.1e9, ni=0.02e9, pretax=0.12e9))))
    assert ("note", "pretax_fixed") in codes(checks.checks({}, {}, normalize(raw(1e9, pretax=0.5e9))))
    # a 53-week fiscal year
    yr = {"end": "2026-09-03", "py_end": "2025-08-28", "form": "10-K"}
    assert codes(checks.checks(yr, {}, normalize(raw(1e9)), None, normalize(raw(0.9e9)), annual=True)) == [("note", "long_year")]

    # the built site: checks on the chart data, a flag in the index for the latest quarter
    site = _site(tmp_path)
    exdv = json.load(open(site / "data" / "c" / "9999901.json"))
    assert all(isinstance(q.get("checks"), list) for q in exdv["quarters"])
    # the thread's last post keeps the disclaimer even when the source line has to be cut
    cfg = dict(social.DEFAULTS, min_revenue=0, max_age_days=10000, max_per_run=50)
    for e in social.candidates(str(site), {"posted": {}}, cfg, today=dt.date(2026, 10, 2)):
        c_, q_ = social.quarter_of(str(site), e)
        last = social.compose(c_, q_, dict(cfg, numbered=False))[-1]
        assert social.SOURCE_DISCLAIMER in last and social.xlen(last) <= 280, last
    # API posting holds a flagged quarter; the e-mails say what to check
    ix = json.load(open(site / "data" / "index.json"))
    ix["companies"][0]["check"] = "warn"
    json.dump(ix, open(site / "data" / "index.json", "w"))
    held = ix["companies"][0]["cik"]
    api = [e["cik"] for e in social.candidates(str(site), {"posted": {}}, dict(cfg, mode="api"), today=dt.date(2026, 10, 2))]
    mail = [e["cik"] for e in social.candidates(str(site), {"posted": {}}, cfg, today=dt.date(2026, 10, 2))]
    assert held not in api and held in mail
    e0 = ix["companies"][0]
    c0, q0 = social.quarter_of(str(site), e0)
    q0["checks"] = [{"level": "warn", "code": "derived_jump", "text": "Revenue is 0.3% of the year-ago quarter."}]
    thread = social.build_email([(e0, c0, q0, social.compose_parts(c0, q0, cfg), [])], cfg, "x", "o@x.com")
    assert "Check before posting: a probable data error" in thread.get_body(("html",)).get_content()
    assert "CHECK BEFORE POSTING" in thread.get_body(("plain",)).get_content()
    reader = notify.build_message(_sub("ann"), [(e0, c0, q0, ["you follow it"])], "https://ex.github.io/ff", {}, "x")
    html = reader.get_body(("html",)).get_content()
    assert "Data check: please verify in the filing" in html and "can contain errors" in html


def test_depreciation_and_amortization_tagged_apart():
    """Oracle tags depreciation and amortization of intangibles apart: D&A is their sum; depreciation alone is labelled so."""
    from pipeline import facts, release
    from pipeline.model import normalize
    F = lambda s, e, v: {"start": s, "end": e, "val": v, "filed": "2026-09-11"}
    fx = facts.index_facts({"facts": {"us-gaap": {
        "Depreciation": {"label": "Depreciation", "units": {"USD": [F("2026-06-01", "2026-08-31", 3156e6),
                                                                   F("2025-06-01", "2025-08-31", 1351e6)]}},
        "AmortizationOfIntangibleAssets": {"label": "Amortization", "units": {"USD": [F("2026-06-01", "2026-08-31", 202e6),
                                                                                     F("2025-06-01", "2025-08-31", 420e6)]}}}}})
    assert facts.value(fx, "da", "2026-08-31") == 3358e6 and facts.value(fx, "da", "2025-08-31") == 1771e6
    assert facts.ytd_value(fx, "da", "2026-08-31") == 3358e6
    raw = facts.extract(fx, "2026-08-31")
    assert (raw["da"], raw["dep"], raw["amort"]) == (3358e6, 3156e6, 202e6)
    base = {"revenue": 19345e6, "ni": 4760e6, "tax": 847e6, "pretax": 5607e6, "oi": 6728e6, "ocf": 23103e6}
    filled = lambda r: dict(base, **{k: v for k, v in r.items() if v is not None})
    assert normalize(filled(raw))["da_label"] == "Depreciation &amp; amortization"
    # a combined tag wins, nothing is added twice
    fx2 = facts.index_facts({"facts": {"us-gaap": {
        "DepreciationDepletionAndAmortization": {"units": {"USD": [F("2026-06-01", "2026-08-31", 500e6)]}},
        "Depreciation": {"units": {"USD": [F("2026-06-01", "2026-08-31", 400e6)]}},
        "AmortizationOfIntangibleAssets": {"units": {"USD": [F("2026-06-01", "2026-08-31", 100e6)]}}}}})
    assert facts.value(fx2, "da", "2026-08-31") == 500e6
    # depreciation alone: the chart says "Depreciation", never D&A
    fx3 = facts.index_facts({"facts": {"us-gaap": {"Depreciation": {"units": {"USD": [F("2026-06-01", "2026-08-31", 400e6)]}}}}})
    raw3 = facts.extract(fx3, "2026-08-31")
    assert raw3["da"] == 400e6 and normalize(filled(raw3))["da_label"] == "Depreciation"
    # an earnings release whose row is "Depreciation" alone
    assert release.depreciation_only({"cf_labels": {"da": "depreciation"}})
    assert not release.depreciation_only({"cf_labels": {"da": "depreciation and amortization"}})
