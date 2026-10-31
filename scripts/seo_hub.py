"""Crawlable pages for the Disclosure Hub's views and for material 8-K events.

The hub itself is one page with #tab routes (disclosures/#rotation …); search engines index a URL, not a fragment.
Each important view gets its own URL with the current figures drawn into the page — a snapshot that reads without
script, with its own analysis, charts and links to every company's pages — and a link to the live, interactive view:

    disclosures/signals/        13F crowding, officials and insiders in one table
    disclosures/smart-money/    the quarter's 13F flows: net buying and selling, new positions and exits
    disclosures/insider-trades/ Form 4: clusters of insider buying, CEO and CFO sales, 10b5-1 plans
    disclosures/congress-trades/ members of Congress and officials: most bought and sold in 90 days
    disclosures/activist-stakes/ Schedule 13D and 13G: holders above 5%
    disclosures/form-144/       notices of proposed insider sales
    disclosures/8-k-events/     8-K items by kind, with an event page each (below)
    disclosures/short-interest/ FINRA short interest: rises, falls, days to cover
    disclosures/sector-rotation/ sectors' growth, margins and relative strength (the RRG's inputs)
    disclosures/options/        implied volatility, put/call, max pain, gamma walls
    disclosures/guidance-track-record/ who meets the guidance it gives
    disclosures/cross-holdings/ who owns whom: institutions and companies holding each other
    disclosures/investment-gains/ companies' gains on equity investments, and what they bought

    events/<company>-<topic>-<date>/  one page per material 8-K (deals, material agreements, leadership changes,
                                      impairments, restatements, debt, bankruptcy, delisting, auditor, control)
    events/                           every event page, by kind

The event archive (store/seo-events.json) keeps each event once it was seen, so event pages stay up after the
hub's rolling window moves on. sitemap-hub.xml (robots.txt, IndexNow).

    python scripts/seo_hub.py --site _site --store store
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
import seo_svg as SV  # noqa: E402

e, fdate, display_name = seo.e, seo.fdate, seo.display_name
DISCLAIMER = ("<p class='muted'>Read automatically from SEC EDGAR (13F, Form 4, Form 144, Schedule 13D/G, 8-K, XBRL), House and Senate "
              "disclosures, FINRA and exchange data; errors are possible. Not investment advice.</p>")


def read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def money(v):
    if v is None:
        return '—'
    a, s = abs(v), '−' if v < 0 else ''
    return f"{s}${a / 1e12:.2f}T" if a >= 1e12 else f"{s}${a / 1e9:.2f}B" if a >= 1e9 else f"{s}${a / 1e6:.1f}M" if a >= 1e6 else f"{s}${a / 1e3:.0f}K" if a >= 1e3 else f"{s}${a:,.0f}"


def num(v, d=0):
    return '—' if v is None else f"{v:,.{d}f}"


def table(head, rows):
    return (f"<div class='tbl-wrap'><table><thead><tr>{''.join(f'<th>{e(h)}</th>' for h in head)}</tr></thead><tbody>"
            + ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in rows) + '</tbody></table></div>')


def tiles(items):
    return "<div class='seo-tiles'>" + ''.join(f"<div class='seo-tile'><span>{e(k)}</span><b>{e(v)}</b></div>" for k, v in items if v not in (None, '')) + '</div>'


class Links:
    """Ticker or CIK → the company's page, from a page `depth` folders below the site root."""
    def __init__(self, site):
        ix = read(os.path.join(site, 'data', 'index.json')) or {}
        self.rows = (ix.get('companies') if isinstance(ix, dict) else ix) or []
        self.by_t, self.by_cik = {}, {}
        for r in self.rows:
            s = seo.slug_for(r)
            if not os.path.exists(os.path.join(site, 'c', s, 'index.html')) and os.path.isdir(os.path.join(site, 'c')):
                continue
            if r.get('ticker'):
                self.by_t.setdefault(r['ticker'].upper(), (s, r))
            self.by_cik.setdefault(int(r['cik']), (s, r))

    def row(self, ticker=None, cik=None):
        hit = self.by_t.get((ticker or '').upper()) or (self.by_cik.get(int(cik)) if str(cik or '').isdigit() else None)
        return hit[1] if hit else None

    def __call__(self, ticker=None, label=None, cik=None, depth=2):
        hit = self.by_t.get((ticker or '').upper()) or (self.by_cik.get(int(cik)) if str(cik or '').isdigit() else None)
        text = e(label or ticker or '—')
        return f"<a href='{'../' * depth}c/{hit[0]}/'><b>{text}</b></a>" if hit else f"<b>{text}</b>"


def nm(s):
    return display_name(s or '')


# ------------------------------------------------------------------------------------------------- the hub's views
# each returns (slug, tab, title, h1, lead, body) or None
def signals(hub, L):
    d = read(os.path.join(hub, 'market', 'signals.json')) or {}
    rows = d.get('rows') or []
    if len(rows) < 10:
        return None
    tags, ck = d.get('tags') or {}, d.get('clock') or {}
    cnt = {}
    for r in rows:
        for t in r.get('tags') or []:
            cnt[t] = cnt.get(t, 0) + 1
    short = lambda t: (tags.get(t) or t).split(':')[0]
    top = sorted(rows, key=lambda r: (-(r.get('heat') or 0), -abs((r.get('f13') or {}).get('usd_net') or 0)))
    inflow = sorted([r for r in rows if (r.get('f13') or {}).get('usd_net')], key=lambda r: -r['f13']['usd_net'])
    both = [r for r in rows if {'officials_buying', 'insider_buying'} & set(r.get('tags') or []) and 'new_money' in (r.get('tags') or []) or
            {'crowded_buy', 'insider_buying'} <= set(r.get('tags') or [])]
    lead = (f"{len(rows)} stocks where 13F managers, members of Congress, company insiders or the company's own results sent a signal this quarter "
            f"({e(ck.get('managers_filed') or '')} managers' 13F reports for the quarter ended {e(fdate(ck.get('report_quarter_end') or ''))}). "
            f"The largest net 13F inflow was {inflow[0]['ticker']} ({money(inflow[0]['f13']['usd_net'])}); "
            f"{len(both)} stocks were bought by managers and by insiders or officials at once." if inflow else '')
    body = tiles([('Stocks with a signal', num(len(rows))), ('13F managers filed', num(ck.get('managers_filed'))),
                  ('Quarter', fdate(ck.get('report_quarter_end') or '')), ('Prices to', fdate(ck.get('latest_close') or ''))])
    body += SV.hbars([(short(t), n) for t, n in sorted(cnt.items(), key=lambda kv: -kv[1])], str, 'How many stocks carry each signal', n=17,
                     note='A stock can carry several. Thresholds: ' + ', '.join(f"{k.replace('_usd', '').replace('_', ' ')} {money(v) if 'usd' in k else v}" for k, v in (d.get('thresholds') or {}).items()) + '.')
    body += SV.diverging([(r['ticker'], r['f13']['usd_net']) for r in inflow[:8] + inflow[-8:]], money, 'Largest net 13F buying (+) and selling (−), in dollars',
                         note='Dollars added minus dollars sold across every manager that filed, at the quarter-end price.', n=16)
    body += "<h2>The strongest signals</h2>" + table(['Stock', '13F net', 'Managers +/−', 'Officials 90d buy/sell', 'Signals'], [
        [L(r['ticker'], f"{r['ticker']} · {nm(r.get('name'))}"), money((r.get('f13') or {}).get('usd_net')),
         f"{num((r.get('f13') or {}).get('buyers'))} / {num((r.get('f13') or {}).get('sellers'))}",
         f"{(r.get('officials') or {}).get('d90_buys', 0)} / {(r.get('officials') or {}).get('d90_sells', 0)}",
         f"<span class='muted' style='white-space:normal'>{e(', '.join(short(t) for t in r.get('tags') or []))}</span>"]
        for r in top[:40]])
    if both:
        body += "<h2>Bought by managers and by insiders or officials</h2><ul class='seo-list'>" + ''.join(
            f"<li>{L(r['ticker'], r['ticker'])} {e(nm(r.get('name')))} — " + e(', '.join(short(t) for t in r.get('tags') or [])) + '</li>' for r in both[:25]) + '</ul>'
    return ('signals', 'signals', 'Stock signals from 13F, Congress and insider filings', 'Stock signals: where managers, officials and insiders agree', lead, body)


