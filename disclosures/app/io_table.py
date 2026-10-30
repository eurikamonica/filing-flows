"""One company's input-output account (投入产出要素表), from its latest 10-K: what it produced and for whom, what it bought
and from which industries, and how the value it added was paid out to its factors — labour, capital, the state, lenders
and owners. Built by notes.py with the rest of the filing (the Notes view's "Inputs & outputs" pane), so each line
links to the note that discloses it.

  output        revenue, plus the year's build-up of finished goods and work in progress (inventory notes): gross
                output. Split by segment, product or service and region (the revenue notes' members), and the
                customers the concentration note names
  intermediate  purchased goods and services = operating spending (revenue less operating income, less depreciation
                and amortization) less pay and taxes on production; by supplying industry as BEA's Use table splits the
                company's industry's purchases (pipeline/data/bea_io.json; the imported share of each commodity goes to
                imports) — an estimate at industry-average precision: a 10-K does not list its suppliers by industry
  value added   pay (employees) + taxes on production + gross operating surplus; the surplus split into capital
                consumption (depreciation and amortization), interest, income tax, net income and the rest
  pay           as the 10-K states it where it is tagged (labour and related expense, salaries and wages); otherwise
                the 10-K's headcount (Workforce, app/employees.py) × the industry's compensation per full-time employee
                (BEA NIPA tables 6.2D / 6.5D, app/data/bea_pay.json) + stock-based pay; otherwise the industry's share of
                operating spending (the Use table)
  capital       capital spending (by the industry's asset mix: BEA fixed assets) and the stock it builds — property,
                plant and equipment, leased assets, inventories; purchase commitments as inputs already bought ahead
  banks and     revenue less pre-tax income is their spending; interest paid and credit losses or claims are shown as
  insurers      financial inputs, apart from purchases
Every line says where it comes from: the 10-K (with its note), derived from 10-K figures, or estimated (BEA).
"""
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
BEA_IO = HERE.parents[1] / 'pipeline' / 'data' / 'bea_io.json'
BEA_PAY = HERE / 'data' / 'bea_pay.json'
_cache = {}

REV = ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'RevenueFromContractWithCustomerIncludingAssessedTax',
       'SalesRevenueNet', 'RevenuesNetOfInterestExpense', 'RevenueFromContractsWithCustomers', 'Revenue']
COGS = ['CostOfRevenue', 'CostOfGoodsAndServicesSold', 'CostOfGoodsSold', 'CostOfServices', 'CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization']
RND = ['ResearchAndDevelopmentExpense', 'ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost']
SGA = ['SellingGeneralAndAdministrativeExpense']
OI = ['OperatingIncomeLoss']
EBT = ['IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest',
       'IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments',
       'IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic', 'ProfitLossBeforeTax']
DA = ['DepreciationDepletionAndAmortization', 'DepreciationAmortizationAndAccretionNet', 'DepreciationAndAmortization',
      'DepreciationAmortizationAndOther', 'DepreciationAndAmortisationExpense']
DEP = ['Depreciation', 'DepreciationNonproduction', 'DepreciationDepletionAndAmortizationPropertyPlantAndEquipment']
AMO = ['AmortizationOfIntangibleAssets']
PAY = ['LaborAndRelatedExpense', 'SalariesAndWages', 'SalariesWagesAndOfficersCompensation', 'EmployeeBenefitsAndShareBasedCompensation',
       'EmployeeBenefitsExpense', 'LaborCosts']
SBC = ['ShareBasedCompensation', 'AllocatedShareBasedCompensationExpense']
TAXPROD = ['TaxesExcludingIncomeAndExciseTaxes', 'ExciseAndSalesTaxes', 'OtherTaxExpenseBenefit', 'TaxesOther']
INTEREST = ['InterestExpense', 'InterestExpenseNonoperating', 'InterestExpenseDebt', 'InterestAndDebtExpense', 'InterestExpenseOperating', 'FinanceCosts']
PROV = ['ProvisionForLoanLeaseAndOtherLosses', 'ProvisionForCreditLossesNet', 'ProvisionForLoanAndLeaseLosses', 'CreditLossExpenseReversal',
        'PolicyholderBenefitsAndClaimsIncurredNet', 'BenefitsLossesAndExpenses', 'PolicyholderBenefitsAndClaimsIncurredGross']
