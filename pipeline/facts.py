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
                "OperatingLeasesIncomeStatementLeaseRevenue", "RevenueNet",
                "Revenue", "RevenueFromContractsWithCustomers",                       # IFRS (ifrs-full)
                "RevenueFromSaleOfGoods", "RevenueAndOperatingIncome"],               # Sanofi; HSBC's total operating income
    "cor": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfServices",
            "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization", "CostOfSales"],
    "gp": ["GrossProfit"],
    "rd": ["ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
           "TechnologyAndDevelopmentExpense"],
    "sm": ["SellingAndMarketingExpense", "MarketingAndAdvertisingExpense", "SellingExpense", "DistributionCosts"],
    "ga": ["GeneralAndAdministrativeExpense", "AdministrativeExpense"],
    "sga": ["SellingGeneralAndAdministrativeExpense"],
    "costs_total": ["CostsAndExpenses", "BenefitsLossesAndExpenses"],
    "opex_total": ["OperatingExpenses", "OperatingExpense"],
    "oi": ["OperatingIncomeLoss", "ProfitLossFromOperatingActivities"],
    "pretax": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
               "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
               "IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign", "ProfitLossBeforeTax"],
    "tax": ["IncomeTaxExpenseBenefit", "IncomeTaxExpenseBenefitContinuingOperations", "IncomeTaxExpenseContinuingOperations"],
    "ni": ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLossAttributableToOwnersOfParent"],
    "pl": ["ProfitLoss"],
    "nci": ["NetIncomeLossAttributableToNoncontrollingInterest", "MinorityInterestInNetIncomeLossOfConsolidatedEntities",
            "ProfitLossAttributableToNoncontrollingInterests"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
            "CashFlowsFromUsedInOperatingActivities"],
    # depreciation & amortization: a combined tag, else depreciation + amortization of intangibles (see _da: Oracle,
    # for one, tags the two apart; depreciation alone is labelled "Depreciation" on the chart, never D&A)
    "da": ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet", "DepreciationAndAmortization",
           "DepreciationAndAmortisationExpense", "AdjustmentsForDepreciationAndAmortisationExpense"],
    "dep": ["DepreciationDepletionAndAmortizationPropertyPlantAndEquipment", "Depreciation"],
    "amort": ["AmortizationOfIntangibleAssets", "AmortisationExpense"],
    "sbc": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense", "AdjustmentsForSharebasedPayments",
            "ExpenseFromSharebasedPaymentTransactionsWithEmployees"],
    # revenue from contracts with customers: the total the revenue lines usually add up to (Vistra: $4.40B of contract
    # revenue, minus $0.38B of other revenues such as hedging results, = $4.02B of total revenues)
    "rev_contract": ["RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax"],
    # capital expenditures: the general tags, then the ones oil & gas, real-estate and utility filers use
    # banks tag no total revenue: revenue = net interest income + noninterest income (bank_revenue below), and their
    # costs are the provision for credit losses and noninterest expense (model.normalize)
    "nii": ["InterestIncomeExpenseNet"],
    "int_inc": ["InterestAndDividendIncomeOperating", "InterestIncomeOperating"],
    "int_exp": ["InterestExpense", "InterestExpenseOperating"],
    "nonii": ["NoninterestIncome"],
    "prov": ["ProvisionForLoanLeaseAndOtherLosses", "ProvisionForLoanAndLeaseLosses", "ProvisionForLoanLossesExpensed"],
    "nonint_exp": ["NoninterestExpense"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
              "PaymentsToAcquireOilAndGasPropertyAndEquipment", "PaymentsToAcquireOilAndGasProperty",
              "PaymentsToExploreAndDevelopOilAndGasProperties", "PaymentsForCapitalImprovements",
              "PaymentsToDevelopRealEstateAssets", "PaymentsForConstructionInProcess",
              "PaymentsToAcquireOtherPropertyPlantAndEquipment", "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
              "PurchaseOfPropertyPlantAndEquipment"],
}
# several tags can coexist: the largest is the total (revenue), or the main capex line rather than a small sub-line
MAX_KEYS = {"revenue", "capex"}
# ... except that "Revenues" is the income statement's total by definition: it wins even when contract revenue is larger
# (other revenues can be negative: hedging losses). The largest tag is only for filers without it.
TOTAL_FIRST = {"revenue": "Revenues"}
# cash-flow bridge items: an income statement can tag a narrower figure than the cash-flow statement adds back (Vistra:
# D&A $445M on the income statement, $645M in the cash flow, which includes nuclear fuel amortization). A tag reported
# only year-to-date (no three-month figure after the first quarter) is the cash-flow statement's, and it wins.
CASH_FLOW_KEYS = {"da", "sbc", "dep", "amort"}


