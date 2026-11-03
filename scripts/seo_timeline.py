"""Timelines: a year of the stock with every disclosure marked on it, and what followed each one.

    c/<slug>/timeline/              the last 252 sessions as a line, with insiders' Form 4 buys and sales, Form 144 notices of
                                    planned sales, earnings reports and material 8-Ks marked; a table of each mark with the
                                    stock's move 1, 5 and 21 sessions later and the same figure for the market; the insiders'
                                    trades scored (the stock against SPY over the 63 sessions after each); what the same kind
                                    of 8-K usually did across the universe
    disclosures/insider-signals/    insiders' trades by pattern across the universe: how often buys of each size, cluster buys,
                                    repeat buyers and sales were followed by the stock beating or lagging the market
    sitemap-timelines.xml

Data: disclosures/data/research/paths/moves/{a,n}/<KEY>.json (daily returns; filings with the time of day), smart/t/<T>.json
(scored trades), holders/<T>.json (Form 144), research/earnings/c/<T>.json (report dates), data/event-stats.json and
data/insider-stats.json (scripts/event_stats.py). Every number is the record; nothing is a forecast.

    python scripts/seo_timeline.py --site _site
"""
import argparse
import datetime as dt
import json
import math
import os
import re
import sys
from xml.sax.saxutils import escape as xesc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seo  # noqa: E402
import seo_svg as SV  # noqa: E402
import event_stats as ES  # noqa: E402

e, fdate, display_name, money = seo.e, seo.fdate, seo.display_name, seo.money
read = ES.read
SESSIONS = 252
MATERIAL = {'1.01', '1.02', '1.03', '1.05', '2.01', '2.03', '2.04', '2.05', '2.06', '3.01', '4.01', '4.02', '5.01', '5.02'}
DISCLAIMER = ("<p class='muted'>Prices are daily closes; filings and trades are as filed with the SEC (Form 4 within two business days of the trade, "
              "8-K within four of the event). Moves after a mark are the stock's close-to-close change and the same for SPY; they describe the record, "
              "not what the next one will do. Not investment advice.</p>")


def pct(v, d=1):
    return seo.pct(100 * v) if v is not None else '—'


def spct(v):
    return f"{'+' if v > 0 else '−' if v < 0 else ''}{abs(100 * v):.1f}%" if v is not None else '—'


def marks_for(t, cik, hub, er, days):
    """[(day, kind, label, detail dict)] for the year on the chart"""
    t0 = days[0]
    out = []
    sm = read(os.path.join(hub, 'smart', 't', re.sub(r'[^A-Za-z0-9-]', '_', t) + '.json')) or {}
    F = sm.get('trade_fields') or ['date', 'actor', 'name', 'group', 'd', 'size', 'ex', 'ex2', 'follow', 'known']
    ins = [dict(zip(F, x)) for x in sm.get('trades') or [] if len(x) >= 6 and x[3] == 'ins']
    for x in ins:
        if x['date'] >= t0:
            out.append((x['date'], 'buy' if x['d'] > 0 else 'sell', f"{x['name']} {'bought' if x['d'] > 0 else 'sold'} {money(x.get('size') or 0)}", x))
    hd = read(os.path.join(hub, 'holders', re.sub(r'[^A-Za-z0-9-]', '_', t) + '.json')) or {}
    for x in hd.get('form144') or []:
        d = x.get('sale_date') or x.get('filed')
        if d and d >= t0 and (x.get('value') or 0) > 0:
            out.append((d, 'plan', f"Form 144: {x.get('seller_name') or x.get('seller') or 'an affiliate'} plans to sell {money(x['value'])}", x))
    for h in (er or {}).get('history') or []:
        if h.get('reported') and h['reported'] >= t0:
            s = h.get('surprise')
            out.append((h['reported'], 'earnings', f"Earnings: {'beat' if h.get('beat') else 'missed'} the EPS estimate" + (f" by {100 * s:.1f}%" if s is not None else ''), h))
    nd = read(os.path.join(hub, 'research', 'paths', 'moves', 'n', re.sub(r'[^A-Za-z0-9-]', '_', t) + '.json')) or {}
    for ev in nd.get('events') or []:
        try:
            day, time, form, items, head = ev[0], ev[1], ev[2], ev[3], ev[4]
        except (IndexError, TypeError):
            continue
        if day < t0 or not str(form).startswith('8-K'):
            continue
        codes = [c.strip() for c in (items.split(',') if isinstance(items, str) else items or []) if c.strip()]
        core = [c for c in codes if c in MATERIAL]
        if not core:
            continue
        out.append((day, 'event', (head or ES.ITEM_NAMES.get(core[0], 'Item ' + core[0]))[:90], {'items': core, 'time': time, 'accession': ev[7] if len(ev) > 7 else None, 'headline': head}))
    out.sort(key=lambda m: m[0])
    return out


