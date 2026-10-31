"""Daily pages for search engines from the Disclosure Hub's data: the lists people search for by day, each dated, with
the newest first, every company linked to its own pages.

    daily/                        today's lists, the top lines of each
    daily/insider-buying/         open-market purchases by officers, directors and 10% owners (Form 4, code P)
    daily/insider-selling/        their sales (code S), marked when under a 10b5-1 plan
    daily/congress-trades/        stock trades disclosed by members of Congress and other officials
    daily/guidance-changes/       companies that raised, lowered, reaffirmed or withdrew guidance (8-K earnings releases)
    daily/takeover-rumors/        headlines, 8-Ks and 13Ds about sales, approaches and take-private offers
    daily/earnings-calendar/      who reports in the next two weeks, with the analysts' EPS and revenue estimates
    daily/activist-stakes/        new Schedule 13D filings: holders above 5% who may seek to influence the company
    sitemap-daily.xml (robots.txt, IndexNow)

    python scripts/seo_daily.py --site _site --site-url https://filing-flows.com
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

e, fdate, display_name = seo.e, seo.fdate, seo.display_name
GUIDE = {'raised': '▲ raised', 'lowered': '▼ lowered', 'narrowed': 'narrowed', 'widened': 'widened', 'reaffirmed': 'reaffirmed', 'initiated': 'initiated',
         'withdrawn': 'withdrawn', 'mixed': 'raised and lowered', 'updated': 'updated'}
KIND = {'news': 'News', '8-K': '8-K', '8-K deal': '8-K', '13D': '13D', 'deal': 'Agreed deal', 'SC 13E3': 'Going private', 'DEFM14A': 'Merger proxy', 'SC 14D9': 'Tender offer'}


def read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def money(v):
    if v is None:
        return '—'
    a = abs(v)
    return f"${a / 1e9:.2f}B" if a >= 1e9 else f"${a / 1e6:.1f}M" if a >= 1e6 else f"${a / 1e3:.0f}K" if a >= 1e3 else f"${a:,.0f}"


class Links:
    """Ticker → the company's page (and a topic page under it) when the site has one."""
    def __init__(self, site):
        ix = read(os.path.join(site, 'data', 'index.json')) or {}
        self.slug = {}
        for r in (ix.get('companies') if isinstance(ix, dict) else ix) or []:
            if r.get('ticker'):
                self.slug.setdefault(r['ticker'].upper(), seo.slug_for(r))
        self.site = site

    def __call__(self, ticker, label=None, topic=None):
        t = (ticker or '').upper()
        s = self.slug.get(t)
        text = e(label or t or '—')
        if not s:
            return f"<b>{text}</b>"
        sub = f"{topic}/" if topic and os.path.exists(os.path.join(self.site, 'c', s, topic, 'index.html')) else ''
        return f"<a href='../../c/{s}/{sub}'><b>{text}</b></a>"


def by_date(rows, key):
    out = {}
    for r in rows:
        out.setdefault(key(r) or '', []).append(r)
    return sorted(out.items(), reverse=True)


def table(head, rows):
    return (f"<div class='tbl-wrap'><table><thead><tr>{''.join(f'<th>{e(h)}</th>' for h in head)}</tr></thead><tbody>"
            + ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in rows) + '</tbody></table></div>')


