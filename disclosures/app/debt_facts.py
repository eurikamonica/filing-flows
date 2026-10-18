"""Debt and interest figures from SEC companyfacts (XBRL, us-gaap), as filed — used by debt.py.

Everything is read from the company's own XBRL facts: balances at the latest balance-sheet date, flows as trailing
twelve months (the last fiscal year + this year to date − the same period a year earlier), quarter-end history since
2009, the maturity ladder, weighted-average rates, revolver capacity, convertible terms and conversions. Each figure
keeps the concept it came from, so the page can say which tag was used.
"""
import datetime as dt
import math

# ---- concept families, most specific first --------------------------------------------------------------------------
TOTAL_DEBT = [  # total debt including the current portion (each entry: list of concepts summed)
    ['DebtLongtermAndShorttermCombinedAmount'],
    ['DebtCurrent', 'LongTermDebtNoncurrent'],
    ['LongTermDebt', 'ShortTermBorrowings', 'CommercialPaper'],
    ['LongTermDebt', 'ShortTermBorrowings'],
    ['LongTermDebt', 'CommercialPaper'],
    ['LongTermDebtCurrent', 'LongTermDebtNoncurrent', 'ShortTermBorrowings', 'CommercialPaper'],
    ['LongTermDebtCurrent', 'LongTermDebtNoncurrent', 'ShortTermBorrowings'],
    ['LongTermDebtCurrent', 'LongTermDebtNoncurrent'],
    ['DebtAndCapitalLeaseObligations'],
    ['LongTermDebtAndCapitalLeaseObligationsCurrent', 'LongTermDebtAndCapitalLeaseObligations'],
    ['LongTermDebt'],
    ['LongTermDebtNoncurrent'],
    ['LongTermDebtAndCapitalLeaseObligations'],
    ['SeniorNotes'],
    ['NotesPayable'],
]
CURRENT_DEBT = [['DebtCurrent'], ['LongTermDebtCurrent', 'ShortTermBorrowings', 'CommercialPaper'],
                ['LongTermDebtCurrent', 'ShortTermBorrowings'], ['LongTermDebtAndCapitalLeaseObligationsCurrent', 'ShortTermBorrowings'],
                ['LongTermDebtCurrent'], ['LongTermDebtAndCapitalLeaseObligationsCurrent'], ['ShortTermBorrowings']]
CASH = [['CashAndCashEquivalentsAtCarryingValue'], ['CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents'], ['Cash'],
        ['CashAndDueFromBanks']]
INVEST = [['MarketableSecuritiesCurrent'], ['ShortTermInvestments'], ['AvailableForSaleSecuritiesDebtSecuritiesCurrent'],
          ['OtherShortTermInvestments']]
