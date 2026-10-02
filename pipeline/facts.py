"""Turn SEC companyfacts (XBRL, non-dimensional) into quarterly values.

10-Q income-statement facts are usually 3-month durations. Cash-flow facts and 10-K facts are
year-to-date, so a quarter is derived as YTD minus the previous YTD with the same start date
(e.g. Q4 = full year - nine months).
"""
import datetime as dt

CONCEPTS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet", "SalesRevenueGoodsNet",
                "SalesRevenueServicesNet", "RevenuesNetOfInterestExpense", "RegulatedAndUnregulatedOperatingRevenue",
                "OperatingLeasesIncomeStatementLeaseRevenue", "RevenueNet"],
    "cor": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfServices",
            "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization"],
    "gp": ["GrossProfit"],
    "rd": ["ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
           "TechnologyAndDevelopmentExpense"],
    "sm": ["SellingAndMarketingExpense", "MarketingAndAdvertisingExpense", "SellingExpense"],
    "ga": ["GeneralAndAdministrativeExpense"],
    "sga": ["SellingGeneralAndAdministrativeExpense"],
    "costs_total": ["CostsAndExpenses", "BenefitsLossesAndExpenses"],
    "opex_total": ["OperatingExpenses"],
    "oi": ["OperatingIncomeLoss"],
    "pretax": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
               "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
               "IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign"],
    "tax": ["IncomeTaxExpenseBenefit", "IncomeTaxExpenseBenefitContinuingOperations"],
    "ni": ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"],
    "pl": ["ProfitLoss"],
    "nci": ["NetIncomeLossAttributableToNoncontrollingInterest", "MinorityInterestInNetIncomeLossOfConsolidatedEntities"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "da": ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
           "DepreciationAndAmortization", "DepreciationDepletionAndAmortizationPropertyPlantAndEquipment", "Depreciation"],
    "sbc": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
}
MAX_KEYS = {"revenue"}          # several revenue tags can coexist; the largest is the total


def d(s):
    return dt.date.fromisoformat(s)


def index_facts(companyfacts):
    """concept -> {(start, end): fact} keeping the most recently filed fact per period (USD only)."""
    out = {}
    for taxonomy in ("us-gaap", "ifrs-full"):
        for concept, body in companyfacts.get("facts", {}).get(taxonomy, {}).items():
            for unit, facts in body.get("units", {}).items():
                if unit != "USD":
                    continue
                per = out.setdefault(concept, {})
                for f in facts:
                    if "start" not in f:
                        continue
                    key = (f["start"], f["end"])
                    if key not in per or f.get("filed", "") >= per[key].get("filed", ""):
                        per[key] = f
    return out


def _quarter_from(per, end):
    """Quarter value ending at `end`, directly or as YTD - prior YTD."""
    at_end = [(s, f) for (s, e), f in per.items() if e == end]
    if not at_end:
        return None
    for s, f in at_end:
        if 75 <= (d(end) - d(s)).days <= 100:
            return f["val"]
    s0, f0 = min(at_end, key=lambda x: x[0])           # longest year-to-date span
    for (s, e), f in per.items():
        if s == s0 and e != end and 75 <= (d(end) - d(e)).days <= 105:
            return f0["val"] - f["val"]
    return None


def value(facts, key, end):
    vals = []
    for concept in CONCEPTS[key]:
        per = facts.get(concept)
        if not per:
            continue
        v = _quarter_from(per, end)
        if v is not None:
            if key not in MAX_KEYS:
                return v
            vals.append(v)
    return max(vals) if vals else None


def ytd_value(facts, key, end):
    """Year-to-date value ending at `end` (the longest duration reported), e.g. nine months of cash flow."""
    vals = []
    for concept in CONCEPTS[key]:
        at_end = [(s, f) for (s, e), f in facts.get(concept, {}).items() if e == end]
        if at_end:
            s0, f0 = min(at_end, key=lambda x: x[0])
            if key not in MAX_KEYS:
                return f0["val"]
            vals.append(f0["val"])
    return max(vals) if vals else None


def period_ends(facts):
    ends = set()
    for concept in CONCEPTS["revenue"] + CONCEPTS["ni"] + CONCEPTS["oi"]:
        for (s, e) in facts.get(concept, {}):
            ends.add(e)
    return sorted(ends)


def comparison_ends(facts, end):
    """(previous quarter end, same quarter last year end) available in the facts."""
    ends = [d(e) for e in period_ends(facts)]
    e0 = d(end)
    q1 = [x for x in ends if 75 <= (e0 - x).days <= 105]
    py = [x for x in ends if 350 <= (e0 - x).days <= 380]
    pick = lambda xs, target: min(xs, key=lambda x: abs((e0 - x).days - target)).isoformat() if xs else None
    return pick(q1, 91), pick(py, 364)


def extract(facts, end):
    return {k: value(facts, k, end) for k in CONCEPTS} if end else None


def fiscal_label(end, fiscal_year_end):
    """'Q3 FY26' for non-calendar fiscal years, 'Q2 2026' for calendar years."""
    e = d(end)
    mm, dd = int(fiscal_year_end[:2]), int(fiscal_year_end[2:])
    def fye(y):
        try:
            return dt.date(y, mm, min(dd, 28 if mm == 2 else dd))
        except ValueError:
            return dt.date(y, mm, 28)
    base = fye(e.year) if e > fye(e.year) + dt.timedelta(days=20) else fye(e.year - 1)
    fy = base.year + 1
    q = min(4, max(1, round(((e - base).days / 30.44) / 3)))
    if mm == 12 and dd >= 25:
        return f"Q{q} {fy}", q, fy
    return f"Q{q} FY{str(fy)[2:]}", q, fy


def calendar_quarter(end):
    e = d(end) - dt.timedelta(days=15)
    return f"CY{e.year}Q{(e.month - 1) // 3 + 1}"
