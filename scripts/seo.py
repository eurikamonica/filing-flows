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
    name = re.sub(r",?\s+(?:&\s+)?(Inc|Corp|Corporation|Co|Ltd|Plc|Holdings|Group)\.?$", "", name)
    return re.sub(r"\bJpmorgan\b", "JPMorgan", name).rstrip(" &,")


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


ORD = {"1": "first", "2": "second", "3": "third", "4": "fourth"}


def period_words(label):
    """'Q2 2026' → 'second quarter 2026', 'Q2 FY27' → 'second quarter fiscal 2027', 'FY2025' → 'fiscal 2025' — the words
    earnings releases use in their headlines ("Onto Innovation reports second quarter 2026 results"), and people search."""
    m = re.fullmatch(r"Q([1-4])\s+(?:FY)?(\d{2}|\d{4})", (label or "").strip())
    if m:
        y = m[2] if len(m[2]) == 4 else "20" + m[2]
        return f"{ORD[m[1]]} quarter {'fiscal ' if 'FY' in label else ''}{y}"
    m = re.fullmatch(r"FY\s?(\d{2}|\d{4})", (label or "").strip())
    return f"fiscal {m[1] if len(m[1]) == 4 else '20' + m[1]}" if m else (label or "")


def slug_for(e_):
    t = (e_.get("ticker") or "").lower().replace(".", "-")
    return t if re.fullmatch(r"[a-z0-9-]{1,12}", t) else f"cik-{e_['cik']}"


_TILE = re.compile(r"<div class='seo-tile'><span>([^<]*)</span><b>([+−-])")


def _signs(body):
    """A tile whose figure starts with + is green, with − red (the growth and the losses stand out)."""
    return _TILE.sub(lambda m: f"<div class='seo-tile {'up' if m.group(2) == '+' else 'down'}'><span>{m.group(1)}</span><b>{m.group(2)}", body)


def page(title, desc, canonical, body, depth, image, jsonld=None):
    body = _signs(body)
    up = "../" * depth
    ld = f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(desc)}"><link rel="canonical" href="{e(canonical)}">
