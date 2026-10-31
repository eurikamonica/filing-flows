"""Search pages about a company's history, from its own filings (data/c/<cik>.json) and its guidance record
(data/guidance-record/<cik>.json, scripts/guidance_board.cjs):

    c/<slug>/<quarter>/                    every quarter on file, for good: "NVIDIA second quarter fiscal 2027 results
                                           (Q2 FY27)" — the Sankey, the key lines with Q/Q and Y/Y, what changed, the filing
    c/<slug>/<quarter>-vs-<previous>/      quarter over quarter: every line against the quarter before, what drove it
    c/<slug>/<quarter>-vs-<year-ago>/      year over year: every line against the same quarter a year earlier
                                           (both for the latest two quarters)
    c/<slug>/<metric>/                     one figure quarter by quarter: gross margin, operating margin, net income,
                                           free cash flow, R&D, capex, and the largest revenue lines ("data-center-revenue")
    c/<slug>/guidance-history/             every guided period against what was reported: hit rate, misses, moves
    sitemap-quarters.xml, sitemap-periods.xml, sitemap-metrics.xml (robots.txt, IndexNow); a "History" block on c/<slug>/

    python scripts/seo_history.py --site _site --site-url https://filing-flows.com
"""
import argparse
import html as H
import json
import os
import re
import sys
from xml.sax.saxutils import escape as xesc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seo  # noqa: E402

e, display_name, slug_for, fdate = seo.e, seo.display_name, seo.slug_for, seo.fdate
PERIOD_PAGES = 2                   # quarters with Q/Q and Y/Y pages (the newest)


def read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def money(v):
    return '—' if v is None else (('−' if v < 0 else '') + f'${abs(v) / 1e12:.2f}T') if abs(v) >= 1e12 else seo.money(v)


def pc(v, d=0):
    return '—' if v is None else f'{v:+.{d}f}%'


def pts(v):
    return '—' if v is None else f'{v:+.1f} pts'


def qslug(label):
    return re.sub(r'[^a-z0-9]+', '-', (label or '').lower()).strip('-')


def year_ago(label):
    m = re.fullmatch(r'Q([1-4])\s+(FY)?(\d{2}|\d{4})', (label or '').strip())
    if not m:
        return None
    y = int(m[3]) - 1
    return f"Q{m[1]} {m[2] or ''}{y:02d}" if len(m[3]) == 2 else f"Q{m[1]} {m[2] or ''}{y}"


def nodes(q):
    """{id: (label, this, previous quarter, year ago)} of a quarter's Sankey."""
    return {n['id']: (H.unescape(n.get('name') or n.get('label') or n['id']), n.get('v'), n.get('q'), n.get('y')) for n in q.get('nodes') or []}


def chg(a, b):
    return (a / b - 1) * 100 if a is not None and b not in (None, 0) and b > 0 else None


def margin(n, k, i):
    r, x = n.get('revenue'), n.get(k)
    return 100 * x[i] / r[i] if r and x and r[i] and x[i] is not None else None


KEY = [('revenue', 'Revenue'), ('gp', 'Gross profit'), ('oi', 'Operating profit'), ('net', 'Net earnings'), ('ocf', 'Operating cash flow'), ('fcf', 'Free cash flow')]


def sankey_figure(cik, label, alt):
    """drawn in the browser from the company's data by seo-quarter.js (one shared script, not one per page)"""
    return (f"<figure class='seo-chart' id='sankey' data-src='../../../data/c/{e(cik)}.json' data-label='{e(label)}' aria-label='{e(alt)}'>"
            "<p class='muted'>Drawing the Sankey…</p></figure><script src='../../../sankey.js' defer></script><script src='../../../seo-quarter.js' defer></script>")


def first(s):
    """the first sentence ("$96.2B" keeps its decimal point)"""
    return re.split(r'(?<=\.)\s', s, maxsplit=1)[0]


