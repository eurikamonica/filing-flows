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
          'd_other': 'Other working capital', 'gain': 'Gains on sales', 'equity_inc': 'Equity-method income',
          # the rest of the bridge's items (pipeline/fsa.py NONCASH and WC): without a label the page showed the field name
          'gain_inv': 'Gains on investments', 'gain_dis': 'Gains on disposals', 'd_emp': 'Employee-related liabilities',
          'd_casset': 'Contract assets', 'd_oassets': 'Prepaid and other assets', 'd_oliab': 'Other liabilities',
          'd_tax': 'Income taxes payable', 'd_onet': 'Other operating capital'}


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


def runway(c, qs, ttm):
    """Cash runway and the debt wall from the latest balance sheet (quality.val) and the maturity buckets (quality.cap.maturities):
    {cash, debt, net, fcf_ttm, fcf_q, burn, months, due12, buckets, label} or None when there is no balance sheet."""
    Q = c.get('quality') or {}
    v = Q.get('val') or {}
    cash = v.get('cash_all') if v.get('cash_all') is not None else ((v.get('b_cash') or 0) + (v.get('b_sti') or 0) if v.get('b_cash') is not None else None)
    if cash is None:
        return None
    debt = v.get('debt') if v.get('debt') is not None else (v.get('b_ltd') or 0) + (v.get('b_stb') or 0)
    f_ttm = fcf(ttm) if ttm else None
    f_q = fcf(qs[-1]) if qs else None
    ocf_ttm = ((ttm or {}).get('items') or {}).get('ocf')
    ocf_q = [(x.get('items') or {}).get('ocf') for x in qs[-4:]]
    # a runway is the question only when the business itself consumes cash. A company whose operations bring cash in and
    # whose capital spending is larger (Amazon, a utility building plant) funds the gap by choice, from cash and
    # borrowing: "0 months of runway" for Ameren or FirstEnergy said something false.
    burn = None
    if ocf_ttm is not None and ocf_ttm < 0 and f_ttm is not None and f_ttm < 0:
        burn = -f_ttm                                                   # a year's burn at the trailing rate
    elif ocf_q and ocf_q[-1] is not None and ocf_q[-1] < 0 and f_q is not None and f_q < 0 and sum(1 for x in ocf_q if x is not None and x < 0) >= 2:
        burn = -4 * f_q                                                 # operations turned to burning cash recently: the latest quarter annualised
    months = 12 * cash / burn if burn and cash > 0 else None           # no cash on file is a gap in the data, not zero months
    mat = (Q.get('cap') or {}).get('maturities') or {}
    buckets = [(b[0], b[1]) for b in mat.get('buckets') or [] if len(b) >= 2 and b[1]]
    due12 = next((a for k, a in buckets if k == 1), None)
    if due12 is None and v.get('b_ltd_c') is not None:
        due12 = (v.get('b_ltd_c') or 0) + (v.get('b_stb') or 0)
    return {'cash': cash, 'debt': debt, 'net': cash - (debt or 0), 'fcf_ttm': f_ttm, 'ocf_ttm': ocf_ttm, 'fcf_q': f_q, 'burn': burn, 'months': months, 'due12': due12,
            'buckets': buckets, 'label': mat.get('label'), 'at': v.get('end') or mat.get('at')}


