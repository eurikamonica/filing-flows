"""Comparison pages for search engines: "NVIDIA vs AMD" for each company and its nearest peers in the same industry (SEC
SIC code, closest in revenue), side by side from their latest filings — revenue, growth, margins, net earnings, cash
flow, the largest segments, and, when the Disclosure Hub has them, market value, P/E and the analysts' target.

    compare/<a>-vs-<b>/   the larger company by revenue first (one page per pair)
    compare/              every comparison, by industry
    sitemap-compare.xml (robots.txt, IndexNow); a "Compare with" block on each company's c/<slug>/ page

    python scripts/seo_compare.py --site _site --site-url https://filing-flows.com [--peers 3]
"""
import argparse
import html as H
import json
import math
import os
import re
import sys
from xml.sax.saxutils import escape as xesc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seo  # noqa: E402
import seo_svg as SV  # noqa: E402
from seo_history import sankey_figure  # noqa: E402

e, display_name, slug_for, fdate = seo.e, seo.display_name, seo.slug_for, seo.fdate


def read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def money(v):
    return '—' if v is None else (('−' if v < 0 else '') + f'${abs(v) / 1e12:.2f}T') if abs(v) >= 1e12 else seo.money(v)


def pct(v, signed=False):
    return '—' if v is None else (f'{v:+.0f}%' if signed else f'{v:.1f}%')


def figures(c):
    """The comparable figures of a company's latest quarter (data/c/<cik>.json)."""
    qs = (c or {}).get('quarters') or []
    if not qs:
        return None
    q = qs[0]
    h = q.get('headline') or {}
    if not h.get('revenue'):
        return None
    into, lab = {}, {n['id']: H.unescape(n.get('label') or n.get('name') or n['id']) for n in q.get('nodes') or []}
    segs = {}
    for ln in q.get('links') or []:
        into[ln['t']] = into.get(ln['t'], 0) + (ln.get('v') or 0)
        if ln['t'] == 'revenue':
            segs[lab.get(ln['s'], ln['s'])] = segs.get(lab.get(ln['s'], ln['s']), 0) + (ln.get('v') or 0)
    rev = h['revenue']
    g = lambda k: into.get(k)    # noqa: E731
    return {'label': q.get('label'), 'filed': q.get('filed'), 'form': q.get('form'), 'revenue': rev, 'yoy': h.get('yoy'),
            'om': h.get('om'), 'ni': h.get('ni'), 'ocf': h.get('ocf'), 'gm': (100 * g('gp') / rev) if g('gp') else None,
            'nm': (100 * h['ni'] / rev) if h.get('ni') is not None else None, 'fcf': g('fcf'),
            'segs': sorted(segs.items(), key=lambda x: -x[1])[:4] if len(segs) > 1 else []}


# rivals people search as "X vs Y", whatever their revenue gap or industry code
FAMOUS = [('NVDA', 'AMD'), ('AMD', 'INTC'), ('NVDA', 'INTC'), ('AAPL', 'MSFT'), ('MSFT', 'GOOGL'), ('GOOGL', 'META'), ('AMZN', 'WMT'), ('WMT', 'COST'), ('WMT', 'TGT'),
          ('KO', 'PEP'), ('V', 'MA'), ('HD', 'LOW'), ('MCD', 'SBUX'), ('MCD', 'CMG'), ('TSLA', 'GM'), ('TSLA', 'F'), ('GM', 'F'), ('UBER', 'LYFT'), ('UBER', 'DASH'),
          ('NFLX', 'DIS'), ('JPM', 'BAC'), ('JPM', 'WFC'), ('GS', 'MS'), ('XOM', 'CVX'), ('PFE', 'MRK'), ('LLY', 'NVO'), ('CRM', 'ORCL'), ('ADBE', 'CRM'),
          ('ABNB', 'BKNG'), ('COIN', 'HOOD'), ('PYPL', 'XYZ'), ('NKE', 'LULU'), ('UPS', 'FDX'), ('T', 'VZ'), ('TMUS', 'VZ'), ('PG', 'CL'), ('BA', 'LMT'),
          ('AVGO', 'QCOM'), ('MU', 'WDC'), ('PLTR', 'SNOW'), ('CRWD', 'PANW'), ('ORCL', 'MSFT'), ('AMZN', 'MSFT'), ('META', 'SNAP'), ('SPOT', 'NFLX'),
          ('DELL', 'HPQ'), ('CAT', 'DE'), ('UNH', 'CVS'), ('ABBV', 'BMY'), ('MRNA', 'PFE'), ('AAL', 'DAL'), ('DAL', 'UAL'), ('MAR', 'HLT'), ('LULU', 'ONON')]