def smart(hub, L):
    d = read(os.path.join(hub, 'market', 'flows.json')) or {}
    w = (d.get('windows') or {}).get('quarter') or {}
    ls = (w.get('lists') or {}).get('stocks') or {}
    if not ls.get('net_buy'):
        return None
    tot = w.get('totals') or {}
    nb, ns, newp, ex, fst = ls.get('net_buy') or [], ls.get('net_sell') or [], ls.get('new_positions') or [], ls.get('exits') or [], ls.get('first_on_file') or []
    lab = lambda r: r.get('ticker') or nm(r.get('name') or r.get('issuer'))
    lead = (f"{num(w.get('managers'))} 13F managers reported for {e(w.get('label') or '')}: they bought {money(tot.get('usd_add'))} of stock and sold "
            f"{money(tot.get('usd_sold'))}. Most net buying: {', '.join(lab(r) for r in nb[:3])}; most net selling: {', '.join(lab(r) for r in ns[:3])}"
            + (f". The largest new listing held was {lab(fst[0])}, bought by {num(fst[0].get('buyers'))} managers for {money(fst[0].get('usd_add'))}." if fst else '.'))
    body = tiles([('Managers', num(w.get('managers'))), ('Bought', money(tot.get('usd_add'))), ('Sold', money(tot.get('usd_sold'))),
                  ('Net', money((tot.get('usd_add') or 0) - (tot.get('usd_sold') or 0)))])
    body += SV.diverging([(lab(r), r.get('usd_net')) for r in nb[:10] + ns[:10]], money, 'Net 13F buying (+) and selling (−), largest of the quarter', n=20,
                         note='Every manager that filed: dollars added minus dollars sold.')
    row = lambda r: [L(r.get('ticker'), lab(r)), e(nm(r.get('name') or r.get('issuer'))), money(r.get('usd_net')), f"{num(r.get('buyers'))} / {num(r.get('sellers'))}",
                     f"{num(r.get('new'))} / {num(r.get('exits'))}", e(', '.join(f"{nm(x['manager'])} {money(x['usd'])}" for x in (r.get('top_buy') or [])[:2]))]
    hd = ['Stock', 'Name', 'Net $', 'Buyers / sellers', 'New / exits', 'Largest buyers']
    body += '<h2>Most net buying</h2>' + table(hd, [row(r) for r in nb[:25]])
    body += '<h2>Most net selling</h2>' + table(hd, [row(r) for r in ns[:25]])
    body += '<h2>Most new positions</h2>' + table(hd, [row(r) for r in newp[:15]])
    body += '<h2>Most exits</h2>' + table(hd, [row(r) for r in ex[:15]])
    if fst:
        body += "<h2>New to 13F this quarter (IPOs, spin-offs, listings)</h2>" + table(hd, [row(r) for r in fst[:15]])
    return ('smart-money', 'smart', f"Smart money: 13F buying and selling, {w.get('label', '').split(' —')[0]}", 'Smart money: what 13F managers bought and sold', lead, body)


def insiders(hub, L):
    d = read(os.path.join(hub, 'market', 'insiders.json')) or {}
    sm = d.get('summary') or []
    if len(sm) < 5:
        return None
    buys = sorted([r for r in sm if r.get('buy_value')], key=lambda r: -r['buy_value'])
    sells = sorted([r for r in sm if r.get('sell_value')], key=lambda r: -r['sell_value'])
    clus = [r for r in buys if r.get('cluster') or (r.get('buyers30') or 0) >= 3]
    cs = [r for r in sells if r.get('ceo_cfo_sell')]
    bv, sv = sum(r.get('buy_value') or 0 for r in sm), sum(r.get('sell_value') or 0 for r in sm)
    lead = (f"Since {fdate(d.get('since') or '')}, insiders bought {money(bv)} and sold {money(sv)} of their own companies' stock in the open market "
            f"(Form 4, codes P and S) across {len(sm)} companies. {len(clus)} companies had a cluster — three or more insiders buying within 30 days — "
            f"the pattern studies find most informative" + (f"; the largest purchase total was at {nm(buys[0].get('issuer'))} ({money(buys[0]['buy_value'])})." if buys else '.'))
    body = tiles([('Companies', num(len(sm))), ('Bought', money(bv)), ('Sold', money(sv)), ('Buying clusters', num(len(clus))), ('CEO/CFO selling', num(len(cs)))])
    body += SV.hbars([(r.get('ticker') or nm(r.get('issuer')), r['buy_value']) for r in buys], money, 'Largest insider buying, by company', n=12, color=SV.GREEN)
    body += SV.hbars([(r.get('ticker') or nm(r.get('issuer')), r['sell_value']) for r in sells], money, 'Largest insider selling, by company', n=12, color=SV.RED,
                     note='Sales under a 10b5-1 plan were scheduled in advance and say less about the insider’s view.')
    row = lambda r: [L(r.get('ticker'), r.get('ticker') or nm(r.get('issuer')), r.get('cik')), e(nm(r.get('issuer'))), f"{r.get('buys', 0)} · {money(r.get('buy_value'))}",
                     f"{r.get('sells', 0)} · {money(r.get('sell_value'))}", e(', '.join((r.get('buyers') or [])[:4])), e(fdate(r.get('last')))]
    hd = ['Ticker', 'Company', 'Buys', 'Sells', 'Buyers', 'Last']
    if clus:
        body += '<h2>Clusters: several insiders buying</h2>' + table(hd, [row(r) for r in clus[:25]])
    body += '<h2>Largest insider buying</h2>' + table(hd, [row(r) for r in buys[:30]])
    if cs:
        body += '<h2>CEO or CFO selling</h2>' + table(hd, [row(r) for r in cs[:20]])
    body += "<p>Day by day: <a href='../../daily/insider-buying/'>today’s insider buying</a> · <a href='../../daily/insider-selling/'>today’s insider selling</a>.</p>"
    return ('insider-trades', 'insiders', 'Insider trading: buying clusters, CEO and CFO sales (Form 4)', 'Insider buying and selling (Form 4)', lead, body)


