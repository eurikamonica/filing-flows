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
import re
import os
import sys
from xml.sax.saxutils import escape as xesc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import seo  # noqa: E402
from pipeline import traps as T  # noqa: E402
from pipeline import trap_cases as TC  # noqa: E402
fin = T.fin

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


def finding_html(f, name, doc=None):
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
    c = chart_contract(f, doc) if doc else None
    if c:
        body += f"<script type='application/json' class='trap-chart'>{json.dumps(c, separators=(',', ':')).replace('</', '<\\/')}</script>"
    if st in ("triggered", "review"):
        if f.get("alternative_explanations"):
            body += "<p><b>What would explain it innocently</b></p><ul class='seo-list'>" + "".join(f"<li>{e(x)}</li>" for x in f["alternative_explanations"]) + "</ul>"
        if f.get("missing_evidence"):
            body += "<p><b>What to look for in the filing</b></p><ul class='seo-list'>" + "".join(f"<li>{e(x)}</li>" for x in f["missing_evidence"]) + "</ul>"
        if f.get("falsified_if"):
            body += "<p><b>What would show the trap does not apply</b></p><ul class='seo-list'>" + "".join(f"<li>{e(x)}</li>" for x in f["falsified_if"]) + "</ul>"
        body += f"<p class='muted'>Look again: {e(f.get('next_review', 'next filing').replace('_', ' '))}.</p>"
    return head + body


