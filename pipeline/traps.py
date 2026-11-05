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

RULE_VERSION = "1.0"
STATUSES = ("triggered", "clear", "insufficient_data", "not_applicable", "review", "expired")
EXPIRED_DAYS = 455                                   # about 15 months without a new filing: findings are stale, not clear

# overlap groups: findings in one group share a root cause; a page shows one per group so a company is not scored three
# times for the same thing (cash conversion: A01 and B02; the share count: A07 and D03)
GROUPS = {"A01": "cash_conversion", "B02": "cash_conversion", "A07": "share_count", "D03": "share_count", "B08": "earnings_definition", "C02": "liquidity"}

NAMES = {
    "A01": ("FCF growth = the business improved", "cash flow"),
    "A07": ("Stock compensation added back = no economic cost", "share count"),
    "B02": ("Receivables growing = future cash is certain", "revenue quality"),
    "B08": ("Adjusted profit = economic profit", "earnings definition"),
    "C02": ("Low net debt = no refinancing risk", "liquidity"),
    "D03": ("EPS growth = profit growth", "share count"),
}


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
    return {"fy": fys, "q": qs, "cap_fy": cap_fy, "shares": shares, "val": Q.get("val") or {}, "mat": cap.get("maturities") or {},
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
def rule_b08(I, docs, er):
    """Adjusted profit = economic profit: adjusted (street) EPS above GAAP quarter after quarter (B08)"""
    pts = [p for p in ((er or {}).get("nongaap") or {}).get("points") or [] if fin(p.get("gap_pct")) and fin(p.get("street")) and fin(p.get("gaap"))]
    if len(pts) < 3:
        return finding("B08", "insufficient_data", reason="fewer than three quarters with both an adjusted and a GAAP EPS on file")
    pts = sorted(pts, key=lambda p: p["quarter"])[-4:]
    above = [p for p in pts if p["gap_pct"] >= 0.10]
    obs = {"quarters": [[p["quarter"], p["street"], p["gaap"], _r(p["gap_pct"], 3)] for p in pts], "quarters_adjusted_above_gaap_10pct": len(above), "of": len(pts),
           "latest_gap_pct": _r(pts[-1]["gap_pct"], 3)}
    how = "the analysts' 'actual' (usually the company's adjusted EPS) against GAAP net income ÷ diluted shares for the matching quarter; a gap of 10% or more counts"
    ev = [cite(p["quarter"], None, f"adjusted {p['street']:.2f} vs GAAP {p['gaap']:.2f}") for p in pts]
    if len(above) >= 3:
        mean_gap = sum(p["gap_pct"] for p in above) / len(above)
        return finding("B08", "triggered", obs, "high" if mean_gap >= 0.5 else "medium", "medium",
                       explanation=f"Adjusted EPS was at least 10% above GAAP in {len(above)} of the last {len(pts)} quarters (on average {100 * mean_gap:.0f}% above). "
                                   f"Costs excluded every quarter (restructuring, stock compensation, amortisation of acquired intangibles, litigation) are a recurring cost of the business, not a one-off.",
                       alternatives=["A genuine one-off this year (an impairment, a settlement) that happens to span several quarters", "Amortisation of acquired intangibles, which many investors also exclude by choice",
                                     "The analysts' 'actual' is not the company's own adjusted figure"],
                       missing=["The reconciliation table in the earnings release: which items, how much, how often", "Whether the same items were excluded in earlier years"],
                       evidence=ev, how=how)
    if above:
        return finding("B08", "review", obs, confidence="medium", explanation=f"Adjusted EPS was 10% or more above GAAP in {len(above)} of the last {len(pts)} quarters: read the reconciliation before taking the adjusted figure.", how=how, evidence=ev)
    return finding("B08", "clear", obs, confidence="medium", explanation=f"Adjusted and GAAP EPS were within 10% of each other in the last {len(pts)} quarters" + (" (adjusted below GAAP)" if pts[-1]["gap_pct"] < 0 else "") + ".", how=how, evidence=ev)


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


def evaluate(c, er=None, today=None):
    """Every rule on one company: {cik, name, as_of, filed, generated_at, rule_version, findings, summary, priority}."""
    today = today or dt.date.today()
    I = inputs(c)
    docs = {}
    for q in list((c or {}).get("quarters") or []) + list((c or {}).get("years") or []):
        if q.get("end") and q.get("doc_url"):
            docs.setdefault(q["end"], q["doc_url"])
    latest = I["latest"]
    as_of, filed = latest.get("end"), latest.get("filed")
    out = [rule_a01(I, docs), rule_a07(I, docs), rule_b02(I, docs), rule_b08(I, docs, er), rule_c02(I, docs), rule_d03(I, docs)]
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
    return {"cik": ((c or {}).get("profile") or {}).get("cik"), "name": I["name"], "as_of": as_of, "filed": filed, "generated_at": today.isoformat(),
            "rule_version": RULE_VERSION, "findings": out, "summary": summary, "priority": pri[:3], "is_demo": False,
            "note": ("Each finding is a question to verify against the filing, with the normal explanations that produce the same figures. "
                     "A triggered rule is not a finding of manipulation and not a view on the stock. Not investment advice.")}