INCTAX = ['IncomeTaxExpenseBenefit', 'IncomeTaxExpenseContinuingOperations']
NI = ['NetIncomeLoss', 'ProfitLoss', 'NetIncomeLossAvailableToCommonStockholdersBasic']
CAPEX = ['PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsToAcquireProductiveAssets', 'PaymentsForCapitalImprovements',
         'PaymentsToAcquireOtherPropertyPlantAndEquipment', 'PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities']
PPE = ['PropertyPlantAndEquipmentNet', 'PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization',
       'PropertyPlantAndEquipment']
PPEG = ['PropertyPlantAndEquipmentGross']
ROU = ['OperatingLeaseRightOfUseAsset']
LEASE = ['OperatingLeaseCost', 'LeaseCost', 'OperatingLeasesRentExpenseNet']
ADV = ['AdvertisingExpense', 'MarketingAndAdvertisingExpense']
INV = ['InventoryNet', 'InventoryGross', 'Inventories']
FG = ['InventoryFinishedGoodsNetOfReserves', 'InventoryFinishedGoods']
WIP = ['InventoryWorkInProcessNetOfReserves', 'InventoryWorkInProcess']
RAW = ['InventoryRawMaterialsNetOfReserves', 'InventoryRawMaterials', 'InventoryRawMaterialsAndSupplies']
PURCH = ['UnrecordedUnconditionalPurchaseObligationBalanceSheetAmount', 'PurchaseObligation', 'UnrecordedUnconditionalPurchaseObligationAmount',
         'ContractualObligation']
INTANG = ['IntangibleAssetsNetExcludingGoodwill', 'FiniteLivedIntangibleAssetsNet']
GW = ['Goodwill']
TAX_CAP = 0.04                                   # taxes on production (property, payroll) per dollar of spending, at most
GOODS = ('11', '21', '31', '32', '33', '42')      # BEA industries whose output is goods (and the wholesale margin on them)
OTHER_NAMES = {'_OTHER': 'Other commodities (scrap, used goods)', 'S00101': 'Federal government enterprises', 'S00102': 'Federal electric utilities',
               'S00201': 'State and local transit', 'S00202': 'State and local electric utilities', 'S00203': 'Other state and local enterprises',
               'S00500': 'General government', 'S00600': 'General government'}
SPLIT_AXES = [('segment', ('StatementBusinessSegmentsAxis', 'SegmentsAxis')), ('product', ('ProductOrServiceAxis',)),
              ('region', ('StatementGeographicalAxis', 'GeographicalAxis'))]


def fin(v):
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)


def _json(p):
    if str(p) not in _cache:
        try:
            _cache[str(p)] = json.loads(Path(p).read_text())
        except (OSError, ValueError):
            _cache[str(p)] = None
    return _cache[str(p)]


def bea_mix(io, sic):
    """{BEA detail industry: weight} for an SEC SIC code (pipeline/ioflow.py's rule: a code ending in 0 takes its
    three-digit group, in 00 its two-digit group, weighted by output)."""
    if not io:
        return {}
    sic = str(sic or '').zfill(4)
    m = io['sic'].get(sic)
    if m:
        return {b: w for b, w in m if b in io['industries']}
    for n in ((3, 2) if sic.endswith('00') else (3,) if sic.endswith('0') else ()):
        acc = {}
        for code, pairs in io['sic'].items():
            if code.startswith(sic[:n]):
                for b, _ in pairs:
                    if b in io['industries']:
                        acc[b] = io['industries'][b]['output']
        if acc:
            tot = sum(acc.values())
            return {b: v / tot for b, v in acc.items() if v / tot >= 0.01}
    return {}