def page_for(doc, r, slug, base, has_cf=True, has_eq=True):
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
    every = "<h2 id='all'>Every rule</h2>" + "".join(finding_html(f, name, doc) for f in doc["findings"])
    body = (f"<p class='crumbs'><a href='../../../'>Filing Flows</a> › <a href='../../'>Companies</a> › <a href='../'>{e(name)}</a> › Analysis traps</p>"
            f"<h1>{e(name)} ({e(t)}): analysis traps</h1><p class='muted'>Where its figures could mislead a reader, and what to check before taking them at face value · "
            f"Data: {e(r.get('label') or 'latest quarter')}, to {e(fdate(doc['as_of']))}, filed {e(fdate(doc['filed']))}; rules v{e(doc['rule_version'])}</p>"
            f"<p class='lead'>{e(lead)}</p>{top}{every}"
            "<h2 id='statuses'>What the statuses mean</h2><div class='seo-note'><p><b>Triggered</b>: the filings show the pattern; read the normal explanations and the missing evidence before concluding anything. "
            "<b>To review</b>: one quarter or a weak signal; a reader's judgement, not a pattern. <b>Not triggered</b>: the pattern is absent on these figures. <b>Insufficient data</b>: the filings read so far do not hold what the rule needs; "
            "this is not a clean bill. <b>Not applicable</b>: the rule is not meant for this kind of company (a bank's working capital, a loss-making quarter's EPS growth). <b>Out of date</b>: the latest filing is more than fifteen months old.</p>"
            "<p>Severity is what the pattern could mean for cash, value or solvency; confidence is how reliable the inputs and the reading are. The two are kept apart.</p></div>"
            f"<h2 id='note'>Record a view</h2><div id='trap-note' data-key='{e(str(doc.get('cik')))}'><p class='muted'>A reader's judgement, grounds, what would change it and the next review; kept in the browser (needs JavaScript).</p></div>"
            f"<p><a class='seo-cta' href='../../../disclosures/analysis-traps/'>Every rule and the companies it triggers on →</a>"
            + (f" <a href='../cash-flow/'>{e(name)}: cash flow →</a>" if has_cf else "")   # only to sibling pages that were written
            + (" <a href='../earnings-quality/'>Earnings quality score →</a>" if has_eq else "") + "</p>"
            + DISCLAIMER + "<script src='../../../trap-charts.js' defer></script>")
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
        lib = TC.by_rule().get(k) or {"cases": [], "papers": []}
        secs += (f"<h2 id='{k}'>{e(k)} · {e(nm)} <span class='muted'>{len(hits)} of {n}</span></h2>"
                 + (f"<p>{e(RULE_BLURB[k])}" + (f" <span class='muted'>Cases: {', '.join(f'<a href=cases/#{e(c)}>{e(c)}</a>' for c in lib['cases'])}" if lib["cases"] else "")
                    + (f"{' ·' if lib['cases'] else ' <span class=muted>'}Papers: {', '.join(f'<a href=cases/#papers>{e(p)}</a>' for p in lib['papers'])}" if lib["papers"] else "") + ("</span>" if lib["cases"] or lib["papers"] else "") + "</p>")
                 + (f"<ul class='seo-list'>" + "".join(f"<li>{L(cik)} <span class='muted'>{e(f['severity'])} · {e(f['explanation'].split('. ')[0])}.</span></li>" for cik, f in hits[:40]) + "</ul>" if hits else "<p class='muted'>No company triggers it on the latest filings.</p>"))
    ch = (read(os.path.join(site, "data", "traps", "changes.json")) or {}).get("changes") or []
    if ch:
        secs += ("<h2 id='changes'>What a newer filing changed <span class='muted'>last " + str(KEEP_DAYS) + " days</span></h2>"
                 "<p>Each rule is re-run when a company files; a trap that appears, goes, or changes severity between two filings is listed here (a rule changed on this site is not).</p><ul class='seo-list'>"
                 + "".join(f"<li>{e(c['date'])} · <a href='{e(c['url'])}'><b>{e(c['ticker'])}</b></a> {e(c['rule'])} {e(lower(c['rule_name']))}: <b>{e(CHANGE_WORD[c['kind']])}</b>"
                           + (f" ({e(c.get('from_severity') or '')} → {e(c.get('severity') or '')})" if c["kind"] == "severity" else "") + f" on the filing to {e(c.get('as_of') or '')} (was {e(c.get('prev_as_of') or '')})"
                           + (f" <span class='trap-st rev'>rules changed too: v{e(c.get('prev_rule_version') or '?')} → v{e(c.get('rule_version') or '')}</span>" if c.get("method_changed") else "")
                           + (f" <span class='muted'>{e(c['explanation'].split('. ')[0])}.</span>" if c.get("explanation") else "") + "</li>" for c in ch[:40]) + "</ul>")
    counts = {k: len(by_rule[k]) for k in T.NAMES}
    lead = (f"{seo.n_of(len(T.NAMES), 'rule')} on {seo.n_of(n, 'company', 'companies')}' filings, each a common misreading of a figure: "
            + ", ".join(f"{lower(T.NAMES[k][0])} ({counts[k]})" for k in T.NAMES) + ". A triggered rule is a question to verify, with the normal explanation that would produce the same figures.")
    url = f"{base}/disclosures/analysis-traps/"
    body = (f"<p class='crumbs'><a href='../../'>Filing Flows</a> › <a href='../'>Disclosures</a> › Analysis traps</p><h1>Analysis traps: where the figures could mislead you</h1>"
            f"<p class='lead'>{e(lead)}</p><nav class='seo-toc'>" + "".join(f"<a href='#{k}'>{k}</a>" for k in T.NAMES) + ("<a href='#changes'>Changes</a>" if ch else "") + "</nav>" + secs
            + "<h2 id='cases'>Cases and papers</h2><p><a href='cases/'>The public cases and the papers behind the rules →</a> the mechanism, the misreading, what to check and the normal explanation, as the cited material states them.</p>"
            + "<h2 id='practice'>Practice</h2><p><a href='practice/'>Practice on real filings →</a> the figures first, then a reader's conclusion, then your call; the answer comes with the innocent explanations and what would show the trap does not apply.</p>"
            + "<h2 id='method'>Method</h2><div class='seo-note'><p>Ten rules of a hundred-item catalogue (docs/TRAP_RULEBOOK.md in the repository), chosen because the site already holds every figure they need: "
              "the cash bridge, capex, stock compensation and share counts, receivables, debt maturities, adjusted against GAAP EPS. Each reads the company's own filings by a fixed formula with coarse, "
              "documented thresholds and carries its figures, so a reader can apply stricter ones. Statuses: triggered, to review, not triggered, insufficient data, not applicable, out of date; "
              "missing data is never shown as clear. Severity and confidence are kept apart. The rules are independent of the earnings quality score and change nothing in it.</p></div>" + DISCLAIMER)
    d = os.path.join(site, "disclosures", "analysis-traps")
    os.makedirs(d, exist_ok=True)
    ld = {"@context": "https://schema.org", "@graph": [{"@type": "WebPage", "name": "Analysis traps: where the figures could mislead you", "url": url, "description": lead[:300]}]}
    open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(seo.page("Analysis Traps: Ten Ways a Company's Figures Mislead, Checked on Every Filing", lead[:300], url, body, 2, base + "/og.png", ld))
    return url


