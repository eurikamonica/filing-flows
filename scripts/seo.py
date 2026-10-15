"""Search-engine pages: the Sankey site is one page with #c-… routes, which search engines do not index. At build time
this writes a plain, readable HTML page per company and per sector, plus sitemap.xml and robots.txt:

    c/<ticker>/index.html     "NVIDIA (NVDA) Q2 FY27 earnings: revenue $96.2B, +106% Y/Y" — the latest quarter's figures,
                              the analysis, 8 quarters of history, the company's own description, peers, and a link
                              into the interactive chart (/#c-<cik>)
    c/index.html              every company A–Z
    sector/<id>/index.html    the sector's companies by revenue
    sitemap.xml, robots.txt

    python scripts/seo.py --data _site/data --out _site --site-url https://filing-flows.com
(build_site.py calls write_pages() itself.)
"""
import argparse
import datetime as dt
import html
import json
import os
import re
from xml.sax.saxutils import escape as xesc

e = lambda s: html.escape(str(s if s is not None else ""), quote=True)
KEEP_UPPER = {"AI", "AMD", "AT&T", "BP", "CVS", "HP", "IBM", "II", "III", "IV", "LLC", "LP", "NV", "PLC", "SA", "UPS", "USA", "US", "NVIDIA", "REIT"}


def display_name(name):
    name = re.sub(r"\s*[/(\\][A-Z]{2}[/)\\]?\s*$", "", (name or "").strip())
    if name.upper() == name:
        name = " ".join(w if (w.upper() in KEEP_UPPER or re.search(r"\d", w)) else w.capitalize() for w in name.split())
    return re.sub(r",?\s+(Inc|Corp|Corporation|Co|Ltd|Plc|Holdings|Group)\.?$", "", name)


def money(v):
    if v is None:
        return "—"
    a, s = abs(v), "−" if v < 0 else ""
    return f"{s}${a / 1e9:.1f}B" if a >= 0.95e9 else f"{s}${a / 1e6:.0f}M" if a >= 0.95e6 else f"{s}${a / 1e3:.0f}K"


def pct(v, signed=True):
    return "—" if v is None else (f"{v:+.0f}%" if signed else f"{v:.1f}%")


def fdate(s):
    try:
        d = dt.date.fromisoformat(str(s)[:10])
        return f"{d:%b} {d.day}, {d.year}"
    except ValueError:
        return s or ""


def slug_for(e_):
    t = (e_.get("ticker") or "").lower().replace(".", "-")
    return t if re.fullmatch(r"[a-z0-9-]{1,12}", t) else f"cik-{e_['cik']}"


def page(title, desc, canonical, body, depth, image, jsonld=None):
    up = "../" * depth
    ld = f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(desc)}"><link rel="canonical" href="{e(canonical)}">
