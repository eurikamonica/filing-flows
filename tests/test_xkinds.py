"""pipeline/xkinds.py: post kinds registered by feature modules reach the engage dispatch, the schedules, the hashtags,
the writing guide, the owner's buttons and requests, and the schema — without edits to those files."""
import datetime as dt
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_registered_kind_reaches_engage_and_owner_tools():
    from pipeline import engage, hashtags as H, notify, xkinds as X
    X.load()

    @X.kind("zz_test_kind", tag="zz_test", hashtags=["#ZZTest", "#stocks"], cooldown=30, schedule=["close"],
            label="✦ ZZ test", title="a test format", guide="Say ZZ.", corpus=2)
    def plan(site, rows, c, by_ticker, state_ok, today):
        return {"task": "ZZ facts", "cashtags": ["ZZ"], "fallback": "$ZZ is a test company, and this sentence is long enough. Thoughts?"}

    try:
        H.KINDS.setdefault("zz_test", ["#ZZTest", "#stocks"])
        assert X.expand(["lows52", "@close", "lows52"])[:2] == ["lows52", "zz_test_kind"]
        assert X.expand(["@morning"]) == [k for k, v in sorted(X.REG.items()) if "morning" in v["schedule"]]
        p = engage.registered_plan("zz_test_kind", None, [], {}, {}, lambda *a, **k: True, dt.date(2026, 10, 19))
        assert p["kind"] == "zz_test_kind" and p["items"] == [] and p["cashtags"] == ["ZZ"]
        assert engage.registered_plan("no_such_kind", None, [], {}, {}, None, None) is None
        assert engage.kind_tag("zz_test_kind") == "zz_test" and engage.kind_tag("insider") == "insider"
        assert "## zz_test_kind\nSay ZZ." in engage.guide()
        assert {"kind": "engage_zz_test_kind", "label": "✦ ZZ test", "title": "a test format"} in X.buttons()
        post = engage.clean(p["fallback"], p["cashtags"], H.pick(engage.kind_tag("zz_test_kind"), key="t"))
        assert "#ZZTest" in post
        f = notify.post_kind_filter(True)["or"]
        assert "kind.like.engage_*" in f and "post_8k" in f
        assert notify.post_kind_filter(False)["and"].endswith("kind.not.like.engage_*)")
    finally:
        X.REG.pop("zz_test_kind", None)
    try:
        X.kind("Bad-Name", tag="x")
        raise AssertionError("a bad kind name passed")
    except ValueError:
        pass
    try:
        X.kind("ok_name", tag="x", schedule=["hourly"])
        raise AssertionError("an unknown schedule passed")
    except ValueError:
        pass


def test_schema_site_and_workflow_accept_any_engage_kind():
    sql = open(os.path.join(ROOT, "supabase", "schema.sql"), encoding="utf-8").read()
    assert sql.count("'^engage_[a-z0-9_]+$'") == 4
    assert "kind !~ '^engage_[a-z0-9_]+$') or public.am_i_owner()" in sql
    app = open(os.path.join(ROOT, "web", "app.js"), encoding="utf-8").read()
    assert "xsite.engage_more" in app and "x-[a-z0-9]+" in app and "disclosures/views.json" in app
    wf = open(os.path.join(ROOT, ".github", "workflows", "engage.yml"), encoding="utf-8").read()
    for slot in ("@morning", "@close", "@evening", "@weekly", "@events"):
        assert re.search(r"kinds=[a-z0-9_,]*" + slot, wf), slot
    scan = open(os.path.join(ROOT, ".github", "workflows", "scan.yml"), encoding="utf-8").read()
    assert "'research-*'" in scan and "--research _research" in scan
