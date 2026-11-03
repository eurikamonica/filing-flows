"""The home page's first HTML, before the app draws (web/index.html: <main id="app">): what the site is, who reported
this week, who reports next, and the pages to explore — plain links a crawler reads without running the app, and the
freshest internal links on the site (the home page is crawled most often). The app replaces it as soon as it starts.

    python scripts/seo_home.py --site _site
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seo  # noqa: E402

e, display_name, fdate = seo.e, seo.display_name, seo.fdate
MARK = '<div class="loading">Loading…</div>'


def read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def block(site, today=None):
    today = today or dt.date.today()
    ix = read(os.path.join(site, 'data', 'index.json')) or {}
    rows = (ix.get('companies') if isinstance(ix, dict) else ix) or []
    has = lambda *p: os.path.exists(os.path.join(site, *p, 'index.html'))
    week = (today - dt.timedelta(days=7)).isoformat()
    fresh = sorted([r for r in rows if (r.get('filed') or '') >= week and r.get('ticker') and has('c', seo.slug_for(r))], key=lambda r: -(r.get('revenue') or 0))
    out = ["<section class='static-home'><h1>See Where the Money Really Goes.</h1>"
           "<p>SEC Filings, Made Visual. Every new 10-Q, 10-K and earnings release on SEC EDGAR drawn as a Sankey, from revenue to costs, profit and cash; "
           "13F holdings, insider and Congress trades, 8-K events, earnings quality and hidden financial obligations.</p>"]
    if fresh:
        out.append(f"<h2>Reported this week ({len(fresh)})</h2><ul>" + ''.join(
            f"<li><a href='c/{seo.slug_for(r)}/'>{e(display_name(r.get('name')))} ({e(r['ticker'])}) {e(r.get('label'))} earnings</a>: revenue {e(r.get('rev') or '—')}"
            + (f", {seo.pct(r.get('yoy'))} Y/Y" if r.get('yoy') is not None else '') + '</li>' for r in fresh[:40]) + '</ul>')
    cal = read(os.path.join(site, 'disclosures', 'data', 'research', 'earnings', 'index.json')) or {}
    F = cal.get('fields') or []
    nxt = sorted([dict(zip(F, x)) for x in cal.get('rows') or []], key=lambda r: (r.get('report_date') or '', r.get('ticker') or '')) if F else []
    end = (today + dt.timedelta(days=7)).isoformat()
    slug = {(r.get('ticker') or '').upper(): seo.slug_for(r) for r in rows if r.get('ticker')}
    nxt = [r for r in nxt if today.isoformat() <= (r.get('report_date') or '') <= end and slug.get((r.get('ticker') or '').upper())
           and has('c', slug[r['ticker'].upper()], 'earnings-date')]
    if nxt:
        out.append(f"<h2>Reporting in the next seven days</h2><ul>" + ''.join(
            f"<li><a href='c/{slug[r['ticker'].upper()]}/earnings-date/'>{e(display_name(r.get('name')))} ({e(r['ticker'])}) earnings {e(fdate(r['report_date']))}: what to expect</a></li>"
            for r in nxt[:40]) + '</ul>')
    explore = [('c/', 'Every company A–Z'), ('daily/', 'Today in the filings'), ('events/', 'Material 8-K events'), ('disclosures/signals/', 'Stock signals'),
               ('disclosures/smart-money/', '13F smart money'), ('disclosures/insider-trades/', 'Insider trading'), ('disclosures/congress-trades/', 'Congress stock trades'),
               ('disclosures/activist-stakes/', 'Activist 13D stakes'), ('disclosures/guidance-track-record/', 'Guidance track record'),
               ('disclosures/short-interest/', 'Short interest'), ('disclosures/insider-signals/', 'Do insider trades predict the stock?'), ('events/impact/', 'Which 8-K items move stocks'), ('disclosures/earnings-quality/', 'Earnings quality scores'), ('disclosures/cash-runway/', 'Cash runway'), ('disclosures/sector-rotation/', 'Sector rotation'), ('gamma/', 'Industries'),
               ('chains/', 'Supply chains & themes'), ('m/', '13F managers'), ('o/', 'Officials’ trades'), ('compare/', 'Compare companies'), ('zh/', '中文')]
    out.append("<h2>Explore</h2><ul>" + ''.join(f"<li><a href='{u}'>{e(l)}</a></li>" for u, l in explore if has(*u.strip('/').split('/'))) + '</ul></section>')
    return ''.join(out)


def write(site, today=None):
    p = os.path.join(site, 'index.html')
    t = open(p, encoding='utf-8').read()
    if MARK not in t:
        return False
    open(p, 'w', encoding='utf-8').write(t.replace(MARK, block(site, today), 1))
    return True


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', default='_site')
    a = ap.parse_args()
    print('home page links:', 'written' if write(a.site) else 'no placeholder found')
