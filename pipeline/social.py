"""New charts as ready-to-post X threads, built from the site data (no language model).

Default: e-mail. Each run that finds new company quarters sends one e-mail with every thread laid out post by post
(character counts, an "open in X" link for the first post) and the chart images attached, for posting by hand.
Optional: post directly through the X API (pay-per-use: $0.015 a post, $0.20 with a link).

Thread
  1. headline figures, with the chart (and the year-ago comparison chart) attached
  2. the company in its own words: the opening of Item 1 of its 10-K, quoted
  3. the rule-based analysis paragraph(s)
  4. what the filing itself says about revenue, quoted
  5. source: form, filing date and accession number

    python -m pipeline.social --site _site --store store --check     # exit 0 when there is something to send
    python -m pipeline.social --site _site --store store             # send (needs the e-mail or X secrets)
    python -m pipeline.social --site _site --store store --dry-run   # print the threads, send nothing
"""
import argparse
import base64
import datetime as dt
import functools
import http.server
import json
import os
import re
import sys
import threading

import requests

from . import text as filing_text

API = "https://api.x.com/2"
SECRETS = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")
MAIL_SECRETS = ("MAIL_USERNAME", "MAIL_PASSWORD")
MAIL_MAX_BYTES = 18_000_000            # Gmail accepts 25 MB; attachments grow by a third when encoded
DEFAULTS = {"enabled": True, "mode": "email", "scope": "all", "min_revenue": 1e9, "max_per_run": 4, "max_age_days": 3,
            "preliminary": True, "include_link": False, "images": ["standard", "year_ago"], "site_url": "",
            # general X hashtags: one in the headline in place of the word "results", the others on the last post
            "headline_tag": "#earnings", "hashtags": ["#stocks", "#investing"]}
LIMIT = 280
KEEP_UPPER = {"PLC", "LLC", "LP", "AG", "SA", "NV", "SE", "ETF", "REIT", "II", "III", "IV", "USA", "US", "UK", "AI",
              "NA", "SPA", "AB", "ASA", "BV", "HK", "IBM", "AMD", "CSX", "PG&E", "AT&T", "3M"}


# ------------------------------------------------------------------ text helpers
def xlen(text):
    """Length as X counts it: URLs are 23, most Latin and punctuation 1, other characters 2."""
    text = re.sub(r"https?://\S+", "x" * 23, text)
    return sum(1 if (o <= 4351 or 8192 <= o <= 8205 or 8208 <= o <= 8223 or 8242 <= o <= 8247) else 2
               for o in map(ord, text))


def dec(s):
    return (s or "").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9“\"$(])", dec(text).strip()) if s]


def fit(prefix, body, suffix="", limit=LIMIT):
    """prefix + as many whole sentences of body as fit + suffix; a cut sentence ends with an ellipsis."""
    room = limit - xlen(prefix) - xlen(suffix)
    out = ""
    for s in sentences(body):
        cand = (out + " " + s).strip()
        if xlen(cand) <= room:
            out = cand
        else:
            break
    if not out:
        words, out = dec(body).split(), ""
        for w in words:
            if xlen(out + " " + w + "…") > room:
                break
            out = (out + " " + w).strip()
        out += "…"
    return prefix + out + suffix


def pack(paragraphs, max_posts=2, prefix=""):
    """Sentences of the paragraphs packed into at most max_posts posts."""
    posts, cur = [], prefix
    for s in [s for p in paragraphs for s in sentences(p)]:
        cand = (cur + " " + s).strip() if cur else s
        if xlen(cand) <= LIMIT:
            cur = cand
        else:
            if cur:
                posts.append(cur)
            if len(posts) >= max_posts:
                return posts
            cur = s if xlen(s) <= LIMIT else fit("", s)
    if cur and len(posts) < max_posts:
        posts.append(cur)
    return posts


def display_name(name):
    name = re.sub(r"\s*[/(\\][A-Z]{2}[/)\\]?\s*$", "", name.strip())          # "ACUITY INC. (DE)" -> "ACUITY INC."
    if name.upper() == name:
        name = " ".join(w if (w.upper() in KEEP_UPPER or re.search(r"\d", w)) else w.capitalize() for w in name.split())
    return name


def money(v, big):
    a, s = abs(v), "−" if v < 0 else ""
    if big and a >= 5e6:                                # below $0.01B a billions figure would read "$0.00B"
        b = a / 1e9
        return f"{s}${b:.1f}B" if b >= 0.95 else f"{s}${b:.2f}B"
    m = a / 1e6
    return f"{s}${m:,.1f}M" if m >= 0.95 else f"{s}${a / 1e3:,.0f}K"


