"""Search-engine pages per company and topic, from the Disclosure Hub's published data: each answers one question people
search for, with the answer in the first sentence, the figures behind it, a short FAQ (FAQPage structured data) and
links to the company's other pages and to the interactive view.

    c/<slug>/stock-forecast/   "NVIDIA (NVDA) stock forecast and fair value": analysts' price targets and ratings, the
                               fair-value range of every method (DCF, Monte Carlo, peers), the earnings beat rate
    c/<slug>/who-owns/         "Who owns NVIDIA (NVDA) stock?": the largest 13F holders and their latest changes,
                               funds buying and selling, Congress and insider trades, short interest
    c/<slug>/guidance/         "NVIDIA (NVDA) guidance and outlook": the latest guidance (raised, lowered …), its record
                               against what was reported, the forward-looking statements of the latest 10-Q / 10-K
    c/<slug>/takeover/         "Is NVIDIA (NVDA) a takeover target?": the LBO worked through step by step (the site's own
                               model, scripts/seo_lbo.py) or why one does not fit, what takeovers on record paid, the
                               historical odds, rumors, deals
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
import seo_svg as SV  # noqa: E402
import seo_charts as SC  # noqa: E402
import seo_lbo  # noqa: E402
from seo_history import sankey_figure  # noqa: E402

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
    return '—' if v is None else f"{'−' if v < 0 else ''}${abs(v):,.{d}f}"


def pc(v, d=0, signed=True):
    if signed and d == 0:
        return seo.pct(v)                                           # a change: +10%, −0.4% (never "-0%")
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
        if tg.get('n') == 1 or (tg.get('low') is not None and usd(tg.get('low')) == usd(tg.get('high'))):    # one target: no median, no range
            who = "One analyst's" if tg.get('n') == 1 else "The analysts'"
            lead += f" {who} price target is {usd(tg['median'])} ({pc(up(tg['median']))})."
        else:
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
        qa.append((f"What is {seo.poss(name)} fair value?", f"The fair-value methods on Filing Flows (DCF, Monte Carlo, peer multiples and others) put it between "
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
            + SV.ranges([(x.get('method'), x.get('low'), x.get('high'), x.get('point')) for x in fb[:10] if x.get('low') is not None],
                        usd, f"{name} fair value by method (price {usd(price)})", legend=('low – high', 'point estimate'))
            + (f"<h2>Fair value by method</h2><div class='tbl-wrap'><table><thead><tr><th>Method</th><th class='num'>Low</th><th class='num'>Point</th>"
               f"<th class='num'>High</th><th class='num'>vs price</th></tr></thead><tbody>{rows}</tbody></table></div>" if rows else ''))
    return {'title': f"{name} ({t}) stock forecast, price target and fair value", 'h1': f"{name} ({t}) stock forecast and fair value",
            'desc': lead[:300], 'body': body, 'qa': qa}


def safe(f, topic, ticker):
    """one page that cannot be built (odd data) is left out, not the run"""
    try:
        return f()
    except Exception as err:  # noqa: BLE001
        print(f'  {ticker} {topic}: skipped ({type(err).__name__}: {err})')
        return None


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
    qlast = dict(zip(q.get('fields') or [], qr[-2])) if len(qr) >= 2 and isinstance(qr[-2], (list, tuple)) else {}
    lead = f"{len(inst):,} funds reported {name} ({t}) shares in their latest 13F filings" + (f", worth {money(total)} in all" if total else '') + '.'
    if top:
        lead += f" The largest holder is {display_name(top[0].get('manager'))} ({money(top[0].get('value_usd'))})."
    if qlast.get('buyers') is not None:
        lead += f" Last quarter {seo.n_of(qlast.get('buyers'), 'fund')} added to their stakes and {qlast.get('sellers')} cut them."
    if off:
        lead += f" Members of Congress and other officials disclosed {seo.n_of(len(off), 'trade')} ({len(buys)} buys, {len(sells)} sales)."
    shares = lambda r: f"{(r.get('shares') or 0):,.0f}"   # noqa: E731
    rows = ''.join(f"<tr><td>{e(display_name(r.get('manager')))}</td><td class='num'>{e(shares(r))}</td>"
                   f"<td class='num'>{e(money(r.get('value_usd')))}</td><td>{e((r.get('status') or '').lower())}</td><td>{e(r.get('period'))}</td></tr>" for r in top)
    orow = ''.join(f"<tr><td>{e(r.get('date'))}</td><td>{e(r.get('person'))}</td><td>{e(r.get('transaction_type'))}</td>"
                   f"<td class='num'>{e(money(r.get('amount_min')))}–{e(money(r.get('amount_max')))}</td></tr>" for r in sorted(off, key=lambda r: r.get('date') or '', reverse=True)[:10])
    qa = [(f"Who owns the most {t} stock?", f"By the latest 13F filings: " + '; '.join(f"{display_name(r.get('manager'))} ({money(r.get('value_usd'))})" for r in top[:5]) + '.')] if top else []
    if off:
        last = max(off, key=lambda r: r.get('date') or '')
        qa.append((f"Has Congress traded {t} stock?", f"Officials disclosed {seo.n_of(len(off), 'trade')} on file: {len(buys)} buys and {len(sells)} sales. The latest: "
                   f"{last.get('person')}, {last.get('transaction_type')} on {last.get('date')}."))
    if short and len(short) >= 3:
        qa.append((f"What is the short interest in {t}?", f"{short[1]:,.0f} shares were sold short at the {short[0]} settlement, {short[2]}% of the float."))
    body = (f"<p class='lead'>{e(lead)}</p>"
            + SV.hbars([(display_name(r.get('manager')), r.get('value_usd')) for r in top], money, f"Largest holders of {t} (13F)")
            + (f"<h2>Largest holders (13F)</h2><div class='tbl-wrap'><table><thead><tr><th>Fund</th><th class='num'>Shares</th><th class='num'>Value</th>"
               f"<th>Change</th><th>Quarter</th></tr></thead><tbody>{rows}</tbody></table></div>" if rows else '')
            + (f"<h2>Trades by Congress and other officials</h2><div class='tbl-wrap'><table><thead><tr><th>Date</th><th>Who</th><th>Trade</th><th class='num'>Amount</th></tr></thead><tbody>{orow}</tbody></table></div>" if orow else ''))
    return {'title': f"Who owns {name} ({t}) stock? Top holders, fund buying and Congress trades", 'h1': f"Who owns {name} ({t}) stock",
            'desc': lead[:300], 'body': body, 'qa': qa}


def gval(v, unit):
    """one guided figure: −$0.65 a share, $1.2B, 4.5%"""
    if unit == 'ps':
        return f"{'−' if v < 0 else ''}${abs(v):,.2f}"
    if unit == 'usd':
        return money(v)
    if unit == 'growth':
        return f"{'+' if v > 0 else '−' if v < 0 else ''}{abs(v):g}%"
    if unit == 'bps':
        return f"{'+' if v > 0 else '−' if v < 0 else ''}{abs(v):g} bps"
    if unit == 'x':
        return f"{v:g}×"
    return f"{'−' if v < 0 else ''}{abs(v):g}%"


def pword(p):
    """a guided period as a reader says it: 'Q@2026-12-27' (named by its last day in the release) is "the quarter ending
    Dec 27, 2026"; 'Q4 2026', 'FY2026' stay"""
    m = re.fullmatch(r'(Q|FY)@(\d{4}-\d{2}-\d{2})', str(p or ''))
    if not m:
        return p or ''
    return f"the {'quarter' if m.group(1) == 'Q' else 'year'} ending {fdate(m.group(2))}"


def grange(i):
    """a guided range, or the one figure when both ends are the same ("EPS $-0.65–-0.65" read wrong)"""
    lo, hi, u = i.get('lo'), i.get('hi'), i.get('unit')
    if hi is None or gval(hi, u) == gval(lo, u):                 # "$1.9B–$1.9B" too
        return gval(lo, u)
    return f"{gval(lo, u)} to {gval(hi, u)}" if lo < 0 or hi < 0 or u in ('growth', 'bps') else f"{gval(lo, u)}–{gval(hi, u)}"


