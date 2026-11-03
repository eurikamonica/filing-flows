"""scripts/compare_hosts.py: two hosts of the site compared address by address (no network: stand-in hosts)."""
import hashlib
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("compare_hosts", Path(__file__).resolve().parent.parent / "scripts" / "compare_hosts.py")
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)

SITE = "filing-flows.com"
INDEX = (b'<?xml version="1.0"?><sitemapindex><sitemap><loc>https://filing-flows.com/sitemap.xml</loc></sitemap>'
         b'</sitemapindex>')
MAP = b"<urlset>" + b"".join(b"<url><loc>https://filing-flows.com/p%d.html</loc></url>" % i for i in range(50)) + \
      b"<url><loc>https://filing-flows.com/c/amzn/</loc></url></urlset>"


class Fake:
    def __init__(self, name, pages, absolute):
        self.name, self.host, self.pages, self.absolute = name, SITE, pages, absolute
        self.asked = []

    def get(self, path, host=None, method="GET"):
        self.asked.append((path, host))
        if host and host.startswith("www."):
            return 301, {"location": f"https://{SITE}{path}"}, b""
        if path == "/c/amzn":
            return 301, {"location": f"https://{SITE}/c/amzn/" if self.absolute else "/c/amzn/"}, b""
        if path in self.pages:
            body = self.pages[path]
            return 200, {"content-type": "text/html; charset=utf-8"}, body
        return 404, {"content-type": "text/html"}, b"nf"


def pages(**over):
    base = {"/sitemap-index.xml": INDEX, "/sitemap.xml": MAP, "/": b"home", "/c/amzn/": b"amzn"}
    base.update({f"/p{i}.html": b"page %d" % i for i in range(50)})
    base.update(over)
    return base


def test_location_forms_match():
    assert C.norm_location("https://filing-flows.com/c/amzn/", SITE, SITE) == "/c/amzn/"
    assert C.norm_location("/c/amzn/?x=1", "203.0.113.5", SITE) == "/c/amzn/?x=1"
    assert C.norm_location("https://example.org/x", SITE, SITE) == "https://example.org/x"
    assert C.norm_location(None, SITE, SITE) is None


def test_identical_hosts():
    old, new = Fake("old", pages(), absolute=True), Fake("new", pages(), absolute=False)
    r = C.run(old, new, SITE, sample=20, seed=1, workers=2)
    assert r["sitemap_pages"] == 51
    assert all(x["diff"] == [] for x in r["rows"]), [x for x in r["rows"] if x["diff"]]
    assert ("/", "www." + SITE) in new.asked
    assert any(p == "/p3" for p, _ in old.asked) or any(p.endswith(".html") for p, _ in old.asked)
    md = C.report_md(r)
    assert "**0** with a different status" in md


def test_differences_are_reported():
    newp = pages()
    del newp["/p7.html"]
    newp["/p8.html"] = b"other"
    old, new = Fake("old", pages(), absolute=True), Fake("new", newp, absolute=False)
    r = C.run(old, new, SITE, sample=51, seed=2, workers=2)
    by = {x["path"]: x for x in r["rows"] if x["host"] == SITE}
    assert by["/p7.html"]["diff"] == ["status"]
    assert by["/p8.html"]["diff"] == ["body"]
    assert by["/p8.html"]["old"]["sha256"] == hashlib.sha256(b"page 8").hexdigest()
    md = C.report_md(r)
    assert "**1** with a different status" in md and "← fix these" in md
    assert "`/p8.html`" in md