SINGLE = {   # instants: one concept each, first found wins
    'commercial_paper': ['CommercialPaper'],
    'short_term_borrowings': ['ShortTermBorrowings', 'OtherShortTermBorrowings'],
    'finance_leases': ['FinanceLeaseLiability', 'CapitalLeaseObligations'],
    'operating_leases': ['OperatingLeaseLiability'],
    'convertible': ['ConvertibleDebtNoncurrent', 'ConvertibleNotesPayable', 'ConvertibleDebt', 'ConvertibleLongTermNotesPayable',
                    'ConvertibleSubordinatedDebtNoncurrent', 'ConvertibleSeniorNotesPayable'],
    'convertible_current': ['ConvertibleNotesPayableCurrent', 'ConvertibleDebtCurrent'],
    'debt_fair_value': ['LongTermDebtFairValue', 'DebtInstrumentFairValue'],
    'revolver_capacity': ['LineOfCreditFacilityMaximumBorrowingCapacity'],
    'revolver_available': ['LineOfCreditFacilityRemainingBorrowingCapacity'],
    'revolver_drawn': ['LineOfCredit', 'LongTermLineOfCredit', 'LinesOfCreditCurrent'],
    'equity': ['StockholdersEquity', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'],
    'assets': ['Assets'],
    'liabilities': ['Liabilities'],
    'assets_current': ['AssetsCurrent'],
    'liabilities_current': ['LiabilitiesCurrent'],
    'retained_earnings': ['RetainedEarningsAccumulatedDeficit'],
    'deposits': ['Deposits'],
    'time_deposits': ['TimeDeposits'],
}
FLOWS = {    # durations, trailing twelve months
    'interest_expense': ['InterestExpense', 'InterestExpenseNonoperating', 'InterestExpenseDebt', 'InterestAndDebtExpense',
                         'InterestExpenseRelatedParty', 'InterestCostsIncurred'],
    'interest_paid': ['InterestPaidNet', 'InterestPaid'],
    'operating_income': ['OperatingIncomeLoss'],
    'pretax_income': ['IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest',
                      'IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments'],
    'net_income': ['NetIncomeLoss', 'ProfitLoss'],
    'da': ['DepreciationDepletionAndAmortization', 'DepreciationAmortizationAndAccretionNet', 'DepreciationAndAmortization',
           'Depreciation'],
    'ocf': ['NetCashProvidedByUsedInOperatingActivities', 'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations'],
    'capex': ['PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsToAcquireProductiveAssets'],
    'revenue': ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'SalesRevenueNet',
                'RevenueFromContractWithCustomerIncludingAssessedTax'],
    'debt_issued': ['ProceedsFromIssuanceOfLongTermDebt', 'ProceedsFromIssuanceOfSeniorLongTermDebt', 'ProceedsFromIssuanceOfDebt',
                    'ProceedsFromConvertibleDebt'],
    'debt_repaid': ['RepaymentsOfLongTermDebt', 'RepaymentsOfDebt', 'RepaymentsOfSeniorDebt'],
    'converted_amount': ['DebtConversionConvertedInstrumentAmount1', 'DebtConversionOriginalDebtAmount1'],
    'deposit_interest': ['InterestExpenseDeposits'],
}
MATURITY = [('next12m', ['LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths']),
            ('rest_of_year', ['LongTermDebtMaturitiesRepaymentsOfPrincipalRemainderOfFiscalYear']),
            ('y2', ['LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo']),
            ('y3', ['LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree']),
            ('y4', ['LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour']),
            ('y5', ['LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive']),
            ('after5', ['LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive'])]
RATES = {    # 'pure' units (0.0435 = 4.35%)
    'wavg_rate_long': ['LongTermDebtWeightedAverageInterestRate', 'LongtermDebtWeightedAverageInterestRate'],
    'wavg_rate_short': ['ShortTermDebtWeightedAverageInterestRate', 'ShortTermBorrowingsWeightedAverageInterestRate',
                        'CommercialPaperWeightedAverageInterestRate'],
    'wavg_rate_all': ['DebtWeightedAverageInterestRate'],
    'effective_rate': ['DebtInstrumentInterestRateEffectivePercentage'],
    'stated_rate': ['DebtInstrumentInterestRateStatedPercentage'],
    'revolver_fee': ['LineOfCreditFacilityCommitmentFeePercentage'],
    'revolver_rate': ['LineOfCreditFacilityInterestRateAtPeriodEnd'],
    'fixed_share': ['LongTermDebtPercentageBearingFixedInterestRate'],
    'variable_share': ['LongTermDebtPercentageBearingVariableInterestRate'],
}
CONVERT = {'conversion_price': (['DebtInstrumentConvertibleConversionPrice1'], 'USD/shares'),
           'conversion_ratio': (['DebtInstrumentConvertibleConversionRatio1'], 'pure'),
           'if_converted_shares': (['IncrementalCommonSharesAttributableToConversionOfDebtSecurities'], 'shares'),
           'converted_shares': (['DebtConversionConvertedInstrumentSharesIssued1'], 'shares')}


def _d(s):
    return dt.date.fromisoformat(s)


def facts_of(cf, concept, unit='USD', taxonomy='us-gaap'):
    """[{start?, end, val, filed, form, accn, fy, fp}] for one concept and unit, newest filing per period kept."""
    node = (cf.get('facts', {}).get(taxonomy, {}) or {}).get(concept)
    if not node:
        return []
    rows = node.get('units', {}).get(unit) or []
    best = {}
    for r in rows:
        if r.get('val') is None or not r.get('end'):
            continue
        k = (r.get('start'), r['end'])
        if k not in best or (r.get('filed') or '') > (best[k].get('filed') or ''):
            best[k] = r
    return sorted(best.values(), key=lambda r: (r['end'], r.get('start') or ''))