def guidance(co, h, ol, rec=None):
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
        lead = f"{name} ({t}) {word} its guidance on {fdate(g.get('filed'))}: " + '; '.join(
            f"{i.get('name') or i.get('metric')} {grange(i)} for {pword(i.get('period'))}" for i in its) + '.'
        qa.append((f"Did {name} raise or lower its guidance?", lead))
    if md:
        c = md.get('counts') or {}
        lead += (f" {seo.poss(name)} {md.get('form')} filed {fdate(md.get('filed'))} makes {c.get('n', 0)} forward-looking statements"
                 + (f", {c.get('new', 0)} of them new and {c.get('dropped', 0)} no longer said since the filing before" if md.get('vs') else '') + '.')
        new = [s for s in md.get('statements') or [] if s.get('status') in ('new', 'updated')][:3] or (md.get('statements') or [])[:3]
        if new:
            qa.append((f"What does {name} expect?", ' '.join(s['t'] for s in new)[:600]))
    stm = ''.join(f"<li>{('<b>' + e(s.get('status')) + '</b> · ') if s.get('status') in ('new', 'updated') else ''}{e(s['t'])}</li>"
                  for s in (md or {}).get('statements', [])[:12])
    items = ''.join(f"<tr><td>{e(i.get('name') or i.get('metric'))}</td><td>{e(pword(i.get('period')))}</td><td class='num'>{e(grange(i))}</td>"
                    f"<td>{e(i.get('change') or '')}</td></tr>" for i in (g.get('items') or [])[:12] if i.get('lo') is not None)
    body = (f"<p class='lead'>{e(lead.strip())}</p>" + SC.guidance_outlook(name, rec, ol, money)
            + (f"<h2>Latest guidance</h2><div class='tbl-wrap'><table><thead><tr><th>Metric</th><th>Period</th><th class='num'>Range</th><th>Change</th></tr></thead><tbody>{items}</tbody></table></div>"
               + (f"<p class='muted'>From the earnings release filed {e(fdate(g.get('filed')))} (<a href='{e(g.get('url'))}' rel='nofollow'>8-K on EDGAR</a>).</p>" if g.get('url') else '') if items else '')
            + (f"<h2>Forward-looking statements, {e(md.get('form'))} filed {e(fdate(md.get('filed')))}</h2><ul class='seo-list'>{stm}</ul>" if stm else ''))
    return {'title': f"{name} ({t}) guidance and outlook: what the company expects", 'h1': f"{name} ({t}) guidance and outlook",
            'desc': lead.strip()[:300], 'body': body, 'qa': qa, 'modified': max(filter(None, [g.get('filed'), (md or {}).get('filed')]), default=None)}


LBO_DEFAULTS = {'premium': 0.30, 'leverage': 5.5, 'maxDebtShare': 0.65, 'minCoverage': 2.0, 'loanPremium': 0.5, 'fees': 0.02, 'years': 5,
                'target': 0.20, 'nwc': 0.10}                              # disclosures/docs/lbo-model.js DEFAULTS (the run returns them)
NOT_LBO_KIND = {'bank': 'a bank', 'insurer': 'an insurer', 'reit': 'a real-estate investment trust'}


def _f(v):
    return v if isinstance(v, (int, float)) and v == v and abs(v) != float('inf') else None


def _sp(v, d=0):
    """a percent with a true minus sign: 14%, −0.3% (the IRR, the premium against today's price)"""
    return '—' if v is None else f"{'−' if v < 0 else ''}{abs(v):.{d}f}%"


def _pf(v):
    """a premium as the proxies state it: 35%, 32.5%"""
    return f"{v:.1f}".rstrip('0').rstrip('.') + '%'


def _desc(parts, n=300):
    """the meta description: whole sentences up to about n characters, never cut mid-word"""
    out = ''
    for s in parts:
        if out and len(out) + 1 + len(s) > n:
            break
        out = (out + ' ' + s).strip()
    return out if len(out) <= n else out[:n].rsplit(' ', 1)[0] + '…'


def _irr_words(irr):
    """a buyer's yearly return in words: "about 14% a year", "a loss of about 3% a year", "a loss of all the money the buyer puts in" """
    if irr is None:
        return None
    if irr <= -0.995:
        return 'a loss of all the money the buyer puts in'
    return f"about {irr * 100:.0f}% a year" if irr >= 0 else f"a loss of about {-irr * 100:.0f}% a year"


def _premium_note(prem, sector):
    """(median %, low %, high %, deals, where) of the premiums the merger proxies on record state: the company's sector
    when it has ten deals or more, else all of them; None without them"""
    if not prem or not prem.get('median'):
        return None
    for s, n, med, lo, hi in prem.get('by_sector') or []:
        if s == sector and s != 'other' and n >= 10 and med:
            return med, lo, hi, n, 'in its sector'
    return prem['median'], prem.get('p25'), prem.get('p75'), prem.get('n') or 0, 'on record'


def _why_not(name, why, inp, kind):
    """(the short reason, the paragraph, the FAQ answer's second sentence) why the buyout model is not run on a company"""
    rev, eb = (inp or {}).get('revenue'), (inp or {}).get('ebitda')
    if not inp and kind in NOT_LBO_KIND:
        return (f"{name} is {NOT_LBO_KIND[kind]}, so the buyout model is not run on it",
                f"{name} is {NOT_LBO_KIND[kind]}: its debt — deposits, policy reserves or property loans — is part of how it does business, "
                "so a model that lends against EBITDA does not describe what a buyer would pay. Deals for companies like it are priced "
                "on book value and earnings instead.",
                "Its debt is part of the business, so deals for companies like it are priced on book value and earnings, not on borrowing against EBITDA.")
    if why == 'no positive EBITDA to borrow against' and eb is not None:
        return (f"it has no positive EBITDA to borrow against ({money(eb)} over the last 12 months" + (f", on revenue of {money(rev)})" if rev else ')'),
                f"A leveraged buyout is paid for mostly with debt that the company's own cash flow repays. {seo.poss(name)} EBITDA over the last 12 months was "
                f"{money(eb)}" + (f" on revenue of {money(rev)}" if rev else '') + ", so there is nothing to lend against and nothing to repay a loan "
                "with: a buyer would have to pay almost entirely with its own money. That is the kind of deal another company — a strategic buyer "
                "that wants the products, the pipeline or the technology — makes, not a private-equity fund. The model therefore gives no buyout price.",
                "With no cash flow to repay a loan, a buyer would pay almost entirely with its own money: a deal for another company (a strategic "
                "buyer), not for a private-equity fund.")
    if why == 'EBITDA margin under 3%' and eb is not None and rev:
        return (f"its EBITDA margin is only {100 * eb / rev:.1f}% ({money(eb)} on revenue of {money(rev)}), too thin to carry buyout debt",
                f"{name} kept {100 * eb / rev:.1f}% of its revenue as EBITDA over the last 12 months ({money(eb)} on {money(rev)}). A margin that thin "
                "cannot carry the debt a leveraged buyout needs — a small dip in sales would leave nothing for interest — so the model gives no buyout price.",
                "A margin that thin leaves almost nothing to pay interest with, so buyout debt does not fit.")
    if why == 'the debt alone pays for it':
        return ("its figures leave a buyer no equity to put in (the debt alone would cover the price), which the model treats as unusable",
                f"On {seo.poss(name)} figures the new debt the model allows would cover the whole price, leaving the buyer nothing to invest. That happens "
                "when cash or other figures are unusual, so the model gives no buyout price rather than a misleading one.",
                "The model gives no buyout price rather than a misleading one.")
    return ("the figures a buyout model needs (revenue, EBITDA, the share count and the price) are not all on file",
            f"The buyout model needs {seo.poss(name)} revenue, EBITDA, share count and share price; not all of them are on file, so it gives no buyout price.",
            "The model gives no buyout price until they are.")