def chg(a, b):
    if a is None or b is None or a <= 0 or b <= 0:
        return None
    g = round((a / b - 1) * 100)
    return ("+" if g > 0 else "−" if g < 0 else "") + f"{abs(g)}%"


def fdate(s):
    return dt.date.fromisoformat(s[:10]).strftime("%b %-d, %Y") if s else ""


FOOTNOTE = re.compile(r"^\s*(\(\s*[0-9a-z]{1,2}\s*\)|\[\s*\d{1,2}\s*\]|\*+|†|‡|\d{1,2}\s*[).]\s)")


def is_footnote(text):
    """A footnote or a cross-reference rather than something the company says about the quarter."""
    t = text.strip()
    if len(t) < 60 or FOOTNOTE.match(t):
        return True
    low = t.lower()
    return len(t) < 400 and ("non-gaap financial measure" in low or low.startswith(("see ", "refer to ", "for additional information")))


def filing_quote(q):
    """The company's own words about its revenue (or its largest revenue line):
    (paragraph, where it is from, the line it is about)."""
    nodes = {n["id"]: n for n in q["nodes"]}
    order = [nodes.get("revenue")] + sorted([n for n in q["nodes"] if n["id"].startswith("L:")], key=lambda n: -n["v"])
    where = ("earnings release" if q.get("form") == "8-K"
             else f"{q.get('form')} ({'Item 7' if q.get('form') == '10-K' else 'Item 2'}, MD&A)")
    for n in order:
        for note in (n or {}).get("notes") or []:
            for para in (note.get("text") or "").split("\n"):
                if para.strip() and not is_footnote(para):
                    return para.strip(), where, dec(n.get("name") or "revenue")
    return None


def form_words(q):
    """'10-Q', '10-K' or 'earnings release (8-K)'."""
    return "earnings release (8-K)" if q.get("form") == "8-K" else q.get("form", "")


def filing_line(q, short=False):
    """'10-Q filed Jul 31, 2026 · quarter ended Jun 27, 2026': which document, when, for what period.
    short: the period end without its year when it is the filing's year."""
    period = "fiscal year" if q.get("period") == "fy" else "quarter"
    end = fdate(q.get("end"))
    if short and q.get("end") and q.get("filed") and q["end"][:4] == q["filed"][:4]:
        end = end.rsplit(",", 1)[0]
    words = form_words(q)
    return f"{words[:1].upper() + words[1:]} filed {fdate(q.get('filed'))} · {period} ended {end}"


def chart_captions(q, with_year_ago=True):
    """What each attached image shows, in order: [(short name, caption)]."""
    out = [("Chart 1", f"{q['label']}: where the revenue went, from costs to profit and operating cash flow")]
    vs = (q.get("compare_y") or {}).get("vs")
    if with_year_ago and vs:
        out.append(("Chart 2", f"The same flows compared with {vs}: band width is {q['label']}, "
                               f"a dark strip inside a band is growth over {vs}"))
    return out


def revenue_mix(q, top=5):
    """The revenue lines (segments or products) of this quarter, largest first: [(name, value, share of revenue)]."""
    rev = next((n for n in q["nodes"] if n["id"] == "revenue"), None)
    if not rev or not rev.get("v") or rev["v"] <= 0:
        return []
    leaves = sorted([n for n in q["nodes"] if n["id"].startswith("L:") and (n.get("v") or 0) > 0], key=lambda n: -n["v"])
    if len(leaves) < 2:
        return []
    out = [(dec(n["name"]), n["v"], n["v"] / rev["v"] * 100) for n in leaves[:top]]
    rest = sum(n["v"] for n in leaves[top:])
    if rest > 0:
        out.append(("Other lines", rest, rest / rev["v"] * 100))
    return out


def industry_words(p, sector_names=None):
    """'Electronic Computers (Technology sector)' from the SEC's industry code."""
    from .sectors import SECTORS
    ind = (p.get("industry") or "").strip()
    sec = (sector_names or SECTORS).get(p.get("sector") or "", "")
    if ind and sec and sec != "Other":
        return f"{ind} ({sec} sector)"
    return ind or (f"{sec} sector" if sec else "")


def share_words(s):
    return f"{s:.0f}%" if s >= 9.5 else f"{s:.1f}%".replace(".0%", "%")


def business(c, q, top=5):
    """What the company does, from the filing: its SEC industry and where this quarter's revenue came from."""
    p = c["profile"]
    big = (next((n["v"] for n in q["nodes"] if n["id"] == "revenue"), 0) or 0) >= 1e9
    return {"industry": industry_words(p),
            "mix": [(n, money(v, big), share_words(s)) for n, v, s in revenue_mix(q, top)]}


