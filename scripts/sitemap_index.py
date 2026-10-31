"""sitemap-index.xml: every sitemap robots.txt lists, in one file — the one address to give Google Search Console and
Bing Webmaster Tools (each sitemap's newest <lastmod> is its own).

    python scripts/sitemap_index.py --site _site
"""
import argparse
import os
import re
from xml.sax.saxutils import escape


def write(site):
    robots = os.path.join(site, 'robots.txt')
    if not os.path.exists(robots):
        return 0
    txt = open(robots, encoding='utf-8').read()
    urls = [u for u in re.findall(r'(?im)^Sitemap:\s*(\S+)', txt) if not u.endswith('sitemap-index.xml')]
    rows = []
    for u in urls:
        path = os.path.join(site, u.rsplit('/', 1)[-1])
        if not os.path.exists(path):
            continue
        body = open(path, encoding='utf-8', errors='replace').read()
        mods = re.findall(r'<lastmod>([^<]{10})', body)
        rows.append(f'<sitemap><loc>{escape(u)}</loc>' + (f'<lastmod>{max(mods)}</lastmod>' if mods else '') + '</sitemap>')
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + '\n'.join(rows) + '\n</sitemapindex>\n')
    open(os.path.join(site, 'sitemap-index.xml'), 'w', encoding='utf-8').write(xml)
    if urls and 'sitemap-index.xml' not in txt:
        base = urls[0].rsplit('/', 1)[0]
        open(robots, 'w', encoding='utf-8').write(txt.rstrip('\n') + f'\nSitemap: {base}/sitemap-index.xml\n')
    return len(rows)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', default='_site')
    print('sitemap index:', write(ap.parse_args().site), 'sitemaps')