def pairs(rows, k=3):
    """Each company with its k nearest peers by revenue in the same SIC code (same industry name when no code); the
    larger first, each pair once."""
    by = {}
    for r in rows:
        if (r.get('revenue') or 0) > 0 and r.get('ticker'):
            by.setdefault(r.get('sic') or r.get('industry') or '', []).append(r)
    out = {}
    for grp, L in by.items():
        if not grp or len(L) < 2:
            continue
        L = sorted(L, key=lambda r: -r['revenue'])
        for i, r in enumerate(L):
            near = sorted((x for x in L if x is not r), key=lambda x: abs(math.log(x['revenue'] / r['revenue'])))[:k]
            for x in near:
                a, b = (r, x) if r['revenue'] >= x['revenue'] else (x, r)
                out.setdefault((a['cik'], b['cik']), (a, b))
    by_t = {r['ticker']: r for r in rows if (r.get('revenue') or 0) > 0 and r.get('ticker')}
    for x, y in FAMOUS:
        if x in by_t and y in by_t:
            a, b = sorted((by_t[x], by_t[y]), key=lambda r: -r['revenue'])
            out.setdefault((a['cik'], b['cik']), (a, b))
    return list(out.values())


def page_for(a, b, fa, fb, va, vb, base):
    na, nb = display_name(a.get('name')), display_name(b.get('name'))
    ta, tb = a['ticker'], b['ticker']
    url = f"{base}/compare/{slug_for(a)}-vs-{slug_for(b)}/"
    bigger = f"{na} is the larger company: {money(fa['revenue'])} of revenue in its latest quarter ({fa['label']}) against {money(fb['revenue'])} for {nb} ({fb['label']})."
    parts = [bigger]
    if fa.get('yoy') is not None and fb.get('yoy') is not None:
        fast, slow = (na, nb) if fa['yoy'] >= fb['yoy'] else (nb, na)
        parts.append(f"{fast} is growing faster ({pct(max(fa['yoy'], fb['yoy']), True)} against {pct(min(fa['yoy'], fb['yoy']), True)} a year earlier).")
    if fa.get('om') is not None and fb.get('om') is not None:
        hi = na if fa['om'] >= fb['om'] else nb
        parts.append(f"{hi} is more profitable, with an operating margin of {pct(max(fa['om'], fb['om']))} against {pct(min(fa['om'], fb['om']))}.")
    lead = ' '.join(parts)
    rows = [('Latest quarter', fa['label'], fb['label']), ('Revenue', money(fa['revenue']), money(fb['revenue'])),
            ('Revenue growth, Y/Y', pct(fa.get('yoy'), True), pct(fb.get('yoy'), True)), ('Gross margin', pct(fa.get('gm')), pct(fb.get('gm'))),
            ('Operating margin', pct(fa.get('om')), pct(fb.get('om'))), ('Net earnings', money(fa.get('ni')), money(fb.get('ni'))),
            ('Net margin', pct(fa.get('nm')), pct(fb.get('nm'))), ('Operating cash flow', money(fa.get('ocf')), money(fb.get('ocf'))),
            ('Free cash flow', money(fa.get('fcf')), money(fb.get('fcf')))]
    if va or vb:
        va, vb = va or {}, vb or {}
        rows += [('Market value', money(va.get('mcap')), money(vb.get('mcap'))),
                 ('P/E', f"{va['pe']:.1f}×" if va.get('pe') else '—', f"{vb['pe']:.1f}×" if vb.get('pe') else '—'),
                 ('Analysts’ mean target', f"${va['target_mean']:.2f}" if va.get('target_mean') else '—', f"${vb['target_mean']:.2f}" if vb.get('target_mean') else '—')]
    tbl = (f"<div class='tbl-wrap'><table><thead><tr><th></th><th class='num'>{e(na)} ({e(ta)})</th><th class='num'>{e(nb)} ({e(tb)})</th></tr></thead><tbody>"
           + ''.join(f"<tr><td>{e(k)}</td><td class='num'>{e(x)}</td><td class='num'>{e(y)}</td></tr>" for k, x, y in rows) + '</tbody></table></div>')
    seg = ''
    for n_, f in ((na, fa), (nb, fb)):
        if f['segs']:
            seg += f"<h3>{e(n_)}</h3><ul class='seo-list'>" + ''.join(f"<li>{e(s)}: {e(money(v))} ({100 * v / f['revenue']:.0f}%)</li>" for s, v in f['segs']) + '</ul>'
    qa = [(f"Which is bigger, {na} or {nb}?", bigger)]
    if len(parts) > 1:
        qa.append((f"Is {na} or {nb} growing faster?", parts[1]))
    if len(parts) > 2:
        qa.append((f"Which is more profitable, {na} or {nb}?", parts[2]))
    sa, sb = slug_for(a), slug_for(b)
    body = (f"<p class='crumbs'><a href='../../'>Filing Flows</a> › <a href='../'>Comparisons</a> › {e(ta)} vs {e(tb)}</p>"
            f"<h1>{e(na)} vs {e(nb)}: {e(ta)} and {e(tb)} compared</h1><p class='lead'>{e(lead)}</p>"
            + SV.pair([('Revenue', fa.get('revenue'), fb.get('revenue'), money), ('Revenue growth, Y/Y', fa.get('yoy'), fb.get('yoy'), lambda v: pct(v, True)),
                       ('Gross margin', fa.get('gm'), fb.get('gm'), pct), ('Operating margin', fa.get('om'), fb.get('om'), pct),
                       ('Net margin', fa.get('nm'), fb.get('nm'), pct), ('Free cash flow', fa.get('fcf'), fb.get('fcf'), money)],
                      (f'{na} ({ta})', f'{nb} ({tb})'), f'{na} vs {nb}, latest quarter')
            + f"<h2>Where the money goes: {e(ta)} and {e(tb)}</h2><div class='seo-two'>"
            + ''.join(f"<div><h3>{e(n_)} ({e(tk)}) · {e(f_['label'])}</h3>" + sankey_figure(x['cik'], f_['label'], f"{n_} {f_['label']} Sankey", up='../../') + '</div>'
                      for n_, tk, x, f_ in ((na, ta, a, fa), (nb, tb, b, fb)))
            + "</div>"
            + ''.join(SV.hbars(list(f_['segs']), money, f"{n_} revenue by segment, {f_['label']}") for n_, f_ in ((na, fa), (nb, fb)) if len(f_['segs'] or []) > 1)
            + f"{tbl}"
            + (f"<h2>Where the revenue comes from</h2>{seg}" if seg else '')
            + '<h2>Questions</h2>' + ''.join(f'<h3>{e(q)}</h3><p>{e(x)}</p>' for q, x in qa)
            + f"<p>More: <a href='../../c/{sa}/'>{e(na)} earnings</a> · <a href='../../c/{sa}/revenue/'>how {e(na)} makes money</a> · "
              f"<a href='../../c/{sb}/'>{e(nb)} earnings</a> · <a href='../../c/{sb}/revenue/'>how {e(nb)} makes money</a></p>"
            + f"<p class='muted'>From the companies' latest 10-Q, 10-K or earnings release ({e(fa['form'])} filed {e(fdate(fa['filed']))}; {e(fb['form'])} filed {e(fdate(fb['filed']))}). "
              "Fiscal quarters can end on different dates. Not investment advice.</p>")
    mod = max(fa.get('filed') or '', fb.get('filed') or '')[:10] or None
    ld = {'@context': 'https://schema.org', '@graph': [
        {'@type': 'BreadcrumbList', 'itemListElement': [{'@type': 'ListItem', 'position': 1, 'name': 'Filing Flows', 'item': base + '/'},
                                                         {'@type': 'ListItem', 'position': 2, 'name': 'Comparisons', 'item': base + '/compare/'},
                                                         {'@type': 'ListItem', 'position': 3, 'name': f'{ta} vs {tb}', 'item': url}]},
        {'@type': 'FAQPage', 'mainEntity': [{'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': x}} for q, x in qa]}]}
    title = f"{na} vs {nb} ({ta} vs {tb}): revenue, growth and margins compared | Filing Flows"
    return url, mod, seo.page(title, lead[:300], url, body, 2, base + '/og.png', ld)


