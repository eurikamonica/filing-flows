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
    # depreciation & amortization: a combined tag, else depreciation + amortization of intangibles (see _da: Oracle,
    # for one, tags the two apart; depreciation alone is labelled "Depreciation" on the chart, never D&A)
    "da": ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet", "DepreciationAndAmortization"],
    "dep": ["DepreciationDepletionAndAmortizationPropertyPlantAndEquipment", "Depreciation"],
    "amort": ["AmortizationOfIntangibleAssets"],
    "sbc": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"],
    # capital expenditures: the general tags, then the ones oil & gas, real-estate and utility filers use
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
              "PaymentsToAcquireOilAndGasPropertyAndEquipment", "PaymentsToAcquireOilAndGasProperty",
              "PaymentsToExploreAndDevelopOilAndGasProperties", "PaymentsForCapitalImprovements",
              "PaymentsToDevelopRealEstateAssets", "PaymentsForConstructionInProcess",
              "PaymentsToAcquireOtherPropertyPlantAndEquipment"],
}
# several tags can coexist: the largest is the total (revenue), or the main capex line rather than a small sub-line
MAX_KEYS = {"revenue", "capex"}


def d(s):
    return dt.date.fromisoformat(s)


def index_facts(companyfacts):
    """concept -> {(start, end): fact} keeping the most recently filed fact per period (USD only)."""
    out, names = {}, {}
    out["__labels__"] = names                            # concept -> SEC's standard label, to say where a figure came from
    for taxonomy in ("us-gaap", "ifrs-full"):
        for concept, body in companyfacts.get("facts", {}).get(taxonomy, {}).items():
            names.setdefault(concept, body.get("label"))
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


def _year_from(per, end):
    """Full fiscal-year value ending at `end` (a 52/53-week or 12-month duration)."""
    for (s, e), f in per.items():
        if e == end and 350 <= (d(e) - d(s)).days <= 380:
            return f["val"]
    return None


def _first(facts, key, get):
    """(value, concept) of the first tag of CONCEPTS[key] that has a figure, else (None, None)."""
    for concept in CONCEPTS[key]:
        per = facts.get(concept)
        if per:
            v = get(per)
            if v is not None:
                return v, concept
    return None, None


def _da(facts, get):
    """Depreciation & amortization: the combined tag, else depreciation + amortization of intangible assets, else
    depreciation alone. `get` reads one tag's figure for the period."""
    v, _ = _first(facts, "da", get)
    if v is not None:
        return v
    dep, _ = _first(facts, "dep", get)
    if dep is None:
        return None
    amort, _ = _first(facts, "amort", get)
    return dep + (amort or 0)


def value(facts, key, end, annual=False):
    if key == "da":
        return _da(facts, lambda per: _year_from(per, end) if annual else _quarter_from(per, end))
    vals = []
    for concept in CONCEPTS[key]:
        per = facts.get(concept)
        if not per:
            continue
        v = _year_from(per, end) if annual else _quarter_from(per, end)
        if v is not None:
            if key not in MAX_KEYS:
                return v
            vals.append(v)
    return max(vals) if vals else None


def source(facts, key, end, annual=False):
    """The concept value() takes its figure from (for MAX_KEYS, the largest), or None."""
    best = None
    for concept in CONCEPTS[key]:
        per = facts.get(concept)
        if not per:
            continue
        v = _year_from(per, end) if annual else _quarter_from(per, end)
        if v is None:
            continue
        if key not in MAX_KEYS:
            return concept
        if best is None or v > best[0]:
            best = (v, concept)
    return best[1] if best else None


def _quarter_how(per, end):
    """'3m' when a three-month fact exists for the quarter ending `end`, else 'ytd' (year-to-date minus the prior)."""
    return "3m" if any(e == end and 75 <= (d(end) - d(s)).days <= 100 for (s, e) in per) else "ytd"


def provenance(facts, end, annual=False):
    """{key: {"c": concept, "ytd": True when the quarter is year-to-date minus the prior year-to-date}} for every
    figure found for the period: which tag each number on the chart was read from."""
    out = {}
    for key in CONCEPTS:
        concept = source(facts, key, end, annual)
        if concept:
            out[key] = {"c": concept, "ytd": (not annual) and _quarter_how(facts[concept], end) == "ytd"}
    return out


def _ytd(per, end):
    at_end = [(s, f) for (s, e), f in per.items() if e == end]
    return min(at_end, key=lambda x: x[0])[1]["val"] if at_end else None


def ytd_value(facts, key, end):
    """Year-to-date value ending at `end` (the longest duration reported), e.g. nine months of cash flow."""
    if key == "da":
        return _da(facts, lambda per: _ytd(per, end))
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


def year_ends(facts):
    """Fiscal-year ends with a full-year revenue figure."""
    ends = set()
    for concept in CONCEPTS["revenue"]:
        for (s, e) in facts.get(concept, {}):
            if 350 <= (d(e) - d(s)).days <= 380:
                ends.add(e)
    return sorted(ends)


def quarter_ends(facts):
    """Quarter ends whose quarterly revenue can be read (directly or as year-to-date minus the earlier year-to-date)."""
    out = []
    per = {}
    for concept in CONCEPTS["revenue"]:
        for k, f in facts.get(concept, {}).items():
            per.setdefault(k, f)
    for e in sorted({e for (s, e) in per}):
        if _quarter_from(per, e) is not None:
            out.append(e)
    return out


def comparison_ends(facts, end):
    """(previous quarter end, same quarter last year end) available in the facts."""
    ends = [d(e) for e in period_ends(facts)]
    e0 = d(end)
    q1 = [x for x in ends if 75 <= (e0 - x).days <= 105]
    py = [x for x in ends if 350 <= (e0 - x).days <= 380]
    pick = lambda xs, target: min(xs, key=lambda x: abs((e0 - x).days - target)).isoformat() if xs else None
    return pick(q1, 91), pick(py, 364)


def extract(facts, end, annual=False):
    return {k: value(facts, k, end, annual) for k in CONCEPTS} if end else None


def prior_year_end(facts, end):
    """The fiscal year before the one ending at `end`, if its full-year figures are in the facts."""
    e0 = d(end)
    xs = [d(e) for e in year_ends(facts) if 350 <= (e0 - d(e)).days <= 380]
    return min(xs, key=lambda x: abs((e0 - x).days - 364)).isoformat() if xs else None


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


def fiscal_year_label(end, fiscal_year_end):
    """'FY2025' for calendar years, 'FY26' for other fiscal years (the year the fiscal year ends in)."""
    label, q, fy = fiscal_label(end, fiscal_year_end)
    return (f"FY{fy}" if label.startswith("Q") and " FY" not in label else f"FY{str(fy)[2:]}"), fy


def calendar_quarter(end):
    e = d(end) - dt.timedelta(days=15)
    return f"CY{e.year}Q{(e.month - 1) // 3 + 1}"