# ---------------------------------------------------------------- chart data contracts (docs/TRAP_RESEARCH_VOL2.md §37)
NOT_SUPPORTED = ["that the business improved or worsened", "manipulation or fraud", "the direction of the stock"]


def chart_contract(f, doc):
    """the data behind a finding's chart: G01 for A01 (the FCF bridge), G04 for C02 (the cash margin); None otherwise.
    Every value is observed from the filings (data_kind observed); the page's script turns the reader's inputs into a
    scenario and labels it so. Missing parts are declared in `coverage`, never drawn as zero."""
    o = f.get("observed") or {}
    src = [{"period": x.get("period"), "url": x.get("url"), "what": x.get("what")} for x in (f.get("evidence") or [])]
    base = {"chart_version": "1.0", "rule_id": f["rule_id"], "entity_id": str(doc.get("cik") or ""), "data_kind": "observed", "unit": "USD", "currency": "USD",
            "entity_scope": "consolidated", "source_snapshot": doc.get("filed"), "evidence_cutoff": doc.get("filed"), "sources": src, "rule_version": doc.get("rule_version"),
            "not_supported_claims": NOT_SUPPORTED}
    if f["rule_id"] == "A01" and fin(o.get("fcf_prior")) and fin(o.get("fcf_current")):
        vals = [{"name": "prior_fcf", "value": o["fcf_prior"]}, {"name": "current_fcf", "value": o["fcf_current"]}, {"name": "capex_reduction", "value": -(o.get("delta_capex") or 0)}]
        if fin(o.get("delta_wc_cash")):
            vals.append({"name": "wc_cash_change", "value": o["delta_wc_cash"]})
        return dict(base, chart_id="fcf_bridge", question="Where did the free cash flow increase come from?", period_basis=f"fiscal years {o.get('fy_prior')} to {o.get('fy_current')}",
                    coverage="complete" if fin(o.get("delta_wc_cash")) else "partial: working capital not in the data", values=vals,
                    assumptions=["FCF = operating cash flow − cash capex; the parts are the change in capex and the change in the cash-bridge working-capital items; the rest is 'other', not an improvement"])
    if f["rule_id"] == "C02" and fin(o.get("cash")) and fin(o.get("due_12m")):
        return dict(base, chart_id="liquidity_matrix", question="Can the cash reach the debt due within a year?", period_basis=f"as of {o.get('as_of') or doc.get('as_of')}; FCF over the last twelve months",
                    coverage="partial: no credit facility and no due dates inside the year in the data" + ("; FCF not in the data" if not fin(o.get("fcf_ttm")) else ""),
                    values=[{"name": "cash", "value": o["cash"]}, {"name": "due_12m", "value": o["due_12m"]}, {"name": "fcf_ttm", "value": o.get("fcf_ttm")}, {"name": "debt", "value": o.get("debt")}],
                    assumptions=["A facility counts only when the reader marks it drawable", "Negative FCF counts as zero inflow", "The minimum operating cash is the reader's input (0 by default)"])
    return None


# ---------------------------------------------------------------- evidence changes: a new filing makes a trap appear or go
CHANGE_WORD = {"new": "newly triggered", "released": "no longer triggered", "severity": "severity changed", "review": "now to review", "lapsed": "no longer checkable"}
KEEP_DAYS, FEED_MAX = 180, 20


def state_of(doc):
    return {"as_of": doc.get("as_of"), "filed": doc.get("filed"), "f": {f["rule_id"]: [f["status"], f.get("severity")] for f in doc["findings"]}}


