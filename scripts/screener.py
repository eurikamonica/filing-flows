"""The screener's table: one row per listed company with everything the site knows that can be filtered on, merged from
the published files, so the hub's Screener tab (disclosures/docs/screener.js) and the static lists (disclosures/screener/)
read one file.

    disclosures/data/screener.json   {generated_at, fields, rows, presets}
    disclosures/screener/            the preset screens as plain pages, each a table of the companies that pass

Sources: data/index.json (the latest quarter), research/quality/index.json (fundamentals, factor scores), data/quality-score.json
(the earnings quality score), research/earnings/index.json (the next report, the beat rate, the implied move),
market/signals.json (13F flows, officials, price), market/insiders.json (Form 4 summary), market/short-interest.json,
and each company's data/c/<cik>.json for cash, debt and runway (seo_cashflow.runway). Not investment advice.

    python scripts/screener.py --site _site
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
from xml.sax.saxutils import escape as xesc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seo  # noqa: E402
import seo_cashflow as CF  # noqa: E402

e, display_name, money = seo.e, seo.display_name, seo.money
FIELDS = ['ticker', 'cik', 'name', 'sector', 'industry', 'slug', 'label', 'filed', 'revenue', 'yoy', 'om', 'mcap', 'price', 'growth', 'margin', 'fcf_y', 'div_y', 'bb_y', 'sy',
          'roic', 'ev_s', 'f_score', 'z', 'z_zone', 'm_flag', 'qmj', 'composite', 'qscore', 'qgrade', 'report_date', 'beat_rate', 'implied', 'avg_move', 'r1m', 'r3m', 'r1y',
          'from_high', 'above_ma200', 'f13_net', 'f13_buyers', 'f13_sellers', 'heat', 'ins_buys', 'ins_sells', 'ins_buy_usd', 'ins_sell_usd', 'short_dtc', 'short_chg',
          'cash', 'debt', 'net_cash', 'fcf_ttm', 'runway_months', 'tags']
# the preset screens: name, title, one line, the test, the sort key and direction, the columns to show
PRESETS = [
    ('quality-growth', 'Quality growth', 'Revenue up 15%+ in the year, operating margin above 15%, earnings quality B or better, Altman safe.',
     lambda r: (r['growth'] or 0) >= 0.15 and (r['om'] or 0) >= 15 and (r['qgrade'] or 'Z') <= 'B' and r['z_zone'] in (None, 'safe'), 'growth', -1,
     ['growth', 'om', 'qscore', 'fcf_y', 'mcap']),
    ('cash-machines', 'Cash machines', 'Free cash flow yield above 5%, shareholder yield above 3%, net cash or modest debt (debt under twice free cash flow).',
     lambda r: (r['fcf_y'] or 0) >= 0.05 and (r['sy'] or 0) >= 0.03 and ((r['net_cash'] or 0) >= 0 or ((r['debt'] or 0) <= 2 * (r['fcf_ttm'] or 0) if (r['fcf_ttm'] or 0) > 0 else False)), 'fcf_y', -1,
     ['fcf_y', 'sy', 'net_cash', 'fcf_ttm', 'mcap']),
    ('insiders-buying', 'Insiders buying', 'Two or more open-market insider buys on file, more bought than sold, and the stock below its 200-day average.',
     lambda r: (r['ins_buys'] or 0) >= 2 and (r['ins_buy_usd'] or 0) > (r['ins_sell_usd'] or 0) and r['above_ma200'] is False, 'ins_buy_usd', -1,
     ['ins_buys', 'ins_buy_usd', 'ins_sells', 'r3m', 'from_high']),
    ('smart-money-inflows', '13F inflows', 'Net 13F buying of $500M or more last quarter, more buyers than sellers, and the stock above its 200-day average.',
     lambda r: (r['f13_net'] or 0) >= 5e8 and (r['f13_buyers'] or 0) > (r['f13_sellers'] or 0) and r['above_ma200'] is True, 'f13_net', -1,
     ['f13_net', 'f13_buyers', 'f13_sellers', 'r3m', 'mcap']),
    ('short-squeeze', 'Short squeeze candidates', 'Days to cover of 5 or more, short interest up 10%+ since the last report, and the stock up over three months.',
     lambda r: (r['short_dtc'] or 0) >= 5 and (r['short_chg'] or 0) >= 10 and (r['r3m'] or 0) > 0, 'short_dtc', -1,
     ['short_dtc', 'short_chg', 'r3m', 'r1m', 'mcap']),
    ('earnings-this-week', 'Reporting within seven days', 'Companies due to report within the next seven days, with the beat rate and the move the options price in.',
     lambda r: r['report_date'] and 0 <= (dt.date.fromisoformat(r['report_date']) - dt.date.today()).days <= 7, 'report_date', 1,
     ['report_date', 'beat_rate', 'implied', 'avg_move', 'mcap']),
    ('distress', 'Distress watch', 'Altman Z in the distress zone or less than a year of cash at the current burn, and more than $300M of market value.',
     lambda r: (r['z_zone'] == 'distress' or (r['runway_months'] is not None and r['runway_months'] < 12)) and (r['mcap'] or 0) >= 3e8, 'runway_months', 1,
     ['runway_months', 'cash', 'debt', 'z', 'z_zone']),
    ('low-quality-earnings', 'Low-quality earnings', 'Earnings quality grade D or E and a Beneish flag, with more than $2B of market value.',
     lambda r: (r['qgrade'] or 'A') >= 'D' and r['m_flag'] and (r['mcap'] or 0) >= 2e9, 'qscore', 1,
     ['qscore', 'qgrade', 'growth', 'margin', 'mcap']),
    ('fallen-leaders', 'Fallen leaders', 'Down 30% or more from the 52-week high, still growing revenue 10%+ year over year, free cash flow positive.',
     lambda r: (r['from_high'] or 0) <= -0.3 and (r['yoy'] or 0) >= 10 and (r['fcf_ttm'] or 0) > 0, 'from_high', 1,
     ['from_high', 'yoy', 'fcf_ttm', 'r1y', 'mcap']),
    ('momentum', 'Momentum', 'Up over one, three and twelve months, within 10% of the 52-week high, above the 200-day average.',
     lambda r: (r['r1m'] or 0) > 0 and (r['r3m'] or 0) > 0 and (r['r1y'] or 0) > 0 and (r['from_high'] or -1) >= -0.1 and r['above_ma200'] is True, 'r1y', -1,
     ['r1m', 'r3m', 'r1y', 'from_high', 'mcap']),
]
COL = {'growth': 'Revenue growth, FY', 'om': 'Operating margin', 'qscore': 'Quality score', 'qgrade': 'Grade', 'fcf_y': 'FCF yield', 'mcap': 'Market value', 'sy': 'Shareholder yield',
       'net_cash': 'Net cash', 'fcf_ttm': 'Free cash flow, 12m', 'ins_buys': 'Insider buys', 'ins_buy_usd': 'Bought', 'ins_sells': 'Insider sales', 'r3m': '3 months', 'r1m': '1 month',
       'r1y': '12 months', 'from_high': 'From 52-wk high', 'f13_net': '13F net buying', 'f13_buyers': 'Buyers', 'f13_sellers': 'Sellers', 'short_dtc': 'Days to cover',
       'short_chg': 'Short interest change', 'report_date': 'Reports', 'beat_rate': 'Beat rate', 'implied': 'Implied move', 'avg_move': 'Avg. move', 'runway_months': 'Runway',
       'cash': 'Cash & investments', 'debt': 'Debt', 'z': 'Altman Z', 'z_zone': 'Zone', 'yoy': 'Revenue Y/Y', 'margin': 'Margin'}
PCT = {'growth', 'fcf_y', 'sy', 'r3m', 'r1m', 'r1y', 'from_high', 'beat_rate', 'implied', 'avg_move', 'margin', 'div_y', 'bb_y', 'roic'}
USD = {'mcap', 'net_cash', 'fcf_ttm', 'ins_buy_usd', 'ins_sell_usd', 'f13_net', 'cash', 'debt', 'revenue'}


def read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def fmt(k, v):
    if v is None:
        return '—'
    if k in PCT:
        return (lambda r: f"{'+' if r > 0 else '−' if r < 0 else ''}{abs(r):.1f}%")(round(100 * v, 1)) if k in ('r3m', 'r1m', 'r1y', 'from_high', 'growth') else f"{100 * v:.1f}%"
    if k in USD:
        return money(v)
    if k == 'om' or k == 'yoy' or k == 'short_chg':
        return f"{v:+.1f}%" if k != 'om' else f"{v:.1f}%"
    if k == 'runway_months':
        return '10+ yrs' if v > 120 else f"{v / 12:.1f} yrs" if v >= 24 else f"{v:.0f} mo"
    if k == 'report_date':
        return seo.fdate(v)
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def build(site, today=None):
    hub = os.path.join(site, 'disclosures', 'data')
    today = today or dt.date.today()
    ix = read(os.path.join(site, 'data', 'index.json')) or {}
    rows = ix.get('companies') if isinstance(ix, dict) else ix
    K = lambda t: str(t or '').upper().replace('.', '-')
    q = {}
    qd = read(os.path.join(hub, 'research', 'quality', 'index.json')) or {}
    for x in qd.get('rows') or []:
        r = dict(zip(qd.get('fields') or [], x))
        q[K(r.get('ticker'))] = r
    qs = {}
    sd = read(os.path.join(site, 'data', 'quality-score.json')) or {}
    for x in sd.get('rows') or []:
        r = dict(zip(sd.get('fields') or [], x))
        qs[K(r.get('ticker'))] = r
    er = {}
    ed = read(os.path.join(hub, 'research', 'earnings', 'index.json')) or {}
    for x in ed.get('rows') or []:
        r = dict(zip(ed.get('fields') or [], x))
        er[K(r.get('ticker'))] = r
    sg = {K(r.get('ticker')): r for r in (read(os.path.join(hub, 'market', 'signals.json')) or {}).get('rows') or []}
    ins = {K(r.get('ticker')): r for r in (read(os.path.join(hub, 'market', 'insiders.json')) or {}).get('summary') or []}
    sh = {K(r.get('ticker')): r for r in (read(os.path.join(hub, 'market', 'short-interest.json')) or {}).get('rows') or []}
    runways = read(os.path.join(site, 'data', 'runway.json'))       # seo_cashflow.py's, when it ran first (scan.yml)
    out, seen = [], set()
    for r in rows or []:
        t = K(r.get('ticker'))
        if not t or t in seen:
            continue
        seen.add(t)
        slug = seo.slug_for(r)
        Q, S, E, G, I, H = q.get(t, {}), qs.get(t, {}), er.get(t, {}), sg.get(t, {}), ins.get(t, {}), sh.get(t, {})
        if not Q and not G and not E:
            continue
        rw = runways.get(str(r.get('cik'))) if runways is not None else None
        c = read(os.path.join(site, 'data', 'c', f"{r['cik']}.json")) if runways is None and r.get('cik') else None
        if c:
            try:
                cap = ((c.get('quality') or {}).get('cap') or {})
                qq = [x for x in cap.get('q') or [] if (x.get('items') or {}).get('ocf') is not None]
                rw = CF.runway(c, qq, cap.get('ttm'))
            except Exception:  # noqa: BLE001
                rw = None
        P = G.get('price') or {}
        F13 = G.get('f13') or {}
        d = {'ticker': t, 'cik': r.get('cik'), 'name': display_name(r.get('name')), 'sector': r.get('sector') or Q.get('sector'), 'industry': r.get('industry'), 'slug': slug,
             'label': r.get('label'), 'filed': r.get('filed'), 'revenue': r.get('revenue'), 'yoy': r.get('yoy'), 'om': r.get('om') if r.get('om') is None or abs(r['om']) <= 1000 else None,
             'mcap': Q.get('mcap'), 'price': Q.get('price') or P.get('last'), 'growth': Q.get('growth'), 'margin': Q.get('margin'), 'fcf_y': Q.get('fcf_y'), 'div_y': Q.get('div_y'),
             'bb_y': Q.get('bb_y'), 'sy': Q.get('sy'), 'roic': Q.get('roic'), 'ev_s': Q.get('ev_s'), 'f_score': Q.get('f_score'), 'z': Q.get('z'), 'z_zone': Q.get('z_zone'),
             'm_flag': Q.get('m_flag'), 'qmj': Q.get('qmj'), 'composite': Q.get('composite'), 'qscore': S.get('score'), 'qgrade': S.get('grade'),
             'report_date': E.get('report_date'), 'beat_rate': E.get('beat_rate'), 'implied': E.get('implied'), 'avg_move': E.get('avg_move'),
             'r1m': P.get('r1m'), 'r3m': P.get('r3m'), 'r1y': P.get('r1y'), 'from_high': P.get('from_high'), 'above_ma200': P.get('above_ma200'),
             'f13_net': F13.get('usd_net'), 'f13_buyers': F13.get('buyers'), 'f13_sellers': F13.get('sellers'), 'heat': G.get('heat'),
             'ins_buys': I.get('buys'), 'ins_sells': I.get('sells'), 'ins_buy_usd': I.get('buy_value'), 'ins_sell_usd': I.get('sell_value'),
             'short_dtc': H.get('dtc') if (H.get('dtc') or 0) < 999 else None, 'short_chg': H.get('change_pct'),     # 999.99: no volume to cover with
             'cash': rw and rw['cash'], 'debt': rw and rw['debt'], 'net_cash': rw and rw['net'], 'fcf_ttm': rw and rw['fcf_ttm'], 'runway_months': rw and rw['months'] and round(rw['months'], 1),
             'tags': G.get('tags') or []}
        for k in ('mcap', 'cash', 'debt', 'net_cash', 'fcf_ttm', 'f13_net', 'ins_buy_usd', 'ins_sell_usd', 'revenue'):
            if isinstance(d.get(k), float):
                d[k] = round(d[k])
        for k in ('growth', 'margin', 'fcf_y', 'div_y', 'bb_y', 'sy', 'roic', 'r1m', 'r3m', 'r1y', 'from_high', 'beat_rate', 'implied', 'avg_move'):
            if isinstance(d.get(k), float):
                d[k] = round(d[k], 4)
        out.append(d)
    out.sort(key=lambda d: -(d.get('mcap') or 0))
    presets = []
    for key, title, line, test, sk, sd_, cols in PRESETS:
        hits = []
        for d in out:
            try:
                if test(d):
                    hits.append(d)
            except Exception:  # noqa: BLE001
                pass
        hits.sort(key=lambda d: (d.get(sk) is None, (d.get(sk) or 0) * sd_ if not isinstance(d.get(sk), str) else d.get(sk)))
        presets.append({'key': key, 'title': title, 'line': line, 'sort': sk, 'dir': sd_, 'cols': cols, 'tickers': [d['ticker'] for d in hits]})      # all of them: the counts shown are the real ones
    return {'generated_at': today.isoformat(), 'fields': FIELDS, 'rows': [[d.get(k) for k in FIELDS] for d in out], 'presets': presets,
            'note': 'One row per listed company, merged from the site’s published files: the latest quarter (SEC XBRL), fundamentals and factor scores (research/quality), '
                    'the earnings quality score, the next report and beat rate, 13F flows and the price (market/signals), Form 4 insider trades, FINRA short interest, and cash, '
                    'debt and runway from the cash-flow statements. Not investment advice.'}, out


def pages(site, base, doc, rows):
    by = {d['ticker']: d for d in rows}
    urls = []
    has = lambda d: os.path.exists(os.path.join(site, 'c', d['slug'], 'index.html'))
    nav = "<nav class='seo-toc'>" + ''.join(f"<a href='#{p['key']}'>{e(p['title'])}</a>" for p in doc['presets']) + '</nav>'
    secs = ''
    for p in doc['presets']:
        hits = [by[t] for t in p['tickers'] if t in by][:60]
        secs += f"<h2 id='{p['key']}'>{e(p['title'])} <span class='muted'>{len(p['tickers'])}</span></h2><p>{e(p['line'])}</p>"
        if not hits:
            secs += "<p class='muted'>No company passes today.</p>"
            continue
        secs += ("<div class='tbl-wrap'><table><thead><tr><th>Company</th>" + ''.join(f"<th class='num'>{e(COL.get(c, c))}</th>" for c in p['cols']) + "</tr></thead><tbody>"
                 + ''.join(f"<tr><td>{'<a href=' + chr(39) + '../../c/' + d['slug'] + '/' + chr(39) + '><b>' + e(d['ticker']) + '</b></a>' if has(d) else '<b>' + e(d['ticker']) + '</b>'} {e(d['name'])}</td>"
                           + ''.join(f"<td class='num'>{e(fmt(c, d.get(c)))}</td>" for c in p['cols']) + '</tr>' for d in hits) + '</tbody></table></div>')
        secs += f"<p><a href='../#screener/{p['key']}'>Open this screen live: change the thresholds, add columns, export →</a></p>"
    n = len(rows)
    lead = (f"{n} listed companies in one table, with {len(FIELDS) - 6} fields each from the filings and the market: growth, margins, free cash flow and shareholder yield, "
            f"the Piotroski, Altman and Beneish scores, the earnings quality score, the next report and beat rate, 13F flows, insider trades, short interest, cash, debt and runway. "
            f"Ten preset screens below; every threshold can be changed in the live screener.")
    body = (f"<p class='crumbs'><a href='../../'>Filing Flows</a> › <a href='../'>Disclosures</a> › Screener</p><h1>Stock screener: {n} companies, {len(FIELDS) - 6} fields from the filings</h1>"
            f"<p class='lead'>{e(lead)}</p><p><a class='seo-cta' href='../#screener'>Open the live screener →</a></p>{nav}{secs}"
            "<p class='muted'>Screens are descriptive: the companies that pass a set of tests today, from public filings and daily closes; what happened, not what will. "
            "Thresholds are arbitrary starting points. Not investment advice.</p>")
    url = f"{base}/disclosures/screener/"
    ld = {'@context': 'https://schema.org', '@graph': [
        {'@type': 'BreadcrumbList', 'itemListElement': [{'@type': 'ListItem', 'position': 1, 'name': 'Filing Flows', 'item': base + '/'},
                                                         {'@type': 'ListItem', 'position': 2, 'name': 'Disclosures', 'item': base + '/disclosures/'},
                                                         {'@type': 'ListItem', 'position': 3, 'name': 'Screener', 'item': url}]},
        {'@type': 'Dataset', 'name': 'Stock screener table', 'description': lead[:500], 'url': url, 'dateModified': doc['generated_at'],
         'distribution': {'@type': 'DataDownload', 'encodingFormat': 'application/json', 'contentUrl': f"{base}/disclosures/data/screener.json"},
         'creator': {'@type': 'Organization', 'name': 'Filing Flows', 'url': base + '/'}, 'isAccessibleForFree': True}]}
    os.makedirs(os.path.join(site, 'disclosures', 'screener'), exist_ok=True)
    open(os.path.join(site, 'disclosures', 'screener', 'index.html'), 'w', encoding='utf-8').write(seo.page(
        f'Stock Screener: {n} Companies on Growth, Cash Flow, Quality, Insider and 13F Flows, from SEC Filings | Filing Flows', lead[:300], url, body, 2, base + '/og.png', ld))
    urls.append((url, doc['generated_at']))
    return urls


def write(site, base, today=None):
    base = base.rstrip('/')
    doc, rows = build(site, today)
    os.makedirs(os.path.join(site, 'disclosures', 'data'), exist_ok=True)
    with open(os.path.join(site, 'disclosures', 'data', 'screener.json'), 'w', encoding='utf-8') as f:
        json.dump(doc, f, separators=(',', ':'))
    urls = pages(site, base, doc, rows)
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f'<url><loc>{xesc(u)}</loc><lastmod>{xesc(str(m)[:10])}</lastmod></url>' for u, m in urls]
    sm.append('</urlset>')
    open(os.path.join(site, 'sitemap-screener.xml'), 'w', encoding='utf-8').write('\n'.join(sm))
    robots = os.path.join(site, 'robots.txt')
    txt = open(robots).read() if os.path.exists(robots) else f'User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n'
    if 'sitemap-screener.xml' not in txt:
        open(robots, 'w').write(txt.rstrip('\n') + f'\nSitemap: {base}/sitemap-screener.xml\n')
    return len(rows), {p['key']: len(p['tickers']) for p in doc['presets']}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', default='_site')
    ap.add_argument('--site-url', default=os.environ.get('SITE_URL', '') or 'https://filing-flows.com')
    a = ap.parse_args()
    m = re.search(r'https?://[^\s"]+', a.site_url or '')
    n, presets = write(a.site, m.group(0) if m else 'https://filing-flows.com')
    print(f"screener: {n} companies; " + ', '.join(f"{k} {v}" for k, v in presets.items()))
