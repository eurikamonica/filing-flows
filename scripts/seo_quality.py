"""Earnings quality score: one number from 0 to 100 per company, with the reasons, from the quality research module.

    data/quality-score.json           every scored company: score, grade, the points by component, the reasons
    c/<slug>/earnings-quality/        the score, what earned and lost points, the components against the universe
    disclosures/earnings-quality/     the ranking: highest and lowest, by sector; the Beneish flags and the biggest non-GAAP gaps
    sitemap-quality.xml

The score weighs eight signs that reported profit is (or is not) backed by cash and free of the markers of managed
earnings, each scored against the whole universe (a percentile) or on its published scale:
    accruals        (net income − operating cash flow) / assets: the lower, the more of the profit is cash            20
    discretionary   the modified Jones model's unexplained accruals, size either way                                  10
    beneish         Beneish M-score: −2.22 and below clean, −1.78 and above flagged                                   15
    dechow          Dechow F-score: 1 is normal, above 1.85 raised, above 2.45 high                                   15
    montier         Montier C-score: checks failed out of those possible                                              15
    piotroski       Piotroski F-score out of nine                                                                     10
    nongaap         the gap between adjusted and GAAP earnings, as a share of the adjusted figure                     10
    smoothness      σ(ROA) / σ(cash flow / assets): profit far steadier than cash is a mark of smoothing               5
A missing component drops its weight and the rest is rescaled, so a bank (no Altman or Beneish) is scored on what applies.
Research: disclosures/data/research/quality/index.json (disclosures/app/quality.py). Not investment advice.

    python scripts/seo_quality.py --site _site
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

e, display_name = seo.e, seo.display_name
WEIGHTS = {'accruals': 20, 'discretionary': 10, 'beneish': 15, 'dechow': 15, 'montier': 15, 'piotroski': 10, 'nongaap': 10, 'smoothness': 5}
LABEL = {'accruals': 'Accruals', 'discretionary': 'Discretionary accruals', 'beneish': 'Beneish M-score', 'dechow': 'Dechow F-score', 'montier': 'Montier C-score',
         'piotroski': 'Piotroski F-score', 'nongaap': 'Non-GAAP gap', 'smoothness': 'Earnings smoothness'}
DISCLAIMER = ("<p class='muted'>Computed from the companies’ own XBRL filings (latest fiscal year) by published formulas; a statistical screen, not an audit or an "
              "accusation. A low score means the reported profit shows more of the markers of managed or low-quality earnings than its peers. Not investment advice.</p>")


def read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def pct_rank(values, lower_better=True):
    """{index: percentile 0..1 (1 = best)} for the non-None values"""
    xs = sorted((v, i) for i, v in enumerate(values) if v is not None)
    n = len(xs)
    out = {}
    for k, (v, i) in enumerate(xs):
        p = k / (n - 1) if n > 1 else 0.5
        out[i] = 1 - p if lower_better else p
    return out


def components(r, ranks, i):
    """{component: (score 0..1, text)} for one row; a component is left out when its input is missing"""
    out = {}
    a = r.get('accruals')
    if a is not None and i in ranks['accruals']:
        s = ranks['accruals'][i]
        # lower is better: "lower than 93% of companies"; a negative figure stays "backed by cash" even when most are lower
        out['accruals'] = (s, f"accruals of {100 * a:+.1f}% of assets, {'lower' if s >= 0.5 else 'higher'} than {100 * (s if s >= 0.5 else 1 - s):.0f}% of companies"
                              + (' (profit backed by cash)' if a < -0.02 else ' (profit running ahead of cash)' if a > 0.05 else ''))
    da = r.get('da')
    if da is not None and i in ranks['discretionary']:
        s = ranks['discretionary'][i]
        out['discretionary'] = (s, f"discretionary accruals of {100 * da:+.1f}% of assets (modified Jones), {'smaller' if s >= 0.5 else 'larger'} than most")
    m = r.get('m_score')
    if m is not None:
        s = clamp((-1.78 - m) / 0.44)                                   # −2.22 → 1, −1.78 → 0
        out['beneish'] = (s, f"Beneish M-score {m:.2f}: {'flagged (above −1.78)' if m > -1.78 else 'clean (below −2.22)' if m < -2.22 else 'in the grey zone'}")
    f = r.get('dechow_f')
    if f is not None:
        s = clamp((2.45 - f) / 1.45)                                    # 1.0 → 1, 2.45 → 0
        out['dechow'] = (s, f"Dechow F-score {f:.2f} ({r.get('dechow_band') or ('normal' if f < 1 else 'raised')})")
    c, cn = r.get('c_score'), r.get('c_n')
    if c is not None and cn:
        s = (cn - c) / cn
        out['montier'] = (s, f"Montier C-score {c} of {cn} checks failed")
    p, pn = r.get('f_score'), r.get('f_n')
    if p is not None and pn:
        s = p / pn
        out['piotroski'] = (s, f"Piotroski F-score {p} of {pn}")
    g = r.get('ng_gap')
    if g is not None:
        s = clamp(1 - abs(g) / 0.3)
        out['nongaap'] = (s, (f"adjusted earnings {abs(100 * g):.0f}% {'above' if g < 0 else 'below'} GAAP" if abs(g) < 10          # a gap beyond ten times the
                              else f"adjusted earnings {'far above' if g < 0 else 'far below'} GAAP (more than ten times apart)")  # adjusted figure: no percentage
                          if abs(g) >= 0.005 else 'adjusted and GAAP earnings agree')
    sm = r.get('smooth')
    if sm is not None:
        s = clamp((sm - 0.2) / 0.5) if sm < 0.7 else 1.0
        out['smoothness'] = (s, f"profit {'far ' if sm < 0.35 else ''}steadier than cash flow (smoothness {sm:.2f})" if sm < 0.7 else f"profit about as variable as cash flow (smoothness {sm:.2f})")
    return out


def score_all(ix):
    F = ix.get('fields') or []
    rows = [dict(zip(F, x)) for x in ix.get('rows') or []]
    ranks = {'accruals': pct_rank([r.get('accruals') for r in rows]), 'discretionary': pct_rank([abs(r['da']) if r.get('da') is not None else None for r in rows])}
    out = []
    for i, r in enumerate(rows):
        comp = components(r, ranks, i)
        if len(comp) < 4:
            continue
        wt = sum(WEIGHTS[k] for k in comp)
        pts = {k: (WEIGHTS[k] * s * 100 / wt, WEIGHTS[k] * 100 / wt, txt) for k, (s, txt) in comp.items()}
        score = round(sum(p for p, _, _ in pts.values()))
        out.append({'ticker': r.get('ticker'), 'cik': r.get('cik'), 'name': r.get('name'), 'sector': r.get('sector'), 'mcap': r.get('mcap'), 'score': score,
                    'grade': 'A' if score >= 80 else 'B' if score >= 65 else 'C' if score >= 50 else 'D' if score >= 35 else 'E',
                    'parts': {k: [round(p, 1), round(w, 1), txt] for k, (p, w, txt) in pts.items()}, 'm_flag': bool(r.get('m_flag')), 'ng_gap': r.get('ng_gap'), 'growth': r.get('growth')})
    out.sort(key=lambda x: -x['score'])
    n = len(out)
    for k, x in enumerate(out):
        x['rank'] = k + 1
        x['pctl'] = round(1 - k / (n - 1), 3) if n > 1 else 0.5
    return out


def reasons(x):
    """the components by points lost, as sentences"""
    parts = sorted(x['parts'].items(), key=lambda kv: kv[1][1] - kv[1][0], reverse=True)
    lost = [(k, p, w, t) for k, (p, w, t) in parts if w - p >= 2]
    won = [(k, p, w, t) for k, (p, w, t) in parts if w - p < 2]
    return lost, won


def page_for(x, slug, base, universe, has_cf=True):
    name = display_name(x.get('name'))
    t = x.get('ticker') or ''
    lost, won = reasons(x)
    sec = [y for y in universe if y.get('sector') == x.get('sector')]
    sec_rank = sorted(sec, key=lambda y: -y['score']).index(x) + 1 if x in sec else None
    lead = (f"{name} ({t}) scores {x['score']} of 100 for earnings quality, grade {x['grade']}: rank {x['rank']} of {len(universe)} companies"
            + (f" and {sec_rank} of {len(sec)} in {x['sector']}" if sec_rank and x.get('sector') else '') + '. '
            + ('It loses the most points on ' + ', '.join(t for _, _, _, t in lost[:3]) + '. ' if lost else 'No component costs it more than a point or two. ')
            + ('It earns full or near-full marks for ' + ', '.join(t for _, _, _, t in won[:3]) + '.' if won else '')
            + (f" Revenue grew {100 * x['growth']:.0f}% in the year: fast growth raises accruals, the Beneish and Dechow scores and the C-score by construction, so a growing company scores lower than a steady one with the same accounting." if (x.get('growth') or 0) >= 0.3 else ''))
    tbl = ("<div class='tbl-wrap'><table><thead><tr><th>Component</th><th>What the filings show</th><th class='num'>Points</th><th class='num'>Of</th></tr></thead><tbody>"
           + ''.join(f"<tr><td>{e(LABEL[k])}</td><td>{e(txt)}</td><td class='num {'up' if p >= 0.8 * w else 'down' if p < 0.4 * w else ''}'>{p:.0f}</td><td class='num muted'>{w:.0f}</td></tr>"
                     for k, (p, w, txt) in sorted(x['parts'].items(), key=lambda kv: -kv[1][1])) + '</tbody></table></div>')
    chart = SV.hbars([(LABEL[k], 100 * p / w) for k, (p, w, _) in x['parts'].items() if w], lambda v: f"{v:.0f}%", f"{t}: share of the available points, by component", n=8)
    url = f"{base}/c/{slug}/earnings-quality/"
    title = f"{name} ({t}) Earnings Quality Score: {x['score']}/100, Grade {x['grade']}"
    body = (f"<p class='crumbs'><a href='../../../'>Filing Flows</a> › <a href='../../'>Companies</a> › <a href='../'>{e(name)}</a> › Earnings quality</p>"
            f"<h1>{e(name)} earnings quality score</h1><p class='muted'>How much of the reported profit is backed by cash, and how many markers of managed earnings the filings show</p>"
            f"<p class='seo-hl {'up' if x['score'] >= 65 else 'down' if x['score'] < 50 else ''}'><span>Score</span><b>{x['score']} / 100</b> · grade {e(x['grade'])} · rank {x['rank']} of {len(universe)}</p>"
            f"<p class='lead'>{e(lead)}</p><h2 id='parts'>What earned and lost points</h2>{tbl}{chart}"
            "<h2 id='how'>How the score is built</h2><div class='seo-note'><p>Eight published measures, each scored against the whole universe or on its own scale and weighted: "
            "accruals 20, discretionary accruals 10, Beneish M 15, Dechow F 15, Montier C 15, Piotroski F 10, the non-GAAP gap 10, smoothness 5. "
            "A measure that cannot be computed (Beneish for a bank, say) drops out and the rest is rescaled, so every company is scored on what applies to it.</p></div>"
            f"<p><a class='seo-cta' href='../../../disclosures/earnings-quality/'>Every company ranked →</a> <a href='../../../disclosures/#quality'>The full quality workbench, live →</a> "
            + (f"<a href='../cash-flow/'>{e(name)}: cash flow →</a>" if has_cf else '') + f"</p>{DISCLAIMER}")
    ld = {'@context': 'https://schema.org', '@graph': [
        {'@type': 'BreadcrumbList', 'itemListElement': [{'@type': 'ListItem', 'position': 1, 'name': 'Filing Flows', 'item': base + '/'},
                                                         {'@type': 'ListItem', 'position': 2, 'name': name, 'item': f"{base}/c/{slug}/"},
                                                         {'@type': 'ListItem', 'position': 3, 'name': 'Earnings quality', 'item': url}]},
        {'@type': 'FAQPage', 'mainEntity': [{'@type': 'Question', 'name': f"How good is the quality of {name}'s earnings?", 'acceptedAnswer': {'@type': 'Answer', 'text': lead}}]},
        {'@type': 'WebPage', 'name': title, 'url': url, 'description': lead[:300]}]}
    return url, seo.page(seo.fit(title), lead[:300], url, body, 3, base + '/og.png', ld)


def index_page(site, base, scored, slugs):
    L = lambda x: (f"<a href='../../c/{slugs[x['cik']]}/earnings-quality/'><b>{e(x['ticker'])}</b></a>" if x['cik'] in slugs else f"<b>{e(x['ticker'])}</b>") + f" {e(display_name(x['name']))}"
    row = lambda x: [L(x), e(x.get('sector') or ''), f"<b>{x['score']}</b>", e(x['grade']), e('; '.join(t for _, _, _, t in reasons(x)[0][:2]) or '—')]
    T = lambda rows: "<div class='tbl-wrap'><table><thead><tr><th>Company</th><th>Sector</th><th class='num'>Score</th><th>Grade</th><th>Loses points on</th></tr></thead><tbody>" + ''.join(f"<tr>{''.join(f'<td>{c}</td>' for c in r)}</tr>" for r in rows) + '</tbody></table></div>'
    big = [x for x in scored if (x.get('mcap') or 0) >= 10e9]
    best, worst = big[:30], sorted(big, key=lambda x: x['score'])[:30]
    flagged = [x for x in scored if x.get('m_flag') and (x.get('mcap') or 0) >= 2e9][:30]
    gaps = sorted([x for x in scored if x.get('ng_gap') is not None and (x.get('mcap') or 0) >= 2e9], key=lambda x: x['ng_gap'])[:25]
    by_sec = {}
    for x in scored:
        by_sec.setdefault(x.get('sector') or 'other', []).append(x['score'])
    grades = {g: sum(1 for x in scored if x['grade'] == g) for g in 'ABCDE'}
    lead = (f"{len(scored):,} companies scored 0–100 on eight published measures of earnings quality: accruals, discretionary accruals, Beneish M, Dechow F, Montier C, Piotroski F, "
            f"the non-GAAP gap and smoothness. {grades['A']:,} grade A, {grades['B']:,} B, {grades['C']:,} C, {grades['D']:,} D and {grades['E']:,} E. "
            f"The median score is {sorted(x['score'] for x in scored)[len(scored) // 2]}.")
    body = (f"<p class='crumbs'><a href='../../'>Filing Flows</a> › <a href='../'>Disclosures</a> › Earnings quality</p><h1>Earnings quality scores: every company, 0 to 100</h1>"
            f"<p class='lead'>{e(lead)}</p>"
            + SV.hbars([(s, sum(v) / len(v)) for s, v in sorted(by_sec.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]))], lambda v: f"{v:.0f}", 'Average score by sector', n=12)
            + "<nav class='seo-toc'><a href='#best'>Highest</a><a href='#worst'>Lowest</a><a href='#beneish'>Beneish flags</a><a href='#gaps'>Non-GAAP gaps</a></nav>"
            f"<h2 id='best'>Highest scores (market value $10B+)</h2>{T(map(row, best))}<h2 id='worst'>Lowest scores ($10B+)</h2>{T(map(row, worst))}")
    if flagged:
        body += f"<h2 id='beneish'>Beneish M-score flagged (above −1.78, $2B+)</h2><p class='muted'>A statistical screen for the profile of past manipulators, not an accusation; most flagged companies are simply growing fast or changing shape.</p>{T(map(row, flagged))}"
    if gaps:
        body += ("<h2 id='gaps'>Largest non-GAAP gaps ($2B+)</h2><p class='muted'>Adjusted earnings furthest above GAAP, as a share of the adjusted figure.</p>"
                 "<div class='tbl-wrap'><table><thead><tr><th>Company</th><th class='num'>Adjusted above GAAP</th><th class='num'>Score</th></tr></thead><tbody>"
                 + ''.join(f"<tr><td>{L(x)}</td><td class='num'>{abs(100 * x['ng_gap']):.0f}%</td><td class='num'>{x['score']}</td></tr>" for x in gaps) + '</tbody></table></div>')
    body += f"<p><a class='seo-cta' href='../#quality'>The quality workbench, live: every measure, every company →</a></p>{DISCLAIMER}"
    url = f"{base}/disclosures/earnings-quality/"
    ld = {'@context': 'https://schema.org', '@graph': [
        {'@type': 'BreadcrumbList', 'itemListElement': [{'@type': 'ListItem', 'position': 1, 'name': 'Filing Flows', 'item': base + '/'},
                                                         {'@type': 'ListItem', 'position': 2, 'name': 'Disclosures', 'item': base + '/disclosures/'},
                                                         {'@type': 'ListItem', 'position': 3, 'name': 'Earnings quality', 'item': url}]},
        {'@type': 'Dataset', 'name': 'Earnings quality scores', 'description': lead[:500], 'url': url, 'creator': {'@type': 'Organization', 'name': 'Filing Flows', 'url': base + '/'}, 'isAccessibleForFree': True}]}
    os.makedirs(os.path.join(site, 'disclosures', 'earnings-quality'), exist_ok=True)
    open(os.path.join(site, 'disclosures', 'earnings-quality', 'index.html'), 'w', encoding='utf-8').write(seo.page(
        'Earnings Quality Scores: Every Company 0–100 on Accruals, Beneish, Dechow and the Non-GAAP Gap | Filing Flows', lead[:300], url, body, 2, base + '/og.png', ld))
    return url


def link_from_company(site, slug):
    p = os.path.join(site, 'c', slug, 'index.html')
    if not os.path.exists(p):
        return
    t = open(p, encoding='utf-8').read()
    if 'earnings-quality/' in t:
        return
    open(p, 'w', encoding='utf-8').write(t.replace('<nav class="seo-toc" aria-label="On this page">', '<nav class="seo-toc" aria-label="On this page"><a href="earnings-quality/">Quality score</a>', 1))


def write(site, base, today=None):
    base = base.rstrip('/')
    ix = read(os.path.join(site, 'disclosures', 'data', 'research', 'quality', 'index.json'))
    if not ix:
        print('quality score: no research/quality/index.json')
        return 0
    scored = score_all(ix)
    if not scored:
        return 0
    cix = read(os.path.join(site, 'data', 'index.json')) or {}
    rows = cix.get('companies') if isinstance(cix, dict) else cix
    slugs = {int(r['cik']): seo.slug_for(r) for r in rows or [] if r.get('cik') and os.path.exists(os.path.join(site, 'c', seo.slug_for(r), 'index.html'))}
    os.makedirs(os.path.join(site, 'data'), exist_ok=True)
    with open(os.path.join(site, 'data', 'quality-score.json'), 'w', encoding='utf-8') as f:
        json.dump({'generated_at': (today or dt.date.today()).isoformat(), 'weights': WEIGHTS, 'n': len(scored),
                   'fields': ['ticker', 'cik', 'name', 'sector', 'score', 'grade', 'rank', 'lost', 'won'],
                   'rows': [[x['ticker'], x['cik'], x['name'], x['sector'], x['score'], x['grade'], x['rank'],
                             [t for _, _, _, t in reasons(x)[0][:3]], [t for _, _, _, t in reasons(x)[1][:3]]] for x in scored]}, f, separators=(',', ':'))
    urls = []
    for x in scored:
        slug = slugs.get(x.get('cik'))
        if not slug:
            continue
        try:
            url, doc = page_for(x, slug, base, scored, os.path.exists(os.path.join(site, 'c', slug, 'cash-flow', 'index.html')))
        except Exception as err:  # noqa: BLE001
            print(f"quality page skipped ({x.get('ticker')}): {err}")
            continue
        d = os.path.join(site, 'c', slug, 'earnings-quality')
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'index.html'), 'w', encoding='utf-8').write(doc)
        link_from_company(site, slug)
        urls.append(url)
    urls.insert(0, index_page(site, base, scored, slugs))
    today_s = str(ix.get('asof') or (today or dt.date.today()).isoformat())[:10]     # the fundamentals' date: changes when they do
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f'<url><loc>{xesc(u)}</loc><lastmod>{today_s}</lastmod></url>' for u in urls]
    sm.append('</urlset>')
    open(os.path.join(site, 'sitemap-quality.xml'), 'w', encoding='utf-8').write('\n'.join(sm))
    robots = os.path.join(site, 'robots.txt')
    txt = open(robots).read() if os.path.exists(robots) else f'User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n'
    if 'sitemap-quality.xml' not in txt:
        open(robots, 'w').write(txt.rstrip('\n') + f'\nSitemap: {base}/sitemap-quality.xml\n')
    return len(urls)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', default='_site')
    ap.add_argument('--site-url', default=os.environ.get('SITE_URL', '') or 'https://filing-flows.com')
    a = ap.parse_args()
    m = re.search(r'https?://[^\s"]+', a.site_url or '')
    print('earnings quality pages:', write(a.site, m.group(0) if m else 'https://filing-flows.com'))