def congress(hub, L):
    d = read(os.path.join(hub, 'market', 'officials-trades.json')) or {}
    sm = (d.get('summary') or {}).get('d90') or []
    if len(sm) < 5:
        return None
    mon = d.get('monitor') or {}
    by = sorted(sm, key=lambda r: -(r.get('buys') or 0))
    se = sorted(sm, key=lambda r: -(r.get('sells') or 0))
    people = {}
    for r in d.get('latest_reports') or []:
        people.setdefault(r.get('person'), r)
    lead = (f"Stock trades disclosed by members of Congress and other officials in the last 90 days (periodic transaction reports). Most bought: "
            f"{', '.join(r['ticker'] for r in by[:5])}; most sold: {', '.join(r['ticker'] for r in se[:5])}. Reports reach us on average "
            f"{mon.get('lag_days', '—')} days after the trade, the delay the law allows (up to 45 days).")
    body = tiles([('Stocks traded (90 days)', num(len(sm))), ('Reports read (30 days)', num(mon.get('ptr_last_30_days_read'))),
                  ('Newest report', fdate(mon.get('newest_ptr_filed') or '')), ('Trades on file', num(len(d.get('trades') or [])))])
    body += SV.diverging([(r['ticker'], (r.get('buys') or 0) - (r.get('sells') or 0)) for r in sm], lambda v: f"{v:+.0f}", 'Officials’ buys minus sells by stock (90 days)', n=16,
                         note='Count of disclosed transactions; amounts are reported in ranges only.')
    body += '<h2>Most traded by officials (90 days)</h2>' + table(['Stock', 'Buys', 'Sells', 'Who bought', 'Who sold', 'Last'], [
        [L(r['ticker'], f"{r['ticker']} · {nm(r.get('name'))}"), num(r.get('buys')), num(r.get('sells')), e(', '.join((r.get('people_buy') or [])[:4])),
         e(', '.join((r.get('people_sell') or [])[:4])), e(fdate(r.get('last')))] for r in sorted(sm, key=lambda r: -((r.get('buys') or 0) + (r.get('sells') or 0)))[:40]])
    if people:
        body += '<h2>Latest reports</h2>' + table(['Official', 'Office', 'Filed', 'Trades', 'Buys / sells', 'Tickers'], [
            [e(p), e(r.get('office')), e(fdate(r.get('filed_date'))), num(r.get('trades')), f"{r.get('buys', 0)} / {r.get('sells', 0)}",
             e(', '.join((r.get('tickers') or [])[:6]))] for p, r in list(people.items())[:25]])
    body += "<p>Day by day: <a href='../../daily/congress-trades/'>today’s Congress stock trades</a>.</p>"
    return ('congress-trades', 'trades', 'Congress stock trades: what members of Congress bought and sold', 'Congress and officials’ stock trades', lead, body)


def stakes(hub, L):
    d = read(os.path.join(hub, 'market', 'stakes.json')) or {}
    sm = d.get('summary') or []
    if len(sm) < 5:
        return None
    act = sorted([r for r in sm if r.get('new13d')], key=lambda r: (-(r.get('new13d') or 0), -(r.get('max_percent') or 0)))
    big = sorted([r for r in sm if r.get('max_percent')], key=lambda r: -r['max_percent'])
    lat = [r for r in d.get('latest') or [] if str(r.get('form', '')).upper().replace('SC ', '').startswith('13D') and not r.get('amendment')]
    lead = (f"{len(sm)} companies with Schedule 13D or 13G filings since {fdate(d.get('since') or '')}: holders crossing 5% must file within days. "
            f"A 13D (rather than the passive 13G) means the holder may seek to influence the company; {len(act)} companies drew a new 13D"
            + (f", most at {nm(act[0].get('issuer'))} ({act[0]['new13d']})." if act else '.'))
    body = tiles([('Companies', num(len(sm))), ('With a new 13D', num(len(act))), ('Filings on file', num(d.get('on_file'))),
                  ('Largest stake', f"{big[0]['max_percent']:.1f}%" if big else '')])
    body += SV.hbars([(r.get('ticker') or nm(r.get('issuer')), r['max_percent']) for r in big], lambda v: f"{v:.1f}%", 'Largest stakes disclosed (percent of the class)', n=12)
    row = lambda r: [L(r.get('ticker'), r.get('ticker') or nm(r.get('issuer')), r.get('cik')), e(nm(r.get('issuer'))), num(r.get('filings')), num(r.get('new13d')),
                     f"{r.get('max_percent') or 0:.1f}%", e(', '.join((r.get('filers') or [])[:3])), e(fdate(r.get('last')))]
    hd = ['Ticker', 'Company', 'Filings', 'New 13D', 'Largest %', 'Filers', 'Last']
    body += '<h2>New activist (13D) stakes</h2>' + table(hd, [row(r) for r in act[:30]])
    body += '<h2>Largest stakes</h2>' + table(hd, [row(r) for r in big[:20]])
    if lat:
        body += '<h2>Latest original 13D filings</h2>' + table(['Filed', 'Company', 'Holder', 'Percent', 'Filing'], [
            [e(fdate(r.get('filed'))), L(None, nm(r.get('issuer')), r.get('issuer_cik')), e(r.get('filer') or r.get('person')),
             f"{r['percent']:.1f}%" if r.get('percent') else '—', f"<a href='{e(r.get('url'))}' rel='nofollow'>SEC</a>"] for r in lat[:25]])
    body += "<p>Day by day: <a href='../../daily/activist-stakes/'>today’s new 13D stakes</a>.</p>"
    return ('activist-stakes', 'stakes', 'Activist stakes: new Schedule 13D and 13G filings above 5%', 'Activist and 5% stakes (13D / 13G)', lead, body)


