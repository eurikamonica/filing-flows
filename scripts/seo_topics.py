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
TOPICS = [('stock-forecast', 'Stock forecast & fair value', 'x-fairvalue'), ('who-owns', 'Who owns the stock', 'holders'),
          ('guidance', 'Guidance & outlook', 'x-outlook'), ('takeover', 'Takeover & LBO', 'x-lbo'), ('risks', 'Recalls, complaints & regulation', 'x-outside')]
LINK = {'stock-forecast': lambda n: f'{n} stock forecast, price target and fair value', 'who-owns': lambda n: f'Who owns {n} stock: holders, funds and Congress trades',
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
        pages = {
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
                    f"<p><a class='seo-cta' href='../../../#c-{cik}-{app}'>Open the interactive view →</a></p>"
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
