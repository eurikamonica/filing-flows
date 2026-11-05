"""Report cards: how each company's reports went against what was expected, and what the stock did.

    c/<slug>/report-card/     every report on file: the analysts' EPS estimate, the GAAP and adjusted EPS reported, the
                              surprise, the revenue guided and reported, the stock's move on the day and against the
                              market; the hit rates; how the stock reacted to beats and misses; the earnings-day move
                              model (implied move against the realized moves, how often the implied range held); the
                              guidance credibility (where results land in the guided range, the odds the next one lands
                              above the midpoint)
    disclosures/report-cards/ the companies ranked: most reliable beaters, the biggest earnings-day movers, where the
                              options over- or under-price the move, the most credible guidance
    sitemap-reportcards.xml

Data: disclosures/data/research/earnings/c/<T>.json and index.json (app/earnings_season.py), data/guidance-record/<cik>.json
(pipeline/eps_guide.py). Every sentence is computed from the company's own record; nothing is forecast beyond the
odds its record implies.

    python scripts/seo_reportcard.py --site _site
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

e, fdate, display_name = seo.e, seo.fdate, seo.display_name


def read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def money(v):
    return seo.money(v)


def pc(v, d=1):
    return '—' if v is None else f"{100 * v:+.{d}f}%"


def usd2(v):
    return seo.usd2(v)


def quarter_label(q, hist_labels):
    """'2026-07-31' → the company's own label when the record has it, else 'Q to Jul 2026'"""
    if q in hist_labels:
        return hist_labels[q]
    try:
        d = dt.date.fromisoformat(q)
        return f"Q to {d:%b} {d.year}"
    except ValueError:
        return q


def credibility(rec):
    """Where the reported figures landed in the guided ranges, metric by metric → the summary and the odds.
    Returns None without at least three judged periods on the main metric."""
    if not rec:
        return None
    out = []
    for m in rec.get('metrics') or []:
        rows = [r for r in m.get('rows') or [] if r.get('actual') is not None and (r.get('guides') or [{}])[-1].get('lo') is not None]
        if len(rows) < 3:
            continue
        pos, vs = [], []
        lower_is_better = (m.get('hits') or {}).get('better') == 'lower'     # costs and tax rates: landing low is the beat
        for r in rows:
            g = r['guides'][-1]
            lo, hi, a = g['lo'], g['hi'], r['actual']
            if hi is None or lo is None:
                continue
            width = hi - lo
            p = (a - lo) / width if width else (0.5 if a == lo else (2 if a > lo else -1))
            pos.append(1 - p if lower_is_better else p)
            if r.get('vsMid') is not None:
                vs.append(-r['vsMid'] if lower_is_better else r['vsMid'])
        if not pos:
            continue
        above_mid = sum(1 for p in pos if p > 0.5)
        above = sum(1 for p in pos if p > 1)
        below = sum(1 for p in pos if p < 0)
        n = len(pos)
        p_next = (above_mid + 1) / (n + 2)                      # Laplace: the odds the next lands above the midpoint
        avg = sum(vs) / len(vs) if vs else None
        style = ('conservative: results beat the range itself' if above / n >= 0.6 else 'conservative: results land in the better half' if above_mid / n >= 0.7
                 else 'optimistic: results land in the worse half' if above_mid / n <= 0.3 else 'even-handed: results land around the midpoint')
        out.append({'name': m.get('name'), 'unit': m.get('unit'), 'n': n, 'lower': lower_is_better, 'above': above, 'within': n - above - below, 'below': below, 'above_mid': above_mid,
                    'p_next': p_next, 'avg_vs_mid': avg, 'style': style, 'pos': pos[-8:]})
    return out or None


def day_move(px, spy, report):
    """the report's move from the site's own daily prices (research/paths moves, what the timeline draws), the same window
    as the earnings research's: the close before the report day to the close of the first session after it, so a
    report before the open and one after the close are both inside. (move, excess over SPY), or (None, None)."""
    if not px or not report:
        return None, None
    days, cum = px
    i0 = ES.bisect_day(days, report) - 1
    i1 = i0 + 1 + (1 if i0 + 1 < len(days) and days[i0 + 1] == report else 0)
    if i0 < 0 or i1 >= len(days) or i1 >= len(cum):
        return None, None
    try:
        if (dt.date.fromisoformat(days[i1]) - dt.date.fromisoformat(report)).days > 6 or (dt.date.fromisoformat(report) - dt.date.fromisoformat(days[i0])).days > 6:
            return None, None
    except ValueError:
        return None, None
    mv = math.expm1(cum[i1] - cum[i0])
    ex = None
    if spy:
        sd, sc = spy
        a, b = ES.bisect_day(sd, days[i0]), ES.bisect_day(sd, days[i1])
        if b < len(sd) and b < len(sc) and sd[a] == days[i0] and sd[b] == days[i1]:
            ex = mv - math.expm1(sc[b] - sc[a])
    return mv, ex


