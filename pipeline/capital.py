"""Capital allocation from SEC XBRL company facts: where a company's cash came from and where it went, how its share
count moved, and when its long-term debt falls due — the company page's "Capital" tab.

  sources = operating cash flow (when positive) + net borrowing (when positive) + shares issued + asset and business
            sales + other investing or financing inflows + cash drawn from the balance sheet
  uses    = capital expenditures + acquisitions + buybacks + dividends + taxes paid on employee shares + net debt
            repaid + other investing or financing outflows + cash added to the balance sheet

Every line is the filer's own cash-flow tag. "Other investing" and "other financing" are each section's reported total
minus the lines shown; what operating, investing and financing cash flow and the exchange-rate effect do not explain
against the reported change in cash is shown as unreconciled (usually cash flows of discontinued operations), never
spread over the other lines. Debt is shown net (issued − repaid): companies that roll commercial paper report gross
figures many times their actual borrowing; the gross figures are kept for the evidence drawer.

Periods: the last five fiscal years, and the trailing twelve months when a 10-Q came after the last 10-K
(last fiscal year + this year to date − the same period a year earlier).
"""
from . import facts as F
from . import fsa as W

KEEP_FY = 5

OCF = F.CONCEPTS["ocf"]
INV_TOTAL = ["NetCashProvidedByUsedInInvestingActivities", "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations"]
FIN_TOTAL = ["NetCashProvidedByUsedInFinancingActivities", "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations"]
FX = ["EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
      "EffectOfExchangeRateOnCashAndCashEquivalents",
      "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsIncludingDisposalGroupAndDiscontinuedOperations"]
DCASH = ["CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
         "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseExcludingExchangeRateEffect",
         "CashAndCashEquivalentsPeriodIncreaseDecrease", "CashPeriodIncreaseDecrease",
         "CashAndCashEquivalentsPeriodIncreaseDecreaseExcludingExchangeRateEffect"]
EXCL_FX = {"CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseExcludingExchangeRateEffect",
           "CashAndCashEquivalentsPeriodIncreaseDecreaseExcludingExchangeRateEffect"}

ACQ = ["PaymentsToAcquireBusinessesNetOfCashAcquired", "PaymentsToAcquireBusinessesGross",
       "PaymentsToAcquireBusinessesAndInterestInAffiliates"]
# asset and business sales: one tag per group
SALES = [["ProceedsFromSalesOfBusinessAffiliateAndProductiveAssets"],         # both kinds in one figure: nothing else
         ["ProceedsFromSaleOfPropertyPlantAndEquipment", "ProceedsFromSaleOfProductiveAssets",
          "ProceedsFromSaleOfOtherPropertyPlantAndEquipment", "ProceedsFromSaleOfRealEstateHeldforinvestment",
          "ProceedsFromSaleOfRealEstate", "ProceedsFromSaleOfPropertyHeldForSale"],
         ["ProceedsFromDivestitureOfBusinessesNetOfCashDivested", "ProceedsFromDivestitureOfBusinesses",
          "ProceedsFromSaleOfBusinesses", "ProceedsFromDivestitureOfBusinessesAndInterestsInAffiliates"]]
SALES_TOTALS = {"ProceedsFromSalesOfBusinessAffiliateAndProductiveAssets"}
# property bought by real-estate companies (their main investment; not in the capital expenditure tags)
REALESTATE = ["PaymentsToAcquireRealEstate", "PaymentsToAcquireCommercialRealEstate", "PaymentsToAcquireRealEstateHeldForInvestment"]
BUYBACK = ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity"]
DIVIDEND = ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends", "PaymentsOfOrdinaryDividends"]
WITHHOLD = ["PaymentsRelatedToTaxWithholdingForShareBasedCompensation"]
# shares issued: offerings, then employee plans; a total of all equity issued covers the employee group
STOCK = [["ProceedsFromIssuanceOfCommonStock", "ProceedsFromIssuanceOrSaleOfEquity", "ProceedsFromIssuanceInitialPublicOffering"],
         ["ProceedsFromStockOptionsExercised", "ProceedsFromIssuanceOfSharesUnderIncentiveAndShareBasedCompensationPlansIncludingStockOptions",
          "ProceedsFromIssuanceOfSharesUnderIncentiveAndShareBasedCompensationPlans", "ProceedsFromStockPlans"],
         ["ProceedsFromSaleOfTreasuryStock"],
         ["ProceedsFromIssuanceOfPreferredStockAndPreferenceStock", "ProceedsFromIssuanceOfConvertiblePreferredStock"]]