ROLES = {"headline": "Headline and charts", "business": "What the company does", "about": "The company in its own words",
         "analysis": "Analysis", "quote": "From the filing", "source": "Source"}


def hashtag(word):
    """'#earnings' from 'earnings', '#Earnings', ' #earnings! ': letters, digits and _ only; '' when nothing is left."""
    w = re.sub(r"[^\w]", "", str(word or "").replace("#", ""), flags=re.ASCII)
    return f"#{w}" if w and not w.isdigit() else ""


def hashtags(words):
    """The configured hashtags, cleaned, without repeats (config/x.json "hashtags": a list, or one string)."""
    if isinstance(words, str):
        words = words.replace(",", " ").split()
    out = []
    for w in words or []:
        t = hashtag(w)
        if t and t.lower() not in [x.lower() for x in out]:
            out.append(t)
    return out


def _post1(c, q, cfg, tick, name, n_images):
    """Headline post: which filing, when, the main figures, and what the attached charts show; trimmed to fit."""
    nodes = {n["id"]: n for n in q["nodes"]}
    rev = nodes["revenue"]
    big = rev["v"] >= 1e9
    m = lambda v: money(v, big)
    prelim = q.get("form") == "8-K"
    h = q.get("headline") or {}
    ry, rq = chg(rev["v"], rev.get("y")), chg(rev["v"], rev.get("q"))
    tag = hashtag(cfg.get("headline_tag", DEFAULTS["headline_tag"]))     # "$AAPL Apple Inc. Q3 FY26 #earnings"
    head = (f"${tick} " if tick else "") + f"{name} {q['label']} {tag or 'results'}" + (" (preliminary)" if prelim else "")

    def rev_line(qq=True):
        parts = [x for x in (ry and ry + " Y/Y", qq and rq and rq + " Q/Q") if x]
        return f"Revenue {m(rev['v'])}" + (f" ({', '.join(parts)})" if parts else "")

    gp, om = nodes.get("gp"), h.get("om")
    pc = lambda x: f"{x:.1f}%".replace("-", "−")
    margin_full = " · ".join(x for x in ((f"Gross margin {pc(gp['v'] / rev['v'] * 100)}" if gp else None),
                                          (f"operating margin {pc(om)}" if om is not None else None)) if x)
    margin_full = margin_full[:1].upper() + margin_full[1:]
    margin_short = f"Operating margin {pc(om)}" if om is not None else margin_full
    ni = h.get("ni")
    net = nodes.get("net") or nodes.get("netinc")
    ny = chg(net["v"], net.get("y")) if net and ni is not None else None
    net_line = "" if ni is None else (f"Net earnings {m(ni)}" if ni >= 0 else f"Net loss {m(-ni)}") + (f" ({ny} Y/Y)" if ny else "")
    ocf, fcf = nodes.get("ocf"), nodes.get("fcf")
    cash_full = (f"Operating cash flow {m(ocf['v'])}" + (f" · free cash flow {m(fcf['v'])}" if fcf else "")) if ocf else ""
    cash_short = f"Operating cash flow {m(ocf['v'])}" if ocf else ""
    vs = (q.get("compare_y") or {}).get("vs")
    two = n_images > 1 and vs
    lab = q["label"]
    charts_full = (f"Charts: {lab} from revenue to profit and cash, then the same vs {vs} (dark strips = growth)"
                   if two else f"Chart: {lab} from revenue to profit and cash")
    charts_mid = f"Charts: {lab} revenue to cash; vs {vs} (dark = growth)" if two else f"Chart: {lab} revenue to cash"
    charts_short = f"Charts: {lab}, and vs {vs}" if two else f"Chart: {lab}"
    # the figures first, then the chart explanation: the first version that fits wins
    variants = [(True, margin_full, cash_full, charts_full), (True, margin_full, cash_short, charts_full),
                (True, margin_full, cash_full, charts_mid), (True, margin_full, cash_short, charts_mid),
                (False, margin_full, cash_short, charts_mid), (False, margin_short, cash_short, charts_mid),
                (False, margin_short, cash_short, charts_short), (False, margin_short, "", charts_short),
                (False, "", "", charts_short)]
    room = cfg.get("_room", LIMIT)
    post = ""
    for qq, mg, cash, charts in variants:
        for short in (False, True):
            rows = [x for x in (rev_line(qq), mg, net_line, cash) if x]
            post = "\n".join([head, filing_line(q, short), ""] + rows + ["", charts])
            if xlen(post) <= room:
                return post
    return fit("", post, limit=room)


