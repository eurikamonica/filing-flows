"""Working capital, the net income → operating cash flow bridge, valuation inputs, and where each figure comes from:
the data behind the company page's "Cash & quality" and "Valuation" tabs (with pipeline/quality.py).

Specification: fsa-beta/planning/02_FINANCIAL_ANALYSIS.md and 03_VALUATION.md on the beta/fsa-chatgpt branch (written by
ChatGPT (OpenAI)), applied to each company's SEC XBRL company facts.

  DSO = average trade receivables ÷ revenue × days   (total revenue stands in for credit sales: labelled a proxy)
  DIO = average inventory ÷ cost of revenue × days
  DPO = average trade payables ÷ cost of revenue × days   (cost of revenue stands in for purchases: a proxy)
  CCC = DSO + DIO − DPO;  averages need both the opening and the closing balance, else the measure is left out
  bridge: net income + the adjustments the cash-flow statement discloses = operating cash flow; what the tags do not
          explain is the residual, shown, never filled in
Every figure carries its evidence: the XBRL concept, how the period was read (a three-month fact, a year-to-date
difference, a full year, a balance) and the filings the facts come from.
"""
from . import facts as F

# balance sheet items: key -> candidate concepts, best first (one concept gives both the opening and closing balance)
BAL = {
    "ar": ["AccountsReceivableNetCurrent", "AccountsReceivableNet", "ReceivablesNetCurrent"],
    "inv": ["InventoryNet", "InventoryNetOfAllowancesCustomerAdvancesAndProgressBillings"],
    "ap": ["AccountsPayableCurrent", "AccountsPayableTradeCurrent"],
    "ap_accr": ["AccountsPayableAndAccruedLiabilitiesCurrent"],          # payables with accrued liabilities: a proxy
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "Cash", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "sti": ["ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
    "ltd": ["LongTermDebt", "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities"],   # with current maturities
    "ltd_nc": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"],
    "ltd_c": ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"],
    "debt_c": ["DebtCurrent"],                                          # all short-term debt, current maturities included
    "stb": ["ShortTermBorrowings", "CommercialPaper"],
    "nci": ["MinorityInterest"],
    "pref": ["PreferredStockValue"],
}
INSTANT_CONCEPTS = {c for v in BAL.values() for c in v}
SHARE_CONCEPTS = {"WeightedAverageNumberOfDilutedSharesOutstanding", "EntityCommonStockSharesOutstanding"}

# the cash-flow statement's reconciliation of net income to operating cash flow. (key, label, cash effect of a positive
# fact, candidate concepts: the first one tagged for the period is used, so one group never counts a figure twice)
NONCASH = [
    ("da", "Depreciation and amortization", +1, None),                  # facts.CONCEPTS["da"] (cash-flow statement first)
    ("sbc", "Share-based compensation", +1, None),
    ("dtax", "Deferred income taxes", +1, ["DeferredIncomeTaxExpenseBenefit", "DeferredIncomeTaxesAndTaxCredits"]),
    ("impair", "Impairments", +1, ["GoodwillAndIntangibleAssetImpairment", "AssetImpairmentCharges", "GoodwillImpairmentLoss",
                                   "ImpairmentOfLongLivedAssetsHeldForUse", "ImpairmentOfIntangibleAssetsExcludingGoodwill"]),
    ("gain_inv", "Gains on investments", -1, ["GainLossOnInvestments", "GainLossOnSaleOfInvestments"]),
    ("gain_dis", "Gains on disposals", -1, ["GainLossOnDispositionOfAssets1", "GainLossOnDispositionOfAssets",
                                           "GainLossOnSaleOfPropertyPlantEquipment"]),
    ("other_nc", "Other non-cash items", -1, ["OtherNoncashIncomeExpense"]),
]
# working capital: an increase in an asset uses cash (−), an increase in a liability provides it (+)
WC = [
    ("d_ar", "Receivables", -1, ["IncreaseDecreaseInAccountsReceivable", "IncreaseDecreaseInReceivables",
                                 "IncreaseDecreaseInAccountsAndOtherReceivables", "IncreaseDecreaseInAccountsReceivableAndOtherOperatingAssets"]),
    ("d_inv", "Inventories", -1, ["IncreaseDecreaseInInventories", "IncreaseDecreaseInRetailRelatedInventories",
                                  "IncreaseDecreaseInInventoriesAndOtherOperatingAssets"]),
    ("d_ap", "Payables", +1, ["IncreaseDecreaseInAccountsPayable", "IncreaseDecreaseInAccountsPayableTrade",
                              "IncreaseDecreaseInAccountsPayableAndAccruedLiabilities",
                              "IncreaseDecreaseInAccountsPayableAndOtherOperatingLiabilities"]),
    ("d_accr", "Accrued liabilities", +1, ["IncreaseDecreaseInAccruedLiabilitiesAndOtherOperatingLiabilities",
                                           "IncreaseDecreaseInAccruedLiabilities", "IncreaseDecreaseInOtherAccruedLiabilities"]),
    ("d_emp", "Employee-related liabilities", +1, ["IncreaseDecreaseInEmployeeRelatedLiabilities"]),
    ("d_contract", "Deferred revenue", +1, ["IncreaseDecreaseInContractWithCustomerLiability", "IncreaseDecreaseInDeferredRevenue"]),
    ("d_casset", "Contract assets", -1, ["IncreaseDecreaseInContractWithCustomerAsset"]),
    ("d_oassets", "Prepaid and other assets", -1, ["IncreaseDecreaseInPrepaidDeferredExpenseAndOtherAssets",
                                                   "IncreaseDecreaseInOtherOperatingAssets", "IncreaseDecreaseInOtherCurrentAssets",
                                                   "IncreaseDecreaseInPrepaidExpense"]),
    ("d_oliab", "Other liabilities", +1, ["IncreaseDecreaseInOtherOperatingLiabilities", "IncreaseDecreaseInOtherCurrentLiabilities",
                                          "IncreaseDecreaseInOtherNoncurrentLiabilities"]),
    ("d_tax", "Income taxes payable", +1, ["IncreaseDecreaseInIncomeTaxesPayableNetOfIncomeTaxesReceivable",
                                           "IncreaseDecreaseInAccruedIncomeTaxesPayable", "IncreaseDecreaseInIncomeTaxes",
                                           "IncreaseDecreaseInAccruedTaxesPayable"]),
    ("d_onet", "Other operating capital", -1, ["IncreaseDecreaseInOtherOperatingCapitalNet"]),
]
# a combined tag already contains the narrower group: then that group is skipped
COVERS = {"IncreaseDecreaseInAccountsPayableAndAccruedLiabilities": {"d_accr"},
          "IncreaseDecreaseInAccountsPayableAndOtherOperatingLiabilities": {"d_accr", "d_oliab"},
          "IncreaseDecreaseInAccruedLiabilitiesAndOtherOperatingLiabilities": {"d_oliab"},
          "IncreaseDecreaseInAccountsReceivableAndOtherOperatingAssets": {"d_oassets"},
          "IncreaseDecreaseInInventoriesAndOtherOperatingAssets": {"d_oassets"}}


LABELS = {k: label for k, label, _, _ in NONCASH + WC}


def compact(o):
    """Round for publishing: amounts to whole dollars, ratios and days to 3 decimals."""
    if isinstance(o, float):
        return int(round(o)) if abs(o) >= 1000 else round(o, 3)
    if isinstance(o, dict):
        return {k: compact(v) for k, v in o.items()}
    if isinstance(o, list):
        return [compact(v) for v in o]
    return o


class Evidence:
    """Compact provenance: concepts and filings listed once, figures point at them by index."""

    def __init__(self, fx):
        self.fx, self.concepts, self.filings, self._c, self._f = fx, [], [], {}, {}

    def _ci(self, concept):
        if concept not in self._c:
            self._c[concept] = len(self.concepts)
            self.concepts.append([concept, (self.fx.get("__labels__") or {}).get(concept) or concept])
        return self._c[concept]

    def _fi(self, f):
        k = f.get("accn")
        if k not in self._f:
            self._f[k] = len(self.filings)
            self.filings.append([k, f.get("form"), f.get("filed")])
        return self._f[k]

    def ref(self, concept, how, facts, day=None):
        """[concept index, how the figure was read, [filing indexes]] (+ the balance date for a balance)."""
        r = [self._ci(concept), how, [self._fi(f) for f in facts if f]]
        return r + [day] if day else r

    def out(self):
        return {"concepts": self.concepts, "filings": self.filings}


def _dur(per, end, annual):
    """(value, facts, how) of a duration concept for the quarter or fiscal year ending `end` (see facts._quarter_from)."""
    if not per:
        return None, [], None
    if annual:
        for (s, e), f in per.items():
            if e == end and 350 <= (F.d(e) - F.d(s)).days <= 380:
                return f["val"], [f], "fy"
        return None, [], None
    at_end = [(s, f) for (s, e), f in per.items() if e == end]
    for s, f in at_end:
        if 75 <= (F.d(end) - F.d(s)).days <= 100:
            return f["val"], [f], "3m"
    if not at_end:
        return None, [], None
    s0, f0 = min(at_end, key=lambda x: x[0])
    for (s, e), f in per.items():
        if s == s0 and e != end and 75 <= (F.d(end) - F.d(e)).days <= 105:
            return f0["val"] - f["val"], [f0, f], "ytd"
    return None, [], None


def keyed(fx, ev, key, end, annual):
    """A facts.CONCEPTS figure with its evidence: (value, ref) — the same value facts.value gives."""
    v = F.value(fx, key, end, annual)
    if v is None:
        return None, None
    c = F.source(fx, key, end, annual)
    _, used, how = _dur(fx.get(c), end, annual) if c else (None, [], None)
    return v, ev.ref(c, how or ("fy" if annual else "3m"), used) if c else None


def first(fx, ev, concepts, end, annual):
    """(value, ref, concept) of the first candidate tagged for the period."""
    for c in concepts:
        v, used, how = _dur(fx.get(c), end, annual)
        if v is not None:
            return v, ev.ref(c, how, used), c
    return None, None, None


def balance(fx, ev, concepts, day, lo=0, hi=7):
    """(value, ref, concept) of the candidate with the latest balance on `day` or up to `hi` days before (a week by
    default: 52/53-week years); among equally recent ones, the first candidate."""
    inst = fx.get("__instants__") or {}
    best = None
    for i, c in enumerate(concepts):
        per = inst.get(c) or {}
        k = day if day in per else max((x for x in per if lo <= (F.d(day) - F.d(x)).days <= hi), default=None)
        if k and (best is None or k > best[0]):
            best = (k, c)
    if not best:
        return None, None, None
    k, c = best
    f = inst[c][k]
    return f["val"], ev.ref(c, "bal", [f], k), c


def pair(fx, ev, concepts, start, end):
    """Opening and closing balance from ONE concept (the first with both), else the closing balance alone."""
    inst = fx.get("__instants__") or {}
    for c in concepts:
        if start and inst.get(c):
            o, ro, _ = balance(fx, ev, [c], start)
            cl, rc, _ = balance(fx, ev, [c], end)
            if o is not None and cl is not None:
                return o, cl, ro, rc, c
    cl, rc, c = balance(fx, ev, concepts, end)
    return None, cl, None, rc, c


def _has_inventory(fx, end):
    inst = fx.get("__instants__") or {}
    return any(F.d(end).toordinal() - F.d(k).toordinal() <= 800 for c in BAL["inv"] for k in inst.get(c) or {})


def working_capital(fx, ev, end, prev, annual):
    rev, r_rev = keyed(fx, ev, "revenue", end, annual)
    cor, r_cor = keyed(fx, ev, "cor", end, annual)
    days = (F.d(end) - F.d(prev)).days if prev else (364 if annual else 91)
    ar_o, ar_c, r_aro, r_arc, _ = pair(fx, ev, BAL["ar"], prev, end)
    inv_o, inv_c, r_invo, r_invc, _ = pair(fx, ev, BAL["inv"], prev, end)
    ap_o, ap_c, r_apo, r_apc, _ = pair(fx, ev, BAL["ap"], prev, end)
    ap_proxy = False
    if ap_c is None:
        ap_o, ap_c, r_apo, r_apc, _ = pair(fx, ev, BAL["ap_accr"], prev, end)
        ap_proxy = ap_c is not None
    has_inv = _has_inventory(fx, end)
    avg = lambda a, b: (a + b) / 2 if a is not None and b is not None else None
    dso = avg(ar_o, ar_c) / rev * days if avg(ar_o, ar_c) is not None and rev and rev > 0 else None
    dio = avg(inv_o, inv_c) / cor * days if has_inv and avg(inv_o, inv_c) is not None and cor and cor > 0 else None
    dpo = avg(ap_o, ap_c) / cor * days if avg(ap_o, ap_c) is not None and cor and cor > 0 else None
    ccc = None
    if dso is not None and dpo is not None and (dio is not None or not has_inv):
        ccc = dso + (dio or 0) - dpo
    refs = {k: r for k, r in (("rev", r_rev), ("cor", r_cor), ("ar_o", r_aro), ("ar_c", r_arc), ("inv_o", r_invo),
                              ("inv_c", r_invc), ("ap_o", r_apo), ("ap_c", r_apc)) if r}
    return {"rev": rev, "cor": cor, "days": days, "ar_o": ar_o, "ar_c": ar_c, "inv_o": inv_o, "inv_c": inv_c,
            "ap_o": ap_o, "ap_c": ap_c, "ap_proxy": ap_proxy, "has_inv": has_inv,
            "dso": dso, "dio": dio, "dpo": dpo, "ccc": ccc}, refs


def bridge(fx, ev, end, annual):
    """Net income → operating cash flow from the disclosed adjustments; the residual is what they do not explain."""
    pl, r_pl = keyed(fx, ev, "pl", end, annual)
    ni, r_ni = (pl, r_pl) if pl is not None else keyed(fx, ev, "ni", end, annual)
    ocf, r_ocf = keyed(fx, ev, "ocf", end, annual)
    if ni is None or ocf is None:
        return None
    items, skip = [], set()
    for key, label, sign, cands in NONCASH + WC:
        if key in skip:
            continue
        if cands is None:
            v, r = keyed(fx, ev, key, end, annual)
            c = None
        else:
            v, r, c = first(fx, ev, cands, end, annual)
        if v is None:
            continue
        skip |= COVERS.get(c, set())
        items.append([key, sign * v, r])                     # labels: LABELS (the page has its own copy)
    explained = ni + sum(x[1] for x in items)
    return {"start": ni, "basis": "pl" if pl is not None else "ni", "items": items, "ocf": ocf,
            "residual": ocf - explained, "ref": {"start": r_pl if pl is not None else r_ni, "ocf": r_ocf}}


def _ttm_ends(qe):
    """The last four consecutive quarter ends (each 75–105 days after the one before), or None."""
    if len(qe) < 4:
        return None
    last = qe[-4:]
    ok = all(75 <= (F.d(b) - F.d(a)).days <= 105 for a, b in zip(last, last[1:]))
    return last if ok else None


def shares(fx, ev, end):
    """Diluted weighted-average shares for the latest quarter (or year), and the cover page's shares outstanding."""
    sh = fx.get("__shares__") or {}
    out = {}
    per = sh.get("WeightedAverageNumberOfDilutedSharesOutstanding") or {}
    cands = [(k, f) for k, f in per.items() if isinstance(k, tuple) and k[1] <= end]
    q = [(k, f) for k, f in cands if 75 <= (F.d(k[1]) - F.d(k[0])).days <= 100]
    pick = max(q or cands, key=lambda kf: (kf[0][1], -(F.d(kf[0][1]) - F.d(kf[0][0])).days), default=None)
    if pick:
        (s, e), f = pick
        out["diluted"] = f["val"]
        out["diluted_end"] = e
        out["r_diluted"] = ev.ref("WeightedAverageNumberOfDilutedSharesOutstanding", "3m" if 75 <= (F.d(e) - F.d(s)).days <= 100 else "fy", [f])
    per = sh.get("EntityCommonStockSharesOutstanding") or {}
    days = [k for k in per if not isinstance(k, tuple)]
    if days:
        k = max(days)
        out["outstanding"], out["outstanding_at"] = per[k]["val"], k
        out["r_outstanding"] = ev.ref("EntityCommonStockSharesOutstanding", "bal", [per[k]], k)
    return out


def valuation_inputs(fx, ev, qe, ye):
    """Trailing-twelve-month operating figures and the latest balance sheet: the forward DCF's starting point."""
    ttm = _ttm_ends(qe)
    keys = ("revenue", "oi", "pretax", "tax", "da", "capex", "sbc", "ocf")
    out, refs = {}, {}
    if ttm:
        out["basis"], out["end"], out["periods"] = "ttm", ttm[-1], ttm
        for k in keys:
            vals = [keyed(fx, ev, k, e, False) for e in ttm]
            if all(v is not None for v, _ in vals):
                out[k] = sum(v for v, _ in vals)
                refs[k] = [r for _, r in vals]
    elif ye:
        out["basis"], out["end"], out["periods"] = "fy", ye[-1], [ye[-1]]
        for k in keys:
            v, r = keyed(fx, ev, k, ye[-1], True)
            if v is not None:
                out[k], refs[k] = v, [r]
    if not out.get("revenue"):
        return None
    end = out["end"]
    # the latest balance on or before the period end: some filers tag a balance only in the 10-K (shown with its date)
    bal = {k: balance(fx, ev, BAL[k], end, 0, 400) for k in ("cash", "sti", "ltd", "ltd_nc", "ltd_c", "debt_c", "stb", "nci", "pref")}
    v = lambda k: bal[k][0]
    for k, (val, r, _) in bal.items():
        if val is not None:
            out["b_" + k], refs["b_" + k] = val, [r]
    out["bal_dates"] = sorted({r[3] for _, r, _ in bal.values() if r and len(r) > 3})
    # debt: total long-term debt (current maturities included), else noncurrent + current; short-term borrowings and
    # commercial paper only when no all-in current debt figure already includes them
    if v("ltd") is not None:
        debt, how = v("ltd") + (v("stb") or 0), "long-term debt incl. current maturities" + (" + short-term borrowings" if v("stb") else "")
    elif v("ltd_nc") is not None:
        cur = v("debt_c") if v("debt_c") is not None else (v("ltd_c") or 0) + (v("stb") or 0)
        debt, how = v("ltd_nc") + cur, "noncurrent + current debt"
    else:
        debt, how = v("debt_c") if v("debt_c") is not None else v("stb"), "short-term debt only"
    out["debt"], out["debt_how"] = debt or 0, how if debt else "no debt tagged"
    out["cash_all"] = (v("cash") or 0) + (v("sti") or 0)
    out["claims"] = (v("nci") or 0) + (v("pref") or 0)
    sh = shares(fx, ev, end)
    for k in ("diluted", "diluted_end", "outstanding", "outstanding_at"):
        if k in sh:
            out[k] = sh[k]
    for k in ("r_diluted", "r_outstanding"):
        if k in sh:
            refs[k[2:]] = [sh[k]]
    out["refs"] = refs
    return out