STOCK_TOTALS = {"ProceedsFromIssuanceOrSaleOfEquity"}
# debt: a net figure for all borrowing when the filer gives one, else gross issued − gross repaid + net short-term
DEBT_NET_ALL = ["ProceedsFromRepaymentsOfDebt", "ProceedsFromRepaymentsOfLongTermDebtAndCapitalSecurities"]
DEBT_IN = [["ProceedsFromIssuanceOfLongTermDebt", "ProceedsFromIssuanceOfDebt", "ProceedsFromDebtNetOfIssuanceCosts",
            "ProceedsFromIssuanceOfSeniorLongTermDebt", "ProceedsFromIssuanceOfUnsecuredDebt", "ProceedsFromIssuanceOfSecuredDebt",
            "ProceedsFromConvertibleDebt", "ProceedsFromIssuanceOfLongTermDebtAndCapitalSecuritiesNet", "ProceedsFromNotesPayable",
            "ProceedsFromDebtMaturingInMoreThanThreeMonths"],
           ["ProceedsFromLongTermLinesOfCredit", "ProceedsFromLinesOfCredit"],
           ["ProceedsFromShortTermDebt", "ProceedsFromIssuanceOfCommercialPaper"],
           ["ProceedsFromShortTermDebtMaturingInMoreThanThreeMonths"],
           ["ProceedsFromOtherShortTermDebt"]]
DEBT_OUT = [["RepaymentsOfLongTermDebt", "RepaymentsOfDebt", "RepaymentsOfSeniorDebt", "RepaymentsOfLongTermDebtAndCapitalSecurities",
             "RepaymentsOfUnsecuredDebt", "RepaymentsOfSecuredDebt", "RepaymentsOfConvertibleDebt", "RepaymentsOfNotesPayable",
             "RepaymentsOfDebtAndCapitalLeaseObligations", "RepaymentsOfDebtMaturingInMoreThanThreeMonths"],
            ["RepaymentsOfLinesOfCredit", "RepaymentsOfLongTermLinesOfCredit"],
            ["RepaymentsOfShortTermDebt", "RepaymentsOfCommercialPaper"],
            ["RepaymentsOfShortTermDebtMaturingInMoreThanThreeMonths"],
            ["RepaymentsOfOtherShortTermDebt"],
            ["FinanceLeasePrincipalPayments", "RepaymentsOfLongTermCapitalLeaseObligations"]]
DEBT_ST_NET = [["ProceedsFromRepaymentsOfShortTermDebt", "ProceedsFromRepaymentsOfShortTermDebtMaturingInThreeMonthsOrLess"],
               ["ProceedsFromRepaymentsOfShortTermDebtMaturingInMoreThanThreeMonths"],
               ["ProceedsFromRepaymentsOfCommercialPaper"],
               ["ProceedsFromRepaymentsOfLinesOfCredit"],
               ["ProceedsFromRepaymentsOfOtherDebt"],
               ["ProceedsFromRepaymentsOfRelatedPartyDebt"]]
# every debt tag, signed as cash: when the fixed groups above do not fit the financing section (a filer tags both a
# statement line and its breakdown from the notes: Apple's commercial paper, net, and the same split by maturity), the
# combination of these that, with the other lines, adds up to the section's total is used instead
DEBT_TAGS = ([(1, t) for g in DEBT_IN for t in g] + [(-1, t) for g in DEBT_OUT for t in g] +
             [(1, t) for g in DEBT_ST_NET for t in g] + [(1, t) for t in DEBT_NET_ALL])
OTHER_FIN = ["ProceedsFromPaymentsForOtherFinancingActivities"]
FIT = 0.001                # a combination fits when it leaves less than 0.1% of the section's gross flows unexplained