def move_model(hist, implied, avg_move):
    """The earnings-day move: what the options price in against what the stock has done, and how often the implied
    range held. Returns a dict or None."""
    mv = [h['move'] for h in hist if h.get('move') is not None]
    if not mv:
        return None
    ab = sorted(abs(x) for x in mv)
    med = ab[len(ab) // 2]
    up = sum(1 for x in mv if x > 0)
    beats = [h for h in hist if h.get('beat') == 1 and h.get('move') is not None]
    misses = [h for h in hist if h.get('beat') == 0 and h.get('move') is not None]
    up_on_beat = sum(1 for h in beats if h['move'] > 0) / len(beats) if beats else None
    down_on_miss = sum(1 for h in misses if h['move'] < 0) / len(misses) if misses else None
    imp = (implied or {}).get('move')
    held = sum(1 for x in ab if imp is not None and x <= imp) / len(ab) if imp else None
    return {'n': len(mv), 'median_abs': med, 'largest': max(ab), 'up_share': up / len(mv), 'up_on_beat': up_on_beat, 'n_beats': len(beats),
            'down_on_miss': down_on_miss, 'n_misses': len(misses), 'implied': imp, 'held': held, 'avg_move': avg_move,
            'ratio': (med / imp) if imp else None}


def page_for(co, er, rec, base, slug, c=None, px=None, spy=None):
    name, t = display_name(co.get('name')), co.get('ticker') or ''
    hist = [dict(h) for h in (er or {}).get('history') or [] if h.get('est') is not None and h.get('act') is not None]
    for h in hist:                                  # a report-day move the earnings research has not got: from the site's prices
        if h.get('move') is None and h.get('reported'):
            h['move'], h['excess'] = day_move(px, spy, h['reported'])
    if len(hist) < 3:
        return None
    hist.sort(key=lambda h: h.get('reported') or '')
    labels = {}                                     # quarter end → the company's own label ("Q2 FY27"), from its quarters
    for q in (c or {}).get('quarters') or []:
        if q.get('end') and q.get('label'):
            labels[q['end']] = q['label']
    def near(d):                                    # the estimate's quarter end can differ by a few days from the filing's
        try:
            x = dt.date.fromisoformat(d)
        except (TypeError, ValueError):
            return None
        return next((v for k, v in labels.items() if abs((dt.date.fromisoformat(k) - x).days) <= 7), None)
    for h in hist:
        if h.get('quarter') and h['quarter'] not in labels and near(h['quarter']):
            labels[h['quarter']] = near(h['quarter'])
    own_rev = {q['label']: (q.get('headline') or {}).get('revenue') for q in (c or {}).get('quarters') or [] if q.get('label')}
    gaap = {p['quarter']: p for p in ((er.get('nongaap') or {}).get('points') or [])}
    rev_rows = {}
    rm = next((m for m in (rec or {}).get('metrics') or [] if m.get('metric') == 'revenue'), None)
    if rm:
        by_label = {v: k for k, v in labels.items()}
        for r in rm.get('rows') or []:
            if by_label.get(r.get('label')):
                rev_rows[by_label[r['label']]] = r
    beats = sum(1 for h in hist if h.get('beat') == 1)
    n = len(hist)
    # a surprise against an estimate within a nickel of zero (−$0.05 reported against $0.01) is a −600% that says nothing:
    # n/m in the table, left out of the average (the beat or miss still counts)
    surprises = [h['surprise'] for h in hist if h.get('surprise') is not None and abs(h.get('est') or 0) >= 0.05]
    avg_s = sum(surprises) / len(surprises) if surprises else None
    mm = move_model(hist, er.get('implied'), er.get('avg_move'))
    cred = credibility(rec)
    last = hist[-1]
    nxt = er.get('report_date')
    today = dt.date.today().isoformat()
    cs = er.get('consensus') or {}
    # ---- the sentences
    lead = (f"{name} ({t}) beat the analysts' EPS estimate in {beats} of its last {n} reports ({100 * beats / n:.0f}%)"
            + (f", by {pc(avg_s)} on average" if avg_s is not None else '') + '.')
    if mm:
        lead += (f" On report days the stock moved {100 * mm['median_abs']:.1f}% in either direction on median (largest {100 * mm['largest']:.1f}%), rising {100 * mm['up_share']:.0f}% of the time"
                 + (f"; after a beat it rose {100 * mm['up_on_beat']:.0f}% of the time" if mm['up_on_beat'] is not None and mm['n_beats'] >= 3 else '') + '.')
    if nxt and nxt >= today:
        lead += f" Next report: {fdate(nxt)}" + (f", analysts expect EPS {seo.usd2(cs['eps'])}" if cs.get('eps') is not None else '') + (f"; options imply a move of about ±{100 * mm['implied']:.1f}%" if mm and mm.get('implied') else '') + '.'
    # ---- tiles
    tiles = [('Beat rate', f"{100 * beats / n:.0f}% of {n}"), ('Average surprise', pc(avg_s)),
             ('Median move on the day', f"±{100 * mm['median_abs']:.1f}%" if mm else None), ('Rose on the day', f"{100 * mm['up_share']:.0f}%" if mm else None),
             ('Options imply next', f"±{100 * mm['implied']:.1f}%" if mm and mm.get('implied') else None), ('Next report', fdate(nxt) if nxt and nxt >= today else None)]
    # ---- the table
    # every column a row can fill; a column no report of this company fills (it never guides revenue, its GAAP EPS is not
    # read) is left out rather than shown as a column of dashes
    cols = [('Quarter', ''), ('Reported', ''), ('EPS est.', 'num'), ('EPS reported', 'num'), ('Surprise', 'num'), ('GAAP EPS', 'num'),
            ('Revenue guided', 'num'), ('Revenue reported', 'num'), ('Stock, the day', 'num'), ('vs market', 'num')]
    cells = []
    for h in reversed(hist):
        q = h.get('quarter')
        g = gaap.get(q) or {}
        rv = rev_rows.get(q) or {}
        gl = (rv.get('guides') or [{}])[-1] if rv else {}
        guided = f"{money(gl['lo'])}–{money(gl['hi'])}" if gl.get('lo') is not None and gl.get('hi') is not None else None
        lab_q = quarter_label(q, labels)
        rev_act = rv.get('actual') if rv.get('actual') is not None else own_rev.get(lab_q)      # the filing's revenue when none was guided
        sc = 'up' if (h.get('surprise') or 0) > 0 else 'down' if (h.get('surprise') or 0) < 0 else ''
        mc = 'up' if (h.get('move') or 0) > 0 else 'down' if (h.get('move') or 0) < 0 else ''
        cells.append([e(lab_q), e(fdate(h.get('reported'))), usd2(h.get('est')), f"<b>{usd2(h.get('act'))}</b>",
                      (f"<span class='{sc}'>{pc(h.get('surprise'))}</span>" if abs(h.get('est') or 0) >= 0.05 else 'n/m'),
                      usd2(g.get('gaap')) if g.get('gaap') is not None else None, guided,
                      (money(rev_act) + (f" <span class=muted>({e(rv.get('outcome'))})</span>" if rv.get('outcome') else '')) if rev_act is not None else None,
                      f"<span class='{mc}'>{pc(h.get('move'))}</span>" if h.get('move') is not None else None, pc(h.get('excess')) if h.get('excess') is not None else None])
    keep = [j for j in range(len(cols)) if j < 5 or any(r[j] is not None for r in cells)]
    table = ("<div class='tbl-wrap'><table><thead><tr>" + ''.join(f"<th{' class=num' if cols[j][1] else ''}>{cols[j][0]}</th>" for j in keep) + "</tr></thead><tbody>"
             + ''.join("<tr>" + ''.join(f"<td{' class=num' if cols[j][1] else ''}>{r[j] if r[j] is not None else '—'}</td>" for j in keep) + "</tr>" for r in cells)
             + "</tbody></table></div>")
    shown = {cols[j][0] for j in keep}
    note = ' '.join(filter(None, [
        "Estimates and reported EPS are the Street's adjusted figures" + ("; GAAP EPS is from the filing (SEC XBRL)." if 'GAAP EPS' in shown else '.'),
        "Revenue guided is the last range the company gave before the report." if 'Revenue guided' in shown else None,
        "Revenue reported is from the company's filing." if 'Revenue reported' in shown else None,
        ("The stock's move is close to close around the report date (the close before it to the close of the session after), "
         "against SPY for the market column." if 'Stock, the day' in shown else "No daily prices are on file for these report days, so the stock's moves are not shown.")]))
    # ---- charts
    lab = lambda h: quarter_label(h.get('quarter'), labels)
    charts = SV.duo([(lab(h), h['est'], h['act']) for h in hist[-8:]], ('Estimate', 'Reported'), seo.usd2, f"{name}: EPS reported against the estimate")
    charts += SV.diverging([(lab(h), 100 * h['move']) for h in reversed(hist[-10:]) if h.get('move') is not None], lambda v: f"{v:+.1f}%",
                           f"{t}: the stock's move on each report day", n=10, note='Close to close around the report, from the daily price history.')
    pts = [(lab(h), 100 * h['surprise'], 100 * h['move'], 1) for h in hist if h.get('surprise') is not None and h.get('move') is not None and abs(h.get('est') or 0) >= 0.05]
    if len(pts) >= 6:
        charts += SV.scatter(pts, 'EPS surprise', 'the stock on the day', f"{t}: does a bigger beat mean a bigger move?", me=None,
                             note='Each dot is one report. Dashed lines are the medians.', xfmt=lambda v: f"{v:+.0f}%", yfmt=lambda v: f"{v:+.0f}%")
    # ---- the move model
    model = ''
    if mm:
        s = [f"Over {mm['n']} reports the stock moved <b>{100 * mm['median_abs']:.1f}%</b> on median on the day (close to close), the largest move {100 * mm['largest']:.1f}%."]
        if mm.get('implied'):
            s.append(f"For the next report the options price in about <b>±{100 * mm['implied']:.1f}%</b>"
                     + (f" — {'more' if mm['ratio'] < 1 else 'less'} than the stock's median move ({mm['ratio']:.1f}× the implied)" if mm.get('ratio') else '')
                     + (f"; a range that size would have covered <b>{100 * mm['held']:.0f}%</b> of the past moves" if mm.get('held') is not None else '') + '.')
            if mm.get('held') is not None:
                s.append('Read it as: ' + ('the options have usually been generous, so the straddle has tended to overpay.' if mm['held'] >= 0.75 else
                                           'the options have usually been about right.' if mm['held'] >= 0.5 else 'the stock has often moved more than the options priced in.'))
        if mm['up_on_beat'] is not None and mm['n_beats'] >= 3:
            s.append(f"After a beat the stock rose {100 * mm['up_on_beat']:.0f}% of the time ({mm['n_beats']} beats)"
                     + (f"; after a miss it fell {100 * mm['down_on_miss']:.0f}% of the time ({mm['n_misses']} misses)" if mm['down_on_miss'] is not None and mm['n_misses'] >= 2 else '') + '.')
        model = "<h2 id='move'>The earnings-day move</h2><div class='seo-note'>" + ''.join(f"<p>{x}</p>" for x in s) + "</div>"
    # ---- guidance credibility
    credh = ''
    if cred:
        parts = []
        for c in cred:
            parts.append(f"<p><b>{e(c['name'])}</b>: of {c['n']} guided periods, {c['above']} came in beyond the {'better' if c['lower'] else 'top'} end of the range, {c['within']} within and {c['below']} short of it; "
                         f"{c['above_mid']} of {c['n']} on the better side of the midpoint" + (f" ({'lower' if c['lower'] else 'higher'} is better)" if c['lower'] else '') + (f", on average {c['avg_vs_mid']:+.1f}% against the midpoint (+ is better)" if c['avg_vs_mid'] is not None else '')
                         + f". Guidance has been <b>{e(c['style'])}</b>. On that record the odds the next lands on the better side of the midpoint are about <b>{100 * c['p_next']:.0f}%</b>.</p>")
        credh = ("<h2 id='guidance'>How credible is its guidance?</h2><div class='seo-note'>" + ''.join(parts)
                 + "<p class='muted'>Position in the range: 0 is the worse end, 1 the better end (for costs and tax rates, lower). Odds are the record plus one each way (Laplace), not a forecast.</p></div>"
                 + SV.bars([(f"#{i + 1}", min(1.5, max(-0.5, p))) for i, p in enumerate(cred[0]['pos'])], lambda v: 'beat' if v >= 1.5 else 'missed' if v <= -0.5 else f"{v:.2f}", f"{t}: where {cred[0]['name'].lower()} landed in its guided range, last {len(cred[0]['pos'])} periods",
                           note='1 = the better end of the range, 0 = the worse end; "beat" is beyond the range, "missed" short of it.', color=SV.BLUE))
    url = f"{base}/c/{slug}/report-card/"
    title = f"{name} ({t}) Earnings Report Card: Beat {beats} of {n}, Moves ±{100 * mm['median_abs']:.1f}% on the Day" if mm else f"{name} ({t}) Earnings Report Card: Beat {beats} of {n}"
    body = (f"<p class='crumbs'><a href='../../../'>Filing Flows</a> › <a href='../../'>Companies</a> › <a href='../'>{e(name)}</a> › Report card</p>"
            f"<h1>{e(name)} earnings report card</h1><p class='muted'>Every report on file against what analysts and the company itself expected, and what the stock did</p>"
            f"<p class='seo-hl {'up' if beats / n >= 0.7 else 'down' if beats / n < 0.5 else ''}'><span>Beat rate</span><b>{beats} of {n}</b> reports beat the EPS estimate</p>"
            "<nav class='seo-toc'><a href='#card'>Report card</a><a href='#charts'>Charts</a><a href='#move'>The move</a>" + ("<a href='#guidance'>Guidance</a>" if cred else '') + "</nav>"
            f"<p class='lead'>{e(lead)}</p><div class='seo-tiles'>" + ''.join(f"<div class='seo-tile'><span>{e(k)}</span><b>{e(v)}</b></div>" for k, v in tiles if v) + "</div>"
            f"<h2 id='card'>Report by report</h2>{table}<p class='muted'>{e(note)}</p>"
            f"<h2 id='charts'>Charts</h2><div class='seo-grid'>{charts}</div>{model}{credh}"
            f"<p><a class='seo-cta' href='../earnings-date/'>The next report: what to expect →</a> <a href='../'>{e(name)}: every quarter →</a></p>"
            "<p class='muted'>Read automatically from SEC filings, earnings releases and public estimates; errors are possible. Not investment advice.</p>")
    ld = {'@context': 'https://schema.org', '@graph': [
        {'@type': 'BreadcrumbList', 'itemListElement': [{'@type': 'ListItem', 'position': 1, 'name': 'Filing Flows', 'item': base + '/'},
                                                         {'@type': 'ListItem', 'position': 2, 'name': name, 'item': f"{base}/c/{slug}/"},
                                                         {'@type': 'ListItem', 'position': 3, 'name': 'Report card', 'item': url}]},
        {'@type': 'FAQPage', 'mainEntity': [{'@type': 'Question', 'name': f"How often does {name} beat earnings?", 'acceptedAnswer': {'@type': 'Answer', 'text': lead}}]
         + ([{'@type': 'Question', 'name': f"How much does {t} stock move on earnings?", 'acceptedAnswer': {'@type': 'Answer', 'text': re.sub('<[^>]+>', '', s[0] if mm else '')}}] if mm else [])},
        {'@type': 'WebPage', 'name': title, 'url': url, 'dateModified': last.get('reported'), 'description': lead[:300]}]}
    return url, last.get('reported'), seo.page(seo.fit(title), lead[:300], url, body, 3, base + '/og.png', ld), {
        'ticker': t, 'name': name, 'slug': slug, 'n': n, 'beats': beats, 'avg_s': avg_s, 'med': mm and mm['median_abs'], 'up': mm and mm['up_share'],
        'implied': mm and mm.get('implied'), 'ratio': mm and mm.get('ratio'), 'held': mm and mm.get('held'), 'cred': cred[0] if cred else None, 'next': nxt}


def index_page(site, base, cards):
    L = lambda c: f"<a href='../../c/{c['slug']}/report-card/'><b>{e(c['ticker'])}</b></a> {e(c['name'])}"
    cs = [c for c in cards if c['n'] >= 4]
    best = sorted(cs, key=lambda c: (-c['beats'] / c['n'], -c['n']))[:25]
    movers = sorted([c for c in cs if c['med']], key=lambda c: -c['med'])[:20]
    calm = sorted([c for c in cs if c['med']], key=lambda c: c['med'])[:15]
    cheap = sorted([c for c in cs if c['ratio'] and c['implied'] and c['n'] >= 6], key=lambda c: -c['ratio'])[:15]      # the stock moves more than the options price
    rich = sorted([c for c in cs if c['ratio'] and c['implied'] and c['n'] >= 6], key=lambda c: c['ratio'])[:15]
    cred = sorted([c for c in cs if c['cred'] and c['cred']['n'] >= 4], key=lambda c: -c['cred']['above_mid'] / c['cred']['n'])[:20]
    today = dt.date.today().isoformat()
    soon = sorted([c for c in cs if c['next'] and c['next'] >= today], key=lambda c: c['next'])[:20]
    lead = (f"{len(cs)} companies with four or more reports on record. Beat rates, the size of the stock's move on the day, where the options have priced that move too high or "
            f"too low, and whose guidance is most conservative — each company's own record, nothing more.")
    body = (f"<p class='crumbs'><a href='../../'>Filing Flows</a> › <a href='../'>Disclosures</a> › Report cards</p><h1>Earnings report cards</h1><p class='lead'>{lead}</p>"
            + SV.hbars([(c['ticker'], 100 * c['beats'] / c['n']) for c in best[:15]], lambda v: f"{v:.0f}%", 'Most reliable beaters (share of reports that beat the EPS estimate)', n=15)
            + SV.hbars([(c['ticker'], 100 * c['med']) for c in movers[:15]], lambda v: f"±{v:.1f}%", 'Biggest earnings-day movers (median move on the day)', n=15, color=SV.RED)
            + ("<h2>Reporting next, with their record</h2>" + table(['Company', 'Reports', 'Beat rate', 'Median move', 'Options imply'], [
                [L(c), str(c['n']), f"{100 * c['beats'] / c['n']:.0f}%", f"±{100 * c['med']:.1f}%" if c['med'] else '—', f"±{100 * c['implied']:.1f}%" if c['implied'] else '—'] for c in soon]) if soon else '')
            + sect("<h2>Most reliable beaters</h2>", ['Company', 'Beat rate', 'Reports', 'Avg. surprise', 'Rose on the day'], [
                [L(c), f"{100 * c['beats'] / c['n']:.0f}%", str(c['n']), pc(c['avg_s']), f"{100 * c['up']:.0f}%" if c['up'] is not None else '—'] for c in best])
            + sect("<h2>The stock has moved more than the options priced in</h2><p class='muted'>Median realized move divided by the move the options currently imply; above 1 the straddle has tended to be cheap, below 1 generous.</p>",
                   ['Company', 'Median move', 'Options imply', 'Ratio', 'Implied range held'], [[L(c), f"±{100 * c['med']:.1f}%", f"±{100 * c['implied']:.1f}%", f"{c['ratio']:.1f}×", f"{100 * c['held']:.0f}%" if c['held'] is not None else '—'] for c in cheap])
            + sect("<h2>The options have priced in more than the stock moved</h2>", ['Company', 'Median move', 'Options imply', 'Ratio', 'Implied range held'], [[L(c), f"±{100 * c['med']:.1f}%", f"±{100 * c['implied']:.1f}%", f"{c['ratio']:.1f}×", f"{100 * c['held']:.0f}%" if c['held'] is not None else '—'] for c in rich])
            + sect("<h2>Calmest on report day</h2>", ['Company', 'Median move', 'Beat rate'], [[L(c), f"±{100 * c['med']:.1f}%", f"{100 * c['beats'] / c['n']:.0f}%"] for c in calm])
            + ("<h2>Most conservative guidance</h2><p class='muted'>Share of guided periods whose result landed above the midpoint of the range.</p>" + table(['Company', 'Metric', 'Better side of midpoint', 'Beat the range', 'Avg. vs midpoint', 'Odds next on the better side'], [
                [L(c), e(c['cred']['name']), f"{c['cred']['above_mid']} of {c['cred']['n']}", str(c['cred']['above']), f"{c['cred']['avg_vs_mid']:+.1f}%" if c['cred']['avg_vs_mid'] is not None else '—', f"{100 * c['cred']['p_next']:.0f}%"] for c in cred]) if cred else '')
            + "<p class='muted'>From each company's reports, earnings releases and daily prices; errors are possible. Not investment advice.</p>")
    url = f"{base}/disclosures/report-cards/"
    os.makedirs(os.path.join(site, 'disclosures', 'report-cards'), exist_ok=True)
    open(os.path.join(site, 'disclosures', 'report-cards', 'index.html'), 'w', encoding='utf-8').write(seo.page(
        'Earnings report cards: who beats, how much stocks move on the day, whose guidance is conservative | Filing Flows', lead[:300], url, body, 2, base + '/og.png'))
    return url


def sect(head_html, cols, rows):
    """a heading and its table, or nothing when no company qualifies (an empty table under a heading reads as broken)"""
    return head_html + table(cols, rows) if rows else ''


def table(head, rows):
    return (f"<div class='tbl-wrap'><table><thead><tr>{''.join(f'<th>{e(h)}</th>' for h in head)}</tr></thead><tbody>"
            + ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in rows) + '</tbody></table></div>')