def diff(prev, doc, today, prev_version=None):
    """the changes between a company's previous findings and today's, only when a newer filing is behind them (a rule
    upgrade that flips a status without a new filing is not an evidence change)"""
    out = []
    if not prev or not doc.get("filed") or (prev.get("filed") or "") >= doc["filed"]:
        return out
    old = prev.get("f") or {}
    for f in doc["findings"]:
        was = old.get(f["rule_id"])
        if not was:
            continue
        st0, sv0 = was[0], was[1]
        st1, sv1 = f["status"], f.get("severity")
        kind = None
        if st1 == "triggered" and st0 != "triggered":
            kind = "new"
        elif st0 == "triggered" and st1 in ("clear", "review"):
            kind = "released"
        elif st0 == "triggered" and st1 in ("insufficient_data", "not_applicable", "expired"):
            kind = "lapsed"
        elif st0 == st1 == "triggered" and sv0 != sv1:
            kind = "severity"
        elif st1 == "review" and st0 == "clear":
            kind = "review"
        if not kind:
            continue
        ev = next((x.get("url") for x in (f.get("evidence") or []) if x.get("url")), None) or doc.get("doc_url")
        out.append({"date": today.isoformat(), "cik": doc["cik"], "ticker": doc.get("ticker") or "", "name": doc.get("name") or "", "rule": f["rule_id"], "rule_name": f["name"],
                    "kind": kind, "from": st0, "to": st1, "severity": sv1, "from_severity": sv0, "as_of": doc.get("as_of"), "prev_as_of": prev.get("as_of"), "filed": doc["filed"],
                    "explanation": (f.get("explanation") or f.get("reason") or "")[:240], "doc_url": ev,
                    "method_changed": bool(prev_version and prev_version != T.RULE_VERSION), "rule_version": T.RULE_VERSION, "prev_rule_version": prev_version})
    return out


def track_changes(site, store, docs, slugs, base, today):
    """store/traps-state.json (last findings per company) and store/traps-changes.json (the log) in the data store;
    data/traps/changes.json on the site, and up to FEED_MAX trap events in Flo's alert feed"""
    state = read(os.path.join(store, "traps-state.json")) if store else None
    prev = (state or {}).get("companies") or {}
    log = (read(os.path.join(store, "traps-changes.json")) if store else None) or {}
    changes = [c for c in (log.get("changes") or []) if (c.get("date") or "") >= (today - dt.timedelta(days=KEEP_DAYS)).isoformat()]
    seen = {(c["cik"], c["rule"], c.get("as_of"), c["kind"]) for c in changes}
    fresh = []
    for cik, doc in docs.items():
        for c in diff(prev.get(str(cik)), doc, today, (state or {}).get("rule_version")):
            if (c["cik"], c["rule"], c.get("as_of"), c["kind"]) in seen:
                continue
            c["url"] = f"{base}/c/{slugs[cik]}/analysis-traps/#{c['rule']}" if cik in slugs else f"{base}/#traps/{c['ticker']}"
            fresh.append(c)
    changes = sorted(fresh + changes, key=lambda c: (c["date"], c.get("filed") or ""), reverse=True)[:2000]
    if store:
        os.makedirs(store, exist_ok=True)
        with open(os.path.join(store, "traps-state.json"), "w", encoding="utf-8") as f:
            json.dump({"generated_at": today.isoformat(), "rule_version": T.RULE_VERSION, "companies": {str(cik): state_of(d) for cik, d in docs.items()}}, f, separators=(",", ":"))
        with open(os.path.join(store, "traps-changes.json"), "w", encoding="utf-8") as f:
            json.dump({"generated_at": today.isoformat(), "changes": changes}, f, separators=(",", ":"))
    with open(os.path.join(site, "data", "traps", "changes.json"), "w", encoding="utf-8") as f:
        json.dump({"generated_at": today.isoformat(), "first_run": not prev, "n": len(changes), "changes": changes[:400]}, f, separators=(",", ":"))
    flo_feed(site, [c for c in changes if c["date"] >= (today - dt.timedelta(days=3)).isoformat()], today)
    print(f"analysis traps: {len(fresh)} evidence changes today ({len(changes)} in the last {KEEP_DAYS} days)" + ("; first run, state saved" if not prev else ""))
    return fresh


