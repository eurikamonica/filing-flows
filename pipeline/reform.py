"""The balance sheet reformulated into operating and financing activities, and the returns that follow from it (RNOA,
net borrowing cost, financial leverage) — the company page's "Balance sheet" workbench.

  net operating assets   NOA = operating assets − operating liabilities
  net financial oblig.   NFO = financial obligations − financial assets      (negative: net financial assets)
  NOA − NFO = common equity + minority interests                           (the balance check)
  net financial expense  NFE = (interest expense − interest income) × (1 − tax rate)
  operating income       OI  = net income (incl. minority interests) + NFE   (after tax)
  RNOA = OI ÷ average NOA = profit margin × asset turnover;  NBC = NFE ÷ average NFO;  FLEV = average NFO ÷ average equity
  ROE  = RNOA + FLEV × (RNOA − NBC)

Each balance-sheet line comes from a standard tag with a default class and the reason for it; the reader can move
any line between operating and financing in the browser and every figure is recomputed there. What the tagged lines
leave of total assets or total liabilities is a line of its own ("other, not tagged separately"), so the totals always
match the filing and nothing is filled in. Each line's candidates are US GAAP tags, then IFRS ones (ifrs-full: foreign filers' 20-Fs, European
annual reports), so an IFRS balance sheet reads into the same lines. When the balance sheet tags its current assets (liabilities) at every year
end, that rest is split into a current and a non-current line, and each line says which section it is in ("cur"; a
lease line has a part in both, its current part in "cv") — the company page's balance sheet in blocks draws the
sections. A negative rest means a line above is also inside another one (a detail from the notes counted twice). Each
line carries an empty "suggest" for a classification read from the filing's notes later (the local model).
"""
from . import facts as F
from . import fsa as W

KEEP = 5                                # fiscal years of returns (one more balance sheet for the opening balances)

