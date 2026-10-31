"""A cash-flow analysis page per company (c/<slug>/cash-flow/), from the cash-flow statements it filed (SEC XBRL,
pipeline/quality.py → quality.cap and quality.q in data/c/<cik>.json):

    free cash flow quarter by quarter (operating cash flow less capital spending) and against a year earlier
    where the cash came from and went, latest quarter and trailing twelve months
    profit to cash: the bridge from net income to operating cash flow (non-cash charges, working capital)
    working capital: days of receivables, inventory and payables, and the cash conversion cycle
    the quarter-by-quarter table, and the company's Sankey

Every sentence on the page is computed from the company's own figures, so no two pages say the same thing.
Pages are written only for companies with at least four quarters of cash-flow statements.

    python scripts/seo_cashflow.py --site _site
"""
import argparse
import json
import os
import re
import sys
from xml.sax.saxutils import escape as xesc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seo  # noqa: E402
import seo_svg as SV  # noqa: E402
import seo_charts as SC  # noqa: E402
import seo_history as SH  # noqa: E402

e, display_name, fdate = seo.e, seo.display_name, seo.fdate
BRIDGE = {'da': 'Depreciation & amortization', 'sbc': 'Stock-based pay', 'dtax': 'Deferred taxes', 'impair': 'Impairments', 'other_nc': 'Other non-cash',
          'd_ar': 'Receivables', 'd_inv': 'Inventory', 'd_ap': 'Payables', 'd_accr': 'Accrued liabilities', 'd_contract': 'Deferred revenue',
          'd_other': 'Other working capital', 'gain': 'Gains on sales', 'equity_inc': 'Equity-method income'}


def money(v):
    return seo.money(v)


def fcf(p):
    it = (p or {}).get('items') or {}
    return None if it.get('ocf') is None else it['ocf'] + (it.get('capex') or 0)


def analysis(name, qs, ttm, qq):
    """the sentences: what this company's cash did, from its own numbers"""
    out = []
    last = qs[-1]
    it = last['items']
    f = fcf(last)
    yago = next((x for x in qs[:-1] if x.get('end', '')[:4] == str(int(last['end'][:4]) - 1) and x.get('end', '')[5:] == last['end'][5:]), None)
    s = f"In {last['label']}, {name} generated {money(it.get('ocf'))} of operating cash flow"
    if it.get('capex'):
        s += f" and spent {money(-it['capex'])} on capital projects, leaving free cash flow of {money(f)}"
    s += '.'
    if yago and fcf(yago) is not None and f is not None:
        d = f - fcf(yago)
        s += f" That is {money(abs(d))} {'more' if d > 0 else 'less'} than in {yago['label']} ({money(fcf(yago))})."
    out.append(s)
    if ttm and ttm.get('items'):
        ti = ttm['items']
        uses = sorted(((SC.CASH.get(k, k).lower(), -v) for k, v in ti.items() if v and v < 0 and k not in ('cash', 'fx', 'unrec')), key=lambda kv: -kv[1])
        srcs = sorted(((SC.CASH.get(k, k).lower(), v) for k, v in ti.items() if v and v > 0 and k not in ('ocf', 'cash', 'fx', 'unrec')), key=lambda kv: -kv[1])
        s = f"Over the twelve months to {fdate(ttm.get('end'))}, operating cash flow was {money(ti.get('ocf'))}"
        if uses:
            s += '; the largest uses were ' + ', '.join(f"{k} ({money(v)})" for k, v in uses[:3])
        if srcs:
            s += '; besides operations, cash came from ' + ', '.join(f"{k} ({money(v)})" for k, v in srcs[:2])
        if ti.get('cash'):
            s += f"; the cash balance {'fell' if ti['cash'] > 0 else 'rose'} by {money(abs(ti['cash']))}"
        out.append(s + '.')
    q = [x for x in qq if x.get('ni') and x.get('ocf') is not None]
    if q:
        x = q[-1]
        r = x['ocf'] / x['ni'] if x['ni'] > 0 else None
        s = f"Operating cash flow was {money(x['ocf'])} against net income of {money(x['ni'])}"
        if r is not None:
            s += f" — {r:.1f}× profit, " + ('cash ran ahead of reported earnings.' if r >= 1.1 else 'roughly in line with earnings.' if r >= 0.9 else 'less cash than reported earnings, worth checking against working capital.')
        else:
            s += '.'
        items = sorted(((x.get('bridge') or {}).get('items') or []), key=lambda i: -abs(i[1]))
        if items:
            s += ' The largest differences: ' + ', '.join(f"{BRIDGE.get(k, k).lower()} {'+' if v > 0 else '−'}{money(abs(v))}" for k, v, *_ in items[:3]) + '.'
        out.append(s)
        wc = x.get('wc') or {}
        if wc.get('ccc') is not None:
            out.append(f"Its cash conversion cycle was {wc['ccc']:.0f} days (receivables {wc.get('dso') or 0:.0f} + inventory {wc.get('dio') or 0:.0f} − payables "
                       f"{wc.get('dpo') or 0:.0f})" + (': suppliers fund its working capital.' if wc['ccc'] < 0 else '.'))
    return out