def flo_feed(site, fresh, today):
    """trap events into disclosures/data/market/flo-alerts.json (built earlier in the run by scripts/build_flo_alerts.py,
    without them): the last three days' changes, since the feed is rebuilt every run and the pulse shows 72 hours. The
    feed takes only SEC-cited events, so a change is added only with the filing it rests on"""
    p = os.path.join(site, "disclosures", "data", "market", "flo-alerts.json")
    feed = read(p)
    if not feed or feed.get("schema") != 1 or not isinstance(feed.get("events"), list):
        return 0
    rank = {"new": 0, "severity": 1, "released": 2, "review": 3, "lapsed": 4}
    pick = sorted([c for c in fresh if c.get("doc_url") and c["ticker"] and re.fullmatch(r"https://(www\.)?sec\.gov/Archives/.*", c["doc_url"])],
                  key=lambda c: (rank[c["kind"]], {"high": 0, "medium": 1, "low": 2}.get(c.get("severity"), 3)))[:FEED_MAX]
    events = [e for e in feed["events"] if (e or {}).get("kind") != "trap"]
    for c in pick:
        at = f"{c['date']}T00:00:00Z"
        pr = "high" if c["kind"] in ("new", "severity") and c.get("severity") == "high" else "medium" if c["kind"] in ("new", "severity") else "info"
        events.append({"id": f"trap:{c['cik']}:{c['rule']}:{c.get('as_of')}:{c['kind']}", "kind": "trap", "ticker": c["ticker"], "priority": pr,
                       "title": f"{c['ticker']} {c['rule']} {c['rule_name']}: {CHANGE_WORD[c['kind']]}" + (f" ({c.get('from_severity')} → {c.get('severity')})" if c["kind"] == "severity" else ""),
                       "detail": c["explanation"][:180], "event_at": at, "filed": c["filed"], "rule": c["rule"], "change": c["kind"], "status": c["to"], "was": c["from"],
                       "severity": c.get("severity"), "as_of": c.get("as_of"), "page": c.get("url"), "source_url": c["doc_url"], "source_label": "SEC filing · Filing Flows analysis traps",
                       "scope": "A rule re-run on a newer filing; a question to verify, not a verdict."})
    feed["events"] = events[:300]
    with open(p, "w", encoding="utf-8") as f:
        json.dump(feed, f, separators=(",", ":"))
    return len(pick)