# (key, side, name, default class, reason, [groups of candidate tags]): one tag per group, the first tagged
LINES = [
    ("cash", "a", "Cash and cash equivalents", "fin", "Cash can repay debt or be paid out: a financial asset. Cash needed to run the business is operating; move it if you know how much.",
     [["CashAndCashEquivalentsAtCarryingValue", "Cash", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
       "CashAndCashEquivalents"]]),
    ("sti", "a", "Short-term investments", "fin", "Securities held for the cash they will return: financial.",
     [["ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
       "OtherCurrentFinancialAssets", "CurrentFinancialAssetsAtFairValueThroughProfitOrLoss", "ShorttermDepositsNotClassifiedAsCashEquivalents"]]),
    ("lti", "a", "Long-term investments", "fin", "Securities held for their return: financial. A stake in another business that is part of operations is operating.",
     [["MarketableSecuritiesNoncurrent", "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent", "LongTermInvestments",
       "OtherLongTermInvestments", "EquitySecuritiesFVNINoncurrent", "EquitySecuritiesWithoutReadilyDeterminableFairValueAmount",
       "OtherNoncurrentFinancialAssets", "NoncurrentFinancialAssetsAvailableforsale", "NoncurrentFinancialAssets"]]),
    ("resale", "a", "Resale agreements and securities borrowed", "fin", "Cash lent against securities: financial.",
     [["SecuritiesPurchasedUnderAgreementsToResell", "FederalFundsSoldAndSecuritiesPurchasedUnderAgreementsToResell"], ["SecuritiesBorrowed"]]),
    ("secs", "a", "Debt securities", "fin", "Bonds held for sale or to maturity: financial.",
     [["AvailableForSaleSecuritiesDebtSecurities", "DebtSecuritiesAvailableForSaleExcludingAccruedInterest"],
      ["HeldToMaturitySecurities", "DebtSecuritiesHeldToMaturityAmortizedCostAfterAllowanceForCreditLoss",
       "DebtSecuritiesHeldToMaturityExcludingAccruedInterestAfterAllowanceForCreditLoss"]]),
    ("eqsec", "a", "Equity securities", "fin", "Shares held for their return: financial.",
     [["EquitySecuritiesFvNi", "MarketableSecuritiesEquitySecurities"]]),
    ("loans", "a", "Loans, net of the allowance", "op", "Lending is a bank's business: operating.",
     [["LoansAndLeasesReceivableNetReportedAmount", "FinancingReceivableExcludingAccruedInterestAfterAllowanceForCreditLoss",
       "LoansAndLeasesReceivableNetOfDeferredIncome", "NotesReceivableNet", "LoansAndAdvancesToCustomers"]]),
    ("ar", "a", "Receivables", "op", "Owed by customers for sales: operating.",
     [["AccountsReceivableNetCurrent", "ReceivablesNetCurrent", "AccountsReceivableNet",
       "TradeAndOtherCurrentReceivables", "CurrentTradeReceivables"]]),
    ("orec", "a", "Other receivables", "op", "Owed by suppliers and others, not by customers (vendor non-trade receivables): operating.",
     [["NontradeReceivablesCurrent"]]),
    ("inv", "a", "Inventory", "op", "Goods held for sale: operating.", [["InventoryNet", "Inventories"]]),
    ("oca", "a", "Prepaid and other current assets", "op", "Prepayments and other operating items: operating.",
     [["PrepaidExpenseAndOtherAssetsCurrent", "OtherAssetsCurrent", "PrepaidExpenseCurrent",
       "OtherCurrentAssets", "OtherCurrentNonfinancialAssets"]]),
    ("ppe", "a", "Property, plant and equipment", "op", "Assets used to produce and sell: operating.",
     [["PropertyPlantAndEquipmentNet", "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
       "PropertyPlantAndEquipment", "PropertyPlantAndEquipmentIncludingRightofuseAssets"]]),
    ("rou", "a", "Operating lease right-of-use assets", "op", "Leased stores, offices and equipment used in the business: operating.", [["OperatingLeaseRightOfUseAsset", "RightofuseAssets"]]),
    ("invprop", "a", "Investment property", "op", "Buildings and land held to rent out (IFRS): the business of a property company, operating.",
     [["InvestmentProperty"]]),
    ("gw", "a", "Goodwill", "op", "Paid for acquired businesses: operating.", [["Goodwill"]]),
    ("intang", "a", "Intangible assets", "op", "Acquired technology, brands and customer relationships: operating.",
     [["IntangibleAssetsNetExcludingGoodwill", "FiniteLivedIntangibleAssetsNet", "IntangibleAssetsOtherThanGoodwill"]]),
    ("eqm", "a", "Equity-method investments", "op", "Stakes in associated businesses, usually part of operations. Financial if held as an investment.", [["EquityMethodInvestments", "InvestmentAccountedForUsingEquityMethod",
       "InvestmentsInAssociatesAccountedForUsingEquityMethod"]]),
    ("dta", "a", "Deferred tax assets", "op", "Taxes on operating income paid ahead: operating.", [["DeferredIncomeTaxAssetsNet", "DeferredTaxAssetsNetNoncurrent", "DeferredTaxAssets"]]),
    ("onca", "a", "Other non-current assets", "op", "Other long-term operating items: operating.",
     [["OtherAssetsNoncurrent", "DeferredIncomeTaxesAndOtherAssetsNoncurrent", "OtherNoncurrentAssets", "OtherNoncurrentNonfinancialAssets"]]),
    ("deposits", "l", "Deposits", "op", "Customers' money a bank holds is its business: operating.", [["Deposits", "DepositsFromCustomers"]]),
    ("repo", "l", "Repurchase agreements", "fin", "Cash borrowed against securities: financial.",
     [["SecuritiesSoldUnderAgreementsToRepurchase", "FederalFundsPurchasedAndSecuritiesSoldUnderAgreementsToRepurchase"]]),
    ("ap", "l", "Accounts payable", "op", "Owed to suppliers for operations: operating.",
     [["AccountsPayableCurrent", "AccountsPayableTradeCurrent", "AccountsPayableAndAccruedLiabilitiesCurrent",
       "AccountsPayableAndAccruedLiabilitiesCurrentAndNoncurrent", "TradeAndOtherCurrentPayables", "TradeAndOtherCurrentPayablesToTradeSuppliers"]]),
    ("accr", "l", "Accrued liabilities", "op", "Services and other costs not yet paid: operating.", [["AccruedLiabilitiesCurrent", "AccrualsClassifiedAsCurrent"]]),
    ("comp", "l", "Accrued compensation", "op", "Wages, bonuses and benefits earned but not yet paid: operating.",
     [["EmployeeRelatedLiabilitiesCurrent"]]),
    ("defrev", "l", "Deferred revenue", "op", "Customers' payments ahead of delivery: operating.",
     [["ContractWithCustomerLiabilityCurrent", "DeferredRevenueCurrent", "CurrentContractLiabilities"]]),
    ("taxp", "l", "Income taxes payable", "op", "Taxes on operating income: operating.", [["AccruedIncomeTaxesCurrent", "TaxesPayableCurrent", "CurrentTaxLiabilitiesCurrent", "CurrentTaxLiabilities"]]),
    ("ocl", "l", "Other current liabilities", "op", "Other operating items due within a year: operating.", [["OtherLiabilitiesCurrent", "OtherCurrentLiabilities", "OtherCurrentNonfinancialLiabilities"]]),
    ("std", "l", "Short-term debt and commercial paper", "fin", "Borrowed money: financial.",
     [["DebtCurrent", "CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings"],
      ["ShortTermBorrowings", "CommercialPaper", "OtherShortTermBorrowings", "NotesPayableCurrent", "ShorttermBorrowings"]]),
    ("ltdc", "l", "Current portion of long-term debt", "fin", "Borrowed money falling due within a year: financial.",
     [["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent", "CurrentPortionOfLongtermBorrowings"]]),
    ("ltd", "l", "Long-term debt", "fin", "Bonds, notes and loans: financial.",
     [["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations", "LongTermNotesPayable", "LongTermNotesAndLoans",
       "SeniorLongTermNotes", "ConvertibleNotesPayable", "OtherLongTermDebtNoncurrent", "LongTermLineOfCredit",
       "UnsecuredDebt", "SeniorNotes", "NotesPayable", "SecuredDebt", "LongtermBorrowings", "NoncurrentPortionOfNoncurrentBorrowings"]]),
    ("flease", "l", "Finance lease liabilities", "fin", "Leases that work like a loan for the asset: financial.",
     [["FinanceLeaseLiabilityNoncurrent"], ["FinanceLeaseLiabilityCurrent"]]),
    ("olease", "l", "Operating lease liabilities", "op", "Rent owed on leases used in the business: operating by default. Move it to financing to treat leases like debt (if the balance sheet has no lease line of its own, they sit inside other liabilities).",
     [["OperatingLeaseLiabilityNoncurrent"], ["OperatingLeaseLiabilityCurrent"]]),
    ("lease", "l", "Lease liabilities", "fin", "IFRS 16 puts every lease on the balance sheet like a loan for the asset: financial.",
     [["NoncurrentLeaseLiabilities"], ["CurrentLeaseLiabilities"]]),
    ("prov", "l", "Provisions", "op", "Obligations of uncertain timing or amount (warranties, restructuring, legal claims): operating.",
     [["NoncurrentProvisions", "OtherLongtermProvisions"], ["CurrentProvisions", "OtherShorttermProvisions"]]),
    ("taxpn", "l", "Income taxes payable, non-current", "op", "Taxes on operating income due after a year (often uncertain tax positions): operating.",
     [["AccruedIncomeTaxesNoncurrent"]]),
    ("dtl", "l", "Deferred tax liabilities", "op", "Taxes on operating income deferred: operating.", [["DeferredIncomeTaxLiabilitiesNet", "DeferredTaxLiabilitiesNoncurrent", "DeferredTaxLiabilities"]]),
    ("pension", "l", "Pension and retiree benefits", "op", "Promised to employees for their work: operating (some analysts treat the unfunded part as debt).",
     [["DefinedBenefitPensionPlanLiabilitiesNoncurrent", "PensionAndOtherPostretirementDefinedBenefitPlansLiabilitiesNoncurrent"]]),
    ("defrevn", "l", "Deferred revenue, non-current", "op", "Customers' payments for later years: operating.",
     [["ContractWithCustomerLiabilityNoncurrent", "DeferredRevenueNoncurrent", "NoncurrentContractLiabilities"]]),
    ("oncl", "l", "Other non-current liabilities", "op", "Other long-term operating obligations: operating.",
     [["OtherLiabilitiesNoncurrent", "DeferredIncomeTaxesAndOtherLiabilitiesNoncurrent", "OtherNoncurrentLiabilities",
       "OtherNoncurrentNonfinancialLiabilities"]]),
]
# a combined tag that already contains another line: that line is skipped
COVERS = {"AccountsPayableAndAccruedLiabilitiesCurrent": {"accr"}, "AccountsPayableAndAccruedLiabilitiesCurrentAndNoncurrent": {"accr"},
          "DebtCurrent": {"ltdc"}, "CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings": {"ltdc"},
          "LongTermDebtAndCapitalLeaseObligations": {"flease"},
          "PropertyPlantAndEquipmentIncludingRightofuseAssets": {"rou"}}    # IFRS 16: the leased assets inside PP&E