def instants(cf, concept, unit='USD', taxonomy='us-gaap', as_of=None):
    """{end: (val, filed)} of point-in-time facts; with as_of only facts filed by then."""
    out = {}
    for r in facts_of(cf, concept, unit, taxonomy):
        if r.get('start'):
            continue
        if as_of and (r.get('filed') or '9999') > as_of:
            continue
        out[r['end']] = (r['val'], r.get('filed'))
    return out


def latest_instant(cf, family, as_of=None, unit='USD', min_end=None):
    """(value, end, concepts) for the first family entry whose concepts all have a value at the same latest date."""
    best = None
    for combo in family:
        series = [instants(cf, c, unit, as_of=as_of) for c in combo]
        if not all(series):
            continue
        common = set(series[0])
        for s in series[1:]:
            common &= set(s)
        if not common:
            continue
        end = max(common)
        if min_end and end < min_end:
            continue
        val = sum(s[end][0] for s in series)
        if best is None or end > best[1]:
            best = (val, end, combo)
    return best


def value_at(cf, family, end, as_of=None, unit='USD'):
    """(value, end, concepts) of the first family entry whose concepts all have a value at exactly that date."""
    for combo in family:
        series = [instants(cf, c, unit, as_of=as_of) for c in combo]
        if all(end in s for s in series):
            return sum(s[end][0] for s in series), end, combo
    return None


def durations(cf, concept, unit='USD', as_of=None):
    out = []
    for r in facts_of(cf, concept, unit):
        if not r.get('start'):
            continue
        if as_of and (r.get('filed') or '9999') > as_of:
            continue
        days = (_d(r['end']) - _d(r['start'])).days
        out.append((r['start'], r['end'], days, r['val'], r.get('filed')))
    return out


def ttm(cf, concepts, as_of=None, unit='USD'):
    """(value, end, concept, how): the trailing twelve months at the latest period end, from 3-month quarters, a fiscal
    year, or FY + YTD − prior YTD."""
    best = None
    for c in concepts:
        rows = durations(cf, c, unit, as_of)
        if not rows:
            continue
        by = {(s, e): v for s, e, _, v, _ in rows}
        fys = [(s, e, v) for s, e, d, v, _ in rows if 350 <= d <= 380]
        ends = sorted({e for _, e, _, _, _ in rows}, reverse=True)
        for end in ends[:3]:
            got = None
            fy = next(((s, e, v) for s, e, v in fys if e == end), None)
            if fy:
                got = (fy[2], 'fiscal year')
            else:
                q = sorted([(s, e, v) for s, e, d, v, _ in rows if 80 <= d <= 100], key=lambda x: x[1])
                qe = [x for x in q if x[1] <= end]
                if len(qe) >= 4 and qe[-1][1] == end:
                    last4 = qe[-4:]
                    span = (_d(last4[-1][1]) - _d(last4[0][0])).days
                    if 350 <= span <= 380:
                        got = (sum(x[2] for x in last4), 'four quarters')
                if got is None:
                    ytd = [(s, e, d, v) for s, e, d, v, _ in rows if e == end and 80 <= d <= 290]
                    for s, e, d, v in sorted(ytd, key=lambda x: -x[2]):
                        prior_fy = next(((a, b, w) for a, b, w in fys if b < e and 0 <= (_d(s) - _d(b)).days <= 7), None)
                        if not prior_fy:
                            continue
                        py_end = _d(e) - dt.timedelta(days=364)
                        py = next((w for (a, b), w in by.items() if a and abs((_d(b) - py_end).days) <= 10
                                   and abs((_d(b) - _d(a)).days - d) <= 10), None)
                        if py is not None:
                            got = (prior_fy[2] + v - py, 'FY + YTD − prior YTD')
                            break
            if got:
                if best is None or end > best[1]:
                    best = (got[0], end, c, got[1])
                break
    return best


def pure(cf, concepts, unit='pure', as_of=None):
    """Latest value of a rate / ratio concept (instant or duration), its date and concept."""
    best = None
    for c in concepts:
        for r in facts_of(cf, c, unit):
            if as_of and (r.get('filed') or '9999') > as_of:
                continue
            if best is None or r['end'] > best[1]:
                best = (r['val'], r['end'], c)
    return best