def compose_parts(c, q, cfg):
    """The thread as [{"role", "text"}]: headline and charts, what the company does, the company in its own words,
    the analysis (one post per paragraph), a quote from the filing, the source. Every post fits 280 characters."""
    p = c["profile"]
    tick = (p.get("tickers") or [""])[0].replace("-", ".")          # cashtags use BRK.B, not BRK-B
    name = display_name(p["name"])
    prelim = q.get("form") == "8-K"
    numbered = cfg.get("numbered", True)
    room = LIMIT - (6 if numbered else 0)                          # "\n\n3/8" (up to 9/9)
    n_images = 1 + ("year_ago" in (cfg.get("images") or []) and bool(q.get("compare_y")))
    parts = [("headline", _post1(c, q, dict(cfg, _room=room), tick, name, n_images))]

    biz = business(c, q)
    intro = c.get("intro")
    intro_text = (intro.get("text") if isinstance(intro, dict) else intro) or ""
    if biz["mix"]:
        head = [x for x in (f"What {name} does", f"Industry: {biz['industry']}" if biz["industry"] else "",
                            f"Where {q['label']} revenue came from:") if x]
        for top in (5, 4, 3, 2):                                   # fewer lines (the rest as "Other lines") until it fits
            post = "\n".join(head + [f"· {n} {v} ({s})" for n, v, s in business(c, q, top)["mix"]])
            if xlen(post) <= room:
                parts.append(("business", post))
                break
    if intro_text.strip():
        cite = filing_text.intro_cite(intro, short=True)
        ind = f" ({biz['industry']})" if biz["industry"] and not any(r == "business" for r, _ in parts) else ""
        parts.append(("about", fit(f"About {name}{ind}, in its own words ({cite}):\n“", intro_text, "”", limit=room)))
    elif biz["industry"] and not any(r == "business" for r, _ in parts):
        parts.append(("business", f"What {name} does\nIndustry: {biz['industry']}"))

    for para in (q.get("analysis") or [])[:3]:
        if para.strip():
            parts.append(("analysis", fit("", para, limit=room)))

    note = filing_quote(q)
    if note:
        about = "" if note[2].lower() == "revenue" else f", on {note[2]}"
        parts.append(("quote", fit(f"From the {note[1]}{about}:\n“", note[0], "”", limit=room)))

    acc = re.search(r"(\d{10}-\d{2}-\d{6})", q.get("index_url") or "")
    period = "fiscal year" if q.get("period") == "fy" else "quarter"
    src = (f"Source: {name} {form_words(q)} for the {period} ended {fdate(q.get('end'))}, filed with the SEC on "
           f"{fdate(q.get('filed'))}" + (f" (accession {acc.group(1)})" if acc else "") + ". "
           + ("Preliminary: read from the earnings release until the 10-Q/10-K. " if prelim else "GAAP figures as reported. ")
           + "Generated automatically; not investment advice.")
    link = cfg.get("site_url", "").rstrip("/")
    if cfg.get("include_link") and link:
        src = fit("", src, f" {link}/#c-{p['cik']}", limit=room)
    parts.append(("source", src if xlen(src) <= room else fit("", src, limit=room)))

    # the general hashtags: on the last post, or (when it is full) on the reply with the most room; never in the headline
    tags = [t for t in hashtags(cfg.get("hashtags", DEFAULTS["hashtags"]))
            if t.lower() != hashtag(cfg.get("headline_tag", DEFAULTS["headline_tag"])).lower()]
    while tags:
        line = "\n\n" + " ".join(tags)
        fits = [i for i in range(1, len(parts)) if xlen(parts[i][1] + line) <= room]
        if fits:
            i = len(parts) - 1 if len(parts) - 1 in fits else max(fits, key=lambda k: room - xlen(parts[k][1]))
            parts[i] = (parts[i][0], parts[i][1] + line)
            break
        tags.pop()                                                 # fewer tags, first ones first
    n = len(parts)
    return [{"role": r, "text": t + (f"\n\n{i + 1}/{n}" if numbered else "")} for i, (r, t) in enumerate(parts)]


def compose(c, q, cfg):
    """The thread as a list of post texts."""
    return [x["text"] for x in compose_parts(c, q, cfg)]


# ------------------------------------------------------------------ what to post
def load_cfg(path):
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.load(open(path)))
    except FileNotFoundError:
        pass
    cfg["site_url"] = cfg.get("site_url") or os.environ.get("X_SITE_URL", "")
    return cfg


def load_state(store):
    try:
        return json.load(open(os.path.join(store, "x_state.json")))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"posted": {}}


def save_state(store, st):
    os.makedirs(store, exist_ok=True)
    json.dump(st, open(os.path.join(store, "x_state.json"), "w"), separators=(",", ":"))


