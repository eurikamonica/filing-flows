"""Spanish and French company pages for search engines (es/c/<slug>/, fr/c/<slug>/): the latest results, revenue by
segment, the next earnings date and the analysts' estimates, written in each language with its own number and date
conventions ("96,2 mil millones de dólares", "96,2 milliards de dollars", "17 de noviembre de 2026", "17 novembre
2026"). Every language version of a company (en, zh-Hans, es, fr) names all the others with hreflang, so search
engines show each reader their own language.

    es/c/<slug>/, fr/c/<slug>/, es/, fr/   sitemap-es.xml, sitemap-fr.xml (robots.txt, IndexNow)
    hreflang added to the English c/<slug>/ and the Chinese zh/c/<slug>/ pages

    python scripts/seo_intl.py --site _site --site-url https://filing-flows.com   (after seo_zh.py)
"""
import argparse
import datetime as dt
import html as H
import json
import os
import re
import sys
from xml.sax.saxutils import escape as xesc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seo  # noqa: E402
import seo_svg as SV  # noqa: E402
from seo_history import sankey_figure  # noqa: E402

e, display_name, slug_for = seo.e, seo.display_name, seo.slug_for


def read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def num(v, d=1):
    """1234.5 → '1.234,5' (both languages use a decimal comma; Spanish groups with '.', French with a narrow space)."""
    return f'{v:,.{d}f}'.replace(',', '§').replace('.', ',').replace('§', '.')