def page_for(co, base, slug, site, hub, stats, istats):
    t = (co.get('ticker') or '').upper()
    name = display_name(co.get('name'))
    key = re.sub(r'[^A-Za-z0-9-]', '_', t)
    ad = read(os.path.join(hub, 'research', 'paths', 'moves', 'a', key + '.json'))
    if not ad or not ad.get('last'):
        return None
    days_all, closes_all = ES.prices(ad)
    days_all, cum_all = ES.decode(ad)
    if len(days_all) < 60:
        return None
    spy_doc = read(os.path.join(hub, 'research', 'paths', 'moves', 'a', 'SPY.json'))
    spy = ES.decode(spy_doc)[:2] if spy_doc else None
    days, closes = days_all[-SESSIONS:], closes_all[-SESSIONS:]
    er = read(os.path.join(hub, 'research', 'earnings', 'c', key + '.json'))
    marks = marks_for(t, co.get('cik'), hub, er, days)
    if not marks:
        return None
    chart = SV.line_marks(days, closes, [(d, k, lab) for d, k, lab, _ in marks], lambda v: f"${v:,.0f}" if v >= 100 else f"${v:,.2f}",
                          f"{t}: a year of the stock with every disclosure on it", note=f"Daily closes, {fdate(days[0])} to {fdate(days[-1])}; hover a mark for the filing.")
    # the table: each mark and what followed
    KIND = {'buy': 'Insider buy', 'sell': 'Insider sale', 'earnings': 'Earnings', 'event': '8-K', 'plan': 'Form 144'}
    rows, after = [], {1: [], 5: [], 21: []}
    for d, k, lab, x in marks[::-1][:80]:
        rx = ES.reaction(days_all, cum_all, d, x.get('time') if k == 'event' else '09:00', spy=spy)
        cells = []
        for h in (1, 5, 21):
            v = rx.get(h) if rx else None
            if v and v[0] is not None:
                cells.append(f"<td class='{'up' if v[0] > 0 else 'down' if v[0] < 0 else ''}'>{spct(v[0])}" + (f" <span class='muted'>({spct(v[1])} vs SPY)</span>" if v[1] is not None else '') + '</td>')
                if k in ('buy', 'sell'):
                    after[h].append((k, v[1] if v[1] is not None else v[0]))
            else:
                cells.append("<td class='muted'>—</td>")
        rows.append(f"<tr><td>{e(fdate(d))}</td><td>{e(KIND[k])}</td><td>{e(lab)}</td>{''.join(cells)}</tr>")
    table = ("<div class='tbl-wrap'><table class='seo-table'><thead><tr><th>Date</th><th>Kind</th><th>What</th><th>Next session</th><th>5 sessions</th><th>21 sessions</th></tr></thead><tbody>"
             + ''.join(rows) + '</tbody></table></div>')
    # insiders' scored record for this stock
    ins = [x for d, k, lab, x in marks if k in ('buy', 'sell')]
    scored = [x for x in ins if x.get('ex') is not None]
    ins_h = ''
    if ins:
        nb, ns = sum(1 for x in ins if x['d'] > 0), sum(1 for x in ins if x['d'] < 0)
        ub, us = sum(x.get('size') or 0 for x in ins if x['d'] > 0), sum(x.get('size') or 0 for x in ins if x['d'] < 0)
        s = (f"In the year on the chart, {name}'s insiders reported <b>{nb} open-market buy{'s' if nb != 1 else ''}</b> ({money(ub)}) and <b>{ns} sale{'s' if ns != 1 else ''}</b> ({money(us)}).")
        if scored:
            right = sum(1 for x in scored if (x['ex'] > 0) == (x['d'] > 0))
            s += (f" Of the {len(scored)} old enough to score, <b>{right}</b> were followed by the stock doing what the trade implied over the next 63 sessions "
                  f"(beating SPY after a buy, lagging it after a sale); the median excess return after a buy was "
                  f"{spct(sorted(x['ex'] for x in scored if x['d'] > 0)[len([x for x in scored if x['d'] > 0]) // 2]) if any(x['d'] > 0 for x in scored) else '—'}"
                  f" and after a sale {spct(sorted(x['ex'] for x in scored if x['d'] < 0)[len([x for x in scored if x['d'] < 0]) // 2]) if any(x['d'] < 0 for x in scored) else '—'}.")
        ins_h = f"<h2 id='insiders'>Insiders’ record here</h2><p>{s}</p>"
        pat = (istats or {}).get('patterns') or {}
        if pat.get('buy') and pat.get('sell'):
            ins_h += (f"<p class='muted'>Across the whole universe ({pat['buy']['n'] + pat['sell']['n']:,} scored trades), insider buys beat the market "
                      f"{100 * pat['buy']['hit']:.0f}% of the time and sales were followed by a lagging stock {100 * pat['sell']['hit']:.0f}% of the time"
                      + (f"; buys of $1M or more {100 * pat['buy_large']['hit']:.0f}%" if pat.get('buy_large') else '') + ". "
                      "<a href='../../../disclosures/insider-signals/'>Every pattern →</a></p>")
    # 8-Ks of this kind across the universe
    ev_h, items_seen = '', []
    for d, k, lab, x in marks:
        if k == 'event':
            for c in x.get('items') or []:
                if c not in items_seen:
                    items_seen.append(c)
    its = [(c, (stats or {}).get('items', {}).get(c)) for c in items_seen]
    its = [(c, s) for c, s in its if s and s.get('h1')]
    if its:
        ev_h = ("<h2 id='kind'>What this kind of 8-K usually did</h2><div class='tbl-wrap'><table class='seo-table'><thead><tr><th>Item</th><th>8-Ks</th><th>Next session, median</th>"
                "<th>Up next session</th><th>21 sessions, median</th><th>Typical size</th></tr></thead><tbody>" + ''.join(
                    f"<tr><td><b>{e(c)}</b> {e(s.get('name', ''))}</td><td>{s['h1']['n']:,}</td><td class='{'up' if s['h1']['median'] > 0 else 'down' if s['h1']['median'] < 0 else ''}'>{spct(s['h1']['median'])}</td>"
                    f"<td>{100 * s['h1']['up']:.0f}%</td><td>{spct(s['h21']['median']) if s.get('h21') else '—'}</td><td>±{100 * s['h1']['abs_median']:.1f}%</td></tr>" for c, s in its)
                + "</tbody></table></div><p class='muted'>Across every company in the move-odds universe, measured from the close before the filing. "
                  "<a href='../../../events/impact/'>Every 8-K item ranked →</a></p>")
    chg = closes[-1] / closes[0] - 1
    n_ev = sum(1 for m in marks if m[2] and m[1] == 'event')
    lead = (f"{name} ({t}) stock {'rose' if chg > 0 else 'fell'} {abs(100 * chg):.0f}% over the last {len(days)} sessions, to ${closes[-1]:,.2f}. On the way it reported "
            f"{sum(1 for m in marks if m[1] == 'earnings')} quarter{'s' if sum(1 for m in marks if m[1] == 'earnings') != 1 else ''}, its insiders filed "
            + (f"{sum(1 for m in marks if m[1] in ('buy', 'sell'))} open-market trade{'s' if sum(1 for m in marks if m[1] in ('buy', 'sell')) != 1 else ''}" if any(m[1] in ('buy', 'sell') for m in marks) else 'no open-market trades (10b5-1 plan sales aside)')
            + (f" and {sum(1 for m in marks if m[1] == 'plan')} Form 144 notice{'s' if sum(1 for m in marks if m[1] == 'plan') != 1 else ''} of planned sales" if any(m[1] == 'plan' for m in marks) else '')
            + f", and the company filed {n_ev} material 8-K{'s' if n_ev != 1 else ''}. Each is marked on the price and listed with what the stock did next.")
    url = f"{base}/c/{slug}/timeline/"
    title = f"{name} ({t}) Stock Timeline: Insider Trades, Earnings and 8-Ks on the Price Chart"
    body = (f"<p class='crumbs'><a href='../../../'>Filing Flows</a> › <a href='../../'>Companies</a> › <a href='../'>{e(name)}</a> › Timeline</p>"
            f"<h1>{e(name)} stock timeline</h1><p class='muted'>A year of the price with every insider trade, planned sale, earnings report and material 8-K marked</p>"
            f"<p class='seo-hl {'up' if chg > 0 else 'down'}'><span>{len(days)} sessions</span><b>{spct(chg)}</b> to ${closes[-1]:,.2f}</p>"
            "<nav class='seo-toc'><a href='#chart'>Chart</a><a href='#marks'>Each mark</a>" + ("<a href='#insiders'>Insiders</a>" if ins_h else '') + ("<a href='#kind'>8-K kinds</a>" if ev_h else '') + "</nav>"
            f"<p class='lead'>{e(lead)}</p><div id='chart'>{chart}</div>"
            f"<h2 id='marks'>Each mark, and what followed</h2>{table}{ins_h}{ev_h}"
            f"<p><a class='seo-cta' href='../report-card/'>Report card: every quarter against the estimate →</a> <a href='../'>{e(name)}: every quarter →</a> "
            f"<a href='../../../disclosures/#insiders'>Live insider trades →</a></p>{DISCLAIMER}")
    ld = {'@context': 'https://schema.org', '@graph': [
        {'@type': 'BreadcrumbList', 'itemListElement': [{'@type': 'ListItem', 'position': 1, 'name': 'Filing Flows', 'item': base + '/'},
                                                         {'@type': 'ListItem', 'position': 2, 'name': name, 'item': f"{base}/c/{slug}/"},
                                                         {'@type': 'ListItem', 'position': 3, 'name': 'Timeline', 'item': url}]},
        {'@type': 'FAQPage', 'mainEntity': [{'@type': 'Question', 'name': f"Are {name} insiders buying or selling?", 'acceptedAnswer': {'@type': 'Answer', 'text': re.sub('<[^>]+>', '', ins_h)[:600] or lead}}]},
        {'@type': 'WebPage', 'name': title, 'url': url, 'dateModified': days[-1], 'description': lead[:300]}]}
    return url, days[-1], seo.page(seo.fit(title), lead[:300], url, body, 3, base + '/og.png', ld), {
        'ticker': t, 'name': name, 'slug': slug, 'buys': sum(1 for m in marks if m[1] == 'buy'), 'sells': sum(1 for m in marks if m[1] == 'sell'),
        'buy_usd': sum(m[3].get('size') or 0 for m in marks if m[1] == 'buy'), 'sell_usd': sum(m[3].get('size') or 0 for m in marks if m[1] == 'sell'), 'chg': chg}


