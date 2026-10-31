"""Search-engine pages for the people behind the disclosures (Disclosures → People & index; disclosures/app/people.py):

    m/<slug>/index.html   "Berkshire Hathaway 13F portfolio: top holdings, latest changes and a copy-the-13F backtest"
    o/<slug>/index.html   "Nancy Pelosi stock trades: disclosed transactions, performance against SPY, committees"
    m/index.html, o/index.html   the lists
    sitemap-people.xml (listed in robots.txt next to sitemap.xml)

Runs after the Disclosure Hub is staged (scan.yml), from its published data:
    python scripts/seo_people.py --people _site/disclosures/data/research/people --out _site --site-url https://filing-flows.com
"""
import argparse
import json
import os
import re
import sys
from xml.sax.saxutils import escape as xesc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seo  # noqa: E402
import seo_svg as SV  # noqa: E402

e = seo.e
MAX_PAGES = 400             # per kind: the page count and the build stay small


def money(v):
    return seo.money(v) if v is not None else "—"


def pct(v, signed=True):
    if v is None:
        return "—"
    return f"{v * 100:+.1f}%" if signed else f"{v * 100:.1f}%"


def amount(lo, hi):
    if lo is None:
        return "—"
    return f"${lo:,.0f}–${hi:,.0f}" if hi else f"over ${lo:,.0f}"


