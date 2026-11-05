"""Analysis traps on the site (pipeline/traps.py, docs/TRAP_RULEBOOK.md):

    data/traps/<cik>.json            every rule's finding for the company (status, severity, confidence, the figures, the
                                     normal explanations, the missing evidence, the filing it was read from)
    data/traps/index.json            one row per company: which rules triggered, the top severity, the data's date
    c/<slug>/analysis-traps/         the company's findings as a page: the three to check first, then every rule
    c/<slug>/  (a card)              "Before you read the chart": the priority items, linked to the page
    disclosures/analysis-traps/      the rules explained, how many companies each one triggers on, the companies by rule
    sitemap-traps.xml

Independent of the quality score and every other module: it reads the published files and writes its own. TRAPS=off in
the environment skips it. Not investment advice: a triggered rule is a question to verify, never a conclusion.

    python scripts/seo_traps.py --site _site
"""
import argparse
import datetime as dt
import json
import os
import sys
from xml.sax.saxutils import escape as xesc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import seo  # noqa: E402
from pipeline import traps as T  # noqa: E402

e, display_name, fdate = seo.e, seo.display_name, seo.fdate
STATUS_WORD = {"triggered": "Triggered", "clear": "Not triggered", "insufficient_data": "Insufficient data", "not_applicable": "Not applicable", "review": "To review", "expired": "Out of date"}
STATUS_CLASS = {"triggered": "trig", "clear": "ok", "insufficient_data": "na", "not_applicable": "na", "review": "rev", "expired": "na"}
DISCLAIMER = ("<p class='muted'>Each rule reads the company's own filings by a fixed formula and says what would explain the same figures innocently. "
              "A triggered rule is a question to verify, not a finding of manipulation, and not a view on the stock. Missing data is shown as missing, never as clear. "
              "Not investment advice.</p>")


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def money(v):
    return T._money(v)


def fmt_obs(k, v):
    """one observed figure for the page: dollars, percentages, counts, dates"""
    if v is None:
        return "—"
    if isinstance(v, list):
        return "; ".join(" / ".join(str(x) for x in row) if isinstance(row, list) else str(row) for row in v)
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, str):
        return v
    if any(k.endswith(s) for s in ("_pct", "_pct_revenue", "_yoy", "_growth", "_change", "share_of_delta", "_share")) or k in ("latest_gap_pct", "eps_growth_from_share_count"):
        return f"{100 * v:+.1f}%" if abs(v) < 20 else f"{v:.2f}"
    if k.startswith("eps"):
        return f"${v:.2f}"
    if k in ("dso", "dso_median_8q", "cover_ratio", "buybacks_over_sbc"):
        return f"{v:.1f}"
    if k.endswith("shares") or k.endswith("_prior") and "shares" in k or "shares" in k:
        return f"{v / 1e6:,.1f}M shares" if abs(v) >= 1e6 else f"{v:,.0f} shares"
    if isinstance(v, (int, float)) and abs(v) >= 1e5:
        return money(v)
    return f"{v:,}" if isinstance(v, int) else f"{v:,.2f}"


