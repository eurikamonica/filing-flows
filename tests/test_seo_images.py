"""Google Images: the share pictures carry their credit and terms (XMP), pages show them with alt and caption, the
structured data says how they may be used, and the sitemaps list them."""
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pipeline import ogimg  # noqa: E402
import seo  # noqa: E402


def jpeg():
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (40, 20), (250, 250, 247)).save(b, "JPEG")
    return b.getvalue()


def test_xmp_credit_and_terms():
    from PIL import Image
    j = jpeg()
    x = ogimg.with_xmp(j, "TARGET CORP (TGT) Q2 FY27 revenue breakdown & more", "https://example.com/")
    y = ogimg.with_xmp(x, "again", "https://example.com/")
    assert x.count(ogimg.XMP_TAG) == 1 and y.count(ogimg.XMP_TAG) == 1               # replaced, never stacked
    im = Image.open(io.BytesIO(y))
    im.load()
    xmp = im.info["xmp"].decode("utf-8")
    assert "<photoshop:Credit>Filing Flows (filing-flows.com)</photoshop:Credit>" in xmp
    assert "<xmpRights:WebStatement>https://example.com/license/</xmpRights:WebStatement>" in xmp and "plus:LicensorURL" in xmp
    assert ogimg.with_xmp(b"not a jpeg", "t", "https://example.com/") == b"not a jpeg"
    assert "&amp; more" in ogimg.with_xmp(j, "a & more", "https://example.com/").decode("latin-1")


def test_figure_structured_data_and_license(tmp_path):
    f = seo.share_figure("https://img/x.jpg", "Target Q2 revenue breakdown Sankey", "How Target makes money", "https://example.com/c/tgt/revenue/", 3, False)
    assert "alt='Target Q2 revenue breakdown Sankey'" in f and "How Target makes money" in f and "href='../../../license/'" in f and "seo-embed" not in f
    assert seo.share_figure(None, "a", "b", "u") == ""
    ld = seo.image_ld("https://example.com", "https://img/x.jpg", "alt", "cap")
    assert ld["license"] == ld["acquireLicensePage"] == "https://example.com/license/" and ld["creditText"].startswith("Filing Flows")
    urls = seo.license_page(str(tmp_path), "https://example.com")
    assert urls[0][0] == "https://example.com/license/" and "free to use" in (tmp_path / "license" / "index.html").read_text()
    json.dumps(ld)