ALL_CURRENT_DEBT = {"DebtCurrent", "CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings"}   # nothing else in that line
# The current section of a classified balance sheet (the other lines are non-current). A line of two groups,
# non-current then current, has a part in each: its current part is published as "cv".
CURRENT = {"cash", "sti", "ar", "orec", "inv", "oca", "ap", "accr", "comp", "defrev", "taxp", "ocl", "std", "ltdc"}
SPLIT = {"flease": (False, True), "olease": (False, True), "lease": (False, True), "prov": (False, True)}
# Read only from a side without current and non-current sections (banks, insurers, brokers): on a classified balance
# sheet these tags are details in the notes of the lines above, so they would count twice.
UNCLASSIFIED = {"resale", "secs", "eqsec", "loans", "deposits", "repo"}
TOTALS = {"assets": ["Assets"], "liab": ["Liabilities"], "le": ["LiabilitiesAndStockholdersEquity", "EquityAndLiabilities"],
          "ca": ["AssetsCurrent", "CurrentAssets"], "cl": ["LiabilitiesCurrent", "CurrentLiabilities"],
          "cse": ["StockholdersEquity", "EquityAttributableToOwnersOfParent"], "nci": ["MinorityInterest", "NoncontrollingInterests"],
          "eq_all": ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "Equity"],
          "temp": ["RedeemableNoncontrollingInterestEquityCarryingAmount", "TemporaryEquityCarryingAmountAttributableToParent"],
          "ltd_all": ["LongTermDebt", "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities"]}