def write(site, base, k=3):
    base = base.rstrip('/')
    ix = read(os.path.join(site, 'data', 'index.json')) or {}
    latest = {}
    for r in (ix.get('companies') if isinstance(ix, dict) else ix) or []:
        if r['cik'] not in latest or (r.get('filed') or '') > (latest[r['cik']].get('filed') or ''):
            latest[r['cik']] = r
    vix = read(os.path.join(site, 'disclosures', 'data', 'research', 'valuation', 'index.json')) or {}
    vF = vix.get('fields') or []
    val = {r[vF.index('cik')]: dict(zip(vF, r)) for r in vix.get('rows') or []} if vF else {}
    figs, urls, by_co, by_ind = {}, [], {}, {}

    def fig(r):
        if r['cik'] not in figs:
            figs[r['cik']] = figures(read(os.path.join(site, 'data', 'c', f"{r['cik']}.json")))
        return figs[r['cik']]
    for a, b in pairs(list(latest.values()), k):
        fa, fb = fig(a), fig(b)
        if not fa or not fb:
            continue
        url, mod, doc = page_for(a, b, fa, fb, val.get(a['cik']), val.get(b['cik']), base)
        d = os.path.join(site, 'compare', f"{slug_for(a)}-vs-{slug_for(b)}")
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'index.html'), 'w', encoding='utf-8').write(doc)
        urls.append((url, mod))
        for x, y in ((a, b), (b, a)):
            by_co.setdefault(x['cik'], []).append((y, f"{slug_for(a)}-vs-{slug_for(b)}"))
        by_ind.setdefault(a.get('industry') or 'Other', []).append((a, b))
    for cik, L in by_co.items():                                       # the company page links to its comparisons
        r = latest[cik]
        main = os.path.join(site, 'c', slug_for(r), 'index.html')
        try:
            txt = open(main, encoding='utf-8').read()
        except OSError:
            continue
        if 'class="seo-compare"' in txt or '</main>' not in txt:
            continue
        block = (f'<section class="seo-compare"><h2>Compare {e(r["ticker"])} with</h2><ul class="seo-list">'
                 + ''.join(f"<li><a href='../../compare/{s}/'>{e(display_name(r.get('name')))} vs {e(display_name(y.get('name')))} ({e(r['ticker'])} vs {e(y['ticker'])})</a></li>" for y, s in L[:6])
                 + '</ul></section>')
        open(main, 'w', encoding='utf-8').write(txt.replace('</main>', block + '</main>', 1))
    if urls:
        lis = ''.join(f"<h2>{e(ind)}</h2><ul class='seo-list'>" + ''.join(
            f"<li><a href='{slug_for(a)}-vs-{slug_for(b)}/'>{e(display_name(a.get('name')))} vs {e(display_name(b.get('name')))}</a></li>" for a, b in L) + '</ul>'
            for ind, L in sorted(by_ind.items()))
        body = (f"<p class='crumbs'><a href='../'>Filing Flows</a> › Comparisons</p><h1>Company comparisons</h1>"
                f"<p class='lead'>{len(urls):,} side-by-side comparisons of US-listed companies and their closest peers in the same industry: revenue, growth, margins and cash flow from their latest filings.</p>{lis}")
        open(os.path.join(site, 'compare', 'index.html'), 'w', encoding='utf-8').write(seo.page(
            'Company comparisons: revenue, growth and margins side by side | Filing Flows', f'{len(urls):,} comparisons of US-listed companies with their closest industry peers, from SEC filings.',
            base + '/compare/', body, 1, base + '/og.png'))
        urls.insert(0, (base + '/compare/', None))
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f'<url><loc>{xesc(u)}</loc>' + (f'<lastmod>{m}</lastmod>' if m else '') + '</url>' for u, m in urls]
    sm.append('</urlset>')
    open(os.path.join(site, 'sitemap-compare.xml'), 'w', encoding='utf-8').write('\n'.join(sm))
    robots = os.path.join(site, 'robots.txt')
    txt = open(robots).read() if os.path.exists(robots) else f'User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n'
    if 'sitemap-compare.xml' not in txt:
        open(robots, 'w').write(txt.rstrip('\n') + f'\nSitemap: {base}/sitemap-compare.xml\n')
    return max(0, len(urls) - 1)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', default='_site')
    ap.add_argument('--site-url', default=os.environ.get('SITE_URL', '') or 'https://filing-flows.com')
    ap.add_argument('--peers', type=int, default=3)
    a = ap.parse_args()
    m = re.search(r'https?://[^\s"]+', a.site_url or '')
    print(f"comparison pages: {write(a.site, m.group(0) if m else 'https://filing-flows.com', a.peers)}")