# ---------------------------------------------------------------- the lists: (slug, title, h1, lead, body, top lines, n)
def insiders(hub, link, today, code):
    d = read(os.path.join(hub, 'market', 'insiders.json')) or {}
    since = (today - dt.timedelta(days=14)).isoformat()
    rows = [r for r in d.get('latest') or [] if r.get('code') == code and (r.get('date') or '') >= since and r.get('ticker')
            and (r.get('value') or 0) < 1.5e9]            # a billion-dollar 'purchase' by one person is a misread filing, not news
    if not rows:
        return None
    buy = code == 'P'
    tot = sum(r.get('value') or 0 for r in rows)
    big = sorted(rows, key=lambda r: -(r.get('value') or 0))[:3]
    word = 'bought' if buy else 'sold'
    lead = (f"Company insiders {word} {money(tot)} of their own companies' shares in {len(rows)} open-market trades over the last two weeks. "
            + 'The largest: ' + '; '.join(f"{r.get('insider')} ({r.get('role') or 'insider'}) {word} {money(r.get('value'))} of {r.get('issuer')} ({r['ticker']})" for r in big) + '.')
    body = ''
    for day, rs in by_date(rows, lambda r: r.get('date')):
        body += f"<h2>{e(fdate(day))}</h2>" + table(['Company', 'Insider', 'Role', 'Value', 'Price', 'Shares'], [
            [link(r['ticker'], f"{r['ticker']} · {r.get('issuer')}", 'who-owns'), e(r.get('insider')), e(r.get('role') or r.get('title') or ''),
             e(money(r.get('value'))) + (" <span class='muted'>10b5-1 plan</span>" if r.get('plan_10b5_1') else ''), e(f"${r['price']:,.2f}" if r.get('price') else '—'),
             e(f"{r['shares']:,.0f}" if r.get('shares') else '—')] for r in sorted(rs, key=lambda r: -(r.get('value') or 0))])
    slug = 'insider-buying' if buy else 'insider-selling'
    title = (f"Insider buying today ({fdate(today.isoformat())}): the largest open-market purchases by executives and directors" if buy else
             f"Insider selling today ({fdate(today.isoformat())}): the largest share sales by executives and directors")
    tops = [f"{r['ticker']}: {r.get('insider')} {word} {money(r.get('value'))}" for r in big]
    return slug, title, 'Insider buying' if buy else 'Insider selling', lead, body, tops, len(rows)


def congress(hub, link, today):
    d = read(os.path.join(hub, 'market', 'officials-trades.json')) or {}
    since = (today - dt.timedelta(days=45)).isoformat()
    rows = [r for r in d.get('trades') or [] if (r.get('date') or '') >= since and r.get('ticker')]
    if not rows:
        return None
    buys = [r for r in rows if r.get('type') == 'purchase']
    people = len({r.get('person') for r in rows})
    lead = (f"{people} members of Congress and other officials disclosed {len(rows)} stock trades made in the last 45 days: {len(buys)} purchases and "
            f"{len(rows) - len(buys)} sales. Disclosures are filed up to 45 days after the trade; amounts are given in ranges.")
    body = ''
    for day, rs in by_date(rows, lambda r: r.get('date')):
        body += f"<h2>{e(fdate(day))}</h2>" + table(['Company', 'Who', 'Trade', 'Amount', 'Disclosed'], [
            [link(r['ticker'], r['ticker'], 'who-owns'), e(r.get('person')) + f" <span class='muted'>{e(r.get('jurisdiction') or '')}</span>", e(r.get('type')),
             e(f"{money(r.get('amount_min'))}–{money(r.get('amount_max'))}"), e(r.get('filed_date') or '') + (f" · <a href='{e(r.get('source_url'))}' rel='nofollow'>filing</a>" if r.get('source_url') else '')]
            for r in rs[:60]])
    tops = [f"{r['ticker']}: {r.get('person')} {r.get('type')} ({r.get('date')})" for r in sorted(rows, key=lambda r: r.get('date') or '', reverse=True)[:3]]
    return ('congress-trades', f"Congress stock trades today ({fdate(today.isoformat())}): what members of Congress bought and sold", 'Congress stock trades',
            lead, body, tops, len(rows))