def d(s):
    return dt.date.fromisoformat(s)


def statement_fact(f):
    """False for a fact from a proxy statement (DEF 14A and the like): its pay-versus-performance table tags the
    year's net income too, often the consolidated figure (DaVita: $1,078.7M against the 10-K's $746.8M to
    shareholders), and being filed after the 10-K it would replace the financial statements' figure."""
    return "14A" not in (f.get("form") or "")


def version(f, accn=None, before=None):
    """Which of a period's figures (one per filing that tagged the period) a chart takes, highest first: an amended
    filing's (a 10-K/A restating it), then the chart's own filing's (accn), then the latest filed on or before the
    chart's filing (before: that filing's date), then the earliest filed after it. A later filing's comparative can be
    on another basis: Pixelworks' Q2 2025 revenue is $8.3M in its own 10-Q and $0.2M a year later, the Shanghai
    business sold and moved to discontinued operations; TDS's Q2 2025 is $1.24B, then $298M without the wireless
    business. A chart cites its filing and keeps to what was reported by then: its own figures, its comparatives
    (the year-ago quarter on the same basis), the quarter before as that quarter's own filing had it."""
    amended, filed = (f.get("form") or "").endswith("/A"), f.get("filed") or ""
    if before and filed > before:
        return (amended, False, False, tuple(-ord(ch) for ch in filed))
    return (amended, accn is not None and f.get("accn") == accn, True, tuple(ord(ch) for ch in filed))


def _filed_on(companyfacts, accn):
    """When the filing accn was made, from any of its facts (None: no fact of that filing in companyfacts)."""
    if not accn:
        return None
    for tax in ("us-gaap", "ifrs-full", "dei"):
        for body in (companyfacts.get("facts", {}).get(tax) or {}).values():
            for fs in (body.get("units") or {}).values():
                for f in fs:
                    if f.get("accn") == accn:
                        return f.get("filed")
    return None


