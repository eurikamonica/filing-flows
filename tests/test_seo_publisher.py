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


def test_no_signed_zero():
    """f"{v:+.1f}%" of −0.04 prints "−0.0%": page() drops the sign of a change that rounds to nothing, and only that."""
    doc = seo.page("T", "down −0.0% today", "https://x/", "<p>was −0.0% (typical ±2.1%)</p><td>-0%</td><td>-0.01%</td><td>10-0%</td><p>−0,0 %</p>", 1, "https://x/og.png")
    assert "was 0.0% (typical" in doc and "<td>0%</td>" in doc and "-0.01%" in doc and "10-0%" in doc and "<p>0,0 %</p>" in doc
    assert 'content="down 0.0% today"' in doc and "−0.0%" not in doc


def test_text_already_encoded_is_not_encoded_twice():
    """An FDA recall's "PACK A &#38; B" showed as "A &amp;#38; B" on c/mdln/risks/; "S&P" and "AT&T" are plain text."""
    assert seo.e("OPEN HEART PACK A &#38; B") == "OPEN HEART PACK A &amp; B" and seo.e("Procter &amp; Gamble") == "Procter &amp; Gamble"
    assert seo.e("S&P 500") == "S&amp;P 500" and seo.e("Procter&regulation") == "Procter&amp;regulation" and seo.e("<b>") == "&lt;b&gt;"


def test_translated_page_placeholder_and_one_disclaimer():
    """The chart's placeholder in the page's language; the footer carries the disclaimer, the source line names the filing."""
    doc = seo.page("T", "d", "https://x/", "<figure><p class='muted'>Drawing the Sankey…</p></figure>", 1, "https://x/og.png")
    assert "正在绘制 Sankey 图…" in seo.localize(doc, "zh-Hans") and "Dibujando el diagrama de Sankey…" in seo.localize(doc, "es")
    import seo_intl as I
    assert I.L["es"]["source"]("Apple", "10-Q").endswith("ante la SEC de EE. UU.") and "conseil" not in I.L["fr"]["source"]("Apple", "10-Q")


def test_guidance_ranges():
    """"EPS $-0.65–-0.65" on c/wnc/guidance/: one figure when both ends agree, signs before the dollar, words for a range across zero."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import seo_topics as T
    assert T.grange({"lo": -0.65, "hi": -0.65, "unit": "ps"}) == "−$0.65" and T.grange({"lo": 1.2, "hi": 1.35, "unit": "ps"}) == "$1.20–$1.35"
    assert T.grange({"lo": -2, "hi": 1, "unit": "growth"}) == "−2% to +1%" and T.grange({"lo": 30, "hi": 32, "unit": "pct"}) == "30%–32%"