def page_for(c, row, slug, base):
    Q = c.get('quality') or {}
    cap = Q.get('cap') or {}
    qs = [x for x in cap.get('q') or [] if (x.get('items') or {}).get('ocf') is not None]
    if len(qs) < 4:
        return None
    qq = [x for x in Q.get('q') or [] if x.get('label')]
    p = c.get('profile') or {}
    name = display_name(p.get('name') or row.get('name'))
    tk = row.get('ticker') or ''
    ttm = cap.get('ttm')
    last = qs[-1]
    f = fcf(last)
    lines = analysis(name, qs, ttm, qq)
    wc = (qq[-1].get('wc') if qq else None) or {}
    ttf = fcf(ttm) if ttm else None
    url = f"{base}/c/{slug}/cash-flow/"
    title = f"{name}{' (' + tk + ')' if tk else ''} cash flow {last['label']}: free cash flow, capex and where the cash went"
    desc = ' '.join(lines)[:300]
    body = (f"<p class='crumbs'><a href='../../../'>Filing Flows</a> › <a href='../../'>Companies</a> › <a href='../'>{e(name)}</a> › Cash flow</p>"
            f"<h1>{e(name)} cash flow, quarter by quarter</h1><p class='muted'>Latest: {e(last['label'])} · from the cash-flow statements filed with the SEC</p>"
            f"<p class='seo-hl {'up' if (f or 0) >= 0 else 'down'}'><span>Free cash flow</span><b>{money(f)}</b> in {e(last['label'])}"
            + (f" · <b>{money(ttf)}</b> over twelve months" if ttf is not None else '') + '</p>'
            "<nav class='seo-toc'><a href='#analysis'>Analysis</a><a href='#fcf'>Free cash flow</a><a href='#where'>Where it went</a><a href='#bridge'>Profit to cash</a>"
            "<a href='#table'>Every quarter</a><a href='#sankey'>Sankey</a></nav>")
    body += "<div class='seo-tiles'>" + ''.join(f"<div class='seo-tile'><span>{e(k)}</span><b>{e(v)}</b></div>" for k, v in [
        ('Operating cash flow', money(last['items'].get('ocf'))), ('Capital spending', money(last['items'].get('capex'))),
        ('Free cash flow', ('+' if (f or 0) > 0 else '') + money(f)),
        ('Cash / net income', f"{qq[-1]['ocf'] / qq[-1]['ni']:.1f}×" if qq and qq[-1].get('ni') and qq[-1]['ni'] > 0 and qq[-1].get('ocf') is not None else None),
        ('Cash conversion cycle', f"{wc['ccc']:.0f} days" if wc.get('ccc') is not None else None)] if v not in (None, '—')) + '</div>'
    body += "<h2 id='analysis'>Analysis</h2><div class='seo-note'>" + ''.join(f"<p>{e(s)}</p>" for s in lines) + '</div>'
    body += "<h2 id='fcf'>Free cash flow</h2><div class='seo-grid'>"
    body += SV.bars([(x['label'], fcf(x)) for x in qs], money, f"{name}: free cash flow by quarter", note='Operating cash flow less capital spending.')
    body += SV.duo([(x['label'], x['items'].get('ocf'), -(x['items'].get('capex') or 0)) for x in qs], ('Operating cash flow', 'Capital spending'), money,
                   f"{name}: operating cash flow against capital spending")
    body += '</div>'
    body += "<h2 id='where'>Where the cash came from and went</h2><div class='seo-grid'>"
    for per in (last, ttm):
        if per and per.get('items'):
            body += SV.diverging(sorted(((SC.CASH.get(k, k), v) for k, v in per['items'].items() if k in SC.CASH and v), key=lambda kv: -abs(kv[1])), money,
                                 f"{name}: sources (+) and uses (−) of cash, {per.get('label')}", n=12)
    body += '</div>'
    bq = [x for x in qq if (x.get('bridge') or {}).get('items')]
    if bq:
        x = bq[-1]
        b = x['bridge']
        body += (f"<h2 id='bridge'>From profit to cash</h2>" + SV.diverging([('Net income', b.get('start'))] + [(BRIDGE.get(k, k), v) for k, v, *_ in b['items'] if v]
                                                                            + [('Operating cash flow', x.get('ocf'))], money,
                                                                            f"{name}: net income to operating cash flow, {x['label']}", n=14,
                                                                            note='Non-cash charges are added back; money tied up in receivables or inventory is subtracted.'))
        wq = [y for y in qq if (y.get('wc') or {}).get('ccc') is not None]
        if len(wq) >= 2:
            body += seo_table(['Quarter', 'Receivable days', 'Inventory days', 'Payable days', 'Cash conversion cycle'], [
                [e(y['label']), f"{y['wc'].get('dso') or 0:.0f}", f"{y['wc'].get('dio') or 0:.0f}" if y['wc'].get('has_inv') else '—', f"{y['wc'].get('dpo') or 0:.0f}",
                 f"{y['wc']['ccc']:.0f}"] for y in reversed(wq)])
    cols = [k for k in ('ocf', 'capex', 'acq', 'buyback', 'div', 'borrow', 'stock', 'cash') if any((x['items'].get(k) for x in qs))]
    body += "<h2 id='table'>Every quarter</h2>" + seo_table(['Quarter'] + [SC.CASH[k] for k in cols] + ['Free cash flow'], [
        [e(x['label'])] + [money(x['items'].get(k)) if x['items'].get(k) is not None else '—' for k in cols] + [money(fcf(x))] for x in reversed(qs)])
    body += (f"<h2 id='sankey'>{e(name)}: income statement and cash flow</h2>"
             + SH.sankey_figure(row['cik'], row.get('label') or '', f"{name} earnings and cash flow Sankey", up='../../../')
             + f"<p><a class='seo-cta' href='../'>{e(name)}: every quarter, Q/Q and Y/Y →</a> <a href='../../../#c-{row['cik']}'>Open in the app</a></p>"
             "<p class='muted'>Read automatically from the company’s XBRL cash-flow statements; quarterly figures for the fourth quarter are the year less the first three. "
             "Errors are possible. Not investment advice.</p>")
    ld = {'@context': 'https://schema.org', '@graph': [
        {'@type': 'BreadcrumbList', 'itemListElement': [{'@type': 'ListItem', 'position': 1, 'name': 'Filing Flows', 'item': base + '/'},
                                                         {'@type': 'ListItem', 'position': 2, 'name': name, 'item': f"{base}/c/{slug}/"},
                                                         {'@type': 'ListItem', 'position': 3, 'name': 'Cash flow', 'item': url}]},
        {'@type': 'WebPage', 'name': title, 'url': url, 'dateModified': row.get('filed') or last.get('end'), 'description': desc,
         'about': {'@type': 'Corporation', 'name': name, **({'tickerSymbol': tk} if tk else {})}}]}
    return seo.page(f"{title} | Filing Flows", desc, url, body, 3, f"{base}/og.png", ld), row.get('filed') or last.get('end')