L = {
    'es': {
        'ord': ['primer', 'segundo', 'tercer', 'cuarto'],
        'months': ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'],
        'date': lambda d, m: f'{d.day} de {m} de {d.year}',
        'q': lambda o, y, fy: f'{o} trimestre {"del año fiscal" if fy else "de"} {y}',
        'fy': lambda y: f'año fiscal {y}',
        'bn': 'mil millones de dólares', 'mn': 'millones de dólares', 'th': 'mil dólares', 'usd': 'dólares', 'pct': '%',
        'thou': '.', 'sep': '; ',
        'title': lambda who, per, rev, yoy: f'{who}: resultados del {per}, ingresos de {rev}' + (f', {yoy} interanual' if yoy else ''),
        'h1': lambda who, per: f'Resultados de {who} del {per}',
        'lead': lambda who, per, rev, up, g, om, ni, form, date: (f'{who} registró ingresos de {rev} en el {per}'
                                                                  + (f', {"un aumento" if up else "una caída"} del {g} interanual' if g else '')
                                                                  + (f', con un margen operativo del {om}' if om else '') + (f' y un beneficio neto de {ni}' if ni else '')
                                                                  + f' ({form} presentado el {date}).'),
        'segs': 'Ingresos por segmento: ', 'cents': lambda gp, net: 'De cada dólar de ingresos, ' + ' y '.join(
            x for x in (f'{gp} centavos fueron beneficio bruto' if gp is not None else '', f'{net} centavos beneficio neto' if net is not None else '') if x) + '.',
        'next': lambda date, days, est: f'Presentará sus próximos resultados el {date}{" (fecha estimada)" if est else ""}, dentro de {days} días.',
        'expect': lambda eps, rev, ya: f' Los analistas esperan un beneficio por acción (BPA) de {eps} dólares' + (f' e ingresos de {rev}' if rev else '') + (f', frente a {ya} dólares hace un año' if ya else '') + '.',
        'beat': lambda b: f' Superó la estimación de BPA en el {b}% de los trimestres registrados.',
        'tiles': ['Ingresos', 'Interanual', 'Margen operativo', 'Beneficio neto', 'Flujo de caja operativo'],
        'h_seg': lambda n, per: f'Ingresos de {n} por segmento ({per})', 'seg_head': ['Segmento', 'Ingresos', 'Peso', 'Interanual'],
        'chart_rev': 'ingresos por trimestre', 'chart_ni': 'beneficio neto por trimestre', 'chart_sankey': 'diagrama Sankey de ingresos, beneficios y caja',
        'h_hist': 'Resultados trimestrales recientes', 'hist_head': ['Trimestre', 'Ingresos', 'Interanual', 'Margen operativo', 'Beneficio neto'],
        'faq': 'Preguntas frecuentes', 'q_last': lambda n: f'¿Cómo fueron los últimos resultados de {n}?', 'q_how': lambda n: f'¿Cómo gana dinero {n}?',
        'q_when': lambda n: f'¿Cuándo presenta resultados {n}?',
        'cta': 'Abrir el diagrama Sankey interactivo →', 'source': lambda n, f: f'Datos leídos automáticamente del {f} que {n} presentó ante la SEC de EE. UU.; pueden contener errores. No es asesoramiento de inversión.',
        'idx_title': 'Resultados de empresas de EE. UU.: ingresos, márgenes y próxima fecha de resultados | Filing Flows',
        'idx_h1': lambda n: f'Resultados trimestrales de {n} empresas cotizadas en EE. UU.',
        'idx_lead': 'Los últimos ingresos, crecimiento, márgenes, beneficio neto e ingresos por segmento de cada empresa, con la próxima fecha de resultados y lo que esperan los analistas, leídos de sus informes ante la SEC y actualizados cada día.',
        'idx_item': lambda who: f'Resultados de {who}', 'crumb': 'Filing Flows en español', 'other': 'Otros idiomas',
    },
    'fr': {
        'ord': ['premier', 'deuxième', 'troisième', 'quatrième'],
        'months': ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'],
        'date': lambda d, m: f'{d.day} {m} {d.year}',
        'q': lambda o, y, fy: f'{o} trimestre {"de l’exercice " if fy else ""}{y}',
        'fy': lambda y: f'exercice {y}',
        'bn': 'milliards de dollars', 'mn': 'millions de dollars', 'th': 'milliers de dollars', 'usd': 'dollars', 'pct': ' %',
        'thou': ' ', 'sep': ' ; ',
        'title': lambda who, per, rev, yoy: f'{who} : résultats du {per}, chiffre d’affaires de {rev}' + (f', {yoy} sur un an' if yoy else ''),
        'h1': lambda who, per: f'Résultats de {who} au {per}',
        'lead': lambda who, per, rev, up, g, om, ni, form, date: (f'{who} a réalisé un chiffre d’affaires de {rev} au {per}'
                                                                  + (f', en {"hausse" if up else "baisse"} de {g} sur un an' if g else '')
                                                                  + (f', avec une marge opérationnelle de {om}' if om else '') + (f' et un bénéfice net de {ni}' if ni else '')
                                                                  + f' ({form} déposé le {date}).'),
        'segs': 'Chiffre d’affaires par segment : ', 'cents': lambda gp, net: 'Sur chaque dollar de chiffre d’affaires, ' + ' et '.join(
            x for x in (f'{gp} cents de marge brute' if gp is not None else '', f'{net} cents de bénéfice net' if net is not None else '') if x) + '.',
        'next': lambda date, days, est: f'Prochains résultats attendus le {date}{" (date estimée)" if est else ""}, dans {days} jours.',
        'expect': lambda eps, rev, ya: f' Les analystes attendent un bénéfice par action (BPA) de {eps} dollars' + (f' et un chiffre d’affaires de {rev}' if rev else '') + (f', contre {ya} dollars un an plus tôt' if ya else '') + '.',
        'beat': lambda b: f' Le BPA a dépassé le consensus dans {b} % des trimestres connus.',
        'tiles': ['Chiffre d’affaires', 'Sur un an', 'Marge opérationnelle', 'Bénéfice net', 'Flux de trésorerie d’exploitation'],
        'h_seg': lambda n, per: f'Chiffre d’affaires de {n} par segment ({per})', 'seg_head': ['Segment', 'Chiffre d’affaires', 'Part', 'Sur un an'],
        'chart_rev': 'chiffre d’affaires par trimestre', 'chart_ni': 'bénéfice net par trimestre', 'chart_sankey': 'diagramme de Sankey du chiffre d’affaires au cash',
        'h_hist': 'Résultats trimestriels récents', 'hist_head': ['Trimestre', 'Chiffre d’affaires', 'Sur un an', 'Marge opérationnelle', 'Bénéfice net'],
        'faq': 'Questions fréquentes', 'q_last': lambda n: f'Quels sont les derniers résultats de {n} ?', 'q_how': lambda n: f'Comment {n} gagne-t-il de l’argent ?',
        'q_when': lambda n: f'Quand {n} publie-t-il ses résultats ?',
        'cta': 'Ouvrir le diagramme de Sankey interactif →', 'source': lambda n, f: f'Données lues automatiquement dans le {f} déposé par {n} auprès de la SEC américaine ; des erreurs sont possibles. Ceci n’est pas un conseil en investissement.',
        'idx_title': 'Résultats des entreprises américaines : chiffre d’affaires, marges et date des prochains résultats | Filing Flows',
        'idx_h1': lambda n: f'Résultats trimestriels de {n} entreprises cotées aux États-Unis',
        'idx_lead': 'Le dernier chiffre d’affaires, la croissance, les marges, le bénéfice net et la répartition par segment de chaque entreprise, avec la date des prochains résultats et les attentes des analystes, lus dans ses documents déposés auprès de la SEC et mis à jour chaque jour.',
        'idx_item': lambda who: f'Résultats de {who}', 'crumb': 'Filing Flows en français', 'other': 'Autres langues',
    },
}
LANG_NAME = {'en': 'English', 'zh-Hans': '中文', 'es': 'Español', 'fr': 'Français'}