def posted_already(st, cik, end):
    e0 = dt.date.fromisoformat(end)
    for key in st["posted"]:
        k_cik, k_end = key.split(":")
        if int(k_cik) == int(cik) and abs((dt.date.fromisoformat(k_end) - e0).days) <= 10:
            return True                            # the 10-Q after a posted 8-K is not posted again
    return False


def candidates(site, st, cfg, today=None):
    ix = json.load(open(os.path.join(site, "data", "index.json")))
    today = today or dt.date.today()
    out = []
    for e in ix["companies"]:
        if posted_already(st, e["cik"], e["end"]):
            continue
        if cfg["scope"] == "starred" and not e.get("starred"):
            continue
        if (e.get("revenue") or 0) < cfg["min_revenue"]:
            continue
        if e.get("prelim") and not cfg["preliminary"]:
            continue
        if e.get("filed") and (today - dt.date.fromisoformat(e["filed"])).days > cfg["max_age_days"]:
            continue
        out.append(e)
    out.sort(key=lambda e: (e.get("filed") or "", e.get("revenue") or 0), reverse=True)
    return out[: cfg["max_per_run"]]


def quarter_of(site, e):
    c = json.load(open(os.path.join(site, "data", "c", f"{e['cik']}.json")))
    q = next((x for x in c["quarters"] if x["end"] == e["end"]), c["quarters"][0])
    return c, q


# ------------------------------------------------------------------ chart images (the site's own renderer, headless)
class Charts:
    """One headless Chromium for all the drawing in a run, using the site's own web/sankey.js:
    PNG/JPG images, SVG (for PDF reports) and PDF printing of an HTML page.
    site: the built site folder, or the URL of the published site.

        with Charts("_site") as ch:
            png = ch.image(("chart", spec, None), "png")
            svg = ch.svg(("history", company_json))
            pdf = ch.pdf(html)
    """

    DRAW = """async ([kind, data, mode, fmt, opts, lopts]) => {
      await document.fonts.ready;
      const sc = kind === 'history' ? Sankey.history(data) : Sankey.layout(data, Object.assign({ compare: mode }, lopts || {}));
      if (fmt === 'svg') return Sankey.toSVG(Object.assign({}, sc, { shapes: sc.shapes.filter((s) => !s.ui) }), opts.aria || 'Chart');
      const blob = await Sankey.exportScene(sc, fmt, opts);
      const buf = new Uint8Array(await blob.arrayBuffer());
      let s = '';
      for (let i = 0; i < buf.length; i += 32768) s += String.fromCharCode.apply(null, buf.subarray(i, i + 32768));
      return btoa(s);
    }"""

    def __init__(self, site):
        self.site = str(site)
        self.srv = self.pw = self.browser = self.page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        if re.match(r"https?://", self.site):
            self.base = self.site.rstrip("/") + "/"
        else:
            class Quiet(http.server.SimpleHTTPRequestHandler):
                def log_message(self, *a):
                    pass
            self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=os.path.abspath(self.site)))
            threading.Thread(target=self.srv.serve_forever, daemon=True).start()
            self.base = f"http://127.0.0.1:{self.srv.server_address[1]}/"
        try:
            self.pw = sync_playwright().start()
            self.browser = self.pw.chromium.launch()
            self.page = self.browser.new_page()
            self.page.goto(self.base + "index.html#method")
            self.page.wait_for_function("window.Sankey && document.fonts")
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc):
        for close in (lambda: self.browser and self.browser.close(), lambda: self.pw and self.pw.stop(),
                      lambda: self.srv and self.srv.shutdown()):
            try:
                close()
            except Exception:
                pass
        self.srv = self.pw = self.browser = self.page = None
        return False

    def _draw(self, what, fmt, opts):
        kind, data, mode, lopts = (tuple(what) + (None, None))[:4]
        return self.page.evaluate(self.DRAW, [kind, data, mode, fmt, opts, lopts or {}])

    def image(self, what, fmt="png", scale=2, quality=None, width=None):
        """what: ("chart", spec, compare mode or None[, layout options such as {"decreases": True}])
        or ("history", company json) -> image bytes."""
        return base64.b64decode(self._draw(what, fmt, {"scale": scale, "quality": quality, "width": width}))

    def svg(self, what, aria="Chart"):
        """The same drawing as standalone SVG markup (screen-only marks removed), for printing."""
        return self._draw(what, "svg", {"aria": aria})

    def pdf(self, html, footer=""):
        """Print an HTML page (US Letter, landscape) with Chromium: vector text and charts."""
        pg = self.browser.new_page()
        try:
            pg.set_content(html, wait_until="load", timeout=60000)
            pg.evaluate("document.fonts.ready.then(() => true)")
            foot = ('<div style="width:100%;padding:0 0.5in;font:7.5px Helvetica,Arial,sans-serif;color:#6b6a66;'
                    'display:flex;justify-content:space-between"><span>' + footer + '</span>'
                    '<span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>')
            return pg.pdf(format="Letter", landscape=True, print_background=True, display_header_footer=True,
                          header_template="<div></div>", footer_template=foot,
                          margin={"top": "0.45in", "bottom": "0.55in", "left": "0.5in", "right": "0.5in"})
        finally:
            pg.close()