def guidance(hub, link, today):
    d = read(os.path.join(hub, 'market', 'events8k.json')) or {}
    since = (today - dt.timedelta(days=14)).isoformat()
    rows = [r for r in d.get('rows') or [] if r.get('guidance') and r.get('ticker') and (r.get('filed') or '') >= since]
    if not rows:
        return None
    up = [r for r in rows if r['guidance'] == 'raised']
    down = [r for r in rows if r['guidance'] in ('lowered', 'withdrawn')]
    lead = (f"{len(rows)} companies updated their guidance in earnings releases over the last two weeks: {len(up)} raised it and {len(down)} lowered or withdrew it."
            + (' Raised: ' + ', '.join(r['ticker'] for r in up[:8]) + '.' if up else '') + (' Lowered: ' + ', '.join(r['ticker'] for r in down[:6]) + '.' if down else ''))
    body = ''
    for day, rs in by_date(rows, lambda r: r.get('filed')):
        body += f"<h2>{e(fdate(day))}</h2>" + table(['Company', 'Guidance', 'Release'], [
            [link(r['ticker'], r['ticker'], 'guidance'), e(GUIDE.get(r['guidance'], r['guidance'])),
             (f"<a href='{e(r.get('url'))}' rel='nofollow'>{e(r.get('headline') or r.get('company') or '8-K')}</a>" if r.get('url') else e(r.get('headline') or ''))]
            for r in sorted(rs, key=lambda r: (r['guidance'] != 'raised', r['ticker']))])
    tops = [f"{r['ticker']} {GUIDE.get(r['guidance'], r['guidance'])}" for r in (up + down)[:4]]
    return ('guidance-changes', f"Guidance raised and lowered today ({fdate(today.isoformat())}): companies changing their outlook", 'Guidance changes',
            lead, body, tops, len(rows))


def rumors(hub, link, today):
    d = read(os.path.join(hub, 'research', 'lbo', 'rumors.json')) or {}
    since = (today - dt.timedelta(days=14)).isoformat()
    rows = [r for r in d.get('rows') or [] if (r[0] or '') >= since and r[3] in ('news', '8-K', '13D', 'deal', 'SC 13E3', 'DEFM14A', 'SC 14D9') and not (len(r) > 7 and r[7] == 'buyer')]
    if not rows:
        return None
    cos = list(dict.fromkeys(r[1] for r in rows))
    lead = f"{len(cos)} listed companies were the subject of takeover talk or deal filings in the last two weeks: " + ', '.join(cos[:12]) + '. A headline is not a deal; most reported talks end without one.'
    body = ''
    for day, rs in by_date(rows, lambda r: r[0]):
        seen, out = set(), []
        for r in rs:
            if (r[1], r[3]) in seen and r[3] == 'news':
                continue
            seen.add((r[1], r[3]))
            out.append([link(r[1], r[1], 'takeover'), e(KIND.get(r[3], r[3])), (f"<a href='{e(r[6])}' rel='nofollow'>{e(r[4])}</a>" if r[6] else e(r[4]))
                        + (f" <span class='muted'>— {e(r[5])}</span>" if r[5] and r[3] == 'news' else '')])
        body += f"<h2>{e(fdate(day))}</h2>" + table(['Company', 'Kind', 'What'], out[:40])
    return ('takeover-rumors', f"Takeover rumors and buyout news today ({fdate(today.isoformat())}): companies exploring a sale or receiving offers",
            'Takeover rumors', lead, body, [f"{r[1]}: {r[4][:90]}" for r in rows[:3]], len(cos))