def money(v, t):
    """96.2e9 → '96,2 mil millones de dólares' / '96,2 milliards de dollars'; 5.3e8 → '530 millones de dólares'."""
    if v is None:
        return '—'
    s, a = ('-' if v < 0 else ''), abs(v)
    x, unit = (f'{a / 1e9:,.1f}', t['bn']) if a >= 1e9 else (f'{a / 1e6:,.0f}', t['mn']) if a >= 1e6 else (f'{a / 1e3:,.0f}', t['th'])
    x = x.replace(',', '§').replace('.', ',').replace('§', t['thou'])
    return f"{s}{x[:-2] if x.endswith(',0') else x} {unit}"


def pct(v, t, signed=False):
    if v is None:
        return None
    x = f'{abs(v):.0f}' if signed else f'{v:.1f}'.replace('.', ',')
    return (('+' if v >= 0 else '−') if signed else '') + x + t['pct']


def period(label, t):
    m = re.fullmatch(r'Q([1-4])\s+(FY)?(\d{2}|\d{4})', (label or '').strip())
    if m:
        y = m[3] if len(m[3]) == 4 else '20' + m[3]
        return t['q'](t['ord'][int(m[1]) - 1], y, bool(m[2]))
    m = re.fullmatch(r'FY\s?(\d{2}|\d{4})', (label or '').strip())
    return t['fy'](m[1] if len(m[1]) == 4 else '20' + m[1]) if m else (label or '')


def ldate(s, t):
    try:
        d = dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return s or ''
    return t['date'](d, t['months'][d.month - 1])


def alternates(slug, base, langs):
    """<link rel="alternate" hreflang=…> for every language version of a company page that exists."""
    path = {'en': f'{base}/c/{slug}/', 'zh-Hans': f'{base}/zh/c/{slug}/', 'es': f'{base}/es/c/{slug}/', 'fr': f'{base}/fr/c/{slug}/'}
    out = ''.join(f'<link rel="alternate" hreflang="{k}" href="{e(path[k])}">' for k in ('en', 'zh-Hans', 'es', 'fr') if k in langs)
    return out + f'<link rel="alternate" hreflang="x-default" href="{e(path["en"])}">'