<meta property="og:type" content="article"><meta property="og:site_name" content="Filing Flows"><meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{e(canonical)}"><meta property="og:image" content="{e(image)}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{e(title)}"><meta name="twitter:description" content="{e(desc)}"><meta name="twitter:image" content="{e(image)}">
<link rel="stylesheet" href="{up}styles.css"><link rel="stylesheet" href="{up}seo.css">{ld}
</head><body><header class="seo-top"><a class="seo-brand" href="{up}">Filing Flows</a><nav><a href="{up}#home">Latest</a><a href="{up}c/">Companies</a><a href="{up}#sectors">Sectors</a><a href="{up}disclosures/">Disclosures</a></nav></header>
<main class="seo">{body}</main>
<footer class="seo-foot">Figures read automatically from SEC filings (XBRL and earnings releases); errors are possible. Not investment advice. <a href="{up}">filing-flows.com</a></footer>
</body></html>"""


def company_page(c, ix_entry, peers, sector_name, base, depth=2):
    p, quarters = c["profile"], c.get("quarters") or []
    q = quarters[0] if quarters else {}
    h = q.get("headline") or {}
    name, t = display_name(p["name"]), (p.get("tickers") or [""])[0]
    who = f"{name} ({t})" if t else name
    form = q.get("form") or ""
    status = " (preliminary, from the earnings release)" if form == "8-K" else ""
    title = f"{who} {q.get('label', '')} earnings: revenue {h.get('rev_fmt') or money(h.get('revenue'))}" + (
        f", {pct(h.get('yoy'))} Y/Y" if h.get("yoy") is not None else "") + " | Filing Flows"
    desc = (f"{name}'s {q.get('label', '')} {form} filed {fdate(q.get('filed'))}{status}: revenue {h.get('rev_fmt') or money(h.get('revenue'))}"
            + (f" ({pct(h.get('yoy'))} Y/Y)" if h.get("yoy") is not None else "")
            + (f", operating margin {pct(h.get('om'), False)}" if h.get("om") is not None else "")
            + (f", net earnings {h.get('ni_fmt') or money(h.get('ni'))}" if h.get("ni") is not None else "")
            + ". Income statement and cash flow as a Sankey diagram, read from the SEC filing.")
    url = f"{base}/c/{slug_for(ix_entry)}/"
    app = "../" * depth + f"#c-{p['cik']}"
    rows = "".join(
        f"<tr><td>{e(x.get('label'))}</td><td>{e(x.get('form'))}</td><td>{e(fdate(x.get('filed')))}</td>"
        f"<td class='num'>{e((x.get('headline') or {}).get('rev_fmt') or money((x.get('headline') or {}).get('revenue')))}</td>"
        f"<td class='num'>{e(pct((x.get('headline') or {}).get('yoy')))}</td><td class='num'>{e(pct((x.get('headline') or {}).get('om'), False))}</td>"
        f"<td class='num'>{e(money((x.get('headline') or {}).get('ni')))}</td><td class='num'>{e(money((x.get('headline') or {}).get('ocf')))}</td></tr>"
        for x in quarters[:8])
    analysis = "".join(f"<p>{e(a)}</p>" for a in (q.get("analysis") or [])[:4])
    intro = c.get("intro") or {}
    about = (f"<h2>About {e(name)}</h2><blockquote>{e((intro.get('text') or '')[:900])}</blockquote>"
             f"<p class='muted'>In its own words, from its {e(intro.get('source') or 'annual report')}"
             + (f", filed {e(fdate(intro.get('filed')))}" if intro.get("filed") else "") + ".</p>") if intro.get("text") else ""
    peer_links = "".join(f"<li><a href='../{slug_for(x)}/'>{e(display_name(x.get('name')))}{' (' + e(x['ticker']) + ')' if x.get('ticker') else ''}</a> "
                         f"<span class='muted'>{e(x.get('label'))} · revenue {e(x.get('rev') or '—')}{' · ' + pct(x.get('yoy')) + ' Y/Y' if x.get('yoy') is not None else ''}</span></li>"
                         for x in peers)
    tiles = "".join(f"<div class='seo-tile'><span>{e(k)}</span><b>{e(v)}</b></div>" for k, v in (
        ("Revenue", h.get("rev_fmt") or money(h.get("revenue"))), ("Year over year", pct(h.get("yoy"))),
        ("Operating margin", pct(h.get("om"), False)), ("Net earnings", h.get("ni_fmt") or money(h.get("ni"))),
        ("Operating cash flow", money(h.get("ocf")))))
    body = f"""<p class="crumbs"><a href="../../">Filing Flows</a> › <a href="../../sector/{e(p.get('sector') or 'other')}/">{e(sector_name)}</a> › {e(who)}</p>