def form144(hub, L):
    d = read(os.path.join(hub, 'market', 'form144.json')) or {}
    sm = d.get('summary') or []
    if len(sm) < 5:
        return None
    big = sorted([r for r in sm if r.get('value')], key=lambda r: -r['value'])
    tot = sum(r.get('value') or 0 for r in sm)
    plan = sum(1 for r in sm if r.get('plan'))
    lead = (f"Form 144 notices are filed before an affiliate sells restricted or control stock. Since {fdate(d.get('since') or '')}, {len(sm)} companies drew notices "
            f"for {money(tot)} of proposed sales; {plan} of them under a 10b5-1 plan. A notice is an intention, not a sale — the Form 4 shows what was sold.")
    body = tiles([('Companies', num(len(sm))), ('Proposed sales', money(tot)), ('Under a 10b5-1 plan', num(plan)), ('Notices on file', num(d.get('on_file')))])
    body += SV.hbars([(r.get('ticker') or nm(r.get('issuer')), r['value']) for r in big], money, 'Largest proposed insider sales (Form 144)', n=12, color=SV.RED)
    body += '<h2>Largest proposed sales</h2>' + table(['Ticker', 'Company', 'Notices', 'Value', 'Sellers', 'Plan', 'Last'], [
        [L(r.get('ticker'), r.get('ticker') or nm(r.get('issuer')), r.get('cik')), e(nm(r.get('issuer'))), num(r.get('notices')), money(r.get('value')),
         e(', '.join((r.get('sellers') or [])[:3])), 'yes' if r.get('plan') else '', e(fdate(r.get('last')))] for r in big[:40]])
    return ('form-144', 'form144', 'Form 144: proposed insider stock sales', 'Form 144: proposed insider sales', lead, body)


def shorts(hub, L):
    d = read(os.path.join(hub, 'market', 'short-interest.json')) or {}
    rows = {r['ticker']: r for r in d.get('rows') or [] if r.get('ticker')}
    top = d.get('top') or {}
    if len(rows) < 20:
        return None
    rs = lambda k: [rows[t] for t in top.get(k) or [] if t in rows]
    rise, fall, dtc, lg = rs('rise'), rs('fall'), rs('dtc'), rs('largest')
    lead = (f"Short interest for the settlement date {fdate(d.get('settlement_date') or '')} against {fdate(d.get('previous_date') or '')}, {num(d.get('stocks'))} stocks. "
            + (f"The largest rise was {rise[0]['ticker']} ({rise[0]['change_pct']:+.1f}%), the highest days to cover {dtc[0]['ticker']} ({dtc[0]['dtc']:.1f} days)." if rise and dtc else ''))
    body = tiles([('Settlement date', fdate(d.get('settlement_date') or '')), ('Stocks', num(d.get('stocks'))), ('Shown', num(d.get('shown')))])
    body += SV.diverging([(r['ticker'], r.get('change_pct')) for r in rise[:10] + fall[:10]], lambda v: f"{v:+.0f}%", 'Short interest: largest rises and falls', n=20)
    row = lambda r: [L(r['ticker'], r['ticker']), e(nm(r.get('name'))), num(r.get('short')), f"{r.get('change_pct') or 0:+.1f}%", f"{r.get('dtc') or 0:.1f}", e(r.get('market'))]
    hd = ['Ticker', 'Name', 'Shares short', 'Change', 'Days to cover', 'Market']
    for h, xs in (('Largest rises', rise), ('Largest falls', fall), ('Most days to cover', dtc), ('Most shares short', lg)):
        body += f'<h2>{h}</h2>' + table(hd, [row(r) for r in xs[:25]])
    return ('short-interest', 'shorts', 'Short interest: biggest rises, falls and days to cover', 'Short interest', lead, body)


def rotation(hub, L):
    d = read(os.path.join(hub, 'market', 'rotation.json')) or {}
    f = d.get('fields') or []
    sec = d.get('sectors') or {}
    if not sec or 'cal' not in f:
        return None
    lab = {v['key']: v.get('label') or v['key'] for v in d.get('vars') or []}
    lab.update({'revg': 'Revenue Y/Y %', 'om': 'Op. margin %', 'nm': 'Net margin %', 'ret': 'Return, quarter %', 'rel': 'Vs market %', 'mom121': 'Momentum',
                'f13': '13F net managers'})
    idx = {k: i for i, k in enumerate(f)}
    last = lambda p: next((x for x in reversed(p or []) if x and x[idx['rs']] is not None), None) if 'rs' in idx else (p or [None])[-1]
    keys = [k for k in ('revg', 'om', 'nm', 'ret', 'rel', 'rs', 'mom121', 'f13') if k in idx]
    rows = []
    for sid, s in sec.items():
        x = last(s.get('p'))
        if x:
            rows.append((s.get('name') or sid, x))
    if len(rows) < 4:
        return None
    pts = [(n, x[idx['rs']], x[idx['mom121']] if 'mom121' in idx and x[idx['mom121']] is not None else 0, None) for n, x in rows if x[idx['rs']] is not None]
    q = rows[0][1][idx['cal']]
    lead = (f"Where each sector stands in {q}: revenue growth, margins, returns and relative strength against the market ({d.get('benchmark') or 'SPY'}). "
            f"These are the inputs of the relative rotation graph (RRG): leaders have strength and momentum, laggards neither. "
            f"Strongest now: {', '.join(n for n, *_ in sorted(pts, key=lambda p: -(p[1] or 0))[:3])}.")
    body = SV.hbars([(n, x) for n, x, *_ in sorted(pts, key=lambda p: -(p[1] or 0))], lambda v: f"{v:.0f}", f"Sectors in {q}: {lab.get('rs', 'relative strength')}", n=12,
                    note='Higher is stronger against the market; from the hub’s rotation data.')
    body += table(['Sector'] + [lab.get(k, k) for k in keys], [[e(n)] + [num(x[idx[k]], 1) for k in keys] for n, x in sorted(rows, key=lambda r: -(r[1][idx['rs']] or 0) if 'rs' in idx else 0)])
    cos = sorted([c for c in d.get('companies') or [] if c.get('p')], key=lambda c: -((last(c['p']) or [0] * len(f))[idx['rs']] or 0) if 'rs' in idx else 0)
    if cos:
        body += '<h2>Strongest companies</h2>' + table(['Company', 'Sector'] + [lab.get(k, k) for k in keys], [
            [L(c.get('t'), f"{c.get('t')} · {nm(c.get('n'))}", c.get('cik')), e((sec.get(c.get('s')) or {}).get('name') or c.get('s'))] + [num((last(c['p']) or [None] * len(f))[idx[k]], 1) for k in keys]
            for c in cos[:30]])
    return ('sector-rotation', 'rotation', f"Sector rotation {q}: relative strength, momentum, growth and margins", 'Sector rotation (RRG)', lead, body)