def render_charts(site, jobs, fmt="png", scale=2, quality=None, width=None):
    """jobs: list of (spec, compare mode or None) -> list of image bytes, drawn by web/sankey.js in Chromium."""
    with Charts(site) as ch:
        return [ch.image(("chart", spec, mode), fmt, scale, quality, width) for spec, mode in jobs]


# ------------------------------------------------------------------ X API v2 (OAuth 1.0a user context)
class XError(Exception):
    pass


class RateLimited(XError):
    pass


class X:
    def __init__(self, keys, session=None):
        from requests_oauthlib import OAuth1
        self.auth = OAuth1(keys["X_API_KEY"], keys["X_API_SECRET"], keys["X_ACCESS_TOKEN"], keys["X_ACCESS_TOKEN_SECRET"])
        self.s = session or requests.Session()

    def _check(self, r):
        if r.status_code == 429:
            raise RateLimited("rate limited by X; the rest waits for the next run")
        if r.status_code >= 300:
            raise XError(f"X API {r.status_code}: {r.text[:300]}")
        return r.json()

    def upload(self, png):
        r = self.s.post(f"{API}/media/upload", auth=self.auth, files={"media": ("sankey.png", png, "image/png")},
                        data={"media_category": "tweet_image"}, timeout=120)
        return self._check(r)["data"]["id"]

    def post(self, text, media_ids=None, reply_to=None):
        body = {"text": text}
        if media_ids:
            body["media"] = {"media_ids": media_ids}
        if reply_to:
            body["reply"] = {"in_reply_to_tweet_id": reply_to}
        return self._check(self.s.post(f"{API}/tweets", auth=self.auth, json=body, timeout=60))["data"]["id"]


def post_thread(x, posts, images):
    ids = []
    media = [x.upload(png) for png in images][:4]
    for i, text in enumerate(posts):
        ids.append(x.post(text, media_ids=media if i == 0 else None, reply_to=ids[-1] if ids else None))
    return ids


# ------------------------------------------------------------------ e-mail (post by hand)
def intent_url(text):
    from urllib.parse import quote
    return "https://x.com/intent/post?text=" + quote(text, safe="")


def image_names(e, q, n):
    base = re.sub(r"[^A-Za-z0-9.]+", "-", f"{e.get('ticker') or e['cik']}-{q['label']}").strip("-")
    names = [f"{base}-1-chart.png"]
    if n > 1:
        names.append(f"{base}-2-vs-{re.sub(r'[^A-Za-z0-9]+', '-', (q.get('compare_y') or {}).get('vs', 'year-ago'))}.png")
    return names