def _lbo_tables(name, inp, rates, r, mp, sens, d):
    """the LBO worked through: entry, the new debt (and which limit set it), five years under the buyer, the exit, the
    return at other premiums, the figures used and the rules"""
    en, ex, yrs = r.get('entry') or {}, r.get('exit') or {}, r.get('years') or []
    price, shares = inp['price'], inp['shares']
    eb, rate = inp['ebitda'], _f(r.get('rate')) or 0
    debt0, cash0, claims = inp.get('debt') or 0, inp.get('cash') or 0, inp.get('claims') or 0
    caps = [(d['leverage'] * eb, f"{d['leverage']:g}× EBITDA"), (d['maxDebtShare'] * (en.get('ev') or 0), f"{d['maxDebtShare']:.0%} of the price"),
            (eb / (d['minCoverage'] * rate) if rate else float('inf'), f"interest EBITDA covers {d['minCoverage']:g} times")]
    bound = min(caps, key=lambda c: c[0])[1]
    row = lambda k, v, n='': f"<tr><td>{e(k)}</td><td class='num'>{e(v)}</td><td>{e(n)}</td></tr>"   # noqa: E731
    entry = (row('Offer price a share', usd(r.get('price')), f"today's {usd(price)} plus {r.get('premium', d['premium']):.0%}")
             + row('× shares', f"{shares / 1e6:,.1f} million")
             + row('= Equity value', money((r.get('price') or 0) * shares))
             + row('+ Debt refinanced', money(debt0)) + row('− Cash', money(cash0))
             + (row('+ Other claims', money(claims), 'preferred stock, minority interests') if claims else '')
             + row('= Enterprise value', money(en.get('ev')), f"{en.get('multiple', 0):.1f}× EBITDA of {money(eb)}")
             + row('Fees', money(en.get('fees')), f"{d['fees']:.0%} of the price")
             + row('New debt', money(en.get('debt')), f"{en.get('leverage', 0):.1f}× EBITDA at {100 * rate:.2f}% a year; the limit that binds: {bound}")
             + row("Buyer's own money", money(en.get('equity')), f"{100 * (en.get('equityShare') or 0):.0f}% of the cost"))
    yr = ''.join(f"<tr><td>Year {y['t']}</td><td class='num'>{e(money(y['revenue']))}</td><td class='num'>{e(money(y['ebitda']))}</td>"
                 f"<td class='num'>{e(money(y['interest']))}</td><td class='num'>{e(money(y['fcf']))}</td><td class='num'>{e(money(y['debt']))}</td></tr>" for y in yrs)
    moic = _f(r.get('moic'))
    exit_ = (row('Exit multiple', f"{ex.get('multiple', 0):.1f}× EBITDA", "today's trading multiple, before any premium")
             + row('Enterprise value at exit', money(ex.get('ev')))
             + row('− Debt left', money(ex.get('debt'))) + (row('+ Cash built up', money(ex.get('cash'))) if (ex.get('cash') or 0) > 0 else '')
             + row("= Buyer's equity", money(ex.get('equity')))
             + row('Money multiple', f"{moic:.2f}×" if moic is not None else '—', f"on {money(en.get('equity'))} put in")
             + row("Buyer's yearly return (IRR)", _sp(100 * r['irr'], 1) if _f(r.get('irr')) is not None else '—'))
    sv = ''.join(f"<tr><td class='num'>{100 * p:.0f}%</td><td class='num'>{e(usd(pp))}</td><td class='num'>{e(_sp(100 * i, 1) if _f(i) is not None else '—')}</td></tr>"
                 for p, pp, i in sens or [])
    margin = 100 * eb / inp['revenue']
    figs = (row('Revenue, last 12 months', money(inp['revenue'])) + row('EBITDA, last 12 months', money(eb), f"{margin:.1f}% of revenue")
            + (row('Depreciation and amortization', money(inp.get('da'))) if inp.get('da') is not None else '')
            + (row('Capital spending', money(abs(inp['capex']))) if inp.get('capex') is not None else '')
            + row('Debt', money(debt0)) + row('Cash', money(cash0))
            + row('Share price', usd(price), f"on {fdate(inp['price_date'])}" if inp.get('price_date') else ''))
    rt = rates or {}
    rules = (f"Fixed rules, the same as the interactive view's starting point: the shares are bought at today's price plus "
             f"{r.get('premium', d['premium']):.0%}, the company's debt is refinanced and fees take {d['fees']:.0%}. New debt is the least of "
             f"{d['leverage']:g}× EBITDA, {d['maxDebtShare']:.0%} of the price and the amount whose interest EBITDA covers {d['minCoverage']:g} times, "
             f"at {100 * rate:.2f}% a year (" + (f"SOFR {rt['base']:g}% plus the high-yield B spread {rt['spread_b']:g}% plus {d['loanPremium']:g}%"
                                                 if _f(rt.get('base')) is not None and _f(rt.get('spread_b')) is not None else 'the market rate for such loans')
             + (f", rates of {fdate(rt['as_of'])}" if rt.get('as_of') else '') + "). "
             f"Revenue grows {100 * (_f(r.get('growth')) or 0):.1f}% in the first year — the company's own rate, held between −3% and +8% — "
             f"fading to 3% by year {d['years']}; the EBITDA margin, depreciation and capital spending stay at today's share of revenue; working capital "
             f"takes {d['nwc']:.0%} of each year's added revenue; tax is {100 * (_f(r.get('tax')) or 0):.0f}% of profit after interest. Every dollar of "
             f"free cash flow repays debt. After {d['years']} years the buyer sells at today's multiple of EBITDA.")
    debt_chart = SV.bars([('Entry', en.get('debt'))] + [(f"Year {y['t']}", y['debt']) for y in yrs], money, f"{name}: buyout debt left, year by year",
                         note='Free cash flow after interest and tax repays the debt; a shortfall is borrowed.')
    return ("<h2>The buyout, step by step</h2><div class='tbl-wrap'><table><thead><tr><th>Entry</th><th class='num'>Amount</th><th>How</th></tr></thead>"
            f"<tbody>{entry}</tbody></table></div>"
            f"<h2>{d['years']} years under the buyer</h2>" + debt_chart
            + "<div class='tbl-wrap'><table><thead><tr><th>Year</th><th class='num'>Revenue</th><th class='num'>EBITDA</th><th class='num'>Interest</th>"
            f"<th class='num'>Free cash flow</th><th class='num'>Debt left</th></tr></thead><tbody>{yr}</tbody></table></div>"
            "<h2>The exit and the buyer's return</h2><div class='tbl-wrap'><table><thead><tr><th>Exit</th><th class='num'>Amount</th><th></th></tr></thead>"
            f"<tbody>{exit_}</tbody></table></div>"
            + (f"<h2>Price against return</h2><p>What the buyer makes at other premiums over today's {e(usd(price))}"
               + (f"; the IRR reaches {d['target']:.0%} at {e(usd(mp))} a share" if mp else '') + ".</p>"
               "<div class='tbl-wrap'><table><thead><tr><th class='num'>Premium</th><th class='num'>Price a share</th><th class='num'>Buyer's IRR</th></tr></thead>"
               f"<tbody>{sv}</tbody></table></div>" if sv else '')
            + "<h2>The figures used</h2><div class='tbl-wrap'><table><thead><tr><th>Figure</th><th class='num'>Amount</th><th></th></tr></thead>"
            f"<tbody>{figs}</tbody></table></div><p class='muted'>{e(rules)}</p>")