<meta property="og:type" content="article"><meta property="og:site_name" content="Filing Flows"><meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{e(canonical)}"><meta property="og:image" content="{e(image)}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:site" content="@FilingFlow"><meta name="twitter:title" content="{e(title)}"><meta name="twitter:description" content="{e(desc)}"><meta name="twitter:image" content="{e(image)}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<link rel="icon" href="{up}favicon.svg" type="image/svg+xml"><link rel="icon" href="{up}favicon-32.png" sizes="32x32" type="image/png"><link rel="apple-touch-icon" href="{up}apple-touch-icon.png">
<link rel="stylesheet" href="{up}styles.css"><link rel="stylesheet" href="{up}seo.css">{ld}
</head><body><header class="seo-top"><a class="seo-brand" href="{up}">Filing Flows</a><nav><a href="{up}#home">Latest</a><a href="{up}c/">Companies</a><a href="{up}gamma/">Industries</a><a href="{up}chains/">Themes</a><a href="{up}model/">Model</a><a href="{up}daily/">Today</a><a href="{up}disclosures/">Signals</a><a href="{up}events/">8-K events</a><a href="{up}#method">Method</a></nav></header>
<main class="seo">{body}</main>
<footer class="seo-foot">Figures read automatically from SEC filings (XBRL and earnings releases); errors are possible. Not investment advice. <a href="{up}">filing-flows.com</a> · <a href="https://x.com/FilingFlow" rel="me noopener">Charts posted daily on X: @FilingFlow</a></footer>
</body></html>"""


def company_page(c, ix_entry, peers, sector_name, base, depth=2, image=None, all_rows=None, chains=None, images=None):
    p, quarters = c["profile"], c.get("quarters") or []
    q = quarters[0] if quarters else {}
    h = q.get("headline") or {}
    name, t = display_name(p["name"]), (p.get("tickers") or [""])[0]
    who = f"{name} ({t})" if t else name
    form = q.get("form") or ""
    status = " (preliminary, from the earnings release)" if form == "8-K" else ""
    words = period_words(q.get("label"))
    title = f"{who} {words} results ({q.get('label', '')} earnings): revenue {h.get('rev_fmt') or money(h.get('revenue'))}" + (
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
    import seo_svg as SV                                   # charts drawn into the page (no script)
    import seo_charts as SC
    drawn = SC.static(c, ix_entry, all_rows or [], money)
    live = SC.live(p['cik'], t, ix_entry.get('sic'), ix_entry.get('sector'), chains or [], images or {}, depth)
    hq = [(x.get("label"), x.get("headline") or {}) for x in reversed(quarters[:8])]
    charts = (SV.bars([(l, hh.get("revenue")) for l, hh in hq], money, f"{name} revenue by quarter")
              + SV.bars([(l, hh.get("ni")) for l, hh in hq], money, f"{name} net earnings by quarter"))
    intro = c.get("intro") or {}
    about = (f"<h2 id='about'>About {e(name)}</h2><blockquote>{e((intro.get('text') or '')[:900])}</blockquote>"
             f"<p class='muted'>In its own words, from its {e(intro.get('source') or 'annual report')}"
             + (f", filed {e(fdate(intro.get('filed')))}" if intro.get("filed") else "") + ".</p>") if intro.get("text") else ""
    peer_links = "".join(f"<li><a href='../{slug_for(x)}/'>{e(display_name(x.get('name')))}{' (' + e(x['ticker']) + ')' if x.get('ticker') else ''}</a> "
                         f"<span class='muted'>{e(x.get('label'))} · revenue {e(x.get('rev') or '—')}{' · ' + pct(x.get('yoy')) + ' Y/Y' if x.get('yoy') is not None else ''}</span></li>"
                         for x in peers)
    rev, ni_, yoy_ = h.get("revenue"), h.get("ni"), h.get("yoy")
    bits = []
    if rev and yoy_ is not None:
        bits.append(f"Revenue {'up' if yoy_ >= 0 else 'down'} <b>{abs(yoy_):.0f}%</b> year over year to <b>{e(h.get('rev_fmt') or money(rev))}</b>")
    if rev and ni_ is not None and rev > 0:
        bits.append(f"<b>{100 * ni_ / rev:.0f}¢</b> of every $1 of revenue {'kept as net profit' if ni_ >= 0 else 'lost'}")
    if h.get("om") is not None:
        bits.append(f"operating margin <b>{h['om']:.1f}%</b>")
    highlight = (f"<p class='seo-hl {'up' if (yoy_ or 0) >= 0 else 'down'}'><span>{e(q.get('label', ''))}</span> " + " · ".join(bits) + "</p>") if bits else ""
    tiles = "".join(f"<div class='seo-tile'><span>{e(k)}</span><b>{e(v)}</b></div>" for k, v in (
        ("Revenue", h.get("rev_fmt") or money(h.get("revenue"))), ("Year over year", pct(h.get("yoy"))),
        ("Operating margin", pct(h.get("om"), False)), ("Net earnings", h.get("ni_fmt") or money(h.get("ni"))),
        ("Operating cash flow", money(h.get("ocf")))))
    body = f"""<p class="crumbs"><a href="../../">Filing Flows</a> › <a href="../../sector/{e(p.get('sector') or 'other')}/">{e(sector_name)}</a> › {e(who)}</p>
