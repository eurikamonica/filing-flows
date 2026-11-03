"""scripts/site_monitor.py: what counts as a problem, and when the owner is e-mailed (no network)."""
import datetime as dt
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("site_monitor", Path(__file__).resolve().parent.parent / "scripts" / "site_monitor.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

NOW = dt.datetime(2026, 11, 3, 12, 0, tzinfo=dt.timezone.utc)


def site(stamp="2026-11-03T11:40:00Z", www=(301, "https://filing-flows.com/"), home=200):
    def fetch(url):
        path = url.split("filing-flows.com", 1)[1].split("?")[0]
        if url.startswith("https://www."):
            return www[0], {"Location": www[1]}, b""
        if path == "/":
            return home, {}, b"<!doctype html><html>" if home == 200 else b""
        if path in ("/robots.txt", "/sitemap-index.xml"):
            return 200, {}, b"ok"
        if path == M.STAMP:
            return 200, {}, json.dumps({"generated_at": stamp}).encode()
        return 404, {}, b""
    return fetch


def test_healthy_site():
    assert M.site_problems("https://filing-flows.com", NOW, fetch=site(), days=lambda h: 80) == []


def test_problems():
    p = M.site_problems("https://filing-flows.com", NOW, fetch=site(stamp="2026-11-03T06:00:00Z", home=502),
                        days=lambda h: 5)
    assert any("/ answered 502" in x for x in p)
    assert any("last built 6 hours ago" in x for x in p)
    assert any("expires in 5 days" in x for x in p)
    p = M.site_problems("https://filing-flows.com", NOW, fetch=site(www=(200, "")), days=lambda h: 80)
    assert p == ["www.filing-flows.com answered 200 instead of a redirect to filing-flows.com"]
    assert M.site_problems("https://filing-flows.com", NOW, fetch=site(www=(0, "")), days=lambda h: 80) == []


def test_when_to_mail():
    a, st = M.decide(["x"], {}, NOW)
    assert a == "alert"
    later = NOW + dt.timedelta(hours=1)
    assert M.decide(["x"], st, later)[0] is None                       # still the same problem: quiet
    assert M.decide(["x"], st, NOW + dt.timedelta(hours=7))[0] == "repeat"
    assert M.decide(["x", "y"], st, later)[0] == "alert"               # something new
    assert M.decide([], st, later) == ("recovered", {})
    assert M.decide([], {}, later) == (None, {})
