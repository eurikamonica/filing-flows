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
import sys
from urllib.parse import quote
from xml.sax.saxutils import escape as xesc

e = lambda s: html.escape(str(s if s is not None else ""), quote=True)

# The site's own X account: the footer link, the twitter:site tag and the Organization's sameAs on every page.
# Change it here (and in web/index.html) if the account is renamed again.
SITE_NAME = "Filing Flows"
X_HANDLE = "FilingFlows"
X_URL = f"https://x.com/{X_HANDLE}"
_PAGE_TYPES = {"WebPage", "AboutPage", "CollectionPage", "FAQPage", "ItemPage", "NewsArticle", "Article", "Dataset"}


def _origin(url):
    m = re.match(r"https?://[^/]+", url or "")
    return m.group(0) if m else ""


def organization(base):
    """Filing Flows itself: one node with a fixed @id, so every page's publisher points at the same site and X account
    (search engines and AI answers tie filing-flows.com and @FilingFlows together from it)."""
    return {"@type": "Organization", "@id": f"{base}/#org", "name": SITE_NAME, "alternateName": [X_HANDLE, "filing-flows.com"],
            "url": f"{base}/", "logo": f"{base}/apple-touch-icon.png", "sameAs": [X_URL]}


def with_publisher(jsonld, canonical, title):
    """The page's structured data plus the Filing Flows Organization, named as publisher of the page. A
    {"@type": "Organization", "name": "Filing Flows"} written anywhere inside becomes a reference to that one node; a page
    with no page-type node gets a plain WebPage. Pages without an absolute canonical URL are left as they were."""
    base = _origin(canonical)
    if not base:
        return jsonld
    ref = {"@id": f"{base}/#org"}
    is_us = lambda x: isinstance(x, dict) and x.get("@type") == "Organization" and x.get("name") == SITE_NAME

    def walk(x):
        if is_us(x):
            return dict(ref)
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return x
    nodes = (jsonld or {}).get("@graph") if isinstance(jsonld, dict) and "@graph" in jsonld else \
        ([{k: v for k, v in jsonld.items() if k != "@context"}] if jsonld else [])
    graph = [walk(n) for n in nodes if not is_us(n)]
    pages = [n for n in graph if isinstance(n, dict) and n.get("@type") in _PAGE_TYPES]
    if not pages:
        graph.append({"@type": "WebPage", "name": title, "url": canonical})
        pages = graph[-1:]
    for n in pages:
        n.setdefault("publisher", dict(ref))
    graph.append(organization(base))
    return {"@context": "https://schema.org", "@graph": graph}


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))    # the repository: pipeline/names.py
from pipeline import names as _names  # noqa: E402
from pipeline import dims as _dims  # noqa: E402

KEEP_UPPER = _names.KEEP_UPPER


def display_name(name):
    """A filing's name as a page shows it (pipeline/names.py): 'W&T OFFSHORE INC' → W&T Offshore, 'AMPHENOL CORP /DE/' → Amphenol."""
    return _names.display(name)


def person(name):
    """A Form 4 or 13D person's name in capitals, cased: 'O'BRIEN MICHAEL J' → O'Brien Michael J (pipeline/names.py)."""
    return _names.person(name)


ENTITY = re.compile(r"\b(?:INC|LLC|L\.L\.C|LP|L\.P|LLP|LTD|LIMITED|CORP|CORPORATION|CO|COMPANY|FUNDS?|CAPITAL|PARTNERS(?:HIP)?|MANAGEMENT|TRUSTS?|TRUSTEES?"
                    r"|ADVISORS|ADVISERS|ADVISORY|HOLDINGS?|GROUP|GMBH|SA|S\.A|NV|N\.V|BV|B\.V|PLC|AG|SE|SARL|PTE|SPA|S\.P\.A|SICAV|SICAF|VENTURES"
                    r"|INVESTMENTS?|INVESTORS|ASSOCIATES|ASSETS?|EQUITY|EQUITIES|FOUNDATION|BANK|BANCORP|ENTERPRISES|INDUSTRIES|TECHNOLOGIES|SYSTEMS"
                    r"|INTERNATIONAL|GLOBAL|ACQUISITION|SPONSOR|ESTATE|UNIVERSITY|COLLEGE|PENSION|RETIREMENT|INSURANCE|SECURITIES|FINANCIAL|FINANCE"
                    r"|RESEARCH|MASTER|OFFSHORE|STRATEGIES|STRATEGIC|OPPORTUNIT(?:Y|IES)|SUB|MERGER|FAMILY|OFFICE|KG|OY|AB|ASA|AS|SPV)\b", re.I)


def filer(name):
    """a Form 4 or 13D filer's name as the filing writes it, in capitals, cased: a person's word by word ('KIRK RONALD' →
    Kirk Ronald, the filing's word order kept), an entity's as a company's ('KKR GROUP LP' → KKR Group LP)"""
    if not name:
        return name
    return _names.cased(name) if ENTITY.search(name) else _names.person(name)


def label(text):
    """A chart line's label as the pages print it: the XBRL member leftovers gone ('Retail Revenue Member' → Retail Revenue)."""
    return _dims.clean_label(html.unescape(str(text or "")))


MEANINGFUL = 1000     # a margin or share of revenue beyond ±1000% says the revenue is a sliver, not how profitable the company is


def ratio(x, rev):
    """x as a percentage of revenue, None when there is no revenue to speak of (|ratio| ≥ 1000%: a biotech's $40K of
    collaboration revenue against a $50M loss is not a −125,000% margin)."""
    if x is None or not rev or rev <= 0:
        return None
    v = 100 * x / rev
    return v if abs(v) < MEANINGFUL else None


