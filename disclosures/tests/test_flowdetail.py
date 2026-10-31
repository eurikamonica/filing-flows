"""app/flowdetail.py: the detailed Sankey on a small made-up filing (statements, a note that splits other income, revenue by
product members, a cash flow statement)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import notes as N               # noqa: E402
import flowdetail as D          # noqa: E402

G = 'us-gaap:'
CTX = {'Q': ('2026-01-01', '2026-03-31'), 'PQ': ('2025-01-01', '2025-03-31')}
AX = 'srt:ProductOrServiceAxis'


def filing(q, pq, members=None, nonop_note=True, segs=None):
    """q, pq: {local concept: value} of the quarter and the same quarter a year earlier (a first quarter: the year to date)."""
    contexts = {k: {'s': s, 'e': e, 'dims': {}} for k, (s, e) in CTX.items()}
    facts = [{'c': 'dei:DocumentPeriodEndDate', 'v': '2026-03-31', 'ctx': 'Q', 'u': None, 'd': None, 'id': None},
             {'c': 'dei:DocumentType', 'v': '10-Q', 'ctx': 'Q', 'u': None, 'd': None, 'id': None},
             {'c': 'dei:DocumentFiscalPeriodFocus', 'v': 'Q1', 'ctx': 'Q', 'u': None, 'd': None, 'id': None}]
    for cid, vals in (('Q', q), ('PQ', pq)):
        for c, v in vals.items():
            facts.append({'c': (c if ':' in c else G + c), 'v': float(v), 'ctx': cid, 'u': 'USD', 'd': '-6', 'id': None})
    for cid, ms in (members or {}).items():
        for m, v in ms.items():
            k = f'{cid}_{m}'
            contexts[k] = {'s': CTX[cid][0], 'e': CTX[cid][1], 'dims': {AX: 'x:' + m}}
            facts.append({'c': G + 'Revenues', 'v': float(v), 'ctx': k, 'u': 'USD', 'd': '-6', 'id': None})
    for m, vals in (segs or {}).items():               # a segment's own lines (ASU 2023-07), with the consolidation member
        k = f'S_{m}'
        contexts[k] = {'s': CTX['Q'][0], 'e': CTX['Q'][1], 'dims': {D.SEG_AXIS: 'x:' + m, D.CONS_AXIS: 'srt:OperatingSegmentsMember'}}
        for c, v in vals.items():
            facts.append({'c': G + c, 'v': float(v), 'ctx': k, 'u': 'USD', 'd': '-6', 'id': None})
    cal = {
        'R_IS': {G + 'NetIncomeLoss': [(G + 'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest', 1.0), (G + 'IncomeTaxExpenseBenefit', -1.0)],
                 G + 'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest': [(G + 'OperatingIncomeLoss', 1.0), (G + 'NonoperatingIncomeExpense', 1.0)],
                 G + 'OperatingIncomeLoss': [(G + 'GrossProfit', 1.0), (G + 'OperatingExpenses', -1.0)],
                 G + 'GrossProfit': [(G + 'Revenues', 1.0), (G + 'CostOfRevenue', -1.0)],
                 G + 'OperatingExpenses': [(G + 'ResearchAndDevelopmentExpense', 1.0), (G + 'SellingGeneralAndAdministrativeExpense', 1.0)]},
        'R_CF': {G + 'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect':
                 [(G + 'NetCashProvidedByUsedInOperatingActivities', 1.0), (G + 'NetCashProvidedByUsedInInvestingActivities', 1.0), (G + 'NetCashProvidedByUsedInFinancingActivities', 1.0)],
                 G + 'NetCashProvidedByUsedInOperatingActivities': [(G + 'NetIncomeLoss', 1.0), (G + 'DepreciationDepletionAndAmortization', 1.0),
                                                                    (G + 'ShareBasedCompensation', 1.0), (G + 'IncreaseDecreaseInAccountsReceivable', -1.0)],
                 G + 'NetCashProvidedByUsedInInvestingActivities': [(G + 'PaymentsToAcquirePropertyPlantAndEquipment', -1.0), (G + 'ProceedsFromSaleOfPropertyPlantAndEquipment', 1.0)],
                 G + 'NetCashProvidedByUsedInFinancingActivities': [(G + 'PaymentsForRepurchaseOfCommonStock', -1.0), (G + 'PaymentsOfDividends', -1.0)]},
    }
    if nonop_note:
        cal['R_D1'] = {G + 'NonoperatingIncomeExpense': [(G + 'InvestmentIncomeInterest', 1.0), (G + 'InterestExpenseNonoperating', -1.0), (G + 'OtherNonoperatingIncomeExpense', 1.0)]}
    reports = [{'cat': 'Statements', 'short': 'Consolidated Statements of Operations', 'role': 'R_IS', 'pos': 1, 'r': 'R2', 'parent': None},
               {'cat': 'Statements', 'short': 'Consolidated Statements of Cash Flows', 'role': 'R_CF', 'pos': 2, 'r': 'R3', 'parent': None},
               {'cat': 'Notes', 'short': 'Other Income (Expense)', 'role': 'R_N1', 'pos': 3, 'r': 'R4', 'parent': None},
               {'cat': 'Details', 'short': 'Other Income (Expense) - Components (Details)', 'role': 'R_D1', 'pos': 4, 'r': 'R5', 'parent': 'R_N1'}]
    pre = {'R_IS': [{'c': G + c, 'depth': 1, 'pref': None} for c in ('Revenues', 'CostOfRevenue', 'GrossProfit', 'ResearchAndDevelopmentExpense',
                                                                       'SellingGeneralAndAdministrativeExpense', 'OperatingExpenses', 'OperatingIncomeLoss',
                                                                       'NonoperatingIncomeExpense', 'IncomeTaxExpenseBenefit', 'NetIncomeLoss')]}
    F = {'reports': reports, 'contexts': contexts, 'units': {}, 'facts': facts, 'labels': {}, 'pre': pre, 'cal': cal, 'def': {}, 'roles': {}}
    return N.Filing(F)


PROFIT = {'Revenues': 100, 'CostOfRevenue': 40, 'GrossProfit': 60, 'ResearchAndDevelopmentExpense': 15, 'SellingGeneralAndAdministrativeExpense': 10,
          'OperatingExpenses': 25, 'OperatingIncomeLoss': 35, 'InvestmentIncomeInterest': 3, 'InterestExpenseNonoperating': 1,
          'OtherNonoperatingIncomeExpense': 0.5, 'NonoperatingIncomeExpense': 2.5,
          'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest': 37.5, 'IncomeTaxExpenseBenefit': 7.5,
          'NetIncomeLoss': 30, 'DepreciationDepletionAndAmortization': 6, 'ShareBasedCompensation': 4, 'IncreaseDecreaseInAccountsReceivable': 5,
          'NetCashProvidedByUsedInOperatingActivities': 35, 'PaymentsToAcquirePropertyPlantAndEquipment': 20, 'ProceedsFromSaleOfPropertyPlantAndEquipment': 2,
          'NetCashProvidedByUsedInInvestingActivities': -18, 'PaymentsForRepurchaseOfCommonStock': 10, 'PaymentsOfDividends': 5,
          'NetCashProvidedByUsedInFinancingActivities': -15,
          'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect': 2}
SCALE = 1e9


def scaled(d, f=SCALE):
    return {k: v * f for k, v in d.items()}


def balanced(nodes, links):
    for n in nodes:
        i = sum(l['v'] for l in links if l['t'] == n['id'])
        o = sum(l['v'] for l in links if l['s'] == n['id'])
        if i and o and abs(i - o) > 1e-6 * max(i, o):
            return n['id']
    return None


class Structure(unittest.TestCase):
    def setUp(self):
        self.FL = filing(scaled(PROFIT), scaled(PROFIT, 0.8 * SCALE), {'Q': {'AMember': 70 * SCALE, 'BMember': 30 * SCALE},
                                                                      'PQ': {'AMember': 50 * SCALE, 'BMember': 30 * SCALE}})
        self.F = D.read_filing(self.FL)

    def test_the_statements_and_the_note(self):
        F = self.F
        self.assertEqual(F['periods']['fq'], 1)
        self.assertEqual(F['root'], G + 'NetIncomeLoss')
        self.assertIn('Other Income', F['via'][G + 'NonoperatingIncomeExpense'])         # split by the note
        self.assertEqual(F['axis'], AX)                                                  # revenue by products
        self.assertTrue(F['cash_root'].startswith('cf>'))

    def test_flows(self):
        F = self.F
        cur, py = D.quarter_values(F, None)
        nodes, links = D.spec_of(F, cur, None, py)
        ids = {n['id']: n for n in nodes}
        for m in ('revenue', 'gp', 'cor', 'opex', 'oi', 'pretax', 'tax', 'net', 'ocf', 'nonop'):
            self.assertIn(m, ids)
        self.assertIsNone(balanced(nodes, links))
        L = {(l['s'], l['t']): l['v'] / SCALE for l in links}
        self.assertAlmostEqual(L[('revenue', 'gp')], 60)
        self.assertAlmostEqual(L[('revenue', 'cor')], 40)
        self.assertAlmostEqual(L[('gp', 'opex')], 25)
        self.assertAlmostEqual(L[('pretax', 'tax')], 7.5)
        self.assertAlmostEqual(L[('net', 'ocf')], 25)                        # net income less the receivables it did not collect
        self.assertAlmostEqual(L[('k:' + G + 'Revenues|' + AX + '=x:AMember', 'revenue')], 70)
        # colours: revenue grey, costs red, profit and gains green, non-cash items blue
        self.assertEqual(ids['revenue']['color'], 'rev')
        self.assertEqual(ids['k:' + G + 'ResearchAndDevelopmentExpense']['color'], 'cost')
        self.assertEqual(ids['k:' + G + 'InvestmentIncomeInterest']['color'], 'profit')
        self.assertEqual(ids['k:cf>' + G + 'ShareBasedCompensation']['color'], 'noncash')
        # columns: revenue → gross profit → operating profit → pre-tax → net earnings → operating cash flow
        c = {i: ids[i]['col'] for i in ('revenue', 'gp', 'oi', 'pretax', 'net', 'ocf')}
        self.assertEqual([c['gp'] - c['revenue'], c['oi'] - c['gp'], c['pretax'] - c['oi'], c['net'] - c['pretax']], [1, 1, 1, 1])
        self.assertGreater(c['ocf'], c['net'] + 1)
        # labels: share of the parent line, Y/Y; the comparison lines
        self.assertEqual(ids['gp']['lines'][1][1], '$60.0B · 60% of revenue')
        self.assertTrue(ids['revenue']['lines'][2][1].startswith('Y/Y +25%'))
        self.assertTrue(ids['revenue']['cmp_y'].startswith('Δ +$20.0B'))

    def test_a_loss_funds_the_costs(self):
        loss = dict(PROFIT, ResearchAndDevelopmentExpense=70, OperatingExpenses=80, OperatingIncomeLoss=-20,
                    IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest=-17.5,
                    IncomeTaxExpenseBenefit=1, NetIncomeLoss=-18.5, NetCashProvidedByUsedInOperatingActivities=-13.5,
                    CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect=-46.5)
        FL = filing(scaled(loss), scaled(PROFIT, 0.8 * SCALE))
        F = D.read_filing(FL)
        cur, py = D.quarter_values(F, None)
        nodes, links = D.spec_of(F, cur, None, py)
        self.assertIsNone(balanced(nodes, links))
        L = {(l['s'], l['t']): l['v'] / SCALE for l in links}
        self.assertAlmostEqual(L[('gp', 'opex')], 60)
        self.assertAlmostEqual(L[('oi', 'opex')], 20)                       # the operating loss pays the rest of the costs
        self.assertNotIn(('gp', 'oi'), L)

    def test_a_split_that_does_not_add_up_is_left_whole(self):
        # the note's parts leave 3 of other income's 2.5 unexplained: other income stays one line
        FL = filing(dict(scaled(PROFIT), InterestExpenseNonoperating=4 * SCALE), scaled(PROFIT, 0.8 * SCALE))
        F = D.read_filing(FL)
        self.assertNotIn(G + 'NonoperatingIncomeExpense', F['J'])


class Ultra(unittest.TestCase):
    def test_segments_cash_by_use(self):
        segs = {'EastMember': {'Revenues': 70e9, 'CostOfRevenue': 30e9, 'SellingGeneralAndAdministrativeExpense': 5e9, 'OperatingIncomeLoss': 35e9,
                               'DepreciationDepletionAndAmortization': 2e9},
                'WestMember': {'Revenues': 30e9, 'CostOfRevenue': 10e9, 'SellingGeneralAndAdministrativeExpense': 5e9, 'OperatingIncomeLoss': 15e9}}
        F = D.read_filing(filing(scaled(PROFIT), scaled(PROFIT, 0.8 * SCALE), segs=segs))
        U = F['U']
        seg = U['seg']
        self.assertEqual(seg['profit'], G + 'OperatingIncomeLoss')
        east = [t for t in seg['J'] if 'EastMember' in t and 'OperatingIncomeLoss' in t][0]
        kids = {D.local(D.parse_key(k)[0]): w for k, w in seg['J'][east]}
        # revenue less cost of revenue and SG&A make the profit; depreciation is a memo line, not one of the expenses
        self.assertEqual(kids, {'Revenues': 1.0, 'CostOfRevenue': -1.0, 'SellingGeneralAndAdministrativeExpense': -1.0})
        self.assertIn(('gap:seg', 1.0), [tuple(x) for x in seg['J'][G + 'OperatingIncomeLoss']])
        self.assertEqual(U['cash_uses']['order'], ['capex', 'buyback', 'dividend'])
        vals = D.synth(U, F['vals']['cur'])
        self.assertAlmostEqual(vals['gap:seg'], -15e9)                   # 35 − 35 − 15: what the segments do not carry
        self.assertAlmostEqual(vals['cat:fcf'], 17e9)                    # operating cash flow 35 less capital spending 20 net of 2 of sales
        self.assertEqual(D.label_of(None, 'cat:buyback'), 'Share buybacks')


class Forward(unittest.TestCase):
    def test_what_the_notes_commit(self):
        T = 'us-gaap:RevenueRemainingPerformanceObligationExpectedTimingOfSatisfactionStartDateAxis'
        ctx = {'I': {'i': '2026-03-31', 'dims': {}}, 'T1': {'i': '2026-03-31', 'dims': {T: 'typed:2026-04-01'}},
               'T2': {'i': '2026-03-31', 'dims': {T: 'typed:2027-04-01'}},
               'P1': {'i': '2026-03-31', 'dims': {'srt:ShareRepurchaseProgramAxis': 'x:P2024Member'}},
               'P2': {'i': '2026-03-31', 'dims': {'srt:ShareRepurchaseProgramAxis': 'x:P2026Member'}}}
        f = lambda c, v, cx, u='USD': {'c': c, 'v': v, 'ctx': cx, 'u': u, 'd': '-6', 'id': None}
        facts = [f(G + 'RevenueRemainingPerformanceObligation', 500e9, 'I'),
                 f(G + 'RevenueRemainingPerformanceObligationPercentage', 0.4, 'T1', 'pure'),
                 f(G + 'RevenueRemainingPerformanceObligationPercentage', 0.3, 'T2', 'pure'),
                 {'c': G + 'RevenueRemainingPerformanceObligationExpectedTimingOfSatisfactionPeriod1', 'v': 'P12M', 'ctx': 'T1', 'u': None, 'd': None, 'id': None},
                 f(G + 'StockRepurchaseProgramRemainingAuthorizedRepurchaseAmount1', 10e9, 'P1'),
                 f(G + 'StockRepurchaseProgramRemainingAuthorizedRepurchaseAmount1', 30e9, 'P2'),
                 f(G + 'RestructuringAndRelatedCostExpectedCost1', 2e9, 'I'), f(G + 'RestructuringAndRelatedCostCostIncurredToDate1', 1.5e9, 'I')]
        FL = N.Filing({'reports': [], 'contexts': ctx, 'units': {}, 'facts': facts, 'labels': {}, 'pre': {}, 'cal': {}, 'def': {}, 'roles': {}})
        out = D.forward(FL, '2026-03-31')
        self.assertEqual(out['rpo'], 500e9)
        self.assertAlmostEqual(out['rpo_12m'], 200e9)                    # 40% within twelve months
        self.assertEqual(out['buyback'], 40e9)                           # the programs' sum
        self.assertEqual(out['restructuring_left'], 0.5e9)


class Helpers(unittest.TestCase):
    def test_tidy(self):
        self.assertEqual(D.tidy('Increase (Decrease) in Accounts Receivable'), 'Accounts receivable')
        self.assertEqual(D.tidy('Federal Income Tax Expense (Benefit), Continuing Operations'), 'Federal income tax')
        self.assertEqual(D.tidy('Payments to Acquire Businesses, Net of Cash Acquired'), 'Payments to acquire businesses')

    def test_nested_members(self):
        top, groups = D._nest({'DC': 89, 'Compute': 50, 'Networking': 39, 'Gaming': 7}, 96)
        self.assertEqual(sorted(top), ['DC', 'Gaming'])
        self.assertEqual(sorted(groups['DC']), ['Compute', 'Networking'])
        self.assertIsNone(D._nest({'A': 10, 'B': 20}, 50))


if __name__ == '__main__':
    unittest.main()