INSTANT_CONCEPTS = {t for *_, gs in LINES for g in gs for t in g} | {t for v in TOTALS.values() for t in v}
FLOWS = {"int_exp": ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt", "InterestAndDebtExpense", "FinanceCosts"],
         "int_inc": ["InvestmentIncomeInterest", "InterestIncomeOther", "InvestmentIncomeInterestAndDividend", "FinanceIncome"]}
TAX_RATE = 0.21            # US federal statutory rate, for the tax shield on net interest (editable on the page)
OTHER_A = ("oth_a", "a", "Other assets, not tagged separately", "op",
           "Total assets minus the lines above: assets the company tags its own way. Operating by default.")
OTHER_L = ("oth_l", "l", "Other liabilities, not tagged separately", "op",
           "Total liabilities minus the lines above: liabilities the company tags its own way. Operating by default.")
# what the lines leave of each section, when the balance sheet tags its current totals at every year end
OTHER_SECTIONS = {
    "a": [("oth_ca", "ca", "Other current assets, not tagged separately",
           "Total current assets minus the current lines above: current assets the company tags its own way. Operating by default."),
          ("oth_nca", "nca", "Other non-current assets, not tagged separately",
           "Non-current assets (total assets − current assets) minus the non-current lines above: assets the company tags its own way. Operating by default.")],
    "l": [("oth_cl", "cl", "Other current liabilities, not tagged separately",
           "Total current liabilities minus the current lines above: current liabilities the company tags its own way. Operating by default."),
          ("oth_ncl", "ncl", "Other non-current liabilities, not tagged separately",
           "Non-current liabilities (total liabilities − current liabilities) minus the non-current lines above: liabilities the company tags its own way. Operating by default.")]}