def line_svg(rows, w=860, h=260):
    """A two-line chart (the clone and SPY, both starting at 1) as inline SVG: rows = [[YYYY-MM, clone, spy], …]."""
    pts = [r for r in rows if r[1] is not None and r[2] is not None]
    if len(pts) < 2:
        return ""
    lo = min(min(r[1], r[2]) for r in pts + [["", 1.0, 1.0]])
    hi = max(max(r[1], r[2]) for r in pts + [["", 1.0, 1.0]])
    pad = (hi - lo) * 0.08 or 0.05
    lo, hi = lo - pad, hi + pad
    x = lambda i: 48 + i * (w - 64) / (len(pts) - 1)
    y = lambda v: 16 + (hi - v) * (h - 48) / (hi - lo)
    path = lambda k: " ".join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(r[k]):.1f}" for i, r in enumerate(pts))
    ticks = "".join(f"<text x='{x(i):.1f}' y='{h - 8}' font-size='11' text-anchor='middle' fill='currentColor' opacity='.65'>{e(r[0])}</text>"
                    for i, r in enumerate(pts) if i % max(1, len(pts) // 6) == 0 or i == len(pts) - 1)
    base = f"<line x1='48' x2='{w - 16}' y1='{y(1.0):.1f}' y2='{y(1.0):.1f}' stroke='currentColor' opacity='.25' stroke-dasharray='3 3'/>"
    return (f"<svg viewBox='0 0 {w} {h}' role='img' aria-label='Clone portfolio against SPY'>{base}"
            f"<path d='{path(2)}' fill='none' stroke='#8a8f98' stroke-width='2'/><path d='{path(1)}' fill='none' stroke='#17734a' stroke-width='2.5'/>"
            f"{ticks}<text x='52' y='14' font-size='12' fill='#17734a'>clone</text><text x='100' y='14' font-size='12' fill='#8a8f98'>SPY</text></svg>")


def manager_page(m, base):
    name, slug = m["name"], m["slug"]
    url = f"{base}/m/{slug}/"
    c = m.get("clone") or {}
    title = f"{name} 13F portfolio: top holdings, latest changes and a copy-the-13F backtest | Filing Flows"
    desc = (f"{name}'s 13F for the quarter ended {m['period']} (filed {seo.fdate(m['filed'])}): {m['positions']} common-share positions, "
            f"{money(m['aum'])} reported. "
            + (f"Copying each 13F the day after it was filed returned {pct(c.get('total'))} from {seo.fdate(c.get('start'))} to "
               f"{seo.fdate(c.get('end'))}, against {pct(c.get('spy_total'))} for SPY." if c.get("total") is not None else ""))
    rows = "".join(f"<tr><td>{e(h[0])}</td><td>{e(h[1])}</td><td class='num'>{pct(h[2], False)}</td><td class='num'>{money(h[3])}</td>"
                   f"<td>{e((h[4] or 'unchanged').lower())}{' ' + pct(h[5] / 100) if h[5] is not None and h[4] in ('INCREASE', 'DECREASE') else ''}</td></tr>"
                   for h in (m.get("holdings") or [])[:25] if h[0])
    lst = lambda xs: "".join(f"<li><b>{e(a[0])}</b> <span class='muted'>{e((a[1] or '').lower())}{' ' + pct(a[2] / 100) if a[2] is not None and a[1] not in ('NEW', 'EXIT') else ''}</span></li>" for a in xs)
    tiles = "".join(f"<div class='seo-tile'><span>{e(k)}</span><b>{e(v)}</b></div>" for k, v in (
        ("Reported 13F assets", money(m["aum"])), ("Positions (common)", f"{m['positions']}"), ("Quarter", m["period"]),
        ("Clone return", pct(c.get("total"))), ("SPY, same days", pct(c.get("spy_total"))), ("Clone max drawdown", pct(c.get("max_dd")))))
    rec = m.get("record") or {}
    record = (f"<h2>Track record</h2><p>Of {rec.get('scored')} position changes scored in {rec.get('decisions')} separate decisions, "
              f"{pct(rec.get('hit'), False)} were on the right side of SPY over the next three months (Disclosures → Smart money).</p>"
              if rec.get("scored") else "")
    body = f"""<p class="crumbs"><a href="../../">Filing Flows</a> › <a href="../">13F managers</a> › {e(name)}</p>
<h1>{e(name)}: 13F portfolio and what copying it returned</h1>
<p class="lead">{e(desc)}</p>
<div class="seo-tiles">{tiles}</div>
<h2>Copying the 13F</h2>
<figure class="seo-chart" style="width:auto;margin:12px 0">{line_svg(c.get('monthly') or [])}</figure>
<p class="muted">Each 13F bought at the close of the first trading day after it was filed and held, drifting, until the next one;
value-weighted over the common-share positions with a price ({pct(c.get('coverage'), False)} of the portfolio on average);
{c.get('filings') or 0} filings since {e(seo.fdate(c.get('first_filing')))}. Price returns for the clone and SPY alike (no dividends,
no costs). A 13F lists only US long positions at quarter end, reported up to 45 days later.</p>
<h2>Largest holdings ({e(m['period'])})</h2>
{SV.hbars([(f"{h[0]} · {h[1]}", h[3]) for h in (m.get('holdings') or []) if h[0]], money, f"{name}: largest 13F holdings, {m['period']}", n=15)}
{SV.diverging([(a[0], a[2]) for a in (m.get('adds') or []) if a[2] is not None] + [(a[0], -abs(a[2])) for a in (m.get('cuts') or []) if a[2] is not None],
              lambda v: f"{v:+.0f}%", f"{name}: biggest adds and cuts in the quarter (change in shares)", n=14)}
<div class="tbl-wrap"><table><thead><tr><th>Ticker</th><th>Company</th><th class="num">Weight</th><th class="num">Value</th><th>Change in the quarter</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>Biggest adds</h2><ul class="seo-list">{lst(m.get('adds') or []) or '<li class="muted">None reported.</li>'}</ul>
<h2>Biggest cuts</h2><ul class="seo-list">{lst(m.get('cuts') or []) or '<li class="muted">None reported.</li>'}</ul>
{record}
<p><a class="seo-cta" href="../../disclosures/#people/m-{e(m['cik'])}">Open in Disclosures →</a> <span class="muted">every quarter, the clone month by month, the smart-money record</span></p>
<p class="muted">Source: SEC Form 13F-HR, filer CIK {e(m['cik'])}. Not investment advice.</p>"""
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "Organization", "name": name, "url": url, "identifier": f"SEC CIK {m['cik']}"},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Filing Flows", "item": base + "/"},
            {"@type": "ListItem", "position": 2, "name": "13F managers", "item": base + "/m/"},
            {"@type": "ListItem", "position": 3, "name": name, "item": url}]}]}
    return url, seo.page(title, desc, url, body, 2, base + "/og.png", ld)