# partners' stakes in subsidiaries (noncontrolling interests): money in from them, distributions out to them
NCI_IN = [["ProceedsFromMinorityShareholders"], ["ProceedsFromPaymentsToMinorityShareholders"]]
NCI_OUT = [["PaymentsOfDividendsMinorityInterest"], ["PaymentsToMinorityShareholders"],
           ["PaymentsForRepurchaseOfRedeemableNoncontrollingInterest"]]

# long-term debt falling due, as of a 10-K balance sheet date: (bucket, tag); bucket 1 = the next fiscal year
MATURITIES = [(1, "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths"),
              (2, "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo"),
              (3, "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree"),
              (4, "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour"),
              (5, "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive"),
              (6, "LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive")]
INSTANT_CONCEPTS = {t for _, t in MATURITIES}
SHARE_CONCEPTS = {"WeightedAverageNumberOfSharesOutstandingBasic", "CommonStockSharesOutstanding",
                  "WeightedAverageNumberOfShareOutstandingBasicAndDiluted"}

UNREC_FLAG = 0.05          # unreconciled cash over 5% of all cash moved: said on the page
SPLIT = 1.8                # a share count that jumps by this factor in a year: probably a stock split, not dilution


# ------------------------------------------------------------------ reading a figure for a fiscal year or the TTM
def read(per, P):
    """(value, facts, how) of a duration concept for the period P: {"kind": "fy", "end"} or {"kind": "ttm", "end": the
    latest quarter end, "fy": the last fiscal year end before it}."""
    if not per:
        return None, [], None
    if P["kind"] == "fy":
        return W._dur(per, P["end"], True)
    q, fy = P["end"], P["fy"]
    v_fy, used, _ = W._dur(per, fy, True)
    # this fiscal year to date: the figure ending at q that starts the day after the last fiscal year (some filers
    # also tag a trailing twelve months ending at q: Amazon)
    ytd = [(s, f) for (s, e), f in per.items() if e == q and abs((F.d(s) - F.d(fy)).days - 1) <= 7]
    if v_fy is None or not ytd:
        return None, [], None
    s0, f0 = ytd[0]
    span = (F.d(q) - F.d(s0)).days
    prior = [((s, e), f) for (s, e), f in per.items()
             if 357 <= (F.d(q) - F.d(e)).days <= 378 and abs((F.d(e) - F.d(s)).days - span) <= 10]
    if not prior:
        return None, [], None
    _, f1 = min(prior, key=lambda kf: abs((F.d(q) - F.d(kf[0][1])).days - 364))
    return v_fy + f0["val"] - f1["val"], used + [f0, f1], "ttm"


def pick(fx, ev, concepts, P, largest=False):
    """(value, ref, concept): the first candidate tagged for the period (or the largest, as for capital expenditures)."""
    hits = []
    for c in concepts:
        v, used, how = read(fx.get(c), P)
        if v is not None:
            hits.append((v, c, used, how))
            if not largest:
                break
    if not hits:
        return None, None, None
    v, c, used, how = max(hits, key=lambda h: h[0]) if largest else hits[0]
    return v, ev.ref(c, how, used), c


def groups(fx, ev, gs, P, covers=None):
    """Sum of the first tagged candidate of each group: (total or None, [[value, ref], ...])."""
    total, parts = None, []
    for g in gs:
        v, r, c = pick(fx, ev, g, P)
        if v is None:
            continue
        total = (total or 0) + v
        parts.append([v, r])
        if covers and c in covers:
            break
    return total, parts


def one(fx, ev, concepts, P, largest=False):
    """(value, [[value, ref]], concept) of one figure (pick) in the parts format."""
    v, r, c = pick(fx, ev, concepts, P, largest)
    return v, ([[v, r]] if v is not None else []), c