def _bal(fx, ev, tags, day):
    v, r, c = W.balance(fx, ev, tags, day, 0, 7)
    return v, r, c


def compute(fx, ev, ye, fye="1231"):
    """{"ends", "labels", "lines": [...], "totals": {...}, "flows": [...], "tax_rate", "suggest"} or None."""
    ends = [e for e in ye[-(KEEP + 1):] if _bal(fx, ev, TOTALS["assets"], e)[0] is not None]
    if len(ends) < 2:
        return None
    lines, totals, tev = [], {k: [] for k in TOTALS}, {k: [] for k in TOTALS}
    for k, tags in TOTALS.items():
        for e in ends:
            v, r, _ = _bal(fx, ev, tags, e)
            totals[k].append(v)
            tev[k].append(r)
    # total liabilities when not tagged: liabilities and equity − equity (with minority interests) − temporary equity;
    # shareholders' equity when only the total with minority interests is tagged (Caterpillar, Visa, AT&T)
    for i, e in enumerate(ends):
        if totals["cse"][i] is None and totals["eq_all"][i] is not None:
            totals["cse"][i] = totals["eq_all"][i] - (totals["nci"][i] or 0)
            tev["cse"][i] = tev["eq_all"][i]
        if totals["liab"][i] is None and totals["le"][i] is not None:
            eq = totals["eq_all"][i] if totals["eq_all"][i] is not None else (totals["cse"][i] or 0) + (totals["nci"][i] or 0)
            totals["liab"][i] = totals["le"][i] - eq - (totals["temp"][i] or 0)
    # a side is classified when its current total is tagged at every year end: then what the lines leave is split
    # into its current and non-current part, and the lines of unclassified balance sheets are not read
    classified = {"a": all(v is not None for v in totals["ca"]), "l": all(v is not None for v in totals["cl"])}
    skipped = set()
    for key, side, name, cls, why, groups in LINES:
        if key in skipped or (key in UNCLASSIFIED and classified[side]):
            continue
        vals, refs, tags, cur = [], [], [], []
        for e in ends:
            tot, rs, used, cv = None, [], None, None
            for gi, g in enumerate(groups):
                v, r, c = _bal(fx, ev, g, e)
                if v is not None:
                    tot = (tot or 0) + v
                    if key in SPLIT and SPLIT[key][gi]:
                        cv = (cv or 0) + v
                    rs.append(r)
                    used = c
                    skipped |= COVERS.get(c, set())
                    if c in ALL_CURRENT_DEBT:                        # all current debt: nothing else in this line
                        break
            vals.append(tot)
            refs.append(rs)
            tags.append(used)
            cur.append(cv)
        if key == "ltd" and all(v is None for v in vals):           # only the total with current maturities is tagged
            vals, refs, cur = [], [], []
            for e in ends:
                v, r, _ = _bal(fx, ev, TOTALS["ltd_all"], e)
                vals.append(v)
                refs.append([r] if r else [])
                cur.append(_bal(fx, ev, ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"], e)[0] if v is not None else None)
            name, why = "Long-term debt (incl. current portion)", "Bonds, notes and loans, current maturities included: financial."
            skipped.add("ltdc")
        if any(v for v in vals):
            x = {"k": key, "side": side, "name": name, "cls": cls, "why": why, "v": vals, "ev": refs, "suggest": None}
            if classified[side]:
                x["cur"] = 1 if key in CURRENT else 0
                if any(cur):                    # a lease line's current part; the current maturities in the debt total
                    x["cv"] = cur
            lines.append(x)
    if "ltdc" in skipped:
        lines = [x for x in lines if x["k"] != "ltdc"]
    # the same borrowings tagged twice: Novo Nordisk's 20-F tags its current borrowings as ShorttermBorrowings and as
    # CurrentPortionOfLongtermBorrowings, equal at every year end. One line, so the rest is not short by it.
    by = {x["k"]: x for x in lines}
    if "std" in by and "ltdc" in by and any(v is not None for v in by["ltdc"]["v"]) \
            and all(b is None or a == b for a, b in zip(by["std"]["v"], by["ltdc"]["v"])):
        lines = [x for x in lines if x["k"] != "ltdc"]

    def current_part(x, i):
        return (x["cv"][i] or 0) if "cv" in x else (x["v"][i] or 0) if x.get("cur") else 0

    for spec, tot, sub in ((OTHER_A, "assets", "ca"), (OTHER_L, "liab", "cl")):
        key, side, name, cls, why = spec
        mine = [x for x in lines if x["side"] == side]
        if not classified[side]:
            rest = []
            for i in range(len(ends)):
                t = totals[tot][i]
                rest.append(None if t is None else t - sum(x["v"][i] or 0 for x in mine))
            lines.append({"k": key, "side": side, "name": name, "cls": cls, "why": why, "v": rest, "ev": [[] for _ in ends],
                          "derived": tot, "suggest": None})
            continue
        (kc, dc, nc, wc), (kn, dn, nn, wn) = OTHER_SECTIONS[side]
        rc, rn = [], []
        for i in range(len(ends)):
            t, s = totals[tot][i], totals[sub][i]
            cp = sum(current_part(x, i) for x in mine)
            rc.append(s - cp)
            rn.append(None if t is None else t - s - (sum(x["v"][i] or 0 for x in mine) - cp))
        lines.append({"k": kc, "side": side, "name": nc, "cls": cls, "why": wc, "v": rc, "ev": [[] for _ in ends],
                      "derived": dc, "cur": 1, "suggest": None})
        lines.append({"k": kn, "side": side, "name": nn, "cls": cls, "why": wn, "v": rn, "ev": [[] for _ in ends],
                      "derived": dn, "cur": 0, "suggest": None})
    flows = []
    for e in ends[1:]:
        row, refs = {}, {}
        for k in ("revenue", "oi", "pretax", "tax", "ni", "pl"):
            v, r = W.keyed(fx, ev, k, e, True)
            if v is not None:
                row[k], refs[k] = v, r
        for k, tags in FLOWS.items():
            v, used, how = None, [], None
            for c in tags:
                v, used, how = W._dur(fx.get(c), e, True)
                if v is not None:
                    refs[k] = ev.ref(c, how, used)
                    break
            if v is not None:
                row[k] = v
        flows.append({"end": e, "label": F.fiscal_year_label(e, fye)[0], **row, "ev": refs})
    return {"ends": ends, "labels": [F.fiscal_year_label(e, fye)[0] for e in ends], "lines": lines,
            "totals": {k: v for k, v in totals.items() if any(x is not None for x in v)},
            "ev_totals": {k: v for k, v in tev.items() if any(v)}, "flows": flows, "tax_rate": TAX_RATE, "suggest": None}
