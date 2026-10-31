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


def filing(q, pq, members=None, nonop_note=True):
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