<h1>{e(who)} reports {e(words)} results</h1>
<p class="muted">{e(q.get('label', ''))} earnings · {e(form)} filed {e(fdate(q.get('filed')))}</p>
{highlight}
<p class="lead">{e(desc)}</p>
<div class="seo-tiles">{tiles}</div>
<nav class="seo-toc" aria-label="On this page"><a href="#sankey">Sankey</a>{'<a href="#changed">What changed</a>' if analysis else ''}<a href="#history">History</a>{'<a href="#charts">Charts</a>' if drawn else ''}<a href="#interactive">Interactive</a>{'<a href="#about">About</a>' if about else ''}</nav>
<figure class="seo-chart" id="sankey" data-src="../../data/c/{e(p['cik'])}.json" data-label="{e(q.get('label', ''))}" data-filed="{e(q.get('filed') or '')}" aria-label="{e(who)} {e(q.get('label', ''))} income statement and cash flow Sankey"><p class="muted">Drawing the Sankey…</p></figure>
<noscript><p class="muted">The Sankey needs JavaScript; the figures are in the table below.</p></noscript>
<p><a class="seo-cta" href="{e(app)}">Open the interactive Sankey →</a> <span class="muted">click any line for what the company wrote about it, compare Y/Y and Q/Q, export as PNG or PDF</span></p>
<script src="../../sankey.js"></script><script src="../../seo-quarter.js" defer></script>
{f'<h2 id="changed">What changed this quarter</h2><div class="seo-note">{analysis}</div>' if analysis else ''}
<h2 id="history">Quarterly history</h2>
{charts}
<div class="tbl-wrap"><table><thead><tr><th>Quarter</th><th>Form</th><th>Filed</th><th class="num">Revenue</th><th class="num">Y/Y</th><th class="num">Op. margin</th><th class="num">Net earnings</th><th class="num">Op. cash flow</th></tr></thead><tbody>{rows}</tbody></table></div>
{drawn}
{live}
{about}
{f'<h2>Other {e(p.get("industry") or sector_name)} companies</h2><ul class="seo-list">{peer_links}</ul>' if peer_links else ''}
<p class="muted">Source: <a href="{e(q.get('index_url') or q.get('doc_url') or '')}" rel="nofollow">{e(name)} {e(form)} on SEC EDGAR</a> · CIK {e(p['cik'])} · {e(p.get('industry') or '')}</p>"""
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "Corporation", "name": name, "tickerSymbol": t or None, "url": url},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Filing Flows", "item": base + "/"},
            {"@type": "ListItem", "position": 2, "name": sector_name, "item": f"{base}/sector/{p.get('sector') or 'other'}/"},
            {"@type": "ListItem", "position": 3, "name": who, "item": url}]}]}
    return url, page(title, desc, url, body, depth, image or base + "/og.png", ld)


def index_charts(latest, names):
    """The A–Z page's charts: the largest companies, and the sectors by companies and combined revenue."""
    import seo_svg as SV
    rows = sorted(latest.values(), key=lambda x: -(x.get("revenue") or 0))
    by = {}
    for x in rows:
        k = names.get(x.get("sector"), x.get("sector") or "Other")
        by[k] = by.get(k, 0) + (x.get("revenue") or 0)
    return (SV.hbars([(x.get("ticker") or display_name(x.get("name")), x.get("revenue")) for x in rows], money, "The largest companies by quarterly revenue", n=20)
            + SV.hbars(sorted(by.items(), key=lambda kv: -kv[1]), money, "Combined quarterly revenue by sector", color=SV.GREY, n=14))


def sector_charts(items, sname):
    """A sector page's charts: the largest companies, growth against margin, and the largest one's Sankey."""
    import seo_svg as SV
    from seo_history import sankey_figure
    out = SV.hbars([(x.get("ticker") or display_name(x.get("name")), x.get("revenue")) for x in items], money, f"{sname}: the largest companies by quarterly revenue", n=15)
    pts = [(x.get("ticker") or display_name(x.get("name")), max(-100, min(300, x["yoy"])), max(-100, min(100, x["om"])), x.get("revenue"))
           for x in items[:150] if x.get("yoy") is not None and x.get("om") is not None]
    out += SV.scatter(pts, "revenue growth, year over year", "operating margin", f"{sname}: growth against margin, the largest {len(pts)} companies",
                      me=pts[0][0] if pts else None, note="Dot size is quarterly revenue; dashed lines are the medians; the largest company is named.")
    if items:
        top = items[0]
        out += (f"<h2>The largest: {e(display_name(top.get('name')))}</h2>"
                + sankey_figure(top["cik"], top.get("label"), f"{display_name(top.get('name'))} {top.get('label')} Sankey", up="../../"))
    return out


def list_page(title, desc, url, intro, items, depth, extra=''):
    lis = "".join(f"<li><a href='{'../' * depth}c/{slug_for(x)}/'>{e(display_name(x.get('name')))}{' (' + e(x['ticker']) + ')' if x.get('ticker') else ''}</a> "
                  f"<span class='muted'>{e(x.get('label'))} · revenue {e(x.get('rev') or '—')}{' · ' + pct(x.get('yoy')) + ' Y/Y' if x.get('yoy') is not None else ''}</span></li>"
                  for x in items)
    body = f"<p class='crumbs'><a href='{'../' * depth}'>Filing Flows</a> › {e(title)}</p><h1>{e(title)}</h1><p class='lead'>{e(intro)}</p>{extra}<ul class='seo-list'>{lis}</ul>"
    return page(f"{title} | Filing Flows", desc, url, body, depth, url.split("/c/")[0].split("/sector/")[0] + "/og.png")