def options(hub, L):
    d = read(os.path.join(hub, 'market', 'options.json')) or {}
    rows = [r for r in d.get('rows') or [] if r.get('iv30') is not None]
    if len(rows) < 10:
        return None
    ch = sorted([r for r in rows if r.get('iv30_chg') is not None], key=lambda r: -abs(r['iv30_chg']))
    hi = sorted(rows, key=lambda r: -r['iv30'])
    lead = (f"Options positioning for {len(rows)} stocks and ETFs: 30-day implied volatility, put/call open interest, max pain and the strikes with the most "
            f"dealer gamma. Highest implied volatility: {', '.join(r['ticker'] for r in hi[:4])}; largest change: {', '.join(r['ticker'] for r in ch[:4])}.")
    body = SV.diverging([(r['ticker'], r['iv30_chg']) for r in ch], lambda v: f"{v:+.1f}", 'Change in 30-day implied volatility (points)', n=16)
    body += table(['Ticker', 'Spot', 'IV30', 'Δ IV', 'Put/call OI', 'Max pain', 'Call wall', 'Put wall', 'Gamma flip'], [
        [L(r['ticker'], r['ticker']), num(r.get('spot'), 2), f"{r['iv30']:.1f}%", f"{r.get('iv30_chg') or 0:+.1f}", num(r.get('pc_oi'), 2),
         f"{num(r.get('max_pain'), 0)} ({e(r.get('max_pain_exp') or '')})", num(r.get('call_wall'), 0), num(r.get('put_wall'), 0), num(r.get('gamma_flip'), 0)]
        for r in sorted(rows, key=lambda r: -(r.get('contracts') or 0))[:60]])
    return ('options', 'options', 'Options positioning: implied volatility, put/call, max pain and gamma walls', 'Options positioning', lead, body)


def guidance(hub, L):
    d = read(os.path.join(hub, 'market', 'guidance-board.json')) or {}
    rows = [r for r in d.get('rows') or [] if (r.get('n') or 0) >= 2 and r.get('rate') is not None]
    if len(rows) < 10:
        return None
    rate = lambda r: r['rate'] * 100 if r['rate'] <= 1 else r['rate']
    best = sorted(rows, key=lambda r: (-rate(r), -r['n']))
    worst = sorted(rows, key=lambda r: (rate(r), -r['n']))
    sect = {}
    for r in rows:
        sect.setdefault(r.get('sector') or 'other', []).append(rate(r))
    avg = sum(rate(r) for r in rows) / len(rows)
    rec = [x for x in d.get('recent') or [] if len(x) >= 6 and x[3] in ('raised', 'lowered', 'withdrawn')]
    lead = (f"How often companies deliver what they guide: {len(rows)} companies with at least two guided periods judged against what they then reported. "
            f"On average they met or beat {avg:.0f}% of their guided figures; {sum(1 for r in rows if rate(r) >= 99.9)} met every one.")
    body = tiles([('Companies judged', num(len(rows))), ('Average met or beat', f"{avg:.0f}%"), ('Raised lately', num(sum(1 for x in rec if x[3] == 'raised'))),
                  ('Lowered lately', num(sum(1 for x in rec if x[3] == 'lowered')))])
    body += SV.hbars([(k.replace('-', ' ').capitalize(), sum(v) / len(v)) for k, v in sect.items() if len(v) >= 3], lambda v: f"{v:.0f}%",
                     'Share of guided figures met or beaten, by sector', n=12)
    row = lambda r: [L(r.get('t'), f"{r.get('t')} · {nm(r.get('name'))}", r.get('cik')), num(r.get('n')), f"{rate(r):.0f}%", num(r.get('beat')), num(r.get('miss')),
                     f"{r.get('raised', 0)} / {r.get('lowered', 0)}"]
    hd = ['Company', 'Guided periods', 'Met or beat', 'Beat', 'Missed', 'Raised / lowered']
    body += '<h2>Most reliable guidance</h2>' + table(hd, [row(r) for r in best[:30]])
    body += '<h2>Least reliable guidance</h2>' + table(hd, [row(r) for r in worst[:20]])
    if rec:
        body += '<h2>Latest guidance changes</h2>' + table(['Filed', 'Company', 'Change', 'Headline'], [
            [e(fdate(x[0])), L(x[1], x[1], x[2]), e(x[3]), f"<a href='{e(x[5])}' rel='nofollow'>{e(x[4][:140])}</a>"] for x in rec[:30]])
    body += "<p>Day by day: <a href='../../daily/guidance-changes/'>today’s guidance changes</a>.</p>"
    return ('guidance-track-record', 'guidance', 'Guidance track record: which companies meet the guidance they give', 'Guidance track record', lead, body)


def cross(hub, L):
    d = read(os.path.join(hub, 'market', 'crossholdings.json')) or {}
    cos = d.get('companies') or []
    if len(cos) < 10:
        return None
    ins = sorted(d.get('institutions') or [], key=lambda r: -(r.get('total') or 0))
    holders = [c for c in cos if c.get('is_holder')]
    hi = sorted([c for c in cos if c.get('f13_pct') is not None], key=lambda c: -c['f13_pct'])
    chains = sorted(d.get('chains') or [], key=lambda c: -(c.get('usd2') or 0))
    lead = (f"Who owns whom among {len(cos)} large companies: the institutions that hold them, the companies that hold each other "
            f"({len(holders)} also own listed stakes), and {len(chains)} chains of indirect ownership (A owns B, which owns C).")
    body = tiles([('Companies', num(len(cos))), ('Also holders', num(len(holders))), ('Ownership chains', num(len(chains))), ('Quarter', e(d.get('quarter') or ''))])
    body += SV.hbars([(c.get('ticker'), c['f13_pct'] * 100) for c in hi], lambda v: f"{v:.0f}%", 'Share of the company held by 13F institutions', n=12)
    body += '<h2>The largest institutions</h2>' + table(['Institution', '13F holdings', 'Period'], [[e(nm(r.get('name'))), money(r.get('total')), e(r.get('period'))] for r in ins[:12]])
    body += '<h2>Companies and their largest holders</h2>' + table(['Company', 'Market value', '13F holders', 'Held by 13F', 'Largest holders'], [
        [L(c.get('ticker'), f"{c.get('ticker')} · {nm(c.get('name'))}", c.get('cik')), money(c.get('mcap')), num(c.get('f13_holders')),
         f"{(c.get('f13_pct') or 0) * 100:.0f}%", e(', '.join(f"{nm(x['name'])} {(x.get('pct') or 0) * 100:.1f}%" for x in (c.get('top_institutions') or [])[:3]))]
        for c in sorted(cos, key=lambda c: -(c.get('mcap') or 0))[:40]])
    if chains:
        body += '<h2>Ownership chains</h2>' + table(['Holder', 'Via', 'Holds', 'Stake in the middle company', 'Its stake'], [
            [e(c.get('from')), L(c.get('via'), c.get('via')), L(c.get('to'), c.get('to')), money(c.get('usd1')), money(c.get('usd2'))] for c in chains[:30]])
    return ('cross-holdings', 'cross', 'Cross-holdings: who owns whom among listed companies', 'Cross-holdings: who owns whom', lead, body)