def debt_fit(fx, ev, P, target, scale, optional=()):
    """(net borrowing, parts, optional keys kept) from the fewest debt tags (and optional lines: taxes paid on employee
    shares, which some filers include in their buyback line) that add up to `target` — the financing total minus every
    other line — or None when no combination does."""
    cands = []
    for sign, t in DEBT_TAGS:
        v, used, how = read(fx.get(t), P)
        if v is not None and abs(v) >= 0.5:
            cands.append((sign * v, t, used, how))
    opt = [(v, k) for v, k in optional if v]
    n = len(cands) + len(opt)
    if n > 15:
        return None
    tol = max(FIT * scale, 1e6)
    best = None
    for mask in range(1 << n):
        tot = sum(c[0] for i, c in enumerate(cands) if mask >> i & 1) + \
            sum(o[0] for j, o in enumerate(opt) if mask >> (len(cands) + j) & 1)
        err = abs(target - tot)
        if err > tol:
            continue
        # the simplest reading: each debt tag costs 1 — a breakdown by maturity from the notes 2.5, since the statement
        # line it splits is usually tagged too — and leaving out an optional line 1; then the closest
        cost = sum(2.5 if "Maturing" in c[1] else 1 for i, c in enumerate(cands) if mask >> i & 1) + \
            len(opt) - bin(mask >> len(cands)).count("1")
        key = (cost, err)
        if best is None or key < best[0]:
            best = (key, mask)
    if best is None:
        return None
    mask = best[1]
    parts = [[c[0], ev.ref(c[1], c[3], c[2])] for i, c in enumerate(cands) if mask >> i & 1]
    kept = {o[1] for j, o in enumerate(opt) if mask >> (len(cands) + j) & 1}
    return (sum(v for v, _ in parts) if parts else None), parts, kept