def chain_pages(data_dir, out_dir, base, images=None):
    """chains/<id>/: one page per supply chain or theme (pipeline/chains.py), with the app's chart a click away."""
    try:
        ix = json.load(open(os.path.join(data_dir, "chains", "index.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return []
    urls, cards = [], []
    for c in ix.get("chains") or []:
        try:
            d = json.load(open(os.path.join(data_dir, "chains", f"{c['id']}.json"), encoding="utf-8"))
        except (OSError, ValueError):
            continue
        url = f"{base}/chains/{c['id']}/"
        rows = sorted((r for r in d.get("companies") or [] if r.get("role") != "tier2"), key=lambda r: -(r.get("attr") or 0))
        cov = d.get("coverage") or {}
        lead = (f"{money(cov.get('spend'))} spent in the last twelve months by {', '.join(b['t'] for b in d.get('buyers') or [])}; "
                f"{money(cov.get('traced'))} traced to {cov.get('suppliers')} listed suppliers." if d.get("kind") == "spend"
                else f"{len(rows)} companies, {money(sum(r.get('attr') or 0 for r in rows))} of revenue in the last twelve months.")
        lis = "".join(f"<li><a href='../../c/{e(r['t'].lower())}/'>{e(r['t'])}</a> {e(r.get('name') or '')} "
                      f"<span class='muted'>{money(r.get('attr'))} · {e(r.get('line') or '')}</span></li>" for r in rows[:60])
        body = (f"<p class='crumbs'><a href='../../'>Filing Flows</a> › <a href='../'>Chains</a> › {e(d['name'])}</p>"
                f"<h1>{e(d['name'])}</h1><p class='lead'>{e(d.get('about') or '')}</p><p>{e(lead)} Trailing twelve months to "
                f"{fdate(d.get('asof'))}, from SEC filings.</p><p><a class='seo-cta' href='../../#chain-{e(c['id'])}'>Open the interactive money-flow chart →</a></p>"
                f"<h2>Companies</h2><ul class='seo-list'>{lis}</ul>")
        import seo_svg as SV
        img = (images or {}).get(f"chain-{c['id']}")
        pic = (f"<figure class='seo-pic'><a href='../../#chain-{e(c['id'])}'><img src='{e(img)}' alt='{e(d['name'])} money flow chart' width='1200' height='630' "
               f"loading='lazy' style='width:100%;height:auto;border-radius:8px'></a><figcaption class='muted small'>The money-flow chart (open the interactive one above).</figcaption></figure>" if img else '')
        bars = SV.hbars([(f"{r['t']} · {r.get('name') or ''}", r.get('attr')) for r in rows], money, f"{d['name']}: the largest companies by revenue in the chain", n=15)
        body = body.replace("<h2>Companies</h2>", pic + bars + "<h2>Companies</h2>", 1)
        desc = f"{d['name']}: where the money flows, from SEC filings. {lead}"[:300]
        os.makedirs(os.path.join(out_dir, "chains", c["id"]), exist_ok=True)
        open(os.path.join(out_dir, "chains", c["id"], "index.html"), "w", encoding="utf-8").write(
            page(f"{d['name']} — money flows | Filing Flows", desc, url, body, 2, (images or {}).get(f"chain-{c['id']}") or base + "/og.png"))
        urls.append((url, (d.get("generated") or "")[:10] or None))
        cards.append(f"<li><a href='{e(c['id'])}/'>{e(d['name'])}</a> <span class='muted'>{e(d.get('theme') or '')} · {e(lead)}</span></li>")
    if cards:
        body = ("<p class='crumbs'><a href='../'>Filing Flows</a> › Chains</p><h1>Supply chains and trading themes</h1>"
                "<p class='lead'>Where the money flows, industry by industry: buyers' spending traced to listed suppliers, customers and "
                "countries, and the hot themes, from SEC filings.</p><p><a class='seo-cta' href='../#chains'>Open the charts →</a></p>"
                f"<ul class='seo-list'>{''.join(cards)}</ul>")
        open(os.path.join(out_dir, "chains", "index.html"), "w", encoding="utf-8").write(
            page("Supply chains and trading themes | Filing Flows", "Industry money flows from SEC filings: AI capex, power, "
                 "semiconductors, defense, space, quantum, crypto and more.", f"{base}/chains/", body, 1, base + "/og.png"))
        urls.append((f"{base}/chains/", None))
    return urls


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def qname(q):
    """'2026Q3' -> 'Q3 2026'."""
    m = re.match(r"(\d{4})Q(\d)", str(q or ""))
    return f"Q{m.group(2)} {m.group(1)}" if m else str(q or "")


def gamma_charts(d, mdl, nm, sic):
    """An industry page's charts: its companies by revenue, how their growth spreads, the model's forecast range, and
    the interactive money flow (input-output) and money flow lab (web/seo-embed.js)."""
    import seo_svg as SV
    cos = sorted(d.get("companies") or [], key=lambda m: -(m.get("revenue_usd") or 0))
    out = SV.hbars([((m.get("ticker") or display_name(m.get("name"))), m.get("revenue_usd")) for m in cos], money, f"{nm}: the largest companies by quarterly revenue", n=12)
    ys = [100 * (m.get("current") or {}).get("yoy") for m in cos if (m.get("current") or {}).get("yoy") is not None]
    if len(ys) >= 5:
        edges = [-1e9, -25, -10, 0, 10, 25, 50, 1e9]
        names_ = ["< −25%", "−25 to −10%", "−10 to 0%", "0 to 10%", "10 to 25%", "25 to 50%", "> 50%"]
        cnt = [sum(1 for y in ys if lo <= y < hi) for lo, hi in zip(edges, edges[1:])]
        out += SV.bars(list(zip(names_, cnt)), lambda v: f"{v:.0f}", f"{nm}: how many companies grew how fast (revenue, year over year)", color=SV.GREY)
    fc = mdl.get("fc") or []
    if fc:
        out += SV.ranges([(qname(q), lo, hi, rv) for q, g, rv, lo, hi, *_ in fc], money, f"{nm}: the growth model's forecast of industry revenue",
                         legend=("80% range", "model's central forecast"))
    out += (f"<section class='seo-live' data-kind='industry' data-sic='{e(sic)}' data-sector='{e(d.get('sector') or '')}'><h2>Money flow: where the industry's revenue goes</h2>"
            f"<p class='muted'>Loading the interactive chart…</p></section><script>window.FF_BASE='../../';</script><script src='../../sankey.js' defer></script>"
            f"<script src='../../chains.js' defer></script><script src='../../flowlab.js' defer></script><script src='../../seo-embed.js' defer></script>")
    return out


def gamma_pages(data_dir, out_dir, base, slugs, images=None):
    """gamma/<sic>/: one page per SEC industry (SIC) - its growth distribution, companies, the customers and suppliers
    its companies name, and the growth model's forecast; gamma/: every industry by sector."""
    ix = _load(os.path.join(data_dir, "gamma", "index.json"))
    if not ix:
        return []
    names = ix.get("sector_names") or {}
    urls, by_sector = [], {}
    for r in ix.get("industries") or []:
        d = _load(os.path.join(data_dir, "gamma", f"{r['sic']}.json"))
        if not d or not d.get("companies"):
            continue
        sic, nm = d["sic"], d["name"]
        url = f"{base}/gamma/{sic}/"
        sm = (d.get("summary") or {}).get("yoy") or {}
        mdl = _load(os.path.join(data_dir, "model", "i", f"{sic}.json")) or {}
        fc = (mdl.get("fc") or [None])[0]
        rel = d.get("relationships") or []
        sector = names.get(d.get("sector"), d.get("sector") or "")
        n = len(d["companies"])
        period = qname(d.get("period"))
        med = f"{100 * sm['median']:+.0f}%" if sm.get("median") is not None else None
        lead = (f"{n} companies filing with the SEC under SIC {sic}." + (f" Median revenue growth {med} year on year in {period}"
                f" (middle half {100 * sm['p25']:+.0f}% to {100 * sm['p75']:+.0f}%, {sm['n']} companies)." if med and sm.get("p25") is not None else "")
                + (f" The growth model expects the industry's combined revenue to grow {100 * fc[1]:+.0f}% in {qname(fc[0])}." if fc else "")
                + (f" {len(rel)} customer or supplier links named in annual reports." if rel else ""))
        title = f"{nm} (SIC {sic}): revenue growth{', ' + med + ' Y/Y' if med else ''} — {n} companies | Filing Flows"
        tiles = "".join(f"<div class='seo-tile'><span>{e(k)}</span><b>{e(v)}</b></div>" for k, v in (
            ("Companies", str(n)), ("Median growth Y/Y", med or "—"),
            ("Middle half", f"{100 * sm['p25']:+.0f}% to {100 * sm['p75']:+.0f}%" if sm.get("p25") is not None else "—"),
            ("Industry revenue, next quarter", f"{100 * fc[1]:+.0f}% Y/Y ({qname(fc[0])}, model)" if fc else "—")))
        rows = []
        for m in sorted(d["companies"], key=lambda m: -(m.get("revenue_usd") or 0))[:60]:
            cur = m.get("current") or {}
            s = (m.get("ticker") or "").lower().replace(".", "-")
            who = (f"<a href='../../c/{e(s)}/'>{e(m.get('ticker'))}</a> " if s in slugs else (e(m.get("ticker") or "") + " ")) + e(display_name(m.get("name")))
            rows.append(f"<tr><td>{who}</td><td class='num'>{e(money(m.get('revenue_usd')))}</td><td class='num'>{e(pct(100 * cur['yoy']) if cur.get('yoy') is not None else '—')}</td>"
                        f"<td>{e(str(m.get('stage') or '').replace('unknown', '—'))}</td></tr>")
        links = "".join(f"<li>{e(x.get('supplier'))} → {e(x.get('customer'))}"
                        + (f" <span class='muted'>{100 * x['share']:.0f}% of the supplier's revenue" + (f", {money(x['value_usd'])}" if x.get("value_usd") else "") + "</span>" if x.get("share") else "")
                        + "</li>" for x in sorted(rel, key=lambda x: -(x.get("value_usd") or 0))[:25])
        fct = "".join(f"<tr><td>{e(qname(q))}</td><td class='num'>{100 * g:+.1f}%</td><td class='num'>{e(money(rv))}</td><td class='num'>{e(money(lo))} – {e(money(hi))}</td></tr>"
                      for q, g, rv, lo, hi, *_ in (mdl.get("fc") or [])) if mdl.get("fc") else ""
        body = (f"<p class='crumbs'><a href='../../'>Filing Flows</a> › <a href='../'>Industries</a> › {e(sector)} › {e(nm)}</p>"
                f"<h1>{e(nm)} <span class='muted'>SIC {e(sic)}</span></h1><p class='lead'>{e(lead)}</p><div class='seo-tiles'>{tiles}</div>"
                + gamma_charts(d, mdl, nm, sic)
                + f"<p><a class='seo-cta' href='../../#gamma-{e(sic)}'>Open the industry: growth distribution, money flow, network →</a></p>"
                + (f"<h2>Who sells to whom</h2><p class='muted'>Customers and suppliers named in the companies' annual reports; the share is of the supplier's revenue.</p><ul class='seo-list'>{links}</ul>" if links else "")
                + (f"<h2>Growth model</h2><p class='muted'>Industry revenue, the same companies year on year; 80% ranges. Fitted on SEC filings and tested out of sample (<a href='../../model/'>how</a>).</p>"
                   f"<div class='tbl-wrap'><table><thead><tr><th>Quarter</th><th class='num'>Growth Y/Y</th><th class='num'>Revenue</th><th class='num'>80% range</th></tr></thead><tbody>{fct}</tbody></table></div>" if fct else "")
                + f"<h2>Companies</h2><div class='tbl-wrap'><table><thead><tr><th>Company</th><th class='num'>Quarterly revenue</th><th class='num'>Y/Y</th><th>Stage</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
                + f"<p class='muted'>Growth from positive, comparable quarterly revenue as filed; industries are SEC Standard Industrial Classification codes. Data {e(fdate((d.get('generated') or '')[:10]))}.</p>")
        os.makedirs(os.path.join(out_dir, "gamma", sic), exist_ok=True)
        img = (images or {}).get(f"gamma-{sic}") or base + "/og.png"
        open(os.path.join(out_dir, "gamma", sic, "index.html"), "w", encoding="utf-8").write(page(title, lead[:300], url, body, 2, img))
        urls.append((url, (d.get("generated") or "")[:10] or None))
        by_sector.setdefault(sector, []).append((nm, sic, n, med))
    if by_sector:
        parts = []
        for sname in sorted(by_sector):
            lis = "".join(f"<li><a href='{e(sic)}/'>{e(nm)}</a> <span class='muted'>SIC {e(sic)} · {n} companies{' · median ' + med + ' Y/Y' if med else ''}</span></li>"
                          for nm, sic, n, med in sorted(by_sector[sname]))
            parts.append(f"<h2>{e(sname)}</h2><ul class='seo-list'>{lis}</ul>")
        body = ("<p class='crumbs'><a href='../'>Filing Flows</a> › Industries</p><h1>Every industry, by SEC SIC code</h1>"
                "<p class='lead'>Revenue growth across each industry's companies, the customers and suppliers they name, and a growth "
                "forecast, from SEC filings.</p><p><a class='seo-cta' href='../#gamma'>Open the industries →</a></p>" + "".join(parts))
        open(os.path.join(out_dir, "gamma", "index.html"), "w", encoding="utf-8").write(
            page("Industries by SEC SIC code: revenue growth and who sells to whom | Filing Flows",
                 "Every SEC industry (SIC code): median revenue growth, the companies, named customers and suppliers, and a growth forecast.",
                 f"{base}/gamma/", body, 1, base + "/og.png"))
        urls.append((f"{base}/gamma/", None))
    return urls


def model_page(data_dir, out_dir, base):
    """model/: the growth model at four levels - what it is, how it scored out of sample, and its sector and theme forecasts."""
    ix = _load(os.path.join(data_dir, "model", "index.json"))
    if not ix:
        return []
    sc = ix.get("scores") or {}
    score_rows = "".join(
        f"<tr><td>{e(lvl.capitalize())}</td><td class='num'>{s.get('entities')}</td><td class='num'>{100 * s['uncond']:.1f}%</td>"
        f"<td class='num'>{100 * s['naive']:.1f}%</td><td class='num'>{s.get('beats_naive')}</td></tr>"
        for lvl, s in sc.items() if s.get("uncond") is not None)

    def fc_rows(items, link):
        out = []
        for x in items:
            fc = (x.get("fc") or [None])[0]
            if not fc:
                continue
            out.append(f"<tr><td>{link(x)}</td><td class='num'>{100 * x['g_now']:+.1f}%</td><td class='num'>{100 * fc[1]:+.1f}% <span class='muted'>{e(qname(fc[0]))}</span></td></tr>"
                       if x.get("g_now") is not None else "")
        return "".join(out)
    sectors = fc_rows(sorted(ix.get("sectors") or [], key=lambda x: -(x.get("rev_ttm") or 0)), lambda x: e(x["name"]))
    themes = fc_rows([x for x in ix.get("concepts") or [] if x.get("kind") == "chain"],
                     lambda x: f"<a href='../chains/{e(x['id'])}/'>{e(x['name'])}</a>")
    head = "<thead><tr><th></th><th class='num'>Latest Y/Y</th><th class='num'>Next quarter</th></tr></thead>"
    body = ("<p class='crumbs'><a href='../'>Filing Flows</a> › Growth model</p><h1>One growth model, four levels</h1>"
            "<p class='lead'>Each company's revenue growth, each industry's, each sector's and each theme's is modelled the same way: this "
            "quarter's year-on-year growth = a constant + ρ × last quarter's + γ × its parent's growth, fitted on SEC filings with a prior "
            "taken from its peers, so a company with few quarters leans on its industry. Every fit is tested out of sample against "
            "“growth stays what it was”.</p><p><a class='seo-cta' href='../#model'>Open the model →</a></p>"
            f"<h2>How it scored, one quarter ahead</h2><div class='tbl-wrap'><table><thead><tr><th>Level</th><th class='num'>Fits</th><th class='num'>Model error</th>"
            f"<th class='num'>Naive error</th><th class='num'>Model better</th></tr></thead><tbody>{score_rows}</tbody></table></div>"
            f"<p class='muted'>Median error of next-quarter revenue. Data {e(fdate((ix.get('generated') or '')[:10]))}, through {e(qname(ix.get('asof')))}.</p>"
            f"<h2>Sectors</h2><div class='tbl-wrap'><table>{head}<tbody>{sectors}</tbody></table></div>"
            + (f"<h2>Themes and supply chains</h2><div class='tbl-wrap'><table>{head}<tbody>{themes}</tbody></table></div>" if themes else ""))
    os.makedirs(os.path.join(out_dir, "model"), exist_ok=True)
    open(os.path.join(out_dir, "model", "index.html"), "w", encoding="utf-8").write(page(
        "Revenue growth forecasts for every sector, industry and theme | Filing Flows",
        "A revenue growth model fitted on SEC filings for every company, SIC industry, sector and trading theme, with out-of-sample scores.",
        f"{base}/model/", body, 1, base + "/og.png"))
    return [(f"{base}/model/", (ix.get("generated") or "")[:10] or None)]


def og_images(base):
    """{page key: image URL} for pages with their own share picture (pipeline/ogimg.py writes og/index.json on the
    "media" branch; the build fetches it to OG_MANIFEST). Keys: c-<cik>, chain-<id>, gamma-<sic>."""
    path = os.environ.get("OG_MANIFEST")
    m = _load(path) if path else None
    if not m:
        return {}
    root = (m.get("base") or "").rstrip("/")
    return {k: f"{root}/{v['file']}" + (f"?v={v['v']}" if v.get("v") else "") for k, v in (m.get("images") or {}).items() if root and v.get("file")}


def write_pages(data_dir, out_dir, base):
    base = (base or "").rstrip("/")
    if not base:
        return 0
    images = og_images(base)
    ix = json.load(open(os.path.join(data_dir, "index.json"), encoding="utf-8"))
    rows = ix["companies"] if isinstance(ix, dict) else ix
    names = ix.get("sector_names") or {}
    latest = {}
    for r in rows:                                  # one page per company: its newest quarter
        if r["cik"] not in latest or (r.get("filed") or "") > (latest[r["cik"]].get("filed") or ""):
            latest[r["cik"]] = r
    chain_of = {}                                   # ticker → the supply chains and themes it is in (pipeline/chains.py)
    try:
        for ch in (json.load(open(os.path.join(data_dir, "chains", "index.json"), encoding="utf-8")).get("chains") or []):
            for tk in ch.get("buyers") or []:
                chain_of.setdefault(str(tk).upper(), []).append({"id": ch["id"], "name": ch.get("name") or ch["id"], "role": "buyer"})
            for L in ch.get("layers") or []:
                for tk in L.get("tickers") or []:
                    chain_of.setdefault(str(tk).upper(), []).append({"id": ch["id"], "name": ch.get("name") or ch["id"], "role": L.get("name") or "supplier"})
    except (OSError, ValueError, KeyError, AttributeError):
        pass
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
        url, doc = company_page(c, r, peers, names.get(r.get("sector"), r.get("sector") or "Other"), base, image=images.get(f"c-{cik}"),
                                all_rows=by_industry.get(r.get("sic") or r.get("industry"), []), chains=chain_of.get(str(r.get("ticker") or "").upper(), []), images=images)
        d = os.path.join(out_dir, "c", slug_for(r))
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(doc)
        urls.append((url, r.get("filed")))
        n += 1
    az = sorted(latest.values(), key=lambda x: display_name(x.get("name")).lower())
    os.makedirs(os.path.join(out_dir, "c"), exist_ok=True)
    open(os.path.join(out_dir, "c", "index.html"), "w", encoding="utf-8").write(list_page(
        f"Earnings results of {len(az):,} US companies, A–Z: revenue, margins and cash flow as Sankey charts",
        f"The latest quarterly results of {len(az):,} US-listed companies, read from their 10-Q, 10-K and earnings releases: revenue, growth, operating margin, net income and cash flow, each as a Sankey chart. A–Z.",
        base + "/c/", f"{len(az)} companies with an income-statement Sankey, newest quarter first in each page.", az, 1, index_charts(latest, names)))
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
            url, f"{len(items)} {sname} companies by revenue, each with its latest quarter drawn from the SEC filing.", items, 2, sector_charts(items, sname)))
        urls.append((url, None))
    urls += chain_pages(data_dir, out_dir, base, images)
    urls += gamma_pages(data_dir, out_dir, base, {slug_for(r) for r in latest.values()}, images)
    urls += model_page(data_dir, out_dir, base)
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