def takeover(co, lbo, board_row, model=None, defaults=None, prem=None):
    """c/<slug>/takeover/: whether a leveraged buyout works and at what price — the whole calculation on the page when it
    does, and why not when it does not — the historical odds, what takeovers on record paid, and the rumors.
    model: this company's result from scripts/seo_lbo.py (the site's own LBO model); without it the board's summary."""
    if not lbo or not (lbo.get('inputs') or lbo.get('rumors')):
        return None
    name, t = co['who_name'], co['ticker']
    inp = lbo.get('inputs') or None
    hs = ((lbo.get('history') or {}).get('acquired')) or {}
    rum = lbo.get('rumors') or []
    br = board_row or {}
    d = {**LBO_DEFAULTS, **{k: v for k, v in (defaults or {}).items() if v is not None}}
    m = model or {}
    r = m.get('run') if m.get('ok') else None
    if r and _f(r.get('irr')) is None:
        r = None
    irr = r['irr'] if r else br.get('irr')
    mp = ((m.get('max') or {}).get('price') if r else br.get('max_price'))
    capped = bool(r and (m.get('max') or {}).get('capped'))
    flags = (r.get('flags') if r else br.get('flags') if br.get('irr') is not None else None) or []
    why = None if irr is not None else (m.get('why') or (br.get('flags') or [None])[0])
    # "no buyout" when the model (or the board, which runs it) has looked at the figures and found none, or when the figures
    # it needs were never put together (a bank, insurer or REIT, or a company missing revenue, EBITDA, shares or price)
    no_lbo = irr is None and (bool(inp and (m or br)) or not inp)
    if not rum and irr is None and not hs and not no_lbo:
        return None
    price = (inp or {}).get('price')
    parts, qa_lbo = [], None
    if irr is not None:
        offer = r.get('price') if r else (price * (1 + d['premium']) if price else None)
        s = (f"A leveraged buyout at today's price plus {d['premium']:.0%}" + (f" ({usd(offer)} a share)" if offer else '')
             + f" would return {_irr_words(irr)} to a private-equity buyer over {d['years']} years")
        if mp:
            s += (f"; the most a buyer could pay for a {d['target']:.0%} return is more than {usd(mp)} a share" if capped else
                  f"; the most a buyer could pay for a {d['target']:.0%} return is {usd(mp)} a share" + (f" ({_sp(100 * (mp / price - 1))} against today's {usd(price)})" if price else ''))
        elif r:
            s += f"; no price, however low, gets a buyer to {d['target']:.0%}"
        parts.append(s + '.')
        if 'too big' in flags:
            ev = (r or {}).get('entry', {}).get('ev') if r else br.get('ev')
            parts.append((f"At {money(ev)} it would be larger than any buyout on record (the model flags anything over $60 billion), so this is a "
                          "thought experiment more than a prospect.") if ev else "It would be larger than any buyout on record, so this is a thought experiment.")
        if 'levered' in flags and inp and inp.get('ebitda'):
            parts.append(f"It already carries {((inp.get('debt') or 0) - (inp.get('cash') or 0)) / inp['ebitda']:.1f}× EBITDA in net debt (the model flags "
                         "anything over 6×), so a buyer could add little debt of its own.")
        qa_lbo = ' '.join(parts)
    elif no_lbo:
        short, _, answer = _why_not(name, why, inp, lbo.get('kind'))
        parts.append(f"A leveraged buyout does not work for {name} on its latest figures: {short}.")
        qa_lbo = parts[-1] + ' ' + answer
    hist_s = (f"Historically {hs['p'] * 100:.1f}% of companies with its figures were bought within a year ({hs.get('lift') or '—'}× the average)."
              if hs.get('p') is not None else None)
    if hist_s:
        parts.append(hist_s)
    if rum:
        parts.append(f"Latest signal ({rum[0].get('date')}): {rum[0].get('text')}.")
    lead_txt = ' '.join(parts)
    pn = _premium_note(prem, lbo.get('sector'))
    prem_html, qa_cost = '', None
    if pn:
        med, lo, hi, n, where = pn
        txt = (f"Takeovers {where} paid a median premium of {_pf(med)} over the share price before the deal"
               + (f" (the middle half {_pf(lo)} to {_pf(hi)})" if lo is not None and hi is not None else '')
               + f", according to the {n:,} merger proxies and tender-offer responses on EDGAR that state a premium.")
        rows_ = ''
        if price and inp.get('shares'):
            eq = lambda p_: price * (1 + p_ / 100) * inp['shares']   # noqa: E731
            txt += f" At the median, {name} would cost about {usd(price * (1 + med / 100))} a share, {money(eq(med))} for all its shares."
            rows_ = ''.join(f"<tr><td>{e(k)}</td><td class='num'>{e(_pf(p_))}</td><td class='num'>{e(usd(price * (1 + p_ / 100)))}</td>"
                            f"<td class='num'>{e(money(eq(p_)))}</td></tr>" for k, p_ in (('Low end (a quarter of deals paid less)', lo),
                                                                                          ('Median', med), ('High end (a quarter paid more)', hi)) if p_ is not None)
            qa_cost = (f"What would a takeover of {name} cost?", txt)
        prem_html = (f"<h2>What a takeover could cost</h2><p>{e(txt)}</p>"
                     + (f"<div class='tbl-wrap'><table><thead><tr><th>Premium</th><th class='num'>%</th><th class='num'>Price a share</th>"
                        f"<th class='num'>All shares</th></tr></thead><tbody>{rows_}</tbody></table></div>" if rows_ else ''))
    odds = ''
    if hs.get('p') is not None:
        odds = (f"<h2>The odds, from history</h2><p>{e(hist_s)} "
                + (f"Its figures put it in decile {hs['decile']} of 10 (10 = the most likely to be bought). " if hs.get('decile') else '')
                + "The odds come from a model of every merger proxy, tender-offer response and going-private statement filed on EDGAR since 2011, "
                "set against each company's size, margins, debt, cash flow and growth the year before.</p>")
    rl = ''.join(f"<li>{e(x.get('date'))} · {e(x.get('kind'))} · {e(x.get('text'))}</li>" for x in rum[:10])
    qa = [(f"Is {name} being acquired?", (f"The latest signal on file is from {rum[0].get('date')}: {rum[0].get('text')}. A headline is not a deal; "
                                          "Filing Flows lists the news, 8-K filings and 13D filings about a sale.") if rum else
           "No headline, 8-K or 13D about a sale is on file in the last year.")]
    if qa_lbo:
        qa.append((f"Could private equity buy {name}?", qa_lbo))
    if qa_cost:
        qa.append(qa_cost)
    tiles = []
    if irr is not None:
        tiles = [('Share price', usd(price)), (f"Offer at +{d['premium']:.0%}", usd(r.get('price')) if r else None),
                 ("Buyer's IRR", _sp(100 * irr)), (f"Most for {d['target']:.0%}", (('> ' if capped else '') + usd(mp)) if mp else None),
                 ('EV / EBITDA', f"{r['todayMultiple']:.1f}×" if r and _f(r.get('todayMultiple')) else None),
                 ('Buyout debt', f"{r['entry']['leverage']:.1f}× EBITDA" if r and _f((r.get('entry') or {}).get('leverage')) is not None else None)]
    elif inp:
        tiles = [('Share price', usd(price)), ('Market value', money(inp.get('mcap'))), ('Enterprise value', money(inp.get('ev'))),
                 ('Cash', money(inp.get('cash'))), ('Debt', money(inp.get('debt') or 0)), ('Revenue, 12 months', money(inp.get('revenue'))),
                 ('Revenue growth', pc(100 * inp['g0']) if _f(inp.get('g0')) is not None else None), ('EBITDA, 12 months', money(inp.get('ebitda')))]
    tile_html = ''.join(f"<div class='seo-tile'><span>{e(k)}</span><b>{e(v)}</b></div>" for k, v in tiles if v and v != '—')
    if r and inp:
        detail = _lbo_tables(name, inp, lbo.get('rates'), r, mp if not capped else None, m.get('sens'), d)
    elif no_lbo:
        detail = f"<h2>Why a leveraged buyout does not fit</h2><p>{e(_why_not(name, why, inp, lbo.get('kind'))[1])}</p>"
    else:
        detail = ''
    body = (f"<p class='lead'>{e(lead_txt)}</p>" + (f"<div class='seo-tiles'>{tile_html}</div>" if tile_html else '') + detail + prem_html + odds
            + (f"<h2>Rumors and deal signals</h2><ul class='seo-list'>{rl}</ul>" if rl else ''))
    title = (f"{name} ({t}) takeover and buyout analysis: LBO price, odds and rumors" if irr is not None else
             f"{name} ({t}) takeover analysis: odds, deal premiums and rumors")
    pre = f"{name} ({t}): "                                      # the snippet names the company (the lead begins "A leveraged buyout …")
    return {'title': title, 'h1': f"Is {name} ({t}) a takeover target?", 'desc': pre + _desc(parts, 300 - len(pre)), 'body': body, 'qa': qa}


