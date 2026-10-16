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
match the filing and nothing is filled in. Each line carries an empty "suggest" for a classification read from the
filing's notes later (the local model).
"""
from . import facts as F
from . import fsa as W

KEEP = 5                                # fiscal years of returns (one more balance sheet for the opening balances)

# (key, side, name, default class, reason, [groups of candidate tags]): one tag per group, the first tagged
LINES = [
    ("cash", "a", "Cash and cash equivalents", "fin", "Cash can repay debt or be paid out: a financial asset. Cash needed to run the business is operating; move it if you know how much.",
     [["CashAndCashEquivalentsAtCarryingValue", "Cash", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]]),
    ("sti", "a", "Short-term investments", "fin", "Securities held for the cash they will return: financial.",
     [["ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"]]),
    ("lti", "a", "Long-term investments", "fin", "Securities held for their return: financial. A stake in another business that is part of operations is operating.",
     [["MarketableSecuritiesNoncurrent", "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent", "LongTermInvestments"]]),
    ("ar", "a", "Receivables", "op", "Owed by customers for sales: operating.",
     [["AccountsReceivableNetCurrent", "ReceivablesNetCurrent", "AccountsReceivableNet"]]),
    ("inv", "a", "Inventory", "op", "Goods held for sale: operating.", [["InventoryNet"]]),
    ("oca", "a", "Prepaid and other current assets", "op", "Prepayments and other operating items: operating.",
     [["PrepaidExpenseAndOtherAssetsCurrent", "OtherAssetsCurrent", "PrepaidExpenseCurrent"]]),
    ("ppe", "a", "Property, plant and equipment", "op", "Assets used to produce and sell: operating.",
     [["PropertyPlantAndEquipmentNet", "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization"]]),
    ("rou", "a", "Operating lease right-of-use assets", "op", "Leased stores, offices and equipment used in the business: operating.", [["OperatingLeaseRightOfUseAsset"]]),
    ("gw", "a", "Goodwill", "op", "Paid for acquired businesses: operating.", [["Goodwill"]]),
    ("intang", "a", "Intangible assets", "op", "Acquired technology, brands and customer relationships: operating.",
     [["IntangibleAssetsNetExcludingGoodwill", "FiniteLivedIntangibleAssetsNet"]]),
    ("eqm", "a", "Equity-method investments", "op", "Stakes in associated businesses, usually part of operations. Financial if held as an investment.", [["EquityMethodInvestments"]]),
    ("dta", "a", "Deferred tax assets", "op", "Taxes on operating income paid ahead: operating.", [["DeferredIncomeTaxAssetsNet", "DeferredTaxAssetsNetNoncurrent"]]),
    ("onca", "a", "Other non-current assets", "op", "Other long-term operating items: operating.", [["OtherAssetsNoncurrent"]]),
    ("ap", "l", "Accounts payable", "op", "Owed to suppliers for operations: operating.",
     [["AccountsPayableCurrent", "AccountsPayableTradeCurrent", "AccountsPayableAndAccruedLiabilitiesCurrent"]]),
    ("accr", "l", "Accrued liabilities", "op", "Wages, services and other costs not yet paid: operating.",
     [["AccruedLiabilitiesCurrent", "EmployeeRelatedLiabilitiesCurrent"]]),
    ("defrev", "l", "Deferred revenue", "op", "Customers' payments ahead of delivery: operating.",
     [["ContractWithCustomerLiabilityCurrent", "DeferredRevenueCurrent"]]),
    ("taxp", "l", "Income taxes payable", "op", "Taxes on operating income: operating.", [["AccruedIncomeTaxesCurrent", "TaxesPayableCurrent"]]),
    ("ocl", "l", "Other current liabilities", "op", "Other operating items due within a year: operating.", [["OtherLiabilitiesCurrent"]]),
    ("std", "l", "Short-term debt and commercial paper", "fin", "Borrowed money: financial.",
     [["DebtCurrent"], ["ShortTermBorrowings", "CommercialPaper", "OtherShortTermBorrowings", "NotesPayableCurrent"]]),
    ("ltdc", "l", "Current portion of long-term debt", "fin", "Borrowed money falling due within a year: financial.",
     [["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"]]),
    ("ltd", "l", "Long-term debt", "fin", "Bonds, notes and loans: financial.",
     [["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations", "LongTermNotesPayable", "LongTermNotesAndLoans",
       "SeniorLongTermNotes", "ConvertibleNotesPayable", "OtherLongTermDebtNoncurrent", "LongTermLineOfCredit",
       "UnsecuredDebt", "SeniorNotes", "NotesPayable", "SecuredDebt"]]),
    ("flease", "l", "Finance lease liabilities", "fin", "Leases that work like a loan for the asset: financial.",
     [["FinanceLeaseLiabilityNoncurrent"], ["FinanceLeaseLiabilityCurrent"]]),
    ("olease", "l", "Operating lease liabilities", "op", "Rent owed on leases used in the business: operating by default. Move it to financing to treat leases like debt (if the balance sheet has no lease line of its own, they sit inside other liabilities).",
     [["OperatingLeaseLiabilityNoncurrent"], ["OperatingLeaseLiabilityCurrent"]]),
    ("dtl", "l", "Deferred tax liabilities", "op", "Taxes on operating income deferred: operating.", [["DeferredIncomeTaxLiabilitiesNet", "DeferredTaxLiabilitiesNoncurrent"]]),
    ("pension", "l", "Pension and retiree benefits", "op", "Promised to employees for their work: operating (some analysts treat the unfunded part as debt).",
     [["DefinedBenefitPensionPlanLiabilitiesNoncurrent", "PensionAndOtherPostretirementDefinedBenefitPlansLiabilitiesNoncurrent"]]),
    ("defrevn", "l", "Deferred revenue, non-current", "op", "Customers' payments for later years: operating.",
     [["ContractWithCustomerLiabilityNoncurrent", "DeferredRevenueNoncurrent"]]),
    ("oncl", "l", "Other non-current liabilities", "op", "Other long-term operating obligations: operating.", [["OtherLiabilitiesNoncurrent"]]),
]
# a combined tag that already contains another line: that line is skipped
COVERS = {"AccountsPayableAndAccruedLiabilitiesCurrent": {"accr"}, "DebtCurrent": {"ltdc"},
          "LongTermDebtAndCapitalLeaseObligations": {"flease"}}
TOTALS = {"assets": ["Assets"], "liab": ["Liabilities"], "le": ["LiabilitiesAndStockholdersEquity"],
          "cse": ["StockholdersEquity"], "nci": ["MinorityInterest"],
          "eq_all": ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
          "temp": ["RedeemableNoncontrollingInterestEquityCarryingAmount", "TemporaryEquityCarryingAmountAttributableToParent"],
          "ltd_all": ["LongTermDebt"]}
INSTANT_CONCEPTS = {t for *_, gs in LINES for g in gs for t in g} | {t for v in TOTALS.values() for t in v}
FLOWS = {"int_exp": ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt", "InterestAndDebtExpense"],
         "int_inc": ["InvestmentIncomeInterest", "InterestIncomeOther", "InvestmentIncomeInterestAndDividend"]}
TAX_RATE = 0.21            # US federal statutory rate, for the tax shield on net interest (editable on the page)
OTHER_A = ("oth_a", "a", "Other assets, not tagged separately", "op",
           "Total assets minus the lines above: assets the company tags its own way. Operating by default.")
OTHER_L = ("oth_l", "l", "Other liabilities, not tagged separately", "op",
           "Total liabilities minus the lines above: liabilities the company tags its own way. Operating by default.")


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
    skipped = set()
    for key, side, name, cls, why, groups in LINES:
        if key in skipped:
            continue
        vals, refs, tags = [], [], []
        for e in ends:
            tot, rs, used = None, [], None
            for g in groups:
                v, r, c = _bal(fx, ev, g, e)
                if v is not None:
                    tot = (tot or 0) + v
                    rs.append(r)
                    used = c
                    skipped |= COVERS.get(c, set())
                    if c == "DebtCurrent":                           # all current debt: nothing else in this line
                        break
            vals.append(tot)
            refs.append(rs)
            tags.append(used)
        if key == "ltd" and all(v is None for v in vals):           # only the total with current maturities is tagged
            vals, refs = [], []
            for e in ends:
                v, r, _ = _bal(fx, ev, TOTALS["ltd_all"], e)
                vals.append(v)
                refs.append([r] if r else [])
            name, why = "Long-term debt (incl. current portion)", "Bonds, notes and loans, current maturities included: financial."
            skipped.add("ltdc")
        if any(v for v in vals):
            lines.append({"k": key, "side": side, "name": name, "cls": cls, "why": why, "v": vals, "ev": refs, "suggest": None})
    if "ltdc" in skipped:
        lines = [x for x in lines if x["k"] != "ltdc"]
    for spec, tot in ((OTHER_A, "assets"), (OTHER_L, "liab")):
        key, side, name, cls, why = spec
        rest = []
        for i in range(len(ends)):
            t = totals[tot][i]
            rest.append(None if t is None else t - sum(x["v"][i] or 0 for x in lines if x["side"] == side))
        lines.append({"k": key, "side": side, "name": name, "cls": cls, "why": why, "v": rest, "ev": [[] for _ in ends],
                      "derived": tot, "suggest": None})
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
