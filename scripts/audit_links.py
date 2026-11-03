"""Link and page-structure audit of the built static site (run by scan.yml before publishing; it never stops the publish).

The page audit (scripts/audit_pages.py) checks what the charts say; this one checks how the pages hang together:
  sitemap    every Sitemap line in robots.txt names a file that exists, and every <loc> in it a page that exists
  link       every internal href/src on a page (a sample of the company pages, every other page) resolves to a file
  head       each page has one <title>, a meta description, a canonical address that is its own (or, for a page that
             is not to be indexed, any), parseable JSON-LD and one <h1>
  text       template leaks and number glitches in the visible text: None, NaN, undefined, "{…}", "$-0.24", "&amp;"
  title      two indexable pages with the same title
Prints a summary, the first findings of each kind as warnings (--github) and a table in the run's summary.

    python scripts/audit_links.py --site _site [--sample 4000] [--github]
"""
import argparse
import collections
import html
import json
import os
import random
import re
import sys
from urllib.parse import unquote, urlsplit

SKIP = ('data/', 'disclosures/data/', 'beta/', 'feeds/', 'media/', 'disclosures/docs/')
HREF = re.compile(r'''<(a|link|script|img|source|iframe)\b[^>]*?\s(href|src)=["']([^"']+)["']''', re.I)
TITLE = re.compile(r'<title>(.*?)</title>', re.S)
SMELLS = [(re.compile(r'>[^<]*\b(None|NaN|nan|undefined)\b[^<]*<'), 'None/NaN/undefined'), (re.compile(r'\$-\d'), '$-N (sign after $)'),
          (re.compile(r'&amp;(amp|lt|gt|#x?\d+);'), 'double-escaped entity'), (re.compile(r'>[^<]*\{[a-z_]+[\(\[\}][^<]*<|\$\{'), 'template leak')]


def pages(site):
    for root, dirs, files in os.walk(site):
        rel = os.path.relpath(root, site).replace(os.sep, '/')
        rel = '' if rel == '.' else rel + '/'
        if rel.startswith(SKIP):
            dirs[:] = []
            continue
        for f in files:
            if f == 'index.html':
                yield rel


def target(site, here, href, base):
    """the file a link points at, or None for links that are not ours to check"""
    u = urlsplit(href)
    if u.scheme in ('mailto', 'javascript', 'data', 'tel'):
        return None
    if u.scheme in ('http', 'https'):
        if not base or not href.startswith(base + '/'):
            return None
        p = unquote(u.path).lstrip('/')
        t = os.path.join(site, p)
    elif not u.path:
        return None
    else:
        p = unquote(u.path)
        t = os.path.normpath(os.path.join(site, p.lstrip('/')) if p.startswith('/') else os.path.join(site, here, p))
    if os.path.isdir(t) or t.endswith(os.sep):
        t = os.path.join(t, 'index.html')
    return t