def build_email(items, cfg, sender, to):
    """items: list of (e, c, q, posts, [(filename, png)]); posts: texts or compose_parts() dicts.
    -> EmailMessage with plain-text and HTML bodies: per company the filing, what each attached chart shows, the posts."""
    import html as H
    from email.message import EmailMessage
    tickers = ", ".join(e.get("ticker") or str(e["cik"]) for e, *_ in items)
    msg = EmailMessage()
    msg["Subject"] = (f"X thread: {display_name(items[0][1]['profile']['name'])} {items[0][2].get('label')} — {tickers}" if len(items) == 1
                      else f"Filing Flows: {len(items)} new charts ready to post — {tickers}")
    msg["From"], msg["To"] = sender, to
    site = cfg.get("site_url", "").rstrip("/")
    text, rich = [], []
    small = "font:14px/1.5 Helvetica,Arial,sans-serif;color:#555;margin:0 0 6px"
    for e, c, q, posts, images in items:
        posts = [p if isinstance(p, dict) else {"role": "", "text": p} for p in posts]
        title = f"{display_name(c['profile']['name'])} ({e.get('ticker') or c['profile'].get('cik')}) · {q.get('label')}"
        page = f"{site}/#c-{e['cik']}-{q['end']}" if site else ""
        caps = chart_captions(q, len(images) > 1)
        files = [(name, f"{short}: {cap}") for (name, _), (short, cap) in zip(images, caps)]
        text.append(f"{'=' * 60}\n{title}\n{filing_line(q)}\n"
                    + "".join(f"Attach to post 1: {name} ({what})\n" for name, what in files)
                    + f"Open post 1 in X: {intent_url(posts[0]['text'])}" + (f"\nChart page: {page}" if page else "") + "\n")
        rich.append(f'<h2 style="font:600 19px/1.3 Helvetica,Arial,sans-serif;margin:28px 0 4px">{H.escape(title)}</h2>'
                    f'<p style="{small}">{H.escape(filing_line(q))}</p>'
                    + "".join(f'<p style="{small}">Attach to post 1: <b>{H.escape(name)}</b> · {H.escape(what)}</p>' for name, what in files)
                    + f'<p style="{small};margin-bottom:12px"><a href="{H.escape(intent_url(posts[0]["text"]))}">Open post 1 in X</a>'
                    + (f' · <a href="{H.escape(page)}">Chart page</a>' if page else "") + "</p>")
        for i, p in enumerate(posts):
            ptxt = p["text"]
            label = (f"Post {i + 1} of {len(posts)}" + (f" · {ROLES[p['role']]}" if p["role"] in ROLES else "")
                     + f" · {xlen(ptxt)}/{LIMIT}" + (" · reply to the post above" if i else " · attach the charts"))
            text.append(f"--- {label} ---\n{ptxt}\n")
            rich.append(f'<div style="font:12px Helvetica,Arial,sans-serif;color:#888;margin:10px 0 3px">{H.escape(label)}</div>'
                        f'<pre style="white-space:pre-wrap;font:15px/1.45 Helvetica,Arial,sans-serif;background:#f4f3ef;'
                        f'border-radius:6px;padding:10px 12px;margin:0">{H.escape(ptxt)}</pre>')
    footer = ("Each block is one post: paste the first as a new post with the attached images, then add the others as "
              "replies (or with + in the composer). Generated by Filing Flows from SEC filings.")
    msg.set_content("\n".join(text) + "\n" + footer)
    msg.add_alternative('<div style="max-width:680px">' + "".join(rich) +
                        f'<p style="font:12px/1.5 Helvetica,Arial,sans-serif;color:#888;margin-top:28px">{H.escape(footer)}</p></div>',
                        subtype="html")
    for *_, images in items:
        for name, png in images:
            msg.add_attachment(png, maintype="image", subtype="png", filename=name)
    return msg


def sender_address(user):
    """The From line: MAIL_FROM when set (another provider, your own domain), else the login address."""
    return os.environ.get("MAIL_FROM") or user


def send_email(msg, user, password, host=None, port=None):
    """SMTP_HOST / SMTP_PORT choose the provider (default Gmail, port 465 over SSL; 587 uses STARTTLS)."""
    import smtplib
    host = host or os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    port = int(port or os.environ.get("SMTP_PORT") or 465)
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=60) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=60) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(msg)


def batches(items, max_bytes=MAIL_MAX_BYTES):
    """Split threads into e-mails that stay under the attachment size limit."""
    out, cur, size = [], [], 0
    for it in items:
        n = sum(len(png) for _, png in it[4])
        if cur and size + n > max_bytes:
            out.append(cur)
            cur, size = [], 0
        cur.append(it)
        size += n
    if cur:
        out.append(cur)
    return out