def signals_page(site, base, istats, cards):
    pat = (istats or {}).get('patterns') or {}
    if not pat.get('buy'):
        return None
    order = ['buy', 'buy_large', 'buy_mid', 'buy_small', 'buy_cluster', 'buy_lone', 'buy_repeat', 'buy_first', 'sell', 'sell_large', 'sell_mid', 'sell_small']
    rows = [pat[k] for k in order if k in pat]
    tbl = ("<div class='tbl-wrap'><table class='seo-table'><thead><tr><th>Pattern</th><th>Trades scored</th><th>Right</th><th>Median excess return, 63 sessions</th><th>Mean</th></tr></thead><tbody>"
           + ''.join(f"<tr><td>{e(r['label'])}</td><td>{r['n']:,}</td><td class='{'up' if r['hit'] >= 0.5 else 'down'}'>{100 * r['hit']:.0f}%</td>"
                     f"<td class='{'up' if r['median_excess'] > 0 else 'down' if r['median_excess'] < 0 else ''}'>{spct(r['median_excess'])}</td><td>{spct(r['mean_excess'])}</td></tr>" for r in rows) + '</tbody></table></div>')
    chart = SV.hbars([(r['label'], 100 * r['hit']) for r in rows], lambda v: f"{v:.0f}%", 'How often each pattern was right (stock beat SPY after a buy, lagged after a sale)', n=14)
    b, s = pat['buy'], pat['sell']
    lead = (f"Insiders’ open-market trades from the last 400 days, {istats['trades']:,} of them old enough to score against the market over the following 63 sessions. "
            f"Buys were followed by the stock beating SPY {100 * b['hit']:.0f}% of the time (median excess {spct(b['median_excess'])}); sales by the stock lagging {100 * s['hit']:.0f}% of the time."
            + (f" Size mattered most: buys of $1M or more were right {100 * pat['buy_large']['hit']:.0f}% of the time against {100 * pat['buy_small']['hit']:.0f}% for buys under $100k." if pat.get('buy_large') and pat.get('buy_small') else ''))
    heavy = sorted([c for c in cards if c['buys'] >= 2], key=lambda c: -c['buy_usd'])[:25]
    sellers = sorted([c for c in cards if c['sells'] >= 2], key=lambda c: -c['sell_usd'])[:25]
    L = lambda c: f"<a href='../../c/{c['slug']}/timeline/'><b>{e(c['ticker'])}</b></a> {e(c['name'])}"
    lists = ''
    if heavy:
        lists += "<h2 id='buying'>Most insider buying in the last year</h2><div class='tbl-wrap'><table class='seo-table'><thead><tr><th>Company</th><th>Buys</th><th>Bought</th><th>Stock, 252 sessions</th></tr></thead><tbody>" + ''.join(
            f"<tr><td>{L(c)}</td><td>{c['buys']}</td><td>{money(c['buy_usd'])}</td><td class='{'up' if c['chg'] > 0 else 'down'}'>{spct(c['chg'])}</td></tr>" for c in heavy) + '</tbody></table></div>'
    if sellers:
        lists += "<h2 id='selling'>Most insider selling in the last year</h2><div class='tbl-wrap'><table class='seo-table'><thead><tr><th>Company</th><th>Sales</th><th>Sold</th><th>Stock, 252 sessions</th></tr></thead><tbody>" + ''.join(
            f"<tr><td>{L(c)}</td><td>{c['sells']}</td><td>{money(c['sell_usd'])}</td><td class='{'up' if c['chg'] > 0 else 'down'}'>{spct(c['chg'])}</td></tr>" for c in sellers) + '</tbody></table></div>'
    url = f"{base}/disclosures/insider-signals/"
    body = (f"<p class='crumbs'><a href='../../'>Filing Flows</a> › <a href='../'>Disclosures</a> › Insider signals</p><h1>Do insider trades predict the stock? The record, by pattern</h1>"
            f"<p class='lead'>{e(lead)}</p>{chart}<h2 id='patterns'>Every pattern</h2>{tbl}<p class='muted'>{e(istats.get('note') or '')}</p>{lists}"
            f"<p><a class='seo-cta' href='../insider-trades/'>This week's insider trades →</a> <a href='../#insiders'>Live, filterable →</a></p>{DISCLAIMER}")
    ld = {'@context': 'https://schema.org', '@graph': [
        {'@type': 'BreadcrumbList', 'itemListElement': [{'@type': 'ListItem', 'position': 1, 'name': 'Filing Flows', 'item': base + '/'},
                                                         {'@type': 'ListItem', 'position': 2, 'name': 'Disclosures', 'item': base + '/disclosures/'},
                                                         {'@type': 'ListItem', 'position': 3, 'name': 'Insider signals', 'item': url}]},
        {'@type': 'Dataset', 'name': 'Insider trading patterns and what followed', 'description': lead[:500], 'url': url, 'dateModified': istats.get('generated_at'),
         'creator': {'@type': 'Organization', 'name': 'Filing Flows', 'url': base + '/'}, 'isAccessibleForFree': True}]}
    os.makedirs(os.path.join(site, 'disclosures', 'insider-signals'), exist_ok=True)
    open(os.path.join(site, 'disclosures', 'insider-signals', 'index.html'), 'w', encoding='utf-8').write(seo.page(
        'Do Insider Trades Predict the Stock? Buys, Sales and Cluster Buys Scored | Filing Flows', lead[:300], url, body, 2, base + '/og.png', ld))
    return url