def investors(hub, L):
    d = None
    for p in (('research', 'investors', 'index.json'), ('research', 'investors', 'public', 'index.json')):
        d = read(os.path.join(hub, *p))
        if d:
            break
    rows = (d or {}).get('rows') if isinstance(d, dict) else d
    rows = [r for r in rows or [] if r.get('gains')]
    if len(rows) < 5:
        return None
    rows.sort(key=lambda r: -(r.get('gains') or 0))
    lead = (f"Listed companies with the largest gains on the stakes they hold in other companies (SEC XBRL: equity securities, equity-method and other investments), "
            f"and what their own filings, 13F reports and others’ filings say they bought. Largest: {nm(rows[0].get('name'))} ({money(rows[0]['gains'])}).")
    body = SV.hbars([(r.get('t') or nm(r.get('name')), r['gains']) for r in rows], money, 'Gains on investments, latest four quarters', n=15, color=SV.GREEN)
    body += table(['Company', 'Gains', 'Share of pre-tax profit', 'Largest holding'], [
        [L(r.get('t'), f"{r.get('t') or ''} · {nm(r.get('name'))}", r.get('cik')), money(r.get('gains')),
         f"{r['share'] * 100:.0f}%" if isinstance(r.get('share'), (int, float)) else '—', e(r.get('top_gainer') or '')] for r in rows[:40]])
    return ('investment-gains', 'investors', 'Which companies earn the most from their investments, and what they bought', 'Investment gains by company', lead, body)


# --------------------------------------------------------------------------------------------------- 8-K events
ITEMS = {'1.01': 'Entry into a material definitive agreement', '1.02': 'Termination of a material definitive agreement', '1.03': 'Bankruptcy or receivership',
         '1.05': 'Material cybersecurity incident', '2.01': 'Completion of an acquisition or disposition of assets', '2.02': 'Results of operations',
         '2.03': 'Creation of a direct financial obligation', '2.04': 'Triggering events that accelerate an obligation', '2.05': 'Costs of exit or disposal activities',
         '2.06': 'Material impairments', '3.01': 'Notice of delisting or failure to meet a listing standard', '3.02': 'Unregistered sales of equity securities',
         '3.03': 'Material modification of the rights of security holders', '4.01': 'Change in the certifying accountant',
         '4.02': 'Non-reliance on previously issued financial statements (restatement)', '5.01': 'Change in control', '5.02': 'Departure or appointment of directors and officers',
         '5.03': 'Amendments to the articles or bylaws', '5.07': 'Results of a shareholder vote', '7.01': 'Regulation FD disclosure', '8.01': 'Other events',
         '9.01': 'Financial statements and exhibits'}
WHY = {'1.01': 'A material agreement is one the company considers important enough to disclose within four business days: a merger agreement, a large supply or customer contract, a credit agreement or a licence. The terms often move the company’s outlook more than a quarter’s results.',
       '1.02': 'Ending a material agreement can remove revenue, financing or a planned deal; the filing says who ended it and whether penalties apply.',
       '1.03': 'A bankruptcy or receivership filing usually leaves common shareholders last in line; what matters is the plan, the financing and whether the shares survive.',
       '1.05': 'Companies must disclose a material cybersecurity incident within four business days of deciding it is material: its nature, scope and likely impact.',
       '2.01': 'Completing an acquisition or a sale changes the company’s size and mix from this quarter on; the price paid and how it was financed are in the filing.',
       '2.03': 'New debt or a guarantee: the amount, the rate and the maturity set the cost of capital and the repayment wall ahead.',
       '2.04': 'An event that accelerates debt — a default or covenant breach — can make borrowings due at once.',
       '2.05': 'Exit and restructuring costs: the charges to expect, the cash part, and the jobs or sites affected.',
       '2.06': 'An impairment writes down an asset — often goodwill from an acquisition — admitting it is worth less than paid.',
       '3.01': 'A delisting notice starts a compliance window; companies often answer with a reverse split, a plan, or a move to another market.',
       '4.01': 'A change of auditor is routine when cost-driven, a warning sign when it follows a disagreement — the filing must say which.',
       '4.02': 'Non-reliance means earlier financial statements should no longer be relied on: a restatement is coming.',
       '5.01': 'A change in control: someone now controls the company.',
       '5.02': 'Leadership changes: who leaves, who arrives and on what terms. A sudden CEO or CFO departure without a successor deserves attention.'}
TOPIC = {'deal': 'Mergers and acquisitions', 'contract': 'Material contracts', 'debt': 'Debt and financing', 'offering': 'Share offerings', 'ceo': 'CEO changes',
         'cfo': 'CFO changes', 'director': 'Board changes', 'impairment': 'Impairments', 'restructuring': 'Restructuring', 'restatement': 'Restatements',
         'bankruptcy': 'Bankruptcy', 'delisting': 'Delisting notices', 'auditor': 'Auditor changes', 'control': 'Changes in control', 'cyber': 'Cybersecurity incidents',
         'buyback': 'Buybacks', 'dividend': 'Dividends', 'fda': 'FDA decisions'}
MATERIAL_ITEMS = {'1.01', '1.02', '1.03', '1.05', '2.01', '2.03', '2.04', '2.05', '2.06', '3.01', '4.01', '4.02', '5.01'}
MATERIAL_TOPICS = {'deal', 'contract', 'debt', 'impairment', 'restructuring', 'restatement', 'bankruptcy', 'delisting', 'auditor', 'control', 'cyber', 'ceo', 'cfo', 'fda'}
KEEP = ('accession', 'url', 'form', 'filed', 'cik', 'company', 'items', 'code', 'topics', 'headline', 'quote', 'ticker', 'score')


def material(r):
    its = set(r.get('items') or [])
    return bool(its & MATERIAL_ITEMS or set(r.get('topics') or []) & MATERIAL_TOPICS) and (r.get('quote') or r.get('headline'))


def event_slug(r, L):
    row = L.row(r.get('ticker'), r.get('cik'))
    who = seo.slug_for(row) if row else re.sub(r'[^a-z0-9]+', '-', (r.get('company') or f"cik-{r.get('cik')}").lower()).strip('-')[:40]
    what = (r.get('topics') or [None])[0] or {'1.01': 'agreement', '2.01': 'acquisition', '2.03': 'debt', '5.02': 'leadership'}.get(r.get('code'), 'filing')
    return f"{who}-{what}-{r.get('filed', '')}-{str(r.get('accession', ''))[-6:]}"