LABEL = {"fy_prior": "Fiscal year before", "fy_current": "Fiscal year", "ocf_prior": "Operating cash flow, year before", "ocf_current": "Operating cash flow", "capex_prior": "Capex, year before",
         "capex_current": "Capex", "fcf_prior": "Free cash flow, year before", "fcf_current": "Free cash flow", "delta_fcf": "Change in FCF", "delta_capex": "Change in capex",
         "delta_wc_cash": "Working capital: change in its cash contribution", "capex_reduction": "Of which: capex cut", "wc_release": "Of which: working capital released",
         "temporary_share_of_delta": "Share of the increase that need not repeat", "other_ocf_change": "Operating cash flow before working capital: change",
         "sbc": "Stock compensation", "revenue": "Revenue", "sbc_pct_revenue": "SBC / revenue", "buybacks": "Buybacks", "buybacks_over_sbc": "Buybacks / SBC",
         "diluted_shares_prior": "Diluted shares, year before", "diluted_shares": "Diluted shares", "diluted_change": "Diluted shares: change", "fy": "Fiscal year",
         "quarter": "Quarter", "revenue_yoy": "Revenue, year over year", "receivables_yoy": "Receivables, year over year", "prior_quarter": "Quarter before",
         "prior_revenue_yoy": "Revenue y/y, quarter before", "prior_receivables_yoy": "Receivables y/y, quarter before", "dso": "Days sales outstanding", "dso_median_8q": "DSO, median of eight quarters",
         "receivables": "Receivables", "quarters": "Quarter / adjusted EPS / GAAP EPS / gap", "quarters_adjusted_above_gaap_10pct": "Quarters with adjusted ≥ 10% above GAAP", "of": "Quarters compared",
         "latest_gap_pct": "Latest gap", "cash": "Cash and investments", "debt": "Debt", "net_debt": "Net debt", "due_12m": "Due within a year", "due_source": "Read from", "fcf_ttm": "Free cash flow, twelve months",
         "cover": "Cash plus free cash flow", "cover_ratio": "Coverage of what is due", "due_2y": "Due in the second year", "as_of": "Balance sheet date",
         "eps_prior": "EPS, year before", "eps": "EPS", "net_income_prior": "Net income, year before", "net_income": "Net income", "eps_growth": "EPS growth",
         "net_income_growth": "Net income growth", "share_count_change": "Diluted shares: change", "eps_growth_from_share_count": "EPS growth from the share count"}


def lower(name):
    """a rule's name inside a sentence: "FCF growth = the business improved" keeps its acronyms"""
    w = name.split(" ", 1)
    return (w[0] if w[0].isupper() else w[0].lower()) + (" " + w[1] if len(w) > 1 else "")


def finding_html(f, name):
    st = f["status"]
    head = (f"<h3 id='{e(f['rule_id'])}'><span class='trap-id'>{e(f['rule_id'])}</span> {e(f['name'])} <span class='trap-st {STATUS_CLASS[st]}'>{STATUS_WORD[st]}</span>"
            + (f" <span class='muted'>severity {e(f['severity'])} · confidence {e(f['confidence'])}</span>" if st == "triggered" else f" <span class='muted'>confidence {e(f['confidence'])}</span>" if f.get("confidence") else "")
            + "</h3>")
    if st in ("insufficient_data", "not_applicable", "expired"):
        return head + f"<p class='muted'>{e(f.get('reason') or '')}</p>"
    body = f"<p>{e(f['explanation'])}</p>"
    if f.get("observed"):
        body += ("<details><summary>The figures and how they are read</summary><div class='tbl-wrap'><table><tbody>"
                 + "".join(f"<tr><td>{e(LABEL.get(k, k.replace('_', ' ')))}</td><td class='num'>{e(fmt_obs(k, v))}</td></tr>" for k, v in f["observed"].items())
                 + f"</tbody></table></div><p class='muted'>{e(f['how'])}</p>"
                 + ("<p class='muted'>Source: " + " · ".join((f"<a href='{e(x['url'])}' rel='nofollow'>{e(x['period'])}</a>" if x.get("url") else e(str(x['period']))) + (f" ({e(x['what'])})" if x.get("what") else "") for x in f["evidence"]) + "</p>" if f.get("evidence") else "")
                 + "</details>")
    if st in ("triggered", "review"):
        if f.get("alternative_explanations"):
            body += "<p><b>What would explain it innocently</b></p><ul class='seo-list'>" + "".join(f"<li>{e(x)}</li>" for x in f["alternative_explanations"]) + "</ul>"
        if f.get("missing_evidence"):
            body += "<p><b>What to look for in the filing</b></p><ul class='seo-list'>" + "".join(f"<li>{e(x)}</li>" for x in f["missing_evidence"]) + "</ul>"
        body += f"<p class='muted'>Look again: {e(f.get('next_review', 'next filing').replace('_', ' '))}.</p>"
    return head + body


