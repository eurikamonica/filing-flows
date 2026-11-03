"""scripts/seo.py: every search page names Filing Flows (one Organization with the X account in sameAs) as its
publisher, and /about/ describes the site."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seo  # noqa: E402

BASE = "https://filing-flows.com"


def ld(doc):
    return json.loads(re.search(r'application/ld\+json">(.*?)</script>', doc, re.S).group(1))


def test_publisher_on_every_page():
    us = {"@type": "Organization", "name": "Filing Flows"}
    page_ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "name": "T", "url": BASE + "/c/aaa/"},
        {"@type": "ImageObject", "contentUrl": "https://img/a.jpg", "creator": us},
        {"@type": "Organization", "name": "Berkshire Hathaway"}]}
    doc = seo.page("Alpha (AAA)", "d", BASE + "/c/aaa/", "<p>x</p>", 2, "https://img/a.jpg", page_ld)
    g = ld(doc)["@graph"]
    org = next(n for n in g if n.get("@id") == BASE + "/#org")
    assert org["sameAs"] == [seo.X_URL] and org["name"] == "Filing Flows"
    assert next(n for n in g if n["@type"] == "WebPage")["publisher"] == {"@id": BASE + "/#org"}
    assert next(n for n in g if n["@type"] == "ImageObject")["creator"] == {"@id": BASE + "/#org"}
    assert any(n.get("name") == "Berkshire Hathaway" for n in g)                    # other organizations are left alone
    assert f'content="@{seo.X_HANDLE}"' in doc and f'href="{seo.X_URL}"' in doc and 'href="../../about/"' in doc
    assert "x.com/FilingFlow\"" not in doc                                           # the old handle is gone
    bare = ld(seo.page("List", "d", BASE + "/c/", "b", 1, "i"))["@graph"]               # a page without its own data
    assert [n["@type"] for n in bare] == ["WebPage", "Organization"] and bare[0]["publisher"]


def test_about_page(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTACT_EMAIL", "team@example.com")
    assert seo.about_page(str(tmp_path), BASE, 3986) == [(BASE + "/about/", None)]
    doc = (tmp_path / "about" / "index.html").read_text()
    assert "<h1>About Filing Flows</h1>" in doc and "3,986 US-listed companies" in doc and "mailto:team@example.com" in doc
    g = ld(doc)["@graph"]
    assert g[0]["@type"] == "AboutPage" and g[0]["about"] == {"@id": BASE + "/#org"}
    assert f"rel='me noopener'>@{seo.X_HANDLE}</a>" in doc


def test_one_image_object_per_picture():
    """the company page's primaryImageOfPage points at the full ImageObject (credit, licence) by @id instead of a
    second, bare ImageObject of the same picture"""
    o = seo.image_ld(BASE, "https://img/x.jpg?v=1", "alt")
    assert o["@id"] == "https://img/x.jpg#image" and o["license"].endswith("/license/") and o["creditText"]


def test_translated_pages_have_translated_chrome():
    doc = seo.localize(seo.page("T", "d", BASE + "/es/c/aaa/", "<p>x</p>", 3, "i"), "es")
    assert '<html lang="es">' in doc and ">Empresas</a>" in doc and ">Companies</a>" not in doc
    assert "No es asesoramiento de inversión" in doc and "Figures read automatically" not in doc and ">Acerca de</a>" in doc
    zh = seo.localize(seo.page("T", "d", BASE + "/zh/c/aaa/", "<p>x</p>", 3, "i"), "zh-Hans")
    assert ">公司</a>" in zh and "每日图表发布在 X：@" in zh
