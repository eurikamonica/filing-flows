"""Analysis traps: "why this number may mislead you", as questions a reader can verify (docs/TRAP_RULEBOOK.md).

A trap is a common misreading of a figure the site already shows (free cash flow up = the business improved, EPS up =
profit up, low net debt = no refinancing risk …). Each rule looks at the company's own filings and says what it observed,
why it is worth checking, what normal explanation would produce the same figures, what evidence is missing, and when to
look again. A finding is never a verdict: a triggered rule is a question, not a conclusion of manipulation, and it does
not translate into a buy or sell view or a price forecast.

Statuses: triggered | clear | insufficient_data | not_applicable | review (a rule that needs a reader's judgement) |
expired (the latest filing is more than 15 months old). Missing data never shows as clear. Severity (what it could mean
for cash, value or solvency) and confidence (how reliable the inputs and the reading are) are separate.

Rules live in RULES, versioned; each returns a Finding. The first six (the rulebook's phase P1):
  A01  FCF growth = the business improved        the change in free cash flow split into working capital, capex, the rest
  A07  SBC added back = no economic cost         stock compensation against revenue, dilution and the buybacks offsetting it
  B02  receivables growing = future cash certain receivables and DSO against revenue, over the last quarters
  B08  adjusted profit = economic profit         adjusted (street) EPS above GAAP quarter after quarter
  C02  low net debt = no refinancing risk        debt due within a year against cash and conservative cash flow
  D03  EPS growth = profit growth                EPS up while net income is flat and the share count fell

Inputs are the published company file (data/c/<cik>.json: quality.q / fy / val / cap, drivers) and the earnings research
file (research/earnings/c/<T>.json: adjusted vs GAAP EPS). Thresholds below are starting points, documented in the
rulebook; they are deliberately coarse, and every finding carries the figures so a reader can apply their own.

    from pipeline import traps
    doc = traps.evaluate(company_json, earnings_json, today=date)
"""
import datetime as dt
import re

RULE_VERSION = "1.1"
STATUSES = ("triggered", "clear", "insufficient_data", "not_applicable", "review", "expired")
EXPIRED_DAYS = 455                                   # about 15 months without a new filing: findings are stale, not clear

# overlap groups: findings in one group share a root cause; a page shows one per group so a company is not scored three
# times for the same thing (cash conversion: A01 and B02; the share count: A07 and D03)
GROUPS = {"A01": "cash_conversion", "B02": "cash_conversion", "A07": "share_count", "D03": "share_count", "B08": "earnings_definition", "C02": "liquidity",
          "E02": "cycle", "J06": "cycle", "E07": "valuation_precision", "J08": "payout"}

NAMES = {
    "A01": ("FCF growth = the business improved", "cash flow"),
    "A07": ("Stock compensation added back = no economic cost", "share count"),
    "B02": ("Receivables growing = future cash is certain", "revenue quality"),
    "B08": ("Adjusted profit = economic profit", "earnings definition"),
    "C02": ("Low net debt = no refinancing risk", "liquidity"),
    "D03": ("EPS growth = profit growth", "share count"),
    "E02": ("Low P/E at a cyclical peak = undervalued", "valuation"),
    "E07": ("A precise DCF value = the true value", "valuation"),
    "J06": ("A bank's low P/E and high profit = safe", "banks"),
    "J08": ("A REIT's low net income = the dividend is unsafe", "REITs"),
}
# phase P2 (docs/TRAP_RULEBOOK.md): mid-cycle earnings and the P/E (E02), the DCF's range and terminal weight (E07), banks
# and REITs with rules of their own (J06, J08) instead of an industrial company's FCF rules


