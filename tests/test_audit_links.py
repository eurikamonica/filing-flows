"""scripts/audit_links.py: a built site's sitemaps, links, heads, text and titles."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_links as A  # noqa: E402

HEAD = '<html><head><title>{t}</title><meta name="description" content="d"><link rel="canonical" href="https://x.test/{p}"></head><body><h1>h</h1>{b}</body></html>'


def page(site, rel, title, body=''):
    d = site / rel
    d.mkdir(parents=True, exist_ok=True)
    (d / 'index.html').write_text(HEAD.format(t=title, p=rel, b=body))


def test_audit(tmp_path):
    s = tmp_path
    page(s, '', 'Home', "<a href='c/aaa/'>A</a> <a href='c/bbb/'>B</a> <a href='https://elsewhere.test/x'>x</a> <a href='#top'>t</a>")
    page(s, 'c/aaa/', 'Alpha', "<a href='../'>up</a> <a href='q2-2026-vs-q2-2025/'>Y/Y</a> <p>EPS $-0.24</p>")
    page(s, 'c/aaa/q2-2026/', 'Alpha', "<a href='https://x.test/c/aaa/'>abs</a>")
    page(s, 'c/', 'Companies')
    (s / 'robots.txt').write_text('Sitemap: https://x.test/sitemap.xml\nSitemap: https://x.test/sitemap-gone.xml\n')
    (s / 'sitemap.xml').write_text('<urlset><url><loc>https://x.test/c/aaa/</loc></url><url><loc>https://x.test/c/zzz/</loc></url></urlset>')
    r = A.audit(str(s), 'https://x.test')
    f = r['found']
    assert r['pages'] == 4 and r['sitemap_urls'] == 2
    assert any('sitemap-gone.xml' in x for x in f['sitemap']) and any('c/zzz/' in x for x in f['sitemap'])
    assert sorted(f['link']) == ['/ → c/bbb/', '/c/aaa/ → q2-2026-vs-q2-2025/']
    assert any('$-N' in x for x in f['text']) and not f['head']
    assert f['title'] and 'Alpha' in f['title'][0]
    assert A.main(['--site', str(s), '--site-url', 'https://x.test']) == 0