def ld(base, crumbs, qa, modified=None):
    g = [{'@type': 'BreadcrumbList', 'itemListElement': [{'@type': 'ListItem', 'position': i + 1, 'name': n, 'item': u} for i, (n, u) in enumerate(crumbs)]}]
    if qa:
        g.append({'@type': 'FAQPage', 'mainEntity': [{'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}} for q, a in qa]})
    if modified:
        g.append({'@type': 'WebPage', 'name': crumbs[-1][0], 'url': crumbs[-1][1], 'dateModified': modified})
    return {'@context': 'https://schema.org', '@graph': g}


def faq(qa):
    return '<h2>Questions</h2>' + ''.join(f'<h3>{e(q)}</h3><p>{e(a)}</p>' for q, a in qa) if qa else ''


# ---------------------------------------------------------------- one quarter, for good
def quarter_page(r, c, i, base, slug, who, name, has_period):
    q = c['quarters'][i]
    lab = q.get('label')
    words = seo.period_words(lab)
    n = nodes(q)
    rev = n.get('revenue')
    if not rev or not rev[1]:
        return None
    h = q.get('headline') or {}
    yoy, qoq = chg(rev[1], rev[3]), chg(rev[1], rev[2])
    lead = f"{who} reported revenue of {money(rev[1])} for the {words} ({lab})" + (f", {pc(yoy)} from a year earlier" if yoy is not None else '') + (
        f" and {pc(qoq)} from the quarter before" if qoq is not None else '') + '.'
    om, nm = margin(n, 'oi', 1), margin(n, 'net', 1)
    if om is not None:
        lead += f" Operating margin was {om:.1f}%" + (f", net earnings {money(n['net'][1])} ({nm:.1f}% of revenue)" if nm is not None else '') + '.'
    rows = ''.join(f"<tr><td>{e(t)}</td><td class='num'>{e(money(n[k][1]))}</td><td class='num'>{e(pc(chg(n[k][1], n[k][2])))}</td><td class='num'>{e(pc(chg(n[k][1], n[k][3])))}</td></tr>"
                   for k, t in KEY if k in n and n[k][1] is not None)
    qs = c['quarters']
    prev_q = qs[i + 1] if i + 1 < len(qs) else None
    next_q = qs[i - 1] if i > 0 else None
    ya = year_ago(lab)
    navs = []
    if next_q:
        navs.append(f"<a href='../{qslug(next_q['label'])}/'>← {e(next_q['label'])}</a>")
    if prev_q:
        navs.append(f"<a href='../{qslug(prev_q['label'])}/'>{e(prev_q['label'])} →</a>")
    if has_period:
        if prev_q:
            navs.append(f"<a href='../{qslug(lab)}-vs-{qslug(prev_q['label'])}/'>{e(lab)} vs {e(prev_q['label'])} (Q/Q)</a>")
        if ya:
            navs.append(f"<a href='../{qslug(lab)}-vs-{qslug(ya)}/'>{e(lab)} vs {e(ya)} (Y/Y)</a>")
    analysis = ''.join(f'<p>{e(a)}</p>' for a in (q.get('analysis') or [])[:4])
    qa = [(f"What was {name}'s revenue in the {words}?", first(lead))]
    if om is not None:
        qa.append((f"Was {name} profitable in the {words}?", f"Operating profit was {money(n['oi'][1])} ({om:.1f}% of revenue)" + (f" and net earnings {money(n['net'][1])}." if 'net' in n and n['net'][1] is not None else '.')))
    url = f"{base}/c/{slug}/{qslug(lab)}/"
    body = (f"<p class='crumbs'><a href='../../../'>Filing Flows</a> › <a href='../'>{e(who)}</a> › {e(lab)}</p>"
            f"<h1>{e(who)} {e(words)} results ({e(lab)})</h1><p class='muted'>{e(q.get('form'))} filed {e(fdate(q.get('filed')))}</p>"
            f"<nav class='seo-more'>{' · '.join(navs)}</nav><p class='lead'>{e(lead)}</p>{sankey_figure(r['cik'], lab, f'{who} {lab} income statement Sankey')}"
            f"<div class='tbl-wrap'><table><thead><tr><th>{e(lab)}</th><th class='num'>Amount</th><th class='num'>Q/Q</th><th class='num'>Y/Y</th></tr></thead><tbody>{rows}</tbody></table></div>"
            + (f"<h2>What changed</h2>{analysis}" if analysis else '') + faq(qa)
            + f"<p><a class='seo-cta' href='../../../#c-{r['cik']}'>Open the interactive Sankey →</a></p>"
            + (f"<p class='muted'>Source: <a href='{e(q.get('doc_url'))}' rel='nofollow'>{e(name)} {e(q.get('form'))} on SEC EDGAR</a>.</p>" if q.get('doc_url') else ''))
    title = f"{who} {words} results ({lab}): revenue {money(rev[1])}" + (f", {pc(yoy)} Y/Y" if yoy is not None else '') + ' | Filing Flows'
    crumbs = [('Filing Flows', base + '/'), (who, f'{base}/c/{slug}/'), (f'{lab} results', url)]
    return url, (q.get('filed') or '')[:10] or None, seo.page(title, lead[:300], url, body, 3, base + '/og.png', ld(base, crumbs, qa, (q.get('filed') or '')[:10] or None))


# ---------------------------------------------------------------- quarter over quarter, year over year
def period_page(r, c, i, base, slug, who, name, mode):
    q = c['quarters'][i]
    lab = q.get('label')
    j = 2 if mode == 'qoq' else 3
    other = (c['quarters'][i + 1]['label'] if i + 1 < len(c['quarters']) else None) if mode == 'qoq' else year_ago(lab)
    if not other:
        return None
    n = nodes(q)
    rev = n.get('revenue')
    if not rev or not rev[1] or not rev[j]:
        return None
    what = 'quarter over quarter' if mode == 'qoq' else 'year over year'
    d = rev[1] - rev[j]
    lead = f"{name}'s revenue {'rose' if d >= 0 else 'fell'} {money(abs(d))} ({pc(chg(rev[1], rev[j]))}) from {money(rev[j])} in {other} to {money(rev[1])} in {lab}."
    movers = sorted(((k, v) for k, v in n.items() if k not in ('revenue',) and v[1] is not None and v[j] is not None
                     and any(ln['s'] == k and ln['t'] == 'revenue' or ln['t'] == k and ln['s'] in n for ln in q.get('links') or [])
                     and k not in ('gp', 'cor', 'oi', 'opex', 'net', 'tax', 'pretax', 'ocf', 'fcf', 'capex', 'da', 'sbc', 'wc_out', 'nonop_in', 'nonop_out')),
                    key=lambda kv: -abs(kv[1][1] - kv[1][j]))
    segs = [(k, v) for k, v in movers if any(ln['s'] == k and ln['t'] in ('revenue',) or (ln['s'] == k and str(ln['t']).startswith('G:')) for ln in q.get('links') or [])][:3]
    if segs:
        lead += ' The biggest changes: ' + '; '.join(f"{v[0]} {'+' if v[1] >= v[j] else '−'}{money(abs(v[1] - v[j]))} ({pc(chg(v[1], v[j]))})" for k, v in segs) + '.'
    for k, t in (('gp', 'Gross margin'), ('oi', 'Operating margin'), ('net', 'Net margin')):
        a, b = margin(n, k, 1), margin(n, k, j)
        if a is not None and b is not None:
            lead += f" {t} {a:.1f}% against {b:.1f}% ({pts(a - b)})."
            break
    rows = ''.join(f"<tr><td>{e(v[0])}</td><td class='num'>{e(money(v[1]))}</td><td class='num'>{e(money(v[j]))}</td><td class='num'>{e(money(v[1] - v[j]))}</td>"
                   f"<td class='num'>{e(pc(chg(v[1], v[j])))}</td></tr>" for k, v in n.items() if v[1] is not None and v[j] is not None)
    mrows = ''.join(f"<tr><td>{t}</td><td class='num'>{margin(n, k, 1):.1f}%</td><td class='num'>{margin(n, k, j):.1f}%</td><td class='num'>{e(pts(margin(n, k, 1) - margin(n, k, j)))}</td></tr>"
                    for k, t in (('gp', 'Gross margin'), ('oi', 'Operating margin'), ('net', 'Net margin'), ('fcf', 'Free cash flow margin'))
                    if margin(n, k, 1) is not None and margin(n, k, j) is not None)
    qa = [(f"How much did {name}'s revenue grow {what} in {lab}?", lead.split(' The biggest')[0])]
    if segs:
        qa.append((f"What drove {name}'s revenue change in {lab}?", first(lead.split(' The biggest changes: ')[1]) if ' The biggest changes: ' in lead else ''))
    url = f"{base}/c/{slug}/{qslug(lab)}-vs-{qslug(other)}/"
    title = f"{who} {lab} vs {other}: {what} revenue {pc(chg(rev[1], rev[j]))}, margins and every line compared | Filing Flows"
    body = (f"<p class='crumbs'><a href='../../../'>Filing Flows</a> › <a href='../'>{e(who)}</a> › <a href='../{qslug(lab)}/'>{e(lab)}</a> › vs {e(other)}</p>"
            f"<h1>{e(who)} {e(lab)} vs {e(other)} ({e(what)})</h1><p class='lead'>{e(lead)}</p>"
            + (f"<h2>Margins</h2><div class='tbl-wrap'><table><thead><tr><th></th><th class='num'>{e(lab)}</th><th class='num'>{e(other)}</th><th class='num'>Change</th></tr></thead><tbody>{mrows}</tbody></table></div>" if mrows else '')
            + f"<h2>Every line</h2><div class='tbl-wrap'><table><thead><tr><th>Line</th><th class='num'>{e(lab)}</th><th class='num'>{e(other)}</th><th class='num'>Change</th><th class='num'>%</th></tr></thead><tbody>{rows}</tbody></table></div>"
            + faq([x for x in qa if x[1]]) + f"<p><a href='../{qslug(lab)}/'>{e(lab)} results →</a> · <a class='seo-cta' href='../../../#c-{r['cik']}'>Compare in the interactive Sankey →</a></p>")
    crumbs = [('Filing Flows', base + '/'), (who, f'{base}/c/{slug}/'), (f'{lab} vs {other}', url)]
    return url, (q.get('filed') or '')[:10] or None, seo.page(title, lead[:300], url, body, 3, base + '/og.png', ld(base, crumbs, [x for x in qa if x[1]]))


# ---------------------------------------------------------------- one figure, quarter by quarter
METRICS = [('gross-margin', 'gross margin', ('gp', 'ratio')), ('operating-margin', 'operating margin', ('oi', 'ratio')),
           ('net-income', 'net income', ('net', 'value')), ('free-cash-flow', 'free cash flow', ('fcf', 'value')),
           ('research-and-development', 'R&D spending', ('I:rd', 'value')), ('capex', 'capital expenditures', ('capex', 'value'))]


def series(c, key, kind):
    out = []
    for q in c.get('quarters') or []:
        n = nodes(q)
        if key not in n or n[key][1] is None:
            continue
        v = margin(n, key, 1) if kind == 'ratio' else n[key][1]
        if v is not None:
            out.append((q.get('label'), v, q.get('filed')))
    return out


def metric_page(r, c, base, slug, who, name, mslug, label, key, kind):
    s = series(c, key, kind)
    if len(s) < 3:
        return None
    fmt = (lambda v: f'{v:.1f}%') if kind == 'ratio' else money
    latest, prev = s[0], s[1]
    hi, lo = max(s, key=lambda x: x[1]), min(s, key=lambda x: x[1])
    delta = (f"{pts(latest[1] - prev[1])} from {prev[0]}" if kind == 'ratio' else f"{pc(chg(latest[1], prev[1]))} from {prev[0]}")
    lead = (f"{name}'s {label} was {fmt(latest[1])} in {latest[0]} ({seo.period_words(latest[0])}), {delta}. "
            f"Over the last {len(s)} quarters it ranged from {fmt(lo[1])} ({lo[0]}) to {fmt(hi[1])} ({hi[0]}).")
    ya = {x[0]: x[1] for x in s}
    rows = ''.join(f"<tr><td>{e(x[0])}</td><td class='num'>{e(fmt(x[1]))}</td><td class='num'>{e((pts(x[1] - s[i + 1][1]) if kind == 'ratio' else pc(chg(x[1], s[i + 1][1]))) if i + 1 < len(s) else '—')}</td>"
                   f"<td class='num'>{e(((pts(x[1] - ya[year_ago(x[0])]) if kind == 'ratio' else pc(chg(x[1], ya[year_ago(x[0])]))) if year_ago(x[0]) in ya else '—'))}</td></tr>" for i, x in enumerate(s))
    qa = [(f"What is {name}'s {label}?", first(lead)), (f"How has {name}'s {label} changed?", lead[len(first(lead)):].strip() or lead)]
    url = f"{base}/c/{slug}/{mslug}/"
    title = f"{who} {label} by quarter: {fmt(latest[1])} in {latest[0]} | Filing Flows"
    body = (f"<p class='crumbs'><a href='../../../'>Filing Flows</a> › <a href='../'>{e(who)}</a> › {e(label[0].upper() + label[1:])}</p>"
            f"<h1>{e(who)} {e(label)} by quarter</h1><p class='lead'>{e(lead)}</p>"
            f"<div class='tbl-wrap'><table><thead><tr><th>Quarter</th><th class='num'>{e(label[0].upper() + label[1:])}</th><th class='num'>Q/Q</th><th class='num'>Y/Y</th></tr></thead><tbody>{rows}</tbody></table></div>"
            + faq(qa) + f"<p><a href='../{qslug(latest[0])}/'>{e(latest[0])} results →</a> · <a href='../revenue/'>How {e(name)} makes money →</a></p>")
    crumbs = [('Filing Flows', base + '/'), (who, f'{base}/c/{slug}/'), (label, url)]
    mod = (latest[2] or '')[:10] or None
    return url, mod, seo.page(title, lead[:300], url, body, 3, base + '/og.png', ld(base, crumbs, qa, mod))


def segment_metrics(c):
    """The largest revenue lines of the latest quarter: (slug, label, node id)."""
    qs = c.get('quarters') or []
    if not qs:
        return []
    q = qs[0]
    n = nodes(q)
    tops = [ln['s'] for ln in q.get('links') or [] if ln['t'] == 'revenue' and ln['s'] in n and ln['s'] not in ('rev_more',)]
    tops = sorted(set(tops), key=lambda k: -(n[k][1] or 0))[:3] if len(set(tops)) > 1 else []
    out = []
    for k in tops:
        lbl = n[k][0]
        s = re.sub(r'[^a-z0-9]+', '-', lbl.lower()).strip('-')[:40]
        if s and s not in ('revenue', 'other-revenues', 'other'):
            out.append((f'{s}-revenue' if 'revenue' not in s else s, f'{lbl} revenue', k))
    return out


# ---------------------------------------------------------------- guided against reported
def unit_fmt(v, unit):
    if v is None:
        return '—'
    return money(v) if unit == 'usd' else f'${v:.2f}' if unit == 'ps' else f'{v:.1f}%'


def vs_mid(v, unit):
    return '—' if v is None else f"{v:+.1f}{' pts' if unit == 'pct' else '%'}"


def guidance_page(r, rec, base, slug, who, name):
    ms = [m for m in rec.get('metrics') or [] if m.get('rows')]
    if not ms:
        return None
    judged = [m for m in ms if (m.get('hits') or {}).get('n')]
    n = sum(m['hits']['n'] for m in judged)
    hit = sum(m['hits']['hitOrBeat'] for m in judged)
    said = rec.get('said') or {}
    lead = f"{name} gave guidance in {rec.get('releases')} earnings releases on file since {fdate(rec.get('since'))}."
    if n:
        lead += f" Of {n} guided periods since reported, it met or beat its own guidance {hit} times ({round(100 * hit / n)}%)."
        best = max(judged, key=lambda m: m['hits']['n'])
        lead += f" {best['name']}: {best['hits']['hitOrBeat']} of {best['hits']['n']}" + (
            f", on average {best['hits']['avgVsMid']:+.1f}{' pts' if best['unit'] == 'pct' else '%'} against the guided midpoint" if best['hits'].get('avgVsMid') is not None else '') + '.'
    if said.get('raised') or said.get('lowered'):
        lead += f" Its releases raised guidance {said.get('raised', 0)} times and lowered it {said.get('lowered', 0)} times."
    OUT = {'above': 'above the range', 'within': 'within the range', 'below': 'below the range', 'met': 'met'}
    body = ''
    for m in ms[:6]:
        rows = ''
        for x in m['rows'][:10]:
            guides = ' → '.join(f"{(x2.get('change') + ' ') if i and x2.get('change') not in (None, 'first') else ''}{unit_fmt(x2['lo'], m['unit'])}"
                                + (f"–{unit_fmt(x2['hi'], m['unit'])}" if x2.get('hi') is not None and x2['hi'] != x2['lo'] else '') + f" ({fdate(x2.get('filed'))})"
                                for i, x2 in enumerate(x.get('guides') or []))
            res = OUT.get(x.get('outcome')) or ('to be reported' if x.get('pending') else '—')
            rows += (f"<tr><td>{e(x.get('label'))}</td><td>{e(guides)}</td><td class='num'>{e(unit_fmt(x.get('actual'), m['unit']))}</td><td>{e(res)}</td>"
                     f"<td class='num'>{e(vs_mid(x.get('vsMid'), m['unit']))}</td></tr>")
        h = m.get('hits') or {}
        body += (f"<h2>{e(m['name'])}</h2>" + (f"<p>Met or beat {h['hitOrBeat']} of {h['n']} periods ({h.get('above', 0)} above, {h.get('within', 0) + h.get('met', 0)} within, {h.get('below', 0)} below).</p>" if h.get('n') else
                                               "<p class='muted'>No reported figure to hold it to yet (adjusted figures are not in the GAAP statements, or the period is still to be reported).</p>")
                 + f"<div class='tbl-wrap'><table><thead><tr><th>Period</th><th>Guided (and how it moved)</th><th class='num'>Reported</th><th>Result</th><th class='num'>vs midpoint</th></tr></thead><tbody>{rows}</tbody></table></div>")
    qa = [(f"Does {name} beat its guidance?", lead.split(' Its releases')[0] if n else lead)]
    if said.get('raised') or said.get('lowered'):
        qa.append((f"How often does {name} raise guidance?", f"Its earnings releases raised guidance {said.get('raised', 0)} times and lowered it {said.get('lowered', 0)} times since {fdate(rec.get('since'))}."))
    url = f"{base}/c/{slug}/guidance-history/"
    title = f"{who} guidance history: guided vs reported" + (f", met or beat {round(100 * hit / n)}% of the time" if n else '') + ' | Filing Flows'
    page_body = (f"<p class='crumbs'><a href='../../../'>Filing Flows</a> › <a href='../'>{e(who)}</a> › Guidance history</p>"
                 f"<h1>{e(who)} guidance history: what it guided and what it reported</h1><p class='lead'>{e(lead)}</p>{body}" + faq(qa)
                 + "<p><a href='../guidance/'>Latest guidance and outlook →</a></p><p class='muted'>Each guided period is held to the last guidance given before its figures were reported; a single figure counts as in line within 1% (0.25 pts for a rate). Reported figures are GAAP, from the company's filings; adjusted guidance shows its moves only.</p>")
    crumbs = [('Filing Flows', base + '/'), (who, f'{base}/c/{slug}/'), ('Guidance history', url)]
    return url, (rec.get('latest') or '')[:10] or None, seo.page(title, lead[:300], url, page_body, 3, base + '/og.png', ld(base, crumbs, qa))


# ---------------------------------------------------------------- write
def write(site, base, period_pages=PERIOD_PAGES):
    base = base.rstrip('/')
    ix = read(os.path.join(site, 'data', 'index.json')) or {}
    latest = {}
    for r in (ix.get('companies') if isinstance(ix, dict) else ix) or []:
        if r['cik'] not in latest or (r.get('filed') or '') > (latest[r['cik']].get('filed') or ''):
            latest[r['cik']] = r
    maps = {'quarters': [], 'periods': [], 'metrics': []}
    counts = {'quarters': 0, 'qoq': 0, 'yoy': 0, 'metrics': 0, 'guidance': 0}

    def put(path, url, mod, doc, kind):
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(doc)
        maps[kind].append((url, mod))
    def one(cik, r):
        if not r.get('ticker'):
            return
        c = read(os.path.join(site, 'data', 'c', f'{cik}.json'))
        if not c or not c.get('quarters'):
            return
        slug, name = slug_for(r), display_name(r.get('name'))
        who = f"{name} ({r['ticker']})"
        d = os.path.join(site, 'c', slug)
        links = []
        for i, q in enumerate(c['quarters']):
            lab = q.get('label')
            if not lab or not qslug(lab):
                continue
            has_period = i < period_pages
            out = quarter_page(r, c, i, base, slug, who, name, has_period)
            if out:
                put(os.path.join(d, qslug(lab)), *out, 'quarters')
                counts['quarters'] += 1
                links.append((f'{qslug(lab)}/', f'{lab} results'))
            if has_period:
                for mode in ('qoq', 'yoy'):
                    out = period_page(r, c, i, base, slug, who, name, mode)
                    if out:
                        put(os.path.join(d, out[0].rstrip('/').rsplit('/', 1)[1]), *out, 'periods')
                        counts[mode] += 1
        mlinks = []
        for mslug, label, (key, kind) in METRICS:
            out = metric_page(r, c, base, slug, who, name, mslug, label, key, kind)
            if out:
                put(os.path.join(d, mslug), *out, 'metrics')
                counts['metrics'] += 1
                mlinks.append((f'{mslug}/', f'{name} {label} by quarter'))
        for mslug, label, key in segment_metrics(c):
            out = metric_page(r, c, base, slug, who, name, mslug, label, key, 'value')
            if out:
                put(os.path.join(d, mslug), *out, 'metrics')
                counts['metrics'] += 1
                mlinks.append((f'{mslug}/', f'{name} {label} by quarter'))
        rec = read(os.path.join(site, 'data', 'guidance-record', f'{cik}.json'))
        if rec:
            out = guidance_page(r, rec, base, slug, who, name)
            if out:
                put(os.path.join(d, 'guidance-history'), *out, 'metrics')
                counts['guidance'] += 1
                mlinks.insert(0, ('guidance-history/', f'{name} guidance history: guided vs reported'))
        main = os.path.join(d, 'index.html')
        try:
            txt = open(main, encoding='utf-8').read()
            if 'class="seo-history"' not in txt and '</main>' in txt and (links or mlinks):
                block = ('<section class="seo-history"><h2>History</h2>'
                         + (f"<p>Every quarter: {' · '.join(f'<a href={chr(39)}{u}{chr(39)}>{e(t)}</a>' for u, t in links)}</p>" if links else '')
                         + (f"<ul class='seo-list'>{''.join(f'<li><a href={chr(39)}{u}{chr(39)}>{e(t)}</a></li>' for u, t in mlinks)}</ul>" if mlinks else '') + '</section>')
                open(main, 'w', encoding='utf-8').write(txt.replace('</main>', block + '</main>', 1))
        except OSError:
            pass

    for cik, r in latest.items():
        try:
            one(cik, r)
        except Exception as err:  # noqa: BLE001 - one company's odd data never stops the run
            print(f"  {r.get('ticker')}: skipped ({type(err).__name__}: {err})")
    robots = os.path.join(site, 'robots.txt')
    txt = open(robots).read() if os.path.exists(robots) else f'User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n'
    for kind, urls in maps.items():
        sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        sm += [f'<url><loc>{xesc(u)}</loc>' + (f'<lastmod>{m}</lastmod>' if m else '') + '</url>' for u, m in urls[:50000]]
        sm.append('</urlset>')
        open(os.path.join(site, f'sitemap-{kind}.xml'), 'w', encoding='utf-8').write('\n'.join(sm))
        if f'sitemap-{kind}.xml' not in txt:
            txt = txt.rstrip('\n') + f'\nSitemap: {base}/sitemap-{kind}.xml\n'
    open(robots, 'w').write(txt)
    return counts


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', default='_site')
    ap.add_argument('--site-url', default=os.environ.get('SITE_URL', '') or 'https://filing-flows.com')
    a = ap.parse_args()
    m = re.search(r'https?://[^\s"]+', a.site_url or '')
    print('history pages:', write(a.site, m.group(0) if m else 'https://filing-flows.com'))