def risks(co, out):
    if not out:
        return None
    name, t = co['who_name'], co['ticker']
    r, cp, en, fr, tr = (out.get(k) or {} for k in ('recalls', 'complaints', 'environment', 'fedreg', 'trials'))
    parts, qa, body = [], [], ''
    if r.get('n'):
        parts.append(f"{seo.n_of(r.get('last_12m', 0), 'recall')} in the last 12 months ({r.get('n')} in five years, {r.get('class1', 0)} Class I)")
        qa.append((f"Has {name} had any recalls?", f"{seo.n_of(r.get('n'), 'recall')} on file over five years from the FDA, CPSC and NHTSA; {r.get('last_12m', 0)} in the last 12 months."))
        body += '<h2>Latest recalls</h2><ul class="seo-list">' + ''.join(f"<li>{e(x.get('date'))} · {e(x.get('source'))} · {e(x.get('what'))}</li>" for x in (r.get('latest') or [])[:8]) + '</ul>'
    if cp.get('last_12m'):
        parts.append(f"{seo.n_of(cp['last_12m'], 'consumer complaint')} to the CFPB in 12 months" + (f" ({cp['change'] * 100:+.0f}%)" if cp.get('change') is not None else ''))
        qa.append((f"How many complaints does {name} get?", f"{cp['last_12m']:,} complaints to the Consumer Financial Protection Bureau in the last 12 months"
                   + (f", {cp['change'] * 100:+.0f}% on the year before" if cp.get('change') is not None else '') + '.'))
    if en.get('facilities'):
        parts.append(f"{seo.n_of(en.get('in_violation', 0), 'EPA-regulated facility', 'EPA-regulated facilities')} in violation, {money(en.get('penalties_5y'))} in penalties over five years")
        qa.append((f"Has {name} been fined by the EPA?", f"Its {seo.n_of(en['facilities'], 'EPA-regulated facility', 'EPA-regulated facilities')} drew {money(en.get('penalties_5y'))} in penalties over five years; "
                   f"{en.get('in_violation', 0)} {'is' if en.get('in_violation', 0) == 1 else 'are'} in violation now."))
    if fr.get('count'):
        parts.append(f"{seo.n_of(fr['count'], 'Federal Register document')} in a year")
    if tr.get('active'):
        parts.append(f"{seo.n_of(tr['active'], 'active clinical trial')}")
        qa.append((f"How many clinical trials does {name} have?", f"{tr['active']} active studies on ClinicalTrials.gov, {((tr.get('phases') or {}).get('PHASE3') or {}).get('active', 0)} in phase 3."))
    if not parts:
        return None
    desc = f"{name} ({t}) beyond its filings: " + '; '.join(parts) + '.'
    # nothing found ("0 EPA-regulated facilities in violation, $0 in penalties", a count of Federal Register notices): the
    # page stays for the company page's readers but is no answer a search should land on (noindex, out of the sitemap)
    found = r.get('n') or cp.get('last_12m') or en.get('in_violation') or (en.get('penalties_5y') or 0) > 0 or tr.get('active')
    return {'title': f"{name} ({t}) recalls, complaints, EPA and regulation", 'h1': f"{name} ({t}): recalls, complaints and regulation",
            'desc': desc[:300], 'body': f"<p class='lead'>{e(desc)}</p>" + body, 'qa': qa, 'noindex': not found}


# ---------------------------------------------------------------- revenue and earnings date
def _flows(q):
    """(labels, inflow per node {id: [v, q, y]}, children {id: [ids]}) of a Sankey spec."""
    import html as H
    lab = {n['id']: seo.label(n.get('label') or n.get('name') or n['id']) for n in q.get('nodes') or []}
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