def official_page(o, base):
    name, slug = o["name"], o["slug"]
    url = f"{base}/o/{slug}/"
    perf = o.get("performance") or {}
    role = "Senator" if o.get("chamber") == "US Senate" else "Representative" if o.get("chamber") == "US House" else "Official"
    who = f"{name}" + (f" ({(o.get('party') or '')[:1]}-{o.get('state')})" if o.get("party") and o.get("state") else "")
    title = f"{name} stock trades: disclosed transactions, performance against SPY and committees | Filing Flows"
    desc = (f"{role} {name}'s disclosed stock trades: {perf.get('n') or 0} on file"
            + (f", the scored ones averaging {pct(perf.get('follow'))} against SPY over the 63 trading days after disclosure"
               if perf.get("follow") is not None else "")
            + (f"; committees: {', '.join(c[1] for c in (o.get('committees') or [])[:3] if len(c[0]) == 4)}" if o.get("committees") else "") + ".")
    tiles = "".join(f"<div class='seo-tile'><span>{e(k)}</span><b>{e(v)}</b></div>" for k, v in (
        ("Chamber", o.get("chamber") or "—"), ("Trades on file", f"{perf.get('n') or 0}"), ("Scored", f"{perf.get('scored') or 0}"),
        ("After disclosure vs SPY", pct(perf.get("follow"))), ("Right side of SPY", pct(perf.get("hit"), False))))
    coms = "".join(f"<li>{e(c[1])}{' — ' + e(c[2]) if c[2] else ''}</li>" for c in o.get("committees") or [] if len(c[0]) == 4)
    ov = "".join(f"<tr><td>{e(x['date'])}</td><td><b>{e(x['ticker'])}</b></td><td>{e(x['type'])}</td><td>{e(amount(x.get('amount_min'), x.get('amount_max')))}</td>"
                 f"<td>{e(x['committee'])}</td><td>{e(x['area'])}</td></tr>" for x in o.get("overlaps") or [])
    rec = "".join(f"<tr><td>{e(t[0])}</td><td><b>{e(t[1])}</b></td><td>{e(t[2])}</td><td>{e(amount(t[3], t[4]))}</td><td>{e(t[5] or '')}</td><td>{e(t[6] or '')}</td></tr>"
                  for t in (o.get("recent") or [])[:30])
    tot = {}
    for x in o.get("recent") or []:
        mid = ((x[3] or 0) + (x[4] or x[3] or 0)) / 2
        k = (x[1], 'buy' if 'purchase' in str(x[2]).lower() else 'sell')
        tot[k] = tot.get(k, 0) + mid
    items = sorted(((f"{tk} ({'bought' if s == 'buy' else 'sold'})", v if s == 'buy' else -v) for (tk, s), v in tot.items()), key=lambda z: -abs(z[1]))
    trade_chart = SV.diverging(items, lambda v: money(abs(v)), f"{name}: recent trades by stock (middle of each reported range; bought → right, sold ← left)", n=14)
    body = f"""<p class="crumbs"><a href="../../">Filing Flows</a> › <a href="../">Officials</a> › {e(name)}</p>
<h1>{e(who)}: disclosed stock trades</h1>
<p class="lead">{e(desc)}</p>
<div class="seo-tiles">{tiles}</div>
{f'<h2>Committees</h2><ul class="seo-list">{coms}</ul>' if coms else ''}
{f'<h2>Trades in sectors under their committees</h2><p class="muted">A trade in a sector that one of the member’s committees oversees (the map is published with the data). A fact pattern from public disclosures, not a finding of wrongdoing.</p><div class="tbl-wrap"><table><thead><tr><th>Date</th><th>Ticker</th><th>Type</th><th>Amount</th><th>Committee</th><th>Area</th></tr></thead><tbody>{ov}</tbody></table></div>' if ov else ''}
{trade_chart}
{f'<h2>Recent disclosed trades</h2><div class="tbl-wrap"><table><thead><tr><th>Date</th><th>Ticker</th><th>Type</th><th>Amount</th><th>Owner</th><th>Filed</th></tr></thead><tbody>{rec}</tbody></table></div>' if rec else ''}
<p class="muted">Performance: each scored trade’s stock return less SPY’s over the 63 trading days after it was disclosed (a sale counts when the
stock then lagged), weighted by the middle of the reported amount range{', ' + str(perf.get('first')) + ' to ' + str(perf.get('last')) if perf.get('first') else ''}.</p>
<p><a class="seo-cta" href="../../disclosures/#people/o-{e(slug)}">Open in Disclosures →</a></p>
<p class="muted">Source: House and Senate periodic transaction reports; committees from the congress-legislators project. Not investment advice.</p>"""
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "Person", "name": name, "jobTitle": f"U.S. {role}" if role != "Official" else None, "url": url},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Filing Flows", "item": base + "/"},
            {"@type": "ListItem", "position": 2, "name": "Officials", "item": base + "/o/"},
            {"@type": "ListItem", "position": 3, "name": name, "item": url}]}]}
    return url, seo.page(title, desc, url, body, 2, base + "/og.png", ld)