def pay_line(pay, bea_code):
    """The NIPA industry line (compensation per full-time employee) of a BEA detail industry, by its NAICS prefix."""
    if not pay:
        return None
    nm = pay['naics']
    for k in range(min(4, len(bea_code)), 1, -1):
        ln = nm.get(bea_code[:k])
        if ln and str(ln) in pay['lines']:
            return str(ln)
    return '3'


class Get:
    """Facts of one filing by local name, period and dimensions, remembering which concept answered."""

    def __init__(self, FL):
        self.FL = FL

    def __call__(self, names, p, dims=()):
        if p is None:
            return None
        for nm in names:
            cands = ['us-gaap:' + nm] + [c for c in self.FL.by_local.get(nm, []) if not c.startswith('us-gaap:')]
            for c in cands:
                r = self.FL.num.get((c, p, dims))
                if r is not None and fin(r[0]):
                    return c, float(r[0])
        return None


def _v(x):
    return x[1] if x else None


def _label(FL, m):
    s = FL.label(m)
    for suf in (' [Member]', ' Member', ' Segment', ' segment'):
        if s.endswith(suf):
            s = s[: -len(suf)]
    return s.strip()


def splits(FL, rev_c, p, total):
    """Revenue by segment, product or service and region: {kind: [[label, value]]} (members of one axis only, largest
    first, totals and overlaps left out)."""
    out = {}
    if not rev_c or not total:
        return out
    local = rev_c.split(':')[-1]
    concepts = [c for c in FL.by_local.get(local, [])] + [c for nm in REV for c in FL.by_local.get(nm, []) if nm != local]
    for kind, axes in SPLIT_AXES:
        best = []
        for c in concepts:
            vals = {}
            for (cc, pp, dims), r in FL.num.items():
                if cc != c or pp != p or len(dims) != 1:
                    continue
                ax, m = dims[0]
                if ax.split(':')[-1] in axes and fin(r[0]) and r[0] > 0:
                    vals[m] = float(r[0])
            items = sorted(vals.items(), key=lambda x: -x[1])
            keep, cum = [], 0.0
            for m, v in items:
                if v >= 0.985 * total and len(items) > 1:
                    continue                                   # a total under another name
                if len(items) > 2 and _label(FL, m).lower().startswith(('total ', 'all ')):
                    continue                                   # a subtotal of members listed beside it
                if cum + v > 1.03 * total:
                    continue                                   # overlaps an item already kept (a region and its country)
                keep.append([_label(FL, m), v])
                cum += v
            if len(keep) >= 2 and cum >= 0.5 * total and len(keep) > len(best):
                best = keep
        if best:
            out[kind] = best[:12]
    return out


def customers(FL, p):
    """The customers the concentration note names, with their share of revenue."""
    out = []
    for (c, pp, dims), r in FL.num.items():
        if pp != p or not c.endswith('ConcentrationRiskPercentage1') or not fin(r[0]):
            continue
        d = dict(dims)
        bench = next((m for a, m in d.items() if a.endswith('ConcentrationRiskByBenchmarkAxis')), '')
        typ = next((m for a, m in d.items() if a.endswith('ConcentrationRiskByTypeAxis')), '')
        if not any(k in bench for k in ('Revenue', 'SalesRevenue', 'Sales')):
            continue
        if typ and 'Customer' not in typ:
            continue
        who = [m for a, m in d.items() if not a.endswith(('ConcentrationRiskByBenchmarkAxis', 'ConcentrationRiskByTypeAxis'))]
        if len(who) != 1:
            continue
        v = float(r[0])
        v = v / 100 if v > 1.5 else v
        if 0 < v <= 1:
            out.append([_label(FL, who[0]), round(v, 4)])
    seen, res = set(), []
    for lab, v in sorted(out, key=lambda x: -x[1]):
        if lab not in seen:
            seen.add(lab)
            res.append([lab, v])
    return res[:8]