def runway_section(name, rw):
    if not rw:
        return '', None
    tiles = [('Cash & investments', money(rw['cash'])), ('Debt', money(rw['debt']) if rw['debt'] else 'none'), ('Net cash' if rw['net'] >= 0 else 'Net debt', money(abs(rw['net']))),
             ('Due within a year', money(rw['due12']) if rw['due12'] else None)]
    if rw['months'] is not None:
        tiles.append(('Cash runway', f"{rw['months'] / 12:.1f} years" if rw['months'] >= 24 else seo.n_of(rw['months'], 'month')))
    if rw['burn'] and rw['months'] is not None:
        how = f"{name} is burning cash: its operations consume cash, a free cash flow of {money(-rw['burn'])} a year at the current rate"
        line = (how + f" against {money(rw['cash'])} of cash and investments: a runway of about <b>{rw['months'] / 12:.1f} years</b>" if rw['months'] >= 24 else
                how + f" against {money(rw['cash'])} of cash and investments: a runway of about <b>{seo.n_of(rw['months'], 'month')}</b>")
        if rw['due12']:
            line += f"; {money(rw['due12'])} of debt also comes due within a year, which {'the cash covers' if rw['cash'] >= rw['due12'] + rw['burn'] else 'would need refinancing or new money'}"
        line += ' before any new financing.'
    elif rw['burn']:
        line = f"{name}'s operations consume cash (free cash flow {money(-rw['burn'])} a year), and no cash balance is on file to set against it."
    elif (rw.get('fcf_ttm') or 0) < 0 and (rw.get('ocf_ttm') or 0) > 0:
        line = (f"{name}'s operations bring cash in ({money(rw['ocf_ttm'])} over twelve months), and it spends more than that on capital projects: a gap of "
                f"{money(-rw['fcf_ttm'])} funded from its {money(rw['cash'])} of cash and investments and from borrowing"
                + (f" ({money(rw['debt'])} of debt" + (f", {money(rw['due12'])} due within a year" if rw['due12'] else '') + ')' if rw['debt'] else '')
                + ". That is a choice to invest, not a cash runway running down.")
    else:
        line = (f"{name} funds itself: free cash flow was {money(rw['fcf_ttm'])} over the last twelve months"
                + (f", and {money(rw['cash'])} of cash and investments stands against {money(rw['debt'])} of debt" if rw['debt'] else f", with {money(rw['cash'])} of cash and investments and no debt on the balance sheet")
                + (f" ({money(rw['due12'])} due within a year, {rw['cash'] / rw['due12']:.1f}× covered by cash)" if rw['due12'] else '') + '.')
    body = ("<h2 id='runway'>Cash runway and the debt wall</h2><div class='seo-tiles'>"
            + ''.join(f"<div class='seo-tile'><span>{e(k)}</span><b>{e(v)}</b></div>" for k, v in tiles if v) + f"</div><div class='seo-note'><p>{line}</p></div>")
    if len(rw['buckets']) >= 2:
        lab = {1: 'Year 1', 2: 'Year 2', 3: 'Year 3', 4: 'Year 4', 5: 'Year 5', 6: 'After year 5'}
        body += SV.bars([(lab.get(k, str(k)), a) for k, a in rw['buckets']], money, f"{name}: debt maturities by year ({rw['label'] or 'latest 10-K'})",
                        note=f"Principal due in each year as disclosed in the annual report, against {money(rw['cash'])} of cash and investments now.", color=SV.RED)
    return body, re.sub('<[^>]+>', '', line)


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
            "<nav class='seo-toc'><a href='#analysis'>Analysis</a><a href='#fcf'>Free cash flow</a><a href='#allocation'>By year</a><a href='#runway'>Runway & debt</a><a href='#where'>Where it went</a><a href='#bridge'>Profit to cash</a>"
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
    fys = [x for x in cap.get('fy') or [] if x.get('items') and x['items'].get('ocf') is not None][-10:]
    if len(fys) >= 3:
        keys = [('ocf', 'Operating cash flow'), ('borrow', 'Net borrowing'), ('stock', 'Shares issued'), ('sales', 'Asset sales'), ('capex', 'Capital spending'),
                ('acq', 'Acquisitions'), ('buyback', 'Buybacks'), ('div', 'Dividends')]
        ser = [(lab, [(x['items'].get(k) or 0) for x in fys]) for k, lab in keys]
        tot_in = sum(v for x in fys for k in ('ocf',) for v in [x['items'].get(k) or 0])
        uses = {lab: -sum(min(0, v) for v in vals) for lab, vals in ser}
        top = sorted(((k, v) for k, v in uses.items() if v > 0), key=lambda kv: -kv[1])[:2]
        body += ("<h2 id='allocation'>Capital allocation, year by year</h2>"
                 + SV.stacked([x['label'] for x in fys], ser, money, f"{name}: where the cash came from (up) and went (down), by fiscal year",
                              note=f"Over these {len(fys)} years operating cash flow totalled {money(tot_in)}"
                              + ('; the largest uses were ' + ' and '.join(f"{k.lower()} ({money(v)})" for k, v in top) if top else '') + '. Cash-flow statements as filed.',
                              colors=(SV.GREEN, SV.BLUE, '#7b6aa8', '#6fae8a', SV.RED, '#c08a3e', '#a05a8c', '#8a8f98')))
        lines.append(f"Over the last {len(fys)} fiscal years {name} generated {money(tot_in)} from operations"
                     + ('; the largest uses were ' + ' and '.join(f"{k.lower()} ({money(v)})" for k, v in top) if top else '') + '.')
    rw = runway(c, qs, ttm)
    rws, rline = runway_section(name, rw)
    body += rws
    if rline:
        lines.append(rline)
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
    return seo.page(f"{title} | Filing Flows", desc, url, body, 3, f"{base}/og.png", ld), row.get('filed') or last.get('end'), rw


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
    lines.append(f"{seo.n_of(len(cx), 'company', 'companies')} in {name} (SIC {sic}) spent {money(tot)} on capital projects over their latest twelve months, "
                 f"{tot / ocf * 100:.0f}% of the {money(ocf)} their operations generated" if ocf > 0 else
                 f"{seo.n_of(len(cx), 'company', 'companies')} in {name} (SIC {sic}) spent {money(tot)} on capital projects over their latest twelve months")
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
            f"<h1>{e(name)}: capital spending and supply chain</h1><p class='muted'>SIC {e(sic)} · {seo.n_of(len(cx), 'company', 'companies')} with filed cash-flow statements</p>"
            "<div class='seo-tiles'>" + ''.join(f"<div class='seo-tile'><span>{e(k)}</span><b>{e(v)}</b></div>" for k, v in [
                ('Capital spending, 12 months', money(tot)), ('Operating cash flow', money(ocf)), ('Capex / cash flow', f"{tot / ocf * 100:.0f}%" if ocf > 0 else None),
                ('Capex / revenue', f"{tot / rev * 100:.1f}%" if rev else None), ('Top 3 share', f"{top3 * 100:.0f}%")] if v) + '</div>'
            + "<h2>Analysis</h2><div class='seo-note'>" + ''.join(f"<p>{e(s)}</p>" for s in lines) + '</div>'
            + "<h2>Charts</h2><div class='seo-grid'>" + ''.join(x for x in body_ch if x) + '</div>')
    body += "<h2>Capital spending by company</h2>" + seo_table(['Company', 'Capital spending', 'Operating cash flow', 'Capex / OCF', 'Period'], [
        [(f"<a href='../../../c/{x[0][3]}/cash-flow/'>{e(x[1].get('ticker') or '')} {e(display_name(x[1].get('name')))}</a>" if x[0][3]
          else f"{e(x[1].get('ticker') or '')} {e(display_name(x[1].get('name')))}"), money(x[0][0]), money(x[0][1]),
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


def runway_page(site, base, cards):
    """disclosures/cash-runway/: who is burning cash and how long it lasts, the debt walls, the fortress balance sheets"""
    if not cards:
        return None
    L = lambda c: f"<a href='../../c/{c['slug']}/cash-flow/'><b>{e(c['ticker'])}</b></a> {e(c['name'])}"
    burners = sorted([c for c in cards if c.get('months') is not None and (c.get('cash') or 0) > 0], key=lambda c: c['months'])
    walls = sorted([c for c in cards if c.get('due12') and c['cash'] > 0 and c['due12'] > c['cash']], key=lambda c: -c['due12'] / c['cash'])[:30]
    forts = sorted([c for c in cards if c['net'] > 0 and (c.get('fcf_ttm') or 0) > 0], key=lambda c: -c['net'])[:30]
    yrs = lambda m: f"{m / 12:.1f} yrs" if m >= 24 else f"{m:.0f} mo"
    n_burn = len(burners)
    gap = sum(1 for c in cards if (c.get('fcf_ttm') or 0) < 0 and (c.get('ocf_ttm') or 0) > 0)
    lead = (f"Of {len(cards):,} companies with a balance sheet on file, {n_burn:,} have operations that consume cash"
            + (f"; {sum(1 for c in burners if c['months'] < 12):,} of them have less than a year of runway without new money" if burners else '')
            + f". Another {gap:,} bring cash in from operations but spend more on capital projects, a gap they fund by choice (not counted as burning)"
            + f". {len(walls):,} have more debt due within a year than cash on hand. Figures are from the companies' own cash-flow statements and balance sheets as filed.")
    body = (f"<p class='crumbs'><a href='../../'>Filing Flows</a> › <a href='../'>Disclosures</a> › Cash runway</p><h1>Cash runway: who is burning cash, and how long it lasts</h1>"
            f"<p class='lead'>{e(lead)}</p>")
    if burners:
        body += "<h2 id='burning'>Shortest runway</h2>" + seo_table(['Company', 'Cash & investments', 'Free cash flow, a year', 'Runway', 'Due within a year'], [
            [L(c), money(c['cash']), money(-c['burn']), yrs(c['months']), money(c['due12']) if c['due12'] else '—'] for c in burners[:40]])
        body += SV.hbars([(f"{c['ticker']} {c['name'][:28]}", c['months']) for c in burners[:15]], lambda v: yrs(v), 'Shortest cash runway at the current burn', n=15, color=SV.RED)
    if walls:
        body += "<h2 id='walls'>Debt walls: more due within a year than cash</h2>" + seo_table(['Company', 'Due within a year', 'Cash & investments', 'Coverage', 'Free cash flow, 12 months'], [
            [L(c), money(c['due12']), money(c['cash']), f"{c['cash'] / c['due12']:.2f}×", money(c['fcf_ttm']) if c.get('fcf_ttm') is not None else '—'] for c in walls])
    if forts:
        body += "<h2 id='fortress'>Fortress balance sheets: most net cash, self-funding</h2>" + seo_table(['Company', 'Net cash', 'Cash & investments', 'Debt', 'Free cash flow, 12 months'], [
            [L(c), money(c['net']), money(c['cash']), money(c['debt']) if c['debt'] else 'none', money(c['fcf_ttm'])] for c in forts])
    body += ("<p class='muted'>Runway is cash and investments divided by the trailing year's negative free cash flow (or the latest quarter's, annualised, when the burn is new); "
             "it assumes no new financing and no change in the burn. Debt due within a year is the annual report's first maturity bucket or the current portion on the balance sheet. Not investment advice.</p>"
             "<p><a class='seo-cta' href='../#quality'>Earnings quality, live →</a></p>")
    url = f"{base}/disclosures/cash-runway/"
    ld = {'@context': 'https://schema.org', '@graph': [
        {'@type': 'BreadcrumbList', 'itemListElement': [{'@type': 'ListItem', 'position': 1, 'name': 'Filing Flows', 'item': base + '/'},
                                                         {'@type': 'ListItem', 'position': 2, 'name': 'Disclosures', 'item': base + '/disclosures/'},
                                                         {'@type': 'ListItem', 'position': 3, 'name': 'Cash runway', 'item': url}]},
        {'@type': 'Dataset', 'name': 'Cash runway and debt maturities by company', 'description': lead[:500], 'url': url, 'creator': {'@type': 'Organization', 'name': 'Filing Flows', 'url': base + '/'}, 'isAccessibleForFree': True}]}
    os.makedirs(os.path.join(site, 'disclosures', 'cash-runway'), exist_ok=True)
    with open(os.path.join(site, 'disclosures', 'cash-runway', 'index.html'), 'w', encoding='utf-8') as f:
        f.write(seo.page('Cash Runway: Which Companies Are Burning Cash and How Long It Lasts | Filing Flows', lead[:300], url, body, 2, f"{base}/og.png", ld))
    return url


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
    urls, capex, cards = [], {}, []
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
        if len(out) > 2 and out[2]:
            cards.append({**out[2], 'cik': int(r['cik']), 'slug': slug, 'ticker': r.get('ticker') or '', 'name': display_name(r.get('name'))})
    try:                                    # the screener reads the runways from here instead of every company file again
        with open(os.path.join(site, 'data', 'runway.json'), 'w', encoding='utf-8') as f:
            json.dump({str(x['cik']): {k: x.get(k) for k in ('cash', 'debt', 'net', 'fcf_ttm', 'burn', 'months', 'due12')} for x in cards}, f, separators=(',', ':'))
    except OSError as err:
        print(f"runway file not written: {err}")
    try:
        u = runway_page(site, base, cards)
        if u:
            urls.insert(0, (u, None))
    except Exception as err:  # noqa: BLE001
        print(f"cash runway page skipped: {err}")
    for k, v in list(capex.items()):        # a company with fewer than four quarters of cash flow has no cash-flow page to link to
        if not os.path.exists(os.path.join(site, 'c', v[3], 'cash-flow', 'index.html')):
            capex[k] = v[:3] + (None,) + v[4:]
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