def index_facts(companyfacts, currency="USD", accn=None):
    """concept -> {(start, end): fact} keeping one fact per period (version: the chart's own filing's when accn is
    given, then the latest by that filing's date; else the most recently filed), in the company's reporting currency (US dollars for nearly all; a foreign
    filer's own, fx.py). us-gaap and ifrs-full concepts. Balances are point-in-time facts (no start): those
    quality.INSTANTS needs go to "__instants__" as concept -> {day: fact}. Facts from proxy statements are left out
    (statement_fact)."""
    from .history import CONCEPTS as KEEP_ALL
    from .quality import INSTANTS, SHARES
    out, names, inst, shares, vers, every = {}, {}, {}, {}, {}, {}
    out["__labels__"] = names                            # concept -> SEC's standard label, to say where a figure came from
    out["__instants__"] = inst                           # balances pipeline/quality.py reads (assets, reserves, debt, ...)
    out["__shares__"] = shares                           # share counts: concept -> {(start, end) or end: fact}
    out["__versions__"] = vers                           # every filing's version of the headline figures (history.py)
    out["__accn__"] = accn                               # the filing whose figures are preferred (None: the latest)
    before = _filed_on(companyfacts, accn)
    newer = lambda f, old: version(f, accn, before) >= version(old, accn, before)
    for taxonomy in ("dei",):
        for concept, body in companyfacts.get("facts", {}).get(taxonomy, {}).items():
            if concept in SHARES:
                names.setdefault(concept, body.get("label"))
                for f in body.get("units", {}).get("shares", []):
                    if not statement_fact(f):
                        continue
                    k = (f["start"], f["end"]) if "start" in f else f["end"]
                    per = shares.setdefault(concept, {})
                    if k not in per or newer(f, per[k]):
                        per[k] = f
    for taxonomy in ("us-gaap", "ifrs-full"):
        for concept, body in companyfacts.get("facts", {}).get(taxonomy, {}).items():
            names.setdefault(concept, body.get("label"))
            for unit, facts in body.get("units", {}).items():
                facts = [f for f in facts if statement_fact(f)]
                if unit == "shares" and concept in SHARES and taxonomy == "us-gaap":
                    per = shares.setdefault(concept, {})
                    for f in facts:
                        k = (f["start"], f["end"]) if "start" in f else f["end"]
                        if k not in per or newer(f, per[k]):
                            per[k] = f
                if unit != currency:
                    continue
                per = out.setdefault(concept, {})
                for f in facts:
                    if "start" not in f:
                        if concept in INSTANTS and taxonomy == "us-gaap":
                            day = inst.setdefault(concept, {})
                            if f["end"] not in day or newer(f, day[f["end"]]):
                                day[f["end"]] = f
                        continue
                    key = (f["start"], f["end"])
                    if key in per:
                        every.setdefault(concept, {}).setdefault(key, [per[key]]).append(f)
                    if key not in per or newer(f, per[key]):
                        per[key] = f
                    if concept in KEEP_ALL and taxonomy == "us-gaap":
                        vers.setdefault(concept, {}).setdefault(key, []).append(f)
    for concept, keys in every.items():
        _scale_slips(out[concept], keys)
        _corrections(out[concept], keys)
    return out


SLIP = 100                     # versions of one figure this far apart are not a restatement but a slip of the scale
CORRECTION = 0.05              # ... and this close are a correction, not a restatement: the latest filing's wins


def _corrections(per, every):
    """A later filing's version of a figure within CORRECTION of the chart's own filing's is a correction (Plexus'
    FY2024 10-K tags revenue of $4,078M, the segment total before eliminations; the next 10-K's comparative has the
    income statement's $3,961M) or a minor reclassification: the latest filed wins. Far apart, the versions are on
    different bases (a business moved to discontinued operations) and the chart keeps its own filing's."""
    for key, versions in every.items():
        latest = max(versions, key=lambda f: f.get("filed") or "")
        chosen = per[key]
        if latest is chosen or not latest.get("val") or not chosen.get("val"):
            continue
        if abs(latest["val"] - chosen["val"]) <= CORRECTION * max(abs(latest["val"]), abs(chosen["val"])):
            per[key] = latest