def account(FL, g, p, i_end, i_open, sic, fin_co, employees, mix, io, pay):
    """The year's account for duration p (balance sheet at i_end, i_open). → dict of values and their concepts."""
    a, src = {}, {}

    def take(key, names, period=p):
        r = g(names, period)
        if r:
            a[key], src[key] = r[1], r[0]
        return r
    rev = take('revenue', REV)
    if not rev and fin_co:
        ii = g(['InterestAndDividendIncomeOperating', 'InterestIncomeOperating'], p)
        ni_ = g(['NoninterestIncome'], p)
        if ii:
            a['revenue'] = ii[1] + (ni_[1] if ni_ else 0)
            src['revenue'] = ii[0]
    if not a.get('revenue') or a['revenue'] <= 0:
        return None
    for k, names in (('cogs', COGS), ('rnd', RND), ('sga', SGA), ('oi', OI), ('ebt', EBT), ('sbc', SBC), ('pay', PAY), ('taxprod', TAXPROD),
                     ('interest', INTEREST), ('inctax', INCTAX), ('ni', NI), ('capex', CAPEX), ('lease', LEASE), ('adv', ADV), ('prov', PROV)):
        take(k, names)
    if not take('da', DA):
        d1, d2 = g(DEP, p), g(AMO, p)
        if d1 or d2:
            a['da'] = (_v(d1) or 0) + (_v(d2) or 0)
            src['da'] = (d1 or d2)[0]
    for k in ('interest', 'capex', 'da', 'sbc', 'lease', 'adv', 'prov'):
        if k in a:
            a[k] = abs(a[k])
    for k, names in (('ppe', PPE), ('ppeg', PPEG), ('rou', ROU), ('inv', INV), ('fg', FG), ('wip', WIP), ('raw', RAW), ('purch', PURCH),
                     ('intang', INTANG), ('gw', GW)):
        take(k, names, i_end)
    for k, names in (('inv0', INV), ('fg0', FG), ('wip0', WIP)):
        r = g(names, i_open)
        if r:
            a[k], src[k] = r[1], r[0]
    notes = []
    R = a['revenue']
    # inventory build of the company's own products (finished goods and work in progress): output not yet sold
    dinv = None
    if 'fg' in a and 'fg0' in a:
        dinv = (a['fg'] - a['fg0']) + ((a.get('wip', 0) - a.get('wip0', 0)) if 'wip' in a and 'wip0' in a else 0)
    a['dinv'] = dinv
    out = R + (dinv or 0.0)
    # what the year's operations cost (spending), and what of it was financial (banks and insurers)
    finc = 0.0
    if fin_co:
        if 'ebt' not in a:
            return None
        costs = R - a['ebt']
        gross_interest = src.get('revenue', '').split(':')[-1].startswith('Interest')   # revenue read as interest income + other
        finc = a.get('prov', 0.0) + (a.get('interest', 0.0) if gross_interest else 0.0)    # banks' net revenue is after interest
        a['gross_interest'] = gross_interest
    else:
        if 'oi' in a:
            costs = R - a['oi']
        elif 'ebt' in a:
            costs = R - a['ebt'] - a.get('interest', 0.0)
            notes.append('No operating income tagged: pre-tax income plus interest stands in for it.')
        else:
            return None
    da = a.get('da', 0.0)
    if 'da' not in a:
        notes.append('No depreciation and amortization tagged: capital consumption is left at zero.')
    spend = max(0.0, costs - finc - da)
    # the industry's shares (BEA Use table): pay, purchases and taxes on production per dollar of operating spending
    I = (io or {}).get('industries', {})
    w = {b: x for b, x in mix.items() if b in I}
    tw = sum(w.values()) or 1.0
    w = {b: x / tw for b, x in w.items()}
    sh = {k: sum(x * I[b][k] for b, x in w.items()) for k in ('comp', 'inter', 'tax')} if w else {'comp': 0.3, 'inter': 0.65, 'tax': 0.05}
    norm = sum(sh.values()) or 1.0
    sh = {k: v / norm for k, v in sh.items()}
    # pay
    how = None
    if 'pay' in a and a['pay'] > 0:
        comp, how = a['pay'], 'disclosed'
    elif employees and pay and w:
        lines = {}
        for b, x in w.items():
            ln = pay_line(pay, b)
            lines[ln] = lines.get(ln, 0) + x
        per = sum(x * pay['lines'][ln][1] for ln, x in lines.items())      # per employee, part-time staff counted as one
        comp = employees * per + a.get('sbc', 0.0)
        how = 'headcount'
        a['pay_per_fte'] = per
        a['pay_line'] = pay['lines'][max(lines, key=lines.get)][0]
    else:
        comp, how = spend * sh['comp'], 'industry'
    if how != 'disclosed':
        lo, hi = a.get('sbc', 0.0), 0.9 * spend
        if comp > hi:
            comp = hi
            notes.append('Estimated pay capped at 90% of operating spending.')
        comp = max(comp, lo)
    a['comp'], a['comp_how'] = comp, how
    taxp = a['taxprod'] if 'taxprod' in a and a['taxprod'] > 0 else spend * min(sh['tax'], TAX_CAP)   # sales and excise taxes are not in revenue
    a['taxp'], a['taxp_how'] = taxp, 'disclosed' if 'taxprod' in a and a['taxprod'] > 0 else 'industry'
    inter = spend - comp - taxp
    if inter < 0:
        notes.append('Pay and taxes exceed operating spending: purchases set to zero.')
        inter = 0.0
    a['inter'], a['spend'], a['finc'], a['output'] = inter, spend, finc, out
    va = out - inter - finc
    gos = va - comp - taxp
    a['va'], a['gos'] = va, gos
    # the surplus: who received it
    if fin_co:
        rest = gos - da - a.get('inctax', 0.0) - a.get('ni', 0.0) - (dinv or 0.0)
    else:
        rest = gos - da - a.get('interest', 0.0) - a.get('inctax', 0.0) - a.get('ni', 0.0) - (dinv or 0.0)
    a['gos_rest'] = rest
    a['notes'] = notes
    a['src'] = src
    a['shares'] = sh
    return a