def list_page(title, desc, url, items, depth=1):
    lis = "".join(f"<li><a href='{e(slug)}/'>{e(label)}</a> <span class='muted'>{e(note)}</span></li>" for slug, label, note in items)
    body = f"<p class='crumbs'><a href='../'>Filing Flows</a> › {e(title)}</p><h1>{e(title)}</h1><p class='lead'>{e(desc)}</p><ul class='seo-list'>{lis}</ul>"
    return seo.page(f"{title} | Filing Flows", desc, url, body, depth, url.rsplit("/", 2)[0] + "/og.png")


def write_pages(people_dir, out_dir, base):
    base = (base or "").rstrip("/")
    if not base or not os.path.isdir(people_dir):
        return 0, 0

    def load(rel):
        try:
            return json.load(open(os.path.join(people_dir, rel), encoding="utf-8"))
        except (OSError, ValueError):
            return None
    urls, nm, no = [], 0, 0
    mg = load("managers.json") or {}
    F = mg.get("fields") or []
    items = []
    for r in (mg.get("rows") or [])[:MAX_PAGES]:
        row = dict(zip(F, r))
        m = load(f"m/{row['cik']}.json")
        if not m or not re.fullmatch(r"[a-z0-9-]{1,80}", m.get("slug") or ""):
            continue
        url, doc = manager_page(m, base)
        d = os.path.join(out_dir, "m", m["slug"])
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(doc)
        urls.append((url, m.get("filed")))
        items.append((m["slug"], m["name"], f"{money(m['aum'])} · {m['period']}"))
        nm += 1
    if items:
        open(os.path.join(out_dir, "m", "index.html"), "w", encoding="utf-8").write(list_page(
            "13F managers", "The largest 13F filers: their latest portfolios, last quarter's changes and what copying each 13F returned.",
            base + "/m/", items))
        urls.append((base + "/m/", None))
    of = load("officials.json") or {}
    F = of.get("fields") or []
    items = []
    for r in (of.get("rows") or [])[:MAX_PAGES]:
        row = dict(zip(F, r))
        o = load(f"o/{row['slug']}.json")
        if not o or not re.fullmatch(r"[a-z0-9-]{1,80}", o.get("slug") or ""):
            continue
        url, doc = official_page(o, base)
        d = os.path.join(out_dir, "o", o["slug"])
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(doc)
        urls.append((url, (o.get("performance") or {}).get("last")))
        items.append((o["slug"], o["name"], f"{o.get('chamber') or ''} · {(o.get('performance') or {}).get('n') or 0} trades"))
        no += 1
    if items:
        open(os.path.join(out_dir, "o", "index.html"), "w", encoding="utf-8").write(list_page(
            "Officials' stock trades", "Members of Congress with disclosed stock trades: what they traded, how it did against SPY, their committees.",
            base + "/o/", sorted(items, key=lambda x: x[1])))
        urls.append((base + "/o/", None))
    if urls:
        sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for u, mod in urls:
            sm.append(f"<url><loc>{xesc(u)}</loc>" + (f"<lastmod>{xesc(str(mod)[:10])}</lastmod>" if mod else "") + "</url>")
        sm.append("</urlset>")
        open(os.path.join(out_dir, "sitemap-people.xml"), "w", encoding="utf-8").write("\n".join(sm))
        robots = os.path.join(out_dir, "robots.txt")
        txt = open(robots).read() if os.path.exists(robots) else f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n"
        if "sitemap-people.xml" not in txt:
            open(robots, "w").write(txt.rstrip("\n") + f"\nSitemap: {base}/sitemap-people.xml\n")
    return nm, no


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--people", default="_site/disclosures/data/research/people")
    ap.add_argument("--out", default="_site")
    ap.add_argument("--site-url", default="")
    a = ap.parse_args()
    base = a.site_url.strip().rstrip("/")
    if not base:                                 # the repository variable SITE_URL, forgiving quotes, spaces and "SITE_URL = …"
        v = os.environ.get("SITE_URL", "").strip().strip("'\"").strip()
        m = re.match(r"^[A-Z][A-Z0-9_]*\s*[=:]\s*(.*)$", v)
        base = (m.group(1) if m else v).strip().strip("'\"").strip().rstrip("/")
    cname = os.path.join(a.out, "CNAME")         # build_site.py writes the custom domain here: same address as the other pages
    if not base and os.path.exists(cname):
        host = open(cname, encoding="utf-8").read().strip()
        base = f"https://{host}" if host else ""
    if not base and os.environ.get("GITHUB_REPOSITORY"):
        owner, repo = os.environ["GITHUB_REPOSITORY"].split("/", 1)
        base = f"https://{owner.lower()}.github.io/{repo}"
    m, o = write_pages(a.people, a.out, base)
    print(f"people pages: {m} managers, {o} officials")