def vs(v, what):
    """a change in a sentence: '+12% from a year earlier', '−0.4% from Q1 2026', 'up 15-fold from Q2 2026' (a sliver's base)"""
    if v is None:
        return f"— from {what}"
    if v >= MEANINGFUL:
        return f"up {1 + v / 100:,.0f}-fold from {what}"
    return f"{pct(v)} from {what}"


def times(n):
    """'once', 'twice', '3 times'."""
    try:
        k = int(round(float(n)))
    except (TypeError, ValueError):
        return f"{n} times"
    return "once" if k == 1 else "twice" if k == 2 else f"{k:,} times"


def money(v):
    if v is None:
        return "—"
    a, s = abs(v), "−" if v < 0 else ""
    if a < 500:
        return "$0" if a < 0.5 else f"{s}${a:,.0f}"                # "$0 in penalties", not "$0K"
    if a >= 999.95e9:
        return f"{s}${a / 1e12:.2f}T"                              # $6.90T (a 13F filer's assets), not $6897.7B
    if a >= 999.5e6:
        return f"{s}${a / 1e9:.1f}B"                               # $1.0B, $113.2B
    if a >= 99.95e6:
        return f"{s}${a / 1e6:.0f}M"                               # $978M (not "$1.0B" for $977.7M)
    if a >= 0.9995e6:
        return f"{s}${a / 1e6:.1f}M"                               # $13.3M, as the Sankey prints it
    return f"{s}${a / 1e3:.0f}K"


def n_of(n, word, plural=None):
    """A count with its noun: '1 company', '12 companies', '1,741 companies' (plural: when it is not word + s)."""
    try:
        k = int(round(float(n)))
    except (TypeError, ValueError):
        return f"{n} {plural or word + 's'}"
    w = word if k == 1 else (plural or (word[:-1] + "ies" if word.endswith("y") and word[-2:-1] not in "aeiou" else word + "s"))
    return f"{k:,} {w}"


def poss(name):
    """The possessive of a name: Illinois Tool Works' latest quarter, Macy's stores, Apple's revenue."""
    name = str(name or "")
    if name.endswith(("'s", "’s")):
        return name
    return name + ("'" if name.endswith(("s", "S")) else "'s")


def usd2(v):
    """a per-share dollar figure with its sign in front: −$0.24, not $-0.24"""
    return "—" if v is None else f"{'−' if v < 0 else ''}${abs(v):,.2f}"


def pct(v, signed=True):
    """a growth rate (signed, whole percent) or a margin (one decimal); a margin beyond ±1000% is 'n/m' (see ratio)"""
    if v is None:
        return "—"
    if signed:
        if v >= MEANINGFUL:                                     # +2627% from a sliver: 27× reads
            return f"{1 + v / 100:,.0f}×"
        return "0%" if abs(v) < 0.05 else f"{v:+.1f}%" if abs(v) < 0.95 else f"{v:+.0f}%"    # never "-0%": −0.4%, or 0%
    return f"{v:.1f}%" if abs(v) < MEANINGFUL else "n/m"


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
    if len(title) > 70 and title.endswith(" | Filing Flows"):      # a long title keeps its own words; search shows the site's name anyway
        title = title[:-len(" | Filing Flows")]
    body = _signs(body)
    up = "../" * depth
    jsonld = with_publisher(jsonld, canonical, title)
    ld = f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(desc)}"><meta name="robots" content="max-image-preview:large, max-snippet:-1, max-video-preview:-1"><link rel="canonical" href="{e(canonical)}">
<meta property="og:type" content="article"><meta property="og:site_name" content="Filing Flows"><meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{e(canonical)}"><meta property="og:image" content="{e(image)}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:site" content="@{X_HANDLE}"><meta name="twitter:title" content="{e(title)}"><meta name="twitter:description" content="{e(desc)}"><meta name="twitter:image" content="{e(image)}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<link rel="icon" href="{up}favicon.svg" type="image/svg+xml"><link rel="icon" href="{up}favicon-32.png" sizes="32x32" type="image/png"><link rel="apple-touch-icon" href="{up}apple-touch-icon.png">
<link rel="stylesheet" href="{up}styles.css"><link rel="stylesheet" href="{up}seo.css">{ld}
</head><body><header class="seo-top"><a class="seo-brand" href="{up}">Filing Flows</a><nav><a href="{up}#home">Latest</a><a href="{up}c/">Companies</a><a href="{up}gamma/">Industries</a><a href="{up}chains/">Themes</a><a href="{up}model/">Model</a><a href="{up}daily/">Today</a><a href="{up}disclosures/">Signals</a><a href="{up}events/">8-K events</a><a href="{up}#method">Method</a></nav></header>
<main class="seo">{body}</main>
<footer class="seo-foot">Figures read automatically from SEC filings (XBRL and earnings releases); errors are possible. Not investment advice. <a href="{up}">filing-flows.com</a> · <a href="{up}about/">About</a> · <a href="{X_URL}" rel="me noopener">Charts posted daily on X: @{X_HANDLE}</a></footer>
</body></html>"""


def fit(title, site=" | Filing Flows", width=62):
    """the site name only when the title still fits in a search result (about 60 characters); Google shows the
    site's name beside the result anyway"""
    return title + site if len(title) + len(site) <= width else title