def seo_table(head, rows):
    return (f"<div class='tbl-wrap'><table><thead><tr>{''.join(f'<th>{e(h)}</th>' for h in head)}</tr></thead><tbody>"
            + ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in rows) + '</tbody></table></div>')


def link_from_company(site, slug):
    """the company's page links to its cash-flow page (in the table of contents)"""
    p = os.path.join(site, 'c', slug, 'index.html')
    if not os.path.exists(p):
        return
    t = open(p, encoding='utf-8').read()
    if 'cash-flow/' in t:
        return
    t = t.replace('<nav class="seo-toc" aria-label="On this page">', '<nav class="seo-toc" aria-label="On this page"><a href="cash-flow/">Cash flow</a>', 1)
    open(p, 'w', encoding='utf-8').write(t)


def _view(v):
    """a lab view → ({id: label}, links [(src, tgt, value, grade)])"""
    return {n[0]: n[2] for n in v.get('nodes') or []}, [(l[0], l[1], l[2], l[3]) for l in v.get('links') or []]


def industry_pages(site, base, capex):
    """gamma/<sic>/supply-chain/: the industry's capital spending (filed, by company), what it buys (asset types and the
    industries that build them), its suppliers two steps up (BEA input-output), its filed cash flow, and the customer and
    supplier links its companies name in their annual reports"""
    urls = []
    gi = read(os.path.join(site, 'data', 'gamma', 'index.json')) or {}
    for ind in gi.get('industries') or []:
        sic = ind['sic']
        fl = read(os.path.join(site, 'data', 'gamma', 'flowlab', f"{sic}.json"))
        g = read(os.path.join(site, 'data', 'gamma', f"{sic}.json")) or {}
        if not fl or not os.path.exists(os.path.join(site, 'gamma', sic, 'index.html')):
            continue
        try:
            out = industry_page(sic, ind, fl, g, capex, base)
        except Exception as err:  # noqa: BLE001
            print(f"supply-chain page skipped (SIC {sic}): {err}")
            continue
        if not out:
            continue
        d = os.path.join(site, 'gamma', sic, 'supply-chain')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(out)
        p = os.path.join(site, 'gamma', sic, 'index.html')
        t = open(p, encoding='utf-8').read()
        if 'supply-chain/' not in t:
            t = t.replace('<h2>Companies</h2>', "<p><a class='seo-cta' href='supply-chain/'>Capital spending and supply chain →</a></p><h2>Companies</h2>", 1)
            open(p, 'w', encoding='utf-8').write(t)
        urls.append((f"{base}/gamma/{sic}/supply-chain/", (gi.get('generated') or '')[:10] or None))
    return urls