def segment_river(name, qs, n=12):
    """the lines that make up revenue, quarter by quarter (a stacked area): how the mix shifted"""
    rows, shown = [], {}
    for q in qs[:n]:
        nodes = {x.get('id'): x for x in q.get('nodes') or []}
        d = {}
        for ln in q.get('links') or []:
            s = nodes.get(ln.get('s'))
            if ln.get('t') == 'revenue' and s and s.get('name') and ln.get('v'):
                lab = seo.label(s['name'])
                key = lab.casefold()                          # "MEDTECH" and "MedTech" are one line
                shown.setdefault(key, lab)                    # … shown with the latest quarter's spelling
                d[key] = d.get(key, 0) + ln['v']
        if len(d) >= 2:
            rows.append((q.get('label'), d))
    # one breakdown throughout: a quarter whose lines are another partition of revenue (product/service against
    # segments) would draw bands that start and stop; the run of quarters sharing the latest quarter's lines is drawn
    keep = []
    for lab, d in rows:
        same = len(set(d) & set(rows[0][1])) / max(1, len(set(d) | set(rows[0][1])))
        if same < 0.5:
            break
        keep.append((lab, d))
    rows = list(reversed(keep))
    if len(rows) < 3:
        return ''
    names = sorted({k for _, d in rows for k in d}, key=lambda k: -sum(d.get(k, 0) for _, d in rows))[:8]
    first, last = rows[0][1], rows[-1][1]
    tf, tl = sum(first.values()) or 1, sum(last.values()) or 1
    both = [k for k in names if k in first and k in last]        # a line reported at both ends: a relabelled one is no shift in the mix
    shift = sorted(((k, last[k] / tl - first[k] / tf) for k in both), key=lambda kv: -abs(kv[1]))[0] if both else None
    note = ('' if shift is None else
            f"{shown[shift[0]]} went from {100 * first[shift[0]] / tf:.0f}% of revenue in {rows[0][0]} to {100 * last[shift[0]] / tl:.0f}% in {rows[-1][0]}, the largest shift in the mix."
            if abs(shift[1]) >= 0.02 else f"The mix barely moved between {rows[0][0]} and {rows[-1][0]}.")
    return SV.river([l for l, _ in rows], [(shown[k], [d.get(k) for _, d in rows]) for k in names], money, f"{name}: revenue by line, {rows[0][0]} to {rows[-1][0]}", note=note)


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
    chg = lambda a, b: (a / b - 1) * 100 if a is not None and b and b > 0 else None    # noqa: E731  (no growth from a negative base)
    segs = []
    for s_ in dict.fromkeys(kids.get('revenue', [])):
        sub = [(lab.get(k, k), _from(links, k, s_)) for k in dict.fromkeys(kids.get(s_, []))]
        segs.append((lab.get(s_, s_), _from(links, s_, 'revenue'), sorted(sub, key=lambda x: -x[1][0])))
    segs.sort(key=lambda x: -x[1][0])
    tot = rev[0]
    val = lambda nid: (into.get(nid) or [None])[0]               # noqa: E731
    gp, oi, net = val('gp'), val('oi'), val('net')
    g = chg(rev[0], rev[2])
    lead = f"{name} ({t}) made {money(tot)} of revenue in the {words} ({q.get('label')})" + (f", {seo.vs(g, 'a year earlier')}" if g is not None else '') + '.'
    if len(segs) > 1:
        lead += ' ' + '; '.join(f"{n_} brought in {money(v[0])} ({100 * v[0] / tot:.0f}%)" for n_, v, _ in segs[:3]) + '.'
    cents = [(k, x) for k, x in (('gross profit', gp), ('operating profit', oi), ('net earnings', net)) if seo.ratio(x, tot) is not None]
    if cents:    # a company whose costs dwarf its revenue has no "cents of every dollar" to speak of (seo.ratio)
        lead += ' Of every dollar of revenue, ' + ', '.join(f"{abs(100 * x / tot):.0f}¢ was {'left as ' + k if x >= 0 else 'lost at the ' + k + ' line'}" for k, x in cents) + '.'
    rows = ''
    for n_, v, sub in segs:
        rows += (f"<tr><td><b>{e(n_)}</b></td><td class='num'>{e(money(v[0]))}</td><td class='num'>{100 * v[0] / tot:.1f}%</td>"
                 f"<td class='num'>{e(pc(chg(v[0], v[1])))}</td><td class='num'>{e(pc(chg(v[0], v[2])))}</td></tr>")
        for sn, sv in sub[:8]:
            rows += (f"<tr><td>&nbsp;&nbsp;↳ {e(sn)}</td><td class='num'>{e(money(sv[0]))}</td><td class='num'>{100 * sv[0] / tot:.1f}%</td>"
                     f"<td class='num'>{e(pc(chg(sv[0], sv[1])))}</td><td class='num'>{e(pc(chg(sv[0], sv[2])))}</td></tr>")
    ladder = [('Revenue', tot), ('Cost of revenue', val('cor')), ('Gross profit', gp), ('Operating expenses', val('opex')), ('Operating profit', oi),
              ('Income tax', val('tax')), ('Net earnings', net), ('Operating cash flow', val('ocf')), ('Free cash flow', val('fcf'))]
    lad = ''.join(f"<tr><td>{e(k)}</td><td class='num'>{e(money(x))}</td><td class='num'>{e(seo.pct(100 * x / tot, False))}</td></tr>" for k, x in ladder if x is not None)
    hist = ''.join(f"<tr><td>{e(x.get('label'))}</td><td class='num'>{e(money((x.get('headline') or {}).get('revenue')))}</td>"
                   f"<td class='num'>{e(pc((x.get('headline') or {}).get('yoy')))}</td></tr>" for x in qs[:8])
    qa = [(f"How does {name} make money?", lead)]
    if len(segs) > 1:
        s0 = segs[0]
        g0 = chg(s0[1][0], s0[1][2])
        qa.append((f"What is {seo.poss(name)} biggest business?", f"{s0[0]}: {money(s0[1][0])} in the {words}, {100 * s0[1][0] / tot:.0f}% of revenue"
                   + (f", {seo.vs(g0, 'a year earlier')}" if g0 is not None else '') + '.'))
    if seo.ratio(net, tot) is not None:
        qa.append((f"What is {seo.poss(name)} profit margin?", f"Net {'earnings were' if net >= 0 else 'loss was'} {money(abs(net))}, {abs(100 * net / tot):.1f}% of revenue, in the {words}"
                   + (f"; the operating margin was {100 * oi / tot:.1f}%." if seo.ratio(oi, tot) is not None else '.')))
    body = (f"<p class='lead'>{e(lead)}</p>" + sankey_figure(co.get('cik') or 0, q.get('label'), f"{name} {q.get('label')} revenue to profit and cash Sankey")
            + (SV.hbars([(n_, v[0]) for n_, v, _ in segs], money, f"{name} revenue by segment, {q.get('label')}") if len(segs) > 1 else '')
            + segment_river(name, qs)
            + SV.bars([(x.get('label'), (x.get('headline') or {}).get('revenue')) for x in reversed(qs[:8])], money, f"{name} revenue by quarter")
            + (SV.hbars([(k, x) for k, x in ladder[1:] if x is not None and x > 0], lambda v, tt=tot: f"{100 * v / tt:.0f}¢", f"{name}: where each dollar of revenue goes", n=9)
               if all(seo.ratio(x, tot) is not None for k, x in ladder[1:] if x is not None and x > 0) else '')
            + (f"<h2>Revenue by segment, {e(q.get('label'))}</h2><div class='tbl-wrap'><table><thead><tr><th>Segment</th><th class='num'>Revenue</th><th class='num'>Share</th>"
               f"<th class='num'>Q/Q</th><th class='num'>Y/Y</th></tr></thead><tbody>{rows}</tbody></table></div>" if len(segs) > 1 else '')
            + f"<h2>Where each dollar of revenue goes</h2><div class='tbl-wrap'><table><thead><tr><th>Line</th><th class='num'>{e(q.get('label'))}</th><th class='num'>% of revenue</th></tr></thead><tbody>{lad}</tbody></table></div>"
            + f"<h2>Revenue, quarter by quarter</h2><div class='tbl-wrap'><table><thead><tr><th>Quarter</th><th class='num'>Revenue</th><th class='num'>Y/Y</th></tr></thead><tbody>{hist}</tbody></table></div>"
            + f"<p class='muted'>From {e(name)}'s {e(q.get('form'))} filed {e(fdate(q.get('filed')))}" + (f" (<a href='{e(q.get('doc_url'))}' rel='nofollow'>on EDGAR</a>)" if q.get('doc_url') else '') + '.</p>')
    return {'title': f"How {name} ({t}) makes money: revenue by segment, {q.get('label')}", 'h1': f"How {name} ({t}) makes money",
            'desc': lead[:300], 'body': body, 'qa': qa, 'modified': (q.get('filed') or '')[:10] or None}