def calendar(hub, link, today):
    d = read(os.path.join(hub, 'research', 'earnings', 'index.json')) or {}
    F = d.get('fields') or []
    if not F:
        return None
    rows = [dict(zip(F, r)) for r in d.get('rows') or []]
    end = (today + dt.timedelta(days=14)).isoformat()
    rows = [r for r in rows if today.isoformat() <= (r.get('report_date') or '') <= end]
    if not rows:
        return None
    first = sorted(rows, key=lambda r: r['report_date'])
    lead = (f"{len(rows)} companies report earnings in the next two weeks. Coming up first: "
            + ', '.join(f"{r['ticker']} ({fdate(r['report_date'])})" for r in first[:8]) + '.')
    body = ''
    for day, rs in sorted(by_date(rows, lambda r: r.get('report_date')), key=lambda x: x[0]):
        body += f"<h2>{e(fdate(day))}</h2>" + table(['Company', 'EPS estimate', 'Analysts', 'Beat rate', 'Beat odds (model)'], [
            [link(r['ticker'], f"{r['ticker']} · {display_name(r.get('name'))}", 'earnings-date'), e(f"${r['eps']:.2f}" if r.get('eps') is not None else '—'),
             e(f"{r['n']:.0f}" if r.get('n') else '—'), e(f"{round(100 * r['beat_rate'])}%" if r.get('beat_rate') is not None else '—'),
             e(f"{round(100 * r['model'])}%" if isinstance(r.get('model'), (int, float)) else '—')] for r in sorted(rs, key=lambda r: r['ticker'])[:80]])
    return ('earnings-calendar', f"Earnings calendar this week and next ({fdate(today.isoformat())}): who reports, EPS estimates and beat odds", 'Earnings calendar',
            lead, body, [f"{r['ticker']} reports {fdate(r['report_date'])}" for r in first[:3]], len(rows))


def stakes(hub, link, today):
    d = read(os.path.join(hub, 'market', 'stakes.json')) or {}
    since = (today - dt.timedelta(days=14)).isoformat()
    rows = [r for r in d.get('latest') or [] if str(r.get('form', '')).startswith('13D') and (r.get('filed') or '') >= since]
    if not rows:
        return None
    new = [r for r in rows if not r.get('amendment')]
    lead = (f"{len(rows)} Schedule 13D filings in the last two weeks, {len(new)} of them new: holders above 5% of a company who may seek to influence it. "
            + ('Largest new stakes: ' + '; '.join(f"{r.get('filer')} {r.get('percent')}% of {r.get('issuer')}" for r in sorted(new, key=lambda r: -(r.get('percent') or 0))[:3]) + '.' if new else ''))
    tick = lambda r: (r.get('ticker') or '')   # noqa: E731
    body = ''
    for day, rs in by_date(rows, lambda r: r.get('filed')):
        body += f"<h2>{e(fdate(day))}</h2>" + table(['Company', 'Holder', 'Stake', 'Filing', 'Purpose'], [
            [link(tick(r), r.get('issuer')) if tick(r) else e(r.get('issuer')), e(r.get('filer') or r.get('person')), e(f"{r.get('percent')}%" if r.get('percent') is not None else '—'),
             (f"<a href='{e(r.get('url'))}' rel='nofollow'>{e(r.get('form'))}</a>" if r.get('url') else e(r.get('form'))) + (' (amended)' if r.get('amendment') else ''),
             e((r.get('purpose') or '')[:160])] for r in rs[:50]])
    return ('activist-stakes', f"New 13D filings today ({fdate(today.isoformat())}): activist stakes above 5%", 'Activist stakes (13D)', lead, body,
            [f"{r.get('filer')} {r.get('percent')}% of {r.get('issuer')}" for r in new[:3]], len(rows))