def segments(q):
    """[(segment, revenue)] the lines that flow straight into revenue (or into a group that does), largest first"""
    nodes = {n.get("id"): n for n in q.get("nodes") or []}
    into = {l.get("t") for l in q.get("links") or []}
    out = []
    for l in q.get("links") or []:
        s = nodes.get(l.get("s")) or {}
        if l.get("t") == "revenue" and l.get("v") and s.get("name"):
            out.append((label(s["name"]), l["v"]))
    return sorted(out, key=lambda x: -x[1])


LICENSE = "/license/"


def image_ld(base, image, alt, caption=None):
    """ImageObject for Google Images: the credit, the creator and the terms (a licence page and where to get it), so
    the picture can carry the "Licensable" badge and the credit line in image results"""
    return {"@type": "ImageObject", "contentUrl": image, "url": image, "name": alt, **({"caption": caption} if caption else {}), "width": 1200, "height": 630,
            "creditText": "Filing Flows (filing-flows.com)", "creator": {"@type": "Organization", "name": "Filing Flows", "url": base + "/"},
            "copyrightNotice": "© Filing Flows — free to use with credit and a link", "license": base + LICENSE, "acquireLicensePage": base + LICENSE}


def share_figure(image, alt, caption, url, depth=2, embed=True, tweet=None):
    """the company's Sankey as a picture with its caption: what image search reads (alt, caption, the text around it)"""
    if not image:
        return ""
    up = "../" * depth
    return (f"<figure class='seo-share'><a href='{e(image)}'><img src='{e(image)}' alt='{e(alt)}' width='1200' height='630' loading='lazy'></a>"
            f"<figcaption>{e(caption)} — free to use with credit and a link (<a href='{up}license/'>terms</a>)."
            + (f" <a href='https://x.com/intent/tweet?text={quote(tweet)}&amp;url={quote(url)}' rel='noopener'>Share on X</a>" if tweet else "") + "</figcaption>"
            + (embed_box(url, image, alt, caption) if embed else "") + "</figure>")


def license_page(out_dir, base):
    body = ("<p class='crumbs'><a href='../'>Filing Flows</a> › Using the charts</p><h1>Using Filing Flows charts</h1>"
            "<p class='lead'>Every chart on Filing Flows — the earnings Sankeys, the cash-flow and 13F charts — is free to use in articles, posts, newsletters, "
            "videos, classes and research, with two conditions.</p><div class='seo-note'>"
            "<p><b>1. Credit:</b> “Source: Filing Flows (filing-flows.com)”, and online a link to the chart's page (the embed code under each chart does both).</p>"
            "<p><b>2. As drawn:</b> keep the figures and the Filing Flows mark; do not sell the pictures themselves or present them as your own.</p>"
            "<p>The figures are read automatically from companies' SEC filings (XBRL and earnings releases) and can contain errors; check the filing before relying "
            "on a number. Nothing here is investment advice.</p>"
            f"<p>For other uses — print, a larger size, or many charts at once — write to <a href='{X_URL}' rel='me noopener'>@{X_HANDLE} on X</a>.</p></div>")
    os.makedirs(os.path.join(out_dir, "license"), exist_ok=True)
    open(os.path.join(out_dir, "license", "index.html"), "w", encoding="utf-8").write(page(
        "Using Filing Flows charts: free with credit and a link | Filing Flows",
        "The earnings Sankeys and other Filing Flows charts are free to use in articles, posts and research with credit and a link to filing-flows.com.",
        base + LICENSE, body, 1, base + "/og.png"))
    return [(base + LICENSE, None)]


def embed_box(url, image, alt, caption):
    """'Embed this chart': the picture linked to its page (a link back to the site wherever it is posted), or the
    interactive chart in a frame with the same credit line under it"""
    img = (f'<a href="{url}"><img src="{image}" alt="{alt}" width="600" style="max-width:100%;height:auto"></a>'
           f'<br><small>{caption} — <a href="{url}">Filing Flows</a></small>')
    frame = (f'<iframe src="{url}embed/" width="100%" height="460" style="border:0;max-width:900px" loading="lazy" title="{alt}"></iframe>'
             f'<br><small>{caption} — <a href="{url}">Filing Flows</a></small>')
    box = lambda i, lab, code: (f"<label for='emb-{i}'>{e(lab)}</label><textarea id='emb-{i}' readonly rows='3' onclick='this.select()'>{e(code)}</textarea>")
    return (f"<details class='seo-embed'><summary>Embed this chart on your site</summary>{box('img', 'Picture with a link (blogs, newsletters, forums)', img)}"
            f"{box('frame', 'Interactive chart', frame)}<p class='muted'>Free to use with the credit line. Click a box to select the code.</p></details>")