def send_one(site, cfg, cik, end):
    """E-mail one company quarter's thread with its charts, whatever was sent before (the site's "Email me" button)."""
    user, password = os.environ.get("MAIL_USERNAME", ""), os.environ.get("MAIL_PASSWORD", "")
    if not (user and password):
        raise SystemExit("MAIL_USERNAME and MAIL_PASSWORD secrets are required")
    e = {"cik": int(cik), "end": end}
    c, q = quarter_of(site, e)
    if q["end"] != end:
        raise SystemExit(f"no quarter ending {end} on the site for CIK {cik}")
    e["ticker"] = (c["profile"].get("tickers") or [""])[0]
    modes = [None] + (["y"] if "year_ago" in cfg["images"] and q.get("compare_y") else [])
    pngs = render_charts(site, [(q, m) for m in modes])
    item = (e, c, q, compose(c, q, cfg), list(zip(image_names(e, q, len(modes)), pngs)))
    send_email(build_email([item], cfg, sender_address(user), os.environ.get("MAIL_TO") or user), user, password)
    print(f"e-mailed {e['ticker'] or cik} {q['label']}")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="_site")
    ap.add_argument("--store", default="store")
    ap.add_argument("--config", default="config/x.json")
    ap.add_argument("--check", action="store_true", help="exit 0 if sending is set up and something is waiting")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--one", metavar="CIK:END", help="e-mail the thread for one company quarter now (on request)")
    args = ap.parse_args()
    cfg, st = load_cfg(args.config), load_state(args.store)
    if args.one:
        send_one(args.site, cfg, *args.one.split(":", 1))
        return
    from . import notify, owner                        # (they import this module)
    supa = owner.supa_from_env()
    osets = owner.settings(supa, cfg)
    now = dt.datetime.now(dt.timezone.utc)
    mail_keys = {k: os.environ.get(k, "") for k in MAIL_SECRETS}
    slot = owner.due_slot(now, osets, st) if cfg["enabled"] and all(mail_keys.values()) else None
    mode = cfg.get("mode", "email")
    instant = mode == "api" or bool(osets.get("instant_threads"))     # e-mail threads after each scan: an owner setting
    keys = {k: os.environ.get(k, "") for k in (MAIL_SECRETS if mode == "email" else SECRETS)}
    ready = cfg["enabled"] and instant and mode in ("email", "api") and all(keys.values())
    todo = candidates(args.site, st, cfg)
    if args.check:
        if slot and not owner.pending(notify.Site(args.site).json("index.json"), st, osets, cfg, now):
            owner.mark_sent(st, [], slot, now)         # a morning with nothing new: done, no browser needed
            save_state(args.store, st)
            print("owner daily report: nothing new since the last one")
            slot = None
        sys.exit(0 if (ready and todo) or slot else 1)
    if slot:                                           # the owner's daily report (8:00 in the owner's time zone)
        site = notify.Site(args.site)
        user, password = mail_keys["MAIL_USERNAME"], mail_keys["MAIL_PASSWORD"]
        mailer = notify.Mailer(os.environ.get("SMTP_HOST") or "smtp.gmail.com", os.environ.get("SMTP_PORT") or 465, user, password)
        try:
            owner.send_daily(site, st, cfg, osets, now, slot, mailer.send, sender_address(user), owner.addresses(supa),
                             cfg.get("site_url", ""), dry_run=args.dry_run)
        except Exception as err:
            print(f"::warning::owner daily report not sent: {err}")
        finally:
            mailer.close()
        if not args.dry_run:
            save_state(args.store, st)
    if not instant:
        print("X threads after each scan: off (owner setting); the daily report carries them.")
        return
    if not ready or args.dry_run:
        why = ("dry run" if args.dry_run else "config/x.json has enabled: false" if not cfg["enabled"]
               else f"secrets missing: {', '.join(k for k, v in keys.items() if not v)}")
        print(f"Sending off ({why}); {len(todo)} thread(s) waiting:")
        for e in todo:
            c, q = quarter_of(args.site, e)
            print("\n".join(f"  [{i + 1}] {t}" for i, t in enumerate(compose(c, q, cfg))), "\n")
        return
    jobs, threads = [], []
    for e in todo:
        c, q = quarter_of(args.site, e)
        modes = [None] + (["y"] if "year_ago" in cfg["images"] and q.get("compare_y") else [])
        threads.append((e, c, q, len(modes)))
        jobs += [(q, m) for m in modes]
    pngs = render_charts(args.site, jobs)
    items, k = [], 0
    for e, c, q, n in threads:
        items.append((e, c, q, compose(c, q, cfg), list(zip(image_names(e, q, n), pngs[k:k + n]))))
        k += n
    now = lambda: dt.datetime.utcnow().isoformat(timespec="seconds")
    if mode == "email":
        to = os.environ.get("MAIL_TO") or keys["MAIL_USERNAME"]
        for group in batches(items):
            send_email(build_email(group, cfg, sender_address(keys["MAIL_USERNAME"]), to),
                       keys["MAIL_USERNAME"], keys["MAIL_PASSWORD"])
            for e, c, q, *_ in group:
                st["posted"][f"{e['cik']}:{e['end']}"] = {"t": now(), "via": "email"}
                print(f"e-mailed {e.get('ticker') or e['cik']} {q['label']}")
            save_state(args.store, st)
        return
    x = X(keys)
    for e, c, q, posts, images in items:
        key = f"{e['cik']}:{e['end']}"
        try:
            ids = post_thread(x, posts, [png for _, png in images])
            st["posted"][key] = {"t": now(), "ids": ids}
            print(f"posted {e.get('ticker') or e['cik']} {q['label']}: https://x.com/i/status/{ids[0]}")
        except RateLimited as err:
            print(err)
            break
        except XError as err:
            print(f"failed {e.get('ticker') or e['cik']}: {err}")
            st["posted"][key] = {"t": now(), "error": str(err)[:200]}
        finally:
            save_state(args.store, st)


if __name__ == "__main__":
    main()