def input_groups(io, mix, A, sic):
    """Purchases in groups, each by supplying industry: for goods producers (SIC 01–39) materials, components and
    contract manufacturing — cost of revenue less the pay and depreciation it carries (each function's share of costs)
    — over the industries that make goods, and the rest over services, rent and energy; for wholesalers and retailers
    (SIC 50–59) the merchandise bought for resale (cost of revenue; whose it is the 10-K does not say) and the rest;
    otherwise all purchases over the industry's whole mix."""
    I = io['industries']
    w = {b: x for b, x in mix.items() if b in I}
    tw = sum(w.values()) or 1.0
    vec, imp = {}, 0.0
    for b, x in w.items():
        for i, s_ in I[b]['suppliers'].items():
            vec[i] = vec.get(i, 0.0) + x / tw * s_
        imp += x / tw * I[b]['imports']
    inter = A['inter']
    name = lambda i: OTHER_NAMES.get(i) or (I.get(i) or {}).get('name') or i
    fns = [A.get(k) for k in ('cogs', 'rnd', 'sga') if fin(A.get(k)) and A.get(k) > 0]
    cogs_share = A['cogs'] / sum(fns) if fin(A.get('cogs')) and A['cogs'] > 0 and fns else None

    def spread(total, keys, with_imports, n=10):
        sh = {i: vec[i] for i in keys}
        tot = sum(sh.values()) + (imp if with_imports else 0.0)
        if total <= 0 or tot <= 0:
            return [], 0.0
        items = sorted(sh.items(), key=lambda x: -x[1])
        out = [[name(i), round(total * v / tot), round(v / tot, 4)] for i, v in items[:n] if v > 0]
        rest = sum(v for _, v in items[n:])
        if rest > 0:
            out.append(['All other industries', round(total * rest / tot), round(rest / tot, 4)])
        return out, round(total * imp / tot) if with_imports else 0
    goods_keys = [i for i in vec if i[:2] in GOODS]
    serv_keys = [i for i in vec if i[:2] not in GOODS]
    sic2 = int(sic[:2]) if sic and sic[:2].isdigit() else None
    if sic2 is not None and 50 <= sic2 <= 59 and cogs_share:
        resale = min(inter, A['cogs'])
        rest_sup, _ = spread(inter - resale, list(vec), False)
        return [{'k': 'resale', 'name': 'Merchandise bought for resale', 'v': round(resale), 'suppliers': [], 'imports': None,
                 'note': 'Cost of revenue: the goods it sells, from manufacturers and wholesalers the 10-K does not name'},
                {'k': 'other', 'name': 'Services, rent, energy and other purchases', 'v': round(inter - resale), 'suppliers': rest_sup, 'imports': 0}]
    if sic2 is not None and sic2 <= 39 and cogs_share:
        goods = A['cogs'] - (A['comp'] + A.get('da', 0.0)) * cogs_share
        goods = max(0.0, min(inter, goods))
        gs, gi = spread(goods, goods_keys, True)
        ss, _ = spread(inter - goods, serv_keys, False)
        return [{'k': 'goods', 'name': 'Materials, components and contract manufacturing', 'v': round(goods), 'suppliers': gs, 'imports': gi,
                 'note': 'Cost of revenue less the pay and depreciation it carries (each in proportion to cost of revenue among the costs)'},
                {'k': 'services', 'name': 'Services, rent, energy and other purchases', 'v': round(inter - goods), 'suppliers': ss, 'imports': 0}]
    al, ai = spread(inter, list(vec), True, 12)
    return [{'k': 'all', 'name': 'Goods and services bought', 'v': round(inter), 'suppliers': al, 'imports': ai}]