# ---------------------------------------------------------------- the teaching library: papers and public cases by rule
def cases_page(site, base):
    """disclosures/analysis-traps/cases/: the public cases and the papers behind the rules, as the cited material states them"""
    url = f"{base}/disclosures/analysis-traps/cases/"
    link_rules = lambda rs: ", ".join(f"<a href='../#{e(r)}'>{e(r)} {e(lower(T.NAMES[r][0]))}</a>" for r in rs if r in T.NAMES) or "<span class='muted'>method, not one rule</span>"
    cards = "".join(
        f"<div class='trap-card' id='{e(c[0])}'><h3>{e(c[0])} · {e(c[1])} <span class='muted'>{e(c[2])}</span></h3>"
        f"<p><b>What the material describes</b>: {e(c[4])} <a href='{e(c[3])}' rel='nofollow'>Primary source →</a></p>"
        f"<p><b>The misreading it illustrates</b>: {e(c[5])}</p><p><b>What to check</b>: {e(c[6])}</p>"
        + (f"<p><b>The normal explanation</b>: {e(c[7])}</p>" if c[7] and c[7] != "—" else "")
        + f"<p class='muted'>Rules: {link_rules(c[8])}</p></div>" for c in TC.CASES)
    papers = "<div class='tbl-wrap'><table><thead><tr><th>Paper</th><th>Finding</th><th>Limit for this site</th><th>Rules</th></tr></thead><tbody>" + "".join(
        f"<tr><td><b>{e(p[0])}</b> {e(p[1])}<br><a href='{e(p[3])}' rel='nofollow'>{e(p[2])}</a></td><td>{e(p[4])}</td><td>{e(p[5])}</td><td>{link_rules(p[6])}</td></tr>" for p in TC.PAPERS) + "</tbody></table></div>"
    lead = (f"{len(TC.CASES)} public cases (SEC complaints and orders, FINMA, FCA, FRC, Federal Reserve and Bank of England reviews, one 10-K contrast) and {len(TC.PAPERS)} papers, "
            "each tied to the rules it illustrates: the mechanism, the misreading, what to check and the normal explanation. The facts are stated as the cited material states them at its date; "
            "an allegation stays an allegation, a settlement a settlement. No case is a verdict on any company the rules run on today.")
    body = (f"<p class='crumbs'><a href='../../../'>Filing Flows</a> › <a href='../../'>Disclosures</a> › <a href='../'>Analysis traps</a> › Cases and papers</p>"
            f"<h1>Analysis traps: the cases and the papers behind the rules</h1><p class='lead'>{e(lead)}</p><p class='muted'>{e(TC.RULE_NOTE)}</p>"
            "<nav class='seo-toc'><a href='#cases'>Cases</a><a href='#papers'>Papers</a><a href='#limits'>Limits</a></nav>"
            f"<h2 id='cases'>Cases</h2>{cards}<h2 id='papers'>Papers</h2>{papers}"
            "<h2 id='limits'>Three limits on reading the cases</h2><div class='seo-note'><p>This is a library of mechanisms: a company that resembles a historical case is not thereby the next one, and the site never says so. "
            "The internal evidence in enforcement cases (emails, customer records, bank statements) was usually not public at the time; what was visible beforehand and what came out afterwards are kept apart, or the library would fake foresight. "
            "Enforcement samples are the cases that were found, investigated and within a jurisdiction; a company with no case is not a clean negative.</p></div>" + DISCLAIMER)
    d = os.path.join(site, "disclosures", "analysis-traps", "cases")
    os.makedirs(d, exist_ok=True)
    ld = {"@context": "https://schema.org", "@graph": [{"@type": "WebPage", "name": "Analysis traps: the cases and the papers behind the rules", "url": url, "description": lead[:300]}]}
    open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(seo.page("Analysis Traps: 34 Public Cases and 27 Papers Behind the Rules", lead[:300], url, body, 3, base + "/og.png", ld))
    return url


# ---------------------------------------------------------------- practice mode: the figures first, the reading second
CLAIM = {"A01": "Free cash flow rose, so the business improved.", "A07": "Adjusted profit adds stock compensation back, and rightly: it costs no cash.",
         "B02": "Receivables are growing with sales; the cash will follow.", "B08": "Adjusted EPS is the right measure of profit: the excluded items are one-offs.",
         "C02": "Net debt is low, so refinancing is no concern.", "D03": "EPS is growing, so profit is growing.", "E02": "The P/E is low, so the stock is cheap.",
         "E07": "The DCF's value is the stock's fair value.", "J06": "A record profit at a low P/E: the bank is cheap.", "J08": "The REIT's dividend is well covered."}
ANSWER = {"triggered": "trap", "review": "trap", "clear": "holds", "insufficient_data": "unknown"}
PRACTICE_MAX = {"trap": 60, "holds": 40, "unknown": 12}


def practice_items(docs, rows, slugs, base):
    """quiz items from real findings: the figures, the naive claim, the answer (the trap applies / the figures hold up /
    cannot tell), the explanation and the counter-evidence; round-robin over the rules, largest companies first"""
    rev = {int(r["cik"]): r.get("revenue") or 0 for r in rows}
    pools = {k: [] for k in T.NAMES}
    for cik, d in sorted(docs.items(), key=lambda kv: -rev.get(kv[0], 0)):
        for f in d["findings"]:
            a = ANSWER.get(f["status"])
            if not a or not f.get("observed") or (a == "holds" and f.get("confidence") == "low"):
                continue
            figs = [[LABEL.get(k, k.replace("_", " ")), fmt_obs(k, v)] for k, v in list(f["observed"].items())[:9]]
            pools[f["rule_id"]].append({"id": f"{cik}-{f['rule_id']}", "ticker": d.get("ticker") or "", "name": d.get("name") or "", "rule": f["rule_id"], "trap": f["name"],
                                        "claim": CLAIM[f["rule_id"]], "as_of": d.get("as_of"), "figures": figs, "answer": a, "severity": f.get("severity"),
                                        "explanation": f.get("explanation") or f.get("reason") or "", "alternatives": (f.get("alternative_explanations") or [])[:3],
                                        "falsified_if": (f.get("falsified_if") or [])[:3], "how": f.get("how") or "",
                                        "url": f"{base}/c/{slugs[cik]}/analysis-traps/#{f['rule_id']}" if cik in slugs else f"{base}/#traps/{d.get('ticker') or ''}"})
    out, count = [], {"trap": 0, "holds": 0, "unknown": 0}
    for i in range(80):
        for k in T.NAMES:
            if i < len(pools[k]) and count[pools[k][i]["answer"]] < PRACTICE_MAX[pools[k][i]["answer"]]:
                out.append(pools[k][i]); count[pools[k][i]["answer"]] += 1
    return out


