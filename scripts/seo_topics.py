"""Search-engine pages per company and topic, from the Disclosure Hub's published data: each answers one question people
search for, with the answer in the first sentence, the figures behind it, a short FAQ (FAQPage structured data) and
links to the company's other pages and to the interactive view.

    c/<slug>/stock-forecast/   "NVIDIA (NVDA) stock forecast and fair value": analysts' price targets and ratings, the
                               fair-value range of every method (DCF, Monte Carlo, peers), the earnings beat rate
    c/<slug>/who-owns/         "Who owns NVIDIA (NVDA) stock?": the largest 13F holders and their latest changes,
                               funds buying and selling, Congress and insider trades, short interest
    c/<slug>/guidance/         "NVIDIA (NVDA) guidance and outlook": the latest guidance (raised, lowered …), its record
                               against what was reported, the forward-looking statements of the latest 10-Q / 10-K
    c/<slug>/takeover/         "Is NVIDIA (NVDA) a takeover target?": the LBO price, the historical odds, rumors, deals
    c/<slug>/risks/            "NVIDIA (NVDA) recalls, complaints and regulation": recalls, CFPB complaints, EPA
                               enforcement, the Federal Register, clinical trials, attention
    sitemap-topics.xml (listed in robots.txt); a "More on NVDA" block added to each company's c/<slug>/ page.

Runs after the Disclosure Hub is staged (scan.yml); a page is written only when its data says something:
    python scripts/seo_topics.py --site _site --site-url https://filing-flows.com
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

e, display_name, slug_for, fdate = seo.e, seo.display_name, seo.slug_for, seo.fdate


def money(v):
    return '—' if v is None else (('−' if v < 0 else '') + f'${abs(v) / 1e12:.2f}T') if abs(v) >= 1e12 else seo.money(v)
TOPICS = [('revenue', 'How it makes money', ''), ('earnings-date', 'Next earnings date', 'eps'),
          ('stock-forecast', 'Stock forecast & fair value', 'x-fairvalue'), ('who-owns', 'Who owns the stock', 'holders'),
          ('guidance', 'Guidance & outlook', 'x-outlook'), ('takeover', 'Takeover & LBO', 'x-lbo'), ('risks', 'Recalls, complaints & regulation', 'x-outside')]
LINK = {'revenue': lambda n: f'How {n} makes money: revenue by segment', 'earnings-date': lambda n: f'{n} next earnings date and what analysts expect',
        'stock-forecast': lambda n: f'{n} stock forecast, price target and fair value', 'who-owns': lambda n: f'Who owns {n} stock: holders, funds and Congress trades',
        'guidance': lambda n: f'{n} guidance and outlook', 'takeover': lambda n: f'Is {n} a takeover target? LBO and rumors',
        'risks': lambda n: f'{n} recalls, complaints and regulation'}
GUIDE = {'raised': 'raised', 'lowered': 'lowered', 'narrowed': 'narrowed', 'widened': 'widened', 'reaffirmed': 'reaffirmed', 'initiated': 'initiated',
         'withdrawn': 'withdrew', 'mixed': 'raised some and lowered other parts of', 'updated': 'updated'}


def read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def usd(v, d=2):
    return '—' if v is None else f'${v:,.{d}f}'


def pc(v, d=0, signed=True):
    return '—' if v is None else (f'{v:+.{d}f}%' if signed else f'{v:.{d}f}%')


def faq_html(qa):
    return '<h2>Questions</h2>' + ''.join(f'<h3>{e(q)}</h3><p>{e(a)}</p>' for q, a in qa) if qa else ''


def ld_for(name, ticker, url, crumbs, qa, modified):
    g = [{'@type': 'BreadcrumbList', 'itemListElement': [{'@type': 'ListItem', 'position': i + 1, 'name': n, 'item': u} for i, (n, u) in enumerate(crumbs)]},
         {'@type': 'WebPage', 'name': crumbs[-1][0], 'url': url, 'dateModified': modified, 'about': {'@type': 'Corporation', 'name': name, 'tickerSymbol': ticker or None}}]
    if qa:
        g.append({'@type': 'FAQPage', 'mainEntity': [{'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}} for q, a in qa]})
    return {'@context': 'https://schema.org', '@graph': g}


def nav(slug, here, have, cik):
    links = [f"<a href='../'>Earnings Sankey</a>"] + [
        (f"<b>{e(label)}</b>" if t == here else f"<a href='../{t}/'>{e(label)}</a>") for t, label, _ in TOPICS if t in have]
    return f"<nav class='seo-more'>{' · '.join(links)}</nav>"


# ---------------------------------------------------------------- the topics
def forecast(co, v, cons):
    if not v and not cons:
        return None
    name, t = co['who_name'], co['ticker']
    price = (v or {}).get('price') or ((cons or {}).get('analysts') or {}).get('price')
    an = (cons or {}).get('analysts') or {}
    tg = an.get('targets') or {}
    rating = (an.get('rating') or {}).get('key')
    fb = [x for x in (v or {}).get('football') or [] if x.get('point') is not None]
    dcf = ((v or {}).get('dcf') or {}).get('value')
    pts = sorted(x['point'] for x in fb)
    mid = pts[len(pts) // 2] if pts else None
    if price is None or (not tg.get('median') and mid is None):
        return None
    up = lambda x: (x / price - 1) * 100 if x and price else None   # noqa: E731
    lead = f"{name} ({t}) trades at {usd(price)}."
    if tg.get('median'):
        lead += f" {tg.get('n') or 'The'} analysts' median price target is {usd(tg['median'])} ({pc(up(tg['median']))}), from {usd(tg.get('low'))} to {usd(tg.get('high'))}."
    if mid is not None:
        lead += f" Across {len(pts)} valuation methods the middle fair value is {usd(mid)} ({pc(up(mid))})" + (f"; the DCF says {usd(dcf)}." if dcf else '.')
    rows = ''.join(f"<tr><td>{e(x.get('method'))}</td><td class='num'>{usd(x.get('low'))}</td><td class='num'>{usd(x.get('point'))}</td><td class='num'>{usd(x.get('high'))}</td>"
                   f"<td class='num'>{pc(up(x.get('point')))}</td></tr>" for x in fb[:10])
    beat = (cons or {}).get('beat_rate')
    qa = []
    if tg.get('median'):
        qa.append((f"What is the price target for {t} stock?", f"The median of {tg.get('n') or 'the'} analysts' 12-month targets is {usd(tg['median'])}, "
                   f"{pc(up(tg['median']))} from {usd(price)}; the range is {usd(tg.get('low'))} to {usd(tg.get('high'))}." +
                   (f" The average rating is {rating.replace('_', ' ')}." if rating else '')))
    if mid is not None:
        qa.append((f"What is {name}'s fair value?", f"The fair-value methods on Filing Flows (DCF, Monte Carlo, peer multiples and others) put it between "
                   f"{usd(pts[0])} and {usd(pts[-1])}, with a middle value of {usd(mid)} against a price of {usd(price)}. Each method's assumptions are on the page."))
    if beat is not None:
        qa.append((f"Does {name} usually beat earnings estimates?", f"It beat the consensus EPS estimate in {round(100 * beat)}% of the quarters on record."))
    qa.append((f"Is {t} stock a buy?", "Filing Flows does not give advice. It shows what analysts expect, what each valuation method implies and the "
               "figures behind them, read from SEC filings, so you can judge for yourself."))
    body = (f"<p class='lead'>{e(lead)}</p>"
            + (f"<div class='seo-tiles'><div class='seo-tile'><span>Price</span><b>{usd(price)}</b></div>"
               + (f"<div class='seo-tile'><span>Median target</span><b>{usd(tg.get('median'))}</b></div>" if tg.get('median') else '')
               + (f"<div class='seo-tile'><span>Fair value, middle</span><b>{usd(mid)}</b></div>" if mid is not None else '')
               + (f"<div class='seo-tile'><span>DCF</span><b>{usd(dcf)}</b></div>" if dcf else '')
               + (f"<div class='seo-tile'><span>EPS beat rate</span><b>{round(100 * beat)}%</b></div>" if beat is not None else '') + "</div>")
            + (f"<h2>Fair value by method</h2><div class='tbl-wrap'><table><thead><tr><th>Method</th><th class='num'>Low</th><th class='num'>Point</th>"
               f"<th class='num'>High</th><th class='num'>vs price</th></tr></thead><tbody>{rows}</tbody></table></div>" if rows else ''))
    return {'title': f"{name} ({t}) stock forecast, price target and fair value", 'h1': f"{name} ({t}) stock forecast and fair value",
            'desc': lead[:300], 'body': body, 'qa': qa}


def owners(co, h):
    if not h or not (h.get('institutional') or h.get('officials')):
        return None
    name, t = co['who_name'], co['ticker']
    inst = sorted(h.get('institutional') or [], key=lambda r: -(r.get('value_usd') or 0))
    top = inst[:15]
    total = sum(r.get('value_usd') or 0 for r in inst)
    off = h.get('officials') or []
    buys = [r for r in off if 'purchase' in str(r.get('transaction_type', '')).lower()]
    sells = [r for r in off if 'sale' in str(r.get('transaction_type', '')).lower()]
    short = (h.get('short') or [None])[-1] if isinstance(h.get('short'), list) and h.get('short') else None
    q = h.get('q13f') or {}
    qr = (q.get('rows') or [])
    qlast = dict(zip(q.get('fields') or [], qr[-2])) if len(qr) >= 2 else {}
    lead = f"{len(inst):,} funds reported {name} ({t}) shares in their latest 13F filings" + (f", worth {money(total)} in all" if total else '') + '.'
    if top:
        lead += f" The largest holder is {display_name(top[0].get('manager'))} ({money(top[0].get('value_usd'))})."
    if qlast.get('buyers') is not None:
        lead += f" Last quarter {qlast.get('buyers')} funds added to their stakes and {qlast.get('sellers')} cut them."
    if off:
        lead += f" Members of Congress and other officials disclosed {len(off)} trades ({len(buys)} buys, {len(sells)} sales)."
    shares = lambda r: f"{(r.get('shares') or 0):,.0f}"   # noqa: E731
    rows = ''.join(f"<tr><td>{e(display_name(r.get('manager')))}</td><td class='num'>{e(shares(r))}</td>"
                   f"<td class='num'>{e(money(r.get('value_usd')))}</td><td>{e((r.get('status') or '').lower())}</td><td>{e(r.get('period'))}</td></tr>" for r in top)
    orow = ''.join(f"<tr><td>{e(r.get('date'))}</td><td>{e(r.get('person'))}</td><td>{e(r.get('transaction_type'))}</td>"
                   f"<td class='num'>{e(money(r.get('amount_min')))}–{e(money(r.get('amount_max')))}</td></tr>" for r in sorted(off, key=lambda r: r.get('date') or '', reverse=True)[:10])
    qa = [(f"Who owns the most {t} stock?", f"By the latest 13F filings: " + '; '.join(f"{display_name(r.get('manager'))} ({money(r.get('value_usd'))})" for r in top[:5]) + '.')] if top else []
    if off:
        last = max(off, key=lambda r: r.get('date') or '')
        qa.append((f"Has Congress traded {t} stock?", f"Officials disclosed {len(off)} trades on file: {len(buys)} buys and {len(sells)} sales. The latest: "
                   f"{last.get('person')}, {last.get('transaction_type')} on {last.get('date')}."))
    if short and len(short) >= 3:
        qa.append((f"What is the short interest in {t}?", f"{short[1]:,.0f} shares were sold short at the {short[0]} settlement, {short[2]}% of the float."))
    body = (f"<p class='lead'>{e(lead)}</p>"
            + (f"<h2>Largest holders (13F)</h2><div class='tbl-wrap'><table><thead><tr><th>Fund</th><th class='num'>Shares</th><th class='num'>Value</th>"
               f"<th>Change</th><th>Quarter</th></tr></thead><tbody>{rows}</tbody></table></div>" if rows else '')
            + (f"<h2>Trades by Congress and other officials</h2><div class='tbl-wrap'><table><thead><tr><th>Date</th><th>Who</th><th>Trade</th><th class='num'>Amount</th></tr></thead><tbody>{orow}</tbody></table></div>" if orow else ''))
    return {'title': f"Who owns {name} ({t}) stock? Top holders, fund buying and Congress trades", 'h1': f"Who owns {name} ({t}) stock",
            'desc': lead[:300], 'body': body, 'qa': qa}


def guidance(co, h, ol):
    g = (h or {}).get('guidance') or {}
    docs = (ol or {}).get('docs') or []
    md = next((d for d in docs if d.get('kind') == 'mdna'), None)
    if not g.get('items') and not md:
        return None
    name, t = co['who_name'], co['ticker']
    lead, qa = '', []
    if g.get('items'):
        word = GUIDE.get(g.get('label'), 'gave')
        its = [i for i in g['items'] if i.get('lo') is not None and not i.get('scope')][:4]
        rng = lambda i: (f"{i['lo']:,.2f}–{i['hi']:,.2f}" if i.get('unit') == 'ps' else f"{money(i['lo'])}–{money(i['hi'])}" if i.get('unit') == 'usd'   # noqa: E731
                         else f"{i['lo']:g}–{i['hi']:g}%")
        lead = f"{name} ({t}) {word} its guidance on {fdate(g.get('filed'))}: " + '; '.join(
            f"{i.get('name') or i.get('metric')} {('$' if i.get('unit') == 'ps' else '')}{rng(i)} for {i.get('period')}" for i in its) + '.'
        qa.append((f"Did {name} raise or lower its guidance?", lead))
    if md:
        c = md.get('counts') or {}
        lead += (f" {name}'s {md.get('form')} filed {fdate(md.get('filed'))} makes {c.get('n', 0)} forward-looking statements"
                 + (f", {c.get('new', 0)} of them new and {c.get('dropped', 0)} no longer said since the filing before" if md.get('vs') else '') + '.')
        new = [s for s in md.get('statements') or [] if s.get('status') in ('new', 'updated')][:3] or (md.get('statements') or [])[:3]
        if new:
            qa.append((f"What does {name} expect?", ' '.join(s['t'] for s in new)[:600]))
    stm = ''.join(f"<li>{('<b>' + e(s.get('status')) + '</b> · ') if s.get('status') in ('new', 'updated') else ''}{e(s['t'])}</li>"
                  for s in (md or {}).get('statements', [])[:12])
    items = ''.join(f"<tr><td>{e(i.get('name') or i.get('metric'))}</td><td>{e(i.get('period'))}</td><td class='num'>{e(i.get('lo'))}–{e(i.get('hi'))} {e(i.get('unit'))}</td>"
                    f"<td>{e(i.get('change') or '')}</td></tr>" for i in (g.get('items') or [])[:12] if i.get('lo') is not None)
    body = (f"<p class='lead'>{e(lead.strip())}</p>"
            + (f"<h2>Latest guidance</h2><div class='tbl-wrap'><table><thead><tr><th>Metric</th><th>Period</th><th class='num'>Range</th><th>Change</th></tr></thead><tbody>{items}</tbody></table></div>"
               + (f"<p class='muted'>From the earnings release filed {e(fdate(g.get('filed')))} (<a href='{e(g.get('url'))}' rel='nofollow'>8-K on EDGAR</a>).</p>" if g.get('url') else '') if items else '')
            + (f"<h2>Forward-looking statements, {e(md.get('form'))} filed {e(fdate(md.get('filed')))}</h2><ul class='seo-list'>{stm}</ul>" if stm else ''))
    return {'title': f"{name} ({t}) guidance and outlook: what the company expects", 'h1': f"{name} ({t}) guidance and outlook",
            'desc': lead.strip()[:300], 'body': body, 'qa': qa, 'modified': max(filter(None, [g.get('filed'), (md or {}).get('filed')]), default=None)}


def takeover(co, lbo, board_row):
    if not lbo or not (lbo.get('inputs') or lbo.get('rumors')):
        return None
    name, t = co['who_name'], co['ticker']
    hs = ((lbo.get('history') or {}).get('acquired')) or {}
    rum = lbo.get('rumors') or []
    br = board_row or {}
    if not rum and not br.get('irr') and not hs:
        return None
    lead = f"Is {name} ({t}) a takeover target?"
    parts = []
    if br.get('irr') is not None:
        parts.append(f"A leveraged buyout at today's price plus 30% would return about {br['irr'] * 100:.0f}% a year to a private-equity buyer"
                     + (f"; the most a buyer could pay for a 20% return is {usd(br.get('max_price'))} a share" if br.get('max_price') else '') + '.')
    if hs.get('p') is not None:
        parts.append(f"Historically {hs['p'] * 100:.1f}% of companies with its figures were bought within a year ({hs.get('lift') or '—'}× the average).")
    if rum:
        parts.append(f"Latest signal ({rum[0].get('date')}): {rum[0].get('text')}.")
    desc = ' '.join(parts)
    rl = ''.join(f"<li>{e(x.get('date'))} · {e(x.get('kind'))} · {e(x.get('text'))}</li>" for x in rum[:10])
    qa = [(f"Is {name} being acquired?", (f"The latest signal on file is from {rum[0].get('date')}: {rum[0].get('text')}. A headline is not a deal; "
                                          "Filing Flows lists the news, 8-K filings and 13D filings about a sale.") if rum else
           "No headline, 8-K or 13D about a sale is on file in the last year.")]
    if br.get('irr') is not None:
        qa.append((f"Could private equity buy {name}?", parts[0]))
    body = f"<p class='lead'>{e(desc)}</p>" + (f"<h2>Rumors and deal signals</h2><ul class='seo-list'>{rl}</ul>" if rl else '')
    return {'title': f"{name} ({t}) takeover and buyout analysis: LBO price, odds and rumors", 'h1': lead, 'desc': desc[:300], 'body': body, 'qa': qa}


def risks(co, out):
    if not out:
        return None
    name, t = co['who_name'], co['ticker']
    r, cp, en, fr, tr = (out.get(k) or {} for k in ('recalls', 'complaints', 'environment', 'fedreg', 'trials'))
    parts, qa, body = [], [], ''
    if r.get('n'):
        parts.append(f"{r.get('last_12m', 0)} recalls in the last 12 months ({r.get('n')} in five years, {r.get('class1', 0)} Class I)")
        qa.append((f"Has {name} had any recalls?", f"{r.get('n')} recalls on file over five years from the FDA, CPSC and NHTSA; {r.get('last_12m', 0)} in the last 12 months."))
        body += '<h2>Latest recalls</h2><ul class="seo-list">' + ''.join(f"<li>{e(x.get('date'))} · {e(x.get('source'))} · {e(x.get('what'))}</li>" for x in (r.get('latest') or [])[:8]) + '</ul>'
    if cp.get('last_12m'):
        parts.append(f"{cp['last_12m']:,} consumer complaints to the CFPB in 12 months" + (f" ({cp['change'] * 100:+.0f}%)" if cp.get('change') is not None else ''))
        qa.append((f"How many complaints does {name} get?", f"{cp['last_12m']:,} complaints to the Consumer Financial Protection Bureau in the last 12 months"
                   + (f", {cp['change'] * 100:+.0f}% on the year before" if cp.get('change') is not None else '') + '.'))
    if en.get('facilities'):
        parts.append(f"{en.get('in_violation', 0)} EPA-regulated facilities in violation, {money(en.get('penalties_5y'))} in penalties over five years")
        qa.append((f"Has {name} been fined by the EPA?", f"Its {en['facilities']:,} EPA-regulated facilities drew {money(en.get('penalties_5y'))} in penalties over five years; "
                   f"{en.get('in_violation', 0)} are in violation now."))
    if fr.get('count'):
        parts.append(f"{fr['count']} Federal Register documents in a year")
    if tr.get('active'):
        parts.append(f"{tr['active']} active clinical trials")
        qa.append((f"How many clinical trials does {name} have?", f"{tr['active']} active studies on ClinicalTrials.gov, {((tr.get('phases') or {}).get('PHASE3') or {}).get('active', 0)} in phase 3."))
    if not parts:
        return None
    desc = f"{name} ({t}) beyond its filings: " + '; '.join(parts) + '.'
    return {'title': f"{name} ({t}) recalls, complaints, EPA and regulation", 'h1': f"{name} ({t}): recalls, complaints and regulation",
            'desc': desc[:300], 'body': f"<p class='lead'>{e(desc)}</p>" + body, 'qa': qa}


# ---------------------------------------------------------------- revenue and earnings date
def _flows(q):
    """(labels, inflow per node {id: [v, q, y]}, children {id: [ids]}) of a Sankey spec."""
    import html as H
    lab = {n['id']: H.unescape(n.get('label') or n.get('name') or n['id']) for n in q.get('nodes') or []}
    into, kids = {}, {}
    for ln in q.get('links') or []:
        a = into.setdefault(ln['t'], [0.0, 0.0, 0.0])
        for i, k in enumerate(('v', 'q', 'y')):
            a[i] += ln.get(k) or 0
        kids.setdefault(ln['t'], []).append(ln['s'])
    return lab, into, kids


def _from(links, node, target):
    v = [0.0, 0.0, 0.0]
    for ln in links:
        if ln['s'] == node and ln['t'] == target:
            for i, k in enumerate(('v', 'q', 'y')):
                v[i] += ln.get(k) or 0
    return v


def revenue(co, c):
    qs = (c or {}).get('quarters') or []
    if not qs or not qs[0].get('links'):
        return None
    q = qs[0]
    name, t = co['who_name'], co['ticker']
    lab, into, kids = _flows(q)
    links = q['links']
    rev = into.get('revenue')
    if not rev:
        out = [0.0, 0.0, 0.0]
        for ln in links:
            if ln['s'] == 'revenue':
                for i, k in enumerate(('v', 'q', 'y')):
                    out[i] += ln.get(k) or 0
        rev = out
    if not rev or not rev[0] or rev[0] <= 0:
        return None
    words = seo.period_words(q.get('label'))
    chg = lambda a, b: (a / b - 1) * 100 if a and b else None    # noqa: E731
    segs = []
    for s_ in dict.fromkeys(kids.get('revenue', [])):
        sub = [(lab.get(k, k), _from(links, k, s_)) for k in dict.fromkeys(kids.get(s_, []))]
        segs.append((lab.get(s_, s_), _from(links, s_, 'revenue'), sorted(sub, key=lambda x: -x[1][0])))
    segs.sort(key=lambda x: -x[1][0])
    tot = rev[0]
    val = lambda nid: (into.get(nid) or [None])[0]               # noqa: E731
    gp, oi, net = val('gp'), val('oi'), val('net')
    g = chg(rev[0], rev[2])
    lead = f"{name} ({t}) made {money(tot)} of revenue in the {words} ({q.get('label')})" + (f", {g:+.0f}% from a year earlier" if g is not None else '') + '.'
    if len(segs) > 1:
        lead += ' ' + '; '.join(f"{n_} brought in {money(v[0])} ({100 * v[0] / tot:.0f}%)" for n_, v, _ in segs[:3]) + '.'
    cents = [(k, x) for k, x in (('gross profit', gp), ('operating profit', oi), ('net earnings', net)) if x is not None]
    if cents:
        lead += ' Of every dollar of revenue, ' + ', '.join(f"{100 * x / tot:.0f}¢ was left as {k}" for k, x in cents) + '.'
    rows = ''
    for n_, v, sub in segs:
        rows += (f"<tr><td><b>{e(n_)}</b></td><td class='num'>{e(money(v[0]))}</td><td class='num'>{100 * v[0] / tot:.1f}%</td>"
                 f"<td class='num'>{e(pc(chg(v[0], v[1])))}</td><td class='num'>{e(pc(chg(v[0], v[2])))}</td></tr>")
        for sn, sv in sub[:8]:
            rows += (f"<tr><td>&nbsp;&nbsp;↳ {e(sn)}</td><td class='num'>{e(money(sv[0]))}</td><td class='num'>{100 * sv[0] / tot:.1f}%</td>"
                     f"<td class='num'>{e(pc(chg(sv[0], sv[1])))}</td><td class='num'>{e(pc(chg(sv[0], sv[2])))}</td></tr>")
    ladder = [('Revenue', tot), ('Cost of revenue', val('cor')), ('Gross profit', gp), ('Operating expenses', val('opex')), ('Operating profit', oi),
              ('Income tax', val('tax')), ('Net earnings', net), ('Operating cash flow', val('ocf')), ('Free cash flow', val('fcf'))]
    lad = ''.join(f"<tr><td>{e(k)}</td><td class='num'>{e(money(x))}</td><td class='num'>{100 * x / tot:.1f}%</td></tr>" for k, x in ladder if x is not None)
    hist = ''.join(f"<tr><td>{e(x.get('label'))}</td><td class='num'>{e((x.get('headline') or {}).get('rev_fmt') or money((x.get('headline') or {}).get('revenue')))}</td>"
                   f"<td class='num'>{e(pc((x.get('headline') or {}).get('yoy')))}</td></tr>" for x in qs[:8])
    qa = [(f"How does {name} make money?", lead)]
    if len(segs) > 1:
        s0 = segs[0]
        g0 = chg(s0[1][0], s0[1][2])
        qa.append((f"What is {name}'s biggest business?", f"{s0[0]}: {money(s0[1][0])} in the {words}, {100 * s0[1][0] / tot:.0f}% of revenue"
                   + (f", {g0:+.0f}% from a year earlier" if g0 is not None else '') + '.'))
    if net is not None:
        qa.append((f"What is {name}'s profit margin?", f"Net earnings were {money(net)}, {100 * net / tot:.1f}% of revenue, in the {words}"
                   + (f"; the operating margin was {100 * oi / tot:.1f}%." if oi is not None else '.')))
    body = (f"<p class='lead'>{e(lead)}</p>"
            + (f"<h2>Revenue by segment, {e(q.get('label'))}</h2><div class='tbl-wrap'><table><thead><tr><th>Segment</th><th class='num'>Revenue</th><th class='num'>Share</th>"
               f"<th class='num'>Q/Q</th><th class='num'>Y/Y</th></tr></thead><tbody>{rows}</tbody></table></div>" if len(segs) > 1 else '')
            + f"<h2>Where each dollar of revenue goes</h2><div class='tbl-wrap'><table><thead><tr><th>Line</th><th class='num'>{e(q.get('label'))}</th><th class='num'>% of revenue</th></tr></thead><tbody>{lad}</tbody></table></div>"
            + f"<h2>Revenue, quarter by quarter</h2><div class='tbl-wrap'><table><thead><tr><th>Quarter</th><th class='num'>Revenue</th><th class='num'>Y/Y</th></tr></thead><tbody>{hist}</tbody></table></div>"
            + f"<p class='muted'>From {e(name)}'s {e(q.get('form'))} filed {e(fdate(q.get('filed')))}" + (f" (<a href='{e(q.get('doc_url'))}' rel='nofollow'>on EDGAR</a>)" if q.get('doc_url') else '') + '.</p>')
    return {'title': f"How {name} ({t}) makes money: revenue by segment, {q.get('label')}", 'h1': f"How {name} ({t}) makes money",
            'desc': lead[:300], 'body': body, 'qa': qa, 'modified': (q.get('filed') or '')[:10] or None}


def earnings_date(co, er, c, cons):
    if not er or not er.get('report_date'):
        return None
    name, t = co['who_name'], co['ticker']
    cs = er.get('consensus') or {}
    d = er['report_date']
    try:
        days = (dt.date.fromisoformat(d) - dt.date.today()).days
    except ValueError:
        return None
    when = fdate(d) + (' (estimated)' if er.get('date_estimated') else '')
    q = ((c or {}).get('quarters') or [{}])[0]
    h = q.get('headline') or {}
    if days >= 0:
        lead = (f"{name} ({t}) is expected to report earnings on {when}" + (f", in {days} days" if days else ', today')
                + (f", for the quarter ending {fdate(er.get('quarter'))}" if er.get('quarter') else '') + '.')
        if cs.get('eps') is not None:
            lead += (f" Analysts expect EPS of ${cs['eps']:.2f}"
                     + (f" (${cs['eps_low']:.2f} to ${cs['eps_high']:.2f}, {cs['n']:.0f} estimates)" if cs.get('eps_low') is not None and cs.get('n') else '')
                     + (f" on revenue of {money(cs['rev'])}" if cs.get('rev') else '')
                     + ((f", against ${cs['year_ago_eps']:.2f}" + (f" and {money(cs['year_ago_rev'])}" if cs.get('year_ago_rev') else '') + ' a year ago')
                        if cs.get('year_ago_eps') is not None else '') + '.')
    else:
        lead = (f"{name} ({t}) last reported on {fdate(d)}"
                + (f": revenue {h.get('rev_fmt') or money(h.get('revenue'))} for the {seo.period_words(q.get('label'))}" if h.get('revenue') else '')
                + '. The next date is not set yet.')
    beat = (cons or {}).get('beat_rate')
    p = (er.get('model') or {}).get('p')
    if beat is not None:
        lead += f" It beat the EPS estimate in {round(100 * beat)}% of the quarters on record"
        lead += f"; Filing Flows' model gives it a {round(100 * p)}% chance of beating this time." if p is not None and days >= 0 else '.'
    qa = [(f"When does {t} report earnings?", lead.split('. ')[0].rstrip('.') + '.')]
    if cs.get('eps') is not None and days >= 0:
        qa.append((f"What are analysts expecting from {name}?", f"EPS of ${cs['eps']:.2f}" + (f" and revenue of {money(cs['rev'])}" if cs.get('rev') else '') + ' for the quarter.'))
    if beat is not None:
        qa.append((f"Does {name} usually beat earnings?", f"It beat the consensus EPS estimate in {round(100 * beat)}% of the quarters on record."))
    tiles = ''.join(f"<div class='seo-tile'><span>{e(k)}</span><b>{e(v)}</b></div>" for k, v in (
        ('Report date', when), ('Days to go', str(days) if days >= 0 else '—'), ('EPS estimate', f"${cs['eps']:.2f}" if cs.get('eps') is not None and days >= 0 else '—'),
        ('Revenue estimate', money(cs.get('rev')) if cs.get('rev') and days >= 0 else '—'), ('Beat rate', f"{round(100 * beat)}%" if beat is not None else '—')))
    last = (f"<h2>The last report</h2><p>{e(name)} reported revenue of {e(h.get('rev_fmt') or money(h.get('revenue')))} for the {e(seo.period_words(q.get('label')))}"
            + (f" ({e(pc(h.get('yoy')))} Y/Y)" if h.get('yoy') is not None else '') + (f", net earnings {e(h.get('ni_fmt') or money(h.get('ni')))}" if h.get('ni') is not None else '')
            + ". <a href='../revenue/'>How it makes money →</a></p>") if h.get('revenue') else ''
    body = f"<p class='lead'>{e(lead)}</p><div class='seo-tiles'>{tiles}</div>{last}"
    return {'title': f"{name} ({t}) earnings date {d[:4]}: next report {fdate(d)}, EPS estimate", 'h1': f"{name} ({t}) next earnings date",
            'desc': lead[:300], 'body': body, 'qa': qa}


# ---------------------------------------------------------------- write
def write(site, base, limit=None):
    base = base.rstrip('/')
    ix = read(os.path.join(site, 'data', 'index.json')) or {}
    rows = ix.get('companies') if isinstance(ix, dict) else ix
    latest = {}
    for r in rows or []:
        if r['cik'] not in latest or (r.get('filed') or '') > (latest[r['cik']].get('filed') or ''):
            latest[r['cik']] = r
    hub = os.path.join(site, 'disclosures', 'data')
    board = read(os.path.join(hub, 'research', 'lbo', 'board.json')) or {}
    bF = board.get('fields') or []
    brow = {r[bF.index('cik')]: dict(zip(bF, r)) for r in board.get('rows') or []} if bF else {}
    today = dt.date.today().isoformat()
    d0 = dt.date.today()
    week = (d0 - dt.timedelta(days=d0.weekday())).isoformat()      # most topics change daily in small ways: dated by the week
    urls, counts = [], {t: 0 for t, _, _ in TOPICS}
    order = sorted(latest.values(), key=lambda r: -(r.get('revenue') or 0))[:limit]
    for r in order:
        cik, slug, t = r['cik'], slug_for(r), (r.get('ticker') or '')
        if not t:
            continue
        co = {'who_name': display_name(r.get('name')), 'ticker': t}
        h = read(os.path.join(hub, 'holders', f'{t}.json'))
        cdoc = read(os.path.join(site, 'data', 'c', f'{cik}.json'))
        pages = {
            'revenue': revenue(co, cdoc),
            'earnings-date': earnings_date(co, read(os.path.join(hub, 'research', 'earnings', 'c', f'{t}.json')), cdoc, read(os.path.join(hub, 'consensus', 'c', f'{cik}.json'))),
            'stock-forecast': forecast(co, read(os.path.join(hub, 'research', 'valuation', 'c', f'{cik}.json')), read(os.path.join(hub, 'consensus', 'c', f'{cik}.json'))),
            'who-owns': owners(co, h),
            'guidance': guidance(co, h, read(os.path.join(site, 'data', 'outlook', f'{cik}.json'))),
            'takeover': takeover(co, read(os.path.join(hub, 'research', 'lbo', 'c', f'{cik}.json')), brow.get(cik)),
            'risks': risks(co, read(os.path.join(hub, 'research', 'outside', 'c', f'{cik}.json'))),
        }
        have = [k for k, v in pages.items() if v]
        if not have:
            continue
        for topic, p in pages.items():
            if not p:
                continue
            url = f'{base}/c/{slug}/{topic}/'
            app = next(a for k, _, a in TOPICS if k == topic)
            crumbs = [('Filing Flows', base + '/'), (f"{co['who_name']} ({t})", f'{base}/c/{slug}/'), (p['h1'], url)]
            body = (f"<p class='crumbs'><a href='../../../'>Filing Flows</a> › <a href='../'>{e(co['who_name'])} ({e(t)})</a> › {e(next(l for k, l, _ in TOPICS if k == topic))}</p>"
                    f"<h1>{e(p['h1'])}</h1>{nav(slug, topic, have, cik)}{p['body']}{faq_html(p['qa'])}"
                    f"<p><a class='seo-cta' href='../../../#c-{cik}{('-' + app) if app else ''}'>Open the interactive view →</a></p>"
                    f"<p class='muted'>Updated {e(fdate(today))}. Read automatically from SEC filings and public data; errors are possible. Not investment advice.</p>")
            mod = p.get('modified') or week
            doc = seo.page(f"{p['title']} | Filing Flows", p['desc'], url, body, 3, base + '/og.png', ld_for(co['who_name'], t, url, crumbs, p['qa'], mod))
            d = os.path.join(site, 'c', slug, topic)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, 'index.html'), 'w', encoding='utf-8') as f:
                f.write(doc)
            urls.append((url, mod))
            counts[topic] += 1
        main = os.path.join(site, 'c', slug, 'index.html')            # the company page links to its topics
        try:
            txt = open(main, encoding='utf-8').read()
            if 'class="seo-more-main"' not in txt and '</main>' in txt:
                block = (f'<section class="seo-more-main"><h2>More on {e(t)}</h2><ul class="seo-list">'
                         + ''.join(f"<li><a href='{k}/'>{e(LINK[k](co['who_name']))}</a></li>" for k, l, _ in TOPICS if k in have) + '</ul></section>')
                open(main, 'w', encoding='utf-8').write(txt.replace('</main>', block + '</main>', 1))
        except OSError:
            pass
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f'<url><loc>{xesc(u)}</loc><lastmod>{m}</lastmod></url>' for u, m in urls]
    sm.append('</urlset>')
    open(os.path.join(site, 'sitemap-topics.xml'), 'w', encoding='utf-8').write('\n'.join(sm))
    robots = os.path.join(site, 'robots.txt')
    txt = open(robots).read() if os.path.exists(robots) else f'User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n'
    if 'sitemap-topics.xml' not in txt:
        open(robots, 'w').write(txt.rstrip('\n') + f'\nSitemap: {base}/sitemap-topics.xml\n')
    return counts


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', default='_site')
    ap.add_argument('--site-url', default=os.environ.get('SITE_URL', '') or 'https://filing-flows.com')
    ap.add_argument('--limit', type=int, default=None)
    a = ap.parse_args()
    base = re.search(r'https?://[^\s"]+', a.site_url or '')
    c = write(a.site, base.group(0) if base else 'https://filing-flows.com')
    print('topic pages: ' + ', '.join(f'{k} {v}' for k, v in c.items()) + f' · {sum(c.values())} in all')