def suppliers(io, mix, inter, capex):
    """Purchases and capital spending by supplying industry (BEA Use table and fixed assets): ([[name, $, share]],
    imports $, [[name, $, share]], imports $)."""
    I = io['industries']
    w = {b: x for b, x in mix.items() if b in I}
    tw = sum(w.values()) or 1.0
    sup, imp = {}, 0.0
    for b, x in w.items():
        for i, s in I[b]['suppliers'].items():
            sup[i] = sup.get(i, 0.0) + inter * x / tw * s
        imp += inter * x / tw * I[b]['imports']
    cs, cimp = {}, 0.0
    inv = io.get('invest') or {}
    for b, x in w.items():
        cm = (io.get('capex') or {}).get(I[b].get('fa') or '') or inv
        for i, s in (cm.get('suppliers') or {}).items():
            cs[i] = cs.get(i, 0.0) + capex * x / tw * s
        cimp += capex * x / tw * (cm.get('imports') or 0.0)

    def top(d, tot, n):
        items = sorted(d.items(), key=lambda x: -x[1])
        keep = [[OTHER_NAMES.get(i) or (I.get(i) or {}).get('name') or i, v, v / tot if tot else None] for i, v in items[:n] if v > 0]
        rest = sum(v for _, v in items[n:])
        if rest > 0:
            keep.append(['All other industries', rest, rest / tot if tot else None])
        return keep
    return top(sup, inter, 12), imp, top(cs, capex, 8), cimp