def _scale_slips(per, every):
    """A filing that tags a figure at the wrong scale (Smith Midland's Q2 2025 10-Q: net income $4,171, meaning
    $4,171 thousand, beside revenue of $26.2M; its later filings say $4.171M) is told from the other versions of the
    period's figure: when versions are SLIP times apart, the one more filings agree with wins, then the one in
    scale with the concept's other periods."""
    import math
    mags = None
    for key, versions in every.items():
        vals = [f["val"] for f in versions if f.get("val")]
        if len(vals) < 2 or max(abs(v) for v in vals) < SLIP * min(abs(v) for v in vals):
            continue
        if mags is None:
            mags = sorted(math.log10(abs(f["val"])) for k, f in per.items() if f.get("val") and k not in every) or [0]
        typical = mags[len(mags) // 2]
        def score(f):
            agree = sum(1 for g in versions if g.get("val") and abs(g["val"] - f["val"]) <= 0.01 * abs(f["val"]))
            return (agree, -abs(math.log10(abs(f["val"])) - typical))
        best = max((f for f in versions if f.get("val")), key=score)
        if not per[key].get("val") or score(best) > score(per[key]):
            per[key] = best


def _same(a, b):
    return abs(a - b) <= 0.001 * max(abs(a), abs(b), 1)


def _quarter_from(per, end):
    """Quarter value ending at `end`, directly or as YTD - prior YTD. A quarter-long context that carries the figure of
    a longer period ending the same day is a tagging slip (Tractor Supply's 10-K: fourth-quarter net income tagged
    with the year's $1.10B; NiSource's: the year's revenue in the fourth quarter's context) and is passed over for
    the year-to-date derivation when there is one."""
    at_end = [(s, f) for (s, e), f in per.items() if e == end]
    if not at_end:
        return None
    s0, f0 = min(at_end, key=lambda x: x[0])           # longest year-to-date span
    longer = (d(end) - d(s0)).days >= 170
    derived = None
    if longer:
        for (s, e), f in per.items():
            if s == s0 and e != end and 75 <= (d(end) - d(e)).days <= 105:
                derived = f0["val"] - f["val"]
                break
    for s, f in at_end:
        if 75 <= (d(end) - d(s)).days <= 100:
            if longer and f is not f0 and _same(f["val"], f0["val"]) and derived is not None and not _same(derived, f["val"]):
                continue
            return f["val"]
    return derived


def _year_from(per, end):
    """Full fiscal-year value ending at `end` (a 52/53-week or 12-month duration)."""
    for (s, e), f in per.items():
        if e == end and 350 <= (d(e) - d(s)).days <= 380:
            return f["val"]
    return None


def cash_flow_only(per):
    """True when a tag is reported only year-to-date (as in a 10-Q's cash-flow statement): every quarter-long figure
    starts where a longer one starts (a first quarter), and some longer one exists."""
    long_starts = {s for (s, e) in per if (d(e) - d(s)).days >= 170}
    quarters = [s for (s, e) in per if 75 <= (d(e) - d(s)).days <= 100]
    return bool(long_starts) and all(s in long_starts for s in quarters)


def _candidates(facts, key, get):
    """[(value, concept)] of the tags of CONCEPTS[key] that have a figure, in the list's order."""
    out = []
    for concept in CONCEPTS[key]:
        per = facts.get(concept)
        if per:
            v = get(per)
            if v is not None:
                out.append((v, concept))
    return out


def _quarter_ends_of(per, end):
    """The three quarter ends before `end` with a figure under this tag (nearest to 91, 182 and 273 days before, within
    three weeks), or None when one is missing."""
    ends = {e for (s, e) in per if 60 < (d(end) - d(e)).days < 300}
    out = []
    for target in (91, 182, 273):
        near = [e for e in ends if abs((d(end) - d(e)).days - target) <= 21]
        if not near:
            return None
        out.append(min(near, key=lambda e: abs((d(end) - d(e)).days - target)))
    return out


def consistent_year(per, end):
    """True when a tag's four quarters of the year ending at `end` add up to its full-year figure (within 3%): the
    tag the company reports with all year. A tag that appears only in the 10-K (Nasdaq's "depreciation, depletion and
    amortization" of $145M, a note's figure, beside the cash flow statement's $632M of depreciation and amortization,
    reported every quarter) does not pass. None when the tag has no full-year figure."""
    total = _year_from(per, end)
    if total is None:
        return None
    ends = _quarter_ends_of(per, end)
    if not ends:
        return False
    vals = [_quarter_from(per, e) for e in ends + [end]]
    if any(v is None for v in vals):
        return False
    # within 3% of the year, or of the quarters' size when the year nets to little (TDS's 2025: quarters of +7, +12,
    # -82 and +56 against a year of -6: a $0.5M slip in a restated quarter is no reason to prefer another tag)
    return abs(sum(vals) - total) <= 0.03 * max(abs(total), sum(abs(v) for v in vals) / 2, 1)


def _pick(facts, key, get, end=None, annual=False):
    """(value, concept) for a key (see MAX_KEYS, TOTAL_FIRST, CASH_FLOW_KEYS), else (None, None). For a full year,
    a tag whose quarters add up to its year (consistent_year) is preferred to one that does not."""
    c = _candidates(facts, key, get)
    if not c:
        return None, None
    if annual and end and len(c) > 1:
        good = [x for x in c if consistent_year(facts[x[1]], end)]
        # ... unless, for a cash-flow item, the year's own tag is many times the one reported quarterly (JLL: $112M of
        # share-based compensation in the 10-K's cash flow statement; the quarters tag a $0.7M plan apart)
        if good and len(good) < len(c) and not (key in CASH_FLOW_KEYS and
                                                 max(x[0] for x in c) >= 2 * max(x[0] for x in good)):
            c = good
    if key in TOTAL_FIRST:
        hit = next((x for x in c if x[1] == TOTAL_FIRST[key]), None)
        if hit:
            return _total_or_larger(facts, get, c, hit, end, annual)
    if key in MAX_KEYS:
        return max(c, key=lambda x: x[0])
    if key in CASH_FLOW_KEYS and len(c) > 1:
        cf = [x for x in c if cash_flow_only(facts[x[1]])]
        if cf:
            top = max(cf, key=lambda x: x[0])
            return top if annual and top[0] >= 2 * cf[0][0] > 0 else cf[0]   # a year's tag many times the first: the whole
    return c[0]


# "Revenues" far below another revenue tag is checked against the income statement: the total revenue is the one that
# closes it (revenue − costs and expenses = operating income, or + other income = pre-tax). Vistra's "Revenues" sit
# below its contract revenue by its hedging losses and close the statement; Blue Owl's "Revenues" ($0.14B, a narrower
# line) against its $0.75B of total revenues, net (= contract revenue) do not.
TOTAL_NEAR = 0.75


def total_ok(total, top):
    """True when a "Revenues" figure is close enough to the largest revenue tag to be taken without a check."""
    return total is not None and top is not None and (top <= 0 or total >= TOTAL_NEAR * top)


# a "Revenues" below this share of the largest revenue tag that the company did not report in the quarter before nor a
# year earlier is a line newly tagged that way, not the total (Cumberland: $0.17M of other revenue beside $8.8M of net
# revenues, with a costs sub-total that happens to close on it)
NEW_LINE = 0.25


def _total_or_larger(facts, get, c, hit, end=None, annual=False):
    top = max(c, key=lambda x: x[0])
    if top is hit or total_ok(hit[0], top[0]):
        return hit
    nper = facts.get("NonoperatingIncomeExpense")
    v = lambda k: _pick(facts, k, get)[0]                                                    # noqa: E731
    if closes_better(top[0], hit[0], v("costs_total"), v("oi"), v("pretax"), get(nper) if nper else None,
                     gp=v("gp"), cor=v("cor"), opex=v("opex_total")):
        return top
    if end and hit[0] < NEW_LINE * top[0] and not _reported_before(facts.get(hit[1]) or {}, end, annual):
        return top
    return hit


def _reported_before(per, end, annual=False):
    """True when the tag has a figure for the period a quarter before or a year before `end` from another filing
    (the comparative column of the filing that tags the line this way is no evidence of it)."""
    if not per:
        return False
    own = {f.get("accn") for (s, e), f in per.items() if e == end}
    if annual:
        e = prior_year_end({"Revenues": per, "__labels__": {}}, end)
        ends = [e] if e else []
    else:
        ends = [e for e in comparison_ends({"Revenues": per, "__labels__": {}}, end) if e]
    return any(f.get("accn") not in own for (s, e), f in per.items() if e in ends)


def closes_better(top, total, costs, oi=None, pre=None, non=None, gp=None, cor=None, opex=None):
    """True when the larger revenue figure closes the income statement — revenue − costs and expenses = operating income
    (or with other income = pre-tax earnings), revenue − cost of revenue = gross profit, revenue − operating expenses
    (and cost of revenue) = operating income — within 2%, and much better than the "Revenues" figure does."""
    def gap(r):
        g = []
        if costs is not None and oi is not None:
            g.append(abs(r - costs - oi))
        if costs is not None and pre is not None:
            g.append(abs(r - costs + (non or 0) - pre))
        if gp is not None and cor is not None:
            g.append(abs(r - cor - gp))
        if opex is not None and oi is not None:
            g.append(min(abs(r - opex - oi), abs(r - (cor or 0) - opex - oi)))
        return min(g) if g else None
    g_hit, g_top = gap(total), gap(top)
    return g_hit is not None and g_top is not None and g_top <= 0.02 * abs(top) and g_top < 0.5 * g_hit


def _first(facts, key, get, end=None, annual=False):
    """(value, concept) for the key's figure: see _pick."""
    return _pick(facts, key, get, end, annual)


def _da(facts, get, end=None, annual=False):
    """Depreciation & amortization: the combined tag, else depreciation + amortization of intangible assets, else
    depreciation alone. A combined tag that equals the depreciation tag while amortization is tagged apart holds
    depreciation only (Jazz: $41.6M under both, $654.7M of amortization beside): the two are added. `get` reads one
    tag's figure for the period."""
    v, _ = _first(facts, "da", get, end, annual)
    dep, _ = _first(facts, "dep", get, end, annual)
    amort, _ = _first(facts, "amort", get, end, annual)
    if v is not None:
        if dep is not None and amort and amort > 0 and _same(v, dep):
            return dep + amort
        return v
    if dep is None:
        return None
    return dep + (amort or 0)


def value(facts, key, end, annual=False):
    get = lambda per: _year_from(per, end) if annual else _quarter_from(per, end)
    if key == "da":
        return _da(facts, get, end, annual)
    return _pick(facts, key, get, end, annual)[0]


def source(facts, key, end, annual=False):
    """The concept value() takes its figure from (see _pick), or None."""
    get = lambda per: _year_from(per, end) if annual else _quarter_from(per, end)
    if key == "da":
        v, concept = _pick(facts, "da", get, end, annual)
        return concept if v is not None else _pick(facts, "dep", get, end, annual)[1]
    return _pick(facts, key, get, end, annual)[1]


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
    return _pick(facts, key, lambda per: _ytd(per, end))[0]


def period_ends(facts):
    ends = set()
    for concept in CONCEPTS["revenue"] + CONCEPTS["ni"] + CONCEPTS["oi"] + CONCEPTS["nii"]:
        for (s, e) in facts.get(concept, {}):
            ends.add(e)
    return sorted(ends)


def year_ends(facts):
    """Fiscal-year ends with a full-year revenue figure (a bank's: net interest income)."""
    ends = set()
    for concept in CONCEPTS["revenue"] + CONCEPTS["nii"]:
        for (s, e) in facts.get(concept, {}):
            if 350 <= (d(e) - d(s)).days <= 380:
                ends.add(e)
    return sorted(ends)


def quarter_ends(facts):
    """Quarter ends whose quarterly revenue can be read (directly or as year-to-date minus the earlier year-to-date)."""
    out = []
    per = {}
    for concept in CONCEPTS["revenue"] + CONCEPTS["nii"]:
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
    if not end:
        return None
    raw = {k: value(facts, k, end, annual) for k in CONCEPTS}
    if not annual:
        fourth_quarter_check(facts, end, raw)
    odd_one_out(raw)
    return bank_revenue(raw, source(facts, "revenue", end, annual))


def odd_one_out(raw):
    """Net income to shareholders and the consolidated figure (ProfitLoss) should differ by the minority interests'
    share, and pre-tax earnings less tax is the consolidated figure. When the shareholders' figure fits pre-tax less
    tax and ProfitLoss does not (Smith Midland's 2024 10-Qs tag ProfitLoss with the sign flipped), the ProfitLoss tag
    is the slip: without it the chart would show a minority interest that does not exist."""
    pretax, tax, ni, pl = (raw.get(k) for k in ("pretax", "tax", "ni", "pl"))
    if None in (pretax, tax, ni, pl) or raw.get("nci") is not None:
        return
    after_tax = pretax - tax
    tol = 0.005 * max(abs(after_tax), abs(ni), abs(pl), 1)
    if abs(after_tax - ni) <= tol < abs(after_tax - pl):
        raw["pl"] = ni


# a fourth quarter is checked against the year less the three quarters before it: off by more than this share of the
# larger of the figures, it is replaced by that difference
Q4_TOLERANCE = 0.25


def fourth_quarter_check(facts, end, raw):
    """A quarter at a fiscal year end is read from the 10-K as the year less nine months (or a fourth-quarter fact).
    Either can be a tagging slip (NiSource's fourth-quarter revenue tagged as the year's $6.52B; Plexus' nine months
    tagged as $2.975M instead of $2,975M, leaving the whole year as the quarter). So each figure is checked against
    the year less the three quarters reported before: when they disagree by more than Q4_TOLERANCE of the larger,
    the difference is taken, and raw["q4_fixed"] lists the keys. A figure the 10-K lacks a quarter for is filled the
    same way."""
    ends = _quarter_ends_of({(s, e): None for c in (CONCEPTS["revenue"] + CONCEPTS["ni"] + CONCEPTS["nii"])
                             for (s, e) in facts.get(c, {})}, end)
    if not ends:
        return
    fixed = []
    for k in CONCEPTS:
        total = value(facts, k, end, annual=True)
        if total is None:
            continue
        before = [value(facts, k, e) for e in ends]
        if any(v is None for v in before):
            continue
        ytd = _nine_months(facts, k, max(ends))
        if ytd and total and abs(ytd) * SLIP > abs(total) > abs(ytd) / SLIP \
                and abs(sum(before) - ytd) > Q4_TOLERANCE * max(abs(ytd), abs(sum(before)), 1):
            continue                                      # the three quarters do not add up to the nine months either
        alt = total - sum(before)
        q = raw.get(k)
        # quarters read from a tag that is not the year's (AMG: share-based compensation from the cash flow statement in
        # the 10-Qs, the expense allocated in the 10-K) can put the difference the wrong side of zero: left alone then
        if total and (alt > 0) != (total > 0) and (q is None or (q > 0) == (total > 0)):
            continue
        if q is None:
            raw[k] = alt
            fixed.append(k)
        elif abs(q - alt) > Q4_TOLERANCE * max(abs(total), abs(q), abs(alt), 1):
            raw[k] = alt
            fixed.append(k)
    if fixed:
        raw["q4_fixed"] = fixed


def _nine_months(facts, key, end):
    """The year-to-date figure of the three quarters before a fourth (a fact of 255-290 days ending at end), from
    the first of the key's tags that has one. The quarters' sum is checked against it (when it is in scale with the
    year: Plexus' nine months are the slip) before it replaces a fourth quarter: a quarter derived through a slipped
    tag (Smith Midland's Q2 2025 capex tagged $5 thousand) would otherwise hand the fourth quarter its error."""
    for c in CONCEPTS[key]:
        for (s, e), f in facts.get(c, {}).items():
            if e == end and 255 <= (d(e) - d(s)).days <= 290:
                return f["val"]
    return None


# a bank's own total: these tags are the whole income statement's revenue, so a bank that uses them keeps them
TOTAL_TAGS = {"Revenues", "RevenuesNetOfInterestExpense", "Revenue"}


def bank_revenue(raw, rev_concept=None):
    """A bank reports no total revenue: what it calls total revenue is net interest income + noninterest income
    (interest income − interest expense when net interest income is not tagged). When both are tagged and the revenue
    found is not a total-revenue tag (a bank's "revenue from contracts with customers" is only the fee part of its
    noninterest income), revenue is their sum and raw["rev_bank"] says so: the chart draws the two as revenue lines,
    and the provision for credit losses and noninterest expense as the costs."""
    nii = raw.get("nii")
    if nii is None and raw.get("int_inc") is not None and raw.get("int_exp") is not None:
        nii = raw["int_inc"] - raw["int_exp"]
        raw["nii"] = nii
    if rev_concept in TOTAL_TAGS or nii is None or raw.get("nonii") is None or nii + raw["nonii"] <= 0:
        return raw
    if raw.get("revenue") is not None:
        raw["rev_tagged"] = raw["revenue"]
    raw["revenue"] = nii + raw["nonii"]
    raw["rev_bank"] = True
    return raw


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