def archive(site, store):
    rows = (read(os.path.join(site, 'disclosures', 'data', 'market', 'events8k.json')) or {}).get('rows') or []
    path = os.path.join(store, 'seo-events.json') if store else None
    old = (read(path) if path else None) or {}
    for r in rows:
        if r.get('accession') and material(r):
            old[r['accession']] = {k: r.get(k) for k in KEEP}
    keep = dict(sorted(old.items(), key=lambda kv: kv[1].get('filed') or '', reverse=True)[:20000])
    if path:
        os.makedirs(store, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(keep, f, separators=(',', ':'))
    return list(keep.values())


def event_pages(site, base, L, evs):
    """one page per material 8-K: what the item means, the company's own words, the company's figures and its other events"""
    evs = sorted(evs, key=lambda r: (r.get('filed') or '', r.get('accession') or ''), reverse=True)
    by_co, by_topic, urls = {}, {}, []
    for r in evs:
        r['_slug'] = event_slug(r, L)
        by_co.setdefault(str(r.get('cik')), []).append(r)
        for t in r.get('topics') or ['other']:
            by_topic.setdefault(t, []).append(r)
    for r in evs:
        try:
            row = L.row(r.get('ticker'), r.get('cik'))
            name = nm(r.get('company'))
            tk = r.get('ticker') or (row or {}).get('ticker') or ''
            its = [i for i in r.get('items') or [] if i != '9.01']
            kind = ITEMS.get(r.get('code')) or (ITEMS.get(its[0]) if its else '8-K')
            topic = TOPIC.get((r.get('topics') or [None])[0], kind)
            title = f"{name}{' (' + tk + ')' if tk else ''} 8-K, {fdate(r.get('filed'))}: {topic.lower() if topic != kind else kind.lower()}"
            body = (f"<p class='crumbs'><a href='../../'>Filing Flows</a> › <a href='../'>8-K events</a> › {e(name)}</p>"
                    f"<h1>{e(name)}: {e(kind.lower())}</h1><p class='muted'>Form {e(r.get('form') or '8-K')} filed {e(fdate(r.get('filed')))} · items "
                    f"{e(', '.join(its) or '—')}</p>")
            if r.get('headline'):
                body += f"<p class='seo-hl'><span>{e(topic)}</span>{e(r['headline'])}</p>"
            if r.get('quote'):
                body += f"<h2>What the filing says</h2><blockquote class='seo-quote'>{e(r['quote'][:1600])}</blockquote>"
            body += f"<p><a class='seo-cta' href='{e(r.get('url'))}' rel='nofollow'>Read the filing on SEC EDGAR →</a></p>"
            why = [f"<p><b>Item {e(i)} — {e(ITEMS.get(i, ''))}.</b> {e(WHY[i])}</p>" for i in its if i in WHY]
            if why:
                body += "<h2>What this kind of filing means</h2><div class='seo-note'>" + ''.join(why) + '</div>'
            if row:
                s = seo.slug_for(row)
                body += (f"<h2>{e(name)} at a glance</h2>" + tiles([('Latest quarter', row.get('label')), ('Revenue', row.get('rev')),
                                                                       ('Revenue Y/Y', seo.pct(row.get('yoy')) if row.get('yoy') is not None else None),
                                                                       ('Operating margin', f"{row['om']:.1f}%" if row.get('om') is not None else None),
                                                                       ('Industry', row.get('industry'))]))
                import seo_history as SH
                body += SH.sankey_figure(row['cik'], row.get('label') or '', f"{name} income statement and cash flow, {row.get('label')}", up='../../')
                body += f"<p><a href='../../c/{s}/'>{e(name)}: every quarter, Q/Q and Y/Y, holders and guidance →</a></p>"
            other = [x for x in by_co.get(str(r.get('cik')), []) if x is not r][:12]
            if other:
                body += f"<h2>{e(name)}’s other material 8-Ks</h2><ul class='seo-list'>" + ''.join(
                    f"<li><a href='../{x['_slug']}/'>{e(fdate(x.get('filed')))} — {e(TOPIC.get((x.get('topics') or [None])[0]) or ITEMS.get(x.get('code'), '8-K'))}</a>"
                    f"{' <span class=muted>' + e((x.get('headline') or '')[:100]) + '</span>' if x.get('headline') else ''}</li>" for x in other) + '</ul>'
            t0 = (r.get('topics') or [None])[0]
            same = [x for x in by_topic.get(t0, []) if x is not r][:10] if t0 else []
            if same:
                body += f"<h2>Other recent {e(TOPIC.get(t0, t0).lower())}</h2><ul class='seo-list'>" + ''.join(
                    f"<li><a href='../{x['_slug']}/'>{e(nm(x.get('company')))}</a> <span class='muted'>{e(fdate(x.get('filed')))}</span></li>" for x in same) + '</ul>'
            body += DISCLAIMER
            url = f"{base}/events/{r['_slug']}/"
            desc = (r.get('headline') or r.get('quote') or '')[:250] or f"{name} filed an 8-K on {fdate(r.get('filed'))}: {kind}."
            ld = {'@context': 'https://schema.org', '@graph': [
                {'@type': 'BreadcrumbList', 'itemListElement': [{'@type': 'ListItem', 'position': 1, 'name': 'Filing Flows', 'item': base + '/'},
                                                                 {'@type': 'ListItem', 'position': 2, 'name': '8-K events', 'item': base + '/events/'},
                                                                 {'@type': 'ListItem', 'position': 3, 'name': name, 'item': url}]},
                {'@type': 'NewsArticle', 'headline': title[:110], 'datePublished': r.get('filed'), 'dateModified': r.get('filed'), 'url': url,
                 'about': {'@type': 'Corporation', 'name': name, **({'tickerSymbol': tk} if tk else {})},
                 'publisher': {'@type': 'Organization', 'name': 'Filing Flows', 'url': base + '/'}}]}
            d = os.path.join(site, 'events', r['_slug'])
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, 'index.html'), 'w', encoding='utf-8') as f:
                f.write(seo.page(f"{title} | Filing Flows", desc, url, body, 2, base + '/og.png', ld))
            urls.append((url, r.get('filed')))
        except Exception as err:  # noqa: BLE001
            print(f"event page skipped ({r.get('accession')}): {err}")
    # the index: by kind, newest first
    secs = ''
    for t, xs in sorted(by_topic.items(), key=lambda kv: -len(kv[1])):
        secs += (f"<h2 id='{e(t)}'>{e(TOPIC.get(t, t.capitalize()))} <span class='muted'>{len(xs)}</span></h2><ul class='seo-list'>" + ''.join(
            f"<li><a href='{x['_slug']}/'>{e(nm(x.get('company')))}</a> <span class='muted'>{e(fdate(x.get('filed')))}"
            f"{' — ' + e((x.get('headline') or '')[:110]) if x.get('headline') else ''}</span></li>" for x in xs[:60]) + '</ul>')
    cnt = {t: len(xs) for t, xs in by_topic.items()}
    idx = (f"<p class='crumbs'><a href='../'>Filing Flows</a> › 8-K events</p><h1>Material 8-K events</h1>"
           f"<p class='lead'>{len(evs)} material current reports — deals, material agreements, new debt, impairments, restatements, leadership changes, "
           f"delisting notices — each with what the company wrote, what the item means and the company’s figures.</p>"
           + SV.hbars([(TOPIC.get(t, t), n) for t, n in sorted(cnt.items(), key=lambda kv: -kv[1])], str, 'Material 8-Ks by kind', n=14)
           + "<nav class='seo-toc'>" + ''.join(f"<a href='#{e(t)}'>{e(TOPIC.get(t, t))}</a>" for t in sorted(cnt, key=lambda t: -cnt[t])) + '</nav>' + secs + DISCLAIMER)
    os.makedirs(os.path.join(site, 'events'), exist_ok=True)
    with open(os.path.join(site, 'events', 'index.html'), 'w', encoding='utf-8') as f:
        f.write(seo.page('Material 8-K events: deals, debt, impairments, restatements, leadership changes | Filing Flows',
                         'Every material 8-K filed with the SEC, with the company’s own words, what the item means and the company’s figures.',
                         f"{base}/events/", idx, 1, base + '/og.png'))
    return [(f"{base}/events/", None)] + urls