def link_from_company(site, slug):
    p = os.path.join(site, 'c', slug, 'index.html')
    if not os.path.exists(p):
        return
    t = open(p, encoding='utf-8').read()
    if 'timeline/' in t:
        return
    open(p, 'w', encoding='utf-8').write(t.replace('<nav class="seo-toc" aria-label="On this page">', '<nav class="seo-toc" aria-label="On this page"><a href="timeline/">Timeline</a>', 1))


def write(site, base):
    base = base.rstrip('/')
    ix = read(os.path.join(site, 'data', 'index.json')) or {}
    rows = ix.get('companies') if isinstance(ix, dict) else ix
    hub = os.path.join(site, 'disclosures', 'data')
    stats = read(os.path.join(site, 'data', 'event-stats.json'))
    istats = read(os.path.join(site, 'data', 'insider-stats.json'))
    urls, cards = [], []
    for r in rows or []:
        t = r.get('ticker')
        slug = seo.slug_for(r)
        if not t or not os.path.exists(os.path.join(site, 'c', slug, 'index.html')):
            continue
        try:
            out = page_for(r, base, slug, site, hub, stats, istats)
        except Exception as err:  # noqa: BLE001
            print(f"timeline skipped ({t}): {err}")
            continue
        if not out:
            continue
        url, mod, doc, card = out
        d = os.path.join(site, 'c', slug, 'timeline')
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'index.html'), 'w', encoding='utf-8').write(doc)
        link_from_company(site, slug)
        urls.append((url, mod))
        cards.append(card)
    sig = signals_page(site, base, istats, cards)
    if sig:
        urls.insert(0, (sig, (istats or {}).get('generated_at')))
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f'<url><loc>{xesc(u)}</loc>' + (f'<lastmod>{xesc(str(m)[:10])}</lastmod>' if m else '') + '</url>' for u, m in urls]
    sm.append('</urlset>')
    open(os.path.join(site, 'sitemap-timelines.xml'), 'w', encoding='utf-8').write('\n'.join(sm))
    robots = os.path.join(site, 'robots.txt')
    txt = open(robots).read() if os.path.exists(robots) else f'User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n'
    if 'sitemap-timelines.xml' not in txt:
        open(robots, 'w').write(txt.rstrip('\n') + f'\nSitemap: {base}/sitemap-timelines.xml\n')
    return len(urls)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', default='_site')
    ap.add_argument('--site-url', default=os.environ.get('SITE_URL', '') or 'https://filing-flows.com')
    a = ap.parse_args()
    m = re.search(r'https?://[^\s"]+', a.site_url or '')
    print('timeline pages:', write(a.site, m.group(0) if m else 'https://filing-flows.com'))