def page_for(doc, r, slug, base):
    name, t = display_name(r.get("name")), r.get("ticker") or ""
    url = f"{base}/c/{slug}/analysis-traps/"
    F = {f["rule_id"]: f for f in doc["findings"]}
    pri = [F[k] for k in doc["priority"] if k in F]
    s = doc["summary"]
    n_tr = s["triggered"]
    lead = (f"{name} ({t}): {seo.n_of(n_tr, 'rule')} of {len(doc['findings'])} triggered on the filings to {fdate(doc['as_of'])}"
            + (f": {'; '.join(lower(f['name']) for f in pri if f['status'] == 'triggered')}" if n_tr else "")
            + (f". {s['review']} to review" if s["review"] else "") + (f"; {s['insufficient_data']} with insufficient data" if s["insufficient_data"] else "")
            + (f"; {s['not_applicable']} not applicable" if s["not_applicable"] else "") + (f"; {s['expired']} out of date" if s["expired"] else "") + ". "
            "Each is a question to verify, with the normal explanation that would produce the same figures.")
    top = ("<h2 id='first'>Check these first</h2>" + "".join(
        f"<div class='trap-card {STATUS_CLASS[f['status']]}'><p><b><a href='#{e(f['rule_id'])}'>{e(f['name'])}</a></b> <span class='trap-st {STATUS_CLASS[f['status']]}'>{STATUS_WORD[f['status']]}</span>"
        + (f" · severity {e(f['severity'])}" if f.get("severity") else "") + f" · confidence {e(f['confidence'])}</p><p>{e(f['explanation'])}</p>"
        + (f"<p class='muted'>Innocent reading: {e(f['alternative_explanations'][0])}.</p>" if f.get("alternative_explanations") else "") + "</div>" for f in pri)
           if pri else "<h2 id='first'>Check these first</h2><p>No rule is triggered on the latest filings" + (", and none is marked to review" if not s["review"] else "") + ".</p>")
    every = "<h2 id='all'>Every rule</h2>" + "".join(finding_html(f, name) for f in doc["findings"])
    body = (f"<p class='crumbs'><a href='../../../'>Filing Flows</a> › <a href='../../'>Companies</a> › <a href='../'>{e(name)}</a> › Analysis traps</p>"
            f"<h1>{e(name)} ({e(t)}): analysis traps</h1><p class='muted'>Where its figures could mislead a reader, and what to check before taking them at face value · "
            f"Data: {e(r.get('label') or 'latest quarter')}, to {e(fdate(doc['as_of']))}, filed {e(fdate(doc['filed']))}; rules v{e(doc['rule_version'])}</p>"
            f"<p class='lead'>{e(lead)}</p>{top}{every}"
            "<h2 id='statuses'>What the statuses mean</h2><div class='seo-note'><p><b>Triggered</b>: the filings show the pattern; read the normal explanations and the missing evidence before concluding anything. "
            "<b>To review</b>: one quarter or a weak signal; a reader's judgement, not a pattern. <b>Not triggered</b>: the pattern is absent on these figures. <b>Insufficient data</b>: the filings read so far do not hold what the rule needs; "
            "this is not a clean bill. <b>Not applicable</b>: the rule is not meant for this kind of company (a bank's working capital, a loss-making quarter's EPS growth). <b>Out of date</b>: the latest filing is more than fifteen months old.</p>"
            "<p>Severity is what the pattern could mean for cash, value or solvency; confidence is how reliable the inputs and the reading are. The two are kept apart.</p></div>"
            f"<p><a class='seo-cta' href='../../../disclosures/analysis-traps/'>Every rule and the companies it triggers on →</a> <a href='../cash-flow/'>{e(name)}: cash flow →</a> <a href='../earnings-quality/'>Earnings quality score →</a></p>"
            + DISCLAIMER)
    title = f"{name} ({t}) Analysis Traps: {seo.n_of(n_tr, 'rule')} triggered on its filings" if n_tr else f"{name} ({t}) Analysis Traps: what to check before reading the figures"
    qa = [(f"What should I check before trusting {seo.poss(name)} figures?", lead)] + [(f"Is {seo.poss(name)} {f['name'].split(' = ')[0].lower()} what it looks like?", f["explanation"]) for f in pri[:2]]
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "Filing Flows", "item": base + "/"},
                                                         {"@type": "ListItem", "position": 2, "name": name, "item": f"{base}/c/{slug}/"},
                                                         {"@type": "ListItem", "position": 3, "name": "Analysis traps", "item": url}]},
        {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qa]},
        {"@type": "WebPage", "name": title, "url": url, "description": lead[:300], "dateModified": doc["filed"]}]}
    return url, seo.page(seo.fit(title), lead[:300], url, body, 3, base + "/og.png", ld)