def industry_page(sic, ind, fl, g, capex, base):
    views = fl.get('views') or {}
    name = ind.get('name') or g.get('name') or f"SIC {sic}"
    mem = [m for m in g.get('companies') or [] if int(m['cik']) in capex]
    cx = sorted(((capex[int(m['cik'])], m) for m in mem), key=lambda x: -(x[0][0] or 0))
    tot = sum(x[0][0] or 0 for x in cx)
    ocf = sum(x[0][1] or 0 for x in cx if x[0][1])
    if len(cx) < 2 or tot <= 0:
        return None
    rev = fl.get('revenue')
    body_ch, lines = [], []
    top3 = sum(x[0][0] for x in cx[:3]) / tot
    lines.append(f"{len(cx)} companies in {name} (SIC {sic}) spent {money(tot)} on capital projects over their latest twelve months, "
                 f"{tot / ocf * 100:.0f}% of the {money(ocf)} their operations generated" if ocf > 0 else
                 f"{len(cx)} companies in {name} (SIC {sic}) spent {money(tot)} on capital projects over their latest twelve months")
    lines[-1] += (f"; the three largest spenders — {', '.join(x[1].get('ticker') or display_name(x[1].get('name')) for x in cx[:3])} — account for {top3 * 100:.0f}%."
                  if len(cx) > 3 else '.')
    if rev:
        lines.append(f"Capital spending is {tot / rev * 100:.1f}% of the industry's {money(rev)} of annual revenue.")
    body_ch.append(SV.hbars([(x[1].get('ticker') or display_name(x[1].get('name')), x[0][0]) for x in cx], money, f"{name}: capital spending by company, latest twelve months",
                            n=12, color=SV.BLUE, note='Filed cash-flow statements (SEC XBRL).'))
    cv = views.get('capex')
    if cv:
        lab, ls = _view(cv)
        meta = cv.get('meta') or {}
        cls = meta.get('classes') or {}
        if cls:
            body_ch.append(SV.hbars([(k.capitalize(), v) for k, v in cls.items() if v], money, f"{name}: what the capital spending buys (US part)", n=6, color=SV.GREY,
                                    note='Capital spending × the industry’s asset mix (BEA fixed assets): grade C, an industry average applied to filed figures.'))
            big = max(cls.items(), key=lambda kv: kv[1])
            lines.append(f"By the industry's asset mix most of it goes to {big[0]} ({big[1] / sum(cls.values()) * 100:.0f}%)"
                         + (f"; about {money(meta['imports'])} is imported" if meta.get('imports') else '') + '.')
        build = {}
        for s, t_, v, gr in ls:
            if t_.startswith('s:') and not t_.endswith(':other'):
                build[lab.get(t_, t_)] = build.get(lab.get(t_, t_), 0) + v
        if build:
            body_ch.append(SV.hbars(sorted(build.items(), key=lambda kv: -kv[1]), money, f"{name}: the industries that build and sell what it buys", n=10, color=SV.GREY,
                                    note='BEA fixed assets: investment by asset type → supplying industry. Estimates (grade C).'))
            b = max(build.items(), key=lambda kv: kv[1])
            lines.append(f"The largest supplier of that spending is {b[0].lower()} ({money(b[1])}).")
    tv = views.get('tiers')
    if tv:
        lab, ls = _view(tv)
        t1 = {}
        for s, t_, v, gr in ls:
            if s == 'k:p' and t_.startswith('t1:') and t_ != 't1:other':
                t1[lab.get(t_, t_)] = v
        if t1:
            body_ch.append(SV.hbars(sorted(t1.items(), key=lambda kv: -kv[1]), money, f"{name}: its first-tier supplying industries", n=10,
                                    note='Purchased inputs × the industry’s input mix (BEA Use table), US part: grade C.'))
            ts = sorted(t1.items(), key=lambda kv: -kv[1])[:3]
            lines.append('Its largest supplying industries, by the input-output tables: ' + ', '.join(f"{k.lower()} ({money(v)})" for k, v in ts) + '.')
    cv2 = views.get('cash')
    if cv2:
        lab, ls = _view(cv2)
        items = [(lab.get(s, s), v) for s, t_, v, gr in ls if t_ == 'pool'] + [(lab.get(t_, t_), -v) for s, t_, v, gr in ls if s == 'pool']
        if items:
            body_ch.append(SV.diverging(sorted(items, key=lambda kv: -abs(kv[1])), money, f"{name}: where the industry's cash came from (+) and went (−)", n=14,
                                        note='The companies’ cash-flow statements, latest four quarters or fiscal year: every figure filed (grade A).'))
    rel = sorted(g.get('relationships') or [], key=lambda x: -(x.get('value_usd') or 0))
    body = (f"<p class='crumbs'><a href='../../../'>Filing Flows</a> › <a href='../../'>Industries</a> › <a href='../'>{e(name)}</a> › Capital spending and supply chain</p>"
            f"<h1>{e(name)}: capital spending and supply chain</h1><p class='muted'>SIC {e(sic)} · {len(cx)} companies with filed cash-flow statements</p>"
            "<div class='seo-tiles'>" + ''.join(f"<div class='seo-tile'><span>{e(k)}</span><b>{e(v)}</b></div>" for k, v in [
                ('Capital spending, 12 months', money(tot)), ('Operating cash flow', money(ocf)), ('Capex / cash flow', f"{tot / ocf * 100:.0f}%" if ocf > 0 else None),
                ('Capex / revenue', f"{tot / rev * 100:.1f}%" if rev else None), ('Top 3 share', f"{top3 * 100:.0f}%")] if v) + '</div>'
            + "<h2>Analysis</h2><div class='seo-note'>" + ''.join(f"<p>{e(s)}</p>" for s in lines) + '</div>'
            + "<h2>Charts</h2><div class='seo-grid'>" + ''.join(x for x in body_ch if x) + '</div>')
    body += "<h2>Capital spending by company</h2>" + seo_table(['Company', 'Capital spending', 'Operating cash flow', 'Capex / OCF', 'Period'], [
        [f"<a href='../../../c/{x[0][3]}/cash-flow/'>{e(x[1].get('ticker') or '')} {e(display_name(x[1].get('name')))}</a>", money(x[0][0]), money(x[0][1]),
         f"{x[0][0] / x[0][1] * 100:.0f}%" if x[0][1] and x[0][1] > 0 else '—', e(x[0][2] or '')] for x in cx[:60]])
    if rel:
        body += ("<h2>Customers and suppliers named in annual reports</h2>" + seo_table(['Supplier', 'Customer', 'Share of supplier revenue', 'Evidence', 'Source'], [
            [e(x.get('supplier')), e(x.get('customer')), f"{x['share'] * 100:.0f}%" if x.get('share') else '—', e(x.get('evidence_level') or ''),
             f"<a href='{e(x['source_url'])}' rel='nofollow'>filing</a>" if x.get('source_url') else ''] for x in rel[:40]]))
    body += (f"<p><a class='seo-cta' href='../../../#gamma-{e(sic)}'>The interactive money flow: switch views, follow each dollar →</a></p>"
             "<p class='muted'>Evidence grades: A filed figure · B computed from filed figures · C industry average (BEA input-output and fixed-asset tables) applied to filed "
             "figures. Estimates are not the companies’ own records. Not investment advice.</p>")
    url = f"{base}/gamma/{sic}/supply-chain/"
    title = f"{name} capital spending and supply chain: {money(tot)} capex, who supplies the industry"
    return seo.page(f"{title} | Filing Flows", ' '.join(lines)[:300], url, body, 3, base + '/og.png')