# ------------------------------------------------------------------ one period's sources and uses
def period(fx, ev, P, label):
    """One period's cash moves: items {key: cash effect, + in / − out}; ev {key: [[cash effect, ref], ...]}: the tagged
    figures behind each item (several for a sum: asset sales, shares issued, borrowing, partners)."""
    ocf, e_ocf, _ = one(fx, ev, OCF, P)
    if ocf is None:
        return None
    inv, e_inv, _ = one(fx, ev, INV_TOTAL, P)
    fin, e_fin, _ = one(fx, ev, FIN_TOTAL, P)
    fxe, e_fx, _ = one(fx, ev, FX, P)
    dc, e_dc, c_dc = one(fx, ev, DCASH, P)
    if dc is not None and c_dc in EXCL_FX and fxe is not None:
        dc += fxe                                                  # the change in cash after exchange-rate effects
        e_dc = e_dc + e_fx
    capex, e_capex, _ = one(fx, ev, F.CONCEPTS["capex"], P, largest=True)
    acq, e_acq, _ = one(fx, ev, ACQ, P)
    re_, e_re, _ = one(fx, ev, REALESTATE, P)
    sales, e_sales = groups(fx, ev, SALES, P, covers=SALES_TOTALS)
    bb, e_bb, _ = one(fx, ev, BUYBACK, P)
    div, e_div, c_div = one(fx, ev, DIVIDEND, P)
    wh, e_wh, _ = one(fx, ev, WITHHOLD, P)
    stock, e_stock = groups(fx, ev, STOCK, P, covers=STOCK_TOTALS)
    net_all, e_netall, _ = one(fx, ev, DEBT_NET_ALL, P)
    if net_all is not None:
        borrow, e_borrow, debt = net_all, e_netall, {"net_tag": True}
    else:
        iss, e_iss = groups(fx, ev, DEBT_IN, P)
        rep, e_rep = groups(fx, ev, DEBT_OUT, P)
        st, e_st = groups(fx, ev, DEBT_ST_NET, P)
        borrow = None if iss is None and rep is None and st is None else (iss or 0) - (rep or 0) + (st or 0)
        e_borrow = e_iss + [[-v, r] for v, r in e_rep] + e_st
        debt = {"iss": iss, "rep": rep, "st": st}
    n_in, e_nin = groups(fx, ev, NCI_IN, P)
    # "PaymentsOfDividends" can be every dividend paid, partners' included: then theirs is not taken again
    n_out, e_nout = groups(fx, ev, NCI_OUT[1:] if c_div == "PaymentsOfDividends" else NCI_OUT, P)
    nci = None if n_in is None and n_out is None else (n_in or 0) - (n_out or 0)
    if fin is not None:                     # does the borrowing make the financing section add up? else find what does
        oth, _, _ = pick(fx, ev, OTHER_FIN, P)
        rest = -(bb or 0) - (div or 0) + (stock or 0) + (nci or 0) + (oth or 0)
        scale = abs(fin) + sum(abs(v) for v in (bb, div, wh, stock, nci, oth, borrow) if v)
        if abs(fin - rest + (wh or 0) - (borrow or 0)) > max(FIT * scale, 1e6):
            fit = debt_fit(fx, ev, P, fin - rest, scale, optional=[(-(wh or 0), "withhold")])
            if fit:
                borrow, e_borrow, kept = fit
                debt = {"fit": True, "iss": sum(v for v, _ in e_borrow if v > 0) or None,
                        "rep": -sum(v for v, _ in e_borrow if v < 0) or None}
                if wh and "withhold" not in kept:           # inside another line (the buybacks): not taken twice
                    debt["withhold_inside"] = wh
                    wh, e_wh = None, []
    neg = lambda v: None if v is None else -v
    flip = lambda parts: [[-v, r] for v, r in parts]
    items = {"ocf": ocf, "capex": neg(capex), "realestate": neg(re_), "acq": neg(acq), "sales": sales, "buyback": neg(bb),
             "div": neg(div), "withhold": neg(wh), "stock": stock, "borrow": borrow, "nci": nci, "fx": fxe}
    known_inv = sum(items[k] or 0 for k in ("capex", "realestate", "acq", "sales"))
    known_fin = sum(items[k] or 0 for k in ("buyback", "div", "withhold", "stock", "borrow", "nci"))
    items["inv_other"] = inv - known_inv if inv is not None else None
    items["fin_other"] = fin - known_fin if fin is not None else None
    flows = ocf + (inv if inv is not None else known_inv) + (fin if fin is not None else known_fin) + (fxe or 0)
    if dc is not None:
        items["unrec"] = dc - flows
        items["cash"] = -dc                                         # + drawn from the balance sheet, − added to it
    else:
        items["unrec"] = None
        items["cash"] = -flows                                      # the change in cash the sections add up to
    items = {k: v for k, v in items.items() if v is not None and abs(v) >= 0.5}
    moved = sum(v for v in items.values() if v > 0)
    flags = []
    if abs(items.get("unrec", 0)) > UNREC_FLAG * max(moved, 1):
        flags.append("unrec")
    if dc is None:
        flags.append("no_dcash")
    for k, total in (("inv_other", inv), ("fin_other", fin)):
        if total is None:
            flags.append("no_" + k[:3])
    ev_ = {"ocf": e_ocf, "capex": flip(e_capex), "realestate": flip(e_re), "acq": flip(e_acq), "sales": e_sales,
           "buyback": flip(e_bb), "div": flip(e_div), "withhold": flip(e_wh), "stock": e_stock, "borrow": e_borrow,
           "nci": e_nin + flip(e_nout), "fx": e_fx, "inv": e_inv, "fin": e_fin, "dcash": e_dc}
    out = {"end": P["end"], "kind": P["kind"], "label": label, "items": items, "inv": inv, "fin": fin, "dcash": dc,
           "debt": {k: v for k, v in debt.items() if v is not None}, "flags": flags,
           "ev": {k: v for k, v in ev_.items() if v}}
    if P["kind"] == "ttm":
        out["fy"] = P["fy"]
    return out


# ------------------------------------------------------------------ shares: dilution against buybacks
def _shares_fy(fx, concept, end):
    per = (fx.get("__shares__") or {}).get(concept) or {}
    for k, f in per.items():
        if isinstance(k, tuple) and k[1] == end and 350 <= (F.d(k[1]) - F.d(k[0])).days <= 380:
            return f
    return None


def _shares_at(fx, concept, day):
    per = (fx.get("__shares__") or {}).get(concept) or {}
    days = [k for k in per if not isinstance(k, tuple) and 0 <= (F.d(day) - F.d(k)).days <= 7]
    return per[max(days)] if days else None