def build_io(FL, meta, concept_notes, sic=None, employees=None):
    """The input-output account of the filing's latest fiscal year (and the year before where it was filed)."""
    io, pay = _json(BEA_IO), _json(BEA_PAY)
    g = Get(FL)
    p, p0 = FL.dur(0), FL.dur(1)
    if not p:
        return None
    sic = str(sic or meta.get('sic') or '').zfill(4) if (sic or meta.get('sic')) else ''
    fin_co = bool(sic) and (sic[:2] in ('60', '61', '62', '63', '64') or (sic[:2] == '67' and sic != '6798'))
    mix = bea_mix(io, sic) if sic else {}
    emp = employees.get('employees') if employees else None
    r0 = g(REV, p)
    if emp and r0 and not 1e4 <= r0[1] / emp <= 5e7:
        emp = None                                     # a headcount that cannot be right (revenue per employee off the scale)
    A = account(FL, g, p, FL.inst(0), FL.opening(0) or FL.inst(1), sic, fin_co, emp, mix, io, pay)
    if not A:
        return None
    B = account(FL, g, p0, FL.inst(1), FL.opening(1), sic, fin_co, None, mix, io, pay) if p0 else None
    if B and A['comp_how'] == 'headcount' and B['comp_how'] != 'disclosed' and A['spend']:
        B['comp'] = min(0.9 * B['spend'], A['comp'] / A['spend'] * B['spend'])  # last year's pay at this year's ratio
        B['comp_how'] = 'headcount'
        B['inter'] = max(0.0, B['spend'] - B['comp'] - B['taxp'])
        B['va'] = B['output'] - B['inter'] - B['finc']
        B['gos'] = B['va'] - B['comp'] - B['taxp']
        B['gos_rest'] = B['gos'] - B.get('da', 0) - (0 if fin_co else B.get('interest', 0)) - B.get('inctax', 0) - B.get('ni', 0)

    def ln(group, key, label, src=None, how=None, note=None, of=None):
        v = A.get(key)
        if v is None:
            return None
        c = A['src'].get(src or key)
        ns = sorted(concept_notes.get(c, ()), key=lambda x: int(x[1:])) if c else []
        return {'g': group, 'k': key, 'label': label, 'v': round(v), 'v0': round(B[key]) if B and fin(B.get(key)) else None,
                'pct': round(v / A['output'], 4) if A['output'] else None, 'src': how or ('10-K' if c else 'derived'), 'c': c, 'notes': ns[:4],
                **({'note': note} if note else {})}
    fin_label = ('Interest paid, credit losses and claims' if A.get('gross_interest') else 'Credit losses and claims') + ' (financial inputs)'
    if A['comp_how'] == 'headcount':
        comp_note = (f"{emp:,.0f} employees (10-K) × ${A.get('pay_per_fte', 0):,.0f} average pay and benefits per employee in "
                     f"{A.get('pay_line', 'its industry')} (BEA, {(pay or {}).get('year')}) + stock-based pay")
    elif A['comp_how'] == 'industry':
        comp_note = f"{A['shares']['comp'] * 100:.0f}% of operating spending, its industry's share of pay (BEA Use table)"
    else:
        comp_note = None
    L = [ln('output', 'revenue', 'Revenue'),
         ln('output', 'dinv', 'Inventory build (finished goods and work in progress)', src='fg', note='Output made but not yet sold') if A.get('dinv') else None,
         ln('output', 'output', 'Gross output', how='derived'),
         ln('inter', 'inter', 'Purchased goods and services (intermediate inputs)', how='derived',
            note='Operating spending less pay and taxes on production'),
         ln('fin', 'finc', fin_label, how='derived') if fin_co else None,
         ln('va', 'va', 'Value added', how='derived'),
         ln('va', 'comp', 'Pay: employees\' wages, benefits and stock pay', src='pay',
            how='10-K' if A['comp_how'] == 'disclosed' else 'estimate', note=comp_note),
         ln('va', 'sbc', '… of which stock-based pay'),
         ln('va', 'taxp', 'Taxes on production (property, payroll, excise)', src='taxprod', how='10-K' if A['taxp_how'] == 'disclosed' else 'estimate',
            note=None if A['taxp_how'] == 'disclosed' else f"{A['shares']['tax'] * 100:.1f}% of operating spending (BEA Use table)"),
         ln('va', 'gos', 'Gross operating surplus (to capital, lenders, the state and owners)', how='derived'),
         ln('gos', 'da', 'Capital consumption: depreciation and amortization'),
         ln('gos', 'interest', 'Interest to lenders') if not fin_co else None,
         ln('gos', 'inctax', 'Income tax'),
         ln('gos', 'ni', 'Net income to owners'),
         ln('gos', 'dinv', 'Kept as inventory (output not yet sold)', src='fg') if A.get('dinv') else None,
         ln('gos', 'gos_rest', 'Other: non-operating gains (−) or costs (+), minority interests', how='derived') if abs(A.get('gos_rest', 0)) > 0.005 * A['output'] else None]
    L = [x for x in L if x]
    capital = [x for x in (ln('cap', 'capex', 'Capital spending (property, plant and equipment)'), ln('cap', 'ppe', 'Property, plant and equipment, net'),
                           ln('cap', 'ppeg', 'Property, plant and equipment, at cost'), ln('cap', 'rou', 'Leased assets (operating lease right of use)'),
                           ln('cap', 'lease', 'Operating lease cost'), ln('cap', 'intang', 'Intangible assets'), ln('cap', 'gw', 'Goodwill'),
                           ln('cap', 'inv', 'Inventories'), ln('cap', 'raw', '… raw materials'), ln('cap', 'wip', '… work in process'), ln('cap', 'fg', '… finished goods'),
                           ln('cap', 'purch', 'Purchase commitments (inputs bought ahead)')) if x]
    functional = [x for x in (ln('fn', 'cogs', 'Cost of revenue'), ln('fn', 'rnd', 'Research and development'), ln('fn', 'sga', 'Selling, general and administrative'),
                              ln('fn', 'adv', 'Advertising'), ln('fn', 'oi', 'Operating income')) if x]
    sup, imp, csup, cimp = suppliers(io, mix, A['inter'], A.get('capex', 0.0)) if io and mix else ([], None, [], None)
    va, out_ = A['va'], A['output']
    R = {'inter_share': A['inter'] / out_ if out_ else None, 'va_share': va / out_ if out_ else None,
         'labor_share': A['comp'] / va if va > 0 else None, 'capital_share': A['gos'] / va if va > 0 else None,
         'tax_share': (A['taxp'] + A.get('inctax', 0)) / va if va > 0 else None, 'da_share': A.get('da', 0) / va if va > 0 else None,
         'rnd_intensity': A['rnd'] / A['revenue'] if 'rnd' in A else None, 'capex_to_da': A['capex'] / A['da'] if A.get('capex') and A.get('da') else None,
         'capital_output': A['ppe'] / A['revenue'] if 'ppe' in A else None,
         'import_content': (imp + (cimp or 0)) / (A['inter'] + A.get('capex', 0)) if imp is not None and (A['inter'] + A.get('capex', 0)) > 0 else None}
    labor = None
    if emp:
        labor = {'employees': emp, 'as_of': employees.get('as_of'), 'revenue_per': A['revenue'] / emp, 'va_per': va / emp, 'pay_per': A['comp'] / emp,
                 'ppe_per': A['ppe'] / emp if 'ppe' in A else None, 'source': 'the 10-K\'s headcount (Workforce)'}
    I = (io or {}).get('industries', {})
    return {'fy': FL.fy_label(0), 'fy_prev': FL.fy_label(1) if p0 else None, 'financial': fin_co, 'sic': sic or None, 'fin_label': fin_label if fin_co else None,
            'industry': [[b, I[b]['name'], round(x, 3)] for b, x in sorted(mix.items(), key=lambda x: -x[1])][:4],
            'shares': {k: round(v, 4) for k, v in A['shares'].items()}, 'comp_how': A['comp_how'],
            'lines': L, 'capital': capital, 'functional': functional,
            'splits': {k: [[lab, round(v)] for lab, v in vals] for k, vals in splits(FL, A['src'].get('revenue'), p, A['revenue']).items()},
            'customers': customers(FL, p), 'inputs': input_groups(io, mix, A, sic) if io and mix else [],
            'suppliers': [[n, round(v), round(s, 4) if s is not None else None] for n, v, s in sup],
            'imports': round(imp) if imp is not None else None, 'capex_suppliers': [[n, round(v), round(s, 4) if s is not None else None] for n, v, s in csup],
            'capex_imports': round(cimp) if cimp is not None else None, 'ratios': {k: round(v, 4) if fin(v) else None for k, v in R.items()},
            'labor': {k: (round(v) if isinstance(v, float) else v) for k, v in labor.items()} if labor else None, 'notes': A['notes']}