def embed_page(c, r, url):
    name = display_name((c.get("profile") or {}).get("name") or r.get("name"))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(name)} Sankey | Filing Flows</title><meta name="robots" content="noindex, follow"><link rel="canonical" href="{e(url)}">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>body{{margin:0;background:#fbfaf7;font:13px/1.4 'IBM Plex Sans',system-ui,sans-serif;color:#2b2b2b}}.seo-chart{{margin:0}}.seo-chart svg{{width:100%;height:auto;display:block}}
.seo-sk-modes{{display:flex;gap:6px;padding:6px}}.seo-sk-modes button{{font:inherit;border:1px solid #d8d4cc;background:#fff;border-radius:99px;padding:3px 10px;cursor:pointer}}
.seo-sk-modes button[aria-pressed=true]{{background:#17734a;color:#fff;border-color:#17734a}}.seo-sk-notes{{display:none}}.cr{{padding:4px 8px;color:#6b6b6b}}.cr a{{color:#17734a}}</style></head>
<body><figure class="seo-chart" data-src="../../../data/c/{e(r['cik'])}.json" aria-label="{e(name)} income statement and cash flow Sankey"><p>Drawing…</p></figure>
<p class="cr">{e(name)} earnings Sankey · <a href="{e(url)}" target="_blank" rel="noopener">Filing Flows — every quarter, from the SEC filing</a></p>
<script src="../../../sankey.js"></script><script src="../../../seo-quarter.js" defer></script></body></html>"""


def peer_table(me, peers, industry):
    """the company against its largest industry peers on one table: revenue, growth, margin, the quarter"""
    rows = [me] + list(peers)
    def td(x, k, f):
        v = x.get(k)
        return f"<td class='num'>{e(f(v)) if v is not None else '—'}</td>"
    om = lambda v: pct(v, False)
    cls_me = " class='me'"
    body = "".join(f"<tr{cls_me if x is me else ''}><td>{('<b>' + e(x.get('ticker') or '') + '</b> ' if x is me else f'<a href=' + chr(39) + '../' + slug_for(x) + '/' + chr(39) + '><b>' + e(x.get('ticker') or '') + '</b></a> ') if x.get('ticker') else ''}{e(display_name(x.get('name')))}</td>"
                   f"<td>{e(x.get('label'))}</td>{td(x, 'revenue', money)}{td(x, 'yoy', pct)}{td(x, 'om', om)}</tr>" for x in rows)
    med = lambda k: sorted(v for v in (x.get(k) for x in rows) if v is not None)
    note = ''
    for k, lab, f in (('yoy', 'revenue growth', pct), ('om', 'operating margin', om)):
        m = med(k)
        if len(m) >= 3 and me.get(k) is not None and (k != 'om' or abs(me[k]) < MEANINGFUL):
            mid = m[len(m) // 2]
            note += f" {lab.capitalize()}: {f(me[k])} against the peers' median {f(mid)}."
    return (f"<h2 id='peers'>{e(display_name(me.get('name')))} against its {e(industry)} peers</h2><p class='muted'>The largest companies of the same SEC industry, each at its latest quarter.{e(note)}</p>"
            "<div class='tbl-wrap'><table><thead><tr><th>Company</th><th>Quarter</th><th class='num'>Revenue</th><th class='num'>Y/Y</th><th class='num'>Op. margin</th></tr></thead><tbody>" + body + "</tbody></table></div>")


def ties_section(ties, cik, pages):
    """customers and suppliers named in annual reports (data/gamma/<sic>.json relationships), linked to their pages"""
    sells, buys = [], []
    for x in ties:
        if str(x.get("supplier_cik")) == str(cik):
            sells.append((x.get("customer"), x.get("customer_cik"), x))
        elif str(x.get("customer_cik")) == str(cik):
            buys.append((x.get("supplier"), x.get("supplier_cik"), x))
    if not sells and not buys:
        return ""
    def li(n, k, x, side):
        pg = pages.get(int(k)) if str(k or "").isdigit() else None
        who = f"<a href='../{pg}/'>{e(n)}</a>" if pg else e(n)
        share = f" — {100 * x['share']:.0f}% of {'its' if side == 'sells' else 'the supplier’s'} revenue" if x.get("share") else ""
        return (f"<li>{who}<span class='muted'>{e(share)} · {e(x.get('evidence_level') or 'named in a filing')}"
                + (f" · <a href='{e(x['source_url'])}' rel='nofollow'>source</a>" if x.get("source_url") else "") + "</span></li>")
    seen = lambda xs: list({(n, str(k)): (n, k, x) for n, k, x in xs}.values())
    out = "<h2 id='ties'>Customers and suppliers named in filings</h2>"
    if sells:
        out += "<h3>Sells to</h3><ul class='seo-list'>" + "".join(li(n, k, x, 'sells') for n, k, x in sorted(seen(sells), key=lambda s: -(s[2].get('share') or 0))[:12]) + "</ul>"
    if buys:
        out += "<h3>Buys from</h3><ul class='seo-list'>" + "".join(li(n, k, x, 'buys') for n, k, x in sorted(seen(buys), key=lambda s: -(s[2].get('share') or 0))[:12]) + "</ul>"
    return out


def company_page(c, ix_entry, peers, sector_name, base, depth=2, image=None, all_rows=None, chains=None, images=None, ties=None, pages=None):
    p, quarters = c["profile"], c.get("quarters") or []
    q = quarters[0] if quarters else {}
    h = q.get("headline") or {}
    name, t = display_name(p["name"]), (p.get("tickers") or [""])[0]
    who = f"{name} ({t})" if t else name
    form = q.get("form") or ""
    status = " (preliminary, from the earnings release)" if form == "8-K" else ""
    words = period_words(q.get("label"))
    revs = money(h.get('revenue'))
    # the company page is the evergreen one ("amazon earnings", "amazon revenue breakdown"); the quarter's own page
    # (c/<slug>/q3-2026/) answers "amazon q3 2026 earnings": two pages aimed at one query split its ranking
    title = fit(f"{who} Earnings & Revenue Breakdown: {revs}" + (f" ({pct(h.get('yoy'))})" if h.get("yoy") is not None else ""))
    segs = segments(q)
    desc = (f"{name} made {revs} in {q.get('label', '')}" + (f" ({pct(h.get('yoy'))} Y/Y)" if h.get("yoy") is not None else "")
            + (": " + ", ".join(f"{n} {money(v)}" for n, v in segs[:3]) if len(segs) >= 2 else "")
            + (f". Operating margin {pct(h.get('om'), False)}" if h.get("om") is not None else "")
            + (f", net {'earnings' if h['ni'] >= 0 else 'loss'} {money(abs(h['ni']))}" if h.get("ni") is not None else "")
            + f". See where every dollar goes — costs, profit and cash — as a Sankey from the {form} filed {fdate(q.get('filed'))}{status}.")
    url = f"{base}/c/{slug_for(ix_entry)}/"
    app = "../" * depth + f"#c-{p['cik']}"
    rows = "".join(
        f"<tr><td>{e(x.get('label'))}</td><td>{e(x.get('form'))}</td><td>{e(fdate(x.get('filed')))}</td>"
        f"<td class='num'>{e(money((x.get('headline') or {}).get('revenue')))}</td>"
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
    r_me = ix_entry
    peer_links = "".join(f"<li><a href='../{slug_for(x)}/'>{e(display_name(x.get('name')))}{' (' + e(x['ticker']) + ')' if x.get('ticker') else ''}</a> "
                         f"<span class='muted'>{e(x.get('label'))} · revenue {e(x.get('rev') or '—')}{' · ' + pct(x.get('yoy')) + ' Y/Y' if x.get('yoy') is not None else ''}</span></li>"
                         for x in peers)
    rev, ni_, yoy_ = h.get("revenue"), h.get("ni"), h.get("yoy")
    bits = []
    if rev and yoy_ is not None:
        bits.append(f"Revenue {'up' if yoy_ >= 0 else 'down'} <b>{abs(yoy_):.0f}%</b> year over year to <b>{e(money(rev))}</b>")
    if ratio(ni_, rev) is not None:
        bits.append(f"<b>{abs(ratio(ni_, rev)):.0f}¢</b> of every $1 of revenue {'kept as net profit' if ni_ >= 0 else 'lost'}")
    if h.get("om") is not None and abs(h["om"]) < MEANINGFUL:
        bits.append(f"operating margin <b>{h['om']:.1f}%</b>")
    highlight = (f"<p class='seo-hl {'up' if (yoy_ or 0) >= 0 else 'down'}'><span>{e(q.get('label', ''))}</span> " + " · ".join(bits) + "</p>") if bits else ""
    tiles = "".join(f"<div class='seo-tile'><span>{e(k)}</span><b>{e(v)}</b></div>" for k, v in (
        ("Revenue", money(h.get("revenue"))), ("Year over year", pct(h.get("yoy"))),
        ("Operating margin", pct(h.get("om"), False)), ("Net earnings", money(h.get("ni"))),
        ("Operating cash flow", money(h.get("ocf")))))
    tweet = f"{who} {q.get('label', '')} revenue breakdown"
    import seo_history as SH
    qs_ = SH.qslug(q.get('label') or '')
    qlink = f" · <a href='{qs_}/'>{e(who)} {e(q.get('label', ''))} earnings results →</a>" if qs_ and form != '8-K' else ''
    alt = f"{name} {q.get('label', '')} revenue breakdown: Sankey diagram of revenue" + (f" ({', '.join(n for n, _ in segs[:4])})" if segs else "") + ", costs, profit and cash flow"
    share = share_figure(image, alt, f"{name} {q.get('label', '')} revenue breakdown", url, depth, True, tweet)
    ties_html = ties_section(ties or [], p['cik'], pages or {})
    body = f"""<p class="crumbs"><a href="../../">Filing Flows</a> › <a href="../../sector/{e(p.get('sector') or 'other')}/">{e(sector_name)}</a> › {e(who)}</p>
<h1>{e(who)} earnings and revenue breakdown</h1>
<p class="muted">Latest: {e(q.get('label', ''))} · {e(form)} filed {e(fdate(q.get('filed')))}{qlink}</p>
{highlight}
<p class="lead">{e(desc)}</p>
<div class="seo-tiles">{tiles}</div>
<nav class="seo-toc" aria-label="On this page"><a href="#sankey">Sankey</a>{'<a href="#changed">What changed</a>' if analysis else ''}<a href="#history">History</a>{'<a href="#charts">Charts</a>' if drawn else ''}<a href="#interactive">Interactive</a>{'<a href="#about">About</a>' if about else ''}</nav>
<figure class="seo-chart" id="sankey" data-src="../../data/c/{e(p['cik'])}.json" data-label="{e(q.get('label', ''))}" data-filed="{e(q.get('filed') or '')}" aria-label="{e(who)} {e(q.get('label', ''))} income statement and cash flow Sankey"><p class="muted">Drawing the Sankey…</p></figure>
<noscript><p class="muted">The Sankey needs JavaScript; the figures are in the table below.</p></noscript>
<p><a class="seo-cta" href="{e(app)}">Open the interactive Sankey →</a> <span class="muted">click any line for what the company wrote about it, compare Y/Y and Q/Q, export as PNG or PDF</span></p>
<script src="../../sankey.js"></script><script src="../../seo-quarter.js" defer></script>
{share}
{f'<h2 id="changed">What changed this quarter</h2><div class="seo-note">{analysis}</div>' if analysis else ''}
<h2 id="history">Quarterly history</h2>
{charts}
<div class="tbl-wrap"><table><thead><tr><th>Quarter</th><th>Form</th><th>Filed</th><th class="num">Revenue</th><th class="num">Y/Y</th><th class="num">Op. margin</th><th class="num">Net earnings</th><th class="num">Op. cash flow</th></tr></thead><tbody>{rows}</tbody></table></div>
{drawn}
{live}
{ties_html}
{about}
{peer_table(r_me, peers, p.get("industry") or sector_name) if peers else ''}
<p class="muted">Source: <a href="{e(q.get('index_url') or q.get('doc_url') or '')}" rel="nofollow">{e(name)} {e(form)} on SEC EDGAR</a> · CIK {e(p['cik'])} · {e(p.get('industry') or '')}</p>"""
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "Corporation", "name": name, "tickerSymbol": t or None, "url": url},
        {"@type": "WebPage", "name": title, "url": url, "datePublished": q.get("filed"), "dateModified": q.get("filed"),
         **({"primaryImageOfPage": {"@type": "ImageObject", "contentUrl": image}} if image else {})},
        *([image_ld(base, image, alt, f"{name} {q.get('label', '')} revenue breakdown")] if image else []),
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


def _cal(end):
    """the calendar quarter holding a period end: '2026-07-26' → ('CY2026Q3', 'Q3 2026')"""
    y, m = int(end[:4]), int(end[5:7])
    q = (m - 1) // 3 + 1
    return f"CY{y}Q{q}", f"Q{q} {y}"


def chain_index(data_dir, d, n=12):
    """The theme's own quarterly series from its members' filings: the suppliers' revenue attributed to the chain (each
    company's quarterly revenue scaled by the share the chain takes of its trailing twelve months) and, for a spend chain,
    the buyers' capital spending — by calendar quarter, over the quarters where at least 70% of the members report.
    Returns {'revenue': [(label, value, members)], 'capex': [...], 'yoy': …} or None."""
    sup = [r for r in d.get('companies') or [] if r.get('role') != 'tier2' and r.get('cik') and (r.get('attr') or 0) > 0 and (r.get('rev') or 0) > 0]
    buy = [b for b in d.get('buyers') or [] if isinstance(b, dict) and b.get('cik')]
    rev, cap = {}, {}
    for r in sup:
        c = _load(os.path.join(data_dir, 'c', f"{r['cik']}.json"))
        h = ((c or {}).get('quality') or {}).get('hist') or {}
        if not h.get('periods'):
            continue
        vs = (h.get('v') or {}).get('revenue') if isinstance(h.get('v'), dict) else None     # [[period index, [[value, evidence] …]] …]
        if not vs:
            continue
        scale = min(1.0, (r.get('attr') or 0) / r['rev'])
        qs, fys = {}, []
        for pi, evs in vs:
            per = h['periods'][pi] if 0 <= pi < len(h['periods']) else None
            val = evs[0][0] if evs and evs[0] else None
            if not per or not isinstance(val, (int, float)):
                continue
            if per[2] == 'q':
                qs[(per[0], per[1])] = val
            elif per[2] == 'fy':
                fys.append((per[0], per[1], val))
        for (a, b), val in qs.items():
            rev.setdefault(_cal(b), {})[r['cik']] = val * scale
        for a, b, val in fys:                                   # the fourth quarter: the year less its three reported quarters
            inside = [v for (qa, qb), v in qs.items() if qa >= a and qb < b]
            if len(inside) == 3 and r['cik'] not in rev.get(_cal(b), {}):
                rev.setdefault(_cal(b), {})[r['cik']] = (val - sum(inside)) * scale
    for b in buy:
        c = _load(os.path.join(data_dir, 'c', f"{b['cik']}.json"))
        hq = (((c or {}).get('quality') or {}).get('cap') or {}).get('hq') or {}
        ks = hq.get('keys') or []
        if 'capex' not in ks:
            continue
        ci = ks.index('capex')
        for row in hq.get('rows') or []:
            if row[0] and row[1 + ci] is not None:
                cap.setdefault(_cal(row[0]), {})[b['cik']] = -row[1 + ci]
    def series(m, members):
        need = max(1, int(0.7 * len(members)))
        ks = sorted(k for k, v in m.items() if len(v) >= need)[-n:]
        return [(k[1], sum(m[k].values()), len(m[k])) for k in ks]
    out = {'revenue': series(rev, sup) if sup else [], 'capex': series(cap, buy) if buy else []}
    if not out['revenue'] and not out['capex']:
        return None
    for key in ('revenue', 'capex'):
        xs = out[key]
        out[key + '_yoy'] = xs[-1][1] / xs[-5][1] - 1 if len(xs) >= 5 and xs[-5][1] else None
    return out


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
                else f"{n_of(len(rows), 'company', 'companies')}, {money(sum(r.get('attr') or 0 for r in rows))} of revenue in the last twelve months.")
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
        idx = ''
        try:
            ci = chain_index(data_dir, d)
        except Exception:  # noqa: BLE001
            ci = None
        if ci:
            idx = "<h2 id='index'>The theme quarter by quarter</h2>"
            if ci['revenue']:
                idx += SV.bars([(l, v) for l, v, _ in ci['revenue']], money, f"{d['name']}: the chain's revenue by calendar quarter",
                               note=f"Each supplier's quarterly revenue scaled by the share of it this chain takes (its attributed share of the trailing twelve months), summed; "
                                    f"{n_of(ci['revenue'][-1][2], 'company', 'companies')} in the latest quarter" + (f", {pct(100 * ci['revenue_yoy'])} against a year earlier" if ci.get('revenue_yoy') is not None else '') + '.')
                lead += f" The chain's attributed revenue was {money(ci['revenue'][-1][1])} in {ci['revenue'][-1][0]}" + (f", {pct(100 * ci['revenue_yoy'])} year over year" if ci.get('revenue_yoy') is not None else '') + '.'
            if ci['capex']:
                idx += SV.bars([(l, v) for l, v, _ in ci['capex']], money, f"{d['name']}: the buyers' capital spending by calendar quarter",
                               note=f"Capital expenditures of the chain's buyers from their cash-flow statements, by calendar quarter; {ci['capex'][-1][2]} companies in the latest quarter"
                                    + (f", {pct(100 * ci['capex_yoy'])} against a year earlier" if ci.get('capex_yoy') is not None else '') + '.', color=SV.BLUE)
        body = body.replace("<h2>Companies</h2>", pic + bars + idx + "<h2>Companies</h2>", 1)
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
        spread = sm.get("p25") is not None and (sm.get("n") or 0) >= 3           # a middle half of one company is no spread
        lead = (f"{n_of(n, 'company')} filing with the SEC under SIC {sic}." + (f" Median revenue growth {med} year on year in {period}"
                + (f" (middle half {100 * sm['p25']:+.0f}% to {100 * sm['p75']:+.0f}%, {n_of(sm['n'], 'company')})" if spread else f" ({n_of(sm.get('n') or n, 'company')})") + "." if med else "")
                + (f" The growth model expects the industry's combined revenue to grow {100 * fc[1]:+.0f}% in {qname(fc[0])}." if fc else "")
                + (f" {len(rel)} customer or supplier links named in annual reports." if rel else ""))
        title = f"{nm} (SIC {sic}): revenue growth{', ' + med + ' Y/Y' if med else ''} — {n_of(n, 'company')} | Filing Flows"
        tiles = "".join(f"<div class='seo-tile'><span>{e(k)}</span><b>{e(v)}</b></div>" for k, v in (
            ("Companies", str(n)), ("Median growth Y/Y", med or "—"),
            ("Middle half", f"{100 * sm['p25']:+.0f}% to {100 * sm['p75']:+.0f}%" if spread else "—"),
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
        fct = "".join(f"<tr><td>{e(qname(q))}</td><td class='num'>{100 * g:+.1f}%</td><td class='num'>{e(money(rv))}</td>"
                      f"<td class='num'>{e(money(lo)) + ' – ' + e(money(hi)) if lo is not None and hi is not None else '—'}</td></tr>"
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
            lis = "".join(f"<li><a href='{e(sic)}/'>{e(nm)}</a> <span class='muted'>SIC {e(sic)} · {n_of(n, 'company')}{' · median ' + med + ' Y/Y' if med else ''}</span></li>"
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


def about_page(out_dir, base, n_companies):
    """about/index.html: what the site is, where the numbers come from, how the charts and text are made, the X account
    and how to reach the owner — the page search engines and AI answers read to describe the site."""
    url = f"{base}/about/"
    mail = os.environ.get("CONTACT_EMAIL", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if re.fullmatch(r"[^@\s<>\"']+@[^@\s<>\"']+\.[A-Za-z]{2,}", mail):
        contact = f"e-mail <a href='mailto:{e(mail)}'>{e(mail)}</a>"
    elif re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        contact = f"open an issue at <a href='https://github.com/{e(repo)}/issues'>github.com/{e(repo)}</a>"
    else:
        contact = f"send a message to <a href='{X_URL}' rel='me noopener'>@{X_HANDLE}</a> on X"
    count = f"{n_companies:,} US-listed companies" if n_companies else "thousands of US-listed companies"
    title = "About Filing Flows: SEC filings drawn as Sankey charts"
    desc = (f"Filing Flows reads every 10-Q, 10-K and earnings release on SEC EDGAR and draws each one as a Sankey chart, "
            f"from revenue to costs, profit and cash. Where the numbers come from, how the charts are made, and @{X_HANDLE} on X.")
    body = f"""<p class='crumbs'><a href='../'>Filing Flows</a> › About</p>
<h1>About Filing Flows</h1>
<p class='lead'>Filing Flows draws every earnings filing on SEC EDGAR as a Sankey chart: where a company's revenue comes from, what it costs, what is left as profit and how much of it turns into cash.</p>
<h2>What it is</h2>
<p>Filing Flows (<a href='../'>filing-flows.com</a>) is an independent website run by an individual developer. It reads US companies' 10-Q and 10-K reports and earnings releases and gives each company a page with its latest quarter drawn as a Sankey, the change from a year and a quarter earlier, and its quarterly history. It covers {count}. Alongside the earnings charts it follows <a href='../m/'>13F fund holdings</a>, <a href='../o/'>officials' stock trades</a> and <a href='../events/'>8-K events</a>.</p>
<h2>Where the numbers come from</h2>
<p>Every figure comes from <a href='https://www.sec.gov/edgar/search/' rel='noopener'>SEC EDGAR</a>: the XBRL financial data companies file with the SEC and the filing documents themselves. The site checks EDGAR every 15 minutes and redraws a company's page when it files. Each company page links to the filing it was read from. Company descriptions and the notes on chart lines are quoted from the filings.</p>
<h2>How the charts and text are made</h2>
<p>The charts are drawn from the reported numbers. The analysis paragraphs are produced by fixed rules from those numbers; no language model is involved. Figures are read automatically, so errors are possible: when a number looks wrong, the filing linked on the page is the authority. The <a href='../#method'>Method</a> page explains how each line of a chart is built.</p>
<h2>Follow and share</h2>
<p>New charts are posted every day on X: <a href='{X_URL}' rel='me noopener'>@{X_HANDLE}</a>. Every chart is free to share with a link to its page, and each company page has an embed code for blogs and newsletters.</p>
<h2>Not investment advice</h2>
<p>Filing Flows is not affiliated with the SEC or with any company it covers. Nothing on the site is investment advice.</p>
<h2>Contact</h2>
<p>For corrections or questions, {contact}. See also the <a href='../privacy.html'>privacy policy</a> and <a href='../terms.html'>terms</a>.</p>"""
    ld = {"@context": "https://schema.org", "@type": "AboutPage", "name": title, "url": url, "description": desc,
          "about": {"@id": f"{base}/#org"}}
    os.makedirs(os.path.join(out_dir, "about"), exist_ok=True)
    open(os.path.join(out_dir, "about", "index.html"), "w", encoding="utf-8").write(page(title, desc, url, body, 1, base + "/og.png", ld))
    return [(url, None)]


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
    ties = {}                                       # cik → customer and supplier links named in filings
    try:
        for f in os.listdir(os.path.join(data_dir, "gamma")):
            if f.endswith(".json") and f[:-5].isdigit():
                for x in (_load(os.path.join(data_dir, "gamma", f)) or {}).get("relationships") or []:
                    for k in (x.get("supplier_cik"), x.get("customer_cik")):
                        if k:
                            ties.setdefault(str(k), []).append(x)
    except OSError:
        pass
    pages = {int(r["cik"]): slug_for(r) for r in latest.values()}
    by_industry = {}
    for r in latest.values():
        by_industry.setdefault(r.get("sic") or r.get("industry"), []).append(r)
    urls, n, pics = [(base + "/", None)], 0, {}
    for cik, r in latest.items():
        try:
            c = json.load(open(os.path.join(data_dir, "c", f"{cik}.json"), encoding="utf-8"))
        except (OSError, ValueError):
            continue
        peers, seen_figs = [], set()
        for x in sorted((x for x in by_industry.get(r.get("sic") or r.get("industry"), []) if x["cik"] != cik), key=lambda x: -(x.get("revenue") or 0)):
            figs = (x.get("revenue"), x.get("yoy"), x.get("label"))             # a co-registrant files the same statements
            if figs in seen_figs and x.get("revenue"):                          # (Sunoco LP and SunocoCorp LLC): listed once
                continue
            seen_figs.add(figs)
            peers.append(x)
            if len(peers) == 8:
                break
        url, doc = company_page(c, r, peers, names.get(r.get("sector"), r.get("sector") or "Other"), base, image=images.get(f"c-{cik}"),
                                all_rows=by_industry.get(r.get("sic") or r.get("industry"), []), chains=chain_of.get(str(r.get("ticker") or "").upper(), []), images=images,
                                ties=ties.get(str(cik)), pages=pages)
        d = os.path.join(out_dir, "c", slug_for(r))
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(doc)
        os.makedirs(os.path.join(d, "embed"), exist_ok=True)       # the frame other sites embed (not indexed itself)
        open(os.path.join(d, "embed", "index.html"), "w", encoding="utf-8").write(embed_page(c, r, url))
        urls.append((url, r.get("filed")))
        if images.get(f"c-{cik}"):
            pics[url] = images[f"c-{cik}"]
        n += 1
    az = sorted(latest.values(), key=lambda x: display_name(x.get("name")).lower())
    os.makedirs(os.path.join(out_dir, "c"), exist_ok=True)
    open(os.path.join(out_dir, "c", "index.html"), "w", encoding="utf-8").write(list_page(
        f"Earnings results of {len(az):,} US companies, A–Z: revenue, margins and cash flow as Sankey charts",
        f"The latest quarterly results of {len(az):,} US-listed companies, read from their 10-Q, 10-K and earnings releases: revenue, growth, operating margin, net income and cash flow, each as a Sankey chart. A–Z.",
        base + "/c/", f"{len(az)} companies with an income-statement Sankey, newest quarter first in each page.", az, 1, index_charts(latest, names)))
    urls.append((base + "/c/", None))
    sectors_lis = []
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
        sectors_lis.append(f"<li><a href='{e(sid)}/'>{e(sname)}</a> <span class='muted'>{n_of(len(items), 'company', 'companies')} · {e(money(sum(x.get('revenue') or 0 for x in items)))} of quarterly revenue</span></li>")
    if sectors_lis:                                              # sector/ itself: the sectors (the address a crumb or a reader may try)
        url = f"{base}/sector/"
        body = (f"<p class='crumbs'><a href='../'>Filing Flows</a> › Sectors</p><h1>Earnings by sector</h1>"
                f"<p class='lead'>The latest quarterly results of US-listed companies by sector, each company's latest quarter drawn from its SEC filing.</p>"
                f"<ul class='seo-list'>{''.join(sectors_lis)}</ul>")
        open(os.path.join(out_dir, "sector", "index.html"), "w", encoding="utf-8").write(page(
            "Earnings by sector | Filing Flows", f"Quarterly earnings of US-listed companies by sector: {len(sectors_lis)} sectors, each company's latest quarter as a Sankey chart.",
            url, body, 1, base + "/og.png"))
        urls.append((url, None))
    urls += chain_pages(data_dir, out_dir, base, images)
    urls += gamma_pages(data_dir, out_dir, base, {slug_for(r) for r in latest.values()}, images)
    urls += model_page(data_dir, out_dir, base)
    urls += about_page(out_dir, base, len(latest))
    urls += license_page(out_dir, base)
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">']
    for u, mod in urls:                              # each company's Sankey picture, for image search
        sm.append(f"<url><loc>{xesc(u)}</loc>" + (f"<lastmod>{xesc(str(mod)[:10])}</lastmod>" if mod else "")
                  + (f"<image:image><image:loc>{xesc(pics[u])}</image:loc></image:image>" if u in pics else "") + "</url>")
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