<h1>{e(who)} earnings: {e(q.get('label', ''))}</h1>
<p class="lead">{e(desc)}</p>
<div class="seo-tiles">{tiles}</div>
<p><a class="seo-cta" href="{e(app)}">Open the interactive Sankey →</a> <span class="muted">revenue → costs → profit → cash, with Y/Y and Q/Q for every line</span></p>
{f'<h2>What changed this quarter</h2>{analysis}' if analysis else ''}
<h2>Quarterly history</h2>
<div class="tbl-wrap"><table><thead><tr><th>Quarter</th><th>Form</th><th>Filed</th><th class="num">Revenue</th><th class="num">Y/Y</th><th class="num">Op. margin</th><th class="num">Net earnings</th><th class="num">Op. cash flow</th></tr></thead><tbody>{rows}</tbody></table></div>
{about}
{f'<h2>Other {e(p.get("industry") or sector_name)} companies</h2><ul class="seo-list">{peer_links}</ul>' if peer_links else ''}
<p class="muted">Source: <a href="{e(q.get('index_url') or q.get('doc_url') or '')}" rel="nofollow">{e(name)} {e(form)} on SEC EDGAR</a> · CIK {e(p['cik'])} · {e(p.get('industry') or '')}</p>"""
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "Corporation", "name": name, "tickerSymbol": t or None, "url": url},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Filing Flows", "item": base + "/"},
            {"@type": "ListItem", "position": 2, "name": sector_name, "item": f"{base}/sector/{p.get('sector') or 'other'}/"},
            {"@type": "ListItem", "position": 3, "name": who, "item": url}]}]}
    return url, page(title, desc, url, body, depth, base + "/og.png", ld)


def list_page(title, desc, url, intro, items, depth):
    lis = "".join(f"<li><a href='{'../' * depth}c/{slug_for(x)}/'>{e(display_name(x.get('name')))}{' (' + e(x['ticker']) + ')' if x.get('ticker') else ''}</a> "
                  f"<span class='muted'>{e(x.get('label'))} · revenue {e(x.get('rev') or '—')}{' · ' + pct(x.get('yoy')) + ' Y/Y' if x.get('yoy') is not None else ''}</span></li>"
                  for x in items)
    body = f"<p class='crumbs'><a href='{'../' * depth}'>Filing Flows</a> › {e(title)}</p><h1>{e(title)}</h1><p class='lead'>{e(intro)}</p><ul class='seo-list'>{lis}</ul>"
    return page(f"{title} | Filing Flows", desc, url, body, depth, url.split("/c/")[0].split("/sector/")[0] + "/og.png")


def write_pages(data_dir, out_dir, base):
    base = (base or "").rstrip("/")
    if not base:
        return 0
    ix = json.load(open(os.path.join(data_dir, "index.json"), encoding="utf-8"))
    rows = ix["companies"] if isinstance(ix, dict) else ix
    names = ix.get("sector_names") or {}
    latest = {}
    for r in rows:                                  # one page per company: its newest quarter
        if r["cik"] not in latest or (r.get("filed") or "") > (latest[r["cik"]].get("filed") or ""):
            latest[r["cik"]] = r
    by_industry = {}
    for r in latest.values():
        by_industry.setdefault(r.get("sic") or r.get("industry"), []).append(r)
    urls, n = [(base + "/", None)], 0
    for cik, r in latest.items():
        try:
            c = json.load(open(os.path.join(data_dir, "c", f"{cik}.json"), encoding="utf-8"))
        except (OSError, ValueError):
            continue
        peers = sorted((x for x in by_industry.get(r.get("sic") or r.get("industry"), []) if x["cik"] != cik), key=lambda x: -(x.get("revenue") or 0))[:8]
        url, doc = company_page(c, r, peers, names.get(r.get("sector"), r.get("sector") or "Other"), base)
        d = os.path.join(out_dir, "c", slug_for(r))
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(doc)
        urls.append((url, r.get("filed")))
        n += 1
    az = sorted(latest.values(), key=lambda x: display_name(x.get("name")).lower())
    os.makedirs(os.path.join(out_dir, "c"), exist_ok=True)
    open(os.path.join(out_dir, "c", "index.html"), "w", encoding="utf-8").write(list_page(
        "Every company, A–Z", "Earnings Sankeys for every company that filed a 10-Q, 10-K or earnings release, A–Z.",
        base + "/c/", f"{len(az)} companies with an income-statement Sankey, newest quarter first in each page.", az, 1))
    urls.append((base + "/c/", None))
    for sid, sname in names.items():
        items = sorted((x for x in latest.values() if x.get("sector") == sid), key=lambda x: -(x.get("revenue") or 0))
        if not items:
            continue
        d = os.path.join(out_dir, "sector", sid)
        os.makedirs(d, exist_ok=True)
        url = f"{base}/sector/{sid}/"
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(list_page(
            f"{sname} earnings", f"Latest quarterly earnings of {len(items)} {sname} companies as Sankey diagrams: revenue, growth, margins.",
            url, f"{len(items)} {sname} companies by revenue, each with its latest quarter drawn from the SEC filing.", items, 2))
        urls.append((url, None))
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u, mod in urls:
        sm.append(f"<url><loc>{xesc(u)}</loc>" + (f"<lastmod>{xesc(str(mod)[:10])}</lastmod>" if mod else "") + "</url>")
    sm.append("</urlset>")
    open(os.path.join(out_dir, "sitemap.xml"), "w", encoding="utf-8").write("\n".join(sm))
    open(os.path.join(out_dir, "robots.txt"), "w").write(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="_site/data")
    ap.add_argument("--out", default="_site")
    ap.add_argument("--site-url", default=os.environ.get("SITE_URL", ""))
    a = ap.parse_args()
    print(f"{write_pages(a.data, a.out, a.site_url)} company pages written")