def audit(site, base, sample=4000, seed=1):
    found = collections.defaultdict(list)
    # sitemaps
    robots = open(os.path.join(site, 'robots.txt'), encoding='utf-8').read() if os.path.exists(os.path.join(site, 'robots.txt')) else ''
    n_locs = 0
    for sm in re.findall(r'^Sitemap:\s*(\S+)', robots, re.M):
        f = os.path.join(site, urlsplit(sm).path.lstrip('/'))
        if not os.path.exists(f):
            found['sitemap'].append(f'robots.txt lists {sm}, which is not built')
            continue
        for loc in re.findall(r'<loc>([^<]+)</loc>', open(f, encoding='utf-8').read()):
            loc = html.unescape(loc)
            n_locs += 1
            p = urlsplit(loc).path
            if p.endswith('.xml'):
                if not os.path.exists(os.path.join(site, p.lstrip('/'))):
                    found['sitemap'].append(f'{os.path.basename(f)} lists {loc}, which is not built')
                continue
            t = os.path.join(site, unquote(p).lstrip('/'))
            if p.endswith('/') or os.path.isdir(t):
                t = os.path.join(t, 'index.html')
            if not os.path.exists(t):
                found['sitemap'].append(f'{os.path.basename(f)} lists {loc}, which is not built')
    # pages: every page of the smaller kinds, a sample of the company, translated and comparison pages
    allp = list(pages(site))
    many = ('c/', 'zh/', 'es/', 'fr/', 'compare/')      # thousands of pages each, all made the same way: a sample
    rest = [p for p in allp if not p.startswith(many)]
    comp = [p for p in allp if p.startswith(many)]
    random.Random(seed).shuffle(comp)
    todo = rest + comp[:max(0, sample)]
    titles = collections.defaultdict(list)
    checked_links = 0
    for rel in todo:
        try:
            src = open(os.path.join(site, rel, 'index.html'), encoding='utf-8').read()
        except (OSError, UnicodeDecodeError) as err:
            found['head'].append(f'{rel}: unreadable ({err})')
            continue
        head = src[:src.find('</head>')] if '</head>' in src else src[:4000]
        noindex = 'noindex' in head
        app = 'id="app"' in src or 'id="workspace"' in src
        m = TITLE.search(head)
        if not m:
            found['head'].append(f'/{rel}: no <title>')
        elif not noindex and not app:
            titles[html.unescape(m.group(1)).strip()].append(rel)
        if not noindex and not app:
            if 'name="description"' not in head:
                found['head'].append(f'/{rel}: no meta description')
            c = re.search(r'<link rel="canonical" href="([^"]+)"', head)
            if not c:
                found['head'].append(f'/{rel}: no canonical')
            elif base and c.group(1).rstrip('/') != f'{base}/{rel}'.rstrip('/'):
                found['head'].append(f'/{rel}: canonical is {c.group(1)}')
            n_h1 = len(re.findall(r'<h1\b', src))
            if n_h1 != 1:
                found['head'].append(f'/{rel}: {n_h1} <h1>')
        for j in re.findall(r'<script type="application/ld\+json">(.*?)</script>', src, re.S):
            try:
                json.loads(j)
            except ValueError as err:
                found['head'].append(f'/{rel}: JSON-LD does not parse ({err})')
        for _, _, href in HREF.findall(src):
            t = target(site, rel, html.unescape(href), base)
            if t is None:
                continue
            checked_links += 1
            if not os.path.exists(t):
                found['link'].append(f'/{rel} → {href}')
        body = src[len(head):]
        body = re.sub(r'<script\b.*?</script>|<style\b.*?</style>', '', body, flags=re.S)
        for rx, what in SMELLS:
            mm = rx.search(body)
            if mm:
                found['text'].append(f'/{rel}: {what}: …{re.sub(r"<[^>]+>", " ", body[max(0, mm.start() - 60):mm.end() + 30]).strip()[:120]}…')
    for t, rs in titles.items():
        if len(rs) > 1:
            found['title'].append(f'{len(rs)} pages titled "{t[:80]}": /{rs[0]} /{rs[1]}')
    return {'pages': len(allp), 'checked': len(todo), 'links': checked_links, 'sitemap_urls': n_locs, 'found': found}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--site', default='_site')
    ap.add_argument('--site-url', default=os.environ.get('SITE_URL', '') or 'https://filing-flows.com')
    ap.add_argument('--sample', type=int, default=4000, help='company, translated and comparison pages checked, at random; every other page is')
    ap.add_argument('--github', action='store_true')
    a = ap.parse_args(argv)
    m = re.search(r'https?://[^\s"\']+', a.site_url or '')
    base = (m.group(0) if m else '').rstrip('/')
    r = audit(a.site, base, a.sample)
    f = r['found']
    line = ', '.join(f'{k} {len(f.get(k, []))}' for k in ('sitemap', 'link', 'head', 'text', 'title'))
    print(f"link audit: {r['pages']} pages, {r['checked']} read, {r['links']} internal links, {r['sitemap_urls']} sitemap URLs — {line}")
    for k in ('sitemap', 'link', 'head', 'text', 'title'):
        for x in f.get(k, [])[:8]:
            print(f'::warning::link audit · {k} · {x}' if a.github else f'  {k}: {x}')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if a.github and summary:
        with open(summary, 'a', encoding='utf-8') as fh:
            fh.write(f"### Link audit\n{r['pages']} pages, {r['checked']} read, {r['links']} internal links, {r['sitemap_urls']} sitemap URLs: {line}\n\n")
            rows = [(k, x) for k in ('sitemap', 'link', 'head', 'text', 'title') for x in f.get(k, [])[:15]]
            if rows:
                fh.write('| check | finding |\n|---|---|\n' + ''.join(f"| {k} | {x.replace('|', '/')} |\n" for k, x in rows) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