def company(lang, r, c, er, cons, base, langs):
    t = L[lang]
    qs = (c or {}).get('quarters') or []
    if not qs:
        return None
    q = qs[0]
    h = q.get('headline') or {}
    if not h.get('revenue'):
        return None
    tk, en = r['ticker'], display_name(r.get('name'))
    who = f'{en} ({tk})'
    per = period(q.get('label'), t)
    rev = h['revenue']
    lead = t['lead'](who, per, money(rev, t), (h.get('yoy') or 0) >= 0, pct(h.get('yoy'), t, True) and pct(h.get('yoy'), t, True).lstrip('+−'),
                     pct(h.get('om'), t), money(h.get('ni'), t) if h.get('ni') is not None else None, q.get('form'), ldate(q.get('filed'), t))
    lab = {n['id']: H.unescape(n.get('label') or n.get('name') or n['id']) for n in q.get('nodes') or []}
    into, segs = {}, {}
    for ln in q.get('links') or []:
        into[ln['t']] = into.get(ln['t'], 0) + (ln.get('v') or 0)
        if ln['t'] == 'revenue':
            a = segs.setdefault(lab.get(ln['s'], ln['s']), [0.0, 0.0])
            a[0] += ln.get('v') or 0
            a[1] += ln.get('y') or 0
    segs = sorted(segs.items(), key=lambda x: -x[1][0])
    if len(segs) > 1:
        lead += ' ' + t['segs'] + t['sep'].join(f'{k} {money(v[0], t)} ({100 * v[0] / rev:.0f}{t["pct"]})' for k, v in segs[:3]) + '.'
    gp, net = into.get('gp'), into.get('net')
    if gp or net:
        lead += ' ' + t['cents'](round(100 * gp / rev) if gp else None, round(100 * net / rev) if net else None)
    nxt = ''
    if er and er.get('report_date'):
        try:
            days = (dt.date.fromisoformat(er['report_date']) - dt.date.today()).days
        except ValueError:
            days = -1
        cs = er.get('consensus') or {}
        if days >= 0:
            nxt = t['next'](ldate(er['report_date'], t), days, er.get('date_estimated'))
            if cs.get('eps') is not None:
                nxt += t['expect'](num(cs['eps'], 2), money(cs['rev'], t) if cs.get('rev') else None, num(cs['year_ago_eps'], 2) if cs.get('year_ago_eps') is not None else None)
    beat = (cons or {}).get('beat_rate')
    if beat is not None:
        nxt += t['beat'](round(100 * beat))
    nxt = nxt.strip()
    hq = [(x.get('label'), x.get('headline') or {}) for x in reversed(qs[:8])]
    fm = lambda v: money(v, t)
    charts = (SV.bars([(l, h2.get('revenue')) for l, h2 in hq], fm, f"{en} — {t['chart_rev']}")
              + SV.bars([(l, h2.get('ni')) for l, h2 in hq], fm, f"{en} — {t['chart_ni']}")
              + (SV.hbars([(k, v[0]) for k, v in segs], fm, f"{en} — {t['h_seg'](en, per)}") if len(segs) > 1 else ''))
    slug = slug_for(r)
    url = f'{base}/{lang}/c/{slug}/'
    seg_rows = ''.join(f"<tr><td>{e(k)}</td><td class='num'>{e(money(v[0], t))}</td><td class='num'>{e(num(100 * v[0] / rev))}{e(t['pct'])}</td>"
                       f"<td class='num'>{e(pct((v[0] / v[1] - 1) * 100, t, True) if v[1] else '—')}</td></tr>" for k, v in segs[:12])
    hist = ''.join(f"<tr><td>{e(period(x.get('label'), t))}</td><td class='num'>{e(money((x.get('headline') or {}).get('revenue'), t))}</td>"
                   f"<td class='num'>{e(pct((x.get('headline') or {}).get('yoy'), t, True) or '—')}</td><td class='num'>{e(pct((x.get('headline') or {}).get('om'), t) or '—')}</td>"
                   f"<td class='num'>{e(money((x.get('headline') or {}).get('ni'), t))}</td></tr>" for x in qs[:8])
    qa = [(t['q_last'](en), lead.split(' ' + t['segs'])[0])]
    if len(segs) > 1:
        qa.append((t['q_how'](en), t['segs'] + t['sep'].join(f'{k} {money(v[0], t)} ({100 * v[0] / rev:.0f}{t["pct"]})' for k, v in segs[:4]) + '.'))
    if nxt:
        qa.append((t['q_when'](en), nxt))
    tiles = ''.join(f"<div class='seo-tile'><span>{e(k)}</span><b>{e(v)}</b></div>" for k, v in zip(t['tiles'], (
        money(rev, t), pct(h.get('yoy'), t, True) or '—', pct(h.get('om'), t) or '—', money(h.get('ni'), t), money(h.get('ocf'), t))))
    others = ' · '.join(f"<a href='{u}' hreflang='{k}'>{LANG_NAME[k]}</a>" for k, u in (('en', f'../../../c/{slug}/'), ('zh-Hans', f'../../../zh/c/{slug}/'),
                        ('es', f'../../../es/c/{slug}/'), ('fr', f'../../../fr/c/{slug}/')) if k in langs and k != lang)
    body = (f"<p class='crumbs'><a href='../../'>{e(t['crumb'])}</a> › {e(who)}</p><h1>{e(t['h1'](who, per))}</h1><p class='lead'>{e(lead)}</p>"
            f"<div class='seo-tiles'>{tiles}</div>" + sankey_figure(r['cik'], q.get('label'), f"{who} — {t['chart_sankey']}") + charts
            + (f'<p>{e(nxt)}</p>' if nxt else '')
            + (f"<h2>{e(t['h_seg'](en, per))}</h2><div class='tbl-wrap'><table><thead><tr>" + ''.join(f"<th{' class=num' if i else ''}>{e(x)}</th>" for i, x in enumerate(t['seg_head']))
               + f"</tr></thead><tbody>{seg_rows}</tbody></table></div>" if len(segs) > 1 else '')
            + f"<h2>{e(t['h_hist'])}</h2><div class='tbl-wrap'><table><thead><tr>" + ''.join(f"<th{' class=num' if i else ''}>{e(x)}</th>" for i, x in enumerate(t['hist_head']))
            + f"</tr></thead><tbody>{hist}</tbody></table></div>"
            + f"<h2>{e(t['faq'])}</h2>" + ''.join(f'<h3>{e(x)}</h3><p>{e(y)}</p>' for x, y in qa)
            + f"<p><a class='seo-cta' href='../../../#c-{r['cik']}'>{e(t['cta'])}</a></p><p class='muted'>{e(t['other'])}: {others}</p>"
            + f"<p class='muted'>{e(t['source'](en, q.get('form')))}</p>")
    ld = {'@context': 'https://schema.org', '@graph': [
        {'@type': 'WebPage', 'name': t['h1'](who, per), 'url': url, 'inLanguage': lang, 'dateModified': (q.get('filed') or '')[:10],
         'about': {'@type': 'Corporation', 'name': en, 'tickerSymbol': tk}},
        {'@type': 'FAQPage', 'mainEntity': [{'@type': 'Question', 'name': x, 'acceptedAnswer': {'@type': 'Answer', 'text': y}} for x, y in qa]}]}
    title = t['title'](who, per, money(rev, t), pct(h.get('yoy'), t, True)) + ' | Filing Flows'
    doc = seo.page(title, lead[:200], url, body, 3, base + '/og.png', ld)
    doc = doc.replace('<html lang="en">', f'<html lang="{lang}">', 1).replace('<link rel="canonical"', alternates(slug, base, langs) + '<link rel="canonical"', 1)
    return url, (q.get('filed') or '')[:10] or None, doc, who, rev