def read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write(site, base):
    base = base.rstrip('/')
    ix = json.load(open(os.path.join(site, 'data', 'index.json'), encoding='utf-8'))
    rows = ix.get('companies') if isinstance(ix, dict) else ix
    urls, capex = [], {}
    for r in rows:
        slug = seo.slug_for(r)
        if not os.path.exists(os.path.join(site, 'c', slug, 'index.html')):
            continue
        try:
            with open(os.path.join(site, 'data', 'c', f"{r['cik']}.json"), encoding='utf-8') as f:
                c = json.load(f)
            tt = ((c.get('quality') or {}).get('cap') or {}).get('ttm') or {}
            if (tt.get('items') or {}).get('capex') is not None:
                capex[int(r['cik'])] = (-tt['items']['capex'], tt['items'].get('ocf'), tt.get('label'), slug, r)
            out = page_for(c, r, slug, base)
        except Exception as err:  # noqa: BLE001
            print(f"cash-flow page skipped ({r.get('ticker') or r['cik']}): {err}")
            continue
        if not out:
            continue
        d = os.path.join(site, 'c', slug, 'cash-flow')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(out[0])
        link_from_company(site, slug)
        urls.append((f"{base}/c/{slug}/cash-flow/", out[1]))
    try:
        urls += industry_pages(site, base, capex)
    except Exception as err:  # noqa: BLE001
        print(f"industry supply-chain pages skipped: {err}")
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f'<url><loc>{xesc(u)}</loc>' + (f'<lastmod>{xesc(str(m)[:10])}</lastmod>' if m else '') + '</url>' for u, m in urls]
    sm.append('</urlset>')
    open(os.path.join(site, 'sitemap-cashflow.xml'), 'w', encoding='utf-8').write('\n'.join(sm))
    robots = os.path.join(site, 'robots.txt')
    txt = open(robots).read() if os.path.exists(robots) else f'User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n'
    if 'sitemap-cashflow.xml' not in txt:
        open(robots, 'w').write(txt.rstrip('\n') + f'\nSitemap: {base}/sitemap-cashflow.xml\n')
    return len(urls)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', default='_site')
    ap.add_argument('--site-url', default=os.environ.get('SITE_URL', '') or 'https://filing-flows.com')
    a = ap.parse_args()
    m = re.search(r'https?://[^\s"]+', a.site_url or '')
    print(f"cash-flow pages: {write(a.site, m.group(0) if m else 'https://filing-flows.com')}")