def link_from_company(site, slug):
    p = os.path.join(site, 'c', slug, 'index.html')
    if not os.path.exists(p):
        return
    t = open(p, encoding='utf-8').read()
    if 'report-card/' in t:
        return
    open(p, 'w', encoding='utf-8').write(t.replace('<nav class="seo-toc" aria-label="On this page">', '<nav class="seo-toc" aria-label="On this page"><a href="report-card/">Report card</a>', 1))


def write(site, base):
    base = base.rstrip('/')
    ix = read(os.path.join(site, 'data', 'index.json')) or {}
    rows = ix.get('companies') if isinstance(ix, dict) else ix
    hub = os.path.join(site, 'disclosures', 'data')
    urls, cards = [], []
    moves = os.path.join(hub, 'research', 'paths', 'moves', 'a')
    spy_doc = read(os.path.join(moves, 'SPY.json'))
    spy = ES.decode(spy_doc) if spy_doc else None
    for r in rows or []:
        t = r.get('ticker')
        slug = seo.slug_for(r)
        if not t or not os.path.exists(os.path.join(site, 'c', slug, 'index.html')):
            continue
        er = read(os.path.join(hub, 'research', 'earnings', 'c', f"{str(t).upper().replace('.', '-')}.json"))
        if not er:
            continue
        rec = read(os.path.join(site, 'data', 'guidance-record', f"{r['cik']}.json"))
        try:
            ad = read(os.path.join(moves, re.sub(r'[^A-Za-z0-9-]', '_', str(t).upper()) + '.json'))
            out = page_for(r, er, rec, base, slug, read(os.path.join(site, 'data', 'c', f"{r['cik']}.json")),
                           ES.decode(ad) if ad else None, spy)
        except Exception as err:  # noqa: BLE001
            print(f"report card skipped ({t}): {err}")
            continue
        if not out:
            continue
        url, mod, doc, card = out
        d = os.path.join(site, 'c', slug, 'report-card')
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'index.html'), 'w', encoding='utf-8').write(doc)
        link_from_company(site, slug)
        urls.append((url, mod))
        cards.append(card)
    if cards:
        urls.insert(0, (index_page(site, base, cards), dt.date.today().isoformat()))
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f'<url><loc>{xesc(u)}</loc>' + (f'<lastmod>{xesc(str(m)[:10])}</lastmod>' if m else '') + '</url>' for u, m in urls]
    sm.append('</urlset>')
    open(os.path.join(site, 'sitemap-reportcards.xml'), 'w', encoding='utf-8').write('\n'.join(sm))
    robots = os.path.join(site, 'robots.txt')
    txt = open(robots).read() if os.path.exists(robots) else f'User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n'
    if 'sitemap-reportcards.xml' not in txt:
        open(robots, 'w').write(txt.rstrip('\n') + f'\nSitemap: {base}/sitemap-reportcards.xml\n')
    return len(cards)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', default='_site')
    ap.add_argument('--site-url', default=os.environ.get('SITE_URL', '') or 'https://filing-flows.com')
    a = ap.parse_args()
    m = re.search(r'https?://[^\s"]+', a.site_url or '')
    print(f"report cards: {write(a.site, m.group(0) if m else 'https://filing-flows.com')}")