PRACTICE_JS = r"""
(function(){
var E=function(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})};
var root=document.getElementById('practice'),items=[],order=[],i=0,score={right:0,done:0},rule='',KEY='ff:traps-practice:v1';
var WORD={trap:'Not necessarily: the figures fit the trap',holds:'The figures hold up under this rule',unknown:'Cannot tell from these figures'};
function load(){try{var d=JSON.parse(localStorage.getItem(KEY)||'null');if(d&&d.score)score=d.score}catch(e){}}
function save(){try{localStorage.setItem(KEY,JSON.stringify({score:score}))}catch(e){}}
function shuffle(a){for(var j=a.length-1;j>0;j--){var k=Math.floor(Math.random()*(j+1)),t=a[j];a[j]=a[k];a[k]=t}return a}
function start(){var pool=items.filter(function(x){return !rule||x.rule===rule});order=shuffle(pool.slice());i=0;show()}
function show(){
 if(!order.length){root.innerHTML='<p class="muted">No item for this rule yet.</p>';return}
 var x=order[i%order.length];
 root.innerHTML='<div class="trap-card"><p class="muted">'+E(x.rule)+' · '+E(x.trap)+' · item '+(i+1)+' of '+order.length+(score.done?' · '+score.right+' / '+score.done+' right so far':'')+'</p>'
 +'<p><b>'+E(x.ticker)+'</b> '+E(x.name)+', filings to '+E(x.as_of)+'. The figures:</p><div class="tbl-wrap"><table><tbody>'+x.figures.map(function(r){return'<tr><td>'+E(r[0])+'</td><td class="num">'+E(r[1])+'</td></tr>'}).join('')+'</tbody></table></div>'
 +'<p class="muted">'+E(x.how)+'</p><p>A reader concludes: <b>“'+E(x.claim)+'”</b> Does it follow?</p><p class="pr-btns">'
 +['holds','trap','unknown'].map(function(a){return'<button class="btn" data-a="'+a+'">'+E(WORD[a])+'</button>'}).join(' ')+'</p><div id="pr-reveal"></div></div>';
 Array.prototype.forEach.call(root.querySelectorAll('button[data-a]'),function(b){b.onclick=function(){answer(x,b.getAttribute('data-a'))}});
}
function answer(x,a){
 var ok=a===x.answer;score.done++;if(ok)score.right++;save();
 var r=document.getElementById('pr-reveal');
 r.innerHTML='<p><b>'+(ok?'Right.':'Not this time.')+'</b> '+E(WORD[x.answer])+(x.severity?' (severity '+E(x.severity)+')':'')+'.</p><p>'+E(x.explanation)+'</p>'
 +(x.alternatives.length?'<p><b>What would explain it innocently</b></p><ul class="seo-list">'+x.alternatives.map(function(t){return'<li>'+E(t)+'</li>'}).join('')+'</ul>':'')
 +(x.falsified_if.length?'<p><b>What would show the trap does not apply</b></p><ul class="seo-list">'+x.falsified_if.map(function(t){return'<li>'+E(t)+'</li>'}).join('')+'</ul>':'')
 +'<p><a href="'+E(x.url)+'">The company\'s analysis-traps page →</a> · <button class="btn" id="pr-next">Next</button></p>';
 Array.prototype.forEach.call(root.querySelectorAll('button[data-a]'),function(b){b.disabled=true;if(b.getAttribute('data-a')===x.answer)b.classList.add('pr-ok')});
 document.getElementById('pr-next').onclick=function(){i++;show()};
}
load();
fetch('../../../data/traps/practice.json',{cache:'no-cache'}).then(function(r){return r.json()}).then(function(d){
 items=d.items||[];var sel=document.getElementById('pr-rule');
 Object.keys(d.rules||{}).forEach(function(k){var o=document.createElement('option');o.value=k;o.textContent=k+' · '+d.rules[k];sel.appendChild(o)});
 sel.onchange=function(){rule=sel.value;start()};
 document.getElementById('pr-reset').onclick=function(){score={right:0,done:0};save();start()};
 start();
}).catch(function(){root.innerHTML='<p class="muted">The practice set could not be read.</p>'});
})();
"""