def shares(fx, ev, ye, fye):
    """Per fiscal year: diluted and basic weighted-average shares, shares outstanding at year end, share-based
    compensation, buybacks and taxes paid on employee shares (the cash side of dilution)."""
    out = []
    for e in ye[-(KEEP_FY + 1):]:
        P = {"kind": "fy", "end": e}
        row = {"end": e, "label": F.fiscal_year_label(e, fye)[0], "ev": {}}
        both = "WeightedAverageNumberOfShareOutstandingBasicAndDiluted"          # one figure when they are equal
        for key, concept in (("diluted", "WeightedAverageNumberOfDilutedSharesOutstanding"),
                             ("basic", "WeightedAverageNumberOfSharesOutstandingBasic"), ("out", "CommonStockSharesOutstanding")):
            f = _shares_at(fx, concept, e) if key == "out" else _shares_fy(fx, concept, e)
            if not f and key != "out" and _shares_fy(fx, both, e):
                f, concept = _shares_fy(fx, both, e), both
            if f:
                row[key] = f["val"]
                row["ev"][key] = ev.ref(concept, "bal" if key == "out" else "fy", [f], f["end"] if key == "out" else None)
        sbc, r_sbc = W.keyed(fx, ev, "sbc", e, True)
        bb, r_bb, _ = pick(fx, ev, BUYBACK, P)
        wh, r_wh, _ = pick(fx, ev, WITHHOLD, P)
        for key, v, r in (("sbc", sbc, r_sbc), ("bb", bb, r_bb), ("wh", wh, r_wh)):
            if v is not None:
                row[key] = v
                row["ev"][key] = r
        if any(k in row for k in ("diluted", "basic", "out")):
            out.append(row)
    for a, b in zip(out, out[1:]):                                  # a jump this large is a split, not dilution
        for k in ("diluted", "basic", "out"):
            if a.get(k) and b.get(k) and not (1 / SPLIT < b[k] / a[k] < SPLIT):
                b.setdefault("split", []).append(k)
    return out


# ------------------------------------------------------------------ when the debt falls due
def maturities(fx, ev, ye, fye):
    """Long-term debt principal due in each of the next five fiscal years and after, as of the latest 10-K that tags
    it, with cash and short-term investments on the same date."""
    inst = fx.get("__instants__") or {}
    if not ye:
        return None
    recent = [e for e in ye if (F.d(ye[-1]) - F.d(e)).days <= 400]                 # this or the previous 10-K, not older
    days = sorted({k for _, t in MATURITIES for k in inst.get(t) or {} if any(abs((F.d(k) - F.d(e)).days) <= 7 for e in recent)})
    for day in reversed(days):
        buckets = []
        for b, t in MATURITIES:
            f = (inst.get(t) or {}).get(day)
            if f:
                buckets.append([b, f["val"], ev.ref(t, "bal", [f], day)])
        if len(buckets) < 3:
            continue
        cash, r_cash, _ = W.balance(fx, ev, W.BAL["cash"], day)
        sti, r_sti, _ = W.balance(fx, ev, W.BAL["sti"], day)
        ltd, r_ltd, _ = W.balance(fx, ev, W.BAL["ltd"], day)
        label, fy = F.fiscal_year_label(day, fye)
        return {"at": day, "label": label, "fy": fy, "buckets": buckets, "cash": cash, "sti": sti, "ltd": ltd,
                "ev": {k: r for k, r in (("cash", r_cash), ("sti", r_sti), ("ltd", r_ltd)) if r}}
    return None


# ------------------------------------------------------------------ the tab's data
def compute(fx, ev, qe, ye, fye="1231"):
    """{"fy": [periods], "ttm": period or None, "shares": [...], "maturities": {...}} or None."""
    fy = []
    for e in ye[-KEEP_FY:]:
        p = period(fx, ev, {"kind": "fy", "end": e}, F.fiscal_year_label(e, fye)[0])
        if p:
            fy.append(p)
    ttm = None
    if qe and ye and qe[-1] > ye[-1] and (F.d(qe[-1]) - F.d(ye[-1])).days < 330:
        q = qe[-1]
        ttm = period(fx, ev, {"kind": "ttm", "end": q, "fy": ye[-1]}, "TTM to " + F.fiscal_label(q, fye)[0])
    sh = shares(fx, ev, ye, fye)
    mat = maturities(fx, ev, ye, fye)
    if not (fy or ttm or sh or mat):
        return None
    return {"fy": fy, "ttm": ttm, "shares": sh, "maturities": mat}