def patch_alternates(path, slug, base, langs):
    """Give an existing page (English or Chinese) the full set of language alternates."""
    try:
        txt = open(path, encoding='utf-8').read()
    except OSError:
        return
    txt = re.sub(r'<link rel="alternate" hreflang="[^"]+" href="[^"]*">', '', txt)
    if '<link rel="canonical"' in txt:
        txt = txt.replace('<link rel="canonical"', alternates(slug, base, langs) + '<link rel="canonical"', 1)
        open(path, 'w', encoding='utf-8').write(txt)


def write(site, base, langs=('es', 'fr')):
    base = base.rstrip('/')
    ix = read(os.path.join(site, 'data', 'index.json')) or {}
    latest = {}
    for r in (ix.get('companies') if isinstance(ix, dict) else ix) or []:
        if r['cik'] not in latest or (r.get('filed') or '') > (latest[r['cik']].get('filed') or ''):
            latest[r['cik']] = r
    hub = os.path.join(site, 'disclosures', 'data')
    urls = {lg: [] for lg in langs}
    listed = {lg: [] for lg in langs}
    for cik, r in latest.items():
        if not r.get('ticker'):
            continue
        slug = slug_for(r)
        c = read(os.path.join(site, 'data', 'c', f'{cik}.json'))
        er = read(os.path.join(hub, 'research', 'earnings', 'c', f"{r['ticker']}.json"))
        cons = read(os.path.join(hub, 'consensus', 'c', f'{cik}.json'))
        have = {'en'} | ({'zh-Hans'} if os.path.exists(os.path.join(site, 'zh', 'c', slug, 'index.html')) else set()) | set(langs)
        made = False
        for lg in langs:
            out = company(lg, r, c, er, cons, base, have)
            if not out:
                continue
            url, mod, doc, who, rev = out
            d = os.path.join(site, lg, 'c', slug)
            os.makedirs(d, exist_ok=True)
            open(os.path.join(d, 'index.html'), 'w', encoding='utf-8').write(doc)
            urls[lg].append((url, mod))
            listed[lg].append((who, slug, rev))
            made = True
        if made:
            patch_alternates(os.path.join(site, 'c', slug, 'index.html'), slug, base, have)
            if 'zh-Hans' in have:
                patch_alternates(os.path.join(site, 'zh', 'c', slug, 'index.html'), slug, base, have)
            en_page = os.path.join(site, 'c', slug, 'index.html')
            try:
                txt = open(en_page, encoding='utf-8').read()
                if 'class="seo-langs"' not in txt and '</main>' in txt:
                    links = ' · '.join(f"<a href='../../{lg}/c/{slug}/' hreflang='{lg}'>{LANG_NAME[lg]}</a>" for lg in langs)
                    open(en_page, 'w', encoding='utf-8').write(txt.replace('</main>', f"<p class='muted seo-langs'>{links}</p></main>", 1))
            except OSError:
                pass
    robots = os.path.join(site, 'robots.txt')
    txt = open(robots).read() if os.path.exists(robots) else f'User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n'
    for lg in langs:
        t = L[lg]
        if listed[lg]:
            items = ''.join(f"<li><a href='c/{s}/'>{e(t['idx_item'](w))}</a></li>" for w, s, _ in sorted(listed[lg], key=lambda x: -x[2]))
            body = (f"<p class='crumbs'><a href='../'>Filing Flows</a> › {e(t['crumb'])}</p><h1>{e(t['idx_h1'](num(len(listed[lg]), 0)))}</h1>"
                    f"<p class='lead'>{e(t['idx_lead'])}</p><ul class='seo-list'>{items}</ul>")
            doc = seo.page(t['idx_title'], t['idx_lead'][:200], f'{base}/{lg}/', body, 1, base + '/og.png').replace('<html lang="en">', f'<html lang="{lg}">', 1)
            os.makedirs(os.path.join(site, lg), exist_ok=True)
            open(os.path.join(site, lg, 'index.html'), 'w', encoding='utf-8').write(doc)
            urls[lg].insert(0, (f'{base}/{lg}/', None))
        sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        sm += [f'<url><loc>{xesc(u)}</loc>' + (f'<lastmod>{m}</lastmod>' if m else '') + '</url>' for u, m in urls[lg]]
        sm.append('</urlset>')
        open(os.path.join(site, f'sitemap-{lg}.xml'), 'w', encoding='utf-8').write('\n'.join(sm))
        if f'sitemap-{lg}.xml' not in txt:
            txt = txt.rstrip('\n') + f'\nSitemap: {base}/sitemap-{lg}.xml\n'
    open(robots, 'w').write(txt)
    return {lg: len(listed[lg]) for lg in langs}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', default='_site')
    ap.add_argument('--site-url', default=os.environ.get('SITE_URL', '') or 'https://filing-flows.com')
    a = ap.parse_args()
    m = re.search(r'https?://[^\s"]+', a.site_url or '')
    print('pages:', write(a.site, m.group(0) if m else 'https://filing-flows.com'))