def fin(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v


def _r(v, d=3):
    return round(v, d) if fin(v) else None


def finding(rule_id, status, observed=None, severity=None, confidence=None, explanation="", alternatives=None, missing=None,
            evidence=None, how="", next_review="next_filing", reason=""):
    """one rule's result; the fields of the rulebook's finding record (§6.1)"""
    name, area = NAMES[rule_id]
    return {"rule_id": rule_id, "rule_version": RULE_VERSION, "name": name, "area": area, "group": GROUPS[rule_id], "status": status,
            "severity": severity if status == "triggered" else None, "confidence": confidence if status in ("triggered", "clear", "review") else None,
            "observed": observed or {}, "explanation": explanation, "alternative_explanations": alternatives or [], "missing_evidence": missing or [],
            "evidence": evidence or [], "how": how, "next_review": next_review, "reason": reason}


# ---------------------------------------------------------------- the company file, read once
def _by_end(xs):
    return sorted((x for x in xs or [] if x.get("end")), key=lambda x: x["end"])


def inputs(c):
    """What the rules read from a company file, with None where the file has nothing."""
    Q = (c or {}).get("quality") or {}
    cap = Q.get("cap") or {}
    fys = _by_end(Q.get("fy"))
    qs = _by_end(Q.get("q"))
    cap_fy = {x["end"]: x for x in _by_end(cap.get("fy"))}
    shares = _by_end(cap.get("shares"))
    quarters = (c or {}).get("quarters") or []
    latest = quarters[0] if quarters else {}
    latest_end = (quarters[0].get("end") if quarters else None) or ""
    if latest_end:                                      # years read long ago (Boston Properties: FY2010-2014 beside a 2026 quarter) are not the company now
        cutoff = f"{int(latest_end[:4]) - 2}-01-01"
        fys = [f for f in fys if f["end"] >= cutoff]
        shares = [x for x in shares if x["end"] >= cutoff]
    return {"fy": fys, "q": qs, "cap_fy": cap_fy, "shares": shares, "val": Q.get("val") or {}, "mat": cap.get("maturities") or {}, "quarters": quarters,
            "ttm": cap.get("ttm") or {}, "drivers": Q.get("drivers") or {}, "latest": latest,
            "sic": str(((c or {}).get("profile") or {}).get("sic") or ""), "name": ((c or {}).get("profile") or {}).get("name") or ""}


def is_financial(sic):
    """banks, insurers, REITs and other financials: working-capital and FCF rules do not apply as written"""
    try:
        s = int(sic[:4])
    except ValueError:
        return False
    return 6000 <= s <= 6799


def cite(label, doc_url=None, what=""):
    return {"period": label, "what": what, "url": doc_url or ""}


# ---------------------------------------------------------------- A01
def wc_items(bridge):
    """the working-capital items of a cash bridge (d_ar, d_inv, d_ap, d_accr, d_oassets …), summed, with the sign of the cash flow"""
    items = [x for x in (bridge or {}).get("items") or [] if isinstance(x, list) and len(x) >= 2 and str(x[0]).startswith("d_")]
    if not items:
        return None
    return sum(x[1] for x in items if fin(x[1]))


def rule_a01(I, docs):
    """FCF growth = the business improved: split ΔFCF into working capital, capex and the rest (A01)"""
    if is_financial(I["sic"]):
        return finding("A01", "not_applicable", reason="a financial company: free cash flow after capex is not the measure of its business")
    fys = [f for f in I["fy"] if fin(f.get("ocf")) and I["cap_fy"].get(f["end"], {}).get("items", {}).get("capex") is not None]
    if len(fys) < 2:
        return finding("A01", "insufficient_data", reason="fewer than two fiscal years with operating cash flow and capital expenditure on file")
    f0, f1 = fys[-2], fys[-1]
    cx0, cx1 = -I["cap_fy"][f0["end"]]["items"]["capex"], -I["cap_fy"][f1["end"]]["items"]["capex"]        # stored negative: paid
    fcf0, fcf1 = f0["ocf"] - cx0, f1["ocf"] - cx1
    d_fcf = fcf1 - fcf0
    wc0, wc1 = wc_items(f0.get("bridge")), wc_items(f1.get("bridge"))
    obs = {"fy_prior": f0.get("label"), "fy_current": f1.get("label"), "ocf_prior": f0["ocf"], "ocf_current": f1["ocf"], "capex_prior": cx0, "capex_current": cx1,
           "fcf_prior": fcf0, "fcf_current": fcf1, "delta_fcf": d_fcf, "delta_capex": cx1 - cx0,
           "delta_wc_cash": (wc1 - wc0) if wc0 is not None and wc1 is not None else None}
    how = "FCF = operating cash flow − cash capex; ΔFCF = ΔOCF − ΔCapEx; the working-capital part is the change in the cash-bridge items (receivables, inventory, payables, accruals), with the sign of the cash flow statement"
    ev = [cite(f1.get("label"), docs.get(f1["end"]), "cash flow statement, fiscal year"), cite(f0.get("label"), docs.get(f0["end"]), "cash flow statement, fiscal year before")]
    if d_fcf <= 0:
        return finding("A01", "clear", obs, confidence="high", explanation=f"Free cash flow did not rise ({_money(fcf0)} → {_money(fcf1)}): the trap does not arise.", how=how, evidence=ev)
    if obs["delta_wc_cash"] is None:
        return finding("A01", "insufficient_data", obs, reason="no working-capital items in the cash bridge for both years", how=how, evidence=ev)
    capex_cut = max(0.0, cx0 - cx1)
    wc_part = max(0.0, obs["delta_wc_cash"])
    temp = capex_cut + wc_part
    share = temp / d_fcf if d_fcf else 0.0
    obs.update({"capex_reduction": capex_cut, "wc_release": wc_part, "temporary_share_of_delta": _r(share)})
    core = d_fcf - obs["delta_wc_cash"] - (cx0 - cx1)                      # the change in OCF before working capital, net of capex
    obs["other_ocf_change"] = core
    small_base = fcf0 <= 0 or (abs(fcf0) < 0.02 * abs(f1["ocf"]) if f1["ocf"] else True)     # a negative or tiny base: no percentage
    pct_txt = "" if small_base else f" (+{100 * d_fcf / fcf0:.0f}%)"
    conf = "high" if all(abs((f.get("bridge") or {}).get("residual") or 0) <= 0.05 * abs(f["ocf"]) for f in (f0, f1)) else "medium"
    if share >= 0.5:
        sev = "high" if share >= 0.8 and core <= 0 else "medium"
        parts = []
        if wc_part:
            parts.append(f"working capital released {_money(wc_part)} more cash than the year before")
        if capex_cut:
            parts.append(f"capital expenditure fell by {_money(capex_cut)}")
        how_much = (f"{100 * share:.0f}% of the increase came from sources that need not repeat" if share <= 1
                    else "more than the whole increase came from sources that need not repeat")
        return finding("A01", "triggered", obs, sev, conf,
                       explanation=f"Free cash flow rose {_money(d_fcf)}{pct_txt}, from {_money(fcf0)} to {_money(fcf1)}, but {' and '.join(parts)}: "
                                   f"{how_much}. Operating cash flow before working capital "
                                   f"{'fell' if core < 0 else 'rose' if core > 0 else 'was unchanged'}{(' by ' + _money(abs(core))) if core else ''}.",
                       alternatives=["An expansion programme finished, so capex fell back to maintenance levels for good", "Suppliers agreed longer payment terms in a contract",
                                     "Inventory was brought down after a glut and will stay down"],
                       missing=["Maintenance capex (what it costs to keep the assets working)", "Supplier payment terms and any supply-chain financing", "Management's capex guidance for next year"],
                       evidence=ev, how=how)
    return finding("A01", "clear", obs, confidence=conf,
                   explanation=f"Free cash flow rose {_money(d_fcf)} to {_money(fcf1)}; working capital and lower capex explain {100 * share:.0f}% of it, "
                               f"so most of the gain is in operating cash flow itself.", how=how, evidence=ev)


# ---------------------------------------------------------------- A07
def rule_a07(I, docs):
    """Stock compensation added back = no economic cost: SBC against revenue, dilution and the buybacks that offset it (A07)"""
    sh = [s for s in I["shares"] if fin(s.get("sbc"))]
    if len(sh) < 2:
        return finding("A07", "insufficient_data", reason="fewer than two fiscal years of stock compensation and share counts on file")
    s0, s1 = sh[-2], sh[-1]
    rev = next((f["wc"]["rev"] for f in reversed(I["fy"]) if f["end"] == s1["end"] and (f.get("wc") or {}).get("rev")), None)
    if not rev:
        return finding("A07", "insufficient_data", reason="no revenue for the fiscal year of the share count")
    sbc, bb = s1["sbc"], s1.get("bb") or 0
    dil0, dil1 = s0.get("diluted"), s1.get("diluted")
    d_dil = (dil1 / dil0 - 1) if fin(dil0) and fin(dil1) and dil0 else None
    obs = {"fy": s1.get("label"), "sbc": sbc, "revenue": rev, "sbc_pct_revenue": _r(sbc / rev, 4), "buybacks": bb, "buybacks_over_sbc": _r(bb / sbc, 2) if sbc else None,
           "diluted_shares_prior": dil0, "diluted_shares": dil1, "diluted_change": _r(d_dil, 4)}
    how = "SBC / revenue from the cash flow statement's add-back; the diluted weighted share count year over year; buybacks from the financing section"
    ev = [cite(s1.get("label"), docs.get(s1["end"]), "stock compensation, buybacks and the diluted share count, fiscal year")]
    intensity = sbc / rev
    if intensity < 0.03:
        return finding("A07", "clear", obs, confidence="high", explanation=f"Stock compensation is {100 * intensity:.1f}% of revenue: small enough that adding it back changes little.", how=how, evidence=ev)
    diluting = d_dil is not None and d_dil > 0.005
    offset = bb >= sbc
    if diluting or not offset:
        sev = "high" if intensity >= 0.10 else "medium"
        why = (f"the diluted share count still rose {100 * d_dil:.1f}%" if diluting else "buybacks did not cover it") if d_dil is not None else "buybacks did not cover it"
        return finding("A07", "triggered", obs, sev, "high",
                       explanation=f"Stock compensation was {_money(sbc)}, {100 * intensity:.1f}% of revenue, in {s1.get('label')}; buybacks were {_money(bb)} "
                                   f"({(bb / sbc):.1f}× the SBC) and {why}. 'Adjusted' figures that add SBC back treat pay in shares as free; the cost is "
                                   f"borne by every shareholder as dilution, or by the cash spent to buy the shares back.",
                       alternatives=["A young company paying in equity while it scales; intensity falls as revenue grows", "Buybacks at prices below intrinsic value make up for the dilution over time",
                                     "A one-off grant (an acquisition, a founder award) rather than a steady level"],
                       missing=["The share count after the latest buybacks (the next 10-Q's cover)", "The price paid for the buybacks against the shares' value", "Unvested awards outstanding"],
                       evidence=ev, how=how)
    return finding("A07", "clear", obs, confidence="high",
                   explanation=f"Stock compensation is {100 * intensity:.1f}% of revenue, but buybacks of {_money(bb)} covered it ({(bb / sbc):.1f}×) and the diluted share count "
                               f"{'fell ' + f'{100 * -d_dil:.1f}%' if d_dil is not None and d_dil < 0 else 'was about flat'}: the dilution has been paid for in cash.", how=how, evidence=ev)


# ---------------------------------------------------------------- B02
def rule_b02(I, docs):
    """Receivables growing = future cash is certain: receivables and DSO against revenue over the last quarters (B02)"""
    if is_financial(I["sic"]):
        return finding("B02", "not_applicable", reason="a financial company: receivables and DSO are not its working capital")
    qs = [q for q in I["q"] if (q.get("wc") or {}).get("ar_c") is not None and (q.get("wc") or {}).get("rev")]
    if len(qs) < 5:
        return finding("B02", "insufficient_data", reason="fewer than five quarters with receivables and revenue on file (a year-over-year comparison needs five)")
    by_end = {q["end"]: q for q in qs}
    rows = []
    for q in qs[-2:]:
        ya = _year_ago(q["end"], list(by_end))
        if not ya:
            continue
        p = by_end[ya]
        g_rev = q["wc"]["rev"] / p["wc"]["rev"] - 1 if p["wc"]["rev"] else None
        g_ar = q["wc"]["ar_c"] / p["wc"]["ar_c"] - 1 if p["wc"]["ar_c"] else None
        rows.append((q, p, g_rev, g_ar))
    if len(rows) < 2 or any(g is None for _, _, a, b in rows for g in (a, b)):
        return finding("B02", "insufficient_data", reason="no quarter a year earlier to compare the last two quarters with")
    dsos = [q["wc"].get("dso") for q in qs if fin((q.get("wc") or {}).get("dso"))]
    med = sorted(dsos[-9:-1])[len(dsos[-9:-1]) // 2] if len(dsos) >= 5 else None
    dso = qs[-1]["wc"].get("dso")
    (q1, p1, gr1, ga1), (q0, p0, gr0, ga0) = rows[-1], rows[-2]
    obs = {"quarter": q1.get("label"), "revenue_yoy": _r(gr1, 4), "receivables_yoy": _r(ga1, 4), "prior_quarter": q0.get("label"), "prior_revenue_yoy": _r(gr0, 4),
           "prior_receivables_yoy": _r(ga0, 4), "dso": _r(dso, 1), "dso_median_8q": _r(med, 1), "receivables": q1["wc"]["ar_c"], "revenue": q1["wc"]["rev"]}
    how = "receivables and revenue against the same quarter a year earlier; DSO = receivables / quarterly revenue × days, against the median of the eight quarters before"
    ev = [cite(q1.get("label"), docs.get(q1["end"]), "receivables and revenue"), cite(p1.get("label"), docs.get(p1["end"]), "the same quarter a year earlier")]
    gap1, gap0 = ga1 - gr1, ga0 - gr0
    stretched = med is not None and dso is not None and dso >= 1.15 * med
    if gap1 >= 0.10 and gap0 >= 0.10 and stretched:
        sev = "high" if gap1 >= 0.30 else "medium"
        return finding("B02", "triggered", obs, sev, "medium",
                       explanation=f"Receivables grew {100 * ga1:.0f}% year over year in {q1.get('label')} against revenue growth of {100 * gr1:.0f}%, and the quarter before "
                                   f"{100 * ga0:.0f}% against {100 * gr0:.0f}%; days sales outstanding is {dso:.0f} against a median of {med:.0f} over the eight quarters before. "
                                   f"More of each quarter's revenue is still owed by customers.",
                       alternatives=["Seasonality: a quarter that always ends with big shipments", "An acquisition brought its own receivables", "New business with longer standard terms (government, large enterprise)",
                                     "Currency: receivables booked in a strengthening currency"],
                       missing=["The receivables ageing and the allowance for credit losses", "Any factoring or receivables sold (and whether with recourse)", "Credit terms by customer group"],
                       evidence=ev, how=how)
    if gap1 >= 0.10 and stretched:
        return finding("B02", "review", obs, confidence="medium",
                       explanation=f"Receivables outgrew revenue in {q1.get('label')} ({100 * ga1:.0f}% against {100 * gr1:.0f}%) and DSO is {dso:.0f} against a median of {med:.0f}; "
                                   f"one quarter can be timing, so this is one to watch rather than a pattern.", how=how, evidence=ev)
    return finding("B02", "clear", obs, confidence="medium",
                   explanation=f"Receivables grew {100 * ga1:.0f}% against revenue {100 * gr1:.0f}% in {q1.get('label')}" + (f"; DSO {dso:.0f} against a median of {med:.0f}" if med is not None and dso is not None else "")
                               + ": collections are keeping pace with sales.", how=how, evidence=ev)


def _year_ago(end, ends, tol=20):
    d = dt.date.fromisoformat(end)
    best = None
    for x in ends:
        if x >= end:
            continue
        gap = abs((d - dt.date.fromisoformat(x)).days - 365)
        if gap <= tol and (best is None or gap < best[0]):
            best = (gap, x)
    return best[1] if best else None


# ---------------------------------------------------------------- B08
def _item_key(label):
    """one adjustment's name across quarters: 'Amortization of acquired intangible assets (1)' = 'amortization of acquired intangible assets'"""
    k = re.sub(r"\(\d+\)|\([a-z]\)|\*+", " ", str(label or "").lower())
    k = re.sub(r"\b(net of tax(es)?|pre-?tax|after tax|the|of|and|related|expense|expenses|costs?|charges?|items?|impact)\b", " ", k)
    k = re.sub(r"[^a-z]+", " ", k).strip()
    return k[:60]


ITEM_KINDS = (("stock|share.based|equity.based|sbc", "stock compensation"), ("amortiz|intangible", "amortisation of acquired intangibles"), ("restructur|severance|reorgani|exit|realign", "restructuring"),
              ("litigation|legal|settlement", "litigation"), ("acquisition|merger|integration|transaction|deal", "acquisition costs"), ("impairment|write.?(down|off)", "impairments"),
              ("tax", "tax items"), ("gain|loss|investment|equity (in|investment)|fair value|mark.to.market|derivative|hedg", "gains and losses"), ("depreciation|interest", "definitional (EBITDA)"))


def item_kind(label):
    l = str(label or "").lower()
    return next((k for pat, k in ITEM_KINDS if re.search(pat, l)), "other")


def rule_b08(I, docs, er):
    """Adjusted profit = economic profit: the same costs excluded quarter after quarter, read from the releases'
    reconciliation tables (B08); the adjusted-vs-GAAP EPS gap as the stand-in where the tables are not on file"""
    qs = [q for q in (I["quarters"] or []) if (q.get("nongaap") or {}).get("items")]
    qs = sorted(qs, key=lambda q: q["end"])[-6:]
    recon = [q for q in qs if not re.search(r"ebitda|ffo|funds", str(q["nongaap"].get("measure") or ""), re.I) or not re.search(r"net (income|earnings|loss)", str(q["nongaap"].get("from") or ""), re.I)]
    if len(recon) >= 3:
        recon = recon[-4:]
        seen = {}
        for q in recon:
            for label, amt in q["nongaap"]["items"]:
                k = _item_key(label)
                seen.setdefault(k, {"label": label, "kind": item_kind(label), "quarters": [], "amounts": []})
                seen[k]["quarters"].append(q.get("label")); seen[k]["amounts"].append(amt)
        rec = sorted([v for v in seen.values() if len(v["quarters"]) >= 3 and v["kind"] != "definitional (EBITDA)" and sum(v["amounts"]) > 0], key=lambda v: -sum(v["amounts"]))
        gaps = [(q.get("label"), q["nongaap"]["gaap"], q["nongaap"]["adjusted"]) for q in recon]
        obs = {"quarters_with_a_reconciliation": [[l, _r(g / 1e6, 0), _r(a / 1e6, 0)] for l, g, a in gaps], "measure": recon[-1]["nongaap"].get("measure"),
               "recurring_items": [[v["label"], v["kind"], len(v["quarters"]), _r(sum(v["amounts"]) / 1e6, 0)] for v in rec],
               "latest_items": [[l, _r(a / 1e6, 0)] for l, a in recon[-1]["nongaap"]["items"]]}
        how = "the items of the release's GAAP-to-adjusted reconciliation, matched by name across the last quarters (the table is kept only where GAAP + the items = the adjusted figure); an item excluded in three or more of four quarters is recurring"
        ev = [cite(q.get("label"), q.get("doc_url"), f"reconciliation: {q['nongaap'].get('from')} → {q['nongaap'].get('measure')}") for q in recon]
        if rec:
            tot = sum(sum(v["amounts"]) for v in rec)
            gaap_tot = sum(g for _, g, _ in gaps)
            share = tot / abs(gaap_tot) if gaap_tot else None
            kinds = sorted({v["kind"] for v in rec})
            sev = "high" if share is not None and share >= 0.3 else "medium"
            return finding("B08", "triggered", obs, sev, "medium",
                           explanation=f"{seo_n(len(rec), 'cost')} excluded from adjusted profit in at least three of the last {len(recon)} quarters: " +
                                       "; ".join(f"{v['label']} ({_money(sum(v['amounts']))} over {len(v['quarters'])} quarters)" for v in rec[:4]) +
                                       (f". Together {_money(tot)}, {100 * share:.0f}% of GAAP net income over the same quarters" if share is not None else "") +
                                       ". A cost that recurs every quarter is a cost of the business, whatever the label.",
                           alternatives=["Amortisation of acquired intangibles is non-cash and many investors exclude it by choice (the cash was paid at the acquisition)",
                                         "A multi-year programme (a restructuring, an integration) with a known end date", "Litigation that will end with one judgement"],
                           missing=["Whether the same items were excluded in earlier years (the releases before these)", "Cash paid for the excluded items (the cash flow statement)", "The share count the adjusted EPS is divided by"],
                           evidence=ev, how=how)
        return finding("B08", "clear", obs, confidence="medium", explanation=f"The releases' reconciliations over the last {len(recon)} quarters show no cost excluded in three or more of them.", how=how, evidence=ev)
    pts = [p for p in ((er or {}).get("nongaap") or {}).get("points") or [] if fin(p.get("gap_pct")) and fin(p.get("street")) and fin(p.get("gaap"))]
    if len(pts) < 3:
        return finding("B08", "insufficient_data", reason=(f"{len(recon)} quarter{'s' if len(recon) != 1 else ''} with a reconciliation table on file (three are needed)" if recon else "no reconciliation table read from the releases yet") + " and fewer than three quarters with both an adjusted and a GAAP EPS")
    pts = sorted(pts, key=lambda p: p["quarter"])[-4:]
    above = [p for p in pts if p["gap_pct"] >= 0.10]
    obs = {"quarters": [[p["quarter"], p["street"], p["gaap"], _r(p["gap_pct"], 3)] for p in pts], "quarters_adjusted_above_gaap_10pct": len(above), "of": len(pts),
           "latest_gap_pct": _r(pts[-1]["gap_pct"], 3)}
    how = "the analysts' 'actual' (usually the company's adjusted EPS) against GAAP net income ÷ diluted shares for the matching quarter; a gap of 10% or more counts (the stand-in until three releases' reconciliation tables are on file)"
    ev = [cite(p["quarter"], None, f"adjusted {p['street']:.2f} vs GAAP {p['gaap']:.2f}") for p in pts]
    if len(above) >= 3:
        mean_gap = sum(p["gap_pct"] for p in above) / len(above)
        return finding("B08", "triggered", obs, "high" if mean_gap >= 0.5 else "medium", "low",
                       explanation=f"Adjusted EPS was at least 10% above GAAP in {len(above)} of the last {len(pts)} quarters (on average {100 * mean_gap:.0f}% above). "
                                   f"Costs excluded every quarter (restructuring, stock compensation, amortisation of acquired intangibles, litigation) are a recurring cost of the business, not a one-off.",
                       alternatives=["A genuine one-off this year (an impairment, a settlement) that happens to span several quarters", "Amortisation of acquired intangibles, which many investors also exclude by choice",
                                     "The analysts' 'actual' is not the company's own adjusted figure"],
                       missing=["The reconciliation table in the earnings release: which items, how much, how often", "Whether the same items were excluded in earlier years"],
                       evidence=ev, how=how)
    if above:
        return finding("B08", "review", obs, confidence="low", explanation=f"Adjusted EPS was 10% or more above GAAP in {len(above)} of the last {len(pts)} quarters: read the reconciliation before taking the adjusted figure.", how=how, evidence=ev)
    return finding("B08", "clear", obs, confidence="low", explanation=f"Adjusted and GAAP EPS were within 10% of each other in the last {len(pts)} quarters" + (" (adjusted below GAAP)" if pts[-1]["gap_pct"] < 0 else "") + ".", how=how, evidence=ev)


def seo_n(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


# ---------------------------------------------------------------- C02
def rule_c02(I, docs):
    """Low net debt = no refinancing risk: debt due within a year against cash and conservative cash flow (C02)"""
    v, mat, ttm = I["val"], I["mat"], I["ttm"]
    cash = v.get("cash_all") if v.get("cash_all") is not None else ((v.get("b_cash") or 0) + (v.get("b_sti") or 0) if v.get("b_cash") is not None else None)
    debt = v.get("debt") if v.get("debt") is not None else ((v.get("b_ltd") or 0) + (v.get("b_stb") or 0) if v.get("b_ltd") is not None else None)
    if cash is None or debt is None:
        return finding("C02", "insufficient_data", reason="no balance-sheet cash or debt on file")
    if not debt:
        if "no debt tagged" in str(v.get("debt_how") or ""):           # Berkshire: debt sits in subsidiaries' lines the reader did not find
            return finding("C02", "insufficient_data", {"cash": cash}, reason="no debt figure could be read from the balance sheet (the filing may tag it in other lines)")
        return finding("C02", "not_applicable", {"cash": cash, "debt": 0}, reason="no debt on the balance sheet")
    buckets = {b[0]: b[1] for b in mat.get("buckets") or [] if isinstance(b, list) and len(b) >= 2 and fin(b[1])}
    due12 = buckets.get(1)
    src = "the debt maturity table"
    if due12 is None and v.get("b_ltd_c") is not None:
        due12 = (v.get("b_ltd_c") or 0) + (v.get("b_stb") or 0)
        src = "the current portion of debt on the balance sheet"
    if due12 is None:
        return finding("C02", "insufficient_data", {"cash": cash, "debt": debt}, reason="neither a maturity table nor the current portion of debt is on file")
    items = ttm.get("items") or {}
    ocf, capex = items.get("ocf"), items.get("capex")
    fcf = (ocf + (capex or 0)) if fin(ocf) else None
    cover = cash + max(0.0, fcf or 0.0)
    obs = {"cash": cash, "debt": debt, "net_debt": debt - cash, "due_12m": due12, "due_source": src, "fcf_ttm": fcf, "cover": cover, "cover_ratio": _r(cover / due12, 2) if due12 else None,
           "due_2y": buckets.get(2), "as_of": v.get("end") or mat.get("at")}
    how = "due within a year from the maturity table (else the current portion of debt), against cash and investments plus free cash flow over the last twelve months (zero if negative); no credit lines assumed"
    ev = [cite(mat.get("label") or v.get("end"), docs.get(I["latest"].get("end")), "debt maturities, cash and investments")]
    if due12 <= 0:
        return finding("C02", "clear", obs, confidence="medium", explanation=f"Nothing comes due within a year; net debt is {_money(debt - cash)}.", how=how, evidence=ev)
    if cover < due12:
        short = due12 - cover
        sev = "high" if cover < 0.75 * due12 else "medium"
        return finding("C02", "triggered", obs, sev, "medium",
                       explanation=f"{_money(due12)} of debt comes due within a year against {_money(cash)} of cash and investments"
                                   + (f" and {_money(fcf)} of free cash flow over the last twelve months" if fcf and fcf > 0 else (" and no free cash flow to add" if fcf is not None else ""))
                                   + f": {_money(short)} short, to be refinanced or raised. Net debt of {_money(debt - cash)} says nothing about when the debt falls due.",
                       alternatives=["A committed, undrawn credit facility covers the gap (not visible in the balance sheet)", "The notes are routinely rolled over in the commercial-paper or bond market at an investment-grade rating",
                                     "Cash held abroad or in subsidiaries can be moved to where the debt is", "A sale of a business or asset already agreed brings the cash"],
                       missing=["Undrawn committed facilities and their covenants", "The cost and rating of the refinancing", "Restricted cash and the operating minimum"],
                       evidence=ev, how=how)
    return finding("C02", "clear", obs, confidence="medium",
                   explanation=f"{_money(due12)} comes due within a year, {obs['cover_ratio']:.1f}× covered by cash and investments of {_money(cash)}" + (f" plus {_money(fcf)} of free cash flow" if fcf and fcf > 0 else "") + ".",
                   how=how, evidence=ev)


# ---------------------------------------------------------------- D03
def rule_d03(I, docs):
    """EPS growth = profit growth: EPS up while net income is flat and the share count fell (D03)"""
    dq = [d for d in (I["drivers"].get("q") or []) if (d.get("eps") or {}).get("eps0") is not None and (d.get("cur") or {}).get("ni") is not None and (d.get("pri") or {}).get("ni") is not None
          and fin(d.get("dil0")) and fin(d.get("dil1"))]
    if not dq:
        return finding("D03", "insufficient_data", reason="no quarter with EPS, net income and diluted shares for both this year and last")
    d = sorted(dq, key=lambda x: x["end"])[-1]
    ni0, ni1 = d["pri"]["ni"], d["cur"]["ni"]
    e0, e1 = d["eps"]["eps0"], d["eps"]["eps1"]
    obs = {"quarter": d.get("label"), "prior_quarter": d.get("prev_label"), "eps_prior": e0, "eps": e1, "net_income_prior": ni0, "net_income": ni1,
           "diluted_shares_prior": d["dil0"], "diluted_shares": d["dil1"], "eps_growth": _r(e1 / e0 - 1, 4) if e0 else None, "net_income_growth": _r(ni1 / ni0 - 1, 4) if ni0 else None,
           "share_count_change": _r(d["dil1"] / d["dil0"] - 1, 4) if d["dil0"] else None}
    how = "EPS and net income against the same quarter a year earlier; the EPS bridge attributes the change to profit first, then to the share count (the order is fixed and disclosed)"
    ev = [cite(d.get("label"), docs.get(d.get("end")), "net income, diluted shares, EPS"), cite(d.get("prev_label"), docs.get(d.get("prev")), "the same quarter a year earlier")]
    if ni0 <= 0 or ni1 <= 0 or e0 <= 0:
        return finding("D03", "not_applicable", obs, reason="a loss in one of the quarters: EPS growth has no meaning")
    g_eps, g_ni, g_sh = e1 / e0 - 1, ni1 / ni0 - 1, d["dil1"] / d["dil0"] - 1
    if g_eps >= 0.05 and g_ni <= 0.02 and g_sh <= -0.01:
        from_shares = (e1 - ni1 / d["dil0"]) / e0 if d["dil0"] else None       # EPS at the old share count, then the share count's part
        obs["eps_growth_from_share_count"] = _r(from_shares, 4)
        return finding("D03", "triggered", obs, "medium", "high",
                       explanation=f"EPS rose {100 * g_eps:.0f}% in {d.get('label')} ({e0:.2f} → {e1:.2f}) while net income {'fell ' + f'{100 * -g_ni:.0f}%' if g_ni < 0 else 'was flat'} "
                                   f"({_money(ni0)} → {_money(ni1)}): the diluted share count fell {100 * -g_sh:.1f}%, and {'all' if from_shares is not None and from_shares >= g_eps - 0.005 else 'most'} of the EPS growth is the smaller denominator.",
                       alternatives=["Buybacks at prices below the shares' value do add value per share; the question is the price paid and how they were financed", "A one-off item depressed this quarter's net income",
                                     "Shares were cancelled after a disposal whose proceeds were returned"],
                       missing=["The average price paid for the buybacks against the shares' value", "Whether the buybacks were funded by debt", "Next quarter's net income trend"],
                       evidence=ev, how=how)
    return finding("D03", "clear", obs, confidence="high",
                   explanation=f"EPS {'rose' if g_eps >= 0 else 'fell'} {100 * abs(g_eps):.0f}% and net income {'rose' if g_ni >= 0 else 'fell'} {100 * abs(g_ni):.0f}% in {d.get('label')}; "
                               f"the share count {'fell' if g_sh < 0 else 'rose'} {100 * abs(g_sh):.1f}%: EPS growth follows profit growth.", how=how, evidence=ev)


# ---------------------------------------------------------------- E02 / J06: the cycle
def fy_net_income(c):
    """[(label, net income)] by fiscal year, oldest first, from the company file's history (quality.hist)"""
    h = ((c or {}).get("quality") or {}).get("hist") or {}
    per, v = h.get("periods") or [], (h.get("v") or {}).get("ni") or []
    out = []
    for i, vals in v:
        if i < len(per) and per[i][2] == "fy" and vals and fin(vals[0][0]):
            out.append((per[i][3], vals[0][0]))
    return out


def is_bank(sic):
    try:
        s = int(sic[:4])
    except ValueError:
        return False
    return 6020 <= s <= 6036 or s in (6099, 6111, 6141, 6153, 6159, 6162, 6163, 6172, 6189, 6199)


def is_reit(sic):
    return sic[:4] == "6798"


def rule_e02(c, I, val, docs):
    """Low P/E at a cyclical peak = undervalued: the P/E on this year's profit against the P/E on mid-cycle profit (E02)"""
    if is_financial(I["sic"]):
        return finding("E02", "not_applicable", reason="a financial company: J06 reads its cycle instead")
    inp = (val or {}).get("inputs") or {}
    mcap, ni = inp.get("mcap"), inp.get("ni")
    fys = fy_net_income(c)
    if not fin(mcap) or not fin(ni) or not mcap:
        return finding("E02", "insufficient_data", reason="no market value or trailing net income in the valuation research")
    if len(fys) < 5:
        return finding("E02", "insufficient_data", reason=f"{len(fys)} fiscal years of net income on file; a cycle needs five")
    hist = [v for _, v in fys[-8:]]
    med = sorted(hist)[len(hist) // 2]
    peak = max(hist)
    obs = {"market_value": mcap, "net_income_ttm": ni, "pe_ttm": _r(mcap / ni, 1) if ni > 0 else None, "net_income_median_fy": med, "pe_mid_cycle": _r(mcap / med, 1) if med > 0 else None,
           "net_income_peak_fy": peak, "years": [[l, _r(v / 1e6, 0)] for l, v in fys[-8:]]}
    how = "P/E on the trailing twelve months' net income against the P/E on the median net income of the last eight fiscal years (a mid-cycle stand-in); 'at a peak' = this year's profit at or above 90% of the best year and at least 1.3× the median"
    ev = [cite(I["latest"].get("label"), docs.get(I["latest"].get("end")), "net income, trailing twelve months")]
    if ni <= 0 or med <= 0:
        return finding("E02", "not_applicable", obs, reason="a loss on a trailing or mid-cycle basis: the P/E has no meaning", how=how, evidence=ev)
    pe, pe_mid = mcap / ni, mcap / med
    ups = sum(1 for a, b in zip(hist, hist[1:]) if b > a)
    cyclical = len(hist) - 1 - ups >= 2                 # at least two down years in the window: a cycle, not a steady climb
    obs["down_years_in_window"] = len(hist) - 1 - ups
    at_peak = ni >= 0.9 * peak and ni >= 1.3 * med
    if at_peak and not cyclical:
        return finding("E02", "clear", obs, confidence="medium", explanation=f"Net income of {_money(ni)} is a high, but the last eight years rose almost every year (median {_money(med)}): a steady climb, not a cycle's top, so the P/E of {pe:.1f}× is not on peak profit in that sense.", how=how, evidence=ev)
    if at_peak and pe <= 12:
        return finding("E02", "triggered", obs, "high" if pe_mid >= 2.5 * pe else "medium", "medium",
                       explanation=f"The shares trade at {pe:.1f}× this year's net income of {_money(ni)}, but that profit is at a high: the median of the last eight fiscal years is {_money(med)}, "
                                   f"on which the same market value is {pe_mid:.1f}×. A low multiple of peak profit is not a low multiple of normal profit.",
                       alternatives=["The business has changed for good (a merger, a new line, a pricing regime) and the old years are not its normal", "The market is right that profit will fall, and the price already says so",
                                     "Capacity has left the industry, so the cycle's trough is higher than before"],
                       missing=["Where the industry's prices and volumes stand against their own history", "Capacity on order across the industry", "Management's view of the cycle in the MD&A"],
                       evidence=ev, how=how)
    if at_peak:
        return finding("E02", "review", obs, confidence="medium",
                       explanation=f"Net income of {_money(ni)} is at a high against a median of {_money(med)} over eight years; at {pe:.1f}× the market is not pricing it as cheap, but a multiple on this year's profit still understates the mid-cycle one ({pe_mid:.1f}×).", how=how, evidence=ev)
    return finding("E02", "clear", obs, confidence="medium", explanation=f"Net income of {_money(ni)} is not at a cyclical high against the last eight years (median {_money(med)}, best {_money(peak)}): the P/E of {pe:.1f}× is on a normal year.", how=how, evidence=ev)


def rule_j06(c, I, val, docs):
    """A bank's low P/E and high profit = safe: profit at a cycle high priced as permanent (J06)"""
    if not is_bank(I["sic"]):
        return finding("J06", "not_applicable", reason="not a bank")
    inp = (val or {}).get("inputs") or {}
    mcap, ni = inp.get("mcap"), inp.get("ni")
    fys = fy_net_income(c)
    if not fin(mcap) or not fin(ni) or not mcap:
        return finding("J06", "insufficient_data", reason="no market value or trailing net income in the valuation research")
    if len(fys) < 5:
        return finding("J06", "insufficient_data", reason=f"{len(fys)} fiscal years of net income on file; a credit cycle needs five")
    hist = [v for _, v in fys[-8:]]
    med, peak = sorted(hist)[len(hist) // 2], max(hist)
    obs = {"market_value": mcap, "net_income_ttm": ni, "pe_ttm": _r(mcap / ni, 1) if ni > 0 else None, "net_income_median_fy": med, "pe_mid_cycle": _r(mcap / med, 1) if med > 0 else None,
           "years": [[l, _r(v / 1e6, 0)] for l, v in fys[-8:]]}
    how = "a bank's P/E on trailing net income against the P/E on its median net income of the last eight years; credit losses, deposit costs and capital are what turn the cycle, none of which the P/E shows"
    ev = [cite(I["latest"].get("label"), docs.get(I["latest"].get("end")), "net income")]
    if ni <= 0 or med <= 0:
        return finding("J06", "not_applicable", obs, reason="a loss: the P/E has no meaning", how=how, evidence=ev)
    pe = mcap / ni
    ups = sum(1 for a, b in zip(hist, hist[1:]) if b > a)
    obs["down_years_in_window"] = len(hist) - 1 - ups
    if ni >= 0.9 * peak and ni >= 1.25 * med and pe <= 11 and len(hist) - 1 - ups >= 1:
        return finding("J06", "triggered", obs, "medium", "low",
                       explanation=f"The bank trades at {pe:.1f}× net income of {_money(ni)}, its best or near-best year of the last eight (median {_money(med)}). Bank profit at the top of a credit cycle carries low provisions and cheap deposits; "
                                   f"the P/E says nothing about the loan book, the deposit costs or the capital that decide the next part of the cycle.",
                       alternatives=["Higher rates lifted net interest income for good, not for a cycle", "The bank's mix (fees, wealth management) is less cyclical than a lender's", "Provisions are already at a normal level and reserves are full"],
                       missing=["The allowance for credit losses against loans and its trend", "Deposit costs and the share of uninsured deposits", "CET1 and the loan book's concentration (CRE, construction, consumer)"],
                       evidence=ev, how=how)
    return finding("J06", "clear", obs, confidence="low", explanation=f"At {pe:.1f}× net income of {_money(ni)} (median {_money(med)} over eight years) the profit is not at a cycle high priced as cheap; the credit cycle is still the thing to read.", how=how, evidence=ev)


# ---------------------------------------------------------------- E07: the DCF's precision
def rule_e07(val, docs, I):
    """A precise DCF value = the true value: the terminal value's weight and the range across the inputs (E07)"""
    dcf, sens = (val or {}).get("dcf") or {}, (val or {}).get("sensitivity") or {}
    v, price = dcf.get("value"), (val or {}).get("price")
    if not fin(v):
        return finding("E07", "insufficient_data", reason="no DCF in the valuation research for this company")
    tor = [t for t in sens.get("tornado") or [] if fin(t.get("low")) and fin(t.get("high"))]
    rng = (val or {}).get("range")
    obs = {"dcf_value": _r(v, 2), "price": price, "terminal_value_share": _r(dcf.get("tv_share"), 3),
           "swing_by_input": [[t.get("input"), t.get("how"), _r(t["low"], 2), _r(t["high"], 2)] for t in tor[:4]],
           "range_all_methods": [_r(rng[0], 2), _r(rng[1], 2)] if isinstance(rng, list) and len(rng) == 2 else None}
    how = "the DCF's point value against the share of it that is the terminal value and the value at each input moved by one step (growth ±5 pts, WACC ±1 pt, margin ±3 pts …); the range across every method the research ran"
    ev = [cite(str((val or {}).get("generated_at") or "")[:10], None, "valuation research")]
    if not tor:
        return finding("E07", "review", obs, confidence="medium", explanation=f"The DCF says {v:,.2f} a share" + (f", {100 * dcf['tv_share']:.0f}% of it the terminal value" if fin(dcf.get("tv_share")) else "") + "; no sensitivity run is on file, so read it as a range, not a point.", how=how, evidence=ev)
    top = max(tor, key=lambda t: abs(t["high"] - t["low"]))
    spread = (top["high"] - top["low"]) / v if v else None
    tv = dcf.get("tv_share")
    always = (f"The DCF's point value is {v:,.2f} a share" + (f" (price {price:,.2f})" if fin(price) else "") + (f"; {100 * tv:.0f}% of it is the terminal value, a number about years no one has seen" if fin(tv) else "")
              + f". Moving {top['input'].lower()} by {top['how']} alone takes it from {top['low']:,.2f} to {top['high']:,.2f}"
              + (f"; across every method the research ran the range is {rng[0]:,.0f} to {rng[1]:,.0f}" if obs["range_all_methods"] else "") + ". The value is a range; the decimals are not information.")
    sev = "high" if (fin(tv) and tv >= 0.7) or (spread and spread >= 0.4) else "medium"    # most of the value in the terminal, or one input swings it 40%
    return finding("E07", "review", obs, severity=None, confidence="high", explanation=always,
                   alternatives=["A stable, mature business with a narrow range of outcomes, where the point value is a fair summary", "The inputs that matter most are themselves well known (a regulated return, a long contract)"],
                   missing=["Which input you believe differs from the research's and why", "What the price implies for growth (the reverse DCF on the fair-value page)"],
                   evidence=ev, how=how) | {"watch": sev}


# ---------------------------------------------------------------- J08: a REIT's payout
def rule_j08(I, docs):
    """A REIT's low net income = the dividend is unsafe: the dividend against operating cash flow after maintenance capex (J08)"""
    if not is_reit(I["sic"]):
        return finding("J08", "not_applicable", reason="not a REIT")
    fys = [f for f in I["fy"] if fin(f.get("ocf")) and fin(f.get("ni"))]
    if not fys:
        return finding("J08", "insufficient_data", reason="no fiscal year with net income and operating cash flow on file")
    f1 = fys[-1]
    items = (I["cap_fy"].get(f1["end"]) or {}).get("items") or {}
    div, capex = items.get("div"), items.get("capex")
    if div is None:
        return finding("J08", "insufficient_data", reason="no dividends paid in the cash flow statement for the latest fiscal year")
    div, capex = abs(div), abs(capex or 0)
    ni, ocf = f1["ni"], f1["ocf"]
    obs = {"fy": f1.get("label"), "net_income": ni, "operating_cash_flow": ocf, "dividends_paid": div, "capex": capex, "payout_of_net_income": _r(div / ni, 2) if ni > 0 else None,
           "payout_of_ocf": _r(div / ocf, 2) if ocf > 0 else None, "payout_of_ocf_after_capex": _r(div / (ocf - capex), 2) if ocf - capex > 0 else None}
    how = "a REIT's net income is after depreciation of buildings that usually hold their value, so FFO / AFFO is the payout measure; here operating cash flow and operating cash flow after capex stand in for it (capex includes acquisitions of property where the filing lumps them)"
    ev = [cite(f1.get("label"), docs.get(f1["end"]), "net income, operating cash flow, dividends and capex, fiscal year")]
    if ocf <= 0:
        return finding("J08", "triggered", obs, "high", "medium", explanation=f"Dividends of {_money(div)} were paid in {f1.get('label')} while operating cash flow was {_money(ocf)}: the payout is funded by borrowing or asset sales, whatever net income says.",
                       alternatives=["A one-off working-capital swing in the year", "A development programme nearing completion"], missing=["FFO and AFFO as the REIT reports them", "The development pipeline and its funding"], evidence=ev, how=how)
    if div > ocf:
        return finding("J08", "triggered", obs, "medium", "medium",
                       explanation=f"Dividends of {_money(div)} exceeded operating cash flow of {_money(ocf)} in {f1.get('label')} ({100 * div / ocf:.0f}%): the low net income ({_money(ni)}) is not the reason to worry, the cash is.",
                       alternatives=["Capital returned after a disposal, as a one-off", "Timing of rent collections at year end"], missing=["FFO and AFFO as the REIT reports them", "The maintenance capex the REIT discloses", "Debt maturities and undrawn facilities"], evidence=ev, how=how)
    if ni < div:
        return finding("J08", "clear", obs, confidence="medium",
                       explanation=f"Net income of {_money(ni)} is below the {_money(div)} of dividends, as a REIT's usually is: depreciation of buildings is not cash. Operating cash flow of {_money(ocf)} covers the dividend {ocf / div:.1f}×"
                                   + (f" ({(ocf - capex) / div:.1f}× after capex of {_money(capex)})" if ocf - capex > 0 else f"; capex of {_money(capex)} is larger than what is left, which is a funding question, not a payout one") + ".", how=how, evidence=ev)
    return finding("J08", "clear", obs, confidence="medium", explanation=f"Dividends of {_money(div)} are covered by net income ({_money(ni)}) and by operating cash flow ({_money(ocf)}).", how=how, evidence=ev)


# ---------------------------------------------------------------- the run
def _money(v):
    if not fin(v):
        return "—"
    if v == 0:
        return "$0"
    a, s = abs(v), "−" if v < 0 else ""
    if a >= 1e12:
        return f"{s}${a / 1e12:.2f}T"
    if a >= 1e9:
        return f"{s}${a / 1e9:.1f}B"
    if a >= 1e6:
        return f"{s}${a / 1e6:.0f}M"
    return f"{s}${a / 1e3:.0f}K"


SEV = {"high": 3, "medium": 2, "low": 1, None: 0}
CONF = {"high": 3, "medium": 2, "low": 1, None: 0}


def evaluate(c, er=None, today=None, val=None):
    """Every rule on one company: {cik, name, as_of, filed, generated_at, rule_version, findings, summary, priority}.
    er: the earnings research file; val: the valuation research file (both optional: their rules read insufficient)."""
    today = today or dt.date.today()
    I = inputs(c)
    docs = {}
    for q in list((c or {}).get("quarters") or []) + list((c or {}).get("years") or []):
        if q.get("end") and q.get("doc_url"):
            docs.setdefault(q["end"], q["doc_url"])
    latest = I["latest"]
    as_of, filed = latest.get("end"), latest.get("filed")
    out = [rule_a01(I, docs), rule_a07(I, docs), rule_b02(I, docs), rule_b08(I, docs, er), rule_c02(I, docs), rule_d03(I, docs),
           rule_e02(c, I, val, docs), rule_e07(val, docs, I), rule_j06(c, I, val, docs), rule_j08(I, docs)]
    expired = False
    if filed:
        try:
            expired = (today - dt.date.fromisoformat(filed[:10])).days > EXPIRED_DAYS
        except ValueError:
            expired = False
    if expired:
        for f in out:
            if f["status"] in ("triggered", "clear", "review"):
                f["status_before_expiry"] = f["status"]
                f["status"] = "expired"
                f["reason"] = f"the latest filing is from {filed[:10]}: the finding is out of date, not cleared"
    summary = {s: sum(1 for f in out if f["status"] == s) for s in STATUSES}
    # the priority list: triggered findings by severity then confidence, one per overlap group; then the ones to review
    pri, seen = [], set()
    for f in sorted((f for f in out if f["status"] == "triggered"), key=lambda f: (-SEV[f["severity"]], -CONF[f["confidence"]], f["rule_id"])):
        if f["group"] in seen:
            f["merged_into_group"] = True
            continue
        seen.add(f["group"])
        pri.append(f["rule_id"])
    pri += [f["rule_id"] for f in out if f["status"] == "review"][:max(0, 3 - len(pri))]
    return {"cik": ((c or {}).get("profile") or {}).get("cik"), "name": I["name"], "as_of": as_of, "filed": filed, "doc_url": latest.get("doc_url"), "generated_at": today.isoformat(),
            "rule_version": RULE_VERSION, "findings": out, "summary": summary, "priority": pri[:3], "is_demo": False,
            "note": ("Each finding is a question to verify against the filing, with the normal explanations that produce the same figures. "
                     "A triggered rule is not a finding of manipulation and not a view on the stock. Not investment advice.")}