def write(site, base, today=None):
    base = base.rstrip('/')
    today = today or dt.date.today()
    hub = os.path.join(site, 'disclosures', 'data')
    link = Links(site)
    made = []
    for fn in (lambda: insiders(hub, link, today, 'P'), lambda: insiders(hub, link, today, 'S'), lambda: congress(hub, link, today),
               lambda: guidance(hub, link, today), lambda: rumors(hub, link, today), lambda: calendar(hub, link, today), lambda: stakes(hub, link, today)):
        try:
            r = fn()
        except Exception as err:  # noqa: BLE001
            print(f'daily page skipped: {err}')
            r = None
        if r:
            made.append(r)
    urls = []
    for slug, title, short, lead, body, tops, n in made:
        url = f'{base}/daily/{slug}/'
        nav = ' · '.join(f"<b>{e(s_)}</b>" if s == slug else f"<a href='../{s}/'>{e(s_)}</a>" for s, _, s_, *_ in made)
        html = (f"<p class='crumbs'><a href='../../'>Filing Flows</a> › <a href='../'>Today</a> › {e(short)}</p><h1>{e(title.split(' (')[0])}</h1>"
                f"<p class='muted'>Updated {e(fdate(today.isoformat()))}</p><nav class='seo-more'>{nav}</nav><p class='lead'>{e(lead)}</p>{body}"
                f"<p><a class='seo-cta' href='../../disclosures/'>Every list, live, in Disclosures →</a></p>"
                "<p class='muted'>Read automatically from SEC filings (Form 4, 8-K, Schedule 13D), House and Senate disclosures and news headlines; errors are possible. Not investment advice.</p>")
        ld = {'@context': 'https://schema.org', '@graph': [
            {'@type': 'BreadcrumbList', 'itemListElement': [{'@type': 'ListItem', 'position': 1, 'name': 'Filing Flows', 'item': base + '/'},
                                                             {'@type': 'ListItem', 'position': 2, 'name': 'Today', 'item': base + '/daily/'},
                                                             {'@type': 'ListItem', 'position': 3, 'name': short, 'item': url}]},
            {'@type': 'WebPage', 'name': title, 'url': url, 'dateModified': today.isoformat(), 'description': lead[:300]}]}
        doc = seo.page(f"{title} | Filing Flows", lead[:300], url, html, 2, base + '/og.png', ld)
        os.makedirs(os.path.join(site, 'daily', slug), exist_ok=True)
        open(os.path.join(site, 'daily', slug, 'index.html'), 'w', encoding='utf-8').write(doc)
        urls.append(url)
    if made:
        cards = ''.join(f"<h2><a href='{slug}/'>{e(short)}</a> <span class='muted'>{n}</span></h2><ul class='seo-list'>" + ''.join(f"<li>{e(t)}</li>" for t in tops) + '</ul>'
                        for slug, _, short, _, _, tops, n in made)
        idx = (f"<p class='crumbs'><a href='../'>Filing Flows</a> › Today</p><h1>Today in the filings: {e(fdate(today.isoformat()))}</h1>"
               f"<p class='lead'>What insiders, members of Congress, activists and companies themselves disclosed: insider buying and selling, Congress stock trades, "
               f"guidance changes, takeover rumors, new 13D stakes and the earnings calendar — updated every day.</p>{cards}")
        url = f'{base}/daily/'
        open(os.path.join(site, 'daily', 'index.html'), 'w', encoding='utf-8').write(seo.page(
            f"Today in the filings ({fdate(today.isoformat())}): insider buying, Congress trades, guidance, takeover rumors | Filing Flows",
            'Every day: the largest insider purchases and sales, Congress stock trades, companies raising or lowering guidance, takeover rumors, new 13D stakes and who reports earnings next.',
            url, idx, 1, base + '/og.png'))
        urls.insert(0, url)
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f'<url><loc>{xesc(u)}</loc><lastmod>{today.isoformat()}</lastmod><changefreq>daily</changefreq></url>' for u in urls]
    sm.append('</urlset>')
    open(os.path.join(site, 'sitemap-daily.xml'), 'w', encoding='utf-8').write('\n'.join(sm))
    robots = os.path.join(site, 'robots.txt')
    txt = open(robots).read() if os.path.exists(robots) else f'User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n'
    if 'sitemap-daily.xml' not in txt:
        open(robots, 'w').write(txt.rstrip('\n') + f'\nSitemap: {base}/sitemap-daily.xml\n')
    return [m[0] for m in made]


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', default='_site')
    ap.add_argument('--site-url', default=os.environ.get('SITE_URL', '') or 'https://filing-flows.com')
    a = ap.parse_args()
    m = re.search(r'https?://[^\s"]+', a.site_url or '')
    made = write(a.site, m.group(0) if m else 'https://filing-flows.com')
    print(f"daily pages: {', '.join(made) or 'none'}")