def practice_page(site, base, items):
    """disclosures/analysis-traps/practice/: one real finding at a time, the figures before the reading"""
    url = f"{base}/disclosures/analysis-traps/practice/"
    n_rules = len({x["rule"] for x in items})
    lead = (f"{len(items)} real findings from the latest filings, {n_rules} rules: the figures first, then a reader's conclusion, then your call: do the figures hold up, do they fit a trap, "
            "or can they not say? The answer comes with the innocent explanations and what would show the trap does not apply. No fabricated numbers; not investment advice.")
    body = (f"<p class='crumbs'><a href='../../../'>Filing Flows</a> › <a href='../../'>Disclosures</a> › <a href='../'>Analysis traps</a> › Practice</p>"
            f"<h1>Analysis traps: practice on real filings</h1><p class='lead'>{e(lead)}</p>"
            "<p><label>Rule <select id='pr-rule'><option value=''>All rules</option></select></label> · <button class='btn' id='pr-reset'>Reset the score</button></p>"
            "<div id='practice'><p class='muted'>Reading the practice set…</p></div>"
            "<h2>How the practice set is built</h2><div class='seo-note'><p>Every item is a finding of the same rules that run on every company (data/traps/&lt;cik&gt;.json), shown with its figures: "
            "triggered and to-review findings answer “the figures fit the trap”, findings the rule cleared with at least medium confidence answer “the figures hold up”, "
            "and findings with insufficient data answer “cannot tell” (missing data is never shown as clear). The set is drawn round-robin over the rules, largest companies first, and rebuilt with the site.</p></div>"
            + DISCLAIMER + f"<script>{PRACTICE_JS}</script>")
    d = os.path.join(site, "disclosures", "analysis-traps", "practice")
    os.makedirs(d, exist_ok=True)
    ld = {"@context": "https://schema.org", "@graph": [{"@type": "WebPage", "name": "Analysis traps: practice on real filings", "url": url, "description": lead[:300]}]}
    open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(seo.page("Analysis Traps Practice: Read the Figures, Then Decide", lead[:300], url, body, 3, base + "/og.png", ld))
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


def write(site, base, today=None, store=None):
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
    js = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "trap-charts.js")
    if os.path.exists(js):
        import shutil
        shutil.copy(js, os.path.join(site, "trap-charts.js"))
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
            url, html = page_for(doc, r, slug, base, os.path.exists(os.path.join(site, "c", slug, "cash-flow", "index.html")),
                                 os.path.exists(os.path.join(site, "c", slug, "earnings-quality", "index.html")))
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
        track_changes(site, store, docs, slugs, base, today)
        items = practice_items(docs, rows, slugs, base)
        with open(os.path.join(out_dir, "practice.json"), "w", encoding="utf-8") as f:
            json.dump({"generated_at": today.isoformat(), "rule_version": T.RULE_VERSION, "rules": {k: v[0] for k, v in T.NAMES.items()}, "items": items}, f, separators=(",", ":"))
        urls.insert(0, (practice_page(site, base, items), today.isoformat()))
        urls.insert(0, (cases_page(site, base), today.isoformat()))
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
    ap.add_argument("--store", default=None, help="the data store (branch data): previous findings, the change log")
    a = ap.parse_args()
    if (os.environ.get("TRAPS") or "").lower() == "off":
        print("analysis traps: TRAPS=off, skipped")
    else:
        write(a.site, a.site_url, store=a.store)