def card_on_company_page(site, slug, doc):
    """the company page: a short card before the chart, linked to the page; the toc gets a link"""
    p = os.path.join(site, "c", slug, "index.html")
    if not os.path.exists(p):
        return
    t = open(p, encoding="utf-8").read()
    if "analysis-traps/" in t:
        return
    F = {f["rule_id"]: f for f in doc["findings"]}
    pri = [F[k] for k in doc["priority"] if k in F]
    if pri:
        items = "".join(f"<li><a href='analysis-traps/#{e(f['rule_id'])}'>{e(f['name'])}</a> <span class='trap-st {STATUS_CLASS[f['status']]}'>{STATUS_WORD[f['status']]}</span>: {e(f['explanation'].split('. ')[0])}.</li>" for f in pri)
        card = f"<aside class='seo-traps'><p><b>Before you read the chart</b> · {seo.n_of(doc['summary']['triggered'], 'analysis trap')} triggered on the latest filings</p><ul>{items}</ul><p><a href='analysis-traps/'>Every rule, the figures and the innocent explanations →</a></p></aside>"
    else:
        card = f"<aside class='seo-traps'><p><b>Before you read the chart</b> · no analysis trap triggered on the latest filings <a href='analysis-traps/'>(the rules, and what could not be checked →)</a></p></aside>"
    t = t.replace('<nav class="seo-toc" aria-label="On this page">', '<nav class="seo-toc" aria-label="On this page"><a href="analysis-traps/">Analysis traps</a>', 1)
    if "</nav>" in t:
        t = t.replace("</nav>", "</nav>" + card, 1)
    else:
        t = t.replace("</main>", card + "</main>", 1)
    open(p, "w", encoding="utf-8").write(t)