def shares_outstanding(cf, as_of=None):
    best = None
    for r in facts_of(cf, 'EntityCommonStockSharesOutstanding', 'shares', 'dei'):
        if as_of and (r.get('filed') or '9999') > as_of:
            continue
        if best is None or r['end'] > best[1]:
            best = (r['val'], r['end'])
    if best is None:
        for c in ('WeightedAverageNumberOfDilutedSharesOutstanding', 'CommonStockSharesOutstanding'):
            for r in facts_of(cf, c, 'shares'):
                if as_of and (r.get('filed') or '9999') > as_of:
                    continue
                if best is None or r['end'] > best[1]:
                    best = (r['val'], r['end'])
    return best


def latest_period(cf, as_of=None):
    """The company's latest balance-sheet date (from Assets / equity), to reject stale debt tags."""
    best = None
    for c in ('Assets', 'LiabilitiesAndStockholdersEquity', 'StockholdersEquity', 'Liabilities'):
        for end in instants(cf, c, as_of=as_of):
            best = max(best or end, end)
    return best


def snapshot(cf, as_of=None):
    """Every debt figure at the latest balance date (on or before as_of's filings). A debt total older than the latest
    balance sheet by more than ~6 months (a company that moved to its own tags) is left out rather than shown stale."""
    out, src = {}, {}
    lp = latest_period(cf, as_of)
    floor = _shift(lp, -200) if lp else None
    td = latest_instant(cf, TOTAL_DEBT, as_of, min_end=floor)
    end = td[1] if td else None
    if td:
        out['total_debt'], src['total_debt'] = td[0], '+'.join(td[2])
    for key, fam in (('current_debt', CURRENT_DEBT), ('cash', CASH), ('investments', INVEST)):
        v = value_at(cf, fam, end, as_of) if end else latest_instant(cf, fam, as_of, min_end=floor)
        if v:
            out[key], src[key] = v[0], '+'.join(v[2])
    for key, fam in SINGLE.items():
        v = latest_instant(cf, [[c] for c in fam], as_of, min_end=end or floor)
        if v and (end is None or v[1] >= end):
            out[key], src[key] = v[0], v[2][0]
    for key, fam in FLOWS.items():
        v = ttm(cf, fam, as_of)
        if v and (end is None or v[1] >= end) and (floor is None or v[1] >= floor):
            out[key], src[key] = v[0], f'{v[2]} ({v[3]})'
    lad, lad_end = {}, None
    for key, fam in MATURITY:
        v = latest_instant(cf, [[c] for c in fam], as_of, min_end=_shift(lp, -400) if lp else None)
        if v and (lad_end is None or v[1] >= lad_end):
            if lad_end is not None and v[1] > lad_end:
                lad = {}
            lad[key] = v[0]; lad_end = v[1]
    if lad:
        out['maturities'] = {'as_of': lad_end, **lad}
    for key, fam in RATES.items():
        v = pure(cf, fam, as_of=as_of)
        if v and (end is None or v[1] >= _shift(end, -400)):
            out[key], src[key] = v[0], v[2]
    for key, (fam, unit) in CONVERT.items():
        v = pure(cf, fam, unit, as_of=as_of)
        if v and (end is None or v[1] >= _shift(end, -400)):
            out[key], src[key] = v[0], v[2]
    sh = shares_outstanding(cf, as_of)
    if sh:
        out['shares'] = sh[0]
    out['balance_date'] = end or lp
    out['latest_period'] = lp
    return out, src


def _shift(d, days):
    return str(_d(d) + dt.timedelta(days=days))


def history(cf, since='2009-01-01'):
    """Quarter-end series: total debt, cash, interest expense (TTM), EBIT (TTM), D&A (TTM), each as filed then."""
    td_dates = set()
    for combo in TOTAL_DEBT[:8]:
        for c in combo:
            td_dates |= set(instants(cf, c))
    out = []
    for end in sorted(d for d in td_dates if d >= since):
        filed = None
        for combo in TOTAL_DEBT:
            ss = [instants(cf, c) for c in combo]
            if all(end in s for s in ss):
                filed = max(s[end][1] or '' for s in ss)
                break
        if not filed:
            continue
        snap, _ = snapshot(cf, as_of=filed)
        if snap.get('balance_date') != end:
            continue
        out.append({'end': end, 'filed': filed, **{k: snap.get(k) for k in ('total_debt', 'cash', 'investments', 'interest_expense',
                                                                            'operating_income', 'da', 'ocf', 'revenue', 'shares',
                                                                            'convertible', 'equity', 'interest_paid')}})
    return out


def num(v):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else v
