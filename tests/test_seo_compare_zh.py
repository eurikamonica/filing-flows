"""scripts/seo_compare.py and scripts/seo_zh.py on a stand-in site: pairs of nearest peers and well-known rivals, the
answer-first comparison, links from the company page; Chinese pages with Chinese names, periods and units, hreflang
both ways, the list page and the sitemaps."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seo_compare as C  # noqa: E402
import seo_zh as Z  # noqa: E402


def w(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj))


def co(cik, label, rev, yoy, om, ni, segs):
    nodes = [{"id": f"S{i}", "name": n} for i, (n, _) in enumerate(segs)] + [{"id": "revenue", "name": "Revenue"}, {"id": "net", "name": "Net earnings"}]
    links = [{"s": f"S{i}", "t": "revenue", "v": v, "y": v / 1.1} for i, (_, v) in enumerate(segs)] + [{"s": "revenue", "t": "net", "v": ni}]
    return {"quarters": [{"label": label, "form": "10-Q", "filed": "2026-08-26", "headline": {"revenue": rev, "yoy": yoy, "om": om, "ni": ni},
                          "nodes": nodes, "links": links}]}


def site(tmp):
    rows = [{"cik": 1, "ticker": "NVDA", "name": "NVIDIA CORP", "sic": "3674", "revenue": 9.6e10, "filed": "2026-08-26"},
            {"cik": 2, "ticker": "AMD", "name": "ADVANCED MICRO DEVICES INC", "sic": "3674", "revenue": 1.15e10, "filed": "2026-08-05"},
            {"cik": 3, "ticker": "INTC", "name": "INTEL CORP", "sic": "3674", "revenue": 1.3e10, "filed": "2026-08-01"},
            {"cik": 4, "ticker": "KO", "name": "COCA COLA CO", "sic": "2080", "revenue": 1.3e10, "filed": "2026-10-28"}]
    w(tmp / "data" / "index.json", {"companies": rows})
    w(tmp / "data" / "c" / "1.json", co(1, "Q2 FY27", 9.62e10, 106, 66.2, 5.97e10, [("Data Center", 8.9e10), ("Edge Computing", 7.2e9)]))
    w(tmp / "data" / "c" / "2.json", co(2, "Q2 2026", 1.154e10, 50, 17.3, 2.3e9, [("Data Center", 6e9), ("Client", 5.5e9)]))
    w(tmp / "data" / "c" / "3.json", co(3, "Q2 2026", 1.3e10, -2, 1.0, -1e8, [("CCG", 8e9), ("DCAI", 5e9)]))
    w(tmp / "data" / "c" / "4.json", co(4, "Q3 2026", 1.338e10, 7, 33.4, 4.06e9, [("Concentrate operations", 8.2e9), ("Finished product operations", 5.18e9)]))
    for s in ("nvda", "amd"):
        w(tmp / "c" / s / "index.html", '<html lang="en"><head><link rel="canonical" href="x"></head><body><main class="seo">x</main></body></html>')
    return tmp


def test_compare(tmp_path):
    s = site(tmp_path)
    n = C.write(str(s), "https://example.com", k=1)
    assert n >= 2
    page = (s / "compare" / "nvda-vs-amd" / "index.html").read_text()               # a well-known rival pair, the larger first
    assert "NVIDIA is the larger company: $96.2B of revenue" in page and "NVIDIA is growing faster (+106% against +50%" in page
    assert '"FAQPage"' in page and "Which is more profitable, NVIDIA or Advanced Micro Devices?" in page
    assert not (s / "compare" / "amd-vs-nvda").exists()
    assert "compare/nvda-vs-amd/" in (s / "c" / "nvda" / "index.html").read_text()
    assert "sitemap-compare.xml" in (s / "robots.txt").read_text()


def test_zh(tmp_path):
    s = site(tmp_path)
    assert Z.write(str(s), "https://example.com") == 4
    nv = (s / "zh" / "c" / "nvda" / "index.html").read_text()
    assert '<html lang="zh-Hans">' in nv and "<h1>英伟达（NVDA）2027财年第二季度财报" in nv
    assert "营收 962 亿美元，同比增长 106%" in nv and "Data Center 890 亿美元（93%）" in nv
    assert 'hreflang="en" href="https://example.com/c/nvda/"' in nv
    assert "<h1>超威半导体（AMD）2026年第二季度财报" in (s / "zh" / "c" / "amd" / "index.html").read_text()
    en = (s / "c" / "nvda" / "index.html").read_text()
    assert 'hreflang="zh-Hans" href="https://example.com/zh/c/nvda/"' in en and "中文版：英伟达（NVDA）财报" in en
    assert "热门公司" in (s / "zh" / "index.html").read_text()
    assert (s / "sitemap-zh.xml").read_text().count("<url>") == 5
    assert Z.yuan(9.622e10) == "962.2 亿美元" and Z.yuan(9.62e10) == "962 亿美元" and Z.yuan(5.3e6) == "530 万美元" and Z.period("FY2025") == "2025财年"