def hub_page(site, base, docs, rows, slugs):
    """disclosures/analysis-traps/: each rule, its count, the companies it triggers on (largest first)"""
    n = len(docs)
    by_rule = {k: [] for k in T.NAMES}
    for cik, d in docs.items():
        for f in d["findings"]:
            if f["status"] == "triggered":
                by_rule[f["rule_id"]].append((cik, f))
    rev = {int(r["cik"]): r.get("revenue") or 0 for r in rows}
    name_of = {int(r["cik"]): (display_name(r.get("name")), r.get("ticker") or "") for r in rows}
    secs = ""
    for k, (nm, area) in T.NAMES.items():
        hits = sorted(by_rule[k], key=lambda x: -rev.get(x[0], 0))
        L = lambda cik: (f"<a href='../../c/{slugs[cik]}/analysis-traps/#{k}'><b>{e(name_of[cik][1])}</b></a>" if cik in slugs else f"<b>{e(name_of[cik][1])}</b>") + f" {e(name_of[cik][0])}"
        secs += (f"<h2 id='{k}'>{e(k)} · {e(nm)} <span class='muted'>{len(hits)} of {n}</span></h2>"
                 + (f"<p>{e(RULE_BLURB[k])}</p>")
                 + (f"<ul class='seo-list'>" + "".join(f"<li>{L(cik)} <span class='muted'>{e(f['severity'])} · {e(f['explanation'].split('. ')[0])}.</span></li>" for cik, f in hits[:40]) + "</ul>" if hits else "<p class='muted'>No company triggers it on the latest filings.</p>"))
    counts = {k: len(by_rule[k]) for k in T.NAMES}
    lead = (f"{seo.n_of(len(T.NAMES), 'rule')} on {seo.n_of(n, 'company', 'companies')}' filings, each a common misreading of a figure: "
            + ", ".join(f"{lower(T.NAMES[k][0])} ({counts[k]})" for k in T.NAMES) + ". A triggered rule is a question to verify, with the normal explanation that would produce the same figures.")
    url = f"{base}/disclosures/analysis-traps/"
    body = (f"<p class='crumbs'><a href='../../'>Filing Flows</a> › <a href='../'>Disclosures</a> › Analysis traps</p><h1>Analysis traps: where the figures could mislead you</h1>"
            f"<p class='lead'>{e(lead)}</p><nav class='seo-toc'>" + "".join(f"<a href='#{k}'>{k}</a>" for k in T.NAMES) + "</nav>" + secs
            + "<h2 id='method'>Method</h2><div class='seo-note'><p>Six rules of a hundred-item catalogue (docs/TRAP_RULEBOOK.md in the repository), chosen because the site already holds every figure they need: "
              "the cash bridge, capex, stock compensation and share counts, receivables, debt maturities, adjusted against GAAP EPS. Each reads the company's own filings by a fixed formula with coarse, "
              "documented thresholds and carries its figures, so a reader can apply stricter ones. Statuses: triggered, to review, not triggered, insufficient data, not applicable, out of date; "
              "missing data is never shown as clear. Severity and confidence are kept apart. The rules are independent of the earnings quality score and change nothing in it.</p></div>" + DISCLAIMER)
    d = os.path.join(site, "disclosures", "analysis-traps")
    os.makedirs(d, exist_ok=True)
    ld = {"@context": "https://schema.org", "@graph": [{"@type": "WebPage", "name": "Analysis traps: where the figures could mislead you", "url": url, "description": lead[:300]}]}
    open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(seo.page("Analysis Traps: Six Ways a Company's Figures Mislead, Checked on Every Filing", lead[:300], url, body, 2, base + "/og.png", ld))
    return url


RULE_BLURB = {
    "A01": "Free cash flow rose, but working capital released cash or capital expenditure fell: the part of the increase that need not repeat next year.",
    "A07": "Stock compensation is a real cost paid in shares; 'adjusted' figures that add it back only hold up when buybacks have paid for the dilution.",
    "B02": "Receivables growing faster than revenue for two quarters, with days sales outstanding above its own history: more of each sale is still owed.",
    "B08": "Adjusted EPS at least 10% above GAAP quarter after quarter: the excluded costs are a recurring cost of the business.",
    "C02": "Debt due within a year exceeds cash and investments plus the last twelve months' free cash flow: a low net debt says nothing about when it falls due.",
    "D03": "EPS rose while net income was flat or down and the share count fell: the growth is the smaller denominator.",
    "E02": "A low P/E on this year's profit when that profit is at a high against the last eight years: the multiple on mid-cycle profit is what matters.",
    "E07": "A DCF's point value against the terminal value's weight and the swing from each input: a range, not a number (always 'to review').",
    "J06": "A bank at a low P/E on its best year of the last eight: provisions, deposit costs and capital turn the cycle, not the multiple.",
    "J08": "A REIT paying more in dividends than its net income is normal; paying more than its operating cash flow is the question.",
}