def events_view(hub, L, evs):
    d = read(os.path.join(hub, 'market', 'events8k.json')) or {}
    cnt = d.get('counts') or {}
    if not cnt:
        return None
    rows = sorted(evs, key=lambda r: r.get('filed') or '', reverse=True)
    lead = (f"{num(d.get('on_file'))} 8-K current reports filed in the last {d.get('days') or ''} days, sorted into what they announce: "
            + ', '.join(f"{TOPIC.get(k, k).lower()} {v}" for k, v in sorted(cnt.items(), key=lambda kv: -kv[1])[:8]) + '. Each material one has its own page.')
    body = SV.hbars([(TOPIC.get(k, k.capitalize()), v) for k, v in cnt.items()], str, '8-K filings by what they announce', n=18)
    body += '<h2>Latest material events</h2>' + table(['Filed', 'Company', 'What', 'Headline'], [
        [e(fdate(r.get('filed'))), L(r.get('ticker'), nm(r.get('company')), r.get('cik')),
         f"<a href='../../events/{event_slug(r, L)}/'>{e(TOPIC.get((r.get('topics') or [None])[0]) or ITEMS.get(r.get('code'), '8-K'))}</a>", e((r.get('headline') or r.get('quote') or '')[:140])]
        for r in rows[:50]])
    body += "<p><a href='../../events/'>Every material 8-K event, by kind →</a></p>"
    return ('8-k-events', 'events', '8-K events: deals, debt, leadership changes and other material news', '8-K events', lead, body)


# --------------------------------------------------------------------------------------------------- writing
def write(site, base, store=None, today=None):
    base = base.rstrip('/')
    today = (today or dt.date.today()).isoformat()
    hub = os.path.join(site, 'disclosures', 'data')
    L = Links(site)
    evs = archive(site, store)
    made = []
    for fn in (signals, smart, insiders, congress, stakes, form144, lambda h, l: events_view(h, l, evs), shorts, rotation, options, guidance, cross, investors):
        try:
            r = fn(hub, L)
        except Exception as err:  # noqa: BLE001
            print(f'hub page skipped: {err}')
            r = None
        if r:
            made.append(r)
    urls = []
    for slug, tab, title, h1, lead, body in made:
        url = f'{base}/disclosures/{slug}/'
        nav = "<nav class='seo-toc'>" + ''.join(f"<a href='../{s}/'{' aria-current=page' if s == slug else ''}>{e(h.split(':')[0])}</a>" for s, _, _, h, *_ in made) + '</nav>'
        html = (f"<p class='crumbs'><a href='../../'>Filing Flows</a> › <a href='../'>Disclosures</a> › {e(h1.split(':')[0])}</p><h1>{e(h1)}</h1>"
                f"<p class='muted'>Snapshot of {e(fdate(today))} · <a href='../#{e(tab)}'>open the live, interactive view →</a></p>{nav}"
                f"<p class='lead'>{lead}</p>{seo._signs(body)}<p><a class='seo-cta' href='../#{e(tab)}'>Filter, sort and chart it live in Disclosures →</a></p>{DISCLAIMER}")
        ld = {'@context': 'https://schema.org', '@graph': [
            {'@type': 'BreadcrumbList', 'itemListElement': [{'@type': 'ListItem', 'position': 1, 'name': 'Filing Flows', 'item': base + '/'},
                                                             {'@type': 'ListItem', 'position': 2, 'name': 'Disclosures', 'item': base + '/disclosures/'},
                                                             {'@type': 'ListItem', 'position': 3, 'name': h1, 'item': url}]},
            {'@type': 'Dataset', 'name': title, 'description': re.sub('<[^>]+>', '', lead)[:500], 'url': url, 'dateModified': today,
             'creator': {'@type': 'Organization', 'name': 'Filing Flows', 'url': base + '/'}, 'isAccessibleForFree': True,
             'license': 'https://www.sec.gov/privacy#dissemination'}]}
        d = os.path.join(site, 'disclosures', slug)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(seo.page(f"{title} | Filing Flows", re.sub('<[^>]+>', '', lead)[:300], url, html, 2, base + '/og.png', ld))
        urls.append((url, today))
    _link_hub(site, made)
    urls += event_pages(site, base, L, evs)
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f'<url><loc>{xesc(u)}</loc>' + (f'<lastmod>{xesc(m)}</lastmod>' if m else '') + '</url>' for u, m in urls]
    sm.append('</urlset>')
    open(os.path.join(site, 'sitemap-hub.xml'), 'w', encoding='utf-8').write('\n'.join(sm))
    robots = os.path.join(site, 'robots.txt')
    txt = open(robots).read() if os.path.exists(robots) else f'User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n'
    if 'sitemap-hub.xml' not in txt:
        open(robots, 'w').write(txt.rstrip('\n') + f'\nSitemap: {base}/sitemap-hub.xml\n')
    return [m[0] for m in made], len(evs)


def _link_hub(site, made):
    """plain links from the hub's own page to each snapshot, so crawlers find them from disclosures/"""
    p = os.path.join(site, 'disclosures', 'index.html')
    if not made or not os.path.exists(p):
        return
    t = open(p, encoding='utf-8').read()
    t = re.sub(r'<nav class="hub-pages".*?</nav>', '', t, flags=re.S)
    nav = ('<nav class="hub-pages" aria-label="Pages" style="max-width:1200px;margin:24px auto;padding:0 16px;font-size:13px;line-height:1.9">Pages: '
           + ' · '.join(f'<a href="{s}/">{e(h.split(":")[0])}</a>' for s, _, _, h, *_ in made) + ' · <a href="../events/">8-K events</a></nav>')
    t = t.replace('</body>', nav + '</body>', 1) if '</body>' in t else t + nav
    open(p, 'w', encoding='utf-8').write(t)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', default='_site')
    ap.add_argument('--store', default='')
    ap.add_argument('--site-url', default=os.environ.get('SITE_URL', '') or 'https://filing-flows.com')
    a = ap.parse_args()
    m = re.search(r'https?://[^\s"]+', a.site_url or '')
    pages, n = write(a.site, m.group(0) if m else 'https://filing-flows.com', a.store or None)
    print(f"hub pages: {', '.join(pages)}; {n} event pages")