def earnings_date(co, er, c, cons, today=None):
    """c/<slug>/earnings-date/: one URL for the company's earnings, all year round. Before a report it is the preview
    (date, what analysts expect, the model's odds, the options' implied move, what to watch in the last quarter's
    lines); for ten days after a report it leads with the result against the estimate; then it turns to the next date.
    Search engines index it ahead of the report, so it is there when people search on the day."""
    if not er or not er.get('report_date'):
        return None
    today = today or dt.date.today()
    name, t = co['who_name'], co['ticker']
    cs = er.get('consensus') or {}
    d = er['report_date']
    try:
        days = (dt.date.fromisoformat(d) - today).days
    except ValueError:
        return None
    when = fdate(d) + (' (estimated)' if er.get('date_estimated') else '')
    q = ((c or {}).get('quarters') or [{}])[0]
    h = q.get('headline') or {}
    hist = [x for x in er.get('history') or [] if x.get('reported')]
    last = hist[-1] if hist else None
    since = (today - dt.date.fromisoformat(last['reported'])).days if last else None
    just = last is not None and since is not None and 0 <= since <= 10 and last.get('act') is not None and last.get('est') is not None
    beat = (cons or {}).get('beat_rate', er.get('beat_rate'))
    p = (er.get('model') or {}).get('p')
    mv = (er.get('implied') or {}).get('move')
    revs = money(h.get('revenue'))
    try:                                                    # the site's latest quarter is the one just reported (it ended < 4 months before)
        same_q = bool(last and q.get('end') and 0 <= (dt.date.fromisoformat(last['reported']) - dt.date.fromisoformat(q['end'])).days <= 120)
    except ValueError:
        same_q = False
    segs = seo.segments(q) if q.get('nodes') else []
    lead = ''
    if just:
        verb = 'beat' if last['act'] > last['est'] else 'missed' if last['act'] < last['est'] else 'matched'
        lead = (f"{name} ({t}) reported on {fdate(last['reported'])} and {verb} the EPS estimate: {seo.usd2(last['act'])} against {seo.usd2(last['est'])}"
                + (f" ({100 * last['surprise']:+.1f}%)" if last.get('surprise') is not None else '')
                + (f". Revenue was {revs} for {q.get('label')}" + (f", {pc(h.get('yoy'))} year over year" if h.get('yoy') is not None else '') if h.get('revenue') and same_q else '')
                + (f". The stock moved {100 * last['move']:+.1f}% on the report" if last.get('move') is not None else '') + '. ')
        title = f"{name} ({t}) Earnings {verb.capitalize()}: EPS {seo.usd2(last['act'])} vs {seo.usd2(last['est'])}" + (f", Revenue {revs}" if h.get('revenue') and same_q else '')
        h1 = f"{name} ({t}) earnings: {verb} the estimate"
    if days >= 0:
        lead += (f"{name} ({t}) {'reports next' if just else 'is expected to report earnings'} on {when}" + (', tomorrow' if days == 1 else f", in {days} days" if days else ', today')
                 + (f", for the quarter ending {fdate(er.get('quarter'))}" if er.get('quarter') else '') + '.')
        if cs.get('eps') is not None:
            lead += (f" Analysts expect EPS of {seo.usd2(cs['eps'])}"
                     + ((f" ({seo.usd2(cs['eps_low'])} to {seo.usd2(cs['eps_high'])}, {seo.n_of(cs['n'], 'estimate')})" if cs.get('eps_low') != cs.get('eps_high')
                         else f" ({seo.n_of(cs['n'], 'estimate')})") if cs.get('eps_low') is not None and cs.get('n') else '')
                     + (f" on revenue of {money(cs['rev'])}" if cs.get('rev') else '')
                     + ((f", against {seo.usd2(cs['year_ago_eps'])}" + (f" and {money(cs['year_ago_rev'])}" if cs.get('year_ago_rev') else '') + ' a year ago')
                        if cs.get('year_ago_eps') is not None else '') + '.')
        if not just:
            title = f"{name} ({t}) Earnings {fdate(d)[:-6]}: What to Expect" + (f" (EPS Est. {seo.usd2(cs['eps'])})" if cs.get('eps') is not None else '')
            h1 = f"{name} ({t}) earnings on {fdate(d)}: what to expect"
    elif not just:
        lead = (f"{name} ({t}) last reported on {fdate(last['reported'] if last else d)}"
                + (f": revenue {revs} for the {seo.period_words(q.get('label'))}" if h.get('revenue') else '') + '. The next date is not set yet.')
        title, h1 = f"{name} ({t}) earnings: latest results and next report date", f"{name} ({t}) earnings"
    if beat is not None:
        lead += f" It beat the EPS estimate in {round(100 * beat)}% of the quarters on record"
        lead += f"; Filing Flows' model gives it a {round(100 * p)}% chance of beating next time." if p is not None and days >= 0 else '.'
    if mv and days >= 0:
        lead += f" Options imply a move of about ±{100 * mv:.1f}% on the report."
    qa = [(f"When does {t} report earnings?", (f"{name} is expected to report on {when}." if days >= 0 else 'The next date is not set yet.'))]
    if just:
        qa.insert(0, (f"Did {name} beat earnings?", lead.split('. ')[0].rstrip('.') + '.'))
    if cs.get('eps') is not None and days >= 0:
        qa.append((f"What are analysts expecting from {name}?", f"EPS of {seo.usd2(cs['eps'])}" + (f" and revenue of {money(cs['rev'])}" if cs.get('rev') else '') + ' for the quarter.'))
    if beat is not None:
        qa.append((f"Does {name} usually beat earnings?", f"It beat the consensus EPS estimate in {round(100 * beat)}% of the quarters on record."))
    tiles = ''.join(f"<div class='seo-tile'><span>{e(k)}</span><b>{e(v)}</b></div>" for k, v in (
        ('Last result', (f"{'+' if last['act'] >= last['est'] else '−'}{abs(100 * (last.get('surprise') or 0)):.1f}% vs estimate") if just else None),
        ('Report date', when if days >= 0 else None), ('Days to go', str(days) if days >= 0 else None),
        ('EPS estimate', f"{seo.usd2(cs['eps'])}" if cs.get('eps') is not None and days >= 0 else None),
        ('Revenue estimate', money(cs.get('rev')) if cs.get('rev') and days >= 0 else None), ('Beat rate', f"{round(100 * beat)}%" if beat is not None else None),
        ('Implied move', f"±{100 * mv:.1f}%" if mv and days >= 0 else None)) if v)
    charts = ''
    hh = [x for x in hist[-8:] if x.get('est') is not None and x.get('act') is not None]
    if len(hh) >= 3:
        charts += SV.duo([(fdate(x['reported'])[:3] + ' ' + x['reported'][2:4], x['est'], x['act']) for x in hh], ('Estimate', 'Reported'), seo.usd2,
                         f"{name}: EPS against the estimate, last {len(hh)} reports")
    mm = [x for x in hist[-8:] if x.get('move') is not None]
    if len(mm) >= 3:
        charts += SV.diverging([(fdate(x['reported']), 100 * x['move']) for x in reversed(mm)], lambda v: f"{v:+.1f}%", f"{t}: the stock's move on each report", n=8)
    watch = ''
    if days >= 0 and q.get('nodes'):
        grow = []
        for n in q.get('nodes') or []:
            if n.get('color') == 'rev' and n.get('v') and n.get('y'):
                grow.append((seo.label(n.get('name')), n['v'], (n['v'] / n['y'] - 1) * 100))
        grow = sorted(grow, key=lambda g: -g[1])[:6]
        if grow:
            watch = (f"<h2>What to watch</h2><p>Last quarter ({e(q.get('label'))}) the lines that make up revenue grew like this; the report shows whether the trend holds:</p>"
                     + SV.diverging([(g[0], g[2]) for g in grow], seo.pct, f"{name}: revenue lines, growth year over year, {q.get('label')}", n=6))
            ours = er.get('ours') or {}
            if ours.get('eps') is not None and cs.get('eps') is not None:
                watch += (f"<p>Filing Flows' own estimate from the SEC figures — the same quarter last year times recent growth — is EPS {seo.usd2(ours['eps'])}"
                          + (f" on revenue of {money(ours['rev'])}" if ours.get('rev') else '') + f", against the analysts' {seo.usd2(cs['eps'])}.</p>")
    lastq = (f"<h2>The last report</h2><p>{e(name)} reported revenue of {e(revs)} for the {e(seo.period_words(q.get('label')))}"
             + (f" ({e(pc(h.get('yoy')))} Y/Y)" if h.get('yoy') is not None else '') + (f", net {'earnings' if h['ni'] >= 0 else 'loss'} {e(money(abs(h['ni'])))}" if h.get('ni') is not None else '')
             + (": " + ', '.join(f"{e(n)} {e(money(v))}" for n, v in segs[:4]) if len(segs) >= 2 else '')
             + ". <a href='../revenue/'>How it makes money →</a> · <a href='../'>Every quarter →</a></p>") if h.get('revenue') else ''
    body = f"<p class='lead'>{e(lead)}</p><div class='seo-tiles'>{tiles}</div>{watch}{lastq}" + (f"<div class='seo-grid'>{charts}</div>" if charts else '')
    mod = (last['reported'] if just else None) or (today - dt.timedelta(days=today.weekday())).isoformat()
    return {'title': title, 'h1': h1, 'desc': lead[:300], 'body': body, 'qa': qa, 'modified': mod}


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
    prem = (read(os.path.join(hub, 'research', 'lbo', 'history.json')) or {}).get('premiums')
    today = dt.date.today().isoformat()
    d0 = dt.date.today()
    week = (d0 - dt.timedelta(days=d0.weekday())).isoformat()      # most topics change daily in small ways: dated by the week
    urls, counts = [], {t: 0 for t, _, _ in TOPICS}
    images, pics = seo.og_images(base), {}
    order = sorted(latest.values(), key=lambda r: -(r.get('revenue') or 0))[:limit]
    # the takeover pages' LBO: every company's inputs through the site's own model in one Node process
    lbos = {r['cik']: read(os.path.join(hub, 'research', 'lbo', 'c', f"{r['cik']}.json")) for r in order if r.get('ticker')}
    models, lbo_defaults = seo_lbo.model_all({c: (d['inputs'], d.get('rates') or board.get('rates') or {}) for c, d in lbos.items() if d and d.get('inputs')}, site)
    for r in order:
        try:
            cik, slug, t = r['cik'], slug_for(r), (r.get('ticker') or '')
            if not t:
                continue
            co = {'who_name': display_name(r.get('name')), 'ticker': t, 'cik': cik}
            h = read(os.path.join(hub, 'holders', f'{t}.json'))
            cdoc = read(os.path.join(site, 'data', 'c', f'{cik}.json'))
            pages = {
                'revenue': lambda: revenue(co, cdoc),
                'earnings-date': lambda: earnings_date(co, read(os.path.join(hub, 'research', 'earnings', 'c', f'{t}.json')), cdoc, read(os.path.join(hub, 'consensus', 'c', f'{cik}.json'))),
                'stock-forecast': lambda: forecast(co, read(os.path.join(hub, 'research', 'valuation', 'c', f'{cik}.json')), read(os.path.join(hub, 'consensus', 'c', f'{cik}.json'))),
                'who-owns': lambda: owners(co, h),
                'guidance': lambda: guidance(co, h, read(os.path.join(site, 'data', 'outlook', f'{cik}.json')),
                                             read(os.path.join(site, 'data', 'guidance-record', f'{cik}.json'))),
                'takeover': lambda: takeover(co, lbos.get(cik), brow.get(cik), models.get(cik), lbo_defaults, prem),
                'risks': lambda: risks(co, read(os.path.join(hub, 'research', 'outside', 'c', f'{cik}.json'))),
            }
            pages = {k: safe(f, k, t) for k, f in pages.items()}
            q0 = ((cdoc or {}).get('quarters') or [{}])[0] or {}
            latest_q = q0.get('label')
            hq = q0.get('headline') or {}                           # the quarter in words: what the chart's figure holds before it is drawn
            in_words = (f"{co['who_name']}, {latest_q}: revenue {money(hq['revenue'])}" + (f" ({pc(hq.get('yoy'))} year over year)" if hq.get('yoy') is not None else '')
                        + (f", net {'earnings' if hq['ni'] >= 0 else 'loss'} {money(abs(hq['ni']))}" if hq.get('ni') is not None else '')
                        + '. The chart follows the revenue to costs, profit and cash.') if hq.get('revenue') else ''
            have =[k for k, v in pages.items() if v]
            if not have:
                continue
            for topic, p in pages.items():
                if not p:
                    continue
                url = f'{base}/c/{slug}/{topic}/'
                app = next(a for k, _, a in TOPICS if k == topic)
                # "How Target makes money" is what image search matches the Sankey to: the picture, its alt and caption here too
                pic = images.get(f"c-{cik}") if topic == 'revenue' else None
                cap = f"How {co['who_name']} makes money: {latest_q} revenue breakdown" if pic else None
                alt = f"{co['who_name']} ({t}) {latest_q} revenue breakdown Sankey: revenue by segment, costs, profit and cash flow" if pic else None
                crumbs = [('Filing Flows', base + '/'), (f"{co['who_name']} ({t})", f'{base}/c/{slug}/'), (p['h1'], url)]
                body = (f"<p class='crumbs'><a href='../../../'>Filing Flows</a> › <a href='../'>{e(co['who_name'])} ({e(t)})</a> › {e(next(l for k, l, _ in TOPICS if k == topic))}</p>"
                        f"<h1>{e(p['h1'])}</h1>{nav(slug, topic, have, cik)}{p['body']}"
                        + (seo.share_figure(pic, alt, cap, url, 3, False) if pic else '')
                        + (f"<h2>{e(seo.poss(co['who_name']))} latest quarter</h2>" + sankey_figure(cik, latest_q, f"{co['who_name']} {latest_q} income statement Sankey", fallback=in_words) if latest_q and topic != 'revenue' else '')
                        + f"{faq_html(p['qa'])}"
                        f"<p><a class='seo-cta' href='../../../#c-{cik}{('-' + app) if app else ''}'>Open the interactive view →</a></p>"
                        f"<p class='muted'>Updated {e(fdate(today))}. Read automatically from SEC filings and public data; errors are possible. Not investment advice.</p>")
                mod = p.get('modified') or week
                ld = ld_for(co['who_name'], t, url, crumbs, p['qa'], mod)
                if pic:
                    ld['@graph'].append(seo.image_ld(base, pic, alt, cap))
                    pics[url] = pic
                doc = seo.page(seo.fit(p['title']), p['desc'], url, body, 3, images.get(f"c-{cik}") or base + '/og.png', ld)
                if p.get('noindex'):
                    doc = seo.noindex(doc)
                d = os.path.join(site, 'c', slug, topic)
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, 'index.html'), 'w', encoding='utf-8') as f:
                    f.write(doc)
                if not p.get('noindex'):
                    urls.append((url, mod))
                counts[topic] += 1
            main = os.path.join(site, 'c', slug, 'index.html')            # the company page links to its topics
            try:
                txt = open(main, encoding='utf-8').read()
                if 'class="seo-more-main"' not in txt and '</main>' in txt:
                    charts13 = ''
                    if h:                                                   # 13F: the largest holders and the funds' net buying
                        inst = sorted(h.get('institutional') or [], key=lambda x: -(x.get('value_usd') or 0))[:10]
                        charts13 += SV.hbars([(display_name(x.get('manager')), x.get('value_usd')) for x in inst], money, f"Largest holders of {t} (13F)")
                        q13 = h.get('q13f') or {}
                        F = q13.get('fields') or []
                        if 'usd_net' in F and q13.get('periods'):
                            cov = q13.get('coverage') or []
                            top = max(cov) if cov else 0
                            pts = [(pq[:7], dict(zip(F, row)).get('usd_net')) for i, (pq, row) in enumerate(zip(q13['periods'], q13.get('rows') or []))
                                   if isinstance(row, (list, tuple)) and (not cov or cov[i] >= 0.5 * top)]
                            charts13 += SV.bars(pts[-8:], money, f"Funds' net buying of {t} by quarter (13F)", color=None,
                                                note='Value of shares 13F filers added minus the value they sold, each quarter (quarters with most filings in).')
                    if charts13:
                        charts13 = f"<h2>13F: who owns {e(t)} and who is buying</h2>" + charts13
                    try:
                        charts13 = SC.guidance_outlook(co['who_name'], read(os.path.join(site, 'data', 'guidance-record', f'{cik}.json')),
                                                       read(os.path.join(site, 'data', 'outlook', f'{cik}.json')), money) + charts13
                    except Exception as err:  # noqa: BLE001                 # one company's odd figures never stop the other pages
                        print(f"  {t} guidance charts: skipped ({type(err).__name__}: {err})")
                    block = (f'<section class="seo-more-main">{charts13}<h2>More on {e(t)}</h2><ul class="seo-list">'
                             + ''.join(f"<li><a href='{k}/'>{e(LINK[k](co['who_name']))}</a></li>" for k, l, _ in TOPICS if k in have) + '</ul></section>')
                    open(main, 'w', encoding='utf-8').write(txt.replace('</main>', block + '</main>', 1))
            except Exception as err:  # noqa: BLE001
                print(f"  {t} company-page block: skipped ({type(err).__name__}: {err})")
        except Exception as err:  # noqa: BLE001              # one company never stops the rest (and the sitemap)
            print(f"  {r.get('ticker') or r.get('cik')}: topic pages skipped ({type(err).__name__}: {err})")
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">']
    sm += [f'<url><loc>{xesc(u)}</loc><lastmod>{m}</lastmod>' + (f'<image:image><image:loc>{xesc(pics[u])}</image:loc></image:image>' if u in pics else '') + '</url>' for u, m in urls]
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