def write(site, base, today=None):
    base = base.rstrip("/")
    today = today or dt.date.today()
    ix = read(os.path.join(site, "data", "index.json")) or {}
    rows = [r for r in ((ix.get("companies") if isinstance(ix, dict) else ix) or []) if r.get("cik")]
    latest = {}
    for r in rows:
        if int(r["cik"]) not in latest or (r.get("filed") or "") > (latest[int(r["cik"])].get("filed") or ""):
            latest[int(r["cik"])] = r
    out_dir = os.path.join(site, "data", "traps")
    os.makedirs(out_dir, exist_ok=True)
    docs, slugs, urls, index_rows = {}, {}, [], []
    for cik, r in latest.items():
        c = read(os.path.join(site, "data", "c", f"{cik}.json"))
        if not c or not c.get("quarters"):
            continue
        t = r.get("ticker") or ""
        er = read(os.path.join(site, "disclosures", "data", "research", "earnings", "c", f"{t.replace('.', '-')}.json")) if t else None
        val = read(os.path.join(site, "disclosures", "data", "research", "valuation", "c", f"{cik}.json"))
        try:
            doc = T.evaluate(c, er, today, val)
        except Exception as err:  # noqa: BLE001
            print(f"traps skipped ({t or cik}): {err}")
            continue
        doc["ticker"], doc["name"] = t, display_name(r.get("name"))
        with open(os.path.join(out_dir, f"{cik}.json"), "w", encoding="utf-8") as f:
            json.dump(doc, f, separators=(",", ":"))
        docs[cik] = doc
        trig = [f["rule_id"] for f in doc["findings"] if f["status"] == "triggered"]
        top = max((f["severity"] for f in doc["findings"] if f["status"] == "triggered"), key=lambda s: T.SEV[s], default=None)
        index_rows.append([t, cik, doc["name"], r.get("sector"), doc["as_of"], trig, top, doc["priority"], doc["summary"]["insufficient_data"]])
        slug = seo.slug_for(r)
        if not os.path.exists(os.path.join(site, "c", slug, "index.html")):
            continue
        slugs[cik] = slug
        try:
            url, html = page_for(doc, r, slug, base)
        except Exception as err:  # noqa: BLE001
            print(f"traps page skipped ({t}): {err}")
            continue
        d = os.path.join(site, "c", slug, "analysis-traps")
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(html)
        card_on_company_page(site, slug, doc)
        urls.append((url, doc["filed"]))
    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"generated_at": today.isoformat(), "rule_version": T.RULE_VERSION, "rules": {k: {"name": v[0], "area": v[1], "blurb": RULE_BLURB[k]} for k, v in T.NAMES.items()},
                   "fields": ["ticker", "cik", "name", "sector", "as_of", "triggered", "top_severity", "priority", "insufficient"], "rows": index_rows}, f, separators=(",", ":"))
    if docs:
        urls.insert(0, (hub_page(site, base, docs, rows, slugs), today.isoformat()))
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f"<url><loc>{xesc(u)}</loc>" + (f"<lastmod>{xesc(str(m)[:10])}</lastmod>" if m else "") + "</url>" for u, m in urls]
    sm.append("</urlset>")
    open(os.path.join(site, "sitemap-traps.xml"), "w", encoding="utf-8").write("\n".join(sm))
    robots = os.path.join(site, "robots.txt")
    txt = open(robots).read() if os.path.exists(robots) else f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n"
    if "sitemap-traps.xml" not in txt:
        open(robots, "w").write(txt.rstrip("\n") + f"\nSitemap: {base}/sitemap-traps.xml\n")
    trig_n = sum(1 for d in docs.values() if d["summary"]["triggered"])
    print(f"analysis traps: {len(docs)} companies evaluated, {len(urls) - 1} pages, {trig_n} with a triggered rule")
    return len(docs)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="_site")
    ap.add_argument("--site-url", default=os.environ.get("SITE_URL") or "https://filing-flows.com")
    a = ap.parse_args()
    if (os.environ.get("TRAPS") or "").lower() == "off":
        print("analysis traps: TRAPS=off, skipped")
    else:
        write(a.site, a.site_url)
